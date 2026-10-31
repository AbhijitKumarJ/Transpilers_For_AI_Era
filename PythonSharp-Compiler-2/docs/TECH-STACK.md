# PythonSharp Technology Stack

**Status:** Stable across Phases 1–5
**Last updated:** 2026-10-30
**Related docs:** [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), [ROADMAP.md](ROADMAP.md), [PROGRESS.md](PROGRESS.md)

## 1. Summary

PythonSharp is a **Python-hosted transpiler**. The compiler is written in modern
Python, uses only the standard library at runtime, and emits Python 3.11+ source
and PEP 552 bytecode. This keeps the toolchain approachable, makes the compiler
itself hackable by the target audience, and lets the project dogfood the Python
ecosystem it targets.

| Layer | Choice | Version floor |
| --- | --- | --- |
| Compiler host language | Python | 3.11 |
| Generated code target | CPython | 3.11 |
| Parsing | Hand-written lexer + recursive-descent/Pratt parser | n/a |
| Internal representation | Dataclass-based multi-pass AST | n/a |
| Code generation | Python `ast`, `compile`, PEP 552 | 3.11 |
| Project format | `.psproj` (XML and TOML) | n/a |
| CLI | `argparse` | 3.11 |
| Testing | `pytest`, `pytest-cov` | current |
| Linting/formatting | `ruff` | current |
| Compiler type checking | `mypy` strict | current |
| Generated-code validation | `pyright` strict | current |
| Packaging | `pyproject.toml` + `setuptools` | current |
| CI | GitHub Actions | n/a |

## 2. Guiding principles

1. **Standard library only at runtime.** A user installing `psc` must not pull in a
   third-party compiler framework or runtime shim.
2. **Boring, inspectable technology.** A hand-written parser and Python's own AST
   are easier to debug and extend than generated parser tables or a custom IR.
3. **No execution of project code during compilation.** Parsing and analysis must
   never import or run user modules.
4. **Deterministic output.** No wall-clock timestamps, random identifiers, or
   absolute paths in emitted source. `.pyc` headers use PEP 552 timestamp fields
   and are excluded from the source-determinism guarantee.
5. **Two runtimes, one contract.** Compiler host and generated code may differ in
   future, but Phase 1 pins both to CPython 3.11+ to reduce drift.
6. **Defer complexity with a clear seam.** Bindgen, LSP, and native compilation get
   explicit extension points rather than speculative abstractions.

## 3. Compiler host

### Python 3.11+

Rationale:

- `tomllib` is available for TOML project files without dependencies.
- `ast.unparse` and `compile` are stable for the target syntax.
- Exception groups and improved error messages benefit diagnostics.
- The target runtime floor is also 3.11, minimizing version-specific emission.
- The audience already has Python; no second toolchain is required to build.

Alternatives considered:

| Alternative | Why not now |
| --- | --- |
| Rust | Faster compiler, but slower iteration, higher contributor bar, and no need before profiling |
| Go | Fast and easy distribution, but duplicates data handling and lacks Python AST fidelity |
| TypeScript/Node | Excellent tooling, but creates a two-runtime developer experience |
| C#/.NET | Natural language affinity, but contradicts the "Python-native toolchain" positioning |

A Rust rewrite remains possible after Phase 5 if compiler performance becomes a
verified bottleneck. The pass boundaries in [ARCHITECTURE.md](ARCHITECTURE.md) are
designed to make that migration a reimplementation of passes, not a redesign.

## 4. Frontend

### Lexer

- Hand-written scanner with explicit state for strings, interpolation, comments,
  and preprocessor-free syntax.
- Emits tokens with `SourceSpan` (file, start line/column, end line/column).
- No regex-only tokenization; regex is used only for simple literal classes.

### Parser

- Recursive descent for declarations and statements.
- Pratt/precedence-climbing for expressions.
- Produces a multi-pass AST in which unresolved names and types are legal until
  semantic passes fill them in.
- Error recovery at declaration and statement boundaries so one syntax error does
  not cascade.

Alternatives considered:

| Alternative | Why not now |
| --- | --- |
| Lark | Fast to start, but generated trees and error positions are harder to control |
| ANTLR | Heavy runtime dependency and a separate grammar toolchain |
| Tree-sitter | Great for editors, not ideal as the compiler's primary parser |
| PEG parser generator | Grammar debugging and left-recursion handling add risk |

## 5. Semantic passes

All passes operate on the same mutated AST plus shared compiler context. No pass
emits Python text directly until the backend.

