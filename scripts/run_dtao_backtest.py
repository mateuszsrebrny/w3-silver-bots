#!/usr/bin/env python3
"""Compare holding alpha against weekly TAO-denominated profit trimming."""

import argparse
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtesting.dtao import load_current_prices, run_price_only_backtest


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netuids", required=True, help="Comma-separated subnet numbers")
    parser.add_argument("--input", type=Path, default=Path("data/dtao/daily.csv"))
    parser.add_argument("--target-tao", type=Decimal, default=Decimal("1"))
    parser.add_argument("--trim-trigger-tao", type=Decimal, default=Decimal("1.2"))
    return parser.parse_args()


def main():
    args = parse_args()
    netuids = [int(item.strip()) for item in args.netuids.split(",")]
    days = load_current_prices(args.input, netuids)
    result = run_price_only_backtest(days, args.target_tao, args.trim_trigger_tao)
    print(f"Subnets: {', '.join(map(str, sorted(netuids)))}")
    print(f"Period: {result.start} to {result.end} ({result.days} days)")
    print(f"Initial: {result.initial_tao:.6f} TAO, equal value per subnet")
    print(f"Hold: {result.hold_tao:.6f} TAO; max drawdown {result.hold_max_drawdown:.2%}")
    print(
        f"Weekly trim: {result.trim_tao:.6f} TAO; "
        f"cash {result.trim_cash_tao:.6f} TAO; {result.trim_count} trims; "
        f"max drawdown {result.trim_max_drawdown:.2%}"
    )
    print(f"Trim minus hold: {result.trim_tao - result.hold_tao:+.6f} TAO")
    print("Price-only spot valuation; excludes staking dividends, swap slippage and fees.")


if __name__ == "__main__":
    main()
