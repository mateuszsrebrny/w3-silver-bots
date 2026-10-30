from datetime import date, timedelta
from decimal import Decimal
import pytest

from backtesting.dtao_top11 import evaluate_cohorts, make_cohorts


def test_prior_day_ranking_and_delisting():
    entry = date(2025, 3, 2)
    prices = {}
    for offset in range(4):
        day = entry + timedelta(days=offset)
        prices[(day, 1)] = (10, Decimal("1"))
        if offset < 2:
            prices[(day, 2)] = (20, Decimal("1"))
        if offset >= 2:
            prices[(day, 2)] = (21, Decimal("100"))
    emissions = {
        entry - timedelta(days=1): [(1, 10, 200), (2, 20, 100)],
        entry: [(1, 10, 10), (2, 20, 999)],
    }
    cohorts, skipped = make_cohorts(prices, emissions, basket_size=1, window_days=4)
    assert skipped == []
    assert cohorts[0].netuids == (1,)
    cohorts, _ = make_cohorts(prices, emissions, basket_size=2, window_days=4)
    assert cohorts[0].lost_subnets == (2,)
    assert cohorts[0].days[-1][1][2] == 0
    results, _ = evaluate_cohorts(cohorts, [Decimal("1.2")])
    assert results[Decimal("1.2")][0].hold_tao == 1


def test_skips_stale_ranking_instead_of_replacing_with_future_knowledge():
    entry = date(2025, 3, 2)
    prices = {(entry + timedelta(days=i), 2): (20, Decimal("1")) for i in range(2)}
    emissions = {entry - timedelta(days=1): [(1, 10, 200), (2, 20, 100)]}
    cohorts, skipped = make_cohorts(prices, emissions, basket_size=1, window_days=2)
    assert cohorts == []
    assert skipped == [entry]


def test_missing_entire_snapshot_is_not_a_delisting():
    entry = date(2025, 3, 2)
    prices = {
        (entry, 1): (10, Decimal("1")),
        (entry + timedelta(days=2), 1): (10, Decimal("1")),
    }
    emissions = {entry - timedelta(days=1): [(1, 10, 200)]}
    with pytest.raises(ValueError, match="Missing daily price snapshot"):
        make_cohorts(prices, emissions, basket_size=1, window_days=3)
