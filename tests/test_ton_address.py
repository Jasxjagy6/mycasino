"""Tests for ``core.ton_address``.

We exercise SLIP-0010 derivation (no external libs needed) and the
public-key → address derivation; the result is checked to be
deterministic and to match expected lengths.
"""

from __future__ import annotations

import pytest

from core import ton_address


SAMPLE_MNEMONIC = (
    "abandon abandon abandon abandon abandon abandon "
    "abandon abandon abandon abandon abandon about"
)


def test_derivation_path_format():
    assert ton_address.derivation_path(0) == "m/44'/607'/0'/0/0"
    assert ton_address.derivation_path(42) == "m/44'/607'/0'/0/42"


def test_mnemonic_to_seed_deterministic():
    a = ton_address._mnemonic_to_seed(SAMPLE_MNEMONIC)
    b = ton_address._mnemonic_to_seed(SAMPLE_MNEMONIC)
    assert a == b
    assert len(a) == 64


def test_slip10_derive_path_deterministic():
    seed = ton_address._mnemonic_to_seed(SAMPLE_MNEMONIC)
    a = ton_address._slip10_derive_path(seed, "m/44'/607'/0'/0/0")
    b = ton_address._slip10_derive_path(seed, "m/44'/607'/0'/0/0")
    assert a == b
    assert len(a) == 32


def test_slip10_derive_path_different_indexes_differ():
    seed = ton_address._mnemonic_to_seed(SAMPLE_MNEMONIC)
    a = ton_address._slip10_derive_path(seed, "m/44'/607'/0'/0/0")
    b = ton_address._slip10_derive_path(seed, "m/44'/607'/0'/0/1")
    assert a != b


def test_crc16_xmodem_known_value():
    # Standard reference: CRC-16/XMODEM of "123456789" == 0x31C3
    assert ton_address._crc16_xmodem(b"123456789").hex() == "31c3"


def test_derive_ton_address_returns_object_or_none():
    """Either we get a properly-shaped TonDerivation, or None when no
    Ed25519 library is available.  Both are acceptable outcomes — we
    just need to make sure the code path doesn't raise."""
    result = ton_address.derive_ton_address(SAMPLE_MNEMONIC, 0)
    if result is None:
        pytest.skip("No Ed25519 library available — derivation skipped")
    assert isinstance(result, ton_address.TonDerivation)
    assert result.derivation_path == "m/44'/607'/0'/0/0"
    assert len(result.public_key_hex) == 64
    assert len(result.private_key_hex) == 64
    assert result.address


def test_derive_ton_address_is_deterministic():
    a = ton_address.derive_ton_address(SAMPLE_MNEMONIC, 0)
    b = ton_address.derive_ton_address(SAMPLE_MNEMONIC, 0)
    if a is None or b is None:
        pytest.skip("No Ed25519 library available — derivation skipped")
    assert a.address == b.address
    assert a.public_key_hex == b.public_key_hex


def test_derive_ton_address_index_changes_output():
    a = ton_address.derive_ton_address(SAMPLE_MNEMONIC, 0)
    b = ton_address.derive_ton_address(SAMPLE_MNEMONIC, 1)
    if a is None or b is None:
        pytest.skip("No Ed25519 library available — derivation skipped")
    assert a.public_key_hex != b.public_key_hex
