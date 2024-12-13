#!/usr/bin/python3

from dotenv import load_dotenv
import os

import botweb3lib

# Load environment variables from the .env file
load_dotenv()

chain = "polygon"
dry_run = True
wallet = os.getenv("WALLET")

print(f"wallet: {wallet}")


botweb3lib.setup_botweb3lib(chain, dry_run)

balance = botweb3lib.check_balance(["dai", "wmatic"], wallet)
print(balance)
