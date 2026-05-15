#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv
import os
from pathlib import Path
import sys

from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from botweb3lib import BlockchainAccess


DEFAULT_CHAIN = "arbitrum"
DEFAULT_PRIVATE_KEY_ENV_VAR = "BOT_PRIVATE_KEY"
DEFAULT_RECEIPT_DIR = "reports/aave_supplies"
DEFAULT_RECEIPT_TIMEOUT_SECONDS = 180
DEFAULT_REFERRAL_CODE = 0
DEFAULT_SUPPLY_GAS_LIMIT = 400000
AAVE_POOL_BY_CHAIN = {
    "arbitrum": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
}
WETH_ABI = [
    {
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    }
]
AAVE_POOL_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"},
            {"internalType": "uint16", "name": "referralCode", "type": "uint16"},
        ],
        "name": "supply",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]
WRAPPED_NATIVE_BY_CHAIN = {
    "arbitrum": "weth",
}


@dataclass(frozen=True)
class SupplyPlan:
    wallet: str
    display_token: str
    pool_token: str
    amount: Decimal
    amount_wei: int
    approval_needed: bool
    wrap_tx: dict | None
    approve_tx: dict | None
    supply_tx: dict
    total_gas_cost_eth: Decimal


def parse_args():
    parser = argparse.ArgumentParser(description="Preview or execute an Aave supply on Arbitrum.")
    parser.add_argument("--chain", default=DEFAULT_CHAIN, choices=["arbitrum"])
    parser.add_argument("--token", required=True, choices=["dai", "wbtc", "eth"])
    amount_group = parser.add_mutually_exclusive_group(required=True)
    amount_group.add_argument("--amount", help="Token amount in human units")
    amount_group.add_argument("--all", action="store_true", help="Use full token balance. ETH is not supported with --all.")
    parser.add_argument("--pool")
    parser.add_argument(
        "--private-key-env-var",
        default=DEFAULT_PRIVATE_KEY_ENV_VAR,
        help="Env var holding the sender private key",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview only. This is already the default unless --execute is set.",
    )
    parser.add_argument("--execute", action="store_true", help="Actually send the transactions")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation when --execute is set")
    parser.add_argument(
        "--receipt-dir",
        default=DEFAULT_RECEIPT_DIR,
        help="Directory for saved JSON receipts",
    )
    parser.add_argument(
        "--receipt-timeout-seconds",
        type=int,
        default=DEFAULT_RECEIPT_TIMEOUT_SECONDS,
        help="How long to wait for a mined receipt after each sent transaction",
    )
    parser.add_argument("--config", default="chains.config.yaml")
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


def to_token_wei(blockchain_access, token, amount):
    return BlockchainAccess.my_toWei(amount, blockchain_access.get_decimals(token))


def from_token_wei(blockchain_access, token, amount_wei):
    return BlockchainAccess.my_fromWei(amount_wei, blockchain_access.get_decimals(token))


def build_approve_tx(blockchain_access, token, owner, spender, amount_wei, nonce):
    contract = blockchain_access.get_token_contract(token)
    w3 = blockchain_access.get_w3()
    fee_params = BlockchainAccess.build_fee_params(w3)
    tx = contract.functions.approve(spender, amount_wei).build_transaction(
        {
            "from": owner,
            "nonce": nonce,
            "chainId": blockchain_access.get_chain_id(),
            **fee_params,
        }
    )
    tx["gas"] = BlockchainAccess.estimate_gas(w3, tx, 65000)
    return tx


def build_wrap_tx(blockchain_access, owner, amount_wei, nonce):
    w3 = blockchain_access.get_w3()
    fee_params = BlockchainAccess.build_fee_params(w3)
    weth = WRAPPED_NATIVE_BY_CHAIN[blockchain_access.get_chain()]
    contract = w3.eth.contract(
        address=blockchain_access.get_token_contract_address(weth),
        abi=WETH_ABI,
    )
    tx = contract.functions.deposit().build_transaction(
        {
            "from": owner,
            "nonce": nonce,
            "chainId": blockchain_access.get_chain_id(),
            "value": amount_wei,
            **fee_params,
        }
    )
    tx["gas"] = BlockchainAccess.estimate_gas(w3, tx, 120000)
    return tx


