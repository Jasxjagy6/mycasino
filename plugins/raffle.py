"""Auto-split from bot.py — plugins.raffle."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

@check_banned
@check_maintenance
async def raffle_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /raffle command - show type selection"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    keyboard = [
        [apply_button_style(InlineKeyboardButton("Referrals Only", callback_data="raffle_type_referrals"), 'primary', peb('diamond'))],
        [apply_button_style(InlineKeyboardButton("All Players", callback_data="raffle_type_all"), 'success', peb('green_circle'))],
        [apply_button_style(InlineKeyboardButton("Cancel", callback_data="raffle_cancel"), 'danger', peb('cross'))]
    ]

    await safe_edit_message(
        query,
        "🎰 <b>Create a Raffle</b>\n\n"
        "Choose the raffle type:\n\n"
        "🔵 <b>Referrals Only:</b> Only your referrals can participate\n"
        "🟢 <b>All Players:</b> Anyone can participate by wagering",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard)
    )
    return ConversationHandler.END

@check_banned
@check_maintenance
async def raffle_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle raffle type selection"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    raffle_type = query.data.split('_')[-1]  # 'referrals' or 'all'
    context.user_data['raffle_type'] = raffle_type
    context.user_data['raffle_creator'] = user.id

    await safe_edit_message(
        query,
        f"{pe('casino')} <b>Create Raffle - {raffle_type.title()}</b>\n\n"
        f"Enter the <b>prize amount in USD</b>:\n\n"
        f"Your balance: ${get_active_balance_usd(user.id):.2f}\n\n"
        f"The amount will be deducted from your balance immediately.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="raffle_cancel")]])
    )
    return RAFFLE_PRIZE_AMOUNT

async def raffle_prize_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect prize amount"""
    user = update.effective_user
    try:
        prize_usd = float(update.message.text)
        if prize_usd <= 0:
            await update.message.reply_text(f"{pe('cross')} Prize must be positive. Try again:")
            return RAFFLE_PRIZE_AMOUNT

        # Deduct prize from balance atomically — the balance check is
        # rolled into deduct_wallet_safe so we cannot race a concurrent
        # bet on the same wallet (single-process or multi-worker).
        try:
            await deduct_wallet_safe(user.id, prize_usd)
        except ValueError:
            balance = get_active_balance_usd(user.id)
            await update.message.reply_text(
                f"{pe('cross')} Insufficient balance. You have ${balance:.2f}. Try again:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="raffle_cancel")]])
            )
            return RAFFLE_PRIZE_AMOUNT
        save_user_data(user.id)

        context.user_data['raffle_prize_usd'] = prize_usd

        await update.message.reply_text(
            f"{pe('check')} Prize set to ${prize_usd:.2f} (deducted from balance)\n\n"
            f"Enter the <b>wager amount needed for 1 ticket</b> (in USD):\n\n"
            f"Example: 10 (users need to wager $10 to earn 1 ticket)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="raffle_cancel")]])
        )
        return RAFFLE_TICKET_COST
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid amount. Enter a number:")
        return RAFFLE_PRIZE_AMOUNT

async def raffle_ticket_cost_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect ticket cost"""
    try:
        ticket_cost = float(update.message.text)
        if ticket_cost <= 0:
            await update.message.reply_text(f"{pe('cross')} Ticket cost must be positive. Try again:")
            return RAFFLE_TICKET_COST

        context.user_data['raffle_ticket_cost'] = ticket_cost

        await update.message.reply_text(
            f"{pe('check')} Ticket cost set to ${ticket_cost:.2f}\n\n"
            f"Enter the <b>raffle duration in days</b> (1-30):\n\n"
            f"Example: 7 (raffle runs for 7 days)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="raffle_cancel")]])
        )
        return RAFFLE_DURATION
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid amount. Enter a number:")
        return RAFFLE_TICKET_COST

async def raffle_duration_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect raffle duration"""
    try:
        duration_days = int(update.message.text)
        if duration_days <= 0 or duration_days > 30:
            await update.message.reply_text(f"{pe('cross')} Duration must be between 1 and 30 days. Try again:")
            return RAFFLE_DURATION

        context.user_data['raffle_duration_days'] = duration_days

        await update.message.reply_text(
            f"{pe('check')} Duration set to {duration_days} days\n\n"
            f"Enter the <b>number of winners</b> (1-100):\n\n"
            f"Example: 5 (5 winners will be selected)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="raffle_cancel")]])
        )
        return RAFFLE_NUM_WINNERS
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid number. Enter an integer:")
        return RAFFLE_DURATION

