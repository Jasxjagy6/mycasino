"""Auto-split from bot.py — plugins.bonus."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

@check_banned
@check_maintenance
async def claim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /claim <code> command - claim a surprise code drop."""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            f"Usage: <code>/claim CODE</code>",
            parse_mode=ParseMode.HTML
        )
        return

    code = context.args[0].upper()

    if code not in surprise_drops:
        await update.message.reply_text(f"{pe('cross')} Invalid code. This code does not exist.")
        return

    drop = surprise_drops[code]

    if drop.get("status") != "active" or drop.get("claimed_by") is not None:
        await update.message.reply_text(f"{pe('cross')} This code has already been claimed!")
        return

    # Check wager requirement
    user_wagered = user_stats.get(user.id, {}).get("bets", {}).get("amount", 0.0)
    if user_wagered < drop["wager_requirement"]:
        await update.message.reply_text(
            f"{pe('cross')} <b>Wager requirement not met!</b>\n\n"
            f"You need <b>${drop['wager_requirement']:.2f}</b> wagered in the last 30 days.\n"
            f"Your current 30-day wager: <b>${user_wagered:.2f}</b>",
            parse_mode=ParseMode.HTML
        )
        return

    # Claim the code
    drop["claimed_by"] = user.id
    drop["claimed_by_username"] = normalize_username(user.username) or f"User_{user.id}"
    drop["status"] = "claimed"

    # Credit the user with the amount (marked as deposit for 2x wager requirement)
    credit_wallet(user.id, drop["amount"])
    user_stats.setdefault(user.id, {})["unwagered_deposit"] = user_stats.get(user.id, {}).get("unwagered_deposit", 0.0) + drop["amount"]
    save_user_data(user.id)

    claimer_display = get_privacy_display_name(user.id, drop["claimed_by_username"])

    await update.message.reply_text(
        f"\U0001f389 <b>Code Claimed!</b>\n\n"
        f"You claimed <b>${drop['amount']:.2f}</b> from surprise code <code>{code}</code>!\n"
        f"\u26a0\ufe0f This amount has a <b>2x</b> wager requirement before withdrawal.",
        parse_mode=ParseMode.HTML
    )

    # Update the original message with claimed status
    try:
        bot_username = await get_bot_username(context)
        new_img = generate_surprise_drop_image(code, drop["amount"], drop["wager_requirement"], bot_username, claimed_by=claimer_display)

        await context.bot.edit_message_media(
            chat_id=drop["chat_id"],
            message_id=drop["message_id"],
            media=InputMediaPhoto(
                media=new_img,
                caption=(
                    f"\U0001f381 <b>SURPRISE CODE DROP!</b> \U0001f381\n\n"
                    f"A surprise bonus of <b>${drop['amount']:.2f}</b> was dropped!\n"
                    f"<b>CLAIMED</b> by @{claimer_display}!\n\n"
                    f"Code: <code>{code}</code>\n"
                    f"\u26a0\ufe0f Better luck next time!"
                ),
                parse_mode=ParseMode.HTML,
            )
        )
    except Exception as e:
        logging.warning(f"Could not update surprise drop message: {e}")

@check_banned
@check_maintenance
async def claim_gift_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /claim <code>")
        return

    code = context.args[0]

    if code not in gift_codes:
        await update.message.reply_text("Invalid or expired gift code.")
        return

    code_data = gift_codes[code]

    if code_data["claims_left"] <= 0:
        await update.message.reply_text("This gift code has already been fully claimed.")
        return

    if user.id in code_data["claimed_by"]:
        await update.message.reply_text("You have already claimed this gift code.")
        return

    # Check wager requirement
    wager_requirement = code_data.get("wager_requirement", 0)
    if wager_requirement > 0:
        user_total_wagered = user_stats[user.id].get("bets", {}).get("amount", 0.0)
        if user_total_wagered < wager_requirement:
            await update.message.reply_text(
                f"{pe('cross')} You don't meet the wager requirement for this gift code.\n\n"
                f"Required: ${wager_requirement:.2f} wagered\n"
                f"Your total wagered: ${user_total_wagered:.2f}\n"
                f"You need to wager ${wager_requirement - user_total_wagered:.2f} more in the casino to claim this code."
            )
            return

    # All checks passed, award the user
    amount = code_data["amount"]
    credit_wallet(user.id, amount)
    user_stats[user.id].setdefault("claimed_gift_codes", []).append(code)

    code_data["claims_left"] -= 1
    code_data["claimed_by"].append(user.id)

    save_user_data(user.id)
    save_gift_code(code)

    await update.message.reply_text(f"{pe('win')} Success! You have claimed a gift code and received ${amount:.2f}!")

