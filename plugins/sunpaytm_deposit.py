"""SunPaytm UPI / USDT deposit integration.

Flow:
  1. User clicks "Deposit via UPI" in deposit menu
  2. Bot asks for amount in INR
  3. Creates a pay-in order via SunPaytm API
  4. User gets checkout URL to complete payment
  5. SunPaytm sends async webhook on settlement
  6. Bot credits user's balance (95 INR = 1 USD)
"""
from __future__ import annotations
from core.foundation import *
from core.foundation import _sunpaytm_processed_orders, _save_sunpaytm_processed_orders, _sunpaytm_bot_ref

import hashlib
import hmac
import json
import logging

import aiohttp

# ── Conversation states ──────────────────────────────────────────────────────
SUNPAYTM_ASK_AMOUNT = "sunpaytm_ask_amount"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _sunpaytm_sign(payload: dict | str, secret: str) -> str:
    if isinstance(payload, dict):
        raw_body = json.dumps(payload, separators=(',', ':'))
    else:
        raw_body = payload
    return hmac.new(secret.encode(), raw_body.encode(), hashlib.sha256).hexdigest()


API_BASE = "https://sunpaytm.quest/api/public"

async def _sunpaytm_api_call(path: str, payload: dict) -> dict | None:
    url = f"{API_BASE}{path}"
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": SUNPAYTM_API_KEY,
    }

    body_str = json.dumps(payload, separators=(',', ':'))
    headers["X-Signature"] = _sunpaytm_sign(body_str, SUNPAYTM_API_SECRET)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=body_str, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                text = await resp.text()
                logging.error(f"SunPaytm POST {url} -> {resp.status}: {text}")
                return None
    except asyncio.TimeoutError:
        logging.error(f"SunPaytm POST {path} timed out")
        return None
    except aiohttp.ClientError as e:
        logging.error(f"SunPaytm POST {path} network error: {e}")
        return None
    except Exception as e:
        logging.error(f"SunPaytm POST {path} exception: {e}")
        return None


async def _sunpaytm_create_payin(
    user_id: int,
    amount_inr: float,
    method: str = "upi",
    customer_name: str = "",
    customer_phone: str = "",
    customer_email: str = "",
) -> dict | None:
    if not SUNPAYTM_API_KEY:
        logging.warning("SUNPAYTM_API_KEY not configured")
        return None

    order_id = f"{user_id}_{int(datetime.now().timestamp())}"

    payload = {
        "order_id": order_id,
        "amount": round(amount_inr, 2),
        "currency": "INR",
        "method": method,
        "notify_url": f"{SUNPAYTM_WEBHOOK_HOST}/sunpaytm_webhook",
    }
    if customer_name:
        payload["customer_name"] = customer_name
    if customer_phone:
        payload["customer_phone"] = customer_phone
    if customer_email:
        payload["customer_email"] = customer_email

    logging.info(f"SunPaytm create_payin: {json.dumps(payload)}")

    result = await _sunpaytm_api_call("/v1/payins", payload)
    if result:
        logging.info(f"SunPaytm create_payin response: {json.dumps(result)[:500]}")
    return result


# ── Webhook handler ──────────────────────────────────────────────────────────

async def sunpaytm_webhook_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    try:
        body_bytes = await request.read()
        body = json.loads(body_bytes)
    except Exception:
        body_bytes = b"{}"
        body = {}
    logging.info(f"SunPaytm webhook received: {body}")

    # Verify x-signature header (webhook secret — log-only for now)
    received_sign = request.headers.get("x-signature", "")
    if received_sign and SUNPAYTM_API_SECRET:
        raw_body = body_bytes.decode("utf-8")
        expected_sign = hmac.new(SUNPAYTM_API_SECRET.encode(), raw_body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sign, received_sign):
            logging.warning(f"SunPaytm webhook x-signature mismatch: got={received_sign[:20]}... expected={expected_sign[:20]}... (proceeding anyway)")

    # Determine order info from webhook payload
    order_id = body.get("order_id") or body.get("merchant_order_id") or body.get("order_no", "")
    status = body.get("status", "").lower()
    event = body.get("event", "").lower()
    trade_no = body.get("transaction_id") or body.get("id", "")
    amount_inr = float(body.get("amount", 0))

    if status not in ("paid", "success", "completed", "settled", "1") and "success" not in event:
        logging.info(f"SunPaytm webhook: ignoring status={status} event={event}")
        return aiohttp.web.Response(status=200)

    # Dedup
    if order_id in _sunpaytm_processed_orders:
        return aiohttp.web.Response(status=200)
    _sunpaytm_processed_orders.add(order_id)
    _save_sunpaytm_processed_orders()

    # Extract user ID from order_id (format: {telegram_id}_{timestamp})
    try:
        telegram_id = int(order_id.split("_")[0])
    except (ValueError, IndexError):
        logging.error(f"SunPaytm: cannot parse user_id from order_id={order_id}")
        return aiohttp.web.Response(status=200)

    # Record deposit in DB
    usd_amount = amount_inr / SUNPAYTM_INR_TO_USD
    try:
        db = DepositDatabase()
        db.add_deposit(tx_hash=trade_no or order_id, user_id=telegram_id, chain="SUNPAYTM",
                       amount=amount_inr, amount_usd=round(usd_amount, 2), to_address="")
        db.update_deposit_status(trade_no or order_id, "confirmed")
        db.update_deposit_status(trade_no or order_id, "swept")
    except Exception as e:
        logging.error(f"SunPaytm: DB record error: {e}")

    # Credit wallet: 95 INR = 1 USD
    ensure_wallet_dict(telegram_id)
    credit_wallet(telegram_id, usd_amount)
    user_stats.setdefault(telegram_id, {})
    user_stats[telegram_id]["unwagered_deposit"] = user_stats[telegram_id].get("unwagered_deposit", 0.0) + usd_amount
    save_user_data(telegram_id)

    logging.info(f"SunPaytm: credited {telegram_id} with ${usd_amount:.2f} (INR {amount_inr:.2f})")

    # Notify user
    try:
        bot = _sunpaytm_bot_ref
        if bot:
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"{pe('check')} <b>UPI Deposit Confirmed!</b>\n\n"
                    f"{pe('money')} Amount: <code>\u20b9{amount_inr:.2f}</code>\n"
                    f"{pe('dollar')} Credited: <code>${usd_amount:.2f}</code>\n"
                    f"{pe('lightning')} Rate: 95 INR = 1 USD\n"
                    f"\uD83E\uDDFE TXN: <code>{trade_no or order_id}</code>\n\n"
                    f"Use /balance to check your updated balance."
                ),
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logging.error(f"SunPaytm: notify user failed: {e}")

    return aiohttp.web.Response(status=200)


