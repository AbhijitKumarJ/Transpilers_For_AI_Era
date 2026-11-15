# PythonSharp Compiler (`psc`) CLI Guide

**Status:** Active  
**Compiler version:** 0.2.0  
**Language version:** 0.2.0  

`psc` is the multi-pass static C#-to-Python 3.11+ transpiler and development toolkit. It compiles `.ps` / `.pysharp` projects into idiomatic Python 3.11+ source code and line-pinned PEP 552 bytecode (`.pyc`), manages multi-project dependencies, and provides Language Server Protocol (LSP) diagnostics and autocompletion.

---

## 0. Building the Compiler Dist Installer (`dist/`)

```bash
# Clean previous build artifacts
rm -rf dist/ build/ *.egg-info

# Build the distributable installer wheel (.whl) and source tarball (.tar.gz) into dist/
python -m build --outdir dist
# or using pyproject-build:
pyproject-build --outdir dist

# Install the built 0.2.0 compiler installer wheel
pip install dist/pythonsharp_compiler-0.2.0-py3-none-any.whl
# or with uv:
uv pip install dist/pythonsharp_compiler-0.2.0-py3-none-any.whl

# Verify CLI
psc --version
```

---

## 1. Command Reference

| Command | Aliases | Description |
| --- | --- | --- |
| `psc create <name>` | `psc new` | Generates a new starter PythonSharp project with `.psproj`, `ProjMain.ps`, `TestUtil.ps`, `run_main.py`, and `.ps.conf.json` |
| `psc build [target]` | — | Compiles `.ps` files and project dependencies into Python packages and line-pinned `.pyc` files |
| `psc rebuild [target]` | — | Cleans the output directory and triggers a complete fresh build of the target and its dependencies |
| `psc clean [target]` | — | Deletes compiled artifacts (`.py`, `.pyc`, directories) and build caches from the project `out_dir` |
| `psc add reference <path>` | `psc add-reference` | Adds a project dependency reference (`<ProjectReference>`) to a `.psproj` file |
| `psc run [target]` | — | Compiles the target project and dependencies, then executes a static `Main()` or specified entrypoint |
| `psc watch [target]` | — | Watches source files and rebuilds incrementally upon file changes |
| `psc check [target]` | — | Runs semantic analysis (Pass 1 & Pass 2) without emitting files; reports errors and warnings |
| `psc dump-ast [target]` | — | Emits lowered Python 3.11+ AST source directly to stdout without writing files |
| `psc format [target]` | — | Formats `.ps` source files with Allman brace style, operator spacing, and token preservation |
| `psc stubgen <package>` | — | Generates `.d.ps` stubs for an installed Python package (via pyright or stubgen) into `.ps-stubs/` |
| `psc bindgen <target>` | — | Generates `.d.ps` ambient stubs from Python `.pyi` type definitions with optional Triple-Surface bundles |
| `psc lsp` | — | Starts the Language Server Protocol (LSP) server over stdio for editor integrations (e.g., VS Code) |

---

## 2. Project Scaffolding: `psc create` / `psc new`

Generate a new runnable PythonSharp project from scratch with sensible defaults:

```bash
# Create project in a subfolder named 'MyApp'
psc create MyApp

# Or specify a custom target folder
psc create MyApp -o ./src/MyApp

# Use the 'new' alias
psc new Services
```

### Generated Starter Structure:
```text
MyApp/
├── MyApp.psproj       # XML project file with AssemblyName and TargetFramework
├── ProjMain.ps        # Entrypoint class with static Main(string[] args)
├── TestUtil.ps        # Utility class demonstrating cross-file namespace sharing
└── run_main.py        # Python runner harness pre-configured with sys.path for dist/
```

To run immediately:
```bash
cd MyApp
psc build
python run_main.py
```

---

## 3. Project Dependencies: `psc add reference`

PythonSharp supports multi-project dependency chains typical of multi-layered C# enterprise architectures (e.g. Core -> Domain -> Data -> Services -> App).

### Adding a Project Reference:

```bash
# In the App project directory, reference a Services project:
psc add reference ../Services/Services.psproj

# Or specify both the referenced project and the target project explicitly:
psc add reference ../Domain/Domain.psproj -p ../Services/Services.psproj

# Use the shorthand alias:
psc add-reference ../Core/Core.psproj -p ../Domain/Domain.psproj
```

