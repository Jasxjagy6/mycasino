"""Auto-split from bot.py — plugins.jackpot."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def _jackpot_today_utc_key(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")

def _jackpot_save_now():
    """Synchronous save. Cheap (small JSON), safe to call from async via run_in_executor."""
    global _jackpot_dirty
    try:
        tmp = JACKPOT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_jackpot_state, f, indent=2, default=str)
        os.replace(tmp, JACKPOT_FILE)
        _jackpot_dirty = False
    except Exception as e:
        logging.error(f"Failed to save jackpot state: {e}")

def _jackpot_prune_user(user_id):
    """Keep only the last 7 UTC-day buckets for this user."""
    key = str(user_id)
    bucket = _jackpot_state["user_wagers"].get(key)
    if not isinstance(bucket, dict):
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    pruned = {d: v for d, v in bucket.items() if d > cutoff}
    if pruned:
        _jackpot_state["user_wagers"][key] = pruned
    else:
        _jackpot_state["user_wagers"].pop(key, None)

def _jackpot_user_7d_wager(user_id) -> float:
    _jackpot_load()
    _jackpot_prune_user(user_id)
    bucket = _jackpot_state["user_wagers"].get(str(user_id))
    if not bucket:
        return 0.0
    try:
        return float(sum(float(v) for v in bucket.values()))
    except (TypeError, ValueError):
        return 0.0

def _jackpot_credit(user_id: int, bet_amount_usd: float):
    """Hook called from ``update_stats_on_bet``. Adds the configured
    percentage of ``bet_amount_usd`` to the pool and records the bet
    against the user's 7-day wager bucket.

    Phase 2: when ``MYCASINO_REDIS_BACKEND`` is set, the pool delta is
    also added to a Redis ``INCRBYFLOAT`` counter via
    :func:`core.redis_backend.incr_jackpot`.  This is a *mirror*, not
    a switch-over: the in-memory pool stays the source of truth for
    the player-facing ``/jackpot`` UI until reads are flipped in a
    later PR.  Multiple stateless workers can credit the same pool
    without losing increments.
    """
    if bet_amount_usd is None or bet_amount_usd <= 0:
        return
    _jackpot_load()
    rate = float(_jackpot_state.get("accum_rate", JACKPOT_DEFAULT_ACCUM_RATE) or 0.0)
    contribution = float(bet_amount_usd) * rate
    if contribution > 0:
        _jackpot_state["pool"] = float(_jackpot_state.get("pool", 0.0)) + contribution
        # Best-effort Redis mirror.  Schedule fire-and-forget so the
        # sync caller never blocks on network I/O.
        try:
            from core import redis_backend as _rb
            if _rb.redis_enabled():
                import asyncio as _aio
                try:
                    _loop = _aio.get_running_loop()
                    _loop.create_task(_rb.incr_jackpot("daily", contribution))
                except RuntimeError:
                    # No running loop (e.g. called from a sync test) — drop.
                    pass
        except Exception:  # noqa: BLE001
            logging.exception("Redis jackpot mirror failed for user=%s", user_id)
    key = str(user_id)
    bucket = _jackpot_state["user_wagers"].setdefault(key, {})
    today = _jackpot_today_utc_key()
    bucket[today] = float(bucket.get(today, 0.0)) + float(bet_amount_usd)
    _jackpot_prune_user(user_id)
    _jackpot_mark_dirty()

def _jackpot_get_font(size: int):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _jackpot_paste_circle_avatar(img, avatar, x, y, size, ring_color):
    """Paste a circular avatar onto ``img`` at (x, y). Returns possibly
    converted RGB ``img`` and a fresh ``ImageDraw``."""
    draw = ImageDraw.Draw(img)
    draw.ellipse([x - 2, y - 2, x + size + 2, y + size + 2],
                 outline=ring_color, width=2)
    if avatar is None:
        draw.ellipse([x, y, x + size, y + size], fill=(20, 30, 60))
        return img, draw
    try:
        a = avatar.resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
        rgba = img.convert("RGBA")
        a_rgba = a.convert("RGBA")
        a_rgba.putalpha(mask)
        rgba.paste(a_rgba, (x, y), a_rgba)
        img = rgba.convert("RGB")
        return img, ImageDraw.Draw(img)
    except Exception:
        draw.ellipse([x, y, x + size, y + size], fill=(20, 30, 60))
        return img, draw

@check_banned
@check_maintenance
async def jackpot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """``/jackpot`` — show jackpot status (any user).

    ``/jackpot <amount>`` — owner-only, sets the 7-day wager threshold.
    ``/jackpot rate <0..1>`` — owner-only, sets the accumulator rate.
    """
    user = update.effective_user
    if not user:
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)
    _jackpot_load()

    args = context.args or []

    # --- Owner controls ---
    if args and is_admin(user.id):
        first = args[0].lower()
        if first in ("rate",) and len(args) >= 2:
            try:
                new_rate = float(args[1])
            except ValueError:
                await update.message.reply_text("Usage: /jackpot rate <0..1>")
                return
            if new_rate < 0 or new_rate > 0.5:
                await update.message.reply_text(
                    "Rate must be between 0 and 0.5 (i.e. 0%–50%)."
                )
                return
            async with _jackpot_lock:
                _jackpot_state["accum_rate"] = new_rate
                _jackpot_mark_dirty()
                await asyncio.get_running_loop().run_in_executor(_save_executor, _jackpot_save_now)
            await update.message.reply_text(
                f"Jackpot accumulator rate set to {new_rate*100:.2f}% per bet.")
            return
        if first in ("draw",):
            await update.message.reply_text("Triggering jackpot draw…")
            try:
                rec = await _jackpot_run_draw(context.application)
                if rec is None:
                    await update.message.reply_text(
                        "Draw skipped — no eligible users or empty pool.")
                else:
                    await update.message.reply_text(
                        f"Drew jackpot: @{rec.get('username') or rec.get('user_id')} "
                        f"won ${rec.get('amount', 0):,.2f}."
                    )
            except Exception as e:
                await update.message.reply_text(f"Draw failed: {e}")
            return
        # Otherwise treat first arg as new threshold amount.
        try:
            new_thr = float(args[0].replace("$", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text(
                "Usage:\n"
                "  /jackpot              — view jackpot status\n"
                "  /jackpot <amount>     — (owner) set 7-day wager threshold\n"
                "  /jackpot rate <0..1>  — (owner) set accumulator rate\n"
                "  /jackpot draw         — (owner) trigger an immediate draw"
            )
            return
        if new_thr < 0:
            await update.message.reply_text("Threshold must be >= 0.")
            return
        async with _jackpot_lock:
            _jackpot_state["wager_threshold"] = new_thr
            _jackpot_mark_dirty()
            await asyncio.get_running_loop().run_in_executor(_save_executor, _jackpot_save_now)
        await update.message.reply_text(
            f"Jackpot wager threshold set to ${new_thr:,.2f} (7-day wager)."
        )
        return

    # --- Player view ---
    pool = float(_jackpot_state.get("pool", 0.0))
    threshold = float(_jackpot_state.get("wager_threshold", JACKPOT_DEFAULT_THRESHOLD_USD))
    user_w = _jackpot_user_7d_wager(user.id)
    last_winner = _jackpot_state.get("last_winner")

    now_utc = datetime.now(timezone.utc)
    next_dt = _jackpot_next_draw_dt(now_utc)
    secs = max(0, int((next_dt - now_utc).total_seconds()))

    bot_uname = await get_bot_username(context)
    profile_pic = await _get_cached_profile_picture(context, user.id)

    try:
        loop = asyncio.get_running_loop()
        img_buf = await loop.run_in_executor(
            _image_executor,
            generate_jackpot_status_image,
            pool, threshold, user_w, secs, last_winner,
            bot_uname, user.username, profile_pic,
        )
    except Exception as e:
        logging.error(f"Jackpot status render failed: {e}")
        img_buf = None

    rate_pct = float(_jackpot_state.get("accum_rate", JACKPOT_DEFAULT_ACCUM_RATE)) * 100
    eligible = user_w >= threshold
    elig_line = (
        "\u2705 You are eligible for tonight's draw."
        if eligible
        else f"Wager ${max(0.0, threshold - user_w):,.2f} more in the next 7 days to qualify."
    )
    last_line = ""
    if isinstance(last_winner, dict) and last_winner.get("username"):
        last_line = (
            f"\nLast winner: @{last_winner['username']} "
            f"won ${float(last_winner.get('amount', 0)):,.2f}"
        )
    caption = (
        f"\U0001F4B0 <b>Daily Jackpot</b>\n"
        f"Pool: <b>${pool:,.2f}</b>\n"
        f"Your 7-day wager: ${user_w:,.2f} / ${threshold:,.2f}\n"
        f"Each bet contributes {rate_pct:.2f}% to the pool.\n"
        f"Draw: 5:30 PM IST daily.\n"
        f"{elig_line}{last_line}"
    )

    try:
        if img_buf is not None:
            await update.message.reply_photo(
                photo=img_buf, caption=caption, parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(caption, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Failed to send jackpot status: {e}")

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('jackpot', jackpot_command, block=False))

