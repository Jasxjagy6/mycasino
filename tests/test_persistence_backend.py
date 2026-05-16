"""Tests for the JSON path of ``core.persistence_backend``.

The PG path needs a real database so we skip it; CI exercises it
through the dedicated ``test_wallet_ledger.py`` when DSN is set.
"""

from __future__ import annotations


import pytest

from core import persistence_backend as pb


@pytest.fixture
def temp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCASINO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MYCASINO_PERSIST_BACKEND_FORCE_JSON", "1")
    return tmp_path


async def test_backend_name_defaults_to_json(monkeypatch):
    monkeypatch.delenv("MYCASINO_PERSIST_BACKEND", raising=False)
    monkeypatch.delenv("MYCASINO_PERSIST_BACKEND_FORCE_JSON", raising=False)
    assert pb.backend_name() == "json"


async def test_backend_name_postgres_can_be_enabled(monkeypatch):
    monkeypatch.delenv("MYCASINO_PERSIST_BACKEND_FORCE_JSON", raising=False)
    monkeypatch.setenv("MYCASINO_PERSIST_BACKEND", "postgres")
    assert pb.backend_name() == "postgres"


async def test_force_json_overrides(monkeypatch):
    monkeypatch.setenv("MYCASINO_PERSIST_BACKEND_FORCE_JSON", "1")
    monkeypatch.setenv("MYCASINO_PERSIST_BACKEND", "postgres")
    assert pb.backend_name() == "json"


async def test_save_then_load_roundtrip(temp_data_dir):
    state = {"name": "Alice", "balance": 12.5, "tags": ["vip"]}
    await pb.save(42, state)
    loaded = await pb.load(42)
    assert loaded == state


async def test_load_missing_returns_none(temp_data_dir):
    assert await pb.load(99999999) is None


async def test_load_all_returns_every_user(temp_data_dir):
    await pb.save(1, {"x": 1})
    await pb.save(2, {"x": 2})
    await pb.save(3, {"x": 3})
    all_users = await pb.load_all()
    assert all_users == {1: {"x": 1}, 2: {"x": 2}, 3: {"x": 3}}


async def test_flush_dirty_writes_only_listed_users(temp_data_dir):
    state_table = {1: {"v": "a"}, 2: {"v": "b"}, 3: {"v": "c"}}
    saved = await pb.flush_dirty([1, 3], state_table.get)
    assert saved == 2
    assert await pb.load(1) == {"v": "a"}
    assert await pb.load(2) is None
    assert await pb.load(3) == {"v": "c"}
