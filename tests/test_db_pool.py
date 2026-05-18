"""Tests for ``core.db_pool``.

We can't spin up a real Postgres on a CI box without infrastructure,
so we exercise the import-safety + env-driven behaviour and skip the
live-pool tests when ``POSTGRES_URL`` isn't set.
"""

from __future__ import annotations

import os

import pytest

from core import db_pool


def test_pg_ledger_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MYCASINO_PG_LEDGER", raising=False)
    assert db_pool.pg_ledger_enabled() is False


def test_pg_ledger_enabled_when_set(monkeypatch):
    # ``pg_ledger_enabled`` requires both POSTGRES_URL AND the toggle
    # AND a working ``asyncpg`` install.  If asyncpg isn't on this CI
    # box the function correctly stays False — skip in that case.
    if not db_pool._ASYNCPG_AVAILABLE:
        import pytest as _pt

        _pt.skip("asyncpg not installed")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://stub/db")
    monkeypatch.setenv("MYCASINO_PG_LEDGER", "1")
    assert db_pool.pg_ledger_enabled() is True
    monkeypatch.setenv("MYCASINO_PG_LEDGER", "yes")
    assert db_pool.pg_ledger_enabled() is True
    monkeypatch.setenv("MYCASINO_PG_LEDGER", "off")
    assert db_pool.pg_ledger_enabled() is False


def test_migrations_dir_default(monkeypatch):
    monkeypatch.delenv("MYCASINO_PG_MIGRATIONS_DIR", raising=False)
    d = db_pool.migrations_dir()
    assert d.name == "migrations"


def test_migrations_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MYCASINO_PG_MIGRATIONS_DIR", str(tmp_path))
    assert db_pool.migrations_dir() == tmp_path


async def test_get_pool_returns_none_without_dsn(monkeypatch):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    await db_pool.reset_pool()
    pool = await db_pool.get_pool()
    assert pool is None


@pytest.mark.skipif(
    not os.environ.get("POSTGRES_URL"),
    reason="POSTGRES_URL not set — skipping live PG test",
)
async def test_run_migrations_applies(tmp_path):
    pool = await db_pool.get_pool()
    if pool is None:
        pytest.skip("Postgres unreachable")
    # Re-runnable migrations: applying twice must not raise.
    await db_pool.run_migrations()
    await db_pool.run_migrations()
