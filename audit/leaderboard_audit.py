"""Cross-check Redis leaderboard sorted-sets against the ledger.

The leaderboard ZSET is a *hot* counter that workers increment on
every bet.  This script rebuilds the same counts straight out of
``ledger_entries`` for the active period and reports any drift.

Run::

    POSTGRES_URL=... MYCASINO_REDIS_URL=... python -m audit.leaderboard_audit weekly wagered
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

from core import db_pool, redis_backend  # noqa: E402


PERIOD_TO_INTERVAL = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "alltime": None,
}

METRIC_TO_KIND = {
    "wagered": ("bet_debit", lambda delta: -float(delta)),
    "won": ("bet_credit", lambda delta: float(delta)),
}


async def audit(period: str, metric: str, *, tolerance: float = 0.01):
    if period not in PERIOD_TO_INTERVAL:
        raise SystemExit(f"unknown period: {period}")
    if metric not in METRIC_TO_KIND:
        raise SystemExit(f"unknown metric: {metric}")
    kind, sign = METRIC_TO_KIND[metric]
    interval = PERIOD_TO_INTERVAL[period]
    pool = await db_pool.get_pool()
    if pool is None:
        raise SystemExit("Postgres unavailable")
    cutoff = None if interval is None else datetime.now(timezone.utc) - interval
    async with pool.acquire() as conn:
        if cutoff is None:
            rows = await conn.fetch(
                "SELECT user_id, SUM(delta) AS total FROM ledger_entries "
                "WHERE kind=$1 GROUP BY user_id",
                kind,
            )
        else:
            rows = await conn.fetch(
                "SELECT user_id, SUM(delta) AS total FROM ledger_entries "
                "WHERE kind=$1 AND created_at >= $2 GROUP BY user_id",
                kind,
                cutoff,
            )
    expected = {int(r["user_id"]): sign(r["total"]) for r in rows}

    cli = await redis_backend.get_client()
    if cli is None:
        raise SystemExit("Redis unavailable")
    key = f"mycasino:lb:{period}:{metric}"
    raw = await cli.zrange(key, 0, -1, withscores=True)
    actual = {int(uid): float(score) for uid, score in raw}

    all_users = set(expected) | set(actual)
    drift_rows = []
    for uid in sorted(all_users):
        exp = expected.get(uid, 0.0)
        act = actual.get(uid, 0.0)
        diff = act - exp
        if abs(diff) > tolerance:
            drift_rows.append((uid, exp, act, diff))
    print(f"Audit  period={period} metric={metric} kind={kind}")
    print(f"  expected entries: {len(expected)}")
    print(f"  redis entries   : {len(actual)}")
    print(f"  drift > {tolerance}: {len(drift_rows)}")
    for row in drift_rows[:50]:
        uid, exp, act, diff = row
        print(f"    user={uid:>12} expected={exp:>14.4f} redis={act:>14.4f} diff={diff:+.4f}")
    return drift_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("period", choices=list(PERIOD_TO_INTERVAL))
    parser.add_argument("metric", choices=list(METRIC_TO_KIND))
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args()
    drift = asyncio.run(audit(args.period, args.metric, tolerance=args.tolerance))
    sys.exit(1 if drift else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
