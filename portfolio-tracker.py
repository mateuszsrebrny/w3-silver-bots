#!/usr/bin/python3

from dotenv import load_dotenv
import os
from botweb3lib import BlockchainAccess

# Load environment variables from the .env file
load_dotenv()

dry_run = True
wallet = os.getenv("WALLET")

print(f"Wallet: {wallet}")

# Load blockchain configuration
BlockchainAccess.load_config()


class TokenBalance:
    def __init__(self, blockchain_access, token_name, wallet):
        self._blockchain_access = blockchain_access
        self.token_name = token_name
        self.wallet = wallet
        self.balance = self._fetch_balance()

    def _fetch_balance(self):
        """Fetch the balance of the token for the given wallet."""
        return self._blockchain_access.check_balance([self.token_name], self.wallet)[self.token_name]

    def __str__(self):
        return f"{self.token_name} @ {self._blockchain_access.get_chain()}: {self.balance}"

    def __lt__(self, other):
        """Define sorting by balance value."""
        return self.balance < other.balance


balances = []

def print_balances(chain):
    for token_balance in balances:
        print(token_balance)


# Iterate over supported chains
for chain in ["polygon", "optimism"]:
    blockchain_access = BlockchainAccess(chain, dry_run)

    tokens = blockchain_access.get_all_tokens()

    balances += [TokenBalance(blockchain_access, token, wallet) for token in tokens]

balances.sort(reverse=True)

print_balances(chain)
