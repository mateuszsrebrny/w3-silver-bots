#!/usr/bin/python3

from dotenv import load_dotenv
import os
from botweb3lib import BlockchainAccess

# Load environment variables from the .env file
load_dotenv()

dry_run = True
wallet = os.getenv("WALLET")
value_token = "usdc"

print(f"Wallet: {wallet}")

# Load blockchain configuration
BlockchainAccess.load_config()


VALUE_PATHS = {
    "polygon": {
        "default": [("kyberswap", ["{token}", "usdc"])],
    },
    "optimism": {
        "default": [("kyberswap", ["{token}", "usdc"])],
    },
    "ethereum": {
        "default": [("kyberswap", ["{token}", "usdc"])],
    },
    "arbitrum": {
        "default": [("kyberswap", ["{token}", "usdc"])],
    },
}

TRACKED_TOKENS = {
    "polygon": ["pol", "aave", "link", "ghst", "bal"],
    "optimism": ["eth", "velo"],
    "ethereum": ["adai", "eth", "dai", "wbtc", "glm", "wsteth", "wtau"],
    "arbitrum": ["aarb", "eth"],
}


def get_value_paths(chain, token_name):
    chain_paths = VALUE_PATHS[chain]
    template_paths = chain_paths.get(token_name, chain_paths["default"])
    return [
        (venue, [step.format(token=token_name) for step in path])
        for venue, path in template_paths
    ]


def quote_path(blockchain_access, venue, path, input_quantity):
    if venue == "kyberswap":
        if len(path) != 2:
            return 0
        return blockchain_access.check_kyberswap_price(path, input_quantity)
    raise ValueError(f"Unknown venue: {venue}")


class TokenBalance:
    def __init__(self, blockchain_access, token_name, wallet, value_token=value_token):
        self._blockchain_access = blockchain_access
        self.token_name = token_name
        self.wallet = wallet
        self.value_token = value_token
        self.balance = self._fetch_balance()
        self.value = self._fetch_value()

    def _fetch_balance(self):
        """Fetch the balance of the token for the given wallet."""
        return self._blockchain_access.check_balance([self.token_name], self.wallet)[self.token_name]

    def _fetch_value(self):
        candidate_paths = get_value_paths(
            self._blockchain_access.get_chain(), self.token_name
        )

        for venue, path in candidate_paths:
            value = quote_path(self._blockchain_access, venue, path, self.balance)
            if value > 0 or len(path) == 1:
                return value

        return 0


    def __str__(self):
        return (
            f"{self.token_name} @ {self._blockchain_access.get_chain()}: "
            f"{self.balance} = {self.value} {self.value_token}"
        )

    def __lt__(self, other):
        if self.value_token == other.value_token:
            return self.value < other.value
        return self.balance < other.balance


balances = []

def print_balances(chain):
    for token_balance in balances:
        print(token_balance)


# Iterate over supported chains
for chain in ["polygon", "optimism", "ethereum", "arbitrum"]:
    blockchain_access = BlockchainAccess(chain, dry_run)

    tokens = TRACKED_TOKENS[chain]

    balances += [TokenBalance(blockchain_access, token, wallet) for token in tokens]

balances.sort(reverse=True)

print_balances(chain)
