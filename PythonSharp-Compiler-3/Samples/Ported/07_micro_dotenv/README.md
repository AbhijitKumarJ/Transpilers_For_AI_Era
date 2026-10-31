# Ported 07: Micro DotEnv

A ported micro subset of the `python-dotenv` library implemented in PythonSharp (`.ps`). Demonstrates file I/O, dictionary data structures (`Dict<string, string>`), loop control (`continue`), string splitting, quote unescaping, and environment variable synchronization (`os.environ`).

## Project Structure

- `MicroDotEnv.psproj`: PythonSharp project file specifying assembly `MicroDotEnv` and target `py3.11`.
- `DotEnv.ps`: Core implementation of `DotEnv` with `.env` syntax parsing and OS environment loading.
- `run_dotenv.py`: Verification harness testing in-memory parsing, quotes and comments, and live `os.environ` mutation.

## Features

- **Robust Key-Value Parsing**: Parses `KEY=VALUE`, `export KEY=VALUE`, inline `#` comments, and empty values.
- **Quote Unescaping**: Supports double-quoted values with escape sequences (`\n`, `\t`, `\"`) and single-quoted literal values.
- **Environment Injection**: `DotEnv.Load(path, overrideExisting)` seamlessly syncs loaded pairs into Python's `os.environ`.

## How to Build and Run

```bash
# Build the PythonSharp project
psc build Samples/Ported/07_micro_dotenv

# Run the test suite
python3 Samples/Ported/07_micro_dotenv/run_dotenv.py
```

