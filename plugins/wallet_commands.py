"""Auto-split from bot.py — plugins.wallet_commands."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def _build_rain_message(rain, participants):
    """Build the rain announcement message text."""
    creator = f"@{rain['creator_username']}" if rain['creator_username'] else f"User {rain['creator_id']}"
    count = len(participants)
    try:
        end_dt = datetime.fromisoformat(rain['end_time'])
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        remaining = max(0, int((end_dt - datetime.now(timezone.utc)).total_seconds()))
    except Exception:
        remaining = 0
    per_person = rain['amount'] / count if count > 0 else rain['amount']
    lines = [
        f"🌧️ <b>Rain Event!</b>",
        f"",
        f"<b>{creator}</b> is raining <b>{rain['amount']:.4f} {rain['currency']}</b> on the group!",
        f"",
        f"⏳ Time remaining: <b>{remaining // 60}m {remaining % 60}s</b>",
        f"👥 Participants: <b>{count}</b>",
        f"{pe('money')} Per person (current): <b>{per_person:.6f} {rain['currency']}</b>",
        f"",
        f"Press the button below to join the rain!",
    ]
    return "\n".join(lines)

@check_banned
@check_maintenance
async def rain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a group rain. Usage: /rain <amount> <currency>"""
    logging.info(f"[RAIN] Command triggered by user {update.effective_user.id}")
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    args = update.message.text.strip().split()
    logging.info(f"[RAIN] Args: {args}")
    if len(args) < 2:
        disp_currency = get_display_currency(user.id)
        disp_sym = CURRENCY_SYMBOLS.get(disp_currency, "$")
        await update.message.reply_text(
            "Usage: /rain <b>&lt;amount&gt;</b> [<b>&lt;currency&gt;</b>]\n\n"
            "Examples:\n"
            f"• <code>/rain 100</code> — Rain {disp_sym}100 (your display currency)\n"
            "• <code>/rain 5 USDT</code> — Rain 5 USDT\n"
            "• <code>/rain 0.01 ETH</code> — Rain 0.01 ETH",
            parse_mode=ParseMode.HTML
        )
        return

    # If only an amount is given, interpret it as the user's display
    # currency (parity with bets, tips and leaderboards) and rain it
    # in USDT — the bot's most stable settlement coin.
    if len(args) == 2:
        try:
            disp_currency = get_display_currency(user.id)
            amount_disp = float(args[1])
            if amount_disp <= 0:
                raise ValueError
            amount_usd = convert_display_to_usd(amount_disp, disp_currency)
            usdt_price = LIVE_PRICES.get("USDT", 1.0) or 1.0
            amount = amount_usd / usdt_price
            currency = "USDT"
        except ValueError:
            await update.message.reply_text(f"{pe('cross')} Invalid amount. Please enter a positive number.", parse_mode=ParseMode.HTML)
            return
        logging.info(f"[RAIN] Amount (display→USDT): {amount_disp} {disp_currency} → {amount} USDT")
    else:
        # Explicit currency: keep classic behaviour (raw crypto amount).
        try:
            amount = float(args[1])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(f"{pe('cross')} Invalid amount. Please enter a positive number.", parse_mode=ParseMode.HTML)
            return
        currency = args[2].upper()
        logging.info(f"[RAIN] Amount: {amount}, Currency: {currency}")

    # Validate currency exists in wallet
    wallet = ensure_wallet_dict(user.id)
    if currency not in wallet and currency not in LIVE_PRICES:
        await update.message.reply_text(f"{pe('cross')} Unknown currency: <b>{currency}</b>. Use USDT, ETH, BNB, SOL, etc.", parse_mode=ParseMode.HTML)
        return

    # Check balance
    price = LIVE_PRICES.get(currency, 1.0)
    amount_usd = amount * price
    available_crypto = wallet.get(currency, 0.0)
    logging.info(f"[RAIN] Balance check: available={available_crypto}, needed={amount}")

    if available_crypto < amount:
        await update.message.reply_text(
            f"{pe('cross')} Insufficient balance.\n"
            f"You need <b>{amount:.6f} {currency}</b> but have <b>{available_crypto:.6f} {currency}</b>.",
            parse_mode=ParseMode.HTML
        )
        return

    if amount_usd < RAIN_MIN_AMOUNT:
        await update.message.reply_text(
            f"{pe('cross')} Rain amount too small. Minimum is <b>${RAIN_MIN_AMOUNT:.2f}</b> (≈ {RAIN_MIN_AMOUNT/price:.6f} {currency}).",
            parse_mode=ParseMode.HTML
        )
        return

    # Deduct immediately to lock funds
    logging.info(f"[RAIN] Deducting {amount} {currency} from user {user.id}")
    credit_wallet_crypto(user.id, -amount, currency)
    save_user_data(user.id)

    # Create rain in DB (async to avoid blocking event loop)
    rain_id = str(uuid.uuid4())
    end_time = (datetime.now(timezone.utc) + timedelta(seconds=RAIN_DURATION_SECONDS)).isoformat()
    db = global_deposit_db

    try:
        logging.info(f"[RAIN] Creating rain in DB: {rain_id}")
        created = await db.async_create_rain(
            rain_id=rain_id,
            chat_id=update.effective_chat.id,
            creator_id=user.id,
            creator_username=user.username,
            amount=amount,
            currency=currency,
            end_time=end_time
        )
        logging.info(f"[RAIN] async_create_rain returned: {created}")
        if not created:
            # Refund on DB failure
            credit_wallet_crypto(user.id, amount, currency)
            save_user_data(user.id)
            await update.message.reply_text(f"{pe('cross')} Failed to create rain. Please try again in a moment.")
            return

        # Build initial rain message
        logging.info(f"[RAIN] Fetching rain data for {rain_id}")
        rain = await db.async_get_rain(rain_id)
        logging.info(f"[RAIN] async_get_rain returned: {rain}")
        if not rain:
            credit_wallet_crypto(user.id, amount, currency)
            save_user_data(user.id)
            await update.message.reply_text(f"{pe('cross')} Failed to create rain. Please try again in a moment.")
            return

        text = _build_rain_message(rain, [])
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Join Rain", callback_data=f"join_rain_{rain_id}")
        ]])
        logging.info(f"[RAIN] Sending rain message to chat {update.effective_chat.id}")
        sent = await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        logging.info(f"[RAIN] Message sent: {sent.message_id}")

        # Store message_id for later updates (async)
        await db.async_set_rain_message_id(rain_id, sent.message_id)

        # Schedule job to finalize rain after duration
        if context.job_queue:
            context.job_queue.run_once(
                finalize_rain_job,
                when=RAIN_DURATION_SECONDS,
                data={'rain_id': rain_id, 'chat_id': update.effective_chat.id, 'message_id': sent.message_id},
                name=f"rain_{rain_id}"
            )
        logging.info(f"Rain {rain_id} started by {user.id} for {amount} {currency} in chat {update.effective_chat.id}")
    except Exception as e:
        logging.error(f"Rain command error: {e}")
        # Refund on unexpected error
        credit_wallet_crypto(user.id, amount, currency)
        save_user_data(user.id)
        await update.message.reply_text(f"{pe('cross')} An error occurred while creating the rain. Your balance has been refunded. Please try again.")

