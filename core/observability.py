"""Phase 4 — Observability: Prometheus metrics + Sentry + structured logs.

We try to depend on **only the standard library** so the bot keeps
running when the optional packages aren't installed.  When
``prometheus_client`` is present we use its real metrics; otherwise we
expose a hand-rolled exporter that produces identical text-format
output.  Same story for Sentry — if ``sentry-sdk`` is installed AND
``SENTRY_DSN`` is set, we initialise it; otherwise we no-op.

Three opt-in entry points:

* :func:`configure_logging` — switches the root logger to JSON output.
* :func:`init_sentry` — wires up sentry-sdk if available.
* :func:`metrics_text` / :func:`metrics_handler` — produce the
  Prometheus exposition format that ``runtime/metrics_server.py``
  serves.

Standard metric names (all gauges / counters):

    mycasino_bets_total{game}                       Counter
    mycasino_bet_volume_usd_total{game}             Counter (sum of stake_usd)
    mycasino_house_revenue_usd_total{game}          Counter (sum of stake-payout)
    mycasino_active_games                           Gauge
    mycasino_pg_pool_in_use                         Gauge
    mycasino_redis_op_total{op,result}              Counter
    mycasino_rate_limit_blocked_total{bucket}       Counter
    mycasino_withdrawals_total{coin,status}         Counter
    mycasino_jackpot_balance_usd{pool}              Gauge
    mycasino_errors_total{module}                   Counter
"""

from __future__ import annotations

import json
import logging
import logging.config
import os
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() in _TRUTHY


