"""Tests for the Phase 2 hot-path sync→async bridge (core.ledger_writer).

The bridge is what makes the legacy synchronous wallet helpers
(``credit_wallet``, ``credit_wallet_safe``, ``deduct_wallet``) actually
mirror their writes to the PostgreSQL ledger without requiring a 40+
file plugin rewrite.  We exercise three modes:

* **Disabled** — PG flag unset → every call is a no-op (the legacy
  in-memory path stays the only writer).
* **Enabled, loop running** — calls funnel through
  ``asyncio.create_task`` and the patched ``adjust_balance`` is
  invoked exactly once with the right delta + intent_id.
* **Enabled, no loop** — calls land in the in-process buffer; the
  next ``drain_pending`` picks them up and applies them.
"""

from __future__ import annotations

import asyncio

import pytest

from core import ledger_writer


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Each test starts with a clean module + PG flag explicitly off.

    Tests that want the "enabled" path call :func:`_enable_pg` below
    to flip the ``db_pool.pg_ledger_enabled`` predicate.  We patch the
    function directly so we don't need real asyncpg or a reachable
    Postgres instance to exercise the bridge.
    """
    monkeypatch.delenv("MYCASINO_PG_LEDGER", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    from core import db_pool
    monkeypatch.setattr(db_pool, "pg_ledger_enabled", lambda: False)
    ledger_writer.reset_for_tests()
    yield
    ledger_writer.reset_for_tests()


def _enable_pg(monkeypatch):
    """Force ``pg_ledger_enabled() -> True`` for the rest of the test."""
    from core import db_pool
    monkeypatch.setattr(db_pool, "pg_ledger_enabled", lambda: True)


def test_enqueue_is_noop_when_disabled():
    ledger_writer.enqueue_mutation(123, "USDT", -1.5, kind="bet_debit")
    s = ledger_writer.stats()
    assert s["enqueued"] == 0
    assert s["completed"] == 0
    assert s["failed"] == 0
    assert s["skipped"] == 1
    assert ledger_writer.pending_count() == 0


def test_zero_delta_is_skipped(monkeypatch):
    _enable_pg(monkeypatch)
    ledger_writer.enqueue_mutation(123, "USDT", 0, kind="bet_credit")
    assert ledger_writer.stats()["skipped"] == 1


def test_enqueue_buffers_when_no_loop(monkeypatch):
    _enable_pg(monkeypatch)
    # We're calling from a *sync* test — there is no running loop, so
    # the bridge falls back to the in-process buffer.
    ledger_writer.enqueue_mutation(7, "USDT", -2.0, kind="bet_debit", intent_id="i-1")
    assert ledger_writer.pending_count() == 1
    assert ledger_writer.stats()["enqueued"] == 1


def test_enqueue_creates_task_when_loop_running(monkeypatch):
    _enable_pg(monkeypatch)
    calls: list = []

    async def fake_adjust_balance(user_id, coin, delta, **kw):
        calls.append((user_id, coin, float(delta), kw))

        # Need to return something LedgerEntry-shaped; we don't inspect it.
        return None

    async def run():
        # Patch wallet_ledger.adjust_balance only after the loop starts.
        from core import wallet_ledger
        wallet_ledger.adjust_balance = fake_adjust_balance  # type: ignore[assignment]
        ledger_writer.enqueue_mutation(
            42,
            "USDT",
            -1.25,
            kind="bet_debit",
            intent_id="i-loop",
            ref="g1",
            metadata={"usd": 1.0},
        )
        # Wait for the fire-and-forget task to finish.
        await ledger_writer.drain_pending(timeout=2.0)

    asyncio.run(run())
    assert calls, "ledger writer didn't reach adjust_balance"
    user_id, coin, delta, kw = calls[0]
    assert user_id == 42
    assert coin == "USDT"
    assert delta == pytest.approx(-1.25)
    assert kw["intent_id"] == "i-loop"
    assert kw["ref"] == "g1"
    assert kw["kind"] == "bet_debit"


def test_drain_applies_buffered_entries(monkeypatch):
    _enable_pg(monkeypatch)
    seen: list = []

    async def fake_adjust_balance(user_id, coin, delta, **kw):
        seen.append((user_id, coin, float(delta)))
        return None

    async def run():
        from core import wallet_ledger
        wallet_ledger.adjust_balance = fake_adjust_balance  # type: ignore[assignment]
        # First, fill the buffer from sync land (no loop).
        # Use a thread so there's no running loop at call time.
        import threading

        def _push():
            ledger_writer.enqueue_mutation(1, "USDT", -1.0, kind="bet_debit")
            ledger_writer.enqueue_mutation(1, "USDT", 2.0, kind="bet_credit")

        t = threading.Thread(target=_push)
        t.start()
        t.join()
        assert ledger_writer.pending_count() == 2
        await ledger_writer.drain_pending(timeout=2.0)

    asyncio.run(run())
    assert len(seen) == 2
    deltas = sorted(d for _, _, d in seen)
    assert deltas == [-1.0, 2.0]


def test_bridge_swallows_adjust_errors(monkeypatch):
    """A flaky PG must never propagate up into the bet hot path."""
    _enable_pg(monkeypatch)

    async def fake_adjust_balance(*a, **kw):
        raise RuntimeError("db boom")

    async def run():
        from core import wallet_ledger
        wallet_ledger.adjust_balance = fake_adjust_balance  # type: ignore[assignment]
        ledger_writer.enqueue_mutation(99, "USDT", -3.0, kind="bet_debit")
        await ledger_writer.drain_pending(timeout=2.0)

    asyncio.run(run())
    s = ledger_writer.stats()
    assert s["failed"] >= 1, f"expected failure counter to advance: {s}"
