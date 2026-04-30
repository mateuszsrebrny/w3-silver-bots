from decimal import Decimal
import json

import pytest

from botweb3lib import BlockchainAccess, NATIVE_TOKEN_ADDRESS


@pytest.fixture(autouse=True)
def reset_class_state():
    original_config = BlockchainAccess._config
    original_abi_cache = dict(BlockchainAccess._abi_cache)
    yield
    BlockchainAccess._config = original_config
    BlockchainAccess._abi_cache = original_abi_cache


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
                    }
                },
            }
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
