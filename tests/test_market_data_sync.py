from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from market_data.candles import Candle
from market_data.store import CandleStore
from market_data.sync import MarketDataSyncService


UTC = timezone.utc


def make_candle(day):
    return Candle(
        timestamp=datetime(2024, 1, day, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal(str(100 + day)),
        volume=Decimal("10"),
        source="coinbase",
        product_id="BTC-USD",
        granularity="1d",
    )


class FakeProvider:
    def __init__(self, ranges):
        self.ranges = ranges
        self.calls = []

    def fetch_candles(self, product_id, granularity, start, end):
        key = (start, end)
        self.calls.append((product_id, granularity, start, end))
        return list(self.ranges.get(key, []))


def test_sync_seeds_missing_store(tmp_path):
    store = CandleStore(tmp_path / "BTC-USD-1d.csv")
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 3, tzinfo=UTC)
    provider = FakeProvider({(start, end): [make_candle(1), make_candle(2)]})
    service = MarketDataSyncService(provider, store)

    candles = service.sync("BTC-USD", "1d", start, end)

    assert [candle.timestamp.day for candle in candles] == [1, 2]
    assert store.exists()


def test_update_history_appends_tail(tmp_path):
    store = CandleStore(tmp_path / "BTC-USD-1d.csv")
    store.save([make_candle(1), make_candle(2)])
    start = datetime(2024, 1, 3, tzinfo=UTC)
    end = datetime(2024, 1, 5, tzinfo=UTC)
    provider = FakeProvider({(start, end): [make_candle(3), make_candle(4)]})
    service = MarketDataSyncService(provider, store)

    candles = service.update_history("BTC-USD", "1d", end)

    assert [candle.timestamp.day for candle in candles] == [1, 2, 3, 4]


def test_repair_gaps_fetches_missing_ranges(tmp_path):
    store = CandleStore(tmp_path / "BTC-USD-1d.csv")
    broken_path = store.path
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume,source,product_id,granularity",
                "2024-01-01T00:00:00Z,100,110,90,101,10,coinbase,BTC-USD,1d",
                "2024-01-03T00:00:00Z,100,110,90,103,10,coinbase,BTC-USD,1d",
            ]
        )
    )
    missing_start = datetime(2024, 1, 2, tzinfo=UTC)
    missing_end = datetime(2024, 1, 3, tzinfo=UTC)
    provider = FakeProvider({(missing_start, missing_end): [make_candle(2)]})
    service = MarketDataSyncService(provider, store)

    candles = service.repair_gaps("BTC-USD", "1d", datetime(2024, 1, 4, tzinfo=UTC))

    assert [candle.timestamp.day for candle in candles] == [1, 2, 3]


def test_update_requires_existing_store(tmp_path):
    service = MarketDataSyncService(FakeProvider({}), CandleStore(tmp_path / "BTC-USD-1d.csv"))

    with pytest.raises(ValueError, match="seed history first"):
        service.update_history("BTC-USD", "1d", datetime(2024, 1, 2, tzinfo=UTC))
