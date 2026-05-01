#!/usr/bin/env python3

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_data.candles import UTC
from market_data.providers import CoinbaseCandleProvider
from market_data.store import CandleStore
from market_data.sync import MarketDataSyncService


DEFAULT_PRODUCTS = ["BTC-USD", "ETH-USD"]
DEFAULT_GRANULARITY = "1d"
DEFAULT_START = datetime(2020, 1, 1, tzinfo=UTC)
DEFAULT_DATA_ROOT = Path("data/market/coinbase")


def parse_args():
    parser = argparse.ArgumentParser(description="Sync historical market candles.")
    parser.add_argument(
        "--product",
        action="append",
        dest="products",
        help="Coinbase product id, e.g. BTC-USD",
    )
    parser.add_argument(
        "--granularity",
        default=DEFAULT_GRANULARITY,
        choices=["1d"],
        help="Stored candle granularity.",
    )
    parser.add_argument(
        "--since",
        default=DEFAULT_START.date().isoformat(),
        help="Seed start date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--mode",
        default="sync",
        choices=["seed", "update", "repair", "sync"],
        help="How to mutate the local store.",
    )
    parser.add_argument(
        "--data-root",
        default=str(DEFAULT_DATA_ROOT),
        help="Directory where market CSV files are stored.",
    )
    return parser.parse_args()


def parse_start_date(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def latest_completed_daily_candle_open(now=None):
    now = now or datetime.now(tz=UTC)
    today_open = datetime(now.year, now.month, now.day, tzinfo=UTC)
    return today_open


def build_store_path(data_root, product_id, granularity):
    return Path(data_root) / f"{product_id}-{granularity}.csv"


def run_sync(products, granularity, since, mode, data_root):
    provider = CoinbaseCandleProvider()
    end = latest_completed_daily_candle_open()

    for product_id in products:
        store = CandleStore(build_store_path(data_root, product_id, granularity))
        service = MarketDataSyncService(provider, store)
        if mode == "seed":
            service.seed_history(product_id, granularity, since, end)
        elif mode == "update":
            service.update_history(product_id, granularity, end)
        elif mode == "repair":
            service.repair_gaps(product_id, granularity, end)
        else:
            service.sync(product_id, granularity, since, end)


def main():
    args = parse_args()
    products = args.products or DEFAULT_PRODUCTS
    run_sync(
        products=products,
        granularity=args.granularity,
        since=parse_start_date(args.since),
        mode=args.mode,
        data_root=args.data_root,
    )


if __name__ == "__main__":
    main()
