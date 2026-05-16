"""Auto-split from bot.py — plugins.games_mines."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def generate_mine_positions(server_seed, client_seed, nonce, num_mines):
    """Generate deterministic mine positions for Mines game"""
    positions = []
    offset = 0
    # Use nonce * 1000 to ensure consecutive games don't produce overlapping hash inputs
    # This prevents the issue where nonce N uses offsets 0,1,2... which overlap with nonce N+1
    base_nonce = nonce * 1000
    while len(positions) < num_mines:
        pos = get_provably_fair_result(server_seed, client_seed, base_nonce + offset, 25)
        if pos not in positions:
            positions.append(pos)
        offset += 1
    return sorted(positions)

def get_mines_multiplier(num_mines, safe_picks):
    """Return the Mines payout multiplier for ``safe_picks`` safe tiles
    on a 25-cell board with ``num_mines`` mines.

    Phase 1a fix: this looks up ``MINES_MULT_TABLE`` (now computed from
    the fair formula with the declared ``HOUSE_EDGES['originals']``
    house edge) and falls back to ``_compute_mines_multiplier`` for any
    out-of-range coordinate so we never silently return ``1.0`` for a
    valid (mines, picks) pair.
    """
    if safe_picks == 0:
        return 1.0
    try:
        return MINES_MULT_TABLE[num_mines][safe_picks]
    except KeyError:
        try:
            return _compute_mines_multiplier(
                num_mines, safe_picks, HOUSE_EDGES["originals"]
            )
        except Exception:
            return 1.0

def mines_keyboard(game_id, reveal=False):
    game = game_sessions.get(game_id)
    if not game: return InlineKeyboardMarkup([])

    total_cells = game["total_cells"]
    num_per_row = 5
    user_id = game.get("user_id")
    buttons = []
    for i in range(total_cells):  # 0-24 to match mine positions
        if i in game["picks"]:
            emoji = "✅"
        elif reveal and i in game["mines"]:
            emoji = "💥"
        elif reveal:
            emoji = "💎"
        else:
            emoji = "🟦"  # Blue tile for colorful grid
        # Add user_id to callback for user-specific buttons
        btn = InlineKeyboardButton(emoji, callback_data=f"mines_pick_{game_id}_{i}_{user_id}")
        # Apply primary style (BLUE) to unselected tiles
        if emoji == "🟦":
            buttons.append(apply_button_style(btn, 'primary'))  # BLUE
        else:
            buttons.append(btn.to_dict())

    keyboard = [buttons[i:i+num_per_row] for i in range(0, len(buttons), num_per_row)]
    if game["status"] == 'active' and game["picks"]:
        safe_picks = len(game["picks"])
        multiplier = get_mines_multiplier(game["num_mines"], safe_picks)
        winnings = game["bet_amount"] * multiplier
        # GREEN cashout button
        cashout_text = f"Cashout ({dformat(winnings)})"
        cashout_btn = apply_button_style(
            InlineKeyboardButton(cashout_text, callback_data=f"mines_cashout_{game_id}_{user_id}"),
            'success',  # GREEN
            peb('cashout')
        )
        keyboard.append([cashout_btn])
        # BLUE random button
        random_btn = apply_button_style(
            InlineKeyboardButton("Random", callback_data=f"mines_random_{game_id}_{user_id}"),
            'primary',  # BLUE
            peb('random')
        )
        keyboard.append([random_btn])
    return create_styled_keyboard(keyboard)

@check_banned
@check_maintenance
async def mines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("mines"):
        await update.message.reply_text(
            "\U0001f527 <b>Mines</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    num_mines = int(context.user_data['bombs'])

    try:
        bet_amount_str = update.message.text.lower()
        # Display-currency aware: typed in the user's chosen fiat.
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except ValueError:
        await update.message.reply_text("Invalid bet amount. Please enter a number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    if not await check_bet_limits(update, bet_amount, 'mines'):
        return SELECT_BET_AMOUNT

    # Generate a fresh 15-character client seed for this game BEFORE calculating mines
    # This ensures each game has a completely unique seed for truly random results
    game_client_seed = generate_game_client_seed()

    # Use server seed from user's provably fair data, but fresh client seed per game
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)  # Increment nonce at game start

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Cancel", callback_data="cancel_game")]
        ])
        await update.message.reply_text(f"{pe('cross')} You don't have enough balance. Please enter a lower amount.", reply_markup=keyboard)
        return SELECT_BET_AMOUNT

    total_cells = 25

    # Calculate mine positions using server seed + fresh game client seed
    mine_numbers = generate_mine_positions(seeds["server_seed"], game_client_seed, current_nonce, num_mines)

    game_id = generate_unique_id("MN")
    game_sessions[game_id] = {
        "id": game_id, "game_type": "mines", "user_id": user.id, "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "status": "active", "timestamp": str(datetime.now(timezone.utc)), "mines": mine_numbers,
        "picks": [], "total_cells": total_cells, "num_mines": num_mines,
        "server_seed": seeds["server_seed"], "client_seed": game_client_seed, "nonce": current_nonce
    }
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    initial_text = (
        f"{pe('bomb')} <b>Mines Game Started!</b> (ID: <code>{game_id}</code>)\n\nBet: <b>{dformat(bet_amount)}</b>\nMines: <b>{num_mines}</b>\n\n"
        "Click the buttons to reveal tiles. Find gems to increase your multiplier. Avoid the bombs!\n"
        "You can cash out after any successful pick."
    )
    await update.message.reply_text(
        initial_text, parse_mode=ParseMode.HTML, reply_markup=mines_keyboard(game_id)
    )
    context.user_data.clear()
    return ConversationHandler.END

@check_banned
@check_maintenance
async def mines_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    parts = query.data.split("_")
    action = parts[1]
    game_id = parts[2]

    game = game_sessions.get(game_id)

    if not game:
        await query.edit_message_text("No active mines game found, it has ended, or it is not your game.", reply_markup=None)
        return

    # NEW: Enhanced user-specific security check
    # Format: mines_pick_{game_id}_{tile}_{user_id} or mines_cashout_{game_id}_{user_id} or mines_random_{game_id}_{user_id}
    if len(parts) >= 5 and parts[4].isdigit():
        # For pick action: parts = ['mines', 'pick', game_id, tile, user_id]
        button_user_id = int(parts[4])
        if user.id != button_user_id:
            await query.answer("This is not your game!", show_alert=True)
            return
    elif len(parts) >= 4 and parts[3].isdigit() and action in ['cashout', 'random']:
        # For cashout/random: parts = ['mines', 'cashout'/'random', game_id, user_id]
        button_user_id = int(parts[3])
        if user.id != button_user_id:
            await query.answer("This is not your game!", show_alert=True)
            return

    # Fallback security check
    if user.id != game.get('user_id'):
        await query.answer("This is not your game!", show_alert=True)
        return

    if game.get("status") != 'active':
        # Don't edit message if game is over, just inform the user who tapped
        await query.answer("This game has already ended.", show_alert=True)
        return

    # NEW: Handle random tile selection
    if action == "random":
        # Get unpicked tiles - use 0-24 to match mine positions
        unpicked = [i for i in range(game["total_cells"]) if i not in game["picks"]]
        if not unpicked:
            await query.answer("No tiles left to pick!", show_alert=True)
            return

        # Randomly select a tile
        cell = _secure_choice(unpicked)

        # Check if it's a mine
        if cell in game["mines"]:
            game["status"] = 'completed'
            game["win"] = False
            # Note: nonce was incremented at game start for provably fair
            await update_stats_on_bet(user.id, game_id, game['bet_amount'], win=False, context=context)
            update_pnl(user.id)
            save_user_data(user.id)

            # Store provably fair record
            store_provably_fair_record(game_id, "mines", game["server_seed"], game["client_seed"], game["nonce"],
                                       result_data=f"Hit mine at tile {cell} (Random), Mine positions: {game['mines']}")

            # Send template instead of inline keyboard
            username = f"@{user.username}" if user.username else f"User{user.id}"
            winnings = 0.0
            template = _render_mines_sync(
                username=username,
                bet_amount=game['bet_amount'],
                num_mines=game['num_mines'],
                picks=list(game['picks']),
                mines=list(game['mines']),
                won=False,
                multiplier=0.0,
                winnings=winnings,
                game_id=game_id,
                safe_count=len(game['picks']),
            )
            pf_button = await create_provably_fair_button(game_id, context)
            kb = InlineKeyboardMarkup([[pf_button]])
            if template:
                await query.edit_message_media(
                    InputMediaPhoto(template, caption=f"{pe('bust')} <b>Boom!</b> Random picked tile {cell} - it was a mine! (ID: <code>{game_id}</code>)\n\nYou lost your bet of <b>${game['bet_amount']:.2f}</b>.", parse_mode=ParseMode.HTML),
                    reply_markup=kb
                )
            else:
                await query.edit_message_text(
                    f"{pe('bust')} <b>Boom!</b> Random picked tile {cell} - it was a mine! (ID: <code>{game_id}</code>)\n\nYou lost your bet of <b>${game['bet_amount']:.2f}</b>.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb
                )
            return

        # Safe pick
        game["picks"].append(cell)
        safe_picks = len(game["picks"])
        multiplier = get_mines_multiplier(game["num_mines"], safe_picks)
        potential_winnings = game["bet_amount"] * multiplier

        if safe_picks == (game["total_cells"] - game["num_mines"]):
            # MAX WIN
            game["status"] = 'completed'
            game["win"] = True
            game["multiplier"] = multiplier
            credit_wallet(user.id, potential_winnings)
            # Note: nonce was incremented at game start for provably fair
            await update_stats_on_bet(user.id, game_id, game['bet_amount'], win=True, multiplier=multiplier, context=context)
            update_pnl(user.id)
            save_user_data(user.id)

            # Store provably fair record
            store_provably_fair_record(game_id, "mines", game["server_seed"], game["client_seed"], game["nonce"],
                                       result_data=f"Max win: {safe_picks} gems (Last Random), Multiplier: {multiplier:.2f}x, Mine positions: {game['mines']}")

            # Send template
            username = f"@{user.username}" if user.username else f"User{user.id}"
            template = _render_mines_sync(
                username=username,
                bet_amount=game['bet_amount'],
                num_mines=game['num_mines'],
                picks=list(game['picks']),
                mines=list(game['mines']),
                won=True,
                multiplier=multiplier,
                winnings=potential_winnings,
                game_id=game_id,
                safe_count=safe_picks,
            )
            pf_button = await create_provably_fair_button(game_id, context)
            kb = InlineKeyboardMarkup([[pf_button]])
            if template:
                await query.edit_message_media(
                    InputMediaPhoto(template, caption=f"{pe('win')} <b>MAX WIN!</b> (ID: <code>{game_id}</code>)\n\nRandom picked tile {cell} - You found all {safe_picks} gems and won <b>${potential_winnings:.2f}</b>!\nFinal Multiplier: <b>{multiplier:.2f}x</b>", parse_mode=ParseMode.HTML),
                    reply_markup=kb
                )
            else:
                await query.edit_message_text(
                    f"{pe('win')} <b>MAX WIN!</b> (ID: <code>{game_id}</code>)\n\nRandom picked tile {cell} - You found all {safe_picks} gems and won <b>${potential_winnings:.2f}</b>!\nFinal Multiplier: <b>{multiplier:.2f}x</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb
                )
            return

        # Continue playing
        await query.edit_message_text(
            f"{pe('bomb')} <b>Mines Game</b> (ID: <code>{game_id}</code>)\n\n"
            f"{pe('check')} Safe! Random picked tile {cell} - it's a gem!\n\n"
            f"Bet: <b>${game['bet_amount']:.2f}</b> | Mines: <b>{game['num_mines']}</b>\n"
            f"Safe Picks: <b>{safe_picks}</b> | Multiplier: <b>{multiplier:.2f}x</b>\n"
            f"Potential Cashout: <b>${potential_winnings:.2f}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=mines_keyboard(game_id)
        )
        return

    if action == "cashout":
        safe_picks = len(game["picks"])
        if safe_picks == 0:
            await query.answer("You need to make at least one pick to cash out.", show_alert=True)
            return

        multiplier = get_mines_multiplier(game["num_mines"], safe_picks)
        winnings = game["bet_amount"] * multiplier
        credit_wallet(user.id, winnings)
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        # Note: nonce was incremented at game start for provably fair
        await update_stats_on_bet(user.id, game_id, game['bet_amount'], win=True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)

        # Store provably fair record
        store_provably_fair_record(game_id, "mines", game["server_seed"], game["client_seed"], game["nonce"],
                                   result_data=f"Cashed out: {safe_picks} safe picks, Multiplier: {multiplier:.2f}x, Mine positions: {game['mines']}")

        # Send template
        username = f"@{user.username}" if user.username else f"User{user.id}"
        template = _render_mines_sync(
            username=username,
            bet_amount=game['bet_amount'],
            num_mines=game['num_mines'],
            picks=list(game['picks']),
            mines=list(game['mines']),
            won=True,
            multiplier=multiplier,
            winnings=winnings,
            game_id=game_id,
            safe_count=safe_picks,
        )
        pf_button = await create_provably_fair_button(game_id, context)
        rebet_btn = apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"mines_rebet_{game['bet_amount']}_{game['num_mines']}_{user.id}"), 'primary')
        double_btn = apply_button_style(InlineKeyboardButton("Double", callback_data=f"mines_double_{game['bet_amount']}_{game['num_mines']}_{user.id}"), 'success')
        kb = InlineKeyboardMarkup([[rebet_btn, double_btn], [pf_button]])
        if template:
            await query.edit_message_media(
                InputMediaPhoto(template, caption=f"{pe('withdraw')} <b>Cashed Out!</b> (ID: <code>{game_id}</code>)\n\nYou won <b>{dformat(winnings)}</b> with {safe_picks} correct picks!\nMultiplier: <b>{multiplier:.2f}x</b>", parse_mode=ParseMode.HTML),
                reply_markup=kb
            )
        else:
            await query.edit_message_text(
                f"{pe('withdraw')} <b>Cashed Out!</b> (ID: <code>{game_id}</code>)\n\nYou won <b>{dformat(winnings)}</b> with {safe_picks} correct picks!\nMultiplier: <b>{multiplier:.2f}x</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    try:
        cell = int(parts[3])
    except (ValueError, IndexError): return

    if cell in game["picks"]:
        await query.answer("You have already picked this tile.", show_alert=True)
        return

    if cell in game["mines"]:
        game["status"] = 'completed'
        game["win"] = False
        # Note: nonce was incremented at game start for provably fair
        await update_stats_on_bet(user.id, game_id, game['bet_amount'], win=False, context=context)
        update_pnl(user.id)
        save_user_data(user.id)

        # Store provably fair record
        store_provably_fair_record(game_id, "mines", game["server_seed"], game["client_seed"], game["nonce"],
                                   result_data=f"Hit mine at tile {cell}, Mine positions: {game['mines']}")

        # Send template
        username = f"@{user.username}" if user.username else f"User{user.id}"
        template = _render_mines_sync(
            username=username,
            bet_amount=game['bet_amount'],
            num_mines=game['num_mines'],
            picks=list(game['picks']),
            mines=list(game['mines']),
            won=False,
            multiplier=0.0,
            winnings=0.0,
            game_id=game_id,
            safe_count=len(game['picks']),
        )
        pf_button = await create_provably_fair_button(game_id, context)
        rebet_btn = apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"mines_rebet_{game['bet_amount']}_{game['num_mines']}_{user.id}"), 'primary')
        double_btn = apply_button_style(InlineKeyboardButton("Double", callback_data=f"mines_double_{game['bet_amount']}_{game['num_mines']}_{user.id}"), 'success')
        kb = InlineKeyboardMarkup([[rebet_btn, double_btn], [pf_button]])
        if template:
            await query.edit_message_media(
                InputMediaPhoto(template, caption=f"{pe('bust')} <b>Boom!</b> You hit a mine at tile {cell}. (ID: <code>{game_id}</code>)\n\nYou lost your bet of <b>${game['bet_amount']:.2f}</b>.", parse_mode=ParseMode.HTML),
                reply_markup=kb
            )
        else:
            await query.edit_message_text(
                f"{pe('bust')} <b>Boom!</b> You hit a mine at tile {cell}. (ID: <code>{game_id}</code>)\n\nYou lost your bet of <b>${game['bet_amount']:.2f}</b>.",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    game["picks"].append(cell)
    safe_picks = len(game["picks"])
    multiplier = get_mines_multiplier(game["num_mines"], safe_picks)
    potential_winnings = game["bet_amount"] * multiplier

    if safe_picks == (game["total_cells"] - game["num_mines"]):
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        credit_wallet(user.id, potential_winnings)
        # Note: nonce was incremented at game start for provably fair
        await update_stats_on_bet(user.id, game_id, game['bet_amount'], win=True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)

        # Store provably fair record
        store_provably_fair_record(game_id, "mines", game["server_seed"], game["client_seed"], game["nonce"],
                                   result_data=f"Max win: {safe_picks} gems, Multiplier: {multiplier:.2f}x, Mine positions: {game['mines']}")

        # Send template
        username = f"@{user.username}" if user.username else f"User{user.id}"
        template = _render_mines_sync(
            username=username,
            bet_amount=game['bet_amount'],
            num_mines=game['num_mines'],
            picks=list(game['picks']),
            mines=list(game['mines']),
            won=True,
            multiplier=multiplier,
            winnings=potential_winnings,
            game_id=game_id,
            safe_count=safe_picks,
        )
        pf_button = await create_provably_fair_button(game_id, context)
        rebet_btn = apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"mines_rebet_{game['bet_amount']}_{game['num_mines']}_{user.id}"), 'primary')
        double_btn = apply_button_style(InlineKeyboardButton("Double", callback_data=f"mines_double_{game['bet_amount']}_{game['num_mines']}_{user.id}"), 'success')
        kb = InlineKeyboardMarkup([[rebet_btn, double_btn], [pf_button]])
        if template:
            await query.edit_message_media(
                InputMediaPhoto(template, caption=f"{pe('win')} <b>MAX WIN!</b> (ID: <code>{game_id}</code>)\n\nYou found all {safe_picks} gems and won <b>${potential_winnings:.2f}</b>!\nFinal Multiplier: <b>{multiplier:.2f}x</b>", parse_mode=ParseMode.HTML),
                reply_markup=kb
            )
        else:
            await query.edit_message_text(
                f"{pe('win')} <b>MAX WIN!</b> (ID: <code>{game_id}</code>)\n\nYou found all {safe_picks} gems and won <b>${potential_winnings:.2f}</b>!\nFinal Multiplier: <b>{multiplier:.2f}x</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    next_text = (
        f"{pe('bomb')} <b>Mines Game</b> (ID: <code>{game_id}</code>)\n\n"
        f"{pe('check')} Safe! Tile {cell} is a gem!\n\n"
        f"Bet: <b>${game['bet_amount']:.2f}</b> | Mines: <b>{game['num_mines']}</b>\n"
        f"Safe Picks: <b>{safe_picks}</b> | Multiplier: <b>{multiplier:.2f}x</b>\n"
        f"Potential Cashout: <b>${potential_winnings:.2f}</b>"
    )
    await query.edit_message_text(next_text, parse_mode=ParseMode.HTML, reply_markup=mines_keyboard(game_id))
    await query.answer(f"Safe! Current multiplier: {multiplier:.2f}x")

@check_banned
@check_maintenance
async def mines_rebet_double_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Rebet and Double buttons for mines"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data: mines_rebet_{bet_amount}_{num_mines}_{user_id}
    parts = query.data.split("_")
    if len(parts) < 5:
        await query.answer("Invalid button data", show_alert=True)
        return

    action = parts[1]  # rebet or double
    try:
        original_bet = float(parts[2])
        num_mines = int(parts[3])
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
    if not await check_bet_limits(update, bet_amount, 'mines', user_id=user.id):
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

    # Use user's provably fair seeds and increment nonce at game start
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)  # Increment nonce at game start to ensure unique results
    game_id = generate_unique_id("MN")
    total_cells = 25

    # Generate mine positions using provably fair method
    available = list(range(total_cells))
    mines = []
    for i in range(num_mines):
        idx = get_provably_fair_result(seeds["server_seed"], seeds["client_seed"], current_nonce + i, len(available))
        mines.append(available.pop(idx))

    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "mines",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "num_mines": num_mines,
        "total_cells": total_cells,
        "mines": mines,
        "picks": [],
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "server_seed": seeds["server_seed"],
        "client_seed": seeds["client_seed"],
        "nonce": current_nonce
    }

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    mines_text = (
        f"{pe('bomb')} <b>Mines Game Started!</b> (ID: <code>{game_id}</code>)\n\n"
        f"Bet: <b>{dformat(bet_amount)}</b> | Mines: <b>{num_mines}</b>\n"
        f"Pick tiles to find gems! Avoid the mines!\n\n"
        f"Tap tiles to reveal, or use Random button."
    )

    # Use safe edit to handle photo-to-text transition
    chat_type = query.message.chat.type
    try:
        await query.edit_message_text(
            mines_text,
            parse_mode=ParseMode.HTML,
            reply_markup=mines_keyboard(game_id)
        )
    except Exception:
        # Previous message was likely a photo
        if chat_type in ["group", "supergroup"]:
            # In groups: send new message as reply (don't delete to avoid permission issues)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=mines_text,
                parse_mode=ParseMode.HTML,
                reply_markup=mines_keyboard(game_id),
                reply_to_message_id=query.message.message_id
            )
        else:
            # In DMs: delete and send new message
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(
                mines_text,
                parse_mode=ParseMode.HTML,
                reply_markup=mines_keyboard(game_id)
            )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CallbackQueryHandler(mines_rebet_double_callback, pattern='^mines_(rebet|double)_', block=False))
    app.add_handler(CallbackQueryHandler(mines_pick_callback, pattern='^mines_', block=False))

