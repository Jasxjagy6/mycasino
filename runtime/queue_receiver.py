"""Tiny webhook receiver that pushes Telegram updates into Redis.

Run as a long-lived service.  It does the absolute minimum:

1. Validate the inbound HTTP request matches the configured webhook
   secret.
2. Append the raw JSON body to a Redis Stream (XADD).
3. Reply ``200 OK`` immediately so Telegram is happy.

Because the receiver never imports the casino logic, it can run for
weeks without ever needing to be redeployed.  Workers can crash, be
upgraded, or be horizontally scaled, and Telegram never sees a hiccup
— updates simply pile up in the stream.

Environment variables
---------------------

``MYCASINO_REDIS_URL``       — e.g. ``redis://localhost:6379/0``
``MYCASINO_QUEUE_STREAM``    — stream name (default
                               ``mycasino:updates``)
``MYCASINO_QUEUE_MAXLEN``    — approximate cap on stream length
                               (default 100_000)
``MYCASINO_RECEIVER_HOST``   — bind host (default ``0.0.0.0``)
``MYCASINO_RECEIVER_PORT``   — bind port (default ``8200``)
``MYCASINO_RECEIVER_PATH``   — webhook URL path (default
                               ``/bot_webhook``)
``MYCASINO_RECEIVER_SECRET`` — optional Telegram secret token; when set
                               we require the
                               ``X-Telegram-Bot-Api-Secret-Token``
                               header to match.

Run::

    python -m runtime.queue_receiver
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from typing import Optional

from aiohttp import web

from runtime.queue_common import (
    DEFAULT_MAXLEN,
    DEFAULT_STREAM,
    QueueConfig,
    get_redis_client,
)

logger = logging.getLogger(__name__)


async def _handle_update(request: web.Request) -> web.Response:
    cfg: QueueConfig = request.app["queue_config"]
    redis = request.app["redis"]

    if cfg.secret:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != cfg.secret:
            return web.Response(status=401, text="invalid secret")

    try:
        body = await request.read()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read webhook body")
        return web.Response(status=400, text="bad body")

    if not body:
        return web.Response(status=400, text="empty body")

    # Defensive: parse + reserialize so corrupted payloads never enter
    # the stream.
    try:
        payload = json.loads(body)
    except Exception:
        logger.warning("Webhook payload is not valid JSON; dropping")
        return web.Response(status=400, text="not json")

    serialized = json.dumps(payload, separators=(",", ":"))
    try:
        await redis.xadd(
            cfg.stream,
            {"payload": serialized},
            maxlen=cfg.maxlen,
            approximate=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("XADD failed")
        return web.Response(status=503, text="queue unavailable")

    return web.Response(status=200, text="ok")


async def _healthz(request: web.Request) -> web.Response:
    redis = request.app["redis"]
    try:
        pong = await redis.ping()
    except Exception:  # noqa: BLE001
        return web.json_response({"ok": False, "redis": False}, status=503)
    return web.json_response({"ok": True, "redis": bool(pong)})


async def build_app(cfg: Optional[QueueConfig] = None) -> web.Application:
    cfg = cfg or QueueConfig.from_env()
    app = web.Application(client_max_size=2 * 1024 * 1024)
    app["queue_config"] = cfg
    app["redis"] = get_redis_client(cfg.redis_url)
    app.router.add_post(cfg.path, _handle_update)
    app.router.add_get("/healthz", _healthz)
    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("MYCASINO_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = QueueConfig.from_env()
    logger.info(
        "Starting receiver on %s:%s%s -> stream=%s (maxlen=%d)",
        cfg.host,
        cfg.port,
        cfg.path,
        cfg.stream,
        cfg.maxlen,
    )
    app = asyncio.run(_run(cfg))


async def _run(cfg: QueueConfig) -> None:
    app = await build_app(cfg)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.host, cfg.port)
    await site.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    try:
        await stop.wait()
    finally:
        await runner.cleanup()
        try:
            await app["redis"].aclose()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":  # pragma: no cover - entrypoint
    main()


# Constants re-exported for tests / external callers.
__all__ = [
    "build_app",
    "main",
    "DEFAULT_STREAM",
    "DEFAULT_MAXLEN",
]
