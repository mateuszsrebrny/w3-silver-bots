import time
import json
import requests
import traceback
import cloudscraper 
from web3 import Web3

_bot_address = "0x5084a58B67152f21FFBEb73b231E61318cEEcB74"

# default chain
_chain = "polygon"

_dry_run = True

def setup_botweb3lib(chain, dry_run):
  global _chain
  _chain = chain
  print("chain:", _chain)

  global _dry_run
  _dry_run = dry_run
  print("dry_run:", _dry_run)

def get_chain():
  return _chain

_contract_address = {}

#polygon contracts
_contract_address["polygon"] = {
  "quickswap" : "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
  "apeswap" : "0x9E31215F6421c4EED2c04116d430CaF30999680d",
  "sushiswap" : "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
  "weth" : "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
  "mai" : "0xa3Fa99A148fA48D14Ed51d610c367C61876997F1",
  "dai" : "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
  "aave" : "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",
  "qi" : "0x580A84C73811E1839F75d86d75d88cCa0c241fF4",
  "wmatic" : "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
  "glm" : "0x0B220b82F3eA3B7F6d9A1D8ab58930C064A2b5Bf",
  "link" : "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",
  "sand" : "0xBbba073C31bF03b8ACf7c28EF0738DeCF3695683",
  "wbtc" : "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
  "uni" : "0xb33EaAd8d922B1083446DC23f610c2567fB5180f",
  "jeur" : "0x4e3Decbb3645551B8A19f0eA1678079FCB33fB4c",
  "usdc" : "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
  "bal" : "0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3",
  "stmatic" : "0x3A58a54C066FdC0f2D55FC9C89F0415C92eBf3C4",
  "ldo" : "0xC3C7d422809852031b44ab29EEC9F1EfF2A58756",
}

_contract_address["optimism"] = {
  "op" : "0x4200000000000000000000000000000000000042",
  "mai" : "0xdFA46478F9e5EA86d57387849598dbFB2e964b02",
  "dai" : "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
  "weth" : "0x4200000000000000000000000000000000000006",
  "qi" : "0x3F56e0c36d275367b8C502090EDF38289b3dEa0d",
  "ldo" : "0xFdb794692724153d1488CcdBE0C56c252596735F",
}

def get_contract_address(contract):
  return _contract_address[get_chain()][contract]

decimals = {
  "weth" : "ether",
  "mai" : "ether",
  "dai" : "ether",
  "aave" : "ether",
  "bal" : "ether",
  "qi" : "ether",
  "wmatic" : "ether",
  "glm" : "ether",
  "link" : "ether",
  "crv" : "ether",
  "sand" : "ether",
  "fxs" : "ether",
  "bal" : "ether",
  "stmatic" : "ether",
  "ldo" : "ether",
  "uni" : "ether",
  "jeur" : "ether",
  "op" : "ether",
  "wbtc" : "lovelace", # hack to get 8 decimals
  "usdc" : "mwei",
}

_rpc_url = {
  "polygon" : "https://polygon-rpc.com/",
  "optimism" : "https://rpc.ankr.com/optimism",
}

_chain_id = {
  "polygon" : 137,
  "optimism" : 10,
}

def get_chain_id():
  return _chain_id[get_chain()]

_w3 = None

def get_w3():
  global _w3
  if not _w3:
    print("before w3 creation")
    _w3 = Web3(Web3.HTTPProvider(_rpc_url[get_chain()]))
    print("after w3 creation")

    if not _w3.is_connected():
      print("w3 NOT connected")
      exit(-1)
    print("w3 is connected")
  return _w3

def my_toWei(quantity, unit):
  wei = Web3.toWei(quantity, unit)
  if unit == "lovelace":
    return wei * 100 
  return wei

def my_fromWei(wei, unit):
  quantity = Web3.from_wei(wei, unit)
  if unit == "lovelace":
    return quantity / 100
  return quantity

_contract = {}

def get_univ2_contract(swap_name):
  if swap_name in _contract:
    return _contract[swap_name]

  with open("abi/" + swap_name + "swap.abi.json") as f:
      abi_json = json.load(f)
  abi = abi_json["result"]
  address = get_contract_address(swap_name + "swap")
  _contract[swap_name] = get_w3().eth.contract(address=address, abi=abi)

  return _contract[swap_name]

