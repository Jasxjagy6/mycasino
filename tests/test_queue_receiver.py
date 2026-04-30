"""Tests for runtime.queue_receiver — runs against fakeredis."""

from __future__ import annotations

import json

import pytest

aiohttp = pytest.importorskip("aiohttp")
fakeredis = pytest.importorskip("fakeredis")

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from runtime.queue_common import QueueConfig
from runtime import queue_receiver


@pytest.fixture
def fake_redis():
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield server


@pytest.fixture
def cfg() -> QueueConfig:
    return QueueConfig(
        redis_url="redis://localhost/0",
        stream="test:updates",
        maxlen=100,
        host="127.0.0.1",
        port=0,
        path="/bot_webhook",
        secret="topsecret",
    )


@pytest.fixture
async def client(cfg, fake_redis, monkeypatch):
    async def _build():
        app = web.Application(client_max_size=2 * 1024 * 1024)
        app["queue_config"] = cfg
        app["redis"] = fake_redis
        app.router.add_post(cfg.path, queue_receiver._handle_update)
        app.router.add_get("/healthz", queue_receiver._healthz)
        return app

    server = TestServer(await _build())
    async with TestClient(server) as c:
        yield c


@pytest.mark.asyncio
async def test_secret_token_required(client, cfg):
    r = await client.post(cfg.path, data=json.dumps({"update_id": 1}))
    assert r.status == 401


@pytest.mark.asyncio
async def test_valid_post_xadds(client, cfg, fake_redis):
    headers = {"X-Telegram-Bot-Api-Secret-Token": cfg.secret}
    r = await client.post(
        cfg.path, data=json.dumps({"update_id": 42}), headers=headers
    )
    assert r.status == 200
    length = await fake_redis.xlen(cfg.stream)
    assert length == 1


@pytest.mark.asyncio
async def test_invalid_json_rejected(client, cfg):
    headers = {"X-Telegram-Bot-Api-Secret-Token": cfg.secret}
    r = await client.post(cfg.path, data="not json", headers=headers)
    assert r.status == 400


@pytest.mark.asyncio
async def test_healthz_pings_redis(client, fake_redis):
    r = await client.get("/healthz")
    assert r.status == 200
    body = await r.json()
    assert body["redis"] is True
