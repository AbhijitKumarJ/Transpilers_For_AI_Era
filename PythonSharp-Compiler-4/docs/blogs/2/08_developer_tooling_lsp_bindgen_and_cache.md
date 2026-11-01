# Level 2 — Blog 08: Developer Tooling Subsystems — LSP Protocol Server, Bindgen & Build Cache

In Blogs 01 through 07, we explored the complete compilation pipeline of **PythonSharp (`psc`)**. But a modern developer expects more than a CLI compiler: they expect rich editor support in VS Code, instant Go-To-Definition across project boundaries, seamless interop with existing Python libraries, and instant watch-mode compilation.

In this post, we explore the tooling and developer experience subsystems that make PythonSharp a joy to use:
1. **The Pure-Python LSP Server (`src/psc/lsp/`)**: How `psc lsp` implements the JSON-RPC Language Server Protocol to provide autocompletion, hover tooltips, and Go-To-Definition across files.
2. **Two-Way Interop with `ps-bindgen` (`src/psc/bindgen/`)**: How PythonSharp inspects external Python libraries (FastAPI, NumPy, Requests) and generates strongly typed `.d.ps` C# ambient headers.
3. **Continuous Watch Mode (`src/psc/watcher.py`)**: How `ProjectWatcher` uses SHA-256 fingerprint snapshots to provide sub-second incremental recompilation on file saves.

---

## 1. The Pure-Python Language Server Protocol (LSP) Server

When you open a `.ps` file in VS Code or any LSP-compatible editor, the editor spawns `psc lsp` over standard I/O (stdin/stdout).

The LSP subsystem lives in [`src/psc/lsp/server.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/lsp/server.py) and [`src/psc/lsp/protocol.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/lsp/protocol.py).

```mermaid
sequenceDiagram
    participant Editor as VS Code / Editor
    participant LSP as psc lsp (LanguageServer)
    participant Compiler as Compiler (Lexer, Parser, SymTab)

    Editor->>LSP: textDocument/didOpen (file:///App/Order.ps)
    LSP->>Compiler: Parse & collect symbols
    Compiler-->>LSP: DiagnosticBag
    LSP-->>Editor: textDocument/publishDiagnostics (live red squiggles)

    Editor->>LSP: textDocument/hover (line: 12, col: 15)
    LSP->>Compiler: Lookup symbol at span
    Compiler-->>LSP: MemberSymbol(name='CalculateTotal', type='decimal')
    LSP-->>Editor: Hover tooltip markdown: "(method) decimal Order.CalculateTotal()"

    Editor->>LSP: textDocument/definition (line: 12, col: 15)
    LSP->>Compiler: Lookup symbol definition span
    LSP-->>Editor: Location (file:///App/Order.ps#L45)
```

### 1. Zero External Dependencies
Most LSP implementations in Python rely on heavyweight frameworks like `pygls`. PythonSharp implements the JSON-RPC 2.0 framing protocol directly in [`src/psc/lsp/protocol.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/lsp/protocol.py):

```python
class JsonRpcProtocol:
    def read_message(self, stream: BinaryIO) -> dict | None:
        # Read HTTP-style headers: Content-Length: 124\r\n\r\n
        headers = {}
        while True:
            line = stream.readline().decode("latin1")
            if not line or line == "\r\n":
                break
            key, val = line.split(":", 1)
            headers[key.strip().lower()] = val.strip()

        length = int(headers.get("content-length", 0))
        body = stream.read(length).decode("utf-8")
        return json.loads(body)
```

### 2. Cross-File Go-To-Definition
When you right-click a symbol and choose **Go to Definition**:
1. The editor sends a `textDocument/definition` request with the cursor's `(line, character)` position.
2. `server.py` converts the URI to a local file path and locates the token at that position.
3. The server queries `symtab.lookup_type()` or `symtab.lookup_member()`.
4. It extracts the target's `SourceSpan(file_id, start_line, start_col, ...)` and returns an LSP `Location` object.
5. If the symbol is a standard library type (like `List<T>` or `Console.WriteLine`), it opens [`stdlib/PythonSharp.Core.d.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/stdlib/PythonSharp.Core.d.ps) directly at the definition!

