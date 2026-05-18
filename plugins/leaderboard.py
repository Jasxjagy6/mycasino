"""Auto-split from bot.py — plugins.leaderboard."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

# ── PIL leaderboard rendering (moved from core/dashboards.py so /reload
#    leaderboard can hot-swap the rendering without touching core). ──

async def generate_leaderboard_image(context, period='all_time', viewing_user_id=None):
    """Generate leaderboard template image with user's actual rank."""
    try:
        global _bot_username_cache
        if _bot_username_cache is None:
            bot_info = await context.bot.get_me()
            _bot_username_cache = bot_info.username
        bot_username = _bot_username_cache

        # Rebuild leaderboards to ensure fresh data
        _rebuild_leaderboards()

        # Map period to data key and title
        period_map = {
            'all_time': ('all_time', 'All-Time Top Wagered'),
            'weekly': ('weekly', 'Weekly Top Wagered'),
            'monthly': ('monthly', 'Monthly Top Wagered'),
            'highest_wins': ('highest_wins', 'Highest Wins - This Month'),
        }
        data_key, section_title = period_map.get(period, ('all_time', 'All-Time Top Wagered'))
        data = leaderboard_data.get(data_key, [])

        entries = []
        top_uids = []
        if data_key == 'highest_wins':
            for i, (uid, uname, wamt, gtype, ts) in enumerate(data[:10]):
                entries.append({"rank": i + 1, "username": get_privacy_display_name(uid, uname), "value": wamt})
                top_uids.append(uid)
        else:
            for i, (uid, uname, wagered) in enumerate(data[:10]):
                entries.append({"rank": i + 1, "username": get_privacy_display_name(uid, uname), "value": wagered})
                top_uids.append(uid)

        # Fetch real Telegram avatars for the top-3 (best-effort) so the
        # hexagonal podium circles aren't all blank/wireframe placeholders.
        top_avatars = {}
        for rank_idx, uid in enumerate(top_uids[:3], start=1):
            try:
                pic = await _get_cached_profile_picture(context, uid)
                if pic is not None:
                    top_avatars[rank_idx] = pic
            except Exception:
                pass

        # Calculate viewing user's rank and wagered amount
        user_rank = None
        user_wagered = 0.0
        if viewing_user_id and viewing_user_id in user_stats:
            stats = user_stats[viewing_user_id]
            if data_key == 'weekly':
                user_wagered = stats.get('weekly_stats', {}).get('weighted_wager', 0.0)
            elif data_key == 'monthly':
                user_wagered = stats.get('monthly_stats', {}).get('weighted_wager', 0.0)
            elif data_key == 'highest_wins':
                user_wagered = stats.get('last_win', 0)
            else:
                user_wagered = stats.get('bets', {}).get('amount', 0.0)

            # Find rank in top 10
            for i, entry in enumerate(entries):
                if entry.get('uid') == viewing_user_id or any(
                    d[0] == viewing_user_id for d in [data[i]] if i < len(data)
                ):
                    user_rank = i + 1
                    break

            # If not in top 10, calculate approximate rank
            if user_rank is None and user_wagered > 0:
                rank = 1
                for _, _, val, *rest in data:
                    if val > user_wagered:
                        rank += 1
                user_rank = rank

        loop = asyncio.get_running_loop()
        # Use functools.partial so the kwargs (notably ``top_avatars``) are
        # forwarded into the executor without relying on positional ordering.
        from functools import partial as _lb_partial

        # Render the amounts in the VIEWING user's display currency
        # (compact-formatted). Pinned to that user so everyone sees the
        # leaderboard in whatever unit they chose.
        if viewing_user_id is not None:
            def _leader_formatter(v, _uid=viewing_user_id):
                return format_compact_for_user(_uid, v)
            lb_value_formatter = _leader_formatter
        else:
            lb_value_formatter = None

        result = await loop.run_in_executor(
            _image_executor,
            _lb_partial(
                _render_leaderboard_sync,
                entries,
                bot_username,
                section_title,
                user_rank,
                user_wagered,
                value_formatter=lb_value_formatter,
                top_avatars=top_avatars,
            ),
        )
        return result
    except Exception as e:
        logging.error(f"Error generating leaderboard image: {e}")
        return None

