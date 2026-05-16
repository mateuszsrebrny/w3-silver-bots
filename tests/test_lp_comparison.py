from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backtesting.lp_comparison import LPComparisonBacktestEngine
from backtesting.multi_asset import MultiAssetSeries
from backtesting.series import PriceSeries
from market_data.candles import Candle


UTC = timezone.utc


def make_series(closes, product_id):
    candles = []
    start = datetime(2024, 1, 1, tzinfo=UTC)
    for offset, close in enumerate(closes):
        timestamp = start + timedelta(days=offset)
        close_decimal = Decimal(str(close))
        candles.append(
            Candle(
                timestamp=timestamp,
                open=close_decimal,
                high=close_decimal,
                low=close_decimal,
                close=close_decimal,
                volume=Decimal("1"),
                source="test",
                product_id=product_id,
                granularity="1d",
            )
        )
    return PriceSeries(product_id, "1d", candles)


def test_lp_matches_hold_50_50_when_relative_price_is_unchanged():
    bundle = MultiAssetSeries(
        {
            "BTC-USD": make_series([100, 120], "BTC-USD"),
            "ETH-USD": make_series([200, 240], "ETH-USD"),
        }
    )

    results = LPComparisonBacktestEngine(fee_yield_pct="0").run_pair(
        bundle,
        "wbtc-weth",
        datetime(2024, 1, 1, tzinfo=UTC),
        initial_value="1000",
    )

    hold_50 = next(result for result in results if result.strategy_name.endswith("hold_50_50"))
    lp = next(result for result in results if result.strategy_name.endswith("lp_50_50"))
    assert hold_50.ending_value == lp.ending_value


def test_lp_underperforms_hold_50_50_when_relative_price_moves_without_fees():
    bundle = MultiAssetSeries(
        {
            "BTC-USD": make_series([100, 200], "BTC-USD"),
            "ETH-USD": make_series([100, 100], "ETH-USD"),
        }
    )

    results = LPComparisonBacktestEngine(fee_yield_pct="0").run_pair(
        bundle,
        "wbtc-weth",
        datetime(2024, 1, 1, tzinfo=UTC),
        initial_value="1000",
    )

    hold_50 = next(result for result in results if result.strategy_name.endswith("hold_50_50"))
    lp = next(result for result in results if result.strategy_name.endswith("lp_50_50"))
    assert lp.ending_value < hold_50.ending_value


def test_lp_fee_overlay_can_exceed_zero_fee_lp():
    bundle = MultiAssetSeries(
        {
            "BTC-USD": make_series([100, 100, 100], "BTC-USD"),
            "ETH-USD": make_series([100, 100, 100], "ETH-USD"),
        }
    )

    no_fee = LPComparisonBacktestEngine(fee_yield_pct="0").run_pair(
        bundle,
        "wbtc-weth",
        datetime(2024, 1, 1, tzinfo=UTC),
        initial_value="1000",
    )
    with_fee = LPComparisonBacktestEngine(fee_yield_pct="36.5").run_pair(
        bundle,
        "wbtc-weth",
        datetime(2024, 1, 1, tzinfo=UTC),
        initial_value="1000",
    )

    no_fee_lp = next(result for result in no_fee if result.strategy_name.endswith("lp_50_50"))
    with_fee_lp = next(result for result in with_fee if result.strategy_name.endswith("lp_50_50"))
    assert with_fee_lp.ending_value > no_fee_lp.ending_value


def test_pair_run_includes_both_single_asset_holds():
    bundle = MultiAssetSeries(
        {
            "BTC-USD": make_series([100, 100], "BTC-USD"),
            "ETH-USD": make_series([200, 200], "ETH-USD"),
        }
    )

    results = LPComparisonBacktestEngine(fee_yield_pct="0").run_pair(
        bundle,
        "wbtc-weth",
        datetime(2024, 1, 1, tzinfo=UTC),
        initial_value="1000",
    )

    strategy_names = {result.strategy_name for result in results}
    assert "wbtc-weth_hold_btc_usd" in strategy_names
    assert "wbtc-weth_hold_eth_usd" in strategy_names
