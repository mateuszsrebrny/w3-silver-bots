from decimal import Decimal
import sys

import yaml

import portfolio_tracker
from scripts import snapshot_portfolio


class FakeChainAccess:
    def __init__(self, chain):
        self._chain = chain

    def get_chain(self):
        return self._chain

    def is_beefy_vault_token(self, token):
        return False

    def is_beefy_priced_token(self, token):
        return False

    def check_kyberswap_price(self, path, amount):
        prices = {
            "eth": Decimal("2000"),
            "weth": Decimal("2000"),
            "wsteth": Decimal("2500"),
            "adai": Decimal("1"),
            "wbtc": Decimal("80000"),
        }
        return Decimal(str(amount)) * prices[path[0]]


class FakeTokenBalance:
    def __init__(
        self,
        chain,
        token_name,
        balance,
        value,
        wallet="0xwallet",
        wallet_label="wallet",
        interest_apr=None,
    ):
        self._blockchain_access = FakeChainAccess(chain)
        self.token_name = token_name
        self.balance = Decimal(str(balance))
        self.value = Decimal(str(value))
        self.wallet = wallet
        self.wallet_label = wallet_label
        self.interest_apr = interest_apr


class FakeVaultChainAccess(FakeChainAccess):
    def is_beefy_vault_token(self, token):
        return token == "moowstethweth"

    def get_beefy_vault_underlying_amounts(self, token, share_balance):
        assert token == "moowstethweth"
        assert Decimal(str(share_balance)) == Decimal("1.8")
        return {
            "weth": Decimal("0.9"),
            "wsteth": Decimal("0.7"),
        }


def test_build_position_rows_includes_interest_fields():
    balances = [
        FakeTokenBalance(
            "ethereum",
            "adai",
            "100",
            "100",
            interest_apr=("Aave supply APR", Decimal("2.96")),
        ),
        FakeTokenBalance("arbitrum", "wbtc", "0.1", "8000"),
    ]

    rows = snapshot_portfolio.build_position_rows(
        balances,
        "2026-05-16T10:00:00Z",
        "2026-05-16",
    )

    assert rows[0]["token"] == "adai"
    assert rows[0]["interest_label"] == "Aave supply APR"
    assert rows[0]["interest_rate_pct"] == "2.96"
    assert rows[1]["token"] == "wbtc"
    assert rows[1]["interest_label"] == ""


def test_build_position_rows_skips_zero_balance_and_zero_value():
    balances = [
        FakeTokenBalance("ethereum", "adai", "0", "0"),
        FakeTokenBalance("arbitrum", "wbtc", "0.1", "8000"),
    ]

    rows = snapshot_portfolio.build_position_rows(
        balances,
        "2026-05-16T10:00:00Z",
        "2026-05-16",
    )

    assert len(rows) == 1
    assert rows[0]["token"] == "wbtc"


def test_build_summary_rows_aggregates_buckets_and_chain_totals():
    balances = [
        FakeTokenBalance("ethereum", "adai", "100", "100"),
        FakeTokenBalance("arbitrum", "wbtc", "0.1", "8000"),
        FakeTokenBalance("optimism", "eth", "2", "4000"),
        FakeTokenBalance("optimism", "wsteth", "1", "2500"),
    ]
    wallets = [
        portfolio_tracker.WalletSpec("external", "0xexternal"),
        portfolio_tracker.WalletSpec("bot", "0xbot"),
    ]

    rows = snapshot_portfolio.build_summary_rows(
        balances,
        wallets,
        "2026-05-16T10:00:00Z",
        "2026-05-16",
    )
    by_metric = {row["metric"]: row for row in rows}

    assert by_metric["portfolio_total_usdc"]["value"] == "14600.000000"
    assert by_metric["stable_dai_family_amount"]["value"] == "100"
    assert by_metric["stable_dai_family_usdc"]["value"] == "100"
    assert by_metric["wbtc_amount"]["value"] == "0.1"
    assert by_metric["wbtc_usdc"]["value"] == "8000"
    assert by_metric["eth_family_amount"]["value"] == "3"
    assert by_metric["eth_family_usdc"]["value"] == "6500"
    assert by_metric["chain_total_usdc_optimism"]["value"] == "6500.000000"
    assert by_metric["portfolio_total_usdc"]["wallet_label"] == "portfolio"
    assert by_metric["portfolio_total_usdc"]["wallet_address"] == "multiple"


def test_main_writes_latest_yaml_and_csvs(tmp_path, monkeypatch, capsys):
    balances = [
        FakeTokenBalance("ethereum", "adai", "100", "100"),
        FakeTokenBalance("arbitrum", "wbtc", "0.1", "8000"),
        FakeTokenBalance("optimism", "eth", "2", "4000"),
    ]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "snapshot_portfolio.py",
            "--output-dir",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(snapshot_portfolio.portfolio_tracker, "load_wallets", lambda wallet=None: [portfolio_tracker.WalletSpec("wallet", "0xabc")])
    monkeypatch.setattr(snapshot_portfolio.portfolio_tracker.BlockchainAccess, "load_config", classmethod(lambda cls: None))
    monkeypatch.setattr(snapshot_portfolio.portfolio_tracker, "build_balances", lambda chains, wallets, dry_run=True: balances)
    monkeypatch.setattr(snapshot_portfolio.portfolio_tracker, "sort_balances", lambda token_balances: token_balances)

    snapshot_portfolio.main()

    latest_path = tmp_path / "latest.yaml"
    positions_path = tmp_path / "positions.csv"
    summary_path = tmp_path / "summary.csv"

    assert latest_path.exists()
    assert positions_path.exists()
    assert summary_path.exists()

    latest = yaml.safe_load(latest_path.read_text(encoding="utf-8"))
    assert latest["wallets"][0]["address"] == "0xabc"
    assert latest["positions"][0]["token"] == "adai"
    assert any(row["metric"] == "portfolio_total_usdc" for row in latest["summary"])

    output = capsys.readouterr().out
    assert "Wrote snapshot to" in output


def test_build_summary_rows_decomposes_beefy_vault_underlying():
    vault_balance = FakeTokenBalance("optimism", "moowstethweth", "1.8", "3950")
    vault_balance._blockchain_access = FakeVaultChainAccess("optimism")

    rows = snapshot_portfolio.build_summary_rows(
        [vault_balance],
        [portfolio_tracker.WalletSpec("wallet", "0xwallet")],
        "2026-05-16T10:00:00Z",
        "2026-05-16",
    )
    by_metric = {row["metric"]: row for row in rows}

    assert by_metric["eth_family_amount"]["value"] == "1.6"
    assert by_metric["eth_family_usdc"]["value"] == "3550.0"
