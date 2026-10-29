# PythonSharp Roadmap

**Status:** Phase 0–Phase 5 complete and verified; CI marked OUT OF SCOPE (D-015)
**Last updated:** 2026-10-30
**Related docs:** [PRD.md](PRD.md), [TECH-STACK.md](TECH-STACK.md), [PROGRESS.md](PROGRESS.md), [CORE-API.md](CORE-API.md), [RELEASE-NOTES-PHASE-2.md](RELEASE-NOTES-PHASE-2.md), [LSP.md](LSP.md)

## 1. Phase overview

| Phase | Name | Outcome | Status |
| --- | --- | --- | --- |
| Phase 0 | Ideation and architecture | Design archive, PRD, stack, architecture, spec | DONE |
| Phase 1 | Core compiler (`psc`) | Multi-file `.ps` to `.py` and `.pyc` with diagnostics and tracebacks | DONE (CI out of scope) |
| Phase 2 | Core library and hardening | Complete Core types, LINQ surface, performance and compatibility | DONE |
| Phase 3 | Ecosystem bindings (`ps-bindgen`) | Python `.pyi`/typeshed to `.d.ps` bindings | DONE |
| Phase 4 | Pythonic metaprogramming | Decorators, schema models, async, generators | DONE |
| Phase 5 | Tooling and native compilation | LSP, incremental builds, wheel orchestration, native compilation | DONE |

```text
Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3
                              └────▶ Phase 4 ──▶ Phase 5
```

Phase 3 and Phase 4 may overlap after Phase 2; Phase 5 depends on stable Phase 1
through Phase 3 interfaces.

## 2. Phase 0: Ideation and architecture (DONE)

### Deliverables

- Raw design record in `Ideation/` covering syntax, planning, milestones, and
  rationale.
- Maintained documentation set in `docs/`:
  PRD, tech stack, roadmap, architecture, language spec, diagnostics, testing, and
  progress tracker.
- Reference implementation drafts for M1-M6 captured in the ideation notes.

### Exit gate

- Documentation set is internally consistent.
- Phase 1 scope, non-goals, and milestone gates are agreed.
- Repository layout and technology decisions are recorded.

## 3. Phase 1: Core compiler (DONE locally)

**Objective:** Deliver a working `psc` that compiles a multi-file project to
readable Python source and line-pinned bytecode, with actionable diagnostics and
end-to-end tests.

**Scope:** Milestones M0 through M6. The ideation drafts are design input and must
be validated, not copied blindly.

### Phase 1 summary

| Milestone | Name | Primary output | Indicative effort |
| --- | --- | --- | --- |
| M0 | Repository bootstrap | Installable package, CI, test harness | 1-2 days |
| M1 | Frontend foundation | Lexer, tokens, AST, parser, diagnostics | 3-4 days |
| M2 | Pass 1: symbols and projects | Project loader, symbol table, namespace tree | 2-3 days |
| M3 | Pass 2A: layout and access | Slots, `__ps_types__`, access checks, disposal | 3-4 days |
| M4 | Pass 2B: erasure, overloads, LINQ | Primitive resolver, dispatch, LINQ fusion | 3-4 days |
| M5 | Pass 3A: Python AST | Topological ordering, lowering, AST builder | 3-4 days |
| M6 | Pass 3B and CLI | Emitter, `.pyc`, CLI, Core declarations, tests | 3-4 days |

Effort is indicative for one experienced engineer and is not a commitment.

### M0: Repository bootstrap

**Status:** Complete locally; remote GitHub Actions and cross-platform CI are marked OUT OF SCOPE by decision
D-015.

**Tasks**

- Create `src/psc` package layout, `tests`, `stdlib`, and `pyproject.toml`.
- Configure `setuptools`, console script, Python 3.11 floor, and dev extras.
- Configure `ruff`, `mypy`, `pytest`, and coverage.
- Add GitHub Actions matrix for Python 3.11-3.13 on Linux, macOS, and Windows.
- Add license, contribution notes, and a minimal README.
- Add the commerce sample fixture skeleton.
- Extract reference drafts from the ideation notes into tracked source files.

**Gate**

- `pip install -e ".[dev]"` succeeds in a clean environment.
- `ruff`, format check, strict `mypy`, and `pytest` pass with coverage.
- The suite passes on CPython 3.11, 3.12, and 3.13 on the local Linux host.
- Pyright strict, clean wheel install, and clean sdist install pass locally.
- `psc --version` works.

### M1: Frontend foundation

