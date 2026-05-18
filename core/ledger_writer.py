"""Phase 2 hot-path wiring — sync→async bridge to the Postgres ledger.

The legacy wallet helpers (``credit_wallet``, ``credit_wallet_safe``,
``credit_wallet_crypto``, ``deduct_wallet``) are **synchronous** and
called from hundreds of places.  Rewriting every call-site as ``await``
would be a 40+ file change with high regression risk.

This module is the narrow bridge: every wallet mutation also funnels
through :func:`enqueue_mutation`, which schedules a non-blocking
``asyncio.create_task`` (when a loop is running) or buffers the entry
for the next async tick (when called from a thread-pool executor).

Design rules
------------
* The legacy in-memory ``user_wallets`` dict stays the read path for
  the bot UI — we update it synchronously before returning.
* The Postgres ledger write is **best-effort**: if it fails (network
  flake, PG down, ledger disabled), the bet is *not* rolled back; we
  log and rely on the periodic ``audit/wallet_audit.py`` cron to
  surface drift.
* Every entry carries a stable ``intent_id`` so retrying the bridge
  after a worker crash never double-credits.
* When ``MYCASINO_PG_LEDGER`` is unset this entire module is a no-op,
  which means the legacy bot path keeps running untouched.

Public API
----------
:func:`enqueue_mutation` — fire-and-forget; safe to call from sync
    code.
:func:`enqueue_bet_debit` / :func:`enqueue_bet_credit` — convenience
    wrappers used by the game plugins.
:func:`drain_pending` — used at shutdown to await every queued write
    (avoid losing entries on graceful stop).
:func:`pending_count` — gauge feeder for /metrics.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import weakref
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Mutation:
    user_id: int
    coin: str
    delta: float
    kind: str
    intent_id: str
    ref: Optional[str]
    metadata: Optional[Dict[str, Any]]


# In-process buffer — used when no event loop is running yet (very
# early at startup) or when we're called from a thread that doesn't
# share the bot's loop.  The worker / autoloader's startup task drains
# this buffer once the loop is up.
_pending_lock = threading.Lock()
_pending: list = []

# Counters surfaced to /metrics
_stats = {"enqueued": 0, "completed": 0, "failed": 0, "skipped": 0}

# We weakref the running tasks so the GC can clean them up.  Tracking
# them lets drain_pending() await everything before shutdown.
_inflight: "weakref.WeakSet[asyncio.Task]" = weakref.WeakSet()


def pending_count() -> int:
    """Number of mutations still buffered (not yet attempted)."""
    with _pending_lock:
        return len(_pending)


def stats() -> Dict[str, int]:
    """Snapshot of the bridge's counters (for /metrics / debugging)."""
    return dict(_stats)


def _make_intent(prefix: str, user_id: int, coin: str, ref: Optional[str]) -> str:
    # Fall back to a high-precision wall-clock when no ``ref`` is
    # provided.  Two simultaneous credits to the same user/coin from
    # the legacy path (e.g. raffle payout + tip received) are still
    # uniquely keyed.
    if ref:
        return f"{prefix}:{user_id}:{coin}:{ref}"
    return f"{prefix}:{user_id}:{coin}:{time.time_ns()}"


