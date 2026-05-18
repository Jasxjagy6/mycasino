"""Rakeback / VIP / jackpot audit.

Recomputes the expected rakeback for every user from the ledger and
compares against what we actually paid out.  Drift here usually points
at a misconfigured rakeback rate per VIP tier.
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


# Default tier → rakeback rate.  Override via CLI if your VIP table differs.
DEFAULT_TIER_RATES = {
    "bronze": 0.001,
    "silver": 0.002,
    "gold": 0.003,
    "platinum": 0.005,
    "diamond": 0.01,
}


async def audit(default_rate: float = 0.001, tolerance: float = 0.01):
    pool = await db_pool.get_pool()
    if pool is None:
        raise SystemExit("Postgres unavailable")
    async with pool.acquire() as conn:
        # Total wager per user.
        wagered = {
            int(r["user_id"]): float(-r["total"])
            for r in await conn.fetch(
                "SELECT user_id, SUM(delta) AS total FROM ledger_entries "
                "WHERE kind='bet_debit' GROUP BY user_id"
            )
        }
        # Total rakeback paid out.
        paid = {
            int(r["user_id"]): float(r["total"])
            for r in await conn.fetch(
                "SELECT user_id, SUM(delta) AS total FROM ledger_entries "
                "WHERE kind IN ('rakeback', 'vip_bonus') GROUP BY user_id"
            )
        }
    drift = []
    for uid, w in wagered.items():
        # Rough expected — caller can override with a tier lookup script.
        expected = w * default_rate
        actual = paid.get(uid, 0.0)
        if abs(actual - expected) > tolerance:
            drift.append((uid, expected, actual, actual - expected))
    print(f"Rakeback audit: users={len(wagered)} drifts={len(drift)} (rate={default_rate})")
    for uid, exp, act, diff in drift[:50]:
        print(f"  user={uid:>12} expected={exp:>14.4f} paid={act:>14.4f} diff={diff:+.4f}")
    return drift


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--default-rate", type=float, default=0.001)
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args()
    drift = asyncio.run(audit(args.default_rate, args.tolerance))
    sys.exit(1 if drift else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
