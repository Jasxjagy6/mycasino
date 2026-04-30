"""Auto-split from bot.py — plugins.games_highlow."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def calculate_highlow_multiplier(current_card: int, deck: list, bet_type: str) -> float:
    """
    Calculate multiplier based on probability according to hl.txt specifications.
    Formula: Multiplier = 0.98 / P(Bet)
    House edge is 2%, meaning 98% RTP
    """
    if not deck:
        return 1.0

    total_remaining = len(deck)

    # Count remaining cards by rank
    rank_counts = {}
    for card in deck:
        rank_counts[card] = rank_counts.get(card, 0) + 1

    # Calculate probabilities
    if bet_type == "high":
        # Count cards with rank higher than current
        higher_cards = sum(count for rank, count in rank_counts.items() if rank > current_card)
        probability = higher_cards / total_remaining if total_remaining > 0 else 0
    elif bet_type == "low":
        # Count cards with rank lower than current
        lower_cards = sum(count for rank, count in rank_counts.items() if rank < current_card)
        probability = lower_cards / total_remaining if total_remaining > 0 else 0
    elif bet_type == "tie":
        # Count cards with same rank as current
        same_cards = rank_counts.get(current_card, 0)
        probability = same_cards / total_remaining if total_remaining > 0 else 0
    else:
        return 1.0

    # Avoid division by zero
    if probability <= 0:
        return 0  # Can't win, no multiplier

    # Calculate multiplier with 2% house edge
    multiplier = 0.98 / probability

    return round(multiplier, 2)

@check_banned
@check_maintenance
async def highlow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("highlow"):
        await update.message.reply_text(
            "\U0001f527 <b>HighLow</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text(
            "Usage: /hl amount\n\nExamples:\n"
            "• /hl 5 - Bet $5\n"
            "• /hl all - Bet all balance"
        )
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except Exception:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet, 'highlow'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Use user's provably fair seeds with fresh game client seed (like mines)
    # This ensures each game has unique, unpredictable seeds
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)  # Increment nonce to ensure unique results per game

    # Generate fresh client seed for this specific game
    game_client_seed = generate_game_client_seed()
    game_id = generate_unique_id("HL")

    # Generate deck of cards (1-13, where 1=Ace, 11=Jack, 12=Queen, 13=King) deterministically
    deck = list(range(1, 14)) * 4  # 4 suits
    # Shuffle deck using provably fair method
    for i in range(len(deck) - 1, 0, -1):
        j = get_provably_fair_result(seeds["server_seed"], game_client_seed, current_nonce + i, i + 1)
        deck[i], deck[j] = deck[j], deck[i]

    current_card = deck.pop()

    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "highlow",
        "user_id": user.id,
        "bet_amount": bet,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "streak": 0,
        "server_seed": seeds["server_seed"],
        "client_seed": game_client_seed,
        "nonce": current_nonce,
        "deck": deck,
        "current_card": current_card,
        "current_multiplier": 1.0
    }

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    card_name = get_card_name(current_card)

    # Calculate multipliers for each choice
    high_mult = calculate_highlow_multiplier(current_card, deck, "high")
    low_mult = calculate_highlow_multiplier(current_card, deck, "low")
    tie_mult = calculate_highlow_multiplier(current_card, deck, "tie")

    # Build keyboard - row 1: Higher/Lower, row 2: Tie, row 3: Skip/Cashout
    row1 = []

    # Add Higher button only if not King (13)
    if current_card != 13:
        row1.append(apply_button_style(InlineKeyboardButton(f"Higher ({high_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_high"), 'primary'))

    # Add Lower button only if not Ace (1)
    if current_card != 1:
        row1.append(apply_button_style(InlineKeyboardButton(f"Lower ({low_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_low"), 'success'))

    # Row 2: Tie button
    row2 = [apply_button_style(InlineKeyboardButton(f"Tie ({tie_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_tie"), 'primary')]

    # Row 3: Skip Card button only (no cashout on first card)
    row3 = [apply_button_style(InlineKeyboardButton("Skip Card", callback_data=f"hl_skip_{game_id}"), 'primary')]

    # Create keyboard with new layout
    keyboard = [row1, row2, row3]

    # Build multiplier text
    mult_text = "Choose your prediction:\n"
    if current_card != 13:
        mult_text += f"{pe('up')} Higher: {high_mult:.2f}x\n"
    if current_card != 1:
        mult_text += f"{pe('down')} Lower: {low_mult:.2f}x\n"
    mult_text += f"{pe('refresh')} Tie: {tie_mult:.2f}x"

    await update.message.reply_text(
        f"🎴 <b>High-Low Game Started!</b> (ID: <code>{game_id}</code>)\n\n"
        f"{pe('money')} Bet: {dformat(bet)}\n"
        f"{pe('cards')} Current Card: <b>{card_name}</b>\n"
        f"{pe('chart')} Cards remaining: {len(deck)}\n\n"
        f"{mult_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard)
    )

@check_banned
@check_maintenance
async def highlow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    if not query.data.startswith("hl_"):
        try: await query.answer()
        except: pass
        return

    if not await _acquire_callback(query.id):
        try: await query.answer()
        except: pass
        return

    if not _check_user_action_flood(user.id, query.data, _USER_ACTION_COOLDOWN_GAME):
        try: await query.answer("⏳ Too fast!", show_alert=False)
        except: pass
        _release_callback(query.id)
        return

    try:
        await query.answer()

        parts = query.data.split("_")
        action = parts[1]
        game_id = parts[2]

        game = game_sessions.get(game_id)
        if not game:
            await query.edit_message_text("No active High-Low game found.")
            return

        if user.id != game.get('user_id'):
            await query.answer("This is not your game!", show_alert=True)
            return

        if game.get('status') != 'active':
            await query.edit_message_text("This game is already finished.")
            return

        if action == "skip":
            # Skip the current card and draw a new one
            if not game["deck"]:
                await query.answer("No more cards to skip!", show_alert=True)
                return

            # Draw a random card from the remaining deck using provably fair RNG
            deck_size = len(game["deck"])
            nonce_for_draw = game["nonce"] + game["streak"] + HILOW_SKIP_NONCE_OFFSET  # Offset to differentiate from pick draws
            random_index = get_provably_fair_result(game["server_seed"], game["client_seed"], nonce_for_draw, deck_size)
            new_card = game["deck"].pop(random_index)
            game["current_card"] = new_card

            card_name = get_card_name(new_card)
            win_amount = game["bet_amount"] * game["current_multiplier"]

            # Calculate new multipliers for the new card
            high_mult = calculate_highlow_multiplier(new_card, game["deck"], "high")
            low_mult = calculate_highlow_multiplier(new_card, game["deck"], "low")
            tie_mult = calculate_highlow_multiplier(new_card, game["deck"], "tie")

            # Build keyboard - row 1: Higher/Lower, row 2: Tie, row 3: Skip/Cashout
            row1 = []
            if new_card != 13:
                row1.append(apply_button_style(InlineKeyboardButton(f"Higher ({high_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_high"), 'primary'))
            if new_card != 1:
                row1.append(apply_button_style(InlineKeyboardButton(f"Lower ({low_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_low"), 'success'))

            row2 = [apply_button_style(InlineKeyboardButton(f"Tie ({tie_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_tie"), 'primary')]

            row3 = [
                apply_button_style(InlineKeyboardButton("Skip Card", callback_data=f"hl_skip_{game_id}"), 'primary'),
                apply_button_style(InlineKeyboardButton("Cash Out ({dformat(win_amount)})", callback_data=f"hl_cashout_{game_id}"), 'success')
            ]

            keyboard = [row1, row2, row3]

            # Build multiplier text
            mult_text = "Next multipliers:\n"
            if new_card != 13:
                mult_text += f"{pe('up')} Higher: {high_mult:.2f}x\n"
            if new_card != 1:
                mult_text += f"{pe('down')} Lower: {low_mult:.2f}x\n"
            mult_text += f"{pe('refresh')} Tie: {tie_mult:.2f}x"

            await query.edit_message_text(
                f"⏭️ <b>Card Skipped!</b>\n\n"
                f"{pe('cards')} New Current Card: <b>{card_name}</b>\n"
                f"{pe('money')} Current Win: <b>{dformat(win_amount)}</b>\n"
                f"{pe('fire')} Streak: {game['streak']}\n"
                f"{pe('stats')} Current Multiplier: {game['current_multiplier']:.2f}x\n"
                f"{pe('chart')} Cards remaining: {len(game['deck'])}\n\n"
                f"{mult_text}\n\n"
                f"Continue playing or cash out?\nID: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=create_styled_keyboard(keyboard)
            )
            return

        if action == "pick":
            choice = parts[3]  # high, low, or tie
            current_card = game["current_card"]

            if not game["deck"]:
                # Deck exhausted - auto cashout
                action = "cashout"
            else:
                # Draw a random card from the remaining deck using provably fair RNG
                # This ensures true probability distribution matching remaining cards
                deck_size = len(game["deck"])
                nonce_for_draw = game["nonce"] + game["streak"]  # Use streak to vary nonce
                random_index = get_provably_fair_result(game["server_seed"], game["client_seed"], nonce_for_draw, deck_size)
                next_card = game["deck"].pop(random_index)

                # Calculate the multiplier for this choice BEFORE the draw
                choice_multiplier = calculate_highlow_multiplier(current_card, game["deck"] + [next_card], choice)

                # Determine if choice was correct
                correct = False
                if choice == "high" and next_card > current_card:
                    correct = True
                elif choice == "low" and next_card < current_card:
                    correct = True
                elif choice == "tie" and next_card == current_card:
                    correct = True

                if correct:
                    game["streak"] += 1
                    # Apply the multiplier for this win
                    game["current_multiplier"] *= choice_multiplier

                    win_amount = game["bet_amount"] * game["current_multiplier"]
                    game["current_card"] = next_card

                    card_name = get_card_name(next_card)

                    # Calculate new multipliers for next round
                    high_mult = calculate_highlow_multiplier(next_card, game["deck"], "high")
                    low_mult = calculate_highlow_multiplier(next_card, game["deck"], "low")
                    tie_mult = calculate_highlow_multiplier(next_card, game["deck"], "tie")

                    # Build keyboard - row 1: Higher/Lower, row 2: Tie, row 3: Skip/Cashout
                    row1 = []
                    if next_card != 13:
                        row1.append(apply_button_style(InlineKeyboardButton(f"Higher ({high_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_high"), 'primary'))
                    if next_card != 1:
                        row1.append(apply_button_style(InlineKeyboardButton(f"Lower ({low_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_low"), 'success'))

                    row2 = [apply_button_style(InlineKeyboardButton(f"Tie ({tie_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_tie"), 'primary')]

                    row3 = [
                        apply_button_style(InlineKeyboardButton("Skip Card", callback_data=f"hl_skip_{game_id}"), 'primary'),
                        apply_button_style(InlineKeyboardButton("Cash Out ({dformat(win_amount)})", callback_data=f"hl_cashout_{game_id}"), 'success')
                    ]

                    keyboard = [row1, row2, row3]

                    # Build multiplier text
                    mult_text = "Next multipliers:\n"
                    if next_card != 13:
                        mult_text += f"{pe('up')} Higher: {high_mult:.2f}x\n"
                    if next_card != 1:
                        mult_text += f"{pe('down')} Lower: {low_mult:.2f}x\n"
                    mult_text += f"{pe('refresh')} Tie: {tie_mult:.2f}x"

                    await query.edit_message_text(
                        f"{pe('win')} <b>Correct!</b> The next card is {card_name}!\n\n"
                        f"{pe('cards')} Current Card: <b>{card_name}</b>\n"
                        f"{pe('money')} Current Win: <b>{dformat(win_amount)}</b>\n"
                        f"{pe('fire')} Streak: {game['streak']}\n"
                        f"{pe('stats')} Current Total Multiplier: {game['current_multiplier']:.2f}x\n"
                        f"{pe('chart')} Cards remaining: {len(game['deck'])}\n\n"
                        f"{mult_text}\n\n"
                        f"Continue playing or cash out?\nID: <code>{game_id}</code>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=create_styled_keyboard(keyboard)
                    )
                else:
                    # Wrong guess - game over
                    game["status"] = 'completed'
                    game["win"] = False
                    increment_user_nonce(user.id)
                    await update_stats_on_bet(user.id, game_id, game['bet_amount'], False, context=context)
                    update_pnl(user.id)
                    save_user_data(user.id)

                    # Store provably fair record
                    store_provably_fair_record(game_id, "hilo", game["server_seed"], game["client_seed"], game["nonce"],
                                               result_data=f"Streak: {game['streak']}, Next card: {next_card}")

                    # Add rebet/double and provably fair buttons
                    keyboard = [
                        [
                            apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"highlow_rebet_{game['bet_amount']}_{user.id}"), 'primary'),
                            apply_button_style(InlineKeyboardButton("Double", callback_data=f"highlow_double_{game['bet_amount']}_{user.id}"), 'success')
                        ],
                        [await create_provably_fair_button(game_id, context)]
                    ]

                    next_card_name = get_card_name(next_card)
                    await query.edit_message_text(
                        f"{pe('cross')} <b>Wrong!</b> The next card was {next_card_name}.\n\n"
                        f"💔 You lost your bet of ${game['bet_amount']:.2f}\n"
                        f"{pe('fire')} Your streak was: {game['streak']}\n"
                        f"ID: <code>{game_id}</code>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )

        elif action == "cashout":
            win_amount = game["bet_amount"] * game["current_multiplier"]
            credit_wallet(user.id, win_amount)
            game["status"] = 'completed'
            game["win"] = True
            game["multiplier"] = game["current_multiplier"]
            increment_user_nonce(user.id)
            await update_stats_on_bet(user.id, game_id, game['bet_amount'], True, multiplier=game["current_multiplier"], context=context)
            update_pnl(user.id)
            save_user_data(user.id)

            # Store provably fair record
            store_provably_fair_record(game_id, "hilo", game["server_seed"], game["client_seed"], game["nonce"],
                                       result_data=f"Streak: {game['streak']}, Multiplier: {game['current_multiplier']:.2f}x")

            # Add rebet/double and provably fair buttons
            keyboard = [
                [
                    apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"highlow_rebet_{game['bet_amount']}_{user.id}"), 'primary'),
                    apply_button_style(InlineKeyboardButton("Double", callback_data=f"highlow_double_{game['bet_amount']}_{user.id}"), 'success')
                ],
                [await create_provably_fair_button(game_id, context)]
            ]

            await query.edit_message_text(
                f"{pe('withdraw')} <b>Cashed Out!</b>\n\n"
                f"{pe('win')} You won <b>{dformat(win_amount)}</b>!\n"
                f"{pe('fire')} Final streak: {game['streak']}\n"
                f"{pe('stats')} Final multiplier: {game['current_multiplier']:.2f}x\n"
                f"ID: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    finally:
        _release_callback(query.id)

@check_banned
@check_maintenance
async def highlow_rebet_double_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Rebet and Double buttons for highlow"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data: highlow_rebet_{bet_amount}_{user_id} or highlow_double_{bet_amount}_{user_id}
    parts = query.data.split("_")
    if len(parts) < 4:
        await query.answer("Invalid button data", show_alert=True)
        return

    action = parts[1]  # rebet or double
    try:
        original_bet = float(parts[2])
        button_user_id = int(parts[3])
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
        bet = original_bet
    else:  # double
        bet = original_bet * 2

    # Check bet limits
    if not await check_bet_limits(update, bet, 'highlow', user_id=user.id):
        await query.answer("Bet exceeds limits", show_alert=True)
        return

    # Check balance
    if get_active_balance_usd(user.id) < bet:
        await query.answer("Insufficient balance!", show_alert=True)
        return

    deduct_wallet(user.id, bet)
    save_user_data(user.id)

    # Use user's provably fair seeds
    seeds = get_user_seeds(user.id)
    game_id = generate_unique_id("HL")

    # Generate deck of cards deterministically
    deck = list(range(1, 14)) * 4  # 4 suits
    # Shuffle deck using provably fair method
    for i in range(len(deck) - 1, 0, -1):
        j = get_provably_fair_result(seeds["server_seed"], seeds["client_seed"], seeds["nonce"] + i, i + 1)
        deck[i], deck[j] = deck[j], deck[i]

    current_card = deck.pop()

    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "highlow",
        "user_id": user.id,
        "bet_amount": bet,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "streak": 0,
        "server_seed": seeds["server_seed"],
        "client_seed": seeds["client_seed"],
        "nonce": seeds["nonce"],
        "deck": deck,
        "current_card": current_card,
        "current_multiplier": 1.0
    }

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    card_name = get_card_name(current_card)

    # Calculate multipliers for each choice
    high_mult = calculate_highlow_multiplier(current_card, deck, "high")
    low_mult = calculate_highlow_multiplier(current_card, deck, "low")
    tie_mult = calculate_highlow_multiplier(current_card, deck, "tie")

    # Build keyboard - row 1: Higher/Lower, row 2: Tie, row 3: Skip
    row1 = []
    if current_card != 13:
        row1.append(apply_button_style(InlineKeyboardButton(f"Higher ({high_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_high"), 'primary'))
    if current_card != 1:
        row1.append(apply_button_style(InlineKeyboardButton(f"Lower ({low_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_low"), 'success'))

    row2 = [apply_button_style(InlineKeyboardButton(f"Tie ({tie_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_tie"), 'primary')]
    row3 = [apply_button_style(InlineKeyboardButton("Skip Card", callback_data=f"hl_skip_{game_id}"), 'primary')]

    keyboard = [row1, row2, row3]

    # Build multiplier text
    mult_text = "Choose your prediction:\n"
    if current_card != 13:
        mult_text += f"{pe('up')} Higher: {high_mult:.2f}x\n"
    if current_card != 1:
        mult_text += f"{pe('down')} Lower: {low_mult:.2f}x\n"
    mult_text += f"{pe('refresh')} Tie: {tie_mult:.2f}x"

    await query.edit_message_text(
        f"🎴 <b>High-Low Game Started!</b> (ID: <code>{game_id}</code>)\n\n"
        f"{pe('money')} Bet: {dformat(bet)}\n"
        f"?? Current Card: <b>{card_name}</b>\n"
        f"{pe('chart')} Cards remaining: {len(deck)}\n\n"
        f"{mult_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard)
    )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('hl', highlow_command, block=False))
    app.add_handler(CallbackQueryHandler(highlow_rebet_double_callback, pattern='^highlow_(rebet|double)_', block=False))
    app.add_handler(CallbackQueryHandler(highlow_callback, pattern='^hl_', block=False))

