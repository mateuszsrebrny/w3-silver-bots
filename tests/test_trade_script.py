from decimal import Decimal
import os
import sys

from scripts import trade


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_parse_args_accepts_expected_trade_shape(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trade.py",
            "--to-token",
            "eth",
            "--amount",
            "100",
        ],
    )

    args = trade.parse_args()

    assert args.chain == "arbitrum"
    assert args.from_token == "dai"
    assert args.to_token == "eth"
    assert args.amount == "100"
    assert args.execute is False


def test_fetch_route_uses_kyber_v1_get(monkeypatch):
    captured = {}

    class FakeBlockchainAccess:
        def get_token_contract_address(self, token):
            return {"dai": "0xdai", "eth": "0xeth"}[token]

        def get_kyberswap_chain_name(self):
            return "arbitrum"

        def get_decimals(self, token):
            return "ether"

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return FakeResponse(
            {
                "data": {
                    "routerAddress": "0xrouter",
                    "routeSummary": {"amountOut": "123", "gas": "456"},
                }
            }
        )

    monkeypatch.setattr(trade.requests, "get", fake_get)

    route = trade.fetch_route(FakeBlockchainAccess(), "dai", "eth", Decimal("100"), "0xwallet")

    assert route.router_address == "0xrouter"
    assert route.route_summary["amountOut"] == "123"
    assert captured["url"].endswith("/arbitrum/api/v1/routes")
    assert captured["params"]["origin"] == "0xwallet"
    assert captured["headers"]["x-client-id"] == trade.CLIENT_ID


def test_build_encoded_swap_uses_kyber_v1_post(monkeypatch):
    captured = {}

    class FakeBlockchainAccess:
        def get_kyberswap_chain_name(self):
            return "arbitrum"

    def fake_post(url, headers, data, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        return FakeResponse({"data": {"data": "0xdeadbeef", "value": "7"}})

    monkeypatch.setattr(trade.requests, "post", fake_post)
    route = trade.SwapRoute(router_address="0xrouter", route_summary={"routeID": "abc"})

    encoded = trade.build_encoded_swap(FakeBlockchainAccess(), route, "0xwallet", 50, 600)

    assert encoded.router_address == "0xrouter"
    assert encoded.calldata == "0xdeadbeef"
    assert encoded.value_wei == 7
    assert captured["url"].endswith("/arbitrum/api/v1/route/build")
    assert captured["headers"]["x-client-id"] == trade.CLIENT_ID
    assert '"sender": "0xwallet"' in captured["data"]


def test_main_preview_only_prints_trade_summary(monkeypatch, capsys):
    class FakeBlockchainAccess:
        def __init__(self, chain, dry_run):
            self.chain = chain
            self.dry_run = dry_run

        @classmethod
        def load_config(cls, config_path):
            return None

        @classmethod
        def my_fromWei(cls, amount_wei, unit):
            if unit == "ether":
                return Decimal(str(amount_wei)) / Decimal(str(10**18))
            return Decimal(str(amount_wei))

        @classmethod
        def my_toWei(cls, amount, unit):
            if unit == "ether":
                return int(Decimal(str(amount)) * Decimal(str(10**18)))
            return int(Decimal(str(amount)))

        def check_kyberswap_price(self, pair, amount):
            return Decimal("2300")

        def check_allowance(self, token, owner, spender):
            return Decimal("0")

        def get_decimals(self, token):
            return "ether"

        def get_w3(self):
            class FakeW3:
                class eth:
                    gas_price = 100

                    @staticmethod
                    def estimate_gas(tx):
                        return 21000

                    @staticmethod
                    def get_transaction_count(owner):
                        return 5

            return FakeW3()

        def get_chain_id(self):
            return 42161

        def get_token_contract(self, token):
            class FakeContract:
                class functions:
                    @staticmethod
                    def approve(spender, amount):
                        class FakeApprove:
                            @staticmethod
                            def build_transaction(tx):
                                return dict(tx)
                        return FakeApprove()
            return FakeContract()

    monkeypatch.setattr(trade, "BlockchainAccess", FakeBlockchainAccess)
    monkeypatch.setattr(trade, "load_private_key", lambda: "0x" + "11" * 32)
    monkeypatch.setattr(trade, "wallet_from_private_key", lambda private_key: "0xwallet")
    monkeypatch.setattr(
        trade,
        "fetch_route",
        lambda blockchain_access, from_token, to_token, amount, wallet: trade.SwapRoute(
            router_address="0xrouter",
            route_summary={"amountOut": str(2 * 10**17), "gas": "123456"},
        ),
    )
    monkeypatch.setattr(
        trade,
        "build_encoded_swap",
        lambda blockchain_access, route, wallet, slippage_bps, deadline_seconds: trade.EncodedSwap(
            router_address="0xrouter",
            calldata="0xdead",
            value_wei=0,
        ),
    )
    monkeypatch.setattr(trade, "build_approval_tx", lambda *args, **kwargs: {"gas": 50000})
    monkeypatch.setattr(trade, "build_swap_tx", lambda *args, **kwargs: {"gas": 120000})
    monkeypatch.setattr(
        trade,
        "assess_gas_cost",
        lambda blockchain_access, gas_limit, eth_usd_price=None: trade.GasAssessment(
            gas_price_wei=100,
            gas_limit=gas_limit,
            gas_cost_eth=Decimal("0.001"),
            gas_cost_usd=Decimal("2.30"),
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trade.py",
            "--to-token",
            "eth",
            "--amount",
            "100",
        ],
    )
    monkeypatch.setenv("BOT_PRIVATE_KEY", "0x" + "11" * 32)

    trade.main()

    output = capsys.readouterr().out
    assert "Swap: 100 dai -> eth" in output
    assert "Approval needed: True" in output
    assert "Preview only. Use --execute to actually send the trade." in output
