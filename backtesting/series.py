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

    @classmethod
    def from_csv(cls, path):
        candles = CandleStore(path).load()
        if not candles:
            raise ValueError(f"No candles found in {path}")
        first = candles[0]
        return cls(first.product_id, first.granularity, candles)

    def candles(self):
        return list(self._candles)

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
        closes = []
        for candle in self._candles:
            if candle.timestamp > timestamp:
                break
            closes.append(candle.close)

        if len(closes) < window_days:
            return None

        window = closes[-window_days:]
        return sum(window) / Decimal(window_days)

    def trailing_return(self, timestamp, window_days):
        current_close = self.close_at(timestamp)
        if current_close is None:
            return None

        lookback_close = self.close_at(timestamp.replace() - timedelta(days=window_days))
        if lookback_close is None or lookback_close == 0:
            return None

        return (current_close / lookback_close) - Decimal("1")

    def latest_close(self):
        return self._candles[-1].close
