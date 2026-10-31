# RustSharp Product Requirements Document (PRD)

| Field | Value |
| :--- | :--- |
| **Product** | RustSharp |
| **Compiler Binary** | `rsharpc` |
| **Current Target** | Phase 0 (Ideation & Docs Preparation Complete; Phase 1 Bootstrap Starting) |
| **Host Toolchain** | Rust 1.85+ (Edition 2021/2024), Cargo |
| **Output Target** | Idiomatic Rust 2021/2024 Source + Synthesized Cargo Workspaces |
| **Owner** | RustSharp Core Team |
| **Related Documents** | [TECH-STACK.md](TECH-STACK.md), [ROADMAP.md](ROADMAP.md), [ARCHITECTURE.md](ARCHITECTURE.md), [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [PROGRESS.md](PROGRESS.md) |

---

## 1. Executive Summary

RustSharp is a statically typed, C#-style language and multi-pass compiler (`rsharpc`) that lowers directly into idiomatic, zero-cost, borrow-checked Rust code and synthesized Cargo projects. It bridges the chasm between C#'s unmatched developer ergonomics, structured namespaces, and file decoupling, and Rust's bare-metal speed, memory safety, and fearless concurrency.

The defining architectural thesis of RustSharp is **Compile-Time C# Discipline, Runtime Zero-Cost Rust Isomorphism**. Every `.rsharp` language feature either erases completely at compile time or maps 1:1 to optimal stack-allocated Rust structs, enums, or zero-cost iterators. Unlike naive transpilers that introduce runtime garbage collectors, `Arc<Mutex<T>>` wrappers, or heavy vtable shims, RustSharp solves the semantic ownership chasm through **Interprocedural Escape and Mutation Analysis**, classifying types into explicit architectural archetypes and inferring exact Rust borrows (`&T`, `&mut T`, or owned `T`) ahead of time.

---

## 2. Problem Statement: Solving "The Myth of Code Transpilation"

Transpiling an object-oriented, managed language like C# or Java into Rust historically fails not because of surface syntax, but because of **irreconcilable semantic mismatches** in memory models, type hierarchies, and error propagation:

### 2.1 The Semantic Chasm

1. **Garbage Collection vs. Single Ownership:**
   - *In C#:* Objects are allocated on the managed heap with arbitrary multi-ownership, cycles, and indeterminate lifetimes managed by a tracing GC.
   - *In Rust:* Every value has a single owner. Aliasing and mutability are mutually exclusive ($\text{Aliasing} \oplus \text{Mutability}$). Lifetimes are verified statically.
   - *The Failure Mode:* Naive transpilation forces every C# reference into `Rc<RefCell<T>>` or `Arc<RwLock<T>>`, destroying performance, introducing runtime borrow panics (`BorrowMutError`), and leaking cyclic graphs.

2. **Nominal Inheritance vs. Traits and Tagged Unions:**
   - *In C#:* Polymorphism relies on open nominal class inheritance, mutable protected state, and virtual method tables.
   - *In Rust:* There is no class inheritance. Data is modeled via structs and algebraic data types (`enum`), with behavior decoupled into `trait` definitions.
   - *The Failure Mode:* Emulating class hierarchies with void pointers or nested vtables produces unidiomatic, unmaintainable Rust that cannot interoperate with native crates.

3. **Implicit Exception Unwinding vs. Monadic Error Propagation:**
   - *In C#:* Any method may throw arbitrary exceptions that unwind the runtime call stack.
   - *In Rust:* Errors are explicit values returned via `Result<T, E>` and propagated using the `?` operator. Stack unwinding (`panic!`) is reserved for unrecoverable bugs.

4. **Namespace and Physical File Coupling:**
   - *In Rust:* Code organization is tightly coupled to physical folder paths and explicit `mod` declarations in `lib.rs` / `main.rs`. Circular references across files require explicit module re-exports.
   - *In C#:* Physical folders are decoupled from logical `namespace` trees. Files can be organized by feature, and symbols resolve globally across files.

### 2.2 The Market Opportunity

Modern software engineering—especially in the era of AI-generated code—faces an acute tension:
- **C# / .NET:** Offers supreme clarity, structured encapsulation, clear access modifiers (`public`, `internal`, `private`), and enterprise reviewability, but brings a 40MB+ runtime VM, GC latency spikes, and suboptimal integration into embedded, systems, or serverless domains.
- **Rust:** Offers world-class performance, deterministic memory safety, and rich systems crates, but enforces cognitive overhead through lifetime annotations (`'a`), complex borrow fights, and fragmented file-module hierarchies.

RustSharp eliminates this trade-off: developers and AI agents write clear, high-level, modular C# syntax, and `rsharpc` emits clean, standard, borrow-checked Rust crates that compile with zero warnings under native `cargo`.

---

## 3. Vision & Core Principles

> **"C# developer ergonomics and clarity, compiled to zero-cost, bare-metal Rust."**

### Guiding Principles

1. **Zero-Cost Abstractions by Default:**
   No hidden garbage collection, no ambient tracing runtime, and no unrequested `Arc<Mutex<T>>` wrapping. High-level abstractions compile down to optimal Rust primitives.
2. **Three Architectural Archetypes:**
   Rather than attempting to solve undecidable general aliasing, RustSharp explicitly classifies types into:
   - `record` / `struct`: Value types & linear DTOs $\rightarrow$ Plain Rust `struct` with automatic borrow inference (`&T`, `&mut T`).
   - `service class`: Dependency-injected actors & orchestrators $\rightarrow$ Immutable/readonly fields, passed via `Arc<T>` or `&T`.
   - `shared class`: Multi-owner mutable state (caches, graph nodes) $\rightarrow$ Explicit `Arc<RwLock<T>>` or arena handle (`slotmap`).
3. **Whole-Program Borrow & Mutation Inference:**
   The compiler inspects call graphs to automatically infer whether a parameter must be `&T`, `&mut T`, or owned `T`, and injects caller-site `let mut` declarations and `&mut` references without manual developer annotation.
4. **Checked Effect Propagation:**
   Exceptions are converted into static algebraic effects: `throws SomeError` lowers directly to `Result<T, SomeError>` and `?`.
5. **Decoupled Virtual Namespaces:**
   Physical directory structures do not dictate Rust `mod` trees. `namespace Foo.Bar;` aggregates across files automatically into synthesized `src/foo/bar.rs` modules and `Cargo.toml`.
6. **Seamless Native Rust Co-Existence:**
   Pure `.rsharp` code effortlessly imports external Cargo crates via `extern using tokio::time;` and integrates raw `.rs` implementation files via `extern partial`.

---

## 4. Goals and Non-Goals

### Goals

| ID | Goal Statement |
| :--- | :--- |
| **G1** | Deliver a standalone CLI compiler (`rsharpc`) written in modern Rust that compiles `.rsharp` projects into valid, verifiable Rust crates. |
| **G2** | Implement a robust, resilient recursive-descent and Pratt parser producing multi-pass ASTs with exact 1-indexed source spans. |
| **G3** | Aggregate virtual namespaces across arbitrary directory layouts into unified Rust module trees and synthesized `Cargo.toml` manifests. |
| **G4** | Implement static whole-program ownership and borrow inference, inferring parameter mutability and caller call-site coercions without lifetime syntax. |
| **G5** | Lower closed-world class hierarchies into zero-cost tagged unions (`enum`) and open polymorphic interfaces into native Rust traits. |
| **G6** | Provide compile-time diagnostic verification (`RSHARP000`–`RSHARP005`) with ASCII caret source previews and actionable remediation hints. |
| **G7** | Provide bidirectional SourceMaps linking original `.rsharp` line/column positions to emitted Rust code for seamless debugging. |
| **G8** | Support ambient standard library declarations (`RustSharp.Core.d.rsharp`) with zero runtime overhead via compile-time attribute erasure. |

### Non-Goals

- **Full .NET Runtime Emulation:** RustSharp does not port the CLR, reflection APIs (`System.Reflection`), thread-pool runtimes, or the JIT engine.
- **Dynamic Unbounded Inheritance:** Arbitrary, runtime-polymorphic open class inheritance with dynamic downcasting (`is`/`as`) is replaced with sealed enum dispatch or open traits.
- **Transpiling Legacy WinForms/WPF/ASP.NET:** Legacy .NET UI and platform-bound frameworks are out of scope.
- **Automatic Translation of Arbitrary C# Binaries:** `rsharpc` processes source code written to the RustSharp specification, not compiled `.dll` assemblies.

---

## 5. Users and Personas

| Persona | Motivation | Value Provided by RustSharp |
| :--- | :--- | :--- |
| **Systems / Backend Engineer** | Needs Rust's performance and reliability but wants faster delivery and clearer domain structure | Eliminates borrow-checker fights; provides structured namespace and DTO semantics. |
| **Enterprise C# Architect** | Wants to modernize backend services or edge workloads to run without the .NET runtime memory footprint | Familiar language ergonomics, records, LINQ, and clean separation of concerns without runtime penalty. |
| **AI / Agentic Code Generator** | LLMs generate C# structure with high consistency, but struggle with Rust lifetime management and module exports | AI agents generate well-bounded `.rsharp` code; `rsharpc` mechanically produces correct Rust module trees and ownership annotations. |
| **Tooling & Infrastructure Developer** | Builds CLI utilities, plugins, or embedded software targeting low-memory environments | Zero-cost binaries with no GC pauses, fast startup times, and full access to crates.io ecosystem. |

---

## 6. Use Cases and User Stories

### Use Cases

1. **High-Throughput Microservices:**
   Building a Commerce or Payment API using high-level DTOs, dependency-injected services, and LINQ pipelines that compiles into an ultra-low-latency, zero-cost native binary.
2. **Edge & Embedded Data Processing:**
   Running business logic on memory-constrained devices where the .NET CLR cannot fit, but C# domain clarity is desired.
3. **Safe Interop with Existing Rust Crates:**
   Writing domain logic in `.rsharp` while pulling in high-performance native crates like `tokio`, `serde`, `axum`, or `rust_decimal` via `extern using`.
4. **Multi-File Domain Modeling:**
   Partitioning complex domain models across 50+ files without worrying about Rust's physical file module trees or circular reference compilation errors.

### User Stories

- *As an engineer,* I can declare `namespace Store.Orders;` across ten different folders, and `rsharpc` synthesizes a clean Rust module hierarchy and `Cargo.toml` without manual `mod` wiring.
- *As a developer,* I can pass a `record Order` to a service method that updates its total, and `rsharpc` automatically infers `&mut Order` and adds `let mut` at the call-site.
- *As a code reviewer,* I can see explicit `throws PaymentFailedError` signatures in `.rsharp` and trust that the emitted Rust code handles errors via idiomatic `Result<T, PaymentFailedError>` and `?`.
- *As a systems programmer,* I can declare an `extern partial` class and implement raw, performance-critical assembly or unsafe Rust code in a co-located `.rs` file.

---

## 7. Scope by Phase

```mermaid
flowchart LR
    P0["Phase 0: Ideation & Docs"] --> P1["Phase 1: Bootstrap Compiler (M0-M6)"]
    P1 --> P2["Phase 2: Core Lib & Zero-Cost LINQ"]
    P2 --> P3["Phase 3: Cargo Bindgen Bridge"]
    P3 --> P4["Phase 4: Metaprogramming & Async"]
    P4 --> P5["Phase 5: Tooling & LSP"]
    P5 --> P6["Phase 6: Real-World Dogfooding"]
```

- **Phase 0: Ideation & Architectural Documentation (CURRENT)**
  Synthesize ideation drafts into standard project documentation ([PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [TECH-STACK.md](TECH-STACK.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [CORE-API.md](CORE-API.md), [TESTING.md](TESTING.md), [ROADMAP.md](ROADMAP.md), [PROGRESS.md](PROGRESS.md), [LSP.md](LSP.md), [blogs/PLAN.md](blogs/PLAN.md), and root `README.md`).
- **Phase 1: The Bootstrap Compiler & Ownership Analyzer (M0–M6)**
  - M0: Cargo workspace setup, project skeleton, and test harnesses.
  - M1: Frontend foundation: UTF-8 lexer, Pratt parser, multi-pass AST, `SourceSpan`, diagnostics engine.
  - M2: Pass 1: `.rsproj` project loader, virtual namespace aggregation, `GlobalSymbolTable`, circular reference collection.
  - M3: Pass 2: Type checking, static monomorphized overload dispatch, encapsulation enforcement.
  - M4: Pass 3: Whole-program escape & mutation analysis, parameter borrow inference (`&T`/`&mut T`/owned), caller mutation injection.
  - M5: Pass 4: Preflight ownership verifier, enforcing `RSHARP001`–`RSHARP005` diagnostics.
  - M6: Pass 5: Rust AST & code emitter, bidirectional SourceMap, Cargo workspace synthesizer, CLI entry point, `RustSharp.Core.d.rsharp`, and E2E `commerce_workspace` verification.
- **Phase 2: Core Library & Zero-Cost LINQ Hardening**
  Complete `RustSharp.Core` ambient types, full LINQ-to-iterator fusion (`Where`, `Select`, `OrderBy`, `GroupBy`, `Take`, `Skip`), and fallback iterators.
- **Phase 3: Cargo Ecosystem Bridge (`rsharp-bindgen`)**
  Automated tool to inspect external Rust crates (via `syn`/`rustdoc` JSON) and emit typed `.d.rsharp` ambient declarations.
- **Phase 4: Metaprogramming, Attributes-to-Macros & Async Ecosystem**
  Mapping attributes like `[JsonPropertyName]` to `#[serde(rename = "...")]`, `async`/`await` lowering to Tokio futures, and async streams (`IAsyncEnumerable<T>`).
- **Phase 5: Developer Experience, Incremental Cache & LSP Server**
  Incremental compilation cache with SHA-256 fingerprinting, continuous watch mode (`rsharpc watch`), and pure-Rust Language Server Protocol server (`rsharpc lsp`) supporting live diagnostics, hover, definition, and completion.
- **Phase 6: Real-World Dogfooding & Ecosystem Libraries**
  Porting canonical real-world C# and Rust libraries to `.rsharp` to stress-test compiler throughput, binary size, and code quality.

---

## 8. Functional Requirements

| ID | Requirement Description | Phase |
| :--- | :--- | :--- |
| **F-001** | Hand-written UTF-8 lexer supporting string interpolation `$"..."`, decimal literals `10.0m`, comments, and operators. | M1 |
| **F-002** | Pratt expression parser handling precedence from null-coalescing `??` to primary postfix calls and indexing. | M1 |
| **F-003** | Declaration parser supporting `record`, `struct`, `service class`, `shared class`, `abstract class`, and `extensible interface`. | M1 |
| **F-004** | Discovery and loading of `.rsproj` project files, resolving all referenced `.rsharp`, `.d.rsharp`, and co-located `.rs` files. | M2 |
| **F-005** | Virtual Namespace Aggregator collecting declarations across decoupled physical files into unified symbol tables. | M2 |
| **F-006** | Multi-file circular type reference resolution without requiring manual forward declarations. | M2 |
| **F-007** | Static monomorphized overload resolution for methods and constructors at compile time. | M3 |
| **F-008** | Access modifier checking (`public`, `internal`, `private`, `protected`). | M3 |
| **F-009** | Interprocedural Escape and Mutation Analysis calculating field-level mutations and escape lifespans. | M4 |
| **F-010** | Automatic parameter borrow inference: assign `&self`/`&mut self`, `&T`/`&mut T`/owned `T`. | M4 |
| **F-011** | Caller-site mutation injection: automatically emit `let mut` and pass `&mut arg` at call sites. | M4 |
| **F-012** | Preflight verifier diagnostics: emit `RSHARP001` (illegal shared mutability), `RSHARP002` (escaping borrow), `RSHARP003` (uncaught effect). | M5 |
| **F-013** | Zero-cost LINQ-to-iterator fusion lowering `.Where().Select().ToList()` into `.iter().filter().map().collect()`. | M6 |
| **F-014** | Synthesizer emitting complete Cargo workspace (`Cargo.toml`, `src/lib.rs`, and modular `.rs` source files). | M6 |
| **F-015** | Bidirectional SourceMap mapping emitted Rust line/column coordinates back to original `.rsharp` source spans. | M6 |

---

## 9. Quality Attributes & Non-Functional Requirements

- **Transpiler Performance:** The compiler must parse, analyze, and emit 10,000 lines of `.rsharp` code in under 250 milliseconds on modern developer hardware.
- **Zero-Cost Generated Code:** Emitted Rust code must introduce zero unnecessary heap allocations, no unconditional `Arc<Mutex<T>>` wrappers, and compile with zero warnings under standard `cargo check`.
- **Reproducibility & Determinism:** Compiling the same `.rsharp` project twice with identical inputs must produce byte-identical Rust output files and SourceMaps.
- **Diagnostic Precision:** Diagnostic messages must print exact 1-indexed line and column numbers, display two-line ASCII caret visual context, and provide actionable remediation hints.
- **Portability:** The host compiler must compile and run on Linux (x86_64, aarch64), macOS (Apple Silicon, Intel), and Windows.

---

## 10. Success Criteria & Verification Gates

1. **Self-Contained Bootstrap (Phase 1):**
   The `commerce_workspace` multi-file fixture (comprising Domain models, Database service, Payment processor, and CLI application) transpile with zero warnings, pass `cargo check`, and pass all integration assertions in `cargo test`.
2. **Diagnostic Correctness:**
   Every test fixture in `tests/m5_preflight_verifier_tests.rs` designed to violate borrow or effect rules triggers the exact diagnostic code (`RSHARP001`, `RSHARP002`, `RSHARP003`) with proper span coordinates.
3. **End-to-End Execution:**
   The emitted Cargo crate runs natively via `cargo run`, correctly processing domain transactions and outputting formatted results identical to the specification.

