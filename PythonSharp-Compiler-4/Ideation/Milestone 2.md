Here are the raw individual files for **Milestone 2 (Pass 1: Project Configuration, `GlobalSymbolTable`, `SymbolCollector`, Virtual Namespace Aggregator, and Circular Cross-File Type Resolver)** of the **PythonSharp Prototype Transpiler (`psc`)**.

---

### 1. `src/psc/project.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import tomllib
import xml.etree.ElementTree as ET


@dataclass(slots=True)
class PsProjectConfig:
    """Represents a .psproj assembly boundary and build configuration."""
    project_name: str
    root_dir: Path
    out_dir: Path = field(default_factory=lambda: Path("dist"))
    target_python: str = "3.11"
    emit_pyc: bool = True
    source_files: list[Path] = field(default_factory=list)
    stub_files: list[Path] = field(default_factory=list)
    pypi_dependencies: dict[str, str] = field(default_factory=dict)

    def all_input_files(self) -> list[Path]:
        """Returns ambient .d.ps stubs first, followed by user .ps source files."""
        return [*self.stub_files, *self.source_files]


def load_project(psproj_path: Path, stdlib_dir: Path | None = None) -> PsProjectConfig:
    """
    Loads a PythonSharp project file (.psproj in XML or TOML format) and
    discovers all .ps and .d.ps files recursively inside the project root.
    """
    psproj_path = psproj_path.resolve()
    root_dir = psproj_path.parent
    raw_text = psproj_path.read_text(encoding="utf-8").strip()

    project_name = psproj_path.stem
    out_dir = root_dir / "dist"
    target_python = "3.11"
    emit_pyc = True
    pypi_deps: dict[str, str] = {}

    if raw_text.startswith("<"):
        # Parse C#-style XML .psproj
        root = ET.fromstring(raw_text)
        prop_group = root.find("PropertyGroup")
        if prop_group is not None:
            if (name_el := prop_group.find("AssemblyName")) is not None and name_el.text:
                project_name = name_el.text.strip()
            if (out_el := prop_group.find("OutputPath")) is not None and out_el.text:
                out_dir = root_dir / out_el.text.strip()
            if (py_el := prop_group.find("TargetPython")) is not None and py_el.text:
                target_python = py_el.text.strip()
            if (pyc_el := prop_group.find("EmitPyc")) is not None and pyc_el.text:
                emit_pyc = pyc_el.text.strip().lower() == "true"

        for pkg in root.findall("./ItemGroup/PyPiPackage"):
            inc = pkg.attrib.get("Include")
            ver = pkg.attrib.get("Version", "*")
            if inc:
                pypi_deps[inc] = ver
    else:
        # Parse TOML-formatted .psproj
        data = tomllib.loads(raw_text)
        proj_sec = data.get("project", {})
        project_name = proj_sec.get("name", project_name)
        if "out_dir" in proj_sec:
            out_dir = root_dir / proj_sec["out_dir"]
        target_python = proj_sec.get("target_python", target_python)
        emit_pyc = bool(proj_sec.get("emit_pyc", emit_pyc))
        pypi_deps = dict(data.get("dependencies", {}))

    stub_files: list[Path] = []
    if stdlib_dir is not None and stdlib_dir.exists():
        stub_files.extend(sorted(stdlib_dir.rglob("*.d.ps")))

    project_stubs = sorted(root_dir.rglob("*.d.ps"))
    for st in project_stubs:
        if st not in stub_files:
            stub_files.append(st)

    source_files = sorted(
        p for p in root_dir.rglob("*.ps") if not p.name.endswith(".d.ps")
    )

    return PsProjectConfig(
        project_name=project_name,
        root_dir=root_dir,
        out_dir=out_dir,
        target_python=target_python,
        emit_pyc=emit_pyc,
        source_files=source_files,
        stub_files=stub_files,
        pypi_dependencies=pypi_deps,
    )

```

---

### 2. `src/psc/semantics/__init__.py`

```python
from psc.semantics.symbols import (
    BUILTIN_PRIMITIVE_MAP,
    GlobalSymbolTable,
    MemberSymbol,
    ResolvedType,
    TypeSymbol,
    pascal_to_snake,
)
from psc.semantics.collector import SymbolCollector

__all__ = [
    "BUILTIN_PRIMITIVE_MAP",
    "GlobalSymbolTable",
    "MemberSymbol",
    "ResolvedType",
    "TypeSymbol",
    "SymbolCollector",
    "pascal_to_snake",
]

```

---

### 3. `src/psc/semantics/symbols.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
import re
from typing import Literal
from psc.diagnostics import SourceSpan
from psc.frontend.ast_nodes import (
    AccessMod,
    CompilationUnit,
    ImportDecl,
    MemberDecl,
    ParamDecl,
    SymbolId,
    TypeDecl,
    TypeKind,
    TypeRef,
)


_SNAKE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z0-9])([A-Z])")


