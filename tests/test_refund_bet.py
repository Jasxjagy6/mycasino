"""Unit tests for the Phase 1f ``refund_bet`` helper in
``core.wallet``.

Audit reference: M3 in ``upgrade_and_fixes.txt`` -- admin
``/cancel <game_id>`` previously refunded USD at the *current*
``LIVE_PRICES`` instead of the crypto amount that was originally
deducted. With ``refund_bet`` the refund now uses the stored crypto
quantity (or stored locked-price quote) and is immune to subsequent
price drift.

These tests are AST-isolated -- they parse ``core/wallet.py`` and
extract just the ``refund_bet`` function (and its inner closure), then
run it against a fake ``LIVE_PRICES`` / ``ensure_wallet_dict`` /
``credit_wallet_safe`` / ``get_active_currency`` namespace. This
mirrors ``tests/test_house_balance.py``.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest


# ---------------------------------------------------------------------
# Helper: load refund_bet from core/wallet.py
# ---------------------------------------------------------------------


def _load_refund_bet():
    wallet_path = Path(__file__).resolve().parents[1] / "core" / "wallet.py"
    source = wallet_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(wallet_path))

    extracted: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "refund_bet":
            extracted.append(node)
    if not extracted:
        raise RuntimeError("refund_bet not found in core/wallet.py")

    module = ast.Module(body=extracted, type_ignores=[])
    ast.fix_missing_locations(module)

    # Backing state shared across the test
    wallets: dict[int, dict[str, float]] = {}
    credit_log: list[tuple] = []

    def ensure_wallet_dict(user_id):
        return wallets.setdefault(user_id, {})

    def get_active_currency(user_id):
        return "USDT"

    def credit_wallet_safe(user_id, usd_amount, coin=None, *, locked_price=None):
        # Mimic the live behaviour: USD -> crypto at LIVE_PRICES
        coin = coin or "USDT"
        price = LIVE_PRICES.get(coin, 1.0)
        crypto = usd_amount / price
        ensure_wallet_dict(user_id)[coin] = (
            ensure_wallet_dict(user_id).get(coin, 0.0) + crypto
        )
        credit_log.append((user_id, usd_amount, coin, crypto))
        return crypto, coin

    # The LIVE_PRICES used by the fallback path. Tests can mutate
    # this between the bet and the refund to simulate price drift.
    LIVE_PRICES: dict[str, float] = {"USDT": 1.0, "BTC": 60_000.0}

    ns: dict = {
        "__name__": "_isolated_refund_bet",
        "logging": logging,
        "ensure_wallet_dict": ensure_wallet_dict,
        "get_active_currency": get_active_currency,
        "credit_wallet_safe": credit_wallet_safe,
        "LIVE_PRICES": LIVE_PRICES,
    }
    exec(compile(module, str(wallet_path), "exec"), ns)
    ns["_wallets"] = wallets
    ns["_credit_log"] = credit_log
    return ns


@pytest.fixture()
def env():
    return _load_refund_bet()


# ---------------------------------------------------------------------
# Branch 1: crypto_bet_amount + active_currency (single-player games)
# ---------------------------------------------------------------------


def test_refund_uses_stored_crypto_amount_when_available(env) -> None:
    """When a single-player game stored ``crypto_bet_amount`` and
    ``active_currency``, refund should use those directly and NOT touch
    LIVE_PRICES at all."""
    game_data = {
        "id": "GAME1",
        "user_id": 42,
        "bet_amount": 50.0,
        "crypto_bet_amount": 0.000833,  # ~$50 worth of BTC at $60k
        "active_currency": "BTC",
    }
    credited, coin = env["refund_bet"](42, game_data, reason="test")
    assert credited == pytest.approx(0.000833)
    assert coin == "BTC"
    assert env["_wallets"][42]["BTC"] == pytest.approx(0.000833)
    # Did NOT fall back to credit_wallet_safe
    assert env["_credit_log"] == []


def test_refund_uses_crypto_amount_even_after_price_crash(env) -> None:
    """The headline invariant for Phase 1f: a 20% price drop after the
    bet does NOT change what the user gets back."""
    game_data = {
        "user_id": 7,
        "bet_amount": 50.0,
        "crypto_bet_amount": 0.000833,
        "active_currency": "BTC",
    }
    # Simulate BTC dropping from $60k to $50k
    env["LIVE_PRICES"]["BTC"] = 50_000.0
    credited, coin = env["refund_bet"](7, game_data, reason="test")
    # User must get back EXACTLY 0.000833 BTC -- not 0.001 BTC (which is
    # what the old credit_wallet(50.0) would have given them at the new
    # price).
    assert credited == pytest.approx(0.000833)
    assert coin == "BTC"
    assert env["_credit_log"] == []


def test_refund_uses_crypto_amount_even_after_price_pump(env) -> None:
    """Symmetric case: if the price rises and we used USD@LIVE_PRICES
    we'd shortchange the user. The user gets back exactly what they
    bet."""
    game_data = {
        "user_id": 7,
        "bet_amount": 50.0,
        "crypto_bet_amount": 0.000833,
        "active_currency": "BTC",
    }
    env["LIVE_PRICES"]["BTC"] = 80_000.0
    credited, coin = env["refund_bet"](7, game_data, reason="test")
    assert credited == pytest.approx(0.000833)
    assert coin == "BTC"


# ---------------------------------------------------------------------
# Branch 2: per-player deducted record (PvP games)
# ---------------------------------------------------------------------


def test_refund_uses_per_player_deducted_record_pvp(env) -> None:
    """PvP games store ``deducted = {host_id: {crypto_amount, coin},
    opponent_id: {crypto_amount, coin}}``. Each player must get back
    their own exact crypto."""
    match = {
        "id": "MATCH1",
        "players": [101, 202],
        "bet_amount_usd": 100.0,
        "deducted": {
            101: {"crypto_amount": 0.001666, "coin": "BTC"},
            202: {"crypto_amount": 110.0, "coin": "USDT"},
        },
    }
    # Host
    credited, coin = env["refund_bet"](101, match, reason="test")
    assert credited == pytest.approx(0.001666)
    assert coin == "BTC"
    # Opponent
    credited, coin = env["refund_bet"](202, match, reason="test")
    assert credited == pytest.approx(110.0)
    assert coin == "USDT"


def test_refund_handles_string_keyed_deducted(env) -> None:
    """Deducted records may have been JSON-roundtripped (which converts
    int keys to strings). The helper must still find them."""
    match = {
        "players": [101],
        "bet_amount_usd": 100.0,
        "deducted": {
            "101": {"crypto_amount": 0.001666, "coin": "BTC"},
        },
    }
    credited, coin = env["refund_bet"](101, match, reason="test")
    assert credited == pytest.approx(0.001666)
    assert coin == "BTC"


def test_refund_prefers_per_player_deducted_over_crypto_bet_amount(env) -> None:
    """If both ``deducted`` and ``crypto_bet_amount`` exist on the
    match (unlikely but possible), the per-player record wins because
    it's the most specific."""
    match = {
        "players": [101],
        "bet_amount_usd": 100.0,
        "crypto_bet_amount": 999.0,
        "active_currency": "USDT",
        "deducted": {101: {"crypto_amount": 0.001666, "coin": "BTC"}},
    }
    credited, coin = env["refund_bet"](101, match, reason="test")
    assert credited == pytest.approx(0.001666)
    assert coin == "BTC"


