"""Auto-split from bot.py — plugins.games_plinko."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def _validate_telegram_webapp_data(init_data_raw: str) -> dict | None:
    """Validate Telegram WebApp initData using HMAC-SHA256.

    Security measures:
    1. HMAC-SHA256 signature verification using BOT_TOKEN
    2. auth_date expiry check (prevents replay attacks)
    3. Strict parameter parsing

    Returns parsed user dict on success, None on failure.
    """
    if not init_data_raw or not isinstance(init_data_raw, str):
        return None
    try:
        import urllib.parse as urlparse
        params = dict(urlparse.parse_qsl(init_data_raw, keep_blank_values=True))
        received_hash = params.pop('hash', '')
        if not received_hash or len(received_hash) != 64:
            logging.warning("Plinko auth: missing or invalid hash length")
            return None

        # --- Anti-replay: check auth_date is not too old ---
        auth_date_str = params.get('auth_date', '')
        if not auth_date_str:
            logging.warning("Plinko auth: missing auth_date")
            return None
        try:
            auth_date = int(auth_date_str)
            now_ts = int(datetime.now(timezone.utc).timestamp())
            age = now_ts - auth_date
            if age < -60:  # Allow 60s clock skew
                logging.warning(f"Plinko auth: auth_date is in the future by {abs(age)}s")
                return None
            if age > PLINKO_AUTH_MAX_AGE_SECONDS:
                logging.warning(f"Plinko auth: initData expired ({age}s old, max {PLINKO_AUTH_MAX_AGE_SECONDS}s)")
                return None
        except (ValueError, TypeError):
            logging.warning("Plinko auth: invalid auth_date format")
            return None

        # --- HMAC-SHA256 signature verification ---
        # Build check string (alphabetically sorted key=value pairs)
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(params.items()))

        # Two-step HMAC: first derive secret from "WebAppData" + BOT_TOKEN,
        # then sign the data_check_string
        secret_key = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            logging.warning("Plinko auth: HMAC signature mismatch")
            return None

        # --- Parse and validate user JSON ---
        user_json = params.get('user', '')
        if not user_json:
            logging.warning("Plinko auth: missing user field")
            return None
        user_data = json.loads(user_json)
        if not isinstance(user_data, dict) or 'id' not in user_data:
            logging.warning("Plinko auth: user data missing 'id' field")
            return None
        # Ensure user_id is an integer
        if not isinstance(user_data['id'], int):
            logging.warning("Plinko auth: user id is not an integer")
            return None

        return user_data
    except json.JSONDecodeError:
        logging.warning("Plinko auth: invalid user JSON")
        return None
    except Exception as e:
        logging.error(f"Plinko auth validation error: {e}")
        return None

def _plinko_check_rate_limit(user_id: int) -> tuple:
    """Check if user can place a bet. Uses sliding window rate limiting.

    Returns:
        (allowed: bool, retry_after_seconds: float)
        - If allowed is True, retry_after is 0
        - If allowed is False, retry_after is seconds until they can bet again
    """
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - 60  # 1 minute sliding window

    # Initialize if needed
    if user_id not in _plinko_rate_limits:
        _plinko_rate_limits[user_id] = []

    # Prune expired timestamps (sliding window)
    timestamps = _plinko_rate_limits[user_id]
    # Use bisect for O(log n) finding of cutoff point
    import bisect
    idx = bisect.bisect_left(timestamps, cutoff)
    if idx > 0:
        del timestamps[:idx]

    # Check rate limit
    if len(timestamps) >= PLINKO_RATE_LIMIT_BETS_PER_MIN:
        # Calculate when the oldest entry will expire
        oldest = timestamps[0] if timestamps else now
        retry_after = (oldest + 60) - now
        return False, max(PLINKO_RATE_LIMIT_COOLDOWN_SEC, round(retry_after, 1))

    # Check minimum cooldown between bets (prevents double-tap / race conditions)
    last_bet = _plinko_last_bet_time.get(user_id, 0)
    elapsed_ms = (now - last_bet) * 1000
    if elapsed_ms < PLINKO_MIN_BET_COOLDOWN_MS:
        retry_after = (PLINKO_MIN_BET_COOLDOWN_MS - elapsed_ms) / 1000
        return False, round(retry_after, 2)

    # Allow the bet and record timestamp
    timestamps.append(now)
    _plinko_last_bet_time[user_id] = now
    return True, 0

async def _plinko_get_user_from_request(request: aiohttp.web.Request) -> dict | None:
    """Extract and validate user from Plinko web request.
    Uses Telegram WebApp initData from X-Auth-Token header."""
    auth_token = request.headers.get('X-Auth-Token', '')
    if not auth_token:
        return None
    user_data = _validate_telegram_webapp_data(auth_token)
    if not user_data or 'id' not in user_data:
        return None
    return user_data

async def plinko_health_check(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Health check endpoint for monitoring."""
    import psutil
    import os as _os
    process = psutil.Process(_os.getpid())
    return aiohttp.web.json_response({
        "status": "healthy",
        "bot_running": not bot_stopped,
        "users_loaded": len(user_stats),
        "active_games": sum(1 for g in game_sessions.values() if g.get('status') == 'active'),
        "pending_withdrawals": sum(1 for w in withdrawal_requests.values() if w.get('status') == 'pending'),
        "memory_mb": round(process.memory_info().rss / 1024 / 1024, 1),
        "cpu_percent": process.cpu_percent(),
    })