**Status:** Implemented and verified locally; committed in `d14384d`.

**Tasks**

- Implement `SourceSpan`, `Diagnostic`, and `DiagnosticEngine` in
  `src/psc/diagnostics.py`.
- Implement token kinds and tokens in `src/psc/frontend/tokens.py`.
- Implement the lexer with strings, interpolation, comments, and numeric literals
  in `src/psc/frontend/lexer.py`.
- Define the multi-pass AST in `src/psc/frontend/ast_nodes.py`.
- Implement recursive-descent declarations and Pratt expression parsing in
  `src/psc/frontend/parser.py`.
- Add syntax error recovery at statement and declaration boundaries.
- Add unit tests for tokens, lexer, spans, precedence, and recovery.

**Gate**

- Fixture sources parse without crashes; expected syntax errors produce PS000-class
  diagnostics with accurate spans.
- Precedence tests cover every operator level.
- Frontend coverage is at least 90%.

### M2: Pass 1 - project and symbols

**Status:** Implemented and verified locally; committed in `d14384d`.

**Tasks**

- Implement `.psproj` loading (XML default, TOML read-only) in `src/psc/project.py`.
- Build the global symbol table and scope hierarchy in
  `src/psc/semantics/symbols.py`.
- Implement the symbol collector in `src/psc/semantics/collector.py` for
  namespaces, types, members, and imports.
- Aggregate declared namespaces into the virtual namespace tree and detect
  collisions.
- Resolve forward and circular cross-file type references.
- Validate `using` and `extern using` targets.
- Add project and symbol tests, including cycles.

**Gate**

- A multi-file sample resolves all types with no order dependency.
- Circular references terminate with a precise diagnostic when invalid.
- Duplicate symbols and namespace collisions report stable codes.

### M3: Pass 2A - layout and access

**Status:** Implemented and verified locally; committed in `d14384d`.

**Tasks**

- Implement slot planning in `src/psc/semantics/slot_analyzer.py`, including
  deduplication across the inheritance chain.
- Emit `__ps_types__` metadata for nominal checks.
- Synthesize `IDisposable` and `IAsyncDisposable` context managers.
- Enforce visibility in `src/psc/semantics/access_checker.py`, emitting `PS001`.
- Detect circular static initializers (`PS003`) and `dynamic` use in
  `[NativeCompile]` types (`PS004`).
- Add `tests/test_access_and_slots.py` with positive and negative cases.

**Gate**

- Inheritance slot layouts are deduplicated and deterministic.
- Access violations fail compilation with correct spans.
- Disposal lowers to `with` and `async with` in the AST tests.
- `__ps_types__` reflects the full nominal type chain.

### M4: Pass 2B - erasure, overloads, and LINQ

**Status:** Implemented and verified locally; committed in `d14384d`.

**Tasks**

- Implement `[MapsTo]` and `[InlineTemplate]` erasure in
  `src/psc/semantics/primitive_resolver.py`.
- Resolve `@overload` groups and emit runtime dispatch plans in
  `src/psc/semantics/overload_resolver.py`.
- Detect dispatch collisions and emit `PS002`.
- Implement LINQ chain fusion with lambda alpha-renaming in
  `src/psc/semantics/linq_fuser.py`.
- Implement the Phase 1 type checker in `src/psc/semantics/type_checker.py`.
- Add `tests/test_overloads_and_linq.py` plus type-checker tests.

**Gate**

- Primitive wrappers leave no runtime residue.
- Overload selection is deterministic for int/float/string/reference cases.
- Colliding overloads fail with `PS002`.
- Fused comprehensions preserve evaluation order and scoping.
- Type errors in the supported subset report actionable diagnostics.

### M5: Pass 3A - Python AST construction

**Status:** Implemented and verified locally; committed in `d14384d`.

**Tasks**

- Implement namespace topological sorting and package planning in
  `src/psc/codegen/topo_sorter.py`.
- Lower expressions, operators, null-safety, slicing, and interpolation in
  `src/psc/codegen/expr_lowerer.py`.
- Emit overload dispatch routers in `src/psc/codegen/overload_emitter.py`.
- Build Python `ast.Module` trees in `src/psc/codegen/py_ast_builder.py`.
- Stamp `.ps` line and column positions onto emitted nodes.
- Validate generated modules with `compile()`.
- Add `tests/test_py_ast_builder.py`.

**Gate**

- Generated ASTs compile for the full fixture corpus.
- Source spans map every emitted statement to a `.ps` line.
- Import ordering and namespace packaging are deterministic.
- Null-safety and slicing lowerings match the language spec.

