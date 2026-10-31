from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from typing import Any

from psc.codegen import NamespacePackagePlanner, PythonAstBuilder
from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.project import load_project
from psc.semantics import GlobalSymbolTable, analyze_compilation_units

STDLIB_STUB = """
namespace PythonSharp.Core;

[MapsTo("contextlib.AbstractContextManager")]
public interface IDisposable
{
    [MapsTo("dispose")]
    void Dispose();
}

[MapsTo("contextlib.AbstractAsyncContextManager")]
public interface IAsyncDisposable
{
    [MapsTo("dispose_async")]
    void DisposeAsync();
}

[MapsTo("list")]
[RuntimeType("list")]
public primitive class List<T> : IEnumerable<T>
{
    [InlineTemplate("[]")]
    public extern List();

    [MapsTo("append")]
    public extern void Add(T item);
}

[MapsTo("dict")]
[RuntimeType("dict")]
public primitive class Dict<TKey, TValue>
{
    [InlineTemplate("{}")]
    public extern Dict();

    [MapsTo("get")]
    public extern TValue? GetOrDefault(TKey key, TValue? defaultValue = default);

    [InlineTemplate("({0} in {self})")]
    public extern bool ContainsKey(TKey key);

    [MapsTo("values")]
    public extern IEnumerable<TValue> Values();

    [MapsTo("clear")]
    public extern void Clear();
}

[MapsTo("collections.abc.Iterable")]
public primitive interface IEnumerable<T>
{
    [LinqStage("Filter")]
    IEnumerable<T> Where(Func<T, bool> predicate);

    [LinqStage("Map")]
    IEnumerable<TResult> Select<TResult>(Func<T, TResult> selector);

    [LinqStage("TerminalList")]
    List<T> ToList();
}
"""


