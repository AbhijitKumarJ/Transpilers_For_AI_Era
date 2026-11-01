from __future__ import annotations

from pathlib import Path

import pytest

from psc import LANGUAGE_VERSION, __version__
from psc.cli import build_parser, main


def test_build_parser_exposes_compiler_metadata() -> None:
    parser = build_parser()

    assert parser.prog == "psc"
    assert "PythonSharp" in parser.description


def test_main_without_arguments_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "usage: psc" in captured.out


def test_version_flag_prints_compiler_and_language_versions(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert f"psc {__version__} (language {LANGUAGE_VERSION})" in captured.out


def test_help_flag_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "usage: psc" in captured.out


def test_dump_ast_and_run_static_entrypoint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "Program.ps"
    source.write_text(
        """
        namespace Demo;

        using PythonSharp.Core;

        public static class Program
        {
            public static void Main()
            {
                Console.WriteLine("hello from psc");
            }
        }
        """.strip(),
        encoding="utf-8",
    )

    assert main(["dump-ast", str(source)]) == 0
    dump_output = capsys.readouterr().out
    assert "# === Module: demo.py" in dump_output
    assert "class Program" in dump_output
    assert "def main()" in dump_output

    assert main(["run", str(source), "-e", "Program.Main"]) == 0
    run_output = capsys.readouterr().out
    assert "hello from psc" in run_output


def test_check_directory_target_and_psproj_out_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "Hello.ps"
    source.write_text(
        """
        namespace Hello;
        public class Greeter { public int Answer() => 42; }
        """.strip(),
        encoding="utf-8",
    )
    assert main(["check", str(tmp_path)]) == 0
    assert "Check succeeded: 1 .ps file(s)" in capsys.readouterr().out

    project_file = tmp_path / "Hello.psproj"
    project_file.write_text(
        "<Project><PropertyGroup><AssemblyName>Hello</AssemblyName></PropertyGroup></Project>", encoding="utf-8"
    )
    out_dir = tmp_path / "out"
    assert main(["build", str(project_file), "--out-dir", str(out_dir), "--no-pyc"]) == 0
    assert out_dir.exists()
    assert "Build succeeded" in capsys.readouterr().out


def test_check_reports_no_sources_and_compile_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(tmp_path)]) == 1
    assert "No .ps source files" in capsys.readouterr().err

    bad = tmp_path / "Broken.ps"
    bad.write_text("namespace Broken; public class {", encoding="utf-8")
    assert main(["check", str(bad)]) == 1
    assert "PS000" in capsys.readouterr().err


def test_run_autodetects_static_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "Program.ps"
    source.write_text(
        """
        namespace Demo;
        using PythonSharp.Core;
        public static class Program
        {
            public static void Main() => Console.WriteLine("auto main");
        }
        """.strip(),
        encoding="utf-8",
    )
    assert main(["run", str(source)]) == 0
    assert "auto main" in capsys.readouterr().out


def test_build_caching_and_force(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "App.ps"
    source.write_text("namespace Demo; public class Greeter {}", encoding="utf-8")
    out_dir = tmp_path / "dist"

    # First build: cache miss
    assert main(["build", str(source), "-o", str(out_dir), "--no-pyc"]) == 0
    out1 = capsys.readouterr().out
    assert "Build succeeded" in out1

    # Second build with unchanged sources: cache hit
    assert main(["build", str(source), "-o", str(out_dir), "--no-pyc"]) == 0
    out2 = capsys.readouterr().out
    assert "Build is up to date" in out2

    # Third build with --force: forced rebuild
    assert main(["build", str(source), "-o", str(out_dir), "--no-pyc", "--force"]) == 0
    out3 = capsys.readouterr().out
    assert "Build succeeded" in out3
