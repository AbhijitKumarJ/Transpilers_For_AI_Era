from __future__ import annotations

import ast

from psc.codegen.py_ast_builder import PythonAstBuilder
from psc.codegen.topo_sorter import NamespacePackagePlanner
from psc.diagnostics import DiagnosticEngine
from psc.frontend.lexer import Lexer
from psc.frontend.parser import Parser
from psc.semantics import analyze_compilation_units
from psc.semantics.collector import SymbolCollector
from psc.semantics.symbols import GlobalSymbolTable


def test_canonical_and_surface_level_attributes() -> None:
    source = """
    namespace PythonSharp.Test;

    [SurfaceLevel(2)]
    public static primitive class RawApi
    {
        [CanonicalApi("PythonSharp.Test.EnterpriseApi.ExecuteCanonical", "PythonSharp.Test.BridgeApi.ExecuteBridge")]
        [SurfaceLevel(2)]
        [InlineTemplate("raw_exec({0})")]
        public static extern void raw_exec(string command);
    }
    """
    diag = DiagnosticEngine()
    tokens = Lexer(source, file_id=0, ps_filename="Test.d.ps", diagnostics=diag).tokenize()
    unit = Parser(tokens, diag).parse_compilation_unit()
    unit.is_ambient_stub = True

    symtab = GlobalSymbolTable()
    collector = SymbolCollector(symtab, diag)
    collector.collect_all([unit])

    raw_type = symtab.types_by_qname["PythonSharp.Test.RawApi"]
    assert raw_type.surface_level == 2

    members = raw_type.lookup_member("raw_exec")
    assert len(members) == 1
    m = members[0]
    assert m.surface_level == 2
    assert m.canonical_api == "PythonSharp.Test.EnterpriseApi.ExecuteCanonical"
    assert m.bridge_api == "PythonSharp.Test.BridgeApi.ExecuteBridge"
    assert m.inline_template == "raw_exec({0})"


def test_primitive_static_property_lowering_and_auto_import() -> None:
    source_stub = """
    namespace os;

    [SurfaceLevel(2)]
    public static primitive class os
    {
        [InlineTemplate("os.environ")]
        public static extern object environ { get; }

        [InlineTemplate("os.path.join({0}, {1})")]
        public static extern string join(string a, string b);
    }
    """
    source_user = """
    namespace App;

    using os;

    public class Worker
    {
        public static string Run()
        {
            var env = os.environ;
            var path = os.join("dir", "file.txt");
            return path;
        }
    }
    """
    diag = DiagnosticEngine()
    toks_stub = Lexer(source_stub, file_id=0, ps_filename="os.d.ps", diagnostics=diag).tokenize()
    unit_stub = Parser(toks_stub, diag).parse_compilation_unit()
    unit_stub.is_ambient_stub = True

    toks_user = Lexer(source_user, file_id=1, ps_filename="Worker.ps", diagnostics=diag).tokenize()
    unit_user = Parser(toks_user, diag).parse_compilation_unit()

    units = [unit_stub, unit_user]
    symtab = GlobalSymbolTable()
    analyze_compilation_units(units, symtab, diag)

    planned_modules = NamespacePackagePlanner(symtab).plan_modules()
    assert "app.py" in planned_modules or "__root__.py" in planned_modules
    planned = planned_modules.get("app.py") or list(planned_modules.values())[0]

    builder = PythonAstBuilder(symtab)
    py_mod = builder.build_module(planned)
    code = ast.unparse(py_mod)

    # Verify auto-import of `os` occurred without explicit `extern using os;`
    assert "import os" in code
    # Verify `os.environ` lowered as an attribute read (not a call `os.environ()`)
    assert "os.environ" in code
    assert "os.environ()" not in code
    # Verify `os.path.join` lowered as expected
    assert "os.path.join('dir', 'file.txt')" in code or 'os.path.join("dir", "file.txt")' in code


