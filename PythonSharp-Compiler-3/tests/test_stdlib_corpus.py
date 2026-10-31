from __future__ import annotations

import ast
from pathlib import Path

from psc.cli import _discover_inputs, parse_and_analyze_config
from psc.codegen import NamespacePackagePlanner, PythonAstBuilder
from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.project import find_stdlib_stubs, is_ps_stub_file
from psc.semantics import GlobalSymbolTable
from psc.semantics.collector import SymbolCollector


def test_all_stdlib_stubs_parse_with_zero_errors() -> None:
    """Every .d.ps stub across core, python_stdlib, and scientific packages must parse with 0 errors."""
    stdlib_dir = Path("stdlib")
    stubs = sorted(p for p in stdlib_dir.rglob("*") if p.is_file() and is_ps_stub_file(p))
    assert len(stubs) >= 94, f"Expected at least 94 stdlib stubs, found {len(stubs)}"

    for stub in stubs:
        diag = DiagnosticEngine()
        unit = Parser.from_source(
            stub.read_text(encoding="utf-8"),
            file_id=0,
            ps_filename=str(stub),
            diagnostics=diag,
        ).parse_compilation_unit()
        assert not diag.has_errors(), f"Parse errors in {stub}:\n{diag.format_all()}"
        assert len(unit.types) >= 1 or len(unit.imports) >= 0


def test_stdlib_symbols_collect_and_analyze_with_zero_diagnostics() -> None:
    """Ambient standard library stubs collect into the global symbol table without collisions."""
    stdlib_dir = Path("stdlib")
    ordered_stubs = find_stdlib_stubs(stdlib_dir)
    assert len(ordered_stubs) >= 90

    diag = DiagnosticEngine()
    units = []
    for idx, stub in enumerate(ordered_stubs):
        unit = Parser.from_source(
            stub.read_text(encoding="utf-8"),
            file_id=-(idx + 1),
            ps_filename=str(stub),
            diagnostics=diag,
        ).parse_compilation_unit()
        units.append(unit)

    assert not diag.has_errors(), f"Parse errors loading stdlib:\n{diag.format_all()}"

    symtab = GlobalSymbolTable(default_assembly_name="PythonSharp.Stdlib")
    collector = SymbolCollector(symtab=symtab, diagnostics=diag)
    collector.collect_all(units)

    assert not diag.has_errors(), f"Symbol collection errors in stdlib:\n{diag.format_all()}"

    # Verify key types exist across all 3 surfaces
    assert "PythonSharp.Core.String" in symtab.types_by_qname
    assert "PythonSharp.Core.Bytes" in symtab.types_by_qname
    assert "PythonSharp.Core.Complex" in symtab.types_by_qname
    assert "PythonSharp.Numerics.Tensors.NDArray" in symtab.types_by_qname
    assert "PythonSharp.DataScience.Tabular.DataFrame" in symtab.types_by_qname
    assert "PythonSharp.DeepLearning.TorchTensor" in symtab.types_by_qname


def test_sample_07_customer_churn_pipeline_compiles_cleanly() -> None:
    """Sample 07 customer churn prediction pipeline transpiles across all 3 surfaces."""
    psproj = Path("Samples/07_ai_ml_triple_surface/CustomerChurnPipeline.psproj")
    config = _discover_inputs(psproj, out_dir=None)
    units, symtab, diag = parse_and_analyze_config(config)

    assert not diag.has_errors(), f"Diagnostics in Sample 07:\n{diag.format_all()}"

    planner = NamespacePackagePlanner(symtab)
    planned = planner.plan_modules()
    assert "enterprise_ai/churn_prediction.py" in planned

    builder = PythonAstBuilder(symtab)
    py_mod = builder.build_module(planned["enterprise_ai/churn_prediction.py"])
    code = ast.unparse(py_mod)

    # Verify Surface 2 (Raw Python ABI)
    assert "pd.read_csv" in code
    assert "to_numpy" in code

    # Verify Surface 3 (C# Bridge)
    assert "_prep.StandardScaler()" in code
    assert "_ms.train_test_split" in code
    assert "_ens.RandomForestClassifier" in code
    assert "_met.accuracy_score" in code

    # Verify Surface 1 (Enterprise FQN) & Decorator Lowering
    assert "'cuda' if _torch.cuda.is_available() else 'cpu'" in code
    assert "@disable_gradient_tracking" in code
    assert "_torch.from_numpy" in code

