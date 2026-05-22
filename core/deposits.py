"""Auto-split from bot.py — core.deposits."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

class OxaPayService:
    """OxaPay payment gateway integration."""

    API_URL = "https://api.oxapay.com/merchants/request"

    def __init__(self, merchant_key: str, webhook_host: str):
        self.merchant_key = merchant_key
        self.callback_url = f"{webhook_host}/oxapay_webhook" if webhook_host else ""

    async def create_invoice(self, user_id: int, amount: float, currency: str) -> str | None:
        """Create an OxaPay invoice and return the payUrl, or None on failure.
        
        Args:
            user_id: User ID for order tracking
            amount: Amount in USD
            currency: Currency code (should be 'USD' for the amount)
        """
        if not self.merchant_key:
            logging.warning("OXAPAY_MERCHANT_KEY is not configured.")
            return None
        order_id = f"{user_id}_{int(datetime.now().timestamp())}"
        # OxaPay expects amount as a number and currency as 'USD'
        # The pay currency (BTC, ETH, etc.) is selected by the user on the payment page
        payload = {
            "merchant": self.merchant_key,
            "amount": str(round(amount, 2)),
            "currency": "USD",
            "orderId": order_id,
            "callbackUrl": self.callback_url,
        }
        logging.info(f"OxaPay request payload: {payload}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logging.error(f"OxaPay invoice HTTP error {resp.status}")
                        return None
                    data = await resp.json()
                    if data.get("result") == 100:
                        return data.get("payLink") or data.get("payUrl")
                    logging.error(f"OxaPay invoice error response: {data}")
                    return None
        except asyncio.TimeoutError:
            logging.error("OxaPay create_invoice timed out")
            return None
        except aiohttp.ClientError as e:
            logging.error(f"OxaPay create_invoice network error: {e}")
            return None
        except Exception as e:
            logging.error(f"OxaPay create_invoice exception: {e}")
            return None

def build_deposit_menu():
    """Build deposit menu dynamically based on available chains.

    NOTE: this view intentionally uses plain unicode emoji rather than
    premium <tg-emoji> tags because invalid emoji IDs make Telegram reject
    the entire message with MESSAGE_HAS_INVALID_CUSTOM_EMOJI_ID, which
    would cause /deposit to show users "an error occurred".
    """
    # Build chain list based on availability
    chains_text = [
        "\U0001F539 <b>Ethereum (ETH)</b> - ETH, USDT, USDC",
        "\U0001F538 <b>BNB Chain (BNB)</b> - BNB, USDT, USDC",
        "\U0001F537 <b>Base</b> - ETH, USDC",
    ]

    keyboard_rows = [
        [
            apply_button_style(InlineKeyboardButton("Ethereum", callback_data="deposit_ETH"), 'primary', None),
            apply_button_style(InlineKeyboardButton("BNB Chain", callback_data="deposit_BNB"), 'primary', None)
        ],
        [
            apply_button_style(InlineKeyboardButton("Base", callback_data="deposit_BASE"), 'primary', None),
        ]
    ]

    # Add TRON if available
    if TRON_AVAILABLE:
        chains_text.append("\U0001F53A <b>TRON (TRX)</b> - TRX, USDT")
        keyboard_rows[-1].append(apply_button_style(InlineKeyboardButton("TRON", callback_data="deposit_TRON"), 'primary', None))

    # Add Solana if available
    row_3 = []
    if SOLANA_AVAILABLE:
        chains_text.append("\u25CE <b>Solana (SOL)</b> - SOL, USDT, USDC")
        row_3.append(apply_button_style(InlineKeyboardButton("Solana", callback_data="deposit_SOLANA"), 'primary', None))

    # TON deposit removed as per requirements
    # if TON_AVAILABLE:
    #     chains_text.append("• 💎 <b>TON</b> - TON")
    #     row_3.append(InlineKeyboardButton("TON", callback_data="deposit_TON"))

    if row_3:
        keyboard_rows.append(row_3)

    # Add bottom row - History BLUE, Back RED
    keyboard_rows.append([
        apply_button_style(InlineKeyboardButton("Deposit History", callback_data="deposit_history"), 'primary', None),  # BLUE
        apply_button_style(InlineKeyboardButton("Back", callback_data="back_to_main"), 'danger', None)  # RED
    ])

    # Add OxaPay option if configured
    if OXAPAY_MERCHANT_KEY:
        keyboard_rows.append([
            apply_button_style(InlineKeyboardButton("Deposit via OxaPay", callback_data="deposit_oxapay"), 'primary', None)
        ])

    text = (
        "💰 <b>Deposit Funds</b>\n\n"
        "Select a blockchain to get your unique deposit address:\n\n"
        + "\n".join(chains_text) + "\n\n"
        f"<i>Minimum deposit: ${MIN_DEPOSIT_USD}</i>"
    )

    return text, keyboard_rows

@check_banned
@check_maintenance
async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show deposit options.

    Emojis in this command use plain unicode (no premium <tg-emoji> tags).
    Invalid/missing custom-emoji IDs cause Telegram to reject the whole
    message with MESSAGE_HAS_INVALID_CUSTOM_EMOJI_ID, which was surfacing to
    users as "an error occurred" when running /deposit.
    """
    user_id = update.effective_user.id

    if not DEPOSIT_ENABLED:
        await update.message.reply_text("\u274C Deposits are currently disabled.")
        return

    # In group chats, don't show inline buttons - redirect to DM
    if update.effective_chat.type in ['group', 'supergroup']:
        bot_username = await get_bot_username(context)
        await update.message.reply_text(
            f"\U0001F48E To deposit, please message me privately: @{bot_username}",
            parse_mode=ParseMode.HTML
        )
        return

    text, keyboard_rows = build_deposit_menu()
    sent_message = await update.message.reply_text(text, reply_markup=create_styled_keyboard(keyboard_rows), parse_mode=ParseMode.HTML)
    # Set menu owner after sending
    set_menu_owner(sent_message, user_id)

