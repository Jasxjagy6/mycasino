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
