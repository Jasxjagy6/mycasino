"""Auto-split from bot.py — plugins.wallet_commands."""
from __future__ import annotations
import re as _re
from core import foundation as _foundation  # for late-bound module-level lookups
from core.foundation import *  # noqa: F401, F403


def _ensure_pending_tips_registry():
    """Return the shared ``(pending_tips, PENDING_TIP_TTL_SECONDS)`` from
    ``core.foundation``, attaching them lazily if the live foundation
    module was loaded before the registry was added.

    This makes ``/tip`` resilient to the deployment scenario where this
    plugin has been ``/reload``-ed but ``core.foundation`` is still the
    older in-memory revision (``core.foundation`` is intentionally NOT
    reloaded by ``/refreshcore`` in production because re-running its
    body would reset ``user_stats``/``user_wallets`` and lose live data).
    Without this, the new tip code raised ``NameError: name
    'pending_tips' is not defined`` and PTB's global error_handler
    replied with "An error occurred. Please try again."
    """
    reg = getattr(_foundation, "pending_tips", None)
    if not isinstance(reg, dict):
        reg = {}
        try:
            _foundation.pending_tips = reg
        except Exception:
            pass
    ttl = getattr(_foundation, "PENDING_TIP_TTL_SECONDS", None)
    if not isinstance(ttl, int) or ttl <= 0:
        ttl = 24 * 60 * 60
        try:
            _foundation.PENDING_TIP_TTL_SECONDS = ttl
        except Exception:
            pass
    # Also expose on this module's globals so unqualified references in
    # the rest of this file resolve, even though `from core.foundation
    # import *` may not have picked them up.
    globals().setdefault("pending_tips", reg)
    globals()["pending_tips"] = reg
    globals()["PENDING_TIP_TTL_SECONDS"] = ttl
    return reg, ttl


# Best-effort eager init at import time so other functions in this
# module can use the registry directly. The runtime call inside
# tip_command is the real safety net.
try:
    _ensure_pending_tips_registry()
except Exception:
    pass

# In-memory side-table for rain metadata that doesn't fit the DB schema
# (min wager-required, total USD value of the rain pool, creator's
# display currency).  Keyed by ``rain_id``.  Survives /reload because
# this module's globals persist across importlib.reload (only changed
# code is swapped, dict references stay alive).
_RAIN_EXTRA: dict = {}

_RAIN_DURATION_RE = _re.compile(r"^(\d+(?:\.\d+)?)([smh])$", _re.IGNORECASE)
_RAIN_DURATION_DEFAULT = 300         # seconds — original default
_RAIN_DURATION_MAX = 60 * 60 * 24    # 24h hard cap
_RAIN_DURATION_MIN = 30              # 30s lower bound


def _parse_rain_duration(token: str) -> int:
    """Parse a duration string like ``30s`` / ``2m`` / ``1h``.  Returns
    seconds, clamped to [_RAIN_DURATION_MIN, _RAIN_DURATION_MAX]. Raises
    :class:`ValueError` on bad input."""
    m = _RAIN_DURATION_RE.match(token.strip())
    if not m:
        raise ValueError(f"Bad duration: {token!r}. Use e.g. 30s, 2m, 1h.")
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "s":
        secs = val
    elif unit == "m":
        secs = val * 60
    else:  # h
        secs = val * 3600
    secs = int(secs)
    if secs < _RAIN_DURATION_MIN:
        raise ValueError(f"Duration must be at least {_RAIN_DURATION_MIN}s.")
    if secs > _RAIN_DURATION_MAX:
        raise ValueError("Duration cannot exceed 24h.")
    return secs


