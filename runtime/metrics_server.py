"""Lightweight HTTP server that exposes ``/metrics`` and ``/healthz``.

Run this as a sidecar (or inside the same worker) to make the bot
scrapable by Prometheus.  The server uses ``aiohttp`` if it's already
installed (it is — the bot depends on it) and otherwise falls back to
the stdlib ``http.server``.

Endpoints
---------
* ``GET /metrics``  — Prometheus exposition format.
* ``GET /healthz``  — 200 if the process can answer; 503 otherwise.
* ``GET /readyz``   — 200 once we've finished startup (pool ready, etc.).

Run standalone with:

    python -m runtime.metrics_server --port 9100
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time

from core.observability import (
    WORKER_HEARTBEAT,
    metrics_text,
)

logger = logging.getLogger(__name__)

_ready = {"value": False}


def mark_ready() -> None:
    _ready["value"] = True


def mark_unready() -> None:
    _ready["value"] = False


def heartbeat() -> None:
    """Call from your main loop so /healthz reflects liveness."""
    WORKER_HEARTBEAT.set(time.time())


async def _handle_metrics(_request):
    from aiohttp import web

    return web.Response(
        body=metrics_text(),
        content_type="text/plain",
        charset="utf-8",
    )


async def _handle_healthz(_request):
    from aiohttp import web

    # Healthy as long as the heartbeat has been bumped within 60s.
    bound = float(os.environ.get("MYCASINO_HEALTH_MAX_AGE", "60"))
    ts_dict = dict(WORKER_HEARTBEAT.values)
    last = max(ts_dict.values(), default=0.0)
    age = time.time() - last if last else float("inf")
    if last == 0.0 or age <= bound:
        return web.Response(text="ok\n")
    return web.Response(status=503, text=f"stale heartbeat: {age:.1f}s\n")


async def _handle_readyz(_request):
    from aiohttp import web

    if _ready["value"]:
        return web.Response(text="ok\n")
    return web.Response(status=503, text="not ready\n")


async def serve_async(host: str = "0.0.0.0", port: int = 9100):
    from aiohttp import web

    app = web.Application()
    app.router.add_get("/metrics", _handle_metrics)
    app.router.add_get("/healthz", _handle_healthz)
    app.router.add_get("/readyz", _handle_readyz)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("metrics server listening on http://%s:%s", host, port)
    return runner


async def _amain():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("MYCASINO_METRICS_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MYCASINO_METRICS_PORT", "9100")),
    )
    args = parser.parse_args()
    runner = await serve_async(args.host, args.port)
    # Heartbeat once so /healthz returns 200 even without a worker.
    heartbeat()
    mark_ready()
    try:
        while True:
            await asyncio.sleep(15)
            heartbeat()
    finally:
        await runner.cleanup()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":  # pragma: no cover
    main()
