"""In-process hot-reload manager.

Wraps :func:`importlib.reload` with the bookkeeping required to swap a
plugin module while the PTB ``Application`` is running:

* tracks which handlers each plugin registered with the dispatcher so
  they can be removed cleanly before the new version registers fresh
  handlers;
* tracks which background tasks each plugin spawned via
  :meth:`PluginContext.spawn_task` so old tasks are cancelled before the
  reloaded module starts new ones;
* runs the plugin's optional ``on_reload``/``on_unload`` lifecycle
  hooks under an ``asyncio.Lock`` so two concurrent ``/reload`` commands
  cannot race;
* preserves per-plugin state via the ``state`` dict on
  :class:`PluginContext` — modules that want their state to survive a
  reload simply read/write through ``ctx.state``.

Reloads are best-effort: if the new version of the module raises during
``register`` the manager rolls the dispatcher back to the previous
state and re-raises so the admin sees the traceback.  The bot keeps
running on the old code in that case — never a half-loaded plugin.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
import time
import traceback
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from telegram.ext import Application, BaseHandler

logger = logging.getLogger(__name__)


@dataclass
class PluginRecord:
    """Bookkeeping for a single loaded plugin module."""

    name: str
    module: ModuleType
    handlers: List["BaseHandler"] = field(default_factory=list)
    handler_groups: Dict[int, List["BaseHandler"]] = field(default_factory=dict)
    tasks: List[asyncio.Task] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)
    loaded_at: float = field(default_factory=time.time)
    version: int = 1

    def add_handler_record(self, handler: "BaseHandler", group: int) -> None:
        self.handlers.append(handler)
        self.handler_groups.setdefault(group, []).append(handler)


class PluginContext:
    """Object passed to every plugin's ``register(ctx)`` function.

    A plugin uses the context to:

    * register handlers via :meth:`add_handler` (the manager records
      them so it can remove them on reload);
    * spawn background tasks via :meth:`spawn_task` (the manager
      cancels them on reload);
    * persist state across reloads via the ``state`` dict.
    """

    def __init__(
        self,
        manager: "HotReloadManager",
        application: "Application",
        record: PluginRecord,
    ) -> None:
        self._manager = manager
        self._application = application
        self._record = record

    @property
    def application(self) -> "Application":
        return self._application

    @property
    def state(self) -> Dict[str, Any]:
        return self._record.state

    @property
    def name(self) -> str:
        return self._record.name

    @property
    def version(self) -> int:
        return self._record.version

    def add_handler(self, handler: "BaseHandler", group: int = 0) -> None:
        """Register a PTB handler and record it for later removal."""
        self._application.add_handler(handler, group=group)
        self._record.add_handler_record(handler, group)

    def spawn_task(
        self, coro: Awaitable[Any], *, name: Optional[str] = None
    ) -> asyncio.Task:
        """Schedule a background task tied to this plugin's lifetime."""
        task = asyncio.create_task(coro, name=name or f"plugin:{self.name}")
        self._record.tasks.append(task)
        return task

    def logger(self) -> logging.Logger:
        return logging.getLogger(f"plugin.{self.name}")


