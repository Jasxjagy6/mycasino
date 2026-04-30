# Zero-Downtime Architecture

The casino bot runs against real money.  Every dropped Telegram update
is a wager that doesn't get placed, a withdrawal that doesn't get
acknowledged, or a bonus that doesn't get awarded.  This document
describes the three independent strategies the runtime layer offers
for deploying the bot **without ever dropping an update**, and how to
combine them.

## TL;DR

| Strategy                    | When to use                           | Code             | Dropped updates? |
| --------------------------- | ------------------------------------- | ---------------- | ---------------- |
| Hot module reload           | Patch a single feature, dev iteration | `runtime.hot_reload` | none |
| Blue-green webhook          | Major version upgrade, schema migrate | `runtime.blue_green` + nginx | none |
| Decoupled receiver/worker   | Horizontal scale, frequent worker restarts | `runtime.queue_receiver` + `runtime.queue_worker` | none (Redis buffers) |

You can run any combination.  Production typically runs **all three**:
nginx in front of two webhook colors, each color built on top of the
queue receiver/worker pair, with hot-reload available to admins inside
each worker for live patches.

---

## 1. Hot Module Reload

Casino feature code lives under [`plugins/`](../plugins/) as small
modules (e.g. `plugins/example_blackjack.py`).  Each plugin exports
`register(ctx)`.  When an admin issues `/reload <plugin>`, the runtime:

1. Calls the plugin's `on_unload(ctx)` (if defined).
2. Cancels every background task the plugin spawned via
   `ctx.spawn_task(...)`.
3. Removes every PTB handler the plugin registered via
   `ctx.add_handler(...)`.
4. Calls `importlib.reload(module)` to pick up the new source on disk.
5. Calls the **new** module's `register(ctx)` and `on_reload(ctx)`.
6. Carries over `ctx.state` so per-user balances, in-flight games,
   etc. survive the swap.

If `register()` raises on the new version, the manager rolls back to
the old handlers — **the bot never enters a half-loaded state**.

### Admin commands

* `/reload <plugin>` — swap a single plugin
* `/reloadall` — swap every loaded plugin
* `/loadplugin <plugin>` / `/unloadplugin <plugin>` — load or remove
* `/listplugins` — show loaded plugins, version, handler count
* `/runtimestatus` — process uptime, plugin count, Redis stream stats

Authorisation defers to `bot.is_admin`; you can also set
`BOT_OWNER_IDS=12345,67890` in the env.

### Writing a plugin

```python
# plugins/my_feature.py
from telegram.ext import CommandHandler

async def _ping(update, ctx):
    await update.message.reply_text("pong")

def register(ctx):
    ctx.add_handler(CommandHandler("ping", _ping))

async def on_load(ctx):
    ctx.logger().info("my_feature loaded")
```

That's it.  Drop the file in `plugins/`, run `/loadplugin my_feature`,
edit the file, run `/reload my_feature`.

### State that survives reloads

Anything you stick in `ctx.state` (a plain `dict`) is carried over to
the reloaded version of the module.  Use it for caches, in-flight game
state, per-user data structures, etc.

> **Don't** rely on module-level globals for persistent state — the
> module is replaced on reload.

---

## 2. Blue-Green Webhook

Telegram pushes updates to a public HTTPS endpoint.  Two PTB
applications run on different local ports (`8000` for blue, `8001` for
green); nginx routes `/bot_webhook` to whichever is **active** based
on a single-line config file.

### Switch flow

`deploy/blue_green_switch.sh deploy <git-ref>` performs:

1. Detect the current active color (CURR) — read
   `/etc/nginx/active_color.conf`.
2. Pick the inactive color (NEXT) — opposite of CURR.
3. Check out `<git-ref>` into `/opt/mycasino-${NEXT}` and install deps.
4. `systemctl restart mycasino-bot@${NEXT}` (the systemd unit binds
   port 8000 if `${NEXT}=blue`, 8001 if `green`).
5. Poll `http://127.0.0.1:9000/healthz` (blue) or `:9001/healthz`
   (green) until 200 — the bot's `runtime.blue_green` side-car only
   reports ready after `post_init` finishes.
6. Atomically rewrite `active_color.conf` to `"NEXT"` and run
   `nginx -s reload`.  The reload is itself zero-downtime (nginx
   workers finish in-flight requests before exiting).
7. SIGTERM the old color.  The bot's drain handler stops accepting
   new updates, drains in-flight ones, and exits cleanly.

### Why this is zero-downtime

* nginx reload preserves accepted connections.
* The new color is fully booted (Redis, Postgres, deposit system,
  helper bots, etc.) before nginx flips.
* The old color drains for `DRAIN_GRACE` (default 30s) so any
  Telegram update that nginx already proxied has time to finish.

### nginx config

See [`deploy/nginx/mycasino.conf`](../deploy/nginx/mycasino.conf).

---

## 3. Decoupled (Receiver + Workers + Redis Stream)

This is the highest-availability mode and how the prompt's
"enterprise-grade" approach is implemented.

