from __future__ import annotations

from pathlib import Path
from psc import compile_sources

STDLIB = Path("stdlib/PythonSharp.Core.d.ps").read_text(encoding="utf-8")


def test_string_backed_enums(tmp_path: Path):
    source = """
namespace ModelEnums;

public enum TaskStatus : string
{
    Pending = "PENDING",
    InProgress = "IN_PROGRESS",
    Completed = "COMPLETED",
    Failed
}

public class StatusInspector
{
    public static string GetStatusName(TaskStatus s)
    {
        return s.ToString();
    }
}
"""
    artifacts, diagnostics = compile_sources(
        sources={"Enums.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="ModelEnums",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    py_code = artifacts[0].py_source

    assert "class TaskStatus(enum.StrEnum):" in py_code
    assert "Pending = 'PENDING'" in py_code or 'Pending = "PENDING"' in py_code
    assert "Failed = 'Failed'" in py_code or 'Failed = "Failed"' in py_code

    # Execute in Python
    env: dict[str, object] = {}
    exec(py_code, env)
    TaskStatus = env["TaskStatus"]
    assert getattr(TaskStatus, "Pending") == "PENDING"
    assert getattr(TaskStatus, "InProgress") == "IN_PROGRESS"
    assert getattr(TaskStatus, "Failed") == "Failed"
    assert isinstance(getattr(TaskStatus, "Pending"), str)


def test_structural_duck_typing(tmp_path: Path):
    source = """
namespace DuckTyping;

public interface IQuackable
{
    string Quack();
    int Loudness { get; set; }
}

public class MallardDuck
{
    public int Loudness { get; set; }

    public MallardDuck(int loudness)
    {
        Loudness = loudness;
    }

    public string Quack()
    {
        return "Quack!";
    }
}

public class DuckTester
{
    public static bool CheckQuackable(object obj)
    {
        return obj is IQuackable;
    }
}
"""
    artifacts, diagnostics = compile_sources(
        sources={"Duck.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="DuckTyping",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    py_code = artifacts[0].py_source

    assert "@runtime_checkable" in py_code
    assert "class IQuackable(Protocol):" in py_code
    assert "DuckTyping.IQuackable" in py_code  # MallardDuck's __ps_types__ includes structurally matched IQuackable

    env: dict[str, object] = {}
    exec(py_code, env)
    MallardDuck: type = env["MallardDuck"]  # type: ignore
    DuckTester: type = env["DuckTester"]  # type: ignore
    duck = MallardDuck(5)
    assert getattr(DuckTester, "check_quackable")(duck) is True


def test_relational_and_var_pattern_matching(tmp_path: Path):
    source = """
namespace PatternTest;

public class RelationalClassifier
{
    public static string Classify(int val)
    {
        switch (val)
        {
            case > 0:
                return "positive";
            case < 0:
                return "negative";
            default:
                return "zero";
        }
    }

    public static string ClassifyWithVar(int val)
    {
        switch (val)
        {
            case var x when x > 100:
                return "large";
            case var x when x > 0:
                return "positive";
            default:
                return "other";
        }
    }
}
"""
    artifacts, diagnostics = compile_sources(
        sources={"Pattern.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="PatternTest",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    py_code = artifacts[0].py_source

    env: dict[str, object] = {}
    exec(py_code, env)
    cls = env["RelationalClassifier"]
    assert getattr(cls, "classify")(10) == "positive"
    assert getattr(cls, "classify")(-5) == "negative"
    assert getattr(cls, "classify")(0) == "zero"
    assert getattr(cls, "classify_with_var")(500) == "large"
    assert getattr(cls, "classify_with_var")(42) == "positive"
    assert getattr(cls, "classify_with_var")(-1) == "other"


def test_list_and_slice_pattern_matching(tmp_path: Path):
    source = """
namespace ListPatternTest;

public class SequenceMatcher
{
    public static string MatchList(object items)
    {
        switch (items)
        {
            case [1, 2, 3]:
                return "one-two-three";
            case [var first, ..var rest]:
                return "head-tail";
            case []:
                return "empty";
            default:
                return "unknown";
        }
    }
}
"""
    artifacts, diagnostics = compile_sources(
        sources={"ListPattern.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="ListPatternTest",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    py_code = artifacts[0].py_source

    env: dict[str, object] = {}
    exec(py_code, env)
    matcher = env["SequenceMatcher"]
    assert getattr(matcher, "match_list")([1, 2, 3]) == "one-two-three"
    assert getattr(matcher, "match_list")([10, 20, 30, 40]) == "head-tail"
    assert getattr(matcher, "match_list")([]) == "empty"
    assert getattr(matcher, "match_list")("string") == "unknown"