@check_banned
@check_maintenance
async def join_rain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a user clicking the Join Rain button."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    rain_id_str = query.data.replace("join_rain_", "", 1)

    db = global_deposit_db
    rain = await db.async_get_rain(rain_id_str)

    if not rain:
        await query.answer(f"{pe('cross')} This rain no longer exists.", show_alert=True)
        return

    if rain['status'] != 'active':
        await query.answer(f"{pe('rain')} This rain has already ended!", show_alert=True)
        return

    # Check time
    try:
        end_dt = datetime.fromisoformat(rain['end_time'])
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= end_dt:
            await query.answer(f"{pe('rain')} This rain has already ended!", show_alert=True)
            return
    except Exception:
        pass

    # Prevent creator from joining their own rain
    if user.id == rain['creator_id']:
        await query.answer(f"{pe('umbrella')} You can't join your own rain!", show_alert=True)
        return

    # Ensure user is registered
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Add participant (returns False if already joined) - async
    added = await db.async_add_rain_participant(rain_id_str, user.id, user.username)
    if not added:
        await query.answer(f"{pe('check')} You've already joined this rain!", show_alert=True)
        return

    await query.answer(f"{pe('rain')} You joined the rain!")

    # Update the announcement message
    participants = await db.async_get_rain_participants(rain_id_str)
    text = _build_rain_message(rain, participants)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"Join Rain ({len(participants)})", callback_data=f"join_rain_{rain_id_str}")
    ]])
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        pass  # Message may have been edited too recently; ignore

