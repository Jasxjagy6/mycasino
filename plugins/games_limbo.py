"""Auto-split from bot.py — plugins.games_limbo."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def get_limbo_multiplier(server_seed, client_seed, nonce):
    """
    Generate a provably fair Limbo multiplier using Stake.com's algorithm.
    Returns a multiplier between 1.00 and 1000.00.

    Algorithm:
    - Uses first 52 bits of SHA256 hash as random seed
    - Converts to range [1, 100] for percentage (uniform distribution)
    - Applies formula: house_edge_multiplier / random_percentage
    - With house_edge_multiplier=92:
      * P(X >= 2) = P(92/random_percentage >= 2) = P(random_percentage <= 46)
      * Since random_percentage is uniformly distributed in [1, 100]:
      * P(random_percentage <= 46) = 46/100 = 46%
    - Higher multipliers have exponentially lower chances (e.g., P(X >= 10) ≈ 9.2%)
    """
    hash_result = create_hash(server_seed, client_seed, nonce)

    # Use first 13 hex characters (52 bits) for precision
    hex_value = int(hash_result[:13], 16)
    max_val = 16 ** 13

    # Convert to [1, 100] range to avoid division by zero and ensure proper distribution
    # This gives uniform distribution across 1-100 (inclusive)
    random_percentage = ((hex_value / max_val) * 99) + 1

    # Apply house edge to achieve 46% chance at 2x
    # With house_edge_multiplier=92 and uniform random_percentage in [1, 100]:
    # P(X >= 2) = P(random_percentage <= 46) = 46 out of 100 values = 46%
    house_edge_multiplier = 92

    try:
        result = house_edge_multiplier / random_percentage
        # Clamp between 1.00 and 1000.00
        result = max(1.00, min(1000.00, result))
        return round(result, 2)
    except:
        # Should never happen with random_percentage in [1, 100], but safety fallback
        return 1.00

def _limbo_get_font(size: int):
    """Load font for Limbo template with caching for performance."""
    if size in _limbo_font_cache:
        return _limbo_font_cache[size]
    
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    
    try:
        for font_path in font_paths:
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, size)
                _limbo_font_cache[size] = font
                return font
    except Exception:
        pass
    
    # Fallback to default
    font = ImageFont.load_default()
    _limbo_font_cache[size] = font
    return font

@check_banned
@check_maintenance
async def limbo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Limbo game: /lb amount target_multiplier
    Example: /lb 10 2.5 or /lb all 1.5
    """
    if not is_game_enabled("limbo"):
        await update.message.reply_text(
            "\U0001f527 <b>Limbo</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    args = update.message.text.strip().split()

    # Show instructions only when no arguments provided
    if len(args) == 1:
        await update.message.reply_text(
            "🚀 <b>LIMBO</b>\n\n"
            "<b>How to play:</b>\n"
            "• Choose your target multiplier (1.01 - 1000.00)\n"
            "• A random outcome is generated (1.00 - 1000.00)\n"
            "• If outcome ≥ your target: You win (bet × target)\n"
            "• If outcome < your target: You lose\n\n"
            "<b>Probability:</b>\n"
            "• 2x = ~46% chance\n"
            "• 4x = ~23% chance\n"
            "• Higher multipliers = lower chance\n\n"
            "<b>Usage:</b> <code>/lb amount multiplier</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/lb 10 2.00</code> - Bet $10 at 2x\n"
            "• <code>/lb all 1.5</code> - Bet all at 1.5x\n\n"
            f"<b>Min bet:</b> ${MIN_BALANCE:.2f}",
            parse_mode=ParseMode.HTML
        )
        return

    if len(args) != 3:
        await update.message.reply_text(
            "Usage: <code>/lb amount multiplier</code>\nExample: <code>/lb 10 2.00</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet_amount = get_active_balance_usd(user.id)
        else:
            bet_amount = float(bet_amount_str)

        target_multiplier = float(args[2])
    except ValueError:
        await update.message.reply_text("Invalid amount or multiplier. Please use numbers.")
        return

    # Validate target multiplier
    if target_multiplier < 1.01 or target_multiplier > 1000.00:
        await update.message.reply_text("Target multiplier must be between 1.01 and 1000.00")
        return

    if not await check_bet_limits(update, bet_amount, 'limbo'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Use user's provably fair seeds with fresh game client seed (like mines)
    # This ensures each game has unique, unpredictable seeds
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)  # Increment nonce to ensure unique results per game

    # Generate fresh client seed for this specific game
    game_client_seed = generate_game_client_seed()

    # Generate provably fair outcome
    game_id = generate_unique_id("LMB")
    outcome = get_limbo_multiplier(seeds["server_seed"], game_client_seed, current_nonce)

    # Determine win/loss
    win = outcome >= target_multiplier

    if win:
        winnings = bet_amount * target_multiplier
        credit_wallet(user.id, winnings)
        profit = winnings - bet_amount
    else:
        profit = -bet_amount
        winnings = 0

    # Store game session
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "limbo",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "target_multiplier": target_multiplier,
        "outcome": outcome,
        "status": "completed",
        "timestamp": str(datetime.now(timezone.utc)),
        "win": win,
        "server_seed": seeds["server_seed"],
        "client_seed": game_client_seed,
        "nonce": current_nonce
    }

    # Update stats
    if win:
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=target_multiplier, context=context)
    else:
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    # Store provably fair record
    store_provably_fair_record(game_id, "limbo", seeds["server_seed"], game_client_seed, current_nonce,
                               result_data=f"Target: {target_multiplier:.2f}x, Outcome: {outcome:.2f}x")

    update_pnl(user.id)
    save_user_data(user.id)

    # Generate Limbo template image
    active_currency = get_active_currency(user.id)
    player_pic = await _get_cached_profile_picture(context, user.id)

    # Track recent limbo players in this chat (newest first, max 3) so
    # the limbo PIL can show a player rail at the bottom matching the
    # template. Names only — no hardcoded examples.
    chat_id = update.effective_chat.id if update.effective_chat else 0
    cur_uid = user.id
    cur_display = user.username or user.first_name or str(user.id)
    bucket = _recent_limbo_players.setdefault(chat_id, [])
    bucket = [(uid, nm) for (uid, nm) in bucket if uid != cur_uid]
    bucket.insert(0, (cur_uid, cur_display))
    bucket = bucket[:_RECENT_LIMBO_MAX]
    _recent_limbo_players[chat_id] = bucket
    # Build rail entries (best-effort avatars).
    rail_entries = []
    for uid, nm in bucket:
        if uid == cur_uid:
            pic = player_pic
        else:
            try:
                pic = await _get_cached_profile_picture(context, uid)
            except Exception:
                pic = None
        rail_entries.append({"name": nm, "pic": pic})

    limbo_image = await async_generate_limbo_image(
        target_multiplier=target_multiplier,
        outcome=outcome,
        bet_amount=bet_amount,
        win=win,
        profit=profit if win else 0,
        player_username=user.username or str(user.id),
        bot_username=await get_bot_username(context),
        game_id=game_id,
        currency=active_currency,
        player_profile_pic=player_pic,
        recent_players=rail_entries,
    )

    # Create keyboard with provably fair button only
    keyboard = [[await create_provably_fair_button(game_id, context)]]

    # Send as photo with minimal caption
    caption = f"Game ID: <code>{game_id}</code>"
    
    await update.message.reply_photo(
        photo=limbo_image,
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('Limbo', limbo_command, block=False))
    app.add_handler(CommandHandler('lb', limbo_command, block=False))
    app.add_handler(CommandHandler('limbo', limbo_command, block=False))

