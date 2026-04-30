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
        "pol": [("kyberswap", ["pol", "usdc"])],
        "dai": [("kyberswap", ["dai", "usdc"]), ("uniswap_v3", ["dai", "usdc"])],
        "usdc": [("kyberswap", ["usdc", "usdc"]), ("uniswap_v3", ["usdc"])],
        "weth": [
            ("kyberswap", ["weth", "usdc"]),
            ("uniswap_v3", ["weth", "usdc"]),
            ("quickswap_v2", ["weth", "usdc"]),
        ],
        "wmatic": [
            ("kyberswap", ["wmatic", "usdc"]),
            ("uniswap_v3", ["wmatic", "usdc"]),
            ("quickswap_v2", ["wmatic", "usdc"]),
        ],
        "wbtc": [
            ("kyberswap", ["wbtc", "usdc"]),
            ("uniswap_v3", ["wbtc", "weth", "usdc"]),
            ("quickswap_v2", ["wbtc", "weth", "usdc"]),
        ],
        "stmatic": [
            ("kyberswap", ["stmatic", "usdc"]),
            ("uniswap_v3", ["stmatic", "wmatic", "usdc"]),
            ("quickswap_v2", ["stmatic", "wmatic", "usdc"]),
        ],
        "bal": [
            ("kyberswap", ["bal", "usdc"]),
            ("quickswap_v2", ["bal", "wmatic", "usdc"]),
            ("uniswap_v3", ["bal", "usdc"]),
            ("uniswap_v3", ["bal", "weth", "usdc"]),
        ],
        "default": [
            ("kyberswap", ["{token}", "usdc"]),
            ("uniswap_v3", ["{token}", "usdc"]),
            ("uniswap_v3", ["{token}", "weth", "usdc"]),
            ("quickswap_v2", ["{token}", "wmatic", "usdc"]),
            ("quickswap_v2", ["{token}", "weth", "usdc"]),
            ("uniswap_v3", ["{token}", "wmatic", "usdc"]),
            ("quickswap_v2", ["{token}", "usdc"]),
            ("uniswap_v3", ["{token}", "dai", "usdc"]),
        ],
    },
    "optimism": {
        "eth": [("kyberswap", ["eth", "usdc"]), ("uniswap_v3", ["weth", "usdc"])],
        "dai": [("kyberswap", ["dai", "usdc"]), ("uniswap_v3", ["dai", "usdc"])],
        "usdc": [("kyberswap", ["usdc", "usdc"]), ("uniswap_v3", ["usdc"])],
        "weth": [("kyberswap", ["weth", "usdc"]), ("uniswap_v3", ["weth", "usdc"])],
        "op": [("kyberswap", ["op", "usdc"]), ("uniswap_v3", ["op", "weth", "usdc"])],
        "default": [
            ("kyberswap", ["{token}", "usdc"]),
            ("uniswap_v3", ["{token}", "usdc"]),
            ("uniswap_v3", ["{token}", "weth", "usdc"]),
            ("uniswap_v3", ["{token}", "dai", "usdc"]),
        ],
    },
    "ethereum": {
        "eth": [("kyberswap", ["eth", "usdc"])],
        "dai": [("kyberswap", ["dai", "usdc"]), ("uniswap_v3", ["dai", "usdc"])],
        "usdc": [("kyberswap", ["usdc", "usdc"]), ("uniswap_v3", ["usdc"])],
        "wbtc": [("kyberswap", ["wbtc", "usdc"])],
        "wsteth": [("kyberswap", ["wsteth", "usdc"])],
        "wtau": [("kyberswap", ["wtau", "usdc"])],
        "default": [
            ("kyberswap", ["{token}", "usdc"]),
            ("uniswap_v3", ["{token}", "usdc"]),
            ("uniswap_v3", ["{token}", "weth", "usdc"]),
            ("uniswap_v3", ["{token}", "dai", "usdc"]),
        ],
    },
    "arbitrum": {
        "eth": [("kyberswap", ["eth", "usdc"])],
        "usdc": [("kyberswap", ["usdc", "usdc"])],
        "default": [("kyberswap", ["{token}", "usdc"])],
    },
}

TRACKED_TOKENS = {
    "polygon": ["pol", "aave", "link", "ghst", "bal"],
    "optimism": ["eth", "velo"],
    "ethereum": ["eth", "dai", "wbtc", "glm", "wsteth", "wtau"],
    "arbitrum": ["eth"],
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
    if venue == "uniswap_v3":
        return blockchain_access.check_uniswap_price_path(path, input_quantity)
    if venue == "quickswap_v2":
        return blockchain_access.check_quickswap_v2_price_path(path, input_quantity)
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
