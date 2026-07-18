"""Auto-split from bot.py — core.misc."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def load_user_data_if_missing(user_id: int):
    """Load a user's data from disk into memory if not already present.

    Prevents silent deposit loss after bot restarts where users are not yet
    in the in-memory ``user_stats``/``user_wallets`` dicts.
    """
    if user_id in user_stats:
        return  # Already loaded — nothing to do
    fpath = os.path.join(DATA_DIR, f"{user_id}.json")
    if not os.path.exists(fpath):
        return  # No file yet — new user
    try:
        with open(fpath, "r") as f:
            data = json.load(f)
        raw_wallet = data.get("wallet", 0.0)
        if isinstance(raw_wallet, (int, float)):
            user_wallets[user_id] = {"USDT": float(raw_wallet)}
        elif isinstance(raw_wallet, dict):
            clean_wallet = {}
            for k, v in raw_wallet.items():
                try:
                    clean_wallet[k] = float(v)
                except (TypeError, ValueError):
                    logging.warning(f"load_user_data_if_missing: invalid wallet value for user {user_id}, coin {k}: {v}")
            user_wallets[user_id] = clean_wallet if clean_wallet else {"USDT": 0.0}
        else:
            user_wallets[user_id] = {"USDT": 0.0}
        if "active_currency" not in data:
            data["active_currency"] = "USDT"
        user_stats[user_id] = data
        logging.info(f"load_user_data_if_missing: loaded user {user_id} from disk")
    except Exception as e:
        logging.error(f"load_user_data_if_missing: failed to load user {user_id}: {e}")

async def async_generate_bj_image(*args, **kwargs) -> BytesIO:
    """Async wrapper for generate_bj_image to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_image_executor, lambda: generate_bj_image(*args, **kwargs))

async def async_generate_dice_rush_image() -> BytesIO:
    """Async wrapper for generate_dice_rush_image to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_image_executor, lambda: generate_dice_rush_image())

async def async_generate_limbo_image(*args, **kwargs) -> BytesIO:
    """Async wrapper for generate_limbo_image to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_image_executor, lambda: generate_limbo_image(*args, **kwargs))

async def start_tower_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new tower game with selected difficulty"""
    query = update.callback_query
    user = query.from_user

    bet_amount = context.user_data.get('tower_bet_amount')
    difficulty = context.user_data.get('tower_difficulty', 'medium')

    if not bet_amount:
        await query.answer("Error: Bet amount not set!", show_alert=True)
        return

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await query.answer("Insufficient balance.", show_alert=True)
        return
    save_user_data(user.id)

    # Use user's provably fair seeds with fresh game client seed (like mines)
    # This ensures each game has unique, unpredictable seeds
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)  # Increment nonce to ensure unique results per game

    # Generate fresh client seed for this specific game
    game_client_seed = generate_game_client_seed()

    # Generate tower configuration - 9 floors using deterministic positions
    tiles_per_floor = TOWER_DIFFICULTY_CONFIG[difficulty]['tiles']
    tower_config = generate_tower_positions(seeds["server_seed"], game_client_seed, current_nonce, difficulty, 9)

    # Create game session
    game_id = generate_unique_id("TW")
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "tower",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "difficulty": difficulty,
        "tiles_per_floor": tiles_per_floor,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "tower_config": tower_config,
        "current_floor": 0,
        "selected_tiles": [],  # Track which tiles were selected
        "server_seed": seeds["server_seed"],
        "client_seed": game_client_seed,
        "nonce": current_nonce
    }

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    # Clear setup data
    context.user_data.pop('tower_bet_amount', None)
    context.user_data.pop('tower_difficulty', None)

    # Build the tower keyboard (replaces text visual + old keyboard)
    keyboard = build_tower_keyboard(game_sessions[game_id])

    await query.edit_message_text(
        f"{pe('tower')} <b>Tower Climb</b>\n"
        f"ID: <code>{game_id}</code>\n\n"
        f"{pe('money')} Bet: ${bet_amount:.2f}\n"
        f"{pe('target')} Difficulty: {TOWER_DIFFICULTY_CONFIG[difficulty]['name']}\n"
        f"{pe('chart')} Floor: 0/9\n"
        f"{pe('gem')} Multiplier: 0.90x\n\n"
        f"Select a tile to start climbing!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def start_pvb_game_from_context(query, context, user, bet_amount_usd):
    """Wrapper to start a PvB game using existing conversation handler logic."""
    game_type = context.user_data.get('game_type', 'dice')
    game_mode = context.user_data.get('game_mode', 'normal')
    game_rolls = context.user_data.get('game_rolls', 1)
    target_points = context.user_data.get('target_points', 1)

    internal_game_type = f"pvb_{game_type}"
    game_id = generate_unique_id("PVB")
    seeds = get_user_seeds(user.id)

    game_sessions[game_id] = {
        "id": game_id,
        "game_type": internal_game_type,
        "user_id": user.id,
        "bet_amount": bet_amount_usd,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount_usd / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "game_mode": game_mode,
        "game_rolls": game_rolls,
        "target_points": target_points,
        "server_seed": seeds["server_seed"],
        "client_seed": seeds["client_seed"],
        "nonce": seeds["nonce"],
        "turn": "bot",
        "player_score": 0,
        "bot_score": 0,
        "round": 0,
    }

    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    await execute_pvb_game_round(query, context, game_id, user)

async def start_pvb_conversation_after_setup(query, context):
    """Helper function to enter the PvB conversation after mode and roll setup"""
    await query.edit_message_text(
        f"Please enter your bet amount for this game (or 'all').",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]])
    )
    return SELECT_BET_AMOUNT

async def cancel_withdrawal_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the withdrawal conversation and return to main menu"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Withdrawal cancelled.")
    context.user_data.clear()
    await start_command_inline(query, context)
    return ConversationHandler.END

async def cancel_recovery_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Recovery process cancelled.")
    context.user_data.clear()
    await start_command_inline(query, context)
    return ConversationHandler.END

def check_7up_2dice_win(option: str, dice_values: list) -> bool:
    """Check if a 2-dice 7up bet wins."""
    total = sum(dice_values)
    d1, d2 = dice_values[0], dice_values[1]
    opt = SEVEN_UP_DOWN_2DICE.get(option)
    if not opt:
        return False

    if "range" in opt:
        lo, hi = opt["range"]
        return lo <= total <= hi
    elif opt.get("check") == "odd":
        return total % 2 == 1
    elif opt.get("check") == "even":
        return total % 2 == 0
    elif opt.get("check") == "pair":
        return d1 == d2
    elif opt.get("check") == "combo16":
        return (d1 == 1 and d2 == 6) or (d1 == 6 and d2 == 1)
    return False

def check_7up_3dice_win(option: str, dice_values: list) -> bool:
    """Check if a 3-dice 7up bet wins."""
    total = sum(dice_values)
    vals = sorted(dice_values)
    opt = SEVEN_UP_DOWN_3DICE.get(option)
    if not opt:
        return False

    if "range" in opt:
        lo, hi = opt["range"]
        return lo <= total <= hi
    elif opt.get("check") == "alldiff":
        return len(set(dice_values)) == 3
    elif opt.get("check") == "triple":
        return len(set(dice_values)) == 1
    elif opt.get("check") == "allodd":
        return all(v % 2 == 1 for v in dice_values)
    elif opt.get("check") == "alleven":
        return all(v % 2 == 0 for v in dice_values)
    elif opt.get("check") == "2kind":
        return len(set(dice_values)) == 2 and not len(set(dice_values)) == 1
    elif opt.get("check") == "seq3":
        return set(vals) in VALID_SEQUENCES_3DICE
    return False

def check_7up_specific_combo(target_combo: list, dice_values: list) -> tuple:
    """Check specific combo bets (e.g., 1,2,3 or 6,6,6).
    Returns (won: bool, multiplier: float, combo_type: str)"""
    target_sorted = sorted(target_combo)
    actual_sorted = sorted(dice_values)

    if target_sorted != actual_sorted:
        return (False, 0, "")

    # Determine combo type
    unique = len(set(target_combo))
    if unique == 1:
        return (True, SEVEN_UP_3DICE_SPECIFIC["specific_triple"], "specific_triple")
    elif unique == 2:
        return (True, SEVEN_UP_3DICE_SPECIFIC["pair_kicker"], "pair_kicker")
    else:
        return (True, SEVEN_UP_3DICE_SPECIFIC["distinct_triple"], "distinct_triple")

async def async_generate_7up_help_image() -> BytesIO:
    """Async wrapper for 7up help image generation."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_image_executor, generate_7up_help_image)

