from decimal import Decimal
import json
import requests
import yaml
from web3 import Web3

NATIVE_TOKEN_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


class BlockchainAccess:

    _config = None
    _abi_cache = {}
    _kyberswap_chain_names = {
        "polygon": "polygon",
        "optimism": "optimism",
        "ethereum": "ethereum",
        "arbitrum": "arbitrum",
    }

    @classmethod
    def load_config(cls, config_path="chains.config.yaml"):
        with open(config_path, "r") as file:
            cls._config = yaml.safe_load(file)

    def __init__(self, chain="polygon", dry_run=True):

        if BlockchainAccess._config is None:
            raise ValueError(
                "Config not loaded. Execute BlockchainAccess.load_config()."
            )

        self._chain = chain
        print("chain:", self._chain)

        # TODO verify chain is in the config

        self._dry_run = dry_run
        print("dry_run:", self._dry_run)

        self._w3 = None
        self._contract = {}

    def get_chain(self):
        return self._chain

    def get_config(self):
        return BlockchainAccess._config["networks"][self._chain]

    def get_rpc_url(self):
        return self.get_config()["rpc_url"]

    def get_chain_id(self):
        return self.get_config()["chain_id"]

    def get_kyberswap_chain_name(self):
        if self._chain not in BlockchainAccess._kyberswap_chain_names:
            raise KeyError(f"KyberSwap chain not configured for {self._chain}")
        return BlockchainAccess._kyberswap_chain_names[self._chain]

    def get_decimals(self, token):
        return self.get_config()["contracts"]["erc20"][token]["decimals"]

    def is_native_token(self, token):
        token_info = self.get_config()["contracts"]["erc20"][token]
        return token_info.get("native", False)

    def get_all_tokens(self):
        return self.get_config()["contracts"]["erc20"].keys()

    def get_contract_address(self, contract_type, name):
        contracts = self.get_config()["contracts"]
        contract_group = contracts.get(contract_type)

        if contract_group is None:
            contract_group = contracts.get(contract_type + "s")

        if contract_group is None:
            raise KeyError(f"Unknown contract type: {contract_type}")

        contract_info = contract_group[name]

        if isinstance(contract_info, dict):
            address = contract_info["address"]
        else:
            address = contract_info

        if address == NATIVE_TOKEN_ADDRESS:
            return address

        return Web3.to_checksum_address(address)

    def get_token_contract_address(self, token):
        return self.get_contract_address("erc20", token)

    def get_w3(self):
        if not self._w3:
            rpc_url = self.get_rpc_url()
            self._w3 = Web3(Web3.HTTPProvider(rpc_url))

            if not self._w3.is_connected():
                print(f"w3 {self._chain} NOT connected")
                raise ConnectionError(f"Failed to connect Web3 at {rpc_url}")

            print(f"w3 {self._chain} is connected")

        return self._w3

    @classmethod
    def my_toWei(cls, quantity, unit):
        if unit == "lovelace":
            return int(Decimal(str(quantity)) * (10**8))
        return Web3.to_wei(quantity, unit)

    @classmethod
    def my_fromWei(cls, wei, unit):
        quantity = Web3.from_wei(wei, unit)
        if unit == "lovelace":
            return quantity / 100
        return quantity

    def _get_cached_contract(self, cache_key, address, abi):
        if cache_key not in self._contract:
            self._contract[cache_key] = self.get_w3().eth.contract(address=address, abi=abi)
        return self._contract[cache_key]

    @classmethod
    def _load_abi_result(cls, abi_path):
        if abi_path not in cls._abi_cache:
            with open(abi_path) as f:
                abi_json = json.load(f)

            abi_result = abi_json["result"]
            if isinstance(abi_result, str):
                abi_result = json.loads(abi_result)

            cls._abi_cache[abi_path] = abi_result

        return cls._abi_cache[abi_path]

    def init_token_contract(self, token):
        if self.is_native_token(token):
            return

        if token in self._contract:
            return

        abi = BlockchainAccess._load_abi_result("abi/erc20.abi.json")

        self._contract[token] = self.get_w3().eth.contract(
            address=self.get_token_contract_address(token), abi=abi
        )

    def check_balance_token(self, token, wallet):
        if self.is_native_token(token):
            balance_wei = self.get_w3().eth.get_balance(wallet)
            return BlockchainAccess.my_fromWei(balance_wei, self.get_decimals(token))

        self.init_token_contract(token)

        balance_wei = self._contract[token].functions.balanceOf(wallet).call()
        return BlockchainAccess.my_fromWei(balance_wei, self.get_decimals(token))

    def check_balance(self, tokens, wallet):
        balance = {}
        for token in tokens:
            balance[token] = self.check_balance_token(token, wallet)
            print(f"holding( {wallet} @ {self._chain} ): {balance[token]} {token}")

        return balance

    def check_kyberswap_price(self, pair, input_quantity, client_id="w3-silver-bots"):
        from_token = pair[0]
        to_token = pair[1]

        if from_token == to_token:
            return input_quantity

        input_quantity_wei = BlockchainAccess.my_toWei(
            input_quantity, self.get_decimals(from_token)
        )

        if input_quantity_wei == 0:
            return 0

        url = (
            "https://aggregator-api.kyberswap.com/"
            f"{self.get_kyberswap_chain_name()}/api/v1/routes"
        )
        params = {
            "tokenIn": self.get_token_contract_address(from_token),
            "tokenOut": self.get_token_contract_address(to_token),
            "amountIn": str(input_quantity_wei),
        }
        headers = {"x-client-id": client_id}

        try:
            response = requests.get(url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            route_json = response.json()
            output_quantity_wei = int(route_json["data"]["routeSummary"]["amountOut"])
            output_quantity = BlockchainAccess.my_fromWei(
                output_quantity_wei, self.get_decimals(to_token)
            )

            if output_quantity > 0:
                print("kyberswap:", input_quantity, from_token, "->", output_quantity, to_token)

            return output_quantity
        except Exception:
            return 0

##################################################
# Not used, nor refactored into BlockchainAccess #
##################################################
#
# _bot_address = "0x5084a58B67152f21FFBEb73b231E61318cEEcB74"
#
#
# def get_univ2_contract(swap_name):
#    if swap_name in _contract:
#        return _contract[swap_name]
#
#    with open("abi/" + swap_name + "swap.abi.json") as f:
#        abi_json = json.load(f)
#    abi = abi_json["result"]
#    address = get_swap_contract_address(swap_name + "swap")
#    _contract[swap_name] = get_w3().eth.contract(address=address, abi=abi)
#
#    return _contract[swap_name]
#
#
## with open("private_key_file") as f:
##  _b_k = f.read()
#
#
# def sign_n_send_transaction(txn={}, contract_fun=None):
#
#    bot_nonce = get_w3().eth.get_transaction_count(_bot_address)
#
#    if get_chain() == "polygon":
#        gas_json = requests.get("https://gasstation-mainnet.matic.network/v2").json()
#
#        if gas_json["standard"]["maxFee"] > 500:
#            print("gas too high:", gas_json["standard"]["maxFee"])
#            return
#
#        maxFee_wei = Web3.toWei(gas_json["standard"]["maxFee"], "gwei")
#        maxPriorityFee_wei = Web3.toWei(gas_json["standard"]["maxPriorityFee"], "gwei")
#
#        print("gas maxFee:", gas_json["standard"]["maxFee"], "nonce:", bot_nonce)
#
#        if contract_fun:
#            txn = contract_fun.buildTransaction(
#                dict(
#                    nonce=bot_nonce,
#                    chainId=get_chain_id(),
#                    maxFeePerGas=maxFee_wei,
#                    maxPriorityFeePerGas=maxPriorityFee_wei,
#                    gas=1000000,
#                )
#            )
#        else:
#            txn["nonce"] = bot_nonce
#            txn["chainId"] = get_chain_id()
#
#            # gas estimated manually (max.*FeePerGas)
#            # is better than gasPrice from 1inch
#            txn.pop("gasPrice")
#            txn["maxFeePerGas"] = maxFee_wei
#            txn["maxPriorityFeePerGas"] = maxPriorityFee_wei
#
#    elif get_chain() == "optimism":
#        txn["nonce"] = bot_nonce
#        txn["chainId"] = get_chain_id()
#        txn["gasPrice"] = int(txn["gasPrice"])
#
#    print("txn:", txn)
#
#    signed_txn = get_w3().eth.account.sign_transaction(txn, _b_k)
#
#    if _dry_run:
#        print("dry run -> returning")
#        return
#
#    print("signed tx: ", signed_txn)
#
#    txn_hash = get_w3().eth.send_raw_transaction(signed_txn.rawTransaction)
#    print("txn hash: ", Web3.toHex(txn_hash))
#
#    txn_receipt = get_w3().eth.wait_for_transaction_receipt(txn_hash)
#    txn_info = get_w3().eth.getTransaction(txn_hash)
#
#    print("txn receipt: ", txn_receipt)
#    print("txn info: ", txn_info)
#    print("--> txn status: ", txn_receipt["status"])
#
#
# def swap_contracts_path(swap_path):
#    path = []
#    for token in swap_path:
#        path.append(get_token_contract_address(token))
#    return path
#
#
# def sell_uniswapv2(pair, input_quantity, buy_stops, swap_name):
#
#    buy_path = pair.copy()
#    buy_path[1:1] = buy_stops
#
#    input_quantity_wei = my_toWei(input_quantity, get_decimals(pair[0]))
#    minimum_input_quantity_wei = int(input_quantity_wei * 0.003)
#
#    contracts_path = swap_contracts_path(buy_path)
#
#    deadline = int(time.time() + 60)
#
#    fun = get_univ2_contract(swap_name).functions.swapExactTokensForTokens(
#        input_quantity_wei,
#        minimum_input_quantity_wei,
#        contracts_path,
#        _bot_address,
#        deadline,
#    )
#
#    sign_n_send_transaction(contract_fun=fun)
#
#
# def check_1inch_allowance(tokenName):
#    allow_params = {
#        "tokenAddress": get_token_contract_address(tokenName),
#        "walletAddress": _bot_address,
#    }
#
#    allow_json = _call_1inch_api("approve/allowance", allow_params)
#    # print(tokenName, "allow_json:", allow_json)
#
#    try:
#
#        allowance = int(allow_json["allowance"])
#        print("check_1inch_allowance", tokenName, "allowance:", allowance)
#
#        return allowance > 0
#
#    except Exception as e:
#        traceback.print_exc()
#        print("check_1inch_allowance:", tokenName, allow_json)
#        return False
#
#
# def check_allowance(token, swap):
#    if swap == "1inch":
#        return check_1inch_allowance(token)
#
#    print("don't know how to check allowance on", swap)
#    return False
#
#
# def sell_1inch(sell_token, sell_amount, buy_token):
#    # print("1inch selling", sell_amount, sell_token, "into", buy_token)
#    sell_amount_wei = my_toWei(sell_amount, get_decimals(sell_token))
#
#    swap_params = {
#        "fromTokenAddress": get_token_contract_address(sell_token),
#        "toTokenAddress": get_token_contract_address(buy_token),
#        "amount": sell_amount_wei,
#        "fromAddress": _bot_address,
#        "slippage": 1,
#    }
#
#    print("swap_params:", swap_params)
#
#    swap_call_json = _call_1inch_api("swap", swap_params)
#
#    try:
#        swap_txn = swap_call_json["tx"]
#        # print("swap_txn:", swap_txn)
#
#        swap_txn["to"] = get_w3().toChecksumAddress(swap_txn["to"])
#        swap_txn["value"] = int(swap_txn["value"])
#        swap_txn["gas"] = int(swap_txn["gas"] * 1.25)
#
#        sign_n_send_transaction(swap_txn)
#
#    except Exception as e:
#        traceback.print_exc()
#        print("not selling, swap_call_json:", swap_call_json)
#
#
# def sell(pair, input_quantity, buy_stops, swap_name):
#    print(swap_name, "selling", input_quantity, pair[0], "for", pair[1])
#
#    if swap_name == "1inch":
#        sell_1inch(pair[0], input_quantity, pair[1])
#
#    else:
#        sell_uniswapv2(pair, input_quantity, buy_stops, swap_name)
#
#    check_balance(pair)
#
#
# def get_amounts_out(path, input_quantity, swap):
#
#    input_quantity_wei = my_toWei(input_quantity, get_decimals(path[0]))
#
#    contracts_path = swap_contracts_path(path)
#
#    get_amounts_out_result = (
#        get_univ2_contract(swap)
#        .functions.getAmountsOut(input_quantity_wei, contracts_path)
#        .call()
#    )
#
#    input_amount = my_fromWei(get_amounts_out_result[0], get_decimals(path[0]))
#    output_amount = my_fromWei(get_amounts_out_result[-1], get_decimals(path[-1]))
#
#    print(swap, path, ":", input_amount, path[0], "->", output_amount, path[-1])
#
#    return output_amount
#
#
# def check_price(pair, input_quantity, buy_stops, buy_swap):
#    if buy_swap == "1inch":
#        return check_1inch_price(pair, input_quantity)
#
#    buy_path = pair.copy()
#    buy_path[1:1] = buy_stops
#
#    buy_quantity = get_amounts_out(
#        path=buy_path, input_quantity=input_quantity, swap=buy_swap
#    )
#
#    return buy_quantity
