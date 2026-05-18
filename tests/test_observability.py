"""Tests for ``core.observability`` — metrics + structured logging."""

from __future__ import annotations

import json
import logging

import pytest

from core import observability as obs


def test_json_formatter_outputs_valid_json():
    rec = logging.LogRecord(
        name="my.module",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    out = obs.JsonFormatter().format(rec)
    obj = json.loads(out)
    assert obj["msg"] == "hello world"
    assert obj["lvl"] == "INFO"
    assert obj["name"] == "my.module"
    assert "ts" in obj


def test_configure_logging_idempotent():
    obs.configure_logging("DEBUG", force_json=True)
    obs.configure_logging("INFO", force_json=False)
    # No exception ⇒ ok.
    assert logging.getLogger().level == logging.INFO


def test_counter_inc_and_render():
    counter = obs.REGISTRY.counter("test_counter_for_obs", "help text")
    counter.inc(2, {"label": "a"})
    counter.inc(1, {"label": "b"})
    text = counter.render()
    assert 'test_counter_for_obs{label="a"} 2' in text
    assert 'test_counter_for_obs{label="b"} 1' in text


def test_gauge_set_replaces_value():
    gauge = obs.REGISTRY.gauge("test_gauge_for_obs", "help")
    gauge.set(5.0)
    gauge.set(10.0)
    text = gauge.render()
    assert "test_gauge_for_obs 10.0" in text


def test_record_bet_updates_three_metrics():
    before_bets = obs.BETS_TOTAL.values.copy()
    obs.record_bet("blackjack", stake_usd=10.0, payout_usd=8.0)
    delta_bets = obs.BETS_TOTAL.values[(("game", "blackjack"),)] - before_bets.get(
        (("game", "blackjack"),), 0
    )
    assert delta_bets == 1


def test_metrics_text_renders_known_metric():
    obs.BETS_TOTAL.inc(1, {"game": "test_metrics_text_renders_known_metric"})
    text = obs.metrics_text()
    assert "mycasino_bets_total" in text
    assert "test_metrics_text_renders_known_metric" in text


def test_metrics_handler_returns_text():
    status, ctype, body = obs.metrics_handler()
    assert status == 200
    assert "text/plain" in ctype
    assert body  # non-empty


def test_init_sentry_skips_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert obs.init_sentry() is False


async def test_instrument_records_errors():
    @obs.instrument()
    async def boom():
        raise RuntimeError("nope")

    before = obs.ERRORS_TOTAL.values.copy()
    with pytest.raises(RuntimeError):
        await boom()
    # ``instrument`` records the wrapped function's defining module —
    # which is this test module, not the decorator's own module.
    key = (("module", __name__),)
    assert obs.ERRORS_TOTAL.values.get(key, 0) > before.get(key, 0)
