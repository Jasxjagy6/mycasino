"""Auto-split from bot.py — plugins.general."""
from __future__ import annotations
from core import foundation as _foundation  # for late-bound module-level lookups
from core.foundation import *  # noqa: F401, F403


def _ensure_pending_tips_registry():
    """Mirror of plugins.wallet_commands._ensure_pending_tips_registry.

    Lazily attaches ``pending_tips`` / ``PENDING_TIP_TTL_SECONDS`` onto
    the live ``core.foundation`` module if a hot-reload of this plugin
    happened against an older foundation revision (foundation itself
    cannot be reloaded in production because that would reset
    ``user_stats``/``user_wallets``).
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
    globals()["pending_tips"] = reg
    globals()["PENDING_TIP_TTL_SECONDS"] = ttl
    return reg, ttl


try:
    _ensure_pending_tips_registry()
except Exception:
    pass

@check_banned
@check_maintenance
async def chicken_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /chicken command — shows Chicken Road Mini App inline button."""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context,
                                  first_name=user.first_name)

    if not is_game_enabled("chicken_road"):
        await update.message.reply_text(
            "\U0001f527 <b>Chicken Road</b> is currently under maintenance. Try again later.",
            parse_mode=ParseMode.HTML
        )
        return

    cr_url = _get_chicken_road_web_url() if CHICKEN_ROAD_WEB_ENABLED else None

    if cr_url and update.effective_chat.type == "private":
        from telegram import WebAppInfo
        keyboard = [[InlineKeyboardButton(
            "\U0001f414 Play Chicken Road",
            web_app=WebAppInfo(url=cr_url)
        )]]
        await update.message.reply_text(
            "\U0001f414 <b>CHICKEN ROAD</b>\n\n"
            "Cross the dungeon road — hop over manholes — cash out before fire!\n\n"
            "\U0001f3b2 4 modes: Easy / Medium / Hard / Hardcore\n"
            "\U0001f4b0 RTP: 98% | Max Win: $20,000 | Provably Fair",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif cr_url:
        bot_username = await get_bot_username(context)
        deep_link    = f"https://t.me/{bot_username}?start=chickenroad"
        keyboard     = [[InlineKeyboardButton("Open Chicken Road", url=deep_link)]]
        await update.message.reply_text(
            "\U0001f414 <b>CHICKEN ROAD</b>\n"
            "Available in private chat! Tap below to open.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "\U0001f414 <b>CHICKEN ROAD</b>\n\n"
            "Web game not yet configured. Contact admin.",
            parse_mode=ParseMode.HTML
        )

async def maxbet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /maxbet and /limits commands - show dynamic max bet limits."""
    user = update.effective_user
    house_bal = bot_settings.get("house_balance", 100_000_000_000_000.0)

    standard_limit = round(house_bal * 0.006, 2)
    special_limit = round(house_bal * 0.003, 2)

    # Generate PIL image for max bet limits
    try:
        img = Image.new('RGB', (600, 420), color=(15, 15, 30))
        draw = ImageDraw.Draw(img)

        # Try to load font
        try:
            font_title = ImageFont.truetype(DASHBOARD_FONT_PATH, 28)
            font_header = ImageFont.truetype(DASHBOARD_FONT_PATH, 20)
            font_body = ImageFont.truetype(DASHBOARD_FONT_PATH, 16)
            font_small = ImageFont.truetype(DASHBOARD_FONT_PATH, 13)
        except Exception:
            font_title = ImageFont.load_default()
            font_header = font_title
            font_body = font_title
            font_small = font_title

        # Title
        draw.text((30, 20), "MAX BET LIMITS", fill=(255, 215, 0), font=font_title)
        draw.text((30, 55), "@playcsino | Telegram Casino", fill=(150, 150, 170), font=font_small)

        # Divider
        draw.line([(30, 80), (570, 80)], fill=(60, 60, 80), width=2)

        # Standard games section
        y = 100
        draw.text((30, y), "STANDARD GAMES", fill=(0, 200, 255), font=font_header)
        y += 30
        draw.text((30, y), f"Limit: ${standard_limit:,.2f}", fill=(0, 255, 100), font=font_body)
        y += 25
        draw.text((30, y), "0.6% of house balance", fill=(120, 120, 150), font=font_small)
        y += 20
        draw.text((30, y), "Games: Roulette, Blackjack, Crash, Dice, Plinko,", fill=(180, 180, 200), font=font_small)
        y += 18
        draw.text((30, y), "Limbo, 7Up, Rush, Chicken Road, Slots, Coinflip", fill=(180, 180, 200), font=font_small)

        # Divider
        y += 30
        draw.line([(30, y), (570, y)], fill=(60, 60, 80), width=1)

        # Special games section
        y += 15
        draw.text((30, y), "SPECIAL GAMES", fill=(255, 165, 0), font=font_header)
        y += 30
        draw.text((30, y), f"Limit: ${special_limit:,.2f}", fill=(0, 255, 100), font=font_body)
        y += 25
        draw.text((30, y), "0.3% of house balance", fill=(120, 120, 150), font=font_small)
        y += 20
        draw.text((30, y), "Games: Mines, Tower, Keno, HiLo", fill=(180, 180, 200), font=font_small)

        # Divider
        y += 30
        draw.line([(30, y), (570, y)], fill=(60, 60, 80), width=1)

        # PvP section
        y += 15
        draw.text((30, y), "PVP EMOJI GAMES", fill=(200, 100, 255), font=font_header)
        y += 30
        draw.text((30, y), "No Limit", fill=(0, 255, 100), font=font_body)
        y += 25
        draw.text((30, y), "Player vs Player - no house risk", fill=(120, 120, 150), font=font_small)

        # Footer
        draw.line([(30, 390), (570, 390)], fill=(60, 60, 80), width=1)
        draw.text((30, 398), "Play smart, win big! Limits adjust dynamically.", fill=(100, 100, 130), font=font_small)

        bio = BytesIO()
        img.save(bio, 'PNG', optimize=True)
        bio.seek(0)

        await update.message.reply_photo(
            photo=bio,
            caption=f"{pe('chart')} <b>Dynamic Max Bet Limits</b>\n\nLimits adjust automatically based on house balance.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Error generating maxbet image: {e}")
        # Fallback to text
        await update.message.reply_text(
            f"{pe('chart')} <b>MAX BET LIMITS</b>\n\n"
            f"<b>STANDARD GAMES</b> (0.6% of house balance)\n"
            f"Limit: <b>${standard_limit:,.2f}</b>\n"
            f"Roulette, Blackjack, Crash, Dice, Plinko, Limbo, 7Up, Rush, Chicken, Slots\n\n"
            f"<b>SPECIAL GAMES</b> (0.3% of house balance)\n"
            f"Limit: <b>${special_limit:,.2f}</b>\n"
            f"Mines, Tower, Keno, HiLo\n\n"
            f"<b>PVP EMOJI GAMES</b>\n"
            f"No Limit (player vs player)\n\n"
            f"<i>Limits adjust dynamically based on house balance.</i>",
            parse_mode=ParseMode.HTML
        )

@check_banned
@check_maintenance
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    ## NEW FEATURE ##
    # Handle deep linking for referrals and escrow
    referrer_id = None
    if context.args and len(context.args) > 0:
        deep_link_arg = context.args[0]
        if deep_link_arg.startswith("ref_"):
            try:
                referrer_id = int(deep_link_arg.replace("ref_", ""))
                if referrer_id == user.id: # Can't refer yourself
                    referrer_id = None
                else:
                    # Notify referrer
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"{pe('win')} New referral! {user.mention_html()} has joined using your link.",
                        parse_mode=ParseMode.HTML
                    )
            except (ValueError, TypeError, BadRequest, Forbidden):
                referrer_id = None # Invalid referral ID or can't message

        elif deep_link_arg.startswith("escrow_"):
            deal_id = deep_link_arg.replace("escrow_", "")
            await handle_escrow_deep_link(update, context, deal_id)
            return

        elif deep_link_arg.startswith("provablyfair_"):
            pf_id = deep_link_arg.replace("provablyfair_", "")
            await handle_provably_fair_deep_link(update, context, pf_id)
            return

        elif deep_link_arg == "deposit":
            await ensure_user_in_wallets(user.id, user.username, None, context, user.first_name)
            await deposit_command(update, context)
            return

        elif deep_link_arg == "withdraw":
            await ensure_user_in_wallets(user.id, user.username, None, context, user.first_name)
            # Show withdraw info in DM
            user_currency = get_user_currency(user.id)
            formatted_balance = format_balance_with_locked(user.id, user_currency)
            await update.message.reply_text(
                f"{pe('withdraw')} <b>Withdraw</b>\n\n"
                f"<b>Your Balance:</b> {formatted_balance}\n\n"
                f"Use /withdraw to start a withdrawal.",
                parse_mode=ParseMode.HTML
            )
            return

        elif deep_link_arg == "plinko":
            await ensure_user_in_wallets(user.id, user.username, context=context)
            if PLINKO_WEB_ENABLED and _get_plinko_web_url():
                from telegram import WebAppInfo
                plinko_web_url = _get_plinko_web_url()
                keyboard = [[InlineKeyboardButton(
                    "Open Plinko",
                    web_app=WebAppInfo(url=plinko_web_url)
                )]]
                await update.message.reply_text(
                    f"{pe('plinko')} <b>PLINKO</b>\n\n"
                    f"Drop the ball and win big!\n\n"
                    f"Tap below to open the Plinko web dashboard:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(
                    f"{pe('plinko')} <b>PLINKO</b>\n\n"
                    f"Usage: /plinko amount risk\n"
                    f"Risk: low, medium, or high\n"
                    f"Example: /plinko 5 medium",
                    parse_mode=ParseMode.HTML
                )
            return

        elif deep_link_arg == "chickenroad":
            await ensure_user_in_wallets(user.id, user.username, context=context)
            if CHICKEN_ROAD_WEB_ENABLED and _get_chicken_road_web_url():
                cr_web_url = _get_chicken_road_web_url()
                from telegram import WebAppInfo
                keyboard = [[InlineKeyboardButton("🐔 Play Chicken Road",
                                                   web_app=WebAppInfo(url=cr_web_url))]]
                await update.message.reply_text(
                    "🐔 <b>CHICKEN ROAD</b>\n\nCross the dungeon to win big!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text("Chicken Road is not available.", parse_mode=ParseMode.HTML)
            return

    await ensure_user_in_wallets(user.id, user.username, referrer_id, context, user.first_name)

    # Check if user is banned
    user_lang = get_user_lang(user.id)
    if user.id in bot_settings.get("banned_users", []):
        await update.message.reply_text(get_text("banned_user", user_lang))
        return

    # Get user's preferred currency
    user_currency = get_user_currency(user.id)
    formatted_balance = format_balance_with_locked(user.id, user_currency)

    # Get total wagers for display
    stats = user_stats.get(user.id, {})
    total_wagered = stats.get('bets', {}).get('amount', 0.0)
    formatted_wagers = format_currency(total_wagered, user_currency)

    # Check if in group chat
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

        # Simplified balance: Balance: $X (X' COIN)
        active_coin = get_active_currency(user.id)
        balance_usd = get_active_balance_usd(user.id)
        wallet = ensure_wallet_dict(user.id)
        crypto_balance = wallet.get(active_coin, 0.0)
        formatted_crypto = format_crypto_amount(crypto_balance, active_coin)

        welcome_text = (
            f"{pe('balance')} <b>Balance:</b> ${balance_usd:,.2f} ({formatted_crypto} {active_coin})"
        )

        reply_markup = create_styled_keyboard(keyboard)

        if update.message:
            sent_message = await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            set_menu_owner(sent_message, user.id)
        return

    # DM: Original behavior
    # NEW UI STRUCTURE - Casino themed with COLORED buttons (Bot API 9.4)
    # Build Plinko WebApp URL using centralized helper
    plinko_web_url = _get_plinko_web_url() if PLINKO_WEB_ENABLED else None

    keyboard = [
        # Row 0: Plinko Web Dashboard (NEW - above deposit/withdraw)
    ]

    # Add Plinko WebApp button if web dashboard is enabled and URL is configured
    if plinko_web_url:
        from telegram import WebAppInfo
        plinko_btn = InlineKeyboardButton(
            "Plinko",
            web_app=WebAppInfo(url=plinko_web_url)
        )
        keyboard.append([apply_button_style(plinko_btn, None, peb('withdraw'))])

    keyboard.extend([
        # Row 1: Deposit & Withdraw with styles
        [
            apply_button_style(InlineKeyboardButton("Deposit", callback_data="main_deposit"), 'primary', peb('deposit')),  # BLUE
            apply_button_style(InlineKeyboardButton("Withdraw", callback_data="main_withdraw"), 'success', peb('withdraw'))  # GREEN
        ],
        # Row 2: Games & More with styles
        [
            apply_button_style(InlineKeyboardButton("Games", callback_data="main_games"), 'primary', peb('game')),  # BLUE
            apply_button_style(InlineKeyboardButton("More", callback_data="main_more"), 'danger', peb('chart'))  # RED
        ],
        # Row 3: Settings
    ])

    # Add Settings button only in DMs
    if update.effective_chat.type == "private":
        keyboard.append([apply_button_style(InlineKeyboardButton("Settings", callback_data="main_settings"), 'success', peb('settings'))])  # GREEN

    # Row 5: Admin Dashboard (only for admin)
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton(get_text("admin_panel", user_lang), callback_data="admin_dashboard").to_dict()])

    # Get total wagers for display
    stats = user_stats.get(user.id, {})
    total_wagered = stats.get('bets', {}).get('amount', 0.0)
    formatted_wagers = format_currency(total_wagered, user_currency)

    # Create links row - Only show in DMs to avoid spam in groups
    if update.effective_chat.type == "private":
        links_row = []
        if LINK_PORTAL:
            links_row.append(InlineKeyboardButton("Portal", url=LINK_PORTAL).to_dict())
        if LINK_CHANNEL:
            links_row.append(InlineKeyboardButton("Channel", url=LINK_CHANNEL).to_dict())

        links_row_2 = []
        if LINK_CHAT:
            links_row_2.append(InlineKeyboardButton("Chat", url=LINK_CHAT).to_dict())
        if LINK_SUPPORT:
            links_row_2.append(InlineKeyboardButton("Support", url=LINK_SUPPORT).to_dict())

        # Add links rows if they have buttons
        if links_row:
            keyboard.append(links_row)
        if links_row_2:
            keyboard.append(links_row_2)

    welcome_text = (
        f"{pe('casino')} <b>Welcome to @playcsino</b>  {pe('lightning')}\n"
        f"<i>Telegram Casino</i>\n\n"
        f"{pe('balance')} <b>Balance:</b> {formatted_balance}\n"
        f"{pe('chart')} <b>Wagered:</b> {formatted_wagers}\n\n"
        f"{pe('plinko')} Try <b>Plinko</b> & 🐔 <b>Chicken Road</b> - new games!\n"
        f"{pe('game')} Pick an option to get started!"
    )

    # Create styled keyboard using helper function
    reply_markup = create_styled_keyboard(keyboard)

    # Send dashboard image with caption text below
    caption_text = f"{pe('down_arrow')} Please choose an option to start"
    dashboard_image = await generate_dashboard_image(user.id, context)
    if dashboard_image and update.message:
        try:
            sent_message = await update.message.reply_photo(
                photo=dashboard_image,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            set_menu_owner(sent_message, user.id)
        except Exception as e:
            logging.error(f"Error sending dashboard image: {e}")
            sent_message = await update.message.reply_text(
                caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            set_menu_owner(sent_message, user.id)
    elif update.message:
        sent_message = await update.message.reply_text(
            caption_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        set_menu_owner(sent_message, user.id)
    elif update.callback_query:
         await safe_edit_message(
            update.callback_query,
            caption_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
         set_menu_owner(update.callback_query.message, user.id)

@check_banned
@check_maintenance
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()
    data = query.data
    user = query.from_user

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if user.id in bot_settings.get("banned_users", []):
        await query.answer("You are banned.", show_alert=True)
        return
    if user.id in bot_settings.get("tempbanned_users", []):
        await query.answer("You are temporarily banned.", show_alert=True)
        return

    if data == "main_deposit":
        # Show deposit menu
        if not DEPOSIT_ENABLED:
            await safe_edit_message(
                query,
                "❌ Deposits are currently disabled.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data="back_to_main")]])
            )
            return

        text, keyboard = build_deposit_menu()
        await safe_edit_message(query, text, reply_markup=create_styled_keyboard(keyboard), parse_mode=ParseMode.HTML)
        return

    elif data == "main_withdraw":
        # NEW: Check if withdrawals are enabled
        if not bot_settings.get("withdrawals_enabled", True):
            await safe_edit_message(
                query,
                "❌ <b>Withdrawals Disabled</b>\n\n"
                "Withdrawals are temporarily disabled by the administrator. "
                "Please contact support for more information.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data="back_to_main")]])
            )
            return

        if user.id in bot_settings.get("tempbanned_users", []):
            await safe_edit_message(
                query,
                "❌ <b>Withdrawals Disabled</b>\n\n"
                "Your account is currently restricted from making withdrawals. "
                "Please contact support for more information.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data="back_to_main")]])
            )
            return

        # Check if withdrawal address is set
        withdrawal_address = user_stats[user.id].get("withdrawal_address")
        if not withdrawal_address:
            await safe_edit_message(
                query,
                "💳 <b>Withdrawal Address Not Set</b>\n\n"
                "Please set your USDT-BEP20 withdrawal address in Settings first before requesting a withdrawal.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Go to Settings", callback_data="main_settings")],
                    [InlineKeyboardButton("Back to Main Menu", callback_data="back_to_main")]
                ])
            )
            return

        # Ask for withdrawal: Step 1 - Select crypto
        wallet = ensure_wallet_dict(user.id)
        keyboard = []
        for coin in SUPPORTED_CRYPTOS:
            bal = wallet.get(coin, 0.0)
            price = LIVE_PRICES.get(coin, 1.0)
            usd_val = bal * price
            if usd_val > 0.01:
                symbol = CRYPTO_SYMBOLS.get(coin, "💎")
                formatted = format_crypto_amount(bal, coin)
                keyboard.append([InlineKeyboardButton(
                    f"{symbol} {coin} - ${usd_val:,.2f} ({formatted})",
                    callback_data=f"withdraw_coin_{coin}"
                )])
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="back_to_main")])

        if len(keyboard) <= 1:
            await safe_edit_message(
                query,
                "❌ <b>No Balance</b>\n\nYou don't have any crypto balance to withdraw.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_to_main")]])
            )
            return

        await safe_edit_message(
            query,
            f"{pe('withdraw')} <b>Withdrawal - Select Coin</b>\n\n"
            f"<b>Withdrawal Address:</b> <code>{withdrawal_address}</code>\n\n"
            f"Select the crypto you want to withdraw:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    elif data == "main_games":
        await games_menu(update, context)

    elif data == "main_wallet":
        wallet = ensure_wallet_dict(user.id)
        total_usd = get_total_balance_usd(user.id)
        active_coin = get_active_currency(user.id)
        stats = user_stats.get(user.id, {})
        total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
        total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))

        # Build multi-currency wallet display
        portfolio_lines = []
        for coin, amount in wallet.items():
            if amount > 0.0 or coin == active_coin:
                price = LIVE_PRICES.get(coin, 1.0)
                usd_val = amount * price
                formatted = format_crypto_amount(amount, coin)
                coin_pe = pe({'USDT':'balance','BTC':'money','ETH':'gem','SOL':'coin','BNB':'diamond','TRX':'diamond','LTC':'coin'}.get(coin, 'gem'))
                if usd_val > 0.001 or coin == active_coin:
                    portfolio_lines.append(f"{coin_pe} {coin}: ${usd_val:,.2f} ({formatted} {coin})")

        wallet_text = (
            f"{pe('briefcase')} <b>Your Wallet</b>\n\n"
            f"{pe('briefcase')} Total Portfolio: <b>${total_usd:,.2f}</b>\n\n"
            + "\n".join(portfolio_lines) + "\n\n"
            f"{pe('diamond')} Active Currency: {active_coin}\n"
            f"{pe('dice')} Total Wagered: ${stats.get('bets', {}).get('amount', 0.0):,.2f}\n"
            f"{pe('trophy')} Wins: {stats.get('bets', {}).get('wins', 0)}\n"
            f"{pe('lose')} Losses: {stats.get('bets', {}).get('losses', 0)}\n"
            f"{pe('stats')} P&L: <b>${stats.get('pnl', 0.0):,.2f}</b>\n"
            f"{pe('balance')} Total Deposited: ${total_deposits:,.2f}\n"
            f"{pe('withdraw')} Total Withdrawn: ${total_withdrawals:,.2f}"
        )

        keyboard = [
            [InlineKeyboardButton("Withdraw", callback_data="main_withdraw")],
            [InlineKeyboardButton("My Game Matches", callback_data="my_history_0")],
            [InlineKeyboardButton("Transactions", callback_data="my_transactions")],
            [InlineKeyboardButton("Back to More", callback_data="main_more")]
        ]

        # Send dashboard image with wallet text as new message (callback can't edit to photo)
        dashboard_image = await generate_dashboard_image(user.id, context)
        if dashboard_image:
            try:
                sent_msg = await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=dashboard_image,
                    caption=wallet_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                set_menu_owner(sent_msg, user.id)
                # Delete the old message
                try:
                    await query.message.delete()
                except Exception as del_err:
                    logging.warning(f"Could not delete old message: {del_err}")
            except Exception as e:
                logging.error(f"Error sending dashboard image: {e}")
                # Fallback to editing text
                await safe_edit_message(
                    query,
                    wallet_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        else:
            # No image, just edit text
            await safe_edit_message(
                query,
                wallet_text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    ## NEW FEATURE ##
    elif data == "main_leaderboard":
        await leaderboard_command(update, context, from_callback=True)

    ## NEW FEATURE ##
    elif data == "main_referral":
        await referral_command(update, context, from_callback=True)

    elif data == "main_support":
        await safe_edit_message(
            query,
            "🆘 <b>Support</b>\n\n"
            "Need help or have questions?\n"
            "Contact the bot owner:\n\n"
            "👤 @jashanxjagy\n\n"
            "We're here to help you 24/7!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to More", callback_data="main_more")]])
        )

    elif data == "main_help":
        await help_command(update, context, from_callback=True)

    elif data == "main_info":
        info_text = (
            "ℹ️ <b>Casino Rules & Info</b>\n\n"
            "<b>🎰 General Rules:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• All games use provably fair system\n"
            "• No refunds on completed bets\n"
            "• Contact support for disputes\n\n"
            "<b>🛡️ Escrow Rules:</b>\n"
            "• Use /escrow to start a secure trade.\n"
            "• Seller deposits funds into bot's secure wallet.\n"
            "• Buyer confirms receipt of goods/services.\n"
            "• Seller releases funds to the buyer.\n"
            "• All transactions are on the blockchain.\n\n"
            "<b>⚠️ Responsible Gaming:</b>\n"
            "• Only bet what you can afford to lose\n"
            "• Set personal limits\n"
            "• Contact support if you need help"
        )
        await safe_edit_message(
            query,
            info_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to More", callback_data="main_more")]])
        )

    ## NEW FEATURE ##
    elif data == "main_level":
        await level_command(update, context, from_callback=True)

    ## NEW FEATURE ##
    elif data == "main_settings":
        await settings_command(update, context)

    elif data == "main_more":
        await more_menu(update, context)

    elif data.startswith("more_page_"):
        page = int(data.split("_")[-1])
        await more_menu(update, context, page)

    elif data == "main_daily":
        await daily_command(update, context, from_callback=True)

    elif data == "main_bonuses":
        await bonuses_menu(update, context)

    elif data == "main_achievements":
        await achievements_command(update, context, from_callback=True)

    elif data == "main_claim_gift":
        await safe_edit_message(
            query,
            "🎟️ <b>Claim Gift Code</b>\n\n"
            "Use the command:\n<code>/claim YOUR_CODE</code>\n\n"
            "Example: <code>/claim AB3X7</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to More", callback_data="main_more")]])
        )

    elif data == "main_stats":
        await stats_command(update, context, from_callback=True)

    elif data == "back_to_main":
        await query.answer()  # Acknowledge the button press
        await start_command_inline(query, context)

    elif data.startswith("my_history"):
        page = int(data.split('_')[-1])
        # Show history command output for game matches
        await _show_wallet_history(update, context, query, page)

    elif data == "my_transactions":
        # Show transactions command output
        await _show_wallet_transactions(update, context, query)


    elif data.startswith("my_matches"):
        page = int(data.split('_')[-1])
        await matches_command(update, context, from_callback=True, page=page)

    elif data.startswith("my_deals"):
        page = int(data.split('_')[-1])
        await deals_command(update, context, from_callback=True, page=page)

async def start_command_inline(query, context):
    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)

    # Get user's preferred currency and language
    user_currency = get_user_currency(user.id)
    user_lang = get_user_lang(user.id)
    formatted_balance = format_balance_with_locked(user.id, user_currency)

    # Get total wagers for display
    stats = user_stats.get(user.id, {})
    total_wagered = stats.get('bets', {}).get('amount', 0.0)
    formatted_wagers = format_currency(total_wagered, user_currency)

    # NEW UI STRUCTURE - Casino themed with premium emojis - STYLED VERSION
    keyboard = [
        # Row 1: Deposit & Withdraw
        [
            apply_button_style(InlineKeyboardButton("Deposit", callback_data="main_deposit"), 'primary', peb('deposit')),  # BLUE
            apply_button_style(InlineKeyboardButton("Withdraw", callback_data="main_withdraw"), 'success', peb('withdraw'))  # GREEN
        ],
        # Row 2: Games & More
        [
            apply_button_style(InlineKeyboardButton("Games", callback_data="main_games"), 'primary', peb('game')),  # BLUE
            apply_button_style(InlineKeyboardButton("More", callback_data="main_more"), 'danger', peb('chart'))  # RED
        ],
        # Row 3: Settings
    ]

    # Add Settings button only in DMs - with better error handling
    try:
        if query.message and query.message.chat and query.message.chat.type == "private":
            keyboard.append([apply_button_style(InlineKeyboardButton("Settings", callback_data="main_settings"), 'success', peb('settings'))])  # GREEN
    except AttributeError:
        # Default to adding settings if we can't determine chat type
        keyboard.append([apply_button_style(InlineKeyboardButton("Settings", callback_data="main_settings"), 'success', peb('settings'))])  # GREEN

    # Row 5: Admin Dashboard (only for admin)
    if is_admin(user.id):
        keyboard.append([apply_button_style(InlineKeyboardButton("Admin Panel", callback_data="admin_dashboard"), 'danger', peb('settings'))])

    # Create links row - Only show in DMs to avoid spam in groups
    try:
        is_private = query.message and query.message.chat and query.message.chat.type == "private"
    except AttributeError:
        is_private = True  # Default to showing links if we can't determine

    if is_private:
        links_row = []
        if LINK_PORTAL:
            links_row.append(InlineKeyboardButton("Portal", url=LINK_PORTAL).to_dict())
        if LINK_CHANNEL:
            links_row.append(InlineKeyboardButton("Channel", url=LINK_CHANNEL).to_dict())

        links_row_2 = []
        if LINK_CHAT:
            links_row_2.append(InlineKeyboardButton("Chat", url=LINK_CHAT).to_dict())
        if LINK_SUPPORT:
            links_row_2.append(InlineKeyboardButton("Support", url=LINK_SUPPORT).to_dict())

        # Add links rows if they have buttons
        if links_row:
            keyboard.append(links_row)
        if links_row_2:
            keyboard.append(links_row_2)

    welcome_text = (
        f"{pe('casino')} <b>Welcome to @playcsino</b>  {pe('lightning')}\n"
        f"<i>Telegram Casino</i>\n\n"
        f"{pe('balance')} <b>Balance:</b> {formatted_balance}\n"
        f"{pe('chart')} <b>Wagered:</b> {formatted_wagers}\n\n"
        f"{pe('plinko')} Try <b>Plinko</b> & 🐔 <b>Chicken Road</b> - new games!\n"
        f"{pe('game')} Pick an option to get started!"
    )

    # Create styled keyboard using helper function
    reply_markup = create_styled_keyboard(keyboard)

    caption_text = f"{pe('down_arrow')} Please choose an option to start"

    # Generate dashboard image and send with caption
    dashboard_image = await generate_dashboard_image(user.id, context)
    if dashboard_image:
        try:
            await query.message.reply_photo(
                photo=dashboard_image,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            await query.message.delete()
        except Exception as e:
            logging.error(f"Error sending dashboard image in inline: {e}")
            await safe_edit_message(query, caption_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await safe_edit_message(query, caption_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user if update.effective_user else None
    user_lang = get_user_lang(user.id) if user else DEFAULT_LANG

    # Determine if in group chat
    is_group = False
    if update.callback_query:
        try:
            is_group = update.callback_query.message.chat.type in ["group", "supergroup"]
        except AttributeError:
            pass
    elif update.effective_chat:
        is_group = update.effective_chat.type in ["group", "supergroup"]

    if is_group:
        # Group chat: only House Games and Emoji Games, no official link, no back button
        keyboard = [
            [apply_button_style(InlineKeyboardButton("House Games", callback_data="games_category_house"), 'primary', peb('fire'))],  # BLUE
            [apply_button_style(InlineKeyboardButton("Emoji Games", callback_data="games_category_emoji"), 'success', peb('dice'))],  # GREEN
        ]
    else:
        # DM: full menu
        keyboard = [
            [apply_button_style(InlineKeyboardButton("House Games", callback_data="games_category_house"), 'primary', peb('fire'))],  # BLUE
            [apply_button_style(InlineKeyboardButton("Emoji Games", callback_data="games_category_emoji"), 'success', peb('dice'))],  # GREEN
            [InlineKeyboardButton("Official Group", url="https://t.me/playcsino").to_dict()],
            [apply_button_style(InlineKeyboardButton(get_text("back", user_lang), callback_data="back_to_main"), 'danger')]  # RED
        ]
    text = get_text("games_menu", user_lang)

    if update.callback_query:
        await safe_edit_message(
            update.callback_query,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_styled_keyboard(keyboard)
        )
        # Set menu owner after editing
        if user:
            set_menu_owner(update.callback_query.message, user.id)
    else:
        sent_message = await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_styled_keyboard(keyboard)
        )
        # Set menu owner after sending
        if user:
            set_menu_owner(sent_message, user.id)

@check_banned
@check_maintenance
async def games_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not await _acquire_callback(query.id):
        try: await query.answer()
        except: pass
        return

    try:
        # Check menu ownership BEFORE answering
        if not check_menu_ownership(query, context):
            await query.answer("This menu is not for you.", show_alert=True)
            return

        await query.answer()

        # Extract category from callback data
        if query.data == "games_category_emoji":
            category = "emoji"
        elif query.data == "games_emoji_regular":
            category = "emoji-regular"
        elif query.data == "games_emoji_single":
            category = "emoji-single"
        elif query.data == "games_category_house":
            category = "house"
        else:
            category = query.data.split('_')[-1]

        if category == "house":
            text = f"{pe('house')} <b>House Games</b>\n\nChoose a game to see how to play:"

            # Get bot username for deep links
            bot_username = context.bot.username

            # Build deep link URLs for Mini Apps
            plinko_deep = f"https://t.me/{bot_username}?start=plinko"
            chicken_deep = f"https://t.me/{bot_username}?start=chickenroad"

            keyboard = [
                # Plain Mini App buttons (no color, no premium emoji)
                [InlineKeyboardButton("🔴 Plinko Mini App", url=plinko_deep)],
                [InlineKeyboardButton("🐔 Chicken Road Mini App", url=chicken_deep)],
                [apply_button_style(InlineKeyboardButton("Blackjack", callback_data="game_blackjack"), 'success', peb('cards')),  # GREEN
                 apply_button_style(InlineKeyboardButton("Dice Roll", callback_data="game_dice_roll"), 'success', peb('dice'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Predict", callback_data="game_predict"), 'success', peb('crystal')),  # GREEN
                 apply_button_style(InlineKeyboardButton("Roulette", callback_data="game_roulette"), 'success', peb('darts'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Slots", callback_data="game_slots"), 'success', peb('casino')),  # GREEN
                 apply_button_style(InlineKeyboardButton("Tower", callback_data="game_tower_start"), 'success', peb('tower'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Mines", callback_data="game_mines_start"), 'success', peb('bomb')),  # GREEN
                 apply_button_style(InlineKeyboardButton("Keno", callback_data="game_keno"), 'success', peb('darts'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Coin Flip", callback_data="game_coin_flip"), 'success', peb('coin')),  # GREEN
                 apply_button_style(InlineKeyboardButton("High-Low", callback_data="game_highlow"), 'success', peb('hilow'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Back to Categories", callback_data="main_games"), 'danger', peb('back'))]  # RED
            ]
        elif category == "emoji":
            text = f"{pe('smile')} <b>Emoji Games</b>\n\nChoose a category:"
            keyboard = [
                [apply_button_style(InlineKeyboardButton("Regular Games", callback_data="games_emoji_regular"), 'primary', peb('game'))],  # BLUE
                [apply_button_style(InlineKeyboardButton("Single Emoji Games", callback_data="games_emoji_single"), 'success', peb('darts'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Back to Categories", callback_data="main_games"), 'danger', peb('back'))]  # RED
            ]
        elif category == "emoji-regular":
            text = f"{pe('game')} <b>Regular Emoji Games</b>\n\nChoose a game to see how to play:"
            keyboard = [
                [apply_button_style(InlineKeyboardButton("Dice", callback_data="game_dice_bot"), 'success', peb('dice'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Darts", callback_data="game_darts"), 'success', peb('darts'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Football", callback_data="game_football"), 'success', peb('goal'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Bowling", callback_data="game_bowling"), 'success', peb('bowl'))],  # GREEN
                [apply_button_style(InlineKeyboardButton("Back to Emoji Games", callback_data="games_category_emoji"), 'danger', peb('back'))]  # RED
            ]
        elif category == "emoji-single":
            text = f"{pe('darts')} <b>Single Emoji Games</b>\n\nQuick games with instant results!\n\nHow to play: Choose a game, set your bet, and watch the emoji!"
            keyboard = [
                [apply_button_style(InlineKeyboardButton("Darts (1.15x)", callback_data="game_single_darts"), 'primary', peb('darts'))],  # BLUE
                [apply_button_style(InlineKeyboardButton("Soccer (1.53x)", callback_data="game_single_soccer"), 'primary', peb('goal'))],  # BLUE
                [apply_button_style(InlineKeyboardButton("Basket (2.25x)", callback_data="game_single_basket"), 'primary', peb('basketball'))],  # BLUE
                [apply_button_style(InlineKeyboardButton("Bowling (5.00x)", callback_data="game_single_bowling"), 'primary', peb('bowl'))],  # BLUE
                [apply_button_style(InlineKeyboardButton("Slot (14.5x)", callback_data="game_single_slot"), 'primary', peb('casino'))],  # BLUE
                [apply_button_style(InlineKeyboardButton("Back to Emoji Games", callback_data="games_category_emoji"), 'danger', peb('back'))]  # RED
            ]
        else:
            return

        await safe_edit_message(
            query,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=create_styled_keyboard(keyboard)
        )
    finally:
        _release_callback(query.id)

@check_banned
@check_maintenance
async def game_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    data = query.data
    await ensure_user_in_wallets(query.from_user.id, query.from_user.username, context=context)

    if data == "game_blackjack":
        await safe_edit_message(query,
            "🃏 <b>Blackjack</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Get as close to 21 as possible\n"
            "• Beat the dealer without going over 21\n"
            "• Ace = 1 or 11, Face cards = 10\n\n"
            "<b>Commands:</b>\n"
            "• <code>/bj amount</code> - Start blackjack\n"
            "• Example: <code>/bj 5</code> or <code>/bj all</code>\n\n"
            "<b>Payouts:</b>\n"
            "• Win: 2x your bet\n"
            "• Blackjack: 2.5x your bet\n"
            "• Push: Get your bet back",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="games_category_house")]])
        )

    elif data == "game_coin_flip":
        await safe_edit_message(query,
            "🪙 <b>Coin Flip</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Choose Heads or Tails\n"
            "• Win: 2x multiplier\n"
            "• Keep winning to increase multiplier!\n\n"
            "<b>Commands:</b>\n"
            "• <code>/flip amount</code> - Start coin flip\n"
            "• Example: <code>/flip 1</code> or <code>/flip all</code>\n\n"
            "<b>Multiplier Chain:</b>\n"
            "• 1 win: 2x\n"
            "• 2 wins: 4x\n"
            "• 3 wins: 8x\n"
            "• And so on... 🚀",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="games_category_house")]])
        )

    elif data == "game_highlow":
        await safe_edit_message(query,
            "🎴 <b>High-Low Card Game</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• You're shown a card\n"
            "• Guess if next card is Higher, Lower, or Skip\n"
            "• Each correct guess increases multiplier\n"
            "• Cash out anytime after first win!\n\n"
            "<b>Commands:</b>\n"
            "• <code>/hl amount</code> - Start High-Low game\n"
            "• Example: <code>/hl 5</code> or <code>/hl all</code>\n\n"
            "<b>Multipliers:</b>\n"
            "• Increases based on probability of outcome\n"
            "• Ace is low (1), King is high (13)\n"
            "• Skip gives smaller multiplier but safer",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="games_category_house")]])
        )
    elif data == "game_limbo":
        await safe_edit_message(query,
            "🚀 <b>LIMBO</b>\n\n"
            "<b>How to play:</b>\n"
            "• Choose your target multiplier (1.01 - 1000.00)\n"
            "• A random outcome is generated\n"
            "• If outcome ≥ your target: You win (bet × target)\n"
            "• If outcome < your target: You lose\n\n"
            "<b>Probability:</b>\n"
            "• 2x = ~48% chance\n"
            "• 4x = ~24% chance\n"
            "• Higher multipliers = lower chance\n\n"
            "<b>Usage:</b> <code>/lb amount multiplier</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/lb 10 2.00</code> - Bet $10 at 2x\n"
            "• <code>/lb all 1.5</code> - Bet all at 1.5x\n\n"
            f"<b>Min bet:</b> ${MIN_BALANCE:.2f}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Back", callback_data="games_category_house")]]
            ),
        )
    elif data == "game_roulette":
        await safe_edit_message(query,
            "🎯 <b>Roulette</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Choose number (0-36), color, or type\n\n"
            "<b>Commands:</b>\n"
            "• <code>/roul amount</code> (interactive menu)\n"
            "• <code>/roul amount choice</code> (quick bet)\n"
            "• <code>/roulette amount choice</code>\n\n"
            "<b>Interactive Examples:</b>\n"
            "• <code>/roul 10</code> (opens menu)\n\n"
            "<b>Quick Bet Examples:</b>\n"
            "• <code>/roul 1 5</code> (number 5)\n"
            "• <code>/roul all red</code> (red color)\n"
            "• <code>/roul 1 even</code> (even numbers)\n"
            "• <code>/roul 1 low</code> (1-18)\n"
            "• <code>/roul 1 high</code> (19-36)\n\n"
            "<b>Payouts:</b>\n"
            "• Single number: 35x\n"
            "• Red/Black, Even/Odd, High/Low: 1.96x\n"
            "• Columns: 2.92x",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="games_category_house")]])
        )

    elif data == "game_dice_roll":
        await safe_edit_message(query,
            "🎲 <b>Dice Roll</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Choose number (1-6), even/odd, or high/low\n"

            "• Bot rolls real Telegram dice\n\n"
            "<b>Commands:</b>\n"
            "• <code>/dr amount choice</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/dr 1 3</code> (number 3)\n"
            "• <code>/dr all even</code> (even numbers)\n"
            "• <code>/dr 1 high</code> (4,5,6)\n"
            "• <code>/dr 1 low</code> (1,2,3)\n\n"
            "<b>Payouts:</b>\n"
            "• Exact number: 5.30x\n"
            "• Even/Odd/High/Low: 1.96x",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="games_category_house")]])
        )

    elif data == "game_slots":
        await safe_edit_message(query,
            "🎰 <b>Slots</b>\n\n"
            "<b>How to play:</b>\n"
            "• Bot rolls real Telegram slot machine\n"
            "• Get 3 matching symbols to win\n\n"
            "<b>Commands:</b>\n"
            "• <code>/sl amount</code>\n"
            "• Example: <code>/sl 1</code> or <code>/sl all</code>\n\n"
            "<b>Payouts:</b>\n"
            "• 3 matching BAR, LEMON, or GRAPE: 10x\n"
            "• Triple 7s (JACKPOT): 20x\n"
            "• No match: 0x",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="games_category_house")]])
        )

    elif data == "game_predict":
        await safe_edit_message(query,
            "🔮 <b>Predict Dice</b>\n\n"
            "<b>How to play:</b>\n"
            "• Predict if dice will be up (4-6) or down (1-3)\n"
            "• 2x payout on correct prediction\n\n"
            "<b>Commands:</b>\n"
            "• <code>/predict amount up</code>\n"
            "• <code>/predict all down</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="games_category_house")]])
        )



    elif data == "game_keno":
        await safe_edit_message(query,
            "🎯 <b>KENO</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Pick 1-10 numbers from 1-40\n"
            "• 10 random numbers are drawn\n"
            "• Win based on matches!\n\n"
            "<b>Commands:</b>\n"
            "• <code>/keno amount</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/keno 10</code> - Start with $10\n"
            "• <code>/keno all</code> - Start with all balance\n\n"
            "<b>Strategy Tips:</b>\n"
            "• More picks = higher payouts\n"
            "• But need more matches to win\n"
            "• 5-7 picks is balanced\n"
            "• Check payout table in-game\n\n"
            "Uses provably fair system!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="games_category_house")]])
        )

    elif data == "game_crash":
        await safe_edit_message(query,
            "📉 <b>CRASH</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Multiplier starts at 1.00x and rises\n"
            "• Cash out before it crashes!\n"
            "• The longer you wait, the higher the multiplier\n"
            "• But if you don't cash out in time, you lose\n\n"
            "<b>Commands:</b>\n"
            "• <code>/crash amount</code>\n"
            "• <code>/crash amount target</code> (auto cashout)\n\n"
            "<b>Examples:</b>\n"
            "• <code>/crash 10</code> - $10 bet, manual cashout\n"
            "• <code>/crash 5 2.5</code> - $5, auto cashout at 2.5x\n"
            "• <code>/crash all 3</code> - All balance, auto at 3x\n\n"
            "<b>Tips:</b>\n"
            "• Average crash point: ~1.98x\n"
            "• Lower targets = higher win rate\n"
            "• High multipliers are rare but exciting!\n\n"
            "Provably fair!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to House Games", callback_data="games_category_house")]])
        )

    elif data == "game_plinko":
        await safe_edit_message(query,
            "🎪 <b>PLINKO</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Drop a ball through pegs\n"
            "• Ball bounces randomly\n"
            "• Land in slots with different multipliers\n"
            "• Center = lower multipliers, safer\n"
            "• Edges = higher multipliers, riskier\n\n"
            "<b>Commands:</b>\n"
            "• <code>/plinko amount risk</code>\n\n"
            "<b>Risk Levels:</b>\n"
            "• <code>low</code> - Max 5.6x, safer\n"
            "• <code>medium</code> - Max 33x, balanced\n"
            "• <code>high</code> - Max 420x, risky!\n\n"
            "<b>Examples:</b>\n"
            "• <code>/plinko 5 low</code>\n"
            "• <code>/plinko 10 medium</code>\n"
            "• <code>/plinko all high</code>\n\n"
            "Provably fair!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to House Games", callback_data="games_category_house")]])
        )

    elif data == "game_cr":
        cr_url = _get_chicken_road_web_url()
        if cr_url and update.effective_chat.type == "private":
            from telegram import WebAppInfo
            keyboard = [[InlineKeyboardButton("🐔 Play Chicken Road",
                                                web_app=WebAppInfo(url=cr_url))]]
            await safe_edit_message(query,
                "🐔 <b>CHICKEN ROAD</b>\n\n"
                "Cross the dungeon — step by step — before the fire gets you!\n\n"
                "• 4 difficulty modes: Easy / Medium / Hard / Hardcore\n"
                "• RTP: 98% | Max Win: $20,000\n"
                "• Provably Fair",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.answer("Open in private chat to play Chicken Road!", show_alert=True)

    elif data == "game_wheel":
        await safe_edit_message(query,
            "🎡 <b>WHEEL OF FORTUNE</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Spin the wheel for prizes\n"
            "• 50 segments with different multipliers\n"
            "• Multipliers range from 0.2x to 50x\n"
            "• The higher the multiplier, the rarer\n\n"
            "<b>Commands:</b>\n"
            "• <code>/wheel amount</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/wheel 10</code> - Spin with $10\n"
            "• <code>/wheel all</code> - Spin with all balance\n\n"
            "<b>Multiplier Distribution:</b>\n"
            "• 0.2x-1x: Common (~40%)\n"
            "• 1.5x-5x: Uncommon (~35%)\n"
            "• 10x-20x: Rare (~20%)\n"
            "• 30x-50x: Very Rare (~5%)\n\n"
            "Provably fair!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to House Games", callback_data="games_category_house")]])
        )

    elif data == "game_scratch":
        await safe_edit_message(query,
            "🎫 <b>SCRATCH CARD</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Buy a scratch card\n"
            "• Reveal 9 squares instantly\n"
            "• Match 3 symbols to win\n"
            "• Different symbols = different multipliers\n\n"
            "<b>Commands:</b>\n"
            "• <code>/scratch amount</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/scratch 5</code> - Buy $5 card\n"
            "• <code>/scratch all</code> - Buy card with all balance\n\n"
            "<b>Symbol Multipliers:</b>\n"
            "• 💎 Diamond: 100x\n"
            "• 👑 Crown: 50x\n"
            "• ⭐ Star: 20x\n"
            "• 💰 Money: 10x\n"
            "• 🍀 Clover: 5x\n"
            "• 🎰 Slot: 2x\n\n"
            "Provably fair!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to House Games", callback_data="games_category_house")]])
        )

    elif data == "game_coin_chain":
        await safe_edit_message(query,
            "🪙 <b>COIN TOSS CHAIN</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Toss a coin - Heads or Tails\n"
            "• Each correct guess = 1.9x multiplier\n"
            "• Keep winning to build a chain\n"
            "• Cash out anytime or go for more\n"
            "• One wrong guess = lose everything\n\n"
            "<b>Commands:</b>\n"
            "• <code>/coinchain amount</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/coinchain 5</code> - Start with $5\n"
            "• <code>/coinchain all</code> - Start with all balance\n\n"
            "<b>Chain Multipliers:</b>\n"
            "• 1 win: 1.9x\n"
            "• 2 wins: 3.61x\n"
            "• 3 wins: 6.86x\n"
            "• 4 wins: 13.03x\n"
            "• 5 wins: 24.76x\n"
            "• 10 wins: 613.11x (!)\n\n"
            "Provably fair!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to House Games", callback_data="games_category_house")]])
        )

    # Single Emoji Games
    elif data.startswith("game_single_"):
        game_key = data.replace("game_single_", "")
        if game_key in SINGLE_EMOJI_GAMES:
            game_config = SINGLE_EMOJI_GAMES[game_key]
            await safe_edit_message(query,
                f"{game_config['emoji']} <b>{game_config['name']}</b>\n\n"
                f"<b>How to play:</b>\n"
                f"• Quick instant-result game\n"
                f"• Win when: {game_config['win_description']}\n"
                f"• Multiplier: {game_config['multiplier']}x\n"
                f"• Win chance: {game_config['win_chance']*100:.1f}%\n\n"
                f"<b>How to start:</b>\n"
                f"1. Tap 'Play Game' below\n"
                f"2. Enter your bet amount\n"
                f"3. Watch the {game_config['emoji']} animation!\n\n"
                f"Simple, fast, and fun!",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"Play {game_config['emoji']}", callback_data=f"play_single_{game_key}")],
                    [InlineKeyboardButton("Back", callback_data="games_category_emoji-single")]
                ])
            )

    # PvP games
    elif data.startswith("game_"):
        game_name_map = {
            "football": "Football", "darts": "Darts", "bowling": "Bowling", "dice_bot": "Dice"
        }
        game_key = data.replace("game_", "")
        game_name = game_name_map.get(game_key, game_key.replace("_", " ").title())

        keyboard = [
            [InlineKeyboardButton("Play vs Bot", callback_data=f"pvb_start_{game_key}")],
            [InlineKeyboardButton("Play vs Player", callback_data=f"pvp_info_{game_key}")],
            [InlineKeyboardButton("Back to Regular Games", callback_data="games_emoji_regular")]
        ]

        await safe_edit_message(query,
            f"{pe('game')} <b>{game_name}</b>\n\n"
            "Who do you want to play against?",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # Set menu owner after editing to ensure buttons work for this user
        set_menu_owner(query.message, query.from_user.id)

@check_banned
@check_maintenance
async def game_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help button callbacks for Mines and Tower games."""
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    data = query.data

    if data == "mines_help":
        await safe_edit_message(query,
            f"{pe('bomb')} <b>Mines Game</b>\n\n"
            "<b>How to Play:</b>\n"
            "Click on tiles to reveal gems or mines. Each safe gem increases your multiplier!\n"
            "Cash out at any time to secure your winnings. Hitting a mine ends the game.\n\n"
            "<b>Commands:</b>\n"
            "• <code>/mines &lt;amount&gt;</code> - Start a game with specified bet amount\n"
            "• <code>/m &lt;amount&gt;</code> - Alias for /mines\n"
            "• <code>/continue &lt;game_id&gt;</code> - Continue an active mines game\n\n"
            "<b>Examples:</b>\n"
            "• <code>/mines 10</code> - Start with $10 bet\n"
            "• <code>/m all</code> - Start with all-in bet\n\n"
            "<b>Multipliers:</b>\n"
            "• More mines = higher multipliers\n"
            "• More safe picks = higher multipliers\n"
            "• Cash out anytime to lock in profits!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to House Games", callback_data="games_category_house")]])
        )
    elif data == "tower_help":
        await safe_edit_message(query,
            f"{pe('tower')} <b>Tower Game</b>\n\n"
            "<b>How to Play:</b>\n"
            "Climb the tower by selecting safe tiles. Each floor has one snake hidden behind a tile.\n"
            "Cash out at any time to secure your winnings, or reach the top for the jackpot!\n\n"
            "<b>Difficulty Modes:</b>\n"
            "• Easy: 4 tiles per floor (25% risk)\n"
            "• Medium: 3 tiles per floor (33% risk)\n"
            "• Hard: 2 tiles per floor (50% risk)\n\n"
            "<b>Commands:</b>\n"
            "• <code>/tower &lt;amount&gt;</code> - Start a game with specified bet amount\n"
            "• <code>/tr &lt;amount&gt;</code> - Alias for /tower\n"
            "• <code>/continue &lt;game_id&gt;</code> - Continue an active tower game\n\n"
            "<b>Examples:</b>\n"
            "• <code>/tower 10</code> - Start with $10 bet\n"
            "• <code>/tr all</code> - Start with all-in bet\n\n"
            "<b>Multipliers:</b>\n"
            "• Each floor climbed increases multiplier\n"
            "• Higher difficulty = higher rewards\n"
            "• 9 floors to reach the top!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to House Games", callback_data="games_category_house")]])
        )

