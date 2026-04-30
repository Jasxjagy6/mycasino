"""One-call wiring of the zero-downtime runtime into a PTB application.

Typical use from ``bot.py``::

    app = app_builder.build()
    ...
    from runtime import register_runtime
    register_runtime(app, is_admin=is_admin)

The function is idempotent — calling it twice on the same application
is a no-op.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Optional, TYPE_CHECKING

from runtime.admin_handlers import register_admin_handlers
from runtime.plugin_loader import PluginManager, install, is_installed

if TYPE_CHECKING:  # pragma: no cover
    from telegram.ext import Application

logger = logging.getLogger(__name__)

_RUNTIME_FLAG = "_mycasino_runtime_installed"


def register_runtime(
    application: "Application",
    *,
    is_admin: Optional[Callable[[int], bool]] = None,
    plugins_package: str = "plugins",
    autoload_plugins: Optional[bool] = None,
) -> PluginManager:
    """Wire the runtime layer onto an existing PTB application.

    Parameters
    ----------
    application:
        The :class:`telegram.ext.Application` instance you just built.
    is_admin:
        Optional sync callable ``(user_id) -> bool``.  When supplied it
        is used to gate the admin commands; otherwise the runtime falls
        back to the ``BOT_OWNER_IDS`` env var.
    plugins_package:
        Importable package containing plugin modules (default
        ``"plugins"``).
    autoload_plugins:
        If ``None`` (default) the runtime auto-loads plugins on startup
        only when the env var ``MYCASINO_AUTOLOAD_PLUGINS`` is truthy
        (``1``/``true``/``yes``).  Pass ``True``/``False`` to force.
    """
    if getattr(application, _RUNTIME_FLAG, False):
        logger.debug("Runtime already installed on application; skipping")
        return application.bot_data.get("plugin_manager")  # type: ignore[return-value]

    manager = PluginManager(application, package=plugins_package)
    if not is_installed():
        install(manager)

    register_admin_handlers(application, manager, is_admin=is_admin)
    application.bot_data["plugin_manager"] = manager
    setattr(application, _RUNTIME_FLAG, True)

    if autoload_plugins is None:
        autoload_plugins = _truthy(os.environ.get("MYCASINO_AUTOLOAD_PLUGINS"))

    if autoload_plugins:
        # Defer to post_init so we run on the application's event loop.
        prev_post_init = application.post_init

        async def _runtime_post_init(app):
            if prev_post_init is not None:
                await prev_post_init(app)
            try:
                names = await manager.load_all()
                if names:
                    logger.info(
                        "Auto-loaded plugins: %s", ", ".join(names)
                    )
                else:
                    logger.info("No plugins discovered for auto-load")
            except Exception:  # noqa: BLE001
                logger.exception("Plugin autoload failed")

        application.post_init = _runtime_post_init  # type: ignore[assignment]

    logger.info(
        "Zero-downtime runtime installed (package=%s, autoload=%s)",
        plugins_package,
        autoload_plugins,
    )
    return manager


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def schedule_load_all(manager: PluginManager) -> asyncio.Task:
    """Schedule a load_all() on the running loop; returns the Task."""
    loop = asyncio.get_event_loop()
    return loop.create_task(manager.load_all())
