from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from market_data.store import CandleStore


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    close: Decimal


class PriceSeries:
    def __init__(self, product_id, granularity, candles):
        self.product_id = product_id
        self.granularity = granularity
        self._candles = list(candles)
        self._by_timestamp = {candle.timestamp: candle for candle in self._candles}
        self._timestamps = [candle.timestamp for candle in self._candles]
        self._index_by_timestamp = {
            candle.timestamp: index for index, candle in enumerate(self._candles)
        }
        self._closes = [candle.close for candle in self._candles]
        self._prefix_close_sums = []
        running_sum = Decimal("0")
        for close in self._closes:
            running_sum += close
            self._prefix_close_sums.append(running_sum)

    @classmethod
    def from_csv(cls, path):
        candles = CandleStore(path).load()
        if not candles:
            raise ValueError(f"No candles found in {path}")
        first = candles[0]
        return cls(first.product_id, first.granularity, candles)

    def candles(self):
        return list(self._candles)

    def candles_since(self, since):
        return [candle for candle in self._candles if candle.timestamp >= since]

    def sunday_candles_since(self, since):
        return [
            candle
            for candle in self._candles
            if candle.timestamp >= since and candle.timestamp.weekday() == 6
        ]

    def get_candle(self, timestamp):
        return self._by_timestamp.get(timestamp)

    def close_at(self, timestamp):
        candle = self.get_candle(timestamp)
        if candle is None:
            return None
        return candle.close

    def moving_average(self, timestamp, window_days):
        index = self._index_by_timestamp.get(timestamp)
        if index is None:
            return None
        if index + 1 < window_days:
            return None

        window_end = self._prefix_close_sums[index]
        window_start = (
            self._prefix_close_sums[index - window_days]
            if index >= window_days
            else Decimal("0")
        )
        return (window_end - window_start) / Decimal(window_days)

    def trailing_return(self, timestamp, window_days):
        index = self._index_by_timestamp.get(timestamp)
        if index is None or index < window_days:
            return None
        current_close = self._closes[index]
        lookback_close = self._closes[index - window_days]
        if lookback_close is None or lookback_close == 0:
            return None

        return (current_close / lookback_close) - Decimal("1")

    def latest_close(self):
        return self._candles[-1].close