def _build_rain_message(rain, participants):
    """Build the rain announcement message text — premium-emoji styled."""
    extra = _RAIN_EXTRA.get(rain['rain_id'], {})
    disp_currency = extra.get('display_currency') or 'USD'
    pool_usd = float(extra.get('amount_usd') or 0.0)
    min_wager_usd = float(extra.get('min_wager_usd') or 0.0)

    creator_uname = rain.get('creator_username') or ''
    creator_uid = rain.get('creator_id')
    creator_display = get_privacy_display_name(creator_uid, creator_uname or f"User {creator_uid}")
    if creator_uname and creator_display == creator_uname:
        creator_display = f"@{creator_uname}"

    count = len(participants)
    try:
        end_dt = datetime.fromisoformat(rain['end_time'])
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        remaining = max(0, int((end_dt - datetime.now(timezone.utc)).total_seconds()))
    except Exception:
        remaining = 0
    if remaining >= 3600:
        time_str = f"{remaining // 3600}h {(remaining % 3600) // 60}m"
    elif remaining >= 60:
        time_str = f"{remaining // 60}m {remaining % 60}s"
    else:
        time_str = f"{remaining}s"

    if pool_usd > 0:
        total_str = format_display_amount(pool_usd, disp_currency, with_symbol=True)
        per_person_str = (
            format_display_amount(pool_usd / count, disp_currency, with_symbol=True)
            if count else format_display_amount(pool_usd, disp_currency, with_symbol=True)
        )
    else:
        total_str = f"{rain['amount']:.4f} {rain['currency']}"
        per_person_str = (
            f"{rain['amount'] / count:.6f} {rain['currency']}" if count else total_str
        )

    lines = [
        f"{pe('rain')} <b>RAIN INCOMING!</b> {pe('sparkles')}",
        "━━━━━━━━━━━━━━━━━━",
        f"{pe('crown')} <b>{creator_display}</b> is raining",
        f"{pe('moneybag')} <b>{total_str}</b> on the group!",
        "",
        f"{pe('lightning')} Time left: <b>{time_str}</b>",
        f"{pe('user')} Joined: <b>{count}</b>",
        f"{pe('gift')} Per winner: <b>{per_person_str}</b>",
    ]
    if min_wager_usd > 0:
        wager_str = format_display_amount(min_wager_usd, disp_currency, with_symbol=True)
        lines.append(f"{pe('chart')} Min wager required: <b>{wager_str}</b>")
    lines += [
        "",
        f"{pe('fire')} Tap the button to claim your share!",
    ]
    return "\n".join(lines)


def _build_rain_keyboard(rain_id, joined_count):
    """Premium-emoji blue Join Rain button."""
    label = f"Join Rain ({joined_count})" if joined_count else "Join Rain"
    btn = apply_button_style(
        InlineKeyboardButton(label, callback_data=f"join_rain_{rain_id}"),
        'primary',         # blue
        peb('rain'),        # premium 🌧 icon
    )
    return create_styled_keyboard([[btn]])

_USAGE_TEXT = (
    "Usage:\n"
    "• <code>/rain &lt;amount&gt;</code>\n"
    "• <code>/rain &lt;amount&gt; &lt;wager-required&gt;</code>\n"
    "• <code>/rain &lt;amount&gt; &lt;wager-required&gt; &lt;duration&gt;</code>\n"
    "• <code>/rain &lt;amount&gt; &lt;currency&gt;</code> (classic crypto syntax)\n\n"
    "<i>Amount &amp; wager are in your display currency. Duration accepts "
    "<code>30s</code> / <code>2m</code> / <code>1h</code>.</i>\n\n"
    "Examples:\n"
    "• <code>/rain 1000</code> — 1000 in your display currency for 5 min\n"
    "• <code>/rain 1000 500 2m</code> — 1000 pool, only users who've wagered 500+ can join, ends in 2 min\n"
    "• <code>/rain 5 USDT</code> — raw 5 USDT"
)

_KNOWN_RAIN_CURRENCIES = {
    "USDT", "USDC", "BTC", "ETH", "SOL", "BNB", "TRX", "LTC", "TON",
}


