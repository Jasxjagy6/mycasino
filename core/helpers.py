"""Auto-split from bot.py — core.helpers."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def get_privacy_display_name(user_id: int, original_name: str) -> str:
    """Return 'Hidden User' if the user has privacy mode enabled, otherwise the original name."""
    if user_stats.get(user_id, {}).get("privacy_mode", False):
        return "Hidden User"
    return original_name

def _get_cached_wagered_rank(user_id: int) -> int | None:
    """Return user_id's rank by total wagered, rebuilding the cache at most
    once per minute. Thread-unsafe but called only from the event loop, and
    the worst case on a race is a duplicate rebuild — not a correctness bug."""
    global _wagered_rank_cache, _wagered_rank_cache_built_at
    import time as _t
    now_mono = _t.monotonic()
    if (not _wagered_rank_cache or
            now_mono - _wagered_rank_cache_built_at > _WAGERED_RANK_CACHE_TTL):
        wagered = [
            (uid, stats.get('bets', {}).get('amount', 0.0))
            for uid, stats in user_stats.items()
        ]
        wagered = [(uid, amt) for uid, amt in wagered if amt > 0]
        wagered.sort(key=lambda x: x[1], reverse=True)
        _wagered_rank_cache = {uid: idx + 1 for idx, (uid, _) in enumerate(wagered)}
        _wagered_rank_cache_built_at = now_mono
    return _wagered_rank_cache.get(user_id)

def _invalidate_leaderboard_cache():
    """Force the next `_rebuild_leaderboards` call to do real work."""
    global _leaderboard_rebuilt_at
    _leaderboard_rebuilt_at = 0.0

def _rebuild_leaderboards(force: bool = False):
    """Rebuild all leaderboard caches from user_stats data.

    Cached for `_LEADERBOARD_REBUILD_TTL` seconds — pass `force=True` from
    invalidation paths (admin reset, weekly/monthly rollover) to bypass the
    cache.
    """
    global _leaderboard_rebuilt_at
    import time as _time_lb
    if not force:
        now_mono = _time_lb.monotonic()
        if (_leaderboard_rebuilt_at and
                now_mono - _leaderboard_rebuilt_at < _LEADERBOARD_REBUILD_TTL):
            return  # cached result is still fresh
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday())  # Monday
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Collect all-time wagered
    all_time = []
    weekly = []
    monthly = []
    highest_wins = []

    for uid, stats in user_stats.items():
        # Get user's display name from userinfo
        userinfo = stats.get('userinfo', {})
        first_name = userinfo.get('first_name', '')
        username_handle = userinfo.get('username', '')
        
        # Use first_name as display name, fall back to @username, then User{uid}
        if first_name and first_name != 'None':
            display_name = first_name
        elif username_handle and username_handle != 'None':
            display_name = f"@{username_handle}"
        else:
            display_name = f"User{uid}"

        # All-time wagered
        total_wagered = stats.get('bets', {}).get('amount', 0.0)
        if total_wagered > 0:
            all_time.append((uid, display_name, total_wagered))

        # Weekly wagered
        weekly_wagered = stats.get('weekly_stats', {}).get('weighted_wager', 0.0)
        if weekly_wagered > 0:
            weekly.append((uid, display_name, weekly_wagered))

        # Monthly wagered
        monthly_wagered = stats.get('monthly_stats', {}).get('weighted_wager', 0.0)
        if monthly_wagered > 0:
            monthly.append((uid, display_name, monthly_wagered))

        # Highest wins this month
        last_win = stats.get('last_win', 0)
        if last_win > 0:
            # Try to get the game type from recent sessions
            sessions = stats.get('game_sessions', [])
            game_type = 'unknown'
            win_ts = now
            # Check game_sessions dict for this user's biggest win
            for gid in reversed(sessions):
                gs = game_sessions.get(gid, {})
                if gs.get('user_id') == uid and gs.get('win', False):
                    profit = gs.get('bet_amount', 0) * (gs.get('multiplier', 0) - 1)
                    if profit >= last_win * 0.9:  # Close enough
                        game_type = gs.get('game_type', 'unknown')
                        try:
                            win_ts = datetime.fromisoformat(gs.get('timestamp', str(now)))
                        except:
                            pass
                        break
            highest_wins.append((uid, display_name, last_win, game_type, win_ts))

    # PERFORMANCE: heapq.nlargest is O(N log k) with k=10 — cheaper than
    # sorted(...)[:10] which is O(N log N). Noticeable once user_stats grows
    # past a few thousand entries.
    import heapq as _heapq_rl
    leaderboard_data["all_time"] = _heapq_rl.nlargest(10, all_time, key=lambda x: x[2])
    leaderboard_data["weekly"] = _heapq_rl.nlargest(10, weekly, key=lambda x: x[2])
    leaderboard_data["monthly"] = _heapq_rl.nlargest(10, monthly, key=lambda x: x[2])
    leaderboard_data["highest_wins"] = _heapq_rl.nlargest(10, highest_wins, key=lambda x: x[2])
    _leaderboard_rebuilt_at = _time_lb.monotonic()

def _get_wallet_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _wallet_locks:
        _wallet_locks[user_id] = asyncio.Lock()
    return _wallet_locks[user_id]

def _get_game_lock(game_id: str) -> asyncio.Lock:
    if game_id not in _game_locks:
        _game_locks[game_id] = asyncio.Lock()
    return _game_locks[game_id]

async def _acquire_callback(query_id: str) -> bool:
    """Returns True if this callback ID is new. Returns False if duplicate (already processing)."""
    async with _inflight_lock:
        if query_id in _inflight_callbacks:
            return False
        _inflight_callbacks.add(query_id)
    return True

def _release_callback(query_id: str):
    """Release a callback ID after processing is done."""
    _inflight_callbacks.discard(query_id)

def _check_user_action_flood(user_id: int, action_key: str, cooldown: float) -> bool:
    """
    Returns True if action is allowed (not flooding).
    Returns False if user is tapping too fast.
    """
    import time as _time
    now = _time.monotonic()
    user_ts = _user_action_timestamps.setdefault(user_id, {})
    last = user_ts.get(action_key, 0.0)
    if now - last < cooldown:
        return False
    user_ts[action_key] = now
    return True

def _get_withdrawal_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _withdrawal_locks:
        _withdrawal_locks[user_id] = asyncio.Lock()
    return _withdrawal_locks[user_id]

def _get_raffle_lock(raffle_id: str) -> asyncio.Lock:
    if raffle_id not in _raffle_locks:
        _raffle_locks[raffle_id] = asyncio.Lock()
    return _raffle_locks[raffle_id]

def convert_currency(amount_usd, to_currency="USD"):
    """Legacy helper - USD -> target currency (display only)."""
    return convert_usd_to_display(amount_usd, to_currency)

def convert_to_usd(amount, from_currency="USD"):
    """Legacy helper - any currency -> USD."""
    return convert_display_to_usd(amount, from_currency)

def format_compact_usd(amount_usd):
    """Legacy USD compact format - now a thin wrapper.

    Existing callers passed raw USD amounts; keep that contract.
    """
    return "$" + format_compact(float(amount_usd or 0.0), "USD")

def format_compact_for_user(user_id, amount_usd, with_usdt_estimate: bool = False) -> str:
    """Compact version of format_for_user (used by leaderboards/stats)."""
    return format_for_user(user_id, amount_usd, compact=True, with_usdt_estimate=with_usdt_estimate)

async def _concurrency_middleware(request, handler, semaphore):
    """Middleware that limits concurrent requests using a semaphore.
    Prevents event loop saturation under high load (4k+ users)."""
    async with semaphore:
        return await handler(request)

def _secure_shuffle(seq):
    """Cryptographically secure shuffle using Fisher-Yates with secrets.
    Replaces random.shuffle() with secrets-based implementation."""
    for i in range(len(seq) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        seq[i], seq[j] = seq[j], seq[i]

def _secure_randint(a, b):
    """Cryptographically secure random integer in [a, b].
    Replaces random.randint() with secrets-based implementation."""
    if a > b:
        raise ValueError("a must be <= b")
    return a + secrets.randbelow(b - a + 1)

def _secure_choices(population, k, weights=None):
    """Cryptographically secure random choices with replacement.
    Replaces random.choices() - does NOT support weights for simplicity."""
    if weights is not None:
        # Weighted selection using cumulative distribution
        import bisect
        total = sum(weights)
        cum_weights = []
        current = 0
        for w in weights:
            current += w
            cum_weights.append(current)
        return [population[bisect.bisect(cum_weights, secrets.randbelow(total))] for _ in range(k)]
    return [_secure_choice(population) for _ in range(k)]

def generate_game_client_seed():
    """Generate a fresh 15-character client seed for each new game (mines/keno).
    This ensures each game has a unique random seed for truly fair results.
    Uses cryptographically secure random generation for unpredictable results."""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(15))

def create_hash(server_seed, client_seed, nonce):
    combined = f"{server_seed}:{client_seed}:{nonce}"
    return hashlib.sha256(combined.encode()).hexdigest()

def get_provably_fair_result(server_seed, client_seed, nonce, max_value):
    """Unbiased integer draw in ``[0, max_value)``.

    Phase 3 — routes to :func:`core.fair_rng.draw_uniform_int` which
    uses rejection sampling, so outcomes are uniform even when
    ``max_value`` does not divide 2**32 (the legacy modulo path was
    biased by ~1.5% on the mines tile range ``n=25``).  The function
    signature is unchanged, so every existing game call site picks up
    the fix without further edits.
    """
    from core.fair_rng import draw_uniform_int
    return draw_uniform_int(server_seed, client_seed, nonce, max_value)

def get_user_seeds(user_id):
    """Get user's current seeds and nonce - ensures seeds are initialized and saved"""
    # If user doesn't exist in user_stats, raise an error as callers should ensure user exists
    if user_id not in user_stats:
        logging.error(f"get_user_seeds called for non-existent user {user_id} - this should never happen")
        # Return emergency defaults - but this indicates a bug in calling code
        emergency_seeds = {
            "server_seed": generate_server_seed(),
            "client_seed": generate_client_seed(),
            "nonce": 0
        }
        return emergency_seeds

    # Initialize provably_fair data if it doesn't exist and SAVE it immediately
    if "provably_fair" not in user_stats[user_id]:
        user_stats[user_id]["provably_fair"] = {
            "server_seed": generate_server_seed(),
            "client_seed": generate_client_seed(),
            "nonce": 0,
            "next_server_seed": generate_server_seed()
        }
        save_user_data(user_id)
        logging.info(f"Initialized provably_fair data for user {user_id}")

    pf_data = user_stats[user_id]["provably_fair"]
    return {
        "server_seed": pf_data.get("server_seed"),
        "client_seed": pf_data.get("client_seed"),
        "nonce": pf_data.get("nonce", 0)
    }

