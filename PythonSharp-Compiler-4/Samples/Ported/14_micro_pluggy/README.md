# Ported: `14_micro_pluggy`

A micro hook and plugin management engine inspired by `pytest`'s `pluggy`, ported to **PythonSharp** (`.ps`), compiling to clean Python 3.11+.

Ported from concepts in the `pluggy` library.

---

## Features

- **Hook Specifications (`HookSpec`)**:
  - Defines extension contracts and hook points (`on_user_signup`, `get_auth_token`).
  - Supports specification classes via `pm.AddHookspecs(specClass)`.
  - Configurable execution modes: multi-result accumulation or `firstresult=True`.
- **Plugin Management (`PluginManager`)**:
  - `Register(plugin)`: Automatically inspects registered plugin instances and binds matching methods to hooks.
  - `Unregister(plugin)`: Removes plugin implementations from all active hook callers.
  - `Call(hookName, args)`: Dispatches arguments to registered plugins and collects execution results.
- **Execution Strategies**:
  - **Sequential / Fan-out**: Runs every implementation and returns a list of results.
  - **First-Result-Wins**: Returns immediately on the first non-null result (ideal for authentication strategies, resolvers, or fallback pipelines).

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/14_micro_pluggy -o Samples/Ported/14_micro_pluggy/dist

# 2. Run the test harness
python3 Samples/Ported/14_micro_pluggy/run_pluggy.py
```

