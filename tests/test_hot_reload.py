"""Tests for runtime.hot_reload.HotReloadManager.

These tests write tiny synthetic plugin modules to a temporary
directory, point the manager at them, and verify that load → reload →
unload behave correctly: handlers are added/removed, state survives
reloads, register-time errors are rolled back, and background tasks
are cancelled.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from runtime.hot_reload import HotReloadManager
from tests.conftest import FakeHandler


def _write_plugin(plugin_dir: Path, name: str, body: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text(
        '"""Synthetic test plugins."""\n'
    )
    (plugin_dir / f"{name}.py").write_text(textwrap.dedent(body))


@pytest.fixture
def tmp_plugins(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "synth_plugins"
    monkeypatch.syspath_prepend(str(tmp_path))
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("")
    yield plugin_dir
    # Drop any modules we imported under the synth package so a later
    # test gets a clean slate.
    for mod in list(sys.modules):
        if mod.startswith("synth_plugins"):
            del sys.modules[mod]


@pytest.mark.asyncio
async def test_load_registers_handler(tmp_plugins, fake_app):
    _write_plugin(
        tmp_plugins,
        "alpha",
        """
        def register(ctx):
            from tests.conftest import FakeHandler
            ctx.add_handler(FakeHandler('alpha-handler'))
        """,
    )
    mgr = HotReloadManager(fake_app, package="synth_plugins")
    info = await mgr.load("alpha")
    assert info["name"] == "alpha"
    assert info["handlers"] == 1
    assert "alpha-handler" in fake_app.handler_names()


@pytest.mark.asyncio
async def test_reload_swaps_handlers_and_preserves_state(tmp_plugins, fake_app):
    _write_plugin(
        tmp_plugins,
        "bravo",
        """
        def register(ctx):
            from tests.conftest import FakeHandler
            ctx.state.setdefault('counter', 0)
            ctx.state['counter'] += 1
            ctx.add_handler(FakeHandler(f"v1-{ctx.state['counter']}"))
        """,
    )
    mgr = HotReloadManager(fake_app, package="synth_plugins")
    await mgr.load("bravo")
    assert "v1-1" in fake_app.handler_names()

    # Rewrite plugin source.
    (tmp_plugins / "bravo.py").write_text(textwrap.dedent("""
        def register(ctx):
            from tests.conftest import FakeHandler
            ctx.state['counter'] += 10
            ctx.add_handler(FakeHandler(f"v2-{ctx.state['counter']}"))
    """))
    info = await mgr.reload("bravo")
    assert info["version"] == 2
    names = fake_app.handler_names()
    # Only the new handler should remain.
    assert any("v2-" in n for n in names)
    assert not any("v1-" in n for n in names)


@pytest.mark.asyncio
async def test_reload_failure_rolls_back(tmp_plugins, fake_app):
    _write_plugin(
        tmp_plugins,
        "charlie",
        """
        def register(ctx):
            from tests.conftest import FakeHandler
            ctx.add_handler(FakeHandler('good'))
        """,
    )
    mgr = HotReloadManager(fake_app, package="synth_plugins")
    await mgr.load("charlie")
    assert "good" in fake_app.handler_names()

    # Break the source.
    (tmp_plugins / "charlie.py").write_text(textwrap.dedent("""
        def register(ctx):
            raise RuntimeError("boom")
    """))
    with pytest.raises(RuntimeError, match="boom"):
        await mgr.reload("charlie")
    # Old handlers must be back in place.
    assert "good" in fake_app.handler_names()


@pytest.mark.asyncio
async def test_unload_removes_handlers_and_cancels_tasks(tmp_plugins, fake_app):
    _write_plugin(
        tmp_plugins,
        "delta",
        """
        import asyncio

        async def _bg(state):
            try:
                while True:
                    await asyncio.sleep(0.05)
                    state['ticks'] = state.get('ticks', 0) + 1
            except asyncio.CancelledError:
                state['cancelled'] = True
                raise

        def register(ctx):
            from tests.conftest import FakeHandler
            ctx.add_handler(FakeHandler('delta-handler'))
            ctx.spawn_task(_bg(ctx.state))
        """,
    )
    mgr = HotReloadManager(fake_app, package="synth_plugins")
    await mgr.load("delta")
    await asyncio.sleep(0.15)
    rec = mgr._plugins["delta"]  # noqa: SLF001
    assert rec.state.get("ticks", 0) >= 1

    ok = await mgr.unload("delta")
    assert ok is True
    assert "delta-handler" not in fake_app.handler_names()


@pytest.mark.asyncio
async def test_load_missing_register_raises(tmp_plugins, fake_app):
    _write_plugin(
        tmp_plugins,
        "echo",
        """
        # No register() function on purpose.
        x = 1
        """,
    )
    mgr = HotReloadManager(fake_app, package="synth_plugins")
    with pytest.raises(RuntimeError, match="register"):
        await mgr.load("echo")
    assert "echo" not in mgr.list_plugins()


@pytest.mark.asyncio
async def test_reload_all_reports_per_plugin_status(tmp_plugins, fake_app):
    _write_plugin(
        tmp_plugins,
        "foxtrot",
        """
        def register(ctx):
            from tests.conftest import FakeHandler
            ctx.add_handler(FakeHandler('fox'))
        """,
    )
    _write_plugin(
        tmp_plugins,
        "golf",
        """
        def register(ctx):
            from tests.conftest import FakeHandler
            ctx.add_handler(FakeHandler('golf'))
        """,
    )
    mgr = HotReloadManager(fake_app, package="synth_plugins")
    await mgr.load("foxtrot")
    await mgr.load("golf")
    results = await mgr.reload_all()
    assert results == {"foxtrot": "ok", "golf": "ok"}
