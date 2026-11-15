# PythonSharp User Manual

Welcome to **PythonSharp (`psc`)**, a statically typed, C#-flavored language that compiles directly to clean, idiomatic Python 3.11+ source code and PEP 552 line-pinned bytecode.

PythonSharp brings compile-time discipline, strict type safety, enterprise architecture patterns, and world-class IDE tooling to the Python ecosystem with **Zero Runtime Wrapper Tax**.

---

## 1. Introduction & Philosophy

### 1.1 The Transpiler for the AI Era
In modern software engineering, AI code generation and complex scientific libraries (PyTorch, Pandas, Matplotlib, Quantum Computing) have shifted the engineering bottleneck:
> **The primary bottleneck in modern software is no longer typing code; it is auditing, reviewing, and verifying it.**

Python code in scientific computing frequently relies on dense, cryptic shorthands, implicit tensor broadcasts, and magic kwargs. When LLMs generate hundreds of lines of such code, subtle bugs (such as transposed dimensions or shape mismatches) hide in plain sight.

PythonSharp solves this by providing:
- **Explicitness over Shorthand:** Verbose, strongly-typed C# declarations and LINQ pipelines that make every type transition, method invocation, and data flow completely obvious to reviewers and static analyzers.
- **Isomorphic Runtime Lowering:** Emitted Python is ordinary, clean, readable Python with no proprietary runtime library or heavy wrappers.
- **Tri-Modal Flexibility:** Developers can move seamlessly between raw Python C-extension APIs, idiomatic C# pipelines, and DDD enterprise domain interfaces.

### 1.2 Core Design Invariants
1. **Zero Runtime Wrapper Tax:** Compiled code imports native Python packages directly. Primitives (`int`, `string`, `List<T>`, `Dict<K,V>`) erase completely into native Python types (`int`, `str`, `list`, `dict`).
2. **Span Preservation:** Every line in compiled `.py` files is mapped directly to the originating `.ps` line, ensuring Python tracebacks, loggers, and debuggers point straight to your `.ps` source files.
3. **No Project Execution During Compilation:** The compiler never `exec`s, `eval`s, or imports user code during compilation.
4. **Deterministic Output:** Code generation is strictly deterministic and reproducible.

---

## 2. Installation & Environment Setup

