#!/usr/bin/env python3
"""Compare fixed emission-ranked baskets with pure and trimmed rotation."""

import argparse
from decimal import Decimal
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtesting.dtao import run_price_only_backtest
from backtesting.dtao_rebalance import run_rebalance_backtest
from backtesting.dtao_top11 import load_emissions, load_prices, make_cohorts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, default=Path("data/dtao/daily.csv"))
    parser.add_argument("--emissions", type=Path, default=Path("data/dtao/emissions"))
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--basket-size", type=int, default=11)
    parser.add_argument("--compare-size", type=int,
                        help="Compare pure swap with another basket size on the same dates")
    parser.add_argument("--total-tao", type=Decimal, default=Decimal("11"))
    parser.add_argument("--trigger", type=Decimal, default=Decimal("1.2"),
                        help="Trim multiple of the equal initial position size")
    parser.add_argument("--cadence", choices=("monthly", "daily"), default="monthly")
    parser.add_argument("--cost-bps", type=Decimal, default=Decimal("0"),
                        help="Illustrative per-side swap cost for rotation variants")
    args = parser.parse_args()
    if args.basket_size < 1 or args.total_tao <= 0 or (args.compare_size is not None and args.compare_size < 1):
        parser.error("--basket-size and --total-tao must be positive")
    target_tao = args.total_tao / args.basket_size
    trigger_tao = target_tao * args.trigger
    prices = load_prices(args.prices)
    emissions = load_emissions(args.emissions)
    cohorts, skipped = make_cohorts(
        prices, emissions, basket_size=args.basket_size, window_days=args.window_days
    )
    if not cohorts:
        raise ValueError("No complete monthly cohorts")
    rows = []
    monthly_pure = []
    print(f"Top {args.basket_size}; initial {args.total_tao} TAO; {target_tao} TAO per subnet")
    print(f"Rotation cadence: {args.cadence}; rank signal: previous day's snapshot")
    print(f"Swap cost per side: {args.cost_bps} bps (hold and fixed trim remain cost-free)")
    print("Entry       Hold     Trim     Swap only  Swap+trim  Swap+topup  Exits  Turnover")
    for cohort in cohorts:
        fixed = run_price_only_backtest(
            cohort.days, target_tao=target_tao, trim_trigger_tao=trigger_tao
        )
        pure = run_rebalance_backtest(
            cohort, prices, emissions, trigger_tao=None, rotation_cadence=args.cadence,
            cost_bps=args.cost_bps, target_tao=target_tao,
        )
        if args.cadence == "daily":
            monthly_pure.append(run_rebalance_backtest(
                cohort, prices, emissions, trigger_tao=None,
                rotation_cadence="monthly", cost_bps=args.cost_bps,
                target_tao=target_tao,
            ))
        rotate = run_rebalance_backtest(
            cohort, prices, emissions, trigger_tao=trigger_tao, rotation_cadence=args.cadence,
            cost_bps=args.cost_bps, target_tao=target_tao,
        )
        topup = run_rebalance_backtest(
            cohort, prices, emissions, trigger_tao=trigger_tao, topup=True,
            rotation_cadence=args.cadence, cost_bps=args.cost_bps,
            target_tao=target_tao,
        )
        rows.append((fixed.hold_tao, fixed.trim_tao, pure.end_tao, rotate.end_tao, topup.end_tao, pure, rotate, topup))
        print(
            f"{fixed.start}  {fixed.hold_tao:>7.3f}  {fixed.trim_tao:>7.3f}  "
            f"{pure.end_tao:>9.3f}  {rotate.end_tao:>9.3f}  "
            f"{topup.end_tao:>10.3f}  {pure.rotations:>5}  "
            f"{pure.turnover_tao:>8.3f}"
        )
    print(f"Windows: {len(rows)}; skipped entries: {len(skipped)}; initial: {args.total_tao} TAO")
    print("Median final TAO: " + ", ".join(
        f"{name} {median(row[i] for row in rows):.3f}"
        for i, name in enumerate(("hold", "trim", "swap only", "swap+trim", "swap+topup"))
    ))
    for index, name in ((2, "swap only"), (3, "swap+trim"), (4, "swap+topup")):
        print(
            f"{name} beats hold: {sum(row[index] > row[0] for row in rows)}/{len(rows)}; "
            f"beats fixed trim: {sum(row[index] > row[1] for row in rows)}/{len(rows)}; "
            f"median delta vs hold {median(row[index] - row[0] for row in rows):+.3f} TAO"
        )
    print(f"Incomplete positive-emission signals skipped: {sum(row[5].skipped_signals for row in rows)}")
    if monthly_pure:
        paired = [row[2] - monthly.end_tao for row, monthly in zip(rows, monthly_pure)]
        print(
            f"Daily pure swap vs monthly pure swap: wins {sum(delta > 0 for delta in paired)}/{len(paired)}; "
            f"median paired delta {median(paired):+.3f} TAO; "
            f"median exits {median(row[5].rotations for row in rows):.1f} vs "
            f"{median(run.rotations for run in monthly_pure):.1f}"
        )
    if args.compare_size is not None:
        comparison_cohorts, _ = make_cohorts(
            prices, emissions, basket_size=args.compare_size,
            window_days=args.window_days,
        )
        comparison_by_start = {
            cohort.days[0][0]: cohort for cohort in comparison_cohorts
        }
        paired = []
        for cohort, row in zip(cohorts, rows):
            other = comparison_by_start.get(cohort.days[0][0])
            if other is None:
                continue
            comparison = run_rebalance_backtest(
                other, prices, emissions, trigger_tao=None,
                rotation_cadence=args.cadence, cost_bps=args.cost_bps,
                target_tao=args.total_tao / args.compare_size,
            )
            paired.append((row[5], comparison))
        if not paired:
            raise ValueError("No shared entry dates for basket comparison")
        deltas = [left.end_tao - right.end_tao for left, right in paired]
        print(
            f"Pure swap top {args.basket_size} vs top {args.compare_size}: "
            f"wins {sum(delta > 0 for delta in deltas)}/{len(deltas)}; "
            f"median paired delta {median(deltas):+.3f} TAO"
        )
        print(
            f"Median exits: {median(left.rotations for left, _ in paired):.1f} vs "
            f"{median(right.rotations for _, right in paired):.1f}; "
            f"median max drawdown: {median(left.max_drawdown for left, _ in paired):.1%} "
            f"vs {median(right.max_drawdown for _, right in paired):.1%}"
        )
    print("No new capital or rewards. Cost bps is a constant illustrative drag, not an execution quote. Monthly entry windows overlap.")


if __name__ == "__main__":
    main()
