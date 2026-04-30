"""End-to-end smoke test: register_runtime against a real PTB Application.

Builds an actual ``telegram.ext.Application`` (no token validation
happens at build time so this works offline), wires the runtime,
loads the example_coinflip plugin, and verifies the admin commands
plus the plugin's command are all reachable in the dispatcher.
"""

from __future__ import annotations

import os

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
async def test_register_runtime_loads_example_plugin():
    app = ApplicationBuilder().token("0:fake").build()
    manager = register_runtime(app)
    # Manually load the shipped coinflip plugin.
    info = await manager.hot_reload.load("example_coinflip")
    assert info["handlers"] == 1
    cmds = _command_names(app)
    assert "coinflip" in cmds and "cf" in cmds
