"""Auto-split from bot.py — plugins.games_roulette."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def get_roulette_number_emoji(number):
    """Get colored emoji for roulette number"""
    if number == 0:
        return "🟢"
    elif number in ROULETTE_RED_NUMBERS:
        return "🔴"
    else:
        return "⚫"

def create_roulette_menu_keyboard(user_id, bet_amount, selected=None):
    """Create the main roulette menu with betting options (COLORED buttons - Bot API 9.4)
    selected: the currently selected choice key (e.g. 'dozen1', 'red', 'even', etc.)"""
    # Map internal choice names back to action keys for highlighting
    selected_actions = set()
    if selected:
        reverse_map = {
            "dozen1": "1-12", "dozen2": "13-24", "dozen3": "25-36",
            "low": "1-18", "high": "19-36",
            "even": "even", "odd": "odd",
            "red": "red", "black": "black"
        }
        action_key = reverse_map.get(selected, selected)
        selected_actions.add(action_key)

    def _btn(text, action):
        btn = InlineKeyboardButton(text, callback_data=f"roul_{action}_{user_id}")
        if action in selected_actions:
            return apply_button_style(btn, 'success')  # GREEN for selected
        return btn.to_dict()

    keyboard = [
        [apply_button_style(InlineKeyboardButton("Start", callback_data=f"roul_start_{user_id}"), 'success')],  # GREEN
        [InlineKeyboardButton("Bet on Number", callback_data=f"roul_bet_number_{user_id}").to_dict()],
        [_btn("1-12", "1-12"), _btn("13-24", "13-24"), _btn("25-36", "25-36")],
        [_btn("1-18", "1-18"), _btn("19-36", "19-36")],
        [_btn("Even", "even"), _btn("Odd", "odd")],
        [_btn("🔴 Red", "red"), _btn("⚫ Black", "black")],
        [apply_button_style(InlineKeyboardButton("Cancel Bet", callback_data=f"roul_cancel_{user_id}"), 'danger')]  # RED
    ]
    return create_styled_keyboard(keyboard)

def create_roulette_number_selection_keyboard(user_id, selected_numbers):
    """Create keyboard for number selection (0-36) with 3 numbers per row (COLORED buttons)"""
    keyboard = [
        # Row 1: GREEN Start button
        [apply_button_style(InlineKeyboardButton("Start", callback_data=f"roul_start_numbers_{user_id}"), 'success')]
    ]

    # Row 2: Number 0 alone
    emoji_0 = get_roulette_number_emoji(0)
    selected_0 = "✅ " if 0 in selected_numbers else ""
    btn_0 = InlineKeyboardButton(f"{selected_0}{emoji_0}  0  ", callback_data=f"roul_num_0_{user_id}")
    if 0 in selected_numbers:
        keyboard.append([apply_button_style(btn_0, 'success')])  # GREEN if selected
    else:
        keyboard.append([btn_0.to_dict()])

    # Rows 3-14: Numbers 1-36 in rows of 3 (12 rows total)
    for row_start in range(1, 37, 3):
        row = []
        for num in range(row_start, min(row_start + 3, 37)):
            emoji = get_roulette_number_emoji(num)
            selected = "✅ " if num in selected_numbers else ""
            btn = InlineKeyboardButton(f"{selected}{emoji}  {num}  ", callback_data=f"roul_num_{num}_{user_id}")
            if num in selected_numbers:
                row.append(apply_button_style(btn, 'success'))  # GREEN if selected
            else:
                row.append(btn.to_dict())
        keyboard.append(row)

    # Last row: RED Back button
    keyboard.append([apply_button_style(InlineKeyboardButton("Back", callback_data=f"roul_back_{user_id}"), 'danger')])

    return create_styled_keyboard(keyboard)

@check_banned
@check_maintenance
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("roulette"):
        await update.message.reply_text(
            "\U0001f527 <b>Roulette</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    message_text = update.message.text.strip()
    args = message_text.replace('/roulette', '').replace('/roul', '').strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # NEW: Support for /roul amount (interactive menu)
    if len(args) == 1:
        try:
            bet_amount_str = args[0].lower()
            # Display-currency aware (parity with blackjack/tower).
            bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return

        # Check bet limits
        if not await check_bet_limits(update, bet_amount, 'roulette'):
            return

        # Check balance
        if get_active_balance_usd(user.id) < bet_amount:
            await send_insufficient_balance_message(update)
            return

        # Store bet amount and show interactive menu
        context.user_data['roulette_bet_amount'] = bet_amount
        context.user_data['roulette_selected_numbers'] = []
        context.user_data['roulette_selection'] = None

        menu_text = (
            f"{pe('target')} <b>Roulette Game</b>\n\n"
            f"{pe('money')} Bet Amount: <b>{dformat(bet_amount)}</b>\n\n"
            f"Select your bet or choose numbers:"
        )

        # Try to send with roulette image if available
        roulette_image_path = os.path.join(BASE_DIR, ROULETTE_IMAGE) if ROULETTE_IMAGE else None
        if roulette_image_path and os.path.exists(roulette_image_path):
            try:
                with open(roulette_image_path, 'rb') as photo:
                    sent_message = await update.message.reply_photo(
                        photo=photo,
                        caption=menu_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=create_roulette_menu_keyboard(user.id, bet_amount)
                    )
                    set_menu_owner(sent_message, user.id)
                    return
            except Exception as e:
                logging.warning(f"Could not send roulette image: {e}")
                # Fall back to text-only message

        # Text-only fallback if image not available or failed
        sent_message = await update.message.reply_text(
            menu_text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_roulette_menu_keyboard(user.id, bet_amount)
        )
        set_menu_owner(sent_message, user.id)
        return

    # OLD: Support for /roul amount choice (classic mode)
    if len(args) != 2:
        await update.message.reply_text(
            "Usage:\n"
            "• <b>Interactive Menu:</b> /roul amount\n"
            "• <b>Quick Bet:</b> /roul amount choice\n\n"
            "Examples:\n"
            "• /roul 10 (opens menu)\n"
            "• /roul 1 5 (quick bet on number 5)\n"
            "• /roul all red (quick bet on red)\n"
            "• /roul 1 even (quick bet on even)\n"
            "• /roul 1 low (quick bet 1-18)\n"
            "• /roul 1 high (quick bet 19-36)\n"
            "• /roul 1 column1 (quick bet on column 1)",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        bet_amount_str = args[0].lower()
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return
    choice = args[1].lower()

    if not await check_bet_limits(update, bet_amount, 'roulette'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    valid_numbers = list(range(0, 37))
    valid_choices = ["red", "black", "even", "odd", "low", "high", "column1", "column2", "column3"]
    choice_numbers = []  # Initialize for template rendering
    if choice.isdigit():
        if int(choice) not in valid_numbers:
            await update.message.reply_text("Number must be between 0 and 36.")
            return
        choice_type = "number"
        choice_numbers = [int(choice)]
    elif choice in valid_choices:
        choice_type = "special"
        if choice in ROULETTE_CONFIG:
            choice_numbers = ROULETTE_CONFIG[choice].get("numbers", [])
    else:
        await update.message.reply_text("Invalid choice. Use a number (0-36), red, black, etc.")
        return

    # Use user's provably fair seeds with fresh game client seed (like mines)
    # This ensures each game has unique, unpredictable seeds
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)  # Increment nonce at game start to ensure unique results

    # Generate fresh client seed for this specific game
    game_client_seed = generate_game_client_seed()
    winning_number = get_provably_fair_result(seeds["server_seed"], game_client_seed, current_nonce, 37)
    game_id = generate_unique_id("RL")

    # Send roulette sticker animation for the winning number
    try:
        sticker_id = ROULETTE_STICKERS[winning_number]
        await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=sticker_id)
        await asyncio.sleep(2.5)  # Let animation play before showing result
    except Exception as e:
        logging.warning(f"Failed to send roulette sticker: {e}")

    win = False
    multiplier = 0
    if choice_type == "number":
        if int(choice) == winning_number:
            win = True
            multiplier = ROULETTE_CONFIG["single_number"]["multiplier"]
    elif choice in ROULETTE_CONFIG:
        config = ROULETTE_CONFIG[choice]
        if winning_number in config["numbers"]:
            win = True
            multiplier = config["multiplier"]

    if winning_number == 0: color = "🟢 Green"
    elif winning_number in ROULETTE_CONFIG["red"]["numbers"]: color = "🔴 Red"
    else: color = "⚫ Black"

    if win:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} You win {format_for_user(user.id, winnings)}! (Multiplier: {multiplier}x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} You lose {format_for_user(user.id, bet_amount)}. Better luck next time!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    # Note: nonce was incremented at game start for provably fair

    game_sessions[game_id] = {
        "id": game_id, "game_type": "roulette", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": win, "multiplier": multiplier, "choice": choice, "result": winning_number,
        "server_seed": seeds["server_seed"], "client_seed": game_client_seed, "nonce": current_nonce
    }
    update_pnl(user.id)
    save_user_data(user.id)

    # Store provably fair record
    store_provably_fair_record(game_id, "roulette", seeds["server_seed"], game_client_seed, current_nonce,
                               result_data=f"Winning number: {winning_number}, Choice: {choice}")

    # Send template
    username = f"@{user.username}" if user.username else f"User{user.id}"
    template = _render_roulette_sync(
        username=username,
        bet_amount=bet_amount,
        choice=choice,
        choice_numbers=choice_numbers or [],
        winning_number=winning_number,
        won=win,
        multiplier=multiplier,
        winnings=winnings if win else 0,
        game_id=game_id,
    )
    pf_button = await create_provably_fair_button(game_id, context)
    kb = InlineKeyboardMarkup([[pf_button]])

    caption = (f"{pe('target')} <b>Roulette Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"{pe('casino')} Winning Number: <b>{winning_number}</b> {color}\n"
        f"{pe('dice')} Your Choice: {choice}\n💰 Your Bet: {dformat(bet_amount)}\n\n{result_text}")

    if template:
        await update.message.reply_photo(
            photo=template,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
    else:
        await update.message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )

@check_banned
@check_maintenance
async def roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle roulette interactive menu callbacks"""
    query = update.callback_query
    user = query.from_user

    if not query.data.startswith("roul_"):
        try: await query.answer()
        except: pass
        return

    if not await _acquire_callback(query.id):
        try: await query.answer()
        except: pass
        return

    # Parse callback data
    parts = query.data.split("_")
    action = parts[1]
    user_id_from_button = int(parts[-1]) if parts[-1].isdigit() else None

    # User-specific button check
    if user_id_from_button and user.id != user_id_from_button:
        await query.answer("This menu is not for you!", show_alert=True)
        return

    await query.answer()
    current_task = asyncio.current_task()
    if current_task is not None:
        current_task.add_done_callback(lambda _task, qid=query.id: _release_callback(qid))

    # Rebet - place the same bet again (handled before bet_amount check since it uses old game data)
    if action == "rebet":
        # parts: ['roul', 'rebet', game_id, user_id]
        if len(parts) < 4:
            await query.answer("Invalid rebet request!", show_alert=True)
            return

        old_game_id = parts[2]
        old_game = game_sessions.get(old_game_id)

        if not old_game:
            await query.answer("Previous game not found!", show_alert=True)
            return

        if old_game.get("user_id") != user.id:
            await query.answer("This is not your game!", show_alert=True)
            return

        # Get bet details from old game
        rebet_amount = old_game.get("bet_amount", 0)
        rebet_choice = old_game.get("choice")
        rebet_numbers = old_game.get("choice_numbers")

        if not rebet_choice or rebet_amount <= 0:
            await query.answer("Cannot rebet - invalid game data!", show_alert=True)
            return

        # ATOMIC balance check + deduct to prevent race conditions
        await ensure_user_in_wallets(user.id, user.username, context=context)
        try:
            crypto_deducted, coin = await deduct_wallet_safe(user.id, rebet_amount)
        except ValueError:
            await query.answer(f"{pe('cross')} Insufficient balance! Need ${rebet_amount:.2f}", show_alert=True)
            return
        save_user_data(user.id)

        # Generate new result with provably fair
        seeds = get_user_seeds(user.id)
        current_nonce = seeds["nonce"]
        increment_user_nonce(user.id)
        winning_number = get_provably_fair_result(seeds["server_seed"], seeds["client_seed"], current_nonce, 37)
        game_id = generate_unique_id("RL")

        # Send roulette sticker animation for the winning number
        try:
            sticker_id = ROULETTE_STICKERS[winning_number]
            await context.bot.send_sticker(chat_id=query.message.chat_id, sticker=sticker_id)
            await asyncio.sleep(2.5)  # Let animation play before showing result
        except Exception as e:
            logging.warning(f"Failed to send roulette sticker in rebet: {e}")

        # Determine win/loss
        win = False
        multiplier = 0

        if rebet_choice == "numbers" and rebet_numbers:
            multiplier_map = {1: 36, 2: 18, 3: 12, 4: 9, 5: 7, 6: 6}
            multiplier = multiplier_map.get(len(rebet_numbers), 1)
            if winning_number in rebet_numbers:
                win = True
            choice_display = f"Numbers: {', '.join(map(str, sorted(rebet_numbers)))}"
        elif rebet_choice in ROULETTE_CONFIG:
            config = ROULETTE_CONFIG[rebet_choice]
            if winning_number in config["numbers"]:
                win = True
                multiplier = config["multiplier"]
            # Friendly display names
            if rebet_choice == "dozen1":
                choice_display = "1-12 (Dozen 1)"
            elif rebet_choice == "dozen2":
                choice_display = "13-24 (Dozen 2)"
            elif rebet_choice == "dozen3":
                choice_display = "25-36 (Dozen 3)"
            else:
                choice_display = rebet_choice.upper()
        else:
            choice_display = rebet_choice

        # Determine color
        if winning_number == 0:
            color = "🟢 Green"
        elif winning_number in ROULETTE_CONFIG["red"]["numbers"]:
            color = "🔴 Red"
        else:
            color = "⚫ Black"

        # Process win/loss
        if win:
            winnings = rebet_amount * multiplier
            credit_wallet(user.id, winnings)
            result_text = f"{pe('win')} You win {format_for_user(user.id, winnings)}! (Multiplier: {multiplier}x)"
            await update_stats_on_bet(user.id, game_id, rebet_amount, True, multiplier=multiplier, context=context)
        else:
            result_text = f"{pe('lose')} You lose ${rebet_amount:.2f}. Better luck next time!"
            await update_stats_on_bet(user.id, game_id, rebet_amount, False, context=context)

        # Store game session with rebet data
        game_sessions[game_id] = {
            "id": game_id, "game_type": "roulette", "user_id": user.id,
            "bet_amount": rebet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
            "active_currency": get_active_currency(user.id),
            "crypto_bet_amount": rebet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
            "win": win, "multiplier": multiplier, "choice": rebet_choice, "result": winning_number,
            "server_seed": seeds["server_seed"], "client_seed": seeds["client_seed"], "nonce": current_nonce,
            "choice_numbers": rebet_numbers
        }
        update_pnl(user.id)
        save_user_data(user.id)

        # Store provably fair record
        store_provably_fair_record(game_id, "roulette", seeds["server_seed"], seeds["client_seed"], current_nonce,
                                   result_data=f"Winning number: {winning_number}, Choice: {rebet_choice}")

        # Send template
        username = f"@{user.username}" if user.username else f"User{user.id}"
        template = _render_roulette_sync(
            username=username,
            bet_amount=rebet_amount,
            choice=rebet_choice,
            choice_numbers=rebet_numbers or [],
            winning_number=winning_number,
            won=win,
            multiplier=multiplier,
            winnings=winnings if win else 0,
            game_id=game_id,
        )
        pf_button = await create_provably_fair_button(game_id, context)
        rebet_button = InlineKeyboardButton("Rebet", callback_data=f"roul_rebet_{game_id}_{user.id}")
        kb = InlineKeyboardMarkup([[pf_button], [rebet_button]])

        caption = (f"{pe('target')} <b>Roulette Result</b> (ID: <code>{game_id}</code>)\n\n"
            f"{pe('casino')} Winning Number: <b>{winning_number}</b> {color}\n"
            f"{pe('dice')} Your Choice: {choice_display}\n"
            f"{pe('money')} Your Bet: ${rebet_amount:.2f}\n\n{result_text}")

        if template:
            chat_type = query.message.chat.type
            try:
                await query.edit_message_media(
                    InputMediaPhoto(template, caption=caption, parse_mode=ParseMode.HTML),
                    reply_markup=kb
                )
            except Exception:
                # Failed to edit media, send new photo message
                if chat_type in ["group", "supergroup"]:
                    # In groups: send as reply (don't delete)
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=template,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb,
                        reply_to_message_id=query.message.message_id
                    )
                else:
                    # In DMs: delete and send new
                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await query.message.reply_photo(
                        photo=template,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb
                    )
        else:
            await safe_edit_message(query, caption, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # Get stored bet amount
    bet_amount = context.user_data.get('roulette_bet_amount')
    if not bet_amount:
        await safe_edit_message(query, "Session expired. Please start a new game with /roul amount")
        return

    # Cancel bet
    if action == "cancel":
        context.user_data.clear()
        await safe_edit_message(query, "🎯 Roulette game cancelled.")
        return

    # Back to main menu from number selection
    if action == "back":
        context.user_data['roulette_selected_numbers'] = []
        menu_text = (
            f"{pe('target')} <b>Roulette Game</b>\n\n"
            f"{pe('money')} Bet Amount: <b>{dformat(bet_amount)}</b>\n\n"
            f"Select your bet or choose numbers:"
        )
        await safe_edit_message(
            query,
            menu_text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_roulette_menu_keyboard(user.id, bet_amount)
        )
        return

    # Number selection mode
    if action == "num":
        selected_numbers = context.user_data.get('roulette_selected_numbers', [])
        number = int(parts[2])

        if number in selected_numbers:
            # Deselect
            selected_numbers.remove(number)
        else:
            # Select (max 6)
            if len(selected_numbers) >= 6:
                await query.answer("Maximum 6 numbers allowed!", show_alert=True)
                return
            selected_numbers.append(number)

        context.user_data['roulette_selected_numbers'] = selected_numbers

        # Update keyboard
        multiplier_map = {1: 36, 2: 18, 3: 12, 4: 9, 5: 7, 6: 6}
        multiplier = multiplier_map.get(len(selected_numbers), 1)

        menu_text = (
            f"{pe('target')} <b>Roulette - Number Selection</b>\n\n"
            f"{pe('money')} Bet Amount: <b>{dformat(bet_amount)}</b>\n"
            f"{pe('dice')} Selected: <b>{len(selected_numbers)}/6 numbers</b>\n"
            f"{pe('chart')} Multiplier: <b>{multiplier}x</b>\n\n"
            f"Select up to 6 numbers (tap to toggle):"
        )
        await safe_edit_message(
            query,
            menu_text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_roulette_number_selection_keyboard(user.id, selected_numbers)
        )
        return

    # Bet on number - show number selection
    if action == "bet" and len(parts) >= 3 and parts[2] == "number":
        context.user_data['roulette_selected_numbers'] = []
        menu_text = (
            f"{pe('target')} <b>Roulette - Number Selection</b>\n\n"
            f"{pe('money')} Bet Amount: <b>{dformat(bet_amount)}</b>\n"
            f"{pe('dice')} Selected: <b>0/6 numbers</b>\n"
            f"{pe('chart')} Multiplier: <b>36x</b>\n\n"
            f"Select up to 6 numbers (tap to toggle):"
        )
        await safe_edit_message(
            query,
            menu_text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_roulette_number_selection_keyboard(user.id, [])
        )
        return

    # Start with number selection
    if action == "start" and len(parts) >= 3 and parts[2] == "numbers":
        selected_numbers = context.user_data.get('roulette_selected_numbers', [])
        if not selected_numbers:
            await query.answer("Please select at least one number!", show_alert=True)
            return

        # Play with selected numbers
        choice = "numbers"
        choice_numbers = selected_numbers
    # Start with single option selection
    elif action == "start":
        selection = context.user_data.get('roulette_selection')
        if not selection:
            await query.answer("Please select a bet option first!", show_alert=True)
            return
        choice = selection
        choice_numbers = None
    # Selection from menu
    else:
        # Map action to choice
        choice_map = {
            "1-12": "dozen1", "13-24": "dozen2", "25-36": "dozen3",  # Dozen bets (not column bets!)
            "1-18": "low", "19-36": "high",
            "even": "even", "odd": "odd",
            "red": "red", "black": "black"
        }

        # Store selection
        if action in choice_map or action in ["1-12", "13-24", "25-36", "1-18", "19-36"]:
            # Map the selection - FIXED: "1-12" etc are dozen bets, not column bets
            if action == "1-12":
                choice = "dozen1"  # Numbers 1-12
            elif action == "13-24":
                choice = "dozen2"  # Numbers 13-24
            elif action == "25-36":
                choice = "dozen3"  # Numbers 25-36
            elif action == "1-18":
                choice = "low"
            elif action == "19-36":
                choice = "high"
            else:
                choice = action

            context.user_data['roulette_selection'] = choice

            # Display friendly name for dozen bets
            display_name = choice.upper()
            if choice == "dozen1":
                display_name = "1-12 (Dozen 1)"
            elif choice == "dozen2":
                display_name = "13-24 (Dozen 2)"
            elif choice == "dozen3":
                display_name = "25-36 (Dozen 3)"

            # Update menu to show selection
            menu_text = (
                f"{pe('target')} <b>Roulette Game</b>\n\n"
                f"{pe('money')} Bet Amount: <b>{dformat(bet_amount)}</b>\n"
                f"{pe('dice')} Selected: <b>{display_name}</b>\n\n"
                f"Tap <b>Start</b> to play or select a different option:"
            )
            await safe_edit_message(
                query,
                menu_text,
                parse_mode=ParseMode.HTML,
                reply_markup=create_roulette_menu_keyboard(user.id, bet_amount, selected=choice)
            )
            return
        else:
            return

    # Execute the game
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await safe_edit_message(query, "❌ Insufficient balance.")
        context.user_data.clear()
        return
    save_user_data(user.id)

    # Generate result with provably fair seeds and increment nonce at game start
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)  # Increment nonce at game start to ensure unique results
    winning_number = get_provably_fair_result(seeds["server_seed"], seeds["client_seed"], current_nonce, 37)
    game_id = generate_unique_id("RL")

    # Send roulette sticker animation for the winning number
    try:
        sticker_id = ROULETTE_STICKERS[winning_number]
        # Send as reply to the callback message to help user find it
        await query.message.reply_sticker(sticker=sticker_id)
        await asyncio.sleep(2.5)  # Let animation play before showing result
    except Exception as e:
        logging.warning(f"Failed to send roulette sticker in start action: {e}")

    # Ensure choice_numbers is defined (will be None for non-number bets)
    try:
        _ = choice_numbers
    except NameError:
        choice_numbers = None

    # Determine win/loss
    win = False
    multiplier = 0

    if choice == "numbers":
        # Multiple number bet
        multiplier_map = {1: 36, 2: 18, 3: 12, 4: 9, 5: 7, 6: 6}
        multiplier = multiplier_map.get(len(choice_numbers), 1)
        if winning_number in choice_numbers:
            win = True
        choice_display = f"Numbers: {', '.join(map(str, sorted(choice_numbers)))}"
    elif choice in ROULETTE_CONFIG:
        config = ROULETTE_CONFIG[choice]
        if winning_number in config["numbers"]:
            win = True
            multiplier = config["multiplier"]
        # Friendly display names for dozen bets
        if choice == "dozen1":
            choice_display = "1-12 (Dozen 1)"
        elif choice == "dozen2":
            choice_display = "13-24 (Dozen 2)"
        elif choice == "dozen3":
            choice_display = "25-36 (Dozen 3)"
        else:
            choice_display = choice.upper()
    else:
        choice_display = choice

    # Determine color
    if winning_number == 0:
        color = "🟢 Green"
    elif winning_number in ROULETTE_CONFIG["red"]["numbers"]:
        color = "🔴 Red"
    else:
        color = "⚫ Black"

    # Process win/loss
    if win:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} You win {format_for_user(user.id, winnings)}! (Multiplier: {multiplier}x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} You lose {format_for_user(user.id, bet_amount)}. Better luck next time!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    # Note: nonce was incremented at game start for provably fair

    # Store game session with rebet data
    game_sessions[game_id] = {
        "id": game_id, "game_type": "roulette", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": win, "multiplier": multiplier, "choice": choice, "result": winning_number,
        "server_seed": seeds["server_seed"], "client_seed": seeds["client_seed"], "nonce": current_nonce,
        "choice_numbers": choice_numbers  # Store for rebet
    }
    update_pnl(user.id)
    save_user_data(user.id)

    # Store provably fair record
    store_provably_fair_record(game_id, "roulette", seeds["server_seed"], seeds["client_seed"], current_nonce,
                               result_data=f"Winning number: {winning_number}, Choice: {choice}")

    # Send template
    username = f"@{user.username}" if user.username else f"User{user.id}"
    template = _render_roulette_sync(
        username=username,
        bet_amount=bet_amount,
        choice=choice,
        choice_numbers=choice_numbers or [],
        winning_number=winning_number,
        won=win,
        multiplier=multiplier,
        winnings=winnings if win else 0,
        game_id=game_id,
    )
    pf_button = await create_provably_fair_button(game_id, context)
    rebet_button = InlineKeyboardButton("Rebet", callback_data=f"roul_rebet_{game_id}_{user.id}")
    kb = InlineKeyboardMarkup([[pf_button], [rebet_button]])

    caption = (f"{pe('target')} <b>Roulette Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"{pe('casino')} Winning Number: <b>{winning_number}</b> {color}\n"
        f"{pe('dice')} Your Choice: {choice_display}\n"
        f"{pe('money')} Your Bet: {dformat(bet_amount)}\n\n{result_text}")

    if template:
        await query.edit_message_media(
            InputMediaPhoto(template, caption=caption, parse_mode=ParseMode.HTML),
            reply_markup=kb
        )
    else:
        await safe_edit_message(query, caption, parse_mode=ParseMode.HTML, reply_markup=kb)

    # Clear user data
    context.user_data.clear()

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler(['roul', 'roulette'], roulette_command, block=False))
    app.add_handler(CallbackQueryHandler(roulette_callback, pattern='^roul_', block=False))

