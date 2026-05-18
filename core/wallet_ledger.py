"""Phase 2 — PostgreSQL wallet + ledger with row-level locking.

Every balance-mutating operation goes through one of three public
functions:

* :func:`place_bet`     — debit the user's wallet at the start of a bet
* :func:`settle_bet`    — credit winnings at the end of a bet
* :func:`adjust_balance` — generic credit/debit (deposits, tips,
  rakeback, withdrawal hold, refunds, etc.)

All three open a single transaction and serialize concurrent access to
the same wallet via ``SELECT ... FOR UPDATE``.  A copy of every change
lands in ``ledger_entries`` so the wallet table is always
reconstructable from the journal.

Operations also accept a stable ``intent_id`` — when supplied, repeating
the call returns the existing ledger entry instead of double-spending.
That lets the worker layer retry on partial failures without bookkeeping.

The module is import-safe even when ``asyncpg`` isn't installed; in
that case the public functions raise ``LedgerUnavailable`` so callers
can fall back to legacy code paths.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, Optional

from core.db_pool import get_pool, pg_ledger_enabled

logger = logging.getLogger(__name__)

# We work in Decimal so a 1e-18 precision crypto value never truncates.
getcontext().prec = 60


class LedgerUnavailable(RuntimeError):
    """Raised when the PG ledger is requested but unavailable."""


class InsufficientFunds(ValueError):
    """Raised when a debit would leave the wallet negative."""


# ----------------------------------------------------------------------------
# Result types
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerEntry:
    """Returned to call-sites so they can pull tx id, new balance, etc."""

    ledger_id: int
    user_id: int
    coin: str
    delta: Decimal
    balance_after: Decimal
    kind: str
    intent_id: Optional[str]
    ref: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def _ensure_user_and_wallet(conn, user_id: int, coin: str) -> None:
    """Idempotently create the user + wallet rows.

    Safe under high concurrency because of the upsert form.
    """
    await conn.execute(
        "INSERT INTO users (user_id) VALUES ($1) "
        "ON CONFLICT (user_id) DO NOTHING",
        user_id,
    )
    await conn.execute(
        "INSERT INTO wallets (user_id, coin, balance) "
        "VALUES ($1, $2, 0) "
        "ON CONFLICT (user_id, coin) DO NOTHING",
        user_id,
        coin,
    )


def _row_to_ledger_entry(row) -> LedgerEntry:
    return LedgerEntry(
        ledger_id=row["id"],
        user_id=row["user_id"],
        coin=row["coin"],
        delta=row["delta"],
        balance_after=row["balance_after"],
        kind=row["kind"],
        intent_id=row["intent_id"],
        ref=row["ref"],
        metadata=dict(row["metadata"]) if row["metadata"] else {},
    )


async def _check_intent(conn, intent_id: Optional[str]) -> Optional[LedgerEntry]:
    if not intent_id:
        return None
    row = await conn.fetchrow(
        "SELECT id, user_id, coin, delta, balance_after, kind, "
        "intent_id, ref, metadata "
        "FROM ledger_entries WHERE intent_id = $1",
        intent_id,
    )
    if row is None:
        return None
    return _row_to_ledger_entry(row)


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


async def get_balance(user_id: int, coin: str) -> Decimal:
    """Read the current balance for a (user, coin) pair.

    Does NOT take a row lock — only use for read-only views (dashboards,
    /balance command).  All mutating code must call one of the
    place_bet/settle_bet/adjust_balance helpers.
    """
    pool = await get_pool()
    if pool is None:
        raise LedgerUnavailable("Postgres pool not initialised")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance FROM wallets WHERE user_id=$1 AND coin=$2",
            user_id,
            coin,
        )
        if row is None:
            return Decimal("0")
        return row["balance"]


async def get_all_balances(user_id: int) -> Dict[str, Decimal]:
    pool = await get_pool()
    if pool is None:
        raise LedgerUnavailable("Postgres pool not initialised")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT coin, balance FROM wallets WHERE user_id=$1",
            user_id,
        )
        return {r["coin"]: r["balance"] for r in rows}


async def adjust_balance(
    user_id: int,
    coin: str,
    delta,
    *,
    kind: str,
    intent_id: Optional[str] = None,
    ref: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    allow_negative: bool = False,
) -> LedgerEntry:
    """Generic credit/debit with row-locking.

    ``delta`` may be positive (credit) or negative (debit).
    ``intent_id`` makes the call idempotent.
    ``allow_negative`` is only respected for admin adjustments — in all
    other cases the CHECK constraint on wallets.balance >= 0 prevents
    overdraw at the DB layer too.
    """
    if not pg_ledger_enabled():
        raise LedgerUnavailable(
            "PG ledger is disabled; set POSTGRES_URL and MYCASINO_PG_LEDGER=1"
        )
    delta_d = _to_decimal(delta)
    if delta_d == 0:
        raise ValueError("delta must be non-zero")
    pool = await get_pool()
    if pool is None:
        raise LedgerUnavailable("Postgres pool not initialised")
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await _check_intent(conn, intent_id)
            if existing is not None:
                return existing
            await _ensure_user_and_wallet(conn, user_id, coin)
            # Row lock until commit.
            row = await conn.fetchrow(
                "SELECT balance, hold FROM wallets "
                "WHERE user_id=$1 AND coin=$2 FOR UPDATE",
                user_id,
                coin,
            )
            current: Decimal = row["balance"]
            new_balance = current + delta_d
            if new_balance < 0 and not allow_negative:
                raise InsufficientFunds(
                    f"user={user_id} coin={coin} balance={current} delta={delta_d}"
                )
            await conn.execute(
                "UPDATE wallets SET balance = $1, updated_at = NOW() "
                "WHERE user_id = $2 AND coin = $3",
                new_balance,
                user_id,
                coin,
            )
            entry_row = await conn.fetchrow(
                "INSERT INTO ledger_entries "
                "(user_id, coin, delta, balance_after, kind, intent_id, ref, metadata) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb) "
                "RETURNING id, user_id, coin, delta, balance_after, kind, "
                "intent_id, ref, metadata",
                user_id,
                coin,
                delta_d,
                new_balance,
                kind,
                intent_id,
                ref,
                _encode_metadata(metadata),
            )
            return _row_to_ledger_entry(entry_row)


async def place_bet(
    user_id: int,
    coin: str,
    amount,
    *,
    game_id: str,
    intent_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> LedgerEntry:
    """Debit ``amount`` from the user's wallet for a new bet."""
    if intent_id is None:
        intent_id = f"bet:debit:{game_id}"
    amount_d = _to_decimal(amount)
    if amount_d <= 0:
        raise ValueError("Bet amount must be positive")
    return await adjust_balance(
        user_id,
        coin,
        -amount_d,
        kind="bet_debit",
        intent_id=intent_id,
        ref=game_id,
        metadata=metadata,
    )


