"""Historical, emission-ranked dTAO baskets without staking rewards."""

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median

from backtesting.dtao import Result, run_price_only_backtest


@dataclass(frozen=True)
class Cohort:
    signal_day: date
    netuids: tuple[int, ...]
    days: list[tuple[date, dict[int, Decimal]]]
    lost_subnets: tuple[int, ...]


def load_prices(path: Path):
    prices = {}
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            day = date.fromisoformat(row["date"])
            key = (day, int(row["netuid"]))
            if key in prices:
                raise ValueError(f"Duplicate price: {key}")
            price = Decimal(row["price_tao_per_alpha"])
            if not price.is_finite() or price <= 0:
                raise ValueError(f"Invalid price: {key}")
            prices[key] = (int(row["registered_at"]), price)
    return prices


def load_emissions(directory: Path):
    emissions = {}
    for path in sorted(directory.glob("*.csv")):
        day = date.fromisoformat(path.stem)
        rows = []
        with path.open(newline="") as source:
            for row in csv.DictReader(source):
                if date.fromisoformat(row["date"]) != day:
                    raise ValueError(f"Emission date mismatch: {path}")
                rows.append((int(row["netuid"]), int(row["registered_at"]), int(row["tao_in_emission_rao"])))
        emissions[day] = rows
    return emissions


def make_cohorts(prices, emissions, basket_size=11, window_days=90):
    if basket_size < 1 or window_days < 2:
        raise ValueError("Basket size must be positive and window must span at least two days")
    available_days = sorted({day for day, _ in prices})
    if not available_days:
        raise ValueError("No price data")
    available_set = set(available_days)
    last_day = available_days[-1]
    cohorts = []
    skipped = []
    seen_months = set()
    for entry_day in available_days:
        month = (entry_day.year, entry_day.month)
        if entry_day.weekday() != 6 or month in seen_months:
            continue
        seen_months.add(month)
        if entry_day + timedelta(days=window_days - 1) > last_day:
            continue
        signal_day = entry_day - timedelta(days=1)
        ranked = sorted(
            (row for row in emissions.get(signal_day, []) if row[2] > 0),
            key=lambda row: (-row[2], row[0]),
        )[:basket_size]
        if len(ranked) != basket_size or any(
            prices.get((entry_day, netuid), (None,))[0] != registration
            for netuid, registration, _ in ranked
        ):
            skipped.append(entry_day)
            continue
        registrations = {netuid: registration for netuid, registration, _ in ranked}
        netuids = tuple(sorted(registrations))
        days = []
        lost = set()
        for offset in range(window_days):
            day = entry_day + timedelta(days=offset)
            if day not in available_set:
                raise ValueError(f"Missing daily price snapshot on {day}")
            daily = {}
            for netuid in netuids:
                observation = prices.get((day, netuid))
                if observation is None or observation[0] != registrations[netuid]:
                    lost.add(netuid)
                daily[netuid] = (
                    observation[1] if netuid not in lost else Decimal("0")
                )
            days.append((day, daily))
        cohorts.append(Cohort(signal_day, netuids, days, tuple(sorted(lost))))
    return cohorts, skipped


def evaluate_cohorts(cohorts, triggers):
    if not cohorts:
        raise ValueError("No eligible cohorts")
    if len(set(triggers)) != len(triggers):
        raise ValueError("Trim triggers must be distinct")
    results: dict[Decimal, list[Result]] = {}
    for trigger in triggers:
        results[trigger] = [run_price_only_backtest(cohort.days, trim_trigger_tao=trigger) for cohort in cohorts]
    summaries = {}
    for trigger, runs in results.items():
        deltas = [run.trim_tao - run.hold_tao for run in runs]
        summaries[trigger] = {
            "wins": sum(delta > 0 for delta in deltas),
            "median_delta_tao": median(deltas),
            "lower_drawdown": sum(run.trim_max_drawdown < run.hold_max_drawdown for run in runs),
        }
    return results, summaries