@check_banned
@check_maintenance
async def deposit_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit method selection"""
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    user_id = query.from_user.id
    chain = query.data.replace("deposit_", "")

    # Get or create user addresses
    db = global_deposit_db
    user_data = await db.async_get_or_create_user(user_id)

    # Get address for selected chain
    address = user_data.get(f"{chain.lower()}_address")

    if not address:
        error_msg = f"\u274C <b>Error Generating {chain} Address</b>\n\n"
        if chain == 'TON':
            error_msg += "TON deposits are currently unavailable. The required library (pytoniq-core) is not installed.\n\n"
            error_msg += "Please contact the administrator or try another chain."
        else:
            error_msg += f"{chain} address could not be generated. Please try again or contact support."

        keyboard = [[InlineKeyboardButton("Back", callback_data=f"back_to_deposit_menu_{user_id}")]]
        await safe_edit_message(
            query,
            error_msg,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Log for debugging
    logging.info(f"Showing deposit address for user {user_id}, chain {chain}: {address}")

    # Generate QR code with the actual address
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(address)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)

    # Chain info
    chain_info = {
        'ETH': {'name': 'Ethereum', 'symbol': 'ETH', 'tokens': 'ETH, USDT, USDC'},
        'BNB': {'name': 'BNB Chain', 'symbol': 'BNB', 'tokens': 'BNB, USDT, USDC'},
        'BASE': {'name': 'Base', 'symbol': 'ETH', 'tokens': 'ETH, USDC'},
        'TRON': {'name': 'TRON', 'symbol': 'TRX', 'tokens': 'TRX, USDT'},
        'SOLANA': {'name': 'Solana', 'symbol': 'SOL', 'tokens': 'SOL, USDT, USDC'},
        'TON': {'name': 'TON', 'symbol': 'TON', 'tokens': 'TON'}
    }

    info = chain_info.get(chain, {})

    text = (
        f"\U0001F4B0 <b>{info['name']} Deposit Address</b>\n\n"
        f"<code>{address}</code>\n\n"
        f"<b>Supported Assets:</b> {info['tokens']}\n"
        f"<b>Network:</b> {info['name']}\n"
        f"<b>Min Deposit:</b> ${MIN_DEPOSIT_USD}\n\n"
        f"\u26A0\uFE0F <b>Important:</b>\n"
        f"\u2022 Only send {info['tokens']} to this address\n"
        f"\u2022 Deposits are automatically credited after {CONFIRMATIONS.get(chain, 10)} confirmations\n"
        f"\u2022 This is your personal deposit address\n\n"
        f"<i>Scan QR code or copy address above</i>\n\n"
        f"\u26A0\uFE0F <b>IMPORTANT:</b> After you have sent your funds, you MUST tap the "
        f"<b>\U0001F504 Check Status</b> button below. The bot will then actively scan the "
        f"blockchain for your deposit for the next 3 minutes."
    )

    keyboard = [
        [InlineKeyboardButton("Check Status", callback_data=f"check_deposit_{chain}_{user_id}")],
        [InlineKeyboardButton("Back", callback_data=f"back_to_deposit_menu_{user_id}")]
    ]

    await query.message.reply_photo(
        photo=bio,
        caption=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

    await query.delete_message()

async def check_deposit_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check deposit status - actively scans for new deposits"""
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer("Checking for deposits...")

    user_id = query.from_user.id

    # Extract chain from callback data if specific chain check
    chain_to_check = None
    if query.data.startswith("check_deposit_"):
        # Handle both old format (check_deposit_ETH) and new format (check_deposit_ETH_12345)
        # Old format maintained for backward compatibility with existing messages
        parts = query.data.replace("check_deposit_", "").split("_")
        chain_to_check = parts[0]
        # If user_id is provided, verify it matches
        if len(parts) > 1:
            button_user_id = int(parts[1])
            if button_user_id != user_id:
                await query.answer("This button is not for you!", show_alert=True)
                return

    db = global_deposit_db

    # If checking a specific chain, register the user for 3-minute on-demand scanning
    if chain_to_check:
        try:
            user_data = await db.async_get_or_create_user(user_id)
            address = user_data.get(f"{chain_to_check.lower()}_address")

            if address:
                # Register for on-demand scanning (expires in 3 minutes)
                expiry = datetime.now() + timedelta(minutes=3)
                active_manual_scans[(user_id, chain_to_check)] = expiry
                logging.info(f"Registered on-demand scan for user {user_id} on {chain_to_check} (expires {expiry})")
        except Exception as e:
            logging.error(f"Error registering scan: {e}")

    # Get deposit history (async to avoid blocking the event loop)
    deposits = await global_deposit_db.async_get_user_deposits(user_id, limit=5)

    # Chain name mapping for display
    chain_names = {
        'ETH': 'Ethereum',
        'BNB': 'BNB Chain',
        'BASE': 'Base',
        'TRON': 'TRON',
        'SOLANA': 'Solana',
        'TON': 'TON'
    }

    text = (
        "📊 <b>Deposit Status</b>\n\n"
        "✅ <b>Started scanning the blockchain for the next 3 minutes.</b>\n"
        "You will be notified automatically when your deposit arrives!\n\n"
    )
    if deposits:
        text += f"{pe('list')} <b>Recent Deposits:</b>\n\n"
        for dep in deposits:
            tx_hash, chain, token, amount, amount_usd, status, created_at, confirmed_at = dep

            status_emoji = {
                'pending': '⏳',
                'confirmed': '✅',
                'swept': '✅',
                'failed': '❌'
            }.get(status, '❓')

            asset = token or chain
            text += (
                f"{status_emoji} <b>{amount:.4f} {asset}</b> (${amount_usd:.2f})\n"
                f"   Chain: {chain}\n"
                f"   Status: {status.title()}\n"
                f"   Date: {created_at[:19]}\n"
                f"   TX: <code>{tx_hash[:16]}...</code>\n\n"
            )
    else:
        text += (
            f"<i>No deposits recorded yet for "
            f"{chain_names.get(chain_to_check, chain_to_check) if chain_to_check else 'all chains'}.\n"
            "Send funds to your deposit address — you'll be notified when it arrives.</i>"
        )

    keyboard = [
        [InlineKeyboardButton("Scan Again", callback_data=f"check_deposit_{chain_to_check}_{user_id}" if chain_to_check else "deposit_history")],
        [InlineKeyboardButton("Back", callback_data=f"back_to_deposit_menu_{user_id}")]
    ]

    # Use safe_edit_message to handle the transition from Photo -> Text
    await safe_edit_message(
        query,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def back_to_deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to deposit menu"""
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    # Extract user_id from callback_data if provided
    user_id = query.from_user.id
    if "_" in query.data:
        parts = query.data.split("_")
        if len(parts) > 3 and parts[-1].isdigit():
            button_user_id = int(parts[-1])
            if button_user_id != user_id:
                await query.answer("This button is not for you!", show_alert=True)
                return

    await query.answer()

    text, keyboard = build_deposit_menu()

    # Use safe_edit_message to handle the transition from Photo -> Text
    await safe_edit_message(query, text, reply_markup=create_styled_keyboard(keyboard), parse_mode=ParseMode.HTML)

async def oxapay_deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: user clicks '⚡ Deposit via OxaPay'."""
    query = update.callback_query
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    await safe_edit_message(
        query,
        "⚡ <b>OxaPay Deposit</b>\n\n"
        "How much USD would you like to deposit? (e.g. <code>20</code>)\n\n"
        "<i>Type /cancel to abort.</i>",
        parse_mode=ParseMode.HTML
    )
    return OXAPAY_ASK_AMOUNT

async def oxapay_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User sends USD amount."""
    text = update.message.text.strip()
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid amount. Please enter a positive number, e.g. <code>20</code>.", parse_mode=ParseMode.HTML)
        return OXAPAY_ASK_AMOUNT
    context.user_data['oxapay_amount'] = amount
    await update.message.reply_text(
        "Which crypto would you like to pay with?\n\n"
        "Supported: <code>BTC</code>, <code>ETH</code>, <code>USDT</code>, <code>LTC</code>, <code>TRX</code>\n\n"
        "Type the currency symbol (e.g. <code>USDT</code>).\n<i>Type /cancel to abort.</i>",
        parse_mode=ParseMode.HTML
    )
    return OXAPAY_ASK_CURRENCY

async def oxapay_receive_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User sends currency, create OxaPay invoice and send link."""
    currency = update.message.text.strip().upper()
    if currency not in OXAPAY_SUPPORTED_CURRENCIES:
        await update.message.reply_text(
            f"{pe('cross')} Unsupported currency. Choose from: {', '.join(sorted(OXAPAY_SUPPORTED_CURRENCIES))}",
            parse_mode=ParseMode.HTML
        )
        return OXAPAY_ASK_CURRENCY

    amount_usd = context.user_data.get('oxapay_amount', 0)
    user_id = update.effective_user.id

    # Get crypto price for display only (OxaPay handles conversion internally)
    crypto_price = LIVE_PRICES.get(currency, None)
    if crypto_price is None or crypto_price <= 0:
        await update.message.reply_text(
            f"{pe('cross')} Unable to get live price for {currency}. Please try again later."
        )
        return ConversationHandler.END

    # Calculate estimated crypto amount for display
    amount_crypto = amount_usd / crypto_price
    precision = CRYPTO_PRECISION.get(currency, 5)

    # Create invoice with USD amount - OxaPay handles crypto conversion
    svc = OxaPayService(OXAPAY_MERCHANT_KEY, OXAPAY_WEBHOOK_HOST)
    pay_url = await svc.create_invoice(user_id, amount_usd, "USD")

    if pay_url:
        await update.message.reply_text(
            f"{pe('check')} <b>OxaPay Invoice Created!</b>\n\n"
            f"Amount: <b>${amount_usd:.2f}</b> (≈ {amount_crypto:.{precision}f} {currency})\n"
            f"Rate: 1 {currency} = ${crypto_price:,.2f}\n\n"
            f"👉 <a href=\"{pay_url}\">Click here to complete payment</a>\n\n"
            f"<i>You can choose your preferred cryptocurrency on the payment page.</i>\n"
            f"<i>Your balance will be credited automatically after payment confirmation.</i>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            "❌ Failed to create OxaPay invoice. Please try again later or contact support."
        )
    return ConversationHandler.END

async def oxapay_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel OxaPay flow."""
    if update.message:
        await update.message.reply_text(f"{pe('cross')} OxaPay deposit cancelled.")
    return ConversationHandler.END

def verify_oxapay_signature(raw_body: bytes, received_hmac: str) -> bool:
    """Verify the HMAC-SHA256 signature sent by OxaPay.

    OxaPay signs the raw JSON body with the merchant key using HMAC-SHA256
    and sends the hex-digest in the ``hmac`` field of the callback payload.
    We recompute the digest over the raw body (before JSON parsing) and
    compare in constant time.
    """
    expected = hmac.new(
        OXAPAY_MERCHANT_KEY.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, received_hmac)

async def oxapay_webhook_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """aiohttp endpoint to receive OxaPay payment callbacks.

    • Verifies HMAC-SHA256 signature using the merchant key.
    • Guards against duplicate processing (in-memory set).
    • Credits the user wallet and records the deposit in the DB.
    • Sends a Telegram success message to the user.
    • Always returns HTTP 200 so OxaPay does not keep retrying.
    """
    global _oxapay_bot_ref, _oxapay_processed_orders

    # Always return 200 to OxaPay — errors are logged server-side.
    ok = aiohttp.web.Response(text="ok")

    try:
        # ── 1. Read raw body (needed for HMAC before JSON parsing) ──
        raw_body = await request.read()
        data = json.loads(raw_body)
        logging.info(f"OxaPay webhook received: {data}")

        # ── 2. Signature verification ──
        received_hmac = data.get("hmac", "")
        if received_hmac:
            # Strip the hmac field from the body before verification:
            # OxaPay computes the HMAC over the payload *without* the hmac
            # field itself, so we rebuild the body excluding it.
            verify_data = {k: v for k, v in data.items() if k != "hmac"}
            verify_body = json.dumps(verify_data, separators=(",", ":")).encode()
            if not verify_oxapay_signature(verify_body, received_hmac):
                logging.warning("OxaPay webhook: HMAC signature mismatch — ignoring callback")
                return ok

        # ── 3. Only process terminal success statuses ──
        status = data.get("status", "").lower()
        if status not in ("paid", "confirmed"):
            return ok

        # ── 4. Extract fields ──
        order_id = data.get("orderId", "")
        track_id = data.get("trackId", "")
        amount_usd = float(data.get("amount", 0))
        paid_currency = data.get("currency", "USDT").upper()
        raw_pay = (
            data.get("payAmount")
            if data.get("payAmount") is not None
            else data.get("pay_amount")
        )
        pay_amount = float(raw_pay) if raw_pay is not None else amount_usd

        # ── 5. Duplicate guard (keyed on orderId which we control) ──
        dedup_key = order_id
        if dedup_key in _oxapay_processed_orders:
            logging.info(f"OxaPay webhook: duplicate callback for {dedup_key} — skipping")
            return ok
        _oxapay_processed_orders.add(dedup_key)
        _save_oxapay_processed_orders()  # Persist immediately to prevent double-credit on restart

        # ── 6. Validate amount ──
        if pay_amount <= 0:
            logging.warning(
                f"OxaPay webhook: pay_amount is {pay_amount} for orderId {order_id}, skipping credit"
            )
            return ok

        # ── 7. Resolve Telegram user from orderId ({telegram_id}_{timestamp}) ──
        telegram_id_str = order_id.split("_")[0] if "_" in order_id else ""
        if not telegram_id_str.isdigit():
            logging.warning(f"OxaPay webhook: unrecognised orderId {order_id}")
            return ok
        telegram_id = int(telegram_id_str)

        # ── 8. Record deposit in the database ──
        # OxaPay deposits land directly in the merchant account — no on-chain
        # sweep is necessary — so we move the status straight to 'swept'.
        db = global_deposit_db
        try:
            tx_ref = order_id
            db.add_deposit(
                tx_hash=tx_ref,
                user_id=telegram_id,
                chain="OXAPAY",
                amount=pay_amount,
                amount_usd=amount_usd,
                to_address="oxapay",
                token=paid_currency,
            )
            db.update_deposit_status(
                tx_ref, "confirmed",
                confirmed_at=datetime.now().isoformat(),
            )
            db.update_deposit_status(
                tx_ref, "swept",
                swept_at=datetime.now().isoformat(),
            )
        except Exception as db_err:
            logging.error(f"OxaPay webhook: DB error for {order_id}: {db_err}")

        # ── 9. Credit user wallet ──
        if telegram_id in user_wallets:
            credit_wallet_crypto(telegram_id, pay_amount, paid_currency)
            if telegram_id in user_stats:
                user_stats[telegram_id]["unwagered_deposit"] = (
                    user_stats[telegram_id].get("unwagered_deposit", 0.0) + amount_usd
                )
            save_user_data(telegram_id)
            logging.info(
                f"OxaPay: credited {pay_amount} {paid_currency} "
                f"(${amount_usd:.2f}) to user {telegram_id}"
            )
        else:
            logging.warning(f"OxaPay webhook: user {telegram_id} not found in user_wallets")

        # ── 10. Notify the user via Telegram ──
        if _oxapay_bot_ref:
            try:
                await _oxapay_bot_ref.send_message(
                    chat_id=telegram_id,
                    text=(
                        f"{pe('check')} <b>Deposit Confirmed!</b>\n\n"
                        f"{pe('money')} <b>{pay_amount:.8f} {paid_currency}</b> "
                        f"(${amount_usd:.2f})\n\n"
                        f"Your balance has been credited. Good luck! 🎰"
                    ),
                    parse_mode="HTML",
                )
            except Exception as msg_err:
                logging.error(
                    f"OxaPay webhook: failed to notify user {telegram_id}: {msg_err}"
                )

        return ok

    except Exception as e:
        logging.error(f"OxaPay webhook error: {e}")
        # Still return 200 so OxaPay does not retry on our server errors.
        return ok

@check_banned
@check_maintenance
async def withdrawal_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "💳 <b>Change Withdrawal Address</b>\n\n"
        "Please enter your new USDT-BEP20 withdrawal address.\n"
        "⚠️ Make sure it's a valid BEP20 address.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="main_settings")]])
    )
    return SETTINGS_WITHDRAWAL_ADDRESS_CHANGE

@check_banned
@check_maintenance
async def withdraw_coin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal coin selection callback."""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    coin = query.data.replace("withdraw_coin_", "")

    if coin not in SUPPORTED_CRYPTOS:
        await query.edit_message_text(f"{pe('cross')} Invalid crypto selected.")
        return

    wallet = ensure_wallet_dict(user.id)
    balance = wallet.get(coin, 0.0)
    price = LIVE_PRICES.get(coin, 1.0)
    balance_usd = balance * price
    formatted = format_crypto_amount(balance, coin)

    context.user_data['withdrawal_coin'] = coin
    context.user_data['withdrawal_flow'] = True

    await query.edit_message_text(
        f"{pe('withdraw')} <b>Withdraw {coin}</b>\n\n"
        f"{pe('gem')} Available: {formatted} {coin} (${balance_usd:,.2f})\n\n"
        f"Enter the amount in USD you want to withdraw.\n"
        f"Type 'all' to withdraw your entire {coin} balance.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back_to_main")]])
    )
    return WITHDRAWAL_AMOUNT