def increment_user_nonce(user_id):
    """Increment user's nonce after a bet - call get_user_seeds first to ensure initialization.
    NOTE: This is called after deduct_wallet_safe which already holds the wallet lock,
    making the nonce increment effectively atomic within the bet flow."""
    if user_id not in user_stats:
        logging.error(f"increment_user_nonce called for non-existent user {user_id}")
        return

    # Call get_user_seeds first to ensure provably_fair is properly initialized and saved
    if "provably_fair" not in user_stats[user_id]:
        get_user_seeds(user_id)

    # This is safe because it's called after deduct_wallet_safe which holds the wallet lock
    user_stats[user_id]["provably_fair"]["nonce"] += 1
    save_user_data(user_id)

async def safe_send_message(bot, chat_id, text, **kwargs):
    """Send a message with automatic retry on Telegram flood / timeout errors.

    PERFORMANCE / CORRECTNESS:
      - Honours Telegram's ``retry_after`` from PTB's ``RetryAfter`` exception
        instead of a blind 2^n backoff. When Telegram tells us exactly how
        long to wait, sleeping longer wastes latency, sleeping shorter just
        gets flood-limited again.
      - Recognises permanent failures (user blocked the bot / chat gone /
        deactivated account) and returns ``None`` immediately — don't waste
        retries on a dead DM.
      - Bounded backoff (capped at 60s) so a rogue chat can never hold a
        handler hostage.
    """
    try:
        from telegram.error import RetryAfter, TimedOut, NetworkError, Forbidden as _Forbidden, BadRequest as _BadRequest
    except Exception:  # pragma: no cover
        RetryAfter = TimedOut = NetworkError = _Forbidden = _BadRequest = ()  # type: ignore

    for attempt in range(3):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except RetryAfter as e:
            wait = min(float(getattr(e, 'retry_after', 1.0)) + 0.5, 60.0)
            logging.warning(
                f"Flood-limited on send to {chat_id}, sleeping {wait:.1f}s "
                f"(attempt {attempt + 1}/3)"
            )
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as e:
            if attempt == 2:
                logging.error(
                    f"safe_send_message network error to {chat_id} after retries: {e}"
                )
                return None
            await asyncio.sleep(0.5 * (attempt + 1))
        except _Forbidden:
            # User blocked bot, deactivated, or kicked — permanent.
            return None
        except _BadRequest as e:
            msg = str(e).lower()
            if ("chat not found" in msg or "user is deactivated" in msg
                    or "bot was blocked" in msg or "forbidden" in msg):
                return None
            if attempt == 2:
                logging.error(f"safe_send_message BadRequest to {chat_id}: {e}")
                return None
            await asyncio.sleep(0.3)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "flood" in err or "rate limit" in err:
                wait = min(2 ** attempt, 30)
                logging.warning(
                    f"Rate limited on send to {chat_id}, retrying in {wait}s"
                )
                await asyncio.sleep(wait)
            elif ("forbidden" in err or "chat not found" in err
                    or "blocked" in err or "deactivated" in err):
                return None
            else:
                if attempt == 2:
                    logging.error(
                        f"safe_send_message failed after 3 attempts to {chat_id}: {e}"
                    )
                    return None
                await asyncio.sleep(0.5)
    return None

async def smart_rate_limit(chat_id, chat_type="private"):
    """
    Smart rate limiting for emoji sending
    - In groups: faster rolling (0.5s between, 2s animation wait)
    - In DMs: moderate speed (0.7s between, 3s animation wait)
    - Tracks timestamps to avoid hitting Telegram limits

    Phase 2: when ``MYCASINO_REDIS_BACKEND`` is set, the sliding-window
    counter is shared across **every** stateless PTB worker via
    :func:`core.redis_backend.check_rate_limit`.  Two workers serving
    the same chat will not both blast Telegram in the same window —
    the second worker waits.  The legacy per-process timestamp dict
    is kept as a fallback so a Redis outage degrades to today's
    behaviour.
    """
    global emoji_send_timestamps

    now = asyncio.get_event_loop().time()
    last_send = emoji_send_timestamps.get(chat_id, 0)

    # Determine delays based on chat type
    if chat_type in ["group", "supergroup"]:
        # Faster in groups but still safe
        min_interval = 0.3  # Minimum time between sends
        animation_wait = 2.0  # Reduced animation wait
    else:
        # DM settings
        min_interval = 0.5
        animation_wait = 3.0

    # Phase 2: cross-worker sliding-window guard via Redis.  We allow
    # at most one emoji send per ``min_interval`` per chat — when the
    # window is exhausted the helper *blocks* for ``retry_after_ms``
    # rather than racing past the legacy timestamp guard.
    try:
        from core import redis_backend as _rb
        if _rb.redis_enabled():
            window_ms = max(1, int(min_interval * 1000))
            res = await _rb.check_rate_limit(
                f"emoji:{chat_id}",
                limit=1,
                window_ms=window_ms,
            )
            if not res.allowed and res.retry_after_ms > 0:
                await asyncio.sleep(res.retry_after_ms / 1000.0)
    except Exception:  # noqa: BLE001
        logging.exception("Redis rate-limit failed for chat=%s; legacy path", chat_id)

    # Wait if needed to respect minimum interval
    time_since_last = now - last_send
    if time_since_last < min_interval:
        await asyncio.sleep(min_interval - time_since_last)

    # Update last send time
    emoji_send_timestamps[chat_id] = asyncio.get_event_loop().time()

    return animation_wait  # Return how long to wait for animation

