from dotenv import load_dotenv
import os
from botweb3lib import BlockchainAccess

DEFAULT_CHAINS = ["polygon", "optimism", "ethereum", "arbitrum"]
DEFAULT_VALUE_TOKEN = "usdc"

TRACKED_TOKENS = {
    "polygon": ["pol", "aave", "link", "ghst", "bal"],
    "optimism": ["eth", "velo"],
    "ethereum": ["adai", "eth", "dai", "wbtc", "glm", "wsteth", "wtau"],
    "arbitrum": ["aarb", "eth"],
}


class TokenBalance:
    def __init__(
        self,
        blockchain_access,
        token_name,
        wallet,
        value_token=DEFAULT_VALUE_TOKEN,
    ):
        self._blockchain_access = blockchain_access
        self.token_name = token_name
        self.wallet = wallet
        self.value_token = value_token
        self.balance = self._fetch_balance()
        self.value = self._fetch_value()

    def _fetch_balance(self):
        """Fetch the balance of the token for the given wallet."""
        return self._blockchain_access.check_balance([self.token_name], self.wallet)[
            self.token_name
        ]

    def _fetch_value(self):
        return self._blockchain_access.check_kyberswap_price(
            [self.token_name, self.value_token],
            self.balance,
        )

    def __str__(self):
        return (
            f"{self.token_name} @ {self._blockchain_access.get_chain()}: "
            f"{self.balance} = {self.value} {self.value_token}"
        )

    def __lt__(self, other):
        if self.value_token == other.value_token:
            return self.value < other.value
        return self.balance < other.balance


def print_balances(token_balances):
    for token_balance in token_balances:
        print(token_balance)


def build_balances(
    chains,
    wallet,
    dry_run=True,
    value_token=DEFAULT_VALUE_TOKEN,
    blockchain_access_cls=BlockchainAccess,
):
    token_balances = []

    for chain in chains:
        blockchain_access = blockchain_access_cls(chain, dry_run)
        tokens = TRACKED_TOKENS[chain]
        token_balances.extend(
            TokenBalance(blockchain_access, token, wallet, value_token=value_token)
            for token in tokens
        )

    return token_balances


def sort_balances(token_balances):
    token_balances.sort(reverse=True)
    return token_balances


def main():
    load_dotenv()
    wallet = os.getenv("WALLET")
    dry_run = True

    print(f"Wallet: {wallet}")
    BlockchainAccess.load_config()

    token_balances = build_balances(DEFAULT_CHAINS, wallet, dry_run=dry_run)
    sort_balances(token_balances)
    print_balances(token_balances)


if __name__ == "__main__":
    main()
