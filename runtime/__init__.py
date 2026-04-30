"""Zero-downtime runtime layer for the casino bot.

This package adds three independent (and composable) zero-downtime
deployment strategies on top of the existing 39k-line ``bot.py``:

1. **Dynamic Module Reloading** (``runtime.hot_reload`` +
   ``runtime.plugin_loader``).  Casino feature code lives in the
   ``plugins/`` directory.  Admins can issue ``/reload <plugin>`` and the
   plugin's handlers are swapped in-process via :func:`importlib.reload`
   without restarting the bot — no dropped updates, no missed wagers.

2. **Webhook + Blue-Green** (``runtime.blue_green``).  A drop-in helper
   that runs the PTB ``Application`` in webhook mode behind nginx.  Two
   ports (8000/8001) take turns serving traffic; the
   ``deploy/blue_green_switch.sh`` script flips the upstream atomically
   so users never notice a deploy.

3. **Decoupled Receiver/Worker** (``runtime.queue_receiver`` +
   ``runtime.queue_worker``).  A tiny aiohttp receiver pushes incoming
   Telegram updates into a Redis Stream.  One or more worker processes
   consume the stream and dispatch updates through the full PTB
   ``Application``.  Workers can be killed and restarted at any time;
   updates buffer in Redis for the few seconds the workers are gone, so
   no message is lost — the receiver itself is so small it almost never
   needs to restart.

The three strategies are independent: a deployment can pick any
combination (e.g. polling + hot reload for development, webhook +
blue-green for production frontends, queue receiver + N workers for
horizontally-scaled processing).

Public entry points
-------------------

- :func:`register_runtime` — call once after building the PTB
  ``Application`` to wire admin commands and load plugins.
- :func:`get_plugin_manager` — access the singleton
  :class:`runtime.plugin_loader.PluginManager`.
- :func:`run_blue_green_webhook` — drop-in replacement for
  ``app.run_webhook`` that adds a ``/healthz`` endpoint and graceful
  shutdown for blue-green deploys.

The runtime package never imports ``bot.py``; integration is one-way so
that ``bot.py`` can opt in or out and so that hot-reload doesn't tear
down the runtime itself.
"""

from runtime.plugin_loader import PluginManager, get_plugin_manager
from runtime.hot_reload import HotReloadManager
from runtime.admin_handlers import register_admin_handlers
from runtime.bootstrap import register_runtime

__all__ = [
    "PluginManager",
    "HotReloadManager",
    "get_plugin_manager",
    "register_admin_handlers",
    "register_runtime",
]

__version__ = "1.0.0"
