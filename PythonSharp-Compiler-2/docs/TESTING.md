# PythonSharp Testing Strategy

**Status:** Phases 1–5 complete; 31 test files, 130 unit tests passing, 8 dogfooding ported package test runners; CI and publishing deferred (D-015)
**Last updated:** 2026-10-30
**Related docs:** [ARCHITECTURE.md](ARCHITECTURE.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [ROADMAP.md](ROADMAP.md), [PROGRESS.md](PROGRESS.md)

## 1. Objectives

Testing for `psc` must prove four things:

1. **The compiler accepts the intended language.** Valid programs parse, analyze,
   and emit.
2. **The compiler rejects invalid programs precisely.** Errors carry the right
   code, message, and source span.
3. **Emitted Python is real Python.** It compiles, type-checks, imports, runs, and
   debugs like hand-written code.
4. **Output is reproducible.** Identical inputs produce identical source artifacts.

Correct execution alone is insufficient. A test that runs but emits unreadable
Python, loses source locations, or hides a diagnostic is a failure.

## 2. Test layers

| Layer | Scope | Tools |
| --- | --- | --- |
| Unit | One module or pass in isolation | `pytest` |
| Golden | Full emitted source compared to approved files | `pytest` + fixtures |
| Integration | Multi-pass compile of a project | `pytest` |
| Runtime | Execute emitted `.py` / `.pyc` and assert behavior | `pytest` + `subprocess` |
| Exception semantics | Typed/untyped catches, guards, finally, rethrow, and exception mapping | `pytest` + runtime execution |
| Traceback | Assert runtime errors report `.ps` locations | `pytest` |
| Type contract | Generated Python passes static checking | `pyright --strict` |
| CLI | Commands, output, and exit codes | `pytest` + `subprocess` |
| Determinism | Repeated builds match byte for byte | `pytest` |
| Packaging | Wheel and sdist install in a clean environment | Local clean venv; retained CI job |
| Performance | Compile-time and runtime baselines | benchmark harness |
| Dogfooding | Ported real-world Python packages compiled and verified | Dedicated test runners in `Samples/Ported/` |

## 3. Milestone test matrix

### M0: Bootstrap

| Test | Assertion |
| --- | --- |
| Package import | `import psc` succeeds from an editable install |
| CLI smoke | `psc --help` exits `0` |
| Toolchain | `ruff`, format check, strict `mypy`, and `pytest` run locally; CI workflow retained |
| Fixture tree | Commerce sample files exist and are discovered |

### M1: Frontend

Primary file: `tests/test_lexer_parser.py`

| Test | Assertion |
| --- | --- |
| Token kinds | Integers, decimals, strings, interpolation, keywords, operators |
| Spans | Exact `file:line:col` for starts and ends |
| Lexer errors | Unterminated strings and invalid characters produce `PS000` |
| Precedence | Every operator level parses with the expected tree shape |
| Declarations | Namespaces, imports, classes, interfaces, enums, records, structs |
| Statements | `if`, `while`, `foreach`, `try`/`catch`, `switch`, `using` |
| Expressions | Null-coalescing, null-conditional, lambdas, slicing, casts |
| Recovery | One malformed statement does not consume the following declaration |
| Termination | Adversarial input cannot loop the parser |

### M2: Pass 1

Primary files: `tests/test_project.py`, `tests/test_symbol_collector.py`

| Test | Assertion |
| --- | --- |
| XML project | Property group and dependency parsing |
| TOML project | `[project]` and `[dependencies]` parsing |
| File discovery | Deterministic ordering of `.ps` and `.d.ps` files |
| Symbols | Types, members, namespaces, imports are registered |
| Duplicates | Duplicate type and member declarations report errors |
| Namespace aggregation | Types from different files share one namespace |
| Circular types | Mutual `Order` / `OrderCache` references resolve |
| Circular inheritance | Cycle is rejected with the path |
| Internal scope | Assembly identity comes from the project |
| Ambiguity | Two namespace spellings mapping to one module path are rejected |

### M3: Pass 2A

Primary file: `tests/test_access_and_slots.py`

| Test | Assertion |
| --- | --- |
| Slots | Only new slots are listed; inherited slots are excluded |
| Deduplication | Diamond inheritance does not duplicate slots |
| `__ps_types__` | Includes full nominal ancestry and interfaces |
| PS001 private | External read/write rejected; internal access allowed |
| PS001 protected | Derived access allowed; unrelated access rejected |
| PS001 internal | Same assembly allowed; cross-assembly rejected |
| PS001 readonly | Assignment outside constructor rejected |
| Property accessors | Getter and setter visibility checked independently |
| Disposal | `IDisposable` synthesizes `__enter__`/`__exit__` |
| Async disposal | `IAsyncDisposable` synthesizes async context methods |
| PS003 | Static initializer cycle reports the full path |
| PS004 | `dynamic` in `[NativeCompile]` reports the field/parameter/local |

### M4: Pass 2B

Primary file: `tests/test_overloads_and_linq.py`

| Test | Assertion |
| --- | --- |
| Primitive erasure | `List<T>`/`Dict<K,V>`/`HashSet<T>`/`String` leave no wrapper |
| Inline templates | `ContainsKey` emits `key in mapping` |
| Arity dispatch | One-argument and two-argument overloads route correctly |
| Type dispatch | `int`, `bool`, `float`, `str`, class, interface cases |
| Bool guard | `True` does not select the `int` overload first |
| Interface dispatch | `__ps_types__` membership selects interface overloads |
| PS002 | Erased generic collisions are rejected |
| LINQ Where+Select | Fused list comprehension, no lambda allocation |
| LINQ predicates | Multiple `Where` filters are conjoined |
| LINQ terminals | Set, dict, any, all, sum, first-or-default lower correctly |
| Alpha-renaming | Nested pipelines do not capture outer variables |
| Fallback | Non-fusable chains lower without semantic changes |
| LINQ stage guard | Only calls carrying `[LinqStage]` fuse; `Math.Max` stays a normal call |
| Type checker | Nullability, assignment, return, and generic constraints |
| Generated annotations | Every expression node carries a resolved Python type |

### P2.2: Core API

Primary file: `tests/test_core_api.py`

| Test | Assertion |
| --- | --- |
| `Math` mapping | `Math` lowers to the `math` module and imports it automatically |
| Math operations | Sqrt, Pow, Sign, Clamp, PI/E, rounding, floor/ceiling, min/max |
| String members | Substring overloads, IndexOf/LastIndexOf, ToString, IsNullOrEmpty |
| Collection members | List insert/remove-at/index/sort/reverse; Dict ContainsValue; HashSet set operations |
| Exception mappings | Additional I/O, format, null-reference, permission, and arithmetic names |
| Pyright strict | Generated Core API sample reports zero errors |

### P2.3: LINQ surface

Primary file: `tests/test_linq_surface.py`

| Test | Assertion |
| --- | --- |
| Operator surface | OrderBy/ThenBy, Distinct, Take/Skip, Concat, Contains, LastOrDefault, Average, Min/Max lower and execute |
| Lazy fallback | Mixed chains use `filter`, `map`, `itertools.islice`, `itertools.chain`, and `dict.fromkeys` without changing results |
| Materialisers | ToDict, ToHashSet, Count, Any, All, FirstOrDefault, Sum, Min, and Max fall back correctly |
| Ordering composition | ThenBy and ThenByDescending preserve primary ordering for ties |
| Negative slicing | Take/Skip clamp negative counts to zero |
| Imports | `itertools` and `statistics` are imported automatically |
| Pyright strict | Generated LINQ surface sample reports zero errors |

### P2.4: Semantic hardening

Primary file: `tests/test_property_semantics.py`

| Test | Assertion |
| --- | --- |
| Static auto-properties | Get/set and get-only static properties emit as class attributes and retain initializers |
| Static computed properties | Getter-only expression/body properties emit as classmethods and reads lower to calls on CPython 3.11-3.13 |
| Static member qualification | Bare static fields, properties, and method calls inside instance/static methods use the declaring type |
| Record static state | Static auto-properties in records use `ClassVar` and do not become constructor fields |
| Rejections | Static custom setters, setters on frozen records, and record/struct instance fields/auto-properties produce PS000 diagnostics |
| Generic erasure | Existing PS002 tests cover erased generic overload collisions; type-parameter erasure remains `object` at runtime |

### M5: Pass 3A

Primary file: `tests/test_py_ast_builder.py`

| Test | Assertion |
| --- | --- |
| Module planning | One module per namespace; deterministic path |
| Topological order | Base classes precede derived types |
| Imports | `from __future__`, typing, stdlib, cross-namespace imports |
| Class shape | Bases, slots, metadata, properties, methods |
| Constructors | `base(...)`, `this(...)`, slot initializers |
| Overload AST | `@overload` stubs plus runtime dispatcher |
| Interface AST | Protocol declaration and nominal checks |
| Record/struct | Dataclass decorators and primary constructor fields |
| Enum | `IntEnum` with explicit values and preserved member names |
| Null safety | Single-evaluation temporaries for `?.` and `??` |
| Slicing | Index, range, step, and multi-axis lowering |
| Statement lowering | `foreach`, `switch`, `try`, `using` |
| Span stamping | Every statement maps to the expected `.ps` line |
| Validation | `compile(tree, ...)` succeeds for every module |

### M6: Pass 3B and CLI

Primary files: `tests/test_bytecode_tracebacks.py`,
`tests/test_emitter.py`, `tests/test_cli.py`, `tests/test_determinism.py`

| Test | Assertion |
| --- | --- |
| Source emission | `.py` files exist at planned paths |
| Package markers | Intermediate `__init__.py` files exist |
| PEP 552 header | 16-byte header, timestamp mode, source size |
| `.pyc` locations | Standalone and `__pycache__` artifacts exist |
| Load code | `marshal.loads` returns a `CodeType` |
| `co_filename` | Every nested code object points to its `.ps` file |
| Traceback | Runtime exception reports `.ps` file and line |
| CLI check | Clean project exits `0`; errors exit `1` |
| CLI build | Emits artifacts and prints a summary |
| CLI dump-ast | Prints lowered source without writing |
| CLI run | Executes the requested entrypoint |
| No source files | Exits `1` with a clear message |
| Determinism | Two builds produce identical `.py` and manifest output |
| Clean install | Wheel installs with no runtime dependencies |

## 4. Fixtures

The canonical fixture is `tests/fixtures/commerce_sample/`:

```text
Commerce.psproj
Domain/
  IAuditable.ps
  Order.ps
Services/
  OrderCache.ps
```

It exercises:

- Two files contributing to one namespace (`IAuditable`, `Order`).
- A circular cross-file type reference (`Order` ↔ `OrderCache`).
- Interface conformance and `__ps_types__`.
- `IDisposable`.
- Primitive `Dict<int, Order>` with index assignment.
- Constructor overloads and method overloads.
- LINQ `Where` + `Select` + `ToList`.
- A `private set` property (`AuditTag`).

Additional fixtures:

| Fixture | Purpose |
| --- | --- |
| `tests/fixtures/minimal/` | One namespace, one class, smoke test |
| `tests/fixtures/overloads/` | Valid and ambiguous overload sets |
| `tests/fixtures/linq/` | Fusion and fallback cases |
| `tests/fixtures/errors/` | One file per diagnostic code |
| `tests/fixtures/golden/` | Approved emitted Python snapshots |

Fixtures are source files, not generated at test time. Expected outputs are
reviewed and committed.

## 5. Golden output tests

- Golden tests compare emitted `.py` after normalizing line endings.
- Headers are stable; the compiler version may be included only if the golden
  update process accounts for it.
- Golden files are reviewed for readability, not just correctness.
- Updating goldens requires an intentional `--update-golden` run and a diff review.
- Golden tests must cover classes, records, enums, interfaces, overloads, LINQ,
  null safety, and slicing.

## 6. Diagnostic tests

For each of `PS000`-`PS004`:

1. A minimal trigger asserts the code and severity.
2. A negative case compiles cleanly.
3. The span is asserted by file, line, and column.
4. The message is asserted by snapshot or key phrases.
5. The CLI exits `1` for the trigger.
6. Multiple diagnostics are sorted deterministically.

Diagnostic snapshots should not assert incidental whitespace in the CLI header.

## 7. Generated-code contract tests

After emission, the test harness must:

1. Parse every emitted `.py` with `ast.parse`.
2. Compile every emitted module with `compile()`.
3. Run Pyright strict on the sample corpus. Pyright errors fail the build unless
   they are explicitly allowlisted with a tracked issue.
4. Import the package in a subprocess with `PYTHONPATH` pointing at the output.
5. Execute the sample entrypoint and assert its output.

Pyright is a separate signal from `psc` diagnostics. A program may type-check in
`psc` but still produce poor Python annotations; the generated-code check catches
that.

## 8. Traceback and bytecode tests

- Compile a fixture whose method raises at a known `.ps` line.
- Execute the emitted code with `.pyc` enabled.
- Capture the traceback and assert:
  - the file path ends with the original `.ps` filename;
  - the line number matches the expected `.ps` line;
  - the function name is the emitted snake_case name.
- Repeat for a nested function, method, lambda/comprehension helper, and a
  cross-namespace call.
- Test with and without `.pyc` to ensure source execution also maps lines.
- Treat `.pyc` as an optimization artifact; never make passing tests depend on
  loading stale bytecode.

## 9. Determinism and reproducibility

Test that:

- File discovery order is stable.
- Symbol and import ordering is stable.
- Two builds in different working directories produce identical `.py` files and
  manifests (no absolute paths).
- `.pyc` timestamps are the only allowed nondeterminism; source artifacts remain
  byte-identical.
- Randomized dictionary iteration cannot affect output. Run the suite with
  `PYTHONHASHSEED` varied in CI.

## 10. CLI and packaging tests

| Test | Assertion |
| --- | --- |
| `psc check` | Reports success and exit `0` |
| `psc check` with errors | Reports diagnostics and exit `1` |
| `psc build` | Writes `.py` and `.pyc`; prints output path |
| `psc build --no-pyc` | Writes no `.pyc` |
| `psc dump-ast` | Prints lowered modules, writes nothing |
| `psc run --entry` | Executes the named entrypoint |
| Missing target | Clear error and exit `1` |
| Bad flags | `argparse` exit `2` |
| Wheel install | Fresh venv, no third-party runtime imports |
| `psc --version` | Prints compiler and language version |

## 11. CI pipeline

```text
lint ─┬─▶ mypy ─┬─▶ unit/integration ─┬─▶ generated-code validation
      │         │                     ├─▶ traceback tests
      │         │                     └─▶ CLI tests
      │         └─▶ determinism
      └─▶ format check

packaging ─▶ wheel build ─▶ clean-venv install ─▶ smoke test
```

Matrix:

- CPython 3.11, 3.12, 3.13.
- Linux, macOS, Windows.
- `PYTHONHASHSEED` variation on at least one job.
- Golden tests run on every platform; line endings are normalized.

The workflow is retained for future use, but GitHub Actions execution is deferred
by D-015. The equivalent local gates were run on Linux with CPython 3.11, 3.12,
and 3.13; macOS and Windows remain unverified until CI is enabled.

CI must fail on:

- Any test failure.
- Coverage below threshold.
- Ruff or format violations.
- Mypy strict errors.
- Pyright strict errors on the sample corpus.
- Determinism mismatches.

## 12. Coverage targets

| Scope | Target |
| --- | --- |
| `src/psc` line coverage | ≥ 90% |
| Diagnostic codes | 100% triggered and asserted |
| Frontend | ≥ 90% |
| Semantic passes | ≥ 90% |
| Emitter | ≥ 90% |
| CLI | ≥ 80% |

Current results: 95.1% total, 91.5% codegen, and 91.6% CLI. P2.4 adds static property, static-member qualification, dataclass member-shape, and cross-version regression coverage. P2.5 adds golden snapshot comparison and execution, interpolated-string member qualification, nullable-erasure PS002 coverage, and cross-version golden runs.

Coverage is a floor, not a goal. A 95% suite that misses traceback fidelity is
worse than a 90% suite that covers the contract.

## 13. Performance benchmarks

Phase 1 measures without enforcing a hard budget:

- Parse time for the fixture corpus.
- Full compile time for a generated 25k LOC project.
- Emitted source size and module count.
- Cold import time of emitted packages.
- Runtime overhead on primitive-heavy and LINQ-heavy microbenchmarks.

The M6 baseline is 7.55 seconds for 26,002 LOC (1,000 classes, 21 methods each)
and becomes the Phase 2 regression gate. Benchmarks run on a dedicated CI job or
nightly schedule, not on every pull request.

### 13.1 P2.5 golden output corpus

`tests/fixtures/golden/Golden/Showcase.ps` is compiled and compared against
`tests/fixtures/golden/expected/golden.py`. Update snapshots deliberately:

```bash
.venv/bin/pytest tests/test_golden_output.py --update-golden -q
.venv/bin/pytest tests/test_golden_output.py -q
```

The suite also imports the emitted golden module and executes representative
record, enum, LINQ, nullable, and overload paths. Golden output is validated with
Pyright strict and must stay identical on CPython 3.11-3.13 after line-ending
normalization.

### 13.2 P2.5 compiler benchmark harness

`benchmarks/benchmark_compiler.py` generates 1,000 classes x 21 methods (27,004
source lines), compiles them in memory, and reports best-of-N compile time,
emitted module count, emitted bytes/lines, and cold-import time. The local
best-of-1 measurement is 20.1 seconds and best-of-2 is 21.9 seconds on a 4-core
i5-7200U. The default budget is 30 seconds on that host. The M6 7.55-second
baseline and the NFR target of under 10 seconds remain hardware-sensitive
performance follow-ups.

### 13.3 Real-World Dogfooding: Ported Package Test Runners

The `Samples/Ported/` directory hosts 8 canonical Python packages ported to C# / PythonSharp syntax, compiled to zero-dependency Python with `psc`, and tested against rigorous test suites:

| Ported Package | Scope & Features Tested | Test Runner |
| :--- | :--- | :--- |
| `01_leftpad` | String padding (`PadLeft`, `PadRight`), parameter defaults, negative widths | `Samples/Ported/01_leftpad/run_leftpad.py` |
| `02_slugify` | Regex compilation, string case conversion, character filtering | `Samples/Ported/02_slugify/run_slugify.py` |
| `03_isprime` | Fast trial-division prime checking, loop early returns, range checking | `Samples/Ported/03_isprime/run_isprime.py` |
| `04_levenshtein` | Matrix dynamic programming, 2D string distance, substitutions/insertions | `Samples/Ported/04_levenshtein/run_levenshtein.py` |
| `05_semver` | SemVer 2.0 parser & comparator (`Major`, `Minor`, `Patch`, `Prerelease`), records | `Samples/Ported/05_semver/run_semver.py` |
| `06_micro_tqdm` | Terminal carriage return formatting (`\r`), time calculations, progress rate | `Samples/Ported/06_micro_tqdm/run_tqdm.py` |
| `07_micro_dotenv` | Line-by-line `.env` parsing, comments/whitespace stripping, quote unescaping | `Samples/Ported/07_micro_dotenv/run_dotenv.py` |
| `08_micro_requests`| Sockets HTTP parser, URL splitting, status code/header/body decoding | `Samples/Ported/08_micro_requests/run_requests.py` |

Run any ported suite with:
```bash
.venv/bin/python Samples/Ported/01_leftpad/run_leftpad.py
```

## 14. Fuzzing and robustness

- Lexer and parser fuzzing with `hypothesis` is optional after M1.
- Every fuzz failure must produce a diagnostic or a controlled exception, never a
  hang or an unhandled crash.
- Project loader tests include path traversal attempts (`../` outside the root),
  malformed XML/TOML, and missing files.
- The compiler must not import or execute project code. A test asserts that a
  fixture with a side-effecting module is never imported during compilation.

## 15. Test data rules

- Fixtures are small, focused, and named for the behavior they prove.
- No secrets, credentials, or machine-specific paths in fixtures.
- Golden files are committed, readable, and reviewed.
- Generated test output goes to `tmp_path`, never into the source tree.
- Tests must not depend on network access.

## 16. Local commands

```bash
pip install -e ".[dev]"

ruff check .
ruff format --check .
mypy src/psc
pytest
pytest --cov=psc --cov-report=term-missing
pytest tests/test_bytecode_tracebacks.py -q
```

Run the full suite before opening a pull request. Run the packaging smoke test when
touching `pyproject.toml`, the CLI, or the emitter.