# ── Conversation handlers ────────────────────────────────────────────────────

async def sunpaytm_deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Loading...")
    logging.info(f"SunPaytm deposit start by user {update.effective_user.id}")
    try:
        await safe_edit_message(
            query,
            "🏦 <b>UPI / Bank Deposit via SunPaytm</b>\n\n"
            "Enter the amount in <b>INR (₹)</b> you want to deposit.\n\n"
            "💲 Rate: <b>95 INR = 1 USD</b>\n"
            "💲 Min: <b>₹100</b>\n\n"
            "Example: <code>500</code> for ₹500 (≈ $5.26)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="deposit_sunpaytm_cancel")]]),
        )
    except Exception as e:
        logging.error(f"SunPaytm deposit start edit failed: {e}", exc_info=True)
        await query.message.reply_text(
            "🏦 <b>UPI / Bank Deposit via SunPaytm</b>\n\n"
            "Enter the amount in <b>INR (₹)</b> you want to deposit.\n\n"
            "💲 Rate: <b>95 INR = 1 USD</b>\n"
            "💲 Min: <b>₹100</b>\n\n"
            "Example: <code>500</code> for ₹500 (≈ $5.26)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="deposit_sunpaytm_cancel")]]),
        )
    return SUNPAYTM_ASK_AMOUNT


async def sunpaytm_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    try:
        amount_inr = float(text)
        if amount_inr < 100:
            await update.message.reply_text(f"{pe('cross')} Minimum deposit is \u20b9100. Please enter a larger amount.")
            return SUNPAYTM_ASK_AMOUNT
        if amount_inr > 100000:
            await update.message.reply_text(f"{pe('cross')} Maximum deposit is \u20b91,00,000. Please enter a smaller amount.")
            return SUNPAYTM_ASK_AMOUNT
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid amount. Please enter a number (e.g. 500).")
        return SUNPAYTM_ASK_AMOUNT

    usd_amount = amount_inr / SUNPAYTM_INR_TO_USD

    await update.message.reply_text(
        "\u23F1 Creating your deposit order...",
    )

    result = await _sunpaytm_create_payin(
        user_id=user.id,
        amount_inr=amount_inr,
        method="upi",
        customer_name=user.full_name or "",
    )

    if not result:
        await update.message.reply_text(
            f"{pe('cross')} <b>Deposit creation failed.</b>\n\n"
            f"Please try again later or contact support.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    checkout_url = (result.get("checkout_url") or result.get("payment_url")
                    or result.get("redirect_url") or result.get("merchant_gateway_payment_url", ""))

    if not checkout_url:
        await update.message.reply_text(
            f"{pe('cross')} <b>Unexpected response from payment gateway.</b>\n\n"
            f"Details: {json.dumps(result, indent=2)[:500]}",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    order_id = result.get("transaction", {}).get("id") or result.get("order_id", "")

    text = (
        f"🏦 <b>UPI Deposit Order Created</b>\n\n"
        f"💰 Amount: <b>\u20b9{amount_inr:.2f}</b>\n"
        f"💲 You'll receive: <b>${usd_amount:.2f}</b>\n"
        f"⚡ Rate: 95 INR = 1 USD\n\n"
        f"🚀 Click the button below to complete payment:"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Pay Now", url=checkout_url)],
    ])

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return ConversationHandler.END


async def sunpaytm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{pe('cross')} Deposit cancelled.", parse_mode=ParseMode.HTML)
    return ConversationHandler.END


def register(ctx):
    app = ctx.application
    # Register handlers — order doesn't matter here as long as the
    # ConversationHandler in foundation.py already registered deposit_sunpaytm.
    app.add_handler(CallbackQueryHandler(sunpaytm_cancel_callback, pattern=r"^deposit_sunpaytm_cancel$", block=False))


async def sunpaytm_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, keyboard_rows = build_deposit_menu()
    await safe_edit_message(
        query, text,
        reply_markup=create_styled_keyboard(keyboard_rows),
        parse_mode=ParseMode.HTML,
    )