class HotReloadManager:
    """Loads, reloads and unloads plugin modules at runtime.

    The manager assumes the calling process is the one running the PTB
    ``Application``.  It is safe to use from multiple async tasks; an
    internal lock serialises load/reload/unload operations per plugin.
    """

    def __init__(
        self,
        application: "Application",
        package: str = "plugins",
    ) -> None:
        self._application = application
        self._package = package
        self._plugins: Dict[str, PluginRecord] = {}
        self._global_lock = asyncio.Lock()
        self._per_plugin_locks: Dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def package(self) -> str:
        return self._package

    def list_plugins(self) -> List[str]:
        return sorted(self._plugins.keys())

    def info(self, name: str) -> Optional[Dict[str, Any]]:
        rec = self._plugins.get(name)
        if rec is None:
            return None
        return {
            "name": rec.name,
            "version": rec.version,
            "loaded_at": rec.loaded_at,
            "handlers": len(rec.handlers),
            "tasks": sum(1 for t in rec.tasks if not t.done()),
            "module": rec.module.__name__,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lock_for(self, name: str) -> asyncio.Lock:
        lock = self._per_plugin_locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            self._per_plugin_locks[name] = lock
        return lock

    def _full_module_name(self, name: str) -> str:
        return f"{self._package}.{name}"

    async def _cancel_tasks(self, record: PluginRecord) -> None:
        if not record.tasks:
            return
        for task in record.tasks:
            if not task.done():
                task.cancel()
        # Give the loop a chance to actually cancel them.
        for task in record.tasks:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:  # noqa: BLE001 — log and continue
                logger.exception(
                    "Plugin %s background task raised during cancel", record.name
                )
        record.tasks.clear()

    def _remove_handlers(self, record: PluginRecord) -> None:
        for group, handlers in record.handler_groups.items():
            for handler in handlers:
                try:
                    self._application.remove_handler(handler, group=group)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Failed to remove handler %r for plugin %s",
                        handler,
                        record.name,
                        exc_info=True,
                    )
        record.handlers.clear()
        record.handler_groups.clear()

    async def _call_lifecycle(
        self,
        module: ModuleType,
        ctx: PluginContext,
        hook: str,
    ) -> None:
        fn: Optional[Callable[..., Any]] = getattr(module, hook, None)
        if fn is None:
            return
        try:
            result = fn(ctx)
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # noqa: BLE001
            logger.exception("Plugin %s %s raised", ctx.name, hook)
            raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _snapshot_app_handlers(self) -> Dict[int, List[Any]]:
        """Return ``{group: [handler, ...]}`` from the live application.

        Used by :meth:`load` / :meth:`reload` to detect handlers that a
        plugin's ``register()`` added via the bare ``app.add_handler``
        API (i.e. without going through ``ctx.add_handler``) so the
        manager can still bookkeep — and later remove — them.
        """
        snap: Dict[int, List[Any]] = {}
        for group, handlers in (self._application.handlers or {}).items():
            snap[group] = list(handlers)
        return snap

    def _diff_app_handlers(
        self,
        before: Dict[int, List[Any]],
        record: PluginRecord,
    ) -> int:
        """Detect handlers added since *before* and attach them to *record*."""
        added = 0
        for group, handlers in (self._application.handlers or {}).items():
            old_set = before.get(group, [])
            old_ids = {id(h) for h in old_set}
            for h in handlers:
                if id(h) not in old_ids:
                    record.add_handler_record(h, group)
                    added += 1
        return added

    def _adopt_existing(self, name: str) -> Optional[PluginRecord]:
        """Build a :class:`PluginRecord` from handlers already in the app.

        Some plugins are loaded by the legacy ``main()`` flow (the
        monolith era) instead of going through ``manager.load()``.  When
        an admin asks to reload one of those, walk the live application
        handlers and pick out the ones that belong to ``plugins.<name>``.

        A callback "belongs" to the plugin if any of:

        * ``cb.__module__`` equals the plugin's full module name; OR
        * ``cb`` is an object identity match (``is``) for one of the
          functions defined in the plugin's module dict; OR
        * ``cb`` is a wrapper produced by a decorator (``check_banned``,
          ``check_maintenance``) that closes over a function whose
          ``__module__`` matches the plugin — found by walking
          ``cb.__closure__``.

        This handles the common pattern in this casino where plugin
        functions are wrapped by decorators living in ``core.foundation``
        but the underlying ``func`` is defined in the plugin module.
        """
        full = self._full_module_name(name)
        module = sys.modules.get(full)
        if module is None:
            return None
        # Build a set of function objects exported by the plugin module
        # (and not just re-exported via ``from core.foundation import *``).
        own_funcs = set()
        for k, v in module.__dict__.items():
            if k.startswith("__"):
                continue
            if callable(v) and getattr(v, "__module__", "") == full:
                own_funcs.add(id(v))
        record = PluginRecord(name=name, module=module)

        def _belongs(cb, _depth: int = 0, _seen: Optional[set] = None) -> bool:
            if cb is None or _depth > 8:
                return False
            cb_mod = getattr(cb, "__module__", "")
            if cb_mod == full:
                return True
            if id(cb) in own_funcs:
                return True
            if _seen is None:
                _seen = set()
            if id(cb) in _seen:
                return False
            _seen.add(id(cb))
            # Decorator pattern: walk closure cells recursively.  Each
            # decorator stacks another wrapper, so the real function may
            # be several layers deep.
            closure = getattr(cb, "__closure__", None) or ()
            for cell in closure:
                try:
                    val = cell.cell_contents
                except ValueError:
                    continue
                if not callable(val):
                    continue
                if _belongs(val, _depth + 1, _seen):
                    return True
            return False

        for group, handlers in (self._application.handlers or {}).items():
            for h in handlers:
                cb = getattr(h, "callback", None)
                if _belongs(cb):
                    record.add_handler_record(h, group)
        return record

    async def load(self, name: str) -> Dict[str, Any]:
        """Load a plugin by short name (e.g. ``"blackjack"``)."""
        async with self._lock_for(name):
            if name in self._plugins:
                return self.info(name)  # type: ignore[return-value]

            full = self._full_module_name(name)
            already_imported = full in sys.modules
            module = importlib.import_module(full)
            # If the module was already imported by the legacy ``_wireup``
            # flow, its ``register()`` has already been called against
            # the application — re-calling it here would double-register
            # every handler.  Adopt the existing handlers instead.
            if already_imported:
                record = self._adopt_existing(name) or PluginRecord(
                    name=name, module=module
                )
                self._plugins[name] = record
                logger.info(
                    "Plugin adopted (legacy-loaded): %s (%d handlers)",
                    name,
                    len(record.handlers),
                )
                return self.info(name)  # type: ignore[return-value]

            record = PluginRecord(name=name, module=module)
            ctx = PluginContext(self, self._application, record)
            register = getattr(module, "register", None)
            if register is None:
                raise RuntimeError(
                    f"Plugin '{name}' is missing a top-level register(ctx) function"
                )
            before = self._snapshot_app_handlers()
            try:
                result = register(ctx)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # Roll back: do not keep half-registered handlers.
                self._remove_handlers(record)
                # Drop the partially-imported module so the next attempt
                # gets a fresh import (matters if the module raised at
                # register time after side-effects at import time).
                sys.modules.pop(full, None)
                raise
            # Detect handlers register() added via app.add_handler so
            # they're tracked alongside ones added via ctx.add_handler.
            self._diff_app_handlers(before, record)
            await self._call_lifecycle(module, ctx, "on_load")
            self._plugins[name] = record
            logger.info(
                "Plugin loaded: %s (v%d, %d handlers)",
                name,
                record.version,
                len(record.handlers),
            )
            return self.info(name)  # type: ignore[return-value]

    async def reload(self, name: str) -> Dict[str, Any]:
        """Atomically swap a plugin for its newest source on disk."""
        async with self._lock_for(name):
            old = self._plugins.get(name)
            if old is None:
                # Plugin was loaded by the legacy ``_wireup`` flow, not
                # via ``manager.load()`` — adopt its handlers first so
                # we can bookkeep + reload it cleanly.
                adopted = self._adopt_existing(name)
                if adopted is not None:
                    self._plugins[name] = adopted
                    old = adopted
                else:
                    # Genuinely unloaded; treat as a regular load.
                    return await self.load(name)

            old_ctx = PluginContext(self, self._application, old)
            # Snapshot handlers BEFORE we strip them so we can roll back
            # on failure.  ``_remove_handlers`` clears the bookkeeping
            # in-place, so without this copy the rollback would have
            # nothing to re-register.
            saved_groups = {
                grp: list(handlers)
                for grp, handlers in old.handler_groups.items()
            }
            await self._call_lifecycle(old.module, old_ctx, "on_unload")
            await self._cancel_tasks(old)
            self._remove_handlers(old)

            try:
                new_module = importlib.reload(old.module)
            except Exception:
                # The old module is still importable (Python keeps it on
                # failure); re-register the OLD handlers so the bot
                # keeps running.
                logger.exception(
                    "importlib.reload failed for plugin %s — keeping old version",
                    name,
                )
                old.handler_groups = saved_groups
                old.handlers = [h for hs in saved_groups.values() for h in hs]
                await self._reregister_old(old)
                raise

            new_record = PluginRecord(
                name=name,
                module=new_module,
                state=old.state,  # carry user state across reload
                version=old.version + 1,
            )
            new_ctx = PluginContext(self, self._application, new_record)
            register = getattr(new_module, "register", None)
            if register is None:
                logger.error(
                    "Reloaded plugin %s is missing register(); reverting", name
                )
                old.handler_groups = saved_groups
                old.handlers = [h for hs in saved_groups.values() for h in hs]
                await self._reregister_old(old)
                raise RuntimeError(
                    f"Reloaded plugin '{name}' is missing register(ctx)"
                )
            before = self._snapshot_app_handlers()
            try:
                result = register(new_ctx)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                self._remove_handlers(new_record)
                logger.exception(
                    "register() failed on reloaded plugin %s — reverting", name
                )
                old.handler_groups = saved_groups
                old.handlers = [h for hs in saved_groups.values() for h in hs]
                await self._reregister_old(old)
                raise
            # Track handlers register() added via app.add_handler.
            self._diff_app_handlers(before, new_record)
            await self._call_lifecycle(new_module, new_ctx, "on_reload")
            self._plugins[name] = new_record
            logger.info(
                "Plugin reloaded: %s (v%d, %d handlers)",
                name,
                new_record.version,
                len(new_record.handlers),
            )
            return self.info(name)  # type: ignore[return-value]

    async def _reregister_old(self, old: PluginRecord) -> None:
        """Best-effort: rebind the previous-version handlers."""
        try:
            for group, handlers in list(old.handler_groups.items()):
                for handler in handlers:
                    self._application.add_handler(handler, group=group)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to re-register old handlers for plugin %s", old.name
            )

    async def unload(self, name: str) -> bool:
        async with self._lock_for(name):
            old = self._plugins.pop(name, None)
            if old is None:
                return False
            ctx = PluginContext(self, self._application, old)
            try:
                await self._call_lifecycle(old.module, ctx, "on_unload")
            except Exception:  # noqa: BLE001
                logger.warning("on_unload raised for %s", name, exc_info=True)
            await self._cancel_tasks(old)
            self._remove_handlers(old)
            sys.modules.pop(self._full_module_name(name), None)
            logger.info("Plugin unloaded: %s", name)
            return True

    async def reload_all(self) -> Dict[str, str]:
        """Reload every currently-loaded plugin; return per-plugin status."""
        async with self._global_lock:
            results: Dict[str, str] = {}
            for name in list(self._plugins.keys()):
                try:
                    await self.reload(name)
                    results[name] = "ok"
                except Exception as e:  # noqa: BLE001
                    results[name] = f"error: {e}"
                    logger.error(
                        "reload_all: %s failed\n%s",
                        name,
                        traceback.format_exc(),
                    )
            return results
