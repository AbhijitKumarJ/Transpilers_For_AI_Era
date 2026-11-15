from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.semantics import GlobalSymbolTable, SymbolCollector


def _unit(source: str, filename: str, diagnostics: DiagnosticEngine, file_id: int = 0):
    return Parser.from_source(
        source,
        file_id=file_id,
        ps_filename=filename,
        diagnostics=diagnostics,
    ).parse_compilation_unit()


def _collect(
    sources: list[tuple[str, str]],
    *,
    assembly_name: str | None = "MyApp",
) -> tuple[GlobalSymbolTable, DiagnosticEngine]:
    diagnostics = DiagnosticEngine()
    units = [_unit(source, filename, diagnostics, file_id=index) for index, (source, filename) in enumerate(sources)]
    symtab = GlobalSymbolTable(default_assembly_name="DefaultApp")
    SymbolCollector(symtab=symtab, diagnostics=diagnostics).collect_all(units, assembly_name=assembly_name)
    return symtab, diagnostics


def test_collector_registers_primitives_indexers_attributes_and_generic_methods() -> None:
    source = """
    namespace Feature;

    using PythonSharp.Core;

    [SchemaModel]
    [NativeCompile]
    [MapsTo("dict")]
    [RuntimeType("builtins.dict")]
    public primitive class Bag<TKey, TValue>
    {
        [InlineTemplate("{}")]
        public extern Bag();

        [MapsTo("size")]
        [InlineTemplate("len({self})")]
        public int Count => 0;

        [InlineTemplate("{self}[{0}]")]
        public extern TValue this[TKey key]
        {
            get;
            [InlineTemplate("{self}[{0}] = {value}")] set;
        }

        [MapsTo("put")]
        [InlineTemplate("{self}[{0}] = {1}")]
        [LinqStage("Map")]
        public async static void Put(
            TKey key,
            TValue value,
            int retries = 3,
            params string[] labels)
        {
        }

        public Bag(int seed) { }
    }
    """

    symtab, diagnostics = _collect([(source, "Feature/Bag.ps")])

    assert not diagnostics.has_errors(), diagnostics.format_all()
    bag = symtab.types_by_qname["Feature.Bag"]
    assert bag.maps_to_py_type == "dict"
    assert bag.runtime_isinstance_type == "builtins.dict"
    assert bag.is_schema_model is True
    assert bag.is_native_compile is True
    assert bag.assembly_name == "MyApp"
    assert bag.unit.emitted_py_module_path == "feature.py"

    count = bag.lookup_member("Count")[0]
    assert count.kind == "property"
    assert count.snake_name == "size"
    assert count.maps_to_py_name == "size"
    assert count.inline_template == "len({self})"
    assert count.is_readonly is True
    assert count.is_extern is True
    assert count.setter_access is None

    indexer = bag.lookup_member("this[]")[0]
    assert indexer.kind == "indexer"
    assert indexer.snake_name == "__getitem__"
    assert indexer.setter_access.value == "public"
    assert indexer.inline_template == "{self}[{0}]"
    assert indexer.setter_inline_template == "{self}[{0}] = {value}"
    assert indexer.is_extern is True
    assert indexer.param_names == ["key"]
    assert indexer.resolved_type is not None
    assert indexer.resolved_type.is_type_param is True
    assert indexer.param_types[0].qualified_name == "TKey"

    put = bag.lookup_member("Put")[0]
    assert put.kind == "method"
    assert put.snake_name == "put"
    assert put.maps_to_py_name == "put"
    assert put.inline_template == "{self}[{0}] = {1}"
    assert put.linq_stage == "Map"
    assert put.is_async is True
    assert put.is_static is True
    assert put.is_extern is True
    assert put.param_names == ["key", "value", "retries", "labels"]
    assert put.min_arity == 2
    assert put.max_arity == 999
    assert put.has_varargs is True
    assert put.has_kwargs is False
    assert put.param_types[0].qualified_name == "TKey"

    ctors = bag.lookup_member("Bag")
    assert len(ctors) == 2
    empty_ctor, seed_ctor = ctors
    assert empty_ctor.kind == "constructor"
    assert empty_ctor.snake_name == "__init__"
    assert empty_ctor.resolved_type is None
    assert empty_ctor.min_arity == 0
    assert empty_ctor.max_arity == 0
    assert seed_ctor.kind == "constructor"
    assert seed_ctor.snake_name == "__init__"
    assert seed_ctor.param_names == ["seed"]
    assert seed_ctor.min_arity == 1
    assert seed_ctor.max_arity == 1


