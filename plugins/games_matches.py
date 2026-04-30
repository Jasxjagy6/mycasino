"""Auto-split from bot.py — plugins.games_matches."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

async def show_emoji_game_setup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    game_type: str
):
    """
    Show the new interactive game setup panel for PvB emoji games.
    Stores state in context.user_data under 'eg_setup_{game_type}'.
    """
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Initialize setup state for this game_type
    setup_key = f"eg_setup_{game_type}"
    if setup_key not in context.user_data:
        context.user_data[setup_key] = {
            "mode": "normal",    # normal / crazy
            "rolls": 1,          # 1 / 2 / 3
            "first_to": 1,       # 1 / 2 / 3
            "bet_usd": None,     # float or None (None = not selected)
        }

    state = context.user_data[setup_key]
    balance = get_active_balance_usd(user.id)

    text, keyboard = _build_emoji_setup_ui(game_type, state, balance, user)

    if update.message:
        sent = await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        set_menu_owner(sent, user.id)
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

def _build_emoji_setup_ui(game_type: str, state: dict, balance: float, user) -> tuple:
    """
    Build the text + InlineKeyboardMarkup for the emoji game setup panel.
    Returns (text_str, InlineKeyboardMarkup).
    """
    EMOJI_MAP = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    NAME_MAP  = {"dice": "DICE", "darts": "DARTS", "goal": "GOAL", "bowl": "BOWLING"}
    em = EMOJI_MAP.get(game_type, "🎮")
    name = NAME_MAP.get(game_type, game_type.upper())

    mode      = state.get("mode", "normal")
    rolls     = state.get("rolls", 1)
    first_to  = state.get("first_to", 1)
    bet_usd   = state.get("bet_usd")

    mode_label  = f"{pe('normal') if mode == 'normal' else pe('crazy')} Mode: {'Normal' if mode == 'normal' else 'Crazy'}"
    rolls_label = f"{pe('left')}  {rolls} Roll{'s' if rolls > 1 else ''}  {pe('right')}"
    ft_label    = f"{pe('left')}  First to {first_to}  {pe('right')}"

    # Bet display
    if bet_usd is not None:
        bet_display = f"{pe('money')} Bet: ${bet_usd:.2f}"
    else:
        bet_display = f"{pe('money')} Bet: Not set"

    # --- Message text ---
    mode_desc = "Highest score wins the round" if mode == "normal" else "Lowest score wins the round"
    text = (
        f"{em}  <b>{name}</b> — Play vs Bot\n\n"
        f"Roll against the casino dealer.  {mode_desc}.\n"
        f"First player to <b>{first_to}</b> point(s) wins the match.\n"
        f"Each round: <b>{rolls}</b> roll(s) per player.\n"
        f"{bet_display}"
    )

    uid = user.id
    gt  = game_type

    # --- Keyboard ---
    play_label = f"{pe('play')}  PLAY NOW  {pe('play')}"
    keyboard = [
        [InlineKeyboardButton(play_label, callback_data=f"egsetup_play_{gt}_{uid}")],
        [
            InlineKeyboardButton(mode_label,  callback_data=f"egsetup_mode_{gt}_{uid}"),
            InlineKeyboardButton(rolls_label, callback_data=f"egsetup_rolls_{gt}_{uid}"),
        ],
        [
            InlineKeyboardButton(f"{pe('left')}", callback_data=f"egsetup_ft_dec_{gt}_{uid}"),
            InlineKeyboardButton(ft_label,    callback_data=f"egsetup_ft_mid_{gt}_{uid}"),
            InlineKeyboardButton(f"{pe('right')}", callback_data=f"egsetup_ft_inc_{gt}_{uid}"),
        ],
    ]

    # Bet amount buttons
    if balance > 0:
        pct_bets = [
            ("5%",  round(balance * 0.05, 2)),
            ("10%", round(balance * 0.10, 2)),
            ("25%", round(balance * 0.25, 2)),
            ("50%", round(balance * 0.50, 2)),
        ]
        bet_row1 = [
            InlineKeyboardButton(f"{pct}  ${amt:.2f}", callback_data=f"egsetup_bet_{amt}_{gt}_{uid}")
            for pct, amt in pct_bets
        ]
        bet_row2 = [
            InlineKeyboardButton("All In",  callback_data=f"egsetup_bet_{round(balance,2)}_{gt}_{uid}"),
            InlineKeyboardButton("Custom", callback_data=f"egsetup_bet_custom_{gt}_{uid}"),
        ]
        keyboard.append(bet_row1)
        keyboard.append(bet_row2)
    else:
        keyboard.append([InlineKeyboardButton("Deposit to Play", callback_data="main_deposit")])

    pvp_game_type = gt if gt != 'goal' else 'football'
    keyboard.append([
        InlineKeyboardButton("PvP Info",  callback_data=f"pvp_info_{pvp_game_type}"),
        InlineKeyboardButton("Back",      callback_data="games_emoji_regular"),
    ])

    return text, InlineKeyboardMarkup(keyboard)

async def _start_pvb_from_setup(query, context, game_type, mode, rolls, first_to, bet_usd, user):
    """Directly start a PvB emoji game from the setup panel."""
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if get_active_balance_usd(user.id) < bet_usd:
        await query.answer("Insufficient balance!", show_alert=True)
        return

    ongoing_game_id, ongoing_game_type = get_user_active_emoji_game(user.id)
    if ongoing_game_id:
        game_name = extract_game_name(ongoing_game_type)
        await query.edit_message_text(
            f"{pe('warning')} You already have an ongoing <b>{game_name}</b> match "
            f"(ID: <code>{ongoing_game_id}</code>).\nPlease finish it first!",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        await deduct_wallet_safe(user.id, bet_usd)
    except ValueError:
        await query.answer("Insufficient balance!", show_alert=True)
        return

    context.user_data['game_type']     = game_type
    context.user_data['game_mode']     = mode
    context.user_data['game_rolls']    = rolls
    context.user_data['target_points'] = first_to
    context.user_data['bet_amount']    = bet_usd

    await start_pvb_game_from_context(query, context, user, bet_usd)

async def play_single_emoji_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_key: str, bet_amount_usd: float, bet_amount_currency: float, currency: str):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if game_key not in SINGLE_EMOJI_GAMES:
        await update.message.reply_text("Invalid game.")
        return

    game_config = SINGLE_EMOJI_GAMES[game_key]

    # Check bet limits
    if not await check_bet_limits(update, bet_amount_usd, f'emoji_{game_key}'):
        return

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount_usd)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Insufficient balance.")
        return
    save_user_data(user.id)

    # Send the dice/emoji animation using helper bot in groups
    command_msg_id = update.message.message_id
    dice_msg, used_helper = await smart_roll(context, update.effective_chat.id, game_config['dice_type'], reply_to_message_id=command_msg_id)

    # Wait for the animation to complete
    if used_helper:
        await asyncio.sleep(HELPER_BOT_ANIMATION_DELAY)
    else:
        await asyncio.sleep(4)

    # Check if won
    dice_value = dice_msg.dice.value
    won = game_config['win_condition'](dice_value)

    game_id = generate_unique_id("SE")
    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")
    formatted_bet = f"{currency_symbol}{bet_amount_currency:.2f}"

    # Add game to game_sessions for history tracking
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": f"single_emoji_{game_key}",
        "user_id": user.id,
        "bet_amount": bet_amount_usd,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount_usd / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "status": "completed",
        "timestamp": str(datetime.now(timezone.utc)),
        "win": won,
        "multiplier": game_config['multiplier'] if won else 0,
        "dice_value": dice_value,
        "game_name": game_config['name']
    }

    if won:
        winnings_usd = bet_amount_usd * game_config['multiplier']
        winnings_currency = bet_amount_currency * game_config['multiplier']
        credit_wallet(user.id, winnings_usd)
        await update_stats_on_bet(user.id, game_id, bet_amount_usd, True, multiplier=game_config['multiplier'], context=context)
        update_pnl(user.id)
        save_user_data(user.id)

        await update.message.reply_text(
            f"{pe('win')} <b>YOU WON!</b>\n\n"
            f"{game_config['emoji']} {game_config['win_description']}!\n"
            f"Bet: {formatted_bet}\n"
            f"Won: {currency_symbol}{winnings_currency:.2f} ({game_config['multiplier']}x)\n\n"
            f"Game ID: <code>{game_id}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await update_stats_on_bet(user.id, game_id, bet_amount_usd, False, multiplier=0, context=context)
        update_pnl(user.id)
        save_user_data(user.id)

        await update.message.reply_text(
            f"😔 <b>You lost</b>\n\n"
            f"Better luck next time!\n"
            f"Lost: {formatted_bet}\n\n"
            f"Game ID: <code>{game_id}</code>",
            parse_mode=ParseMode.HTML
        )

async def execute_group_challenge_game(update: Update, context: ContextTypes.DEFAULT_TYPE, match_id: str):
    """Initialize group challenge game - actual rolls are handled by message_listener"""
    match = game_sessions.get(match_id)
    if not match:
        return

    game_type = match["game_type"].replace("group_challenge_", "")
    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(game_type, "🎮")

    # Initialize game state for turn-based play
    match["players"] = [match["host_id"], match["opponent_id"]]
    match["usernames"] = {
        match["host_id"]: match["host_username"],
        match["opponent_id"]: match["opponent_username"]
    }
    match["player_rolls"] = {match["host_id"]: [], match["opponent_id"]: []}
    match["points"] = {match["host_id"]: 0, match["opponent_id"]: 0}
    match["target_points"] = match.get("target_score", 1)  # Use target_points for consistency
    match["game_mode"] = match.get("mode", "normal")
    match["game_rolls"] = match.get("rolls", 1)
    match["last_roller"] = None
    match["current_round"] = 1

    # PERFORMANCE: proactively index both players.
    _index_user_game(match["host_id"], match_id)
    _index_user_game(match["opponent_id"], match_id)

    mode_desc = "Highest wins" if match["mode"] == "normal" else "Lowest wins"

    await context.bot.send_message(
        match["chat_id"],
        f"{emoji} <b>ROUND 1</b> {emoji}\n\n"
        f"Mode: {match['mode'].title()} ({mode_desc})\n"
        f"Target: First to {match.get('target_score', 1)} wins!\n\n"
        f"<b>{display_at(match['host_username'])}, your turn!</b>\n"
        f"Send {match['rolls']} {emoji} to start!",
        parse_mode=ParseMode.HTML
    )

async def play_vs_bot_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str, target_score: int):
    user = update.effective_user
    bet_amount = context.user_data['bet_amount']
    game_mode = context.user_data.get('game_mode', 'normal')  # normal or crazy
    game_rolls = context.user_data.get('game_rolls', 1)  # 1, 2, or 3 rolls
    bot_rolls_first = context.user_data.get('bot_rolls_first', False)  # NEW: who rolls first
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not await check_bet_limits(update, bet_amount, f'pvb_{game_type}'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await update.message.reply_text("You no longer have enough balance for this bet. Game cancelled.")
        return
    save_user_data(user.id)

    game_id = generate_unique_id("PVB")
    # Handle different game_type naming variations
    emoji_map = {
        "dice": "🎲", "dice_bot": "🎲",
        "darts": "🎯",
        "goal": "⚽", "football": "⚽",
        "bowl": "🎳", "bowling": "🎳"
    }

    mode_text = "Highest total score wins" if game_mode == "normal" else "Lowest total score wins"

    # Get the emoji for this game type
    emoji = emoji_map.get(game_type, "🎲")  # Default to dice if not found

    # Create game session
    game_sessions[game_id] = {
        "id": game_id, "game_type": f"pvb_{game_type}", "user_id": user.id,
        "chat_id": update.effective_chat.id,  # Track chat for isolation
        "bet_amount": bet_amount, "status": "active", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "target_score": target_score, "current_round": 1,
        "user_score": 0, "bot_score": 0,
        "bot_rolls": [],
        "user_rolls": [],
        "game_mode": game_mode,
        "game_rolls": game_rolls,
        "history": [],
        "bot_rolls_first": bot_rolls_first,
        "round_timeout": default_round_timeout,  # Store timeout at creation time
        "waiting_for": "bot" if bot_rolls_first else "user",  # Tracks whose turn: 'bot' or 'user'
        "command_message_id": update.message.message_id if hasattr(update, 'message') and update.message else None  # For tagging in groups
    }
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    # Store in BOTH context.chat_data AND global dict for reliability
    context.chat_data[f"active_pvb_game_{user.id}"] = game_id
    active_pvb_games[user.id] = game_id  # Global fallback

    chat_id = update.effective_chat.id

    if bot_rolls_first:
        # Bot rolls first
        # Set flag to prevent user from rolling during bot's initial roll
        game_sessions[game_id]['bot_is_rolling'] = True

        await update.message.reply_text(
            f"{pe('game')} {game_type.capitalize()} vs Bot started! (ID: <code>{game_id}</code>)\n"
            f"<b>Mode:</b> {game_mode.capitalize()} ({mode_text})\n"
            f"<b>Rolls per round:</b> {game_rolls}\n"
            f"<b>Target:</b> First to {target_score} points wins ${bet_amount*1.96:.2f}.\n\n"
            f"<b>Bot is rolling first...</b>",
            parse_mode=ParseMode.HTML
        )

        # Bot rolls - use multi_roll_parallel for lightning-fast speed
        bot_rolls = []
        telegram_emoji = emoji
        command_msg_id = game_sessions[game_id].get('command_message_id')
        try:
            rolls_data = await multi_roll_parallel(context, chat_id, telegram_emoji, game_rolls, reply_to_message_id=command_msg_id)
            for msg, _ in rolls_data:
                bot_rolls.append(msg.dice.value)
        except Exception as e:
            logging.error(f"Error sending dice in PvB game: {e}")
            await update.message.reply_text(f"{pe('cross')} An error occurred. Game terminated.")
            game_sessions[game_id].pop('bot_is_rolling', None)
            game_sessions[game_id]['status'] = 'error'
            context.chat_data.pop(f"active_pvb_game_{user.id}", None)
            if user.id in active_pvb_games:
                del active_pvb_games[user.id]
            credit_wallet(user.id, bet_amount)
            update_pnl(user.id)
            save_user_data(user.id)
            return

        game_sessions[game_id]["bot_rolls"] = bot_rolls
        bot_total = sum(bot_rolls)
        bot_rolls_text = " + ".join(str(r) for r in bot_rolls)

        # Clear rolling flags and set waiting_for to user
        game_sessions[game_id].pop('bot_is_rolling', None)
        game_sessions[game_id]["waiting_for"] = "user"

        # GREEN cashout button below (dynamic multiplier based on win probability)
        _co_round = game_sessions[game_id].get("current_round", 1)
        _co_mult = calculate_cashout_multiplier(game_sessions[game_id], user_id=user.id)
        _co_kb = _build_pvb_cashout_keyboard(game_id, _co_round, _co_mult)

        _co_sent = await update.message.reply_text(
            f"{pe('robot')} Bot rolled: {bot_rolls_text} = <b>{bot_total}</b>\n\n"
            f"{user.mention_html()}, <b>Your turn!</b> Send {game_rolls} {emoji} emoji{'s' if game_rolls > 1 else ''} to respond.\n"
            f"Or tap Cashout to collect <b>${bet_amount * _co_mult:.2f}</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=_co_kb
        )
        _register_cashout_button(game_id, user.id, chat_id, _co_round,
                                 message_id=getattr(_co_sent, 'message_id', None))

        # Schedule PvB timeout
        if context.job_queue:
            _cancel_pvb_timeout_jobs(context, user.id, game_id)
            round_timeout = game_sessions[game_id].get('round_timeout', default_round_timeout)
            warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
            context.job_queue.run_once(
                pvb_timeout_warn_job,
                when=warn_time,
                data={'user_id': user.id, 'game_id': game_id, 'chat_id': chat_id},
                name=f"pvb_warn_{game_id}"
            )
            context.job_queue.run_once(
                pvb_timeout_finish_job,
                when=round_timeout,
                data={'user_id': user.id, 'game_id': game_id, 'chat_id': chat_id},
                name=f"pvb_finish_{game_id}"
            )
    else:
        # User rolls first (default) - GREEN cashout button visible from the start at ~0.93x
        _co_round = game_sessions[game_id].get("current_round", 1)
        _co_mult = calculate_cashout_multiplier(game_sessions[game_id], user_id=user.id)
        _co_kb = _build_pvb_cashout_keyboard(game_id, _co_round, _co_mult)

        _co_sent = await update.message.reply_text(
            f"{pe('game')} {game_type.capitalize()} vs Bot started! (ID: <code>{game_id}</code>)\n"
            f"<b>Mode:</b> {game_mode.capitalize()} ({mode_text})\n"
            f"<b>Rolls per round:</b> {game_rolls}\n"
            f"<b>Target:</b> First to {target_score} points wins ${bet_amount*1.96:.2f}.\n\n"
            f"{user.mention_html()}, <b>Your turn first! Send {game_rolls} {emoji} emoji{'s' if game_rolls > 1 else ''} to start.</b>\n"
            f"Or tap Cashout to collect <b>${bet_amount * _co_mult:.2f}</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=_co_kb
        )
        _register_cashout_button(game_id, user.id, chat_id, _co_round,
                                 message_id=getattr(_co_sent, 'message_id', None))

        # Schedule PvB timeout
        if context.job_queue:
            _cancel_pvb_timeout_jobs(context, user.id, game_id)
            round_timeout = game_sessions[game_id].get('round_timeout', default_round_timeout)
            warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
            context.job_queue.run_once(
                pvb_timeout_warn_job,
                when=warn_time,
                data={'user_id': user.id, 'game_id': game_id, 'chat_id': chat_id},
                name=f"pvb_warn_{game_id}"
            )
            context.job_queue.run_once(
                pvb_timeout_finish_job,
                when=round_timeout,
                data={'user_id': user.id, 'game_id': game_id, 'chat_id': chat_id},
                name=f"pvb_finish_{game_id}"
            )

    if DEBUG_EMOJI_GAMES:
        logging.info(f"PvB game created: game_id={game_id}, user_id={user.id}, bot_rolls_first={bot_rolls_first}")

def _cancel_pvp_timeout_jobs(context, match_id):
    """Cancel any pending PvP timeout jobs for a match."""
    if context.job_queue:
        for job in context.job_queue.get_jobs_by_name(f"pvp_warn_{match_id}"):
            job.schedule_removal()
        for job in context.job_queue.get_jobs_by_name(f"pvp_finish_{match_id}"):
            job.schedule_removal()

async def pvp_timeout_warn_job(context: ContextTypes.DEFAULT_TYPE):
    """Warn the idle PvP player with 60 seconds (or 25% of timeout) left in the round."""
    data = context.job.data
    match_id = data['match_id']
    chat_id = data['chat_id']
    waiting_user_id = data['waiting_user_id']

    match_data = game_sessions.get(match_id)
    if not match_data or match_data.get('status') != 'active':
        return  # Game already resolved

    timeout = match_data.get('round_timeout', default_round_timeout)
    warn_seconds = 60 if timeout > 60 else max(5, int(timeout * 0.25))

    waiting_username = match_data.get('usernames', {}).get(waiting_user_id, f"User {waiting_user_id}")
    mention = f'<a href="tg://user?id={waiting_user_id}">@{waiting_username}</a>'
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{pe('warning')} {mention}, you have <b>{warn_seconds} seconds</b> left to roll or you will lose this round!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.warning(f"Could not send PvP timeout warning for match {match_id}: {e}")

async def pvp_timeout_finish_job(context: ContextTypes.DEFAULT_TYPE):
    """Auto-award the round to the player who rolled after opponent timeout."""
    data = context.job.data
    match_id = data['match_id']
    chat_id = data['chat_id']
    rolling_user_id = data['rolling_user_id']

    match_data = game_sessions.get(match_id)
    if not match_data or match_data.get('status') != 'active':
        return  # Game already resolved

    players = match_data.get('players', [])
    if rolling_user_id not in players:
        return

    idle_user_id = [pid for pid in players if pid != rolling_user_id][0]

    # CRITICAL: Check if idle user has already rolled (race condition fix)
    idle_rolls = match_data.get('player_rolls', {}).get(idle_user_id, [])
    if len(idle_rolls) > 0:
        # Idle user already rolled, cancel this timeout
        return

    timeout = match_data.get('round_timeout', default_round_timeout)

    rolling_username = match_data.get('usernames', {}).get(rolling_user_id, f"User {rolling_user_id}")
    idle_username = match_data.get('usernames', {}).get(idle_user_id, f"User {idle_user_id}")
    # Don't show @ for Bot
    rolling_display = rolling_username if rolling_user_id == 0 else display_at(rolling_username)
    idle_display = idle_username if idle_user_id == 0 else display_at(idle_username)
    rolling_mention = f'<a href="tg://user?id={rolling_user_id}">{rolling_display}</a>'
    idle_mention = f'<a href="tg://user?id={idle_user_id}">{idle_display}</a>'

    # Award the round to the active player
    # Ensure points dict has both players
    p1, p2 = players
    if p1 not in match_data.get("points", {}):
        match_data.setdefault("points", {})[p1] = 0
    if p2 not in match_data.get("points", {}):
        match_data.setdefault("points", {})[p2] = 0
    match_data["points"][rolling_user_id] += 1

    text = f"⏰ <b>Round Timeout!</b>\n\n"
    text += f"{idle_mention} failed to roll within {timeout} seconds.\n"
    text += f"{pe('win')} {rolling_mention} wins this round!\n\n"
    text += f"<b>Score:</b> {match_data.get('usernames', {}).get(p1, f'Player {p1}')} {match_data['points'][p1]} - {match_data['points'][p2]} {match_data.get('usernames', {}).get(p2, f'Player {p2}')}\n\n"

    target = match_data.get("target_points", match_data.get("target_score", 1))

    # Check if someone won the match
    if match_data["points"].get(p1, 0) >= target or match_data["points"].get(p2, 0) >= target:
        final_winner = p1 if match_data["points"].get(p1, 0) >= target else p2
        loser_id = p2 if final_winner == p1 else p1
        match_data.update({"status": "completed", "winner_id": final_winner})

        # Resolve side bets for this match
        winner_index = "p1" if final_winner == p1 else "p2"
        asyncio.ensure_future(resolve_sidebets_for_match(match_id, winner_index, context))

        bet_amount = match_data.get("bet_amount_usd", match_data.get("bet_amount", 0))
        winnings = bet_amount * 1.94

        final_winner_username = match_data.get('usernames', {}).get(final_winner, f"Player {final_winner}")
        # Don't show @ for Bot
        final_winner_display = final_winner_username if final_winner == 0 else display_at(final_winner_username)
        final_winner_mention = f'<a href="tg://user?id={final_winner}">{final_winner_display}</a>'

        if final_winner != 0:
            credit_wallet(final_winner, winnings)
            await update_stats_on_bet(final_winner, match_id, bet_amount, True, pvp_win=True, multiplier=1.94, context=context)
            update_pnl(final_winner)
            save_user_data(final_winner)
            if 'game_sessions' not in user_stats[final_winner]:
                user_stats[final_winner]['game_sessions'] = []
            user_stats[final_winner]['game_sessions'].append(match_id)

        if loser_id != 0:
            await update_stats_on_bet(loser_id, match_id, bet_amount, False, context=context)
            update_pnl(loser_id)
            save_user_data(loser_id)
            if 'game_sessions' not in user_stats[loser_id]:
                user_stats[loser_id]['game_sessions'] = []
            user_stats[loser_id]['game_sessions'].append(match_id)

        text += f"{pe('trophy')} <b>{final_winner_mention} wins the match and earns ${winnings:.2f}!</b>"
        # Emoji-game match messages are no longer pinned, so nothing to unpin.
    else:
        # Continue to next round - player who rolled (winner) rolls first
        match_data["last_roller"] = None
        match_data["player_rolls"] = {p1: [], p2: []}
        next_first = rolling_user_id  # Player who rolled wins the round and rolls first
        next_first_username = match_data.get('usernames', {}).get(next_first, f"Player {next_first}")
        gtype = match_data.get("game_type", "pvp_dice").replace("pvp_", "").replace("group_challenge_", "").replace("xdxw_", "")
        emoji_map = {"dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3"}
        emoji = emoji_map.get(gtype, "\U0001f3b2")
        game_rolls = match_data.get("game_rolls", 1)
        text += f"Next round: {next_first_username} rolls first! Send {game_rolls} {emoji} to continue."

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Could not send PvP timeout result for match {match_id}: {e}")

def _cancel_pvb_timeout_jobs(context, user_id, game_id=None):
    """Cancel any pending PvB timeout jobs for a user."""
    if context.job_queue:
        # Cancel jobs for specific game if game_id provided
        if game_id:
            for job in context.job_queue.get_jobs_by_name(f"pvb_warn_{game_id}"):
                job.schedule_removal()
            for job in context.job_queue.get_jobs_by_name(f"pvb_finish_{game_id}"):
                job.schedule_removal()
        # Also cancel all user-level jobs (backward compat)
        for job in context.job_queue.get_jobs_by_name(f"pvb_warn_{user_id}"):
            job.schedule_removal()
        for job in context.job_queue.get_jobs_by_name(f"pvb_finish_{user_id}"):
            job.schedule_removal()

async def pvb_timeout_warn_job(context: ContextTypes.DEFAULT_TYPE):
    """Warn the idle PvB player with 60 seconds (or 25% of timeout) left in the round."""
    data = context.job.data
    user_id = data['user_id']
    game_id = data['game_id']

    game = game_sessions.get(game_id)
    if not game or game.get('status') != 'active':
        return  # Game already resolved

    timeout = game.get('round_timeout', default_round_timeout)
    warn_seconds = 60 if timeout > 60 else max(5, int(timeout * 0.25))

    username = user_stats.get(user_id, {}).get('userinfo', {}).get('username') or user_stats.get(user_id, {}).get('userinfo', {}).get('first_name') or f"Player"

    try:
        await context.bot.send_message(
            chat_id=data['chat_id'],
            text=f"{pe('warning')} @{username}, you have <b>{warn_seconds} seconds</b> left to roll or the bot will win this round!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.warning(f"Could not send PvB timeout warning for game {game_id}: {e}")

async def pvb_timeout_finish_job(context: ContextTypes.DEFAULT_TYPE):
    """Auto-award the round to the bot after user timeout. Continue to next round or end match."""
    data = context.job.data
    user_id = data['user_id']
    game_id = data['game_id']

    game = game_sessions.get(game_id)
    if not game or game.get('status') != 'active':
        return  # Game already resolved

    # Prevent duplicate timeout processing
    if game.get('timeout_processing'):
        return  # Already processing a timeout
    game['timeout_processing'] = True

    # CRITICAL: Check if user has already rolled (race condition fix)
    user_rolls = game.get('user_rolls', [])
    if len(user_rolls) > 0:
        # User already rolled, cancel this timeout
        game.pop('timeout_processing', None)
        return

    timeout = game.get('round_timeout', default_round_timeout)
    chat_id = data['chat_id']

    # Ensure score fields exist (defensive for old game sessions)
    if 'bot_score' not in game:
        game['bot_score'] = 0
    if 'user_score' not in game:
        game['user_score'] = 0

    # Bot wins this round
    game["bot_score"] += 1

    text = f"⏰ <b>Round Timeout!</b>\n\n"
    text += f"You failed to roll within {timeout} seconds.\n"
    text += f"{pe('robot')} Bot wins this round!\n\n"
    text += f"<b>Score:</b> You {game['user_score']} - {game['bot_score']} Bot\n\n"

    target = game.get("target_score", 1)

    if game["bot_score"] >= target:
        # Bot wins the match
        game['status'] = 'completed'
        game['win'] = False
        bet_amount = game.get("bet_amount", 0)
        await update_stats_on_bet(user_id, game_id, bet_amount, False, context=context)
        update_pnl(user_id)
        save_user_data(user_id)

        if user_id in active_pvb_games:
            del active_pvb_games[user_id]

        text += f"{pe('lose')} Bot wins the match ({game['bot_score']}-{game['user_score']}). You lost {format_for_user(user_id, bet_amount)}."

        # Send final match result
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Could not send PvB timeout result for game {game_id}: {e}")
    else:
        # Send round timeout message first
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Could not send PvB timeout result for game {game_id}: {e}")

        # Continue to next round - bot rolls first for next round
        game["current_round"] += 1
        game['user_rolls'] = []
        game['bot_rolls'] = []
        game['waiting_for'] = 'bot'  # Set to bot while it's rolling

        # Bot rolls for the new round
        game_type = game['game_type'].replace("pvb_", "").replace("xdxw_", "")
        emoji_map = {"dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3", "bowling": "\U0001f3b3", "football": "\u26bd", "dice_bot": "\U0001f3b2"}
        expected_emoji = emoji_map.get(game_type, "\U0001f3b2")
        game_rolls = game.get('game_rolls', 1)

        bot_rolls = []
        try:
            command_msg_id = game.get('command_message_id')
            rolls_data = await multi_roll_parallel(context, chat_id, expected_emoji, game_rolls, reply_to_message_id=command_msg_id)
            for msg, _ in rolls_data:
                bot_rolls.append(msg.dice.value)

            game["bot_rolls"] = bot_rolls
            # Store bot rolls in game session (not context.user_data which is None in job queue)
            game['pre_rolled_bot_values'] = bot_rolls
            game['waiting_for'] = 'user'  # Now it's user's turn
            bot_total = sum(bot_rolls)
            bot_rolls_text = " + ".join(str(r) for r in bot_rolls)

            username_display = user_stats.get(user_id, {}).get('userinfo', {}).get('username') or user_stats.get(user_id, {}).get('userinfo', {}).get('first_name') or f"Player"

            # Send "Your turn" message AFTER bot rolls
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{pe('robot')} <b>BOT ROLLED FIRST!</b>\n\n"
                     f"Bot rolled: [{bot_rolls_text}] = <b>{bot_total}</b>\n\n"
                     f"{username_display}, Your turn! Send {game_rolls} {expected_emoji} to respond.",
                parse_mode=ParseMode.HTML
            )

            # Schedule timeout for the new round
            if context.job_queue:
                _cancel_pvb_timeout_jobs(context, user_id, game_id)
                round_timeout = game.get('round_timeout', default_round_timeout)
                warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
                context.job_queue.run_once(
                    pvb_timeout_warn_job,
                    when=warn_time,
                    data={'user_id': user_id, 'game_id': game_id, 'chat_id': chat_id},
                    name=f"pvb_warn_{game_id}"
                )
                context.job_queue.run_once(
                    pvb_timeout_finish_job,
                    when=round_timeout,
                    data={'user_id': user_id, 'game_id': game_id, 'chat_id': chat_id},
                    name=f"pvb_finish_{game_id}"
                )

            # Clear the flag so next round can process timeouts
            game.pop('timeout_processing', None)
        except Exception as e:
            logging.error(f"Error sending bot rolls after PvB timeout: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{pe('warning')} Error continuing game. Please contact support.",
                parse_mode=ParseMode.HTML
            )
            game['status'] = 'error'
            game.pop('timeout_processing', None)
            if user_id in active_pvb_games:
                del active_pvb_games[user_id]
            credit_wallet(user_id, game.get('bet_amount', 0))
            update_pnl(user_id)
            save_user_data(user_id)

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Could not send PvB timeout result for game {game_id}: {e}")

@check_banned
@check_maintenance
async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False, page=0):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_game_ids = user_stats[user.id].get("game_sessions", [])

    if not user_game_ids:
        text = "You haven't played any matches yet."
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Back to Wallet", callback_data="main_wallet")]]) if from_callback else None
        if from_callback: await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else: await update.message.reply_text(text, reply_markup=reply_markup)
        return

    all_games = [game_sessions[gid] for gid in reversed(user_game_ids) if gid in game_sessions]
    pending_games = [g for g in all_games if g.get("status") == "active"]
    completed_games = [g for g in all_games if g.get("status") != "active"]

    msg = ""
    # Display pending games first, always
    if pending_games:
        msg += "⏳ <b>Your Pending/Active Games:</b>\n\n"
        for game in pending_games:
            game_type = game['game_type'].replace('_', ' ').title()
            coin = game.get('active_currency', 'USDT')
            crypto_bet = game.get('crypto_bet_amount', game['bet_amount'])
            formatted_crypto = format_crypto_amount(crypto_bet, coin)
            msg += (f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"
                    f"<b>Bet:</b> ${game['bet_amount']:.2f} ({formatted_crypto} {coin}) | <b>Status:</b> {game['status'].capitalize()}\n"
                    f"Use <code>/continue {game['id']}</code> to resume.\n"
                    "--------------------\n")

    # Paginated completed games
    page_size = 10
    start_index = page * page_size
    end_index = start_index + page_size
    paginated_completed = completed_games[start_index:end_index]

    msg += f"📜 <b>Your Completed Games (Page {page + 1}):</b>\n\n"
    if not paginated_completed:
        msg += "No completed games on this page.\n"

    for game in paginated_completed:
        game_type = game['game_type'].replace('_', ' ').title()
        coin = game.get('active_currency', 'USDT')
        crypto_bet = game.get('crypto_bet_amount', game['bet_amount'])
        formatted_crypto = format_crypto_amount(crypto_bet, coin)
        msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"

        # Determine win/loss/push status text
        if game.get('win') is True:
            win_status = "Win"
        elif game.get('win') is False:
            win_status = "Loss"
        else: # Covers push (None) or other statuses
            win_status = game['status'].capitalize()

        msg += f"<b>Bet:</b> ${game['bet_amount']:.2f} ({formatted_crypto} {coin}) | <b>Result:</b> {win_status}\n"

        # Add game-specific details
        if game['game_type'] == 'blackjack':
            player_val = calculate_hand_value(game.get('player_hand', []))
            dealer_val = calculate_hand_value(game.get('dealer_hand', []))
            msg += f"<b>Hand:</b> {player_val} vs <b>Dealer:</b> {dealer_val}\n"
        elif game['game_type'] in ['mines', 'tower', 'coin_flip']:
            multiplier = game.get('multiplier', 0)
            msg += f"<b>Multiplier:</b> {multiplier:.2f}x\n"
        elif 'players' in game: # PvP
            p1_id, p2_id = game['players']
            p1_name = game['usernames'].get(p1_id, f"ID:{p1_id}")
            p2_name = game['usernames'].get(p2_id, f"ID:{p2_id}")
            score = f"{game['points'].get(p1_id, 0)} - {game['points'].get(p2_id, 0)}"
            msg += f"<b>Match:</b> {p1_name} vs {p2_name}\n<b>Score:</b> {score}\n"

        msg += "--------------------\n"

    # Pagination Keyboard
    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(f"{pe('left')} Previous", callback_data=f"my_matches_{page - 1}"))
    if end_index < len(completed_games):
        nav_row.append(InlineKeyboardButton(f"Next {pe('arrow_right')}", callback_data=f"my_matches_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("Back to Wallet", callback_data="main_wallet")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_callback:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

@check_banned
@check_maintenance
async def deals_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False, page=0):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_deal_ids = user_stats[user.id].get("escrow_deals", [])

    if not user_deal_ids:
        text = "You have no escrow deals."
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Back to Wallet", callback_data="main_wallet")]]) if from_callback else None
        if from_callback: await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else: await update.message.reply_text(text, reply_markup=reply_markup)
        return

    all_deals = []
    for deal_id in reversed(user_deal_ids):
        deal = escrow_deals.get(deal_id)
        if not deal and os.path.exists(os.path.join(ESCROW_DIR, f"{deal_id}.json")):
            with open(os.path.join(ESCROW_DIR, f"{deal_id}.json"), "r") as f: deal = json.load(f)
        if deal: all_deals.append(deal)

    page_size = 10
    start_index = page * page_size
    end_index = start_index + page_size
    paginated_deals = all_deals[start_index:end_index]

    msg = f"🛡️ <b>Your Escrow Deals (Page {page + 1}):</b>\n\n"
    if not paginated_deals:
        msg += "No deals on this page.\n"

    for deal in paginated_deals:
        seller_name = deal['seller'].get('username') or f"ID:{deal['seller']['id']}"
        buyer_name = deal['buyer'].get('username') or f"ID:{deal['buyer']['id']}"
        role = "Seller" if user.id == deal['seller']['id'] else "Buyer"
        msg += (f"<b>Deal ID:</b> <code>{deal['id']}</code>\n<b>Your Role:</b> {role}\n"
                f"<b>Amount:</b> ${deal['amount']:.2f} USDT\n<b>Seller:</b> @{seller_name}\n<b>Buyer:</b> @{buyer_name}\n"
                f"<b>Status:</b> {deal['status'].replace('_', ' ').capitalize()}\n--------------------\n")

    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(f"{pe('left')} Previous", callback_data=f"my_deals_{page - 1}"))
    if end_index < len(all_deals):
        nav_row.append(InlineKeyboardButton(f"Next {pe('arrow_right')}", callback_data=f"my_deals_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("Back to Wallet", callback_data="main_wallet")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_callback: await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else: await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

@check_banned
@check_maintenance
async def single_emoji_bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dedicated handler for single emoji game bet input. Registered before all other text handlers."""
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    if user.id not in awaiting_single_emoji_bet or not update.message.text:
        return

    game_key = awaiting_single_emoji_bet[user.id]
    if game_key not in SINGLE_EMOJI_GAMES:
        del awaiting_single_emoji_bet[user.id]
        return

    try:
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(update.message.text, user.id)

        if get_active_balance_usd(user.id) < bet_amount_usd:
            await send_insufficient_balance_message(update)
            del awaiting_single_emoji_bet[user.id]
            return

        del awaiting_single_emoji_bet[user.id]
        await play_single_emoji_game(update, context, game_key, bet_amount_usd, bet_amount_currency, currency)
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a valid number or 'all'.")
    except Exception as e:
        logging.error(f"Single emoji game error for user {user.id}: {e}", exc_info=True)
        awaiting_single_emoji_bet.pop(user.id, None)
        await update.message.reply_text(f"Error: {str(e)}")

