# PythonSharp Phase 2 Release Notes: Core Library and Hardening

**Phase:** Phase 2 (P2.1 – P2.6 Complete)  
**Date:** 2026-10-29  
**Repository Baseline:** `35b9671`  
**Related Documents:** [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [CORE-API.md](CORE-API.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [TESTING.md](TESTING.md), [PROGRESS.md](PROGRESS.md)

---

## 1. Executive Summary

Phase 2 (*Core Library and Hardening*) builds on the initial Phase 1 compiler foundation to turn PythonSharp into a production-grade transpiler. While Phase 1 proved that a static multi-pass C#-to-Python compiler could emit runnable, typed Python packages, Phase 2 broadens the standard library surface, hardens language edge cases, ensures strict Python 3.11–3.13 compatibility, adds an automated regression corpus, and polishes diagnostics with actionable user hints.

Across Phase 2, the compiler maintained its defining core architectural principle: **zero runtime wrapper tax**. Transpiled code runs on standard Python 3.11+ interpreters without any third-party packages or runtime adapters.

---

## 2. Milestone Deliverables

### P2.1: Exception Semantics (Decision D-016)
- **Direct Exception Mapping**: Exceptions map directly to Python native exceptions (`ValueError`, `RuntimeError`, `KeyError`, `IndexError`, `OSError`, etc.) via `[MapsTo]` attributes in `PythonSharp.Core.d.ps`.
- **Ordered Guarded Dispatcher**: Multiple `catch` blocks and `when` filter conditions lower through an ordered dispatcher over `BaseException`. If a filter condition evaluates to `False`, execution falls through cleanly to subsequent handlers, matching C# specification.
- **Untyped Catch**: Lowered to `except BaseException:`.
- **Bare `throw;`**: Lowered to bare Python `raise;` and validated at compile time so that bare `throw;` outside a catch handler produces a precise `PS000` diagnostic.

### P2.2: Core API Completion (Decision D-017)
- **`Math` Class**: Full mathematical function mapping (`Sqrt`, `Pow`, `Abs`, `Round`, `Floor`, `Ceiling`, `Clamp`, `Sign`, `Sin`, `Cos`, `Tan`, `PI`, `E`) directly to Python's `math` module with automatic `import math` injection.
- **Collection & String Additions**:
  - `String`: `Substring`, `IndexOf`, `LastIndexOf`, `ToString`, `IsNullOrEmpty`.
  - `List<T>`: `Insert`, `RemoveAt`, `IndexOf`, `Sort`, `Reverse`, `Contains`.
  - `Dict<K, V>`: `ContainsValue`, `Remove`.
  - `HashSet<T>`: Complete set algebra (`UnionWith`, `IntersectWith`, `ExceptWith`, `SymmetricExceptWith`, `IsSubsetOf`, `IsSupersetOf`, `Overlaps`, `SetEquals`).
- **Explicit LINQ Fusion Guard (D-017)**: Only methods carrying explicit `[LinqStage]` metadata participate in comprehension fusion. This prevents name-colliding methods (like `Math.Max` or `Math.Min`) from being erroneously lowered as LINQ terminals.

### P2.3: LINQ Surface Expansion (Decision D-018)
- **Expanded Operator Surface**: Added `OrderBy`, `OrderByDescending`, `ThenBy`, `ThenByDescending`, `Distinct`, `Take`, `Skip`, `Concat`, `Contains`, `LastOrDefault`, `Average`, `Min`, and `Max`.
- **Lazy Fallback Pipeline**: Non-fusable LINQ chains lower into standard Python iterators (`filter`, `map`, `itertools.islice`, `itertools.chain`, `dict.fromkeys`).
- **Stable Multi-Key Ordering**: Multi-stage sorting (`OrderBy(...).ThenBy(...)`) is lowered by applying stable sorts in reverse key order, preserving multi-column sorting semantics.
- **Automatic Imports**: The code generator automatically imports `itertools` and `statistics` whenever iterator fallbacks or statistical aggregators are referenced.
- **Deferred Operators**: `SingleOrDefault` remains intentionally deferred until a faithful single-element check can be emitted without introducing runtime wrapper code.

### P2.4: Semantic Hardening (Decisions D-019 & D-020)
- **Static Property Lowering**: Static auto-properties lower to class attributes (using `typing.ClassVar` inside dataclasses to avoid constructor parameter generation). Static getter-only computed properties lower to `@classmethod` and member reads rewrite to method invocations, avoiding Python 3.13 `classmethod`/`property` deprecation and runtime incompatibilities.
- **Static Member Qualification**: Bare static member reads, writes, and calls are automatically qualified with their declaring class name.
- **Record & Struct Restrictions**: Primary constructors in records and structs enforce immutable or mutable dataclass constraints. Explicit instance fields, auto-properties, and static setters in records/structs are rejected at compile time with actionable diagnostics.
- **Operator Overload Resolution**: Operator overloads are explicitly deferred to Phase 4 (D-020).

### P2.5: Compatibility and Performance
- **Golden Output Corpus**: End-to-end regression harness at `tests/fixtures/golden/` with `tests/test_golden_output.py` supporting `--update-golden` snapshot updates and runtime execution checks.
- **Cross-Python Verification**: Verified across CPython 3.11, 3.12, and 3.13 on Linux.
- **Compiler Benchmarking Harness**: Added `benchmarks/benchmark_compiler.py` and `benchmarks/README.md`. Tested on a 27,000 LOC synthetic project (1,000 classes × 21 methods). Local 4-core host completes compilation in ~20–22s (comfortably within the 30s regression floor budget).

### P2.6: API & Diagnostics Polish
- **Core Library Guide**: Created [CORE-API.md](CORE-API.md) detailing every supported class, method, lowering target, and semantic deviation vs .NET.
- **Actionable Diagnostic Hints**: Extended `Diagnostic` with optional `hint` fields and equipped `DiagnosticEngine` with contextual fix recommendations for `PS000` through `PS004`.
- **Documentation Modernization**: Aligned [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [ROADMAP.md](ROADMAP.md), and [PROGRESS.md](PROGRESS.md).

---

## 3. Metrics & Quality Gates

| Metric | Phase 1 Baseline | Phase 2 Current | Status |
|---|---|---|---|
| **Test Files** | 18 | 24 | +6 test suites |
| **Total Automated Tests** | 78 | 103 | 100% passing |
| **Compiler Line Coverage** | 94.9% | > 95% | Exceeds $\ge 90\%$ gate |
| **Static Type Checking** | Pyright strict clean | Pyright strict clean | 0 errors on generated code |
| **Code Formatting & Linting** | Ruff clean | Ruff clean | 0 errors across codebase |
| **Runtime Dependencies** | 0 | 0 | Pure Python standard library |
| **CPython Compatibility** | 3.11 – 3.13 | 3.11 – 3.13 | Fully verified on Linux |

---

## 4. Behavioral Differences from C# / .NET

To ensure transparency and predictable runtime behavior, the following differences between PythonSharp and .NET Core are documented in [CORE-API.md](CORE-API.md):

1. **`List<T>.Remove(item)`**: Transpiles to `list.remove(item)`. Raises `ValueError` if the item is absent, unlike .NET which returns `false`. Guard with `Contains` when absent items are expected.
2. **`Dict<K, V>.Add(key, value)`**: Transpiles to `dict[key] = value`. Overwrites existing keys rather than throwing `ArgumentException`.
3. **`Dict<K, V>.Remove(key)`**: Transpiles to `dict.pop(key)`. Raises `KeyError` if key is absent. Guard with `ContainsKey` when necessary.
4. **`HashSet<T>.Remove(item)`**: Transpiles to `set.discard(item)`. Safe no-op if item is missing.
5. **`struct` Reference Semantics**: In PythonSharp, `struct` and `record struct` types are lowered as Python classes/dataclasses. Assignments do not perform implicit deep copy-on-assignment.

---

## 5. What's Next: Phase 3 Preview (`ps-bindgen`)

With the Core library and language semantics hardened, the next major milestone is **Phase 3: Ecosystem Bindings**:
- **Automatic `.pyi` / Typeshed Ingestion**: Parse Python type stub files and typeshed definitions using Python's `ast` parser.
- **Declaration Emission (`.d.ps`)**: Automatically generate ambient `.d.ps` declaration files for third-party Python packages (`numpy`, `pandas`, `requests`, `fastapi`, `torch`).
- **`psc bindgen` CLI Tool**: Command to generate and update bindings with drift detection and deterministic manifests.

