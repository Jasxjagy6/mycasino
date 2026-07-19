"""Auto-split from bot.py — plugins.cwallet_deposit.

SECURITY: This module ONLY processes group messages verified to be
sent directly by the CWallet bot (@cctip_bot).  Forwarded messages,
private messages, and messages from any other sender are ignored.
Sender identity is verified by Telegram user_id, never by username.
"""
from __future__ import annotations
from core.foundation import *

import re
import json
import hmac
import hashlib
import logging
from datetime import datetime

CWALLET_BOT_USERID: int | None = None

TIP_PATTERNS = [
    re.compile(
        r'(?:✅|🎁)?\s*@?(\w+)\s+(?:sent|tipped)\s+([\d.]+)\s+(\w+)\s+to\s+@?(\w+)',
        re.IGNORECASE
    ),
    re.compile(
        r'(?:✅|🎁)?\s*[Tt]ip\s+of\s+([\d.]+)\s+(\w+)\s+sent\s+to\s+@?(\w+)\s+by\s+@?(\w+)',
        re.IGNORECASE
    ),
    re.compile(
        r'@?(\w+)\s+tip\s+details:.*?\n\s*(\w+)\s+\+?([\d.]+)\s+@?(\w+)',
        re.IGNORECASE | re.DOTALL
    ),
    re.compile(
        r'\[(\w+)\]\(tg://user\?id=\d+\)\s+tip\s+details:.*?\n\s*\*\*(\w+)\*\*\s+`\+?([\d.]+)`\s+\[(\w+)\]\(tg://user\?id=\d+\)',
        re.IGNORECASE | re.DOTALL
    ),
]


def _resolve_cwallet_bot_username() -> str:
    return (CWALLET_BOT_USERNAME or 'cctip_bot').lower().lstrip('@')


def parse_tip_message(text: str) -> dict | None:
    if not text:
        return None
    for pat in TIP_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        groups = m.groups()
        if len(groups) == 4:
            text_lower = text.lower()
            # pattern 3: "sender tip details:\ncurrency +amount receiver"
            if 'tip details' in text_lower:
                sender, currency, amount, receiver = groups
            # pattern 2: "Tip of X currency sent to @receiver by @sender"
            elif 'by' in text_lower:
                amount, currency, receiver, sender = groups
            # pattern 1: "@sender sent X currency to @receiver"
            else:
                sender, amount, currency, receiver = groups
            return {
                'sender_username': sender.strip('@'),
                'receiver_username': receiver.strip('@'),
                'amount': float(amount),
                'currency': currency.upper(),
            }
    return None


async def _get_cwallet_bot_id(context) -> int | None:
    global CWALLET_BOT_USERID
    if CWALLET_BOT_USERID is not None:
        return CWALLET_BOT_USERID
    bot_username = _resolve_cwallet_bot_username()
    try:
        chat = await context.bot.get_chat(f"@{bot_username}")
        CWALLET_BOT_USERID = chat.id
        logging.info(f"CWallet bot user_id resolved: @{bot_username} = {CWALLET_BOT_USERID}")
        return CWALLET_BOT_USERID
    except Exception as e:
        logging.error(f"Failed to resolve CWallet bot @{bot_username}: {e}")
        return None


