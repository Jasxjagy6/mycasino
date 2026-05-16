"""Verify wallet balances == SUM(ledger_entries.delta) per (user, coin).

Drift here is a real correctness bug — either the ledger missed an
entry, or a wallet got mutated outside the ledger.  Run nightly.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import db_pool  # noqa: E402


async def audit(tolerance: float = 1e-9):
    pool = await db_pool.get_pool()
    if pool is None:
        raise SystemExit("Postgres unavailable")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT w.user_id, w.coin, w.balance,
                   COALESCE((
                       SELECT SUM(delta)
                       FROM ledger_entries l
                       WHERE l.user_id = w.user_id AND l.coin = w.coin
                   ), 0) AS expected
            FROM wallets w
            """
        )
    drift = []
    for row in rows:
        diff = float(row["balance"]) - float(row["expected"])
        if abs(diff) > tolerance:
            drift.append(row)
    print(f"Wallet audit: {len(rows)} rows checked, {len(drift)} drifts")
    for row in drift[:50]:
        print(
            f"  user={row['user_id']:>12} coin={row['coin']:>6} "
            f"balance={float(row['balance']):>14.8f} "
            f"expected={float(row['expected']):>14.8f}"
        )
    return drift


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tolerance", type=float, default=1e-9)
    args = parser.parse_args()
    drift = asyncio.run(audit(args.tolerance))
    sys.exit(1 if drift else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
