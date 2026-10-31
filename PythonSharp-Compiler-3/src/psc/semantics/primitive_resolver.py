from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend.ast_nodes import (
    AttributeNode,
    BlockStmt,
    CompilationUnit,
    Expr,
    ExprKind,
    ForEachStmt,
    IfStmt,
    IndexerDecl,
    LiteralKind,
    MemberLoweringMode,
    MethodDecl,
    PropertyDecl,
    Stmt,
    SwitchStmt,
    TryCatchFinallyStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol, pascal_to_snake

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
        "CanonicalApi",
        "CanonicalApiAttribute",
        "SurfaceLevel",
        "SurfaceLevelAttribute",
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
        inline_tpl = self._extract_string_attr(prop.attributes, ("InlineTemplate", "InlineTemplateAttribute"))
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
        inline_tpl = self._extract_string_attr(indexer.attributes, ("InlineTemplate", "InlineTemplateAttribute"))
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

        inline_tpl = self._extract_string_attr(method.attributes, ("InlineTemplate", "InlineTemplateAttribute"))
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
            if short_name in ("PythonDecorator", "PythonDecoratorAttribute"):
                if attr.args and attr.args[0].expr is not None:
                    first_arg = attr.args[0].expr
                    if first_arg.kind == ExprKind.LITERAL and isinstance(first_arg.data.get("value"), str):
                        code_str = first_arg.data["value"]
                        import ast as py_ast

                        try:
                            parsed_ast = py_ast.parse(code_str, mode="eval").body
                            decorators.append(
                                Expr(
                                    span=attr.span,
                                    kind=ExprKind.RAW_PYTHON_AST,
                                    data={"ast": parsed_ast},
                                )
                            )
                        except Exception:
                            pass
                continue
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
                if first_expr.kind == ExprKind.LITERAL and first_expr.data.get("literal_kind") == LiteralKind.STRING:
                    return str(first_expr.data["value"])
        return None
