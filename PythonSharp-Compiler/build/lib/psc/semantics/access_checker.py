from __future__ import annotations

from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend.ast_nodes import (
    AccessMod,
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
    MethodDecl,
    PropertyDecl,
    ReturnStmt,
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
)

ASSIGN_OPS = frozenset(
    {
        BinaryOp.ASSIGN,
        BinaryOp.ADD_ASSIGN,
        BinaryOp.SUB_ASSIGN,
        BinaryOp.MUL_ASSIGN,
        BinaryOp.DIV_ASSIGN,
        BinaryOp.NULL_COALESCE_ASSIGN,
    }
)


class AccessChecker:
    """
    Pass 2A Encapsulation Verifier (Rule PS001):
      Enforces compile-time `private`, `protected`, and `internal` (.psproj assembly-scoped)
      visibility across all type references, field accesses, property getters/setters
      (including `{ get; private set; }`), constructors, methods, and indexers.
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        diagnostics: DiagnosticEngine,
    ) -> None:
        self.symtab = symtab
        self.diagnostics = diagnostics

    def check_all(self, units: list[CompilationUnit]) -> None:
        """Runs encapsulation verification across all non-ambient compilation units."""
        for unit in units:
            if unit.is_ambient_stub:
                continue
            for decl in unit.types:
                if decl.symbol_id is not None and decl.symbol_id in self.symtab.types_by_id:
                    type_sym = self.symtab.types_by_id[decl.symbol_id]
                    self.check_type_decl(type_sym)

    # ========================================================================
    # CORE VISIBILITY VERIFICATION RULES (PS001)
    # ========================================================================

    def verify_type_access(
        self,
        span: SourceSpan,
        caller_type: TypeSymbol,
        target_type: TypeSymbol,
    ) -> bool:
        """Verifies that `caller_type` is permitted to reference `target_type`."""
        if target_type.is_ambient_stub or target_type.access == AccessMod.PUBLIC:
            return True

        if target_type.access == AccessMod.INTERNAL:
            if caller_type.assembly_name == target_type.assembly_name:
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=target_type.name,
                access_mod="internal",
                owner_type=".".join(target_type.namespace) or target_type.assembly_name,
            )
            return False

        if target_type.access == AccessMod.PRIVATE:
            if caller_type.id == target_type.id:
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=target_type.name,
                access_mod="private",
                owner_type=".".join(target_type.namespace) or target_type.assembly_name,
            )
            return False

        if target_type.access == AccessMod.PROTECTED:
            if caller_type.is_subclass_of(target_type.qualified_name):
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=target_type.name,
                access_mod="protected",
                owner_type=".".join(target_type.namespace) or target_type.assembly_name,
            )
            return False

        return True

    def verify_member_access(
        self,
        span: SourceSpan,
        caller_type: TypeSymbol,
        target_member: MemberSymbol,
        is_write: bool = False,
        in_constructor: bool = False,
    ) -> bool:
        """
        Verifies that `caller_type` can read (or write, if `is_write=True`) `target_member`.
        Handles `private set`, `protected set`, `internal set`, and `readonly` fields.
        """
        owner_sym = self.symtab.types_by_id.get(target_member.owner_type_id)
        if owner_sym is not None and owner_sym.is_ambient_stub:
            return True

        # 1. Check write-specific constraints (`readonly` fields and property setters)
        if is_write:
            if target_member.kind == "field" and target_member.is_readonly:
                if not (in_constructor and caller_type.id == target_member.owner_type_id):
                    self.diagnostics.report_ps001_access_violation(
                        span=span,
                        member_name=target_member.name,
                        access_mod="readonly",
                        owner_type=target_member.owner_qualified_name,
                    )
                    return False

            if target_member.kind in ("property", "indexer"):
                if target_member.setter_access is None:
                    # Read-only property (`{ get; }` or `=> expr`)
                    if not (in_constructor and caller_type.id == target_member.owner_type_id):
                        self.diagnostics.report_ps001_access_violation(
                            span=span,
                            member_name=f"{target_member.name}.set",
                            access_mod="private (read-only)",
                            owner_type=target_member.owner_qualified_name,
                        )
                        return False
                    effective_access = AccessMod.PRIVATE
                else:
                    effective_access = target_member.setter_access
                member_label = f"{target_member.name}.set"
            else:
                effective_access = target_member.access
                member_label = target_member.name
        else:
            effective_access = target_member.access
            member_label = target_member.name

        # 2. Evaluate effective AccessMod against caller context
        if effective_access == AccessMod.PUBLIC:
            return True

        if effective_access == AccessMod.PRIVATE:
            if caller_type.id == target_member.owner_type_id:
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=member_label,
                access_mod="private",
                owner_type=target_member.owner_qualified_name,
            )
            return False

        if effective_access == AccessMod.PROTECTED:
            if caller_type.is_subclass_of(target_member.owner_qualified_name):
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=member_label,
                access_mod="protected",
                owner_type=target_member.owner_qualified_name,
            )
            return False

        if effective_access == AccessMod.INTERNAL:
            if owner_sym is None or caller_type.assembly_name == owner_sym.assembly_name:
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=member_label,
                access_mod="internal",
                owner_type=target_member.owner_qualified_name,
            )
            return False

        return True

    # ========================================================================
    # AST TRAVERSAL & LOCAL TYPE ENVIRONMENT TRACKING
    # ========================================================================

    def check_type_decl(self, type_sym: TypeSymbol) -> None:
        decl = type_sym.ast_node
        active_tparams = set(type_sym.type_params)

        # Verify base type accessibility
        for base_sym in type_sym.base_type_symbols:
            self.verify_type_access(decl.span, type_sym, base_sym)

        # Verify primary constructor parameter types
        for p in decl.primary_ctor_params:
            self._check_type_ref_access(p.type_ref, type_sym, active_tparams)
            if p.default_value is not None:
                self._check_expr(p.default_value, type_sym, {}, in_constructor=True)

        # Verify all members
        for member in decl.members:
            if isinstance(member, FieldDecl):
                self._check_type_ref_access(member.type_ref, type_sym, active_tparams)
                if member.initializer is not None:
                    self._check_expr(
                        member.initializer,
                        type_sym,
                        {},
                        in_constructor=("static" not in member.modifiers),
                    )

            elif isinstance(member, PropertyDecl):
                self._check_type_ref_access(member.type_ref, type_sym, active_tparams)
                if member.initializer is not None:
                    self._check_expr(member.initializer, type_sym, {}, in_constructor=True)
                if member.expr_body is not None:
                    self._check_expr(member.expr_body, type_sym, {}, in_constructor=False)
                for acc in member.accessors:
                    prop_ty = self.symtab.resolve_type_ref(
                        member.type_ref,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=active_tparams,
                    )
                    env = {"value": prop_ty} if acc.kind == "set" else {}
                    if acc.body is not None:
                        self._check_stmt(acc.body, type_sym, env, in_constructor=False)
                    if acc.expr_body is not None:
                        self._check_expr(acc.expr_body, type_sym, env, in_constructor=False)

            elif isinstance(member, IndexerDecl):
                self._check_type_ref_access(member.type_ref, type_sym, active_tparams)
                base_env: dict[str, ResolvedType] = {}
                for p in member.params:
                    self._check_type_ref_access(p.type_ref, type_sym, active_tparams)
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
                        self._check_stmt(acc.body, type_sym, env, in_constructor=False)
                    if acc.expr_body is not None:
                        self._check_expr(acc.expr_body, type_sym, env, in_constructor=False)

            elif isinstance(member, MethodDecl):
                method_tparams = active_tparams | set(member.type_params)
                if member.return_type is not None:
                    self._check_type_ref_access(member.return_type, type_sym, method_tparams)

                env = {}
                for p in member.params:
                    self._check_type_ref_access(p.type_ref, type_sym, method_tparams)
                    p_ty = self.symtab.resolve_type_ref(
                        p.type_ref,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=method_tparams,
                    )
                    env[p.name] = p_ty
                    if p.default_value is not None:
                        self._check_expr(
                            p.default_value,
                            type_sym,
                            env,
                            in_constructor=member.is_constructor,
                        )

                if member.ctor_chain is not None:
                    for arg in member.ctor_chain.args:
                        self._check_expr(arg.expr, type_sym, env, in_constructor=True)

                if member.body is not None:
                    self._check_stmt(member.body, type_sym, env, in_constructor=member.is_constructor)
                if member.expr_body is not None:
                    self._check_expr(member.expr_body, type_sym, env, in_constructor=member.is_constructor)

    def _check_type_ref_access(
        self,
        type_ref: TypeRef,
        caller_type: TypeSymbol,
        active_tparams: set[str],
    ) -> None:
        resolved = self.symtab.resolve_type_ref(
            type_ref,
            current_ns=caller_type.namespace,
            imports=caller_type.unit.imports,
            active_type_params=active_tparams,
        )
        if resolved.symbol_id is not None and resolved.symbol_id in self.symtab.types_by_id:
            target_sym = self.symtab.types_by_id[resolved.symbol_id]
            self.verify_type_access(type_ref.span, caller_type, target_sym)

        for arg in type_ref.type_args:
            self._check_type_ref_access(arg, caller_type, active_tparams)
        for elem_tr, _ in type_ref.tuple_elements:
            self._check_type_ref_access(elem_tr, caller_type, active_tparams)

    def _check_stmt(
        self,
        stmt: Stmt,
        caller_type: TypeSymbol,
        env: dict[str, ResolvedType],
        in_constructor: bool,
    ) -> None:
        if isinstance(stmt, BlockStmt):
            inner_env = dict(env)
            for s in stmt.statements:
                self._check_stmt(s, caller_type, inner_env, in_constructor)

        elif isinstance(stmt, LocalVarStmt):
            if stmt.type_ref is not None:
                self._check_type_ref_access(stmt.type_ref, caller_type, set(caller_type.type_params))
            init_ty = self._check_expr(stmt.initializer, caller_type, env, in_constructor)
            if stmt.type_ref is not None:
                decl_ty = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
                env[stmt.name] = decl_ty
            elif init_ty is not None:
                env[stmt.name] = init_ty

        elif isinstance(stmt, UsingResourceStmt):
            if stmt.type_ref is not None:
                self._check_type_ref_access(stmt.type_ref, caller_type, set(caller_type.type_params))
            init_ty = self._check_expr(stmt.initializer, caller_type, env, in_constructor)
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
            self._check_expr(stmt.condition, caller_type, env, in_constructor)
            self._check_stmt(stmt.then_branch, caller_type, dict(env), in_constructor)
            if stmt.else_branch is not None:
                self._check_stmt(stmt.else_branch, caller_type, dict(env), in_constructor)

        elif isinstance(stmt, WhileStmt):
            self._check_expr(stmt.condition, caller_type, env, in_constructor)
            self._check_stmt(stmt.body, caller_type, dict(env), in_constructor)

        elif isinstance(stmt, ForEachStmt):
            coll_ty = self._check_expr(stmt.collection, caller_type, env, in_constructor)
            loop_env = dict(env)
            if stmt.type_ref is not None:
                self._check_type_ref_access(stmt.type_ref, caller_type, set(caller_type.type_params))
                loop_env[stmt.item_name] = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
            elif coll_ty is not None and coll_ty.type_args:
                loop_env[stmt.item_name] = coll_ty.type_args[0]
            self._check_stmt(stmt.body, caller_type, loop_env, in_constructor)

        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                self._check_expr(stmt.value, caller_type, env, in_constructor)

        elif isinstance(stmt, YieldStmt):
            if stmt.value is not None:
                self._check_expr(stmt.value, caller_type, env, in_constructor)

        elif isinstance(stmt, ThrowStmt):
            if stmt.exception is not None:
                self._check_expr(stmt.exception, caller_type, env, in_constructor)

        elif isinstance(stmt, TryCatchFinallyStmt):
            self._check_stmt(stmt.try_block, caller_type, dict(env), in_constructor)
            for catch in stmt.catches:
                catch_env = dict(env)
                if catch.exception_type is not None:
                    self._check_type_ref_access(catch.exception_type, caller_type, set(caller_type.type_params))
                    if catch.bind_name:
                        catch_env[catch.bind_name] = self.symtab.resolve_type_ref(
                            catch.exception_type,
                            current_ns=caller_type.namespace,
                            imports=caller_type.unit.imports,
                            active_type_params=set(caller_type.type_params),
                        )
                if catch.when_guard is not None:
                    self._check_expr(catch.when_guard, caller_type, catch_env, in_constructor)
                if catch.body is not None:
                    self._check_stmt(catch.body, caller_type, catch_env, in_constructor)
            if stmt.finally_block is not None:
                self._check_stmt(stmt.finally_block, caller_type, dict(env), in_constructor)

        elif isinstance(stmt, SwitchStmt):
            self._check_expr(stmt.scrutinee, caller_type, env, in_constructor)
            for sec in stmt.sections:
                sec_env = dict(env)
                for pat, guard in sec.labels:
                    if pat is not None and pat.type_ref is not None:
                        self._check_type_ref_access(pat.type_ref, caller_type, set(caller_type.type_params))
                        if pat.bind_name:
                            sec_env[pat.bind_name] = self.symtab.resolve_type_ref(
                                pat.type_ref,
                                current_ns=caller_type.namespace,
                                imports=caller_type.unit.imports,
                                active_type_params=set(caller_type.type_params),
                            )
                    if guard is not None:
                        self._check_expr(guard, caller_type, sec_env, in_constructor)
                for s in sec.statements:
                    self._check_stmt(s, caller_type, sec_env, in_constructor)

        elif isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr, caller_type, env, in_constructor)

    def _check_expr(
        self,
        expr: Expr | None,
        caller_type: TypeSymbol,
        env: dict[str, ResolvedType],
        in_constructor: bool,
        is_write_target: bool = False,
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
                return ResolvedType(
                    qualified_name=qname,
                    py_annotation=py_ann,
                    runtime_isinstance_type=rt,
                    symbol_id=sym.id if sym else None,
                    is_primitive=True,
                )
            return None

        if kind == ExprKind.THIS:
            return ResolvedType(
                qualified_name=caller_type.qualified_name,
                py_annotation=caller_type.name,
                runtime_isinstance_type=caller_type.name,
                symbol_id=caller_type.id,
            )

        if kind == ExprKind.BASE:
            if caller_type.base_type_symbols:
                base_sym = caller_type.base_type_symbols[0]
                return ResolvedType(
                    qualified_name=base_sym.qualified_name,
                    py_annotation=base_sym.name,
                    runtime_isinstance_type=base_sym.name,
                    symbol_id=base_sym.id,
                )
            return None

        if kind == ExprKind.IDENT:
            name = str(expr.data.get("name", ""))
            # 1. Local variable or parameter in scope
            if name in env:
                return env[name]
            # 2. Implicit `this.<Member>` access on current class or base classes
            members = caller_type.lookup_member(name, include_bases=True)
            if members:
                target_member = members[0]
                self.verify_member_access(
                    expr.span,
                    caller_type,
                    target_member,
                    is_write=is_write_target,
                    in_constructor=in_constructor,
                )
                return target_member.resolved_type
            # 3. Type identifier for static member access (`OrderCache.StaticMethod()`)
            type_sym = self.symtab.lookup_type_in_context([name], caller_type.namespace, caller_type.unit.imports)
            if type_sym is not None:
                self.verify_type_access(expr.span, caller_type, type_sym)
                return ResolvedType(
                    qualified_name=type_sym.qualified_name,
                    py_annotation=type_sym.name,
                    runtime_isinstance_type=type_sym.name,
                    symbol_id=type_sym.id,
                )
            return None

        if kind in (ExprKind.MEMBER_ACCESS, ExprKind.NULL_COND_ACCESS):
            target_expr: Expr | None = expr.data.get("target")
            member_name: str = str(expr.data.get("member", ""))
            target_ty = self._check_expr(target_expr, caller_type, env, in_constructor, is_write_target=False)
            if target_ty is not None and target_ty.symbol_id is not None:
                owner_sym = self.symtab.types_by_id.get(target_ty.symbol_id)
                if owner_sym is not None:
                    members = owner_sym.lookup_member(member_name, include_bases=True)
                    if members:
                        target_member = members[0]
                        self.verify_member_access(
                            expr.span,
                            caller_type,
                            target_member,
                            is_write=is_write_target,
                            in_constructor=in_constructor,
                        )
                        return target_member.resolved_type
            return None

        if kind == ExprKind.BINARY:
            op: BinaryOp = expr.data["op"]
            left: Expr = expr.data["left"]
            right: Expr = expr.data["right"]
            is_assign = op in ASSIGN_OPS
            left_ty = self._check_expr(left, caller_type, env, in_constructor, is_write_target=is_assign)
            self._check_expr(right, caller_type, env, in_constructor, is_write_target=False)
            return left_ty

        if kind == ExprKind.NULL_COALESCE:
            left_ty = self._check_expr(expr.data.get("left"), caller_type, env, in_constructor)
            right_ty = self._check_expr(expr.data.get("right"), caller_type, env, in_constructor)
            return right_ty or left_ty

        if kind == ExprKind.UNARY:
            return self._check_expr(expr.data.get("operand"), caller_type, env, in_constructor)

        if kind == ExprKind.CALL:
            callee: Expr = expr.data["callee"]
            args = expr.data.get("args", ())
            for arg in args:
                self._check_expr(arg.expr, caller_type, env, in_constructor)
            return self._check_expr(callee, caller_type, env, in_constructor)

        if kind == ExprKind.NEW_OBJECT:
            type_ref: TypeRef = expr.data["type_ref"]
            self._check_type_ref_access(type_ref, caller_type, set(caller_type.type_params))
            resolved_ty = self.symtab.resolve_type_ref(
                type_ref,
                current_ns=caller_type.namespace,
                imports=caller_type.unit.imports,
                active_type_params=set(caller_type.type_params),
            )
            args = expr.data.get("args", ())
            for arg in args:
                self._check_expr(arg.expr, caller_type, env, in_constructor)

            # Check constructor accessibility if the type has explicit constructors
            if resolved_ty.symbol_id is not None and resolved_ty.symbol_id in self.symtab.types_by_id:
                inst_sym = self.symtab.types_by_id[resolved_ty.symbol_id]
                ctors = [
                    m for m in inst_sym.lookup_member(inst_sym.name, include_bases=False) if m.kind == "constructor"
                ]
                if ctors:
                    # Pick matching arity constructor if overloaded, or first constructor
                    matching = [c for c in ctors if c.min_arity <= len(args) <= c.max_arity] or ctors
                    if not any(self._can_access_quietly(caller_type, c) for c in matching):
                        self.verify_member_access(expr.span, caller_type, matching[0], is_write=False)

                # Also check object initializer property writes (`new Order { Total = 10m }`)
                for prop_name, init_val_expr in expr.data.get("initializers", ()):
                    self._check_expr(init_val_expr, caller_type, env, in_constructor)
                    props = inst_sym.lookup_member(prop_name, include_bases=True)
                    if props:
                        self.verify_member_access(expr.span, caller_type, props[0], is_write=True)

            return resolved_ty

        if kind == ExprKind.INDEX_OR_SLICE:
            target_ty = self._check_expr(expr.data.get("target"), caller_type, env, in_constructor)
            for dim in expr.data.get("dimensions", ()):
                if dim.single_expr is not None:
                    self._check_expr(dim.single_expr, caller_type, env, in_constructor)
                if dim.start is not None:
                    self._check_expr(dim.start, caller_type, env, in_constructor)
                if dim.stop is not None:
                    self._check_expr(dim.stop, caller_type, env, in_constructor)
                if dim.step is not None:
                    self._check_expr(dim.step, caller_type, env, in_constructor)
            if target_ty is not None and target_ty.symbol_id is not None:
                owner_sym = self.symtab.types_by_id.get(target_ty.symbol_id)
                if owner_sym is not None:
                    idx_members = owner_sym.lookup_member("this[]", include_bases=True)
                    if idx_members:
                        self.verify_member_access(
                            expr.span,
                            caller_type,
                            idx_members[0],
                            is_write=is_write_target,
                            in_constructor=in_constructor,
                        )
                        return idx_members[0].resolved_type
            return None

        if kind == ExprKind.INTERP_STRING:
            for part in expr.data.get("parts", ()):
                if part.is_expr and part.expr is not None:
                    self._check_expr(part.expr, caller_type, env, in_constructor)
            qname, py_ann, rt = BUILTIN_PRIMITIVE_MAP["string"]
            return ResolvedType(
                qualified_name=qname, py_annotation=py_ann, runtime_isinstance_type=rt, is_primitive=True
            )

        if kind in (ExprKind.LIST_LITERAL, ExprKind.TUPLE_LITERAL):
            for el in expr.data.get("elements", ()):
                self._check_expr(el, caller_type, env, in_constructor)
            return None

        if kind == ExprKind.TYPE_CHECK_IS:
            self._check_expr(expr.data.get("target"), caller_type, env, in_constructor)
            pat = expr.data.get("pattern")
            if pat is not None and pat.type_ref is not None:
                self._check_type_ref_access(pat.type_ref, caller_type, set(caller_type.type_params))
            return None

        if kind == ExprKind.TYPE_CAST_AS:
            self._check_expr(expr.data.get("target"), caller_type, env, in_constructor)
            tr: TypeRef | None = expr.data.get("type_ref")
            if tr is not None:
                self._check_type_ref_access(tr, caller_type, set(caller_type.type_params))
                return self.symtab.resolve_type_ref(
                    tr,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                ).with_nullable(True)
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
                self._check_expr(body, caller_type, lam_env, in_constructor=False)
            elif isinstance(body, BlockStmt):
                self._check_stmt(body, caller_type, lam_env, in_constructor=False)
            return None

        if kind == ExprKind.SWITCH_EXPR:
            self._check_expr(expr.data.get("scrutinee"), caller_type, env, in_constructor)
            for arm in expr.data.get("arms", ()):
                arm_env = dict(env)
                if arm.pattern.type_ref is not None:
                    self._check_type_ref_access(arm.pattern.type_ref, caller_type, set(caller_type.type_params))
                    if arm.pattern.bind_name:
                        arm_env[arm.pattern.bind_name] = self.symtab.resolve_type_ref(
                            arm.pattern.type_ref,
                            current_ns=caller_type.namespace,
                            imports=caller_type.unit.imports,
                            active_type_params=set(caller_type.type_params),
                        )
                if arm.when_guard is not None:
                    self._check_expr(arm.when_guard, caller_type, arm_env, in_constructor)
                self._check_expr(arm.result_expr, caller_type, arm_env, in_constructor)
            return None

        return None

    def _can_access_quietly(self, caller_type: TypeSymbol, member: MemberSymbol) -> bool:
        if member.access == AccessMod.PUBLIC:
            return True
        if member.access == AccessMod.PRIVATE:
            return caller_type.id == member.owner_type_id
        if member.access == AccessMod.PROTECTED:
            return caller_type.is_subclass_of(member.owner_qualified_name)
        if member.access == AccessMod.INTERNAL:
            owner_sym = self.symtab.types_by_id.get(member.owner_type_id)
            return owner_sym is None or caller_type.assembly_name == owner_sym.assembly_name
        return True
