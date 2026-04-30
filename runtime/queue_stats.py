"""Lightweight Redis Stream stats used by ``/runtimestatus``.

Returns ``None``-friendly results when Redis is unreachable so the
admin command can still render the rest of the runtime status.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from runtime.queue_common import QueueConfig, get_redis_client

logger = logging.getLogger(__name__)


async def snapshot(cfg: Optional[QueueConfig] = None) -> Optional[Dict[str, Any]]:
    cfg = cfg or QueueConfig.from_env()
    try:
        redis = get_redis_client(cfg.redis_url)
    except Exception:
        return None
    try:
        try:
            length = await redis.xlen(cfg.stream)
        except Exception:
            length = 0
        try:
            groups = await redis.xinfo_groups(cfg.stream)
            groups_count = len(groups) if groups else 0
        except Exception:
            groups_count = 0
        try:
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass
        return {
            "stream": cfg.stream,
            "length": int(length or 0),
            "groups": groups_count,
        }
    except Exception:  # noqa: BLE001
        logger.warning("queue_stats snapshot failed", exc_info=True)
        return None
