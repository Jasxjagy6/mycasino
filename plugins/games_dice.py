"""Auto-split from bot.py — plugins.games_dice."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

# --- Phase 1a: house-edge-aligned multipliers ------------------------
# Single source of truth: ``HOUSE_EDGES['originals']`` (declared in
# ``core/foundation.py``). Every dice / coin-flip multiplier below is
# computed from that constant, so changing the declared edge in one
# place re-tunes every payout in this module.
#
# Before this fix the live values were:
#   * coin-flip parlay per-round: 1.94  (≈3% edge, declared 1%)
#   * dice 50/50 (even/odd/high/low): 1.96  (≈2% edge, declared 1%)
#   * dice exact-number: 5.30           (≈11.67% edge, declared 1%)
# That mismatch broke rakeback accounting (audit S7, S8, M2, M3).
_ORIGINALS_EDGE = HOUSE_EDGES.get("originals", 0.01)
# Fair odds on a 50/50 = 2.00; on a 1/6 exact-number = 6.00.
COIN_FLIP_PER_ROUND_MULT = round(2.0 * (1.0 - _ORIGINALS_EDGE), 4)  # 1.98
DICE_5050_MULT = round(2.0 * (1.0 - _ORIGINALS_EDGE), 4)            # 1.98
DICE_EXACT_MULT = round(6.0 * (1.0 - _ORIGINALS_EDGE), 4)           # 5.94

def _dr_get_font(size=14):
    """Get font for Dice Rush image."""
    try:
        return ImageFont.truetype("bold.ttf", size)
    except:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except:
            return ImageFont.load_default()

@check_banned
@check_maintenance
async def coin_flip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("coinflip"):
        await update.message.reply_text(
            "\U0001f527 <b>Coinflip</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if len(args) != 2:
        await update.message.reply_text("Usage: /flip amount or /flip all")
        return
    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except Exception:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet, 'coin_flip'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Use user's provably fair seeds with fresh game client seed (like mines)
    # This ensures each game has unique, unpredictable seeds
    seeds = get_user_seeds(user.id)
    current_nonce = seeds["nonce"]
    increment_user_nonce(user.id)  # Increment nonce at game start to ensure unique results

    # Generate fresh client seed for this specific game
    game_client_seed = generate_game_client_seed()
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
        "client_seed": game_client_seed,
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
    await update.message.reply_text(
        f"{pe('coin')} <b>Coin Flip Started!</b> (ID: <code>{game_id}</code>)\n\n💰 Bet: {dformat(bet)}\nChoose Heads or Tails!\n\n"
        f"{pe('target')} Current Multiplier: {COIN_FLIP_PER_ROUND_MULT:.2f}x",
        parse_mode=ParseMode.HTML,
        reply_markup=create_styled_keyboard(keyboard)
    )

@check_banned
@check_maintenance
async def coin_flip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    parts = query.data.split("_")
    action = parts[1]
    game_id = parts[2]

    game = game_sessions.get(game_id)
    if not game:
        await query.edit_message_text("No active coin flip game found or this is not your game.")
        return

    if user.id != game.get('user_id'):
        await query.answer("This is not your game!", show_alert=True)
        return

    if game.get('status') != 'active':
        await query.edit_message_text("This game is already finished.")
        return


    if action == "pick":
        pick = parts[3]
        game["nonce"] += 1
        result_num = get_provably_fair_result(game["server_seed"], game["client_seed"], game["nonce"], 2)
        bot_choice = "Heads" if result_num == 0 else "Tails"

        if pick == bot_choice:
            game["streak"] += 1
            # Phase 1a: base multiplier per round derived from
            # HOUSE_EDGES["originals"] (1% by default) so the parlay
            # actually delivers the declared edge instead of ~3% per
            # round. Sequence: 1.98, 3.96, 7.92, 15.84, 31.68, ...
            multiplier = COIN_FLIP_PER_ROUND_MULT * (2 ** (game["streak"] - 1))
            win_amount = game["bet_amount"] * multiplier
            next_multiplier = COIN_FLIP_PER_ROUND_MULT * (2 ** game["streak"])
            keyboard = [
                [apply_button_style(InlineKeyboardButton("Heads", callback_data=f"flip_pick_{game_id}_Heads"), 'primary'),
                 apply_button_style(InlineKeyboardButton("Tails", callback_data=f"flip_pick_{game_id}_Tails"), 'primary')],
                [apply_button_style(InlineKeyboardButton(f"Cash Out ({dformat(win_amount)})", callback_data=f"flip_cashout_{game_id}"), 'success')]
            ]
            await query.edit_message_text(
                f"{pe('win')} <b>Correct!</b> The coin landed on {pick}!\n\n"
                f"{pe('money')} Current Win: <b>{dformat(win_amount)}</b>\n🔥 Streak: {game['streak']}\n"
                f"{pe('target')} Next Multiplier: {next_multiplier:.2f}x\n\nContinue playing or cash out?\nID: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=create_styled_keyboard(keyboard)
            )
        else:
            game["status"] = 'completed'
            game["win"] = False
            # Note: nonce was incremented at game start for provably fair
            await update_stats_on_bet(user.id, game_id, game['bet_amount'], False, context=context)
            update_pnl(user.id)
            save_user_data(user.id)

            # Store provably fair record
            store_provably_fair_record(game_id, "coinflip", game["server_seed"], game["client_seed"], game["nonce"],
                                       result_data=f"Streak: {game['streak']}, Result: {bot_choice}")

            # Add rebet/double and provably fair buttons
            keyboard = [
                [
                    apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"coinflip_rebet_{game['bet_amount']}_{user.id}"), 'primary', peb('rebet')),
                    apply_button_style(InlineKeyboardButton("Double", callback_data=f"coinflip_double_{game['bet_amount']}_{user.id}"), 'success', peb('double'))
                ],
                [await create_provably_fair_button(game_id, context)]
            ]

            await query.edit_message_text(
                f"{pe('cross')} <b>Wrong!</b> You picked {pick}, but the coin landed on {bot_choice}.\n\n"
                f"💔 You lost your bet of ${game['bet_amount']:.2f}\n🎯 Your streak was: {game['streak']}\nID: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            # del game_sessions[game_id] # FIX: Don't delete history

    elif action == "cashout":
        # Phase 1a: derived from HOUSE_EDGES["originals"] — see
        # COIN_FLIP_PER_ROUND_MULT at the top of this module.
        multiplier = COIN_FLIP_PER_ROUND_MULT * (2 ** (game["streak"] - 1))
        win_amount = game["bet_amount"] * multiplier
        credit_wallet(user.id, win_amount)
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        # Note: nonce was incremented at game start for provably fair
        await update_stats_on_bet(user.id, game_id, game['bet_amount'], True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)

        # Store provably fair record
        store_provably_fair_record(game_id, "coinflip", game["server_seed"], game["client_seed"], game["nonce"],
                                   result_data=f"Streak: {game['streak']}, Multiplier: {multiplier:.2f}x")

        # Add rebet/double and provably fair buttons
        keyboard = [
            [
                apply_button_style(InlineKeyboardButton("Rebet", callback_data=f"coinflip_rebet_{game['bet_amount']}_{user.id}"), 'primary'),
                apply_button_style(InlineKeyboardButton("Double", callback_data=f"coinflip_double_{game['bet_amount']}_{user.id}"), 'success')
            ],
            [await create_provably_fair_button(game_id, context)]
        ]

        await query.edit_message_text(
            f"{pe('withdraw')} <b>Cashed Out!</b>\n\n🎉 You won <b>{dformat(win_amount)}</b>!\n"
            f"{pe('fire')} Final streak: {game['streak']}\n📈 Final multiplier: {multiplier:.2f}x\nID: <code>{game_id}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

@check_banned
@check_maintenance
async def dice_roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("dice"):
        await update.effective_message.reply_text(
            "\U0001f527 <b>Dice Roll</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 3:
        await update.message.reply_text("Usage: /dr amount choice\n\nExamples:\n• /dr 1 3\n• /dr all even\n• /dr 1 high")
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return
    choice = args[2].lower()

    if not await check_bet_limits(update, bet_amount, 'dice_roll'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    valid_numbers = ['1', '2', '3', '4', '5', '6']
    valid_types = ['even', 'odd', 'high', 'low']
    if choice not in valid_numbers and choice not in valid_types:
        await update.message.reply_text("Invalid choice. Use 1-6, even, odd, high, or low.")
        return

    await update.message.reply_text(f"{pe('dice')} Rolling the dice...", parse_mode=ParseMode.HTML)
    chat_type = update.effective_chat.type
    animation_wait = await smart_rate_limit(update.effective_chat.id, chat_type)
    command_msg_id = update.message.message_id
    try:
        dice_msg, used_helper = await smart_roll(context, update.effective_chat.id, "🎲", reply_to_message_id=command_msg_id)
        dice_result = dice_msg.dice.value
        if used_helper:
            await asyncio.sleep(HELPER_BOT_ANIMATION_DELAY)
        else:
            await asyncio.sleep(animation_wait)
    except Exception as e:
        logging.error(f"Error sending dice in dice_roll_command: {e}")
        # Refund the bet on error
        credit_wallet(user.id, bet_amount)
        save_user_data(user.id)
        await update.message.reply_text(f"{pe('cross')} An error occurred while rolling the dice. Your bet has been refunded.")
        return
    game_id = generate_unique_id("DR")

    win = False
    multiplier = 0 # NEW
    # Phase 1a: multipliers derived from HOUSE_EDGES["originals"]. See
    # DICE_EXACT_MULT and DICE_5050_MULT at the top of this module —
    # changing the declared edge in core/foundation.py retunes both.
    if choice in valid_numbers:
        if int(choice) == dice_result: win, multiplier = True, DICE_EXACT_MULT
    elif choice == "even":
        if dice_result in [2, 4, 6]: win, multiplier = True, DICE_5050_MULT
    elif choice == "odd":
        if dice_result in [1, 3, 5]: win, multiplier = True, DICE_5050_MULT
    elif choice == "high":
        if dice_result in [4, 5, 6]: win, multiplier = True, DICE_5050_MULT
    elif choice == "low":
        if dice_result in [1, 2, 3]: win, multiplier = True, DICE_5050_MULT

    if win:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} You win {format_for_user(user.id, winnings)}! (Multiplier: {multiplier}x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} You lose {dformat(bet_amount)}. Try again!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "dice_roll", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": win, "multiplier": multiplier, "choice": choice, "result": dice_result
    }
    update_pnl(user.id)
    save_user_data(user.id)

    await update.message.reply_text(
        f"{pe('dice')} <b>Dice Roll Result</b> (ID: <code>{game_id}</code>)\n\n🎯 Result: <b>{dice_result}</b>\n"
        f"{pe('dice')} Your Choice: {choice}\n💰 Your Bet: {dformat(bet_amount)}\n\n{result_text}",
        parse_mode=ParseMode.HTML
    )

async def dice_rush_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dice Rush game with 5 modes:
    1. Classic Rush: /rush [1-6] [amount] or /dicerush [1-6] [amount]
    2. Odd/Even Rush: /rush odd [amount] or /rush even [amount]
    3. High/Low Rush: /rush high [amount] or /rush low [amount]
    4. Rainbow Rush: /rr [amount] or /rushrainbow [amount]
    5. Blaze Rush: /br [amount] or /blazerush [amount]

    When used alone (/rush), shows help menu with image.
    """
    if not is_game_enabled("dice"):
        await update.effective_message.reply_text(
            "\U0001f527 <b>Dice Rush</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return

    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # If no args, show help menu with image
    if len(args) == 1:
        await _send_dice_rush_help(update, context)
        return

    # Parse the game mode and bet amount
    mode = args[1].lower()

    # Classic Rush: /rush [1-6] [amount]
    if mode in ['1', '2', '3', '4', '5', '6']:
        if len(args) != 3:
            await update.message.reply_text("Usage: /rush [1-6] [amount]\nExample: /rush 3 5")
            return
        try:
            bet_amount_str = args[2].lower()
            # Display-currency aware (parity with blackjack/tower).
            bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return
        await _play_classic_rush(update, context, user, int(mode), bet_amount)

    # Odd/Even Rush
    elif mode in ['odd', 'even']:
        if len(args) != 3:
            await update.message.reply_text(f"Usage: /rush {mode} [amount]\nExample: /rush {mode} 5")
            return
        try:
            bet_amount_str = args[2].lower()
            bet_amount = get_active_balance_usd(user.id) if bet_amount_str == 'all' else float(bet_amount_str)
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return
        await _play_odd_even_rush(update, context, user, mode, bet_amount)

    # High/Low Rush
    elif mode in ['high', 'low']:
        if len(args) != 3:
            await update.message.reply_text(f"Usage: /rush {mode} [amount]\nExample: /rush {mode} 5")
            return
        try:
            bet_amount_str = args[2].lower()
            bet_amount = get_active_balance_usd(user.id) if bet_amount_str == 'all' else float(bet_amount_str)
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return
        await _play_high_low_rush(update, context, user, mode, bet_amount)

    else:
        await update.message.reply_text("Invalid mode. Use: 1-6, odd, even, high, low\nOr use /rr for Rainbow Rush, /br for Blaze Rush")

async def _send_dice_rush_help(update, context):
    """Send Dice Rush help menu with image."""
    try:
        # Generate the help image
        img_buf = await async_generate_dice_rush_image()

        caption = (
            f"{pe('dice')} <b>DICE RUSH</b> | @playcsino\n\n"
            f"<b>1. Classic Rush</b>\n"
            f"/rush [1-6] [amount] - Pick number, win on 2+ matches\n"
            f"2 Hits: 2.8x | 3: 5x | 4: 10x | 5: 20x | 6: 40x\n\n"
            f"<b>2. Odd/Even Rush</b>\n"
            f"/rush odd/even [amount] - Win on 4+ matches\n"
            f"4 Match: 1.8x | 5: 4x | 6: 10x\n\n"
            f"<b>3. High/Low Rush</b>\n"
            f"/rush high/low [amount] - Win on 4+ matches\n"
            f"4 Match: 1.8x | 5: 4x | 6: 10x\n\n"
            f"<b>4. Rainbow Rush</b>\n"
            f"/rr [amount] - All 6 different = 55x\n\n"
            f"<b>5. Blaze Rush</b>\n"
            f"/br [amount] - All same parity = 25x\n\n"
            f"Provably Fair Gaming"
        )

        await update.message.reply_photo(
            photo=img_buf,
            caption=caption,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Error sending Dice Rush help image: {e}")
        # Fallback to text only
        await update.message.reply_text(
            f"{pe('dice')} <b>DICE RUSH</b>\n\n"
            f"<b>1. Classic Rush:</b> /rush [1-6] [amount] - Pick number, win on 2+ matches\n"
            f"<b>2. Odd/Even:</b> /rush odd/even [amount] - Win on 4+ matches\n"
            f"<b>3. High/Low:</b> /rush high/low [amount] - Win on 4+ matches\n"
            f"<b>4. Rainbow:</b> /rr [amount] - All 6 different = 55x\n"
            f"<b>5. Blaze:</b> /br [amount] - All same parity = 25x",
            parse_mode=ParseMode.HTML
        )

async def _play_classic_rush(update, context, user, chosen_number, bet_amount):
    """Classic Rush: Pick number 1-6, roll 6 dice, win on 2+ matches."""
    if not await check_bet_limits(update, bet_amount, 'dice_rush'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    # Send waiting message
    wait_msg = await update.message.reply_text(
        f"{pe('dice')} <b>Classic Rush</b>\n"
        f"Your pick: <b>{chosen_number}</b> | Bet: {dformat(bet_amount)}\n"
        f"Rolling 6 dice...",
        parse_mode=ParseMode.HTML
    )

    # Roll 6 dice in parallel using multi-bot system
    chat_id = update.effective_chat.id
    command_msg_id = update.message.message_id
    rolls = await multi_roll_parallel(context, chat_id, DICE_RUSH_EMOJI, 6, reply_to_message_id=command_msg_id)

    # Collect results
    results = [msg.dice.value for msg, _ in rolls]
    matches = sum(1 for r in results if r == chosen_number)

    # Delete waiting message
    try:
        await wait_msg.delete()
    except:
        pass

    # Calculate payout
    payouts = {2: 2.8, 3: 5, 4: 10, 5: 20, 6: 40}
    multiplier = payouts.get(matches, 0)

    game_id = generate_unique_id("CR")

    if matches >= 2:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} You win {format_for_user(user.id, winnings)}! ({matches} hits, {multiplier}x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} Only {matches} match(es). Need 2+ to win!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    # Store game session
    game_sessions[game_id] = {
        "id": game_id, "game_type": "classic_rush", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": matches >= 2, "multiplier": multiplier, "choice": chosen_number, "results": results, "matches": matches
    }
    update_pnl(user.id)
    save_user_data(user.id)

    # Format dice results
    dice_display = ", ".join([str(r) for r in results])

    await update.message.reply_text(
        f"{pe('dice')} <b>Classic Rush Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"Your Pick: <b>{chosen_number}</b>\n"
        f"Rolls: [{dice_display}]\n"
        f"Matches: <b>{matches}</b>/6\n"
        f"Bet: {dformat(bet_amount)}\n\n"
        f"{result_text}",
        parse_mode=ParseMode.HTML
    )

async def _play_odd_even_rush(update, context, user, choice, bet_amount):
    """Odd/Even Rush: Pick odd or even, roll 6 dice, win on 4+ matches."""
    if not await check_bet_limits(update, bet_amount, 'dice_rush'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    wait_msg = await update.message.reply_text(
        f"{pe('dice')} <b>Odd/Even Rush</b>\n"
        f"Your pick: <b>{choice.upper()}</b> | Bet: {dformat(bet_amount)}\n"
        f"Rolling 6 dice...",
        parse_mode=ParseMode.HTML
    )

    chat_id = update.effective_chat.id
    command_msg_id = update.message.message_id
    rolls = await multi_roll_parallel(context, chat_id, DICE_RUSH_EMOJI, 6, reply_to_message_id=command_msg_id)

    results = [msg.dice.value for msg, _ in rolls]
    odd_numbers = {1, 3, 5}
    even_numbers = {2, 4, 6}

    if choice == 'odd':
        matches = sum(1 for r in results if r in odd_numbers)
    else:
        matches = sum(1 for r in results if r in even_numbers)

    try:
        await wait_msg.delete()
    except:
        pass

    payouts = {4: 1.8, 5: 4, 6: 10}
    multiplier = payouts.get(matches, 0)
    game_id = generate_unique_id("OE")

    if matches >= 4:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} You win {format_for_user(user.id, winnings)}! ({matches} matches, {multiplier}x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} Only {matches} matches. Need 4+ to win!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "odd_even_rush", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": matches >= 4, "multiplier": multiplier, "choice": choice, "results": results, "matches": matches
    }
    update_pnl(user.id)
    save_user_data(user.id)

    dice_display = ", ".join([str(r) for r in results])
    parity_label = "Odd" if choice == 'odd' else "Even"

    await update.message.reply_text(
        f"{pe('dice')} <b>Odd/Even Rush Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"Your Pick: <b>{parity_label}</b>\n"
        f"Rolls: [{dice_display}]\n"
        f"{parity_label} Matches: <b>{matches}</b>/6\n"
        f"Bet: {dformat(bet_amount)}\n\n"
        f"{result_text}",
        parse_mode=ParseMode.HTML
    )

async def _play_high_low_rush(update, context, user, choice, bet_amount):
    """High/Low Rush: Pick high (4,5,6) or low (1,2,3), roll 6 dice, win on 4+ matches."""
    if not await check_bet_limits(update, bet_amount, 'dice_rush'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    wait_msg = await update.message.reply_text(
        f"{pe('dice')} <b>High/Low Rush</b>\n"
        f"Your pick: <b>{choice.upper()}</b> | Bet: {dformat(bet_amount)}\n"
        f"Rolling 6 dice...",
        parse_mode=ParseMode.HTML
    )

    chat_id = update.effective_chat.id
    command_msg_id = update.message.message_id
    rolls = await multi_roll_parallel(context, chat_id, DICE_RUSH_EMOJI, 6, reply_to_message_id=command_msg_id)

    results = [msg.dice.value for msg, _ in rolls]
    high_numbers = {4, 5, 6}
    low_numbers = {1, 2, 3}

    if choice == 'high':
        matches = sum(1 for r in results if r in high_numbers)
    else:
        matches = sum(1 for r in results if r in low_numbers)

    try:
        await wait_msg.delete()
    except:
        pass

    payouts = {4: 1.8, 5: 4, 6: 10}
    multiplier = payouts.get(matches, 0)
    game_id = generate_unique_id("HL")

    if matches >= 4:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} You win {format_for_user(user.id, winnings)}! ({matches} matches, {multiplier}x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} Only {matches} matches. Need 4+ to win!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "high_low_rush", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": matches >= 4, "multiplier": multiplier, "choice": choice, "results": results, "matches": matches
    }
    update_pnl(user.id)
    save_user_data(user.id)

    dice_display = ", ".join([str(r) for r in results])
    label = "High" if choice == 'high' else "Low"

    await update.message.reply_text(
        f"{pe('dice')} <b>High/Low Rush Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"Your Pick: <b>{label}</b>\n"
        f"Rolls: [{dice_display}]\n"
        f"{label} Matches: <b>{matches}</b>/6\n"
        f"Bet: {dformat(bet_amount)}\n\n"
        f"{result_text}",
        parse_mode=ParseMode.HTML
    )