| Pass | Technology | Output |
| --- | --- | --- |
| Pass 1 | Symbol tables built with dataclasses and dictionaries | Global symbols, namespace tree, resolved type references |
| Pass 2A | Slot and access analyzers | `__slots__`, `__ps_types__`, disposability, access diagnostics |
| Pass 2B | Primitive/overload/LINQ resolvers | Erased types, dispatch groups, fused comprehensions |
| Pass 2C | Type checker | Type errors, coercions, null-safety results |
| Pass 3A | Python `ast` builders | `ast.Module` per emitted Python module, with source positions |
| Pass 3B | Emitter | `.py` files, PEP 552 `.pyc` files, artifact manifest |

Data structures use `@dataclass(slots=True)` where practical. The compiler avoids
global mutable state; a `CompilerContext` owns the symbol table, diagnostics, and
options for one build.

## 6. Backend

### Python `ast`

- Build `ast.Module` trees using Python 3.11-compatible nodes.
- Stamp `lineno`, `col_offset`, `end_lineno`, and `end_col_offset` from `.ps`
  spans on every statement and expression that supports them.
- Validate each module with `compile(tree, filename, "exec")` before writing.
- Emit source with `ast.unparse` followed by a deterministic formatting pass.

### Bytecode

- Serialize code objects with `marshal`.
- Write PEP 552 compliant `.pyc` headers (magic, flags, timestamp, source size)
  using the timestamp-invalidated mode implemented by the prototype.
- Write both standalone `<module>.pyc` and `__pycache__/<stem>.<cache_tag>.pyc`
  artifacts.
- Keep `.py` source emission as the primary artifact; `.pyc` is an optimization
  and execution convenience. Source-hash invalidation can be added later.
- Never rely on `.pyc` as the only output; version portability is not guaranteed.

### Source mapping

- Every emitted statement carries the `.ps` line of its originating construct.
- Traceback fixtures assert that runtime errors report `.ps` file names and lines.
- A future source map may add column-level mapping; Phase 1 guarantees line-level.

## 7. Project model and configuration

| Artifact | Format | Library |
| --- | --- | --- |
| `.psproj` project file | XML (default) or TOML | `xml.etree.ElementTree`, `tomllib` |
| Output manifest (`psc-manifest.json`) | Deterministic JSON | `json` |

The project loader resolves source roots, output directory, target Python version,
external module aliases, and dependency declarations. It validates paths and
reports configuration errors as diagnostics with a dedicated code range.

## 8. CLI

- `argparse` with Phase 1 subcommands: `check`, `build`, `dump-ast`, `run`.
- `build` supports `--out-dir` and `--no-pyc`; `run` supports `--entry`.
- `--version` prints compiler and language versions; metadata lives in `src/psc/__init__.py`.
- Human-readable diagnostics by default; `--json` is a later CI/editor feature.
- Exit codes: `0` success, `1` compilation errors, `2` usage/configuration errors.
- `--verbose` pass timings and emitted-artifact reporting are a later enhancement.
- No interactive prompts in CI mode.

Alternatives considered: Typer and Click were rejected for Phase 1 to preserve the
zero-runtime-dependency rule. If CLI ergonomics become a problem, a vendored
minimal wrapper is preferred over a dependency.

## 9. Quality toolchain

| Concern | Tool | Configuration |
| --- | --- | --- |
| Unit/integration tests | `pytest` | `pyproject.toml` |
| Coverage | `pytest-cov` | fail under 90% on `src/psc` |
| Lint | `ruff check` | default rules plus import sorting |
| Format | `ruff format` | line length 100 |
| Compiler types | `mypy --strict` | `src/psc` |
| Generated types | `pyright --strict` | emitted sample corpus |
| Packaging check | `python -m build`, `twine check` | CI release job |
| Security scan | `pip-audit` (dev), dependency review | CI |
| Dead code/imports | `ruff` rules | CI |

`hypothesis` is optional for lexer/parser fuzzing once the grammar stabilizes. It
is not a Phase 1 release gate.

## 10. Packaging and distribution

- `pyproject.toml` with `setuptools` build backend.
- Single distribution: `pythonsharp-compiler` (import package `psc`).
- Console script: `psc = psc.cli:main`.
- Wheel includes compiler, stdlib declarations, and templates.
- No compiled extensions in Phase 1.
- Semantic versioning for the compiler; a separate language version string is
  embedded in diagnostics and `psc --version`.
- Python classifiers cover 3.11, 3.12, and 3.13.

## 11. Generated code runtime contract

Emitted Python may use only:

- Python built-ins and standard library modules.
- The user's own Python dependencies declared by the project.
- Optional runtime helpers only when a feature requires them, emitted inline
  rather than imported from a PythonSharp runtime.

Forbidden in emitted code:

- Imports of `psc` or any PythonSharp-only runtime.
- Wrapper objects for primitives.
- Reflection-based type registries beyond `__ps_types__` metadata used for
  diagnostics and `isinstance` checks.
- Non-deterministic identifiers or timestamps.

## 12. Future technology decisions

