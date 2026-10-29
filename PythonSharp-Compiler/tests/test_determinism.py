from __future__ import annotations

from pathlib import Path

from psc import compile_sources

STDLIB = Path("stdlib/PythonSharp.Core.d.ps")


def _build(out_dir: Path) -> None:
    source = """
    namespace Deterministic.Sample;

    public record Row(int Id, string Name);

    public class Table
    {
        private readonly Dict<int, Row> _rows = new Dict<int, Row>();
        public void Add(Row row) => _rows[row.Id] = row;
        public List<int> Ids() => _rows.Values().Select(row => row.Id).ToList();
    }
    """
    artifacts, diagnostics = compile_sources(
        sources={"Deterministic/Table.ps": source},
        out_dir=out_dir,
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
        assembly_name="Deterministic",
        emit_pyc=True,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1


def test_two_builds_produce_identical_python_and_manifest_artifacts(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _build(first)
    _build(second)

    first_files = sorted(p.relative_to(first) for p in first.rglob("*") if p.is_file() and p.suffix == ".py")
    second_files = sorted(p.relative_to(second) for p in second.rglob("*") if p.is_file() and p.suffix == ".py")
    assert first_files == second_files
    for rel_path in first_files:
        assert (first / rel_path).read_bytes() == (second / rel_path).read_bytes()

    first_manifest = (first / "psc-manifest.json").read_bytes()
    second_manifest = (second / "psc-manifest.json").read_bytes()
    assert first_manifest == second_manifest
    manifest_text = first_manifest.decode("utf-8")
    assert str(tmp_path) not in manifest_text
