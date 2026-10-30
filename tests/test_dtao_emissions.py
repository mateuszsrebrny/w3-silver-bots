import asyncio
import csv
from datetime import date

import pytest

from dtao_history.emissions import price_days, snapshot_emissions, sync_emissions


class FakeClient:
    def __init__(self):
        self.blocks = []

    async def query_map(self, item, block):
        assert item == ("SubtensorModule", "SubnetTaoInEmission")
        self.blocks.append(block)
        return [(1, 10), (2, 5)]


def test_snapshot_matches_price_block_and_fills_zero_emission():
    rows = [
        {"date": "2026-01-01", "block": "100", "netuid": "1", "registered_at": "50"},
        {"date": "2026-01-01", "block": "100", "netuid": "3", "registered_at": "60"},
    ]
    client = FakeClient()

    result = asyncio.run(snapshot_emissions(client, rows))

    assert client.blocks == [100]
    assert [row["tao_in_emission_rao"] for row in result] == [10, 0]
    assert result[1]["registered_at"] == 60


def test_snapshot_rejects_mixed_blocks():
    rows = [{"block": "100"}, {"block": "101"}]

    with pytest.raises(ValueError, match="one block"):
        asyncio.run(snapshot_emissions(FakeClient(), rows))


def test_sync_is_resumable_and_writes_complete_day(tmp_path):
    prices = tmp_path / "prices.csv"
    prices.write_text(
        "date,block,netuid,registered_at\n"
        "2026-01-01,100,1,50\n"
        "2026-01-01,100,3,60\n"
        "2026-01-02,200,2,70\n"
    )
    assert len(price_days(prices)) == 2
    output = tmp_path / "emissions"
    client = FakeClient()

    count = asyncio.run(sync_emissions(client, prices, output, until=date(2026, 1, 1)))
    resumed = asyncio.run(sync_emissions(client, prices, output))

    assert count == resumed == 1
    assert client.blocks == [100, 200]
    with (output / "2026-01-01.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert [row["tao_in_emission_rao"] for row in rows] == ["10", "0"]