@check_banned
@check_maintenance
async def rain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a group rain.

    Forms supported (all amount/wager values are in the *user's display
    currency*):

    * ``/rain <amount>`` — default duration, no wager requirement.
    * ``/rain <amount> <wager-required>``
    * ``/rain <amount> <wager-required> <duration>``  (eg ``2m``, ``30s``, ``1h``)
    * ``/rain <amount> <CURRENCY>`` — classic crypto syntax (raw amount in that crypto).
    """
    logging.info(f"[RAIN] Command triggered by user {update.effective_user.id}")
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    args = update.message.text.strip().split()
    logging.info(f"[RAIN] Args: {args}")
    if len(args) < 2:
        await update.message.reply_text(_USAGE_TEXT, parse_mode=ParseMode.HTML)
        return

    disp_currency = get_display_currency(user.id)
    min_wager_usd = 0.0
    duration_secs = RAIN_DURATION_SECONDS or _RAIN_DURATION_DEFAULT

    # Detect classic explicit-crypto syntax: /rain <amount> <CURRENCY>
    second_arg_is_currency = (
        len(args) == 3 and args[2].upper() in _KNOWN_RAIN_CURRENCIES
    )
    classic_two_arg_currency = (
        len(args) == 3 and not second_arg_is_currency and args[2].upper() in _KNOWN_RAIN_CURRENCIES
    )
    classic_currency = (
        len(args) == 3 and args[2].upper() in _KNOWN_RAIN_CURRENCIES
    )

    if classic_currency:
        try:
            amount = float(args[1])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                f"{pe('cross')} Invalid amount. Please enter a positive number.",
                parse_mode=ParseMode.HTML,
            )
            return
        currency = args[2].upper()
        amount_disp = None
    else:
        try:
            amount_disp = float(args[1])
            if amount_disp <= 0:
                raise ValueError
            amount_usd = convert_display_to_usd(amount_disp, disp_currency)
        except ValueError:
            await update.message.reply_text(
                f"{pe('cross')} Invalid amount. Please enter a positive number.",
                parse_mode=ParseMode.HTML,
            )
            return
        if len(args) >= 3:
            try:
                wager_disp = float(args[2])
                if wager_disp < 0:
                    raise ValueError
                min_wager_usd = convert_display_to_usd(wager_disp, disp_currency)
            except ValueError:
                await update.message.reply_text(
                    f"{pe('cross')} Invalid wager-required. Please enter a non-negative number.",
                    parse_mode=ParseMode.HTML,
                )
                return
        if len(args) >= 4:
            try:
                duration_secs = _parse_rain_duration(args[3])
            except ValueError as e:
                await update.message.reply_text(
                    f"{pe('cross')} {e}", parse_mode=ParseMode.HTML
                )
                return
        usdt_price = LIVE_PRICES.get("USDT", 1.0) or 1.0
        amount = amount_usd / usdt_price
        currency = "USDT"
        logging.info(
            f"[RAIN] Display→USDT: {amount_disp} {disp_currency} → "
            f"{amount:.6f} USDT (wager_min_usd={min_wager_usd:.2f}, dur={duration_secs}s)"
        )

    # Validate currency exists in wallet
    wallet = ensure_wallet_dict(user.id)
    if currency not in wallet and currency not in LIVE_PRICES:
        await update.message.reply_text(f"{pe('cross')} Unknown currency: <b>{currency}</b>. Use USDT, ETH, BNB, SOL, etc.", parse_mode=ParseMode.HTML)
        return

    # Check balance
    price = LIVE_PRICES.get(currency, 1.0)
    amount_usd = amount * price
    available_crypto = wallet.get(currency, 0.0)
    logging.info(f"[RAIN] Balance check: available={available_crypto}, needed={amount}")

    if available_crypto < amount:
        await update.message.reply_text(
            f"{pe('cross')} Insufficient balance.\n"
            f"You need <b>{amount:.6f} {currency}</b> but have <b>{available_crypto:.6f} {currency}</b>.",
            parse_mode=ParseMode.HTML
        )
        return

    if amount_usd < RAIN_MIN_AMOUNT:
        await update.message.reply_text(
            f"{pe('cross')} Rain amount too small. Minimum is <b>${RAIN_MIN_AMOUNT:.2f}</b> (≈ {RAIN_MIN_AMOUNT/price:.6f} {currency}).",
            parse_mode=ParseMode.HTML
        )
        return

    # Deduct immediately to lock funds
    logging.info(f"[RAIN] Deducting {amount} {currency} from user {user.id}")
    credit_wallet_crypto(user.id, -amount, currency)
    save_user_data(user.id)

    # Create rain in DB (async to avoid blocking event loop)
    rain_id = str(uuid.uuid4())
    end_time = (datetime.now(timezone.utc) + timedelta(seconds=duration_secs)).isoformat()
    _RAIN_EXTRA[rain_id] = {
        'amount_usd': amount_usd,
        'min_wager_usd': min_wager_usd,
        'display_currency': disp_currency,
        'creator_id': user.id,
    }
    db = global_deposit_db

    try:
        logging.info(f"[RAIN] Creating rain in DB: {rain_id}")
        created = await db.async_create_rain(
            rain_id=rain_id,
            chat_id=update.effective_chat.id,
            creator_id=user.id,
            creator_username=user.username,
            amount=amount,
            currency=currency,
            end_time=end_time
        )
        logging.info(f"[RAIN] async_create_rain returned: {created}")
        if not created:
            # Refund on DB failure
            credit_wallet_crypto(user.id, amount, currency)
            save_user_data(user.id)
            await update.message.reply_text(f"{pe('cross')} Failed to create rain. Please try again in a moment.")
            return

        # Build initial rain message
        logging.info(f"[RAIN] Fetching rain data for {rain_id}")
        rain = await db.async_get_rain(rain_id)
        logging.info(f"[RAIN] async_get_rain returned: {rain}")
        if not rain:
            credit_wallet_crypto(user.id, amount, currency)
            save_user_data(user.id)
            await update.message.reply_text(f"{pe('cross')} Failed to create rain. Please try again in a moment.")
            return

        text = _build_rain_message(rain, [])
        keyboard = _build_rain_keyboard(rain_id, 0)
        logging.info(f"[RAIN] Sending rain message to chat {update.effective_chat.id}")
        sent = await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        logging.info(f"[RAIN] Message sent: {sent.message_id}")

        # Store message_id for later updates (async)
        await db.async_set_rain_message_id(rain_id, sent.message_id)

        # Schedule job to finalize rain after duration
        if context.job_queue:
            context.job_queue.run_once(
                finalize_rain_job,
                when=duration_secs,
                data={'rain_id': rain_id, 'chat_id': update.effective_chat.id, 'message_id': sent.message_id},
                name=f"rain_{rain_id}"
            )
        else:
            # JobQueue extra not installed — fall back to a plain asyncio task.
            async def _finalize_no_jq():
                await asyncio.sleep(duration_secs)
                fake_ctx = type('FakeCtx', (), {
                    'bot': context.bot,
                    'job': type('FakeJob', (), {'data': {
                        'rain_id': rain_id,
                        'chat_id': update.effective_chat.id,
                        'message_id': sent.message_id,
                    }})(),
                })()
                await finalize_rain_job(fake_ctx)
            asyncio.create_task(_finalize_no_jq(), name=f"rain_finalize_{rain_id}")
        logging.info(f"Rain {rain_id} started by {user.id} for {amount} {currency} in chat {update.effective_chat.id}")
    except Exception as e:
        logging.error(f"Rain command error: {e}")
        # Refund on unexpected error
        credit_wallet_crypto(user.id, amount, currency)
        save_user_data(user.id)
        await update.message.reply_text(f"{pe('cross')} An error occurred while creating the rain. Your balance has been refunded. Please try again.")

@check_banned
@check_maintenance
async def join_rain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a user clicking the Join Rain button."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    rain_id_str = query.data.replace("join_rain_", "", 1)

    db = global_deposit_db
    rain = await db.async_get_rain(rain_id_str)

    if not rain:
        await query.answer(f"{pe('cross')} This rain no longer exists.", show_alert=True)
        return

    if rain['status'] != 'active':
        await query.answer(f"{pe('rain')} This rain has already ended!", show_alert=True)
        return

    # Check time
    try:
        end_dt = datetime.fromisoformat(rain['end_time'])
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= end_dt:
            await query.answer(f"{pe('rain')} This rain has already ended!", show_alert=True)
            return
    except Exception:
        pass

    # Prevent creator from joining their own rain
    if user.id == rain['creator_id']:
        await query.answer("You can't join your own rain!", show_alert=True)
        return

    # Ensure user is registered
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Min-wager gate.  Compares the user's lifetime wagered total (USD)
    # against the rain's ``min_wager_usd`` requirement set by the creator.
    extra = _RAIN_EXTRA.get(rain_id_str, {})
    min_wager_usd = float(extra.get('min_wager_usd') or 0.0)
    if min_wager_usd > 0:
        u_stats = user_stats.get(user.id, {})
        wagered_total = float(u_stats.get('bets', {}).get('amount', 0.0))
        if wagered_total < min_wager_usd:
            disp = get_display_currency(user.id)
            need = format_display_amount(min_wager_usd, disp, with_symbol=True)
            have = format_display_amount(wagered_total, disp, with_symbol=True)
            await query.answer(
                f"You need {need} wagered to join this rain. You have {have}.",
                show_alert=True,
            )
            return

    # Add participant (returns False if already joined) - async
    added = await db.async_add_rain_participant(rain_id_str, user.id, user.username)
    if not added:
        await query.answer("You've already joined this rain!", show_alert=True)
        return

    await query.answer("You joined the rain!")

    # Update the announcement message
    participants = await db.async_get_rain_participants(rain_id_str)
    text = _build_rain_message(rain, participants)
    keyboard = _build_rain_keyboard(rain_id_str, len(participants))
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except Exception:
        pass  # Message may have been edited too recently; ignore

async def finalize_rain_job(context: ContextTypes.DEFAULT_TYPE):
    """Job that fires when the rain window closes and distributes funds."""
    data = context.job.data
    rain_id = data['rain_id']
    chat_id = data['chat_id']
    message_id = data['message_id']

    db = global_deposit_db
    rain = await db.async_get_rain(rain_id)

    if not rain or rain['status'] != 'active':
        return  # Already completed or missing

    await db.async_complete_rain(rain_id)
    participants = await db.async_get_rain_participants(rain_id)
    amount = rain['amount']
    currency = rain['currency']
    creator_id = rain['creator_id']
    creator_username = rain['creator_username'] or f"User {creator_id}"

    extra = _RAIN_EXTRA.get(rain_id, {})
    pool_disp_currency = extra.get('display_currency') or 'USD'
    pool_usd = float(extra.get('amount_usd') or 0.0)
    price = LIVE_PRICES.get(currency, 1.0)
    if pool_usd <= 0:
        pool_usd = amount * price

    creator_uname_raw = rain.get('creator_username') or ''
    creator_display = get_privacy_display_name(creator_id, creator_uname_raw or creator_username)
    if creator_uname_raw and creator_display == creator_uname_raw:
        creator_display = f"@{creator_uname_raw}"

    if not participants:
        # No one joined — refund creator
        credit_wallet_crypto(creator_id, amount, currency)
        save_user_data(creator_id)
        pool_str = format_display_amount(pool_usd, pool_disp_currency, with_symbol=True)
        text = (
            f"{pe('rain')} <b>Rain Ended — No Participants</b>\n\n"
            f"Nobody joined {creator_display}'s rain.\n"
            f"<b>{pool_str}</b> has been refunded."
        )
    else:
        per_person = amount / len(participants)
        per_person_usd = pool_usd / len(participants)
        recipient_lines = []

        for uid, uname in participants:
            await ensure_user_in_wallets_sync(uid, uname, context)
            credit_wallet_crypto(uid, per_person, currency)
            update_stats_on_rain_received(uid, per_person_usd)
            save_user_data(uid)
            display = get_privacy_display_name(uid, uname or f"User {uid}")
            if uname and display == uname:
                recipient_lines.append(f"@{uname}")
            else:
                recipient_lines.append(display)

        recipients_str = ", ".join(recipient_lines)
        pool_str = format_display_amount(pool_usd, pool_disp_currency, with_symbol=True)
        each_str = format_display_amount(per_person_usd, pool_disp_currency, with_symbol=True)
        text = (
            f"{pe('rain')} <b>Rain Complete!</b> {pe('sparkles')}\n\n"
            f"<b>{creator_display}</b> rained <b>{pool_str}</b> on {len(participants)} user(s)!\n"
            f"{pe('moneybag')} Each received: <b>{each_str}</b>\n\n"
            f"{pe('win')} Recipients: {recipients_str}"
        )

    # Edit the original rain message
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.warning(f"Could not edit rain message {message_id}: {e}")
        # Fall back to sending a new message
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e2:
            logging.error(f"Failed to send rain result message: {e2}")
    finally:
        _RAIN_EXTRA.pop(rain_id, None)

@check_banned
@check_maintenance
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)
    user_currency = get_user_currency(user.id)
    formatted_balance = format_balance_with_locked(user.id, user_currency)

    # Get total wagers for display
    stats = user_stats.get(user.id, {})
    total_wagered = stats.get('bets', {}).get('amount', 0.0)
    formatted_wagers = format_currency(total_wagered, user_currency)

    is_group = update.effective_chat.type in ["group", "supergroup"]

    if is_group:
        # Group chat: simplified balance display with Deposit/Withdraw link buttons, NO template image
        bot_username = await get_bot_username(context)
        keyboard = [
            [
                apply_button_style(InlineKeyboardButton("Deposit", url=f"https://t.me/{bot_username}?start=deposit"), 'primary'),  # BLUE
                apply_button_style(InlineKeyboardButton("Withdraw", url=f"https://t.me/{bot_username}?start=withdraw"), 'success')  # GREEN
            ],
        ]

        # Group format: ONLY the user's display-currency balance.  We
        # intentionally drop the crypto wallet line — groups are public
        # and people don't want their wallet coin or balance leaking.
        balance_usd = get_active_balance_usd(user.id)
        disp = get_display_currency(user.id)
        display_str = format_for_user(
            user.id, balance_usd, compact=False,
            with_usdt_estimate=False,
        )
        cur_emoji = pe(CURRENCY_EMOJI_KEY.get(disp, 'dollar'))
        text = f"{cur_emoji} <b>Balance:</b> {display_str}"

        reply_markup = create_styled_keyboard(keyboard)

        sent_message = await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        set_menu_owner(sent_message, user.id)
        return

    # DM: original behavior
    keyboard = [
        [
            InlineKeyboardButton("Deposit", callback_data="main_deposit"),
            InlineKeyboardButton("Withdraw", callback_data="main_withdraw")
        ],
        [InlineKeyboardButton("View Full Wallet", callback_data="main_wallet")]
    ]

    text = f"{pe('money')} <b>Your Balance</b>\n\n{formatted_balance}"

    # Send dashboard image with balance text in caption (NEW FEATURE - Combined)
    dashboard_image = await generate_dashboard_image(user.id, context)
    if dashboard_image:
        try:
            await update.message.reply_photo(
                photo=dashboard_image,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logging.error(f"Error sending dashboard image: {e}")
            # Fallback to text only
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        # No image, send text only
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

@check_banned
@check_maintenance
async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send another user a tip in your active currency.

    The body is wrapped in a try/except so that if any helper raises
    (e.g. wallet load failed, currency rate stale, Telegram returned a
    BadRequest on the inline-keyboard render), the rightful sender gets
    a precise error message instead of PTB's global "An error occurred."
    fallback that the user complained about.
    """
    try:
        return await _tip_command_impl(update, context)
    except Exception as exc:  # noqa: BLE001
        logging.exception("/tip failed for user %s: %s", update.effective_user.id, exc)
        try:
            await update.message.reply_text(
                f"{pe('cross')} /tip failed: <code>{type(exc).__name__}: {exc}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


async def _tip_command_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending_tips_reg, PENDING_TTL = _ensure_pending_tips_registry()
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    message_text = (update.message.text or "").strip().split()
    target_user_id = None
    target_username = None

    # Parse tip amount in the sender's DISPLAY currency so /tip @x 500
    # means "500 of whatever currency I've chosen".
    display_currency = get_display_currency(user.id)
    disp_sym = CURRENCY_SYMBOLS.get(display_currency, "")

    raw_amount_str = None
    if update.message.reply_to_message and len(message_text) == 2:
        try:
            raw_amount_str = message_text[1]
            tip_amount_display = float(raw_amount_str)
            tip_amount_usd = convert_display_to_usd(tip_amount_display, display_currency)
            target_user_id = update.message.reply_to_message.from_user.id
            target_username = update.message.reply_to_message.from_user.username
        except (ValueError, IndexError):
             await update.message.reply_text("Usage (reply to a message): /tip amount")
             return
    elif len(message_text) == 3:
        try:
            target_username_str = normalize_username(message_text[1])
            raw_amount_str = message_text[2]
            tip_amount_display = float(raw_amount_str)
            tip_amount_usd = convert_display_to_usd(tip_amount_display, display_currency)
            target_user_id = username_to_userid.get(target_username_str)
            if not target_user_id:
                try:
                    chat = await context.bot.get_chat(target_username_str)
                    target_user_id = chat.id
                    target_username = chat.username
                except Exception:
                    await update.message.reply_text(f"User {target_username_str} not found.")
                    return
            else:
                # user_stats may not have a 'userinfo' subdict for very
                # old / partially-migrated rows — fall back to the
                # canonical-form username we already have.
                target_username = (
                    user_stats.get(target_user_id, {})
                    .get('userinfo', {})
                    .get('username')
                    or target_username_str.lstrip('@')
                )
        except (ValueError, IndexError):
            await update.message.reply_text("Usage: /tip @username amount")
            return
    else:
        await update.message.reply_text("Usage: /tip @username amount OR reply to a message with /tip amount")
        return

    if not target_user_id:
        await update.message.reply_text("Could not find the target user.")
        return

    is_owner = is_admin(user.id)
    if user.id == target_user_id and not is_owner:
        await update.message.reply_text("You cannot tip yourself.")
        return
    if tip_amount_usd <= 0:
        await update.message.reply_text("Tip amount must be positive.")
        return

    # Calculate crypto equivalent for confirmation
    active_coin = get_active_currency(user.id)
    price = LIVE_PRICES.get(active_coin, 1.0)
    crypto_amount = tip_amount_usd / price
    formatted_crypto = format_crypto_amount(crypto_amount, active_coin)
    tipped_user_mention = f"@{target_username}" if target_username else f"User (ID: {target_user_id})"

    # Display the tip in the sender's currency, plus a USDT estimate so
    # the receiver can eyeball the value regardless of their own setting.
    sender_display_str = format_display_amount(tip_amount_usd, display_currency)
    usdt_estimate_str = format_display_amount(tip_amount_usd, "USDT")

    # Store tip data for confirmation.
    #
    # We keep the existing per-user `context.user_data['pending_tip']`
    # entry (for backwards compatibility / single-process deployments)
    # AND mirror it into the module-level `pending_tips` registry in
    # core.foundation, keyed by tip_id.  The module-level registry
    # survives /reload of plugins, blue-green deploys, and any context
    # in which PTB recreated `context.user_data` between the /tip
    # command and the user tapping Confirm/Cancel.  Without this
    # mirror, the rightful sender was being told "This menu is not for
    # you." whenever the in-memory user_data dict had been recycled.
    tip_id = f"{user.id}_{target_user_id}_{int(datetime.now(timezone.utc).timestamp())}"
    pending_tip_entry = {
        'tip_id': tip_id,
        'sender_id': user.id,
        'target_user_id': target_user_id,
        'target_username': target_username,
        'tip_amount_usd': tip_amount_usd,
        'tip_amount_display': tip_amount_display,
        'display_currency': display_currency,
        'crypto_amount': crypto_amount,
        'coin': active_coin,
        'is_owner': is_owner,
        'created_ts': int(datetime.now(timezone.utc).timestamp()),
    }
    context.user_data['pending_tip'] = pending_tip_entry
    pending_tips_reg[tip_id] = pending_tip_entry

    # Opportunistic GC: drop stale entries so the dict can't grow
    # unbounded if users routinely abandon /tip prompts.
    _cutoff = int(datetime.now(timezone.utc).timestamp()) - PENDING_TTL
    for _stale_id in [
        _tid for _tid, _td in list(pending_tips_reg.items())
        if _td.get('created_ts', 0) < _cutoff
    ]:
        pending_tips_reg.pop(_stale_id, None)

    # Colorful premium-emoji confirm (green) / cancel (red) buttons.
    keyboard = [[
        apply_button_style(
            InlineKeyboardButton("Confirm", callback_data=f"confirm_tip_{tip_id}"),
            'success',
            peb('check'),
        ),
        apply_button_style(
            InlineKeyboardButton("Cancel", callback_data=f"cancel_tip_{tip_id}"),
            'danger',
            peb('cross'),
        ),
    ]]
    await update.message.reply_text(
        f"{pe('warning')} <b>Confirm Tip</b>\n\n"
        f"{pe(CURRENCY_EMOJI_KEY.get(display_currency, 'balance'))} "
        f"Sending: <b>{sender_display_str}</b> (~ {usdt_estimate_str} USDT)\n"
        f"{pe('gem')} Wallet debit: <b>{formatted_crypto} {active_coin}</b>\n"
        f"{pe('user')} To: {tipped_user_mention}\n\n"
        f"Please confirm or cancel.",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard),
    )

