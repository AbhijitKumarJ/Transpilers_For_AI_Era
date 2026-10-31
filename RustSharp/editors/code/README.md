# RustSharp VS Code & Editor Support

First-class language support for **RustSharp (`.rsharp`)** in Visual Studio Code and compatible LSP editors (Neovim, Helix, Sublime Text).

---

## Features

- **Rich Syntax Highlighting:**
  - TextMate grammar covering archetypes (`record`, `service class`, `shared class`, `value struct`), checked effects (`throws`), attributes (`[HttpGet]`, `[JsonPropertyName]`, `[Borrow]`), string interpolation (`$"{expr}"`), verbatim strings (`@"..."`), raw strings (`"""..."""`), hexadecimal literals (`0x...`), and LINQ operators.
- **Language Server (`rsharpc lsp`):**
  - **Whole-Program Inferred Borrows in Hover:** Real-time tooltips showing whether a method receives `&self` or `&mut self`, parameters receive `&T` or `&mut T`, and the exact lowered Rust signature.
  - **Cross-File Go to Definition:** Jump directly across files, decoupled virtual namespaces, and project boundaries to symbol declarations (types, methods, fields, local variables, parameters, and enum variants).
  - **Document Symbols / Outline View:** Hierarchical outline of types, methods, fields, and enum variants in the sidebar and breadcrumb navigation.
  - **Workspace Symbol Search (`Ctrl+T` / `Cmd+T`):** Fuzzy symbol search across all `.rsharp` files in the project workspace.
  - **Real-Time Diagnostics:** ASCII carets and error codes (`RSHARP001`, `RSHARP002`, `RSHARP003`, `RSHARP004`, `RSHARP005`) published directly to the Problems panel on keystroke (`textDocument/publishDiagnostics`).
  - **IntelliSense Autocompletion:** Contextual completions for zero-cost LINQ pipeline operators (`Where`, `Select`, `OrderBy`, `Distinct`, `ToList`, etc.), primitive types, and language keywords.
  - **Zero External Dependencies:** Built with pure VS Code API and Node standard libraries—no `node_modules` or `npm install` required!

---

## Installation in VS Code

1. Build the release binary:
   ```bash
   cargo build --release
   ```
2. Symlink the extension to your VS Code extensions folder:
   ```bash
   ln -s "$(pwd)/editors/code" ~/.vscode/extensions/rustsharp-0.1.0
   ```
3. Restart or reload VS Code (`Developer: Reload Window`).

---

## Configuration in Neovim (`nvim-lspconfig`)

In your `init.lua`:

```lua
local lspconfig = require('lspconfig')
local configs = require('lspconfig.configs')

if not configs.rsharpc then
  configs.rsharpc = {
    default_config = {
      cmd = { 'rsharpc', 'lsp' },
      filetypes = { 'rustsharp' },
      root_dir = lspconfig.util.root_pattern('*.rsproj', 'Cargo.toml', '.git'),
      settings = {},
    },
  }
end

lspconfig.rsharpc.setup{}

vim.filetype.add({
  extension = {
    rsharp = 'rustsharp',
    rsproj = 'xml',
  },
})
```

---

## Configuration in Helix (`languages.toml`)

In `~/.config/helix/languages.toml`:

```toml
[[language]]
name = "rustsharp"
scope = "source.rsharp"
file-types = ["rsharp"]
comment-token = "//"
language-servers = [ "rsharpc" ]

[language-server.rsharpc]
command = "rsharpc"
args = ["lsp"]
```
