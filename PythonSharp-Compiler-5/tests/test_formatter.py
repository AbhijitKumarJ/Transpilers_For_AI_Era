from __future__ import annotations

import tempfile
from pathlib import Path

from psc.cli import main
from psc.formatter import format_code


def test_format_code_indentation_and_spacing():
    unformatted = """namespace TestApp;
using System;
public class MyClass {
public static void Main(string[] args){
if(args.Length > 0){
for(int i=0;i<args.Length;i++){
Console.WriteLine(args[i]);
}
}
}
}
"""
    formatted = format_code(unformatted, tab_size=4, insert_spaces=True)
    expected_lines = [
        "namespace TestApp;",
        "",
        "using System;",
        "",
        "public class MyClass",
        "{",
        "    public static void Main(string[] args)",
        "    {",
        "        if (args.Length > 0)",
        "        {",
        "            for (int i = 0; i < args.Length; i++)",
        "            {",
        "                Console.WriteLine(args[i]);",
        "            }",
        "        }",
        "    }",
        "}",
    ]
    assert formatted.strip() == "\n".join(expected_lines).strip()


def test_format_code_preserves_strings_and_comments():
    source = """namespace Demo;

public class Test
{
    // Important comment with { braces } and + - * operators
    public static void Run()
    {
        string msg = "hello + world; {not code}";
        string verbatim = @"multi
line + string
with {braces}";
        Console.WriteLine(msg);
    }
}
"""
    formatted = format_code(source, tab_size=4, insert_spaces=True)
    assert 'string msg = "hello + world; {not code}";' in formatted
    assert "@\"multi\nline + string\nwith {braces}\"" in formatted
    assert "// Important comment with { braces } and + - * operators" in formatted


def test_format_code_idempotent():
    source = """namespace Demo;

public class Test
{
    public static void Run()
    {
        int x = 10 + 20;
        Console.WriteLine(x);
    }
}
"""
    first_pass = format_code(source)
    second_pass = format_code(first_pass)
    assert first_pass == second_pass


def test_cli_format(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        file_path = tmp_path / "Unformatted.ps"
        file_path.write_text("namespace Demo;public class Foo{public static void Bar(){}}", encoding="utf-8")

        # Test check mode
        code = main(["format", str(file_path), "--check"])
        assert code == 1

        # Test in-place formatting
        code = main(["format", str(file_path)])
        assert code == 0

        # After formatting, check mode should return 0
        code = main(["format", str(file_path), "--check"])
        assert code == 0

        content = file_path.read_text(encoding="utf-8")
        assert "namespace Demo;" in content
        assert "public class Foo" in content
        assert "{" in content