async def plinko_serve_html(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Serve the Plinko web dashboard HTML (cached in memory with ETag support).
    Optimized for high load: 300s cache TTL + ETag for conditional requests."""
    global _plinko_html_cache, _plinko_html_cache_time, _plinko_html_cache_etag
    now = datetime.now(timezone.utc).timestamp()

    # Cache HTML for 300 seconds (5 minutes) to reduce disk reads under 4k+ load
    if _plinko_html_cache is None or (now - _plinko_html_cache_time) > 300:
        html_path = os.path.join(BASE_DIR, 'plinko_web', 'index.html')
        if not os.path.exists(html_path):
            return aiohttp.web.Response(text="Plinko dashboard not found", status=404)
        with open(html_path, 'r', encoding='utf-8') as f:
            _plinko_html_cache = f.read()
        _plinko_html_cache_time = now
        # Generate ETag from content
        import hashlib
        _plinko_html_cache_etag = '"' + hashlib.md5(_plinko_html_cache.encode()).hexdigest() + '"'

    # Check If-None-Match for conditional request
    if_none_match = request.headers.get('If-None-Match', '')
    if if_none_match == _plinko_html_cache_etag:
        return aiohttp.web.Response(status=304)

    return aiohttp.web.Response(
        text=_plinko_html_cache,
        content_type='text/html',
        headers={
            'Cache-Control': 'public, max-age=300',
            'ETag': _plinko_html_cache_etag,
            'X-Content-Type-Options': 'nosniff',
            # X-Frame-Options removed: conflicts with CSP and blocks Telegram WebView
            'Content-Security-Policy': "frame-ancestors 'self' https://*.telegram.org https://telegram.org",
            'Access-Control-Allow-Origin': '*',
            'Connection': 'keep-alive',
        }
    )

async def plinko_api_user(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """GET /plinko/api/user - Get user balance and provably fair seeds.

    Security: Authenticated via Telegram WebApp initData (HMAC-SHA256).
    Only returns server_seed_hash (never the raw server seed).
    """
    user_data = await _plinko_get_user_from_request(request)
    if not user_data:
        return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)

    user_id = user_data['id']
    username = user_data.get('username', user_data.get('first_name', 'Player'))

    # Ensure user exists in wallets (must have used /start first)
    if user_id not in user_stats:
        return aiohttp.web.json_response({"error": "Please start the bot first with /start"}, status=403)

    # Check all ban types
    if user_id in _banned_set or user_id in _tempbanned_set:
        return aiohttp.web.json_response({"error": "Account restricted"}, status=403)

    # Check maintenance mode
    if bot_settings.get("maintenance_mode", False):
        return aiohttp.web.json_response({"error": "Bot is under maintenance"}, status=503)

    balance_usd = get_active_balance_usd(user_id)
    active_coin = get_active_currency(user_id)

    # Get or generate provably fair seeds
    seeds = get_user_seeds(user_id)
    # SECURITY: Only return the HASH of the server seed, never the raw seed
    server_seed_hash = hashlib.sha256(seeds['server_seed'].encode()).hexdigest()

    return aiohttp.web.json_response({
        "user_id": user_id,
        "username": username,
        "balance": round(balance_usd, 2),
        "active_coin": active_coin,
        "server_seed_hash": server_seed_hash,
        "client_seed": seeds['client_seed'],
        "nonce": seeds.get('nonce', 0)
    })

async def plinko_api_bet(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """POST /plinko/api/bet - Place a Plinko bet from web dashboard.

    Security measures:
    1. Telegram WebApp initData HMAC-SHA256 authentication
    2. auth_date anti-replay (max 1 hour)
    3. Per-user rate limiting (60 bets/minute)
    4. Request body size limit (4KB)
    5. Input validation (NaN/Infinity/negative/type checks)
    6. Atomic wallet deduction (async lock prevents double-spend)
    7. Ban and maintenance checks
    8. Provably fair result generation
    """
    # --- Auth ---
    user_data = await _plinko_get_user_from_request(request)
    if not user_data:
        return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)

    user_id = user_data['id']
    if user_id not in user_stats:
        return aiohttp.web.json_response({"error": "Please start the bot first"}, status=403)

    # --- Ban checks (permanent + temporary) ---
    if user_id in _banned_set or user_id in _tempbanned_set:
        return aiohttp.web.json_response({"error": "Account restricted"}, status=403)

    # --- Maintenance mode ---
    if bot_settings.get("maintenance_mode", False):
        return aiohttp.web.json_response({"error": "Bot is under maintenance"}, status=503)

    # --- Game enabled check ---
    if not is_game_enabled("plinko"):
        return aiohttp.web.json_response({"error": "Plinko is under maintenance"}, status=503)

    # --- Rate limiting ---
    allowed, retry_after = _plinko_check_rate_limit(user_id)
    if not allowed:
        return aiohttp.web.json_response(
            {"error": f"Too many bets. Try again in {retry_after:.1f}s."},
            status=429,
            headers={"Retry-After": str(int(retry_after) + 1)}
        )

    # --- Request body size limit ---
    if request.content_length and request.content_length > PLINKO_MAX_REQUEST_BODY_BYTES:
        return aiohttp.web.json_response({"error": "Request too large"}, status=413)

    try:
        body = await request.json()
    except Exception:
        return aiohttp.web.json_response({"error": "Invalid request body"}, status=400)

    if not isinstance(body, dict):
        return aiohttp.web.json_response({"error": "Invalid request format"}, status=400)

    # --- Extract and validate bet parameters ---
    bet_amount = body.get('amount', 0)
    risk = body.get('risk', 'medium')
    rows = body.get('rows', 16)

    # Type coercion safety
    try:
        bet_amount = float(bet_amount)
        rows = int(rows)
    except (ValueError, TypeError):
        return aiohttp.web.json_response({"error": "Invalid parameter types"}, status=400)

    # NaN / Infinity / negative checks
    if not math.isfinite(bet_amount) or bet_amount <= 0:
        return aiohttp.web.json_response({"error": "Invalid bet amount"}, status=400)

    if bet_amount < PLINKO_WEB_MIN_BET:
        return aiohttp.web.json_response({"error": f"Minimum bet is ${PLINKO_WEB_MIN_BET:.2f}"}, status=400)
    # Use dynamic max bet (min of static and dynamic)
    _plinko_dyn_max = min(PLINKO_WEB_MAX_BET, get_dynamic_max_bet("originals", "plinko"))
    if bet_amount > _plinko_dyn_max:
        return aiohttp.web.json_response({"error": f"Maximum bet is ${_plinko_dyn_max:.2f}"}, status=400)

    # Round to 2 decimal places to prevent floating point exploits
    bet_amount = round(bet_amount, 2)

    if not isinstance(risk, str) or risk not in ('low', 'medium', 'high'):
        return aiohttp.web.json_response({"error": "Invalid risk level"}, status=400)
    if rows not in (8, 10, 12, 14, 16):
        return aiohttp.web.json_response({"error": "Invalid row count"}, status=400)

    # --- Atomic balance deduction (per-user lock prevents double-spend) ---
    try:
        crypto_deducted, coin = await deduct_wallet_safe(user_id, bet_amount)
    except ValueError:
        return aiohttp.web.json_response({"error": "Insufficient balance"}, status=400)

    # --- Get multipliers for this row/risk combo ---
    mults = PLINKO_WEB_MULTIPLIERS.get(rows, {}).get(risk, PLINKO_MULTIPLIERS.get(risk, [1.0]))
    num_slots = len(mults)

    # --- Generate provably fair result using binomial distribution ---
    # Stake.com-style: N rows = N peg collisions = N binary left/right decisions
    # The sum of right-bounces determines the slot (binomial distribution)
    seeds = get_user_seeds(user_id)
    server_seed = seeds['server_seed']
    client_seed = seeds['client_seed']
    nonce = seeds.get('nonce', 0)
    result_index = get_plinko_slot_result(server_seed, client_seed, nonce, rows)
    multiplier = mults[result_index]

    winnings = round(bet_amount * multiplier, 8)  # Precision for crypto
    profit = round(winnings - bet_amount, 8)
    win = multiplier >= 1.0

    # --- Credit winnings ---
    credit_wallet(user_id, winnings)

    # --- Generate game ID and increment nonce ---
    game_id = generate_unique_id('PLINKO')
    increment_user_nonce(user_id)

    # --- Update stats (fire-and-forget for non-critical tasks) ---
    await update_stats_on_bet(user_id, game_id, bet_amount, win, multiplier=multiplier, context=None)
    save_user_data(user_id)

    # --- Store game session (for history and provably fair verification) ---
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "plinko",
        "user_id": user_id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user_id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user_id), 1.0),
        "risk": risk,
        "rows": rows,
        "result_index": result_index,
        "multiplier": multiplier,
        "status": "completed",
        "timestamp": str(datetime.now(timezone.utc)),
        "win": win,
        "profit": profit,
        "server_seed": server_seed,
        "client_seed": client_seed,
        "nonce": nonce,
        "source": "web"
    }

    # Store provably fair record
    store_provably_fair_record(game_id, "plinko", server_seed, client_seed, nonce,
                               result_data=f"Risk: {risk}, Rows: {rows}, Slot: {result_index + 1}, Multiplier: {multiplier}x")

    new_balance = get_active_balance_usd(user_id)

    return aiohttp.web.json_response({
        "game_id": game_id,
        "slot": result_index,
        "multiplier": multiplier,
        "bet_amount": round(bet_amount, 2),
        "winnings": round(winnings, 2),
        "profit": round(profit, 2),
        "win": win,
        "new_balance": round(new_balance, 2),
        "nonce": nonce
    })

async def plinko_api_history(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """GET /plinko/api/history - Get user's recent plinko bets."""
    user_data = await _plinko_get_user_from_request(request)
    if not user_data:
        return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)

    user_id = user_data['id']

    # Ban check for history too
    if user_id in _banned_set:
        return aiohttp.web.json_response({"error": "Account restricted"}, status=403)

    stats = user_stats.get(user_id, {})
    game_ids = stats.get('game_sessions', [])

    bets = []
    for gid in reversed(game_ids[-50:]):
        game = game_sessions.get(gid)
        if game and game.get('game_type') == 'plinko' and game.get('status') == 'completed':
            bets.append({
                "game_id": game['id'],
                "risk": game.get('risk', 'medium'),
                "rows": game.get('rows', 16),
                "slot": game.get('result_index', 0),
                "multiplier": game.get('multiplier', 0),
                "bet_amount": round(game.get('bet_amount', 0), 2),
                "profit": round(game.get('bet_amount', 0) * game.get('multiplier', 0) - game.get('bet_amount', 0), 2),
                "win": game.get('win', False),
                "timestamp": game.get('timestamp', '')
            })
            if len(bets) >= 20:
                break

    return aiohttp.web.json_response({"bets": bets})

