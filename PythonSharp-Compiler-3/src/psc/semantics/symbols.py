from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
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

_SNAKE_1 = re.compile(r"([^_])([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z])([A-Z])")
_SNAKE_DIGIT = re.compile(r"([A-Za-z])([0-9])")


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
    s1 = _SNAKE_DIGIT.sub(r"\1_\2", core)
    s1 = _SNAKE_1.sub(r"\1_\2", s1)
    s2 = _SNAKE_2.sub(r"\1_\2", s1).lower()
    result = f"{leading}{s2}"
    return f"{result}_" if keyword.iskeyword(result) else result


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
    "Bytes": ("PythonSharp.Core.Bytes", "bytes", "bytes"),
    "bytes": ("PythonSharp.Core.Bytes", "bytes", "bytes"),
    "byte[]": ("PythonSharp.Core.Bytes", "bytes", "bytes"),
    "Complex": ("PythonSharp.Core.Complex", "complex", "complex"),
    "complex": ("PythonSharp.Core.Complex", "complex", "complex"),
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
        if nullable:
            if not ann.endswith(" | None") and ann != "None" and ann != "Any":
                ann = f"{ann} | None"
        elif ann.endswith(" | None"):
            ann = ann.removesuffix(" | None")
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
    canonical_api: str | None = None
    bridge_api: str | None = None
    surface_level: int = 0


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

    # Extracted from attributes ([MapsTo], [RuntimeType], [SchemaModel], [NativeCompile], [CanonicalApi], [SurfaceLevel])
    maps_to_py_type: str | None = None
    runtime_isinstance_type: str | None = None
    is_schema_model: bool = False
    is_native_compile: bool = False
    canonical_api: str | None = None
    bridge_api: str | None = None
    surface_level: int = 0

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
        canonical_api: str | None = None,
        bridge_api: str | None = None,
        surface_level: int = 0,
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
            canonical_api=canonical_api,
            bridge_api=bridge_api,
            surface_level=surface_level,
        )

        self.types_by_id[sym_id] = type_sym
        self.types_by_qname[qname] = type_sym
        self.short_name_index.setdefault(decl.name, []).append(type_sym)
        self.namespaces.setdefault(ns_tuple, []).append(type_sym)

        # Enterprise alias registrations for Numerics domain sub-namespaces
        if qname == "PythonSharp.Numerics.ArrayFactory":
            self.types_by_qname["PythonSharp.Numerics.Creation.ArrayFactory"] = type_sym
        elif qname == "PythonSharp.Numerics.MatrixOperations":
            self.types_by_qname["PythonSharp.Numerics.LinearAlgebra.MatrixOperations"] = type_sym
        elif qname == "PythonSharp.Numerics.RandomTensorGenerator":
            self.types_by_qname["PythonSharp.Numerics.Random.RandomTensorGenerator"] = type_sym
        elif qname == "PythonSharp.Numerics.ElementWiseMath":
            self.types_by_qname["PythonSharp.Numerics.Mathematics.ElementWiseMath"] = type_sym
        elif qname == "PythonSharp.Numerics.TensorManipulation":
            self.types_by_qname["PythonSharp.Numerics.Manipulation.TensorManipulation"] = type_sym
        elif qname == "contextlib.subprocess":
            self.types_by_qname["subprocess.subprocess"] = type_sym
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
                if "." in ns_prefix:
                    parent_ns = ns_prefix.rsplit(".", 1)[0]
                    parent_candidate = f"{parent_ns}.{joined}"
                    if parent_candidate in self.types_by_qname:
                        return self.types_by_qname[parent_candidate]

        # 5. Implicitly search `PythonSharp.Core`
        core_candidate = f"PythonSharp.Core.{joined}"
        if core_candidate in self.types_by_qname:
            return self.types_by_qname[core_candidate]

        # 6. Check built-in primitive aliases
        if joined in BUILTIN_PRIMITIVE_MAP:
            mapped_qname = BUILTIN_PRIMITIVE_MAP[joined][0]
            if mapped_qname in self.types_by_qname:
                return self.types_by_qname[mapped_qname]
        if joined == "int" and "PythonSharp.Core.Int32" in self.types_by_qname:
            return self.types_by_qname["PythonSharp.Core.Int32"]
        if joined == "double" and "PythonSharp.Core.Double" in self.types_by_qname:
            return self.types_by_qname["PythonSharp.Core.Double"]
        if joined == "bool" and "PythonSharp.Core.Boolean" in self.types_by_qname:
            return self.types_by_qname["PythonSharp.Core.Boolean"]

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
            self.resolve_type_ref(arg, current_ns, imports, type_params) for arg in type_ref.type_args
        )

        # 5. Built-in callable delegates `Func<...>` and `Action<...>`
        if joined == "Func" and resolved_args:
            param_anns = ", ".join(a.py_annotation for a in resolved_args[:-1])
            ret_ann = resolved_args[-1].py_annotation
            return ResolvedType(
                qualified_name="PythonSharp.Core.Func",
                py_annotation=f"Callable[[{param_anns}], {ret_ann}]",
                runtime_isinstance_type="collections.abc.Callable",
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
