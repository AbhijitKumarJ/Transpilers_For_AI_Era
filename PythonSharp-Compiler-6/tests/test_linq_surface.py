from __future__ import annotations

from pathlib import Path

from psc import compile_sources

STDLIB = Path("stdlib/PythonSharp.Core.d.ps")


def _compile_and_exec(source: str, tmp_path: Path) -> tuple[dict[str, object], str]:
    artifacts, diag = compile_sources(
        sources={"LinqSurface.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
    )
    assert not diag.has_errors(), diag.format_all()
    assert len(artifacts) == 1
    py_source = artifacts[0].py_path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(compile(py_source, str(artifacts[0].py_path), "exec"), namespace)
    return namespace, py_source


def test_linq_surface_operators_and_lazy_fallback(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class LinqOps
    {
        public static List<int> TakeSkip(List<int> xs) { return xs.Skip(1).Take(2).ToList(); }
        public static List<int> TakeNegative(List<int> xs) { return xs.Take(-1).ToList(); }
        public static List<int> SkipNegative(List<int> xs) { return xs.Skip(-1).ToList(); }
        public static List<int> Sorted(List<int> xs) { return xs.OrderBy(x => x).ToList(); }
        public static List<int> SortedDesc(List<int> xs) { return xs.OrderByDescending(x => x).ToList(); }
        public static List<int> ThenBy(List<int> xs) { return xs.OrderBy(x => x % 2).ThenBy(x => x).ToList(); }
        public static List<int> ThenByDesc(List<int> xs) { return xs.OrderBy(x => x % 2).ThenByDescending(x => x).ToList(); }
        public static List<int> Reordered(List<int> xs)
        {
            return xs.OrderBy(x => x % 2).ThenBy(x => x).OrderByDescending(x => x).ToList();
        }
        public static List<int> Distinct(List<int> xs) { return xs.Distinct().ToList(); }
        public static List<int> Concat(List<int> xs, List<int> ys) { return xs.Concat(ys).ToList(); }
        public static bool Has(List<int> xs, int value) { return xs.Where(x => x > 1).Contains(value); }
        public static int? Last(List<int> xs) { return xs.LastOrDefault(); }
        public static int? LastEven(List<int> xs) { return xs.LastOrDefault(x => x % 2 == 0); }
        public static double Average(List<int> xs) { return xs.Average(); }
        public static int Min(List<int> xs) { return xs.Min(); }
        public static int Max(List<int> xs) { return xs.Max(); }
        public static List<int> Lazy(List<int> xs)
        {
            return xs.Where(x => x > 1).Take(2).Select(x => x * 10).ToList();
        }
    }
    """
    namespace, py_source = _compile_and_exec(source, tmp_path)

    assert "import itertools" in py_source
    assert "import statistics" in py_source
    assert "itertools.islice" in py_source
    assert "itertools.chain" in py_source
    assert "dict.fromkeys" in py_source
    assert "statistics.fmean" in py_source
    assert " in filter(" in py_source

    ops = namespace["LinqOps"]
    assert ops.take_skip([1, 2, 3, 4]) == [2, 3]
    assert ops.take_negative([1, 2, 3]) == []
    assert ops.skip_negative([1, 2, 3]) == [1, 2, 3]
    assert ops.sorted([3, 1, 2]) == [1, 2, 3]
    assert ops.sorted_desc([3, 1, 2]) == [3, 2, 1]
    assert ops.then_by([3, 1, 4, 2]) == [2, 4, 1, 3]
    assert ops.then_by_desc([3, 1, 4, 2]) == [4, 2, 3, 1]
    assert ops.reordered([3, 1, 4, 2]) == [4, 3, 2, 1]
    assert ops.distinct([1, 2, 1, 3, 2]) == [1, 2, 3]
    assert ops.concat([1, 2], [3]) == [1, 2, 3]
    assert ops.has([1, 2, 3], 3) is True
    assert ops.has([1, 2, 3], 1) is False
    assert ops.last([]) is None
    assert ops.last([1, 2, 3]) == 3
    assert ops.last_even([]) is None
    assert ops.last_even([1, 2, 3, 4]) == 4
    assert ops.average([1, 2, 3]) == 2.0
    assert ops.min([3, 1, 2]) == 1
    assert ops.max([3, 1, 2]) == 3
    assert ops.lazy([1, 2, 3, 4]) == [20, 30]


def test_linq_var_does_not_emit_unresolved_generic_annotations(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class LinqOps
    {
        public static List<string> Names(List<string> xs)
        {
            var ordered = xs.OrderBy(x => x).Select(x => x).ToList();
            return ordered;
        }
    }
    """
    namespace, py_source = _compile_and_exec(source, tmp_path)

    assert "TResult" not in py_source
    assert "ordered: list[" not in py_source
    assert namespace["LinqOps"].names(["b", "a"]) == ["a", "b"]


def test_linq_lazy_fallback_for_materializers_and_terminals(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class LinqOps
    {
        public static Dict<int, int> ToDict(List<int> xs)
        {
            return xs.OrderBy(x => x).ToDict(x => x, x => x * 2);
        }

        public static int Count(List<int> xs) { return xs.Skip(1).Count(); }
        public static bool Any(List<int> xs) { return xs.Take(2).Any(x => x > 1); }
        public static bool All(List<int> xs) { return xs.Take(2).All(x => x > 0); }
        public static int? First(List<int> xs) { return xs.OrderByDescending(x => x).FirstOrDefault(); }
        public static HashSet<int> Set(List<int> xs) { return xs.Take(2).ToHashSet(); }
        public static bool AnyNoPredicate(List<int> xs) { return xs.Take(2).Any(); }
        public static int CountTake(List<int> xs) { return xs.Take(2).Count(); }
        public static int SumTake(List<int> xs) { return xs.Take(2).Sum(); }
        public static int MinTake(List<int> xs) { return xs.Take(2).Min(); }
        public static int MaxTake(List<int> xs) { return xs.Take(2).Max(); }
        public static int? FirstEven(List<int> xs) { return xs.Take(3).FirstOrDefault(x => x % 2 == 0); }
        public static List<int> Flat(List<int> xs) { return xs.Take(2).SelectMany(x => xs).ToList(); }
    }
    """
    namespace, py_source = _compile_and_exec(source, tmp_path)

    assert "dict(map(" in py_source
    assert "len(list(" in py_source
    assert "any(map(" in py_source
    assert "all(map(" in py_source
    assert "next(iter(" in py_source
    assert "set(itertools.islice(" in py_source
    assert "itertools.chain.from_iterable(" in py_source
    assert "any(itertools.islice(" in py_source
    assert "len(list(" in py_source
    assert "sum(itertools.islice(" in py_source
    assert "min(itertools.islice(" in py_source
    assert "max(itertools.islice(" in py_source
    assert "next(iter(filter(" in py_source

    ops = namespace["LinqOps"]
    assert ops.to_dict([3, 1, 2]) == {1: 2, 2: 4, 3: 6}
    assert ops.count([1, 2, 3]) == 2
    assert ops.any([1, 2, 3]) is True
    assert ops.any([0, 0]) is False
    assert ops.all([1, 2]) is True
    assert ops.all([0, 1]) is False
    assert ops.first([1, 3, 2]) == 3
    assert ops.first([]) is None
    assert ops.set([1, 1, 2, 3]) == {1}
    assert ops.any_no_predicate([1, 2]) is True
    assert ops.any_no_predicate([]) is False
    assert ops.count_take([1, 2, 3]) == 2
    assert ops.sum_take([1, 2, 3]) == 3
    assert ops.min_take([3, 1, 2]) == 1
    assert ops.max_take([3, 1, 2]) == 3
    assert ops.first_even([1, 3, 4, 5]) == 4
    assert ops.first_even([1, 3, 5]) is None
    assert ops.flat([1, 2, 3]) == [1, 2, 3, 1, 2, 3]
