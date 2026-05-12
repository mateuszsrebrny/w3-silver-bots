#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv
import json
import os
from pathlib import Path
import sys

from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from botweb3lib import BlockchainAccess


DEFAULT_CHAIN = "arbitrum"
DEFAULT_RECIPIENT_ENV_VAR = "WALLET"
DEFAULT_PRIVATE_KEY_ENV_VAR = "BOT_PRIVATE_KEY"
DEFAULT_RECEIPT_DIR = "reports/transfers"
DEFAULT_NATIVE_GAS_LIMIT = 21_000
DEFAULT_ERC20_TRANSFER_GAS_LIMIT = 100_000
DEFAULT_RECEIPT_TIMEOUT_SECONDS = 180
DEFAULT_GAS_BUFFER_BPS = 0


@dataclass(frozen=True)
class TransferPlan:
    tx: dict
    token: str
    amount: Decimal
    amount_wei: int
    gas_limit: int
    gas_price_wei: int
    gas_cost_native: Decimal
    balance_before_native: Decimal


def parse_args():
    parser = argparse.ArgumentParser(
        description="Preview or execute a token transfer from the bot wallet."
    )
    parser.add_argument("--chain", default=DEFAULT_CHAIN)
    parser.add_argument("--token", required=True, help="Configured token symbol, e.g. eth or dai")
    amount_group = parser.add_mutually_exclusive_group(required=True)
    amount_group.add_argument("--amount", help="Token amount in human units")
    amount_group.add_argument(
        "--all",
        action="store_true",
        help="Send the maximum possible amount of this token",
    )
    parser.add_argument("--to", help="Recipient address. Defaults to WALLET from .env")
    parser.add_argument(
        "--to-env-var",
        default=DEFAULT_RECIPIENT_ENV_VAR,
        help="Recipient env var to use when --to is omitted",
    )
    parser.add_argument(
        "--private-key-env-var",
        default=DEFAULT_PRIVATE_KEY_ENV_VAR,
        help="Env var holding the sender private key",
    )
    parser.add_argument("--config", default="chains.config.yaml")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview only. This is already the default unless --execute is set.",
    )
    parser.add_argument("--execute", action="store_true", help="Actually send the transaction")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation when --execute is set")
    parser.add_argument(
        "--gas-buffer-bps",
        type=int,
        default=DEFAULT_GAS_BUFFER_BPS,
        help="Optional gas-limit buffer in basis points above the RPC estimate. Default is 0.",
    )
    parser.add_argument(
        "--receipt-dir",
        default=DEFAULT_RECEIPT_DIR,
        help="Directory for saved JSON receipts",
    )
    parser.add_argument(
        "--receipt-timeout-seconds",
        type=int,
        default=DEFAULT_RECEIPT_TIMEOUT_SECONDS,
        help="How long to wait for a mined receipt after sending",
    )
    return parser.parse_args()


def quantize_amount(value, places="0.000000"):
    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_DOWN)


def load_private_key(env_var):
    private_key = os.getenv(env_var) or os.getenv("PRIVATE_KEY")
    if not private_key:
        raise ValueError(f"{env_var} is not set in the environment")
    return private_key


def wallet_from_private_key(private_key):
    return Web3().eth.account.from_key(private_key).address


def load_recipient(args):
    recipient = args.to or os.getenv(args.to_env_var)
    if not recipient:
        raise ValueError(
            f"Recipient not provided. Use --to or set {args.to_env_var} in the environment."
        )
    return Web3.to_checksum_address(recipient)


def to_token_wei(blockchain_access, token, amount):
    return BlockchainAccess.my_toWei(amount, blockchain_access.get_decimals(token))


def from_token_wei(blockchain_access, token, amount_wei):
    return BlockchainAccess.my_fromWei(amount_wei, blockchain_access.get_decimals(token))


def fee_cap_wei(fee_params):
    if "maxFeePerGas" in fee_params:
        return int(fee_params["maxFeePerGas"])
    return int(fee_params["gasPrice"])


def build_fee_params(w3):
    latest_block = w3.eth.get_block("latest")
    base_fee_wei = int(latest_block.get("baseFeePerGas", 0) or 0)
    try:
        priority_fee_wei = int(w3.eth.max_priority_fee)
    except Exception:
        priority_fee_wei = 100_000

    if base_fee_wei > 0:
        max_fee_per_gas_wei = (2 * base_fee_wei) + priority_fee_wei
        return {
            "maxFeePerGas": max_fee_per_gas_wei,
            "maxPriorityFeePerGas": priority_fee_wei,
            "type": 2,
        }

    gas_price_wei = int(w3.eth.gas_price)
    return {"gasPrice": gas_price_wei}


def estimate_gas(w3, tx, fallback_gas_limit):
    try:
        return int(w3.eth.estimate_gas(tx))
    except Exception as exc:
        print(
            f"Gas estimation failed for tx to {tx.get('to')}: {exc}. "
            f"Falling back to gas limit {fallback_gas_limit}.",
            file=sys.stderr,
        )
        return fallback_gas_limit


