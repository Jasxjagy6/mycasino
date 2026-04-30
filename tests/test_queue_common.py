"""Tests for runtime.queue_common."""

from __future__ import annotations

import os

import pytest

from runtime.queue_common import (
    DEFAULT_GROUP,
    DEFAULT_MAXLEN,
    DEFAULT_STREAM,
    QueueConfig,
)


def test_defaults():
    cfg = QueueConfig()
    assert cfg.stream == DEFAULT_STREAM
    assert cfg.group == DEFAULT_GROUP
    assert cfg.maxlen == DEFAULT_MAXLEN


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("MYCASINO_REDIS_URL", "redis://example.com:6379/3")
    monkeypatch.setenv("MYCASINO_QUEUE_STREAM", "alt-stream")
    monkeypatch.setenv("MYCASINO_QUEUE_MAXLEN", "12345")
    monkeypatch.setenv("MYCASINO_RECEIVER_PORT", "9999")
    monkeypatch.setenv("MYCASINO_RECEIVER_SECRET", "shh")
    monkeypatch.setenv("MYCASINO_QUEUE_AUTOCLAIM", "0")

    cfg = QueueConfig.from_env()
    assert cfg.redis_url == "redis://example.com:6379/3"
    assert cfg.stream == "alt-stream"
    assert cfg.maxlen == 12345
    assert cfg.port == 9999
    assert cfg.secret == "shh"
    assert cfg.enable_autoclaim is False


def test_from_env_consumer_default(monkeypatch):
    monkeypatch.delenv("MYCASINO_QUEUE_CONSUMER", raising=False)
    cfg = QueueConfig.from_env()
    assert cfg.consumer.startswith("worker-")
    assert str(os.getpid()) in cfg.consumer