| Phase | Need | Candidate technology | Decision trigger |
| --- | --- | --- | --- |
| 2 | Broader Core library | Python stdlib + generated helpers | Core API freeze |
| 3 | Python stub parsing | `ast` + `ast.parse` on `.pyi` files | First bindgen milestone |
| 3 | Typeshed ingestion | Vendored typeshed snapshot | Offline reproducibility requirement |
| 4 | Schema models | Pydantic v2 | User demand and runtime dependency policy exception |
| 4 | Async and generators | Native Python async/await lowering | Phase 1 stability |
| 5 | LSP | `pygls` | Editor integration milestone |
| 5 | Incremental builds | Content hashing + artifact cache | Build-time baseline |
| 5 | Native compilation | `mypyc` first, Cython as fallback | Benchmark showing a real win |
| Future | Compiler performance | Rust port of hot passes | Profiling proves Python is the bottleneck |

## 13. Alternatives considered at the project level

| Approach | Why it was rejected |
| --- | --- |
| Source-to-source regex transpiler | Cannot handle scopes, types, or diagnostics reliably |
| Runtime library with decorators only | No compile-time enforcement; ergonomics remain Pythonic but not C#-like |
| Full C# compiler frontend reuse (Roslyn) | Hosts .NET, creates semantic mismatch, and violates the Python-native toolchain goal |
| Compile to a custom bytecode VM | Abandons the Python ecosystem and debuggability |
| Emit C extensions directly in Phase 1 | High complexity; defer to Phase 5 with a proven backend |
| Generate Python via templates/string concatenation | Error-prone, hard to map positions, and hard to validate |

## 14. Supported version matrix

| Component | Supported |
| --- | --- |
| Compiler host | CPython 3.11, 3.12, 3.13 |
| Generated source | CPython 3.11+ |
| Generated `.pyc` | Exact host minor version; treated as a cache artifact |
| Operating systems | Linux, macOS, Windows |
| Architectures | x86_64 and arm64 |

Python 3.14 is evaluated when its `ast` and bytecode formats stabilize; it is not
a Phase 1 target.

## 15. Dependency policy

- **Runtime:** zero third-party dependencies.
- **Development:** `pytest`, `pytest-cov`, `ruff`, `mypy`, `pyright`, `build`,
  `twine`, and `pip-audit`.
- **Optional:** `hypothesis` for fuzzing, `uv` for fast local environments.
- New runtime dependencies require an ADR and a PRD exception.
- Dependencies are pinned in a lock file for CI; the published wheel has no
  runtime requirements.

## 16. Repository layout

```text
PythonSharp/
├── docs/                       # Maintained documentation
├── Ideation/                   # Raw design archive
├── src/
│   └── psc/
│       ├── __init__.py
│       ├── cli.py
│       ├── diagnostics.py
│       ├── project.py
│       ├── frontend/
│       │   ├── __init__.py
│       │   ├── tokens.py
│       │   ├── lexer.py
│       │   ├── ast_nodes.py
│       │   └── parser.py
│       ├── semantics/
│       │   ├── __init__.py
│       │   ├── symbols.py
│       │   ├── collector.py
│       │   ├── slot_analyzer.py
│       │   ├── access_checker.py
│       │   ├── primitive_resolver.py
│       │   ├── overload_resolver.py
│       │   ├── linq_fuser.py
│       │   └── type_checker.py
│       └── codegen/
│           ├── __init__.py
│           ├── topo_sorter.py
│           ├── expr_lowerer.py
│           ├── overload_emitter.py
│           ├── py_ast_builder.py
│           └── emitter.py
├── stdlib/
│   └── PythonSharp.Core.d.ps
├── tests/
│   ├── fixtures/
│   │   └── commerce_sample/
│   └── test_*.py
├── pyproject.toml
├── README.md
└── LICENSE
```

## 17. Standard development commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ruff check .
ruff format --check .
mypy src/psc
pytest
python -m build
```

Windows activation uses `.venv\Scripts\activate`. The retained CI workflow runs the
same commands when enabled; local verification currently uses the same tool versions.

## 18. Technology risks

| Risk | Mitigation |
| --- | --- |
| `ast` changes across CPython minors | Pin emitter behavior per version; run the CI matrix; validate with `compile()` |
| `ast.unparse` output drifts | Golden formatting tests and a deterministic post-format pass |
| PEP 552 header incompatibility | Source hash mode and explicit version checks; source output is authoritative |
| Python compiler speed | M6 baseline: 7.55s for 26,002 LOC; cache parse results later; keep Rust port option |
| Tooling sprawl (mypy + pyright) | Separate responsibilities: mypy for compiler, pyright for generated code |
| `tomllib` read-only limitation | Use XML as the writable project format; TOML is read-only support |
| Windows path and encoding issues | Explicit UTF-8 handling, path normalization, and CI on Windows |