async def rainbow_rush_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rainbow Rush: Win if all 6 dice are different. Payout 55x."""
    if not is_game_enabled("dice"):
        await update.effective_message.reply_text(
            "\U0001f527 <b>Rainbow Rush</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return

    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text("Usage: /rr [amount]\nExample: /rr 5")
        return

    try:
        bet_amount_str = args[1].lower()
        bet_amount = get_active_balance_usd(user.id) if bet_amount_str == 'all' else float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    await _play_rainbow_rush(update, context, user, bet_amount)

async def _play_rainbow_rush(update, context, user, bet_amount):
    """Rainbow Rush gameplay: all 6 dice must be different."""
    if not await check_bet_limits(update, bet_amount, 'dice_rush'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    wait_msg = await update.message.reply_text(
        f"{pe('rainbow')} <b>Rainbow Rush</b>\n"
        f"Bet: {dformat(bet_amount)} | Win: 55x if all 6 dice are different!\n"
        f"Rolling 6 dice...",
        parse_mode=ParseMode.HTML
    )

    chat_id = update.effective_chat.id
    command_msg_id = update.message.message_id
    rolls = await multi_roll_parallel(context, chat_id, DICE_RUSH_EMOJI, 6, reply_to_message_id=command_msg_id)

    results = [msg.dice.value for msg, _ in rolls]
    unique_count = len(set(results))
    is_win = unique_count == 6  # All different

    try:
        await wait_msg.delete()
    except:
        pass

    multiplier = 55 if is_win else 0
    game_id = generate_unique_id("RR")

    if is_win:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        result_text = f"{pe('win')} RAINBOW! You win {format_for_user(user.id, winnings)}! (55x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"{pe('lose')} {unique_count}/6 unique. Need all 6 different!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "rainbow_rush", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": is_win, "multiplier": multiplier, "results": results, "unique_count": unique_count
    }
    update_pnl(user.id)
    save_user_data(user.id)

    dice_display = ", ".join([str(r) for r in results])

    await update.message.reply_text(
        f"{pe('rainbow')} <b>Rainbow Rush Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"Rolls: [{dice_display}]\n"
        f"Unique: <b>{unique_count}</b>/6\n"
        f"Bet: {dformat(bet_amount)}\n\n"
        f"{result_text}",
        parse_mode=ParseMode.HTML
    )

async def blaze_rush_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Blaze Rush: Win if all 6 dice are same parity (all odd or all even). Payout 25x."""
    if not is_game_enabled("dice"):
        await update.effective_message.reply_text(
            "\U0001f527 <b>Blaze Rush</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return

    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text("Usage: /br [amount]\nExample: /br 5")
        return

    try:
        bet_amount_str = args[1].lower()
        bet_amount = get_active_balance_usd(user.id) if bet_amount_str == 'all' else float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    await _play_blaze_rush(update, context, user, bet_amount)

async def _play_blaze_rush(update, context, user, bet_amount):
    """Blaze Rush gameplay: all 6 dice must be same parity."""
    if not await check_bet_limits(update, bet_amount, 'dice_rush'):
        return

    try:
        crypto_deducted, coin = await deduct_wallet_safe(user.id, bet_amount)
    except ValueError:
        await send_insufficient_balance_message(update)
        return
    save_user_data(user.id)

    wait_msg = await update.message.reply_text(
        f"{pe('fire')} <b>Blaze Rush</b>\n"
        f"Bet: {dformat(bet_amount)} | Win: 25x if all same parity!\n"
        f"Rolling 6 dice...",
        parse_mode=ParseMode.HTML
    )

    chat_id = update.effective_chat.id
    command_msg_id = update.message.message_id
    rolls = await multi_roll_parallel(context, chat_id, DICE_RUSH_EMOJI, 6, reply_to_message_id=command_msg_id)

    results = [msg.dice.value for msg, _ in rolls]
    odd_numbers = {1, 3, 5}
    all_odd = all(r in odd_numbers for r in results)
    all_even = all(r not in odd_numbers for r in results)
    is_win = all_odd or all_even

    try:
        await wait_msg.delete()
    except:
        pass

    multiplier = 25 if is_win else 0
    game_id = generate_unique_id("BR")

    if is_win:
        winnings = bet_amount * multiplier
        credit_wallet(user.id, winnings)
        parity = "All Odd" if all_odd else "All Even"
        result_text = f"{pe('win')} BLAZE! {parity}! You win {format_for_user(user.id, winnings)}! (25x)"
        await update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        odd_count = sum(1 for r in results if r in odd_numbers)
        even_count = 6 - odd_count
        result_text = f"{pe('lose')} {odd_count} odd, {even_count} even. Need all same parity!"
        await update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "blaze_rush", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "win": is_win, "multiplier": multiplier, "results": results
    }
    update_pnl(user.id)
    save_user_data(user.id)

    dice_display = ", ".join([str(r) for r in results])

    await update.message.reply_text(
        f"{pe('fire')} <b>Blaze Rush Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"Rolls: [{dice_display}]\n"
        f"Bet: {dformat(bet_amount)}\n\n"
        f"{result_text}",
        parse_mode=ParseMode.HTML
    )

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('flip', coin_flip_command, block=False))
    app.add_handler(CommandHandler('dr', dice_roll_command, block=False))
    app.add_handler(CommandHandler(['rush', 'dicerush'], dice_rush_command, block=False))
    app.add_handler(CommandHandler(['rr', 'rushrainbow'], rainbow_rush_command, block=False))
    app.add_handler(CommandHandler(['br', 'blazerush'], blaze_rush_command, block=False))
    app.add_handler(CallbackQueryHandler(coin_flip_callback, pattern='^flip_', block=False))