def calculate_match_win_probability(match_data: dict) -> dict:
    """Calculate live win/loss probabilities for a match.

    Returns dict with:
    - p_win_p1: probability player 1 wins the match
    - p_win_p2: probability player 2 wins the match
    - p_draw: probability of draw (if applicable)
    - mult_win_p1: multiplier for betting on p1 win (with house edge)
    - mult_win_p2: multiplier for betting on p2 win (with house edge)
    - is_locked: True if any probability > SIDEBET_LOCK_THRESHOLD
    """
    players = match_data.get("players", [])
    if len(players) < 2:
        return {"p_win_p1": 0.5, "p_win_p2": 0.5, "p_draw": 0,
                "mult_win_p1": 1.86, "mult_win_p2": 1.86, "is_locked": False}

    p1, p2 = players[0], players[1]
    points = match_data.get("points", {p1: 0, p2: 0})
    target = match_data.get("target_points", match_data.get("target_score", 1))
    game_rolls = match_data.get("game_rolls", 1)
    game_mode = match_data.get("game_mode", match_data.get("mode", "normal"))

    p1_score = points.get(p1, 0)
    p2_score = points.get(p2, 0)

    # Calculate remaining rounds needed
    p1_needs = target - p1_score
    p2_needs = target - p2_score

    if p1_needs <= 0:
        return {"p_win_p1": 1.0, "p_win_p2": 0.0, "p_draw": 0,
                "mult_win_p1": 1.0, "mult_win_p2": 0, "is_locked": True}
    if p2_needs <= 0:
        return {"p_win_p1": 0.0, "p_win_p2": 1.0, "p_draw": 0,
                "mult_win_p1": 0, "mult_win_p2": 1.0, "is_locked": True}

    # Calculate single round win probability
    dist = _DICE_DIST.get(game_rolls, _DICE_DIST[1])
    p_win_round = 0.0
    p_lose_round = 0.0
    p_draw_round = 0.0

    # Check if we have partial roll data (mid-round)
    p1_rolls = match_data.get("player_rolls", {}).get(p1, [])
    p2_rolls = match_data.get("player_rolls", {}).get(p2, [])

    if len(p1_rolls) == game_rolls and len(p2_rolls) < game_rolls:
        # Player 1 has finished rolling, player 2 hasn't
        p1_total = sum(p1_rolls)
        remaining_rolls = game_rolls - len(p2_rolls)
        p2_partial = sum(p2_rolls) if p2_rolls else 0

        remaining_dist = _DICE_DIST.get(remaining_rolls, _DICE_DIST[1])

        for remaining_sum, prob in remaining_dist.items():
            p2_total = p2_partial + remaining_sum
            if game_mode == "normal":
                if p2_total > p1_total:
                    p_lose_round += prob
                elif p2_total < p1_total:
                    p_win_round += prob
                else:
                    p_draw_round += prob
            else:  # crazy mode - lowest wins
                if p2_total < p1_total:
                    p_lose_round += prob
                elif p2_total > p1_total:
                    p_win_round += prob
                else:
                    p_draw_round += prob
    elif len(p2_rolls) == game_rolls and len(p1_rolls) < game_rolls:
        # Player 2 finished, player 1 hasn't
        p2_total = sum(p2_rolls)
        remaining_rolls = game_rolls - len(p1_rolls)
        p1_partial = sum(p1_rolls) if p1_rolls else 0

        remaining_dist = _DICE_DIST.get(remaining_rolls, _DICE_DIST[1])

        for remaining_sum, prob in remaining_dist.items():
            p1_total = p1_partial + remaining_sum
            if game_mode == "normal":
                if p1_total > p2_total:
                    p_win_round += prob
                elif p1_total < p2_total:
                    p_lose_round += prob
                else:
                    p_draw_round += prob
            else:
                if p1_total < p2_total:
                    p_win_round += prob
                elif p1_total > p2_total:
                    p_lose_round += prob
                else:
                    p_draw_round += prob
    else:
        # No partial data or both rolled - use symmetric probability
        for s1, p1_prob in dist.items():
            for s2, p2_prob in dist.items():
                joint_prob = p1_prob * p2_prob
                if game_mode == "normal":
                    if s1 > s2:
                        p_win_round += joint_prob
                    elif s1 < s2:
                        p_lose_round += joint_prob
                    else:
                        p_draw_round += joint_prob
                else:
                    if s1 < s2:
                        p_win_round += joint_prob
                    elif s1 > s2:
                        p_lose_round += joint_prob
                    else:
                        p_draw_round += joint_prob

    # Use iterative dynamic programming instead of recursive lru_cache
    # This avoids creating a new cache per call and is faster for small state spaces
    # PERFORMANCE: O(target^2) time and space, which is tiny (max 25 cells for ft5)
    memo = {}

    def match_prob(s1, s2):
        if s1 >= target:
            return 1.0
        if s2 >= target:
            return 0.0
        key = (s1, s2)
        if key in memo:
            return memo[key]

        # Handle draws by computing effective probabilities without draws
        if p_draw_round > 0 and p_draw_round < 1:
            eff_p_win = p_win_round / (1 - p_draw_round)
            eff_p_lose = p_lose_round / (1 - p_draw_round)
        else:
            eff_p_win = p_win_round
            eff_p_lose = p_lose_round

        result = eff_p_win * match_prob(s1 + 1, s2) + eff_p_lose * match_prob(s1, s2 + 1)
        memo[key] = result
        return result

    p_win_p1 = match_prob(p1_score, p2_score)
    p_win_p2 = 1.0 - p_win_p1

    # Clamp probabilities
    p_win_p1 = max(0.001, min(0.999, p_win_p1))
    p_win_p2 = max(0.001, min(0.999, p_win_p2))

    # Calculate multipliers with 7% house edge
    fair_mult_p1 = 1.0 / p_win_p1 if p_win_p1 > 0 else 999.0
    fair_mult_p2 = 1.0 / p_win_p2 if p_win_p2 > 0 else 999.0

    mult_win_p1 = round(fair_mult_p1 * (1 - SIDEBET_HOUSE_EDGE), 2)
    mult_win_p2 = round(fair_mult_p2 * (1 - SIDEBET_HOUSE_EDGE), 2)

    # Cap multipliers
    mult_win_p1 = min(mult_win_p1, 50.0)
    mult_win_p2 = min(mult_win_p2, 50.0)

    is_locked = p_win_p1 > SIDEBET_LOCK_THRESHOLD or p_win_p2 > SIDEBET_LOCK_THRESHOLD

    return {
        "p_win_p1": round(p_win_p1, 4),
        "p_win_p2": round(p_win_p2, 4),
        "p_draw": round(p_draw_round, 4),
        "mult_win_p1": mult_win_p1,
        "mult_win_p2": mult_win_p2,
        "is_locked": is_locked,
        "p1_score": p1_score,
        "p2_score": p2_score,
        "target": target,
    }

