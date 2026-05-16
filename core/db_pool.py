"""asyncpg pool manager — Phase 2 PostgreSQL backbone.

A single shared pool per process.  ``get_pool()`` returns ``None`` when
PostgreSQL is unavailable or disabled, which lets every call-site fall
back to the legacy JSON/SQLite path without branching at every line.

The pool is configured via env vars only — never imported at module
load time so a missing ``asyncpg`` install won't crash the rest of the
bot.

Env vars
--------
``POSTGRES_URL``
    DSN such as ``postgresql://user:pass@host:5432/casino``.
``MYCASINO_PG_LEDGER``
    Truthy value ("1", "true", "yes") enables the wallet+ledger
    backend.  When unset, all calls into :mod:`core.wallet_ledger`
    no-op so the legacy in-memory path keeps running.
``MYCASINO_PG_MIN_POOL`` / ``MYCASINO_PG_MAX_POOL``
    Min/max pool sizes (defaults: 2 / 20).
``MYCASINO_PG_STATEMENT_TIMEOUT``
    Per-statement timeout in milliseconds (default: 5000).
``MYCASINO_PG_MIGRATIONS_DIR``
    Directory containing ``00xx_*.sql`` migration files (default:
    ``deploy/migrations`` relative to repo root).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional

try:
    import asyncpg  # type: ignore[import-not-found]
    _ASYNCPG_AVAILABLE = True
except Exception:  # pragma: no cover - import failure path
    asyncpg = None  # type: ignore[assignment]
    _ASYNCPG_AVAILABLE = False

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() in _TRUTHY


def pg_ledger_enabled() -> bool:
    """Returns True iff the PG wallet+ledger path is enabled."""
    return _ASYNCPG_AVAILABLE and bool(os.environ.get("POSTGRES_URL")) and _truthy(
        os.environ.get("MYCASINO_PG_LEDGER")
    )


class _PoolState:
    """Lazy singleton holder for the asyncpg pool."""

    def __init__(self) -> None:
        self.pool: Optional[Any] = None
        self.lock = asyncio.Lock()
        self.url: Optional[str] = None
        self.failed_once = False


_state = _PoolState()


async def get_pool() -> Optional[Any]:
    """Return the shared asyncpg.Pool, creating it on first use.

    Returns ``None`` when:
      * ``asyncpg`` isn't installed
      * ``POSTGRES_URL`` is empty
      * a previous initialisation attempt failed (we don't keep
        retrying — call :func:`reset_pool` to force another attempt)
    """
    if not _ASYNCPG_AVAILABLE:
        return None
    if _state.failed_once:
        return None
    url = os.environ.get("POSTGRES_URL")
    if not url:
        return None
    if _state.pool is not None and _state.url == url:
        return _state.pool
    async with _state.lock:
        if _state.pool is not None and _state.url == url:
            return _state.pool
        try:
            min_size = int(os.environ.get("MYCASINO_PG_MIN_POOL", "2"))
            max_size = int(os.environ.get("MYCASINO_PG_MAX_POOL", "20"))
            timeout_ms = int(
                os.environ.get("MYCASINO_PG_STATEMENT_TIMEOUT", "5000")
            )
            _state.pool = await asyncpg.create_pool(
                dsn=url,
                min_size=min_size,
                max_size=max_size,
                command_timeout=timeout_ms / 1000.0,
                # Setting a session-level statement_timeout protects us
                # from a runaway query holding a wallet row lock.
                server_settings={
                    "statement_timeout": str(timeout_ms),
                    "application_name": "mycasino",
                },
            )
            _state.url = url
            logger.info(
                "PostgreSQL pool ready (min=%s max=%s timeout_ms=%s)",
                min_size,
                max_size,
                timeout_ms,
            )
            return _state.pool
        except Exception:  # noqa: BLE001
            logger.exception("Failed to initialise asyncpg pool")
            _state.failed_once = True
            return None


async def reset_pool() -> None:
    """Tear down the current pool — primarily used in tests."""
    async with _state.lock:
        if _state.pool is not None:
            try:
                await _state.pool.close()
            except Exception:  # noqa: BLE001
                logger.exception("pool close raised; continuing")
        _state.pool = None
        _state.url = None
        _state.failed_once = False


async def acquire() -> AsyncIterator[Any]:  # pragma: no cover - thin
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("PostgreSQL pool is not available")
    async with pool.acquire() as conn:
        yield conn


def migrations_dir() -> Path:
    explicit = os.environ.get("MYCASINO_PG_MIGRATIONS_DIR")
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve().parent.parent
    return here / "deploy" / "migrations"


async def run_migrations(directory: Optional[Path] = None) -> int:
    """Apply every ``00xx_*.sql`` file under ``directory`` in order.

    Returns the number of files applied (skipping ones already in
    ``schema_migrations``).  No-op if the pool isn't available.
    """
    pool = await get_pool()
    if pool is None:
        logger.warning("Skipping migrations: no Postgres pool")
        return 0
    dir_ = directory or migrations_dir()
    if not dir_.exists():
        logger.warning("Skipping migrations: %s does not exist", dir_)
        return 0
    files = sorted(dir_.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        return 0
    async with pool.acquire() as conn:
        # The initial migration creates the table, so handle the bootstrap
        # case where the table doesn't exist yet.
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        )
        already = {
            r["version"]
            for r in await conn.fetch("SELECT version FROM schema_migrations")
        }
        applied = 0
        for path in files:
            version = path.stem
            if version in already:
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) "
                        "VALUES ($1) ON CONFLICT DO NOTHING",
                        version,
                    )
            except Exception:  # noqa: BLE001
                logger.exception("Migration %s failed; aborting", version)
                raise
            logger.info("Applied migration %s", version)
            applied += 1
    return applied


__all__ = [
    "get_pool",
    "reset_pool",
    "run_migrations",
    "pg_ledger_enabled",
    "migrations_dir",
]