def test_end_to_end_ast_lowering_and_runtime_execution_of_order_cache() -> None:
    """
    Compiles `OrderService.ps` through Pass 1 -> Pass 2 -> Pass 3A (`PythonAstBuilder`),
    verifies the emitted Python 3.11+ source code structure, and executes the compiled
    module on CPython 3.11+ to verify:
      - `@dataclass(slots=True, frozen=True)` on `Order`
      - `__slots__ = ('_store', '_audit_tag')` (zero `__dict__` allocation on `OrderCache`)
      - `__ps_types__` O(1) nominal interface checking (`cache is IAuditable`)
      - `@overload` runtime dispatcher on `put(Order)` vs `put(int, Decimal)`
      - Fused list comprehension in `get_active_ids()`
      - `using var cache = ...` lowering to `with OrderCache(...) as cache:` (`__enter__`/`__exit__`)
    """
    source = """
    namespace Commerce.Services;

    using PythonSharp.Core;

    public interface IAuditable { string AuditTag { get; } }

    public record Order(int Id, decimal Total, bool IsActive);

    public class OrderCache : IAuditable, IDisposable
    {
        private readonly Dict<int, Order> _store = new Dict<int, Order>();
        public string AuditTag { get; private set; }

        public OrderCache(string tag) => AuditTag = tag;

        public void Put(Order order) => _store[order.Id] = order;
        public void Put(int id, decimal total) => _store[id] = new Order(id, total, true);

        public bool IsAuditTarget(object candidate) => candidate is IAuditable;

        public List<int> GetActiveIds(decimal minTotal = 0.0m)
        {
            return _store.Values()
                .Where(o => o.IsActive && o.Total >= minTotal)
                .Select(o => o.Id)
                .ToList();
        }

        public void Dispose() => _store.Clear();
    }
    """
    diag = DiagnosticEngine()
    unit_std = Parser.from_source(
        STDLIB_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_srv = Parser.from_source(
        source, file_id=1, ps_filename="Services/OrderCache.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable(default_assembly_name="CommerceApp")
    analyze_compilation_units([unit_std, unit_srv], symtab, diag)
    assert not diag.has_errors(), diag.format_all()

    planner = NamespacePackagePlanner(symtab)
    planned_modules = planner.plan_modules()
    assert "commerce/services.py" in planned_modules

    builder = PythonAstBuilder(symtab)
    py_mod_ast = builder.build_module(planned_modules["commerce/services.py"])
    py_source = ast.unparse(py_mod_ast)

    # 1. Verify structural Python 3.11+ constructs in emitted code
    assert "from __future__ import annotations" in py_source
    assert "@dataclass(slots=True, frozen=True)" in py_source
    assert "__slots__ = ('_store', '_audit_tag')" in py_source
    assert "@overload" in py_source
    assert "[o.id for o in self._store.values() if o.is_active and o.total >= min_total]" in py_source
    assert "def __enter__(self) -> OrderCache:" in py_source
    assert (
        "def __exit__(self, exc_type: object | None, exc_val: object | None, exc_tb: object | None) -> None:"
        in py_source
    )

    # 2. Execute the emitted Python AST in CPython and test runtime behavior!
    ns_globals: dict[str, Any] = {}
    code_obj = compile(py_mod_ast, filename="Services/OrderCache.ps", mode="exec")
    exec(code_obj, ns_globals)

    OrderCls = ns_globals["Order"]
    OrderCacheCls = ns_globals["OrderCache"]

    with OrderCacheCls("PROD-AUDIT") as cache:
        # Confirm `__slots__` eliminates per-instance `__dict__`
        assert not hasattr(cache, "__dict__")
        assert cache.audit_tag == "PROD-AUDIT"
        assert cache.is_audit_target(cache) is True
        assert cache.is_audit_target("not-auditable") is False

        # Test Overload Variant 0: `Put(Order)`
        cache.put(OrderCls(101, Decimal("25.50"), True))
        cache.put(OrderCls(102, Decimal("5.00"), False))

        # Test Overload Variant 1: `Put(int, decimal)`
        cache.put(103, Decimal("99.95"))

        # Test fused LINQ comprehension `GetActiveIds(minTotal)`
        assert cache.get_active_ids() == [101, 103]
        assert cache.get_active_ids(Decimal("50.00")) == [103]

    # Exiting the `with` block automatically invoked `Dispose()` -> `_store.clear()`!
    assert cache.get_active_ids() == []


def test_multidimensional_tensor_slicing_and_walrus_null_safety_lowering() -> None:
    """
    Verifies Pass 3A lowering for:
      - `tensor[1..5, ^2.., ::2]` -> `tensor[1:5, -2:, ::2]`
      - `user?.Profile?.Name ?? "Guest"` -> walrus-guarded `IfExp` that does NOT
        treat empty string `""` or `0` as null!
    """
    source = """
    namespace ML.Pipelines;

    public record Profile(string? Name);
    public record User(Profile? Profile);

    public class Slicer
    {
        public object Slice1D(object seq) => seq[1..5:2];
        public object FromEnd(object seq) => seq[^1];
        public string ResolveName(User? user) => user?.Profile?.Name ?? "Guest";
        public int CoalesceZero(int? count) => count ?? 42;
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Slicer.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit], symtab, diag)
    assert not diag.has_errors(), diag.format_all()

    planned = NamespacePackagePlanner(symtab).plan_modules()["ml/pipelines.py"]
    py_mod_ast = PythonAstBuilder(symtab).build_module(planned)
    py_source = ast.unparse(py_mod_ast)

    assert "seq[1:5:2]" in py_source
    assert "seq[-1]" in py_source

    ns_globals: dict[str, Any] = {}
    exec(compile(py_mod_ast, filename="Slicer.ps", mode="exec"), ns_globals)

    ProfileCls = ns_globals["Profile"]
    UserCls = ns_globals["User"]
    slicer = ns_globals["Slicer"]()

    assert slicer.slice_1d([0, 1, 2, 3, 4, 5, 6]) == [1, 3]
    assert slicer.from_end([10, 20, 30]) == 30
    assert slicer.resolve_name(None) == "Guest"
    assert slicer.resolve_name(UserCls(None)) == "Guest"
    assert slicer.resolve_name(UserCls(ProfileCls(None))) == "Guest"
    assert slicer.resolve_name(UserCls(ProfileCls("Ada"))) == "Ada"
    # Crucial null-safety test: empty string `""` and `0` are NOT null (`is not None`)!
    assert slicer.resolve_name(UserCls(ProfileCls(""))) == ""
    assert slicer.coalesce_zero(0) == 0
    assert slicer.coalesce_zero(None) == 42


def test_build_enum_interface_records_properties_indexers_and_context_managers() -> None:
    source = """
    namespace Shapes;

    using PythonSharp.Core;

    public interface IShape { int Area { get; } }

    public enum Color { Red, Green }

    public record Point(int X, int Y);

    public record struct Pair(int A, int B);

    public class Square : IShape, IDisposable
    {
        public int Side { get; private set; }
        public Color Tint { get; set; } = Color.Red;
        public int Area => Side * Side;

        public int this[int index]
        {
            get => Side + index;
            set => Side = value - index;
        }

        public Square(int side) { Side = side; }

        public void Dispose() { }
    }

    public class AsyncSquare : IAsyncDisposable
    {
        public void DisposeAsync() { }
    }

    public class Parent
    {
        public int Value;
        public Parent(int value) { Value = value; }
    }

    public class Child : Parent
    {
        public Child(int value) : base(value) { }
        public Child(string value) : this(value.Length) { }
        public int Score(int value) => value;
        public int Score(string value) => value.Length;
    }
    """
    diagnostics = DiagnosticEngine()
    unit_std = Parser.from_source(
        STDLIB_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diagnostics
    ).parse_compilation_unit()
    unit_shapes = Parser.from_source(
        source, file_id=1, ps_filename="Shapes.ps", diagnostics=diagnostics
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable(default_assembly_name="ShapesApp")
    analyze_compilation_units([unit_std, unit_shapes], symtab, diagnostics)
    assert not diagnostics.has_errors(), diagnostics.format_all()

    planned = NamespacePackagePlanner(symtab).plan_modules()["shapes.py"]
    module = PythonAstBuilder(symtab).build_module(planned)
    compiled = compile(module, filename="Shapes.ps", mode="exec")
    rendered = ast.unparse(module)

    assert "class IShape(Protocol)" in rendered
    assert "class Color(enum.IntEnum)" in rendered
    assert "@dataclass(slots=True, frozen=True)" in rendered
    assert "@dataclass(slots=True)" in rendered
    assert "@property" in rendered
    assert "@area.setter" not in rendered
    assert "def __getitem__(self, index: int) -> int:" in rendered
    assert "def __setitem__(self, index: int, value: int) -> None:" in rendered
    assert "def __enter__(self)" in rendered
    assert "def __exit__(" in rendered
    assert "async def __aenter__(self)" in rendered
    assert "async def __aexit__(" in rendered
    assert "await self.dispose_async()" in rendered
    assert "super().__init__(value)" in rendered
    assert "self.__init__(value.length)" in rendered
    assert "__ps_types__" in rendered

    namespace: dict[str, Any] = {}
    exec(compiled, namespace)
    square = namespace["Square"](4)
    assert square.area == 16
    assert square[3] == 7
    square[3] = 10
    assert square.side == 7
    assert namespace["Color"].Red.value == 0
    assert namespace["Point"](1, 2).x == 1
    child = namespace["Child"](3)
    assert child.value == 3
    assert child.score(7) == 7


def test_enum_implicit_values_follow_the_previous_member() -> None:
    source = """
    namespace Enums;

    public enum Status
    {
        Draft = 1,
        Published,
        Paused = 10,
        Archived,
    }
    """
    diagnostics = DiagnosticEngine()
    unit_std = Parser.from_source(
        STDLIB_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diagnostics
    ).parse_compilation_unit()
    unit_enums = Parser.from_source(
        source, file_id=1, ps_filename="Enums.ps", diagnostics=diagnostics
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable(default_assembly_name="EnumsApp")
    analyze_compilation_units([unit_std, unit_enums], symtab, diagnostics)
    assert not diagnostics.has_errors(), diagnostics.format_all()

    planned = NamespacePackagePlanner(symtab).plan_modules()["enums.py"]
    module = PythonAstBuilder(symtab).build_module(planned)
    namespace: dict[str, Any] = {}
    exec(compile(module, filename="Enums.ps", mode="exec"), namespace)

    status = namespace["Status"]
    assert status.Draft.value == 1
    assert status.Published.value == 2
    assert status.Paused.value == 10
    assert status.Archived.value == 11


def test_every_commerce_fixture_module_builds_and_compiles() -> None:
    project = load_project(
        Path("tests/fixtures/commerce_sample/Commerce.psproj"),
        stdlib_dir=Path("stdlib"),
    )
    diagnostics = DiagnosticEngine()
    units = [
        Parser.from_source(
            path.read_text(encoding="utf-8"),
            file_id=file_id,
            ps_filename=path.name,
            diagnostics=diagnostics,
        ).parse_compilation_unit()
        for file_id, path in enumerate(project.all_input_files())
    ]
    symtab = GlobalSymbolTable(default_assembly_name=project.project_name)
    analyze_compilation_units(units, symtab, diagnostics)
    assert not diagnostics.has_errors(), diagnostics.format_all()

    planned_modules = NamespacePackagePlanner(symtab).plan_modules()
    assert set(planned_modules) == {"commerce/domain.py", "commerce/services.py"}
    for module_name, planned in planned_modules.items():
        module = PythonAstBuilder(symtab).build_module(planned)
        compile(module, filename=module_name, mode="exec")
