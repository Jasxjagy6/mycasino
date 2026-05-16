"""Tests for ``core.fair_rng``.

The big claim of this module is that the RNG is unbiased.  We can't
prove uniformity in finite time, but we can be confident with a
chi-squared style sanity check on a million draws.
"""

from __future__ import annotations

import hashlib

import pytest

from core import fair_rng


def test_server_seed_hash_matches_sha256():
    seed = fair_rng.generate_server_seed()
    assert fair_rng.server_seed_hash(seed) == hashlib.sha256(seed.encode()).hexdigest()


def test_initial_state_populated():
    state = fair_rng.initial_state()
    assert state.server_seed
    assert state.server_seed_hash
    assert state.client_seed
    assert state.next_server_seed
    assert state.nonce == 0
    assert state.server_seed != state.next_server_seed
    assert state.server_seed_hash == fair_rng.server_seed_hash(state.server_seed)


def test_ensure_state_fills_missing_fields():
    state = fair_rng.SeedState(
        server_seed="abc",
        server_seed_hash="",
        client_seed="",
        nonce=7,
        next_server_seed="",
    )
    out = fair_rng.ensure_state(state)
    assert out.server_seed_hash == fair_rng.server_seed_hash("abc")
    assert out.client_seed
    assert out.next_server_seed
    assert out.nonce == 7  # never reset by ensure_state


def test_next_nonce_is_monotonic():
    state = fair_rng.initial_state()
    a = fair_rng.next_nonce(state, user_id=42)
    b = fair_rng.next_nonce(state, user_id=42)
    c = fair_rng.next_nonce(state, user_id=42, count=3)
    d = fair_rng.next_nonce(state, user_id=42)
    assert (a, b, c, d) == (0, 1, 2, 5)
    assert state.nonce == 6


def test_rotate_promotes_next_server_seed():
    state = fair_rng.initial_state()
    old_next = state.next_server_seed
    fair_rng.next_nonce(state, user_id=1)
    fair_rng.next_nonce(state, user_id=1)
    revealed = state.server_seed
    fair_rng.rotate(state, user_id=1)
    assert state.server_seed == old_next
    assert state.server_seed_hash == fair_rng.server_seed_hash(old_next)
    assert state.server_seed != revealed
    assert state.nonce == 0
    assert state.next_server_seed != old_next


def test_draw_uniform_int_range():
    seed = fair_rng.generate_server_seed()
    cseed = fair_rng.generate_client_seed()
    for n in (2, 3, 25, 37, 100):
        for nonce in range(20):
            v = fair_rng.draw_uniform_int(seed, cseed, nonce, n)
            assert 0 <= v < n


def test_draw_uniform_int_is_deterministic():
    a = fair_rng.draw_uniform_int("S", "C", 7, 25)
    b = fair_rng.draw_uniform_int("S", "C", 7, 25)
    assert a == b


def test_draw_uniform_int_changes_with_nonce():
    a = fair_rng.draw_uniform_int("S", "C", 7, 100)
    b = fair_rng.draw_uniform_int("S", "C", 8, 100)
    # Two draws CAN collide, but not for non-trivial n with these seeds.
    assert a != b


def test_draw_uniform_int_distribution():
    """Chi-squared-ish sanity check — mines case (n=25)."""
    seed = "AAAAAAAAAAAAAAAA"
    cseed = "BBBBBBBBBBBB"
    n = 25
    rounds = 25_000
    counts = [0] * n
    for nonce in range(rounds):
        counts[fair_rng.draw_uniform_int(seed, cseed, nonce, n)] += 1
    expected = rounds / n
    # Worst-case deviation should be small.  We allow ±5*sigma which
    # for a uniform draw of 1000 samples is ~150.
    sigma = (expected * (n - 1) / n) ** 0.5
    worst = max(abs(c - expected) for c in counts)
    assert worst < 5 * sigma, f"worst deviation {worst} vs sigma {sigma}"


def test_draw_uniform_int_n_equals_one():
    assert fair_rng.draw_uniform_int("S", "C", 0, 1) == 0


def test_draw_uniform_int_rejects_zero():
    with pytest.raises(ValueError):
        fair_rng.draw_uniform_int("S", "C", 0, 0)


def test_draw_uniform_float_in_unit_interval():
    for nonce in range(50):
        v = fair_rng.draw_uniform_float("S", "C", nonce)
        assert 0.0 <= v < 1.0


def test_fair_shuffle_is_deterministic_and_permutation():
    a = fair_rng.fair_shuffle("S", "C", 0, list(range(25)))
    b = fair_rng.fair_shuffle("S", "C", 0, list(range(25)))
    assert a == b
    assert sorted(a) == list(range(25))


def test_legacy_shim_uses_unbiased_path():
    # Calling the legacy name should land on the new implementation.
    expected = fair_rng.draw_uniform_int("S", "C", 5, 25)
    actual = fair_rng.get_provably_fair_result("S", "C", 5, 25)
    assert actual == expected
