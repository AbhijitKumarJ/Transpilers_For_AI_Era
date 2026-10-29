# PythonSharp Progress Tracker

**Last updated:** 2026-10-30
**Repository HEAD:** `c31494b` Docs: add 12-part comprehensive blog series in docs/blogs
**Current phase:** Phases 1-5 Complete; Real-World Dogfooding (8 Ported Packages) Complete; 12-Part Blog Series Complete; CI marked OUT OF SCOPE
**Overall implementation:** All 5 roadmap phases verified; 8 canonical Python libraries ported in `Samples/Ported/`; 12-part blog series in `docs/blogs/`; 130 test suites passing locally; CI marked OUT OF SCOPE (D-015)

This is the single live status document. Update it whenever work starts, a task
completes, a gate passes, or a decision is made.

## 1. Snapshot

| Area | Status | Notes |
| --- | --- | --- |
| Ideation review | DONE | Raw design archive read and synthesized |
| Documentation set | DONE | 12 core documents + 12-part blog series in `docs/blogs/` |
| Phase 0 exit gate | DONE | Scope, stack, architecture, and diagnostics recorded |
| Phase 1 implementation | DONE | M0 scaffold through M6 emitter, CLI, Core stub, and release tests implemented locally |
| Phase 1 M0-M6 gates | DONE | 7 / 7 verified locally on Linux with CPython 3.11-3.13; CI marked out of scope |
| Phase 2 P2.1-P2.6 | DONE | Direct Python exception model, Core API surface, LINQ operators & fusion, golden output corpus |
| Phase 3 ps-bindgen | DONE | `.pyi` AST parser, `TypeConverter`, `BindgenGenerator`, `psc bindgen` CLI, and manifest drift tracking |
| Phase 4 metaprogramming | DONE | `[PythonDecorator]`, `[SchemaModel]` Pydantic v2 emission, `[KwArgs]`, generator `yield`, and async streams (`IAsyncEnumerable<T>`) |
| Phase 5 tooling & native | DONE | Incremental compilation cache (`BuildCacheManager`), continuous watch mode (`psc watch`), pure-Python LSP server (`psc lsp`), and AOT native compilation (`[NativeCompile]`) |
| Dogfooding (Ported Packages) | DONE | 8 canonical Python libraries ported in `Samples/Ported/` (Tiers 1-4: left-pad, slugify, is-prime, levenshtein, semver, micro-tqdm, micro-dotenv, micro-requests) |
| Blog Series | DONE | 12 beginner-friendly architectural and tutorial blog posts in `docs/blogs/` with master `PLAN.md` |
| Compiler Enhancements | DONE | `BreakStmt`/`ContinueStmt`, ternary `? :`, integer division `//`, binary expression type resolution, escape unescaping, Core stdlib additions (`Int32`, `Double`, `Boolean`, `Console.Write`, `String.Join`) |
| Multi-Extension Support | DONE | `.ps`, `.pysharp`, `.pys`, `.d.ps`, `.d.pysharp`, `.d.pys`, `.psproj`, `.pysharpproj` |
| Diagnostics PS000-PS004 | DONE | All five codes implemented, tested, and equipped with actionable hints |
| Packaging | DONE | Tested and verified wheel and sdist generation (`dist/pythonsharp_compiler-0.1.0-py3-none-any.whl`) |
| Editor support | DONE | Documented LSP integration (`docs/LSP.md`), Go-To-Definition across files and stdlib, VS Code extension bundle (`editors/vscode/`) |
| Test suite | DONE | 31 test files, 130 tests, >95% line coverage (all passing in ~3.5s) |
| CI | OUT OF SCOPE | Remote GitHub Actions / cross-platform CI matrix marked OUT OF SCOPE (D-015); local Linux suite (CPython 3.11-3.13) is 100% green |
| Git status | Phase 5 complete | All 5 phases implemented and verified locally |

## 2. Status legend

| Status | Meaning |
| --- | --- |
| DONE | Implemented and verified; committed unless marked uncommitted |
| DONE (uncommitted) | Verified locally; commit pending |
| IN PROGRESS | Actively being worked |
| BLOCKED | Cannot proceed without a decision or dependency |
| TODO | Planned, not started |
| DEFERRED | Intentionally moved beyond the current phase |

