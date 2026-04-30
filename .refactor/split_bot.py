"""Programmatically split bot.py into core/* + plugins/*.

Strategy
--------

* Every top-level Import / Assign / If / Try / Expr / class-of-state from bot.py
  is preserved IN ORDER inside ``core/foundation.py`` — that becomes the
  shared "runtime namespace" that every other module pulls in via
  ``from core.foundation import *``.

* Top-level function definitions are bucketed into target modules
  (per-game plugins, per-area core modules) by name pattern.  Each
  bucket gets its own file with:

    1. ``from __future__ import annotations``
    2. ``from core.foundation import *  # noqa: F401, F403``
    3. The full source text of every function in the bucket, in
       original line order.
    4. For plugin buckets: a ``register(ctx)`` function that calls
       ``ctx.add_handler(...)`` for every handler from main()'s
       original ``add_handler`` list whose callback is in this
       bucket.

* The ``main()`` function and the ``if __name__`` guard are moved to
  ``core/foundation.py`` (so behaviour is preserved when running
  ``python -m core.foundation`` or via the new thin bot.py launcher
  that just calls ``foundation.main()``).

* The replacement ``bot.py`` is ~80 lines: imports foundation,
  registers the runtime, autoloads plugins, runs main().

Re-running the script is idempotent — destination files are
overwritten.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
BOT = ROOT / "bot.py"
SRC = BOT.read_text()
LINES = SRC.split("\n")
TREE = ast.parse(SRC)


# ---------------------------------------------------------------------------
# Categorisation rules: first match wins.
# ---------------------------------------------------------------------------

RULES: List[Tuple[str, str]] = [
    # ----- Per-game plugins ------------------------------------------------
    (r'^_bj_|^bj_|blackjack|bjsplit|create_deck|calculate_hand_value|format_hand|can_split_hand|_play_next_split_hand|_resolve_split_game|handle_dealer_turn|^get_card_name$', 'plugins.games_blackjack'),
    (r'^slots?_|^sl_command|^spin_', 'plugins.games_slots'),
    (r'^roulette_|^roul_|get_roulette_number_emoji|create_roulette_menu_keyboard|create_roulette_number_selection_keyboard', 'plugins.games_roulette'),
    (r'^(dice_rush|rainbow_rush|blaze_rush|dice_roll|coin_flip)|_dr_get_font|_send_dice_rush_help|_play_classic_rush|_play_odd_even_rush|_play_high_low_rush|_play_rainbow_rush|_play_blaze_rush', 'plugins.games_dice'),
    (r'^mines_|^_mines_|generate_mine_positions|get_mines_multiplier', 'plugins.games_mines'),
    (r'^tower_|^_tower_|build_tower_keyboard|create_tower_floor_keyboard|create_tower_game_visual|handle_tower_pick|handle_tower_cashout|create_revealed_floor_keyboard|generate_tower_positions', 'plugins.games_tower'),
    (r'^limbo_|^_limbo_|get_limbo_multiplier', 'plugins.games_limbo'),
    (r'^keno_|^_keno_|generate_keno_numbers|create_keno_keyboard|get_keno_payout_text', 'plugins.games_keno'),
    (r'^highlow_|^hilow_|^_hilow_|^hl_command|calculate_highlow_multiplier', 'plugins.games_highlow'),
    (r'^matches_|^_matches_|^deals_|extract_game_name|get_user_active_emoji_game|show_emoji_game_setup|_build_emoji_setup_ui|_start_pvb_from_setup|create_reply_pvp_challenge|create_reply_pvp_challenge_xdxw|parse_xdxw_format|create_xdxw_challenge|play_single_emoji_game|create_group_challenge|execute_group_challenge_game|play_vs_bot_game|single_emoji_bet_handler|^_cancel_pvp_timeout_jobs|pvp_timeout_warn_job|pvp_timeout_finish_job|_cancel_pvb_timeout_jobs|pvb_timeout_warn_job|pvb_timeout_finish_job', 'plugins.games_matches'),
    (r'^plinko_|^_plinko_|^plinko\b|_get_plinko_web_url|_validate_telegram_webapp_data|get_plinko_slot_result', 'plugins.games_plinko'),
    (r'^chicken_road|chickenroad|_chicken_road_|_cr_|^cr_api|^cr_serve|^cr_health|_build_chicken_road_mult_table|get_chicken_road_crash_step|get_chicken_road_multiplier|_get_chicken_road_web_url', 'plugins.games_chicken_road'),
    # ----- Other plugins ---------------------------------------------------
    (r'^jackpot_|^_jackpot_|^jackpot$', 'plugins.jackpot'),
    (r'^raffle_|^raffles_|^_raffle_|monitor_raffles_task', 'plugins.raffle'),
    (r'^(tip|rain|balance|bal)_command$|tip_callback|rain_callback|_build_rain_message|finalize_rain_job', 'plugins.wallet_commands'),
    (r'^leaderboard_|^lb_command|^_leaderboard_|_flush_leaderboard_buffer|update_leaderboards|_update_leaderboard_entry|_update_highest_wins', 'plugins.leaderboard'),
    (r'^referral_|^setcode_|^code_command|^_referral|process_referral_commission|generate_unique_referral_code', 'plugins.referral'),
    (r'^(ai_|perplexity_|g4f_|_ai_|process_ai_request)', 'plugins.ai_features'),
    (r'^(vip_|_vip_|weekly_|monthly_|^bonus_|claim_)|calculate_all_user_bonuses|send_admin_bonus_notification|check_and_send_bonus_notification', 'plugins.bonus'),
    (r'^(start_command|help_command|info_command|users_command|stats_command|user_info_command|main_menu|whoami|p_command|price_command|continue_command|cancel_all_command|active_games|games_menu|more_menu|send_users_page|send_active_games_page)', 'plugins.general'),
    (r'^auto_accept_join_request', 'plugins.general'),
    (r'^(ban_user|unban_user|tempban_user|untempban_user|kick_command|promote_command|pin_command|purge_command|clear_command|clearall_command|timeout_command|stop_command|resume_command|cancel_command|cashout_command)', 'plugins.admin_commands'),
    (r'^admin_|display_admin_user_panel|broadcast|gift_code|^gift_', 'plugins.admin_commands'),
    (r'^(check_banned|check_maintenance|is_game_enabled|game_off|game_on|game_status|maintenance_)', 'plugins.admin_commands'),
    (r'^(setting|settings_|set_|toggle_)', 'plugins.admin_commands'),
    (r'^(escrow_|handle_escrow|create_and_finalize_escrow|monitor_escrow|release_escrow|generate_verification_code)', 'plugins.escrow'),
    (r'^(predict_command|cashout_command|recover_token_step|hash_pin|is_valid_bep20_address|change_withdrawal_address_step|process_withdrawal_amount|handle_provably_fair_deep_link)', 'plugins.account'),
    # ----- Core support modules -------------------------------------------
    (r'^(deposit|withdraw|oxapay|hot_wallet|sweep|consolidate|build_deposit_menu|check_deposit_status|back_to_deposit_menu|verify_oxapay_signature|_load_oxapay|_save_oxapay)', 'core.deposits'),
    (r'^(DepositDatabase|OxaPayService|HDWalletManager|EvmService|TronService|SolanaService|TonService|BlockMonitor|AutoSweeper)$', 'core.deposits'),
    (r'^(credit_wallet|deduct_wallet|ensure_wallet|get_active_balance|get_total_balance|get_active_currency|format_crypto|calculate_bet_deduction|deduct_wallet_safe|credit_wallet_safe|credit_wallet_crypto|format_balance_with_locked|get_locked_balance_in_games|send_insufficient_balance_message|ensure_user_in_wallets|reduce_unwagered_amounts|calculate_required_wager|update_stats_on_bet|update_stats_on_withdrawal|update_stats_on_tip_received|update_stats_on_tip_sent|update_stats_on_rain_received|update_pnl|get_user_tier|check_username_bonus|apply_username_bonus|get_username_bonus_guidance|_show_wallet_history|_show_wallet_transactions|check_bet_limits|validate_bet_amount|check_withdrawal_limit|get_all_registered_user_ids)', 'core.wallet'),
    (r'^(load_language_files|get_user_language|^pe$|^peb$|^get_text$|set_user_language|get_user_lang)', 'core.i18n'),
    (r'^(render_|_render_|dashboard_image|create_dashboard|generate_.*_image|_game_template_background|_get_cached_profile_picture|create_circular_mask|get_user_profile_picture|get_display_name|_resolve_dashboard_font|_paste_avatar_in_circle|_bj_round_rect|_bj_get_font|_bj_draw_card|_bj_draw_hidden_card|_bj_parse_card|create_progress_bar)', 'core.dashboards'),
    (r'^(save|load)_.*data$|^_sync_write_user|^_flush_dirty_users|^_sync_save_bot_state|^save_bot_state|^load_bot_state|^_flush_bot_state|^load_all_escrow_deals|^save_escrow_deal|^save_all_escrow_deals|^save_group_settings|^load_all_group_settings|^save_all_group_settings|^save_gift_code|^load_all_gift_codes|^save_all_gift_codes', 'core.persistence'),
    (r'^max_bet|_max_bet|dynamic_max', 'core.max_bets'),
    (r'^(achievement|_achievement|check_and_award_achievement|check_achievement)', 'core.achievements'),
    (r'^(level_|_level_|get_user_level|get_level|xp_|check_and_award_level_up|_flatten_levels|_get_total_wager|_current_and_next_level|_progress_bar)', 'core.levels'),
    (r'^(get_crypto_price|update_live_prices|update_live_fiat_rates|_get_http|_get_httpx|create_optional_rate)', 'core.helpers'),
    (r'^(_index_user|_unindex_user|_get_user_active|_get_wallet_lock|_get_game_lock|_get_withdrawal|_get_raffle|_acquire|_release|_check_user_action_flood|_rebuild_)', 'core.helpers'),
    (r'^(is_admin$|^get_privacy_display_name$|safe_send_message|safe_edit_message|smart_rate_limit|smart_roll|multi_roll_parallel|_secure_choice|_secure_shuffle|_secure_randint|_secure_choices|generate_server_seed|generate_client_seed|generate_game_client_seed|generate_unique_id|create_hash|get_provably_fair_result|get_user_seeds|increment_user_nonce|store_provably_fair_record|create_provably_fair_button|normalize_username|display_at|check_menu_ownership|get_user_currency|get_display_currency|_rate_usd_to|convert_usd_to_display|convert_display_to_usd|convert_currency|convert_to_usd|_decimal_places|format_compact|format_display_amount|format_for_user|format_currency|format_compact_usd|format_compact_for_user|parse_bet_amount|active_scans_monitor_task|_event_loop_watchdog|on_bot_shutdown|_cleanup_inflight_callbacks|_cleanup_rate_limit_timestamps|_cleanup_profile_pic_cache|_cleanup_menu_owners|_cleanup_game_sessions|_cleanup_user_cache|_concurrency_middleware|_get_env_or_default|apply_button_style|create_styled_keyboard|_check_and_prompt_helper_bots|_get_cached_wagered_rank|_invalidate_leaderboard_cache|get_bot_username|get_working_web3_bsc|message_listener|ensure_user_in_wallets_sync|_build_history_keyboard|_show_games_history_page|generate_surprise_code)', 'core.helpers'),
    (r'^(post_init|_auto_start|_init_helper|run_bots|_signal|stop_bot|main$)', 'core.bootstrap'),
    # Catch-alls — anything still uncategorised goes to a sensible bucket.
    (r'_command$', 'plugins.general'),
    (r'_callback$', 'plugins.general'),
]


def categorise(name: str) -> str:
    for pat, target in RULES:
        if re.search(pat, name):
            return target
    return 'core.misc'


# ---------------------------------------------------------------------------
# Walk bot.py top-level: build buckets.
# ---------------------------------------------------------------------------

def get_source(node: ast.AST) -> str:
    """Return the original source text of a top-level node, including
    its full decorator/header/body, preserving exact indentation and
    trailing newlines."""
    start = node.lineno - 1
    end = node.end_lineno
    # Include any ``@decorator`` lines that immediately precede the def
    # (they're part of node.decorator_list in AST but their lineno is
    # the @-line so this already works for decorated funcs).
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if node.decorator_list:
            start = min(node.decorator_list[0].lineno, node.lineno) - 1
    return "\n".join(LINES[start:end])


# Identify functions/classes that are CALLED from module-level code in
# the original bot.py.  Those MUST stay in foundation because they run
# during foundation's import (otherwise we'd have a NameError when the
# foundation module body tries to call them).
TOP_DEF_NAMES = {
    n.name for n in TREE.body
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
}
KEEP_IN_FOUNDATION: set = set()
# Also keep the `main()` function itself in foundation so the launcher
# can call ``foundation.main()`` directly.
KEEP_IN_FOUNDATION.add("main")

# Compute transitive closure of "what is reachable from module-level code
# BEFORE main() runs": these MUST stay in foundation otherwise the
# foundation module body will NameError on import.
_defs_by_name = {
    n.name: n for n in TREE.body
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
}

def _refs_within(node: ast.AST) -> set:
    """All top-level def names referenced anywhere in this AST."""
    return {
        sub.id for sub in ast.walk(node)
        if isinstance(sub, ast.Name) and sub.id in _defs_by_name
    }

_seeds: set = set()
for _n in TREE.body:
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        continue
    _seeds |= _refs_within(_n)

# Closure over CALLS made by reachable functions: a function passed as
# a value (e.g. atexit.register(f)) is in seeds; what f *itself* calls
# must also be reachable.  We use the call-graph because Name references
# inside a function don't actually need that name to exist at import
# time, only at *call* time -- but call time is after wireup() runs, so
# names from split modules are fine.  EXCEPT: anything that f calls at
# its own module-level (which doesn't exist for non-classes), so just
# CALLS suffice.
def _calls_within(node: ast.AST) -> set:
    return {
        sub.func.id for sub in ast.walk(node)
        if isinstance(sub, ast.Call)
        and isinstance(sub.func, ast.Name)
        and sub.func.id in _defs_by_name
    }

# Direct module-level calls (not just references) bring in transitive
# CALLS because they execute now.  References that AREN'T calls (e.g.
# atexit.register(f), passing f as a callback) don't need transitive
# resolution at import time -- only the name itself must be defined.
_module_level_calls: set = set()
for _n in TREE.body:
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        continue
    for _sub in ast.walk(_n):
        if (
            isinstance(_sub, ast.Call)
            and isinstance(_sub.func, ast.Name)
            and _sub.func.id in _defs_by_name
            and _sub.func.id != "main"
        ):
            _module_level_calls.add(_sub.func.id)

_queue = list(_module_level_calls)
_visited = set(_module_level_calls)
while _queue:
    _cur = _queue.pop()
    if _cur not in _defs_by_name:
        continue
    _new = _calls_within(_defs_by_name[_cur]) - _visited - {"main"}
    _visited |= _new
    _queue.extend(_new)

# Foundation must contain:
#   - every name referenced from module-level code (so the bare name
#     resolves at module body execution -- e.g. atexit.register(f)),
#   - the transitive *call* closure of names directly *called* at module
#     level (so those calls don't NameError),
#   - main() and its bootstrap helpers (kept by name below).
KEEP_IN_FOUNDATION |= _seeds
KEEP_IN_FOUNDATION |= _visited

# Any function used as a DECORATOR on a top-level def runs at module-
# import time of any module that contains a decorated function -- so it
# MUST be in foundation (decorators are resolved before _wireup runs).
for _n in TREE.body:
    if not isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        continue
    for _dec in _n.decorator_list:
        if isinstance(_dec, ast.Name) and _dec.id in _defs_by_name:
            KEEP_IN_FOUNDATION.add(_dec.id)
        elif isinstance(_dec, ast.Call) and isinstance(_dec.func, ast.Name) and _dec.func.id in _defs_by_name:
            KEEP_IN_FOUNDATION.add(_dec.func.id)
# And the transitive call closure of those decorators (they invoke
# helpers when the decorated function is called -- but decorator BODIES
# also reference internal helpers at definition time).
_dec_seeds = {n for n in KEEP_IN_FOUNDATION if n in _defs_by_name}
_q2 = list(_dec_seeds)
_v2 = set(_dec_seeds)
while _q2:
    _c2 = _q2.pop()
    if _c2 not in _defs_by_name:
        continue
    _new2 = _calls_within(_defs_by_name[_c2]) - _v2 - {"main"}
    _v2 |= _new2
    _q2.extend(_new2)
KEEP_IN_FOUNDATION |= _v2
# Bootstrap helpers main() calls directly need to stay co-resident with
# main() because they reference module-level state heavily.
KEEP_IN_FOUNDATION.update({
    "post_init", "_auto_start_helper_bots", "_init_helper_bot",
    "_signal_handler", "_event_loop_watchdog", "on_bot_shutdown",
    "_cleanup_inflight_callbacks", "_cleanup_rate_limit_timestamps",
    "_cleanup_profile_pic_cache", "_cleanup_menu_owners",
    "_cleanup_game_sessions", "_cleanup_user_cache",
    "active_scans_monitor_task", "monitor_raffles_task",
    "_check_and_prompt_helper_bots", "create_optional_rate_limiter",
    "stop_bot",
})


buckets: Dict[str, List[ast.AST]] = {}
foundation_nodes: List[ast.AST] = []

for node in TREE.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # Functions referenced by module-level code stay in foundation.
        if isinstance(node, ast.ClassDef) and node.name in KEEP_IN_FOUNDATION:
            foundation_nodes.append(node)
            continue
        if not isinstance(node, ast.ClassDef) and node.name in KEEP_IN_FOUNDATION:
            foundation_nodes.append(node)
            continue
        # Otherwise route to a split bucket.
        target = categorise(node.name)
        buckets.setdefault(target, []).append(node)
    elif isinstance(node, ast.If):
        # Only the very last ``if __name__ == "__main__":`` is dropped —
        # everything else (e.g. ``if SOLANA_AVAILABLE: ...``) is module
        # state and stays in foundation.
        is_main_guard = (
            isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        )
        if is_main_guard:
            continue
        foundation_nodes.append(node)
    else:
        foundation_nodes.append(node)


# ---------------------------------------------------------------------------
# Map handler add_handler() callbacks back to function names so we can
# emit per-plugin register() functions automatically.
# ---------------------------------------------------------------------------

main_node: Optional[ast.FunctionDef] = None
for n in TREE.body:
    if isinstance(n, ast.FunctionDef) and n.name == "main":
        main_node = n
        break

# Map name -> bucket so register() emitter knows what stays where.
name_to_bucket: Dict[str, str] = {}
for bucket, nodes in buckets.items():
    for n in nodes:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name_to_bucket[n.name] = bucket


# ---------------------------------------------------------------------------
# Foundation module: imports + module-level state + helpers used by every
# bucket.  We build it as the original lines for those nodes, in order,
# so module-level statements still execute exactly once on import.
# ---------------------------------------------------------------------------

def write_foundation(out: Path) -> None:
    parts: List[str] = [
        '"""Shared casino runtime: imports, configuration, module-level state.\n',
        'This module is the single source of truth for everything that the',
        'split casino plugins need to run.  Every other module under',
        '``core/`` and ``plugins/`` does ``from core.foundation import *``',
        'to share this namespace.',
        '',
        'It is auto-generated from bot.py by .refactor/split_bot.py — do',
        'NOT edit the imports or module-level state here unless you also',
        'rerun the splitter.',
        '"""',
        "",
    ]
    for node in foundation_nodes:
        parts.append(get_source(node))
        parts.append("")  # blank line separator

    # Foundation also re-exports every function/class in the buckets so
    # cross-bucket calls (e.g. blackjack calling credit_wallet from
    # core.wallet) work via the simple ``from core.foundation import *``
    # idiom every plugin uses.
    parts.append("\n# === re-exports of every split function/class follow ===\n")
    for bucket in sorted(buckets):
        # Late re-import is fine; foundation imports happen lazily inside
        # a function so we don't introduce cycles at import time.
        parts.append(f"# from {bucket} import *  # late-bound below")

    # Order modules by tier: core modules first (so plugin decorators
    # like @check_banned can resolve), then plugins.
    core_mods = sorted(b for b in buckets if b.startswith("core."))
    plugin_mods = sorted(b for b in buckets if b.startswith("plugins."))
    ordered = core_mods + plugin_mods

    parts.append(
        "\n\n# Auto-generated by .refactor/split_bot.py: ordered list of split modules.\n"
        f"_SPLIT_MODULES = {ordered!r}\n"
        "\n"
        "def _wireup() -> None:\n"
        "    \"\"\"Wire all split modules together via this foundation namespace.\n"
        "\n"
        "    The casino was originally a single 39k-line bot.py.  After\n"
        "    splitting into per-feature files, each split module's\n"
        "    ``from core.foundation import *`` snapshots foundation at import\n"
        "    time -- so a module imported earlier cannot see names defined in\n"
        "    a module imported later.\n"
        "\n"
        "    Strategy:\n"
        "\n"
        "    1. Import each module IN ORDER (core.* before plugins.*).  After\n"
        "       each import, hoist that module's public names into foundation,\n"
        "       so the NEXT module's ``from core.foundation import *`` already\n"
        "       sees the previous module's symbols.  This handles class-body\n"
        "       and decorator-time references like ``@check_banned``.\n"
        "    2. After every module is loaded, push the FULL merged namespace\n"
        "       back into every split module's __dict__ so cross-module\n"
        "       function calls resolve at call time too.\n"
        "    \"\"\"\n"
        "    import importlib, logging as _logging\n"
        "    log = _logging.getLogger(__name__)\n"
        "    g = globals()\n"
        "    mods = []\n"
        "    for mn in _SPLIT_MODULES:\n"
        "        try:\n"
        "            mod = importlib.import_module(mn)\n"
        "        except Exception as e:\n"
        "            log.warning('Failed to import split module %s: %s', mn, e, exc_info=True)\n"
        "            continue\n"
        "        mods.append(mod)\n"
        "        # Hoist this module's public names into foundation IMMEDIATELY\n"
        "        # so the next split module sees them via ``from core.foundation import *``.\n"
        "        for k in dir(mod):\n"
        "            if k.startswith('_'):\n"
        "                continue\n"
        "            g[k] = getattr(mod, k)\n"
        "    # Push the fully-merged namespace back into every module so that\n"
        "    # late-bound references (function bodies that resolve names at\n"
        "    # call time) succeed across module boundaries.\n"
        "    snapshot = {k: v for k, v in g.items() if not k.startswith('_')}\n"
        "    for mod in mods:\n"
        "        for k, v in snapshot.items():\n"
        "            if k not in mod.__dict__:\n"
        "                mod.__dict__[k] = v\n"
        "    log.info('Foundation wireup complete: %d modules, %d names', len(mods), len(snapshot))\n"
    )

    out.write_text("\n".join(parts) + "\n")


