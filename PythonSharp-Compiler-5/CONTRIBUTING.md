# Contributing to PythonSharp

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/LANGUAGE-SPEC.md](docs/LANGUAGE-SPEC.md), and
[docs/TESTING.md](docs/TESTING.md) before changing compiler behavior.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows, activate with `.venv\Scripts\activate`.

## Checks

Run all checks before opening a pull request:

```bash
ruff format --check .
ruff check .
mypy src/psc
pytest --cov=psc --cov-report=term-missing
```

## Building, Packaging & Verification

PythonSharp packages its standard library stubs (95 `.d.ps` files across `00_core/`, `01_python_stdlib/`, and `02_scientific_and_ai/`) directly inside `psc.stdlib` as package data via `MANIFEST.in` and `pyproject.toml`.

### 1. Build Distribution Packages
```bash
pyproject-build --outdir dist
# or: python -m build --outdir dist
```

### 2. Verify Wheel Bundled Stubs
Verify that all 95 definition stubs are packaged in the wheel:
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

### 3. Clean-Environment Smoke Test
Test the wheel in a fresh, isolated virtual environment to verify ambient resolution and lowering:
```bash
# In an isolated directory:
uv venv .venv && source .venv/bin/activate
uv pip install /path/to/dist/pythonsharp_compiler-0.1.0-py3-none-any.whl

# Build and verify NumPy sample (must emit native 'import numpy as _np', '@', and '.T')
psc build Samples/Ported/20_numpy_numerics/NumpyNumerics.psproj -o dist/
python Samples/Ported/20_numpy_numerics/run_numpy.py
```

### 4. VS Code Extension Packaging
To build the VS Code `.vsix` extension:
```bash
cd editors/vscode
npx @vscode/vsce package
# Emits editors/vscode/pythonsharp-0.1.0.vsix
```

## Change expectations

- Add or update tests for every behavior change.
- Keep diagnostics stable: preserve code, severity, and source spans.
- Update [docs/PROGRESS.md](docs/PROGRESS.md) when a milestone task or gate
  changes.
- Add a decision-log entry for architecture, diagnostic, phase-ordering, or
  release-criteria changes.
- Keep generated Python readable; generated artifacts must remain deterministic.
- Do not commit virtual environments, build output, secrets, or machine-specific
  paths.