@check_banned
@check_maintenance
async def withdrawal_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("Only the owner can approve withdrawals.", show_alert=True)
        return

    withdrawal_id = query.data.split("_")[-1]
    withdrawal = withdrawal_requests.get(withdrawal_id)

    if not withdrawal:
        await query.answer("Withdrawal request not found.", show_alert=True)
        return

    if withdrawal["status"] != "pending":
        await query.answer(f"This withdrawal has already been {withdrawal['status']}.", show_alert=True)
        return

    # Ask for TXID
    await query.edit_message_text(
        f"{pe('withdraw')} <b>Approve Withdrawal</b>\n\n"
        f"<b>Request ID:</b> <code>{withdrawal_id}</code>\n\n"
        f"Please enter the transaction hash (TXID) for this withdrawal:",
        parse_mode=ParseMode.HTML
    )

    context.user_data['withdrawal_approve_id'] = withdrawal_id
    return WITHDRAWAL_APPROVAL_TXID

async def withdrawal_txid_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txid = update.message.text.strip()
    withdrawal_id = context.user_data.get('withdrawal_approve_id')

    if not withdrawal_id or withdrawal_id not in withdrawal_requests:
        await update.message.reply_text(f"{pe('cross')} Withdrawal request not found.")
        context.user_data.clear()
        return ConversationHandler.END

    withdrawal = withdrawal_requests[withdrawal_id]

    # Update withdrawal status
    withdrawal["status"] = "approved"
    withdrawal["txid"] = txid
    withdrawal["approved_at"] = str(datetime.now(timezone.utc))

    # Notify user
    coin = withdrawal.get("coin", "USDT")
    currency_symbol = CURRENCY_SYMBOLS.get(coin, "$")
    crypto_amount = withdrawal.get("crypto_amount", withdrawal.get("amount_usd", 0))
    try:
        await context.bot.send_message(
            chat_id=withdrawal["user_id"],
            text=(
                f"{pe('check')} <b>Withdrawal Approved</b>\n\n"
                f"<b>Request ID:</b> <code>{withdrawal_id}</code>\n"
                f"<b>Amount:</b> ${withdrawal['amount_usd']:.2f} ({format_crypto_amount(crypto_amount, coin)} {coin})\n"
                f"<b>Transaction Hash:</b> <code>{txid}</code>\n\n"
                f"Your withdrawal has been processed successfully!"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Failed to notify user about withdrawal approval: {e}")

    await update.message.reply_text(
        f"{pe('check')} Withdrawal {withdrawal_id} approved and user notified."
    )

    context.user_data.clear()
    return ConversationHandler.END

@check_banned
@check_maintenance
async def withdrawal_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("Only the owner can cancel withdrawals.", show_alert=True)
        return

    withdrawal_id = query.data.split("_")[-1]
    withdrawal = withdrawal_requests.get(withdrawal_id)

    if not withdrawal:
        await query.answer("Withdrawal request not found.", show_alert=True)
        return

    if withdrawal["status"] != "pending":
        await query.answer(f"This withdrawal has already been {withdrawal['status']}.", show_alert=True)
        return

    # Return funds to user (ATOMIC - prevents race conditions)
    user_id = withdrawal["user_id"]
    amount_usd = withdrawal["amount_usd"]
    async with _get_withdrawal_lock(user_id):
        credit_wallet_safe(user_id, amount_usd)
    save_user_data(user_id)

    # Update withdrawal status
    withdrawal["status"] = "cancelled"
    withdrawal["cancelled_at"] = str(datetime.now(timezone.utc))

    # Notify user
    coin = withdrawal.get("coin", "USDT")
    currency_symbol = CURRENCY_SYMBOLS.get(coin, "$")
    crypto_amount = withdrawal.get("crypto_amount", withdrawal.get("amount_usd", 0))
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"{pe('cross')} <b>Withdrawal Cancelled</b>\n\n"
                f"<b>Request ID:</b> <code>{withdrawal_id}</code>\n"
                f"<b>Amount:</b> ${withdrawal['amount_usd']:.2f} ({format_crypto_amount(crypto_amount, coin)} {coin})\n\n"
                f"Your withdrawal request has been cancelled by the administrator.\n"
                f"The funds have been returned to your balance.\n\n"
                f"For more information, please contact support @jashanxjagy."
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Failed to notify user about withdrawal cancellation: {e}")

    await query.edit_message_text(
        f"{pe('cross')} Withdrawal {withdrawal_id} cancelled. Funds returned to user's balance."
    )

    return ConversationHandler.END

async def withdrawinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: Show withdrawal details and re-present approve/decline buttons.
    If already processed, show the status and TXID."""
    if not is_admin(update.effective_user.id):
        return  # Silently ignore non-admin users

    args = update.message.text.strip().split()
    if len(args) != 2:
        await update.message.reply_text(
            "Usage: /withdrawinfo <withdrawal_id>\n"
            "Example: /withdrawinfo WD-240428-ABC123"
        )
        return

    withdrawal_id = args[1]
    withdrawal = withdrawal_requests.get(withdrawal_id)

    if not withdrawal:
        await update.message.reply_text(
            f"{pe('cross')} Withdrawal request <code>{withdrawal_id}</code> not found.",
            parse_mode=ParseMode.HTML
        )
        return

    status = withdrawal.get("status", "unknown")
    user_id = withdrawal.get("user_id", "N/A")
    username = withdrawal.get("username", "N/A")
    amount_usd = withdrawal.get("amount_usd", 0)
    crypto_amount = withdrawal.get("crypto_amount", 0)
    coin = withdrawal.get("coin", "USDT")
    address = withdrawal.get("withdrawal_address", "N/A")
    timestamp = withdrawal.get("timestamp", "N/A")
    txid = withdrawal.get("txid")

    formatted_crypto = format_crypto_amount(crypto_amount, coin) if crypto_amount else "N/A"

    text = (
        f"{pe('withdraw')} <b>Withdrawal Details</b>\n\n"
        f"<b>Request ID:</b> <code>{withdrawal_id}</code>\n"
        f"<b>User ID:</b> <code>{user_id}</code>\n"
        f"<b>User:</b> @{username}\n"
        f"<b>USD Value:</b> ${amount_usd:.2f}\n"
        f"<b>Coin:</b> {coin}\n"
        f"<b>Crypto Amount:</b> {formatted_crypto} {coin}\n"
        f"<b>Address:</b> <code>{address}</code>\n"
        f"<b>Requested:</b> {timestamp}\n"
    )

    if status == "pending":
        text += f"\n<b>Status:</b> {pe('warning')} <b>PENDING</b>"
        # Show approve/decline buttons (fresh ones that won't expire)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Approve", callback_data=f"withdrawal_approve_{withdrawal_id}"),
             InlineKeyboardButton("Cancel", callback_data=f"withdrawal_cancel_{withdrawal_id}")]
        ])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    elif status == "approved":
        approved_at = withdrawal.get("approved_at", "N/A")
        text += (
            f"\n<b>Status:</b> {pe('check')} <b>APPROVED</b>\n"
            f"<b>Approved At:</b> {approved_at}\n"
            f"<b>TXID:</b> <code>{txid or 'N/A'}</code>"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    elif status == "cancelled":
        cancelled_at = withdrawal.get("cancelled_at", "N/A")
        text += (
            f"\n<b>Status:</b> {pe('cross')} <b>CANCELLED</b>\n"
            f"<b>Cancelled At:</b> {cancelled_at}\n"
            f"Funds were returned to user's balance."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        text += f"\n<b>Status:</b> {status.upper()}"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

