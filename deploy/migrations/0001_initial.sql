-- Phase 2 — PostgreSQL wallet + ledger schema for mycasino.
--
-- Design goals
-- ------------
-- * Authoritative wallet state lives in PostgreSQL — no more JSON
--   dirty-flag flusher.  Concurrent bets serialize through a per-user
--   row lock (``SELECT ... FOR UPDATE``) so two workers can never split
--   the same balance.
-- * Every balance change is journaled in ``ledger_entries`` so the
--   wallet table is always reconstructable from the ledger.  The
--   ``balance_after`` snapshot lets us spot drift cheaply.
-- * ``processed_intents`` gives us idempotency for any operation that
--   has a stable client-side intent id (deposits, withdrawals, settled
--   bets).  Workers that retry on partial failure can safely replay.
-- * All amount columns use ``NUMERIC(38, 18)`` so we never lose
--   precision on tiny crypto values.  The application layer keeps
--   USD-denominated values in plain Python floats; the ledger is the
--   source of truth and uses high-precision decimals.
--
-- Safe to run multiple times: every CREATE uses IF NOT EXISTS.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id        BIGINT       PRIMARY KEY,
    username       TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Optional JSON blob for non-wallet metadata (referrals, tier, etc.).
    -- Always read/written by the application layer; never by triggers.
    profile        JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_users_username
    ON users (LOWER(username))
    WHERE username IS NOT NULL;


-- ---------------------------------------------------------------------------
-- wallets — one row per (user_id, coin).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wallets (
    user_id        BIGINT          NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    coin           TEXT            NOT NULL,
    balance        NUMERIC(38, 18) NOT NULL DEFAULT 0,
    -- Soft hold for in-flight bets that haven't been settled.  Real
    -- balance available for spend is (balance - hold).
    hold           NUMERIC(38, 18) NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, coin),
    CHECK (balance >= 0),
    CHECK (hold    >= 0),
    CHECK (balance >= hold)
);

CREATE INDEX IF NOT EXISTS idx_wallets_user_coin
    ON wallets (user_id, coin);


