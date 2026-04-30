"""Reference plugin: a minimal blackjack table.

Demonstrates the full plugin lifecycle:

* registers a ``/bj`` command handler;
* keeps per-user game state in ``ctx.state`` so it survives reloads;
* spawns a background watchdog task via ``ctx.spawn_task``;
* implements ``on_load`` / ``on_reload`` / ``on_unload`` lifecycle hooks.

The game logic is intentionally compact — this file is meant to be
copy-pasted as the starting point for a real plugin, not to replace
the full blackjack implementation in ``bot.py``.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, TYPE_CHECKING

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

if TYPE_CHECKING:  # pragma: no cover
    from runtime.hot_reload import PluginContext

logger = logging.getLogger(__name__)

CARDS = list(range(1, 14))  # 1=A, 11=J, 12=Q, 13=K
SUITS = ["\u2660", "\u2665", "\u2666", "\u2663"]  # ♠ ♥ ♦ ♣


def _card_value(card: int) -> int:
    if card == 1:
        return 11  # Ace high; soft-ace handling left to caller
    if card >= 10:
        return 10
    return card


def _hand_value(hand: List[int]) -> int:
    total = sum(_card_value(c) for c in hand)
    aces = hand.count(1)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _draw() -> int:
    return random.choice(CARDS)


def _format_hand(hand: List[int]) -> str:
    out = []
    for c in hand:
        suit = random.choice(SUITS)
        face = {1: "A", 11: "J", 12: "Q", 13: "K"}.get(c, str(c))
        out.append(f"{face}{suit}")
    return " ".join(out)


async def _bj_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    games: Dict[int, Dict[str, Any]] = context.bot_data.setdefault(
        "_example_blackjack_games", {}
    )
    user = update.effective_user
    if user is None:
        return
    state = games.get(user.id)
    args = (context.args or [])
    action = args[0].lower() if args else "deal"
    if action == "deal":
        player = [_draw(), _draw()]
        dealer = [_draw(), _draw()]
        games[user.id] = {"player": player, "dealer": dealer, "done": False}
        await update.message.reply_text(
            f"\U0001f0cf Blackjack: you have {_format_hand(player)} "
            f"({_hand_value(player)}). Dealer shows {_format_hand([dealer[0]])}.\n"
            "Reply with /bj hit or /bj stand."
        )
        return
    if state is None or state.get("done"):
        await update.message.reply_text("No active hand. Try /bj deal")
        return
    if action == "hit":
        state["player"].append(_draw())
        v = _hand_value(state["player"])
        if v > 21:
            state["done"] = True
            await update.message.reply_text(
                f"\U0001f4a5 Bust! {_format_hand(state['player'])} ({v})"
            )
        else:
            await update.message.reply_text(
                f"You: {_format_hand(state['player'])} ({v})"
            )
        return
    if action == "stand":
        while _hand_value(state["dealer"]) < 17:
            state["dealer"].append(_draw())
        pv = _hand_value(state["player"])
        dv = _hand_value(state["dealer"])
        state["done"] = True
        outcome = (
            "you win" if pv <= 21 and (dv > 21 or pv > dv)
            else "push" if pv == dv
            else "you lose"
        )
        await update.message.reply_text(
            f"You {_format_hand(state['player'])} ({pv}) vs "
            f"Dealer {_format_hand(state['dealer'])} ({dv}) — {outcome}."
        )
        return
    await update.message.reply_text("Usage: /bj [deal|hit|stand]")


async def _watchdog(state: Dict[str, Any]) -> None:
    """Tiny background loop demonstrating ctx.spawn_task lifecycle."""
    log = logging.getLogger("plugin.example_blackjack.watchdog")
    while True:
        await asyncio.sleep(60.0)
        state["ticks"] = state.get("ticks", 0) + 1
        log.debug("watchdog tick #%d", state["ticks"])


def register(ctx: "PluginContext") -> None:
    ctx.add_handler(CommandHandler("bj", _bj_cmd))
    ctx.spawn_task(_watchdog(ctx.state), name="example_blackjack:watchdog")


async def on_load(ctx: "PluginContext") -> None:
    ctx.logger().info("example_blackjack loaded")


async def on_reload(ctx: "PluginContext") -> None:
    ctx.logger().info(
        "example_blackjack reloaded (carry-over state keys: %s)",
        list(ctx.state.keys()),
    )


async def on_unload(ctx: "PluginContext") -> None:
    ctx.logger().info("example_blackjack unloaded")
