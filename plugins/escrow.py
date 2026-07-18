"""Auto-split from bot.py — plugins.escrow."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

@check_banned
@check_maintenance
async def escrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # NEW: Check if escrow feature is enabled
    if not bot_settings.get("escrow_enabled", True):
        error_msg = f"{pe('cross')} This feature is currently disabled by the owner."
        if from_callback:
            await safe_edit_message(
                update.callback_query,
                error_msg,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to More", callback_data="main_more")]])
            )
        else:
            await update.message.reply_text(error_msg)
        return

    if not all([ESCROW_DEPOSIT_ADDRESS, ESCROW_WALLET_PRIVATE_KEY]):
        error_msg = "Escrow system is not configured by the owner yet."
        if from_callback: await safe_edit_message(update.callback_query, error_msg)
        else: await update.message.reply_text(error_msg)
        return

    context.user_data['escrow_step'] = 'ask_amount'
    context.user_data['escrow_data'] = {'creator_id': user.id, 'creator_username': user.username}
    text = f"{pe('shield')} <b>New Escrow Deal</b>\n\nPlease enter the deal amount in USDT (BEP20)."
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="escrow_action_cancel_setup")]]
    if from_callback:
        await safe_edit_message(update.callback_query, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

@check_banned
@check_maintenance
async def handle_escrow_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    step = context.user_data.get('escrow_step')
    deal_data = context.user_data.get('escrow_data', {})
    cancel_button = [[InlineKeyboardButton("Cancel", callback_data="escrow_action_cancel_setup")]]

    if step == 'ask_amount':
        try:
            amount = float(update.message.text)
            if amount <= 0: raise ValueError
            deal_data['amount'] = amount
            context.user_data['escrow_step'] = 'ask_role'
            keyboard = [
                [InlineKeyboardButton(f"{pe('house')} I am the Seller", callback_data="escrow_role_seller")],
                [InlineKeyboardButton(f"{pe('shopping')} I am the Buyer", callback_data="escrow_role_buyer")],
                [InlineKeyboardButton("Cancel", callback_data="escrow_action_cancel_setup")]
            ]
            await update.message.reply_text(f"{pe('check')} Amount set to ${amount:.2f} USDT.\n\nPlease select your role:", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        except (ValueError, TypeError):
            await update.message.reply_text(f"{pe('cross')} Invalid amount. Please enter a positive number.", reply_markup=InlineKeyboardMarkup(cancel_button))
            return

    elif step == 'ask_details':
        deal_data['details'] = update.message.text
        # REMOVED: ask_partner_method step. Forcing link creation.
        await create_and_finalize_escrow_deal(update, context, by_link=True)

@check_banned
@check_maintenance
async def escrow_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user, data = query.from_user, query.data.split('_')
    action = data[1]
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if action == 'role':
        role = data[2]
        context.user_data['escrow_data']['creator_role'] = role
        context.user_data['escrow_data']['partner_role'] = 'Buyer' if role == 'seller' else 'Seller'
        context.user_data['escrow_step'] = 'ask_details'
        cancel_button = [[InlineKeyboardButton("Cancel", callback_data="escrow_action_cancel_setup")]]
        await query.edit_message_text(f"{pe('check')} Role selected. Now, please provide the deal details (e.g., 'Sale of item X').", reply_markup=InlineKeyboardMarkup(cancel_button))

    # REMOVED: partner action, as we now force link creation.

    elif action == 'confirm':
        deal_id, decision = data[2], data[3]
        deal = escrow_deals.get(deal_id)
        if not deal or (user.id != deal.get('buyer', {}).get('id') and user.id != deal.get('seller', {}).get('id')):
            await query.edit_message_text("This deal is not for you or has expired.")
            return
        if user.id == deal.get('creator_id'):
            await query.answer("Waiting for the other party to respond.", show_alert=True); return

        if decision == 'accept':
            deal['status'] = 'accepted_awaiting_deposit'
            save_escrow_deal(deal_id)
            seller_id, buyer_id = deal['seller']['id'], deal['buyer']['id']
            await query.edit_message_text(f"{pe('check')} You accepted the deal. Seller will now be prompted to deposit ${deal['amount']:.2f} USDT.")
            deposit_text = (f"{{pe('check')}} The other party accepted the deal!\n\n<b>Deal ID:</b> <code>{deal_id}</code>\n"
                            f"Please deposit exactly <code>{deal['amount']}</code> USDT (BEP20) to:\n<code>{ESCROW_DEPOSIT_ADDRESS}</code>\n\n"
                            f"{pe('warning')} Send from your own wallet (NOT from an exchange). Have enough BNB for gas.")
            await context.bot.send_message(chat_id=seller_id, text=deposit_text, parse_mode='HTML')
            context.job_queue.run_repeating(monitor_escrow_deposit, interval=20, first=10, data={'deal_id': deal_id}, name=f"escrow_monitor_{deal_id}")
        else: # Decline
            deal['status'] = 'declined_by_partner'; save_escrow_deal(deal_id)
            await query.edit_message_text("You have declined the deal. It has been cancelled.")
            await context.bot.send_message(chat_id=deal['creator_id'], text=f"The other party has declined your escrow deal ({deal_id}).")

    elif action == 'action':
        if data[2] == "cancel" and data[3] == "setup":
             context.user_data.clear()
             await query.edit_message_text("Escrow setup cancelled.")
             await more_menu(update, context)
             return

        deal_id, decision = data[2], data[3]
        deal = escrow_deals.get(deal_id)
        if not deal or user.id not in [deal['seller']['id'], deal['buyer']['id']]: return

        if decision == 'release':
            if user.id != deal['seller']['id']: await query.answer("Only the seller can release funds.", show_alert=True); return
            if deal['status'] != 'funds_secured': await query.answer("Funds are not in a releasable state.", show_alert=True); return
            keyboard = [
                [InlineKeyboardButton("Yes, Release Funds", callback_data=f"escrow_action_{deal_id}_releaseconfirm")],
                [InlineKeyboardButton("No, Cancel", callback_data=f"escrow_action_{deal_id}_releasecancel")]
            ]
            await query.edit_message_text(f"{pe('warning')} Are you sure you want to release the funds to the buyer? This action is irreversible.", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        elif decision == 'releaseconfirm':
            if user.id != deal['seller']['id']: return
            # NEW: Credit buyer's casino balance directly instead of asking for withdrawal address
            buyer_id = deal['buyer']['id']
            amount = deal['amount']

            # Add funds to buyer's casino balance
            await ensure_user_in_wallets(buyer_id, context=context)
            credit_wallet(buyer_id, amount)
            save_user_data(buyer_id)

            # Update deal status
            deal['status'] = 'completed'
            deal['completed_at'] = str(datetime.now(timezone.utc))
            save_escrow_deal(deal_id)

            # Notify both parties
            seller_msg = (
                f"{pe('check')} <b>Deal Completed!</b>\n\n"
                f"<b>Deal ID:</b> <code>{deal_id}</code>\n"
                f"<b>Amount:</b> ${amount:.2f}\n\n"
                f"The funds have been credited to the buyer's casino balance.\n"
                f"Thank you for using our escrow service!"
            )
            buyer_msg = (
                f"{pe('check')} <b>Funds Received!</b>\n\n"
                f"<b>Deal ID:</b> <code>{deal_id}</code>\n"
                f"<b>Amount:</b> ${amount:.2f}\n\n"
                f"The funds have been added to your casino balance.\n"
                f"You can now withdraw them using the withdrawal feature.\n\n"
                f"Use /withdraw to request a withdrawal."
            )

            await query.edit_message_text(seller_msg, parse_mode=ParseMode.HTML)
            await context.bot.send_message(chat_id=buyer_id, text=buyer_msg, parse_mode=ParseMode.HTML)

        elif decision == 'releasecancel': await query.edit_message_text("Release cancelled.")
        elif decision == 'dispute':
            deal['status'] = 'disputed'; save_escrow_deal(deal_id)
            dispute_text = f"{pe('alarm')} A dispute has been opened for deal <code>{deal_id}</code>. Contact @Ittz_surajj for assistance."
            await query.edit_message_text(dispute_text, parse_mode="HTML")
            other_party_id = deal['buyer']['id'] if user.id == deal['seller']['id'] else deal['seller']['id']
            await context.bot.send_message(chat_id=other_party_id, text=dispute_text, parse_mode="HTML")
            await context.bot.send_message(BOT_OWNER_ID, text=f"New dispute for deal {deal_id}.")

async def create_and_finalize_escrow_deal(update: Update, context: ContextTypes.DEFAULT_TYPE, by_link=False):
    user = update.effective_user
    deal_data = context.user_data.get('escrow_data', {})
    if deal_data['creator_role'] == 'seller':
        deal_data['seller'] = {'id': user.id, 'username': user.username}
        deal_data['buyer'] = {'id': None, 'username': None} # Partner joins via link
    else:
        deal_data['buyer'] = {'id': user.id, 'username': user.username}
        deal_data['seller'] = {'id': None, 'username': None} # Partner joins via link

    deal_id = generate_unique_id("ESC")
    deal_data.update({'id': deal_id, 'status': 'pending_confirmation', 'timestamp': str(datetime.now(timezone.utc))})
    escrow_deals[deal_id] = deal_data
    save_escrow_deal(deal_id)

    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_stats[user.id]['escrow_deals'].append(deal_id)
    save_user_data(user.id)

    context.user_data.pop('escrow_step', None); context.user_data.pop('escrow_data', None)

    buyer_username = deal_data.get('buyer', {}).get('username') or "TBD (via link)"
    seller_username = deal_data.get('seller', {}).get('username') or "TBD (via link)"
    deal_summary = (f"🛡️ <b>New Escrow Deal Created</b>\n\n<b>Deal ID:</b> <code>{deal_id}</code>\n"
                    f"<b>Amount:</b> ${deal_data['amount']:.2f} USDT\n<b>Seller:</b> @{seller_username}\n"
                    f"<b>Buyer:</b> @{buyer_username}\n<b>Details:</b> {deal_data['details']}")

    bot_username = await get_bot_username(context)
    deal_link = f"https://t.me/{bot_username}?start=escrow_{deal_id}"

    reply_target = update.callback_query.message if update.callback_query else update.message
    await reply_target.reply_text(f"{deal_summary}\n\nShare this link with the other party to join:\n<code>{deal_link}</code>", parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def handle_escrow_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE, deal_id: str):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    deal = escrow_deals.get(deal_id)
    if not deal: await update.message.reply_text("This escrow deal link is invalid or has expired."); return

    is_joinable = (deal['creator_role'] == 'seller' and deal.get('buyer', {}).get('id') is None) or \
                  (deal['creator_role'] == 'buyer' and deal.get('seller', {}).get('id') is None)
    if not is_joinable or deal['status'] != 'pending_confirmation':
        await update.message.reply_text("This deal has already been accepted or is no longer valid."); return
    if user.id == deal['creator_id']:
        await update.message.reply_text("You cannot accept your own deal. Share the link with the other party."); return

    if deal['creator_role'] == 'seller': deal['buyer'] = {'id': user.id, 'username': user.username}
    else: deal['seller'] = {'id': user.id, 'username': user.username}
    user_stats[user.id]['escrow_deals'].append(deal_id)
    save_user_data(user.id)
    save_escrow_deal(deal_id)

    deal_summary = (f"🛡️ <b>You are joining an Escrow Deal</b>\n\n<b>Deal ID:</b> <code>{deal_id}</code>\n"
                    f"<b>Amount:</b> ${deal['amount']:.2f} USDT\n<b>Seller:</b> @{deal['seller']['username']}\n"
                    f"<b>Buyer:</b> @{deal['buyer']['username']}\n<b>Details:</b> {deal['details']}")
    keyboard = [[InlineKeyboardButton("Accept Deal", callback_data=f"escrow_confirm_{deal_id}_accept"), InlineKeyboardButton("Decline Deal", callback_data=f"escrow_confirm_{deal_id}_decline")]]
    await update.message.reply_text(f"{deal_summary}\n\nPlease confirm to proceed.", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

def generate_verification_code(pf_record):
    """Generate game-specific verification code"""
    game_type = pf_record['game_type']
    server_seed = pf_record['server_seed']
    client_seed = pf_record['client_seed']
    nonce = pf_record['nonce']

    # Base verification functions used by all games
    base_code = f"""import hashlib

