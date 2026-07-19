"""P2P Escrow System — bot holds funds, releases on confirmation.

Flow:
  1. Seller uses /escrow <amount> @buyer (or reply to buyer's message)
  2. Bot shows deal in group with Accept (green) / Decline (red) buttons
  3. Bot pins the deal message
  4. Buyer taps Accept -> amount deducted from seller's wallet (held by bot)
  5. Release (seller only) -> final confirm -> amount credited to buyer
  6. Dispute (both) -> admins can /refund (back to seller) or /release (to buyer)
"""
from __future__ import annotations
from core.foundation import *
import secrets
from datetime import datetime, timezone

# ── Helpers ──────────────────────────────────────────────────────────────────

def _generate_escrow_id() -> str:
    return "ESC_" + secrets.token_hex(4).upper()


def _get_available_balance(user_id: int) -> float:
    currency = get_active_currency(user_id)
    wallet = ensure_wallet_dict(user_id)
    balance = wallet.get(currency, 0.0)
    locked = get_locked_balance_in_games(user_id)['total']
    price = LIVE_PRICES.get(currency, 1.0)
    locked_currency = locked / price if price > 0 else 0
    return max(0.0, balance - locked_currency)


def _format_deal_text(deal: dict, include_footer: bool = True) -> str:
    status_map = {
        'pending_acceptance': (pe('clock'), 'Pending Acceptance'),
        'active':             (pe('lock'), 'Active — Funds Held by Bot'),
        'completed':          (pe('check'), 'Completed'),
        'disputed':           (pe('warning'), 'Disputed — Awaiting Admin'),
        'cancelled':          (pe('cross'), 'Cancelled'),
        'refunded':           ('\U0001F9FE', 'Refunded to Seller'),
        'released_by_admin':  (pe('shield'), 'Released by Admin'),
    }
    emoji, status_str = status_map.get(deal['status'], (pe('escrow'), deal['status'].title()))

    lines = [
        f"{pe('escrow')} <b>Escrow Deal #{deal['id']}</b>\n",
        f"{pe('dollar')} <b>Amount:</b> {deal['amount']} {deal['currency']}",
        f"{pe('moneybag')} <b>Seller:</b> @{deal['seller_username']}",
        f"{pe('shopping')} <b>Buyer:</b> @{deal['buyer_username']}",
        f"{emoji} <b>Status:</b> {status_str}",
        f"{pe('clock')} <b>Created:</b> {deal['created_at']}",
    ]
    if deal.get('accepted_at'):
        lines.append(f"{pe('lock')} <b>Accepted:</b> {deal['accepted_at']}")
    if deal.get('completed_at'):
        lines.append(f"{pe('check')} <b>Completed:</b> {deal['completed_at']}")
    if include_footer:
        lines.append(f"\n{pe('star')} <i>This deal is secured by the bot.</i>")
    return "\n".join(lines)


async def _get_buyer_from_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[int, str] | None:
    """Extract buyer (user_id, username) from command reply or @mention."""
    msg = update.message
    if not msg:
        return None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        if not u.is_bot:
            return (u.id, u.username or str(u.id))
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "text_mention" and ent.user and not ent.user.is_bot:
                return (ent.user.id, ent.user.username or str(ent.user.id))
    return None