# ---------------------------------------------------------------------
# Branch 3: locked price quote (Phase 1d-style)
# ---------------------------------------------------------------------


def test_refund_uses_locked_price_when_no_crypto_amount(env) -> None:
    """If only a ``locked_price`` quote was stored (Phase 1d style),
    the helper reconstructs the crypto amount from the USD bet."""
    game_data = {
        "user_id": 1,
        "bet_amount": 50.0,
        "locked_price": 60_000.0,
        "locked_coin": "BTC",
    }
    credited, coin = env["refund_bet"](1, game_data, reason="test")
    # $50 / $60k = 0.000833...
    assert credited == pytest.approx(50.0 / 60_000.0)
    assert coin == "BTC"


def test_refund_locked_price_ignores_subsequent_drift(env) -> None:
    game_data = {
        "user_id": 1,
        "bet_amount": 50.0,
        "locked_price": 60_000.0,
        "locked_coin": "BTC",
    }
    env["LIVE_PRICES"]["BTC"] = 30_000.0
    credited, _ = env["refund_bet"](1, game_data, reason="test")
    assert credited == pytest.approx(50.0 / 60_000.0)
    # At the current price the user would have got 50/30000 = 0.001666
    # -- twice as much BTC. Confirm we did NOT do that.
    assert credited != pytest.approx(50.0 / 30_000.0)


# ---------------------------------------------------------------------
# Branch 4: fallback to credit_wallet_safe + warning log
# ---------------------------------------------------------------------


def test_refund_fallback_warns_and_uses_live_price(env, caplog) -> None:
    """If the game_data has NO crypto info, we have to use the old
    USD-at-current-price behaviour -- but log loudly so operators can
    audit."""
    game_data = {
        "user_id": 5,
        "bet_amount": 100.0,
        # No crypto_bet_amount, no active_currency, no locked_price.
    }
    with caplog.at_level(logging.WARNING):
        credited, coin = env["refund_bet"](5, game_data, reason="test")
    # At LIVE_PRICES["USDT"]=1.0, $100 -> 100 USDT
    assert credited == pytest.approx(100.0)
    assert coin == "USDT"
    # The fallback should have been logged as a warning
    matching = [r for r in caplog.records
                if r.levelno >= logging.WARNING
                and "FALLBACK" in r.getMessage()]
    assert matching, "expected a WARNING log about the fallback"


def test_refund_with_no_bet_amount_at_all_returns_zero(env) -> None:
    """If we have neither crypto info nor a USD bet, return (0.0, coin)
    instead of crashing."""
    game_data = {"user_id": 99}  # No bet info at all
    credited, _ = env["refund_bet"](99, game_data, reason="test")
    assert credited == 0.0


# ---------------------------------------------------------------------
# Defensive input handling
# ---------------------------------------------------------------------


@pytest.mark.parametrize("bad_amount", [
    0, -1.0, float("nan"), float("inf"), float("-inf"),
])
def test_refund_rejects_invalid_crypto_amounts(env, bad_amount, caplog) -> None:
    game_data = {
        "user_id": 5,
        "bet_amount": 50.0,
        "crypto_bet_amount": bad_amount,
        "active_currency": "BTC",
    }
    with caplog.at_level(logging.WARNING):
        credited, _ = env["refund_bet"](5, game_data, reason="test")
    # Nothing credited
    assert credited == 0.0
    # Wallet untouched
    assert env["_wallets"].get(5, {}).get("BTC", 0.0) == 0.0
    matching = [r for r in caplog.records
                if r.levelno >= logging.WARNING
                and "rejected invalid crypto amount" in r.getMessage()]
    assert matching, "expected a WARNING about the invalid crypto amount"
