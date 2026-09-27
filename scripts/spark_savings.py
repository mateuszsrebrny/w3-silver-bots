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
DEFAULT_RECEIPT_DIR = "reports/spark_savings"
DEFAULT_RECEIPT_TIMEOUT_SECONDS = 180
DEFAULT_REFERRAL_CODE = 0
DEFAULT_SLIPPAGE_BPS = 5
SPARK_PSM_BY_CHAIN = {
    "arbitrum": "0x2B05F8e1cACC6974fD79A673a341Fe1f58d27266",
}
PSM_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "assetIn", "type": "address"},
            {"internalType": "address", "name": "assetOut", "type": "address"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
        ],
        "name": "previewSwapExactIn",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "assetIn", "type": "address"},
            {"internalType": "address", "name": "assetOut", "type": "address"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "minAmountOut", "type": "uint256"},
            {"internalType": "address", "name": "receiver", "type": "address"},
            {"internalType": "uint256", "name": "referralCode", "type": "uint256"},
        ],
        "name": "swapExactIn",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass(frozen=True)
class SparkSavingsPlan:
    wallet: str
    amount: Decimal
    amount_wei: int
    expected_susds: Decimal
    expected_susds_wei: int
    min_susds: Decimal
    min_susds_wei: int
    approval_needed: bool
    approve_tx: dict | None
    swap_tx: dict
    total_gas_cost_eth: Decimal


def parse_args():
    parser = argparse.ArgumentParser(description="Preview or execute Spark Savings USDS -> sUSDS on Arbitrum.")
    parser.add_argument("--chain", default=DEFAULT_CHAIN, choices=["arbitrum"])
    parser.add_argument("--amount", required=True, help="USDS amount in human units")
    parser.add_argument("--psm")
    parser.add_argument("--slippage-bps", type=int, default=DEFAULT_SLIPPAGE_BPS)
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
    parser.add_argument("--receipt-dir", default=DEFAULT_RECEIPT_DIR)
    parser.add_argument("--receipt-timeout-seconds", type=int, default=DEFAULT_RECEIPT_TIMEOUT_SECONDS)
    parser.add_argument("--config", default="chains.config.yaml")
    args = parser.parse_args()

    if args.slippage_bps < 0 or args.slippage_bps > 1000:
        parser.error("--slippage-bps must be between 0 and 1000")
    return args


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


def resolve_psm_address(args):
    return Web3.to_checksum_address(args.psm or SPARK_PSM_BY_CHAIN[args.chain])


def build_approve_tx(blockchain_access, owner, spender, amount_wei, nonce):
    contract = blockchain_access.get_token_contract("usds")
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


def get_psm_contract(blockchain_access, psm_address):
    return blockchain_access.get_w3().eth.contract(address=Web3.to_checksum_address(psm_address), abi=PSM_ABI)


def build_swap_tx(blockchain_access, owner, psm_address, amount_wei, min_susds_wei, nonce):
    w3 = blockchain_access.get_w3()
    fee_params = BlockchainAccess.build_fee_params(w3)
    contract = get_psm_contract(blockchain_access, psm_address)
    tx = contract.functions.swapExactIn(
        blockchain_access.get_token_contract_address("usds"),
        blockchain_access.get_token_contract_address("susds"),
        amount_wei,
        min_susds_wei,
        owner,
        DEFAULT_REFERRAL_CODE,
    ).build_transaction(
        {
            "from": owner,
            "nonce": nonce,
            "chainId": blockchain_access.get_chain_id(),
            **fee_params,
        }
    )
    tx["gas"] = BlockchainAccess.estimate_gas(w3, tx, 220000)
    return tx


def gas_cost_eth(blockchain_access, tx):
    fee_cap_wei = BlockchainAccess.fee_cap_wei(BlockchainAccess.build_fee_params(blockchain_access.get_w3()))
    return from_token_wei(blockchain_access, "eth", int(tx["gas"]) * fee_cap_wei)


