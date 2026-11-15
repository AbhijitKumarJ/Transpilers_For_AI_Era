from __future__ import annotations

import tempfile
from pathlib import Path

from psc.cli import main
from psc.project import find_stdlib_stubs, load_project


def test_lazy_stdlib_stub_loading(tmp_path: Path) -> None:
    stdlib_mock = tmp_path / "stdlib"
    stdlib_mock.mkdir()

    # Core (Layer 0)
    core_dir = stdlib_mock / "00_core"
    core_dir.mkdir()
    (core_dir / "00_primitives.d.ps").write_text("namespace PythonSharp.Core;", encoding="utf-8")

    # High-value (Layer 1)
    py_dir = stdlib_mock / "01_python_stdlib" / "os"
    py_dir.mkdir(parents=True)
    (py_dir / "os.d.ps").write_text("namespace PythonSharp.Os;", encoding="utf-8")

    # Long-tail Typeshed Replica (Layer 2)
    typeshed_dir = stdlib_mock / "03_typeshed_replica"
    urllib_dir = typeshed_dir / "urllib" / "request"
    urllib_dir.mkdir(parents=True)
    (urllib_dir / "request.d.ps").write_text("namespace Extern.Urllib.Request;", encoding="utf-8")

    sqlite_dir = typeshed_dir / "sqlite3"
    sqlite_dir.mkdir(parents=True)
    (sqlite_dir / "sqlite3.d.ps").write_text("namespace Extern.Sqlite3;", encoding="utf-8")

    # Case 1: Project with no references to Layer 2
    stubs_no_l2 = find_stdlib_stubs(stdlib_mock, referenced_namespaces={"System", "PythonSharp.Core", "PythonSharp.Os"})
    stub_names = [s.name for s in stubs_no_l2]
    assert "00_primitives.d.ps" in stub_names
    assert "os.d.ps" in stub_names
    assert "request.d.ps" not in stub_names
    assert "sqlite3.d.ps" not in stub_names

    # Case 2: Project with using urllib.request
    stubs_with_urllib = find_stdlib_stubs(stdlib_mock, referenced_namespaces={"Extern.Urllib.Request"})
    stub_names_urllib = [s.name for s in stubs_with_urllib]
    assert "00_primitives.d.ps" in stub_names_urllib
    assert "os.d.ps" in stub_names_urllib
    assert "request.d.ps" in stub_names_urllib
    assert "sqlite3.d.ps" not in stub_names_urllib


def test_project_auto_discovery_of_ps_stubs(tmp_path: Path) -> None:
    proj_dir = tmp_path / "MyProject"
    proj_dir.mkdir()
    (proj_dir / "MyProject.psproj").write_text(
        '<Project Sdk="PythonSharp.Sdk"><PropertyGroup><AssemblyName>MyProject</AssemblyName></PropertyGroup></Project>',
        encoding="utf-8",
    )
    (proj_dir / "Program.ps").write_text("namespace MyProject; public class Program {}", encoding="utf-8")

    # Put a 3rd party stub in .ps-stubs/matplotlib/
    ps_stubs_dir = proj_dir / ".ps-stubs" / "matplotlib"
    ps_stubs_dir.mkdir(parents=True)
    (ps_stubs_dir / "pyplot.d.ps").write_text("namespace Extern.Matplotlib.Pyplot;", encoding="utf-8")

    cfg = load_project(proj_dir / "MyProject.psproj")
    stub_names = [s.name for s in cfg.stub_files]
    assert "pyplot.d.ps" in stub_names


def test_cli_stubgen(tmp_path: Path, capsys) -> None:
    # Setup dummy typings directory
    typings_dir = tmp_path / "typings" / "demo_lib"
    typings_dir.mkdir(parents=True)
    (typings_dir / "__init__.pyi").write_text("def ping() -> str: ...\n", encoding="utf-8")

    # Run psc stubgen from this folder
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        out_stubs = tmp_path / ".ps-stubs" / "demo_lib"
        code = main(["stubgen", "demo_lib", "-o", str(out_stubs)])
        assert code == 0
        captured = capsys.readouterr()
        assert "Successfully generated" in captured.out
        assert (out_stubs / "demo_lib.d.ps").exists()
        content = (out_stubs / "demo_lib.d.ps").read_text(encoding="utf-8")
        assert "namespace Extern.DemoLib;" in content
        assert "public static extern string Ping();" in content
    finally:
        os.chdir(old_cwd)


