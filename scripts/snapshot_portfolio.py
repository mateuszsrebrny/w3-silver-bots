#!/usr/bin/env python3

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, UTC
from decimal import Decimal
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import portfolio_tracker


DEFAULT_OUTPUT_DIR = Path("data/portfolio_snapshots")
POSITION_HEADERS = [
    "timestamp_utc",
    "date",
    "wallet_label",
    "wallet_address",
    "chain",
    "token",
    "amount",
    "value_usdc",
    "interest_label",
    "interest_rate_pct",
]
SUMMARY_HEADERS = [
    "timestamp_utc",
    "date",
    "wallet_label",
    "wallet_address",
    "metric",
    "value",
    "unit",
]
STABLE_TOKENS = {"adai", "dai", "usdc", "usdt", "mai"}
BTC_TOKENS = {"wbtc"}
ETH_FAMILY_TOKENS = {"eth", "weth", "steth", "wsteth"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Write local-only historical portfolio snapshots for DCA bookkeeping and Grafana."
    )
    parser.add_argument(
        "--wallet",
        help="Track only this wallet address. If omitted, load WALLET and optionally BOT_WALLET from .env.",
    )
    parser.add_argument(
        "--chain",
        action="append",
        choices=portfolio_tracker.DEFAULT_CHAINS,
        help="Limit tracking to this chain. Repeat to query multiple chains.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for CSV/YAML snapshot files. Intended to stay gitignored.",
    )
    return parser.parse_args()


def _stringify_decimal(value):
    decimal_value = Decimal(str(value))
    if decimal_value == 0:
        return "0"
    return format(decimal_value, "f")


def _interest_fields(token_balance):
    if token_balance.interest_apr is None:
        return "", ""
    label, value = token_balance.interest_apr
    return label, _stringify_decimal(value)


def _token_value_usdc(blockchain_access, token_name, amount):
    is_beefy_vault_token = getattr(blockchain_access, "is_beefy_vault_token", None)
    if is_beefy_vault_token is not None and is_beefy_vault_token(token_name):
        return blockchain_access.get_beefy_vault_value(token_name, amount)

    is_beefy_priced_token = getattr(blockchain_access, "is_beefy_priced_token", None)
    if is_beefy_priced_token is not None and is_beefy_priced_token(token_name):
        return blockchain_access.get_beefy_token_value(token_name, amount)

    return blockchain_access.check_kyberswap_price([token_name, portfolio_tracker.DEFAULT_VALUE_TOKEN], amount)


def build_position_rows(token_balances, timestamp_utc, snapshot_date):
    rows = []
    for token_balance in token_balances:
        balance = Decimal(str(token_balance.balance))
        value = Decimal(str(token_balance.value))
        if balance == 0 and value == 0:
            continue
        label, rate = _interest_fields(token_balance)
        rows.append(
            {
                "timestamp_utc": timestamp_utc,
                "date": snapshot_date,
                "wallet_label": token_balance.wallet_label or "wallet",
                "wallet_address": token_balance.wallet,
                "chain": token_balance._blockchain_access.get_chain(),
                "token": token_balance.token_name,
                "amount": _stringify_decimal(balance),
                "value_usdc": _stringify_decimal(value),
                "interest_label": label,
                "interest_rate_pct": rate,
            }
        )
    return rows


def _sum_bucket(token_balances, token_names):
    total_amount = Decimal("0")
    total_value = Decimal("0")
    for token_balance in token_balances:
        get_underlying_amounts = getattr(
            token_balance._blockchain_access,
            "get_beefy_vault_underlying_amounts",
            None,
        )
        is_beefy_vault_token = getattr(
            token_balance._blockchain_access,
            "is_beefy_vault_token",
            None,
        )
        if (
            get_underlying_amounts is not None
            and is_beefy_vault_token is not None
            and is_beefy_vault_token(token_balance.token_name)
        ):
            underlying_amounts = get_underlying_amounts(token_balance.token_name, token_balance.balance)
            for underlying_token, underlying_amount in underlying_amounts.items():
                if underlying_token not in token_names:
                    continue
                total_amount += Decimal(str(underlying_amount))
                total_value += Decimal(
                    str(_token_value_usdc(token_balance._blockchain_access, underlying_token, underlying_amount))
                )
            continue

        if token_balance.token_name not in token_names:
            continue
        total_amount += Decimal(str(token_balance.balance))
        total_value += Decimal(str(token_balance.value))
    return total_amount, total_value


