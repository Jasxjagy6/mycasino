"""Shared pytest fixtures for runtime tests.

Tests do NOT import bot.py — they only exercise the runtime layer
against a fake PTB ``Application`` so they run in milliseconds without
network access or a real Telegram bot token.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Callable, List, Tuple

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeHandler:
    def __init__(self, name: str) -> None:
        self.name = name
        self.callback: Callable[..., Any] | None = None


class FakeApplication:
    """Minimal stand-in for telegram.ext.Application used in tests."""

    def __init__(self) -> None:
        self.handlers: List[Tuple[int, Any]] = []
        self.bot_data: dict = {}
        self.post_init = None

    def add_handler(self, handler: Any, group: int = 0) -> None:
        self.handlers.append((group, handler))

    def remove_handler(self, handler: Any, group: int = 0) -> None:
        try:
            self.handlers.remove((group, handler))
        except ValueError:
            pass

    def handler_count(self) -> int:
        return len(self.handlers)

    def handler_names(self) -> List[str]:
        return [getattr(h, "name", repr(h)) for _g, h in self.handlers]


@pytest.fixture
def fake_app() -> FakeApplication:
    return FakeApplication()


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
