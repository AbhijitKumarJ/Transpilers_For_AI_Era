from __future__ import annotations

from pathlib import Path

import pytest

from psc import compile_sources
from psc.bindgen import generate_bindings, parse_pyi_source
from psc.bindgen.manifest import BindingManifest, compute_file_hash

SAMPLE_MATH_UTILS_PYI = """
from typing import Optional, Union, List

VERSION: str

def add(x: int, y: int) -> int: ...
def power(base: float, exp: float = 2.0) -> float: ...
def normalize(value: Union[int, float], scale: Optional[float] = None) -> float: ...
def log_message(msg: str, *args: object, **kwargs: object) -> None: ...

class Calculator:
    precision: int
    def __init__(self, precision: int = 4) -> None: ...
    @property
    def is_active(self) -> bool: ...
    @is_active.setter
    def is_active(self, value: bool) -> None: ...
    def compute(self, data: List[float]) -> float: ...
    @staticmethod
    def create_default() -> Calculator: ...
    def __getitem__(self, index: int) -> float: ...
    def __setitem__(self, index: int, value: float) -> None: ...
"""


def test_parse_pyi_generates_valid_d_ps() -> None:
    d_ps = parse_pyi_source(SAMPLE_MATH_UTILS_PYI, module_name="math_utils")

    # Assert namespace and using
    assert "namespace Extern.MathUtils;" in d_ps
    assert "extern using math_utils;" in d_ps

    # Assert static module class for top-level functions and constants
    assert "public static class MathUtils" in d_ps
    assert '[MapsTo("VERSION")]' in d_ps
    assert "public static extern string Version { get; }" in d_ps

    # Assert snake_case -> PascalCase with [MapsTo]
    assert '[MapsTo("add")]' in d_ps
    assert "public static extern int Add(int x, int y);" in d_ps

    # Assert default parameter value
    assert '[MapsTo("power")]' in d_ps
    assert "public static extern float Power(float @base, float exp = 2.0);" in d_ps

    # Assert Union parameter splitting into overloads
    assert '[MapsTo("normalize")]' in d_ps
    assert "public static extern float Normalize(int value, float? scale = null);" in d_ps
    assert "public static extern float Normalize(float value, float? scale = null);" in d_ps

    # Assert *args and **kwargs
    assert '[MapsTo("log_message")]' in d_ps
    assert "params object[] args" in d_ps
    assert "[KwArgs] object kwargs = null" in d_ps

    # Assert class generation
    assert "public class Calculator" in d_ps
    assert '[MapsTo("precision")]' in d_ps
    assert "public extern int Precision;" in d_ps

    # Assert constructor
    assert "public extern Calculator(int precision = 4);" in d_ps

    # Assert properties
    assert '[MapsTo("is_active")]' in d_ps
    assert "public extern bool IsActive { get; set; }" in d_ps

    # Assert static method
    assert '[MapsTo("create_default")]' in d_ps
    assert "public static extern Calculator CreateDefault();" in d_ps

    # Assert indexers
    assert "public extern float this[int index] { get; set; }" in d_ps


def test_generate_bindings_and_manifest(tmp_path: Path) -> None:
    stubs_dir = tmp_path / "stubs"
    stubs_dir.mkdir()
    pyi_file = stubs_dir / "sample_pkg.pyi"
    pyi_file.write_text(
        "def ping() -> bool: ...\nclass Client:\n    def connect(self) -> None: ...\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    manifest_path = out_dir / "psc-bindings-manifest.json"

    generated = generate_bindings(stubs_dir, out_dir=out_dir, manifest_path=manifest_path)
    assert len(generated) == 1
    assert generated[0].name == "sample_pkg.d.ps"
    assert generated[0].exists()

    # Verify manifest
    assert manifest_path.exists()
    manifest = BindingManifest.load_from(manifest_path)
    assert "sample_pkg" in manifest.entries
    entry = manifest.entries["sample_pkg"]
    assert entry.pyi_hash == compute_file_hash(pyi_file)
    assert not manifest.is_drifted("sample_pkg", pyi_file)

    # Drift check: modify .pyi
    pyi_file.write_text("def ping() -> bool: ...\ndef pong() -> bool: ...\n", encoding="utf-8")
    assert manifest.is_drifted("sample_pkg", pyi_file)


def test_bindgen_cli_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from psc.cli import main

    pyi_file = tmp_path / "tiny.pyi"
    pyi_file.write_text("def run_task(id: int) -> None: ...\n", encoding="utf-8")
    out_dir = tmp_path / "out_stubs"

    code = main(["bindgen", str(pyi_file), "--out-dir", str(out_dir)])
    assert code == 0
    captured = capsys.readouterr()
    assert "Bindgen succeeded: generated 1 .d.ps file(s)" in captured.out
    assert (out_dir / "tiny.d.ps").exists()


def test_end_to_end_transpilation_with_generated_bindings(tmp_path: Path) -> None:
    # 1. Create a dummy native Python module to call into
    py_module_dir = tmp_path / "native_pkg"
    py_module_dir.mkdir()
    (py_module_dir / "__init__.py").write_text("", encoding="utf-8")
    (py_module_dir / "engine.py").write_text(
        """
def compute_sum(a: int, b: int) -> int:
    return a + b

class Worker:
    def __init__(self, name: str) -> None:
        self._name = name
    def get_greeting(self) -> str:
        return f"Hello, {self._name}!"
""",
        encoding="utf-8",
    )

    # 2. Generate .d.ps from a .pyi stub
    pyi_content = """
def compute_sum(a: int, b: int) -> int: ...

class Worker:
    def __init__(self, name: str) -> None: ...
    def get_greeting(self) -> str: ...
"""
    pyi_path = tmp_path / "engine.pyi"
    pyi_path.write_text(pyi_content, encoding="utf-8")
    d_ps_content = parse_pyi_source(pyi_content, module_name="native_pkg.engine")

    # 3. Write a PythonSharp project that uses the generated bindings
    ps_code = """
namespace App;

using PythonSharp.Core;
using Extern.NativePkg.Engine;

public class Program
{
    public static int Main()
    {
        int sum = Engine.ComputeSum(10, 32);
        Worker w = new Worker("Ada");
        string greeting = w.GetGreeting();
        return sum;
    }
}
"""
    stdlib_source = Path("stdlib/PythonSharp.Core.d.ps").read_text(encoding="utf-8")
    sources = {
        "App/Program.ps": ps_code,
        "Extern/Engine.d.ps": d_ps_content,
    }

    out_dist = tmp_path / "dist"
    artifacts, diagnostics = compile_sources(
        sources=sources,
        out_dir=out_dist,
        stdlib_source=stdlib_source,
        assembly_name="App",
        emit_pyc=False,
    )

    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    emitted_code = artifacts[0].py_source

    # Check lowered code calls through correctly
    assert "compute_sum(10, 32)" in emitted_code
    assert "Worker('Ada')" in emitted_code
    assert "get_greeting()" in emitted_code
