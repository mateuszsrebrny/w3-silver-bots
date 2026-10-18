import asyncio
import csv
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import os
import tempfile


UTC = timezone.utc
FIELDS = (
    "date", "block", "timestamp_utc", "netuid", "registered_at",
    "tao_in_rao", "alpha_in_rao", "price_tao_per_alpha",
)
MODULE = "SubtensorModule"


async def snapshot_block(client, day, head, lower=0, hint=None):
    target = datetime.combine(day, time(0, 30), tzinfo=UTC)
    if await client.timestamp(head) < target:
        raise ValueError(f"No finalized block at or after {target.isoformat()}")
    if hint is not None and lower < hint <= head:
        hinted_time = await client.timestamp(hint)
        if hinted_time >= target:
            if await client.timestamp(hint - 1) < target:
                return hint
            candidate = max(lower, hint - 256)
            if await client.timestamp(candidate) < target:
                lower = candidate + 1
            head = hint
        else:
            candidate = min(head, hint + 256)
            if await client.timestamp(candidate) >= target:
                head = candidate
            lower = hint + 1
    # First block at or after 00:30 UTC, rather than assuming a fixed block time.
    while lower < head:
        middle = (lower + head) // 2
        if await client.timestamp(middle) < target:
            lower = middle + 1
        else:
            head = middle
    return lower


async def snapshot_rows(client, day, block):
    added = await client.query_map((MODULE, "NetworksAdded"), block=block)
    netuids = sorted(int(netuid) for netuid, active in added if active and int(netuid) != 0)
    if not netuids:
        return []
    keys = [[netuid] for netuid in netuids]
    registrations, tao_reserves, alpha_reserves = await asyncio.gather(
        *(client.query_batch((MODULE, item), keys, block=block) for item in (
            "NetworkRegisteredAt", "SubnetTAO", "SubnetAlphaIn"
        ))
    )
    timestamp = (await client.timestamp(block)).isoformat()
    rows = []
    for netuid, registered, tao, alpha in zip(
        netuids, registrations, tao_reserves, alpha_reserves, strict=True
    ):
        tao, alpha = int(tao), int(alpha)
        rows.append({
            "date": day.isoformat(),
            "block": block,
            "timestamp_utc": timestamp,
            "netuid": netuid,
            "registered_at": int(registered),
            "tao_in_rao": tao,
            "alpha_in_rao": alpha,
            "price_tao_per_alpha": str(Decimal(tao) / Decimal(alpha)) if alpha else "",
        })
    return rows


def read_rows(path):
    if not path.exists():
        return []
    with path.open(newline="") as source:
        return list(csv.DictReader(source))


def replace_day(path, day, rows):
    path = Path(path)
    existing = [row for row in read_rows(path) if row["date"] != day.isoformat()]
    combined = sorted(existing + rows, key=lambda row: (row["date"], int(row["netuid"])))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".dtao-", suffix=".csv", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(combined)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def sync_days(client, since, until, path, resume=False):
    if until < since:
        raise ValueError("--until must be on or after --since")
    head = await client.finalized_block()
    daily_blocks = round(86400 / await client.block_time())
    saved_days = {row["date"] for row in read_rows(Path(path))} if resume else set()
    lower = 0
    previous_interval = daily_blocks
    day = since
    while day <= until:
        if day.isoformat() in saved_days:
            day += timedelta(days=1)
            continue
        hint = lower + previous_interval if lower else None
        block = await snapshot_block(client, day, head, lower, hint)
        rows = await snapshot_rows(client, day, block)
        replace_day(path, day, rows)
        print(f"{day}: block {block}, {len(rows)} subnets")
        if lower:
            previous_interval = block - lower
        lower = block
        day += timedelta(days=1)
