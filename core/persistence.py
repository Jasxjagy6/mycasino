"""Auto-split from bot.py — core.persistence."""
from __future__ import annotations
from core.foundation import *  # noqa: F401, F403

def _sync_write_user(user_id):
    """Synchronous disk write. Runs in ThreadPoolExecutor, never on event loop."""
    if user_id not in user_stats:
        return
    try:
        try:
            import orjson
            data = dict(user_stats[user_id])
            data["wallet"] = ensure_wallet_dict(user_id)
            path = os.path.join(DATA_DIR, f"{user_id}.json")
            tmp_path = path + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
            os.replace(tmp_path, path)  # atomic rename — crash-safe
        except ImportError:
            data = dict(user_stats.get(user_id, {}))
            data["wallet"] = ensure_wallet_dict(user_id)
            path = os.path.join(DATA_DIR, f"{user_id}.json")
            tmp_path = path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f, default=str)
            os.replace(tmp_path, path)
    except Exception as e:
        logging.error(f"Disk write failed for user {user_id}: {e}")

def save_all_user_data():
    """Save all user data. Uses PostgreSQL if enabled, otherwise JSON files."""
    logging.info("Saving all user data...")
    if USE_POSTGRES_FOR_ALL and pg_db:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(pg_db.save_all_users())
            else:
                loop.run_until_complete(pg_db.save_all_users())
            logging.info("All user data saved to PostgreSQL.")
        except Exception as e:
            logging.error(f"PostgreSQL save failed: {e}")
            # Fallback to JSON
            for user_id in user_stats.keys():
                save_user_data(user_id)
    else:
        for user_id in user_stats.keys():
            save_user_data(user_id)
        logging.info("All user data saved to JSON files.")

def save_bot_state_inline():
    """Original blocking save — kept for shutdown / startup paths."""
    try:
        _sync_save_bot_state_json()
        save_all_escrow_deals()
        save_all_group_settings()
        save_all_recovery_data()
        save_all_gift_codes()
    except Exception as e:
        logging.error(f"save_bot_state partial failure: {e}")

def save_all_data():
    """Alias used by shutdown/atexit hooks — routes to the full save."""
    save_bot_state_full()

