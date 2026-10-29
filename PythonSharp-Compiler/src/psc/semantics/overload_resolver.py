from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
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
        if rt_type == "int":
            # bool is a subclass of int in Python; the strict guard prevents
            # True/False from selecting an int overload.
            return RuntimeTypeCheck(kind="PyIsInstanceStrictInt", target_type="int")
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
                    erased_a = [self._erased_runtime_token(sym_a.param_types[p]) for p in range(k)]
                    erased_b = [self._erased_runtime_token(sym_b.param_types[p]) for p in range(k)]
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
        return f"{check.kind}:{check.target_type}"

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

        if kind == ExprKind.INTERP_STRING:
            for part in expr.data.get("parts", ()):
                if part.is_expr and part.expr is not None:
                    self._resolve_expr(part.expr, caller_type, env)
            qname, py_ann, rt = BUILTIN_PRIMITIVE_MAP["string"]
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
                if m.is_static:
                    expr.data["static_owner"] = caller_type.maps_to_py_type or caller_type.name
                    if self._is_static_computed_property(m):
                        expr.data["static_property_call"] = True
                else:
                    expr.data["implicit_this"] = True
                if m.resolved_type is not None:
                    expr.resolved_type = m.resolved_type.py_annotation
                return m.resolved_type
            type_sym = self.symtab.lookup_type_in_context([name], caller_type.namespace, caller_type.unit.imports)
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
                        if self._is_static_computed_property(m):
                            expr.data["static_property_call"] = True
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
                            ret_ty = self._substitute_type_args(owner_sym, target_ty, chosen.resolved_type)
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
                    else:
                        callee.data["static_owner"] = caller_type.maps_to_py_type or caller_type.name
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
                    m for m in inst_sym.lookup_member(inst_sym.name, include_bases=False) if m.kind == "constructor"
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
            res_ty = left_ty or right_ty
            if res_ty is not None:
                expr.resolved_type = res_ty.py_annotation
            return res_ty

        if kind == ExprKind.NULL_COALESCE:
            left_ty = self._resolve_expr(expr.data.get("left"), caller_type, env)
            right_ty = self._resolve_expr(expr.data.get("right"), caller_type, env)
            coalesced: ResolvedType | None = right_ty or (left_ty.with_nullable(False) if left_ty else None)
            if coalesced is not None:
                expr.resolved_type = coalesced.py_annotation
            return coalesced

        if kind == ExprKind.CONDITIONAL:
            self._resolve_expr(expr.data.get("condition"), caller_type, env)
            then_ty = self._resolve_expr(expr.data.get("then_expr"), caller_type, env)
            else_ty = self._resolve_expr(expr.data.get("else_expr"), caller_type, env)
            chosen_ty = then_ty or else_ty
            if chosen_ty is not None:
                expr.resolved_type = chosen_ty.py_annotation
            return chosen_ty

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
    def _pick_overload_candidate(candidates: list[MemberSymbol], arg_count: int) -> MemberSymbol:
        for cand in candidates:
            if cand.min_arity <= arg_count <= cand.max_arity:
                return cand
        return candidates[0]

    @staticmethod
    def _is_static_computed_property(mem_sym: MemberSymbol) -> bool:
        if not mem_sym.is_static or mem_sym.kind != "property":
            return False
        prop = mem_sym.ast_node
        if not isinstance(prop, PropertyDecl):
            return False
        if prop.expr_body is not None:
            return True
        return any(accessor.body is not None or accessor.expr_body is not None for accessor in prop.accessors)

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

        mapping: dict[str, ResolvedType] = {tp: arg for tp, arg in zip(owner_sym.type_params, receiver_ty.type_args)}

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
