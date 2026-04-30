"""Auto-split from bot.py — core.achievements."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

@check_banned
@check_maintenance
async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_lang = get_user_lang(user.id)
    stats = user_stats[user.id]
    user_achievements = stats.get("achievements", [])

    if not user_achievements:
        text = get_text("no_achievements", user_lang)
    else:
        text = f"{pe('trophy')} <b>{get_text('achievements', user_lang)}</b> 🏅\n\n"
        for ach_id in user_achievements:
            ach_data = ACHIEVEMENTS.get(ach_id)
            if ach_data:
                text += f"{ach_data['emoji']} <b>{ach_data['name']}</b> - <i>{ach_data['description']}</i>\n"

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Back to More", callback_data="main_more")]]) if from_callback else None

    if from_callback:
        await safe_edit_message(update.callback_query, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        sent_message = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        # Set menu owner when sending with keyboard
        if reply_markup:
            set_menu_owner(sent_message, user.id)

