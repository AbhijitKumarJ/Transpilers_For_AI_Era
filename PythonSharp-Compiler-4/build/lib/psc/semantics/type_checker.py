from __future__ import annotations

from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend.ast_nodes import (
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
    TypeConstraint,
    TypeKind,
    TypeRef,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.access_checker import AccessChecker
from psc.semantics.linq_fuser import LinqComprehensionFuser
from psc.semantics.overload_resolver import OverloadResolver
from psc.semantics.primitive_resolver import PrimitiveResolver
from psc.semantics.slot_analyzer import SlotAndHierarchyAnalyzer
from psc.semantics.symbols import GlobalSymbolTable, ResolvedType, TypeSymbol


class TypeChecker:
    """
    Pass 2 Orchestrator & Static Type / Generic Constraint Verifier:
      1. Coordinates Pass 2A (`SlotAndHierarchyAnalyzer`, `AccessChecker`) and
         Pass 2B (`PrimitiveResolver`, `OverloadResolver`, `LinqComprehensionFuser`).
      2. Verifies generic `where T : BaseOrInterface` constraints on classes and methods.
      3. Verifies non-nullable vs. nullable (`T` vs `T?`) assignment and return compatibility.
      4. Ensures all expression nodes carry resolved Python 3.11+ type annotations.
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        diagnostics: DiagnosticEngine,
    ) -> None:
        self.symtab = symtab
        self.diagnostics = diagnostics
        self.slot_analyzer = SlotAndHierarchyAnalyzer(symtab, diagnostics)
        self.access_checker = AccessChecker(symtab, diagnostics)
        self.primitive_resolver = PrimitiveResolver(symtab, diagnostics)
        self.overload_resolver = OverloadResolver(symtab, diagnostics)
        self.linq_fuser = LinqComprehensionFuser(symtab)
        self._catch_depth = 0

    def check_and_decorate_all(self, units: list[CompilationUnit]) -> None:
        """Executes the complete Pass 2 semantic analysis and AST decoration pipeline."""
        # Pass 2A: Hierarchy slots, __ps_types__, PS003/PS004, and PS001 access verification
        self.slot_analyzer.analyze_all(units)
        self.access_checker.check_all(units)

        # Pass 2B: Primitive erasure, @overload dispatch synthesis (PS002), and LINQ fusion
        self.primitive_resolver.resolve_all(units)
        self.overload_resolver.resolve_all(units)
        self.linq_fuser.fuse_all(units)

        # Pass 2C: Generic constraint verification & nullability / return type checks
        self.verify_all(units)

    def verify_all(self, units: list[CompilationUnit]) -> None:
        """Runs Pass 2C only: generic constraints and nullability/return checks."""
        for unit in units:
            if unit.is_ambient_stub:
                continue
            for decl in unit.types:
                if decl.symbol_id is not None and decl.symbol_id in self.symtab.types_by_id:
                    type_sym = self.symtab.types_by_id[decl.symbol_id]
                    self.verify_type_decl(type_sym)

    # ========================================================================
    # GENERIC CONSTRAINT & NULLABILITY VERIFICATION
    # ========================================================================

    def verify_type_decl(self, type_sym: TypeSymbol) -> None:
        decl = type_sym.ast_node
        active_tparams = set(type_sym.type_params)

        self._verify_declared_constraints(decl.constraints, type_sym, active_tparams)

        for member in decl.members:
            if isinstance(member, FieldDecl):
                self._verify_dataclass_member_shape(type_sym, member)
                if member.initializer is not None:
                    decl_ty = self.symtab.resolve_type_ref(
                        member.type_ref,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=active_tparams,
                    )
                    self._check_null_assignment(
                        span=member.span,
                        target_name=member.name,
                        declared_type=decl_ty,
                        value_expr=member.initializer,
                    )
                    self._check_expr_generic_instantiations(member.initializer, type_sym, active_tparams)

            elif isinstance(member, PropertyDecl):
                self._verify_dataclass_member_shape(type_sym, member)
                self._verify_static_property_shape(type_sym, member)
                prop_ty = self.symtab.resolve_type_ref(
                    member.type_ref,
                    current_ns=type_sym.namespace,
                    imports=type_sym.unit.imports,
                    active_type_params=active_tparams,
                )
                if member.initializer is not None:
                    self._check_null_assignment(
                        span=member.span,
                        target_name=member.name,
                        declared_type=prop_ty,
                        value_expr=member.initializer,
                    )
                    self._check_expr_generic_instantiations(member.initializer, type_sym, active_tparams)
                if member.expr_body is not None:
                    self._check_expr_generic_instantiations(member.expr_body, type_sym, active_tparams)
                for acc in member.accessors:
                    if acc.body is not None:
                        self._check_stmt_types(
                            acc.body,
                            type_sym,
                            expected_return=prop_ty if acc.kind == "get" else None,
                            active_tparams=active_tparams,
                        )

            elif isinstance(member, IndexerDecl):
                idx_ty = self.symtab.resolve_type_ref(
                    member.type_ref,
                    current_ns=type_sym.namespace,
                    imports=type_sym.unit.imports,
                    active_type_params=active_tparams,
                )
                for acc in member.accessors:
                    if acc.body is not None:
                        self._check_stmt_types(
                            acc.body,
                            type_sym,
                            expected_return=idx_ty if acc.kind == "get" else None,
                            active_tparams=active_tparams,
                        )

            elif isinstance(member, MethodDecl):
                method_tparams = active_tparams | set(member.type_params)
                self._verify_declared_constraints(member.constraints, type_sym, method_tparams)
                expected_ret: ResolvedType | None = None
                if not member.is_constructor and member.return_type is not None:
                    expected_ret = self.symtab.resolve_type_ref(
                        member.return_type,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=method_tparams,
                    )

                for p in member.params:
                    if p.default_value is not None:
                        p_ty = self.symtab.resolve_type_ref(
                            p.type_ref,
                            current_ns=type_sym.namespace,
                            imports=type_sym.unit.imports,
                            active_type_params=method_tparams,
                        )
                        self._check_null_assignment(
                            span=p.span,
                            target_name=p.name,
                            declared_type=p_ty,
                            value_expr=p.default_value,
                        )

                if member.expr_body is not None:
                    if expected_ret is not None and expected_ret.py_annotation != "None":
                        self._check_null_assignment(
                            span=member.expr_body.span,
                            target_name=f"{member.name}() return",
                            declared_type=expected_ret,
                            value_expr=member.expr_body,
                        )
                    self._check_expr_generic_instantiations(member.expr_body, type_sym, method_tparams)

                if member.body is not None:
                    self._check_stmt_types(
                        member.body,
                        type_sym,
                        expected_return=expected_ret,
                        active_tparams=method_tparams,
                    )

    def _verify_declared_constraints(
        self,
        constraints: list[TypeConstraint],
        owner_type: TypeSymbol,
        active_tparams: set[str],
    ) -> None:
        for tc in constraints:
            if tc.type_param not in active_tparams:
                self.diagnostics.report_syntax_error(
                    tc.span,
                    f"Constraint references undeclared type parameter '{tc.type_param}' on '{owner_type.name}'.",
                )
            for bound_ref in tc.bounds:
                self.symtab.resolve_type_ref(
                    bound_ref,
                    current_ns=owner_type.namespace,
                    imports=owner_type.unit.imports,
                    active_type_params=active_tparams,
                )

    def _verify_dataclass_member_shape(
        self,
        owner_type: TypeSymbol,
        member: FieldDecl | PropertyDecl,
    ) -> None:
        if owner_type.kind not in (TypeKind.RECORD, TypeKind.RECORD_STRUCT, TypeKind.STRUCT):
            return
        if "static" in member.modifiers:
            return

        if isinstance(member, FieldDecl):
            self.diagnostics.report_syntax_error(
                member.span,
                f"Instance field '{owner_type.name}.{member.name}' is not supported in records/structs; "
                "declare it as a primary constructor parameter.",
            )
            return

        all_auto = member.expr_body is None and all(
            accessor.body is None and accessor.expr_body is None for accessor in member.accessors
        )
        if all_auto:
            self.diagnostics.report_syntax_error(
                member.span,
                f"Instance auto-property '{owner_type.name}.{member.name}' is not supported in records/structs; "
                "declare it as a primary constructor parameter.",
            )
            return

        if owner_type.kind == TypeKind.RECORD and any(accessor.kind == "set" for accessor in member.accessors):
            self.diagnostics.report_syntax_error(
                member.span,
                f"Instance property '{owner_type.name}.{member.name}' has a setter, "
                "but records are emitted as frozen dataclasses.",
            )

    def _verify_static_property_shape(self, owner_type: TypeSymbol, prop: PropertyDecl) -> None:
        if "static" not in prop.modifiers:
            return
        has_setter = any(accessor.kind == "set" for accessor in prop.accessors)
        all_auto = prop.expr_body is None and all(
            accessor.body is None and accessor.expr_body is None for accessor in prop.accessors
        )
        if has_setter and not all_auto:
            self.diagnostics.report_syntax_error(
                prop.span,
                f"Static property '{owner_type.name}.{prop.name}' has a custom setter; "
                "only auto-properties and getter-only static properties are supported.",
            )

    def _check_stmt_types(
        self,
        stmt: Stmt,
        caller_type: TypeSymbol,
        expected_return: ResolvedType | None,
        active_tparams: set[str],
    ) -> None:
        if isinstance(stmt, BlockStmt):
            for s in stmt.statements:
                self._check_stmt_types(s, caller_type, expected_return, active_tparams)

        elif isinstance(stmt, LocalVarStmt):
            if stmt.type_ref is not None:
                decl_ty = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=active_tparams,
                )
                self._check_null_assignment(
                    span=stmt.span,
                    target_name=stmt.name,
                    declared_type=decl_ty,
                    value_expr=stmt.initializer,
                )
            self._check_expr_generic_instantiations(stmt.initializer, caller_type, active_tparams)

        elif isinstance(stmt, UsingResourceStmt):
            self._check_expr_generic_instantiations(stmt.initializer, caller_type, active_tparams)

        elif isinstance(stmt, IfStmt):
            self._check_expr_generic_instantiations(stmt.condition, caller_type, active_tparams)
            self._check_stmt_types(stmt.then_branch, caller_type, expected_return, active_tparams)
            if stmt.else_branch is not None:
                self._check_stmt_types(stmt.else_branch, caller_type, expected_return, active_tparams)

        elif isinstance(stmt, WhileStmt):
            self._check_expr_generic_instantiations(stmt.condition, caller_type, active_tparams)
            self._check_stmt_types(stmt.body, caller_type, expected_return, active_tparams)

        elif isinstance(stmt, ForEachStmt):
            self._check_expr_generic_instantiations(stmt.collection, caller_type, active_tparams)
            self._check_stmt_types(stmt.body, caller_type, expected_return, active_tparams)

        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                if expected_return is not None and expected_return.py_annotation != "None":
                    self._check_null_assignment(
                        span=stmt.span,
                        target_name="return value",
                        declared_type=expected_return,
                        value_expr=stmt.value,
                    )
                self._check_expr_generic_instantiations(stmt.value, caller_type, active_tparams)

        elif isinstance(stmt, YieldStmt):
            if stmt.value is not None:
                self._check_expr_generic_instantiations(stmt.value, caller_type, active_tparams)

        elif isinstance(stmt, ThrowStmt):
            if stmt.exception is not None:
                self._check_expr_generic_instantiations(stmt.exception, caller_type, active_tparams)
            elif self._catch_depth == 0:
                self.diagnostics.report_syntax_error(
                    stmt.span,
                    "A bare 'throw;' is only valid inside a catch handler.",
                )

        elif isinstance(stmt, TryCatchFinallyStmt):
            self._check_stmt_types(stmt.try_block, caller_type, expected_return, active_tparams)
            for c in stmt.catches:
                if c.body is not None:
                    self._catch_depth += 1
                    try:
                        self._check_stmt_types(c.body, caller_type, expected_return, active_tparams)
                    finally:
                        self._catch_depth -= 1
            if stmt.finally_block is not None:
                self._check_stmt_types(stmt.finally_block, caller_type, expected_return, active_tparams)

        elif isinstance(stmt, SwitchStmt):
            self._check_expr_generic_instantiations(stmt.scrutinee, caller_type, active_tparams)
            for sec in stmt.sections:
                for s in sec.statements:
                    self._check_stmt_types(s, caller_type, expected_return, active_tparams)

        elif isinstance(stmt, ExprStmt):
            self._check_expr_generic_instantiations(stmt.expr, caller_type, active_tparams)

    def _check_null_assignment(
        self,
        span: SourceSpan,
        target_name: str,
        declared_type: ResolvedType,
        value_expr: Expr,
    ) -> None:
        """
        Reports a compile-time error if `null` is assigned directly to a non-nullable
        type (`T` instead of `T?`), unless `default` is used for an optional parameter.
        """
        if (
            value_expr.kind == ExprKind.LITERAL
            and value_expr.data.get("literal_kind") == LiteralKind.NULL
            and not declared_type.is_nullable
            and not declared_type.is_type_param
            and declared_type.py_annotation not in ("Any", "object", "None")
        ):
            self.diagnostics.report_syntax_error(
                span,
                f"Cannot assign 'null' to non-nullable target '{target_name}' of type '{declared_type.py_annotation}'. "
                f"Mark the type as nullable ('{declared_type.py_annotation}?').",
            )

    def _check_expr_generic_instantiations(
        self,
        expr: Expr | None,
        caller_type: TypeSymbol,
        active_tparams: set[str],
    ) -> None:
        if expr is None:
            return

        if expr.kind == ExprKind.NEW_OBJECT:
            type_ref: TypeRef = expr.data["type_ref"]
            self._verify_type_ref_constraints(type_ref, caller_type, active_tparams)
            for arg in expr.data.get("args", ()):
                self._check_expr_generic_instantiations(arg.expr, caller_type, active_tparams)

        elif expr.kind == ExprKind.CALL:
            self._check_expr_generic_instantiations(expr.data.get("callee"), caller_type, active_tparams)
            for arg in expr.data.get("args", ()):
                self._check_expr_generic_instantiations(arg.expr, caller_type, active_tparams)

        elif expr.kind in (ExprKind.BINARY, ExprKind.NULL_COALESCE):
            self._check_expr_generic_instantiations(expr.data.get("left"), caller_type, active_tparams)
            self._check_expr_generic_instantiations(expr.data.get("right"), caller_type, active_tparams)
        elif expr.kind == ExprKind.CONDITIONAL:
            self._check_expr_generic_instantiations(expr.data.get("condition"), caller_type, active_tparams)
            self._check_expr_generic_instantiations(expr.data.get("then_expr"), caller_type, active_tparams)
            self._check_expr_generic_instantiations(expr.data.get("else_expr"), caller_type, active_tparams)

    def _verify_type_ref_constraints(
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
            generic_sym = self.symtab.types_by_id[resolved.symbol_id]
            decl = generic_sym.ast_node
            if decl.constraints and len(type_ref.type_args) == len(decl.type_params):
                param_to_arg = {
                    tp: self.symtab.resolve_type_ref(
                        arg_ref,
                        current_ns=caller_type.namespace,
                        imports=caller_type.unit.imports,
                        active_type_params=active_tparams,
                    )
                    for tp, arg_ref in zip(decl.type_params, type_ref.type_args)
                }
                for tc in decl.constraints:
                    arg_resolved = param_to_arg.get(tc.type_param)
                    if (
                        arg_resolved is not None
                        and not arg_resolved.is_type_param
                        and arg_resolved.symbol_id is not None
                        and arg_resolved.symbol_id in self.symtab.types_by_id
                    ):
                        arg_sym = self.symtab.types_by_id[arg_resolved.symbol_id]
                        for bound_ref in tc.bounds:
                            bound_resolved = self.symtab.resolve_type_ref(
                                bound_ref,
                                current_ns=generic_sym.namespace,
                                imports=generic_sym.unit.imports,
                                active_type_params=set(decl.type_params),
                            )
                            if not arg_sym.is_subclass_of(bound_resolved.qualified_name):
                                self.diagnostics.report_syntax_error(
                                    type_ref.span,
                                    f"Type argument '{arg_sym.qualified_name}' for '{generic_sym.name}<{tc.type_param}>' "
                                    f"does not satisfy constraint '{bound_resolved.qualified_name}'.",
                                )
