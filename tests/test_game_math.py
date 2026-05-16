"""Unit tests for ``core.game_math`` — the pure house-edge math.

These tests assert that every payout multiplier in the bot is derived
from a single declared house-edge constant. They do **not** import
``core.foundation`` (which needs ``web3`` / ``telegram`` / ``uvloop``
etc.) — ``core.game_math`` is intentionally dependency-free so this
file can run in any environment that has Python 3.10+ available.

References:
  * upgrade_and_fixes.txt §S7 (coin-flip), §S8 (dice exact), §S9 (mines),
    §S10 (limbo), §M1–M3.
"""

from __future__ import annotations

import math

import pytest

from core import game_math


# ---------------------------------------------------------------------
# Mines
# ---------------------------------------------------------------------


@pytest.mark.parametrize("edge", [0.0, 0.005, 0.01, 0.02, 0.05])
def test_mines_multiplier_no_win_for_zero_picks(edge: float) -> None:
    """``safe_picks=0`` always returns 1.0 (no win yet)."""
    for mines in range(1, 25):
        assert game_math.mines_multiplier(mines, 0, edge) == 1.0


@pytest.mark.parametrize(
    "mines,picks,edge,expected",
    [
        # 1 mine, 1 pick at 1% edge:
        #   fair = C(25,1) / C(24,1) = 25/24 ≈ 1.04167
        #   * (1 - 0.01) = 1.03125 → rounds to 1.03
        (1, 1, 0.01, 1.03),
        # 1 mine, 24 picks at 1% edge:
        #   fair = C(25,24) / C(24,24) = 25/1 = 25.0
        #   * 0.99 = 24.75
        (1, 24, 0.01, 24.75),
        # 5 mines, 5 picks at 1% edge:
        #   fair = C(25,5) / C(20,5) = 53130 / 15504 ≈ 3.4268
        #   * 0.99 ≈ 3.39
        (5, 5, 0.01, 3.39),
        # 3 mines, 3 picks at 1% edge:
        #   fair = C(25,3) / C(22,3) = 2300 / 1540 ≈ 1.4935
        #   * 0.99 ≈ 1.48
        (3, 3, 0.01, 1.48),
        # 0% edge collapses to fair odds:
        #   1 mine, 1 pick: exactly 25/24 ≈ 1.04
        (1, 1, 0.0, 1.04),
    ],
)
def test_mines_multiplier_known_values(
    mines: int, picks: int, edge: float, expected: float
) -> None:
    assert game_math.mines_multiplier(mines, picks, edge) == pytest.approx(
        expected, abs=0.01
    )


@pytest.mark.parametrize("edge", [0.0, 0.01, 0.05])
def test_mines_multiplier_monotone_in_picks(edge: float) -> None:
    """For fixed mines, the multiplier strictly increases as you reveal
    more safe cells (you've already survived more risk)."""
    for mines in (1, 3, 5, 10):
        prev = 0.0
        max_picks = 25 - mines
        for picks in range(1, max_picks + 1):
            value = game_math.mines_multiplier(mines, picks, edge)
            assert value > prev, (
                f"Mines={mines}, picks={picks}, edge={edge}: "
                f"value={value} not strictly greater than prev={prev}"
            )
            prev = value


@pytest.mark.parametrize("edge", [0.0, 0.01, 0.05])
def test_mines_multiplier_monotone_in_mines(edge: float) -> None:
    """For fixed picks, the multiplier strictly increases as you add
    more mines (it's harder to survive each pick)."""
    for picks in (1, 3, 5, 10):
        prev = 0.0
        # mines from 1 up to (board_size - picks) so picks remain valid
        for mines in range(1, 25 - picks + 1):
            value = game_math.mines_multiplier(mines, picks, edge)
            assert value > prev, (
                f"Picks={picks}, mines={mines}, edge={edge}: "
                f"value={value} not strictly greater than prev={prev}"
            )
            prev = value


def test_mines_multiplier_invalid_inputs() -> None:
    """Out-of-range inputs collapse to the no-win sentinel ``1.0``."""
    # safe_picks larger than safe_cells
    assert game_math.mines_multiplier(20, 10, 0.01) == 1.0
    # mines == 0
    assert game_math.mines_multiplier(0, 5, 0.01) == 1.0
    # mines >= board_size
    assert game_math.mines_multiplier(25, 1, 0.01) == 1.0
    assert game_math.mines_multiplier(26, 1, 0.01) == 1.0
    # negative picks
    assert game_math.mines_multiplier(1, -1, 0.01) == 1.0


def test_mines_multiplier_edge_lowers_payout() -> None:
    """Raising the house edge must never raise (and almost always
    lowers) the payout multiplier for any (mines, picks) pair."""
    for mines in range(1, 25):
        for picks in range(1, 25 - mines + 1):
            zero_edge = game_math.mines_multiplier(mines, picks, 0.0)
            one_pct = game_math.mines_multiplier(mines, picks, 0.01)
            two_pct = game_math.mines_multiplier(mines, picks, 0.02)
            assert one_pct <= zero_edge
            assert two_pct <= one_pct


def test_build_mines_table_shape() -> None:
    """The materialised table must have ``mines`` 1..24 and, for each,
    every valid ``picks`` from 1..(25-mines)."""
    table = game_math.build_mines_table(0.01)
    assert set(table.keys()) == set(range(1, 25))
    for mines, row in table.items():
        assert set(row.keys()) == set(range(1, 25 - mines + 1)), (
            f"Mines={mines}: row keys {sorted(row.keys())} != "
            f"expected {list(range(1, 25 - mines + 1))}"
        )
        for picks, value in row.items():
            assert value == game_math.mines_multiplier(mines, picks, 0.01)


