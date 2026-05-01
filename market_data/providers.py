from datetime import datetime
from decimal import Decimal

import requests

from market_data.candles import (
    Candle,
    UTC,
    ensure_utc,
    format_coinbase_timestamp,
    granularity_to_seconds,
)


class CoinbaseCandleProvider:
    BASE_URL = "https://api.exchange.coinbase.com"
    MAX_CANDLES_PER_REQUEST = 300
    SOURCE_NAME = "coinbase"

    def __init__(self, session=None, base_url=None):
        self._session = session or requests.Session()
        self._base_url = base_url or self.BASE_URL

    def fetch_candles(self, product_id, granularity, start, end):
        start = ensure_utc(start)
        end = ensure_utc(end)
        if end <= start:
            return []

        all_candles = []
        step_seconds = granularity_to_seconds(granularity)
        window_seconds = step_seconds * self.MAX_CANDLES_PER_REQUEST

        cursor = start
        while cursor < end:
            window_end = min(
                end,
                datetime.fromtimestamp(cursor.timestamp() + window_seconds, tz=UTC),
            )
            all_candles.extend(
                self._fetch_window(product_id, granularity, cursor, window_end)
            )
            cursor = window_end

        deduped = {
            candle.timestamp: candle for candle in all_candles if start <= candle.timestamp < end
        }
        return [deduped[timestamp] for timestamp in sorted(deduped)]

    def _fetch_window(self, product_id, granularity, start, end):
        response = self._session.get(
            f"{self._base_url}/products/{product_id}/candles",
            params={
                "granularity": granularity_to_seconds(granularity),
                "start": format_coinbase_timestamp(start),
                "end": format_coinbase_timestamp(end),
            },
            timeout=20,
        )
        response.raise_for_status()

        candles = []
        for raw_candle in response.json():
            candle = self._normalize_candle(raw_candle, product_id, granularity)
            if start <= candle.timestamp < end:
                candles.append(candle)
        return candles

    def _normalize_candle(self, raw_candle, product_id, granularity):
        timestamp, low, high, open_, close, volume = raw_candle
        return Candle(
            timestamp=datetime.fromtimestamp(int(timestamp), tz=UTC),
            open=Decimal(str(open_)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=Decimal(str(volume)),
            source=self.SOURCE_NAME,
            product_id=product_id,
            granularity=granularity,
        )