@check_banned
@check_maintenance
async def coinflip_rebet_double_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Rebet and Double buttons for coinflip"""
    query = update.callback_query
    user = query.from_user

    if not await _acquire_callback(query.id):
        try: await query.answer()
        except: pass
        return

    try:
        # Parse callback data: coinflip_rebet_{bet_amount}_{user_id} or coinflip_double_{bet_amount}_{user_id}
        parts = query.data.split("_")
        if len(parts) < 4:
            await query.answer("Invalid button data", show_alert=True)
            return

        action = parts[1]  # rebet or double
        try:
            original_bet = float(parts[2])
            button_user_id = int(parts[3])
        except (ValueError, IndexError):
            await query.answer("Invalid button data", show_alert=True)
            return

        # User-specific button check
        if user.id != button_user_id:
            await query.answer("This button is not for you!", show_alert=True)
            return

        await query.answer()
        await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)

        # Determine bet amount
        if action == "rebet":
            bet = original_bet
        else:  # double
            bet = original_bet * 2

        # Check bet limits
        if not await check_bet_limits(update, bet, 'coin_flip', user_id=user.id):
            await query.answer("Bet exceeds limits", show_alert=True)
            return

        # Atomic balance check + deduct to prevent race conditions
        try:
            crypto_deducted, coin = await deduct_wallet_safe(user.id, bet)
        except ValueError:
            await query.answer("Insufficient balance!", show_alert=True)
            return
        save_user_data(user.id)

        # Use user's provably fair seeds and increment nonce at game start
        seeds = get_user_seeds(user.id)
        current_nonce = seeds["nonce"]
        increment_user_nonce(user.id)
        game_id = generate_unique_id("CF")

        game_sessions[game_id] = {
            "id": game_id,
            "game_type": "coin_flip",
            "user_id": user.id,
            "bet_amount": bet,
            "active_currency": get_active_currency(user.id),
            "crypto_bet_amount": bet / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
            "status": "active",
            "timestamp": str(datetime.now(timezone.utc)),
            "streak": 0,
            "server_seed": seeds["server_seed"],
            "client_seed": seeds["client_seed"],
            "nonce": current_nonce
        }
        await ensure_user_in_wallets(user.id, user.username, context=context)
        if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
        user_stats[user.id]['game_sessions'].append(game_id)
        save_user_data(user.id)

        keyboard = [
            [apply_button_style(InlineKeyboardButton("Heads", callback_data=f"flip_pick_{game_id}_Heads"), 'primary'),
             apply_button_style(InlineKeyboardButton("Tails", callback_data=f"flip_pick_{game_id}_Tails"), 'primary')]
        ]
        await query.edit_message_text(
            f"{pe('coin')} <b>Coin Flip Started!</b> (ID: <code>{game_id}</code>)\n\n💰 Bet: ${bet:.2f}\nChoose Heads or Tails!\n\n"
            f"{pe('target')} Current Multiplier: 1.94x",
            parse_mode=ParseMode.HTML,
            reply_markup=create_styled_keyboard(keyboard)
        )
    finally:
        _release_callback(query.id)

@check_banned
@check_maintenance
async def emoji_game_setup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all egsetup_* callback data from the emoji game setup panel."""
    query = update.callback_query

    parts = query.data.split("_")
    try:
        owner_id = int(parts[-1])
    except (ValueError, IndexError):
        await query.answer("Invalid callback.", show_alert=True)
        return

    if query.from_user.id != owner_id:
        await query.answer("This menu is not yours.", show_alert=True)
        return

    await query.answer()
    user  = query.from_user

    action    = parts[1]
    game_type = parts[-2]
    setup_key = f"eg_setup_{game_type}"

    if setup_key not in context.user_data:
        context.user_data[setup_key] = {"mode": "normal", "rolls": 1, "first_to": 1, "bet_usd": None}
    state = context.user_data[setup_key]

    if action == "play":
        if not state.get("bet_usd"):
            await query.answer("Please select a bet amount first!", show_alert=True)
            return
        bet = state["bet_usd"]
        mode = state["mode"]
        rolls = state["rolls"]
        first_to = state["first_to"]
        balance = get_active_balance_usd(user.id)
        if balance < bet:
            await query.answer("Insufficient balance!", show_alert=True)
            return
        context.user_data['game_type']  = game_type
        context.user_data['game_mode']  = mode
        context.user_data['game_rolls'] = rolls
        context.user_data['target_points'] = first_to
        context.user_data['preset_bet']    = bet
        await _start_pvb_from_setup(query, context, game_type, mode, rolls, first_to, bet, user)
        return

    elif action == "mode":
        state["mode"] = "crazy" if state["mode"] == "normal" else "normal"

    elif action == "rolls":
        state["rolls"] = (state["rolls"] % 3) + 1

    elif action == "ft":
        sub = parts[2]
        if sub == "inc":
            state["first_to"] = min(state["first_to"] + 1, 3)
        elif sub == "dec":
            state["first_to"] = max(state["first_to"] - 1, 1)

    elif action == "bet":
        sub = parts[2]
        if sub == "custom":
            context.user_data[f"eg_awaiting_custom_bet_{game_type}"] = True
            await query.edit_message_text(
                f"{pe('pencil')} <b>Custom Bet Amount</b>\n\nPlease reply with your bet amount (e.g. <code>5.50</code>).\n"
                f"Your balance: <b>${get_active_balance_usd(user.id):.2f}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Cancel", callback_data=f"egsetup_cancelcustom_{game_type}_{user.id}")]
                ])
            )
            return
        else:
            try:
                state["bet_usd"] = float(sub)
            except ValueError:
                pass

    elif action == "cancelcustom":
        context.user_data.pop(f"eg_awaiting_custom_bet_{game_type}", None)

    balance = get_active_balance_usd(user.id)
    text, keyboard = _build_emoji_setup_ui(game_type, state, balance, user)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@check_banned
