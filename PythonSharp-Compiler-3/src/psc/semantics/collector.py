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
        namespace_paths: dict[str, tuple[str, ...]] = {}

        # Sub-pass 1A: Register all type headers across all files
        for unit in units:
            ns_tuple = tuple(unit.namespace)
            module_path = namespace_to_module_path(ns_tuple)
            unit.emitted_py_module_path = module_path
            existing_ns = namespace_paths.get(module_path)
            if existing_ns is not None and existing_ns != ns_tuple and unit.types:
                self.diagnostics.report_syntax_error(
                    unit.types[0].span,
                    "Namespace path collision: "
                    f"'{'.'.join(existing_ns)}' and '{'.'.join(ns_tuple)}' "
                    f"both map to '{module_path}'.",
                )
            else:
                namespace_paths[module_path] = ns_tuple
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
        runtime_type = self._extract_string_attr(decl.attributes, ("RuntimeType", "RuntimeTypeAttribute"))
        is_schema = self._has_attr(decl.attributes, ("SchemaModel", "SchemaModelAttribute"))
        is_native = self._has_attr(decl.attributes, ("NativeCompile", "NativeCompileAttribute"))
        canon_api, bridge_api = self._extract_canonical_attr(decl.attributes)
        surface_level = self._extract_surface_level(decl.attributes)

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
            canonical_api=canon_api,
            bridge_api=bridge_api,
            surface_level=surface_level,
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
        visited: set[int] = set()
        in_stack: set[int] = set()

        def dfs(sym: TypeSymbol, path: list[str]) -> bool:
            sid = sym.id.value
            if sid in in_stack:
                cycle_str = " -> ".join([*path, sym.qualified_name])
                self.diagnostics.report_syntax_error(sym.span, f"Circular inheritance cycle detected: {cycle_str}")
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

        canon_api, bridge_api = self._extract_canonical_attr(field_decl.attributes)
        surface_level = self._extract_surface_level(field_decl.attributes)

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
            canonical_api=canon_api,
            bridge_api=bridge_api,
            surface_level=surface_level,
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
        inline_tpl = self._extract_string_attr(prop_decl.attributes, ("InlineTemplate", "InlineTemplateAttribute"))
        canon_api, bridge_api = self._extract_canonical_attr(prop_decl.attributes)
        surface_level = self._extract_surface_level(prop_decl.attributes)

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
            canonical_api=canon_api,
            bridge_api=bridge_api,
            surface_level=surface_level,
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

        inline_tpl = self._extract_string_attr(idx_decl.attributes, ("InlineTemplate", "InlineTemplateAttribute"))
        canon_api, bridge_api = self._extract_canonical_attr(idx_decl.attributes)
        surface_level = self._extract_surface_level(idx_decl.attributes)
        setter_tpl: str | None = None
        setter_acc: AccessMod | None = None
        for acc in idx_decl.accessors:
            if acc.kind == "set":
                setter_acc = acc.access or idx_decl.access
                setter_tpl = self._extract_string_attr(acc.attributes, ("InlineTemplate", "InlineTemplateAttribute"))

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
            canonical_api=canon_api,
            bridge_api=bridge_api,
            surface_level=surface_level,
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
        inline_tpl = self._extract_string_attr(method_decl.attributes, ("InlineTemplate", "InlineTemplateAttribute"))
        linq_stage = self._extract_string_attr(method_decl.attributes, ("LinqStage", "LinqStageAttribute"))
        canon_api, bridge_api = self._extract_canonical_attr(method_decl.attributes)
        surface_level = self._extract_surface_level(method_decl.attributes)

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
            canonical_api=canon_api,
            bridge_api=bridge_api,
            surface_level=surface_level,
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
                if first_expr.kind == ExprKind.LITERAL and first_expr.data.get("literal_kind") == LiteralKind.STRING:
                    return str(first_expr.data["value"])
        return None

    @staticmethod
    def _extract_canonical_attr(attrs: list[AttributeNode]) -> tuple[str | None, str | None]:
        for attr in attrs:
            if attr.path[-1] in ("CanonicalApi", "CanonicalApiAttribute") and attr.args:
                canon: str | None = None
                bridge: str | None = None
                first_expr = attr.args[0].expr
                if first_expr.kind == ExprKind.LITERAL and first_expr.data.get("literal_kind") == LiteralKind.STRING:
                    canon = str(first_expr.data["value"])
                if len(attr.args) > 1:
                    second_expr = attr.args[1].expr
                    if second_expr.kind == ExprKind.LITERAL and second_expr.data.get("literal_kind") == LiteralKind.STRING:
                        bridge = str(second_expr.data["value"])
                return canon, bridge
        return None, None

    @staticmethod
    def _extract_surface_level(attrs: list[AttributeNode]) -> int:
        for attr in attrs:
            if attr.path[-1] in ("SurfaceLevel", "SurfaceLevelAttribute") and attr.args:
                first_expr = attr.args[0].expr
                if first_expr.kind == ExprKind.LITERAL and first_expr.data.get("literal_kind") == LiteralKind.INT:
                    return int(first_expr.data["value"])
        return 0