async def raffle_num_winners_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect number of winners and create raffle"""
    user = update.effective_user
    try:
        num_winners = int(update.message.text)
        if num_winners <= 0 or num_winners > 100:
            await update.message.reply_text(f"{pe('cross')} Number of winners must be between 1 and 100. Try again:")
            return RAFFLE_NUM_WINNERS

        # Create the raffle
        raffle_id = generate_unique_id("RAFFLE")
        end_time = datetime.now(timezone.utc) + timedelta(days=context.user_data['raffle_duration_days'])

        active_raffles[raffle_id] = {
            "id": raffle_id,
            "creator": user.id,
            "type": context.user_data['raffle_type'],  # 'referrals' or 'all'
            "prize_usd": context.user_data['raffle_prize_usd'],
            "ticket_cost": context.user_data['raffle_ticket_cost'],
            "end_time": str(end_time),
            "total_winners": num_winners,
            "tickets": {},  # {user_id: ticket_count}
            "wager_tracker": {}  # {user_id: accumulated_wager}
        }
        save_bot_state()

        # Clear context data
        for key in ['raffle_type', 'raffle_creator', 'raffle_prize_usd', 'raffle_ticket_cost', 'raffle_duration_days']:
            context.user_data.pop(key, None)

        await update.message.reply_text(
            f"{pe('check')} <b>Raffle Created!</b>\n\n"
            f"{pe('casino')} <b>Raffle ID:</b> <code>{raffle_id}</code>\n"
            f"{pe('money')} <b>Prize Pool:</b> ${active_raffles[raffle_id]['prize_usd']:.2f}\n"
            f"🎫 <b>Ticket Cost:</b> ${active_raffles[raffle_id]['ticket_cost']:.2f} wagered\n"
            f"👥 <b>Type:</b> {active_raffles[raffle_id]['type'].title()}\n"
            f"{pe('trophy')} <b>Winners:</b> {num_winners}\n"
            f"⏰ <b>Ends:</b> {end_time.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Players will automatically earn tickets by wagering!\n"
            f"Use <code>/info {raffle_id}</code> to check progress.",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid number. Enter an integer:")
        return RAFFLE_NUM_WINNERS

@check_banned
@check_maintenance
async def raffle_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel raffle creation"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Refund prize if it was deducted
    if 'raffle_prize_usd' in context.user_data:
        prize = context.user_data['raffle_prize_usd']
        credit_wallet(user.id, prize)
        save_user_data(user.id)
        await safe_edit_message(query, f"{pe('cross')} Raffle creation cancelled. ${prize:.2f} refunded.", parse_mode=ParseMode.HTML)
    else:
        await safe_edit_message(query, "❌ Raffle creation cancelled.", parse_mode=ParseMode.HTML)

    # Clear context
    for key in ['raffle_type', 'raffle_creator', 'raffle_prize_usd', 'raffle_ticket_cost', 'raffle_duration_days']:
        context.user_data.pop(key, None)

    return ConversationHandler.END

@check_banned
@check_maintenance
async def raffle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start raffle creation flow"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    keyboard = [
        [apply_button_style(InlineKeyboardButton("Referrals Only", callback_data="raffle_type_referrals"), 'primary', peb('diamond'))],
        [apply_button_style(InlineKeyboardButton("All Players", callback_data="raffle_type_all"), 'success', peb('green_circle'))],
    ]

    sent_message = await update.message.reply_text(
        "🎰 <b>Create a Raffle</b>\n\n"
        "Choose the raffle type:\n\n"
        "🔵 <b>Referrals Only:</b> Only your referrals can participate\n"
        "🟢 <b>All Players:</b> Anyone can participate by wagering",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard)
    )
    set_menu_owner(sent_message, user.id)

@check_banned
@check_maintenance
async def raffles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show raffles dashboard"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    keyboard = [
        [apply_button_style(InlineKeyboardButton("My Raffles", callback_data=f"raffles_mine_{user.id}"), 'primary')],
        [apply_button_style(InlineKeyboardButton("Active Raffles", callback_data="raffles_active"), 'success', peb('star'))],
    ]

    sent_message = await update.message.reply_text(
        "🎰 <b>Raffle Dashboard</b>\n\n"
        "Select an option:",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard)
    )
    set_menu_owner(sent_message, user.id)

@check_banned
@check_maintenance
async def raffles_mine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's created raffles"""
    query = update.callback_query
    user_id = int(query.data.split('_')[-1])

    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    my_raffles = [r for r in active_raffles.values() if r['creator'] == user_id]

    if not my_raffles:
        await safe_edit_message(
            query,
            "❌ You haven't created any active raffles.\n\n"
            "Use <code>/raffle</code> to create one!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="raffles_back")]])
        )
        return

    msg = "🎰 <b>Your Active Raffles</b>\n\n"
    for raffle in my_raffles:
        end_time = datetime.fromisoformat(raffle['end_time'].replace('Z', '+00:00'))
        time_left = end_time - datetime.now(timezone.utc)
        total_tickets = sum(raffle['tickets'].values())
        participants = len(raffle['tickets'])

        msg += (
            f"<b>ID:</b> <code>{raffle['id']}</code>\n"
            f"{pe('money')} Prize: ${raffle['prize_usd']:.2f} | 🎫 {total_tickets} tickets | 👥 {participants} players\n"
            f"⏰ Ends in: {time_left.days}d {time_left.seconds//3600}h\n"
            f"Use <code>/info {raffle['id']}</code> for details\n\n"
        )

    await safe_edit_message(
        query,
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="raffles_back")]])
    )