async def process_tip(
    sender_username: str,
    receiver_username: str,
    amount: float,
    currency: str,
    dedup_key: str,
) -> tuple[float, str] | None:
    receiver_username = receiver_username.lower().lstrip('@')
    cwallet_user = CWALLET_RECEIVE_USERNAME.lower().lstrip('@')
    logging.info(f"CWallet: process_tip receiver={receiver_username} expected={cwallet_user}")
    if receiver_username != cwallet_user:
        logging.info("CWallet: receiver mismatch in process_tip")
        return None

    sender_username = sender_username.lower().lstrip('@')

    if dedup_key in _cwallet_processed_tips:
        logging.info(f"CWallet: duplicate tip {dedup_key} skipped")
        return None
    _cwallet_processed_tips.add(dedup_key)
    _save_cwallet_processed_tips()

    sender_id = username_to_userid.get(sender_username)
    if not sender_id:
        for uid, stats in user_stats.items():
            if stats.get('userinfo', {}).get('username', '').lower() == sender_username:
                sender_id = uid
                break
    logging.info(f"CWallet: sender_id lookup for @{sender_username}: {sender_id}")
    if not sender_id:
        logging.warning(f"CWallet: sender @{sender_username} not found in user database")
        return None

    currency_upper = currency.upper()
    price_usd = await get_crypto_price_usd(currency_upper)
    logging.info(f"CWallet: {amount} {currency_upper} price=${price_usd}")
    usd_value = amount * price_usd
    if usd_value <= 0:
        logging.warning(f"CWallet: invalid USD {usd_value} for {amount} {currency} @{sender_username}")
        return None

    credit_wallet_crypto(sender_id, amount, currency_upper)
    if sender_id in user_stats:
        user_stats[sender_id]["unwagered_deposit"] = (
            user_stats[sender_id].get("unwagered_deposit", 0.0) + usd_value
        )
    save_user_data(sender_id)

    logging.info(
        f"CWallet: credited {amount} {currency_upper} "
        f"(${usd_value:.2f}) user {sender_id} (@{sender_username}) "
        f"[{dedup_key}]"
    )

    if _cwallet_bot_ref:
        try:
            await _cwallet_bot_ref.send_message(
                chat_id=sender_id,
                text=(
                    f"{pe('check')} <b>CWallet Deposit Confirmed!</b>\n\n"
                    f"{pe('money')} <b>{amount} {currency_upper}</b> "
                    f"(${usd_value:.2f})\n\n"
                    f"Your balance has been credited. Good luck! 🎰"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logging.error(f"CWallet: notify fail user {sender_id}: {e}")

    return usd_value, currency_upper


async def cwallet_webhook_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    ok_resp = aiohttp.web.Response(text="ok")
    try:
        body = await request.read()
        if CWALLET_WEBHOOK_SECRET:
            sig = request.headers.get('X-CWallet-Signature', '') or request.headers.get('x-cwallet-signature', '')
            if sig:
                expected = hmac.new(CWALLET_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(expected, sig):
                    logging.warning("CWallet webhook: HMAC mismatch")
                    return aiohttp.web.Response(text="signature mismatch", status=403)
        data = json.loads(body if isinstance(body, bytes) else body)
        sender = (data.get('sender_username') or data.get('sender') or '').lstrip('@')
        receiver = (data.get('receiver_username') or data.get('receiver') or '').lstrip('@')
        amount = float(data.get('amount', 0) or data.get('tip_amount', 0))
        currency = (data.get('currency') or data.get('coin') or 'USDT').upper()
        dedup_key = data.get('id') or data.get('tx_id') or f"wh_{sender}_{receiver}_{amount}_{currency}_{int(datetime.now().timestamp())}"
        await process_tip(sender, receiver, amount, currency, str(dedup_key))
        return ok_resp
    except Exception as e:
        logging.error(f"CWallet webhook error: {e}", exc_info=True)
        return ok_resp


async def start_cwallet_webhook_server(application=None):
    try:
        global _cwallet_bot_ref
        if not CWALLET_RECEIVE_USERNAME:
            return
        logging.info("Starting CWallet webhook server...")
        if application is not None:
            _cwallet_bot_ref = application.bot
        app_web = aiohttp.web.Application()
        app_web.router.add_post("/cwallet_webhook", cwallet_webhook_handler)
        runner = aiohttp.web.AppRunner(app_web)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", CWALLET_WEBHOOK_PORT)
        await site.start()
        logging.info(f"CWallet webhook listening on 0.0.0.0:{CWALLET_WEBHOOK_PORT}")
    except Exception as e:
        logging.error(f"CWallet webhook server error: {e}", exc_info=True)


@check_banned
@check_maintenance
async def cwallet_deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    text = (
        "\U0001FA99 <b>CWallet Deposit</b>\n\n"
        "<b>Instructions:</b>\n"
        "1. Go to our chat @Diwacasino\n"
        "2. Make sure you have a balance in @cctip_bot\n"
        "3. Send a tip using @cctip_bot to us:\n\n"
        "<b>Format:</b>\n"
        "<code>/tip 10 USDT @Ittz_surajj</code>\n"
        "<code>/tip 0.1 ETH @Ittz_surajj</code>\n"
        "<code>/tip 1 SOL @Ittz_surajj</code>\n\n"
        "<b>Supported Coins:</b>\n"
        "\u2022 USDT \u00B7 USDC \u00B7 TON \u00B7 ETH \u00B7 BNB \u00B7 SOL \u00B7 LTC\n\n"
        "<b>Notes:</b>\n"
        "\u2022 Use only @cctip_bot.\n"
        "\u2022 All coins are auto-converted to USD at live market rates.\n"
        "\u2022 The bot will detect your tip and credit your balance instantly."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.edited_message or update.channel_post or update.edited_channel_post
    if not msg:
        return

    if msg.chat_id < 0:
        track_cwallet_monitor_group(msg.chat_id)

    if not msg.text:
        return

    if msg.from_user and msg.from_user.id == 962775809:
        logging.info(f"CWallet: *** GOT CCTIP BOT MSG *** raw={repr(msg.text)} chat={msg.chat_id}")

    if not msg.from_user:
        return

    if msg.forward_origin:
        return

    expected_id = await _get_cwallet_bot_id(context)
    if expected_id is None:
        return
    if msg.from_user.id != expected_id:
        return

    if msg.forward_origin:
        return

    parsed = parse_tip_message(msg.text)
    if not parsed:
        return

    if parsed['receiver_username'].lower().lstrip('@') != CWALLET_RECEIVE_USERNAME.lower().lstrip('@'):
        return

    dedup_key = f"g_{msg.chat_id}_{msg.message_id}"
    result = await process_tip(
        parsed['sender_username'],
        parsed['receiver_username'],
        parsed['amount'],
        parsed['currency'],
        dedup_key,
    )
    if result:
        logging.info(f"CWallet: processed tip in chat {msg.chat_id} msg {msg.message_id}")


async def cwallet_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = update.my_chat_member
    if not member:
        return
    chat = member.chat
    if chat.type not in ('group', 'supergroup'):
        return
    new_status = member.new_chat_member.status
    if new_status in ('member', 'administrator'):
        track_cwallet_monitor_group(chat.id)


def register(ctx):
    ctx.app.add_handler(CommandHandler("cwallet", cwallet_deposit_command, block=False))
