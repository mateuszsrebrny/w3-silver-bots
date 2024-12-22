#!/usr/bin/python3

from dotenv import load_dotenv
import os

from botweb3lib import BlockchainAccess

# Load environment variables from the .env file
load_dotenv()

chain = "polygon"
dry_run = True
wallet = os.getenv("WALLET")

print(f"wallet: {wallet}")

BlockchainAccess.load_config()

blockchain = BlockchainAccess(chain, dry_run)

balance = blockchain.check_balance(["dai", "wmatic"], wallet)
print(balance)