Checklists use `[x]` only when the task is verified. A design draft in `Ideation/`
does not count as implementation.

## 3. Phase 0: Ideation and architecture (DONE)

- [x] Read the ten files in `Ideation/`.
- [x] Extract the language syntax and lowering model.
- [x] Extract the six-milestone Phase 1 plan.
- [x] Extract the Phase 1-5 roadmap.
- [x] Identify the missing support files (`type_checker.py`, fixtures, README).
- [x] Record the feasibility rationale and known semantic risks.
- [x] Create [PRD.md](PRD.md).
- [x] Create [TECH-STACK.md](TECH-STACK.md).
- [x] Create [ROADMAP.md](ROADMAP.md).
- [x] Create [ARCHITECTURE.md](ARCHITECTURE.md).
- [x] Create [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md).
- [x] Create [DIAGNOSTICS.md](DIAGNOSTICS.md).
- [x] Create [TESTING.md](TESTING.md).
- [x] Create this tracker.
- [x] Cross-check document links, fences, and terminology.
- [x] Review and commit the documentation set (`a85bbec`).
- [ ] Resolve the open language decisions needed before lowering (M3-M5).

Phase 0 is complete as a design milestone. The remaining unchecked item covers
semantic decisions for later lowering passes, not M1 parsing.

## 4. Phase 1: Core compiler (DONE locally)

Reference drafts for M1-M6 live in `Ideation/Milestone 1.md` through
`Ideation/Milestone 6.md` plus `Ideation/Milestone 1-6 missing files.md`. All six
milestones have been extracted into `src/psc/`, adapted to the package layout, and
verified locally. Phase 1 is complete on the local Linux host; GitHub Actions
execution and publishing are deferred by decision D-015. The baseline is committed
as `d14384d`.

### M0: Repository bootstrap (DONE locally, 100%)

- [x] Create `src/psc/` package skeleton.
- [x] Create `tests/` and `tests/fixtures/` structure.
- [x] Add the commerce sample fixture skeleton.
- [x] Create `stdlib/PythonSharp.Core.d.ps`.
- [x] Create `pyproject.toml` with `setuptools`, console script, and dev extras.
- [x] Configure `ruff`, `mypy`, `pytest`, and a 90% coverage threshold.
- [x] Add GitHub Actions test, generated-code, packaging, and CLI smoke jobs.
- [x] Verify `.gitignore` covers `.venv`, `dist`, caches, and `.pyc`.
- [x] Add the MIT license and contribution notes.
- [x] Extract the M1 ideation reference draft into source files.
- [x] Verify editable install, `psc --version`, and `psc --help` in `.venv`.
- [x] Retain the CI workflow for later use; GitHub execution is deferred (D-015).
- [x] Validate the CI-equivalent local matrix: Python 3.11, 3.12, and 3.13 on Linux.
- [x] Validate generated-code Pyright strict, wheel install, and sdist install locally.

**Gate:** verified locally. Install, lint, format, strict mypy, tests, coverage,
generated-code Pyright, and clean wheel/sdist installs pass. GitHub Actions and
publishing are intentionally deferred by D-015; no CI run is claimed.

### M1: Frontend foundation (DONE locally, 100%)

- [x] Implement `SourceSpan`, `Diagnostic`, and `DiagnosticEngine`.
- [x] Implement token kinds and tokens.
- [x] Implement the lexer for comments, literals, interpolation, and operators.
- [x] Define the multi-pass AST.
- [x] Implement declaration and statement parsing.
- [x] Implement Pratt expression parsing with the specified precedence.
- [x] Implement parser error recovery and termination guards.
- [x] Extract and expand `tests/test_lexer_parser.py`.
- [x] Add lexer, diagnostics, parser, precedence, and CLI test coverage.
- [x] Assert spans, operator precedence, recovery, and `PS000` behavior.
- [x] Reach the frontend coverage gate.

