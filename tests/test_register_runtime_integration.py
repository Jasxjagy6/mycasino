"""End-to-end smoke test: register_runtime against a real PTB Application.

Builds an actual ``telegram.ext.Application`` (no token validation
happens at build time so this works offline) and wires the runtime,
verifying that the runtime's admin commands are reachable in the
dispatcher.

Plugin loading is also exercised against a synthetic in-tmp plugin
(plugins/ in this repo are auto-split from bot.py and require the
full casino foundation to load -- not appropriate for a unit test).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ptb = pytest.importorskip("telegram.ext")
from telegram.ext import ApplicationBuilder, CommandHandler

from runtime import register_runtime


def _command_names(application) -> list[str]:
    out: list[str] = []
    for _group, hs in application.handlers.items():
        for h in hs:
            if isinstance(h, CommandHandler):
                for cmd in h.commands:
                    out.append(cmd)
    return out


@pytest.mark.asyncio
async def test_register_runtime_wires_admin_handlers(monkeypatch):
    monkeypatch.setenv("BOT_OWNER_IDS", "111222333")
    app = ApplicationBuilder().token("0:fake").build()
    manager = register_runtime(app)
    cmds = _command_names(app)
    # Runtime admin commands must be present.
    for needle in ("reload", "reloadall", "loadplugin", "unloadplugin",
                   "listplugins", "runtimestatus"):
        assert needle in cmds, f"missing admin command: {needle}"
    assert manager is not None


@pytest.mark.asyncio
async def test_register_runtime_loads_synthetic_plugin(tmp_path, monkeypatch):
    """Drop a tiny synthetic plugin into a temp dir, point the loader
    at it, and verify hot-reload load() registers its handler."""
    plugins_root = tmp_path / "_test_plugins"
    plugins_root.mkdir()
    (plugins_root / "__init__.py").write_text("")
    (plugins_root / "smoketest.py").write_text(
        "from telegram.ext import CommandHandler\n"
        "async def _smoketest_handler(update, context):\n"
        "    pass\n"
        "def register(ctx):\n"
        "    ctx.add_handler(CommandHandler(['smoketest'], _smoketest_handler))\n"
    )
    sys.path.insert(0, str(tmp_path))
    monkeypatch.setenv("MYCASINO_PLUGINS_PACKAGE", "_test_plugins")
    try:
        app = ApplicationBuilder().token("0:fake").build()
        manager = register_runtime(app)
        info = await manager.hot_reload.load("smoketest")
        assert info["handlers"] == 1
        assert "smoketest" in _command_names(app)
    finally:
        sys.path.remove(str(tmp_path))