def build_supply_tx(blockchain_access, owner, pool_address, asset_address, amount_wei, nonce):
    w3 = blockchain_access.get_w3()
    fee_params = BlockchainAccess.build_fee_params(w3)
    contract = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=AAVE_POOL_ABI)
    tx = contract.functions.supply(
        Web3.to_checksum_address(asset_address),
        amount_wei,
        owner,
        DEFAULT_REFERRAL_CODE,
    ).build_transaction(
        {
            "from": owner,
            "nonce": nonce,
            "chainId": blockchain_access.get_chain_id(),
            "gas": DEFAULT_SUPPLY_GAS_LIMIT,
            **fee_params,
        }
    )
    tx["gas"] = BlockchainAccess.estimate_gas(w3, tx, DEFAULT_SUPPLY_GAS_LIMIT)
    return tx


def gas_cost_eth(blockchain_access, tx):
    fee_cap_wei = BlockchainAccess.fee_cap_wei(BlockchainAccess.build_fee_params(blockchain_access.get_w3()))
    return from_token_wei(blockchain_access, "eth", int(tx["gas"]) * fee_cap_wei)


def resolve_pool_address(args):
    return Web3.to_checksum_address(args.pool or AAVE_POOL_BY_CHAIN[args.chain])


def build_supply_plan(blockchain_access, args, wallet):
    token = args.token
    if args.all and token == "eth":
        raise ValueError("Native ETH does not support --all. Use an explicit --amount.")

    w3 = blockchain_access.get_w3()
    nonce = w3.eth.get_transaction_count(wallet)
    pool_address = resolve_pool_address(args)
    amount = None

    if token == "eth":
        if args.amount is None:
            raise ValueError("ETH supply requires an explicit --amount.")
        amount = Decimal(str(args.amount))
        amount_wei = to_token_wei(blockchain_access, token, amount)
        if amount_wei <= 0:
            raise ValueError("Supply amount must be greater than zero.")
        pool_token = WRAPPED_NATIVE_BY_CHAIN[args.chain]
        wrap_tx = build_wrap_tx(blockchain_access, wallet, amount_wei, nonce)
        nonce += 1
        allowance = blockchain_access.check_allowance(pool_token, wallet, pool_address)
        approval_needed = allowance < amount
        approve_tx = None
        if approval_needed:
            approve_tx = build_approve_tx(blockchain_access, pool_token, wallet, pool_address, amount_wei, nonce)
            nonce += 1
        supply_tx = build_supply_tx(
            blockchain_access,
            wallet,
            pool_address,
            blockchain_access.get_token_contract_address(pool_token),
            amount_wei,
            nonce,
        )
    else:
        if args.all:
            amount = blockchain_access.check_balance_token(token, wallet)
        else:
            amount = Decimal(str(args.amount))
        amount_wei = to_token_wei(blockchain_access, token, amount)
        if amount_wei <= 0:
            raise ValueError("Supply amount must be greater than zero.")
        pool_token = token
        wrap_tx = None
        allowance = blockchain_access.check_allowance(token, wallet, pool_address)
        approval_needed = allowance < amount
        approve_tx = None
        if approval_needed:
            approve_tx = build_approve_tx(blockchain_access, token, wallet, pool_address, amount_wei, nonce)
            nonce += 1
        supply_tx = build_supply_tx(
            blockchain_access,
            wallet,
            pool_address,
            blockchain_access.get_token_contract_address(token),
            amount_wei,
            nonce,
        )

    total_gas = gas_cost_eth(blockchain_access, supply_tx)
    if approve_tx is not None:
        total_gas += gas_cost_eth(blockchain_access, approve_tx)
    if wrap_tx is not None:
        total_gas += gas_cost_eth(blockchain_access, wrap_tx)

    return SupplyPlan(
        wallet=wallet,
        display_token=token,
        pool_token=pool_token,
        amount=amount,
        amount_wei=amount_wei,
        approval_needed=approval_needed,
        wrap_tx=wrap_tx,
        approve_tx=approve_tx,
        supply_tx=supply_tx,
        total_gas_cost_eth=total_gas,
    )


