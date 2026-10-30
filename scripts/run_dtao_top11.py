#!/usr/bin/env python3
"""Compare historical top-emission subnet baskets in 90-day price-only tests."""

import argparse
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtesting.dtao_top11 import evaluate_cohorts, load_emissions, load_prices, make_cohorts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, default=Path("data/dtao/daily.csv"))
    parser.add_argument("--emissions", type=Path, default=Path("data/dtao/emissions"))
    parser.add_argument("--basket-size", type=int, default=11)
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--triggers", default="1.1,1.2,1.3,1.5")
    args = parser.parse_args()
    triggers = [Decimal(value.strip()) for value in args.triggers.split(",")]
    cohorts, skipped = make_cohorts(
        load_prices(args.prices), load_emissions(args.emissions),
        args.basket_size, args.window_days,
    )
    results, summaries = evaluate_cohorts(cohorts, triggers)
    print(f"Cohorts: {len(cohorts)}; skipped entry dates: {len(skipped)}")
    print("Top emissions: prior-day TAO injected into subnet pools per block; no future ranking.")
    print("1 TAO per subnet at entry. Missing/deregistered subnet is worth zero thereafter.")
    print("Entry       Signal      Top subnets                                  Lost  Hold TAO")
    first_runs = next(iter(results.values()))
    for cohort, run in zip(cohorts, first_runs):
        names = ",".join(map(str, cohort.netuids))
        print(
            f"{run.start}  {cohort.signal_day}  {names:<44} "
            f"{len(cohort.lost_subnets):>4}  {run.hold_tao:>8.3f}"
        )
    print("Trigger  Wins  Median trim minus hold  Lower drawdown  Median hold  Median trim")
    from statistics import median
    for trigger, runs in results.items():
        summary = summaries[trigger]
        print(
            f"{trigger:>7}  {summary['wins']:>2}/{len(runs):<2}  "
            f"{summary['median_delta_tao']:>+21.3f}  "
            f"{summary['lower_drawdown']:>2}/{len(runs):<2}  "
            f"{median(run.hold_tao for run in runs):>11.3f}  "
            f"{median(run.trim_tao for run in runs):>11.3f}"
        )
    print("Excludes dividends, execution slippage and fees; monthly entry windows overlap.")


if __name__ == "__main__":
    main()
