from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from market_data.candles import Candle
from market_data.store import CandleStore


UTC = timezone.utc


def make_candle(day, close="101"):
    timestamp = datetime(2024, 1, day, tzinfo=UTC)
    return Candle(
        timestamp=timestamp,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal(close),
        volume=Decimal("12"),
        source="coinbase",
        product_id="BTC-USD",
        granularity="1d",
    )


def test_store_save_load_roundtrip(tmp_path):
    store = CandleStore(tmp_path / "BTC-USD-1d.csv")
    candles = [make_candle(1), make_candle(2)]

    store.save(candles)

    assert store.load() == candles


def test_store_merge_dedupes_and_prefers_new(tmp_path):
    store = CandleStore(tmp_path / "BTC-USD-1d.csv")
    merged = store.merge(
        [make_candle(1, close="101"), make_candle(2, close="102")],
        [make_candle(2, close="109"), make_candle(3, close="103")],
    )

    assert [candle.timestamp.day for candle in merged] == [1, 2, 3]
    assert merged[1].close == Decimal("109")


def test_store_find_missing_timestamps(tmp_path):
    store = CandleStore(tmp_path / "BTC-USD-1d.csv")
    missing = store.find_missing_timestamps([make_candle(1), make_candle(3)])

    assert missing == [datetime(2024, 1, 2, tzinfo=UTC)]


def test_store_validate_rejects_duplicates(tmp_path):
    store = CandleStore(tmp_path / "BTC-USD-1d.csv")

    with pytest.raises(ValueError, match="Duplicate"):
        store.validate([make_candle(1), make_candle(1)])


def test_store_validate_rejects_missing_gap(tmp_path):
    store = CandleStore(tmp_path / "BTC-USD-1d.csv")

    with pytest.raises(ValueError, match="Missing candle timestamps"):
        store.validate([make_candle(1), make_candle(3)])
