"""Pure house-edge math for the casino games.

This module is intentionally **dependency-free** — it only imports from
the standard library.  That lets unit tests verify the math without
pulling in the rest of ``core.foundation`` (which needs ``web3``,
``telegram``, ``uvloop``, ``dotenv`` etc. just to import).

Every payout multiplier in the bot is derived from a single declared
house-edge constant (``HOUSE_EDGES`` in ``core/foundation.py``).  The
functions here are the single source of truth for those derivations:

* :func:`mines_multiplier`       — Mines payout for k safe picks with m mines.
* :func:`build_mines_table`      — Materialises the full Mines payout table.
* :func:`fair_two_outcome_multiplier`   — Fair payout for a 1/2 outcome.
* :func:`fair_six_outcome_multiplier`   — Fair payout for a 1/6 outcome.
* :func:`limbo_factor_for_edge`         — Limbo ``factor`` constant.

Audit references: S7 (coin-flip), S8 (dice exact), S9 (mines), S10 (limbo),
M1–M3 in ``upgrade_and_fixes.txt``.
"""

from __future__ import annotations

import math
from typing import Dict


__all__ = [
    "mines_multiplier",
    "build_mines_table",
    "fair_two_outcome_multiplier",
    "fair_six_outcome_multiplier",
    "limbo_factor_for_edge",
    "fair_blackjack_win_multiplier",
    "fair_blackjack_natural_multiplier",
    "effective_rakeback_edge",
    "BetOutcome",
    "resolve_bet_outcome",
    "BLACKJACK_WIN_FAIR",
    "BLACKJACK_NATURAL_FAIR",
    "MINES_BOARD_SIZE",
]


# Mines board is fixed at 25 cells in the game logic.
MINES_BOARD_SIZE: int = 25


def mines_multiplier(
    num_mines: int,
    safe_picks: int,
    edge: float,
    *,
    board_size: int = MINES_BOARD_SIZE,
) -> float:
    """Fair Mines payout multiplier for ``safe_picks`` safe tiles on a
    ``board_size``-cell board with ``num_mines`` mines, with the house
    edge ``edge`` applied.

    Formula:
        M(picks, mines) = (1 - edge) * C(N, picks) / C(N - mines, picks)

    Returns ``1.0`` for invalid coordinates (safe_picks == 0, or more
    picks than the number of safe cells, or mines outside the range).
    """
    if safe_picks <= 0:
        return 1.0
    if num_mines <= 0 or num_mines >= board_size:
        return 1.0
    safe_cells = board_size - num_mines
    if safe_picks > safe_cells:
        return 1.0
    try:
        fair = math.comb(board_size, safe_picks) / math.comb(safe_cells, safe_picks)
    except (ValueError, ZeroDivisionError):
        return 1.0
    return round(fair * (1.0 - edge), 2)


def build_mines_table(
    edge: float,
    *,
    board_size: int = MINES_BOARD_SIZE,
) -> Dict[int, Dict[int, float]]:
    """Materialise the full Mines payout table at the given ``edge``.

    Returns ``{num_mines: {safe_picks: multiplier}}`` for all valid
    (num_mines, safe_picks) combinations on a ``board_size``-cell board.
    """
    table: Dict[int, Dict[int, float]] = {}
    for mines in range(1, board_size):
        max_picks = board_size - mines
        row: Dict[int, float] = {}
        for picks in range(1, max_picks + 1):
            row[picks] = mines_multiplier(mines, picks, edge, board_size=board_size)
        table[mines] = row
    return table


def fair_two_outcome_multiplier(edge: float) -> float:
    """Fair payout for a 1/2 outcome (coin-flip / dice even-odd / dice high-low).

    ``2 * (1 - edge)`` rounded to 4 decimal places.
    """
    return round(2.0 * (1.0 - edge), 4)


def fair_six_outcome_multiplier(edge: float) -> float:
    """Fair payout for a 1/6 outcome (dice exact-number).

    ``6 * (1 - edge)`` rounded to 4 decimal places.
    """
    return round(6.0 * (1.0 - edge), 4)


def limbo_factor_for_edge(edge: float) -> float:
    """Limbo ``factor`` constant for the Stake-style ``result = factor /
    random_percentage`` algorithm.

    With ``random_percentage`` uniform on ``[1, 100]`` and the player
    winning ``bet * target`` iff ``result >= target``, the expected RTP
    is ``factor / 100`` — so ``factor = 100 * (1 - edge)`` delivers the
    declared house edge exactly.
    """
    return round(100.0 * (1.0 - edge), 4)


# ---------------------------------------------------------------------
# Blackjack constants (Phase 1c)
# ---------------------------------------------------------------------
#
# Standard blackjack rules pay 1:1 on a regular win (so the player
# receives back ``2 * bet`` including their stake) and 3:2 on a
# natural blackjack (so the player receives back ``2.5 * bet``).
# These are the published industry numbers — every house edge applied
# to blackjack should be a discount on top of these fair payouts.

BLACKJACK_WIN_FAIR: float = 2.0
BLACKJACK_NATURAL_FAIR: float = 2.5


