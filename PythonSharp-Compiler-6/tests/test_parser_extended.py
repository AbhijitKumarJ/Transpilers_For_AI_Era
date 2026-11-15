from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import (
    AccessMod,
    BinaryOp,
    ExprKind,
    FieldDecl,
    IndexerDecl,
    LiteralKind,
    LocalVarStmt,
    MethodDecl,
    Parser,
    PropertyDecl,
    TypeKind,
    UsingResourceStmt,
)


def _parse(source: str, filename: str = "Kitchen.ps") -> tuple[object, DiagnosticEngine]:
    diagnostics = DiagnosticEngine()
    parser = Parser.from_source(source, ps_filename=filename, diagnostics=diagnostics)
    return parser.parse_compilation_unit(), diagnostics


def test_parse_declarations_members_attributes_and_type_references() -> None:
    source = """
    namespace Kitchen.Sink;

    using System;
    using Collections = System.Collections.Generic;
    extern using collections.abc as abc;

    [Marker]
    public enum Color
    {
        [Obsolete("old")]
        Red = 1,
        Green,
        Blue = 1 + 2,
    }

    public record Person(string Name, [KwArgs] int Age = 18);
    public record class Employee(string Name);
    public record struct Point(int X, int Y);
    public primitive struct Handle { }
    public primitive interface IHandle { }

    [System.Obsolete("widget")]
    [Container(1, Name: "widget", Enabled: true)]
    [Extra]
    public sealed partial class Widget<T> : Base, IFoo<T> where T : Base, IFoo
    {
        private readonly List<int> _items = [1, 2, 3];
        internal int? maybe;
        protected (int Id, string Name) Pair;
        public string Name { get; private set; } = "widget";
        public int Count => _items.Count;
        public string Described
        {
            get { return Name; }
            set { Name = value; }
        }
        public int this[int index]
        {
            get => _items[index];
            set => _items[index] = value;
        }
        public Widget() : this("widget") { }
        public Widget(string name) : base(name) { this.Name = name; }
        public Widget(int seed) : this() => _items = [seed];
        public extern void Dispose();
        public TOut Map<TOut>(T input, params int[] rest) where TOut : Base, IFoo => input as TOut;
        public static Widget<T> Create<TInput>(TInput value) where TInput : Base
        {
            return new Widget<T>();
        }
    }

    public interface IThing
    {
        int Value { get; }
        void Run();
    }
    """

    unit, diagnostics = _parse(source)

    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert unit.namespace == ["Kitchen", "Sink"]
    assert [imp.alias for imp in unit.imports] == [None, "Collections", "abc"]
    assert [imp.is_extern for imp in unit.imports] == [False, False, True]

    color, person, employee, point, handle, ihandle, widget, thing = unit.types
    assert color.kind == TypeKind.ENUM
    assert [member.name for member in color.enum_members] == ["Red", "Green", "Blue"]
    assert color.enum_members[0].attributes[0].path == ["Obsolete"]
    assert color.enum_members[2].value is not None

    assert person.kind == TypeKind.RECORD
    assert [param.name for param in person.primary_ctor_params] == ["Name", "Age"]
    assert person.primary_ctor_params[1].is_kwargs_dict is True
    assert employee.kind == TypeKind.RECORD
    assert point.kind == TypeKind.RECORD_STRUCT
    assert handle.kind == TypeKind.PRIMITIVE_STRUCT
    assert ihandle.kind == TypeKind.PRIMITIVE_INTERFACE

    assert widget.kind == TypeKind.CLASS
    assert widget.modifiers == ["sealed", "partial"]
    assert widget.attributes[0].path == ["System", "Obsolete"]
    assert widget.attributes[1].args[1].name == "Name"
    assert widget.type_params == ["T"]
    assert [base.display_name() for base in widget.base_types] == ["Base", "IFoo<T>"]
    assert widget.constraints[0].type_param == "T"
    assert [bound.display_name() for bound in widget.constraints[0].bounds] == ["Base", "IFoo"]

    fields = [member for member in widget.members if isinstance(member, FieldDecl)]
    assert [field.name for field in fields] == ["_items", "maybe", "Pair"]
    assert fields[0].modifiers == ["readonly"]
    assert fields[1].type_ref.is_nullable is True
    assert fields[2].type_ref.tuple_elements[0][1] == "Id"

    name_prop = next(member for member in widget.members if isinstance(member, PropertyDecl) and member.name == "Name")
    assert name_prop.initializer is not None
    assert name_prop.accessors[1].access == AccessMod.PRIVATE
    described = next(
        member for member in widget.members if isinstance(member, PropertyDecl) and member.name == "Described"
    )
    assert described.accessors[0].body is not None
    assert described.accessors[1].body is not None

    indexer = next(member for member in widget.members if isinstance(member, IndexerDecl))
    assert indexer.params[0].name == "index"
    assert indexer.accessors[0].expr_body is not None
    assert indexer.accessors[1].expr_body is not None

    constructors = [member for member in widget.members if isinstance(member, MethodDecl) and member.is_constructor]
    assert len(constructors) == 3
    assert constructors[0].ctor_chain is not None
    assert constructors[0].ctor_chain.target == "this"
    assert constructors[1].ctor_chain is not None
    assert constructors[1].ctor_chain.target == "base"
    assert constructors[2].expr_body is not None

    map_method = next(member for member in widget.members if isinstance(member, MethodDecl) and member.name == "Map")
    assert map_method.type_params == ["TOut"]
    assert map_method.params[1].is_params is True
    assert map_method.params[1].type_ref.type_args[0].path == ["int"]

    create_method = next(
        member for member in widget.members if isinstance(member, MethodDecl) and member.name == "Create"
    )
    assert create_method.modifiers == ["static"]
    assert create_method.return_type is not None
    assert create_method.return_type.path == ["Widget"]

    assert thing.kind == TypeKind.INTERFACE
    assert thing.members[0].access == AccessMod.PUBLIC
    assert isinstance(thing.members[1], MethodDecl)
    assert thing.members[1].body is None


