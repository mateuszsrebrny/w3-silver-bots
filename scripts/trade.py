#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv
import json
import os
from pathlib import Path
import sys
import time

import requests
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from botweb3lib import BlockchainAccess


CLIENT_ID = "w3-silver-bots"
KYBER_BASE_URL = "https://aggregator-api.kyberswap.com"
DEFAULT_CHAIN = "arbitrum"
DEFAULT_FROM_TOKEN = "dai"
DEFAULT_SLIPPAGE_BPS = 50
DEFAULT_DEADLINE_SECONDS = 20 * 60
DEFAULT_APPROVAL_GAS_LIMIT = 65000
DEFAULT_SWAP_GAS_LIMIT = 900000


@dataclass(frozen=True)
class SwapRoute:
    router_address: str
    route_summary: dict


@dataclass(frozen=True)
class EncodedSwap:
    router_address: str
    calldata: str
    value_wei: int


@dataclass(frozen=True)
class GasAssessment:
    gas_price_wei: int
    gas_limit: int
    gas_cost_eth: Decimal
    gas_cost_usd: Decimal | None


def parse_args():
    parser = argparse.ArgumentParser(description="Execute a DAI-funded Arbitrum swap with a local wallet.")
    parser.add_argument("--chain", default=DEFAULT_CHAIN, choices=["arbitrum"])
    parser.add_argument("--from-token", default=DEFAULT_FROM_TOKEN, choices=["dai"])
    parser.add_argument("--to-token", required=True, choices=["eth", "wbtc"])
    parser.add_argument("--amount", required=True, help="Input token amount in human units, e.g. 100")
    parser.add_argument("--slippage-bps", type=int, default=DEFAULT_SLIPPAGE_BPS)
    parser.add_argument("--deadline-seconds", type=int, default=DEFAULT_DEADLINE_SECONDS)
    parser.add_argument("--execute", action="store_true", help="Actually send transactions. Default is preview only.")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation when --execute is set.")
    parser.add_argument("--allowance-buffer-bps", type=int, default=0, help="Optional approval buffer above the input amount.")
    parser.add_argument("--config", default="chains.config.yaml")
    return parser.parse_args()


def quantize_amount(value, places="0.000000"):
    return Decimal(value).quantize(Decimal(places), rounding=ROUND_DOWN)


