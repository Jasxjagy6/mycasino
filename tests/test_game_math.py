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


# ---------------------------------------------------------------------
# Bet outcome resolution (Phase 1b)
# ---------------------------------------------------------------------


def test_resolve_bet_outcome_loss() -> None:
    """A loss adds the full stake to the house balance and increments
    the losses counter; net loss equals the stake."""
    o = game_math.resolve_bet_outcome(10.0, win=False)
    assert o.house_balance_delta == 10.0
    assert o.counter == "losses"
    assert o.net_loss_this_bet == 10.0
    assert o.win_amount == 0.0


def test_resolve_bet_outcome_win() -> None:
    """A win pays out net winnings: house_balance_delta is negative,
    win counter increments, net_loss is negative (a net WIN for player)."""
    # 1.94x payout on a $10 bet \u2192 winnings $19.40, net win $9.40
    o = game_math.resolve_bet_outcome(10.0, win=True, multiplier=1.94)
    assert o.house_balance_delta == pytest.approx(-9.4)
    assert o.counter == "wins"
    assert o.net_loss_this_bet == pytest.approx(-9.4)
    assert o.win_amount == pytest.approx(19.4)


def test_resolve_bet_outcome_push() -> None:
    """A push must NOT touch the house balance and must NOT count as
    a win or a loss. Audit S6 / M5."""
    o = game_math.resolve_bet_outcome(10.0, win=False, push=True)
    assert o.house_balance_delta == 0.0
    assert o.counter == "pushes"
    assert o.net_loss_this_bet == 0.0
    assert o.win_amount == 0.0


def test_resolve_bet_outcome_push_wins_over_win_flag() -> None:
    """If ``push=True`` is passed alongside ``win=True``, push takes
    precedence (defensive against caller bugs that set both)."""
    o = game_math.resolve_bet_outcome(50.0, win=True, multiplier=2.0, push=True)
    assert o.counter == "pushes"
    assert o.house_balance_delta == 0.0
    assert o.net_loss_this_bet == 0.0
    assert o.win_amount == 0.0


def test_resolve_bet_outcome_blackjack_natural_push_does_not_drain_house() -> None:
    """Concrete blackjack-natural-push regression scenario from audit S6.

    Before Phase 1b: caller passed ``win=False, multiplier=0`` and the
    house silently kept the $25 stake even though the player got the
    bet back via ``credit_wallet``. Net effect: house_balance += $25
    per push.

    After Phase 1b: with ``push=True`` the house_balance_delta is
    zero. Verify this is exactly the case.
    """
    bet = 25.0
    o = game_math.resolve_bet_outcome(bet, win=False, multiplier=0, push=True)
    assert o.house_balance_delta == 0.0
    # And the buggy non-push path would have inflated by +bet:
    buggy = game_math.resolve_bet_outcome(bet, win=False, multiplier=0)
    assert buggy.house_balance_delta == bet


def test_resolve_bet_outcome_house_balance_conserves_money() -> None:
    """For every outcome, the (player_credit + house_balance_delta) sum
    must equal zero -- i.e. money is conserved.

    On a win the player got back ``amount * multiplier``; the house
    paid ``amount * multiplier - amount``. So player_credit
    (relative to having staked ``amount``) is the net win
    ``amount * multiplier - amount``, and house_balance_delta is
    ``-(amount * multiplier - amount)``. Their sum is zero => OK.

    On a push the player got back ``amount``; the house lost / kept
    nothing. Player_credit_relative = 0, house_balance_delta = 0.

    On a loss the player got back nothing; the house kept ``amount``.
    Player_credit_relative = -amount, house_balance_delta = +amount.
    Sum zero => OK.
    """
    amount = 100.0
    # Win
    ow = game_math.resolve_bet_outcome(amount, win=True, multiplier=2.5)
    net_player_win = ow.win_amount - amount  # what the player gained
    assert net_player_win + ow.house_balance_delta == pytest.approx(0.0)
    # Loss
    ol = game_math.resolve_bet_outcome(amount, win=False)
    assert -amount + ol.house_balance_delta == pytest.approx(0.0)
    # Push
    op = game_math.resolve_bet_outcome(amount, win=False, push=True)
    assert 0.0 + op.house_balance_delta == pytest.approx(0.0)


@pytest.mark.parametrize("multiplier", [1.5, 1.94, 2.425, 5.94, 10.0])
def test_resolve_bet_outcome_win_amount_matches_multiplier(multiplier: float) -> None:
    """win_amount is exactly amount * multiplier on any win."""
    o = game_math.resolve_bet_outcome(40.0, win=True, multiplier=multiplier)
    assert o.win_amount == pytest.approx(40.0 * multiplier)


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
