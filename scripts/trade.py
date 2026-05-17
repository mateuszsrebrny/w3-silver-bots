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
ROUTE_GAS_LIMIT_MULTIPLIER = 4
DEFAULT_RECEIPT_TIMEOUT_SECONDS = 180
DEFAULT_RECEIPT_DIR = "reports/trades"


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


@dataclass(frozen=True)
class QuoteValuation:
    input_value_usd: Decimal | None
    output_value_usd: Decimal | None
    quote_discount_bps: Decimal | None


def parse_args():
    parser = argparse.ArgumentParser(description="Execute an Arbitrum swap with a local wallet.")
    parser.add_argument("--chain", default=DEFAULT_CHAIN, choices=["arbitrum"])
    parser.add_argument("--from-token", default=DEFAULT_FROM_TOKEN, choices=["dai", "weth", "wbtc", "wsteth"])
    parser.add_argument("--to-token", required=True, choices=["dai", "eth", "weth", "wbtc", "wsteth"])
    parser.add_argument("--amount", required=True, help="Input token amount in human units, e.g. 100")
    parser.add_argument("--slippage-bps", type=int, default=DEFAULT_SLIPPAGE_BPS)
    parser.add_argument("--deadline-seconds", type=int, default=DEFAULT_DEADLINE_SECONDS)
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview only. This is already the default unless --execute is set.",
    )
    parser.add_argument("--execute", action="store_true", help="Actually send transactions. Default is preview only.")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation when --execute is set.")
    parser.add_argument("--allowance-buffer-bps", type=int, default=0, help="Optional approval buffer above the input amount.")
    parser.add_argument(
        "--receipt-timeout-seconds",
        type=int,
        default=DEFAULT_RECEIPT_TIMEOUT_SECONDS,
        help="How long to wait for a mined approval receipt before sending the swap.",
    )
    parser.add_argument(
        "--receipt-dir",
        default=DEFAULT_RECEIPT_DIR,
        help="Directory for saved JSON receipts",
    )
    parser.add_argument("--config", default="chains.config.yaml")
    return parser.parse_args()


def quantize_amount(value, places="0.000000"):
    return Decimal(value).quantize(Decimal(places), rounding=ROUND_DOWN)