# Your Game Data
server_seed = "{server_seed}"
client_seed = "{client_seed}"
nonce = {nonce}

# Core Verification Functions
def create_hash(server_seed, client_seed, nonce):
    combined = f"{{server_seed}}:{{client_seed}}:{{nonce}}"
    return hashlib.sha256(combined.encode()).hexdigest()

def get_provably_fair_result(server_seed, client_seed, nonce, max_value):
    hash_result = create_hash(server_seed, client_seed, nonce)
    hex_value = int(hash_result[:8], 16)
    return hex_value % max_value

"""

    # Game-specific verification code
    if game_type == "roulette":
        game_code = """# Roulette Verification
RED_NUMBERS = {{1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}}

winning_number = get_provably_fair_result(server_seed, client_seed, nonce, 37)

if winning_number == 0:
    color = "Green 🟢"
elif winning_number in RED_NUMBERS:
    color = "Red 🔴"
else:
    color = "Black ⚫"

print(f"=== Roulette Verification ===")
print(f"Winning Number: {{winning_number}} ({{color}})")
print(f"Hash: {{create_hash(server_seed, client_seed, nonce)[:16]}}...")
"""

    elif game_type == "hilo":
        game_code = """# Hi-Lo (High-Low) Card Game Verification
# Generate shuffled deck
deck = list(range(1, 14)) * 4  # 1-13, 4 suits (52 cards)

