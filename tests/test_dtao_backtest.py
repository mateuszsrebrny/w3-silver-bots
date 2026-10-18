from datetime import date
from decimal import Decimal

import pytest

from backtesting.dtao import load_current_prices, run_price_only_backtest


def test_load_uses_current_subnet_incarnation(tmp_path):
    path = tmp_path / "daily.csv"
    path.write_text(
        "date,netuid,registered_at,price_tao_per_alpha\n"
        "2026-02-05,1,old,9\n"
        "2026-02-06,1,new,1\n"
        "2026-02-07,1,new,2\n"
        "2026-02-05,2,stable,3\n"
        "2026-02-06,2,stable,4\n"
        "2026-02-07,2,stable,5\n"
    )

    days = load_current_prices(path, [1, 2])

    assert days == [
        (date(2026, 2, 6), {1: Decimal("1"), 2: Decimal("4")}),
        (date(2026, 2, 7), {1: Decimal("2"), 2: Decimal("5")}),
    ]


def test_load_rejects_missing_days_instead_of_forward_filling(tmp_path):
    path = tmp_path / "daily.csv"
    path.write_text(
        "date,netuid,registered_at,price_tao_per_alpha\n"
        "2026-02-06,1,a,1\n"
        "2026-02-08,1,a,2\n"
    )

    with pytest.raises(ValueError, match="Missing price"):
        load_current_prices(path, [1])


def test_weekly_trim_sells_above_trigger_and_keeps_proceeds_in_tao():
    days = [
        (date(2026, 2, 7), {1: Decimal("1"), 2: Decimal("1")}),
        (date(2026, 2, 8), {1: Decimal("1.3"), 2: Decimal("0.5")}),
        (date(2026, 2, 9), {1: Decimal("0.5"), 2: Decimal("0.5")}),
    ]

    result = run_price_only_backtest(days)

    assert result.initial_tao == Decimal("2")
    assert result.hold_tao == Decimal("1.0")
    assert result.trim_cash_tao == Decimal("0.3")
    assert result.trim_tao == Decimal("0.3") + Decimal("0.5") / Decimal("1.3") + Decimal("0.5")
    assert result.trim_count == 1
    assert result.hold_max_drawdown == Decimal("0.5")
    assert result.trim_max_drawdown < result.hold_max_drawdown


def test_invalid_trim_parameters():
    days = [(date(2026, 2, 7), {1: Decimal("1")})]

    with pytest.raises(ValueError, match="Trim trigger"):
        run_price_only_backtest(days, trim_trigger_tao=Decimal("1"))