async def smart_roll(context: ContextTypes.DEFAULT_TYPE, chat_id: int, emoji: str, reply_to_message_id: int = None):
    """
    Roll dice using round-robin across ALL helper bots in groups.
    Falls back to main bot if no helpers available or in private chat.
    Returns tuple: (message, used_helper_bot: bool)
    """
    global _helper_bot_rr_index
    is_group = chat_id < 0

    if is_group and helper_bots:
        # Round-robin: cycle through all helper bots evenly
        selected = helper_bots[_helper_bot_rr_index % len(helper_bots)]
        _helper_bot_rr_index += 1
        try:
            if reply_to_message_id:
                msg = await selected.send_dice(chat_id=chat_id, emoji=emoji, reply_to_message_id=reply_to_message_id)
            else:
                msg = await selected.send_dice(chat_id=chat_id, emoji=emoji)
            return (msg, True)
        except Exception as e:
            logging.warning(f"Helper bot round-robin failed (idx={(_helper_bot_rr_index-1) % len(helper_bots)}): {e}")

    # Fallback: main bot
    if reply_to_message_id:
        msg = await context.bot.send_dice(chat_id=chat_id, emoji=emoji, reply_to_message_id=reply_to_message_id)
    else:
        msg = await context.bot.send_dice(chat_id=chat_id, emoji=emoji)
    return (msg, False)

async def multi_roll_parallel(context: ContextTypes.DEFAULT_TYPE, chat_id: int, emoji: str, count: int, reply_to_message_id: int = None):
    """
    Roll dice emojis with smart speed based on available helper bots.

    Speed modes:
    - Groups with 3+ helper bots: PARALLEL (zero delay, lightning-fast)
    - Groups with 1-2 helper bots: SEQUENTIAL with small delay (0.1s)
    - Private chat (DM): SEQUENTIAL with 0.15s delay to avoid rate limits

    Args:
        context: Bot context
        chat_id: Target chat ID
        emoji: Dice emoji to send (e.g., '🎲')
        count: Number of dice to roll (1-6)
        reply_to_message_id: Optional message ID to reply to (for tagging user)

    Returns:
        list of (message, used_helper_bot: bool) tuples - one per die
    """
    is_group = chat_id < 0
    helper_count = len(helper_bots) if is_group else 0

    # Determine speed mode
    if is_group and helper_count >= 3:
        mode = "parallel"  # Lightning-fast
    elif is_group and helper_count >= 1:
        mode = "fast_sequential"  # Small delay
    else:
        mode = "slow_sequential"  # DM mode - safe delay

    async def _roll_one(bot_ref, emoji, chat_id, reply_to_message_id):
        """Roll a single die with the given bot."""
        try:
            if isinstance(bot_ref, tuple):
                bot_obj = bot_ref[1]
                if reply_to_message_id:
                    msg = await bot_obj.send_dice(chat_id=chat_id, emoji=emoji, reply_to_message_id=reply_to_message_id)
                else:
                    msg = await bot_obj.send_dice(chat_id=chat_id, emoji=emoji)
                return (msg, False)
            else:
                if reply_to_message_id:
                    msg = await bot_ref.send_dice(chat_id=chat_id, emoji=emoji, reply_to_message_id=reply_to_message_id)
                else:
                    msg = await bot_ref.send_dice(chat_id=chat_id, emoji=emoji)
                return (msg, True)
        except Exception as e:
            logging.warning(f"Multi-roll bot failed: {e}")
            if reply_to_message_id:
                msg = await context.bot.send_dice(chat_id=chat_id, emoji=emoji, reply_to_message_id=reply_to_message_id)
            else:
                msg = await context.bot.send_dice(chat_id=chat_id, emoji=emoji)
            return (msg, False)

    if mode == "parallel":
        # LIGHTNING-FAST: Fire all rolls simultaneously using asyncio.gather
        # Each die sent by a different helper bot - zero delay
        available_bots = list(helper_bots)
        available_bots.append(('main', context.bot))

        tasks = []
        for i in range(count):
            bot_ref = available_bots[i % len(available_bots)]
            tasks.append(_roll_one(bot_ref, emoji, chat_id, reply_to_message_id))

        results = await asyncio.gather(*tasks)
        return list(results)

    elif mode == "fast_sequential":
        # FAST: Sequential rolls with minimal delay (0.1s)
        # Uses helper bots one after another
        results = []
        available_bots = list(helper_bots)
        available_bots.append(('main', context.bot))

        for i in range(count):
            bot_ref = available_bots[i % len(available_bots)]
            msg, used_helper = await _roll_one(bot_ref, emoji, chat_id, reply_to_message_id)
            results.append((msg, used_helper))
            if i < count - 1:  # No delay after last roll
                await asyncio.sleep(0.1)
        return results

    else:
        # SLOW SEQUENTIAL (DM mode): 0.15s delay between rolls to avoid rate limits
        results = []
        for i in range(count):
            msg, used_helper = await _roll_one(('main', context.bot), emoji, chat_id, reply_to_message_id)
            results.append((msg, used_helper))
            if i < count - 1:  # No delay after last roll
                await asyncio.sleep(0.15)
        return results

def store_provably_fair_record(game_id, game_type, server_seed, client_seed, nonce, result_data=None):
    """Store provably fair verification data for a completed game"""
    provably_fair_records[game_id] = {
        "game_id": game_id,
        "game_type": game_type,
        "server_seed": server_seed,
        "client_seed": client_seed,
        "nonce": nonce,
        "result_data": result_data,  # Game-specific result information
        "timestamp": str(datetime.now(timezone.utc))
    }
    # Keep only last 1000 records to avoid memory issues
    if len(provably_fair_records) > 1000:
        oldest_key = next(iter(provably_fair_records))
        del provably_fair_records[oldest_key]

async def create_provably_fair_button(game_id, context):
    """Create a provably fair URL button that links to DM"""
    try:
        bot_username = await get_bot_username(context)
        pf_url = f"https://t.me/{bot_username}?start=provablyfair_{game_id}"
        return InlineKeyboardButton("Provably Fair", url=pf_url)
    except Exception as e:
        logging.error(f"Error creating provably fair button: {e}")
        # Fallback to callback button if we can't get bot username
        return InlineKeyboardButton("Provably Fair", callback_data=f"pf_show_{game_id}")

def display_at(username):
    """Return username with exactly one leading @ for display purposes.
    Handles cases where normalize_username() already added @ prefix."""
    if not username:
        return "Unknown"
    s = str(username)
    stripped = s.lstrip("@")
    if not stripped:
        return s
    return f"@{stripped}"

def check_menu_ownership(query, context) -> bool:
    """
    Check if the user clicking the button is the owner of the menu.
    For group chats, we track menu ownership by message_id.
    Returns True if the user is the owner or if no owner is set.
    Returns False if another user is trying to interact with the menu.
    OPTIMIZED: Uses in-memory _menu_owners dict with TTL expiry.
    """
    menu_key = f"{query.message.chat_id}_{query.message.message_id}"
    entry = _menu_owners.get(menu_key)
    if entry is None:
        return True
    owner_id, expiry = entry
    if datetime.now().timestamp() > expiry:
        _menu_owners.pop(menu_key, None)
        return True
    return query.from_user.id == owner_id