def load_private_key():
    private_key = os.getenv("BOT_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError("BOT_PRIVATE_KEY is not set in the environment")
    return private_key


def wallet_from_private_key(private_key):
    return Web3().eth.account.from_key(private_key).address


def to_token_wei(blockchain_access, token, amount):
    return BlockchainAccess.my_toWei(amount, blockchain_access.get_decimals(token))


def from_token_wei(blockchain_access, token, amount_wei):
    return BlockchainAccess.my_fromWei(amount_wei, blockchain_access.get_decimals(token))


def kyber_headers():
    return {"x-client-id": CLIENT_ID}


def fetch_route(blockchain_access, from_token, to_token, amount, wallet):
    amount_wei = to_token_wei(blockchain_access, from_token, amount)
    params = {
        "tokenIn": blockchain_access.get_token_contract_address(from_token),
        "tokenOut": blockchain_access.get_token_contract_address(to_token),
        "amountIn": str(amount_wei),
        "origin": wallet,
    }
    response = requests.get(
        f"{KYBER_BASE_URL}/{blockchain_access.get_kyberswap_chain_name()}/api/v1/routes",
        params=params,
        headers=kyber_headers(),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload["data"]
    return SwapRoute(router_address=data["routerAddress"], route_summary=data["routeSummary"])


def build_encoded_swap(blockchain_access, route, wallet, slippage_bps, deadline_seconds):
    body = {
        "routeSummary": route.route_summary,
        "sender": wallet,
        "recipient": wallet,
        "slippageTolerance": slippage_bps,
        "deadline": int(time.time()) + deadline_seconds,
        "enableGasEstimation": False,
    }
    response = requests.post(
        f"{KYBER_BASE_URL}/{blockchain_access.get_kyberswap_chain_name()}/api/v1/route/build",
        headers={**kyber_headers(), "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload["data"]
    calldata = data.get("data")
    if not calldata:
        raise ValueError("Kyber route/build response did not include calldata")
    value_wei = int(data.get("value", "0"))
    return EncodedSwap(router_address=route.router_address, calldata=calldata, value_wei=value_wei)


def build_approval_tx(blockchain_access, token, owner, spender, amount_wei):
    contract = blockchain_access.get_token_contract(token)
    w3 = blockchain_access.get_w3()
    tx = contract.functions.approve(spender, amount_wei).build_transaction(
        {
            "from": owner,
            "nonce": w3.eth.get_transaction_count(owner),
            "chainId": blockchain_access.get_chain_id(),
            "gasPrice": w3.eth.gas_price,
            "gas": DEFAULT_APPROVAL_GAS_LIMIT,
        }
    )
    tx["gas"] = _safe_estimate_gas(w3, tx, DEFAULT_APPROVAL_GAS_LIMIT)
    return tx


def build_swap_tx(blockchain_access, sender, encoded_swap):
    w3 = blockchain_access.get_w3()
    tx = {
        "from": sender,
        "to": Web3.to_checksum_address(encoded_swap.router_address),
        "data": encoded_swap.calldata,
        "value": encoded_swap.value_wei,
        "nonce": w3.eth.get_transaction_count(sender),
        "chainId": blockchain_access.get_chain_id(),
        "gasPrice": w3.eth.gas_price,
        "gas": DEFAULT_SWAP_GAS_LIMIT,
    }
    tx["gas"] = _safe_estimate_gas(w3, tx, DEFAULT_SWAP_GAS_LIMIT)
    return tx


def _safe_estimate_gas(w3, tx, fallback_gas_limit):
    try:
        return w3.eth.estimate_gas(tx)
    except Exception:
        return fallback_gas_limit


def assess_gas_cost(blockchain_access, gas_limit, eth_usd_price=None):
    w3 = blockchain_access.get_w3()
    gas_price_wei = int(w3.eth.gas_price)
    gas_cost_eth = Decimal(gas_price_wei * gas_limit) / Decimal(10**18)
    gas_cost_usd = None
    if eth_usd_price is not None:
        gas_cost_usd = gas_cost_eth * Decimal(str(eth_usd_price))
    return GasAssessment(
        gas_price_wei=gas_price_wei,
        gas_limit=gas_limit,
        gas_cost_eth=gas_cost_eth,
        gas_cost_usd=gas_cost_usd,
    )


def sign_and_send(blockchain_access, tx, private_key):
    signed = blockchain_access.get_w3().eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = blockchain_access.get_w3().eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


def maybe_confirm(args):
    if args.yes:
        return
    answer = input("Send transactions? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Cancelled")


def print_preview(args, wallet, route, encoded_swap, input_amount, expected_amount_out, approval_needed, approval_amount, approval_gas, swap_gas):
    print(f"Wallet: {wallet}")
    print(f"Chain: {args.chain}")
    print(f"Swap: {input_amount} {args.from_token} -> {args.to_token}")
    print(f"Router: {route.router_address}")
    print(f"Expected output: {quantize_amount(expected_amount_out)} {args.to_token}")
    print(f"Route gas estimate (router units): {route.route_summary.get('gas')}")
    print(f"Approval needed: {approval_needed}")
    if approval_needed:
        print(f"Approval amount: {approval_amount} {args.from_token}")
        print(f"Approval gas: {approval_gas.gas_limit} @ {approval_gas.gas_price_wei} wei")
        print(f"Approval gas cost: {approval_gas.gas_cost_eth} ETH")
    print(f"Swap tx value: {encoded_swap.value_wei} wei")
    print(f"Swap gas: {swap_gas.gas_limit} @ {swap_gas.gas_price_wei} wei")
    print(f"Swap gas cost: {swap_gas.gas_cost_eth} ETH")
    if swap_gas.gas_cost_usd is not None:
        print(f"Swap gas cost (usd est): {quantize_amount(swap_gas.gas_cost_usd, '0.01')}")


def main():
    load_dotenv()
    args = parse_args()

    BlockchainAccess.load_config(args.config)
    blockchain_access = BlockchainAccess(chain=args.chain, dry_run=not args.execute)
    private_key = load_private_key()
    wallet = wallet_from_private_key(private_key)

    input_amount = Decimal(str(args.amount))
    route = fetch_route(blockchain_access, args.from_token, args.to_token, input_amount, wallet)
    encoded_swap = build_encoded_swap(
        blockchain_access,
        route,
        wallet,
        args.slippage_bps,
        args.deadline_seconds,
    )

    amount_out_wei = int(route.route_summary["amountOut"])
    expected_amount_out = from_token_wei(blockchain_access, args.to_token, amount_out_wei)
    eth_usd_price = blockchain_access.check_kyberswap_price(["eth", "usdc"], Decimal("1"))

    input_amount_wei = to_token_wei(blockchain_access, args.from_token, input_amount)
    approval_amount_wei = input_amount_wei * (10_000 + args.allowance_buffer_bps) // 10_000
    allowance = blockchain_access.check_allowance(args.from_token, wallet, route.router_address)
    approval_needed = allowance < input_amount

    approval_tx = None
    approval_gas = None
    if approval_needed:
        approval_tx = build_approval_tx(
            blockchain_access,
            args.from_token,
            wallet,
            route.router_address,
            approval_amount_wei,
        )
        approval_gas = assess_gas_cost(blockchain_access, approval_tx["gas"], eth_usd_price=eth_usd_price)

    swap_tx = build_swap_tx(blockchain_access, wallet, encoded_swap)
    swap_gas = assess_gas_cost(blockchain_access, swap_tx["gas"], eth_usd_price=eth_usd_price)

    print_preview(
        args=args,
        wallet=wallet,
        route=route,
        encoded_swap=encoded_swap,
        input_amount=input_amount,
        expected_amount_out=expected_amount_out,
        approval_needed=approval_needed,
        approval_amount=from_token_wei(blockchain_access, args.from_token, approval_amount_wei),
        approval_gas=approval_gas,
        swap_gas=swap_gas,
    )

    if not args.execute:
        print("Preview only. Use --execute to actually send the trade.")
        return

    maybe_confirm(args)

    if approval_tx is not None:
        approval_hash = sign_and_send(blockchain_access, approval_tx, private_key)
        print(f"Approval tx sent: {approval_hash}")

    swap_hash = sign_and_send(blockchain_access, swap_tx, private_key)
    print(f"Swap tx sent: {swap_hash}")


if __name__ == "__main__":
    main()
