# PythonSharp Language Server (`psc lsp`)

PythonSharp includes a pure-Python, zero-dependency Language Server Protocol (LSP) server implementing JSON-RPC 2.0 over standard input and output (`stdio`).

The server provides real-time compiler diagnostics, type hover cards, go-to-definition navigation, and keyword/symbol autocompletion across any LSP-compliant editor.

---

## 1. Starting the Server

The server is integrated directly into the `psc` CLI:

```bash
psc lsp
```

No external NodeJS or Python wrapper is required. The server reads `Content-Length:` framed JSON-RPC 2.0 packets on `stdin` and writes responses and notifications to `stdout`.

---

## 2. Supported Capabilities

| Capability | LSP Method | Description |
| :--- | :--- | :--- |
| **Document Sync** | `textDocument/didOpen`, `didChange`, `didClose` | Full-document synchronization and live parsing across `.ps`, `.pysharp`, and `.pys` files |
| **Diagnostics** | `textDocument/publishDiagnostics` | Real-time compiler diagnostics (`PS000`–`PS004`) with exact source spans and actionable fix hints |
| **Hover Cards** | `textDocument/hover` | Type signatures, class/interface/record declarations, docstrings, and Core type documentation |
| **Go To Definition** | `textDocument/definition` | Navigates to symbols within the current document, cross-file declarations across the workspace/project, and ambient standard library stubs (`PythonSharp.Core.d.ps`) |
| **Completion** | `textDocument/completion` | Autocompletes C# keywords, project symbols, and Core standard library types (`String`, `List`, `Dict`, `Task`, `IEnumerable`, `Console`, `Math`, `Int32`, etc.) |

---

## 3. Editor Configurations

### Visual Studio Code
A ready-to-use extension definition is located in `editors/vscode/`. It contributes syntax highlighting, language configuration, file associations for `*.ps`, `*.pysharp`, `*.pys`, `*.d.ps`, `*.d.pysharp`, `*.d.pys`, and automated LSP server launching.

To configure manually via the generic `vscode-languageclient` or standard runner:
```json
{
  "pythonsharp.serverPath": "psc",
  "pythonsharp.serverArgs": ["lsp"]
}
```

### Neovim (Built-in LSP)
Add the following to your `init.lua` or `after/ftplugin/pythonsharp.lua`:

```lua
vim.filetype.add({
  extension = {
    ps = "pythonsharp",
    pysharp = "pythonsharp",
    pys = "pythonsharp",
  },
})

local client = vim.lsp.start({
  name = "pythonsharp-lsp",
  cmd = { "psc", "lsp" },
  root_dir = vim.fs.dirname(vim.fs.find({ "*.psproj", "*.pysharpproj", ".git" }, { upward = true })[1]),
})
```

### Helix (`languages.toml`)
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

### Sublime Text (LSP package)
In `LSP.sublime-settings`:

```json
{
  "clients": {
    "pythonsharp": {
      "enabled": true,
      "command": ["psc", "lsp"],
      "selector": "source.ps, source.pysharp, source.pys"
    }
  }
}
```

