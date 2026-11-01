from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import (
    ComprehensionKind,
    ExprKind,
    MethodDecl,
    Parser,
    ReturnStmt,
)
from psc.semantics import (
    GlobalSymbolTable,
    analyze_compilation_units,
)

STDLIB_STUB = """
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

    [MapsTo("values")]
    public extern IEnumerable<TValue> Values();

    [MapsTo("clear")]
    public extern void Clear();
}

[MapsTo("set")]
[RuntimeType("set")]
public primitive class HashSet<T> : IEnumerable<T>
{
    [InlineTemplate("set()")]
    public extern HashSet();
}

[MapsTo("collections.abc.Iterable")]
public primitive interface IEnumerable<T>
{
    [LinqStage("Filter")]
    IEnumerable<T> Where(Func<T, bool> predicate);

    [LinqStage("Map")]
    IEnumerable<TResult> Select<TResult>(Func<T, TResult> selector);

    [LinqStage("FlatMap")]
    IEnumerable<TResult> SelectMany<TResult>(Func<T, IEnumerable<TResult>> selector);

    [LinqStage("TerminalList")]
    List<T> ToList();

    [LinqStage("TerminalSet")]
    HashSet<T> ToHashSet();

    [LinqStage("TerminalDict")]
    Dict<TKey, TValue> ToDict<TKey, TValue>(
        Func<T, TKey> keySelector,
        Func<T, TValue> valueSelector
    );

    [LinqStage("TerminalAny")]
    bool Any(Func<T, bool> predicate);

    [LinqStage("TerminalSum")]
    T Sum();
}
"""


