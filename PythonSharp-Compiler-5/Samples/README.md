# PythonSharp (`psc`) Sample Projects

This directory contains standalone scripts and mini-projects demonstrating **mixed-language PythonSharp (.ps) and Python (.py) architectures**.

Each sample is contained in a numerically prefixed directory showcasing a distinct capability of PythonSharp.

---

## Sample Directory Index

| Directory | Name | Highlights & Capabilities |
| :--- | :--- | :--- |
| [`01_hello_world/`](01_hello_world/) | **Hello World & CLI Execution** | Static methods, entrypoint (`Main`), string interpolation, running directly via `psc run`, and importing into Python. |
| [`02_linq_pipeline/`](02_linq_pipeline/) | **Fused LINQ & Records** | Multi-file `.psproj` build, C# `record` types, strongly typed `List<T>`, and fused LINQ queries (`.Where()`, `.OrderByDescending()`, `.Take()`, `.Sum()`) executed over Python data. |
| [`03_pydantic_schemas/`](03_pydantic_schemas/) | **Pydantic v2 Schema Models** | `[SchemaModel]` lowering to Pydantic v2 `BaseModel`, field validation, JSON dumping/loading, and API data contracts without synthetic wrappers. |
| [`04_bindgen_interop/`](04_bindgen_interop/) | **Native Python Interop (`ps-bindgen`)** | Generating ambient `.d.ps` stubs from `.pyi`, using `extern using`, and calling native Python modules at full speed with static C# type safety. |
| [`05_async_streams/`](05_async_streams/) | **Async Streams & Generators** | `IAsyncEnumerable<T>`, `yield return`, async generators, and real-time streaming with Python `asyncio` (`async for`). |
| [`06_triple_surface_migration/`](06_triple_surface_migration/) | **Triple-Surface Architecture Migration** | Demonstrates progressive migration across Surface 1 (C# Enterprise), Surface 2 (Canonical Bridge), and Surface 3 (Pythonic Direct), using intrinsic `[SurfaceLevel]`, `[CanonicalApi]`, `@` tensor operations, and `psc check --target-surface`. |
| [`Ported/`](Ported/) | **Ported Python Libraries (Dogfooding)** | 18 canonical Python packages across 8 tiers ported to C#/PythonSharp syntax and validated with test suites. |

---

## Ported Libraries (Real-World Dogfooding)

The [`Samples/Ported/`](Ported/) folder contains complete, production-grade ports of canonical Python packages, organized across 8 tiers of complexity from easiest to advanced. See [`Samples/Ported/PLAN.md`](Ported/PLAN.md) for the architectural roadmap:

### Completed Ports (Tiers 1–7 & Tier 9)

All 18 targets from the roadmap are implemented, compiled with `psc build`, and verified with 100% test pass rates:

| Ported Package | Original Python Equivalent | Focus & Tested Concepts | Test Command |
| :--- | :--- | :--- | :--- |
| [`01_leftpad`](Ported/01_leftpad/) | `left-pad` / `pad-left` | String padding, length calculation, default parameters | `python3 Ported/01_leftpad/run_leftpad.py` |
| [`02_slugify`](Ported/02_slugify/) | `python-slugify` | URL slugs, regex patterns, case normalization | `python3 Ported/02_slugify/run_slugify.py` |
| [`03_isprime`](Ported/03_isprime/) | `is-prime` | $6k \pm 1$ trial division, prime factoring, sieves | `python3 Ported/03_isprime/run_isprime.py` |
| [`04_levenshtein`](Ported/04_levenshtein/) | `Levenshtein` | 2D dynamic programming matrix, edit distance | `python3 Ported/04_levenshtein/run_levenshtein.py` |
| [`05_semver`](Ported/05_semver/) | `semver` | SemVer 2.0.0 parsing, records, precedence comparison | `python3 Ported/05_semver/run_semver.py` |
| [`06_micro_tqdm`](Ported/06_micro_tqdm/) | `tqdm` | Terminal `\r` formatting, progress calculation, timing | `python3 Ported/06_micro_tqdm/run_tqdm.py` |
| [`07_micro_dotenv`](Ported/07_micro_dotenv/) | `python-dotenv` | File I/O, quote unescaping, environment key-values | `python3 Ported/07_micro_dotenv/run_dotenv.py` |
| [`08_micro_requests`](Ported/08_micro_requests/) | `requests` | Sockets HTTP GET/POST, headers, status codes, JSON | `python3 Ported/08_micro_requests/run_requests.py` |
| [`09_micro_toml`](Ported/09_micro_toml/) | `pytoml` / `toml` | Scanner state machine, nested tables, arrays of tables, serialization | `python3 Ported/09_micro_toml/run_toml.py` |
| [`10_micro_bitarray`](Ported/10_micro_bitarray/) | `bitarray` | Low-level bitwise operations (`&`, `\|`, `^`, `~`, `<<`, `>>`), hex/binary formats | `python3 Ported/10_micro_bitarray/run_bitarray.py` |
| [`11_micro_croniter`](Ported/11_micro_croniter/) | `croniter` | 5-field cron parsing, calendar modulo math, leap-year rollover | `python3 Ported/11_micro_croniter/run_croniter.py` |
| [`12_json_logger`](Ported/12_json_logger/) | `python-json-logger` | Structured JSON log formatter, field mapping, tracebacks | `python3 Ported/12_json_logger/run_logger.py` |
| [`13_micro_fn`](Ported/13_micro_fn/) | `fn.py` | Currying (`curry_2`/`curry_3`), partials, pipelines, composition | `python3 Ported/13_micro_fn/run_fn.py` |
| [`14_micro_pluggy`](Ported/14_micro_pluggy/) | `pluggy` | Hook specifications, plugin manager, multi-result accumulation, firstresult | `python3 Ported/14_micro_pluggy/run_pluggy.py` |
| [`15_multimethod`](Ported/15_multimethod/) | `multimethod` | Multiple dispatch, subtype specificity, argument resolution, error handling | `python3 Ported/15_multimethod/run_multimethod.py` |
| [`16_micro_retry`](Ported/16_micro_retry/) | `retry` | Exponential backoff, exception filtering, re-throw semantics, decorator | `python3 Ported/16_micro_retry/run_retry.py` |
| [`17_micro_eventloop`](Ported/17_micro_eventloop/) | `micro-asyncio` | Cooperative `Task` model, ready & sleep deadline queues, interleaved scheduling | `python3 Ported/17_micro_eventloop/run_eventloop.py` |
| [`20_numpy_numerics`](Ported/20_numpy_numerics/) | `numpy` | Multidimensional tensors, matrix multiplication (`@` / `.dot()`), axis slicing, vector math | `python3 Ported/20_numpy_numerics/run_numpy.py` |

To build any ported library:
```bash
psc build Samples/Ported/01_leftpad -o Samples/Ported/01_leftpad/dist
python3 Samples/Ported/01_leftpad/run_leftpad.py
```

---

## Prerequisites & Setup

Ensure Python 3.11+ is available and `psc` is installed in your active environment:

```bash
# If working directly from the source repository:
export PYTHONPATH=src
alias psc="python3 -m psc.cli"

# Or with an editable install:
pip install -e .
```

---

## How to Compile & Run Each Sample

### 1. Sample 01 — Hello World

```bash
cd Samples/01_hello_world

# Option A: Run directly through psc (auto-detects static Main)
psc run Program.ps

# Option B: Compile to dist/ and run from Python
psc build Program.ps -o dist
python3 main.py
```

### 2. Sample 02 — Fused LINQ Data Pipeline

```bash
cd Samples/02_linq_pipeline

# Compile multi-file project (.psproj)
psc build DataPipeline.psproj -o dist

# Run the Python processing script
python3 run_pipeline.py
```

### 3. Sample 03 — Pydantic v2 Schemas

```bash
cd Samples/03_pydantic_schemas

# Compile schema model declarations
psc build Schemas.ps -o dist

# Run the Python model validation & serialization script
python3 app.py
```

### 4. Sample 04 — Native Python Interop (`ps-bindgen`)

```bash
cd Samples/04_bindgen_interop

# Step 1: Generate .d.ps ambient stubs from .pyi
psc bindgen native_text.pyi -o stubs --root-namespace Extern

# Step 2: Compile the PythonSharp project using the ambient stubs
psc build . -o dist

# Step 3: Run the integrated Python script
python3 run_interop.py
```

### 5. Sample 05 — Async Streams (`IAsyncEnumerable<T>`)

```bash
cd Samples/05_async_streams

# Compile the async stream service
psc build StreamService.ps -o dist

# Run the asyncio event consumer script
python3 run_async.py
```

### 6. Sample 06 — Triple-Surface Architecture Migration

```bash
cd Samples/06_triple_surface_migration

# Validate against target surfaces (reports PS005 surface migration warnings if mismatched)
psc check . --target-surface=surface_1
psc check . --target-surface=surface_2
psc check . --target-surface=surface_3

# Compile targeting Surface 3 (Pythonic Direct) with zero runtime wrapper tax
psc build . -o dist --target-surface=surface_3

# Run the linear regression and tensor verification script
python3 run_triple_surface.py
```

---

## Architectural Principles of Mixed PythonSharp & Python

1. **Zero Runtime Wrapper Tax:**
   PythonSharp emits clean, idiomatic Python 3.11+ source code and bytecode line-pinned directly to the `.ps` lines. Emitted classes use Python `@property`, `@dataclass(slots=True)`, or Pydantic `BaseModel` directly without synthetic adapter wrappers.
2. **First-Class Interop:**
   Transpiled modules can be imported by standard Python code using `from <namespace_submodule> import <Class>`, and methods follow Python `snake_case` naming conventions.
3. **Dual Execution Models:**
   - **Standalone:** Execute standalone scripts directly via `psc run <file.ps>`.
   - **Library / Service:** Transpile into a `dist/` directory via `psc build` and import freely into existing FastAPI, Django, Flask, or PyTorch workflows.

