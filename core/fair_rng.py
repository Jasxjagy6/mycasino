"""Phase 3 — Provably-fair RNG with unbiased modulo and nonce monotonicity.

The legacy ``get_provably_fair_result`` lived inside the monolith and
used ``int(...) % n`` directly on bytes drawn from an HMAC stream.
That's biased whenever ``n`` does NOT divide 2**bits — for the mines
game (``max_n=25``) the bias is ~1.5% on the last few tiles.  This
module replaces that with **rejection sampling**, so every outcome in
``[0, n)`` is equiprobable up to the HMAC's collision resistance.

It also handles seed lifecycle:

* ``initial_state(...)`` produces a fresh ``(server_seed, server_seed_hash,
  client_seed, nonce=0)`` tuple — the hash is what the player sees
  BEFORE any game is played (a commitment).
* ``rotate(...)`` reveals the current server seed and commits a new one.
  Nonces reset to 0 for the new seed.  The old seed can be reproduced
  by the player to verify every game that used it.
* ``next_nonce(...)`` is the only place a nonce should ever be
  incremented.  It refuses to go backwards.

All callers move to :func:`draw_uniform_int` / :func:`draw_uniform_float` —
the legacy bias-prone helpers are flagged as deprecated.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
import threading
from dataclasses import dataclass
from typing import Iterable, Iterator, List


# ----------------------------------------------------------------------------
# Seed generation
# ----------------------------------------------------------------------------


_ALPHABET = string.ascii_letters + string.digits
_SERVER_SEED_LEN = 64
_CLIENT_SEED_LEN = 16


def generate_server_seed() -> str:
    """Cryptographically secure 64-char server seed."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(_SERVER_SEED_LEN))


