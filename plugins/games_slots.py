"""Auto-split from bot.py — plugins.games_slots."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

@check_banned
@check_maintenance
async def slots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("slots"):
        await update.message.reply_text(
            "\U0001f527 <b>Slots</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if len(args) != 2:
        await update.message.reply_text("Usage: /sl amount\nExample: /sl 5 or /sl all")
        return
    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet_amount = get_active_balance_usd(user.id)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet_amount, 'slots'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Generate provably fair seeds for slots
    game_id = generate_unique_id("SL")
    server_seed = generate_server_seed()
    client_seed = generate_client_seed()
    nonce = 1

    await update.message.reply_text(f"{pe('casino')} Spinning the slots...")
    command_msg_id = update.message.message_id
    slot_msg, used_helper = await smart_roll(context, update.effective_chat.id, "🎰", reply_to_message_id=command_msg_id)
    slot_value = slot_msg.dice.value
    if used_helper:
        await asyncio.sleep(HELPER_BOT_ANIMATION_DELAY)
    else:
        await asyncio.sleep(3)  # Standard slot animation wait

    win = False
    multiplier = 0
    win_type = ""
    # FIX: Updated slot machine logic with new multipliers
    if slot_value == 64: # 777
        win, multiplier, win_type = True, 20, "🍀 JACKPOT - Triple 7s!"
    elif slot_value in [1, 22, 43]: # bar, grape, lemon
        win, multiplier, win_type = True, 10, "🎉 Triple Match!"

    if win:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} {win_type}\nYou win {format_for_user(user.id, winnings)}! (Multiplier: {multiplier}x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} No match! You lose ${bet_amount:.2f}\nTry again for the jackpot!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "slots", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": win, "multiplier": multiplier, "result": slot_value,
        "server_seed": server_seed, "client_seed": client_seed, "nonce": nonce
    }

    # Store provably fair record
    store_provably_fair_record(game_id, "slots", server_seed, client_seed, nonce,
                               result_data=f"Slot value: {slot_value}, Multiplier: {multiplier}x")

    update_pnl(user.id)
    save_user_data(user.id)

    # Create keyboard with Rebet and Double buttons (NO provably fair for emoji-based slots)
    keyboard = [
        [
            apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"slots_rebet_{bet_amount}_{user.id}"), 'primary'),  # BLUE
            apply_button_style(InlineKeyboardButton("Double", callback_data=f"slots_double_{bet_amount}_{user.id}"), 'success')  # GREEN
        ]
    ]

    await update.message.reply_text(
        f"{pe('casino')} <b>Slots Result</b>\n\n💰 Your Bet: ${bet_amount:.2f}\n\n{result_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def slots_rebet_double_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Rebet and Double buttons for slots"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data: slots_rebet_{bet_amount}_{user_id} or slots_double_{bet_amount}_{user_id}
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
        bet_amount = original_bet
    else:  # double
        bet_amount = original_bet * 2

    # Check bet limits
    limits = bot_settings.get('game_limits', {}).get('slots', {})
    min_bet = limits.get('min', MIN_BALANCE)
    max_bet = limits.get('max')

    if bet_amount < min_bet:
        await query.answer(f"Minimum bet is ${min_bet:.2f}", show_alert=True)
        return
    if max_bet is not None and bet_amount > max_bet:
        await query.answer(f"Maximum bet is ${max_bet:.2f}", show_alert=True)
        return

    # Check balance
    if get_active_balance_usd(user.id) < bet_amount:
        await query.answer("Insufficient balance!", show_alert=True)
        return

    deduct_wallet(user.id, bet_amount)
    save_user_data(user.id)

    # Generate provably fair seeds for slots
    game_id = generate_unique_id("SL")
    server_seed = generate_server_seed()
    client_seed = generate_client_seed()
    nonce = 1

    await query.edit_message_text(f"{pe('casino')} Spinning the slots...")
    command_msg_id = query.message.message_id
    slot_msg, used_helper = await smart_roll(context, query.message.chat.id, "🎰", reply_to_message_id=command_msg_id)
    slot_value = slot_msg.dice.value
    if used_helper:
        await asyncio.sleep(HELPER_BOT_ANIMATION_DELAY)
    else:
        await asyncio.sleep(3)  # Standard slot animation wait

    win = False
    multiplier = 0
    win_type = ""
    # FIX: Updated slot machine logic with new multipliers
    if slot_value == 64: # 777
        win, multiplier, win_type = True, 20, "🍀 JACKPOT - Triple 7s!"
    elif slot_value in [1, 22, 43]: # bar, grape, lemon
        win, multiplier, win_type = True, 10, "🎉 Triple Match!"

    if win:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} {win_type}\nYou win {format_for_user(user.id, winnings)}! (Multiplier: {multiplier}x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} No match! You lose ${bet_amount:.2f}\nTry again for the jackpot!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "slots", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": win, "multiplier": multiplier, "result": slot_value,
        "server_seed": server_seed, "client_seed": client_seed, "nonce": nonce
    }

    # Store provably fair record
    store_provably_fair_record(game_id, "slots", server_seed, client_seed, nonce,
                               result_data=f"Slot value: {slot_value}, Multiplier: {multiplier}x")

    update_pnl(user.id)
    save_user_data(user.id)

    # Create keyboard with Rebet, Double, and Provably Fair buttons
    keyboard = [
        [
            apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"slots_rebet_{bet_amount}_{user.id}"), 'primary'),  # BLUE
            apply_button_style(InlineKeyboardButton("Double", callback_data=f"slots_double_{bet_amount}_{user.id}"), 'success')  # GREEN
        ]
        # NOTE: Slots is emoji-based, no provably fair verification (removed as per previous design decision)
    ]

    await query.edit_message_text(
        f"{pe('casino')} <b>Slots Result</b>\n\n💰 Your Bet: ${bet_amount:.2f}\n\n{result_text}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('sl', slots_command, block=False))
    app.add_handler(CallbackQueryHandler(slots_rebet_double_callback, pattern='^slots_(rebet|double)_', block=False))