@check_banned
@check_maintenance
async def raffles_active_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all active raffles"""
    query = update.callback_query
    await query.answer()

    if not active_raffles:
        await safe_edit_message(
            query,
            "❌ No active raffles at the moment.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="raffles_back")]])
        )
        return

    msg = "🌟 <b>Active Raffles</b>\n\n"
    raffle_list = list(active_raffles.values())[:10]  # Limit to 10
    if len(active_raffles) > 10:
        msg += f"<i>Showing first 10 of {len(active_raffles)} active raffles</i>\n\n"

    for raffle in raffle_list:
        end_time = datetime.fromisoformat(raffle['end_time'].replace('Z', '+00:00'))
        time_left = end_time - datetime.now(timezone.utc)
        total_tickets = sum(raffle['tickets'].values())
        participants = len(raffle['tickets'])

        msg += (
            f"<b>ID:</b> <code>{raffle['id']}</code>\n"
            f"{pe('money')} Prize: ${raffle['prize_usd']:.2f} | Type: {raffle['type'].title()}\n"
            f"🎫 {total_tickets} tickets | 👥 {participants} players | 🏆 {raffle['total_winners']} winners\n"
            f"⏰ {time_left.days}d {time_left.seconds//3600}h left\n\n"
        )

    await safe_edit_message(
        query,
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="raffles_back")]])
    )

@check_banned
@check_maintenance
async def raffles_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to raffles menu"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    keyboard = [
        [apply_button_style(InlineKeyboardButton("My Raffles", callback_data=f"raffles_mine_{user.id}"), 'primary')],
        [apply_button_style(InlineKeyboardButton("Active Raffles", callback_data="raffles_active"), 'success', peb('star'))],
    ]

    await safe_edit_message(
        query,
        "🎰 <b>Raffle Dashboard</b>\n\n"
        "Select an option:",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard)
    )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('raffle', raffle_command, block=False))
    app.add_handler(CommandHandler('raffles', raffles_command, block=False))
    app.add_handler(CallbackQueryHandler(raffles_mine_callback, pattern='^raffles_mine_', block=False))
    app.add_handler(CallbackQueryHandler(raffles_active_callback, pattern='^raffles_active', block=False))
    app.add_handler(CallbackQueryHandler(raffles_back_callback, pattern='^raffles_back', block=False))

