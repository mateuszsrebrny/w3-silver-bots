from datetime import date, timedelta
from decimal import Decimal

import pytest

from backtesting.dtao_rebalance import run_rebalance_backtest
from backtesting.dtao_top11 import make_cohorts


def sample():
    start = date(2025, 3, 2)
    prices = {}
    for offset in range(37):
        day = start + timedelta(days=offset)
        prices[(day, 1)] = (10, Decimal("1") if offset < 7 else Decimal("1.3"))
        prices[(day, 2)] = (
            20, Decimal("0.5") if offset == 35 else Decimal("1")
        )
        prices[(day, 3)] = (30, Decimal("1"))
    emissions = {
        start - timedelta(days=1): [(1, 10, 300), (2, 20, 200), (3, 30, 100)],
        date(2025, 4, 5): [(3, 30, 300), (2, 20, 200), (1, 10, 100)],
        date(2025, 4, 6): [(1, 10, 300), (2, 20, 200), (3, 30, 100)],
    }
    cohorts, skipped = make_cohorts(prices, emissions, basket_size=2, window_days=37)
    assert skipped == []
    return cohorts[0], prices, emissions


def test_rotation_recycles_cash_and_topup_changes_result():
    cohort, prices, emissions = sample()
    rotate = run_rebalance_backtest(cohort, prices, emissions)
    topup = run_rebalance_backtest(cohort, prices, emissions, topup=True)
    assert rotate.rotations == topup.rotations == 1
    assert rotate.trims == topup.trims == 1
    assert rotate.topups == 0
    assert topup.topups == 1
    assert rotate.cash_tao == Decimal("0.3")
    assert topup.cash_tao == 0
    assert topup.end_tao > rotate.end_tao


def test_pure_swap_reinvests_full_exit_value_and_never_trims_winners():
    cohort, prices, emissions = sample()
    prices[(date(2025, 4, 7), 3)] = (30, Decimal("2"))
    pure = run_rebalance_backtest(cohort, prices, emissions, trigger_tao=None)
    assert pure.rotations == 1
    assert pure.trims == pure.topups == 0
    assert pure.cash_tao == 0
    assert pure.end_tao == Decimal("3.6")
    with_cost = run_rebalance_backtest(
        cohort, prices, emissions, trigger_tao=None, cost_bps=Decimal("100")
    )
    assert with_cost.end_tao == Decimal("3.54826")
    scaled = run_rebalance_backtest(
        cohort, prices, emissions, trigger_tao=None, target_tao=Decimal("2.2")
    )
    assert scaled.end_tao == Decimal("7.92")


def test_newcomer_gets_partial_allocation_when_sale_proceeds_are_insufficient():
    start = date(2025, 3, 2)
    prices = {}
    for offset in range(37):
        day = start + timedelta(days=offset)
        prices[(day, 1)] = (10, Decimal("0.5") if offset >= 35 else Decimal("1"))
        prices[(day, 2)] = (20, Decimal("1"))
    emissions = {
        start - timedelta(days=1): [(1, 10, 200), (2, 20, 100)],
        date(2025, 4, 5): [(2, 20, 200), (1, 10, 100)],
    }
    cohort, _ = make_cohorts(prices, emissions, basket_size=1, window_days=37)
    result = run_rebalance_backtest(cohort[0], prices, emissions)
    assert result.rotations == 1
    assert result.end_tao == Decimal("0.5")


def test_invalid_trigger():
    cohort, prices, emissions = sample()
    with pytest.raises(ValueError, match="Trim trigger"):
        run_rebalance_backtest(cohort, prices, emissions, trigger_tao=Decimal("1"))
    with pytest.raises(ValueError, match="Top-ups require"):
        run_rebalance_backtest(cohort, prices, emissions, trigger_tao=None, topup=True)
    with pytest.raises(ValueError, match="Trade cost"):
        run_rebalance_backtest(cohort, prices, emissions, cost_bps=Decimal("10000"))
    with pytest.raises(ValueError, match="Target per subnet"):
        run_rebalance_backtest(cohort, prices, emissions, target_tao=Decimal("0"))


def test_missing_monthly_signal_is_an_error():
    cohort, prices, emissions = sample()
    del emissions[date(2025, 4, 5)]
    with pytest.raises(ValueError, match="Missing emission signal"):
        run_rebalance_backtest(cohort, prices, emissions)


def test_daily_rotation_uses_previous_day_and_can_trade_midweek():
    start = date(2025, 3, 2)
    prices = {
        (start + timedelta(days=offset), netuid): (netuid * 10, Decimal("1"))
        for offset in range(3) for netuid in (1, 2)
    }
    emissions = {
        start - timedelta(days=1): [(1, 10, 200), (2, 20, 100)],
        start: [(1, 10, 200), (2, 20, 100)],
        start + timedelta(days=1): [(2, 20, 200), (1, 10, 100)],
        start + timedelta(days=2): [(1, 10, 200), (2, 20, 100)],
    }
    cohort, _ = make_cohorts(prices, emissions, basket_size=1, window_days=3)
    daily = run_rebalance_backtest(
        cohort[0], prices, emissions, trigger_tao=None, rotation_cadence="daily"
    )
    monthly = run_rebalance_backtest(cohort[0], prices, emissions, trigger_tao=None)
    assert daily.rotations == 1
    assert monthly.rotations == 0
    assert daily.end_tao == monthly.end_tao == 1


def test_daily_rotation_requires_every_prior_day_signal():
    start = date(2025, 3, 2)
    prices = {(start + timedelta(days=offset), 1): (10, Decimal("1")) for offset in range(2)}
    emissions = {start - timedelta(days=1): [(1, 10, 200)]}
    cohort, _ = make_cohorts(prices, emissions, basket_size=1, window_days=2)
    with pytest.raises(ValueError, match="Missing emission signal"):
        run_rebalance_backtest(cohort[0], prices, emissions, trigger_tao=None, rotation_cadence="daily")


def test_daily_rotation_waits_when_fewer_than_basket_size_have_positive_emission():
    start = date(2025, 3, 2)
    prices = {
        (start + timedelta(days=offset), netuid): (netuid * 10, Decimal("1"))
        for offset in range(2) for netuid in (1, 2)
    }
    emissions = {
        start - timedelta(days=1): [(1, 10, 200), (2, 20, 100)],
        start: [(1, 10, 0), (2, 20, 100)],
    }
    cohort, _ = make_cohorts(prices, emissions, basket_size=2, window_days=2)
    result = run_rebalance_backtest(
        cohort[0], prices, emissions, trigger_tao=None, rotation_cadence="daily"
    )
    assert result.rotations == 0
    assert result.skipped_signals == 1