# Fisher-Yates shuffle with provably fair results
for i in range(len(deck) - 1, 0, -1):
    j = get_provably_fair_result(server_seed, client_seed, nonce + i, i + 1)
    deck[i], deck[j] = deck[j], deck[i]

card_names = {{1:'ACE', 2:'2', 3:'3', 4:'4', 5:'5', 6:'6', 7:'7', 8:'8', 9:'9', 10:'10', 11:'JACK', 12:'QUEEN', 13:'KING'}}

print("=== Hi-Lo Card Sequence ===")
print("First 10 cards from shuffled deck:")
for i in range(min(10, len(deck))):
    card_value = deck[-(i+1)]  # Cards are popped from end
    print(f"  Card {{i+1}}: {{card_names[card_value]}} ({{card_value}})")
"""

    elif game_type == "mines":
        # Extract mine count from result data if available
        result_data = pf_record.get('result_data', '')
        num_mines = 3  # Default
        # Try to extract from result_data
        import re
        if result_data:
            match = re.search(r'Mine positions: \[([^\]]+)\]', result_data)
            if match:
                try:
                    positions_str = match.group(1)
                    num_mines = len(positions_str.split(','))
                except:
                    pass

        game_code = f"""# Mines Game Verification
def generate_mine_positions(server_seed, client_seed, nonce, num_mines):
    positions = []
    offset = 0
    # IMPORTANT: Use nonce * 1000 to ensure unique results for consecutive games
    base_nonce = nonce * 1000
    while len(positions) < num_mines:
        pos = get_provably_fair_result(server_seed, client_seed, base_nonce + offset, 25)
        if pos not in positions:
            positions.append(pos)
        offset += 1
    return sorted(positions)