def _render_leaderboard_sync(entries, bot_username, section_title, user_rank=None, user_wagered=0.0,
                             value_formatter=None, your_rank_label="YOUR POSITION",
                             your_value_label="Total Wagered",
                             top_avatars=None):
    """Render the leaderboard card — hexagonal-podium design that mirrors
    ``example_designs/leaderboard_pil_design_template.png``.

    Layout (top→bottom):
      • Dark blue header strip with `LEADERBOARD` centered, `@bot_username`
        + `CASINO` subtitle in the top-right.
      • Section title pill (e.g. "All-Time Top Wagered").
      • Three hexagonal pedestals in 3D perspective. #2 is left (silver),
        #1 is center+taller (gold), #3 is right (bronze). Each pedestal has
        a coloured light-beam shooting up, a circular avatar floating above
        in the beam, and the user's name + value over the beam.
      • "RANKS 4 — 10" separator.
      • Left: "YOUR POSITION" card (rounded blue-bordered).
      • Right: rows for ranks 4–10, alternating filled/empty.
      • Footer: "Play Responsibly • Telegram Casino", diamond glyph
        bottom-right.

    `top_avatars` is an optional dict mapping ``rank → PIL.Image`` (1, 2 or 3)
    so the top-3 podium circles can show real Telegram avatars. Falls back
    to the wireframe-mask placeholder when an avatar is not provided.
    `value_formatter` formats the numeric `entry['value']` (defaults to USD).
    """
    if value_formatter is None:
        value_formatter = lambda v: f"${v:,.2f}"
    try:
        # Larger canvas to fit the hexagonal podium + ranks 4-10 + your-position card.
        W, H = 850, 1180
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # ── PALETTE ──────────────────────────────────────────────
        C_BG_TOP    = (5,  8,  28)
        C_BG_MID    = (10, 12, 36)
        C_BG_BOT    = (18, 10, 42)
        C_HEADER    = (10, 20, 56)
        C_CARD      = (10, 20, 44)
        C_CARD_ALT  = (7,  15, 34)
        C_BORDER    = (28, 56, 110)
        C_GOLD      = (255, 200, 60)
        C_GOLD_DIM  = (160, 120, 20)
        C_SILVER    = (210, 220, 235)
        C_SILVER_DIM= (110, 125, 150)
        C_BRONZE    = (220, 145, 80)
        C_BRONZE_DIM= (130, 85,  40)
        C_BLUE      = (90, 200, 255)
        C_BLUE_DIM  = (35, 110, 200)
        C_GREEN     = (60, 230, 130)
        C_WHITE     = (240, 245, 255)
        C_MUTED     = (130, 145, 180)
        C_ACCENT    = (25, 60, 120)

        MEDAL = [C_GOLD, C_SILVER, C_BRONZE]
        MEDAL_DIM = [C_GOLD_DIM, C_SILVER_DIM, C_BRONZE_DIM]
        MEDAL_BG = [(35,28,4), (24,28,38), (32,22,10)]

        # ── BACKGROUND: dark navy → faint purple gradient ────────
        for yy in range(H):
            t = yy / H
            if t < 0.5:
                u = t * 2
                r = int(C_BG_TOP[0] + u * (C_BG_MID[0] - C_BG_TOP[0]))
                g = int(C_BG_TOP[1] + u * (C_BG_MID[1] - C_BG_TOP[1]))
                b = int(C_BG_TOP[2] + u * (C_BG_MID[2] - C_BG_TOP[2]))
            else:
                u = (t - 0.5) * 2
                r = int(C_BG_MID[0] + u * (C_BG_BOT[0] - C_BG_MID[0]))
                g = int(C_BG_MID[1] + u * (C_BG_BOT[1] - C_BG_MID[1]))
                b = int(C_BG_MID[2] + u * (C_BG_BOT[2] - C_BG_MID[2]))
            draw.line([(0, yy), (W, yy)], fill=(r, g, b))

        # Subtle "circuit-board" lines on the left + right edges (decorative).
        _rng = random.Random(11)
        for _ in range(40):
            sx0 = _rng.choice([_rng.randint(0, 80), _rng.randint(W - 80, W - 1)])
            sy0 = _rng.randint(50, H - 50)
            seg_len = _rng.randint(40, 110)
            draw.line([(sx0, sy0), (sx0 + seg_len, sy0)], fill=(20, 30, 70), width=1)
            draw.line([(sx0 + seg_len, sy0), (sx0 + seg_len, sy0 - 20)], fill=(20, 30, 70), width=1)
            draw.ellipse([sx0 + seg_len - 2, sy0 - 22, sx0 + seg_len + 2, sy0 - 18], fill=(60, 130, 200))

        # Decorative starfield.
        for _ in range(120):
            sx, sy = _rng.randint(0, W), _rng.randint(0, H)
            br = _rng.randint(40, 140)
            draw.ellipse([sx - 1, sy - 1, sx + 1, sy + 1], fill=(br, br, br + 20))

        # ── FONTS ────────────────────────────────────────────────
        def _tf(size):
            try:
                return ImageFont.truetype(DASHBOARD_FONT_PATH, size)
            except Exception:
                return ImageFont.load_default()

        fHero  = _tf(50)   # LEADERBOARD title
        fH3    = _tf(20)   # section pill text
        fBody  = _tf(16)   # row text
        fSmall = _tf(13)   # small labels
        fTiny  = _tf(11)   # footer
        fHexN  = _tf(72)   # gigantic #1/#2/#3 inside hex
        fBadge = _tf(14)   # rank badge text
        fName  = _tf(20)   # podium username
        fAmt   = _tf(15)   # podium amount
        fYRk   = _tf(58)   # YOUR POSITION rank glyph

        # ── HEADER STRIP ─────────────────────────────────────────
        HDR_H = 92
        draw.rectangle([0, 0, W, HDR_H], fill=C_HEADER)
        # Hero title centered.
        title = "LEADERBOARD"
        tw = draw.textlength(title, font=fHero)
        draw.text(((W - tw) // 2, 18), title, fill=C_BLUE, font=fHero)
        # Top-right: @bot_username + CASINO subtitle.
        bot_lbl = f"@{bot_username}"
        blw = draw.textlength(bot_lbl, font=fSmall)
        draw.text((W - blw - 22, 18), bot_lbl, fill=C_WHITE, font=fSmall)
        casino_sub = "CASINO"
        cw = draw.textlength(casino_sub, font=fTiny)
        draw.text((W - cw - 22, 38), casino_sub, fill=C_MUTED, font=fTiny)
        # Top-left: small leaderboard chip.
        lb_chip = "leaderboard"
        lcw = draw.textlength(lb_chip, font=fSmall)
        chip_y = HDR_H + 12
        draw.text((W - lcw - 22, chip_y), lb_chip, fill=C_BLUE, font=fSmall)
        # tiny bar-chart glyph next to it
        draw.rectangle([W - lcw - 38, chip_y + 4, W - lcw - 34, chip_y + 18], fill=C_BLUE)
        draw.rectangle([W - lcw - 32, chip_y + 8, W - lcw - 28, chip_y + 18], fill=C_BLUE)
        draw.rectangle([W - lcw - 26, chip_y + 12, W - lcw - 22, chip_y + 18], fill=C_BLUE)

        # ── SECTION TITLE PILL ───────────────────────────────────
        stw = draw.textlength(section_title, font=fH3)
        pill_w = int(stw + 56)
        pill_h = 46
        pill_x = (W - pill_w) // 2
        pill_y = HDR_H + 38
        draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
                               radius=22, fill=(8, 18, 44), outline=C_BLUE_DIM, width=2)
        draw.text((pill_x + 28, pill_y + 11), section_title, fill=C_WHITE, font=fH3)

        # Decorative dotted side lines below pill (matches the template).
        for dx in range(20, pill_x - 20, 14):
            draw.line([(dx, pill_y + pill_h // 2), (dx + 6, pill_y + pill_h // 2)],
                      fill=C_BORDER, width=1)
        for dx in range(pill_x + pill_w + 20, W - 20, 14):
            draw.line([(dx, pill_y + pill_h // 2), (dx + 6, pill_y + pill_h // 2)],
                      fill=C_BORDER, width=1)

        # ── TOP-3 HEXAGONAL PODIUM ───────────────────────────────
        top3 = entries[:3]
        avatars = top_avatars or {}

        def _hex_polygon(cx, cy, radius_w, radius_h):
            """Return a 6-point hex polygon (pointy top/bottom)."""
            return [
                (cx, cy - radius_h),
                (cx + radius_w, cy - radius_h // 2),
                (cx + radius_w, cy + radius_h // 2),
                (cx, cy + radius_h),
                (cx - radius_w, cy + radius_h // 2),
                (cx - radius_w, cy - radius_h // 2),
            ]

        def _paste_avatar_circle(cx, cy, r, pic, ring_color):
            """Paste a circular avatar at (cx, cy) with radius r."""
            box = (cx - r, cy - r, cx + r, cy + r)
            # Glow ring.
            draw.ellipse([box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4],
                         outline=ring_color, width=3)
            if isinstance(pic, Image.Image):
                try:
                    sz = (r * 2, r * 2)
                    src = pic.convert("RGBA").resize(sz, Image.Resampling.LANCZOS)
                    mask = Image.new("L", sz, 0)
                    ImageDraw.Draw(mask).ellipse([0, 0, sz[0] - 1, sz[1] - 1], fill=255)
                    img.paste(src, (cx - r, cy - r), mask)
                    return
                except Exception:
                    pass
            # Fallback: dim disc with mask-like initial.
            draw.ellipse(box, fill=(20, 20, 35), outline=ring_color, width=2)

        def _draw_light_beam(cx, top_y, bot_y, top_w, bot_w, color):
            """Translucent trapezoidal beam shooting up from the hex top."""
            beam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            beam_draw = ImageDraw.Draw(beam)
            # Layered alpha so the beam looks brighter at the bottom (where it
            # leaves the hex) and fades softly toward the top.
            for layer, (alpha, scale) in enumerate([
                (110, 1.0),
                (70,  0.85),
                (40,  0.7),
            ]):
                tw_l = max(2, int(top_w * scale))
                bw_l = max(4, int(bot_w * scale))
                poly = [
                    (cx - bw_l // 2, bot_y),
                    (cx + bw_l // 2, bot_y),
                    (cx + tw_l // 2, top_y),
                    (cx - tw_l // 2, top_y),
                ]
                beam_draw.polygon(poly, fill=(color[0], color[1], color[2], alpha))
            beam = beam.filter(ImageFilter.GaussianBlur(radius=12))
            img.alpha_composite(beam)

        def _draw_hex_pedestal(rank_num, entry, cx, avatar_cy, hex_h, is_center):
            """Render a single hex pedestal + avatar + label.

            Positioning is driven from ``avatar_cy`` (the y-center of the
            floating avatar). Username + amount are stacked below the avatar
            and the hex sits below them. The hex top is computed
            deterministically so the labels never overlap the hex.
            """
            mc = MEDAL[rank_num - 1]
            mdim = MEDAL_DIM[rank_num - 1]
            mbg = MEDAL_BG[rank_num - 1]

            av_r = 40 if is_center else 32
            rx = 96 if is_center else 80
            ry = hex_h // 2

            # Compute label band + hex top from avatar position so nothing
            # overlaps.
            label_top = avatar_cy + av_r + 12
            hex_top_y = label_top + 56  # username row (24) + amount row (20) + pad
            cy = hex_top_y + ry
            poly = _hex_polygon(cx, cy, rx, ry)

            # 1. Light beam (drawn first, behind the hex).
            beam_top = max(HDR_H + 60, avatar_cy - av_r - 30)
            _draw_light_beam(
                cx, beam_top, cy,
                top_w=int(rx * 0.7), bot_w=int(rx * 1.7),
                color=mc,
            )

            # 2. Glow halo behind hex.
            halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            halo_draw = ImageDraw.Draw(halo)
            halo_poly = _hex_polygon(cx, cy, rx + 16, ry + 16)
            halo_draw.polygon(halo_poly, fill=(mc[0], mc[1], mc[2], 50))
            halo = halo.filter(ImageFilter.GaussianBlur(radius=10))
            img.alpha_composite(halo)

            # 3. Filled hex with bright outline.
            draw.polygon(poly, fill=mbg, outline=mc)
            for _ in range(2):
                draw.polygon(poly, outline=mc)
            # Inner thin dim outline for depth.
            inner = _hex_polygon(cx, cy, rx - 10, ry - 10)
            draw.polygon(inner, outline=mdim)

            # 4. Big rank glyph centered in hex.
            rk_str = f"#{rank_num}"
            rkw = draw.textlength(rk_str, font=fHexN)
            # Vertically centred-ish in the hex (font ascent makes pure
            # centring look low; nudge up a bit).
            glyph_y = cy - 50
            draw.text((cx - rkw / 2 + 4, glyph_y + 4), rk_str, fill=mdim, font=fHexN)
            draw.text((cx - rkw / 2, glyph_y), rk_str, fill=mc, font=fHexN)

            # 5. Floating avatar.
            _paste_avatar_circle(cx, avatar_cy, av_r, avatars.get(rank_num), mc)

            # 6. Small "#N" badge clipped to the avatar's top-left.
            badge_w, badge_h = 42, 24
            bx0 = cx - av_r - 10
            by0 = avatar_cy - av_r - 8
            draw.rounded_rectangle([bx0, by0, bx0 + badge_w, by0 + badge_h],
                                   radius=8, fill=mbg, outline=mc, width=2)
            bs = f"#{rank_num}"
            bsw = draw.textlength(bs, font=fBadge)
            draw.text((bx0 + (badge_w - bsw) / 2, by0 + 4), bs, fill=mc, font=fBadge)

            # 7. Username + amount labels between the avatar and the hex top.
            uname = (entry["username"][:18] if entry and entry.get("username") else "")
            unw = draw.textlength(uname, font=fName)
            draw.text((cx - unw / 2, label_top), uname, fill=C_WHITE, font=fName)
            if entry:
                val_str = value_formatter(entry["value"])
                vw = draw.textlength(val_str, font=fAmt)
                draw.text((cx - vw / 2, label_top + 28), val_str, fill=C_GREEN, font=fAmt)

            return cy + ry  # Return hex bottom y for caller layout.

        # Layout: hex centers and heights.
        side_hex_h = 130
        center_hex_h = 170
        cx_left = int(W * 0.20)
        cx_mid  = W // 2
        cx_right = int(W * 0.80)

        # Avatar y positions (center sits higher = taller pedestal).
        ctr_avatar_y  = HDR_H + 130
        side_avatar_y = HDR_H + 170

        ctr_bottom = _draw_hex_pedestal(
            1, top3[0] if len(top3) >= 1 else None,
            cx_mid, ctr_avatar_y, center_hex_h, True,
        )
        _ = _draw_hex_pedestal(
            2, top3[1] if len(top3) >= 2 else None,
            cx_left, side_avatar_y, side_hex_h, False,
        )
        _ = _draw_hex_pedestal(
            3, top3[2] if len(top3) >= 3 else None,
            cx_right, side_avatar_y, side_hex_h, False,
        )

        # ── RANKS 4-10 SEPARATOR ─────────────────────────────────
        sep_y = ctr_bottom + 30
        draw.line([(40, sep_y), (W - 40, sep_y)], fill=C_BORDER, width=1)
        ranks_lbl = "RANKS  4 — 10"
        rlw = draw.textlength(ranks_lbl, font=fSmall)
        draw.rectangle([((W - rlw) // 2 - 8), sep_y - 8, ((W + rlw) // 2 + 8), sep_y + 8],
                       fill=C_BG_MID)
        draw.text(((W - rlw) // 2, sep_y - 7), ranks_lbl, fill=C_MUTED, font=fSmall)

        # ── YOUR POSITION (left) + RANKS 4-10 ROWS (right) ───────
        body_y = sep_y + 26
        # Your-position card on the left.
        YP_W = 250
        YP_H = 200
        YP_X = 22
        draw.rounded_rectangle([YP_X, body_y, YP_X + YP_W, body_y + YP_H],
                               radius=20, fill=(8, 18, 44), outline=C_BLUE, width=2)
        # Soft outer glow.
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.rounded_rectangle([YP_X - 6, body_y - 6, YP_X + YP_W + 6, body_y + YP_H + 6],
                             radius=24, outline=(60, 160, 220, 80), width=4)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=4))
        img.alpha_composite(glow)
        # Header line.
        draw.text((YP_X + 22, body_y + 14), your_rank_label, fill=C_MUTED, font=fSmall)
        draw.line([(YP_X + 22, body_y + 34), (YP_X + YP_W - 22, body_y + 34)],
                  fill=C_BORDER, width=1)
        # Rank glyph (centered) — stacked above the wager so wide ranks like
        # "#101" never overlap the value below.
        if user_rank is not None and isinstance(user_rank, int):
            rk_str = f"#{user_rank}"
            rk_color = C_GOLD
        else:
            rk_str = "–"
            rk_color = C_MUTED
        rk_w = draw.textlength(rk_str, font=fYRk)
        rk_x = YP_X + (YP_W - rk_w) / 2
        draw.text((rk_x, body_y + 44), rk_str, fill=rk_color, font=fYRk)
        # Thin divider between the rank glyph and the wager block.
        draw.line([(YP_X + 40, body_y + 124), (YP_X + YP_W - 40, body_y + 124)],
                  fill=C_BORDER, width=1)
        # Wager label + value centered below the rank.
        wlw = draw.textlength(your_value_label, font=fSmall)
        draw.text((YP_X + (YP_W - wlw) / 2, body_y + 132),
                  your_value_label, fill=C_MUTED, font=fSmall)
        if user_wagered > 0:
            wv = value_formatter(user_wagered)
        else:
            wv = "—"
        wvw = draw.textlength(wv, font=fName)
        draw.text((YP_X + (YP_W - wvw) / 2, body_y + 150),
                  wv, fill=C_GREEN, font=fName)

        # Right-side ranks 4-10 rows.
        ROWS_X0 = YP_X + YP_W + 18
        ROWS_X1 = W - 22
        rows_y = body_y
        ROW_H = 64
        ROW_GAP = 8
        rank_entries = list(entries[3:10])
        # Always render exactly 7 slots (filled or empty) so the card stays
        # visually balanced like the template.
        for i in range(7):
            row_top = rows_y + i * (ROW_H + ROW_GAP)
            row_bot = row_top + ROW_H
            if row_bot > body_y + YP_H + 220:
                break
            entry = rank_entries[i] if i < len(rank_entries) else None
            row_filled = entry is not None
            bg = C_CARD if row_filled else (10, 18, 38)
            draw.rounded_rectangle([ROWS_X0, row_top, ROWS_X1, row_bot],
                                   radius=12, fill=bg, outline=C_BORDER, width=1)
            # Avatar circle (left).
            ac_r = 18
            ac_cx = ROWS_X0 + 26
            ac_cy = (row_top + row_bot) // 2
            draw.ellipse([ac_cx - ac_r, ac_cy - ac_r, ac_cx + ac_r, ac_cy + ac_r],
                         fill=(18, 30, 60), outline=C_BORDER, width=1)
            if row_filled:
                rk_str = f"#{entry['rank']}"
                rkw = draw.textlength(rk_str, font=fBadge)
                draw.text((ac_cx - rkw / 2, ac_cy - 8), rk_str, fill=C_BLUE, font=fBadge)
                # Username.
                uname = entry["username"][:24]
                draw.text((ac_cx + ac_r + 16, ac_cy - 10), uname, fill=C_WHITE, font=fBody)
                # Value (right-aligned).
                vstr = value_formatter(entry["value"])
                vw = draw.textlength(vstr, font=fBody)
                draw.text((ROWS_X1 - vw - 18, ac_cy - 10), vstr, fill=C_GREEN, font=fBody)
            else:
                # Empty placeholder row.
                draw.text((ROWS_X1 - 28, ac_cy - 10), "—", fill=C_MUTED, font=fBody)

        # ── FOOTER ────────────────────────────────────────────────
        footer_y = H - 42
        footer = "Play Responsibly  •  Telegram Casino"
        fw = draw.textlength(footer, font=fSmall)
        draw.text(((W - fw) // 2, footer_y), footer, fill=C_MUTED, font=fSmall)
        # Tiny diamond glyph in the bottom-right corner.
        dx, dy = W - 36, footer_y - 4
        diamond = [(dx, dy - 10), (dx + 10, dy), (dx, dy + 10), (dx - 10, dy)]
        draw.polygon(diamond, fill=C_BLUE)

        # ── SAVE ──────────────────────────────────────────────────
        output = BytesIO()
        img = img.convert("RGB")
        img.save(output, format='JPEG', quality=95)
        output.seek(0)
        return output
    except Exception as e:
        logging.error(f"PIL leaderboard render error: {e}")
        import traceback; traceback.print_exc()
        return None

async def generate_leaderboard_referral_image(context):
    """Generate referral leaderboard template - following same design language."""
    try:
        global _bot_username_cache
        if _bot_username_cache is None:
            bot_info = await context.bot.get_me()
            _bot_username_cache = bot_info.username
        bot_username = _bot_username_cache

        # PERFORMANCE: heapq.nlargest(10, ...) over a generator is O(N log 10)
        # instead of O(N log N) from sorted(..., reverse=True). Matters at
        # 5000+ users when the referral leaderboard gets tapped.
        import heapq as _heapq_rl
        sorted_users = _heapq_rl.nlargest(
            10,
            user_stats.items(),
            key=lambda item: len(item[1].get('referral', {}).get('referred_users', [])),
        )

        entries = []
        for i, (uid, st) in enumerate(sorted_users):
            uname = st.get('userinfo', {}).get('username', f'User-{uid}').lstrip('@')
            rc = len(st.get('referral', {}).get('referred_users', []))
            if rc > 0:
                entries.append({"rank": len(entries) + 1, "username": uname, "referrals": rc})

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _image_executor,
            _render_leaderboard_referral_sync,
            entries,
            bot_username,
        )
        return result
    except Exception as e:
        logging.error(f"Error generating referral leaderboard image: {e}")
        return None

def _render_leaderboard_referral_sync(entries, bot_username):
    """Render referral leaderboard with the same look as the main wagered
    leaderboard. Re-uses ``_render_leaderboard_sync`` so the design stays in
    sync with the example template (hex podium top-3, ranks 4-10, etc.).
    """
    converted = []
    for e in (entries or []):
        converted.append({
            "rank": e.get("rank"),
            "username": e.get("username", ""),
            "value": int(e.get("referrals", 0) or 0),
        })
    return _render_leaderboard_sync(
        entries=converted,
        bot_username=bot_username,
        section_title="All-Time Top Referrers",
        user_rank=None,
        user_wagered=0.0,
        value_formatter=lambda v: (
            f"{int(v):,} ref" if int(v) == 1 else f"{int(v):,} refs"
        ),
        your_rank_label="YOUR REFERRALS",
        your_value_label="Total Referrals",
    )


async def _flush_leaderboard_buffer():
    """Batch-process leaderboard updates every 10 seconds.

    PERFORMANCE: dropped the per-entry INFO log (fires once per bet, so in a
    busy casino that's hundreds of file-I/O log records a minute for no
    operational benefit). Kept a DEBUG line for troubleshooting and an
    INFO only when something actually fails.
    """
    logging.debug("[LEADERBOARD] Flush task started (10s interval)")
    while True:
        await asyncio.sleep(10)
        async with _leaderboard_buffer_lock:
            if not _leaderboard_buffer:
                continue
            batch = list(_leaderboard_buffer)
            _leaderboard_buffer.clear()
        failures = 0
        for (user_id, amount, win_amount, game_type, multiplier, ts) in batch:
            try:
                update_leaderboards(user_id, amount, win_amount, game_type, multiplier)
            except Exception as e:
                failures += 1
                logging.error(
                    f"Leaderboard update error for {user_id}: {e}",
                    exc_info=True
                )
        if failures:
            logging.warning(
                f"[LEADERBOARD] batch of {len(batch)} processed, "
                f"{failures} failure(s)"
            )
        else:
            logging.debug(f"[LEADERBOARD] batch of {len(batch)} processed")

def update_leaderboards(user_id, bet_amount, win_amount=0, game_type="", multiplier=0):
    """Update leaderboard data after each bet.

    Phase 2: when ``MYCASINO_REDIS_BACKEND`` is set we also push the
    wager/win deltas into Redis sorted sets via
    :func:`core.redis_backend.lb_incr`.  The in-memory ``leaderboard_data``
    structure stays authoritative for the player-facing UI until a later
    PR flips reads over to Redis; the mirror just gets the data ready
    for that switch and makes the leaderboard horizontally scalable
    across stateless PTB workers in the meantime.
    """
    global leaderboard_data, leaderboard_last_update

    # Get user info
    username = user_stats.get(user_id, {}).get('userinfo', {}).get('username', f'User-{user_id}')
    username = username.lstrip('@')

    # Phase 2 Redis mirror — fire-and-forget so the legacy bet flow
    # never blocks on Redis I/O.
    try:
        from core import redis_backend as _rb
        if _rb.redis_enabled():
            import asyncio as _aio
            try:
                _loop = _aio.get_running_loop()
                if bet_amount and float(bet_amount) > 0:
                    for _period in ("daily", "weekly", "monthly", "alltime"):
                        _loop.create_task(
                            _rb.lb_incr(_period, "wagered", int(user_id), float(bet_amount))
                        )
                if win_amount and float(win_amount) > 0:
                    for _period in ("daily", "weekly", "monthly", "alltime"):
                        _loop.create_task(
                            _rb.lb_incr(_period, "won", int(user_id), float(win_amount))
                        )
            except RuntimeError:
                # No running loop — fall through to legacy in-memory path.
                pass
    except Exception:  # noqa: BLE001
        logging.exception("Redis leaderboard mirror failed for user=%s", user_id)

    # Check for weekly/monthly reset
    now = datetime.now(timezone.utc)

    # Weekly reset (every Monday)
    if now.date() > leaderboard_last_update["weekly_reset"].date():
        days_diff = (now.date() - leaderboard_last_update["weekly_reset"].date()).days
        if days_diff >= 7 or now.weekday() < leaderboard_last_update["weekly_reset"].weekday():
            leaderboard_data["weekly"] = []
            leaderboard_last_update["weekly_reset"] = now

    # Monthly reset
    if now.month != leaderboard_last_update["monthly_reset"].month or now.year != leaderboard_last_update["monthly_reset"].year:
        leaderboard_data["monthly"] = []
        leaderboard_data["highest_wins"] = []  # Reset highest wins monthly
        leaderboard_last_update["monthly_reset"] = now

    # Update all-time leaderboard
    total_wagered = user_stats.get(user_id, {}).get('bets', {}).get('amount', 0.0)
    _update_leaderboard_entry(leaderboard_data["all_time"], user_id, username, total_wagered)

    # Update weekly leaderboard
    _update_leaderboard_entry(leaderboard_data["weekly"], user_id, username, bet_amount, accumulate=True)

    # Update monthly leaderboard
    _update_leaderboard_entry(leaderboard_data["monthly"], user_id, username, bet_amount, accumulate=True)

    # Update highest wins if this is a win
    if win_amount > 0 and multiplier > 0:
        _update_highest_wins(user_id, username, win_amount, game_type, now)

    # Keep only top 10 (already sorted by bisect insertion)
    for key in ["all_time", "weekly", "monthly"]:
        if len(leaderboard_data[key]) > 10:
            del leaderboard_data[key][10:]
    if len(leaderboard_data["highest_wins"]) > 10:
        leaderboard_data["highest_wins"] = sorted(leaderboard_data["highest_wins"], key=lambda x: x[2], reverse=True)[:10]

def _update_leaderboard_entry(leaderboard, user_id, username, amount, accumulate=False):
    """O(log n) insertion using bisect instead of O(n log n) sort."""
    new_score = 0
    for i, entry in enumerate(leaderboard):
        if entry[0] == user_id:
            new_score = (entry[2] + amount) if accumulate else amount
            leaderboard.pop(i)
            break
    else:
        new_score = amount

    # bisect on negative values to achieve descending sort
    scores_neg = [-e[2] for e in leaderboard]
    idx = bisect.bisect_left(scores_neg, -new_score)
    leaderboard.insert(idx, (user_id, username, new_score))

    if len(leaderboard) > 10:
        del leaderboard[10:]

def _update_highest_wins(user_id, username, win_amount, game_type, timestamp):
    """Helper to update highest wins"""
    # Check if this win should be in top 10
    if len(leaderboard_data["highest_wins"]) < 10 or win_amount > leaderboard_data["highest_wins"][-1][2]:
        leaderboard_data["highest_wins"].append((user_id, username, win_amount, game_type, timestamp))
        leaderboard_data["highest_wins"] = sorted(leaderboard_data["highest_wins"], key=lambda x: x[2], reverse=True)[:10]

@check_banned
@check_maintenance
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    """Display leaderboard with interactive buttons"""
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    user_id = update.effective_user.id

    # Set menu owner for group protection when called as command
    if not from_callback:
        context.user_data['menu_owner_id'] = user_id

    # Rebuild leaderboard from user_stats before display
    _rebuild_leaderboards()

    # Default view is all-time
    view = context.user_data.get('leaderboard_view', 'all_time')

    # Leaderboard amounts are rendered in the VIEWING user's display
    # currency, compact-formatted so big numbers collapse to
    # e.g. 6.3L (INR) or $1.2M (USD) instead of bleeding across the row.
    def _fmt(amt_usd):
        return format_compact_for_user(user_id, amt_usd)

    # Get leaderboard data
    if view == 'all_time':
        title = f"{pe('trophy')} <b>Top 10 Players - All Time</b> {pe('trophy')}"
        data = leaderboard_data["all_time"]
        msg = f"{title}\n\n"
        if data:
            for i, (uid, username, wagered) in enumerate(data):
                rank_sym = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                display_name = get_privacy_display_name(uid, username)
                msg += f"{rank_sym} {display_name} - <b>{_fmt(wagered)}</b>\n"
        else:
            msg += "No data available yet.\n"
    elif view == 'weekly':
        title = f"{pe('weekly')} <b>Top 10 Players - This Week</b> {pe('weekly')}"
        data = leaderboard_data["weekly"]
        msg = f"{title}\n\n"
        if data:
            for i, (uid, username, wagered) in enumerate(data):
                rank_sym = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                display_name = get_privacy_display_name(uid, username)
                msg += f"{rank_sym} {display_name} - <b>{_fmt(wagered)}</b>\n"
        else:
            msg += "No data available yet.\n"
    elif view == 'monthly':
        title = f"{pe('monthly')} <b>Top 10 Players - This Month</b> {pe('monthly')}"
        data = leaderboard_data["monthly"]
        msg = f"{title}\n\n"
        if data:
            for i, (uid, username, wagered) in enumerate(data):
                rank_sym = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                display_name = get_privacy_display_name(uid, username)
                msg += f"{rank_sym} {display_name} - <b>{_fmt(wagered)}</b>\n"
        else:
            msg += "No data available yet.\n"
    elif view == 'highest_wins':
        title = f"{pe('money')} <b>Highest Wins - This Month</b> {pe('money')}"
        data = leaderboard_data["highest_wins"]
        msg = f"{title}\n\n"
        if data:
            for i, (uid, username, win_amount, game_type, timestamp) in enumerate(data):
                rank_sym = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
                display_name = get_privacy_display_name(uid, username)
                date_str = timestamp.strftime("%Y-%m-%d") if isinstance(timestamp, datetime) else str(timestamp)[:10]
                msg += f"{rank_sym} {display_name} - <b>{_fmt(win_amount)}</b>\n   Game: {game_type.upper()} | Date: {date_str}\n\n"
        else:
            msg += "No wins recorded yet.\n"

    # === Calculate user's rank ===
    # Find user's position in the current view
    if view == 'highest_wins':
        ranked_list = [(uid, uname, wamt) for uid, uname, wamt, _, _ in leaderboard_data.get('highest_wins', [])]
    else:
        ranked_list = leaderboard_data.get(view if view != 'alltime' else 'all_time', [])

    user_rank = None
    user_wagered = 0.0
    for i, (uid, uname, wag) in enumerate(ranked_list):
        if uid == user_id:
            user_rank = i + 1
            user_wagered = wag
            break

    # If not in top 10, calculate rank from all users
    if user_rank is None:
        if view == 'highest_wins':
            all_entries = [(uid, uname, wamt) for uid, uname, wamt, _, _ in leaderboard_data.get('highest_wins', [])]
        else:
            all_entries = leaderboard_data.get(view if view != 'alltime' else 'all_time', [])

        # Check if user has any wagering
        stats = user_stats.get(user_id, {})
        if view == 'weekly':
            user_wagered = stats.get('weekly_stats', {}).get('weighted_wager', 0.0)
        elif view == 'monthly':
            user_wagered = stats.get('monthly_stats', {}).get('weighted_wager', 0.0)
        elif view == 'highest_wins':
            user_wagered = stats.get('last_win', 0)
        else:
            user_wagered = stats.get('bets', {}).get('amount', 0.0)

        if user_wagered > 0:
            # Count how many users have more wagered
            rank = 1
            for uid2, uname2, wag2 in all_entries:
                if wag2 > user_wagered:
                    rank += 1
            user_rank = rank
        else:
            user_rank = "Unranked"
            user_wagered = 0.0

    # Add user rank to message (wagered in user's display currency, compact).
    wagered_str = format_compact_for_user(user_id, user_wagered)
    rank_display = ""
    if isinstance(user_rank, int):
        rank_display = f"\n{pe('chart')} <b>Your Rank: #{user_rank}</b> - {wagered_str} wagered"
    else:
        rank_display = f"\n{pe('chart')} <b>Your Rank:</b> Unranked - {wagered_str} wagered"

    msg += rank_display

    # Determine if in group chat
    is_group = False
    if from_callback and update.callback_query:
        try:
            is_group = update.callback_query.message.chat.type in ["group", "supergroup"]
        except AttributeError:
            pass
    elif update.effective_chat:
        is_group = update.effective_chat.type in ["group", "supergroup"]

    # Create inline buttons (user-specific)
    keyboard = [
        [
            apply_button_style(InlineKeyboardButton("Weekly", callback_data=f"leaderboard_weekly_{user_id}"), 'primary'),
            apply_button_style(InlineKeyboardButton("Monthly", callback_data=f"leaderboard_monthly_{user_id}"), 'success')
        ],
        [
            apply_button_style(InlineKeyboardButton("Highest Wins", callback_data=f"leaderboard_wins_{user_id}"), 'primary')
        ],
        [
            apply_button_style(InlineKeyboardButton("All Time", callback_data=f"leaderboard_alltime_{user_id}"), 'success')
        ],
    ]

    # Only show back button in DMs
    if not is_group:
        keyboard.append([
            apply_button_style(InlineKeyboardButton("Back to More", callback_data="main_more"), 'danger', peb('back'))
        ])

    reply_markup = create_styled_keyboard(keyboard)

    # Generate leaderboard image
    lb_image = await generate_leaderboard_image(context, period=view, viewing_user_id=user_id)

    if from_callback:
        # EDIT the existing message in place - no delete+resend (like blackjack)
        if lb_image:
            try:
                await update.callback_query.edit_message_media(
                    media=InputMediaPhoto(media=lb_image, parse_mode=ParseMode.HTML),
                    reply_markup=reply_markup
                )
                return
            except Exception as e:
                logging.error(f"Error updating leaderboard image: {e}")

        # Fallback: edit text message in place
        await update.callback_query.edit_message_text(
            msg,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    else:
        # Main bot handles /leaderboard in all chats (groups and DMs)
        # Get original message ID for tagging in groups
        original_message_id = None
        if is_group and update.message:
            original_message_id = update.message.message_id

        if lb_image:
            if original_message_id:
                sent_message = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=lb_image,
                    reply_markup=reply_markup,
                    reply_to_message_id=original_message_id
                )
            else:
                sent_message = await update.message.reply_photo(
                    photo=lb_image,
                    reply_markup=reply_markup
                )
        else:
            if original_message_id:
                sent_message = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                    reply_to_message_id=original_message_id
                )
            else:
                sent_message = await update.message.reply_text(
                    msg,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
        if reply_markup:
            set_menu_owner(sent_message, user_id)
        return

@check_banned
@check_maintenance
async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle leaderboard navigation button clicks"""
    query = update.callback_query
    user = query.from_user

    # Parse callback data
    parts = query.data.split("_")
    if len(parts) < 3:
        return

    action = parts[1]  # weekly, monthly, wins, alltime
    button_user_id = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None

    # User-specific button check
    if button_user_id and user.id != button_user_id:
        await query.answer("This menu is not for you!", show_alert=True)
        return

    await query.answer()

    # Set the view in user_data
    view_map = {
        'weekly': 'weekly',
        'monthly': 'monthly',
        'wins': 'highest_wins',
        'alltime': 'all_time'
    }

    if action in view_map:
        context.user_data['leaderboard_view'] = view_map[action]
        await leaderboard_command(update, context, from_callback=True)

@check_banned
@check_maintenance
async def leaderboard_referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)

    # Create inline buttons for referral leaderboard
    keyboard = [
        [InlineKeyboardButton("Back to More", callback_data="main_more")]
    ]
    reply_markup = create_styled_keyboard(keyboard)

    # Generate referral leaderboard template image
    rf_image = await generate_leaderboard_referral_image(context)

    is_group = update.effective_chat.type in ["group", "supergroup"]

    # Use helper bot in groups for info commands
    if is_group and helper_bot:
        try:
            if rf_image:
                sent_message = await helper_bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=rf_image,
                    reply_markup=reply_markup
                )
            else:
                sent_message = await helper_bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"{pe('push')} Referral Leaderboard", parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
            set_menu_owner(sent_message, update.effective_user.id)
            return
        except Exception as e:
            logging.warning(f"Helper bot failed for /leaderboardrf: {e}")

    if rf_image:
        sent_message = await update.message.reply_photo(
            photo=rf_image,
            reply_markup=reply_markup
        )
    else:
        sent_message = await update.message.reply_text(f"{pe('push')} Referral Leaderboard", parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    set_menu_owner(sent_message, update.effective_user.id)

def register(ctx):
    """Auto-generated from main()'s add_handler list."""
    app = ctx.application
    app.add_handler(CommandHandler('leaderboard', leaderboard_command, block=False))
    app.add_handler(CommandHandler('leaderboardrf', leaderboard_referral_command, block=False))
    app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern='^leaderboard_(weekly|monthly|wins|alltime)_', block=False))
    if helper_app is not None:
        helper_app.add_handler(CallbackQueryHandler(leaderboard_callback, pattern='^leaderboard_(weekly|monthly|wins|alltime)_', block=False))