def buffered_gas_limit(estimated_gas, buffer_bps=DEFAULT_GAS_BUFFER_BPS):
    return max(int(estimated_gas), (int(estimated_gas) * (10_000 + buffer_bps) + 9_999) // 10_000)


def build_native_transfer_plan(
    blockchain_access,
    token,
    sender,
    recipient,
    amount=None,
    send_all=False,
    gas_buffer_bps=DEFAULT_GAS_BUFFER_BPS,
):
    w3 = blockchain_access.get_w3()
    fee_params = build_fee_params(w3)
    gas_price_wei = fee_cap_wei(fee_params)
    balance_wei = int(w3.eth.get_balance(sender))
    balance_native = from_token_wei(blockchain_access, token, balance_wei)
    nonce = w3.eth.get_transaction_count(sender)

    preview_tx = {
        "from": sender,
        "to": recipient,
        "value": 0,
        "nonce": nonce,
        "chainId": blockchain_access.get_chain_id(),
        **fee_params,
    }
    initial_gas_limit = buffered_gas_limit(
        estimate_gas(w3, preview_tx, DEFAULT_NATIVE_GAS_LIMIT),
        buffer_bps=gas_buffer_bps,
    )
    gas_cost_wei = initial_gas_limit * gas_price_wei

    if send_all:
        amount_wei = balance_wei - gas_cost_wei
        if amount_wei <= 0:
            raise ValueError("Native balance is too low to cover gas for a send-all transfer.")
    else:
        if amount is None:
            raise ValueError("Amount is required when send_all is False.")
        amount_wei = to_token_wei(blockchain_access, token, amount)
        if amount_wei <= 0:
            raise ValueError("Transfer amount must be greater than zero.")
        if amount_wei + gas_cost_wei > balance_wei:
            raise ValueError(
                "Insufficient native balance to cover the requested transfer amount plus gas."
            )

    gas_probe_tx = {
        "from": sender,
        "to": recipient,
        "value": amount_wei,
        "nonce": nonce,
        "chainId": blockchain_access.get_chain_id(),
        **fee_params,
    }
    gas_limit = buffered_gas_limit(
        estimate_gas(w3, gas_probe_tx, initial_gas_limit),
        buffer_bps=gas_buffer_bps,
    )
    gas_cost_wei = gas_limit * gas_price_wei

    if send_all:
        amount_wei = balance_wei - gas_cost_wei
        if amount_wei <= 0:
            raise ValueError("Native balance is too low to cover gas for a send-all transfer.")
    elif amount_wei + gas_cost_wei > balance_wei:
        raise ValueError(
            "Insufficient native balance to cover the requested transfer amount plus gas."
        )

    tx = {
        "from": sender,
        "to": recipient,
        "value": amount_wei,
        "nonce": nonce,
        "chainId": blockchain_access.get_chain_id(),
        **fee_params,
        "gas": gas_limit,
    }
    transfer_amount = from_token_wei(blockchain_access, token, amount_wei)
    gas_cost_native = from_token_wei(blockchain_access, token, gas_cost_wei)
    return TransferPlan(
        tx=tx,
        token=token,
        amount=transfer_amount,
        amount_wei=amount_wei,
        gas_limit=gas_limit,
        gas_price_wei=gas_price_wei,
        gas_cost_native=gas_cost_native,
        balance_before_native=balance_native,
    )


def build_erc20_transfer_plan(
    blockchain_access,
    token,
    sender,
    recipient,
    amount=None,
    send_all=False,
    gas_buffer_bps=DEFAULT_GAS_BUFFER_BPS,
):
    w3 = blockchain_access.get_w3()
    contract = blockchain_access.get_token_contract(token)
    fee_params = build_fee_params(w3)
    gas_price_wei = fee_cap_wei(fee_params)
    nonce = w3.eth.get_transaction_count(sender)
    balance_wei = int(contract.functions.balanceOf(sender).call())
    balance_native = from_token_wei(blockchain_access, "eth", int(w3.eth.get_balance(sender)))

    if send_all:
        amount_wei = balance_wei
    else:
        if amount is None:
            raise ValueError("Amount is required when send_all is False.")
        amount_wei = to_token_wei(blockchain_access, token, amount)

    if amount_wei <= 0:
        raise ValueError("Transfer amount must be greater than zero.")
    if amount_wei > balance_wei:
        raise ValueError("Insufficient token balance for the requested transfer amount.")

    tx = contract.functions.transfer(recipient, amount_wei).build_transaction(
        {
            "from": sender,
            "nonce": nonce,
            "chainId": blockchain_access.get_chain_id(),
            **fee_params,
        }
    )
    tx["gas"] = buffered_gas_limit(
        estimate_gas(w3, tx, DEFAULT_ERC20_TRANSFER_GAS_LIMIT),
        buffer_bps=gas_buffer_bps,
    )

    gas_cost_wei = int(tx["gas"]) * gas_price_wei
    gas_cost_native = from_token_wei(blockchain_access, "eth", gas_cost_wei)
    transfer_amount = from_token_wei(blockchain_access, token, amount_wei)
    return TransferPlan(
        tx=tx,
        token=token,
        amount=transfer_amount,
        amount_wei=amount_wei,
        gas_limit=int(tx["gas"]),
        gas_price_wei=gas_price_wei,
        gas_cost_native=gas_cost_native,
        balance_before_native=balance_native,
    )


def build_transfer_plan(
    blockchain_access,
    token,
    sender,
    recipient,
    amount=None,
    send_all=False,
    gas_buffer_bps=DEFAULT_GAS_BUFFER_BPS,
):
    if blockchain_access.is_native_token(token):
        return build_native_transfer_plan(
            blockchain_access,
            token,
            sender,
            recipient,
            amount=amount,
            send_all=send_all,
            gas_buffer_bps=gas_buffer_bps,
        )
    return build_erc20_transfer_plan(
        blockchain_access,
        token,
        sender,
        recipient,
        amount=amount,
        send_all=send_all,
        gas_buffer_bps=gas_buffer_bps,
    )


def sign_and_send(blockchain_access, tx, private_key):
    w3 = blockchain_access.get_w3()
    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


def to_jsonable(value):
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): to_jsonable(inner) for key, inner in value.items()}
    return value


