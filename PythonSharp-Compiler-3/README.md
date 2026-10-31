# PythonSharp (`psc`)

PythonSharp is a statically typed, C#-style language that compiles to readable
Python 3.11+ source and line-pinned bytecode. It targets compile-time discipline
with runtime Python isomorphism: `.ps` sources use explicit types, namespaces,
classes, interfaces, records, and LINQ-style pipelines, while the generated Python
remains ordinary, debuggable Python.

> Status: Phase 1 (M0-M6), Phase 2 (P2.1-P2.6), Phase 3 (P3.1-P3.4), Phase 4
> (P4.1-P4.4), Phase 5 (P5.1-P5.4), and Triple-Surface Architecture (Milestones U1-U5)
> are complete locally on CPython 3.11-3.13. Triple-Surface delivers a tri-modal ladder
> (Surface 1 Raw ABI, Surface 2 Idiomatic Bridge, Surface 3 Enterprise Architecture)
> with Zero Runtime Wrapper Tax, modular standard library packages (`stdlib/01_python_stdlib/`,
> `stdlib/02_scientific_and_ai/`), multi-surface stub generation (`psc bindgen --triple-surface`),
> LSP hover ladder cards, surface migration diagnostics (`PS005`), matrix `@` operator lowering,
> and multi-axis range slicing. Real-world dogfooding is verified across 18 canonical Python
> libraries in `Samples/Ported/` (Tiers 1-9) plus the showcases in `Samples/06_triple_surface_migration/`
> and `Samples/07_ai_ml_triple_surface/`. 145 tests pass across 35 test files with >95% line coverage.
> Remote CI is marked OUT OF SCOPE.

## Requirements

- Python 3.11 or newer
- `pip` or [`uv`](https://docs.astral.sh/uv/)

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

psc --version
psc check tests/fixtures/commerce_sample/Commerce.psproj
psc build tests/fixtures/commerce_sample/Commerce.psproj --out-dir build/commerce
pytest
```

On Windows, activate the environment with `.venv\Scripts\activate`.

`psc build` writes importable `.py` modules, PEP 552 `.pyc` files, package
markers, and a deterministic `psc-manifest.json`. To run a program with a static
`Main` method:

```bash
psc run path/to/Program.ps -e Program.Main
```

Omit `-e` to auto-detect a static `main()` method. Other commands include:
- `psc build <path> [-f] [--native] [--target-surface <1|2|3>]`: Incremental build with SHA-256 caching, optional native AOT C-extension compilation, and target surface verification.
- `psc watch <path>`: Continuously watches files and rebuilds incrementally on changes.
- `psc lsp`: Headless Language Server Protocol (LSP) server for editor integration (diagnostics, tri-modal surface ladder hover cards, definition, completion).
- `psc bindgen <path> -o <stubs> [--triple-surface]`: Generates typed `.d.ps` ambient stubs from `.pyi` type definitions with optional 4-file Triple-Surface bundles.
- `psc check <path> [--target-surface <1|2|3>]`: Verification and diagnostics without code emission; emits `PS005` surface migration warnings.
- `psc dump-ast <path>`: Prints lowered Python source code to stdout.

## Quality gates

```bash
ruff format --check .
ruff check .
mypy src/psc
pytest --cov=psc --cov-report=term-missing
```

The retained CI workflow mirrors these checks plus generated-code Pyright
validation and clean wheel installation. Remote CI is marked OUT OF SCOPE; all gates pass locally.

## Documentation & Blog Series

- [Documentation index](docs/README.md)
- [Product requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Language specification](docs/LANGUAGE-SPEC.md)
- [Core API reference](docs/CORE-API.md)
- [LSP guide](docs/LSP.md)
- [Testing strategy](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Progress tracker](docs/PROGRESS.md)
- [Phase 2 release notes](docs/RELEASE-NOTES-PHASE-2.md)
- [Triple Surface Architecture](docs/Triple%20Surface/README.md)
- [Level 1 Blog Series (12 Parts): Architecture & Concepts](docs/blogs/PLAN.md)
- [Level 2 Blog Series (26 Parts): Deep Dive, Code Layout & 17 Ported Case Studies](docs/blogs/2/PLAN.md)

## Repository layout

```text
src/psc/          Compiler package (frontend, semantics, codegen, CLI, LSP, bindgen)
tests/            Unit tests, golden fixtures, triple-surface tests, and commerce sample
stdlib/           Modular standard library bundles (Core, 01_python_stdlib, 02_scientific_and_ai)
editors/          Editor extensions and integrations (VS Code LSP & syntax)
Samples/          Interactive samples, showcase (06_triple_surface_migration), and 18 ported Python libraries
docs/             Maintained documentation, 12-part Level 1 & 26-part Level 2 blog series
benchmarks/       Compiler performance and scale benchmark harness
Ideation/         Original design notes and reference drafts
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks, and change expectations.

---

# Background: Transpilers For AI Era

Transpilers For AI Era: When the bottleneck shifts from typing code to auditing and verifying it

Every major transpiler that succeeded (like TypeScript) did so because its creators looked at the failures of previous tools, identified the exact friction points, and engineered specific compiler designs to bypass them.

**Note: Ideas are just my brainstorming with llms, I don't mean to offend anyone here.**

## Original Question: 
The problem that i see with neural nets, quantum computing etc in language like python is, 
people take pride in putting 10 lines of logic in one, even though it creates a deep valley between those who are habituated and can't think beyond research and normal folks who want to learn and have worked on application layer understanding the benefit of clear verbose syntax over shorthands for scaling and maintenance, optimization in today's world should be left to transpilers rather than human. It also has great bearing on llm generated code, since llms can generate large codes with accuracy now so review requires more verbosity than shorthand tricks that can hide any number of quirks. 


The biggest unspoken friction points in modern tech: quantum computing and machine learning documentation are still written in "chalkboard compression format" rather than software engineering format. When physicists invented bra-ket notation, daggers, and Euler exponents nearly a century ago, they were writing by hand with chalk. Writing out an explicit 16-element state array took ten minutes on a blackboard, so they invented dense symbolic shorthands as human compression algorithms to save their wrists. The exact same culture carried over into Python neural network research, where academics translate compact LaTeX equations directly into clever one-line tensor broadcasts and single-letter variables, mistaking visual brevity for conceptual clarity. The point about transpilers and LLM code review is dead-on. In modern stacks—whether it is torch.compile and XLA in deep learning, or Qiskit's transpile() stage compiling logical gates down into OpenQASM and hardware microwave pulses—human-level shorthand buys zero runtime performance because the compiler lowers everything into an optimized intermediate representation anyway. Even more importantly, in an era where LLMs generate massive blocks of code in seconds, the engineering bottleneck has shifted from typing code to auditing and verifying it. A dense mathematical one-liner acts like a zip bomb during code review: an unintended tensor broadcast, a sign flip, or a relative phase bug can hide inside three characters, whereas verbose, explicit, step-by-step code forces every assumption and state transition out into the open where both humans and LLMs can verify it.  