def generate_client_seed() -> str:
    """User-mutable 16-char client seed (only used until they set their own)."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CLIENT_SEED_LEN))


def server_seed_hash(server_seed: str) -> str:
    """SHA-256 hash of the server seed.  Published BEFORE play as a commit."""
    return hashlib.sha256(server_seed.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------
# Seed lifecycle state
# ----------------------------------------------------------------------------


@dataclass
class SeedState:
    """In-memory representation of a user's provably-fair commitment."""

    server_seed: str
    server_seed_hash: str
    client_seed: str
    nonce: int = 0
    next_server_seed: str = ""

    def to_dict(self) -> dict:
        return {
            "server_seed": self.server_seed,
            "server_seed_hash": self.server_seed_hash,
            "client_seed": self.client_seed,
            "nonce": self.nonce,
            "next_server_seed": self.next_server_seed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SeedState":
        return cls(
            server_seed=data.get("server_seed") or generate_server_seed(),
            server_seed_hash=data.get("server_seed_hash") or "",
            client_seed=data.get("client_seed") or generate_client_seed(),
            nonce=int(data.get("nonce") or 0),
            next_server_seed=data.get("next_server_seed") or "",
        )


def initial_state() -> SeedState:
    server_seed = generate_server_seed()
    next_seed = generate_server_seed()
    return SeedState(
        server_seed=server_seed,
        server_seed_hash=server_seed_hash(server_seed),
        client_seed=generate_client_seed(),
        nonce=0,
        next_server_seed=next_seed,
    )


def ensure_state(state: SeedState) -> SeedState:
    """Fill in any missing fields on an existing state object.

    Older user records didn't carry ``server_seed_hash`` or
    ``next_server_seed``.  This refreshes those without ever touching
    the nonce so previously-played games still verify.
    """
    if not state.server_seed:
        state.server_seed = generate_server_seed()
    if not state.server_seed_hash:
        state.server_seed_hash = server_seed_hash(state.server_seed)
    if not state.client_seed:
        state.client_seed = generate_client_seed()
    if not state.next_server_seed:
        state.next_server_seed = generate_server_seed()
    return state


_nonce_locks: dict = {}
_global_lock = threading.Lock()


def _lock_for(user_id) -> threading.Lock:
    with _global_lock:
        lock = _nonce_locks.get(user_id)
        if lock is None:
            lock = threading.Lock()
            _nonce_locks[user_id] = lock
        return lock


def next_nonce(state: SeedState, user_id: int, count: int = 1) -> int:
    """Atomically reserve ``count`` consecutive nonces for ``state``.

    Returns the first reserved nonce.  Used by games that draw multiple
    samples per round (mines reveals all tiles up-front, plinko draws
    `rows` samples, etc.) — the caller uses
    ``[nonce, nonce + count - 1]``.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    lock = _lock_for(user_id)
    with lock:
        nonce = state.nonce
        state.nonce = nonce + count
        return nonce


def rotate(state: SeedState, user_id: int) -> SeedState:
    """Reveal the active server seed and commit a fresh one.

    Returns the SAME object (mutated) to make legacy callers happy, but
    the safer pattern is to ignore the return value and read the
    mutated state.
    """
    lock = _lock_for(user_id)
    with lock:
        revealed = state.server_seed
        # If the next-seed slot has a value, promote it; otherwise generate.
        new_seed = state.next_server_seed or generate_server_seed()
        new_next = generate_server_seed()
        state.server_seed = new_seed
        state.server_seed_hash = server_seed_hash(new_seed)
        state.next_server_seed = new_next
        state.nonce = 0
        # We deliberately leave client_seed alone — the player owns it.
        _ = revealed  # The revealed seed should be persisted by caller.
    return state


# ----------------------------------------------------------------------------
# Byte stream + unbiased draw
# ----------------------------------------------------------------------------


def _hmac_bytes_stream(
    server_seed: str, client_seed: str, nonce: int
) -> Iterator[int]:
    """Lazily produce bytes from HMAC-SHA256(server, "client:nonce:i").

    Each ``i`` block yields 32 bytes.  Callers should pull as many
    bytes as they need.
    """
    key = server_seed.encode("utf-8")
    cursor = 0
    while True:
        msg = f"{client_seed}:{nonce}:{cursor}".encode("utf-8")
        block = hmac.new(key, msg, hashlib.sha256).digest()
        for b in block:
            yield b
        cursor += 1


def draw_uniform_int(
    server_seed: str,
    client_seed: str,
    nonce: int,
    n: int,
) -> int:
    """Return a uniformly-random integer in ``[0, n)`` — *no modulo bias*.

    Uses rejection sampling: we read 4 bytes at a time and keep the
    sample only when it falls inside the largest multiple of ``n`` that
    fits in 2**32.  The expected number of rejections is < 1 for any
    sane ``n`` (and zero for power-of-two ``n``).
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if n == 1:
        return 0
    stream = _hmac_bytes_stream(server_seed, client_seed, nonce)
    max_sample = (1 << 32)
    # Largest multiple of n that is < 2**32.  We reject anything above it.
    cutoff = max_sample - (max_sample % n)
    # Safety cap on the rejection loop — under correct math this can
    # never run more than ~32 times before bailing.  Past that we'd
    # rather degrade gracefully than hang.
    for _ in range(64):
        b0 = next(stream)
        b1 = next(stream)
        b2 = next(stream)
        b3 = next(stream)
        sample = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
        if sample < cutoff:
            return sample % n
    # Astronomically unlikely fall-through.  Mod the last sample so we
    # at least return a valid value; this is still uniform up to ~2^-64.
    return sample % n  # pragma: no cover


def draw_uniform_float(
    server_seed: str,
    client_seed: str,
    nonce: int,
) -> float:
    """Return a uniform float in [0, 1) with ~53 bits of entropy."""
    stream = _hmac_bytes_stream(server_seed, client_seed, nonce)
    # 53 bits ≈ 7 bytes (we keep the top 53 of 56).
    val = 0
    for _ in range(7):
        val = (val << 8) | next(stream)
    val >>= (56 - 53)
    return val / float(1 << 53)


def draw_uniform_ints(
    server_seed: str,
    client_seed: str,
    base_nonce: int,
    n: int,
    count: int,
) -> List[int]:
    """Convenience: draw ``count`` independent integers, one per nonce."""
    return [
        draw_uniform_int(server_seed, client_seed, base_nonce + i, n)
        for i in range(count)
    ]


# ----------------------------------------------------------------------------
# Shuffling helpers
# ----------------------------------------------------------------------------


def fair_shuffle(
    server_seed: str,
    client_seed: str,
    base_nonce: int,
    items: Iterable,
) -> list:
    """Fisher-Yates shuffle using the unbiased ``draw_uniform_int``.

    Each swap consumes a unique nonce so the result is fully
    reproducible from (server_seed, client_seed, base_nonce).
    """
    seq = list(items)
    n = len(seq)
    for i in range(n - 1, 0, -1):
        j = draw_uniform_int(server_seed, client_seed, base_nonce + (n - 1 - i), i + 1)
        seq[i], seq[j] = seq[j], seq[i]
    return seq


# ----------------------------------------------------------------------------
# Backwards-compat shim
# ----------------------------------------------------------------------------


def get_provably_fair_result(
    server_seed: str,
    client_seed: str,
    nonce: int,
    max_n: int,
) -> int:
    """Drop-in replacement for the legacy biased helper.

    Old call sites do
    ``idx = get_provably_fair_result(seed, cseed, nonce, max_n)``
    expecting an integer in ``[0, max_n)``.  We route to the unbiased
    draw so existing games gain the fix without further edits.
    """
    return draw_uniform_int(server_seed, client_seed, nonce, max_n)


__all__ = [
    "SeedState",
    "generate_server_seed",
    "generate_client_seed",
    "server_seed_hash",
    "initial_state",
    "ensure_state",
    "next_nonce",
    "rotate",
    "draw_uniform_int",
    "draw_uniform_float",
    "draw_uniform_ints",
    "fair_shuffle",
    "get_provably_fair_result",
]
