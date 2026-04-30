"""Auto-split from bot.py — plugins.games_chicken_road."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def get_chicken_road_crash_step(server_seed: str, client_seed: str,
                                 nonce: int, mode: str) -> int:
    """
    Provably fair: determine which step the chicken hits a bone.
    Returns a step number in [1, max_steps+1].
    If result == max_steps + 1, the path is completely safe (all steps crossed).

    Uses HMAC-SHA256 to generate a deterministic random value, then determines
    the crash step using inverse transform sampling of the geometric distribution.

    Formula: crash_step = ceil(log(random) / log(p_survive))
    where p_survive = probability of surviving one step (varies by difficulty)

    This ensures the crash step follows the correct geometric distribution:
    - P(crash at step 1) = 1 - p_survive
    - P(crash at step 2) = p_survive * (1 - p_survive)
    - P(survive n steps) = p_survive^n
    """
    import hmac as _hmac_cr, hashlib as _hs_cr, math as _m_cr
    data = f"{client_seed}:{nonce}".encode('utf-8')
    key  = server_seed.encode('utf-8')
    h    = _hmac_cr.new(key, data, _hs_cr.sha256).hexdigest()

    # Convert first 8 hex chars to float in (0, 1)
    r = (int(h[:8], 16) + 1) / (2**32)

    cfg = CHICKEN_ROAD_MODES[mode]
    p_survive = cfg["p_survive"]
    max_steps = cfg["max_steps"]

    # Inverse transform sampling for geometric distribution
    # crash_step = ceil(log(r) / log(p_survive))
    crash_step = _m_cr.ceil(_m_cr.log(r) / _m_cr.log(p_survive))

    # Clamp to valid range [1, max_steps + 1]
    return max(1, min(int(crash_step), max_steps + 1))

def get_chicken_road_multiplier(step: int, mode: str) -> float:
    """Return the cash-out multiplier for the given step in the given mode."""
    table = CHICKEN_ROAD_MULT_TABLE.get(mode, [])
    if step < 1 or step > len(table):
        return 1.0
    return table[step - 1]

def _chicken_road_check_rate_limit(user_id: int) -> tuple:
    """Sliding window rate limiter for new game starts (NOT for step/cashout actions)."""
    now    = datetime.now(timezone.utc).timestamp()
    cutoff = now - 60.0
    if user_id not in _chicken_road_rate_limits:
        _chicken_road_rate_limits[user_id] = []
    timestamps = _chicken_road_rate_limits[user_id]
    idx = bisect.bisect_left(timestamps, cutoff)
    if idx > 0:
        del timestamps[:idx]
    if len(timestamps) >= CHICKEN_ROAD_RATE_LIMIT_BETS_PER_MIN:
        oldest     = timestamps[0] if timestamps else now
        retry      = (oldest + 60) - now
        return False, max(CHICKEN_ROAD_RATE_LIMIT_COOLDOWN_SEC, round(retry, 1))
    last_bet   = _chicken_road_last_bet_time.get(user_id, 0)
    elapsed_ms = (now - last_bet) * 1000
    if elapsed_ms < CHICKEN_ROAD_MIN_BET_COOLDOWN_MS:
        retry = (CHICKEN_ROAD_MIN_BET_COOLDOWN_MS - elapsed_ms) / 1000
        return False, round(retry, 2)
    timestamps.append(now)
    _chicken_road_last_bet_time[user_id] = now
    return True, 0.0

async def _cr_get_user_from_request(request: aiohttp.web.Request) -> dict | None:
    """Authenticate a Chicken Road web request via Telegram WebApp initData."""
    auth_token = request.headers.get('X-Auth-Token', '')
    if not auth_token:
        return None
    return _validate_telegram_webapp_data(auth_token)

async def cr_health_check(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Health check endpoint for monitoring."""
    import psutil
    import os as _os
    process = psutil.Process(_os.getpid())
    return aiohttp.web.json_response({
        "status": "healthy",
        "bot_running": not bot_stopped,
        "users_loaded": len(user_stats),
        "active_chicken_games": sum(1 for g in chicken_road_active_games.values() if g.get('status') == 'active'),
        "memory_mb": round(process.memory_info().rss / 1024 / 1024, 1),
        "cpu_percent": process.cpu_percent(),
    })

