# Sample 06: Triple-Surface Architecture & Migration Showcase

This sample demonstrates the **Tri-Modal Architecture Ladder** in PythonSharp, proving that code written at any surface level compiles to line-pinned, native Python with **Zero Runtime Wrapper Tax**.

---

## The Tri-Modal Ladder

| Surface Level | Namespace / API Style | Target Audience | Example Syntax | Lowered Python 3.11+ Output |
| :--- | :--- | :--- | :--- | :--- |
| **Surface 1: Raw Python ABI** | `using time;`<br/>`using numpy;`<br/>`using json;` | Data scientists & Pythonistas | `time.time();`<br/>`np.ones(2, 2);`<br/>`a.dot(b);` | `_py_time.time()`<br/>`np.ones((2, 2))`<br/>`a.dot(b)` |
| **Surface 2: Idiomatic C# Bridge** | `using PythonSharp.Time;`<br/>`using PythonSharp.NumPy;`<br/>`using PythonSharp.Json;` | C# .NET Developers migrating Python code | `Time.NowEpoch();`<br/>`np.Ones(2, 2);`<br/>`a.Dot(b);` | `_py_time.time()`<br/>`_np.ones((2, 2))`<br/>`a.dot(b)` |
| **Surface 3: Enterprise Architecture** | `using PythonSharp.System.Diagnostics;`<br/>`using PythonSharp.Numerics.Creation;`<br/>`using PythonSharp.Serialization.Json;` | Enterprise Architects & Large-Scale Systems | `SystemClock.GetUnixTimestampSeconds();`<br/>`ArrayFactory.CreateOnesMatrix(2, 2);`<br/>`a.MultiplyMatrix(b);` | `_py_time.time()`<br/>`_np.ones((2, 2))`<br/>`a @ b` |

---

## Key Technical Achievements

1. **Zero Runtime Wrapper Tax**:
   - There are **no adapter objects, no reflection wrappers, and no proxy classes** generated at runtime.
   - All method and property calls erase completely at compile time into direct Python expressions (e.g. `a.MultiplyMatrix(b)` erases directly to Python's native matrix operator `a @ b`).
2. **Metadata-Driven Migration**:
   - Each stub in `stdlib/01_python_stdlib/` and `stdlib/02_scientific_and_ai/` is decorated with `[SurfaceLevel(N)]` and `[CanonicalApi("...")]`.
   - The PythonSharp LSP server (`psc lsp`) renders interactive hover cards revealing the tri-modal ladder and canonical migration paths.
   - The transpiler (`psc check --target-surface 3`) emits actionable `WARNING [PS005]` diagnostics whenever legacy Surface 1 or Surface 2 APIs are referenced in an enterprise codebase.

---

## How to Build and Run

```bash
# 1. Compile the PythonSharp project into dist/
psc build Samples/06_triple_surface_migration/TripleSurface.psproj -o Samples/06_triple_surface_migration/dist

# 2. Execute the verification runner
python3 Samples/06_triple_surface_migration/run_triple_surface.py
```