### M6: Pass 3B, CLI, and release readiness

**Status:** Implemented and verified locally; committed in `d14384d`.

**Tasks**

- Implement `.py` emission and deterministic formatting in
  `src/psc/codegen/emitter.py`.
- Emit PEP 552 timestamp-invalidated `.pyc` artifacts with a deterministic
  `psc-manifest.json`.
- Implement `src/psc/cli.py` with `check`, `build`, `dump-ast`, and `run`; add
  `--version`.
- Publish `src/psc/__init__.py` with the public compiler API.
- Define `stdlib/PythonSharp.Core.d.ps` for the Phase 1 Core surface and package
  it as wheel data.
- Add `tests/test_bytecode_tracebacks.py` asserting `.ps` locations.
- Add end-to-end commerce sample compile and execution tests.
- Verify build determinism and clean-environment install; add CLI tests.
- Validate the generated commerce corpus with Pyright strict.
- Write the Phase 1 README and usage guide.

**Gate**

- `psc build tests/fixtures/commerce_sample` emits a runnable package.
- Runtime tracebacks report `.ps` file and line.
- Two clean builds produce identical `.py` and manifest artifacts.
- Generated code passes Pyright strict with zero diagnostics on the sample corpus.
- Wheel builds and installs without runtime dependencies; clean-install
  `psc check` and `psc build` work outside the repository.
- 25k LOC baseline is measured and recorded (7.55s for 26,002 LOC).
- Codegen coverage is 90.4% and total line coverage is 94.9%.
- All Phase 1 release criteria are met locally on CPython 3.11-3.13; remote GitHub
  Actions and cross-platform CI are marked OUT OF SCOPE by D-015.

## 4. Phase 2: Core library and hardening (DONE)

**Objective:** Complete the PythonSharp.Core surface and stabilize Phase 1 output
across real projects.

**Scope**

- Core types: `String`, `List<T>`, `Dict<K,V>`, `HashSet<T>`, `Math`,
  `Console`, `IDisposable`, `IAsyncDisposable`, and LINQ extension surface.
- Property lowering, struct/value-object strategy, exception mapping, generics
  erasure, and operator overloads as decided by open questions.
- Full LINQ method surface with documented fusion rules and fallbacks.
- Compatibility matrix: CPython 3.11, 3.12, and 3.13; Linux, macOS, Windows.
- Performance baseline and regression benchmarks.
- Golden output corpus and readability review.
- Error-message quality pass and suggested fixes where feasible.

### 4.1 Workstreams

| ID | Workstream | Deliverable | Dependency | Status |
| --- | --- | --- | --- | --- |
| P2.1 | Exception semantics | Resolve OQ-03; define exception mapping and lower `try`/`catch`/`when`/`finally`/`throw` faithfully | None | DONE |
| P2.2 | Core API completion | Audit and complete `PythonSharp.Core.d.ps`; add `Math`, exception surface, and missing collection/string members | P2.1 for exception types | DONE |
| P2.3 | LINQ surface | Implement and document the supported LINQ operators, including lazy fallbacks where fusion is unavailable | P2.2 | DONE |
| P2.4 | Semantic hardening | Property lowering edge cases, generic erasure checks, struct/record behavior, and OQ-08 operator overloads | P2.1-P2.3 | DONE |
| P2.5 | Compatibility and performance | CPython 3.11-3.13 regression runs, golden corpus, benchmark budget, and cross-platform verification when CI is enabled | P2.1-P2.4 | DONE |
| P2.6 | API and diagnostics polish | Core API documentation, clearer errors and suggested fixes, and Phase 2 release notes | P2.1-P2.5 | DONE |

### 4.2 OQ-03 resolution (D-016)

Use Python exceptions directly, without a wrapper runtime:

- `throw new X(...)` lowers to `raise X(...)`; bare `throw` lowers to bare
  `raise` and is valid only inside a catch handler.
- Exception names map through explicit Core `[MapsTo]` declarations.
- Multiple or guarded catch clauses lower through one ordered dispatcher so a
  failed `when` guard falls through to later catches, matching C# behavior.
- Untyped `catch` catches `BaseException`; typed catches use the mapped Python
  exception type.

The mapping and lowering are implemented in P2.1 and covered by
`tests/test_exceptions.py`.

### 4.3 P2.1 implementation slice (complete)