def test_triple_surface_numpy_transpilation() -> None:
    from pathlib import Path
    stdlib_dir = Path(__file__).parent.parent / "stdlib"
    diag = DiagnosticEngine()

    stub_units = []
    file_id = 0
    for stub_path in sorted(stdlib_dir.rglob("*.d.ps")):
        source = stub_path.read_text(encoding="utf-8")
        toks = Lexer(source, file_id=file_id, ps_filename=stub_path.name, diagnostics=diag).tokenize()
        unit = Parser(toks, diag).parse_compilation_unit()
        unit.is_ambient_stub = True
        stub_units.append(unit)
        file_id += 1

    # Surface 3 & Surface 1 Test
    user_source = """
    namespace AI.Calibration;

    using PythonSharp.Numerics.Tensors;
    using PythonSharp.Numerics.LinearAlgebra;
    using PythonSharp.Numerics.Creation;
    using PythonSharp.NumPy;

    public class CalibrationPipeline
    {
        public static NDArray<double> RunSurface3(NDArray<double> mat)
        {
            var z = np.Zeros(3, 3);
            var inv = np.LinearAlgebra.Inverse(mat);
            return inv;
        }

        public static NDArray<double> RunSurface1(NDArray<double> mat)
        {
            var z = ArrayFactory.CreateZeroMatrix(3, 3);
            var inv = MatrixOperations.ComputeInverse(mat);
            return inv;
        }
    }
    """
    toks_user = Lexer(user_source, file_id=file_id, ps_filename="CalibrationPipeline.ps", diagnostics=diag).tokenize()
    unit_user = Parser(toks_user, diag).parse_compilation_unit()

    units = [*stub_units, unit_user]
    symtab = GlobalSymbolTable()
    analyze_compilation_units(units, symtab, diag)

    assert not diag.has_errors(), [d.message for d in diag.diagnostics]

    planned_modules = NamespacePackagePlanner(symtab).plan_modules()
    assert "ai/calibration.py" in planned_modules
    planned = planned_modules["ai/calibration.py"]

    builder = PythonAstBuilder(symtab)
    py_mod = builder.build_module(planned)
    code = ast.unparse(py_mod)

    # Verify that both Surface 3 and Surface 1 lowered cleanly to zero-wrapper NumPy calls
    assert "import numpy as _np" in code
    assert "def run_surface_3(mat" in code
    assert "_np.zeros((3, 3))" in code
    assert "_np.linalg.inv(mat)" in code

    assert "def run_surface_1(mat" in code


def test_triple_surface_matrix_multiplication_and_slicing() -> None:
    from pathlib import Path

    from psc.cli import _discover_inputs, parse_and_analyze_config

    config = _discover_inputs(Path("Samples/Ported/20_numpy_numerics/NumpyNumerics.psproj"), out_dir=None)
    units, symtab, diag = parse_and_analyze_config(config)

    assert not diag.has_errors(), [d.message for d in diag.diagnostics]

    planned_modules = NamespacePackagePlanner(symtab).plan_modules()
    assert "numpy_numerics.py" in planned_modules
    planned = planned_modules["numpy_numerics.py"]

    builder = PythonAstBuilder(symtab)
    py_mod = builder.build_module(planned)
    code = ast.unparse(py_mod)

    # Verify @ operator lowering
    assert "return a @ b" in code
    # Verify .T property lowering
    assert "return matrix.T" in code
    # Verify multi-axis slicing lowering
    assert "return matrix[0:2, 0:2]" in code


def test_sample_06_triple_surface_showcase_compiles() -> None:
    from pathlib import Path

    from psc.cli import _discover_inputs, parse_and_analyze_config

    config = _discover_inputs(Path("Samples/06_triple_surface_migration/TripleSurface.psproj"), out_dir=None)
    units, symtab, diag = parse_and_analyze_config(config)

    assert not diag.has_errors(), [d.message for d in diag.diagnostics]

    planned_modules = NamespacePackagePlanner(symtab).plan_modules()
    assert "triple_surface_migration.py" in planned_modules
    planned = planned_modules["triple_surface_migration.py"]

    builder = PythonAstBuilder(symtab)
    py_mod = builder.build_module(planned)
    code = ast.unparse(py_mod)

    assert "import numpy as _np" in code
    assert "import numpy as np" in code
    assert "import time as _py_time" in code
    assert "import json as _py_json" in code
    assert "a @ b" in code
    assert "a.dot(b)" in code
