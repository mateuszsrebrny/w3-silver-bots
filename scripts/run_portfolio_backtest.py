#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtesting.multi_asset import MultiAssetSeries
from backtesting.portfolio_engine import PortfolioManagementBacktestEngine
from backtesting.portfolio_strategies import Static50_50Rebalance, Target50_50WithCashBand
from backtesting.reporting import format_results_table
from backtesting.series import PriceSeries


UTC = timezone.utc
DEFAULT_DATA_ROOT = Path("data/market/coinbase")


def parse_args():
    parser = argparse.ArgumentParser(description="Backtest BTC/ETH/DAI portfolio-management strategies.")
    parser.add_argument("--since", default="2020-01-01")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--interval-days", type=int, default=7)
    parser.add_argument("--initial-btc", default="0.5")
    parser.add_argument("--initial-eth", default="5")
    parser.add_argument("--initial-dai", default="10000")
    parser.add_argument("--withdrawal-dai", default="0")
    parser.add_argument("--withdrawal-interval-days", type=int)
    return parser.parse_args()


def parse_since(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def build_bundle(data_root):
    root = Path(data_root)
    return MultiAssetSeries(
        {
            "BTC-USD": PriceSeries.from_csv(root / "BTC-USD-1d.csv"),
            "ETH-USD": PriceSeries.from_csv(root / "ETH-USD-1d.csv"),
        }
    )


def run_backtests(args):
    bundle = build_bundle(args.data_root)
    engine = PortfolioManagementBacktestEngine(
        interval_days=args.interval_days,
        withdrawal_amount_dai=args.withdrawal_dai,
        withdrawal_interval_days=args.withdrawal_interval_days,
    )
    since = parse_since(args.since)
    strategies = [
        Static50_50Rebalance(),
        Target50_50WithCashBand(),
    ]
    return [
        engine.run(
            bundle,
            strategy,
            since,
            initial_btc=args.initial_btc,
            initial_eth=args.initial_eth,
            initial_dai=args.initial_dai,
        )
        for strategy in strategies
    ]


def main():
    args = parse_args()
    results = run_backtests(args)
    print(format_results_table(results))


if __name__ == "__main__":
    main()
