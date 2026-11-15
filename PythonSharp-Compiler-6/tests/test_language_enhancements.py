from __future__ import annotations

import tempfile
from pathlib import Path

from psc import compile_sources
from psc.project import load_project
from psc.semantics.collector import SymbolCollector
from psc.semantics.symbols import GlobalSymbolTable

STDLIB = Path("stdlib/PythonSharp.Core.d.ps").read_text(encoding="utf-8")


def test_operator_overloading_compilation_and_execution(tmp_path: Path):
    source = """
namespace Geometry;

public class Vector
{
    public double X { get; set; }
    public double Y { get; set; }

    public Vector(double x, double y)
    {
        X = x;
        Y = y;
    }

    public static Vector operator +(Vector a, Vector b)
    {
        return new Vector(a.X + b.X, a.Y + b.Y);
    }

    public static Vector operator -(Vector a, Vector b)
    {
        return new Vector(a.X - b.X, a.Y - b.Y);
    }

    public static Vector operator *(Vector a, double scalar)
    {
        return new Vector(a.X * scalar, a.Y * scalar);
    }

    public static Vector operator -(Vector a)
    {
        return new Vector(-a.X, -a.Y);
    }

    public static bool operator ==(Vector a, Vector b)
    {
        return a.X == b.X && a.Y == b.Y;
    }

    public static bool operator !=(Vector a, Vector b)
    {
        return !(a == b);
    }

    public static double operator @(Vector a, Vector b)
    {
        return a.X * b.X + a.Y * b.Y;
    }
}

public static class App
{
    public static (double, double, double, bool, bool, double) Run()
    {
        var v1 = new Vector(2.0, 3.0);
        var v2 = new Vector(4.0, 5.0);

        var vAdd = v1 + v2;
        var vSub = v2 - v1;
        var vNeg = -v1;
        bool eq = (v1 == v2);
        bool neq = (v1 != v2);
        double dot = v1 @ v2;

        return (vAdd.X, vSub.Y, vNeg.X, eq, neq, dot);
    }
}
"""
    artifacts, diagnostics = compile_sources(
        sources={"Geometry.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="Geometry",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), f"Compile errors: {diagnostics.format_all()}"
    assert len(artifacts) == 1
    py_code = artifacts[0].py_source

    # Verify dunder methods were emitted without @staticmethod
    assert "def __add__(a: Vector, b: Vector) -> Vector:" in py_code
    assert "def __sub__(a: Vector, b: Vector) -> Vector:" in py_code
    assert "def __neg__(a: Vector) -> Vector:" in py_code
    assert "def __eq__(a: Vector, b: Vector) -> bool:" in py_code
    assert "def __ne__(a: Vector, b: Vector) -> bool:" in py_code
    assert "def __matmul__(a: Vector, b: Vector) -> float:" in py_code
    assert "@staticmethod\n    def __add__" not in py_code

    # Execute and verify runtime results
    scope: dict[str, object] = {}
    exec(py_code, scope)
    app_cls = scope["App"]
    run_fn = getattr(app_cls, "run")
    add_x, sub_y, neg_x, eq, neq, dot = run_fn()

    assert add_x == 6.0
    assert sub_y == 2.0
    assert neg_x == -2.0
    assert eq is False
    assert neq is True
    assert dot == (2.0 * 4.0 + 3.0 * 5.0)  # 23.0


def test_partial_classes_across_files(tmp_path: Path):
    p1 = """
namespace Commerce;

public partial class Order
{
    public string Id { get; set; } = "";

    public Order(string id)
    {
        Id = id;
    }

    partial void OnProcessed();
}
"""
    p2 = """
namespace Commerce;

public partial class Order
{
    public double Total { get; set; } = 0.0;
    public bool IsProcessed { get; set; } = false;

    partial void OnProcessed()
    {
        IsProcessed = true;
    }

    public void Process()
    {
        OnProcessed();
    }

    public string GetSummary()
    {
        return $"{Id}: {Total}";
    }
}

public static class Program
{
    public static (string, bool) Run()
    {
        var order = new Order("ORD-42");
        order.Total = 150.0;
        order.Process();
        return (order.GetSummary(), order.IsProcessed);
    }
}
"""
    artifacts, diagnostics = compile_sources(
        sources={"Order_Part1.ps": p1, "Order_Part2.ps": p2},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="Commerce",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), f"Compile errors: {diagnostics.format_all()}"
    assert len(artifacts) == 1
    py_code = artifacts[0].py_source

    scope: dict[str, object] = {}
    exec(py_code, scope)
    prog_cls = scope["Program"]
    summary, processed = getattr(prog_cls, "run")()
    assert summary == "ORD-42: 150.0"
    assert processed is True


def test_query_syntax_linq(tmp_path: Path):
    source = """
namespace QueryTest;

using System.Collections.Generic;

public static class QueryRunner
{
    public static List<int> RunFilterAndSort()
    {
        var numbers = new List<int>();
        numbers.Add(1);
        numbers.Add(5);
        numbers.Add(2);
        numbers.Add(8);
        numbers.Add(3);
        numbers.Add(7);
        numbers.Add(4);

        var result = (from n in numbers
                      where n > 2
                      orderby n descending
                      select n * 10).ToList();
        return result;
    }
}
"""
    artifacts, diagnostics = compile_sources(
        sources={"QueryTest.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="QueryTest",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), f"Compile errors: {diagnostics.format_all()}"
    assert len(artifacts) == 1
    py_code = artifacts[0].py_source

    # Execute and check
    scope: dict[str, object] = {}
    exec(py_code, scope)
    runner = scope["QueryRunner"]
    res = getattr(runner, "run_filter_and_sort")()
    # 8, 7, 5, 4, 3 * 10 -> [80, 70, 50, 40, 30]
    assert list(res) == [80, 70, 50, 40, 30]
