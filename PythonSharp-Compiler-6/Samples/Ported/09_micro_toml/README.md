# Ported: `09_micro_toml`

A zero-external-dependency TOML parser and serializer ported to **PythonSharp** (`.ps`), compiling to clean, idiomatic Python 3.11+.

Ported from concepts in `pytoml` and `toml`.

---

## Features

- **Scalar Primitives**:
  - Double-quoted strings with escape decoding (`\"`, `\n`, `\t`, `\\`)
  - Single-quoted literal strings
  - Signed integers (`int`) and floating-point numbers (`double`)
  - Booleans (`true`, `false`)
- **Complex Structures**:
  - Arrays (`[1, 2, 3]`), multiline arrays, and nested arrays (`[[1, 2], [3, 4]]`)
  - Inline tables (`{ a = 1, b = "hello" }`)
  - Dotted keys (`server.options.tls = true`)
- **Tables & Sections**:
  - Standard section tables (`[database]`, `[database.credentials]`)
  - Array of tables (`[[products]]`)
  - Comment filtering (`# ...`) outside quotes
- **Serialization**:
  - `Toml.Dumps(Dict<string, object> dict)` emitting formatted TOML with nested tables and array-of-tables
  - Full roundtrip parity (`Parse(Dumps(data)) == data`)

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/09_micro_toml -o Samples/Ported/09_micro_toml/dist

# 2. Run the test harness
python3 Samples/Ported/09_micro_toml/run_toml.py
```

