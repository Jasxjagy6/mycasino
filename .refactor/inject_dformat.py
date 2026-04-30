"""Rewrite hardcoded ``${VAR:.2f}`` style amounts inside game plugin
f-strings to ``{dformat(VAR)}`` so they render in the user's display
currency.

Conservative — only matches a curated allow-list of variable names
that we *know* are USD amounts.  Anything else (crypto prices,
multipliers, percentages) is left untouched.
"""
from __future__ import annotations
import re, sys, os, ast

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Files we will rewrite.
TARGETS = [
    "plugins/games_blackjack.py",
    "plugins/games_chicken_road.py",
    "plugins/games_crash.py",  # may not exist
    "plugins/games_dice.py",
    "plugins/games_highlow.py",
    "plugins/games_keno.py",
    "plugins/games_limbo.py",
    "plugins/games_matches.py",
    "plugins/games_mines.py",
    "plugins/games_plinko.py",
    "plugins/games_roulette.py",
    "plugins/games_slots.py",
    "plugins/games_tower.py",
]

# USD-amount variable names we know about.  Add more as needed.
KNOWN_AMT_NAMES = {
    "bet_amount", "bet", "amount", "amount_usd", "wager",
    "profit", "profit_usd",
    "payout", "total_payout", "payout_usd", "winnings", "win_amount",
    "loss", "loss_usd", "lost", "lost_amount",
    "current_value", "current_amount", "current_payout",
    "potential_win", "max_payout", "min_bet", "max_bet",
    "winnings_usd", "won_amount",
    "balance_usd",
    "stake", "stake_usd",
}

# Match ``${ VAR [.attrs] [:.<digits>?<f or g>?] }`` inside f-strings.
# We allow:
#   ${bet_amount:.2f}
#   ${self.bet:.2f}
#   ${state.bet_amount:,.4f}
RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_.]*)(:[,.0-9_+f]*)?\}"
)


def replacer(match: re.Match) -> str:
    expr = match.group(1)
    spec = match.group(2) or ""
    last = expr.rsplit(".", 1)[-1]
    if last not in KNOWN_AMT_NAMES:
        return match.group(0)  # leave alone
    # Drop the format spec; dformat handles formatting.
    return f"{{dformat({expr})}}"


def ensure_import(src: str) -> str:
    if "dformat" in src:
        return src
    # Most plugins do ``from core.foundation import *`` — that already
    # pulls in dformat.  Skip explicit import if so.
    if re.search(r"from core\.foundation import \*", src):
        return src
    # Otherwise add an explicit import after the last existing core
    # import.
    return src.replace(
        "from core.foundation import",
        "from core.foundation import dformat,  # noqa: E402\nfrom core.foundation import",
        1,
    )


def main():
    total = 0
    for rel in TARGETS:
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            continue
        before = open(path).read()
        after, n = RE.subn(replacer, before)
        if n == 0:
            print(f"  {rel}: no changes")
            continue
        after = ensure_import(after)
        # AST sanity-check.
        try:
            ast.parse(after)
        except SyntaxError as e:
            print(f"  {rel}: ABORT — would break syntax: {e}")
            continue
        open(path, "w").write(after)
        print(f"  {rel}: rewrote {n} amount placeholder(s)")
        total += n
    print(f"\nTotal substitutions: {total}")


if __name__ == "__main__":
    main()