### `.psproj` Project Reference Format:

`psc add reference` automatically resolves relative paths and inserts `<ProjectReference>` nodes into the target project file:

**XML Format (`.psproj`):**
```xml
<Project Sdk="PythonSharp.Sdk/0.1.0">
  <PropertyGroup>
    <AssemblyName>App</AssemblyName>
    <TargetFramework>py3.11</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="../Services/Services.psproj" />
  </ItemGroup>
</Project>
```

**TOML Format (`.psproj`):**
```toml
[project]
name = "App"
target_python = "py3.11"

project_references = [
    "../Services/Services.psproj",
]
```

### Dependency Build Semantics:
- **Topological Sorting:** `psc build` analyzes all transitive references, detects circular references (reporting an error), and builds dependencies in dependency-first order (e.g., Core, then Domain, then Data, then Services, then App).
- **Independent Compilation:** Any sub-project (e.g. `Domain` or `Data`) can be compiled independently without compiling its parent consumers.
- **Dist Artifact Merging:** When compiling a consumer project, compiled modules (`.py`), line-pinned bytecode (`.pyc`), and package subdirectories from all referenced dependencies are automatically copied into the consumer's `dist/` folder.
- **Assembly Isolation:** Each project's `ArtifactEmitter` only emits its own source units, preserving C# `internal` scope boundaries between assemblies.
- **Zero Path Configuration:** The consumer's `run_main.py` (which prepends its local `dist/` to `sys.path`) executes seamlessly because all dependency modules are present in `dist/`.

---

## 4. Multi-Depth & Multi-Folder Sub-Namespaces

In PythonSharp, physical folder layout does not dictate namespace names. Multiple files in different directories can share a namespace, or files in the same directory can belong to different sub-namespaces.

### Package vs. Module Layout in `dist/`:

To prevent Python package shadowing collisions (where a folder `ps_2/` shadows a file `ps_2.py`), `psc` automatically partitions namespaces:

1. **Parent Package Namespaces:** Any namespace that has child sub-namespaces declared in the same compilation emits directly to `.../__init__.py`.
2. **Leaf Namespaces:** Any namespace with no child sub-namespaces emits to `.../<name>.py`.
3. **Intermediate Packages:** Any directories between the output root and nested modules automatically receive `# Auto-generated PythonSharp package` `__init__.py` markers.

### Example Architecture:

Suppose a project declares the following namespaces across arbitrary folders:

```csharp
// ProjMain.ps
namespace Company.App;

// Services/OrderService.ps
namespace Company.App.Services;

// Services/Payments/Gateways/Stripe.ps
namespace Company.App.Services.Payments.Gateways.Stripe;

// Diagnostics/Telemetry.ps
namespace ThirdParty.Diagnostics.Telemetry;
```

When compiled with `psc build`, the emitted `dist/` structure is:

```text
dist/
├── company/
│   └── app/
│       ├── __init__.py                               # Contains Company.App types (No collision!)
│       └── services/
│           ├── __init__.py                           # Contains Company.App.Services types
│           └── payments/
│               ├── __init__.py                       # Package marker
│               └── gateways/
│                   ├── __init__.py                   # Package marker
│                   └── stripe.py                     # Contains Leaf Stripe types
└── third_party/
    └── diagnostics/
        ├── __init__.py                               # Package marker
        └── telemetry.py                              # Contains Leaf Telemetry types
```

### Child Sub-Namespace Resolution:
- Types declared in child sub-namespaces (e.g. `OrderService` in `Company.App.Services`) are automatically discoverable by parent namespaces (`Company.App`) in the same project without requiring explicit `using` statements.
- Cross-namespace type calls automatically synthesize idiomatic Python `from ... import ...` statements in the emitted AST.

---

## 5. Cleaning & Rebuilding: `psc clean` & `psc rebuild`

```bash
# Clean compiled artifacts and cache from dist/
psc clean

# Clean a specific project output folder
psc clean ./MyApp/MyApp.psproj -o ./MyApp/dist

# Rebuild from scratch (cleans out_dir, recompiles dependencies, and emits fresh artifacts)
psc rebuild

# Rebuild a subproject
psc rebuild ./Services/Services.psproj
```

