from __future__ import annotations

from typing import Any

from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend.ast_nodes import (
    BlockStmt,
    CompilationUnit,
    Expr,
    ExprKind,
    ExprStmt,
    ForEachStmt,
    IfStmt,
    LocalVarStmt,
    MethodDecl,
    PropertyDecl,
    ReturnStmt,
    Stmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.symbols import GlobalSymbolTable


class SurfaceMigrationChecker:
    """
    Pass 2C Surface Migration Verifier (Rule PS005):
    Verifies that code targeting an Enterprise Surface Level (e.g. Surface 3)
    does not reference lower-tier Surface 1 (Raw ABI) or Surface 2 (Bridge) symbols.
    Emits WARNING [PS005] with actionable migration hints to canonical enterprise alternatives.
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        diagnostics: DiagnosticEngine,
        target_surface: int = 3,
    ) -> None:
        self.symtab = symtab
        self.diagnostics = diagnostics
        self.target_surface = target_surface

    def check_all(self, units: list[CompilationUnit]) -> None:
        if self.target_surface <= 1:
            return

        for unit in units:
            if unit.is_ambient_stub:
                continue
            self._check_unit(unit)

    def _check_unit(self, unit: CompilationUnit) -> None:
        # 1. Check imports: using PythonSharp.Raw... or PythonSharp.Bridge...
        for imp in unit.imports:
            ns_str = ".".join(imp.path)
            if "Raw" in imp.path and self.target_surface >= 2:
                canonical_ns = ".".join([p for p in imp.path if p != "Raw"])
                self.diagnostics.report_ps005_surface_migration(
                    span=imp.span,
                    symbol_name=ns_str,
                    current_surface=1,
                    target_surface=self.target_surface,
                    canonical_target=f"using {canonical_ns};",
                )
            elif "Bridge" in imp.path and self.target_surface >= 3:
                canonical_ns = ".".join([p for p in imp.path if p != "Bridge"])
                self.diagnostics.report_ps005_surface_migration(
                    span=imp.span,
                    symbol_name=ns_str,
                    current_surface=2,
                    target_surface=self.target_surface,
                    canonical_target=f"using {canonical_ns};",
                )

        # 2. Check types, properties, methods, expressions
        for decl in unit.types:
            for member in decl.members:
                if isinstance(member, MethodDecl):
                    if member.body:
                        self._check_block(member.body)
                elif isinstance(member, PropertyDecl):
                    if member.getter_body:
                        self._check_block(member.getter_body)
                    if member.setter_body:
                        self._check_block(member.setter_body)

    def _check_block(self, block: BlockStmt) -> None:
        for stmt in block.statements:
            self._check_stmt(stmt)

    def _check_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, LocalVarStmt):
            if stmt.initializer:
                self._check_expr(stmt.initializer)
        elif isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr)
        elif isinstance(stmt, ReturnStmt):
            if stmt.expr:
                self._check_expr(stmt.expr)
        elif isinstance(stmt, IfStmt):
            self._check_expr(stmt.condition)
            self._check_block(stmt.then_branch)
            if stmt.else_branch:
                self._check_block(stmt.else_branch)
        elif isinstance(stmt, WhileStmt):
            self._check_expr(stmt.condition)
            self._check_block(stmt.body)
        elif isinstance(stmt, ForEachStmt):
            self._check_expr(stmt.iterable)
            self._check_block(stmt.body)
        elif isinstance(stmt, UsingResourceStmt):
            if stmt.resource_expr:
                self._check_expr(stmt.resource_expr)
            self._check_block(stmt.body)
        elif isinstance(stmt, TryCatchFinallyStmt):
            self._check_block(stmt.try_block)
            for c in stmt.catch_clauses:
                self._check_block(c.body)
            if stmt.finally_block:
                self._check_block(stmt.finally_block)
        elif isinstance(stmt, ThrowStmt):
            if stmt.expr:
                self._check_expr(stmt.expr)
        elif isinstance(stmt, YieldStmt):
            if stmt.expr:
                self._check_expr(stmt.expr)

    def _check_expr(self, expr: Expr | None) -> None:
        if expr is None:
            return

        data: dict[str, Any] = expr.data
        kind = expr.kind

        if kind == ExprKind.CALL:
            callee: Expr | None = data.get("callee")
            args: list[Any] = data.get("args", [])
            for a in args:
                if isinstance(a, Expr):
                    self._check_expr(a)
                elif hasattr(a, "expr") and isinstance(a.expr, Expr):
                    self._check_expr(a.expr)

            if callee is not None:
                if callee.kind in (ExprKind.MEMBER_ACCESS, ExprKind.NULL_COND_ACCESS):
                    target: Expr | None = callee.data.get("target")
                    member_name: str = str(callee.data.get("member", ""))
                    if target is not None and target.kind == ExprKind.IDENT:
                        owner_name = str(target.data.get("name", ""))
                        self._check_symbol_reference(owner_name, member_name, expr.span)
                    else:
                        self._check_expr(target)
                elif callee.kind == ExprKind.IDENT:
                    self._check_symbol_reference(None, str(callee.data.get("name", "")), expr.span)
                else:
                    self._check_expr(callee)
            return

        if kind in (ExprKind.MEMBER_ACCESS, ExprKind.NULL_COND_ACCESS):
            target = data.get("target")
            member_name = str(data.get("member", ""))
            if isinstance(target, Expr) and target.kind == ExprKind.IDENT:
                owner_name = str(target.data.get("name", ""))
                self._check_symbol_reference(owner_name, member_name, expr.span)
            else:
                self._check_expr(target)
            return

        if kind == ExprKind.IDENT:
            name = str(data.get("name", ""))
            self._check_symbol_reference(None, name, expr.span)
            return

        # Recursive check for binary, unary, ternary, collections
        for val in data.values():
            if isinstance(val, Expr):
                self._check_expr(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, Expr):
                        self._check_expr(item)
                    elif hasattr(item, "expr") and isinstance(item.expr, Expr):
                        self._check_expr(item.expr)

    def _check_symbol_reference(self, owner_name: str | None, member_name: str | None, span: SourceSpan) -> None:
        if owner_name:
            candidates = self.symtab.short_name_index.get(owner_name, [])
            for ts in candidates:
                if 0 < ts.surface_level < self.target_surface:
                    self.diagnostics.report_ps005_surface_migration(
                        span=span,
                        symbol_name=ts.name,
                        current_surface=ts.surface_level,
                        target_surface=self.target_surface,
                        canonical_target=ts.canonical_api,
                    )
                if member_name and member_name in ts.members_by_name:
                    mem = ts.members_by_name[member_name][0]
                    eff_surface = mem.surface_level or ts.surface_level
                    eff_canonical = mem.canonical_api or ts.canonical_api
                    if 0 < eff_surface < self.target_surface:
                        self.diagnostics.report_ps005_surface_migration(
                            span=span,
                            symbol_name=f"{ts.name}.{mem.name}",
                            current_surface=eff_surface,
                            target_surface=self.target_surface,
                            canonical_target=eff_canonical,
                        )
        elif member_name:
            candidates = self.symtab.short_name_index.get(member_name, [])
            for ts in candidates:
                if 0 < ts.surface_level < self.target_surface:
                    self.diagnostics.report_ps005_surface_migration(
                        span=span,
                        symbol_name=ts.name,
                        current_surface=ts.surface_level,
                        target_surface=self.target_surface,
                        canonical_target=ts.canonical_api,
                    )
