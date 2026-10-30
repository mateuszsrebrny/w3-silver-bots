from datetime import date, timedelta
from decimal import Decimal

import pytest

from backtesting.dtao_sweep import monthly_windows, run_threshold_sweep


def sample_days():
    start = date(2026, 1, 30)
    return [
        (start + timedelta(days=index), {1: Decimal("1") + Decimal(index) / 100})
        for index in range(65)
    ]


def test_monthly_windows_use_first_available_day_and_minimum_length():
    windows = monthly_windows(sample_days(), minimum_days=30)

    assert [window[0][0] for window in windows] == [
        date(2026, 1, 30), date(2026, 2, 1), date(2026, 3, 1)
    ]


def test_sweep_reports_results_for_each_threshold_and_window():
    results, summaries = run_threshold_sweep(
        sample_days(), [Decimal("1.1"), Decimal("1.5")], minimum_days=30
    )

    assert len(results[Decimal("1.1")]) == 3
    assert len(results[Decimal("1.5")]) == 3
    assert summaries[0].trigger_tao == Decimal("1.1")
    assert summaries[0].windows == 3
    assert summaries[0].trim_wins == 0
    assert results[Decimal("1.1")][0].trim_count > results[Decimal("1.5")][0].trim_count


def test_sweep_rejects_duplicate_triggers():
    with pytest.raises(ValueError, match="distinct"):
        run_threshold_sweep(sample_days(), [Decimal("1.2"), Decimal("1.2")])


def test_sweep_rejects_too_short_dataset():
    with pytest.raises(ValueError, match="No monthly windows"):
        run_threshold_sweep(sample_days(), [Decimal("1.2")], minimum_days=90)
