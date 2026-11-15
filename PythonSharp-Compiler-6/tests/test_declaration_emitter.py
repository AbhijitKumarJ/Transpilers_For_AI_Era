from __future__ import annotations

from pathlib import Path

from psc import compile_sources

STDLIB = Path("stdlib/PythonSharp.Core.d.ps").read_text(encoding="utf-8")


def test_declaration_emitter_basic(tmp_path: Path) -> None:
    source = """
namespace DemoLib;

using PythonSharp.Core;

public class MathHelper
{
    public int Offset;
    public string Name { get; set; }

    public MathHelper(int offset)
    {
        Offset = offset;
    }

    public static int Add(int a, int b)
    {
        return a + b;
    }

    public void DoSomething(string text)
    {
        Console.WriteLine(text);
    }
}

public enum Color
{
    Red,
    Green,
    Blue = 10
}
"""
    artifacts, diagnostics = compile_sources(
        sources={"DemoLib/MathHelper.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB,
        assembly_name="DemoLib",
        emit_pyc=False,
    )

    assert not diagnostics.has_errors()
    assert len(artifacts) >= 1
    art = artifacts[0]
    assert art.d_ps_path is not None
    assert art.d_ps_path.exists()

    d_ps = art.d_ps_path.read_text(encoding="utf-8")
    assert "namespace DemoLib;" in d_ps
    assert "public class MathHelper" in d_ps
    assert "public static extern int Add(int a, int b);" in d_ps
    assert "public extern void DoSomething(string text);" in d_ps
    assert "public extern MathHelper(int offset);" in d_ps
    assert "public extern string Name { get; set; }" in d_ps
    assert "public int Offset;" in d_ps
    assert "public enum Color" in d_ps
    assert "Red," in d_ps
    assert "Blue = 10," in d_ps
