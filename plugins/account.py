"""Auto-split from bot.py — plugins.account."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

@check_banned
@check_maintenance
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("predict"):
        await update.message.reply_text(
            "\U0001f527 <b>Predict</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    args = update.message.text.strip().split()
    if len(args) != 3 or args[2].lower() not in ("up", "down"):
        await update.message.reply_text(
            "Usage: /predict amount up/down\nExample: /predict 1 up or /predict all up\n"
            "<b>Guess if the dice will be up (4-6) or down (1-3).</b>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except Exception:
        await update.message.reply_text("Invalid amount.")
        return

    direction = args[2].lower()
    if not await check_bet_limits(update, bet_amount, 'predict'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    await update.message.reply_text(f"Rolling the dice... {pe('dice')}", parse_mode=ParseMode.HTML)
    chat_type = update.effective_chat.type
    animation_wait = await smart_rate_limit(update.effective_chat.id, chat_type)
    command_msg_id = update.message.message_id
    try:
        dice_msg, used_helper = await smart_roll(context, update.effective_chat.id, "🎲", reply_to_message_id=command_msg_id)
        outcome = dice_msg.dice.value
        if used_helper:
            await asyncio.sleep(HELPER_BOT_ANIMATION_DELAY)
        else:
            await asyncio.sleep(animation_wait)
    except Exception as e:
        logging.error(f"Error sending dice in predict_command: {e}")
        # Refund the bet on error
        credit_wallet(user.id, bet_amount)
        save_user_data(user.id)
        await update.message.reply_text(f"{pe('cross')} An error occurred while rolling the dice. Your bet has been refunded.")
        return
    game_id = generate_unique_id("PRD")

    win = (direction == "up" and outcome in [4, 5, 6]) or (direction == "down" and outcome in [1, 2, 3])

    if win:
        winnings = bet_amount * 2
        credit_wallet(user.id, winnings)
        result_text = f"Result: {outcome} {pe('dice')}\n{pe('win')} You won! You receive ${winnings:.2f}."
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=2, context=context)
    else:
        result_text = f"Result: {outcome} {pe('dice')}\n{pe('lose')} You lost! Better luck next time."
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "predict", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": win, "multiplier": 2 if win else 0, "choice": direction, "result": outcome
    }
    update_pnl(user.id)
    save_user_data(user.id)
    await update.message.reply_text(f"{result_text}\nID: <code>{game_id}</code>", parse_mode=ParseMode.HTML)

async def handle_provably_fair_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE, pf_id: str):
    """Handle provably fair verification deep link"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Get the provably fair record
    pf_record = provably_fair_records.get(pf_id)

    if not pf_record:
        await update.message.reply_text(
            "❌ This provably fair verification link is invalid or has expired.\n\n"
            "Verification records are kept for recent games only.",
            parse_mode=ParseMode.HTML
        )
        return

    game_type = pf_record['game_type']

    # Build the verification message with game details
    text = (
        f"🔐 <b>Provable Fairness Verification</b>\n\n"
        f"<b>Game ID:</b> <code>{pf_record['game_id']}</code>\n"
        f"<b>Game Type:</b> {game_type.title()}\n\n"
        f"<b>Server Seed:</b>\n<code>{pf_record['server_seed']}</code>\n\n"
        f"<b>Client Seed:</b>\n<code>{pf_record['client_seed']}</code>\n\n"
        f"<b>Nonce:</b> {pf_record['nonce']}\n\n"
    )

    # Add result data if available
    if pf_record.get('result_data'):
        text += f"<b>Result Data:</b> {pf_record['result_data']}\n\n"

    text += (
        f"{pe('bulb')} <b>How to Verify:</b>\n"
        f"Copy the Python code below (long press on code → Copy) and run it.\n\n"
        f"<b>Online Python Compilers:</b>\n"
        f"• <a href='https://www.programiz.com/python-programming/online-compiler/'>Programiz</a>\n"
        f"• <a href='https://repl.it/languages/python3'>Repl.it</a>\n"
        f"• <a href='https://www.online-python.com/'>Online-Python</a>\n\n"
        f"The code is pre-filled with your game data!\n"
        f"Use /serverseed and /seed to view your seeds anytime."
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    # Generate and send game-specific verification code
    verification_code = generate_verification_code(pf_record)

    await update.message.reply_text(
        f"<b>📋 {game_type.title()} Verification Code:</b>\n\n"
        f"{verification_code}\n\n"
        f"{pe('bulb')} <b>Tip:</b> Long press on the code block to copy it easily!",
        parse_mode=ParseMode.MARKDOWN
    )

def hash_pin(pin: str) -> str:
    """Hashes a PIN using SHA256."""
    return hashlib.sha256(pin.encode()).hexdigest()

def is_valid_bep20_address(address: str) -> bool:
    """Validate if address is a valid BEP20 (Ethereum-format) address"""
    if not address or not address.startswith("0x"):
        return False
    if len(address) != 42:  # 0x + 40 hex chars
        return False
    try:
        int(address[2:], 16)  # Check if it's valid hex
        return True
    except ValueError:
        return False

async def change_withdrawal_address_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Same logic as set_withdrawal_address_step
    return await set_withdrawal_address_step(update, context)

async def process_withdrawal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    amount_str = update.message.text.strip().lower()

    # Get selected withdrawal coin
    coin = context.user_data.get('withdrawal_coin', get_active_currency(user.id))
    wallet = ensure_wallet_dict(user.id)
    crypto_balance = wallet.get(coin, 0.0)
    price = LIVE_PRICES.get(coin, 1.0)
    balance_usd = crypto_balance * price

    try:
        if amount_str == 'all':
            amount_usd = balance_usd
        else:
            amount_usd = float(amount_str)
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a valid number or 'all'.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back_to_main")]])
        )
        return WITHDRAWAL_AMOUNT

    if amount_usd <= 0:
        await update.message.reply_text(
            "❌ Amount must be greater than 0.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back_to_main")]])
        )
        return WITHDRAWAL_AMOUNT

    if amount_usd > balance_usd:
        formatted = format_crypto_amount(crypto_balance, coin)
        await update.message.reply_text(
            f"{pe('cross')} Insufficient {coin} balance.\n"
            f"Your {coin} balance: {formatted} {coin} (${balance_usd:,.2f})",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back_to_main")]])
        )
        return WITHDRAWAL_AMOUNT

    # Check withdrawal limits (new security feature)
    is_allowed, limit_error = check_withdrawal_limit(user.id, amount_usd)
    if not is_allowed:
        await update.message.reply_text(
            f"{pe('cross')} <b>Withdrawal Limit Exceeded</b>\n\n{limit_error}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back_to_main")]])
        )
        return WITHDRAWAL_AMOUNT

    # Check wager requirements
    total_wager_needed, breakdown = calculate_required_wager(user.id)
    if total_wager_needed > 0:
        rejection_msg = (
            f"{pe('cross')} <b>Withdrawal Requirements Not Met</b>\n\n"
            f"Before you can withdraw, you must wager the following amounts on casino games:\n\n"
        )

        if breakdown["unwagered_tips"] > 0:
            rejection_msg += (
                f"{pe('withdraw')} <b>Tips Received:</b> ${breakdown['unwagered_tips']:,.2f}\n"
                f"   Required wager: ${breakdown['unwagered_tips']:,.2f} (1x)\n\n"
            )

        if breakdown["unwagered_deposit"] > 0:
            rejection_msg += (
                f"{pe('money')} <b>Deposits:</b> ${breakdown['unwagered_deposit']:,.2f}\n"
                f"   Required wager: ${breakdown['deposit_wager_needed']:,.2f} (2x)\n\n"
            )

        rejection_msg += (
            f"{pe('chart')} <b>Total Wager Needed:</b> ${total_wager_needed:,.2f}\n\n"
            f"<i>Play any casino game to meet these requirements.</i>"
        )

        await update.message.reply_text(
            rejection_msg,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Play Games", callback_data="main_games")]])
        )
        return ConversationHandler.END

    # Calculate crypto amount
    crypto_amount = amount_usd / price
    formatted_crypto = format_crypto_amount(crypto_amount, coin)

    # Generate unique withdrawal ID
    withdrawal_id = generate_unique_id("WD")
    withdrawal_address = user_stats[user.id].get("withdrawal_address")

    # Create withdrawal request
    withdrawal_requests[withdrawal_id] = {
        "id": withdrawal_id,
        "user_id": user.id,
        "username": user.username or f"User_{user.id}",
        "amount_usd": amount_usd,
        "crypto_amount": crypto_amount,
        "coin": coin,
        "withdrawal_address": withdrawal_address,
        "status": "pending",
        "timestamp": str(datetime.now(timezone.utc)),
        "txid": None
    }

    # Deduct from user's specific coin wallet (ATOMIC - prevents double-spend race)
    async with _get_withdrawal_lock(user.id):
        try:
            deducted_amount, deducted_coin = await deduct_wallet_safe(user.id, amount_usd, coin)
        except ValueError as e:
            if "INSUFFICIENT_FUNDS" in str(e):
                await update.message.reply_text(
                    f"{pe('cross')} <b>Insufficient Funds</b>\n\n"
                    f"You do not have enough {coin} balance to withdraw ${amount_usd:.2f}.\n"
                    f"Your current {coin} balance is insufficient for this withdrawal.",
                    parse_mode=ParseMode.HTML
                )
                return ConversationHandler.END
            raise
    save_user_data(user.id)

    # Notify user
    await update.message.reply_text(
        f"{pe('check')} <b>Withdrawal Request Submitted</b>\n\n"
        f"<b>Request ID:</b> <code>{withdrawal_id}</code>\n"
        f"<b>USD Value:</b> ${amount_usd:.2f}\n"
        f"<b>Coin:</b> {coin}\n"
        f"<b>Crypto Amount:</b> {formatted_crypto} {coin}\n"
        f"<b>Address:</b> <code>{withdrawal_address}</code>\n\n"
        f"Your withdrawal request is currently pending review by the administrator.\n"
        f"You will be notified once it's processed.",
        parse_mode=ParseMode.HTML
    )

    # Forward to owner with both USD and crypto amounts
    try:
        await context.bot.send_message(
            chat_id=BOT_OWNER_ID,
            text=(
                f"📤 <b>Withdrawal Request</b>\n\n"
                f"<b>Request ID:</b> <code>{withdrawal_id}</code>\n"
                f"<b>User ID:</b> {user.id}\n"
                f"<b>User:</b> @{user.username or user.id}\n"
                f"<b>USD Value:</b> ${amount_usd:.2f}\n"
                f"<b>Coin:</b> {coin}\n"
                f"<b>Crypto Amount:</b> {formatted_crypto} {coin}\n"
                f"<b>Address:</b> <code>{withdrawal_address}</code>\n"
                f"<b>Status:</b> Pending"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Approve", callback_data=f"withdrawal_approve_{withdrawal_id}"),
                 InlineKeyboardButton("Cancel", callback_data=f"withdrawal_cancel_{withdrawal_id}")]
            ])
        )
    except Exception as e:
        logging.error(f"Failed to notify owner about withdrawal {withdrawal_id}: {e}")

    # Clear user_data to prevent capturing subsequent inputs
    context.user_data.clear()
    return ConversationHandler.END