def find_active_emoji_game_for_user(target_user_id: int, chat_id: int = None) -> tuple:
    """Find an active emoji game that a specific user is participating in.
    PERFORMANCE: Uses index for O(1) lookup instead of full scan.
    Returns (match_id, match_data) or (None, None)."""
    # Fast path: check PvB games
    if target_user_id in active_pvb_games:
        game_id = active_pvb_games[target_user_id]
        game_data = game_sessions.get(game_id)
        if game_data and game_data.get("status") == "active":
            if chat_id is None or game_data.get("chat_id") == chat_id:
                return (game_id, game_data)

    # Fast path: check indexed games
    for game_id in _get_user_active_game_ids(target_user_id):
        match_data = game_sessions.get(game_id)
        if not match_data or match_data.get("status") != "active":
            continue
        game_type = match_data.get("game_type", "")
        if not any(x in game_type for x in ['pvp_', 'pvb_', 'group_challenge_', 'xdxw_']):
            continue
        if chat_id is None or match_data.get("chat_id") == chat_id:
            return (game_id, match_data)

    # Fallback: full scan for backward compatibility
    for match_id, match_data in game_sessions.items():
        if match_data.get("status") != "active":
            continue
        game_type = match_data.get("game_type", "")
        if not any(x in game_type for x in ['pvp_', 'pvb_', 'group_challenge_', 'xdxw_']):
            continue
        players = match_data.get("players", [])
        if target_user_id in players:
            if chat_id is None or match_data.get("chat_id") == chat_id:
                _index_user_game(target_user_id, match_id)
                return (match_id, match_data)
        if match_data.get("user_id") == target_user_id:
            if chat_id is None or match_data.get("chat_id") == chat_id:
                _index_user_game(target_user_id, match_id)
                return (match_id, match_data)

    return (None, None)

async def resolve_sidebets_for_match(match_id: str, winner_player_index: str, context):
    """Resolve all side bets for a completed match.
    winner_player_index is 'p1' or 'p2'.

    Win/lose notifications are sent to the bettor's private DM, NOT the
    group chat, to avoid spamming the group and leaking individual wagers.
    """
    if match_id not in match_sidebets:
        return

    match_data = game_sessions.get(match_id, {})
    game_type = match_data.get("game_type", "match").replace("pvp_", "").replace("pvb_", "").replace("group_challenge_", "").replace("xdxw_", "")

    sidebet_ids = match_sidebets.pop(match_id, [])

    # PERFORMANCE: Fan out all DM notifications in parallel via safe_send_message
    # (honours RetryAfter, skips blocked/deactivated users). The previous
    # implementation awaited each DM sequentially — with 20 sidebets on a
    # popular match that meant 20 round trips serialized, which with
    # Telegram's per-chat 1 msg/s limit meant the losing group in a busy
    # game had to wait many seconds for all resolutions to complete.
    dm_tasks = []

    for sb_id in sidebet_ids:
        sb = active_sidebets.get(sb_id)
        if not sb or sb.get("status") != "active":
            continue

        bettor_id = sb["bettor_id"]
        bet_amount = sb["bet_amount_usd"]
        multiplier = sb["multiplier_at_placement"]
        bet_on_label = "WIN" if sb.get("bet_on") == "p1" else "LOSS"

        if sb["bet_on"] == winner_player_index:
            payout = bet_amount * multiplier
            credit_wallet(bettor_id, payout)
            sb["status"] = "won"
            sb["payout"] = payout
            text = (
                f"\U0001F389 <b>Side Bet WON!</b>\n\n"
                f"Match: <code>{match_id}</code> ({game_type})\n"
                f"Your pick: <b>{bet_on_label}</b>\n"
                f"Stake: <b>${bet_amount:.2f}</b>\n"
                f"Payout: <b>${payout:.2f}</b> ({multiplier}x)"
            )
        else:
            sb["status"] = "lost"
            sb["payout"] = 0
            text = (
                f"\U0001F614 <b>Side Bet LOST</b>\n\n"
                f"Match: <code>{match_id}</code> ({game_type})\n"
                f"Your pick: <b>{bet_on_label}</b>\n"
                f"Stake lost: <b>${bet_amount:.2f}</b>"
            )

        # Update sidebet in game_sessions for history tracking
        if sb_id in game_sessions:
            game_sessions[sb_id]["status"] = "completed"
            game_sessions[sb_id]["result"] = sb["status"]
            game_sessions[sb_id]["payout"] = sb.get("payout", 0)

        dm_tasks.append(safe_send_message(
            context.bot, bettor_id, text, parse_mode=ParseMode.HTML
        ))
        save_user_data(bettor_id)
        active_sidebets.pop(sb_id, None)

    if dm_tasks:
        # return_exceptions so one dead DM doesn't abort the others.
        await asyncio.gather(*dm_tasks, return_exceptions=True)

def _is_pvb_session(game: dict) -> bool:
    """True if this game_sessions entry is a Player-vs-Bot match.

    Covers every PvB entry point:
      - legacy /dice play_vs_bot_game (user_id/bot_rolls schema only)
      - xdxw_playbot / gc_playbot (has both players=[host,0] and legacy keys)
      - converted rpvp/bot challenges
    """
    if not isinstance(game, dict):
        return False
    if 0 in (game.get("players") or []):
        return True
    if game.get("opponent_id") == 0:
        return True
    if "user_score" in game or "bot_score" in game or "bot_rolls" in game:
        return True
    # Don't treat a plain PvP challenge as PvB just because host_id exists.
    return False

