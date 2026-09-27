import argparse
from decimal import Decimal
from dotenv import load_dotenv
import os
from dataclasses import dataclass
from botweb3lib import BlockchainAccess

DEFAULT_CHAINS = ["polygon", "optimism", "ethereum", "arbitrum"]
DEFAULT_VALUE_TOKEN = "usdc"

TRACKED_TOKENS = {
    "polygon": ["pol", "rcowwmaticldo", "aave", "link", "ghst", "bal"],
    "optimism": ["aop", "moowstethweth", "eth", "velo"],
    "ethereum": ["rbeqi", "adai", "eth", "dai", "usds", "susds", "wbtc", "glm", "wsteth", "wtao"],
    "arbitrum": ["adai", "aarb", "eth", "dai", "usds", "susds", "wbtc", "wsteth"],
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
        self.interest_apr = self._fetch_interest_apr()
        self.underlying_amount = self._fetch_underlying_amount()
        self.underlying_token = self._fetch_underlying_token()

    def _fetch_balance(self):
        """Fetch the balance of the token for the given wallet."""
        return self._blockchain_access.check_balance([self.token_name], self.wallet)[
            self.token_name
        ]

    def _fetch_value(self):
        is_beefy_vault_token = getattr(self._blockchain_access, "is_beefy_vault_token", None)
        if is_beefy_vault_token is not None and is_beefy_vault_token(self.token_name):
            return self._blockchain_access.get_beefy_vault_value(self.token_name, self.balance)
        is_beefy_priced_token = getattr(self._blockchain_access, "is_beefy_priced_token", None)
        if is_beefy_priced_token is not None and is_beefy_priced_token(self.token_name):
            return self._blockchain_access.get_beefy_token_value(self.token_name, self.balance)
        is_erc4626_token = getattr(self._blockchain_access, "is_erc4626_token", None)
        if is_erc4626_token is not None and is_erc4626_token(self.token_name):
            return self._blockchain_access.get_erc4626_token_value(
                self.token_name,
                self.balance,
                self.value_token,
            )
        is_spark_psm_token = getattr(self._blockchain_access, "is_spark_psm_token", None)
        if is_spark_psm_token is not None and is_spark_psm_token(self.token_name):
            return self._blockchain_access.get_spark_psm_token_value(
                self.token_name,
                self.balance,
                self.value_token,
            )
        return self._blockchain_access.check_kyberswap_price(
            [self.token_name, self.value_token],
            self.balance,
        )

    def _fetch_interest_apr(self):
        get_beefy_vault_apy = getattr(self._blockchain_access, "get_beefy_vault_apy", None)
        is_beefy_vault_token = getattr(self._blockchain_access, "is_beefy_vault_token", None)
        if (
            get_beefy_vault_apy is not None
            and is_beefy_vault_token is not None
            and is_beefy_vault_token(self.token_name)
        ):
            try:
                apy = get_beefy_vault_apy(self.token_name)
                if apy is not None:
                    return ("Beefy APY", apy)
            except Exception:
                return None

        get_beefy_token_apr = getattr(self._blockchain_access, "get_beefy_token_apr", None)
        get_beefy_token_interest_label = getattr(
            self._blockchain_access,
            "get_beefy_token_interest_label",
            None,
        )
        is_beefy_priced_token = getattr(self._blockchain_access, "is_beefy_priced_token", None)
        if (
            get_beefy_token_apr is not None
            and is_beefy_priced_token is not None
            and is_beefy_priced_token(self.token_name)
        ):
            try:
                apr = get_beefy_token_apr(self.token_name)
                if apr is not None:
                    label = "Beefy APR"
                    if get_beefy_token_interest_label is not None:
                        label = get_beefy_token_interest_label(self.token_name)
                    return (label, apr)
            except Exception:
                return None

        get_aave_supply_apr = getattr(self._blockchain_access, "get_aave_supply_apr", None)
        get_defillama_yield_apr = getattr(self._blockchain_access, "get_defillama_yield_apr", None)
        get_defillama_yield_label = getattr(self._blockchain_access, "get_defillama_yield_label", None)
        has_defillama_yield_apr = getattr(self._blockchain_access, "has_defillama_yield_apr", None)
        if (
            get_defillama_yield_apr is not None
            and has_defillama_yield_apr is not None
            and has_defillama_yield_apr(self.token_name)
        ):
            try:
                apr = get_defillama_yield_apr(self.token_name)
                if apr is not None:
                    label = "DeFiLlama APY"
                    if get_defillama_yield_label is not None:
                        label = get_defillama_yield_label(self.token_name)
                    return (label, apr)
            except Exception:
                return None

        if get_aave_supply_apr is None:
            return None

        try:
            apr = get_aave_supply_apr(self.token_name)
            if apr is None:
                return None
            return ("Aave supply APR", apr)
        except Exception:
            return None

    def _fetch_underlying_amount(self):
        is_erc4626_token = getattr(self._blockchain_access, "is_erc4626_token", None)
        get_erc4626_underlying_amount = getattr(
            self._blockchain_access,
            "get_erc4626_underlying_amount",
            None,
        )
        if (
            is_erc4626_token is not None
            and get_erc4626_underlying_amount is not None
            and is_erc4626_token(self.token_name)
        ):
            try:
                return get_erc4626_underlying_amount(self.token_name, self.balance)
            except Exception:
                return None

        is_spark_psm_token = getattr(self._blockchain_access, "is_spark_psm_token", None)
        get_spark_psm_underlying_amount = getattr(
            self._blockchain_access,
            "get_spark_psm_underlying_amount",
            None,
        )
        if (
            is_spark_psm_token is not None
            and get_spark_psm_underlying_amount is not None
            and is_spark_psm_token(self.token_name)
        ):
            try:
                return get_spark_psm_underlying_amount(self.token_name, self.balance)
            except Exception:
                return None

        return None

    def _fetch_underlying_token(self):
        if self.underlying_amount is None:
            return None

        get_erc4626_underlying_token = getattr(
            self._blockchain_access,
            "get_erc4626_underlying_token",
            None,
        )
        is_erc4626_token = getattr(self._blockchain_access, "is_erc4626_token", None)
        if (
            is_erc4626_token is not None
            and get_erc4626_underlying_token is not None
            and is_erc4626_token(self.token_name)
        ):
            try:
                return get_erc4626_underlying_token(self.token_name)
            except Exception:
                return None

        get_spark_psm_underlying_token = getattr(
            self._blockchain_access,
            "get_spark_psm_underlying_token",
            None,
        )
        is_spark_psm_token = getattr(self._blockchain_access, "is_spark_psm_token", None)
        if (
            is_spark_psm_token is not None
            and get_spark_psm_underlying_token is not None
            and is_spark_psm_token(self.token_name)
        ):
            try:
                return get_spark_psm_underlying_token(self.token_name)
            except Exception:
                return None

        return None

    def _underlying_suffix(self):
        if (
            self.underlying_amount is None
            or self.underlying_token is None
            or Decimal(str(self.balance)) == 0
        ):
            return ""
        return f" (underlying: {self.underlying_amount} {self.underlying_token})"

    def _interest_suffix(self):
        if self.interest_apr is None or Decimal(str(self.balance)) == 0:
            return ""
        label, value = self.interest_apr
        return f" ({label}: {value.quantize(Decimal('0.01'))}%)"

    def _display_value(self):
        value = Decimal(str(self.value))
        if value == 0:
            return "0"
        return str(value.normalize()) if value == value.normalize() else str(value)

    def __str__(self):
        wallet_part = f" [{self.wallet_label}]" if self.wallet_label else ""
        return (
            f"{self.token_name} @ {self._blockchain_access.get_chain()}{wallet_part}: "
            f"{self.balance} = {self._display_value()} {self.value_token}"
            f"{self._underlying_suffix()}{self._interest_suffix()}"
        )

    def __lt__(self, other):
        if self.value_token == other.value_token:
            return self.value < other.value
        return self.balance < other.balance


def print_balances(token_balances):
    for token_balance in token_balances:
        print(token_balance)


def summarize_by_chain(token_balances, value_token=DEFAULT_VALUE_TOKEN):
    summaries = {}
    for token_balance in token_balances:
        chain = token_balance._blockchain_access.get_chain()
        summaries.setdefault(chain, Decimal("0"))
        summaries[chain] += Decimal(str(token_balance.value))
    return {
        chain: total.quantize(Decimal("0.000001"))
        for chain, total in summaries.items()
    }


def summarize_total(token_balances):
    total = Decimal("0")
    for token_balance in token_balances:
        total += Decimal(str(token_balance.value))
    return total.quantize(Decimal("0.000001"))


def print_summaries(token_balances, value_token=DEFAULT_VALUE_TOKEN):
    chain_summaries = summarize_by_chain(token_balances, value_token=value_token)
    for chain, total in chain_summaries.items():
        print(f"Total @ {chain}: {total} {value_token}")
    print(f"Total @ portfolio: {summarize_total(token_balances)} {value_token}")


def parse_args():
    parser = argparse.ArgumentParser(description="Track portfolio balances across configured chains.")
    parser.add_argument(
        "--wallet",
        help="Track only this wallet address. If omitted, load WALLET and optionally BOT_WALLET from .env.",
    )
    parser.add_argument(
        "--chain",
        action="append",
        choices=DEFAULT_CHAINS,
        help="Limit tracking to this chain. Repeat the flag to query multiple chains.",
    )
    return parser.parse_args()


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


def load_wallets(wallet=None):
    if wallet:
        return [WalletSpec("wallet", wallet)]
    return load_wallets_from_env()


def main():
    load_dotenv()
    args = parse_args()
    wallets = load_wallets(wallet=args.wallet)
    chains = args.chain or DEFAULT_CHAINS
    dry_run = True

    for wallet in wallets:
        print(f"Wallet [{wallet.label}]: {wallet.address}")
    BlockchainAccess.load_config()

    token_balances = build_balances(chains, wallets, dry_run=dry_run)
    sort_balances(token_balances)
    print_balances(token_balances)
    print_summaries(token_balances)


if __name__ == "__main__":
    main()
