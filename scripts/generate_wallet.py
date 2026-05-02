#!/usr/bin/env python3

from pathlib import Path
import secrets
import sys

from eth_account import Account


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def generate_wallet():
    entropy = secrets.token_hex(32)
    account = Account.create(entropy)
    return {
        "address": account.address,
        "private_key": "0x" + account.key.hex(),
    }


def main():
    wallet = generate_wallet()
    print("Generated new wallet")
    print(f"Address: {wallet['address']}")
    print(f"Private key: {wallet['private_key']}")
    print()
    print("Add this to your local .env file:")
    print(f"BOT_WALLET={wallet['address']}")
    print(f"BOT_PRIVATE_KEY={wallet['private_key']}")
    print()
    print("Do not commit the private key.")


if __name__ == "__main__":
    main()
