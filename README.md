# mycasino

Production Telegram casino bot with a zero-downtime deployment runtime.

The bot itself lives in [`bot.py`](./bot.py) — a single-file Telegram bot
built on `python-telegram-bot` v20.  This repo ships a thin **runtime
layer** on top of it that lets you deploy and update the bot without
ever dropping a Telegram update.

## Layout

```
bot.py                    # the casino bot (entry point: `python bot.py`)
runtime/                  # zero-downtime runtime layer
  hot_reload.py           # importlib.reload() with handler / task bookkeeping
  plugin_loader.py        # discovers plugins under ./plugins/
  admin_handlers.py       # /reload, /reloadall, /listplugins, /runtimestatus
  bootstrap.py            # one-call register_runtime(app)
  queue_receiver.py       # tiny aiohttp -> Redis Stream receiver
  queue_worker.py         # XREADGROUP worker that drives a PTB Application
  blue_green.py           # webhook + side-car health endpoints + drain
plugins/                  # hot-reloadable casino feature modules
deploy/                   # nginx config, systemd units, blue-green switch
docs/ZERO_DOWNTIME.md     # full architecture / deployment guide
tests/                    # runtime unit tests
chicken_road_web/         # static frontend for the chicken-road game
plinko_web/               # static frontend for plinko
```

## Quick start (single-instance, polling)

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-runtime.txt
cp .env.example .env  # fill in BOT_TOKEN and BOT_OWNER_IDS
python bot.py
```

Then DM the bot from an admin account:

* `/listplugins` — show currently-loaded plugins
* `/reload <name>` — hot-swap a plugin without restarting

## Three deployment modes

The runtime supports the three approaches described in
[docs/ZERO_DOWNTIME.md](./docs/ZERO_DOWNTIME.md):

1. **Hot reload** — `python bot.py`, then `/reload <plugin>` from an admin.
   Zero-second swap of any plugin module.
2. **Blue-green webhook** — two `mycasino-bot@blue` and `mycasino-bot@green`
   systemd units behind nginx.  `deploy/blue_green_switch.sh deploy <ref>`
   brings up the inactive color, waits for health, flips nginx, drains
   the old color.
3. **Decoupled (Redis Streams)** — one tiny
   `mycasino-receiver.service` writes incoming Telegram updates into a
   Redis Stream; N `mycasino-worker@N.service` workers consume and
   dispatch.  Workers can be killed / upgraded freely; updates buffer in
   Redis.

## Tests

```
pip install -r requirements-dev.txt
pytest
```

## License

Proprietary — © the mycasino authors.  See repo settings for licensing.
