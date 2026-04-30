"""Auto-split from bot.py — core.dashboards."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def _paste_avatar_in_circle(base, draw, cx, cy, rx, ry, pic,
                            accent_rgba=(70, 200, 255, 255),
                            mesh_overlay=True):
    """Composite a circular Telegram avatar into ``base`` at the given
    centre + radii, with a neon ring and optional faint wireframe-mesh
    overlay so it still reads as the template's "wireframe head" cell.
    Falls back to drawing the wireframe head when ``pic`` is None or
    invalid.

    base: PIL.Image RGBA
    draw: ImageDraw of base (caller still has it; we just need it for
          the fallback path)
    """
    from PIL import Image as _Img, ImageDraw as _ImgDraw, ImageFilter as _ImgF
    import math as _math

    W, H = base.size
    # Render avatar (or fallback wireframe).
    if pic is not None:
        try:
            sw = max(2, rx * 2)
            sh = max(2, ry * 2)
            src = pic.convert("RGBA").resize((sw, sh), _Img.Resampling.LANCZOS)
            mask = _Img.new("L", (sw, sh), 0)
            _ImgDraw.Draw(mask).ellipse([0, 0, sw - 1, sh - 1], fill=255)
            base.paste(src, (cx - rx, cy - ry, cx - rx + sw, cy - ry + sh), mask)
            # Neon ring + soft outer glow.
            ring_layer = _Img.new("RGBA", (W, H), (0, 0, 0, 0))
            rd = _ImgDraw.Draw(ring_layer)
            rd.ellipse([cx - rx - 2, cy - ry - 2, cx + rx + 2, cy + ry + 2],
                       outline=accent_rgba, width=3)
            ring_layer = ring_layer.filter(_ImgF.GaussianBlur(radius=1.5))
            base.alpha_composite(ring_layer)
            draw_b = _ImgDraw.Draw(base)
            draw_b.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                           outline=accent_rgba, width=2)
            return True
        except Exception:
            pass

    # Fallback: original wireframe head.
    head_layer = _Img.new("RGBA", (W, H), (0, 0, 0, 0))
    hd = _ImgDraw.Draw(head_layer)
    hd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
               outline=accent_rgba, width=2)
    for ang in range(-80, 81, 14):
        rad = _math.radians(ang)
        x = cx + _math.sin(rad) * rx
        hd.line([(int(x), cy - ry), (int(x), cy + ry)],
                fill=(accent_rgba[0], accent_rgba[1], accent_rgba[2], 110),
                width=1)
    for ang in range(-70, 71, 14):
        rad = _math.radians(ang)
        yy = cy + _math.sin(rad) * ry
        hd.line([(cx - rx, int(yy)), (cx + rx, int(yy))],
                fill=(accent_rgba[0], accent_rgba[1], accent_rgba[2], 90),
                width=1)
    hd.ellipse([cx - 3, cy - 5, cx + 3, cy + 1],
               fill=(accent_rgba[0] + 100, accent_rgba[1] + 30,
                     min(255, accent_rgba[2] + 30), 255))
    head_layer = head_layer.filter(_ImgF.GaussianBlur(radius=0.5))
    base.alpha_composite(head_layer)
    return False

def create_circular_mask(image_size):
    """Create a circular mask for profile pictures."""
    mask = Image.new('L', image_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, image_size[0], image_size[1]), fill=255)
    return mask

async def generate_dashboard_image(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    OPTIMIZED: Collects all data asynchronously first, then runs CPU-bound
    PIL rendering in a ThreadPoolExecutor so the event loop is never blocked.
    """
    try:
        stats = user_stats.get(user_id, {})
        userinfo = stats.get('userinfo', {})
        balance = get_total_balance_usd(user_id)
        level_data = get_user_level(user_id)
        last_win = stats.get('last_win', 0.0)
        first_name = userinfo.get('first_name', 'User')
        username = userinfo.get('username', 'N/A')
        join_date = userinfo.get('join_date', 'N/A')

        # Cached bot username
        global _bot_username_cache
        if _bot_username_cache is None:
            bot_info = await context.bot.get_me()
            _bot_username_cache = bot_info.username
        bot_username = _bot_username_cache

        # Cached profile picture
        profile_pic = await _get_cached_profile_picture(context, user_id)

        # Format join date
        if join_date != 'N/A':
            try:
                date_obj = datetime.fromisoformat(join_date.replace('Z', '+00:00'))
                join_date = date_obj.strftime('%b %d, %Y')
            except (ValueError, AttributeError):
                join_date = join_date[:10] if len(join_date) > 10 else join_date

        # Render amounts in the user's chosen display currency (e.g.
        # \u20B9500 for INR) rather than hard-coded USD. We pick the
        # compact formatter so long lifetime numbers fit inside the card.
        bal_str = format_compact_for_user(user_id, balance)
        last_win_str = (
            format_compact_for_user(user_id, last_win) if last_win > 0 else "Play to win!"
        )

        text_data = {
            "name": first_name,
            "user_id": str(user_id),
            "username": f"@{username}",
            "bot_username": f"@{bot_username}",
            "level": level_data['name'],
            "balance": bal_str,
            "last_win": last_win_str,
            "member_since": join_date,
        }

        # Offload PIL to thread executor
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _image_executor,
            _render_dashboard_sync,
            text_data,
            profile_pic,
        )
        return result
    except Exception as e:
        logging.error(f"Error generating dashboard image for {user_id}: {e}")
        return None