async def finalize_rain_job(context: ContextTypes.DEFAULT_TYPE):
    """Job that fires when the rain window closes and distributes funds."""
    data = context.job.data
    rain_id = data['rain_id']
    chat_id = data['chat_id']
    message_id = data['message_id']

    db = global_deposit_db
    rain = await db.async_get_rain(rain_id)

    if not rain or rain['status'] != 'active':
        return  # Already completed or missing

    await db.async_complete_rain(rain_id)
    participants = await db.async_get_rain_participants(rain_id)
    amount = rain['amount']
    currency = rain['currency']
    creator_id = rain['creator_id']
    creator_username = rain['creator_username'] or f"User {creator_id}"

    if not participants:
        # No one joined — refund creator
        credit_wallet_crypto(creator_id, amount, currency)
        save_user_data(creator_id)
        text = (
            f"🌧️ <b>Rain Ended — No Participants</b>\n\n"
            f"Nobody joined {creator_username}'s rain.\n"
            f"<b>{amount:.6f} {currency}</b> has been refunded."
        )
    else:
        per_person = amount / len(participants)
        price = LIVE_PRICES.get(currency, 1.0)
        per_person_usd = per_person * price
        recipient_lines = []

        for uid, uname in participants:
            await ensure_user_in_wallets_sync(uid, uname, context)
            credit_wallet_crypto(uid, per_person, currency)
            update_stats_on_rain_received(uid, per_person_usd)
            save_user_data(uid)
            recipient_lines.append(f"@{uname}" if uname else f"User {uid}")

        recipients_str = ", ".join(recipient_lines)
        creator_display = f"@{rain['creator_username']}" if rain['creator_username'] else creator_username
        text = (
            f"🌧️ <b>Rain Complete!</b>\n\n"
            f"<b>{creator_display}</b> rained <b>{amount:.6f} {currency}</b> on {len(participants)} user(s)!\n"
            f"{pe('money')} Each received: <b>{per_person:.6f} {currency}</b>\n\n"
            f"{pe('win')} Recipients: {recipients_str}"
        )

    # Edit the original rain message
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.warning(f"Could not edit rain message {message_id}: {e}")
        # Fall back to sending a new message
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e2:
            logging.error(f"Failed to send rain result message: {e2}")

