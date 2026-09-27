#!/usr/bin/env python3

import argparse
from decimal import Decimal
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYTHON = sys.executable


def positive_decimal(value):
    amount = Decimal(str(value))
    if amount <= 0:
        raise argparse.ArgumentTypeError("amount must be greater than zero")
    return amount


def nonnegative_decimal(value):
    amount = Decimal(str(value))
    if amount < 0:
        raise argparse.ArgumentTypeError("amount must be zero or greater")
    return amount


def parse_args():
    parser = argparse.ArgumentParser(description="Run the weekly Arbitrum DCA sequence.")
    parser.add_argument(
        "--adai",
        type=nonnegative_decimal,
        default=Decimal("0"),
        help="Optional aDAI amount to withdraw to DAI before swapping. Defaults to 0.",
    )
    parser.add_argument("--wbtc", type=positive_decimal, required=True, help="DAI amount to swap into WBTC")
    parser.add_argument("--wsteth", type=positive_decimal, required=True, help="DAI amount to swap into wstETH")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview only. This is already the default unless --execute is set.",
    )
    parser.add_argument("--execute", action="store_true", help="Actually send the withdraw and swap transactions")
    parser.add_argument("--yes", action="store_true", help="Forward --yes to child scripts when executing")
    parser.add_argument("--python", default=DEFAULT_PYTHON, help="Python executable used to run child scripts")
    return parser.parse_args()


def build_commands(args):
    mode_flag = "--execute" if args.execute else "--preview"
    yes_flags = ["--yes"] if args.execute and args.yes else []

    commands = []
    if args.adai > 0:
        commands.append(
            [
                args.python,
                str(ROOT / "scripts" / "aave_withdraw.py"),
                "--token",
                "adai",
                "--amount",
                str(args.adai),
                mode_flag,
                *yes_flags,
            ]
        )

    wbtc_preview_balance = []
    wsteth_preview_balance = []
    if not args.execute and args.adai > 0:
        wbtc_preview_balance = ["--assume-input-balance", str(args.adai)]
        wsteth_preview_balance = ["--assume-input-balance", str(args.adai - args.wbtc)]

    commands.extend(
        [
            [
                args.python,
                str(ROOT / "scripts" / "trade.py"),
                "--from-token",
                "dai",
                "--to-token",
                "wbtc",
                "--amount",
                str(args.wbtc),
                mode_flag,
                *wbtc_preview_balance,
                *yes_flags,
            ],
            [
                args.python,
                str(ROOT / "scripts" / "trade.py"),
                "--from-token",
                "dai",
                "--to-token",
                "wsteth",
                "--amount",
                str(args.wsteth),
                mode_flag,
                *wsteth_preview_balance,
                *yes_flags,
            ],
        ]
    )
    return commands


def print_command(command):
    print("$ " + " ".join(command))


def run_commands(commands):
    for index, command in enumerate(commands, start=1):
        print(f"\nStep {index}/{len(commands)}")
        print_command(command)
        subprocess.run(command, cwd=ROOT, check=True)


def main():
    args = parse_args()
    print("Mode: execute" if args.execute else "Mode: preview")
    if args.adai > 0:
        print(f"Withdraw: {args.adai} adai -> dai")
    else:
        print("Withdraw: skipped")
    print(f"Swap: {args.wbtc} dai -> wbtc")
    print(f"Swap: {args.wsteth} dai -> wsteth")

    commands = build_commands(args)
    run_commands(commands)


if __name__ == "__main__":
    main()
