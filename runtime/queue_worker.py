"""Redis-backed worker that drains the receiver's stream.

The worker process imports ``bot.py`` (or a configurable factory) and
builds a real PTB ``Application``.  Instead of running webhook or
polling itself, it pulls updates from a Redis Stream produced by the
:mod:`runtime.queue_receiver` and feeds them into
``application.update_queue`` exactly the way the built-in updater
would.

Design points
-------------

* Uses ``XREADGROUP`` so multiple workers can run side-by-side and
  share the load — Redis distributes entries across consumers.
* Uses ``XAUTOCLAIM`` to recover entries that a crashed worker left
  unacknowledged.  No update is lost across restarts.
* On shutdown the worker stops accepting new entries, drains anything
  already in flight, then ``XACK``s and exits cleanly.
* When the worker can't reach Redis it sleeps with exponential
  backoff and keeps retrying — Telegram messages pile up in the
  receiver's stream meanwhile.

Run::

    python -m runtime.queue_worker
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import signal
import sys
import time
from typing import Any, Callable, List, Optional, Tuple

from telegram import Update

from runtime.queue_common import (
    QueueConfig,
    ensure_consumer_group,
    get_redis_client,
)

logger = logging.getLogger(__name__)


class WorkerStopped(Exception):
    """Raised internally to short-circuit the read loop on shutdown."""


def _resolve_application_factory() -> Callable[[], Any]:
    """Resolve a callable that returns a built PTB ``Application``.

    The factory is selected via the ``MYCASINO_APP_FACTORY`` env var,
    in ``module:callable`` form.  Default is
    ``bot:_build_worker_application`` — a small helper added to
    ``bot.py`` by the integration patch.  Fall back to constructing a
    bare ``Application`` from ``BOT_TOKEN`` if the helper is missing.
    """
    spec = os.environ.get("MYCASINO_APP_FACTORY", "bot:_build_worker_application")
    if ":" not in spec:
        raise RuntimeError(
            f"MYCASINO_APP_FACTORY must be 'module:callable', got {spec!r}"
        )
    module_name, attr = spec.split(":", 1)
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError:
        raise RuntimeError(
            f"Worker cannot import application factory module: {module_name}"
        )
    fn = getattr(mod, attr, None)
    if fn is None:
        # Fallback: build a minimal Application from BOT_TOKEN.
        logger.warning(
            "Application factory %s missing; building minimal Application",
            spec,
        )
        return _build_minimal_application
    return fn


def _build_minimal_application() -> Any:
    from telegram.ext import ApplicationBuilder

    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN env var required when using the minimal application factory"
        )
    return ApplicationBuilder().token(token).build()


class QueueWorker:
    """Drives a PTB Application from a Redis Stream."""

    def __init__(self, application: Any, cfg: Optional[QueueConfig] = None) -> None:
        self.application = application
        self.cfg = cfg or QueueConfig.from_env()
        self.redis = get_redis_client(self.cfg.redis_url)
        self._stop = asyncio.Event()
        self._inflight: List[str] = []

    async def _ack(self, ids: List[str]) -> None:
        if not ids:
            return
        try:
            await self.redis.xack(self.cfg.stream, self.cfg.group, *ids)
        except Exception:  # noqa: BLE001
            logger.exception("XACK failed for %d ids", len(ids))

    async def _dispatch(self, raw_payload: str) -> None:
        try:
            data = json.loads(raw_payload)
        except Exception:
            logger.warning("Skipping malformed payload (not JSON)")
            return
        update = Update.de_json(data, self.application.bot)
        if update is None:
            logger.warning("Skipping payload that did not parse as Update")
            return
        try:
            await self.application.update_queue.put(update)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to enqueue update onto Application")
            raise

    async def _process_entries(
        self, entries: List[Tuple[str, dict]]
    ) -> None:
        ids: List[str] = []
        for entry_id, fields in entries:
            self._inflight.append(entry_id)
            payload = fields.get("payload") if isinstance(fields, dict) else None
            if payload is None and isinstance(fields, list):
                # In case decode_responses=False made fields a list of bytes.
                try:
                    payload = dict(zip(fields[::2], fields[1::2])).get("payload")
                except Exception:
                    payload = None
            if payload is None:
                ids.append(entry_id)
                continue
            try:
                await self._dispatch(payload)
            except Exception:  # noqa: BLE001
                logger.exception("Dispatch failed for %s; will retry later", entry_id)
                # Don't ack — XAUTOCLAIM will pick it up later.
                continue
            ids.append(entry_id)
        if ids:
            await self._ack(ids)
            for i in ids:
                try:
                    self._inflight.remove(i)
                except ValueError:
                    pass

    async def _autoclaim_loop(self) -> None:
        """Reclaim entries from dead consumers in the background."""
        if not self.cfg.enable_autoclaim:
            return
        while not self._stop.is_set():
            try:
                # XAUTOCLAIM returns (next_cursor, entries, [deleted ids])
                res = await self.redis.xautoclaim(
                    name=self.cfg.stream,
                    groupname=self.cfg.group,
                    consumername=self.cfg.consumer,
                    min_idle_time=self.cfg.claim_idle_ms,
                    start_id="0-0",
                    count=self.cfg.batch_size,
                )
                entries: List[Tuple[str, dict]] = []
                if isinstance(res, (list, tuple)) and len(res) >= 2:
                    entries = res[1] or []
                if entries:
                    logger.info(
                        "Reclaimed %d entries from idle consumers", len(entries)
                    )
                    await self._process_entries(entries)
            except Exception:  # noqa: BLE001
                logger.warning("autoclaim cycle failed", exc_info=True)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

    async def _read_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                resp = await self.redis.xreadgroup(
                    groupname=self.cfg.group,
                    consumername=self.cfg.consumer,
                    streams={self.cfg.stream: ">"},
                    count=self.cfg.batch_size,
                    block=self.cfg.block_ms,
                )
                backoff = 1.0
            except Exception:  # noqa: BLE001
                logger.warning(
                    "xreadgroup failed (sleep %.1fs)", backoff, exc_info=True
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 30.0)
                continue
            if not resp:
                continue
            for _stream_name, entries in resp:
                await self._process_entries(entries)

    async def run(self) -> None:
        await ensure_consumer_group(self.redis, self.cfg.stream, self.cfg.group)
        await self.application.initialize()
        await self.application.start()
        autoclaim = asyncio.create_task(self._autoclaim_loop(), name="qworker-autoclaim")
        try:
            logger.info(
                "Worker %s online: stream=%s group=%s",
                self.cfg.consumer,
                self.cfg.stream,
                self.cfg.group,
            )
            await self._read_loop()
        finally:
            autoclaim.cancel()
            try:
                await autoclaim
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            try:
                await self.application.stop()
                await self.application.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception("Application shutdown raised")
            try:
                await self.redis.aclose()
            except Exception:  # noqa: BLE001
                pass

    def request_stop(self) -> None:
        if not self._stop.is_set():
            logger.info("Worker stop requested")
            self._stop.set()


async def _async_main() -> None:
    cfg = QueueConfig.from_env()
    factory = _resolve_application_factory()
    application = factory()
    if asyncio.iscoroutine(application):
        application = await application
    worker = QueueWorker(application, cfg)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except NotImplementedError:
            pass
    await worker.run()


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("MYCASINO_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":  # pragma: no cover - entrypoint
    main()
