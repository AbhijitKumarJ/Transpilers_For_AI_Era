# PythonSharp (`psc`)

PythonSharp is a statically typed, C#-style language that compiles to readable
Python 3.11+ source and line-pinned bytecode. It targets compile-time discipline
with runtime Python isomorphism: `.ps` sources use explicit types, namespaces,
classes, interfaces, records, and LINQ-style pipelines, while the generated Python
remains ordinary, debuggable Python.

> Status: Phase 1 (M0-M6), Phase 2 (P2.1-P2.6), Phase 3 (P3.1-P3.4), Phase 4
> (P4.1-P4.4), Phase 5 (P5.1-P5.4), Triple-Surface Architecture (Milestones U1-U5),
> and Next-Gen AI Inference (Tiers 8-12) are complete locally on CPython 3.11-3.13.
> Triple-Surface delivers a tri-modal ladder (Surface 1 Raw ABI, Surface 2 Idiomatic Bridge,
> Surface 3 Enterprise Architecture) with Zero Runtime Wrapper Tax, modular standard library
> packages (`stdlib/01_python_stdlib/`, `stdlib/02_scientific_and_ai/`), multi-surface stub
> generation (`psc bindgen --triple-surface`), LSP hover ladder cards, surface migration
> diagnostics (`PS005`), matrix `@` operator lowering, and multi-axis range slicing.
> Modern language enhancements include String-Backed Enums (`enum Status : string` -> `enum.StrEnum`),
> Structural Duck-Typing Interface Conformance (`@runtime_checkable Protocol` with automatic
> nominal registration in `__ps_types__`), and Advanced Pattern Matching (relational `> 0`,
> list patterns `[var first, ..var rest]`, slice patterns, and var bindings).
> Real-world dogfooding is verified across 32 canonical Python libraries in `Samples/Ported/`
> (Tiers 1-12) plus 7 showcases (including `Samples/06_triple_surface_migration/`
> and `Samples/07_ai_ml_triple_surface/`) — 39 total operational projects.
> 152 tests pass across 37 test files with >95% line coverage; 6 LSP protocol tests pass.
> 54 comprehensive technical blog posts across 4 levels document the architecture,
> compiler internals, ported case studies, and next-gen AI inference pipelines.
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

## Building & Distribution

PythonSharp is distributed as a self-contained pure-Python wheel (`.whl`) and source distribution (`.tar.gz`). The wheel bundles all 95 standard library definition stubs (`00_core/`, `01_python_stdlib/`, `02_scientific_and_ai/`) under `psc.stdlib`, ensuring full offline compilation, zero wrapper tax, and instant lowering for native operators (`@`, `.T`):

### 1. Build Wheel and Sdist
```bash
# Build into dist/ using pyproject-build or python -m build
pyproject-build --outdir dist
# or: python -m build --outdir dist
```

### 2. Verify Wheel Bundled Stubs
```bash
python -c "
import zipfile, pathlib
whl = sorted(pathlib.Path('dist').glob('*.whl'))[-1]
with zipfile.ZipFile(whl) as z:
    stubs = [n for n in z.namelist() if n.endswith('.d.ps')]
    print(f'Wheel: {whl.name} | Bundled stubs: {len(stubs)} (Expected: 95)')
    assert len(stubs) == 95, f'Missing stubs! Found {len(stubs)}'
"
```

### 3. Install in a Clean Virtual Environment
```bash
# Create clean virtual environment
mkdir -p ~/my_pythonsharp_project && cd ~/my_pythonsharp_project
uv venv .venv && source .venv/bin/activate
# or: python -m venv .venv && source .venv/bin/activate

# Install from the wheel
uv pip install /path/to/PythonSharp/dist/pythonsharp_compiler-0.1.0-py3-none-any.whl

# Verify CLI
psc --version
```

## Visual Studio Code Extension

A pre-packaged VS Code extension (`editors/vscode/pythonsharp-0.1.0.vsix`) provides syntax highlighting, language configuration, and seamless LSP integration (`psc lsp`):

```bash
# Option A: Install the pre-packaged .vsix
code --install-extension /path/to/PythonSharp/editors/vscode/pythonsharp-0.1.0.vsix

# Option B: Link the extension directory for live development
mkdir -p ~/.vscode/extensions
ln -s /path/to/PythonSharp/editors/vscode ~/.vscode/extensions/pythonsharp
```

When opened in VS Code with your virtual environment selected, the extension provides:
- **Go To Definition (`F12`)**: Jumps into project files and ambient stubs inside `site-packages/psc/stdlib/`.
- **Hover**: Real-time type signatures and interactive Tri-Modal Surface Ladder cards.
- **IntelliSense**: Autocompletes C# keywords, project types, and standard library members.
- **Diagnostics**: Real-time compiler errors (`PS000`–`PS005`) with exact spans and actionable fix hints.

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
- [Level 3 Blog Series (10 Parts): Advanced Architecture & Systems Engineering](docs/blogs/3/PLAN.md)
- [Level 4 Blog Series (6 Parts): AI/ML & Next-Gen Scientific Inference](docs/blogs/4/PLAN.md)

## Repository layout

```text
src/psc/          Compiler package (frontend, semantics, codegen, CLI, LSP, bindgen)
tests/            Unit tests (152 tests, 37 files), golden fixtures, triple-surface tests, and samples
stdlib/           Modular standard library bundles (Core, 01_python_stdlib, 02_scientific_and_ai)
editors/          Editor extensions and integrations (VS Code LSP & syntax)
Samples/          7 interactive showcases and 32 real-world ported Python packages across 12 tiers
docs/             Maintained documentation, and 54 technical blog posts across 4 levels (blogs/1-4)
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