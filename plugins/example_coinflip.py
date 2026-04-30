"""Tiny coin-flip plugin used for runtime smoke-testing.

Adds ``/coinflip`` and ``/cf`` commands.  Useful as the simplest
possible plugin — start here when you want to confirm hot-reload is
wired up correctly: change the ``HEADS_EMOJI``, run ``/reload
example_coinflip``, and watch your next ``/coinflip`` reflect the new
emoji without a process restart.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

if TYPE_CHECKING:  # pragma: no cover
    from runtime.hot_reload import PluginContext

HEADS_EMOJI = "\U0001fa99"  # 🪙
TAILS_EMOJI = "\U0001fa99"


async def _cf(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    side = "heads" if random.random() < 0.5 else "tails"
    emoji = HEADS_EMOJI if side == "heads" else TAILS_EMOJI
    await update.message.reply_text(f"{emoji} {side}!")


def register(ctx: "PluginContext") -> None:
    ctx.add_handler(CommandHandler(["coinflip", "cf"], _cf))
