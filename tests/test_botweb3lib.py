from decimal import Decimal
import json

import pytest

import botweb3lib
from botweb3lib import BlockchainAccess, NATIVE_TOKEN_ADDRESS


@pytest.fixture(autouse=True)
def reset_class_state():
    original_config = BlockchainAccess._config
    original_abi_cache = dict(BlockchainAccess._abi_cache)
    original_beefy_api_cache = dict(BlockchainAccess._beefy_api_cache)
    yield
    BlockchainAccess._config = original_config
    BlockchainAccess._abi_cache = original_abi_cache
    BlockchainAccess._beefy_api_cache = original_beefy_api_cache


@pytest.fixture
def sample_config():
    return {
        "networks": {
            "polygon": {
                "rpc_url": "https://polygon.example",
                "chain_id": 137,
                "contracts": {
                    "erc20": {
                        "pol": {
                            "address": NATIVE_TOKEN_ADDRESS,
                            "decimals": "ether",
                            "native": True,
                        },
                        "usdc": {
                            "address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
                            "decimals": "mwei",
                        },
                        "wbtc": {
                            "address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
                            "decimals": "lovelace",
                        },
                        "moousdc": {
                            "address": "0x1111111111111111111111111111111111111111",
                            "decimals": "ether",
                            "beefy_vault_id": "test-vault",
                            "beefy_oracle_id": "test-oracle",
                        },
                        "rcowwmaticldo": {
                            "address": "0x3333333333333333333333333333333333333333",
                            "decimals": "ether",
                            "beefy_price_oracle_id": "uniswap-cow-poly-wmatic-ldo",
                            "beefy_apr_breakdown_id": "uniswap-cow-poly-wmatic-ldo-rp",
                            "beefy_apr_field": "totalApy",
                            "beefy_interest_label": "Beefy APY",
                        },
                    }
                },
            },
            "ethereum": {
                "rpc_url": "https://ethereum.example",
                "chain_id": 1,
                "contracts": {
                    "erc20": {
                        "beqi": {
                            "address": "0x6c9D885B37b131aa68794ee1549fFB80be381Fa9",
                            "decimals": "ether",
                            "beefy_price_oracle_id": "beQIv2",
                        },
                        "rbeqi": {
                            "address": "0x5e3e4ed40e754254095f091aa51871d125f4380a",
                            "decimals": "ether",
                            "beefy_price_oracle_id": "beQIv2",
                            "beefy_apr_breakdown_id": "beefy-beqi-earnings",
                            "beefy_apr_field": "vaultApr",
                        }
                    }
                },
            },
        }
    }


def test_get_contract_address_checksums_and_native(sample_config):
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")

    assert blockchain_access.get_contract_address("erc20", "pol") == NATIVE_TOKEN_ADDRESS
    assert (
        blockchain_access.get_contract_address("erc20", "usdc")
        == "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    )


def test_kyberswap_chain_name_rejects_unknown_chain(sample_config):
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")
    blockchain_access._chain = "base"

    with pytest.raises(KeyError):
        blockchain_access.get_kyberswap_chain_name()


def test_lovelace_unit_roundtrip():
    quantity = 0.07047496

    wei_amount = BlockchainAccess.my_toWei(quantity, "lovelace")

    assert wei_amount == 7047496
    assert BlockchainAccess.my_fromWei(wei_amount, "lovelace") == Decimal("0.07047496")


def test_load_abi_result_parses_stringified_result(tmp_path):
    abi_path = tmp_path / "abi.json"
    abi_path.write_text(json.dumps({"result": '[{"name":"balanceOf","type":"function"}]'}))

    abi = BlockchainAccess._load_abi_result(str(abi_path))

    assert abi == [{"name": "balanceOf", "type": "function"}]


def test_check_balance_token_uses_native_balance(monkeypatch, sample_config):
    class FakeEth:
        def get_balance(self, wallet):
            assert wallet == "0xwallet"
            return 2 * 10**18

    class FakeWeb3:
        eth = FakeEth()

    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")
    blockchain_access._w3 = FakeWeb3()

    assert blockchain_access.check_balance_token("pol", "0xwallet") == 2


def test_check_balance_token_uses_erc20_contract(monkeypatch, sample_config):
    class FakeCall:
        def call(self):
            return 1234567

    class FakeFunctions:
        def balanceOf(self, wallet):
            assert wallet == "0xwallet"
            return FakeCall()

    class FakeContract:
        functions = FakeFunctions()

    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")

    def fake_init_token_contract(token):
        assert token == "usdc"
        blockchain_access._contract[token] = FakeContract()

    monkeypatch.setattr(blockchain_access, "init_token_contract", fake_init_token_contract)

    assert blockchain_access.check_balance_token("usdc", "0xwallet") == Decimal("1.234567")


def test_check_kyberswap_price_success(monkeypatch, sample_config):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"routeSummary": {"amountOut": "1234567"}}}

    def fake_get(url, params, headers, timeout):
        assert url == "https://aggregator-api.kyberswap.com/polygon/api/v1/routes"
        assert params["tokenIn"] == "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        assert params["tokenOut"] == "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6"
        assert params["amountIn"] == "1000000"
        assert headers == {"x-client-id": "tests"}
        assert timeout == 20
        return FakeResponse()

    monkeypatch.setattr("botweb3lib.requests.get", fake_get)
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")

    assert (
        blockchain_access.check_kyberswap_price(["usdc", "wbtc"], 1, client_id="tests")
        == Decimal("0.01234567")
    )


