# Level 2 — Blog 17: Ported 09 — Micro-Toml (`09_micro_toml`): Scanner State Machines & TOML Serialization

Welcome to **Tier 5: Data Structures & Parsing**!

In this tier, we face targets that test complex internal state machines, recursive dictionary trees, and structured data serialization without third-party dependencies.

We begin with **`09_micro_toml`**, ported from canonical concepts in the `pytoml` and `toml` packages.

In this post, we explore:
1. **The TOML Format**: Section headers (`[table]`), nested dotted tables (`[server.http]`), and arrays of tables (`[[users]]`).
2. **Project Layout**: The `.psproj` boundary and source architecture.
3. **The C# Implementation (`Toml.ps`)**: Character-by-character scanner state machines, quote unescaping, recursive dictionary path traversal, and serialization.
4. **The Transpiled Output (`micro_toml.py`)**: Type discrimination helpers (`IsDict`, `IsList`, `IsInt`) and zero-overhead dictionary mutations.
5. **The Verification Test Harness (`run_toml.py`)**: Validating full parsing, dotted keys, arrays of tables, and round-trip dump serialization.

---

## 1. The Challenge: Parsing TOML 1.0

TOML (Tom's Obvious Minimal Language) has become the standard configuration format for Python (`pyproject.toml`), Rust (`Cargo.toml`), and modern developer tools.

Unlike JSON or YAML, TOML combines simple key-value pairs with stateful table headers:

```toml
title = "PythonSharp Server Config"
port = 8080
enabled = true

[server.http]
host = "0.0.0.0"
workers = 4

[[users]]
name = "Ada Lovelace"
role = "Admin"

[[users]]
name = "Alan Turing"
role = "Cryptographer"
```

A complete TOML parser must:
1. **Track Global Context**: Subsequent key-value pairs belong to the most recently declared section header.
2. **Traverse Dotted Paths**: `[server.http]` requires navigating into `dict["server"]` (creating it if missing) and setting the active table to `dict["server"]["http"]`.
3. **Manage Arrays of Tables**: `[[users]]` must append a new dictionary to a list at `dict["users"]` and set the active table to that newly created dictionary.
4. **Parse Diverse Primitive Types**: Booleans (`true`/`false`), integers (`42`), floats (`3.14`), single-quoted raw strings, and double-quoted escaped strings.

---

## 2. Project Layout

The project lives under [`Samples/Ported/09_micro_toml/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/09_micro_toml/):

```
Samples/Ported/09_micro_toml/
├── MicroToml.psproj       # Project configuration manifest
├── Toml.ps                # C# TOML parser & serializer (566 lines)
├── README.md              # Documentation and build instructions
├── run_toml.py            # Automated test runner and round-trip verification
└── dist/
    └── micro_toml.py      # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `Toml.ps`

In [`Toml.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/09_micro_toml/Toml.ps), type discrimination and dictionary path navigation are central:

### 1. Zero-Cost Dynamic Type Discriminators
Because TOML produces heterogenous dictionaries (`Dict<string, object>`), we define inline type inspection predicates:

```csharp
namespace MicroToml;

using PythonSharp.Core;

public class Toml
{
    [InlineTemplate("isinstance({0}, bool)")]
    public static extern bool IsBool(object val);

    [InlineTemplate("isinstance({0}, int) and not isinstance({0}, bool)")]
    public static extern bool IsInt(object val);

    [InlineTemplate("isinstance({0}, float)")]
    public static extern bool IsFloat(object val);

    [InlineTemplate("isinstance({0}, str)")]
    public static extern bool IsString(object val);

    [InlineTemplate("isinstance({0}, list)")]
    public static extern bool IsList(object val);

    [InlineTemplate("isinstance({0}, dict)")]
    public static extern bool IsDict(object val);
```

### 2. Dotted Table Path Navigation
When a header like `[server.http]` is encountered:

```csharp
// Split "server.http" by "."
List<string> parts = headerName.Split(".");
Dict<string, object> cursor = root;

int p = 0;
while (p < parts.Count)
{
    string part = parts[p].Trim();
    if (p == parts.Count - 1)
    {
        // Terminal table
        if (!cursor.ContainsKey(part))
        {
            cursor[part] = new Dict<string, object>();
        }
        currentTable = AsDict(cursor[part]);
    }
    else
    {
        // Intermediate table
        if (!cursor.ContainsKey(part))
        {
            cursor[part] = new Dict<string, object>();
        }
        cursor = AsDict(cursor[part]);
    }
    p += 1;
}
```

### 3. Array of Tables (`[[users]]`)
```csharp
if (isTableArray)
{
    if (!cursor.ContainsKey(lastPart))
    {
        cursor[lastPart] = new List<object>();
    }
    List<object> tableList = AsList(cursor[lastPart]);
    Dict<string, object> newTable = new Dict<string, object>();
    tableList.Add(newTable);
    currentTable = newTable;
}
```

---

## 4. The Transpiled Output: `micro_toml.py`

Compiling with:
```bash
psc build Samples/Ported/09_micro_toml -o Samples/Ported/09_micro_toml/dist
```
emits [`Samples/Ported/09_micro_toml/dist/micro_toml.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/09_micro_toml/dist/micro_toml.py).

### Transpiled Snippet:
```python
# Auto-generated by PythonSharp (psc) — Bytecode line-pinned to Toml.ps
from __future__ import annotations

class Toml:
    __ps_types__ = ('MicroToml.Toml',)
    __slots__ = ()

    @staticmethod
    def parse(text: str) -> dict[str, object]:
        root: dict[str, object] = {}
        current_table: dict[str, object] = root
        lines: list[str] = text.split('\n')
        i: int = 0
        while i < len(lines):
            line: str = Toml.strip_comment(lines[i]).strip()
            i += 1
            if len(line) == 0:
                continue
            if line.startswith('[[') and line.endswith(']]'):
                # Array of tables handler
                header_name: str = line[2:len(line) - 2].strip()
                current_table = Toml.resolve_array_table(root, header_name)
            elif line.startswith('[') and line.endswith(']'):
                # Standard section table handler
                header_name: str = line[1:len(line) - 1].strip()
                current_table = Toml.resolve_table(root, header_name)
            else:
                # Key-value assignment
                eq_idx: int = line.find('=')
                key: str = line[0:eq_idx].strip()
                raw_val: str = line[eq_idx + 1:].strip()
                val: object = Toml.parse_value(raw_val)
                current_table[key] = val
        return root
```

---

## 5. Verification Test Suite

[`run_toml.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/09_micro_toml/run_toml.py) verifies parsing, arrays of tables, and dumps round-tripping:

```python
toml_content = """
# Server Configuration
title = "Micro TOML Test"
port = 8080
debug = true
ratio = 0.75

[database]
host = "localhost"
port = 5432

[[servers]]
name = "alpha"
ip = "10.0.0.1"

[[servers]]
name = "beta"
ip = "10.0.0.2"
"""

data = Toml.parse(toml_content)
assert data["title"] == "Micro TOML Test"
assert data["port"] == 8080
assert data["debug"] is True
assert data["ratio"] == 0.75
assert data["database"]["host"] == "localhost"

servers = data["servers"]
assert len(servers) == 2
assert servers[0]["name"] == "alpha" and servers[1]["name"] == "beta"

# Verify Round-trip Serialization
dumped = Toml.dumps(data)
reparsed = Toml.parse(dumped)
assert reparsed == data
```

Running the runner:
```bash
python3 Samples/Ported/09_micro_toml/run_toml.py
```
Outputs:
```
=== Step 1: Building MicroToml via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported Toml Functionality ===
[PASS] Toml.parse simple key-value pairs (string, int, float, bool)
[PASS] Toml.parse nested section tables ([server.http])
[PASS] Toml.parse array of tables ([[servers]])
[PASS] Toml.parse inline arrays ([1, 2, 3])
[PASS] Toml.dumps serialization verified
[PASS] Round-trip parse(dumps(parse(text))) equality verified

All micro-toml verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Robust State Machines**: Character-level scanning and stateful section navigation written in typed C# compiles into efficient Python string and dictionary manipulations.
2. **Recursive Dictionary Path Traversal**: Safely constructing arbitrary nested object graphs.
3. **Lossless Round-Trip Serialization**: Parsing and dumping produce identical data structures.

---

## Next Steps

Now let's tackle low-level bitwise operations and byte buffer packing!

In **[Blog 18: Ported 10 — Micro-BitArray (`10_micro_bitarray`): Bitwise Operations & Byte Packing](./18_ported_10_micro_bitarray_bitwise_ops_and_packing.md)**, we examine how adding bitwise operators to the compiler enabled pure-Python bit manipulation!

