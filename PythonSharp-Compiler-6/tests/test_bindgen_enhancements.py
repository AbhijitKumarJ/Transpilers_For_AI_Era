from __future__ import annotations

import ast
from pathlib import Path

from psc import compile_sources
from psc.bindgen import generate_bindings, parse_pyi_source
from psc.bindgen.generator import BindgenGenerator

STDLIB = Path("stdlib/PythonSharp.Core.d.ps").read_text(encoding="utf-8")


def test_bindgen_nested_directories(tmp_path: Path) -> None:
    stubs_dir = tmp_path / "stubs"
    stubs_dir.mkdir()

    # Create nested pyi: urllib/request.pyi
    urllib_dir = stubs_dir / "urllib"
    urllib_dir.mkdir()
    (urllib_dir / "request.pyi").write_text("def urlopen(url: str) -> object: ...\n", encoding="utf-8")

    out_dir = tmp_path / "out"

    # Test single-file mode
    generated = generate_bindings(stubs_dir, out_dir=out_dir, triple_surface=False)
    assert len(generated) == 1
    expected_path = out_dir / "urllib" / "request.d.ps"
    assert expected_path.exists()
    assert generated[0] == expected_path

    content = expected_path.read_text(encoding="utf-8")
    assert "namespace Extern.Urllib.Request;" in content
    assert "public static extern object Urlopen(string url);" in content

    # Test triple-surface mode
    out_ts = tmp_path / "out_ts"
    generated_ts = generate_bindings(stubs_dir, out_dir=out_ts, triple_surface=True)
    assert len(generated_ts) == 4
    expected_ts_dir = out_ts / "urllib" / "request"
    assert (expected_ts_dir / "00_request.primitives.d.ps").exists()
    assert (expected_ts_dir / "01_request.raw.d.ps").exists()
    assert (expected_ts_dir / "02_request.csharp.d.ps").exists()
    assert (expected_ts_dir / "03_request.enterprise.d.ps").exists()


def test_bindgen_ast_conditional_flattening() -> None:
    pyi_source = """
import sys
from typing import TYPE_CHECKING

if sys.version_info >= (3, 11):
    def modern_feature() -> int: ...
else:
    def legacy_feature() -> int: ...

if sys.version_info < (3, 8):
    def obsolete_feature() -> int: ...

if TYPE_CHECKING:
    class StaticCheckOnly:
        val: str

class MyService:
    if sys.version_info >= (3, 10):
        def service_method(self) -> bool: ...
"""
    d_ps = parse_pyi_source(pyi_source, module_name="conditional_pkg")

    # Features for 3.11+ should be included
    assert "public static extern int ModernFeature();" in d_ps
    assert "public class StaticCheckOnly" in d_ps
    assert "public extern bool ServiceMethod();" in d_ps

    # Features for < 3.8 and else-branch should be excluded
    assert "LegacyFeature" not in d_ps
    assert "ObsoleteFeature" not in d_ps


def test_bindgen_ps002_overload_deduplication(tmp_path: Path) -> None:
    pyi_source = """
from typing import overload, Literal

@overload
def open(file: str, mode: Literal["r"] = "r") -> object: ...
@overload
def open(file: str, mode: Literal["w"] = "w") -> object: ...
@overload
def open(file: str, mode: Literal["rb"] = "rb") -> object: ...

class Reader:
    @overload
    def read(self, size: int = -1) -> bytes: ...
    @overload
    def read(self, size: None = None) -> bytes: ...
"""
    d_ps = parse_pyi_source(pyi_source, module_name="io_pkg")

    # Verify that duplicate erased signatures (open with file, mode) were deduplicated
    open_count = d_ps.count("public static extern object Open(")
    assert open_count == 1, f"Expected 1 Open signature, found {open_count}:\n{d_ps}"

    # Verify Reader.read was deduplicated
    read_count = d_ps.count("public extern bytes Read(")
    assert read_count == 1, f"Expected 1 Read signature, found {read_count}:\n{d_ps}"

    # Verify that the generated .d.ps compiles cleanly in a PythonSharp project without PS002 errors
    ps_code = """
namespace TestApp;

using PythonSharp.Core;
using Extern.IoPkg;

public class Program
{
    public static void Main()
    {
        object f = IoPkg.Open("test.txt");
    }
}
"""
    sources = {
        "TestApp/Program.ps": ps_code,
        "Extern/IoPkg.d.ps": d_ps,
    }
    artifacts, diagnostics = compile_sources(
        sources=sources,
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="TestApp",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), f"Expected no PS002 errors, but got:\n{diagnostics.format_all()}"
