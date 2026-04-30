"""Auto-split from bot.py — plugins.referral."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

async def process_referral_commission(user_id, amount, commission_type):
    if user_id not in user_stats or not user_stats[user_id].get('referral', {}).get('referrer_id'):
        return

    referrer_id = user_stats[user_id]['referral']['referrer_id']
    if referrer_id not in user_stats:
        return

    if commission_type == 'bet':
        # NEW: 0.2% wager commission in active currency
        active_currency = get_active_currency(user_id)
        price = LIVE_PRICES.get(active_currency, 1.0)
        crypto_amount = amount / price  # Convert USD bet to crypto
        commission_crypto = crypto_amount * 0.002  # 0.2% in active crypto

        # Ensure commissions dict exists
        if 'commissions' not in user_stats[referrer_id]['referral']:
            user_stats[referrer_id]['referral']['commissions'] = {}

        # Add commission to referrer's balance
        user_stats[referrer_id]['referral']['commissions'][active_currency] = (
            user_stats[referrer_id]['referral']['commissions'].get(active_currency, 0.0) + commission_crypto
        )

        # Also update the old commission_earned field for backward compatibility
        commission_usd = commission_crypto * price
        user_stats[referrer_id]['referral']['commission_earned'] = (
            user_stats[referrer_id]['referral'].get('commission_earned', 0.0) + commission_usd
        )

        save_user_data(referrer_id)
        logging.info(f"Awarded {commission_crypto} {active_currency} wager commission to referrer {referrer_id} from user {user_id}'s {commission_type}.")
    else:
        return

@check_banned
@check_maintenance
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    logging.info(f"Referral command called by user {user.id}")
    
    try:
        await ensure_user_in_wallets(user.id, user.username, context=context)

        bot_username = await get_bot_username(context)
        referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"

        if user.id not in user_stats:
            logging.error(f"User {user.id} not in user_stats after ensure_user_in_wallets")
            await update.message.reply_text("Error: User data not loaded. Please try again in a moment.")
            return

        stats = user_stats[user.id]
        logging.info(f"User {user.id} stats keys: {list(stats.keys())[:10]}")
        ref_info = stats.get('referral', {})
        logging.info(f"User {user.id} referral info: {ref_info}")

        # Ensure code exists (for backward compatibility)
        if 'code' not in ref_info:
            ref_info['code'] = generate_unique_referral_code()
            referral_codes[ref_info['code']] = user.id
            save_user_data(user.id)

        # Get commission details per currency
        commissions = ref_info.get('commissions', {})
        commission_text = ""
        if commissions:
            commission_text = f"\n\n{pe('gem')} <b>Accumulated Commissions:</b>\n"
            for currency, amount in commissions.items():
                if amount > 0:
                    symbol = CRYPTO_SYMBOLS.get(currency, "")
                    formatted = format_crypto_amount(amount, currency)
                    usd_value = amount * LIVE_PRICES.get(currency, 1.0)
                    commission_text += f"  {symbol} {formatted} {currency} (${usd_value:.2f})\n"

        msg = (f"{pe('push')} <b>Your Referral Dashboard</b> 🤝\n\n"
               f"Share your unique link or code to earn commissions!\n\n"
               f"{pe('link')} <b>Your Link:</b>\n<code>{referral_link}</code>\n\n"
               f"🎫 <b>Your Code:</b> <code>{ref_info.get('code', 'N/A')}</code>\n"
               f"{pe('bulb')} Use <code>/setcode YOURCODE</code> to customize it\n\n"
               f"👥 <b>Total Referrals:</b> {len(ref_info.get('referred_users', []))}\n"
               f"{pe('money')} <b>Total Commission Earned:</b> ${ref_info.get('commission_earned', 0.0):.4f}"
               f"{commission_text}\n\n"
               f"<b>Commission Rates:</b>\n"
               f"- <b>0.5%</b> of deposits (in native crypto)\n"
               f"- <b>0.2%</b> of wagers (in active currency)")

    except Exception as e:
        logging.error(f"Error in referral_command for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text(f"An error occurred: {str(e)}")
        return

    # Add buttons for transferring commissions and viewing referrals
    keyboard = []
    if commissions and any(v > 0 for v in commissions.values()):
        keyboard.append([apply_button_style(InlineKeyboardButton("Transfer to Balance", callback_data=f"ref_transfer_{user.id}"), 'success', peb('deposit'))])

    if len(ref_info.get('referred_users', [])) > 0:
        keyboard.append([apply_button_style(InlineKeyboardButton("Check My Referrals", callback_data=f"ref_check_{user.id}"), 'primary', peb('user'))])

    keyboard.append([InlineKeyboardButton("Back to More", callback_data="main_more")])
    reply_markup = create_styled_keyboard(keyboard) if from_callback else (create_styled_keyboard(keyboard) if keyboard else None)

    if from_callback:
        await safe_edit_message(update.callback_query, msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
    else:
        sent_message = await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
        # Set ownership when sending with keyboard
        if reply_markup:
            set_menu_owner(sent_message, user.id)

@check_banned
@check_maintenance
async def setcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Usage: <code>/setcode YOUR_CODE</code>\n\n"
            "Requirements:\n"
            "• 4-12 alphanumeric characters\n"
            "• No special characters or spaces\n\n"
            "Example: <code>/setcode MYCODE123</code>",
            parse_mode=ParseMode.HTML
        )
        return

    new_code = context.args[0].upper()

    # Validate code
    if not new_code.isalnum():
        await update.message.reply_text(f"{pe('cross')} Code must be alphanumeric (letters and numbers only).")
        return

    if len(new_code) < 4 or len(new_code) > 12:
        await update.message.reply_text(f"{pe('cross')} Code must be between 4 and 12 characters long.")
        return

    # Check if code already exists
    if new_code in referral_codes and referral_codes[new_code] != user.id:
        await update.message.reply_text(f"{pe('cross')} This code is already taken. Please choose a different one.")
        return

    # Update user's code
    stats = user_stats[user.id]
    old_code = stats['referral'].get('code')

    # Remove old code from global mapping
    if old_code and old_code in referral_codes:
        del referral_codes[old_code]

    # Add new code
    stats['referral']['code'] = new_code
    referral_codes[new_code] = user.id
    save_user_data(user.id)
    save_bot_state()

    bot_username = await get_bot_username(context)
    await update.message.reply_text(
        f"{pe('check')} Your referral code has been updated!\n\n"
        f"🎫 <b>Your New Code:</b> <code>{new_code}</code>\n\n"
        f"Share this link:\n<code>https://t.me/{bot_username}?start=ref_{user.id}</code>\n\n"
        f"Or tell users to use: <code>/code {new_code}</code>",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Usage: <code>/code REFERRAL_CODE</code>\n\n"
            "Use this to set your referrer if you forgot to use their link.\n\n"
            "Example: <code>/code ABC123</code>",
            parse_mode=ParseMode.HTML
        )
        return

    code = context.args[0].upper()

    # Check if user already has a referrer
    stats = user_stats[user.id]
    if stats['referral'].get('referrer_id'):
        await update.message.reply_text(f"{pe('cross')} You already have a referrer set. You cannot change it.")
        return

    # Look up the code
    if code not in referral_codes:
        await update.message.reply_text(f"{pe('cross')} Invalid referral code. Please check and try again.")
        return

    referrer_id = referral_codes[code]

    # Can't refer yourself
    if referrer_id == user.id:
        await update.message.reply_text(f"{pe('cross')} You cannot use your own referral code.")
        return

    # Set the referrer
    stats['referral']['referrer_id'] = referrer_id

    # Add to referrer's referred_users list
    await ensure_user_in_wallets(referrer_id, context=context)
    if 'commissions' not in user_stats[referrer_id]['referral']:
        user_stats[referrer_id]['referral']['commissions'] = {}
    user_stats[referrer_id]['referral']['referred_users'].append(user.id)

    save_user_data(user.id)
    save_user_data(referrer_id)

    await update.message.reply_text(
        f"{pe('check')} Referral code applied successfully!\n\n"
        f"Your referrer will now earn commissions on your deposits and wagers."
    )

    # Notify referrer
    try:
        await context.bot.send_message(
            chat_id=referrer_id,
            text=f"{pe('win')} New referral! User {user.mention_html()} has used your code. You will now earn commissions on their deposits and wagers.",
            parse_mode=ParseMode.HTML
        )
    except (BadRequest, Forbidden):
        pass

@check_banned
@check_maintenance
async def referral_transfer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transfer accumulated referral commissions to main balance"""
    query = update.callback_query
    user_id = int(query.data.split('_')[-1])

    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()
    await ensure_user_in_wallets(user_id, query.from_user.username, context=context)

    stats = user_stats[user_id]
    commissions = stats['referral'].get('commissions', {})

    if not commissions or not any(v > 0 for v in commissions.values()):
        await safe_edit_message(
            query,
            "❌ No commissions to transfer.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Referral", callback_data="main_referral")]])
        )
        return

    # Transfer each currency to user's wallet
    transfer_summary = []
    for currency, amount in list(commissions.items()):
        if amount > 0:
            credit_wallet_crypto(user_id, amount, currency)
            symbol = CRYPTO_SYMBOLS.get(currency, "")
            formatted = format_crypto_amount(amount, currency)
            usd_value = amount * LIVE_PRICES.get(currency, 1.0)
            transfer_summary.append(f"  {symbol} {formatted} {currency} (${usd_value:.2f})")
            commissions[currency] = 0.0

    save_user_data(user_id)

    msg = (
        "✅ <b>Commission Transfer Complete!</b>\n\n"
        "Transferred to your balance:\n" + "\n".join(transfer_summary) + "\n\n"
        "Your commissions have been reset to 0."
    )

    await safe_edit_message(
        query,
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Referral", callback_data="main_referral")]])
    )

