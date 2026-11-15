Here are the raw individual files for **Milestone 4 (Pass 2B: `primitive_resolver.py` for `[MapsTo]` and `[InlineTemplate]` type erasure, `overload_resolver.py` for `@overload` dispatch table synthesis and Rule `PS002` runtime collision detection, `linq_fuser.py` for `.Where().Select().ToList()` comprehension fusion with lambda alpha-renaming, updated `src/psc/semantics/__init__.py`, and `tests/test_overloads_and_linq.py`)** of the **PythonSharp Prototype Transpiler (`psc`)**.

---

##### 1. src/psc/semantics/primitive_resolver.py

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine
from psc.frontend.ast_nodes import (
    AttributeNode,
    BlockStmt,
    CompilationUnit,
    Expr,
    ExprKind,
    FieldDecl,
    ForEachStmt,
    IfStmt,
    IndexerDecl,
    LiteralKind,
    LocalVarStmt,
    MemberLoweringMode,
    MethodDecl,
    ParamDecl,
    PropertyDecl,
    ReturnStmt,
    Stmt,
    SwitchStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    TypeDecl,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.symbols import GlobalSymbolTable, MemberSymbol, TypeSymbol, pascal_to_snake


INTRINSIC_ATTR_NAMES = frozenset(
    {
        "MapsTo",
        "MapsToAttribute",
        "InlineTemplate",
        "InlineTemplateAttribute",
        "RuntimeType",
        "RuntimeTypeAttribute",
        "KwArgs",
        "KwArgsAttribute",
        "LinqStage",
        "LinqStageAttribute",
        "PythonDecorator",
        "PythonDecoratorAttribute",
        "SchemaModel",
        "SchemaModelAttribute",
        "NativeCompile",
        "NativeCompileAttribute",
    }
)


class PrimitiveResolver:
    """
    Pass 2B (Part 1) — Primitive Type Erasure & Member Attribute Resolver:
      1. Populates `MemberLoweringMode` (`PrimitiveInlineTemplate`, `PrimitiveDirect`,
         or `StandardPython`) on every `PropertyDecl`, `IndexerDecl`, and `MethodDecl`.
      2. Detects `[KwArgs]` on parameters (`param.is_kwargs_dict = True`).
      3. Detects `yield return` / `yield break` inside method bodies (`method.is_generator = True`).
      4. Lowers non-intrinsic C# `[Attributes]` into Python `@decorator` expressions.
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        diagnostics: DiagnosticEngine,
    ) -> None:
        self.symtab = symtab
        self.diagnostics = diagnostics

    def resolve_all(self, units: list[CompilationUnit]) -> None:
        for unit in units:
            for decl in unit.types:
                if decl.symbol_id is not None and decl.symbol_id in self.symtab.types_by_id:
                    type_sym = self.symtab.types_by_id[decl.symbol_id]
                    self.resolve_type(type_sym)

    def resolve_type(self, type_sym: TypeSymbol) -> None:
        decl = type_sym.ast_node
        decl.decorators_to_emit = self._extract_python_decorators(decl.attributes)

        for member in decl.members:
            if isinstance(member, PropertyDecl):
                member.lowering_mode = self.resolve_property_lowering(type_sym, member)
            elif isinstance(member, IndexerDecl):
                member.lowering_mode = self.resolve_indexer_lowering(type_sym, member)
            elif isinstance(member, MethodDecl):
                self._resolve_method_params_and_decorators(member)
                member.lowering_mode = self.resolve_method_lowering(type_sym, member)
                if member.body is not None:
                    member.is_generator = self._stmt_contains_yield(member.body)

    def resolve_property_lowering(
        self,
        type_sym: TypeSymbol,
        prop: PropertyDecl,
    ) -> MemberLoweringMode:
        inline_tpl = self._extract_string_attr(
            prop.attributes, ("InlineTemplate", "InlineTemplateAttribute")
        )
        if inline_tpl is not None:
            return MemberLoweringMode(
                kind="PrimitiveInlineTemplate",
                emitted_snake_name=prop.emitted_snake_name,
                inline_template=inline_tpl,
            )

        maps_to = self._extract_string_attr(prop.attributes, ("MapsTo", "MapsToAttribute"))
        if maps_to is not None or type_sym.is_primitive:
            target = maps_to or prop.emitted_snake_name
            return MemberLoweringMode(
                kind="PrimitiveDirect",
                emitted_snake_name=target,
                py_target_name=target,
            )

        return MemberLoweringMode(
            kind="StandardPython",
            emitted_snake_name=prop.emitted_snake_name,
        )

    def resolve_indexer_lowering(
        self,
        type_sym: TypeSymbol,
        indexer: IndexerDecl,
    ) -> MemberLoweringMode:
        inline_tpl = self._extract_string_attr(
            indexer.attributes, ("InlineTemplate", "InlineTemplateAttribute")
        )
        if inline_tpl is not None:
            return MemberLoweringMode(
                kind="PrimitiveInlineTemplate",
                emitted_snake_name="__getitem__",
                inline_template=inline_tpl,
            )

        return MemberLoweringMode(
            kind="StandardPython",
            emitted_snake_name="__getitem__",
        )

    def resolve_method_lowering(
        self,
        type_sym: TypeSymbol,
        method: MethodDecl,
    ) -> MemberLoweringMode:
        snake = "__init__" if method.is_constructor else pascal_to_snake(method.name)

        inline_tpl = self._extract_string_attr(
            method.attributes, ("InlineTemplate", "InlineTemplateAttribute")
        )
        if inline_tpl is not None:
            return MemberLoweringMode(
                kind="PrimitiveInlineTemplate",
                emitted_snake_name=snake,
                inline_template=inline_tpl,
            )

        maps_to = self._extract_string_attr(method.attributes, ("MapsTo", "MapsToAttribute"))
        if maps_to is not None or (type_sym.is_primitive and not method.is_constructor):
            target = maps_to or snake
            return MemberLoweringMode(
                kind="PrimitiveDirect",
                emitted_snake_name=target,
                py_target_name=target,
            )

        return MemberLoweringMode(
            kind="StandardPython",
            emitted_snake_name=snake,
        )

    def _resolve_method_params_and_decorators(self, method: MethodDecl) -> None:
        method.decorators_to_emit = self._extract_python_decorators(method.attributes)
        for p in method.params:
            if self._has_attr(p.attributes, ("KwArgs", "KwArgsAttribute")):
                p.is_kwargs_dict = True

    def _extract_python_decorators(self, attrs: list[AttributeNode]) -> list[Expr]:
        decorators: list[Expr] = []
        for attr in attrs:
            short_name = attr.path[-1]
            if short_name in INTRINSIC_ATTR_NAMES:
                continue
            # Convert `[MyDecorator(arg1, key = val)]` into a CALL or IDENT Expr for Pass 3
            snake_path = [pascal_to_snake(seg) for seg in attr.path]
            callee = Expr(span=attr.span, kind=ExprKind.IDENT, data={"name": snake_path[0]})
            for seg in snake_path[1:]:
                callee = Expr(
                    span=attr.span,
                    kind=ExprKind.MEMBER_ACCESS,
                    data={"target": callee, "member": seg, "type_args": []},
                )
            if attr.args:
                from psc.frontend.ast_nodes import ArgNode

                call_args = [
                    ArgNode(
                        span=a.span,
                        name=pascal_to_snake(a.name) if a.name else None,
                        expr=a.expr,
                    )
                    for a in attr.args
                ]
                decorators.append(
                    Expr(
                        span=attr.span,
                        kind=ExprKind.CALL,
                        data={"callee": callee, "args": call_args, "type_args": []},
                    )
                )
            else:
                decorators.append(callee)
        return decorators

    def _stmt_contains_yield(self, stmt: Stmt) -> bool:
        if isinstance(stmt, YieldStmt):
            return True
        if isinstance(stmt, BlockStmt):
            return any(self._stmt_contains_yield(s) for s in stmt.statements)
        if isinstance(stmt, IfStmt):
            return self._stmt_contains_yield(stmt.then_branch) or (
                stmt.else_branch is not None and self._stmt_contains_yield(stmt.else_branch)
            )
        if isinstance(stmt, WhileStmt):
            return self._stmt_contains_yield(stmt.body)
        if isinstance(stmt, ForEachStmt):
            return self._stmt_contains_yield(stmt.body)
        if isinstance(stmt, TryCatchFinallyStmt):
            if self._stmt_contains_yield(stmt.try_block):
                return True
            for c in stmt.catches:
                if c.body and self._stmt_contains_yield(c.body):
                    return True
            if stmt.finally_block and self._stmt_contains_yield(stmt.finally_block):
                return True
        if isinstance(stmt, SwitchStmt):
            for sec in stmt.sections:
                if any(self._stmt_contains_yield(s) for s in sec.statements):
                    return True
        return False

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

##### 2. src/psc/semantics/overload_resolver.py

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend.ast_nodes import (
    BinaryOp,
    BlockStmt,
    CompilationUnit,
    Expr,
    ExprKind,
    ExprStmt,
    FieldDecl,
    ForEachStmt,
    IfStmt,
    IndexerDecl,
    LiteralKind,
    LocalVarStmt,
    MemberLoweringMode,
    MethodDecl,
    OverloadDispatchGroup,
    OverloadGuard,
    PropertyDecl,
    ReturnStmt,
    RuntimeTypeCheck,
    Stmt,
    SwitchStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    TypeRef,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.symbols import (
    BUILTIN_PRIMITIVE_MAP,
    GlobalSymbolTable,
    MemberSymbol,
    ResolvedType,
    TypeSymbol,
    pascal_to_snake,
)


class OverloadResolver:
    """
    Pass 2B (Part 2) — Method & Constructor Overload Dispatcher + Call-Site Resolver:
      1. Groups methods/constructors sharing a name on a non-primitive `TypeDecl`
         into `OverloadDispatchGroup` descriptors.
      2. Computes `is_strictly_arity_disjoint` and per-variant `OverloadGuard` runtime
         checks (`isinstance(arg, ...)` or `"Interface" in getattr(arg, "__ps_types__", ())`).
      3. Enforces Rule PS002 when two overloads share an arity and erase to identical
         Python runtime types (e.g., `Process(List<int>)` vs `Process(List<string>)`).
      4. Walks all statements and expressions in user `.ps` files to populate
         `Expr.resolved_type` and `Expr.resolved_lowering` (`MemberLoweringMode`).
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        diagnostics: DiagnosticEngine,
    ) -> None:
        self.symtab = symtab
        self.diagnostics = diagnostics

    def resolve_all(self, units: list[CompilationUnit]) -> None:
        # Step 1: Build overload dispatch groups on all types
        for unit in units:
            for decl in unit.types:
                if decl.symbol_id is not None and decl.symbol_id in self.symtab.types_by_id:
                    type_sym = self.symtab.types_by_id[decl.symbol_id]
                    decl.overload_groups = self.build_overload_groups(type_sym)

        # Step 2: Resolve all call sites, member accesses, and `new` expressions in user units
        for unit in units:
            if unit.is_ambient_stub:
                continue
            for decl in unit.types:
                if decl.symbol_id is not None and decl.symbol_id in self.symtab.types_by_id:
                    type_sym = self.symtab.types_by_id[decl.symbol_id]
                    self.resolve_type_bodies(type_sym)

    # ========================================================================
    # 1. OVERLOAD GROUP SYNTHESIS & RULE PS002 COLLISION DETECTION
    # ========================================================================

    def build_overload_groups(self, type_sym: TypeSymbol) -> list[OverloadDispatchGroup]:
        if type_sym.is_primitive or type_sym.is_interface or type_sym.is_enum:
            return []

        decl = type_sym.ast_node
        methods_by_snake: dict[str, list[tuple[MethodDecl, MemberSymbol]]] = {}

        for member in decl.members:
            if isinstance(member, MethodDecl) and member.symbol_id is not None:
                mem_sym = self.symtab.members_by_id.get(member.symbol_id)
                if mem_sym is None:
                    continue
                snake = "__init__" if member.is_constructor else pascal_to_snake(member.name)
                methods_by_snake.setdefault(snake, []).append((member, mem_sym))

        groups: list[OverloadDispatchGroup] = []

        for snake_name, pairs in methods_by_snake.items():
            if len(pairs) == 1:
                # Single method/constructor: no runtime @overload dispatch needed
                single_decl, _ = pairs[0]
                if single_decl.lowering_mode.kind == "Unresolved":
                    single_decl.lowering_mode = MemberLoweringMode(
                        kind="StandardPython",
                        emitted_snake_name=snake_name,
                    )
                continue

            # Multiple overloads sharing the same name!
            arity_Disjoint = self._are_strictly_arity_disjoint([m_sym for _, m_sym in pairs])
            self._verify_no_ps002_erasure_collisions(type_sym, pairs)

            variant_ids = []
            for idx, (m_decl, m_sym) in enumerate(pairs):
                guard = self._build_overload_guard(m_sym)
                m_decl.lowering_mode = MemberLoweringMode(
                    kind="OverloadedVariant",
                    emitted_snake_name=snake_name,
                    overload_index=idx,
                    runtime_guard=guard,
                )
                variant_ids.append(m_sym.id)

            groups.append(
                OverloadDispatchGroup(
                    snake_name=snake_name,
                    variants=variant_ids,
                    is_strictly_arity_disjoint=arity_Disjoint,
                )
            )

        return groups

    @staticmethod
    def _are_strictly_arity_disjoint(variants: list[MemberSymbol]) -> bool:
        """Returns True if no two variants can ever be invoked with the same argument count."""
        for i in range(len(variants)):
            for j in range(i + 1, len(variants)):
                a = variants[i]
                b = variants[j]
                if max(a.min_arity, b.min_arity) <= min(a.max_arity, b.max_arity):
                    return False
        return True

    def _build_overload_guard(self, mem_sym: MemberSymbol) -> OverloadGuard:
        checks: list[tuple[int, RuntimeTypeCheck]] = []
        for idx, p_ty in enumerate(mem_sym.param_types):
            rt_check = self._compute_runtime_type_check(p_ty)
            if rt_check.kind != "NoneRequired":
                checks.append((idx, rt_check))
        return OverloadGuard(
            min_arity=mem_sym.min_arity,
            max_arity=mem_sym.max_arity,
            param_type_checks=checks,
        )

    def _compute_runtime_type_check(self, resolved_ty: ResolvedType) -> RuntimeTypeCheck:
        if resolved_ty.is_type_param or resolved_ty.py_annotation in ("Any", "object"):
            return RuntimeTypeCheck(kind="NoneRequired", target_type="object")

        if resolved_ty.symbol_id is not None and resolved_ty.symbol_id in self.symtab.types_by_id:
            target_sym = self.symtab.types_by_id[resolved_ty.symbol_id]
            if target_sym.is_interface and not target_sym.is_primitive:
                return RuntimeTypeCheck(
                    kind="PsTypesContains",
                    target_type=target_sym.qualified_name,
                )

        rt_type = resolved_ty.runtime_isinstance_type or resolved_ty.py_annotation
        return RuntimeTypeCheck(kind="PyIsInstance", target_type=rt_type)

    def _verify_no_ps002_erasure_collisions(
        self,
        owner_type: TypeSymbol,
        pairs: list[tuple[MethodDecl, MemberSymbol]],
    ) -> None:
        """
        Checks every pair of overloaded methods with overlapping arities.
        If their runtime parameter checks (`isinstance` / `__ps_types__`) are identical
        for any shared arity `k`, reports compile-time error PS002.
        """
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                decl_a, sym_a = pairs[i]
                decl_b, sym_b = pairs[j]
                overlap_min = max(sym_a.min_arity, sym_b.min_arity)
                overlap_max = min(sym_a.max_arity, sym_b.max_arity)
                if overlap_min > overlap_max:
                    continue

                # Check at the smallest overlapping arity `k = overlap_min`
                k = overlap_min
                if k <= len(sym_a.param_types) and k <= len(sym_b.param_types):
                    erased_a = [
                        self._erased_runtime_token(sym_a.param_types[p]) for p in range(k)
                    ]
                    erased_b = [
                        self._erased_runtime_token(sym_b.param_types[p]) for p in range(k)
                    ]
                    if erased_a == erased_b:
                        sig_a = self._format_signature(decl_a)
                        sig_b = self._format_signature(decl_b)
                        erased_str = ", ".join(erased_a) if erased_a else "()"
                        self.diagnostics.report_ps002_ambiguous_overload(
                            span=decl_b.span,
                            method_name=f"{owner_type.name}.{decl_b.name}",
                            sig_a=sig_a,
                            sig_b=sig_b,
                            erased_py_type=erased_str,
                        )

    def _erased_runtime_token(self, ty: ResolvedType) -> str:
        check = self._compute_runtime_type_check(ty)
        null_suffix = "?" if ty.is_nullable else ""
        return f"{check.kind}:{check.target_type}{null_suffix}"

    @staticmethod
    def _format_signature(decl: MethodDecl) -> str:
        params_str = ", ".join(f"{p.type_ref.display_name()} {p.name}" for p in decl.params)
        return f"{decl.name}({params_str})"

    # ========================================================================
    # 2. CALL-SITE & EXPRESSION SEMANTIC DECORATION
    # ========================================================================

    def resolve_type_bodies(self, type_sym: TypeSymbol) -> None:
        decl = type_sym.ast_node
        active_tparams = set(type_sym.type_params)

        for member in decl.members:
            if isinstance(member, FieldDecl) and member.initializer is not None:
                self._resolve_expr(member.initializer, type_sym, {})
            elif isinstance(member, PropertyDecl):
                if member.initializer is not None:
                    self._resolve_expr(member.initializer, type_sym, {})
                if member.expr_body is not None:
                    self._resolve_expr(member.expr_body, type_sym, {})
                prop_ty = self.symtab.resolve_type_ref(
                    member.type_ref,
                    current_ns=type_sym.namespace,
                    imports=type_sym.unit.imports,
                    active_type_params=active_tparams,
                )
                for acc in member.accessors:
                    env = {"value": prop_ty} if acc.kind == "set" else {}
                    if acc.body is not None:
                        self._resolve_stmt(acc.body, type_sym, env)
                    if acc.expr_body is not None:
                        self._resolve_expr(acc.expr_body, type_sym, env)
            elif isinstance(member, IndexerDecl):
                base_env: dict[str, ResolvedType] = {}
                for p in member.params:
                    base_env[p.name] = self.symtab.resolve_type_ref(
                        p.type_ref,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=active_tparams,
                    )
                idx_ty = self.symtab.resolve_type_ref(
                    member.type_ref,
                    current_ns=type_sym.namespace,
                    imports=type_sym.unit.imports,
                    active_type_params=active_tparams,
                )
                for acc in member.accessors:
                    env = dict(base_env)
                    if acc.kind == "set":
                        env["value"] = idx_ty
                    if acc.body is not None:
                        self._resolve_stmt(acc.body, type_sym, env)
                    if acc.expr_body is not None:
                        self._resolve_expr(acc.expr_body, type_sym, env)
            elif isinstance(member, MethodDecl):
                method_tparams = active_tparams | set(member.type_params)
                env = {}
                for p in member.params:
                    env[p.name] = self.symtab.resolve_type_ref(
                        p.type_ref,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=method_tparams,
                    )
                    if p.default_value is not None:
                        self._resolve_expr(p.default_value, type_sym, env)
                if member.ctor_chain is not None:
                    for arg in member.ctor_chain.args:
                        self._resolve_expr(arg.expr, type_sym, env)
                if member.body is not None:
                    self._resolve_stmt(member.body, type_sym, env)
                if member.expr_body is not None:
                    self._resolve_expr(member.expr_body, type_sym, env)

    def _resolve_stmt(
        self,
        stmt: Stmt,
        caller_type: TypeSymbol,
        env: dict[str, ResolvedType],
    ) -> None:
        if isinstance(stmt, BlockStmt):
            inner_env = dict(env)
            for s in stmt.statements:
                self._resolve_stmt(s, caller_type, inner_env)
        elif isinstance(stmt, LocalVarStmt):
            init_ty = self._resolve_expr(stmt.initializer, caller_type, env)
            if stmt.type_ref is not None:
                env[stmt.name] = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
            elif init_ty is not None:
                env[stmt.name] = init_ty
        elif isinstance(stmt, UsingResourceStmt):
            init_ty = self._resolve_expr(stmt.initializer, caller_type, env)
            if stmt.type_ref is not None:
                env[stmt.name] = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
            elif init_ty is not None:
                env[stmt.name] = init_ty
        elif isinstance(stmt, IfStmt):
            self._resolve_expr(stmt.condition, caller_type, env)
            self._resolve_stmt(stmt.then_branch, caller_type, dict(env))
            if stmt.else_branch is not None:
                self._resolve_stmt(stmt.else_branch, caller_type, dict(env))
        elif isinstance(stmt, WhileStmt):
            self._resolve_expr(stmt.condition, caller_type, env)
            self._resolve_stmt(stmt.body, caller_type, dict(env))
        elif isinstance(stmt, ForEachStmt):
            coll_ty = self._resolve_expr(stmt.collection, caller_type, env)
            loop_env = dict(env)
            if stmt.type_ref is not None:
                loop_env[stmt.item_name] = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
            elif coll_ty is not None and coll_ty.type_args:
                loop_env[stmt.item_name] = coll_ty.type_args[0]
            self._resolve_stmt(stmt.body, caller_type, loop_env)
        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                self._resolve_expr(stmt.value, caller_type, env)
        elif isinstance(stmt, YieldStmt):
            if stmt.value is not None:
                self._resolve_expr(stmt.value, caller_type, env)
        elif isinstance(stmt, ThrowStmt):
            if stmt.exception is not None:
                self._resolve_expr(stmt.exception, caller_type, env)
        elif isinstance(stmt, TryCatchFinallyStmt):
            self._resolve_stmt(stmt.try_block, caller_type, dict(env))
            for c in stmt.catches:
                c_env = dict(env)
                if c.exception_type is not None and c.bind_name:
                    c_env[c.bind_name] = self.symtab.resolve_type_ref(
                        c.exception_type,
                        current_ns=caller_type.namespace,
                        imports=caller_type.unit.imports,
                        active_type_params=set(caller_type.type_params),
                    )
                if c.when_guard is not None:
                    self._resolve_expr(c.when_guard, caller_type, c_env)
                if c.body is not None:
                    self._resolve_stmt(c.body, caller_type, c_env)
            if stmt.finally_block is not None:
                self._resolve_stmt(stmt.finally_block, caller_type, dict(env))
        elif isinstance(stmt, SwitchStmt):
            self._resolve_expr(stmt.scrutinee, caller_type, env)
            for sec in stmt.sections:
                sec_env = dict(env)
                for pat, guard in sec.labels:
                    if pat is not None and pat.type_ref is not None and pat.bind_name:
                        sec_env[pat.bind_name] = self.symtab.resolve_type_ref(
                            pat.type_ref,
                            current_ns=caller_type.namespace,
                            imports=caller_type.unit.imports,
                            active_type_params=set(caller_type.type_params),
                        )
                    if guard is not None:
                        self._resolve_expr(guard, caller_type, sec_env)
                for s in sec.statements:
                    self._resolve_stmt(s, caller_type, sec_env)
        elif isinstance(stmt, ExprStmt):
            self._resolve_expr(stmt.expr, caller_type, env)

    def _resolve_expr(
        self,
        expr: Expr | None,
        caller_type: TypeSymbol,
        env: dict[str, ResolvedType],
    ) -> ResolvedType | None:
        if expr is None:
            return None

        kind = expr.kind

        if kind == ExprKind.LITERAL:
            lit_kind = expr.data.get("literal_kind")
            lit_map = {
                LiteralKind.INT: "int",
                LiteralKind.FLOAT: "double",
                LiteralKind.DECIMAL: "decimal",
                LiteralKind.STRING: "string",
                LiteralKind.BOOL: "bool",
            }
            if lit_kind in lit_map:
                qname, py_ann, rt = BUILTIN_PRIMITIVE_MAP[lit_map[lit_kind]]
                sym = self.symtab.types_by_qname.get(qname)
                res = ResolvedType(
                    qualified_name=qname,
                    py_annotation=py_ann,
                    runtime_isinstance_type=rt,
                    symbol_id=sym.id if sym else None,
                    is_primitive=True,
                )
                expr.resolved_type = res.py_annotation
                return res
            return None

        if kind == ExprKind.THIS:
            res = ResolvedType(
                qualified_name=caller_type.qualified_name,
                py_annotation=caller_type.name,
                runtime_isinstance_type=caller_type.name,
                symbol_id=caller_type.id,
            )
            expr.resolved_type = res.py_annotation
            return res

        if kind == ExprKind.BASE:
            if caller_type.base_type_symbols:
                b = caller_type.base_type_symbols[0]
                res = ResolvedType(
                    qualified_name=b.qualified_name,
                    py_annotation=b.name,
                    runtime_isinstance_type=b.name,
                    symbol_id=b.id,
                )
                expr.resolved_type = res.py_annotation
                return res
            return None

        if kind == ExprKind.IDENT:
            name = str(expr.data.get("name", ""))
            if name in env:
                res = env[name]
                expr.resolved_type = res.py_annotation
                return res
            members = caller_type.lookup_member(name, include_bases=True)
            if members:
                m = members[0]
                expr.resolved_lowering = self._member_symbol_to_lowering(m)
                if not m.is_static:
                    expr.data["implicit_this"] = True
                if m.resolved_type is not None:
                    expr.resolved_type = m.resolved_type.py_annotation
                return m.resolved_type
            type_sym = self.symtab.lookup_type_in_context(
                [name], caller_type.namespace, caller_type.unit.imports
            )
            if type_sym is not None:
                res = ResolvedType(
                    qualified_name=type_sym.qualified_name,
                    py_annotation=type_sym.maps_to_py_type or type_sym.name,
                    runtime_isinstance_type=type_sym.runtime_isinstance_type or type_sym.name,
                    symbol_id=type_sym.id,
                    is_primitive=type_sym.is_primitive,
                )
                expr.resolved_type = res.py_annotation
                return res
            return None

        if kind in (ExprKind.MEMBER_ACCESS, ExprKind.NULL_COND_ACCESS):
            target_expr: Expr | None = expr.data.get("target")
            member_name: str = str(expr.data.get("member", ""))
            target_ty = self._resolve_expr(target_expr, caller_type, env)
            if target_ty is not None and target_ty.symbol_id is not None:
                owner_sym = self.symtab.types_by_id.get(target_ty.symbol_id)
                if owner_sym is not None:
                    members = owner_sym.lookup_member(member_name, include_bases=True)
                    if members:
                        m = members[0]
                        expr.resolved_lowering = self._member_symbol_to_lowering(m)
                        substituted = self._substitute_type_args(owner_sym, target_ty, m.resolved_type)
                        if substituted is not None:
                            expr.resolved_type = substituted.py_annotation
                        return substituted
            return None

        if kind == ExprKind.CALL:
            callee: Expr = expr.data["callee"]
            args = expr.data.get("args", ())
            for arg in args:
                self._resolve_expr(arg.expr, caller_type, env)

            if callee.kind in (ExprKind.MEMBER_ACCESS, ExprKind.NULL_COND_ACCESS):
                target_expr = callee.data.get("target")
                member_name = str(callee.data.get("member", ""))
                target_ty = self._resolve_expr(target_expr, caller_type, env)
                if target_ty is not None and target_ty.symbol_id is not None:
                    owner_sym = self.symtab.types_by_id.get(target_ty.symbol_id)
                    if owner_sym is not None:
                        candidates = owner_sym.lookup_member(member_name, include_bases=True)
                        if candidates:
                            chosen = self._pick_overload_candidate(candidates, len(args))
                            lowering = self._member_symbol_to_lowering(chosen)
                            callee.resolved_lowering = lowering
                            expr.resolved_lowering = lowering
                            if chosen.linq_stage is not None:
                                expr.data["linq_stage"] = chosen.linq_stage
                            ret_ty = self._substitute_type_args(
                                owner_sym, target_ty, chosen.resolved_type
                            )
                            if ret_ty is not None:
                                expr.resolved_type = ret_ty.py_annotation
                            return ret_ty
            elif callee.kind == ExprKind.IDENT:
                method_name = str(callee.data.get("name", ""))
                candidates = caller_type.lookup_member(method_name, include_bases=True)
                if candidates:
                    chosen = self._pick_overload_candidate(candidates, len(args))
                    lowering = self._member_symbol_to_lowering(chosen)
                    callee.resolved_lowering = lowering
                    expr.resolved_lowering = lowering
                    if not chosen.is_static:
                        callee.data["implicit_this"] = True
                    if chosen.resolved_type is not None:
                        expr.resolved_type = chosen.resolved_type.py_annotation
                    return chosen.resolved_type
            else:
                self._resolve_expr(callee, caller_type, env)
            return None

        if kind == ExprKind.NEW_OBJECT:
            type_ref: TypeRef = expr.data["type_ref"]
            args = expr.data.get("args", ())
            for arg in args:
                self._resolve_expr(arg.expr, caller_type, env)
            for _, init_val in expr.data.get("initializers", ()):
                self._resolve_expr(init_val, caller_type, env)

            resolved_ty = self.symtab.resolve_type_ref(
                type_ref,
                current_ns=caller_type.namespace,
                imports=caller_type.unit.imports,
                active_type_params=set(caller_type.type_params),
            )
            expr.resolved_type = resolved_ty.py_annotation

            if resolved_ty.symbol_id is not None and resolved_ty.symbol_id in self.symtab.types_by_id:
                inst_sym = self.symtab.types_by_id[resolved_ty.symbol_id]
                ctors = [
                    m
                    for m in inst_sym.lookup_member(inst_sym.name, include_bases=False)
                    if m.kind == "constructor"
                ]
                if ctors:
                    chosen_ctor = self._pick_overload_candidate(ctors, len(args))
                    expr.resolved_lowering = self._member_symbol_to_lowering(chosen_ctor)
                elif inst_sym.is_primitive and inst_sym.maps_to_py_type:
                    expr.resolved_lowering = MemberLoweringMode(
                        kind="PrimitiveDirect",
                        emitted_snake_name=inst_sym.maps_to_py_type,
                        py_target_name=inst_sym.maps_to_py_type,
                    )
            return resolved_ty

        if kind == ExprKind.BINARY:
            left_ty = self._resolve_expr(expr.data.get("left"), caller_type, env)
            right_ty = self._resolve_expr(expr.data.get("right"), caller_type, env)
            op: BinaryOp = expr.data["op"]
            if op in (
                BinaryOp.EQ,
                BinaryOp.NEQ,
                BinaryOp.LT,
                BinaryOp.GT,
                BinaryOp.LTE,
                BinaryOp.GTE,
                BinaryOp.AND,
                BinaryOp.OR,
            ):
                expr.resolved_type = "bool"
                return ResolvedType(
                    qualified_name="PythonSharp.Core.Boolean",
                    py_annotation="bool",
                    runtime_isinstance_type="bool",
                    is_primitive=True,
                )
            return left_ty or right_ty

        if kind == ExprKind.NULL_COALESCE:
            left_ty = self._resolve_expr(expr.data.get("left"), caller_type, env)
            right_ty = self._resolve_expr(expr.data.get("right"), caller_type, env)
            res = right_ty or (left_ty.with_nullable(False) if left_ty else None)
            if res is not None:
                expr.resolved_type = res.py_annotation
            return res

        if kind == ExprKind.UNARY:
            return self._resolve_expr(expr.data.get("operand"), caller_type, env)

        if kind == ExprKind.INDEX_OR_SLICE:
            target_ty = self._resolve_expr(expr.data.get("target"), caller_type, env)
            for dim in expr.data.get("dimensions", ()):
                if dim.single_expr is not None:
                    self._resolve_expr(dim.single_expr, caller_type, env)
                if dim.start is not None:
                    self._resolve_expr(dim.start, caller_type, env)
                if dim.stop is not None:
                    self._resolve_expr(dim.stop, caller_type, env)
                if dim.step is not None:
                    self._resolve_expr(dim.step, caller_type, env)
            if target_ty is not None and target_ty.type_args:
                elem_ty = target_ty.type_args[-1]
                expr.resolved_type = elem_ty.py_annotation
                return elem_ty
            return None

        if kind == ExprKind.TYPE_CHECK_IS:
            self._resolve_expr(expr.data.get("target"), caller_type, env)
            pat = expr.data.get("pattern")
            if pat is not None and pat.type_ref is not None:
                pat_ty = self.symtab.resolve_type_ref(
                    pat.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
                expr.data["runtime_type_check"] = self._compute_runtime_type_check(pat_ty)
            expr.resolved_type = "bool"
            return None

        if kind == ExprKind.TYPE_CAST_AS:
            self._resolve_expr(expr.data.get("target"), caller_type, env)
            tr: TypeRef | None = expr.data.get("type_ref")
            if tr is not None:
                cast_ty = self.symtab.resolve_type_ref(
                    tr,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
                expr.data["runtime_type_check"] = self._compute_runtime_type_check(cast_ty)
                nullable_cast = cast_ty.with_nullable(True)
                expr.resolved_type = nullable_cast.py_annotation
                return nullable_cast
            return None

        if kind == ExprKind.LAMBDA:
            lam_env = dict(env)
            for lp in expr.data.get("params", ()):
                if lp.type_ref is not None:
                    lam_env[lp.name] = self.symtab.resolve_type_ref(
                        lp.type_ref,
                        current_ns=caller_type.namespace,
                        imports=caller_type.unit.imports,
                        active_type_params=set(caller_type.type_params),
                    )
            body = expr.data.get("body")
            if isinstance(body, Expr):
                self._resolve_expr(body, caller_type, lam_env)
            elif isinstance(body, BlockStmt):
                self._resolve_stmt(body, caller_type, lam_env)
            return None

        if kind == ExprKind.SWITCH_EXPR:
            self._resolve_expr(expr.data.get("scrutinee"), caller_type, env)
            for arm in expr.data.get("arms", ()):
                arm_env = dict(env)
                if arm.pattern.type_ref is not None and arm.pattern.bind_name:
                    arm_env[arm.pattern.bind_name] = self.symtab.resolve_type_ref(
                        arm.pattern.type_ref,
                        current_ns=caller_type.namespace,
                        imports=caller_type.unit.imports,
                        active_type_params=set(caller_type.type_params),
                    )
                if arm.when_guard is not None:
                    self._resolve_expr(arm.when_guard, caller_type, arm_env)
                self._resolve_expr(arm.result_expr, caller_type, arm_env)
            return None

        return None

    @staticmethod
    def _pick_overload_candidate(
        candidates: list[MemberSymbol], arg_count: int
    ) -> MemberSymbol:
        for cand in candidates:
            if cand.min_arity <= arg_count <= cand.max_arity:
                return cand
        return candidates[0]

    @staticmethod
    def _member_symbol_to_lowering(mem_sym: MemberSymbol) -> MemberLoweringMode:
        if mem_sym.inline_template is not None:
            return MemberLoweringMode(
                kind="PrimitiveInlineTemplate",
                emitted_snake_name=mem_sym.snake_name,
                inline_template=mem_sym.inline_template,
            )
        if mem_sym.maps_to_py_name is not None or mem_sym.is_extern:
            return MemberLoweringMode(
                kind="PrimitiveDirect",
                emitted_snake_name=mem_sym.maps_to_py_name or mem_sym.snake_name,
                py_target_name=mem_sym.maps_to_py_name or mem_sym.snake_name,
            )
        ast_node = mem_sym.ast_node
        if hasattr(ast_node, "lowering_mode") and ast_node.lowering_mode.kind != "Unresolved":
            return ast_node.lowering_mode
        return MemberLoweringMode(
            kind="StandardPython",
            emitted_snake_name=mem_sym.snake_name,
        )

    @staticmethod
    def _substitute_type_args(
        owner_sym: TypeSymbol,
        receiver_ty: ResolvedType,
        member_ty: ResolvedType | None,
    ) -> ResolvedType | None:
        if member_ty is None:
            return None
        if not owner_sym.type_params or not receiver_ty.type_args:
            return member_ty

        mapping: dict[str, ResolvedType] = {
            tp: arg
            for tp, arg in zip(owner_sym.type_params, receiver_ty.type_args)
        }

        def sub(rt: ResolvedType) -> ResolvedType:
            if rt.is_type_param and rt.qualified_name in mapping:
                mapped = mapping[rt.qualified_name]
                return mapped.with_nullable(True) if rt.is_nullable else mapped
            if rt.type_args:
                new_args = tuple(sub(a) for a in rt.type_args)
                base_py = rt.py_annotation.split("[")[0]
                args_py = ", ".join(a.py_annotation for a in new_args)
                full_py = f"{base_py}[{args_py}]"
                if rt.is_nullable:
                    full_py = f"{full_py} | None"
                return ResolvedType(
                    qualified_name=rt.qualified_name,
                    py_annotation=full_py,
                    runtime_isinstance_type=rt.runtime_isinstance_type,
                    symbol_id=rt.symbol_id,
                    type_args=new_args,
                    is_nullable=rt.is_nullable,
                    is_primitive=rt.is_primitive,
                )
            return rt

        return sub(member_ty)


```

---

##### 3. src/psc/semantics/linq_fuser.py

```python
from __future__ import annotations
from dataclasses import dataclass, field
from psc.frontend.ast_nodes import (
    ArgNode,
    BlockStmt,
    CompilationUnit,
    ComprehensionKind,
    Expr,
    ExprKind,
    ExprStmt,
    FieldDecl,
    ForEachStmt,
    IfStmt,
    IndexerDecl,
    LocalVarStmt,
    MethodDecl,
    PropertyDecl,
    ReturnStmt,
    SliceDimension,
    Stmt,
    SwitchArm,
    SwitchStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.symbols import GlobalSymbolTable


@dataclass(slots=True)
class ComprehensionGenerator:
    """Represents a single `for <item_var> in <iterable>` clause with optional `if` filters."""
    item_var: str
    iterable: Expr
    filters: list[Expr] = field(default_factory=list)


STAGE_BY_METHOD_NAME: dict[str, str] = {
    "Where": "Filter",
    "Select": "Map",
    "SelectMany": "FlatMap",
    "ToList": "TerminalList",
    "ToHashSet": "TerminalSet",
    "ToDict": "TerminalDict",
    "Any": "TerminalAny",
    "All": "TerminalAll",
    "FirstOrDefault": "TerminalFirstOrDefault",
    "Count": "TerminalCount",
    "Sum": "TerminalSum",
    "Min": "TerminalMin",
    "Max": "TerminalMax",
}

TERMINAL_STAGE_TO_KIND: dict[str, ComprehensionKind] = {
    "TerminalList": ComprehensionKind.LIST,
    "TerminalSet": ComprehensionKind.SET,
    "TerminalDict": ComprehensionKind.DICT,
    "TerminalAny": ComprehensionKind.ANY,
    "TerminalAnyPred": ComprehensionKind.ANY,
    "TerminalAll": ComprehensionKind.ALL,
    "TerminalFirstOrDefault": ComprehensionKind.FIRST_OR_DEFAULT,
    "TerminalFirstOrDefaultPred": ComprehensionKind.FIRST_OR_DEFAULT,
    "TerminalCount": ComprehensionKind.COUNT,
    "TerminalSum": ComprehensionKind.SUM,
    "TerminalMin": ComprehensionKind.MIN,
    "TerminalMax": ComprehensionKind.MAX,
}


class LinqComprehensionFuser:
    """
    Pass 2B (Part 3) — Zero-Overhead LINQ-to-Comprehension Fusion Pass:
      Rewrites chained `[LinqStage]` method calls (`.Where().Select().ToList()`,
      `.SelectMany()`, `.ToHashSet()`, `.ToDict()`, `.Any()`, `.All()`, `.FirstOrDefault()`,
      `.Sum()`, `.Count()`) into a single `ExprKind.LINQ_COMPREHENSION` node with
      inlined and alpha-renamed lambda bodies—eliminating all runtime lambda allocations.
    """

    def __init__(self, symtab: GlobalSymbolTable) -> None:
        self.symtab = symtab

    def fuse_all(self, units: list[CompilationUnit]) -> None:
        for unit in units:
            if unit.is_ambient_stub:
                continue
            for decl in unit.types:
                for member in decl.members:
                    if isinstance(member, FieldDecl) and member.initializer is not None:
                        member.initializer = self.rewrite_expr(member.initializer)
                    elif isinstance(member, PropertyDecl):
                        if member.initializer is not None:
                            member.initializer = self.rewrite_expr(member.initializer)
                        if member.expr_body is not None:
                            member.expr_body = self.rewrite_expr(member.expr_body)
                        for acc in member.accessors:
                            if acc.body is not None:
                                self.rewrite_stmt(acc.body)
                            if acc.expr_body is not None:
                                acc.expr_body = self.rewrite_expr(acc.expr_body)
                    elif isinstance(member, IndexerDecl):
                        for acc in member.accessors:
                            if acc.body is not None:
                                self.rewrite_stmt(acc.body)
                            if acc.expr_body is not None:
                                acc.expr_body = self.rewrite_expr(acc.expr_body)
                    elif isinstance(member, MethodDecl):
                        if member.body is not None:
                            self.rewrite_stmt(member.body)
                        if member.expr_body is not None:
                            member.expr_body = self.rewrite_expr(member.expr_body)

    def rewrite_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, BlockStmt):
            for s in stmt.statements:
                self.rewrite_stmt(s)
        elif isinstance(stmt, LocalVarStmt):
            stmt.initializer = self.rewrite_expr(stmt.initializer)
        elif isinstance(stmt, UsingResourceStmt):
            stmt.initializer = self.rewrite_expr(stmt.initializer)
        elif isinstance(stmt, IfStmt):
            stmt.condition = self.rewrite_expr(stmt.condition)
            self.rewrite_stmt(stmt.then_branch)
            if stmt.else_branch is not None:
                self.rewrite_stmt(stmt.else_branch)
        elif isinstance(stmt, WhileStmt):
            stmt.condition = self.rewrite_expr(stmt.condition)
            self.rewrite_stmt(stmt.body)
        elif isinstance(stmt, ForEachStmt):
            stmt.collection = self.rewrite_expr(stmt.collection)
            self.rewrite_stmt(stmt.body)
        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                stmt.value = self.rewrite_expr(stmt.value)
        elif isinstance(stmt, YieldStmt):
            if stmt.value is not None:
                stmt.value = self.rewrite_expr(stmt.value)
        elif isinstance(stmt, ThrowStmt):
            if stmt.exception is not None:
                stmt.exception = self.rewrite_expr(stmt.exception)
        elif isinstance(stmt, TryCatchFinallyStmt):
            self.rewrite_stmt(stmt.try_block)
            for c in stmt.catches:
                if c.when_guard is not None:
                    c.when_guard = self.rewrite_expr(c.when_guard)
                if c.body is not None:
                    self.rewrite_stmt(c.body)
            if stmt.finally_block is not None:
                self.rewrite_stmt(stmt.finally_block)
        elif isinstance(stmt, SwitchStmt):
            stmt.scrutinee = self.rewrite_expr(stmt.scrutinee)
            for sec in stmt.sections:
                for idx, (pat, guard) in enumerate(sec.labels):
                    if guard is not None:
                        sec.labels[idx] = (pat, self.rewrite_expr(guard))
                for s in sec.statements:
                    self.rewrite_stmt(s)
        elif isinstance(stmt, ExprStmt):
            stmt.expr = self.rewrite_expr(stmt.expr)

    def rewrite_expr(self, expr: Expr) -> Expr:
        # First Attempt: If this is the outermost call of a LINQ pipeline, fuse the whole chain!
        fused = self.try_fuse_method_chain(expr)
        if fused is not None:
            return fused

        # Otherwise recursively rewrite child expressions
        kind = expr.kind
        if kind == ExprKind.CALL:
            expr.data["callee"] = self.rewrite_expr(expr.data["callee"])
            for arg in expr.data.get("args", ()):
                arg.expr = self.rewrite_expr(arg.expr)
        elif kind in (ExprKind.MEMBER_ACCESS, ExprKind.NULL_COND_ACCESS):
            if expr.data.get("target") is not None:
                expr.data["target"] = self.rewrite_expr(expr.data["target"])
        elif kind in (ExprKind.BINARY, ExprKind.NULL_COALESCE):
            expr.data["left"] = self.rewrite_expr(expr.data["left"])
            expr.data["right"] = self.rewrite_expr(expr.data["right"])
        elif kind == ExprKind.UNARY:
            expr.data["operand"] = self.rewrite_expr(expr.data["operand"])
        elif kind == ExprKind.NEW_OBJECT:
            for arg in expr.data.get("args", ()):
                arg.expr = self.rewrite_expr(arg.expr)
            inits = expr.data.get("initializers", [])
            for i, (prop, val) in enumerate(inits):
                inits[i] = (prop, self.rewrite_expr(val))
        elif kind in (ExprKind.LIST_LITERAL, ExprKind.TUPLE_LITERAL):
            elems = expr.data.get("elements", [])
            for i, el in enumerate(elems):
                elems[i] = self.rewrite_expr(el)
        elif kind == ExprKind.LAMBDA:
            body = expr.data.get("body")
            if isinstance(body, Expr):
                expr.data["body"] = self.rewrite_expr(body)
            elif isinstance(body, BlockStmt):
                self.rewrite_stmt(body)
        elif kind == ExprKind.SWITCH_EXPR:
            expr.data["scrutinee"] = self.rewrite_expr(expr.data["scrutinee"])
            for arm in expr.data.get("arms", ()):
                if arm.when_guard is not None:
                    arm.when_guard = self.rewrite_expr(arm.when_guard)
                arm.result_expr = self.rewrite_expr(arm.result_expr)

        return expr

    # ========================================================================
    # CORE LINQ CHAIN EXTRACTION, ALPHA-RENAMING & COMPREHENSION FUSION
    # ========================================================================

    def try_fuse_method_chain(self, expr: Expr) -> Expr | None:
        """
        Unwinds a chain of `.Where()`, `.Select()`, `.SelectMany()`, and terminal
        consumers (`.ToList()`, `.ToHashSet()`, `.ToDict()`, `.Any()`, `.All()`,
        `.FirstOrDefault()`, `.Sum()`, `.Count()`, `.Min()`, `.Max()`) into a single
        `ExprKind.LINQ_COMPREHENSION` node.
        """
        chain: list[tuple[str, list[ArgNode], Expr]] = []
        curr = expr

        while curr.kind == ExprKind.CALL:
            callee: Expr = curr.data["callee"]
            if callee.kind != ExprKind.MEMBER_ACCESS:
                break
            member_name = str(callee.data.get("member", ""))
            stage = curr.data.get("linq_stage") or STAGE_BY_METHOD_NAME.get(member_name)
            if stage is None:
                break
            args: list[ArgNode] = list(curr.data.get("args", ()))
            chain.append((stage, args, curr))
            curr = callee.data["target"]

        if not chain:
            return None

        # Reverse so stages are ordered from source -> intermediate -> terminal
        chain.reverse()
        source_expr = self.rewrite_expr(curr)

        generators: list[ComprehensionGenerator] = []
        current_gen = ComprehensionGenerator(item_var="_x", iterable=source_expr)
        has_bound_item_var = False

        projection: Expr | None = None
        key_projection: Expr | None = None
        value_projection: Expr | None = None
        terminal_kind = ComprehensionKind.GENERATOR

        for idx, (stage, args, call_node) in enumerate(chain):
            is_last = idx == len(chain) - 1

            if stage == "Filter":
                if not args or args[0].expr.kind != ExprKind.LAMBDA:
                    return None
                lam_param, lam_body = self._extract_lambda(args[0].expr)
                if not has_bound_item_var:
                    current_gen.item_var = lam_param
                    has_bound_item_var = True
                elif lam_param != current_gen.item_var:
                    lam_body = self._alpha_rename_ident(
                        lam_body, old_name=lam_param, new_name=current_gen.item_var
                    )

                # If a `.Select()` projection already occurred before `.Where()`, substitute it!
                if projection is not None:
                    lam_body = self._substitute_ident_with_expr(
                        lam_body, target_name=current_gen.item_var, replacement=projection
                    )
                current_gen.filters.append(lam_body)

            elif stage == "Map":
                if not args or args[0].expr.kind != ExprKind.LAMBDA:
                    return None
                lam_param, lam_body = self._extract_lambda(args[0].expr)
                if not has_bound_item_var:
                    current_gen.item_var = lam_param
                    has_bound_item_var = True
                elif lam_param != current_gen.item_var:
                    lam_body = self._alpha_rename_ident(
                        lam_body, old_name=lam_param, new_name=current_gen.item_var
                    )

                if projection is not None:
                    lam_body = self._substitute_ident_with_expr(
                        lam_body, target_name=current_gen.item_var, replacement=projection
                    )
                projection = lam_body

            elif stage == "FlatMap":
                # `.SelectMany(o => o.Items)` adds a second generator clause to the comprehension!
                if not args or args[0].expr.kind != ExprKind.LAMBDA:
                    return None
                lam_param, lam_body = self._extract_lambda(args[0].expr)
                if not has_bound_item_var:
                    current_gen.item_var = lam_param
                    has_bound_item_var = True
                elif lam_param != current_gen.item_var:
                    lam_body = self._alpha_rename_ident(
                        lam_body, old_name=lam_param, new_name=current_gen.item_var
                    )
                generators.append(current_gen)
                current_gen = ComprehensionGenerator(item_var="_item", iterable=lam_body)
                has_bound_item_var = False
                projection = None

            elif stage in TERMINAL_STAGE_TO_KIND and is_last:
                terminal_kind = TERMINAL_STAGE_TO_KIND[stage]

                # Handle predicate-bearing terminals (`Any(u => ...)`, `All(u => ...)`, `FirstOrDefault(u => ...)`)
                if stage in ("TerminalAny", "TerminalAnyPred", "TerminalAll") and args:
                    if args[0].expr.kind == ExprKind.LAMBDA:
                        lam_param, lam_body = self._extract_lambda(args[0].expr)
                        if not has_bound_item_var:
                            current_gen.item_var = lam_param
                            has_bound_item_var = True
                        elif lam_param != current_gen.item_var:
                            lam_body = self._alpha_rename_ident(
                                lam_body, old_name=lam_param, new_name=current_gen.item_var
                            )
                        projection = lam_body

                elif stage in ("TerminalFirstOrDefault", "TerminalFirstOrDefaultPred") and args:
                    if args[0].expr.kind == ExprKind.LAMBDA:
                        lam_param, lam_body = self._extract_lambda(args[0].expr)
                        if not has_bound_item_var:
                            current_gen.item_var = lam_param
                            has_bound_item_var = True
                        elif lam_param != current_gen.item_var:
                            lam_body = self._alpha_rename_ident(
                                lam_body, old_name=lam_param, new_name=current_gen.item_var
                            )
                        current_gen.filters.append(lam_body)

                elif stage == "TerminalDict":
                    if len(args) != 2:
                        return None
                    k_param, k_body = self._extract_lambda(args[0].expr)
                    v_param, v_body = self._extract_lambda(args[1].expr)
                    if not has_bound_item_var:
                        current_gen.item_var = k_param
                        has_bound_item_var = True
                    elif k_param != current_gen.item_var:
                        k_body = self._alpha_rename_ident(
                            k_body, old_name=k_param, new_name=current_gen.item_var
                        )
                    if v_param != current_gen.item_var:
                        v_body = self._alpha_rename_ident(
                            v_body, old_name=v_param, new_name=current_gen.item_var
                        )
                    key_projection = k_body
                    value_projection = v_body
            else:
                # Unsupported mid-chain terminal
                return None

        generators.append(current_gen)
        primary_gen = generators[0]

        return Expr(
            span=expr.span,
            kind=ExprKind.LINQ_COMPREHENSION,
            data={
                "source": primary_gen.iterable,
                "item_var": primary_gen.item_var,
                "filters": primary_gen.filters,
                "generators": generators,
                "projection": projection,
                "key_projection": key_projection,
                "value_projection": value_projection,
                "terminal_kind": terminal_kind,
            },
            resolved_type=expr.resolved_type,
        )

    @staticmethod
    def _extract_lambda(lam_expr: Expr) -> tuple[str, Expr]:
        params = lam_expr.data.get("params", ())
        param_name = params[0].name if params else "_x"
        body = lam_expr.data["body"]
        assert isinstance(body, Expr), "LINQ comprehension fusion requires expression-bodied lambdas"
        return param_name, body

    def _alpha_rename_ident(self, expr: Expr, old_name: str, new_name: str) -> Expr:
        """Recursively renames `IDENT(old_name)` to `IDENT(new_name)` inside an expression tree."""
        return self._substitute_ident_with_expr(
            expr,
            target_name=old_name,
            replacement=Expr(span=expr.span, kind=ExprKind.IDENT, data={"name": new_name}),
        )

    def _substitute_ident_with_expr(
        self, expr: Expr, target_name: str, replacement: Expr
    ) -> Expr:
        kind = expr.kind

        if kind == ExprKind.IDENT:
            if expr.data.get("name") == target_name:
                return Expr(
                    span=expr.span,
                    kind=replacement.kind,
                    data=dict(replacement.data),
                    resolved_type=replacement.resolved_type or expr.resolved_type,
                    resolved_lowering=replacement.resolved_lowering or expr.resolved_lowering,
                )
            return expr

        if kind in (ExprKind.MEMBER_ACCESS, ExprKind.NULL_COND_ACCESS):
            new_data = dict(expr.data)
            if new_data.get("target") is not None:
                new_data["target"] = self._substitute_ident_with_expr(
                    new_data["target"], target_name, replacement
                )
            return Expr(
                span=expr.span,
                kind=kind,
                data=new_data,
                resolved_type=expr.resolved_type,
                resolved_lowering=expr.resolved_lowering,
            )

        if kind in (ExprKind.BINARY, ExprKind.NULL_COALESCE):
            new_data = dict(expr.data)
            new_data["left"] = self._substitute_ident_with_expr(
                new_data["left"], target_name, replacement
            )
            new_data["right"] = self._substitute_ident_with_expr(
                new_data["right"], target_name, replacement
            )
            return Expr(
                span=expr.span,
                kind=kind,
                data=new_data,
                resolved_type=expr.resolved_type,
                resolved_lowering=expr.resolved_lowering,
            )

        if kind == ExprKind.UNARY:
            new_data = dict(expr.data)
            new_data["operand"] = self._substitute_ident_with_expr(
                new_data["operand"], target_name, replacement
            )
            return Expr(
                span=expr.span,
                kind=kind,
                data=new_data,
                resolved_type=expr.resolved_type,
                resolved_lowering=expr.resolved_lowering,
            )

        if kind == ExprKind.CALL:
            new_data = dict(expr.data)
            new_data["callee"] = self._substitute_ident_with_expr(
                new_data["callee"], target_name, replacement
            )
            new_data["args"] = [
                ArgNode(
                    span=a.span,
                    name=a.name,
                    expr=self._substitute_ident_with_expr(a.expr, target_name, replacement),
                )
                for a in new_data.get("args", ())
            ]
            return Expr(
                span=expr.span,
                kind=kind,
                data=new_data,
                resolved_type=expr.resolved_type,
                resolved_lowering=expr.resolved_lowering,
            )

        if kind == ExprKind.INDEX_OR_SLICE:
            new_data = dict(expr.data)
            new_data["target"] = self._substitute_ident_with_expr(
                new_data["target"], target_name, replacement
            )
            new_dims = []
            for d in new_data.get("dimensions", ()):
                new_dims.append(
                    SliceDimension(
                        span=d.span,
                        is_range_or_slice=d.is_range_or_slice,
                        single_expr=(
                            self._substitute_ident_with_expr(d.single_expr, target_name, replacement)
                            if d.single_expr
                            else None
                        ),
                        start=(
                            self._substitute_ident_with_expr(d.start, target_name, replacement)
                            if d.start
                            else None
                        ),
                        stop=(
                            self._substitute_ident_with_expr(d.stop, target_name, replacement)
                            if d.stop
                            else None
                        ),
                        step=(
                            self._substitute_ident_with_expr(d.step, target_name, replacement)
                            if d.step
                            else None
                        ),
                    )
                )
            new_data["dimensions"] = new_dims
            return Expr(
                span=expr.span,
                kind=kind,
                data=new_data,
                resolved_type=expr.resolved_type,
                resolved_lowering=expr.resolved_lowering,
            )

        return expr


```

---

##### 4. src/psc/semantics/**init**.py

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine
from psc.frontend.ast_nodes import CompilationUnit
from psc.semantics.symbols import (
    BUILTIN_PRIMITIVE_MAP,
    GlobalSymbolTable,
    MemberSymbol,
    ResolvedType,
    TypeSymbol,
    namespace_to_module_path,
    pascal_to_snake,
)
from psc.semantics.collector import SymbolCollector
from psc.semantics.slot_analyzer import SlotAndHierarchyAnalyzer
from psc.semantics.access_checker import AccessChecker
from psc.semantics.primitive_resolver import PrimitiveResolver
from psc.semantics.overload_resolver import OverloadResolver
from psc.semantics.linq_fuser import ComprehensionGenerator, LinqComprehensionFuser


def analyze_compilation_units(
    units: list[CompilationUnit],
    symtab: GlobalSymbolTable,
    diagnostics: DiagnosticEngine,
    assembly_name: str | None = None,
) -> None:
    """
    Runs the complete Pass 1 + Pass 2A + Pass 2B semantic pipeline across all units:
      1. SymbolCollector (Pass 1: global type headers, inheritance, member signatures)
      2. SlotAndHierarchyAnalyzer (Pass 2A: deduplicated __slots__, __ps_types__, PS003/PS004)
      3. AccessChecker (Pass 2A: Rule PS001 private/protected/internal verification)
      4. PrimitiveResolver (Pass 2B: [MapsTo], [InlineTemplate], [KwArgs], generators)
      5. OverloadResolver (Pass 2B: @overload dispatch groups, Rule PS002, call-site binding)
      6. LinqComprehensionFuser (Pass 2B: .Where().Select().ToList() comprehension fusion)
    """
    SymbolCollector(symtab, diagnostics).collect_all(units, assembly_name=assembly_name)
    SlotAndHierarchyAnalyzer(symtab, diagnostics).analyze_all(units)
    AccessChecker(symtab, diagnostics).check_all(units)
    PrimitiveResolver(symtab, diagnostics).resolve_all(units)
    OverloadResolver(symtab, diagnostics).resolve_all(units)
    LinqComprehensionFuser(symtab).fuse_all(units)


__all__ = [
    "BUILTIN_PRIMITIVE_MAP",
    "GlobalSymbolTable",
    "MemberSymbol",
    "ResolvedType",
    "TypeSymbol",
    "SymbolCollector",
    "SlotAndHierarchyAnalyzer",
    "AccessChecker",
    "PrimitiveResolver",
    "OverloadResolver",
    "LinqComprehensionFuser",
    "ComprehensionGenerator",
    "analyze_compilation_units",
    "namespace_to_module_path",
    "pascal_to_snake",
]


```

---

##### 5. tests/test_overloads_and_linq.py

```python
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

    find_methods = [
        m for m in cache_decl.members if isinstance(m, MethodDecl) and m.name == "Find"
    ]
    assert find_methods[0].lowering_mode.runtime_guard is not None
    assert find_methods[0].lowering_mode.runtime_guard.param_type_checks[0][1].kind == "PyIsInstance"
    assert find_methods[0].lowering_mode.runtime_guard.param_type_checks[0][1].target_type == "int"

    assert find_methods[2].lowering_mode.runtime_guard is not None
    assert find_methods[2].lowering_mode.runtime_guard.param_type_checks[0][1].kind == "PsTypesContains"
    assert (
        find_methods[2].lowering_mode.runtime_guard.param_type_checks[0][1].target_type
        == "Commerce.Services.IAuditable"
    )

    # 3. Verify LINQ Comprehension Fusion & Alpha-Renaming (`o`, `x`, `item` -> all unified to `o`!)
    get_active = next(
        m for m in cache_decl.members if isinstance(m, MethodDecl) and m.name == "GetActiveIds"
    )
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


```

---

Shall we continue with the raw individual files for **Milestone 5 (Pass 3A: `src/psc/codegen/expr_lowerer.py` and `src/psc/codegen/py_ast_builder.py` for lowering decorated `.ps` ASTs into Python 3.11+ `ast.Module` trees with `__slots__`, `__ps_types__`, `@overload` dispatchers, walrus `??`/`?.` null-safety, multi-dimensional tensor slicing, `match`/`case`, fused comprehensions, and `.ps` line-number stamping, plus `tests/test_py_ast_builder.py`)**?
