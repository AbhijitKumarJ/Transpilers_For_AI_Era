from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.native import NativeCompiler
from psc.semantics import GlobalSymbolTable, analyze_compilation_units


def test_detect_native_types() -> None:
    source = """
    namespace FastMath;

    [NativeCompile]
    public class Matrix
    {
        public int Determinant() => 42;
    }

    public class NormalClass {}
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, file_id=0, ps_filename="Matrix.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable(default_assembly_name="FastMath")
    analyze_compilation_units([unit], symtab=symtab, diagnostics=diag, assembly_name="FastMath")

    assert not diag.has_errors()
    assert NativeCompiler.has_native_types(symtab) is True

    # Negative check
    source_normal = "namespace Plain; public class Regular {}"
    diag2 = DiagnosticEngine()
    unit2 = Parser.from_source(source_normal, file_id=0, ps_filename="Plain.ps", diagnostics=diag2).parse_compilation_unit()
    symtab2 = GlobalSymbolTable(default_assembly_name="Plain")
    analyze_compilation_units([unit2], symtab=symtab2, diagnostics=diag2, assembly_name="Plain")
    assert NativeCompiler.has_native_types(symtab2) is False


def test_native_compile_missing_tools(tmp_path: Path) -> None:
    py_file = tmp_path / "module.py"
    py_file.write_text("def run(): return 10\n", encoding="utf-8")

    compiler = NativeCompiler()
    with patch("shutil.which", return_value=None):
        res = compiler.compile_module(py_file, out_dir=tmp_path)
        assert res.success is False
        assert "Neither 'mypyc' nor 'cythonize'" in str(res.error)


def test_native_compile_mypyc_success(tmp_path: Path) -> None:
    py_file = tmp_path / "fast_calc.py"
    py_file.write_text("def compute() -> int: return 123\n", encoding="utf-8")
    expected_so = tmp_path / "fast_calc.cpython-312-x86_64-linux-gnu.so"
    expected_so.write_text("fake binary", encoding="utf-8")

    compiler = NativeCompiler()
    with patch("shutil.which", side_effect=lambda x: "/usr/bin/mypyc" if x == "mypyc" else None):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Compilation finished"
            mock_run.return_value.stderr = ""
            res = compiler.compile_module(py_file, out_dir=tmp_path)
            assert res.success is True
            assert res.compiler_used == "mypyc"
            assert res.output_binary == expected_so
