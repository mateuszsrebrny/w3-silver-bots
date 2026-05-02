from dotenv import load_dotenv
import os
from dataclasses import dataclass
from botweb3lib import BlockchainAccess

DEFAULT_CHAINS = ["polygon", "optimism", "ethereum", "arbitrum"]
DEFAULT_VALUE_TOKEN = "usdc"

TRACKED_TOKENS = {
    "polygon": ["pol", "aave", "link", "ghst", "bal"],
    "optimism": ["eth", "velo"],
    "ethereum": ["adai", "eth", "dai", "wbtc", "glm", "wsteth", "wtau"],
    "arbitrum": ["aarb", "eth"],
}


@dataclass(frozen=True)
class WalletSpec:
    label: str
    address: str


class TokenBalance:
    def __init__(
        self,
        blockchain_access,
        token_name,
        wallet,
        wallet_label=None,
        value_token=DEFAULT_VALUE_TOKEN,
    ):
        self._blockchain_access = blockchain_access
        self.token_name = token_name
        self.wallet = wallet
        self.wallet_label = wallet_label
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
        wallet_part = f" [{self.wallet_label}]" if self.wallet_label else ""
        return (
            f"{self.token_name} @ {self._blockchain_access.get_chain()}{wallet_part}: "
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
    wallets,
    dry_run=True,
    value_token=DEFAULT_VALUE_TOKEN,
    blockchain_access_cls=BlockchainAccess,
):
    token_balances = []
    wallet_specs = normalize_wallets(wallets)

    for wallet_spec in wallet_specs:
        for chain in chains:
            blockchain_access = blockchain_access_cls(chain, dry_run)
            tokens = TRACKED_TOKENS[chain]
            token_balances.extend(
                TokenBalance(
                    blockchain_access,
                    token,
                    wallet_spec.address,
                    wallet_label=wallet_spec.label,
                    value_token=value_token,
                )
                for token in tokens
            )

    return token_balances


def sort_balances(token_balances):
    token_balances.sort(reverse=True)
    return token_balances


def normalize_wallets(wallets):
    if isinstance(wallets, str):
        return [WalletSpec("wallet", wallets)]

    normalized = []
    for wallet in wallets:
        if isinstance(wallet, WalletSpec):
            normalized.append(wallet)
        else:
            normalized.append(WalletSpec("wallet", wallet))
    return normalized


def load_wallets_from_env():
    wallets = []
    seen = set()

    for label, env_var in [("external", "WALLET"), ("bot", "BOT_WALLET")]:
        address = os.getenv(env_var)
        if not address or address in seen:
            continue
        wallets.append(WalletSpec(label, address))
        seen.add(address)

    if not wallets:
        raise ValueError("No wallets configured. Set WALLET and optionally BOT_WALLET.")

    return wallets


def main():
    load_dotenv()
    wallets = load_wallets_from_env()
    dry_run = True

    for wallet in wallets:
        print(f"Wallet [{wallet.label}]: {wallet.address}")
    BlockchainAccess.load_config()

    token_balances = build_balances(DEFAULT_CHAINS, wallets, dry_run=dry_run)
    sort_balances(token_balances)
    print_balances(token_balances)


if __name__ == "__main__":
    main()