def pascal_to_snake(name: str) -> str:
    """Converts C# PascalCase or camelCase identifiers into Python snake_case."""
    if not name:
        return name
    leading = ""
    core = name
    while core.startswith("_"):
        leading += "_"
        core = core[1:]
    if not core:
        return leading
    s1 = _SNAKE_1.sub(r"\1_\2", core)
    s2 = _SNAKE_2.sub(r"\1_\2", s1).lower()
    return f"{leading}{s2}"


def namespace_to_module_path(namespace: tuple[str, ...]) -> str:
    """Maps a logical PythonSharp namespace tuple to its target Python package module path."""
    if not namespace:
        return "__root__.py"
    parts = [pascal_to_snake(segment) for segment in namespace]
    return "/".join(parts) + ".py"


# Maps C# built-in primitive keyword types -> (QualifiedName, PEP-484 Annotation, Runtime isinstance type)
BUILTIN_PRIMITIVE_MAP: dict[str, tuple[str, str, str | None]] = {
    "void": ("void", "None", None),
    "bool": ("bool", "bool", "bool"),
    "int": ("int", "int", "int"),
    "long": ("long", "int", "int"),
    "float": ("float", "float", "(float, int)"),
    "double": ("double", "float", "(float, int)"),
    "decimal": ("decimal", "Decimal", "Decimal"),
    "string": ("PythonSharp.Core.String", "str", "str"),
    "object": ("object", "object", "object"),
    "dynamic": ("dynamic", "Any", None),
}


@dataclass(frozen=True, slots=True)
class ResolvedType:
    """Represents a fully resolved static and runtime type in PythonSharp."""
    qualified_name: str
    py_annotation: str
    runtime_isinstance_type: str | None = None
    symbol_id: SymbolId | None = None
    type_args: tuple[ResolvedType, ...] = ()
    is_nullable: bool = False
    is_primitive: bool = False
    is_interface: bool = False
    is_type_param: bool = False
    is_tuple: bool = False

    def with_nullable(self, nullable: bool = True) -> ResolvedType:
        if self.is_nullable == nullable:
            return self
        ann = self.py_annotation
        if nullable and not ann.endswith(" | None") and ann != "None" and ann != "Any":
            ann = f"{ann} | None"
        return ResolvedType(
            qualified_name=self.qualified_name,
            py_annotation=ann,
            runtime_isinstance_type=self.runtime_isinstance_type,
            symbol_id=self.symbol_id,
            type_args=self.type_args,
            is_nullable=nullable,
            is_primitive=self.is_primitive,
            is_interface=self.is_interface,
            is_type_param=self.is_type_param,
            is_tuple=self.is_tuple,
        )

    def runtime_erased_signature(self) -> str:
        """
        Returns the runtime-observable type key used by Pass 2B (Rule PS002)
        to detect ambiguous method overloads after generic type erasure.
        """
        if self.is_type_param or self.qualified_name in ("object", "dynamic"):
            return "object"
        if self.is_interface:
            return f"ps_interface:{self.qualified_name}"
        if self.runtime_isinstance_type:
            base = self.runtime_isinstance_type
        else:
            base = self.qualified_name
        return f"{base}?" if self.is_nullable else base


@dataclass(slots=True)
class MemberSymbol:
    """Registered symbol for a field, property, method, constructor, or indexer."""
    id: SymbolId
    name: str
    snake_name: str
    kind: Literal["field", "property", "method", "constructor", "indexer"]
    owner_type_id: SymbolId
    owner_qualified_name: str
    access: AccessMod
    setter_access: AccessMod | None
    is_static: bool
    is_async: bool
    is_extern: bool
    is_readonly: bool
    span: SourceSpan
    ast_node: MemberDecl | ParamDecl
    resolved_type: ResolvedType | None = None
    param_types: list[ResolvedType] = field(default_factory=list)
    param_names: list[str] = field(default_factory=list)
    min_arity: int = 0
    max_arity: int = 0
    has_varargs: bool = False
    has_kwargs: bool = False
    # Compiler intrinsic metadata from .d.ps attributes
    maps_to_py_name: str | None = None
    inline_template: str | None = None
    setter_inline_template: str | None = None
    linq_stage: str | None = None


