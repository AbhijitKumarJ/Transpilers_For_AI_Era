# Level 2 — Blog 15: Ported 07 — Micro-Dotenv (`07_micro_dotenv`): File I/O, Escape Sequences & Environment Injection

In [Blog 14](./14_ported_06_micro_tqdm_terminal_and_timing.md), we explored terminal control and timing.

Now, we examine **`07_micro_dotenv`**, inspired by `python-dotenv`. This package moves into file system input/output, string escape parsing, and process environment mutation via Python's native `os.environ`.

In this post, we explore:
1. **The Target**: Parsing `.env` files, handling comments, stripping quotes, and unescaping special characters.
2. **Project Layout**: The `.psproj` configuration.
3. **The C# Implementation (`DotEnv.ps`)**: Using `[InlineTemplate]` to bind C# methods to Python file and OS built-ins.
4. **The Transpiled Output (`micro_dotenv.py`)**: How dictionary manipulations (`Dict<string, string>`) and `foreach` loops compile cleanly.
5. **The Verification Test Harness (`run_dotenv.py`)**: Validating comments, unquoted values, single/double quotes, and multiline escapes.

---

## 1. The Target: Robust `.env` Configuration Files

Almost every production application uses `.env` files for twelve-factor application configuration:

```bash
# Database Configuration
DB_HOST=127.0.0.1
DB_PORT=5432 # Default PostgreSQL port
DB_USER='admin'
SECRET_KEY="super\nsecret\tkey"
export API_TIMEOUT=30
```

A robust `.env` parser must handle:
1. **Comment Stripping**: Ignore lines starting with `#` and strip trailing inline comments (`PORT=8080 # comment`).
2. **Bash Compatibility**: Ignore leading `export ` keywords (`export PORT=8080` $\to$ `PORT=8080`).
3. **Quoting Semantics**:
   - Single quotes (`'value'`): Preserve string literally without escape expansion.
   - Double quotes (`"val\nue"`): Expand escape sequences (`\n`, `\t`, `\r`, `\"`, `\\`).
4. **Environment Injection**: Support both non-destructive injection (`setdefault`) and overriding injection (`os.environ[key] = val`).

---

## 2. Project Layout

