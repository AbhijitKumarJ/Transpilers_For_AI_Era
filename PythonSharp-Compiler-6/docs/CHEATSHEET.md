# PythonSharp CLI & Configuration Cheatsheet

A quick-reference guide for developers using the PythonSharp (`psc`) compiler, CLI tooling, project configurations, and language server.

---

## 1. Building the Dist Installer & Quick Installation

### Building the Compiler Installer (`dist/`)
```bash
# Clean previous build artifacts
rm -rf dist/ build/ *.egg-info

# Build the distributable installer wheel (.whl) and source tarball (.tar.gz)
python -m build --outdir dist
# or using pyproject-build:
pyproject-build --outdir dist

# Install the newly built 0.2.0 wheel installer into your environment:
pip install dist/pythonsharp_compiler-0.2.0-py3-none-any.whl
# or with uv:
uv pip install dist/pythonsharp_compiler-0.2.0-py3-none-any.whl

# Verify installation & view help
psc --version
psc --help
```

---

## 2. Project Lifecycle & Compilation

### Scaffolding New Projects
Every new project is automatically scaffolded with `<name>.psproj`, `ProjMain.ps`, `TestUtil.ps`, `run_main.py`, and `.ps.conf.json`:
```bash
# Scaffold a new starter project
psc create MyService
psc create MyDataLib --out-dir ./libs/MyDataLib

# Alias: 'new'
psc new AnalyticsDemo
```

### Building & Cleaning
```bash
# Standard incremental build (reads project root or .psproj directly)
psc build
psc build src/App.psproj

# Force full compilation (bypasses build cache)
psc build -f
psc build --force

# Specify custom output directory (default: dist/)
psc build --out-dir ./artifacts/dist

# Rebuild (clean dist/ + compile from scratch with all dependencies)
psc rebuild
psc rebuild src/App.psproj

# Clean build artifacts and compiler cache (.psc_cache/)
psc clean
psc clean src/App.psproj
```

### Static Analysis & Diagnostics (No Emission)
```bash
# Check code for syntax, type, access, and surface errors without writing to disk
psc check
psc check src/App.psproj

# Enforce a specific surface tier (emits PS005 warnings for violations)
psc check --target-surface 2
```

### Running Applications
```bash
# Execute the program's static Main() entrypoint (auto-detects Main)
psc run
psc run src/App.psproj

# Execute with explicit class and method entrypoint
psc run -e ProjMain.main
psc run src/App.psproj -e MyCompany.App.Program.Main

# Pass arguments to the program
psc run src/App.psproj -- --port 8080 --env production
```

### Continuous Watch Mode
```bash
# Watch project directory and incrementally recompile on any .ps change
psc watch
psc watch src/App.psproj

# Customize polling/debounce interval in seconds (default: 0.5s)
psc watch --interval 0.25
```

---

## 3. Project References (`<ProjectReference>`)

```bash
# Add a dependency reference from the current project to another project
psc add reference ../DataLayer/DataLayer.psproj
psc add reference ../Common/Common.psproj -p src/App.psproj

# Alias: 'add-reference'
psc add-reference ../Domain/Domain.psproj
```

### Project File Syntax (`.psproj`)
```xml
<Project Sdk="PythonSharp.Sdk/0.1.0">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0-py3.13</TargetFramework>
    <RootNamespace>MyCompany.MyService</RootNamespace>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>

  <ItemGroup>
    <!-- Cross-project dependencies compiled topologically -->
    <ProjectReference Include="../DataLayer/DataLayer.psproj" />
    <ProjectReference Include="../Common/Common.psproj" />
  </ItemGroup>
</Project>
```

---

## 4. Stub Generation (`psc stubgen` / `psc bindgen`)

Generate zero-manual-edit, strongly-typed `.d.ps` declaration files directly from Python packages or `.pyi` type definitions.

```bash
# Generate dedicated stubs from an installed package (e.g. pandas, matplotlib, torch)
psc stubgen .venv/lib/python3.13/site-packages/matplotlib -o .ps-stubs/matplotlib

# Generate complete 4-file Triple-Surface bundles (Surface 0, 1, 2, 3)
psc stubgen .venv/lib/python3.13/site-packages/pandas -o .ps-stubs/pandas --triple-surface

# Generate single raw ABI surface
psc stubgen .venv/lib/python3.13/site-packages/requests -o .ps-stubs/requests --no-triple-surface

# Dry-run stub generation (prints generated signatures to stdout without writing)
psc stubgen path/to/module.pyi --dry-run
```

---

## 5. Code Formatting & AST Inspection

