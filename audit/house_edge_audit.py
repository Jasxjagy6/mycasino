"""Estimate the realised house edge per game from the ledger.

Compares ``sum(stake) - sum(payout)`` per game vs the declared
``HOUSE_EDGES`` table.  Useful for catching regressions in payout
math after a deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import db_pool  # noqa: E402


async def audit(days: int = 7):
    pool = await db_pool.get_pool()
    if pool is None:
        raise SystemExit("Postgres unavailable")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ref AS game_id,
                   SUM(CASE WHEN kind='bet_debit'  THEN -delta ELSE 0 END) AS stake,
                   SUM(CASE WHEN kind='bet_credit' THEN  delta ELSE 0 END) AS payout
            FROM ledger_entries
            WHERE kind IN ('bet_debit', 'bet_credit')
              AND created_at >= $1
            GROUP BY ref
            """,
            cutoff,
        )
    # Aggregate by game name (heuristic: game_id is prefixed "blackjack-G-..." etc.).
    per_game = {}
    for r in rows:
        gid = (r["game_id"] or "").lower()
        game = gid.split(":", 1)[0].split("-", 1)[0] if gid else "unknown"
        agg = per_game.setdefault(game, {"stake": 0.0, "payout": 0.0, "n": 0})
        agg["stake"] += float(r["stake"])
        agg["payout"] += float(r["payout"])
        agg["n"] += 1
    print(f"House-edge audit (last {days} days):")
    print(f"{'game':>14}  {'rounds':>8}  {'stake':>14}  {'payout':>14}  {'realised':>10}")
    for game, agg in sorted(per_game.items()):
        if agg["stake"] <= 0:
            continue
        edge = 1 - (agg["payout"] / agg["stake"])
        print(
            f"{game:>14}  {agg['n']:>8}  {agg['stake']:>14.2f}  "
            f"{agg['payout']:>14.2f}  {edge:>10.4%}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    asyncio.run(audit(args.days))


if __name__ == "__main__":  # pragma: no cover
    main()