@check_banned
@check_maintenance
async def play_vs_bot_game_from_callback(query, context: ContextTypes.DEFAULT_TYPE, game_type: str, target_score: int):
    """Start PvB game from a callback query (used when bot rolls first is selected)"""
    user = query.from_user
    bet_amount = context.user_data['bet_amount']
    game_mode = context.user_data.get('game_mode', 'normal')
    game_rolls = context.user_data.get('game_rolls', 1)
    bot_rolls_first = context.user_data.get('bot_rolls_first', False)

    await ensure_user_in_wallets(user.id, user.username, context=context)

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="You no longer have enough balance for this bet. Game cancelled."
        )
        return
    save_user_data(user.id)

    game_id = generate_unique_id("PVB")
    emoji_map = {
        "dice": "🎲", "dice_bot": "🎲",
        "darts": "🎯",
        "goal": "⚽", "football": "⚽",
        "bowl": "🎳", "bowling": "🎳"
    }

    mode_text = "Highest total score wins" if game_mode == "normal" else "Lowest total score wins"
    emoji = emoji_map.get(game_type, "🎲")

    # Create game session
    game_sessions[game_id] = {
        "id": game_id, "game_type": f"pvb_{game_type}", "user_id": user.id,
        "chat_id": query.message.chat_id,  # Track chat for isolation
        "bet_amount": bet_amount, "status": "active", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "target_score": target_score, "current_round": 1,
        "user_score": 0, "bot_score": 0,
        "bot_rolls": [],
        "user_rolls": [],
        "game_mode": game_mode,
        "game_rolls": game_rolls,
        "history": [],
        "bot_rolls_first": bot_rolls_first,
        "round_timeout": default_round_timeout,  # Store timeout at creation time
        "waiting_for": "bot" if bot_rolls_first else "user",  # Track whose turn it is
        "command_message_id": query.message.message_id if hasattr(query, 'message') and query.message else None  # For tagging in groups
    }

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    # Store in both context.chat_data and global dict
    context.chat_data[f"active_pvb_game_{user.id}"] = game_id
    active_pvb_games[user.id] = game_id

    chat_id = query.message.chat_id

    if bot_rolls_first:
        # Bot rolls first
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{pe('game')} {game_type.capitalize()} vs Bot started! (ID: <code>{game_id}</code>)\n"
                 f"<b>Mode:</b> {game_mode.capitalize()} ({mode_text})\n"
                 f"<b>Rolls per round:</b> {game_rolls}\n"
                 f"<b>Target:</b> First to {target_score} points wins ${bet_amount*1.96:.2f}.\n\n"
                 f"<b>Bot is rolling first...</b>",
            parse_mode=ParseMode.HTML
        )

        # Bot rolls
        bot_rolls = []
        # Use the emoji directly for Telegram sendDice
        telegram_emoji = emoji
        command_msg_id = game_sessions[game_id].get('command_message_id')

        # Bot rolls - use multi_roll_parallel for lightning-fast speed
        try:
            rolls_data = await multi_roll_parallel(context, chat_id, telegram_emoji, game_rolls, reply_to_message_id=command_msg_id)
            for msg, _ in rolls_data:
                bot_rolls.append(msg.dice.value)
        except Exception as e:
            logging.error(f"Error sending dice in PvB game: {e}")
            await context.bot.send_message(chat_id=chat_id, text=f"{pe('cross')} An error occurred. Game terminated.")
            game_sessions[game_id]['status'] = 'error'
            context.chat_data.pop(f"active_pvb_game_{user.id}", None)
            if user.id in active_pvb_games:
                del active_pvb_games[user.id]
            credit_wallet(user.id, bet_amount)
            update_pnl(user.id)
            save_user_data(user.id)
            return

        game_sessions[game_id]["bot_rolls"] = bot_rolls
        bot_total = sum(bot_rolls)
        bot_rolls_text = ROLL_SEPARATOR.join(str(r) for r in bot_rolls)

        game_sessions[game_id]["waiting_for"] = "user"

        # GREEN cashout button below
        _co_round = game_sessions[game_id].get("current_round", 1)
        _co_mult = calculate_cashout_multiplier(game_sessions[game_id], user_id=user.id)
        _co_kb = _build_pvb_cashout_keyboard(game_id, _co_round, _co_mult)

        username_display = user.first_name if user.first_name else "Player"
        _co_sent = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{pe('robot')} <b>BOT ROLLED FIRST!</b>\n\n"
                 f"Bot rolled: [{bot_rolls_text}] = {bot_total}\n\n"
                 f"{username_display}, Your turn! Send {game_rolls} {emoji} to respond.\n"
                 f"Or tap Cashout to collect <b>${bet_amount * _co_mult:.2f}</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=_co_kb
        )
        _register_cashout_button(game_id, user.id, chat_id, _co_round,
                                 message_id=getattr(_co_sent, 'message_id', None))

        # Schedule PvB timeout
        if context.job_queue:
            _cancel_pvb_timeout_jobs(context, user.id, game_id)
            round_timeout = game_sessions[game_id].get('round_timeout', default_round_timeout)
            warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
            context.job_queue.run_once(
                pvb_timeout_warn_job,
                when=warn_time,
                data={'user_id': user.id, 'game_id': game_id, 'chat_id': chat_id},
                name=f"pvb_warn_{game_id}"
            )
            context.job_queue.run_once(
                pvb_timeout_finish_job,
                when=round_timeout,
                data={'user_id': user.id, 'game_id': game_id, 'chat_id': chat_id},
                name=f"pvb_finish_{game_id}"
            )
    else:
        # User rolls first (default) - GREEN cashout button visible from the start
        _co_round = game_sessions[game_id].get("current_round", 1)
        _co_mult = calculate_cashout_multiplier(game_sessions[game_id], user_id=user.id)
        _co_kb = _build_pvb_cashout_keyboard(game_id, _co_round, _co_mult)

        _co_sent = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{pe('game')} {game_type.capitalize()} vs Bot started! (ID: <code>{game_id}</code>)\n"
                 f"<b>Mode:</b> {game_mode.capitalize()} ({mode_text})\n"
                 f"<b>Rolls per round:</b> {game_rolls}\n"
                 f"<b>Target:</b> First to {target_score} points wins ${bet_amount*1.96:.2f}.\n\n"
                 f"<b>Your turn first! Send {game_rolls} {emoji} emoji{'s' if game_rolls > 1 else ''} to start.</b>\n"
                 f"Or tap Cashout to collect <b>${bet_amount * _co_mult:.2f}</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=_co_kb
        )
        _register_cashout_button(game_id, user.id, chat_id, _co_round,
                                 message_id=getattr(_co_sent, 'message_id', None))

        # Schedule PvB timeout
        if context.job_queue:
            _cancel_pvb_timeout_jobs(context, user.id, game_id)
            round_timeout = game_sessions[game_id].get('round_timeout', default_round_timeout)
            warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
            context.job_queue.run_once(
                pvb_timeout_warn_job,
                when=warn_time,
                data={'user_id': user.id, 'game_id': game_id, 'chat_id': chat_id},
                name=f"pvb_warn_{game_id}"
            )
            context.job_queue.run_once(
                pvb_timeout_finish_job,
                when=round_timeout,
                data={'user_id': user.id, 'game_id': game_id, 'chat_id': chat_id},
                name=f"pvb_finish_{game_id}"
            )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('matches', matches_command, block=False))
    app.add_handler(CommandHandler(['deals', 'he'], deals_command, block=False))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, single_emoji_bet_handler, block=False))

