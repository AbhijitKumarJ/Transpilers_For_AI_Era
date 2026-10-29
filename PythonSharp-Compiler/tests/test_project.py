from __future__ import annotations

from pathlib import Path

import pytest

from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.project import PsProjectConfig, load_project
from psc.semantics import GlobalSymbolTable, SymbolCollector


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_load_xml_project_reads_properties_dependencies_and_files(tmp_path: Path) -> None:
    project_file = _write(
        tmp_path / "Commerce.psproj",
        """
        <Project>
          <PropertyGroup>
            <AssemblyName>CommerceApp</AssemblyName>
            <OutputPath>build</OutputPath>
            <TargetPython>3.12</TargetPython>
            <EmitPyc>false</EmitPyc>
          </PropertyGroup>
          <ItemGroup>
            <PyPiPackage Include="requests" Version="2.32" />
            <PyPiPackage Include="rich" />
          </ItemGroup>
        </Project>
        """,
    )
    source_z = _write(tmp_path / "src" / "Z.ps", "namespace Z; class Z {}")
    source_a = _write(tmp_path / "src" / "A.ps", "namespace A; class A {}")
    project_stub = _write(tmp_path / "stubs" / "External.d.ps", "namespace External;")
    stdlib_dir = tmp_path.parent / f"{tmp_path.name}_stdlib"
    stdlib_stub = _write(stdlib_dir / "PythonSharp.Core.d.ps", "namespace PythonSharp.Core;")

    config = load_project(project_file, stdlib_dir=stdlib_dir)

    assert config.project_name == "CommerceApp"
    assert config.root_dir == tmp_path
    assert config.out_dir == tmp_path / "build"
    assert config.target_python == "3.12"
    assert config.emit_pyc is False
    assert config.pypi_dependencies == {"requests": "2.32", "rich": "*"}
    assert config.source_files == [source_a, source_z]
    assert config.stub_files == [stdlib_stub, project_stub]
    assert config.all_input_files() == [stdlib_stub, project_stub, source_a, source_z]


def test_load_toml_project_reads_project_and_dependency_sections(tmp_path: Path) -> None:
    project_file = _write(
        tmp_path / "Tool.psproj",
        """
        [project]
        name = "Tooling"
        out_dir = "artifacts"
        target_python = "3.13"
        emit_pyc = false

        [dependencies]
        rich = ">=13"
        """,
    )
    source = _write(tmp_path / "Domain" / "Thing.ps", "namespace Domain; class Thing {}")
    stub = _write(tmp_path / "Domain" / "Thing.d.ps", "namespace Domain;")

    config = load_project(project_file)

    assert config.project_name == "Tooling"
    assert config.out_dir == tmp_path / "artifacts"
    assert config.target_python == "3.13"
    assert config.emit_pyc is False
    assert config.pypi_dependencies == {"rich": ">=13"}
    assert config.source_files == [source]
    assert config.stub_files == [stub]


def test_load_project_defaults_and_deduplicates_stdlib_stubs(tmp_path: Path) -> None:
    project_file = _write(tmp_path / "Plain.psproj", "[project]\n")
    _write(tmp_path / "src" / "Source.ps", "namespace App;")
    stdlib_stub = _write(tmp_path / "stdlib" / "Core.d.ps", "namespace PythonSharp.Core;")

    config = load_project(project_file, stdlib_dir=tmp_path / "stdlib")

    assert config.project_name == "Plain"
    assert config.out_dir == tmp_path / "dist"
    assert config.target_python == "3.11"
    assert config.emit_pyc is True
    assert config.pypi_dependencies == {}
    assert config.stub_files == [stdlib_stub]
    assert config.all_input_files() == [stdlib_stub, tmp_path / "src" / "Source.ps"]


def test_load_project_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / "Missing.psproj")


def test_project_config_all_input_files_does_not_mutate_lists(tmp_path: Path) -> None:
    stub = tmp_path / "A.d.ps"
    source = tmp_path / "A.ps"
    config = PsProjectConfig(
        project_name="Config",
        root_dir=tmp_path,
        source_files=[source],
        stub_files=[stub],
    )

    assert config.all_input_files() == [stub, source]
    assert config.stub_files == [stub]
    assert config.source_files == [source]


