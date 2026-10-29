from __future__ import annotations

from pathlib import Path

from psc import compile_sources

STDLIB = Path("stdlib/PythonSharp.Core.d.ps").read_text(encoding="utf-8")


def test_python_decorator_lowering(tmp_path: Path) -> None:
    source = """
    namespace WebApp;

    using PythonSharp.Core;

    public class ApiController
    {
        [PythonDecorator("app.route('/health', methods=['GET'])")]
        public string HealthCheck() => "OK";

        [app.Post("/login")]
        public string Login(string username) => $"Welcome {username}";
    }
    """
    artifacts, diagnostics = compile_sources(
        sources={"WebApp/ApiController.ps": source},
        out_dir=tmp_path / "web_dist",
        stdlib_source=STDLIB,
        assembly_name="WebApp",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    code = artifacts[0].py_source

    assert "@app.route('/health', methods=['GET'])" in code
    assert "@app.post('/login')" in code


def test_schema_model_pydantic_lowering(tmp_path: Path) -> None:
    source = """
    namespace Models;

    using PythonSharp.Core;

    [SchemaModel]
    public class UserDto
    {
        public int Id { get; set; }
        public string Username { get; set; } = "anonymous";
        public bool IsAdmin { get; set; } = false;

        public string DisplayName() => $"{Username} (#{Id})";
    }

    [SchemaModel]
    public record ItemDto(int ItemId, string Title, float Price = 0.0);
    """
    artifacts, diagnostics = compile_sources(
        sources={"Models/Schemas.ps": source},
        out_dir=tmp_path / "model_dist",
        stdlib_source=STDLIB,
        assembly_name="Models",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    code = artifacts[0].py_source

    # Check Pydantic BaseModel import
    assert "from pydantic import BaseModel" in code

    # Check UserDto inherits BaseModel and has no __slots__
    assert "class UserDto(BaseModel):" in code
    assert "__slots__" not in code

    # Check field annotations
    assert "id: int" in code
    assert "username: str = 'anonymous'" in code or 'username: str = "anonymous"' in code
    assert "is_admin: bool = False" in code

    # Check ItemDto record has no @dataclass and inherits BaseModel
    assert "@dataclass" not in code
    assert "class ItemDto(BaseModel):" in code
    assert "item_id: int" in code
    assert "title: str" in code
    assert "price: float = 0.0" in code


def test_kwargs_parameter_lowering(tmp_path: Path) -> None:
    source = """
    namespace Utils;

    using PythonSharp.Core;

    public class Logger
    {
        public void Log(string message, [KwArgs] Dict<string, object> metadata)
        {
        }
    }
    """
    artifacts, diagnostics = compile_sources(
        sources={"Utils/Logger.ps": source},
        out_dir=tmp_path / "utils_dist",
        stdlib_source=STDLIB,
        assembly_name="Utils",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    code = artifacts[0].py_source

    # Check that [KwArgs] lowered to **metadata
    assert "def log(self, message: str, **metadata: dict[str, object]) -> None:" in code


def test_generators_and_yield_statements(tmp_path: Path) -> None:
    source = """
    namespace Iterators;

    using PythonSharp.Core;

    public class Fibonacci
    {
        public IEnumerable<int> Generate(int max)
        {
            int a = 0;
            int b = 1;
            while (a < max)
            {
                yield return a;
                int temp = a;
                a = b;
                b = temp + b;
            }
            yield break;
        }
    }
    """
    artifacts, diagnostics = compile_sources(
        sources={"Iterators/Fibonacci.ps": source},
        out_dir=tmp_path / "iter_dist",
        stdlib_source=STDLIB,
        assembly_name="Iterators",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    code = artifacts[0].py_source

    assert "yield a" in code
    assert "return" in code

    # Execute generator at runtime
    scope: dict[str, object] = {}
    exec(artifacts[0].code_object, scope)
    fib_cls = scope["Fibonacci"]
    fib_instance = fib_cls()  # type: ignore[operator]
    gen = fib_instance.generate(20)  # type: ignore[attr-defined]
    values = list(gen)
    assert values == [0, 1, 1, 2, 3, 5, 8, 13]


def test_async_streams_and_async_context_managers(tmp_path: Path) -> None:
    source = """
    namespace AsyncStream;

    using PythonSharp.Core;

    public class AsyncResource : IAsyncDisposable
    {
        public Task DisposeAsync()
        {
            return Task.Delay(1);
        }

        public async Task ProcessAsync()
        {
            await using var res = new AsyncResource();
        }
    }
    """
    artifacts, diagnostics = compile_sources(
        sources={"AsyncStream/AsyncResource.ps": source},
        out_dir=tmp_path / "async_dist",
        stdlib_source=STDLIB,
        assembly_name="AsyncStream",
        emit_pyc=False,
    )
    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert len(artifacts) == 1
    code = artifacts[0].py_source

    # Check synthesized __aenter__ and __aexit__
    assert "async def __aenter__(self)" in code
    assert "async def __aexit__(self" in code
    assert "await self.dispose_async()" in code
    assert "async with AsyncResource() as res:" in code
