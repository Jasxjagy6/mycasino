"""Tests for ``core.address_validation``."""

from __future__ import annotations

from core import address_validation as av


# --- BTC ---


def test_btc_p2pkh_valid():
    # genesis block coinbase output
    assert av.is_valid_btc_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")


def test_btc_p2sh_valid():
    assert av.is_valid_btc_address("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy")


def test_btc_bech32_v0_valid():
    assert av.is_valid_btc_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")


def test_btc_bech32m_v1_valid():
    # Example taproot address.
    assert av.is_valid_btc_address(
        "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"
    )


def test_btc_invalid():
    assert not av.is_valid_btc_address("")
    assert not av.is_valid_btc_address("1invalidaddress")
    assert not av.is_valid_btc_address("3J98t1WpEZ73CNmQviecrnyiWrnqRhWNL_")


# --- LTC ---


def test_ltc_p2pkh_valid():
    assert av.is_valid_ltc_address("LM2WMpR1Rp6j3Sa59cMXMs1SPzj9eXpGc1")


def test_ltc_bech32_valid():
    # Real LTC bech32 P2WPKH (v0) address with valid checksum.
    assert av.is_valid_ltc_address("ltc1qhzjptwpym9afcdjhs7jcz6fd0jma0l0rc0e5yr")


def test_ltc_invalid():
    assert not av.is_valid_ltc_address("XM2WMpR1Rp6j3Sa59cMXMs1SPzj9eXpGc1")


# --- TRX ---


def test_trx_valid():
    assert av.is_valid_trx_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")


def test_trx_invalid():
    assert not av.is_valid_trx_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjL")  # too short
    assert not av.is_valid_trx_address("AR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")  # wrong prefix


# --- SOL ---


def test_sol_valid():
    # Solana public key — 44 base58 chars decoding to 32 bytes.
    assert av.is_valid_sol_address("So11111111111111111111111111111111111111112")


def test_sol_invalid():
    assert not av.is_valid_sol_address("not-base58!")
    assert not av.is_valid_sol_address("short")


# --- TON ---


def test_ton_valid_workchain():
    # workchain:64-hex form
    raw = "0:" + "a" * 64
    assert av.is_valid_ton_address(raw)


def test_ton_invalid():
    assert not av.is_valid_ton_address("0:")
    assert not av.is_valid_ton_address("not-a-ton-address")


# --- EVM ---


def test_eth_lowercase_valid():
    assert av.is_valid_eth_address("0x" + "a" * 40)


def test_eth_uppercase_valid():
    assert av.is_valid_eth_address("0x" + "A" * 40)


def test_eth_invalid():
    assert not av.is_valid_eth_address("0x123")
    assert not av.is_valid_eth_address("123" + "a" * 40)


# --- Front door ---


def test_validate_routes_correctly():
    assert av.validate("BTC", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    assert not av.validate("BTC", "garbage")
    assert av.validate("TRX", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    assert not av.validate("TRX", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    assert av.validate("USDT", "0x" + "a" * 40)  # USDT routes to EVM
    assert av.validate("USDC", "0x" + "a" * 40)


def test_validate_unknown_chain_fails_closed():
    res = av.validate("XYZ", "0x" + "a" * 40)
    assert not res.valid
    assert res.reason and "unsupported" in res.reason


def test_validate_alias_lookup():
    assert av.validate("TRON", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    assert av.validate("SOLANA", "So11111111111111111111111111111111111111112")