```
                 ┌──────────────┐         ┌────────────────────────┐
   Telegram ───► │   receiver   │────────►│   Redis Stream         │
                 │ (aiohttp:8200)│  XADD  │  mycasino:updates      │
                 └──────────────┘         │  capped MAXLEN ~ 100k  │
                                          └──────┬─────────────────┘
                                                 │ XREADGROUP / XAUTOCLAIM
                              ┌──────────────────┼───────────────────┐
                              ▼                  ▼                   ▼
                       ┌────────────┐     ┌────────────┐      ┌────────────┐
                       │  worker-1  │     │  worker-2  │ ...  │  worker-N  │
                       └────────────┘     └────────────┘      └────────────┘
```

### Receiver (`runtime.queue_receiver`)

Tiny aiohttp app.  Two routes:

* `POST /bot_webhook` — validates `X-Telegram-Bot-Api-Secret-Token`,
  parses JSON, `XADD`s to the stream with `MAXLEN ~ 100000` so memory
  is bounded.
* `GET /healthz` — pings Redis.

Because the receiver imports nothing from `bot.py`, it almost never
needs to be redeployed.  When you do redeploy it, it starts back up
in <1s — Telegram retries are well within tolerance.

### Worker (`runtime.queue_worker`)

Each worker:

1. Builds a real PTB `Application` via the factory selected by
   `MYCASINO_APP_FACTORY` (default `bot:_build_worker_application`).
2. Creates the consumer group if it doesn't exist
   (`XGROUP CREATE ... MKSTREAM`).
3. `XREADGROUP > ` in a loop, dispatching each entry through
   `Update.de_json` into `application.update_queue`.
4. `XACK`s entries only after dispatch succeeds.
5. Runs an `XAUTOCLAIM` task in the background to recover entries
   left pending by crashed workers.

### Update lifecycle in worker mode

* **Worker crash before XACK** — `XAUTOCLAIM` picks up the entry
  after `MYCASINO_QUEUE_CLAIM_IDLE_MS` (default 60s).
* **Receiver crash** — Telegram retries the webhook (the Bot API
  retries a webhook for up to 24h).  Set `secret_token` so attackers
  can't fake updates while the receiver is down.
* **Redis crash** — the receiver returns 503; Telegram retries.  AOF
  persistence (see `deploy/redis.conf.example`) keeps the stream's
  unacked entries across restarts.

### Scaling

```
sudo systemctl start mycasino-worker@1
sudo systemctl start mycasino-worker@2
sudo systemctl start mycasino-worker@3
...
```

Workers share load via the consumer group.  No coordination needed.

### Restarting workers without dropping updates

```
sudo systemctl restart mycasino-worker@1
```

While `worker-1` is restarting, the other workers pick up its share.
If you restart **all** workers at once, updates buffer in the Redis
Stream for up to `MYCASINO_QUEUE_MAXLEN` entries and drain when the
workers come back.

---

## Combining all three

A typical production deployment looks like:

* nginx (in front, blue-green for the webhook endpoint)
* `mycasino-receiver` (one process, port 8200)
* `mycasino-worker@{1..N}` (N processes per color)
* Redis (with AOF, see [`deploy/redis.conf.example`](../deploy/redis.conf.example))

Routine patch deploy: `/reload <plugin>` from admin chat.<br>
Major upgrade: `deploy/blue_green_switch.sh deploy v2.0.0`.<br>
Worker scaling: `systemctl start mycasino-worker@N`.

## Operational checklists

### First-time setup

1. Provision Redis with the config in
   [`deploy/redis.conf.example`](../deploy/redis.conf.example).
2. Copy [`.env.example`](../.env.example) to `/etc/mycasino/blue.env`
   and `/etc/mycasino/green.env` (and `receiver.env`, `worker.env`).
3. Install the systemd units from [`deploy/systemd/`](../deploy/systemd/).
4. `nginx -t && systemctl reload nginx`.
5. `systemctl enable --now mycasino-receiver`.
6. `systemctl enable --now mycasino-worker@1` (and as many more as you want).
7. `systemctl enable --now mycasino-bot@blue`.
8. Set the Telegram webhook to `https://your-domain/bot_webhook`.

### Sanity-check

```
curl -fsS http://127.0.0.1:9000/healthz   # blue
curl -fsS http://127.0.0.1:9001/healthz   # green
curl -fsS http://127.0.0.1:8200/healthz   # receiver -> redis
deploy/blue_green_switch.sh status
```

### Hot-reload smoke test

1. Edit `plugins/example_coinflip.py`, change `HEADS_EMOJI`.
2. From the admin chat: `/reload example_coinflip`.
3. `/cf` — the new emoji shows up immediately.

### Decoupled smoke test

1. `dev_run_receiver.sh` and `dev_run_worker.sh` in two terminals.
2. Configure the bot's webhook URL to your local receiver.
3. Send a message; watch the worker log dispatch it.
4. `kill -TERM <worker pid>` — message buffer in Redis.
5. Restart the worker — it drains the buffer.