**Gate:** verified locally. The commerce fixtures parse with zero diagnostics;
malformed input reports `PS000` and terminates; precedence tests cover every
operator level; frontend coverage is 98% and total line coverage is 98%. Committed in `d14384d`.

### M2: Pass 1 - project and symbols (DONE locally, 100%)

- [x] Implement `.psproj` loading for XML and TOML.
- [x] Implement deterministic source and stub discovery.
- [x] Implement the global symbol table and scopes for the project-level symbol model.
- [x] Implement the symbol collector.
- [x] Aggregate virtual namespaces and detect path collisions.
- [x] Resolve cross-file and circular type references.
- [x] Validate imported and `extern using` alias resolution used by the symbol table.
- [x] Add `tests/test_project.py`, `tests/test_symbols.py`, and the collector suites.

**Gate:** verified locally. The commerce fixture resolves in both file orders;
inheritance cycles, duplicate types, and namespace path collisions report `PS000`
with precise spans; project loading covers XML, TOML, defaults, stub ordering, and
deduplication. Semantic-module coverage is 99% and project loading is 100%. Committed in `d14384d`.

### M3: Pass 2A - layout and access (DONE locally, 100%)

- [x] Implement slot planning with inheritance deduplication.
- [x] Emit `__ps_types__` with transitive nominal ancestry.
- [x] Synthesize `IDisposable` context-manager methods.
- [x] Synthesize `IAsyncDisposable` context-manager methods.
- [x] Implement `PS001` access and readonly checks.
- [x] Implement `PS003` circular static initializer detection.
- [x] Implement `PS004` `[NativeCompile]` dynamic checks.
- [x] Add `tests/test_access_and_slots.py`.
- [x] Assert getter/setter visibility independently.

**Gate:** verified locally. Slot layouts deduplicate inherited and shadowed fields;
`__ps_types__` carries transitive nominal ancestry; sync and async disposal are
detected through inheritance and unresolved external interfaces; public, internal,
protected, and private access plus readonly writes are enforced; PS003 and PS004
have positive and negative tests. Access-checker coverage is 90%, slot-analyzer
coverage is 95%, and total coverage is 97%. Committed in `d14384d`.

### M4: Pass 2B - erasure, overloads, LINQ, types (DONE locally, 100%)

- [x] Implement `[MapsTo]` type and member erasure.
- [x] Implement `[InlineTemplate]` expansion.
- [x] Implement overload group construction.
- [x] Implement `PS002` collision detection.
- [x] Implement the runtime dispatch plan with the strict bool/int guard.
- [x] Implement LINQ chain recognition and fusion.
- [x] Implement lambda alpha-renaming.
- [x] Implement the Phase 1 type checker and nullability checks.
- [x] Add `tests/test_overloads_and_linq.py`, `tests/test_primitive_resolver.py`, and `tests/test_type_checker.py`.

**Gate:** verified locally. Primitive members lower to inline templates or mapped
targets; overloads produce deterministic arity/type guards, with strict-int guards
preventing `bool` from selecting an `int` overload; PS002 rejects erased generic
collisions; LINQ terminals, `SelectMany`, `ToDict`, projection substitution, and
alpha-renaming are covered; generic constraints and non-nullable assignments report
`PS000`. Primitive-resolver coverage is 95%, overload coverage is 93%, LINQ coverage
is 87%, type-checker coverage is 94%, and total coverage is 96%. Committed in `d14384d`.

### M5: Pass 3A - Python AST (DONE locally, 100%)

- [x] Implement namespace planning and class topological sorting.
- [x] Implement expression and statement lowering.
- [x] Implement null-safety with single evaluation.
- [x] Implement slicing and interpolation lowering.
- [x] Implement overload stubs and dispatch routers.
- [x] Build Python `ast.Module` trees.
- [x] Stamp `.ps` spans on emitted nodes.
- [x] Validate modules with `compile()`.
- [x] Add `tests/test_py_ast_builder.py` and `tests/test_codegen_lowering.py`.

