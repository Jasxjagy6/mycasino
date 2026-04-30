"""Hot-reloadable casino feature plugins.

Each module under this package is an independently reloadable feature.
A plugin must define a top-level ``register(ctx)`` function; see
:class:`runtime.hot_reload.PluginContext` for the API and
``plugins/example_blackjack.py`` for a fully-worked example.

Optional lifecycle hooks (each receives the same ``ctx``):

* ``async def on_load(ctx): ...``      — called once after register on first load
* ``async def on_reload(ctx): ...``    — called after register on a reload
* ``async def on_unload(ctx): ...``    — called before handlers are removed

State that should survive a reload goes into ``ctx.state`` (a plain
dict).  Background tasks must be created via ``ctx.spawn_task`` so the
manager can cancel them when the plugin is reloaded or unloaded.

Discovery honours two env vars:

* ``MYCASINO_PLUGIN_ALLOWLIST`` — only plugins in this comma-separated
  list will be loaded.
* ``MYCASINO_PLUGIN_DENYLIST``  — plugins in this list will be skipped.
"""