def sign_and_send(blockchain_access, tx, private_key):
    signed = blockchain_access.get_w3().eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = blockchain_access.get_w3().eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


def wait_for_receipt(blockchain_access, tx_hash, timeout_seconds):
    return blockchain_access.get_w3().eth.wait_for_transaction_receipt(tx_hash, timeout=timeout_seconds)


def maybe_confirm(args):
    if args.yes:
        return
    answer = input("Send Aave supply transactions? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Cancelled")


def print_preview(args, plan, pool_address):
    print("Mode: execute" if args.execute else "Mode: preview")
    print(f"Wallet: {plan.wallet}")
    print(f"Chain: {args.chain}")
    print(f"Aave pool: {pool_address}")
    print(f"Supply: {plan.amount} {plan.display_token}")
    if plan.display_token != plan.pool_token:
        print(f"Supplied asset on Aave: {plan.pool_token}")
    print(f"Approval needed: {plan.approval_needed}")
    print(f"Wrap needed: {plan.wrap_tx is not None}")
    print(f"Estimated total gas cost: {plan.total_gas_cost_eth} ETH")


def main():
    load_dotenv()
    args = parse_args()

    BlockchainAccess.load_config(args.config)
    blockchain_access = BlockchainAccess(chain=args.chain, dry_run=not args.execute)
    private_key = load_private_key(args.private_key_env_var)
    wallet = Web3.to_checksum_address(wallet_from_private_key(private_key))
    pool_address = resolve_pool_address(args)
    plan = build_supply_plan(blockchain_access, args, wallet)

    print_preview(args, plan, pool_address)

    if not args.execute:
        print("Preview only. Use --execute to actually send the Aave supply.")
        return

    maybe_confirm(args)

    wrap_hash = None
    approve_hash = None
    if plan.wrap_tx is not None:
        wrap_hash = sign_and_send(blockchain_access, plan.wrap_tx, private_key)
        print(f"Wrap tx sent: {wrap_hash}")
        wrap_receipt = wait_for_receipt(blockchain_access, wrap_hash, args.receipt_timeout_seconds)
        if int(wrap_receipt["status"]) != 1:
            raise RuntimeError(f"Wrap transaction failed: {wrap_hash}")

    if plan.approve_tx is not None:
        approve_hash = sign_and_send(blockchain_access, plan.approve_tx, private_key)
        print(f"Approval tx sent: {approve_hash}")
        approval_receipt = wait_for_receipt(blockchain_access, approve_hash, args.receipt_timeout_seconds)
        if int(approval_receipt["status"]) != 1:
            raise RuntimeError(f"Approval transaction failed: {approve_hash}")

    final_nonce = blockchain_access.get_w3().eth.get_transaction_count(wallet)
    final_supply_tx = build_supply_tx(
        blockchain_access,
        wallet,
        pool_address,
        blockchain_access.get_token_contract_address(plan.pool_token),
        plan.amount_wei,
        final_nonce,
    )
    supply_hash = sign_and_send(blockchain_access, final_supply_tx, private_key)
    print(f"Supply tx sent: {supply_hash}")
    supply_receipt = wait_for_receipt(blockchain_access, supply_hash, args.receipt_timeout_seconds)
    metadata = {
        "chain": args.chain,
        "wallet": wallet,
        "display_token": plan.display_token,
        "pool_token": plan.pool_token,
        "amount": str(plan.amount),
        "amount_wei": str(plan.amount_wei),
        "pool_address": pool_address,
        "approval_needed": plan.approval_needed,
        "wrap_tx_hash": wrap_hash,
        "approval_tx_hash": approve_hash,
        "supply_tx_hash": supply_hash,
    }
    receipt_path = BlockchainAccess.save_receipt(
        args.receipt_dir,
        f"{args.chain}-aave-supply-{plan.display_token}",
        supply_hash,
        supply_receipt,
        metadata,
    )
    print(f"Receipt saved: {receipt_path}")
    print(f"Receipt status: {supply_receipt['status']}")
    if int(supply_receipt["status"]) != 1:
        raise RuntimeError(f"Supply transaction failed: {supply_hash}")


if __name__ == "__main__":
    main()