def test_parse_statements_control_flow_patterns_and_lambdas() -> None:
    source = """
    namespace Kitchen.Flow;

    public class Flow
    {
        public async void Run(
            Tensor tensor,
            User? user,
            IEnumerable<int> items,
            int[] numbers,
            int number,
            bool flag)
        {
            using var scope = new GradScope();
            await using var asyncScope = new AsyncScope();
            await foreach (var item in items) { Console.WriteLine(item); }
            foreach (int candidate in numbers) { Console.WriteLine(candidate); }
            if (user != null) { return; } else if (user == null) { throw; } else { throw new Exception("x"); }
            while (user == null) { user = null; }
            var sliced = tensor[1..5, ^2.., ::2, 3:5:2, ..];
            var indexed = tensor[^1];
            var single = tensor[0];
            var name = user?.Profile?.Name ?? "Anonymous";
            var called = user?.Get<int>(1);
            var memberCall = tensor.Map<string>(name);
            var switched = name switch
            {
                "Anonymous" => $"Guest-{1 + 1}",
                string s when s.Length > 5 => s,
                null => "null",
                _ => "Short"
            };
            var tuple = (1, "a");
            var list = [1, 2, 3];
            var obj = new Person("x") { Name = "y", Age = 3 };
            var bare = new Person;
            var constructed = new List<int>();
            var power = 2 ** 3;
            var remainder = 7 % 2;
            var cast = obj as Person;
            var check = obj is Person p { Name: "y" };
            var not = !true;
            var negative = -1;
            var awaited = await FetchAsync();
            var fallback = name ?? "fallback";
            number = 1;
            number += 1;
            number -= 1;
            number *= 2;
            number /= 2;
            name ??= "x";
            FetchById(42);
            Console.WriteLine(name);
            string.Join(",", name);
            this.Name = name;
            try { Run(tensor, user, items, numbers, number, flag); }
            catch (Exception ex) when (ex != null) { throw ex; }
            catch { throw; }
            finally { Console.WriteLine("done"); }
            switch (number)
            {
                case 1:
                    number = 2;
                    break;
                case int i when i > 0:
                    number = i;
                default:
                    number = 0;
                    break;
            }
            int typed = 1;
            List<int> typedList = [1, 2];
            (int Id, string Name) pair = (1, "x");
            Func<int, int, int> lambda = (int x, int y) => x + y;
            Func<int, int> untyped = (x, y) => x;
            Func<int, int> simple = x => x + 1;
            Func<int, int> asyncLambda = async x => await FetchAsync();
            Action blockLambda = () => { Console.WriteLine(); };
            yield return 1;
            yield break;
            return;
        }

        public IEnumerable<int> Numbers()
        {
            yield return 1;
            yield break;
        }
    }
    """

    unit, diagnostics = _parse(source)

    assert not diagnostics.has_errors(), diagnostics.format_all()
    method = unit.types[0].members[0]
    assert isinstance(method, MethodDecl)
    assert method.body is not None
    statements = method.body.statements

    assert isinstance(statements[0], UsingResourceStmt)
    assert statements[0].is_await is False
    assert isinstance(statements[1], UsingResourceStmt)
    assert statements[1].is_await is True
    assert statements[2].is_await is True
    assert statements[3].is_await is False

    sliced = next(stmt for stmt in statements if isinstance(stmt, LocalVarStmt) and stmt.name == "sliced")
    assert sliced.initializer.kind == ExprKind.INDEX_OR_SLICE
    assert len(sliced.initializer.data["dimensions"]) == 5

    switched = next(stmt for stmt in statements if isinstance(stmt, LocalVarStmt) and stmt.name == "switched")
    assert switched.initializer.kind == ExprKind.SWITCH_EXPR
    assert len(switched.initializer.data["arms"]) == 4

    cast = next(stmt for stmt in statements if isinstance(stmt, LocalVarStmt) and stmt.name == "cast")
    assert cast.initializer.kind == ExprKind.TYPE_CAST_AS
    check = next(stmt for stmt in statements if isinstance(stmt, LocalVarStmt) and stmt.name == "check")
    assert check.initializer.kind == ExprKind.TYPE_CHECK_IS
    assert check.initializer.data["pattern"].bind_name == "p"

    block_lambda = next(stmt for stmt in statements if isinstance(stmt, LocalVarStmt) and stmt.name == "blockLambda")
    assert block_lambda.initializer.kind == ExprKind.LAMBDA
    assert block_lambda.initializer.data["params"] == []