1. [x] Add failing tests for exception lowering and diagnostics.
2. [x] Record the OQ-03 decision and exception-name mapping table.
3. [x] Implement the lowering and Core declarations.
4. [x] Run the full local gate and update PROGRESS.

### 4.4 P2.2 Core API slice (complete)

1. [x] Inventory the Core surface and identify the Phase 2 gaps.
2. [x] Add `Math` mapped to Python's `math` module, with automatic module import.
3. [x] Add `String.Substring`/`IndexOf`/`LastIndexOf`/`ToString`/`IsNullOrEmpty`.
4. [x] Add `List` insert/remove-at/index/sort/reverse and `Dict.ContainsValue`/`Remove`.
5. [x] Require an explicit `[LinqStage]` for fusion so `Math.Max`/`Math.Min` are not
   mistaken for LINQ terminals (D-017).
6. [x] Add runtime and Pyright-strict coverage for the new surface.
7. [x] Complete `HashSet` operations and expanded exception mappings.
8. [x] Document the stable Core subset and list deferred APIs.
9. [x] Run the full local gate and update PROGRESS.

**Exit gate**

- Core API documented and covered by tests.
- No P0 semantic divergences in the supported subset.
- Benchmarks within the agreed overhead budget.
- Phase 1 output remains reproducible.

### 4.5 P2.3 LINQ surface slice (complete)

1. [x] Audit `IEnumerable<T>` against the supported LINQ operator surface.
2. [x] Add `OrderBy`/`OrderByDescending`/`ThenBy`/`ThenByDescending`, `Distinct`,
   `Take`, `Skip`, `Concat`, `Contains`, `LastOrDefault`, `Average`, `Min`, and
   `Max` with explicit `[LinqStage]` metadata where fusion applies.
3. [x] Implement and test lazy fallback behavior for chains without a fusable
   stage, preserving source order and stable ordering semantics.
4. [x] Document supported operators and run the full local gate.

`SingleOrDefault` remains deferred until a faithful single-element guard can be
emitted without adding a runtime wrapper. It is not part of the stable subset.

### 4.6 P2.4 semantic hardening slice (complete)

1. [x] Lower static auto-properties to class attributes, using `ClassVar` inside
   dataclasses so they do not become constructor fields.
2. [x] Lower static getter-only computed properties to classmethods and rewrite
   static property reads to calls; this avoids the Python 3.13
   `classmethod`/`property` incompatibility.
3. [x] Qualify bare static fields, properties, and method calls with the declaring
   type inside instance and static methods.
4. [x] Reject static custom setters, setters on frozen records, and unsupported
   record/struct instance fields and auto-properties with explicit diagnostics
   instead of emitting broken code.
5. [x] Retain PS002 and runtime-erasure coverage for generic overload collisions.
6. [x] Resolve OQ-08 by deferring operator overloads to Phase 4 (D-020).
7. [x] Run the full local gate, Pyright strict, and CPython 3.11-3.13 tests.

Records/structs remain frozen/mutable dataclasses over their primary constructor
parameters. Explicit instance fields and auto-properties are outside the stable
subset; computed getter-only properties over primary constructor state are
supported.

### 4.7 P2.5 compatibility and performance slice (complete)

1. [x] Golden output corpus at `tests/fixtures/golden/` with `--update-golden` snapshot
   rewriting and runtime execution test.
2. [x] CPython 3.11, 3.12, and 3.13 local regression runs; golden snapshots normalize
   line endings and execute the emitted module.
3. [x] Compiler benchmark harness at `benchmarks/benchmark_compiler.py`; default
   workload is 1,000 classes x 21 methods, with best-of-N compile timing and a
   cold-import measurement.
4. [x] Local benchmark budget is 30 seconds for the best run on the current 4-core
   host; the M6 reference baseline is 7.55 seconds for 26,002 LOC and the NFR
   target remains under 10 seconds on a typical laptop.
5. [x] Cross-platform remote CI verification is marked OUT OF SCOPE (D-015); local Linux verification is complete.

### 4.8 P2.6 API and diagnostics polish slice (complete)

1. [x] Document the complete Core API surface and behavior differences in [CORE-API.md](CORE-API.md).
2. [x] Add actionable fix hints to the `Diagnostic` model and `DiagnosticEngine` for `PS000` through `PS004`.
3. [x] Document the diagnostic model and hints in [DIAGNOSTICS.md](DIAGNOSTICS.md) and add test coverage.
4. [x] Compile and publish the comprehensive Phase 2 release notes in [RELEASE-NOTES-PHASE-2.md](RELEASE-NOTES-PHASE-2.md).
5. [x] Meet all Phase 2 exit gates: 103 tests passing, >95% coverage, CPython 3.11-3.13 verified, Pyright strict clean.