def _build_pvb_match_view(game: dict, user_id: int = None) -> dict:
    """Project a PvB session into the schema calculate_match_win_probability expects.

    The tricky bit: several PvB flows (xdxw_playbot, gc_playbot) populate BOTH the
    new PvP-style fields (players/points/player_rolls) AND the legacy PvB fields
    (user_score/bot_score/user_rolls/bot_rolls). Only `message_listener`'s PvB
    block updates the legacy fields each round — the new-schema fields go stale.
    If we read `points` / `player_rolls` directly off the dict, the cashout
    multiplier ends up frozen at its round-1 value ("~0.93x no matter what").

    So we ALWAYS prefer the legacy fields when they exist and fall back to the
    PvP-style fields only when the legacy ones were never initialized.
    """
    if user_id is None:
        user_id = game.get("user_id") or game.get("host_id")
        # Last resort: pick the non-bot id from players[]
        if user_id is None:
            for pid in game.get("players") or []:
                if pid != 0:
                    user_id = pid
                    break
    bot_id = 0
    if user_id is None:
        return {}

    # Scores: prefer legacy user_score/bot_score (updated live by message_listener)
    if "user_score" in game or "bot_score" in game:
        user_score = int(game.get("user_score") or 0)
        bot_score = int(game.get("bot_score") or 0)
    elif "points" in game:
        user_score = int((game["points"] or {}).get(user_id, 0) or 0)
        bot_score = int((game["points"] or {}).get(bot_id, 0) or 0)
    else:
        user_score = 0
        bot_score = 0

    # Partial rolls: prefer legacy user_rolls/bot_rolls (updated live each roll)
    if "user_rolls" in game or "bot_rolls" in game:
        user_rolls = list(game.get("user_rolls") or [])
        bot_rolls = list(game.get("bot_rolls") or [])
    elif "player_rolls" in game:
        user_rolls = list((game["player_rolls"] or {}).get(user_id, []) or [])
        bot_rolls = list((game["player_rolls"] or {}).get(bot_id, []) or [])
    else:
        user_rolls = []
        bot_rolls = []

    return {
        "players": [user_id, bot_id],
        "points": {user_id: user_score, bot_id: bot_score},
        "target_points": int(
            game.get("target_score")
            or game.get("target_points")
            or 1
        ),
        "game_rolls": int(game.get("game_rolls") or game.get("rolls") or 1),
        "game_mode": game.get("game_mode") or game.get("mode") or "normal",
        "player_rolls": {
            user_id: user_rolls,
            bot_id: bot_rolls,
        },
    }

def calculate_cashout_multiplier(match_data: dict, user_id: int = None) -> float:
    """Calculate the cashout multiplier for the player in a PvB game.

    Based on the probability of winning the *match* (not just this round),
    mirroring the sidebet engine:
        multiplier = P(player_wins_match) * 2 * (1 - 7% house edge)

    So at 50/50 (pre-roll, 0-0) the multiplier is ~0.93x. Score advantage and
    live partial rolls pull it up; being behind pulls it down. Floor 0.10x
    avoids showing nonsense like 0.00x late in losing games.
    """
    # Always project PvB sessions onto the probability-engine schema using the
    # freshest fields. Otherwise stale new-schema `points`/`player_rolls` on
    # xdxw_playbot / gc_playbot sessions (only legacy keys are updated each
    # round) freeze the multiplier at its round-1 value.
    if _is_pvb_session(match_data):
        match_data = _build_pvb_match_view(match_data, user_id)

    odds = calculate_match_win_probability(match_data)
    p_player_wins = odds.get("p_win_p1", 0.5)
    multiplier = p_player_wins * 2 * (1 - CASHOUT_HOUSE_EDGE)
    # Clamp to a reasonable display range (0.10x .. 50x)
    multiplier = max(0.10, min(multiplier, 50.0))
    return round(multiplier, 2)

def _build_pvb_cashout_keyboard(match_id: str, cashout_round: int, multiplier: float,
                                 extra_top_row: list = None) -> InlineKeyboardMarkup:
    """Build the green cashout button (with optional extra top row e.g. blue 'Bot Rolls First').

    Layout:
      [optional top row buttons]
      [Cashout (X.XXx)]      <- always green, always below the top row
    """
    cashout_btn = apply_button_style(
        InlineKeyboardButton(
            f"Cashout ({multiplier:.2f}x)",
            callback_data=f"pvb_cashout_{match_id}_{cashout_round}"
        ),
        'success', peb('cashout')
    )
    rows = []
    if extra_top_row:
        rows.append(extra_top_row)
    rows.append([cashout_btn])
    return create_styled_keyboard(rows)

def _register_cashout_button(match_id: str, user_id: int, chat_id: int,
                             cashout_round: int, message_id: int = None):
    """Track an active cashout button so subsequent rolls can invalidate or
    re-render it (to keep the multiplier in sync with live match state)."""
    _active_cashout_buttons[match_id] = {
        "round": cashout_round,
        "user_id": user_id,
        "chat_id": chat_id,
        "message_id": message_id,
    }

async def _refresh_pvb_cashout_button(context, match_id: str, game: dict,
                                      user_id: int):
    """Re-render the currently-active cashout button with an updated multiplier
    computed off the latest match state (partial rolls, score). No-op if the
    button isn't tracked or we don't have a message id to edit."""
    info = _active_cashout_buttons.get(match_id)
    if not info or not info.get("message_id") or not info.get("chat_id"):
        return
    try:
        mult = calculate_cashout_multiplier(game, user_id=user_id)
        kb = _build_pvb_cashout_keyboard(match_id, info.get("round", 1), mult)
        await context.bot.edit_message_reply_markup(
            chat_id=info["chat_id"],
            message_id=info["message_id"],
            reply_markup=kb,
        )
    except Exception:
        # Message may have been deleted / too old; silently ignore.
        pass

def _schedule_pvb_cashout_refresh(context, match_id: str, game: dict, user_id: int) -> None:
    """Throttled, fire-and-forget wrapper around `_refresh_pvb_cashout_button`.

    The refresh is purely cosmetic (keeps the cashout multiplier label live);
    awaiting it inside the dice-roll handler is what made concurrent PvB
    matches in the same chat lag.
    """
    info = _active_cashout_buttons.get(match_id)
    if not info or not info.get("message_id") or not info.get("chat_id"):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    now = loop.time()
    last = _cashout_refresh_last.get(match_id, 0.0)
    if now - last < _CASHOUT_REFRESH_MIN_INTERVAL:
        return
    _cashout_refresh_last[match_id] = now
    asyncio.create_task(
        _refresh_pvb_cashout_button(context, match_id, game, user_id)
    )

def is_pvb_game(match_data: dict) -> bool:
    """Check if a game session is a PvB (Player vs Bot) game."""
    players = match_data.get("players", [])
    return 0 in players and match_data.get("status") == "active"