@check_banned
@check_maintenance
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)
    user_currency = get_user_currency(user.id)
    formatted_balance = format_balance_with_locked(user.id, user_currency)

    # Get total wagers for display
    stats = user_stats.get(user.id, {})
    total_wagered = stats.get('bets', {}).get('amount', 0.0)
    formatted_wagers = format_currency(total_wagered, user_currency)

    is_group = update.effective_chat.type in ["group", "supergroup"]

    if is_group:
        # Group chat: simplified balance display with Deposit/Withdraw link buttons, NO template image
        bot_username = await get_bot_username(context)
        keyboard = [
            [
                apply_button_style(InlineKeyboardButton("Deposit", url=f"https://t.me/{bot_username}?start=deposit"), 'primary'),  # BLUE
                apply_button_style(InlineKeyboardButton("Withdraw", url=f"https://t.me/{bot_username}?start=withdraw"), 'success')  # GREEN
            ],
        ]

        # Group format: ONLY the user's display-currency balance.  We
        # intentionally drop the crypto wallet line — groups are public
        # and people don't want their wallet coin or balance leaking.
        balance_usd = get_active_balance_usd(user.id)
        disp = get_display_currency(user.id)
        display_str = format_for_user(
            user.id, balance_usd, compact=False,
            with_usdt_estimate=False,
        )
        cur_emoji = pe(CURRENCY_EMOJI_KEY.get(disp, 'dollar'))
        text = f"{cur_emoji} <b>Balance:</b> {display_str}"

        reply_markup = create_styled_keyboard(keyboard)

        sent_message = await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        set_menu_owner(sent_message, user.id)
        return

    # DM: original behavior
    keyboard = [
        [
            InlineKeyboardButton("Deposit", callback_data="main_deposit"),
            InlineKeyboardButton("Withdraw", callback_data="main_withdraw")
        ],
        [InlineKeyboardButton("View Full Wallet", callback_data="main_wallet")]
    ]

    text = f"{pe('money')} <b>Your Balance</b>\n\n{formatted_balance}"

    # Send dashboard image with balance text in caption (NEW FEATURE - Combined)
    dashboard_image = await generate_dashboard_image(user.id, context)
    if dashboard_image:
        try:
            await update.message.reply_photo(
                photo=dashboard_image,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logging.error(f"Error sending dashboard image: {e}")
            # Fallback to text only
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        # No image, send text only
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

@check_banned
@check_maintenance
async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    message_text = update.message.text.strip().split()
    target_user_id = None
    target_username = None

    # Parse tip amount in the sender's DISPLAY currency so /tip @x 500
    # means "500 of whatever currency I've chosen".
    display_currency = get_display_currency(user.id)
    disp_sym = CURRENCY_SYMBOLS.get(display_currency, "")

    raw_amount_str = None
    if update.message.reply_to_message and len(message_text) == 2:
        try:
            raw_amount_str = message_text[1]
            tip_amount_display = float(raw_amount_str)
            tip_amount_usd = convert_display_to_usd(tip_amount_display, display_currency)
            target_user_id = update.message.reply_to_message.from_user.id
            target_username = update.message.reply_to_message.from_user.username
        except (ValueError, IndexError):
             await update.message.reply_text("Usage (reply to a message): /tip amount")
             return
    elif len(message_text) == 3:
        try:
            target_username_str = normalize_username(message_text[1])
            raw_amount_str = message_text[2]
            tip_amount_display = float(raw_amount_str)
            tip_amount_usd = convert_display_to_usd(tip_amount_display, display_currency)
            target_user_id = username_to_userid.get(target_username_str)
            if not target_user_id:
                try:
                    chat = await context.bot.get_chat(target_username_str)
                    target_user_id = chat.id
                    target_username = chat.username
                except Exception:
                    await update.message.reply_text(f"User {target_username_str} not found.")
                    return
            else:
                target_username = user_stats[target_user_id]['userinfo']['username']
        except (ValueError, IndexError):
            await update.message.reply_text("Usage: /tip @username amount")
            return
    else:
        await update.message.reply_text("Usage: /tip @username amount OR reply to a message with /tip amount")
        return

    if not target_user_id:
        await update.message.reply_text("Could not find the target user.")
        return

    is_owner = is_admin(user.id)
    if user.id == target_user_id and not is_owner:
        await update.message.reply_text("You cannot tip yourself.")
        return
    if tip_amount_usd <= 0:
        await update.message.reply_text("Tip amount must be positive.")
        return

    # Calculate crypto equivalent for confirmation
    active_coin = get_active_currency(user.id)
    price = LIVE_PRICES.get(active_coin, 1.0)
    crypto_amount = tip_amount_usd / price
    formatted_crypto = format_crypto_amount(crypto_amount, active_coin)
    tipped_user_mention = f"@{target_username}" if target_username else f"User (ID: {target_user_id})"

    # Display the tip in the sender's currency, plus a USDT estimate so
    # the receiver can eyeball the value regardless of their own setting.
    sender_display_str = format_display_amount(tip_amount_usd, display_currency)
    usdt_estimate_str = format_display_amount(tip_amount_usd, "USDT")

    # Store tip data for confirmation
    tip_id = f"{user.id}_{target_user_id}_{int(datetime.now(timezone.utc).timestamp())}"
    context.user_data['pending_tip'] = {
        'tip_id': tip_id,
        'sender_id': user.id,
        'target_user_id': target_user_id,
        'target_username': target_username,
        'tip_amount_usd': tip_amount_usd,
        'tip_amount_display': tip_amount_display,
        'display_currency': display_currency,
        'crypto_amount': crypto_amount,
        'coin': active_coin,
        'is_owner': is_owner,
    }

    # Colorful premium-emoji confirm (green) / cancel (red) buttons.
    keyboard = [[
        apply_button_style(
            InlineKeyboardButton(f"✅ Confirm", callback_data=f"confirm_tip_{tip_id}"),
            'success',
            peb('check'),
        ),
        apply_button_style(
            InlineKeyboardButton(f"❌ Cancel", callback_data=f"cancel_tip_{tip_id}"),
            'danger',
            peb('cross'),
        ),
    ]]
    await update.message.reply_text(
        f"{pe('warning')} <b>Confirm Tip</b>\n\n"
        f"{pe(CURRENCY_EMOJI_KEY.get(display_currency, 'balance'))} "
        f"Sending: <b>{sender_display_str}</b> (~ {usdt_estimate_str} USDT)\n"
        f"{pe('gem')} Wallet debit: <b>{formatted_crypto} {active_coin}</b>\n"
        f"{pe('user')} To: {tipped_user_mention}\n\n"
        f"Please confirm or cancel.",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard),
    )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('rain', rain_command, block=False))
    app.add_handler(CommandHandler('tip', tip_command, block=False))
    app.add_handler(CommandHandler(['bal', 'balance'], balance_command, block=False))
    app.add_handler(CallbackQueryHandler(join_rain_callback, pattern='^join_rain_', block=False))

