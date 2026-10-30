#!/usr/bin/env python3
"""Sweep dTAO profit-trim triggers over monthly entry dates."""

import argparse
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtesting.dtao import load_current_prices
from backtesting.dtao_sweep import run_threshold_sweep


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netuids", required=True, help="Comma-separated subnet numbers")
    parser.add_argument("--input", type=Path, default=Path("data/dtao/daily.csv"))
    parser.add_argument("--triggers", default="1.1,1.2,1.3,1.5")
    parser.add_argument("--minimum-days", type=int, default=90)
    return parser.parse_args()


def main():
    args = parse_args()
    netuids = [int(item.strip()) for item in args.netuids.split(",")]
    triggers = [Decimal(item.strip()) for item in args.triggers.split(",")]
    days = load_current_prices(args.input, netuids)
    results, summaries = run_threshold_sweep(days, triggers, args.minimum_days)
    print(f"Subnets: {', '.join(map(str, sorted(netuids)))}")
    print(f"Data: {days[0][0]} to {days[-1][0]}")
    print("Each window starts with 1 TAO in each subnet; Sunday trims sell to 1 TAO.")
    print("Entry       Trigger   Hold TAO   Trim TAO   Delta TAO   Trims   Hold DD   Trim DD")
    for trigger, runs in results.items():
        for run in runs:
            print(
                f"{run.start}  {trigger:>7.1f}  {run.hold_tao:>9.3f}  "
                f"{run.trim_tao:>9.3f}  {run.trim_tao - run.hold_tao:>+10.3f}  "
                f"{run.trim_count:>5}  {run.hold_max_drawdown:>7.1%}  "
                f"{run.trim_max_drawdown:>7.1%}"
            )
    print("Summary across overlapping entry windows:")
    for summary in summaries:
        print(
            f"{summary.trigger_tao} TAO: trim wins {summary.trim_wins}/{summary.windows}; "
            f"median delta {summary.median_delta_tao:+.3f} TAO; "
            f"lower drawdown {summary.lower_drawdown_windows}/{summary.windows}"
        )
    print("Price-only; excludes dividends, slippage and fees. Today's basket is selection-biased.")


if __name__ == "__main__":
    main()