# Mine count from your game
num_mines = {num_mines}

mine_positions = generate_mine_positions(server_seed, client_seed, nonce, num_mines)

print("=== Mines Verification ===")
print(f"Mine Positions (0-24): {{mine_positions}}")
print(f"Number of mines: {{len(mine_positions)}}")
print("\\nGrid (5x5, rows 0-4, cols 0-4):")
for row in range(5):
    row_str = ""
    for col in range(5):
        idx = row * 5 + col
        row_str += "💣 " if idx in mine_positions else "💎 "
    print(f"Row {{row}}: {{row_str}}")
"""

    elif game_type == "tower":
        # Extract difficulty from result data if available
        result_data = pf_record.get('result_data', '')
        difficulty = 'medium'  # Default
        if 'easy' in result_data.lower():
            difficulty = 'easy'
        elif 'hard' in result_data.lower():
            difficulty = 'hard'
        elif 'medium' in result_data.lower():
            difficulty = 'medium'

        game_code = f"""# Tower Game Verification
def generate_tower_positions(server_seed, client_seed, nonce, difficulty, num_floors=9):
    tiles_per_floor = {{'easy': 4, 'medium': 3, 'hard': 2}}.get(difficulty, 3)
    positions = []
    # IMPORTANT: Use nonce * 1000 to ensure unique results for consecutive games
    base_nonce = nonce * 1000
    for floor in range(num_floors):
        snake_pos = get_provably_fair_result(server_seed, client_seed, base_nonce + floor, tiles_per_floor)
        positions.append(snake_pos)
    return positions

# Difficulty from your game
difficulty = '{difficulty}'
snake_positions = generate_tower_positions(server_seed, client_seed, nonce, difficulty, 9)
tiles = {{'easy': 4, 'medium': 3, 'hard': 2}}[difficulty]

