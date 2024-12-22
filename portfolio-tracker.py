#!/usr/bin/python3

from dotenv import load_dotenv
import os

from botweb3lib import BlockchainAccess

# Load environment variables from the .env file
load_dotenv()

dry_run = True
wallet = os.getenv("WALLET")

print(f"wallet: {wallet}")

BlockchainAccess.load_config()

blockchains = {}
balances = {}


def print_balances(chain):
    print("chain:", chain)
    global balances
    for token, balance in balances[chain].items():
        print(f"  {token} : {balance}")


for chain in ["polygon", "optimism"]:

    blockchains[chain] = BlockchainAccess(chain, dry_run)

    tokens = blockchains[chain].get_all_tokens()

    balances[chain] = blockchains[chain].check_balance(tokens, wallet)

    print_balances(chain)