async def recover_token_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = update.message.text.strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    rec_data = recovery_data.get(token_hash)
    if not rec_data:
        await update.message.reply_text(
            "Invalid token. Please try again or contact support.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_recovery")]])
        )
        return RECOVER_ASK_TOKEN

    if rec_data.get('lock_expiry') and rec_data['lock_expiry'] > datetime.now(timezone.utc):
        time_left = rec_data['lock_expiry'] - datetime.now(timezone.utc)
        await update.message.reply_text(f"This token is locked due to too many failed attempts. Please try again in {time_left.seconds // 60} minutes.")
        return ConversationHandler.END

    # --- SUCCESSFUL RECOVERY (NO PIN REQUIRED) ---
    old_user_id = rec_data['user_id']
    new_user = update.effective_user

    if old_user_id not in user_stats:
        await update.message.reply_text("Could not find the original account data. Please contact support.")
        context.user_data.clear()
        return ConversationHandler.END

    # Transfer data
    await ensure_user_in_wallets(new_user.id, new_user.username, context=context)
    user_stats[new_user.id] = user_stats[old_user_id]
    user_wallets[new_user.id] = user_wallets.get(old_user_id, {"USDT": 0.0})

    user_stats[new_user.id]['userinfo']['user_id'] = new_user.id
    user_stats[new_user.id]['userinfo']['username'] = new_user.username
    user_stats[new_user.id]['userinfo']['recovered_from'] = old_user_id
    user_stats[new_user.id]['userinfo']['recovered_at'] = str(datetime.now(timezone.utc))

    # Transfer active games
    active_games_transferred = 0
    for game in game_sessions.values():
        if game.get("status") == "active" and game.get("user_id") == old_user_id:
            game["user_id"] = new_user.id
            active_games_transferred += 1

    # Clean up old user data
    if old_user_id in user_stats: del user_stats[old_user_id]
    if old_user_id in user_wallets: del user_wallets[old_user_id]
    old_username = username_to_userid.pop(normalize_username(rec_data.get("username", "")), None)

    if os.path.exists(os.path.join(DATA_DIR, f"{old_user_id}.json")):
        os.remove(os.path.join(DATA_DIR, f"{old_user_id}.json"))

    # Clean up recovery token
    del recovery_data[token_hash]
    if os.path.exists(os.path.join(RECOVERY_DIR, f"{token_hash}.json")):
        os.remove(os.path.join(RECOVERY_DIR, f"{token_hash}.json"))

    save_user_data(new_user.id)

    await update.message.reply_text(
        f"{pe('check')} <b>Recovery Successful!</b>\n\n"
        f"Welcome back, {new_user.mention_html()}! Your data and balance of ${get_total_balance_usd(new_user.id):,.2f} have been restored. "
        f"{active_games_transferred} active games were transferred to this account. Use /active to see them.",
        parse_mode=ParseMode.HTML
    )
    context.user_data.clear()
    return ConversationHandler.END

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('predict', predict_command, block=False))

