from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from psc import compile_sources

STDLIB = Path("stdlib/PythonSharp.Core.d.ps")


def _compile(source: str, tmp_path: Path) -> tuple[dict[str, object], str]:
    artifacts, diag = compile_sources(
        sources={"Properties.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
    )
    assert not diag.has_errors(), diag.format_all()
    assert len(artifacts) == 1
    py_source = artifacts[0].py_path.read_text(encoding="utf-8")
    module_name = f"_ps_property_{tmp_path.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, artifacts[0].py_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.__dict__, py_source


def test_static_properties_and_static_member_access(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Counter
    {
        public static int Count { get; set; } = 3;
        public static string Name { get; } = "counter";
        public static int Answer => 42;
        public static int Doubled { get { return Count * 2; } }
        public static int Calls = 0;

        public static void Increment()
        {
            Count = Count + 1;
            Calls = Calls + 1;
        }

        public static int Read() { return Count; }
        public static int Double(int value) { return value * 2; }
        public static int Compute() { return Double(Count); }
        public static int ReadAnswer() { return Answer; }
        public static int ReadDoubled() { return Doubled; }
        public static int ReadFromType() { return Counter.Answer; }
        public int ReadInstance() { return Count; }
        public int ComputeInstance() { return Double(Count); }
        public int ReadAnswerInstance() { return Answer; }
    }

    public class Probe
    {
        public static int Read() { return Counter.Answer; }
    }
    """
    namespace, py_source = _compile(source, tmp_path)

    assert "count: int = 3" in py_source
    assert "name: str = 'counter'" in py_source
    assert "@classmethod" in py_source
    assert "def count(self)" not in py_source
    assert "def answer(cls)" in py_source
    assert "def doubled(cls)" in py_source

    counter = namespace["Counter"]
    assert counter.count == 3
    assert counter.name == "counter"
    assert counter.answer() == 42
    assert counter.doubled() == 6
    assert counter.calls == 0
    assert counter.read_answer() == 42
    assert counter.read_doubled() == 6
    assert counter.read_from_type() == 42
    counter.increment()
    assert counter.count == 4
    assert counter.calls == 1
    assert counter.doubled() == 8
    assert counter.read() == 4
    assert counter.compute() == 8
    instance = counter()
    assert instance.read_instance() == 4
    assert instance.compute_instance() == 8
    assert instance.read_answer_instance() == 42
    assert namespace["Probe"].read() == 42


def test_static_auto_property_on_record_uses_classvar(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public record Counter(int Value)
    {
        public static int Count { get; set; } = 1;
        public static int Twice => Count * 2;
        public int DoubledValue => Value * 2;
    }
    """
    namespace, py_source = _compile(source, tmp_path)

    assert "ClassVar[int]" in py_source
    assert "from typing import ClassVar" in py_source
    assert "def twice(cls)" in py_source

    counter = namespace["Counter"]
    assert counter.count == 1
    assert counter.twice() == 2
    counter.count = 5
    assert counter.twice() == 10
    assert counter(7).value == 7
    assert counter(7).doubled_value == 14


def test_record_and_struct_instance_member_limits(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public record Person(string Name)
    {
        private int _age;
        public int Age { get; set; }
        public int Mutable { get { return _age; } set { _age = value; } }
    }

    public struct Point
    {
        public int X;
    }
    """
    _, diag = compile_sources(
        sources={"Properties.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
    )

    assert diag.has_errors()
    messages = "\n".join(d.message for d in diag.diagnostics)
    assert "Instance field 'Person._age' is not supported in records/structs" in messages
    assert "Instance auto-property 'Person.Age' is not supported in records/structs" in messages
    assert "Instance property 'Person.Mutable' has a setter" in messages
    assert "Instance field 'Point.X' is not supported in records/structs" in messages


def test_static_property_custom_setter_is_rejected(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Counter
    {
        public static int Count { get; set { } }
    }
    """
    _, diag = compile_sources(
        sources={"Properties.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
    )

    assert diag.has_errors()
    messages = "\n".join(d.message for d in diag.diagnostics)
    assert "Static property 'Counter.Count' has a custom setter" in messages


def test_static_property_private_setter_is_checked(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Counter
    {
        public static int Count { get; private set; }
    }

    public class User
    {
        public void Set() { Counter.Count = 1; }
    }
    """
    _, diag = compile_sources(
        sources={"Properties.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
    )

    assert diag.has_errors()
    messages = "\n".join(d.message for d in diag.diagnostics)
    assert "Counter.Count.set' is 'private'" in messages


def test_record_interpolated_string_qualifies_primary_constructor_members(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public record Person(string Name)
    {
        public string Greeting() => $"Hello {Name}";
    }
    """
    namespace, py_source = _compile(source, tmp_path)

    assert "f'Hello {self.name}'" in py_source
    assert namespace["Person"]("Ada").greeting() == "Hello Ada"
