"""Tests for runtime.plugin_loader."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from runtime.plugin_loader import (
    PluginManager,
    discovered_names_from_dir,
    install,
    is_installed,
)


@pytest.fixture
def tmp_pkg(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg_under_test"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "alpha.py").write_text(
        "from tests.conftest import FakeHandler\n"
        "def register(ctx):\n"
        "    ctx.add_handler(FakeHandler('a'))\n"
    )
    (pkg / "bravo.py").write_text(
        "from tests.conftest import FakeHandler\n"
        "def register(ctx):\n"
        "    ctx.add_handler(FakeHandler('b'))\n"
    )
    (pkg / "_skip.py").write_text("def register(ctx): pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield pkg
    for mod in list(sys.modules):
        if mod.startswith("pkg_under_test"):
            del sys.modules[mod]


def test_discovered_names_from_dir_skips_underscore(tmp_pkg):
    names = list(discovered_names_from_dir(str(tmp_pkg)))
    assert "alpha" in names
    assert "bravo" in names
    assert "_skip" not in names


@pytest.mark.asyncio
async def test_load_all_loads_every_plugin(tmp_pkg, fake_app):
    mgr = PluginManager(fake_app, package="pkg_under_test")
    loaded = await mgr.load_all()
    assert set(loaded) == {"alpha", "bravo"}
    assert fake_app.handler_count() == 2


@pytest.mark.asyncio
async def test_allowlist_limits_discovery(tmp_pkg, fake_app, monkeypatch):
    monkeypatch.setenv("MYCASINO_PLUGIN_ALLOWLIST", "alpha")
    mgr = PluginManager(fake_app, package="pkg_under_test")
    loaded = await mgr.load_all()
    assert loaded == ["alpha"]


@pytest.mark.asyncio
async def test_denylist_excludes_named(tmp_pkg, fake_app, monkeypatch):
    monkeypatch.setenv("MYCASINO_PLUGIN_DENYLIST", "alpha")
    mgr = PluginManager(fake_app, package="pkg_under_test")
    loaded = await mgr.load_all()
    assert loaded == ["bravo"]


def test_install_singleton(fake_app):
    # Reset the module-level singleton between tests.
    import runtime.plugin_loader as pl
    pl._singleton = None
    assert is_installed() is False
    mgr = PluginManager(fake_app, package="pkg_under_test")
    install(mgr)
    assert is_installed() is True
    pl._singleton = None