def format_bps_percent(bps):
    return (Decimal(str(bps)) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


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
    fee_params = BlockchainAccess.build_fee_params(w3)
    tx = contract.functions.approve(spender, amount_wei).build_transaction(
        {
            "from": owner,
            "nonce": w3.eth.get_transaction_count(owner),
            "chainId": blockchain_access.get_chain_id(),
            "gas": DEFAULT_APPROVAL_GAS_LIMIT,
            **fee_params,
        }
    )
    tx["gas"] = _safe_estimate_gas(w3, tx, DEFAULT_APPROVAL_GAS_LIMIT)
    return tx


def build_swap_tx(blockchain_access, sender, encoded_swap):
    w3 = blockchain_access.get_w3()
    fee_params = BlockchainAccess.build_fee_params(w3)
    tx = {
        "from": sender,
        "to": Web3.to_checksum_address(encoded_swap.router_address),
        "data": encoded_swap.calldata,
        "value": encoded_swap.value_wei,
        "nonce": w3.eth.get_transaction_count(sender),
        "chainId": blockchain_access.get_chain_id(),
        "gas": DEFAULT_SWAP_GAS_LIMIT,
        **fee_params,
    }
    tx["gas"] = _safe_estimate_gas(w3, tx, DEFAULT_SWAP_GAS_LIMIT)
    return tx


def apply_route_gas_floor(tx, route):
    route_gas = route.route_summary.get("gas")
    if route_gas is None:
        return tx

    route_gas_limit = int(route_gas)
    tx["gas"] = max(int(tx["gas"]), route_gas_limit * ROUTE_GAS_LIMIT_MULTIPLIER)
    return tx


def _safe_estimate_gas(w3, tx, fallback_gas_limit):
    return BlockchainAccess.estimate_gas(w3, tx, fallback_gas_limit)


def assess_gas_cost(blockchain_access, gas_limit, eth_usd_price=None):
    w3 = blockchain_access.get_w3()
    gas_price_wei = BlockchainAccess.fee_cap_wei(BlockchainAccess.build_fee_params(w3))
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


def wait_for_receipt(blockchain_access, tx_hash, timeout_seconds):
    return blockchain_access.get_w3().eth.wait_for_transaction_receipt(
        tx_hash,
        timeout=timeout_seconds,
    )


def diagnose_failed_swap(blockchain_access, tx, receipt=None):
    w3 = blockchain_access.get_w3()
    block_identifier = "latest"
    if receipt is not None and receipt.get("blockNumber") is not None:
        block_identifier = int(receipt["blockNumber"])

    payload = {
        "from": tx["from"],
        "to": tx["to"],
        "data": tx["data"],
        "value": tx.get("value", 0),
        "gas": int(tx["gas"]),
    }
    diagnostic = {
        "block_identifier": block_identifier,
        "same_gas_limit": int(tx["gas"]),
    }

    try:
        w3.eth.call(payload, block_identifier=block_identifier)
        diagnostic["same_gas_error"] = None
    except Exception as exc:
        diagnostic["same_gas_error"] = str(exc)

    higher_gas_limit = max(int(tx["gas"]) * 2, 1_500_000)
    payload["gas"] = higher_gas_limit
    diagnostic["higher_gas_limit"] = higher_gas_limit
    try:
        w3.eth.call(payload, block_identifier=block_identifier)
        diagnostic["higher_gas_success"] = True
        diagnostic["higher_gas_error"] = None
    except Exception as exc:
        diagnostic["higher_gas_success"] = False
        diagnostic["higher_gas_error"] = str(exc)

    if diagnostic["same_gas_error"] and diagnostic["higher_gas_success"]:
        diagnostic["summary"] = "Likely gas limit too low for this route."
    elif diagnostic["same_gas_error"] is not None:
        diagnostic["summary"] = diagnostic["same_gas_error"]
    else:
        diagnostic["summary"] = "eth_call did not reproduce the failure."

    return diagnostic


def save_trade_receipt(
    receipt_dir,
    chain,
    from_token,
    to_token,
    tx_hash,
    receipt,
    metadata,
):
    return BlockchainAccess.save_receipt(
        receipt_dir,
        f"{chain}-{from_token}-to-{to_token}",
        tx_hash,
        receipt,
        metadata,
    )


def maybe_confirm(args):
    if args.yes:
        return
    answer = input("Send transactions? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Cancelled")


def assess_quote_value(blockchain_access, from_token, to_token, input_amount, expected_amount_out):
    input_value_usd = blockchain_access.check_kyberswap_price([from_token, "usdc"], input_amount, log_quote=False)
    output_value_usd = blockchain_access.check_kyberswap_price([to_token, "usdc"], expected_amount_out, log_quote=False)

    if input_value_usd and output_value_usd:
        quote_discount_bps = (
            (Decimal(str(input_value_usd)) - Decimal(str(output_value_usd)))
            / Decimal(str(input_value_usd))
            * Decimal("10000")
        )
    else:
        quote_discount_bps = None

    return QuoteValuation(
        input_value_usd=Decimal(str(input_value_usd)) if input_value_usd else None,
        output_value_usd=Decimal(str(output_value_usd)) if output_value_usd else None,
        quote_discount_bps=quote_discount_bps,
    )


def print_preview(
    args,
    wallet,
    route,
    input_amount,
    expected_amount_out,
    approval_needed,
    approval_gas,
    swap_gas,
    quote_value,
):
    total_gas_cost_eth = swap_gas.gas_cost_eth
    total_gas_cost_usd = swap_gas.gas_cost_usd
    if approval_gas is not None:
        total_gas_cost_eth += approval_gas.gas_cost_eth
        if total_gas_cost_usd is not None and approval_gas.gas_cost_usd is not None:
            total_gas_cost_usd += approval_gas.gas_cost_usd
        else:
            total_gas_cost_usd = None

    print("Mode: execute" if args.execute else "Mode: preview")
    print(f"Wallet: {wallet}")
    print(f"Chain: {args.chain}")
    print(f"Swap: {input_amount} {args.from_token} -> {args.to_token}")
    print(f"Router: {route.router_address}")
    print(f"Expected output: {quantize_amount(expected_amount_out)} {args.to_token}")
    if quote_value.input_value_usd is not None:
        print(f"Input value (usd est): {quantize_amount(quote_value.input_value_usd, '0.01')} usdc")
    if quote_value.output_value_usd is not None:
        print(f"Output value (usd est): {quantize_amount(quote_value.output_value_usd, '0.01')} usdc")
    if quote_value.quote_discount_bps is not None:
        print(
            "Quote discount vs spot (rough): "
            f"{format_bps_percent(quote_value.quote_discount_bps)}%"
        )
    print(f"Route gas estimate (router units): {route.route_summary.get('gas')}")
    print(f"Approval needed: {approval_needed}")
    print(f"Total gas cost: {total_gas_cost_eth} ETH")
    if total_gas_cost_usd is not None:
        print(f"Total gas cost (usd est): {quantize_amount(total_gas_cost_usd, '0.01')} usdc")


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
    eth_usd_price = blockchain_access.check_kyberswap_price(["eth", "usdc"], Decimal("1"), log_quote=False)
    quote_value = assess_quote_value(
        blockchain_access,
        args.from_token,
        args.to_token,
        input_amount,
        expected_amount_out,
    )

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

    preview_swap_tx = build_swap_tx(blockchain_access, wallet, encoded_swap)
    preview_swap_gas_limit = int(preview_swap_tx["gas"])
    preview_swap_tx = apply_route_gas_floor(preview_swap_tx, route)
    swap_gas = assess_gas_cost(blockchain_access, preview_swap_gas_limit, eth_usd_price=eth_usd_price)

    print_preview(
        args=args,
        wallet=wallet,
        route=route,
        input_amount=input_amount,
        expected_amount_out=expected_amount_out,
        approval_needed=approval_needed,
        approval_gas=approval_gas,
        swap_gas=swap_gas,
        quote_value=quote_value,
    )

    if not args.execute:
        print("Preview only. Use --execute to actually send the trade.")
        return

    maybe_confirm(args)

    approval_hash = None
    approval_receipt = None
    if approval_tx is not None:
        approval_hash = sign_and_send(blockchain_access, approval_tx, private_key)
        print(f"Approval tx sent: {approval_hash}")
        approval_receipt = wait_for_receipt(
            blockchain_access,
            approval_hash,
            timeout_seconds=args.receipt_timeout_seconds,
        )
        if int(approval_receipt["status"]) != 1:
            raise RuntimeError(f"Approval transaction failed: {approval_hash}")
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

    swap_tx = build_swap_tx(blockchain_access, wallet, encoded_swap)
    swap_tx = apply_route_gas_floor(swap_tx, route)
    swap_hash = sign_and_send(blockchain_access, swap_tx, private_key)
    print(f"Swap tx sent: {swap_hash}")
    swap_receipt = wait_for_receipt(
        blockchain_access,
        swap_hash,
        timeout_seconds=args.receipt_timeout_seconds,
    )
    failed_swap_diagnostic = None
    if int(swap_receipt["status"]) != 1:
        failed_swap_diagnostic = diagnose_failed_swap(
            blockchain_access,
            swap_tx,
            receipt=swap_receipt,
        )
    metadata = {
        "chain": args.chain,
        "wallet": wallet,
        "from_token": args.from_token,
        "to_token": args.to_token,
        "input_amount": str(input_amount),
        "input_amount_wei": str(input_amount_wei),
        "expected_amount_out": str(expected_amount_out),
        "expected_amount_out_wei": str(amount_out_wei),
        "approval_needed": approval_needed,
        "approval_amount_wei": str(approval_amount_wei) if approval_needed else None,
        "approval_tx_hash": approval_hash,
        "route_router": route.router_address,
        "route_gas_estimate": route.route_summary.get("gas"),
        "quote_input_value_usd": str(quote_value.input_value_usd) if quote_value.input_value_usd is not None else None,
        "quote_output_value_usd": str(quote_value.output_value_usd) if quote_value.output_value_usd is not None else None,
        "quote_discount_bps": str(quote_value.quote_discount_bps) if quote_value.quote_discount_bps is not None else None,
        "preview_swap_gas_limit": swap_gas.gas_limit,
        "preview_swap_gas_price_wei": str(swap_gas.gas_price_wei),
        "swap_tx_hash": swap_hash,
    }
    if approval_gas is not None:
        metadata["preview_approval_gas_limit"] = approval_gas.gas_limit
        metadata["preview_approval_gas_price_wei"] = str(approval_gas.gas_price_wei)
    if approval_receipt is not None:
        metadata["approval_receipt_status"] = int(approval_receipt["status"])
    if failed_swap_diagnostic is not None:
        metadata["failed_swap_diagnostic"] = failed_swap_diagnostic
    receipt_path = save_trade_receipt(
        args.receipt_dir,
        args.chain,
        args.from_token,
        args.to_token,
        swap_hash,
        swap_receipt,
        metadata,
    )
    print(f"Receipt saved: {receipt_path}")
    print(f"Receipt status: {swap_receipt['status']}")
    if int(swap_receipt["status"]) != 1:
        print(f"Failure diagnostic: {failed_swap_diagnostic['summary']}")
        if failed_swap_diagnostic["same_gas_error"] is not None:
            print(f"Call with gas={failed_swap_diagnostic['same_gas_limit']}: {failed_swap_diagnostic['same_gas_error']}")
        if failed_swap_diagnostic["higher_gas_success"]:
            print(
                f"Call with gas={failed_swap_diagnostic['higher_gas_limit']}: ok"
            )
        elif failed_swap_diagnostic["higher_gas_error"] is not None:
            print(
                f"Call with gas={failed_swap_diagnostic['higher_gas_limit']}: {failed_swap_diagnostic['higher_gas_error']}"
            )
        raise RuntimeError(f"Swap transaction failed: {swap_hash}")


if __name__ == "__main__":
    main()