@check_banned
@check_maintenance
async def endrain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: instantly end the active rain in this chat.

    Iterates rains in this chat that are still ``active``, finalises each
    by reusing :func:`finalize_rain_job`. Idempotent — calling on a chat
    with no active rain replies politely.
    """
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("🚫 Admin only.")
        return
    chat_id = update.effective_chat.id
    db = global_deposit_db
    ended = 0
    try:
        # Pull active rains in this chat. We use the underlying conn pool
        # because there's no async helper to list rains by chat.
        conn = await db._get_conn()
        try:
            cur = await conn.execute(
                "SELECT rain_id, message_id FROM rains WHERE chat_id = ? AND status = 'active'",
                (chat_id,),
            )
            rows = await cur.fetchall()
        finally:
            await db._release_conn(conn)
    except Exception as e:
        logging.error(f"/endrain failed to query rains: {e}")
        rows = []

    for row in rows:
        rain_id, message_id = row[0], row[1]
        # Cancel any scheduled finaliser job. JobQueue may not be installed
        # — that's fine, we'll just let the no-op task notice the rain is
        # already completed when it wakes up.
        if context.job_queue is not None:
            for job in context.job_queue.get_jobs_by_name(f"rain_{rain_id}"):
                try:
                    job.schedule_removal()
                except Exception:
                    pass
        # Build a fake context object to reuse finalize_rain_job verbatim.
        fake_ctx = type('FakeCtx', (), {
            'bot': context.bot,
            'job': type('FakeJob', (), {'data': {
                'rain_id': rain_id,
                'chat_id': chat_id,
                'message_id': message_id,
            }})(),
        })()
        try:
            await finalize_rain_job(fake_ctx)
            ended += 1
        except Exception as e:
            logging.error(f"/endrain failed to finalise rain {rain_id}: {e}")

    if ended:
        await update.message.reply_text(
            f"{pe('check')} Ended {ended} active rain(s) in this chat."
        )
    else:
        await update.message.reply_text(
            f"{pe('warning')} No active rain in this chat."
        )


def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('rain', rain_command, block=False))
    app.add_handler(CommandHandler('endrain', endrain_command, block=False))
    app.add_handler(CommandHandler('tip', tip_command, block=False))
    app.add_handler(CommandHandler(['bal', 'balance'], balance_command, block=False))
    app.add_handler(CallbackQueryHandler(join_rain_callback, pattern='^join_rain_', block=False))