def test_ps_conf_json_layer_and_surface_filtering(tmp_path: Path) -> None:
    stdlib_mock = tmp_path / "stdlib"
    stdlib_mock.mkdir()

    # Core
    core_dir = stdlib_mock / "00_core"
    core_dir.mkdir()
    (core_dir / "00_primitives.d.ps").write_text("namespace PythonSharp.Core;", encoding="utf-8")

    # High-value stdlib (Layer 1)
    py_dir = stdlib_mock / "01_python_stdlib" / "math"
    py_dir.mkdir(parents=True)
    (py_dir / "math.d.ps").write_text("namespace PythonSharp.Math;", encoding="utf-8")

    # Scientific handcrafted stdlib (Layer 1)
    sci_dir = stdlib_mock / "02_scientific_and_ai" / "matplotlib"
    sci_dir.mkdir(parents=True)
    (sci_dir / "matplotlib.d.ps").write_text("namespace PythonSharp.Matplotlib;", encoding="utf-8")

    proj_dir = tmp_path / "MyProject"
    proj_dir.mkdir()
    (proj_dir / "MyProject.psproj").write_text(
        '<Project Sdk="PythonSharp.Sdk"><PropertyGroup><AssemblyName>MyProject</AssemblyName></PropertyGroup></Project>',
        encoding="utf-8",
    )
    (proj_dir / "Program.ps").write_text("namespace MyProject;\nusing PythonSharp.Bridge.Matplotlib.Pyplot;\npublic class Program {}", encoding="utf-8")

    # Dedicated stub with triple-surface bundle in .ps-stubs/matplotlib
    m_dir = proj_dir / ".ps-stubs" / "matplotlib"
    m_dir.mkdir(parents=True)
    (m_dir / "00_pyplot.primitives.d.ps").write_text("namespace PythonSharp.Primitives.Matplotlib.Pyplot;", encoding="utf-8")
    (m_dir / "01_pyplot.raw.d.ps").write_text("namespace PythonSharp.Raw.Matplotlib.Pyplot;", encoding="utf-8")
    (m_dir / "02_pyplot.csharp.d.ps").write_text("namespace PythonSharp.Bridge.Matplotlib.Pyplot;", encoding="utf-8")
    (m_dir / "03_pyplot.enterprise.d.ps").write_text("namespace PythonSharp.Matplotlib.Pyplot;", encoding="utf-8")

    # Write .ps.conf.json disabling 02_scientific_and_ai, disabling package 'matplotlib' in stdlib, and preferred_surface=2
    (proj_dir / ".ps.conf.json").write_text(
        """{
    "stub_layers": {
        "02_scientific_and_ai": false
    },
    "disabled_packages": ["matplotlib"],
    "preferred_surface": 2
}
""",
        encoding="utf-8",
    )

    cfg = load_project(proj_dir / "MyProject.psproj", stdlib_dir=stdlib_mock)
    stub_names = [s.name for s in cfg.stub_files]

    # Verify 02_scientific_and_ai / matplotlib handcrafted stdlib stub was filtered out
    assert "matplotlib.d.ps" not in stub_names
    assert "math.d.ps" in stub_names
    assert "00_primitives.d.ps" in stub_names

    # Verify triple-surface filtering: Surface 0 (primitives) and Surface 2 (csharp) are present, Surface 1 and 3 are filtered!
    assert "00_pyplot.primitives.d.ps" in stub_names
    assert "02_pyplot.csharp.d.ps" in stub_names
    assert "01_pyplot.raw.d.ps" not in stub_names
    assert "03_pyplot.enterprise.d.ps" not in stub_names


