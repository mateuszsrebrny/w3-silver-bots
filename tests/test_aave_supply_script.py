from decimal import Decimal
import json
import sys

from scripts import aave_supply


def test_parse_args_accepts_amount(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aave_supply.py",
            "--token",
            "dai",
            "--amount",
            "100",
        ],
    )

    args = aave_supply.parse_args()

    assert args.chain == "arbitrum"
    assert args.token == "dai"
    assert args.amount == "100"
    assert args.execute is False


def test_build_supply_plan_erc20_uses_approval_when_allowance_low():
    class FakeCall:
        def __init__(self, value):
            self.value = value

        def call(self):
            return self.value

    class FakeApproveBuilder:
        @staticmethod
        def build_transaction(tx):
            return dict(tx)

    class FakeSupplyBuilder:
        @staticmethod
        def build_transaction(tx):
            return dict(tx)

    class FakeTokenFunctions:
        @staticmethod
        def approve(spender, amount):
            return FakeApproveBuilder()

    class FakePoolFunctions:
        @staticmethod
        def supply(asset, amount, on_behalf_of, referral_code):
            return FakeSupplyBuilder()

    class FakeContract:
        functions = FakeTokenFunctions()

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
            return 5

        @staticmethod
        def estimate_gas(tx):
            return 50000

        @staticmethod
        def contract(address, abi):
            return FakePoolContract()

    class FakeW3:
        eth = FakeEth()

    class FakeBlockchainAccess:
        def get_chain(self):
            return "arbitrum"

        def get_w3(self):
            return FakeW3()

        def get_chain_id(self):
            return 42161

        def get_decimals(self, token):
            return "ether"

        def get_token_contract(self, token):
            return FakeContract()

        def get_token_contract_address(self, token):
            return {
                "dai": "0x00000000000000000000000000000000000000dA",
                "weth": "0x00000000000000000000000000000000000000eF",
            }[token]

        def check_allowance(self, token, owner, spender):
            return Decimal("0")

        def check_balance_token(self, token, wallet):
            return Decimal("250")

        @classmethod
        def my_toWei(cls, amount, unit):
            return int(Decimal(str(amount)) * Decimal(str(10**18)))

        @classmethod
        def my_fromWei(cls, amount_wei, unit):
            return Decimal(str(amount_wei)) / Decimal(str(10**18))

    class Args:
        chain = "arbitrum"
        token = "dai"
        amount = "100"
        all = False
        pool = None

    plan = aave_supply.build_supply_plan(FakeBlockchainAccess(), Args(), "0xwallet")

    assert plan.display_token == "dai"
    assert plan.pool_token == "dai"
    assert plan.wrap_tx is None
    assert plan.approval_needed is True
    assert plan.approve_tx["nonce"] == 5
    assert plan.supply_tx["nonce"] == 6


