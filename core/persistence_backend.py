"""Phase 3 — Persistence backend abstraction (JSON or Postgres).

The legacy bot persists every user as ``data/users/{user_id}.json``
and flushes a "dirty set" every few seconds.  That model is fine for a
single VM but it:

* Loses the last few seconds of state on crash.
* Forces every worker to hold the full user table in memory.
* Doesn't compose with the new PG ledger — wallets live in Postgres
  but stats still live in JSON.

This module gives every caller a single ``save(user_id)`` /
``load(user_id)`` interface that routes to the right backend.  When
``MYCASINO_PERSIST_BACKEND=postgres`` (and the pool is healthy) we
write to a ``user_state`` JSONB column; otherwise we fall through to
the legacy disk path so existing deployments keep working.

The Postgres backend uses an UPSERT, so two workers writing the same
user concurrently is safe (last-writer-wins on each field — for
stats-style "increment counters" workloads, callers should pre-compute
the merge in core/wallet.py before saving).

Public API
----------
``async load(user_id) -> Optional[dict]``
``async save(user_id, state) -> None``
``async load_all() -> Dict[int, dict]`` (used at startup)
``flush_dirty(dirty_user_ids, fetch_fn) -> int``  drop-in for the old
flusher loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from core.db_pool import get_pool

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() in _TRUTHY


def backend_name() -> str:
    """``"postgres"`` when configured & healthy, else ``"json"``."""
    if _truthy(os.environ.get("MYCASINO_PERSIST_BACKEND_FORCE_JSON")):
        return "json"
    if os.environ.get("MYCASINO_PERSIST_BACKEND", "").lower() == "postgres":
        return "postgres"
    return "json"


def data_dir() -> Path:
    explicit = os.environ.get("MYCASINO_DATA_DIR")
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve().parent.parent
    return here / "data" / "users"


# ---------------------------------------------------------------------------
# Postgres schema bootstrap — runs on first save.
# ---------------------------------------------------------------------------


_USER_STATE_DDL = """
CREATE TABLE IF NOT EXISTS user_state (
    user_id    BIGINT       PRIMARY KEY,
    state      JSONB        NOT NULL,
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_state_updated ON user_state (updated_at);
"""

_schema_ready_lock = asyncio.Lock()
_schema_ready = {"value": False}


async def _ensure_schema(conn) -> None:
    if _schema_ready["value"]:
        return
    async with _schema_ready_lock:
        if _schema_ready["value"]:
            return
        await conn.execute(_USER_STATE_DDL)
        _schema_ready["value"] = True


# ---------------------------------------------------------------------------
# JSON backend
# ---------------------------------------------------------------------------


def _json_path(user_id: int) -> Path:
    return data_dir() / f"{user_id}.json"


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read %s", path)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def save(user_id: int, state: dict) -> None:
    """Persist ``state`` for ``user_id``.

    Tries Postgres when the backend is configured; falls through to
    JSON on any error so a missing pool never costs us data.
    """
    backend = backend_name()
    if backend == "postgres":
        pool = await get_pool()
        if pool is not None:
            try:
                async with pool.acquire() as conn:
                    await _ensure_schema(conn)
                    await conn.execute(
                        "INSERT INTO user_state (user_id, state, updated_at) "
                        "VALUES ($1, $2::jsonb, NOW()) "
                        "ON CONFLICT (user_id) DO UPDATE "
                        "SET state = EXCLUDED.state, updated_at = NOW()",
                        user_id,
                        json.dumps(state, default=str),
                    )
                return
            except Exception:  # noqa: BLE001
                logger.exception(
                    "PG save failed for user %s — falling back to JSON",
                    user_id,
                )
    # JSON fallback.
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _atomic_write_json, _json_path(user_id), state)


async def load(user_id: int) -> Optional[dict]:
    backend = backend_name()
    if backend == "postgres":
        pool = await get_pool()
        if pool is not None:
            try:
                async with pool.acquire() as conn:
                    await _ensure_schema(conn)
                    row = await conn.fetchrow(
                        "SELECT state FROM user_state WHERE user_id=$1",
                        user_id,
                    )
                    if row is not None:
                        state = row["state"]
                        if isinstance(state, str):
                            state = json.loads(state)
                        return state
            except Exception:  # noqa: BLE001
                logger.exception(
                    "PG load failed for user %s — falling back to JSON",
                    user_id,
                )
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _read_json, _json_path(user_id))


async def load_all() -> Dict[int, dict]:
    """Return every persisted user record.  Used once at startup."""
    backend = backend_name()
    if backend == "postgres":
        pool = await get_pool()
        if pool is not None:
            try:
                async with pool.acquire() as conn:
                    await _ensure_schema(conn)
                    rows = await conn.fetch("SELECT user_id, state FROM user_state")
                    out: Dict[int, dict] = {}
                    for r in rows:
                        state = r["state"]
                        if isinstance(state, str):
                            state = json.loads(state)
                        out[int(r["user_id"])] = state
                    return out
            except Exception:  # noqa: BLE001
                logger.exception("PG load_all failed — falling back to JSON")
    # JSON fallback.
    out: Dict[int, dict] = {}
    d = data_dir()
    if not d.exists():
        return out
    for path in d.glob("*.json"):
        try:
            uid = int(path.stem)
        except ValueError:
            continue
        data = _read_json(path)
        if data is not None:
            out[uid] = data
    return out


async def flush_dirty(
    user_ids: Iterable[int],
    fetch_state: Callable[[int], dict],
    *,
    concurrency: int = 16,
) -> int:
    """Drop-in replacement for the legacy ``_flush_dirty_users`` loop.

    ``fetch_state(user_id)`` returns the in-memory dict for the user
    (it's called synchronously, so callers should pass a tiny lookup
    closure).  Writes happen in parallel up to ``concurrency``.

    Returns the number of users actually persisted.
    """
    ids = list(user_ids)
    if not ids:
        return 0
    sem = asyncio.Semaphore(concurrency)
    saved = 0

    async def _one(uid: int) -> None:
        nonlocal saved
        async with sem:
            try:
                state = fetch_state(uid)
            except Exception:  # noqa: BLE001
                logger.exception("fetch_state(%s) raised", uid)
                return
            if state is None:
                return
            try:
                await save(uid, state)
                saved += 1
            except Exception:  # noqa: BLE001
                logger.exception("flush_dirty save failed for %s", uid)

    await asyncio.gather(*(_one(uid) for uid in ids))
    return saved


__all__ = [
    "backend_name",
    "save",
    "load",
    "load_all",
    "flush_dirty",
    "data_dir",
]
