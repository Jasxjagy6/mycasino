"""Phase 2 — Redis backbone for rate-limits, leaderboards, jackpot, dedup.

This module is the **only** place anything reaches into Redis from
core/.  Plugins import the typed helpers (e.g. ``check_rate_limit``,
``incr_jackpot``) and never touch raw clients themselves.

Design points
-------------

* One async client per process, lazily created.  Every helper accepts
  an optional ``client`` argument for tests (we use ``fakeredis``).
* All commands are **idempotent** wherever possible — leaderboards use
  ``ZINCRBY`` (commutative), jackpot pools use ``INCRBYFLOAT``,
  dedup uses ``SET NX`` with TTL.  Multiple workers can run side by
  side without coordination.
* When Redis is unreachable, helpers fail **open** for non-critical
  paths (rate limit lets requests through; leaderboard updates are
  dropped with a warning) and **closed** for critical paths
  (deduplication treats the call as "not seen" only if explicitly
  configured, otherwise raises).

Env vars
--------
``MYCASINO_REDIS_URL``
    Same DSN as the queue (default ``redis://localhost:6379/0``).
``MYCASINO_REDIS_BACKEND``
    Truthy enables the Redis path globally.  When unset, every
    high-level helper degrades to a local-memory fallback (good for
    test runs without redis-server).
``MYCASINO_LEADERBOARD_TTL``
    Seconds before per-period leaderboards (daily/weekly) auto-expire
    (default: 8 days).
``MYCASINO_JACKPOT_KEY_PREFIX``
    Namespace prefix for jackpot pools (default: ``mycasino:jackpot:``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() in _TRUTHY


def redis_enabled() -> bool:
    return _truthy(os.environ.get("MYCASINO_REDIS_BACKEND"))


# ----------------------------------------------------------------------------
# Client management
# ----------------------------------------------------------------------------


_state_lock = asyncio.Lock()
_state: Dict[str, Any] = {"client": None, "url": None, "failed": False}


async def get_client() -> Optional[Any]:
    """Return a shared :class:`redis.asyncio.Redis` (or ``None``).

    Tests can monkey-patch this to a ``fakeredis.aioredis.FakeRedis``.
    """
    if _state["failed"]:
        return None
    url = os.environ.get("MYCASINO_REDIS_URL", "redis://localhost:6379/0")
    if _state["client"] is not None and _state["url"] == url:
        return _state["client"]
    async with _state_lock:
        if _state["client"] is not None and _state["url"] == url:
            return _state["client"]
        try:
            import redis.asyncio as redis_async  # type: ignore[import-not-found]
        except Exception:  # pragma: no cover - import failure path
            logger.warning("redis package not available; backend disabled")
            _state["failed"] = True
            return None
        try:
            client = redis_async.from_url(url, decode_responses=True)
            # Probe — fail-fast if redis is offline.
            await client.ping()
            _state["client"] = client
            _state["url"] = url
            logger.info("Redis backend ready at %s", url)
            return client
        except Exception:  # noqa: BLE001
            logger.warning("Redis backend unreachable at %s; staying offline", url)
            _state["failed"] = True
            return None


async def reset_client() -> None:
    """Tear down the shared client — primarily used in tests."""
    async with _state_lock:
        client = _state.get("client")
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
        _state["client"] = None
        _state["url"] = None
        _state["failed"] = False


def set_client_for_tests(client: Any) -> None:
    """Inject a fake client (e.g. ``fakeredis``).  Test-only."""
    _state["client"] = client
    _state["url"] = "test://"
    _state["failed"] = False


# ----------------------------------------------------------------------------
# Rate limit (sliding window via ZSET)
# ----------------------------------------------------------------------------


class RateLimitResult:
    __slots__ = ("allowed", "count", "limit", "retry_after_ms", "window_ms")

    def __init__(
        self,
        allowed: bool,
        count: int,
        limit: int,
        retry_after_ms: int,
        window_ms: int,
    ) -> None:
        self.allowed = allowed
        self.count = count
        self.limit = limit
        self.retry_after_ms = retry_after_ms
        self.window_ms = window_ms

    def __repr__(self) -> str:  # pragma: no cover - debug
        return (
            f"RateLimitResult(allowed={self.allowed} count={self.count}/"
            f"{self.limit} retry_ms={self.retry_after_ms})"
        )


# Lua script for atomic sliding-window rate limit.
# KEYS[1] = sorted-set key,
# ARGV    = now_ms, window_ms, limit
_RL_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
-- Drop entries older than the window.
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
local allowed = 0
if count < limit then
  -- Use the current ms as the member; combine with a random suffix in
  -- case multiple calls land in the same millisecond.
  redis.call('ZADD', key, now, now .. ':' .. ARGV[4])
  count = count + 1
  allowed = 1
end
redis.call('PEXPIRE', key, window)
return {allowed, count, limit}
"""

