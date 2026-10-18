import asyncio
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dtao_history.sync import snapshot_block, snapshot_rows, sync_days
from scripts.sync_dtao_history import parse_args


UTC = timezone.utc


class FakeClient:
    def __init__(self):
        self.start = datetime(2026, 10, 1, tzinfo=UTC)

    async def timestamp(self, block):
        return self.start + timedelta(minutes=block)

    async def finalized_block(self):
        return 3000

    async def block_time(self):
        return 60

    async def query_map(self, item, *, block):
        assert item == ("SubtensorModule", "NetworksAdded")
        return [(0, True), (116, True), (120, False)]

    async def query_batch(self, item, keys, *, block):
        assert keys == [[116]]
        return {
            "NetworkRegisteredAt": [8294730 if block < 1440 else 9210632],
            "SubnetTAO": [2000000000],
            "SubnetAlphaIn": [4000000000],
        }[item[1]]


def test_snapshot_block_finds_first_block_after_utc_0030():
    client = FakeClient()
    assert asyncio.run(snapshot_block(client, date(2026, 10, 2), 3000)) == 1470
    assert asyncio.run(snapshot_block(client, date(2026, 10, 2), 3000, 30, 1470)) == 1470
    assert asyncio.run(snapshot_block(client, date(2026, 10, 2), 3000, 30, 1460)) == 1470
    assert asyncio.run(snapshot_block(client, date(2026, 10, 2), 3000, 30, 1480)) == 1470
    with pytest.raises(ValueError, match="No finalized block"):
        asyncio.run(snapshot_block(client, date(2026, 10, 4), 3000))


def test_snapshot_rows_keeps_registration_identity_and_price():
    client = FakeClient()
    old = asyncio.run(snapshot_rows(client, date(2026, 10, 1), 30))
    new = asyncio.run(snapshot_rows(client, date(2026, 10, 2), 1470))
    assert [row["registered_at"] for row in old + new] == [8294730, 9210632]
    assert Decimal(new[0]["price_tao_per_alpha"]) == Decimal("0.5")
    assert new[0]["netuid"] == 116


def test_sync_replaces_existing_day_without_duplicate(tmp_path):
    path = tmp_path / "daily.csv"
    day = date(2026, 10, 1)
    client = FakeClient()
    asyncio.run(sync_days(client, day, day + timedelta(days=1), path))
    asyncio.run(sync_days(client, day, day, path))
    with path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 2
    assert [row["date"] for row in rows] == ["2026-10-01", "2026-10-02"]
    assert [int(row["registered_at"]) for row in rows] == [8294730, 9210632]


def test_sync_resume_skips_saved_days(tmp_path):
    path = tmp_path / "daily.csv"
    day = date(2026, 10, 1)
    client = FakeClient()
    asyncio.run(sync_days(client, day, day, path))

    async def no_queries(item, *, block):
        raise AssertionError("already saved day should not be fetched again")

    client.query_map = no_queries
    asyncio.run(sync_days(client, day, day, path, resume=True))
    with path.open(newline="") as source:
        assert len(list(csv.DictReader(source))) == 1


def test_empty_reserve_does_not_divide_by_zero():
    client = FakeClient()

    async def empty_reserve(item, keys, *, block):
        if item[1] == "SubnetAlphaIn":
            return [0]
        return await FakeClient.query_batch(client, item, keys, block=block)

    client.query_batch = empty_reserve
    rows = asyncio.run(snapshot_rows(client, date(2026, 10, 1), 30))
    assert rows[0]["price_tao_per_alpha"] == ""


def test_cli_parses_date_range():
    args = parse_args(["--since", "2025-02-13", "--until", "2025-02-14"])
    assert args.since == date(2025, 2, 13)
    assert args.until == date(2025, 2, 14)