def test_parse_primary_literals_calls_and_slices() -> None:
    source = """
    namespace Kitchen.Expr;

    public class Expressions
    {
        public object All(string text)
        {
            var i = 42;
            var f = 1.5;
            var d = 2.5m;
            var s = "text";
            var t = true;
            var n = false;
            var z = null;
            var def = default;
            var tuple = (1, 2, 3);
            var list = [1, 2,];
            var newWithArgs = new Widget(1, 2) { X = 1, Y = 2, };
            var newBare = new Widget;
            var qualified = new Commerce.Domain.Order();
            var generic = new Dict<string, List<int>>();
            var index = list[1];
            var openStart = list[..2];
            var openEnd = list[1..];
            var openBoth = list[..];
            var stepped = list[::2];
            var stopped = list[1:2];
            var noStop = list[1:];
            var noStart = list[:2];
            var call = All(text);
            var named = All(other: text);
            var member = text.Length;
            var memberCall = text.Substring(1, 2);
            var conditional = text?.Length;
            var conditionalCall = text?.Substring(1);
            var genericMemberCall = list.Cast<int>();
            return tuple;
        }
    }
    """

    unit, diagnostics = _parse(source)

    assert not diagnostics.has_errors(), diagnostics.format_all()
    method = unit.types[0].members[0]
    assert isinstance(method, MethodDecl)
    assert method.body is not None
    locals_by_name = {stmt.name: stmt for stmt in method.body.statements if isinstance(stmt, LocalVarStmt)}

    assert locals_by_name["i"].initializer.data["literal_kind"] == LiteralKind.INT
    assert locals_by_name["f"].initializer.data["literal_kind"] == LiteralKind.FLOAT
    assert locals_by_name["d"].initializer.data["literal_kind"] == LiteralKind.DECIMAL
    assert locals_by_name["s"].initializer.data["literal_kind"] == LiteralKind.STRING
    assert locals_by_name["t"].initializer.data["value"] is True
    assert locals_by_name["n"].initializer.data["value"] is False
    assert locals_by_name["z"].initializer.data["literal_kind"] == LiteralKind.NULL
    assert locals_by_name["def"].initializer.data["literal_kind"] == LiteralKind.DEFAULT
    assert locals_by_name["tuple"].initializer.kind == ExprKind.TUPLE_LITERAL
    assert locals_by_name["list"].initializer.kind == ExprKind.LIST_LITERAL
    assert locals_by_name["newWithArgs"].initializer.kind == ExprKind.NEW_OBJECT
    assert len(locals_by_name["newWithArgs"].initializer.data["initializers"]) == 2
    assert locals_by_name["newBare"].initializer.kind == ExprKind.NEW_OBJECT
    assert locals_by_name["qualified"].initializer.data["type_ref"].path == ["Commerce", "Domain", "Order"]
    assert locals_by_name["generic"].initializer.data["type_ref"].type_args[1].display_name() == "List<int>"

    assert locals_by_name["call"].initializer.kind == ExprKind.CALL
    assert locals_by_name["named"].initializer.data["args"][0].name == "other"
    assert locals_by_name["member"].initializer.kind == ExprKind.MEMBER_ACCESS
    assert locals_by_name["memberCall"].initializer.kind == ExprKind.CALL
    assert locals_by_name["conditional"].initializer.kind == ExprKind.NULL_COND_ACCESS
    assert locals_by_name["conditional"].initializer.data["is_call"] is False
    assert locals_by_name["conditionalCall"].initializer.kind == ExprKind.NULL_COND_ACCESS
    assert locals_by_name["conditionalCall"].initializer.data["is_call"] is True
    assert locals_by_name["genericMemberCall"].initializer.data["type_args"][0].display_name() == "int"

    for name in ("openStart", "openEnd", "openBoth", "stepped", "stopped", "noStop", "noStart"):
        assert locals_by_name[name].initializer.kind == ExprKind.INDEX_OR_SLICE


