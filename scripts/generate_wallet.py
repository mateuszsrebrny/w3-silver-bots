#!/usr/bin/env python3

import argparse
from pathlib import Path
import sys

from eth_account import Account


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


Account.enable_unaudited_hdwallet_features()


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a recoverable EVM wallet.")
    parser.add_argument("--num-words", type=int, default=12, choices=[12, 15, 18, 21, 24])
    parser.add_argument("--passphrase", default="", help="Optional BIP-39 passphrase.")
    return parser.parse_args()


def generate_wallet(num_words=12, passphrase=""):
    account, mnemonic = Account.create_with_mnemonic(
        num_words=num_words,
        passphrase=passphrase,
    )
    return {
        "address": account.address,
        "private_key": "0x" + account.key.hex(),
        "mnemonic": mnemonic,
        "account_path": "m/44'/60'/0'/0/0",
    }


def main():
    args = parse_args()
    wallet = generate_wallet(num_words=args.num_words, passphrase=args.passphrase)
    print("Generated new recoverable wallet")
    print(f"Address: {wallet['address']}")
    print(f"Private key: {wallet['private_key']}")
    print(f"Mnemonic: {wallet['mnemonic']}")
    print(f"Account path: {wallet['account_path']}")
    print()
    print("Add this to your local .env file:")
    print(f"BOT_WALLET={wallet['address']}")
    print(f"BOT_PRIVATE_KEY={wallet['private_key']}")
    print()
    print("Back up the mnemonic offline.")
    print("Do not commit the private key or mnemonic.")


if __name__ == "__main__":
    main()
