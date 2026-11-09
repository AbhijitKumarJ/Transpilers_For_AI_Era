# PythonSharp Compiler (`psc`) CLI Guide

**Status:** Active  
**Compiler version:** 0.1.0  
**Language version:** 0.1.0  

`psc` is the multi-pass static C#-to-Python 3.11+ transpiler and development toolkit. It compiles `.ps` / `.pysharp` projects into idiomatic Python 3.11+ source code and line-pinned PEP 552 bytecode (`.pyc`), manages multi-project dependencies, and provides Language Server Protocol (LSP) diagnostics and autocompletion.

---

## 1. Command Reference

| Command | Aliases | Description |
| --- | --- | --- |
| `psc create <name>` | `psc new` | Generates a new starter PythonSharp project with `.psproj`, `ProjMain.ps`, `TestUtil.ps`, and `run_main.py` |
| `psc build [target]` | — | Compiles `.ps` files and project dependencies into Python packages and line-pinned `.pyc` files |
| `psc rebuild [target]` | — | Cleans the output directory and triggers a complete fresh build of the target and its dependencies |
| `psc clean [target]` | — | Deletes compiled artifacts (`.py`, `.pyc`, directories) and build caches from the project `out_dir` |
| `psc add reference <path>` | `psc add-reference` | Adds a project dependency reference (`<ProjectReference>`) to a `.psproj` file |
| `psc run [target]` | — | Compiles the target project and dependencies, then executes a static `Main()` or specified entrypoint |
| `psc watch [target]` | — | Watches source files and rebuilds incrementally upon file changes |
| `psc check [target]` | — | Runs semantic analysis (Pass 1 & Pass 2) without emitting files; reports errors and warnings |
| `psc dump-ast [target]` | — | Emits lowered Python 3.11+ AST source directly to stdout without writing files |
| `psc format [target]` | — | Formats `.ps` source files with Allman brace style, operator spacing, and token preservation |
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

## 8. Language Features in Lowering

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

## 7. Quality & Verification Workflow

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