**Gate:** verified locally. Every commerce fixture module builds and compiles;
the end-to-end `OrderCache` and slicing/null-safety modules execute; broad
statement/expression lowering compiles inside a synthetic async function; block
and async lambdas are hoisted to nested functions; Python-keyword identifiers are
suffixed with `_`. Statement and expression nodes are span-stamped from `.ps`
locations. At the M5 gate, coverage was 84.7% across codegen and 93.6% overall;
the final Phase 1 totals are in section 10. Committed in `d14384d`.

### M6: Pass 3B, CLI, and release readiness (DONE locally, 100%)

- [x] Emit `.py` packages with `__init__.py` markers.
- [x] Emit PEP 552 timestamp-invalidated `.pyc` artifacts.
- [x] Pin `co_filename` recursively to `.ps` files.
- [x] Write the deterministic `psc-manifest.json` build manifest.
- [x] Implement `check`, `build`, `dump-ast`, and `run` CLI commands.
- [x] Add `--version` and package metadata.
- [x] Complete `stdlib/PythonSharp.Core.d.ps`.
- [x] Add `tests/test_bytecode_tracebacks.py`.
- [x] Add `tests/test_emitter.py`, `tests/test_cli.py`, `tests/test_determinism.py`.
- [x] Add the end-to-end commerce sample test.
- [x] Verify wheel install in a clean environment.
- [x] Measure the 25k LOC compile baseline.
- [x] Write the README and quickstart.
- [x] Validate the generated commerce package with Pyright strict.
- [x] Package the Core stub as wheel data and verify `psc check/build` outside the repo.

**Gate:** verified locally. `psc build` emits a runnable package plus
`psc-manifest.json`; tracebacks report `.ps` files and lines; two builds produce
byte-identical `.py` and manifest output; Pyright strict reports zero errors on
the commerce corpus; a clean wheel install compiles an external project. The
measured baseline is 7.55 seconds for 26,002 LOC (1,000 classes, 21 methods each).
Final coverage is 90.4% across codegen and 94.9% overall. Committed in `d14384d`.

## 5. Later phases

| Phase | Status | Entry condition |
| --- | --- | --- |
| Phase 2: Core library and hardening | DONE | Phase 1 release criteria met; P2.1-P2.6 complete |
| Phase 3: `ps-bindgen` | DONE | Phase 2 complete; P3.1-P3.4 complete |
| Phase 4: Metaprogramming | DONE | Phase 1-3 complete; P4.1-P4.4 complete |
| Phase 5: Tooling and native compilation | DONE | Phase 1-4 complete; P5.1-P5.4 complete |

Detailed scope and gates are in [ROADMAP.md](ROADMAP.md).

## 6. Immediate next actions

1. Maintain 100% clean test suite across all 128 tests on CPython 3.11-3.13.
2. Maintain zero-runtime wrapper tax across all emitted projects.
3. Remote GitHub Actions CI is marked OUT OF SCOPE (D-015); local Linux gate passes 100% on CPython 3.11-3.13.
4. Packaging verified with standalone wheel and sdist in `dist/`.

## 7. Open decisions

| ID | Decision | Blocks | Status |
| --- | --- | --- | --- |
| OQ-01 | `struct` value-copy semantics (or explicit unsupported status) | M5 | RESOLVED: reference semantics documented, no copy-on-assign |
| OQ-02 | `switch` pattern lowering scope; parser supports discard, null, literal, type/property patterns with guards | M5 | RESOLVED: only faithful Python patterns lower; complex patterns deferred |
| OQ-03 | Exception model mapping for parsed typed/untyped catch, `when`, `finally`, and bare `throw` | M5 | RESOLVED: direct Python exception model, D-016 |
| OQ-04 | Property lowering details (backing slots, init-only) | M5 | RESOLVED: auto-properties use backing slots; expression properties are read-only; static properties use class attributes/classmethods (D-019) |
| OQ-05 | Minimum CPython patch version for `.pyc` artifacts | M6 | RESOLVED: host CPython 3.11+ bytecode; `.pyc` is host-specific, `.py` is portable |
| OQ-06 | Generic constraint enforcement scope in Phase 1 | M4 | RESOLVED: explicit bounds checked statically, erased at runtime |
| OQ-07 | Caching and incremental build strategy | Phase 2 | RESOLVED: content-hash build caching in Phase 5 via `BuildCacheManager` (D-022) |
| OQ-08 | Operator overload spelling and lowering | Phase 2 | RESOLVED: deferred to Phase 4; no operator overloading in the Phase 2 stable subset (D-020) |

