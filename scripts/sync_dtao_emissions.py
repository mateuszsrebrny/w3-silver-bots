#!/usr/bin/env python3
"""Backfill historical TAO-in-emission ranking from the Bittensor archive node."""

import argparse
import asyncio
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dtao_history.emissions import sync_emissions


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, default=Path("data/dtao/daily.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/dtao/emissions"))
    parser.add_argument("--network", default="wss://archive.sub.latent.to:443")
    parser.add_argument("--since", type=date.fromisoformat)
    parser.add_argument("--until", type=date.fromisoformat)
    parser.add_argument("--refresh", action="store_true", help="Re-fetch days already stored")
    parser.add_argument("--signal-only", action="store_true", help="Fetch only days needed for monthly top-11 entry signals")
    return parser.parse_args()


async def run(args):
    from bittensor import Client

    client = Client(network=args.network, fallback_endpoints=[], archive_endpoints=[])
    await client.connect()
    try:
        count = await sync_emissions(
            client, args.prices, args.output_dir, args.since, args.until, args.refresh,
            args.signal_only,
        )
    finally:
        await client.close()
    print(f"Synced {count} emission days")


def main():
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