-- ---------------------------------------------------------------------------
-- ledger_entries — append-only journal of every wallet mutation.
--
-- Read flow for a bet:
--   1. SELECT ... FOR UPDATE on wallets row
--   2. INSERT ledger row with delta + balance_after
--   3. UPDATE wallets balance/hold
--   4. COMMIT
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ledger_entries (
    id              BIGSERIAL       PRIMARY KEY,
    user_id         BIGINT          NOT NULL,
    coin            TEXT            NOT NULL,
    delta           NUMERIC(38, 18) NOT NULL,
    balance_after   NUMERIC(38, 18) NOT NULL,
    -- 'bet_debit' | 'bet_credit' | 'deposit' | 'withdraw' | 'tip' |
    -- 'rakeback' | 'jackpot' | 'admin_adjust' | 'refund' | ...
    kind            TEXT            NOT NULL,
    -- Stable de-dup key supplied by the caller. NULL allowed for purely
    -- internal entries (e.g. rakeback flushes) where no idempotency
    -- guarantee is required.
    intent_id       TEXT,
    -- Free-form context — game id, withdrawal id, tx hash, etc.
    ref             TEXT,
    metadata        JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, coin) REFERENCES wallets (user_id, coin)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ledger_user_time
    ON ledger_entries (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ledger_kind_time
    ON ledger_entries (kind, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_ledger_intent
    ON ledger_entries (intent_id)
    WHERE intent_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- processed_intents — fast-path "have we seen this intent?" SET.
--
-- The unique index on ledger_entries.intent_id is the source of truth,
-- but a small dedicated table lets us reject duplicates with a single
-- short-lived row insert instead of touching the heavy ledger table.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed_intents (
    intent_id    TEXT         PRIMARY KEY,
    kind         TEXT         NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processed_intents_created
    ON processed_intents (created_at);


-- ---------------------------------------------------------------------------
-- withdrawals — workflow state for outbound payments.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS withdrawals (
    withdrawal_id     TEXT          PRIMARY KEY,
    user_id           BIGINT        NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    coin              TEXT          NOT NULL,
    chain             TEXT,
    -- The amount we debited from the user's wallet.
    amount            NUMERIC(38, 18) NOT NULL,
    amount_usd        NUMERIC(38, 18) NOT NULL,
    -- The recipient address (must validate against ``core.address_validation``
    -- before this row is created).
    address           TEXT          NOT NULL,
    status            TEXT          NOT NULL,   -- 'pending'|'approved'|'broadcast'|'confirmed'|'cancelled'|'failed'
    tx_hash           TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    metadata          JSONB         NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_withdrawals_user_time
    ON withdrawals (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_withdrawals_status
    ON withdrawals (status, created_at);


-- ---------------------------------------------------------------------------
-- provably_fair_records — every settled bet's RNG inputs.  Stored
-- forever so users can verify games even years later.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provably_fair_records (
    game_id        TEXT         PRIMARY KEY,
    user_id        BIGINT       NOT NULL,
    game_type      TEXT         NOT NULL,
    server_seed    TEXT         NOT NULL,
    -- Hash committed BEFORE the round is played.  Identifies which seed
    -- the player would have seen if they queried /serverseed at the time.
    server_seed_hash TEXT       NOT NULL,
    client_seed    TEXT         NOT NULL,
    nonce          INTEGER      NOT NULL,
    -- Final round outcome (game-specific JSON, e.g. {"hand": [...], "result": "win"}).
    outcome        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- A seed becomes "revealed" once the user rotates to the next one.
    revealed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pf_user_time
    ON provably_fair_records (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pf_game_type_time
    ON provably_fair_records (game_type, created_at DESC);


-- ---------------------------------------------------------------------------
-- pf_seed_lifecycle — tracks the active server seed for each user.
-- A new row is inserted on every rotation; the previous row's
-- ``revealed_at`` is set to NOW().  Lets us prove the seed was committed
-- BEFORE the games that used it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pf_seed_lifecycle (
    id                BIGSERIAL    PRIMARY KEY,
    user_id           BIGINT       NOT NULL,
    server_seed       TEXT         NOT NULL,
    server_seed_hash  TEXT         NOT NULL,
    client_seed       TEXT         NOT NULL,
    nonce_start       INTEGER      NOT NULL DEFAULT 0,
    nonce_end         INTEGER,
    committed_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    revealed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pf_lifecycle_user_time
    ON pf_seed_lifecycle (user_id, committed_at DESC);


-- ---------------------------------------------------------------------------
-- leaderboard_snapshots — persisted top-N entries per (period, metric).
--
-- Hot leaderboard state lives in Redis sorted sets; this table is for
-- the cold/snapshot side (weekly/monthly winners, audit history).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
    id          BIGSERIAL    PRIMARY KEY,
    period      TEXT         NOT NULL,    -- 'daily'|'weekly'|'monthly'|'alltime'
    metric      TEXT         NOT NULL,    -- 'wagered'|'won'|'multiplier'|...
    snapshot_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- ordered JSON array of {user_id, username, value, rank}
    entries     JSONB        NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lb_period_time
    ON leaderboard_snapshots (period, metric, snapshot_at DESC);


-- ---------------------------------------------------------------------------
-- jackpot_log — history of jackpot pool drops.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jackpot_log (
    id            BIGSERIAL     PRIMARY KEY,
    pool_name     TEXT          NOT NULL,
    winner_id     BIGINT,
    amount        NUMERIC(38, 18) NOT NULL,
    triggered_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    metadata      JSONB         NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_jackpot_pool_time
    ON jackpot_log (pool_name, triggered_at DESC);


-- ---------------------------------------------------------------------------
-- schema_migrations — version tracking
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT         PRIMARY KEY,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

INSERT INTO schema_migrations (version) VALUES ('0001_initial')
    ON CONFLICT (version) DO NOTHING;
