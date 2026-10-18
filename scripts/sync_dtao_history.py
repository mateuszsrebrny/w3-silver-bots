#!/usr/bin/env python3
"""Store daily, block-pinned dTAO reserve snapshots from an archive node."""

import argparse
import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dtao_history.sync import sync_days


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    today = datetime.now(timezone.utc).date()
    parser.add_argument("--since", type=date.fromisoformat, default=today)
    parser.add_argument("--until", type=date.fromisoformat, default=today)
    parser.add_argument("--output", type=Path, default=Path("data/dtao/daily.csv"))
    parser.add_argument("--network", default="archive", help="Bittensor archive network or wss endpoint")
    parser.add_argument("--resume", action="store_true", help="Skip days already present in the output CSV")
    return parser.parse_args(argv)


async def run(args):
    try:
        from bittensor import Client
    except ImportError as exc:
        raise SystemExit("Install project requirements in .venv; see README.") from exc
    client = Client(network=args.network, fallback_endpoints=[], archive_endpoints=[])
    await client.connect()
    try:
        await sync_days(client, args.since, args.until, args.output, resume=args.resume)
    finally:
        await client.close()


def main():
    args = parse_args()
    if args.until < args.since:
        raise SystemExit("--until must be on or after --since")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
