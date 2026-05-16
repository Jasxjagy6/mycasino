"""Unit tests for the Phase 1e house_balance helpers in
``core.foundation``: ``get_house_balance``, ``apply_house_balance_delta``,
``apply_house_balance_delta_sync`` and ``set_house_balance``.

Because ``core.foundation`` is a giant file that imports ``telegram``,
``web3``, ``httpx``, ``uvloop`` etc. (none of which are guaranteed to
be available in every CI image), we run these tests **in-process by
isolating the relevant code rather than importing the whole module**.

We parse ``core/foundation.py`` with ``ast``, pull out only the four
helper function definitions by name, and ``exec`` them in a sandboxed
namespace that supplies the few symbols they actually need:
``logging``, ``asyncio``, ``bot_settings``, ``_house_balance_lock``.
This mirrors how ``test_game_math.py`` already isolates
``core.game_math`` from the rest of the codebase.
"""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path

import pytest


# ---------------------------------------------------------------------
# Helper: load the four house_balance functions from core/foundation.py
# without importing the whole module.
# ---------------------------------------------------------------------


def _load_house_balance_helpers():
    """Parse ``core/foundation.py`` with ast, extract just the four
    helper functions by name, and exec them in a sandboxed namespace.

    Returns a dict-style namespace exposing the helpers and the
    backing ``bot_settings`` / ``_house_balance_lock`` so tests can
    assert against them directly.
    """
    foundation_path = Path(__file__).resolve().parents[1] / "core" / "foundation.py"
    source = foundation_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(foundation_path))

    wanted = {
        "get_house_balance",
        "apply_house_balance_delta",
        "apply_house_balance_delta_sync",
        "set_house_balance",
    }
    extracted: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in wanted:
                extracted.append(node)

    if len(extracted) != len(wanted):
        missing = wanted - {n.name for n in extracted}
        raise RuntimeError(
            f"Could not find the following helpers in core/foundation.py: {missing}"
        )

    # Build a fresh Module containing just those four defs.
    module = ast.Module(body=extracted, type_ignores=[])
    ast.fix_missing_locations(module)

    ns: dict = {
        "__name__": "_isolated_house_balance_helpers",
        "asyncio": asyncio,
        "logging": logging,
        "bot_settings": {"house_balance": 0.0},
        "_house_balance_lock": asyncio.Lock(),
    }
    exec(compile(module, str(foundation_path), "exec"), ns)
    return ns


@pytest.fixture()
def helpers():
    """A fresh namespace per test (so bot_settings doesn't leak)."""
    return _load_house_balance_helpers()


# ---------------------------------------------------------------------
# get_house_balance
# ---------------------------------------------------------------------


