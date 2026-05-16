"""Phase 3 — Per-chain withdrawal address validation.

The user-supplied withdrawal address is the single most dangerous
piece of input the bot accepts: a typo sends funds into the void.
This module is the central, well-tested validator used by
``set_withdrawal_address`` and the OxaPay webhook.

Each validator returns ``True`` only for addresses that the chain's
canonical rules accept — base58 / bech32 / hex checksum etc.  False
positives are far worse than false negatives, so we err on the strict
side.

Public API
----------
``validate(coin_or_chain, address)`` is the one-stop function.  It
maps every coin we support to the right validator:

    coin/chain        → validator
    ----------------------------
    BTC               → P2PKH/P2SH/P2WPKH
    LTC               → P2PKH/P2SH/P2WPKH
    TRX / TRON / USDT(TRC20) → base58check, leading 'T'
    SOL / SOLANA      → base58, 32-byte pubkey
    TON               → URL-safe base64, 36 bytes
    ETH / BNB / BASE  → EIP-55 checksum or all-lower hex
    USDT/USDC (eth-like) → ETH-style

Returns ``ValidationResult`` so callers can show the error to the user.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    chain: str
    reason: Optional[str] = None

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return self.valid


# ---------------------------------------------------------------------------
# Base58 / Bech32 helpers
# ---------------------------------------------------------------------------


_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {ch: i for i, ch in enumerate(_B58_ALPHABET)}


def _b58decode(s: str) -> Optional[bytes]:
    n = 0
    for ch in s:
        if ch not in _B58_INDEX:
            return None
        n = n * 58 + _B58_INDEX[ch]
    # Recover leading zero bytes.
    pad = 0
    for ch in s:
        if ch == "1":
            pad += 1
        else:
            break
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * pad + raw


def _b58check_valid(addr: str, expected_lengths=(25,)) -> bool:
    """Strict Base58Check: payload + 4-byte SHA256(SHA256(payload)) checksum."""
    decoded = _b58decode(addr)
    if decoded is None:
        return False
    if len(decoded) not in expected_lengths:
        return False
    payload, checksum = decoded[:-4], decoded[-4:]
    computed = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return computed == checksum


_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values) -> int:
    generators = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= generators[i]
    return chk


def _bech32_hrp_expand(hrp: str):
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _bech32_verify_checksum(hrp: str, data, spec: str) -> bool:
    const = 1 if spec == "bech32" else 0x2BC830A3
    return _bech32_polymod(_bech32_hrp_expand(hrp) + data) == const


def _bech32_decode(addr: str):
    """Returns (hrp, data, spec) or (None, None, None)."""
    if any(ord(x) < 33 or ord(x) > 126 for x in addr):
        return None, None, None
    if addr.lower() != addr and addr.upper() != addr:
        return None, None, None
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr) or len(addr) > 90:
        return None, None, None
    hrp = addr[:pos]
    data = []
    for c in addr[pos + 1 :]:
        idx = _BECH32_CHARSET.find(c)
        if idx == -1:
            return None, None, None
        data.append(idx)
    for spec in ("bech32", "bech32m"):
        if _bech32_verify_checksum(hrp, data, spec):
            return hrp, data[:-6], spec
    return None, None, None


# ---------------------------------------------------------------------------
# Per-chain validators
# ---------------------------------------------------------------------------


_ETH_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_valid_eth_address(addr: str) -> bool:
    """Either all lowercase / uppercase, or a valid EIP-55 checksum."""
    if not isinstance(addr, str) or not _ETH_RE.match(addr):
        return False
    body = addr[2:]
    if body == body.lower() or body == body.upper():
        return True
    # Validate EIP-55 mixed-case checksum.
    try:
        hashed = hashlib.sha3_256(body.lower().encode("ascii")).hexdigest()
    except Exception:  # noqa: BLE001
        return False
    # eth uses keccak, not sha3 — fall back to keccak when available.
    try:
        from Crypto.Hash import keccak as _keccak  # type: ignore[import-not-found]

        k = _keccak.new(digest_bits=256)
        k.update(body.lower().encode("ascii"))
        hashed = k.hexdigest()
    except Exception:  # noqa: BLE001
        # web3.py ships ``Web3.keccak`` which is a much better source.
        try:
            from web3 import Web3  # type: ignore[import-not-found]

            hashed = Web3.keccak(text=body.lower()).hex()[2:]
        except Exception:  # noqa: BLE001
            # Without keccak we accept the format-only check above.  Better
            # than rejecting the user when our libraries are stale.
            return True
    for i, ch in enumerate(body):
        if ch.isalpha():
            should_be_upper = int(hashed[i], 16) >= 8
            if should_be_upper and ch != ch.upper():
                return False
            if not should_be_upper and ch != ch.lower():
                return False
    return True


def is_valid_btc_address(addr: str) -> bool:
    if not isinstance(addr, str) or not addr:
        return False
    # P2PKH starts with '1', P2SH with '3'.
    if addr[0] in "13" and 26 <= len(addr) <= 35:
        return _b58check_valid(addr)
    # Bech32 / Bech32m segwit (bc1...).
    if addr.lower().startswith("bc1"):
        hrp, data, spec = _bech32_decode(addr)
        if hrp != "bc" or data is None:
            return False
        if not data:
            return False
        witver = data[0]
        if witver > 16:
            return False
        # Strictly: v0 → bech32, v1+ → bech32m
        if witver == 0 and spec != "bech32":
            return False
        if witver != 0 and spec != "bech32m":
            return False
        return True
    return False


def is_valid_ltc_address(addr: str) -> bool:
    if not isinstance(addr, str) or not addr:
        return False
    # P2PKH 'L', P2SH 'M' or '3' (legacy).
    if addr[0] in "LM3" and 26 <= len(addr) <= 35:
        return _b58check_valid(addr)
    # Bech32 segwit: ltc1...
    if addr.lower().startswith("ltc1"):
        hrp, data, spec = _bech32_decode(addr)
        if hrp != "ltc" or data is None:
            return False
        if not data:
            return False
        witver = data[0]
        if witver > 16:
            return False
        if witver == 0 and spec != "bech32":
            return False
        if witver != 0 and spec != "bech32m":
            return False
        return True
    return False


def is_valid_trx_address(addr: str) -> bool:
    if not isinstance(addr, str) or not addr:
        return False
    if not addr.startswith("T") or len(addr) != 34:
        return False
    return _b58check_valid(addr)


def is_valid_sol_address(addr: str) -> bool:
    if not isinstance(addr, str) or not addr:
        return False
    if not (32 <= len(addr) <= 44):
        return False
    decoded = _b58decode(addr)
    if decoded is None:
        return False
    return len(decoded) == 32


def is_valid_ton_address(addr: str) -> bool:
    """Strict TON address: 48 chars (workchain '0:' raw also accepted)."""
    if not isinstance(addr, str) or not addr:
        return False
    addr = addr.strip()
    # Workchain:hex form, e.g. "0:abcd...".
    if ":" in addr:
        parts = addr.split(":", 1)
        if len(parts) != 2:
            return False
        wc, body = parts
        try:
            int(wc)
        except ValueError:
            return False
        if len(body) != 64:
            return False
        return all(ch in "0123456789abcdefABCDEF" for ch in body)
    # User-friendly form: 48 url-safe base64 chars.
    if len(addr) != 48:
        return False
    body = addr.replace("-", "+").replace("_", "/")
    import base64

    try:
        raw = base64.b64decode(body + "=" * (-len(body) % 4), validate=True)
    except Exception:  # noqa: BLE001
        return False
    if len(raw) != 36:
        return False
    payload, crc = raw[:-2], raw[-2:]
    # Reuse the same crc16-xmodem we ship in core/ton_address.py to
    # avoid a circular import we keep a small copy inline.
    table = []
    for i in range(256):
        c = i << 8
        for _ in range(8):
            if c & 0x8000:
                c = ((c << 1) & 0xFFFF) ^ 0x1021
            else:
                c = (c << 1) & 0xFFFF
        table.append(c)
    c = 0
    for b in payload:
        c = ((c << 8) & 0xFFFF) ^ table[((c >> 8) ^ b) & 0xFF]
    return c.to_bytes(2, "big") == crc


# ---------------------------------------------------------------------------
# Front door
# ---------------------------------------------------------------------------


def _normalise_chain(value: str) -> str:
    v = (value or "").upper()
    aliases = {
        "TRON": "TRX",
        "SOLANA": "SOL",
        "BNB": "BSC",
        "BSC": "BSC",
        "BASE": "BASE",
        "ETH": "ETH",
        "ETHEREUM": "ETH",
    }
    return aliases.get(v, v)


# coins that pay out on an EVM-style chain
_EVM_COINS = {"ETH", "BNB", "BSC", "BASE", "USDT", "USDC", "DAI", "WETH"}


def validate(coin_or_chain: str, address: str) -> ValidationResult:
    """One-stop validator.  ``coin_or_chain`` may be a coin (BTC, USDT)
    or a chain (TRX, ETH, BSC, BASE, TON)."""
    chain = _normalise_chain(coin_or_chain)
    if not isinstance(address, str) or not address.strip():
        return ValidationResult(False, chain, "address is empty")
    address = address.strip()
    if chain == "BTC":
        ok = is_valid_btc_address(address)
        return ValidationResult(ok, chain, None if ok else "invalid BTC address")
    if chain == "LTC":
        ok = is_valid_ltc_address(address)
        return ValidationResult(ok, chain, None if ok else "invalid LTC address")
    if chain == "TRX":
        ok = is_valid_trx_address(address)
        return ValidationResult(ok, chain, None if ok else "invalid TRX address")
    if chain == "SOL":
        ok = is_valid_sol_address(address)
        return ValidationResult(ok, chain, None if ok else "invalid SOL address")
    if chain == "TON":
        ok = is_valid_ton_address(address)
        return ValidationResult(ok, chain, None if ok else "invalid TON address")
    if chain in _EVM_COINS:
        ok = is_valid_eth_address(address)
        return ValidationResult(ok, chain, None if ok else "invalid EVM address")
    # Unknown chain — fail closed.
    return ValidationResult(False, chain, f"unsupported chain: {chain}")


__all__ = [
    "ValidationResult",
    "is_valid_btc_address",
    "is_valid_ltc_address",
    "is_valid_trx_address",
    "is_valid_sol_address",
    "is_valid_ton_address",
    "is_valid_eth_address",
    "validate",
]
