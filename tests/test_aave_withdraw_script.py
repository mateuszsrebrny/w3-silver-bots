from decimal import Decimal
import json
import sys

from scripts import aave_withdraw


def test_parse_args_accepts_all(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aave_withdraw.py",
            "--token",
            "adai",
            "--all",
        ],
    )

    args = aave_withdraw.parse_args()

    assert args.chain == "arbitrum"
    assert args.token == "adai"
    assert args.all is True
    assert args.execute is False


def test_build_withdraw_plan_uses_atoken_balance_for_all():
    class FakeWithdrawBuilder:
        @staticmethod
        def build_transaction(tx):
            return dict(tx)

    class FakePoolFunctions:
        @staticmethod
        def withdraw(asset, amount, recipient):
            return FakeWithdrawBuilder()

    class FakePoolContract:
        functions = FakePoolFunctions()

    class FakeEth:
        max_priority_fee = 10
        gas_price = 100

        @staticmethod
        def get_block(block_name):
            return {"baseFeePerGas": 100}

        @staticmethod
        def get_transaction_count(wallet):
            return 4

        @staticmethod
        def estimate_gas(tx):
            return 70000

        @staticmethod
        def contract(address, abi):
            return FakePoolContract()

    class FakeW3:
        eth = FakeEth()

    class FakeBlockchainAccess:
        def get_w3(self):
            return FakeW3()

        def get_chain_id(self):
            return 42161

        def get_decimals(self, token):
            return "ether"

        def check_balance_token(self, token, wallet):
            assert token == "adai"
            return Decimal("1.2345")

        def get_token_contract_address(self, token):
            return "0x00000000000000000000000000000000000000dA"

        @classmethod
        def my_toWei(cls, amount, unit):
            return int(Decimal(str(amount)) * Decimal(str(10**18)))

        @classmethod
        def my_fromWei(cls, amount_wei, unit):
            return Decimal(str(amount_wei)) / Decimal(str(10**18))

    class Args:
        chain = "arbitrum"
        token = "adai"
        amount = None
        all = True
        pool = None
        to = None

    wallet = "0x1111111111111111111111111111111111111111"
    plan = aave_withdraw.build_withdraw_plan(FakeBlockchainAccess(), Args(), wallet)

    assert plan.wallet == wallet
    assert plan.atoken == "adai"
    assert plan.underlying_token == "dai"
    assert plan.amount == Decimal("1.2345")
    assert plan.amount_wei == int(Decimal("1.2345") * Decimal(str(10**18)))
    assert plan.withdraw_tx["nonce"] == 4


def test_build_withdraw_plan_rejects_balance_overrun():
    class FakeEth:
        @staticmethod
        def get_transaction_count(wallet):
            return 0

    class FakeW3:
        eth = FakeEth()

    class FakeBlockchainAccess:
        def get_w3(self):
            return FakeW3()

        def check_balance_token(self, token, wallet):
            return Decimal("0.5")

        def get_decimals(self, token):
            return "ether"

        @classmethod
        def my_toWei(cls, amount, unit):
            return int(Decimal(str(amount)) * Decimal(str(10**18)))

    class Args:
        chain = "arbitrum"
        token = "adai"
        amount = "1"
        all = False
        pool = None
        to = None

    try:
        aave_withdraw.build_withdraw_plan(
            FakeBlockchainAccess(),
            Args(),
            "0x1111111111111111111111111111111111111111",
        )
    except ValueError as exc:
        assert "exceeds adai balance" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_print_preview_shows_full_atoken_balance(capsys):
    plan = aave_withdraw.WithdrawPlan(
        wallet="0xwallet",
        atoken="adai",
        underlying_token="dai",
        amount=Decimal("1.000000808292691565"),
        amount_wei=0,
        atoken_balance=Decimal("1.000000808292691565"),
        withdraw_tx={"nonce": 7},
        total_gas_cost_eth=Decimal("0.001"),
    )
    args = type("Args", (), {"execute": False, "chain": "arbitrum"})()

    aave_withdraw.print_preview(args, plan, "0xpool")

    output = capsys.readouterr().out
    assert "Withdraw: 1.000000808292691565 adai -> dai" in output
    assert "aToken balance: 1.000000808292691565 adai" in output


def test_main_execute_saves_receipt(monkeypatch, tmp_path, capsys):
    class FakeBlockchainAccess:
        def __init__(self, chain, dry_run):
            self.chain = chain
            self.dry_run = dry_run

        @classmethod
        def load_config(cls, config_path):
            return None

        @classmethod
        def save_receipt(cls, receipt_dir, filename_stem, tx_hash, receipt, metadata):
            path = tmp_path / f"{filename_stem}-{tx_hash[:10]}.json"
            path.write_text(json.dumps({"metadata": metadata, "receipt": receipt}))
            return path

    plan = aave_withdraw.WithdrawPlan(
        wallet="0xwallet",
        atoken="adai",
        underlying_token="dai",
        amount=Decimal("1"),
        amount_wei=123,
        atoken_balance=Decimal("2"),
        withdraw_tx={"nonce": 7},
        total_gas_cost_eth=Decimal("0.001"),
    )

    monkeypatch.setattr(aave_withdraw, "BlockchainAccess", FakeBlockchainAccess)
    monkeypatch.setattr(aave_withdraw, "load_private_key", lambda env_var: "0x" + "11" * 32)
    monkeypatch.setattr(aave_withdraw, "wallet_from_private_key", lambda private_key: "0xwallet")
    monkeypatch.setattr(aave_withdraw.Web3, "to_checksum_address", lambda address: address)
    monkeypatch.setattr(aave_withdraw, "build_withdraw_plan", lambda blockchain_access, args, wallet: plan)
    monkeypatch.setattr(aave_withdraw, "resolve_pool_address", lambda args: "0xpool")
    monkeypatch.setattr(aave_withdraw, "sign_and_send", lambda blockchain_access, tx, private_key: "0xwithdraw")
    monkeypatch.setattr(
        aave_withdraw,
        "wait_for_receipt",
        lambda blockchain_access, tx_hash, timeout_seconds: {"status": 1, "transactionHash": tx_hash},
    )
    monkeypatch.setattr(aave_withdraw, "maybe_confirm", lambda args: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aave_withdraw.py",
            "--token",
            "adai",
            "--amount",
            "1",
            "--execute",
            "--receipt-dir",
            str(tmp_path),
        ],
    )

    aave_withdraw.main()

    output = capsys.readouterr().out
    assert "Withdraw tx sent: 0xwithdraw" in output
    assert "Receipt saved:" in output
    receipt_files = list(tmp_path.glob("arbitrum-aave-withdraw-adai-0xwithdraw.json"))
    assert len(receipt_files) == 1
    payload = json.loads(receipt_files[0].read_text())
    assert payload["metadata"]["withdraw_tx_hash"] == "0xwithdraw"
    assert payload["metadata"]["underlying_token"] == "dai"
