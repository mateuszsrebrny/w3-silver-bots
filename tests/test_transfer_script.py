from decimal import Decimal
import json
import os
import sys

import pytest

from scripts import transfer


def test_parse_args_accepts_send_all(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transfer.py",
            "--token",
            "eth",
            "--all",
        ],
    )

    args = transfer.parse_args()

    assert args.chain == "arbitrum"
    assert args.token == "eth"
    assert args.all is True
    assert args.amount is None


def test_parse_args_accepts_preview_flag(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transfer.py",
            "--token",
            "eth",
            "--all",
            "--preview",
        ],
    )

    args = transfer.parse_args()

    assert args.preview is True
    assert args.execute is False


def test_parse_args_accepts_gas_buffer_bps(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transfer.py",
            "--token",
            "eth",
            "--all",
            "--gas-buffer-bps",
            "250",
        ],
    )

    args = transfer.parse_args()

    assert args.gas_buffer_bps == 250


def test_build_native_transfer_plan_send_all_reserves_gas():
    estimated_gas_values = []

    class FakeW3:
        class eth:
            max_priority_fee = 10

            @staticmethod
            def get_balance(address):
                return 5_000_000

            @staticmethod
            def get_transaction_count(address):
                return 7

            @staticmethod
            def estimate_gas(tx):
                estimated_gas_values.append(tx["value"])
                return 21_000

            @staticmethod
            def get_block(block_name):
                assert block_name == "latest"
                return {"baseFeePerGas": 100}

    class FakeBlockchainAccess:
        def get_w3(self):
            return FakeW3()

        def get_chain_id(self):
            return 42161

        def get_decimals(self, token):
            return "lovelace" if token == "btc" else "wei"

        def is_native_token(self, token):
            return token == "eth"

        @classmethod
        def my_fromWei(cls, amount_wei, unit):
            return Decimal(str(amount_wei))

    plan = transfer.build_native_transfer_plan(
        FakeBlockchainAccess(),
        "eth",
        "0xsender",
        "0xrecipient",
        send_all=True,
    )

    assert estimated_gas_values == [0, 5_000_000 - (21_000 * 210)]
    assert plan.amount_wei == 5_000_000 - (21_000 * 210)
    assert plan.tx["value"] == plan.amount_wei
    assert plan.gas_limit == 21_000
    assert plan.gas_price_wei == 210
    assert plan.tx["maxFeePerGas"] == 210
    assert plan.tx["maxPriorityFeePerGas"] == 10
    assert plan.tx["type"] == 2
    assert plan.gas_cost_native == Decimal(str(21_000 * 210))


def test_build_erc20_transfer_plan_send_all_uses_full_token_balance():
    class FakeCall:
        def __init__(self, value):
            self._value = value

        def call(self):
            return self._value

    class FakeTransferBuilder:
        @staticmethod
        def build_transaction(tx):
            return dict(tx)

    class FakeFunctions:
        @staticmethod
        def balanceOf(address):
            return FakeCall(12345)

        @staticmethod
        def transfer(recipient, amount_wei):
            assert recipient == "0xrecipient"
            assert amount_wei == 12345
            return FakeTransferBuilder()

    class FakeContract:
        functions = FakeFunctions()

    class FakeW3:
        class eth:
            max_priority_fee = 5

            @staticmethod
            def get_balance(address):
                return 999

            @staticmethod
            def get_transaction_count(address):
                return 3

            @staticmethod
            def estimate_gas(tx):
                return 55_000

            @staticmethod
            def get_block(block_name):
                assert block_name == "latest"
                return {"baseFeePerGas": 50}

    class FakeBlockchainAccess:
        def get_w3(self):
            return FakeW3()

        def get_chain_id(self):
            return 42161

        def get_token_contract(self, token):
            assert token == "dai"
            return FakeContract()

        def get_decimals(self, token):
            return "wei"

        def is_native_token(self, token):
            return False

        @classmethod
        def my_fromWei(cls, amount_wei, unit):
            return Decimal(str(amount_wei))

        @classmethod
        def my_toWei(cls, amount, unit):
            return int(Decimal(str(amount)))

    plan = transfer.build_erc20_transfer_plan(
        FakeBlockchainAccess(),
        "dai",
        "0xsender",
        "0xrecipient",
        send_all=True,
    )

    assert plan.amount_wei == 12345
    assert plan.amount == Decimal("12345")
    assert plan.tx["gas"] == 55_000
    assert plan.tx["maxFeePerGas"] == 105
    assert plan.tx["maxPriorityFeePerGas"] == 5
    assert plan.tx["type"] == 2
    assert plan.gas_cost_native == Decimal(str(55_000 * 105))


def test_save_receipt_writes_json(tmp_path):
    receipt = {"status": 1, "transactionHash": b"\xaa\xbb"}
    metadata = {"token": "eth", "tx_hash": "0xabc"}

    path = transfer.BlockchainAccess.save_receipt(
        tmp_path,
        "arbitrum-eth",
        "0xabc123",
        receipt,
        metadata,
    )

    payload = json.loads(path.read_text())

    assert payload["metadata"]["token"] == "eth"
    assert payload["receipt"]["transactionHash"] == "0xaabb"
    assert payload["receipt"]["status"] == 1


