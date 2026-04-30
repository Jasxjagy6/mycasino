"""Anti-spam middleware for inline-button (CallbackQuery) traffic.

Two-layer guard, applied to *every* callback query before any handler
group runs:

1. **Per-user rate limit.** A sliding window of recent callback timestamps
   is kept per ``user_id``. When a user fires more than
   ``CALLBACK_BURST_LIMIT`` callbacks within ``CALLBACK_BURST_WINDOW``
   seconds, they are flagged as a spammer for ``CALLBACK_COOLDOWN``
   seconds. While flagged, every callback they send is silently
   ``answer()``-ed and ``ApplicationHandlerStop`` is raised so no further
   handler runs. /commands and /messages are completely unaffected — a
   legitimate user who opens their own menu after the cooldown expires
   never sees the restriction.

2. **Foreign-menu silencing.** When a callback's ``callback_data`` ends
   with the owner's user_id (a common pattern across this codebase, e.g.
   ``stats_view_24h_<owner_id>``), users that are not the owner get a
   silent answer + ApplicationHandlerStop. This is in addition to any
   per-handler "this menu is not for you" check the plugins themselves
   already do.

Everything is in-memory. There's no per-process synchronization needed
because PTB callbacks all run on the single event loop. The state
deliberately resets on a hot-reload of this module — no stale cooldowns
get carried into a new code revision. Bounded memory: only the last
``MAX_TRACKED_USERS`` user states are kept.
"""
from __future__ import annotations

import logging
import re
import time
from collections import deque
from typing import Deque, Dict, Optional

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        ApplicationHandlerStop,
        CallbackQueryHandler,
        ContextTypes,
    )
except Exception:  # pragma: no cover
    Update = object  # type: ignore[assignment]
    Application = object  # type: ignore[assignment]
    ApplicationHandlerStop = Exception  # type: ignore[assignment]
    CallbackQueryHandler = object  # type: ignore[assignment]
    ContextTypes = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


CALLBACK_BURST_WINDOW = 2.0   # seconds — sliding window
CALLBACK_BURST_LIMIT = 10     # max callbacks within the window
CALLBACK_COOLDOWN = 60.0      # seconds — silence period after burst
MAX_TRACKED_USERS = 50_000    # cap to keep memory bounded under floods


# ── State ──────────────────────────────────────────────────────────────

# user_id -> deque of recent callback timestamps (monotonic seconds).
_recent: Dict[int, Deque[float]] = {}

# user_id -> monotonic timestamp until which the user is silenced.
_silenced_until: Dict[int, float] = {}

# Diagnostic counters.
_silenced_cb_count = 0
_foreign_silenced_count = 0


_TRAILING_USER_ID_RE = re.compile(r"_(\d{5,15})$")


def _evict_if_needed() -> None:
    """Trim oldest entries when our tracking dicts get too big."""
    if len(_recent) > MAX_TRACKED_USERS:
        # Drop the oldest 10% by their last-seen timestamp.
        items = sorted(_recent.items(), key=lambda kv: kv[1][-1] if kv[1] else 0)
        drop = max(1, MAX_TRACKED_USERS // 10)
        for uid, _ in items[:drop]:
            _recent.pop(uid, None)
            _silenced_until.pop(uid, None)


def _detect_owner_from_callback(callback_data: Optional[str]) -> Optional[int]:
    """Many callback_data strings end with ``_<owner_user_id>``. Pick that
    out so we can tell if the presser is a foreign user.

    Returns ``None`` when no owner can be inferred. False positives are
    fine — they just mean the foreign-menu silencer doesn't fire for that
    callback, the per-user rate limit still applies."""
    if not callback_data:
        return None
    m = _TRAILING_USER_ID_RE.search(callback_data)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _record_and_check_burst(user_id: int, now: float) -> bool:
    """Append ``now`` to the user's rolling window and return True iff the
    user just exceeded ``CALLBACK_BURST_LIMIT`` within
    ``CALLBACK_BURST_WINDOW`` seconds."""
    dq = _recent.get(user_id)
    if dq is None:
        dq = deque(maxlen=CALLBACK_BURST_LIMIT + 4)
        _recent[user_id] = dq
        _evict_if_needed()
    cutoff = now - CALLBACK_BURST_WINDOW
    dq.append(now)
    while dq and dq[0] < cutoff:
        dq.popleft()
    return len(dq) > CALLBACK_BURST_LIMIT


async def _antispam_callback(update: "Update", context) -> None:
    """The middleware itself, registered at group=-100."""
    global _silenced_cb_count, _foreign_silenced_count
    query = getattr(update, "callback_query", None)
    if query is None or query.from_user is None:
        return
    user_id = query.from_user.id
    now = time.monotonic()

    # Already silenced?
    until = _silenced_until.get(user_id, 0.0)
    if until > now:
        try:
            await query.answer()
        except Exception:
            pass
        _silenced_cb_count += 1
        raise ApplicationHandlerStop

    # Burst detection.
    if _record_and_check_burst(user_id, now):
        _silenced_until[user_id] = now + CALLBACK_COOLDOWN
        logger.info(
            "antispam: user %s entered %.0fs cooldown after burst (>%d in %.1fs)",
            user_id, CALLBACK_COOLDOWN, CALLBACK_BURST_LIMIT, CALLBACK_BURST_WINDOW,
        )
        try:
            await query.answer()
        except Exception:
            pass
        _silenced_cb_count += 1
        raise ApplicationHandlerStop

    # Foreign-menu silencer: never crash if callback_data is something we
    # can't parse. Owners who press their own menu pass straight through.
    owner_id = _detect_owner_from_callback(query.data)
    if owner_id is not None and owner_id != user_id:
        try:
            await query.answer("This menu is not for you.", show_alert=False)
        except Exception:
            pass
        _foreign_silenced_count += 1
        raise ApplicationHandlerStop

    # Otherwise let the request flow through to the actual handlers.


def install_antispam(application: "Application") -> None:
    """Register the middleware as a CallbackQueryHandler at the lowest
    handler group (``-100``) so it runs before every plugin handler."""
    if getattr(application, "_antispam_installed", False):
        return
    handler = CallbackQueryHandler(_antispam_callback, pattern=None, block=False)
    application.add_handler(handler, group=-100)
    setattr(application, "_antispam_installed", True)
    logger.info(
        "antispam middleware installed (window=%.1fs limit=%d cooldown=%.0fs)",
        CALLBACK_BURST_WINDOW,
        CALLBACK_BURST_LIMIT,
        CALLBACK_COOLDOWN,
    )


def get_stats() -> dict:
    """Snapshot of internal counters — surfaced via /runtimestatus."""
    now = time.monotonic()
    active = sum(1 for t in _silenced_until.values() if t > now)
    return {
        "tracked_users": len(_recent),
        "active_cooldowns": active,
        "callbacks_silenced": _silenced_cb_count,
        "foreign_callbacks_silenced": _foreign_silenced_count,
        "burst_window_seconds": CALLBACK_BURST_WINDOW,
        "burst_limit": CALLBACK_BURST_LIMIT,
        "cooldown_seconds": CALLBACK_COOLDOWN,
    }


__all__ = ["install_antispam", "get_stats"]
