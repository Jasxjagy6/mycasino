"""Win broadcaster — posts every game win to the configured channel via a
helper bot so the main bot never spends its own rate-limit budget on
broadcast traffic.

Hot-reloadable: edits land via `/reload` (importlib.reload). Plugin code
calls ``schedule_win_broadcast`` (a fire-and-forget thin wrapper) — that
in turn `enqueue`s onto a bounded asyncio.Queue drained by a singleton
worker task running on the main event loop. Bounded queue + helper-bot
isolation keeps a flood from blocking gameplay.

Set ``WIN_BROADCAST_CHANNEL_ID`` to a `-100…` channel id (preferred) or a
``@channelusername``. Empty / unset disables broadcasting.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from core.foundation import (
    CURRENCY_SYMBOLS,
    HELPER_BOT_TOKEN,
    WIN_BROADCAST_CHANNEL_ID as _CFG_WIN_BROADCAST_CHANNEL_ID,
    format_display_amount,
    get_display_currency,
    get_privacy_display_name,
    helper_bot,
    helper_bots,
    pe,
    user_stats,
)

try:
    from telegram.constants import ParseMode
except Exception:  # pragma: no cover
    class ParseMode:
        HTML = "HTML"

# Resolve channel id / username — env var takes precedence so ops can flip
# the destination without a code deploy.
WIN_CHANNEL = (
    os.environ.get("WIN_BROADCAST_CHANNEL_ID")
    or _CFG_WIN_BROADCAST_CHANNEL_ID
    or "-1003848853417"
).strip() or None

# How many wins to keep in flight before we start dropping oldest. Under a
# 5000+ concurrent user spike this is the back-pressure valve that keeps
# the broadcaster from fanning out and stealing the bot's CPU.
_QUEUE_MAXSIZE = 4096

# Singleton state. Module-level so `/reload core.win_broadcaster` keeps
# the queue and worker task alive until they're explicitly torn down.
_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_dropped = 0  # observability counter; surfaced via /runtimestatus eventually
_round_robin_idx = 0  # spreads load across all configured helper bots


# Map internal game_type strings (and game_id prefixes) to display names.
# Game IDs in this casino are formatted ``<PREFIX>-<datetime>-<rand>`` so
# the prefix uniquely identifies the originating game — we lowercase
# both sides before lookup.
_GAME_DISPLAY_NAMES = {
    "blackjack": "Blackjack",
    "bj": "Blackjack",
    "dice": "Dice",
    "dr": "Dice Race",
    "rush": "Dice Rush",
    "flip": "Coin Flip",
    "cf": "Coin Flip",
    "predict": "Predict",
    "pdt": "Predict",
    "slots": "Slots",
    "sl": "Slots",
    "roulette": "Roulette",
    "rl": "Roulette",
    "rt": "Roulette",
    "mines": "Mines",
    "mns": "Mines",
    "tower": "Tower",
    "twr": "Tower",
    "limbo": "Limbo",
    "lmb": "Limbo",
    "keno": "Keno",
    "highlow": "High-Low",
    "hl": "High-Low",
    "plinko": "Plinko",
    "pl": "Plinko",
    "plk": "Plinko",
    "wheel": "Wheel",
    "wh": "Wheel",
    "scratch": "Scratch",
    "sc": "Scratch",
    "crash": "Crash",
    "cr": "Crash",
    "coinchain": "CoinChain",
    "cc": "CoinChain",
    "chicken": "Chicken Road",
    "chicken_road": "Chicken Road",
    "ckn": "Chicken Road",
    "matches": "Match",
    "match": "Match",
    "pvp": "PvP Match",
    "pvb": "PvB Match",
    "raffle": "Raffle",
    "rfl": "Raffle",
}


def _display_game_name(game_type: str) -> str:
    if not game_type:
        return "Game"
    g = str(game_type).strip().lower()
    return _GAME_DISPLAY_NAMES.get(g, g.replace("_", " ").title() or "Game")


def _resolve_username(user_id: int) -> str:
    """Return the user's visible name for the broadcast.

    Honours privacy mode — returns "Hidden User" if the user has it on.
    Otherwise prefers Telegram username (without @) → first name → "Player N".
    """
    stats = user_stats.get(user_id, {}) or {}
    info = stats.get("userinfo", {}) or {}
    raw = info.get("username") or info.get("first_name") or f"Player {user_id}"
    raw = str(raw).lstrip("@").strip() or f"Player {user_id}"
    return get_privacy_display_name(user_id, raw)


def _pick_helper_bot():
    """Round-robin across *all* configured helper bots so the broadcast
    load is spread across 6 separate Bot API rate-limit budgets instead
    of hammering one."""
    global _round_robin_idx
    pool = helper_bots or ([helper_bot] if helper_bot else [])
    if not pool:
        return None
    bot = pool[_round_robin_idx % len(pool)]
    _round_robin_idx = (_round_robin_idx + 1) % max(len(pool), 1)
    return bot


def _format_win_message(
    user_id: int,
    game_type: str,
    bet_usd: float,
    win_usd: float,
    multiplier: float,
) -> str:
    name = _resolve_username(user_id)
    cur = get_display_currency(user_id)
    sym = CURRENCY_SYMBOLS.get(cur, "$")
    win_str = format_display_amount(float(win_usd), cur, with_symbol=True)
    bet_str = format_display_amount(float(bet_usd), cur, with_symbol=True)
    game_str = _display_game_name(game_type)
    mult_str = f"{float(multiplier):.2f}x" if multiplier and multiplier > 0 else ""
    head = f"{pe('win')} <b>BIG WIN!</b> 🎉"
    body = (
        f"\n\n{pe('user')} <b>{name}</b>\n"
        f"{pe('game')} {game_str}\n"
        f"{pe(_currency_emoji_key(cur))} Won: <b>{win_str}</b>"
    )
    if mult_str:
        body += f"  ({mult_str})"
    if bet_usd and bet_usd > 0:
        body += f"\n💸 Bet: {bet_str}"
    return head + body


def _currency_emoji_key(cur: str) -> str:
    """Map a display currency to its premium emoji key (all fiats fall back
    to ``dollar`` which is the universal premium 💲 in our table)."""
    return "dollar"


def _ensure_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    return _queue


# Track which helper Bot instances have had `initialize()` called on
# them. Direct `Bot(token=...)` instances (constructed outside an
# Application) are NOT auto-initialised by PTB v20+, so the first
# `send_message()` raises "Bot is not properly initialized". Initialising
# is idempotent at the http-pool level — we just need to do it once per
# Bot object.
_initialised_bots: set = set()


async def _ensure_bot_initialised(b) -> None:
    if b is None:
        return
    if id(b) in _initialised_bots:
        return
    init = getattr(b, "initialize", None)
    if init is None:
        _initialised_bots.add(id(b))
        return
    try:
        await init()
    except Exception:  # noqa: BLE001 — already-initialised raises here
        pass
    _initialised_bots.add(id(b))


async def _send_one(payload: dict) -> None:
    """Send a single broadcast. Errors are logged but never raised — a
    win broadcast must never disrupt gameplay."""
    if not WIN_CHANNEL:
        return
    text = payload["text"]
    last_err: Optional[Exception] = None
    # Try ``_pick_helper_bot()`` first then any remaining helpers in the
    # pool. Use ``id()``-based dedup because ``Bot.__eq__`` in PTB v20+
    # accesses ``self.token`` and raises "Bot is not properly
    # initialized" on freshly-constructed Bot instances — that's the
    # root of the broadcast crash we kept seeing.
    pool = helper_bots or ([helper_bot] if helper_bot else [])
    candidates: list = []
    seen_ids: set = set()
    bot = _pick_helper_bot()
    if bot is not None:
        candidates.append(bot)
        seen_ids.add(id(bot))
    for b in pool:
        if id(b) not in seen_ids:
            candidates.append(b)
            seen_ids.add(id(b))
    for i, b in enumerate(candidates):
        try:
            await _ensure_bot_initialised(b)
        except Exception as e:
            logging.debug("Win broadcast init helper %d failed: %r", i, e)
            last_err = e
            continue
        try:
            await b.send_message(
                chat_id=WIN_CHANNEL,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

            return
        except Exception as e:
            last_err = e
            logging.debug("Win broadcast helper %d send failed: %r", i, e)
            # Try the next helper. Most "Forbidden: bot is not a member"
            # errors mean THIS particular helper hasn't been added to the
            # channel — the next one might be.
            continue
    if last_err is not None:
        logging.warning("Win broadcast: all helpers failed: %r", last_err)


async def _drain_queue() -> None:
    q = _ensure_queue()
    global _dropped
    while True:
        payload = await q.get()
        try:
            await _send_one(payload)
        except Exception as e:  # pragma: no cover — defensive
            logging.error("Win broadcast worker crashed sending one: %s", e)
        finally:
            q.task_done()


def _ensure_worker() -> None:
    """Start the worker task if it isn't already running. Safe to call
    repeatedly — including after a hot-reload of this module."""
    global _worker_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no loop yet — caller is in import time
    if _worker_task is not None and not _worker_task.done():
        return
    _worker_task = loop.create_task(_drain_queue(), name="win_broadcast_worker")


def enqueue(
    user_id: int,
    game_type: str,
    bet_usd: float,
    win_usd: float,
    multiplier: float = 0.0,
) -> bool:
    """Enqueue a win broadcast. Returns True if enqueued, False if dropped
    (queue full or channel not configured). Never raises."""
    global _dropped
    if not WIN_CHANNEL:
        return False
    if win_usd is None or float(win_usd) <= 0:
        return False
    try:
        q = _ensure_queue()
        text = _format_win_message(
            user_id=int(user_id),
            game_type=str(game_type or ""),
            bet_usd=float(bet_usd or 0),
            win_usd=float(win_usd),
            multiplier=float(multiplier or 0),
        )
        try:
            q.put_nowait({"text": text})
        except asyncio.QueueFull:
            _dropped += 1
            return False
        _ensure_worker()
        return True
    except Exception as e:  # pragma: no cover — defensive
        logging.debug("Win broadcast enqueue failed: %s", e)
        return False


def schedule_win_broadcast(
    user_id: int,
    game_type: str,
    bet_usd: float,
    win_usd: float,
    multiplier: float = 0.0,
) -> None:
    """Fire-and-forget entry point used from gameplay hot path."""
    enqueue(user_id, game_type, bet_usd, win_usd, multiplier)


def get_stats() -> dict:
    """Diagnostic snapshot — surfaced via /runtimestatus."""
    q = _queue
    return {
        "channel": WIN_CHANNEL or "(disabled)",
        "queued": q.qsize() if q is not None else 0,
        "dropped": _dropped,
        "worker_alive": bool(_worker_task and not _worker_task.done()),
        "helper_pool_size": len(helper_bots or ([helper_bot] if helper_bot else [])),
    }
