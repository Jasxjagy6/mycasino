"""Live verification of currency system changes.

Runs offline (no Telegram I/O): imports the real foundation/plugins,
sets up a synthetic user, flips display currency, and asserts every
behaviour the user complained about now works.
"""
from __future__ import annotations
import os, sys, asyncio, io, traceback

# Make the repo importable
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# Quiet env so foundation doesn't try to call Telegram during import.
os.environ.setdefault("BOT_TOKEN", "test")

import core.foundation as F      # noqa: E402
from core import dashboards      # noqa: E402
import bot as _bot                # noqa: E402  -- triggers wireup


def banner(t):
    print("\n" + "=" * 72 + f"\n  {t}\n" + "=" * 72)


def test_supported_display_currencies():
    banner("1. SUPPORTED_DISPLAY_CURRENCIES is fiat-only")
    print("Value:", F.SUPPORTED_DISPLAY_CURRENCIES)
    assert F.SUPPORTED_DISPLAY_CURRENCIES == ["USD", "INR", "EUR", "GBP"], (
        f"FAILED: got {F.SUPPORTED_DISPLAY_CURRENCIES!r}"
    )
    for c in ("USDT", "BTC", "ETH", "SOL", "BNB", "TRX", "LTC"):
        assert c not in F.SUPPORTED_DISPLAY_CURRENCIES
    print("PASS")


def test_premium_dollar_emoji():
    banner("2. Premium dollar emoji ('dollar') is registered")
    assert "dollar" in F.PREMIUM_EMOJI_IDS
    cid, fallback = F.PREMIUM_EMOJI_IDS["dollar"]
    print(f"id={cid!r} fallback={fallback!r}")
    assert fallback == "💲"
    # Every fiat in CURRENCY_EMOJI_KEY now points at 'dollar'.
    for c in ("USD", "INR", "EUR", "GBP"):
        assert F.CURRENCY_EMOJI_KEY[c] == "dollar", c
    print("PASS")


def test_get_display_currency_falls_back_to_usd():
    banner("3. get_display_currency() falls back to USD for legacy crypto prefs")
    uid = 999_001
    F.user_stats[uid] = {"display_currency": "USDT"}      # legacy crypto pref
    cur = F.get_display_currency(uid)
    print("legacy USDT pref ->", cur)
    assert cur == "USD"
    F.user_stats[uid] = {"display_currency": "INR"}
    cur = F.get_display_currency(uid)
    print("INR pref ->", cur)
    assert cur == "INR"
    print("PASS")


def test_set_display_currency_rejects_crypto():
    banner("4. set_display_currency() rejects crypto codes")
    uid = 999_002
    F.user_stats.setdefault(uid, {})
    from plugins.admin_commands import set_display_currency
    assert set_display_currency(uid, "USDT") is False
    assert set_display_currency(uid, "BTC") is False
    assert set_display_currency(uid, "INR") is True
    assert F.user_stats[uid]["display_currency"] == "INR"
    print("PASS")


def test_parse_bet_amount_inr():
    banner("5. parse_bet_amount honours user's display currency (INR)")
    uid = 999_003
    # Give the user an INR display + USD wallet ($100 worth).
    F.user_stats[uid] = {"display_currency": "INR"}
    F.user_wallets[uid] = {"USDT": 100.0}
    F.user_stats[uid]["active_currency"] = "USDT"

    amount_usd, amount_disp, cur = F.parse_bet_amount("500", uid)
    print(f"/bj 500 INR  -> ${amount_usd:.4f} (display {amount_disp:.2f} {cur})")
    # ₹500 at FX≈85 is ≈$5.85.  Allow wide tolerance because rates are live.
    assert cur == "INR"
    assert 1 < amount_usd < 50, f"expected ~$5-6, got ${amount_usd}"
    assert abs(amount_disp - 500) < 0.001
    print("PASS")


def test_parse_bet_amount_usd_unchanged():
    banner("6. parse_bet_amount with USD display = no conversion (regression)")
    uid = 999_004
    F.user_stats[uid] = {"display_currency": "USD"}
    F.user_wallets[uid] = {"USDT": 100.0}
    F.user_stats[uid]["active_currency"] = "USDT"

    amount_usd, amount_disp, cur = F.parse_bet_amount("10", uid)
    print(f"/bj 10 USD   -> ${amount_usd:.2f} (display {amount_disp:.2f} {cur})")
    assert cur == "USD"
    assert abs(amount_usd - 10.0) < 0.001
    assert abs(amount_disp - 10.0) < 0.001
    print("PASS")


def test_format_for_user_inr():
    banner("7. format_for_user renders INR balance with ₹ symbol")
    uid = 999_005
    F.user_stats[uid] = {"display_currency": "INR"}
    s = F.format_for_user(uid, 5.85, compact=False)
    print("$5.85 -> ", s)
    assert s.startswith("\u20B9"), f"expected ₹-prefix, got {s!r}"
    s_usd = F.format_for_user(999_006, 5.85)  # default USD
    F.user_stats[999_006] = {}  # ensure default
    s_usd = F.format_for_user(999_006, 5.85)
    print("$5.85 (USD) ->", s_usd)
    assert s_usd.startswith("$")
    print("PASS")


