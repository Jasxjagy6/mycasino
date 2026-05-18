"""Tests for ``core.wallet_ledger``.

Live tests require Postgres — they're skipped when ``POSTGRES_URL``
isn't set.  Static tests (import-safety, error-class shapes) always
run.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from core import db_pool, wallet_ledger


def test_module_imports():
    assert hasattr(wallet_ledger, "place_bet")
    assert hasattr(wallet_ledger, "settle_bet")
    assert hasattr(wallet_ledger, "adjust_balance")
    assert hasattr(wallet_ledger, "reserve_withdrawal")


def test_error_classes_are_distinct():
    assert wallet_ledger.LedgerUnavailable is not wallet_ledger.InsufficientFunds


def test_ledger_entry_is_frozen():
    e = wallet_ledger.LedgerEntry(
        ledger_id=1,
        user_id=2,
        coin="USDT",
        delta=Decimal("1"),
        balance_after=Decimal("1"),
        kind="test",
        intent_id="x",
        ref=None,
        metadata={},
    )
    with pytest.raises(Exception):
        e.delta = Decimal("2")  # type: ignore[misc]


@pytest.mark.skipif(
    not os.environ.get("POSTGRES_URL") or not os.environ.get("MYCASINO_PG_LEDGER"),
    reason="POSTGRES_URL + MYCASINO_PG_LEDGER required for live ledger tests",
)
async def test_place_and_settle_bet_round_trip():
    pool = await db_pool.get_pool()
    if pool is None:
        pytest.skip("Postgres unreachable")
    await db_pool.run_migrations()
    user_id = -111  # negative ⇒ unlikely to clash with real users
    coin = "USDT"
    # Seed the wallet with 10.
    await wallet_ledger.adjust_balance(
        user_id, coin, Decimal("10"), kind="seed",
        intent_id=f"seed:{user_id}:{coin}",
    )
    bet = await wallet_ledger.place_bet(
        user_id, coin, Decimal("3"),
        game_id="test-bet-1",
    )
    assert bet.balance_after == Decimal("7")
    settled = await wallet_ledger.settle_bet(
        user_id, coin, Decimal("5"),
        game_id="test-bet-1",
    )
    assert settled.balance_after == Decimal("12")
    # Re-settling the same game_id must be a no-op (or return the existing entry).
    settled_again = await wallet_ledger.settle_bet(
        user_id, coin, Decimal("5"),
        game_id="test-bet-1",
    )
    assert settled_again.balance_after == Decimal("12")