def test_load_recipient_requires_cli_or_env(monkeypatch):
    class Args:
        to = None
        to_env_var = "WALLET"

    monkeypatch.delenv("WALLET", raising=False)

    with pytest.raises(ValueError, match="Recipient not provided"):
        transfer.load_recipient(Args())


def test_main_rejects_sender_matching_recipient(monkeypatch):
    class FakeBlockchainAccess:
        def __init__(self, chain, dry_run):
            self.chain = chain
            self.dry_run = dry_run

        @classmethod
        def load_config(cls, config_path):
            return None

    monkeypatch.setattr(transfer, "BlockchainAccess", FakeBlockchainAccess)
    monkeypatch.setattr(transfer, "load_private_key", lambda env_var: "0x" + "11" * 32)
    monkeypatch.setattr(transfer, "wallet_from_private_key", lambda private_key: "0xsame")
    monkeypatch.setattr(transfer.Web3, "to_checksum_address", lambda address: address)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transfer.py",
            "--token",
            "eth",
            "--all",
            "--to",
            "0xsame",
        ],
    )

    with pytest.raises(ValueError, match="Sender and recipient must be different"):
        transfer.main()


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

    class FakeEth:
        @staticmethod
        def wait_for_transaction_receipt(tx_hash, timeout):
            assert tx_hash == "0xabc"
            assert timeout == 180
            return {"status": 1, "transactionHash": tx_hash}

    class FakeW3:
        eth = FakeEth()

    plan = transfer.TransferPlan(
        tx={"nonce": 1},
        token="eth",
        amount=Decimal("0.1"),
        amount_wei=100,
        gas_limit=21000,
        gas_price_wei=200,
        gas_cost_native=Decimal("0.0000042"),
        balance_before_native=Decimal("1.0"),
    )

    monkeypatch.setattr(transfer, "BlockchainAccess", FakeBlockchainAccess)
    monkeypatch.setattr(transfer, "load_private_key", lambda env_var: "0x" + "11" * 32)
    monkeypatch.setattr(transfer, "wallet_from_private_key", lambda private_key: "0xsender")
    monkeypatch.setattr(transfer.Web3, "to_checksum_address", lambda address: address)
    monkeypatch.setattr(transfer, "build_transfer_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(transfer, "sign_and_send", lambda blockchain_access, tx, private_key: "0xabc")
    monkeypatch.setattr(transfer, "maybe_confirm", lambda args: None)
    monkeypatch.setattr(
        FakeBlockchainAccess,
        "get_w3",
        lambda self: FakeW3(),
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transfer.py",
            "--token",
            "eth",
            "--amount",
            "0.1",
            "--to",
            "0xrecipient",
            "--execute",
            "--receipt-dir",
            str(tmp_path),
        ],
    )

    transfer.main()

    output = capsys.readouterr().out
    assert "Transfer tx sent: 0xabc" in output
    assert "Receipt saved:" in output
    assert "Receipt status: 1" in output
    receipt_files = list(tmp_path.glob("arbitrum-eth-0xabc.json"))
    assert len(receipt_files) == 1
    payload = json.loads(receipt_files[0].read_text())
    assert payload["metadata"]["sender"] == "0xsender"
    assert payload["metadata"]["recipient"] == "0xrecipient"
    assert payload["metadata"]["tx_hash"] == "0xabc"


def test_main_execute_raises_on_failed_receipt(monkeypatch, tmp_path):
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

    class FakeEth:
        @staticmethod
        def wait_for_transaction_receipt(tx_hash, timeout):
            return {"status": 0, "transactionHash": tx_hash}

    class FakeW3:
        eth = FakeEth()

    plan = transfer.TransferPlan(
        tx={"nonce": 1},
        token="eth",
        amount=Decimal("0.1"),
        amount_wei=100,
        gas_limit=21000,
        gas_price_wei=200,
        gas_cost_native=Decimal("0.0000042"),
        balance_before_native=Decimal("1.0"),
    )

    monkeypatch.setattr(transfer, "BlockchainAccess", FakeBlockchainAccess)
    monkeypatch.setattr(transfer, "load_private_key", lambda env_var: "0x" + "11" * 32)
    monkeypatch.setattr(transfer, "wallet_from_private_key", lambda private_key: "0xsender")
    monkeypatch.setattr(transfer.Web3, "to_checksum_address", lambda address: address)
    monkeypatch.setattr(transfer, "build_transfer_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(transfer, "sign_and_send", lambda blockchain_access, tx, private_key: "0xabc")
    monkeypatch.setattr(transfer, "maybe_confirm", lambda args: None)
    monkeypatch.setattr(
        FakeBlockchainAccess,
        "get_w3",
        lambda self: FakeW3(),
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "transfer.py",
            "--token",
            "eth",
            "--amount",
            "0.1",
            "--to",
            "0xrecipient",
            "--execute",
            "--receipt-dir",
            str(tmp_path),
        ],
    )

    with pytest.raises(RuntimeError, match="Transfer transaction failed"):
        transfer.main()
