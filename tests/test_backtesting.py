from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backtesting.engine import BacktestEngine
from backtesting.multi_asset import MultiAssetSeries
from backtesting.reporting import format_results_markdown, format_results_table, write_results_csv
from backtesting.rotation_engine import RotationBacktestEngine
from backtesting.rotation_strategies import (
    BTCCoreETHOverlay,
    BTCOnlyWeekly,
    BuyETHBelowMAOtherwiseBTC,
    BuyFurtherBelowMAWeekly,
    BuyStrongerReturnWeekly,
    EqualSplitWeekly,
)
from backtesting.series import PriceSeries
from backtesting.strategies import (
    WeeklyDipDCA,
    WeeklyDrawdownScaledDCA,
    WeeklyFixedDCA,
    WeeklyMAScaledDCA,
    WeeklyMATrendDCA,
)
from market_data.candles import Candle


UTC = timezone.utc


def make_series(closes, start=datetime(2024, 1, 1, tzinfo=UTC), product_id="BTC-USD"):
    candles = []
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
                source="coinbase",
                product_id=product_id,
                granularity="1d",
            )
        )
    return PriceSeries(product_id, "1d", candles)


def test_price_series_moving_average_uses_trailing_window():
    series = make_series([10, 20, 30, 40, 50])

    moving_average = series.moving_average(datetime(2024, 1, 5, tzinfo=UTC), 3)

    assert moving_average == Decimal("40")


