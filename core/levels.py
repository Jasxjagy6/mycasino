"""Auto-split from bot.py — core.levels."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def _get_total_wager(user_id: int) -> float:
    """Get total wager from user_stats (JSON) instead of SQL."""
    if user_id not in user_stats:
        return 0.0
    return user_stats[user_id].get("bets", {}).get("amount", 0.0)

def _current_and_next_level(total_wager: float):
    """Find current level by highest threshold <= total_wager."""
    curr_idx = -1
    for i, (name, threshold, bonus) in enumerate(ALL_LEVELS):
        if total_wager >= threshold:
            curr_idx = i
        else:
            break

    current = ALL_LEVELS[curr_idx] if curr_idx >= 0 else ("None", 0, 0)
    next_idx = curr_idx + 1
    next_level = ALL_LEVELS[next_idx] if next_idx < len(ALL_LEVELS) else None
    return current, next_level

def _progress_bar(current, target, length=10):
    """Generate a visual progress bar."""
    if target == 0: return "▬" * length
    pct = min(1.0, current / target)
    fill = int(pct * length)
    return "🔘" * fill + "▬" * (length - fill)

def get_user_level(user_id: int):
    """Determines a user's current level based on their total wagered amount.
    Returns a dict compatible with old code: {level, name, wager_required, reward, rakeback_percentage}"""
    total_wager = _get_total_wager(user_id)
    current, next_level = _current_and_next_level(total_wager)

    # Determine the tier for rakeback
    level_name = current[0]  # e.g. "Bronze I"
    tier = level_name.split()[0] if level_name != "None" else "Bronze"
    rakeback = TIER_RAKEBACK.get(tier, 1)

    # Find level index in ALL_LEVELS
    level_idx = -1
    for i, (name, wager, bonus) in enumerate(ALL_LEVELS):
        if name == level_name:
            level_idx = i
            break

    return {
        "level": level_idx,
        "name": level_name,
        "wager_required": current[1],
        "reward": current[2],
        "rakeback_percentage": rakeback
    }

async def check_and_award_level_up(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Checks for level-up, awards reward, and notifies the user."""
    if user_id not in user_stats:
        return

    total_wager = _get_total_wager(user_id)
    claimed_rewards = user_stats[user_id].get("claimed_level_rewards", [])

    for level_name, level_wager, bonus in ALL_LEVELS:
        if total_wager < level_wager:
            break  # Levels are ordered, no need to check further
        if level_name not in claimed_rewards:
            # Award bonus
            credit_wallet(user_id, bonus)
            user_stats[user_id].setdefault("claimed_level_rewards", []).append(level_name)
            save_user_data(user_id)

            # Notify the user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(f"{pe('win')} <b>Level Up!</b> {pe('win')}\n\n"
                          f"Congratulations! You have reached <b>{level_name}</b>.\n"
                          f"You have been awarded a one-time bonus of <b>${bonus:.2f}</b>!"),
                    parse_mode=ParseMode.HTML
                )
            except (BadRequest, Forbidden):
                logging.warning(f"Could not send level-up notification to user {user_id}")

@check_banned
@check_maintenance
async def level_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    total_wager = _get_total_wager(user.id)
    current, next_level = _current_and_next_level(total_wager)
    current_name = current[0]
    tier = current_name.split()[0] if current_name != "None" else "Bronze"
    rakeback = TIER_RAKEBACK.get(tier, 1)
    tier_emoji = TIER_EMOJI.get(tier, "🦄")

    text = f"{tier_emoji} <b>Your Level: {current_name}</b>\n\n"

    if next_level is None:
        text += f"{pe('trophy')} You have reached the maximum level!\n"
        text += f"{pe('money')} Total Wagered: ${total_wager:,.2f}"
    else:
        next_name, next_wager, next_bonus = next_level
        next_tier = next_name.split()[0]
        next_emoji = TIER_EMOJI.get(next_tier, "🦄")
        progress = total_wager - current[1]
        total_for_level = next_wager - current[1]

        bar = _progress_bar(total_wager, next_wager)
        percentage = (progress / total_for_level * 100) if total_for_level > 0 else 100

        text += f"<b>Progress to {next_emoji} {next_name}:</b>\n"
        text += f"{bar} ({percentage:.1f}%)\n\n"
        text += f"{pe('money')} <b>Wagered:</b> ${total_wager:,.2f} / ${next_wager:,.2f}\n"
        text += f"{pe('chart')} <b>Wager Needed:</b> ${next_wager - total_wager:,.2f}\n"
        text += f"{pe('withdraw')} <b>Rakeback:</b> {rakeback}%"

    keyboard = [
        [InlineKeyboardButton("View All Levels", callback_data="levels_Bronze")],
        [InlineKeyboardButton("Back to More", callback_data="main_more")]
    ]

    if from_callback:
        await safe_edit_message(update.callback_query, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        sent_message = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        # Set ownership after sending
        set_menu_owner(sent_message, user.id)

@check_banned
@check_maintenance
async def level_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False, tier="Bronze"):
    """Show levels for a specific tier with pagination"""
    # Handle both command and callback query
    if update.callback_query:
        from_callback = True
        # Answer callback immediately to remove loading spinner
        await update.callback_query.answer()
        # Extract tier from callback data if present
        if update.callback_query.data and update.callback_query.data.startswith("levels_"):
            tier = update.callback_query.data.replace("levels_", "")

    if tier not in LEVELS_DATA:
        tier = "Bronze"

    user = update.effective_user
    total_wager = _get_total_wager(user.id) if user else 0.0

    tier_emoji = TIER_EMOJI.get(tier, "🦄")
    text = f"{tier_emoji} <b>{tier} Levels</b> {tier_emoji}\n\n"
    rakeback = TIER_RAKEBACK.get(tier, 1)
    text += f"{pe('withdraw')} Rakeback Rate: {rakeback}%\n\n"

    for name, wager, bonus in LEVELS_DATA[tier]:
        reached = "✅" if total_wager >= wager else "⬜"
        text += (f"{reached} {tier_emoji} <b>{name}</b>\n"
                 f"  Wager: ${wager:,} | Bonus: ${bonus}\n")

    # Build navigation keyboard
    keyboard = []
    nav_row = []
    nav = LEVEL_NAVIGATION[tier]
    if nav["prev"]:
        nav_row.append(apply_button_style(InlineKeyboardButton(" ", callback_data=f"levels_{nav['prev']}"), 'primary', peb('left')))
    if nav["next"]:
        nav_row.append(apply_button_style(InlineKeyboardButton(" ", callback_data=f"levels_{nav['next']}"), 'primary', peb('arrow_right')))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("Back to My Level", callback_data="main_level")])

    reply_markup = create_styled_keyboard(keyboard)

    if from_callback:
        await safe_edit_message(update.callback_query, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        # Set ownership after editing
        set_menu_owner(update.callback_query.message, update.callback_query.from_user.id)
    else:
        sent_message = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        # Set ownership after sending
        if update.effective_user:
            set_menu_owner(sent_message, update.effective_user.id)