def test_check_kyberswap_price_returns_zero_on_failure(monkeypatch, sample_config):
    def fake_get(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("botweb3lib.requests.get", fake_get)
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")

    assert blockchain_access.check_kyberswap_price(["usdc", "wbtc"], 1) == 0


def test_build_fee_params_uses_eip1559_when_base_fee_present():
    class FakeEth:
        max_priority_fee = 7

        @staticmethod
        def get_block(block_name):
            assert block_name == "latest"
            return {"baseFeePerGas": 100}

    class FakeW3:
        eth = FakeEth()

    fee_params = BlockchainAccess.build_fee_params(FakeW3())

    assert fee_params == {
        "maxFeePerGas": 207,
        "maxPriorityFeePerGas": 7,
        "type": 2,
    }
    assert BlockchainAccess.fee_cap_wei(fee_params) == 207


def test_build_fee_params_falls_back_to_legacy_gas_price():
    class FakeEth:
        gas_price = 123

        @staticmethod
        def get_block(block_name):
            assert block_name == "latest"
            return {"baseFeePerGas": 0}

        @property
        def max_priority_fee(self):
            raise RuntimeError("unsupported")

    class FakeW3:
        eth = FakeEth()

    fee_params = BlockchainAccess.build_fee_params(FakeW3())

    assert fee_params == {"gasPrice": 123}
    assert BlockchainAccess.fee_cap_wei(fee_params) == 123


def test_estimate_gas_falls_back_and_warns():
    warnings = []

    class FakeEth:
        @staticmethod
        def estimate_gas(tx):
            raise RuntimeError("boom")

    class FakeW3:
        eth = FakeEth()

    gas = BlockchainAccess.estimate_gas(
        FakeW3(),
        {"to": "0xabc"},
        21000,
        warning_printer=warnings.append,
    )

    assert gas == 21000
    assert len(warnings) == 1
    assert "Falling back to gas limit 21000" in warnings[0]


def test_get_aave_supply_apr_reads_liquidity_rate(monkeypatch, sample_config):
    class FakeCall:
        @staticmethod
        def call():
            return (0, 0, 42 * 10**24, 0, 0, 0, 0, 0, "0x0", "0x0", "0x0", "0x0", 0, 0, 0)

    class FakeFunctions:
        @staticmethod
        def getReserveData(asset):
            assert asset == "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
            return FakeCall()

    class FakePoolContract:
        functions = FakeFunctions()

    class FakeEth:
        @staticmethod
        def contract(address, abi):
            return FakePoolContract()

    class FakeW3:
        eth = FakeEth()

    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")
    blockchain_access._w3 = FakeW3()
    monkeypatch.setitem(botweb3lib.AAVE_POOL_BY_CHAIN, "polygon", "0x1111111111111111111111111111111111111111")
    monkeypatch.setitem(botweb3lib.AAVE_ATOKEN_UNDERLYING_BY_CHAIN, "polygon", {"ausdc": "usdc"})

    assert blockchain_access.get_aave_supply_apr("ausdc") == Decimal("4.2")


def test_beefy_vault_value_and_apy(monkeypatch, sample_config):
    class FakeCall:
        @staticmethod
        def call():
            return 1100000000000000000

    class FakeFunctions:
        @staticmethod
        def getPricePerFullShare():
            return FakeCall()

    class FakeVaultContract:
        functions = FakeFunctions()

    class FakeEth:
        @staticmethod
        def contract(address, abi):
            assert address == "0x1111111111111111111111111111111111111111"
            return FakeVaultContract()

    class FakeW3:
        eth = FakeEth()

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, timeout):
        assert timeout == 20
        if url == "https://api.beefy.finance/lps":
            return FakeResponse({"test-oracle": 2.5})
        if url == "https://api.beefy.finance/apy/breakdown":
            return FakeResponse({"test-vault": {"totalApy": 0.1234}})
        raise AssertionError(url)

    monkeypatch.setattr("botweb3lib.requests.get", fake_get)
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")
    blockchain_access._w3 = FakeW3()

    assert blockchain_access.is_beefy_vault_token("moousdc") is True
    assert blockchain_access.get_beefy_vault_value("moousdc", Decimal("3")) == Decimal("8.25")
    assert blockchain_access.get_beefy_vault_apy("moousdc") == Decimal("12.3400")


