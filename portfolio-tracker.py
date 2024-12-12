#!/usr/bin/python3

import botweb3lib

chain = "polygon"
dry_run = True

botweb3lib.setup_botweb3lib(chain, dry_run)

balance = botweb3lib.check_balance(["dai", "wmatic"])
print(balance)