def init_token_contract(token):
  if token in _contract:
    return 

  with open("abi/erc20.abi.json") as f:
      info_json = json.load(f)

  abi = info_json["result"]

  _contract[token] = get_w3().eth.contract(address=get_contract_address(token), abi=abi)

def check_balance_token(token, wallet = _bot_address):
  init_token_contract(token)

  balance_wei = _contract[token].functions.balanceOf(wallet).call()
  return my_fromWei(balance_wei, decimals[token])

def check_balance(tokens, wallet = _bot_address):
  balance = {}
  for token in tokens:
    balance[token] = check_balance_token(token, wallet)
    print("holding(", wallet, "):", balance[token], token)

  return balance

#with open("private_key_file") as f:
#  _b_k = f.read()

def sign_n_send_transaction(txn = {}, contract_fun = None):
  
  bot_nonce = get_w3().eth.get_transaction_count(_bot_address)
    
  if get_chain() == "polygon":
    gas_json = requests.get('https://gasstation-mainnet.matic.network/v2').json()

    if gas_json['standard']['maxFee'] > 500:
      print("gas too high:", gas_json['standard']['maxFee'])
      return

    maxFee_wei = Web3.toWei(gas_json['standard']['maxFee'], "gwei")
    maxPriorityFee_wei = Web3.toWei(gas_json['standard']['maxPriorityFee'], "gwei")
    
    print("gas maxFee:", gas_json['standard']['maxFee'], "nonce:", bot_nonce)

    if contract_fun:
      txn = contract_fun.buildTransaction(dict(
              nonce = bot_nonce,
              chainId = get_chain_id(),
              maxFeePerGas = maxFee_wei,
              maxPriorityFeePerGas = maxPriorityFee_wei,
              gas = 1000000,
            ))
    else:
      txn['nonce'] = bot_nonce
      txn['chainId'] = get_chain_id()
      
      # gas estimated manually (max.*FeePerGas) 
      # is better than gasPrice from 1inch
      txn.pop('gasPrice')
      txn['maxFeePerGas'] = maxFee_wei
      txn['maxPriorityFeePerGas'] = maxPriorityFee_wei
  
  elif get_chain() == "optimism":
    txn['nonce'] = bot_nonce
    txn['chainId'] = get_chain_id()
    txn['gasPrice'] = int(txn['gasPrice'])

  print("txn:", txn)

  signed_txn = get_w3().eth.account.sign_transaction(txn, _b_k)

  if _dry_run:
    print("dry run -> returning")
    return

  print("signed tx: ", signed_txn)

  txn_hash = get_w3().eth.send_raw_transaction(signed_txn.rawTransaction)
  print("txn hash: ", Web3.toHex(txn_hash))

  txn_receipt = get_w3().eth.wait_for_transaction_receipt(txn_hash)
  txn_info = get_w3().eth.getTransaction(txn_hash)

  print("txn receipt: ", txn_receipt)
  print("txn info: ", txn_info)
  print("--> txn status: ", txn_receipt['status'])


def swap_contracts_path(swap_path):
  path = []
  for token in swap_path:
    path.append(get_contract_address(token))
  return path


def sell_uniswapv2(pair, input_quantity, buy_stops, swap_name):
  
  buy_path = pair.copy()
  buy_path[1:1] = buy_stops
  
  input_quantity_wei = my_toWei(input_quantity, decimals[pair[0]])
  minimum_input_quantity_wei = int(input_quantity_wei * 0.003)

  contracts_path = swap_contracts_path(buy_path)
  
  deadline = int(time.time() + 60)
  
  fun = get_univ2_contract(swap_name).functions.swapExactTokensForTokens(
          input_quantity_wei,
          minimum_input_quantity_wei,
          contracts_path,
          _bot_address,
          deadline
        )
  
  sign_n_send_transaction(contract_fun = fun)

def _build_1inch_url(method):
  return "https://api.1inch.io/v5.0/" + str(get_chain_id()) + "/" + method

def _call_1inch_api(method, call_params):
  _url = _build_1inch_url(method)

  _scraper = cloudscraper.create_scraper()  
  
  call_json = _scraper.get(_url, params = call_params).json()
  #print(call_json)

  return call_json

