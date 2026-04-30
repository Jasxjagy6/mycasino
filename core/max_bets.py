"""Auto-split from bot.py — core.max_bets."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def get_dynamic_max_bet_for_pvb(game_type: str = None) -> float:
    """Calculate max bet for PvB (Play vs Bot) mode specifically.
    Uses standard game limits since the house is at risk."""
    return get_dynamic_max_bet("originals", game_type)