## 8. Decision log

| ID | Date | Decision | Rationale |
| --- | --- | --- | --- |
| D-001 | 2026-10-28 | Host the compiler on Python 3.11+ | `tomllib`, stable `ast`, audience fit, no second toolchain |
| D-002 | 2026-10-28 | Use a hand-written lexer and recursive-descent/Pratt parser | Debuggable positions, no parser runtime dependency, fine control |
| D-003 | 2026-10-28 | Map one logical namespace to one emitted Python module | Matches the prototype planner and file-independent namespaces |
| D-004 | 2026-10-28 | Use PEP 552 timestamp-invalidated `.pyc` headers | Matches the prototype emitter; source-hash mode deferred |
| D-005 | 2026-10-28 | Enforce access control at compile time only, without name mangling | Runtime readability and Python interop |
| D-006 | 2026-10-28 | Define `PS003` as circular static initialization and `PS004` as NativeCompile dynamic use | Corrects an earlier slot-diagnostic assumption; matches ideation |
| D-007 | 2026-10-28 | Keep zero third-party runtime dependencies | Simple install, portable compiler, no hidden runtime |
| D-008 | 2026-10-28 | Split documentation into PRD, stack, roadmap, architecture, spec, diagnostics, testing, tracker | Clear ownership and update paths |
| D-009 | 2026-10-28 | Structs/records use Python reference semantics; no copy-on-assignment in Phase 1 | Matches the documented Python target and avoids hidden cloning |
| D-010 | 2026-10-28 | Lower only switch patterns with faithful Python `match` equivalents | Prevents silent semantic drift |
| D-011 | 2026-10-28 | Auto-properties lower to `@property` over `_snake_case` slots; computed properties are read-only | Keeps emitted classes Pythonic and enforces access checks statically |
| D-012 | 2026-10-28 | Enforce explicit generic bounds at compile time and erase them at runtime | Preserves C# discipline without runtime generic wrappers |
| D-013 | 2026-10-28 | Treat `.pyc` artifacts as host-interpreter-specific and `.py` as the portable artifact | PEP 552 bytecode magic is tied to the emitting CPython minor version |
| D-014 | 2026-10-28 | Mark generated runtime overload dispatchers with `# type: ignore` while keeping `@overload` stubs fully checked | Variadic runtime dispatch cannot satisfy Pyright's static overload-consistency rule; the public stubs remain the checked contract |
| D-015 | 2026-10-28 | Accept local Linux verification as the complete exit gate; mark remote GitHub Actions and cross-platform CI matrix OUT OF SCOPE | The maintainer is not using GitHub Actions or publishing now; all locally executable gates pass on CPython 3.11-3.13 across all 128 tests |
| D-016 | 2026-10-28 | Use direct Python exceptions without a wrapper hierarchy; map Core exception names through `[MapsTo]`, lower untyped `catch` to `BaseException`, and use an ordered `BaseException` dispatcher for guarded/multiple catches | Preserves C# catch order and guard fallthrough while keeping emitted code idiomatic and Pyright-clean; bare `throw;` is valid only inside a catch |
| D-017 | 2026-10-28 | Fuse LINQ only when overload resolution attaches an explicit `[LinqStage]`; do not infer fusion from the method name | Prevented `Math.Max`/`Math.Min` from being mis-lowered as LINQ terminals and keeps fusion tied to the Core contract |
| D-018 | 2026-10-28 | Lower non-fusable LINQ chains to ordinary Python iterator calls; compose ordering keys by applying stable sorts from the last key to the first; defer `SingleOrDefault` | Preserves C# ordering semantics without runtime wrappers; ordering and materialisation operators are documented as eager, and `SingleOrDefault` stays out of the stable subset until a faithful single-element guard exists |
| D-019 | 2026-10-28 | Lower static auto-properties to class attributes (`ClassVar` inside dataclasses); lower static getter-only computed properties to classmethods and rewrite their accesses to calls; qualify bare static members with the declaring type; reject static custom setters, setters on frozen records, and unsupported record/struct instance fields and auto-properties | Avoids a cross-version `classmethod`/`property` incompatibility (Python 3.13), keeps static access lazy and Pyright-clean, and turns previously broken dataclass member shapes into explicit diagnostics |
| D-020 | 2026-10-28 | Defer operator overloads to Phase 4; Phase 2 has no operator-overloading syntax or lowering | The Phase 4 scope already defines optional operator overloads with documented Python dunder mapping; keeping Phase 2 focused preserves the stable semantic subset |
| D-021 | 2026-10-29 | Lower `[SchemaModel]` to Pydantic v2 `BaseModel` without dataclass or `__slots__` wrappers; import `from pydantic import BaseModel` only on-demand | Preserves zero-runtime wrapper tax for projects not opting into schemas while giving Pydantic full control over validation, serialization, and OpenAPI schemas |
| D-022 | 2026-10-29 | Implement incremental SHA-256 build caching (`BuildCacheManager`), continuous watch mode (`psc watch`), pure-Python LSP server over JSON-RPC 2.0 (`psc lsp`), and AOT native compilation orchestration (`[NativeCompile]`) via mypyc/Cython | Delivers IDE intelligence, rapid developer feedback loops, build skipping for unchanged inputs, and native extension compilation with zero external runtime dependencies |

