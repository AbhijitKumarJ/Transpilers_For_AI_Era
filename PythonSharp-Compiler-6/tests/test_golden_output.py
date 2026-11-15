from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from psc import compile_sources

FIXTURE_ROOT = Path("tests/fixtures/golden")
SOURCE_ROOT = FIXTURE_ROOT / "Golden"
EXPECTED_ROOT = FIXTURE_ROOT / "expected"
STDLIB = Path("stdlib/PythonSharp.Core.d.ps")


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n")


def test_golden_python_output_matches_committed_snapshots(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    sources = {
        path.relative_to(FIXTURE_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(SOURCE_ROOT.rglob("*.ps"))
    }
    artifacts, diagnostics = compile_sources(
        sources=sources,
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
        assembly_name="Golden",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert artifacts

    update = bool(request.config.getoption("--update-golden"))
    for artifact in artifacts:
        expected_path = EXPECTED_ROOT / artifact.module_rel_path
        actual = _normalize_newlines(artifact.py_source)
        if update:
            expected_path.parent.mkdir(parents=True, exist_ok=True)
            expected_path.write_text(actual, encoding="utf-8")
        assert expected_path.exists(), f"Missing golden snapshot: {expected_path}"
        expected = _normalize_newlines(expected_path.read_text(encoding="utf-8"))
        assert actual == expected, f"Golden mismatch for {artifact.module_rel_path}"


def test_golden_output_executes(tmp_path: Path) -> None:
    sources = {
        path.relative_to(FIXTURE_ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(SOURCE_ROOT.rglob("*.ps"))
    }
    artifacts, diagnostics = compile_sources(
        sources=sources,
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
        assembly_name="Golden",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1

    module_name = f"_ps_golden_{tmp_path.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, artifacts[0].py_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    item = module.Item(2, "two")
    catalog = module.Catalog()
    catalog.add(item)

    assert int(module.Status.Draft) == 1
    assert int(module.Status.Published) == 2
    assert item.describe() == "2:two"
    assert catalog.find(2) is item
    assert catalog.names(0, 1) == ["two"]
    assert catalog.describe(None) == "none"
    assert catalog.describe(item) == "2:two"
    assert catalog.sum(1, 2) == 3
    assert catalog.sum(1, 2, 3) == 6