@check_banned
@check_maintenance
async def referral_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of referrals with their stats"""
    query = update.callback_query
    user_id = int(query.data.split('_')[-1])

    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()
    await ensure_user_in_wallets(user_id, query.from_user.username, context=context)

    stats = user_stats[user_id]
    referred_users = stats['referral'].get('referred_users', [])

    if not referred_users:
        await safe_edit_message(
            query,
            "❌ You haven't referred anyone yet.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Referral", callback_data="main_referral")]])
        )
        return

    msg = "👥 <b>Your Referrals</b>\n\n"

    for ref_user_id in referred_users:
        if ref_user_id in user_stats:
            ref_stats = user_stats[ref_user_id]
            total_wagered = ref_stats.get('bets', {}).get('amount', 0.0)
            total_deposits = sum(d.get('amount', 0.0) for d in ref_stats.get('deposits', []))
            msg += f"• User {ref_user_id}\n"
            msg += f"  Wagered: ${total_wagered:,.2f} | Deposits: ${total_deposits:,.2f}\n\n"

    msg += f"Total: {len(referred_users)} referrals"

    await safe_edit_message(
        query,
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Referral", callback_data="main_referral")]])
    )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('referral', referral_command, block=False))
    app.add_handler(CommandHandler('setcode', setcode_command, block=False))
    app.add_handler(CommandHandler('code', code_command, block=False))
    app.add_handler(CallbackQueryHandler(referral_transfer_callback, pattern='^ref_transfer_', block=False))
    app.add_handler(CallbackQueryHandler(referral_check_callback, pattern='^ref_check_', block=False))

