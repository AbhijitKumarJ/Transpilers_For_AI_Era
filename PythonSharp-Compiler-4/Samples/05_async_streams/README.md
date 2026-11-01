# Sample 05: Async Streams & Generators

Demonstrates:
- C# asynchronous streams with `IAsyncEnumerable<string>` and `yield return`.
- Lowering to native Python asynchronous generators.
- Seamless consumption with Python's standard `asyncio` and `async for` loop.

## Compilation & Execution

### 1. Compile the async stream service
```bash
psc build StreamService.ps -o dist
```

### 2. Run the asynchronous Python script
```bash
python3 run_async.py
```

