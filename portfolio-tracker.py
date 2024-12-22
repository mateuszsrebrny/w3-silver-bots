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

polygon_balance = polygon.check_balance(["dai", "wmatic"], wallet)


optimism = BlockchainAccess("optimism", dry_run)

optimism_balance = optimism.check_balance(["dai", "op"], wallet)


print(polygon_balance)
print(optimism_balance)
