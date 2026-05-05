from scripts import generate_wallet
from eth_account import Account


def test_generate_wallet_returns_address_and_private_key():
    wallet = generate_wallet.generate_wallet()

    assert wallet["address"].startswith("0x")
    assert len(wallet["address"]) == 42
    assert wallet["private_key"].startswith("0x")
    assert len(wallet["private_key"]) == 66
    assert len(wallet["mnemonic"].split()) == 12
    assert wallet["account_path"] == "m/44'/60'/0'/0/0"


def test_generate_wallet_mnemonic_recovers_same_address():
    wallet = generate_wallet.generate_wallet()

    Account.enable_unaudited_hdwallet_features()
    recovered = Account.from_mnemonic(wallet["mnemonic"])

    assert recovered.address == wallet["address"]
