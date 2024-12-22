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

balance_polygon = polygon.check_balance(["dai", "wmatic"], wallet)


optimism = BlockchainAccess("optimism", dry_run)

balance_optimism = optimism.check_balance(["dai", "op"], wallet)


print(balance_polygon)
print(balance_optimism)
