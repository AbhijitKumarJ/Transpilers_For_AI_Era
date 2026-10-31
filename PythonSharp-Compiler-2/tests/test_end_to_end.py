from __future__ import annotations

import importlib
import sys
from decimal import Decimal
from pathlib import Path

from psc import compile_sources
from psc.project import load_project


def test_commerce_sample_builds_imports_and_runs_erased_code(tmp_path: Path) -> None:
    fixture_root = Path("tests/fixtures/commerce_sample")
    project = load_project(fixture_root / "Commerce.psproj", stdlib_dir=Path("stdlib"))
    sources = {
        path.relative_to(project.root_dir).as_posix(): path.read_text(encoding="utf-8") for path in project.source_files
    }
    stdlib_source = (Path("stdlib") / "PythonSharp.Core.d.ps").read_text(encoding="utf-8")
    out_dir = tmp_path / "dist"

    artifacts, diagnostics = compile_sources(
        sources=sources,
        out_dir=out_dir,
        stdlib_source=stdlib_source,
        assembly_name=project.project_name,
        emit_pyc=True,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert {artifact.module_rel_path for artifact in artifacts} == {
        "commerce/domain.py",
        "commerce/services.py",
    }

    sys.path.insert(0, str(out_dir))
    try:
        domain = importlib.import_module("commerce.domain")
        services = importlib.import_module("commerce.services")

        first = domain.Order(101, Decimal("80.00"), True)
        second = domain.Order(102, Decimal("25.00"), True)
        cache = services.OrderCache("AUDIT")

        assert cache.audit_tag == "AUDIT"
        assert "Commerce.Domain.IAuditable" in cache.__ps_types__
        assert not hasattr(cache, "__dict__")
        cache.put(first)
        cache.put(second)
        assert cache.get_active_ids() == [101, 102]
        assert cache.get_active_ids(Decimal("50.00")) == [101]

        with cache:
            assert cache.get_active_ids(Decimal("50.00")) == [101]
        assert cache.get_active_ids() == []

        with cache as entered:
            assert entered is cache
    finally:
        sys.path.remove(str(out_dir))
        for module_name in ("commerce.domain", "commerce.services", "commerce"):
            sys.modules.pop(module_name, None)


def test_linq_terminal_lowering_executes_all_comprehension_kinds(tmp_path: Path) -> None:
    source = """
    namespace Queries;

    using PythonSharp.Core;

    public class Repository
    {
        private readonly Dict<int, int> _items = new Dict<int, int>();

        public void Add(int key, int value) => _items.Add(key, value);
        public int CountAll() => _items.Values().Count();
        public bool AnyPositive() => _items.Values().Any(x => x > 0);
        public bool AllPositive() => _items.Values().All(x => x > 0);
        public int FirstPositive() => _items.Values().FirstOrDefault(x => x > 0);
        public int SumAll() => _items.Values().Sum();
        public List<int> Projected() => _items.Values().Select(x => x * 2).ToList();
        public HashSet<int> Unique() => _items.Values().ToHashSet();
        public Dict<int, int> Map() => _items.Values().ToDict(x => x, x => x * 2);
    }
    """
    stdlib_source = (Path("stdlib") / "PythonSharp.Core.d.ps").read_text(encoding="utf-8")
    artifacts, diagnostics = compile_sources(
        sources={"Queries/Repository.ps": source},
        out_dir=tmp_path / "linq-terminals",
        stdlib_source=stdlib_source,
        assembly_name="Queries",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()

    namespace: dict[str, object] = {}
    exec(artifacts[0].code_object, namespace)
    repository_cls = namespace["Repository"]
    repo = repository_cls()  # type: ignore[operator]
    repo.add(1, 10)  # type: ignore[attr-defined]
    repo.add(2, 20)  # type: ignore[attr-defined]

    assert repo.count_all() == 2  # type: ignore[attr-defined]
    assert repo.any_positive() is True  # type: ignore[attr-defined]
    assert repo.all_positive() is True  # type: ignore[attr-defined]
    assert repo.first_positive() in (10, 20)  # type: ignore[attr-defined]
    assert repo.sum_all() == 30  # type: ignore[attr-defined]
    assert sorted(repo.projected()) == [20, 40]  # type: ignore[attr-defined]
    assert repo.unique() == {10, 20}  # type: ignore[attr-defined]
    assert repo.map() == {10: 20, 20: 40}  # type: ignore[attr-defined]
