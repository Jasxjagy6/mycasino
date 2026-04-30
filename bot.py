"""mycasino — Telegram casino bot launcher.

Historically this file was a single 39,371-line monolith.  It has been
split into a proper Python package layout so the bot can be developed,
tested and **deployed with zero downtime**:

* ``core.foundation`` — shared imports, environment, configuration,
  module-level state, the ``main()`` bootstrap and every helper that
  the original bot called *before* ``main()`` ran.  Auto-generated
  from the original bot.py top-level by ``.refactor/split_bot.py``.
* ``core.wallet``, ``core.deposits``, ``core.dashboards``,
  ``core.helpers``, ``core.persistence``, ``core.i18n``,
  ``core.levels``, ``core.achievements``, ``core.max_bets``,
  ``core.misc``, ``core.bootstrap`` — feature-grouped support modules.
* ``plugins.games_*`` — per-game plugins (blackjack, dice, slots,
  roulette, mines, tower, limbo, keno, highlow, matches, plinko,
  chicken_road, jackpot).
* ``plugins.admin_commands``, ``plugins.wallet_commands``,
  ``plugins.bonus``, ``plugins.referral``, ``plugins.leaderboard``,
  ``plugins.raffle``, ``plugins.escrow``, ``plugins.ai_features``,
  ``plugins.account``, ``plugins.general`` — feature plugins.
* ``runtime/`` — zero-downtime runtime: hot-reload manager
  (``/reload``, ``/reloadall``, ``/listplugins``, ``/runtimestatus``),
  blue-green webhook server with health endpoints, Redis-Streams
  receiver/worker pair for decoupled scale-out.

This launcher is intentionally tiny: it loads the foundation, calls
``foundation._wireup()`` to bind every split module's namespace into
a single shared dict (so cross-module function calls resolve), then
runs the casino's original ``main()`` exactly as the monolith always
did — with the zero-downtime runtime auto-installed.
"""
from __future__ import annotations

import logging
import sys

# ---------------------------------------------------------------------------
# 1) Load the shared casino runtime (imports, env, helper bots, model state,
#    multipliers, currency rates, deposit system, dashboards, the original
#    main() bootstrap).
# ---------------------------------------------------------------------------
from core import foundation  # noqa: E402

# ---------------------------------------------------------------------------
# 2) Wire every split module into foundation's shared namespace so the
#    monolith's hundreds of cross-module function references resolve at
#    call time.  Loads every core.* and plugins.* module in dependency order.
# ---------------------------------------------------------------------------
foundation._wireup()


# ---------------------------------------------------------------------------
# 3) Install the zero-downtime runtime.  We do it lazily, *just before*
#    the Application starts polling/serving webhooks, by patching
#    Application.run_polling / Application.run_webhook.  This avoids
#    duplicating any of main()'s setup logic.
# ---------------------------------------------------------------------------
_runtime_installed = False


def _install_runtime_on(app) -> None:
    global _runtime_installed
    if _runtime_installed:
        return
    _runtime_installed = True
    try:
        from runtime import register_runtime
        register_runtime(
            app,
            is_admin=getattr(foundation, "is_admin", None),
            autoload_plugins=False,  # plugins are already part of foundation
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Zero-downtime runtime not installed: %s: %s",
            type(exc).__name__, exc, exc_info=True,
        )


def _patched_main() -> None:
    """Run the original ``main()`` with zero-downtime runtime injection."""
    from telegram.ext import Application

    original_run_polling = Application.run_polling
    original_run_webhook = Application.run_webhook

    def _patched_run_polling(self, *args, **kwargs):
        _install_runtime_on(self)
        return original_run_polling(self, *args, **kwargs)

    def _patched_run_webhook(self, *args, **kwargs):
        _install_runtime_on(self)
        return original_run_webhook(self, *args, **kwargs)

    Application.run_polling = _patched_run_polling  # type: ignore[assignment]
    Application.run_webhook = _patched_run_webhook  # type: ignore[assignment]
    try:
        foundation.main()
    finally:
        Application.run_polling = original_run_polling  # type: ignore[assignment]
        Application.run_webhook = original_run_webhook  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 4) Worker factory for the Redis-Streams scale-out architecture.
#    ``runtime.queue_worker`` imports ``bot:_build_worker_application`` to
#    construct an Application identical to the polling/webhook bot but
#    driven by ``Application.update_queue``.
# ---------------------------------------------------------------------------
def _build_worker_application():
    from telegram.ext import ApplicationBuilder

    builder = (
        ApplicationBuilder()
        .token(foundation.BOT_TOKEN)
        .concurrent_updates(512)
        .get_updates_pool_timeout(30)
        .get_updates_connect_timeout(15)
        .get_updates_read_timeout(15)
        .get_updates_write_timeout(15)
        .connection_pool_size(512)
        .pool_timeout(30)
        .connect_timeout(15)
        .read_timeout(30)
        .write_timeout(30)
    )
    create_rl = getattr(foundation, "create_optional_rate_limiter", None)
    if callable(create_rl):
        rate_limiter = create_rl()
        if rate_limiter is not None:
            builder = builder.rate_limiter(rate_limiter)
    app = builder.build()
    try:
        from runtime import register_runtime
        register_runtime(
            app,
            is_admin=getattr(foundation, "is_admin", None),
            autoload_plugins=False,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Worker: zero-downtime runtime not installed: %s: %s",
            type(exc).__name__, exc, exc_info=True,
        )
    return app


# Re-export the helper so existing imports (``from bot import is_admin``)
# keep working.
is_admin = getattr(foundation, "is_admin", None)


if __name__ == "__main__":
    try:
        _patched_main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