@check_maintenance
async def rpvp_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    match_id = query.data.replace("rpvp_confirm_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending_reply_challenge":
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    # Only the challenged player can confirm
    if user.id != match["opponent_id"]:
        await query.answer("Only the challenged player can confirm!", show_alert=True)
        return

    await query.answer()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Show mode/rolls/target selection to the challenger (who set up the game)
    match["status"] = "pending_setup"

    # Show mode selection with styled buttons
    normal_btn = apply_button_style(
        InlineKeyboardButton("Normal Mode (Highest wins)", callback_data=f"rpvp_mode_{match_id}_normal"),
        'primary', peb('normal')
    )
    crazy_btn = apply_button_style(
        InlineKeyboardButton("Crazy Mode (Lowest wins)", callback_data=f"rpvp_mode_{match_id}_crazy"),
        'danger', peb('crazy')
    )
    keyboard = create_styled_keyboard([[normal_btn], [crazy_btn]])

    host_username = match.get('host_username', 'Challenger')
    await query.edit_message_text(
        f"{pe('confirm')} <b>Challenge Accepted!</b>\n\n"
        f"@{host_username}, select the game mode:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@check_banned
@check_maintenance
async def rpvp_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    parts = query.data.split("_")
    match_id = parts[2]
    mode = parts[3]
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending_setup":
        await query.answer("Challenge not found.", show_alert=True)
        return

    # Only the challenger (host) can set up
    if user.id != match["host_id"]:
        await query.answer("Only the challenger can configure the game!", show_alert=True)
        return

    await query.answer()
    match["mode"] = mode
    match["game_mode"] = mode

    # If rolls and target are pre-set from XdX'w format, skip rolls/target selection
    if match.get("xdxw_preset"):
        host_id = match["host_id"]
        opponent_id = match["opponent_id"]
        target = match["target_score"]

        try:
            host_deducted, host_coin = await deduct_wallet_safe(host_id, match["bet_amount_usd"])
        except ValueError:
            await query.edit_message_text(f"{pe('cross')} Challenger has insufficient balance. Challenge cancelled.")
            match["status"] = "cancelled"
            return

        try:
            opp_deducted, opp_coin = await deduct_wallet_safe(opponent_id, match["bet_amount_usd"])
        except ValueError:
            credit_wallet_safe(host_id, match["bet_amount_usd"])
            await query.edit_message_text(f"{pe('cross')} Opponent has insufficient balance. Challenge cancelled.")
            match["status"] = "cancelled"
            return

        save_user_data(host_id)
        save_user_data(opponent_id)

        match["target_points"] = target
        match["status"] = "active"
        match["points"] = {host_id: 0, opponent_id: 0}
        match["player_rolls"] = {host_id: [], opponent_id: []}
        match["last_roller"] = None

        for pid in [host_id, opponent_id]:
            await ensure_user_in_wallets(pid, context=context)
            if 'game_sessions' not in user_stats.get(pid, {}):
                user_stats.setdefault(pid, {})['game_sessions'] = []
            if match_id not in user_stats[pid].get('game_sessions', []):
                user_stats[pid]['game_sessions'].append(match_id)
            save_user_data(pid)

        game_type = match["game_type"].replace("pvp_", "")
        emoji_map = {"dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3"}
        emoji = emoji_map.get(game_type, "\U0001f3b2")
        currency_symbol = CURRENCY_SYMBOLS.get(match.get("currency", "USDT"), "$")
        mode_desc = "Highest wins" if mode == "normal" else "Lowest wins"

        host_uname = match["usernames"].get(host_id, f"Player {host_id}")
        opp_uname = match["usernames"].get(opponent_id, f"Player {opponent_id}")

        await query.edit_message_text(
            f"{pe('game')} <b>{game_type.upper()} MATCH STARTED!</b> {pe('game')}\n\n"
            f"{pe('lightning')} {display_at(host_uname)} vs {display_at(opp_uname)}\n"
            f"{pe('money')} Prize Pool: {currency_symbol}{match.get('bet_amount_currency', match['bet_amount_usd']) * 2:.2f}\n"
            f"{pe('target')} Mode: {mode.title()} ({mode_desc})\n"
            f"{pe('rolls')} Rolls: {match['game_rolls']}\n"
            f"{pe('trophy')} Target: First to {target}\n\n"
            f"{display_at(host_uname)}, you roll first! Send {match['game_rolls']} {emoji} emoji{'s' if match['game_rolls'] > 1 else ''}.",
            parse_mode=ParseMode.HTML
        )
        return

    # Show rolls selection with styled buttons
    rolls_btns = []
    for r in [1, 2, 3]:
        btn = apply_button_style(
            InlineKeyboardButton(f"{r} Roll{'s' if r > 1 else ''}", callback_data=f"rpvp_rolls_{match_id}_{r}"),
            'primary', peb('rolls')
        )
        rolls_btns.append([btn])

    keyboard = create_styled_keyboard(rolls_btns)
    await query.edit_message_text(
        f"{pe('confirm')} Mode: <b>{mode.title()}</b>\n\n"
        f"Select number of rolls per round:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@check_banned
@check_maintenance
async def rpvp_rolls_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    parts = query.data.split("_")
    match_id = parts[2]
    rolls = int(parts[3])
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending_setup":
        await query.answer("Challenge not found.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the challenger can configure the game!", show_alert=True)
        return

    await query.answer()
    match["game_rolls"] = rolls

    # Show target selection with styled buttons
    target_btns = []
    for t in [1, 2, 3, 5]:
        btn = apply_button_style(
            InlineKeyboardButton(f"First to {t}", callback_data=f"rpvp_target_{match_id}_{t}"),
            'primary', peb('trophy')
        )
        target_btns.append([btn])

    keyboard = create_styled_keyboard(target_btns)
    await query.edit_message_text(
        f"{pe('confirm')} Mode: <b>{match['mode'].title()}</b> | Rolls: <b>{rolls}</b>\n\n"
        f"Select target score (First to X wins):",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@check_banned
@check_maintenance
async def rpvp_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    parts = query.data.split("_")
    match_id = parts[2]
    target = int(parts[3])
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending_setup":
        await query.answer("Challenge not found.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the challenger can configure the game!", show_alert=True)
        return

    await query.answer()

    host_id = match["host_id"]
    opponent_id = match["opponent_id"]

    # Deduct balances atomically
    try:
        host_deducted, host_coin = await deduct_wallet_safe(host_id, match["bet_amount_usd"])
    except ValueError:
        await query.edit_message_text(f"{pe('cross')} Challenger has insufficient balance. Challenge cancelled.")
        match["status"] = "cancelled"
        return

    try:
        opp_deducted, opp_coin = await deduct_wallet_safe(opponent_id, match["bet_amount_usd"])
    except ValueError:
        credit_wallet_safe(host_id, match["bet_amount_usd"])
        await query.edit_message_text(f"{pe('cross')} Opponent has insufficient balance. Challenge cancelled.")
        match["status"] = "cancelled"
        return

    save_user_data(host_id)
    save_user_data(opponent_id)

    # Finalize match setup
    match["target_score"] = target
    match["target_points"] = target
    match["status"] = "active"
    match["points"] = {host_id: 0, opponent_id: 0}
    match["player_rolls"] = {host_id: [], opponent_id: []}
    match["last_roller"] = None

    # Register game sessions
    for pid in [host_id, opponent_id]:
        await ensure_user_in_wallets(pid, context=context)
        if 'game_sessions' not in user_stats.get(pid, {}):
            user_stats.setdefault(pid, {})['game_sessions'] = []
        if match_id not in user_stats[pid].get('game_sessions', []):
            user_stats[pid]['game_sessions'].append(match_id)
        save_user_data(pid)

    game_type = match["game_type"].replace("pvp_", "")
    emoji_map = {"dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3"}
    emoji = emoji_map.get(game_type, "\U0001f3b2")
    currency_symbol = CURRENCY_SYMBOLS.get(match.get("currency", "USDT"), "$")
    mode_desc = "Highest wins" if match["mode"] == "normal" else "Lowest wins"

    host_uname = match["usernames"].get(host_id, f"Player {host_id}")
    opp_uname = match["usernames"].get(opponent_id, f"Player {opponent_id}")

    await query.edit_message_text(
        f"{pe('game')} <b>{game_type.upper()} MATCH STARTED!</b> {pe('game')}\n\n"
        f"{pe('lightning')} {display_at(host_uname)} vs {display_at(opp_uname)}\n"
        f"{pe('money')} Prize Pool: {currency_symbol}{match['bet_amount_currency'] * 2:.2f}\n"
        f"{pe('target')} Mode: {match['mode'].title()} ({mode_desc})\n"
        f"{pe('rolls')} Rolls: {match['game_rolls']}\n"
        f"{pe('trophy')} Target: First to {target}\n\n"
        f"{display_at(host_uname)}, you roll first! Send {match['game_rolls']} {emoji} emoji{'s' if match['game_rolls'] > 1 else ''}.",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def rpvp_playbot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    match_id = query.data.replace("rpvp_playbot_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending_reply_challenge":
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the challenger can play with bot!", show_alert=True)
        return

    await query.answer()

    # Convert to PvB game - show mode selection
    match["status"] = "pending_pvb_setup"
    match["opponent_id"] = 0
    match["opponent_username"] = "Bot"

    normal_btn = apply_button_style(
        InlineKeyboardButton("Normal Mode (Highest wins)", callback_data=f"rpvp_pvb_mode_{match_id}_normal"),
        'primary', peb('normal')
    )
    crazy_btn = apply_button_style(
        InlineKeyboardButton("Crazy Mode (Lowest wins)", callback_data=f"rpvp_pvb_mode_{match_id}_crazy"),
        'danger', peb('crazy')
    )
    keyboard = create_styled_keyboard([[normal_btn], [crazy_btn]])

    await query.edit_message_text(
        f"{pe('robot')} <b>Playing vs Bot!</b>\n\n"
        f"Select game mode:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@check_banned
@check_maintenance
async def rpvp_pvb_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    parts = query.data.split("_")
    # rpvp_pvb_mode_MATCHID_normal
    match_id = parts[3]
    mode = parts[4]
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending_pvb_setup":
        await query.answer("Challenge not found.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the challenger can configure!", show_alert=True)
        return

    await query.answer()
    match["mode"] = mode
    match["game_mode"] = mode

    # Show rolls selection
    rolls_btns = []
    for r in [1, 2, 3]:
        btn = apply_button_style(
            InlineKeyboardButton(f"{r} Roll{'s' if r > 1 else ''}", callback_data=f"rpvp_pvb_rolls_{match_id}_{r}"),
            'primary', peb('rolls')
        )
        rolls_btns.append([btn])

    keyboard = create_styled_keyboard(rolls_btns)
    await query.edit_message_text(
        f"{pe('robot')} <b>vs Bot</b> | Mode: <b>{mode.title()}</b>\n\n"
        f"Select rolls per round:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@check_banned
@check_maintenance
async def rpvp_pvb_rolls_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    parts = query.data.split("_")
    match_id = parts[3]
    rolls = int(parts[4])
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending_pvb_setup":
        await query.answer("Challenge not found.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the challenger can configure!", show_alert=True)
        return

    await query.answer()
    match["game_rolls"] = rolls

    # Show target selection
    target_btns = []
    for t in [1, 2, 3, 5]:
        btn = apply_button_style(
            InlineKeyboardButton(f"First to {t}", callback_data=f"rpvp_pvb_target_{match_id}_{t}"),
            'primary', peb('trophy')
        )
        target_btns.append([btn])

    keyboard = create_styled_keyboard(target_btns)
    await query.edit_message_text(
        f"{pe('robot')} <b>vs Bot</b> | Mode: <b>{match['mode'].title()}</b> | Rolls: <b>{rolls}</b>\n\n"
        f"Select target score:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

@check_banned
@check_maintenance
async def rpvp_pvb_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    parts = query.data.split("_")
    match_id = parts[3]
    target = int(parts[4])
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending_pvb_setup":
        await query.answer("Challenge not found.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the challenger can start!", show_alert=True)
        return

    await query.answer()

    # Deduct host balance
    try:
        host_deducted, host_coin = await deduct_wallet_safe(user.id, match["bet_amount_usd"])
    except ValueError:
        await query.edit_message_text(f"{pe('cross')} Insufficient balance. Game cancelled.")
        match["status"] = "cancelled"
        return
    save_user_data(user.id)

    game_type = match["game_type"].replace("pvp_", "")

    # Convert to proper PvB format
    match["game_type"] = f"pvb_{game_type}"
    match["target_score"] = target
    match["target_points"] = target
    match["status"] = "active"
    match["user_id"] = user.id
    match["players"] = [user.id, 0]
    match["usernames"] = {user.id: match["host_username"], 0: "Bot"}
    match["points"] = {user.id: 0, 0: 0}
    match["player_rolls"] = {user.id: [], 0: []}
    match["last_roller"] = None
    match["user_score"] = 0
    match["bot_score"] = 0
    match["current_round"] = 1
    match["user_rolls"] = []
    match["bot_rolls"] = []
    match["history"] = []
    match["waiting_for"] = "user"
    match["bot_rolls_first"] = False

    # Register in active PvB
    context.chat_data[f"active_pvb_game_{user.id}"] = match_id
    active_pvb_games[user.id] = match_id
    # PERFORMANCE: Proactively index so message_listener's dice scan
    # finds this match via the O(1) per-user index.
    _index_user_game(user.id, match_id)

    emoji_map = {"dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3"}
    emoji = emoji_map.get(game_type, "\U0001f3b2")
    mode_text = "Highest total score wins" if match["mode"] == "normal" else "Lowest total score wins"

    _co_round = match.get("current_round", 1)
    _co_mult = calculate_cashout_multiplier(match, user_id=user.id)
    _co_kb = _build_pvb_cashout_keyboard(match_id, _co_round, _co_mult)

    await query.edit_message_text(
        f"{pe('game')} {game_type.capitalize()} vs Bot started! (ID: <code>{match_id}</code>)\n"
        f"<b>Mode:</b> {match['mode'].capitalize()} ({mode_text})\n"
        f"<b>Rolls per round:</b> {match['game_rolls']}\n"
        f"<b>Target:</b> First to {target} points wins ${match['bet_amount_usd']*1.96:.2f}.\n\n"
        f"{user.mention_html()}, <b>Your turn first! Send {match['game_rolls']} {emoji} emoji{'s' if match['game_rolls'] > 1 else ''} to start.</b>\n"
        f"Or tap Cashout to collect <b>${match['bet_amount_usd'] * _co_mult:.2f}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=_co_kb
    )
    _register_cashout_button(match_id, user.id, match["chat_id"], _co_round,
                             message_id=query.message.message_id)

    # Schedule timeout
    if context.job_queue:
        chat_id = match["chat_id"]
        _cancel_pvb_timeout_jobs(context, user.id, match_id)
        round_timeout = match.get('round_timeout', default_round_timeout)
        warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
        context.job_queue.run_once(
            pvb_timeout_warn_job, when=warn_time,
            data={'user_id': user.id, 'game_id': match_id, 'chat_id': chat_id},
            name=f"pvb_warn_{match_id}"
        )
        context.job_queue.run_once(
            pvb_timeout_finish_job, when=round_timeout,
            data={'user_id': user.id, 'game_id': match_id, 'chat_id': chat_id},
            name=f"pvb_finish_{match_id}"
        )

@check_banned
@check_maintenance
async def rpvp_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    match_id = query.data.replace("rpvp_cancel_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") not in ("pending_reply_challenge",):
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the challenger can cancel!", show_alert=True)
        return

    await query.answer()
    match["status"] = "cancelled"

    # PvP/PvB emoji game challenge messages are no longer pinned, so
    # there is nothing to unpin here.

    await query.edit_message_text(
        f"{pe('cross')} Challenge cancelled by {user.mention_html()}.",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    message_text = update.message.text.strip().split()

    # Check for ongoing game before starting a new one
    if len(message_text) > 1:
        ongoing_game_id, ongoing_game_type = get_user_active_emoji_game(user.id)
        if ongoing_game_id:
            game_name = extract_game_name(ongoing_game_type)
            await update.message.reply_text(
                f"{pe('warning')} You already have an ongoing <b>{game_name}</b> match (ID: <code>{ongoing_game_id}</code>).\n\n"
                f"Please complete it first before starting a new game!",
                parse_mode=ParseMode.HTML
            )
            return

    # NEW: Reply-to-message PvP challenge (also supports XdX'w format when replying)
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        if len(message_text) == 2:
            await create_reply_pvp_challenge(update, context, "dice")
            return
        if len(message_text) == 3 and parse_xdxw_format(update.message.text):
            await create_reply_pvp_challenge_xdxw(update, context, "dice")
            return

    # Check for XdX'w format: /dice amount XdX'w
    if len(message_text) == 3:
        await create_xdxw_challenge(update, context, "dice")
        return

    # `/dice <amount>` (and the other emoji-game equivalents) used to
    # require a group/supergroup chat. In DMs it fell through to the
    # PvP usage handler and just printed help text, which surprised
    # users. Now we route the same single-amount form through the
    # group_challenge flow in private chats too — the resulting
    # mode/rolls/target setup ends with the same Play-with-Bot button
    # the user already knows from groups.
    if len(message_text) == 2:
        await create_group_challenge(update, context, "dice")
        return

    # Check if arguments are provided (PvP format)
    if len(message_text) > 1:
        await generic_emoji_game_command(update, context, "dice")
        return

    # No arguments — show help menu
    await update.message.reply_text(
        "🎲 <b>DICE GAME</b>\n\n"
        "Roll the dice against other players and win real money!\n\n"
        "<b>How to play:</b>\n"
        "• <code>/dice amount XdX'w</code> — Challenge with dice format\n"
        "  Example: <code>/dice 10 2d3w</code> (bet $10, 2 rolls, first to 3 wins)\n\n"
        "• <code>/dice @username amount MX ftY</code> — Challenge a specific player\n"
        "  Example: <code>/dice @player 10 MX ft5</code>\n\n"
        "• In groups: <code>/dice amount</code> — Open challenge for anyone to join\n\n"
        "<b>Rules:</b>\n"
        "• XdX'w format: X = number of rolls (1-3), X' = wins needed (1-10)\n"
        "• MX = Max rounds, ftY = First to Y score\n"
        "• Winner takes the pot (minus house fee)\n\n"
        "💡 Use these commands to start a game. No inline setup needed!",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def football_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    message_text = update.message.text.strip().split()

    # Check for ongoing game before starting a new one
    if len(message_text) > 1:
        ongoing_game_id, ongoing_game_type = get_user_active_emoji_game(user.id)
        if ongoing_game_id:
            game_name = extract_game_name(ongoing_game_type)
            await update.message.reply_text(
                f"{pe('warning')} You already have an ongoing <b>{game_name}</b> match (ID: <code>{ongoing_game_id}</code>).\n\n"
                f"Please complete it first before starting a new game!",
                parse_mode=ParseMode.HTML
            )
            return

    # NEW: Reply-to-message PvP challenge (also supports XdX'w format when replying)
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        if len(message_text) == 2:
            await create_reply_pvp_challenge(update, context, "goal")
            return
        if len(message_text) == 3 and parse_xdxw_format(update.message.text):
            await create_reply_pvp_challenge_xdxw(update, context, "goal")
            return

    # Check for XdX'w format: /goal amount XdX'w
    if len(message_text) == 3:
        await create_xdxw_challenge(update, context, "goal")
        return

    # `/dice <amount>` (and the other emoji-game equivalents) used to
    # require a group/supergroup chat. In DMs it fell through to the
    # PvP usage handler and just printed help text, which surprised
    # users. Now we route the same single-amount form through the
    # group_challenge flow in private chats too — the resulting
    # mode/rolls/target setup ends with the same Play-with-Bot button
    # the user already knows from groups.
    if len(message_text) == 2:
        await create_group_challenge(update, context, "goal")
        return

    # Check if arguments are provided (PvP format)
    if len(message_text) > 1:
        await generic_emoji_game_command(update, context, "goal")
        return

    # No arguments — show help menu
    await update.message.reply_text(
        "⚽ <b>GOAL GAME</b>\n\n"
        "Score goals against other players and win real money!\n\n"
        "<b>How to play:</b>\n"
        "• <code>/goal amount XdX'w</code> — Challenge with dice format\n"
        "  Example: <code>/goal 10 2d3w</code> (bet $10, 2 rolls, first to 3 wins)\n\n"
        "• <code>/goal @username amount MX ftY</code> — Challenge a specific player\n"
        "  Example: <code>/goal @player 10 MX ft5</code>\n\n"
        "• In groups: <code>/goal amount</code> — Open challenge for anyone to join\n\n"
        "<b>Rules:</b>\n"
        "• XdX'w format: X = number of rolls (1-3), X' = wins needed (1-10)\n"
        "• MX = Max rounds, ftY = First to Y score\n"
        "• Winner takes the pot (minus house fee)\n\n"
        "💡 Use these commands to start a game. No inline setup needed!",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def bowling_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    message_text = update.message.text.strip().split()

    # Check for ongoing game before starting a new one
    if len(message_text) > 1:
        ongoing_game_id, ongoing_game_type = get_user_active_emoji_game(user.id)
        if ongoing_game_id:
            game_name = extract_game_name(ongoing_game_type)
            await update.message.reply_text(
                f"{pe('warning')} You already have an ongoing <b>{game_name}</b> match (ID: <code>{ongoing_game_id}</code>).\n\n"
                f"Please complete it first before starting a new game!",
                parse_mode=ParseMode.HTML
            )
            return

    # NEW: Reply-to-message PvP challenge (also supports XdX'w format when replying)
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        if len(message_text) == 2:
            await create_reply_pvp_challenge(update, context, "bowl")
            return
        if len(message_text) == 3 and parse_xdxw_format(update.message.text):
            await create_reply_pvp_challenge_xdxw(update, context, "bowl")
            return

    # Check for XdX'w format: /bowl amount XdX'w
    if len(message_text) == 3:
        await create_xdxw_challenge(update, context, "bowl")
        return

    # `/dice <amount>` (and the other emoji-game equivalents) used to
    # require a group/supergroup chat. In DMs it fell through to the
    # PvP usage handler and just printed help text, which surprised
    # users. Now we route the same single-amount form through the
    # group_challenge flow in private chats too — the resulting
    # mode/rolls/target setup ends with the same Play-with-Bot button
    # the user already knows from groups.
    if len(message_text) == 2:
        await create_group_challenge(update, context, "bowl")
        return

    # Check if arguments are provided (PvP format)
    if len(message_text) > 1:
        await generic_emoji_game_command(update, context, "bowl")
        return

    # No arguments — show help menu
    await update.message.reply_text(
        "🎳 <b>BOWLING GAME</b>\n\n"
        "Bowl strikes against other players and win real money!\n\n"
        "<b>How to play:</b>\n"
        "• <code>/bowl amount XdX'w</code> — Challenge with dice format\n"
        "  Example: <code>/bowl 10 2d3w</code> (bet $10, 2 rolls, first to 3 wins)\n\n"
        "• <code>/bowl @username amount MX ftY</code> — Challenge a specific player\n"
        "  Example: <code>/bowl @player 10 MX ft5</code>\n\n"
        "• In groups: <code>/bowl amount</code> — Open challenge for anyone to join\n\n"
        "<b>Rules:</b>\n"
        "• XdX'w format: X = number of rolls (1-3), X' = wins needed (1-10)\n"
        "• MX = Max rounds, ftY = First to Y score\n"
        "• Winner takes the pot (minus house fee)\n\n"
        "💡 Use these commands to start a game. No inline setup needed!",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def xdxw_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()
    user = query.from_user

    if query.data == "xdxw_cancel":
        await query.edit_message_text(f"{pe('cross')} Challenge cancelled.")
        context.user_data.pop('xdxw_challenge', None)
        return

    mode = query.data.replace("xdxw_mode_", "")
    challenge_data = context.user_data.get('xdxw_challenge')

    if not challenge_data:
        await query.edit_message_text(f"{pe('cross')} Challenge data not found. Please try again.")
        return

    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Create the match
    match_id = generate_unique_id("EG")  # EG = Emoji Game
    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(challenge_data['game_type'], "🎮")

    game_sessions[match_id] = {
        "id": match_id,
        "game_type": f"xdxw_{challenge_data['game_type']}",
        "chat_id": challenge_data['chat_id'],
        "chat_type": challenge_data['chat_type'],
        "host_id": user.id,
        "host_username": user.username or f"User_{user.id}",
        "opponent_id": None,
        "bet_amount_usd": challenge_data['bet_amount_usd'],
        "bet_amount": challenge_data['bet_amount_usd'],
        "bet_amount_currency": challenge_data['bet_amount_currency'],
        "currency": challenge_data['currency'],
        "mode": mode,
        "game_rolls": challenge_data['rolls'],
        "target_score": challenge_data['target'],
        "status": "pending",
        "timestamp": str(datetime.now(timezone.utc)),
        "round_timeout": default_round_timeout,  # Store timeout at creation time
        "command_message_id": challenge_data.get('command_message_id'),  # Original command message ID for tagging
    }

    # Add to user's game sessions
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(match_id)
    save_user_data(user.id)

    currency_symbol = CURRENCY_SYMBOLS.get(challenge_data['currency'], "$")
    mode_desc = "Highest wins point" if mode == "normal" else "Lowest wins point"

    # Show challenge with styled Accept/Play with Bot buttons
    accept_btn = apply_button_style(
        InlineKeyboardButton("Accept Challenge", callback_data=f"xdxw_accept_{match_id}"),
        'success', peb('confirm')
    )
    playbot_btn = apply_button_style(
        InlineKeyboardButton("Play with Bot", callback_data=f"xdxw_playbot_{match_id}"),
        'primary', peb('robot')
    )
    cancel_btn = apply_button_style(
        InlineKeyboardButton("Cancel", callback_data=f"xdxw_cancel_{match_id}"),
        'danger', peb('cross')
    )
    keyboard = create_styled_keyboard([
        [accept_btn],
        [playbot_btn, cancel_btn]
    ])

    await query.edit_message_text(
        f"{pe(challenge_data['game_type'])} <b>{challenge_data['game_type'].upper()} CHALLENGE!</b> {pe(challenge_data['game_type'])}\n\n"
        f"{pe('user')} Host: @{user.username or user.id}\n"
        f"{pe('money')} Bet: {currency_symbol}{challenge_data['bet_amount_currency']:.2f}\n"
        f"{pe('target')} Mode: {mode.title()} ({mode_desc})\n"
        f"{pe('rolls')} Rolls per round: {challenge_data['rolls']}\n"
        f"{pe('trophy')} Win condition: First to {challenge_data['target']}\n"
        f"\U0001f194 Match ID: <code>{match_id}</code>\n\n"
        f"Tap a button below to join!",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

    context.user_data.pop('xdxw_challenge', None)

@check_banned
@check_maintenance
async def xdxw_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    match_id = query.data.replace("xdxw_accept_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending":
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    # Check if game type is enabled
    game_key = match.get("game_type", "").replace("xdxw_", "")
    if not is_game_enabled(game_key):
        await query.answer(f"{game_key.title()} game is currently under maintenance.", show_alert=True)
        return

    if user.id == match["host_id"]:
        await query.answer("You can't accept your own challenge!", show_alert=True)
        return

    await ensure_user_in_wallets(user.id, user.username, context=context)

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, match["bet_amount_usd"])
    except ValueError:
        await query.answer("You don't have enough balance for this challenge.", show_alert=True)
        return

    # Also deduct host's bet atomically
    try:
        host_deducted, host_coin = await deduct_wallet_safe(match["host_id"], match["bet_amount_usd"])
    except ValueError:
        # Refund opponent
        credit_wallet_safe(user.id, match["bet_amount_usd"])
        await query.answer("Host has insufficient balance. Challenge cancelled.", show_alert=True)
        return
    save_user_data(match["host_id"])
    save_user_data(user.id)

    # Start the PvP match
    match["opponent_id"] = user.id
    match["opponent_username"] = user.username or f"User_{user.id}"
    match["status"] = "active"

    # Initialize PvP game state
    match["players"] = [match["host_id"], match["opponent_id"]]
    match["usernames"] = {match["host_id"]: match["host_username"], match["opponent_id"]: match["opponent_username"]}
    match["player_rolls"] = {match["host_id"]: [], match["opponent_id"]: []}
    match["points"] = {match["host_id"]: 0, match["opponent_id"]: 0}
    match["last_roller"] = None
    match["current_round"] = 1

    # PERFORMANCE: index both players on this match.
    _index_user_game(match["host_id"], match["id"])
    _index_user_game(match["opponent_id"], match["id"])

    # Add to opponent's game sessions
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(match_id)
    save_user_data(user.id)

    game_type = match["game_type"].replace("xdxw_", "")
    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(game_type, "🎮")

    currency_symbol = CURRENCY_SYMBOLS.get(match["currency"], "$")

    await query.edit_message_text(
        f"{pe('game')} <b>MATCH STARTED!</b>\n\n"
        f"👤 {display_at(match['host_username'])} vs {display_at(match['opponent_username'])}\n"
        f"{pe('money')} Prize Pool: {currency_symbol}{match['bet_amount_currency'] * 2:.2f}\n"
        f"🔢 Rolls per round: {match['game_rolls']}\n"
        f"{pe('trophy')} First to {match['target_score']} wins\n\n"
        f"<b>{display_at(match['host_username'])}'s turn!</b>\n"
        f"Send {match['game_rolls']} {emoji} to start round 1.",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def xdxw_playbot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    match_id = query.data.replace("xdxw_playbot_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending":
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    # Check if game type is enabled
    game_key = match.get("game_type", "").replace("xdxw_", "")
    if not is_game_enabled(game_key):
        await query.answer(f"{game_key.title()} game is currently under maintenance.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the host can play with the bot!", show_alert=True)
        return

    # Convert to PvB game
    match["status"] = "active"
    match["opponent_id"] = 0  # Bot
    match["opponent_username"] = "Bot"

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, match["bet_amount_usd"])
    except ValueError:
        await query.answer("Insufficient balance.", show_alert=True)
        return
    save_user_data(user.id)

    # Setup PvB game state - will be handled by message_listener
    game_type = match["game_type"].replace("xdxw_", "")
    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(game_type, "🎮")

    # Register as active PvB game
    context.chat_data[f"active_pvb_game_{user.id}"] = match_id
    active_pvb_games[user.id] = match_id  # Global fallback

    # Initialize PvB game state
    match["user_score"] = 0
    match["bot_score"] = 0
    match["target_score"] = match.get("target_score", 1)
    match["target_points"] = match["target_score"]
    match["current_round"] = 1
    match["history"] = []
    match["user_rolls"] = []
    match["bot_rolls"] = []
    match["bet_amount"] = match["bet_amount_usd"]  # For PvB compatibility
    match["game_mode"] = match.get("mode", "normal")
    match["bot_rolls_first"] = False  # Default: user rolls first
    match["waiting_for"] = "user"  # Track whose turn it is
    match["players"] = [user.id, 0]
    match["usernames"] = {user.id: match.get("host_username") or (user.username or f"User_{user.id}"), 0: "Bot"}
    match["points"] = {user.id: 0, 0: 0}
    match["player_rolls"] = {user.id: [], 0: []}

    # PERFORMANCE: index the xdxw play-with-bot match.
    _index_user_game(user.id, match_id)

    # Build keyboard with BLUE 'Bot Rolls First' on top and GREEN Cashout below.
    bot_first_btn = apply_button_style(
        InlineKeyboardButton("Bot Rolls First", callback_data=f"xdxw_bot_first_{match_id}"),
        'primary', peb('robot')
    )
    _co_round = match.get("current_round", 1)
    _co_mult = calculate_cashout_multiplier(match, user_id=user.id)
    keyboard = _build_pvb_cashout_keyboard(match_id, _co_round, _co_mult, extra_top_row=[bot_first_btn])

    await query.edit_message_text(
        f"{pe('robot')} <b>PLAYING WITH BOT!</b>\n\n"
        f"<b>Your turn first!</b> Send {match['game_rolls']} {emoji} to start round 1.\n\n"
        f"<i>Tap </i><b>Bot Rolls First</b><i> to swap turn order, or </i><b>Cashout</b><i> to collect </i><b>${match['bet_amount_usd'] * _co_mult:.2f}</b><i> now.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    _register_cashout_button(match_id, user.id, query.message.chat_id, _co_round,
                             message_id=query.message.message_id)

@check_banned
@check_maintenance
async def xdxw_bot_first_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    match_id = query.data.replace("xdxw_bot_first_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "active":
        await query.answer("This game is no longer active.", show_alert=True)
        return

    if user.id != match.get("host_id"):
        await query.answer("Only the host can use this button!", show_alert=True)
        return

    # Check if the game hasn't started yet (no rolls made)
    if match.get("user_rolls") or match.get("bot_rolls"):
        await query.answer("Game has already started! Too late to change.", show_alert=True)
        return

    # Set bot to roll first
    match["bot_rolls_first"] = True
    match["waiting_for"] = "user"  # After bot rolls, user responds
    match["bot_is_rolling"] = True  # Prevent user from rolling during bot's turn

    game_type = match["game_type"].replace("xdxw_", "")
    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(game_type, "🎮")
    game_rolls = match.get("game_rolls", 1)
    chat_id = query.message.chat_id

    # Bot rolls first
    await query.edit_message_text(
        f"{pe('robot')} <b>BOT IS ROLLING FIRST!</b>\n\n"
        f"Bot is rolling {game_rolls} {emoji}...",
        parse_mode=ParseMode.HTML
    )

    # Perform bot rolls - use multi_roll_parallel for lightning-fast speed
    bot_rolls = []
    command_msg_id = match.get('command_message_id')
    try:
        rolls_data = await multi_roll_parallel(context, chat_id, emoji, game_rolls, reply_to_message_id=command_msg_id)
        for msg, _ in rolls_data:
            bot_rolls.append(msg.dice.value)
    except Exception as e:
        logging.error(f"Error sending dice in PvB game: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"{pe('cross')} An error occurred. Game terminated.")
        match['status'] = 'error'
        match.pop('bot_is_rolling', None)
        context.chat_data.pop(f"active_pvb_game_{user.id}", None)
        if user.id in active_pvb_games:
            del active_pvb_games[user.id]
        refund_amount = match.get('bet_amount', 0)
        if refund_amount > 0:
            credit_wallet(user.id, refund_amount)
            update_pnl(user.id)
            save_user_data(user.id)
        return

    match["bot_rolls"] = bot_rolls
    bot_total = sum(bot_rolls)
    bot_rolls_text = " + ".join(str(r) for r in bot_rolls)

    # Clear rolling flag and store bot roll values
    match.pop('bot_is_rolling', None)
    context.user_data['pre_rolled_bot_values'] = bot_rolls
    if "player_rolls" in match and 0 in match["player_rolls"]:
        match["player_rolls"][0] = list(bot_rolls)

    # Get user for mention
    user_id = match.get("host_id")
    user_mention = f'<a href="tg://user?id={user_id}">Player</a>' if user_id else "Player"

    # Cashout button (green) for the player
    _co_round = match.get("current_round", 1)
    _co_mult = calculate_cashout_multiplier(match, user_id=user_id)
    _co_kb = _build_pvb_cashout_keyboard(match_id, _co_round, _co_mult)

    _co_sent = await context.bot.send_message(
        chat_id=chat_id,
        text=f"{pe('robot')} Bot rolled: {bot_rolls_text} = <b>{bot_total}</b>\n\n"
             f"{user_mention}, <b>Your turn!</b> Send {game_rolls} {emoji} to respond.\n"
             f"Or tap Cashout to collect <b>${match.get('bet_amount_usd', match.get('bet_amount', 0)) * _co_mult:.2f}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=_co_kb
    )
    _register_cashout_button(match_id, user_id, chat_id, _co_round,
                             message_id=getattr(_co_sent, 'message_id', None))

    # Schedule PvB timeout
    if context.job_queue:
        _cancel_pvb_timeout_jobs(context, user.id, match_id)
        round_timeout = match.get('round_timeout', default_round_timeout)
        warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
        context.job_queue.run_once(
            pvb_timeout_warn_job,
            when=warn_time,
            data={'user_id': user.id, 'game_id': match_id, 'chat_id': chat_id},
            name=f"pvb_warn_{match_id}"
        )
        context.job_queue.run_once(
            pvb_timeout_finish_job,
            when=round_timeout,
            data={'user_id': user.id, 'game_id': match_id, 'chat_id': chat_id},
            name=f"pvb_finish_{match_id}"
        )

@check_banned
@check_maintenance
async def play_single_emoji_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    game_key = query.data.replace("play_single_", "")
    if game_key not in SINGLE_EMOJI_GAMES:
        await query.edit_message_text("Game not found.")
        return

    # Check if game type is enabled
    if not is_game_enabled(game_key):
        await query.answer(f"{game_key.title()} game is currently under maintenance.", show_alert=True)
        return

    game_config = SINGLE_EMOJI_GAMES[game_key]
    context.user_data['single_emoji_game'] = game_key
    context.user_data['awaiting_single_emoji_bet'] = True
    awaiting_single_emoji_bet[user.id] = game_key

    try:
        await query.edit_message_text(
            f"{game_config['emoji']} <b>{game_config['name']}</b>\n\n"
            f"Enter your bet amount (or 'all'):\n\n"
            f"Multiplier: {game_config['multiplier']}x\n"
            f"Win chance: {game_config['win_chance']*100:.1f}%",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"play_single_emoji_callback edit error: {e}")
        # Still send a response so user knows what to do
        try:
            await query.message.reply_text(
                f"{game_config['emoji']} <b>{game_config['name']}</b>\n\n"
                f"Enter your bet amount (or 'all'):\n\n"
                f"Multiplier: {game_config['multiplier']}x\n"
                f"Win chance: {game_config['win_chance']*100:.1f}%",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

@check_banned
@check_maintenance
async def group_challenge_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    parts = query.data.split("_")
    game_type = parts[2]
    mode = parts[3]
    bet_amount_usd = float(parts[4])
    bet_amount_currency = float(parts[5])
    currency = parts[6]

    # Show number of rolls selection
    keyboard = [
        [InlineKeyboardButton("1 Roll", callback_data=f"gc_rolls_{game_type}_{mode}_{bet_amount_usd}_{bet_amount_currency}_{currency}_1")],
        [InlineKeyboardButton("2 Rolls", callback_data=f"gc_rolls_{game_type}_{mode}_{bet_amount_usd}_{bet_amount_currency}_{currency}_2")],
        [InlineKeyboardButton("3 Rolls", callback_data=f"gc_rolls_{game_type}_{mode}_{bet_amount_usd}_{bet_amount_currency}_{currency}_3")],
    ]

    await safe_edit_message(query,
        f"{pe('target')} <b>Create {game_type.upper()} Challenge</b>\n\n"
        f"Mode: {mode.title()}\n"
        f"Select number of rolls:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def group_challenge_rolls_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    parts = query.data.split("_")
    game_type = parts[2]
    mode = parts[3]
    bet_amount_usd = float(parts[4])
    bet_amount_currency = float(parts[5])
    currency = parts[6]
    rolls = int(parts[7])

    # Show target score (first to X) selection
    keyboard = [
        [InlineKeyboardButton("First to 1", callback_data=f"gc_target_{game_type}_{mode}_{bet_amount_usd}_{bet_amount_currency}_{currency}_{rolls}_1")],
        [InlineKeyboardButton("First to 2", callback_data=f"gc_target_{game_type}_{mode}_{bet_amount_usd}_{bet_amount_currency}_{currency}_{rolls}_2")],
        [InlineKeyboardButton("First to 3", callback_data=f"gc_target_{game_type}_{mode}_{bet_amount_usd}_{bet_amount_currency}_{currency}_{rolls}_3")],
        [InlineKeyboardButton("First to 5", callback_data=f"gc_target_{game_type}_{mode}_{bet_amount_usd}_{bet_amount_currency}_{currency}_{rolls}_5")],
    ]

    await safe_edit_message(query,
        f"{pe('target')} <b>Create {game_type.upper()} Challenge</b>\n\n"
        f"Mode: {mode.title()}\n"
        f"Rolls: {rolls}\n"
        f"Select target score (First to X wins):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def group_challenge_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()
    user = query.from_user

    parts = query.data.split("_")
    game_type = parts[2]
    mode = parts[3]
    bet_amount_usd = float(parts[4])
    bet_amount_currency = float(parts[5])
    currency = parts[6]
    rolls = int(parts[7])
    target_score = int(parts[8])

    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Final check balance
    if get_active_balance_usd(user.id) < bet_amount_usd:
        await query.edit_message_text(f"{pe('cross')} Insufficient balance to create this challenge.")
        return

    # Create the challenge
    match_id = generate_unique_id("GC")
    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(game_type, "🎮")

    game_sessions[match_id] = {
        "id": match_id,
        "game_type": f"group_challenge_{game_type}",
        "chat_id": update.effective_chat.id,
        "host_id": user.id,
        "host_username": user.username or f"User_{user.id}",
        "opponent_id": None,
        "bet_amount_usd": bet_amount_usd,
        "bet_amount": bet_amount_usd,
        "bet_amount_currency": bet_amount_currency,
        "currency": currency,
        "mode": mode,
        "rolls": rolls,
        "target_score": target_score,
        "status": "pending",
        "timestamp": str(datetime.now(timezone.utc)),
        "round_timeout": default_round_timeout,  # Store timeout at creation time
        # `update.message` is None inside callback queries, so we recover the
        # original /dice <amount> message id stashed by create_group_challenge.
        "command_message_id": context.user_data.pop(
            f"gc_cmd_msg_{game_type}_{int(bet_amount_usd*100)}", None
        ),
    }

    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")
    formatted_bet = f"{currency_symbol}{bet_amount_currency:.2f}"
    mode_desc = "Highest wins" if mode == "normal" else "Lowest wins"

    # Pin the challenge message
    challenge_msg = await query.message.reply_text(
        f"{emoji} <b>GROUP CHALLENGE!</b> {emoji}\n\n"
        f"{pe('game')} Game: {game_type.upper()}\n"
        f"👤 Host: @{user.username or user.id}\n"
        f"{pe('money')} Bet: {formatted_bet}\n"
        f"{pe('target')} Mode: {mode.title()} ({mode_desc})\n"
        f"🔢 Rolls: {rolls}\n"
        f"{pe('trophy')} Target: First to {target_score}\n"
        f"🆔 Match ID: <code>{match_id}</code>\n\n"
        f"Tap a button below to join!",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard([
            [apply_button_style(InlineKeyboardButton("Accept Challenge", callback_data=f"gc_accept_{match_id}"), 'success', peb('confirm'))],
            [apply_button_style(InlineKeyboardButton("Play with Bot", callback_data=f"gc_playbot_{match_id}"), 'primary', peb('robot')),
             apply_button_style(InlineKeyboardButton("Cancel", callback_data=f"gc_cancel_{match_id}"), 'danger', peb('cross'))]
        ])
    )

    # Pinning of group emoji-game challenge messages is intentionally disabled.

    await query.edit_message_text(
        f"{pe('check')} Challenge created!\nMatch ID: <code>{match_id}</code>",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def group_challenge_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    match_id = query.data.replace("gc_accept_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending":
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    # Check if game type is enabled
    game_key = match.get("game_type", "").replace("group_challenge_", "")
    if not is_game_enabled(game_key):
        await query.answer(f"{game_key.title()} game is currently under maintenance.", show_alert=True)
        return

    if user.id == match["host_id"]:
        await query.answer("You can't accept your own challenge!", show_alert=True)
        return

    await ensure_user_in_wallets(user.id, user.username, context=context)

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, match["bet_amount_usd"])
    except ValueError:
        await query.answer("You don't have enough balance for this challenge.", show_alert=True)
        return

    # Also deduct host's bet atomically
    try:
        host_deducted, host_coin = await deduct_wallet_safe(match["host_id"], match["bet_amount_usd"])
    except ValueError:
        # Refund opponent
        credit_wallet_safe(user.id, match["bet_amount_usd"])
        await query.answer("Host has insufficient balance. Challenge cancelled.", show_alert=True)
        return
    save_user_data(match["host_id"])
    save_user_data(user.id)

    # Start the PvP match
    match["opponent_id"] = user.id
    match["opponent_username"] = user.username or f"User_{user.id}"
    match["status"] = "active"

    # Ensure all required fields for PvP are initialized
    if "players" not in match:
        match["players"] = [match["host_id"], user.id]
    if "usernames" not in match:
        match["usernames"] = {match["host_id"]: match.get("host_username", f"User_{match['host_id']}"), user.id: user.username or f"User_{user.id}"}
    if "player_rolls" not in match:
        match["player_rolls"] = {match["host_id"]: [], user.id: []}
    if "points" not in match:
        match["points"] = {match["host_id"]: 0, user.id: 0}
    if "last_roller" not in match:
        match["last_roller"] = None
    if "target_points" not in match:
        match["target_points"] = match.get("target_score", 1)

    # PERFORMANCE: index both players for the newly-accepted PvP match.
    _index_user_game(match["host_id"], match["id"])
    _index_user_game(user.id, match["id"])

    currency_symbol = CURRENCY_SYMBOLS.get(match["currency"], "$")
    formatted_bet = f"{currency_symbol}{match['bet_amount_currency']:.2f}"

    await query.edit_message_text(
        f"{pe('game')} <b>MATCH STARTED!</b>\n\n"
        f"👤 {display_at(match['host_username'])} vs {display_at(user.username or str(user.id))}\n"
        f"{pe('money')} Prize Pool: {currency_symbol}{match['bet_amount_currency'] * 2:.2f}\n\n"
        f"Match will begin shortly...",
        parse_mode=ParseMode.HTML
    )

    # Start the actual game (similar to existing PvP logic)
    await asyncio.sleep(2)
    await execute_group_challenge_game(update, context, match_id)

@check_banned
@check_maintenance
async def group_challenge_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cancel button for group challenges."""
    query = update.callback_query
    user = query.from_user

    match_id = query.data.replace("gc_cancel_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending":
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the host can cancel this challenge!", show_alert=True)
        return

    await query.answer()
    match["status"] = "cancelled"

    # Void any side bets placed on this (never-started) match and refund bettors
    try:
        await void_sidebets_for_cashout(match_id, context)
    except Exception as e:
        logging.warning(f"Failed to void sidebets on group cancel: {e}")

    # Group emoji-game challenge messages are no longer pinned.

    await query.edit_message_text(
        f"{pe('cross')} Challenge cancelled by {user.mention_html()}.",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def xdxw_cancel_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the ^xdxw_cancel_<match_id>$ cancel button shown next to
    Play-with-Bot / Accept-Challenge. Only the host can cancel."""
    query = update.callback_query
    user = query.from_user
    match_id = query.data.replace("xdxw_cancel_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending":
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    if user.id != match.get("host_id"):
        await query.answer("Only the host can cancel this challenge!", show_alert=True)
        return

    await query.answer()
    match["status"] = "cancelled"

    # Void any side bets placed on this (never-started) match and refund bettors
    try:
        await void_sidebets_for_cashout(match_id, context)
    except Exception as e:
        logging.warning(f"Failed to void sidebets on xdxw cancel: {e}")

    # Emoji-game challenge messages are no longer pinned.

    try:
        await query.edit_message_text(
            f"{pe('cross')} Challenge cancelled by {user.mention_html()}.",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        # Message might already be edited / deleted — swallow to avoid breaking UX.
        pass

@check_banned
@check_maintenance
async def group_challenge_playbot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    match_id = query.data.replace("gc_playbot_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "pending":
        await query.answer("This challenge is no longer available.", show_alert=True)
        return

    # Check if game type is enabled
    game_key = match.get("game_type", "").replace("group_challenge_", "")
    if not is_game_enabled(game_key):
        await query.answer(f"{game_key.title()} game is currently under maintenance.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the host can play with the bot!", show_alert=True)
        return

    # Check dynamic max bet limit for PvB (house is at risk)
    game_key = match.get("game_type", "").replace("group_challenge_", "")
    pvb_max_bet = get_dynamic_max_bet_for_pvb(f"pvb_{game_key}")
    if match["bet_amount_usd"] > pvb_max_bet:
        await query.answer(
            f"Max bet limit reached! Please lower your bet to ${pvb_max_bet:.2f} or less.",
            show_alert=True
        )
        return

    # Convert to PvB game
    match["status"] = "active"
    match["opponent_id"] = 0  # Bot
    match["opponent_username"] = "Bot"

    # ATOMIC balance check + deduct to prevent race conditions
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, match["bet_amount_usd"])
    except ValueError:
        await query.answer("Insufficient balance.", show_alert=True)
        return
    save_user_data(user.id)

    # Initialize game state for PvP-style play (waiting for emojis)
    match["players"] = [match["host_id"], 0]  # 0 = Bot
    match["usernames"] = {match["host_id"]: match["host_username"], 0: "Bot"}
    match["player_rolls"] = {match["host_id"]: [], 0: []}
    match["points"] = {match["host_id"]: 0, 0: 0}
    match["target_points"] = match.get("target_score", 1)  # Use target_points for consistency
    match["game_mode"] = match.get("mode", "normal")
    match["game_rolls"] = match.get("rolls", 1)
    match["last_roller"] = None
    match["current_round"] = 1
    match["bot_rolls_first"] = False  # Default: user rolls first
    # Legacy PvB bookkeeping that message_listener's PvB block relies on.
    # Without these, `game["user_score"] += 1` hits KeyError after the first
    # round and the bot replies with "An error occurred".
    match["user_id"] = match["host_id"]
    match["user_score"] = 0
    match["bot_score"] = 0
    match["user_rolls"] = []
    match["bot_rolls"] = []
    match["history"] = []
    match["waiting_for"] = "user"
    match["bet_amount"] = match.get("bet_amount_usd", match.get("bet_amount", 0))

    game_type = match["game_type"].replace("group_challenge_", "")
    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(game_type, "🎮")

    # Register active PvB game so cashout callback can find it
    context.chat_data[f"active_pvb_game_{user.id}"] = match_id
    active_pvb_games[user.id] = match_id
    # PERFORMANCE: index for fast per-user lookup in message_listener.
    _index_user_game(user.id, match_id)

    # Show BLUE "Bot Rolls First" on top + GREEN Cashout below
    bot_first_btn = apply_button_style(
        InlineKeyboardButton("Bot Rolls First", callback_data=f"gc_botfirst_{match_id}"),
        'primary', peb('robot')
    )
    _co_round = match.get("current_round", 1)
    _co_mult = calculate_cashout_multiplier(match, user_id=user.id)
    keyboard = _build_pvb_cashout_keyboard(match_id, _co_round, _co_mult, extra_top_row=[bot_first_btn])

    await query.edit_message_text(
        f"{pe('robot')} <b>PLAYING WITH BOT!</b>\n\n"
        f"<b>Your turn first!</b> Send {match['rolls']} {emoji} to start round 1.\n\n"
        f"<i>Tap </i><b>Bot Rolls First</b><i> to swap turn order, or </i><b>Cashout</b><i> to collect </i><b>${match['bet_amount_usd'] * _co_mult:.2f}</b><i> now.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    _register_cashout_button(match_id, user.id, query.message.chat_id, _co_round,
                             message_id=query.message.message_id)

@check_banned
@check_maintenance
async def group_challenge_botfirst_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    match_id = query.data.replace("gc_botfirst_", "")
    match = game_sessions.get(match_id)

    if not match or match.get("status") != "active":
        await query.answer("This game is no longer available.", show_alert=True)
        return

    if user.id != match["host_id"]:
        await query.answer("Only the host can change who rolls first!", show_alert=True)
        return

    # Set bot rolls first
    match["bot_rolls_first"] = True
    match["waiting_for"] = "bot"  # Bot should roll first
    match["bot_is_rolling"] = True  # Prevent user from rolling during bot's turn

    game_type = match["game_type"].replace("group_challenge_", "")
    emoji_map = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
    emoji = emoji_map.get(game_type, "🎮")

    # Bot rolls first - use multi_roll_parallel for lightning-fast speed
    rolls = match.get("rolls", 1)
    command_msg_id = match.get('command_message_id')

    try:
        rolls_data = await multi_roll_parallel(context, query.message.chat_id, emoji, rolls, reply_to_message_id=command_msg_id)
        roll_values = [msg.dice.value for msg, _ in rolls_data]
    except Exception as e:
        logging.error(f"Error sending bot dice in group challenge: {e}")
        roll_values = [0] * rolls  # Fallback

    match.pop("bot_is_rolling", None)
    match["player_rolls"][0] = roll_values  # 0 = Bot
    # Mirror into the legacy PvB slot so message_listener's PvB block (which
    # reads game["bot_rolls"] for bot_rolls_first matches) can score round 1.
    match["bot_rolls"] = list(roll_values)
    total_value = sum(roll_values)

    # Store bot roll values in context to prevent double rolling
    context.user_data['pre_rolled_bot_values'] = roll_values
    # Now it's user's turn
    match["waiting_for"] = "user"

    # Cashout button (green) for the player
    _co_round = match.get("current_round", 1)
    _co_mult = calculate_cashout_multiplier(match, user_id=user.id)
    _co_kb = _build_pvb_cashout_keyboard(match_id, _co_round, _co_mult)

    await query.edit_message_text(
        f"{pe('robot')} <b>BOT ROLLED FIRST!</b>\n\n"
        f"Bot rolled: {roll_values} = <b>{total_value}</b>\n\n"
        f"{user.mention_html()}, <b>Your turn!</b> Send {rolls} {emoji} to respond.\n"
        f"Or tap Cashout to collect <b>${match['bet_amount_usd'] * _co_mult:.2f}</b>:",
        parse_mode=ParseMode.HTML,
        reply_markup=_co_kb
    )
    _register_cashout_button(match_id, user.id, query.message.chat_id, _co_round,
                             message_id=query.message.message_id)

    # Schedule PvB timeout
    if context.job_queue:
        _cancel_pvb_timeout_jobs(context, user.id, match_id)
        round_timeout = match.get('round_timeout', default_round_timeout)
        warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
        context.job_queue.run_once(
            pvb_timeout_warn_job,
            when=warn_time,
            data={'user_id': user.id, 'game_id': match_id, 'chat_id': query.message.chat_id},
            name=f"pvb_warn_{match_id}"
        )
        context.job_queue.run_once(
            pvb_timeout_finish_job,
            when=round_timeout,
            data={'user_id': user.id, 'game_id': match_id, 'chat_id': query.message.chat_id},
            name=f"pvb_finish_{match_id}"
        )

@check_banned
@check_maintenance
async def crash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("crash"):
        await update.message.reply_text(
            "\U0001f527 <b>Crash</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) < 2:
        await update.message.reply_text("Usage: /crash amount [target_multiplier]\nExample: /crash 5 or /crash 10 2.5")
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)

        auto_cashout = None
        if len(args) >= 3:
            auto_cashout = float(args[2])
            if auto_cashout < 1.01 or auto_cashout > 100:
                await update.message.reply_text("Auto cashout must be between 1.01x and 100x")
                return
    except ValueError:
        await update.message.reply_text("Invalid amount or multiplier.")
        return

    if not await check_bet_limits(update, bet_amount, 'crash'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Generate provably fair crash point
    server_seed = generate_server_seed()
    client_seed = generate_client_seed()
    hash_result = create_hash(server_seed, client_seed, 1)
    hex_value = int(hash_result[:13], 16)
    crash_point = max(1.00, min(100.0, (99 / (hex_value % 99 + 1))))
    crash_point = round(crash_point, 2)

    # Determine result
    if auto_cashout:
        if auto_cashout <= crash_point:
            # Win!
            multiplier = auto_cashout
            winnings = bet_amount * multiplier
            profit = winnings - bet_amount
            credit_wallet(user.id, winnings)
            win = True
            result_text = (
                f"📉 <b>CRASH GAME</b>\n\n"
                f"{pe('target')} Auto Cashout: {auto_cashout:.2f}x\n"
                f"{pe('bust')} Crash Point: {crash_point:.2f}x\n\n"
                f"{pe('check')} <b>CASHED OUT!</b>\n"
                f"{pe('money')} Multiplier: {multiplier:.2f}x\n"
                f"{pe('balance')} Profit: ${profit:.2f}\n"
                f"{pe('withdraw')} Total Payout: ${winnings:.2f}"
            )
        else:
            # Lost
            win = False
            multiplier = 0
            result_text = (
                f"📉 <b>CRASH GAME</b>\n\n"
                f"{pe('target')} Auto Cashout: {auto_cashout:.2f}x\n"
                f"{pe('bust')} Crash Point: {crash_point:.2f}x\n\n"
                f"{pe('cross')} <b>CRASHED!</b>\n"
                f"{pe('withdraw')} Lost: ${bet_amount:.2f}\n"
                f"The game crashed before you could cash out!"
            )
    else:
        # Manual mode - show crash point immediately
        result_text = (
            f"📉 <b>CRASH GAME</b>\n\n"
            f"{pe('bust')} Crash Point: {crash_point:.2f}x\n\n"
            f"{pe('info')} Manual mode - Use auto cashout next time!\n"
            f"Example: /crash 10 2.5"
        )
        # Refund since manual mode not fully implemented
        credit_wallet(user.id, bet_amount)
        await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
        return

    # Generate game ID first before using it
    game_id = generate_unique_id('CRASH')

    await update_stats_on_bet(user.id, game_id, bet_amount, win, multiplier=multiplier, context=context)
    save_user_data(user.id)

    # Store game session and provably fair record
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "crash",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "crash_point": crash_point,
        "auto_cashout": auto_cashout,
        "status": "completed",
        "timestamp": str(datetime.now(timezone.utc)),
        "win": win,
        "multiplier": multiplier if win else 0,
        "server_seed": server_seed,
        "client_seed": client_seed,
        "nonce": 1
    }

    # Store provably fair record
    store_provably_fair_record(game_id, "crash", server_seed, client_seed, 1,
                               result_data=f"Crash point: {crash_point:.2f}x, Auto cashout: {auto_cashout:.2f}x" if auto_cashout else f"Crash point: {crash_point:.2f}x")

    # Create keyboard with provably fair button
    keyboard = [[await create_provably_fair_button(game_id, context)]]

    await update.message.reply_text(result_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

@check_banned
@check_maintenance
async def wheel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("wheel"):
        await update.message.reply_text(
            "\U0001f527 <b>Wheel</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text("Usage: /wheel amount\nExample: /wheel 5 or /wheel all")
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet_amount, 'wheel'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Generate provably fair result
    server_seed = generate_server_seed()
    client_seed = generate_client_seed()
    segment = get_provably_fair_result(server_seed, client_seed, 1, len(WHEEL_SEGMENTS))
    multiplier = WHEEL_SEGMENTS[segment]

    winnings = bet_amount * multiplier
    profit = winnings - bet_amount
    win = multiplier >= 1.0

    # Generate game ID first before using it
    game_id = generate_unique_id('WHEEL')

    credit_wallet(user.id, winnings)
    await update_stats_on_bet(user.id, game_id, bet_amount, win, multiplier=multiplier, context=context)
    save_user_data(user.id)

    # Store game session and provably fair record
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "wheel",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "segment": segment,
        "multiplier": multiplier,
        "status": "completed",
        "timestamp": str(datetime.now(timezone.utc)),
        "win": win,
        "server_seed": server_seed,
        "client_seed": client_seed,
        "nonce": 1
    }

    # Store provably fair record
    store_provably_fair_record(game_id, "wheel", server_seed, client_seed, 1,
                               result_data=f"Segment: {segment + 1}, Multiplier: {multiplier:.1f}x")

    result_text = (
        f"{pe('wheel')} <b>WHEEL OF FORTUNE</b>\n"
        f"Game ID: <code>{game_id}</code>\n\n"
        f"{pe('target')} Segment: #{segment + 1}\n"
        f"{pe('money')} Multiplier: {multiplier:.1f}x\n\n"
    )

    if win:
        result_text += f"{pe('win')} <b>WIN!</b>\n💵 Profit: ${profit:.2f}\n💸 Total Payout: ${winnings:.2f}"
    else:
        result_text += f"{pe('cross')} <b>LOST</b>\n💸 Lost: ${abs(profit):.2f}"

    # Create keyboard with provably fair button
    keyboard = [[await create_provably_fair_button(game_id, context)]]

    await update.message.reply_text(result_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

@check_banned
@check_maintenance
async def scratch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("scratch"):
        await update.message.reply_text(
            "\U0001f527 <b>Scratch</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text("Usage: /scratch amount\nExample: /scratch 5 or /scratch all")
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet_amount, 'scratch'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Generate 9 symbols using weighted random
    server_seed = generate_server_seed()
    client_seed = generate_client_seed()

    symbols = []
    symbol_list = []
    for sym, data in SCRATCH_SYMBOLS.items():
        symbol_list.extend([sym] * data["weight"])

    for i in range(9):
        idx = get_provably_fair_result(server_seed, client_seed, i + 1, len(symbol_list))
        symbols.append(symbol_list[idx])

    # Check for 3 matches
    from collections import Counter
    symbol_counts = Counter(symbols)
    match_symbol = None
    for sym, count in symbol_counts.items():
        if count >= 3:
            match_symbol = sym
            break

    if match_symbol and match_symbol != "❌":
        multiplier = SCRATCH_SYMBOLS[match_symbol]["mult"]
        winnings = bet_amount * multiplier
        profit = winnings - bet_amount
        win = True
        credit_wallet(user.id, winnings)
    else:
        multiplier = 0
        win = False
        winnings = 0
        profit = -bet_amount

    await update_stats_on_bet(user.id, generate_unique_id('SCRATCH'), bet_amount, win, multiplier=multiplier, context=context)
    save_user_data(user.id)

    # Display card
    card_display = f"{symbols[0]} {symbols[1]} {symbols[2]}\n{symbols[3]} {symbols[4]} {symbols[5]}\n{symbols[6]} {symbols[7]} {symbols[8]}"

    result_text = (
        f"🎫 <b>SCRATCH CARD</b>\n\n"
        f"{card_display}\n\n"
    )

    if win:
        result_text += f"{pe('win')} <b>3 {match_symbol} MATCH!</b>\n💰 Multiplier: {multiplier}x\n💵 Profit: ${profit:.2f}\n💸 Total Payout: ${winnings:.2f}"
    else:
        result_text += f"{pe('cross')} <b>NO MATCH</b>\n💸 Lost: ${bet_amount:.2f}\nTry again!"

    await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)

@check_banned
@check_maintenance
async def coinchain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("coinchain"):
        await update.message.reply_text(
            "\U0001f527 <b>Coinchain</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text("Usage: /coinchain amount\nExample: /coinchain 5 or /coinchain all")
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet_amount, 'coinchain'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Create game session
    game_id = generate_unique_id('COINCHAIN')
    game_sessions[game_id] = {
        "id": game_id,
        "user_id": user.id,
        "game_type": "coin_chain",
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "chain_length": 0,
        "current_multiplier": 1.0,
        "status": "active"
    }

    keyboard = [
        [InlineKeyboardButton("Heads", callback_data=f"coinchain_{game_id}_heads"),
         InlineKeyboardButton("Tails", callback_data=f"coinchain_{game_id}_tails")],
        [InlineKeyboardButton("Cash Out", callback_data=f"coinchain_{game_id}_cashout"),
         InlineKeyboardButton("Cancel", callback_data=f"coinchain_{game_id}_cancel")]
    ]

    text = (
        f"{pe('coin')} <b>COIN TOSS CHAIN</b>\n\n"
        f"{pe('balance')} Bet: ${bet_amount:.2f}\n"
        f"⛓️ Chain: 0 wins\n"
        f"{pe('money')} Current: ${bet_amount:.2f} (1.0x)\n\n"
        f"Choose Heads or Tails!\n"
        f"Each correct guess multiplies by 1.9x"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

@check_banned
@check_maintenance
async def coinchain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    # Global dedup guard
    if not await _acquire_callback(query.id):
        try: await query.answer()
        except: pass
        return

    try:
        parts = query.data.split('_')
        game_id = parts[1]
        action = parts[2] if len(parts) > 2 else None

        game = game_sessions.get(game_id)
        if not game or game["status"] != "active":
            await query.answer()
            await query.edit_message_text(f"{pe('cross')} Game not found or already ended.")
            return

        user_id = game["user_id"]

        # SECURITY: Only the game owner can interact
        if user.id != user_id:
            await query.answer("This is not your game!", show_alert=True)
            return

        # Flood guard for game actions
        if not _check_user_action_flood(user.id, query.data[:20], _USER_ACTION_COOLDOWN_GAME):
            await query.answer("⏳ Too fast!", show_alert=False)
            return

        await query.answer()

        if action == "cashout":
            # Cash out current winnings
            multiplier = game["current_multiplier"]
            winnings = game["bet_amount"] * multiplier
            profit = winnings - game["bet_amount"]

            credit_wallet(user_id, winnings)
            game["status"] = "completed"
            await update_stats_on_bet(user_id, game_id, game["bet_amount"], True, multiplier=multiplier, context=context)
            save_user_data(user_id)

            result_text = (
                f"{pe('coin')} <b>COIN TOSS CHAIN</b>\n\n"
                f"{pe('money')} <b>CASHED OUT!</b>\n\n"
                f"⛓️ Chain Length: {game['chain_length']} wins\n"
                f"{pe('money')} Final Multiplier: {multiplier:.2f}x\n"
                f"{pe('balance')} Profit: ${profit:.2f}\n"
                f"{pe('withdraw')} Total Payout: ${winnings:.2f}"
            )
            await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)
            return

        elif action == "cancel":
            game["status"] = "cancelled"
            await query.edit_message_text(f"{pe('cross')} Coin chain game cancelled. Bet refunded.", parse_mode=ParseMode.HTML)
            credit_wallet(user_id, game["bet_amount"])
            save_user_data(user_id)
            return

        elif action in ["heads", "tails"]:
            # Generate coin flip result
            server_seed = generate_server_seed()
            client_seed = generate_client_seed()
            result_num = get_provably_fair_result(server_seed, client_seed, game["chain_length"] + 1, 2)
            result = "heads" if result_num == 0 else "tails"

            if result == action:
                # Correct guess!
                game["chain_length"] += 1
                game["current_multiplier"] *= 1.9

                keyboard = [
                    [InlineKeyboardButton("Heads", callback_data=f"coinchain_{game_id}_heads"),
                     InlineKeyboardButton("Tails", callback_data=f"coinchain_{game_id}_tails")],
                    [InlineKeyboardButton("Cash Out", callback_data=f"coinchain_{game_id}_cashout"),
                     InlineKeyboardButton("Cancel", callback_data=f"coinchain_{game_id}_cancel")]
                ]

                current_value = game["bet_amount"] * game["current_multiplier"]

                text = (
                    f"{pe('coin')} <b>COIN TOSS CHAIN</b>\n\n"
                    f"{pe('check')} Correct! It was {result.upper()}!\n\n"
                    f"⛓️ Chain: {game['chain_length']} wins\n"
                    f"{pe('money')} Current: ${current_value:.2f} ({game['current_multiplier']:.2f}x)\n\n"
                    f"Keep going or cash out?"
                )

                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                # Wrong guess - lose everything
                game["status"] = "completed"
                await update_stats_on_bet(user_id, game_id, game["bet_amount"], False, context=context)
                save_user_data(user_id)

                result_text = (
                    f"{pe('coin')} <b>COIN TOSS CHAIN</b>\n\n"
                    f"{pe('cross')} Wrong! It was {result.upper()}!\n\n"
                    f"⛓️ Chain Length: {game['chain_length']} wins\n"
                    f"{pe('withdraw')} Lost: ${game['bet_amount']:.2f}\n\n"
                    f"Better luck next time!"
                )
                await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)
    finally:
        _release_callback(query.id)

async def cancel_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return  # Silently ignore non-admin users
    await ensure_user_in_wallets(user.id, user.username, context=context)
    cancelled = 0
    for game_id, game in list(game_sessions.items()):
        if game.get("status") == 'active' and 'players' in game: # Only cancel PvP games
            game["status"] = 'cancelled'
            for uid in game["players"]:
                credit_wallet(uid, game["bet_amount"])
                save_user_data(uid)
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"Your match {game_id} has been cancelled by the bot owner. Your bet has been refunded."
                    )
                except Exception: pass
            cancelled += 1
    await update.message.reply_text(
        f"Cancelled {cancelled} active PvP matches. Bets refunded to players."
    )

@check_banned
@check_maintenance
async def stop_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not is_admin(user.id):
        await query.answer("Only the owner can confirm stop.", show_alert=True)
        return
    if query.data == "stop_confirm_yes":
        bot_stopped = True
        await query.edit_message_text(f"{pe('check')} Bot is now stopped. No new matches can be started.")
    else:
        await query.edit_message_text("Stop cancelled. Bot remains active.")

@check_banned
@check_maintenance
async def bank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    # FIX: Show the house balance from bot settings
    bank = bot_settings.get("house_balance", 0.0)
    await update.message.reply_text(f"{pe('house')} <b>BOT BANK</b>\n\n"
                                    f"This is the designated house balance.\n"
                                    f"Current House Balance: <b>${bank:,.2f}</b>",
                                    parse_mode=ParseMode.HTML)

@check_banned
@check_maintenance
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)
    stats = user_stats[user.id]

    # Determine if in group chat
    is_group = False
    if update.callback_query:
        try:
            is_group = update.callback_query.message.chat.type in ["group", "supergroup"]
        except AttributeError:
            pass
    elif update.effective_chat:
        is_group = update.effective_chat.type in ["group", "supergroup"]

    # Check if showing 24hr or all-time stats (for group chats)
    stats_view = context.user_data.get('stats_view', 'all_time')

    # Get user level
    level_data = get_user_level(user.id)

    # Get user's DISPLAY currency (what they want to see amounts in,
    # not the wallet crypto). Every amount below is rendered compact
    # so huge lifetime numbers don't break the layout.
    user_currency = get_display_currency(user.id)
    balance = get_total_balance_usd(user.id)
    formatted_balance = format_compact_for_user(user.id, balance, with_usdt_estimate=(user_currency != "USDT"))

    if is_group and stats_view == '24h':
        # Calculate 24hr stats from game_sessions
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)
        user_game_ids = stats.get("game_sessions", [])

        bets_24h = 0
        wins_24h = 0
        losses_24h = 0
        wagered_24h = 0.0

        for gid in user_game_ids:
            game = game_sessions.get(gid)
            if not game:
                continue
            try:
                ts = game.get("timestamp", "")
                game_time = datetime.fromisoformat(ts.replace('Z', '+00:00')) if ts else None
                if game_time and game_time >= cutoff:
                    bets_24h += 1
                    bet_amt = game.get("bet_amount", 0.0)
                    wagered_24h += bet_amt
                    if game.get("win") is True:
                        wins_24h += 1
                    elif game.get("win") is False:
                        losses_24h += 1
            except (ValueError, TypeError):
                continue

        win_rate = (wins_24h / bets_24h * 100) if bets_24h > 0 else 0
        formatted_wagered = format_compact_for_user(user.id, wagered_24h)

        text = (
            f"{pe('chart')} <b>Your Stats - Last 24 Hours</b>\n\n"
            f"👤 <b>User:</b> @{stats.get('userinfo', {}).get('username','N/A')}\n"
            f"🦄 <b>Level:</b> {level_data['name']}\n"
            f"{pe('money')} <b>Balance:</b> {formatted_balance}\n\n"
            f"{pe('dice')} <b>Betting Stats (24h):</b>\n"
            f"  Total Bets: {bets_24h}\n"
            f"  Wins: {wins_24h} | Losses: {losses_24h}\n"
            f"  Win Rate: {win_rate:.1f}%\n"
            f"  Total Wagered: {formatted_wagered}\n"
        )
    else:
        # All-time stats (default)
        total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
        total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))

        total_wagered = stats.get('bets', {}).get('amount', 0.0)
        _fmt = lambda amt: format_compact_for_user(user.id, amt)
        formatted_wagered = _fmt(total_wagered)
        formatted_deposits = _fmt(total_deposits)
        formatted_withdrawals = _fmt(total_withdrawals)
        formatted_tips_received = _fmt(stats.get('tips_received', {}).get('amount', 0.0))
        formatted_tips_sent = _fmt(stats.get('tips_sent', {}).get('amount', 0.0))
        formatted_rain = _fmt(stats.get('rain_received', {}).get('amount', 0.0))
        formatted_pnl = _fmt(stats.get('pnl', 0.0))

        referral_count = len(stats.get('referral', {}).get('referred_users', []))
        referral_commission = stats.get('referral', {}).get('commission_earned', 0.0)
        formatted_commission = _fmt(referral_commission)

        achievement_count = len(stats.get('achievements', []))

        total_bets = stats.get('bets', {}).get('count', 0)
        wins = stats.get('bets', {}).get('wins', 0)
        losses = stats.get('bets', {}).get('losses', 0)
        win_rate = (wins / total_bets * 100) if total_bets > 0 else 0

        title = "📊 <b>Your Complete Stats</b>" if not is_group else "📊 <b>Your Stats - All Time</b>"

        text = (
            f"{title}\n\n"
            f"👤 <b>User Info:</b>\n"
            f"  Username: @{stats.get('userinfo', {}).get('username','N/A')}\n"
            f"  User ID: <code>{user.id}</code>\n"
            f"  Join Date: {stats.get('userinfo', {}).get('join_date', 'N/A')[:10]}\n"
            f"  Currency: {user_currency}\n\n"
            f"🦄 <b>Level:</b> {level_data['name']}\n"
            f"  Rakeback Rate: {level_data['rakeback_percentage']}%\n\n"
            f"{pe('money')} <b>Balance:</b> {formatted_balance}\n\n"
            f"{pe('dice')} <b>Betting Stats:</b>\n"
            f"  Total Bets: {total_bets}\n"
            f"  Wins: {wins} | Losses: {losses}\n"
            f"  Win Rate: {win_rate:.1f}%\n"
            f"  Total Wagered: {formatted_wagered}\n"
            f"  PvP Wins: {stats.get('bets', {}).get('pvp_wins', 0)}\n\n"
            f"{pe('balance')} <b>Financial Stats:</b>\n"
            f"  Deposits: {len(stats.get('deposits',[]))} ({formatted_deposits})\n"
            f"  Withdrawals: {len(stats.get('withdrawals',[]))} ({formatted_withdrawals})\n"
            f"  P&L: {formatted_pnl}\n\n"
            f"{pe('gift')} <b>Social Stats:</b>\n"
            f"  Tips Received: {stats.get('tips_received', {}).get('count', 0)} ({formatted_tips_received})\n"
            f"  Tips Sent: {stats.get('tips_sent', {}).get('count', 0)} ({formatted_tips_sent})\n"
            f"  Rain Received: {stats.get('rain_received', {}).get('count', 0)} ({formatted_rain})\n\n"
            f"{pe('push')} <b>Referral Stats:</b>\n"
            f"  Referred Users: {referral_count}\n"
            f"  Commission Earned: {formatted_commission}\n\n"
            f"{pe('trophy')} <b>Achievements:</b> {achievement_count} unlocked\n"
        )

    # Generate stats template image - no inline buttons
    stats_image = await generate_stats_image(user.id, context, period=stats_view)
    if stats_image and not from_callback:
        try:
            sent_message = await update.message.reply_photo(
                photo=stats_image
            )
            set_menu_owner(sent_message, user.id)
            return
        except Exception as e:
            logging.error(f"Error sending stats image: {e}")

    if from_callback:
        # For callbacks, generate new image and edit
        stats_image = await generate_stats_image(user.id, context, period=stats_view)
        if stats_image:
            try:
                await update.callback_query.message.reply_photo(
                    photo=stats_image
                )
                await update.callback_query.message.delete()
                return
            except Exception as e:
                logging.error(f"Error editing stats image: {e}")
        await safe_edit_message(update.callback_query, f"{pe('chart')} Stats updated", parse_mode=ParseMode.HTML)
    else:
        sent_message = await update.message.reply_text(f"{pe('chart')} Your Stats", parse_mode=ParseMode.HTML)
        set_menu_owner(sent_message, user.id)

@check_banned
@check_maintenance
async def stats_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stats 24h/all-time toggle in group chats"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data: stats_24h_USERID or stats_alltime_USERID
    parts = query.data.split("_")
    if len(parts) < 3:
        return

    button_user_id = int(parts[-1]) if parts[-1].isdigit() else None

    # User-specific button check
    if button_user_id and user.id != button_user_id:
        await query.answer("This menu is not for you!", show_alert=True)
        return

    await query.answer()

    if parts[1] == "24h":
        context.user_data['stats_view'] = '24h'
    else:
        context.user_data['stats_view'] = 'all_time'

    await stats_command(update, context, from_callback=True)

@check_banned
@check_maintenance
async def limits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display current game limits for all users"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)

    # Determine if in group chat
    is_group = update.effective_chat.type in ["group", "supergroup"]

    # Get game limits from bot_settings
    game_limits = bot_settings.get('game_limits', {})

    if not game_limits:
        msg = "⚖️ <b>Game Limits</b>\n\n❌ No limits have been set yet."
    else:
        msg = "⚖️ <b>Game Limits</b>\n\n"

        # Group games by category
        for game_name in sorted(game_limits.keys()):
            limits = game_limits[game_name]
            min_bet = limits.get('min', 'Not set')
            max_bet = limits.get('max', 'Not set')

            display_name = game_name.replace('_', ' ').title()
            min_str = f"${min_bet:.2f}" if isinstance(min_bet, (int, float)) else min_bet
            max_str = f"${max_bet:.2f}" if isinstance(max_bet, (int, float)) else max_bet

            msg += f"{pe('game')} <b>{display_name}</b>\n"
            msg += f"   Min: {min_str} | Max: {max_str}\n\n"

    # Use helper bot in groups if available
    if is_group and helper_bot:
        try:
            await helper_bot.send_message(
                chat_id=update.effective_chat.id,
                text=msg,
                parse_mode=ParseMode.HTML
            )
            return
        except Exception as e:
            logging.warning(f"Helper bot failed for /limits: {e}")

    # Otherwise use main bot
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return  # Silently ignore non-admin users
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not user_stats:
        await update.message.reply_text("No users found in the database.")
        return

    context.user_data['users_page'] = 0
    await send_users_page(update, context)

async def send_users_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = context.user_data.get('users_page', 0)
    page_size = 5
    user_ids = list(user_stats.keys())
    start_index = page * page_size
    end_index = start_index + page_size

    paginated_user_ids = user_ids[start_index:end_index]

    if update.callback_query and not paginated_user_ids:
        await update.callback_query.answer("No more users.", show_alert=True)
        return

    msg = "<b>All User Stats (Page {}):</b>\n\n".format(page + 1)
    for uid in paginated_user_ids:
        stats = user_stats[uid]
        username = stats.get('userinfo', {}).get('username', 'N/A')
        pnl = stats.get('pnl', 0.0)
        msg += (
            f"👤 @{username} (ID: <code>{uid}</code>)\n"
            f"  - 💰 <b>Balance:</b> ${get_total_balance_usd(uid):.2f}\n"
            f"  - 📈 <b>P&L:</b> ${pnl:.2f}\n"
            f"  - 🎲 <b>Bets:</b> {stats.get('bets',{}).get('count',0)} (W: {stats.get('bets',{}).get('wins',0)}, L: {stats.get('bets',{}).get('losses',0)})\n"
        )

    keyboard = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(f"{pe('left')} Previous", callback_data="users_prev"))
    if end_index < len(user_ids):
        row.append(InlineKeyboardButton(f"Next {pe('arrow_right')}", callback_data="users_next"))
    if row:
        keyboard.append(row)

    # NEW: Back to admin dashboard button
    keyboard.append([InlineKeyboardButton("Back to Admin", callback_data="admin_dashboard")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

@check_banned
@check_maintenance
async def users_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("This is an admin-only button.", show_alert=True)
        return

    await query.answer()
    action = query.data
    page = context.user_data.get('users_page', 0)

    if action == "users_next":
        context.user_data['users_page'] = page + 1
    elif action == "users_prev":
        context.user_data['users_page'] = max(0, page - 1)

    await send_users_page(update, context)

@check_banned
@check_maintenance
async def pvb_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    # Ban check for callbacks
    if user.id in bot_settings.get("banned_users", []):
        await query.answer("You are banned.", show_alert=True)
        return
    if user.id in bot_settings.get("tempbanned_users", []):
        await query.answer("You are temporarily banned.", show_alert=True)
        return

    # Ownership check
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await ensure_user_in_wallets(query.from_user.id, query.from_user.username, context=context)

    if data.startswith("pvb_start_"):
        # Check for ongoing game before starting a new one
        ongoing_game_id, ongoing_game_type = get_user_active_emoji_game(user.id)
        if ongoing_game_id:
            game_name = extract_game_name(ongoing_game_type)
            await query.answer(
                f"{pe('warning')} You have an ongoing {game_name} match (ID: {ongoing_game_id}). Complete it first!",
                show_alert=True
            )
            return

        game_type = data.replace("pvb_start_", "")

        # Check per-game maintenance status
        if not is_game_enabled(game_type):
            emoji_map = {"dice": "\U0001f3b2", "darts": "\U0001f3af", "goal": "\u26bd", "bowl": "\U0001f3b3"}
            emoji = emoji_map.get(game_type, "\U0001f3ae")
            await query.answer(
                f"\U0001f527 {emoji} {game_type.title()} game is under maintenance.",
                show_alert=True
            )
            return

        context.user_data['game_type'] = game_type

        # Show mode selection (Normal/Crazy)
        keyboard = [
            [InlineKeyboardButton("Normal Mode", callback_data=f"pvb_mode_normal_{game_type}")],
            [InlineKeyboardButton("Crazy Mode", callback_data=f"pvb_mode_crazy_{game_type}")],
            [InlineKeyboardButton("Cancel", callback_data="cancel_game")]
        ]
        await query.edit_message_text(
            f"{pe('game')} <b>Select Game Mode</b>\n\n"
            f"<b>Normal Mode:</b> Highest score wins\n"
            f"<b>Crazy Mode:</b> Lowest score wins",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        set_menu_owner(query.message, user.id)
        return

    elif data.startswith("pvb_mode_"):
        # Extract mode and game_type from callback data
        parts = data.split("_")
        mode = parts[2]  # normal or crazy
        game_type = "_".join(parts[3:])  # handle game types with underscores
        context.user_data['game_type'] = game_type
        context.user_data['game_mode'] = mode

        # Show roll selection (1/2/3 rolls)
        keyboard = [
            [InlineKeyboardButton("1 Roll", callback_data=f"pvb_rolls_1_{mode}_{game_type}")],
            [InlineKeyboardButton(f"{pe('first')} 2 Rolls", callback_data=f"pvb_rolls_2_{mode}_{game_type}")],
            [InlineKeyboardButton(f"{pe('first')} 3 Rolls", callback_data=f"pvb_rolls_3_{mode}_{game_type}")],
            [InlineKeyboardButton("Cancel", callback_data="cancel_game")]
        ]
        await query.edit_message_text(
            f"{pe('game')} <b>Select Number of Rolls</b>\n\n"
            f"Mode: <b>{mode.capitalize()}</b>\n"
            f"Choose how many times each player will roll:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        set_menu_owner(query.message, user.id)
        return

    elif data.startswith("pvb_rolls_"):
        # Extract rolls, mode, and game_type from callback data
        parts = data.split("_")
        rolls = int(parts[2])  # 1, 2, or 3
        mode = parts[3]  # normal or crazy
        game_type = "_".join(parts[4:])  # handle game types with underscores
        context.user_data['game_type'] = game_type
        context.user_data['game_mode'] = mode
        context.user_data['game_rolls'] = rolls

        # Now call start_pvb_conversation to enter the conversation handler
        return await start_pvb_conversation_after_setup(query, context)

    elif data.startswith("pvp_info_"):
        game_type_map = {"dice_bot": "dice", "football": "goal", "darts": "darts", "bowling": "bowl"}
        game_type = game_type_map.get(data.replace("pvp_info_", ""), "dice")

        # Update instructions with new command format
        await query.edit_message_text(
            f"{pe('game')} <b>PvP {game_type.capitalize()} Game</b>\n\n"
            f"<b>Command Format:</b>\n"
            f"<code>/{game_type} @username amount MX ftY</code>\n\n"
            f"<b>Parameters:</b>\n"
            f"• <code>@username</code> - Your opponent's username\n"
            f"• <code>amount</code> - Bet amount (or 'all')\n"
            f"• <code>MX</code> - Mode and rolls:\n"
            f"  - <code>N1</code>, <code>N2</code>, <code>N3</code> - Normal mode (1, 2, or 3 rolls)\n"
            f"  - <code>C1</code>, <code>C2</code>, <code>C3</code> - Crazy mode (1, 2, or 3 rolls)\n"
            f"• <code>ftY</code> - First to Y points wins\n\n"
            f"<b>Examples:</b>\n"
            f"• <code>/{game_type} @player 10 N1 ft3</code> - Normal mode, 1 roll, first to 3 points\n"
            f"• <code>/{game_type} @player 20 C2 ft5</code> - Crazy mode, 2 rolls, first to 5 points\n"
            f"• <code>/{game_type} @player all N3 ft3</code> - Normal mode, 3 rolls, bet all\n\n"
            f"<b>Mode Explanation:</b>\n"
            f"• <b>Normal (N):</b> Highest total score wins the point\n"
            f"• <b>Crazy (C):</b> Lowest total score wins the point",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f"game_{data.replace('pvp_info_', '')}")]])
        )

async def he_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    all_deal_files = [f for f in os.listdir(ESCROW_DIR) if f.endswith('.json')]
    if not all_deal_files:
        await update.message.reply_text("No escrow deals found.")
        return
    all_deal_files.sort(reverse=True)
    msg = "📜 <b>All Escrow Deals History (Latest 20):</b>\n\n"
    count = 0
    for fname in all_deal_files:
        if count >= 20: break
        with open(os.path.join(ESCROW_DIR, fname), 'r') as f:
            deal = json.load(f)
            seller_name = deal.get('seller', {}).get('username', 'N/A')
            buyer_name = deal.get('buyer', {}).get('username', 'N/A')
            msg += (f"<b>ID:</b> <code>{deal['id']}</code> | <b>Status:</b> {deal.get('status', 'N/A').capitalize()}\n"
                    f"<b>Amount:</b> ${deal.get('amount', 0.0):.2f} | <b>Date:</b> {deal.get('timestamp', 'N/A').split('T')[0]}\n"
                    f"<b>Seller:</b> @{seller_name}, <b>Buyer:</b> @{buyer_name}\n--------------------\n")
            count += 1
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def hc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)

    all_games = sorted(game_sessions.values(), key=lambda x: x.get("timestamp", ""), reverse=True)
    if not all_games:
        await update.message.reply_text("No game matches found.")
        return

    # Show pending games first for the owner
    pending_games = [g for g in all_games if g.get("status") == "active"]
    completed_games = [g for g in all_games if g.get("status") != "active"]

    msg = ""
    if pending_games:
        msg += "⏳ <b>Owner View: Active/Pending Games:</b>\n\n"
        for game in pending_games[:10]: # Limit display
             game_type = game['game_type'].replace('_', ' ').title()
             msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"
             if 'players' in game:
                p_names = [game['usernames'].get(pid, f"ID:{pid}") for pid in game['players']]
                msg += f"<b>Players:</b> {', '.join(p_names)}\n"
             else:
                uname = user_stats.get(game['user_id'], {}).get('userinfo',{}).get('username', 'N/A')
                msg += f"<b>Player:</b> @{uname}\n"
             msg += "--------------------\n"

    msg += "\n📜 <b>All Casino Matches History (Latest 20 Completed):</b>\n\n"
    for match in completed_games[:20]:
        game_type = match['game_type'].replace('_', ' ').title()
        msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{match['id']}</code>\n"
        if 'players' in match: # PvP
            p1_id, p2_id = match['players']
            p1_name = match['usernames'].get(p1_id, f"ID:{p1_id}")
            p2_name = match['usernames'].get(p2_id, f"ID:{p2_id}")
            score = f"{match['points'].get(p1_id, 0)} - {match['points'].get(p2_id, 0)}"
            msg += f"<b>Match:</b> {p1_name} vs {p2_name}\n<b>Score:</b> {score} | "
        else: # Solo game
            uname = user_stats.get(match['user_id'], {}).get('userinfo',{}).get('username', 'N/A')
            msg += f"<b>Player:</b> @{uname} | "

        msg += (f"<b>Bet:</b> ${match['bet_amount']:.2f}\n"
                f"<b>Status:</b> {match.get('status', 'N/A').capitalize()}\n--------------------\n")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@check_banned
@check_maintenance
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's game history with template image and pagination inline buttons."""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    stats = user_stats.get(user.id, {})
    game_ids = list(reversed(stats.get('game_sessions', [])))
    total_games = len(game_ids)

    if total_games == 0:
        await update.message.reply_text(
            f"{pe('chart')} <b>Game History</b>\n\n"
            f"No games found. Start playing to see your history!",
            parse_mode=ParseMode.HTML
        )
        return

    page = 0
    # Generate history template image
    history_image = await generate_history_image(user.id, context, page)

    # Build pagination keyboard
    keyboard = _build_history_keyboard(game_ids, page, user.id)

    if history_image:
        sent = await update.message.reply_photo(
            photo=history_image,
            caption=f"{pe('chart')} <b>Game History</b> ({total_games} games)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        sent = await update.message.reply_text(
            f"{pe('chart')} <b>Game History</b> ({total_games} games)\n\n"
            f"Use the buttons below to browse your games.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    set_menu_owner(sent, user.id)

async def history_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle history page navigation callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    # Parse callback: hist_page_{user_id}_{page}
    parts = query.data.split('_')
    if len(parts) < 4:
        return
    target_user_id = int(parts[2])
    page = int(parts[3])

    # Verify ownership
    if query.from_user.id != target_user_id:
        await query.answer("This is not your history.", show_alert=True)
        return

    stats = user_stats.get(target_user_id, {})
    game_ids = list(reversed(stats.get('game_sessions', [])))
    total_games = len(game_ids)

    # Generate new page image
    history_image = await generate_history_image(target_user_id, context, page)
    keyboard = _build_history_keyboard(game_ids, page, target_user_id)

    try:
        if history_image:
            await query.message.delete()
            sent = await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=history_image,
                caption=f"{pe('chart')} <b>Game History</b> ({total_games} games) - Page {page + 1}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            set_menu_owner(sent, target_user_id)
        else:
            await safe_edit_message(
                query,
                f"{pe('chart')} <b>Game History</b> ({total_games} games) - Page {page + 1}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logging.error(f"History page callback error: {e}")

async def history_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle viewing a specific game from history."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    # Parse callback: hist_view_{game_id}
    game_id = query.data.replace("hist_view_", "")
    game = game_sessions.get(game_id)

    if not game:
        await query.answer("Game data not found.", show_alert=True)
        return

    # Verify ownership
    if game.get('user_id') != query.from_user.id:
        await query.answer("This is not your game.", show_alert=True)
        return

    game_type = game.get('game_type', 'unknown').replace('_', ' ').title()
    bet_amount = game.get('bet_amount', 0.0)
    multiplier = game.get('multiplier', 0)
    is_win = game.get('win', False)
    profit = bet_amount * multiplier - bet_amount if multiplier else -bet_amount
    risk = game.get('risk', '')
    rows = game.get('rows', '')
    timestamp = game.get('timestamp', 'N/A')

    # Format timestamp
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        timestamp = dt.strftime('%Y-%m-%d %H:%M UTC')
    except Exception:
        pass

    result_emoji = pe('win') if is_win else pe('cross')
    result_text = "WIN" if is_win else "LOSS"
    profit_text = f"+${profit:.2f}" if profit >= 0 else f"-${abs(profit):.2f}"

    msg = (
        f"{pe('chart')} <b>Game Details</b>\n\n"
        f"<b>Game:</b> {game_type}\n"
        f"<b>Game ID:</b> <code>{game_id}</code>\n"
        f"<b>Bet:</b> ${bet_amount:.2f}\n"
    )

    if multiplier:
        msg += f"<b>Multiplier:</b> {multiplier:.2f}x\n"
    if risk:
        msg += f"<b>Risk:</b> {risk.upper()}\n"
    if rows:
        msg += f"<b>Rows:</b> {rows}\n"

    # Chicken Road specific fields
    game_type_raw = game.get('game_type', 'unknown')
    if game_type_raw == 'chicken_road':
        mode_val    = game.get('mode', '')
        steps_taken = game.get('steps_taken', 0)
        max_steps   = game.get('max_steps', 0)
        outcome     = game.get('status', 'unknown')
        if mode_val:
            msg += f"<b>Mode:</b> {mode_val.upper()}\n"
        msg += f"<b>Steps:</b> {steps_taken}/{max_steps}\n"
        msg += f"<b>Outcome:</b> {outcome.replace('_',' ').title()}\n"

    msg += (
        f"\n{result_emoji} <b>Result:</b> {result_text}\n"
        f"<b>Profit:</b> {profit_text}\n"
        f"<b>Time:</b> {timestamp}\n"
    )

    # Back button
    keyboard = [[InlineKeyboardButton("Back to History", callback_data=f"hist_page_{query.from_user.id}_0")]]

    # Add provably fair button if available
    pf_record = provably_fair_records.get(game_id)
    if pf_record:
        bot_username = await get_bot_username(context)
        keyboard[0].insert(0, InlineKeyboardButton(
            "Verify",
            url=f"https://t.me/{bot_username}?start=provablyfair_{game_id}"
        ))

    await safe_edit_message(
        query,
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /info <unique_id>")
        return

    unique_id = context.args[0]
    msg = f"{pe('search')} <b>Detailed Info for ID:</b> <code>{unique_id}</code>\n\n"

    # Check in game sessions
    if unique_id in game_sessions:
        game = game_sessions[unique_id]
        game_type = game['game_type'].replace('_', ' ').title()
        timestamp = datetime.fromisoformat(game['timestamp']).strftime('%Y-%m-%d %H:%M UTC')
        msg += (f"<b>Type:</b> Game Session\n"
                f"<b>Game:</b> {game_type}\n"
                f"<b>Bet:</b> ${game.get('bet_amount', 0):.2f}\n"
                f"<b>Status:</b> {game.get('status', 'N/A').title()}\n"
                f"<b>Date:</b> {timestamp}\n")

        if 'players' in game: # PvP
            p1_id, p2_id = game['players']
            p1_name = game['usernames'].get(p1_id, f"ID:{p1_id}")
            p2_name = game['usernames'].get(p2_id, f"ID:{p2_id}")
            score = f"{game['points'].get(p1_id, 0)} - {game['points'].get(p2_id, 0)}"
            msg += f"<b>Players:</b> {p1_name} vs {p2_name}\n<b>Score:</b> {score}\n"
        elif 'user_id' in game: # Solo or PvB
            uid = game['user_id']
            uname = user_stats.get(uid, {}).get('userinfo',{}).get('username', f'ID:{uid}')
            msg += f"<b>Player:</b> @{uname} (<code>{uid}</code>)\n"

        if game.get('win') is not None:
             msg += f"<b>Result:</b> {'Win' if game['win'] else 'Loss'}\n"
        if game.get('multiplier'):
             msg += f"<b>Multiplier:</b> {game['multiplier']}x\n"

        # Sidebet-specific details
        if game.get('game_type', '').startswith('sidebet_'):
            msg += f"<b>Match ID:</b> <code>{game.get('match_id', 'N/A')}</code>\n"
            msg += f"<b>Bettor:</b> {game.get('bettor_username', 'N/A')}\n"
            msg += f"<b>Target:</b> {game.get('target_username', 'N/A')}\n"
            msg += f"<b>Bet Type:</b> {game['game_type'].replace('sidebet_', '').upper()}\n"
            if game.get('result'):
                msg += f"<b>Outcome:</b> {game['result'].upper()}\n"
            if game.get('payout') is not None:
                msg += f"<b>Payout:</b> ${game['payout']:.2f}\n"

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    # Check in escrow deals
    deal_file = os.path.join(ESCROW_DIR, f"{unique_id}.json")
    deal = escrow_deals.get(unique_id)
    if not deal and os.path.exists(deal_file):
        with open(deal_file, 'r') as f: deal = json.load(f)

    if deal:
        seller, buyer = deal.get('seller', {}), deal.get('buyer', {})
        timestamp = datetime.fromisoformat(deal['timestamp']).strftime('%Y-%m-%d %H:%M UTC')
        msg += (f"<b>Type:</b> Escrow Deal\n"
               f"<b>Status:</b> {deal.get('status', 'N/A').upper()}\n<b>Amount:</b> ${deal.get('amount', 0):.2f} USDT\n"
               f"<b>Date:</b> {timestamp}\n\n"
               f"<b>Seller:</b>\n  - Username: @{seller.get('username', 'N/A')}\n  - ID: <code>{seller.get('id', 'N/A')}</code>\n\n"
               f"<b>Buyer:</b>\n  - Username: @{buyer.get('username', 'N/A')}\n  - ID: <code>{buyer.get('id', 'N/A')}</code>\n\n"
               f"<b>Deal Details:</b>\n<pre>{deal.get('details', 'No details provided.')}</pre>\n\n"
               f"<b>Deposit Tx Hash:</b>\n<code>{deal.get('deposit_tx_hash', 'N/A')}</code>\n\n"
               f"<b>Release Tx Hash:</b>\n<code>{deal.get('release_tx_hash', 'N/A')}</code>\n")
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    # Check in active raffles
    if unique_id in active_raffles:
        raffle = active_raffles[unique_id]
        user = update.effective_user
        end_time = datetime.fromisoformat(raffle['end_time'].replace('Z', '+00:00'))
        time_left = end_time - datetime.now(timezone.utc)
        total_tickets = sum(raffle['tickets'].values())
        participants = len(raffle['tickets'])
        user_tickets = raffle['tickets'].get(user.id, 0)
        user_wager = raffle['wager_tracker'].get(user.id, 0.0)
        time_str = (f"{time_left.days}d {time_left.seconds // 3600}h {(time_left.seconds // 60) % 60}m"
                    if time_left.total_seconds() > 0 else "Ended")
        msg += (
            f"<b>Type:</b> Raffle\n"
            f"{pe('money')} <b>Prize Pool:</b> ${raffle['prize_usd']:.2f}\n"
            f"🎫 <b>Ticket Cost:</b> ${raffle['ticket_cost']:.2f} wagered\n"
            f"👥 <b>Type:</b> {raffle['type'].title()}\n"
            f"{pe('trophy')} <b>Winners:</b> {raffle['total_winners']}\n"
            f"⏰ <b>Time Left:</b> {time_str}\n\n"
            f"{pe('chart')} <b>Statistics:</b>\n"
            f"🎫 Total Tickets: {total_tickets}\n"
            f"👥 Participants: {participants}\n\n"
            f"<b>Your Progress:</b>\n"
            f"🎫 Your Tickets: {user_tickets}\n"
            f"{pe('balance')} Your Wagered: ${user_wager:.2f}\n"
        )
        if raffle.get('type') == 'referrals':
            msg += "\n💡 Only referrals of the creator can participate"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    await update.message.reply_text(f"{pe('cross')} No game, escrow deal, or raffle found with that ID.", parse_mode=ParseMode.HTML)

@check_banned
@check_maintenance
async def clear_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_wallets, user_stats, username_to_userid, escrow_deals, game_sessions, group_settings, bot_settings, gift_codes, recovery_data
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not is_admin(user.id):
        await query.answer("Only the owner can confirm this action.", show_alert=True)
        return

    if query.data == "clear_confirm_yes":
        users_affected = 0
        for user_id in list(user_wallets.keys()):
            wallet = ensure_wallet_dict(user_id)
            if any(v > 0 for v in wallet.values()):
                user_wallets[user_id] = {coin: 0.0 for coin in wallet}
                if user_id in user_stats:
                    update_pnl(user_id)
                    save_user_data(user_id)
                users_affected += 1
        await query.edit_message_text(f"{pe('check')} Done! Reset balances to zero for {users_affected} users.")
    elif query.data == "clearall_confirm_yes":
        backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"backup_all_data_{backup_time}.json")
        try:
            state_to_backup = {
                "wallets": user_wallets, "stats": user_stats, "usernames": username_to_userid,
                "escrow_deals": escrow_deals, "game_sessions": game_sessions, "group_settings": group_settings,
                "bot_settings": bot_settings, "recovery_data": recovery_data, "gift_codes": gift_codes
            }
            with open(backup_file, "w") as f:
                json.dump(state_to_backup, f, default=str, indent=2)
        except Exception as e:
            logging.error(f"Failed to create backup before clearing data: {e}")

        old_count = len(user_stats)
        # Clear all in-memory data
        user_wallets.clear(); user_stats.clear(); username_to_userid.clear(); escrow_deals.clear(); game_sessions.clear(); group_settings.clear(); recovery_data.clear(); gift_codes.clear()
        # Reset bot settings to default
        bot_settings = {
            "daily_bonus_amount": 0.50, "maintenance_mode": False, "banned_users": [],
            "tempbanned_users": [], "house_balance": 100_000_000_000_000.0, "game_limits": {},
            "withdrawals_enabled": True
        }
        # Delete all data files
        for d in [DATA_DIR, ESCROW_DIR, GROUPS_DIR, RECOVERY_DIR, GIFT_CODE_DIR]:
            try:
                for fname in os.listdir(d):
                    if fname.endswith(".json"): os.remove(os.path.join(d, fname))
            except Exception as e: logging.error(f"Error deleting files in {d}: {e}")
        # Delete the main state file
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

        # Clear PostgreSQL data if enabled
        pg_cleared = False
        if USE_POSTGRES_FOR_ALL and pg_db is not None:
            try:
                # Clear in-memory pg_db caches
                if hasattr(pg_db, '_user_cache'): pg_db._user_cache.clear()
                if hasattr(pg_db, '_wallet_cache'): pg_db._wallet_cache.clear()
                if hasattr(pg_db, '_username_to_userid'): pg_db._username_to_userid.clear()
                if hasattr(pg_db, '_dirty_users'): pg_db._dirty_users.clear()
                # Execute direct SQL truncation
                if hasattr(pg_db, '_pool') and pg_db._pool is not None:
                    async with pg_db._pool.acquire() as conn:
                        await conn.execute("DELETE FROM users")
                        try:
                            await conn.execute("DELETE FROM gift_codes")
                        except Exception:
                            pass
                        try:
                            await conn.execute("DELETE FROM game_sessions")
                        except Exception:
                            pass
                    pg_cleared = True
                    logging.info("PostgreSQL data cleared via clearall")
                else:
                    logging.warning("clearall: pg_db._pool not available, only in-memory caches cleared")
            except Exception as e:
                logging.error(f"Failed to clear PostgreSQL data: {e}")

        pg_note = " + PostgreSQL" if pg_cleared else (" (⚠️ PG cache cleared but DB pool unavailable)" if USE_POSTGRES_FOR_ALL else "")
        await query.edit_message_text(f"{pe('check')} All user data and settings cleared! Removed data for {old_count} users.\nA backup was saved to {backup_file}{pg_note}")
    else:
        await query.edit_message_text("Operation cancelled. No changes were made.")

@check_banned
@check_maintenance
async def tip_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tip confirmation/cancellation inline buttons.

    Ownership of the menu is determined from the ``tip_id`` embedded in
    the callback_data (which always begins with the sender's user_id),
    NOT from ``context.user_data``.  The pending tip's full payload is
    looked up first in the module-level ``pending_tips`` registry (which
    survives plugin /reload and PTB context resets) and only falls back
    to ``context.user_data`` for legacy entries.  Previously the menu
    was incorrectly rejecting the rightful sender as "not for you"
    whenever the in-memory ``user_data`` dict was missing.

    Wrapped in try/except so any unexpected handler error answers the
    callback (preventing the spinning loader) and reports the cause to
    the rightful sender instead of falling through to PTB's global
    "An error occurred." catch-all.
    """
    try:
        return await _tip_confirm_impl(update, context)
    except Exception as exc:  # noqa: BLE001
        logging.exception("tip_confirm_callback failed: %s", exc)
        try:
            await update.callback_query.answer(
                f"Tip failed: {type(exc).__name__}", show_alert=True,
            )
        except Exception:
            pass


async def _tip_confirm_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending_tips_reg, _ = _ensure_pending_tips_registry()
    query = update.callback_query
    user = query.from_user
    data = query.data or ""

    # Parse action + tip_id directly from callback_data
    if data.startswith("confirm_tip_"):
        action = "confirm"
        tip_id = data[len("confirm_tip_"):]
    elif data.startswith("cancel_tip_"):
        action = "cancel"
        tip_id = data[len("cancel_tip_"):]
    else:
        try:
            await query.answer()
        except Exception:
            pass
        return

    # Ownership: the sender's user_id is the first token of tip_id
    # ("{sender_id}_{target_id}_{timestamp}").  Validate against the
    # tapping user BEFORE touching any storage so we never leak data.
    sender_id_from_tipid = None
    try:
        sender_id_from_tipid = int(tip_id.split("_", 1)[0])
    except (ValueError, IndexError):
        sender_id_from_tipid = None

    if sender_id_from_tipid is not None and sender_id_from_tipid != user.id:
        await query.answer("This menu is not for you.", show_alert=True)
        return

    # Fetch the pending tip data — try the module-level registry first.
    pending_tip = pending_tips_reg.get(tip_id)
    if pending_tip is None:
        legacy = context.user_data.get('pending_tip')
        if legacy and legacy.get('tip_id') == tip_id:
            pending_tip = legacy

    # Final ownership check from stored payload (defence in depth).
    if pending_tip is not None and pending_tip.get('sender_id') != user.id:
        await query.answer("This menu is not for you.", show_alert=True)
        return

    if pending_tip is None:
        # Either expired/cleaned up or the tip_id was malformed but the
        # sender_id check above already passed (i.e. the tapping user
        # is most likely the rightful sender).  Tell them politely
        # rather than the misleading "not for you".
        await query.answer("This tip request has expired. Please run /tip again.", show_alert=True)
        try:
            await query.edit_message_text(
                f"{pe('cross')} This tip request has expired. Please run /tip again."
            )
        except Exception:
            pass
        return

    await query.answer()

    if action == "cancel":
        pending_tips_reg.pop(tip_id, None)
        context.user_data.pop('pending_tip', None)
        await query.edit_message_text(f"{pe('cross')} Tip cancelled.")
        return

    if action == "confirm":
        tip_amount = pending_tip['tip_amount_usd']
        target_user_id = pending_tip['target_user_id']
        target_username = pending_tip['target_username']
        coin = pending_tip['coin']
        crypto_amount = pending_tip['crypto_amount']
        is_owner = pending_tip['is_owner']
        sender_currency = pending_tip.get('display_currency', get_display_currency(user.id))

        # ATOMIC balance check + deduct to prevent race conditions
        if not is_owner:
            try:
                crypto_deducted, deducted_coin = await deduct_wallet_safe(user.id, tip_amount, coin)
            except ValueError:
                await query.edit_message_text(
                    f"{pe('cross')} Insufficient balance. Tip cancelled.",
                    parse_mode=ParseMode.HTML,
                )
                pending_tips_reg.pop(tip_id, None)
                context.user_data.pop('pending_tip', None)
                return
        await ensure_user_in_wallets(target_user_id, target_username, context=context)
        # Credit the same coin to the receiver
        credit_wallet_crypto(target_user_id, crypto_amount, coin)

        update_stats_on_tip_sent(user.id, tip_amount)
        update_stats_on_tip_received(target_user_id, tip_amount)

        # Track tip for wager requirement (1x)
        if target_user_id in user_stats:
            user_stats[target_user_id]["unwagered_tips"] = user_stats[target_user_id].get("unwagered_tips", 0.0) + tip_amount

        update_pnl(user.id); update_pnl(target_user_id)
        save_user_data(user.id); save_user_data(target_user_id)

        formatted_crypto = format_crypto_amount(crypto_amount, coin)
        tipped_user_mention = f"@{target_username}" if target_username else f"user (ID: {target_user_id})"
        sender_str = format_display_amount(tip_amount, sender_currency)
        usdt_str = format_display_amount(tip_amount, "USDT")
        try:
            await query.edit_message_text(
                f"{pe('check')} Tip sent to {tipped_user_mention}!\n"
                f"{pe(CURRENCY_EMOJI_KEY.get(sender_currency, 'balance'))} "
                f"{sender_str} (~ {usdt_str} USDT)  \u2014  {formatted_crypto} {coin}",
                parse_mode=ParseMode.HTML
            )
        except Exception as edit_exc:
            logging.warning(f"tip_confirm: failed to edit confirmation message: {edit_exc}")
        try:
            # Show the receiver the tip in THEIR preferred currency.
            receiver_str = format_for_user(target_user_id, tip_amount, with_usdt_estimate=True)
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"{pe('gift')} You received a tip of <b>{receiver_str}</b> "
                    f"({formatted_crypto} {coin}) from {user.mention_html()}!"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.warning(f"Failed to send tip notification to {target_user_id}: {e}")

        pending_tips_reg.pop(tip_id, None)
        context.user_data.pop('pending_tip', None)

@check_banned
@check_maintenance
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    is_owner = is_admin(user.id)

    # Set menu owner for group protection when called as command
    if not from_callback:
        context.user_data['menu_owner_id'] = user.id

    help_text = (
        "🎲 <b>Telegram Gambling & Escrow Bot</b> 🎲\n\n"
        "<b>🤖 AI Assistant:</b>\n"
        "• <code>/ai &lt;question&gt;</code> — Ask the AI anything (default: g4f).\n"
        "• <code>/p &lt;SYMBOL&gt;</code> — Get crypto price from MEXC (e.g., /p BTC).\n"
        "• Reply to a message with <code>/ai</code> to discuss it.\n\n"
        "<b>Solo Games:</b>\n"
        "• <b>Blackjack</b>: <code>/bj amount</code>\n"
        "• <b>Coin Flip</b>: <code>/flip amount</code>\n"
        "• <b>Roulette</b>: <code>/roul amount choice</code>\n"
        "• <b>Dice Roll</b>: <code>/dr amount choice</code>\n"
        "• <b>Tower</b>: Use <code>/tr</code> or the Games menu\n"
        "• <b>Slots</b>: <code>/sl amount</code>\n"
        "• <b>Mines</b>: Use <code>/mines</code> or the Games menu\n"
        "• <b>Limbo</b>: <code>/lb amount multiplier</code> or <code>/lb</code> for instructions\n"
        "• <b>Keno</b>: <code>/keno amount</code>\n"
        "• <b>Predict</b>: <code>/predict amount up/down</code>\n"
        "💡 You can use 'all' instead of an amount to bet your entire balance!\n"
        "💡 All amounts are in your selected currency (see Settings).\n\n"
        "<b>🎮 Single Emoji Games:</b>\n"
        "• Access via Games → Emoji Games → Single Emoji Games\n"
        "• Quick instant-result games: Darts, Soccer, Basket, Bowling, Slot\n\n"
        "<b>PvP & PvB Games:</b>\n"
        "• <b>Dice, Darts, Football (Goal), Bowling</b>\n"
        "  - <b>vs Player</b>: <code>/dice @user amount MX ftY</code>\n"
        "     Example: <code>/dice @friend 5 M1 ft3</code> (Mode 1, First to 3)\n"
        "  - <b>vs Bot</b>: Use <code>/games</code> menu\n"
        "  - <b>Group Challenge</b> (Groups only): <code>/dice amount</code>\n"
        "     Example: <code>/dice 10</code> creates a challenge in the group\n"
        "     Others can accept or you can play with bot\n"
        "• Same for: <code>/darts</code>, <code>/goal</code>, <code>/bowl</code>\n\n"
        "<b>Wallet & Withdrawals:</b>\n"
        "• <code>/bal</code> or <code>/bank</code> or <code>/hb</code>\n"
        "• Use the main menu for withdrawals (set withdrawal address in Settings first)\n"
        "• <code>/tip @user amount</code> or reply to a message\n"
        "• <code>/rain amount N</code> — Rain on N users\n"
        "• <code>/stats</code>, <code>/leaderboard</code>, <code>/leaderboardrf</code>\n\n"
        "<b>🎁 Bonuses:</b>\n"
        "• <code>/daily</code> — Claim your daily bonus!\n"
        "• <code>/weekly</code> — Weekly VIP bonus (Sat 6PM UTC, 48h window, based on wagers &amp; losses).\n"
        "• <code>/monthly</code> — Monthly VIP bonus (15th, 48h window, based on wagers &amp; losses).\n"
        "• <code>/rk</code> — Claim accumulated rakeback (auto-earned per bet based on VIP tier).\n"
        "• <code>/claim &lt;code&gt;</code> — Claim a gift code.\n\n"
        "<b>🛡️ History & Info:</b>\n"
        "• <code>/escrow</code>, <code>/deals</code>, <code>/matches</code>\n"
        "• <code>/active</code> — View your active games\n"
        "• <code>/info &lt;id&gt;</code> — Get details of any game/deal\n"
        "• <code>/continue &lt;id&gt;</code> — Resume an active game\n\n"
        "<b>⚙️ Settings & Account:</b>\n"
        "• <code>/referral</code>, <code>/achievements</code>, <code>/level</code>\n"
        "• <code>/language</code> — Change bot language (en/es/fr/ru/hi/zh)\n"
        "• Use Settings menu to:\n"
        "  - Set your withdrawal address (USDT-BEP20)\n"
        "  - Change your display currency\n"
        "  - Set up account recovery\n"
        "• <code>/recover</code> — Start the account recovery process\n\n"
        "<b>Group Management:</b>\n"
        "• Reply with <code>/kick</code>, <code>/mute</code>, <code>/promote</code>, <code>/pin</code>, <code>/purge</code>, <code>/report</code>, <code>/translate</code>\n"
        "• <code>/lockall</code>, <code>/unlockall</code>\n"
        "• <code>/settings</code> — Configure the bot for your group (group admins only)\n\n"
        "<b>Minimum bet: ${:.2f}</b>\nContact @jashanxjagy for support.".format(MIN_BALANCE)
    )

    owner_help = (
        "\n\n👑 <b>Owner Commands:</b>\n"
        "• <code>/admin</code> — Open the admin dashboard.\n"
        "• <code>/setbal @user amount</code> — Manually set a user's balance.\n"
        "• <code>/user @username</code> — Get detailed user info.\n"
        "• <code>/users</code> — View all user stats (paginated)\n"
        "• <code>/activeall</code> — View all active games on the bot (paginated).\n"
        "• <code>/reset @username</code> — Reset a user's recovery token.\n"
        "• <code>/cancel &lt;id&gt;</code> — Cancel a match or deal\n"
        "• <code>/cancelall</code> — Cancel all active matches\n"
        "• <code>/stop</code> & <code>/resume</code> — Pause/resume new games\n"
        "• <code>/clear</code> — Reset all user balances to 0\n"
        "• <code>/clearall</code> — ⚠️ Erase all user data\n"
        "• <code>/he</code> (all escrow), <code>/hc</code> (all games) — History cmds\n"
        "• <code>/export</code> — Export all user data as a JSON file.\n"
        "• Approve/Cancel withdrawals via inline buttons in withdrawal notifications."
    )

    if is_owner:
        help_text += owner_help

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Back to More", callback_data="main_more")]]) if from_callback else None

    if from_callback:
        await safe_edit_message(update.callback_query, help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
    else:
        # Use helper bot in groups for info commands
        is_group = update.effective_chat.type in ["group", "supergroup"]
        if is_group and helper_bot:
            try:
                sent_message = await helper_bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=help_text, parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup, disable_web_page_preview=True
                )
            except Exception as e:
                logging.warning(f"Helper bot failed for /help: {e}")
                sent_message = await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
        else:
            sent_message = await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
        # Set ownership when sending with keyboard
        if reply_markup:
            set_menu_owner(sent_message, user.id)

@check_banned
@check_maintenance
async def match_invite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    match_id = data.split("_", 1)[1]
    match_data = game_sessions.get(match_id)
    if not match_data:
        await query.edit_message_text("Match not found or already cancelled.")
        return

    opponent_id = match_data["players"][1]
    if user_id != opponent_id:
        await query.answer("Only the challenged opponent can accept/decline this match.", show_alert=True)
        return
    if match_data.get("status") != "pending":
        await query.edit_message_text("This match has already been actioned.")
        return

    if data.startswith("accept_"):
        await ensure_user_in_wallets(user_id, query.from_user.username, context=context)
        # ATOMIC balance check + deduct to prevent race conditions
        try:
            crypto_deducted, coin = await deduct_wallet_safe(opponent_id, match_data["bet_amount"])
        except ValueError:
            await query.edit_message_text(
                "❌ You don't have enough balance for this bet.",
            )
            match_data["status"] = "cancelled"
            return

        # Also deduct host's bet atomically
        try:
            host_deducted, host_coin = await deduct_wallet_safe(match_data["host_id"], match_data["bet_amount"])
        except ValueError:
            # Refund opponent
            credit_wallet_safe(opponent_id, match_data["bet_amount"])
            match_data["status"] = "cancelled"
            await query.edit_message_text("Host has insufficient balance. Match cancelled.")
            return
        save_user_data(match_data["host_id"]); save_user_data(opponent_id)
        match_data.update({"status": "active"})

        # Ensure all required fields are initialized for PvP games
        if "points" not in match_data:
            match_data["points"] = {match_data["host_id"]: 0, opponent_id: 0}
        if "player_rolls" not in match_data:
            match_data["player_rolls"] = {match_data["host_id"]: [], opponent_id: []}
        if "last_roller" not in match_data:
            match_data["last_roller"] = None

        # Ensure usernames are properly set for both players
        if "usernames" not in match_data:
            match_data["usernames"] = {}
        # Update/ensure both player usernames are present
        host_username = normalize_username(user_stats.get(match_data["host_id"], {}).get('userinfo', {}).get('username', '')) or f"ID{match_data['host_id']}"
        opp_username = normalize_username(query.from_user.username) or normalize_username(user_stats.get(opponent_id, {}).get('userinfo', {}).get('username', '')) or f"ID{opponent_id}"
        match_data["usernames"][match_data["host_id"]] = host_username
        match_data["usernames"][opponent_id] = opp_username

        await ensure_user_in_wallets(match_data["host_id"], context=context)
        await ensure_user_in_wallets(opponent_id, context=context)
        if 'game_sessions' not in user_stats[match_data["host_id"]]: user_stats[match_data["host_id"]]['game_sessions'] = []
        if 'game_sessions' not in user_stats[opponent_id]: user_stats[opponent_id]['game_sessions'] = []
        user_stats[match_data["host_id"]]['game_sessions'].append(match_id)
        user_stats[opponent_id]['game_sessions'].append(match_id)
        save_user_data(match_data["host_id"]); save_user_data(opponent_id)

        await query.edit_message_text(
            f"Match Accepted! Game starts now.\n<b>Match ID:</b> {match_id}", parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=match_data["chat_id"],
            text=f"{pe('game')} <b>{match_data['game_type'].replace('pvp_','').capitalize()} Match {match_id} Started!</b>\n"
                 f"{match_data['usernames'][match_data['host_id']]} vs {match_data['usernames'][match_data['players'][1]]}\n"
                 f"First to {match_data['target_points']} points wins ${match_data['bet_amount']*2:.2f}!\n"
                 f"{match_data['usernames'][match_data['host_id']]}, it's your turn.",
            parse_mode=ParseMode.HTML
        )
    else: # Decline
        match_data.update({"status": "declined"})
        await query.edit_message_text("Match declined. The match is cancelled.")

@check_banned
@check_maintenance
async def continue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /continue <game_id>")
        return

    game_id = context.args[0]
    game = game_sessions.get(game_id)

    if not game or game.get('status') != 'active' or game.get('user_id') != user.id:
        await update.message.reply_text("Could not find an active game with that ID belonging to you.")
        return

    game_type = game['game_type']

    # Fake an update/query object to pass to the callback handlers
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.message = message
        async def answer(self, *args, **kwargs): pass
        async def edit_message_text(self, *args, **kwargs):
            await self.message.reply_text(*args, **kwargs)

    fake_update = type('FakeUpdate', (), {'callback_query': FakeQuery(user, update.message)})()

    if game_type == 'mines':
        text = f"{pe('bomb')} Resuming Mines Game (ID: <code>{game_id}</code>)..."
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=mines_keyboard(game_id))
    elif game_type == 'tower':
        text = f"{pe('tower')} Resuming Tower Game (ID: <code>{game_id}</code>)..."
        keyboard = build_tower_keyboard(game)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    elif game_type == 'coin_flip':
        text = f"{pe('coin')} Resuming Coin Flip (ID: <code>{game_id}</code>)..."
        multiplier = 2 ** game["streak"]
        win_amount = game["bet_amount"] * multiplier
        keyboard = [
            [apply_button_style(InlineKeyboardButton("Heads", callback_data=f"flip_pick_{game_id}_Heads"), 'primary'),
             apply_button_style(InlineKeyboardButton("Tails", callback_data=f"flip_pick_{game_id}_Tails"), 'primary')],
        ]
        if game['streak'] > 0:
            keyboard.append([apply_button_style(InlineKeyboardButton(f"Cash Out (${win_amount:.2f})", callback_data=f"flip_cashout_{game_id}"), 'success')])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=create_styled_keyboard(keyboard))
    # FIX: Add blackjack continuation
    elif game_type == 'blackjack':
        # Check if this is a split game
        if game.get('split'):
            # Split game - show both hands with active hand highlighted
            from PIL import Image
            split_hands = game['split_hands']
            split_bets = game['split_bets']
            current_hand_index = game.get('current_hand_index', 0)
            
            # Check if current hand is still active (not busted/standing)
            split_results = game.get('split_results', [])
            current_hand_result = None
            for r in split_results:
                if r['hand'] == current_hand_index:
                    current_hand_result = r
                    break
            
            if current_hand_result:
                # Current hand already resolved, move to next
                await update.message.reply_text(
                    f"{pe('cards')} Resuming Blackjack Split (ID: <code>{game_id}</code>)...\n"
                    f"Hand {current_hand_index + 1} already resolved. Moving to next hand.",
                    parse_mode=ParseMode.HTML
                )
                # Trigger the next hand logic
                class FakeQuery:
                    def __init__(self, user, message):
                        self.from_user = user
                        self.message = message
                        self.data = f"bj_split_stand_{game_id}_{current_hand_index}"
                    async def answer(self, *args, **kwargs): pass
                    async def edit_message_media(self, *args, **kwargs):
                        await self.message.reply_photo(*args, **kwargs)
                
                fake_query = FakeQuery(user, update.message)
                await _play_next_split_hand(fake_query, context, game_id, current_hand_index + 1, context.bot.username or "Casino")
                return
            
            # Show split game with current active hand
            current_hand = split_hands[current_hand_index]
            current_bet = split_bets[current_hand_index]
            hand_value = calculate_hand_value(current_hand)
            
            bj_image = await async_generate_bj_image(
                player_hand=current_hand,
                dealer_hand=game['dealer_hand'],
                show_dealer_hole=False,
                player_value=hand_value,
                player_username=user.username,
                bet_amount=sum(split_bets),
                bot_username=context.bot.username or "Casino",
                player_profile_pic=await _get_cached_profile_picture(context, user.id),
                split_hands=split_hands,
                split_active_hand=current_hand_index,
                split_bets=split_bets,
                split_results=split_results,
            )
            
            keyboard_buttons = [
                [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_split_hit_{game_id}_{current_hand_index}"), 'success', peb('hit')),
                 apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_split_stand_{game_id}_{current_hand_index}"), 'danger', peb('stand'))]
            ]
            if len(current_hand) == 2 and get_active_balance_usd(user.id) >= current_bet:
                keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Double", callback_data=f"bj_split_double_{game_id}_{current_hand_index}"), 'primary', peb('double'))])
            
            caption = (
                f"{pe('cards')} <b>Blackjack - Split</b> — ID: <code>{game_id}</code>\n"
                f"{pe('money')} Bet per hand: ${current_bet:.2f}\n"
                f"Playing Hand {current_hand_index + 1} of {len(split_hands)}"
            )
            await update.message.reply_photo(
                photo=bj_image,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
            )
        else:
            # Regular (non-split) blackjack game
            text = f"{pe('cards')} Resuming Blackjack (ID: <code>{game_id}</code>)..."
            player_value = calculate_hand_value(game['player_hand'])
            dealer_show_card = game['dealer_hand'][0]
            hand_text = format_hand("Your hand", game['player_hand'], player_value)
            dealer_text = f"Dealer shows: {dealer_show_card}\n"
            
            bj_image = await async_generate_bj_image(
                player_hand=game['player_hand'],
                dealer_hand=game['dealer_hand'],
                show_dealer_hole=False,
                player_value=player_value,
                player_username=user.username,
                bet_amount=game['bet_amount'],
                bot_username=context.bot.username or "Casino",
                player_profile_pic=await _get_cached_profile_picture(context, user.id),
            )
            
            keyboard = [
                [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_hit_{game_id}"), 'success', peb('hit')),
                 apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_stand_{game_id}"), 'danger', peb('stand'))],
            ]
            # Add Double Down button if eligible
            if len(game['player_hand']) == 2 and get_active_balance_usd(user.id) >= game['bet_amount']:
                keyboard.append([apply_button_style(InlineKeyboardButton("Double Down", callback_data=f"bj_double_{game_id}"), 'primary', peb('double'))])
            # Add Split button if eligible
            if can_split_hand(game['player_hand']) and get_active_balance_usd(user.id) >= game['bet_amount']:
                keyboard.append([apply_button_style(InlineKeyboardButton("Split", callback_data=f"bj_split_{game_id}"), 'primary', peb('deal'))])
            
            await update.message.reply_photo(
                photo=bj_image,
                caption=f"{text}\n\n{hand_text}\n{dealer_text}\n{pe('money')} Bet: ${game['bet_amount']:.2f}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    # FIX: Add highlow continuation
    elif game_type == 'highlow':
        text = f"{pe('darts')} Resuming High/Low Game (ID: <code>{game_id}</code>)..."
        current_card = game['current_card']
        deck = game['deck']
        streak = game.get('streak', 0)
        current_multiplier = game.get('current_multiplier', 1.0)

        card_name = get_card_name(current_card)

        # Calculate multipliers for each choice
        high_mult = calculate_highlow_multiplier(current_card, deck, "high")
        low_mult = calculate_highlow_multiplier(current_card, deck, "low")
        tie_mult = calculate_highlow_multiplier(current_card, deck, "tie")

        # Build keyboard - row 1: Higher/Lower, row 2: Tie, row 3: Skip/Cashout
        row1 = []

        # Add Higher button only if not King (13)
        if current_card != 13:
            row1.append(apply_button_style(InlineKeyboardButton(f"Higher ({high_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_high"), 'primary'))

        # Add Lower button only if not Ace (1)
        if current_card != 1:
            row1.append(apply_button_style(InlineKeyboardButton(f"Lower ({low_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_low"), 'success'))

        # Row 2: Tie button
        row2 = [apply_button_style(InlineKeyboardButton(f"Tie ({tie_mult:.2f}x)", callback_data=f"hl_pick_{game_id}_tie"), 'primary')]

        # Row 3: Skip Card and Cashout buttons (if streak > 0)
        row3 = [apply_button_style(InlineKeyboardButton("Skip Card", callback_data=f"hl_skip_{game_id}"), 'primary')]
        if streak > 0:
            cashout_amount = game['bet_amount'] * current_multiplier
            row3.append(apply_button_style(InlineKeyboardButton("Cash Out (${cashout_amount:.2f})", callback_data=f"hl_cashout_{game_id}"), 'success'))

        keyboard = [row1, row2, row3]

        # Build multiplier text
        mult_text = ""
        if current_card != 13:
            mult_text += f"{pe('up')} Higher: {high_mult:.2f}x\n"
        if current_card != 1:
            mult_text += f"{pe('down')} Lower: {low_mult:.2f}x\n"
        mult_text += f"{pe('refresh')} Tie: {tie_mult:.2f}x"

        msg = (
            f"{text}\n\n"
            f"{pe('cards')} <b>Current Card:</b> {card_name}\n"
            f"{pe('money')} <b>Bet:</b> ${game['bet_amount']:.2f}\n"
            f"{pe('fire')} <b>Streak:</b> {streak}\n"
            f"{pe('chart')} <b>Current Multiplier:</b> {current_multiplier:.2f}x\n\n"
            f"<b>Multipliers:</b>\n{mult_text}"
        )

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=create_styled_keyboard(keyboard))
    else:
        await update.message.reply_text("This game type cannot be continued.")

async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("This is an owner-only command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args:
        await update.message.reply_text("Usage: /user @username")
        return

    target_username = normalize_username(context.args[0])
    target_user_id = username_to_userid.get(target_username)

    if not target_user_id:
        try:
            chat = await context.bot.get_chat(target_username)
            target_user_id = chat.id
            await ensure_user_in_wallets(target_user_id, chat.username, context=context)
        except Exception:
            await update.message.reply_text(f"Could not find user {target_username}.")
            return

    if target_user_id not in user_stats:
        await update.message.reply_text(f"User {target_username} has not interacted with the bot yet.")
        return

    stats = user_stats[target_user_id]
    userinfo = stats.get('userinfo', {})
    join_date_str = userinfo.get('join_date', 'Not available')
    try:
        join_date = datetime.fromisoformat(join_date_str.split('.')[0]).strftime('%Y-%m-%d %H:%M')
    except:
        join_date = join_date_str

    total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
    total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))

    # NEW: Get user level
    level_data = get_user_level(target_user_id)

    text = (
        f"👤 <b>User Info for @{userinfo.get('username','')}</b> (ID: <code>{target_user_id}</code>)\n"
        f"🗓️ Joined: {join_date} UTC\n"
        f"🦄 Level: {level_data['level']} ({level_data['name']})\n" # ADDED
        f"{pe('money')} Balance: ${get_total_balance_usd(target_user_id):.2f}\n"
        f"{pe('stats')} PnL: ${stats.get('pnl', 0.0):.2f}\n"
        f"{pe('dice')} Total Bets: {stats.get('bets', {}).get('count', 0)} (W: {stats.get('bets', {}).get('wins', 0)}, L: {stats.get('bets', {}).get('losses', 0)})\n"
        f"{pe('withdraw')} Total Wagered: ${stats.get('bets', {}).get('amount', 0.0):.2f}\n"
        f"{pe('balance')} Deposits: {len(stats.get('deposits',[]))} (${total_deposits:.2f})\n"
        f"🏧 Withdrawals: {len(stats.get('withdrawals',[]))} (${total_withdrawals:.2f})\n"
        f"{pe('gift')} Tips Received: {stats.get('tips_received', {}).get('count', 0)} (${stats.get('tips_received', {}).get('amount', 0.0):.2f})\n"
        f"{pe('gift')} Tips Sent: {stats.get('tips_sent', {}).get('count', 0)} (${stats.get('tips_sent', {}).get('amount', 0.0):.2f})\n"
        f"🌧️ Rain Received: {stats.get('rain_received', {}).get('count', 0)} (${stats.get('rain_received', {}).get('amount', 0.0):.2f})\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@check_banned
@check_maintenance
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    if not context.args:
        await update.message.reply_text("Usage: /p <SYMBOL>\nExample: /p BTC")
        return

    symbol = context.args[0].upper()
    pair = f"{symbol}USDT"

    # Use the 24hr ticker endpoint for more details
    url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={pair}"

    is_group = update.effective_chat.type in ["group", "supergroup"]

    # Use helper bot for status message in groups
    if is_group and helper_bot:
        try:
            status_msg = await helper_bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"{pe('stats')} Fetching 24hr data for {pair} from MEXC..."
            )
        except Exception as e:
            logging.warning(f"Helper bot failed for /p status: {e}")
            status_msg = await update.message.reply_text(f"{pe('stats')} Fetching 24hr data for {pair} from MEXC...")
    else:
        status_msg = await update.message.reply_text(f"{pe('stats')} Fetching 24hr data for {pair} from MEXC...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        price = float(data['lastPrice'])
        price_change_percent = float(data['priceChangePercent']) * 100
        high_price = float(data['highPrice'])
        low_price = float(data['lowPrice'])
        volume = float(data['volume'])

        direction_emoji = "🔼" if price_change_percent >= 0 else "🔽"

        text = (
            f"{pe('stats')} <b>{data['symbol']}</b> Price: <code>${price:,.8f}</code>\n\n"
            f"{direction_emoji} <b>24h Change:</b> {price_change_percent:+.2f}%\n"
            f"{pe('up')} <b>24h High:</b> ${high_price:,.8f}\n"
            f"{pe('down')} <b>24h Low:</b> ${low_price:,.8f}\n"
            f"{pe('chart')} <b>24h Volume:</b> {volume:,.2f} {symbol}"
        )

        keyboard = [[InlineKeyboardButton("Update", callback_data=f"price_update_{pair}")]]

        # Edit using appropriate bot
        if is_group and helper_bot:
            try:
                await helper_bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg.message_id,
                    text=text, parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logging.warning(f"Helper bot failed to edit /p result: {e}")
                await status_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await status_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    except httpx.HTTPStatusError as e:
        logging.error(f"MEXC API Error for /p command: {e.response.status_code} - {e.response.text}")
        try:
            error_data = e.response.json()
            error_msg = error_data.get('msg', 'Unknown MEXC error')
            if "Invalid symbol" in error_msg:
                 await status_msg.edit_text(f"{pe('cross')} Invalid symbol: `{pair}`. Please check the ticker on MEXC.")
            else:
                 await status_msg.edit_text(f"An API error occurred: {error_msg}")
        except json.JSONDecodeError:
            await status_msg.edit_text(f"An unexpected API error occurred while fetching the price for {pair}.")
    except Exception as e:
        logging.error(f"Error in /p command: {e}")
        await status_msg.edit_text(f"An error occurred: {e}")

@check_banned
@check_maintenance
async def price_update_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Fetching latest price...")

    pair = query.data.split('_')[-1]
    symbol = pair.replace("USDT", "")
    url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={pair}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        price = float(data['lastPrice'])
        price_change_percent = float(data['priceChangePercent']) * 100
        high_price = float(data['highPrice'])
        low_price = float(data['lowPrice'])
        volume = float(data['volume'])

        direction_emoji = "🔼" if price_change_percent >= 0 else "🔽"

        text = (
            f"{pe('stats')} <b>{data['symbol']}</b> Price: <code>${price:,.8f}</code>\n\n"
            f"{direction_emoji} <b>24h Change:</b> {price_change_percent:+.2f}%\n"
            f"{pe('up')} <b>24h High:</b> ${high_price:,.8f}\n"
            f"{pe('down')} <b>24h Low:</b> ${low_price:,.8f}\n"
            f"{pe('chart')} <b>24h Volume:</b> {volume:,.2f} {symbol}"
        )

        keyboard = [[InlineKeyboardButton("Update", callback_data=f"price_update_{pair}")]]

        # Check if message content is different before editing to avoid errors
        if query.message.text != text:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.answer("Price is already up to date.")

    except Exception as e:
        logging.error(f"Error in price_update_callback: {e}")
        await query.answer(f"Failed to update price: {e}", show_alert=True)

@check_banned
@check_maintenance
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Check if daily bonus is enabled
    if not bot_settings.get("daily_bonus_enabled", True):
        text = f"{pe('cross')} Daily bonus is currently unavailable. Please contact the admin for more information."
        if from_callback:
            await update.callback_query.answer(text, show_alert=True)
        else:
            await update.message.reply_text(text)
        return

    stats = user_stats[user.id]
    lang = stats.get("userinfo", {}).get("language", DEFAULT_LANG)
    last_claim_str = stats.get("last_daily_claim")

    if last_claim_str:
        last_claim_time = datetime.fromisoformat(last_claim_str)
        time_since_claim = datetime.now(timezone.utc) - last_claim_time
        if time_since_claim < timedelta(hours=24):
            time_left = timedelta(hours=24) - time_since_claim
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            text = get_text("daily_claim_wait", lang, hours=hours, minutes=minutes)
            if from_callback:
                await update.callback_query.answer(text, show_alert=True)
            else:
                await update.message.reply_text(text)
            return

    bonus_amount = bot_settings.get("daily_bonus_amount", 0.50)
    credit_wallet(user.id, bonus_amount)
    stats["last_daily_claim"] = str(datetime.now(timezone.utc))
    save_user_data(user.id)

    # Show the bonus amount in the user's display currency.
    bonus_display = format_for_user(user.id, bonus_amount)
    try:
        text = get_text("daily_claim_success", lang, amount=bonus_display)
    except Exception:
        text = f"{pe('gift')} Daily bonus claimed: {bonus_display}!"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Back to Bonuses", callback_data="main_bonuses")]]) if from_callback else None

    if from_callback:
        await safe_edit_message(update.callback_query, text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

@check_banned
@check_maintenance
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_lang = get_user_lang(user.id)
    args = context.args

    if not args:
        keyboard = [
            [InlineKeyboardButton(LANGUAGE_NAMES["en"], callback_data="lang_en")],
            [InlineKeyboardButton(LANGUAGE_NAMES["es"], callback_data="lang_es")],
            [InlineKeyboardButton(LANGUAGE_NAMES["fr"], callback_data="lang_fr")],
            [InlineKeyboardButton(LANGUAGE_NAMES["ru"], callback_data="lang_ru")],
            [InlineKeyboardButton(LANGUAGE_NAMES["hi"], callback_data="lang_hi")],
            [InlineKeyboardButton(LANGUAGE_NAMES["zh"], callback_data="lang_zh")]
        ]
        await update.message.reply_text(
            get_text("select_language", user_lang),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    lang_code = args[0].lower()
    if lang_code in LANGUAGE_FILES:
        user_stats[user.id]["userinfo"]["language"] = lang_code
        save_user_data(user.id)
        await update.message.reply_text(get_text("language_set", lang_code))
    else:
        await update.message.reply_text(get_text("error_occurred", user_lang))

@check_banned
@check_maintenance
async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Check menu ownership BEFORE answering
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    user = query.from_user
    lang_code = query.data.split('_')[1]
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if lang_code in LANGUAGE_FILES:
        user_stats[user.id]["userinfo"]["language"] = lang_code
        save_user_data(user.id)
        language_name = LANGUAGE_NAMES.get(lang_code, lang_code)
        await query.answer(get_text("language_set", lang_code), show_alert=True)
        # Go back to settings menu
        await settings_command(update, context)
    else:
        user_lang = get_user_lang(user.id)
        await query.answer(get_text("error_occurred", user_lang), show_alert=True)

def _build_currency_menu(user_id):
    """Build the (text, keyboard) pair for the /currency menu.

    Reused by both the command handler and the callback handler so
    selecting a currency can edit the same message in place — the
    selected option visually flips from blue (primary) to green
    (success) without spawning a new menu."""
    current_currency = get_active_currency(user_id)
    current_display = get_display_currency(user_id)
    keyboard = []

    # --- Active wallet crypto ---
    keyboard.append([InlineKeyboardButton(
        f"\U0001F4B0 Wallet currency (what you hold)",
        callback_data="noop_cur_header_wallet",
    )])
    for curr in SUPPORTED_CRYPTOS:
        bal = ensure_wallet_dict(user_id).get(curr, 0.0)
        price = LIVE_PRICES.get(curr, 1.0)
        usd_val = bal * price if curr != 'USDT' else bal

        text = f"{curr}"
        if curr == current_currency:
            text += " \u2713"
        text += f"  (${usd_val:,.2f})"

        keyboard.append([apply_button_style(
            InlineKeyboardButton(text, callback_data=f"setcurrency_{curr}"),
            'success' if curr == current_currency else 'primary',
            None,
        )])

    # --- Display currency (fiat only: INR / USD / EUR / GBP) ---
    keyboard.append([InlineKeyboardButton(
        f"\U0001F310 Display currency (what you see)",
        callback_data="noop_cur_header_display",
    )])
    for curr in SUPPORTED_DISPLAY_CURRENCIES:
        sym = CURRENCY_SYMBOLS.get(curr, "")
        label = f"{sym} {curr}" if sym else curr
        if curr == current_display:
            label += " \u2713"
        keyboard.append([apply_button_style(
            InlineKeyboardButton(label, callback_data=f"setdisplay_{curr}"),
            # Selected display currency flips from primary (blue) to
            # success (green) the moment the user taps it.
            'success' if curr == current_display else 'primary',
            None,
        )])

    keyboard.append([apply_button_style(
        InlineKeyboardButton("Close", callback_data="close"),
        'danger', None
    )])

    current_symbol = CRYPTO_SYMBOLS.get(current_currency, "\U0001F4B0")
    disp_symbol = CURRENCY_SYMBOLS.get(current_display, "")
    text = (
        f"\U0001F4B0 <b>Select Currency</b>\n\n"
        f"Wallet: {current_symbol} <b>{current_currency}</b>\n"
        f"Display: {disp_symbol} <b>{current_display}</b>\n\n"
        f"\u2022 <b>Wallet</b> is which crypto your balance actually sits in.\n"
        f"\u2022 <b>Display</b> is the unit every balance / bet / stat is shown in.\n"
        f"   Picking INR means <code>/bj 500</code> bets \u20B9500 (not $500).\n\n"
        f"\u26A0\uFE0F <i>Your wallet balance in each coin is segregated.</i>"
    )
    return text, create_styled_keyboard(keyboard)


@check_banned
@check_maintenance
async def currency_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """``/currency`` - select both the active wallet coin AND the
    display currency (the unit you see / type bets in).

    Display currency is restricted to one of the four supported
    fiats (INR / USD / EUR / GBP).  Wallet currency stays whichever
    crypto you deposited in.
    """
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    text, reply_markup = _build_currency_menu(user.id)
    sent = await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )
    set_menu_owner(sent, user.id)

@check_banned
@check_maintenance
async def currency_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle currency selection callbacks.

    ``setcurrency_<coin>``  -> active wallet crypto
    ``setdisplay_<code>``   -> display currency (fiat or crypto)
    ``noop_cur_header_*``   -> header rows (ignore, keep menu open)
    """
    query = update.callback_query

    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return

    await query.answer()

    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    data = query.data or ""

    if data.startswith("noop_cur_header"):
        return

    if data.startswith("setdisplay_"):
        code = data.split("_", 1)[1].upper()
        if set_display_currency(user.id, code):
            sym = CURRENCY_SYMBOLS.get(code, "")
            await query.answer(f"Display currency set to {sym} {code}")
            # Edit the same message so the selected option visually
            # flips from blue (primary) to green (success) right away.
            try:
                text, reply_markup = _build_currency_menu(user.id)
                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            except Exception:
                pass
        else:
            await query.answer("Invalid display currency.", show_alert=True)
        return

    if data.startswith("setcurrency_"):
        currency_code = data.split("_", 1)[1].upper()
        if currency_code in SUPPORTED_CRYPTOS:
            user_stats[user.id]["active_currency"] = currency_code
            save_user_data(user.id)
            symbol = CRYPTO_SYMBOLS.get(currency_code, "💎")
            await query.answer(f"Active currency set to {symbol} {currency_code}")
            try:
                text, reply_markup = _build_currency_menu(user.id)
                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            except Exception:
                pass
        else:
            await query.answer("Invalid currency code.", show_alert=True)
        return

    await query.answer("Unknown action.", show_alert=True)

@check_banned
@check_maintenance
async def surprisedrop_toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /surprisedrop on or /surprisedrop off."""
    user = update.effective_user
    if not is_admin(user.id):
        return

    global surprise_drops_enabled
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await update.message.reply_text(
            f"Usage: <code>/surprisedrop on</code> or <code>/surprisedrop off</code>\n"
            f"Current status: {'ON' if surprise_drops_enabled else 'OFF'}",
            parse_mode=ParseMode.HTML
        )
        return

    if args[0].lower() == "on":
        surprise_drops_enabled = True
        await update.message.reply_text(f"{pe('check')} Surprise code drops are now <b>ENABLED</b>.", parse_mode=ParseMode.HTML)
    else:
        surprise_drops_enabled = False
        await update.message.reply_text(f"{pe('cross')} Surprise code drops are now <b>DISABLED</b>.", parse_mode=ParseMode.HTML)

@check_banned
@check_maintenance
async def surprisedrop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /surprisedrop_now [amount] [wager_req] - Drop a surprise code immediately."""
    user = update.effective_user
    if not is_admin(user.id):
        return

    if not surprise_drops_enabled:
        await update.message.reply_text(f"{pe('cross')} Surprise drops are currently disabled.")
        return

    args = context.args
    # Optional: /surprisedrop_now amount wager_req
    if args and len(args) >= 1:
        try:
            amount = float(args[0])
        except ValueError:
            amount = round(random.uniform(0.5, 3), 2)
    else:
        amount = round(random.uniform(0.5, 3), 2)

    if args and len(args) >= 2:
        try:
            wager_req = float(args[1])
        except ValueError:
            wager_req = round(random.uniform(10, 200), 2)
    else:
        wager_req = round(random.uniform(10, 200), 2)

    code = generate_surprise_code()
    bot_username = await get_bot_username(context)

    surprise_drops[code] = {
        "code": code,
        "amount": amount,
        "wager_requirement": wager_req,
        "claimed_by": None,
        "claimed_by_username": None,
        "timestamp": str(datetime.now(timezone.utc)),
        "chat_id": SURPRISE_DROP_GROUP,
        "message_id": None,
        "status": "active",
    }

    img_buf = generate_surprise_drop_image(code, amount, wager_req, bot_username)

    # Always drop in the designated group, not the admin's current chat
    sent_msg = await context.bot.send_photo(
        chat_id=SURPRISE_DROP_GROUP,
        photo=img_buf,
        caption=(
            f"\U0001f381 <b>SURPRISE CODE DROP!</b> \U0001f381\n\n"
            f"A surprise bonus of <b>${amount:.2f}</b> has been dropped!\n"
            f"Type <code>/claim {code}</code> to claim it!\n\n"
            f"\u26a0\ufe0f <b>Requirements:</b>\n"
            f"- Must have wagered at least <b>${wager_req:.2f}</b> in the last 30 days\n"
            f"- Only <b>ONE</b> user can claim per code\n"
            f"- Amount has <b>2x</b> wager requirement before withdrawal"
        ),
        parse_mode=ParseMode.HTML,
    )

    surprise_drops[code]["chat_id"] = sent_msg.chat_id
    surprise_drops[code]["message_id"] = sent_msg.message_id

    # Notify admin only if the command was run outside the drop group
    if update.effective_chat.id != sent_msg.chat_id:
        await update.message.reply_text(
            f"{pe('check')} Surprise code <code>{code}</code> dropped in {SURPRISE_DROP_GROUP}!",
            parse_mode=ParseMode.HTML,
        )

    # Pin the message
    try:
        await context.bot.pin_chat_message(
            chat_id=sent_msg.chat_id,
            message_id=sent_msg.message_id,
            disable_notification=False
        )
    except Exception as e:
        logging.warning(f"Could not pin surprise drop message: {e}")

@check_banned
@check_maintenance
async def games_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent game results (admin only, paginated)."""
    user = update.effective_user
    if not is_admin(user.id):
        return

    await ensure_user_in_wallets(user.id, user.username, context=context)
    await _show_games_history_page(update, context, page=0)

async def games_history_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination for /gameshistory."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("Not authorized.", show_alert=True)
        return
    await query.answer()
    page = int(query.data.replace("admin_ghist_page_", ""))
    await _show_games_history_page(update, context, page=page)

async def setbal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id): return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    args = context.args
    if len(args) < 2 or len(args) > 3:
        await update.message.reply_text("Usage: /setbal @username <amount_usd> [currency]\nExample: /setbal @user 10 ETH\n(Sets balance to $10 worth of ETH at live price)")
        return

    username = args[0]
    amount_str = args[1]
    coin = args[2].upper() if len(args) == 3 else "USDT"

    if coin not in SUPPORTED_CRYPTOS:
        await update.message.reply_text(f"{pe('cross')} Unsupported currency. Supported: {', '.join(SUPPORTED_CRYPTOS)}")
        return

    target_user_id = username_to_userid.get(normalize_username(username))

    if not target_user_id:
        await update.message.reply_text(f"User {username} not found.")
        return

    try:
        amount_usd = float(amount_str)
        price = LIVE_PRICES.get(coin, 1.0)
        crypto_amount = amount_usd / price
        wallet = ensure_wallet_dict(target_user_id)
        # SET the balance to the specified amount (not add to existing)
        wallet[coin] = crypto_amount
        update_pnl(target_user_id)
        save_user_data(target_user_id)
        formatted = format_crypto_amount(crypto_amount, coin)
        # Also update user_stats balance for consistency
        stats = user_stats.get(target_user_id, {})
        stats.setdefault('balance_usd', {})
        stats['balance_usd'][coin] = amount_usd

        await update.message.reply_text(
            f"{pe('check')} Balance set for {username}:\n"
            f"{pe('balance')} USD Value: ${amount_usd:.2f}\n"
            f"{pe('gem')} {coin}: {formatted} {coin} (@ ${price:,.2f})"
        )
    except ValueError:
        await update.message.reply_text("Invalid amount.")

async def resetleaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to reset all leaderboard data (wagered amounts, wins) while keeping balances intact."""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(f"{pe('cross')} This is an admin-only command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Count how many users will be reset
    reset_count = 0
    for uid, stats in user_stats.items():
        # Reset all-time wagered
        if stats.get('bets', {}).get('amount', 0.0) > 0:
            stats['bets']['amount'] = 0.0
            stats['bets']['count'] = 0
            stats['bets']['wins'] = 0
            stats['bets']['losses'] = 0
            stats['bets']['pvp_wins'] = 0
            stats['bets']['history'] = []
            reset_count += 1

        # Reset PnL
        stats['pnl'] = 0.0

        # Reset weekly stats
        stats['weekly_stats'] = {'weighted_wager': 0.0, 'net_loss': 0.0, 'last_claim': None}

        # Reset monthly stats
        stats['monthly_stats'] = {'weighted_wager': 0.0, 'net_loss': 0.0, 'last_claim': None}

        # Reset last_win
        stats['last_win'] = 0

        # Clear game sessions (these are used for stats display)
        stats['game_sessions'] = []

    # Clear leaderboard cache
    leaderboard_data["all_time"] = []
    leaderboard_data["weekly"] = []
    leaderboard_data["monthly"] = []
    leaderboard_data["highest_wins"] = []

    # Save all user data
    save_all_data()

    # Rebuild empty leaderboards (force-bypass cache after admin reset).
    _invalidate_leaderboard_cache()
    _rebuild_leaderboards(force=True)

    await update.message.reply_text(
        f"{pe('check')} <b>Leaderboard Reset Complete</b>\n\n"
        f"Reset {reset_count} users' wagering data.\n"
        f"All leaderboards cleared and starting fresh.\n"
        f"User balances remain unchanged."
    )

async def setdaily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("This is an admin-only command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /setdaily <amount>\nExample: /setdaily 0.50")
        return

    try:
        amount = float(context.args[0])
        if amount < 0:
            await update.message.reply_text("Amount must be positive.")
            return

        bot_settings["daily_bonus_amount"] = amount
        bot_settings["daily_bonus_enabled"] = True
        await update.message.reply_text(f"{pe('check')} Daily bonus has been set to ${amount:.2f} and enabled.")
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number.")

async def dailyoff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("This is an admin-only command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    bot_settings["daily_bonus_enabled"] = False
    await update.message.reply_text(f"{pe('check')} Daily bonus feature has been disabled. Users will not be able to claim daily bonuses until you enable it again with /dailyon.")

async def dailyon_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("This is an admin-only command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    bot_settings["daily_bonus_enabled"] = True
    bonus_amount = bot_settings.get("daily_bonus_amount", 0.50)
    await update.message.reply_text(f"{pe('check')} Daily bonus feature has been enabled. Current daily bonus amount: ${bonus_amount:.2f}")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to mute them.")
        return

    try:
        member = await chat.get_member(user.id)
        if not member.can_restrict_members and member.status != 'creator':
            await update.message.reply_text("You must be an admin with permission to mute users.")
            return

        target_user = update.message.reply_to_message.from_user
        target_member = await chat.get_member(target_user.id)
        if target_member.status in ['administrator', 'creator']:
            await update.message.reply_text("You cannot mute an administrator.")
            return

        await context.bot.restrict_chat_member(chat.id, target_user.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"Muted {target_user.mention_html()}.", parse_mode=ParseMode.HTML)
    except BadRequest as e:
        await update.message.reply_text(f"Failed to mute user: {e.message}. I might be missing permissions or the target is an admin.")
    except Exception as e:
        logging.error(f"Error in mute_command: {e}")
        await update.message.reply_text("An error occurred.")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to report it to admins.")
        return

    try:
        admins = await context.bot.get_chat_administrators(chat.id)
        report_text = f"{pe('alarm')} Report from {user.mention_html()} in {chat.title}:\n\n<a href='{update.message.reply_to_message.link}'>Reported Message</a>"
        for admin in admins:
            if not admin.user.is_bot:
                try:
                    await context.bot.send_message(admin.user.id, report_text, parse_mode=ParseMode.HTML)
                except (Forbidden, BadRequest):
                    pass
        await update.message.reply_text("Reported to admins.")
    except Exception as e:
        logging.error(f"Error in report_command: {e}")
        await update.message.reply_text("An error occurred while reporting.")

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    if not update.message.reply_to_message or not update.message.reply_to_message.text:
        await update.message.reply_text("Reply to a text message to translate it.")
        return

    text_to_translate = update.message.reply_to_message.text
    # Using g4f for translation
    try:
        translated_text = await g4f.ChatCompletion.create_async(
            model=g4f.models.default,
            messages=[{"role": "user", "content": f"Translate the following text to English: '{text_to_translate}'"}],
        )
        await update.message.reply_text(f"<b>Translation:</b>\n{translated_text}", parse_mode=ParseMode.HTML, reply_to_message_id=update.message.reply_to_message.id)
    except Exception as e:
        await update.message.reply_text(f"Translation failed: {e}")

async def lockall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)

    try:
        member = await chat.get_member(user.id)
        if not member.can_restrict_members and member.status != 'creator':
            await update.message.reply_text("You don't have permission to change group settings.")
            return

        bot_member = await chat.get_member(context.bot.id)
        if not bot_member.can_restrict_members:
            await update.message.reply_text("I don't have permission to restrict members. Please make me an admin with this right.")
            return

        await context.bot.set_chat_permissions(chat.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"{pe('lock')} Chat locked. Only admins can send messages.")
    except BadRequest as e:
        await update.message.reply_text(f"Failed to lock chat: {e.message}")
    except Exception as e:
        logging.error(f"Error in lockall_command: {e}")
        await update.message.reply_text("An error occurred.")

async def unlockall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)

    try:
        member = await chat.get_member(user.id)
        if not member.can_restrict_members and member.status != 'creator':
            await update.message.reply_text("You don't have permission to change group settings.")
            return

        bot_member = await chat.get_member(context.bot.id)
        if not bot_member.can_restrict_members:
            await update.message.reply_text("I don't have permission to change permissions. Please make me an admin with this right.")
            return

        # Restore default permissions for all members
        await context.bot.set_chat_permissions(chat.id, ChatPermissions(
            can_send_messages=True, can_send_media_messages=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True,
            can_change_info=False, can_invite_users=True, can_pin_messages=False
        ))
        await update.message.reply_text(f"{pe('lock')} Chat unlocked. All members can send messages again.")
    except BadRequest as e:
        await update.message.reply_text(f"Failed to unlock chat: {e.message}")
    except Exception as e:
        logging.error(f"Error in unlockall_command: {e}")
        await update.message.reply_text("An error occurred.")

@check_banned
@check_maintenance
async def active_games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # PERFORMANCE: per-user active-games index keeps this O(user's games).
    active_games = []
    for gid in list(_get_user_active_game_ids(user.id)):
        g = game_sessions.get(gid)
        if g and g.get("status") == "active" and g.get("user_id") == user.id:
            active_games.append(g)

    if not active_games:
        await update.message.reply_text("You have no active games. Start one from the /games menu!")
        return

    msg = "<b>Your Active Games:</b>\n\n"
    for game in active_games:
        game_type = game['game_type'].replace('_', ' ').title()
        msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"
        msg += f"<b>Bet:</b> ${game['bet_amount']:.2f}\n"
        msg += f"Use <code>/continue {game['id']}</code> to resume.\n"
        msg += "--------------------\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def active_all_games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    context.user_data['active_games_page'] = 0
    await send_active_games_page(update, context)

async def send_active_games_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = context.user_data.get('active_games_page', 0)
    page_size = 10
    active_games = [g for g in game_sessions.values() if g.get("status") == "active"]

    start_index = page * page_size
    end_index = start_index + page_size
    paginated_games = active_games[start_index:end_index]

    if update.callback_query and not paginated_games:
        await update.callback_query.answer("No more active games.", show_alert=True)
        return

    msg = f"<b>All Active Games (Page {page + 1}/{ -(-len(active_games) // page_size) }):</b>\n\n"
    if not paginated_games:
        msg = "There are no active games on the bot."

    for game in paginated_games:
        game_type = game['game_type'].replace('_', ' ').title()
        msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"
        if 'players' in game:
            p_names = [game['usernames'].get(pid, f"ID:{pid}") for pid in game['players']]
            msg += f"<b>Players:</b> {', '.join(p_names)}\n"
        else:
            uid = game['user_id']
            uname = user_stats.get(uid, {}).get('userinfo', {}).get('username', f'ID:{uid}')
            msg += f"<b>Player:</b> @{uname}\n"
        msg += f"<b>Bet:</b> ${game['bet_amount']:.2f}\n--------------------\n"

    keyboard = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(f"{pe('left')} Previous", callback_data="activeall_prev"))
    if end_index < len(active_games):
        row.append(InlineKeyboardButton(f"Next {pe('arrow_right')}", callback_data="activeall_next"))
    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

@check_banned
@check_maintenance
async def active_all_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("This is an admin-only button.", show_alert=True)
        return

    await query.answer()
    action = query.data
    page = context.user_data.get('active_games_page', 0)

    if action == "activeall_next":
        context.user_data['active_games_page'] = page + 1
    elif action == "activeall_prev":
        context.user_data['active_games_page'] = max(0, page - 1)

    await send_active_games_page(update, context)

@check_banned
@check_maintenance
async def more_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    await query.answer()

    # All items that were previously in the main menu (except Deposit, Withdraw, Games, Settings, Admin)
    all_items = []

    all_items.extend([
        ("Wallet", "main_wallet", 'primary', 'briefcase'),  # BLUE
        ("Leaderboard", "main_leaderboard", 'primary', 'stats'),  # BLUE
        ("Referral", "main_referral", 'primary', 'referral'),  # BLUE
        ("Level", "main_level", 'primary', 'level'),  # BLUE
    ])

    all_items.extend([
        ("Achievements", "main_achievements", 'primary', 'achieve'),  # BLUE
        ("Support", "main_support", 'primary', 'support'),  # BLUE
        ("Help", "main_help", 'primary', 'help'),  # BLUE
        ("Info & Rules", "main_info", 'primary', 'info'),  # BLUE
        ("Claim Gift Code", "main_claim_gift", 'primary', 'gift'),  # BLUE
        ("Stats", "main_stats", 'primary', 'chart'),  # BLUE
        ("Currency", "settings_currency", 'primary', 'diamond'),  # BLUE
    ])

    keyboard = []
    # Add all items (2 per row) with colors and premium emojis
    for i in range(0, len(all_items), 2):
        row = [apply_button_style(InlineKeyboardButton(all_items[i][0], callback_data=all_items[i][1]), all_items[i][2], peb(all_items[i][3]))]
        if i + 1 < len(all_items):
            row.append(apply_button_style(InlineKeyboardButton(all_items[i + 1][0], callback_data=all_items[i + 1][1]), all_items[i + 1][2], peb(all_items[i + 1][3])))
        keyboard.append(row)

    # Add Terms of Service button (no color for URL buttons)
    keyboard.append([InlineKeyboardButton("Terms of Service", url="https://telegra.ph/Casino-Terms-of-Service-11-17").to_dict()])

    # Back button - RED
    keyboard.append([apply_button_style(InlineKeyboardButton("Back to Main Menu", callback_data="back_to_main"), 'danger', peb('back'))])

    text = f"{pe('plus')} <b>More Options</b>\n\nSelect an option:"

    await safe_edit_message(
        query,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard)
    )

async def recover_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        await update.message.reply_text("For security, please use the /recover command in a private chat with me.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Please enter your recovery token.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_recovery")]])
    )
    return RECOVER_ASK_TOKEN

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("This is an owner-only command.")
        return

    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in my DMs for security.")
        return

    await update.message.reply_text("Exporting all user data... This may take a moment.")

    export_data = {
        "user_stats": user_stats,
        "user_wallets": user_wallets
    }

    file_path = os.path.join(DATA_DIR, "export_all_users.json")
    try:
        with open(file_path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)

        await update.message.reply_document(
            document=open(file_path, "rb"),
            caption=f"All user data as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            filename="all_user_data.json"
        )
        os.remove(file_path)
    except Exception as e:
        logging.error(f"Failed to export user data: {e}")
        await update.message.reply_text(f"An error occurred during export: {e}")

async def reset_recovery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /reset @username")
        return

    target_username = normalize_username(context.args[0])
    target_user_id = username_to_userid.get(target_username)

    if not target_user_id:
        await update.message.reply_text(f"User {target_username} not found in the bot's database.")
        return

    stats = user_stats.get(target_user_id)
    if not stats or not stats.get("recovery_token_hash"):
        await update.message.reply_text(f"User {target_username} does not have a recovery token set.")
        return

    token_hash = stats["recovery_token_hash"]

    # Remove from user_stats
    stats["recovery_token_hash"] = None
    save_user_data(target_user_id)

    # Remove from recovery_data
    if token_hash in recovery_data:
        del recovery_data[token_hash]

    # Remove file
    recovery_file = os.path.join(RECOVERY_DIR, f"{token_hash}.json")
    if os.path.exists(recovery_file):
        os.remove(recovery_file)

    await update.message.reply_text(f"Successfully reset the recovery token for {target_username}. They can now set a new one via the settings menu.")
    try:
        await context.bot.send_message(target_user_id, "Your account recovery token has been reset by the administrator. You can now set a new one in the settings menu.")
    except Exception as e:
        logging.warning(f"Could not notify user {target_user_id} about recovery reset: {e}")

@check_banned
@check_maintenance
async def seven_up_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /7up command - play 7Up7Down or show help."""
    if not is_game_enabled("7up7down"):
        await update.message.reply_text(
            f"{pe('warning')} <b>7Up7Down</b> is currently under maintenance.",
            parse_mode=ParseMode.HTML
        )
        return

    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    args = update.message.text.strip().split()

    # No args = show help image
    if len(args) < 2:
        try:
            help_img = await async_generate_7up_help_image()
            await update.message.reply_photo(
                photo=help_img,
                caption=f"{pe('7up')} <b>7 UP DOWN</b>\n\nUse <code>/7up [amount] [option]</code> to play!\n\nExamples:\n"
                        f"<code>/7up 10 high</code> - Bet $10 on high (8-12)\n"
                        f"<code>/7up 50 7</code> - Bet $50 on exact 7\n"
                        f"<code>/7up 25 1,2,3</code> - Bet $25 on specific combo\n"
                        f"<code>/7up 10 3low</code> - 3 dice, bet on low",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Error generating 7up help image: {e}")
            await update.message.reply_text(
                f"{pe('7up')} <b>7 UP DOWN</b>\n\nUse <code>/7up [amount] [option]</code> to play!",
                parse_mode=ParseMode.HTML
            )
        return

    if len(args) < 3:
        await update.message.reply_text(
            f"{pe('cross')} Usage: <code>/7up [amount] [option]</code>\n\n"
            f"Example: <code>/7up 10 high</code> or <code>/7up 50 1,2,3</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # Parse bet amount
    try:
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(args[1], user.id)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid bet amount.")
        return

    if not await check_bet_limits(update, bet_amount_usd, '7up7down'):
        return

    if get_active_balance_usd(user.id) < bet_amount_usd:
        await send_insufficient_balance_message(update)
        return

    option = args[2].lower()
    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")

    # Determine if it's a specific combo bet (contains commas)
    is_specific_combo = "," in option
    is_3dice = option in SEVEN_UP_DOWN_3DICE or option.startswith("3") or is_specific_combo

    if is_specific_combo:
        # Parse specific combo: e.g., "1,2,3" or "6,6,6"
        try:
            combo_values = [int(x.strip()) for x in option.split(",")]
            if len(combo_values) != 3 or not all(1 <= v <= 6 for v in combo_values):
                await update.message.reply_text(
                    f"{pe('cross')} Invalid combo. Use 3 numbers from 1-6 separated by commas.\n"
                    f"Example: <code>/7up 10 1,2,3</code> or <code>/7up 10 6,6,6</code>",
                    parse_mode=ParseMode.HTML
                )
                return
        except (ValueError, IndexError):
            await update.message.reply_text(f"{pe('cross')} Invalid combo format.")
            return

        # Deduct balance
        try:
            crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount_usd)
        except ValueError:
            await update.message.reply_text(f"{pe('cross')} Insufficient balance.")
            return
        save_user_data(user.id)

        # Roll 3 dice
        num_dice = 3
        command_msg_id = update.message.message_id
        chat_id = update.effective_chat.id

        await update.message.reply_text(
            f"{pe('7up')} <b>7UP DOWN - Specific Combo</b>\n\n"
            f"{pe('money')} Bet: {currency_symbol}{bet_amount_currency:.2f}\n"
            f"{pe('target')} Target: [{','.join(str(v) for v in combo_values)}]\n\n"
            f"Rolling {num_dice} dice...",
            parse_mode=ParseMode.HTML
        )

        rolls_data = await multi_roll_parallel(context, chat_id, "\U0001f3b2", num_dice, reply_to_message_id=command_msg_id)
        dice_values = [msg.dice.value for msg, _ in rolls_data]
        await asyncio.sleep(3)  # Wait for dice animation

        won, multiplier, combo_type = check_7up_specific_combo(combo_values, dice_values)

        game_id = generate_unique_id("7UP")
        if won:
            winnings = bet_amount_usd * multiplier
            credit_wallet(user.id, winnings)
            profit = winnings - bet_amount_usd
            combo_names = {"specific_triple": "Specific Triple", "pair_kicker": "Pair + Kicker", "distinct_triple": "Distinct Triple"}
            result_text = (
                f"{pe('win')} <b>JACKPOT!</b> {pe('fire')}\n\n"
                f"Dice: [{', '.join(str(v) for v in dice_values)}]\n"
                f"Target: [{','.join(str(v) for v in combo_values)}]\n"
                f"Type: {combo_names.get(combo_type, 'Combo')}\n"
                f"Multiplier: <b>{multiplier}x</b>\n"
                f"Profit: <b>+{currency_symbol}{profit:.2f}</b>"
            )
        else:
            result_text = (
                f"{pe('lose')} <b>No Match!</b>\n\n"
                f"Dice: [{', '.join(str(v) for v in dice_values)}]\n"
                f"Target: [{','.join(str(v) for v in combo_values)}]\n"
                f"Lost: <b>-{currency_symbol}{bet_amount_currency:.2f}</b>"
            )

        await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)

        # Record game
        game_sessions[game_id] = {
            "id": game_id, "game_type": "7up7down_3dice", "user_id": user.id,
            "bet_amount": bet_amount_usd, "status": "completed", "win": won,
            "option": option, "dice_values": dice_values,
            "multiplier": multiplier if won else 0,
            "timestamp": str(datetime.now(timezone.utc)),
        }
        await update_stats_on_bet(user.id, game_id, bet_amount_usd, won,
                                  multiplier=multiplier if won else 0, context=context)
        save_user_data(user.id)
        return

    # Standard option bet (2 dice or 3 dice)
    if option in SEVEN_UP_DOWN_2DICE:
        opt_data = SEVEN_UP_DOWN_2DICE[option]
        num_dice = 2
        game_subtype = "7up7down_2dice"
    elif option in SEVEN_UP_DOWN_3DICE:
        opt_data = SEVEN_UP_DOWN_3DICE[option]
        num_dice = 3
        game_subtype = "7up7down_3dice"
    else:
        # Try case-insensitive match
        found = False
        for key in SEVEN_UP_DOWN_2DICE:
            if key.lower() == option:
                opt_data = SEVEN_UP_DOWN_2DICE[key]
                option = key
                num_dice = 2
                game_subtype = "7up7down_2dice"
                found = True
                break
        if not found:
            for key in SEVEN_UP_DOWN_3DICE:
                if key.lower() == option:
                    opt_data = SEVEN_UP_DOWN_3DICE[key]
                    option = key
                    num_dice = 3
                    game_subtype = "7up7down_3dice"
                    found = True
                    break
        if not found:
            await update.message.reply_text(
                f"{pe('cross')} Invalid option '<code>{option}</code>'.\n\n"
                f"Use <code>/7up</code> to see all available options.",
                parse_mode=ParseMode.HTML
            )
            return

    multiplier = opt_data["multiplier"]
    desc = opt_data["desc"]

    # Deduct balance
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount_usd)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Insufficient balance.")
        return
    save_user_data(user.id)

    command_msg_id = update.message.message_id
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"{pe('7up')} <b>7UP DOWN</b>\n\n"
        f"{pe('money')} Bet: {currency_symbol}{bet_amount_currency:.2f}\n"
        f"{pe('target')} Option: {desc} ({multiplier}x)\n\n"
        f"Rolling {num_dice} dice...",
        parse_mode=ParseMode.HTML
    )

    rolls_data = await multi_roll_parallel(context, chat_id, "\U0001f3b2", num_dice, reply_to_message_id=command_msg_id)
    dice_values = [msg.dice.value for msg, _ in rolls_data]
    await asyncio.sleep(3)  # Wait for dice animation

    # Check win
    if num_dice == 2:
        won = check_7up_2dice_win(option, dice_values)
    else:
        won = check_7up_3dice_win(option, dice_values)

    total = sum(dice_values)
    game_id = generate_unique_id("7UP")

    if won:
        winnings = bet_amount_usd * multiplier
        credit_wallet(user.id, winnings)
        profit = winnings - bet_amount_usd
        result_text = (
            f"{pe('win')} <b>YOU WIN!</b> {pe('fire')}\n\n"
            f"{pe('dice')} Dice: [{', '.join(str(v) for v in dice_values)}] = <b>{total}</b>\n"
            f"{pe('target')} Option: {desc}\n"
            f"{pe('lightning')} Multiplier: <b>{multiplier}x</b>\n"
            f"{pe('money')} Profit: <b>+{currency_symbol}{profit:.2f}</b>"
        )
    else:
        result_text = (
            f"{pe('lose')} <b>YOU LOSE!</b>\n\n"
            f"{pe('dice')} Dice: [{', '.join(str(v) for v in dice_values)}] = <b>{total}</b>\n"
            f"{pe('target')} Option: {desc}\n"
            f"{pe('money')} Lost: <b>-{currency_symbol}{bet_amount_currency:.2f}</b>"
        )

    await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)

    # Record game
    game_sessions[game_id] = {
        "id": game_id, "game_type": game_subtype, "user_id": user.id,
        "bet_amount": bet_amount_usd, "status": "completed", "win": won,
        "option": option, "dice_values": dice_values, "total": total,
        "multiplier": multiplier if won else 0,
        "timestamp": str(datetime.now(timezone.utc)),
    }
    await update_stats_on_bet(user.id, game_id, bet_amount_usd, won,
                              multiplier=multiplier if won else 0, context=context)
    save_user_data(user.id)

@check_banned
@check_maintenance
async def sidebets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sidebets command - show help or live multipliers for tagged player."""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Check if user is tagging a player's message with an active game
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        target_user_id = target_user.id

        # Find active emoji game for this player
        match_id, match_data = find_active_emoji_game_for_user(target_user_id, update.effective_chat.id)

        if match_id and match_data:
            # Show live multipliers
            odds = calculate_match_win_probability(match_data)
            players = match_data.get("players", [])
            usernames = match_data.get("usernames", {})

            if len(players) >= 2:
                p1, p2 = players[0], players[1]
                p1_name = usernames.get(p1, f"Player {p1}")
                p2_name = usernames.get(p2, "Bot" if p2 == 0 else f"Player {p2}")

                game_type = match_data.get("game_type", "").replace("pvp_", "").replace("pvb_", "").replace("group_challenge_", "").replace("xdxw_", "")

                lock_text = ""
                if odds["is_locked"]:
                    lock_text = f"\n\n{pe('locked')} <b>BETS LOCKED</b> - Probability exceeds {SIDEBET_LOCK_THRESHOLD*100:.0f}%"

                await update.message.reply_text(
                    f"{pe('live')} <b>LIVE SIDE BET ODDS</b> {pe('live')}\n\n"
                    f"{pe(game_type)} <b>{game_type.upper()} Match</b> (ID: <code>{match_id}</code>)\n\n"
                    f"{pe('user')} {display_at(p1_name)}: Score {odds['p1_score']}\n"
                    f"   {pe('robot') + ' Bot' if p2 == 0 else pe('user') + ' ' + display_at(p2_name)}: Score {odds['p2_score']}\n"
                    f"{pe('trophy')} Target: First to {odds['target']}\n\n"
                    f"{pe('odds')} <b>Live Multipliers:</b>\n"
                    f"   {pe('high')} {display_at(p1_name)} wins: <b>{odds['mult_win_p1']}x</b> ({odds['p_win_p1']*100:.1f}% chance)\n"
                    f"   {pe('low')} {'Bot' if p2 == 0 else display_at(p2_name)} wins: <b>{odds['mult_win_p2']}x</b> ({odds['p_win_p2']*100:.1f}% chance)\n\n"
                    f"{pe('warning')} <i>Multipliers change dynamically based on game progress. Place bets using:</i>\n"
                    f"<code>/win amount</code> (reply to player msg) - Bet player wins\n"
                    f"<code>/lose amount</code> (reply to player msg) - Bet player loses"
                    f"{lock_text}",
                    parse_mode=ParseMode.HTML
                )
                return
            else:
                await update.message.reply_text(
                    f"{pe('cross')} Could not determine players for this match.",
                    parse_mode=ParseMode.HTML
                )
                return
        else:
            await update.message.reply_text(
                f"{pe('cross')} {target_user.mention_html()} does not have an active emoji game right now.",
                parse_mode=ParseMode.HTML
            )
            return

    # No reply - show help
    await update.message.reply_text(
        f"{pe('sidebet')} <b>SIDE BETS</b> {pe('sidebet')}\n\n"
        f"Bet on other players' emoji game matches!\n\n"
        f"<b>How to use:</b>\n"
        f"1. Find a player with an active emoji game\n"
        f"2. Reply to their message with:\n"
        f"   {pe('high')} <code>/win amount</code> - Bet that player wins\n"
        f"   {pe('low')} <code>/lose amount</code> - Bet that player loses\n"
        f"   {pe('odds')} <code>/sidebets</code> - View live multipliers\n\n"
        f"<b>How it works:</b>\n"
        f"{pe('lightning')} Multipliers are calculated dynamically based on:\n"
        f"   - Current score in the match\n"
        f"   - Rounds remaining\n"
        f"   - Mid-round roll results\n"
        f"   - Game mode (Normal/Crazy)\n\n"
        f"{pe('warning')} <b>Important:</b>\n"
        f"   - Bets lock when probability exceeds 98%\n"
        f"   - House edge: {SIDEBET_HOUSE_EDGE*100:.0f}%\n"
        f"   - Multipliers can change after each roll\n"
        f"   - Multipliers can change based on game state",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def win_bet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /win command - place a side bet that the tagged player wins."""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        await update.message.reply_text(
            f"{pe('cross')} Reply to a player's message who has an active emoji game.\n"
            f"Usage: <code>/win amount</code>",
            parse_mode=ParseMode.HTML
        )
        return

    args = update.message.text.strip().split()
    if len(args) < 2:
        await update.message.reply_text(
            f"{pe('cross')} Usage: <code>/win amount</code>\nExample: <code>/win 10</code>",
            parse_mode=ParseMode.HTML
        )
        return

    target_user = update.message.reply_to_message.from_user

    # Parse bet amount
    try:
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(args[1], user.id)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid bet amount.")
        return

    if get_active_balance_usd(user.id) < bet_amount_usd:
        await send_insufficient_balance_message(update)
        return

    if not await check_bet_limits(update, bet_amount_usd, 'sidebet_win'):
        return

    # Find active game
    match_id, match_data = find_active_emoji_game_for_user(target_user.id, update.effective_chat.id)
    if not match_id:
        await update.message.reply_text(
            f"{pe('cross')} {target_user.mention_html()} does not have an active emoji game.",
            parse_mode=ParseMode.HTML
        )
        return

    # Players can now bet on their own matches too
    players = match_data.get("players", [])

    # Calculate odds
    odds = calculate_match_win_probability(match_data)

    if odds["is_locked"]:
        await update.message.reply_text(
            f"{pe('locked')} <b>Bets are LOCKED!</b>\n"
            f"Probability exceeds {SIDEBET_LOCK_THRESHOLD*100:.0f}%. No more bets accepted.",
            parse_mode=ParseMode.HTML
        )
        return

    # Determine which player the bet is on
    p1, p2 = players[0], players[1]
    if target_user.id == p1:
        bet_multiplier = odds["mult_win_p1"]
        bet_on = "p1"
    elif target_user.id == p2:
        bet_multiplier = odds["mult_win_p2"]
        bet_on = "p2"
    else:
        # For PvB - user_id is the player
        if match_data.get("user_id") == target_user.id:
            bet_multiplier = odds["mult_win_p1"]
            bet_on = "p1"
        else:
            await update.message.reply_text(f"{pe('cross')} Could not determine bet target.")
            return

    # Deduct balance
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount_usd)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Insufficient balance.")
        return
    save_user_data(user.id)

    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")

    # Create side bet
    sidebet_id = generate_unique_id("SB")
    sidebet_data = {
        "id": sidebet_id,
        "match_id": match_id,
        "bettor_id": user.id,
        "bettor_username": normalize_username(user.username) or f"User_{user.id}",
        "bet_type": "win",
        "bet_on": bet_on,
        "target_player_id": target_user.id,
        "bet_amount_usd": bet_amount_usd,
        "multiplier_at_placement": bet_multiplier,
        "currency": currency,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
    }

    active_sidebets[sidebet_id] = sidebet_data
    if match_id not in match_sidebets:
        match_sidebets[match_id] = []
    match_sidebets[match_id].append(sidebet_id)

    # Store sidebet in game_sessions for /info command and user game history
    game_sessions[sidebet_id] = {
        "id": sidebet_id,
        "game_type": "sidebet_win",
        "bet_amount": bet_amount_usd,
        "bet_amount_usd": bet_amount_usd,
        "user_id": user.id,
        "match_id": match_id,
        "multiplier": bet_multiplier,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "target_player_id": target_user.id,
        "target_username": normalize_username(target_user.username) or f"User_{target_user.id}",
        "bettor_username": normalize_username(user.username) or f"User_{user.id}",
    }
    if 'game_sessions' not in user_stats.get(user.id, {}):
        user_stats.setdefault(user.id, {})['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(sidebet_id)
    save_user_data(user.id)

    target_name = normalize_username(target_user.username) or f"Player {target_user.id}"
    await update.message.reply_text(
        f"{pe('sidebet')} <b>Side Bet Placed!</b>\n\n"
        f"{pe('confirm')} Betting {display_at(target_name)} <b>WINS</b>\n"
        f"{pe('money')} Amount: {currency_symbol}{bet_amount_currency:.2f}\n"
        f"{pe('lightning')} Multiplier: <b>{bet_multiplier}x</b>\n"
        f"{pe('money')} Potential payout: <b>{currency_symbol}{bet_amount_usd * bet_multiplier:.2f}</b>\n\n"
        f"{pe('warning')} <i>Multiplier was locked at time of bet placement.</i>\n"
        f"Bet ID: <code>{sidebet_id}</code>",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def lose_bet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /lose command - place a side bet that the tagged player loses."""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not update.message.reply_to_message or not update.message.reply_to_message.from_user:
        await update.message.reply_text(
            f"{pe('cross')} Reply to a player's message who has an active emoji game.\n"
            f"Usage: <code>/lose amount</code>",
            parse_mode=ParseMode.HTML
        )
        return

    args = update.message.text.strip().split()
    if len(args) < 2:
        await update.message.reply_text(
            f"{pe('cross')} Usage: <code>/lose amount</code>\nExample: <code>/lose 10</code>",
            parse_mode=ParseMode.HTML
        )
        return

    target_user = update.message.reply_to_message.from_user

    # Parse bet amount
    try:
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(args[1], user.id)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Invalid bet amount.")
        return

    if get_active_balance_usd(user.id) < bet_amount_usd:
        await send_insufficient_balance_message(update)
        return

    if not await check_bet_limits(update, bet_amount_usd, 'sidebet_lose'):
        return

    # Find active game
    match_id, match_data = find_active_emoji_game_for_user(target_user.id, update.effective_chat.id)
    if not match_id:
        await update.message.reply_text(
            f"{pe('cross')} {target_user.mention_html()} does not have an active emoji game.",
            parse_mode=ParseMode.HTML
        )
        return

    # Players can now bet on their own matches too
    players = match_data.get("players", [])

    # Calculate odds
    odds = calculate_match_win_probability(match_data)

    if odds["is_locked"]:
        await update.message.reply_text(
            f"{pe('locked')} <b>Bets are LOCKED!</b>\n"
            f"Probability exceeds {SIDEBET_LOCK_THRESHOLD*100:.0f}%. No more bets accepted.",
            parse_mode=ParseMode.HTML
        )
        return

    # Determine which player the bet is AGAINST
    p1, p2 = players[0], players[1]
    if target_user.id == p1:
        # Betting p1 loses = p2 wins
        bet_multiplier = odds["mult_win_p2"]
        bet_on = "p2"
    elif target_user.id == p2:
        bet_multiplier = odds["mult_win_p1"]
        bet_on = "p1"
    else:
        if match_data.get("user_id") == target_user.id:
            bet_multiplier = odds["mult_win_p2"]
            bet_on = "p2"
        else:
            await update.message.reply_text(f"{pe('cross')} Could not determine bet target.")
            return

    # Deduct balance
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount_usd)
    except ValueError:
        await update.message.reply_text(f"{pe('cross')} Insufficient balance.")
        return
    save_user_data(user.id)

    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")

    # Create side bet
    sidebet_id = generate_unique_id("SB")
    sidebet_data = {
        "id": sidebet_id,
        "match_id": match_id,
        "bettor_id": user.id,
        "bettor_username": normalize_username(user.username) or f"User_{user.id}",
        "bet_type": "lose",
        "bet_on": bet_on,
        "target_player_id": target_user.id,
        "bet_amount_usd": bet_amount_usd,
        "multiplier_at_placement": bet_multiplier,
        "currency": currency,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
    }

    active_sidebets[sidebet_id] = sidebet_data
    if match_id not in match_sidebets:
        match_sidebets[match_id] = []
    match_sidebets[match_id].append(sidebet_id)

    # Store sidebet in game_sessions for /info command and user game history
    game_sessions[sidebet_id] = {
        "id": sidebet_id,
        "game_type": "sidebet_lose",
        "bet_amount": bet_amount_usd,
        "bet_amount_usd": bet_amount_usd,
        "user_id": user.id,
        "match_id": match_id,
        "multiplier": bet_multiplier,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "target_player_id": target_user.id,
        "target_username": normalize_username(target_user.username) or f"User_{target_user.id}",
        "bettor_username": normalize_username(user.username) or f"User_{user.id}",
    }
    if 'game_sessions' not in user_stats.get(user.id, {}):
        user_stats.setdefault(user.id, {})['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(sidebet_id)
    save_user_data(user.id)

    target_name = normalize_username(target_user.username) or f"Player {target_user.id}"
    await update.message.reply_text(
        f"{pe('sidebet')} <b>Side Bet Placed!</b>\n\n"
        f"{pe('cross')} Betting {display_at(target_name)} <b>LOSES</b>\n"
        f"{pe('money')} Amount: {currency_symbol}{bet_amount_currency:.2f}\n"
        f"{pe('lightning')} Multiplier: <b>{bet_multiplier}x</b>\n"
        f"{pe('money')} Potential payout: <b>{currency_symbol}{bet_amount_usd * bet_multiplier:.2f}</b>\n\n"
        f"{pe('warning')} <i>Multiplier was locked at time of bet placement.</i>\n"
        f"Bet ID: <code>{sidebet_id}</code>",
        parse_mode=ParseMode.HTML
    )

async def pvb_cashout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cashout button press in PvB emoji games."""
    query = update.callback_query
    user = query.from_user

    # Parse callback data: pvb_cashout_{match_id}_{round}
    parts = query.data.split("_")
    if len(parts) < 4:
        await query.answer("Invalid cashout request.", show_alert=True)
        return

    match_id = parts[2]
    cashout_round = int(parts[3]) if len(parts) > 3 else 0

    match_data = game_sessions.get(match_id)
    if not match_data:
        await query.answer("Game no longer exists.", show_alert=True)
        return

    # Verify this is the correct player. PvB games may store the player either
    # in "players" (e.g. xdxw_playbot/gc_playbot) or only in "user_id"/"host_id"
    # (e.g. /dice play_vs_bot_game). Accept any of those.
    players = match_data.get("players", []) or []
    candidate_ids = [p for p in players if p != 0]
    legacy_id = match_data.get("user_id") or match_data.get("host_id")
    if legacy_id and legacy_id not in candidate_ids:
        candidate_ids.append(legacy_id)
    if not candidate_ids or user.id not in candidate_ids:
        await query.answer("This cashout button is not for you.", show_alert=True)
        return

    # Check if the cashout button is still valid (not expired by a new round/roll)
    active_co = _active_cashout_buttons.get(match_id)
    if not active_co or active_co.get("round") != cashout_round:
        await query.answer("This cashout button has expired.", show_alert=True)
        return

    # Strict per-button ownership: only the registered user_id may use it
    if active_co.get("user_id") and active_co["user_id"] != user.id:
        await query.answer("This cashout button is not for you.", show_alert=True)
        return

    # Invalidate the cashout button immediately
    _active_cashout_buttons.pop(match_id, None)

    if match_data.get("status") != "active":
        await query.answer("Game is no longer active.", show_alert=True)
        return

    await query.answer()

    # Calculate cashout amount based on current win probability of the match.
    bet_amount = match_data.get("bet_amount_usd", match_data.get("bet_amount", 0))
    cashout_mult = calculate_cashout_multiplier(match_data, user_id=user.id)
    cashout_amount = round(bet_amount * cashout_mult, 2)

    # Credit the player
    credit_wallet(user.id, cashout_amount)
    save_user_data(user.id)

    # Mark game as completed with cashout
    match_data["status"] = "cashout"
    match_data["cashout_amount"] = cashout_amount
    match_data["cashout_multiplier"] = cashout_mult

    # Update house balance (house keeps bet - cashout)
    house_profit = bet_amount - cashout_amount
    bot_settings["house_balance"] = bot_settings.get("house_balance", 0) + house_profit

    chat_id = match_data.get("chat_id")
    # Emoji-game match messages are no longer pinned.

    # Send cashout confirmation
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"{pe('cashout')} <b>CASHOUT!</b>\n\n"
                f"{user.mention_html()} cashed out of their match!\n"
                f"{pe('money')} Cashout: <b>${cashout_amount:.2f}</b> ({cashout_mult}x)\n"
                f"{pe('money')} Original bet: ${bet_amount:.2f}\n\n"
                f"Match ID: <code>{match_id}</code>"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Failed to send cashout message: {e}")

    # Void and refund all side bets on this match
    await void_sidebets_for_cashout(match_id, context)

    # Cancel any pending PvB timeout jobs - the game is over
    try:
        _cancel_pvb_timeout_jobs(context, user.id, match_id)
    except Exception:
        pass

    # Clean up active-game indices so the player can start a new game
    try:
        if context.chat_data.get(f"active_pvb_game_{user.id}") == match_id:
            context.chat_data.pop(f"active_pvb_game_{user.id}", None)
    except Exception:
        pass
    if active_pvb_games.get(user.id) == match_id:
        active_pvb_games.pop(user.id, None)

    # Persist & deindex
    game_sessions[match_id] = match_data
    _unindex_user_game(user.id, match_id)

@check_banned
@check_maintenance
async def start_game_conversation_from_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    command = update.message.text.split()[0].lower().lstrip('/')
    # Handle aliases: tower -> tower, mines -> mines
    game_type = 'mines' if command in ('mines', 'm') else 'tower'
    # Check per-game maintenance status
    if not is_game_enabled(game_type):
        emoji_map = {"mines": "\U0001f4a3", "tower": "\U0001f3d4"}
        emoji = emoji_map.get(game_type, "\U0001f3ae")
        await update.message.reply_text(
            f"\U0001f527 {emoji} <b>{game_type.title()}</b> game is currently under maintenance. "
            f"Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END

    # If no arguments, show help menu
    if not context.args or len(context.args) == 0:
        if game_type == 'mines':
            help_text = (
                f"{pe('bomb')} <b>Mines Game</b>\n\n"
                "<b>How to Play:</b>\n"
                "Click on tiles to reveal gems or mines. Each safe gem increases your multiplier!\n"
                "Cash out at any time to secure your winnings. Hitting a mine ends the game.\n\n"
                "<b>Commands:</b>\n"
                "• <code>/mines &lt;amount&gt;</code> - Start a game with specified bet amount\n"
                "• <code>/m &lt;amount&gt;</code> - Alias for /mines\n"
                "• <code>/continue &lt;game_id&gt;</code> - Continue an active mines game\n\n"
                "<b>Examples:</b>\n"
                "• <code>/mines 10</code> - Start with $10 bet\n"
                "• <code>/m all</code> - Start with all-in bet\n"
            )
        else:  # tower
            help_text = (
                f"{pe('tower')} <b>Tower Game</b>\n\n"
                "<b>How to Play:</b>\n"
                "Climb the tower by selecting safe tiles. Each floor has one snake hidden behind a tile.\n"
                "Cash out at any time to secure your winnings, or reach the top for the jackpot!\n\n"
                "<b>Difficulty Modes:</b>\n"
                "• Easy: 4 tiles per floor (25% risk)\n"
                "• Medium: 3 tiles per floor (33% risk)\n"
                "• Hard: 2 tiles per floor (50% risk)\n\n"
                "<b>Commands:</b>\n"
                "• <code>/tower &lt;amount&gt;</code> - Start a game with specified bet amount\n"
                "• <code>/tr &lt;amount&gt;</code> - Alias for /tower\n"
                "• <code>/continue &lt;game_id&gt;</code> - Continue an active tower game\n\n"
                "<b>Examples:</b>\n"
                "• <code>/tower 10</code> - Start with $10 bet\n"
                "• <code>/tr all</code> - Start with all-in bet\n"
            )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    context.user_data['game_type'] = game_type

    # NEW: For /mines amount, parse bet amount from command
    if game_type == 'mines' and context.args and len(context.args) > 0:
        user = update.effective_user
        await ensure_user_in_wallets(user.id, user.username, context=context)

        try:
            bet_amount_str = context.args[0].lower()
            # Display-currency aware (parity with blackjack/tower).
            bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
        except ValueError:
            await update.message.reply_text("Invalid bet amount. Usage: /mines <amount>\nExample: /mines 10")
            return ConversationHandler.END

        # Check bet limits
        if not await check_bet_limits(update, bet_amount, 'mines'):
            return ConversationHandler.END

        # Check balance
        if get_active_balance_usd(user.id) < bet_amount:
            await update.message.reply_text(f"{pe('cross')} You don't have enough balance. Please enter a lower amount.")
            return ConversationHandler.END

        # Store bet amount and ask for number of mines
        context.user_data['bet_amount'] = bet_amount
        buttons = [[InlineKeyboardButton(str(i), callback_data=f"bombs_{i}_{user.id}") for i in range(row, row + 8)] for row in range(1, 25, 8)]
        text = f"{pe('bomb')} <b>Mines Game</b>\n\n💰 Bet Amount: ${bet_amount:.2f}\n\nSelect the number of mines (1-24):"
        buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel_game")])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
        return SELECT_BOMBS

    if game_type == 'mines':
        buttons = [[InlineKeyboardButton(str(i), callback_data=f"bombs_{i}") for i in range(row, row + 8)] for row in range(1, 25, 8)]
        text = f"{pe('bomb')} Select the number of mines (1-24):"
    else: # tower
        buttons = [[InlineKeyboardButton(f"{i}", callback_data=f"bombs_{i}") for i in range(1, 4)]]
        text = f"{pe('tower')} Select the number of bombs per row (1-3):"

    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel_game")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return SELECT_BOMBS

@check_banned
@check_maintenance
async def select_bombs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    # NEW: Check if user-specific button (bombs_X_USERID format)
    parts = query.data.split("_")
    if len(parts) >= 3 and parts[2].isdigit():
        # User-specific button check
        button_user_id = int(parts[2])
        if query.from_user.id != button_user_id:
            await query.answer("This menu is not for you.", show_alert=True)
            return ConversationHandler.END
    else:
        # Check menu ownership (old method)
        if not check_menu_ownership(query, context):
            await query.answer("This menu is not for you.", show_alert=True)
            return ConversationHandler.END

    await query.answer()
    bombs = parts[1]
    context.user_data['bombs'] = bombs

    # NEW: If bet amount is already set (from /mines amount), start game directly
    if 'bet_amount' in context.user_data:
        game_type = context.user_data.get('game_type')
        if game_type == 'mines':
            # Start mines game directly
            user = query.from_user
            bet_amount = context.user_data['bet_amount']
            num_mines = int(bombs)

            # Start the game
            await ensure_user_in_wallets(user.id, user.username, context=context)

            total_cells = 25

            # Generate a fresh 15-character client seed for this game BEFORE calculating mines
            game_client_seed = generate_game_client_seed()

            # Use server seed from user's provably fair data, but fresh client seed per game
            seeds = get_user_seeds(user.id)
            current_nonce = seeds["nonce"]
            increment_user_nonce(user.id)  # Increment nonce at game start

            # Calculate mine positions using server seed + fresh game client seed
            mine_numbers = generate_mine_positions(seeds["server_seed"], game_client_seed, current_nonce, num_mines)

            # Deduct bet atomically BEFORE creating the game session so a
            # failed deduct cannot leave an orphan session sitting in
            # game_sessions / user_stats with no charged stake.
            try:
                await deduct_wallet_safe(user.id, bet_amount)
            except ValueError:
                await query.answer("Insufficient balance!", show_alert=True)
                context.user_data.clear()
                return ConversationHandler.END

            game_id = generate_unique_id("MN")
            game_sessions[game_id] = {
                "id": game_id, "game_type": "mines", "user_id": user.id, "bet_amount": bet_amount,
                "active_currency": get_active_currency(user.id),
                "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
                "status": "active", "timestamp": str(datetime.now(timezone.utc)), "mines": mine_numbers,
                "picks": [], "total_cells": total_cells, "num_mines": num_mines,
                "server_seed": seeds["server_seed"], "client_seed": game_client_seed, "nonce": current_nonce
            }
            await ensure_user_in_wallets(user.id, user.username, context=context)
            if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
            user_stats[user.id]['game_sessions'].append(game_id)

            save_user_data(user.id)

            initial_text = (
                f"{pe('bomb')} <b>Mines Game Started!</b> (ID: <code>{game_id}</code>)\n\nBet: <b>${bet_amount:.2f}</b>\nMines: <b>{num_mines}</b>\n\n"
                "Click the buttons to reveal tiles. Find gems to increase your multiplier. Avoid the bombs!\n"
                "You can cash out after any successful pick."
            )
            await query.edit_message_text(
                initial_text, parse_mode=ParseMode.HTML, reply_markup=mines_keyboard(game_id)
            )
            context.user_data.clear()
            return ConversationHandler.END

    await query.edit_message_text(f"Bombs set to {bombs}. Now, please enter your bet amount (or 'all').", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
    # Set ownership after editing
    set_menu_owner(query.message, query.from_user.id)
    return SELECT_BET_AMOUNT

@check_banned
@check_maintenance
async def pvb_who_rolls_first_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selection of who rolls first in PvB games"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    if data == "pvb_first_user":
        context.user_data['bot_rolls_first'] = False
    elif data == "pvb_first_bot":
        context.user_data['bot_rolls_first'] = True
    else:
        return SELECT_WHO_ROLLS_FIRST

    game_type = context.user_data['game_type']
    target_score = context.user_data['target_score']

    # Create a fake update object for play_vs_bot_game
    await query.delete_message()

    # Start the game - we need to send a new message since play_vs_bot_game expects update.message
    await play_vs_bot_game_from_callback(query, context, game_type, target_score)
    context.user_data.clear()
    return ConversationHandler.END

@check_banned
@check_maintenance
async def choose_ai_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    # Check menu ownership
    if not check_menu_ownership(query, context):
        await query.answer("This menu is not for you.", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    model_choice = query.data.split('_')[-1]
    context.user_data['ai_model'] = model_choice

    await safe_edit_message(
        query,
        f"{pe('robot')} <b>AI Assistant ({model_choice.title()})</b>\n\nI'm ready to help! What's on your mind? Ask me anything.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel & Back to Menu", callback_data="cancel_ai")]])
    )
    return ASK_AI_PROMPT

@check_banned
@check_maintenance
async def transactions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /transactions - Show user's own transaction history
    /transaction user_id or @username - Admin command to view user's transactions
    """
    user = update.effective_user
    args = update.message.text.strip().split()

    # Check if admin is viewing another user's transactions
    if is_admin(user.id) and len(args) > 1:
        target_arg = args[1]
        target_user_id = None

        # Parse @username or user_id
        if target_arg.startswith("@"):
            username = normalize_username(target_arg[1:])  # This adds @ and lowercases
            target_user_id = username_to_userid.get(username)
            # Also try without @ in case it's stored differently
            if not target_user_id:
                username_no_at = target_arg[1:].lower()
                target_user_id = username_to_userid.get(username_no_at)
        else:
            try:
                target_user_id = int(target_arg)
            except ValueError:
                await update.message.reply_text(f"{pe('cross')} Invalid user ID. Usage: /transaction @username or /transaction user_id")
                return

        if not target_user_id:
            await update.message.reply_text(f"{pe('cross')} User not found. Make sure to use @username or user ID.")
            return

        if target_user_id not in user_stats:
            await update.message.reply_text(f"{pe('cross')} User data not found.")
            return

        await send_transactions_page(update, context, target_user_id, 0, is_admin=True)
        return

    # Regular user viewing their own transactions
    await ensure_user_in_wallets(user.id, user.username, context=context)
    await send_transactions_page(update, context, user.id, 0, is_admin=False)

async def close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle close button - delete the message."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    try:
        await query.message.delete()
    except Exception as e:
        logging.debug(f"Could not delete message: {e}")

async def transactions_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle transaction close button - user-specific."""
    query = update.callback_query
    if not query or not query.data:
        return
    
    # Parse callback: txn_close_{user_id}
    parts = query.data.split('_')
    if len(parts) < 3:
        await query.answer("Invalid callback data.", show_alert=True)
        return
    
    target_user_id = int(parts[2])
    
    # Verify ownership
    if query.from_user.id != target_user_id:
        await query.answer("This is not your menu.", show_alert=True)
        return
    
    await query.answer()
    try:
        await query.message.delete()
    except Exception as e:
        logging.debug(f"Could not delete message: {e}")

async def transactions_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle transaction page navigation callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    # Parse callback: txn_page_{user_id}_{page}_{is_admin}
    parts = query.data.split('_')
    if len(parts) < 5:
        await query.answer("Invalid callback data.", show_alert=True)
        return

    target_user_id = int(parts[2])
    page = int(parts[3])
    is_admin_flag = parts[4] == '1'

    # Verify ownership (unless admin)
    if not is_admin_flag and query.from_user.id != target_user_id:
        await query.answer("This is not your transaction history.", show_alert=True)
        return

    # For admin, verify they're still admin
    if is_admin_flag and not is_admin(query.from_user.id):
        await query.answer("You are not authorized to view this.", show_alert=True)
        return

    await query.answer()

    # Create a mock update object for send_transactions_page
    class MockUpdate:
        def __init__(self, callback_query):
            self.callback_query = callback_query
            self.message = callback_query.message

    mock_update = MockUpdate(query)
    await send_transactions_page(mock_update, context, target_user_id, page, is_admin=is_admin_flag)

async def demo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /demo - Users claim demo amount (once per cooldown period)
    /demo amount - Admin sets demo amount
    /demo on/off - Admin enables/disables demo feature
    """
    user = update.effective_user
    args = update.message.text.strip().split()

    # Admin commands
    if is_admin(user.id) and len(args) > 1:
        if args[1].lower() == "on":
            bot_settings["demo_enabled"] = True
            await save_bot_settings_only()
            await update.message.reply_text(f"{pe('check')} Demo feature enabled!")
            return
        elif args[1].lower() == "off":
            bot_settings["demo_enabled"] = False
            await save_bot_settings_only()
            await update.message.reply_text(f"{pe('cross')} Demo feature disabled!")
            return
        else:
            # Try to set amount
            try:
                amount = float(args[1])
                if amount <= 0:
                    await update.message.reply_text(f"{pe('cross')} Amount must be positive!")
                    return
                bot_settings["demo_amount"] = amount
                await save_bot_settings_only()
                await update.message.reply_text(f"{pe('check')} Demo amount set to ${amount:.2f}", parse_mode=ParseMode.HTML)
                return
            except ValueError:
                await update.message.reply_text(f"{pe('cross')} Invalid amount! Usage: /demo <amount>")
                return

    # Regular user claim
    if not bot_settings.get("demo_enabled", True):
        await update.message.reply_text(f"{pe('cross')} Demo feature is currently disabled.", parse_mode=ParseMode.HTML)
        return

    await ensure_user_in_wallets(user.id, user.username, context=context)
    stats = user_stats[user.id]

    # Check cooldown
    last_claim_str = stats.get("last_demo_claim")
    if last_claim_str:
        last_claim_time = datetime.fromisoformat(last_claim_str)
        cooldown_seconds = bot_settings.get("demo_cooldown", 30)
        time_since_claim = (datetime.now(timezone.utc) - last_claim_time).total_seconds()

        if time_since_claim < cooldown_seconds:
            time_left_seconds = int(cooldown_seconds - time_since_claim)
            minutes = time_left_seconds // 60
            seconds = time_left_seconds % 60
            await update.message.reply_text(
                f"⏰ You can claim demo again in {minutes}m {seconds}s"
            )
            return

    # Give demo amount
    demo_amount = bot_settings.get("demo_amount", 10.0)
    credit_wallet(user.id, demo_amount)
    stats["last_demo_claim"] = str(datetime.now(timezone.utc))
    save_user_data(user.id)

    await update.message.reply_text(
        f"{pe('gift')} <b>Demo Claimed!</b>\n\n"
        f"You received <b>${demo_amount:.2f}</b>\n"
        f"New balance: <b>${get_total_balance_usd(user.id):,.2f}</b>\n\n"
        f"{pe('bulb')} Try your luck with our games!",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def serverseed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user their current server seed hash"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    pf_data = user_stats[user.id].get("provably_fair", {})
    server_seed = pf_data.get("server_seed", "")

    # Hash the server seed to show to user (can't reveal actual seed until rotation)
    server_seed_hash = hashlib.sha256(server_seed.encode()).hexdigest()

    keyboard = [[InlineKeyboardButton("Rotate Seeds", callback_data="pf_rotate_seeds")]]

    await update.message.reply_text(
        f"{pe('dice')} <b>Provably Fair - Server Seed</b>\n\n"
        f"<b>Server Seed Hash (SHA-256):</b>\n"
        f"<code>{server_seed_hash}</code>\n\n"
        f"<b>Nonce:</b> {pf_data.get('nonce', 0)}\n\n"
        f"{pe('bulb')} The actual server seed is hidden until you rotate to a new one.\n"
        f"This ensures fairness - we can't change the seed after you know the hash!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def seed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show and allow changing the client seed"""
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    pf_data = user_stats[user.id].get("provably_fair", {})
    client_seed = pf_data.get("client_seed", "")
    nonce = pf_data.get("nonce", 0)

    keyboard = [
        [InlineKeyboardButton("Change Client Seed", callback_data="pf_change_client_seed")],
        [InlineKeyboardButton("Rotate All Seeds", callback_data="pf_rotate_seeds")]
    ]

    await update.message.reply_text(
        f"{pe('dice')} <b>Provably Fair - Your Seed</b>\n\n"
        f"<b>Client Seed:</b>\n"
        f"<code>{client_seed}</code>\n\n"
        f"<b>Nonce:</b> {nonce}\n\n"
        f"{pe('bulb')} You can change your client seed anytime.\n"
        f"The nonce increases with each bet using these seeds.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def pf_rotate_seeds_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rotate server seed - reveal old one and activate next one"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    pf_data = user_stats[user.id].get("provably_fair", {})

    # Reveal old server seed
    old_server_seed = pf_data.get("server_seed", "")
    old_nonce = pf_data.get("nonce", 0)

    # Rotate to next seed
    pf_data["server_seed"] = pf_data.get("next_server_seed", generate_server_seed())
    pf_data["next_server_seed"] = generate_server_seed()
    pf_data["nonce"] = 0  # Reset nonce

    save_user_data(user.id)

    # Show the revealed seed
    new_seed_hash = hashlib.sha256(pf_data["server_seed"].encode()).hexdigest()

    await query.edit_message_text(
        f"{pe('refresh')} <b>Seeds Rotated!</b>\n\n"
        f"<b>Previous Server Seed (REVEALED):</b>\n"
        f"<code>{old_server_seed}</code>\n\n"
        f"<b>Used for {old_nonce} bets</b>\n\n"
        f"<b>New Server Seed Hash:</b>\n"
        f"<code>{new_seed_hash}</code>\n\n"
        f"{pe('check')} Nonce reset to 0\n"
        f"{pe('bulb')} You can now verify all bets made with the old seed!",
        parse_mode=ParseMode.HTML
    )

@check_banned
@check_maintenance
async def pf_change_client_seed_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start conversation to change client seed"""
    query = update.callback_query
    await query.answer()
    user = query.from_user

    # Add cancel button
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="pf_cancel_seed_change")]]

    await query.edit_message_text(
        f"{pe('refresh')} <b>Change Client Seed</b>\n\n"
        f"Please send your new client seed.\n\n"
        f"📝 Requirements:\n"
        f"• 4-64 characters\n"
        f"• Letters and numbers only\n\n"
        f"Tap Cancel below to abort.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return PF_CHANGE_CLIENT_SEED_INPUT

@check_banned
@check_maintenance
async def pf_cancel_seed_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel seed change via inline button"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(f"{pe('cross')} Seed change cancelled.")
    return ConversationHandler.END

@check_banned
@check_maintenance
async def pf_show_game_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show provably fair details for a completed game"""
    query = update.callback_query
    await query.answer()

    game_id = query.data.replace("pf_show_", "")
    game = game_sessions.get(game_id)

    if not game:
        await query.edit_message_text(f"{pe('cross')} Game not found or expired.")
        return

    # Get game details
    server_seed_hash = hashlib.sha256(game.get("server_seed", "").encode()).hexdigest()
    client_seed = game.get("client_seed", "N/A")
    nonce = game.get("nonce", 0)
    game_type = game.get("game_type", "unknown")

    text = (
        f"{pe('dice')} <b>Provably Fair Details</b>\n"
        f"Game ID: <code>{game_id}</code>\n\n"
        f"<b>Server Seed (SHA-256):</b>\n"
        f"<code>{server_seed_hash}</code>\n\n"
        f"<b>Client Seed:</b>\n"
        f"<code>{client_seed}</code>\n\n"
        f"<b>Nonce:</b> {nonce}\n"
        f"<b>Game Type:</b> {game_type}\n\n"
        f"{pe('bulb')} Use /serverseed to rotate your seed and reveal the actual server seed.\n"
        f"Then you can verify this result independently!"
    )

    keyboard = [[InlineKeyboardButton("Verify Result", callback_data=f"pf_verify_menu")]]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def pf_verify_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show verification menu with game selection"""
    query = update.callback_query
    await query.answer()

    # Check if this is a group chat
    chat = update.effective_chat
    user = update.effective_user

    if chat.type in ["group", "supergroup"]:
        # In group chat - send DM to user
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text="🔍 <b>Verify Game Result</b>\n\n"
                     "Select the game type you want to verify:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Coinflip", callback_data="pf_verify_coinflip"),
                     InlineKeyboardButton("Roulette", callback_data="pf_verify_roulette")],
                    [InlineKeyboardButton("High-Low", callback_data="pf_verify_highlow"),
                     InlineKeyboardButton("Blackjack", callback_data="pf_verify_blackjack")],
                    [InlineKeyboardButton(f"{pe('darts')} Keno", callback_data="pf_verify_keno"),
                     InlineKeyboardButton("Mines", callback_data="pf_verify_mines")],
                    [InlineKeyboardButton(f"{pe('tower')} Tower", callback_data="pf_verify_tower")]
                ])
            )
            await query.edit_message_text(
                f"{pe('check')} Check your DM for verification!",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await query.edit_message_text(
                f"{pe('cross')} Please start a private chat with me first by clicking @{context.bot.username}",
                parse_mode=ParseMode.HTML
            )
        return ConversationHandler.END

    # In private chat - show menu normally
    keyboard = [
        [InlineKeyboardButton("Coinflip", callback_data="pf_verify_coinflip"),
         InlineKeyboardButton("Roulette", callback_data="pf_verify_roulette")],
        [InlineKeyboardButton("High-Low", callback_data="pf_verify_highlow"),
         InlineKeyboardButton("Blackjack", callback_data="pf_verify_blackjack")],
        [InlineKeyboardButton(f"{pe('darts')} Keno", callback_data="pf_verify_keno"),
         InlineKeyboardButton("Mines", callback_data="pf_verify_mines")],
        [InlineKeyboardButton(f"{pe('tower')} Tower", callback_data="pf_verify_tower")],
        [InlineKeyboardButton("Back", callback_data="main_menu")]
    ]

    await query.edit_message_text(
        f"{pe('search')} <b>Verify Game Result</b>\n\n"
        f"Select the game type you want to verify.\n\n"
        f"You'll need:\n"
        f"• Server seed (revealed after rotation)\n"
        f"• Client seed\n"
        f"• Nonce\n"
        f"• Game-specific parameters",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_banned
@check_maintenance
async def pf_verify_coinflip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start coinflip verification process"""
    query = update.callback_query
    await query.answer()

    context.user_data['pf_verify_game'] = 'coinflip'

    await query.edit_message_text(
        f"{pe('coin')} <b>Verify Coinflip Result</b>\n\n"
        f"I'll calculate the result for you!\n\n"
        f"Please enter the <b>Server Seed</b> (revealed after rotation):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="pf_verify_cancel")]])
    )

    return PF_VERIFY_INPUT_SERVER_SEED

@check_banned
@check_maintenance
async def pf_verify_roulette_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start roulette verification process"""
    query = update.callback_query
    await query.answer()

    context.user_data['pf_verify_game'] = 'roulette'

    await query.edit_message_text(
        f"{pe('target')} <b>Verify Roulette Result</b>\n\n"
        f"I'll calculate the result for you!\n\n"
        f"Please enter the <b>Server Seed</b> (revealed after rotation):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="pf_verify_cancel")]])
    )

    return PF_VERIFY_INPUT_SERVER_SEED

@check_banned
@check_maintenance
async def pf_verify_highlow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start high-low verification process"""
    query = update.callback_query
    await query.answer()

    context.user_data['pf_verify_game'] = 'highlow'

    await query.edit_message_text(
        f"🎴 <b>Verify High-Low Result</b>\n\n"
        f"I'll calculate the shuffled deck for you!\n\n"
        f"Please enter the <b>Server Seed</b> (revealed after rotation):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="pf_verify_cancel")]])
    )

    return PF_VERIFY_INPUT_SERVER_SEED

@check_banned
@check_maintenance
async def pf_verify_keno_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start keno verification process"""
    query = update.callback_query
    await query.answer()

    context.user_data['pf_verify_game'] = 'keno'

    await query.edit_message_text(
        f"🎱 <b>Verify Keno Result</b>\n\n"
        f"I'll calculate the drawn numbers for you!\n\n"
        f"Please enter the <b>Server Seed</b> (revealed after rotation):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="pf_verify_cancel")]])
    )

    return PF_VERIFY_INPUT_SERVER_SEED

@check_banned
@check_maintenance
async def pf_verify_mines_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start mines verification process"""
    query = update.callback_query
    await query.answer()

    context.user_data['pf_verify_game'] = 'mines'

    await query.edit_message_text(
        f"{pe('bomb')} <b>Verify Mines Result</b>\n\n"
        f"I'll calculate the mine positions for you!\n\n"
        f"Please enter the <b>Server Seed</b> (revealed after rotation):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="pf_verify_cancel")]])
    )

    return PF_VERIFY_INPUT_SERVER_SEED

@check_banned
@check_maintenance
async def pf_verify_tower_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start tower verification process"""
    query = update.callback_query
    await query.answer()

    context.user_data['pf_verify_game'] = 'tower'

    await query.edit_message_text(
        f"🗼 <b>Verify Tower Result</b>\n\n"
        f"I'll calculate the snake positions for you!\n\n"
        f"Please enter the <b>Server Seed</b> (revealed after rotation):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="pf_verify_cancel")]])
    )

    return PF_VERIFY_INPUT_SERVER_SEED

@check_banned
@check_maintenance
async def pf_verify_param_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle difficulty selection for tower"""
    query = update.callback_query
    await query.answer()

    difficulty = query.data.replace("pf_verify_param_", "")
    context.user_data['pf_verify_param'] = difficulty

    # Calculate and show result
    return await pf_verify_calculate_result(query, context, is_callback=True)

@check_banned
@check_maintenance
async def pf_verify_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel verification process"""
    query = update.callback_query
    await query.answer()

    # Clear user data
    for key in ['pf_verify_game', 'pf_verify_server_seed', 'pf_verify_client_seed', 'pf_verify_nonce', 'pf_verify_param']:
        context.user_data.pop(key, None)

    await query.edit_message_text(f"{pe('cross')} Verification cancelled.", parse_mode=ParseMode.HTML)
    return ConversationHandler.END

@check_banned
@check_maintenance
async def rakeback_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context, first_name=user.first_name)
    stats = user_stats[user.id]

    rakeback_balance = stats.get("rakeback_balance", 0.0)

    if rakeback_balance <= 0:
        message = "You have no rakeback to claim. Play some games to accumulate rakeback!" + get_username_bonus_guidance()
        if from_callback:
            await update.callback_query.answer("No rakeback available. Play more games!", show_alert=True)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.HTML)
        return

    # Apply username bonus (5% extra if user has bot username in name)
    final_amount = apply_username_bonus(rakeback_balance, user.id)
    has_bonus = check_username_bonus(user.id)

    credit_wallet(user.id, final_amount)
    stats["rakeback_balance"] = 0.0
    save_user_data(user.id)

    bonus_text = ""
    if has_bonus:
        bonus_text = f"\n{pe('win')} <b>Username Bonus Applied!</b> +5% extra (${final_amount - rakeback_balance:.4f})"

    current_level = get_user_level(user.id)
    message = (
        f"{pe('money')} <b>Rakeback Claimed!</b>\n\n"
        f"Amount: <b>${final_amount:.4f}</b>{bonus_text}\n"
        f"VIP Tier: {current_level['name']} ({current_level['rakeback_percentage']}% rakeback rate)"
        + get_username_bonus_guidance()
    )

    if from_callback:
        keyboard = [[InlineKeyboardButton("Back to Bonuses", callback_data="main_bonuses")]]
        await update.callback_query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('start', start_command, block=False))
    app.add_handler(CommandHandler('help', help_command, block=False))
    app.add_handler(CommandHandler('bank', bank_command, block=False))
    app.add_handler(CommandHandler('hb', bank_command, block=False))
    app.add_handler(CommandHandler('stats', stats_command, block=False))
    app.add_handler(CommandHandler('limits', limits_command, block=False))
    app.add_handler(CommandHandler('users', users_command, block=False))
    app.add_handler(CommandHandler('cancelall', cancel_all_command, block=False))
    app.add_handler(CommandHandler('info', info_command, block=False))
    app.add_handler(CommandHandler('continue', continue_command, block=False))
    app.add_handler(CommandHandler('user', user_info_command, block=False))
    app.add_handler(CommandHandler('p', price_command, block=False))
    app.add_handler(CommandHandler('daily', daily_command, block=False))
    app.add_handler(CommandHandler('language', language_command, block=False))
    app.add_handler(CommandHandler(['currency', 'cur'], currency_command, block=False))
    app.add_handler(CommandHandler(['maxbet', 'limits'], maxbet_command, block=False))
    app.add_handler(CommandHandler('gameshistory', games_history_command, block=False))
    app.add_handler(CommandHandler('surprisedrop', surprisedrop_toggle_command, block=False))
    app.add_handler(CommandHandler('surprisedrop_now', surprisedrop_command, block=False))
    app.add_handler(CallbackQueryHandler(games_history_page_callback, pattern='^admin_ghist_page_', block=False))
    app.add_handler(CommandHandler('setbal', setbal_command, block=False))
    app.add_handler(CommandHandler('resetleaderboard', resetleaderboard_command, block=False))
    app.add_handler(CommandHandler('setdaily', setdaily_command, block=False))
    app.add_handler(CommandHandler('dailyoff', dailyoff_command, block=False))
    app.add_handler(CommandHandler('dailyon', dailyon_command, block=False))
    app.add_handler(CommandHandler('chicken', chicken_command, block=False))
    app.add_handler(CommandHandler(['7up', '7updown', '7ud'], seven_up_command, block=False))
    app.add_handler(CommandHandler(['sidebets', 'sides'], sidebets_command, block=False))
    app.add_handler(CommandHandler('win', win_bet_command, block=False))
    app.add_handler(CommandHandler('lose', lose_bet_command, block=False))
    app.add_handler(CallbackQueryHandler(rpvp_confirm_callback, pattern='^rpvp_confirm_', block=False))
    app.add_handler(CallbackQueryHandler(rpvp_playbot_callback, pattern='^rpvp_playbot_', block=False))
    app.add_handler(CallbackQueryHandler(rpvp_cancel_callback, pattern='^rpvp_cancel_', block=False))
    app.add_handler(CallbackQueryHandler(rpvp_mode_callback, pattern='^rpvp_mode_', block=False))
    app.add_handler(CallbackQueryHandler(rpvp_rolls_callback, pattern='^rpvp_rolls_', block=False))
    app.add_handler(CallbackQueryHandler(rpvp_target_callback, pattern='^rpvp_target_', block=False))
    app.add_handler(CallbackQueryHandler(rpvp_pvb_mode_callback, pattern='^rpvp_pvb_mode_', block=False))
    app.add_handler(CallbackQueryHandler(rpvp_pvb_rolls_callback, pattern='^rpvp_pvb_rolls_', block=False))
    app.add_handler(CallbackQueryHandler(rpvp_pvb_target_callback, pattern='^rpvp_pvb_target_', block=False))
    app.add_handler(CommandHandler('games', games_menu, block=False))
    app.add_handler(CommandHandler('active', active_games_command, block=False))
    app.add_handler(CommandHandler('activeall', active_all_games_command, block=False))
    app.add_handler(CommandHandler('reset', reset_recovery_command, block=False))
    app.add_handler(CommandHandler('export', export_command, block=False))
    app.add_handler(CommandHandler(['history', 'hc'], history_command, block=False))
    app.add_handler(CommandHandler('demo', demo_command, block=False))
    app.add_handler(CommandHandler(['transactions', 'tx'], transactions_command, block=False))
    app.add_handler(CommandHandler('transaction', transactions_command, block=False))
    app.add_handler(CommandHandler('serverseed', serverseed_command, block=False))
    app.add_handler(CommandHandler('seed', seed_command, block=False))
    app.add_handler(CommandHandler('rk', rakeback_command, block=False))
    app.add_handler(CommandHandler('mute', mute_command, block=False))
    app.add_handler(CommandHandler('report', report_command, block=False))
    app.add_handler(CommandHandler('translate', translate_command, block=False))
    app.add_handler(CommandHandler('lockall', lockall_command, block=False))
    app.add_handler(CommandHandler('unlockall', unlockall_command, block=False))
    app.add_handler(CallbackQueryHandler(emoji_game_setup_callback, pattern='^egsetup_', block=False))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern='^(main_|back_to_main|deposit_usdt_menu|deposit_coming_soon|my_matches_|my_deals_|my_history_|my_transactions)', block=False))
    app.add_handler(CallbackQueryHandler(games_category_callback, pattern='^games_(category_|emoji_)', block=False))
    app.add_handler(CallbackQueryHandler(play_single_emoji_callback, pattern='^play_single_', block=False))
    app.add_handler(CallbackQueryHandler(tip_confirm_callback, pattern='^(confirm_tip_|cancel_tip_)', block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_mode_callback, pattern='^gc_mode_', block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_rolls_callback, pattern='^gc_rolls_', block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_target_callback, pattern='^gc_target_', block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_accept_callback, pattern='^gc_accept_', block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_playbot_callback, pattern='^gc_playbot_', block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_cancel_callback, pattern='^gc_cancel_', block=False))
    app.add_handler(CallbackQueryHandler(group_challenge_botfirst_callback, pattern='^gc_botfirst_', block=False))
    app.add_handler(CallbackQueryHandler(pvb_cashout_callback, pattern='^pvb_cashout_', block=False))
    app.add_handler(CallbackQueryHandler(xdxw_mode_callback, pattern='^xdxw_mode_|^xdxw_cancel$', block=False))
    app.add_handler(CallbackQueryHandler(xdxw_accept_callback, pattern='^xdxw_accept_', block=False))
    app.add_handler(CallbackQueryHandler(xdxw_playbot_callback, pattern='^xdxw_playbot_', block=False))
    app.add_handler(CallbackQueryHandler(xdxw_bot_first_callback, pattern='^xdxw_bot_first_', block=False))
    app.add_handler(CallbackQueryHandler(xdxw_cancel_match_callback, pattern='^xdxw_cancel_', block=False))
    app.add_handler(CallbackQueryHandler(coinflip_rebet_double_callback, pattern='^coinflip_(rebet|double)_', block=False))
    app.add_handler(CallbackQueryHandler(coinchain_callback, pattern='^coinchain_', block=False))
    app.add_handler(CallbackQueryHandler(game_info_callback, pattern='^game_', block=False))
    app.add_handler(CallbackQueryHandler(game_help_callback, pattern='^(mines_help|tower_help)$', block=False))
    app.add_handler(CallbackQueryHandler(history_page_callback, pattern='^hist_page_', block=False))
    app.add_handler(CallbackQueryHandler(history_view_callback, pattern='^hist_view_', block=False))
    app.add_handler(CallbackQueryHandler(transactions_page_callback, pattern='^txn_page_', block=False))
    app.add_handler(CallbackQueryHandler(transactions_close_callback, pattern='^txn_close_', block=False))
    app.add_handler(CallbackQueryHandler(close_callback, pattern='^close$', block=False))
    app.add_handler(CallbackQueryHandler(clear_confirm_callback, pattern='^(clear|clearall)_confirm_', block=False))
    app.add_handler(CallbackQueryHandler(match_invite_callback, pattern='^(accept_|decline_)', block=False))
    app.add_handler(CallbackQueryHandler(stop_confirm_callback, pattern='^stop_confirm_', block=False))
    app.add_handler(CallbackQueryHandler(pvb_menu_callback, pattern='^pvp_info_', block=False))
    app.add_handler(CallbackQueryHandler(currency_callback, pattern='^(setcurrency_|setdisplay_|noop_cur_header)', block=False))
    app.add_handler(CallbackQueryHandler(language_callback, pattern='^lang_', block=False))
    app.add_handler(CallbackQueryHandler(stats_view_callback, pattern='^stats_(24h|alltime)_', block=False))
    app.add_handler(CallbackQueryHandler(users_navigation_callback, pattern='^users_', block=False))
    app.add_handler(CallbackQueryHandler(price_update_callback, pattern='^price_update_', block=False))
    app.add_handler(CallbackQueryHandler(active_all_navigation_callback, pattern='^activeall_', block=False))
    if helper_app is not None:
        helper_app.add_handler(CallbackQueryHandler(stats_view_callback, pattern='^stats_(24h|alltime)_', block=False))
        helper_app.add_handler(CallbackQueryHandler(price_update_callback, pattern='^price_update_', block=False))