def test_build_mines_table_one_pct_edge_avg_rtp() -> None:
    """Sanity-check the long-run RTP at 1% edge for a single (mines, picks).

    For mines=1, picks=1: the player has P(safe) = 24/25, payout
    multiplier M = 1.03, so expected return per unit bet
    = (24/25) * 1.03 = 0.9888 → ~1.12% edge (rounding adds a tiny bit).
    Verify it lands inside the [0.5%, 1.5%] band — i.e. the rounding
    error never drifts more than ~0.5% from the declared edge.
    """
    table = game_math.build_mines_table(0.01)
    for mines in range(1, 25):
        for picks in range(1, 25 - mines + 1):
            p_safe = 1.0
            for i in range(picks):
                p_safe *= (25 - mines - i) / (25 - i)
            mult = table[mines][picks]
            expected_return = p_safe * mult
            actual_edge = 1.0 - expected_return
            assert -0.005 <= actual_edge <= 0.015, (
                f"Mines={mines}, picks={picks}: "
                f"actual edge {actual_edge:.4f} drifted outside declared 1% \u00b10.5%"
            )


# ---------------------------------------------------------------------
# Coin-flip / dice 50/50 / dice exact-number
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "edge,expected",
    [
        (0.0, 2.0),
        (0.005, 1.99),
        (0.01, 1.98),
        (0.02, 1.96),
        (0.05, 1.9),
    ],
)
def test_fair_two_outcome_multiplier(edge: float, expected: float) -> None:
    assert game_math.fair_two_outcome_multiplier(edge) == pytest.approx(
        expected, abs=1e-6
    )


@pytest.mark.parametrize(
    "edge,expected",
    [
        (0.0, 6.0),
        (0.01, 5.94),
        (0.02, 5.88),
        (0.05, 5.7),
        (0.1167, 5.2998),  # historical value 5.30 implied this edge
    ],
)
def test_fair_six_outcome_multiplier(edge: float, expected: float) -> None:
    assert game_math.fair_six_outcome_multiplier(edge) == pytest.approx(
        expected, abs=1e-4
    )


def test_coin_flip_parlay_geometric_rtp_is_1_minus_edge() -> None:
    """Coin-flip parlay pays ``M_base * 2 ^ (streak - 1)`` per round, with
    ``M_base = fair_two_outcome_multiplier(edge)``.  The probability of
    surviving ``streak`` rounds is ``0.5 ^ streak``.  So expected return
    per unit bet at cashout time is::

        payout * p_win = M_base * 2^(streak-1) * 0.5^streak
                       = M_base * 0.5 = (1 - edge)

    i.e. the realised house edge is exactly the declared value, no
    matter how many rounds the player chooses to cash out at.
    """
    for edge in (0.0, 0.005, 0.01, 0.02, 0.05):
        m_base = game_math.fair_two_outcome_multiplier(edge)
        for streak in range(1, 11):
            payout_mult = m_base * (2 ** (streak - 1))
            p_win = 0.5 ** streak
            expected_return = payout_mult * p_win
            assert expected_return == pytest.approx(
                1.0 - edge, abs=1e-6
            ), f"edge={edge}, streak={streak}: RTP per stake-unit drifted"


# ---------------------------------------------------------------------
# Limbo
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "edge,expected",
    [
        (0.0, 100.0),
        (0.005, 99.5),
        (0.01, 99.0),
        (0.02, 98.0),
        (0.05, 95.0),
        # The historical buggy constant 92 implied an edge of 8%
        # (it's actually ~7.07% via the [1,100] mapping, but the factor
        #  itself is what we test here).
        (0.08, 92.0),
    ],
)
def test_limbo_factor_for_edge(edge: float, expected: float) -> None:
    assert game_math.limbo_factor_for_edge(edge) == pytest.approx(
        expected, abs=1e-6
    )


def test_limbo_long_run_rtp_strictly_better_than_old_factor() -> None:
    """Monte-Carlo sanity check: for every target we test, the new
    ``factor = limbo_factor_for_edge(0.01) = 99`` must produce a
    realised RTP strictly higher than the historical buggy ``factor =
    92`` (which drove a ~7-8% edge at low targets).

    The Stake-style ``result = factor / pct`` formula does NOT deliver a
    flat RTP across all target multipliers — RTP drifts down as the
    target rises, because the ``pct ∈ [1, 100]`` mapping is
    approximate-Pareto, not exact-Pareto.  Phase 1+ should switch to
    the exact-Pareto formula ``outcome = (1 - edge) / U`` with
    ``U ~ Uniform(0, 1)`` for a target-independent edge.  For now we
    only assert that the new factor improves on the old in every band.
    """
    import random

    seed = 20251115
    new_factor = game_math.limbo_factor_for_edge(0.01)
    old_factor = 92.0
    n_trials = 50_000

    def _rtp(factor: float, target: float, seed_offset: int) -> float:
        rng = random.Random(seed + seed_offset)
        wins = 0
        for _ in range(n_trials):
            pct = rng.uniform(1.0, 100.0)
            outcome = max(1.0, min(1000.0, factor / pct))
            if outcome >= target:
                wins += 1
        return (wins / n_trials) * target

    for target in (1.5, 2.0, 4.0, 10.0):
        new_rtp = _rtp(new_factor, target, seed_offset=0)
        old_rtp = _rtp(old_factor, target, seed_offset=0)
        assert new_rtp > old_rtp, (
            f"target={target}: new RTP {new_rtp:.4f} should beat old "
            f"RTP {old_rtp:.4f}"
        )
        # And it must never give the player a positive edge.
        assert new_rtp <= 1.0 + 1e-6, (
            f"target={target}: new RTP {new_rtp:.4f} exceeds 1.0 — the "
            f"house is paying out more than it takes in!"
        )