def test_commerce_fixture_loads_and_collects_independent_of_file_order() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "commerce_sample"
    stdlib_dir = Path(__file__).parent.parent / "stdlib"
    config = load_project(fixture_root / "Commerce.psproj", stdlib_dir=stdlib_dir)

    assert config.project_name == "Commerce.Sample"
    assert config.out_dir == fixture_root / "dist"
    assert [path.name for path in config.source_files] == ["IAuditable.ps", "Order.ps", "OrderCache.ps"]
    assert [path.name for path in config.stub_files] == ["PythonSharp.Core.d.ps"]

    def collect(paths: list[Path]):
        diagnostics = DiagnosticEngine()
        units = [
            Parser.from_source(
                path.read_text(encoding="utf-8"),
                file_id=index,
                ps_filename=path.name,
                diagnostics=diagnostics,
            ).parse_compilation_unit()
            for index, path in enumerate(paths)
        ]
        symtab = GlobalSymbolTable(default_assembly_name=config.project_name)
        SymbolCollector(symtab=symtab, diagnostics=diagnostics).collect_all(units)
        return symtab, diagnostics, units

    all_paths = config.all_input_files()
    first_symtab, first_diagnostics, first_units = collect(all_paths)
    reversed_symtab, reversed_diagnostics, _ = collect(list(reversed(all_paths)))

    assert not first_diagnostics.has_errors(), first_diagnostics.format_all()
    assert not reversed_diagnostics.has_errors(), reversed_diagnostics.format_all()
    assert set(first_symtab.types_by_qname) == set(reversed_symtab.types_by_qname)

    order = first_symtab.types_by_qname["Commerce.Domain.Order"]
    cache = first_symtab.types_by_qname["Commerce.Services.OrderCache"]
    assert order.is_record is True
    assert cache.is_subclass_of("Commerce.Domain.IAuditable") is True
    assert cache.lookup_member("_store")[0].resolved_type is not None
    assert cache.lookup_member("Put")[0].param_types[0].qualified_name == "Commerce.Domain.Order"
    assert order.lookup_member("RegisterIn")[0].param_types[0].qualified_name == "Commerce.Services.OrderCache"

    module_paths = {Path(unit.ps_filename).name: unit.emitted_py_module_path for unit in first_units}
    assert module_paths["PythonSharp.Core.d.ps"] == "python_sharp/core.py"
    assert module_paths["IAuditable.ps"] == "commerce/domain.py"
    assert module_paths["Order.ps"] == "commerce/domain.py"
    assert module_paths["OrderCache.ps"] == "commerce/services.py"


def test_multi_extension_discovery_and_helpers(tmp_path: Path) -> None:
    from psc.project import (
        is_ps_project_file,
        is_ps_source_file,
        is_ps_stub_file,
    )

    # Extension recognition checks
    assert is_ps_source_file("App.ps") is True
    assert is_ps_source_file("App.pysharp") is True
    assert is_ps_source_file("App.pys") is True
    assert is_ps_source_file("App.d.ps") is False
    assert is_ps_source_file("App.d.pysharp") is False
    assert is_ps_source_file("App.d.pys") is False
    assert is_ps_source_file("App.cs") is False

    assert is_ps_stub_file("Core.d.ps") is True
    assert is_ps_stub_file("Core.d.pysharp") is True
    assert is_ps_stub_file("Core.d.pys") is True
    assert is_ps_stub_file("Core.ps") is False

    assert is_ps_project_file("App.psproj") is True
    assert is_ps_project_file("App.pysharpproj") is True
    assert is_ps_project_file("App.csproj") is False

    # Multi-extension project discovery
    proj = _write(tmp_path / "App.pysharpproj", "<Project><PropertyGroup><AssemblyName>App</AssemblyName></PropertyGroup></Project>")
    f1 = _write(tmp_path / "A.ps", "namespace App; class A {}")
    f2 = _write(tmp_path / "B.pysharp", "namespace App; class B {}")
    f3 = _write(tmp_path / "C.pys", "namespace App; class C {}")
    s1 = _write(tmp_path / "S1.d.ps", "namespace App;")
    s2 = _write(tmp_path / "S2.d.pysharp", "namespace App;")

    cfg = load_project(proj)
    assert cfg.project_name == "App"
    assert set(cfg.source_files) == {f1, f2, f3}
    assert set(cfg.stub_files) == {s1, s2}

