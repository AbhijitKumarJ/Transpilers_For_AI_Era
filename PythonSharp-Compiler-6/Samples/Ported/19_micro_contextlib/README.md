# Sample Port 19: MicroContextLib (Tier 8: Systems & Resources)

A ported, strongly-typed PythonSharp implementation of resource lifecycle management and dynamic LIFO context unwinding inspired by Python's `contextlib` and `contextlib.ExitStack`.

## Architectural Highlights
- **Zero Runtime Wrapper Tax**: Automatically maps `IDisposable` interfaces to native Python `__enter__` and `__exit__` context manager dunders.
- **Guaranteed LIFO Reverse Cleanups**: Demonstrates deterministic resource unwinding in exact reverse acquisition order across both successful executions and simulated runtime exception paths.
- **Python `with` Statement Interoperability**: Compiled classes can be entered and exited via native Python `with` statements directly from standard Python.

## Features
- `ManagedResource`: Tracks acquisition and disposal events.
- `MicroExitStack`: Manages dynamic stacks of `IDisposable` instances and unwinds in LIFO order upon closure.
- `ContextPipeline`: Orchestrates multi-resource workflows under successful and failing scenarios.

## Compilation & Verification

```bash
# 1. Compile via PythonSharp compiler
psc build . -o dist

# 2. Run the automated test runner
python3 run_contextlib.py
```