def test_bindgen_reexport_synthesis(tmp_path: Path) -> None:
    pkg_dir = tmp_path / "typings" / "data_pkg"
    pkg_dir.mkdir(parents=True)
    
    # Submodule with function and class definitions
    sub_dir = pkg_dir / "io"
    sub_dir.mkdir(parents=True)
    (sub_dir / "readers.pyi").write_text(
        """class DataFrame:
    def __getitem__(self, key): ...

def read_data(path: str) -> DataFrame: ...
""",
        encoding="utf-8",
    )

    # __init__.pyi re-exporting read_data and DataFrame
    (pkg_dir / "__init__.pyi").write_text(
        """from data_pkg.io.readers import DataFrame as DataFrame, read_data as read_data
__all__ = ['DataFrame', 'read_data']
""",
        encoding="utf-8",
    )

    from psc.bindgen import generate_bindings

    out_stubs = tmp_path / ".ps-stubs" / "data_pkg"
    generate_bindings(pkg_dir, out_dir=out_stubs, triple_surface=True, package_name="data_pkg")

    # Check that 02_data_pkg.csharp.d.ps synthesized ReadData and DataFrame on the static module class
    csharp_stub = out_stubs / "data_pkg" / "02_data_pkg.csharp.d.ps"
    assert csharp_stub.exists()
    content = csharp_stub.read_text(encoding="utf-8")

    assert "public static class DataPkg" in content
    assert "ReadData" in content
    assert "DataFrame" in content
    # And indexer in readers.pyi must return object, NOT void
    reader_stub = out_stubs / "data_pkg" / "io" / "readers" / "02_readers.csharp.d.ps"
    assert reader_stub.exists()
    reader_content = reader_stub.read_text(encoding="utf-8")
    assert "public extern object this[object index] { get; }" in reader_content


def test_create_project_generates_ps_conf_json(tmp_path: Path) -> None:
    import json
    from psc.cli import create_project

    proj_dir = tmp_path / "MyNewApp"
    code = create_project("MyNewApp", proj_dir)
    assert code == 0

    assert (proj_dir / "MyNewApp.psproj").exists()
    assert (proj_dir / "ProjMain.ps").exists()
    assert (proj_dir / "TestUtil.ps").exists()
    assert (proj_dir / "run_main.py").exists()

    conf_path = proj_dir / ".ps.conf.json"
    assert conf_path.exists()
    data = json.loads(conf_path.read_text(encoding="utf-8"))
    assert data["stub_layers"]["00_core"] is True
    assert data["stub_layers"]["01_python_stdlib"] is True
    assert data["stub_layers"]["02_scientific_and_ai"] is True
    assert data["stub_layers"]["dedicated_stubs"] is True
    assert data["preferred_surface"] == 2


def test_stubgen_excludes_tests_by_default_and_includes_with_flag(tmp_path: Path) -> None:
    from psc.bindgen import generate_bindings

    pkg_dir = tmp_path / "typings" / "sample_pkg"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.pyi").write_text("def hello() -> str: ...\n", encoding="utf-8")

    # Core module
    core_dir = pkg_dir / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "calc.pyi").write_text("def add(a: int, b: int) -> int: ...\n", encoding="utf-8")

    # Tests directory
    tests_dir = pkg_dir / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_calc.pyi").write_text("def test_add() -> None: ...\n", encoding="utf-8")

    # 1. Default run: skips tests/
    out_default = tmp_path / "stubs_default"
    gen_default = generate_bindings(pkg_dir, out_dir=out_default, package_name="sample_pkg")
    default_names = [p.name for p in gen_default]
    assert "calc.d.ps" in default_names
    assert "sample_pkg.d.ps" in default_names
    assert "test_calc.d.ps" not in default_names

    # 2. Explicit run with include_tests=True
    out_tests = tmp_path / "stubs_with_tests"
    gen_tests = generate_bindings(pkg_dir, out_dir=out_tests, package_name="sample_pkg", include_tests=True)
    tests_names = [p.name for p in gen_tests]
    assert "calc.d.ps" in tests_names
    assert "test_calc.d.ps" in tests_names