@dataclass(slots=True)
class TypeSymbol:
    """Registered symbol for a top-level class, record, struct, interface, or enum."""
    id: SymbolId
    name: str
    qualified_name: str
    namespace: tuple[str, ...]
    assembly_name: str
    kind: TypeKind
    access: AccessMod
    span: SourceSpan
    ast_node: TypeDecl
    unit: CompilationUnit
    is_ambient_stub: bool
    type_params: list[str] = field(default_factory=list)

    # Resolved in Pass 1B (Inheritance & Interface Graph)
    base_type_symbols: list[TypeSymbol] = field(default_factory=list)
    base_type_refs: list[ResolvedType] = field(default_factory=list)

    # Extracted from attributes ([MapsTo], [RuntimeType], [SchemaModel], [NativeCompile])
    maps_to_py_type: str | None = None
    runtime_isinstance_type: str | None = None
    is_schema_model: bool = False
    is_native_compile: bool = False

    # Registered in Pass 1C
    members_by_name: dict[str, list[MemberSymbol]] = field(default_factory=dict)

    @property
    def is_primitive(self) -> bool:
        return self.kind in (
            TypeKind.PRIMITIVE_CLASS,
            TypeKind.PRIMITIVE_STRUCT,
            TypeKind.PRIMITIVE_INTERFACE,
        )

    @property
    def is_interface(self) -> bool:
        return self.kind in (TypeKind.INTERFACE, TypeKind.PRIMITIVE_INTERFACE)

    @property
    def is_record(self) -> bool:
        return self.kind in (TypeKind.RECORD, TypeKind.RECORD_STRUCT)

    @property
    def is_struct(self) -> bool:
        return self.kind in (
            TypeKind.STRUCT,
            TypeKind.RECORD_STRUCT,
            TypeKind.PRIMITIVE_STRUCT,
        )

    @property
    def is_enum(self) -> bool:
        return self.kind == TypeKind.ENUM

    def add_member(self, member: MemberSymbol) -> None:
        self.members_by_name.setdefault(member.name, []).append(member)

    def lookup_member(self, name: str, include_bases: bool = True) -> list[MemberSymbol]:
        found = list(self.members_by_name.get(name, ()))
        if include_bases:
            visited: set[SymbolId] = {self.id}
            queue = list(self.base_type_symbols)
            while queue:
                base = queue.pop(0)
                if base.id in visited:
                    continue
                visited.add(base.id)
                if name in base.members_by_name:
                    found.extend(base.members_by_name[name])
                queue.extend(base.base_type_symbols)
        return found

    def is_subclass_of(self, target_qname: str) -> bool:
        if self.qualified_name == target_qname:
            return True
        visited: set[SymbolId] = {self.id}
        queue = list(self.base_type_symbols)
        while queue:
            cur = queue.pop(0)
            if cur.qualified_name == target_qname:
                return True
            if cur.id not in visited:
                visited.add(cur.id)
                queue.extend(cur.base_type_symbols)
        return False


