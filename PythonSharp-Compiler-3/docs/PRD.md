# PythonSharp Product Requirements Document

| Field | Value |
| --- | --- |
| Product | PythonSharp |
| Compiler | `psc` |
| Version | 2.1.0-dev (Phases 1–5, Triple-Surface Architecture & Dogfooding Milestone complete) |
| Status | Phases 1–5, Triple-Surface Architecture (Milestones U1–U5), and 18 Ported Libraries across 8 Tiers complete and verified locally on CPython 3.11–3.13; 142 tests pass with >95% line coverage; CI marked OUT OF SCOPE (D-015) |
| Last updated | 2026-10-31 |
| Owner | PythonSharp project |
| Related docs | [TECH-STACK.md](TECH-STACK.md), [ROADMAP.md](ROADMAP.md), [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [PROGRESS.md](PROGRESS.md), [LSP.md](LSP.md) |

## 1. Summary

PythonSharp is a transpiled language with C#-style structure, static checking, and
ergonomics that emits idiomatic Python 3.11+ as its runtime representation. It
targets teams that want the scalability and reviewability of a statically typed,
namespace-oriented language without leaving the Python runtime, packaging, and
library ecosystem.

The defining constraint is **runtime Python isomorphism**: every construct in
PythonSharp must lower to ordinary Python that a Python developer could have
written by hand. PythonSharp is not a new VM, not a .NET runtime clone, and not a
framework that owns application execution.

## 2. Problem statement

Python is dominant for data, automation, AI, and backend services, but large
Python codebases face persistent structural problems:

- **Optional typing is not enforcement.** Type hints in Python are gradually
  typed, runtime-erased, and frequently incomplete. Errors surface late.
- **Implicit structure.** Dynamic dispatch, monkey-patching, import-time side
  effects, and convention-heavy packages make large systems hard to reason about.
- **Review cost.** Reviewers must hold runtime behavior in their heads because the
  source does not declare contracts, visibility, or ownership.
- **AI-generated code amplifies the problem.** LLM output is fluent Python but
  often drifts in architecture, naming, error handling, and type usage. Teams need
  machine-checkable structure around generated code.
- **Existing transpilers impose a "host metaphor tax."** Languages that map a
  foreign runtime model onto Python produce wrappers, shims, and non-idiomatic
  output that break debugging, profiling, and interoperability.

The market gap is a language that gives **C#-grade compile-time discipline** while
preserving **Python-grade runtime simplicity and ecosystem access**.

## 3. Vision

> **TypeScript for enterprise Python, with C# ergonomics.**

PythonSharp code should read like a disciplined C# codebase and run like a
well-written Python package. A Python engineer should be able to open any emitted
`.py` file and understand it immediately. A C# engineer should be productive in
PythonSharp on day one.

### Product principles

1. **Compile-time C# discipline, runtime Python isomorphism.**
   The compiler rejects ambiguity; the output is plain Python.
2. **Zero-cost abstractions.** Primitive wrappers, visibility, and type metadata
   erase at compile time. No runtime reflection layer is required to execute
   ordinary code.
3. **Deterministic, debuggable output.** Compilation is reproducible, generated
   line numbers map to `.ps` sources, and tracebacks point at the original code.
4. **Ecosystem first.** Python libraries are reachable directly; no bridge runtime
   is required for simple interop.
5. **Escape hatches are explicit.** Attributes such as `[MapsTo]`,
   `[InlineTemplate]`, `[PythonDecorator]`, and `[NativeCompile]` are the only
   sanctioned ways to cross the language boundary.
6. **No hidden magic.** If Python can do it, PythonSharp can expose it; if
   PythonSharp cannot justify a feature, it does not ship it.

## 4. Goals and non-goals

### Goals

| ID | Goal |
| --- | --- |
| G1 | Compile multi-file PythonSharp projects to readable Python 3.11+ packages. |
| G2 | Enforce static structure at compile time: namespaces, types, visibility, overloads, null safety. |
| G3 | Emit line-pinned bytecode so tracebacks and debuggers show `.ps` locations. |
| G4 | Provide a Core standard library of C#-flavored types that erase to Python built-ins. |
| G5 | Support idiomatic Python interop through `extern using` and compile-time attributes. |
| G6 | Deliver a deterministic CLI, project format, and diagnostics suitable for CI. |
| G7 | Establish an extensible pass architecture for later bindgen, metaprogramming, LSP, and native compilation. |

### Non-goals (Phase 1)

- Reimplementing the .NET runtime, BCL, CLR type system, or threading model.
- Full C# language parity: runtime generics, LINQ query syntax beyond method
  chains, delegates/events, reflection, and attributes that execute at runtime are
  out of scope.
- Emitting a binary without Python; native compilation is a later phase.
- Owning package management; `psc` complements Python tooling rather than replacing it.
- Rewriting CPython or depending on a custom interpreter.
- Automatic translation of arbitrary Python source into PythonSharp.
- Guaranteeing performance improvements over hand-written Python; parity is the
  initial target.

## 5. Users and personas

| Persona | Need | What PythonSharp provides |
| --- | --- | --- |
| Enterprise platform engineer | Structure and reviewability across large Python services | Namespaces, visibility, explicit types, deterministic output |
| Data/ML engineer | Python libraries plus safer application code | Ergonomic interop, Core types, low runtime overhead |
| C# developer entering Python | Familiar syntax and semantics | C#-style declarations, LINQ, `IDisposable`, overloads |
| Tech lead / architect | Enforce architecture mechanically | Compiler diagnostics, project boundaries, generated readable code |
| AI-assisted development team | Guardrails around generated code | Compile-time checks, stable conventions, auditable output |
| Tooling author | Stable AST, positions, and project model | Multi-pass AST, symbol tables, source spans, project API |

## 6. Use cases and user stories

### Primary use cases

1. **Greenfield service code.** Build a Python service with namespaces, explicit
   contracts, and compile-time checks.
2. **Hardening existing Python.** Wrap critical domains in PythonSharp while
   calling existing Python packages through `extern using`.
3. **AI-assisted development.** Generate PythonSharp with an LLM, then rely on
   `psc` diagnostics and Python type checking to catch structural drift.
4. **Shared domain libraries.** Publish PythonSharp-built packages that ordinary
   Python applications can import with no PythonSharp runtime dependency.

### User stories

- As a platform engineer, I can compile a multi-file project so that every
  namespace becomes a Python package and every import resolves at compile time.
- As a reviewer, I can see visibility and type contracts in the source and trust
  the compiler to reject violations.
- As a Python developer, I can call a Python library from PythonSharp without
  writing wrappers for straightforward functions and classes.
- As an operator, I can read a traceback from production and land on the exact
  `.ps` line that failed.
- As a library author, I can emit a wheel whose runtime has no PythonSharp
  dependencies.
- As an AI-assisted developer, I can run one command in CI and fail the build on
  structural errors before tests run.

## 7. Scope by phase

All core phases and the dogfooding milestone are complete:

- **Phase 1: Core Compiler (DONE)**: Lexer, parser, diagnostics, multi-pass AST, symbol resolution, access checking, slots, erasure, overload dispatch, LINQ fusion, Python AST lowering, source-position stamping, and `.py`/`.pyc` emission.
- **Phase 2: Core Library & Hardening (DONE)**: Full Core standard library types (`String`, `List`, `Dict`, `HashSet`, `Math`, `Console`, `Int32`, `Double`, `Boolean`), extended LINQ operator surface and fallback iterators, static properties, golden snapshot suite, and compiler benchmark harness.
- **Phase 3: Ecosystem Bindings (DONE)**: `psc bindgen` CLI generating ambient `.d.ps` stubs from `.pyi` and typeshed definitions with `--root-namespace` support and bidirectional interop.
- **Phase 4: Pythonic Metaprogramming (DONE)**: `[PythonDecorator]`, `[SchemaModel]` lowering to Pydantic v2 `BaseModel`, async streams (`IAsyncEnumerable<T>`), and generators (`yield return`).
- **Phase 5: Tooling & Native Compilation (DONE)**: Pure-Python Language Server Protocol server (`psc lsp`), incremental SHA-256 build caching (`BuildCacheManager`), continuous watch mode (`psc watch`), and native AOT compilation orchestration (`NativeCompiler` with `[NativeCompile]` and `--native`).
- **Dogfooding Milestone (DONE)**: 8 canonical real-world Python packages ported to PythonSharp in `Samples/Ported/` (`01_leftpad` through `08_micro_requests`) and validated with dedicated test runners.

## 8. Functional requirements

Priority: **P0** = required for Phase 1 release; **P1** = Phase 1 if schedule allows;
**P2** = later phase.

### 8.1 Frontend and language

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-01 | Tokenize `.ps` source with accurate line and column source spans. | P0 |
| FR-02 | Parse compilation units containing `namespace`, `using`, and `extern using` directives. | P0 |
| FR-03 | Parse classes, records, structs, interfaces, enums, and primitive classes. | P0 |
| FR-04 | Parse fields, properties, methods, constructors, static members, and access modifiers. | P0 |
| FR-05 | Support nullable reference types and null-safety operators (`?`, `?.`, `??`, `!`). | P0 |
| FR-06 | Support expressions with C# precedence, string interpolation, casts, `is`/`as`, and slicing. | P0 |
| FR-07 | Support `if`, `while`, `foreach`, `switch`/pattern matching, `return`, `break`, `continue`. | P0 |
| FR-08 | Support LINQ method chains (`.Where`, `.Select`, `.OrderBy`, `.ToList`, and peers). | P0 |
| FR-09 | Support compile-time attributes: `MapsTo`, `InlineTemplate`, `RuntimeType`, `KwArgs`, `LinqStage`, `PythonDecorator`, `SchemaModel`, `NativeCompile`. | P0 parse; P1 semantics |
| FR-10 | Produce deterministic, multi-pass ASTs with source spans for every node. | P0 |

### 8.2 Semantics and analysis

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-11 | Build a global symbol table across all files in a project. | P0 |
| FR-12 | Aggregate declared namespaces into a virtual namespace tree and detect collisions. | P0 |
| FR-13 | Resolve circular cross-file type references without infinite recursion. | P0 |
| FR-14 | Enforce `public`, `private`, `protected`, and `internal` access; emit `PS001`. | P0 |
| FR-15 | Compute deduplicated `__slots__` and `__ps_types__`; detect static initializer cycles (`PS003`) and `dynamic` use under `[NativeCompile]` (`PS004`). | P0 |
| FR-16 | Resolve primitive wrappers and inline templates with zero runtime cost. | P0 |
| FR-17 | Resolve `@overload` groups and emit deterministic dispatch; emit `PS002` on collisions. | P0 |
| FR-18 | Lower `IDisposable`/`IAsyncDisposable` usage to `with`/`async with`. | P0 |
| FR-19 | Fuse LINQ chains into comprehensions where semantics are preserved, with iterator fallback otherwise. | P0 |
| FR-20 | Type-check the supported Phase 1 subset and report actionable diagnostics. | P0 |

### 8.3 Code generation and output

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-21 | Build Python 3.11+ `ast.Module` trees from lowered nodes. | P0 |
| FR-22 | Stamp generated Python nodes with `.ps` source positions. | P0 |
| FR-23 | Topologically sort namespaces and emit Python package directories. | P0 |
| FR-24 | Emit readable `.py` files with stable formatting. | P0 |
| FR-25 | Emit PEP 552 line-pinned `.pyc` artifacts for direct execution. | P0 |
| FR-26 | Preserve `.ps` line numbers in runtime tracebacks. | P0 |
| FR-27 | Provide a CLI that compiles a project and reports diagnostics with correct exit codes. | P0 |
| FR-28 | Support reproducible builds: identical input and options produce identical `.py` and manifest artifacts. | P0 |

### 8.4 Interop and standard library

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-29 | Import Python modules directly via `extern using`, including aliasing. | P0 (DONE) |
| FR-30 | Provide Core types: String, List, Dict, HashSet, Math, Console, Int32, Double, Boolean, IDisposable, and LINQ surface. | P0 (DONE) |
| FR-31 | Expose extension points for bindgen and native compilation without changing user syntax. | P1 (DONE) |
| FR-32 | Support `[PythonDecorator]` and `[SchemaModel]` lowering. | P2 (DONE) |
| FR-33 | Support `async`/`await`, async streams, and generators. | P2 (DONE) |

## 9. Non-functional requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-01 | Supported host platforms | Linux, macOS, Windows |
| NFR-02 | Generated Python compatibility | CPython 3.11+ |
| NFR-03 | Compiler runtime dependency | Python standard library only |
| NFR-04 | Generated runtime dependency | None for ordinary code |
| NFR-05 | Determinism | Byte-identical `.py` and manifest output for identical inputs and options; `.pyc` headers follow PEP 552 timestamp rules |
| NFR-06 | Source mapping | Exact `.ps` line for every emitted statement |
| NFR-07 | Diagnostic quality | Stable codes, source span, actionable message |
| NFR-08 | Performance | M6 baseline: 7.55s for 26,002 LOC; target under 10s for 25k LOC on a laptop |
| NFR-09 | Test coverage | 90% line coverage on compiler packages; 100% of documented diagnostics |
| NFR-10 | Security | Compiler parses untrusted input without executing project code |
| NFR-11 | Reproducibility | No timestamps or absolute paths in artifacts, except PEP 552 metadata |
| NFR-12 | Extensibility | New lowering rules register through the pass pipeline, not parser edits |
| NFR-13 | Observability | Diagnostic output and artifact summaries are available; detailed `--verbose` pass timings are deferred |

## 10. Success metrics

### Phase 1 release metrics

| Metric | Target |
| --- | --- |
| Reference commerce sample | Compiles and runs end to end |
| Milestone gates | M0-M6 accepted locally on CPython 3.11-3.13 (D-015) |
| Diagnostic coverage | PS001-PS004 implemented and tested |
| Traceback fidelity | 100% of traceback fixtures report `.ps` lines |
| Generated type cleanliness | Pyright strict reports zero errors on emitted samples |
| Unit/integration suite | Green locally on Python 3.11, 3.12, and 3.13; cross-platform CI deferred |
| Runtime dependency check | Emitted packages import with no `psc` installed |
| Build determinism | Two clean builds produce identical `.py` artifacts |

### Post-release indicators

- Time to first successful compile for a new user under 10 minutes.
- Percentage of diagnostics with a suggested fix.
- Compile-time overhead relative to hand-written Python build time.
- Adoption through compiled packages that do not require PythonSharp at runtime.

## 11. Assumptions and constraints

- CPython is the primary runtime; PyPy support is not promised in Phase 1.
- The compiler may require a newer Python than the generated code target, but the
  Phase 1 floor is aligned at 3.11 for both.
- Python's `ast` module is stable enough for the supported subset; version-specific
  differences are handled in the emitter.
- Users accept that PythonSharp runs on the Python object model, including garbage
  collection, duck typing at library boundaries, and the GIL.
- Performance parity, not acceleration, is the Phase 1 promise.
- The Ideation drafts are design input, not verified implementation.

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Semantic mismatch between C# and Python (value types, GC, overloading) | High | Restrict features to those with faithful lowerings; document divergences; diagnostics over silent approximation |
| Generated Python becomes unreadable | High | Golden readability tests; idiomatic lowering rules; no wrapper types for primitives |
| Line mapping breaks across Python versions | High | Version-specific emitter tests; traceback fixtures on the CI matrix |
| `.pyc` portability issues | Medium | Treat bytecode as an optimization artifact; source emission is always available |
| Scope creep toward full C# | High | Enforce non-goals and phase gates; reject features lacking a Python-isomorphic lowering |
| Python-hosted compiler performance | Medium | Profile in M6; design passes for streaming and caching; keep a Rust rewrite option open |
| Static type checker gaps | Medium | Type-check generated output with Pyright in CI; narrow Phase 1 subset |
| Interop edge cases (`*args`, unions, descriptors) | Medium | Defer to bindgen phase; explicit diagnostics for unsupported shapes |
| LLM-generated misuse | Low | Clear examples, diagnostics, and deterministic formatting |
| Security of parsing untrusted code | Medium | Never execute project code during compilation; sandbox any future plugin execution |

## 13. Release criteria (Phase 1)

Phase 1 is releasable when all of the following are true:

1. M0-M6 milestone gates in [ROADMAP.md](ROADMAP.md) pass.
2. The commerce sample compiles, emits source and bytecode, and runs with correct
   tracebacks.
3. PS001, PS002, PS003, and PS004 have positive and negative tests.
4. All generated Python parses and passes Pyright strict on the sample corpus.
5. The wheel installs in a clean environment; `psc --version` and `psc build` work
   without third-party runtime dependencies.
6. Two clean builds produce identical `.py` artifacts.
7. Documentation in this folder matches behavior; PROGRESS is current.
8. No open P0 defects.

## 14. Open questions

| ID | Question | Owner | Needed by | Status |
| --- | --- | --- | --- | --- |
| OQ-01 | How should `struct` value-copy semantics be represented, or explicitly marked unsupported? | Language | M3 | RESOLVED: reference semantics, D-009 |
| OQ-02 | Is `switch` pattern matching in Phase 1 limited to type/value patterns? | Language | M1 | RESOLVED: faithful Python patterns only, D-010 |
| OQ-03 | Which exception model: C#-style `try/catch/finally` mapping to Python, or Python-only? | Language | M1 | RESOLVED: direct Python exception model, D-016 |
| OQ-04 | How are properties represented: `@property` pairs or public fields plus accessors? | Language | M3 | RESOLVED: properties over backing slots, D-011; static properties use class attributes/classmethods, D-019 |
| OQ-05 | What is the minimum supported CPython patch version for `.pyc` artifacts? | Runtime | M6 | RESOLVED: host CPython 3.11+ bytecode, D-013 |
| OQ-06 | Which generic constraints are enforced in Phase 1 beyond parse-and-erase? | Language | M2 | RESOLVED: static bounds, D-012 |
| OQ-07 | What is the caching and incremental-build strategy before Phase 5? | Compiler | Phase 5 | RESOLVED: SHA-256 incremental build caching via `BuildCacheManager` with `--force` override, D-021 |
| OQ-08 | How are operator overloads spelled and lowered? | Language | Phase 2 | RESOLVED: deferred to Phase 4; no operator overloading in the Phase 2 stable subset (D-020) |

## 15. References

- [TECH-STACK.md](TECH-STACK.md) — implementation technology decisions.
- [ROADMAP.md](ROADMAP.md) — phase and milestone definitions.
- [ARCHITECTURE.md](ARCHITECTURE.md) — compiler pipeline design.
- [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md) — syntax and lowering rules.
- [DIAGNOSTICS.md](DIAGNOSTICS.md) — diagnostic catalog.
- [TESTING.md](TESTING.md) — verification strategy.
- [PROGRESS.md](PROGRESS.md) — current status.
- [`../Ideation/PythonSharp Syntax And Phase Planning.md`](../Ideation/PythonSharp%20Syntax%20And%20Phase%20Planning.md) — original syntax and phase notes.
- [`../Ideation/The Myth of Code Transpilation.md`](../Ideation/The%20Myth%20of%20Code%20Transpilation.md) — feasibility rationale.
