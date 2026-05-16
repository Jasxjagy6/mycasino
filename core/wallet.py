"""Auto-split from bot.py — core.wallet."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def format_crypto_amount(amount: float, coin: str) -> str:
    """Format crypto amount with appropriate precision."""
    precision = CRYPTO_PRECISION.get(coin, 5)
    return f"{amount:.{precision}f}"

def get_total_balance_usd(user_id: int) -> float:
    """Get total portfolio value in USD across all coins."""
    wallet = ensure_wallet_dict(user_id)
    total = 0.0
    for coin, amount in wallet.items():
        price = LIVE_PRICES.get(coin, 1.0)
        total += amount * price
    return total

def deduct_wallet(user_id: int, usd_amount: float, coin: str = None,
                  *, locked_price: float = None):
    """Deduct crypto equivalent of USD amount from user's wallet.
    Returns (crypto_amount, coin).

    Phase 1d (audit S19): pass ``locked_price`` to deduct at a quote
    that was locked just before the call (e.g. taken with
    ``core.prices.lock_price``). The matching credit/refund call
    should pass the same ``locked_price`` to keep the round-trip
    USD<->crypto conversion symmetric.

    SECURITY: Validates amount and prevents going negative."""
    import math as _math_dw
    if _math_dw.isnan(usd_amount) or _math_dw.isinf(usd_amount) or usd_amount <= 0:
        logging.warning(f"deduct_wallet: rejected invalid amount {usd_amount} for user {user_id}")
        return 0.0, coin or get_active_currency(user_id)
    wallet = ensure_wallet_dict(user_id)
    if coin is None:
        coin = get_active_currency(user_id)
    if locked_price is not None and locked_price > 0:
        price = float(locked_price)
    else:
        price = LIVE_PRICES.get(coin, 1.0)
    crypto_amount = usd_amount / price
    current = wallet.get(coin, 0.0)
    if current < crypto_amount - 1e-10:
        logging.warning(f"deduct_wallet: INSUFFICIENT user {user_id} has {current} {coin} but needs {crypto_amount} {coin}")
        raise ValueError("INSUFFICIENT_FUNDS")
    wallet[coin] = max(0.0, current - crypto_amount)
    return crypto_amount, coin

async def deduct_wallet_safe(user_id: int, usd_amount: float, coin: str = None,
                              *, locked_price: float = None):
    """
    ATOMIC wallet deduction using per-user asyncio.Lock.
    Returns (crypto_amount, coin) or raises ValueError("INSUFFICIENT_FUNDS").
    Use this instead of deduct_wallet() everywhere a bet is placed.

    Phase 1d: pass ``locked_price`` to use a previously-locked quote
    instead of the current ``LIVE_PRICES`` value.
    """
    async with _get_wallet_lock(user_id):
        wallet = ensure_wallet_dict(user_id)
        if coin is None:
            coin = get_active_currency(user_id)
        if locked_price is not None and locked_price > 0:
            price = float(locked_price)
        else:
            price = LIVE_PRICES.get(coin, 1.0)
        crypto_amount = usd_amount / price
        current = wallet.get(coin, 0.0)
        if current < crypto_amount - 1e-10:
            raise ValueError("INSUFFICIENT_FUNDS")
        wallet[coin] = current - crypto_amount
        return crypto_amount, coin

def calculate_bet_deduction(user_id: int, bet_amount_usd: float) -> tuple:
    """Stake-style: calculate crypto deduction for a USD bet.
    Returns (crypto_amount, coin, has_sufficient) tuple."""
    coin = get_active_currency(user_id)
    price = LIVE_PRICES.get(coin, 1.0)
    crypto_amount = bet_amount_usd / price
    wallet = ensure_wallet_dict(user_id)
    has_sufficient = wallet.get(coin, 0.0) >= crypto_amount
    return crypto_amount, coin, has_sufficient

def validate_bet_amount(bet_amount: float, game_category: str = "originals") -> tuple:
    """Validate bet amount against global limits and house controls.
    Returns (is_valid: bool, error_message: str or None)"""
    if not isinstance(bet_amount, (int, float)):
        return False, "Invalid bet amount"
    import math
    if math.isnan(bet_amount) or math.isinf(bet_amount) or bet_amount <= 0:
        return False, "Bet amount must be a positive number"
    if bet_amount < MIN_BALANCE:
        return False, f"Minimum bet is ${MIN_BALANCE}"
    # Use dynamic max bet limits based on house balance
    max_bet = get_dynamic_max_bet(game_category)
    if bet_amount > max_bet:
        return False, f"Maximum bet is ${max_bet:.2f} for this game"
    return True, None

def check_withdrawal_limit(user_id: int, amount_usd: float) -> tuple:
    """Check if withdrawal is within limits.
    Returns (is_allowed: bool, error_message: str or None)"""
    limits = bot_settings.get('withdrawal_limits', {})
    min_withdrawal = limits.get('min_per_withdrawal', 1.0)
    if amount_usd < min_withdrawal:
        return False, f"Minimum withdrawal is ${min_withdrawal:.2f}"
    max_per_withdrawal = limits.get('max_per_withdrawal', 5000.0)
    if amount_usd > max_per_withdrawal:
        return False, f"Maximum withdrawal is ${max_per_withdrawal:.2f} per transaction"
    wagering_mult = limits.get('wagering_multiplier', 0.0)
    if wagering_mult > 0 and user_id in user_stats:
        unwagered = user_stats[user_id].get('unwagered_deposit', 0.0)
        if unwagered > 0:
            required_wager = unwagered * wagering_mult
            total_wagered = user_stats[user_id].get('bets', {}).get('amount', 0.0)
            if total_wagered < required_wager:
                return False, f"You must wager your deposit {wagering_mult}x before withdrawal."
    return True, None

# ---------------------------------------------------------------------
# Phase 1f (audit M3): refund the EXACT crypto bet, not USD at current
# price.
# ---------------------------------------------------------------------
#
# Before this fix, admin ``/cancel <game_id>`` did
# ``credit_wallet(player_id, bet_amount_usd)`` which converts using the
# *current* ``LIVE_PRICES`` value. A user could bet at BTC=$60k, watch
# the price drop to $50k, ask the admin to cancel, and end up with
# 20%% more BTC than they started with -- free arbitrage on the
# admin's response time.
#
# ``refund_bet`` refunds the exact crypto amount that was originally
# deducted. It tries (in order):
#
#   1. ``game_data["crypto_bet_amount"]`` + ``game_data["active_currency"]``
#        -- stored at bet time by almost all single-player games
#   2. ``game_data["deducted"][player_id]`` (Phase 1f addition for PvP)
#        -- structured per-player record stored when the bet was taken
#   3. ``game_data["locked_price"]`` (Phase 1d-style price lock)
#        -- ``bet_amount / locked_price`` reconstructs the crypto
#   4. Final fallback: ``credit_wallet(user_id, bet_amount)`` with a
#      WARNING log noting that the refund used the *current* price
#      because no locked info was available.
#
# Return value: ``(credited_crypto_amount: float, coin: str)`` so
# callers can show the user "You were refunded 0.000833 BTC".


def refund_bet(player_id: int, game_data: dict, *, reason: str = "cancel"):
    """Refund the exact crypto bet for a single player in ``game_data``.

    ``game_data`` is the dict stored in ``game_sessions[game_id]`` (or
    a similar match dict). For PvP games, the caller passes the
    *match* dict for ``game_data`` and the relevant ``player_id``;
    the helper picks the per-player deducted info out of
    ``game_data["deducted"]`` if present.

    Returns ``(credited_crypto_amount, coin)``.
    """
    import math as _math_rb

    def _credit_crypto_direct(coin: str, crypto_amount: float):
        """Bypass ``credit_wallet``'s USD-to-crypto conversion and add
        the crypto amount directly to the player's wallet."""
        if (
            _math_rb.isnan(crypto_amount) or _math_rb.isinf(crypto_amount)
            or crypto_amount <= 0
        ):
            logging.warning(
                "refund_bet: rejected invalid crypto amount %r for user %s "
                "(reason=%s)",
                crypto_amount, player_id, reason,
            )
            return 0.0, coin
        wallet = ensure_wallet_dict(player_id)
        wallet[coin] = wallet.get(coin, 0.0) + float(crypto_amount)
        logging.info(
            "refund_bet user=%s coin=%s amount=%.10f (reason=%s, source=%s)",
            player_id, coin, float(crypto_amount), reason,
            "direct-crypto",
        )
        return float(crypto_amount), coin

    # 1. Per-player record stored at deduct time (PvP).
    deducted = game_data.get("deducted") if isinstance(game_data, dict) else None
    if isinstance(deducted, dict):
        record = deducted.get(player_id) or deducted.get(str(player_id))
        if isinstance(record, dict):
            crypto_amount = record.get("crypto_amount")
            coin = record.get("coin")
            if coin and crypto_amount is not None:
                return _credit_crypto_direct(str(coin), float(crypto_amount))

    # 2. Single-player game with crypto_bet_amount + active_currency.
    crypto_bet = game_data.get("crypto_bet_amount")
    active_currency = game_data.get("active_currency") or game_data.get("coin")
    if crypto_bet is not None and active_currency:
        return _credit_crypto_direct(str(active_currency), float(crypto_bet))

    # 3. Locked-price-style: USD bet + locked_price quote.
    bet_amount_usd = game_data.get("bet_amount") or game_data.get("bet_amount_usd")
    locked_price = game_data.get("locked_price")
    locked_coin = game_data.get("locked_coin") or game_data.get("active_currency")
    if (
        bet_amount_usd is not None and locked_price
        and locked_coin and float(locked_price) > 0
    ):
        crypto_amount = float(bet_amount_usd) / float(locked_price)
        return _credit_crypto_direct(str(locked_coin), crypto_amount)

    # 4. Last resort -- old behaviour. Log loudly so operators know
    # they refunded at the current price (potential arbitrage).
    if bet_amount_usd is None:
        logging.error(
            "refund_bet: no usable bet amount in game_data for user %s "
            "(reason=%s, keys=%s)",
            player_id, reason, list(game_data.keys()) if isinstance(game_data, dict) else None,
        )
        return 0.0, get_active_currency(player_id)
    logging.warning(
        "refund_bet user=%s reason=%s -- FALLBACK to USD@LIVE_PRICES "
        "(no crypto info in game_data; possible arbitrage on price drift)",
        player_id, reason,
    )
    credited, coin = credit_wallet_safe(player_id, float(bet_amount_usd))
    return credited, coin


