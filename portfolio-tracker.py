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

polygon = BlockchainAccess("polygon", dry_run)

tokens_polygon = polygon.get_all_tokens()

balance_polygon = polygon.check_balance(tokens_polygon, wallet)


optimism = BlockchainAccess("optimism", dry_run)
tokens_optimism = optimism.get_all_tokens()

balance_optimism = optimism.check_balance(tokens_optimism, wallet)


print(balance_polygon)
print(balance_optimism)