def test_build_supply_plan_eth_adds_wrap_step():
    class FakeApproveBuilder:
        @staticmethod
        def build_transaction(tx):
            return dict(tx)

    class FakeDepositBuilder:
        @staticmethod
        def build_transaction(tx):
            return dict(tx)

    class FakeSupplyBuilder:
        @staticmethod
        def build_transaction(tx):
            return dict(tx)

    class FakeWethFunctions:
        @staticmethod
        def approve(spender, amount):
            return FakeApproveBuilder()

        @staticmethod
        def deposit():
            return FakeDepositBuilder()

    class FakePoolFunctions:
        @staticmethod
        def supply(asset, amount, on_behalf_of, referral_code):
            return FakeSupplyBuilder()

    class FakeTokenContract:
        functions = FakeWethFunctions()

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
            return 8

        @staticmethod
        def estimate_gas(tx):
            return 40000

        @staticmethod
        def contract(address, abi):
            if abi == aave_supply.WETH_ABI:
                return FakeTokenContract()
            return FakePoolContract()

    class FakeW3:
        eth = FakeEth()

    class FakeBlockchainAccess:
        def get_chain(self):
            return "arbitrum"

        def get_w3(self):
            return FakeW3()

        def get_chain_id(self):
            return 42161

        def get_decimals(self, token):
            return "ether"

        def get_token_contract(self, token):
            return FakeTokenContract()

        def get_token_contract_address(self, token):
            return {"weth": "0x00000000000000000000000000000000000000eF"}[token]

        def check_allowance(self, token, owner, spender):
            return Decimal("0")

        @classmethod
        def my_toWei(cls, amount, unit):
            return int(Decimal(str(amount)) * Decimal(str(10**18)))

        @classmethod
        def my_fromWei(cls, amount_wei, unit):
            return Decimal(str(amount_wei)) / Decimal(str(10**18))

    class Args:
        chain = "arbitrum"
        token = "eth"
        amount = "0.5"
        all = False
        pool = None

    plan = aave_supply.build_supply_plan(FakeBlockchainAccess(), Args(), "0xwallet")

    assert plan.display_token == "eth"
    assert plan.pool_token == "weth"
    assert plan.wrap_tx is not None
    assert plan.approve_tx is not None
    assert plan.wrap_tx["nonce"] == 8
    assert plan.approve_tx["nonce"] == 9
    assert plan.supply_tx["nonce"] == 10


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

        def get_w3(self):
            class FakeEth:
                @staticmethod
                def get_transaction_count(wallet):
                    return 6

            class FakeW3:
                eth = FakeEth()

            return FakeW3()

        def get_token_contract_address(self, token):
            return "0x00000000000000000000000000000000000000dA"

    plan = aave_supply.SupplyPlan(
        wallet="0xwallet",
        display_token="dai",
        pool_token="dai",
        amount=Decimal("100"),
        amount_wei=123,
        approval_needed=True,
        wrap_tx=None,
        approve_tx={"nonce": 5},
        supply_tx={"nonce": 6},
        total_gas_cost_eth=Decimal("0.001"),
    )

    monkeypatch.setattr(aave_supply, "BlockchainAccess", FakeBlockchainAccess)
    monkeypatch.setattr(aave_supply, "load_private_key", lambda env_var: "0x" + "11" * 32)
    monkeypatch.setattr(aave_supply, "wallet_from_private_key", lambda private_key: "0xwallet")
    monkeypatch.setattr(aave_supply.Web3, "to_checksum_address", lambda address: address)
    monkeypatch.setattr(aave_supply, "build_supply_plan", lambda blockchain_access, args, wallet: plan)
    monkeypatch.setattr(aave_supply, "build_supply_tx", lambda *args, **kwargs: {"nonce": 6})
    monkeypatch.setattr(aave_supply, "resolve_pool_address", lambda args: "0xpool")
    monkeypatch.setattr(
        aave_supply,
        "sign_and_send",
        lambda blockchain_access, tx, private_key: "0xapprove" if tx["nonce"] == 5 else "0xsupply",
    )
    monkeypatch.setattr(
        aave_supply,
        "wait_for_receipt",
        lambda blockchain_access, tx_hash, timeout_seconds: {"status": 1, "transactionHash": tx_hash},
    )
    monkeypatch.setattr(aave_supply, "maybe_confirm", lambda args: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aave_supply.py",
            "--token",
            "dai",
            "--amount",
            "100",
            "--execute",
            "--receipt-dir",
            str(tmp_path),
        ],
    )

    aave_supply.main()

    output = capsys.readouterr().out
    assert "Approval tx sent: 0xapprove" in output
    assert "Supply tx sent: 0xsupply" in output
    assert "Receipt saved:" in output
    receipt_files = list(tmp_path.glob("arbitrum-aave-supply-dai-0xsupply.json"))
    assert len(receipt_files) == 1
    payload = json.loads(receipt_files[0].read_text())
    assert payload["metadata"]["approval_tx_hash"] == "0xapprove"
    assert payload["metadata"]["supply_tx_hash"] == "0xsupply"
