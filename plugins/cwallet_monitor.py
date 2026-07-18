"""CWallet deposit monitor using a Telegram user account (Telethon).

Works around the Telegram Bot API limitation where bots cannot see
messages from other bots.  A user account uses MTProto directly to
read @cctip_bot's confirmation messages from ANY chat it's in and
credit the tipper's casino balance.

Usage:
  1. Create a Telegram user account, join the deposit group(s).
  2. Generate a Telethon StringSession:
       python3 -c "
       from telethon.sessions import StringSession
       from telethon import TelegramClient
       import asyncio
       async def gen():
           c = TelegramClient(StringSession(), API_ID, API_HASH)
           await c.start()
           print(StringSession.save(c.session))
           await c.disconnect()
       asyncio.run(gen())
     "
  3. Set in .env:
       TELEGRAM_API_ID=<api_id>
       TELEGRAM_API_HASH=<api_hash>
       CWALLET_MONITOR_SESSION=<session_string>
"""
from __future__ import annotations
from core.foundation import *

import logging

CCTIP_BOT_USERNAME_LOWER = (CWALLET_BOT_USERNAME or 'cctip_bot').lower().lstrip('@')
_cctip_bot_userid: int | None = None
cwallet_client = None


async def start_cwallet_monitor(application=None):
    if not all([TELEGRAM_API_ID, TELEGRAM_API_HASH, CWALLET_MONITOR_SESSION]):
        logging.info("CWallet monitor: skipped (TELEGRAM_API_ID/HASH or SESSION not set)")
        return None

    try:
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
    except ImportError:
        logging.warning("CWallet monitor: telethon not installed (pip install telethon)")
        return None

    try:
        client = TelegramClient(
            StringSession(CWALLET_MONITOR_SESSION),
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
        )
        await client.start()
        me = await client.get_me()
        logging.info(f"CWallet monitor: logged in as @{me.username} (id={me.id})")
        global cwallet_client
        cwallet_client = client

        load_cwallet_monitored_group_ids()
        logging.info(
            "CWallet monitor: tracking %d groups: %s",
            len(cwallet_monitored_group_ids),
            sorted(cwallet_monitored_group_ids),
        )

        global _cctip_bot_userid
        try:
            cctip = await client.get_entity(CCTIP_BOT_USERNAME_LOWER)
            _cctip_bot_userid = cctip.id
            logging.info(f"CWallet monitor: resolved @{CCTIP_BOT_USERNAME_LOWER} id={_cctip_bot_userid}")
        except Exception as e:
            _cctip_bot_userid = None
            logging.warning(f"CWallet monitor: could not resolve @{CCTIP_BOT_USERNAME_LOWER}: {e}")

        if application is not None:
            global _cwallet_bot_ref
            _cwallet_bot_ref = application.bot

        @client.on(events.NewMessage)
        async def handle_new_message(event):
            msg = event.message
            if not msg or not msg.text:
                return
            if msg.chat_id not in cwallet_monitored_group_ids:
                track_cwallet_monitor_group(msg.chat_id)
            sender = await msg.get_sender()
            if not sender:
                return
            if _cctip_bot_userid is not None:
                if sender.id != _cctip_bot_userid:
                    return
            else:
                sender_username = getattr(sender, 'username', '') or ''
                if sender_username.lower() != CCTIP_BOT_USERNAME_LOWER:
                    return
            parsed = parse_tip_message(msg.text or '')
            if not parsed:
                return
            if parsed['receiver_username'].lower().lstrip('@') != CWALLET_RECEIVE_USERNAME.lower().lstrip('@'):
                return
            dedup_key = f"mt_{msg.chat_id}_{msg.id}"
            logging.info(
                "CWallet monitor: tip @%s %s %s chat=%s",
                parsed['sender_username'],
                parsed['amount'],
                parsed['currency'],
                msg.chat_id,
            )
            result = await process_tip(
                parsed['sender_username'],
                parsed['receiver_username'],
                parsed['amount'],
                parsed['currency'],
                dedup_key,
            )
            if result:
                logging.info(f"CWallet monitor: credited ${result[0]:.2f} from @{parsed['sender_username']}")

        logging.info(
            "CWallet monitor: running (tracking %d groups)",
            len(cwallet_monitored_group_ids),
        )
        return client

    except Exception as e:
        logging.error(f"CWallet monitor: failed to start: {e}", exc_info=True)
        return None


async def stop_cwallet_monitor(client):
    if client:
        try:
            await client.disconnect()
            logging.info("CWallet monitor: disconnected")
        except Exception as e:
            logging.warning(f"CWallet monitor: disconnect error: {e}")