# ---------------------------------------------------------------------------
# Per-bucket files.
# ---------------------------------------------------------------------------

def render_bucket(bucket: str, nodes: List[ast.AST]) -> str:
    parts: List[str] = []
    is_plugin = bucket.startswith("plugins.")
    parts.append(f'"""Auto-split from bot.py — {bucket}."""')
    parts.append("from __future__ import annotations")
    parts.append("from core.foundation import *  # noqa: F401, F403")
    parts.append("")
    # Function bodies in original line order.
    nodes_sorted = sorted(nodes, key=lambda n: n.lineno)
    for n in nodes_sorted:
        parts.append(get_source(n))
        parts.append("")

    if is_plugin:
        parts.append(_render_register_for(bucket, nodes_sorted))

    return "\n".join(parts) + "\n"


def _render_register_for(bucket: str, nodes: List[ast.AST]) -> str:
    """Generate a register(ctx) for a plugin bucket using the
    add_handler() calls from main() that reference functions in this
    bucket."""
    if main_node is None:
        return "def register(ctx):\n    pass\n"

    bucket_names = {
        n.name for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    relevant: List[Tuple[int, str]] = []
    for stmt in ast.walk(main_node):
        if not (isinstance(stmt, ast.Call) and isinstance(stmt.func, ast.Attribute) and stmt.func.attr == "add_handler"):
            continue
        if not stmt.args:
            continue
        inner = stmt.args[0]
        if not isinstance(inner, ast.Call) or not isinstance(inner.func, ast.Name):
            continue
        # Walk the handler-construction args looking for Name() callbacks
        callbacks: List[str] = []
        for a in list(inner.args) + [kw.value for kw in inner.keywords]:
            for sub in ast.walk(a):
                if isinstance(sub, ast.Name) and sub.id in name_to_bucket:
                    callbacks.append(sub.id)
        if any(cb in bucket_names for cb in callbacks):
            relevant.append((stmt.lineno, ast.unparse(stmt)))

    if not relevant:
        return (
            "def register(ctx):\n"
            "    \"\"\"No main() add_handler entries reference this bucket.\n"
            "    Plugin still loads so its admin hooks work.\"\"\"\n"
            "    return None\n"
        )

    body = ["def register(ctx):"]
    body.append('    """Auto-generated from main()\'s add_handler list."""')
    body.append("    app = ctx.application")
    seen = set()
    for ln, src in sorted(relevant):
        if src in seen:
            continue
        seen.add(src)
        # rewrite "app.add_handler(" → keep as is since we set app = ctx.application
        body.append("    " + src)
    return "\n".join(body) + "\n"


# ---------------------------------------------------------------------------
# Run.
# ---------------------------------------------------------------------------

def main() -> None:
    out_root = ROOT
    (out_root / "core").mkdir(exist_ok=True)
    (out_root / "plugins").mkdir(exist_ok=True)

    # Foundation
    write_foundation(out_root / "core" / "foundation.py")

    # core/__init__.py + plugins/__init__.py if not present
    init_core = out_root / "core" / "__init__.py"
    if not init_core.exists():
        init_core.write_text('"""mycasino core package."""\n')
    init_plugins = out_root / "plugins" / "__init__.py"
    # We KEEP the existing plugins/__init__.py — it has the plugin docstring.

    summary: Dict[str, int] = {}
    for bucket, nodes in sorted(buckets.items()):
        # 'plugins.foo' -> plugins/foo.py ; 'core.foo' -> core/foo.py
        pkg, _, mod = bucket.partition(".")
        target_dir = out_root / pkg
        target_dir.mkdir(exist_ok=True)
        target_file = target_dir / f"{mod}.py"
        target_file.write_text(render_bucket(bucket, nodes))
        summary[bucket] = sum(
            1 for n in nodes
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        )

    # Drop the old example_*.py files since the user explicitly hates them.
    for f in (out_root / "plugins").glob("example_*.py"):
        f.unlink()

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
