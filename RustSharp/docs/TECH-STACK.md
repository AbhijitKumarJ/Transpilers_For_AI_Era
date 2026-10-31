# RustSharp Technology Stack

| Field | Value |
| :--- | :--- |
| **Compiler Host** | Rust 1.85+ (Edition 2021 / 2024) |
| **Transpilation Target** | Idiomatic Rust 2021 / 2024 Source + Synthesized Cargo Workspaces |
| **Status** | Active |
| **Owner** | RustSharp Core Team |
| **Related Documents** | [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [TESTING.md](TESTING.md) |

---

## 1. Architectural Summary & Principles

The RustSharp compiler (`rsharpc`) is implemented in **native Rust**. Writing the compiler in Rust offers immediate advantages:
1. **Dogfooding & Mental Model Alignment:** The compiler engineers work in the exact target language that `rsharpc` emits, making it intuitive to determine what constitutes idiomatic, zero-cost Rust code.
2. **Deterministic High Throughput:** Native binary execution, zero-overhead memory management, and fast compilation ensure `rsharpc` meets its latency budget (<250ms for 10k LOC).
3. **Robust Toolchain & Cross-Compilation:** Rust's standard tooling (`cargo`, `rustup`, `clippy`, `rustfmt`) enables straightforward cross-compilation across Linux, macOS, and Windows.

---

## 2. Compiler Host Environment

| Component | Choice | Justification |
| :--- | :--- | :--- |
| **Language** | Rust 1.85+ (Edition 2021/2024) | High performance, memory safety, strong pattern matching for AST passes. |
| **Build System** | Cargo | Native dependency management, automated test runner, and workspace support. |
| **Target Runtime** | Native binaries (no VM) | Emits standard Cargo crates compiled by native `rustc`. |

---

## 3. Frontend Architecture

### 3.1 Hand-Written UTF-8 Lexer
- **Implementation:** `src/frontend/lexer.rs`
- **Design:** Hand-written, linear scan scanner with single-character peek.
- **Features:**
  - Full UTF-8 support.
  - C#-style interpolated strings (`$"Order {id}: {total}"`).
  - Suffix literals: `10.0m` (RustDecimal), `100L` (`i64`), `10u` (`u32`), `3.14f` (`f32`).
  - Slicing and range operators (`..`), null-coalescing (`??`), and safe navigation (`?.`).
  - Line comment (`//`) and block comment (`/* ... */`) tracking.
- **Dependencies:** None (Standard library `std::str::Chars`).

### 3.2 Recursive-Descent Declaration Parser & Pratt Expression Parser
- **Implementation:** `src/frontend/parser.rs`
- **Design:** Recursive-descent for top-level declarations, classes, and statements; Pratt (top-down operator precedence) parser for complex expressions.
- **Operator Precedence Table:**
  - Level 1: Null-Coalescing (`??`)
  - Level 2: Conditional OR (`||`)
  - Level 3: Conditional AND (`&&`)
  - Level 4: Bitwise OR (`|`)
  - Level 5: Bitwise XOR (`^`)
  - Level 6: Bitwise AND (`&`)
  - Level 7: Equality (`==`, `!=`)
  - Level 8: Relational (`<`, `<=`, `>`, `>=`)
  - Level 9: Shift (`<<`, `>>`)
  - Level 10: Additive (`+`, `-`)
  - Level 11: Multiplicative (`*`, `/`, `%`)
  - Level 12: Range (`..`)
  - Level 13: Unary Prefix (`!`, `-`, `~`, `++`, `--`)
  - Level 14: Postfix Member Access (`.`), Safe Navigation (`?.`), Invocation (`()`), Indexing (`[]`)

### 3.3 Multi-Pass AST with Semantic Slots
- **Implementation:** `src/frontend/ast.rs`
- **Design:** Avoids allocating distinct tree types per compiler pass. AST nodes contain interior `Option<T>` semantic decoration slots that are populated during Pass 2 (Type Checking) and Pass 3 (Borrow Inference):
  - `inferred_type: Option<TypeRef>`
  - `inferred_borrow: Option<BorrowKind>` (`Ref`, `MutRef`, `Move`)
  - `caller_coercion: Option<CallerArgCoercion>` (`Direct`, `Ref`, `MutRef`, `Deref`)

---

## 4. Semantic Engine Architecture

### 4.1 Project Configuration & Discovery
- **Implementation:** `src/project.rs`
- **Design:** Discovers `.rsproj` configurations, gathering:
  - User `.rsharp` files across arbitrary subfolders.
  - Ambient `.d.rsharp` stubs (including `stdlib/RustSharp.Core.d.rsharp`).
  - Co-located `.rs` native modules (`extern partial` implementations).
  - External Cargo crate dependencies (e.g., `rust_decimal`, `tokio`, `serde`).

### 4.2 Virtual Namespace Aggregation & Symbol Collection
- **Implementation:** `src/semantics/collector.rs`, `src/semantics/symbols.rs`
- **Design:** Decouples physical file paths from logical module trees. A multi-rooted `GlobalSymbolTable` indexes all declared namespaces, types, methods, fields, and constructors, resolving circular references between types across different files in Pass 1.

### 4.3 Type Checking & Overload Resolution
- **Implementation:** `src/semantics/type_checker.rs`
- **Design:** Statically checks type assignments, method invocations, access visibility (`public`, `internal`, `private`, `protected`), and monomorphizes method/constructor overloads at compile time with zero runtime cost.

### 4.4 Interprocedural Ownership & Borrow Inferrer
- **Implementation:** `src/semantics/borrow_inferrer.rs`
- **Design:** Traverses call graphs to perform escape analysis and field mutation tracking:
  - Detects if `this`/`self` requires `&self`, `&mut self`, or `self`.
  - Infers parameter borrowing: `&T` (read-only), `&mut T` (mutated in-place), or owned `T` (moved/consumed).
  - Determines caller-site coercions (injecting `let mut` and passing `&mut`).

### 4.5 Preflight Verifier & Diagnostics Engine
- **Implementation:** `src/diagnostics.rs`, `src/semantics/preflight_verifier.rs`
- **Design:** Checks ownership constraints before code emission. If violations are detected (e.g., aliased simultaneous mutations or escaping stack references), it halts emission and outputs structured, human-readable diagnostics (`RSHARP000`–`RSHARP005`) with two-line ASCII caret context.

---

## 5. Backend & Code Generation

### 5.1 Idiomatic Rust AST & Source Emitter
- **Implementation:** `src/codegen/rs_ast_emitter.rs`
- **Design:** Formats lowered Rust syntax with idiomatic layout:
  - `record` / `struct` $\rightarrow$ `#[derive(Clone, Debug, PartialEq)] pub struct`
  - `service class` $\rightarrow$ struct holding `Arc<T>` fields with `pub fn new(...) -> Self`
  - `shared class` $\rightarrow$ fields wrapped in `Arc<RwLock<T>>`
  - State inheritance $\rightarrow$ struct flattening + `impl Deref<Target = Base>` / `impl DerefMut`
  - Closed-world polymorphism $\rightarrow$ Rust `enum` with exhaustive `match` dispatch
  - Checked effects (`throws`) $\rightarrow$ `Result<T, E>` and `?`
  - LINQ chains $\rightarrow$ fused Rust `.iter().filter().map().collect()`

### 5.2 Cargo Workspace Synthesizer
- **Implementation:** `src/codegen/cargo_synthesizer.rs`
- **Design:** Emits a standalone, turn-key Cargo workspace:
  - Generates `Cargo.toml` with synthesized crate dependencies.
  - Emits `src/lib.rs` / `src/main.rs` wiring up modular namespace files.
  - Copies and links co-located `.rs` native files.

### 5.3 Bidirectional SourceMap Engine
- **Implementation:** `src/codegen/sourcemap.rs`
- **Design:** Maintains line/column interval mapping between the emitted `.rs` source code and the original `.rsharp` source spans for debugger and compiler traceback navigation.

---

## 6. Host Dependencies (`Cargo.toml`)

The compiler prototype prioritizes zero-bloat, rock-solid crates:

```toml
[package]
name = "rsharpc"
version = "0.1.0"
edition = "2021"
description = "RustSharp (.rsharp) Multi-Pass Compiler — C# Ergonomics to Zero-Cost Rust"

[dependencies]
# CLI Argument Parsing
clap = { version = "4.5", features = ["derive"] }

# Serialization & Deserialization (SourceMaps, Project Configs, LSP JSON-RPC)
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

# File System & Path Traversal
walkdir = "2.5"

# Terminal Formatting & Diagnostics
anstream = "0.6"
anstyle = "1.0"

[dev-dependencies]
tempfile = "3.10"
pretty_assertions = "1.4"
```

---

## 7. Repository Layout

```text
RustSharp/
├── Cargo.toml                  # Compiler package manifest
├── README.md                   # Project landing page & quick start
├── Ideation/                   # Historical design notes & milestone archives
├── docs/                       # Maintained implementation documentation
│   ├── README.md               # Docs navigation & reading order
│   ├── PRD.md                  # Product requirements document
│   ├── TECH-STACK.md           # Technology choices & architecture (this file)
│   ├── ROADMAP.md              # Phased execution plan (Phase 0–6)
│   ├── ARCHITECTURE.md         # 6-Pass compiler architecture & data flow
│   ├── LANGUAGE-SPEC.md        # Formal language specification
│   ├── CORE-API.md             # Ambient standard library reference
│   ├── DIAGNOSTICS.md          # Diagnostic codes & error handling
│   ├── TESTING.md              # Verification strategy & test matrix
│   ├── PROGRESS.md             # Live status tracker & decision log
│   ├── LSP.md                  # Language server protocol specification
│   └── blogs/
│       └── PLAN.md             # 12-part technical blog curriculum
├── stdlib/                     # Standard library ambient stubs
│   └── RustSharp.Core.d.rsharp # Intrinsic attributes & core primitives
├── src/                        # Compiler host implementation
│   ├── lib.rs                  # Library entry point & pipeline orchestration
│   ├── main.rs                 # CLI binary entry point (`rsharpc`)
│   ├── diagnostics.rs          # SourceSpan & DiagnosticEngine
│   ├── project.rs              # .rsproj loader & config
│   ├── frontend/               # Milestone 1: Lexer, tokens, AST, Pratt parser
│   │   ├── mod.rs
│   │   ├── tokens.rs
│   │   ├── lexer.rs
│   │   ├── ast.rs
│   │   └── parser.rs
│   ├── semantics/              # Milestones 2–5: Symbols, type checking, ownership
│   │   ├── mod.rs
│   │   ├── symbols.rs
│   │   ├── collector.rs
│   │   ├── type_checker.rs
│   │   ├── borrow_inferrer.rs
│   │   └── preflight_verifier.rs
│   └── codegen/                # Milestone 6: Emitter, SourceMap, Cargo synthesis
│       ├── mod.rs
│       ├── sourcemap.rs
│       ├── rs_ast_emitter.rs
│       └── cargo_synthesizer.rs
└── tests/                      # Multi-pass verification suites
    ├── m1_parser_tests.rs
    ├── m2_collector_tests.rs
    ├── m3_type_checker_tests.rs
    ├── m4_borrow_inferrer_tests.rs
    ├── m5_preflight_verifier_tests.rs
    ├── m6_e2e_tests.rs
    └── fixtures/
        └── commerce_workspace/ # Multi-file E2E test project
```

---

## 8. Development & Quality Gate Commands

```bash
# 1. Code Formatting
cargo fmt --check

# 2. Static Analysis & Linting
cargo clippy --all-targets -- -D warnings

# 3. Complete Test Execution
cargo test

# 4. Compiler Self-Execution
cargo run -- check tests/fixtures/commerce_workspace/commerce.rsproj
cargo run -- build tests/fixtures/commerce_workspace/commerce.rsproj -o dist/commerce
```

