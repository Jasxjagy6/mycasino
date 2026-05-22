"""Auto-split from bot.py — plugins.games_blackjack."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

@check_banned
@check_maintenance
async def bjsplit_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only test command: deal a split-able blackjack hand for testing the split feature."""
    user = update.effective_user
    if not is_admin(user.id):
        return

    await ensure_user_in_wallets(user.id, user.username, context=context)

    args = update.message.text.strip().split()
    if len(args) != 2:
        await update.message.reply_text("Usage: /bjsplit amount\nExample: /bjsplit 10")
        return

    try:
        bet_amount_usd = float(args[1])
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if bet_amount_usd <= 0:
        await update.message.reply_text("Amount must be positive.")
        return

    user_currency = get_user_currency(user.id)
    currency_symbol = CURRENCY_SYMBOLS.get(user_currency, "$")

    # Force set balance for testing (don't deduct, just credit if needed)
    wallet = ensure_wallet_dict(user.id)
    if wallet.get("USDT", 0) < bet_amount_usd:
        wallet["USDT"] = bet_amount_usd * 2  # Give enough to split
    save_user_data(user.id)

    # Create a deck with guaranteed split-able hand (e.g., 8♠ 8♥)
    deck = create_deck()
    # Find two cards of same rank value and put them at the top
    split_rank = '8'  # Use 8s for a good test hand
    split_suits = ['♠', '♥', '♦', '♣']
    card1 = f"{split_rank}{split_suits[0]}"
    card2 = f"{split_rank}{split_suits[1]}"

    # Remove these cards from deck if present, then insert at top
    deck = [c for c in deck if c != card1 and c != card2]
    deck = [card1, card2] + deck

    player_hand = [deck.pop(0), deck.pop(0)]  # Will be the 8s
    dealer_hand = [deck.pop(0), deck.pop(0)]

    game_id = generate_unique_id("BJS")
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "blackjack",
        "user_id": user.id,
        "bet_amount": bet_amount_usd,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount_usd / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "bet_amount_currency": bet_amount_usd,
        "currency": user_currency,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "deck": deck,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "server_seed": "test_split_server_seed",
        "client_seed": "test_split_client_seed",
        "nonce": 0,
        "doubled": False,
        "test_mode": True  # Mark as test game
    }

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]:
        user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    player_value = calculate_hand_value(player_hand)
    bot_uname = context.bot.username or "Casino"

    # Get player profile picture
    player_profile_pic = await _get_cached_profile_picture(context, user.id)

    # Render initial card image
    bj_image = await async_generate_bj_image(
        player_hand=player_hand,
        dealer_hand=dealer_hand,
        show_dealer_hole=False,
        player_value=player_value,
        player_username=user.username,
        bet_amount=bet_amount_usd,
        bot_username=bot_uname,
        player_profile_pic=player_profile_pic,
    )

    keyboard_buttons = [
        [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_hit_{game_id}"), 'success', peb('hit')),
         apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_stand_{game_id}"), 'danger', peb('stand'))],
    ]
    # Add Double Down button
    keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Double Down", callback_data=f"bj_double_{game_id}"), 'primary', peb('double'))])
    # Add Split button (guaranteed split-able)
    keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Split", callback_data=f"bj_split_{game_id}"), 'primary', peb('deal'))])

    caption = (
        f"{pe('cards')} <b>Blackjack TEST (Split Demo)</b> — ID: <code>{game_id}</code>\n"
        f"{pe('money')} Bet: {currency_symbol}{bet_amount_usd:.2f}\n"
        f"<i>Hand designed for split testing</i>"
    )
    sent = await update.message.reply_photo(
        photo=bj_image,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard_buttons)
    )
    game_sessions[game_id]['message_id'] = sent.message_id
    game_sessions[game_id]['chat_id'] = update.effective_chat.id

