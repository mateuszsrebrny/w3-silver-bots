#!/usr/bin/env python3

import argparse
from dataclasses import dataclass
from decimal import Decimal
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
DEFAULT_RECEIPT_DIR = "reports/aave_withdrawals"
DEFAULT_RECEIPT_TIMEOUT_SECONDS = 180
DEFAULT_WITHDRAW_GAS_LIMIT = 300000
AAVE_POOL_BY_CHAIN = {
    "arbitrum": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
}
WITHDRAWABLE_AAVE_TOKENS = {
    "arbitrum": {
        "adai": "dai",
    }
}
AAVE_POOL_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "to", "type": "address"},
        ],
        "name": "withdraw",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@dataclass(frozen=True)
class WithdrawPlan:
    wallet: str
    atoken: str
    underlying_token: str
    amount: Decimal
    amount_wei: int
    atoken_balance: Decimal
    withdraw_tx: dict
    total_gas_cost_eth: Decimal


def parse_args():
    parser = argparse.ArgumentParser(description="Preview or execute an Aave withdraw on Arbitrum.")
    parser.add_argument("--chain", default=DEFAULT_CHAIN, choices=["arbitrum"])
    parser.add_argument("--token", required=True, choices=["adai"])
    amount_group = parser.add_mutually_exclusive_group(required=True)
    amount_group.add_argument("--amount", help="aToken amount in human units")
    amount_group.add_argument("--all", action="store_true", help="Use full aToken balance")
    parser.add_argument("--to", help="Recipient wallet. Defaults to the sender wallet.")
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
    parser.add_argument("--execute", action="store_true", help="Actually send the transaction")
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
        help="How long to wait for a mined receipt after the transaction is sent",
    )
    parser.add_argument("--config", default="chains.config.yaml")
    return parser.parse_args()


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


def resolve_pool_address(args):
    return Web3.to_checksum_address(args.pool or AAVE_POOL_BY_CHAIN[args.chain])


def resolve_underlying_token(chain, atoken):
    return WITHDRAWABLE_AAVE_TOKENS[chain][atoken]


def build_withdraw_tx(blockchain_access, owner, pool_address, asset_address, amount_wei, nonce, recipient):
    w3 = blockchain_access.get_w3()
    fee_params = BlockchainAccess.build_fee_params(w3)
    contract = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=AAVE_POOL_ABI)
    tx = contract.functions.withdraw(
        Web3.to_checksum_address(asset_address),
        amount_wei,
        Web3.to_checksum_address(recipient),
    ).build_transaction(
        {
            "from": owner,
            "nonce": nonce,
            "chainId": blockchain_access.get_chain_id(),
            "gas": DEFAULT_WITHDRAW_GAS_LIMIT,
            **fee_params,
        }
    )
    tx["gas"] = BlockchainAccess.estimate_gas(w3, tx, DEFAULT_WITHDRAW_GAS_LIMIT)
    return tx


def gas_cost_eth(blockchain_access, tx):
    fee_cap_wei = BlockchainAccess.fee_cap_wei(BlockchainAccess.build_fee_params(blockchain_access.get_w3()))
    return from_token_wei(blockchain_access, "eth", int(tx["gas"]) * fee_cap_wei)


def build_withdraw_plan(blockchain_access, args, wallet):
    atoken = args.token
    underlying_token = resolve_underlying_token(args.chain, atoken)
    recipient = Web3.to_checksum_address(args.to or wallet)
    atoken_balance = blockchain_access.check_balance_token(atoken, wallet)
    if args.all:
        amount = atoken_balance
    else:
        amount = Decimal(str(args.amount))

    amount_wei = to_token_wei(blockchain_access, atoken, amount)
    if amount_wei <= 0:
        raise ValueError("Withdraw amount must be greater than zero.")

    if amount > atoken_balance:
        raise ValueError(f"Withdraw amount exceeds {atoken} balance of {atoken_balance}.")

    nonce = blockchain_access.get_w3().eth.get_transaction_count(wallet)
    pool_address = resolve_pool_address(args)
    withdraw_tx = build_withdraw_tx(
        blockchain_access,
        wallet,
        pool_address,
        blockchain_access.get_token_contract_address(underlying_token),
        amount_wei,
        nonce,
        recipient,
    )

    return WithdrawPlan(
        wallet=wallet,
        atoken=atoken,
        underlying_token=underlying_token,
        amount=amount,
        amount_wei=amount_wei,
        atoken_balance=atoken_balance,
        withdraw_tx=withdraw_tx,
        total_gas_cost_eth=gas_cost_eth(blockchain_access, withdraw_tx),
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
    answer = input("Send Aave withdraw transaction? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Cancelled")


def print_preview(args, plan, pool_address):
    print("Mode: execute" if args.execute else "Mode: preview")
    print(f"Wallet: {plan.wallet}")
    print(f"Chain: {args.chain}")
    print(f"Aave pool: {pool_address}")
    print(f"Withdraw: {plan.amount} {plan.atoken} -> {plan.underlying_token}")
    print(f"aToken balance: {plan.atoken_balance} {plan.atoken}")
    print(f"Estimated total gas cost: {plan.total_gas_cost_eth} ETH")


def main():
    load_dotenv()
    args = parse_args()

    BlockchainAccess.load_config(args.config)
    blockchain_access = BlockchainAccess(chain=args.chain, dry_run=not args.execute)
    private_key = load_private_key(args.private_key_env_var)
    wallet = Web3.to_checksum_address(wallet_from_private_key(private_key))
    pool_address = resolve_pool_address(args)
    plan = build_withdraw_plan(blockchain_access, args, wallet)

    print_preview(args, plan, pool_address)

    if not args.execute:
        print("Preview only. Use --execute to actually send the Aave withdraw.")
        return

    maybe_confirm(args)

    withdraw_hash = sign_and_send(blockchain_access, plan.withdraw_tx, private_key)
    print(f"Withdraw tx sent: {withdraw_hash}")
    withdraw_receipt = wait_for_receipt(blockchain_access, withdraw_hash, args.receipt_timeout_seconds)
    metadata = {
        "chain": args.chain,
        "wallet": wallet,
        "recipient": Web3.to_checksum_address(args.to or wallet),
        "atoken": plan.atoken,
        "underlying_token": plan.underlying_token,
        "amount": str(plan.amount),
        "amount_wei": str(plan.amount_wei),
        "pool_address": pool_address,
        "withdraw_tx_hash": withdraw_hash,
    }
    receipt_path = BlockchainAccess.save_receipt(
        args.receipt_dir,
        f"{args.chain}-aave-withdraw-{plan.atoken}",
        withdraw_hash,
        withdraw_receipt,
        metadata,
    )
    print(f"Receipt saved: {receipt_path}")
    print(f"Receipt status: {withdraw_receipt['status']}")
    if int(withdraw_receipt["status"]) != 1:
        raise RuntimeError(f"Withdraw transaction failed: {withdraw_hash}")


if __name__ == "__main__":
    main()