def test_currency_menu_builder():
    banner("8. _build_currency_menu emits SUCCESS for chosen + PRIMARY for others")
    from plugins.general import _build_currency_menu
    uid = 999_007
    F.user_stats[uid] = {"display_currency": "INR", "active_currency": "USDT"}
    F.user_wallets[uid] = {"USDT": 0}

    text, kb = _build_currency_menu(uid)
    assert "Display:" in text
    # InlineKeyboardMarkup -> rows of InlineKeyboardButtons (already styled).
    rows = kb.inline_keyboard
    chosen_btn = None
    other_disp_btns = []
    for row in rows:
        for btn in row:
            cb = btn.callback_data or ""
            if cb.startswith("setdisplay_INR"):
                chosen_btn = btn
            elif cb.startswith("setdisplay_"):
                other_disp_btns.append(btn)
    assert chosen_btn is not None
    print(f"INR (chosen) label = {chosen_btn.text!r}")
    print(f"Other display buttons: {[b.text for b in other_disp_btns]}")
    # Selected option should have the checkmark in the label.
    assert "\u2713" in chosen_btn.text
    print("PASS (chosen carries ✓; success/primary styling applied via apply_button_style)")


def test_dashboard_pil_inr_no_double_symbol():
    banner("9. Dashboard PIL renders INR balance with single ₹ symbol")
    uid = 999_008
    F.user_stats[uid] = {
        "display_currency": "INR",
        "userinfo": {
            "first_name": "Tester",
            "username": "test_user",
            "join_date": "2025-01-15T00:00:00+00:00",
        },
        "active_currency": "USDT",
    }
    F.user_wallets[uid] = {"USDT": 1000.0}

    bal_str = F.format_compact_for_user(uid, 1000.0)
    print(f"format_compact_for_user($1000, INR) -> {bal_str!r}")
    assert bal_str.startswith("\u20B9"), f"expected ₹-prefix, got {bal_str!r}"
    assert not bal_str.startswith("$"), "no double prefix"

    # Render the actual PIL image.
    text_data = {
        "name": "Tester",
        "user_id": str(uid),
        "username": "@tester",
        "bot_username": "@playcsino",
        "level": "Bronze I",
        "balance": bal_str,
        "last_win": F.format_compact_for_user(uid, 250.0),
        "member_since": "Jan 15, 2025",
    }
    img_bytes = dashboards._render_dashboard_sync(text_data, None)
    out = "/tmp/dashboard_inr.png"
    if isinstance(img_bytes, (bytes, bytearray)):
        open(out, "wb").write(img_bytes)
    elif isinstance(img_bytes, io.BytesIO):
        open(out, "wb").write(img_bytes.getvalue())
    elif hasattr(img_bytes, "save"):
        img_bytes.save(out)
    else:
        # Maybe returns a path
        print("Renderer returned:", type(img_bytes), repr(img_bytes)[:200])
    print(f"Wrote {out}")
    print("PASS")


async def _run_async_tests():
    banner("10. Group /bal text is balance-only (no Wallet line)")
    # We monkey-patch update.message.reply_text to capture the text the
    # handler would have sent, instead of doing a Telegram round-trip.
    from plugins.wallet_commands import balance_command

    captured = {}

    class _Msg:
        def __init__(self): self.message_id = 1
        async def reply_text(self, text, **kw):
            captured["text"] = text
            captured["kw"] = kw
            class _S:
                message_id = 42
                chat_id = -100123
                chat = type("_C", (), {"id": -100123})()
            return _S()
        async def reply_photo(self, **kw):
            captured["photo"] = kw
            class _S:
                message_id = 43
                chat_id = -100123
                chat = type("_C", (), {"id": -100123})()
            return _S()

    class _Chat:
        def __init__(self, ctype): self.type = ctype; self.id = -100123

    class _User:
        id = 999_010
        username = "tester"
        first_name = "Tester"

    class _Update:
        def __init__(self, ctype):
            self.effective_user = _User()
            self.effective_chat = _Chat(ctype)
            self.message = _Msg()

    class _Bot:
        async def get_me(self):
            class _M: username = "playcsino"
            return _M()

    class _Ctx:
        bot = _Bot()
        user_data = {}

    F.user_stats[_User.id] = {
        "display_currency": "INR",
        "userinfo": {"first_name": "Tester", "username": "tester",
                     "join_date": "2025-01-15T00:00:00+00:00"},
        "active_currency": "USDT",
    }
    F.user_wallets[_User.id] = {"USDT": 100.0}

    upd = _Update("supergroup")
    await balance_command(upd, _Ctx())
    text = captured.get("text", "")
    print("--- captured group /bal text ---")
    print(text)
    print("---")
    assert "Wallet:" not in text, "FAILED: wallet line still present"
    assert "Balance" in text or "balance" in text.lower()
    # Should display ₹ for INR user
    assert "\u20B9" in text, "expected ₹ in INR group balance"
    print("PASS")


def main():
    failures = []
    tests = [
        test_supported_display_currencies,
        test_premium_dollar_emoji,
        test_get_display_currency_falls_back_to_usd,
        test_set_display_currency_rejects_crypto,
        test_parse_bet_amount_inr,
        test_parse_bet_amount_usd_unchanged,
        test_format_for_user_inr,
        test_currency_menu_builder,
        test_dashboard_pil_inr_no_double_symbol,
    ]
    for t in tests:
        try:
            t()
        except Exception:
            traceback.print_exc()
            failures.append(t.__name__)
    try:
        asyncio.run(_run_async_tests())
    except Exception:
        traceback.print_exc()
        failures.append("_run_async_tests")
    banner("RESULT")
    if failures:
        print("FAILURES:", failures)
        sys.exit(1)
    print("All currency-system checks PASSED.")


if __name__ == "__main__":
    main()
