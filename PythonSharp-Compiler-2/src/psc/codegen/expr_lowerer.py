from __future__ import annotations

import ast
import re
from typing import Any, cast

from psc.diagnostics import SourceSpan
from psc.frontend.ast_nodes import (
    ArgNode,
    BinaryOp,
    BlockStmt,
    BreakStmt,
    CatchClause,
    ComprehensionKind,
    ContinueStmt,
    Expr,
    ExprKind,
    ExprStmt,
    ForEachStmt,
    IfStmt,
    InterpolatedPart,
    LiteralKind,
    LocalVarStmt,
    PatternNode,
    ReturnStmt,
    RuntimeTypeCheck,
    SliceDimension,
    Stmt,
    SwitchArm,
    SwitchStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    TypeRef,
    UnaryOp,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.linq_fuser import ComprehensionGenerator
from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol, pascal_to_snake

_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{(self|value|\d+)\}")

_SPAN_NODE_TYPES = (ast.expr, ast.stmt, ast.excepthandler, ast.pattern)

ASSIGN_BINARY_OPS = frozenset(
    {
        BinaryOp.ASSIGN,
        BinaryOp.ADD_ASSIGN,
        BinaryOp.SUB_ASSIGN,
        BinaryOp.MUL_ASSIGN,
        BinaryOp.DIV_ASSIGN,
        BinaryOp.NULL_COALESCE_ASSIGN,
    }
)


def _stamp_tree(node: ast.AST, lineno: int, end_lineno: int, col: int, end_col: int) -> None:
    if isinstance(node, _SPAN_NODE_TYPES):
        if getattr(node, "lineno", None) is not None:
            return
        node.lineno = lineno
        node.end_lineno = end_lineno
        node.col_offset = col
        node.end_col_offset = end_col
    for child in ast.iter_child_nodes(node):
        _stamp_tree(child, lineno, end_lineno, col, end_col)


def stamp_span(node: ast.AST, span: SourceSpan) -> ast.AST:
    """
    Stamps a Python `ast.AST` node (and any un-stamped children) with the exact
    1-indexed line number and 0-indexed column offset from the original `.ps` file.
    """
    lineno = max(1, span.start_line)
    end_lineno = max(lineno, span.end_line)
    col = max(0, span.start_col - 1)
    end_col = max(col, span.end_col - 1)
    _stamp_tree(node, lineno, end_lineno, col, end_col)
    return node


class ExpressionLowerer:
    """
    Pass 3A (Part 2) — Python 3.11+ Statement & Expression Lowerer:
      Lowers decorated `.ps` statements and expressions into native Python `ast.AST` nodes:
      - `[InlineTemplate]` substitution (`{self}`, `{0}`, `{1}`, `{value}`)
      - Multi-dimensional tensor/collection slicing (`1..5`, `^2..`, `::2` -> `ast.Slice`)
      - Null-coalescing (`??`, `??=`) and null-conditional chains (`?.`) via walrus `:=`
      - Nominal interface `is` / `as` checks via O(1) `__ps_types__` tuple lookup
      - Fused `LINQ_COMPREHENSION` nodes -> `ast.ListComp`, `ast.SetComp`, `ast.DictComp`, `any`, `all`, `sum`
      - `switch` statements/expressions -> Python 3.10+ `match` / `case`
      - `using var` / `await using var` -> `with` / `async with`
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        current_type: TypeSymbol | None = None,
    ) -> None:
        self.symtab = symtab
        self.current_type = current_type
        self._temp_counter = 0
        self._pending_stmts: list[ast.stmt] = []
        self.needs_decimal_import = False

    def allocate_temp_var(self, prefix: str = "_ps_t") -> str:
        idx = self._temp_counter
        self._temp_counter += 1
        return f"{prefix}{idx}"

    # ========================================================================
    # 1. STATEMENT LOWERING
    # ========================================================================

    def lower_block(self, block: BlockStmt | None) -> list[ast.stmt]:
        if block is None or not block.statements:
            return [ast.Pass(lineno=block.span.start_line if block else 1, col_offset=0)]
        out: list[ast.stmt] = []
        for s in block.statements:
            out.extend(self._lower_stmt_with_prelude(s))
        return out or [ast.Pass(lineno=block.span.start_line, col_offset=0)]

    def _lower_stmt_with_prelude(self, stmt: Stmt) -> list[ast.stmt]:
        start = len(self._pending_stmts)
        lowered = self.lower_stmt(stmt)
        prelude = self._pending_stmts[start:]
        del self._pending_stmts[start:]
        return [*prelude, *lowered]

    def _annotation_is_resolvable(self, annotation: ast.expr) -> bool:
        known = {
            "Any",
            "Callable",
            "ClassVar",
            "Decimal",
            "Generic",
            "Iterable",
            "Literal",
            "Mapping",
            "Optional",
            "Protocol",
            "Sequence",
            "TYPE_CHECKING",
            "TypeVar",
            "Union",
            "bool",
            "bytes",
            "dict",
            "float",
            "int",
            "list",
            "object",
            "set",
            "str",
            "tuple",
        }
        if self.current_type is not None:
            known.update(self.current_type.type_params)

        attribute_roots: set[str] = set()
        for node in ast.walk(annotation):
            if isinstance(node, ast.Attribute):
                root: ast.expr = node
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name):
                    attribute_roots.add(root.id)

        for node in ast.walk(annotation):
            if not isinstance(node, ast.Name) or node.id in known or node.id in attribute_roots:
                continue
            if self.current_type is not None and self.symtab.lookup_type_in_context(
                [node.id],
                self.current_type.namespace,
                self.current_type.unit.imports,
            ):
                continue
            return False
        return True

    def lower_stmt(self, stmt: Stmt) -> list[ast.stmt]:
        if isinstance(stmt, BlockStmt):
            return self.lower_block(stmt)

        if isinstance(stmt, LocalVarStmt):
            target_id = pascal_to_snake(stmt.name)
            val_ast = self.lower_expr(stmt.initializer)
            if stmt.type_ref is not None:
                ann_ast = self.lower_type_ref_annotation(stmt.type_ref)
                node: ast.stmt = ast.AnnAssign(
                    target=ast.Name(id=target_id, ctx=ast.Store()),
                    annotation=ann_ast,
                    value=val_ast,
                    simple=1,
                )
            elif stmt.initializer.resolved_type and stmt.initializer.resolved_type.startswith(
                ("list[", "set[", "dict[")
            ):
                try:
                    ann_ast = ast.parse(stmt.initializer.resolved_type, mode="eval").body
                except SyntaxError:
                    node = ast.Assign(
                        targets=[ast.Name(id=target_id, ctx=ast.Store())],
                        value=val_ast,
                    )
                else:
                    if self._annotation_is_resolvable(ann_ast):
                        node = ast.AnnAssign(
                            target=ast.Name(id=target_id, ctx=ast.Store()),
                            annotation=ann_ast,
                            value=val_ast,
                            simple=1,
                        )
                    else:
                        node = ast.Assign(
                            targets=[ast.Name(id=target_id, ctx=ast.Store())],
                            value=val_ast,
                        )
            else:
                node = ast.Assign(
                    targets=[ast.Name(id=target_id, ctx=ast.Store())],
                    value=val_ast,
                )
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, UsingResourceStmt):
            # In C#, `using var scope = new GradScope();` wraps the remainder of the
            # enclosing block or executes as a context manager. When standalone inside a block,
            # we emit a `with` statement. (Block-level grouping is handled in `lower_block_with_using`.)
            item = ast.withitem(
                context_expr=self.lower_expr(stmt.initializer),
                optional_vars=ast.Name(id=pascal_to_snake(stmt.name), ctx=ast.Store()),
            )
            cls = ast.AsyncWith if stmt.is_await else ast.With
            node = cls(items=[item], body=[ast.Pass()])
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, IfStmt):
            cond_ast = self.lower_expr(stmt.condition)
            then_body = self._ensure_non_empty_stmts(self._lower_stmt_with_prelude(stmt.then_branch), stmt.span)
            else_body = self._lower_stmt_with_prelude(stmt.else_branch) if stmt.else_branch else []
            node = ast.If(test=cond_ast, body=then_body, orelse=else_body)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, WhileStmt):
            cond_ast = self.lower_expr(stmt.condition)
            body_stmts = self._ensure_non_empty_stmts(self._lower_stmt_with_prelude(stmt.body), stmt.span)
            node = ast.While(test=cond_ast, body=body_stmts, orelse=[])
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ForEachStmt):
            target = ast.Name(id=pascal_to_snake(stmt.item_name), ctx=ast.Store())
            iter_ast = self.lower_expr(stmt.collection)
            body_stmts = self._ensure_non_empty_stmts(self._lower_stmt_with_prelude(stmt.body), stmt.span)
            for_cls = ast.AsyncFor if stmt.is_await else ast.For
            node = for_cls(target=target, iter=iter_ast, body=body_stmts, orelse=[])
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ReturnStmt):
            return_value_ast: ast.expr | None = self.lower_expr(stmt.value) if stmt.value is not None else None
            node = ast.Return(value=return_value_ast)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, BreakStmt):
            return [stamp_span(ast.Break(), stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ContinueStmt):
            return [stamp_span(ast.Continue(), stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, YieldStmt):
            if stmt.is_break:
                node = ast.Return(value=None)
            else:
                yield_value_ast: ast.expr | None = self.lower_expr(stmt.value) if stmt.value is not None else None
                node = ast.Expr(value=ast.Yield(value=yield_value_ast))
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ThrowStmt):
            exc_ast = self.lower_expr(stmt.exception) if stmt.exception is not None else None
            node = ast.Raise(exc=exc_ast, cause=None)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, TryCatchFinallyStmt):
            try_body = self.lower_block(stmt.try_block)
            if any(catch.when_guard is not None for catch in stmt.catches):
                handlers = [self._lower_catch_dispatcher(stmt.catches, stmt.span)]
            else:
                handlers = [self._lower_catch_handler(catch) for catch in stmt.catches]
            finalbody = self.lower_block(stmt.finally_block) if stmt.finally_block else []
            node = ast.Try(body=try_body, handlers=handlers, orelse=[], finalbody=finalbody)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, SwitchStmt):
            subject_ast = self.lower_expr(stmt.scrutinee)
            cases: list[ast.match_case] = []
            for sec in stmt.sections:
                sec_body = []
                for s in sec.statements:
                    sec_body.extend(self._lower_stmt_with_prelude(s))
                sec_body = self._ensure_non_empty_stmts(sec_body, sec.span)
                for pat, guard in sec.labels:
                    py_pat, extra_guard = self.lower_pattern(pat)
                    combined_guard = self._combine_guards(extra_guard, self.lower_expr(guard) if guard else None)
                    mc = ast.match_case(pattern=py_pat, guard=combined_guard, body=sec_body)
                    stamp_span(mc, sec.span)
                    cases.append(mc)
            node = ast.Match(subject=subject_ast, cases=cases)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ExprStmt):
            return [self.lower_expr_as_stmt(stmt.expr)]

        return [ast.Pass()]

    def _lower_catch_handler(self, catch: CatchClause) -> ast.ExceptHandler:
        exc_type_ast = (
            self.lower_type_ref_annotation(catch.exception_type)
            if catch.exception_type is not None
            else ast.Name(id="BaseException", ctx=ast.Load())
        )
        bind_name = pascal_to_snake(catch.bind_name) if catch.bind_name else None
        handler = ast.ExceptHandler(
            type=exc_type_ast,
            name=bind_name,
            body=self.lower_block(catch.body),
        )
        stamp_span(handler, catch.span)
        return handler

    def _lower_catch_dispatcher(
        self,
        catches: list[CatchClause],
        span: SourceSpan,
    ) -> ast.ExceptHandler:
        caught_name = self.allocate_temp_var("_ps_exc")
        bind_names: list[str] = []
        for catch in catches:
            if catch.bind_name:
                bind_name = pascal_to_snake(catch.bind_name)
                if bind_name not in bind_names:
                    bind_names.append(bind_name)
        prelude = [
            ast.Assign(
                targets=[ast.Name(id=bind_name, ctx=ast.Store())],
                value=ast.Name(id=caught_name, ctx=ast.Load()),
            )
            for bind_name in bind_names
        ]
        chain: list[ast.stmt] = [ast.Raise(exc=None, cause=None)]
        for catch in reversed(catches):
            tests: list[ast.expr] = []
            if catch.exception_type is not None:
                tests.append(
                    ast.Call(
                        func=ast.Name(id="isinstance", ctx=ast.Load()),
                        args=[
                            ast.Name(id=caught_name, ctx=ast.Load()),
                            self.lower_type_ref_annotation(catch.exception_type),
                        ],
                        keywords=[],
                    )
                )
            if catch.when_guard is not None:
                tests.append(self.lower_expr(catch.when_guard))
            test: ast.expr
            if not tests:
                test = ast.Constant(value=True)
            elif len(tests) == 1:
                test = tests[0]
            else:
                test = ast.BoolOp(op=ast.And(), values=tests)
            chain = [ast.If(test=test, body=self.lower_block(catch.body), orelse=chain)]
        handler = ast.ExceptHandler(
            type=ast.Name(id="BaseException", ctx=ast.Load()),
            name=caught_name,
            body=[*prelude, *chain],
        )
        stamp_span(handler, span)
        return handler

    def lower_block_with_using(self, statements: list[Stmt], fallback_span: SourceSpan) -> list[ast.stmt]:
        """
        Lowers a list of statements where C# `using var x = expr;` declarations
        automatically wrap all subsequent statements in the block inside a Python `with` block.
        """
        if not statements:
            return [stamp_span(ast.Pass(), fallback_span)]  # type: ignore[list-item]

        for idx, stmt in enumerate(statements):
            if isinstance(stmt, UsingResourceStmt):
                prefix = []
                for pre_s in statements[:idx]:
                    prefix.extend(self.lower_stmt(pre_s))
                remaining = self.lower_block_with_using(statements[idx + 1 :], stmt.span)
                item = ast.withitem(
                    context_expr=self.lower_expr(stmt.initializer),
                    optional_vars=ast.Name(id=pascal_to_snake(stmt.name), ctx=ast.Store()),
                )
                with_cls = ast.AsyncWith if stmt.is_await else ast.With
                with_node = stamp_span(with_cls(items=[item], body=remaining), stmt.span)
                return [*prefix, with_node]  # type: ignore[list-item]

        out: list[ast.stmt] = []
        for s in statements:
            out.extend(self._lower_stmt_with_prelude(s))
        return out or [stamp_span(ast.Pass(), fallback_span)]  # type: ignore[list-item]

    def lower_expr_as_stmt(self, expr: Expr) -> ast.stmt:
        """
        Lowers an `Expr` used in statement position (or expression-bodied void method),
        turning assignment expressions (`=`, `+=`, `??=`) into `ast.Assign` / `ast.AugAssign`.
        """
        if expr.kind == ExprKind.BINARY and expr.data["op"] in ASSIGN_BINARY_OPS:
            op: BinaryOp = expr.data["op"]
            left: Expr = expr.data["left"]
            right: Expr = expr.data["right"]

            target_ast: ast.expr = self._lower_assign_target(left)
            val_ast = self.lower_expr(right)

            if op == BinaryOp.ASSIGN:
                node: ast.stmt = ast.Assign(targets=[target_ast], value=val_ast)
            elif op == BinaryOp.NULL_COALESCE_ASSIGN:
                # `target = target if target is not None else val`
                load_ast = self.lower_expr(left)
                cond = ast.Compare(
                    left=load_ast,
                    ops=[ast.IsNot()],
                    comparators=[ast.Constant(value=None)],
                )
                if_exp = ast.IfExp(test=cond, body=load_ast, orelse=val_ast)
                node = ast.Assign(targets=[target_ast], value=if_exp)
            else:
                aug_map: dict[BinaryOp, ast.operator] = {
                    BinaryOp.ADD_ASSIGN: ast.Add(),
                    BinaryOp.SUB_ASSIGN: ast.Sub(),
                    BinaryOp.MUL_ASSIGN: ast.Mult(),
                    BinaryOp.DIV_ASSIGN: ast.Div(),
                }
                assert isinstance(target_ast, (ast.Name, ast.Attribute, ast.Subscript))
                node = ast.AugAssign(target=target_ast, op=aug_map[op], value=val_ast)
            return stamp_span(node, expr.span)  # type: ignore[return-value]

        if expr.kind == ExprKind.CALL:
            callee: Expr = expr.data["callee"]
            lowering = expr.resolved_lowering or callee.resolved_lowering
            if (
                lowering is not None
                and lowering.kind == "PrimitiveInlineTemplate"
                and not self._contains_null_cond(callee)
            ):
                return self._lower_inline_template_stmt(expr, lowering.inline_template)

        val = self.lower_expr(expr)
        return stamp_span(ast.Expr(value=val), expr.span)  # type: ignore[return-value]

    def _lower_inline_template_stmt(self, expr: Expr, template: str) -> ast.stmt:
        callee: Expr = expr.data["callee"]
        raw_args: list[ArgNode] = expr.data.get("args", [])
        pos_args, _ = self._lower_call_args(raw_args)
        receiver_ast: ast.expr | None = None
        if callee.kind == ExprKind.MEMBER_ACCESS and callee.data.get("target") is not None:
            receiver_ast = self.lower_expr(callee.data["target"])
        sanitized, substitutions = self._prepare_inline_template(template, receiver_ast, pos_args)
        parsed = ast.parse(sanitized, mode="exec").body
        if len(parsed) != 1:
            raise SyntaxError(f"Inline template must expand to one statement: {template!r}")
        node = self._replace_template_placeholders(parsed[0], substitutions)
        return cast(ast.stmt, stamp_span(cast(ast.stmt, node), expr.span))

    def _lower_assign_target(self, target_expr: Expr) -> ast.expr:
        lowered = self.lower_expr(target_expr)
        if isinstance(lowered, (ast.Name, ast.Attribute, ast.Subscript, ast.Tuple, ast.List)):
            lowered.ctx = ast.Store()
        return lowered

    # ========================================================================
    # 2. EXPRESSION LOWERING
    # ========================================================================

    def lower_expr(self, expr: Expr) -> ast.expr:
        kind = expr.kind
        span = expr.span

        if kind == ExprKind.RAW_PYTHON_AST:
            return stamp_span(expr.data["ast"], span)  # type: ignore[return-value]

        if kind == ExprKind.LITERAL:
            return stamp_span(self._lower_literal(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.INTERP_STRING:
            parts: list[InterpolatedPart] = expr.data.get("parts", [])
            values: list[ast.expr] = []
            for p in parts:
                if p.is_expr and p.expr is not None:
                    values.append(ast.FormattedValue(value=self.lower_expr(p.expr), conversion=-1, format_spec=None))
                elif p.text:
                    values.append(ast.Constant(value=p.text))
            return stamp_span(ast.JoinedStr(values=values), span)  # type: ignore[return-value]

        if kind == ExprKind.THIS:
            return stamp_span(ast.Name(id="self", ctx=ast.Load()), span)  # type: ignore[return-value]

        if kind == ExprKind.BASE:
            call = ast.Call(func=ast.Name(id="super", ctx=ast.Load()), args=[], keywords=[])
            return stamp_span(call, span)  # type: ignore[return-value]

        if kind == ExprKind.IDENT:
            return stamp_span(self._lower_ident(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.MEMBER_ACCESS:
            return stamp_span(self._lower_member_access(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.NULL_COND_ACCESS:
            return stamp_span(self._lower_null_conditional_chain(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.NULL_COALESCE:
            return stamp_span(self._lower_null_coalesce(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.UNARY:
            op: UnaryOp = expr.data["op"]
            operand_ast = self.lower_expr(expr.data["operand"])
            if op == UnaryOp.AWAIT:
                return stamp_span(ast.Await(value=operand_ast), span)  # type: ignore[return-value]
            if op == UnaryOp.NOT:
                return stamp_span(ast.UnaryOp(op=ast.Not(), operand=operand_ast), span)  # type: ignore[return-value]
            if op == UnaryOp.BITWISE_NOT:
                return stamp_span(ast.UnaryOp(op=ast.Invert(), operand=operand_ast), span)  # type: ignore[return-value]
            # Both UnaryOp.NEG (`-x`) and UnaryOp.FROM_END (`^x`) lower to `-x`!
            return stamp_span(ast.UnaryOp(op=ast.USub(), operand=operand_ast), span)  # type: ignore[return-value]

        if kind == ExprKind.BINARY:
            return stamp_span(self._lower_binary(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.CALL:
            return stamp_span(self._lower_call(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.NEW_OBJECT:
            return stamp_span(self._lower_new_object(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.INDEX_OR_SLICE:
            return stamp_span(self._lower_index_or_slice(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.LIST_LITERAL:
            elts = [self.lower_expr(e) for e in expr.data.get("elements", ())]
            return stamp_span(ast.List(elts=elts, ctx=ast.Load()), span)  # type: ignore[return-value]

        if kind == ExprKind.TUPLE_LITERAL:
            elts = [self.lower_expr(e) for e in expr.data.get("elements", ())]
            return stamp_span(ast.Tuple(elts=elts, ctx=ast.Load()), span)  # type: ignore[return-value]

        if kind == ExprKind.TYPE_CHECK_IS:
            return stamp_span(self._lower_type_check_is(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.TYPE_CAST_AS:
            return stamp_span(self._lower_type_cast_as(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.LAMBDA:
            return stamp_span(self._lower_lambda(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.SWITCH_EXPR:
            return stamp_span(self._lower_switch_expr(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.CONDITIONAL:
            test_ast = self.lower_expr(expr.data["condition"])
            body_ast = self.lower_expr(expr.data["then_expr"])
            orelse_ast = self.lower_expr(expr.data["else_expr"])
            return stamp_span(ast.IfExp(test=test_ast, body=body_ast, orelse=orelse_ast), span)  # type: ignore[return-value]

        if kind == ExprKind.LINQ_COMPREHENSION:
            return stamp_span(self._lower_linq_comprehension(expr), span)  # type: ignore[return-value]

        return stamp_span(ast.Constant(value=None), span)  # type: ignore[return-value]

    # ========================================================================
    # 3. SPECIFIC EXPRESSION LOWERING HELPERS
    # ========================================================================

    def _lower_literal(self, expr: Expr) -> ast.expr:
        lit_kind: LiteralKind = expr.data["literal_kind"]
        val = expr.data.get("value")
        if lit_kind == LiteralKind.DECIMAL:
            self.needs_decimal_import = True
            return ast.Call(
                func=ast.Name(id="Decimal", ctx=ast.Load()),
                args=[ast.Constant(value=str(val))],
                keywords=[],
            )
        if lit_kind in (LiteralKind.NULL, LiteralKind.DEFAULT):
            return ast.Constant(value=None)
        return ast.Constant(value=val)

    def _lower_ident(self, expr: Expr) -> ast.expr:
        raw_name = str(expr.data.get("name", ""))
        lowering = expr.resolved_lowering
        attr_name = (
            lowering.emitted_snake_name if lowering and lowering.emitted_snake_name else pascal_to_snake(raw_name)
        )

        if expr.data.get("implicit_this"):
            return ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr=attr_name,
                ctx=ast.Load(),
            )

        static_owner = expr.data.get("static_owner")
        if static_owner:
            attr = ast.Attribute(
                value=ast.Name(id=str(static_owner), ctx=ast.Load()),
                attr=attr_name,
                ctx=ast.Load(),
            )
            if expr.data.get("static_property_call"):
                return ast.Call(func=attr, args=[], keywords=[])
            return attr

        # Check if `raw_name` refers to a known TypeSymbol (e.g. `Order`, `Math`, `Console`)
        if self.current_type is not None:
            type_sym = self.symtab.lookup_type_in_context(
                [raw_name], self.current_type.namespace, self.current_type.unit.imports
            )
            if type_sym is not None:
                return ast.Name(id=type_sym.maps_to_py_type or type_sym.name, ctx=ast.Load())

        if raw_name in self.symtab.short_name_index:
            sym = self.symtab.short_name_index[raw_name][0]
            return ast.Name(id=sym.maps_to_py_type or sym.name, ctx=ast.Load())

        return ast.Name(id=pascal_to_snake(raw_name), ctx=ast.Load())

    def _lower_member_access(self, expr: Expr) -> ast.expr:
        target_expr: Expr = expr.data["target"]
        member_name: str = str(expr.data["member"])
        lowering = expr.resolved_lowering

        if lowering is not None and lowering.kind == "PrimitiveInlineTemplate":
            receiver_ast = self.lower_expr(target_expr)
            return self.expand_inline_template(lowering.inline_template, receiver_ast, [])

        receiver_ast = self.lower_expr(target_expr)

        # Preserve exact enum member casing if accessing an Enum type
        if isinstance(receiver_ast, ast.Name) and receiver_ast.id in self.symtab.short_name_index:
            t_sym = self.symtab.short_name_index[receiver_ast.id][0]
            if t_sym.is_enum:
                return ast.Attribute(value=receiver_ast, attr=member_name, ctx=ast.Load())

        if lowering is not None and lowering.kind == "PrimitiveDirect" and lowering.py_target_name:
            attr_name = lowering.py_target_name
        elif lowering is not None and lowering.emitted_snake_name:
            attr_name = lowering.emitted_snake_name
        else:
            attr_name = pascal_to_snake(member_name)

        attr = ast.Attribute(value=receiver_ast, attr=attr_name, ctx=ast.Load())
        if expr.data.get("static_property_call"):
            return ast.Call(func=attr, args=[], keywords=[])
        return attr

    def _lower_null_conditional_chain(self, expr: Expr) -> ast.expr:
        """
        Lowers `user?.Profile?.Name` into:
        `(_ps_t1.name if (_ps_t0 := user) is not None and (_ps_t1 := _ps_t0.profile) is not None else None)`
        """
        steps: list[tuple[str, str, list[ArgNode] | None]] = []
        curr: Expr = expr

        while True:
            if curr.kind == ExprKind.NULL_COND_ACCESS:
                m_name = pascal_to_snake(str(curr.data["member"]))
                if curr.data.get("is_call"):
                    steps.append(("call", m_name, list(curr.data.get("args", ()))))
                else:
                    steps.append(("null_cond_attr", m_name, None))
                curr = curr.data["target"]
            elif curr.kind == ExprKind.MEMBER_ACCESS and self._contains_null_cond(curr.data["target"]):
                m_name = pascal_to_snake(str(curr.data["member"]))
                steps.append(("attr", m_name, None))
                curr = curr.data["target"]
            elif curr.kind == ExprKind.CALL and self._contains_null_cond(curr.data["callee"]):
                callee: Expr = curr.data["callee"]
                m_name = pascal_to_snake(str(callee.data.get("member", "")))
                steps.append(("call", m_name, list(curr.data.get("args", ()))))
                curr = callee.data["target"]
            else:
                break

        steps.reverse()
        root_ast = self.lower_expr(curr)
        t0 = self.allocate_temp_var("_ps_nc")
        conditions: list[ast.expr] = [
            ast.Compare(
                left=ast.NamedExpr(
                    target=ast.Name(id=t0, ctx=ast.Store()),
                    value=root_ast,
                ),
                ops=[ast.IsNot()],
                comparators=[ast.Constant(value=None)],
            )
        ]

        current_ref: ast.expr = ast.Name(id=t0, ctx=ast.Load())
        for idx, (step_kind, attr_name, call_args) in enumerate(steps):
            is_last = idx == len(steps) - 1
            if step_kind in ("null_cond_attr", "attr"):
                accessed: ast.expr = ast.Attribute(value=current_ref, attr=attr_name, ctx=ast.Load())
            else:
                pos_args, kw_args = self._lower_call_args(call_args or [])
                accessed = ast.Call(
                    func=ast.Attribute(value=current_ref, attr=attr_name, ctx=ast.Load()),
                    args=pos_args,
                    keywords=kw_args,
                )

            if not is_last:
                ti = self.allocate_temp_var("_ps_nc")
                conditions.append(
                    ast.Compare(
                        left=ast.NamedExpr(
                            target=ast.Name(id=ti, ctx=ast.Store()),
                            value=accessed,
                        ),
                        ops=[ast.IsNot()],
                        comparators=[ast.Constant(value=None)],
                    )
                )
                current_ref = ast.Name(id=ti, ctx=ast.Load())
            else:
                current_ref = accessed

        test_ast = conditions[0] if len(conditions) == 1 else ast.BoolOp(op=ast.And(), values=conditions)
        return ast.IfExp(test=test_ast, body=current_ref, orelse=ast.Constant(value=None))

    def _contains_null_cond(self, expr: Expr | None) -> bool:
        if expr is None:
            return False
        if expr.kind == ExprKind.NULL_COND_ACCESS:
            return True
        if expr.kind == ExprKind.MEMBER_ACCESS:
            return self._contains_null_cond(expr.data.get("target"))
        if expr.kind == ExprKind.CALL:
            return self._contains_null_cond(expr.data.get("callee"))
        return False

    def _lower_null_coalesce(self, expr: Expr) -> ast.expr:
        """Lowers `a ?? b` to `(_ps_t0 if (_ps_t0 := a) is not None else b)`."""
        left_ast = self.lower_expr(expr.data["left"])
        right_ast = self.lower_expr(expr.data["right"])
        tmp = self.allocate_temp_var("_ps_coal")
        named = ast.NamedExpr(target=ast.Name(id=tmp, ctx=ast.Store()), value=left_ast)
        cond = ast.Compare(left=named, ops=[ast.IsNot()], comparators=[ast.Constant(value=None)])
        return ast.IfExp(
            test=cond,
            body=ast.Name(id=tmp, ctx=ast.Load()),
            orelse=right_ast,
        )

    def _lower_binary(self, expr: Expr) -> ast.expr:
        op: BinaryOp = expr.data["op"]
        left_ast = self.lower_expr(expr.data["left"])
        right_ast = self.lower_expr(expr.data["right"])

        if op == BinaryOp.AND:
            return ast.BoolOp(op=ast.And(), values=[left_ast, right_ast])
        if op == BinaryOp.OR:
            return ast.BoolOp(op=ast.Or(), values=[left_ast, right_ast])

        cmp_map: dict[BinaryOp, ast.cmpop] = {
            BinaryOp.EQ: ast.Eq(),
            BinaryOp.NEQ: ast.NotEq(),
            BinaryOp.LT: ast.Lt(),
            BinaryOp.LTE: ast.LtE(),
            BinaryOp.GT: ast.Gt(),
            BinaryOp.GTE: ast.GtE(),
            BinaryOp.IN: ast.In(),
        }
        if op in cmp_map:
            return ast.Compare(left=left_ast, ops=[cmp_map[op]], comparators=[right_ast])

        if op == BinaryOp.DIV:
            def _is_int_type(t: object) -> bool:
                if not t:
                    return False
                name = getattr(t, "qualified_name", None) or (t if isinstance(t, str) else "")
                return name in ("int", "long", "short", "byte", "sbyte", "ushort", "uint", "ulong")

            def _is_float_type(t: object) -> bool:
                if not t:
                    return False
                name = getattr(t, "qualified_name", None) or (t if isinstance(t, str) else "")
                return name in ("float", "double", "decimal")

            left_t = getattr(expr.data.get("left"), "resolved_type", None)
            right_t = getattr(expr.data.get("right"), "resolved_type", None)
            has_float = _is_float_type(expr.resolved_type) or _is_float_type(left_t) or _is_float_type(right_t)
            is_int_div = not has_float and (
                _is_int_type(expr.resolved_type) or (_is_int_type(left_t) and _is_int_type(right_t))
            )
            op_node = ast.FloorDiv() if is_int_div else ast.Div()
            return ast.BinOp(left=left_ast, op=op_node, right=right_ast)

        bin_map: dict[BinaryOp, ast.operator] = {
            BinaryOp.ADD: ast.Add(),
            BinaryOp.SUB: ast.Sub(),
            BinaryOp.MUL: ast.Mult(),
            BinaryOp.MOD: ast.Mod(),
            BinaryOp.POW: ast.Pow(),
            BinaryOp.BITWISE_AND: ast.BitAnd(),
            BinaryOp.BITWISE_OR: ast.BitOr(),
            BinaryOp.BITWISE_XOR: ast.BitXor(),
            BinaryOp.LSHIFT: ast.LShift(),
            BinaryOp.RSHIFT: ast.RShift(),
        }
        if op in bin_map:
            return ast.BinOp(left=left_ast, op=bin_map[op], right=right_ast)

        # Fallback if an assignment expression is used inside an expression context
        if isinstance(left_ast, ast.Name):
            return ast.NamedExpr(
                target=ast.Name(id=left_ast.id, ctx=ast.Store()),
                value=right_ast,
            )
        return right_ast

    def _lower_call(self, expr: Expr) -> ast.expr:
        callee: Expr = expr.data["callee"]
        if self._contains_null_cond(callee):
            return self._lower_null_conditional_chain(expr)

        raw_args: list[ArgNode] = expr.data.get("args", [])
        pos_args, kw_args = self._lower_call_args(raw_args)

        lowering = expr.resolved_lowering or callee.resolved_lowering
        if lowering is not None and lowering.kind == "PrimitiveInlineTemplate":
            receiver_ast: ast.expr | None = None
            if callee.kind == ExprKind.MEMBER_ACCESS and callee.data.get("target") is not None:
                receiver_ast = self.lower_expr(callee.data["target"])
            return self.expand_inline_template(lowering.inline_template, receiver_ast, pos_args)

        if callee.kind == ExprKind.MEMBER_ACCESS:
            target_ast = self.lower_expr(callee.data["target"])
            if lowering is not None and lowering.kind == "PrimitiveDirect" and lowering.py_target_name:
                target_py = lowering.py_target_name
                if "." in target_py:
                    # e.g., `math.sqrt` or `datetime.datetime.fromisoformat`
                    parts = target_py.split(".")
                    func_ast: ast.expr = ast.Name(id=parts[0], ctx=ast.Load())
                    for seg in parts[1:]:
                        func_ast = ast.Attribute(value=func_ast, attr=seg, ctx=ast.Load())
                else:
                    func_ast = ast.Attribute(value=target_ast, attr=target_py, ctx=ast.Load())
            else:
                attr_name = (
                    lowering.emitted_snake_name
                    if lowering and lowering.emitted_snake_name
                    else pascal_to_snake(str(callee.data["member"]))
                )
                func_ast = ast.Attribute(value=target_ast, attr=attr_name, ctx=ast.Load())
        else:
            func_ast = self.lower_expr(callee)

        return ast.Call(func=func_ast, args=pos_args, keywords=kw_args)

    def _lower_new_object(self, expr: Expr) -> ast.expr:
        type_ref: TypeRef = expr.data["type_ref"]
        raw_args: list[ArgNode] = expr.data.get("args", [])
        pos_args, kw_args = self._lower_call_args(raw_args)

        lowering = expr.resolved_lowering
        if lowering is not None and lowering.kind == "PrimitiveInlineTemplate":
            return self.expand_inline_template(lowering.inline_template, None, pos_args)

        # Fallback check for standard primitive collections (`new Dict<K,V>()`, `new List<T>()`, `new HashSet<T>()`)
        short_type = type_ref.path[-1] if type_ref.path else ""
        if short_type == "Dict" and not pos_args and not kw_args:
            return ast.Dict(keys=[], values=[])
        if short_type == "List" and not pos_args and not kw_args:
            return ast.List(elts=[], ctx=ast.Load())
        if short_type == "HashSet" and not pos_args and not kw_args:
            return ast.Call(func=ast.Name(id="set", ctx=ast.Load()), args=[], keywords=[])

        for prop_name, init_val in expr.data.get("initializers", ()):
            kw_args.append(ast.keyword(arg=pascal_to_snake(prop_name), value=self.lower_expr(init_val)))

        cls_name = short_type or "object"
        current_ns = self.current_type.namespace if self.current_type else ()
        imports = self.current_type.unit.imports if self.current_type else []
        target_sym = self.symtab.lookup_type_in_context(type_ref.path, current_ns, imports)
        if target_sym is not None and target_sym.is_ambient_stub and target_sym.maps_to_py_type:
            func_ast = ast.parse(target_sym.maps_to_py_type, mode="eval").body
        else:
            func_ast = ast.Name(id=cls_name, ctx=ast.Load())
        return ast.Call(
            func=func_ast,
            args=pos_args,
            keywords=kw_args,
        )

    def _lower_call_args(self, args: list[ArgNode]) -> tuple[list[ast.expr], list[ast.keyword]]:
        pos: list[ast.expr] = []
        kws: list[ast.keyword] = []
        for a in args:
            val_ast = self.lower_expr(a.expr)
            if a.name is not None:
                kws.append(ast.keyword(arg=pascal_to_snake(a.name), value=val_ast))
            else:
                pos.append(val_ast)
        return pos, kws

    def _lower_index_or_slice(self, expr: Expr) -> ast.expr:
        target_ast = self.lower_expr(expr.data["target"])
        dims: list[SliceDimension] = expr.data.get("dimensions", [])
        lowered_dims = [self._lower_slice_dimension(d) for d in dims]
        if len(lowered_dims) == 1:
            slice_ast = lowered_dims[0]
        else:
            slice_ast = ast.Tuple(elts=lowered_dims, ctx=ast.Load())
        return ast.Subscript(value=target_ast, slice=slice_ast, ctx=ast.Load())

    def _lower_slice_dimension(self, dim: SliceDimension) -> ast.expr:
        if not dim.is_range_or_slice and dim.single_expr is not None:
            return self.lower_expr(dim.single_expr)
        lower_ast = self.lower_expr(dim.start) if dim.start is not None else None
        upper_ast = self.lower_expr(dim.stop) if dim.stop is not None else None
        step_ast = self.lower_expr(dim.step) if dim.step is not None else None
        return ast.Slice(lower=lower_ast, upper=upper_ast, step=step_ast)

    def _lower_type_check_is(self, expr: Expr) -> ast.expr:
        target_ast = self.lower_expr(expr.data["target"])
        pat: PatternNode = expr.data["pattern"]
        rt_check: RuntimeTypeCheck | None = expr.data.get("runtime_type_check")

        if pat.kind == "Null":
            return ast.Compare(left=target_ast, ops=[ast.Is()], comparators=[ast.Constant(value=None)])
        if pat.kind == "Literal" and pat.literal_expr is not None:
            return ast.Compare(
                left=target_ast,
                ops=[ast.Eq()],
                comparators=[self.lower_expr(pat.literal_expr)],
            )

        if pat.bind_name:
            bind_id = pascal_to_snake(pat.bind_name)
            subject_ast: ast.expr = ast.NamedExpr(
                target=ast.Name(id=bind_id, ctx=ast.Store()),
                value=target_ast,
            )
        else:
            subject_ast = target_ast

        check_ast = self.build_runtime_type_check_ast(subject_ast, rt_check, pat.type_ref)

        # If property subpatterns exist (`x is Order { IsActive: true }`), conjoin them
        if pat.property_subpatterns:
            ref_name = pascal_to_snake(pat.bind_name) if pat.bind_name else None
            if ref_name is None:
                ref_name = self.allocate_temp_var("_ps_is")
                subject_ast = ast.NamedExpr(
                    target=ast.Name(id=ref_name, ctx=ast.Store()),
                    value=target_ast,
                )
                check_ast = self.build_runtime_type_check_ast(subject_ast, rt_check, pat.type_ref)
            checks = [check_ast]
            for prop_name, sub_pat in pat.property_subpatterns:
                prop_attr = ast.Attribute(
                    value=ast.Name(id=ref_name, ctx=ast.Load()),
                    attr=pascal_to_snake(prop_name),
                    ctx=ast.Load(),
                )
                if sub_pat.literal_expr is not None:
                    checks.append(
                        ast.Compare(
                            left=prop_attr,
                            ops=[ast.Eq()],
                            comparators=[self.lower_expr(sub_pat.literal_expr)],
                        )
                    )
            return ast.BoolOp(op=ast.And(), values=checks)

        return check_ast

    def _lower_type_cast_as(self, expr: Expr) -> ast.expr:
        target_ast = self.lower_expr(expr.data["target"])
        type_ref: TypeRef = expr.data["type_ref"]
        rt_check: RuntimeTypeCheck | None = expr.data.get("runtime_type_check")

        tmp = self.allocate_temp_var("_ps_as")
        named = ast.NamedExpr(target=ast.Name(id=tmp, ctx=ast.Store()), value=target_ast)
        cond = self.build_runtime_type_check_ast(named, rt_check, type_ref)
        return ast.IfExp(
            test=cond,
            body=ast.Name(id=tmp, ctx=ast.Load()),
            orelse=ast.Constant(value=None),
        )

    def build_runtime_type_check_ast(
        self,
        subject_ast: ast.expr,
        rt_check: RuntimeTypeCheck | None,
        fallback_type_ref: TypeRef | None = None,
    ) -> ast.expr:
        if rt_check is not None and rt_check.kind == "PsTypesContains":
            getattr_call = ast.Call(
                func=ast.Name(id="getattr", ctx=ast.Load()),
                args=[
                    subject_ast,
                    ast.Constant(value="__ps_types__"),
                    ast.Tuple(elts=[], ctx=ast.Load()),
                ],
                keywords=[],
            )
            return ast.Compare(
                left=ast.Constant(value=rt_check.target_type),
                ops=[ast.In()],
                comparators=[getattr_call],
            )

        target_type_str = (
            rt_check.target_type
            if rt_check and rt_check.target_type
            else (fallback_type_ref.path[-1] if fallback_type_ref and fallback_type_ref.path else "object")
        )
        type_map = {"string": "str", "bool": "bool", "int": "int", "double": "float", "decimal": "Decimal"}
        py_type_expr = ast.parse(type_map.get(target_type_str, target_type_str), mode="eval").body

        isinstance_call = ast.Call(
            func=ast.Name(id="isinstance", ctx=ast.Load()),
            args=[subject_ast, py_type_expr],
            keywords=[],
        )
        if rt_check is not None and rt_check.kind == "PyIsInstanceStrictInt":
            not_bool = ast.UnaryOp(
                op=ast.Not(),
                operand=ast.Call(
                    func=ast.Name(id="isinstance", ctx=ast.Load()),
                    args=[subject_ast, ast.Name(id="bool", ctx=ast.Load())],
                    keywords=[],
                ),
            )
            return ast.BoolOp(op=ast.And(), values=[isinstance_call, not_bool])
        return isinstance_call

    def _lower_lambda(self, expr: Expr) -> ast.expr:
        params = expr.data.get("params", [])
        py_args = [ast.arg(arg=pascal_to_snake(p.name)) for p in params]
        body = expr.data.get("body")
        is_async = bool(expr.data.get("is_async"))

        if isinstance(body, Expr) and not is_async:
            return ast.Lambda(
                args=ast.arguments(
                    posonlyargs=[],
                    args=py_args,
                    kwonlyargs=[],
                    kw_defaults=[],
                    defaults=[],
                ),
                body=self.lower_expr(body),
            )

        name = self.allocate_temp_var("_ps_lambda")
        start = len(self._pending_stmts)
        if isinstance(body, BlockStmt):
            fn_body = self.lower_block(body)
        elif isinstance(body, Expr):
            value_ast = self.lower_expr(body)
            nested = self._pending_stmts[start:]
            del self._pending_stmts[start:]
            fn_body = [*nested, ast.Return(value=value_ast)]
        else:
            fn_body = [ast.Pass()]
        fn_cls = ast.AsyncFunctionDef if is_async else ast.FunctionDef
        fn = fn_cls(
            name=name,
            args=ast.arguments(
                posonlyargs=[],
                args=py_args,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=fn_body,
            decorator_list=[],
            returns=None,
        )
        self._pending_stmts.append(cast(ast.stmt, stamp_span(fn, expr.span)))
        return ast.Name(id=name, ctx=ast.Load())

    def _lower_switch_expr(self, expr: Expr) -> ast.expr:
        """
        Lowers a C# `switch` expression (`val switch { pat1 => res1, _ => res2 }`)
        into a nested conditional expression (`ast.IfExp`) with walrus pattern binding.
        """
        scrutinee_ast = self.lower_expr(expr.data["scrutinee"])
        arms: list[SwitchArm] = expr.data.get("arms", [])
        if not arms:
            return ast.Constant(value=None)

        tmp = self.allocate_temp_var("_ps_sw")

        def build_arms(idx: int, first: bool) -> ast.expr:
            arm = arms[idx]
            res_ast = self.lower_expr(arm.result_expr)
            if idx == len(arms) - 1 and arm.pattern.kind == "Discard" and arm.when_guard is None:
                return res_ast

            subj: ast.expr = (
                ast.NamedExpr(target=ast.Name(id=tmp, ctx=ast.Store()), value=scrutinee_ast)
                if first
                else ast.Name(id=tmp, ctx=ast.Load())
            )
            cond = self._pattern_to_bool_expr(subj, arm.pattern, arm.when_guard)
            rest = build_arms(idx + 1, False) if idx + 1 < len(arms) else ast.Constant(value=None)
            return ast.IfExp(test=cond, body=res_ast, orelse=rest)

        return build_arms(0, True)

    def _pattern_to_bool_expr(self, subject_ast: ast.expr, pat: PatternNode, when_guard: Expr | None) -> ast.expr:
        conds: list[ast.expr] = []
        if pat.kind == "Null":
            conds.append(ast.Compare(left=subject_ast, ops=[ast.Is()], comparators=[ast.Constant(value=None)]))
        elif pat.kind == "Literal" and pat.literal_expr is not None:
            conds.append(
                ast.Compare(
                    left=subject_ast,
                    ops=[ast.Eq()],
                    comparators=[self.lower_expr(pat.literal_expr)],
                )
            )
        elif pat.kind == "TypePattern" and pat.type_ref is not None:
            subj: ast.expr
            if pat.bind_name:
                bind_id = pascal_to_snake(pat.bind_name)
                subj = ast.NamedExpr(
                    target=ast.Name(id=bind_id, ctx=ast.Store()),
                    value=subject_ast,
                )
            else:
                subj = subject_ast
            conds.append(self.build_runtime_type_check_ast(subj, None, pat.type_ref))

        if when_guard is not None:
            conds.append(self.lower_expr(when_guard))

        if not conds:
            return ast.Constant(value=True)
        return conds[0] if len(conds) == 1 else ast.BoolOp(op=ast.And(), values=conds)

    def lower_pattern(self, pat: PatternNode | None) -> tuple[ast.pattern, ast.expr | None]:
        """Lowers a `PatternNode` for a `match` / `case` statement."""
        if pat is None or pat.kind == "Discard":
            return ast.MatchAs(pattern=None, name=None), None
        if pat.kind == "Null":
            return ast.MatchSingleton(value=None), None
        if pat.kind == "Literal" and pat.literal_expr is not None:
            return ast.MatchValue(value=self.lower_expr(pat.literal_expr)), None
        if pat.kind == "TypePattern" and pat.type_ref is not None:
            type_name = pat.type_ref.path[-1] if pat.type_ref.path else "object"
            py_map = {"string": "str", "int": "int", "bool": "bool", "double": "float", "decimal": "Decimal"}
            cls_id = py_map.get(type_name, type_name)
            bind_id = pascal_to_snake(pat.bind_name) if pat.bind_name else None

            # Check if `cls_id` is a PythonSharp interface -> match variable + `__ps_types__` guard
            if cls_id in self.symtab.short_name_index and self.symtab.short_name_index[cls_id][0].is_interface:
                iface_sym = self.symtab.short_name_index[cls_id][0]
                var_id = bind_id or self.allocate_temp_var("_ps_m")
                guard = self.build_runtime_type_check_ast(
                    ast.Name(id=var_id, ctx=ast.Load()),
                    RuntimeTypeCheck(kind="PsTypesContains", target_type=iface_sym.qualified_name),
                )
                return ast.MatchAs(pattern=None, name=var_id), guard

            kwd_attrs: list[str] = []
            kwd_pats: list[ast.pattern] = []
            for prop_name, sub_p in pat.property_subpatterns:
                sub_py_pat, _ = self.lower_pattern(sub_p)
                kwd_attrs.append(pascal_to_snake(prop_name))
                kwd_pats.append(sub_py_pat)

            cls_pat = ast.MatchClass(
                cls=ast.Name(id=cls_id, ctx=ast.Load()),
                patterns=[],
                kwd_attrs=kwd_attrs,
                kwd_patterns=kwd_pats,
            )
            if bind_id:
                return ast.MatchAs(pattern=cls_pat, name=bind_id), None
            return cls_pat, None

        return ast.MatchAs(pattern=None, name=None), None

    # ========================================================================
    # 4. ZERO-OVERHEAD LINQ COMPREHENSION LOWERING
    # ========================================================================

    def _lower_linq_comprehension(self, expr: Expr) -> ast.expr:
        generators_data: list[ComprehensionGenerator] = expr.data.get("generators", [])
        projection: Expr | None = expr.data.get("projection")
        key_proj: Expr | None = expr.data.get("key_projection")
        val_proj: Expr | None = expr.data.get("value_projection")
        terminal_kind: ComprehensionKind = expr.data["terminal_kind"]

        py_generators: list[ast.comprehension] = []
        last_item_var = "_x"

        for gen in generators_data:
            last_item_var = pascal_to_snake(gen.item_var)
            iter_ast = self.lower_expr(gen.iterable)
            ifs_ast = [self.lower_expr(f) for f in gen.filters]
            py_generators.append(
                ast.comprehension(
                    target=ast.Name(id=last_item_var, ctx=ast.Store()),
                    iter=iter_ast,
                    ifs=ifs_ast,
                    is_async=0,
                )
            )

        elt_ast: ast.expr = (
            self.lower_expr(projection) if projection is not None else ast.Name(id=last_item_var, ctx=ast.Load())
        )

        if terminal_kind == ComprehensionKind.LIST:
            return ast.ListComp(elt=elt_ast, generators=py_generators)

        if terminal_kind == ComprehensionKind.SET:
            return ast.SetComp(elt=elt_ast, generators=py_generators)

        if terminal_kind == ComprehensionKind.DICT:
            k_ast = self.lower_expr(key_proj) if key_proj else elt_ast
            v_ast = self.lower_expr(val_proj) if val_proj else elt_ast
            return ast.DictComp(key=k_ast, value=v_ast, generators=py_generators)

        if terminal_kind == ComprehensionKind.GENERATOR:
            return ast.GeneratorExp(elt=elt_ast, generators=py_generators)

        if terminal_kind in (
            ComprehensionKind.ANY,
            ComprehensionKind.ALL,
            ComprehensionKind.SUM,
            ComprehensionKind.MIN,
            ComprehensionKind.MAX,
        ):
            fn_map = {
                ComprehensionKind.ANY: "any",
                ComprehensionKind.ALL: "all",
                ComprehensionKind.SUM: "sum",
                ComprehensionKind.MIN: "min",
                ComprehensionKind.MAX: "max",
            }
            gen_exp = ast.GeneratorExp(elt=elt_ast, generators=py_generators)
            return ast.Call(
                func=ast.Name(id=fn_map[terminal_kind], ctx=ast.Load()),
                args=[gen_exp],
                keywords=[],
            )

        if terminal_kind == ComprehensionKind.COUNT:
            gen_exp = ast.GeneratorExp(elt=ast.Constant(value=1), generators=py_generators)
            return ast.Call(
                func=ast.Name(id="sum", ctx=ast.Load()),
                args=[gen_exp],
                keywords=[],
            )

        if terminal_kind == ComprehensionKind.FIRST_OR_DEFAULT:
            gen_exp = ast.GeneratorExp(elt=elt_ast, generators=py_generators)
            return ast.Call(
                func=ast.Name(id="next", ctx=ast.Load()),
                args=[gen_exp, ast.Constant(value=None)],
                keywords=[],
            )

        return ast.ListComp(elt=elt_ast, generators=py_generators)

    # ========================================================================
    # 5. INLINE TEMPLATE EXPANDER & TYPE ANNOTATION HELPER
    # ========================================================================

    def expand_inline_template(
        self,
        template: str,
        receiver: ast.expr | None,
        args: list[ast.expr],
        value_expr: ast.expr | None = None,
    ) -> ast.expr:
        """
        Parses an `[InlineTemplate("...")]` string (such as `"len({self})"`, `"({0} in {self})"`,
        `"{}"`, or `"[]"`) into a Python `ast.expr` and substitutes `{self}`, `{0}`, `{1}`, `{value}`.
        """
        sanitized, substitutions = self._prepare_inline_template(template, receiver, args, value_expr)
        parsed_expr = ast.parse(sanitized, mode="eval").body
        return cast(ast.expr, self._replace_template_placeholders(parsed_expr, substitutions))

    @staticmethod
    def _prepare_inline_template(
        template: str,
        receiver: ast.expr | None,
        args: list[ast.expr],
        value_expr: ast.expr | None = None,
    ) -> tuple[str, dict[str, ast.expr]]:
        substitutions: dict[str, ast.expr] = {}
        if receiver is not None:
            substitutions["__ps_tpl_self__"] = receiver
        if value_expr is not None:
            substitutions["__ps_tpl_value__"] = value_expr
        for idx, arg_node in enumerate(args):
            substitutions[f"__ps_tpl_arg_{idx}__"] = arg_node

        def repl(match: re.Match[str]) -> str:
            token = match.group(1)
            if token == "self":
                return "__ps_tpl_self__"
            if token == "value":
                return "__ps_tpl_value__"
            return f"__ps_tpl_arg_{token}__"

        return _TEMPLATE_PLACEHOLDER_RE.sub(repl, template), substitutions

    @staticmethod
    def _replace_template_placeholders(node: ast.AST, substitutions: dict[str, ast.expr]) -> ast.AST:
        class _PlaceholderReplacer(ast.NodeTransformer):
            def visit_Name(self, self_node: ast.Name) -> Any:
                if self_node.id in substitutions:
                    return substitutions[self_node.id]
                return self_node

        return cast(ast.AST, _PlaceholderReplacer().visit(node))

    def lower_type_ref_annotation(self, type_ref: TypeRef | None) -> ast.expr:
        if type_ref is None:
            return ast.Constant(value=None)
        current_ns = self.current_type.namespace if self.current_type else ()
        imports = self.current_type.unit.imports if self.current_type else []
        active_tparams = set(self.current_type.type_params) if self.current_type else set()

        resolved = self.symtab.resolve_type_ref(
            type_ref,
            current_ns=current_ns,
            imports=imports,
            active_type_params=active_tparams,
        )
        if "Decimal" in resolved.py_annotation:
            self.needs_decimal_import = True
        try:
            return ast.parse(resolved.py_annotation, mode="eval").body
        except SyntaxError:
            return ast.Name(id="Any", ctx=ast.Load())

    @staticmethod
    def _ensure_non_empty_stmts(stmts: list[ast.stmt], span: SourceSpan) -> list[ast.stmt]:
        return stmts if stmts else [stamp_span(ast.Pass(), span)]  # type: ignore[list-item]

    @staticmethod
    def _combine_guards(g1: ast.expr | None, g2: ast.expr | None) -> ast.expr | None:
        if g1 is not None and g2 is not None:
            return ast.BoolOp(op=ast.And(), values=[g1, g2])
        return g1 or g2
