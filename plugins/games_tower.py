"""Auto-split from bot.py — plugins.games_tower."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def generate_tower_positions(server_seed, client_seed, nonce, difficulty, num_floors=9):
    """Generate deterministic snake positions for Tower game"""
    tiles_per_floor = {'easy': 4, 'medium': 3, 'hard': 2}.get(difficulty, 4)
    positions = []
    # Use nonce * 1000 to ensure consecutive games don't produce overlapping hash inputs
    base_nonce = nonce * 1000
    for floor in range(num_floors):
        snake_pos = get_provably_fair_result(server_seed, client_seed, base_nonce + floor, tiles_per_floor)
        positions.append(snake_pos)
    return positions

def build_tower_keyboard(game_state):
    """
    Build the Tower game keyboard with inline buttons showing the grid.
    Returns an InlineKeyboardMarkup.

    Note: Non-interactive tiles use callback_data='tower_noop' which is silently ignored.
    These tiles don't need handling as they represent locked, completed, or revealed positions.
    """
    current_floor = game_state.get('current_floor', 0)
    tiles_per_floor = game_state.get('tiles_per_floor', 3)
    selected_tiles = game_state.get('selected_tiles', [])
    tower_config = game_state.get('tower_config', [])
    status = game_state.get('status', 'active')
    game_id = game_state.get('id')
    difficulty = game_state.get('difficulty', 'medium')
    bet_amount = game_state.get('bet_amount', 0)

    keyboard = []

    # Iterate floors from top (8) down to 0
    for floor in range(8, -1, -1):
        row = []

        if floor > current_floor and status == 'active':
            # Unreached floors during active game - show as locked/blank
            for col in range(tiles_per_floor):
                btn_dict = apply_button_style(
                    InlineKeyboardButton(TILE["lock"], callback_data=f"tower_noop"),
                    'primary'  # Blue background for unreached
                )
                row.append(btn_dict)

        elif floor == current_floor and status == 'active':
            # Active floor - show playable tiles
            for col in range(tiles_per_floor):
                btn_dict = apply_button_style(
                    InlineKeyboardButton(TILE["play"], callback_data=f"tower_pick_{game_id}_{col}"),
                    'primary'  # Blue background for playable tiles
                )
                row.append(btn_dict)

        else:
            # All other cases: completed floors, current floor when game ended, unreached floors when game ended
            # This reveals snakes on all floors when status != 'active'
            snake_pos = tower_config[floor] if floor < len(tower_config) else None
            safe_pos = selected_tiles[floor] if floor < len(selected_tiles) else None

            for col in range(tiles_per_floor):
                if col == snake_pos and status != 'active':
                    # Reveal snake after game ends (on all floors including unreached)
                    # This must be checked BEFORE safe_pos because when user hits a snake,
                    # safe_pos == snake_pos and we want to show snake emoji, not tree
                    btn_dict = apply_button_style(
                        InlineKeyboardButton(TILE["snake"], callback_data=f"tower_noop"),
                        'danger'  # Red background
                    )
                elif col == safe_pos:
                    # User's safe pick - show as green tree
                    btn_dict = apply_button_style(
                        InlineKeyboardButton(TILE["safe"], callback_data=f"tower_noop"),
                        'success'  # Green background
                    )
                else:
                    # Other tiles
                    btn_dict = apply_button_style(
                        InlineKeyboardButton(TILE["blank"], callback_data=f"tower_noop"),
                        'primary'  # Blue background
                    )
                row.append(btn_dict)

        keyboard.append(row)

    # Add action buttons at the bottom
    if status == 'active' and current_floor >= 0:
        # Calculate current multiplier and potential winnings
        multiplier = TOWER_MULTIPLIERS[difficulty][current_floor]
        potential_winnings = bet_amount * multiplier

        action_row = []

        # Random selection button (like Mines)
        random_btn_dict = apply_button_style(
            InlineKeyboardButton("Random", callback_data=f"tower_random_{game_id}"),
            'primary'  # Blue background
        )
        action_row.append(random_btn_dict)

        # Cashout button
        cashout_btn_dict = apply_button_style(
            InlineKeyboardButton(f"Cash Out (${potential_winnings:.2f})", callback_data=f"tower_cashout_{game_id}"),
            'success',  # Green background
            peb('cashout')
        )
        action_row.append(cashout_btn_dict)

        keyboard.append(action_row)

    return InlineKeyboardMarkup(keyboard)

@check_banned
@check_maintenance
async def tower_ask_bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for bet amount when starting tower from inline button"""
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return ConversationHandler.END

    # Check per-game maintenance status
    if not is_game_enabled("tower"):
        await query.answer(
            "\U0001f527 \U0001f3d4 Tower game is under maintenance.",
            show_alert=True
        )
        return ConversationHandler.END

    await query.answer()

    keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]
    await query.edit_message_text(
        "🏗️ <b>Tower Climb</b>\n\n"
        "Please enter your bet amount (or type 'all' to bet your entire balance):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # Set ownership after editing
    set_menu_owner(query.message, query.from_user.id)
    return TOWER_BET_AMOUNT

async def tower_receive_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive bet amount from user input"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    try:
        bet_str = update.message.text.lower()
        # parse_bet_amount honours the user's display currency
        # (e.g. /tower 500 with display=INR means ₹500, not $500).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_str, user.id)
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a number or 'all'.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]])
        )
        return TOWER_BET_AMOUNT

    # Check bet limits
    if not await check_bet_limits(update, bet_amount, 'tower'):
        return TOWER_BET_AMOUNT

    # Check balance
    if get_active_balance_usd(user.id) < bet_amount:
        await update.message.reply_text(
            "❌ Insufficient balance. Please enter a lower amount.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]])
        )
        return TOWER_BET_AMOUNT

    # Show tower intro
    await tower_intro(update, context, bet_amount, from_callback=False)
    return ConversationHandler.END