async def settle_bet(
    user_id: int,
    coin: str,
    payout,
    *,
    game_id: str,
    intent_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[LedgerEntry]:
    """Credit a bet payout (positive value).  No-op when ``payout`` is 0."""
    payout_d = _to_decimal(payout)
    if payout_d < 0:
        raise ValueError("Settle payout must be >= 0")
    if payout_d == 0:
        return None
    if intent_id is None:
        intent_id = f"bet:credit:{game_id}"
    return await adjust_balance(
        user_id,
        coin,
        payout_d,
        kind="bet_credit",
        intent_id=intent_id,
        ref=game_id,
        metadata=metadata,
    )


async def credit_deposit(
    user_id: int,
    coin: str,
    amount,
    *,
    tx_hash: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> LedgerEntry:
    """Idempotent deposit credit keyed on chain tx hash."""
    intent_id = f"deposit:{coin}:{tx_hash}"
    return await adjust_balance(
        user_id,
        coin,
        amount,
        kind="deposit",
        intent_id=intent_id,
        ref=tx_hash,
        metadata=metadata,
    )


async def reserve_withdrawal(
    user_id: int,
    coin: str,
    amount,
    *,
    withdrawal_id: str,
    address: str,
    chain: Optional[str] = None,
    amount_usd: Optional[Decimal] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> LedgerEntry:
    """Debit ``amount`` for a pending withdrawal and create the row.

    The withdrawal row + ledger entry are written in the same
    transaction so a crash between the two can never leak a debit.
    """
    if not pg_ledger_enabled():
        raise LedgerUnavailable(
            "PG ledger is disabled; set POSTGRES_URL and MYCASINO_PG_LEDGER=1"
        )
    amount_d = _to_decimal(amount)
    if amount_d <= 0:
        raise ValueError("Withdrawal amount must be positive")
    intent_id = f"withdrawal:reserve:{withdrawal_id}"
    pool = await get_pool()
    if pool is None:
        raise LedgerUnavailable("Postgres pool not initialised")
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await _check_intent(conn, intent_id)
            if existing is not None:
                return existing
            await _ensure_user_and_wallet(conn, user_id, coin)
            row = await conn.fetchrow(
                "SELECT balance FROM wallets "
                "WHERE user_id=$1 AND coin=$2 FOR UPDATE",
                user_id,
                coin,
            )
            current: Decimal = row["balance"]
            new_balance = current - amount_d
            if new_balance < 0:
                raise InsufficientFunds(
                    f"user={user_id} coin={coin} balance={current} reserve={amount_d}"
                )
            await conn.execute(
                "UPDATE wallets SET balance = $1, updated_at = NOW() "
                "WHERE user_id = $2 AND coin = $3",
                new_balance,
                user_id,
                coin,
            )
            entry_row = await conn.fetchrow(
                "INSERT INTO ledger_entries "
                "(user_id, coin, delta, balance_after, kind, intent_id, ref, metadata) "
                "VALUES ($1, $2, $3, $4, 'withdraw_reserve', $5, $6, $7::jsonb) "
                "RETURNING id, user_id, coin, delta, balance_after, kind, "
                "intent_id, ref, metadata",
                user_id,
                coin,
                -amount_d,
                new_balance,
                intent_id,
                withdrawal_id,
                _encode_metadata(metadata),
            )
            await conn.execute(
                "INSERT INTO withdrawals "
                "(withdrawal_id, user_id, coin, chain, amount, amount_usd, address, status, metadata) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', $8::jsonb) "
                "ON CONFLICT (withdrawal_id) DO NOTHING",
                withdrawal_id,
                user_id,
                coin,
                chain,
                amount_d,
                _to_decimal(amount_usd) if amount_usd is not None else amount_d,
                address,
                _encode_metadata(metadata),
            )
            return _row_to_ledger_entry(entry_row)


async def refund_withdrawal(
    withdrawal_id: str,
    *,
    reason: Optional[str] = None,
) -> Optional[LedgerEntry]:
    """Reverse a withdrawal that never broadcast (admin cancel).

    Returns the credit ledger entry, or None if the withdrawal had
    already been refunded.
    """
    if not pg_ledger_enabled():
        raise LedgerUnavailable(
            "PG ledger is disabled; set POSTGRES_URL and MYCASINO_PG_LEDGER=1"
        )
    pool = await get_pool()
    if pool is None:
        raise LedgerUnavailable("Postgres pool not initialised")
    intent_id = f"withdrawal:refund:{withdrawal_id}"
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await _check_intent(conn, intent_id)
            if existing is not None:
                return existing
            wd = await conn.fetchrow(
                "SELECT user_id, coin, amount, status "
                "FROM withdrawals WHERE withdrawal_id = $1 FOR UPDATE",
                withdrawal_id,
            )
            if wd is None:
                return None
            if wd["status"] in ("broadcast", "confirmed"):
                raise ValueError(
                    f"refund refused: withdrawal already in status {wd['status']}"
                )
            user_id = wd["user_id"]
            coin = wd["coin"]
            amount_d: Decimal = wd["amount"]
            row = await conn.fetchrow(
                "SELECT balance FROM wallets "
                "WHERE user_id=$1 AND coin=$2 FOR UPDATE",
                user_id,
                coin,
            )
            current: Decimal = row["balance"]
            new_balance = current + amount_d
            await conn.execute(
                "UPDATE wallets SET balance = $1, updated_at = NOW() "
                "WHERE user_id = $2 AND coin = $3",
                new_balance,
                user_id,
                coin,
            )
            await conn.execute(
                "UPDATE withdrawals SET status='cancelled', updated_at=NOW(), "
                "metadata = COALESCE(metadata, '{}'::jsonb) || $1::jsonb "
                "WHERE withdrawal_id = $2",
                _encode_metadata({"refund_reason": reason} if reason else None),
                withdrawal_id,
            )
            entry_row = await conn.fetchrow(
                "INSERT INTO ledger_entries "
                "(user_id, coin, delta, balance_after, kind, intent_id, ref, metadata) "
                "VALUES ($1, $2, $3, $4, 'withdraw_refund', $5, $6, $7::jsonb) "
                "RETURNING id, user_id, coin, delta, balance_after, kind, "
                "intent_id, ref, metadata",
                user_id,
                coin,
                amount_d,
                new_balance,
                intent_id,
                withdrawal_id,
                _encode_metadata({"reason": reason} if reason else None),
            )
            return _row_to_ledger_entry(entry_row)


async def mark_withdrawal_broadcast(
    withdrawal_id: str,
    tx_hash: str,
) -> None:
    """Move a withdrawal from 'pending' → 'broadcast' once the tx is sent.

    No wallet mutation — funds were already reserved by
    :func:`reserve_withdrawal`.
    """
    if not pg_ledger_enabled():
        return
    pool = await get_pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE withdrawals SET status='broadcast', tx_hash=$1, updated_at=NOW() "
            "WHERE withdrawal_id=$2 AND status IN ('pending', 'approved')",
            tx_hash,
            withdrawal_id,
        )


async def mark_withdrawal_confirmed(withdrawal_id: str) -> None:
    if not pg_ledger_enabled():
        return
    pool = await get_pool()
    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE withdrawals SET status='confirmed', updated_at=NOW() "
            "WHERE withdrawal_id=$1",
            withdrawal_id,
        )


async def list_ledger(
    user_id: int,
    *,
    limit: int = 50,
    coin: Optional[str] = None,
) -> list:
    """Return the most recent ledger entries for a user."""
    pool = await get_pool()
    if pool is None:
        raise LedgerUnavailable("Postgres pool not initialised")
    async with pool.acquire() as conn:
        if coin:
            rows = await conn.fetch(
                "SELECT id, user_id, coin, delta, balance_after, kind, "
                "intent_id, ref, metadata, created_at "
                "FROM ledger_entries "
                "WHERE user_id=$1 AND coin=$2 "
                "ORDER BY created_at DESC LIMIT $3",
                user_id,
                coin,
                limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, user_id, coin, delta, balance_after, kind, "
                "intent_id, ref, metadata, created_at "
                "FROM ledger_entries "
                "WHERE user_id=$1 "
                "ORDER BY created_at DESC LIMIT $2",
                user_id,
                limit,
            )
        return [dict(r) for r in rows]


def _encode_metadata(metadata) -> str:
    """asyncpg accepts JSONB as a JSON string for the ``$N::jsonb`` cast."""
    import json
    if metadata is None or metadata == {}:
        return "{}"
    return json.dumps(metadata, default=str)


__all__ = [
    "LedgerEntry",
    "LedgerUnavailable",
    "InsufficientFunds",
    "get_balance",
    "get_all_balances",
    "adjust_balance",
    "place_bet",
    "settle_bet",
    "credit_deposit",
    "reserve_withdrawal",
    "refund_withdrawal",
    "mark_withdrawal_broadcast",
    "mark_withdrawal_confirmed",
    "list_ledger",
]