print(f"=== Tower Verification ({{difficulty.title()}}) ===")
print(f"Tiles per floor: {{tiles}}")
print("Snake positions by floor (position 0 to {{tiles-1}}):")
for i, pos in enumerate(snake_positions):
    floor_num = i + 1
    grid = ['🌴' for _ in range(tiles)]
    grid[pos] = '🐍'
    print(f"Floor {{floor_num}}: {{' '.join(grid)}} (Snake at position {{pos}})")
"""

    elif game_type == "blackjack":
        game_code = """# Blackjack Verification
# Generate and shuffle deck
suits = ['♠', '♥', '♦', '♣']
ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
deck = [f"{{r}}{{s}}" for s in suits for r in ranks]

# Fisher-Yates shuffle
for i in range(len(deck) - 1, 0, -1):
    j = get_provably_fair_result(server_seed, client_seed, nonce + i, i + 1)
    deck[i], deck[j] = deck[j], deck[i]

print("=== Blackjack Deck Verification ===")
print("Initial deal (first 4 cards):")
print(f"  Player: {{deck[-1]}}, {{deck[-2]}}")
print(f"  Dealer: {{deck[-3]}}, {{deck[-4]}} (hidden)")
print("\\nNext cards available:")
for i in range(5, min(10, len(deck))):
    print(f"  Card {{i-4}}: {{deck[-i]}}")
"""

    elif game_type == "coinflip":
        game_code = """# Coinflip Verification
result = get_provably_fair_result(server_seed, client_seed, nonce, 2)
outcome = "Heads" if result == 0 else "Tails"

print("=== Coinflip Verification ===")
print(f"Result: {{result}} ({{outcome}})")
print(f"Hash: {{create_hash(server_seed, client_seed, nonce)[:16]}}...")
"""

    elif game_type == "keno":
        game_code = """# Keno Verification
def generate_keno_numbers(server_seed, client_seed, nonce, count=10):
    numbers = []
    offset = 0
    # IMPORTANT: Use nonce * 1000 to ensure unique results for consecutive games
    base_nonce = nonce * 1000
    while len(numbers) < count:
        num = get_provably_fair_result(server_seed, client_seed, base_nonce + offset, 40) + 1
        if num not in numbers:
            numbers.append(num)
        offset += 1
    return sorted(numbers)

keno_numbers = generate_keno_numbers(server_seed, client_seed, nonce, 10)

print("=== Keno Verification ===")
print(f"Drawn Numbers (1-40): {{keno_numbers}}")
print(f"Total drawn: {{len(keno_numbers)}}")
"""

    else:
        # Generic verification for other games
        game_code = """# Generic Game Verification
game_hash = create_hash(server_seed, client_seed, nonce)

print(f"=== Game Verification ===")
print(f"Game Hash: {{game_hash}}")
print(f"First 8 hex chars: {{game_hash[:8]}}")
print(f"Decimal value: {{int(game_hash[:8], 16)}}")