def get_locked_balance_in_games(user_id: int) -> dict:
    """
    Calculate total locked balance in active games and provide breakdown by game type.
    Returns dict with 'total' and 'games' (list of game details)
    """
    locked_total = 0.0
    game_breakdown = []

    # PERFORMANCE: Use the O(1) per-user active-games index. Previous
    # implementation did a full dict scan over every game_session in the
    # system on every single /balance view — O(total games) instead of
    # O(just this user's games).
    for game_id in list(_get_user_active_game_ids(user_id)):
        game = game_sessions.get(game_id)
        if not game or game.get('status') != 'active':
            continue
        if game.get('user_id') != user_id:
            continue
        bet_amount = game.get('bet_amount', 0.0)
        game_type = game.get('game_type', 'unknown')
        locked_total += bet_amount
        game_breakdown.append({
            'game_id': game_id,
            'game_type': game_type,
            'amount': bet_amount
        })

    return {'total': locked_total, 'games': game_breakdown}

def format_balance_with_locked(user_id: int, currency: str = "USD") -> str:
    """
    Format the user's portfolio using their chosen DISPLAY currency.

    Every headline line shows
        <symbol><amount in display currency> (~ N.NN USDT)
    which is the format the user asked for in group chats, and
    also renders the per-coin breakdown of what actually sits in
    the wallet so users can still see which crypto they hold.
    """
    wallet = ensure_wallet_dict(user_id)
    total_usd = get_total_balance_usd(user_id)
    active_coin = get_active_currency(user_id)
    disp = get_display_currency(user_id)
    disp_sym = CURRENCY_SYMBOLS.get(disp, "")

    # Total in the user's display currency + USDT estimate.
    total_display = format_for_user(user_id, total_usd, compact=False, with_usdt_estimate=(disp != "USDT"))
    lines = [f"{pe('briefcase')} Total Portfolio: <b>{total_display}</b>\n"]

    for coin, amount in wallet.items():
        if amount > 0 or coin == active_coin:
            price = LIVE_PRICES.get(coin, 1.0)
            usd_val = amount * price
            symbol = CRYPTO_SYMBOLS.get(coin, "💎")
            formatted_amount = format_crypto_amount(amount, coin)
            if usd_val > 0.001 or coin == active_coin:
                # Show the crypto holding AND what it's worth in the user's display currency.
                disp_val = format_display_amount(usd_val, disp, compact=False)
                lines.append(f"{symbol} {coin}: {disp_val} ({formatted_amount} {coin})")

    lines.append(f"\n{pe('diamond')} Active Currency: {active_coin}")
    if disp != active_coin:
        lines.append(f"{pe('settings')} Display Currency: {disp_sym}{disp}")

    locked_info = get_locked_balance_in_games(user_id)

    if locked_info['total'] > 0:
        game_totals = {}
        for game in locked_info['games']:
            game_type = game['game_type']
            if game_type not in game_totals:
                game_totals[game_type] = 0.0
            game_totals[game_type] += game['amount']

        locked_parts = []
        for game_type, amount in game_totals.items():
            locked_parts.append(f"{format_display_amount(amount, disp)} in game ( {game_type} )")

        locked_str = " + ".join(locked_parts)
        lines.append(f"{pe('lock')} Locked: {locked_str}")

    return "\n".join(lines)

