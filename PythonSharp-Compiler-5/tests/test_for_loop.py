from __future__ import annotations

import ast

from psc.frontend import Lexer, Parser
from psc.diagnostics import DiagnosticEngine
from psc.semantics import GlobalSymbolTable, analyze_compilation_units
from psc.codegen.expr_lowerer import ExpressionLowerer


def _parse_and_lower_snippet(code: str) -> str:
    source = f"""namespace TestNs;

public class TestLoop
{{
    public void Test()
    {{
{code}
    }}
}}
"""
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, file_id=0, ps_filename="TestLoop.ps", diagnostics=diag).parse_compilation_unit()
    assert not diag.has_errors(), f"Parse errors: {diag.diagnostics}"

    symtab = GlobalSymbolTable(default_assembly_name="TestAsm")
    analyze_compilation_units([unit], symtab=symtab, diagnostics=diag, assembly_name="TestAsm")
    assert not diag.has_errors(), f"Semantic errors: {diag.diagnostics}"

    type_decl = unit.types[0]
    method_decl = type_decl.members[0]
    lowerer = ExpressionLowerer(symtab=symtab, current_type=symtab.types_by_qname["TestNs.TestLoop"])
    stmts = lowerer.lower_block(method_decl.body)
    mod = ast.Module(body=stmts, type_ignores=[])
    return ast.unparse(mod)


def test_for_loop_range_lowering_basic() -> None:
    code = """
        int sum = 0;
        for (int i = 0; i < 10; i++)
        {
            sum += i;
        }
    """
    py_code = _parse_and_lower_snippet(code)
    assert "for i in range(10):" in py_code
    assert "sum += i" in py_code

    # Execute and verify
    local_env: dict[str, int] = {}
    exec(py_code, {}, local_env)
    assert local_env["sum"] == 45


def test_for_loop_range_lowering_with_start_and_step() -> None:
    code = """
        int sum = 0;
        for (int i = 2; i < 10; i += 2)
        {
            sum += i;
        }
    """
    py_code = _parse_and_lower_snippet(code)
    assert "for i in range(2, 10, 2):" in py_code

    local_env: dict[str, int] = {}
    exec(py_code, {}, local_env)
    assert local_env["sum"] == 2 + 4 + 6 + 8


def test_for_loop_range_lowering_lte() -> None:
    code = """
        int sum = 0;
        for (int i = 1; i <= 5; i++)
        {
            sum += i;
        }
    """
    py_code = _parse_and_lower_snippet(code)
    assert "for i in range(1, 5 + 1):" in py_code

    local_env: dict[str, int] = {}
    exec(py_code, {}, local_env)
    assert local_env["sum"] == 15


def test_for_loop_while_fallback_decrement() -> None:
    code = """
        int count = 5;
        int sum = 0;
        for (int i = count; i > 0; i -= 1)
        {
            sum += i;
        }
    """
    py_code = _parse_and_lower_snippet(code)
    assert "while i > 0:" in py_code

    local_env: dict[str, int] = {}
    exec(py_code, {}, local_env)
    assert local_env["sum"] == 15


def test_for_loop_continue_semantics() -> None:
    code = """
        int sum = 0;
        for (int i = 0; i < 5; i++)
        {
            if (i == 2)
            {
                continue;
            }
            sum += i;
        }
    """
    py_code = _parse_and_lower_snippet(code)
    local_env: dict[str, int] = {}
    exec(py_code, {}, local_env)
    assert local_env["sum"] == 0 + 1 + 3 + 4


def test_increment_decrement_statements() -> None:
    code = """
        int x = 10;
        x++;
        x--;
        ++x;
        --x;
    """
    py_code = _parse_and_lower_snippet(code)
    local_env: dict[str, int] = {}
    exec(py_code, {}, local_env)
    assert local_env["x"] == 10