```bash
# Format source files using standard Allman brace style
psc format src/ProjMain.ps
psc format --write src/ProjMain.ps

# Dump lowered Python source code to terminal for verification
psc dump-ast src/ProjMain.ps
psc dump-ast src/App.psproj
```

---

## 6. Language Server Protocol (`psc lsp`)

```bash
# Launch the headless JSON-RPC 2.0 language server on stdio
psc lsp
```

### Editor Integration Cheat Sheet
| Editor | Integration Method | Configuration Path |
| :--- | :--- | :--- |
| **VS Code** | Install `editors/vscode/pythonsharp-0.1.0.vsix` | `settings.json`: `"pythonsharp.serverPath": "psc"` |
| **Neovim** | Built-in LSP client | `vim.lsp.start({ name = "psc-lsp", cmd = { "psc", "lsp" } })` |
| **Helix** | `languages.toml` | `[language-server.psc-lsp] command = "psc" args = ["lsp"]` |
| **Sublime** | `LSP` package | `LSP.sublime-settings`: `"command": ["psc", "lsp"]` |

---

## 7. Project Configuration (`.ps.conf.json`)

Place `.ps.conf.json`, `psconfig.json`, or `pythonsharp.json` in the root of your workspace to dynamically control stub layers, eliminate IntelliSense conflicts, and select preferred surface tiers:

```json
{
  "$schema": "https://raw.githubusercontent.com/pythonsharp/psc/main/schemas/psconfig.schema.json",
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

### Property Reference:
- `stub_layers.00_core`: Built-in C# primitives (`Console`, `Math`, `List<T>`, `Dict<K,V>`, `Task`, etc.). Always `true`.
- `stub_layers.01_python_stdlib`: Bundled Python standard library stubs (`os`, `sys`, `json`, `math`, `csv`, etc.).
- `stub_layers.02_scientific_and_ai`: Bundled scientific stubs (`numpy`, `pandas`, `scipy`, `sklearn`, `torch`, etc.). Set to `false` when using dedicated `psc stubgen` stubs.
- `stub_layers.03_typeshed_replica`: Typeshed replica layer. Set to `true` when using raw Python typeshed stubs.
- `stub_layers.dedicated_stubs`: Local `.ps-stubs/` or `typings/` directory ingestion. Default: `true`.
- `disabled_packages`: Array of package names to skip from standard library ingestion (e.g. `["matplotlib"]`).
- `preferred_surface`: Restricts dedicated stubs to Surface 0 plus tier `1` (Raw snake_case), `2` (Idiomatic Bridge PascalCase), or `3` (Enterprise Domain Models).

---

## 8. Compiler Diagnostics & Error Codes

| Code | Severity | Description | Fix Hint |
| :--- | :--- | :--- | :--- |
| **`PS000`** | Error | Syntax or Lexical Error | Check mismatched brackets, missing semicolons, or invalid tokens. |
| **`PS001`** | Error | Visibility / Access Violation | Member or type is `private` or `protected`. Change access modifier or use public API. |
| **`PS002`** | Error | Overload Ambiguity or Type Erasure Collision | Two methods have identical types after Python primitive erasure. Rename method or differentiate parameters. |
| **`PS003`** | Error | Unresolved Type or Symbol Reference | Symbol not found in symtab. Add missing `using` directive or verify project reference. |
| **`PS004`** | Error | Type Check Failure or Incompatible Assignment | Incompatible type in assignment, return, or parameter. Apply explicit cast or adjust type. |
| **`PS005`** | Warning | Triple-Surface Migration Compliance | Surface tier violation (e.g. using Surface 1 Raw ABI when target surface is set to 2 or 3). |

---

## 9. Triple-Surface Ladder Quick Reference

| Surface | File Extension | Naming Convention | Best Suited For |
| :--- | :--- | :--- | :--- |
| **Surface 0 (Primitives)** | `*.primitives.d.ps` | `primitive class <Name>` | Core ABI handles & runtime types (`[RuntimeType]`) |
| **Surface 1 (Raw ABI)** | `*.raw.d.ps` | `snake_case` methods, lowercase args | 1:1 CPython runtime mirror, maximum interoperability |
| **Surface 2 (Idiomatic Bridge)** | `*.csharp.d.ps` | `PascalCase` static classes & methods | Modern C# application code, LINQ pipelines, IDE auto-completion |
| **Surface 3 (Enterprise)** | `*.enterprise.d.ps` | Interfaces, Records, Builder patterns | DDD, Clean Architecture, unit testing, dependency injection |
