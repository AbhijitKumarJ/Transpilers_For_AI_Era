# PythonSharp Compiler Architecture

**Status:** Implemented across Phases 1–5
**Last updated:** 2026-10-30
**Related docs:** [TECH-STACK.md](TECH-STACK.md), [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [ROADMAP.md](ROADMAP.md), [PROGRESS.md](PROGRESS.md), [LSP.md](LSP.md)

## 1. Overview

`psc` is a multi-pass, source-to-source compiler. It parses `.ps` files into a
mutable AST, resolves symbols and types across the whole project, applies
semantic rewriting, builds Python `ast.Module` trees, and emits `.py` and `.pyc`
artifacts.

```text
.ps files + .psproj
        │
        ▼
┌───────────────────┐
│ Frontend          │  lexer → parser → AST + diagnostics          (M1)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Pass 1            │  symbols, namespaces, type resolution        (M2)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Pass 2A           │  slots, access, disposal, __ps_types__       (M3)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Pass 2B           │  primitive erasure, overloads, LINQ fusion   (M4)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Pass 2C           │  type checking and coercion                  (M4)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Pass 3A           │  ordering, lowering, Python AST, spans       (M5)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Pass 3B           │  .py emission, PEP 552 .pyc, manifest        (M6)
└───────────────────┘
```

The frontend and Passes 1-2C never execute project code. Pass 3B invokes
`compile()` on generated Python ASTs, which validates syntax but does not import
or run the project.

## 2. Compiler context

A single `CompilerContext`-style object owns per-build state:

| Field | Purpose |
| --- | --- |
| `options` | Target version, output directory, pyc toggle, strictness |
| `project` | Resolved `.psproj` model and source roots |
| `units` | Parsed compilation units |
| `symtab` | Global symbol table |
| `diagnostics` | Diagnostic engine |
| `artifacts` | Emitted module records and manifest entries |

All passes receive the context explicitly. Module-level mutable state is not
allowed, so parallel builds and tests remain isolated.

## 3. Frontend (M1)

### 3.1 Lexer

The lexer scans UTF-8 source and emits tokens carrying a `SourceSpan`:

```text
SourceSpan(file_id, ps_filename, start_line, start_col, end_line, end_col)
```

- Lines and columns are 1-indexed, matching the `file:line:col` diagnostic format.
- A `file_id` identifies the compilation unit within one build.
- Strings support escape sequences and interpolation segments.
- Comments and whitespace are skipped but retained where needed for formatting.
- Invalid characters and unterminated literals produce diagnostics and recover at
  the next line boundary.

### 3.2 AST

The AST is a tagged dataclass hierarchy in `src/psc/frontend/ast_nodes.py`. It is
deliberately **multi-pass**: a name or type reference may be unresolved when the
node is created.

Major node families:

- Compilation unit: namespace declaration, `using`, `extern using`, type declarations.
- Declarations: class, struct, interface, enum, primitive class, field, property,
  method, constructor, parameter.
- Statements: block, local variable, expression, `if`, `while`, `for`, `foreach`,
  `switch`, `try`/`catch`/`finally`, `return`, `break`, `continue`, `throw`.
- Expressions: literals, identifiers, member access, invocation, index, slicing,
  unary/binary/ternary, assignment, cast, `is`/`as`, null-coalescing, null-conditional,
  interpolation, lambda, LINQ chains.
- Lowering metadata: `emission_strategy`, `lowering_mode`, `comprehension_kind`,
  `runtime_type_checks`, `topological_order_rank`.

Every node retains its originating span. Rewrites never discard the original span.

### 3.3 Parser

- Recursive descent for declarations and statements.
- Pratt parsing for binary operators with explicit precedence and associativity.
- Semicolon-terminated C#-style statements.
- Error recovery:
  - skip to the next `;`, `}`, or declaration keyword;
  - emit one diagnostic per malformed construct where possible;
  - guarantee parser termination even on adversarial input.

The parser accepts only the declared language subset. Unsupported C# constructs
produce a clear diagnostic rather than a generic syntax error where feasible.

## 4. Pass 1: symbols, namespaces, and types (M2)

### 4.1 Project loading

`ProjectLoader` reads `.psproj` and compiler configuration, then:

1. Resolves source roots and all `.ps` files deterministically (sorted paths).
2. Parses each file into a compilation unit.
3. Validates the target Python version against the compiler.
4. Loads external module aliases and Core declarations (`PythonSharp.Core.d.ps`).

Project configuration errors use dedicated diagnostics and stop before code
generation. Loading never imports Python modules named by `extern using`.

### 4.2 Symbol collection

`SymbolCollector` performs a declaration-only walk:

- Registers namespaces, types, members, imports, and type parameters.
- Detects duplicate declarations in the same scope.
- Creates `TypeSymbol` records with qualified names, base types, implemented
  interfaces, namespace tuple, assembly identity, flags, and source spans.
- Records member symbols with C# accessibility and lowering metadata.

Symbols are stored in ordered dictionaries so iteration is deterministic.

### 4.3 Virtual namespace aggregation

PythonSharp namespaces are **logical**, not physical. Multiple `.ps` files in
different directories may contribute types to the same namespace. Pass 1
aggregates them into `symtab.namespaces`.

Namespace mapping:

```text
namespace Commerce.Domain;     →  commerce/domain.py
namespace Commerce.Services;   →  commerce/services.py
namespace ML.Pipelines;        →  ml/pipelines.py
```

Each segment is converted from PascalCase to snake_case. A namespace becomes one
emitted Python module; intermediate directories receive generated `__init__.py`
package markers.

Consequences:

- Emission order follows the namespace dependency graph, not file order.
- Types within a namespace are topologically sorted by inheritance.
- Cross-namespace references lower to `from <module> import <Name>` imports.
- A namespace name collision (two spellings mapping to the same path) is a
  compile-time error.

### 4.4 Cross-file type resolution

`TypeResolver` resolves type references after all symbols are known:

1. Look up the name in the local scope, enclosing types, namespace, imports, then
   global scope.
2. Resolve generic arguments recursively.
3. Detect inheritance cycles using a visiting set and a resolved cache.
4. Validate that base classes and implemented interfaces are types, not values.
5. Validate `extern using` aliases against loaded binding declarations.

Circular references are legal when they do not form an inheritance cycle; they are
resolved lazily and memoized. Inheritance cycles produce a diagnostic with the
cycle path.

## 5. Pass 2A: layout and access (M3)

### 5.1 Slot analysis

`SlotAnalyzer` computes the runtime layout of every emitted class:

- Collect instance fields and auto-property backing fields.
- Walk the inheritance chain from base to derived, deduplicating names.
- Reject illegal re-declarations and slot collisions with a structural diagnostic.
- Emit a single `__slots__` tuple per class containing only that class's new slots.
- Emit `__ps_types__`, a tuple of fully qualified nominal type names including all
  base classes and interfaces.
- Preserve deterministic ordering: base slots first, then declaration order.

Python-level multiple inheritance is limited to what the supported subset can
faithfully represent. Diamond layouts must not duplicate slots.

### 5.2 Access checking

`AccessChecker` enforces `public`, `private`, `protected`, and `internal` at compile
time and emits `PS001` on violation.

| Modifier | Allowed access |
| --- | --- |
| `public` | Any code |
| `private` | The declaring type only |
| `protected` | The declaring type and derived types |
| `internal` | The same assembly/project |
| `protected internal` | Same assembly or derived type |

Access is a compile-time contract. Python output does not add runtime guards or
name mangling, preserving readability and interoperability. Static and instance
contexts, nested types, and cross-assembly references are checked during Pass 2A.

### 5.3 Disposal synthesis

Types implementing `IDisposable` or `IAsyncDisposable` receive context-manager
support:

- `IDisposable` → `__enter__` returns `self`; `__exit__` calls `dispose()`.
- `IAsyncDisposable` → `__aenter__` returns `self`; `__aexit__` awaits
  `dispose_async()`.
- `using` statements and declarations lower to `with` / `async with`.
- Disposal is idempotent; exceptions propagate after cleanup.

### 5.4 Static initialization and native checks

Two additional Pass 2A invariants protect module import and native compilation:

- **`PS003` circular value initialization.** Pass 2A builds a dependency graph of
  static field and property initializers. Circular type references are legal, but
  a cycle between runtime initializers would fail at module import time. A DFS
  reports the full cycle path.
- **`PS004` invalid `[NativeCompile]` dynamic construct.** A type marked
  `[NativeCompile]` may not use `dynamic` in any field, property, parameter, or
  local variable. The check runs before erasure so the diagnostic points at the
  original declaration.
- **Readonly assignment.** Assignments to `readonly` fields outside the
  constructor or declaring type are rejected under `PS001`.

## 6. Pass 2B: erasure, overloads, and LINQ (M4)

### 6.1 Primitive resolver

`PrimitiveResolver` applies attribute-driven erasure:

| PythonSharp | Python target | Mechanism |
| --- | --- | --- |
| `String` | `str` | `[MapsTo("str")]` |
| `List<T>` | `list[T]` | `[MapsTo("list")]` / template |
| `Dict<K,V>` | `dict[K,V]` | `[MapsTo("dict")]` |
| `HashSet<T>` | `set[T]` | `[MapsTo("set")]` |
| `int`, `float`, `bool`, `str` | same | built-in mapping |
| `decimal` | `decimal.Decimal` | stdlib mapping |

`[InlineTemplate]` handles constructs that cannot be expressed as a simple type
mapping, such as formatted strings or chained null checks. Templates are validated
at compile time and never evaluated as Python code during compilation.

Erased types carry no runtime wrapper. Generated code must be indistinguishable
from what a Python developer would write for the same operation.

### 6.2 Overload resolver

`OverloadResolver` groups methods sharing a name into dispatch groups:

1. Order candidates by arity, then specificity.
2. Reject ambiguous groups at compile time (`PS002`).
3. Emit `@overload` stubs for static type checkers.
4. Emit a runtime dispatcher that inspects arguments with `isinstance`. The
   dispatcher signature is intentionally dynamic and carries `# type: ignore`
   because Pyright cannot prove it satisfies every overload stub.
5. Rank `bool` before `int` because `bool` is a subclass of `int`.
6. Treat `int` as acceptable for `float`/`double` parameters when no exact match
   exists.
7. Fall back to a deterministic `TypeError` listing accepted signatures.

Dispatch order is stable and derived from declaration order plus specificity, not
from dictionary iteration.

### 6.3 LINQ fusion

`LinqFuser` recognizes method chains rooted at a sequence:

```text
items.Where(x => x.Active).Select(x => x.Name).ToList()
```

It lowers to a Python expression such as:

```python
[x.name for x in items if x.active]
```

Rules:

- Lambda parameters are alpha-renamed to avoid capture in nested scopes.
- Evaluation order and short-circuit behavior must be preserved.
- `Where` → filter clause; `Select` → element expression; `ToList` → list
  comprehension; `ToDict` → dict comprehension; `ToHashSet` → set
  comprehension.
- `OrderBy`/`OrderByDescending`/`ThenBy`/`ThenByDescending` → stable `sorted`
  calls composed from the last key to the first.
- `SelectMany` → nested comprehension.
- `Any`/`All`/`Count`/`Sum`/`Min`/`Max`/`FirstOrDefault`/`LastOrDefault` lower
  to their Python equivalents when fusion is valid.
- Chains that cannot be fused lower to ordinary Python iterator calls such as
  `filter`, `map`, `itertools.chain`, `itertools.islice`, `dict.fromkeys`,
  `sorted`, and `statistics.fmean` rather than changing semantics.
- `Take`/`Skip` clamp negative counts to zero; ordering and materialisation are
  eager, while filtering, projection, concatenation, and slicing stay lazy where
  Python permits.

### 6.4 Type checker

`TypeChecker` validates the supported subset after erasure and overload resolution:

- Assignability, nullability, and numeric coercions.
- Member and invocation resolution.
- Interface conformance.
- `foreach` element types and LINQ lambda types.
- `IDisposable` usage in `using` statements.
- Unreachable or definitely-unassigned locals where practical.

Type checking is intentionally narrower than C#; unsupported constructs produce
explicit diagnostics. Generated Python is additionally checked by Pyright locally;
the retained CI workflow runs the same check when enabled.

## 7. Pass 3A: Python AST construction (M5)

### 7.1 Topological planning

`NamespacePackagePlanner` groups emittable types by namespace and sorts classes so
that base classes and interfaces precede derived types. Primitive and ambient stub
types are excluded from emission.

### 7.2 Lowering

`ExpressionLowerer` converts semantic AST nodes into Python AST nodes:

| PythonSharp construct | Python lowering |
| --- | --- |
| `?.` | conditional expression guarding `None` |
| `??` | `a if a is not None else b` (not `or`, to preserve falsy values) |
| `!` | erased |
| `is` / `as` | `isinstance` / conditional expression |
| String interpolation | f-string or `str.format`-equivalent AST |
| Slicing | Python `slice` nodes, including multidimensional lowering |
| `foreach` | `for item in iterable` |
| `switch` | `if`/`elif` chain or `match` when semantics match |
| `using` | `with` / `async with` |
| LINQ chain | comprehension or iterator fallback |
| Primitive members | direct Python operations |
| `throw` / `try` / `catch` | Native `raise`, `try`, `except`, and `finally`; guarded/multiple catches use an ordered dispatcher |

### 7.3 Overload emission

`OverloadAstEmitter` creates:

- `typing.overload` stub functions for static analyzers.
- A single runtime implementation that dispatches by argument type.
- Stable `TypeError` messages for unsupported arguments.

### 7.4 Python AST builder and span stamping

`PythonAstBuilder` assembles one `ast.Module` per planned namespace:

- Adds `from __future__ import annotations`.
- Adds typing, stdlib, and cross-namespace imports in deterministic order.
- Emits classes in topological order with `__slots__` and `__ps_types__`.
- Emits constructors, properties, methods, and overload routers.
- Lowers static auto-properties to class attributes (`ClassVar` in dataclasses)
  and static getter-only computed properties to classmethods whose reads become
  calls, avoiding the Python 3.13 `classmethod`/`property` incompatibility.
- Qualifies unqualified static member reads and calls with the declaring type.
- Rejects static custom setters and unsupported record/struct instance fields and
  auto-properties before code generation.
- Stamps `lineno`, `col_offset`, `end_lineno`, and `end_col_offset` from the
  original `.ps` spans on all supported nodes, skipping already-stamped subtrees
  so nested expressions are not re-walked.
- Validates each module with `compile(tree, filename, "exec")`.

Generated helper nodes (comprehensions, dispatch branches, synthesized
`__init__`) inherit the span of the construct that caused them, so runtime errors
land on a meaningful `.ps` line.

Exception lowering follows D-016: Core exception names map to Python builtins,
untyped `catch` uses `BaseException`, and guarded or multiple catches dispatch in
source order so a failed `when` guard continues to the next handler. User-defined
exception classes inherit the mapped Python base class.

Core `Math` calls reference the `math` module, so the builder emits `import math`
when that runtime name appears; lazy LINQ fallback similarly triggers automatic
`itertools` and `statistics` imports. Empty `List`/`Dict`/`HashSet` locals receive
concrete collection annotations for Pyright strict. LINQ fusion is gated on an
explicit `[LinqStage]` from overload resolution (D-017); method names alone do
not trigger fusion. Non-fusable chains use the iterator fallback recorded in
D-018, and ordering stages compose stable sorts so `ThenBy` preserves the primary
key for ties.

## 8. Pass 3B: emission (M6)

`ArtifactEmitter`:

1. Resolves the output root and creates package directories.
2. Compiles the stamped Python AST to a `CodeType` object **before** unparsing.
3. Recursively pins `co_filename` on nested code objects to the originating `.ps`
   file.
4. Emits readable `.py` using `ast.unparse` with a stable header.
5. Writes `.pyc` files:
   - standalone `<module>.pyc`;
   - `__pycache__/<stem>.<cache_tag>.pyc` for normal import caching.
6. Writes package `__init__.py` markers for intermediate directories.
7. Records each artifact (namespace, paths, source, code object, primary `.ps`
   file) in `psc-manifest.json`.

The manifest uses schema version 1, sorted module keys, relative artifact paths,
compiler/language versions, and no timestamps or absolute paths. It is emitted
alongside the package and participates in the byte-for-byte determinism check.

PEP 552 `.pyc` header layout (timestamp mode):

```text
4 bytes  magic number
4 bytes  flags (0)
4 bytes  source mtime
4 bytes  source size
N bytes  marshal.dumps(code_object)
```

Because `co_filename` points at the `.ps` file, CPython tracebacks display, for
example:

```text
File "Services/OrderCache.ps", line 24, in get_or_create
```

`co_filename` is pinned recursively for functions, methods, lambdas, and nested
comprehensions. The age of the `.pyc` header does not affect traceback fidelity.

## 9. Runtime contract

Emitted modules may rely on the following conventions:

| Contract | Shape | Purpose |
| --- | --- | --- |
| Slots | `__slots__: tuple[str, ...]` | Memory layout, prevention of accidental attributes |
| Nominal metadata | `__ps_types__: tuple[str, ...]` | Compiler and tooling type identity |
| Overloads | `@overload` stubs + runtime dispatcher | Static and dynamic dispatch |
| Disposal | `__enter__`/`__exit__`, `__aenter__`/`__aexit__` | `with` / `async with` |
| Primitive erasure | built-in Python types | Zero runtime wrappers |
| Null safety | `None` checks in generated expressions | Preserve C# null semantics |
| Source identity | `co_filename` = `.ps` path | Debuggable tracebacks |

The runtime contract is intentionally small. No PythonSharp runtime package is
imported by emitted code.

## 10. Module map

```text
src/psc/
├── __init__.py                 # Public compile API
├── cli.py                      # CLI entry point
├── diagnostics.py              # SourceSpan, Diagnostic, DiagnosticEngine
├── project.py                  # .psproj loader and build options
├── frontend/
│   ├── __init__.py             # Frontend exports
│   ├── tokens.py               # Token kinds and token records
│   ├── lexer.py                # Scanner
│   ├── ast_nodes.py            # Multi-pass AST
│   └── parser.py               # Recursive descent + Pratt parser
├── semantics/
│   ├── __init__.py             # analyze_compilation_units pipeline
│   ├── symbols.py              # Symbol table, type symbols, resolution
│   ├── collector.py            # Pass 1 collection
│   ├── slot_analyzer.py        # Pass 2A slots and metadata
│   ├── access_checker.py       # Pass 2A visibility (PS001)
│   ├── primitive_resolver.py   # Pass 2B erasure
│   ├── overload_resolver.py    # Pass 2B dispatch (PS002)
│   ├── linq_fuser.py           # Pass 2B LINQ fusion and fallback
│   └── type_checker.py         # Pass 2C type checking
└── codegen/
    ├── __init__.py             # Exported backend API
    ├── topo_sorter.py          # Namespace planning and class ordering
    ├── expr_lowerer.py         # Expression/statement lowering and span stamping
    ├── overload_emitter.py     # Overload stubs and runtime routers
    ├── py_ast_builder.py       # Python ast.Module construction
    └── emitter.py              # .py/.pyc emission and package markers
```

`psc/__init__.py` re-exports the stable compiler API (`compile_project`,
`ArtifactEmitter`, `DiagnosticEngine`) for embedders. Frontend modules live under
`psc.frontend`; semantic passes live under `psc.semantics`; backend modules live
under `psc.codegen`.

## 11. Invariants

1. **No project execution.** Compilation never imports or runs user code.
2. **Span preservation.** Every emitted statement maps to a `.ps` line.
3. **Deterministic ordering.** Files, symbols, imports, and emitted members use
   stable ordering.
4. **One namespace, one module.** A namespace emits exactly one Python module.
5. **No erased residue.** Primitive wrappers never appear in emitted code.
6. **Compile before unparse.** Bytecode is generated from the stamped AST.
7. **Single mutation pass.** Each semantic pass runs once per build; passes do not
   depend on repeated invocation for correctness.
8. **Diagnostics are non-fatal by default.** The engine accumulates errors and
   reports them together; code generation is skipped if errors exist.
9. **Readable output.** Generated Python must pass the golden readability review,
   not merely execute.

## 12. Error handling

- `DiagnosticEngine` collects diagnostics with code, severity, message, span, and
  optional hint.
- Diagnostics are sorted by file, line, column, then code for stable CLI output.
- Duplicate diagnostics for the same span and code are suppressed.
- Passes may recover and continue; fatal configuration errors stop the build.
- Code generation runs only when no error-severity diagnostics exist.
- CLI exit codes are defined in [DIAGNOSTICS.md](DIAGNOSTICS.md).

## 13. Extensibility

| Extension point | Mechanism | Used by |
| --- | --- | --- |
| Type mapping | `[MapsTo]`, `[InlineTemplate]` | Primitive resolver, bindgen |
| Runtime naming | `[RuntimeType]`, `[KwArgs]` | Bindgen, interop |
| Sequence operations | `[LinqStage]` | LINQ fuser |
| Python decorators | `[PythonDecorator]` | Phase 4 |
| Schema models | `[SchemaModel]` | Phase 4 |
| Native compilation | `[NativeCompile]` | Phase 5 |
| Backend target | `ArtifactEmitter` interface | Future backends |
| Analysis pass | Ordered pass registry | Future checks |

New attributes must define: parse shape, validation rules, lowering, diagnostics,
and tests before implementation.

## 14. Performance model

- Parsing and pass 1 are linear in token and symbol count.
- Type resolution is memoized; inheritance cycles are detected with a visiting set.
- Namespace planning and class ordering are linear in types plus edges.
- Emission is linear in emitted nodes.
- The compiler avoids re-parsing files across passes.
- Future work: parallel per-file parsing, parse caching, and incremental builds
  (Phase 5).

Phase 1 target: under 10 seconds for a 25k LOC project on a typical laptop. The
M6 baseline is 7.55 seconds for 26,002 LOC (1,000 classes, 21 methods each).

## 15. Security model

- Treat `.ps`, `.psproj`, and `.d.ps` inputs as untrusted data.
- Never `eval`, `exec`, or import project code during compilation.
- Never resolve `extern using` at compile time; it is a declaration only.
- Path traversal in project files is rejected; outputs must stay under the
  configured output root.
- Bindgen and native compilation (later phases) must validate external inputs and
  document any process execution.
- Generated code inherits the user's Python dependency trust model.