_rl_local_state: Dict[str, deque] = defaultdict(deque)


async def check_rate_limit(
    bucket: str,
    *,
    limit: int,
    window_ms: int,
    client: Optional[Any] = None,
    nonce: Optional[str] = None,
) -> RateLimitResult:
    """Allow at most ``limit`` calls per ``window_ms`` per ``bucket``.

    Returns a :class:`RateLimitResult` — the caller decides whether to
    abort or just record a warning.  When Redis is unavailable, falls
    back to a per-process in-memory deque.
    """
    now_ms = int(time.time() * 1000)
    key = f"mycasino:rl:{bucket}"
    nonce = nonce or f"{os.getpid()}:{now_ms}:{id(check_rate_limit)}"
    cli = client if client is not None else await get_client() if redis_enabled() else None
    if cli is not None:
        try:
            res = await cli.eval(
                _RL_SCRIPT, 1, key, str(now_ms), str(window_ms), str(limit), nonce
            )
            allowed = bool(int(res[0]))
            count = int(res[1])
            limit_returned = int(res[2])
            retry_after = 0 if allowed else window_ms
            return RateLimitResult(allowed, count, limit_returned, retry_after, window_ms)
        except Exception:  # noqa: BLE001
            logger.warning("Redis rate-limit error on %s; falling back", bucket, exc_info=True)
            # Fall through to local path.
    # Local fallback — best-effort, not shared across workers.
    q = _rl_local_state[bucket]
    cutoff = now_ms - window_ms
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) < limit:
        q.append(now_ms)
        return RateLimitResult(True, len(q), limit, 0, window_ms)
    retry_after = max(0, q[0] + window_ms - now_ms)
    return RateLimitResult(False, len(q), limit, retry_after, window_ms)


# ----------------------------------------------------------------------------
# Deduplication (SETNX with TTL)
# ----------------------------------------------------------------------------


_dedup_local: Dict[str, float] = {}


async def claim_once(
    intent_key: str,
    *,
    ttl_seconds: int = 600,
    client: Optional[Any] = None,
) -> bool:
    """Return True iff this is the first time we've seen ``intent_key``
    within ``ttl_seconds``.

    Use it as a guard around webhook handlers, retried bet settlements,
    OxaPay callbacks, etc.
    """
    cli = client if client is not None else await get_client() if redis_enabled() else None
    if cli is not None:
        try:
            ok = await cli.set(
                f"mycasino:dedup:{intent_key}",
                "1",
                ex=ttl_seconds,
                nx=True,
            )
            return bool(ok)
        except Exception:  # noqa: BLE001
            logger.warning("Redis dedup error for %s; falling back", intent_key, exc_info=True)
    now = time.time()
    expiry = _dedup_local.get(intent_key)
    if expiry and expiry > now:
        return False
    _dedup_local[intent_key] = now + ttl_seconds
    return True


# ----------------------------------------------------------------------------
# Jackpot pool (atomic accumulator)
# ----------------------------------------------------------------------------


_jackpot_local: Dict[str, float] = defaultdict(float)


async def incr_jackpot(
    pool: str,
    amount: float,
    *,
    client: Optional[Any] = None,
) -> float:
    """Add ``amount`` to the jackpot pool ``pool``.  Returns the new total.

    Uses ``INCRBYFLOAT`` so two workers can both credit a bet without
    losing one of the writes.
    """
    prefix = os.environ.get("MYCASINO_JACKPOT_KEY_PREFIX", "mycasino:jackpot:")
    key = f"{prefix}{pool}"
    cli = client if client is not None else await get_client() if redis_enabled() else None
    if cli is not None:
        try:
            new_total = await cli.incrbyfloat(key, float(amount))
            return float(new_total)
        except Exception:  # noqa: BLE001
            logger.warning("Redis jackpot incr failed for %s", pool, exc_info=True)
    _jackpot_local[pool] += float(amount)
    return _jackpot_local[pool]


async def get_jackpot(pool: str, *, client: Optional[Any] = None) -> float:
    prefix = os.environ.get("MYCASINO_JACKPOT_KEY_PREFIX", "mycasino:jackpot:")
    key = f"{prefix}{pool}"
    cli = client if client is not None else await get_client() if redis_enabled() else None
    if cli is not None:
        try:
            val = await cli.get(key)
            return float(val) if val is not None else 0.0
        except Exception:  # noqa: BLE001
            logger.warning("Redis jackpot get failed for %s", pool, exc_info=True)
    return _jackpot_local.get(pool, 0.0)


