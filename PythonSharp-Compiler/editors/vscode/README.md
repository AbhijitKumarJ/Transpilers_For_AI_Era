# PythonSharp VS Code Extension

Official Visual Studio Code extension providing language intelligence and syntax highlighting for **PythonSharp** (`.ps`, `.d.ps`).

## Features

- **TextMate Syntax Highlighting**: Comprehensive grammar covering C# keywords, LINQ queries, primitive & core library types, string interpolation (`$"..."`), triple-quoted strings, attributes (`[NativeCompile]`), preprocessor directives, and operators.
- **Language Server Protocol (LSP)**: Connected directly to `psc lsp` via standard JSON-RPC 2.0 stdio:
  - **Live Diagnostics**: Immediate compiler error squigglies, hints, and error codes on typing and file save.
  - **IntelliSense & Autocompletion**: Auto-completes language keywords and PythonSharp core types (`Console`, `Math`, `List`, `Dict`, etc.).
  - **Hover Information**: Inspect types, keywords, and member signatures directly from hover tooltips.
  - **Go to Definition**: Jump straight to type declarations and member definitions.
  - **Zero External Dependencies**: Completely self-contained lightweight client running natively inside VS Code.
- **Project Commands**:
  - `PythonSharp: Restart Language Server`
  - `PythonSharp: Build Project (psc build)`
  - `PythonSharp: Check Diagnostics (psc check)`

## Installation

### Local Development / Direct Link
Link the extension directly to your local VS Code extensions directory:

```bash
mkdir -p ~/.vscode/extensions
ln -sfn /path/to/PythonSharp/editors/vscode ~/.vscode/extensions/pythonsharp-0.1.0
```

Restart or reload VS Code (`Developer: Reload Window`), and any `.ps` or `.d.ps` file will instantly have full syntax highlighting, live LSP diagnostics, hover, and autocompletion!

