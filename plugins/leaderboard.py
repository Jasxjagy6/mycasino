"""Auto-split from bot.py — plugins.leaderboard."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

async def _flush_leaderboard_buffer():
    """Batch-process leaderboard updates every 10 seconds.

    PERFORMANCE: dropped the per-entry INFO log (fires once per bet, so in a
    busy casino that's hundreds of file-I/O log records a minute for no
    operational benefit). Kept a DEBUG line for troubleshooting and an
    INFO only when something actually fails.
    """
    logging.debug("[LEADERBOARD] Flush task started (10s interval)")
    while True:
        await asyncio.sleep(10)
        async with _leaderboard_buffer_lock:
            if not _leaderboard_buffer:
                continue
            batch = list(_leaderboard_buffer)
            _leaderboard_buffer.clear()
        failures = 0
        for (user_id, amount, win_amount, game_type, multiplier, ts) in batch:
            try:
                update_leaderboards(user_id, amount, win_amount, game_type, multiplier)
            except Exception as e:
                failures += 1
                logging.error(
                    f"Leaderboard update error for {user_id}: {e}",
                    exc_info=True
                )
        if failures:
            logging.warning(
                f"[LEADERBOARD] batch of {len(batch)} processed, "
                f"{failures} failure(s)"
            )
        else:
            logging.debug(f"[LEADERBOARD] batch of {len(batch)} processed")

def update_leaderboards(user_id, bet_amount, win_amount=0, game_type="", multiplier=0):
    """Update leaderboard data after each bet"""
    global leaderboard_data, leaderboard_last_update

    # Get user info
    username = user_stats.get(user_id, {}).get('userinfo', {}).get('username', f'User-{user_id}')
    username = username.lstrip('@')

    # Check for weekly/monthly reset
    now = datetime.now(timezone.utc)

    # Weekly reset (every Monday)
    if now.date() > leaderboard_last_update["weekly_reset"].date():
        days_diff = (now.date() - leaderboard_last_update["weekly_reset"].date()).days
        if days_diff >= 7 or now.weekday() < leaderboard_last_update["weekly_reset"].weekday():
            leaderboard_data["weekly"] = []
            leaderboard_last_update["weekly_reset"] = now

    # Monthly reset
    if now.month != leaderboard_last_update["monthly_reset"].month or now.year != leaderboard_last_update["monthly_reset"].year:
        leaderboard_data["monthly"] = []
        leaderboard_data["highest_wins"] = []  # Reset highest wins monthly
        leaderboard_last_update["monthly_reset"] = now

    # Update all-time leaderboard
    total_wagered = user_stats.get(user_id, {}).get('bets', {}).get('amount', 0.0)
    _update_leaderboard_entry(leaderboard_data["all_time"], user_id, username, total_wagered)

    # Update weekly leaderboard
    _update_leaderboard_entry(leaderboard_data["weekly"], user_id, username, bet_amount, accumulate=True)

    # Update monthly leaderboard
    _update_leaderboard_entry(leaderboard_data["monthly"], user_id, username, bet_amount, accumulate=True)

    # Update highest wins if this is a win
    if win_amount > 0 and multiplier > 0:
        _update_highest_wins(user_id, username, win_amount, game_type, now)

    # Keep only top 10 (already sorted by bisect insertion)
    for key in ["all_time", "weekly", "monthly"]:
        if len(leaderboard_data[key]) > 10:
            del leaderboard_data[key][10:]
    if len(leaderboard_data["highest_wins"]) > 10:
        leaderboard_data["highest_wins"] = sorted(leaderboard_data["highest_wins"], key=lambda x: x[2], reverse=True)[:10]

def _update_leaderboard_entry(leaderboard, user_id, username, amount, accumulate=False):
    """O(log n) insertion using bisect instead of O(n log n) sort."""
    new_score = 0
    for i, entry in enumerate(leaderboard):
        if entry[0] == user_id:
            new_score = (entry[2] + amount) if accumulate else amount
            leaderboard.pop(i)
            break
    else:
        new_score = amount

    # bisect on negative values to achieve descending sort
    scores_neg = [-e[2] for e in leaderboard]
    idx = bisect.bisect_left(scores_neg, -new_score)
    leaderboard.insert(idx, (user_id, username, new_score))

    if len(leaderboard) > 10:
        del leaderboard[10:]

def _update_highest_wins(user_id, username, win_amount, game_type, timestamp):
    """Helper to update highest wins"""
    # Check if this win should be in top 10
    if len(leaderboard_data["highest_wins"]) < 10 or win_amount > leaderboard_data["highest_wins"][-1][2]:
        leaderboard_data["highest_wins"].append((user_id, username, win_amount, game_type, timestamp))
        leaderboard_data["highest_wins"] = sorted(leaderboard_data["highest_wins"], key=lambda x: x[2], reverse=True)[:10]

@check_banned
@check_maintenance
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    """Display leaderboard with interactive buttons"""
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    user_id = update.effective_user.id

    # Set menu owner for group protection when called as command
    if not from_callback:
        context.user_data['menu_owner_id'] = user_id

    # Rebuild leaderboard from user_stats before display
    _rebuild_leaderboards()

    # Default view is all-time
    view = context.user_data.get('leaderboard_view', 'all_time')

    # Leaderboard amounts are rendered in the VIEWING user's display
    # currency, compact-formatted so big numbers collapse to
    # e.g. 6.3L (INR) or $1.2M (USD) instead of bleeding across the row.
    def _fmt(amt_usd):
        return format_compact_for_user(user_id, amt_usd)

    # Get leaderboard data
    if view == 'all_time':
        title = f"{pe('trophy')} <b>Top 10 Players - All Time</b> {pe('trophy')}"
        data = leaderboard_data["all_time"]
        msg = f"{title}\n\n"
        if data:
            for i, (uid, username, wagered) in enumerate(data):
                rank_sym = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                display_name = get_privacy_display_name(uid, username)
                msg += f"{rank_sym} {display_name} - <b>{_fmt(wagered)}</b>\n"
        else:
            msg += "No data available yet.\n"
    elif view == 'weekly':
        title = f"{pe('weekly')} <b>Top 10 Players - This Week</b> {pe('weekly')}"
        data = leaderboard_data["weekly"]
        msg = f"{title}\n\n"
        if data:
            for i, (uid, username, wagered) in enumerate(data):
                rank_sym = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                display_name = get_privacy_display_name(uid, username)
                msg += f"{rank_sym} {display_name} - <b>{_fmt(wagered)}</b>\n"
        else:
            msg += "No data available yet.\n"
    elif view == 'monthly':
        title = f"{pe('monthly')} <b>Top 10 Players - This Month</b> {pe('monthly')}"
        data = leaderboard_data["monthly"]
        msg = f"{title}\n\n"
        if data:
            for i, (uid, username, wagered) in enumerate(data):
                rank_sym = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                display_name = get_privacy_display_name(uid, username)
                msg += f"{rank_sym} {display_name} - <b>{_fmt(wagered)}</b>\n"
        else:
            msg += "No data available yet.\n"
    elif view == 'highest_wins':
        title = f"{pe('money')} <b>Highest Wins - This Month</b> {pe('money')}"
        data = leaderboard_data["highest_wins"]
        msg = f"{title}\n\n"
        if data:
            for i, (uid, username, win_amount, game_type, timestamp) in enumerate(data):
                rank_sym = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                display_name = get_privacy_display_name(uid, username)
                date_str = timestamp.strftime("%Y-%m-%d") if isinstance(timestamp, datetime) else str(timestamp)[:10]
                msg += f"{rank_sym} {display_name} - <b>{_fmt(win_amount)}</b>\n   Game: {game_type.upper()} | Date: {date_str}\n\n"
        else:
            msg += "No wins recorded yet.\n"

    # === Calculate user's rank ===
    # Find user's position in the current view
    if view == 'highest_wins':
        ranked_list = [(uid, uname, wamt) for uid, uname, wamt, _, _ in leaderboard_data.get('highest_wins', [])]
    else:
        ranked_list = leaderboard_data.get(view if view != 'alltime' else 'all_time', [])

    user_rank = None
    user_wagered = 0.0
    for i, (uid, uname, wag) in enumerate(ranked_list):
        if uid == user_id:
            user_rank = i + 1
            user_wagered = wag
            break

    # If not in top 10, calculate rank from all users
    if user_rank is None:
        if view == 'highest_wins':
            all_entries = [(uid, uname, wamt) for uid, uname, wamt, _, _ in leaderboard_data.get('highest_wins', [])]
        else:
            all_entries = leaderboard_data.get(view if view != 'alltime' else 'all_time', [])

        # Check if user has any wagering
        stats = user_stats.get(user_id, {})
        if view == 'weekly':
            user_wagered = stats.get('weekly_stats', {}).get('weighted_wager', 0.0)
        elif view == 'monthly':
            user_wagered = stats.get('monthly_stats', {}).get('weighted_wager', 0.0)
        elif view == 'highest_wins':
            user_wagered = stats.get('last_win', 0)
        else:
            user_wagered = stats.get('bets', {}).get('amount', 0.0)

        if user_wagered > 0:
            # Count how many users have more wagered
            rank = 1
            for uid2, uname2, wag2 in all_entries:
                if wag2 > user_wagered:
                    rank += 1
            user_rank = rank
        else:
            user_rank = "Unranked"
            user_wagered = 0.0

    # Add user rank to message (wagered in user's display currency, compact).
    wagered_str = format_compact_for_user(user_id, user_wagered)
    rank_display = ""
    if isinstance(user_rank, int):
        rank_display = f"\n{pe('chart')} <b>Your Rank: #{user_rank}</b> - {wagered_str} wagered"
    else:
        rank_display = f"\n{pe('chart')} <b>Your Rank:</b> Unranked - {wagered_str} wagered"

    msg += rank_display

    # Determine if in group chat
    is_group = False
    if from_callback and update.callback_query:
        try:
            is_group = update.callback_query.message.chat.type in ["group", "supergroup"]
        except AttributeError:
            pass
    elif update.effective_chat:
        is_group = update.effective_chat.type in ["group", "supergroup"]

    # Create inline buttons (user-specific)
    keyboard = [
        [
            apply_button_style(InlineKeyboardButton("Weekly", callback_data=f"leaderboard_weekly_{user_id}"), 'primary'),
            apply_button_style(InlineKeyboardButton("Monthly", callback_data=f"leaderboard_monthly_{user_id}"), 'success')
        ],
        [
            apply_button_style(InlineKeyboardButton("Highest Wins", callback_data=f"leaderboard_wins_{user_id}"), 'primary')
        ],
        [
            apply_button_style(InlineKeyboardButton("All Time", callback_data=f"leaderboard_alltime_{user_id}"), 'success')
        ],
    ]

    # Only show back button in DMs
    if not is_group:
        keyboard.append([
            apply_button_style(InlineKeyboardButton("Back to More", callback_data="main_more"), 'danger', peb('back'))
        ])

    reply_markup = create_styled_keyboard(keyboard)

    # Generate leaderboard image
    lb_image = await generate_leaderboard_image(context, period=view, viewing_user_id=user_id)

    if from_callback:
        # EDIT the existing message in place - no delete+resend (like blackjack)
        if lb_image:
            try:
                await update.callback_query.edit_message_media(
                    media=InputMediaPhoto(media=lb_image, parse_mode=ParseMode.HTML),
                    reply_markup=reply_markup
                )
                return
            except Exception as e:
                logging.error(f"Error updating leaderboard image: {e}")

        # Fallback: edit text message in place
        await update.callback_query.edit_message_text(
            msg,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    else:
        # Main bot handles /leaderboard in all chats (groups and DMs)
        # Get original message ID for tagging in groups
        original_message_id = None
        if is_group and update.message:
            original_message_id = update.message.message_id

        if lb_image:
            if original_message_id:
                sent_message = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=lb_image,
                    reply_markup=reply_markup,
                    reply_to_message_id=original_message_id
                )
            else:
                sent_message = await update.message.reply_photo(
                    photo=lb_image,
                    reply_markup=reply_markup
                )
        else:
            if original_message_id:
                sent_message = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                    reply_to_message_id=original_message_id
                )
            else:
                sent_message = await update.message.reply_text(
                    msg,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
        if reply_markup:
            set_menu_owner(sent_message, user_id)
        return

@check_banned
@check_maintenance
async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle leaderboard navigation button clicks"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data
    parts = query.data.split("_")
    if len(parts) < 3:
        return

    action = parts[1]  # weekly, monthly, wins, alltime
    button_user_id = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None

    # User-specific button check
    if button_user_id and user.id != button_user_id:
        await query.answer("This menu is not for you!", show_alert=True)
        return

    await query.answer()

    # Set the view in user_data
    view_map = {
        'weekly': 'weekly',
        'monthly': 'monthly',
        'wins': 'highest_wins',
        'alltime': 'all_time'
    }

    if action in view_map:
        context.user_data['leaderboard_view'] = view_map[action]
        await leaderboard_command(update, context, from_callback=True)

@check_banned
@check_maintenance
async def leaderboard_referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)

    # Create inline buttons for referral leaderboard
    keyboard = [
        [InlineKeyboardButton("Back to More", callback_data="main_more")]
    ]
    reply_markup = create_styled_keyboard(keyboard)

    # Generate referral leaderboard template image
    rf_image = await generate_leaderboard_referral_image(context)

    is_group = update.effective_chat.type in ["group", "supergroup"]

    # Use helper bot in groups for info commands
    if is_group and helper_bot:
        try:
            if rf_image:
                sent_message = await helper_bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=rf_image,
                    reply_markup=reply_markup
                )
            else:
                sent_message = await helper_bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"{pe('push')} Referral Leaderboard", parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            set_menu_owner(sent_message, update.effective_user.id)
            return
        except Exception as e:
            logging.warning(f"Helper bot failed for /leaderboardrf: {e}")

    if rf_image:
        sent_message = await update.message.reply_photo(
            photo=rf_image,
            reply_markup=reply_markup
        )
    else:
        sent_message = await update.message.reply_text(f"{pe('push')} Referral Leaderboard", parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    set_menu_owner(sent_message, update.effective_user.id)

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('leaderboard', leaderboard_command, block=False))
    app.add_handler(CommandHandler('leaderboardrf', leaderboard_referral_command, block=False))
    app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern='^leaderboard_(weekly|monthly|wins|alltime)_', block=False))
    helper_app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern='^leaderboard_(weekly|monthly|wins|alltime)_', block=False))

