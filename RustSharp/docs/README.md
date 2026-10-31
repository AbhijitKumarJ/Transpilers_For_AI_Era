# RustSharp Documentation

**Status:** Active  
**Last updated:** 2026-10-30  

RustSharp (`rsharpc`) is a statically typed, C#-style language that compiles to idiomatic, zero-cost, borrow-checked Rust code and synthesized Cargo workspaces. It combines C#'s elite IDE ergonomics, pristine project structure, virtual namespaces, and expressiveness with Rust's single-ownership discipline, thread safety, and bare-metal performance—without runtime garbage collection or hidden reference-counting overhead.

This directory is the implementation-oriented documentation set derived from the architectural design notes in [`../Ideation`](../Ideation). The ideation notes remain the historical design archive; the documents here are the maintained source of truth for scope, architecture, language specification, diagnostics, and execution progress.

---

## Document Map

| Document | Purpose | Primary Audience |
| :--- | :--- | :--- |
| [PRD.md](PRD.md) | Problem statement, vision, personas, requirements, success criteria | Product, engineering |
| [TECH-STACK.md](TECH-STACK.md) | Host compiler technology choices, dependencies, repository layout, build toolchain | Engineering |
| [ROADMAP.md](ROADMAP.md) | Phased execution plan (Phase 0–6), milestone deliverables, dependencies, exit gates | Product, engineering |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Multi-pass compiler pipeline, whole-program borrow inference, data flow, lowering contracts | Compiler engineers |
| [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md) | Grammar, type archetypes, struct flattening, closed enum dispatch, effect system (`throws`) | Language & tooling engineers |
| [CORE-API.md](CORE-API.md) | Ambient Standard Library (`RustSharp.Core.d.rsharp`), primitive mappings, LINQ-to-iterator fusion | Engineers, developers |
| [DIAGNOSTICS.md](DIAGNOSTICS.md) | Error code catalog (`RSHARP000`–`RSHARP005`), source span formatting, actionable hints | Compiler engineers, users |
| [LSP.md](LSP.md) | Language Server Protocol server architecture (`rsharpc lsp`), capabilities, editor setups | Tooling, engineers |
| [TESTING.md](TESTING.md) | Verification strategy, test matrix, fixtures (`commerce_workspace`), `cargo check` integration | Engineering, QA |
| [PROGRESS.md](PROGRESS.md) | Live progress tracker, milestone checklists, architectural decision log, next actions | Everyone |
| [blogs/PLAN.md](blogs/PLAN.md) | 12-Part deep-dive educational blog series: "Under the Hood of RustSharp" | Everyone, newcomers |

---

## Reading Order

1. **New to the Project:**
   Start with [PRD.md](PRD.md) to understand why RustSharp exists and how it solves "The Myth of Code Transpilation". Next, read [ROADMAP.md](ROADMAP.md) for milestone pacing, and browse [blogs/PLAN.md](blogs/PLAN.md) for an overview of the compiler design.

2. **Working on Compiler Internals:**
   Read [ARCHITECTURE.md](ARCHITECTURE.md) for the 6-pass compilation pipeline and ownership analysis algorithm, followed by [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), and [CORE-API.md](CORE-API.md).

3. **Writing Tests or Setting Up Tooling:**
   Consult [TESTING.md](TESTING.md) for test execution and fixture layout, [TECH-STACK.md](TECH-STACK.md) for dependency requirements, and [LSP.md](LSP.md) for editor protocol contracts.

4. **Tracking or Updating Work:**
   Consult and update [PROGRESS.md](PROGRESS.md). Whenever a task transitions state (`TODO` $\rightarrow$ `IN PROGRESS` $\rightarrow$ `DONE`) or an architectural decision is frozen, record it in `PROGRESS.md`.

---

## Status Legend

| Marker | Meaning |
| :--- | :--- |
| `DONE` | Implemented, tested, and verified locally |
| `DONE (uncommitted)` | Verified locally; git commit pending |
| `IN PROGRESS` | Actively under development |
| `BLOCKED` | Cannot proceed without an explicit design decision or external dependency |
| `TODO` | Planned for upcoming execution |
| `DEFERRED` | Intentionally scoped to a future milestone or phase |

---

## Conventions

- **Source files:** Use `.rsharp` or `.rs` (for co-located native modules) with UTF-8 encoding.
- **Ambient declaration files:** Use `.d.rsharp` for standard library and crate stubs (e.g. `RustSharp.Core.d.rsharp`).
- **Project configuration:** Project files use the `.rsproj` format (XML or TOML) and map directly to synthesized Cargo crates.
- **Compiler executable:** The RustSharp compiler binary is `rsharpc`.
- **Diagnostic codes:** Use the `RSHARPnnn` format (for example `RSHARP000` for syntax errors, `RSHARP001` for alias mutation conflicts).
- **Phases:** Numbered `Phase 0` through `Phase 6`.
- **Milestones:** Numbered `M0` through `M6` inside Phase 1.

---

## Scope of this Documentation

These documents specify the Phase 1 core compiler (`rsharpc`) in full detail, and establish the roadmap and contracts for subsequent phases (zero-cost LINQ hardening, Cargo ecosystem bindgen, procedural metaprogramming/async, and LSP tooling). Where an architectural design detail is subject to active iteration, it is explicitly tagged with an open decision note rather than assumed closed.