class GlobalSymbolTable:
    """
    Whole-project symbol table that aggregates types across arbitrary physical files
    by their logical `namespace` and resolves circular cross-file type references.
    """

    def __init__(self, default_assembly_name: str = "App") -> None:
        self.default_assembly_name = default_assembly_name
        self._next_symbol_id = 1
        self.types_by_id: dict[SymbolId, TypeSymbol] = {}
        self.types_by_qname: dict[str, TypeSymbol] = {}
        self.short_name_index: dict[str, list[TypeSymbol]] = {}
        self.namespaces: dict[tuple[str, ...], list[TypeSymbol]] = {}
        self.members_by_id: dict[SymbolId, MemberSymbol] = {}

    def allocate_symbol_id(self) -> SymbolId:
        sym_id = SymbolId(self._next_symbol_id)
        self._next_symbol_id += 1
        return sym_id

    def register_type(
        self,
        unit: CompilationUnit,
        decl: TypeDecl,
        assembly_name: str | None = None,
        maps_to_py_type: str | None = None,
        runtime_isinstance_type: str | None = None,
        is_schema_model: bool = False,
        is_native_compile: bool = False,
    ) -> TypeSymbol:
        ns_tuple = tuple(unit.namespace)
        qname = ".".join((*ns_tuple, decl.name)) if ns_tuple else decl.name

        sym_id = self.allocate_symbol_id()
        decl.symbol_id = sym_id

        type_sym = TypeSymbol(
            id=sym_id,
            name=decl.name,
            qualified_name=qname,
            namespace=ns_tuple,
            assembly_name=assembly_name or self.default_assembly_name,
            kind=decl.kind,
            access=decl.access,
            span=decl.span,
            ast_node=decl,
            unit=unit,
            is_ambient_stub=unit.is_ambient_stub,
            type_params=list(decl.type_params),
            maps_to_py_type=maps_to_py_type,
            runtime_isinstance_type=runtime_isinstance_type,
            is_schema_model=is_schema_model,
            is_native_compile=is_native_compile,
        )

        self.types_by_id[sym_id] = type_sym
        self.types_by_qname[qname] = type_sym
        self.short_name_index.setdefault(decl.name, []).append(type_sym)
        self.namespaces.setdefault(ns_tuple, []).append(type_sym)
        return type_sym

    def register_member(self, type_sym: TypeSymbol, member: MemberSymbol) -> None:
        self.members_by_id[member.id] = member
        type_sym.add_member(member)

    def lookup_type_in_context(
        self,
        path: list[str],
        current_ns: tuple[str, ...],
        imports: list[ImportDecl],
    ) -> TypeSymbol | None:
        """
        Resolves a type path (`Order` or `Commerce.Domain.Order`) using:
        1. Fully-qualified name match
        2. Current namespace + parent namespace prefixes
        3. Explicit `using Alias = Qualified.Type;`
        4. Imported `using Some.Namespace;` declarations
        5. Ambient `PythonSharp.Core` namespace
        """
        joined = ".".join(path)

        # 1. Exact qualified match
        if joined in self.types_by_qname:
            return self.types_by_qname[joined]

        # 2. Check alias imports: `using Dt = Commerce.Domain.Order;`
        if len(path) == 1:
            ident = path[0]
            for imp in imports:
                if not imp.is_extern and imp.alias == ident:
                    target_qname = ".".join(imp.path)
                    if target_qname in self.types_by_qname:
                        return self.types_by_qname[target_qname]

        # 3. Search current namespace and enclosing namespace prefixes
        for i in range(len(current_ns), 0, -1):
            prefix = ".".join(current_ns[:i])
            candidate = f"{prefix}.{joined}"
            if candidate in self.types_by_qname:
                return self.types_by_qname[candidate]

        # 4. Search imported `using <Namespace>;`
        for imp in imports:
            if not imp.is_extern and imp.alias is None:
                ns_prefix = ".".join(imp.path)
                candidate = f"{ns_prefix}.{joined}"
                if candidate in self.types_by_qname:
                    return self.types_by_qname[candidate]

        # 5. Implicitly search `PythonSharp.Core`
        core_candidate = f"PythonSharp.Core.{joined}"
        if core_candidate in self.types_by_qname:
            return self.types_by_qname[core_candidate]

        return None

    def resolve_type_ref(
        self,
        type_ref: TypeRef,
        current_ns: tuple[str, ...],
        imports: list[ImportDecl],
        active_type_params: set[str] | None = None,
    ) -> ResolvedType:
        """Resolves a syntactic `TypeRef` into a `ResolvedType`."""
        type_params = active_type_params or set()

        # 1. Tuple type `(int Id, string Name)`
        if type_ref.tuple_elements:
            elem_types = tuple(
                self.resolve_type_ref(elem_tr, current_ns, imports, type_params)
                for elem_tr, _ in type_ref.tuple_elements
            )
            inner_ann = ", ".join(e.py_annotation for e in elem_types)
            return ResolvedType(
                qualified_name=f"tuple[{inner_ann}]",
                py_annotation=f"tuple[{inner_ann}]",
                runtime_isinstance_type="tuple",
                type_args=elem_types,
                is_primitive=True,
                is_tuple=True,
            ).with_nullable(type_ref.is_nullable)

        joined = ".".join(type_ref.path)

        # 2. Generic type parameter (`T`, `TKey`, `TValue`)
        if len(type_ref.path) == 1 and joined in type_params:
            return ResolvedType(
                qualified_name=joined,
                py_annotation=joined,
                runtime_isinstance_type=None,
                is_type_param=True,
            ).with_nullable(type_ref.is_nullable)

        # 3. Built-in C# primitive keyword (`int`, `string`, `decimal`, `bool`, `void`)
        if type_ref.is_primitive_keyword or joined in BUILTIN_PRIMITIVE_MAP:
            qname, py_ann, rt_type = BUILTIN_PRIMITIVE_MAP[joined]
            sym = self.types_by_qname.get(qname)
            return ResolvedType(
                qualified_name=qname,
                py_annotation=py_ann,
                runtime_isinstance_type=rt_type,
                symbol_id=sym.id if sym else None,
                is_primitive=True,
            ).with_nullable(type_ref.is_nullable)

        # 4. Resolve generic type arguments recursively
        resolved_args = tuple(
            self.resolve_type_ref(arg, current_ns, imports, type_params)
            for arg in type_ref.type_args
        )

        # 5. Built-in callable delegates `Func<...>` and `Action<...>`
        if joined == "Func" and resolved_args:
            param_anns = ", ".join(a.py_annotation for a in resolved_args[:-1])
            ret_ann = resolved_args[-1].py_annotation
            return ResolvedType(
                qualified_name="PythonSharp.Core.Func",
                py_annotation=f"Callable[[{param_anns}], {ret_ann}]",
                runtime_isinstance_type=" collections.abc.Callable",
                type_args=resolved_args,
                is_primitive=True,
            ).with_nullable(type_ref.is_nullable)

        if joined == "Action":
            param_anns = ", ".join(a.py_annotation for a in resolved_args)
            return ResolvedType(
                qualified_name="PythonSharp.Core.Action",
                py_annotation=f"Callable[[{param_anns}], None]",
                runtime_isinstance_type="collections.abc.Callable",
                type_args=resolved_args,
                is_primitive=True,
            ).with_nullable(type_ref.is_nullable)

        # 6. Lookup user or stdlib TypeSymbol
        type_sym = self.lookup_type_in_context(type_ref.path, current_ns, imports)
        if type_sym is not None:
            base_py = type_sym.maps_to_py_type or type_sym.name
            rt_check = type_sym.runtime_isinstance_type or (
                type_sym.maps_to_py_type if type_sym.is_primitive else type_sym.name
            )

            # Special handling for Task / Task<T> -> coroutine return type annotation
            if type_sym.qualified_name == "PythonSharp.Core.Task":
                if resolved_args:
                    py_ann = resolved_args[0].py_annotation
                else:
                    py_ann = "None"
            elif resolved_args:
                args_str = ", ".join(a.py_annotation for a in resolved_args)
                py_ann = f"{base_py}[{args_str}]"
            else:
                py_ann = base_py

            return ResolvedType(
                qualified_name=type_sym.qualified_name,
                py_annotation=py_ann,
                runtime_isinstance_type=rt_check,
                symbol_id=type_sym.id,
                type_args=resolved_args,
                is_primitive=type_sym.is_primitive,
                is_interface=type_sym.is_interface,
            ).with_nullable(type_ref.is_nullable)

        # 7. External Python type (from `extern using`) or unresolved symbol fallback
        if resolved_args:
            args_str = ", ".join(a.py_annotation for a in resolved_args)
            fallback_ann = f"{joined}[{args_str}]"
        else:
            fallback_ann = joined

        return ResolvedType(
            qualified_name=joined,
            py_annotation=fallback_ann,
            runtime_isinstance_type=joined,
            type_args=resolved_args,
        ).with_nullable(type_ref.is_nullable)