def test_collector_registers_record_primary_constructors_and_properties() -> None:
    source = """
    namespace Feature;

    public record Person(string Name, int Age = 18);
    public record struct Point(int X, int Y);
    """

    symtab, diagnostics = _collect([(source, "Feature/Records.ps")])

    assert not diagnostics.has_errors(), diagnostics.format_all()
    person = symtab.types_by_qname["Feature.Person"]
    point = symtab.types_by_qname["Feature.Point"]

    name = person.lookup_member("Name")[0]
    assert name.kind == "property"
    assert name.access.value == "public"
    assert name.setter_access.value == "private"
    assert name.is_readonly is True
    assert name.snake_name == "name"
    assert name.resolved_type is not None
    assert name.resolved_type.py_annotation == "str"

    person_ctor = person.lookup_member("Person")[0]
    assert person_ctor.kind == "constructor"
    assert person_ctor.param_names == ["name", "age"]
    assert person_ctor.min_arity == 1
    assert person_ctor.max_arity == 2

    x = point.lookup_member("X")[0]
    assert x.setter_access.value == "public"
    assert x.is_readonly is False
    point_ctor = point.lookup_member("Point")[0]
    assert point_ctor.min_arity == 2
    assert point_ctor.max_arity == 2


def test_collector_handles_private_fields_auto_properties_and_static_properties() -> None:
    source = """
    namespace Feature;

    public class Fields
    {
        private int count;
        private int _already;
        public readonly int Frozen;
        private readonly int _secret = 1;
        public string Name { get; private set; }
        public static int Total { get; set; }
        public int Explicit { get { return count; } }
    }
    """

    symtab, diagnostics = _collect([(source, "Feature/Fields.ps")])

    assert not diagnostics.has_errors(), diagnostics.format_all()
    fields = symtab.types_by_qname["Feature.Fields"]

    count = fields.lookup_member("count")[0]
    assert count.snake_name == "_count"
    already = fields.lookup_member("_already")[0]
    assert already.snake_name == "_already"
    frozen = fields.lookup_member("Frozen")[0]
    assert frozen.is_readonly is True
    assert frozen.setter_access is None
    secret = fields.lookup_member("_secret")[0]
    assert secret.is_readonly is True
    assert secret.setter_access is None

    name = fields.lookup_member("Name")[0]
    assert name.ast_node.backing_slot_name == "_name"
    total = fields.lookup_member("Total")[0]
    assert total.is_static is True
    assert total.ast_node.backing_slot_name is None
    explicit = fields.lookup_member("Explicit")[0]
    assert explicit.ast_node.backing_slot_name is None
    assert explicit.is_readonly is True


def test_collector_reports_duplicate_types_but_accepts_partial_declarations() -> None:
    duplicate_source = "namespace Dup; public class Thing { }"
    symtab, diagnostics = _collect(
        [
            (duplicate_source, "Dup/One.ps"),
            (duplicate_source, "Dup/Two.ps"),
        ]
    )

    assert diagnostics.has_errors()
    assert "Duplicate type definition 'Dup.Thing'" in diagnostics.format_all()
    assert symtab.types_by_qname["Dup.Thing"] is not None

    partial_source = "namespace Dup; public partial class Thing { }"
    _, partial_diagnostics = _collect(
        [
            (partial_source, "Dup/One.ps"),
            (partial_source, "Dup/Two.ps"),
        ]
    )
    assert not partial_diagnostics.has_errors(), partial_diagnostics.format_all()


def test_collector_reports_namespace_module_path_collisions() -> None:
    _, diagnostics = _collect(
        [
            ("namespace FooBar; public class A { }", "A.ps"),
            ("namespace Foo_Bar; public class B { }", "B.ps"),
        ]
    )

    assert diagnostics.has_errors()
    assert "Namespace path collision" in diagnostics.format_all()
    assert "foo_bar.py" in diagnostics.format_all()


def test_collector_uses_core_assembly_for_stubs_and_default_for_user_types() -> None:
    symtab, diagnostics = _collect(
        [
            ("namespace PythonSharp.Core; public class Ambient { }", "stdlib/PythonSharp.Core.d.ps"),
            ("namespace App; public class User { }", "App/User.ps"),
        ],
        assembly_name=None,
    )

    assert not diagnostics.has_errors(), diagnostics.format_all()
    assert symtab.types_by_qname["PythonSharp.Core.Ambient"].assembly_name == "PythonSharp.Core"
    assert symtab.types_by_qname["App.User"].assembly_name == "DefaultApp"
