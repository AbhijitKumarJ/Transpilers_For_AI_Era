from __future__ import annotations

import ast
from pathlib import Path

from psc.bindgen import generate_bindings
from psc.bindgen.generator import BindgenGenerator
from psc.bindgen.manifest import BindingManifest
from psc.diagnostics import DiagnosticEngine
from psc.frontend.parser import Parser

SAMPLE_PYI = """
from typing import List

VERSION: str

def add(x: int, y: int) -> int: ...

class Calculator:
    precision: int
    def __init__(self, precision: int = 4) -> None: ...
    @property
    def is_active(self) -> bool: ...
    def compute(self, data: List[float]) -> float: ...
    def __getitem__(self, index: int) -> float: ...
"""


def test_generator_triple_surface_bundle() -> None:
    pyi_ast = ast.parse(SAMPLE_PYI)
    gen = BindgenGenerator(module_name="math_utils")
    bundle = gen.generate_triple_surface_bundle(pyi_ast)

    assert set(bundle.keys()) == {
        "00_math_utils.primitives.d.ps",
        "01_math_utils.raw.d.ps",
        "02_math_utils.csharp.d.ps",
        "03_math_utils.enterprise.d.ps",
    }

    # 1. Primitives
    prim = bundle["00_math_utils.primitives.d.ps"]
    assert "namespace PythonSharp.Primitives.MathUtils;" in prim
    assert '[MapsTo("Calculator")]' in prim
    assert '[RuntimeType("math_utils.Calculator")]' in prim
    assert "public primitive class Calculator" in prim

    # 2. Raw (Surface 1)
    raw = bundle["01_math_utils.raw.d.ps"]
    assert "namespace PythonSharp.Raw.MathUtils;" in raw
    assert "[SurfaceLevel(1)]" in raw
    assert '[CanonicalApi("PythonSharp.MathUtils.MathUtils.Add")]' in raw
    assert "public static extern int add(int x, int y);" in raw
    assert '[CanonicalApi("PythonSharp.MathUtils.Calculator.Compute")]' in raw
    assert "public extern float compute(List<float> data);" in raw

    # 3. C# Bridge (Surface 2)
    bridge = bundle["02_math_utils.csharp.d.ps"]
    assert "namespace PythonSharp.Bridge.MathUtils;" in bridge
    assert "[SurfaceLevel(2)]" in bridge
    assert '[CanonicalApi("PythonSharp.MathUtils.MathUtils.Add")]' in bridge
    assert "public static extern int Add(int x, int y);" in bridge
    assert '[CanonicalApi("PythonSharp.MathUtils.Calculator.Compute")]' in bridge
    assert "public extern float Compute(List<float> data);" in bridge

    # 4. Enterprise (Surface 3)
    ent = bundle["03_math_utils.enterprise.d.ps"]
    assert "namespace PythonSharp.MathUtils;" in ent
    assert "[SurfaceLevel(3)]" in ent
    assert "public static extern int Add(int x, int y);" in ent
    assert "public extern float Compute(List<float> data);" in ent

    # Verify all generated .d.ps files parse without errors
    for filename, content in bundle.items():
        diag = DiagnosticEngine()
        unit = Parser.from_source(content, file_id=0, ps_filename=filename, diagnostics=diag).parse_compilation_unit()
        assert not diag.has_errors(), f"Syntax errors in {filename}: {diag.format_all()}"
        assert unit.namespace is not None


def test_generate_bindings_triple_surface_manifest(tmp_path: Path) -> None:
    stubs_dir = tmp_path / "stubs"
    stubs_dir.mkdir()
    pyi_file = stubs_dir / "math_utils.pyi"
    pyi_file.write_text(SAMPLE_PYI, encoding="utf-8")

    out_dir = tmp_path / "out"
    manifest_path = out_dir / "psc-bindings-manifest.json"

    generated = generate_bindings(
        stubs_dir,
        out_dir=out_dir,
        manifest_path=manifest_path,
        triple_surface=True,
    )
    assert len(generated) == 4
    filenames = {f.name for f in generated}
    assert filenames == {
        "00_math_utils.primitives.d.ps",
        "01_math_utils.raw.d.ps",
        "02_math_utils.csharp.d.ps",
        "03_math_utils.enterprise.d.ps",
    }

    manifest = BindingManifest.load_from(manifest_path)
    assert "math_utils" in manifest.entries
    entry = manifest.entries["math_utils"]
    assert "primitives" in entry.surface_files
    assert "surface_1" in entry.surface_files
    assert "surface_2" in entry.surface_files
    assert "surface_3" in entry.surface_files
