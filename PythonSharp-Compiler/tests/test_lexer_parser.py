from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import (
    AccessMod,
    ExprKind,
    LiteralKind,
    LocalVarStmt,
    MethodDecl,
    Parser,
    PropertyDecl,
    TypeKind,
    UsingResourceStmt,
)


def test_parse_core_stdlib_primitive_declarations() -> None:
    source = """
    namespace PythonSharp.Core;

    extern using collections.abc as abc;

    [MapsTo("dict")]
    [RuntimeType("dict")]
    public primitive class Dict<TKey, TValue> : IEnumerable<KeyValuePair<TKey, TValue>>
    {
        [InlineTemplate("{}")]
        public extern Dict();

        [InlineTemplate("len({self})")]
        public extern int Count { get; }

        [MapsTo("get")]
        public extern TValue? GetOrDefault(TKey key, TValue? defaultValue = default);

        [InlineTemplate("({0} in {self})")]
        public extern bool ContainsKey(TKey key);

        [InlineTemplate("{self}[{0}]")]
        public extern TValue this[TKey key]
        {
            get;
            [InlineTemplate("{self}[{0}] = {value}")] set;
        }
    }
    """
    diag = DiagnosticEngine()
    parser = Parser.from_source(source, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag)
    unit = parser.parse_compilation_unit()

    assert not diag.has_errors(), diag.format_all()
    assert unit.is_ambient_stub is True
    assert unit.namespace == ["PythonSharp", "Core"]
    assert len(unit.imports) == 1
    assert unit.imports[0].is_extern is True
    assert unit.imports[0].path == ["collections", "abc"]
    assert unit.imports[0].alias == "abc"

    assert len(unit.types) == 1
    dict_decl = unit.types[0]
    assert dict_decl.kind == TypeKind.PRIMITIVE_CLASS
    assert dict_decl.name == "Dict"
    assert dict_decl.type_params == ["TKey", "TValue"]
    assert len(dict_decl.attributes) == 2
    assert dict_decl.attributes[0].path == ["MapsTo"]
    assert len(dict_decl.members) == 5


def test_parse_order_cache_with_overloads_linq_and_disposable() -> None:
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
    parser = Parser.from_source(source, ps_filename="Services/OrderCache.ps", diagnostics=diag)
    unit = parser.parse_compilation_unit()

    assert not diag.has_errors(), diag.format_all()
    assert unit.namespace == ["Commerce", "Services"]
    assert len(unit.types) == 3

    iface, rec, cache = unit.types
    assert iface.kind == TypeKind.INTERFACE
    assert rec.kind == TypeKind.RECORD
    assert [p.name for p in rec.primary_ctor_params] == ["Id", "Total", "IsActive"]

    assert cache.kind == TypeKind.CLASS
    assert [b.display_name() for b in cache.base_types] == ["IAuditable", "IDisposable"]

    prop = next(m for m in cache.members if isinstance(m, PropertyDecl))
    assert prop.name == "AuditTag"
    assert prop.access == AccessMod.PUBLIC
    assert prop.accessors[1].kind == "set"
    assert prop.accessors[1].access == AccessMod.PRIVATE

    puts = [m for m in cache.members if isinstance(m, MethodDecl) and m.name == "Put"]
    assert len(puts) == 2
    assert len(puts[0].params) == 1
    assert len(puts[1].params) == 2

    # Verify exact source line tracking on GetActiveIds
    get_active = next(m for m in cache.members if isinstance(m, MethodDecl) and m.name == "GetActiveIds")
    assert get_active.span.ps_filename == "Services/OrderCache.ps"
    assert get_active.params[0].default_value is not None
    assert get_active.params[0].default_value.data["literal_kind"] == LiteralKind.DECIMAL


def test_parse_multidimensional_slices_null_safety_and_switch_expr() -> None:
    source = """
    namespace ML.Pipelines;

    public class TensorOps
    {
        public void Run(Tensor tensor, User? user)
        {
            using var scope = new GradScope();
            var slice = tensor[1..5, ^2.., ::2];
            var name = user?.Profile?.Name ?? "Anonymous";
            var label = name switch
            {
                "Anonymous" => $"Guest-{1 + 1}",
                string s when s.Length > 5 => s,
                _ => "Short"
            };
        }
    }
    """
    diag = DiagnosticEngine()
    parser = Parser.from_source(source, ps_filename="TensorOps.ps", diagnostics=diag)
    unit = parser.parse_compilation_unit()

    assert not diag.has_errors(), diag.format_all()
    run_method = unit.types[0].members[0]
    assert isinstance(run_method, MethodDecl)
    assert run_method.body is not None

    stmts = run_method.body.statements
    assert len(stmts) == 4
    assert isinstance(stmts[0], UsingResourceStmt)

    # Check multi-axis tensor slice `tensor[1..5, ^2.., ::2]`
    slice_stmt = stmts[1]
    assert isinstance(slice_stmt, LocalVarStmt)
    assert slice_stmt.initializer.kind == ExprKind.INDEX_OR_SLICE
    dims = slice_stmt.initializer.data["dimensions"]
    assert len(dims) == 3
    assert dims[0].is_range_or_slice is True
    assert dims[1].is_range_or_slice is True
    assert dims[2].is_range_or_slice is True
    assert dims[2].step is not None

    # Check `??` and `?.`
    null_stmt = stmts[2]
    assert isinstance(null_stmt, LocalVarStmt)
    assert null_stmt.initializer.kind == ExprKind.NULL_COALESCE

    # Check `switch` expression and interpolated string `$"Guest-{1 + 1}"`
    switch_stmt = stmts[3]
    assert isinstance(switch_stmt, LocalVarStmt)
    assert switch_stmt.initializer.kind == ExprKind.SWITCH_EXPR
    arms = switch_stmt.initializer.data["arms"]
    assert len(arms) == 3
    assert arms[0].result_expr.kind == ExprKind.INTERP_STRING
