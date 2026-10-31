from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.semantics import GlobalSymbolTable, SymbolCollector
from psc.semantics.symbols import ResolvedType, namespace_to_module_path, pascal_to_snake

STDLIB_SOURCE = """
namespace PythonSharp.Core;

[MapsTo("list")]
public primitive class List<T> : IEnumerable<T>
{
    [MapsTo("append")]
    public extern void Add(T item);
}

[MapsTo("dict")]
public primitive class Dict<TKey, TValue> { }

public primitive class Task<T> { }

[MapsTo("collections.abc.Iterable")]
public primitive interface IEnumerable<T> { }
"""

LIBRARY_SOURCE = """
namespace App.Library;

public class Widget { }
"""

APP_SOURCE = """
namespace App.Domain;

using PythonSharp.Core;
using Alias = App.Library.Widget;
using App.Library;

public class Base { public int BaseValue; }
public class Derived : Base { public int Own; }
public enum Color { Red }
public interface IThing { }
public record Person(string Name);
public record struct Point(int X);
public struct Val { }

public class Holder<T>
{
    public T Value;
    public Task<int> Work;
    public List<Alias> Widgets;
    public Widget Direct;
    public Func<int, string> Fn;
    public Action<int> Act;
    public (int Id, string Name) Pair;
    public int[] Array;
    public int? Maybe;
    public External Unknown;
}
"""


def _parse_library() -> tuple[GlobalSymbolTable, DiagnosticEngine]:
    diagnostics = DiagnosticEngine()
    units = [
        Parser.from_source(
            STDLIB_SOURCE,
            file_id=0,
            ps_filename="stdlib/PythonSharp.Core.d.ps",
            diagnostics=diagnostics,
        ).parse_compilation_unit(),
        Parser.from_source(
            LIBRARY_SOURCE,
            file_id=1,
            ps_filename="App/Library/Widget.ps",
            diagnostics=diagnostics,
        ).parse_compilation_unit(),
        Parser.from_source(
            APP_SOURCE,
            file_id=2,
            ps_filename="App/Domain/Holder.ps",
            diagnostics=diagnostics,
        ).parse_compilation_unit(),
    ]
    symtab = GlobalSymbolTable(default_assembly_name="DefaultApp")
    SymbolCollector(symtab=symtab, diagnostics=diagnostics).collect_all(units, assembly_name="MyApp")

    assert not diagnostics.has_errors(), diagnostics.format_all()
    return symtab, diagnostics


def test_pascal_to_snake_and_namespace_module_paths() -> None:
    assert pascal_to_snake("") == ""
    assert pascal_to_snake("___") == "___"
    assert pascal_to_snake("_OrderCache") == "_order_cache"
    assert pascal_to_snake("OrderCache") == "order_cache"
    assert pascal_to_snake("HTTPResponse") == "http_response"
    assert pascal_to_snake("already_snake") == "already_snake"
    assert pascal_to_snake("Foo_Bar") == "foo_bar"
    assert pascal_to_snake("ID") == "id"

    assert namespace_to_module_path(()) == "__root__.py"
    assert namespace_to_module_path(("Commerce", "Domain")) == "commerce/domain.py"
    assert namespace_to_module_path(("FooBar",)) == "foo_bar.py"


def test_resolved_type_nullability_and_runtime_signatures() -> None:
    primitive = ResolvedType("int", "int", "int")
    nullable = primitive.with_nullable()

    assert nullable is not primitive
    assert nullable.is_nullable is True
    assert nullable.py_annotation == "int | None"
    assert nullable.with_nullable() is nullable
    assert nullable.with_nullable(False).py_annotation == "int"
    assert ResolvedType("None", "None").with_nullable().py_annotation == "None"
    assert ResolvedType("Any", "Any").with_nullable().py_annotation == "Any"

    interface = ResolvedType("App.IThing", "IThing", "IThing", is_interface=True)
    type_param = ResolvedType("T", "T", is_type_param=True)
    assert primitive.runtime_erased_signature() == "int"
    assert nullable.runtime_erased_signature() == "int?"
    assert interface.runtime_erased_signature() == "ps_interface:App.IThing"
    assert type_param.runtime_erased_signature() == "object"
    assert ResolvedType("dynamic", "Any").runtime_erased_signature() == "object"
    assert ResolvedType("object", "object", "object").runtime_erased_signature() == "object"
    assert ResolvedType("External", "External").runtime_erased_signature() == "External"