def update_stats_on_withdrawal(user_id, amount, tx_hash, method):
    stats = user_stats[user_id]
    withdrawal_record = {
        "amount": amount,
        "tx_hash": tx_hash,
        "method": method,
        "timestamp": str(datetime.now(timezone.utc))
    }
    stats["withdrawals"].append(withdrawal_record)
    save_user_data(user_id)

def update_stats_on_tip_received(user_id, amount):
    stats = user_stats[user_id]
    stats["tips_received"]["count"] += 1
    stats["tips_received"]["amount"] += amount
    save_user_data(user_id)

def update_stats_on_tip_sent(user_id, amount):
    stats = user_stats[user_id]
    stats["tips_sent"]["count"] += 1
    stats["tips_sent"]["amount"] += amount
    save_user_data(user_id)

def reduce_unwagered_amounts(user_id, bet_amount):
    """
    Reduce unwagered deposit and tip amounts when a bet is placed.

    Tip requirement: 1x wagering (each $1 bet reduces $1 of unwagered tips)
    Deposit requirement: 2x wagering (each $1 bet reduces $0.50 of unwagered deposits,
                         because the user needs to wager 2x the deposit amount)

    Example: $100 deposit requires $200 total wagering
    - After $50 bet: $75 deposit still unwagered (needs $150 more wagering)
    - After $100 bet: $50 deposit still unwagered (needs $100 more wagering)
    - After $200 bet: $0 deposit unwagered (requirement met)
    """
    if user_id not in user_stats:
        return

    stats = user_stats[user_id]
    remaining_bet = bet_amount

    # First, reduce unwagered tips (1x requirement - direct reduction)
    unwagered_tips = stats.get("unwagered_tips", 0.0)
    if unwagered_tips > 0 and remaining_bet > 0:
        reduction = min(unwagered_tips, remaining_bet)
        stats["unwagered_tips"] = max(0, unwagered_tips - reduction)
        remaining_bet -= reduction

    # Then, reduce unwagered deposits (2x requirement - each $1 bet reduces $0.50 of unwagered deposit)
    unwagered_deposit = stats.get("unwagered_deposit", 0.0)
    if unwagered_deposit > 0 and remaining_bet > 0:
        # For 2x requirement, each $1 bet reduces $0.50 of the unwagered deposit amount
        deposit_reduction = remaining_bet / 2.0
        reduction = min(unwagered_deposit, deposit_reduction)
        stats["unwagered_deposit"] = max(0, unwagered_deposit - reduction)