def get_plinko_slot_result(server_seed, client_seed, nonce, rows):
    """Calculate Plinko slot using Stake.com-style binomial distribution.

    For N rows, the ball hits N pegs. At each peg, we determine left(0) or right(1)
    using successive 4-byte chunks of the SHA-256 hash chain. The sum of right-bounces
    determines which slot (0..N) the ball lands in.

    This naturally produces a binomial distribution B(n=rows, p=0.5) where:
    - Center slots are most common (many ways to get ~n/2 rights)
    - Edge slots are rare (only one way to get 0 or n rights)
    - House edge is built into the multiplier table payouts
    """
    num_slots = rows + 1  # N rows produce N+1 slots
    right_bounces = 0

    # We need 'rows' binary decisions. Use hash chain for each decision.
    # Stake.com approach: hash = HMAC(server_seed, client_seed + ":" + nonce + ":" + round)
    # We use: sha256(server_seed + client_seed + ":" + str(nonce) + ":" + str(round))
    for r in range(rows):
        # Generate a hash for this specific peg/row decision
        decision_input = f"{server_seed}:{client_seed}:{nonce}:{r}"
        decision_hash = hashlib.sha256(decision_input.encode()).hexdigest()
        # Use first byte (0-255), threshold at 128 for ~50/50
        byte_val = int(decision_hash[:2], 16)
        if byte_val >= 128:
            right_bounces += 1

    # right_bounces (0 to rows) maps directly to slot index (0 to rows)
    # Slot 0 = all left (leftmost), Slot rows = all right (rightmost)
    return right_bounces

