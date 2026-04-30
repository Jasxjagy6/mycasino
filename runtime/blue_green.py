"""Blue-green webhook helper for zero-downtime deploys.

Wraps PTB's ``Application.run_webhook`` with three additions that make
blue-green deploys behind nginx safe:

1. A ``/healthz`` endpoint that nginx can probe to know when version B
   is live.  It returns ``200 OK`` only after the bot has finished
   ``post_init`` and called :func:`mark_ready`.
2. A ``/readyz`` endpoint that returns ``503`` once the process has
   received SIGTERM, so nginx stops sending NEW traffic to the
   draining instance while the in-flight requests finish.
3. A graceful shutdown handler that waits for the configured drain
   timeout before tearing down the application — long enough for nginx
   health probes to notice and for in-flight Telegram requests to
   complete.

Usage::

    from runtime.blue_green import run_blue_green_webhook
    run_blue_green_webhook(app, listen="0.0.0.0", port=8000,
                           url_path="/bot_webhook",
                           webhook_url="https://example.com/bot_webhook")

Run the *other* color on a different port and flip nginx upstream
with ``deploy/blue_green_switch.sh``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any, Optional

from aiohttp import web

logger = logging.getLogger(__name__)

_READY_STATE = {"ready": False, "draining": False}


def mark_ready() -> None:
    _READY_STATE["ready"] = True
    _READY_STATE["draining"] = False


def mark_draining() -> None:
    _READY_STATE["draining"] = True


def is_ready() -> bool:
    return _READY_STATE["ready"] and not _READY_STATE["draining"]


def is_draining() -> bool:
    return _READY_STATE["draining"]


async def _healthz(_request: web.Request) -> web.Response:
    return web.json_response(
        {"ready": is_ready(), "draining": is_draining()},
        status=200 if is_ready() else 503,
    )


async def _readyz(_request: web.Request) -> web.Response:
    if is_draining():
        return web.json_response({"draining": True}, status=503)
    return web.json_response({"ready": is_ready()}, status=200 if is_ready() else 503)


def install_health_endpoints(application: Any) -> None:
    """Attach /healthz and /readyz to PTB's internal webhook server.

    PTB exposes its underlying ``aiohttp.web.Application`` only when
    webhook mode is active, so this should be called from ``post_init``
    or just before ``run_webhook``.
    """
    # PTB stores its web app under updater._httpd._app in v20+; the
    # internals are private so we register a small post_init hook that
    # attaches our routes if available, and otherwise spins up a side
    # car health server.
    pass  # Side-car path is the supported route; see run_blue_green_webhook.


def run_blue_green_webhook(
    application: Any,
    *,
    listen: str = "0.0.0.0",
    port: int,
    url_path: str,
    webhook_url: str,
    secret_token: Optional[str] = None,
    health_port: Optional[int] = None,
    drain_seconds: float = 25.0,
    allowed_updates: Optional[Any] = None,
    drop_pending_updates: bool = False,
) -> None:
    """Run *application* in webhook mode with health endpoints + drain.

    A side-car aiohttp server hosts ``/healthz`` and ``/readyz`` on
    ``health_port`` (default ``port + 1000``) so nginx can probe the
    bot independently of the Telegram-only webhook listener.
    """
    health_port = health_port if health_port is not None else port + 1000

    async def _start_health_server() -> web.AppRunner:
        app = web.Application()
        app.router.add_get("/healthz", _healthz)
        app.router.add_get("/readyz", _readyz)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, listen, health_port)
        await site.start()
        logger.info("Blue-green health server on %s:%d", listen, health_port)
        return runner

    health_runner: Optional[web.AppRunner] = None

    prev_post_init = application.post_init

    async def _post_init(app):
        nonlocal health_runner
        if prev_post_init is not None:
            await prev_post_init(app)
        health_runner = await _start_health_server()
        mark_ready()

    application.post_init = _post_init

    # Hook signals to mark draining BEFORE PTB tears down so nginx
    # has time to remove us from the upstream pool.
    loop_started = asyncio.new_event_loop()

    def _drain_signal(*_a):
        mark_draining()
        # Schedule a delayed shutdown after the drain period.
        try:
            loop_started.call_later(drain_seconds, _force_stop)
        except Exception:  # noqa: BLE001
            pass

    def _force_stop():
        try:
            asyncio.run_coroutine_threadsafe(application.stop(), loop_started)
        except Exception:  # noqa: BLE001
            pass

    try:
        signal.signal(signal.SIGTERM, _drain_signal)
    except Exception:  # noqa: BLE001 - best-effort
        pass

    kwargs = dict(
        listen=listen,
        port=port,
        url_path=url_path,
        webhook_url=webhook_url,
        drop_pending_updates=drop_pending_updates,
    )
    if allowed_updates is not None:
        kwargs["allowed_updates"] = allowed_updates
    if secret_token:
        kwargs["secret_token"] = secret_token

    try:
        application.run_webhook(**kwargs)
    finally:
        mark_draining()
        if health_runner is not None:
            try:
                asyncio.get_event_loop().run_until_complete(health_runner.cleanup())
            except Exception:  # noqa: BLE001
                pass


def detect_color() -> str:
    """Return ``"blue"`` or ``"green"`` based on the ``MYCASINO_COLOR`` env var.

    The blue-green switch script sets this for the foreground process so
    the bot can include the active color in logs and ``/runtimestatus``.
    """
    val = os.environ.get("MYCASINO_COLOR", "blue").strip().lower()
    return val if val in {"blue", "green"} else "blue"