def build_summary_rows(token_balances, wallets, timestamp_utc, snapshot_date):
    chain_totals = portfolio_tracker.summarize_by_chain(token_balances)
    portfolio_total = portfolio_tracker.summarize_total(token_balances)
    stable_amount, stable_value = _sum_bucket(token_balances, STABLE_TOKENS)
    wbtc_amount, wbtc_value = _sum_bucket(token_balances, BTC_TOKENS)
    eth_amount, eth_value = _sum_bucket(token_balances, ETH_FAMILY_TOKENS)

    if len(wallets) == 1:
        wallet_label = wallets[0].label
        wallet_address = wallets[0].address
    else:
        wallet_label = "portfolio"
        wallet_address = "multiple"

    base = {
        "timestamp_utc": timestamp_utc,
        "date": snapshot_date,
        "wallet_label": wallet_label,
        "wallet_address": wallet_address,
    }
    rows = []
    rows.append({**base, "metric": "portfolio_total_usdc", "value": _stringify_decimal(portfolio_total), "unit": "usdc"})
    rows.append({**base, "metric": "stable_dai_family_amount", "value": _stringify_decimal(stable_amount), "unit": "tokens"})
    rows.append({**base, "metric": "stable_dai_family_usdc", "value": _stringify_decimal(stable_value), "unit": "usdc"})
    rows.append({**base, "metric": "wbtc_amount", "value": _stringify_decimal(wbtc_amount), "unit": "wbtc"})
    rows.append({**base, "metric": "wbtc_usdc", "value": _stringify_decimal(wbtc_value), "unit": "usdc"})
    rows.append({**base, "metric": "eth_family_amount", "value": _stringify_decimal(eth_amount), "unit": "eth_family"})
    rows.append({**base, "metric": "eth_family_usdc", "value": _stringify_decimal(eth_value), "unit": "usdc"})
    for chain, total in chain_totals.items():
        rows.append(
            {
                **base,
                "metric": f"chain_total_usdc_{chain}",
                "value": _stringify_decimal(total),
                "unit": "usdc",
            }
        )
    return rows


def write_csv_rows(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def write_latest_snapshot(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def build_latest_payload(timestamp_utc, snapshot_date, wallets, chains, token_balances, position_rows, summary_rows):
    return {
        "timestamp_utc": timestamp_utc,
        "date": snapshot_date,
        "wallets": [asdict(wallet) for wallet in wallets],
        "chains": chains,
        "positions": position_rows,
        "summary": summary_rows,
        "notes": [
            "Historical CSV files in this directory are intended to stay gitignored.",
            "eth_family_amount includes Beefy vault underlying token decomposition when available.",
            "stable_dai_family_amount sums token amounts across configured stable-like holdings for operational tracking.",
        ],
    }


def main():
    load_dotenv()
    args = parse_args()
    wallets = portfolio_tracker.load_wallets(wallet=args.wallet)
    chains = args.chain or portfolio_tracker.DEFAULT_CHAINS
    timestamp = datetime.now(UTC)
    timestamp_utc = timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot_date = timestamp.date().isoformat()

    portfolio_tracker.BlockchainAccess.load_config()
    token_balances = portfolio_tracker.build_balances(chains, wallets, dry_run=True)
    portfolio_tracker.sort_balances(token_balances)

    position_rows = build_position_rows(token_balances, timestamp_utc, snapshot_date)
    summary_rows = build_summary_rows(token_balances, wallets, timestamp_utc, snapshot_date)

    output_dir = Path(args.output_dir)
    write_csv_rows(output_dir / "positions.csv", POSITION_HEADERS, position_rows)
    write_csv_rows(output_dir / "summary.csv", SUMMARY_HEADERS, summary_rows)
    latest_payload = build_latest_payload(
        timestamp_utc,
        snapshot_date,
        wallets,
        chains,
        token_balances,
        position_rows,
        summary_rows,
    )
    write_latest_snapshot(output_dir / "latest.yaml", latest_payload)

    print(f"Wrote snapshot to {output_dir}")
    print(f"Positions: {len(position_rows)} rows -> {output_dir / 'positions.csv'}")
    print(f"Summary: {len(summary_rows)} rows -> {output_dir / 'summary.csv'}")
    print(f"Latest: {output_dir / 'latest.yaml'}")


if __name__ == "__main__":
    main()
