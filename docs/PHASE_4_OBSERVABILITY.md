# Phase 4 — Observability, audits, runbooks, blue-green

This phase doesn't change behaviour — it makes the bot *observable*
in production so on-call engineers can answer:

1. Is the bot alive?
2. Is it making money?
3. What's currently broken?

without SSHing into every box.

## Prometheus metrics

[`core/observability.py`](../core/observability.py) defines a tiny
registry that talks the standard Prometheus exposition format.  When
`prometheus_client` is installed we use its registry too, so existing
dashboards keep working unchanged.

Canonical metric names (every metric is namespaced `mycasino_*`):

| Metric                                    | Type    | Labels              |
|-------------------------------------------|---------|---------------------|
| `mycasino_bets_total`                     | counter | `game`              |
| `mycasino_bet_volume_usd_total`           | counter | `game`              |
| `mycasino_house_revenue_usd_total`        | counter | `game`              |
| `mycasino_active_games`                   | gauge   | —                   |
| `mycasino_pg_pool_in_use`                 | gauge   | —                   |
| `mycasino_redis_op_total`                 | counter | `op`, `result`      |
| `mycasino_rate_limit_blocked_total`       | counter | `bucket`            |
| `mycasino_withdrawals_total`              | counter | `coin`, `status`    |
| `mycasino_jackpot_balance_usd`            | gauge   | `pool`              |
| `mycasino_errors_total`                   | counter | `module`            |
| `mycasino_worker_heartbeat_ts`            | gauge   | —                   |

Use `core.observability.record_bet(game, stake_usd, payout_usd)` at
every settled bet site for the three top-line bet metrics in one
call.

The metrics endpoint runs as its own process:

```bash
python -m runtime.metrics_server  # default port 9100
```

or as a systemd unit — see
[`deploy/systemd/mycasino-metrics.service`](../deploy/systemd/mycasino-metrics.service).

The same process exposes `/healthz` (stale heartbeat ⇒ 503) and
`/readyz` (set to 200 after `mark_ready()` returns).

## Structured logs

`configure_logging()` (called from `bot.py` startup) switches the
root logger to JSON when `MYCASINO_LOG_JSON=1`.  Every record
becomes a single line with keys `ts, lvl, name, msg, …`.  Plays
nicely with Loki, Datadog Logs, GCP Cloud Logging.

For development, leave `MYCASINO_LOG_JSON` unset and you get human
readable output.

## Sentry

Set `SENTRY_DSN` and the bot calls `sentry_sdk.init(...)` on startup
(no-op when `sentry-sdk` isn't installed).  Tag the deploy color so
errors get associated with the active blue/green release:

```bash
SENTRY_DSN=https://...@sentry.io/1
MYCASINO_ENV=production
MYCASINO_COLOR=blue
SENTRY_TRACES_SAMPLE_RATE=0.05
```

## Audits

[`audit/`](../audit/) ships four read-only scripts to catch drift
between hot state and the ledger:

| Script                        | What it checks                                        |
|-------------------------------|-------------------------------------------------------|
| `wallet_audit.py`             | `wallets.balance == SUM(ledger_entries.delta)`         |
| `leaderboard_audit.py`        | Redis ZSET == ledger replay for `(period, metric)`     |
| `rakeback_audit.py`           | paid rakeback == expected per VIP tier (configurable)  |
| `house_edge_audit.py`         | realised house edge per game over a sliding window     |

Each script returns non-zero on drift, so you can wire them into
cron + alertmanager:

```cron
15 4 * * *  cd /opt/mycasino && /opt/mycasino/.venv/bin/python -m audit.wallet_audit       || /opt/mycasino/bin/alert "wallet drift"
30 4 * * *  cd /opt/mycasino && /opt/mycasino/.venv/bin/python -m audit.leaderboard_audit weekly wagered || true
45 4 * * *  cd /opt/mycasino && /opt/mycasino/.venv/bin/python -m audit.house_edge_audit --days 1        || true
```

## Provably-fair UI

[`tools/provably_fair_ui/index.html`](../tools/provably_fair_ui/index.html)
is a static page that verifies any `(server_seed, client_seed,
nonce, n)` tuple in the browser using WebCrypto.  Host it on any
static host and link from the bot's `/serverseed` flow.

## Runbooks

See [`docs/RUNBOOKS.md`](RUNBOOKS.md) for on-call procedures.

## Blue-green deploys

See [`docs/BLUE_GREEN.md`](BLUE_GREEN.md) for the deployment dance.