### 2.1 Prerequisites
- Python 3.11, 3.12, or 3.13
- A virtual environment managed with `pip`, `venv`, or [`uv`](https://docs.astral.sh/uv/)

### 2.2 Building & Installing the Compiler Installer (`dist/`)

You can build the distributable installer packages (.whl and .tar.gz) directly from source into `dist/`:

```bash
# Clean previous build artifacts
rm -rf dist/ build/ *.egg-info

# Build the distributable installer wheel and tarball into dist/
python -m build --outdir dist
# or using pyproject-build:
pyproject-build --outdir dist

# Install the built 0.2.0 wheel installer into your environment:
pip install dist/pythonsharp_compiler-0.2.0-py3-none-any.whl
# or with uv:
uv pip install dist/pythonsharp_compiler-0.2.0-py3-none-any.whl
```

Or install from PyPI:

```bash
# Using uv (recommended)
uv venv .venv
source .venv/bin/activate
uv pip install pythonsharp-compiler

# Or using standard pip
python -m venv .venv
source .venv/bin/activate
pip install pythonsharp-compiler
```

Verify your installation:
```bash
psc --version
psc --help
```

### 2.3 Setting up Your Editor

#### Visual Studio Code
PythonSharp provides a dedicated VS Code extension (`editors/vscode/pythonsharp-0.1.0.vsix`):
```bash
code --install-extension editors/vscode/pythonsharp-0.1.0.vsix
```
Features included:
- Full syntax highlighting for `.ps`, `.pysharp`, `.pys`, and `.d.ps` files.
- Automated `psc lsp` language server lifecycle.
- **Go To Definition (`F12`)** across project files and bundled standard library stubs.
- Member vs. Namespace collision-free navigation.
- Real-time diagnostic squigglies (`PS000`–`PS005`).
- Status bar shortcuts and Command Palette integration.

#### Neovim
Add the following to your `init.lua`:
```lua
vim.filetype.add({
  extension = {
    ps = "pythonsharp",
    pysharp = "pythonsharp",
    pys = "pythonsharp",
  },
})

vim.lsp.start({
  name = "pythonsharp-lsp",
  cmd = { "psc", "lsp" },
  root_dir = vim.fs.dirname(vim.fs.find({ "*.psproj", "*.pysharpproj", ".git" }, { upward = true })[1]),
})
```

#### Helix
Add to `~/.config/helix/languages.toml`:
```toml
[[language]]
name = "pythonsharp"
scope = "source.ps"
file-types = ["ps", "pysharp", "pys", "d.ps", "d.pysharp", "d.pys"]
roots = ["*.psproj", "*.pysharpproj", ".git"]
language-servers = ["psc-lsp"]

[language-server.psc-lsp]
command = "psc"
args = ["lsp"]
```

---

## 3. Project Architecture & Anatomy

### 3.1 Scaffolding a New Project
To create a complete starter project, use `psc create` (or `psc new`):

```bash
psc create DataAnalyticsDemo
cd DataAnalyticsDemo
```

This scaffolds the following project layout:
```text
DataAnalyticsDemo/
├── DataAnalyticsDemo.psproj   # Project definition and configuration
├── .ps.conf.json              # Dynamic stub layers & surface configuration
├── ProjMain.ps                # Application entrypoint with static Main()
├── TestUtil.ps                # Helper utilities and business logic
├── run_main.py                # Zero-overhead Python execution launcher
└── .gitignore                 # Configured to ignore dist/ and build caches
```

### 3.2 The Project File (`.psproj`)
PythonSharp project files use standard MSBuild XML (or optional TOML):

```xml
<Project Sdk="PythonSharp.Sdk/0.1.0">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0-py3.13</TargetFramework>
    <RootNamespace>DataAnalyticsDemo</RootNamespace>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>

  <ItemGroup>
    <!-- Cross-project dependency references -->
    <ProjectReference Include="../CommonLib/CommonLib.psproj" />
  </ItemGroup>
</Project>
```

### 3.3 Building and Running
Compile your application with `psc build`:
```bash
psc build
```
This compiles your `.ps` source files into `dist/`, emitting:
- Fully typed, human-readable Python modules (`dist/data_analytics_demo.py`, etc.).
- Line-pinned Python bytecode (`dist/*.pyc`).
- Package markers (`__init__.py`).
- Deterministic build manifests (`dist/psc-manifest.json`).

Run your compiled application using the generated `run_main.py`:
```bash
python run_main.py
# or with uv:
uv run run_main.py
```
Or execute directly via the CLI:
```bash
psc run
```

---

## 4. PythonSharp Language Primer

PythonSharp uses clean C# 12+ syntax and compiles directly to standard Python 3.11+.

### 4.1 Namespaces and Usings
```csharp
namespace DataAnalyticsDemo;

// Standard C# imports
using System;
using System.Collections.Generic;

// Import external Python packages
extern using matplotlib.pyplot;
extern using pandas;
```

### 4.2 Primitives and Built-in Types
PythonSharp provides familiar C# types that erase seamlessly to native Python primitives:

| PythonSharp Type | Erased Python Type | Notes |
| :--- | :--- | :--- |
| `int`, `Int32`, `long` | `int` | Arbitrary precision integers |
| `double`, `float` | `float` | 64-bit IEEE floating-point |
| `string`, `String` | `str` | Unicode strings with interpolation (`$"..."`) |
| `bool`, `Boolean` | `bool` | `True` / `False` |
| `List<T>` | `list` | Python lists with `.Add()`, `.Count`, indexers |
| `Dict<TKey, TValue>` | `dict` | Python dictionaries with `.ContainsKey()`, `[k]` |
| `HashSet<T>` | `set` | Python sets |
| `Bytes` | `bytes` | Binary buffers with `.Slice()`, `.Concat()` |
| `object` | `object` | Universal object base |

### 4.3 Classes, Fields, and Auto-Properties
Classes compile with memory-efficient `__slots__` and structural `__ps_types__` nominal metadata:

```csharp
namespace Models;

public class Customer
{
    public int Id { get; set; }
    public string Name { get; set; }
    public double TotalSpend { get; private set; }

    public Customer(int id, string name, double initialSpend)
    {
        Id = id;
        Name = name;
        TotalSpend = initialSpend;
    }

    public void AddTransaction(double amount)
    {
        if (amount <= 0.0)
        {
            throw new ArgumentException("Transaction amount must be positive");
        }
        TotalSpend += amount;
    }

    public override string ToString()
    {
        return $"{Name} (ID: {Id}) - ${TotalSpend:F2}";
    }
}
```

### 4.4 Loops and Control Flow
PythonSharp supports modern C# loops, including classic C-style `for` loops lowered directly to Python `range(...)` calls:

```csharp
// C-style for loop (compiled directly to for i in range(0, 10, 1):)
for (int i = 0; i < 10; i++)
{
    Console.WriteLine($"Step: {i}");
}

// Foreach iteration over collections or iterables
foreach (var item in customerList)
{
    Console.WriteLine(item.Name);
}

// While loops
while (queue.Count > 0)
{
    var task = queue.Dequeue();
    task.Process();
}
```

### 4.5 Advanced Pattern Matching
PythonSharp features modern relational patterns, list patterns with rest/slice captures, and `var` bindings:

```csharp
public static string CategorizeScore(int score) => score switch
{
    >= 90 => "A Grade",
    >= 80 => "B Grade",
    >= 70 => "C Grade",
    _ => "Needs Improvement"
};

public static void ProcessTokens(List<string> tokens)
{
    switch (tokens)
    {
        case ["START", var id, ..var payload, "END"]:
            Console.WriteLine($"Packet {id} with {payload.Count} items");
            break;
        case []:
            Console.WriteLine("Empty packet");
            break;
        default:
            Console.WriteLine("Unrecognized packet shape");
            break;
    }
}
```

### 4.6 String-Backed Enums
Enum declarations with explicit `: string` types compile cleanly to Python 3.11's `enum.StrEnum`:

```csharp
public enum OrderStatus : string
{
    Pending = "pending",
    Processing = "processing",
    Shipped = "shipped",
    Delivered = "delivered"
}
```

### 4.7 Interfaces and Structural Duck-Typing
Interfaces compile to `@runtime_checkable typing.Protocol` definitions, allowing seamless duck-typing against both Python libraries and PythonSharp classes:

```csharp
public interface IDataFilter
{
    bool Match(string input);
}

public class PrefixFilter : IDataFilter
{
    public string Prefix { get; }
    public PrefixFilter(string prefix) => Prefix = prefix;

    public bool Match(string input) => input.StartsWith(Prefix);
}
```

### 4.8 LINQ Query and Fluent Syntax (Zero Wrapper Fusion)
LINQ methods (`.Select()`, `.Where()`, `.OrderBy()`, `.Take()`, `.ToList()`) are analyzed at compile-time and fused directly into high-speed Python list comprehensions and generator expressions:

```csharp
var highValueCustomers = customers
    .Where(c => c.TotalSpend > 1000.0)
    .OrderByDescending(c => c.TotalSpend)
    .Select(c => c.Name)
    .ToList();
```
*Emitted Python:*
```python
high_value_customers = [c.name for c in sorted([c for c in customers if c.total_spend > 1000.0], key=lambda c: c.total_spend, reverse=True)]
```

### 4.9 Python Metaprogramming
PythonSharp gives you first-class access to Python metaprogramming:
- `[PythonDecorator("lru_cache", MaxSize = 128)]`: Attaches native Python decorators.
- `[SchemaModel]`: Generates Pydantic v2 `BaseModel` classes with runtime validation.
- `[KwArgs]`: Accepts dynamic keyword arguments (`params object[] kwargs` -> `**kwargs`).
- `yield return`: Generates Python generator iterators.

---

## 5. The Triple-Surface Architecture

Real-world Python programming encompasses three divergent styles:
1. **Raw CPython ABI:** Low-level, snake_case, positional-only arguments, C-extensions.
2. **Idiomatic C#:** Strongly typed, PascalCase, builder APIs, method chaining.
3. **Enterprise DDD:** Dependency injection, repository interfaces, immutability, unit tests.

The **Triple-Surface Architecture** provides a tri-modal ladder allowing you to choose the exact surface tier appropriate for each layer of your application:

```text
┌────────────────────────────────────────────────────────┐
│  Surface 3: Enterprise Architecture                    │
│  Interfaces, Records, DTOs, Unit Testable Repositories │
└──────────────────────────┬─────────────────────────────┘
                           │ Canonical mapping
┌──────────────────────────▼─────────────────────────────┐
│  Surface 2: Idiomatic C# Bridge                        │
│  PascalCase static classes, Method Chaining, LINQ      │
└──────────────────────────┬─────────────────────────────┘
                           │ Inline erasure
┌──────────────────────────▼─────────────────────────────┐
│  Surface 1: Raw CPython ABI                            │
│  snake_case, 1:1 runtime mirrors, C-extension handles  │
└────────────────────────────────────────────────────────┘
```

- **Surface 0 (Primitives):** Ambient type handles marked with `[RuntimeType]` and `[MapsTo]`.
- **Surface 1 (Raw ABI):** Mirror of Python libraries using exact Python names (e.g. `pd.read_csv(...)`, `plt.plot(...)`).
- **Surface 2 (Idiomatic Bridge):** Modern C# PascalCase APIs (e.g. `Pandas.ReadCsv(...)`, `Pyplot.Plot(...)`).
- **Surface 3 (Enterprise):** Abstract domain records and repository contracts.

### Visualizing Surface Tiers with LSP Hover Cards
When hovering over any type or method in your editor, `psc lsp` renders an interactive Surface Ladder Badge showing the exact tier and the canonical Surface 2 target:

```markdown
(method) NDArray<double> np.ones(int rows, int cols)
Declared in stdlib/02_scientific_and_ai/01_numpy/01_numpy.raw.d.ps

---
Surface Tier: Surface 1 (Raw ABI — Python-native snake_case)
Canonical Target: PythonSharp.Numerics.Creation.ArrayFactory.CreateOnesMatrix
```

---

## 6. Configuring Stub Layers with `.ps.conf.json`

When developing enterprise applications, you may want to use dedicated stubs for certain packages (such as `matplotlib` or `pandas`) while keeping standard stubs for everything else.

PythonSharp provides project-level configuration via `.ps.conf.json`, `psconfig.json`, or `pythonsharp.json`:

```json
{
  "stub_layers": {
    "00_core": true,
    "01_python_stdlib": true,
    "02_scientific_and_ai": false,
    "03_typeshed_replica": false,
    "dedicated_stubs": true
  },
  "disabled_packages": [
    "matplotlib",
    "pandas"
  ],
  "preferred_surface": 2
}
```

### Configuration Options:
1. **`stub_layers`:**
   - `00_core`: Built-in C# primitives (`Console`, `Math`, `List<T>`, etc.). Always keep `true`.
   - `01_python_stdlib`: Ambient Python standard library stubs (`os`, `sys`, `json`, `math`, `csv`).
   - `02_scientific_and_ai`: Built-in scientific bundles. Set to `false` when generating dedicated library stubs.
   - `03_typeshed_replica`: Typeshed replica layer.
   - `dedicated_stubs`: Local `.ps-stubs/` and `typings/` folders.
2. **`disabled_packages`:** Selectively deactivates specific ambient packages from compiler ingestion to prevent collision with dedicated stubs.
3. **`preferred_surface` (`0`, `1`, `2`, or `3`):** Filters dedicated stubs down to Surface 0 and your preferred tier (e.g. `2` for Surface 2 Idiomatic Bridge). This halves memory overhead and eliminates Go-to-Definition ambiguity!

---

## 7. Generating Dedicated Stubs (`psc stubgen`)

PythonSharp's `psc stubgen` (alias: `psc bindgen`) automatically generates strongly-typed `.d.ps` declaration files from Python packages with **zero manual edits required**.

### 7.1 Automated Bindgen Capabilities
- **Cross-Package Symbol Indexing:** Scans all `.pyi` files across the library in under 0.3 seconds to locate symbol definitions across submodule boundaries.
- **Module Re-Export Synthesis:** Detects `from .submodule import func` and `__all__` exports, synthesizing complete static module classes (such as `Pyplot` or `pd`) with correct parameter and return types.
- **Unannotated Return Fallback:** Translates unannotated Python methods (`def func(): ...`) to return `object` rather than `void`, preventing illegal assignment compiler errors in C#.
- **Safe Indexer Generation:** Emits valid `public object this[object key] { get; set; }` properties for dictionary and DataFrame indexers.

### 7.2 Walkthrough: Matplotlib & Pandas
To generate dedicated stubs for Matplotlib and Pandas in your project:

```bash
# 1. Generate dedicated triple-surface stubs into .ps-stubs/
psc stubgen .venv/lib/python3.13/site-packages/matplotlib -o .ps-stubs/matplotlib --triple-surface
psc stubgen .venv/lib/python3.13/site-packages/pandas -o .ps-stubs/pandas --triple-surface

# 2. Add .ps.conf.json to project root
cat << 'EOF' > .ps.conf.json
{
  "stub_layers": {
    "00_core": true,
    "01_python_stdlib": true,
    "02_scientific_and_ai": false,
    "dedicated_stubs": true
  },
  "disabled_packages": ["matplotlib", "pandas"],
  "preferred_surface": 2
}
EOF

# 3. Build your project cleanly
psc rebuild
```

You can now use `Pyplot.Plot(...)`, `Pyplot.Title(...)`, `Pandas.ReadCsv(...)`, and DataFrame methods with full type checking and IntelliSense!

---

## 8. Multi-Project Enterprise Solutions

PythonSharp supports enterprise multi-project architectures using project-to-project references (`<ProjectReference>`).

### 8.1 Solution Structure
```text
EnterpriseSolution/
├── Core/
│   └── Core.psproj
├── Data/
│   └── Data.psproj        # References Core.psproj
├── Services/
│   └── Services.psproj    # References Core.psproj & Data.psproj
└── WebApp/
    └── WebApp.psproj      # References Services.psproj
```

### 8.2 Adding References via CLI
```bash
cd WebApp
psc add reference ../Services/Services.psproj
```

### 8.3 Topological Compilation & Cycle Detection
When you run `psc build WebApp/WebApp.psproj`:
1. `psc` recursively analyzes all referenced `.psproj` files.
2. It constructs a directed dependency graph and verifies there are no circular dependencies.
3. It compiles assemblies in topological order (`Core` -> `Data` -> `Services` -> `WebApp`).
4. It isolates each project's emission boundary, then merges emitted `.py` modules into the root application's `dist/` directory for seamless execution.

---

## 9. Language Server & IDE Integration

The PythonSharp Language Server (`psc lsp`) delivers rich IDE capabilities out of the box:

- **Precision Go-to-Definition (`F12`):**
  - Member identifiers take absolute precedence over colliding namespace names (e.g., `Pyplot.Legend()` navigates directly to the `Legend(...)` method in `02_pyplot.csharp.d.ps`, never to the `matplotlib.legend` namespace).
  - Half-open token column spans (`start_col <= col < end_col`) guarantee that clicking immediately after a member dot (`.`) selects the identifier, not the dot.
- **Real-Time Diagnostics:** Displays syntax errors, visibility violations (`PS001`), erasure collisions (`PS002`), missing symbols (`PS003`), type mismatches (`PS004`), and surface migration alerts (`PS005`).
- **Surface Ladder Hover Cards:** Displays active tier and canonical migration targets.
- **IntelliSense Auto-Completion:** Suggests keywords, project types, namespaces, and standard library members.

---

## 10. Diagnostics Reference & Troubleshooting

| Diagnostic Code | Severity | Root Cause | Solution |
| :--- | :--- | :--- | :--- |
| **`PS000`** | Error | Syntax, token, or parse error. | Check for missing semicolons, unbalanced braces, or invalid tokens. |
| **`PS001`** | Error | Accessing a `private` or `protected` member from outside its scope. | Make the member `public` or `internal`, or call an authorized public API. |
| **`PS002`** | Error | Overload ambiguity caused by Python primitive type erasure. | Overloaded methods must have distinct parameter arities or non-erasing signatures. |
| **`PS003`** | Error | Unresolved identifier, type, or namespace. | Add the required `using` directive, check spelling, or verify project references. |
| **`PS004`** | Error | Incompatible type assignment or invalid method call arguments. | Ensure expressions match expected types or insert explicit casts. |
| **`PS005`** | Warning | Triple-Surface migration violation (e.g., using Surface 1 raw APIs in an enterprise project). | Migrate to the recommended Surface 2 or Surface 3 API shown in the hint. |

---

## 11. Summary & Next Steps

You are now equipped to build scalable, strongly typed, enterprise-grade applications targeting the Python ecosystem with PythonSharp.

- Check the [CLI Cheatsheet](CHEATSHEET.md) for fast syntax references.
- Explore the [Triple Surface Architecture Guide](Triple%20Surface/README.md).
- Dive into the 54-part [Technical Blog Series](blogs/PLAN.md) for architecture deep dives, real-world case studies, and advanced compiler internals.
