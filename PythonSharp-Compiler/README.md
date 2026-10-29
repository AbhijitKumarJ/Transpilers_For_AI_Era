# PythonSharp (`psc`)

PythonSharp is a statically typed, C#-style language that compiles to readable
Python 3.11+ source and line-pinned bytecode. It targets compile-time discipline
with runtime Python isomorphism: `.ps` sources use explicit types, namespaces,
classes, interfaces, records, and LINQ-style pipelines, while the generated Python
remains ordinary, debuggable Python.

> Status: Phase 1 (M0-M6), Phase 2 (P2.1-P2.6), Phase 3 (P3.1-P3.4), Phase 4
> (P4.1-P4.4), and Phase 5 (P5.1-P5.4) are complete locally on CPython 3.11-3.13.
> Phase 5 delivered tooling and native compilation: incremental SHA-256 build caching
> (`BuildCacheManager`), continuous watch mode (`psc watch`), pure-Python Language
> Server Protocol server (`psc lsp` over JSON-RPC 2.0 with diagnostics, hover, definition,
> and completion), and AOT C-extension compilation orchestration (`NativeCompiler` with
> `[NativeCompile]` and `--native`); 130 tests pass with >95% line coverage. Remote
> GitHub Actions and cross-platform CI pipelines are marked OUT OF SCOPE.

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
- `psc build <path> [-f] [--native]`: Incremental build with SHA-256 caching and optional native AOT C-extension compilation.
- `psc watch <path>`: Continuously watches files and rebuilds incrementally on changes.
- `psc lsp`: Headless Language Server Protocol (LSP) server for editor integration (diagnostics, hover, definition, completion).
- `psc bindgen <path> -o <stubs>`: Generates typed `.d.ps` ambient stubs from `.pyi` type definitions.
- `psc check <path>`: Verification and diagnostics without code emission.
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

## Documentation

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
- [12-Part blog series: Under the Hood](docs/blogs/PLAN.md)

## Repository layout

```text
src/psc/          Compiler package (frontend, semantics, codegen, CLI, LSP)
tests/            Unit tests, golden fixtures, and commerce sample
stdlib/           PythonSharp.Core ambient declarations (.d.ps)
editors/          Editor extensions and integrations (VS Code LSP & syntax)
Samples/          Interactive samples and 8 ported Python libraries
docs/             Maintained project documentation and 12-part blog series
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