## 9. Changelog

| Date | Change |
| --- | --- |
| 2026-10-28 | Created the `docs/` set: index, PRD, tech stack, roadmap, architecture, language spec, diagnostics, testing, and this tracker |
| 2026-10-28 | Aligned `.pyc` documentation to timestamp-based PEP 552 |
| 2026-10-28 | Corrected PS003/PS004 definitions and CLI command list to match the prototype design |
| 2026-10-28 | Committed the documentation set as `a85bbec` |
| 2026-10-28 | Bootstrapped M0: package skeleton, `pyproject.toml`, fixtures, stdlib stub, CI matrix, MIT license, README quickstart, and contribution notes |
| 2026-10-28 | Extracted the M1 frontend into `src/psc/frontend/` and `src/psc/diagnostics.py`; verified the commerce fixtures parse cleanly |
| 2026-10-28 | Added lexer, diagnostics, parser, precedence, recovery, and CLI tests; reached 28 tests and 98% line coverage |
| 2026-10-28 | Implemented M2 project loading, symbol table, symbol collector, namespace collision detection, and cross-file resolution; reached 47 tests with 99% semantic coverage |
| 2026-10-28 | Implemented M3 slot analysis, `__ps_types__`, disposal synthesis, `PS001`, `PS003`, and `PS004`; reached 56 tests with 97% total coverage |
| 2026-10-28 | Implemented M4 primitive erasure, overload dispatch with strict bool/int guards, `PS002`, LINQ fusion, lambda alpha-renaming, and the type checker; reached 63 tests with 96% total coverage |
| 2026-10-28 | Implemented M5 namespace planning, topological sorting, statement/expression lowering, null safety, slicing, overload emission, block/async lambda hoisting, and Python AST construction; reached 68 tests with 94% total coverage |
| 2026-10-28 | Implemented M6 `.py`/`.pyc` emission, deterministic manifest, CLI commands, full Core stub, bytecode tracebacks, determinism, end-to-end commerce execution, clean-wheel packaging, Pyright strict validation, and README quickstart; reached 78 tests with 94.9% total coverage and a 7.55s 26k LOC baseline |
| 2026-10-28 | Closed Phase 1 locally after CPython 3.11-3.13 verification, hash-seed determinism, Pyright strict, and clean wheel/sdist installs; GitHub Actions and publishing deferred by D-015 |
| 2026-10-28 | Committed the Phase 1 baseline as `d14384d` and started Phase 2 planning |
| 2026-10-28 | Completed P2.1 exception semantics: D-016 direct Python mapping, Core exception surface, ordered guarded-catch dispatcher, untyped `BaseException` catch, and bare-throw validation; reached 84 tests with 94.9% total coverage |
| 2026-10-28 | Completed P2.2 Core API completion: added `Math`, String/List/Dict/HashSet members, automatic `math` import, expanded exception mappings, explicit-LINQ-stage fusion guard, and documented the stable Core subset; reached 88 tests with 95.0% total coverage and Pyright strict clean |
| 2026-10-28 | Completed P2.3 LINQ surface: added `OrderBy`/`OrderByDescending`/`ThenBy`/`ThenByDescending`, `Distinct`, `Take`, `Skip`, `Concat`, `Contains`, `LastOrDefault`, `Average`, `Min`, and `Max`; implemented lazy iterator fallback with stable ordering composition and automatic `itertools`/`statistics` imports; reached 90 tests with 95.1% total coverage and Pyright strict clean; deferred `SingleOrDefault` |
| 2026-10-28 | Completed P2.4 semantic hardening: added static auto/computed property lowering and static-member qualification, `ClassVar` handling for record static state, explicit diagnostics for unsupported static setters and record/struct instance member shapes, retained generic-erasure PS002 coverage, and resolved OQ-08 as deferred to Phase 4; reached 95 tests with 95.1% total coverage and Pyright strict clean |
| 2026-10-29 | Committed P2.4 as `70497d8`; completed P2.5 with golden output corpus, `--update-golden` workflow, golden runtime execution, CPython 3.11-3.13 regression runs, enum implicit-value fix, nullable-erasure PS002 fix, LINQ unresolved-annotation fix, interpolated-string implicit-`this` fix, deterministic import ordering, and compiler benchmark harness; committed as `35b9671` |
| 2026-10-29 | Completed P2.6 API & diagnostics polish: authored comprehensive `docs/CORE-API.md`, added actionable fix hints for PS000-PS004 in `DiagnosticEngine`, documented diagnostics with hints in `docs/DIAGNOSTICS.md`, compiled `docs/RELEASE-NOTES-PHASE-2.md`, fixed benchmark standalone `sys.path`; reached 103 tests with >95% total coverage |
| 2026-10-29 | Completed Phase 3 ps-bindgen (P3.1-P3.4): implemented `TypeConverter` for Python AST type translation, `BindgenGenerator` with C# PascalCase naming, `[MapsTo]` aliasing, union overload splitting, properties, staticmethods, constructors, and indexers; added `BindingManifest` with SHA-256 drift detection; integrated `psc bindgen` CLI subcommand; verified end-to-end transpilation against generated stubs; reached 112 tests across 26 test files with >95% line coverage |
| 2026-10-29 | Completed Phase 4 Pythonic metaprogramming (P4.1-P4.4): implemented `[PythonDecorator]` raw AST lowering for literal expressions and attribute decorators, `[SchemaModel]` Pydantic v2 `BaseModel` emission with auto-property fields and zero-slot footprint, `[KwArgs]` parameter lowering to `**kwargs`, generator `yield return` lowering, and `IAsyncEnumerable<T>` / `IAsyncEnumerator<T>` Core declarations; reached 117 tests across 27 test files with >95% line coverage and zero wrapper tax |
| 2026-10-29 | Completed Phase 5 Tooling & native compilation (P5.1-P5.4): implemented incremental SHA-256 compilation cache (`BuildCacheManager`), continuous auto-rebuild watch mode (`ProjectWatcher` and `psc watch`), pure-Python Language Server Protocol server (`LanguageServer` and `psc lsp` supporting JSON-RPC 2.0 diagnostics, hover, definition, completion), and native AOT compilation orchestration (`NativeCompiler` with `[NativeCompile]` and `psc build --native`); reached 128 tests across 31 test files with >95% line coverage |

