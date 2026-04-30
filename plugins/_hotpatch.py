"""One-shot bootstrapper that lights up the session-7 upgrades on a
running bot without restarting the process.

Loaded once via ``/loadplugin _hotpatch``. Its ``register(ctx)``:

1. Imports the new ``core.win_broadcaster`` module.
2. Reloads ``core.wallet`` so ``update_stats_on_bet`` picks up the new
   broadcast hook.
3. Re-runs ``core.foundation._wireup()`` so every split module's
   namespace sees the new hooked function (late-bound name resolution).
4. Imports + installs the anti-spam middleware
   (``runtime.antispam.install_antispam``) onto the running application.

Idempotent — safe to ``/reload _hotpatch`` repeatedly.
"""
from __future__ import annotations

import importlib
import logging
import sys

logger = logging.getLogger(__name__)

VERSION = 1


def register(ctx):
    app = ctx.application

    # 1. Ensure the new win_broadcaster module is imported.
    try:
        if "core.win_broadcaster" in sys.modules:
            importlib.reload(sys.modules["core.win_broadcaster"])
        else:
            importlib.import_module("core.win_broadcaster")
        logger.info("[hotpatch] core.win_broadcaster ready")
    except Exception:
        logger.exception("[hotpatch] win_broadcaster import failed")

    # 2. Reload core.wallet so update_stats_on_bet has the new hook.
    try:
        importlib.reload(sys.modules["core.wallet"])
        logger.info("[hotpatch] core.wallet reloaded")
    except KeyError:
        importlib.import_module("core.wallet")
    except Exception:
        logger.exception("[hotpatch] core.wallet reload failed")

    # 3. Re-run _wireup() to re-hoist symbols across split modules.
    try:
        from core import foundation as _f
        if hasattr(_f, "_wireup"):
            _f._wireup()
            logger.info("[hotpatch] _wireup re-applied")
    except Exception:
        logger.exception("[hotpatch] _wireup failed")

    # 4. Install anti-spam middleware (idempotent).
    try:
        from runtime.antispam import install_antispam
        install_antispam(app)
        logger.info("[hotpatch] antispam middleware installed")
    except Exception:
        logger.exception("[hotpatch] antispam install failed")

    # 5. Patch the running PluginManager so its `_adopt_existing`
    # picks up handlers wrapped by core.foundation decorators
    # (`check_banned`, `check_maintenance`). Without this, /reload of
    # plugins whose handlers go through those decorators silently
    # leaves the OLD handlers in place, so new code never runs.
    try:
        import importlib as _imp
        import runtime.hot_reload as _hr
        _imp.reload(_hr)
        # Find the live PluginManager singleton.
        from runtime import plugin_loader as _pl
        pm = getattr(_pl, "_singleton", None)
        hr = getattr(pm, "hot_reload", None) if pm is not None else None
        if hr is not None:
            # Replace the method on the live instance with the freshly
            # reloaded class's implementation.
            import types
            hr._adopt_existing = types.MethodType(
                _hr.HotReloadManager._adopt_existing, hr
            )
            logger.info(
                "[hotpatch] HotReloadManager._adopt_existing patched in-place"
            )
        else:
            logger.warning(
                "[hotpatch] could not locate live PluginManager — _adopt_existing not patched"
            )
        # Force-evict already-tracked plugins so the next /reload uses
        # the patched _adopt_existing path on a clean slate.
        if hr is not None:
            for stale in ("wallet_commands", "leaderboard"):
                if stale in hr._plugins:
                    rec = hr._plugins.pop(stale)
                    rec.handler_groups.clear()
                    rec.handlers.clear()
                    logger.info(
                        "[hotpatch] evicted stale plugin record: %s", stale
                    )

        # Walk the app's handler list and remove duplicate handlers
        # whose callback chain ultimately points at a function in any
        # wallet_commands / leaderboard module. This cleans up handlers
        # accumulated by previous broken /reloads. After this, the
        # plugin manager's `_adopt_existing` (now patched) will pick up
        # whatever's left on the next /reload.
        try:
            app2 = app
            CLEAN_PLUGINS = ("plugins.wallet_commands", "plugins.leaderboard")

            def _belongs_recursive(cb, plugin_full, depth=0, seen=None):
                if cb is None or depth > 8:
                    return False
                if getattr(cb, "__module__", "") == plugin_full:
                    return True
                if seen is None:
                    seen = set()
                if id(cb) in seen:
                    return False
                seen.add(id(cb))
                closure = getattr(cb, "__closure__", None) or ()
                for cell in closure:
                    try:
                        val = cell.cell_contents
                    except Exception:
                        continue
                    if callable(val) and _belongs_recursive(
                        val, plugin_full, depth + 1, seen
                    ):
                        return True
                return False

            removed = 0
            for plugin_full in CLEAN_PLUGINS:
                # Take a snapshot — modifying the dict-of-lists while
                # iterating is unsafe.
                snap = {
                    g: list(hs) for g, hs in (app2.handlers or {}).items()
                }
                for group, handlers in snap.items():
                    for h in handlers:
                        cb = getattr(h, "callback", None)
                        if _belongs_recursive(cb, plugin_full):
                            try:
                                app2.remove_handler(h, group=group)
                                removed += 1
                            except Exception:
                                pass
            logger.info(
                "[hotpatch] removed %d stale handlers from app", removed
            )
        except Exception:
            logger.exception("[hotpatch] handler cleanup failed")
    except Exception:
        logger.exception("[hotpatch] hot_reload patch failed")