def build_plan(blockchain_access, args, wallet):
    amount = Decimal(str(args.amount))
    amount_wei = to_token_wei(blockchain_access, "usds", amount)
    if amount_wei <= 0:
        raise ValueError("Spark Savings amount must be greater than zero.")

    balance = blockchain_access.check_balance_token("usds", wallet)
    if Decimal(str(balance)) < amount:
        raise ValueError(f"Insufficient USDS balance: have {balance}, need {amount}.")

    psm_address = resolve_psm_address(args)
    psm_contract = get_psm_contract(blockchain_access, psm_address)
    expected_susds_wei = int(
        psm_contract.functions.previewSwapExactIn(
            blockchain_access.get_token_contract_address("usds"),
            blockchain_access.get_token_contract_address("susds"),
            amount_wei,
        ).call()
    )
    min_susds_wei = expected_susds_wei * (10_000 - int(args.slippage_bps)) // 10_000

    expected_susds = from_token_wei(blockchain_access, "susds", expected_susds_wei)
    min_susds = from_token_wei(blockchain_access, "susds", min_susds_wei)

    w3 = blockchain_access.get_w3()
    nonce = w3.eth.get_transaction_count(wallet)
    allowance = blockchain_access.check_allowance("usds", wallet, psm_address)
    approval_needed = allowance < amount
    approve_tx = None
    if approval_needed:
        approve_tx = build_approve_tx(blockchain_access, wallet, psm_address, amount_wei, nonce)
        nonce += 1
    swap_tx = build_swap_tx(blockchain_access, wallet, psm_address, amount_wei, min_susds_wei, nonce)

    total_gas = gas_cost_eth(blockchain_access, swap_tx)
    if approve_tx is not None:
        total_gas += gas_cost_eth(blockchain_access, approve_tx)

    return SparkSavingsPlan(
        wallet=wallet,
        amount=amount,
        amount_wei=amount_wei,
        expected_susds=expected_susds,
        expected_susds_wei=expected_susds_wei,
        min_susds=min_susds,
        min_susds_wei=min_susds_wei,
        approval_needed=approval_needed,
        approve_tx=approve_tx,
        swap_tx=swap_tx,
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
    answer = input("Send Spark Savings transactions? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise SystemExit("Cancelled")


def print_preview(args, plan, psm_address):
    print("Mode: execute" if args.execute else "Mode: preview")
    print(f"Wallet: {plan.wallet}")
    print(f"Chain: {args.chain}")
    print(f"Spark PSM: {psm_address}")
    print(f"Deposit: {plan.amount} usds -> susds")
    print(f"Expected output: {plan.expected_susds} susds")
    print(f"Minimum output: {plan.min_susds} susds")
    print(f"Approval needed: {plan.approval_needed}")
    print(f"Estimated total gas cost: {plan.total_gas_cost_eth} ETH")


def main():
    load_dotenv()
    args = parse_args()

    BlockchainAccess.load_config(args.config)
    blockchain_access = BlockchainAccess(chain=args.chain, dry_run=not args.execute)
    private_key = load_private_key(args.private_key_env_var)
    wallet = Web3.to_checksum_address(wallet_from_private_key(private_key))
    psm_address = resolve_psm_address(args)
    plan = build_plan(blockchain_access, args, wallet)

    print_preview(args, plan, psm_address)

    if not args.execute:
        print("Preview only. Use --execute to actually send the Spark Savings deposit.")
        return

    maybe_confirm(args)

    approve_hash = None
    if plan.approve_tx is not None:
        approve_hash = sign_and_send(blockchain_access, plan.approve_tx, private_key)
        print(f"Approval tx sent: {approve_hash}")
        approval_receipt = wait_for_receipt(blockchain_access, approve_hash, args.receipt_timeout_seconds)
        if int(approval_receipt["status"]) != 1:
            raise RuntimeError(f"Approval transaction failed: {approve_hash}")

    final_nonce = blockchain_access.get_w3().eth.get_transaction_count(wallet)
    final_swap_tx = build_swap_tx(
        blockchain_access,
        wallet,
        psm_address,
        plan.amount_wei,
        plan.min_susds_wei,
        final_nonce,
    )
    swap_hash = sign_and_send(blockchain_access, final_swap_tx, private_key)
    print(f"Spark Savings tx sent: {swap_hash}")
    swap_receipt = wait_for_receipt(blockchain_access, swap_hash, args.receipt_timeout_seconds)
    metadata = {
        "chain": args.chain,
        "wallet": wallet,
        "amount_usds": str(plan.amount),
        "amount_wei": str(plan.amount_wei),
        "expected_susds": str(plan.expected_susds),
        "min_susds": str(plan.min_susds),
        "psm_address": psm_address,
        "approval_needed": plan.approval_needed,
        "approval_tx_hash": approve_hash,
        "spark_savings_tx_hash": swap_hash,
    }
    receipt_path = BlockchainAccess.save_receipt(
        args.receipt_dir,
        f"{args.chain}-spark-savings-usds-to-susds",
        swap_hash,
        swap_receipt,
        metadata,
    )
    print(f"Receipt saved: {receipt_path}")
    print(f"Receipt status: {swap_receipt['status']}")
    if int(swap_receipt["status"]) != 1:
        raise RuntimeError(f"Spark Savings transaction failed: {swap_hash}")


if __name__ == "__main__":
    main()
