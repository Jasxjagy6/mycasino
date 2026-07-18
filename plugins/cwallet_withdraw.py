"""CWallet withdrawal via @cctip_bot.

User requests a withdrawal with /withdraw <amount> usdt in a group.
The bot confirms @Ittz_surajj is present and admin, then the session
account replies to the user's withdraw message with "cc <amount> USDT"
to trigger @cctip_bot to tip them.
"""
from __future__ import annotations
from core.foundation import *

import logging
import re

CWALLET_WITHDRAW_MIN = 0.01
CWALLET_WITHDRAW_MAX = 50.0
CWALLET_WITHDRAW_FEE_FLAT = 0.10
CWALLET_WITHDRAW_FEE_PCT = 0.01
_session_user_id: int | None = None
SESSION_USERNAME = CWALLET_RECEIVE_USERNAME


async def _get_session_user_id(context) -> int | None:
    global _session_user_id
    if _session_user_id is not None:
        return _session_user_id
    client = await _get_session_client()
    if client:
        try:
            entity = await client.get_entity(SESSION_USERNAME)
            _session_user_id = entity.id
            logging.info(f"CWallet session user resolved: @{SESSION_USERNAME} = {_session_user_id}")
            return _session_user_id
        except Exception as e:
            logging.error(f"CWallet: failed to resolve @{SESSION_USERNAME} via Telethon: {e}")
    try:
        chat = await context.bot.get_chat(f"@{SESSION_USERNAME}")
        _session_user_id = chat.id
        logging.info(f"CWallet session user resolved via PTB: @{SESSION_USERNAME} = {_session_user_id}")
        return _session_user_id
    except Exception as e:
        logging.error(f"CWallet: failed to resolve @{SESSION_USERNAME}: {e}")
        return None

WITHDRAW_PATTERN = re.compile(
    r'^/withdraw\s+([\d.]+)\s+(usdt)\s*(?:cctip)?\s*$',
    re.IGNORECASE,
)


async def _get_session_client():
    from plugins.cwallet_monitor import cwallet_client
    return cwallet_client