def enqueue_mutation(
    user_id: int,
    coin: str,
    delta: float,
    kind: str,
    *,
    intent_id: Optional[str] = None,
    ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort mirror of a wallet delta to the Postgres ledger.

    ``delta`` is in *crypto* units (matching the legacy
    ``user_wallets[user_id][coin]`` value).  This function NEVER
    raises — it logs and increments ``_stats['failed']`` instead.
    """
    # Lazy import — avoids a hard dep on db_pool when running unit
    # tests for unrelated modules.
    try:
        from core.db_pool import pg_ledger_enabled
    except Exception:  # noqa: BLE001
        _stats["skipped"] += 1
        return
    if not pg_ledger_enabled():
        _stats["skipped"] += 1
        return
    if delta == 0:
        _stats["skipped"] += 1
        return

    iid = intent_id or _make_intent(kind, user_id, coin, ref)
    mut = _Mutation(
        user_id=int(user_id),
        coin=str(coin),
        delta=float(delta),
        kind=str(kind),
        intent_id=iid,
        ref=ref,
        metadata=metadata,
    )
    _stats["enqueued"] += 1

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop in this thread — buffer for later drain.
        with _pending_lock:
            _pending.append(mut)
        return

    task = loop.create_task(_apply_one(mut))
    _inflight.add(task)


def enqueue_bet_debit(
    user_id: int,
    coin: str,
    crypto_amount: float,
    *,
    game_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Sugar for the bet-place path used by every game plugin."""
    if crypto_amount <= 0:
        return
    enqueue_mutation(
        user_id,
        coin,
        -float(crypto_amount),
        kind="bet_debit",
        intent_id=(f"bet:debit:{game_id}" if game_id else None),
        ref=game_id,
        metadata=metadata,
    )


def enqueue_bet_credit(
    user_id: int,
    coin: str,
    crypto_amount: float,
    *,
    game_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Sugar for the bet-settle path used by every game plugin."""
    if crypto_amount <= 0:
        return
    enqueue_mutation(
        user_id,
        coin,
        float(crypto_amount),
        kind="bet_credit",
        intent_id=(f"bet:credit:{game_id}" if game_id else None),
        ref=game_id,
        metadata=metadata,
    )


async def _apply_one(mut: _Mutation) -> None:
    """Write a single buffered mutation to the ledger.

    Best-effort; logs and increments ``_stats['failed']`` on error.
    """
    try:
        # Import here so module import is cheap even when PG is
        # disabled (no asyncpg required).
        from core.wallet_ledger import (
            LedgerUnavailable,
            adjust_balance,
        )
    except Exception:  # noqa: BLE001
        _stats["failed"] += 1
        return
    try:
        await adjust_balance(
            mut.user_id,
            mut.coin,
            mut.delta,
            kind=mut.kind,
            intent_id=mut.intent_id,
            ref=mut.ref,
            metadata=mut.metadata,
            # The legacy in-memory path enforces the non-negative
            # check, and adjust_balance also re-checks at the DB
            # layer.  ``allow_negative`` would only matter for
            # admin-side adjustments, which we route through their
            # own helpers.
            allow_negative=False,
        )
        _stats["completed"] += 1
    except LedgerUnavailable:
        # Postgres pool not initialised yet (e.g. very early in
        # startup) — re-buffer for the next drain.
        with _pending_lock:
            _pending.append(mut)
        _stats["failed"] += 1
    except Exception:  # noqa: BLE001
        # Most common cause: the wallet table doesn't have this
        # (user, coin) row yet — adjust_balance creates it
        # internally, so we usually only land here on real DB errors.
        logger.exception(
            "Ledger mirror failed for user=%s coin=%s kind=%s intent=%s; legacy "
            "in-memory wallet is still authoritative",
            mut.user_id,
            mut.coin,
            mut.kind,
            mut.intent_id,
        )
        _stats["failed"] += 1


async def drain_pending(timeout: float = 30.0) -> None:
    """Apply every buffered mutation and await in-flight tasks.

    Called from the bot's graceful-shutdown path so we don't lose
    a debit/credit we already updated in memory.
    """
    with _pending_lock:
        backlog = list(_pending)
        _pending.clear()
    if backlog:
        logger.info("Draining %d buffered ledger mutations", len(backlog))
        await asyncio.gather(
            *[_apply_one(m) for m in backlog],
            return_exceptions=True,
        )
    # Plus any in-flight tasks created via create_task earlier.
    in_flight = list(_inflight)
    if in_flight:
        logger.info("Awaiting %d in-flight ledger writes", len(in_flight))
        try:
            await asyncio.wait_for(
                asyncio.gather(*in_flight, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Ledger drain timed out after %.1fs", timeout)


def reset_for_tests() -> None:
    """Wipe internal state — used by unit tests."""
    with _pending_lock:
        _pending.clear()
    _inflight.clear()
    for k in list(_stats):
        _stats[k] = 0


__all__ = [
    "enqueue_mutation",
    "enqueue_bet_debit",
    "enqueue_bet_credit",
    "drain_pending",
    "pending_count",
    "stats",
    "reset_for_tests",
]
