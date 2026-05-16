"""Auto-split from bot.py — plugins.games_keno."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def generate_keno_numbers(server_seed, client_seed, nonce, count=10):
    """Generate deterministic keno numbers for Keno game - provably fair"""
    numbers = []
    offset = 0
    # Use nonce * 1000 to ensure consecutive games don't produce overlapping hash inputs
    base_nonce = nonce * 1000
    while len(numbers) < count:
        # Generate numbers 1-40
        num = get_provably_fair_result(server_seed, client_seed, base_nonce + offset, 40) + 1
        if num not in numbers:
            numbers.append(num)
        offset += 1
    return sorted(numbers)

def create_keno_keyboard(game_id, selected_numbers):
    """Create the 40-number grid for Keno with COLORED buttons (Bot API 9.4)"""
    buttons = []
    for i in range(1, 41):
        btn = InlineKeyboardButton(str(i) if i not in selected_numbers else f"✓ {i}",
                                   callback_data=f"keno_pick_{game_id}_{i}")
        # Apply styles: primary (blue) for unselected, success (green) for selected
        if i in selected_numbers:
            buttons.append(apply_button_style(btn, 'success'))  # GREEN for selected
        else:
            buttons.append(apply_button_style(btn, 'primary'))  # BLUE for unselected

    # Create 8 rows of 5 numbers each
    keyboard = [buttons[i:i+5] for i in range(0, 40, 5)]

    # Add action buttons (with .to_dict() for non-styled buttons)
    action_row1 = [
        apply_button_style(InlineKeyboardButton("How to Play", callback_data=f"keno_info_{game_id}"), 'primary', peb('info')),
        apply_button_style(InlineKeyboardButton("Clear All", callback_data=f"keno_clear_{game_id}"), 'danger', peb('clear_all'))
    ]
    action_row2 = [
        InlineKeyboardButton("Payout Table", callback_data=f"keno_payout_{game_id}").to_dict(),
        apply_button_style(InlineKeyboardButton("Cancel", callback_data=f"keno_cancel_{game_id}"), 'danger', peb('cross'))  # RED
    ]

    # Add place bet button if numbers are selected (GREEN)
    if selected_numbers:
        action_row3 = [
            apply_button_style(
                InlineKeyboardButton(f"Place Bet ({len(selected_numbers)} numbers)", callback_data=f"keno_place_{game_id}"),
                'success',  # GREEN
                peb('keno_play')
            )
        ]
        keyboard.extend([action_row1, action_row2, action_row3])
    else:
        keyboard.extend([action_row1, action_row2])

    return create_styled_keyboard(keyboard)

def get_keno_payout_text():
    """Get formatted payout table"""
    text = f"{pe('casino')} <b>KENO PAYOUT TABLE</b>\n────────────────\n\n"
    for picks in range(1, 11):
        text += f"{pe('chart')} <b>{picks} Pick{'s' if picks > 1 else ''}:</b>\n"
        payouts = KENO_PAYOUTS[picks]
        for matches, multiplier in payouts.items():
            if picks == 1 and matches == 0:
                text += f"   • No matches → {multiplier}x\n"
            else:
                text += f"   • {matches} match{'es' if matches != 1 else ''} → {multiplier}x\n"
        text += "\n"
    return text

@check_banned
@check_maintenance
async def keno_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Keno game: /keno amount
    """
    if not is_game_enabled("keno"):
        await update.message.reply_text(
            "\U0001f527 <b>Keno</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    args = update.message.text.strip().split()
    if len(args) != 2:
        await update.message.reply_text(
            "🎯 <b>KENO</b>\n\n"
            "<b>Usage:</b> <code>/keno amount</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/keno 10</code> - Start keno with $10\n"
            "• <code>/keno all</code> - Start keno with all balance\n\n"
            "<b>How to play:</b>\n"
            "1. Pick 1-10 numbers from 1-40\n"
            "2. Place your bet\n"
            "3. 10 random numbers are drawn\n"
            "4. Win based on how many you matched!\n\n"
            f"<b>Min bet:</b> ${MIN_BALANCE:.2f}",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except ValueError:
        await update.message.reply_text("Invalid amount. Please use a number.")
        return

    if not await check_bet_limits(update, bet_amount, 'keno'):
        return

    # Create game session
    game_id = generate_unique_id("KNO")
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "keno",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "selected_numbers": [],
        "status": "selecting",
        "timestamp": str(datetime.now(timezone.utc))
    }

    text = (
        f"{pe('target')} <b>KENO GAME</b>\n"
        f"────────\n\n"
        f"{pe('chart')} <b>Game Status:</b>\n"
        f"• Numbers Selected: 0/10\n"
        f"• Bet Amount: {dformat(bet_amount)}\n\n"
        f"📝 <b>Instructions:</b>\n"
        f"Pick 1 to 10 numbers from the grid below."
    )

    keyboard = create_keno_keyboard(game_id, [])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@check_banned
@check_maintenance
async def keno_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Keno game callbacks"""
    query = update.callback_query

    if not await _acquire_callback(query.id):
        try: await query.answer()
        except: pass
        return

    try:
        await query.answer()

        data = query.data
        parts = data.split('_')
        action = parts[1]
        game_id = parts[2]

        game = game_sessions.get(game_id)
        if not game or game["user_id"] != query.from_user.id:
            await query.answer("This is not your game!", show_alert=True)
            return

        if action == "pick":
            if game["status"] != "selecting":
                await query.answer("Game already completed!", show_alert=True)
                return

            number = int(parts[3])
            selected = game["selected_numbers"]

            if number in selected:
                selected.remove(number)
            else:
                if len(selected) >= 10:
                    await query.answer("Maximum 10 numbers allowed!", show_alert=True)
                    return
                selected.append(number)

            text = (
                f"{pe('target')} <b>KENO GAME</b>\n"
                f"────────\n\n"
                f"{pe('chart')} <b>Game Status:</b>\n"
                f"• Numbers Selected: {len(selected)}/10\n"
                f"• Bet Amount: ${game['bet_amount']:.2f}\n\n"
                f"📝 <b>Instructions:</b>\n"
                f"Pick 1 to 10 numbers from the grid below."
            )

            keyboard = create_keno_keyboard(game_id, selected)
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        elif action == "clear":
            game["selected_numbers"] = []
            text = (
                f"{pe('target')} <b>KENO GAME</b>\n"
                f"────────\n\n"
                f"{pe('chart')} <b>Game Status:</b>\n"
                f"• Numbers Selected: 0/10\n"
                f"• Bet Amount: ${game['bet_amount']:.2f}\n\n"
                f"📝 <b>Instructions:</b>\n"
                f"Pick 1 to 10 numbers from the grid below."
            )
            keyboard = create_keno_keyboard(game_id, [])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        elif action == "info":
            info_text = (
                "ℹ️ <b>HOW TO PLAY KENO</b>\n\n"
                "1️⃣ Select 1-10 numbers from 1-40\n"
                "2️⃣ Click 'Place Bet' when ready\n"
                "3️⃣ 10 random numbers will be drawn\n"
                "4️⃣ Win based on matches!\n\n"
                "<b>Tips:</b>\n"
                "• More picks = higher potential payout\n"
                "• But also need more matches to win\n"
                "• Check payout table for details"
            )
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f"keno_back_{game_id}")]])
            await query.edit_message_text(info_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        elif action == "payout":
            payout_text = get_keno_payout_text()
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f"keno_back_{game_id}")]])
            await query.edit_message_text(payout_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        elif action == "back":
            selected = game["selected_numbers"]
            text = (
                f"{pe('target')} <b>KENO GAME</b>\n"
                f"────────\n\n"
                f"{pe('chart')} <b>Game Status:</b>\n"
                f"• Numbers Selected: {len(selected)}/10\n"
                f"• Bet Amount: ${game['bet_amount']:.2f}\n\n"
                f"📝 <b>Instructions:</b>\n"
                f"Pick 1 to 10 numbers from the grid below."
            )
            keyboard = create_keno_keyboard(game_id, selected)
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        elif action == "place":
            selected = game["selected_numbers"]
            if not selected:
                await query.answer("Please select at least 1 number!", show_alert=True)
                return

            # ATOMIC balance check + deduct to prevent race conditions
            try:
                crypto_deducted, coin = await deduct_wallet_safe(game["user_id"], game["bet_amount"])
            except ValueError:
                await query.answer("Insufficient balance.", show_alert=True)
                return
            save_user_data(game["user_id"])

            # Use provably fair generation for keno with fresh game client seed (like mines)
            seeds = get_user_seeds(game["user_id"])
            current_nonce = seeds["nonce"]
            increment_user_nonce(game["user_id"])

            # Generate fresh client seed for this specific game
            game_client_seed = generate_game_client_seed()

            # Generate keno numbers using provably fair method
            drawn_numbers = generate_keno_numbers(seeds["server_seed"], game_client_seed, current_nonce, 10)

            # Calculate matches
            matches = len(set(selected) & set(drawn_numbers))
            num_picks = len(selected)

            # Get multiplier
            multiplier = KENO_PAYOUTS.get(num_picks, {}).get(matches, 0.0)

            if multiplier > 0:
                winnings = game["bet_amount"] * multiplier
                credit_wallet(game["user_id"], winnings)
                profit = winnings - game["bet_amount"]
                win = True
            else:
                winnings = 0
                profit = -game["bet_amount"]
                win = False

            # Update game - store the game-specific client seed for provably fair verification
            game["status"] = "completed"
            game["drawn_numbers"] = drawn_numbers
            game["matches"] = matches
            game["multiplier"] = multiplier
            game["server_seed"] = seeds["server_seed"]
            game["client_seed"] = game_client_seed  # Store fresh game client seed
            game["nonce"] = current_nonce
            game["win"] = win

            # Update stats
            await update_stats_on_bet(game["user_id"], game_id, game["bet_amount"], win, multiplier=multiplier, context=context)
            update_pnl(game["user_id"])
            save_user_data(game["user_id"])

            # Format result
            selected_str = ", ".join(str(n) for n in sorted(selected))
            drawn_str = ", ".join(str(n) for n in sorted(drawn_numbers))
            matched_str = ", ".join(str(n) for n in sorted(set(selected) & set(drawn_numbers)))

            result_text = (
                f"{pe('target')} <b>KENO RESULT</b>\n"
                f"────────────────\n\n"
                f"{pe('pin')} <b>Your Numbers:</b> {selected_str}\n"
                f"{pe('dice')} <b>Drawn Numbers:</b> {drawn_str}\n"
                f"{pe('check')} <b>Matches:</b> {matches}/{num_picks}\n"
            )

            if matched_str:
                result_text += f"{pe('win')} <b>Matched:</b> {matched_str}\n"

            result_text += "\n"

            if win:
                result_text += (
                    f"{pe('win')} <b>YOU WIN!</b>\n"
                    f"{pe('money')} Multiplier: {multiplier}x\n"
                    f"{pe('balance')} Profit: {dformat(profit)}\n"
                    f"{pe('withdraw')} Total Payout: {dformat(winnings)}\n"
                )
            else:
                result_text += (
                    f"{pe('cross')} <b>NO WIN</b>\n"
                    f"{pe('withdraw')} Lost: ${game['bet_amount']:.2f}\n"
                    f"Better luck next time!"
                )

            result_text += f"\n<b>Game ID:</b> <code>{game_id}</code>"

            # Store provably fair record
            store_provably_fair_record(game_id, "keno", game["server_seed"], game["client_seed"], game["nonce"],
                                       result_data=f"Matches: {matches}/{num_picks}, Drawn: {drawn_numbers}")

            # Send template
            keno_user = game["user_id"]
            keno_user_obj = await context.bot.get_chat(keno_user)
            username = f"@{keno_user_obj.username}" if keno_user_obj.username else f"User{keno_user}"
            template = _render_keno_sync(
                username=username,
                bet_amount=game["bet_amount"],
                selected_numbers=list(selected),
                drawn_numbers=list(drawn_numbers),
                matches=matches,
                num_picks=num_picks,
                won=win,
                multiplier=multiplier,
                winnings=winnings,
                game_id=game_id,
            )
            selected_str_callback = ",".join(str(n) for n in sorted(selected))
            pf_button = await create_provably_fair_button(game_id, context)
            rebet_btn = apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"keno_rebet_{game['bet_amount']}_{selected_str_callback}_{game['user_id']}"), 'primary')
            double_btn = apply_button_style(InlineKeyboardButton("Double", callback_data=f"keno_double_{game['bet_amount']}_{selected_str_callback}_{game['user_id']}"), 'success')
            kb = InlineKeyboardMarkup([[rebet_btn, double_btn], [pf_button]])

            if win:
                caption = f"{pe('win')} <b>YOU WIN!</b>\n{pe('money')} Multiplier: {multiplier}x\n{pe('balance')} Profit: {dformat(profit)}\n{pe('withdraw')} Total Payout: {dformat(winnings)}\n<b>Game ID:</b> <code>{game_id}</code>"
            else:
                caption = f"{pe('cross')} <b>NO WIN</b>\n{pe('withdraw')} Lost: ${game['bet_amount']:.2f}\nBetter luck next time!\n<b>Game ID:</b> <code>{game_id}</code>"

            if template:
                await query.edit_message_media(
                    InputMediaPhoto(template, caption=caption, parse_mode=ParseMode.HTML),
                    reply_markup=kb
                )
            else:
                await query.edit_message_text(caption, parse_mode=ParseMode.HTML, reply_markup=kb)

        elif action == "cancel":
            game["status"] = "cancelled"
            await query.edit_message_text(f"{pe('cross')} Keno game cancelled.", parse_mode=ParseMode.HTML)
    finally:
        _release_callback(query.id)

@check_banned
@check_maintenance
async def keno_rebet_double_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Rebet and Double buttons for keno"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data: keno_rebet_{bet_amount}_{selected_numbers}_{user_id}
    parts = query.data.split("_")
    if len(parts) < 5:
        await query.answer("Invalid button data", show_alert=True)
        return

    action = parts[1]  # rebet or double
    try:
        original_bet = float(parts[2])
        selected_str = parts[3]  # comma-separated numbers
        button_user_id = int(parts[4])
        selected_numbers = [int(n) for n in selected_str.split(",") if n]
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
    if not await check_bet_limits(update, bet_amount, 'keno', user_id=user.id):
        await query.answer("Bet exceeds limits", show_alert=True)
        return

    # Deduct bet atomically (per-user lock prevents double-spend across
    # concurrent rebet/double clicks and across queue workers).
    try:
        await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await query.answer("Insufficient balance!", show_alert=True)
        return
    save_user_data(user.id)

    game_id = generate_unique_id("KN")

    # Use provably fair generation for keno (deterministic)
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)

    # Generate keno numbers using provably fair method
    drawn_numbers = generate_keno_numbers(seeds["server_seed"], seeds["client_seed"], current_nonce, 10)

    # Calculate matches
    matches = len(set(selected_numbers) & set(drawn_numbers))
    num_picks = len(selected_numbers)

    # Get multiplier
    multiplier = KENO_PAYOUTS.get(num_picks, {}).get(matches, 0.0)

    if multiplier > 0:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        profit = winnings - bet_amount
        win = True
    else:
        winnings = 0
        profit = -bet_amount
        win = False

    # Store game session
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "keno",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "selected_numbers": selected_numbers,
        "drawn_numbers": drawn_numbers,
        "matches": matches,
        "multiplier": multiplier,
        "status": "completed",
        "timestamp": str(datetime.now(timezone.utc)),
        "server_seed": seeds["server_seed"],
        "client_seed": seeds["client_seed"],  # Store user's client seed
        "nonce": current_nonce,
        "win": win
    }

    # Update stats
    await update_stats_on_bet(user.id, game_id, bet_amount, win, multiplier=multiplier, context=context)
    update_pnl(user.id)
    save_user_data(user.id)

    # Format result
    selected_str_display = ", ".join(str(n) for n in sorted(selected_numbers))
    drawn_str = ", ".join(str(n) for n in sorted(drawn_numbers))
    matched_str = ", ".join(str(n) for n in sorted(set(selected_numbers) & set(drawn_numbers)))

    result_text = (
        f"{pe('target')} <b>KENO RESULT</b>\n"
        f"────────────────\n\n"
        f"{pe('pin')} <b>Your Numbers:</b> {selected_str_display}\n"
        f"{pe('dice')} <b>Drawn Numbers:</b> {drawn_str}\n"
        f"{pe('check')} <b>Matches:</b> {matches}/{num_picks}\n"
    )

    if matched_str:
        result_text += f"{pe('win')} <b>Matched:</b> {matched_str}\n"

    result_text += "\n"

    if win:
        result_text += (
            f"{pe('win')} <b>YOU WIN!</b>\n"
            f"{pe('money')} Multiplier: {multiplier}x\n"
            f"{pe('balance')} Profit: {dformat(profit)}\n"
            f"{pe('withdraw')} Total Payout: {dformat(winnings)}\n"
        )
    else:
        result_text += (
            f"{pe('cross')} <b>NO WIN</b>\n"
            f"{pe('withdraw')} Lost: {dformat(bet_amount)}\n"
            f"Better luck next time!"
        )

    result_text += f"\n<b>Game ID:</b> <code>{game_id}</code>"

    # Store provably fair record
    store_provably_fair_record(game_id, "keno", seeds["server_seed"], seeds["client_seed"], current_nonce,
                               result_data=f"Matches: {matches}/{num_picks}, Drawn: {drawn_numbers}")

    # Add rebet/double and provably fair buttons
    selected_str_callback = ",".join(str(n) for n in sorted(selected_numbers))
    keyboard = [
        [
            apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"keno_rebet_{bet_amount}_{selected_str_callback}_{user.id}"), 'primary'),
            apply_button_style(InlineKeyboardButton("Double", callback_data=f"keno_double_{bet_amount}_{selected_str_callback}_{user.id}"), 'success')
        ],
        [await create_provably_fair_button(game_id, context)]
    ]

    # Handle photo-to-text transition
    chat_type = query.message.chat.type
    try:
        await query.edit_message_text(result_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        # Previous message was likely a photo
        if chat_type in ["group", "supergroup"]:
            # In groups: send new message as reply
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=result_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
                reply_to_message_id=query.message.message_id
            )
        else:
            # In DMs: try caption edit, then delete+send
            try:
                await query.edit_message_caption(caption=result_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception:
                try:
                    await query.message.delete()
                except Exception:
                    pass
                await query.message.reply_text(result_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('keno', keno_command, block=False))
    app.add_handler(CallbackQueryHandler(keno_rebet_double_callback, pattern='^keno_(rebet|double)_', block=False))
    app.add_handler(CallbackQueryHandler(keno_callback, pattern='^keno_', block=False))