def calculate_required_wager(user_id):
    """
    Calculate how much more the user needs to wager before they can withdraw.
    Returns (total_required, breakdown_dict)
    """
    if user_id not in user_stats:
        return 0.0, {}

    stats = user_stats[user_id]
    unwagered_tips = stats.get("unwagered_tips", 0.0)
    unwagered_deposit = stats.get("unwagered_deposit", 0.0)

    # Tips need 1x wagering
    tips_wager_needed = unwagered_tips

    # Deposits need 2x wagering (so need to wager 2x the unwagered amount)
    deposit_wager_needed = unwagered_deposit * 2.0

    total_needed = tips_wager_needed + deposit_wager_needed

    breakdown = {
        "unwagered_tips": unwagered_tips,
        "tips_wager_needed": tips_wager_needed,
        "unwagered_deposit": unwagered_deposit,
        "deposit_wager_needed": deposit_wager_needed,
        "total_wager_needed": total_needed
    }

    return total_needed, breakdown

async def update_stats_on_bet(user_id, game_id, amount, win, pvp_win=False,
                               multiplier=0, context=None, game_type=None,
                               push=False):
    """OPTIMIZED ASYNC version. Fast in-memory mutations only.

    Phase 1b fix (audit S6 / M5): added ``push`` parameter so blackjack
    pushes (and any future tie outcomes) are recorded correctly. Before
    this fix a push was passed as ``win=False, multiplier=0``, which the
    function treated as a full LOSS and added the bet amount to
    ``bot_settings['house_balance']`` even though the stake had been
    returned to the player via ``credit_wallet``. That silently inflated
    the house balance on every tie and pulled the dynamic max-bet
    ceiling above real reserves.

    On push:
      * ``bot_settings['house_balance']`` is NOT touched (the bet was
        returned to the player).
      * ``stats['bets']['pushes']`` is incremented; wins/losses counts
        are unchanged.
      * Wagered amount, rakeback, raffle tickets and weekly/monthly
        ``weighted_wager`` still accrue (push counts as wagering).
      * Weekly/monthly ``net_loss`` accrues 0 for this bet.

    Defers all heavy work.
    """
    stats = user_stats[user_id]
    stats["bets"]["count"] += 1
    stats["bets"]["amount"] += amount
    # Jackpot accumulator hook: 0.2% of every bet feeds the pool, and the
    # bet contributes to the user's 7-day eligibility wager.
    try:
        _jackpot_credit(user_id, amount)
    except Exception as _e:
        logging.error(f"Jackpot credit hook failed: {_e}")

    reduce_unwagered_amounts(user_id, amount)

    win_amount = 0
    if game_type is None:
        game_type = game_sessions.get(game_id, {}).get('game_type', 'unknown')

    # Phase 1b: resolve outcome via the pure helper in core.game_math so
    # the push / win / loss accounting lives in one tested place.
    from core.game_math import resolve_bet_outcome as _resolve_bet_outcome
    outcome = _resolve_bet_outcome(amount, win, multiplier=multiplier, push=push)
    # Phase 1e (audit S5): every house_balance mutation routes through
    # apply_house_balance_delta so the operation serialises and we get
    # an audit-log entry for post-mortems of unexplained drift. Pushes
    # have a zero delta which short-circuits in the helper.
    if outcome.house_balance_delta != 0.0:
        await apply_house_balance_delta(
            outcome.house_balance_delta,
            reason=f"bet:{game_type}:{game_id}",
        )
    win_amount = outcome.win_amount
    if outcome.counter == "wins":
        if outcome.net_loss_this_bet < 0:
            stats["last_win"] = -outcome.net_loss_this_bet
        stats["bets"]["wins"] += 1
        if pvp_win:
            stats["bets"]["pvp_wins"] = stats["bets"].get("pvp_wins", 0) + 1
    elif outcome.counter == "pushes":
        stats["bets"].setdefault("pushes", 0)
        stats["bets"]["pushes"] += 1
    else:
        stats["bets"]["losses"] += 1

    # Game session history — cap at 100
    if 'game_sessions' not in stats:
        stats['game_sessions'] = []
    stats['game_sessions'].append(game_id)
    if len(stats['game_sessions']) > 100:
        stats['game_sessions'] = stats['game_sessions'][-100:]

    # Bet history — cap at 500
    if 'history' not in stats['bets']:
        stats['bets']['history'] = []
    stats['bets']['history'].append({
        "amount": amount,
        "timestamp": str(datetime.now(timezone.utc))
    })
    if len(stats['bets']['history']) > 500:
        stats['bets']['history'] = stats['bets']['history'][-500:]

    # Rakeback (pure dict ops, fast).
    #
    # Phase 1c (audit M14): the jackpot pool is fed
    # ``JACKPOT_DEFAULT_ACCUM_RATE`` of every bet (default 0.2%) via
    # ``_jackpot_credit`` above. That portion of the declared house
    # edge is paid back to players via jackpot draws -- if we *also*
    # rebate it via rakeback we'd be rebating the same skim twice.
    # ``effective_rakeback_edge`` returns ``declared_edge -
    # jackpot_rate`` (floored at zero), so rakeback rebates only the
    # part the house actually keeps.
    from core.game_math import effective_rakeback_edge as _effective_rakeback_edge
    edge_category = GAME_TYPE_TO_EDGE_CATEGORY.get(game_type, "originals")
    house_edge_rate = HOUSE_EDGES.get(edge_category, HOUSE_EDGES["originals"])
    jackpot_rate = float(JACKPOT_DEFAULT_ACCUM_RATE or 0.0)
    rakeback_edge_rate = _effective_rakeback_edge(house_edge_rate, jackpot_rate)
    edge_amount = amount * rakeback_edge_rate
    level_data = get_user_level(user_id)
    vip_rakeback_pct = level_data["rakeback_percentage"] / 100.0
    stats.setdefault("rakeback_balance", 0.0)
    stats["rakeback_balance"] += edge_amount * vip_rakeback_pct

    # Weekly / monthly stats (fast). ``net_loss_this_bet`` comes from
    # the same outcome resolution above so push / win / loss accounting
    # stays consistent (audit S6 / M5). ``weighted_wager`` keeps the
    # *declared* edge so leaderboard/VIP progression weighs games by
    # their nominal house edge (slots > originals > pvp) -- unchanged.
    weighted_wager = amount * house_edge_rate
    net_loss_this_bet = outcome.net_loss_this_bet
    stats.setdefault("weekly_stats", {"weighted_wager": 0.0, "net_loss": 0.0, "last_claim": None})
    stats["weekly_stats"]["weighted_wager"] += weighted_wager
    stats["weekly_stats"]["net_loss"] += net_loss_this_bet
    stats.setdefault("monthly_stats", {"weighted_wager": 0.0, "net_loss": 0.0, "last_claim": None})
    stats["monthly_stats"]["weighted_wager"] += weighted_wager
    stats["monthly_stats"]["net_loss"] += net_loss_this_bet

    # Raffle tracking (fast in-memory)
    for raffle_id, raffle in list(active_raffles.items()):
        eligible = (raffle['type'] == 'all') or (
            raffle['type'] == 'referrals' and
            user_stats[user_id]['referral'].get('referrer_id') == raffle['creator']
        )
        if eligible:
            raffle['wager_tracker'].setdefault(user_id, 0.0)
            raffle['wager_tracker'][user_id] += amount
            raffle['tickets'].setdefault(user_id, 0)
            # FIX: Use math instead of while loop to prevent blocking on large bets
            ticket_cost = raffle['ticket_cost']
            if ticket_cost > 0:
                new_tickets = int(raffle['wager_tracker'][user_id] / ticket_cost)
                if new_tickets > 0:
                    raffle['tickets'][user_id] += new_tickets
                    raffle['wager_tracker'][user_id] %= ticket_cost

    # Non-blocking mark-dirty
    save_user_data(user_id)

    # Update leaderboard immediately (no buffer delay)
    try:
        update_leaderboards(user_id, amount, win_amount, game_type, multiplier)
    except Exception as e:
        logging.error(f"Leaderboard update failed for user {user_id}: {e}", exc_info=True)

    # Fire-and-forget background tasks
    asyncio.create_task(process_referral_commission(user_id, amount, 'bet'))
    asyncio.create_task(check_and_award_achievements(user_id, context, multiplier))
    asyncio.create_task(check_and_award_level_up(user_id, context))

    # Broadcast every win to the public channel via a helper bot. Wrapped
    # in a try/except so a broadcast failure can never break gameplay.
    if win and win_amount and win_amount > 0:
        try:
            from core import win_broadcaster
            # Resolve a human-readable game type. Many call sites pass
            # only ``game_id`` (no ``game_type``) and a corresponding
            # entry in ``game_sessions`` may have already been popped by
            # the time we reach here. Fall back to the prefix of the
            # game id which encodes the game (eg. ``SCRATCH-…``,
            # ``BJ-…``, ``MNS-…``).
            broadcast_game_type = game_type
            if not broadcast_game_type or broadcast_game_type == 'unknown':
                gid = str(game_id or '')
                prefix = gid.split('-', 1)[0].lower() if gid else ''
                broadcast_game_type = prefix or 'game'
            win_broadcaster.schedule_win_broadcast(
                user_id=user_id,
                game_type=broadcast_game_type,
                bet_usd=amount,
                win_usd=win_amount,
                multiplier=multiplier,
            )
        except Exception as _e:
            logging.debug(f"Win broadcast scheduling failed: {_e}")