@check_banned
@check_maintenance
async def plinko_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_game_enabled("plinko"):
        await update.message.reply_text(
            "\U0001f527 <b>Plinko</b> game is currently under maintenance. Please try again later.",
            parse_mode=ParseMode.HTML
        )
        return
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # If no args or just /plinko, show WebApp button
    if len(args) == 1:
        plinko_web_url = _get_plinko_web_url() if PLINKO_WEB_ENABLED else None
        if plinko_web_url and update.effective_chat.type == "private":
            from telegram import WebAppInfo
            keyboard = [[InlineKeyboardButton(
                "Open Plinko",
                web_app=WebAppInfo(url=plinko_web_url)
            )]]
            await update.message.reply_text(
                f"{pe('plinko')} <b>PLINKO</b>\n\n"
                f"Drop the ball and win big! Choose your risk level, "
                f"number of rows, and watch the ball bounce.\n\n"
                f"Tap below to open the Plinko web dashboard:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        elif plinko_web_url:
            # In groups: direct user to bot DM for the Mini App
            bot_username = context.bot.username
            deep_link = f"https://t.me/{bot_username}?start=plinko"
            keyboard = [[InlineKeyboardButton(
                "Open Plinko in DM",
                url=deep_link
            )]]
            await update.message.reply_text(
                f"{pe('plinko')} <b>PLINKO</b>\n\n"
                f"Plinko Mini App is available in direct messages.\n"
                f"Tap below to open Plinko in the bot's DM:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

    if len(args) != 3:
        await update.message.reply_text("Usage: /plinko amount risk\nRisk: low, medium, or high\nExample: /plinko 5 medium")
        return

    try:
        bet_amount_str = args[1].lower()
        # Display-currency aware (parity with blackjack/tower).
        bet_amount, _bet_disp, _disp_cur = parse_bet_amount(bet_amount_str, user.id)

        risk = args[2].lower()
        if risk not in PLINKO_MULTIPLIERS:
            await update.message.reply_text("Risk must be: low, medium, or high")
            return
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet_amount, 'plinko'):
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
    result_index = get_provably_fair_result(server_seed, client_seed, 1, len(PLINKO_MULTIPLIERS[risk]))
    multiplier = PLINKO_MULTIPLIERS[risk][result_index]

    winnings = bet_amount * multiplier
    profit = winnings - bet_amount
    win = multiplier >= 1.0

    # Generate game ID first before using it
    game_id = generate_unique_id('PLINKO')

    credit_wallet(user.id, winnings)
    await update_stats_on_bet(user.id, game_id, bet_amount, win, multiplier=multiplier, context=context)
    save_user_data(user.id)

    # Store game session and provably fair record
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "plinko",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "active_currency": get_active_currency(user.id),
        "crypto_bet_amount": bet_amount / LIVE_PRICES.get(get_active_currency(user.id), 1.0),
        "risk": risk,
        "result_index": result_index,
        "multiplier": multiplier,
        "status": "completed",
        "timestamp": str(datetime.now(timezone.utc)),
        "win": win,
        "server_seed": server_seed,
        "client_seed": client_seed,
        "nonce": 1
    }

    # Store provably fair record
    store_provably_fair_record(game_id, "plinko", server_seed, client_seed, 1,
                               result_data=f"Risk: {risk}, Slot: {result_index + 1}, Multiplier: {multiplier:.2f}x")

    result_text = (
        f"🎪 <b>PLINKO</b>\n"
        f"Game ID: <code>{game_id}</code>\n\n"
        f"{pe('dice')} Risk Level: {risk.upper()}\n"
        f"{pe('target')} Landed in slot: {result_index + 1}\n"
        f"{pe('money')} Multiplier: {multiplier:.2f}x\n\n"
    )

    if win:
        result_text += f"{pe('win')} <b>WIN!</b>\n💵 Profit: ${profit:.2f}\n💸 Total Payout: ${winnings:.2f}"
    else:
        result_text += f"{pe('cross')} <b>LOST</b>\n💸 Lost: ${abs(profit):.2f}"

    # Create keyboard with provably fair button
    keyboard = [[await create_provably_fair_button(game_id, context)]]

    await update.message.reply_text(result_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

def register(ctx):
    """No main() add_handler entries reference this bucket.
    Plugin still loads so its admin hooks work."""
    return None