async def calculate_all_user_bonuses(bonus_type: str) -> dict:
    """Calculate bonuses for all users. Returns dict with user_id: bonus_amount"""
    bonuses = {}
    now = datetime.now(timezone.utc)

    for user_id, stats in user_stats.items():
        if bonus_type == "weekly":
            weekly_stats = stats.get("weekly_stats", {"weighted_wager": 0.0, "net_loss": 0.0})
            weighted_wager = weekly_stats.get("weighted_wager", 0.0)
            net_loss = weekly_stats.get("net_loss", 0.0)
        else:  # monthly
            monthly_stats = stats.get("monthly_stats", {"weighted_wager": 0.0, "net_loss": 0.0})
            weighted_wager = monthly_stats.get("weighted_wager", 0.0)
            net_loss = monthly_stats.get("net_loss", 0.0)

        loss_component = max(0, net_loss) * 0.05
        tier = get_user_tier(user_id)
        vip_base = VIP_BASE_REWARDS.get(tier, 0.10)
        bonus = vip_base + (weighted_wager * 1.0) + loss_component

        if bonus > 0:
            # Apply username bonus
            final_bonus = apply_username_bonus(bonus, user_id)
            bonuses[user_id] = final_bonus

    return bonuses

async def send_admin_bonus_notification(context: ContextTypes.DEFAULT_TYPE, bonus_type: str):
    """Send admin notification 10 hours before bonus release with adjustment options"""
    try:
        bonuses = await calculate_all_user_bonuses(bonus_type)
        total_bonus = sum(bonuses.values())
        user_count = len(bonuses)

        if user_count == 0:
            logging.info(f"No users eligible for {bonus_type} bonus")
            return

        # Calculate release time
        now = datetime.now(timezone.utc)
        if bonus_type == "weekly":
            # Find next Saturday 6pm
            days_until_saturday = (5 - now.weekday()) % 7
            if days_until_saturday == 0 and now.hour >= 18:
                days_until_saturday = 7
            release_time = (now + timedelta(days=days_until_saturday)).replace(hour=18, minute=0, second=0, microsecond=0)
        else:  # monthly
            # Find next 15th midnight
            if now.day >= 15:
                # Next month
                if now.month == 12:
                    release_time = now.replace(year=now.year + 1, month=1, day=15, hour=0, minute=0, second=0, microsecond=0)
                else:
                    release_time = now.replace(month=now.month + 1, day=15, hour=0, minute=0, second=0, microsecond=0)
            else:
                # This month
                release_time = now.replace(day=15, hour=0, minute=0, second=0, microsecond=0)

        bonus_adjustments[bonus_type]["release_time"] = release_time.isoformat()

        message = (
            f"🔔 <b>{bonus_type.title()} Bonus Notification</b>\n\n"
            f"{pe('chart')} <b>Summary:</b>\n"
            f"• Total users eligible: {user_count}\n"
            f"• Total bonus amount: ${total_bonus:.2f}\n"
            f"• Average per user: ${total_bonus/user_count:.2f}\n\n"
            f"⏰ Release time: {release_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"(Users can claim in 10 hours)\n\n"
            f"Use the buttons below to adjust bonuses:"
        )

        keyboard = [
            [
                InlineKeyboardButton("Increase Bonus", callback_data=f"bonus_adjust_{bonus_type}_increase"),
                InlineKeyboardButton("Decrease Bonus", callback_data=f"bonus_adjust_{bonus_type}_decrease")
            ],
            [InlineKeyboardButton("No Change", callback_data=f"bonus_adjust_{bonus_type}_nochange")]
        ]

        await context.bot.send_message(
            chat_id=BOT_OWNER_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        logging.info(f"Admin notification sent for {bonus_type} bonus")

    except Exception as e:
        logging.error(f"Error sending admin bonus notification: {e}")

@check_banned
@check_maintenance
async def bonus_adjust_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bonus adjustment button clicks"""
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer("This is admin only!", show_alert=True)
        return

    await query.answer()

    # Parse callback data: bonus_adjust_{type}_{action}
    parts = query.data.split("_")
    if len(parts) < 4:
        return

    bonus_type = parts[2]  # weekly or monthly
    action = parts[3]  # increase, decrease, nochange

    if action == "nochange":
        await query.edit_message_text(
            f"{pe('check')} No adjustment made to {bonus_type} bonus.\n"
            f"Users can claim their bonuses as calculated.",
            parse_mode=ParseMode.HTML
        )
        return

    # Store action in context for next step
    context.user_data['bonus_adjust_type'] = bonus_type
    context.user_data['bonus_adjust_action'] = action
    context.user_data['bonus_adjust_message_id'] = query.message.message_id

    await query.edit_message_text(
        f"{pe('chart')} <b>Adjust {bonus_type.title()} Bonus</b>\n\n"
        f"Enter the percentage to {action} the bonus:\n"
        f"• For example: <code>10</code> for 10%\n"
        f"• For 50%: <code>50</code>\n\n"
        f"Type the number below:",
        parse_mode=ParseMode.HTML
    )

    # Set up message handler for percentage input
    context.user_data['awaiting_bonus_percentage'] = True

async def bonus_percentage_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle percentage input for bonus adjustment"""
    if not context.user_data.get('awaiting_bonus_percentage'):
        return

    try:
        percentage = float(update.message.text.strip())
        if percentage < 0:
            await update.message.reply_text(f"{pe('cross')} Percentage must be positive. Please try again.")
            return

        bonus_type = context.user_data.get('bonus_adjust_type')
        action = context.user_data.get('bonus_adjust_action')

        # Apply adjustment
        if action == "decrease":
            percentage = -percentage

        bonus_adjustments[bonus_type]["adjustment_percent"] = percentage
        bonus_adjustments[bonus_type]["last_adjustment_time"] = datetime.now(timezone.utc).isoformat()

        # Calculate new totals
        bonuses = await calculate_all_user_bonuses(bonus_type)
        total_before = sum(bonuses.values())
        total_after = total_before * (1 + percentage / 100)

        keyboard = [
            [
                InlineKeyboardButton("Notify Users", callback_data=f"bonus_notify_{bonus_type}_yes"),
                InlineKeyboardButton("Don't Notify", callback_data=f"bonus_notify_{bonus_type}_no")
            ]
        ]

        await update.message.reply_text(
            f"{pe('check')} <b>Bonus Adjustment Applied</b>\n\n"
            f"{pe('chart')} {bonus_type.title()} bonus {action}d by {abs(percentage):.1f}%\n\n"
            f"<b>Impact:</b>\n"
            f"• Before: ${total_before:.2f}\n"
            f"• After: ${total_after:.2f}\n"
            f"• Difference: ${total_after - total_before:.2f}\n\n"
            f"Do you want to notify users about this adjustment when they claim?",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Clear state
        context.user_data['awaiting_bonus_percentage'] = False

    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid number. Please enter a valid percentage.")

@check_banned
@check_maintenance
async def bonus_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle notify users decision"""
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer("This is admin only!", show_alert=True)
        return

    await query.answer()

    # Parse callback data: bonus_notify_{type}_{decision}
    parts = query.data.split("_")
    if len(parts) < 4:
        return

    bonus_type = parts[2]  # weekly or monthly
    decision = parts[3]  # yes or no

    bonus_adjustments[bonus_type]["notify_users"] = (decision == "yes")

    notify_text = "will be notified" if decision == "yes" else "will NOT be notified"

    await query.edit_message_text(
        f"{pe('check')} <b>Settings Updated</b>\n\n"
        f"Users {notify_text} about the bonus adjustment when they claim their {bonus_type} bonus.\n\n"
        f"Adjustment: {bonus_adjustments[bonus_type]['adjustment_percent']:.1f}%",
        parse_mode=ParseMode.HTML
    )

async def check_and_send_bonus_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Check if it's time to send bonus notifications (called periodically)"""
    now = datetime.now(timezone.utc)

    # Check weekly (Saturday 8am UTC = 10 hours before 6pm)
    if now.weekday() == 5 and now.hour == 8 and now.minute < 30:  # Saturday 8am
        # Check if we already sent notification recently
        last_adj = bonus_adjustments["weekly"].get("last_adjustment_time")
        if last_adj and isinstance(last_adj, str):
            try:
                last_adj_dt = datetime.fromisoformat(last_adj)
                if (now - last_adj_dt).days < 7:
                    return  # Already notified this week
            except (ValueError, TypeError):
                pass  # Invalid format, proceed with notification
        await send_admin_bonus_notification(context, "weekly")

    # Check monthly (14th 2pm UTC = 10 hours before 15th midnight)
    if now.day == 14 and now.hour == 14 and now.minute < 30:
        last_adj = bonus_adjustments["monthly"].get("last_adjustment_time")
        if last_adj and isinstance(last_adj, str):
            try:
                last_adj_dt = datetime.fromisoformat(last_adj)
                # Check if it's been at least 25 days (to avoid duplicate notifications in same month)
                if (now - last_adj_dt).days < 25:
                    return
            except (ValueError, TypeError):
                pass
        await send_admin_bonus_notification(context, "monthly")

async def bonus_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    user = query.from_user
    action = query.data.split('_')[1]

    if action == "weekly":
        await weekly_bonus_command(update, context, from_callback=True)
    elif action == "monthly":
        await monthly_bonus_command(update, context, from_callback=True)
    elif action == "rakeback":
        await rakeback_command(update, context, from_callback=True)

@check_banned
@check_maintenance
async def weekly_bonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)
    stats = user_stats[user.id]
    now = datetime.now(timezone.utc)

    # Check if today is Saturday (weekday() == 5) and within 48h window
    # Find the most recent Saturday at 6:00 PM UTC
    days_since_saturday = (now.weekday() - 5) % 7
    last_saturday_6pm = (now - timedelta(days=days_since_saturday)).replace(hour=18, minute=0, second=0, microsecond=0)
    if last_saturday_6pm > now:
        last_saturday_6pm -= timedelta(days=7)

    window_end = last_saturday_6pm + timedelta(hours=48)

    if now < last_saturday_6pm or now > window_end:
        # Not within the claim window
        next_saturday = last_saturday_6pm + timedelta(days=7)
        time_until = next_saturday - now
        msg = (f"{pe('daily')} <b>Weekly Bonus</b>\n\n"
               f"Weekly bonus is available every <b>Saturday at 6:00 PM UTC</b> for 48 hours.\n"
               f"Next available in: <b>{time_until.days}d {time_until.seconds//3600}h</b>"
               + get_username_bonus_guidance())
        if from_callback:
            await safe_edit_message(update.callback_query, msg, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    # Check if already claimed this period
    last_claim_str = stats.get("last_weekly_claim")
    if last_claim_str:
        last_claim_time = datetime.fromisoformat(last_claim_str)
        if last_claim_time >= last_saturday_6pm:
            msg = ("✅ You've already claimed your weekly bonus this period!"
                   + get_username_bonus_guidance())
            if from_callback:
                await update.callback_query.answer("Already claimed this week!", show_alert=True)
            else:
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

    # Calculate bonus using new formula:
    # Bonus = VIP_Base_Reward + (Weekly_Weighted_Wager * 1.0) + (Weekly_Net_Loss * 0.05)
    weekly_stats = stats.get("weekly_stats", {"weighted_wager": 0.0, "net_loss": 0.0})
    weighted_wager = weekly_stats.get("weighted_wager", 0.0)
    net_loss = weekly_stats.get("net_loss", 0.0)

    # If net_loss is negative (profit), the loss component is 0
    loss_component = max(0, net_loss) * 0.05

    tier = get_user_tier(user.id)
    vip_base = VIP_BASE_REWARDS.get(tier, 0.10)

    bonus = vip_base + (weighted_wager * 1.0) + loss_component

    if bonus <= 0:
        msg = ("You haven't wagered enough to earn a weekly bonus." + get_username_bonus_guidance())
        if from_callback:
            await update.callback_query.answer("No bonus to claim!", show_alert=True)
        else:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    # Apply adjustment if set by admin
    adjustment_percent = bonus_adjustments["weekly"]["adjustment_percent"]
    adjusted_bonus = bonus * (1 + adjustment_percent / 100)

    # Apply username bonus (5% extra if user has bot username in name)
    final_bonus = apply_username_bonus(adjusted_bonus, user.id)
    has_bonus = check_username_bonus(user.id)

    credit_wallet(user.id, final_bonus)
    stats["last_weekly_claim"] = str(now)
    # Reset weekly stats after claiming
    stats["weekly_stats"] = {"weighted_wager": 0.0, "net_loss": 0.0, "last_claim": str(now)}
    save_user_data(user.id)

    bonus_text = ""
    if has_bonus:
        # Show username bonus as 5% of the base bonus (not adjusted bonus)
        username_bonus_amount = bonus * 0.05
        bonus_text = f"\n{pe('win')} <b>Username Bonus:</b> +5% (${username_bonus_amount:.2f})"

    # Add adjustment notification if admin enabled it
    adjustment_text = ""
    if adjustment_percent != 0 and bonus_adjustments["weekly"]["notify_users"]:
        if adjustment_percent > 0:
            adjustment_text = f"\n\n{pe('gift')} <b>Special Bonus!</b> Admin increased all bonuses by {adjustment_percent:.1f}%!"
        else:
            adjustment_text = f"\n\n{pe('warning')} Note: Bonuses were adjusted by {adjustment_percent:.1f}% this week."

    msg = (
        f"{pe('daily')} <b>Weekly Bonus Claimed!</b>\n\n"
        f"{pe('money')} Amount: <b>${final_bonus:.2f}</b>{bonus_text}\n\n"
        f"<b>Breakdown:</b>\n"
        f"  VIP Base ({tier}): ${vip_base:.2f}\n"
        f"  Weighted Wager: ${weighted_wager:.4f}\n"
        f"  Net Loss Bonus: ${loss_component:.2f}"
        + adjustment_text
        + get_username_bonus_guidance()
    )

    if from_callback:
        keyboard = [[InlineKeyboardButton("Back to Bonuses", callback_data="main_bonuses")]]
        await safe_edit_message(update.callback_query, msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@check_banned
@check_maintenance
async def monthly_bonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)
    stats = user_stats[user.id]
    now = datetime.now(timezone.utc)

    # Check if today is the 15th and within 48h window
    # Find the most recent 15th at 00:00 UTC
    if now.day >= 15:
        claim_start = now.replace(day=15, hour=0, minute=0, second=0, microsecond=0)
    else:
        # Go to previous month's 15th
        if now.month == 1:
            claim_start = now.replace(year=now.year - 1, month=12, day=15, hour=0, minute=0, second=0, microsecond=0)
        else:
            claim_start = now.replace(month=now.month - 1, day=15, hour=0, minute=0, second=0, microsecond=0)

    window_end = claim_start + timedelta(hours=48)

    if now < claim_start or now > window_end:
        # Not within the claim window
        if now.day >= 15 and now > window_end:
            # Next month's 15th
            if now.month == 12:
                next_15th = now.replace(year=now.year + 1, month=1, day=15, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_15th = now.replace(month=now.month + 1, day=15, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_15th = claim_start
        time_until = next_15th - now
        msg = (f"🗓️ <b>Monthly Bonus</b>\n\n"
               f"Monthly bonus is available on the <b>15th of every month</b> for 48 hours.\n"
               f"Next available in: <b>{time_until.days}d {time_until.seconds//3600}h</b>"
               + get_username_bonus_guidance())
        if from_callback:
            await safe_edit_message(update.callback_query, msg, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    # Check if already claimed this period
    last_claim_str = stats.get("last_monthly_claim")
    if last_claim_str:
        last_claim_time = datetime.fromisoformat(last_claim_str)
        if last_claim_time >= claim_start:
            msg = ("✅ You've already claimed your monthly bonus this period!"
                   + get_username_bonus_guidance())
            if from_callback:
                await update.callback_query.answer("Already claimed this month!", show_alert=True)
            else:
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            return

    # Calculate bonus using same formula as weekly but with monthly stats
    # Bonus = VIP_Base_Reward + (Monthly_Weighted_Wager * 1.0) + (Monthly_Net_Loss * 0.05)
    monthly_stats = stats.get("monthly_stats", {"weighted_wager": 0.0, "net_loss": 0.0})
    weighted_wager = monthly_stats.get("weighted_wager", 0.0)
    net_loss = monthly_stats.get("net_loss", 0.0)

    # If net_loss is negative (profit), the loss component is 0
    loss_component = max(0, net_loss) * 0.05

    tier = get_user_tier(user.id)
    vip_base = VIP_BASE_REWARDS.get(tier, 0.10)

    bonus = vip_base + (weighted_wager * 1.0) + loss_component

    if bonus <= 0:
        msg = ("You haven't wagered enough to earn a monthly bonus." + get_username_bonus_guidance())
        if from_callback:
            await update.callback_query.answer("No bonus to claim!", show_alert=True)
        else:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    # Apply adjustment if set by admin
    adjustment_percent = bonus_adjustments["monthly"]["adjustment_percent"]
    adjusted_bonus = bonus * (1 + adjustment_percent / 100)

    # Apply username bonus (5% extra if user has bot username in name)
    final_bonus = apply_username_bonus(adjusted_bonus, user.id)
    has_bonus = check_username_bonus(user.id)

    credit_wallet(user.id, final_bonus)
    stats["last_monthly_claim"] = str(now)
    # Reset monthly stats after claiming
    stats["monthly_stats"] = {"weighted_wager": 0.0, "net_loss": 0.0, "last_claim": str(now)}
    save_user_data(user.id)

    bonus_text = ""
    if has_bonus:
        # Show username bonus as 5% of the base bonus (not adjusted bonus)
        username_bonus_amount = bonus * 0.05
        bonus_text = f"\n{pe('win')} <b>Username Bonus:</b> +5% (${username_bonus_amount:.2f})"

    # Add adjustment notification if admin enabled it
    adjustment_text = ""
    if adjustment_percent != 0 and bonus_adjustments["monthly"]["notify_users"]:
        if adjustment_percent > 0:
            adjustment_text = f"\n\n{pe('gift')} <b>Special Bonus!</b> Admin increased all bonuses by {adjustment_percent:.1f}%!"
        else:
            adjustment_text = f"\n\n{pe('warning')} Note: Bonuses were adjusted by {adjustment_percent:.1f}% this month."

    msg = (
        f"🗓️ <b>Monthly Bonus Claimed!</b>\n\n"
        f"{pe('money')} Amount: <b>${final_bonus:.2f}</b>{bonus_text}\n\n"
        f"<b>Breakdown:</b>\n"
        f"  VIP Base ({tier}): ${vip_base:.2f}\n"
        f"  Weighted Wager: ${weighted_wager:.4f}\n"
        f"  Net Loss Bonus: ${loss_component:.2f}"
        + adjustment_text
        + get_username_bonus_guidance()
    )

    if from_callback:
        keyboard = [[InlineKeyboardButton("Back to Bonuses", callback_data="main_bonuses")]]
        await safe_edit_message(update.callback_query, msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('claim', claim_command, block=False))
    app.add_handler(CommandHandler('claim', claim_gift_code_command, block=False))
    app.add_handler(CommandHandler('weekly', weekly_bonus_command, block=False))
    app.add_handler(CommandHandler('monthly', monthly_bonus_command, block=False))
    app.add_handler(CallbackQueryHandler(bonus_adjust_callback, pattern='^bonus_adjust_', block=False))
    app.add_handler(CallbackQueryHandler(bonus_notify_callback, pattern='^bonus_notify_', block=False))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bonus_percentage_input, block=False))

