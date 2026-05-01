"""Auto-split from bot.py — plugins.admin_commands."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def ban_user(user_id: int):
    bot_settings.setdefault("banned_users", [])
    if user_id not in bot_settings["banned_users"]:
        bot_settings["banned_users"].append(user_id)
    _banned_set.add(user_id)

def unban_user(user_id: int):
    bot_settings["banned_users"] = [u for u in bot_settings.get("banned_users", []) if u != user_id]
    _banned_set.discard(user_id)

def tempban_user(user_id: int):
    bot_settings.setdefault("tempbanned_users", [])
    if user_id not in bot_settings["tempbanned_users"]:
        bot_settings["tempbanned_users"].append(user_id)
    _tempbanned_set.add(user_id)

def untempban_user(user_id: int):
    bot_settings["tempbanned_users"] = [u for u in bot_settings.get("tempbanned_users", []) if u != user_id]
    _tempbanned_set.discard(user_id)

async def game_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all game on/off statuses (admin only)."""
    if not is_admin(update.effective_user.id):
        return
    lines = ["\U0001f3ae <b>Game Status</b>\n"]
    for gk, sk in GAME_STATUS_MAP.items():
        status = bot_settings.get("game_status", {}).get(sk, True)
        icon = "\u2705" if status else "\U0001f527"
        lines.append(f"{icon} {gk.title()}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

def set_display_currency(user_id, currency: str) -> bool:
    """Persist the user's chosen display currency."""
    currency = (currency or "").upper()
    if currency not in SUPPORTED_DISPLAY_CURRENCIES:
        return False
    try:
        user_stats.setdefault(user_id, {})["display_currency"] = currency
    except Exception:
        return False
    try:
        save_user_data(user_id)
    except Exception:
        pass
    return True

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return  # Silently ignore non-admin users
    await ensure_user_in_wallets(user.id, user.username, context=context)
    ongoing_matches = [m for m in game_sessions.values() if m.get("status") == 'active' and 'players' in m]
    if ongoing_matches:
        await update.message.reply_text("There are ongoing matches. Please finish or use /cancelall before stopping.")
        return
    keyboard = [[InlineKeyboardButton("Yes", callback_data="stop_confirm_yes"), InlineKeyboardButton("No", callback_data="stop_confirm_no")]]
    await update.message.reply_text("Are you sure you want to stop the bot? This will pause new games.", reply_markup=InlineKeyboardMarkup(keyboard))

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    user = update.effective_user
    if not is_admin(user.id):
        return  # Silently ignore non-admin users
    await ensure_user_in_wallets(user.id, user.username, context=context)
    bot_stopped = False
    await update.message.reply_text(f"{pe('check')} Bot is resumed. New matches can be started.")

async def timeout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to set the default round timeout for future emoji games.
    Usage: /timeout <seconds>
    Example: /timeout 60 - sets 60 second timeout per round for new matches.
    Ongoing matches keep their existing timeout.
    """
    global default_round_timeout
    user = update.effective_user
    if not is_admin(user.id):
        return  # Silently ignore non-admin users

    args = context.args
    if not args:
        await update.message.reply_text(
            f"Current default round timeout: <b>{default_round_timeout} seconds</b>\n\n"
            f"Usage: <code>/timeout &lt;seconds&gt;</code>\n"
            f"Example: <code>/timeout 60</code>\n\n"
            f"{pe('warning')} This only affects <b>new matches</b>. Ongoing matches keep their current timeout.",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        new_timeout = int(args[0])
        if new_timeout < 10:
            await update.message.reply_text("Timeout must be at least 10 seconds.")
            return
        if new_timeout > 3600:
            await update.message.reply_text("Timeout cannot exceed 3600 seconds (1 hour).")
            return
    except ValueError:
        await update.message.reply_text("Please provide a valid number of seconds.")
        return

    old_timeout = default_round_timeout
    default_round_timeout = new_timeout
    await update.message.reply_text(
        f"Round timeout changed: {old_timeout}s → <b>{new_timeout}s</b>\n"
        f"This applies to all <b>new matches</b> started from now on.\n"
        f"Ongoing matches will keep their existing timeout.",
        parse_mode=ParseMode.HTML
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return  # Silently ignore non-admin users
    await ensure_user_in_wallets(user.id, user.username, context=context)
    keyboard = [[InlineKeyboardButton("Yes, clear all funds", callback_data="clear_confirm_yes"), InlineKeyboardButton("No, cancel", callback_data="clear_confirm_no")]]
    await update.message.reply_text(f"{pe('warning')} WARNING: This will reset all user balances to zero!\n\nAre you absolutely sure?", reply_markup=InlineKeyboardMarkup(keyboard))

async def clearall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return  # Silently ignore non-admin users
    await ensure_user_in_wallets(user.id, user.username, context=context)
    keyboard = [[InlineKeyboardButton("Yes, erase ALL data", callback_data="clearall_confirm_yes"), InlineKeyboardButton("No, cancel", callback_data="clearall_confirm_no")]]
    await update.message.reply_text(f"{pe('warning')} EXTREME WARNING ⚠️\n\nThis will completely erase ALL user data, including all settings. This action is IRREVERSIBLE!\n\nAre you absolutely sure?", reply_markup=InlineKeyboardMarkup(keyboard))

@check_banned
@check_maintenance
async def cashout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await ensure_user_in_wallets(user_id, update.effective_user.username, context=context)

    # Find active, cashout-able games for the user
    # PERFORMANCE: lookup via per-user active-games index instead of
    # scanning every game session in the system.
    _cashoutable = {'mines', 'tower', 'coin_flip'}
    active_games = []
    for gid in list(_get_user_active_game_ids(user_id)):
        g = game_sessions.get(gid)
        if (g and g.get('user_id') == user_id and g.get('status') == 'active'
                and g.get('game_type') in _cashoutable):
            active_games.append(g)

    if not active_games:
        await update.message.reply_text("No active games to cash out from. Use `/continue <id>` to resume a game.")
        return

    # For simplicity, cashout the most recent one. A better implementation might list them.
    game = sorted(active_games, key=lambda g: g['timestamp'], reverse=True)[0]
    game_id = game['id']

    # Create a fake query object to pass to the callback handlers since they expect one
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.message = message
        async def answer(self, *args, **kwargs): pass
        async def edit_message_text(self, *args, **kwargs):
            await self.message.reply_text(*args, **kwargs)

    fake_update = type('FakeUpdate', (), {'callback_query': FakeQuery(update.effective_user, update.message)})()

    if game['game_type'] == 'mines':
        fake_update.callback_query.data = f'mines_cashout_{game_id}'
        await mines_pick_callback(fake_update, context)
    elif game['game_type'] == 'tower':
        fake_update.callback_query.data = f'tower_cashout_{game_id}'
        await tower_callback(fake_update, context)
    elif game['game_type'] == 'coin_flip':
        fake_update.callback_query.data = f'flip_cashout_{game_id}'
        await coin_flip_callback(fake_update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return  # Silently ignore non-admin users
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    message_text = update.message.text.strip().split()
    if len(message_text) != 2:
        await update.message.reply_text("Usage: /cancel <match_id | deal_id | raffle_id>")
        return
    item_id = message_text[1]

    if item_id in game_sessions:
        game_data = game_sessions[item_id]
        if game_data.get("status") != "active":
            await update.message.reply_text("This game is not active.")
            return

        game_data["status"] = "cancelled"

        # Cancel any pending timeout jobs
        if 'user_id' in game_data:
            # PvB game - cancel user's timeout jobs
            _cancel_pvb_timeout_jobs(context, game_data['user_id'], item_id)
        elif 'players' in game_data:
            # PvP game - cancel timeout jobs for all players
            _cancel_pvp_timeout_jobs(context, item_id)

        # Refund players
        if 'players' in game_data: # PvP
            bet_amount = game_data["bet_amount"]
            for player_id in game_data['players']:
                credit_wallet(player_id, bet_amount)
                save_user_data(player_id)
                try: await context.bot.send_message(player_id, f"Match {item_id} cancelled by owner. Bet of ${bet_amount:.2f} refunded.")
                except Exception as e: logging.warning(f"Could not notify player {player_id}: {e}")
        elif 'user_id' in game_data: # Solo
            player_id = game_data['user_id']
            bet_amount = game_data['bet_amount']
            credit_wallet(player_id, bet_amount)
            save_user_data(player_id)
            try: await context.bot.send_message(player_id, f"Your game {item_id} was cancelled by the owner. Your bet of ${bet_amount:.2f} has been refunded.")
            except Exception as e: logging.warning(f"Could not notify player {player_id}: {e}")

        await update.message.reply_text(f"Game {item_id} cancelled. Bets refunded.")
        return

    if item_id in escrow_deals:
        deal = escrow_deals[item_id]
        if deal['status'] in ['completed', 'cancelled_by_owner', 'disputed']:
             await update.message.reply_text(f"Deal {item_id} is already finalized.")
             return
        deal['status'] = 'cancelled_by_owner'
        if deal.get('deposit_tx_hash'):
            await update.message.reply_text(f"Deal {item_id} cancelled. Manually refund ${deal['amount']:.2f} to seller @{deal['seller']['username']}.")
        else:
            await update.message.reply_text(f"Deal {item_id} cancelled. No funds were deposited.")
        save_escrow_deal(item_id)
        try:
            await context.bot.send_message(deal['seller']['id'], f"Your escrow deal {item_id} has been cancelled by the bot owner.")
            await context.bot.send_message(deal['buyer']['id'], f"Your escrow deal {item_id} has been cancelled by the bot owner.")
        except Exception as e: logging.warning(f"Could not notify users about deal cancellation: {e}")
        return

    # Check if it's a raffle
    if item_id in active_raffles:
        raffle = active_raffles[item_id]
        prize = raffle.get('prize_usd', 0.0)
        creator_id = raffle.get('creator')
        ticket_participants = raffle.get('participants', {})

        # Add raffle prize to house balance (not refunded to creator)
        bot_settings["house_balance"] = bot_settings.get("house_balance", 0) + prize

        # Refund ticket costs to all participants
        refund_count = 0
        for participant_id_str, participant_data in ticket_participants.items():
            try:
                pid = int(participant_id_str)
                ticket_cost_paid = participant_data.get('paid', 0.0)
                if ticket_cost_paid > 0:
                    credit_wallet(pid, ticket_cost_paid)
                    save_user_data(pid)
                    refund_count += 1
                    try:
                        await context.bot.send_message(
                            pid,
                            f"{pe('warning')} Raffle <code>{item_id}</code> has been cancelled by admin.\n"
                            f"Your ticket cost of ${ticket_cost_paid:.2f} has been refunded.",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass
            except (ValueError, TypeError):
                continue

        # Remove from active raffles completely
        del active_raffles[item_id]
        save_bot_state()

        await update.message.reply_text(
            f"{pe('check')} Raffle <code>{item_id}</code> cancelled.\n"
            f"Prize: ${prize:.2f} added to house balance.\n"
            f"Refunded {refund_count} participant(s) ticket costs.",
            parse_mode=ParseMode.HTML
        )
        return

    await update.message.reply_text("No active match, deal, or raffle found with that ID.")

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to kick them.")
        return

    try:
        member = await chat.get_member(user.id)
        if not member.can_restrict_members and member.status != 'creator':
            await update.message.reply_text("You must be an admin with permission to kick users.")
            return

        target_user = update.message.reply_to_message.from_user
        target_member = await chat.get_member(target_user.id)
        if target_member.status in ['administrator', 'creator']:
            await update.message.reply_text("You cannot kick an administrator.")
            return

        await context.bot.ban_chat_member(chat.id, target_user.id)
        await context.bot.unban_chat_member(chat.id, target_user.id) # Unbanning immediately makes it a kick
        await update.message.reply_text(f"Kicked {target_user.mention_html()}.", parse_mode=ParseMode.HTML)
    except BadRequest as e:
        await update.message.reply_text(f"Failed to kick user: {e.message}. I might be missing permissions or the target is an admin.")
    except Exception as e:
        logging.error(f"Error in kick_command: {e}")
        await update.message.reply_text("An error occurred.")

async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to promote them.")
        return

    try:
        member = await chat.get_member(user.id)
        if not member.can_promote_members and member.status != 'creator':
            await update.message.reply_text("You don't have permission to promote members.")
            return

        await context.bot.promote_chat_member(
            chat_id=chat.id,
            user_id=update.message.reply_to_message.from_user.id,
            can_pin_messages=True,
            can_manage_chat=True,
            can_delete_messages=True,
            can_restrict_members=True
        )
        await update.message.reply_text(f"Promoted {update.message.reply_to_message.from_user.mention_html()} to admin.", parse_mode=ParseMode.HTML)
    except BadRequest as e:
        await update.message.reply_text(f"Failed to promote user: {e.message}. I might be missing permissions.")
    except Exception as e:
        logging.error(f"Error in promote_command: {e}")
        await update.message.reply_text("An error occurred.")

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to pin it.")
        return

    try:
        member = await chat.get_member(user.id)
        if not member.can_pin_messages and member.status != 'creator':
            await update.message.reply_text("You don't have permission to pin messages.")
            return

        await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
    except BadRequest as e:
        await update.message.reply_text(f"Failed to pin message: {e.message}. I might be missing permissions.")
    except Exception as e:
        logging.error(f"Error in pin_command: {e}")
        await update.message.reply_text("An error occurred.")

async def purge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)

    try:
        member = await chat.get_member(user.id)
        if not member.can_delete_messages and member.status != 'creator':
            await update.message.reply_text("You don't have permission to delete messages.")
            return

        bot_member = await chat.get_member(context.bot.id)
        if not bot_member.can_delete_messages:
            await update.message.reply_text("I don't have permission to delete messages. Please make me an admin with this right.")
            return

    except BadRequest as e:
        await update.message.reply_text(f"Could not verify permissions: {e.message}")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to start purging from there up to your command.")
        return

    start_message_id = update.message.reply_to_message.message_id
    end_message_id = update.message.message_id

    message_ids_to_delete = list(range(start_message_id, end_message_id + 1))

    try:
        # Telegram allows deleting up to 100 messages at once
        deleted_count = 0
        for i in range(0, len(message_ids_to_delete), 100):
            chunk = message_ids_to_delete[i:i + 100]
            if await context.bot.delete_messages(chat_id=chat.id, message_ids=chunk):
                deleted_count += len(chunk)

        purge_feedback = await update.message.reply_text(f"{pe('check')} Purged {deleted_count} messages.", quote=False)
        await asyncio.sleep(5) # Wait 5 seconds
        await purge_feedback.delete() # Delete the feedback message
    except BadRequest as e:
        await update.message.reply_text(f"Error purging messages: {e.message}. Messages might be too old (over 48h).", quote=False)
    except Exception as e:
        await update.message.reply_text(f"An unexpected error occurred: {e}", quote=False)

@check_banned
@check_maintenance
async def admin_commands_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admin-only commands."""
    user = update.effective_user
    if not is_admin(user.id):
        return

    commands_list = [
        ("/admin", "Open admin dashboard"),
        ("/admincommands", "Show this list of admin commands"),
        ("/gameshistory", "View recent game results (paginated)"),
        ("/setbal", "Set a user's balance"),
        ("/withdrawinfo", "View withdrawal info"),
        ("/resetleaderboard", "Reset leaderboard data"),
        ("/setdaily", "Set daily bonus amount"),
        ("/dailyoff", "Disable daily bonus"),
        ("/dailyon", "Enable daily bonus"),
        ("/cancelall", "Cancel all active matches"),
        ("/stopall", "Stop all active games"),
        ("/settimeout", "Set round timeout for games"),
        ("/clear", "Clear a user's funds"),
        ("/clearall", "Clear all user funds"),
        ("/gamestatus", "Show game on/off statuses"),
        ("/export", "Export bot data"),
        ("/surprisedrop on/off", "Toggle surprise code drops"),
        ("/mute", "Mute a user in group"),
        ("/lockall", "Lock the group chat"),
        ("/unlockall", "Unlock the group chat"),
    ]

    # Add game toggle commands
    for gk in sorted(GAME_STATUS_MAP.keys()):
        commands_list.append((f"/{gk}on / /{gk}off", f"Enable/disable {gk} game"))

    msg = "\U0001f6e0 <b>Admin Commands</b>\n\n"
    for cmd, desc in commands_list:
        msg += f"<code>{cmd}</code> — {desc}\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def admin_dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    query = update.callback_query

    total_users = len(user_stats)
    total_balance = sum(get_total_balance_usd(uid) for uid in user_wallets)
    active_games = len([g for g in game_sessions.values() if g.get('status') == 'active'])
    pending_withdrawals = len([w for w in withdrawal_requests.values() if w.get('status') == 'pending'])
    banned_users_count = len(bot_settings.get('banned_users', []))
    temp_banned_users_count = len(bot_settings.get('tempbanned_users', []))

    text = (
        f"{pe('crown')} <b>Admin Dashboard</b> 👑\n\n"
        f"{pe('chart')} <b>Bot Stats:</b>\n"
        f"  - Total Users: {total_users}\n"
        f"  - Banned Users: {banned_users_count}\n"
        f"  - Temp Banned (Withdrawals): {temp_banned_users_count}\n"
        f"  - Total User Balance: ${total_balance:,.2f}\n"
        f"  - House Balance: ${bot_settings.get('house_balance', 0):,.2f}\n"
        f"  - Active Escrow Deals: {len(escrow_deals)}\n"
        f"  - Active Games: {active_games}\n"
        f"  - Pending Withdrawals: {pending_withdrawals}\n\n"
        f"{pe('settings')} <b>Bot Settings:</b>\n"
        f"  - Daily Bonus: ${bot_settings.get('daily_bonus_amount', 0.50):.2f}\n"
        f"  - Maintenance Mode: {'ON' if bot_settings.get('maintenance_mode') else 'OFF'}\n"
        f"  - Withdrawals: {'ON' if bot_settings.get('withdrawals_enabled', True) else 'OFF'}"
    )

    keyboard = [
        [InlineKeyboardButton("👥 User Management", callback_data="admin_users"), InlineKeyboardButton("Search User", callback_data="admin_search_user")],
        [InlineKeyboardButton("Pending Withdrawals", callback_data="admin_pending_withdrawals")],
        [InlineKeyboardButton("House Balance", callback_data="admin_set_house_balance"), InlineKeyboardButton("⚖️ Game Limits", callback_data="admin_limits")],
        [InlineKeyboardButton("Bot Settings", callback_data="admin_bot_settings"), InlineKeyboardButton("Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("Gift Codes", callback_data="admin_gift_codes"), InlineKeyboardButton("Active Games", callback_data="admin_active_games")],
        [InlineKeyboardButton("Export Data", callback_data="admin_export_data")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="back_to_main")]
    ]

    if query:
        if not is_admin(query.from_user.id): return
        await query.answer()
        await safe_edit_message(query, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

@check_banned
@check_maintenance
async def admin_bot_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id): return
    await query.answer()

    text = f"{pe('settings')} <b>Bot Settings</b>"
    keyboard = [
        [InlineKeyboardButton(f"Daily Bonus: ${bot_settings.get('daily_bonus_amount', 0.50):.2f}", callback_data="admin_set_daily_bonus")],
        [InlineKeyboardButton(f"Maintenance: {'ON' if bot_settings.get('maintenance_mode') else 'OFF'}", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton(f"Withdrawals: {'Enabled' if bot_settings.get('withdrawals_enabled', True) else 'Disabled'}", callback_data="admin_toggle_withdrawals")],
        [InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]
    ]
    await safe_edit_message(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

@check_banned
@check_maintenance
async def admin_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("This is an admin-only area.", show_alert=True)
        return

    await query.answer()
    action = query.data

    if action == "admin_dashboard":
        await admin_dashboard_command(update, context)
    elif action == "admin_users":
        await users_command(update, context)
    elif action == "admin_search_user":
        await query.edit_message_text("Please enter the @username or user ID of the user to search.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_SEARCH_USER
    elif action == "admin_bot_settings":
        await admin_bot_settings_callback(update, context)
    elif action == "admin_set_house_balance":
        await query.edit_message_text("Please enter the new house balance amount.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_SET_HOUSE_BALANCE
    elif action == "admin_limits":
        await query.edit_message_text("Select limit type to set:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Set Minimum Bet", callback_data="admin_limit_type_min")],
            [InlineKeyboardButton("Set Maximum Bet", callback_data="admin_limit_type_max")],
            [InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]
        ]))
        return ADMIN_LIMITS_CHOOSE_TYPE
    elif action == "admin_set_daily_bonus":
        await query.edit_message_text("Please enter the new daily bonus amount (e.g., 0.75).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_bot_settings")]]))
        return ADMIN_SET_DAILY_BONUS
    elif action == "admin_broadcast":
        await query.edit_message_text("Please send the message you want to broadcast to all users.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_BROADCAST_MESSAGE
    elif action == "admin_toggle_maintenance":
        bot_settings["maintenance_mode"] = not bot_settings.get("maintenance_mode", False)
        save_bot_state()
        await query.answer(f"Maintenance mode is now {'ON' if bot_settings['maintenance_mode'] else 'OFF'}")
        await admin_bot_settings_callback(update, context)
    elif action == "admin_toggle_withdrawals":
        bot_settings["withdrawals_enabled"] = not bot_settings.get("withdrawals_enabled", True)
        save_bot_state()
        await query.answer(f"Withdrawals are now {'ENABLED' if bot_settings['withdrawals_enabled'] else 'DISABLED'}")
        await admin_bot_settings_callback(update, context)
    elif action == "admin_gift_codes":
        await admin_gift_code_menu(update, context)
    # Removed: admin_ban_management - button removed from dashboard
    elif action == "admin_pending_withdrawals":
        await admin_pending_withdrawals(update, context)
    elif action == "admin_active_games":
        await admin_active_games(update, context)
    elif action == "admin_export_data":
        await admin_export_data_callback(update, context)

async def admin_ban_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage banned users"""
    query = update.callback_query
    await query.answer()

    banned_users = bot_settings.get('banned_users', [])
    temp_banned_users = bot_settings.get('tempbanned_users', [])

    text = f"{pe('cross')} <b>Ban Management</b>\n\n"
    text += f"<b>Permanently Banned Users:</b> {len(banned_users)}\n"
    if banned_users:
        for user_id in banned_users[:5]:  # Show first 5
            username = user_stats.get(user_id, {}).get('userinfo', {}).get('username', 'Unknown')
            text += f"  • @{username} (ID: {user_id})\n"
        if len(banned_users) > 5:
            text += f"  ... and {len(banned_users) - 5} more\n"

    text += f"\n<b>Withdrawal Banned Users:</b> {len(temp_banned_users)}\n"
    if temp_banned_users:
        for user_id in temp_banned_users[:5]:  # Show first 5
            username = user_stats.get(user_id, {}).get('userinfo', {}).get('username', 'Unknown')
            text += f"  • @{username} (ID: {user_id})\n"
        if len(temp_banned_users) > 5:
            text += f"  ... and {len(temp_banned_users) - 5} more\n"

    keyboard = [
        [InlineKeyboardButton("Ban User", callback_data="admin_ban_user_prompt"),
         InlineKeyboardButton(f"{pe('minus')} Unban User", callback_data="admin_unban_user_prompt")],
        [InlineKeyboardButton("Temp Ban (Withdrawals)", callback_data="admin_tempban_user_prompt"),
         InlineKeyboardButton("Remove Temp Ban", callback_data="admin_untempban_user_prompt")],
        [InlineKeyboardButton("View All Bans", callback_data="admin_view_all_bans")],
        [InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]
    ]

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_pending_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View and manage pending withdrawal requests"""
    query = update.callback_query
    await query.answer()

    pending = [w for w in withdrawal_requests.values() if w.get('status') == 'pending']

    text = f"{pe('withdraw')} <b>Pending Withdrawal Requests</b>\n\n"

    if not pending:
        text += "No pending withdrawals at the moment."
        keyboard = [[InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]]
    else:
        text += f"Total Pending: {len(pending)}\n\n"
        for w in pending[:5]:  # Show first 5
            text += (
                f"<b>ID:</b> <code>{w['id']}</code>\n"
                f"<b>User:</b> @{w['username']} (ID: {w['user_id']})\n"
                f"<b>Amount:</b> ${w['amount_usd']:.2f}\n"
                f"<b>Address:</b> <code>{w['withdrawal_address']}</code>\n"
                f"<b>Date:</b> {w['timestamp'][:10]}\n\n"
            )

        if len(pending) > 5:
            text += f"... and {len(pending) - 5} more\n\n"

        text += "Use the approval buttons on individual withdrawal notifications to process them."

        keyboard = [
            [InlineKeyboardButton("Refresh", callback_data="admin_pending_withdrawals")],
            [InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]
        ]

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_active_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View all active games"""
    query = update.callback_query
    await query.answer()

    active = [g for g in game_sessions.values() if g.get('status') == 'active']

    text = f"{pe('game')} <b>Active Games</b>\n\n"

    if not active:
        text += "No active games at the moment."
        keyboard = [[InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]]
    else:
        text += f"Total Active Games: {len(active)}\n\n"

        # Group by game type
        game_types = {}
        for game in active:
            game_type = game.get('game_type', 'unknown')
            game_types[game_type] = game_types.get(game_type, 0) + 1

        text += "<b>By Type:</b>\n"
        for game_type, count in game_types.items():
            text += f"  • {game_type.title()}: {count}\n"

        text += "\n<b>Recent Games:</b>\n"
        for game in active[:5]:  # Show first 5
            user_id = game.get('user_id', 'Unknown')
            username = user_stats.get(user_id, {}).get('userinfo', {}).get('username', 'Unknown')
            game_type = game.get('game_type', 'unknown')
            bet_amount = game.get('bet_amount', 0)
            text += f"  • {game_type.title()} - @{username} - ${bet_amount:.2f}\n"

        if len(active) > 5:
            text += f"  ... and {len(active) - 5} more\n"

        keyboard = [
            [InlineKeyboardButton("Refresh", callback_data="admin_active_games")],
            [InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]
        ]

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_export_data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all bot data"""
    query = update.callback_query
    await query.answer("Preparing data export... This may take a moment.", show_alert=True)

    try:
        # Create export data
        export_data = {
            "export_timestamp": str(datetime.now(timezone.utc)),
            "bot_settings": bot_settings,
            "total_users": len(user_stats),
            "total_balance": sum(get_total_balance_usd(uid) for uid in user_wallets),
            "user_stats": user_stats,
            "user_wallets": user_wallets,
            "active_games": len([g for g in game_sessions.values() if g.get('status') == 'active']),
            "escrow_deals": len(escrow_deals),
            "withdrawal_requests": len(withdrawal_requests),
        }

        file_path = os.path.join(DATA_DIR, f"bot_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(file_path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)

        # Send file to admin
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=open(file_path, "rb"),
            caption=f"{pe('chart')} Bot Data Export\n\nGenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            filename=os.path.basename(file_path)
        )

        # Clean up
        os.remove(file_path)

        await query.answer("Export completed! Check your DMs.", show_alert=True)

    except Exception as e:
        logging.error(f"Failed to export data: {e}")
        await query.answer(f"Export failed: {str(e)}", show_alert=True)

async def set_house_balance_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    try:
        amount = float(update.message.text)
        if amount < 0: raise ValueError
        bot_settings['house_balance'] = amount
        save_bot_state()
        await update.message.reply_text(f"{pe('house')} House balance set to ${amount:,.2f}.", parse_mode=ParseMode.HTML)
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a positive number.")
        return ADMIN_SET_HOUSE_BALANCE

    context.user_data.clear()
    await admin_dashboard_command(update, context)
    return ConversationHandler.END

async def admin_limits_choose_type_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.answer()

    limit_type = query.data.split('_')[-1] # min or max
    context.user_data['limit_type'] = limit_type

    all_games = [
        'blackjack', 'coin_flip', 'roulette', 'dice_roll', 'slots',
        'predict', 'tower', 'mines', 'keno', 'limbo', 'highlow',
        'pvp_dice', 'pvp_darts', 'pvp_goal', 'pvp_bowl',
        'emoji_darts', 'emoji_soccer', 'emoji_basket', 'emoji_bowling', 'emoji_slot'
    ]

    keyboard = []
    row = []
    for game in all_games:
        row.append(InlineKeyboardButton(game.replace('_', ' ').title(), callback_data=f"admin_limit_game_{game}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("Back", callback_data="admin_dashboard")])

    await query.edit_message_text(f"Select a game to set the <b>{limit_type}imum</b> bet for:",
                                  reply_markup=InlineKeyboardMarkup(keyboard),
                                  parse_mode=ParseMode.HTML)
    return ADMIN_LIMITS_CHOOSE_GAME

async def admin_limits_choose_game_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id): return ConversationHandler.END
    await query.answer()

    # Fixed: Extract game name properly (format: admin_limit_game_{game_name})
    game_name = query.data.replace('admin_limit_game_', '')
    context.user_data['limit_game'] = game_name
    limit_type = context.user_data['limit_type']

    await query.edit_message_text(f"Please enter the <b>{limit_type}imum</b> bet amount for <b>{game_name.replace('_', ' ').title()}</b>.",
                                  parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
    return ADMIN_LIMITS_SET_AMOUNT

async def admin_limits_set_amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END

    try:
        amount = float(update.message.text)
        if amount < 0: raise ValueError

        game_name = context.user_data['limit_game']
        limit_type = context.user_data['limit_type']

        if game_name not in bot_settings['game_limits']:
            bot_settings['game_limits'][game_name] = {}

        bot_settings['game_limits'][game_name][limit_type] = amount
        save_bot_state()

        await update.message.reply_text(f"{pe('check')} Set <b>{limit_type}imum</b> bet for <b>{game_name.replace('_', ' ').title()}</b> to <b>${amount:,.2f}</b>.",
                                      parse_mode=ParseMode.HTML)

    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a positive number.")
        return ADMIN_LIMITS_SET_AMOUNT

    context.user_data.clear()
    await admin_dashboard_command(update, context)
    return ConversationHandler.END

async def broadcast_win_to_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, game_name: str, bet_amount: float, win_amount: float, multiplier: float):
    """
    Broadcast a win notification to the configured channel.

    Args:
        context: Telegram context
        user_id: User ID of the winner
        username: Username of the winner
        game_name: Name of the game
        bet_amount: Amount bet
        win_amount: Amount won
        multiplier: Win multiplier
    """
    if not WIN_BROADCAST_CHANNEL_ID:
        logging.debug("WIN_BROADCAST_CHANNEL_ID not configured, skipping broadcast")
        return

    try:
        win_text = (
            f"{pe('win')} <b>BIG WIN!</b> 🎉\n\n"
            f"Player: @{username or 'Anonymous'}\n"
            f"Game: {game_name}\n"
            f"Bet: ${bet_amount:.2f}\n"
            f"Won: ${win_amount:.2f}\n"
            f"Multiplier: {multiplier:.2f}x"
        )

        await context.bot.send_message(
            chat_id=WIN_BROADCAST_CHANNEL_ID,
            text=win_text,
            parse_mode=ParseMode.HTML
        )
        logging.info(f"Win broadcast sent to channel for user {user_id}")
    except Exception as e:
        # Print explicitly to console for debugging
        print(f"BROADCAST ERROR: {e}")
        logging.error(f"Failed to broadcast win to channel: {e}")

async def set_daily_bonus_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    try:
        amount = float(update.message.text)
        if amount < 0: raise ValueError

        bot_settings['daily_bonus_amount'] = amount
        save_bot_state()
        await update.message.reply_text(f"Daily bonus amount set to ${amount:.2f}.")
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a positive number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_bot_settings")]]))
        return ADMIN_SET_DAILY_BONUS

    context.user_data.clear()
    # Fake a query to go back to the settings menu
    class FakeQuery:
        def __init__(self, user, message): self.from_user = user; self.message = message
        async def answer(self): pass
        async def edit_message_text(self, *args, **kwargs): await message.reply_text(*args, **kwargs)

    # --- FIX STARTS HERE ---
    # Create a fake update object to call the settings menu function
    fake_update = type('FakeUpdate', (), {'callback_query': FakeQuery(update.effective_user, update.message)})()
    await admin_bot_settings_callback(fake_update, context)
    return ConversationHandler.END

def _classify_broadcast_payload(message) -> dict:
    """Inspect an admin's input message and pick the right Bot API send.

    Returns a dict describing how each user should receive the broadcast:
    ``kind`` is one of ``text|photo|video|animation|document|copy``,
    plus the parameters needed for that send call.

    ``copy`` is the universal fallback — we copy the source message via
    ``bot.copy_message`` which preserves stickers, voice notes, polls,
    audio, and any other type without us needing a dedicated branch.
    """
    if message is None:
        return {"kind": "text", "text": ""}

    caption = message.caption or ""
    caption_entities = message.caption_entities

    # Photos: PTB exposes the sizes list, we want the largest.
    if message.photo:
        return {
            "kind": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": caption,
            "caption_entities": caption_entities,
        }
    if message.animation:  # GIFs come through as animation
        return {
            "kind": "animation",
            "file_id": message.animation.file_id,
            "caption": caption,
            "caption_entities": caption_entities,
        }
    if message.video:
        return {
            "kind": "video",
            "file_id": message.video.file_id,
            "caption": caption,
            "caption_entities": caption_entities,
            "supports_streaming": True,
        }
    if message.document:
        return {
            "kind": "document",
            "file_id": message.document.file_id,
            "caption": caption,
            "caption_entities": caption_entities,
        }
    if message.text:
        return {
            "kind": "text",
            "text": message.text,
            "entities": message.entities,
        }
    # Stickers / voice / audio / poll / etc — fall back to copy_message.
    return {
        "kind": "copy",
        "from_chat_id": message.chat_id,
        "message_id": message.message_id,
    }


async def _send_broadcast_payload(bot, chat_id: int, payload: dict):
    """Send one rendered broadcast payload to a single user.

    Returns the sent message on success, or ``None`` when the destination
    is not reachable (blocked / deactivated / chat not found). Raises
    on transient errors so the caller can decide whether to count it as
    a failure or retry. ``safe_send_message`` is used for the text path
    because that helper handles HTML parse-mode fall-back; media
    branches catch errors locally.
    """
    kind = payload.get("kind")
    if kind == "text":
        return await safe_send_message(
            bot, chat_id, payload.get("text") or "", parse_mode=ParseMode.HTML,
        )
    if kind == "photo":
        return await bot.send_photo(
            chat_id=chat_id,
            photo=payload["file_id"],
            caption=payload.get("caption") or None,
            parse_mode=ParseMode.HTML if not payload.get("caption_entities") else None,
            caption_entities=payload.get("caption_entities") or None,
        )
    if kind == "video":
        return await bot.send_video(
            chat_id=chat_id,
            video=payload["file_id"],
            caption=payload.get("caption") or None,
            parse_mode=ParseMode.HTML if not payload.get("caption_entities") else None,
            caption_entities=payload.get("caption_entities") or None,
            supports_streaming=payload.get("supports_streaming", True),
        )
    if kind == "animation":
        return await bot.send_animation(
            chat_id=chat_id,
            animation=payload["file_id"],
            caption=payload.get("caption") or None,
            parse_mode=ParseMode.HTML if not payload.get("caption_entities") else None,
            caption_entities=payload.get("caption_entities") or None,
        )
    if kind == "document":
        return await bot.send_document(
            chat_id=chat_id,
            document=payload["file_id"],
            caption=payload.get("caption") or None,
            parse_mode=ParseMode.HTML if not payload.get("caption_entities") else None,
            caption_entities=payload.get("caption_entities") or None,
        )
    if kind == "copy":
        return await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=payload["from_chat_id"],
            message_id=payload["message_id"],
        )
    # Unknown payload — be loud in logs but never crash the runner.
    logging.error("Broadcast: unknown payload kind %r", kind)
    return None


async def _run_broadcast(bot, admin_user_id: int, payload: dict, header_label: str = "Broadcast"):
    """Fan-out worker shared by both the dashboard flow and ``/broadcast``.

    Notifies the originating admin with a starting message, dispatches up
    to 25 sends concurrently (well under Telegram's ~30 msg/s global
    cap), pings progress every 500 sends, and posts a final summary.
    Permanent failures (blocked/deactivated) don't burn retries thanks
    to ``safe_send_message`` for the text path; media branches simply
    increment the failed counter on any exception.
    """
    all_user_ids = get_all_registered_user_ids()
    total = len(all_user_ids)
    sent = 0
    failed = 0
    sem = asyncio.Semaphore(25)

    async def _send_one(uid: int):
        nonlocal sent, failed
        async with sem:
            try:
                res = await _send_broadcast_payload(bot, uid, payload)
                if res is None:
                    failed += 1
                else:
                    sent += 1
            except Exception as e:
                failed += 1
                logging.debug(f"Broadcast send to {uid} failed: {e}")

    tasks = [asyncio.create_task(_send_one(uid)) for uid in all_user_ids]
    try:
        await bot.send_message(
            chat_id=admin_user_id,
            text=f"{header_label} starting → {total} users (kind={payload.get('kind')}).",
        )
    except Exception:
        pass
    for i in range(0, len(tasks), 500):
        batch = tasks[i:i + 500]
        await asyncio.gather(*batch, return_exceptions=True)
        try:
            await bot.send_message(
                chat_id=admin_user_id,
                text=(f"{header_label} progress: {sent + failed}/{total}  "
                      f"(ok={sent} fail={failed})"),
            )
        except Exception:
            pass
    try:
        await bot.send_message(
            chat_id=admin_user_id,
            text=(f"{header_label} finished.\n{pe('check')} Sent: {sent}\n"
                  f"{pe('cross')} Failed: {failed}"),
        )
    except Exception:
        pass


async def admin_broadcast_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Conversation step that fires when the admin replies to the
    "Send the message you want to broadcast" prompt.

    Now accepts text, photos, videos, animations (GIFs), documents, and
    falls back to ``copy_message`` for anything else (stickers, voice,
    audio, polls). The fan-out runs in a background task so the
    conversation state is freed immediately and the dashboard re-opens
    without waiting for thousands of sends to finish.
    """
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    payload = _classify_broadcast_payload(update.message)
    if payload.get("kind") == "text" and not (payload.get("text") or "").strip():
        await update.message.reply_text(
            "Empty broadcast — please send the message you want to broadcast."
        )
        return ADMIN_BROADCAST_MESSAGE
    admin_user_id = update.effective_user.id
    asyncio.create_task(
        _run_broadcast(context.bot, admin_user_id, payload, header_label="Broadcast"),
    )
    context.user_data.clear()
    await admin_dashboard_command(update, context)
    return ConversationHandler.END


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top-level admin ``/broadcast`` command.

    Two ways to invoke:

    1. Reply to ANY message with ``/broadcast`` — the bot copies that
       exact message to every registered user (text, photo, video, GIF,
       document, sticker, voice, …).
    2. ``/broadcast some text`` — sends plain text (HTML parse mode) to
       every registered user.

    Provided as a /reload-friendly alternative to the dashboard's
    Broadcast button so admins can ship media broadcasts without
    waiting for a process restart to update the conversation handler's
    filter.
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\U0001f6ab Admin only.")
        return

    reply = update.message.reply_to_message
    args_text = (update.message.text or "")
    # Strip the leading /broadcast (with optional @bot suffix) + any first whitespace.
    after_cmd = ""
    if args_text:
        parts = args_text.split(None, 1)
        if len(parts) == 2:
            after_cmd = parts[1]

    if reply is not None:
        payload = _classify_broadcast_payload(reply)
        # If the admin supplied caption text alongside a reply, override
        # text for text replies / caption for media replies.
        if after_cmd:
            if payload["kind"] == "text":
                payload["text"] = after_cmd
                payload["entities"] = None
            elif payload["kind"] in {"photo", "video", "animation", "document"}:
                payload["caption"] = after_cmd
                payload["caption_entities"] = None
            elif payload["kind"] == "copy":
                # copy_message doesn't support overriding caption easily;
                # tell the admin so they can re-send with the override.
                pass
    else:
        if not after_cmd.strip():
            await update.message.reply_text(
                "Usage:\n"
                "  /broadcast <text>     — send text to all users\n"
                "  Reply to a message with /broadcast — copy that message "
                "(text/photo/video/GIF/doc/sticker) to all users\n"
                "  Reply with /broadcast <override caption> — replace the "
                "caption while broadcasting media",
            )
            return
        payload = {"kind": "text", "text": after_cmd, "entities": None}

    admin_user_id = update.effective_user.id
    asyncio.create_task(
        _run_broadcast(context.bot, admin_user_id, payload, header_label="Broadcast"),
    )
    await update.message.reply_text(
        f"{pe('check')} Broadcast queued (kind={payload.get('kind')}). "
        "Progress + final tally will arrive in DM.",
    )

async def admin_search_user_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    username_or_id = update.message.text
    target_user_id = None

    if username_or_id.isdigit():
        target_user_id = int(username_or_id)
    else:
        target_user_id = username_to_userid.get(normalize_username(username_or_id))

    if not target_user_id or target_user_id not in user_stats:
        await update.message.reply_text("User not found. Please try again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_SEARCH_USER

    context.user_data['admin_search_target'] = target_user_id
    await display_admin_user_panel(update, context, target_user_id)
    return ConversationHandler.END

async def display_admin_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, page=0, history_type='matches'):
    stats = user_stats[target_user_id]
    userinfo = stats.get('userinfo', {})
    total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
    total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))

    is_banned = target_user_id in bot_settings.get("banned_users", [])
    is_temp_banned = target_user_id in bot_settings.get("tempbanned_users", [])

    text = (
        f"👤 <b>Admin Panel for @{userinfo.get('username','')}</b> (ID: <code>{target_user_id}</code>)\n"
        f"{pe('money')} Balance: ${get_total_balance_usd(target_user_id):.2f}\n"
        f"{pe('stats')} PnL: ${stats.get('pnl', 0.0):.2f}\n"
        f"{pe('balance')} Deposits: ${total_deposits:.2f} | 💸 Withdrawals: ${total_withdrawals:.2f}\n"
        f"🚫 Ban Status: {'Banned' if is_banned else 'Not Banned'}\n"
        f"⏳ Temp Ban (Withdrawal): {'Banned' if is_temp_banned else 'Not Banned'}\n"
    )

    # History section
    page_size = 5
    items = []
    if history_type == 'matches':
        items = [game_sessions.get(gid) for gid in reversed(stats.get("game_sessions", [])) if gid in game_sessions]
        text += "\n{pe('scroll')} <b>Match History:</b>\n"
    elif history_type == 'deposits':
        items = list(reversed(stats.get("deposits", [])))
        text += "\n{pe('scroll')} <b>Deposit History:</b>\n"
    elif history_type == 'withdrawals':
        items = list(reversed(stats.get("withdrawals", [])))
        text += "\n{pe('scroll')} <b>Withdrawal History:</b>\n"

    paginated_items = items[page*page_size : (page+1)*page_size]
    if not paginated_items:
        text += "No records found.\n"
    else:
        for item in paginated_items:
            if history_type == 'matches':
                game_type = item['game_type'].replace('_', ' ').title()
                win_status = "Win" if item.get('win') else "Loss"
                text += f" • {game_type} (${item['bet_amount']:.2f}) - {win_status} (<code>{item['id']}</code>)\n"
            elif history_type == 'deposits':
                 ts = datetime.fromisoformat(item['timestamp']).strftime('%Y-%m-%d')
                 text += f" • ${item['amount']:.2f} via {item['method']} ({ts})\n"
            elif history_type == 'withdrawals':
                 ts = datetime.fromisoformat(item['timestamp']).strftime('%Y-%m-%d')
                 text += f" • ${item['amount']:.2f} via {item['method']} ({ts})\n"

    # Keyboard
    keyboard = [
        [
            InlineKeyboardButton("Ban" if not is_banned else "Unban", callback_data=f"admin_user_{target_user_id}_ban"),
            InlineKeyboardButton("TempBan" if not is_temp_banned else "UnTempBan", callback_data=f"admin_user_{target_user_id}_tempban")
        ],
        [
            InlineKeyboardButton("Matches", callback_data=f"admin_user_{target_user_id}_history_matches_0"),
            InlineKeyboardButton("Deposits", callback_data=f"admin_user_{target_user_id}_history_deposits_0"),
            InlineKeyboardButton("Withdrawals", callback_data=f"admin_user_{target_user_id}_history_withdrawals_0")
        ]
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(f"{pe('left')}", callback_data=f"admin_user_{target_user_id}_history_{history_type}_{page-1}"))
    if (page+1)*page_size < len(items):
        nav_row.append(InlineKeyboardButton(f"{pe('arrow_right')}", callback_data=f"admin_user_{target_user_id}_history_{history_type}_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("Back to Admin Dashboard", callback_data="admin_dashboard")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

@check_banned
@check_maintenance
async def admin_user_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("This is an admin-only area.", show_alert=True)
        return

    await query.answer()

    parts = query.data.split('_')
    # admin_user_{user_id}_action
    # admin_user_{user_id}_history_{type}_{page}
    target_user_id = int(parts[2])
    action = parts[3]

    if action == 'ban':
        if target_user_id in bot_settings.get("banned_users", []):
            bot_settings["banned_users"].remove(target_user_id)
            await query.answer("User unbanned.")
        else:
            bot_settings.setdefault("banned_users", []).append(target_user_id)
            await query.answer("User banned.")
        save_bot_state()
    elif action == 'tempban':
        if target_user_id in bot_settings.get("tempbanned_users", []):
            bot_settings["tempbanned_users"].remove(target_user_id)
            await query.answer("User's withdrawal restrictions lifted.")
        else:
            bot_settings.setdefault("tempbanned_users", []).append(target_user_id)
            await query.answer("User temporarily banned from withdrawals.")
        save_bot_state()
    elif action == 'history':
        history_type = parts[4]
        page = int(parts[5])
        await display_admin_user_panel(update, context, target_user_id, page, history_type)
        return

    await display_admin_user_panel(update, context, target_user_id)

@check_banned
@check_maintenance
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_lang = get_user_lang(user.id)

    privacy_on = user_stats.get(user.id, {}).get("privacy_mode", False)
    privacy_style = 'success' if privacy_on else 'danger'
    privacy_label = "Privacy Mode: ON" if privacy_on else "Privacy Mode: OFF"

    keyboard = [
        [apply_button_style(InlineKeyboardButton("Active Currency", callback_data="settings_currency"), 'primary', peb('diamond'))],
        [apply_button_style(InlineKeyboardButton(get_text("language", user_lang), callback_data="settings_language"), 'primary', peb('globe'))],
        [apply_button_style(InlineKeyboardButton(get_text("withdrawal_address", user_lang), callback_data="settings_withdrawal"), 'primary', peb('wallet'))],
        [apply_button_style(InlineKeyboardButton(privacy_label, callback_data="settings_privacy_toggle"), privacy_style, peb('lock'))],
        [apply_button_style(InlineKeyboardButton(get_text("back", user_lang), callback_data="back_to_main"), 'danger', peb('back'))]
    ]

    active_coin = get_active_currency(user.id)
    coin_pe = pe({'USDT':'balance','BTC':'money','ETH':'gem','SOL':'coin','BNB':'diamond','TRX':'diamond','LTC':'coin'}.get(active_coin, 'gem'))
    user_language = user_stats[user.id].get("userinfo", {}).get("language", "en")
    language_name = LANGUAGES.get(user_language, {}).get("language_name", "English")
    withdrawal_address = user_stats[user.id].get("withdrawal_address")
    withdrawal_status = f"<b>{get_text('withdrawal_address', user_lang)}:</b> {pe('check')} Set" if withdrawal_address else f"<b>{get_text('withdrawal_address', user_lang)}:</b> {pe('cross')} Not Set"
    privacy_status = f"{pe('lock')} <b>Privacy Mode:</b> {'ON' if privacy_on else 'OFF'}"

    await safe_edit_message(
        query,
        get_text("settings_menu", user_lang) + f"\n\n"
        f"<b>Active Currency:</b> {coin_pe} {active_coin}\n"
        f"<b>Current Language:</b> {language_name}\n"
        f"{withdrawal_status}\n"
        f"{privacy_status}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    user = query.from_user
    user_lang = get_user_lang(user.id)
    action = query.data.split('_')[1] if len(query.data.split('_')) > 1 else None

    if action == "currency":
        current_currency = get_active_currency(user.id)
        keyboard = []
        for curr in SUPPORTED_CRYPTOS:
            emoji_key = {'USDT':'usdt','BTC':'btc','ETH':'eth','SOL':'sol','BNB':'bnb','TRX':'trx','LTC':'ltc','USDC':'usdc','TON':'ton','BASE':'base'}.get(curr, 'coin')
            text = f"{curr}"
            if curr == current_currency:
                text += " ✓"
            keyboard.append([apply_button_style(InlineKeyboardButton(text, callback_data=f"setcurrency_{curr}"), 'primary', peb(emoji_key))])
        keyboard.append([apply_button_style(InlineKeyboardButton(get_text("back", user_lang), callback_data="main_settings"), 'danger', peb('back'))])

        await safe_edit_message(query,
            f"{pe('diamond')} <b>Select Active Currency</b>\n\n"
            "Choose your active crypto currency.\n"
            "All bets, tips, and games will use this currency.\n"
            f"{pe('warning')} Your balance in each coin is separate (segregated wallets).",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if action == "language":
        await ensure_user_in_wallets(user.id, user.username, context=context)
        current_language = user_stats[user.id].get("userinfo", {}).get("language", "en")
        keyboard = []
        for lang_code, lang_data in LANGUAGES.items():
            text = lang_data.get("language_name", lang_code)
            if lang_code == current_language:
                text += " ✓"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"lang_{lang_code}")])
        keyboard.append([InlineKeyboardButton(get_text("back", user_lang), callback_data="main_settings")])

        await safe_edit_message(query,
            get_text("select_language", user_lang),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if action == "privacy":
        await ensure_user_in_wallets(user.id, user.username, context=context)
        current = user_stats.get(user.id, {}).get("privacy_mode", False)
        user_stats[user.id]["privacy_mode"] = not current
        save_user_data(user.id)
        await settings_command(update, context)
        return

    if action == "withdrawal":
        withdrawal_address = user_stats[user.id].get("withdrawal_address")
        if withdrawal_address:
            # Show current address and option to change
            await safe_edit_message(query,
                f"{pe('wallet')} <b>Withdrawal Address</b>\n\n"
                f"<b>Current Address:</b>\n<code>{withdrawal_address}</code>\n\n"
                f"This is your USDT-BEP20 withdrawal address.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Change Address", callback_data="settings_withdrawal_change")],
                    [InlineKeyboardButton("Back to Settings", callback_data="main_settings")]
                ])
            )
            return
        else:
            # Ask user to set withdrawal address
            await safe_edit_message(query,
                f"{pe('wallet')} <b>Set Withdrawal Address</b>\n\n"
                "Please enter your USDT-BEP20 withdrawal address.\n"
                f"{pe('warning')} Make sure it's a valid BEP20 address.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="main_settings")]])
            )
            return SETTINGS_WITHDRAWAL_ADDRESS

async def set_withdrawal_address_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    address = update.message.text.strip()

    if not is_valid_bep20_address(address):
        await update.message.reply_text(
            "❌ Invalid USDT-BEP20 address. Please enter a valid address starting with 0x.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="main_settings")]])
        )
        return SETTINGS_WITHDRAWAL_ADDRESS

    # Save the withdrawal address
    user_stats[user.id]["withdrawal_address"] = address
    save_user_data(user.id)

    await update.message.reply_text(
        f"{pe('check')} <b>Withdrawal Address Set!</b>\n\n"
        f"Your withdrawal address has been saved:\n<code>{address}</code>\n\n"
        f"You can now use the withdrawal feature. Use /start to return to the main menu.",
        parse_mode=ParseMode.HTML
    )

    # Clear user data to end conversation properly
    context.user_data.clear()
    return ConversationHandler.END

async def admin_gift_code_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = f"{pe('gift')} <b>Gift Code Management</b>\n\nExisting codes:\n"
    if not gift_codes:
        text += "No active gift codes."
    else:
        for code, data in gift_codes.items():
            wager_req = data.get("wager_requirement", 0)
            wager_text = f" (Wager: ${wager_req:.0f})" if wager_req > 0 else ""
            text += f"• <code>{code}</code>: ${data['amount']:.2f}, {data['claims_left']}/{data['total_claims']} left{wager_text}\n"

    keyboard = [
        [InlineKeyboardButton("Create New Code", callback_data="admin_gift_create")],
        [InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_gift_code_create_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter the amount (e.g., 5.50) for the new gift code.",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_gift_codes")]]))
    return ADMIN_GIFT_CODE_AMOUNT

async def admin_gift_code_create_step2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0: raise ValueError
        context.user_data['gift_code_amount'] = amount
        await update.message.reply_text("Amount set. Now enter the maximum number of times this code can be claimed.",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_gift_codes")]]))
        return ADMIN_GIFT_CODE_CLAIMS
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a positive number.")
        return ADMIN_GIFT_CODE_AMOUNT

async def admin_gift_code_create_step3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        claims = int(update.message.text)
        if claims <= 0: raise ValueError
        context.user_data['gift_code_claims'] = claims
        await update.message.reply_text(
            "Number of claims set. Now enter the wager requirement (in $).\n\n"
            "Enter <b>0</b> for no wager requirement, or any positive number (e.g., 100 means users must have wagered $100 to claim).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_gift_codes")]]),
            parse_mode=ParseMode.HTML
        )
        return ADMIN_GIFT_CODE_WAGER
    except ValueError:
        await update.message.reply_text("Invalid number. Please enter a positive integer.")
        return ADMIN_GIFT_CODE_CLAIMS

async def admin_gift_code_create_step4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        wager_requirement = float(update.message.text)
        if wager_requirement < 0: raise ValueError

        amount = context.user_data['gift_code_amount']
        claims = context.user_data['gift_code_claims']

        code = f"GIFT-{''.join(_secure_choices(string.ascii_uppercase + string.digits, k=8))}"
        gift_codes[code] = {
            "amount": amount,
            "total_claims": claims,
            "claims_left": claims,
            "wager_requirement": wager_requirement,
            "claimed_by": [],
            "created_by": update.effective_user.id,
            "created_at": str(datetime.now(timezone.utc))
        }
        save_gift_code(code)

        wager_text = f"Wager requirement: ${wager_requirement:.2f}" if wager_requirement > 0 else "No wager requirement"

        # Build gift codes list for display
        codes_text = f"{pe('gift')} <b>Gift Code Management</b>\n\nExisting codes:\n"
        if not gift_codes:
            codes_text += "No active gift codes."
        else:
            for gift_code, data in gift_codes.items():
                wager_req = data.get("wager_requirement", 0)
                wager_text_item = f" (Wager: ${wager_req:.0f})" if wager_req > 0 else ""
                codes_text += f"• <code>{gift_code}</code>: ${data['amount']:.2f}, {data['claims_left']}/{data['total_claims']} left{wager_text_item}\n"

        keyboard = [
            [InlineKeyboardButton("Create New Code", callback_data="admin_gift_create")],
            [InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")]
        ]

        await update.message.reply_text(
            f"{pe('check')} Gift code created successfully!\n\n"
            f"Code: <code>{code}</code>\n"
            f"Amount: ${amount:.2f}\n"
            f"Uses: {claims}\n"
            f"{wager_text}\n\n"
            f"{codes_text}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data.clear()

        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Invalid number. Please enter 0 or a positive number.")
        return ADMIN_GIFT_CODE_WAGER

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('clear', clear_command, block=False))
    app.add_handler(CommandHandler('timeout', timeout_command, block=False))
    app.add_handler(CommandHandler('clearall', clearall_command, block=False))
    app.add_handler(CommandHandler('cancel', cancel_command, block=False))
    app.add_handler(CommandHandler('cashout', cashout_command, block=False))
    app.add_handler(CommandHandler('resume', resume_command, block=False))
    app.add_handler(CommandHandler('stop', stop_command, block=False))
    app.add_handler(CommandHandler('kick', kick_command, block=False))
    app.add_handler(CommandHandler('promote', promote_command, block=False))
    app.add_handler(CommandHandler('pin', pin_command, block=False))
    app.add_handler(CommandHandler('purge', purge_command, block=False))
    app.add_handler(CommandHandler('admin', admin_dashboard_command, block=False))
    app.add_handler(CommandHandler('admincommands', admin_commands_list, block=False))
    app.add_handler(CommandHandler('gamestatus', game_status_command, block=False))
    app.add_handler(CommandHandler('broadcast', broadcast_command, block=False))
    app.add_handler(CallbackQueryHandler(settings_callback_handler, pattern='^settings_', block=False))
    app.add_handler(CallbackQueryHandler(admin_actions_callback, pattern='^admin_(dashboard|users|bot_settings|toggle_maintenance|broadcast|set_house_balance|limits|gift_codes|toggle_withdrawals|pending_withdrawals|active_games|export_data)$', block=False))
    app.add_handler(CallbackQueryHandler(admin_user_search_callback, pattern='^admin_user_', block=False))

