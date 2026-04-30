"""Shared helpers for the Redis-backed receiver/worker pair."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_STREAM = "mycasino:updates"
DEFAULT_MAXLEN = 100_000
DEFAULT_GROUP = "mycasino-workers"
DEFAULT_PATH = "/bot_webhook"


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class QueueConfig:
    """Configuration shared by the receiver and the worker."""

    redis_url: str = "redis://localhost:6379/0"
    stream: str = DEFAULT_STREAM
    group: str = DEFAULT_GROUP
    consumer: str = "worker-1"
    maxlen: int = DEFAULT_MAXLEN
    host: str = "0.0.0.0"
    port: int = 8200
    path: str = DEFAULT_PATH
    secret: Optional[str] = None
    block_ms: int = 5_000
    batch_size: int = 32
    claim_idle_ms: int = 60_000
    enable_autoclaim: bool = True

    @classmethod
    def from_env(cls) -> "QueueConfig":
        cfg = cls(
            redis_url=os.environ.get(
                "MYCASINO_REDIS_URL", cls.redis_url
            ),
            stream=os.environ.get("MYCASINO_QUEUE_STREAM", DEFAULT_STREAM),
            group=os.environ.get("MYCASINO_QUEUE_GROUP", DEFAULT_GROUP),
            consumer=os.environ.get(
                "MYCASINO_QUEUE_CONSUMER",
                f"worker-{os.getpid()}",
            ),
            maxlen=int(
                os.environ.get("MYCASINO_QUEUE_MAXLEN", DEFAULT_MAXLEN)
            ),
            host=os.environ.get("MYCASINO_RECEIVER_HOST", "0.0.0.0"),
            port=int(os.environ.get("MYCASINO_RECEIVER_PORT", "8200")),
            path=os.environ.get("MYCASINO_RECEIVER_PATH", DEFAULT_PATH),
            secret=os.environ.get("MYCASINO_RECEIVER_SECRET") or None,
            block_ms=int(os.environ.get("MYCASINO_QUEUE_BLOCK_MS", "5000")),
            batch_size=int(
                os.environ.get("MYCASINO_QUEUE_BATCH_SIZE", "32")
            ),
            claim_idle_ms=int(
                os.environ.get("MYCASINO_QUEUE_CLAIM_IDLE_MS", "60000")
            ),
            enable_autoclaim=_truthy(
                os.environ.get("MYCASINO_QUEUE_AUTOCLAIM", "1")
            ),
        )
        return cfg


def get_redis_client(url: str) -> Any:
    """Lazy import so the runtime stays usable when redis isn't installed."""
    try:
        import redis.asyncio as redis_async
    except ImportError as e:  # pragma: no cover - import error path
        raise RuntimeError(
            "redis (>=4.2) is required for the queue receiver/worker. "
            "Install with: pip install 'redis>=4.2'"
        ) from e
    return redis_async.from_url(url, decode_responses=True)


async def ensure_consumer_group(
    redis: Any, stream: str, group: str
) -> None:
    """Create the consumer group, ignoring BUSYGROUP if it already exists."""
    try:
        await redis.xgroup_create(
            name=stream, groupname=group, id="$", mkstream=True
        )
        logger.info("Created consumer group %s on stream %s", group, stream)
    except Exception as e:  # noqa: BLE001
        # redis-py raises ResponseError("BUSYGROUP …") when the group
        # already exists.  Other errors should propagate.
        msg = str(e)
        if "BUSYGROUP" in msg:
            return
        raise