async def void_sidebets_for_cashout(match_id: str, context):
    """Void all side bets for a match where a player cashed out.
    Refund all bettors and notify them via DM."""
    if match_id not in match_sidebets:
        return

    sidebet_ids = match_sidebets.pop(match_id, [])
    for sb_id in sidebet_ids:
        sb = active_sidebets.get(sb_id)
        if not sb or sb.get("status") != "active":
            continue

        bettor_id = sb["bettor_id"]
        bet_amount = sb["bet_amount_usd"]

        # Refund the bettor
        credit_wallet(bettor_id, bet_amount)
        sb["status"] = "voided"
        sb["void_reason"] = "Player cashed out"
        save_user_data(bettor_id)

        # Notify bettor via DM
        try:
            bettor_name = sb.get("bettor_username", f"User {bettor_id}")
            await context.bot.send_message(
                chat_id=bettor_id,
                text=(
                    f"{pe('warning')} <b>Side Bet Voided</b>\n\n"
                    f"Your side bet (ID: <code>{sb_id}</code>) has been voided because "
                    f"the player cashed out of the match.\n\n"
                    f"{pe('money')} <b>Refund: ${bet_amount:.2f}</b> has been returned to your wallet.\n\n"
                    f"Match ID: <code>{match_id}</code>"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.warning(f"Could not notify bettor {bettor_id} about voided sidebet: {e}")

        active_sidebets.pop(sb_id, None)

@check_banned
@check_maintenance
async def start_game_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return ConversationHandler.END

    game_type = 'mines' if 'mines' in query.data else 'tower'

    # Check per-game maintenance status
    if not is_game_enabled(game_type):
        emoji_map = {"mines": "\U0001f4a3", "tower": "\U0001f3d4"}
        emoji = emoji_map.get(game_type, "\U0001f3ae")
        await query.answer(
            f"\U0001f527 {emoji} {game_type.title()} game is under maintenance.",
            show_alert=True
        )
        return ConversationHandler.END

    await query.answer()
    context.user_data['game_type'] = game_type
    user_id = query.from_user.id

    if game_type == 'mines':
        # NEW: Add user_id to buttons for user-specific interactions
        buttons = [[InlineKeyboardButton(str(i), callback_data=f"bombs_{i}") for i in range(row, row + 8)] for row in range(1, 25, 8)]
        text = f"{pe('bomb')} Select the number of mines (1-24):"
    else: # tower
        buttons = [[InlineKeyboardButton(f"{i}", callback_data=f"bombs_{i}") for i in range(1, 4)]]
        text = f"{pe('tower')} Select the number of bombs per row (1-3):"

    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel_game")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    # Set ownership after editing
    set_menu_owner(query.message, query.from_user.id)
    return SELECT_BOMBS

async def select_bet_amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game_type = context.user_data.get('game_type')
    single_emoji_game = context.user_data.get('single_emoji_game')

    if single_emoji_game:
        # Handle single emoji game bet input
        user = update.effective_user
        try:
            bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(update.message.text, user.id)
        except ValueError:
            await update.message.reply_text("Invalid amount. Please enter a valid number or 'all'.")
            return SELECT_BET_AMOUNT

        if get_active_balance_usd(user.id) < bet_amount_usd:
            await send_insufficient_balance_message(update)
            context.user_data.clear()
            return ConversationHandler.END

        await play_single_emoji_game(update, context, single_emoji_game, bet_amount_usd, bet_amount_currency, currency)
        context.user_data.clear()
        return ConversationHandler.END

    if game_type == 'mines':
        return await mines_command(update, context)
    elif game_type == 'tower':
        return await tower_command(update, context)

@check_banned
@check_maintenance
async def start_pvb_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    game_map = {"dice_bot": "dice", "football": "goal", "darts": "darts", "bowling": "bowl"}
    game_key = query.data.replace("pvb_start_", "")
    game_type = game_map.get(game_key, game_key)
    context.user_data['game_type'] = game_type

    await query.edit_message_text("Please enter your bet amount for this game (or 'all').", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
    # Set ownership after editing
    set_menu_owner(query.message, query.from_user.id)
    return SELECT_BET_AMOUNT

async def pvb_get_bet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    try:
        bet_amount_str = update.message.text.lower()
        if bet_amount_str == 'all':
            bet_amount = get_active_balance_usd(user.id)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not await check_bet_limits(update, bet_amount, f"pvb_{context.user_data['game_type']}"):
        return SELECT_BET_AMOUNT

    context.user_data['bet_amount'] = bet_amount
    await update.message.reply_text("Bet amount set. Now, please enter the points target (e.g., ft1, ft3, ft5).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
    return SELECT_TARGET_SCORE

async def pvb_get_target_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        text = update.message.text.lower()
        if not text.startswith("ft") or not text[2:].isdigit():
            raise ValueError

        target_score = int(text[2:])
        if not 1 <= target_score <= 10:
            await update.message.reply_text("Please enter a valid target between ft1 and ft10.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
            return SELECT_TARGET_SCORE

    except (ValueError, IndexError):
        await update.message.reply_text("Invalid format. Please enter the target score as ftX (e.g., ft3).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_TARGET_SCORE

    context.user_data['target_score'] = target_score

    # Ask who should roll first - BLUE buttons for the roll-order choices, RED for cancel
    you_first_btn = apply_button_style(
        InlineKeyboardButton("You Roll First", callback_data="pvb_first_user"),
        'primary', peb('user')
    )
    bot_first_btn = apply_button_style(
        InlineKeyboardButton("Bot Rolls First", callback_data="pvb_first_bot"),
        'primary', peb('robot')
    )
    cancel_btn = apply_button_style(
        InlineKeyboardButton("Cancel", callback_data="cancel_game"),
        'danger', peb('cross')
    )
    keyboard = create_styled_keyboard([
        [you_first_btn],
        [bot_first_btn],
        [cancel_btn],
    ])
    await update.message.reply_text(
        f"{pe('game')} <b>Who Rolls First?</b>\n\n"
        f"Choose who should roll first in each round:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    return SELECT_WHO_ROLLS_FIRST

async def cancel_game_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    # Determine which menu to return to based on game type
    game_type = context.user_data.get('game_type')
    context.user_data.clear()

    if game_type in ['mines', 'tower']:
        # Return to house games menu for mines and tower
        text = f"{pe('house')} <b>House Games</b>\n\nChoose a game to see how to play:"
        keyboard = [
            [InlineKeyboardButton("Blackjack", callback_data="game_blackjack"),
             InlineKeyboardButton("Dice Roll", callback_data="game_dice_roll")],
            [InlineKeyboardButton("Predict", callback_data="game_predict"),
             InlineKeyboardButton("Roulette", callback_data="game_roulette")],
            [InlineKeyboardButton("Slots", callback_data="game_slots"),
             InlineKeyboardButton("Tower", callback_data="tower_help")],
            [InlineKeyboardButton("Mines", callback_data="mines_help"),
             InlineKeyboardButton("Keno", callback_data="game_keno")],
            [InlineKeyboardButton("Coin Flip", callback_data="game_coin_flip"),
             InlineKeyboardButton("High-Low", callback_data="game_highlow")],
            [InlineKeyboardButton("Back to Categories", callback_data="main_games")]
        ]
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        set_menu_owner(query.message, query.from_user.id)
    elif game_type in ['dice_bot', 'darts', 'football', 'bowling', 'dice', 'goal', 'bowl']:
        # Return to emoji regular games menu for PvB games
        text = f"{pe('game')} <b>Regular Emoji Games</b>\n\nChoose a game to see how to play:"
        keyboard = [
            [apply_button_style(InlineKeyboardButton("Dice", callback_data="game_dice_bot"), 'success', peb('dice'))],
            [apply_button_style(InlineKeyboardButton("Darts", callback_data="game_darts"), 'success', peb('darts'))],
            [apply_button_style(InlineKeyboardButton("Football", callback_data="game_football"), 'success', peb('goal'))],
            [apply_button_style(InlineKeyboardButton("Bowling", callback_data="game_bowling"), 'success', peb('bowl'))],
            [apply_button_style(InlineKeyboardButton("Back to Emoji Games", callback_data="main_games_emoji"), 'danger', peb('back'))]
        ]
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_styled_keyboard(keyboard)
        )
        set_menu_owner(query.message, query.from_user.id)
    else:
        # For other games, return to main menu
        await query.edit_message_text("Game setup cancelled.")
        await start_command_inline(query, context)

    return ConversationHandler.END

@check_banned
@check_maintenance
async def start_ai_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    keyboard = [
        [InlineKeyboardButton(f"{pe('robot')} Perplexity (Online)", callback_data="ai_model_perplexity")],
        [InlineKeyboardButton("GPT4Free (Free)", callback_data="ai_model_g4f")],
        [InlineKeyboardButton("Cancel & Back to Menu", callback_data="cancel_ai")]
    ]
    await safe_edit_message(
        query,
        "🤖 <b>AI Assistant</b>\n\nWhich AI model would you like to use?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_AI_MODEL

async def cancel_ai_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    # Return to More menu instead of main menu
    await more_menu(update, context)
    return ConversationHandler.END

async def bonuses_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("Daily Bonus", callback_data="main_daily")],
        [InlineKeyboardButton("Weekly Bonus", callback_data="bonus_weekly")],
        [InlineKeyboardButton(f"{pe('calendar')} Monthly Bonus", callback_data="bonus_monthly")],
        [InlineKeyboardButton("Rakeback", callback_data="bonus_rakeback")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="back_to_main")]
    ]

    await safe_edit_message(
        query,
        "🎁 <b>Bonuses & Rakeback</b> 🎁\n\n"
        "Claim your rewards for playing! Choose an option below.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def save_bot_settings_only():
    """Non-blocking save for bot_settings only (doesn't save all user data)."""
    try:
        state = {
            'username_to_userid': username_to_userid,
            'game_sessions': {k: v for k, v in game_sessions.items()
                              if v.get('status') == 'active'},
            'user_pending_invitations': user_pending_invitations,
            'escrow_deals': escrow_deals,
            'withdrawal_requests': {k: v for k, v in withdrawal_requests.items()
                                   if v.get('status') == 'pending'},
            'bot_stopped': bot_stopped,
            'bot_settings': {k: v for k, v in bot_settings.items()
                             if k != 'menu_owners'},
            'referral_codes': referral_codes,
            'active_raffles': active_raffles,
            'completed_raffles': completed_raffles,
            'leaderboard_data': leaderboard_data,
            'leaderboard_last_update': {
                k: v.isoformat() for k, v in leaderboard_last_update.items()
            },
        }
        tmp = STATE_FILE + ".tmp"
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: _sync_write_state(state, tmp))
    except Exception as e:
        logging.error(f"Failed to save bot settings: {e}")

def _sync_write_state(state, tmp):
    """Synchronous state file write."""
    with open(tmp, "w") as f:
        json.dump(state, f, default=str)
    os.replace(tmp, STATE_FILE)

async def collect_user_transactions(user_id: int) -> list:
    """Collect all transactions for a user from various sources."""
    transactions = []
    stats = user_stats.get(user_id, {})
    wallet = user_wallets.get(user_id, {})
    active_currency = stats.get("active_currency", "USDT")
    price = LIVE_PRICES.get(active_currency, 1.0)

    # 1. Game sessions (wins and losses)
    for game_id in stats.get("game_sessions", []):
        game = game_sessions.get(game_id, {})
        if game.get("user_id") != user_id:
            continue
        try:
            ts_str = game.get("timestamp", "")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else None
        except:
            ts = None

        game_type = game.get("game_type", "unknown")
        bet_amount = game.get("bet_amount", 0)
        won = game.get("win", False)
        multiplier = game.get("multiplier", 0)

        if won and multiplier > 0:
            winnings = bet_amount * multiplier
            net = winnings - bet_amount
            transactions.append({
                "type": "win",
                "amount_usd": winnings,
                "net_usd": net,
                "coin": game.get("active_currency", active_currency),
                "description": f"{game_type.replace('_', ' ').title()} win ({multiplier}x)",
                "game_id": game_id,
                "timestamp": ts,
                "ts_str": ts_str
            })
        else:
            transactions.append({
                "type": "loss",
                "amount_usd": -bet_amount,
                "net_usd": -bet_amount,
                "coin": game.get("active_currency", active_currency),
                "description": f"{game_type.replace('_', ' ').title()} loss",
                "game_id": game_id,
                "timestamp": ts,
                "ts_str": ts_str
            })

    # 2. Bet history (for games not in game_sessions)
    for bet in stats.get("bets", {}).get("history", []):
        try:
            ts_str = bet.get("timestamp", "")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else None
        except:
            ts = None
        amount = bet.get("amount", 0)
        # Only add if it's a negative amount (loss) since wins are in game_sessions
        if amount < 0:
            transactions.append({
                "type": "loss",
                "amount_usd": amount,
                "net_usd": amount,
                "coin": active_currency,
                "description": "Bet loss",
                "timestamp": ts,
                "ts_str": ts_str
            })

    # 3. Withdrawals
    for withdrawal in stats.get("withdrawals", []):
        try:
            ts_str = withdrawal.get("timestamp", "")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else None
        except:
            ts = None
        amount = withdrawal.get("amount", 0)
        method = withdrawal.get("method", "unknown")
        tx_hash = withdrawal.get("tx_hash", "")[:10] if withdrawal.get("tx_hash") else ""
        transactions.append({
            "type": "withdrawal",
            "amount_usd": -amount,
            "net_usd": -amount,
            "coin": active_currency,
            "description": f"Withdrawal via {method}" + (f" ({tx_hash}...)" if tx_hash else ""),
            "timestamp": ts,
            "ts_str": ts_str
        })

    # 4. Deposits
    for deposit in stats.get("deposits", []):
        try:
            ts_str = deposit.get("timestamp", "")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else None
        except:
            ts = None
        amount = deposit.get("amount", 0)
        method = deposit.get("method", "unknown")
        transactions.append({
            "type": "deposit",
            "amount_usd": amount,
            "net_usd": amount,
            "coin": active_currency,
            "description": f"Deposit via {method}",
            "timestamp": ts,
            "ts_str": ts_str
        })

    # 5. Tips received (aggregate) - only if reasonable amount
    tips_received = stats.get("tips_received", {})
    tips_received_amount = tips_received.get("amount", 0)
    # Only show if amount is reasonable (less than $1M to avoid corrupted data)
    if 0 < tips_received_amount < 1000000:
        transactions.append({
            "type": "tip_in",
            "amount_usd": tips_received_amount,
            "net_usd": tips_received_amount,
            "coin": active_currency,
            "description": f"Tips received ({tips_received.get('count', 0)} tips)",
            "timestamp": None,
            "ts_str": ""
        })

    # 6. Tips sent (aggregate) - only if reasonable amount
    tips_sent = stats.get("tips_sent", {})
    tips_sent_amount = tips_sent.get("amount", 0)
    if 0 < tips_sent_amount < 1000000:
        transactions.append({
            "type": "tip_out",
            "amount_usd": -tips_sent_amount,
            "net_usd": -tips_sent_amount,
            "coin": active_currency,
            "description": f"Tips sent ({tips_sent.get('count', 0)} tips)",
            "timestamp": None,
            "ts_str": ""
        })

    # 7. Level-up rewards
    for level_name in stats.get("claimed_level_rewards", []):
        # Find the reward amount from ALL_LEVELS
        for lvl_name, lvl_wager, bonus in ALL_LEVELS:
            if lvl_name == level_name:
                transactions.append({
                    "type": "bonus",
                    "amount_usd": bonus,
                    "net_usd": bonus,
                    "coin": active_currency,
                    "description": f"Level-up reward: {level_name}",
                    "timestamp": None,
                    "ts_str": ""
                })
                break

    # 8. Demo claims (aggregate count, show as transactions)
    last_demo = stats.get("last_demo_claim")
    if last_demo:
        demo_amount = bot_settings.get("demo_amount", 10.0)
        try:
            ts = datetime.fromisoformat(last_demo.replace("Z", "+00:00"))
        except:
            ts = None
        transactions.append({
            "type": "bonus",
            "amount_usd": demo_amount,
            "net_usd": demo_amount,
            "coin": active_currency,
            "description": "Demo claim",
            "timestamp": ts,
            "ts_str": last_demo
        })

    # 9. Rakeback claimed (if tracked)
    rakeback_balance = stats.get("rakeback_balance", 0)

    # Sort by timestamp (newest first), None timestamps go to end
    transactions.sort(key=lambda x: x["timestamp"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    return transactions

def format_transaction(tx: dict) -> str:
    """Format a single transaction as a text line."""
    tx_type = tx.get("type", "unknown")
    amount = tx.get("amount_usd", 0)
    description = tx.get("description", "")
    ts_str = tx.get("ts_str", "")
    has_timestamp = tx.get("timestamp") is not None

    # Format timestamp
    if has_timestamp:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            time_str = ts.strftime("%Y-%m-%d %H:%M")
        except:
            time_str = "Older"
    else:
        time_str = "Older"

    # Emoji and sign based on type - using premium emojis via pe()
    type_emojis = {
        "win": f"{pe('win')} WIN",
        "loss": f"{pe('lose')} LOSS",
        "deposit": f"{pe('deposit')} DEPOSIT",
        "withdrawal": f"{pe('withdraw')} WITHDRAW",
        "tip_in": f"{pe('gift')} TIP IN",
        "tip_out": f"{pe('money')} TIP OUT",
        "bonus": f"{pe('gift')} BONUS",
    }

    emoji_label = type_emojis.get(tx_type, "💵 TRANSACTION")
    sign = "+" if amount > 0 else ""
    amount_str = f"{sign}${abs(amount):.2f}"

    return f"{time_str}\n{emoji_label}: {description}\nAmount: <b>{amount_str}</b>"

async def send_transactions_page(update, context, user_id: int, page: int, is_admin: bool = False):
    """Send a page of transactions to the user."""
    transactions = await collect_user_transactions(user_id)
    total = len(transactions)

    if total == 0:
        text = f"{pe('chart')} <b>No Transactions Found</b>\n\nYou have no transaction history yet."
        if is_admin:
            text = f"{pe('chart')} <b>User Transactions</b>\n\nThis user has no transaction history yet."
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    start_idx = page * TRANSACTIONS_PER_PAGE
    end_idx = min(start_idx + TRANSACTIONS_PER_PAGE, total)
    page_items = transactions[start_idx:end_idx]

    # Build transaction text
    lines = []
    for tx in page_items:
        lines.append(format_transaction(tx))

    text = f"{pe('chart')} <b>Transaction History</b>\n"
    if is_admin:
        # Try to find username for target user
        display_name = str(user_id)
        for uname, uid in username_to_userid.items():
            if uid == user_id:
                display_name = f"@{uname}"
                break
        text = f"{pe('chart')} <b>User Transactions</b> ({display_name}, ID: <code>{user_id}</code>)\n"

    text += f"\nPage {page + 1} of {(total + TRANSACTIONS_PER_PAGE - 1) // TRANSACTIONS_PER_PAGE} ({total} transactions)\n\n"
    text += "\n\n──────────\n\n".join(lines)

    # Build navigation keyboard
    keyboard = []
    nav_row = []

    total_pages = (total + TRANSACTIONS_PER_PAGE - 1) // TRANSACTIONS_PER_PAGE

    # Back button (red) with premium emoji
    if page > 0:
        callback_data = f"txn_page_{user_id}_{page - 1}_{'1' if is_admin else '0'}"
        nav_row.append(apply_button_style(
            InlineKeyboardButton("Back", callback_data=callback_data),
            'danger',
            peb('left')
        ))

    # Next button (blue) with premium emoji
    if (page + 1) < total_pages:
        callback_data = f"txn_page_{user_id}_{page + 1}_{'1' if is_admin else '0'}"
        nav_row.append(apply_button_style(
            InlineKeyboardButton("Next", callback_data=callback_data),
            'primary',
            peb('arrow_right')
        ))

    if nav_row:
        keyboard.append(nav_row)

    # Close button - user-specific to prevent others from closing
    keyboard.append([InlineKeyboardButton("Close", callback_data=f"txn_close_{user_id}")])

    if update.callback_query:
        await safe_edit_message(
            update.callback_query,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def pf_client_seed_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new client seed input"""
    user = update.effective_user
    new_seed = update.message.text.strip()

    # Validate seed
    if len(new_seed) < 4 or len(new_seed) > 64:
        await update.message.reply_text(
            "❌ Client seed must be between 4-64 characters.\n"
            "Please try again or send /cancel"
        )
        return PF_CHANGE_CLIENT_SEED_INPUT

    if not new_seed.replace('_', '').replace('-', '').isalnum():
        await update.message.reply_text(
            "❌ Client seed can only contain letters, numbers, _ and -\n"
            "Please try again or send /cancel"
        )
        return PF_CHANGE_CLIENT_SEED_INPUT

    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Update client seed
    pf_data = user_stats[user.id].get("provably_fair", {})
    old_seed = pf_data.get("client_seed", "")
    pf_data["client_seed"] = new_seed
    pf_data["nonce"] = 0  # Reset nonce

    save_user_data(user.id)

    await update.message.reply_text(
        f"{pe('check')} <b>Client Seed Updated!</b>\n\n"
        f"<b>Old Seed:</b> <code>{old_seed}</code>\n"
        f"<b>New Seed:</b> <code>{new_seed}</code>\n\n"
        f"Nonce reset to 0",
        parse_mode=ParseMode.HTML
    )

    return ConversationHandler.END

async def pf_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel seed change"""
    await update.message.reply_text(f"{pe('cross')} Seed change cancelled.")
    return ConversationHandler.END

async def pf_verify_server_seed_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle server seed input for verification"""
    server_seed = update.message.text.strip()
    context.user_data['pf_verify_server_seed'] = server_seed

    await update.message.reply_text(
        f"{pe('check')} Server seed saved.\n\n"
        f"Now, please enter the <b>Client Seed</b>:",
        parse_mode=ParseMode.HTML
    )

    return PF_VERIFY_INPUT_CLIENT_SEED

async def pf_verify_client_seed_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle client seed input for verification"""
    client_seed = update.message.text.strip()
    context.user_data['pf_verify_client_seed'] = client_seed

    await update.message.reply_text(
        f"{pe('check')} Client seed saved.\n\n"
        f"Now, please enter the <b>Nonce</b> (number):",
        parse_mode=ParseMode.HTML
    )

    return PF_VERIFY_INPUT_NONCE

async def pf_verify_nonce_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle nonce input and calculate result based on game type"""
    try:
        nonce = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid nonce. Please enter a number.")
        return PF_VERIFY_INPUT_NONCE

    context.user_data['pf_verify_nonce'] = nonce
    game = context.user_data.get('pf_verify_game')

    # Games that need additional parameter
    if game in ['mines', 'tower']:
        if game == 'mines':
            await update.message.reply_text(
                f"{pe('check')} Nonce saved.\n\n"
                f"Finally, how many <b>mines</b> were in the game? (1-24):",
                parse_mode=ParseMode.HTML
            )
        else:  # tower
            keyboard = [
                [InlineKeyboardButton("Easy", callback_data="pf_verify_param_easy")],
                [InlineKeyboardButton("Medium", callback_data="pf_verify_param_medium")],
                [InlineKeyboardButton("Hard", callback_data="pf_verify_param_hard")]
            ]
            await update.message.reply_text(
                f"{pe('check')} Nonce saved.\n\n"
                f"Finally, select the <b>Difficulty</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return PF_VERIFY_INPUT_PARAM

    # Calculate and show result for games without additional parameter
    return await pf_verify_calculate_result(update, context)

async def pf_verify_param_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle additional parameter input (mine count)"""
    game = context.user_data.get('pf_verify_game')

    if game == 'mines':
        try:
            mine_count = int(update.message.text.strip())
            if mine_count < 1 or mine_count > 24:
                await update.message.reply_text(f"{pe('cross')} Invalid mine count. Please enter 1-24.")
                return PF_VERIFY_INPUT_PARAM
            context.user_data['pf_verify_param'] = mine_count
        except ValueError:
            await update.message.reply_text(f"{pe('cross')} Invalid input. Please enter a number 1-24.")
            return PF_VERIFY_INPUT_PARAM

    # Calculate and show result
    return await pf_verify_calculate_result(update, context)

async def pf_verify_calculate_result(update_or_query, context: ContextTypes.DEFAULT_TYPE, is_callback=False):
    """Calculate verification result based on game type"""
    server_seed = context.user_data['pf_verify_server_seed']
    client_seed = context.user_data['pf_verify_client_seed']
    nonce = context.user_data['pf_verify_nonce']
    game = context.user_data['pf_verify_game']

    result_text = f"{pe('search')} <b>VERIFICATION RESULT</b>\n\n"
    result_text += f"<b>Server Seed:</b> <code>{server_seed[:20]}...</code>\n"
    result_text += f"<b>Client Seed:</b> <code>{client_seed}</code>\n"
    result_text += f"<b>Nonce:</b> <code>{nonce}</code>\n\n"

    if game == 'coinflip':
        result = get_provably_fair_result(server_seed, client_seed, nonce, 2)
        result_text += f"<b>Calculated Result:</b> {result} ({'Heads' if result == 0 else 'Tails'})\n\n"
        result_text += f"Compare this with your game result!"

    elif game == 'roulette':
        result = get_provably_fair_result(server_seed, client_seed, nonce, 37)
        color = get_roulette_color(result)
        result_text += f"<b>Calculated Result:</b> {result} ({color})\n\n"
        result_text += f"Compare this with your game result!"

    elif game == 'highlow':
        deck = create_deck()
        for i in range(len(deck) - 1, 0, -1):
            j = get_provably_fair_result(server_seed, client_seed, nonce + i, i + 1)
            deck[i], deck[j] = deck[j], deck[i]
        result_text += f"<b>Shuffled Deck (first 10 cards):</b>\n"
        result_text += ", ".join([str(card) for card in deck[:10]])
        result_text += "\n\nCompare with your game's dealt cards!"

    elif game == 'blackjack':
        deck = create_deck()
        for i in range(len(deck) - 1, 0, -1):
            j = get_provably_fair_result(server_seed, client_seed, nonce + i, i + 1)
            deck[i], deck[j] = deck[j], deck[i]
        result_text += f"<b>Shuffled Deck (first 10 cards):</b>\n"
        result_text += ", ".join([str(card) for card in deck[:10]])
        result_text += "\n\nCompare with your game's dealt cards!"

    elif game == 'keno':
        drawn_numbers = []
        offset = 0
        # Use nonce * 1000 to match the actual game algorithm
        base_nonce = nonce * 1000
        while len(drawn_numbers) < 20:
            num = get_provably_fair_result(server_seed, client_seed, base_nonce + offset, 40) + 1
            if num not in drawn_numbers:
                drawn_numbers.append(num)
            offset += 1
        drawn_numbers.sort()
        result_text += f"<b>Drawn Numbers (20):</b>\n"
        result_text += ", ".join(map(str, drawn_numbers))
        result_text += "\n\nCompare with your game's drawn numbers!"

    elif game == 'mines':
        mine_count = context.user_data['pf_verify_param']
        result_text += f"<b>Mine Count:</b> {mine_count}\n\n"
        mine_positions = generate_mine_positions(server_seed, client_seed, nonce, mine_count)
        result_text += f"<b>Mine Positions:</b>\n"
        result_text += ", ".join(map(str, sorted(mine_positions)))
        result_text += "\n\nCompare with the revealed board!"

    elif game == 'tower':
        difficulty = context.user_data['pf_verify_param']
        result_text += f"<b>Difficulty:</b> {difficulty.title()}\n\n"
        snake_positions = generate_tower_positions(server_seed, client_seed, nonce, difficulty)
        result_text += f"<b>Snake Positions (per floor):</b>\n"
        for i, pos in enumerate(snake_positions, 1):
            result_text += f"Floor {i}: Position {pos}\n"
        result_text += "\nCompare with your game's revealed snakes!"

    # Clear user data
    for key in ['pf_verify_game', 'pf_verify_server_seed', 'pf_verify_client_seed', 'pf_verify_nonce', 'pf_verify_param']:
        context.user_data.pop(key, None)

    if is_callback:
        await update_or_query.edit_message_text(result_text, parse_mode=ParseMode.HTML)
    else:
        await update_or_query.message.reply_text(result_text, parse_mode=ParseMode.HTML)

    return ConversationHandler.END

def _build_worker_application():
    """Factory referenced by ``MYCASINO_APP_FACTORY`` (default).

    Returns a fully-built :class:`telegram.ext.Application` with the
    zero-downtime runtime installed and all plugins auto-loaded.
    """
    builder = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(512)
        .get_updates_pool_timeout(30)
        .get_updates_connect_timeout(15)
        .get_updates_read_timeout(15)
        .get_updates_write_timeout(15)
        .connection_pool_size(512)
        .pool_timeout(30)
        .connect_timeout(15)
        .read_timeout(30)
        .write_timeout(30)
    )
    rate_limiter = create_optional_rate_limiter()
    if rate_limiter is not None:
        builder = builder.rate_limiter(rate_limiter)
    app = builder.build()

    try:
        from runtime import register_runtime as _register_runtime
        _register_runtime(app, is_admin=is_admin, autoload_plugins=True)
    except Exception as _e:
        logging.warning(
            f"Worker: zero-downtime runtime not installed: "
            f"{type(_e).__name__}: {_e}",
            exc_info=True,
        )
    return app