def test_fixed_dca_buys_on_7_day_cadence():
    closes = [100 + day for day in range(21)]
    series = make_series(closes)
    result = BacktestEngine(contribution_amount_usd="100", interval_days=7).run(
        series,
        WeeklyFixedDCA("100"),
        datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert result.trade_count == 3
    assert result.total_contributed == Decimal("300")
    assert result.total_invested == Decimal("300")
    assert result.ending_cash == Decimal("0")
    assert result.contribution_interval == "7d"


def test_weekly_ma_trend_dca_skips_without_history_then_buys_when_above_ma():
    closes = [Decimal("100")] * 14 + [Decimal("200")]
    series = make_series(closes)
    result = BacktestEngine(contribution_amount_usd="100", interval_days=7).run(
        series,
        WeeklyMATrendDCA("100", window_days=7),
        datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert result.trade_count == 1
    assert result.total_contributed == Decimal("300")
    assert result.total_invested == Decimal("100")
    assert result.ending_cash == Decimal("200")


def test_weekly_dip_dca_buys_when_below_ma():
    closes = [Decimal("100")] * 14 + [Decimal("50")]
    series = make_series(closes)
    result = BacktestEngine(contribution_amount_usd="100", interval_days=7).run(
        series,
        WeeklyDipDCA("100", window_days=7),
        datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert result.trade_count == 1
    assert result.total_invested == Decimal("100")


def test_fixed_dca_can_run_every_3_days():
    closes = [100 + day for day in range(12)]
    series = make_series(closes)
    result = BacktestEngine(contribution_amount_usd="100", interval_days=3).run(
        series,
        WeeklyFixedDCA("100"),
        datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert result.trade_count == 4
    assert result.total_contributed == Decimal("400")
    assert result.contribution_interval == "3d"


def test_ma_scaled_dca_buys_more_below_ma_and_less_above():
    series = make_series([100] * 10 + [80] + [120])
    strategy = WeeklyMAScaledDCA("100", window_days=5, below_multiplier="2", above_multiplier="0.5")

    below_decision = strategy.decide(series.candles()[10], series, None)
    above_decision = strategy.decide(series.candles()[11], series, None)

    assert below_decision.buy_usd == Decimal("200")
    assert above_decision.buy_usd == Decimal("50.0")


def test_drawdown_scaled_dca_buys_more_on_deeper_drawdown():
    series = make_series([100, 105, 110, 95, 80, 120])
    strategy = WeeklyDrawdownScaledDCA("100", lookback_days=5)

    mild = strategy.decide(series.candles()[3], series, None)
    deep = strategy.decide(series.candles()[4], series, None)
    near_high = strategy.decide(series.candles()[5], series, None)

    assert mild.buy_usd == Decimal("150.0")
    assert deep.buy_usd == Decimal("200.0")
    assert near_high.buy_usd == Decimal("50.0")


def test_results_table_contains_strategy_names():
    closes = [100 + day for day in range(21)]
    series = make_series(closes)
    engine = BacktestEngine(contribution_amount_usd="100", interval_days=7)
    results = [
        engine.run(series, WeeklyFixedDCA("100"), datetime(2024, 1, 1, tzinfo=UTC)),
        engine.run(series, WeeklyMATrendDCA("100", window_days=7), datetime(2024, 1, 1, tzinfo=UTC)),
    ]

    table = format_results_table(results)

    assert "weekly_fixed_dca" in table
    assert "weekly_ma_trend_dca" in table


def test_reporting_can_write_csv_and_markdown(tmp_path):
    closes = [100 + day for day in range(21)]
    series = make_series(closes)
    result = BacktestEngine(contribution_amount_usd="100", interval_days=7).run(
        series,
        WeeklyFixedDCA("100"),
        datetime(2024, 1, 1, tzinfo=UTC),
    )
    csv_path = tmp_path / "results.csv"

    write_results_csv(csv_path, [result])
    markdown = format_results_markdown([result])

    assert "strategy_label" in csv_path.read_text()
    assert "weekly_fixed_dca(weekly_amount_usd=100)" in markdown


def test_multi_asset_series_common_sundays_and_returns():
    btc = make_series([100 + day for day in range(40)], product_id="BTC-USD")
    eth = make_series([200 + day for day in range(40)], product_id="ETH-USD")
    bundle = MultiAssetSeries({"BTC-USD": btc, "ETH-USD": eth})
    sunday_timestamps = bundle.common_sunday_timestamps_since(datetime(2024, 1, 1, tzinfo=UTC))

    assert sunday_timestamps[0] == datetime(2024, 1, 7, tzinfo=UTC)
    assert bundle.trailing_return("BTC-USD", datetime(2024, 1, 14, tzinfo=UTC), 7) > 0
    assert bundle.common_timestamps_since(datetime(2024, 1, 1, tzinfo=UTC))[0] == datetime(2024, 1, 1, tzinfo=UTC)


def test_rotation_engine_btc_only_deploys_all_cash():
    btc = make_series([100 + day for day in range(30)], product_id="BTC-USD")
    eth = make_series([200 + day for day in range(30)], product_id="ETH-USD")
    bundle = MultiAssetSeries({"BTC-USD": btc, "ETH-USD": eth})
    result = RotationBacktestEngine("100", interval_days=7).run(
        bundle,
        BTCOnlyWeekly(),
        datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert result.symbol == "BTC-USD+ETH-USD"
    assert result.trade_count == 5
    assert result.total_invested == Decimal("500")
    assert result.ending_cash == Decimal("0")
    assert result.contribution_interval == "7d"


def test_rotation_engine_equal_split_creates_two_trades_per_sunday():
    btc = make_series([100 + day for day in range(30)], product_id="BTC-USD")
    eth = make_series([200 + day for day in range(30)], product_id="ETH-USD")
    bundle = MultiAssetSeries({"BTC-USD": btc, "ETH-USD": eth})
    result = RotationBacktestEngine("100", interval_days=7).run(
        bundle,
        EqualSplitWeekly(),
        datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert result.trade_count == 10


def test_rotation_engine_can_run_every_5_days():
    btc = make_series([100 + day for day in range(30)], product_id="BTC-USD")
    eth = make_series([200 + day for day in range(30)], product_id="ETH-USD")
    bundle = MultiAssetSeries({"BTC-USD": btc, "ETH-USD": eth})
    result = RotationBacktestEngine("100", interval_days=5).run(
        bundle,
        BTCOnlyWeekly(),
        datetime(2024, 1, 1, tzinfo=UTC),
    )

    assert result.trade_count == 6
    assert result.total_contributed == Decimal("600")
    assert result.contribution_interval == "5d"


def test_buy_stronger_return_prefers_outperformer():
    btc = make_series([100 + day for day in range(40)], product_id="BTC-USD")
    eth = make_series([100 + (day * 3) for day in range(40)], product_id="ETH-USD")
    bundle = MultiAssetSeries({"BTC-USD": btc, "ETH-USD": eth})
    strategy = BuyStrongerReturnWeekly(window_days=7)
    decision = strategy.decide(datetime(2024, 1, 21, tzinfo=UTC), bundle, None)

    assert decision.weights == {"ETH-USD": Decimal("1")}


def test_buy_further_below_ma_prefers_deeper_discount():
    btc = make_series([100] * 10 + [90], product_id="BTC-USD")
    eth = make_series([100] * 10 + [80], product_id="ETH-USD")
    bundle = MultiAssetSeries({"BTC-USD": btc, "ETH-USD": eth})
    strategy = BuyFurtherBelowMAWeekly(window_days=5)

    decision = strategy.decide(datetime(2024, 1, 11, tzinfo=UTC), bundle, None)

    assert decision.weights == {"ETH-USD": Decimal("1")}


def test_buy_eth_below_ma_otherwise_btc_prefers_eth_discount():
    btc = make_series([100] * 10 + [110], product_id="BTC-USD")
    eth = make_series([100] * 10 + [80], product_id="ETH-USD")
    bundle = MultiAssetSeries({"BTC-USD": btc, "ETH-USD": eth})
    strategy = BuyETHBelowMAOtherwiseBTC(window_days=5)

    decision = strategy.decide(datetime(2024, 1, 11, tzinfo=UTC), bundle, None)

    assert decision.weights == {"ETH-USD": Decimal("1")}


def test_btc_core_eth_overlay_adds_eth_only_when_strong():
    btc = make_series([100 + day for day in range(120)], product_id="BTC-USD")
    eth = make_series([100 + (day * 2) for day in range(120)], product_id="ETH-USD")
    bundle = MultiAssetSeries({"BTC-USD": btc, "ETH-USD": eth})
    strategy = BTCCoreETHOverlay(ma_window_days=20, return_window_days=28, eth_weight="0.30")

    decision = strategy.decide(datetime(2024, 4, 29, tzinfo=UTC), bundle, None)

    assert decision.weights == {"BTC-USD": Decimal("0.70"), "ETH-USD": Decimal("0.30")}