---

## 6. Code Formatting: `psc format`

PythonSharp includes a built-in code formatter designed specifically for `.ps` source files:

```bash
# Format in-place all .ps files in current directory and subdirectories
psc format

# Format a specific file
psc format ./src/MathUtil.ps

# Check formatting without modifying files (returns non-zero exit code if unformatted)
psc format --check

# Format with custom indentation settings
psc format --tab-size 2
psc format --indent-tabs
```

### Formatting Rules:
- **Allman Brace Placement:** Opening braces `{` are placed on their own line for class, interface, enum, struct, method, and multi-line control statements.
- **Literal & Comment Integrity:** Verbatim strings (`@""`), interpolated strings (`$""`), and block/line comments (`/* ... */`, `// ...`) are masked before indentation and restored byte-for-byte without altering internal whitespace or newlines.
- **Punctuation & Operator Spacing:** Normalizes spacing around assignments (`=`), comparisons (`==`, `!=`, `<`, `>`), logical operators (`&&`, `||`), commas, and control-flow keyword parentheses (`if (...)`, `for (...)`).
- **Whitespace Sanitation:** Removes trailing whitespace and collapses consecutive empty lines.

---

## 7. Ambient `.d.ps` Declaration Generation

Whenever `psc build` or `psc rebuild` compiles a project, it automatically generates a companion ambient declaration header (`dist/<module>.d.ps`) alongside the `.py` and `.pyc` artifacts:

- **What is `.d.ps`?** Analogous to TypeScript's `.d.ts` declaration files, `.d.ps` files contain strongly typed signatures (`extern` methods, constructors, properties, records, and enums) without method implementation bodies.
- **Cross-Project Referencing:** When Project A references Project B via `<ProjectReference>`, `psc` copies Project B's `.d.ps` file into Project A's `dist/`. The Language Server Protocol (LSP) automatically ingests these declaration stubs, providing full autocompletion, parameter hints, and type checking across projects without needing to parse the referenced project's implementation bodies or rebuild during live coding.

---

## 8. Smart Stubs & Ecosystem Bindings: `psc stubgen` & `psc bindgen`

PythonSharp uses a **Layered Smart-Stub** architectural strategy to balance instant compiler startup (<50ms) and comprehensive Python ecosystem typing:

- **Layer 0 (Core Intrinsics):** Immutable primitive contracts, builtins, and attributes (`stdlib/00_core/`). Loaded unconditionally.
- **Layer 1 (Curated High-Value Domains):** Hand-crafted Python standard library modules and AI/scientific domains with zero-cost `[InlineTemplate]` lowerings (e.g. `@` matrix multiplication, `.T`) and Triple-Surface metadata (`stdlib/01_python_stdlib/`, `stdlib/02_scientific_and_ai/`). Loaded eagerly (~95 files, ~20ms).
- **Layer 2 (Extended Stdlib Long-Tail):** Typeshed standard library modules (`urllib`, `sqlite3`, `csv`, `tarfile`, `asyncio`, etc.). **Loaded lazily on-demand** only when matching namespaces are referenced in project `using` directives.
- **Layer 3 (Project 3rd-Party Stubs):** Discovered automatically from `<project_root>/.ps-stubs/` or `typings/`.

### One-Shot Stub Generation: `psc stubgen <package>`

Generate ambient `.d.ps` stubs for any installed Python library:

```bash
# Generate stubs for matplotlib into .ps-stubs/matplotlib/
psc stubgen matplotlib

# Generate stubs for PyTorch or HuggingFace Transformers
psc stubgen torch
psc stubgen transformers

# Generate with 4-file Triple-Surface bundle (primitives, raw, csharp bridge, enterprise)
psc stubgen pandas --triple-surface
psc stubgen sklearn --triple-surface
```

