"""Reference plugin: a tiny dice game.

Demonstrates per-user wager state stored in ``ctx.state`` so balances
survive ``/reload example_dice`` without the player noticing.
"""

from __future__ import annotations

import random
from typing import Dict, TYPE_CHECKING

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

if TYPE_CHECKING:  # pragma: no cover
    from runtime.hot_reload import PluginContext


def _balances(state: Dict[str, object]) -> Dict[int, float]:
    bal = state.get("balances")
    if not isinstance(bal, dict):
        bal = {}
        state["balances"] = bal
    return bal  # type: ignore[return-value]


async def _make_dice_cmd(state: Dict[str, object]):
    async def _dice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            return
        bal = _balances(state)
        bal.setdefault(user.id, 100.0)
        try:
            wager = float(context.args[0]) if context.args else 1.0
        except ValueError:
            await update.message.reply_text("Usage: /dice <wager>")
            return
        if wager <= 0 or wager > bal[user.id]:
            await update.message.reply_text(
                f"Invalid wager. Balance: {bal[user.id]:.2f}"
            )
            return
        roll = random.randint(1, 6)
        if roll >= 4:
            bal[user.id] += wager
            outcome = f"\U0001f3b2 rolled {roll} — you won {wager:.2f}!"
        else:
            bal[user.id] -= wager
            outcome = f"\U0001f3b2 rolled {roll} — you lost {wager:.2f}."
        await update.message.reply_text(
            f"{outcome} New balance: {bal[user.id]:.2f}"
        )
    return _dice


def register(ctx: "PluginContext") -> None:
    # ``await`` is not allowed in register() because PTB hot-reload may
    # call it synchronously; instead we build the closure directly and
    # treat state.setdefault at call time.
    async def _dice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None:
            return
        bal = _balances(ctx.state)
        bal.setdefault(user.id, 100.0)
        try:
            wager = float(context.args[0]) if context.args else 1.0
        except (ValueError, IndexError):
            await update.message.reply_text("Usage: /dice <wager>")
            return
        if wager <= 0 or wager > bal[user.id]:
            await update.message.reply_text(
                f"Invalid wager. Balance: {bal[user.id]:.2f}"
            )
            return
        roll = random.randint(1, 6)
        if roll >= 4:
            bal[user.id] += wager
            outcome = f"\U0001f3b2 rolled {roll} — you won {wager:.2f}!"
        else:
            bal[user.id] -= wager
            outcome = f"\U0001f3b2 rolled {roll} — you lost {wager:.2f}."
        await update.message.reply_text(
            f"{outcome} New balance: {bal[user.id]:.2f}"
        )

    ctx.add_handler(CommandHandler(["dice", "rolld"], _dice))