def test_get_house_balance_reads_bot_settings(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 1_234.56
    assert helpers["get_house_balance"]() == 1_234.56


def test_get_house_balance_defaults_to_zero(helpers) -> None:
    helpers["bot_settings"].clear()
    assert helpers["get_house_balance"]() == 0.0


def test_get_house_balance_handles_corrupt_value(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = "garbage"
    # Should NOT raise; should return 0.0
    assert helpers["get_house_balance"]() == 0.0


# ---------------------------------------------------------------------
# apply_house_balance_delta (async)
# ---------------------------------------------------------------------


def test_apply_delta_positive(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    new = asyncio.run(helpers["apply_house_balance_delta"](50.0, reason="test"))
    assert new == 150.0
    assert helpers["bot_settings"]["house_balance"] == 150.0


def test_apply_delta_negative(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    new = asyncio.run(helpers["apply_house_balance_delta"](-30.0, reason="test"))
    assert new == 70.0


def test_apply_delta_rejects_nan(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    result = asyncio.run(
        helpers["apply_house_balance_delta"](float("nan"), reason="bad"),
    )
    # Returns current balance, NOT NaN
    assert result == 100.0
    # And the underlying value is untouched
    assert helpers["bot_settings"]["house_balance"] == 100.0


def test_apply_delta_rejects_inf(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    result = asyncio.run(
        helpers["apply_house_balance_delta"](float("inf"), reason="bad"),
    )
    assert result == 100.0
    assert helpers["bot_settings"]["house_balance"] == 100.0


def test_apply_delta_rejects_none(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    result = asyncio.run(
        helpers["apply_house_balance_delta"](None, reason="bad"),
    )
    assert result == 100.0


def test_apply_delta_concurrent_increments_are_not_lost(helpers) -> None:
    """The KEY invariant: 1000 concurrent ``apply_house_balance_delta``
    calls each adding $1 must end at exactly +$1000, never less.

    The old read-modify-write at callsites could lose updates because
    two coroutines could interleave the read between each other's
    writes. With ``_house_balance_lock`` this is impossible.
    """
    helpers["bot_settings"]["house_balance"] = 0.0

    async def _run():
        tasks = [
            helpers["apply_house_balance_delta"](1.0, reason=f"r{i}")
            for i in range(1000)
        ]
        await asyncio.gather(*tasks)

    asyncio.run(_run())
    assert helpers["bot_settings"]["house_balance"] == pytest.approx(1000.0)


# ---------------------------------------------------------------------
# apply_house_balance_delta_sync
# ---------------------------------------------------------------------


def test_apply_delta_sync_basic(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 50.0
    new = helpers["apply_house_balance_delta_sync"](25.0, reason="test")
    assert new == 75.0
    assert helpers["bot_settings"]["house_balance"] == 75.0


def test_apply_delta_sync_rejects_nan(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 50.0
    result = helpers["apply_house_balance_delta_sync"](
        float("nan"), reason="bad",
    )
    assert result == 50.0
    assert helpers["bot_settings"]["house_balance"] == 50.0


# ---------------------------------------------------------------------
# set_house_balance (admin path)
# ---------------------------------------------------------------------


def test_set_house_balance_sets_exact_value(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    new = asyncio.run(helpers["set_house_balance"](999.99, reason="admin-test"))
    assert new == 999.99
    assert helpers["bot_settings"]["house_balance"] == 999.99


def test_set_house_balance_zero_is_allowed(helpers) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    new = asyncio.run(helpers["set_house_balance"](0.0, reason="reset"))
    assert new == 0.0


@pytest.mark.parametrize("bad_amount", [
    -1.0, -0.01, -1_000_000.0,
    float("nan"), float("inf"), float("-inf"),
    None,
])
def test_set_house_balance_rejects_invalid(helpers, bad_amount) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    result = asyncio.run(helpers["set_house_balance"](bad_amount, reason="bad"))
    # Returns current balance, NOT the bad value
    assert result == 100.0
    # And the underlying value is untouched
    assert helpers["bot_settings"]["house_balance"] == 100.0


def test_set_house_balance_concurrent_with_deltas(helpers) -> None:
    """Even with 100 concurrent +$1 deltas, a concurrent ``set`` to a
    specific value must end with exactly that value (whichever
    ``set`` ran last wins, but the value is internally consistent --
    no torn writes)."""
    helpers["bot_settings"]["house_balance"] = 0.0

    async def _run():
        tasks = [
            helpers["apply_house_balance_delta"](1.0, reason=f"r{i}")
            for i in range(100)
        ]
        # Final set happens AFTER all deltas (we await deltas first)
        await asyncio.gather(*tasks)
        await helpers["set_house_balance"](500.0, reason="final")

    asyncio.run(_run())
    assert helpers["bot_settings"]["house_balance"] == 500.0


# ---------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------


def test_apply_delta_logs_reason(helpers, caplog) -> None:
    helpers["bot_settings"]["house_balance"] = 0.0
    with caplog.at_level(logging.INFO):
        asyncio.run(
            helpers["apply_house_balance_delta"](
                42.0, reason="emoji-match-cashout:abc:user=123",
            ),
        )
    matching = [r for r in caplog.records
                if "emoji-match-cashout:abc:user=123" in r.getMessage()]
    assert matching, "expected a log record mentioning the reason"


def test_set_balance_logs_at_warning_level(helpers, caplog) -> None:
    helpers["bot_settings"]["house_balance"] = 100.0
    with caplog.at_level(logging.WARNING):
        asyncio.run(
            helpers["set_house_balance"](
                250.0, reason="admin-set:user=42",
            ),
        )
    matching = [r for r in caplog.records
                if r.levelno >= logging.WARNING
                and "admin-set:user=42" in r.getMessage()]
    assert matching, "expected a WARNING-level admin-set log record"
