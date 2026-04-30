"""Plugin discovery and loading.

The ``plugins/`` package is the home for hot-reloadable casino feature
modules.  A plugin is any module that defines a top-level
``register(ctx)`` function — see :class:`runtime.hot_reload.PluginContext`
for the API.  Modules whose names start with ``_`` are ignored, as is
``__init__.py``.

This module owns the singleton :class:`PluginManager` so that ``bot.py``
and the admin command handlers can share one view of the plugin
registry.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from typing import Iterable, List, Optional, TYPE_CHECKING

from runtime.hot_reload import HotReloadManager

if TYPE_CHECKING:  # pragma: no cover
    from telegram.ext import Application

logger = logging.getLogger(__name__)


class PluginManager:
    """Discovers plugins on disk and delegates load/reload to the manager."""

    def __init__(
        self,
        application: "Application",
        package: str = "plugins",
    ) -> None:
        self.application = application
        self.package = package
        self.hot_reload = HotReloadManager(application, package=package)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> List[str]:
        """Return every plugin short-name found under ``self.package``.

        Honours the ``MYCASINO_PLUGIN_ALLOWLIST`` env var (comma-
        separated short-names) when set, so deploys can ship the same
        code with a different active feature set.
        """
        try:
            pkg = importlib.import_module(self.package)
        except ModuleNotFoundError:
            logger.warning(
                "Plugin package '%s' not importable — no plugins loaded",
                self.package,
            )
            return []

        names: List[str] = []
        for _finder, name, ispkg in pkgutil.iter_modules(pkg.__path__):
            if name.startswith("_"):
                continue
            if ispkg:
                # Sub-packages are allowed but only their top-level
                # ``__init__`` participates in plugin discovery; for that
                # the sub-package itself must define ``register``.
                names.append(name)
            else:
                names.append(name)

        allow = os.environ.get("MYCASINO_PLUGIN_ALLOWLIST", "").strip()
        if allow:
            allowed = {x.strip() for x in allow.split(",") if x.strip()}
            names = [n for n in names if n in allowed]

        deny = os.environ.get("MYCASINO_PLUGIN_DENYLIST", "").strip()
        if deny:
            denied = {x.strip() for x in deny.split(",") if x.strip()}
            names = [n for n in names if n not in denied]

        return sorted(names)

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    async def load_all(self) -> List[str]:
        loaded: List[str] = []
        for name in self.discover():
            try:
                await self.hot_reload.load(name)
                loaded.append(name)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to load plugin %s", name)
        return loaded

    async def reload(self, name: str) -> dict:
        return await self.hot_reload.reload(name)

    async def reload_all(self) -> dict:
        return await self.hot_reload.reload_all()

    async def unload(self, name: str) -> bool:
        return await self.hot_reload.unload(name)

    def list_plugins(self) -> List[str]:
        return self.hot_reload.list_plugins()

    def info(self, name: str) -> Optional[dict]:
        return self.hot_reload.info(name)


# ---------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------

_singleton: Optional[PluginManager] = None


def install(manager: PluginManager) -> None:
    """Register *manager* as the process-wide singleton."""
    global _singleton
    _singleton = manager


def get_plugin_manager() -> PluginManager:
    if _singleton is None:
        raise RuntimeError(
            "PluginManager has not been installed yet — call "
            "runtime.register_runtime(application) first"
        )
    return _singleton


def is_installed() -> bool:
    return _singleton is not None


def discovered_names_from_dir(plugins_dir: str) -> Iterable[str]:
    """Pure-filesystem discovery, used by the test suite."""
    if not os.path.isdir(plugins_dir):
        return []
    out: List[str] = []
    for entry in sorted(os.listdir(plugins_dir)):
        if entry.startswith("_"):
            continue
        if entry.endswith(".py"):
            out.append(entry[:-3])
        elif os.path.isdir(os.path.join(plugins_dir, entry)) and os.path.isfile(
            os.path.join(plugins_dir, entry, "__init__.py")
        ):
            out.append(entry)
    return out