def test_type_symbol_properties_members_and_subclass_queries() -> None:
    symtab, _ = _parse_library()

    task = symtab.types_by_qname["PythonSharp.Core.Task"]
    enumerable = symtab.types_by_qname["PythonSharp.Core.IEnumerable"]
    person = symtab.types_by_qname["App.Domain.Person"]
    point = symtab.types_by_qname["App.Domain.Point"]
    value = symtab.types_by_qname["App.Domain.Val"]
    color = symtab.types_by_qname["App.Domain.Color"]
    widget = symtab.types_by_qname["App.Library.Widget"]
    derived = symtab.types_by_qname["App.Domain.Derived"]

    assert task.is_primitive is True
    assert task.is_interface is False
    assert enumerable.is_primitive is True
    assert enumerable.is_interface is True
    assert person.is_record is True
    assert point.is_record is True
    assert point.is_struct is True
    assert value.is_struct is True
    assert color.is_enum is True
    assert widget.is_record is False

    assert derived.lookup_member("BaseValue")[0].name == "BaseValue"
    assert derived.lookup_member("BaseValue", include_bases=False) == []
    assert derived.lookup_member("Own")[0].name == "Own"
    assert derived.is_subclass_of("App.Domain.Base") is True
    assert derived.is_subclass_of("App.Domain.Derived") is True
    assert derived.is_subclass_of("App.Domain.Val") is False

    assert len(symtab.short_name_index["Widget"]) == 1
    assert len(symtab.namespaces[("App", "Domain")]) == 8
    assert symtab.members_by_id
    assert symtab.types_by_id[derived.id] is derived


def test_global_symbol_table_resolves_aliases_namespaces_imports_and_core() -> None:
    symtab, _ = _parse_library()
    app_unit = symtab.types_by_qname["App.Domain.Holder"].unit
    widget = symtab.types_by_qname["App.Library.Widget"]

    assert symtab.lookup_type_in_context(["App", "Library", "Widget"], ("App", "Domain"), []) is widget
    assert symtab.lookup_type_in_context(["Alias"], ("App", "Domain"), app_unit.imports) is widget
    assert symtab.lookup_type_in_context(["Widget"], ("App", "Domain"), app_unit.imports) is widget
    assert symtab.lookup_type_in_context(["Base"], ("App", "Domain"), []) is symtab.types_by_qname["App.Domain.Base"]
    assert (
        symtab.lookup_type_in_context(["Task"], ("App", "Domain"), []) is symtab.types_by_qname["PythonSharp.Core.Task"]
    )
    assert symtab.lookup_type_in_context(["Unknown"], ("App", "Domain"), []) is None


def test_resolved_field_types_for_generics_tuples_arrays_delegates_and_externals() -> None:
    symtab, _ = _parse_library()
    holder = symtab.types_by_qname["App.Domain.Holder"]
    app_unit = holder.unit

    value = holder.lookup_member("Value")[0].resolved_type
    work = holder.lookup_member("Work")[0].resolved_type
    widgets = holder.lookup_member("Widgets")[0].resolved_type
    direct = holder.lookup_member("Direct")[0].resolved_type
    fn = holder.lookup_member("Fn")[0].resolved_type
    act = holder.lookup_member("Act")[0].resolved_type
    pair = holder.lookup_member("Pair")[0].resolved_type
    array = holder.lookup_member("Array")[0].resolved_type
    maybe = holder.lookup_member("Maybe")[0].resolved_type
    unknown = holder.lookup_member("Unknown")[0].resolved_type

    assert value is not None
    assert value.is_type_param is True
    assert value.py_annotation == "T"
    assert work is not None
    assert work.qualified_name == "PythonSharp.Core.Task"
    assert work.py_annotation == "int"
    assert work.type_args[0].py_annotation == "int"
    assert widgets is not None
    assert widgets.qualified_name == "PythonSharp.Core.List"
    assert widgets.py_annotation == "list[Widget]"
    assert widgets.is_primitive is True
    assert widgets.type_args[0].qualified_name == "App.Library.Widget"
    assert direct is not None
    assert direct.qualified_name == "App.Library.Widget"
    assert direct.py_annotation == "Widget"
    assert fn is not None
    assert fn.py_annotation == "Callable[[int], str]"
    assert fn.runtime_isinstance_type == "collections.abc.Callable"
    assert act is not None
    assert act.py_annotation == "Callable[[int], None]"
    assert pair is not None
    assert pair.is_tuple is True
    assert pair.py_annotation == "tuple[int, str]"
    assert [arg.py_annotation for arg in pair.type_args] == ["int", "str"]
    assert array is not None
    assert array.py_annotation == "list[int]"
    assert maybe is not None
    assert maybe.py_annotation == "int | None"
    assert unknown is not None
    assert unknown.qualified_name == "External"
    assert unknown.py_annotation == "External"

    external_tokens = [member for member in holder.ast_node.members if getattr(member, "name", None) == "Unknown"]
    assert len(external_tokens) == 1
    external_decl = external_tokens[0]
    resolved = symtab.resolve_type_ref(
        external_decl.type_ref,
        current_ns=holder.namespace,
        imports=app_unit.imports,
    )
    assert resolved.qualified_name == "External"