@check_banned
@check_maintenance
async def tower_intro(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_amount: float = None, from_callback: bool = False):
    """Show tower game introduction screen with difficulty selector"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Store bet amount in user_data
    if bet_amount is not None:
        context.user_data['tower_bet_amount'] = bet_amount

    # Get current difficulty or default to 'medium'
    current_difficulty = context.user_data.get('tower_difficulty', 'medium')
    diff_config = TOWER_DIFFICULTY_CONFIG[current_difficulty]

    intro_text = (
        f"{pe('tower')} <b>Tower Climb</b>\n\n"
        f"{pe('bet')} <b>Bet Amount:</b> {dformat(bet_amount)}\n"
        f"{pe('target')} <b>Difficulty:</b> {diff_config['name']} ({diff_config['risk']} risk)\n"
        f"{pe('chart')} <b>Tiles per floor:</b> {diff_config['tiles']}\n"
        f"{pe('trophy')} <b>Floors to climb:</b> 9\n"
        f"{pe('gem')} <b>Max Multiplier:</b> {TOWER_MULTIPLIERS[current_difficulty][9]:.2f}x\n\n"
        f"Select difficulty or start the game!"
    )

    keyboard = [
        # GREEN start button
        [apply_button_style(InlineKeyboardButton("Start Game", callback_data=f"tower_start_game"), 'success')],
        # Difficulty selector buttons (BLUE for current difficulty)
        [
            apply_button_style(InlineKeyboardButton("◀️", callback_data="tower_diff_prev"), 'primary', peb('left')),
            apply_button_style(InlineKeyboardButton(f"{diff_config['name']}", callback_data="tower_diff_info"), 'primary', peb('settings')),  # BLUE
            apply_button_style(InlineKeyboardButton("▶️", callback_data="tower_diff_next"), 'primary', peb('right'))
        ],
        [
            apply_button_style(InlineKeyboardButton("Rules", callback_data="tower_rules"), 'primary', peb('info')),
            InlineKeyboardButton("Multiplier Table", callback_data="tower_multipliers").to_dict()
        ],
        [apply_button_style(InlineKeyboardButton("Back", callback_data="cancel_game"), 'danger', peb('back'))]  # RED
    ]

    reply_markup = create_styled_keyboard(keyboard)

    if from_callback:
        query = update.callback_query
        await safe_edit_message(query, intro_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        sent_message = await update.message.reply_text(intro_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        set_menu_owner(sent_message, user.id)

@check_banned
@check_maintenance
async def tower_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tower and /tr commands with amount"""
    if not is_game_enabled("tower"):
        await update.effective_message.reply_text(
            "\U0001f527 <b>Tower</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # If no arguments, show help menu
    if not context.args or len(context.args) == 0:
        help_text = (
            f"{pe('tower')} <b>Tower Game</b>\n\n"
            "<b>How to Play:</b>\n"
            "Climb the tower by selecting safe tiles. Each floor has one snake hidden behind a tile.\n"
            "Cash out at any time to secure your winnings, or reach the top for the jackpot!\n\n"
            "<b>Difficulty Modes:</b>\n"
            "• Easy: 4 tiles per floor (25% risk)\n"
            "• Medium: 3 tiles per floor (33% risk)\n"
            "• Hard: 2 tiles per floor (50% risk)\n\n"
            "<b>Commands:</b>\n"
            "• <code>/tower &lt;amount&gt;</code> - Start a game with specified bet amount\n"
            "• <code>/tr &lt;amount&gt;</code> - Alias for /tower\n"
            "• <code>/continue &lt;game_id&gt;</code> - Continue an active tower game\n\n"
            "<b>Examples:</b>\n"
            "• <code>/tower 10</code> - Start with $10 bet\n"
            "• <code>/tr all</code> - Start with all-in bet\n"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return

    # Parse bet amount from command (display-currency aware)
    try:
        bet_str = context.args[0].lower()
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_str, user.id)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid amount. Please enter a number or 'all'.")
        return

    # Check bet limits
    if not await check_bet_limits(update, bet_amount, 'tower'):
        return

    # Check balance
    if get_active_balance_usd(user.id) < bet_amount:
        await update.message.reply_text(f"{pe('cross')} Insufficient balance. Please deposit or enter a lower amount.")
        return

    # Show tower intro
    await tower_intro(update, context, bet_amount, from_callback=False)

@check_banned
@check_maintenance
async def tower_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all tower game callbacks"""
    query = update.callback_query
    user = query.from_user

    if not query.data.startswith("tower_"):
        try: await query.answer()
        except: pass
        return

    # Global dedup guard
    if not await _acquire_callback(query.id):
        try: await query.answer()
        except: pass
        return

    # Flood guard for game actions
    if query.data.startswith("tower_pick_") or query.data.startswith("tower_cashout_"):
        if not _check_user_action_flood(user.id, query.data[:20], _USER_ACTION_COOLDOWN_GAME):
            try: await query.answer("⏳ Too fast!", show_alert=False)
            except: pass
            _release_callback(query.id)
            return

    try:
        # Check menu ownership for setup screens
        if query.data in ["tower_diff_prev", "tower_diff_next", "tower_diff_info", "tower_rules", "tower_multipliers", "tower_start_game"]:
            if not check_menu_ownership(query, context):
                await query.answer("This menu is not for you.", show_alert=True)
                return

        await query.answer()

        # Handle difficulty navigation
        if query.data == "tower_diff_prev":
            difficulties = ['easy', 'medium', 'hard']
            current = context.user_data.get('tower_difficulty', 'medium')
            idx = difficulties.index(current)
            new_idx = (idx - 1) % len(difficulties)
            context.user_data['tower_difficulty'] = difficulties[new_idx]
            bet_amount = context.user_data.get('tower_bet_amount')
            await tower_intro(update, context, bet_amount, from_callback=True)
            return

        if query.data == "tower_diff_next":
            difficulties = ['easy', 'medium', 'hard']
            current = context.user_data.get('tower_difficulty', 'medium')
            idx = difficulties.index(current)
            new_idx = (idx + 1) % len(difficulties)
            context.user_data['tower_difficulty'] = difficulties[new_idx]
            bet_amount = context.user_data.get('tower_bet_amount')
            await tower_intro(update, context, bet_amount, from_callback=True)
            return

        if query.data == "tower_rules":
            rules_text = (
                "🎮 <b>Tower Climb - How to Play</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "<b>Objective:</b>\n"
                "Climb all 9 floors to reach the top and win the jackpot.\n\n"
                "<b>⚠️ Warning:</b>\n"
                "Each floor has one snake 🐍 hidden behind a tile.\n"
                "Selecting the snake tile ends the game immediately.\n\n"
                "<b>How to Play:</b>\n"
                "1. Select your difficulty level\n"
                "2. Choose tiles to climb each floor\n"
                "3. Cash out anytime to secure your winnings\n"
                "4. Reach the top floor for maximum payout\n\n"
                "<b>Difficulty Modes:</b>\n"
                "• <b>Easy:</b> 4 tiles per floor (25% risk)\n"
                "• <b>Medium:</b> 3 tiles per floor (33% risk)\n"
                "• <b>Hard:</b> 2 tiles per floor (50% risk)\n\n"
                "🔥 Higher risk offers bigger rewards!\n\n"
                "House edge: 3.0%"
            )
            keyboard = [[InlineKeyboardButton("Back", callback_data="tower_back_to_intro")]]
            await safe_edit_message(query, rules_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if query.data == "tower_multipliers":
            mult_text = (
                "📊 <b>Tower Multiplier Table</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "<code>Floor   Easy   Medium   Hard</code>\n"
                "─────────────────────────────\n"
            )
            for floor in range(10):
                easy_mult = TOWER_MULTIPLIERS['easy'][floor]
                med_mult = TOWER_MULTIPLIERS['medium'][floor]
                hard_mult = TOWER_MULTIPLIERS['hard'][floor]
                mult_text += f"<code> {floor:>2}     {easy_mult:>5.2f}x  {med_mult:>6.2f}x {hard_mult:>7.2f}x</code>\n"

            mult_text += "\nHouse edge: 3.0%\nFloor 0: 0.90x (immediate cashout)"

            keyboard = [[InlineKeyboardButton("Back", callback_data="tower_back_to_intro")]]
            await safe_edit_message(query, mult_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        if query.data == "tower_back_to_intro":
            bet_amount = context.user_data.get('tower_bet_amount')
            await tower_intro(update, context, bet_amount, from_callback=True)
            return

        if query.data == "tower_start_game":
            await start_tower_game(update, context)
            return

        # Handle game actions (pick tile, cashout)
        parts = query.data.split("_")
        if len(parts) < 3:
            return

        action = parts[1]
        game_id = parts[2] if len(parts) > 2 else None

        if not game_id:
            return

        game = game_sessions.get(game_id)

        if not game:
            await query.edit_message_text("Game not found or already finished.")
            return

        # Check game ownership
        if user.id != game.get('user_id'):
            await query.answer("This is not your game!", show_alert=True)
            return

        if game.get('status') != 'active':
            return

        if action == "cashout":
            await handle_tower_cashout(update, context, game_id, game)
            return

        if action == "random":
            # Random tile selection
            tiles_per_floor = game.get('tiles_per_floor', 3)
            random_position = _secure_randint(0, tiles_per_floor - 1)
            await handle_tower_pick(update, context, game_id, game, random_position)
            return

        if action == "pick":
            position = int(parts[3]) if len(parts) > 3 else 0
            await handle_tower_pick(update, context, game_id, game, position)
            return
    finally:
        _release_callback(query.id)

def create_tower_floor_keyboard(game_id: str, floor: int, tiles_per_floor: int, selected_tile: int = None):
    """Create keyboard for current floor"""
    keyboard = []
    row = []
    for pos in range(tiles_per_floor):
        if selected_tile is not None and pos == selected_tile:
            emoji = "✅"  # Safe tile selected
        else:
            emoji = "🟦"  # Unknown tile
        row.append(InlineKeyboardButton(emoji, callback_data=f"tower_pick_{game_id}_{pos}"))
    keyboard.append(row)
    return keyboard

def create_tower_game_visual(game):
    """Create visual representation of the tower showing completed floors"""
    visual = "🏗️ <b>Tower:</b>\n"
    current_floor = game.get('current_floor', 0)
    tiles_per_floor = game.get('tiles_per_floor', 3)
    selected_tiles = game.get('selected_tiles', [])
    tower_config = game.get('tower_config', [])

    # Show floors from top (9) to bottom (0)
    for floor in range(8, -1, -1):
        if floor > current_floor:
            # Future floors - show as unknown
            visual += "❓" * tiles_per_floor + f"  Floor {floor + 1}\n"
        elif floor == current_floor:
            # Current floor - show current state
            visual += "🟦" * tiles_per_floor + f"  Floor {floor + 1} ← YOU\n"
        else:
            # Completed floors - reveal snake and safe tile
            snake_pos = tower_config[floor]
            safe_pos = selected_tiles[floor] if floor < len(selected_tiles) else None
            floor_visual = ""
            for pos in range(tiles_per_floor):
                if pos == safe_pos:
                    floor_visual += "✅"
                elif pos == snake_pos:
                    floor_visual += "🐍"
                else:
                    floor_visual += "⬜"
            visual += floor_visual + f"  Floor {floor + 1}\n"

    return visual

async def handle_tower_pick(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id: str, game: dict, position: int):
    """Handle tile selection"""
    query = update.callback_query
    user = query.from_user

    current_floor = game["current_floor"]
    snake_position = game["tower_config"][current_floor]
    difficulty = game["difficulty"]
    tiles_per_floor = game["tiles_per_floor"]

    # Check if hit snake
    if position == snake_position:
        # Game over - hit snake
        game["status"] = 'completed'
        game["win"] = False
        game["selected_tiles"].append(position)
        increment_user_nonce(user.id)
        await update_stats_on_bet(user.id, game_id, game["bet_amount"], False, context=context)
        update_pnl(user.id)
        save_user_data(user.id)

        # Store provably fair record
        store_provably_fair_record(game_id, "tower", game["server_seed"], game["client_seed"], game["nonce"],
                                   result_data=f"Hit snake on floor {current_floor + 1}, Config: {game['tower_config']}")

        # Answer the callback query first
        await query.answer(f"{pe('lose')} You hit the snake!")

        # Send template
        username = f"@{user.username}" if user.username else f"User{user.id}"
        template = _render_tower_sync(
            username=username,
            bet_amount=game["bet_amount"],
            difficulty=difficulty,
            current_floor=current_floor,
            tower_config=list(game["tower_config"]),
            selected_tiles=list(game["selected_tiles"]),
            won=False,
            multiplier=0,
            winnings=0,
            game_id=game_id,
        )
        pf_button = await create_provably_fair_button(game_id, context)
        rebet_btn = apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"tower_rebet_{game['bet_amount']}_{game['difficulty']}_{user.id}"), 'primary')
        double_btn = apply_button_style(InlineKeyboardButton("Double", callback_data=f"tower_double_{game['bet_amount']}_{game['difficulty']}_{user.id}"), 'success')
        kb = InlineKeyboardMarkup([[rebet_btn, double_btn], [pf_button]])
        if template:
            await query.edit_message_media(
                InputMediaPhoto(template, caption=f"{pe('snake')} <b>Tower Collapsed!</b>\nID: <code>{game_id}</code>\n\n💔 You hit the snake on Floor {current_floor + 1}!\n{pe('withdraw')} Lost: ${game['bet_amount']:.2f}\n{pe('tower')} Floors climbed: {current_floor}/9", parse_mode=ParseMode.HTML),
                reply_markup=kb
            )
        else:
            await query.edit_message_text(
                f"{pe('snake')} <b>Tower Collapsed!</b>\nID: <code>{game_id}</code>\n\n💔 You hit the snake on Floor {current_floor + 1}!\n{pe('withdraw')} Lost: ${game['bet_amount']:.2f}\n{pe('tower')} Floors climbed: {current_floor}/9",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        return

    # Safe tile - advance to next floor
    game["selected_tiles"].append(position)
    game["current_floor"] += 1
    new_floor = game["current_floor"]

    # Check if completed all 9 floors
    if new_floor >= 9:
        multiplier = TOWER_MULTIPLIERS[difficulty][9]
        winnings = game["bet_amount"] * multiplier
        credit_wallet(user.id, winnings)
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        increment_user_nonce(user.id)
        await update_stats_on_bet(user.id, game_id, game["bet_amount"], True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)

        # Store provably fair record
        store_provably_fair_record(game_id, "tower", game["server_seed"], game["client_seed"], game["nonce"],
                                   result_data=f"Conquered all floors, Multiplier: {multiplier}x, Config: {game['tower_config']}")

        # Answer the callback query first
        await query.answer(f"{pe('trophy')} Tower conquered!")

        # Send template
        username = f"@{user.username}" if user.username else f"User{user.id}"
        template = _render_tower_sync(
            username=username,
            bet_amount=game["bet_amount"],
            difficulty=difficulty,
            current_floor=new_floor,
            tower_config=list(game["tower_config"]),
            selected_tiles=list(game["selected_tiles"]),
            won=True,
            multiplier=multiplier,
            winnings=winnings,
            game_id=game_id,
        )
        pf_button = await create_provably_fair_button(game_id, context)
        rebet_btn = apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"tower_rebet_{game['bet_amount']}_{game['difficulty']}_{user.id}"), 'primary')
        double_btn = apply_button_style(InlineKeyboardButton("Double", callback_data=f"tower_double_{game['bet_amount']}_{game['difficulty']}_{user.id}"), 'success')
        kb = InlineKeyboardMarkup([[rebet_btn, double_btn], [pf_button]])
        if template:
            await query.edit_message_media(
                InputMediaPhoto(template, caption=f"{pe('trophy')} <b>Tower Conquered!</b>\nID: <code>{game_id}</code>\n\n{pe('win')} YOU REACHED THE TOP!\n{pe('money')} Winnings: <b>{dformat(winnings)}</b>\n{pe('stats')} Final Multiplier: {multiplier}x\n{pe('tower')} All 9 floors completed!", parse_mode=ParseMode.HTML),
                reply_markup=kb
            )
        else:
            await query.edit_message_text(
                f"{pe('trophy')} <b>Tower Conquered!</b>\nID: <code>{game_id}</code>\n\n{pe('win')} YOU REACHED THE TOP!\n{pe('money')} Winnings: <b>{dformat(winnings)}</b>\n{pe('stats')} Final Multiplier: {multiplier}x\n{pe('tower')} All 9 floors completed!",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        return

    # Continue to next floor
    multiplier = TOWER_MULTIPLIERS[difficulty][new_floor]
    potential_winnings = game["bet_amount"] * multiplier

    # Answer the callback query
    await query.answer(f"{pe('check')} Safe tile!")

    # Build keyboard for next floor
    keyboard = build_tower_keyboard(game)

    await query.edit_message_text(
        f"{pe('check')} <b>Safe! Climbing up...</b>\n"
        f"ID: <code>{game_id}</code>\n\n"
        f"{pe('chart')} Floor: {new_floor}/9\n"
        f"{pe('money')} Current Value: <b>${potential_winnings:.2f}</b>\n"
        f"{pe('stats')} Multiplier: {multiplier}x\n\n"
        f"Choose your next tile or cash out!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

async def handle_tower_cashout(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id: str, game: dict):
    """Handle cashout action"""
    query = update.callback_query
    user = query.from_user

    current_floor = game["current_floor"]
    difficulty = game["difficulty"]
    multiplier = TOWER_MULTIPLIERS[difficulty][current_floor]
    winnings = game["bet_amount"] * multiplier

    credit_wallet(user.id, winnings)
    game["status"] = 'completed'
    game["win"] = True
    game["multiplier"] = multiplier
    increment_user_nonce(user.id)
    await update_stats_on_bet(user.id, game_id, game["bet_amount"], True, multiplier=multiplier, context=context)
    update_pnl(user.id)
    save_user_data(user.id)

    # Store provably fair record
    store_provably_fair_record(game_id, "tower", game["server_seed"], game["client_seed"], game["nonce"],
                               result_data=f"Cashed out at floor {current_floor}, Multiplier: {multiplier}x, Config: {game['tower_config']}")

    # Answer the callback query first
    await query.answer(f"{pe('money')} Cashed out {dformat(winnings)}!")

    # Send template
    username = f"@{user.username}" if user.username else f"User{user.id}"
    template = _render_tower_sync(
        username=username,
        bet_amount=game["bet_amount"],
        difficulty=difficulty,
        current_floor=current_floor,
        tower_config=list(game["tower_config"]),
        selected_tiles=list(game["selected_tiles"]),
        won=True,
        multiplier=multiplier,
        winnings=winnings,
        game_id=game_id,
    )
    pf_button = await create_provably_fair_button(game_id, context)
    rebet_btn = apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"tower_rebet_{game['bet_amount']}_{game['difficulty']}_{user.id}"), 'primary')
    double_btn = apply_button_style(InlineKeyboardButton("Double", callback_data=f"tower_double_{game['bet_amount']}_{game['difficulty']}_{user.id}"), 'success')
    kb = InlineKeyboardMarkup([[rebet_btn, double_btn], [pf_button]])
    if template:
        await query.edit_message_media(
            InputMediaPhoto(template, caption=f"{pe('withdraw')} <b>Cashed Out!</b>\nID: <code>{game_id}</code>\n\n{pe('win')} Winnings: <b>{dformat(winnings)}</b>\n{pe('stats')} Multiplier: {multiplier}x\n{pe('tower')} Floors climbed: {current_floor}/9", parse_mode=ParseMode.HTML),
            reply_markup=kb
        )
    else:
        await query.edit_message_text(
            f"{pe('withdraw')} <b>Cashed Out!</b>\nID: <code>{game_id}</code>\n\n{pe('win')} Winnings: <b>{dformat(winnings)}</b>\n{pe('stats')} Multiplier: {multiplier}x\n{pe('tower')} Floors climbed: {current_floor}/9",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )

@check_banned
@check_maintenance
async def tower_rebet_double_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Rebet and Double buttons for tower"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data: tower_rebet_{bet_amount}_{difficulty}_{user_id}
    parts = query.data.split("_")
    if len(parts) < 5:
        await query.answer("Invalid button data", show_alert=True)
        return

    action = parts[1]  # rebet or double
    try:
        original_bet = float(parts[2])
        difficulty = parts[3]
        button_user_id = int(parts[4])
    except (ValueError, IndexError):
        await query.answer("Invalid button data", show_alert=True)
        return

    # User-specific button check
    if user.id != button_user_id:
        await query.answer("This button is not for you!", show_alert=True)
        return

    await query.answer()
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)

    # Determine bet amount
    if action == "rebet":
        bet_amount = original_bet
    else:  # double
        bet_amount = original_bet * 2

    # Check bet limits
    if not await check_bet_limits(update, bet_amount, 'tower', user_id=user.id):
        await query.answer("Bet exceeds limits", show_alert=True)
        return

    # Deduct bet amount atomically (per-user lock prevents double-spend
    # across concurrent rebet/double clicks and across queue workers).
    try:
        await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await query.answer("Insufficient balance!", show_alert=True)
        return
    save_user_data(user.id)

    # Use user's provably fair seeds
    seeds = get_user_seeds(user.id)

    # Generate tower configuration - 9 floors using deterministic positions
    tiles_per_floor = TOWER_DIFFICULTY_CONFIG[difficulty]['tiles']
    tower_config = generate_tower_positions(seeds["server_seed"], seeds["client_seed"], seeds["nonce"], difficulty, 9)

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
        "selected_tiles": [],
        "server_seed": seeds["server_seed"],
        "client_seed": seeds["client_seed"],
        "nonce": seeds["nonce"]
    }

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    # Build the tower keyboard
    keyboard = build_tower_keyboard(game_sessions[game_id])

    tower_text = (
        f"{pe('tower')} <b>Tower Climb</b>\n"
        f"ID: <code>{game_id}</code>\n\n"
        f"{pe('money')} Bet: {dformat(bet_amount)}\n"
        f"{pe('target')} Difficulty: {TOWER_DIFFICULTY_CONFIG[difficulty]['name']}\n"
        f"{pe('chart')} Floor: 0/9\n"
        f"{pe('gem')} Multiplier: 0.90x\n\n"
        f"Select a tile to start climbing!"
    )

    # Use safe_edit_message to handle photo-to-text transition
    chat_type = query.message.chat.type
    try:
        await query.edit_message_text(
            tower_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception:
        # Previous message was likely a photo
        if chat_type in ["group", "supergroup"]:
            # In groups: send new message as reply (don't delete to avoid permission issues)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=tower_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                reply_to_message_id=query.message.message_id
            )
        else:
            # In DMs: delete and send new message
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(
                tower_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )

def create_revealed_floor_keyboard(game_id: str, floor: int, tiles_per_floor: int, snake_pos: int, selected_pos: int):
    """Create keyboard showing revealed tiles after game over"""
    keyboard = []
    row = []
    for pos in range(tiles_per_floor):
        if pos == selected_pos:
            emoji = "🐍"  # Selected snake
        elif pos == snake_pos:
            emoji = "🐍"  # Snake position
        else:
            emoji = "✅"  # Safe tiles
        row.append(InlineKeyboardButton(emoji, callback_data=f"tower_noop"))
    keyboard.append(row)
    return keyboard

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('tower', tower_command, block=False))
    app.add_handler(CommandHandler('tr', tower_command, block=False))
    app.add_handler(CallbackQueryHandler(tower_rebet_double_callback, pattern='^tower_(rebet|double)_', block=False))
    app.add_handler(CallbackQueryHandler(tower_callback, pattern='^tower_', block=False))

