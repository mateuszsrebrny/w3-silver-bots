from decimal import Decimal
import json
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


def test_parse_args_accepts_preview_flag(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trade.py",
            "--to-token",
            "eth",
            "--amount",
            "100",
            "--preview",
        ],
    )

    args = trade.parse_args()

    assert args.preview is True
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

        @classmethod
        def save_receipt(cls, receipt_dir, filename_stem, tx_hash, receipt, metadata):
            return os.path.join(receipt_dir, f"{filename_stem}-{tx_hash[:10]}.json")

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

        def check_kyberswap_price(self, pair, amount, client_id="w3-silver-bots", log_quote=True):
            if pair == ["eth", "usdc"]:
                return Decimal(str(amount)) * Decimal("500")
            if pair == ["dai", "usdc"]:
                return Decimal(str(amount))
            return Decimal("0")

        def check_allowance(self, token, owner, spender):
            return Decimal("0")

        def get_decimals(self, token):
            return "ether"

        def get_decimals(self, token):
            return "ether"

        def get_decimals(self, token):
            return "ether"

        def get_w3(self):
            class FakeW3:
                class eth:
                    max_priority_fee = 100
                    gas_price = 100

                    @staticmethod
                    def estimate_gas(tx):
                        return 21000

                    @staticmethod
                    def get_transaction_count(owner):
                        return 5

                    @staticmethod
                    def get_block(block_name):
                        assert block_name == "latest"
                        return {"baseFeePerGas": 100}

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
    assert "Mode: preview" in output
    assert "Swap: 100 dai -> eth" in output
    assert "Input value (usd est): 100.00 usdc" in output
    assert "Output value (usd est): 100.00 usdc" in output
    assert "Quote discount vs spot (rough): 0.00%" in output
    assert "Approval needed: True" in output
    assert "Total gas cost: 0.002 ETH" in output
    assert "Total gas cost (usd est): 4.60 usdc" in output
    assert "Preview only. Use --execute to actually send the trade." in output


def test_main_execute_rebuilds_swap_after_approval(monkeypatch, capsys):
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

        def check_kyberswap_price(self, pair, amount, client_id="w3-silver-bots", log_quote=True):
            if pair == ["eth", "usdc"]:
                return Decimal(str(amount)) * Decimal("500")
            if pair == ["dai", "usdc"]:
                return Decimal(str(amount))
            return Decimal("0")

        def check_allowance(self, token, owner, spender):
            return Decimal("0")

        def get_decimals(self, token):
            return "ether"

        @classmethod
        def save_receipt(cls, receipt_dir, filename_stem, tx_hash, receipt, metadata):
            return os.path.join(receipt_dir, f"{filename_stem}-{tx_hash[:10]}.json")

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
    monkeypatch.setattr(trade, "build_approval_tx", lambda *args, **kwargs: {"gas": 50000, "nonce": 0})

    built_swap_txs = [{"gas": 120000, "nonce": 0}, {"gas": 120000, "nonce": 1}]

    def fake_build_swap_tx(*args, **kwargs):
        return built_swap_txs.pop(0)

    sent_txs = []

    def fake_sign_and_send(blockchain_access, tx, private_key):
        sent_txs.append(tx)
        return f"0x{len(sent_txs)}"

    monkeypatch.setattr(trade, "build_swap_tx", fake_build_swap_tx)
    monkeypatch.setattr(trade, "sign_and_send", fake_sign_and_send)
    monkeypatch.setattr(trade, "wait_for_receipt", lambda blockchain_access, tx_hash, timeout_seconds: {"status": 1})
    monkeypatch.setattr(trade, "maybe_confirm", lambda args: None)
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
            "--execute",
        ],
    )
    monkeypatch.setenv("BOT_PRIVATE_KEY", "0x" + "11" * 32)

    trade.main()

    output = capsys.readouterr().out
    assert "Approval tx sent: 0x1" in output
    assert "Swap tx sent: 0x2" in output
    assert sent_txs == [{"gas": 50000, "nonce": 0}, {"gas": 120000, "nonce": 1}]


def test_main_execute_saves_trade_receipt(monkeypatch, tmp_path, capsys):
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

        @classmethod
        def save_receipt(cls, receipt_dir, filename_stem, tx_hash, receipt, metadata):
            path = tmp_path / f"{filename_stem}-{tx_hash[:10]}.json"
            path.write_text(json.dumps({"metadata": metadata, "receipt": receipt}))
            return path

        def check_kyberswap_price(self, pair, amount, client_id="w3-silver-bots", log_quote=True):
            if pair == ["eth", "usdc"]:
                return Decimal(str(amount)) * Decimal("500")
            if pair == ["dai", "usdc"]:
                return Decimal(str(amount))
            return Decimal("0")

        def check_allowance(self, token, owner, spender):
            return Decimal("0")

        def get_decimals(self, token):
            return "ether"

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
    monkeypatch.setattr(trade, "build_approval_tx", lambda *args, **kwargs: {"gas": 50000, "nonce": 0})

    built_swap_txs = [{"gas": 120000, "nonce": 0}, {"gas": 120000, "nonce": 1}]

    monkeypatch.setattr(trade, "build_swap_tx", lambda *args, **kwargs: built_swap_txs.pop(0))
    monkeypatch.setattr(
        trade,
        "sign_and_send",
        lambda blockchain_access, tx, private_key: "0xapproval" if tx["nonce"] == 0 else "0xswap",
    )
    monkeypatch.setattr(
        trade,
        "wait_for_receipt",
        lambda blockchain_access, tx_hash, timeout_seconds: {"status": 1, "transactionHash": tx_hash},
    )
    monkeypatch.setattr(trade, "maybe_confirm", lambda args: None)
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
            "--execute",
            "--receipt-dir",
            str(tmp_path),
        ],
    )
    monkeypatch.setenv("BOT_PRIVATE_KEY", "0x" + "11" * 32)

    trade.main()

    output = capsys.readouterr().out
    assert "Receipt saved:" in output
    assert "Receipt status: 1" in output
    receipt_files = list(tmp_path.glob("arbitrum-dai-to-eth-0xswap.json"))
    assert len(receipt_files) == 1
    payload = json.loads(receipt_files[0].read_text())
    assert payload["metadata"]["approval_tx_hash"] == "0xapproval"
    assert payload["metadata"]["swap_tx_hash"] == "0xswap"
