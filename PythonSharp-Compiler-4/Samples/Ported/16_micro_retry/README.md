# Ported: `16_micro_retry`

A resilience and retry utility with exponential backoff, exception filtering, and decorator wrapping, ported to **PythonSharp** (`.ps`), compiling to clean Python 3.11+.

Ported from concepts in the `retry` library.

---

## Features

- **Exponential Backoff**: Configurable `tries`, initial `delay`, `backoff` multiplier, and `max_delay` ceiling.
- **Exception Filtering**: Restricts retries to specified exception classes or tuples; unexpected errors bubble up immediately without burning retry attempts.
- **Exhaustion Semantics**: Re-raises the original underlying exception once all attempt quotas are exhausted via native `throw;` statements.
- **Dual Invocation**:
  - Direct execution: `Retry.Call(fn, args, tries=3, delay=0.1)`
  - Parameterized decorator: `@Retry.Decorator(tries=4, delay=0.01)`

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/16_micro_retry -o Samples/Ported/16_micro_retry/dist

# 2. Run the test harness
python3 Samples/Ported/16_micro_retry/run_retry.py
```