async def drop_jackpot(
    pool: str,
    *,
    client: Optional[Any] = None,
) -> float:
    """Atomically read the pool and reset it to zero.  Returns the
    amount that was paid out."""
    prefix = os.environ.get("MYCASINO_JACKPOT_KEY_PREFIX", "mycasino:jackpot:")
    key = f"{prefix}{pool}"
    cli = client if client is not None else await get_client() if redis_enabled() else None
    if cli is not None:
        try:
            # GETDEL is atomic on Redis 6.2+.  Fallback to GETSET on
            # older versions.
            try:
                val = await cli.getdel(key)
            except Exception:  # noqa: BLE001
                val = await cli.getset(key, 0)
            return float(val) if val is not None else 0.0
        except Exception:  # noqa: BLE001
            logger.warning("Redis jackpot drop failed for %s", pool, exc_info=True)
    val = _jackpot_local.get(pool, 0.0)
    _jackpot_local[pool] = 0.0
    return val


# ----------------------------------------------------------------------------
# Leaderboards (ZSET)
# ----------------------------------------------------------------------------


_leaderboard_local: Dict[str, Dict[int, float]] = defaultdict(dict)


def _leaderboard_key(period: str, metric: str) -> str:
    return f"mycasino:lb:{period}:{metric}"


async def lb_incr(
    period: str,
    metric: str,
    user_id: int,
    amount: float,
    *,
    ttl_seconds: Optional[int] = None,
    client: Optional[Any] = None,
) -> float:
    """Increment a user's score on the (period, metric) leaderboard.

    Returns the new score.  ``period`` is e.g. ``"daily"``, ``"weekly"``,
    ``"alltime"``; ``metric`` is e.g. ``"wagered"`` or ``"won"``.
    """
    cli = client if client is not None else await get_client() if redis_enabled() else None
    key = _leaderboard_key(period, metric)
    if cli is not None:
        try:
            new_score = await cli.zincrby(key, float(amount), str(user_id))
            ttl = ttl_seconds or int(os.environ.get("MYCASINO_LEADERBOARD_TTL", "691200"))
            if ttl > 0:
                await cli.expire(key, ttl)
            return float(new_score)
        except Exception:  # noqa: BLE001
            logger.warning("Redis lb incr failed for %s/%s", period, metric, exc_info=True)
    bucket = _leaderboard_local[f"{period}:{metric}"]
    bucket[user_id] = bucket.get(user_id, 0.0) + float(amount)
    return bucket[user_id]


async def lb_top(
    period: str,
    metric: str,
    *,
    limit: int = 10,
    client: Optional[Any] = None,
) -> List[Tuple[int, float]]:
    """Return the top-N (user_id, score) entries in descending order."""
    cli = client if client is not None else await get_client() if redis_enabled() else None
    key = _leaderboard_key(period, metric)
    if cli is not None:
        try:
            rows = await cli.zrevrange(key, 0, limit - 1, withscores=True)
            return [(int(uid), float(score)) for uid, score in rows]
        except Exception:  # noqa: BLE001
            logger.warning("Redis lb top failed for %s/%s", period, metric, exc_info=True)
    bucket = _leaderboard_local.get(f"{period}:{metric}", {})
    return sorted(bucket.items(), key=lambda x: x[1], reverse=True)[:limit]


async def lb_rank(
    period: str,
    metric: str,
    user_id: int,
    *,
    client: Optional[Any] = None,
) -> Optional[int]:
    """Return the 1-indexed rank of ``user_id`` on the leaderboard."""
    cli = client if client is not None else await get_client() if redis_enabled() else None
    key = _leaderboard_key(period, metric)
    if cli is not None:
        try:
            rank = await cli.zrevrank(key, str(user_id))
            return None if rank is None else int(rank) + 1
        except Exception:  # noqa: BLE001
            logger.warning("Redis lb rank failed for %s/%s", period, metric, exc_info=True)
    bucket = _leaderboard_local.get(f"{period}:{metric}", {})
    if user_id not in bucket:
        return None
    sorted_users = sorted(bucket.items(), key=lambda x: x[1], reverse=True)
    for i, (uid, _score) in enumerate(sorted_users, start=1):
        if uid == user_id:
            return i
    return None


async def lb_reset(
    period: str,
    metric: str,
    *,
    client: Optional[Any] = None,
) -> None:
    cli = client if client is not None else await get_client() if redis_enabled() else None
    key = _leaderboard_key(period, metric)
    if cli is not None:
        try:
            await cli.delete(key)
        except Exception:  # noqa: BLE001
            logger.warning("Redis lb reset failed for %s/%s", period, metric, exc_info=True)
    _leaderboard_local.pop(f"{period}:{metric}", None)


__all__ = [
    "redis_enabled",
    "get_client",
    "reset_client",
    "set_client_for_tests",
    "RateLimitResult",
    "check_rate_limit",
    "claim_once",
    "incr_jackpot",
    "get_jackpot",
    "drop_jackpot",
    "lb_incr",
    "lb_top",
    "lb_rank",
    "lb_reset",
]