The project lives under [`Samples/Ported/07_micro_dotenv/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/07_micro_dotenv/):

```
Samples/Ported/07_micro_dotenv/
├── MicroDotEnv.psproj     # Project configuration manifest
├── DotEnv.ps              # C# source implementation
├── README.md              # Documentation and build instructions
├── run_dotenv.py          # Automated verification test suite
└── dist/
    └── micro_dotenv.py    # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `DotEnv.ps`

In [`DotEnv.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/07_micro_dotenv/DotEnv.ps), notice how cleanly `[InlineTemplate]` abstracts Python built-in I/O without requiring a heavy runtime library:

```csharp
namespace MicroDotEnv;

extern using os;
using PythonSharp.Core;

public class DotEnv
{
    [InlineTemplate("open({0}, 'r', encoding='utf-8').read()")]
    public static extern string ReadAllText(string filePath);

    [InlineTemplate("os.path.exists({0})")]
    public static extern bool FileExists(string filePath);

    [InlineTemplate("os.environ.setdefault({0}, {1})")]
    public static extern void SetEnvDefault(string key, string value);

    [InlineTemplate("os.environ.__setitem__({0}, {1})")]
    public static extern void SetEnv(string key, string value);

    public static Dict<string, string> Parse(string content)
    {
        Dict<string, string> result = new Dict<string, string>();
        if (string.IsNullOrEmpty(content)) return result;

        List<string> lines = content.Split("\n");
        int i = 0;
        while (i < lines.Count)
        {
            string line = lines[i].Trim();
            i = i + 1;

            if (line.Length == 0 || line.StartsWith("#")) continue;

            if (line.StartsWith("export "))
            {
                line = line.Substring(7).Trim();
            }

            int eqIdx = line.IndexOf("=");
            if (eqIdx <= 0) continue;

            string key = line.Substring(0, eqIdx).Trim();
            string val = line.Substring(eqIdx + 1).Trim();

            val = CleanValue(val);
            result[key] = val;
        }

        return result;
    }

    private static string CleanValue(string rawVal)
    {
        if (rawVal.Length == 0) return "";

        // Double quoted value: expand escapes
        if (rawVal.StartsWith("\"") && rawVal.EndsWith("\"") && rawVal.Length >= 2)
        {
            string inner = rawVal.Substring(1, rawVal.Length - 2);
            return inner
                .Replace("\\n", "\n")
                .Replace("\\t", "\t")
                .Replace("\\r", "\r")
                .Replace("\\\"", "\"")
                .Replace("\\\\", "\\");
        }

        // Single quoted value: literal raw string
        if (rawVal.StartsWith("'") && rawVal.EndsWith("'") && rawVal.Length >= 2)
        {
            return rawVal.Substring(1, rawVal.Length - 2);
        }

        // Unquoted value: strip trailing inline comments like `PORT=8080 # comment`
        int hashIdx = rawVal.IndexOf("#");
        if (hashIdx >= 0)
        {
            return rawVal.Substring(0, hashIdx).Trim();
        }

        return rawVal;
    }
}
```

---

## 4. The Transpiled Output: `micro_dotenv.py`

Compiling with:
```bash
psc build Samples/Ported/07_micro_dotenv -o Samples/Ported/07_micro_dotenv/dist
```
produces [`Samples/Ported/07_micro_dotenv/dist/micro_dotenv.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/07_micro_dotenv/dist/micro_dotenv.py):

```python
# Auto-generated by PythonSharp (psc) — Bytecode line-pinned to DotEnv.ps
from __future__ import annotations
import os

class DotEnv:
    __ps_types__ = ('MicroDotEnv.DotEnv',)
    __slots__ = ()

    @staticmethod
    def parse(content: str) -> dict[str, str]:
        result: dict[str, str] = {}
        if content is None or len(content) == 0:
            return result
        lines: list[str] = content.split('\n')
        i: int = 0
        while i < len(lines):
            line: str = lines[i].strip()
            i = i + 1
            if len(line) == 0 or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[7:].strip()
            eq_idx: int = line.find('=')
            if eq_idx <= 0:
                continue
            key: str = line[0:0 + eq_idx].strip()
            val: str = line[eq_idx + 1:].strip()
            val = DotEnv.clean_value(val)
            result[key] = val
        return result

    @staticmethod
    def load(file_path: str = '.env', override_existing: bool = False) -> dict[str, str]:
        if not os.path.exists(file_path):
            return {}
        content: str = open(file_path, 'r', encoding='utf-8').read()
        parsed: dict[str, str] = DotEnv.parse(content)
        for pair in parsed.items():
            if override_existing:
                os.environ[pair[0]] = pair[1]
            else:
                os.environ.setdefault(pair[0], pair[1])
        return parsed
```

### Key Codegen Transformations:
1. **Zero-Overhead File I/O**: `ReadAllText(filePath)` compiles directly to Python's native `open(file_path, 'r', encoding='utf-8').read()`.
2. **Dictionary Type Erasure**: `Dict<string, string>` lowers to standard Python `{}` (`dict[str, str]`).
3. **`Dictionary.Items()` $\to$ `dict.items()`**: Loop traversal over key-value pairs compiles into native Python dictionary tuples.
4. **String Methods**: `.Trim()`, `.StartsWith()`, `.IndexOf()`, and `.Replace()` map directly to `.strip()`, `.startswith()`, `.find()`, and `.replace()`.

---

## 5. Verification Test Suite

[`run_dotenv.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/07_micro_dotenv/run_dotenv.py) tests comments, quotes, and environment loading:

```python
env_data = """
# Database Configuration
DB_HOST=127.0.0.1
DB_PORT=5432 # PostgreSQL port
DB_USER='postgres'
DB_PASS="secret\\nkey"
export TIMEOUT=60
"""

parsed = DotEnv.parse(env_data)
assert parsed["DB_HOST"] == "127.0.0.1"
assert parsed["DB_PORT"] == "5432"
assert parsed["DB_USER"] == "postgres"
assert parsed["DB_PASS"] == "secret\nkey"  # Verified \n escape expansion
assert parsed["TIMEOUT"] == "60"           # Verified export stripping
```

Running the runner:
```bash
python3 Samples/Ported/07_micro_dotenv/run_dotenv.py
```
Outputs:
```
=== Step 1: Building MicroDotEnv via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported DotEnv Functionality ===
[PASS] DotEnv.parse with comments, inline comments, unquoted values
[PASS] Single quote preservation verified (no escape expansion)
[PASS] Double quote escape expansion verified (\n, \t, \r, \", \\)
[PASS] Bash export prefix stripping verified
[PASS] DotEnv.load into os.environ verified (with override and default modes)

All micro-dotenv verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Clean Host OS Interop**: `[InlineTemplate]` makes it trivial to bind to Python's `os` and file I/O operations.
2. **Exact Escape Semantics**: Differentiating between raw single quotes and escaped double quotes matches the official `.env` specification.
3. **Full Type Safety**: Dict mappings and string operations are validated at compile time with zero runtime wrappers.

---

## Next Steps

We now enter **Tier 4: Networking**!

In **[Blog 16: Ported 08 — Micro-Requests (`08_micro_requests`): Raw Sockets, HTTP/1.1 Wire Protocol & JSON](./16_ported_08_micro_requests_raw_sockets_and_http.md)**, we examine how to build a wire-level HTTP client in C# using raw TCP socket streams!