def check_username_bonus(user_id):
    """Check if a user has the bot username tag in their Telegram name.
    Returns True if the user gets the 5% extra bonus."""
    if not BOT_USERNAME_TAG_NORMALIZED:
        return False
    stats = user_stats.get(user_id, {})
    first_name = stats.get("userinfo", {}).get("first_name", "")
    # Check in first_name (this is where Telegram users set their display name)
    return BOT_USERNAME_TAG_NORMALIZED in (first_name or "").lower()

def apply_username_bonus(amount, user_id):
    """Apply 5% extra bonus if user has bot username in their name."""
    if check_username_bonus(user_id):
        return amount * 1.05
    return amount

def get_username_bonus_guidance():
    """Return guidance message for users to add bot username to their name."""
    if BOT_USERNAME_TAG:
        # Use proper mention/link format instead of plain code
        tag_without_at = BOT_USERNAME_TAG.replace('@', '')
        return (f"\n\n💡 <b>Tip:</b> Add <a href='https://t.me/{tag_without_at}'>{BOT_USERNAME_TAG}</a> to your Telegram name "
                f"to get <b>5% extra</b> on all bonus claims (rakeback, weekly, monthly)!")
    return ""

def get_user_tier(user_id):
    """Get the user's VIP tier name (e.g. 'Bronze', 'Silver', etc.)."""
    level_data = get_user_level(user_id)
    tier = level_data["name"].split()[0] if level_data["name"] != "None" else "Bronze"
    return tier

