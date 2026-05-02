from scripts import generate_wallet


def test_generate_wallet_returns_address_and_private_key():
    wallet = generate_wallet.generate_wallet()

    assert wallet["address"].startswith("0x")
    assert len(wallet["address"]) == 42
    assert wallet["private_key"].startswith("0x")
    assert len(wallet["private_key"]) == 66