def test_beefy_priced_token_value(monkeypatch, sample_config):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, timeout):
        assert timeout == 20
        assert url == "https://api.beefy.finance/prices"
        return FakeResponse({"beQIv2": 1.25})

    monkeypatch.setattr("botweb3lib.requests.get", fake_get)
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("ethereum")

    assert blockchain_access.is_beefy_priced_token("beqi") is True
    assert blockchain_access.get_beefy_token_value("beqi", Decimal("4")) == Decimal("5.0")


def test_beefy_priced_token_value_falls_back_to_lps(monkeypatch, sample_config):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, timeout):
        assert timeout == 20
        if url == "https://api.beefy.finance/prices":
            return FakeResponse({"beQI": 1.25})
        if url == "https://api.beefy.finance/lps":
            return FakeResponse({"uniswap-cow-poly-wmatic-ldo": 6})
        raise AssertionError(url)

    monkeypatch.setattr("botweb3lib.requests.get", fake_get)
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")

    assert blockchain_access.is_beefy_priced_token("rcowwmaticldo") is True
    assert blockchain_access.get_beefy_token_value("rcowwmaticldo", Decimal("7")) == Decimal("42")


def test_beefy_priced_token_apr(monkeypatch, sample_config):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, timeout):
        assert timeout == 20
        assert url == "https://api.beefy.finance/apy/breakdown"
        return FakeResponse({"beefy-beqi-earnings": {"vaultApr": 0.22237282073794604}})

    monkeypatch.setattr("botweb3lib.requests.get", fake_get)
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("ethereum")

    assert blockchain_access.get_beefy_token_apr("rbeqi") == Decimal("22.23728207379460400")


def test_beefy_priced_token_apy_and_label(monkeypatch, sample_config):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, timeout):
        assert timeout == 20
        assert url == "https://api.beefy.finance/apy/breakdown"
        return FakeResponse({"uniswap-cow-poly-wmatic-ldo-rp": {"totalApy": 0.25771911991263097}})

    monkeypatch.setattr("botweb3lib.requests.get", fake_get)
    BlockchainAccess._config = sample_config
    blockchain_access = BlockchainAccess("polygon")

    assert blockchain_access.get_beefy_token_apr("rcowwmaticldo") == Decimal("25.77191199126309700")
    assert blockchain_access.get_beefy_token_interest_label("rcowwmaticldo") == "Beefy APY"
