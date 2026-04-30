from pathlib import Path

import pytest
import yaml

import portfolio_tracker


class FakeBlockchainAccess:
    def __init__(self, chain, dry_run):
        self._chain = chain
        self.dry_run = dry_run

    def get_chain(self):
        return self._chain

    def check_balance(self, tokens, wallet):
        return {tokens[0]: 7}

    def check_kyberswap_price(self, path, quantity):
        return quantity * 3


def test_token_balance_fetches_balance_and_value():
    token_balance = portfolio_tracker.TokenBalance(
        FakeBlockchainAccess("polygon", True),
        "bal",
        "0xwallet",
    )

    assert token_balance.balance == 7
    assert token_balance.value == 21
    assert str(token_balance) == "bal @ polygon: 7 = 21 usdc"


def test_token_balance_uses_requested_value_token():
    token_balance = portfolio_tracker.TokenBalance(
        FakeBlockchainAccess("polygon", True),
        "bal",
        "0xwallet",
        value_token="dai",
    )

    assert token_balance.value_token == "dai"
    assert token_balance.value == 21
    assert str(token_balance) == "bal @ polygon: 7 = 21 dai"


def test_sort_balances_orders_by_value_descending():
    low = portfolio_tracker.TokenBalance(FakeBlockchainAccess("polygon", True), "bal", "0xwallet")
    high = portfolio_tracker.TokenBalance(FakeBlockchainAccess("polygon", True), "aave", "0xwallet")
    low.value = 1
    high.value = 10
    balances = [low, high]

    portfolio_tracker.sort_balances(balances)

    assert balances == [high, low]


def test_build_balances_uses_tracked_tokens(monkeypatch):
    original_tracked = portfolio_tracker.TRACKED_TOKENS
    portfolio_tracker.TRACKED_TOKENS = {"polygon": ["bal", "aave"], "optimism": ["eth"]}

    try:
        balances = portfolio_tracker.build_balances(
            ["polygon", "optimism"],
            "0xwallet",
            dry_run=False,
            value_token="usd",
            blockchain_access_cls=FakeBlockchainAccess,
        )
    finally:
        portfolio_tracker.TRACKED_TOKENS = original_tracked

    assert [balance.token_name for balance in balances] == ["bal", "aave", "eth"]
    assert all(balance.value_token == "usd" for balance in balances)
    assert all(balance._blockchain_access.dry_run is False for balance in balances)


def test_all_tracked_tokens_exist_in_config():
    config_path = Path(__file__).resolve().parents[1] / "chains.config.yaml"
    config = yaml.safe_load(config_path.read_text())
    networks = config["networks"]

    for chain in portfolio_tracker.DEFAULT_CHAINS:
        assert chain in portfolio_tracker.TRACKED_TOKENS
        assert chain in networks

        configured_tokens = networks[chain]["contracts"]["erc20"]
        for token in portfolio_tracker.TRACKED_TOKENS[chain]:
            assert token in configured_tokens


def test_main_loads_runtime_and_prints(monkeypatch, capsys):
    monkeypatch.setenv("WALLET", "0xwallet")
    monkeypatch.setattr(portfolio_tracker, "DEFAULT_CHAINS", ["polygon"])
    monkeypatch.setattr(portfolio_tracker, "build_balances", lambda chains, wallet, dry_run=True, value_token="usdc", blockchain_access_cls=None: ["b2", "b1"])
    monkeypatch.setattr(portfolio_tracker, "sort_balances", lambda balances: balances.reverse())
    monkeypatch.setattr(portfolio_tracker, "print_balances", lambda balances: print(f"balances={balances}"))
    monkeypatch.setattr(portfolio_tracker, "load_dotenv", lambda: None)

    class FakeBlockchainAccessClass:
        @staticmethod
        def load_config():
            print("config_loaded")

    monkeypatch.setattr(portfolio_tracker, "BlockchainAccess", FakeBlockchainAccessClass)

    portfolio_tracker.main()

    captured = capsys.readouterr()
    assert "Wallet: 0xwallet" in captured.out
    assert "config_loaded" in captured.out
    assert "balances=['b1', 'b2']" in captured.out