def update_stats_on_rain_received(user_id, amount):
    stats = user_stats[user_id]
    stats["rain_received"]["count"] += 1
    stats["rain_received"]["amount"] += amount
    save_user_data(user_id)

def update_pnl(user_id):
    stats = user_stats[user_id]
    total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
    total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))
    stats["pnl"] = (total_withdrawals + get_total_balance_usd(user_id)) - (total_deposits + stats["tips_received"]["amount"])
    save_user_data(user_id)

def get_all_registered_user_ids():
    return list(user_stats.keys())

async def _show_wallet_history(update, context, query, page):
    """Show wallet user's game history (matches the /history command)."""
    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    stats = user_stats.get(user.id, {})
    game_ids = list(reversed(stats.get('game_sessions', [])))
    total_games = len(game_ids)

    if total_games == 0:
        text = (
            f"{pe('chart')} <b>Game Matches</b>\n\n"
            f"No games found. Start playing to see your history!"
        )
        keyboard = [[InlineKeyboardButton("Back to Wallet", callback_data="main_wallet")]]
        await safe_edit_message(query, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Generate history template image
    history_image = await generate_history_image(user.id, context, page)

    # Build pagination keyboard with Back to Wallet
    keyboard = _build_history_keyboard(game_ids, page, user.id)
    keyboard.append([InlineKeyboardButton("Back to Wallet", callback_data="main_wallet")])

    if history_image:
        try:
            # Delete old message and send new with photo
            await query.message.delete()
            sent = await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=history_image,
                caption=f"{pe('chart')} <b>Game Matches</b> ({total_games} games)",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            set_menu_owner(sent, user.id)
        except Exception as e:
            logging.error(f"Error sending history image: {e}")
            # Fallback to text
            await safe_edit_message(
                query,
                f"{pe('chart')} <b>Game Matches</b> ({total_games} games)",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await safe_edit_message(
            query,
            f"{pe('chart')} <b>Game Matches</b> ({total_games} games)",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def _show_wallet_transactions(update, context, query):
    """Show wallet user's transactions (matches the /transactions command)."""
    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # Check if user is banned
    if user.id in bot_settings.get("banned_users", []):
        await query.answer("You are banned.", show_alert=True)
        return
    if user.id in bot_settings.get("tempbanned_users", []):
        await query.answer("You are temporarily banned.", show_alert=True)
        return

    # Collect transactions
    transactions = await collect_user_transactions(user.id)
    total = len(transactions)

    if total == 0:
        text = (
            f"{pe('chart')} <b>Transactions</b>\n\n"
            f"No transactions found."
        )
        keyboard = [[InlineKeyboardButton("Back to Wallet", callback_data="main_wallet")]]
        await safe_edit_message(query, text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Build first page
    start_idx = 0
    end_idx = min(TRANSACTIONS_PER_PAGE, total)
    page_items = transactions[start_idx:end_idx]
    total_pages = (total + TRANSACTIONS_PER_PAGE - 1) // TRANSACTIONS_PER_PAGE

    lines = []
    for tx in page_items:
        lines.append(format_transaction(tx))

    text = f"{pe('chart')} <b>Transaction History</b>\n"
    text += f"\nPage 1 of {total_pages} ({total} transactions)\n\n"
    text += "\n\n──────────\n\n".join(lines)

    # Build navigation keyboard
    keyboard = []
    nav_row = []

    # Next button (blue) with premium emoji
    if total_pages > 1:
        callback_data = f"txn_page_{user.id}_1_0"
        nav_row.append(apply_button_style(
            InlineKeyboardButton("Next", callback_data=callback_data),
            'primary',
            peb('arrow_right')
        ))

    if nav_row:
        keyboard.append(nav_row)

    # Back to Wallet button
    keyboard.append([InlineKeyboardButton("Back to Wallet", callback_data="main_wallet")])

    await safe_edit_message(
        query,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ensure_user_in_wallets_sync(user_id, username, context):
    """Ensure user exists in user_wallets; calls ensure_user_in_wallets only if missing (which may involve a DB call)."""
    if user_id not in user_wallets:
        await ensure_user_in_wallets(user_id, username, context=context)

