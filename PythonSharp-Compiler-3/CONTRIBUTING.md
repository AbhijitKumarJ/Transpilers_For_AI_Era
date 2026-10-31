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