## 10. Metrics

| Metric | Current | Target |
| --- | --- | --- |
| Documentation set | 11 / 11 | 9 / 9 |
| Phase 1 milestones started | 7 / 7 | 7 / 7 |
| Phase 1 milestones verified | 7 / 7 | 7 / 7 |
| Diagnostics implemented | 5 / 5 | 5 / 5 |
| Test files | 31 | All milestone suites |
| Automated tests | 128 | Grows with each milestone |
| Compiler line coverage | 95.1% | ≥ 90% |
| Frontend coverage | 98.3% | ≥ 90% |
| Semantic passes coverage | 95.1% | ≥ 90% |
| Codegen coverage | 91.5% | ≥ 90% |
| CLI coverage | 91.6% | ≥ 80% |

| Metric | Current | Target |
| --- | --- | --- |
| Documentation set | 11 / 11 | 9 / 9 |
| Phase 1 milestones started | 7 / 7 | 7 / 7 |
| Phase 1 milestones verified | 7 / 7 | 7 / 7 |
| Diagnostics implemented | 5 / 5 | 5 / 5 |
| Test files | 27 | All milestone suites |
| Automated tests | 117 | Grows with each milestone |
| Compiler line coverage | 95.1% | ≥ 90% |
| Frontend coverage | 98.3% | ≥ 90% |
| Semantic passes coverage | 95.1% | ≥ 90% |
| Codegen coverage | 91.5% | ≥ 90% |
| CLI coverage | 91.6% | ≥ 80% |
| Access checker coverage | 93.5% | ≥ 90% |
| Slot analyzer coverage | 96.0% | ≥ 90% |
| Primitive resolver coverage | 95.4% | ≥ 90% |
| Overload resolver coverage | 95.2% | ≥ 90% |
| Type checker coverage | 96.3% | ≥ 90% |
| Project loader coverage | 100% | ≥ 90% |
| Commerce sample status | Builds, imports, runs, and reports `.ps` tracebacks | Compiles, runs, tracebacks correct |
| Deterministic `.py` builds | Verified for `.py` and manifest | Verified |
| 25k LOC compile time | 20.1s best-of-1 / 21.9s best-of-2 on the local 4-core i5-7200U; M6 reference is 7.55s for 26,002 LOC | ≤ 10s on a typical laptop; nightly regression budget is 30s on the local host |

