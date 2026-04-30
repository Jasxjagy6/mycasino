"""Telegram admin commands for the zero-downtime runtime.

Adds:

* ``/reload <plugin>`` — hot-swap a single plugin via importlib.reload.
* ``/reloadall`` — reload every currently-loaded plugin.
* ``/loadplugin <plugin>`` — load a plugin that wasn't loaded at start.
* ``/unloadplugin <plugin>`` — remove a plugin's handlers + tasks.
* ``/listplugins`` — show loaded plugins, version, handler count.
* ``/runtimestatus`` — process uptime, plugin count, queue stats if Redis is configured.

Authorisation defers to the host bot's ``is_admin`` callable when
provided; otherwise it falls back to the ``BOT_OWNER_IDS`` env var.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Awaitable, Callable, List, Optional, TYPE_CHECKING

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes

if TYPE_CHECKING:  # pragma: no cover
    from telegram.ext import Application

    from runtime.plugin_loader import PluginManager

logger = logging.getLogger(__name__)

_PROCESS_START = time.time()


def _default_is_admin() -> Callable[[int], bool]:
    raw = os.environ.get("BOT_OWNER_IDS", "")
    ids = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ids.add(int(token))
        except ValueError:
            continue

    def _check(user_id: int) -> bool:
        return user_id in ids

    return _check


def _format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h >= 24:
        d, h = divmod(h, 24)
        return f"{d}d{h:02d}h{m:02d}m{s:02d}s"
    return f"{h:02d}h{m:02d}m{s:02d}s"


def register_admin_handlers(
    application: "Application",
    plugin_manager: "PluginManager",
    *,
    is_admin: Optional[Callable[[int], bool]] = None,
    group: int = -100,
) -> None:
    """Register the runtime's admin commands on *application*.

    ``group`` defaults to a very negative number so the admin handlers
    fire before any plugin handler that might capture the same command
    name in group 0.
    """

    if is_admin is None:
        is_admin = _default_is_admin()

    async def _guard(update: Update) -> bool:
        user = update.effective_user
        if user is None or not is_admin(user.id):
            if update.message is not None:
                await update.message.reply_text(
                    "\U0001f6ab Admin only."
                )
            return False
        return True

    async def _reload_cmd(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await _guard(update):
            return
        if not context.args:
            await update.message.reply_text(
                "Usage: /reload <plugin>"
            )
            return
        name = context.args[0].strip()
        try:
            info = await plugin_manager.reload(name)
        except Exception as e:  # noqa: BLE001
            logger.exception("/reload %s failed", name)
            await update.message.reply_text(
                f"\u274c Reload of <code>{name}</code> failed:\n<pre>{type(e).__name__}: {e}</pre>",
                parse_mode=ParseMode.HTML,
            )
            return
        await update.message.reply_text(
            f"\u2705 Reloaded <b>{info['name']}</b> "
            f"(v{info['version']}, {info['handlers']} handlers)",
            parse_mode=ParseMode.HTML,
        )

    async def _reload_all_cmd(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await _guard(update):
            return
        results = await plugin_manager.reload_all()
        if not results:
            await update.message.reply_text("(no plugins loaded)")
            return
        lines: List[str] = []
        for name, status in results.items():
            mark = "\u2705" if status == "ok" else "\u274c"
            lines.append(f"{mark} {name}: {status}")
        await update.message.reply_text(
            "Reload-all results:\n" + "\n".join(lines)
        )

    async def _load_cmd(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await _guard(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /loadplugin <plugin>")
            return
        name = context.args[0].strip()
        try:
            info = await plugin_manager.hot_reload.load(name)
        except Exception as e:  # noqa: BLE001
            logger.exception("/loadplugin %s failed", name)
            await update.message.reply_text(
                f"\u274c Load of <code>{name}</code> failed:\n<pre>{type(e).__name__}: {e}</pre>",
                parse_mode=ParseMode.HTML,
            )
            return
        await update.message.reply_text(
            f"\u2705 Loaded <b>{info['name']}</b> "
            f"({info['handlers']} handlers)",
            parse_mode=ParseMode.HTML,
        )

    async def _unload_cmd(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await _guard(update):
            return
        if not context.args:
            await update.message.reply_text("Usage: /unloadplugin <plugin>")
            return
        name = context.args[0].strip()
        ok = await plugin_manager.unload(name)
        if ok:
            await update.message.reply_text(
                f"\u2705 Unloaded <b>{name}</b>", parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"(plugin {name} was not loaded)"
            )

    async def _list_cmd(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await _guard(update):
            return
        names = plugin_manager.list_plugins()
        if not names:
            await update.message.reply_text("(no plugins loaded)")
            return
        lines = ["<b>Loaded plugins</b>"]
        for name in names:
            info = plugin_manager.info(name) or {}
            lines.append(
                f"\u2022 <code>{name}</code> v{info.get('version', '?')} — "
                f"{info.get('handlers', '?')} handlers, "
                f"{info.get('tasks', '?')} tasks"
            )
        await update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.HTML
        )

    async def _status_cmd(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await _guard(update):
            return
        from runtime import queue_stats  # local import; optional

        names = plugin_manager.list_plugins()
        uptime = _format_uptime(time.time() - _PROCESS_START)
        lines = [
            "<b>Runtime status</b>",
            f"\u2022 uptime: <code>{uptime}</code>",
            f"\u2022 plugins loaded: <code>{len(names)}</code>",
        ]
        try:
            qs = await queue_stats.snapshot()
        except Exception:  # noqa: BLE001 — Redis optional
            qs = None
        if qs is not None:
            lines.append(
                "\u2022 redis stream: "
                f"<code>{qs['stream']}</code> len=<code>{qs['length']}</code> "
                f"groups=<code>{qs['groups']}</code>"
            )
        try:
            from runtime import antispam as _as
            asd = _as.get_stats()
            lines.append(
                "\u2022 antispam: "
                f"tracked=<code>{asd['tracked_users']}</code> "
                f"cooldowns=<code>{asd['active_cooldowns']}</code> "
                f"silenced=<code>{asd['callbacks_silenced']}</code> "
                f"foreign=<code>{asd['foreign_callbacks_silenced']}</code>"
            )
        except Exception:  # pragma: no cover
            pass
        try:
            from core import win_broadcaster as _wb
            wb = _wb.get_stats()
            lines.append(
                "\u2022 win broadcast: "
                f"channel=<code>{wb['channel']}</code> "
                f"queued=<code>{wb['queued']}</code> "
                f"dropped=<code>{wb['dropped']}</code> "
                f"helpers=<code>{wb['helper_pool_size']}</code> "
                f"worker=<code>{'on' if wb['worker_alive'] else 'off'}</code>"
            )
        except Exception:  # pragma: no cover
            pass
        await update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.HTML
        )

    async def _refreshcore_cmd(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Reload one or more core modules (those not in plugins/) and
        re-hoist their public names into every split module so the new
        code is reachable from late-bound plugin handlers."""
        if not await _guard(update):
            return
        if not context.args:
            await update.message.reply_text(
                "Usage: /refreshcore <module> [<module> ...]\n"
                "Examples: /refreshcore core.wallet\n"
                "          /refreshcore core.win_broadcaster runtime.antispam"
            )
            return
        import importlib, sys as _sys
        results = []
        for raw in context.args:
            modname = raw.strip()
            try:
                if modname in _sys.modules:
                    importlib.reload(_sys.modules[modname])
                    action = "reloaded"
                else:
                    importlib.import_module(modname)
                    action = "loaded"
                results.append(f"\u2705 {modname} {action}")
            except Exception as e:  # noqa: BLE001
                logger.exception("/refreshcore %s failed", modname)
                results.append(f"\u274c {modname}: {type(e).__name__}: {e}")
        # Re-hoist core.* symbols into every split module so late-bound
        # references in already-loaded plugins see the new functions.
        try:
            from core import foundation as _f
            if hasattr(_f, "_wireup"):
                _f._wireup()
                results.append("\u2705 _wireup re-applied")
        except Exception as e:  # noqa: BLE001
            results.append(f"\u26a0 _wireup failed: {e}")
        # Make sure antispam middleware is installed.
        try:
            from runtime.antispam import install_antispam
            install_antispam(application)
            results.append("\u2705 antispam installed")
        except Exception as e:  # noqa: BLE001
            results.append(f"\u26a0 antispam install failed: {e}")
        await update.message.reply_text("\n".join(results))

    handlers = [
        CommandHandler("reload", _reload_cmd),
        CommandHandler("reloadall", _reload_all_cmd),
        CommandHandler("loadplugin", _load_cmd),
        CommandHandler("unloadplugin", _unload_cmd),
        CommandHandler("listplugins", _list_cmd),
        CommandHandler("runtimestatus", _status_cmd),
        CommandHandler("refreshcore", _refreshcore_cmd),
    ]
    for h in handlers:
        application.add_handler(h, group=group)
    logger.info(
        "Runtime admin handlers registered (group=%s, %d commands)",
        group,
        len(handlers),
    )


# Re-exported for symmetry with module docstring.
__all__ = ["register_admin_handlers"]


# Type alias used by bootstrap.
IsAdminFn = Callable[[int], bool]
AsyncIsAdminFn = Callable[[int], Awaitable[bool]]
