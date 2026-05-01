from datetime import datetime, timezone
from decimal import Decimal

from market_data.providers import CoinbaseCandleProvider


UTC = timezone.utc


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self.payloads.pop(0))


def test_provider_normalizes_coinbase_candles():
    session = FakeSession(
        [
            [
                [1704067200, "90", "110", "100", "101", "12"],
                [1704153600, "91", "111", "101", "102", "13"],
            ]
        ]
    )
    provider = CoinbaseCandleProvider(session=session, base_url="https://example.test")

    candles = provider.fetch_candles(
        "BTC-USD",
        "1d",
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 3, tzinfo=UTC),
    )

    assert [candle.timestamp.day for candle in candles] == [1, 2]
    assert candles[0].product_id == "BTC-USD"
    assert candles[0].granularity == "1d"
    assert candles[0].source == "coinbase"
    assert candles[1].close == Decimal("102")
    assert session.calls[0]["params"]["granularity"] == 86400


def test_provider_paginates_long_ranges():
    payload = [[1704067200, "90", "110", "100", "101", "12"]]
    session = FakeSession([payload, payload])
    provider = CoinbaseCandleProvider(session=session, base_url="https://example.test")

    provider.fetch_candles(
        "BTC-USD",
        "1d",
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2025, 8, 1, tzinfo=UTC),
    )

    assert len(session.calls) == 2
