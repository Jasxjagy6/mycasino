# Phase 2 — PostgreSQL wallet + ledger, Redis for hot state, stateless workers

This document describes the architectural change that lets mycasino
handle 10k+ concurrent users on the same hardware that previously
choked at a few hundred.

## What changed

| Concern                  | Before                            | After                                          |
|--------------------------|-----------------------------------|------------------------------------------------|
| Wallet balance authority | In-memory dict + JSON file flush  | Postgres `wallets` table                       |
| Bet atomicity            | Per-user `asyncio.Lock`           | `SELECT ... FOR UPDATE` row lock               |
| Bet idempotency          | None                              | `ledger_entries.intent_id` UNIQUE index        |
| Rate limiting            | None / Python dict                | Redis sliding-window via Lua                   |
| Leaderboards             | Python dict, single-process       | Redis sorted-sets (`ZINCRBY`, `ZREVRANGE`)     |
| Jackpot                  | Python float                      | Redis `INCRBYFLOAT` (atomic across workers)    |
| Deduplication            | None                              | Redis `SET NX EX`                              |
| Workers                  | 1                                 | N stateless workers under `XREADGROUP`         |

## Wallet + ledger schema

See [`deploy/migrations/0001_initial.sql`](../deploy/migrations/0001_initial.sql)
for the full DDL.  Key tables:

* `wallets` — one row per `(user_id, coin)`.  All mutations go through
  the row lock so no two workers can split the same balance.
* `ledger_entries` — append-only journal.  Reconstruct `wallets` from
  the journal with
  `SUM(delta) GROUP BY user_id, coin`.  `audit/wallet_audit.py`
  performs this check nightly.
* `withdrawals` — workflow state (`pending → approved → broadcast →
  confirmed | cancelled | failed`).
* `processed_intents` — fast-path "have we seen this intent_id?" set.
* `provably_fair_records` / `pf_seed_lifecycle` — RNG audit trail
  (Phase 3 uses these too).

## Bet life-cycle

```python
# core/wallet_ledger.py
entry = await place_bet(
    user_id, "USDT", 1.0,
    game_id="blackjack-G-251101120000-AB12CD",
    metadata={"chips": 1.0, "table": "bj-fast-1"},
)
# … game plays out …
await settle_bet(
    user_id, "USDT", 2.4,
    game_id="blackjack-G-251101120000-AB12CD",
)
```

Both calls take a row lock, append a ledger entry and update the
wallet inside the same transaction.  If anything throws, Postgres
rolls back; no balance change happens.  Retrying the same
`game_id` is a no-op because the unique index on `ledger_entries.intent_id`
short-circuits the second insert.

## Redis backbone

Everything goes through [`core/redis_backend.py`](../core/redis_backend.py)
— the rest of the codebase never touches a raw Redis client.

* `check_rate_limit(bucket, limit, window_ms)` → sliding window via
  a single `EVAL`.  Fails open if Redis is unreachable so we never
  block real users during an outage.
* `claim_once(intent_key, ttl_seconds)` → `SET NX EX`; returns `True`
  iff this is the first time we've seen the key.
* `incr_jackpot(pool, amount)` → atomic `INCRBYFLOAT`.  Drop the pool
  with `drop_jackpot(pool)` to return the current total and reset.
* `lb_incr(period, metric, user_id, amount)` → `ZINCRBY`; daily/weekly
  keys auto-expire after `MYCASINO_LEADERBOARD_TTL` seconds (default
  8 days).
* `lb_top(period, metric, limit)` → `ZREVRANGE`.

When Redis isn't configured the same helpers fall back to a
per-process Python dict — convenient for unit tests but unsafe for
real workloads.

## Stateless workers

The pre-existing receiver/worker split is already correct, but the
worker used to mutate in-process state (`user_stats[uid]`).  Now that
wallet authority lives in Postgres and hot state lives in Redis, you
can run as many workers as you have cores:

```bash
# /etc/systemd/system/mycasino-worker@.service
for i in 1 2 3 4; do
  sudo systemctl enable --now "mycasino-worker@${i}.service"
done
```

Each worker pulls its own `MYCASINO_QUEUE_CONSUMER` from the unit
instance name, so Redis Streams load-balances updates across them
automatically.

## Configuration

```bash
# Postgres
POSTGRES_URL=postgresql://mycasino:secret@db:5432/mycasino
MYCASINO_PG_LEDGER=1               # enable the new ledger path
MYCASINO_PG_MIN_POOL=2
MYCASINO_PG_MAX_POOL=20
MYCASINO_PG_STATEMENT_TIMEOUT=5000  # ms — protects against runaway locks

# Redis backbone
MYCASINO_REDIS_URL=redis://localhost:6379/0
MYCASINO_REDIS_BACKEND=1            # turn on Redis-backed helpers
MYCASINO_LEADERBOARD_TTL=691200     # 8 days
MYCASINO_JACKPOT_KEY_PREFIX=mycasino:jackpot:

# Workers
MYCASINO_QUEUE_STREAM=mycasino:updates
MYCASINO_QUEUE_GROUP=mycasino-workers
MYCASINO_QUEUE_BATCH_SIZE=32
MYCASINO_QUEUE_BLOCK_MS=5000
MYCASINO_QUEUE_AUTOCLAIM=1
MYCASINO_QUEUE_CLAIM_IDLE_MS=60000  # auto-recover crashed worker entries
```

## Migration from JSON

```bash
POSTGRES_URL=... MYCASINO_PG_LEDGER=1 \
  python -m scripts.migrate_json_to_postgres --dry-run
# inspect output, then drop --dry-run
POSTGRES_URL=... MYCASINO_PG_LEDGER=1 \
  python -m scripts.migrate_json_to_postgres
```

The migration is idempotent — it uses
`intent_id="migration_seed:<uid>:<coin>"` so re-running never
double-credits.

## Capacity targets

The single-worker bottleneck used to be the asyncio.Lock contention
on the JSON flusher.  With the new layout, the bottleneck moves to
Postgres' per-row lock.  Conservatively:

* `SELECT ... FOR UPDATE` + ledger insert: ~2-5ms per bet on a small
  RDS instance.
* Pool size 20 × 5ms ⇒ ~4000 bets/sec/process before contention.
* Two PG replicas + 4 workers ⇒ comfortably north of 10k concurrent
  active users at <1 RPS each.

## What's still single-process

Anything that mutates `core.foundation.*` Python globals (e.g. game
session dicts) is still per-worker.  That's fine because each game
session is sticky to the worker that started it — Redis Streams send
the user's updates to that worker via consumer-group routing, and
recovery happens via `XAUTOCLAIM` if the worker dies.