@check_banned
@check_maintenance
async def cwallet_withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or chat.type not in ('group', 'supergroup'):
        await update.message.reply_text(
            f"{pe('cross')} This command can only be used in groups.",
            parse_mode=ParseMode.HTML,
        )
        return

    msg_text = update.message.text.strip()
    m = WITHDRAW_PATTERN.match(msg_text)
    if not m:
        await update.message.reply_text(
            f"{pe('warning')} <b>Usage:</b>\n"
            f"<code>/withdraw &lt;amount&gt; usdt</code>\n\n"
            f"{pe('lightning')} Example: <code>/withdraw 10 usdt</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    amount = float(m.group(1))
    currency = m.group(2).upper()

    if amount < CWALLET_WITHDRAW_MIN or amount > CWALLET_WITHDRAW_MAX:
        await update.message.reply_text(
            f"{pe('cross')} <b>Invalid amount.</b>\n\n"
            f"{pe('dollar')} Min: <code>${CWALLET_WITHDRAW_MIN:.2f}</code>\n"
            f"{pe('dollar')} Max: <code>${CWALLET_WITHDRAW_MAX:.2f}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    allowed, wager_err = check_withdrawal_limit(user.id, amount)
    if not allowed:
        await update.message.reply_text(
            f"{pe('cross')} <b>Withdrawal blocked.</b>\n\n{wager_err}",
            parse_mode=ParseMode.HTML,
        )
        return

    wallet = ensure_wallet_dict(user.id)
    balance = wallet.get(currency, 0.0)
    if balance < amount:
        await update.message.reply_text(
            f"{pe('cross')} <b>Insufficient balance.</b>\n\n"
            f"{pe('wallet')} Your {currency} balance: <code>{balance:.2f}</code>\n"
            f"{pe('money')} Requested: <code>{amount:.2f}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    sess_uid = await _get_session_user_id(context)
    if sess_uid is None:
        await update.message.reply_text(
            f"{pe('cross')} <b>Cannot process withdrawal.</b>\n\n"
            f"Could not resolve @{SESSION_USERNAME}.",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        member = await context.bot.get_chat_member(chat.id, sess_uid)
        if member.status not in ('member', 'administrator', 'creator'):
            raise ValueError("not in group")
        is_admin = member.status in ('administrator', 'creator')
        if not is_admin:
            await update.message.reply_text(
                f"{pe('warning')} <b>Cannot process withdrawal.</b>\n\n"
                f"@{SESSION_USERNAME} is in this group but is <b>not an admin</b>.\n"
                f"Please make @{SESSION_USERNAME} an admin and try again.",
                parse_mode=ParseMode.HTML,
            )
            return
    except Exception as e:
        logging.warning(f"CWallet withdraw: session user check failed: {e}")
        await update.message.reply_text(
            f"{pe('cross')} <b>Cannot process withdrawal.</b>\n\n"
            f"@{SESSION_USERNAME} is <b>not present</b> in this group.\n"
            f"Add @{SESSION_USERNAME} as an admin to enable withdrawals here.",
            parse_mode=ParseMode.HTML,
        )
        return

    fee = CWALLET_WITHDRAW_FEE_FLAT + amount * CWALLET_WITHDRAW_FEE_PCT
    receive = amount - fee
    confirm_btn = apply_button_style(
        InlineKeyboardButton(
            f"Confirm {amount} USDT",
            callback_data=f"cw_wd_c_{user.id}_{amount}_{currency}",
        ),
        'success', peb('check'),
    )
    cancel_btn = apply_button_style(
        InlineKeyboardButton(
            "Cancel",
            callback_data=f"cw_wd_x_{user.id}",
        ),
        'danger', peb('cross'),
    )
    context.user_data['cw_wd_reply_msg_id'] = update.message.message_id
    keyboard = create_styled_keyboard([[confirm_btn, cancel_btn]])
    await update.message.reply_text(
        f"{pe('wallet')} <b>CWallet Withdrawal</b>\n\n"
        f"{pe('user')} User: @{user.username or user.first_name}\n"
        f"{pe('money')} Amount: <code>{amount} {currency}</code>\n"
        f"{pe('dollar')} Fee: <code>${fee:.2f}</code> ($0.10 + 1%)\n"
        f"{pe('gift')} You receive: <code>{receive:.2f} {currency}</code>\n"
        f"{pe('rocket')} Method: @cctip_bot tip\n\n"
        f"@{SESSION_USERNAME} will tip you in this group.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def cwallet_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    if data.startswith("cw_wd_c_"):
        parts = data.split("_")
        target_uid = int(parts[3])
        amount = float(parts[4])
        currency = parts[5]
    elif data.startswith("cw_wd_x_"):
        target_uid = int(data.split("_")[3])
        amount = 0
        currency = "USDT"
    else:
        return

    if user.id != target_uid:
        await query.answer("This is not your withdrawal request.", show_alert=True)
        return

    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    if data.startswith("cw_wd_x_"):
        await query.edit_message_text(
            f"{pe('cross')} Withdrawal cancelled.",
            parse_mode=ParseMode.HTML,
        )
        return

    chat = update.effective_chat
    if not chat:
        return

    allowed, wager_err = check_withdrawal_limit(user.id, amount)
    if not allowed:
        await query.edit_message_text(
            f"{pe('cross')} <b>Withdrawal blocked.</b>\n\n{wager_err}",
            parse_mode=ParseMode.HTML,
        )
        return

    wallet = ensure_wallet_dict(user.id)
    balance = wallet.get(currency, 0.0)
    if balance < amount:
        await query.edit_message_text(
            f"{pe('cross')} <b>Insufficient balance.</b>\n"
            f"Your {currency} balance: <code>{balance:.2f}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    client = await _get_session_client()
    if not client:
        await query.edit_message_text(
            f"{pe('cross')} <b>Withdrawal system unavailable.</b>\n"
            f"Please try again later.",
            parse_mode=ParseMode.HTML,
        )
        return

    fee = CWALLET_WITHDRAW_FEE_FLAT + amount * CWALLET_WITHDRAW_FEE_PCT
    net_amount = amount - fee
    wallet[currency] = round(balance - amount, 8)
    save_user_data(user.id)

    reply_msg_id = context.user_data.get('cw_wd_reply_msg_id')
    tip_cmd = f"cc {net_amount} USDT"
    try:
        await client.send_message(chat.id, tip_cmd, reply_to=reply_msg_id)
        logging.info(
            f"CWallet withdraw: session sent '{tip_cmd}' in chat {chat.id} "
            f"for user {user.id} (@{user.username})"
        )
        await query.edit_message_text(
            f"{pe('check')} <b>Withdrawal Initiated!</b>\n\n"
            f"{pe('money')} <code>{amount} {currency}</code>\n"
            f"{pe('dollar')} Fee: <code>${fee:.2f}</code>\n"
            f"{pe('gift')} You receive: <code>{net_amount:.2f} {currency}</code>\n"
            f"{pe('user')} To: @{user.username or user.first_name}\n"
            f"{pe('lightning')} @{SESSION_USERNAME} is tipping you now via @cctip_bot.\n"
            f"Please check the group chat for the confirmation.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        wallet[currency] = round(wallet.get(currency, 0.0) + amount, 8)
        save_user_data(user.id)
        logging.error(f"CWallet withdraw: session send failed: {e}", exc_info=True)
        await query.edit_message_text(
            f"{pe('cross')} <b>Withdrawal failed.</b>\n"
            f"Your balance has been restored.\n"
            f"Error: {e}",
            parse_mode=ParseMode.HTML,
        )


REMOVEWAGER_PATTERN = re.compile(r'^/removewager\s+(\d+)\s*$')


async def cwallet_removewager_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    m = REMOVEWAGER_PATTERN.match(update.message.text.strip())
    if not m:
        await update.message.reply_text(
            f"{pe('warning')} Usage: <code>/removewager &lt;user_id&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    target_id = int(m.group(1))
    if target_id not in user_stats:
        await update.message.reply_text(
            f"{pe('cross')} User <code>{target_id}</code> not found in stats.",
            parse_mode=ParseMode.HTML,
        )
        return
    user_stats[target_id]["unwagered_deposit"] = 0.0
    user_stats[target_id]["unwagered_tips"] = 0.0
    save_user_data(target_id)
    await update.message.reply_text(
        f"{pe('check')} Wager requirements removed for user <code>{target_id}</code>.",
        parse_mode=ParseMode.HTML,
    )
