"""Read-only Bittensor portfolio valuation for a public coldkey."""

import asyncio
from dataclasses import dataclass
from decimal import Decimal

import requests


RAO_PER_TAO = Decimal("1000000000")
TAO_SPOT_URL = "https://api.coinbase.com/v2/prices/TAO-USD/spot"


@dataclass(frozen=True)
class BittensorBalance:
    token_name: str
    balance: Decimal
    value: Decimal
    wallet: str
    value_token: str = "usdc"
    tao_value: Decimal | None = None
    hotkey: str | None = None

    @property
    def chain(self):
        return "bittensor"

    def __str__(self):
        hotkey = f" [hotkey {self.hotkey}]" if self.hotkey else ""
        amount = f"{self.balance:f} TAO"
        if self.tao_value is not None and self.token_name.startswith("alpha-"):
            amount = f"{self.balance:f} alpha = {self.tao_value:.9f} TAO"
        return (
            f"{self.token_name} @ bittensor{hotkey}: "
            f"{amount} = {self.value:.6f} {self.value_token}"
        )


def fetch_tao_usd(session=requests):
    response = session.get(TAO_SPOT_URL, timeout=15)
    response.raise_for_status()
    price = Decimal(response.json()["data"]["amount"])
    if not price.is_finite() or price <= 0:
        raise ValueError("Invalid TAO/USD spot price")
    return price


def balances_from_reads(coldkey, free, valuation, tao_usd):
    price = Decimal(str(tao_usd))
    balances = []
    free_tao = Decimal(free.rao) / RAO_PER_TAO
    balances.append(BittensorBalance("tao", free_tao, free_tao * price, coldkey))

    for position in valuation.positions:
        if position.stake.rao == 0:
            continue
        netuid = position.netuid
        amount = Decimal(position.stake.rao) / RAO_PER_TAO
        if netuid == 0:
            tao_value = amount
            token_name = "tao-staked"
        else:
            if netuid not in valuation.tao_per_alpha:
                raise ValueError(f"No TAO/alpha price for subnet {netuid}; cannot value portfolio")
            tao_value = amount * Decimal(str(valuation.tao_per_alpha[netuid]))
            token_name = f"alpha-{netuid}"
        balances.append(
            BittensorBalance(
                token_name, amount, tao_value * price, coldkey,
                tao_value=tao_value, hotkey=position.hotkey,
            )
        )
    return balances


async def read_balances(coldkey, network="finney", client_cls=None, price_fetcher=fetch_tao_usd):
    if client_cls is None:
        from bittensor import Client

        client_cls = Client
    client = client_cls(network=network)
    await client.connect()
    try:
        view = await client.at()
        free, valuation = await asyncio.gather(
            view.read("balance", coldkey_ss58=coldkey),
            view.read("stake_value_for_coldkey", coldkey_ss58=coldkey),
        )
    finally:
        await client.close()
    if not free.rao and not any(p.stake.rao for p in valuation.positions):
        return balances_from_reads(coldkey, free, valuation, Decimal("1"))
    return balances_from_reads(coldkey, free, valuation, price_fetcher())
