from decimal import Decimal
import sys

from scripts import spark_savings


def test_parse_args_defaults_to_preview(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["spark_savings.py", "--amount", "100"],
    )

    args = spark_savings.parse_args()

    assert args.chain == "arbitrum"
    assert args.amount == "100"
    assert args.execute is False
    assert args.slippage_bps == spark_savings.DEFAULT_SLIPPAGE_BPS


def test_parse_args_rejects_large_slippage(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["spark_savings.py", "--amount", "100", "--slippage-bps", "1001"],
    )

    try:
        spark_savings.parse_args()
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("parse_args should reject excessive slippage")


def test_build_plan_previews_spark_savings_swap():
    class FakeCall:
        def __init__(self, value):
            self.value = value

        def call(self):
            return self.value

    class FakePsmFunctions:
        @staticmethod
        def previewSwapExactIn(asset_in, asset_out, amount_in):
            assert asset_in == "0xUSDS"
            assert asset_out == "0xSUSDS"
            assert amount_in == 100 * 10**18
            return FakeCall(99 * 10**18)

        @staticmethod
        def swapExactIn(asset_in, asset_out, amount_in, min_amount_out, receiver, referral_code):
            assert asset_in == "0xUSDS"
            assert asset_out == "0xSUSDS"
            assert amount_in == 100 * 10**18
            assert min_amount_out == 98950500000000000000
            assert receiver == "0xwallet"
            assert referral_code == 0
            return FakeTxBuilder()

    class FakeApproveFunctions:
        @staticmethod
        def approve(spender, amount):
            assert spender == "0x2B05F8e1cACC6974fD79A673a341Fe1f58d27266"
            assert amount == 100 * 10**18
            return FakeTxBuilder()

    class FakeTxBuilder:
        @staticmethod
        def build_transaction(tx):
            return dict(tx)

    class FakePsmContract:
        functions = FakePsmFunctions()

    class FakeTokenContract:
        functions = FakeApproveFunctions()

    class FakeEth:
        @staticmethod
        def contract(address, abi):
            assert address == "0x2B05F8e1cACC6974fD79A673a341Fe1f58d27266"
            return FakePsmContract()

        @staticmethod
        def get_transaction_count(wallet):
            assert wallet == "0xwallet"
            return 7

        @staticmethod
        def get_block(block):
            return {"baseFeePerGas": 0}

        gas_price = 100

        @staticmethod
        def estimate_gas(tx):
            return 21000

    class FakeW3:
        eth = FakeEth()

    class FakeBlockchainAccess:
        def get_w3(self):
            return FakeW3()

        def get_chain(self):
            return "arbitrum"

        def get_chain_id(self):
            return 42161

        def get_decimals(self, token):
            return "ether"

        def get_token_contract_address(self, token):
            return {"usds": "0xUSDS", "susds": "0xSUSDS", "eth": "0xETH"}[token]

        def check_balance_token(self, token, wallet):
            assert token == "usds"
            assert wallet == "0xwallet"
            return Decimal("100")

        def check_allowance(self, token, owner, spender):
            assert token == "usds"
            assert owner == "0xwallet"
            assert spender == "0x2B05F8e1cACC6974fD79A673a341Fe1f58d27266"
            return Decimal("0")

        def get_token_contract(self, token):
            assert token == "usds"
            return FakeTokenContract()

    args = type(
        "Args",
        (),
        {
            "chain": "arbitrum",
            "amount": "100",
            "psm": None,
            "slippage_bps": 5,
        },
    )()

    plan = spark_savings.build_plan(FakeBlockchainAccess(), args, "0xwallet")

    assert plan.amount == Decimal("100")
    assert plan.expected_susds == Decimal("99")
    assert plan.min_susds == Decimal("98.9505")
    assert plan.approval_needed is True
    assert plan.approve_tx["nonce"] == 7
    assert plan.swap_tx["nonce"] == 8