def check_1inch_allowance(tokenName):
  allow_params = {
    "tokenAddress" : get_contract_address(tokenName),
    "walletAddress" : _bot_address,
  }

  allow_json = _call_1inch_api("approve/allowance", allow_params)
  #print(tokenName, "allow_json:", allow_json)

  try:

    allowance = int(allow_json["allowance"])
    print("check_1inch_allowance", tokenName, "allowance:", allowance)

    return allowance > 0

  except Exception as e:
    traceback.print_exc()
    print("check_1inch_allowance:",tokenName, allow_json)
    return False


def check_allowance(token, swap):
  if swap == "1inch":
    return check_1inch_allowance(token)

  print("don't know how to check allowance on", swap)
  return False

def check_1inch_price(pair, input_quantity):
  
 
  fromTokenName = pair[0]
  toTokenName = pair[1]

  input_quantity_wei = my_toWei(input_quantity, decimals[fromTokenName])
  fromTokenAddress = get_contract_address(fromTokenName)
  toTokenAddress = get_contract_address(toTokenName)

  quote_params = {
    "fromTokenAddress" : fromTokenAddress,
    "toTokenAddress" : toTokenAddress,
    "amount" : input_quantity_wei,
  }

  quote_json = _call_1inch_api("quote", quote_params)
 
  try:
    output_quantity_wei = int(quote_json['toTokenAmount'])
    output_quantity = my_fromWei(output_quantity_wei, decimals[toTokenName])

    print("1inch:",input_quantity, pair[0], "->", output_quantity, pair[-1])
    return output_quantity

  except Exception as e:
    traceback.print_exc()
    print("check_1inch_price:", quote_json)
    return 0

def sell_1inch(sell_token, sell_amount, buy_token):
  #print("1inch selling", sell_amount, sell_token, "into", buy_token)
  sell_amount_wei = my_toWei(sell_amount, decimals[sell_token])

  swap_params = {
    "fromTokenAddress" : get_contract_address(sell_token),
    "toTokenAddress" : get_contract_address(buy_token),
    "amount" : sell_amount_wei,
    "fromAddress" : _bot_address,
    "slippage" : 1,
  }

  print("swap_params:", swap_params)
  
  swap_call_json = _call_1inch_api("swap", swap_params) 
  
  try:
    swap_txn = swap_call_json["tx"]
    #print("swap_txn:", swap_txn)

    swap_txn['to'] = get_w3().toChecksumAddress(swap_txn['to']) 
    swap_txn['value'] = int(swap_txn['value'])
    swap_txn['gas'] = int(swap_txn['gas']*1.25)

    sign_n_send_transaction(swap_txn)
  
  except Exception as e:
    traceback.print_exc()
    print("not selling, swap_call_json:", swap_call_json)


def sell(pair, input_quantity, buy_stops, swap_name):
  print(swap_name, "selling", input_quantity, pair[0], "for", pair[1])
  
  if swap_name == "1inch":
    sell_1inch(pair[0], input_quantity, pair[1])
  
  else:
    sell_uniswapv2(pair, input_quantity, buy_stops, swap_name)

  check_balance(pair)


def get_amounts_out(path, input_quantity, swap):

  input_quantity_wei = my_toWei(input_quantity, decimals[path[0]])

  contracts_path = swap_contracts_path(path)
  
  get_amounts_out_result = get_univ2_contract(swap).functions.getAmountsOut(input_quantity_wei, contracts_path).call()

  input_amount = my_fromWei(get_amounts_out_result[0], decimals[path[0]])
  output_amount = my_fromWei(get_amounts_out_result[-1], decimals[path[-1]])

  print(swap, path, ":",input_amount, path[0], "->", output_amount, path[-1])
  
  return output_amount


def check_price(pair, input_quantity, buy_stops, buy_swap):
  if buy_swap == "1inch":
    return check_1inch_price(pair, input_quantity)
  
  buy_path = pair.copy()
  buy_path[1:1] = buy_stops

  buy_quantity = get_amounts_out(path=buy_path, input_quantity=input_quantity, swap=buy_swap)
  
  return buy_quantity

