# On-call Runbooks

Each section here is "what to do at 03:00 when X is on fire".  Keep
them short.  If a runbook grows past a screen, split it.

## Glossary

* **Receiver** — `mycasino-receiver.service` — single-instance HTTP
  server that accepts the Telegram webhook and pushes updates onto
  the `mycasino:updates` Redis stream.
* **Worker** — `mycasino-worker@N.service` — one of N stateless
  processes consuming the stream and driving the PTB Application.
* **Metrics** — `mycasino-metrics.service` — Prometheus `/metrics`
  + `/healthz` endpoints (default port 9100).
* **Ledger** — `wallets` + `ledger_entries` tables in Postgres.
* **Backbone** — Redis instance backing rate-limit, jackpot,
  leaderboards, dedup.

---

## RB-01 — Bot is silent (no replies)

1. Check the receiver:
   ```bash
   systemctl status mycasino-receiver
   journalctl -u mycasino-receiver -n 200
   ```
2. Confirm Telegram is hitting it.  In `/etc/mycasino/receiver.env`
   the path must match the URL you set via `setWebhook`:
   ```bash
   curl -fsS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo" | jq
   ```
3. Check the worker fleet:
   ```bash
   systemctl status 'mycasino-worker@*' --no-pager
   ```
   If ANY worker is healthy, replies should be flowing.  All down ⇒
   continue to RB-02.

## RB-02 — All workers down / restart loop

1. Pull the most recent worker log:
   ```bash
   journalctl -u mycasino-worker@1 -n 500 --no-pager
   ```
2. Most common cause is a bad deploy — switch to the other color:
   ```bash
   deploy/blue_green_switch.sh green
   ```
   See `docs/BLUE_GREEN.md`.
3. Second most common: Postgres unreachable.  Test with
   `psql "$POSTGRES_URL" -c 'SELECT 1'`.

## RB-03 — Stream lag (XLEN > 1000)

1. Inspect the stream length:
   ```bash
   redis-cli XLEN mycasino:updates
   redis-cli XINFO GROUPS mycasino:updates
   ```
2. If the lag is workers being slow:
   * Add more workers:
     `systemctl enable --now mycasino-worker@5.service` (and 6, 7…).
   * Bump batch size: `MYCASINO_QUEUE_BATCH_SIZE=64`.
3. If the lag is workers being stuck — look at the autoclaim metric
   and `journalctl -u mycasino-worker@*`.  A wedged worker auto-claims
   release entries after `MYCASINO_QUEUE_CLAIM_IDLE_MS` (default 60s).

## RB-04 — Postgres pool exhausted

Symptom: `asyncio.TimeoutError` / "pool exhausted" in worker logs.

1. Active connections:
   ```sql
   SELECT pid, application_name, state, query, NOW() - query_start AS age
   FROM pg_stat_activity
   WHERE application_name = 'mycasino'
   ORDER BY age DESC LIMIT 20;
   ```
2. Kill long-running queries holding a wallet row lock:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE application_name='mycasino' AND state='idle in transaction'
     AND NOW() - query_start > interval '30 seconds';
   ```
3. Permanent fix: bump `MYCASINO_PG_MAX_POOL`.

## RB-05 — Redis backbone down

The bot continues running — `core/redis_backend.py` fails open on
rate-limit, leaderboard, and jackpot calls.  But fresh leaderboard
state will be lost (in-memory fallback is per-process).

1. Diagnose:
   ```bash
   redis-cli -u "$MYCASINO_REDIS_URL" ping
   ```
2. While Redis is down, **disable** the new bet rate limit so users
   aren't blocked:
   ```bash
   redis-cli SET mycasino:rl:disabled 1
   ```
   (this isn't honoured by the current code yet — see TODO in
   `core/redis_backend.py`; for now just restart Redis ASAP).
3. After Redis comes back, run `audit/leaderboard_audit.py` to
   rebuild the boards from the ledger.

## RB-06 — Withdrawal stuck in 'broadcast'

1. Look up the row:
   ```sql
   SELECT * FROM withdrawals WHERE withdrawal_id = 'WD-...';
   ```
2. If `tx_hash` is set, check the chain explorer.  If the tx is
   confirmed, flip status manually:
   ```sql
   UPDATE withdrawals SET status='confirmed', updated_at=NOW()
   WHERE withdrawal_id = 'WD-...';
   ```
   (Or programmatically:
   `core.wallet_ledger.mark_withdrawal_confirmed`.)
3. If the tx never broadcast and the user is complaining, refund:
   ```python
   await core.wallet_ledger.refund_withdrawal('WD-...', reason='stuck broadcast')
   ```

## RB-07 — Wallet drift detected

`audit/wallet_audit.py` returned non-zero.

1. List the drifting rows from its output.
2. For each drifting `(user_id, coin)`:
   ```sql
   SELECT * FROM ledger_entries
   WHERE user_id=$1 AND coin=$2 ORDER BY created_at DESC LIMIT 50;
   ```
3. If you find an obvious gap (e.g. a credit with no matching debit),
   record an `admin_adjust` ledger entry to bring the wallet back in
   line.  **Never** UPDATE `wallets.balance` directly — that breaks
   the invariant.

## RB-08 — Master mnemonic rotation

Pre-reqs: a new mnemonic generated offline.

1. Bring up the bot in MAINTENANCE mode (set `BOT_STOPPED=1` and
   restart workers).
2. Sweep all funds from existing deposit addresses to the cold
   wallet (use `core/foundation.py` `EvmService.sweep_funds`).
3. Update `MASTER_MNEMONIC` in the env file.
4. Restart all workers — they will generate new BIP-44 addresses
   for users on next deposit attempt.
5. Take the bot out of MAINTENANCE mode.

⚠️  This is a destructive operation.  Do it during scheduled
downtime with a backup of `data/` and a Postgres snapshot taken
first.

## RB-09 — Worker memory leak

1. Identify the worker:
   ```bash
   systemctl status 'mycasino-worker@*'
   # find the one near or over MemoryMax
   ```
2. Cycle it:
   ```bash
   systemctl restart mycasino-worker@3
   ```
   The autoclaim loop on the other workers picks up its inflight
   entries within `MYCASINO_QUEUE_CLAIM_IDLE_MS`.
3. After the restart, capture a heap dump for analysis:
   ```bash
   python -m tracemalloc … # (configure via env var)
   ```

## RB-10 — Reverting a deploy

See [`docs/BLUE_GREEN.md`](BLUE_GREEN.md).
