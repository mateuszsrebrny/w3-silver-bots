"""Price-only dTAO basket backtests, denominated entirely in TAO."""

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class Result:
    start: date
    end: date
    days: int
    initial_tao: Decimal
    hold_tao: Decimal
    trim_tao: Decimal
    trim_cash_tao: Decimal
    trim_count: int
    hold_max_drawdown: Decimal
    trim_max_drawdown: Decimal


def load_current_prices(path: Path, netuids: list[int]):
    with path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    selected = set(netuids)
    if not selected or len(selected) != len(netuids):
        raise ValueError("Provide distinct subnet numbers")

    latest_registration = {}
    for row in rows:
        netuid = int(row["netuid"])
        if netuid in selected:
            latest_registration[netuid] = row["registered_at"]
    missing = selected - latest_registration.keys()
    if missing:
        raise ValueError(f"No data for subnets: {sorted(missing)}")

    prices = {netuid: {} for netuid in selected}
    for row in rows:
        netuid = int(row["netuid"])
        if netuid not in selected or row["registered_at"] != latest_registration[netuid]:
            continue
        day = date.fromisoformat(row["date"])
        price = Decimal(row["price_tao_per_alpha"])
        if not price.is_finite() or price <= 0:
            raise ValueError(f"Invalid price for subnet {netuid} on {day}")
        if day in prices[netuid]:
            raise ValueError(f"Duplicate price for subnet {netuid} on {day}")
        prices[netuid][day] = price

    start = max(min(series) for series in prices.values())
    end = min(max(series) for series in prices.values())
    days = []
    day = start
    while day <= end:
        if any(day not in prices[netuid] for netuid in selected):
            raise ValueError(f"Missing price on {day}; refusing to forward-fill")
        days.append((day, {netuid: prices[netuid][day] for netuid in selected}))
        day += timedelta(days=1)
    if len(days) < 2:
        raise ValueError("At least two shared days are required")
    return days


def _drawdown(value, peak):
    return Decimal("1") - value / peak


def run_price_only_backtest(days, target_tao=Decimal("1"), trim_trigger_tao=Decimal("1.2")):
    if target_tao <= 0 or trim_trigger_tao <= target_tao:
        raise ValueError("Trim trigger must exceed a positive target")
    start, first_prices = days[0]
    netuids = set(first_prices)
    initial_tao = target_tao * len(netuids)
    hold_alpha = {netuid: target_tao / first_prices[netuid] for netuid in netuids}
    trim_alpha = hold_alpha.copy()
    cash_tao = Decimal("0")
    trims = 0
    hold_peak = trim_peak = initial_tao
    hold_max_drawdown = trim_max_drawdown = Decimal("0")

    for day, prices in days:
        if set(prices) != netuids:
            raise ValueError(f"Subnet set changed on {day}")
        hold_value = sum(hold_alpha[n] * prices[n] for n in netuids)
        trim_value = cash_tao + sum(trim_alpha[n] * prices[n] for n in netuids)
        hold_peak = max(hold_peak, hold_value)
        trim_peak = max(trim_peak, trim_value)
        hold_max_drawdown = max(hold_max_drawdown, _drawdown(hold_value, hold_peak))
        trim_max_drawdown = max(trim_max_drawdown, _drawdown(trim_value, trim_peak))

        if day != start and day.weekday() == 6:
            for netuid in sorted(netuids):
                position_value = trim_alpha[netuid] * prices[netuid]
                if position_value > trim_trigger_tao:
                    sold_tao = position_value - target_tao
                    trim_alpha[netuid] -= sold_tao / prices[netuid]
                    cash_tao += sold_tao
                    trims += 1

    end, last_prices = days[-1]
    return Result(
        start, end, len(days), initial_tao,
        sum(hold_alpha[n] * last_prices[n] for n in netuids),
        cash_tao + sum(trim_alpha[n] * last_prices[n] for n in netuids),
        cash_tao, trims, hold_max_drawdown, trim_max_drawdown,
    )