def _render_dashboard_sync(text_data: dict, profile_pic):
    """
    Pure synchronous PIL rendering - NO disk I/O.
    Generates the entire dashboard programmatically.
    All monetary values displayed in USD ($).
    Runs in ThreadPoolExecutor so event loop is never blocked.

    text_data keys:
        name         - user's first name
        user_id      - user's Telegram ID (string)
        username     - @username
        bot_username - @BotUsername
        level        - level name e.g. "Bronze I"
        balance      - e.g. "$12.50"   <- always USD, always $ prefix
        last_win     - e.g. "$5.00" or "Play to win!"
        member_since - e.g. "Jan 15, 2025"
    """
    try:
        import random as _rand
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        from io import BytesIO

        W, H = 1000, 560
        BG_COLOR = (45, 10, 10)  # Dark maroon background

        img = Image.new("RGBA", (W, H), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # -- Subtle gradient vignette (dark edges) ----------------------------
        for radius in range(min(W, H) // 2, 0, -12):
            alpha = max(0, int(25 * (1.0 - radius / (min(W, H) / 2.0))))
            draw.ellipse(
                [W // 2 - radius, H // 2 - radius, W // 2 + radius, H // 2 + radius],
                outline=(60, 0, 0, alpha)
            )

        # -- Stars: deterministic pattern using fixed seed --------------------
        rng = _rand.Random(42)
        for _ in range(85):
            sx = rng.randint(5, W - 5)
            sy = rng.randint(5, H - 5)
            sr = rng.choice([1, 1, 1, 2, 2, 3])
            alpha_val = rng.randint(50, 180)
            draw.ellipse(
                [sx - sr, sy - sr, sx + sr, sy + sr],
                fill=(255, 255, 255, alpha_val)
            )

        # -- Font loader (tries bold.ttf from bot directory, falls back to default) -
        def _f(size):
            try:
                return ImageFont.truetype(DASHBOARD_FONT_PATH, size)
            except Exception:
                return ImageFont.load_default()

        # -- TOP RIGHT: Bot username & info -----------------------------------
        bot_uname = text_data.get("bot_username", "@CasinoBot").lstrip("@")
        bot_display = f"@{bot_uname}"
        f_bot = _f(26)
        bw = draw.textlength(bot_display, font=f_bot)
        draw.text((W - 22 - bw, 28), bot_display, fill=(255, 215, 0), font=f_bot)

        f_sub = _f(14)
        sub_text = "Telegram Casino"
        sw = draw.textlength(sub_text, font=f_sub)
        draw.text((W - 22 - sw, 62), sub_text, fill=(190, 190, 190), font=f_sub)

        member_text = f"Member since: {text_data.get('member_since', 'N/A')}"
        f_mem = _f(13)
        mw = draw.textlength(member_text, font=f_mem)
        draw.text((W - 22 - mw, 82), member_text, fill=(0, 210, 210), font=f_mem)

        # -- TOP LEFT: Avatar circle ------------------------------------------
        AV_X, AV_Y, AV_SIZE = 45, 45, 115
        if profile_pic:
            try:
                pf = profile_pic.resize((AV_SIZE, AV_SIZE), Image.Resampling.LANCZOS).convert("RGBA")
                mask = Image.new("L", (AV_SIZE, AV_SIZE), 0)
                ImageDraw.Draw(mask).ellipse([0, 0, AV_SIZE - 1, AV_SIZE - 1], fill=255)
                img.paste(pf, (AV_X, AV_Y), mask)
            except Exception:
                pass
        else:
            draw.ellipse(
                [AV_X, AV_Y, AV_X + AV_SIZE, AV_Y + AV_SIZE],
                fill=(70, 20, 20), outline=(255, 140, 0), width=2
            )
            initial = text_data.get("name", "U")[:1].upper()
            f_init = _f(50)
            iw = draw.textlength(initial, font=f_init)
            draw.text((AV_X + (AV_SIZE - iw) / 2, AV_Y + 22), initial, fill=(255, 255, 255), font=f_init)

        # Orange ring around avatar
        draw.ellipse(
            [AV_X - 4, AV_Y - 4, AV_X + AV_SIZE + 4, AV_Y + AV_SIZE + 4],
            outline=(255, 140, 0), width=3
        )

        # -- User name, @username, ID pill, level badge -----------------------
        TEXT_X = AV_X + AV_SIZE + 22
        draw.text((TEXT_X, 52), text_data.get("name", "User"), fill=(255, 255, 255), font=_f(30))
        draw.text((TEXT_X, 92), text_data.get("username", "@user"), fill=(170, 170, 170), font=_f(18))

        # User ID pill (dark background rounded rectangle)
        uid_str = str(text_data.get("user_id", ""))
        f_uid = _f(15)
        uid_w = int(draw.textlength(uid_str, font=f_uid)) + 18
        uid_y = 122
        draw.rounded_rectangle([TEXT_X, uid_y, TEXT_X + uid_w, uid_y + 24], radius=12,
                               fill=(35, 35, 45), outline=(100, 100, 120), width=1)
        draw.text((TEXT_X + 9, uid_y + 4), uid_str, fill=(190, 190, 190), font=f_uid)

        # Level badge (purple pill)
        level_str = text_data.get("level", "Novice")
        f_lv = _f(14)
        lv_w = int(draw.textlength(level_str, font=f_lv)) + 18
        lv_x = TEXT_X + uid_w + 10
        draw.rounded_rectangle([lv_x, uid_y, lv_x + lv_w, uid_y + 24], radius=12,
                               fill=(80, 15, 150), outline=(150, 50, 220), width=1)
        draw.text((lv_x + 9, uid_y + 4), level_str, fill=(215, 175, 255), font=f_lv)

        # -- "Welcome Back!" section ------------------------------------------
        f_wb = _f(28)
        wb = "🎉 Welcome Back!"
        wb_w = draw.textlength(wb, font=f_wb)
        draw.text(((W - wb_w) / 2, 190), wb, fill=(255, 215, 0), font=f_wb)

        # Gold separator line with center diamond
        sep_y = 228
        draw.line([(W // 2 - 210, sep_y), (W // 2 + 210, sep_y)], fill=(200, 170, 0, 130), width=1)
        draw.polygon(
            [(W // 2, sep_y - 5), (W // 2 + 6, sep_y), (W // 2, sep_y + 5), (W // 2 - 6, sep_y)],
            fill=(255, 215, 0)
        )

        # -- Three stat cards -------------------------------------------------
        CARD_Y = 248
        CARD_H = 105
        MARGIN = 30
        GAP = 14
        CARD_W = (W - 2 * MARGIN - 2 * GAP) // 3

        def draw_card(x, label, value, border_color, bg_color, value_color, icon=None, badge=None):
            # Card background
            draw.rounded_rectangle([x, CARD_Y, x + CARD_W, CARD_Y + CARD_H],
                                   radius=10, fill=bg_color, outline=border_color, width=2)
            # Label text
            f_lbl = _f(16)
            lbl_w = draw.textlength(label, font=f_lbl)
            draw.text((x + (CARD_W - lbl_w) / 2, CARD_Y + 10), label,
                      fill=(255, 255, 255), font=f_lbl)
            # Value text
            f_val = _f(24) if len(str(value)) > 8 else _f(26)
            val_w = draw.textlength(str(value), font=f_val)
            draw.text((x + (CARD_W - val_w) / 2, CARD_Y + 40), str(value),
                      fill=value_color, font=f_val)
            # Optional icon below value
            if icon:
                f_ico = _f(11)
                ico_w = draw.textlength(icon, font=f_ico)
                draw.text((x + (CARD_W - ico_w) / 2, CARD_Y + 78), icon,
                          fill=(180, 130, 255), font=f_ico)
            # Optional NEW badge in top-right corner of card
            if badge:
                f_bdg = _f(11)
                bdg_w = int(draw.textlength(badge, font=f_bdg)) + 10
                bdg_x = x + CARD_W - bdg_w - 6
                bdg_y = CARD_Y + 6
                draw.rounded_rectangle([bdg_x, bdg_y, bdg_x + bdg_w, bdg_y + 17],
                                       radius=4, fill=(190, 0, 75))
                draw.text((bdg_x + 5, bdg_y + 2), badge, fill=(255, 255, 255), font=f_bdg)

        # Card 1: Balance (green border).  bal_str already comes
        # pre-formatted in the user's display currency (e.g. "₹500.00",
        # "€20.00", "$12.50") from format_compact_for_user — do NOT
        # prepend an extra "$" here or it stacks two symbols
        # ("$₹500.00").
        bal_str = text_data.get("balance", "$0.00")
        draw_card(
            x=MARGIN,
            label="Your Balance",
            value=bal_str,
            border_color=(0, 190, 75),
            bg_color=(8, 30, 12),
            value_color=(0, 255, 90),
        )

        # Card 2: Last Win — same rule: render the pre-formatted value
        # as-is.  Only the "Play to win!" placeholder skips the symbol.
        lw_str = text_data.get("last_win", "Play to win!")
        draw_card(
            x=MARGIN + CARD_W + GAP,
            label="Last Win",
            value=lw_str,
            border_color=(210, 150, 0),
            bg_color=(30, 22, 5),
            value_color=(255, 195, 45),
        )

        # Card 3: Try Plinko (pink/magenta border, NEW badge, diamond icon)
        draw_card(
            x=MARGIN + 2 * (CARD_W + GAP),
            label="Try Plinko",
            value="💎",
            border_color=(210, 55, 155),
            bg_color=(30, 5, 22),
            value_color=(100, 175, 255),
            icon="Collect & win big!",
            badge="NEW!",
        )

        # -- Tagline ----------------------------------------------------------
        f_tag = _f(18)
        tag = '"The jackpot awaits!"'
        tw = draw.textlength(tag, font=f_tag)
        draw.text(((W - tw) / 2, 378), tag, fill=(175, 175, 195), font=f_tag)
        draw.line([(W // 2 - tw // 2, 402), (W // 2 + tw // 2, 402)],
                  fill=(90, 90, 130), width=1)

        # -- Footer -----------------------------------------------------------
        f_foot = _f(11)
        foot = "Play responsibly"
        fw = draw.textlength(foot, font=f_foot)
        draw.text(((W - fw) / 2, H - 26), foot, fill=(95, 70, 70), font=f_foot)

        # -- Save as JPEG -----------------------------------------------------
        output = BytesIO()
        img.convert("RGB").save(output, format="JPEG", quality=92)
        output.seek(0)
        return output
    except Exception as e:
        logging.error(f"PIL render error: {e}")
        return None

def get_display_name(internal_name):
    """Convert internal game type to display name."""
    clean = internal_name.replace("pvb_", "").replace("xdxw_", "").replace("_original", "").replace("_new", "").lower()
    return GAME_DISPLAY_NAMES.get(clean, internal_name.replace("_", " ").title())

async def generate_stats_image(user_id: int, context: ContextTypes.DEFAULT_TYPE, period='all_time'):
    """Generate stats template image with profile picture support."""
    try:
        stats = user_stats.get(user_id, {})
        userinfo = stats.get('userinfo', {})
        first_name = userinfo.get('first_name', 'User')
        username = userinfo.get('username', '')
        join_date = userinfo.get('join_date', 'N/A')

        global _bot_username_cache
        if _bot_username_cache is None:
            bot_info = await context.bot.get_me()
            _bot_username_cache = bot_info.username
        bot_username = _bot_username_cache

        # Fetch profile picture
        profile_pic = await _get_cached_profile_picture(context, user_id)

        # Format member since
        member_since = 'N/A'
        if join_date != 'N/A':
            try:
                date_obj = datetime.fromisoformat(join_date.replace('Z', '+00:00'))
                member_since = date_obj.strftime('%d %b %Y')
            except (ValueError, AttributeError):
                member_since = join_date[:10]

        # Calculate stats
        if period == '24h':
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=24)
            user_game_ids = stats.get("game_sessions", [])
            total_games = wins = losses = 0
            total_wagered = total_pnl = 0.0
            game_breakdown = {}
            biggest_win = 0.0
            biggest_win_game = ''

            for gid in user_game_ids:
                game = game_sessions.get(gid)
                if not game:
                    continue
                try:
                    ts = game.get("timestamp", "")
                    game_time = datetime.fromisoformat(ts.replace('Z', '+00:00')) if ts else None
                    if game_time and game_time >= cutoff:
                        total_games += 1
                        bet_amt = game.get("bet_amount", 0.0)
                        total_wagered += bet_amt
                        profit = game.get("profit", 0.0)
                        total_pnl += profit
                        gtype = game.get("game_type", "Unknown")
                        if gtype not in game_breakdown:
                            game_breakdown[gtype] = {"games": 0, "wins": 0, "wagered": 0.0, "pnl": 0.0}
                        game_breakdown[gtype]["games"] += 1
                        game_breakdown[gtype]["wagered"] += bet_amt
                        game_breakdown[gtype]["pnl"] += profit
                        if game.get("win") is True:
                            wins += 1
                            game_breakdown[gtype]["wins"] += 1
                            if profit > biggest_win:
                                biggest_win = profit
                                biggest_win_game = gtype
                        elif game.get("win") is False:
                            losses += 1
                except (ValueError, TypeError):
                    continue
            win_rate = (wins / total_games * 100) if total_games > 0 else 0
        else:
            # All-time stats - use game_sessions for complete data
            total_games = wins = losses = 0
            total_wagered = total_pnl = 0.0
            game_breakdown = {}
            biggest_win = 0.0
            biggest_win_game = ''

            # Use user's own game_sessions list for O(k) lookup instead of O(n) full scan
            user_game_ids = user_stats.get(user_id, {}).get("game_sessions", [])
            for gid in user_game_ids:
                game = game_sessions.get(gid)
                if not game:
                    continue
                try:
                    total_games += 1
                    bet_amt = game.get("bet_amount", 0.0)
                    total_wagered += bet_amt
                    profit = game.get("profit", 0.0)
                    total_pnl += profit
                    gtype = game.get("game_type", "unknown")
                    if gtype not in game_breakdown:
                        game_breakdown[gtype] = {"games": 0, "wins": 0, "wagered": 0.0, "pnl": 0.0}
                    game_breakdown[gtype]["games"] += 1
                    game_breakdown[gtype]["wagered"] += bet_amt
                    game_breakdown[gtype]["pnl"] += profit
                    if game.get("win") is True:
                        wins += 1
                        game_breakdown[gtype]["wins"] += 1
                        if profit > biggest_win:
                            biggest_win = profit
                            biggest_win_game = gtype
                    elif game.get("win") is False:
                        losses += 1
                except (ValueError, TypeError):
                    continue

            # Also sync with user_stats bets counters
            total_bets = stats.get('bets', {}).get('count', 0)
            if total_bets > 0:
                wins = stats.get('bets', {}).get('wins', 0)
                losses = stats.get('bets', {}).get('losses', 0)
                total_games = total_bets
                total_wagered = stats.get('bets', {}).get('amount', 0.0)
                total_pnl = stats.get('pnl', 0.0)
            win_rate = (wins / total_games * 100) if total_games > 0 else 0

        # Favorite game = most played (most games)
        fav_game = 'N/A'
        if game_breakdown:
            fav_game = max(game_breakdown.items(), key=lambda x: x[1]["games"])[0]
        avg_bet = (total_wagered / total_games) if total_games > 0 else 0
        total_bonuses = stats.get('rakeback_balance', 0.0)
        level_data = get_user_level(user_id)

        # PvP data
        pvp_wins = stats.get('bets', {}).get('pvp_wins', 0)
        pvp_entries = []
        if pvp_wins > 0:
            pvp_entries.append({"name": "Emoji PvP", "games": pvp_wins, "pnl": f"-${total_pnl * 0.1:.2f}"})

        sorted_games = sorted(game_breakdown.items(), key=lambda x: x[1]["games"], reverse=True)[:8]
        game_list = []
        for gname, gdata in sorted_games:
            ggames = gdata["games"]
            gwr = (gdata["wins"] / ggames * 100) if ggames > 0 else 0
            gpnl = gdata["pnl"]
            display_name = get_display_name(gname)
            # Pre-format pnl in the viewer's display currency; keep raw
            # float too so the renderer knows whether it's positive.
            g_sign = "+" if gpnl >= 0 else "-"
            g_str = f"{g_sign}{format_compact_for_user(user_id, abs(gpnl))}"
            game_list.append({
                "name": display_name,
                "games": ggames,
                "wr": gwr,
                "pnl": gpnl,
                "pnl_str": g_str,
                "pnl_positive": gpnl >= 0,
            })

        # Calculate rank from ALL users by wagered amount.
        # PERFORMANCE: Previously this iterated every user_stats entry and
        # did an O(N log N) sort on every single dashboard view. At 5000
        # users that's tens of megabytes of dict iteration + a sort per
        # stats tap — a real CPU stall on the event loop. We now maintain
        # a ranking cache recomputed at most every 60 seconds and shared
        # across every user. Worst-case staleness: one minute, which is
        # fine for a personal rank readout.
        user_rank = _get_cached_wagered_rank(user_id)
        rank_str = f"#{user_rank}" if user_rank else "#---"

        # Pre-format every monetary field in the user's DISPLAY
        # currency (compact). The renderer prefers the *_str keys
        # and falls back to USD formatting for backwards compat.
        _fmt = lambda amt: format_compact_for_user(user_id, amt)
        pnl_sign = "+" if total_pnl >= 0 else ""

        text_data = {
            "first_name": first_name,
            "username": f"@{username}" if username else "@user",
            "user_id": str(user_id),
            "level": level_data['name'],
            "rank": rank_str,
            "member_since": member_since,
            "bot_username": bot_username,
            "period_label": "30d",
            "total_games": total_games,
            "total_wagered": total_wagered,
            "total_wagered_str": _fmt(total_wagered),
            "total_pnl": total_pnl,
            "total_pnl_str": f"{pnl_sign}{_fmt(total_pnl)}",
            "pnl_positive": total_pnl >= 0,
            "win_rate": win_rate,
            "avg_bet": avg_bet,
            "avg_bet_str": _fmt(avg_bet),
            "biggest_win": biggest_win,
            "biggest_win_str": f"+{_fmt(biggest_win)}",
            "biggest_win_game": biggest_win_game,
            "total_bonuses": total_bonuses,
            "total_bonuses_str": _fmt(total_bonuses),
            "fav_game": fav_game,
        }

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _image_executor,
            _render_stats_sync,
            text_data,
            game_list,
            pvp_entries,
            profile_pic,
        )
        return result
    except Exception as e:
        logging.error(f"Error generating stats image: {e}")
        return None

def _render_stats_sync(text_data, game_list, pvp_entries, profile_pic_data):
    """Render stats image — circuit-board / wireframe-head design.

    Mirrors ``example_designs/stats_pil_image_design_template.png``.
    Layout (rough):
      - Header: bot username centered + "TELEGRAM CASINO • PLAYER STATS" sub.
        Top-right: bot username + "Since <date>".
      - Wireframe head avatar in the top-left (geometric mesh).
      - Glass-effect "name card": first name large + @username + ID.
      - Right of name card: small badge with rank "#N" + circle avatar +
        level pill ("Bronze I" / "Silver II" / etc.).
      - 4×2 grid of colored stat tiles (games, wagered, win rate, P&L /
        avg bet, biggest win, fav game, bonuses) — each tile has a thin
        coloured border that matches the metric type.
      - "GAME BREAKDOWN" table with diamond bullets per row, P&L coloured.
      - Decorative circuit-board lines on the left/right edges + bottom.
      - Footer: "Play Responsibly • Gamble with Control" centered, bot
        username + diamond glyph in the bottom-right.
    """
    try:
        W, H = 1060, 980
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # ── PALETTE ──────────────────────────────────────────────
        C_BG_TOP   = (3,  6,  22)
        C_BG_MID   = (10, 10, 36)
        C_BG_BOT   = (28, 14, 50)
        C_HEADER   = (8,  16, 40)
        C_CARD     = (14, 22, 48)
        C_CARD_ALT = (10, 18, 40)
        C_BORDER   = (28, 56, 110)
        C_WHITE    = (235, 240, 255)
        C_MUTED    = (130, 145, 180)
        C_BLUE     = (90, 200, 255)
        C_BLUE_DIM = (35, 110, 200)
        C_GOLD     = (255, 200, 80)
        C_GOLD_DIM = (170, 130, 30)
        C_GREEN    = (80, 235, 140)
        C_RED      = (255, 90, 100)
        C_PURPLE   = (180, 110, 255)
        C_GRAY     = (120, 130, 160)
        C_CIRCUIT  = (40, 70, 130)

        # ── FONTS ────────────────────────────────────────────────
        def _tf(size):
            try:
                return ImageFont.truetype(DASHBOARD_FONT_PATH, size)
            except Exception:
                return ImageFont.load_default()

        fHero  = _tf(36)
        fSub   = _tf(13)
        fName  = _tf(46)
        fH3    = _tf(20)
        fBody  = _tf(16)
        fSmall = _tf(13)
        fTiny  = _tf(11)
        fTile  = _tf(28)
        fTileLb= _tf(12)
        fLevel = _tf(18)
        fRank  = _tf(20)

        # ── BACKGROUND: navy → faint purple gradient ─────────────
        for yy in range(H):
            t = yy / H
            if t < 0.55:
                u = t / 0.55
                r = int(C_BG_TOP[0] + u * (C_BG_MID[0] - C_BG_TOP[0]))
                g = int(C_BG_TOP[1] + u * (C_BG_MID[1] - C_BG_TOP[1]))
                b = int(C_BG_TOP[2] + u * (C_BG_MID[2] - C_BG_TOP[2]))
            else:
                u = (t - 0.55) / 0.45
                r = int(C_BG_MID[0] + u * (C_BG_BOT[0] - C_BG_MID[0]))
                g = int(C_BG_MID[1] + u * (C_BG_BOT[1] - C_BG_MID[1]))
                b = int(C_BG_MID[2] + u * (C_BG_BOT[2] - C_BG_MID[2]))
            draw.line([(0, yy), (W, yy)], fill=(r, g, b))

        # Decorative circuit-board lines on left edge + bottom.
        _rng = random.Random(42)
        # Bottom right grid (perspective lines).
        for i in range(20):
            yline = H - 280 + i * 14
            draw.line([(W // 2 - i * 22, yline), (W - 30, yline)],
                      fill=(40, 50, 100), width=1)
        for i in range(18):
            x0 = int(W / 2 + i * (W / 2 - 30) / 18)
            draw.line([(x0, H - 280), (x0 + i * 18, H - 30)],
                      fill=(40, 50, 100), width=1)
        # Left edge circuit lines.
        for _ in range(24):
            x0 = _rng.randint(8, 90)
            y0 = _rng.randint(280, H - 200)
            seg = _rng.randint(50, 130)
            draw.line([(x0, y0), (x0 + seg, y0)], fill=C_CIRCUIT, width=1)
            draw.line([(x0 + seg, y0), (x0 + seg, y0 + 18)], fill=C_CIRCUIT, width=1)
            draw.ellipse([x0 + seg - 3, y0 + 16, x0 + seg + 3, y0 + 22], fill=C_BLUE_DIM)
        # Right edge circuit lines.
        for _ in range(16):
            x0 = _rng.randint(W - 130, W - 30)
            y0 = _rng.randint(80, 230)
            seg = _rng.randint(40, 90)
            draw.line([(x0, y0), (x0 - seg, y0)], fill=C_CIRCUIT, width=1)
            draw.line([(x0 - seg, y0), (x0 - seg, y0 + 14)], fill=C_CIRCUIT, width=1)
            draw.ellipse([x0 - seg - 3, y0 + 12, x0 - seg + 3, y0 + 18], fill=C_BLUE_DIM)
        # Faint star sparkle.
        for _ in range(80):
            sx, sy = _rng.randint(0, W), _rng.randint(0, H)
            br = _rng.randint(40, 130)
            draw.ellipse([sx - 1, sy - 1, sx + 1, sy + 1], fill=(br, br, br + 20))

        # ── HEADER STRIP ─────────────────────────────────────────
        draw.rectangle([0, 0, W, 90], fill=C_HEADER)
        # Bot username centered.
        bot_lbl = f"@{text_data['bot_username']}"
        bw = draw.textlength(bot_lbl, font=fHero)
        draw.text(((W - bw) / 2, 12), bot_lbl, fill=C_WHITE, font=fHero)
        # Subtitle.
        sub = "TELEGRAM CASINO  •  PLAYER STATS"
        sw = draw.textlength(sub, font=fSub)
        draw.text(((W - sw) / 2, 58), sub, fill=C_MUTED, font=fSub)
        # Top-right.
        rt_lbl = f"@{text_data['bot_username']}"
        rw = draw.textlength(rt_lbl, font=fSmall)
        draw.text((W - rw - 22, 18), rt_lbl, fill=C_BLUE, font=fSmall)
        ms = f"Since {text_data['member_since']}"
        msw = draw.textlength(ms, font=fTiny)
        draw.text((W - msw - 22, 44), ms, fill=C_MUTED, font=fTiny)
        # Hairline under header.
        draw.line([(0, 92), (W, 92)], fill=C_GOLD_DIM, width=1)

        # ── PROFILE AVATAR (top-left) ────────────────────────────
        # Composite the player's Telegram avatar into a circular cell
        # with a neon ring + faint mesh overlay so it still reads as
        # the template's "wireframe head" position. Falls back to the
        # wireframe head if no profile pic is available.
        head_cx, head_cy = 110, 165
        head_rx, head_ry = 80, 100
        _paste_avatar_in_circle(
            img, draw, head_cx, head_cy, head_rx, head_ry,
            profile_pic_data, accent_rgba=(70, 200, 255, 220),
        )
        draw = ImageDraw.Draw(img)

        # ── NAME CARD (centre, glass blue glow) ──────────────────
        NC_X0 = 220
        NC_X1 = W - 250
        NC_Y0 = 110
        NC_Y1 = 226
        # Outer glow.
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gd.rounded_rectangle([NC_X0 - 6, NC_Y0 - 6, NC_X1 + 6, NC_Y1 + 6],
                             radius=22, outline=(70, 200, 255, 110), width=4)
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=4))
        img.alpha_composite(glow_layer)
        # Card.
        draw.rounded_rectangle([NC_X0, NC_Y0, NC_X1, NC_Y1], radius=18,
                               fill=(10, 22, 50), outline=C_BLUE, width=2)
        # First name.
        name_str = (text_data.get("first_name", "Player") or "Player")[:18] + ".."
        if len(text_data.get("first_name") or "") <= 16:
            name_str = (text_data.get("first_name") or "Player")[:18]
        draw.text((NC_X0 + 30, NC_Y0 + 14), name_str, fill=C_WHITE, font=fName)
        # Username + ID.
        uname = text_data.get("username", "")
        draw.text((NC_X0 + 32, NC_Y0 + 70), uname, fill=C_MUTED, font=fSmall)
        uid_str = f"ID: {text_data.get('user_id', '')}"
        draw.text((NC_X0 + 32, NC_Y0 + 90), uid_str, fill=(85, 100, 140), font=fTiny)

        # ── RANK / LEVEL CARD (right of name card) ───────────────
        RC_X0 = W - 230
        RC_X1 = W - 28
        RC_Y0 = 110
        RC_Y1 = 226
        draw.rounded_rectangle([RC_X0, RC_Y0, RC_X1, RC_Y1], radius=18,
                               fill=(20, 14, 38), outline=C_PURPLE, width=2)
        # Rank pill (top-left of card).
        rk_pill_w, rk_pill_h = 60, 30
        rkx0 = RC_X0 + 18
        rky0 = RC_Y0 + 18
        draw.rounded_rectangle([rkx0, rky0, rkx0 + rk_pill_w, rky0 + rk_pill_h],
                               radius=12, fill=(48, 28, 14), outline=C_GOLD, width=2)
        rk_str = text_data.get("rank", "#---")
        rkw = draw.textlength(rk_str, font=fRank)
        draw.text((rkx0 + (rk_pill_w - rkw) / 2, rky0 + 4), rk_str, fill=C_GOLD, font=fRank)
        # Avatar (top-right of card).
        av_r = 22
        av_cx = RC_X1 - 30
        av_cy = rky0 + rk_pill_h // 2
        if profile_pic_data and isinstance(profile_pic_data, Image.Image):
            try:
                sz = av_r * 2
                src = profile_pic_data.convert("RGBA").resize((sz, sz), Image.Resampling.LANCZOS)
                mask = Image.new("L", (sz, sz), 0)
                ImageDraw.Draw(mask).ellipse([0, 0, sz - 1, sz - 1], fill=255)
                img.paste(src, (av_cx - av_r, av_cy - av_r), mask)
                draw.ellipse([av_cx - av_r, av_cy - av_r, av_cx + av_r, av_cy + av_r],
                             outline=C_PURPLE, width=2)
            except Exception:
                draw.ellipse([av_cx - av_r, av_cy - av_r, av_cx + av_r, av_cy + av_r],
                             fill=(40, 24, 60), outline=C_PURPLE, width=2)
        else:
            draw.ellipse([av_cx - av_r, av_cy - av_r, av_cx + av_r, av_cy + av_r],
                         fill=(40, 24, 60), outline=C_PURPLE, width=2)
        # Level pill (centered below).
        lvl_str = text_data.get("level", "Bronze I")
        lvw = draw.textlength(lvl_str, font=fLevel)
        lpw = max(int(lvw + 36), 130)
        lph = 38
        lpx = RC_X0 + (RC_X1 - RC_X0 - lpw) // 2
        lpy = RC_Y0 + 64
        draw.rounded_rectangle([lpx, lpy, lpx + lpw, lpy + lph], radius=14,
                               fill=(40, 18, 60), outline=C_PURPLE, width=2)
        draw.text((lpx + (lpw - lvw) / 2, lpy + 8), lvl_str, fill=C_PURPLE, font=fLevel)

        # ── 4×2 STAT TILE GRID ───────────────────────────────────
        TILE_Y0 = 250
        TILE_GAP = 14
        TILE_W = (W - 28 - TILE_GAP * 3) // 4
        TILE_H = 96

        def _draw_tile(col, row, value, label, border_color, value_color, icon_glyph=None):
            x0 = 14 + col * (TILE_W + TILE_GAP)
            y0 = TILE_Y0 + row * (TILE_H + TILE_GAP)
            x1 = x0 + TILE_W
            y1 = y0 + TILE_H
            draw.rounded_rectangle([x0, y0, x1, y1], radius=14,
                                   fill=(14, 24, 50), outline=border_color, width=2)
            # Subtle outer glow.
            gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gld = ImageDraw.Draw(gl)
            gld.rounded_rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2],
                                  radius=16,
                                  outline=(border_color[0], border_color[1], border_color[2], 80),
                                  width=2)
            gl = gl.filter(ImageFilter.GaussianBlur(radius=3))
            img.alpha_composite(gl)
            # Icon circle on the left.
            ic_cx = x0 + 32
            ic_cy = y0 + TILE_H // 2 - 4
            draw.ellipse([ic_cx - 18, ic_cy - 18, ic_cx + 18, ic_cy + 18],
                         fill=(8, 16, 36), outline=border_color, width=2)
            if icon_glyph:
                gw = draw.textlength(icon_glyph, font=fH3)
                draw.text((ic_cx - gw / 2, ic_cy - 12), icon_glyph,
                          fill=border_color, font=fH3)
            # Value (centered horizontally in remaining space).
            val_str = str(value)
            vw = draw.textlength(val_str, font=fTile)
            val_cx = (x0 + 60 + x1) // 2
            draw.text((val_cx - vw / 2, y0 + 18), val_str, fill=value_color, font=fTile)
            # Label below.
            lbw = draw.textlength(label, font=fTileLb)
            draw.text((val_cx - lbw / 2, y0 + 60), label, fill=C_MUTED, font=fTileLb)

        # Row 1 - prefer pre-formatted display-currency strings; fall
        # back to USD if they weren't provided (old callers).
        total_pnl = text_data.get("total_pnl", 0.0)
        pnl_pos = text_data.get("pnl_positive", total_pnl >= 0)
        wagered_str = text_data.get("total_wagered_str") or f"${text_data.get('total_wagered', 0):,.2f}"
        pnl_str = text_data.get("total_pnl_str") or f"{'+' if pnl_pos else ''}${total_pnl:,.2f}"
        avg_str = text_data.get("avg_bet_str") or f"${text_data.get('avg_bet', 0):,.2f}"
        big_str = text_data.get("biggest_win_str") or f"+${text_data.get('biggest_win', 0.0):,.2f}"
        bonus_str = text_data.get("total_bonuses_str") or f"${text_data.get('total_bonuses', 0.0) or 0.0:,.2f}"

        _draw_tile(0, 0, text_data.get("total_games", 0), "GAMES PLAYED",
                   C_GRAY, C_WHITE, "⌬")
        _draw_tile(1, 0, wagered_str, "TOTAL WAGERED",
                   C_BLUE, C_BLUE, "$")
        _draw_tile(2, 0, f"{text_data.get('win_rate', 0):.1f}%", "WIN RATE",
                   C_GOLD, C_GOLD, "◷")
        _draw_tile(3, 0, pnl_str, "NET P&L",
                   C_GREEN if pnl_pos else C_RED,
                   C_GREEN if pnl_pos else C_RED, "▣")
        # Row 2
        _draw_tile(0, 1, avg_str, "AVG BET",
                   C_BLUE, C_BLUE, "✎")
        _draw_tile(1, 1, big_str, "BIGGEST WIN",
                   C_GOLD, C_GOLD, "♛")
        fav = text_data.get("fav_game", "—") or "—"
        _draw_tile(2, 1, str(fav)[:14], "FAV GAME",
                   C_GRAY, C_WHITE, "♦")
        _draw_tile(3, 1, bonus_str, "BONUSES",
                   C_PURPLE, C_PURPLE, "🎁")

        # ── GAME BREAKDOWN TABLE ─────────────────────────────────
        BR_Y0 = TILE_Y0 + 2 * (TILE_H + TILE_GAP) + 22
        # Section header.
        section_lbl = "GAME  BREAKDOWN"
        slw = draw.textlength(section_lbl, font=fSmall)
        # Hairline + label centered overlay.
        draw.line([(20, BR_Y0), (W - 20, BR_Y0)], fill=C_BORDER, width=1)
        # Erase a slot for the label.
        draw.rectangle([(W - slw) / 2 - 12, BR_Y0 - 9, (W + slw) / 2 + 12, BR_Y0 + 9],
                       fill=C_BG_MID)
        draw.text(((W - slw) / 2, BR_Y0 - 8), section_lbl, fill=C_BLUE, font=fSmall)
        # Table column headers.
        BR_Y0 += 14
        col_game = 30
        col_played = int(W * 0.45)
        col_wr = int(W * 0.62)
        col_pnl = W - 40
        draw.text((col_game, BR_Y0), "GAME", fill=C_MUTED, font=fTiny)
        draw.text((col_played, BR_Y0), "PLAYED", fill=C_MUTED, font=fTiny)
        draw.text((col_wr, BR_Y0), "WIN RATE", fill=C_MUTED, font=fTiny)
        draw.text((col_pnl, BR_Y0), "P&L", fill=C_MUTED, font=fTiny, anchor="ra")
        BR_Y0 += 18
        # Rows.
        rows = (game_list or [])[:6]
        if not rows:
            draw.text((col_game, BR_Y0 + 8), "No games played yet",
                      fill=C_MUTED, font=fSmall)
            BR_Y0 += 36
        else:
            for entry in rows:
                draw.line([(20, BR_Y0), (W - 20, BR_Y0)], fill=(20, 30, 60), width=1)
                # Diamond bullet.
                bx = col_game - 12
                by = BR_Y0 + 18
                draw.polygon([(bx, by - 5), (bx + 5, by), (bx, by + 5), (bx - 5, by)],
                             fill=C_GOLD)
                # Game name.
                gname = entry.get("name", "")
                draw.text((col_game + 2, BR_Y0 + 12), str(gname)[:24],
                          fill=C_WHITE, font=fBody)
                # Played count.
                draw.text((col_played, BR_Y0 + 12), str(entry.get("games", 0)),
                          fill=C_WHITE, font=fBody)
                # Win rate (red < 50%, green ≥ 50%).
                wr = entry.get("wr", 0.0)
                wr_color = C_GREEN if wr >= 50 else C_RED
                draw.text((col_wr, BR_Y0 + 12), f"{wr:.1f}%",
                          fill=wr_color, font=fBody)
                # P&L right-aligned (prefer pre-formatted display-currency str).
                pnl = entry.get("pnl", 0.0)
                pnl_color = C_GREEN if pnl >= 0 else C_RED
                pnl_str = entry.get("pnl_str") or f"{'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}"
                draw.text((col_pnl, BR_Y0 + 12), pnl_str,
                          fill=pnl_color, font=fBody, anchor="ra")
                BR_Y0 += 36
            draw.line([(20, BR_Y0), (W - 20, BR_Y0)], fill=(20, 30, 60), width=1)

        # ── FOOTER ──────────────────────────────────────────────
        ftr_y = H - 30
        draw.line([(0, ftr_y - 14), (W, ftr_y - 14)], fill=C_BORDER, width=1)
        ftr = "Play Responsibly  •  Gamble with Control"
        fw = draw.textlength(ftr, font=fSmall)
        draw.text(((W - fw) / 2, ftr_y - 8), ftr, fill=C_MUTED, font=fSmall)
        # Diamond + bot username right.
        wm = f"@{text_data['bot_username']}"
        wmw = draw.textlength(wm, font=fSmall)
        draw.text((W - wmw - 30, ftr_y - 8), wm, fill=C_BLUE, font=fSmall)
        dx, dy = W - 22, ftr_y - 4
        draw.polygon([(dx, dy - 8), (dx + 8, dy), (dx, dy + 8), (dx - 8, dy)],
                     fill=C_BLUE)

        # ── SAVE ────────────────────────────────────────────────
        buf = BytesIO()
        img = img.convert("RGB")
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf
    except Exception as e:
        logging.error(f"Error rendering stats image: {e}")
        import traceback
        traceback.print_exc()
        return None


def _game_template_background(W=700, H=1050):
    """Create neon bluish-black background with stars."""
    img = Image.new("RGB", (W, H), (8, 14, 28))
    draw = ImageDraw.Draw(img)
    # Subtle gradient overlay
    for y in range(H):
        shade = int(8 + (y / H) * 6)
        draw.line([(0, y), (W, y)], fill=(shade, 14 + int((y/H)*8), 28 + int((y/H)*12)))
    # Stars
    rng = random.Random(99)
    for _ in range(50):
        sx = rng.randint(0, W)
        sy = rng.randint(0, H)
        sr = rng.randint(1, 2)
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(100, 180, 255, rng.randint(60, 180)))
    return img, draw

def _render_mines_sync(username, bet_amount, num_mines, picks, mines, won, multiplier, winnings, game_id, safe_count):
    """Render Mines result template showing the 5x5 grid with revealed mines and gems."""
    try:
        W, H = 700, 1050
        img, draw = _game_template_background(W, H)

        try:
            f_title = ImageFont.truetype("bold.ttf", 28)
            f_user = ImageFont.truetype("bold.ttf", 18)
            f_stat = ImageFont.truetype("bold.ttf", 20)
            f_small = ImageFont.truetype("bold.ttf", 12)
            f_result = ImageFont.truetype("bold.ttf", 22)
            f_id = ImageFont.truetype("bold.ttf", 11)
            f_grid_lbl = ImageFont.truetype("bold.ttf", 10)
        except Exception:
            f_title = f_user = f_stat = f_small = f_result = f_id = f_grid_lbl = ImageFont.load_default()

        y = 18

        # Bot username top right
        bot_un = "@playcsino"
        bw = draw.textlength(bot_un, font=f_user)
        draw.text((W - 15 - bw, y), bot_un, fill=(100, 180, 255), font=f_user)
        y += 30

        # Game title
        title = "MINES RESULT"
        tw = draw.textlength(title, font=f_title)
        draw.text(((W - tw) // 2, y), title, fill=(255, 255, 255), font=f_title)
        y += 35

        # Username
        un_bbox = draw.textbbox((0, 0), username, font=f_user)
        un_w = un_bbox[2] - un_bbox[0]
        draw.text(((W - un_w) // 2, y), username, fill=(100, 180, 255), font=f_user)
        y += 30

        # Result banner
        if won:
            banner_color = (0, 60, 40)
            banner_text = f"YOU WON ${winnings:.2f}!"
            banner_fill = (0, 255, 120)
        else:
            banner_color = (60, 10, 10)
            banner_text = "YOU HIT A MINE!"
            banner_fill = (255, 80, 80)

        bw2 = draw.textlength(banner_text, font=f_result)
        draw.rounded_rectangle([(W - bw2 - 40) // 2, y, (W + bw2 + 40) // 2, y + 40], radius=10, fill=banner_color)
        draw.text(((W - bw2) // 2, y + 6), banner_text, fill=banner_fill, font=f_result)
        y += 55

        # Stats row
        stat_y = y
        stats = [
            (f"${bet_amount:.2f}", "BET"),
            (f"{num_mines}", "MINES"),
            (f"{safe_count}", "SAFE PICKS"),
            (f"{multiplier:.2f}x", "MULTIPLIER"),
        ]
        stat_w = 155
        stat_h = 60
        stat_gap = 10
        stat_start = (W - (stat_w * 4 + stat_gap * 3)) // 2
        for i, (val, lbl) in enumerate(stats):
            sx = stat_start + i * (stat_w + stat_gap)
            draw.rounded_rectangle([sx, stat_y, sx + stat_w, stat_y + stat_h], radius=8, fill=(12, 25, 45), outline=(40, 80, 120), width=1)
            draw.text((sx + 10, stat_y + 6), val, fill=(255, 255, 255), font=f_stat)
            draw.text((sx + 10, stat_y + 36), lbl, fill=(100, 160, 200), font=f_grid_lbl)
        y = stat_y + stat_h + 20

        # 5x5 Grid
        grid_size = 5
        cell_size = 90
        grid_gap = 6
        grid_total = grid_size * cell_size + (grid_size - 1) * grid_gap
        grid_x = (W - grid_total) // 2
        grid_y = y

        for row in range(grid_size):
            for col in range(grid_size):
                cell_idx = row * grid_size + col
                cx = grid_x + col * (cell_size + grid_gap)
                cy = grid_y + row * (cell_size + grid_gap)

                # Determine cell state
                is_mine = cell_idx in mines
                is_pick = cell_idx in picks

                if is_pick and is_mine:
                    # Hit mine (red X)
                    bg_color = (80, 15, 15)
                    border = (255, 50, 50)
                    symbol = "💥"
                elif is_pick:
                    # Safe pick (green check)
                    bg_color = (10, 50, 20)
                    border = (50, 200, 80)
                    symbol = "💎"
                elif is_mine:
                    # Revealed mine (orange warning)
                    bg_color = (40, 20, 10)
                    border = (200, 150, 50)
                    symbol = "💣"
                else:
                    # Unrevealed safe
                    bg_color = (10, 18, 35)
                    border = (30, 60, 100)
                    symbol = ""

                draw.rounded_rectangle([cx, cy, cx + cell_size, cy + cell_size], radius=8, fill=bg_color, outline=border, width=2)
                if symbol:
                    try:
                        emoji_font = ImageFont.truetype("NotoColorEmoji.ttf", 36)
                    except Exception:
                        emoji_font = ImageFont.load_default()
                    sym_bbox = draw.textbbox((0, 0), symbol, font=emoji_font)
                    sym_w = sym_bbox[2] - sym_bbox[0]
                    sym_h = sym_bbox[3] - sym_bbox[1]
                    draw.text((cx + (cell_size - sym_w) // 2, cy + (cell_size - sym_h) // 2), symbol, font=emoji_font)

        y = grid_y + grid_total + 25

        # Game ID
        gid_text = f"Game ID: {game_id}"
        gid_w = draw.textlength(gid_text, font=f_id)
        draw.text(((W - gid_w) // 2, y), gid_text, fill=(80, 120, 160), font=f_id)

        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output
    except Exception as e:
        logging.error(f"Mines template render error: {e}")
        return None

def _render_tower_sync(username, bet_amount, difficulty, current_floor, tower_config, selected_tiles, won, multiplier, winnings, game_id):
    """Render Tower result template showing the tower grid with snakes revealed."""
    try:
        W, H = 700, 1050
        img, draw = _game_template_background(W, H)

        try:
            f_title = ImageFont.truetype("bold.ttf", 28)
            f_user = ImageFont.truetype("bold.ttf", 18)
            f_stat = ImageFont.truetype("bold.ttf", 20)
            f_small = ImageFont.truetype("bold.ttf", 12)
            f_result = ImageFont.truetype("bold.ttf", 22)
            f_id = ImageFont.truetype("bold.ttf", 11)
            f_floor = ImageFont.truetype("bold.ttf", 14)
            f_grid_lbl = ImageFont.truetype("bold.ttf", 10)
        except Exception:
            f_title = f_user = f_stat = f_small = f_result = f_id = f_floor = f_grid_lbl = ImageFont.load_default()

        diff_name = {'easy': 'Easy', 'medium': 'Medium', 'hard': 'Hard'}.get(difficulty, difficulty.title())
        tiles_per_floor = {'easy': 4, 'medium': 3, 'hard': 2}.get(difficulty, 3)

        y = 18

        # Bot username
        bot_un = "@playcsino"
        bw = draw.textlength(bot_un, font=f_user)
        draw.text((W - 15 - bw, y), bot_un, fill=(100, 180, 255), font=f_user)
        y += 30

        # Title
        title = f"TOWER - {diff_name}"
        tw = draw.textlength(title, font=f_title)
        draw.text(((W - tw) // 2, y), title, fill=(255, 255, 255), font=f_title)
        y += 35

        # Username
        un_bbox = draw.textbbox((0, 0), username, font=f_user)
        un_w = un_bbox[2] - un_bbox[0]
        draw.text(((W - un_w) // 2, y), username, fill=(100, 180, 255), font=f_user)
        y += 30

        # Result banner
        if won:
            banner_color = (0, 60, 40)
            banner_text = f"TOWER CONQUERED! +${winnings:.2f}"
            banner_fill = (0, 255, 120)
        else:
            banner_color = (60, 10, 10)
            banner_text = "TOWER COLLAPSED!"
            banner_fill = (255, 80, 80)
        bw2 = draw.textlength(banner_text, font=f_result)
        draw.rounded_rectangle([(W - bw2 - 40) // 2, y, (W + bw2 + 40) // 2, y + 40], radius=10, fill=banner_color)
        draw.text(((W - bw2) // 2, y + 6), banner_text, fill=banner_fill, font=f_result)
        y += 55

        # Stats
        stat_y = y
        stats = [
            (f"${bet_amount:.2f}", "BET"),
            (f"{current_floor}/9", "FLOORS"),
            (f"{multiplier:.2f}x" if multiplier > 0 else "0x", "MULTIPLIER"),
        ]
        stat_w = 190
        stat_h = 60
        stat_gap = 10
        stat_start = (W - (stat_w * 3 + stat_gap * 2)) // 2
        for i, (val, lbl) in enumerate(stats):
            sx = stat_start + i * (stat_w + stat_gap)
            draw.rounded_rectangle([sx, stat_y, sx + stat_w, stat_y + stat_h], radius=8, fill=(12, 25, 45), outline=(40, 80, 120), width=1)
            draw.text((sx + 10, stat_y + 6), val, fill=(255, 255, 255), font=f_stat)
            draw.text((sx + 10, stat_y + 36), lbl, fill=(100, 160, 200), font=f_grid_lbl)
        y = stat_y + stat_h + 20

        # Tower grid (9 floors, bottom to top)
        floor_h = 55
        tile_w = 80
        tile_h = 40
        tile_gap = 6
        grid_total_h = 9 * (floor_h + 8)
        grid_start_y = y
        grid_total_w = tiles_per_floor * tile_w + (tiles_per_floor - 1) * tile_gap
        grid_start_x = (W - grid_total_w) // 2

        for floor in range(8, -1, -1):  # Floor 8 at top, floor 0 at bottom
            fy = grid_start_y + (8 - floor) * (floor_h + 8)
            snake_pos = tower_config[floor] if floor < len(tower_config) else -1

            # Floor label
            draw.text((15, fy + 15), f"F{floor + 1}", fill=(100, 160, 200), font=f_floor)

            for tile in range(tiles_per_floor):
                tx = grid_start_x + tile * (tile_w + tile_gap)
                is_snake = (tile == snake_pos)
                is_selected = False
                # Check if this tile was selected on this floor
                # selected_tiles stores floor -> tile mapping
                if floor < len(selected_tiles):
                    is_selected = (selected_tiles[floor] == tile)

                if is_selected and is_snake:
                    bg = (80, 15, 15)
                    border = (255, 50, 50)
                    sym = "💀"
                elif is_selected:
                    bg = (10, 50, 20)
                    border = (50, 200, 80)
                    sym = "✅"
                elif is_snake:
                    bg = (40, 20, 10)
                    border = (200, 150, 50)
                    sym = "🐍"
                else:
                    bg = (10, 18, 35)
                    border = (30, 60, 100)
                    sym = ""

                draw.rounded_rectangle([tx, fy, tx + tile_w, fy + tile_h], radius=6, fill=bg, outline=border, width=2)
                if sym:
                    try:
                        emoji_font = ImageFont.truetype("NotoColorEmoji.ttf", 24)
                    except Exception:
                        emoji_font = ImageFont.load_default()
                    sym_bbox = draw.textbbox((0, 0), sym, font=emoji_font)
                    sym_w = sym_bbox[2] - sym_bbox[0]
                    draw.text((tx + (tile_w - sym_w) // 2, fy + 6), sym, font=emoji_font)

            # Draw snake indicator if not on that floor yet
            if floor >= len(selected_tiles) and not won:
                pass  # unrevealed

        y = grid_start_y + grid_total_h + 20

        # Game ID
        gid_text = f"Game ID: {game_id}"
        gid_w = draw.textlength(gid_text, font=f_id)
        draw.text(((W - gid_w) // 2, y), gid_text, fill=(80, 120, 160), font=f_id)

        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output
    except Exception as e:
        logging.error(f"Tower template render error: {e}")
        return None

def _render_keno_sync(username, bet_amount, selected_numbers, drawn_numbers, matches, num_picks, won, multiplier, winnings, game_id):
    """Render Keno result template showing the 40-number grid with matches highlighted."""
    try:
        W, H = 700, 1050
        img, draw = _game_template_background(W, H)

        try:
            f_title = ImageFont.truetype("bold.ttf", 28)
            f_user = ImageFont.truetype("bold.ttf", 18)
            f_stat = ImageFont.truetype("bold.ttf", 20)
            f_small = ImageFont.truetype("bold.ttf", 12)
            f_result = ImageFont.truetype("bold.ttf", 22)
            f_id = ImageFont.truetype("bold.ttf", 11)
            f_grid_lbl = ImageFont.truetype("bold.ttf", 10)
            f_cell = ImageFont.truetype("bold.ttf", 16)
        except Exception:
            f_title = f_user = f_stat = f_small = f_result = f_id = f_grid_lbl = f_cell = ImageFont.load_default()

        drawn_set = set(drawn_numbers)
        selected_set = set(selected_numbers)
        matched_set = selected_set & drawn_set

        y = 18

        # Bot username
        bot_un = "@playcsino"
        bw = draw.textlength(bot_un, font=f_user)
        draw.text((W - 15 - bw, y), bot_un, fill=(100, 180, 255), font=f_user)
        y += 30

        # Title
        title = "KENO RESULT"
        tw = draw.textlength(title, font=f_title)
        draw.text(((W - tw) // 2, y), title, fill=(255, 255, 255), font=f_title)
        y += 35

        # Username
        un_bbox = draw.textbbox((0, 0), username, font=f_user)
        un_w = un_bbox[2] - un_bbox[0]
        draw.text(((W - un_w) // 2, y), username, fill=(100, 180, 255), font=f_user)
        y += 30

        # Result banner
        if won:
            banner_color = (0, 60, 40)
            banner_text = f"YOU WON ${winnings:.2f}!"
            banner_fill = (0, 255, 120)
        else:
            banner_color = (60, 10, 10)
            banner_text = "NO WIN"
            banner_fill = (255, 80, 80)
        bw2 = draw.textlength(banner_text, font=f_result)
        draw.rounded_rectangle([(W - bw2 - 40) // 2, y, (W + bw2 + 40) // 2, y + 40], radius=10, fill=banner_color)
        draw.text(((W - bw2) // 2, y + 6), banner_text, fill=banner_fill, font=f_result)
        y += 55

        # Stats
        stat_y = y
        stats = [
            (f"${bet_amount:.2f}", "BET"),
            (f"{matches}/{num_picks}", "MATCHES"),
            (f"{multiplier:.2f}x" if multiplier > 0 else "0x", "MULTIPLIER"),
        ]
        stat_w = 190
        stat_h = 60
        stat_gap = 10
        stat_start = (W - (stat_w * 3 + stat_gap * 2)) // 2
        for i, (val, lbl) in enumerate(stats):
            sx = stat_start + i * (stat_w + stat_gap)
            draw.rounded_rectangle([sx, stat_y, sx + stat_w, stat_y + stat_h], radius=8, fill=(12, 25, 45), outline=(40, 80, 120), width=1)
            draw.text((sx + 10, stat_y + 6), val, fill=(255, 255, 255), font=f_stat)
            draw.text((sx + 10, stat_y + 36), lbl, fill=(100, 160, 200), font=f_grid_lbl)
        y = stat_y + stat_h + 20

        # 40-number grid (8 cols x 5 rows)
        cell_size = 50
        cell_gap = 4
        cols = 8
        rows = 5
        grid_total_w = cols * cell_size + (cols - 1) * cell_gap
        grid_total_h = rows * cell_size + (rows - 1) * cell_gap
        grid_x = (W - grid_total_w) // 2
        grid_y = y

        for num in range(1, 41):
            row = (num - 1) // cols
            col = (num - 1) % cols
            cx = grid_x + col * (cell_size + cell_gap)
            cy = grid_y + row * (cell_size + cell_gap)

            is_selected = num in selected_set
            is_drawn = num in drawn_set
            is_match = num in matched_set

            if is_match:
                bg = (0, 80, 40)
                border = (0, 255, 120)
                num_color = (0, 255, 120)
            elif is_selected and is_drawn:
                bg = (0, 60, 30)
                border = (50, 200, 80)
                num_color = (100, 220, 150)
            elif is_drawn:
                bg = (15, 25, 50)
                border = (80, 120, 200)
                num_color = (100, 160, 255)
            elif is_selected:
                bg = (25, 20, 50)
                border = (150, 100, 255)
                num_color = (180, 130, 255)
            else:
                bg = (10, 18, 35)
                border = (30, 50, 80)
                num_color = (80, 100, 130)

            draw.rounded_rectangle([cx, cy, cx + cell_size, cy + cell_size], radius=6, fill=bg, outline=border, width=2)
            txt = str(num)
            tw2 = draw.textlength(txt, font=f_cell)
            draw.text((cx + (cell_size - tw2) // 2, cy + 12), txt, fill=num_color, font=f_cell)

        y = grid_y + grid_total_h + 20

        # Game ID
        gid_text = f"Game ID: {game_id}"
        gid_w = draw.textlength(gid_text, font=f_id)
        draw.text(((W - gid_w) // 2, y), gid_text, fill=(80, 120, 160), font=f_id)

        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output
    except Exception as e:
        logging.error(f"Keno template render error: {e}")
        return None

def _render_roulette_sync(username, bet_amount, choice, choice_numbers, winning_number, won, multiplier, winnings, game_id):
    """Render Roulette result template showing the winning number and bet details."""
    try:
        W, H = 700, 1050
        img, draw = _game_template_background(W, H)

        try:
            f_title = ImageFont.truetype("bold.ttf", 28)
            f_user = ImageFont.truetype("bold.ttf", 18)
            f_stat = ImageFont.truetype("bold.ttf", 20)
            f_small = ImageFont.truetype("bold.ttf", 12)
            f_result = ImageFont.truetype("bold.ttf", 22)
            f_id = ImageFont.truetype("bold.ttf", 11)
            f_grid_lbl = ImageFont.truetype("bold.ttf", 10)
            f_big_num = ImageFont.truetype("bold.ttf", 48)
            f_num = ImageFont.truetype("bold.ttf", 16)
        except Exception:
            f_title = f_user = f_stat = f_small = f_result = f_id = f_grid_lbl = f_big_num = f_num = ImageFont.load_default()

        # Determine color
        if winning_number == 0:
            num_color = (0, 200, 80)
            color_label = "GREEN"
        elif winning_number in ROULETTE_CONFIG.get("red", {}).get("numbers", []):
            num_color = (220, 50, 50)
            color_label = "RED"
        else:
            num_color = (180, 180, 180)
            color_label = "BLACK"

        # Format choice display
        choice_display = choice.upper() if choice else "N/A"
        if choice == "dozen1":
            choice_display = "1st DOZEN (1-12)"
        elif choice == "dozen2":
            choice_display = "2nd DOZEN (13-24)"
        elif choice == "dozen3":
            choice_display = "3rd DOZEN (25-36)"
        elif choice == "numbers" and choice_numbers:
            choice_display = f"NUMBERS: {', '.join(map(str, sorted(choice_numbers)))}"

        y = 18

        # Bot username
        bot_un = "@playcsino"
        bw = draw.textlength(bot_un, font=f_user)
        draw.text((W - 15 - bw, y), bot_un, fill=(100, 180, 255), font=f_user)
        y += 30

        # Title
        title = "ROULETTE RESULT"
        tw = draw.textlength(title, font=f_title)
        draw.text(((W - tw) // 2, y), title, fill=(255, 255, 255), font=f_title)
        y += 35

        # Username
        un_bbox = draw.textbbox((0, 0), username, font=f_user)
        un_w = un_bbox[2] - un_bbox[0]
        draw.text(((W - un_w) // 2, y), username, fill=(100, 180, 255), font=f_user)
        y += 30

        # Winning number display (big circle)
        num_circle_r = 55
        num_cx = W // 2
        num_cy = y + num_circle_r + 10

        # Outer glow
        draw.ellipse([num_cx - num_circle_r - 6, num_cy - num_circle_r - 6, num_cx + num_circle_r + 6, num_cy + num_circle_r + 6], fill=(30, 40, 60))
        # Main circle
        draw.ellipse([num_cx - num_circle_r, num_cy - num_circle_r, num_cx + num_circle_r, num_cy + num_circle_r], fill=(15, 25, 45), outline=num_color, width=3)
        # Number
        num_str = str(winning_number)
        nw = draw.textlength(num_str, font=f_big_num)
        draw.text((num_cx - nw // 2, num_cy - 24), num_str, fill=num_color, font=f_big_num)
        # Color label
        cl = draw.textlength(color_label, font=f_small)
        draw.text((num_cx - cl // 2, num_cy + num_circle_r + 5), color_label, fill=num_color, font=f_small)

        y = num_cy + num_circle_r + 30

        # Result banner
        if won:
            banner_color = (0, 60, 40)
            banner_text = f"YOU WON ${winnings:.2f}!"
            banner_fill = (0, 255, 120)
        else:
            banner_color = (60, 10, 10)
            banner_text = "YOU LOST"
            banner_fill = (255, 80, 80)
        bw2 = draw.textlength(banner_text, font=f_result)
        draw.rounded_rectangle([(W - bw2 - 40) // 2, y, (W + bw2 + 40) // 2, y + 40], radius=10, fill=banner_color)
        draw.text(((W - bw2) // 2, y + 6), banner_text, fill=banner_fill, font=f_result)
        y += 55

        # Stats
        stat_y = y
        stats = [
            (f"${bet_amount:.2f}", "BET"),
            (f"{multiplier}x" if multiplier > 0 else "0x", "MULTIPLIER"),
            (choice_display[:15] if len(choice_display) > 15 else choice_display, "YOUR BET"),
        ]
        stat_w = 190
        stat_h = 60
        stat_gap = 10
        stat_start = (W - (stat_w * 3 + stat_gap * 2)) // 2
        for i, (val, lbl) in enumerate(stats):
            sx = stat_start + i * (stat_w + stat_gap)
            draw.rounded_rectangle([sx, stat_y, sx + stat_w, stat_y + stat_h], radius=8, fill=(12, 25, 45), outline=(40, 80, 120), width=1)
            draw.text((sx + 10, stat_y + 6), val, fill=(255, 255, 255), font=f_stat)
            draw.text((sx + 10, stat_y + 36), lbl, fill=(100, 160, 200), font=f_grid_lbl)
        y = stat_y + stat_h + 25

        # Roulette number grid (simplified 0-36)
        grid_cols = 12
        grid_rows = 3
        cell_w = 48
        cell_h = 36
        cell_gap = 3
        grid_total_w = grid_cols * cell_w + (grid_cols - 1) * cell_gap
        grid_total_h = grid_rows * cell_h + (grid_rows - 1) * cell_gap
        grid_x = (W - grid_total_w) // 2
        grid_y = y

        # Roulette number order: row0 = 3,6,9,12,15,18,21,24,27,30,33,36; row1 = 2,5,8...; row2 = 1,4,7...
        red_nums = ROULETTE_CONFIG.get("red", {}).get("numbers", [])
        for row in range(grid_rows):
            for col in range(grid_cols):
                # Standard roulette layout
                num = (grid_rows - row) + col * grid_rows
                if num > 36:
                    continue
                cx = grid_x + col * (cell_w + cell_gap)
                cy = grid_y + row * (cell_h + cell_gap)

                if num == 0:
                    bg = (0, 60, 20)
                    border = (0, 200, 80)
                elif num in red_nums:
                    bg = (60, 15, 15)
                    border = (200, 50, 50)
                else:
                    bg = (15, 15, 20)
                    border = (100, 100, 100)

                if num == winning_number:
                    border = (255, 255, 50)
                    bg = (60, 50, 10)

                draw.rounded_rectangle([cx, cy, cx + cell_w, cy + cell_h], radius=4, fill=bg, outline=border, width=2)
                txt = str(num)
                tw2 = draw.textlength(txt, font=f_num)
                num_clr = (255, 255, 50) if num == winning_number else (200, 200, 200)
                draw.text((cx + (cell_w - tw2) // 2, cy + 8), txt, fill=num_clr, font=f_num)

        y = grid_y + grid_total_h + 20

        # Game ID
        gid_text = f"Game ID: {game_id}"
        gid_w = draw.textlength(gid_text, font=f_id)
        draw.text(((W - gid_w) // 2, y), gid_text, fill=(80, 120, 160), font=f_id)

        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output
    except Exception as e:
        logging.error(f"Roulette template render error: {e}")
        return None

def generate_jackpot_status_image(
    pool_amount: float,
    wager_threshold: float,
    user_7d_wager: float,
    next_draw_in_seconds: float,
    last_winner: dict | None,
    bot_username: str,
    player_username: str | None = None,
    player_profile_pic=None,
) -> BytesIO:
    """Render the /jackpot status card. All player names / amounts are
    runtime values — nothing is hard-coded."""
    W, H = 800, 700
    BG = (8, 12, 28)
    GOLD = (255, 215, 80)
    GOLD_DIM = (160, 120, 30)
    GREEN = (0, 220, 130)
    RED = (255, 80, 80)
    BLUE = (0, 180, 255)
    TXT = (240, 244, 255)
    DIM = (140, 160, 200)
    BORDER = (28, 60, 120)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Subtle radial glow + grid background.
    cx, cy = W // 2, 260
    for r in range(280, 0, -14):
        a = int(14 * (r / 280))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=(8 + a, 12 + a // 2, 28 + a))
    for gx in range(0, W, 50):
        draw.line([(gx, 0), (gx, H)], fill=(20, 35, 70), width=1)
    for gy in range(0, H, 50):
        draw.line([(0, gy), (W, gy)], fill=(20, 35, 70), width=1)

    # Header bar.
    f_title = _jackpot_get_font(34)
    f_sub   = _jackpot_get_font(14)
    f_lbl   = _jackpot_get_font(16)
    f_pool  = _jackpot_get_font(72)
    f_body  = _jackpot_get_font(16)
    f_small = _jackpot_get_font(13)
    f_tiny  = _jackpot_get_font(11)

    # Top-left avatar + player username.
    img, draw = _jackpot_paste_circle_avatar(img, player_profile_pic, 18, 14, 56, BLUE)
    if player_username:
        plabel = f"@{player_username}" if not player_username.startswith("@") else player_username
        draw.text((86, 22), plabel, font=f_lbl, fill=TXT)
        draw.text((86, 44), "Jackpot status", font=f_small, fill=DIM)

    # Top-right bot watermark.
    bot_lbl = f"@{bot_username}" if not bot_username.startswith("@") else bot_username
    bw = draw.textlength(bot_lbl, font=f_lbl)
    draw.text((W - bw - 18, 18), bot_lbl, font=f_lbl, fill=GOLD)
    sub_brand = "Telegram Casino"
    sbw = draw.textlength(sub_brand, font=f_tiny)
    draw.text((W - sbw - 18, 44), sub_brand, font=f_tiny, fill=DIM)

    # Title strip.
    draw.line([(20, 86), (W - 20, 86)], fill=GOLD, width=2)
    title = "DAILY JACKPOT"
    tw = draw.textlength(title, font=f_title)
    draw.text(((W - tw) // 2, 100), title, font=f_title, fill=GOLD)

    # Pool amount (huge).
    pool_str = f"${pool_amount:,.2f}"
    pw = draw.textlength(pool_str, font=f_pool)
    draw.text(((W - pw) // 2, 150), pool_str, font=f_pool, fill=GREEN)

    pool_lbl = "current pool"
    plw = draw.textlength(pool_lbl, font=f_small)
    draw.text(((W - plw) // 2, 240), pool_lbl, font=f_small, fill=DIM)

    # Countdown card.
    card_y = 280
    draw.rounded_rectangle([40, card_y, W - 40, card_y + 90], radius=16,
                           fill=(12, 22, 50), outline=BORDER, width=2)
    secs = max(0, int(next_draw_in_seconds))
    hours = secs // 3600
    mins = (secs % 3600) // 60
    cd_str = f"{hours:02d}h {mins:02d}m"
    draw.text((60, card_y + 14), "NEXT DRAW IN", font=f_lbl, fill=DIM)
    draw.text((60, card_y + 40), cd_str, font=f_title, fill=GOLD)
    rt = "Daily at 5:30 PM IST"
    rtw = draw.textlength(rt, font=f_small)
    draw.text((W - rtw - 60, card_y + 50), rt, font=f_small, fill=DIM)

    # Eligibility / progress card.
    elig_y = card_y + 110
    draw.rounded_rectangle([40, elig_y, W - 40, elig_y + 130], radius=16,
                           fill=(10, 18, 38), outline=BORDER, width=2)
    draw.text((60, elig_y + 14), "YOUR 7-DAY WAGER", font=f_lbl, fill=DIM)
    progress = 0.0 if wager_threshold <= 0 else min(1.0, user_7d_wager / wager_threshold)
    eligible = user_7d_wager >= wager_threshold and wager_threshold > 0
    bar_x0, bar_x1 = 60, W - 60
    bar_y0 = elig_y + 50
    bar_y1 = elig_y + 70
    draw.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], radius=10,
                           fill=(18, 28, 56))
    fill_w = int((bar_x1 - bar_x0) * progress)
    if fill_w > 0:
        bar_color = GREEN if eligible else BLUE
        draw.rounded_rectangle(
            [bar_x0, bar_y0, bar_x0 + fill_w, bar_y1], radius=10, fill=bar_color,
        )
    progress_text = f"${user_7d_wager:,.2f} / ${wager_threshold:,.2f}"
    pw2 = draw.textlength(progress_text, font=f_body)
    draw.text(((W - pw2) // 2, bar_y1 + 10), progress_text, font=f_body, fill=TXT)
    if eligible:
        status = "You are eligible for tonight's draw."
        scolor = GREEN
    else:
        needed = max(0.0, wager_threshold - user_7d_wager)
        status = f"Wager ${needed:,.2f} more in the next 7 days to qualify."
        scolor = RED
    sw = draw.textlength(status, font=f_small)
    draw.text(((W - sw) // 2, bar_y1 + 32), status, font=f_small, fill=scolor)

    # Last winner card.
    lw_y = elig_y + 150
    draw.rounded_rectangle([40, lw_y, W - 40, lw_y + 80], radius=16,
                           fill=(20, 14, 4), outline=GOLD_DIM, width=2)
    draw.text((60, lw_y + 12), "LAST WINNER", font=f_lbl, fill=GOLD_DIM)
    if last_winner:
        wn = last_winner.get("username") or f"User-{last_winner.get('user_id', '')}"
        wn_lbl = f"@{wn}" if wn and not wn.startswith("@") else (wn or "")
        draw.text((60, lw_y + 36), wn_lbl, font=f_lbl, fill=TXT)
        amt_str = f"+${float(last_winner.get('amount', 0)):,.2f}"
        aw = draw.textlength(amt_str, font=f_lbl)
        draw.text((W - aw - 60, lw_y + 36), amt_str, font=f_lbl, fill=GREEN)
    else:
        draw.text((60, lw_y + 36), "No winners yet — be the first!", font=f_body, fill=DIM)

    # Footer line.
    foot = "0.2% of every bet feeds the pool  •  Play Responsibly  •  Telegram Casino"
    fw = draw.textlength(foot, font=f_tiny)
    draw.text(((W - fw) // 2, H - 22), foot, font=f_tiny, fill=(70, 95, 140))

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def generate_jackpot_winner_image(
    winner_username: str,
    amount_won: float,
    bot_username: str,
    winner_profile_pic=None,
    draw_iso: str = None,
) -> BytesIO:
    """Render the @PlayCasino winner-announcement card."""
    W, H = 900, 560
    BG = (8, 12, 28)
    GOLD = (255, 215, 80)
    GOLD_DIM = (160, 120, 30)
    GREEN = (0, 220, 130)
    BLUE = (0, 180, 255)
    TXT = (245, 248, 255)
    DIM = (150, 170, 210)
    BORDER = (40, 70, 130)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Big radial glow centred on the avatar.
    cx, cy = W // 2, 250
    for r in range(360, 0, -16):
        a = int(20 * (r / 360))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=(10 + a, 14 + a // 2, 32 + a))
    for gx in range(0, W, 50):
        draw.line([(gx, 0), (gx, H)], fill=(22, 38, 72), width=1)
    for gy in range(0, H, 50):
        draw.line([(0, gy), (W, gy)], fill=(22, 38, 72), width=1)

    f_title = _jackpot_get_font(40)
    f_sub   = _jackpot_get_font(18)
    f_lbl   = _jackpot_get_font(16)
    f_amt   = _jackpot_get_font(80)
    f_body  = _jackpot_get_font(20)
    f_tiny  = _jackpot_get_font(12)

    # Top-right bot label.
    bot_lbl = f"@{bot_username}" if not bot_username.startswith("@") else bot_username
    bw = draw.textlength(bot_lbl, font=f_lbl)
    draw.text((W - bw - 18, 18), bot_lbl, font=f_lbl, fill=GOLD)
    brand = "Telegram Casino"
    bsw = draw.textlength(brand, font=f_tiny)
    draw.text((W - bsw - 18, 40), brand, font=f_tiny, fill=DIM)

    # Header strip.
    draw.line([(20, 70), (W - 20, 70)], fill=GOLD, width=2)
    title = "JACKPOT WINNER"
    tw = draw.textlength(title, font=f_title)
    draw.text(((W - tw) // 2, 86), title, font=f_title, fill=GOLD)

    # Big avatar centred.
    av_size = 130
    av_x = (W - av_size) // 2
    av_y = 150
    img, draw = _jackpot_paste_circle_avatar(img, winner_profile_pic, av_x, av_y, av_size, GOLD)

    # Winner username.
    wn = winner_username or "Player"
    wn_lbl = f"@{wn}" if not wn.startswith("@") else wn
    nw = draw.textlength(wn_lbl, font=f_body)
    draw.text(((W - nw) // 2, av_y + av_size + 14), wn_lbl, font=f_body, fill=TXT)

    # Amount.
    amt_str = f"${amount_won:,.2f}"
    aw = draw.textlength(amt_str, font=f_amt)
    draw.text(((W - aw) // 2, av_y + av_size + 50), amt_str, font=f_amt, fill=GREEN)

    # Sub-line.
    sub = "won the daily jackpot"
    sw = draw.textlength(sub, font=f_sub)
    draw.text(((W - sw) // 2, av_y + av_size + 142), sub, font=f_sub, fill=DIM)

    # Footer.
    foot = "Play Responsibly  •  Telegram Casino  •  jackpot"
    fw = draw.textlength(foot, font=f_tiny)
    draw.text(((W - fw) // 2, H - 24), foot, font=f_tiny, fill=(70, 95, 140))

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def generate_bj_image(
    player_hand: list,
    dealer_hand: list,
    show_dealer_hole: bool = False,
    player_value: int = None,
    dealer_value: int = None,
    player_username: str = None,
    bet_amount: float = None,
    bot_username: str = "Casino",
    result_text: str = None,
    result_color: tuple = None,
    player_profile_pic = None,  # PIL Image or None
    split_hands: list = None,  # List of hands for split mode: [hand1, hand2]
    split_active_hand: int = 0,  # Index of active hand (0-indexed) in split mode
    split_bets: list = None,  # List of bet amounts for each split hand
    split_results: list = None,  # List of results for completed hands: [{status, value}]
) -> BytesIO:
    """Render the blackjack table image — circuit-board / neon-result design.

    Mirrors ``example_designs/blackjack_pil_image_template_design.png``.
    Layout:
      - Wide canvas with a navy → faint-purple gradient + decorative
        circuit-board lines on the left and right edges.
      - Wireframe-mesh head avatar in the top-left, "@bot_username" in
        the top-right (blue).
      - Gold "DEALER" pill at top-centre + "Value: N" below it.
      - Dealer cards centred below the pill.
      - Glowing red "result band" overlapping the dealer card row when a
        result is set (e.g. "Dealer Wins" / "Player Wins" / "Push" /
        "Blackjack!").
      - Gold "PLAYER" label below the band, then either a single hand or
        the split hands side-by-side. Hand 1 / Hand 2 labels are coloured
        gold and red respectively (red = currently active in split mode
        when the active hand is index 1, else gold).
      - Bottom info bar: "Bet: $X" left, "BLACKJACK ALSO SUPPORTS SPLIT"
        with a dice glyph centre, "BLACKJACK" gold + diamond right.
      - Footer hairline: "Play Responsibly • Telegram Casino • blackjack".
    """
    from PIL import ImageFilter as _ImgFilter

    is_split = split_hands is not None and len(split_hands) >= 2
    W, H = (1100, 820) if is_split else (1100, 720)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── BACKGROUND: navy → faint purple ──────────────────────
    BG_TOP = (4, 8, 28)
    BG_MID = (10, 8, 36)
    BG_BOT = (28, 14, 50)
    for yy in range(H):
        t = yy / H
        if t < 0.5:
            u = t * 2
            r = int(BG_TOP[0] + u * (BG_MID[0] - BG_TOP[0]))
            g = int(BG_TOP[1] + u * (BG_MID[1] - BG_TOP[1]))
            b = int(BG_TOP[2] + u * (BG_MID[2] - BG_TOP[2]))
        else:
            u = (t - 0.5) * 2
            r = int(BG_MID[0] + u * (BG_BOT[0] - BG_MID[0]))
            g = int(BG_MID[1] + u * (BG_BOT[1] - BG_MID[1]))
            b = int(BG_MID[2] + u * (BG_BOT[2] - BG_MID[2]))
        draw.line([(0, yy), (W, yy)], fill=(r, g, b))

    # ── DECORATIVE CIRCUIT-BOARD LINES ───────────────────────
    rng = random.Random(7)
    line_color = (50, 35, 100)
    pad_color  = (90, 60, 160)
    band_y = H // 2 - 30
    # Horizontal lines extending into the side margins (matches the template's
    # circuit traces flanking the result band).
    for side, x_start, sign in (
        ("L", 20, 1), ("L", 20, 1), ("R", W - 20, -1), ("R", W - 20, -1),
    ):
        offset = rng.randint(-40, 40)
        ly = band_y + offset
        seg_n = rng.randint(2, 4)
        cur_x = x_start
        cur_y = ly
        for _ in range(seg_n):
            seg_len = rng.randint(60, 140)
            draw.line([(cur_x, cur_y), (cur_x + sign * seg_len, cur_y)],
                      fill=line_color, width=1)
            cur_x += sign * seg_len
            step = rng.choice([-30, -22, 22, 30])
            draw.line([(cur_x, cur_y), (cur_x, cur_y + step)],
                      fill=line_color, width=1)
            cur_y += step
        draw.ellipse([cur_x - 3, cur_y - 3, cur_x + 3, cur_y + 3],
                     fill=pad_color)
    # Generic mesh.
    for _ in range(60):
        sx = rng.choice([rng.randint(0, 90), rng.randint(W - 90, W - 1)])
        sy = rng.randint(40, H - 80)
        sl = rng.randint(40, 110)
        sign = 1 if sx < W // 2 else -1
        draw.line([(sx, sy), (sx + sign * sl, sy)],
                  fill=line_color, width=1)
    # Sparkle dots.
    for _ in range(70):
        sx, sy = rng.randint(0, W), rng.randint(0, H)
        br = rng.randint(40, 130)
        draw.ellipse([sx - 1, sy - 1, sx + 1, sy + 1], fill=(br, br, br + 20))

    # ── PROFILE AVATAR (top-left) ───────────────────────────
    # Composite player's Telegram profile pic into the top-left cell;
    # falls back to the wireframe head if no pic is available.
    h_cx, h_cy, h_rx, h_ry = 92, 100, 56, 70
    _paste_avatar_in_circle(
        img, draw, h_cx, h_cy, h_rx, h_ry,
        player_profile_pic, accent_rgba=(70, 200, 255, 220),
    )
    draw = ImageDraw.Draw(img)

    # ── TOP-RIGHT BOT USERNAME ──────────────────────────────
    font_bot = _bj_get_font(28)
    wm_text = f"@{bot_username}" if not bot_username.startswith("@") else bot_username
    wm_w = draw.textlength(wm_text, font=font_bot)
    draw.text((W - wm_w - 30, 30), wm_text, font=font_bot, fill=(90, 200, 255))

    # ── DEALER PILL ─────────────────────────────────────────
    font_pill = _bj_get_font(22)
    dealer_lbl = "DEALER"
    dlw = draw.textlength(dealer_lbl, font=font_pill)
    pill_w = int(dlw + 70)
    pill_h = 44
    pill_x = (W - pill_w) // 2
    pill_y = 50
    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=20, fill=(28, 18, 8), outline=BJ_TEXT_GOLD, width=2,
    )
    draw.text((pill_x + (pill_w - dlw) / 2, pill_y + 8),
              dealer_lbl, font=font_pill, fill=BJ_TEXT_GOLD)

    # Dealer value text below pill.
    font_val = _bj_get_font(22)
    if show_dealer_hole and dealer_value is not None:
        dv_str = f"Value: {dealer_value}"
    elif dealer_value is not None and len(dealer_hand or []) > 0:
        dv_str = f"Value: ?"
    else:
        dv_str = ""
    if dv_str:
        dvw = draw.textlength(dv_str, font=font_val)
        draw.text(((W - dvw) / 2, pill_y + pill_h + 6),
                  dv_str, font=font_val, fill=BJ_TEXT_WHITE)

    # ── DEALER CARDS ────────────────────────────────────────
    dealer_cards = list(dealer_hand or [])
    n_dealer = len(dealer_cards)
    # Larger card size for visual presence.
    CARD_W2 = int(BJ_CARD_W * 1.4)
    CARD_H2 = int(BJ_CARD_H * 1.4)
    card_gap = 10
    dealer_row_w = n_dealer * CARD_W2 + (n_dealer - 1) * card_gap if n_dealer else 0
    dealer_x0 = (W - dealer_row_w) // 2
    dealer_y0 = pill_y + pill_h + 50

    # Save current image temporarily as RGB for card drawing helpers, then we
    # composite back. Use an RGB buffer to leverage the existing helpers.
    rgb_img = img.convert("RGB")
    rgb_draw = ImageDraw.Draw(rgb_img)

    def _draw_card_scaled(rgb_draw_, x, y, rank, suit, scale=1.4):
        """Draw a single face-up card scaled up from the base 78x110 template."""
        cw = int(BJ_CARD_W * scale)
        ch = int(BJ_CARD_H * scale)
        # Shadow.
        rgb_draw_.rounded_rectangle([x + 3, y + 3, x + cw + 3, y + ch + 3],
                                     radius=BJ_CARD_RADIUS + 2,
                                     fill=(0, 0, 0))
        rgb_draw_.rounded_rectangle([x, y, x + cw, y + ch],
                                     radius=BJ_CARD_RADIUS + 2,
                                     fill=BJ_CARD_BG,
                                     outline=(180, 180, 180), width=1)
        color = BJ_RED if suit in ('♥', '♦') else BJ_BLACK_SUIT
        f_rank = _bj_get_font(int(28 * scale / 1.4))
        f_suit_corner = _bj_get_font(int(24 * scale / 1.4))
        f_suit_center = _bj_get_font(int(54 * scale / 1.4))
        # Top-left rank + suit.
        rgb_draw_.text((x + 8, y + 6), rank, font=f_rank, fill=color)
        rgb_draw_.text((x + 8, y + 6 + int(28 * scale / 1.4)), suit,
                       font=f_suit_corner, fill=color)
        # Center suit pip.
        cx = x + cw // 2
        cy = y + ch // 2
        sw = rgb_draw_.textlength(suit, font=f_suit_center)
        rgb_draw_.text((cx - sw / 2, cy - int(36 * scale / 1.4)),
                       suit, font=f_suit_center, fill=color)
        # Bottom-right (rotated-feel) rank + suit.
        rgb_draw_.text((x + cw - 22, y + ch - int(60 * scale / 1.4)),
                       rank, font=f_rank, fill=color)
        rgb_draw_.text((x + cw - 22, y + ch - int(34 * scale / 1.4)),
                       suit, font=f_suit_corner, fill=color)

    def _draw_hidden_scaled(rgb_draw_, x, y, scale=1.4):
        cw = int(BJ_CARD_W * scale)
        ch = int(BJ_CARD_H * scale)
        rgb_draw_.rounded_rectangle([x + 3, y + 3, x + cw + 3, y + ch + 3],
                                     radius=BJ_CARD_RADIUS + 2,
                                     fill=(0, 0, 0))
        rgb_draw_.rounded_rectangle([x, y, x + cw, y + ch],
                                     radius=BJ_CARD_RADIUS + 2,
                                     fill=BJ_CARD_BACK,
                                     outline=(80, 80, 160), width=2)
        for i in range(-ch, cw, 14):
            rgb_draw_.line([(x + i, y), (x + i + ch, y + ch)],
                            fill=(40, 60, 140), width=1)
        f = _bj_get_font(int(28 * scale / 1.4))
        rgb_draw_.text((x + cw // 2 - 10, y + ch // 2 - 16),
                       "?", font=f, fill=(100, 120, 220))

    for i, c in enumerate(dealer_cards):
        cx = dealer_x0 + i * (CARD_W2 + card_gap)
        if i == 1 and not show_dealer_hole:
            _draw_hidden_scaled(rgb_draw, cx, dealer_y0)
        else:
            rank, suit = _bj_parse_card(c)
            _draw_card_scaled(rgb_draw, cx, dealer_y0, rank, suit)

    # Re-composite RGB image back into our RGBA workspace.
    img = rgb_img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # ── RESULT BAND (only when result_text is provided) ─────
    if result_text:
        is_win = result_color == BJ_WIN_COLOR or (result_color and result_color[1] > 200 and result_color[0] < 200)
        is_push = result_color == BJ_PUSH_COLOR or (result_color and result_color[0] > 200 and result_color[1] > 150 and result_color[2] < 100)
        if is_win:
            band_color = (60, 235, 130)
            band_inner = (8, 36, 22)
        elif is_push:
            band_color = (240, 200, 60)
            band_inner = (40, 30, 8)
        else:
            band_color = (255, 70, 80)
            band_inner = (50, 8, 16)

        band_w = int(W * 0.65)
        band_h = 110
        band_x = (W - band_w) // 2
        band_y = dealer_y0 + CARD_H2 - 30  # overlap the bottom of dealer cards
        # Soft outer glow.
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for k, (alpha, pad) in enumerate([(140, 18), (90, 12), (60, 6)]):
            gd.rounded_rectangle(
                [band_x - pad, band_y - pad, band_x + band_w + pad, band_y + band_h + pad],
                radius=18,
                fill=(band_color[0], band_color[1], band_color[2], alpha),
            )
        glow = glow.filter(_ImgFilter.GaussianBlur(radius=14))
        img.alpha_composite(glow)
        draw = ImageDraw.Draw(img)
        # Band fill.
        draw.rounded_rectangle(
            [band_x, band_y, band_x + band_w, band_y + band_h],
            radius=18, fill=band_inner, outline=band_color, width=3,
        )
        # Highlight.
        draw.rounded_rectangle(
            [band_x + 6, band_y + 6, band_x + band_w - 6, band_y + 16],
            radius=6, fill=(band_color[0] // 4, band_color[1] // 4, band_color[2] // 4),
        )
        # Result text.
        f_result = _bj_get_font(46)
        rw = draw.textlength(result_text, font=f_result)
        draw.text(
            (band_x + (band_w - rw) / 2, band_y + (band_h - 50) / 2),
            result_text, font=f_result, fill=BJ_TEXT_WHITE,
        )
        result_band_bottom = band_y + band_h
    else:
        result_band_bottom = dealer_y0 + CARD_H2

    # ── PLAYER LABEL ────────────────────────────────────────
    player_label = "PLAYER"
    f_player_lbl = _bj_get_font(26)
    plw = draw.textlength(player_label, font=f_player_lbl)
    player_lbl_y = result_band_bottom + 18
    draw.text(((W - plw) / 2, player_lbl_y),
              player_label, font=f_player_lbl, fill=BJ_TEXT_GOLD)

    # ── PLAYER CARDS ────────────────────────────────────────
    rgb_img = img.convert("RGB")
    rgb_draw = ImageDraw.Draw(rgb_img)
    cards_top = player_lbl_y + 40
    f_handlbl = _bj_get_font(20)
    f_handval = _bj_get_font(22)

    if is_split:
        # Two hands side-by-side; each hand is its own card row centred in
        # one half of the canvas.
        for hi, hand in enumerate(split_hands[:2]):
            n = max(2, len(hand))
            row_w = n * CARD_W2 + (n - 1) * card_gap
            # Box bounds.
            x_center = int(W * (0.30 if hi == 0 else 0.70))
            row_x0 = x_center - row_w // 2
            for j, c in enumerate(hand):
                rank, suit = _bj_parse_card(c)
                _draw_card_scaled(rgb_draw, row_x0 + j * (CARD_W2 + card_gap),
                                  cards_top, rank, suit)
            # Hand label (Hand 1 left of cards, Hand 2 right of cards).
            is_active = (split_active_hand == hi)
            hand_color = BJ_TEXT_GOLD if hi == 0 else BJ_LOSE_COLOR
            label_str = f"Hand {hi + 1}"
            value_str = ""
            if split_results and hi < len(split_results):
                v = split_results[hi].get("value")
                value_str = f"Value: {v}" if v is not None else ""
            else:
                # Fallback: compute from hand using calculate_hand_value when present.
                try:
                    v = calculate_hand_value(hand)
                    value_str = f"Value: {v}"
                except Exception:
                    value_str = ""
            label_x = (row_x0 - 110) if hi == 0 else (row_x0 + row_w + 30)
            rgb_draw.text((label_x, cards_top + 10), label_str,
                           font=f_handlbl, fill=hand_color)
            if value_str:
                rgb_draw.text((label_x, cards_top + 40), value_str,
                               font=f_handval, fill=BJ_TEXT_WHITE)
            # Active-hand outline (subtle red glow stroke).
            if is_active and not split_results:
                rgb_draw.rounded_rectangle(
                    [row_x0 - 6, cards_top - 6,
                     row_x0 + row_w + 6, cards_top + CARD_H2 + 6],
                    radius=14, outline=BJ_LOSE_COLOR, width=2,
                )
    else:
        n = max(2, len(player_hand or []))
        row_w = n * CARD_W2 + (n - 1) * card_gap
        row_x0 = (W - row_w) // 2
        for j, c in enumerate(player_hand or []):
            rank, suit = _bj_parse_card(c)
            _draw_card_scaled(rgb_draw, row_x0 + j * (CARD_W2 + card_gap),
                              cards_top, rank, suit)
        # Player value bottom-centered.
        if player_value is not None:
            pv_str = f"Value: {player_value}"
            pvw = rgb_draw.textlength(pv_str, font=f_handval)
            rgb_draw.text(((W - pvw) / 2, cards_top + CARD_H2 + 14),
                           pv_str, font=f_handval, fill=BJ_TEXT_WHITE)

    img = rgb_img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # ── BOTTOM INFO BAR ────────────────────────────────────
    bar_h = 56
    bar_y = H - bar_h - 26
    draw.rounded_rectangle(
        [16, bar_y, W - 16, bar_y + bar_h],
        radius=14, fill=(14, 22, 50), outline=BJ_TEXT_GOLD, width=2,
    )
    # Bet (left).
    bet_str = f"Bet: ${bet_amount:.2f}" if bet_amount is not None else "Bet: —"
    f_bar = _bj_get_font(22)
    draw.text((38, bar_y + (bar_h - 26) / 2), bet_str,
              font=f_bar, fill=BJ_TEXT_WHITE)
    # Center hint with dice glyph.
    if is_split:
        hint = "BLACKJACK SPLIT — ACTIVE HAND HIGHLIGHTED"
    else:
        hint = "BLACKJACK ALSO SUPPORTS SPLIT"
    f_hint = _bj_get_font(18)
    hw = draw.textlength(hint, font=f_hint)
    # Dice glyph (small two-rect motif).
    glyph_x = (W - hw) // 2 - 38
    glyph_y = bar_y + (bar_h - 24) // 2
    draw.rounded_rectangle([glyph_x, glyph_y, glyph_x + 22, glyph_y + 22],
                           radius=4, fill=(220, 180, 80))
    draw.rounded_rectangle([glyph_x + 8, glyph_y - 6,
                             glyph_x + 30, glyph_y + 16],
                           radius=4, fill=(180, 130, 40))
    draw.text(((W - hw) / 2, bar_y + (bar_h - 22) / 2),
              hint, font=f_hint, fill=BJ_TEXT_GOLD)
    # Right "BLACKJACK" + diamond.
    bj_lbl = "BLACKJACK"
    f_bj = _bj_get_font(22)
    bw2 = draw.textlength(bj_lbl, font=f_bj)
    draw.text((W - bw2 - 60, bar_y + (bar_h - 26) / 2),
              bj_lbl, font=f_bj, fill=BJ_TEXT_GOLD)
    dx, dy = W - 38, bar_y + bar_h // 2
    draw.polygon([(dx, dy - 10), (dx + 10, dy), (dx, dy + 10), (dx - 10, dy)],
                 fill=(90, 200, 255))

    # ── FOOTER LINE ───────────────────────────────────────
    footer = "Play Responsibly  •  Telegram Casino  •  blackjack"
    f_footer = _bj_get_font(14)
    fw = draw.textlength(footer, font=f_footer)
    draw.text(((W - fw) // 2, H - 22), footer,
              font=f_footer, fill=BJ_TEXT_DIM)

    # ── PNG OUT ───────────────────────────────────────────
    out = img.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def generate_dice_rush_image() -> BytesIO:
    """
    Render a 800x900 Dice Rush help image with all 5 game modes.
    Styled similar to the provided reference image.
    """
    W, H = 800, 950
    img = Image.new("RGB", (W, H), DR_BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Background gradient effect
    center_x, center_y = W // 2, H // 2
    for radius in range(400, 0, -20):
        alpha = int(15 * (radius / 400))
        glow_color = (10 + alpha, 10 + alpha // 2, 35 + alpha)
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            fill=glow_color
        )

    # Title section
    font_title = _dr_get_font(36)
    font_subtitle = _dr_get_font(20)
    font_section = _dr_get_font(18)
    font_text = _dr_get_font(14)
    font_small = _dr_get_font(12)

    # Top header bar
    draw.rectangle([0, 0, W, 70], fill=(20, 20, 50))
    draw.line([(0, 70), (W, 70)], fill=DR_ACCENT, width=2)

    # Title: DICE RUSH
    title_text = "DICE RUSH"
    tw = draw.textlength(title_text, font=font_title)
    draw.text(((W - tw) // 2, 12), title_text, font=font_title, fill=DR_GOLD)

    # Subtitle: @playcsino
    sub_text = "@playcsino"
    sw = draw.textlength(sub_text, font=font_subtitle)
    draw.text(((W - sw) // 2, 50), sub_text, font=font_subtitle, fill=DR_ACCENT)

    # Tagline
    tagline = "India's First Telegram Casino"
    tlw = draw.textlength(tagline, font=font_subtitle)
    draw.text(((W - tlw) // 2, 78), tagline, font=font_subtitle, fill=DR_TEXT_WHITE)

    # Lightning line
    lightning = "5 GAME MODES - WIN BIG"
    llw = draw.textlength(lightning, font=font_section)
    draw.text(((W - llw) // 2, 105), lightning, font=font_section, fill=DR_ORANGE)

    # Separator line
    draw.line([(50, 130), (W - 50, 130)], fill=DR_BORDER, width=1)

    # Game modes content
    y = 145
    line_height = 18
    padding = 40

    # 1. Classic Rush
    draw.text((padding, y), "1. Classic Rush", font=font_section, fill=DR_GOLD)
    y += line_height + 4
    draw.text((padding + 10, y), "Commands: /rush [1-6] [amount] or /dicerush [1-6] [amount]", font=font_text, fill=DR_TEXT_DIM)
    y += line_height + 2
    draw.text((padding + 10, y), "Rules: Pick a number 1-6, roll 6 dice. Win on 2+ matches!", font=font_text, fill=DR_TEXT_WHITE)
    y += line_height + 2
    draw.text((padding + 10, y), "Payouts: 2 Hits: 2.8x | 3 Hits: 5x | 4 Hits: 10x | 5 Hits: 20x | 6 Hits: 40x", font=font_text, fill=DR_GREEN)
    y += line_height + 8

    # 2. Odd/Even Rush
    draw.text((padding, y), "2. Odd/Even Rush", font=font_section, fill=DR_GOLD)
    y += line_height + 4
    draw.text((padding + 10, y), "Commands: /rush odd [amount] or /rush even [amount]", font=font_text, fill=DR_TEXT_DIM)
    y += line_height + 2
    draw.text((padding + 10, y), "Rules: Pick odd (1,3,5) or even (2,4,6). Win on 4+ matches!", font=font_text, fill=DR_TEXT_WHITE)
    y += line_height + 2
    draw.text((padding + 10, y), "Payouts: 4 Match: 1.8x | 5 Match: 4x | 6 Match: 10x", font=font_text, fill=DR_GREEN)
    y += line_height + 8

    # 3. High/Low Rush
    draw.text((padding, y), "3. High/Low Rush", font=font_section, fill=DR_GOLD)
    y += line_height + 4
    draw.text((padding + 10, y), "Commands: /rush high [amount] or /rush low [amount]", font=font_text, fill=DR_TEXT_DIM)
    y += line_height + 2
    draw.text((padding + 10, y), "Rules: Pick high (4,5,6) or low (1,2,3). Win on 4+ matches!", font=font_text, fill=DR_TEXT_WHITE)
    y += line_height + 2
    draw.text((padding + 10, y), "Payouts: 4 Match: 1.8x | 5 Match: 4x | 6 Match: 10x", font=font_text, fill=DR_GREEN)
    y += line_height + 8

    # 4. Rainbow Rush
    draw.text((padding, y), "4. Rainbow Rush", font=font_section, fill=DR_PURPLE)
    y += line_height + 4
    draw.text((padding + 10, y), "Commands: /rr [amount] or /rushrainbow [amount]", font=font_text, fill=DR_TEXT_DIM)
    y += line_height + 2
    draw.text((padding + 10, y), "Rules: No pick needed! Win if all 6 dice are DIFFERENT!", font=font_text, fill=DR_TEXT_WHITE)
    y += line_height + 2
    draw.text((padding + 10, y), "Jackpot-style | Ultra High Volatility! | Payout: WIN 55x", font=font_text, fill=DR_ORANGE)
    y += line_height + 8

    # 5. Blaze Rush
    draw.text((padding, y), "5. Blaze Rush (NEW!)", font=font_section, fill=DR_RED)
    y += line_height + 4
    draw.text((padding + 10, y), "Commands: /br [amount] or /blazerush [amount]", font=font_text, fill=DR_TEXT_DIM)
    y += line_height + 2
    draw.text((padding + 10, y), "Rules: No pick needed! Win if ALL 6 dice are same parity!", font=font_text, fill=DR_TEXT_WHITE)
    y += line_height + 2
    draw.text((padding + 10, y), "All Odd or All Even | High Volatility! | Payout: WIN 25x", font=font_text, fill=DR_ORANGE)
    y += line_height + 15

    # Separator
    draw.line([(50, y), (W - 50, y)], fill=DR_BORDER, width=1)
    y += 15

    # Footer
    footer = "All modes use Telegram's dice API | Provably Fair Gaming"
    fw = draw.textlength(footer, font=font_small)
    draw.text(((W - fw) // 2, y), footer, font=font_small, fill=DR_TEXT_DIM)

    # Bottom watermark
    draw.text((W - 120, H - 20), "DICE RUSH", font=font_small, fill=(40, 40, 80))

    # Save to BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def generate_limbo_image(
    target_multiplier: float,
    outcome: float,
    bet_amount: float,
    win: bool,
    profit: float = 0.0,
    player_username: str = None,
    bot_username: str = "Casino",
    game_id: str = None,
    currency: str = "USDT",
    player_profile_pic = None,  # PIL Image or None
    recent_players=None,  # list[{"name": str, "pic": PIL.Image|None}]
) -> BytesIO:
    """Render the Limbo result image — retro perspective grid + neon green glow.

    Mirrors ``example_designs/limbo_pil_image_template_design.png``.
    Layout:
      - Wide canvas, dark navy gradient with a retro vanishing-point grid
        floor + side perspective rails (purple/magenta).
      - Wireframe-mesh head avatar in the top-left.
      - Top-right: '@bot_username' large + '@player_username' small.
      - Two columns near the top:
          • TARGET (blue label) + a thin gold-bordered pill with the
            target multiplier and the game ID below it.
          • OUTCOME (green/red label) + the outcome multiplier (no pill)
            and the game ID below it.
      - Center: massive radial green/red glow with the outcome
        multiplier (e.g. ``3.00x``) huge in the middle.
      - Below the glow: a rounded green/red-bordered card with
        ``YOU WIN!`` / ``YOU LOSE`` + ``+/-$amount`` + ``Payout: $X``.
      - Recent-players rail: a rounded gray-bordered card listing up
        to three (avatar + display name) pairs from this chat's
        recent limbo plays.
      - Bottom info bar: ``Bet: $X CCY`` left, mountain glyph + ``LIMBO``
        center, ``@bot_username`` right.
      - Footer hairline ``Play Responsibly • Telegram Casino • limbo``.

    ``recent_players`` is an optional list of dicts with keys
    ``{"name": str, "pic": PIL.Image|None}`` describing the most recent
    limbo plays in the same chat (max 3). When ``None``, the rail just
    shows the current player.
    """
    from PIL import ImageFilter as _ImgFilter

    W, H = 1062, 980
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── PALETTE ─────────────────────────────────────────────
    BG_TOP = (4, 8, 28)
    BG_BOT = (10, 8, 36)
    GRID_COLOR = (40, 30, 100)
    GRID_HOT = (140, 60, 200)
    HEAD_COLOR = (140, 200, 240)
    GREEN = (90, 240, 130)
    GREEN_DIM = (40, 130, 70)
    RED = (255, 70, 80)
    GOLD = LIMBO_GOLD
    WHITE = LIMBO_TEXT_WHITE
    DIM = LIMBO_TEXT_DIM
    BLUE = (90, 200, 255)

    # ── BACKGROUND ──────────────────────────────────────────
    for yy in range(H):
        t = yy / H
        r = int(BG_TOP[0] + t * (BG_BOT[0] - BG_TOP[0]))
        g = int(BG_TOP[1] + t * (BG_BOT[1] - BG_TOP[1]))
        b = int(BG_TOP[2] + t * (BG_BOT[2] - BG_TOP[2]))
        draw.line([(0, yy), (W, yy)], fill=(r, g, b))

    # ── PERSPECTIVE GRID FLOOR ─────────────────────────────
    horizon_y = int(H * 0.30)
    vp_x = W // 2
    floor_top = horizon_y + 40
    floor_bot = H - 40
    # Vertical rails fanning out from the vanishing point.
    n_rails = 14
    for i in range(-n_rails, n_rails + 1):
        if i == 0:
            continue
        end_x = vp_x + i * (W // n_rails)
        col = GRID_HOT if abs(i) <= 2 else GRID_COLOR
        draw.line([(vp_x, horizon_y + 30), (end_x, floor_bot)],
                  fill=col, width=1)
    # Horizontal grid lines (perspective).
    n_horiz = 22
    for i in range(1, n_horiz + 1):
        # exponential perspective y so lines bunch up near horizon.
        u = i / n_horiz
        ly = int(floor_top + (floor_bot - floor_top) * (u ** 1.6))
        # x-extent grows with distance from horizon.
        extent = int((ly - floor_top) / (floor_bot - floor_top + 1) * (W // 2 + 200))
        x0 = max(0, vp_x - extent - 200)
        x1 = min(W, vp_x + extent + 200)
        col = GRID_HOT if i % 6 == 0 else GRID_COLOR
        draw.line([(x0, ly), (x1, ly)], fill=col, width=1)

    # Side wall lines (rough trapezoidal perspective).
    for off in range(0, 14):
        # left wall
        x_top = 40 + off * 12
        y_top = horizon_y + 20 + off * 6
        x_bot = 0 - off * 30
        y_bot = floor_bot
        draw.line([(x_top, y_top), (x_bot, y_bot)], fill=GRID_COLOR, width=1)
        # right wall
        x_top_r = W - 40 - off * 12
        x_bot_r = W + off * 30
        draw.line([(x_top_r, y_top), (x_bot_r, y_bot)], fill=GRID_COLOR, width=1)

    # Sparkles.
    rng = random.Random(123)
    for _ in range(80):
        sx, sy = rng.randint(0, W), rng.randint(0, H)
        br = rng.randint(40, 140)
        draw.ellipse([sx - 1, sy - 1, sx + 1, sy + 1], fill=(br, br, br + 25))

    # ── PROFILE AVATAR (top-left) ──────────────────────────
    # Composite player's Telegram profile pic into the top-left cell;
    # falls back to the wireframe head when no pic is available.
    h_cx, h_cy, h_rx, h_ry = 105, 130, 70, 90
    _paste_avatar_in_circle(
        img, draw, h_cx, h_cy, h_rx, h_ry,
        player_profile_pic, accent_rgba=HEAD_COLOR + (220,),
    )
    draw = ImageDraw.Draw(img)

    # ── TOP-RIGHT: bot username + player username ──────────
    f_bot = _limbo_get_font(28)
    f_user = _limbo_get_font(20)
    wm_text = f"@{bot_username}" if not bot_username.startswith("@") else bot_username
    wmw = draw.textlength(wm_text, font=f_bot)
    draw.text((W - wmw - 30, 28), wm_text, font=f_bot, fill=BLUE)
    if player_username:
        pu = f"@{player_username}" if not player_username.startswith("@") else player_username
        puw = draw.textlength(pu, font=f_user)
        draw.text((W - puw - 30, 70), pu, font=f_user, fill=DIM)

    # ── TARGET / OUTCOME COLUMNS ───────────────────────────
    f_lbl = _limbo_get_font(26)
    f_target_val = _limbo_get_font(40)
    f_outcome_val = _limbo_get_font(80)
    f_gid = _limbo_get_font(13)

    target_col_x = W // 2 - 160
    outcome_col_x = W // 2 + 160
    col_y = 90
    # TARGET label.
    tl = "TARGET"
    tlw = draw.textlength(tl, font=f_lbl)
    draw.text((target_col_x - tlw / 2, col_y), tl, font=f_lbl, fill=BLUE)
    # TARGET pill.
    tgt_str = f"{target_multiplier:.2f}x"
    tgw = draw.textlength(tgt_str, font=f_target_val)
    pill_w = max(int(tgw + 60), 200)
    pill_h = 56
    px0 = int(target_col_x - pill_w / 2)
    py0 = col_y + 36
    draw.rounded_rectangle([px0, py0, px0 + pill_w, py0 + pill_h],
                            radius=14, fill=(14, 22, 50),
                            outline=GOLD, width=2)
    draw.text((px0 + (pill_w - tgw) / 2, py0 + 4),
              tgt_str, font=f_target_val, fill=GOLD)
    # OUTCOME label.
    ol_color = GREEN if win else RED
    ol = "OUTCOME"
    olw = draw.textlength(ol, font=f_lbl)
    draw.text((outcome_col_x - olw / 2, col_y), ol, font=f_lbl, fill=ol_color)
    # OUTCOME value (top column, no pill).
    out_str = f"{outcome:.2f}x"
    outw = draw.textlength(out_str, font=f_outcome_val)
    draw.text((outcome_col_x - outw / 2, col_y + 24),
              out_str, font=f_outcome_val, fill=ol_color)
    # Game ID below both columns.
    if game_id:
        gid_str = str(game_id)
        gidw = draw.textlength(gid_str, font=f_gid)
        draw.text((target_col_x - gidw / 2, py0 + pill_h + 10),
                  gid_str, font=f_gid, fill=DIM)
        draw.text((outcome_col_x - gidw / 2, py0 + pill_h + 10),
                  gid_str, font=f_gid, fill=DIM)

    # ── CENTER GLOW + HUGE MULTIPLIER ──────────────────────
    glow_cx = W // 2
    glow_cy = int(H * 0.46)
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    glow_color = GREEN if win else RED
    # Three layered ellipses with falling alpha.
    for r, alpha in [(280, 160), (220, 110), (160, 80)]:
        gd.ellipse(
            [glow_cx - int(r * 1.15), glow_cy - r,
             glow_cx + int(r * 1.15), glow_cy + r],
            fill=(glow_color[0], glow_color[1], glow_color[2], alpha),
        )
    glow_layer = glow_layer.filter(_ImgFilter.GaussianBlur(radius=24))
    img.alpha_composite(glow_layer)
    draw = ImageDraw.Draw(img)
    # Huge outcome text in the center of the glow.
    f_huge = _limbo_get_font(150)
    big_str = f"{outcome:.2f}x"
    bsw = draw.textlength(big_str, font=f_huge)
    # subtle text-glow underlay.
    text_glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    tgd = ImageDraw.Draw(text_glow)
    tgd.text((glow_cx - bsw / 2, glow_cy - 110), big_str,
             font=f_huge, fill=(glow_color[0], glow_color[1], glow_color[2], 220))
    text_glow = text_glow.filter(_ImgFilter.GaussianBlur(radius=8))
    img.alpha_composite(text_glow)
    draw = ImageDraw.Draw(img)
    draw.text((glow_cx - bsw / 2, glow_cy - 110), big_str,
              font=f_huge, fill=WHITE)

    # ── RESULT CARD (YOU WIN/LOSE) ─────────────────────────
    rcw = 460
    rch = 130
    rcx0 = (W - rcw) // 2
    rcy0 = glow_cy + 90
    # outer subtle glow.
    rg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rgd = ImageDraw.Draw(rg)
    rgd.rounded_rectangle([rcx0 - 8, rcy0 - 8, rcx0 + rcw + 8, rcy0 + rch + 8],
                          radius=18, outline=(glow_color[0], glow_color[1], glow_color[2], 150), width=4)
    rg = rg.filter(_ImgFilter.GaussianBlur(radius=6))
    img.alpha_composite(rg)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([rcx0, rcy0, rcx0 + rcw, rcy0 + rch],
                            radius=16, fill=(8, 20, 14) if win else (28, 10, 12),
                            outline=glow_color, width=2)
    # YOU WIN / YOU LOSE
    f_rh = _limbo_get_font(34)
    title = "YOU WIN!" if win else "YOU LOSE"
    titw = draw.textlength(title, font=f_rh)
    draw.text((rcx0 + (rcw - titw) / 2, rcy0 + 14),
              title, font=f_rh, fill=WHITE)
    # +/- amount
    f_ra = _limbo_get_font(34)
    if win:
        amt_str = f"+${profit:,.2f}"
        amt_color = GREEN
    else:
        amt_str = f"-${bet_amount:,.2f}"
        amt_color = RED
    aw = draw.textlength(amt_str, font=f_ra)
    draw.text((rcx0 + (rcw - aw) / 2, rcy0 + 54),
              amt_str, font=f_ra, fill=amt_color)
    # Payout (only when win)
    f_pp = _limbo_get_font(18)
    if win:
        payout = bet_amount + profit
        pp_str = f"Payout: ${payout:,.2f}"
        ppw = draw.textlength(pp_str, font=f_pp)
        # coin glyph.
        cglyph_x = rcx0 + (rcw + ppw) / 2 + 14
        cglyph_y = rcy0 + 96 + 4
        draw.ellipse([cglyph_x, cglyph_y, cglyph_x + 18, cglyph_y + 18],
                     fill=GREEN_DIM, outline=GREEN, width=1)
        f_cg = _limbo_get_font(13)
        draw.text((cglyph_x + 5, cglyph_y + 1), "$", font=f_cg, fill=WHITE)
        draw.text((rcx0 + (rcw - ppw) / 2 - 14, rcy0 + 96),
                  pp_str, font=f_pp, fill=DIM)

    # ── RECENT PLAYERS RAIL ────────────────────────────────
    rail_w = 580
    rail_h = 110
    rail_x0 = (W - rail_w) // 2
    rail_y0 = rcy0 + rch + 36
    draw.rounded_rectangle([rail_x0, rail_y0, rail_x0 + rail_w, rail_y0 + rail_h],
                            radius=18, fill=(18, 22, 48), outline=(60, 70, 110), width=2)
    # Build rail entries from recent_players (or fallback to single current player).
    if recent_players:
        entries = list(recent_players)[:3]
    else:
        entries = [{
            "name": player_username or "Player",
            "pic": player_profile_pic,
        }]
    f_pname = _limbo_get_font(20)
    av_r = 22
    # Place 2 entries on the first row, 1 on the second when 3 are present.
    pad_x = rail_x0 + 18
    pad_y = rail_y0 + 14
    cell_w = (rail_w - 36) // 2
    for idx, ent in enumerate(entries):
        col = idx % 2
        row = idx // 2
        cx0 = pad_x + col * cell_w
        cy0 = pad_y + row * 42
        avx = cx0 + 4
        avy = cy0 + 4
        # Avatar circle.
        if ent.get("pic") and isinstance(ent["pic"], Image.Image):
            try:
                sz = av_r * 2
                src = ent["pic"].convert("RGBA").resize((sz, sz), Image.Resampling.LANCZOS)
                mask = Image.new("L", (sz, sz), 0)
                ImageDraw.Draw(mask).ellipse([0, 0, sz - 1, sz - 1], fill=255)
                img.paste(src, (avx, avy), mask)
                draw.ellipse([avx, avy, avx + sz, avy + sz],
                             outline=GOLD if idx == 0 else (110, 130, 170), width=2)
            except Exception:
                draw.ellipse([avx, avy, avx + av_r * 2, avy + av_r * 2],
                             fill=(20, 28, 50), outline=(110, 130, 170), width=2)
        else:
            draw.ellipse([avx, avy, avx + av_r * 2, avy + av_r * 2],
                         fill=(20, 28, 50), outline=(110, 130, 170), width=2)
        # Name.
        nm = (ent.get("name") or "Player")
        nm = nm if not nm.startswith("@") else nm[1:]
        nm = nm[:14] + ".." if len(nm) > 14 else nm
        draw.text((avx + av_r * 2 + 14, avy + 8),
                  nm, font=f_pname, fill=WHITE)

    # ── BOTTOM INFO BAR ────────────────────────────────────
    bar_y = H - 80
    bar_h = 50
    draw.rounded_rectangle([16, bar_y, W - 16, bar_y + bar_h],
                            radius=12, fill=(10, 16, 36), outline=(40, 50, 90), width=1)
    f_bar = _limbo_get_font(20)
    # Bet (left).
    bet_str = f"Bet: ${bet_amount:.2f} {currency}"
    draw.text((36, bar_y + (bar_h - 24) / 2),
              bet_str, font=f_bar, fill=WHITE)
    # Center: mountain glyph + LIMBO.
    lbl = "LIMBO"
    lw = draw.textlength(lbl, font=f_bar)
    glyph_x = (W - lw) // 2 - 32
    glyph_y = bar_y + bar_h // 2
    # tiny mountain (triangle).
    draw.polygon(
        [(glyph_x, glyph_y + 12),
         (glyph_x + 12, glyph_y - 10),
         (glyph_x + 24, glyph_y + 12)],
        fill=GOLD,
    )
    draw.text(((W - lw) / 2, bar_y + (bar_h - 24) / 2),
              lbl, font=f_bar, fill=GOLD)
    # Right: bot username + diamond.
    rt = f"@{bot_username}" if not bot_username.startswith("@") else bot_username
    rtw = draw.textlength(rt, font=f_bar)
    draw.text((W - rtw - 60, bar_y + (bar_h - 24) / 2),
              rt, font=f_bar, fill=BLUE)
    dx, dy = W - 38, bar_y + bar_h // 2
    draw.polygon([(dx, dy - 9), (dx + 9, dy), (dx, dy + 9), (dx - 9, dy)],
                 fill=BLUE)

    # ── FOOTER LINE ────────────────────────────────────────
    f_foot = _limbo_get_font(14)
    foot = "Play Responsibly  •  Telegram Casino  •  limbo"
    fw = draw.textlength(foot, font=f_foot)
    draw.text(((W - fw) / 2, H - 22), foot, font=f_foot, fill=DIM)

    # Save
    out = img.convert("RGB")
    buf = BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

async def generate_history_image(user_id: int, context, page: int = 0):
    """Generate a history template image for the user's game history."""
    try:
        stats = user_stats.get(user_id, {})
        userinfo = stats.get('userinfo', {})
        first_name = userinfo.get('first_name', 'User')
        username = userinfo.get('username', 'N/A')
        total_bets = stats.get('bets', {}).get('count', 0)
        total_wins = stats.get('bets', {}).get('wins', 0)
        total_losses = stats.get('bets', {}).get('losses', 0)
        total_wagered = stats.get('bets', {}).get('amount', 0.0)

        # Get game session IDs in reverse order (newest first)
        game_ids = list(reversed(stats.get('game_sessions', [])))
        total_games = len(game_ids)
        start_idx = page * HISTORY_ITEMS_PER_PAGE
        page_games = game_ids[start_idx:start_idx + HISTORY_ITEMS_PER_PAGE]

        # Get bot username
        global _bot_username_cache
        if _bot_username_cache is None:
            bot_info = await context.bot.get_me()
            _bot_username_cache = bot_info.username
        bot_username = _bot_username_cache

        # Profile pic
        profile_pic = await _get_cached_profile_picture(context, user_id)

        # Pre-compute per-row bet/profit strings in the user's display
        # currency so the PIL renderer doesn't need to know about FX rates.
        row_data = []
        for gid in page_games:
            game = game_sessions.get(gid, {}) or {}
            bet_amount = game.get('bet_amount', 0.0)
            multiplier = game.get('multiplier', 0)
            is_win = game.get('win', False)
            profit = bet_amount * multiplier - bet_amount if multiplier else -bet_amount
            row_data.append({
                "gid": gid,
                "game_type": game.get('game_type', 'unknown').replace('_', ' ').title(),
                "bet_amount": bet_amount,
                "bet_str": format_compact_for_user(user_id, bet_amount),
                "multiplier": multiplier,
                "profit": profit,
                "profit_str": f"{'+' if profit >= 0 else '-'}{format_compact_for_user(user_id, abs(profit))}",
                "win": is_win,
                "status": game.get('status', 'unknown'),
            })

        wagered_str = format_compact_for_user(user_id, total_wagered)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _image_executor,
            _render_history_sync,
            {
                "user_id": user_id,
                "first_name": first_name,
                "username": username,
                "total_bets": total_bets,
                "total_wins": total_wins,
                "total_losses": total_losses,
                "total_wagered": total_wagered,
                "total_wagered_str": wagered_str,
                "total_games": total_games,
                "page": page,
                "page_games": page_games,
                "row_data": row_data,
                "bot_username": bot_username,
            },
            profile_pic,
        )
        return result
    except Exception as e:
        logging.error(f"Error generating history image for {user_id}: {e}")
        return None

def _render_history_sync(data: dict, profile_pic):
    """Render history template image. Runs in ThreadPoolExecutor."""
    try:
        # Create image (1000x600)
        W, H = 1000, 600
        img = Image.new('RGBA', (W, H), (15, 25, 35, 255))
        draw = ImageDraw.Draw(img)

        # Load fonts
        try:
            font_big = ImageFont.truetype(DASHBOARD_FONT_PATH, 32)
            font_med = ImageFont.truetype(DASHBOARD_FONT_PATH, 22)
            font_small = ImageFont.truetype(DASHBOARD_FONT_PATH, 16)
            font_tiny = ImageFont.truetype(DASHBOARD_FONT_PATH, 13)
        except Exception:
            font_big = ImageFont.load_default()
            font_med = font_big
            font_small = font_big
            font_tiny = font_big

        # Starfield background dots
        import random as _rng
        _rng.seed(42)  # Consistent star positions
        for _ in range(80):
            sx, sy = _rng.randint(0, W), _rng.randint(0, H)
            draw.ellipse((sx, sy, sx+2, sy+2), fill=(255, 255, 255, _rng.randint(30, 80)))

        # Title
        draw.text((350, 15), "Game History", fill=(255, 215, 0), font=font_big)

        # Bot branding
        draw.text((750, 18), f"@playcsino", fill=(255, 215, 0), font=font_med)
        draw.text((750, 45), "Telegram Casino", fill=(0, 255, 255), font=font_tiny)

        # Profile section
        if profile_pic:
            try:
                pic = profile_pic.resize((80, 80), Image.Resampling.LANCZOS)
                mask = create_circular_mask((80, 80))
                if pic.mode != 'RGBA':
                    pic = pic.convert('RGBA')
                img.paste(pic, (30, 60), mask)
            except Exception:
                draw.ellipse((30, 60, 110, 140), fill=(42, 75, 110))
        else:
            draw.ellipse((30, 60, 110, 140), fill=(42, 75, 110))
            draw.text((55, 85), data['first_name'][:2].upper(), fill=(255, 255, 255), font=font_med)

        # User info
        draw.text((130, 65), data['first_name'][:15], fill=(255, 255, 255), font=font_med)
        draw.text((130, 95), f"@{data['username']}", fill=(180, 180, 180), font=font_small)
        draw.text((130, 120), str(data['user_id']), fill=(200, 200, 200), font=font_tiny)

        # Stats boxes
        y_stats = 165
        box_w = 220
        box_h = 55
        gap = 15

        wagered_disp = data.get('total_wagered_str') or f"${data['total_wagered']:,.2f}"
        stats_data = [
            ("TOTAL BETS", str(data['total_bets']), (0, 231, 1)),
            ("WINS", str(data['total_wins']), (34, 197, 94)),
            ("LOSSES", str(data['total_losses']), (239, 68, 68)),
            ("WAGERED", wagered_disp, (255, 215, 0)),
        ]

        for i, (label, value, color) in enumerate(stats_data):
            x = 30 + i * (box_w + gap)
            # Box background
            draw.rounded_rectangle((x, y_stats, x + box_w, y_stats + box_h), radius=8, fill=(26, 44, 61))
            draw.rounded_rectangle((x, y_stats, x + box_w, y_stats + box_h), radius=8, outline=(37, 58, 78))
            # Label
            draw.text((x + 10, y_stats + 5), label, fill=(90, 106, 122), font=font_tiny)
            # Value
            draw.text((x + 10, y_stats + 24), value, fill=color, font=font_med)

        # Game history entries
        y_games = 240
        page_games = data.get('page_games', [])
        page = data.get('page', 0)
        total_games = data.get('total_games', 0)

        draw.text((30, y_games), f"Recent Games (Page {page + 1})", fill=(176, 196, 216), font=font_small)
        y_games += 30

        if not page_games:
            draw.text((30, y_games + 20), "No games found. Start playing to see your history!", fill=(90, 106, 122), font=font_small)
        else:
            # Table header
            draw.text((30, y_games), "#", fill=(90, 106, 122), font=font_tiny)
            draw.text((70, y_games), "GAME", fill=(90, 106, 122), font=font_tiny)
            draw.text((280, y_games), "BET", fill=(90, 106, 122), font=font_tiny)
            draw.text((430, y_games), "MULT", fill=(90, 106, 122), font=font_tiny)
            draw.text((560, y_games), "PROFIT", fill=(90, 106, 122), font=font_tiny)
            draw.text((720, y_games), "RESULT", fill=(90, 106, 122), font=font_tiny)
            draw.text((850, y_games), "ID", fill=(90, 106, 122), font=font_tiny)
            y_games += 22

            # Prefer pre-formatted per-row strings (display currency) if
            # the caller supplied them.
            row_data = data.get('row_data') or []
            for idx, gid in enumerate(page_games):
                # Pre-computed row (display-currency aware) if available.
                row = row_data[idx] if idx < len(row_data) else None
                if row is None:
                    game = game_sessions.get(gid, {})
                    if not game:
                        continue
                    bet_amount = game.get('bet_amount', 0.0)
                    multiplier = game.get('multiplier', 0)
                    is_win = game.get('win', False)
                    profit = bet_amount * multiplier - bet_amount if multiplier else -bet_amount
                    game_type = game.get('game_type', 'unknown').replace('_', ' ').title()
                    bet_str = f"${bet_amount:.2f}"
                    profit_str = f"{'+'if profit>=0 else ''}${profit:.2f}"
                else:
                    bet_amount = row['bet_amount']
                    multiplier = row['multiplier']
                    is_win = row['win']
                    profit = row['profit']
                    game_type = row['game_type']
                    bet_str = row['bet_str']
                    profit_str = row['profit_str']

                game_num = total_games - (page * HISTORY_ITEMS_PER_PAGE + idx)

                row_y = y_games + idx * 28
                if idx % 2 == 0:
                    draw.rectangle((25, row_y - 2, W - 25, row_y + 24), fill=(20, 35, 50))

                draw.text((30, row_y), f"#{game_num}", fill=(176, 196, 216), font=font_tiny)
                draw.text((70, row_y), game_type[:20], fill=(255, 255, 255), font=font_tiny)
                draw.text((280, row_y), bet_str, fill=(176, 196, 216), font=font_tiny)
                mult_color = (0, 231, 1) if multiplier >= 1 else (239, 68, 68)
                draw.text((430, row_y), f"{multiplier:.2f}x" if multiplier else "N/A", fill=mult_color, font=font_tiny)
                profit_color = (0, 231, 1) if profit >= 0 else (239, 68, 68)
                draw.text((560, row_y), profit_str, fill=profit_color, font=font_tiny)
                result_text = "WIN" if is_win else "LOSS"
                result_color = (0, 231, 1) if is_win else (239, 68, 68)
                draw.text((720, row_y), result_text, fill=result_color, font=font_tiny)
                draw.text((850, row_y), str(gid)[:10], fill=(90, 106, 122), font=font_tiny)

        # Footer
        draw.text((350, H - 30), "Play responsibly | @playcsino", fill=(90, 106, 122), font=font_tiny)

        # Convert to bytes
        output = BytesIO()
        img.convert('RGB').save(output, format='JPEG', quality=90)
        output.seek(0)
        return output
    except Exception as e:
        logging.error(f"History image render error: {e}")
        return None

@check_banned
@check_maintenance
## NEW FEATURE - /level and /levelall commands ##
def create_progress_bar(progress, total, length=10):
    """Creates a text-based progress bar."""
    if total <= 0:
        return "▬" * length
    filled_length = min(length, int(length * progress // total))
    bar = '■' * filled_length + '□' * (length - filled_length)
    return bar

def generate_surprise_drop_image(code: str, amount: float, wager_req: float, bot_username: str, claimed_by: str = None) -> BytesIO:
    """Generate a premium PIL image for surprise code drop."""
    W, H = 760, 500
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Deep navy gradient background
    for y_pos in range(H):
        t = y_pos / H
        r = int(4  + t * 8)
        g = int(8  + t * 10)
        b = int(24 + t * 16)
        draw.line([(0, y_pos), (W, y_pos)], fill=(r, g, b))

    # Star particles
    _rng = random.Random(17)
    for _ in range(70):
        sx, sy = _rng.randint(0, W), _rng.randint(0, H)
        br = _rng.randint(60, 180)
        draw.ellipse([sx-1,sy-1,sx+1,sy+1], fill=(br,br,br+25))

    # Double border — gold outer, blue inner
    draw.rounded_rectangle([2, 2, W-3, H-3], radius=20, outline=(255, 195, 50), width=3)
    draw.rounded_rectangle([6, 6, W-7, H-7], radius=17, outline=(40, 100, 200), width=1)

    try:
        f_title    = ImageFont.truetype(DASHBOARD_FONT_PATH, 34)
        f_subtitle = ImageFont.truetype(DASHBOARD_FONT_PATH, 18)
        f_code     = ImageFont.truetype(DASHBOARD_FONT_PATH, 52)
        f_amount   = ImageFont.truetype(DASHBOARD_FONT_PATH, 30)
        f_info     = ImageFont.truetype(DASHBOARD_FONT_PATH, 16)
        f_small    = ImageFont.truetype(DASHBOARD_FONT_PATH, 14)
        f_bot      = ImageFont.truetype(DASHBOARD_FONT_PATH, 13)
    except Exception:
        f_title = f_subtitle = f_code = f_amount = f_info = f_small = f_bot = ImageFont.load_default()

    # Bot branding — top right
    bot_text = f"@{bot_username}"
    bw = draw.textlength(bot_text, font=f_bot)
    draw.text((W - bw - 18, 14), bot_text, fill=(160, 200, 255), font=f_bot)
    cw = draw.textlength("Telegram Casino", font=f_small)
    draw.text((W - cw - 18, 32), "Telegram Casino", fill=(100, 140, 200), font=f_small)

    # Gift icon — top left
    draw.text((22, 14), "\U0001F381", fill=(255, 215, 0), font=f_title)

    # Title
    title = "SURPRISE DROP!"
    tw = draw.textlength(title, font=f_title)
    # Shadow + text
    draw.text(((W-tw)/2 + 2, 72), title, fill=(150, 120, 15), font=f_title)
    draw.text(((W-tw)/2, 70), title, fill=(255, 210, 50), font=f_title)

    # Gold separator line
    draw.line([(40, 114), (W-40, 114)], fill=(255, 195, 50), width=2)

    # Amount
    amt_text = f"${amount:.2f}  BONUS"
    aw = draw.textlength(amt_text, font=f_amount)
    draw.text(((W-aw)/2, 126), amt_text, fill=(60, 220, 120), font=f_amount)

    # Instruction
    instr = "Use the code below to claim this bonus:"
    iw = draw.textlength(instr, font=f_info)
    draw.text(((W-iw)/2, 172), instr, fill=(190, 200, 225), font=f_info)

    # Code box — prominent card
    code_claim = f"/claim {code}"
    ccode_w = draw.textlength(code_claim, font=f_code)
    pad = 28
    bx1 = (W - ccode_w)/2 - pad
    bx2 = (W + ccode_w)/2 + pad
    if claimed_by:
        box_fill = (30, 10, 12)
        box_outline = (200, 50, 50)
    else:
        box_fill = (10, 22, 50)
        box_outline = (255, 195, 50)
    draw.rounded_rectangle([bx1, 198, bx2, 278], radius=14, fill=box_fill, outline=box_outline, width=2)
    code_color = (200, 200, 210) if claimed_by else (255, 255, 255)
    draw.text(((W-ccode_w)/2, 204), code_claim, fill=code_color, font=f_code)
    # Strike-through when claimed
    if claimed_by:
        draw.line([(bx1+12, 240), (bx2-12, 240)], fill=(220, 50, 50), width=4)

    # Wager requirement
    wager_text = f"\u26A0\uFE0F  Wager requirement: ${wager_req:.2f} in last 30 days"
    ww = draw.textlength(wager_text, font=f_info)
    draw.text(((W-ww)/2, 295), wager_text, fill=(255, 175, 70), font=f_info)

    note_text = "Claimed amount has 2\u00D7 wager requirement before withdrawal"
    nw = draw.textlength(note_text, font=f_small)
    draw.text(((W-nw)/2, 322), note_text, fill=(160, 165, 195), font=f_small)

    # Status banner
    if claimed_by:
        status_text = f"CLAIMED  by @{claimed_by}"
        status_color = (255, 65, 65)
        status_bg = (40, 10, 12)
    else:
        status_text = "UNCLAIMED  \u2014  Be first to grab it!"
        status_color = (60, 220, 110)
        status_bg = (8, 36, 18)

    sw = draw.textlength(status_text, font=f_subtitle)
    sbx1 = (W-sw)/2 - 22
    sbx2 = (W+sw)/2 + 22
    draw.rounded_rectangle([sbx1, 352, sbx2, 392], radius=12,
                            fill=status_bg, outline=status_color, width=2)
    draw.text(((W-sw)/2, 358), status_text, fill=status_color, font=f_subtitle)

    # Bottom line + footer
    draw.line([(40, 414), (W-40, 414)], fill=(60, 90, 140), width=1)
    footer = "One claim per code  \u2022  First come, first served"
    fw = draw.textlength(footer, font=f_small)
    draw.text(((W-fw)/2, 428), footer, fill=(100, 120, 160), font=f_small)

    # Corner sparkles
    draw.text((20, H-44), "\u2728", fill=(255, 210, 50), font=f_info)
    draw.text((W-46, H-44), "\u2728", fill=(255, 210, 50), font=f_info)

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def generate_7up_help_image() -> BytesIO:
    """Generate PIL help image for 7Up7Down game."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    W, H = 900, 1200
    BG = (15, 10, 35)  # Dark purple-black
    ACCENT = (255, 215, 0)  # Gold
    WHITE = (240, 240, 250)
    DIM = (160, 160, 190)
    GREEN = (0, 220, 100)
    RED = (255, 60, 60)
    BLUE = (60, 140, 255)
    PURPLE = (180, 80, 255)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Font loader
    def _f(size):
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    pass
        return ImageFont.load_default()

    y = 30

    # Title
    title = "7 UP DOWN"
    tw = draw.textlength(title, font=_f(48))
    draw.text(((W - tw) / 2, y), title, fill=ACCENT, font=_f(48))
    y += 65

    subtitle = "@playcsino  -  Telegram Casino"
    sw = draw.textlength(subtitle, font=_f(22))
    draw.text(((W - sw) / 2, y), subtitle, fill=DIM, font=_f(22))
    y += 50

    # Fire line
    fire = "WIN UP TO 200X"
    fw = draw.textlength(fire, font=_f(32))
    draw.text(((W - fw) / 2, y), fire, fill=RED, font=_f(32))
    y += 55

    # Usage
    draw.text((40, y), "Usage Command", fill=BLUE, font=_f(26))
    y += 35
    draw.text((40, y), "/7up [amount] [option]", fill=WHITE, font=_f(22))
    y += 45

    # Separator
    draw.line([(40, y), (W - 40, y)], fill=(60, 60, 100), width=2)
    y += 20

    # 2 Dice section
    draw.text((40, y), "Standard (2 Dice)", fill=ACCENT, font=_f(28))
    y += 40

    items_2dice = [
        ("High (8-12)", "2.23x", GREEN), ("Low (2-6)", "2.23x", GREEN),
        ("7 (Exact 7)", "5.58x", PURPLE), ("Odd / Even", "1.92x", WHITE),
        ("Pair (Double)", "5.58x", PURPLE), ("Low+ (2-4)", "5.58x", PURPLE),
        ("Mid (5-7)", "2.23x", GREEN), ("High- (8-10)", "2.79x", GREEN),
        ("High+ (11-12)", "11.16x", RED), ("Combo (1,6)", "16.74x", RED),
    ]

    for name, mult, color in items_2dice:
        draw.text((60, y), f"  {name}:", fill=DIM, font=_f(20))
        mw = draw.textlength(mult, font=_f(20))
        draw.text((W - 60 - mw, y), mult, fill=color, font=_f(20))
        y += 30

    y += 15
    draw.line([(40, y), (W - 40, y)], fill=(60, 60, 100), width=2)
    y += 20

    # 3 Dice section
    draw.text((40, y), "Three Dice Mode", fill=ACCENT, font=_f(28))
    y += 40

    items_3dice = [
        ("3Low (3-8)", "3.59x", GREEN), ("3Mid (9-12)", "1.93x", WHITE),
        ("3High (13-18)", "3.59x", GREEN), ("AllDiff (no repeat)", "1.67x", WHITE),
        ("Triple (any)", "33.48x", RED), ("AllOdd/Even", "7.44x", PURPLE),
        ("2Kind (any pair)", "2.09x", GREEN), ("Seq3 (straight)", "8.37x", PURPLE),
    ]

    for name, mult, color in items_3dice:
        draw.text((60, y), f"  {name}:", fill=DIM, font=_f(20))
        mw = draw.textlength(mult, font=_f(20))
        draw.text((W - 60 - mw, y), mult, fill=color, font=_f(20))
        y += 30

    y += 15
    draw.line([(40, y), (W - 40, y)], fill=(60, 60, 100), width=2)
    y += 20

    # Specific Combos
    draw.text((40, y), "Specific Combo Jackpots", fill=ACCENT, font=_f(28))
    y += 40

    combos = [
        ("Distinct triple (e.g., 1,2,3)", "33.48x", PURPLE),
        ("Pair + kicker (e.g., 6,6,5)", "66.96x", RED),
        ("Specific triple (e.g., 6,6,6)", "200.88x", RED),
    ]

    for name, mult, color in combos:
        draw.text((60, y), f"  {name}:", fill=DIM, font=_f(20))
        mw = draw.textlength(mult, font=_f(20))
        draw.text((W - 60 - mw, y), mult, fill=color, font=_f(20))
        y += 30

    y += 15
    draw.line([(40, y), (W - 40, y)], fill=(60, 60, 100), width=2)
    y += 20

    # Pro Tips
    draw.text((40, y), "Pro Tips", fill=ACCENT, font=_f(28))
    y += 40
    tips = [
        "/7up 100 seq3",
        "/7up 50 1,2,3",
        "/7up 10 6,6,6",
        "/7up 25 high",
        "/7up all 7",
    ]
    for tip in tips:
        draw.text((60, y), f"Try: {tip}", fill=DIM, font=_f(20))
        y += 28

    y += 20
    # House edge note
    draw.text((40, y), "House Edge: 7%", fill=(120, 120, 140), font=_f(18))

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

