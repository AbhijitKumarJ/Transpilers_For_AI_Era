from __future__ import annotations

from pathlib import Path

from psc import compile_sources

STDLIB = Path("stdlib/PythonSharp.Core.d.ps")


def _compile_and_exec(source: str, tmp_path: Path) -> tuple[dict[str, object], str]:
    artifacts, diag = compile_sources(
        sources={"Exceptions.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
    )
    assert not diag.has_errors(), diag.format_all()
    assert len(artifacts) == 1
    py_source = artifacts[0].py_path.read_text(encoding="utf-8")
    namespace: dict[str, object] = {}
    exec(compile(py_source, str(artifacts[0].py_path), "exec"), namespace)
    return namespace, py_source


def test_custom_exception_inherits_python_exception_and_guarded_catch_falls_through(
    tmp_path: Path,
) -> None:
    source = """
    namespace Demo;

    public class OrderError : Exception
    {
        public OrderError(string message) { }
    }

    public class Worker
    {
        public string Run(bool flag)
        {
            try
            {
                throw new OrderError("bad");
            }
            catch (OrderError ex) when (flag)
            {
                return "guarded";
            }
            catch (Exception ex)
            {
                return "fallback:" + ex.Message;
            }
        }
    }
    """
    namespace, _ = _compile_and_exec(source, tmp_path)

    order_error = namespace["OrderError"]
    assert isinstance(order_error, type)
    assert issubclass(order_error, Exception)

    worker = namespace["Worker"]()
    assert worker.run(True) == "guarded"
    assert worker.run(False) == "fallback:bad"


def test_core_exception_names_map_to_python_builtins(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Worker
    {
        public string Run(string kind)
        {
            try
            {
                if (kind == "argument") { throw new ArgumentException("bad argument"); }
                throw new InvalidOperationException("bad state");
            }
            catch (ArgumentException ex)
            {
                return "argument";
            }
            catch (InvalidOperationException ex)
            {
                return "state";
            }
        }
    }
    """
    namespace, py_source = _compile_and_exec(source, tmp_path)

    assert "raise ValueError('bad argument')" in py_source
    assert "raise RuntimeError('bad state')" in py_source
    worker = namespace["Worker"]()
    assert worker.run("argument") == "argument"
    assert worker.run("state") == "state"


def test_untyped_catch_uses_base_exception(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Worker
    {
        public string Run()
        {
            try
            {
                throw new SystemExit("stop");
            }
            catch
            {
                return "caught";
            }
        }
    }
    """
    namespace, py_source = _compile_and_exec(source, tmp_path)

    assert "except BaseException:" in py_source
    assert namespace["Worker"]().run() == "caught"


def test_bare_throw_outside_catch_is_rejected(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Worker
    {
        public void Run()
        {
            throw;
        }
    }
    """
    _, diag = compile_sources(
        sources={"Exceptions.ps": source},
        out_dir=tmp_path / "dist",
        stdlib_source=STDLIB.read_text(encoding="utf-8"),
    )

    assert diag.has_errors()
    assert "only valid inside a catch" in diag.format_all()


def test_bare_throw_rethrows_to_outer_catch(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Worker
    {
        public string Run()
        {
            try
            {
                try
                {
                    throw new Exception("bad");
                }
                catch (Exception ex)
                {
                    throw;
                }
            }
            catch (Exception ex)
            {
                return "recaught";
            }
        }
    }
    """
    namespace, _ = _compile_and_exec(source, tmp_path)

    assert namespace["Worker"]().run() == "recaught"


def test_untyped_guard_falls_through_and_finally_runs(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Worker
    {
        public string Run(bool flag)
        {
            string result = "start";
            try
            {
                try
                {
                    throw new Exception("bad");
                }
                catch when (flag)
                {
                    result = "guarded";
                }
                catch (Exception ex)
                {
                    result = "fallback";
                }
            }
            finally
            {
                result += "-finally";
            }
            return result;
        }
    }
    """
    namespace, _ = _compile_and_exec(source, tmp_path)

    worker = namespace["Worker"]()
    assert worker.run(True) == "guarded-finally"
    assert worker.run(False) == "fallback-finally"


def test_additional_core_exception_names_map_to_python_builtins(tmp_path: Path) -> None:
    source = """
    namespace Demo;

    public class Worker
    {
        public string Run(string kind)
        {
            try
            {
                if (kind == "null") { throw new NullReferenceException("null"); }
                if (kind == "file") { throw new FileNotFoundException("missing"); }
                if (kind == "format") { throw new FormatException("format"); }
                throw new UnauthorizedAccessException("permission");
            }
            catch (NullReferenceException) { return "null"; }
            catch (FileNotFoundException) { return "file"; }
            catch (FormatException) { return "format"; }
            catch (UnauthorizedAccessException) { return "permission"; }
        }

        public string CatchAsIo()
        {
            try
            {
                throw new FileNotFoundException("missing");
            }
            catch (IOException)
            {
                return "io";
            }
        }
    }
    """
    namespace, _ = _compile_and_exec(source, tmp_path)

    worker = namespace["Worker"]()
    assert worker.run("null") == "null"
    assert worker.run("file") == "file"
    assert worker.run("format") == "format"
    assert worker.run("other") == "permission"
    assert worker.catch_as_io() == "io"