```

---

### 4. `src/psc/semantics/collector.py`

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine
from psc.frontend.ast_nodes import (
    AccessMod,
    AttributeNode,
    CompilationUnit,
    ExprKind,
    FieldDecl,
    IndexerDecl,
    LiteralKind,
    MethodDecl,
    ParamDecl,
    PropertyDecl,
    TypeDecl,
    TypeKind,
)
from psc.semantics.symbols import (
    GlobalSymbolTable,
    MemberSymbol,
    TypeSymbol,
    namespace_to_module_path,
    pascal_to_snake,
)


class SymbolCollector:
    """
    Pass 1 of the PythonSharp Compiler (`psc`):
      - Sub-pass 1A: Scans all .ps and .d.ps files, assigns target Python module paths
        from logical `namespace` declarations, and registers all TypeSymbols globally.
      - Sub-pass 1B: Resolves base classes and implemented interfaces across all files,
        detecting illegal inheritance cycles while allowing circular type references.
      - Sub-pass 1C: Registers all fields, properties, constructors, methods, and indexers
        along with their resolved parameter/return types and compiler intrinsic attributes.
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        diagnostics: DiagnosticEngine,
    ) -> None:
        self.symtab = symtab
        self.diagnostics = diagnostics

    def collect_all(
        self,
        units: list[CompilationUnit],
        assembly_name: str | None = None,
    ) -> None:
        registered_types: list[TypeSymbol] = []

        # Sub-pass 1A: Register all type headers across all files
        for unit in units:
            ns_tuple = tuple(unit.namespace)
            unit.emitted_py_module_path = namespace_to_module_path(ns_tuple)
            for decl in unit.types:
                type_sym = self._register_type_decl(unit, decl, assembly_name)
                registered_types.append(type_sym)

        # Sub-pass 1B: Resolve inheritance hierarchies & verify acyclic base chains
        for type_sym in registered_types:
            self._resolve_base_types(type_sym)

        self._verify_no_inheritance_cycles(registered_types)

        # Sub-pass 1C: Register all members (fields, properties, primary ctors, methods, indexers)
        for type_sym in registered_types:
            self._collect_type_members(type_sym)

    # ========================================================================
    # SUB-PASS 1A: TYPE HEADER REGISTRATION & ATTRIBUTE EXTRACTION
    # ========================================================================

    def _register_type_decl(
        self,
        unit: CompilationUnit,
        decl: TypeDecl,
        assembly_name: str | None,
    ) -> TypeSymbol:
        maps_to = self._extract_string_attr(decl.attributes, ("MapsTo", "MapsToAttribute"))
        runtime_type = self._extract_string_attr(
            decl.attributes, ("RuntimeType", "RuntimeTypeAttribute")
        )
        is_schema = self._has_attr(decl.attributes, ("SchemaModel", "SchemaModelAttribute"))
        is_native = self._has_attr(decl.attributes, ("NativeCompile", "NativeCompileAttribute"))

        ns_tuple = tuple(unit.namespace)
        qname = ".".join((*ns_tuple, decl.name)) if ns_tuple else decl.name

        if qname in self.symtab.types_by_qname and not unit.is_ambient_stub:
            existing = self.symtab.types_by_qname[qname]
            if not existing.is_ambient_stub and "partial" not in decl.modifiers:
                self.diagnostics.report_syntax_error(
                    decl.span,
                    f"Duplicate type definition '{qname}' (already defined at {existing.span.format_location()}).",
                )

        asm = "PythonSharp.Core" if unit.is_ambient_stub else (assembly_name or self.symtab.default_assembly_name)
        return self.symtab.register_type(
            unit=unit,
            decl=decl,
            assembly_name=asm,
            maps_to_py_type=maps_to,
            runtime_isinstance_type=runtime_type or maps_to,
            is_schema_model=is_schema,
            is_native_compile=is_native,
        )

    # ========================================================================
    # SUB-PASS 1B: INHERITANCE & INTERFACE RESOLUTION
    # ========================================================================

    def _resolve_base_types(self, type_sym: TypeSymbol) -> None:
        decl = type_sym.ast_node
        active_tparams = set(type_sym.type_params)

        for base_ref in decl.base_types:
            resolved_base = self.symtab.resolve_type_ref(
                base_ref,
                current_ns=type_sym.namespace,
                imports=type_sym.unit.imports,
                active_type_params=active_tparams,
            )
            type_sym.base_type_refs.append(resolved_base)

            if resolved_base.symbol_id is not None:
                base_sym = self.symtab.types_by_id[resolved_base.symbol_id]
                type_sym.base_type_symbols.append(base_sym)

    def _verify_no_inheritance_cycles(self, types: list[TypeSymbol]) -> None:
        visited: set[ int ] = set()
        in_stack: set[ int ] = set()

        def dfs(sym: TypeSymbol, path: list[str]) -> bool:
            sid = sym.id.value
            if sid in in_stack:
                cycle_str = " -> ".join([*path, sym.qualified_name])
                self.diagnostics.report_syntax_error(
                    sym.span, f"Circular inheritance cycle detected: {cycle_str}"
                )
                return True
            if sid in visited:
                return False

            visited.add(sid)
            in_stack.add(sid)
            for base_sym in sym.base_type_symbols:
                if dfs(base_sym, [*path, sym.qualified_name]):
                    in_stack.remove(sid)
                    return True
            in_stack.remove(sid)
            return False

        for t in types:
            if t.id.value not in visited:
                dfs(t, [])

    # ========================================================================
    # SUB-PASS 1C: MEMBER SIGNATURE COLLECTION
    # ========================================================================

    def _collect_type_members(self, type_sym: TypeSymbol) -> None:
        decl = type_sym.ast_node
        class_tparams = set(type_sym.type_params)

        # 1. If this is a Record with primary constructor parameters, register properties + constructor
        if decl.kind in (TypeKind.RECORD, TypeKind.RECORD_STRUCT) and decl.primary_ctor_params:
            ctor_param_types = []
            ctor_param_names = []
            min_arity = 0

            for p in decl.primary_ctor_params:
                p_resolved = self.symtab.resolve_type_ref(
                    p.type_ref,
                    current_ns=type_sym.namespace,
                    imports=type_sym.unit.imports,
                    active_type_params=class_tparams,
                )
                p.symbol_id = self.symtab.allocate_symbol_id()
                p.emitted_snake_name = pascal_to_snake(p.name)
                ctor_param_types.append(p_resolved)
                ctor_param_names.append(p.emitted_snake_name)
                if p.default_value is None:
                    min_arity += 1

                # Register each primary parameter as a public property on the record
                prop_sym = MemberSymbol(
                    id=self.symtab.allocate_symbol_id(),
                    name=p.name,
                    snake_name=p.emitted_snake_name,
                    kind="property",
                    owner_type_id=type_sym.id,
                    owner_qualified_name=type_sym.qualified_name,
                    access=AccessMod.PUBLIC,
                    setter_access=AccessMod.PRIVATE if decl.kind == TypeKind.RECORD else AccessMod.PUBLIC,
                    is_static=False,
                    is_async=False,
                    is_extern=False,
                    is_readonly=(decl.kind == TypeKind.RECORD),
                    span=p.span,
                    ast_node=p,
                    resolved_type=p_resolved,
                )
                self.symtab.register_member(type_sym, prop_sym)

            # Register the synthesized primary constructor
            ctor_sym = MemberSymbol(
                id=self.symtab.allocate_symbol_id(),
                name=decl.name,
                snake_name="__init__",
                kind="constructor",
                owner_type_id=type_sym.id,
                owner_qualified_name=type_sym.qualified_name,
                access=AccessMod.PUBLIC,
                setter_access=None,
                is_static=False,
                is_async=False,
                is_extern=False,
                is_readonly=False,
                span=decl.span,
                ast_node=decl.primary_ctor_params[0],
                resolved_type=None,
                param_types=ctor_param_types,
                param_names=ctor_param_names,
                min_arity=min_arity,
                max_arity=len(ctor_param_types),
            )
            self.symtab.register_member(type_sym, ctor_sym)

        # 2. Register explicit members (fields, properties, constructors, methods, indexers)
        for member in decl.members:
            if isinstance(member, FieldDecl):
                self._register_field(type_sym, member, class_tparams)
            elif isinstance(member, PropertyDecl):
                self._register_property(type_sym, member, class_tparams)
            elif isinstance(member, IndexerDecl):
                self._register_indexer(type_sym, member, class_tparams)
            elif isinstance(member, MethodDecl):
                self._register_method_or_ctor(type_sym, member, class_tparams)

    def _register_field(
        self,
        type_sym: TypeSymbol,
        field_decl: FieldDecl,
        class_tparams: set[str],
    ) -> None:
        sym_id = self.symtab.allocate_symbol_id()
        field_decl.symbol_id = sym_id
        snake = pascal_to_snake(field_decl.name)
        if field_decl.access == AccessMod.PRIVATE and not snake.startswith("_"):
            snake = f"_{snake}"
        field_decl.emitted_snake_name = snake

        resolved_ty = self.symtab.resolve_type_ref(
            field_decl.type_ref,
            current_ns=type_sym.namespace,
            imports=type_sym.unit.imports,
            active_type_params=class_tparams,
        )

        mem_sym = MemberSymbol(
            id=sym_id,
            name=field_decl.name,
            snake_name=snake,
            kind="field",
            owner_type_id=type_sym.id,
            owner_qualified_name=type_sym.qualified_name,
            access=field_decl.access,
            setter_access=None if "readonly" in field_decl.modifiers else field_decl.access,
            is_static="static" in field_decl.modifiers,
            is_async=False,
            is_extern="extern" in field_decl.modifiers,
            is_readonly="readonly" in field_decl.modifiers,
            span=field_decl.span,
            ast_node=field_decl,
            resolved_type=resolved_ty,
        )
        self.symtab.register_member(type_sym, mem_sym)

    def _register_property(
        self,
        type_sym: TypeSymbol,
        prop_decl: PropertyDecl,
        class_tparams: set[str],
    ) -> None:
        sym_id = self.symtab.allocate_symbol_id()
        prop_decl.symbol_id = sym_id
        snake = pascal_to_snake(prop_decl.name)
        prop_decl.emitted_snake_name = snake

        resolved_ty = self.symtab.resolve_type_ref(
            prop_decl.type_ref,
            current_ns=type_sym.namespace,
            imports=type_sym.unit.imports,
            active_type_params=class_tparams,
        )

        setter_access: AccessMod | None = None
        is_auto_prop = False
        for acc in prop_decl.accessors:
            if acc.kind == "set":
                setter_access = acc.access or prop_decl.access
            if acc.body is None and acc.expr_body is None:
                is_auto_prop = True

        if (
            is_auto_prop
            and not type_sym.is_primitive
            and not type_sym.is_interface
            and "static" not in prop_decl.modifiers
        ):
            prop_decl.backing_slot_name = f"_{snake}"

        maps_to = self._extract_string_attr(prop_decl.attributes, ("MapsTo", "MapsToAttribute"))
        inline_tpl = self._extract_string_attr(
            prop_decl.attributes, ("InlineTemplate", "InlineTemplateAttribute")
        )

        mem_sym = MemberSymbol(
            id=sym_id,
            name=prop_decl.name,
            snake_name=maps_to or snake,
            kind="property",
            owner_type_id=type_sym.id,
            owner_qualified_name=type_sym.qualified_name,
            access=prop_decl.access,
            setter_access=setter_access,
            is_static="static" in prop_decl.modifiers,
            is_async=False,
            is_extern="extern" in prop_decl.modifiers or type_sym.is_primitive,
            is_readonly=(setter_access is None),
            span=prop_decl.span,
            ast_node=prop_decl,
            resolved_type=resolved_ty,
            maps_to_py_name=maps_to,
            inline_template=inline_tpl,
        )
        self.symtab.register_member(type_sym, mem_sym)

    def _register_indexer(
        self,
        type_sym: TypeSymbol,
        idx_decl: IndexerDecl,
        class_tparams: set[str],
    ) -> None:
        sym_id = self.symtab.allocate_symbol_id()
        idx_decl.symbol_id = sym_id

        resolved_ty = self.symtab.resolve_type_ref(
            idx_decl.type_ref,
            current_ns=type_sym.namespace,
            imports=type_sym.unit.imports,
            active_type_params=class_tparams,
        )
        param_types = []
        param_names = []
        for p in idx_decl.params:
            p.symbol_id = self.symtab.allocate_symbol_id()
            p.emitted_snake_name = pascal_to_snake(p.name)
            p_ty = self.symtab.resolve_type_ref(
                p.type_ref,
                current_ns=type_sym.namespace,
                imports=type_sym.unit.imports,
                active_type_params=class_tparams,
            )
            param_types.append(p_ty)
            param_names.append(p.emitted_snake_name)

        inline_tpl = self._extract_string_attr(
            idx_decl.attributes, ("InlineTemplate", "InlineTemplateAttribute")
        )
        setter_tpl: str | None = None
        setter_acc: AccessMod | None = None
        for acc in idx_decl.accessors:
            if acc.kind == "set":
                setter_acc = acc.access or idx_decl.access
                setter_tpl = self._extract_string_attr(
                    acc.attributes, ("InlineTemplate", "InlineTemplateAttribute")
                )

        mem_sym = MemberSymbol(
            id=sym_id,
            name="this[]",
            snake_name="__getitem__",
            kind="indexer",
            owner_type_id=type_sym.id,
            owner_qualified_name=type_sym.qualified_name,
            access=idx_decl.access,
            setter_access=setter_acc,
            is_static=False,
            is_async=False,
            is_extern="extern" in idx_decl.modifiers or type_sym.is_primitive,
            is_readonly=(setter_acc is None),
            span=idx_decl.span,
            ast_node=idx_decl,
            resolved_type=resolved_ty,
            param_types=param_types,
            param_names=param_names,
            min_arity=len(param_types),
            max_arity=len(param_types),
            inline_template=inline_tpl,
            setter_inline_template=setter_tpl,
        )
        self.symtab.register_member(type_sym, mem_sym)

    def _register_method_or_ctor(
        self,
        type_sym: TypeSymbol,
        method_decl: MethodDecl,
        class_tparams: set[str],
    ) -> None:
        sym_id = self.symtab.allocate_symbol_id()
        method_decl.symbol_id = sym_id
        active_tparams = class_tparams | set(method_decl.type_params)

        if method_decl.is_constructor:
            snake_name = "__init__"
            ret_type = None
        else:
            snake_name = pascal_to_snake(method_decl.name)
            assert method_decl.return_type is not None
            ret_type = self.symtab.resolve_type_ref(
                method_decl.return_type,
                current_ns=type_sym.namespace,
                imports=type_sym.unit.imports,
                active_type_params=active_tparams,
            )

        param_types = []
        param_names = []
        min_arity = 0
        has_varargs = False
        has_kwargs = False

        for p in method_decl.params:
            p.symbol_id = self.symtab.allocate_symbol_id()
            p.emitted_snake_name = pascal_to_snake(p.name)
            p_ty = self.symtab.resolve_type_ref(
                p.type_ref,
                current_ns=type_sym.namespace,
                imports=type_sym.unit.imports,
                active_type_params=active_tparams,
            )
            param_types.append(p_ty)
            param_names.append(p.emitted_snake_name)
            if p.is_params:
                has_varargs = True
            elif p.is_kwargs_dict:
                has_kwargs = True
            elif p.default_value is None:
                min_arity += 1

        max_arity = 999 if (has_varargs or has_kwargs) else len(param_types)

        maps_to = self._extract_string_attr(method_decl.attributes, ("MapsTo", "MapsToAttribute"))
        inline_tpl = self._extract_string_attr(
            method_decl.attributes, ("InlineTemplate", "InlineTemplateAttribute")
        )
        linq_stage = self._extract_string_attr(
            method_decl.attributes, ("LinqStage", "LinqStageAttribute")
        )

        mem_sym = MemberSymbol(
            id=sym_id,
            name=method_decl.name,
            snake_name=maps_to or snake_name,
            kind="constructor" if method_decl.is_constructor else "method",
            owner_type_id=type_sym.id,
            owner_qualified_name=type_sym.qualified_name,
            access=method_decl.access,
            setter_access=None,
            is_static="static" in method_decl.modifiers,
            is_async="async" in method_decl.modifiers,
            is_extern="extern" in method_decl.modifiers or type_sym.is_primitive,
            is_readonly=False,
            span=method_decl.span,
            ast_node=method_decl,
            resolved_type=ret_type,
            param_types=param_types,
            param_names=param_names,
            min_arity=min_arity,
            max_arity=max_arity,
            has_varargs=has_varargs,
            has_kwargs=has_kwargs,
            maps_to_py_name=maps_to,
            inline_template=inline_tpl,
            linq_stage=linq_stage,
        )
        self.symtab.register_member(type_sym, mem_sym)

    # ========================================================================
    # ATTRIBUTE EXTRACTION HELPERS
    # ========================================================================

    @staticmethod
    def _has_attr(attrs: list[AttributeNode], names: tuple[str, ...]) -> bool:
        return any(a.path[-1] in names for a in attrs)

    @staticmethod
    def _extract_string_attr(attrs: list[AttributeNode], names: tuple[str, ...]) -> str | None:
        for attr in attrs:
            if attr.path[-1] in names and attr.args:
                first_expr = attr.args[0].expr
                if (
                    first_expr.kind == ExprKind.LITERAL
                    and first_expr.data.get("literal_kind") == LiteralKind.STRING
                ):
                    return str(first_expr.data["value"])
        return None

```

---

### 5. `tests/test_symbol_collector.py`

```python
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

```

---

Shall we continue with the raw individual files for **Milestone 3 (Pass 2A: `access_checker.py` for Rule `PS001` `private`/`protected`/`internal` verification, `slot_analyzer.py` for deduplicated `__slots__`, `__ps_types__` nominal metadata, and `IDisposable` context manager synthesis)**?