async def _notify_owner(context: ContextTypes.DEFAULT_TYPE, deal: dict):
    """Send DM to bot owner about new escrow deal."""
    for owner_id in BOT_OWNER_IDS:
        try:
            chat = await context.bot.get_chat(deal['group_id'])
            link = chat.invite_link or f"https://t.me/c/{str(deal['group_id']).replace('-100', '')}/{deal['pinned_message_id']}"
            await context.bot.send_message(
                chat_id=owner_id,
                text=(
                    f"{pe('escrow')} <b>New Escrow Deal</b>\n\n"
                    f"<b>ID:</b> <code>{deal['id']}</code>\n"
                    f"{pe('dollar')} Amount: {deal['amount']} {deal['currency']}\n"
                    f"{pe('moneybag')} Seller: @{deal['seller_username']}\n"
                    f"{pe('shopping')} Buyer: @{deal['buyer_username']}\n"
                    f"{pe('link')} <a href=\"{link}\">View in Group</a>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logging.error(f"Escrow notify owner {owner_id}: {e}")


# ── /escrow command ──────────────────────────────────────────────────────────

@check_banned
@check_maintenance
async def escrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    chat = update.effective_chat

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text(f"{pe('cross')} Escrow deals can only be created in groups.")
        return

    args = context.args
    if not args:
        await msg.reply_text(
            f"{pe('escrow')} <b>Usage:</b>\n"
            f"<code>/escrow amount @buyer</code>\n"
            f"<code>/escrow all @buyer</code> (entire available balance)\n"
            f"<code>/escrow half @buyer</code> (half of available balance)\n"
            f"<code>/escrow amount</code> (reply to buyer's message)",
            parse_mode=ParseMode.HTML,
        )
        return

    raw = args[0].lower()
    currency = get_active_currency(user.id)
    available = _get_available_balance(user.id)

    if raw == "all":
        amount = available
    elif raw == "half":
        amount = available / 2
    else:
        try:
            amount = float(raw.replace(',', ''))
            if amount <= 0:
                raise ValueError
        except (ValueError, IndexError):
            await msg.reply_text(f"{pe('cross')} Invalid amount. Please enter a positive number, 'all', or 'half'.")
            return

    if amount <= 0:
        await msg.reply_text(f"{pe('cross')} You have no available balance to escrow.", parse_mode=ParseMode.HTML)
        return

    if available < amount:
        await msg.reply_text(
            f"{pe('cross')} <b>Insufficient available balance.</b>\n\n"
            f"{pe('dollar')} Required: {amount} {currency}\n"
            f"{pe('money')} Available: {available:.2f} {currency}\n\n"
            f"{pe('lock')} Balance locked in active games is not counted.",
            parse_mode=ParseMode.HTML,
        )
        return

    buyer_info = await _get_buyer_from_command(update, context)
    if not buyer_info:
        await msg.reply_text(
            f"{pe('cross')} Could not identify buyer. Either reply to the buyer's message or @mention them.",
            parse_mode=ParseMode.HTML,
        )
        return

    buyer_id, buyer_username = buyer_info
    if buyer_id == user.id:
        await msg.reply_text(f"{pe('cross')} You cannot create an escrow deal with yourself.")
        return

    await ensure_user_in_wallets(user.id, user.username, context=context)
    await ensure_user_in_wallets(buyer_id, buyer_username, context=context)

    deal_id = _generate_escrow_id()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    deal = {
        'id': deal_id,
        'status': 'pending_acceptance',
        'amount': amount,
        'currency': currency,
        'seller_id': user.id,
        'seller_username': user.username or str(user.id),
        'buyer_id': buyer_id,
        'buyer_username': buyer_username,
        'group_id': chat.id,
        'group_title': chat.title or str(chat.id),
        'created_at': now,
        'accepted_at': '',
        'completed_at': '',
        'disputed_at': '',
        'disputed_by': 0,
    }

    escrow_deals[deal_id] = deal
    save_escrow_deal(deal_id)

    text = _format_deal_text(deal)
    keyboard = [
        [
            apply_button_style(InlineKeyboardButton("Accept", callback_data=f"es_accept_{deal_id}"), 'success', peb('check')),
        ],
        [
            apply_button_style(InlineKeyboardButton("Cancel Deal", callback_data=f"es_cancel_{deal_id}"), 'danger', peb('bust')),
        ],
    ]

    try:
        sent = await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        deal['pinned_message_id'] = sent.message_id
        save_escrow_deal(deal_id)
        try:
            await sent.pin(disable_notification=True)
        except Exception as e:
            logging.warning(f"Escrow: could not pin message: {e}")
        await _notify_owner(context, deal)
    except Exception as e:
        logging.error(f"Escrow: failed to send deal message: {e}", exc_info=True)
        escrow_deals.pop(deal_id, None)
        try:
            import os
            os.remove(os.path.join(ESCROW_DIR, f"{deal_id}.json"))
        except Exception:
            pass
        await msg.reply_text(f"{pe('cross')} Failed to create escrow deal. Please try again.")


# ── Callback handler ─────────────────────────────────────────────────────────

async def escrow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not data.startswith("es_"):
        return

    parts = data.split("_", 2)
    if len(parts) < 3:
        await query.answer("Invalid request.", show_alert=True)
        return

    action = parts[1]
    rest = parts[2]

    # deal_id always starts with "ESC_" — action may contain
    # underscores (e.g. confirm_release) so extract deal_id by
    # finding "ESC_" in the remainder.
    if rest.startswith("ESC_"):
        deal_id = rest
    elif "ESC_" in rest:
        esc_idx = rest.find("ESC_")
        # rebuild the action with the prefix (e.g. confirm_release)
        action = f"{action}_{rest[:esc_idx].rstrip('_')}"
        deal_id = rest[esc_idx:]
    else:
        await query.answer("Invalid request.", show_alert=True)
        return

    deal = escrow_deals.get(deal_id)
    if not deal:
        await query.answer("This escrow deal no longer exists.", show_alert=True)
        await safe_edit_message(query, f"{pe('cross')} Escrow deal not found.", parse_mode=ParseMode.HTML)
        return

    is_seller = user.id == deal['seller_id']
    is_buyer = user.id == deal['buyer_id']
    is_admin_user = is_admin(user.id)

    # ── Accept ──
    if action == "accept":
        if not is_buyer:
            await query.answer("Only the buyer can accept this deal.", show_alert=True)
            return
        if deal['status'] != 'pending_acceptance':
            await query.answer("This deal is no longer pending.", show_alert=True)
            return

        # Check seller still has balance
        available = _get_available_balance(deal['seller_id'])
        if available < deal['amount']:
            await query.answer("Seller no longer has sufficient balance to proceed.", show_alert=True)
            return

        await query.answer("Deal accepted! Holding funds...")

        # Deduct from seller (convert to USD for wallet functions)
        coin_price = LIVE_PRICES.get(deal['currency'], 1.0)
        usd_equiv = deal['amount'] * coin_price
        try:
            deduct_wallet(deal['seller_id'], usd_equiv, deal['currency'])
        except ValueError:
            await query.answer("Seller has insufficient funds now.", show_alert=True)
            return

        deal['status'] = 'active'
        deal['accepted_at'] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        save_escrow_deal(deal_id)

        text = _format_deal_text(deal)
        keyboard = [
            [
                apply_button_style(InlineKeyboardButton("Release All", callback_data=f"es_release_{deal_id}"), 'success', peb('check')),
                apply_button_style(InlineKeyboardButton("Dispute", callback_data=f"es_dispute_{deal_id}"), 'danger', peb('warning')),
            ],
        ]
        await safe_edit_message(query, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        await query.message.reply_text(
            f"{pe('check')} <b>Deal Accepted!</b>\n\n"
            f"{pe('lock')} The amount of <b>{deal['amount']} {deal['currency']}</b> is now held by the bot.\n"
            f"@{deal['seller_username']} can release the funds when ready.",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Decline ──
    if action == "decline":
        if not is_buyer:
            await query.answer("Only the buyer can decline this deal.", show_alert=True)
            return
        if deal['status'] != 'pending_acceptance':
            await query.answer("This deal is no longer pending.", show_alert=True)
            return

        await query.answer("Deal declined.")
        deal['status'] = 'cancelled'
        save_escrow_deal(deal_id)

        await safe_edit_message(
            query,
            _format_deal_text(deal, include_footer=False),
            parse_mode=ParseMode.HTML,
        )
        await query.message.reply_text(
            f"{pe('cross')} @{deal['buyer_username']} declined the escrow deal #{deal_id}.",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Cancel (seller cancels while pending) ──
    if action == "cancel":
        if not is_seller:
            await query.answer("Only the seller can cancel this deal.", show_alert=True)
            return
        if deal['status'] != 'pending_acceptance':
            await query.answer("This deal cannot be cancelled at this stage.", show_alert=True)
            return

        await query.answer("Deal cancelled.")
        deal['status'] = 'cancelled'
        save_escrow_deal(deal_id)

        await safe_edit_message(
            query,
            _format_deal_text(deal, include_footer=False),
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Release (seller initiates release) ──
    if action == "release":
        if not is_seller:
            await query.answer("Only the seller can release funds.", show_alert=True)
            return
        if deal['status'] != 'active':
            await query.answer("This deal is not in active state.", show_alert=True)
            return

        await query.answer()
        text = (
            f"{pe('warning')} <b>Final Confirmation Required</b>\n\n"
            f"You are about to release <b>{deal['amount']} {deal['currency']}</b> "
            f"to @{deal['buyer_username']}.\n\n"
            f"{pe('cross')} <i>This action cannot be undone.</i>"
        )
        keyboard = [
            [
                apply_button_style(InlineKeyboardButton("Confirm Release", callback_data=f"es_confirm_release_{deal_id}"), 'success', peb('check')),
                apply_button_style(InlineKeyboardButton("Cancel", callback_data=f"es_cancel_release_{deal_id}"), 'danger', peb('cross')),
            ],
        ]
        await safe_edit_message(query, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ── Confirm Release ──
    if action == "confirm_release":
        if not is_seller:
            await query.answer("Only the seller can confirm release.", show_alert=True)
            return
        if deal['status'] != 'active':
            await query.answer("This deal is no longer active.", show_alert=True)
            return

        await query.answer("Funds released!")

        coin_price = LIVE_PRICES.get(deal['currency'], 1.0)
        usd_equiv = deal['amount'] * coin_price
        credit_wallet(deal['buyer_id'], usd_equiv, deal['currency'])
        deal['status'] = 'completed'
        deal['completed_at'] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        save_escrow_deal(deal_id)

        await safe_edit_message(
            query,
            _format_deal_text(deal),
            parse_mode=ParseMode.HTML,
        )
        try:
            await query.message.reply_text(
                f"{pe('trophy')} <b>Escrow Deal Completed!</b>\n\n"
                f"{pe('dollar')} <b>{deal['amount']} {deal['currency']}</b> has been released to @{deal['buyer_username']}.\n\n"
                f"{pe('star')} Deal #{deal['id']} is now closed.",
                parse_mode=ParseMode.HTML,
            )
            await context.bot.send_message(
                chat_id=deal['buyer_id'],
                text=(
                    f"{pe('trophy')} <b>Escrow Received!</b>\n\n"
                    f"@{deal['seller_username']} has released <b>{deal['amount']} {deal['currency']}</b> to you.\n\n"
                    f"\U0001F9FE Deal ID: <code>{deal['id']}</code>\n"
                    f"Use /balance to check your updated balance.",
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logging.error(f"Escrow release notification: {e}")
        return

    # ── Cancel Release (seller backs out of confirm) ──
    if action == "cancel_release":
        if not is_seller:
            await query.answer()
            return
        if deal['status'] != 'active':
            await query.answer()
            return

        await query.answer("Release cancelled.")
        text = _format_deal_text(deal)
        keyboard = [
            [
                apply_button_style(InlineKeyboardButton("Release All", callback_data=f"es_release_{deal_id}"), 'success', peb('check')),
                apply_button_style(InlineKeyboardButton("Dispute", callback_data=f"es_dispute_{deal_id}"), 'danger', peb('warning')),
            ],
        ]
        await safe_edit_message(query, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # ── Dispute ──
    if action == "dispute":
        if not is_seller and not is_buyer and not is_admin_user:
            await query.answer("You are not part of this deal.", show_alert=True)
            return
        if deal['status'] != 'active':
            await query.answer("This deal cannot be disputed at this stage.", show_alert=True)
            return

        await query.answer("Dispute raised. Admins have been notified.")

        deal['status'] = 'disputed'
        deal['disputed_at'] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        deal['disputed_by'] = user.id
        save_escrow_deal(deal_id)

        await safe_edit_message(
            query,
            _format_deal_text(deal),
            parse_mode=ParseMode.HTML,
        )
        await query.message.reply_text(
            f"{pe('warning')} <b>Dispute Raised</b>\n\n"
            f"@{user.username or user.id} has disputed escrow deal #{deal_id}.\n"
            f"The funds are locked. An admin will review and take action.",
            parse_mode=ParseMode.HTML,
        )

        for owner_id in BOT_OWNER_IDS:
            try:
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"{pe('warning')} <b>Escrow Dispute</b>\n\n"
                        f"<b>Deal:</b> <code>{deal['id']}</code>\n"
                        f"{pe('dollar')} Amount: {deal['amount']} {deal['currency']}\n"
                        f"{pe('moneybag')} Seller: @{deal['seller_username']}\n"
                        f"{pe('shopping')} Buyer: @{deal['buyer_username']}\n"
                        f"{pe('bust')} Disputed by: @{user.username or user.id}\n\n"
                        f"Use /escrowinfo {deal['id']} to review.\n"
                        f"Use /refund {deal['id']} to return to seller.\n"
                        f"Use /release {deal['id']} to release to buyer.",
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logging.error(f"Escrow dispute notify owner {owner_id}: {e}")
        return


# ── Admin commands ───────────────────────────────────────────────────────────

@check_banned
async def escrowinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(f"{pe('cross')} Admin only.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(f"{pe('cross')} Usage: /escrowinfo ESC_ID")
        return

    deal_id = args[0].upper()
    deal = escrow_deals.get(deal_id)
    if not deal:
        await update.message.reply_text(f"{pe('cross')} Escrow deal {deal_id} not found.")
        return

    await update.message.reply_text(
        _format_deal_text(deal),
        parse_mode=ParseMode.HTML,
    )


async def _admin_escrow_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    """Handle /refund and /release admin commands for disputed deals."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(f"{pe('cross')} Admin only.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            f"{pe('cross')} Usage: /{action} ESC_ID",
            parse_mode=ParseMode.HTML,
        )
        return

    deal_id = args[0].upper()
    deal = escrow_deals.get(deal_id)
    if not deal:
        await update.message.reply_text(f"{pe('cross')} Escrow deal {deal_id} not found.")
        return

    if deal['status'] != 'disputed':
        await update.message.reply_text(
            f"{pe('cross')} This deal is not disputed. Current status: {deal['status']}",
            parse_mode=ParseMode.HTML,
        )
        return

    if action == "refund":
        coin_price = LIVE_PRICES.get(deal['currency'], 1.0)
        usd_equiv = deal['amount'] * coin_price
        credit_wallet(deal['seller_id'], usd_equiv, deal['currency'])
        deal['status'] = 'refunded'
        deal['completed_at'] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        save_escrow_deal(deal_id)

        await update.message.reply_text(
            f"{pe('check')} <b>Deal Refunded</b>\n\n"
            f"{deal['amount']} {deal['currency']} returned to @{deal['seller_username']}.",
            parse_mode=ParseMode.HTML,
        )

        try:
            await context.bot.send_message(
                chat_id=deal['seller_id'],
                text=(
                    f"\U0001F9FE <b>Escrow Refunded</b>\n\n"
                    f"Admin has refunded <b>{deal['amount']} {deal['currency']}</b> back to you.\n"
                    f"Deal #{deal_id} has been closed.",
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logging.error(f"Escrow refund notify seller: {e}")

    elif action == "release":
        coin_price = LIVE_PRICES.get(deal['currency'], 1.0)
        usd_equiv = deal['amount'] * coin_price
        credit_wallet(deal['buyer_id'], usd_equiv, deal['currency'])
        deal['status'] = 'released_by_admin'
        deal['completed_at'] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        save_escrow_deal(deal_id)

        await update.message.reply_text(
            f"{pe('check')} <b>Deal Released by Admin</b>\n\n"
            f"{deal['amount']} {deal['currency']} released to @{deal['buyer_username']}.",
            parse_mode=ParseMode.HTML,
        )

        try:
            await context.bot.send_message(
                chat_id=deal['buyer_id'],
                text=(
                    f"{pe('shield')} <b>Escrow Released by Admin</b>\n\n"
                    f"Admin has released <b>{deal['amount']} {deal['currency']}</b> to you.\n"
                    f"Deal #{deal_id} has been closed.",
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logging.error(f"Escrow release notify buyer: {e}")

    # Update the group message
    try:
        group_id = deal['group_id']
        msg_id = deal.get('pinned_message_id')
        if group_id and msg_id:
            await context.bot.edit_message_text(
                chat_id=group_id,
                message_id=msg_id,
                text=_format_deal_text(deal),
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        logging.warning(f"Escrow: could not update group message after admin action: {e}")


@check_banned
async def escrow_refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _admin_escrow_action(update, context, "refund")


@check_banned
async def escrow_release_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _admin_escrow_action(update, context, "release")


# ── Plugin registration ─────────────────────────────────────────────────────

def register(ctx):
    app = ctx.application
    app.add_handler(CommandHandler("escrow", escrow_command, block=False))
    app.add_handler(CallbackQueryHandler(escrow_callback, pattern=r"^es_", block=False))
    # Admin commands
    app.add_handler(CommandHandler("escrowinfo", escrowinfo_command, block=False))
    app.add_handler(CommandHandler("refund", escrow_refund_command, block=False))
    app.add_handler(CommandHandler("release", escrow_release_admin_command, block=False))