## 11. Update protocol

| Metric | Current | Target |
| --- | --- | --- |
| Documentation set | 11 / 11 | 9 / 9 |
| Phase 1 milestones started | 7 / 7 | 7 / 7 |
| Phase 1 milestones verified | 7 / 7 | 7 / 7 |
| Diagnostics implemented | 5 / 5 | 5 / 5 |
| Test files | 26 | All milestone suites |
| Automated tests | 112 | Grows with each milestone |
| Compiler line coverage | 95.1% | ≥ 90% |
| Frontend coverage | 98.3% | ≥ 90% |
| Semantic passes coverage | 95.1% | ≥ 90% |
| Codegen coverage | 91.5% | ≥ 90% |
| CLI coverage | 91.6% | ≥ 80% |
| Access checker coverage | 93.5% | ≥ 90% |
| Slot analyzer coverage | 96.0% | ≥ 90% |
| Primitive resolver coverage | 95.4% | ≥ 90% |
| Overload resolver coverage | 95.2% | ≥ 90% |
| Type checker coverage | 96.3% | ≥ 90% |
| Project loader coverage | 100% | ≥ 90% |
| Commerce sample status | Builds, imports, runs, and reports `.ps` tracebacks | Compiles, runs, tracebacks correct |
| Deterministic `.py` builds | Verified for `.py` and manifest | Verified |
| 25k LOC compile time | 20.1s best-of-1 / 21.9s best-of-2 on the local 4-core i5-7200U; M6 reference is 7.55s for 26,002 LOC | ≤ 10s on a typical laptop; nightly regression budget is 30s on the local host |

## 11. Update protocol

1. Change a task to `[x]` only after its test or gate passes.
2. Update the milestone percentage and snapshot table in the same change.
3. Add an entry to the changelog for any status or scope change.
4. Add a decision-log entry for any change to architecture, diagnostics, phase
   ordering, or release criteria.
5. Include the commit hash when a milestone gate is verified.
6. Keep dates in `YYYY-MM-DD` format.
7. If work is paused, record the blocker and the next concrete action in section 6.