## 5. Phase 3: Ecosystem bindings (`ps-bindgen`) (DONE)

**Objective:** Make Python libraries first-class without hand-written stubs.

### 5.1 Workstreams

| ID | Workstream | Deliverable | Dependency | Status |
| --- | --- | --- | --- | --- |
| P3.1 | Stub AST parser & type conversion | `TypeConverter` in `src/psc/bindgen/type_converter.py` for primitives, generics, optionals, unions, callables | Phase 2 | DONE |
| P3.2 | Ambient declaration generator | `BindgenGenerator` in `src/psc/bindgen/generator.py` with `snake_case` -> `PascalCase` + `[MapsTo]`, union overload splitting, properties, indexers | P3.1 | DONE |
| P3.3 | CLI & manifest drift detection | `psc bindgen` CLI subcommand and `BindingManifest` with SHA-256 drift verification in `src/psc/bindgen/manifest.py` | P3.2 | DONE |
| P3.4 | Integration test corpus | Unit and end-to-end integration tests in `tests/test_bindgen.py` and `tests/test_bindgen_types.py` compiling against generated stubs | P3.3 | DONE |

**Scope**

- Parse `.pyi` stubs using Python's native `ast` parser.
- Translate modules, classes, functions, constants, unions, optionals, `*args`, `**kwargs`, properties, and overloads into `.d.ps`.
- Handle C# reserved keywords (`@base`, `@params`, `@in`, etc.) and default parameter values.
- Support `extern using` aliasing and namespace mapping (`Extern.<Module>`).
- Emit deterministic, inspectable bindings and a `psc-bindings-manifest.json` manifest.
- Add `psc bindgen <path> -o <out-dir>` CLI command with automatic drift detection.
- Compile and execute end-to-end integration projects calling into native Python via generated bindings.

**Exit gate**

- All Phase 3 unit and integration tests pass (112 tests total across 26 test files).
- Regeneration is deterministic and diffable.
- Generated ambient stubs compile cleanly in `psc check` and `psc build` with zero diagnostics.

## 6. Phase 4: Pythonic metaprogramming (DONE)

**Objective:** Provide controlled access to Python metaprogramming while retaining
static guarantees.

### 6.1 Workstreams

| ID | Workstream | Deliverable | Dependency | Status |
| --- | --- | --- | --- | --- |
| P4.1 | Python decorators & raw AST | `[PythonDecorator("...")]` and attribute-based decorators lowered directly to Python decorators via `RAW_PYTHON_AST` | Phase 2 | DONE |
| P4.2 | Pydantic v2 schemas | `[SchemaModel]` lowering to Pydantic `BaseModel` classes with field annotations, default values, and computed properties | Phase 2 | DONE |
| P4.3 | KwArgs lowering | `[KwArgs]` parameter lowering to Python `**kwargs` dictionary arguments | Phase 1 | DONE |
| P4.4 | Generators & async streams | C# `yield return` and `yield break` lowering; `IAsyncEnumerable<T>` and `IAsyncEnumerator<T>` Core declarations | Phase 2 | DONE |

**Scope**

- `[PythonDecorator]` lowering with compile-time parsing and validation into Python decorator expressions.
- `[SchemaModel]` lowering to Pydantic v2 `BaseModel` without `__slots__` or dataclass collisions.
- Python `**kwargs` parameter interop via `[KwArgs]`.
- Native generator lowering (`yield return` -> `yield`) and async streams (`IAsyncEnumerable<T>`, `IAsyncEnumerator<T>`).
- Context managers with `IDisposable` and `IAsyncDisposable`.
- Zero-runtime wrapper tax preserved: no runtime dependency is required unless user code opts into Pydantic models.

**Exit gate**

- All Phase 4 metaprogramming unit and integration tests pass (117 tests total across 27 test files).
- Metaprogramming features have explicit runtime dependency declarations (Pydantic models require `pydantic`).
- Decorator, schema, kwargs, generator, and async streams lowering is covered by test suites.
- Zero-runtime wrapper tax is strictly preserved for projects not opting into Pydantic.

## 7. Phase 5: Tooling and native compilation (DONE)

**Objective:** Support large projects and advanced distribution.

### 7.1 Workstreams