def fair_blackjack_win_multiplier(edge: float) -> float:
    """Regular blackjack-win payout multiplier at the given ``edge``.

    ``2 * (1 - edge)`` rounded to 4 decimal places.
    """
    return round(BLACKJACK_WIN_FAIR * (1.0 - edge), 4)


def fair_blackjack_natural_multiplier(edge: float) -> float:
    """Natural-blackjack (3:2) payout multiplier at the given ``edge``.

    ``2.5 * (1 - edge)`` rounded to 4 decimal places.
    """
    return round(BLACKJACK_NATURAL_FAIR * (1.0 - edge), 4)


# ---------------------------------------------------------------------
# Effective rakeback edge (Phase 1c, audit M14)
# ---------------------------------------------------------------------


def effective_rakeback_edge(
    declared_edge: float,
    jackpot_rate: float = 0.0,
) -> float:
    """Return the portion of the declared house edge that the *house*
    actually keeps, after the jackpot pool skim.

    Rakeback is meant to rebate a fraction of what the house keeps.
    Because ``jackpot_rate`` of every bet flows to the jackpot pool
    (which is paid back to users via draws, see
    ``plugins/jackpot.py::_jackpot_credit``), the house's *retained*
    edge is ``declared_edge - jackpot_rate``. Without this adjustment
    the rakeback formula effectively rebates part of the jackpot pool
    on top of itself — double-rebating the player.

    Clamped to zero so a configuration where ``jackpot_rate >
    declared_edge`` doesn't generate negative rakeback (which would
    silently *charge* the player on every bet).
    """
    return max(0.0, declared_edge - jackpot_rate)


# ---------------------------------------------------------------------
# Bet outcome resolution (Phase 1b)
# ---------------------------------------------------------------------


class BetOutcome:
    """Pure-data result of resolving a bet for accounting purposes.

    Attributes
    ----------
    house_balance_delta:
        Signed change to ``bot_settings['house_balance']``. Positive on
        a loss (house keeps the bet), negative on a win (house pays
        out the net winnings), zero on a push.
    counter:
        Which counter on ``stats['bets']`` to increment
        (``"wins"``, ``"losses"`` or ``"pushes"``).
    net_loss_this_bet:
        Realised net loss for the player (used in weekly / monthly
        ``net_loss`` accumulators). Zero on push. Negative on a
        winning bet (i.e. net win is a negative loss).
    win_amount:
        Gross winnings credited back to the player (``amount *
        multiplier`` on a win, ``0`` otherwise). Used for leaderboard
        updates.
    """

    __slots__ = ("house_balance_delta", "counter", "net_loss_this_bet",
                 "win_amount")

    def __init__(
        self,
        *,
        house_balance_delta: float,
        counter: str,
        net_loss_this_bet: float,
        win_amount: float,
    ) -> None:
        self.house_balance_delta = house_balance_delta
        self.counter = counter
        self.net_loss_this_bet = net_loss_this_bet
        self.win_amount = win_amount

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"BetOutcome(house_balance_delta={self.house_balance_delta!r}, "
            f"counter={self.counter!r}, "
            f"net_loss_this_bet={self.net_loss_this_bet!r}, "
            f"win_amount={self.win_amount!r})"
        )

    def __eq__(self, other: object) -> bool:  # pragma: no cover - debug aid
        return (
            isinstance(other, BetOutcome)
            and self.house_balance_delta == other.house_balance_delta
            and self.counter == other.counter
            and self.net_loss_this_bet == other.net_loss_this_bet
            and self.win_amount == other.win_amount
        )


def resolve_bet_outcome(
    amount: float,
    win: bool,
    *,
    multiplier: float = 0.0,
    push: bool = False,
) -> BetOutcome:
    """Compute the accounting deltas for a settled bet.

    Phase 1b fix (audit S6 / M5): pushes must not be treated as losses.
    A push returns the player's stake (caller is expected to have done
    ``credit_wallet(bet)`` for the returned stake), so::

        house_balance_delta = 0
        counter             = "pushes"
        net_loss_this_bet   = 0
        win_amount          = 0

    On a win, the house pays out the net winnings::

        house_balance_delta = -(amount * multiplier - amount)
        counter             = "wins"
        net_loss_this_bet   = amount - amount * multiplier   (≤ 0)
        win_amount          = amount * multiplier

    On a loss, the house keeps the stake::

        house_balance_delta = +amount
        counter             = "losses"
        net_loss_this_bet   = +amount
        win_amount          = 0

    ``push=True`` always wins precedence over ``win``.
    """
    if push:
        return BetOutcome(
            house_balance_delta=0.0,
            counter="pushes",
            net_loss_this_bet=0.0,
            win_amount=0.0,
        )
    if win:
        winnings = amount * multiplier
        return BetOutcome(
            house_balance_delta=-(winnings - amount),
            counter="wins",
            net_loss_this_bet=amount - winnings,
            win_amount=winnings,
        )
    return BetOutcome(
        house_balance_delta=amount,
        counter="losses",
        net_loss_this_bet=amount,
        win_amount=0.0,
    )