def save_receipt(receipt_dir, chain, token, tx_hash, receipt, metadata):
    receipt_path = Path(receipt_dir)
    receipt_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}-{chain}-{token}-{tx_hash[:10]}.json"
    output_path = receipt_path / filename
    payload = {
        "saved_at_utc": timestamp,
        "metadata": metadata,
        "receipt": to_jsonable(dict(receipt)),
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output_path


def maybe_confirm(args):
    if args.yes:
        return
    answer = input("Send transfer? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Cancelled")


def print_preview(args, sender, recipient, plan):
    mode = "all available" if args.all else args.amount
    print("Mode: execute" if args.execute else "Mode: preview")
    print(f"Sender: {sender}")
    print(f"Recipient: {recipient}")
    print(f"Chain: {args.chain}")
    print(f"Token: {args.token}")
    print(f"Requested: {mode}")
    print(f"Transfer amount: {plan.amount} {args.token}")
    print(f"Transfer amount (quantized): {quantize_amount(plan.amount)} {args.token}")
    print(f"Balance before gas: {plan.balance_before_native}")
    print(f"Gas: {plan.gas_limit} @ fee cap {plan.gas_price_wei} wei")
    print(f"Estimated gas cost: {plan.gas_cost_native} ETH")
    if args.all and args.token == "eth":
        print("Native send-all mode: amount is balance minus estimated gas.")


def main():
    load_dotenv()
    args = parse_args()

    BlockchainAccess.load_config(args.config)
    blockchain_access = BlockchainAccess(chain=args.chain, dry_run=not args.execute)
    private_key = load_private_key(args.private_key_env_var)
    sender = Web3.to_checksum_address(wallet_from_private_key(private_key))
    recipient = load_recipient(args)

    if sender == recipient:
        raise ValueError("Sender and recipient must be different addresses.")

    amount = Decimal(str(args.amount)) if args.amount is not None else None
    plan = build_transfer_plan(
        blockchain_access,
        args.token,
        sender,
        recipient,
        amount=amount,
        send_all=args.all,
        gas_buffer_bps=args.gas_buffer_bps,
    )

    print_preview(args, sender, recipient, plan)

    if not args.execute:
        print("Preview only. Use --execute to actually send the transfer.")
        return

    maybe_confirm(args)

    tx_hash = sign_and_send(blockchain_access, plan.tx, private_key)
    print(f"Transfer tx sent: {tx_hash}")

    receipt = blockchain_access.get_w3().eth.wait_for_transaction_receipt(
        tx_hash,
        timeout=args.receipt_timeout_seconds,
    )
    metadata = {
        "chain": args.chain,
        "sender": sender,
        "recipient": recipient,
        "token": args.token,
        "requested_amount": "all" if args.all else str(args.amount),
        "transfer_amount": str(plan.amount),
        "transfer_amount_wei": str(plan.amount_wei),
        "gas_limit": plan.gas_limit,
        "gas_price_wei": str(plan.gas_price_wei),
        "estimated_gas_cost_native": str(plan.gas_cost_native),
        "tx_hash": tx_hash,
    }
    receipt_path = save_receipt(
        args.receipt_dir,
        args.chain,
        args.token,
        tx_hash,
        receipt,
        metadata,
    )
    print(f"Receipt saved: {receipt_path}")
    print(f"Receipt status: {receipt['status']}")


if __name__ == "__main__":
    main()
