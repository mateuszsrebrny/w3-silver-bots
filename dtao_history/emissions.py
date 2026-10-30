"""Resumable, block-pinned subnet TAO-in-emission snapshots."""

import csv
import os
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import tempfile


FIELDS = ("date", "block", "netuid", "registered_at", "tao_in_emission_rao")


def price_days(path):
    by_day = defaultdict(list)
    with Path(path).open(newline="") as source:
        for row in csv.DictReader(source):
            by_day[date.fromisoformat(row["date"])].append(row)
    return dict(sorted(by_day.items()))


async def snapshot_emissions(client, price_rows):
    blocks = {int(row["block"]) for row in price_rows}
    if len(blocks) != 1:
        raise ValueError("Price rows for a day must use one block")
    block = blocks.pop()
    emission_map = {
        int(netuid): int(rao)
        for netuid, rao in await client.query_map(
            ("SubtensorModule", "SubnetTaoInEmission"), block=block
        )
    }
    return [
        {
            "date": row["date"],
            "block": block,
            "netuid": int(row["netuid"]),
            "registered_at": int(row["registered_at"]),
            "tao_in_emission_rao": emission_map.get(int(row["netuid"]), 0),
        }
        for row in price_rows
    ]


def write_day(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".emissions-", suffix=".csv", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def sync_emissions(client, price_path, output_dir, since=None, until=None, refresh=False, signal_only=False):
    synced = 0
    for day, rows in price_days(price_path).items():
        if (since and day < since) or (until and day > until):
            continue
        entry_day = day + timedelta(days=1)
        if signal_only and not (entry_day.weekday() == 6 and entry_day.day <= 7):
            continue
        path = Path(output_dir) / f"{day.isoformat()}.csv"
        if path.exists() and not refresh:
            continue
        write_day(path, await snapshot_emissions(client, rows))
        synced += 1
        if synced % 20 == 0:
            print(f"Synced {synced} emission days through {day}", flush=True)
    return synced