---

## 2. Two-Way Interop with `ps-bindgen`

What happens when you want to call an external Python package from C# with full IntelliSense and type checking?

You run **`psc bindgen <python_package>`**.

The stub generator lives in [`src/psc/bindgen/generator.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/bindgen/generator.py) and [`src/psc/bindgen/type_converter.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/bindgen/type_converter.py).

### How Bindgen Analyzes Python Modules
1. **Reflection & Inspection**: `bindgen` imports the Python package or parses its `.pyi` type stubs into an `ast.AST`.
2. **Type Mapping (`type_converter.py`)**: Converts Python type annotations into C# equivalents:
   - `str` $\to$ `string`
   - `int` $\to$ `int`
   - `list[T]` $\to$ `List<T>`
   - `dict[K, V]` $\to$ `Dictionary<K, V>`
   - `Optional[T]` / `T | None` $\to$ `T?`
   - `Any` $\to$ `object?`
3. **Keyword Escaping**: Python identifiers that collide with C# keywords (e.g. `event`, `base`, `checked`) are escaped using the `@` verbatim prefix (`@event`, `@base`).
4. **Header Generation**: Emits an ambient `.d.ps` file:

```csharp
// Generated by psc bindgen from requests
namespace Requests;

[MapsTo("requests")]
public static class Requests
{
    [InlineTemplate("requests.get({0}, **{1})")]
    public static Response Get(string url, [KwArgs] Dictionary<string, object>? kwargs = null);

    [InlineTemplate("requests.post({0}, json={1})")]
    public static Response Post(string url, object json);
}
```

Now, your C# code can call `Requests.Get("https://api.github.com")` with static type checking, while emitting native `requests.get()` in Python!

---

## 3. Continuous Watch Mode: `ProjectWatcher`

During development, you don't want to switch to your terminal and type `psc build` every time you hit Save.

Running `psc watch` starts the continuous build daemon in [`src/psc/watcher.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/watcher.py):

```python
class ProjectWatcher:
    def watch(self) -> None:
        self._file_hashes = self._snapshot_hashes()
        print(f"[*] Watching {len(self._file_hashes)} file(s) for changes...")

        while True:
            time.sleep(self.poll_interval_sec)
            current_hashes = self._snapshot_hashes()
            changed = [f for f, h in current_hashes.items() if self._file_hashes.get(f) != h]

            if changed:
                print(f"[!] Change detected in {len(changed)} file(s). Rebuilding...")
                success, msg = self.on_build(self.config)
                self._file_hashes = current_hashes
                if success:
                    print(f"[✓] Rebuild succeeded in {msg}")
                else:
                    print(f"[✗] Build failed:\n{msg}")
```

Because `ProjectWatcher` integrates with `BuildCacheManager`, it only recompiles the files that actually changed, completing incremental rebuilds in **under 50 milliseconds**!

---

## Summary of Tooling Subsystem

| Tool / Module | Command | Purpose |
| :--- | :--- | :--- |
| **Language Server** | `psc lsp` | Powers VS Code with diagnostics, hovers, completions, and Go-To-Definition |
| **Stub Generator** | `psc bindgen <pkg>` | Generates C# ambient `.d.ps` files from Python libraries |
| **Project Watcher** | `psc watch` | Watches source trees and triggers instant incremental recompilations |
| **Compiler Cache** | Automatic | Uses SHA-256 digests to skip redundant builds with zero overhead |

---

## Next Steps: Track B Begins!

We have completed **Track A: Compiler Architecture & Code Layout**! We now understand the full compiler engine room.

Now, we enter **Track B: The Ported Libraries Masterclasses**. Over the next 17 blogs, we will analyze how 17 real-world Python packages were ported to PythonSharp, starting from the simplest and progressing to advanced async concurrency.

First up in **[Blog 09: Ported 01 — LeftPad (`01_leftpad`)](./09_ported_01_leftpad_strings_and_erasure.md)**: String manipulation, default parameters, and ambient standard library type erasure!