async def cr_serve_html(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Serve chicken_road_web/index.html with 300s cache and ETag support.
    Optimized for high load (4k+ concurrent users)."""
    global _chicken_road_html_cache, _chicken_road_html_cache_time, _chicken_road_html_cache_etag
    now = datetime.now(timezone.utc).timestamp()
    if _chicken_road_html_cache is None or (now - _chicken_road_html_cache_time) > 300:
        html_path = os.path.join(BASE_DIR, 'chicken_road_web', 'index.html')
        if not os.path.exists(html_path):
            return aiohttp.web.Response(text="Chicken Road not found", status=404)
        with open(html_path, 'r', encoding='utf-8') as f:
            _chicken_road_html_cache = f.read()
        _chicken_road_html_cache_time = now
        import hashlib
        _chicken_road_html_cache_etag = '"' + hashlib.md5(_chicken_road_html_cache.encode()).hexdigest() + '"'

    # Check If-None-Match for conditional request
    if_none_match = request.headers.get('If-None-Match', '')
    if if_none_match == _chicken_road_html_cache_etag:
        return aiohttp.web.Response(status=304)

    return aiohttp.web.Response(
        text=_chicken_road_html_cache,
        content_type='text/html',
        headers={
            'Cache-Control':          'public, max-age=300',
            'ETag':                   _chicken_road_html_cache_etag,
            'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "frame-ancestors 'self' https://*.telegram.org https://telegram.org",
            'Access-Control-Allow-Origin': '*',
            'Connection':             'keep-alive',
            'X-Frame-Options':      'DENY',
            'Content-Security-Policy': "frame-ancestors 'self' https://*.telegram.org",
        }
    )

async def cr_api_user(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """GET /chicken-road/api/user — returns balance, seeds, and active game if any."""
    user_data = await _cr_get_user_from_request(request)
    if not user_data:
        return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)

    user_id  = user_data['id']
    username = user_data.get('username', user_data.get('first_name', 'Player'))

    if user_id in _banned_set:
        return aiohttp.web.json_response({"error": "Account restricted"}, status=403)

    await ensure_user_in_wallets(user_id, username)
    seeds   = get_user_seeds(user_id)
    balance = get_active_balance_usd(user_id)

    import hashlib as _hs2
    server_seed_hash = _hs2.sha256(seeds['server_seed'].encode()).hexdigest()

    active_game = None
    existing    = chicken_road_active_games.get(user_id)
    if existing and existing.get('status') == 'active':
        mode_cfg  = CHICKEN_ROAD_MODES.get(existing['mode'], {})
        max_steps = mode_cfg.get('max_steps', 24)
        steps_taken = existing.get('steps_taken', 0)
        next_step   = steps_taken + 1
        active_game = {
            "game_id":      existing['id'],
            "mode":         existing['mode'],
            "bet_amount":   round(existing['bet_amount'], 2),
            "steps_taken":  steps_taken,
            "max_steps":    max_steps,
            "current_mult": get_chicken_road_multiplier(steps_taken, existing['mode'])
                            if steps_taken > 0 else 0.0,
            "next_mult":    get_chicken_road_multiplier(next_step, existing['mode'])
                            if next_step <= max_steps else 0.0,
            "mult_table":   CHICKEN_ROAD_MULT_TABLE.get(existing['mode'], []),
            "timestamp":    existing.get('timestamp', ''),
        }

    return aiohttp.web.json_response({
        "user_id":          user_id,
        "username":         username,
        "balance":          round(balance, 2),
        "server_seed_hash": server_seed_hash,
        "client_seed":      seeds['client_seed'],
        "nonce":            seeds.get('nonce', 0),
        "active_game":      active_game,
    })

async def cr_api_bet(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """POST /chicken-road/api/bet — start a new Chicken Road round."""
    user_data = await _cr_get_user_from_request(request)
    if not user_data:
        return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)

    user_id  = user_data['id']
    username = user_data.get('username', user_data.get('first_name', 'Player'))

    if user_id in _banned_set:
        return aiohttp.web.json_response({"error": "Account restricted"}, status=403)

    if not is_game_enabled("chicken_road"):
        return aiohttp.web.json_response({"error": "Game under maintenance"}, status=503)

    if chicken_road_active_games.get(user_id, {}).get('status') == 'active':
        return aiohttp.web.json_response(
            {"error": "You already have an active round. Cash out or continue it first."},
            status=409
        )

    allowed, retry_after = _chicken_road_check_rate_limit(user_id)
    if not allowed:
        return aiohttp.web.json_response(
            {"error": "Rate limited", "retry_after": retry_after}, status=429
        )

    if request.content_length and request.content_length > CHICKEN_ROAD_MAX_REQUEST_BODY_BYTES:
        return aiohttp.web.json_response({"error": "Request too large"}, status=413)
    try:
        body = await request.json()
    except Exception:
        return aiohttp.web.json_response({"error": "Invalid JSON"}, status=400)

    bet_amount = body.get('bet_amount')
    mode       = str(body.get('mode', 'medium')).lower().strip()

    import math as _math_cr
    try:
        bet_amount = float(bet_amount)
        if not _math_cr.isfinite(bet_amount):
            raise ValueError
    except (TypeError, ValueError):
        return aiohttp.web.json_response({"error": "Invalid bet amount"}, status=400)

    if mode not in CHICKEN_ROAD_MODES:
        return aiohttp.web.json_response({"error": "Invalid mode"}, status=400)

    if bet_amount < CHICKEN_ROAD_WEB_MIN_BET:
        return aiohttp.web.json_response(
            {"error": f"Minimum bet is ${CHICKEN_ROAD_WEB_MIN_BET:.2f}"}, status=400)
    # Use dynamic max bet (min of static and dynamic)
    _cr_dyn_max = min(CHICKEN_ROAD_WEB_MAX_BET, get_dynamic_max_bet("originals", "chicken_road"))
    if bet_amount > _cr_dyn_max:
        return aiohttp.web.json_response(
            {"error": f"Maximum bet is ${_cr_dyn_max:.2f}"}, status=400)

    lock = _chicken_road_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        if chicken_road_active_games.get(user_id, {}).get('status') == 'active':
            return aiohttp.web.json_response(
                {"error": "Active round already in progress."}, status=409)

        try:
            crypto_deducted, coin = await deduct_wallet_safe(user_id, bet_amount)
        except ValueError:
            return aiohttp.web.json_response({"error": "Insufficient balance"}, status=400)

        seeds      = get_user_seeds(user_id)
        ss, cs, nc = seeds['server_seed'], seeds['client_seed'], seeds.get('nonce', 0)
        crash_step = get_chicken_road_crash_step(ss, cs, nc, mode)

        mode_cfg   = CHICKEN_ROAD_MODES[mode]
        max_steps  = mode_cfg['max_steps']
        game_id    = generate_unique_id('CR')

        active_cur = get_active_currency(user_id)
        game_state = {
            "id":             game_id,
            "game_type":      "chicken_road",
            "user_id":        user_id,
            "bet_amount":     bet_amount,
            "mode":           mode,
            "crash_step":     crash_step,
            "max_steps":      max_steps,
            "steps_taken":    0,
            "current_mult":   0.0,
            "status":         "active",
            "cashout_step":   None,
            "cashout_mult":   None,
            "win":            False,
            "profit":         -bet_amount,
            "payout":         0.0,
            "server_seed":    ss,
            "client_seed":    cs,
            "nonce":          nc,
            "active_currency": active_cur,
            "crypto_bet_amount": bet_amount / LIVE_PRICES.get(active_cur, 1.0) if active_cur else bet_amount,
            "timestamp":      str(datetime.now(timezone.utc)),
            "source":         "web",
        }

        chicken_road_active_games[user_id] = game_state
        game_sessions[game_id]             = game_state
        user_stats.setdefault(user_id, {}).setdefault('game_sessions', []).append(game_id)
        increment_user_nonce(user_id)
        save_user_data(user_id)

    return aiohttp.web.json_response({
        "game_id":     game_id,
        "mode":        mode,
        "bet_amount":  round(bet_amount, 2),
        "steps_taken": 0,
        "max_steps":   max_steps,
        "mult_table":  CHICKEN_ROAD_MULT_TABLE[mode],
        "next_mult":   get_chicken_road_multiplier(1, mode),
        "new_balance": round(get_active_balance_usd(user_id), 2),
        "nonce":       nc,
    })

async def cr_api_step(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """POST /chicken-road/api/step — advance the chicken one step."""
    user_data = await _cr_get_user_from_request(request)
    if not user_data:
        return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)

    user_id = user_data['id']
    if user_id in _banned_set:
        return aiohttp.web.json_response({"error": "Account restricted"}, status=403)

    try:
        body    = await request.json()
        game_id = str(body.get('game_id', ''))
    except Exception:
        return aiohttp.web.json_response({"error": "Invalid JSON"}, status=400)

    lock = _chicken_road_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        game = chicken_road_active_games.get(user_id)
        if not game or game.get('id') != game_id or game.get('status') != 'active':
            return aiohttp.web.json_response({"error": "No active game found"}, status=404)

        steps_taken = game['steps_taken']
        new_step    = steps_taken + 1
        mode        = game['mode']
        crash_step  = game['crash_step']
        max_steps   = game['max_steps']
        bet_amount  = game['bet_amount']

        if new_step == crash_step:
            # FIRE: chicken dies
            game['steps_taken']  = new_step
            game['status']       = 'dead'
            game['win']          = False
            game['payout']       = 0.0
            game['profit']       = -bet_amount
            game['current_mult'] = get_chicken_road_multiplier(new_step, mode) \
                                   if new_step <= max_steps else 0.0
            del chicken_road_active_games[user_id]
            game_sessions[game_id] = game

            await update_stats_on_bet(user_id, game_id, bet_amount,
                                      win=False, multiplier=0.0, context=None)
            store_provably_fair_record(
                game_id, "chicken_road", game['server_seed'], game['client_seed'],
                game['nonce'],
                result_data=f"Mode:{mode}, CrashStep:{crash_step}, Bet:{bet_amount:.2f}, Outcome:FIRE"
            )
            save_user_data(user_id)

            return aiohttp.web.json_response({
                "outcome":      "fire",
                "steps_taken":  new_step,
                "current_mult": game['current_mult'],
                "next_mult":    None,
                "payout":       0.0,
                "profit":       round(-bet_amount, 2),
                "new_balance":  round(get_active_balance_usd(user_id), 2),
                "server_seed":  game['server_seed'],
                "crash_step":   crash_step,
            })

        elif new_step >= max_steps and crash_step > max_steps:
            # COMPLETE: crossed all steps safely — auto-cashout
            final_mult  = get_chicken_road_multiplier(max_steps, mode)
            raw_payout  = round(bet_amount * final_mult, 8)
            payout      = min(raw_payout, CHICKEN_ROAD_WEB_MAX_WIN)
            profit      = round(payout - bet_amount, 8)
            credit_wallet(user_id, payout)

            game['steps_taken']  = max_steps
            game['current_mult'] = final_mult
            game['cashout_step'] = max_steps
            game['cashout_mult'] = final_mult
            game['status']       = 'completed'
            game['win']          = True
            game['payout']       = payout
            game['profit']       = profit
            del chicken_road_active_games[user_id]
            game_sessions[game_id] = game

            await update_stats_on_bet(user_id, game_id, bet_amount,
                                      win=True, multiplier=final_mult, context=None)
            store_provably_fair_record(
                game_id, "chicken_road", game['server_seed'], game['client_seed'],
                game['nonce'],
                result_data=f"Mode:{mode}, Steps:{max_steps}/{max_steps}, Mult:{final_mult}x, Payout:{payout:.2f}"
            )
            save_user_data(user_id)

            return aiohttp.web.json_response({
                "outcome":      "complete",
                "steps_taken":  max_steps,
                "current_mult": final_mult,
                "next_mult":    None,
                "payout":       round(payout, 2),
                "profit":       round(profit, 2),
                "new_balance":  round(get_active_balance_usd(user_id), 2),
                "server_seed":  game['server_seed'],
                "crash_step":   crash_step,
            })

        else:
            # SAFE: survived this step
            new_mult = get_chicken_road_multiplier(new_step, mode)
            next_step_num = new_step + 1
            next_mult = get_chicken_road_multiplier(next_step_num, mode) \
                        if next_step_num <= max_steps else None

            game['steps_taken']  = new_step
            game['current_mult'] = new_mult
            game_sessions[game_id] = game

            return aiohttp.web.json_response({
                "outcome":      "safe",
                "steps_taken":  new_step,
                "current_mult": new_mult,
                "next_mult":    next_mult,
                "payout":       None,
                "profit":       None,
                "new_balance":  None,
                "server_seed":  None,
                "crash_step":   None,
            })

async def cr_api_cashout(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """POST /chicken-road/api/cashout — cash out the current position."""
    user_data = await _cr_get_user_from_request(request)
    if not user_data:
        return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)

    user_id = user_data['id']
    if user_id in _banned_set:
        return aiohttp.web.json_response({"error": "Account restricted"}, status=403)

    try:
        body    = await request.json()
        game_id = str(body.get('game_id', ''))
    except Exception:
        return aiohttp.web.json_response({"error": "Invalid JSON"}, status=400)

    lock = _chicken_road_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        game = chicken_road_active_games.get(user_id)
        if not game or game.get('id') != game_id or game.get('status') != 'active':
            return aiohttp.web.json_response({"error": "No active game found"}, status=404)

        steps_taken = game['steps_taken']
        if steps_taken < 1:
            return aiohttp.web.json_response(
                {"error": "Must take at least one step before cashing out."}, status=400)

        mode       = game['mode']
        bet_amount = game['bet_amount']
        crash_step = game['crash_step']
        mult       = get_chicken_road_multiplier(steps_taken, mode)
        raw_payout = round(bet_amount * mult, 8)
        payout     = min(raw_payout, CHICKEN_ROAD_WEB_MAX_WIN)
        profit     = round(payout - bet_amount, 8)
        credit_wallet(user_id, payout)

        game['cashout_step'] = steps_taken
        game['cashout_mult'] = mult
        game['status']       = 'cashed_out'
        game['win']          = True
        game['payout']       = payout
        game['profit']       = profit
        game['current_mult'] = mult
        del chicken_road_active_games[user_id]
        game_sessions[game_id] = game

        await update_stats_on_bet(user_id, game_id, bet_amount,
                                  win=True, multiplier=mult, context=None)
        store_provably_fair_record(
            game_id, "chicken_road", game['server_seed'], game['client_seed'],
            game['nonce'],
            result_data=f"Mode:{mode}, CashoutStep:{steps_taken}, Mult:{mult}x, Payout:{payout:.2f}"
        )
        save_user_data(user_id)

    return aiohttp.web.json_response({
        "payout":       round(payout, 2),
        "multiplier":   mult,
        "profit":       round(profit, 2),
        "new_balance":  round(get_active_balance_usd(user_id), 2),
        "cashout_step": steps_taken,
        "server_seed":  game['server_seed'],
        "crash_step":   crash_step,
    })

async def cr_api_history(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """GET /chicken-road/api/history — last 20 completed chicken road games."""
    user_data = await _cr_get_user_from_request(request)
    if not user_data:
        return aiohttp.web.json_response({"error": "Unauthorized"}, status=401)

    user_id = user_data['id']
    if user_id in _banned_set:
        return aiohttp.web.json_response({"error": "Account restricted"}, status=403)

    stats    = user_stats.get(user_id, {})
    game_ids = stats.get('game_sessions', [])
    rounds   = []

    for gid in reversed(game_ids[-100:]):
        g = game_sessions.get(gid)
        if not g or g.get('game_type') != 'chicken_road':
            continue
        if g.get('status') not in ('cashed_out', 'dead', 'completed'):
            continue
        rounds.append({
            "game_id":      g['id'],
            "mode":         g.get('mode', 'medium'),
            "bet_amount":   round(g.get('bet_amount', 0), 2),
            "steps_taken":  g.get('steps_taken', 0),
            "max_steps":    g.get('max_steps', 24),
            "multiplier":   g.get('cashout_mult') or g.get('current_mult') or 0.0,
            "payout":       round(g.get('payout', 0), 2),
            "profit":       round(g.get('profit', 0), 2),
            "outcome":      g.get('status', 'unknown'),
            "win":          g.get('win', False),
            "timestamp":    g.get('timestamp', ''),
        })
        if len(rounds) >= 20:
            break

    return aiohttp.web.json_response({"rounds": rounds})

@check_banned
@check_maintenance
async def chicken_road_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cr and /chickenroad commands."""
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
            "Cross the dungeon — one step at a time — before fire roasts you!\n\n"
            "<b>4 Modes:</b>\n"
            "\U0001f7e2 Easy (24 steps, 4% risk/step) — gentle climb\n"
            "\U0001f7e1 Medium (22 steps, 12% risk/step) — balanced\n"
            "\U0001f7e0 Hard (20 steps, 20% risk/step) — high stakes\n"
            "\U0001f534 Hardcore (15 steps, 40% risk/step) — extreme\n\n"
            "\U0001f4b0 RTP: 98% | Max Win: $20,000 | Provably Fair",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif cr_url:
        bot_username = await get_bot_username(context)
        deep_link    = f"https://t.me/{bot_username}?start=chickenroad"
        keyboard     = [[InlineKeyboardButton("Open Chicken Road", url=deep_link)]]
        await update.message.reply_text(
            "\U0001f414 <b>CHICKEN ROAD</b> is available in private chat!\n"
            "Tap the button below to open it.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "\U0001f414 <b>CHICKEN ROAD</b>\n\n"
            "Web game not yet configured. Contact admin.",
            parse_mode=ParseMode.HTML
        )

async def game_chicken_road_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback for game_cr button in games menu."""
    query = update.callback_query
    if not query:
        return
    cr_url = _get_chicken_road_web_url()
    if cr_url and update.effective_chat.type == "private":
        from telegram import WebAppInfo
        keyboard = [[InlineKeyboardButton("\U0001f414 Play Chicken Road",
                                            web_app=WebAppInfo(url=cr_url))],
                     [InlineKeyboardButton("Back", callback_data="main_games")]]
        await query.edit_message_text(
            "\U0001f414 <b>CHICKEN ROAD</b>\n\n"
            "Cross the dungeon — step by step — before the fire gets you!\n\n"
            "\u2022 4 difficulty modes: Easy / Medium / Hard / Hardcore\n"
            "\u2022 RTP: 98% | Max Win: $20,000\n"
            "\u2022 Provably Fair",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.answer("Open in private chat to play Chicken Road!", show_alert=True)

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler(['cr', 'chickenroad'], chicken_road_command, block=False))
    app.add_handler(CallbackQueryHandler(game_chicken_road_callback, pattern='^game_cr$', block=False))