# Common game results
print("\\nPossible results for different games:")
print(f"  Coinflip (0-1): {{get_provably_fair_result(server_seed, client_seed, nonce, 2)}}")
print(f"  Dice (1-6): {{get_provably_fair_result(server_seed, client_seed, nonce, 6) + 1}}")
print(f"  Roulette (0-36): {{get_provably_fair_result(server_seed, client_seed, nonce, 37)}}")
"""

    return f"```python\n{base_code}{game_code}\n```"

async def monitor_escrow_deposit(context: ContextTypes.DEFAULT_TYPE):
    deal_id = context.job.data["deal_id"]
    deal = escrow_deals.get(deal_id)
    if not deal or deal['status'] != 'accepted_awaiting_deposit':
        logging.info(f"Stopping monitor for deal {deal_id}, status is {deal.get('status', 'N/A')}"); context.job.schedule_removal(); return

    logging.info(f"Checking for escrow deposit for deal {deal_id}...")
    try:
        url = f"https://api.bscscan.com/api?module=account&action=tokentx&contractaddress={ESCROW_DEPOSIT_TOKEN_CONTRACT}&address={ESCROW_DEPOSIT_ADDRESS}&sort=desc&apikey={DEPOSIT_API_KEY}"
        async with httpx.AsyncClient() as client: response = await client.get(url, timeout=20.0); data = response.json()

        if data['status'] == '1' and data['result']:
            for tx in data['result']:
                if tx['to'].lower() == ESCROW_DEPOSIT_ADDRESS.lower() and tx['hash'] not in deal.get('processed_txs', []):
                    tx_amount_usdt = int(tx['value']) / (10**ESCROW_DEPOSIT_TOKEN_DECIMALS)
                    if tx_amount_usdt >= deal['amount']:
                        logging.info(f"Detected valid deposit for deal {deal_id}, tx: {tx['hash']}. Amount: {tx_amount_usdt} USDT.")
                        deal.update({'amount': tx_amount_usdt, 'status': 'funds_secured', 'deposit_tx_hash': tx['hash']})
                        if 'processed_txs' not in deal: deal['processed_txs'] = []
                        deal['processed_txs'].append(tx['hash'])
                        save_escrow_deal(deal_id)

                        seller_id, buyer_id = deal['seller']['id'], deal['buyer']['id']
                        seller_msg = (f"{pe('check')} Deposit of ${tx_amount_usdt:.2f} USDT confirmed for deal <code>{deal_id}</code>. Funds are secured.\n\n"
                                      f"You may now proceed with the buyer. Once they confirm receipt, use the button below to release the funds to them.")
                        buyer_msg = (f"{pe('check')} The seller has deposited ${tx_amount_usdt:.2f} USDT for deal <code>{deal_id}</code>. The funds are now secured by the bot.\n\n"
                                     f"Please proceed with the transaction. Let the seller know once you have received the goods/services as agreed.")

                        # Enhanced attractive buttons
                        keyboard_seller = [
                            [InlineKeyboardButton("Release Funds to Buyer", callback_data=f"escrow_action_{deal_id}_release")],
                            [InlineKeyboardButton("Open Dispute", callback_data=f"escrow_action_{deal_id}_dispute")]
                        ]
                        keyboard_buyer = [
                            [InlineKeyboardButton("Open Dispute", callback_data=f"escrow_action_{deal_id}_dispute")]
                        ]

                        await context.bot.send_message(seller_id, seller_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard_seller))
                        await context.bot.send_message(buyer_id, buyer_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard_buyer))
                        context.job.schedule_removal()
                        return
    except Exception as e: logging.error(f"Error monitoring escrow deposit for deal {deal_id}: {e}", exc_info=True)

async def release_escrow_funds(update: Update, context: ContextTypes.DEFAULT_TYPE, deal_id: str):
    deal = escrow_deals.get(deal_id)
    if not deal or deal['status'] != 'funds_secured': await update.message.reply_text("This deal is not ready for fund release."); return
    if not all([ESCROW_WALLET_PRIVATE_KEY, w3_bsc]):
        await update.message.reply_text("Escrow wallet not configured. Contacting admin.")
        await context.bot.send_message(BOT_OWNER_ID, f"FATAL: Attempted to release funds for deal {deal_id} but PK or web3 is missing!")
        return

    try:
        w3 = w3_bsc
        contract = w3.eth.contract(address=Web3.to_checksum_address(ESCROW_DEPOSIT_TOKEN_CONTRACT), abi=ERC20_ABI)
        amount_wei = int(deal['amount'] * (10**ESCROW_DEPOSIT_TOKEN_DECIMALS))
        to_address, from_address = Web3.to_checksum_address(deal['buyer']['withdrawal_address']), Web3.to_checksum_address(ESCROW_DEPOSIT_ADDRESS)
        tx = contract.functions.transfer(to_address, amount_wei).build_transaction({
            'chainId': 56, 'gas': 150000, 'gasPrice': w3.eth.gas_price, 'nonce': w3.eth.get_transaction_count(from_address)})
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=ESCROW_WALLET_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt.status == 1:
            deal.update({'status': 'completed', 'release_tx_hash': tx_hash.hex()}); save_escrow_deal(deal_id)
            explorer_url = f"https://bscscan.com/tx/{tx_hash.hex()}"
            success_msg = f"{pe('check')} Deal {deal_id} completed! ${deal['amount']:.2f} USDT sent to the buyer. Explorer: {explorer_url}"
            await context.bot.send_message(deal['seller']['id'], success_msg); await context.bot.send_message(deal['buyer']['id'], success_msg)
        else: raise Exception("Transaction failed on-chain.")
    except Exception as e:
        logging.error(f"FATAL ERROR releasing funds for deal {deal_id}: {e}", exc_info=True)
        deal['status'] = 'release_failed'; save_escrow_deal(deal_id)
        fail_msg = f"🚨 An error occurred releasing funds for deal {deal_id}. Contact @Ittz_surajj immediately."
        await context.bot.send_message(deal['seller']['id'], fail_msg); await context.bot.send_message(deal['buyer']['id'], fail_msg)
        await context.bot.send_message(BOT_OWNER_ID, f"FATAL ERROR releasing funds for deal {deal_id}: {e}")

@check_banned
@check_maintenance
async def escrow_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only command to manually mark escrow deposit as received"""
    user = update.effective_user

    # Check if user is owner
    if not is_admin(user.id):
        await update.message.reply_text("This command is only available to the bot owner.")
        return

    # Check if escrow_id is provided
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /add <escrow_id>\n\nExample: /add ESC_ABC123")
        return

    deal_id = context.args[0]
    deal = escrow_deals.get(deal_id)

    if not deal:
        await update.message.reply_text(f"{pe('cross')} Escrow deal {deal_id} not found.")
        return

    if deal['status'] != 'accepted_awaiting_deposit':
        await update.message.reply_text(f"{pe('cross')} Deal {deal_id} is not awaiting deposit. Current status: {deal['status']}")
        return

    # Mark deposit as received
    deal['status'] = 'funds_secured'
    deal['deposit_tx_hash'] = 'MANUAL_CONFIRMATION_BY_OWNER'
    save_escrow_deal(deal_id)

    # Notify both parties
    seller_id = deal['seller']['id']
    buyer_id = deal['buyer']['id']

    seller_msg = (f"{pe('check')} Deposit for deal <code>{deal_id}</code> has been confirmed by @Ittz_surajj. Funds are secured.\n\n"
                  f"Amount: ${deal['amount']:.2f} USDT\n\n"
                  f"You may now proceed with the buyer. Once they confirm receipt, use the button below to release the funds to them.")

    buyer_msg = (f"{pe('check')} The seller's deposit for deal <code>{deal_id}</code> has been confirmed by @Ittz_surajj.\n\n"
                 f"Amount: ${deal['amount']:.2f} USDT\n\n"
                 f"The funds are now secured by the bot. Please proceed with the transaction. Let the seller know once you have received the goods/services as agreed.")

    # Create enhanced buttons with better styling
    keyboard_seller = [
        [InlineKeyboardButton("Release Funds to Buyer", callback_data=f"escrow_action_{deal_id}_release")],
        [InlineKeyboardButton("Open Dispute", callback_data=f"escrow_action_{deal_id}_dispute")]
    ]

    keyboard_buyer = [
        [InlineKeyboardButton("Open Dispute", callback_data=f"escrow_action_{deal_id}_dispute")]
    ]

    await context.bot.send_message(seller_id, seller_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard_seller))
    await context.bot.send_message(buyer_id, buyer_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard_buyer))

    # Confirm to owner
    await update.message.reply_text(
        f"{pe('check')} Deposit for deal <code>{deal_id}</code> has been manually confirmed.\n\n"
        f"Amount: ${deal['amount']:.2f} USDT\n"
        f"Seller: {deal['seller']['username']} (ID: {seller_id})\n"
        f"Buyer: {deal['buyer']['username']} (ID: {buyer_id})\n\n"
        f"Both parties have been notified.",
        parse_mode=ParseMode.HTML
    )

async def escrow_toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle escrow feature on/off. Usage: /escrow on|off"""
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text(f"{pe('cross')} This is an admin-only command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args or context.args[0].lower() not in ['on', 'off']:
        current_status = "enabled" if bot_settings.get("escrow_enabled", True) else "disabled"
        await update.message.reply_text(
            f"🛡️ <b>Escrow Feature Status</b>\n\n"
            f"Current: <b>{current_status.upper()}</b>\n\n"
            f"Usage: <code>/escrow on</code> or <code>/escrow off</code>",
            parse_mode=ParseMode.HTML
        )
        return

    action = context.args[0].lower()
    if action == 'off':
        bot_settings["escrow_enabled"] = False
        save_bot_state()
        await update.message.reply_text(f"{pe('check')} Escrow feature has been <b>DISABLED</b>. Users will not be able to access escrow services.", parse_mode=ParseMode.HTML)
    else:
        bot_settings["escrow_enabled"] = True
        save_bot_state()
        await update.message.reply_text(f"{pe('check')} Escrow feature has been <b>ENABLED</b>. Users can now access escrow services.", parse_mode=ParseMode.HTML)

def register(ctx):
    """No main() add_handler entries reference this bucket.
    Plugin still loads so its admin hooks work."""
    return None