@check_banned
@check_maintenance
async def blackjack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("blackjack"):
        await update.message.reply_text(
            "\U0001f527 <b>Blackjack</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    user_currency = get_user_currency(user.id)
    formatted_balance = format_currency(get_active_balance_usd(user.id), user_currency)

    if len(args) != 2:
        await update.message.reply_text(f"Usage: /bj amount\nExample: /bj 5 or /bj all\nYour balance: {formatted_balance}")
        return

    try:
        bet_amount_str = args[1]
        bet_amount_usd, bet_amount_currency, currency = parse_bet_amount(bet_amount_str, user.id)
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a valid number or 'all'.")
        return

    if not await check_bet_limits(update, bet_amount_usd, 'blackjack'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount_usd)
    except ValueError:
        await send_insufficient_balance_message(update, f"{pe('cross')} You don't have enough balance. Your balance: {formatted_balance}")
        return
    save_user_data(user.id)

    # Use user's provably fair seeds
    seeds = get_user_seeds(user.id)

    # Create deck and shuffle deterministically using Fisher-Yates
    deck = create_deck()
    for i in range(len(deck) - 1, 0, -1):
        j = get_provably_fair_result(seeds["server_seed"], seeds["client_seed"], seeds["nonce"] + i, i + 1)
        deck[i], deck[j] = deck[j], deck[i]

    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    game_id = generate_unique_id("BJ")
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "blackjack",
        "user_id": user.id,
        "bet_amount": bet_amount_usd,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount_usd / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "bet_amount_currency": bet_amount_currency,
        "currency": currency,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "deck": deck,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "server_seed": seeds["server_seed"],
        "client_seed": seeds["client_seed"],
        "nonce": seeds["nonce"],
        "doubled": False
    }
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)


    player_value = calculate_hand_value(player_hand)
    dealer_show_card = dealer_hand[0]

    hand_text = format_hand("Your hand", player_hand, player_value)
    dealer_text = f"Dealer shows: {dealer_show_card}\n"

    currency_symbol = CURRENCY_SYMBOLS.get(currency, "$")
    formatted_bet = f"{currency_symbol}{bet_amount_currency:.2f}"

    if player_value == 21:
        dealer_value = calculate_hand_value(dealer_hand)
        game_sessions[game_id]['status'] = 'completed'
        game_sessions[game_id]['win'] = True
        increment_user_nonce(user.id)

        # Store provably fair record
        game = game_sessions[game_id]
        store_provably_fair_record(game_id, "blackjack", game["server_seed"], game["client_seed"], game["nonce"],
                                   result_data=f"Player: {player_value}, Dealer: {dealer_value}")

        # Add provably fair button
        keyboard = [[await create_provably_fair_button(game_id, context)]]
        bot_uname = context.bot.username or "Casino"

        if dealer_value == 21:
            credit_wallet(user.id, bet_amount_usd)
            # Push still counts towards leaderboard wagering
            await update_stats_on_bet(user.id, game_id, bet_amount_usd, False, multiplier=0, context=context)
            save_user_data(user.id)
            bj_image = await async_generate_bj_image(
                player_hand=player_hand,
                dealer_hand=dealer_hand,
                show_dealer_hole=True,
                player_value=player_value,
                dealer_value=dealer_value,
                player_username=user.username,
                bet_amount=bet_amount_usd,
                bot_username=bot_uname,
                result_text="Push - Tie",
                result_color=BJ_PUSH_COLOR,
            )
            caption = (
                f"{pe('push')} Push! Both have blackjack. Bet returned: {formatted_bet}\n"
                f"Game ID: <code>{game_id}</code>"
            )
            await update.message.reply_photo(
                photo=bj_image, caption=caption, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Blackjack pays 2.425x (3% house edge)
            winnings_usd = bet_amount_usd * 2.425
            winnings_currency = bet_amount_currency * 2.425
            credit_wallet(user.id, winnings_usd)
            await update_stats_on_bet(user.id, game_id, bet_amount_usd, True, multiplier=2.425, context=context)
            update_pnl(user.id)
            save_user_data(user.id)
            bj_image = await async_generate_bj_image(
                player_hand=player_hand,
                dealer_hand=dealer_hand,
                show_dealer_hole=True,
                player_value=player_value,
                dealer_value=dealer_value,
                player_username=user.username,
                bet_amount=bet_amount_usd,
                bot_username=bot_uname,
                result_text="Blackjack!",
                result_color=BJ_WIN_COLOR,
            )
            caption = (
                f"{pe('win')} Blackjack! You win {currency_symbol}{winnings_currency:.2f}!\n"
                f"Game ID: <code>{game_id}</code>"
            )
            await update.message.reply_photo(
                photo=bj_image, caption=caption, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    # Get bot username for watermark
    bot_uname = context.bot.username or "Casino"

    # Get player profile picture
    player_profile_pic = await _get_cached_profile_picture(context, user.id)

    # Render initial card image
    player_value = calculate_hand_value(player_hand)
    bj_image = await async_generate_bj_image(
        player_hand=player_hand,
        dealer_hand=dealer_hand,
        show_dealer_hole=False,
        player_value=player_value,
        player_username=user.username,
        bet_amount=bet_amount_usd,
        bot_username=bot_uname,
        player_profile_pic=player_profile_pic,
    )

    keyboard_buttons = [
        [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_hit_{game_id}"), 'success', peb('hit')),
         apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_stand_{game_id}"), 'danger', peb('stand'))],
    ]
    # Add Double Down button if eligible
    if len(player_hand) == 2 and get_active_balance_usd(user.id) >= bet_amount_usd:
        keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Double Down", callback_data=f"bj_double_{game_id}"), 'primary', peb('double'))])
    # Add Split button if eligible (two cards of same rank value)
    if can_split_hand(player_hand) and get_active_balance_usd(user.id) >= bet_amount_usd:
        keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Split", callback_data=f"bj_split_{game_id}"), 'primary', peb('deal'))])

    caption = (
        f"{pe('cards')} <b>Blackjack</b> — ID: <code>{game_id}</code>\n"
        f"{pe('money')} Bet: {formatted_bet}"
    )
    sent = await update.message.reply_photo(
        photo=bj_image,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard_buttons)
    )
    game_sessions[game_id]['message_id'] = sent.message_id
    game_sessions[game_id]['chat_id'] = update.effective_chat.id

def _bj_round_rect(draw, bbox, radius, fill, outline=None, outline_width=1):
    """Draw a filled rounded rectangle."""
    x0, y0, x1, y1 = bbox
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill,
                            outline=outline, width=outline_width)

def _bj_get_font(size: int):
    """Try to load a system font; fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _bj_draw_card(draw, x, y, rank: str, suit: str):
    """Draw a single face-up playing card at position (x, y)."""
    # Card shadow
    draw.rounded_rectangle([x+3, y+3, x+BJ_CARD_W+3, y+BJ_CARD_H+3],
                            radius=BJ_CARD_RADIUS, fill=(0, 0, 0, 80))
    # Card body
    draw.rounded_rectangle([x, y, x+BJ_CARD_W, y+BJ_CARD_H],
                            radius=BJ_CARD_RADIUS, fill=BJ_CARD_BG,
                            outline=(180, 180, 180), width=1)
    color = BJ_RED if suit in ('♥', '♦') else BJ_BLACK_SUIT

    font_rank = _bj_get_font(22)
    font_suit = _bj_get_font(28)
    font_center = _bj_get_font(36)

    # Top-left rank + suit
    draw.text((x+6, y+4), rank, font=font_rank, fill=color)
    draw.text((x+6, y+26), suit, font=font_rank, fill=color)

    # Center suit (large)
    cx = x + BJ_CARD_W // 2
    cy = y + BJ_CARD_H // 2
    suit_w = draw.textlength(suit, font=font_center)
    draw.text((cx - suit_w // 2, cy - 20), suit, font=font_center, fill=color)

    # Bottom-right rank + suit
    draw.text((x + BJ_CARD_W - 22, y + BJ_CARD_H - 42), rank, font=font_rank, fill=color)
    draw.text((x + BJ_CARD_W - 22, y + BJ_CARD_H - 22), suit, font=font_rank, fill=color)

def _bj_draw_hidden_card(draw, x, y):
    """Draw a face-down (hidden) card at position (x, y)."""
    draw.rounded_rectangle([x+3, y+3, x+BJ_CARD_W+3, y+BJ_CARD_H+3],
                            radius=BJ_CARD_RADIUS, fill=(0, 0, 0, 80))
    draw.rounded_rectangle([x, y, x+BJ_CARD_W, y+BJ_CARD_H],
                            radius=BJ_CARD_RADIUS, fill=BJ_CARD_BACK,
                            outline=(80, 80, 160), width=2)
    # Card back pattern (diagonal lines)
    for i in range(-BJ_CARD_H, BJ_CARD_W, 12):
        draw.line([(x + i, y), (x + i + BJ_CARD_H, y + BJ_CARD_H)],
                  fill=(40, 60, 140), width=1)
    # Center logo
    cx, cy = x + BJ_CARD_W // 2, y + BJ_CARD_H // 2
    font = _bj_get_font(20)
    draw.text((cx - 8, cy - 12), "?", font=font, fill=(100, 120, 220))

def _bj_parse_card(card_str: str):
    """Parse card string like 'A♠', '10♥', 'K♦' into (rank, suit)."""
    if len(card_str) >= 2:
        # suit is always the last character
        return card_str[:-1], card_str[-1]
    return card_str, "?"

def create_deck():
    """Create and cryptographically securely shuffle a 52-card deck."""
    deck = [f"{rank}{suit}" for suit in SUITS for rank in RANKS]
    _secure_shuffle(deck)  # Use cryptographic shuffle
    return deck

def calculate_hand_value(hand):
    value = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        if rank == 'A':
            aces += 1
            value += 11
        elif rank in ['J', 'Q', 'K']:
            value += 10
        else:
            value += int(rank)
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def format_hand(title, hand, value):
    cards_str = " ".join(hand)
    return f"{title}: {cards_str} (Value: {value})"

def can_split_hand(hand):
    """Check if a blackjack hand can be split (two cards of same rank).
    Returns True if the hand has exactly 2 cards with the same rank value.
    Note: 10, J, Q, K all count as 10-value cards and can be split."""
    if len(hand) != 2:
        return False
    rank1 = hand[0][:-1]  # Get rank part (e.g., 'A', 'K', '10')
    rank2 = hand[1][:-1]
    # Convert face cards to their numeric value for comparison
    def rank_value(r):
        if r in ['J', 'Q', 'K']:
            return 10
        return int(r) if r != 'A' else 11
    return rank_value(rank1) == rank_value(rank2)

@check_banned
@check_maintenance
async def blackjack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    if not query.data.startswith("bj_"):
        try: await query.answer()
        except: pass
        return

    # Global dedup: ignore duplicate taps
    if not await _acquire_callback(query.id):
        try: await query.answer()
        except: pass
        return

    # Flood guard: prevent same user same action within 0.5s
    if not _check_user_action_flood(user.id, query.data, _USER_ACTION_COOLDOWN_GAME):
        try: await query.answer("⏳ Too fast!", show_alert=False)
        except: pass
        _release_callback(query.id)
        return

    await query.answer()
    current_task = asyncio.current_task()
    if current_task is not None:
        current_task.add_done_callback(lambda _task, qid=query.id: _release_callback(qid))

    parts = query.data.split("_")
    
    # Validate callback format
    if len(parts) < 3:
        await query.answer("Invalid callback data!", show_alert=True)
        return

    # Parse action correctly for both normal and split callbacks
    # Normal: bj_hit_GAMEID, bj_stand_GAMEID, bj_double_GAMEID, bj_split_GAMEID
    # Split hand actions: bj_split_hit_GAMEID_0, bj_split_stand_GAMEID_0, bj_split_double_GAMEID_0
    if parts[1] == "split":
        # Could be either:
        # - bj_split_GAMEID (initial split action) - 3 parts
        # - bj_split_hit_GAMEID_0 (split hand action) - 5 parts
        if len(parts) == 3:
            # Initial split action
            action = "split"
            game_id = parts[2]
            hand_index_for_callback = None
        elif len(parts) >= 5:
            # Split hand action
            action = f"split_{parts[2]}"  # "split_hit", "split_stand", "split_double"
            game_id = parts[3]
            hand_index_for_callback = int(parts[4])  # Store for later use
        else:
            await query.answer("Invalid split callback!", show_alert=True)
            return
    else:
        action = parts[1]  # "hit", "stand", "double"
        game_id = parts[2]
        hand_index_for_callback = None

    game = game_sessions.get(game_id)

    if not game:
        await query.edit_message_text("Game not found or already finished.")
        return

    # Game interaction security - only the game owner can interact
    if user.id != game.get('user_id'):
        await query.answer("This is not your game!", show_alert=True)
        return

    if game.get('status') != 'active':
        await query.edit_message_text("This game is already finished.")
        return

    bot_uname = context.bot.username or "Casino"

    if action == "hit":
        card = game["deck"].pop()
        game["player_hand"].append(card)
        player_value = calculate_hand_value(game["player_hand"])

        if player_value > 21:
            game["status"] = 'completed'
            game["win"] = False
            increment_user_nonce(user.id)
            await update_stats_on_bet(user.id, game_id, game["bet_amount"], False, context=context)
            update_pnl(user.id)
            save_user_data(user.id)

            # Store provably fair record
            store_provably_fair_record(game_id, "blackjack", game["server_seed"], game["client_seed"], game["nonce"],
                                       result_data=f"Player busted: {player_value}")

            # Add provably fair button
            keyboard = [[await create_provably_fair_button(game_id, context)]]

            bj_image = await async_generate_bj_image(
                player_hand=game["player_hand"],
                dealer_hand=game["dealer_hand"],
                show_dealer_hole=False,
                player_value=player_value,
                player_username=user.username,
                bet_amount=game["bet_amount"],
                bot_username=bot_uname,
                player_profile_pic=await _get_cached_profile_picture(context, user.id),
                result_text="Bust!",
                result_color=BJ_LOSE_COLOR,
            )
            caption = (
                f"{pe('bust')} <b>Bust!</b> — ID: <code>{game_id}</code>\n"
                f"You lose {pe('cross')} ${game['bet_amount']:.2f}"
            )
            await query.edit_message_media(
                media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif player_value == 21:
            await handle_dealer_turn(query, context, game_id, bot_uname)
        else:
            # Continue game
            bj_image = await async_generate_bj_image(
                player_hand=game["player_hand"],
                dealer_hand=game["dealer_hand"],
                show_dealer_hole=False,
                player_value=player_value,
                player_username=user.username,
                bet_amount=game["bet_amount"],
                bot_username=bot_uname,
                player_profile_pic=await _get_cached_profile_picture(context, user.id),
            )
            keyboard_buttons = [
                [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_hit_{game_id}"), 'success', peb('hit')),
                 apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_stand_{game_id}"), 'danger', peb('stand'))]
            ]
            caption = (
                f"{pe('cards')} <b>Blackjack</b> — ID: <code>{game_id}</code>\n"
                f"{pe('money')} Bet: ${game['bet_amount']:.2f}"
            )
            await query.edit_message_media(
                media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
            )

    elif action == "stand":
        await handle_dealer_turn(query, context, game_id, bot_uname)

    elif action == "double":
        if get_active_balance_usd(user.id) < game["bet_amount"]:
            # Show alert with deposit option
            await query.answer(f"{pe('cross')} Not enough balance to double down!", show_alert=True)
            # Edit message to show back button
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Back to Game", callback_data=f"bj_continue_{game_id}")]
            ])
            await query.edit_message_text(
                f"{pe('cross')} You don't have enough balance to double down.\n\n"
                f"Required: ${game['bet_amount']:.2f}\n"
                f"Your balance: ${get_active_balance_usd(user.id):.2f}\n\n"
                f"Please deposit to continue.",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            return

        try:
            await deduct_wallet_safe(user.id, game["bet_amount"])
        except ValueError:
            await query.answer("Insufficient balance for double down!", show_alert=True)
            return
        game["bet_amount"] *= 2
        game["doubled"] = True
        save_user_data(user.id)

        card = game["deck"].pop()
        game["player_hand"].append(card)
        player_value = calculate_hand_value(game["player_hand"])

        if player_value > 21:
            game["status"] = 'completed'
            game["win"] = False
            increment_user_nonce(user.id)
            # On double down loss, the original bet amount is what's recorded for stats
            await update_stats_on_bet(user.id, game_id, game["bet_amount"]/2, False, context=context)
            update_pnl(user.id)
            save_user_data(user.id)

            # Store provably fair record
            store_provably_fair_record(game_id, "blackjack", game["server_seed"], game["client_seed"], game["nonce"],
                                       result_data=f"Double down - Player busted: {player_value}")

            # Add provably fair button
            keyboard = [[await create_provably_fair_button(game_id, context)]]

            bj_image = await async_generate_bj_image(
                player_hand=game["player_hand"],
                dealer_hand=game["dealer_hand"],
                show_dealer_hole=False,
                player_value=player_value,
                player_username=user.username,
                bet_amount=game["bet_amount"],
                bot_username=bot_uname,
                player_profile_pic=await _get_cached_profile_picture(context, user.id),
                result_text="Bust!",
                result_color=BJ_LOSE_COLOR,
            )
            caption = (
                f"{pe('bust')} <b>Bust! (Doubled Down)</b> — ID: <code>{game_id}</code>\n"
                f"You lose {pe('cross')} ${game['bet_amount']:.2f}"
            )
            await query.edit_message_media(
                media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await handle_dealer_turn(query, context, game_id, bot_uname)

    elif action == "continue":
        # Continue/back button - show current game state
        if game.get('split'):
            # Split game - show current active hand
            split_hands = game['split_hands']
            split_bets = game['split_bets']
            current_hand_index = game.get('current_hand_index', 0)
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
                bot_username=bot_uname,
                player_profile_pic=await _get_cached_profile_picture(context, user.id),
                split_hands=split_hands,
                split_active_hand=current_hand_index,
                split_bets=split_bets,
                split_results=game.get('split_results', []),
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
            await query.edit_message_media(
                media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
            )
        else:
            # Regular game
            player_value = calculate_hand_value(game['player_hand'])
            bj_image = await async_generate_bj_image(
                player_hand=game['player_hand'],
                dealer_hand=game['dealer_hand'],
                show_dealer_hole=False,
                player_value=player_value,
                player_username=user.username,
                bet_amount=game['bet_amount'],
                bot_username=bot_uname,
                player_profile_pic=await _get_cached_profile_picture(context, user.id),
            )
            keyboard_buttons = [
                [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_hit_{game_id}"), 'success', peb('hit')),
                 apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_stand_{game_id}"), 'danger', peb('stand'))]
            ]
            if len(game['player_hand']) == 2 and get_active_balance_usd(user.id) >= game['bet_amount']:
                keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Double Down", callback_data=f"bj_double_{game_id}"), 'primary', peb('double'))])
            if can_split_hand(game['player_hand']) and get_active_balance_usd(user.id) >= game['bet_amount']:
                keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Split", callback_data=f"bj_split_{game_id}"), 'primary', peb('deal'))])

            caption = (
                f"{pe('cards')} <b>Blackjack</b> — ID: <code>{game_id}</code>\n"
                f"{pe('money')} Bet: ${game['bet_amount']:.2f}"
            )
            await query.edit_message_media(
                media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
            )

    elif action == "split":
        # Split feature - only allowed on initial 2-card hand with matching rank values
        if not can_split_hand(game["player_hand"]):
            await query.answer("Cannot split this hand!", show_alert=True)
            return

        # Check balance for split (need to match original bet)
        original_bet = game["bet_amount"]
        if get_active_balance_usd(user.id) < original_bet:
            await query.answer(f"{pe('cross')} Not enough balance to split!", show_alert=True)
            return

        # Deduct the split bet atomically
        try:
            await deduct_wallet_safe(user.id, original_bet)
        except ValueError:
            await query.answer("Insufficient balance for split!", show_alert=True)
            return
        save_user_data(user.id)

        # Create two separate hands from the split
        first_card = game["player_hand"][0]
        second_card = game["player_hand"][1]

        # Deal one card to each hand
        third_card = game["deck"].pop()
        fourth_card = game["deck"].pop()

        hand1 = [first_card, third_card]
        hand2 = [second_card, fourth_card]

        # Store split hands in game state
        game["split"] = True
        game["split_hands"] = [hand1, hand2]
        game["split_bets"] = [original_bet, original_bet]  # Each hand has the original bet
        game["current_hand_index"] = 0  # Start with first hand
        game["split_results"] = []  # Will store results for each hand

        # Show split image with both hands, highlighting active hand (hand 1)
        bj_image = await async_generate_bj_image(
            player_hand=hand1,
            dealer_hand=game["dealer_hand"],
            show_dealer_hole=False,
            player_value=calculate_hand_value(hand1),
            player_username=user.username,
            bet_amount=original_bet * 2,
            bot_username=bot_uname,
            player_profile_pic=await _get_cached_profile_picture(context, user.id),
            split_hands=[hand1, hand2],
            split_active_hand=0,
            split_bets=[original_bet, original_bet],
            split_results=[],
        )

        keyboard_buttons = [
            [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_split_hit_{game_id}_0"), 'success', peb('hit')),
             apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_split_stand_{game_id}_0"), 'danger', peb('stand'))]
        ]
        # Can double on split hand if only 2 cards and has balance
        if len(hand1) == 2 and get_active_balance_usd(user.id) >= original_bet:
            keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Double", callback_data=f"bj_split_double_{game_id}_0"), 'primary', peb('double'))])

        caption = (
            f"{pe('cards')} <b>Blackjack - Split</b> — ID: <code>{game_id}</code>\n"
            f"{pe('money')} Bet per hand: ${original_bet:.2f}\n"
            f"Playing Hand 1 of 2"
        )
        await query.edit_message_media(
            media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
            reply_markup=InlineKeyboardMarkup(keyboard_buttons)
        )

    elif action == "split_hit":
        # Handle hit on split hand: bj_split_hit_{game_id}_{hand_index}
        hand_index = hand_index_for_callback

        # Draw card to current split hand
        card = game["deck"].pop()
        game["split_hands"][hand_index].append(card)
        hand_value = calculate_hand_value(game["split_hands"][hand_index])

        # Check for bust
        if hand_value > 21:
            # This hand busted, move to next hand or finish
            game["split_results"].append({"hand": hand_index, "value": hand_value, "status": "bust"})
            await _play_next_split_hand(query, context, game_id, hand_index + 1, bot_uname)
        elif hand_value == 21:
            # Stand automatically on 21
            game["split_results"].append({"hand": hand_index, "value": hand_value, "status": "21"})
            await _play_next_split_hand(query, context, game_id, hand_index + 1, bot_uname)
        else:
            # Continue playing this hand - show both hands with active highlighted
            bj_image = await async_generate_bj_image(
                player_hand=game["split_hands"][hand_index],
                dealer_hand=game["dealer_hand"],
                show_dealer_hole=False,
                player_value=hand_value,
                player_username=user.username,
                bet_amount=sum(game["split_bets"]),
                bot_username=bot_uname,
                player_profile_pic=await _get_cached_profile_picture(context, user.id),
                split_hands=game["split_hands"],
                split_active_hand=hand_index,
                split_bets=game["split_bets"],
                split_results=game.get("split_results", []),
            )
            keyboard_buttons = [
                [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_split_hit_{game_id}_{hand_index}"), 'success', peb('hit')),
                 apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_split_stand_{game_id}_{hand_index}"), 'danger', peb('stand'))]
            ]
            if len(game["split_hands"][hand_index]) == 2 and get_active_balance_usd(user.id) >= game["split_bets"][hand_index]:
                keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Double", callback_data=f"bj_split_double_{game_id}_{hand_index}"), 'primary', peb('double'))])

            caption = (
                f"{pe('cards')} <b>Blackjack - Split</b> — ID: <code>{game_id}</code>\n"
                f"{pe('money')} Bet per hand: ${game['split_bets'][hand_index]:.2f}\n"
                f"Playing Hand {hand_index + 1} of {len(game['split_hands'])}"
            )
            await query.edit_message_media(
                media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
            )

    elif action == "split_stand":
        hand_index = hand_index_for_callback

        hand_value = calculate_hand_value(game["split_hands"][hand_index])
        game["split_results"].append({"hand": hand_index, "value": hand_value, "status": "stand"})
        await _play_next_split_hand(query, context, game_id, hand_index + 1, bot_uname)

    elif action == "split_double":
        hand_index = hand_index_for_callback
        current_bet = game["split_bets"][hand_index]

        # Deduct double-down stake atomically (per-user lock).
        try:
            await deduct_wallet_safe(user.id, current_bet)
        except ValueError:
            await query.answer(f"{pe('cross')} Not enough balance to double!", show_alert=True)
            return
        game["split_bets"][hand_index] *= 2
        save_user_data(user.id)

        # Deal one card and stand
        card = game["deck"].pop()
        game["split_hands"][hand_index].append(card)
        hand_value = calculate_hand_value(game["split_hands"][hand_index])

        if hand_value > 21:
            game["split_results"].append({"hand": hand_index, "value": hand_value, "status": "bust"})
        else:
            game["split_results"].append({"hand": hand_index, "value": hand_value, "status": "doubled"})

        await _play_next_split_hand(query, context, game_id, hand_index + 1, bot_uname)

async def _play_next_split_hand(query, context, game_id, next_hand_index, bot_uname):
    """Play the next split hand or resolve the game if all hands are done."""
    game = game_sessions[game_id]
    user_id = game["user_id"]

    if next_hand_index >= len(game["split_hands"]):
        # All hands played, resolve split game
        await _resolve_split_game(query, context, game_id, bot_uname)
        return

    # Move to next hand
    game["current_hand_index"] = next_hand_index
    hand = game["split_hands"][next_hand_index]
    hand_value = calculate_hand_value(hand)
    current_bet = game["split_bets"][next_hand_index]

    # Show split image with both hands, highlighting the active one
    bj_image = await async_generate_bj_image(
        player_hand=hand,
        dealer_hand=game["dealer_hand"],
        show_dealer_hole=False,
        player_value=hand_value,
        player_username=query.from_user.username,
        bet_amount=sum(game["split_bets"]),
        bot_username=bot_uname,
        player_profile_pic=await _get_cached_profile_picture(context, user_id),
        split_hands=game["split_hands"],
        split_active_hand=next_hand_index,
        split_bets=game["split_bets"],
        split_results=game.get("split_results", []),
    )

    keyboard_buttons = [
        [apply_button_style(InlineKeyboardButton("Hit", callback_data=f"bj_split_hit_{game_id}_{next_hand_index}"), 'success', peb('hit')),
         apply_button_style(InlineKeyboardButton("Stand", callback_data=f"bj_split_stand_{game_id}_{next_hand_index}"), 'danger', peb('stand'))]
    ]
    if len(hand) == 2 and get_active_balance_usd(user_id) >= current_bet:
        keyboard_buttons.append([apply_button_style(InlineKeyboardButton("Double", callback_data=f"bj_split_double_{game_id}_{next_hand_index}"), 'primary', peb('double'))])

    caption = (
        f"{pe('cards')} <b>Blackjack - Split</b> — ID: <code>{game_id}</code>\n"
        f"{pe('money')} Bet per hand: ${current_bet:.2f}\n"
        f"Playing Hand {next_hand_index + 1} of {len(game['split_hands'])}"
    )
    await query.edit_message_media(
        media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
        reply_markup=InlineKeyboardMarkup(keyboard_buttons)
    )

async def _resolve_split_game(query, context, game_id, bot_uname):
    """Resolve all split hands against dealer."""
    game = game_sessions[game_id]
    user_id = game["user_id"]

    # Dealer plays
    while calculate_hand_value(game["dealer_hand"]) < 17:
        game["dealer_hand"].append(game["deck"].pop())

    dealer_value = calculate_hand_value(game["dealer_hand"])
    total_wagered = 0
    total_winnings = 0
    results = []

    for i, (hand, bet) in enumerate(zip(game["split_hands"], game["split_bets"])):
        player_value = calculate_hand_value(hand)
        total_wagered += bet

        # Check if this hand already busted from earlier
        existing_result = None
        for r in game.get("split_results", []):
            if r["hand"] == i:
                existing_result = r
                break

        if existing_result and existing_result["status"] == "bust":
            results.append(f"Hand {i+1}: Bust (-{dformat(bet)})")
            continue

        if dealer_value > 21:
            # Dealer busted - hand wins
            winnings = bet * 1.94
            total_winnings += winnings
            credit_wallet(user_id, winnings)
            results.append(f"Hand {i+1}: Win +{dformat(winnings)}")
            game['win'] = True
        elif player_value > dealer_value:
            winnings = bet * 1.94
            total_winnings += winnings
            credit_wallet(user_id, winnings)
            results.append(f"Hand {i+1}: Win +{dformat(winnings)}")
            game['win'] = True
        elif player_value < dealer_value:
            results.append(f"Hand {i+1}: Loss (-{dformat(bet)})")
            if not game.get('win'):
                game['win'] = False
        else:
            # Push
            credit_wallet(user_id, bet)
            total_winnings += bet
            results.append(f"Hand {i+1}: Push")
            if game.get('win') is None:
                game['win'] = None

    update_pnl(user_id)

    # Update stats for original bet (average across split hands)
    avg_bet = total_wagered / len(game["split_hands"])
    has_win = any("Win" in r for r in results)
    await update_stats_on_bet(user_id, game_id, avg_bet, has_win, multiplier=1.94 if has_win else 0, context=context)

    save_user_data(user_id)
    game["status"] = 'completed'
    increment_user_nonce(user_id)

    # Store provably fair record
    store_provably_fair_record(game_id, "blackjack", game["server_seed"], game["client_seed"], game["nonce"],
                               result_data=f"Split - Player hands: {results}, Dealer: {dealer_value}")

    # Build result text
    result_lines = [f"{pe('cards')} <b>Blackjack - Split Result</b> — ID: <code>{game_id}</code>", ""]
    for i, hand in enumerate(game["split_hands"]):
        hval = calculate_hand_value(hand)
        result_lines.append(f"Hand {i+1}: {' '.join(hand)} = {hval}")
    result_lines.append(f"Dealer: {' '.join(game['dealer_hand'])} = {dealer_value}")
    result_lines.append("")

    net = total_winnings - total_wagered
    if net > 0:
        result_lines.append(f"{pe('win')} Net Win: +${net:.2f}")
    elif net < 0:
        result_lines.append(f"{pe('lose')} Net Loss: -${abs(net):.2f}")
    else:
        result_lines.append(f"{pe('push')} Net: $0.00 (Push)")

    result_text = "\n".join(result_lines)

    # Generate final image showing all hands with dealer cards revealed
    bj_image = await async_generate_bj_image(
        player_hand=game["split_hands"][0],
        dealer_hand=game["dealer_hand"],
        show_dealer_hole=True,
        player_value=calculate_hand_value(game["split_hands"][0]),
        dealer_value=dealer_value,
        player_username=None,
        bet_amount=total_wagered,
        bot_username=bot_uname,
        player_profile_pic=await _get_cached_profile_picture(context, user_id),
        result_text="Split Complete",
        result_color=BJ_WIN_COLOR if net > 0 else (BJ_LOSE_COLOR if net < 0 else BJ_PUSH_COLOR),
        split_hands=game["split_hands"],
        split_bets=game["split_bets"],
        split_results=game.get("split_results", []),
    )

    # Add provably fair button
    keyboard = [[await create_provably_fair_button(game_id, context)]]

    await query.edit_message_media(
        media=InputMediaPhoto(media=bj_image, caption=result_text, parse_mode=ParseMode.HTML),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_dealer_turn(query, context, game_id, bot_uname: str = "Casino"):
    game = game_sessions[game_id]
    user_id = game["user_id"]
    original_bet = game["bet_amount"] / 2 if game["doubled"] else game["bet_amount"]
    double_text = " - Doubled Down" if game["doubled"] else ""

    while calculate_hand_value(game["dealer_hand"]) < 17:
        game["dealer_hand"].append(game["deck"].pop())

    player_value = calculate_hand_value(game["player_hand"])
    dealer_value = calculate_hand_value(game["dealer_hand"])

    if dealer_value > 21:
        # Regular win pays 1.94x (3% house edge)
        winnings = game["bet_amount"] * 1.94
        credit_wallet(user_id, winnings)
        result_text_plain = "Dealer Busts! You Win!"
        # NOTE: must use the local `user_id` parameter — there is no `user`
        # object in this function's scope.  Using `user.id` here previously
        # raised NameError *after* credit_wallet() had already credited the
        # win, leaving the game stuck in 'active' status with the player's
        # balance updated but no message edit and no completion (#blackjack-stand-bug).
        result_pe_text = f"{pe('win')} Dealer busts! You win {format_for_user(user_id, winnings)}!"
        result_color_tuple = BJ_WIN_COLOR
        game['win'] = True
        await update_stats_on_bet(user_id, game_id, original_bet, True, multiplier=1.94, context=context)
    elif dealer_value > player_value:
        result_text_plain = "Dealer Wins"
        result_pe_text = f"{pe('lose')} Dealer wins with {dealer_value}. You lose ${game['bet_amount']:.2f}"
        result_color_tuple = BJ_LOSE_COLOR
        game['win'] = False
        await update_stats_on_bet(user_id, game_id, original_bet, False, context=context)
    elif player_value > dealer_value:
        # Regular win pays 1.94x (3% house edge)
        winnings = game["bet_amount"] * 1.94
        credit_wallet(user_id, winnings)
        result_text_plain = "You Win!"
        result_pe_text = f"{pe('win')} You win! {dformat(winnings)}"
        result_color_tuple = BJ_WIN_COLOR
        game['win'] = True
        await update_stats_on_bet(user_id, game_id, original_bet, True, multiplier=1.94, context=context)
    else:
        credit_wallet(user_id, game["bet_amount"])
        result_text_plain = "Push - Tie"
        result_pe_text = f"{pe('push')} Push! Bet returned."
        result_color_tuple = BJ_PUSH_COLOR
        game['win'] = None # No win or loss
        # Push still counts towards leaderboard wagering
        await update_stats_on_bet(user_id, game_id, original_bet, False, multiplier=0, context=context)

    # Finalise the game state FIRST so a follow-up exception (telegram
    # timeout, image render failure, etc.) cannot leave the session
    # stuck in 'active' with the wallet already credited.
    update_pnl(user_id)
    save_user_data(user_id)
    game["status"] = 'completed'
    increment_user_nonce(user_id)

    # Store provably fair record
    try:
        store_provably_fair_record(
            game_id, "blackjack", game["server_seed"], game["client_seed"], game["nonce"],
            result_data=f"Player: {player_value}, Dealer: {dealer_value}",
        )
    except Exception as exc:  # pragma: no cover - PF record is best-effort
        logging.warning(f"blackjack: failed to store PF record for {game_id}: {exc}")

    # Add provably fair button
    keyboard = [[await create_provably_fair_button(game_id, context)]]

    try:
        bj_image = await async_generate_bj_image(
            player_hand=game["player_hand"],
            dealer_hand=game["dealer_hand"],
            show_dealer_hole=True,
            player_value=player_value,
            dealer_value=dealer_value,
            player_username=None,
            bet_amount=game["bet_amount"],
            bot_username=bot_uname,
            player_profile_pic=await _get_cached_profile_picture(context, user_id),
            result_text=result_text_plain,
            result_color=result_color_tuple,
        )
        caption = (
            f"{pe('cards')} <b>Blackjack{double_text}</b> — ID: <code>{game_id}</code>\n\n"
            f"{result_pe_text}"
        )
        await query.edit_message_media(
            media=InputMediaPhoto(media=bj_image, caption=caption, parse_mode=ParseMode.HTML),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as exc:
        # Game is already completed and wallet already settled — the only
        # thing left is the on-screen update.  Fall back to a plain-text
        # caption so the player sees the final result instead of being
        # stuck on the in-progress card image.
        logging.error(
            f"blackjack: failed to edit final media for game {game_id}: {exc}",
            exc_info=True,
        )
        try:
            await query.edit_message_caption(
                caption=(
                    f"{pe('cards')} <b>Blackjack{double_text}</b> — ID: <code>{game_id}</code>\n\n"
                    f"{result_pe_text}"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception:
            try:
                await query.message.reply_text(
                    f"{pe('cards')} Blackjack{double_text} — Game <code>{game_id}</code> finished.\n\n{result_pe_text}",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

def get_card_name(card_value, with_emoji=True):
    """Convert card value to name, optionally with emoji"""
    card_names = {
        1: "Ace (A)", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7",
        8: "8", 9: "9", 10: "10", 11: "Jack (J)", 12: "Queen (Q)", 13: "King (K)"
    }
    name = card_names.get(card_value, str(card_value))

    if with_emoji and card_value in CARD_EMOJIS:
        emoji = CARD_EMOJIS[card_value]
        return f"{name} {emoji}"

    return name

@check_banned
@check_maintenance
async def pf_verify_blackjack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start blackjack verification process"""
    query = update.callback_query
    await query.answer()

    context.user_data['pf_verify_game'] = 'blackjack'

    await query.edit_message_text(
        f"{pe('cards')} <b>Verify Blackjack Result</b>\n\n"
        f"I'll calculate the shuffled deck for you!\n\n"
        f"Please enter the <b>Server Seed</b> (revealed after rotation):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="pf_verify_cancel")]])
    )

    return PF_VERIFY_INPUT_SERVER_SEED

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler(['bj', 'blackjack'], blackjack_command, block=False))
    app.add_handler(CommandHandler('bjsplit', bjsplit_test_command, block=False))
    app.add_handler(CallbackQueryHandler(blackjack_callback, pattern='^bj_', block=False))

