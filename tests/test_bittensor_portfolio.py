import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from bittensor_portfolio import balances_from_reads, fetch_tao_usd, read_balances


def balance(rao):
    return SimpleNamespace(rao=rao)


def position(netuid, rao, hotkey="5hotkey"):
    return SimpleNamespace(netuid=netuid, stake=balance(rao), hotkey=hotkey)


def test_balances_include_free_root_and_alpha_stake():
    valuation = SimpleNamespace(
        positions=[position(0, 2_000_000_000), position(51, 4_000_000_000)],
        tao_per_alpha={51: 0.25},
    )

    balances = balances_from_reads("5coldkey", balance(1_000_000_000), valuation, Decimal("100"))

    assert [(item.token_name, item.balance, item.value) for item in balances] == [
        ("tao", Decimal("1"), Decimal("100")),
        ("tao-staked", Decimal("2"), Decimal("200")),
        ("alpha-51", Decimal("4"), Decimal("100")),
    ]
    assert balances[2].tao_value == Decimal("1.00")
    assert str(balances[0]) == "tao @ bittensor: 1 TAO = 100.000000 usdc"
    assert str(balances[1]) == (
        "tao-staked @ bittensor [hotkey 5hotkey]: 2 TAO = 200.000000 usdc"
    )
    assert str(balances[2]) == (
        "alpha-51 @ bittensor [hotkey 5hotkey]: "
        "4 alpha = 1.000000000 TAO = 100.000000 usdc"
    )


def test_missing_alpha_price_fails_instead_of_undervaluing():
    valuation = SimpleNamespace(positions=[position(51, 1_000_000_000)], tao_per_alpha={})

    with pytest.raises(ValueError, match="No TAO/alpha price"):
        balances_from_reads("5coldkey", balance(0), valuation, Decimal("100"))


def test_fetch_tao_usd_validates_spot_price():
    class Session:
        def get(self, url, timeout):
            assert url.endswith("/TAO-USD/spot")
            assert timeout == 15
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": {"amount": "123.45"}})

    assert fetch_tao_usd(Session()) == Decimal("123.45")


def test_read_balances_uses_same_snapshot_for_balance_and_stake():
    calls = []

    class View:
        async def read(self, name, **kwargs):
            calls.append((name, kwargs))
            if name == "balance":
                return balance(1_000_000_000)
            return SimpleNamespace(positions=[], tao_per_alpha={})

    class Client:
        def __init__(self, network):
            assert network == "finney"

        async def connect(self):
            calls.append("connect")

        async def at(self):
            calls.append("at")
            return View()

        async def close(self):
            calls.append("close")

    balances = asyncio.run(read_balances("5coldkey", client_cls=Client, price_fetcher=lambda: Decimal("200")))

    assert balances[0].value == Decimal("200")
    assert calls[0:2] == ["connect", "at"]
    assert calls[-1] == "close"
    assert all(kwargs == {"coldkey_ss58": "5coldkey"} for _, kwargs in calls[2:-1])
