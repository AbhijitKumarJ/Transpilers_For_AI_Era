from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.semantics import GlobalSymbolTable, SymbolCollector

STDLIB_SNIPPET = """
namespace PythonSharp.Core;

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


def test_circular_cross_file_type_resolution_and_virtual_namespaces() -> None:
    """
    Verifies that two .ps files in completely different physical folders can:
      1. Reference each other's types circularly (Order <-> OrderService)
      2. Aggregate into clean virtual namespace modules (`commerce/domain.py` & `commerce/services.py`)
      3. Resolve `PythonSharp.Core` generic primitive types (`List<Order>`, `Dict<int, Order>`)
    """
    file_order = """
    namespace Commerce.Domain;

    using Commerce.Services;

    public class Order
    {
        public int Id { get; private set; }
        public OrderService? AssignedService { get; set; }

        public Order(int id, OrderService? service = null)
        {
            Id = id;
            AssignedService = service;
        }
    }
    """

    file_service = """
    namespace Commerce.Services;

    using PythonSharp.Core;
    using Commerce.Domain;

    public class OrderService
    {
        private readonly Dict<int, Order> _orders = new Dict<int, Order>();

        public Order? FindOrder(int id) => _orders.GetOrDefault(id);
        public List<Order> GetAll() => new List<Order>();
    }
    """

    diag = DiagnosticEngine()
    unit_stdlib = Parser.from_source(
        STDLIB_SNIPPET, file_id=0, ps_filename="stdlib/PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_order = Parser.from_source(
        file_order, file_id=1, ps_filename="src/Features/Orders/Order.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_service = Parser.from_source(
        file_service, file_id=2, ps_filename="src/Infrastructure/OrderService.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable(default_assembly_name="CommerceApp")
    collector = SymbolCollector(symtab=symtab, diagnostics=diag)
    collector.collect_all([unit_stdlib, unit_order, unit_service])

    assert not diag.has_errors(), diag.format_all()

    # Check virtual namespace module path mapping
    assert unit_order.emitted_py_module_path == "commerce/domain.py"
    assert unit_service.emitted_py_module_path == "commerce/services.py"

    # Verify both circularly-dependent types are registered
    order_sym = symtab.types_by_qname["Commerce.Domain.Order"]
    service_sym = symtab.types_by_qname["Commerce.Services.OrderService"]

    # Order.AssignedService must resolve to Commerce.Services.OrderService? (`OrderService | None`)
    assigned_prop = order_sym.lookup_member("AssignedService")[0]
    assert assigned_prop.resolved_type is not None
    assert assigned_prop.resolved_type.qualified_name == "Commerce.Services.OrderService"
    assert assigned_prop.resolved_type.is_nullable is True
    assert assigned_prop.resolved_type.py_annotation == "OrderService | None"

    # OrderService._orders must resolve to `dict[int, Order]` (primitive type erasure!)
    orders_field = service_sym.lookup_member("_orders")[0]
    assert orders_field.resolved_type is not None
    assert orders_field.resolved_type.qualified_name == "PythonSharp.Core.Dict"
    assert orders_field.resolved_type.is_primitive is True
    assert orders_field.resolved_type.py_annotation == "dict[int, Order]"

    # OrderService.GetAll() return type must resolve to `list[Order]`
    get_all_method = service_sym.lookup_member("GetAll")[0]
    assert get_all_method.resolved_type is not None
    assert get_all_method.resolved_type.py_annotation == "list[Order]"


def test_detects_circular_class_inheritance_cycle() -> None:
    bad_source = """
    namespace CycleTest;

    public class Alpha : Beta { }
    public class Beta : Alpha { }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(bad_source, ps_filename="Cycle.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    collector = SymbolCollector(symtab=symtab, diagnostics=diag)
    collector.collect_all([unit])

    assert diag.has_errors()
    assert "Circular inheritance cycle detected" in diag.format_all()