def test_overload_dispatch_groups_and_linq_comprehension_fusion() -> None:
    """
    Verifies Pass 2B:
      1. Overloaded methods `Put(Order)` and `Put(int, decimal)` are grouped into
         an `OverloadDispatchGroup` with `is_strictly_arity_disjoint = True`.
      2. Overloaded methods sharing arity 1 (`Find(int id)` vs `Find(string tag)` vs `Find(IAuditable item)`)
         build `PyIsInstance("int")`, `PyIsInstance("str")`, and `PsTypesContains("Commerce.Services.IAuditable")`
         guards with `is_strictly_arity_disjoint = False`.
      3. `.Where(o => ...).Where(x => ...).Select(item => item.Id).ToList()` fuses into a single
         `ExprKind.LINQ_COMPREHENSION` node with alpha-renamed iteration variable `o` and 2 filter guards.
    """
    source = """
    namespace Commerce.Services;

    using PythonSharp.Core;

    public interface IAuditable { string AuditTag { get; } }

    public record Order(int Id, decimal Total, bool IsActive);

    public class OrderCache
    {
        private readonly Dict<int, Order> _store = new Dict<int, Order>();

        public void Put(Order order) => _store[order.Id] = order;
        public void Put(int id, decimal total) => _store[id] = new Order(id, total, true);

        public Order? Find(int id) => null;
        public Order? Find(string tag) => null;
        public Order? Find(IAuditable auditable) => null;

        public List<int> GetActiveIds(decimal minTotal = 0.0m)
        {
            return _store.Values()
                .Where(o => o.IsActive)
                .Where(x => x.Total >= minTotal)
                .Select(item => item.Id)
                .ToList();
        }
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

    cache_decl = unit_srv.types[2]
    assert len(cache_decl.overload_groups) == 2

    # 1. Check `put` overload group (Arity 1 vs Arity 2 -> strictly arity disjoint!)
    put_group = next(g for g in cache_decl.overload_groups if g.snake_name == "put")
    assert put_group.is_strictly_arity_disjoint is True
    assert len(put_group.variants) == 2

    # 2. Check `find` overload group (3 variants at Arity 1 -> int, str, and IAuditable interface)
    find_group = next(g for g in cache_decl.overload_groups if g.snake_name == "find")
    assert find_group.is_strictly_arity_disjoint is False
    assert len(find_group.variants) == 3

    find_methods = [m for m in cache_decl.members if isinstance(m, MethodDecl) and m.name == "Find"]
    assert find_methods[0].lowering_mode.runtime_guard is not None
    assert find_methods[0].lowering_mode.runtime_guard.param_type_checks[0][1].kind == "PyIsInstanceStrictInt"
    assert find_methods[0].lowering_mode.runtime_guard.param_type_checks[0][1].target_type == "int"

    assert find_methods[2].lowering_mode.runtime_guard is not None
    assert find_methods[2].lowering_mode.runtime_guard.param_type_checks[0][1].kind == "PsTypesContains"
    assert (
        find_methods[2].lowering_mode.runtime_guard.param_type_checks[0][1].target_type
        == "Commerce.Services.IAuditable"
    )

    # 3. Verify LINQ Comprehension Fusion & Alpha-Renaming (`o`, `x`, `item` -> all unified to `o`!)
    get_active = next(m for m in cache_decl.members if isinstance(m, MethodDecl) and m.name == "GetActiveIds")
    assert get_active.body is not None
    ret_stmt = get_active.body.statements[0]
    assert isinstance(ret_stmt, ReturnStmt)
    assert ret_stmt.value is not None
    comp = ret_stmt.value

    assert comp.kind == ExprKind.LINQ_COMPREHENSION
    assert comp.data["terminal_kind"] == ComprehensionKind.LIST
    assert comp.data["item_var"] == "o"
    assert len(comp.data["filters"]) == 2

    # Verify second `.Where(x => x.Total >= minTotal)` had `x` alpha-renamed to `o`
    second_filter = comp.data["filters"][1]
    left_member = second_filter.data["left"]
    assert left_member.data["target"].data["name"] == "o"

    # Verify `.Select(item => item.Id)` had `item` alpha-renamed to `o`
    proj = comp.data["projection"]
    assert proj is not None
    assert proj.data["target"].data["name"] == "o"
    assert proj.data["member"] == "Id"


def test_ps002_detects_ambiguous_erased_generic_overloads() -> None:
    """
    Verifies Rule PS002:
      `Process(List<int> items)` and `Process(List<string> names)` both erase to
      Python `list` at Arity 1, triggering compile-time error PS002.
    """
    source = """
    namespace CollisionTest;

    using PythonSharp.Core;

    public class BatchProcessor
    {
        public void Process(List<int> ids) { }
        public void Process(List<string> names) { }
    }
    """
    diag = DiagnosticEngine()
    unit_std = Parser.from_source(
        STDLIB_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_col = Parser.from_source(
        source, file_id=1, ps_filename="BatchProcessor.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit_std, unit_col], symtab, diag)

    assert diag.has_errors()
    ps002_errors = [d for d in diag.diagnostics if d.code == "PS002"]
    assert len(ps002_errors) == 1
    assert "Process(List<int> ids)" in ps002_errors[0].message
    assert "Process(List<string> names)" in ps002_errors[0].message


def test_ps002_rejects_nullable_and_non_nullable_overloads_with_the_same_runtime_check() -> None:
    source = """
    namespace NullableCollision;

    public record Item(int Id);

    public class Repository
    {
        public string Find(Item item) => "";
        public string Find(Item? item) => "";
    }
    """
    diag = DiagnosticEngine()
    unit_std = Parser.from_source(
        STDLIB_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_repo = Parser.from_source(
        source, file_id=1, ps_filename="Repository.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit_std, unit_repo], symtab, diag)

    assert diag.has_errors()
    ps002_errors = [d for d in diag.diagnostics if d.code == "PS002"]
    assert len(ps002_errors) == 1
    assert "Find(Item item)" in ps002_errors[0].message
    assert "Find(Item? item)" in ps002_errors[0].message


LINQ_STUB = STDLIB_STUB.replace(
    '    [LinqStage("TerminalSum")]\n    T Sum();',
    """    [LinqStage("TerminalSum")]
    T Sum();

    [LinqStage("TerminalAll")]
    bool All(Func<T, bool> predicate);

    [LinqStage("TerminalFirstOrDefault")]
    T FirstOrDefault(Func<T, bool> predicate);

    [LinqStage("TerminalCount")]
    int Count();

    [LinqStage("TerminalMin")]
    T Min();

    [LinqStage("TerminalMax")]
    T Max();""",
)


def _method_expr(unit, name: str):
    method = next(member for member in unit.types[0].members if isinstance(member, MethodDecl) and member.name == name)
    if method.expr_body is not None:
        return method.expr_body
    assert method.body is not None
    stmt = method.body.statements[0]
    assert isinstance(stmt, ReturnStmt)
    return stmt.value


def test_linq_fusion_variants_and_projection_substitution() -> None:
    source = """
    namespace LinqDemo;

    using PythonSharp.Core;

    public class Queries
    {
        public List<int> Flat(List<List<int>> groups) => groups.SelectMany(g => g).ToList();
        public Dict<int, int> Map(List<int> xs) => xs.ToDict(x => x, x => x * 2);
        public bool AnyPositive(List<int> xs) => xs.Any(x => x > 0);
        public bool AllPositive(List<int> xs) => xs.All(x => x > 0);
        public int FirstPositive(List<int> xs) => xs.FirstOrDefault(x => x > 0);
        public int CountAll(List<int> xs) => xs.Count();
        public int SumAll(List<int> xs) => xs.Sum();
        public int MinAll(List<int> xs) => xs.Min();
        public int MaxAll(List<int> xs) => xs.Max();
        public HashSet<int> Set(List<int> xs) => xs.ToHashSet();
        public List<int> ProjectThenFilter(List<int> xs) => xs.Select(x => x * 2).Where(y => y > 2).ToList();
        public List<int> MemberThenFilter(List<int> xs) => xs.Select(x => x.ToString().Length).Where(y => y > 0).ToList();
        public List<int> UnaryThenFilter(List<int> xs) => xs.Select(x => -x).Where(y => y > 0).ToList();
        public List<int> CallThenFilter(List<int> xs) => xs.Select(x => Use(x)).Where(y => y > 0).ToList();
        public List<int> IndexThenFilter(List<int> xs) => xs.Select(x => xs[x]).Where(y => y > 0).ToList();
        public List<int> CoalesceThenFilter(List<int> xs) => xs.Select(x => Maybe(xs) ?? x).Where(y => y > 0).ToList();
        public int Use(int x) => x;
        public List<int>? Maybe(List<int> xs) => null;
    }
    """
    diag = DiagnosticEngine()
    unit_std = Parser.from_source(
        LINQ_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit = Parser.from_source(source, file_id=1, ps_filename="Queries.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit_std, unit], symtab, diag)

    assert not diag.has_errors(), diag.format_all()

    flat = _method_expr(unit, "Flat")
    assert flat.kind == ExprKind.LINQ_COMPREHENSION
    assert flat.data["terminal_kind"] == ComprehensionKind.LIST
    assert len(flat.data["generators"]) == 2
    assert flat.data["generators"][1].iterable.kind == ExprKind.IDENT

    mapped = _method_expr(unit, "Map")
    assert mapped.kind == ExprKind.LINQ_COMPREHENSION
    assert mapped.data["terminal_kind"] == ComprehensionKind.DICT
    assert mapped.data["key_projection"] is not None
    assert mapped.data["value_projection"] is not None

    expectations = {
        "AnyPositive": (ComprehensionKind.ANY, True),
        "AllPositive": (ComprehensionKind.ALL, True),
        "FirstPositive": (ComprehensionKind.FIRST_OR_DEFAULT, True),
        "CountAll": (ComprehensionKind.COUNT, False),
        "SumAll": (ComprehensionKind.SUM, False),
        "MinAll": (ComprehensionKind.MIN, False),
        "MaxAll": (ComprehensionKind.MAX, False),
        "Set": (ComprehensionKind.SET, False),
    }
    for name, (kind, has_predicate) in expectations.items():
        expr = _method_expr(unit, name)
        assert expr.kind == ExprKind.LINQ_COMPREHENSION, name
        assert expr.data["terminal_kind"] == kind, name
        if has_predicate:
            assert expr.data["projection"] is not None or expr.data["filters"], name

    project_then_filter = _method_expr(unit, "ProjectThenFilter")
    assert project_then_filter.kind == ExprKind.LINQ_COMPREHENSION
    assert project_then_filter.data["item_var"] == "x"
    assert len(project_then_filter.data["filters"]) == 1
    assert project_then_filter.data["projection"] is not None
    filter_left = project_then_filter.data["filters"][0].data["left"]
    assert filter_left.kind == ExprKind.BINARY
    assert filter_left.data["left"].kind == ExprKind.IDENT
    assert filter_left.data["left"].data["name"] == "x"
    assert filter_left.data["right"].data["value"] == 2

    for name in (
        "MemberThenFilter",
        "UnaryThenFilter",
        "CallThenFilter",
        "IndexThenFilter",
        "CoalesceThenFilter",
    ):
        expr = _method_expr(unit, name)
        assert expr.kind == ExprKind.LINQ_COMPREHENSION, name
        assert expr.data["projection"] is not None, name
        assert expr.data["filters"], name
        assert expr.data["filters"][0] is not None, name


def test_overload_call_site_resolution_and_runtime_guards() -> None:
    source = """
    namespace CallSites;

    using PythonSharp.Core;

    public interface IThing { }

    public class Thing : IThing { }

    public class Calculator
    {
        public int Add(int value) => value;
        public int Add(string value) => 1;
        public int Add(int left, int right) => left + right;
        public int Pick(IThing thing) => 1;
        public int Pick(object value) => 2;

        public int Run(int number, string text, Thing thing)
        {
            var a = Add(number);
            var b = Add(text);
            var c = Add(number, 1);
            var d = Pick(thing);
            var e = Pick(text);
            var f = this.Add(number);
            var g = Add(number) + Add(text);
            var h = Maybe(number) ?? Add(number);
            var i = new Calculator().Add(number);
            return g + h + i;
        }

        public int? Maybe(int value) => null;
    }
    """
    diag = DiagnosticEngine()
    unit_std = Parser.from_source(
        STDLIB_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit = Parser.from_source(source, file_id=1, ps_filename="Calculator.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit_std, unit], symtab, diag)

    assert not diag.has_errors(), diag.format_all()

    calc = symtab.types_by_qname["CallSites.Calculator"]
    add_methods = [m for m in calc.ast_node.members if isinstance(m, MethodDecl) and m.name == "Add"]
    assert len(add_methods) == 3
    add_group = next(group for group in calc.ast_node.overload_groups if group.snake_name == "add")
    assert add_group.is_strictly_arity_disjoint is False

    pick_methods = [m for m in calc.ast_node.members if isinstance(m, MethodDecl) and m.name == "Pick"]
    assert pick_methods[0].lowering_mode.runtime_guard is not None
    assert pick_methods[0].lowering_mode.runtime_guard.param_type_checks[0][1].kind == "PsTypesContains"
    assert pick_methods[1].lowering_mode.runtime_guard is not None
    assert pick_methods[1].lowering_mode.runtime_guard.param_type_checks == []

    int_guard = next(
        m
        for m in calc.ast_node.members
        if isinstance(m, MethodDecl)
        and m.name == "Add"
        and len(m.params) == 1
        and m.params[0].type_ref.display_name() == "int"
    ).lowering_mode.runtime_guard
    assert int_guard is not None
    assert int_guard.param_type_checks[0][1].kind == "PyIsInstanceStrictInt"
    assert int_guard.param_type_checks[0][1].target_type == "int"

    run = next(m for m in calc.ast_node.members if isinstance(m, MethodDecl) and m.name == "Run")
    assert run.body is not None
    assert len(run.body.statements) >= 9
    local_a = run.body.statements[0]
    assert isinstance(local_a, type(run.body.statements[0]))
    assert local_a.initializer.resolved_lowering is not None