| ID | Workstream | Deliverable | Dependency | Status |
| --- | --- | --- | --- | --- |
| P5.1 | Incremental compilation & caching | `BuildCacheManager` in `src/psc/build_cache.py` with SHA-256 content hashes, cache hit/miss tracking, and `--force` CLI option | Phase 1 | DONE |
| P5.2 | Watch mode | `ProjectWatcher` in `src/psc/watcher.py` and `psc watch` CLI command with auto-rebuild and debounce | P5.1 | DONE |
| P5.3 | Language Server Protocol (LSP) | Pure-Python LSP server in `src/psc/lsp/` implementing JSON-RPC 2.0, diagnostics, hover, definition, completion, and `psc lsp` CLI command | Phase 1-2 | DONE |
| P5.4 | Native compilation orchestration | `NativeCompiler` in `src/psc/native/` with `[NativeCompile]` detection, `mypyc`/`Cython` AOT C-extension compilation, and `--native` CLI flag | Phase 1 | DONE |

**Scope**

- Incremental build caching with content hashing (`BuildCacheManager` storing SHA-256 of all inputs and outputs).
- Watch mode (`psc watch`) for automatic continuous recompilation on file change.
- Language Server Protocol (`psc lsp`) supporting standard JSON-RPC 2.0 over stdio for IDE integration: real-time diagnostics (`textDocument/publishDiagnostics`), hover documentation (`textDocument/hover`), go-to-definition (`textDocument/definition`), and autocompletion (`textDocument/completion`).
- Native AOT compilation orchestrator (`[NativeCompile]` and `psc build --native`) compiling generated Python to high-performance C-extensions via `mypyc` or Cython.

**Exit gate**

- All Phase 5 tooling and native compilation tests pass (128 tests total across 31 test files).
- Incremental builds avoid redundant compilation on unchanged projects.
- Watch mode reacts to file edits and triggers rebuilds.
- LSP server passes protocol verification for initialize, open/diagnostics, hover, definition, and completion.
- Native compiler detects `[NativeCompile]` and orchestrates extension generation.

## 8. Cross-cutting workstreams

These run in every phase:

| Workstream | Ongoing work |
| --- | --- |
| Documentation | Keep docs and progress current; update on design changes |
| CI | Expand the platform/version matrix; keep gates fast and deterministic |
| Security | Never execute project code at compile time; review native/bindgen execution paths |
| Performance | Track compile time, output size, and runtime overhead |
| Compatibility | Test against the supported CPython matrix and representative libraries |
| DX | Diagnostics, suggested fixes, sample projects, and tutorials |
| Release | SemVer, changelog, wheel verification, and reproducible builds |

## 9. Sequencing and dependencies

```text
M0 ─▶ M1 ─▶ M2 ─▶ M3 ─▶ M4 ─▶ M5 ─▶ M6
                               │
                               ▼
                          Phase 2
                         ┌────┴────┐
                         ▼         ▼
                     Phase 3   Phase 4
                         └────┬────┘
                              ▼
                          Phase 5
```

- M1 depends on M0 for packaging and CI.
- M2 depends on M1 AST and diagnostics.
- M3 and M4 depend on M2 symbols and type resolution.
- M5 depends on M3 and M4 lowering decisions.
- M6 depends on M5's Python AST output.
- Phase 3 depends on stable symbol, type, and binding-extension interfaces from
  Phase 2.
- Phase 5 depends on stable Phase 1-3 interfaces and Phase 2 performance baselines.

## 10. Release milestones

| Release | Contents | Exit criteria |
| --- | --- | --- |
| `0.1.0-alpha` | M1-M3 | Frontend and semantic analysis pass unit tests |
| `0.2.0-alpha` | M4-M5 | Full pipeline builds Python ASTs for the corpus |
| `0.3.0-beta` | M6 | CLI, bytecode, tracebacks, commerce sample |
| `1.0.0` | Phase 2 | Core API stable, compatibility matrix green |
| `1.1.0` | Phase 3 | Bindgen for representative packages |
| `1.2.0` | Phase 4 | Decorators, schema models, async |
| `2.0.0` | Phase 5 | LSP, incremental builds, native compilation |

## 11. Change control

- A milestone's scope is frozen at its start; new work goes to a later milestone
  unless it is required to pass a gate.
- Any change to phase ordering or release criteria requires an entry in the
  decision log in [PROGRESS.md](PROGRESS.md).
- New language features must document their lowering and diagnostics before
  implementation.
- Features without a Python-isomorphic lowering are rejected or deferred.
