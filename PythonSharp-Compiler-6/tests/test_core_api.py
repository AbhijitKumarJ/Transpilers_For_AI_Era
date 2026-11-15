from __future__ import annotations

import math
from pathlib import Path

from psc import compile_sources

STDLIB = Path("stdlib/PythonSharp.Core.d.ps")


def _compile_and_exec(source: str, tmp_path: Path) -> tuple[dict[str, object], str]:
    artifacts, diag = compile_sources(
        sources={"CoreApi.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
    )
    assert not diag.has_errors(), diag.format_all()
    assert len(artifacts) == 1
    py_source = artifacts[0].py_path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(compile(py_source, str(artifacts[0].py_path), "exec"), namespace)
    return namespace, py_source


def test_math_maps_to_python_math_module(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Calculator
    {
        public static double Hypotenuse(double a, double b)
        {
            return Math.Sqrt(Math.Pow(a, 2.0) + Math.Pow(b, 2.0));
        }

        public static int Sign(double value) { return Math.Sign(value); }

        public static double Clamp(double value, double min, double max)
        {
            return Math.Clamp(value, min, max);
        }

        public static double Pi() { return Math.PI; }
        public static double E() { return Math.E; }
        public static double Round(double value) { return Math.Round(value); }
        public static double Floor(double value) { return Math.Floor(value); }
        public static double Ceiling(double value) { return Math.Ceiling(value); }
        public static double Max(double a, double b) { return Math.Max(a, b); }
        public static double Min(double a, double b) { return Math.Min(a, b); }
        public static double Abs(double value) { return Math.Abs(value); }
        public static double Exp(double value) { return Math.Exp(value); }
        public static double Log(double value) { return Math.Log(value); }
        public static double Sin(double value) { return Math.Sin(value); }
        public static double Cos(double value) { return Math.Cos(value); }
        public static double Tan(double value) { return Math.Tan(value); }
        public static double Truncate(double value) { return Math.Truncate(value); }
    }
    """
    namespace, py_source = _compile_and_exec(source, tmp_path)

    assert "import math" in py_source
    calculator = namespace["Calculator"]
    assert calculator.hypotenuse(3.0, 4.0) == 5.0
    assert calculator.sign(-2.0) == -1
    assert calculator.clamp(10.0, 0.0, 5.0) == 5.0
    assert calculator.pi() == math.pi
    assert calculator.e() == math.e
    assert calculator.round(2.5) == 2.0
    assert calculator.floor(2.9) == 2.0
    assert calculator.ceiling(2.1) == 3.0
    assert calculator.max(2.0, 3.0) == 3.0
    assert calculator.min(2.0, 3.0) == 2.0
    assert calculator.abs(-2.0) == 2.0
    assert calculator.exp(0.0) == 1.0
    assert calculator.log(math.e) == 1.0
    assert calculator.sin(0.0) == 0.0
    assert calculator.cos(0.0) == 1.0
    assert calculator.tan(0.0) == 0.0
    assert calculator.truncate(2.9) == 2.0


def test_string_collection_and_dictionary_members(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Toolkit
    {
        public static string Slice(string value) { return value.Substring(1, 3); }
        public static string Tail(string value) { return value.Substring(2); }
        public static int Find(string value, string needle) { return value.IndexOf(needle); }
        public static int FindLast(string value, string needle) { return value.LastIndexOf(needle); }
        public static string Describe(string value) { return value.ToString(); }
        public static bool Missing(string? value) { return String.IsNullOrEmpty(value); }

        public static void Arrange(List<int> values)
        {
            values.Insert(1, 2);
            values.RemoveAt(0);
            values.Sort();
            values.Reverse();
        }

        public static int Position(List<int> values, int item) { return values.IndexOf(item); }

        public static bool HasValue(Dict<string, int> values, int value)
        {
            return values.ContainsValue(value);
        }
    }
    """
    namespace, _ = _compile_and_exec(source, tmp_path)

    toolkit = namespace["Toolkit"]
    assert toolkit.slice("abcdef") == "bcd"
    assert toolkit.tail("abcdef") == "cdef"
    assert toolkit.find("abcabc", "bc") == 1
    assert toolkit.find_last("abcabc", "bc") == 4
    assert toolkit.describe("hello") == "hello"
    assert toolkit.missing(None) is True
    assert toolkit.missing("") is True
    assert toolkit.missing("x") is False

    values = [3, 1]
    toolkit.arrange(values)
    assert values == [2, 1]

    values = [10, 20, 30]
    assert toolkit.position(values, 20) == 1
    assert toolkit.has_value({"a": 1, "b": 2}, 2) is True
    assert toolkit.has_value({"a": 1, "b": 2}, 9) is False


def test_hashset_set_operations(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Sets
    {
        public static int UnionCount()
        {
            var values = new HashSet<int>();
            values.Add(1);
            values.Add(2);
            var other = new HashSet<int>();
            other.Add(2);
            other.Add(3);
            values.UnionWith(other);
            return values.Count;
        }

        public static int IntersectionCount()
        {
            var values = new HashSet<int>();
            values.Add(1);
            values.Add(2);
            values.Add(3);
            var other = new HashSet<int>();
            other.Add(2);
            other.Add(4);
            values.IntersectWith(other);
            return values.Count;
        }

        public static bool Subset()
        {
            var small = new HashSet<int>();
            small.Add(1);
            var large = new HashSet<int>();
            large.Add(1);
            large.Add(2);
            return small.IsSubsetOf(large);
        }

        public static bool Overlaps()
        {
            var left = new HashSet<int>();
            left.Add(1);
            var right = new HashSet<int>();
            right.Add(1);
            right.Add(2);
            return left.Overlaps(right);
        }

        public static int ExceptCount()
        {
            var values = new HashSet<int>();
            values.Add(1);
            values.Add(2);
            values.Add(3);
            var other = new HashSet<int>();
            other.Add(2);
            values.ExceptWith(other);
            return values.Count;
        }

        public static int SymmetricCount()
        {
            var values = new HashSet<int>();
            values.Add(1);
            values.Add(2);
            var other = new HashSet<int>();
            other.Add(2);
            other.Add(3);
            values.SymmetricExceptWith(other);
            return values.Count;
        }

        public static bool Superset()
        {
            var large = new HashSet<int>();
            large.Add(1);
            large.Add(2);
            var small = new HashSet<int>();
            small.Add(1);
            return large.IsSupersetOf(small);
        }

        public static bool EqualSets()
        {
            var left = new HashSet<int>();
            left.Add(1);
            left.Add(2);
            var right = new HashSet<int>();
            right.Add(2);
            right.Add(1);
            return left.SetEquals(right);
        }
    }
    """
    namespace, py_source = _compile_and_exec(source, tmp_path)

    assert "values: set[int] = set()" in py_source
    sets = namespace["Sets"]
    assert sets.union_count() == 3
    assert sets.intersection_count() == 1
    assert sets.subset() is True
    assert sets.overlaps() is True
    assert sets.except_count() == 2
    assert sets.symmetric_count() == 2
    assert sets.superset() is True
    assert sets.equal_sets() is True