def _build_history_keyboard(game_ids, page, user_id):
    """Build inline keyboard for history pagination."""
    total = len(game_ids)
    start = page * HISTORY_ITEMS_PER_PAGE
    page_items = game_ids[start:start + HISTORY_ITEMS_PER_PAGE]

    keyboard = []

    # Game number buttons - Row 1 (first 5)
    row1 = []
    for i, gid in enumerate(page_items[:5]):
        game_num = total - (start + i)
        row1.append(InlineKeyboardButton(
            str(game_num),
            callback_data=f"hist_view_{gid}"
        ))
    if row1:
        keyboard.append(row1)

    # Game number buttons - Row 2 (next 5)
    row2 = []
    for i, gid in enumerate(page_items[5:10]):
        game_num = total - (start + 5 + i)
        row2.append(InlineKeyboardButton(
            str(game_num),
            callback_data=f"hist_view_{gid}"
        ))
    if row2:
        keyboard.append(row2)

    # Navigation row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("Previous", callback_data=f"hist_page_{user_id}_{page - 1}"))
    if (page + 1) * HISTORY_ITEMS_PER_PAGE < total:
        nav_row.append(InlineKeyboardButton("Next", callback_data=f"hist_page_{user_id}_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    return keyboard

@check_banned
@check_maintenance
async def message_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user = update.effective_user

    # Check if user is in custom bet input mode for emoji game setup
    for gt in ["dice", "darts", "goal", "bowl"]:
        awaiting_key = f"eg_awaiting_custom_bet_{gt}"
        if context.user_data.get(awaiting_key):
            context.user_data.pop(awaiting_key)
            setup_key = f"eg_setup_{gt}"
            try:
                amount = float(update.message.text.strip())
                if amount <= 0:
                    raise ValueError
                balance = get_active_balance_usd(user.id)
                if amount > balance:
                    await update.message.reply_text(
                        f"{pe('cross')} Amount exceeds your balance of ${balance:.2f}",
                        parse_mode=ParseMode.HTML
                    )
                    return
                if setup_key not in context.user_data:
                    context.user_data[setup_key] = {"mode": "normal", "rolls": 1, "first_to": 1, "bet_usd": None}
                context.user_data[setup_key]["bet_usd"] = amount
                # Re-show the setup panel
                state = context.user_data[setup_key]
                text, keyboard = _build_emoji_setup_ui(gt, state, balance, user)
                await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            except ValueError:
                await update.message.reply_text(f"{pe('cross')} Invalid amount. Enter a positive number.", parse_mode=ParseMode.HTML)
            return

    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_stats[user.id]['last_update'] = str(datetime.now(timezone.utc))

    # NEW: Check for new members in a group
    if update.message.new_chat_members:
        chat_id = update.effective_chat.id
        settings = group_settings.get(chat_id)
        if settings and settings.get("welcome_message"):
            for new_member in update.message.new_chat_members:
                welcome_text = settings["welcome_message"].format(
                    first_name=new_member.first_name,
                    last_name=new_member.last_name or "",
                    username=f"@{new_member.username}" if new_member.username else "",
                    mention=new_member.mention_html(),
                    chat_title=update.effective_chat.title
                )
                await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
        return


    if 'escrow_step' in context.user_data:
        await handle_escrow_conversation(update, context)
        return

    # Handle PvB games
    # Check BOTH context.chat_data (primary) and global dict (fallback)
    active_pvb_game_id = context.chat_data.get(f"active_pvb_game_{user.id}")
    chat_matched_pvb = False
    if not active_pvb_game_id:
        active_pvb_game_id = active_pvb_games.get(user.id)  # Fallback to global dict
        if active_pvb_game_id and active_pvb_game_id in game_sessions:
            # Check if the chat matches - if not, ignore silently
            game_chat = game_sessions[active_pvb_game_id].get('chat_id')
            if game_chat is not None and game_chat != update.effective_chat.id:
                # Game is in a different chat, ignore this roll silently
                if DEBUG_EMOJI_GAMES:
                    logging.info(f"PvB game in different chat: game_chat={game_chat}, current_chat={update.effective_chat.id}")
                active_pvb_game_id = None
            elif active_pvb_game_id and DEBUG_EMOJI_GAMES:
                logging.info(f"Found PvB game in global dict (fallback): {active_pvb_game_id}")
                chat_matched_pvb = True
        elif active_pvb_game_id:
            chat_matched_pvb = True
    else:
        chat_matched_pvb = True

    # DEBUG LOGGING (controlled by DEBUG_EMOJI_GAMES flag)
    if update.message.dice and DEBUG_EMOJI_GAMES:
        logging.info(f"DICE: user={user.id}, emoji={update.message.dice.emoji}, value={update.message.dice.value}, active_game={active_pvb_game_id}, exists={active_pvb_game_id in game_sessions if active_pvb_game_id else False}")

    if chat_matched_pvb and active_pvb_game_id and active_pvb_game_id in game_sessions:
        game = game_sessions[active_pvb_game_id]

        game_type = (game['game_type']
                     .replace("pvb_", "")
                     .replace("xdxw_", "")
                     .replace("group_challenge_", ""))
        # Handle different game_type naming variations
        emoji_map = {
            "dice": "🎲", "dice_bot": "🎲",
            "darts": "🎯",
            "goal": "⚽", "football": "⚽",
            "bowl": "🎳", "bowling": "🎳"
        }
        expected_emoji = emoji_map.get(game_type, "🎲")  # Default to dice if not found
        game_rolls = game.get('game_rolls', 1)
        game_mode = game.get('game_mode', 'normal')
        bot_rolls_first = game.get('bot_rolls_first', False)

        # CRITICAL FIX (race-condition #1): drop dice that arrive while the
        # bot is still rolling or while we're mid-way through resolving the
        # previous round.
        #
        # `waiting_for == "bot"` and `bot_is_rolling` cover the bot's
        # animation window. But there is a *second* race window between
        # the moment we clear those flags after multi_roll_parallel
        # returns and the moment we reset `game['user_rolls']` to [] at
        # the end of round resolution (which only happens after several
        # `await reply_text` calls). A dice the user spams in that window
        # used to be appended onto the still-full `user_rolls` list, sail
        # past the `len < game_rolls` gate, and trigger a *second* bot
        # roll for the same round — that is the source of the duplicate
        # bot rolls + score corruption + "behaves unusual" reports for
        # /dice <amount> PvB matches.
        #
        # Closing the race: also bail when `user_rolls` is already at
        # full capacity for this round, regardless of the boolean flags.
        if (game.get("waiting_for") == "bot"
                or game.get("bot_is_rolling")
                or len(game.get('user_rolls', []) or []) >= game_rolls):
            if DEBUG_EMOJI_GAMES:
                logging.info(f"PVB IGNORED: user={user.id} tried to roll during bot's turn / round resolution (game={active_pvb_game_id})")
            return

        if update.message.dice and update.message.dice.emoji == expected_emoji and update.message.forward_origin is None:
            # Cancel PvB timeout since user is rolling
            _cancel_pvb_timeout_jobs(context, user.id, active_pvb_game_id)

            user_roll = update.message.dice.value

            # Add to user_rolls list
            if 'user_rolls' not in game:
                game['user_rolls'] = []
            game['user_rolls'].append(user_roll)

            # Check if user has completed all rolls
            if len(game['user_rolls']) < game_rolls:
                # Mid-round partial roll: schedule a throttled, fire-and-forget
                # refresh of the existing cashout button so the label catches
                # up with the new state without awaiting a Telegram round trip
                # inside the dice handler. Awaiting an edit_message_reply_markup
                # here used to serialise concurrent PvB matches behind the per-
                # chat rate limiter.
                _schedule_pvb_cashout_refresh(context, active_pvb_game_id, game, user.id)
                return

            # Round will now resolve — invalidate the cashout button so the
            # player can't cash out after already locking in all their rolls.
            _active_cashout_buttons.pop(active_pvb_game_id, None)
            _cashout_refresh_last.pop(active_pvb_game_id, None)

            # User finished rolling
            user_rolls = game['user_rolls']
            user_total = sum(user_rolls)
            user_rolls_text = ROLL_SEPARATOR.join(str(r) for r in user_rolls)

            if bot_rolls_first:
                # Bot already rolled, so we have bot_rolls
                bot_rolls = game.get('bot_rolls', [])
                bot_total = sum(bot_rolls)
                bot_rolls_text = ROLL_SEPARATOR.join(str(r) for r in bot_rolls)

                # Determine winner based on mode
                win = False
                if game_mode == "normal":
                    # Normal mode: highest total wins
                    win = user_total > bot_total
                    tie = user_total == bot_total
                else:
                    # Crazy mode: lowest total wins
                    win = user_total < bot_total
                    tie = user_total == bot_total

                round_result = {"user_rolls": user_rolls, "bot_rolls": bot_rolls,
                              "user_total": user_total, "bot_total": bot_total, "winner": None}

                if tie:
                    result_text = f"{pe('push')} It's a tie! No point."
                elif win:
                    game["user_score"] += 1
                    round_result["winner"] = "user"
                    result_text = f"{pe('win')} {user.first_name} wins this round!"
                else:
                    game["bot_score"] += 1
                    round_result["winner"] = "bot"
                    result_text = f"{pe('robot')} Bot wins this round!"

                # Consolidated message for bot_rolls_first mode
                username_display = user.first_name if user.first_name else "Player"
                await update.message.reply_text(
                    f"{pe('robot')} <b>BOT ROLLED FIRST!</b>\n\n"
                    f"Bot rolled: [{bot_rolls_text}] = <b>{bot_total}</b>\n"
                    f"{username_display} rolled: [{user_rolls_text}] = <b>{user_total}</b>\n\n"
                    f"{result_text}",
                    parse_mode=ParseMode.HTML
                )
            else:
                # PERFORMANCE: We used to send a "{user} rolled X. Bot is
                # rolling..." ack message here, *then* the bot's dice, *then*
                # the consolidated result. With AIORateLimiter that's three
                # messages-per-round serialised on the same chat's rate
                # window — ~3s of waiting before the result is visible. With
                # 2 players in the same group running PvB matches it doubles
                # to ~6s and feels like the bot has crashed. Skip the ack:
                # the bot's dice that's about to be sent is itself the "I'm
                # rolling now" indicator, and the consolidated result message
                # below repeats both the user's and bot's rolls.
                username_display = user.first_name if user.first_name else "Player"

                # Check if bot already rolled (via "Bot rolls first" button or timeout job)
                pre_rolled_values = context.user_data.get('pre_rolled_bot_values') or game.get('pre_rolled_bot_values')

                if pre_rolled_values:
                    # Bot already rolled - use those values
                    bot_rolls = pre_rolled_values
                    # Clear the stored values from both places
                    context.user_data.pop('pre_rolled_bot_values', None)
                    game.pop('pre_rolled_bot_values', None)
                else:
                    # Bot hasn't rolled yet - roll now using multi_roll_parallel for lightning-fast speed
                    # Set flags to prevent user from sending more emojis during bot's rolling.
                    # Both `bot_is_rolling` and `waiting_for='bot'` are set so any
                    # consumer that only knows about one flag still bails correctly.
                    game['bot_is_rolling'] = True
                    game['waiting_for'] = 'bot'
                    bot_rolls = []
                    # CRITICAL FIX: reply-tag the user's most-recent dice
                    # message rather than the original /dice <amount>
                    # command. Tagging the user's recent dice is the
                    # natural "Bot is responding to your roll" UX and is
                    # what the user expects in /dice <amount> mode (parity
                    # with what they see in /dice <amount> XdX'w mode
                    # where the bot's emoji clearly tags the user). Using
                    # the original /dice command id made the bot's roll
                    # land deep above the user's dice in the chat scroll,
                    # which is what the user reported as "doesn't
                    # actually tag the user message".
                    command_msg_id = (update.message.message_id
                                      if update.message else game.get('command_message_id'))
                    try:
                        rolls_data = await multi_roll_parallel(context, update.effective_chat.id, expected_emoji, game_rolls, reply_to_message_id=command_msg_id)
                        for msg, _ in rolls_data:
                            bot_rolls.append(msg.dice.value)
                    except Exception as e:
                        logging.error(f"Error sending dice in PvB game: {e}")
                        await update.message.reply_text(f"{pe('cross')} An error occurred. Game terminated.")
                        game['status'] = 'error'
                        game.pop('bot_is_rolling', None)
                        game.pop('waiting_for', None)
                        context.chat_data.pop(f"active_pvb_game_{user.id}", None)
                        if user.id in active_pvb_games:
                            del active_pvb_games[user.id]
                        _unindex_user_game(user.id, active_pvb_game_id)
                        _active_cashout_buttons.pop(active_pvb_game_id, None)
                        _cashout_refresh_last.pop(active_pvb_game_id, None)
                        credit_wallet(user.id, game['bet_amount'])
                        update_pnl(user.id)
                        save_user_data(user.id)
                        return
                    # NOTE: keep `bot_is_rolling=True` and `waiting_for='bot'`
                    # in place until *after* user_rolls/bot_rolls are reset
                    # below. Clearing them here used to open a small race
                    # window during the round-result `await reply_text`
                    # where a spammed dice would be appended to the
                    # still-full user_rolls list and trigger a duplicate
                    # bot roll. The flags now act as a single "round in
                    # progress" guard until the round is fully resolved.

                game["bot_rolls"] = bot_rolls
                bot_total = sum(bot_rolls)
                bot_rolls_text = ROLL_SEPARATOR.join(str(r) for r in bot_rolls)

                # Determine winner based on mode
                win = False
                if game_mode == "normal":
                    # Normal mode: highest total wins
                    win = user_total > bot_total
                    tie = user_total == bot_total
                else:
                    # Crazy mode: lowest total wins
                    win = user_total < bot_total
                    tie = user_total == bot_total

                round_result = {"user_rolls": user_rolls, "bot_rolls": bot_rolls,
                              "user_total": user_total, "bot_total": bot_total, "winner": None}

                if tie:
                    result_text = f"{pe('push')} It's a tie! No point."
                elif win:
                    game["user_score"] += 1
                    round_result["winner"] = "user"
                    result_text = f"{pe('win')} {username_display} wins this round!"
                else:
                    game["bot_score"] += 1
                    round_result["winner"] = "bot"
                    result_text = f"{pe('robot')} Bot wins this round!"

                # Consolidated message showing bot rolls and winner
                username_display = user.first_name if user.first_name else "Player"
                await update.message.reply_text(
                    f"<b>{username_display.upper()} ROLLED FIRST!</b>\n\n"
                    f"{username_display} rolled: [{user_rolls_text}] = <b>{user_total}</b>\n"
                    f"{pe('robot')} Bot rolled: [{bot_rolls_text}] = <b>{bot_total}</b>\n\n"
                    f"{result_text}",
                    parse_mode=ParseMode.HTML
                )

            game["history"].append(round_result)
            game["current_round"] += 1
            game['user_rolls'] = []  # Reset for next round
            game['bot_rolls'] = []  # Reset for next round
            # Round fully resolved — *now* it's safe to clear the
            # "round-in-progress" guards. The next-round bot-rolls-first
            # branch below re-sets them as needed for its own bot roll.
            game.pop('bot_is_rolling', None)
            game['waiting_for'] = 'user'

            # Check for game end
            if game["user_score"] >= game["target_score"]:
                # Cancel any pending timeout
                _cancel_pvb_timeout_jobs(context, user.id, active_pvb_game_id)
                winnings = game["bet_amount"] * 1.96
                credit_wallet(user.id, winnings)
                game['status'] = 'completed'
                game['win'] = True
                # Resolve side bets - user (p1) wins
                asyncio.ensure_future(resolve_sidebets_for_match(active_pvb_game_id, "p1", context))
                await update_stats_on_bet(user.id, game['id'], game['bet_amount'], True, multiplier=1.96, context=context)
                # No manual sleep — AIORateLimiter already paces outbound
                # messages per chat. Sleeping here just stretched concurrent
                # PvB matches' total wall-clock time without buying anything.
                await update.message.reply_text(f"{pe('trophy')} {user.mention_html()}, Congratulations! You beat the bot ({game['user_score']}-{game['bot_score']}) and win ${winnings:.2f}!", parse_mode=ParseMode.HTML)
                context.chat_data.pop(f"active_pvb_game_{user.id}", None)
                if user.id in active_pvb_games:
                    del active_pvb_games[user.id]
                _unindex_user_game(user.id, active_pvb_game_id)
                # Lifecycle cleanup: cashout button state is per-game.
                _active_cashout_buttons.pop(active_pvb_game_id, None)
                _cashout_refresh_last.pop(active_pvb_game_id, None)
                _game_locks.pop(active_pvb_game_id, None)
            elif game["bot_score"] >= game["target_score"]:
                # Cancel any pending timeout
                _cancel_pvb_timeout_jobs(context, user.id, active_pvb_game_id)
                game['status'] = 'completed'
                game['win'] = False
                # Resolve side bets - bot (p2) wins
                asyncio.ensure_future(resolve_sidebets_for_match(active_pvb_game_id, "p2", context))
                await update_stats_on_bet(user.id, game['id'], game['bet_amount'], False, context=context)
                # AIORateLimiter handles per-chat pacing; manual sleep removed.
                await update.message.reply_text(f"{pe('lose')} {user.mention_html()}, Bot wins the match ({game['bot_score']}-{game['user_score']}). You lost {format_for_user(user.id, game['bet_amount'])}.", parse_mode=ParseMode.HTML)
                context.chat_data.pop(f"active_pvb_game_{user.id}", None)
                if user.id in active_pvb_games:
                    del active_pvb_games[user.id]
                _unindex_user_game(user.id, active_pvb_game_id)
                # Lifecycle cleanup: cashout button state is per-game.
                _active_cashout_buttons.pop(active_pvb_game_id, None)
                _cashout_refresh_last.pop(active_pvb_game_id, None)
                _game_locks.pop(active_pvb_game_id, None)
            else: # Continue game - next round
                # AIORateLimiter handles per-chat pacing; manual sleep removed.

                if bot_rolls_first:
                    # Bot rolls first for next round
                    # Set flag to prevent user from rolling during bot's turn
                    game['waiting_for'] = 'bot'
                    game['bot_is_rolling'] = True

                    await update.message.reply_text(
                        f"Score: You {game['user_score']} - {game['bot_score']} Bot. (First to {game['target_score']})\n\n"
                        f"<b>Bot is rolling for Round {game['current_round']}...</b>",
                        parse_mode=ParseMode.HTML
                    )

                    # Bot rolls - use multi_roll_parallel for lightning-fast speed
                    bot_rolls = []
                    # Reply-tag the user's most-recent dice (parity with
                    # the user-rolls-first branch above).
                    command_msg_id = (update.message.message_id
                                      if update.message else game.get('command_message_id'))
                    try:
                        rolls_data = await multi_roll_parallel(context, update.effective_chat.id, expected_emoji, game_rolls, reply_to_message_id=command_msg_id)
                        for msg, _ in rolls_data:
                            bot_rolls.append(msg.dice.value)
                    except Exception as e:
                        logging.error(f"Error sending dice in PvB game: {e}")
                        await update.message.reply_text(f"{pe('cross')} An error occurred. Game terminated.")
                        game['status'] = 'error'
                        game.pop('bot_is_rolling', None)
                        game.pop('waiting_for', None)
                        context.chat_data.pop(f"active_pvb_game_{user.id}", None)
                        if user.id in active_pvb_games:
                            del active_pvb_games[user.id]
                        _unindex_user_game(user.id, active_pvb_game_id)
                        _active_cashout_buttons.pop(active_pvb_game_id, None)
                        _cashout_refresh_last.pop(active_pvb_game_id, None)
                        credit_wallet(user.id, game['bet_amount'])
                        update_pnl(user.id)
                        save_user_data(user.id)
                        return

                    game.pop('bot_is_rolling', None)
                    game["bot_rolls"] = bot_rolls
                    bot_total = sum(bot_rolls)
                    bot_rolls_text = ROLL_SEPARATOR.join(str(r) for r in bot_rolls)

                    # Store bot roll values in context for next user response
                    context.user_data['pre_rolled_bot_values'] = bot_rolls
                    # Now it's user's turn
                    game['waiting_for'] = 'user'

                    username_display = user.first_name if user.first_name else "Player"

                    # GREEN cashout button based on live match-win probability
                    _co_match_id = active_pvb_game_id
                    _co_round = game.get('current_round', 1)
                    _co_mult = calculate_cashout_multiplier(game, user_id=user.id)
                    _co_keyboard = _build_pvb_cashout_keyboard(_co_match_id, _co_round, _co_mult)

                    _co_sent = await update.message.reply_text(
                        f"{pe('robot')} <b>BOT ROLLED FIRST!</b>\n\n"
                        f"Bot rolled: [{bot_rolls_text}] = {bot_total}\n\n"
                        f"{username_display}, Your turn! Send {game_rolls} {expected_emoji} to respond.\n"
                        f"Or tap Cashout to collect <b>${round(game['bet_amount'] * _co_mult, 2):.2f}</b>:",
                        parse_mode=ParseMode.HTML,
                        reply_markup=_co_keyboard
                    )
                    _register_cashout_button(_co_match_id, user.id, update.effective_chat.id, _co_round,
                                             message_id=getattr(_co_sent, 'message_id', None))

                    # Schedule PvB timeout for next round
                    if context.job_queue:
                        _cancel_pvb_timeout_jobs(context, user.id, active_pvb_game_id)
                        round_timeout = game.get('round_timeout', default_round_timeout)
                        warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
                        context.job_queue.run_once(
                            pvb_timeout_warn_job,
                            when=warn_time,
                            data={'user_id': user.id, 'game_id': active_pvb_game_id, 'chat_id': update.effective_chat.id},
                            name=f"pvb_warn_{active_pvb_game_id}"
                        )
                        context.job_queue.run_once(
                            pvb_timeout_finish_job,
                            when=round_timeout,
                            data={'user_id': user.id, 'game_id': active_pvb_game_id, 'chat_id': update.effective_chat.id},
                            name=f"pvb_finish_{active_pvb_game_id}"
                        )
                else:
                    # User rolls first for next round - GREEN cashout available now
                    _co_match_id = active_pvb_game_id
                    _co_round = game.get('current_round', 1)
                    _co_mult = calculate_cashout_multiplier(game, user_id=user.id)
                    _co_keyboard = _build_pvb_cashout_keyboard(_co_match_id, _co_round, _co_mult)

                    _co_sent = await update.message.reply_text(
                        f"Score: You {game['user_score']} - {game['bot_score']} Bot. (First to {game['target_score']})\n\n"
                        f"{user.mention_html()}, <b>Your turn! Send {game_rolls} {expected_emoji}!</b>\n"
                        f"Or tap Cashout to collect <b>${round(game['bet_amount'] * _co_mult, 2):.2f}</b>:",
                        parse_mode=ParseMode.HTML,
                        reply_markup=_co_keyboard
                    )
                    _register_cashout_button(_co_match_id, user.id, update.effective_chat.id, _co_round,
                                             message_id=getattr(_co_sent, 'message_id', None))

                    # Schedule PvB timeout for next round
                    if context.job_queue:
                        _cancel_pvb_timeout_jobs(context, user.id, active_pvb_game_id)
                        round_timeout = game.get('round_timeout', default_round_timeout)
                        warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
                        context.job_queue.run_once(
                            pvb_timeout_warn_job,
                            when=warn_time,
                            data={'user_id': user.id, 'game_id': active_pvb_game_id, 'chat_id': update.effective_chat.id},
                            name=f"pvb_warn_{active_pvb_game_id}"
                        )
                        context.job_queue.run_once(
                            pvb_timeout_finish_job,
                            when=round_timeout,
                            data={'user_id': user.id, 'game_id': active_pvb_game_id, 'chat_id': update.effective_chat.id},
                            name=f"pvb_finish_{active_pvb_game_id}"
                        )
            update_pnl(user.id)
            save_user_data(user.id)
            return  # Return only after processing PvB game emoji

    # Check and prompt helper bots in groups (when emoji game is detected)
    if update.message.dice and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        if update.message.forward_origin is None:
            chat_id = update.effective_chat.id
            await _check_and_prompt_helper_bots(context, chat_id)

    if update.message and update.message.dice and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        # Ignore forwarded messages
        if update.message.forward_origin is not None:
            return

        try:
            dice_obj = update.message.dice
            chat_id = update.effective_chat.id
            emoji = dice_obj.emoji

            if DEBUG_EMOJI_GAMES:
                logging.info(f"PVP DICE: user={user.id}, chat={chat_id}, emoji={emoji}, value={dice_obj.value}")

            # PERFORMANCE: previously this iterated every game_session in
            # the entire bot on every dice message in every group. At
            # 5000 users with thousands of active sessions that was O(N)
            # per dice roll on the hottest path. Prefer the per-user
            # active-games index when it has entries; fall back to a
            # full scan only if the index is empty for this user (which
            # happens for freshly created matches that haven't been
            # indexed yet). We also auto-index on the fallback hit so
            # subsequent rolls are O(user's games).
            _indexed_ids = _get_user_active_game_ids(user.id)
            if _indexed_ids:
                _candidate_items = [(gid, game_sessions.get(gid)) for gid in list(_indexed_ids)]
            else:
                _candidate_items = list(game_sessions.items())
            for match_id, match_data in _candidate_items:
                if not match_data:
                    continue
                if (match_data.get("chat_id") == chat_id and match_data.get("status") == 'active' and user.id in match_data.get("players", [])):
                    # Silently swallow user dice that arrive while the bot is
                    # rolling — same rationale as the PvB block above. Without
                    # this, spamming dice during multi_roll_parallel triggers
                    # overlapping round resolutions.
                    if match_data.get("bot_is_rolling"):
                        return
                    # Auto-index for subsequent rolls on the fast path.
                    if not _indexed_ids:
                        _index_user_game(user.id, match_id)
                    if DEBUG_EMOJI_GAMES:
                        logging.info(f"PVP MATCH FOUND: match_id={match_id}, type={match_data.get('game_type')}, players={match_data.get('players')}, points={match_data.get('points')}")

                    # Extract game type properly - handle pvp_, group_challenge_, xdxw_ prefixes
                    raw_game_type = match_data.get("game_type", "pvp_dice")
                    gtype = raw_game_type.replace("pvp_", "").replace("group_challenge_", "").replace("xdxw_", "")
                    players = match_data["players"]
                    game_rolls = match_data.get("game_rolls", 1)
                    game_mode = match_data.get("game_mode", "normal")

                    # Initialize player_rolls if not exists
                    if "player_rolls" not in match_data:
                        match_data["player_rolls"] = {players[0]: [], players[1]: []}

                    last_roller = match_data.get("last_roller")

                    # Check turn order
                    if last_roller is None:
                        if user.id != players[0]:
                            await update.message.reply_text("It's not your turn yet! Host should roll first.")
                            return
                    elif user.id == last_roller:
                        # Check if current player has completed all rolls
                        if len(match_data["player_rolls"][user.id]) < game_rolls:
                            # Allow more rolls
                            pass
                        else:
                            await update.message.reply_text("Wait for your opponent to roll next.")
                            return
                    else:
                        # Other player's turn, check if they've started rolling
                        if len(match_data["player_rolls"][user.id]) > 0 and len(match_data["player_rolls"][user.id]) < game_rolls:
                            # Allow continuing rolls
                            pass
                        else:
                            # Not this player's turn
                            other_id = [pid for pid in players if pid != user.id][0]
                            if len(match_data["player_rolls"][other_id]) < game_rolls:
                                await update.message.reply_text("Wait for your opponent to complete their rolls.")
                                return

                    allowed_emojis = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
                    if emoji != allowed_emojis.get(gtype, "🎲"):
                        await update.message.reply_text(f"Only {allowed_emojis.get(gtype)} emoji allowed for this match!")
                        return

                    # Add roll to player's rolls
                    match_data["player_rolls"][user.id].append(dice_obj.value)
                    match_data["last_roller"] = user.id

                    # Check if player has completed their rolls
                    current_player_rolls = len(match_data["player_rolls"][user.id])
                    if current_player_rolls < game_rolls:
                        # Don't send spam messages - user knows to send more rolls
                        return

                    # Check if both players have completed their rolls
                    p1, p2 = players
                    p1_rolls = match_data["player_rolls"].get(p1, [])
                    p2_rolls = match_data["player_rolls"].get(p2, [])

                    # Check if playing against bot (opponent_id == 0)
                    is_bot_game = match_data.get("opponent_id") == 0

                    if is_bot_game and user.id == p1 and len(p1_rolls) == game_rolls and len(p2_rolls) < game_rolls:
                        # User (host) completed rolls, now bot should roll using multi_roll_parallel.
                        # Set both bot_is_rolling and waiting_for so any other handler
                        # that re-enters during the await silently skips additional dice.
                        match_data['bot_is_rolling'] = True
                        match_data['waiting_for'] = 'bot'
                        # PERFORMANCE: dropped the asyncio.sleep(1) +
                        # "Bot is rolling..." ack reply. With
                        # AIORateLimiter that ack is a third
                        # message-per-round serialised on the chat's
                        # rate window before the bot's actual dice can
                        # land — and the bot's dice that immediately
                        # follows is itself a clear "bot is rolling"
                        # indicator. Same change has already been made
                        # in the PvB block; this brings the PvP-vs-bot
                        # path to parity.

                        bot_rolls = []
                        # Reply-tag the user's most-recent dice rather
                        # than the original /dice <amount> command
                        # (parity with PvB block above and natural UX).
                        command_msg_id = (update.message.message_id
                                          if update.message else match_data.get('command_message_id'))
                        try:
                            rolls_data = await multi_roll_parallel(context, chat_id, dice_obj.emoji, game_rolls, reply_to_message_id=command_msg_id)
                            for msg, _ in rolls_data:
                                bot_rolls.append(msg.dice.value)
                        except Exception as e:
                            logging.error(f"Error sending bot dice in PvP game: {e}")
                            bot_rolls = [0] * game_rolls  # Fallback

                        match_data["player_rolls"][p2] = bot_rolls
                        p2_rolls = bot_rolls
                        # NOTE: defer clearing bot_is_rolling /
                        # waiting_for until after match_data["player_rolls"]
                        # is reset below — same race-window fix as the
                        # PvB block. Otherwise a dice the user spams
                        # during the round-result `await reply_text`
                        # could append onto the still-full p1_rolls list
                        # and trigger a duplicate bot roll.

                    if len(p1_rolls) == game_rolls and len(p2_rolls) == game_rolls:
                        # Both players completed, calculate results
                        p1_total = sum(p1_rolls)
                        p2_total = sum(p2_rolls)

                        p1_rolls_text = " + ".join(str(r) for r in p1_rolls)
                        p2_rolls_text = " + ".join(str(r) for r in p2_rolls)

                        # Safely get usernames with fallbacks
                        p1_username = match_data.get('usernames', {}).get(p1, f"Player {p1}")
                        p2_username = match_data.get('usernames', {}).get(p2, f"Player {p2}")
                        # Don't show @ for Bot
                        p1_display = p1_username if p1 == 0 else display_at(p1_username)
                        p2_display = p2_username if p2 == 0 else display_at(p2_username)
                        p1_mention = f'<a href="tg://user?id={p1}">{p1_display}</a>'
                        p2_mention = f'<a href="tg://user?id={p2}">{p2_display}</a>'

                        text = f"<b>{p1_username.upper()} ROLLED FIRST!</b>\n"
                        text += f"{p1_mention} rolled: [{p1_rolls_text}] = <b>{p1_total}</b>\n"
                        text += f"{p2_mention} rolled: [{p2_rolls_text}] = <b>{p2_total}</b>\n\n"

                        winner_id, extra_info = None, ""

                        # DEBUG: Log scoring details
                        if DEBUG_EMOJI_GAMES:
                            logging.info(f"SCORING: match_id={match_id}, mode={game_mode}, p1={p1}, p2={p2}, p1_total={p1_total}, p2_total={p2_total}, points_before={match_data.get('points')}")

                        # Determine winner based on mode
                        if game_mode == "normal":
                            # Normal mode: highest total wins
                            if p1_total > p2_total:
                                winner_id = p1
                            elif p2_total > p1_total:
                                winner_id = p2
                            else:
                                extra_info = "🤝 It's a tie! No points this round."
                        else:
                            # Crazy mode: lowest total wins
                            if p1_total < p2_total:
                                winner_id = p1
                            elif p2_total < p1_total:
                                winner_id = p2
                            else:
                                extra_info = "🤝 It's a tie! No points this round."

                        if DEBUG_EMOJI_GAMES:
                            logging.info(f"WINNER: winner_id={winner_id}, extra_info={extra_info}")

                        if winner_id is not None:
                            try:
                                # Ensure points dict has both players
                                if p1 not in match_data.get("points", {}):
                                    match_data.setdefault("points", {})[p1] = 0
                                if p2 not in match_data.get("points", {}):
                                    match_data.setdefault("points", {})[p2] = 0
                                match_data["points"][winner_id] += 1
                                winner_username = match_data.get('usernames', {}).get(winner_id, f'Player {winner_id}')
                                winner_mention = f'<a href="tg://user?id={winner_id}">{display_at(winner_username)}</a>'
                                text += f"{pe('win')} {winner_mention} wins this round!"
                                if DEBUG_EMOJI_GAMES:
                                    logging.info(f"POINTS_UPDATED: {match_data['points']}")
                            except Exception as e:
                                logging.error(f"Error updating points: winner_id={winner_id}, error={e}")
                                text += f"{pe('warning')} Error updating score"
                        else:
                            text += extra_info

                        try:
                            # Ensure points dict has both players for display
                            if p1 not in match_data.get("points", {}):
                                match_data.setdefault("points", {})[p1] = 0
                            if p2 not in match_data.get("points", {}):
                                match_data.setdefault("points", {})[p2] = 0
                            text += f"\n\n<b>Score:</b> {p1_mention} {match_data['points'][p1]} - {match_data['points'][p2]} {p2_mention}"
                        except Exception as e:
                            logging.error(f"Error displaying score: p1={p1}, p2={p2}, error={e}")
                            text += f"\n\n<b>Score:</b> Error displaying score"

                        target = match_data.get("target_points", match_data.get("target_score", 1))
                        final_winner = None
                        # Ensure points dict exists before checking
                        if match_data.get("points"):
                            if match_data["points"].get(p1, 0) >= target: final_winner = p1
                            elif match_data["points"].get(p2, 0) >= target: final_winner = p2

                        # Round fully resolved — clear the bot-rolling guards
                        # before anything that awaits, so legitimate next-round
                        # dice are accepted but late-arriving spam from the
                        # current round (already rejected by the new
                        # `len(player_rolls) >= game_rolls` check above)
                        # cannot trigger a duplicate bot roll. Same
                        # race-window fix as the PvB block.
                        match_data.pop('bot_is_rolling', None)
                        match_data['waiting_for'] = 'user'

                        if final_winner is not None:
                            loser_id = p2 if final_winner == p1 else p1
                            match_data.update({"status": "completed", "winner_id": final_winner})

                            # Resolve side bets for this match
                            winner_index = "p1" if final_winner == p1 else "p2"
                            asyncio.ensure_future(resolve_sidebets_for_match(match_id, winner_index, context))

                            # Use bet_amount_usd if available, otherwise bet_amount
                            bet_amount = match_data.get("bet_amount_usd", match_data.get("bet_amount", 0))
                            winnings = bet_amount * 1.94  # 1.94x multiplier

                            # Credit winner (only if not bot)
                            if final_winner != 0:  # 0 = Bot
                                credit_wallet(final_winner, winnings)
                                await update_stats_on_bet(final_winner, match_id, bet_amount, True, pvp_win=True, multiplier=1.94, context=context)
                                update_pnl(final_winner)
                                save_user_data(final_winner)
                                # Add to player history
                                if 'game_sessions' not in user_stats[final_winner]:
                                    user_stats[final_winner]['game_sessions'] = []
                                user_stats[final_winner]['game_sessions'].append(match_id)

                            # Update loser stats (only if not bot)
                            if loser_id != 0:  # 0 = Bot
                                await update_stats_on_bet(loser_id, match_id, bet_amount, False, context=context)
                                update_pnl(loser_id)
                                save_user_data(loser_id)
                                # Add to player history
                                if 'game_sessions' not in user_stats[loser_id]:
                                    user_stats[loser_id]['game_sessions'] = []
                                user_stats[loser_id]['game_sessions'].append(match_id)

                            final_winner_username = match_data.get('usernames', {}).get(final_winner, f"Player {final_winner}")
                            final_winner_mention = f'<a href="tg://user?id={final_winner}">{display_at(final_winner_username)}</a>'
                            text += f"\n\n{pe('trophy')} <b>{final_winner_mention} wins the match and earns ${winnings:.2f}!</b>"
                            # Emoji-game match messages are no longer pinned.
                        else:
                            match_data["last_roller"] = None
                            match_data["player_rolls"] = {p1: [], p2: []}  # Reset rolls for next round
                            text += f"\n\n<b>Next round:</b> {p1_mention} rolls first! ({allowed_emojis[gtype]} emoji)"

                        await asyncio.sleep(HELPER_BOT_ANIMATION_DELAY)
                        # Cancel any pending PvP timeout jobs since round was resolved
                        _cancel_pvp_timeout_jobs(context, match_id)
                        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
                    else:
                        other_id = [pid for pid in players if pid != user.id][0]
                        other_rolls = len(match_data["player_rolls"].get(other_id, []))
                        # Safely get username with fallback
                        other_username = match_data.get('usernames', {}).get(other_id, f"Player {other_id}")
                        if other_rolls == 0:
                            await asyncio.sleep(1)
                            await update.message.reply_text(f"Your rolls complete! Waiting for {other_username} to start rolling.")
                            # Schedule PvP timeout (only for real PvP, not PvB with bot)
                            if not is_bot_game and context.job_queue:
                                _cancel_pvp_timeout_jobs(context, match_id)
                                round_timeout = match_data.get('round_timeout', default_round_timeout)
                                warn_time = round_timeout - 60 if round_timeout > 60 else max(5, int(round_timeout * 0.75))
                                context.job_queue.run_once(
                                    pvp_timeout_warn_job,
                                    when=warn_time,
                                    data={'match_id': match_id, 'chat_id': chat_id, 'waiting_user_id': other_id, 'rolling_user_id': user.id},
                                    name=f"pvp_warn_{match_id}"
                                )
                                context.job_queue.run_once(
                                    pvp_timeout_finish_job,
                                    when=round_timeout,
                                    data={'match_id': match_id, 'chat_id': chat_id, 'rolling_user_id': user.id},
                                    name=f"pvp_finish_{match_id}"
                                )
                        elif other_rolls < game_rolls:
                            await asyncio.sleep(1)
                            await update.message.reply_text(f"Your rolls complete! Waiting for {other_username} to finish ({other_rolls}/{game_rolls} done).")
                    return
        except Exception as e:
            logging.error(f"Error in PvP game handling: {e}", exc_info=True)
            await update.message.reply_text(f"{pe('cross')} An error occurred processing your roll. Please contact support.")
            return

def generate_surprise_code():
    """Generate a random 5-character surprise code (no prefix)."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(chars) for _ in range(5))

async def _show_games_history_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Render a paginated page of recent game history for admin."""
    completed_games = []
    for gid, gdata in game_sessions.items():
        status = gdata.get("status", "")
        if status in ("completed", "finished", "ended", "resolved"):
            completed_games.append((gid, gdata))

    completed_games.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
    total = len(completed_games)
    total_pages = max(1, (total + GAMES_HISTORY_PER_PAGE - 1) // GAMES_HISTORY_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start = page * GAMES_HISTORY_PER_PAGE
    page_games = completed_games[start:start + GAMES_HISTORY_PER_PAGE]

    msg = f"\U0001f4dc <b>Recent Games History</b> (Page {page + 1}/{total_pages})\n\n"

    if not page_games:
        msg += "No completed games found.\n"
    else:
        for gid, gdata in page_games:
            game_type = gdata.get("game_type", "unknown").replace("pvp_", "PvP ").replace("_", " ").title()
            bet = gdata.get("bet_amount", gdata.get("bet_amount_usd", 0))
            winner_id = gdata.get("winner_id", None)
            winner_name = gdata.get("winner_username", "N/A")
            if winner_id:
                winner_name = gdata.get("usernames", {}).get(winner_id, winner_name)
            ts = gdata.get("timestamp", "N/A")
            if isinstance(ts, str) and len(ts) > 19:
                ts = ts[:19]
            msg += (
                f"\U0001f3b2 <b>{game_type}</b>\n"
                f"   ID: <code>{gid}</code>\n"
                f"   Bet: ${bet:.2f}\n"
                f"   Winner: {winner_name}\n"
                f"   Time: {ts}\n\n"
            )

    buttons = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("\u25c0 Back", callback_data=f"admin_ghist_page_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next \u25b6", callback_data=f"admin_ghist_page_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("Close", callback_data="close")])

    if update.callback_query:
        await safe_edit_message(
            update.callback_query, msg,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await update.message.reply_text(
            msg, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