`psc stubgen` delivers a **100% automated, zero-manual-edit workflow**:
1. **Automated Discovery & AST Ingestion:** Discovers existing `typings/<package>` or automatically invokes `pyright --createstub <package>` or `stubgen -p <package>` in the background.
2. **Package Symbol Indexing:** Scans the entire `.pyi` package directory in memory (<0.3s for 300+ files), creating a cross-module AST symbol map.
3. **Automated Re-Export Synthesis:** Top-level package re-exports (`from pandas.io.api import read_csv as read_csv`, `__all__ = [...]`) are automatically detected and synthesized onto the primary static module class (e.g. `public static class Pandas`). They carry their true signatures, parameter defaults, and return types (e.g. `public static extern DataFrame ReadCsv(...)`), with necessary namespace imports (`using PythonSharp.Bridge.Pandas.Core.Frame;`) emitted automatically at the top of the bridge stub.
4. **Safe Unannotated Return Types & Indexers:** In Python typing, omitted return annotations (`def foo(x):`) denote untyped `Any` (`object`), whereas `-> None` denotes `void`. `psc stubgen` accurately maps unannotated returns to `object` and guarantees C# indexer getters (`this[object index] { get; }`) return `object` rather than invalid `void`.
5. **Runtime Overload Erasure (Rule PS002):** Automatically filters duplicate overloads that erase to identical Python runtime signatures, preventing compile-time ambiguities.

---

## 9. Dynamic Stub Layer Configuration: `.ps.conf.json`

To customize stub resolution, eliminate dual-definition conflicts between standard library stubs and 3rd-party stubs, and speed up compiler/LSP execution, PythonSharp supports a `.ps.conf.json` (or `pythonsharp.json` / `psconfig.json`) configuration file placed at your project or workspace root.

### Example `.ps.conf.json`:
```json
{
  "stub_layers": {
    "00_core": true,
    "01_python_stdlib": true,
    "02_scientific_and_ai": false,
    "03_typeshed_replica": true,
    "external_stubs": true
  },
  "disabled_packages": ["matplotlib"],
  "preferred_surface": 2
}
```

### Configuration Options:

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `stub_layers` | `object` | All `true` | Map of layer names (`00_core`, `01_python_stdlib`, `02_scientific_and_ai`, `03_typeshed_replica`, `external_stubs`) to booleans. Setting `"02_scientific_and_ai": false` disables the handcrafted stdlib stubs when using stubgen-generated ones. |
| `disabled_layers` | `list[str]` | `[]` | Alternative shorthand list of layers to disable (e.g. `["02_scientific_and_ai"]`). |
| `disabled_packages`| `list[str]` | `[]` | List of package names to exclude from standard library discovery to prevent dual-definition collisions (e.g. `["matplotlib"]`). |
| `external_stubs` | `bool` | `true` | Toggle loading of dedicated 3rd-party stubs from `.ps-stubs/` and `typings/`. |
| `preferred_surface`| `int` (1, 2, 3) | `null` | When set to `2`, loads **only Surface 0 (primitives)** and **Surface 2 (C# Idiomatic Bridge)**, filtering out `01_*.raw.d.ps` and `03_*.enterprise.d.ps`. Cuts loaded stub files in half and eliminates cross-surface completion clutter! |

Both `psc build` / `psc rebuild` and the Language Server `psc lsp` automatically detect and honor `.ps.conf.json`.

---

## 10. Language Features in Lowering

### C-Style `for` Loops:
- Standard integer loops lower into Python's native `for i in range(...)`:
  ```csharp
  for (int i = 0; i < 10; i++) { ... }
  // Lowers to:
  for i in range(0, 10, 1): ...
  ```
- Non-standard conditions or step expressions lower into robust `while` loops equipped with `try ... finally: <step>` blocks to guarantee iterator advancement across `continue` statements.

### Automatic `.ToString()` Lowering:
- Primitive variables and expressions calling `.ToString()` lower to Python's built-in `str(...)` or `.to_string()`:
  ```csharp
  double val = 42.5;
  string s = val.ToString();
  // Lowers to:
  s = str(val)
  ```
- User class `.ToString()` methods compile to native `__str__(self)` while also creating a `.to_string()` alias method for C# method-call compatibility.

---

## 11. Quality & Verification Workflow

```bash
# Check syntax and semantic types without writing files
psc check

# Enforce Triple-Surface migration levels (1=Raw, 2=Bridge, 3=Enterprise)
psc check --target-surface 3

# Run the project entrypoint
psc run

# Run with an explicit entrypoint method
psc run -e ProjMain.Main
```
