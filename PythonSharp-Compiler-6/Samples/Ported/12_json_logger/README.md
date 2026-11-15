# Ported: `12_json_logger`

A structured JSON log formatter integrated with Python's standard `logging` framework, ported to **PythonSharp** (`.ps`), compiling to clean Python 3.11+.

Ported from concepts in the `python-json-logger` library.

---

## Features

- **Structured JSON Output**: Formats standard Python `logging.LogRecord` objects into JSON lines.
- **Timestamp ISO-8601 Formatting**: Millisecond-precision UTC/local ISO-8601 timestamps (`2026-05-10T14:30:00.123Z`).
- **Configurable Field Renaming**: Map standard fields like `timestamp`, `level`, and `message` to custom keys like `@timestamp`, `severity`, or `msg`.
- **Extra Payload Merging**: Arbitrary dictionaries passed via `logger.info("...", extra={"user_id": 42})` are unpacked and merged into the root JSON object.
- **Exception Serialization**: Full exception tracebacks serialized into `exception` fields when `exc_info=True`.

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/12_json_logger -o Samples/Ported/12_json_logger/dist

# 2. Run the test harness
python3 Samples/Ported/12_json_logger/run_logger.py
```

