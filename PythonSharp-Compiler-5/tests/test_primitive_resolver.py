from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import (
    ExprKind,
    IndexerDecl,
    MethodDecl,
    Parser,
    PropertyDecl,
)
from psc.semantics import GlobalSymbolTable, analyze_compilation_units

STUB = """
namespace PythonSharp.Core;

public primitive interface IEnumerable<T> { }

[MapsTo("list")]
[RuntimeType("list")]
public primitive class List<T> : IEnumerable<T>
{
    [InlineTemplate("[]")]
    public extern List();

    [MapsTo("append")]
    public extern void Add(T item);

    [MapsTo("size")]
    public int Count => 0;

    [InlineTemplate("{self}[{0}]")]
    public extern T this[int index] { get; set; }

    public extern void Clear();
}
"""


def test_primitive_resolver_erasure_decorators_kwargs_and_generators() -> None:
    source = """
    namespace PrimitiveDemo;

    using PythonSharp.Core;

    [Route("/api")]
    [Serializable]
    public class Service
    {
        [Cache(30)]
        public string Name { get; set; } = "service";

        [MapsTo("go")]
        public void Mapped() { }

        [InlineTemplate("{self}.value")]
        public int Templated => 1;

        [InlineTemplate("{self}[{0}]")]
        public int this[int index]
        {
            get => index;
            set { }
        }

        [KwArgs]
        public void Log(string message, [KwArgs] Dict<string, object> extra) { }

        public IEnumerable<int> Numbers()
        {
            yield return 1;
        }

        public void Plain() { }
    }
    """
    diag = DiagnosticEngine()
    unit_std = Parser.from_source(
        STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit = Parser.from_source(source, file_id=1, ps_filename="Service.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit_std, unit], symtab, diag)

    assert not diag.has_errors(), diag.format_all()

    service = symtab.types_by_qname["PrimitiveDemo.Service"].ast_node
    assert [expr.kind for expr in service.decorators_to_emit] == [
        ExprKind.CALL,
        ExprKind.IDENT,
    ]

    name = next(member for member in service.members if isinstance(member, PropertyDecl) and member.name == "Name")
    assert name.lowering_mode.kind == "StandardPython"

    mapped = next(member for member in service.members if isinstance(member, MethodDecl) and member.name == "Mapped")
    assert mapped.lowering_mode.kind == "PrimitiveDirect"
    assert mapped.lowering_mode.py_target_name == "go"

    templated = next(
        member for member in service.members if isinstance(member, PropertyDecl) and member.name == "Templated"
    )
    assert templated.lowering_mode.kind == "PrimitiveInlineTemplate"
    assert templated.lowering_mode.inline_template == "{self}.value"

    indexer = next(member for member in service.members if isinstance(member, IndexerDecl))
    assert indexer.lowering_mode.kind == "PrimitiveInlineTemplate"
    assert indexer.lowering_mode.emitted_snake_name == "__getitem__"

    log = next(member for member in service.members if isinstance(member, MethodDecl) and member.name == "Log")
    assert log.params[1].is_kwargs_dict is True
    assert log.lowering_mode.kind == "StandardPython"

    numbers = next(member for member in service.members if isinstance(member, MethodDecl) and member.name == "Numbers")
    assert numbers.is_generator is True

    plain = next(member for member in service.members if isinstance(member, MethodDecl) and member.name == "Plain")
    assert plain.lowering_mode.kind == "StandardPython"

    list_sym = symtab.types_by_qname["PythonSharp.Core.List"].ast_node
    list_ctor = next(member for member in list_sym.members if isinstance(member, MethodDecl))
    assert list_ctor.lowering_mode.kind == "PrimitiveInlineTemplate"
    add = next(member for member in list_sym.members if isinstance(member, MethodDecl) and member.name == "Add")
    assert add.lowering_mode.kind == "PrimitiveDirect"
    assert add.lowering_mode.py_target_name == "append"
    count = next(member for member in list_sym.members if isinstance(member, PropertyDecl) and member.name == "Count")
    assert count.lowering_mode.kind == "PrimitiveDirect"
    clear = next(member for member in list_sym.members if isinstance(member, MethodDecl) and member.name == "Clear")
    assert clear.lowering_mode.kind == "PrimitiveDirect"