def test_parse_interpolated_string_parts() -> None:
    source = """
    namespace Kitchen.Interp;

    public class Messages
    {
        public string Format(string name, int count)
        {
            return $"Hello {{name}} {name}: {count + 1}";
        }
    }
    """

    unit, diagnostics = _parse(source)

    assert not diagnostics.has_errors(), diagnostics.format_all()
    method = unit.types[0].members[0]
    assert isinstance(method, MethodDecl)
    assert method.body is not None
    expr = method.body.statements[0].value
    assert expr.kind == ExprKind.INTERP_STRING
    parts = expr.data["parts"]
    assert [part.is_expr for part in parts] == [False, True, False, True]
    assert parts[0].text == "Hello {name} "
    assert parts[1].expr.data["name"] == "name"
    assert parts[3].expr.data["op"].name == "ADD"


def test_parser_reports_recoverable_errors_without_hanging() -> None:
    source = """
    namespace Broken;

    public class Bad
    {
        public Bad() : nope() { }
        public int Value { wat; }
        public void Missing(int x { }
        public void Expr()
        {
            var x = ;
            BAD_CHAR#;
        }
    }

    999
    """

    unit, diagnostics = _parse(source, filename="Broken.ps")

    assert diagnostics.has_errors()
    formatted = diagnostics.format_all()
    assert "PS000" in formatted
    assert "Broken.ps" in formatted
    assert unit.namespace == ["Broken"]
    assert unit.types[0].name == "Bad"


def test_operator_precedence_and_associativity() -> None:
    source = """
    namespace Kitchen.Precedence;

    public class Operators
    {
        public void Run(bool a, bool b, bool c, int x, int y, int z, object item)
        {
            var logical = a || b && x == y + z * x;
            var arithmetic = x + y * z;
            var leftAssociative = x - y - z;
            var nullCoalesce = x ?? y;
            var assignment = x = y = z;
            var unary = !a;
            var negative = -x;
            var memberIndex = -item.Value[0];
            var cast = item as string;
            var check = item is string;
            var lambda = (int value) => value + 1;
        }
    }
    """

    unit, diagnostics = _parse(source)

    assert not diagnostics.has_errors(), diagnostics.format_all()
    method = unit.types[0].members[0]
    assert isinstance(method, MethodDecl)
    assert method.body is not None
    locals_by_name = {stmt.name: stmt for stmt in method.body.statements if isinstance(stmt, LocalVarStmt)}

    logical = locals_by_name["logical"].initializer
    assert logical.data["op"] == BinaryOp.OR
    assert logical.data["right"].data["op"] == BinaryOp.AND
    assert logical.data["right"].data["right"].data["op"] == BinaryOp.EQ
    assert logical.data["right"].data["right"].data["right"].data["op"] == BinaryOp.ADD
    assert logical.data["right"].data["right"].data["right"].data["right"].data["op"] == BinaryOp.MUL

    arithmetic = locals_by_name["arithmetic"].initializer
    assert arithmetic.data["op"] == BinaryOp.ADD
    assert arithmetic.data["right"].data["op"] == BinaryOp.MUL

    left_associative = locals_by_name["leftAssociative"].initializer
    assert left_associative.data["op"] == BinaryOp.SUB
    assert left_associative.data["left"].data["op"] == BinaryOp.SUB

    assert locals_by_name["nullCoalesce"].initializer.kind == ExprKind.NULL_COALESCE

    assignment = locals_by_name["assignment"].initializer
    assert assignment.data["op"] == BinaryOp.ASSIGN
    assert assignment.data["right"].data["op"] == BinaryOp.ASSIGN

    assert locals_by_name["unary"].initializer.kind == ExprKind.UNARY
    assert locals_by_name["negative"].initializer.kind == ExprKind.UNARY
    assert locals_by_name["memberIndex"].initializer.kind == ExprKind.UNARY
    assert locals_by_name["cast"].initializer.kind == ExprKind.TYPE_CAST_AS
    assert locals_by_name["check"].initializer.kind == ExprKind.TYPE_CHECK_IS
    assert locals_by_name["lambda"].initializer.kind == ExprKind.LAMBDA
