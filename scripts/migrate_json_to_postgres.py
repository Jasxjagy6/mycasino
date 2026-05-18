"""Backfill: copy every ``data/users/*.json`` into Postgres.

Run once after pointing the bot at a Postgres instance.  Safe to run
multiple times — uses ``ON CONFLICT (user_id) DO UPDATE`` so re-running
overwrites stale rows with the JSON state.

Usage::

    POSTGRES_URL=postgresql://user:pass@host/db \
    MYCASINO_PG_LEDGER=1 \
    python -m scripts.migrate_json_to_postgres
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Dict

# Make ``core/*`` importable without installing the package.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import db_pool, persistence_backend, wallet_ledger  # noqa: E402

logger = logging.getLogger(__name__)


async def migrate(dry_run: bool = False, limit: int = 0) -> Dict[str, int]:
    pool = await db_pool.get_pool()
    if pool is None:
        raise RuntimeError(
            "Postgres pool unavailable — set POSTGRES_URL (and optionally "
            "MYCASINO_PG_LEDGER=1)."
        )
    # Bring the schema online.
    await db_pool.run_migrations()
    data_dir = persistence_backend.data_dir()
    if not data_dir.exists():
        raise RuntimeError(f"Data dir not found: {data_dir}")
    files = sorted(data_dir.glob("*.json"))
    if limit > 0:
        files = files[:limit]
    stats = {"scanned": 0, "user_state_writes": 0, "wallet_rows": 0, "skipped": 0}
    for path in files:
        stats["scanned"] += 1
        try:
            uid = int(path.stem)
        except ValueError:
            stats["skipped"] += 1
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read %s", path)
            stats["skipped"] += 1
            continue
        if dry_run:
            continue
        # 1. Save the full state blob to the user_state table.
        await persistence_backend.save(uid, data)
        stats["user_state_writes"] += 1
        # 2. Seed the wallet rows so SELECT...FOR UPDATE has something
        #    to lock.  We use intent_id="migration_seed:<uid>:<coin>"
        #    so re-running the migration never double-credits.
        wallet = data.get("wallet")
        if isinstance(wallet, dict):
            balances = wallet
        elif isinstance(wallet, (int, float)):
            balances = {"USDT": float(wallet)}
        else:
            balances = {}
        for coin, value in balances.items():
            try:
                amount = Decimal(str(value))
            except Exception:
                continue
            if amount <= 0:
                continue
            try:
                await wallet_ledger.adjust_balance(
                    uid,
                    coin,
                    amount,
                    kind="migration_seed",
                    intent_id=f"migration_seed:{uid}:{coin}",
                    ref="json_backfill",
                    metadata={"source": str(path.name)},
                )
                stats["wallet_rows"] += 1
            except wallet_ledger.LedgerUnavailable:
                logger.warning(
                    "wallet_ledger unavailable — skipping seed for %s/%s",
                    uid,
                    coin,
                )
            except Exception:
                logger.exception(
                    "Failed to seed wallet for %s coin %s", uid, coin
                )
    return stats


async def _amain():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    logging.basicConfig(
        level=os.environ.get("MYCASINO_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stats = await migrate(dry_run=args.dry_run, limit=args.limit)
    print("Migration stats:")
    for k, v in stats.items():
        print(f"  {k:>20} : {v}")


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":  # pragma: no cover
    main()