# ---------------------------------------------------------------------------
# Logging — structured JSON
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Render every record as a single JSON line."""

    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "lvl": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k in self._RESERVED or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: str = "INFO",
    *,
    force_json: Optional[bool] = None,
) -> None:
    """Switch the root logger to JSON.

    Idempotent — safe to call multiple times.  When ``force_json`` is
    ``None``, JSON mode is decided by the env var
    ``MYCASINO_LOG_JSON``.
    """
    use_json = force_json if force_json is not None else _truthy(
        os.environ.get("MYCASINO_LOG_JSON")
    )
    handler = logging.StreamHandler()
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s"
            )
        )
    root = logging.getLogger()
    # Remove existing handlers so we don't double-log.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------


_sentry_initialised = False


def init_sentry(
    dsn: Optional[str] = None,
    *,
    environment: Optional[str] = None,
    release: Optional[str] = None,
) -> bool:
    """Initialise sentry-sdk if installed & DSN configured.

    Returns True on success, False when skipped.  Idempotent.
    """
    global _sentry_initialised
    if _sentry_initialised:
        return True
    dsn = dsn or os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - import failure
        logger.info("sentry-sdk not installed; skipping Sentry init")
        return False
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment or os.environ.get("MYCASINO_ENV", "production"),
            release=release or os.environ.get("MYCASINO_COLOR", "blue"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        )
        _sentry_initialised = True
        logger.info("Sentry initialised")
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Sentry init failed")
        return False


# ---------------------------------------------------------------------------
# Metrics — minimal Prometheus-compatible registry.
#
# We use prometheus_client when available so existing dashboards keep
# working.  When it isn't, the inline implementation produces the same
# text format so a scraping Prometheus can't tell the difference.
# ---------------------------------------------------------------------------


_metrics_lock = threading.Lock()


class _Metric:
    """Either a Counter or a Gauge.  Labels are sorted-tuple keyed."""

    def __init__(self, name: str, kind: str, help_text: str):
        self.name = name
        self.kind = kind  # "counter" or "gauge"
        self.help_text = help_text
        self.values: Dict[Tuple[Tuple[str, str], ...], float] = defaultdict(float)

    def _key(self, labels: Optional[Dict[str, str]]) -> Tuple[Tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(sorted((k, str(v)) for k, v in labels.items()))

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        with _metrics_lock:
            self.values[self._key(labels)] += amount

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        with _metrics_lock:
            self.values[self._key(labels)] = float(value)

    def add(self, amount: float, labels: Optional[Dict[str, str]] = None) -> None:
        self.inc(amount, labels)

    def render(self) -> str:
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} {self.kind}",
        ]
        with _metrics_lock:
            for key, val in self.values.items():
                if not key:
                    lines.append(f"{self.name} {val}")
                else:
                    label_str = ",".join(
                        f'{k}="{_esc(v)}"' for k, v in key
                    )
                    lines.append(f"{self.name}{{{label_str}}} {val}")
        return "\n".join(lines) + "\n"


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Registry:
    def __init__(self) -> None:
        self.metrics: Dict[str, _Metric] = {}

    def counter(self, name: str, help_text: str) -> _Metric:
        if name not in self.metrics:
            self.metrics[name] = _Metric(name, "counter", help_text)
        return self.metrics[name]

    def gauge(self, name: str, help_text: str) -> _Metric:
        if name not in self.metrics:
            self.metrics[name] = _Metric(name, "gauge", help_text)
        return self.metrics[name]

    def render(self) -> str:
        return "".join(m.render() for m in self.metrics.values())


REGISTRY = Registry()


# Canonical metric handles — call sites import these directly.
BETS_TOTAL = REGISTRY.counter(
    "mycasino_bets_total", "Total settled bets, by game"
)
BET_VOLUME_USD = REGISTRY.counter(
    "mycasino_bet_volume_usd_total", "Cumulative bet stake in USD"
)
HOUSE_REVENUE_USD = REGISTRY.counter(
    "mycasino_house_revenue_usd_total", "Cumulative house revenue (stake-payout)"
)
ACTIVE_GAMES = REGISTRY.gauge(
    "mycasino_active_games", "Currently active game sessions"
)
PG_POOL_IN_USE = REGISTRY.gauge(
    "mycasino_pg_pool_in_use", "asyncpg connections in use"
)
REDIS_OPS = REGISTRY.counter(
    "mycasino_redis_op_total", "Redis operation counter"
)
RATE_LIMITED = REGISTRY.counter(
    "mycasino_rate_limit_blocked_total", "Requests blocked by rate limit"
)
WITHDRAWALS_TOTAL = REGISTRY.counter(
    "mycasino_withdrawals_total", "Withdrawals, by coin and status"
)
JACKPOT_BALANCE_USD = REGISTRY.gauge(
    "mycasino_jackpot_balance_usd", "Current jackpot balance in USD"
)
ERRORS_TOTAL = REGISTRY.counter(
    "mycasino_errors_total", "Logged exceptions, by module"
)
WORKER_HEARTBEAT = REGISTRY.gauge(
    "mycasino_worker_heartbeat_ts", "Unix timestamp of last worker heartbeat"
)


def record_bet(game: str, stake_usd: float, payout_usd: float) -> None:
    """One-stop helper for game plugins to update bet metrics."""
    BETS_TOTAL.inc(1, {"game": game})
    BET_VOLUME_USD.inc(stake_usd, {"game": game})
    HOUSE_REVENUE_USD.inc(stake_usd - payout_usd, {"game": game})


def metrics_text() -> str:
    """Return the Prometheus exposition payload for the current process."""
    try:
        from prometheus_client import (  # type: ignore[import-not-found]
            REGISTRY as PROM_REGISTRY,
            generate_latest,
        )
        # We *also* render our internal registry so call-sites that use
        # the lightweight handles still get exported.
        return REGISTRY.render() + generate_latest(PROM_REGISTRY).decode("utf-8")
    except Exception:
        return REGISTRY.render()


def metrics_handler(_request=None) -> Tuple[int, str, str]:
    """Return (status, content_type, body).  Used by the metrics server."""
    return 200, "text/plain; version=0.0.4; charset=utf-8", metrics_text()


# ---------------------------------------------------------------------------
# Decorator: instrument an async function
# ---------------------------------------------------------------------------


def instrument(metric_name: str = "errors"):
    """Decorator that bumps ``ERRORS_TOTAL`` when the wrapped fn raises."""
    def deco(fn: Callable):
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception:
                ERRORS_TOTAL.inc(1, {"module": fn.__module__})
                raise
        return wrapper
    return deco


__all__ = [
    "JsonFormatter",
    "configure_logging",
    "init_sentry",
    "metrics_text",
    "metrics_handler",
    "record_bet",
    "instrument",
    "BETS_TOTAL",
    "BET_VOLUME_USD",
    "HOUSE_REVENUE_USD",
    "ACTIVE_GAMES",
    "PG_POOL_IN_USE",
    "REDIS_OPS",
    "RATE_LIMITED",
    "WITHDRAWALS_TOTAL",
    "JACKPOT_BALANCE_USD",
    "ERRORS_TOTAL",
    "WORKER_HEARTBEAT",
    "REGISTRY",
]
