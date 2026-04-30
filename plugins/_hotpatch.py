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

    # 1. Ensure the new win_broadcaster module is imported. Cancel any
    # in-flight worker first so the reload doesn't leave an old task
    # bound to stale code.
    try:
        old = sys.modules.get("core.win_broadcaster")
        if old is not None:
            t = getattr(old, "_worker_task", None)
            if t is not None and not t.done():
                try:
                    t.cancel()
                except Exception:
                    pass
            # Drop module-level state so reload starts clean.
            for k in ("_worker_task", "_queue", "_initialised_bots"):
                if hasattr(old, k):
                    try:
                        setattr(old, k, None if k != "_initialised_bots" else set())
                    except Exception:
                        pass
            importlib.reload(old)
        else:
            importlib.import_module("core.win_broadcaster")
        # Force the worker to start so the queue starts draining.
        try:
            wb = sys.modules["core.win_broadcaster"]
            wb._ensure_worker()
        except Exception:
            logger.exception("[hotpatch] _ensure_worker failed")
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

    # 2b. Push the freshly-reloaded wallet symbols into every plugin
    # module's namespace, OVERWRITING the stale references they
    # received via `from core.foundation import *` at original import
    # time. The default _wireup() pushback uses setdefault, which won't
    # replace already-set names — that's exactly why /scratch & friends
    # call the OLD update_stats_on_bet (no win-broadcast hook).
    try:
        wallet_mod = sys.modules.get("core.wallet")
        if wallet_mod is not None:
            wallet_public = {
                k: getattr(wallet_mod, k)
                for k in dir(wallet_mod)
                if not k.startswith("__")
                and getattr(getattr(wallet_mod, k, None), "__module__", "") == "core.wallet"
            }
            replaced = 0
            for mn, mod in list(sys.modules.items()):
                if not mn.startswith("plugins.") and mn != "core.foundation":
                    continue
                if mod is None:
                    continue
                for k, v in wallet_public.items():
                    if k in mod.__dict__ and mod.__dict__[k] is not v:
                        mod.__dict__[k] = v
                        replaced += 1
            logger.info(
                "[hotpatch] re-bound %d wallet symbols across plugins",
                replaced,
            )
    except Exception:
        logger.exception("[hotpatch] wallet re-bind failed")

    # 3. Re-run _wireup() to re-hoist symbols across split modules.
    try:
        from core import foundation as _f
        if hasattr(_f, "_wireup"):
            _f._wireup()
            logger.info("[hotpatch] _wireup re-applied")
    except Exception:
        logger.exception("[hotpatch] _wireup failed")

    # 4. Install anti-spam middleware. We tear down any previously
    # installed handler first because a prior version of this hotpatch
    # registered the middleware with ``block=False`` which prevents
    # ``ApplicationHandlerStop`` from short-circuiting downstream
    # handlers — taking it out and re-installing with ``block=True``
    # is the safe path.
    try:
        try:
            for group, handlers in list((app.handlers or {}).items()):
                for h in list(handlers):
                    cb = getattr(h, "callback", None)
                    if getattr(cb, "__module__", "") == "runtime.antispam":
                        try:
                            app.remove_handler(h, group=group)
                        except Exception:
                            pass
            setattr(app, "_antispam_installed", False)
        except Exception:
            pass
        # Reload the module so the new ``block=True`` registration
        # path is in effect even after a partial earlier install.
        try:
            import runtime.antispam as _as
            importlib.reload(_as)
        except Exception:
            from runtime import antispam as _as  # noqa: F401
        from runtime.antispam import install_antispam
        install_antispam(app)
        logger.info("[hotpatch] antispam middleware installed (block=True)")
    except Exception:
        logger.exception("[hotpatch] antispam install failed")

    # 4b. Reload runtime.admin_handlers + re-register the runtime command
    # surface so /runtimestatus picks up the antispam + win-broadcast
    # counter blocks (and so /refreshcore is available without a bot
    # restart).
    try:
        import runtime.admin_handlers as _ah
        importlib.reload(_ah)
        # Strip any previous runtime admin handlers we own so we don't
        # double-register them.
        try:
            for group, handlers in list((app.handlers or {}).items()):
                for h in list(handlers):
                    cb = getattr(h, "callback", None)
                    cb_mod = getattr(cb, "__module__", "")
                    cb_qual = getattr(cb, "__qualname__", "")
                    if cb_mod == "runtime.admin_handlers" or (
                        cb_qual.endswith("_status_cmd")
                        or cb_qual.endswith("_list_cmd")
                        or cb_qual.endswith("_reload_cmd")
                        or cb_qual.endswith("_reloadall_cmd")
                        or cb_qual.endswith("_loadplugin_cmd")
                        or cb_qual.endswith("_unloadplugin_cmd")
                        or cb_qual.endswith("_refreshcore_cmd")
                    ):
                        try:
                            app.remove_handler(h, group=group)
                        except Exception:
                            pass
        except Exception:
            pass
        # Re-call register_runtime to install the freshly-reloaded
        # admin command surface against the same plugin manager.
        try:
            from runtime import plugin_loader as _pl
            from core.foundation import is_admin as _is_admin
            pm = getattr(_pl, "_singleton", None)
            if pm is not None and hasattr(_ah, "register_admin_handlers"):
                _ah.register_admin_handlers(app, pm, is_admin=_is_admin)
                logger.info("[hotpatch] admin handlers re-registered")
        except Exception:
            logger.exception("[hotpatch] admin handler re-register failed")
    except Exception:
        logger.exception("[hotpatch] admin_handlers reload failed")

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
