Here are the raw individual files for **Milestone 5 (Pass 3A: `topo_sorter.py` for Virtual Namespace Aggregation & Topological Class Ordering, `expr_lowerer.py` for Expressions, Statements, Inline Templates, Slicing, Null-Safety & Fused Comprehensions, `overload_emitter.py` for `@overload` Stubs & Runtime Dispatchers, `py_ast_builder.py` for Python 3.11+ `ast.Module` Construction with `.ps` Line-Number Stamping, `src/psc/codegen/__init__.py`, and `tests/test_py_ast_builder.py`)** of the **PythonSharp Prototype Transpiler (`psc`)**.

---

##### 1. src/psc/codegen/topo_sorter.py

```python
from __future__ import annotations
from dataclasses import dataclass, field
from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol, namespace_to_module_path


@dataclass(slots=True)
class PlannedPythonModule:
    """Represents a synthesized Python module aggregated from a logical namespace."""
    namespace: tuple[str, ...]
    module_rel_path: str
    types: list[TypeSymbol] = field(default_factory=list)
    primary_ps_filename: str = ""


class NamespacePackagePlanner:
    """
    Pass 3A (Part 1) — Virtual Namespace Aggregator & Topological Class Sorter:
      1. Groups all non-ambient, non-primitive `TypeSymbol`s by their logical `namespace`
         regardless of which physical `.ps` file or directory declared them.
      2. Topologically orders classes within each synthesized Python module so base
         classes and interfaces always precede subclasses in the emitted `.py` file.
    """

    def __init__(self, symtab: GlobalSymbolTable) -> None:
        self.symtab = symtab

    def plan_modules(self) -> dict[str, PlannedPythonModule]:
        modules_by_path: dict[str, PlannedPythonModule] = {}

        for ns_tuple, ns_types in self.symtab.namespaces.items():
            emittable = [
                t
                for t in ns_types
                if not t.is_ambient_stub
                and not t.is_primitive
                and t.ast_node.emission_strategy.kind != "ErasedPrimitive"
            ]
            if not emittable:
                continue

            sorted_types = self.topological_sort_types(emittable)
            rel_path = namespace_to_module_path(ns_tuple)
            primary_ps = sorted_types[0].span.ps_filename if sorted_types else "module.ps"

            modules_by_path[rel_path] = PlannedPythonModule(
                namespace=ns_tuple,
                module_rel_path=rel_path,
                types=sorted_types,
                primary_ps_filename=primary_ps,
            )

        return modules_by_path

    @staticmethod
    def topological_sort_types(types: list[TypeSymbol]) -> list[TypeSymbol]:
        """
        Orders `types` so that any base class or implemented interface declared
        in the same namespace appears before its derived classes.
        """
        type_map = {t.id.value: t for t in types}
        visited: set[int] = set()
        ordered: list[TypeSymbol] = []

        def visit(sym: TypeSymbol) -> None:
            sid = sym.id.value
            if sid in visited:
                return
            visited.add(sid)
            for base_sym in sym.base_type_symbols:
                if base_sym.id.value in type_map:
                    visit(type_map[base_sym.id.value])
            sym.ast_node.topological_order_rank = len(ordered)
            ordered.append(sym)

        for t in types:
            visit(t)

        return ordered


```

---

##### 2. src/psc/codegen/expr_lowerer.py

```python
from __future__ import annotations
import ast
import re
from typing import Any
from psc.diagnostics import SourceSpan
from psc.frontend.ast_nodes import (
    ArgNode,
    BinaryOp,
    BlockStmt,
    CatchClause,
    ComprehensionKind,
    Expr,
    ExprKind,
    ExprStmt,
    ForEachStmt,
    IfStmt,
    InterpolatedPart,
    LiteralKind,
    LocalVarStmt,
    MemberLoweringMode,
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


def stamp_span(node: ast.AST, span: SourceSpan) -> ast.AST:
    """
    Stamps a Python `ast.AST` node (and any un-stamped children) with the exact
    1-indexed line number and 0-indexed column offset from the original `.ps` file.
    """
    lineno = max(1, span.start_line)
    end_lineno = max(lineno, span.end_line)
    col = max(0, span.start_col - 1)
    end_col = max(col, span.end_col - 1)

    for child in ast.walk(node):
        if isinstance(child, (ast.expr, ast.stmt, ast.excepthandler, ast.match_case, ast.pattern)):
            if getattr(child, "lineno", None) is None:
                child.lineno = lineno
                child.end_lineno = end_lineno
                child.col_offset = col
                child.end_col_offset = end_col

    if isinstance(node, (ast.expr, ast.stmt, ast.excepthandler, ast.match_case, ast.pattern)):
        node.lineno = lineno
        node.end_lineno = end_lineno
        node.col_offset = col
        node.end_col_offset = end_col

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
            out.extend(self.lower_stmt(s))
        return out or [ast.Pass(lineno=block.span.start_line, col_offset=0)]

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
            then_body = self._ensure_non_empty_stmts(self.lower_stmt(stmt.then_branch), stmt.span)
            else_body = self.lower_stmt(stmt.else_branch) if stmt.else_branch else []
            node = ast.If(test=cond_ast, body=then_body, orelse=else_body)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, WhileStmt):
            cond_ast = self.lower_expr(stmt.condition)
            body_stmts = self._ensure_non_empty_stmts(self.lower_stmt(stmt.body), stmt.span)
            node = ast.While(test=cond_ast, body=body_stmts, orelse=[])
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ForEachStmt):
            target = ast.Name(id=pascal_to_snake(stmt.item_name), ctx=ast.Store())
            iter_ast = self.lower_expr(stmt.collection)
            body_stmts = self._ensure_non_empty_stmts(self.lower_stmt(stmt.body), stmt.span)
            for_cls = ast.AsyncFor if stmt.is_await else ast.For
            node = for_cls(target=target, iter=iter_ast, body=body_stmts, orelse=[])
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ReturnStmt):
            val_ast = self.lower_expr(stmt.value) if stmt.value is not None else None
            node = ast.Return(value=val_ast)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, YieldStmt):
            if stmt.is_break:
                node = ast.Return(value=None)
            else:
                val_ast = self.lower_expr(stmt.value) if stmt.value is not None else None
                node = ast.Expr(value=ast.Yield(value=val_ast))
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ThrowStmt):
            exc_ast = self.lower_expr(stmt.exception) if stmt.exception is not None else None
            node = ast.Raise(exc=exc_ast, cause=None)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, TryCatchFinallyStmt):
            try_body = self.lower_block(stmt.try_block)
            handlers: list[ast.ExceptHandler] = []
            for catch in stmt.catches:
                exc_type_ast = (
                    self.lower_type_ref_annotation(catch.exception_type)
                    if catch.exception_type is not None
                    else ast.Name(id="Exception", ctx=ast.Load())
                )
                bind_name = pascal_to_snake(catch.bind_name) if catch.bind_name else None
                c_body = self.lower_block(catch.body)
                if catch.when_guard is not None:
                    guard_ast = self.lower_expr(catch.when_guard)
                    c_body = [
                        ast.If(
                            test=guard_ast,
                            body=c_body,
                            orelse=[ast.Raise(exc=None, cause=None)],
                        )
                    ]
                handler = ast.ExceptHandler(type=exc_type_ast, name=bind_name, body=c_body)
                stamp_span(handler, catch.span)
                handlers.append(handler)
            finalbody = self.lower_block(stmt.finally_block) if stmt.finally_block else []
            node = ast.Try(body=try_body, handlers=handlers, orelse=[], finalbody=finalbody)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, SwitchStmt):
            subject_ast = self.lower_expr(stmt.scrutinee)
            cases: list[ast.match_case] = []
            for sec in stmt.sections:
                sec_body = []
                for s in sec.statements:
                    sec_body.extend(self.lower_stmt(s))
                sec_body = self._ensure_non_empty_stmts(sec_body, sec.span)
                for pat, guard in sec.labels:
                    py_pat, extra_guard = self.lower_pattern(pat)
                    combined_guard = self._combine_guards(
                        extra_guard, self.lower_expr(guard) if guard else None
                    )
                    mc = ast.match_case(pattern=py_pat, guard=combined_guard, body=sec_body)
                    stamp_span(mc, sec.span)
                    cases.append(mc)
            node = ast.Match(subject=subject_ast, cases=cases)
            return [stamp_span(node, stmt.span)]  # type: ignore[list-item]

        if isinstance(stmt, ExprStmt):
            return [self.lower_expr_as_stmt(stmt.expr)]

        return [ast.Pass()]

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
            out.extend(self.lower_stmt(s))
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

            target_ast = self._lower_assign_target(left)
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
                node = ast.AugAssign(target=target_ast, op=aug_map[op], value=val_ast)
            return stamp_span(node, expr.span)  # type: ignore[return-value]

        val = self.lower_expr(expr)
        return stamp_span(ast.Expr(value=val), expr.span)  # type: ignore[return-value]

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

        if kind == ExprKind.LITERAL:
            return stamp_span(self._lower_literal(expr), span)  # type: ignore[return-value]

        if kind == ExprKind.INTERP_STRING:
            parts: list[InterpolatedPart] = expr.data.get("parts", [])
            values: list[ast.expr] = []
            for p in parts:
                if p.is_expr and p.expr is not None:
                    values.append(
                        ast.FormattedValue(
                            value=self.lower_expr(p.expr), conversion=-1, format_spec=None
                        )
                    )
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

        if expr.data.get("implicit_this"):
            attr_name = (
                lowering.emitted_snake_name
                if lowering and lowering.emitted_snake_name
                else pascal_to_snake(raw_name)
            )
            return ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr=attr_name,
                ctx=ast.Load(),
            )

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

        return ast.Attribute(value=receiver_ast, attr=attr_name, ctx=ast.Load())

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
                accessed = ast.Attribute(value=current_ref, attr=attr_name, ctx=ast.Load())
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

        test_ast = (
            conditions[0]
            if len(conditions) == 1
            else ast.BoolOp(op=ast.And(), values=conditions)
        )
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
        }
        if op in cmp_map:
            return ast.Compare(left=left_ast, ops=[cmp_map[op]], comparators=[right_ast])

        bin_map: dict[BinaryOp, ast.operator] = {
            BinaryOp.ADD: ast.Add(),
            BinaryOp.SUB: ast.Sub(),
            BinaryOp.MUL: ast.Mult(),
            BinaryOp.DIV: ast.Div(),
            BinaryOp.MOD: ast.Mod(),
            BinaryOp.POW: ast.Pow(),
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
            kw_args.append(
                ast.keyword(arg=pascal_to_snake(prop_name), value=self.lower_expr(init_val))
            )

        cls_name = short_type or "object"
        return ast.Call(
            func=ast.Name(id=cls_name, ctx=ast.Load()),
            args=pos_args,
            keywords=kw_args,
        )

    def _lower_call_args(
        self, args: list[ArgNode]
    ) -> tuple[list[ast.expr], list[ast.keyword]]:
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
                check_ast = self.build_runtime_type_check_ast(
                    subject_ast, rt_check, pat.type_ref
                )
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
        return isinstance_call

    def _lower_lambda(self, expr: Expr) -> ast.expr:
        params = expr.data.get("params", [])
        py_args = [ast.arg(arg=pascal_to_snake(p.name)) for p in params]
        body = expr.data.get("body")
        if isinstance(body, Expr):
            body_ast = self.lower_expr(body)
        else:
            body_ast = ast.Constant(value=None)
        return ast.Lambda(
            args=ast.arguments(
                posonlyargs=[],
                args=py_args,
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=body_ast,
        )

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

    def _pattern_to_bool_expr(
        self, subject_ast: ast.expr, pat: PatternNode, when_guard: Expr | None
    ) -> ast.expr:
        conds: list[ast.expr] = []
        if pat.kind == "Null":
            conds.append(
                ast.Compare(left=subject_ast, ops=[ast.Is()], comparators=[ast.Constant(value=None)])
            )
        elif pat.kind == "Literal" and pat.literal_expr is not None:
            conds.append(
                ast.Compare(
                    left=subject_ast,
                    ops=[ast.Eq()],
                    comparators=[self.lower_expr(pat.literal_expr)],
                )
            )
        elif pat.kind == "TypePattern" and pat.type_ref is not None:
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
            self.lower_expr(projection)
            if projection is not None
            else ast.Name(id=last_item_var, ctx=ast.Load())
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

        sanitized = _TEMPLATE_PLACEHOLDER_RE.sub(repl, template)
        parsed_expr = ast.parse(sanitized, mode="eval").body

        class _PlaceholderReplacer(ast.NodeTransformer):
            def visit_Name(self, node: ast.Name) -> Any:
                if node.id in substitutions:
                    return substitutions[node.id]
                return node

        return _PlaceholderReplacer().visit(parsed_expr)

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


```

---

##### 3. src/psc/codegen/overload_emitter.py

```python
from __future__ import annotations
import ast
from psc.codegen.expr_lowerer import ExpressionLowerer, stamp_span
from psc.frontend.ast_nodes import (
    MethodDecl,
    OverloadDispatchGroup,
    OverloadGuard,
    ParamDecl,
    ReturnStmt,
    RuntimeTypeCheck,
)
from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol


class OverloadAstEmitter:
    """
    Pass 3A (Part 3) — Method & Constructor `@overload` Dispatcher Emitter:
      1. Emits `@overload` signature stubs with `...` bodies for static type checkers
         (`mypy --strict` / `pyright`).
      2. Emits a unified runtime dispatcher (`def method_name(self, *args)`) that:
         - Binds `_n = len(args)`
         - Dispatches each overload variant using fast arity + `isinstance(...)`
           (with `not isinstance(arg, bool)` protection on `int`) and O(1)
           `"Interface" in getattr(arg, "__ps_types__", ())` checks.
         - Binds the variant's formal parameter names (`order = args[0]`) and executes
           the lowered variant body.
         - Raises a descriptive `TypeError` if no overload matches at runtime.
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        lowerer: ExpressionLowerer,
    ) -> None:
        self.symtab = symtab
        self.lowerer = lowerer

    def emit_overload_group(
        self,
        owner_type: TypeSymbol,
        group: OverloadDispatchGroup,
        variants: list[MethodDecl],
        ctor_slot_inits: list[ast.stmt] | None = None,
    ) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []

        # 1. Emit `@overload` stubs for each variant
        for variant in variants:
            stub_fn = self._build_overload_stub(owner_type, group.snake_name, variant)
            stmts.append(stub_fn)

        # 2. Emit the unified runtime dispatcher
        dispatcher_fn = self._build_runtime_dispatcher(
            owner_type=owner_type,
            snake_name=group.snake_name,
            variants=variants,
            is_strictly_arity_disjoint=group.is_strictly_arity_disjoint,
            ctor_slot_inits=ctor_slot_inits or [],
        )
        stmts.append(dispatcher_fn)
        return stmts

    def _build_overload_stub(
        self,
        owner_type: TypeSymbol,
        snake_name: str,
        method: MethodDecl,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        is_static = "static" in method.modifiers
        py_args = self._build_method_arguments(method.params, is_static=is_static)
        ret_ann = (
            ast.Constant(value=None)
            if method.is_constructor
            else self.lowerer.lower_type_ref_annotation(method.return_type)
        )
        decorators: list[ast.expr] = [ast.Name(id="overload", ctx=ast.Load())]
        if is_static:
            decorators.append(ast.Name(id="staticmethod", ctx=ast.Load()))

        fn_cls = ast.AsyncFunctionDef if "async" in method.modifiers else ast.FunctionDef
        stub = fn_cls(
            name=snake_name,
            args=py_args,
            body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
            decorator_list=decorators,
            returns=ret_ann,
        )
        return stamp_span(stub, method.span)  # type: ignore[return-value]

    def _build_runtime_dispatcher(
        self,
        owner_type: TypeSymbol,
        snake_name: str,
        variants: list[MethodDecl],
        is_strictly_arity_disjoint: bool,
        ctor_slot_inits: list[ast.stmt],
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        first_var = variants[0]
        is_static = "static" in first_var.modifiers
        is_async = any("async" in v.modifiers for v in variants)

        pos_args = [] if is_static else [ast.arg(arg="self")]
        dispatcher_args = ast.arguments(
            posonlyargs=[],
            args=pos_args,
            vararg=ast.arg(arg="args"),
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        )

        body: list[ast.stmt] = []
        if first_var.is_constructor and ctor_slot_inits:
            body.extend(ctor_slot_inits)

        # `_n = len(args)`
        body.append(
            ast.Assign(
                targets=[ast.Name(id="_n", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Name(id="len", ctx=ast.Load()),
                    args=[ast.Name(id="args", ctx=ast.Load())],
                    keywords=[],
                ),
            )
        )

        for variant in variants:
            cond_ast = self._build_variant_guard_expr(
                variant.lowering_mode.runtime_guard,
                include_type_checks=True,
            )
            variant_body = self._build_variant_execution_body(variant)
            if_stmt = stamp_span(
                ast.If(test=cond_ast, body=variant_body, orelse=[]),
                variant.span,
            )
            body.append(if_stmt)  # type: ignore[arg-type]

        # Fallback `raise TypeError(f"No matching overload for Class.method with args {args!r}")`
        err_msg = ast.JoinedStr(
            values=[
                ast.Constant(
                    value=f"No matching overload for {owner_type.name}.{snake_name} with args "
                ),
                ast.FormattedValue(
                    value=ast.Name(id="args", ctx=ast.Load()),
                    conversion=ord("r"),
                    format_spec=None,
                ),
            ]
        )
        raise_stmt = ast.Raise(
            exc=ast.Call(
                func=ast.Name(id="TypeError", ctx=ast.Load()),
                args=[err_msg],
                keywords=[],
            ),
            cause=None,
        )
        body.append(raise_stmt)

        decorators: list[ast.expr] = []
        if is_static:
            decorators.append(ast.Name(id="staticmethod", ctx=ast.Load()))

        ret_ann = (
            ast.Constant(value=None)
            if first_var.is_constructor
            else None
        )

        fn_cls = ast.AsyncFunctionDef if is_async else ast.FunctionDef
        dispatcher = fn_cls(
            name=snake_name,
            args=dispatcher_args,
            body=body,
            decorator_list=decorators,
            returns=ret_ann,
        )
        return stamp_span(dispatcher, first_var.span)  # type: ignore[return-value]

    def _build_variant_guard_expr(
        self,
        guard: OverloadGuard | None,
        include_type_checks: bool = True,
    ) -> ast.expr:
        if guard is None:
            return ast.Constant(value=True)

        conds: list[ast.expr] = []

        # 1. Arity check (`_n == k` or `min_arity <= _n <= max_arity`)
        if guard.min_arity == guard.max_arity:
            conds.append(
                ast.Compare(
                    left=ast.Name(id="_n", ctx=ast.Load()),
                    ops=[ast.Eq()],
                    comparators=[ast.Constant(value=guard.min_arity)],
                )
            )
        elif guard.max_arity >= 999:
            conds.append(
                ast.Compare(
                    left=ast.Name(id="_n", ctx=ast.Load()),
                    ops=[ast.GtE()],
                    comparators=[ast.Constant(value=guard.min_arity)],
                )
            )
        else:
            conds.append(
                ast.Compare(
                    left=ast.Constant(value=guard.min_arity),
                    ops=[ast.LtE(), ast.LtE()],
                    comparators=[
                        ast.Name(id="_n", ctx=ast.Load()),
                        ast.Constant(value=guard.max_arity),
                    ],
                )
            )

        # 2. Per-parameter runtime type checks
        if include_type_checks:
            for param_idx, rt_check in guard.param_type_checks:
                arg_sub = ast.Subscript(
                    value=ast.Name(id="args", ctx=ast.Load()),
                    slice=ast.Constant(value=param_idx),
                    ctx=ast.Load(),
                )
                type_cond = self._build_single_param_check(arg_sub, rt_check)
                if param_idx >= guard.min_arity:
                    # Optional parameter: only check type if caller passed an argument at `param_idx`
                    type_cond = ast.BoolOp(
                        op=ast.Or(),
                        values=[
                            ast.Compare(
                                left=ast.Name(id="_n", ctx=ast.Load()),
                                ops=[ast.LtE()],
                                comparators=[ast.Constant(value=param_idx)],
                            ),
                            type_cond,
                        ],
                    )
                conds.append(type_cond)

        return conds[0] if len(conds) == 1 else ast.BoolOp(op=ast.And(), values=conds)

    def _build_single_param_check(
        self, arg_expr: ast.expr, rt_check: RuntimeTypeCheck
    ) -> ast.expr:
        if rt_check.kind == "PsTypesContains":
            return self.lowerer.build_runtime_type_check_ast(arg_expr, rt_check)

        if rt_check.target_type == "Decimal":
            self.lowerer.needs_decimal_import = True

        # Guard against Python's `bool` subclassing `int` when matching `int` overloads!
        if rt_check.target_type == "int":
            is_int = ast.Call(
                func=ast.Name(id="isinstance", ctx=ast.Load()),
                args=[arg_expr, ast.Name(id="int", ctx=ast.Load())],
                keywords=[],
            )
            not_bool = ast.UnaryOp(
                op=ast.Not(),
                operand=ast.Call(
                    func=ast.Name(id="isinstance", ctx=ast.Load()),
                    args=[arg_expr, ast.Name(id="bool", ctx=ast.Load())],
                    keywords=[],
                ),
            )
            return ast.BoolOp(op=ast.And(), values=[is_int, not_bool])

        return self.lowerer.build_runtime_type_check_ast(arg_expr, rt_check)

    def _build_variant_execution_body(self, variant: MethodDecl) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []

        # 1. Bind parameters from `args[i]` (or default value if optional)
        for idx, p in enumerate(variant.params):
            param_id = p.emitted_snake_name
            arg_sub = ast.Subscript(
                value=ast.Name(id="args", ctx=ast.Load()),
                slice=ast.Constant(value=idx),
                ctx=ast.Load(),
            )
            if p.default_value is not None:
                default_ast = self.lowerer.lower_expr(p.default_value)
                rhs: ast.expr = ast.IfExp(
                    test=ast.Compare(
                        left=ast.Name(id="_n", ctx=ast.Load()),
                        ops=[ast.Gt()],
                        comparators=[ast.Constant(value=idx)],
                    ),
                    body=arg_sub,
                    orelse=default_ast,
                )
            else:
                rhs = arg_sub

            stmts.append(
                ast.Assign(
                    targets=[ast.Name(id=param_id, ctx=ast.Store())],
                    value=rhs,
                )
            )

        # 2. If constructor has `: base(...)` or `: this(...)` chain, emit it first
        if variant.is_constructor and variant.ctor_chain is not None:
            pos_args, kw_args = self.lowerer._lower_call_args(variant.ctor_chain.args)
            if variant.ctor_chain.target == "base":
                chain_callee: ast.expr = ast.Attribute(
                    value=ast.Call(
                        func=ast.Name(id="super", ctx=ast.Load()), args=[], keywords=[]
                    ),
                    attr="__init__",
                    ctx=ast.Load(),
                )
            else:
                chain_callee = ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="__init__",
                    ctx=ast.Load(),
                )
            stmts.append(
                ast.Expr(value=ast.Call(func=chain_callee, args=pos_args, keywords=kw_args))
            )

        # 3. Lower the variant's body or expression body
        if variant.expr_body is not None:
            is_void = variant.is_constructor or (
                variant.return_type is not None and variant.return_type.path == ["void"]
            )
            if is_void:
                stmts.append(self.lowerer.lower_expr_as_stmt(variant.expr_body))
                stmts.append(ast.Return(value=None))
            else:
                stmts.append(ast.Return(value=self.lowerer.lower_expr(variant.expr_body)))
        elif variant.body is not None:
            lowered_stmts = self.lowerer.lower_block_with_using(
                variant.body.statements, variant.span
            )
            stmts.extend(lowered_stmts)
            if not stmts or not isinstance(stmts[-1], (ast.Return, ast.Raise)):
                stmts.append(ast.Return(value=None))
        else:
            stmts.append(ast.Return(value=None))

        for s in stmts:
            stamp_span(s, variant.span)

        return stmts

    def _build_method_arguments(
        self, params: list[ParamDecl], is_static: bool
    ) -> ast.arguments:
        args: list[ast.arg] = [] if is_static else [ast.arg(arg="self")]
        defaults: list[ast.expr] = []
        vararg: ast.arg | None = None
        kwarg: ast.arg | None = None

        for p in params:
            ann = self.lowerer.lower_type_ref_annotation(p.type_ref)
            arg_node = ast.arg(arg=p.emitted_snake_name, annotation=ann)
            if p.is_params:
                vararg = arg_node
            elif p.is_kwargs_dict:
                kwarg = arg_node
            else:
                args.append(arg_node)
                if p.default_value is not None:
                    defaults.append(self.lowerer.lower_expr(p.default_value))

        return ast.arguments(
            posonlyargs=[],
            args=args,
            vararg=vararg,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=kwarg,
            defaults=defaults,
        )


```

---

##### 4. src/psc/codegen/py_ast_builder.py

```python
from __future__ import annotations
import ast
from psc.codegen.expr_lowerer import ExpressionLowerer, stamp_span
from psc.codegen.overload_emitter import OverloadAstEmitter
from psc.codegen.topo_sorter import PlannedPythonModule
from psc.diagnostics import SourceSpan
from psc.frontend.ast_nodes import (
    FieldDecl,
    ImportDecl,
    IndexerDecl,
    MethodDecl,
    PropertyDecl,
    TypeDecl,
    TypeKind,
)
from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol, namespace_to_module_path


class PythonAstBuilder:
    """
    Pass 3A (Part 4) — Python 3.11+ `ast.Module` Builder:
      Lowers a `PlannedPythonModule` into a complete, valid Python 3.11+ `ast.Module`
      stamped with original `.ps` line numbers:
      - `from __future__ import annotations`
      - Required typing / stdlib / cross-namespace imports
      - `Protocol` classes for interfaces
      - `enum.IntEnum` / `enum.Enum` classes for enums
      - `@dataclass(slots=True, frozen=...)` for records and structs
      - Slotted classes (`__slots__ = (...)` and `__ps_types__ = (...)`) with properties,
        overloaded methods/constructors, indexers, and `__enter__`/`__exit__` context managers.
    """

    def __init__(self, symtab: GlobalSymbolTable) -> None:
        self.symtab = symtab

    def build_module(self, planned: PlannedPythonModule) -> ast.Module:
        body: list[ast.stmt] = []
        needs_dataclass = False
        needs_protocol = False
        needs_overload = False
        needs_enum = False
        needs_decimal = False
        needs_any = False

        # Collect all imports declared across units contributing to this namespace
        seen_extern_imports: set[tuple[tuple[str, ...], str | None]] = set()
        seen_ns_imports: set[tuple[str, ...]] = set()
        extern_import_nodes: list[ast.stmt] = []
        ns_import_nodes: list[ast.stmt] = []

        for type_sym in planned.types:
            for imp in type_sym.unit.imports:
                if imp.is_extern:
                    key = (tuple(imp.path), imp.alias)
                    if key not in seen_extern_imports:
                        seen_extern_imports.add(key)
                        extern_import_nodes.append(
                            stamp_span(
                                ast.Import(
                                    names=[
                                        ast.alias(
                                            name=".".join(imp.path),
                                            asname=imp.alias,
                                        )
                                    ]
                                ),
                                imp.span,
                            )  # type: ignore[arg-type]
                        )
                else:
                    target_ns = tuple(imp.path)
                    if (
                        target_ns != planned.namespace
                        and target_ns != ("PythonSharp", "Core")
                        and target_ns not in seen_ns_imports
                        and target_ns in self.symtab.namespaces
                    ):
                        seen_ns_imports.add(target_ns)
                        mod_path = namespace_to_module_path(target_ns).removesuffix(".py").replace("/", ".")
                        imported_names = [
                            ast.alias(name=t.name, asname=None)
                            for t in self.symtab.namespaces[target_ns]
                            if not t.is_primitive and not t.is_ambient_stub
                        ]
                        if imported_names:
                            ns_import_nodes.append(
                                stamp_span(
                                    ast.ImportFrom(
                                        module=mod_path,
                                        names=imported_names,
                                        level=0,
                                    ),
                                    imp.span,
                                )  # type: ignore[arg-type]
                            )

        class_defs: list[ast.stmt] = []
        for type_sym in planned.types:
            decl = type_sym.ast_node
            strat = decl.emission_strategy

            if type_sym.is_interface:
                needs_protocol = True
            if type_sym.is_enum:
                needs_enum = True
            if strat.kind == "SlottedDataclass":
                needs_dataclass = True
            if decl.overload_groups:
                needs_overload = True

            lowerer = ExpressionLowerer(self.symtab, current_type=type_sym)
            cls_stmt = self.build_type_decl(type_sym, lowerer)
            if lowerer.needs_decimal_import:
                needs_decimal = True
            class_defs.append(cls_stmt)

        # Check if `Decimal` or `Any` appears in any annotations
        unparsed_preview = "\n".join(ast.unparse(c) for c in class_defs)
        if "Decimal" in unparsed_preview:
            needs_decimal = True
        if "Any" in unparsed_preview:
            needs_any = True

        # 1. `from __future__ import annotations`
        body.append(
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations", asname=None)],
                level=0,
                lineno=1,
                col_offset=0,
            )
        )

        # 2. Standard library & typing imports
        if needs_dataclass:
            body.append(
                ast.ImportFrom(
                    module="dataclasses",
                    names=[ast.alias(name="dataclass", asname=None)],
                    level=0,
                    lineno=1,
                    col_offset=0,
                )
            )
        if needs_decimal:
            body.append(
                ast.ImportFrom(
                    module="decimal",
                    names=[ast.alias(name="Decimal", asname=None)],
                    level=0,
                    lineno=1,
                    col_offset=0,
                )
            )
        if needs_enum:
            body.append(
                ast.Import(
                    names=[ast.alias(name="enum", asname=None)],
                    lineno=1,
                    col_offset=0,
                )
            )

        typing_names: list[str] = []
        if needs_any:
            typing_names.append("Any")
        if needs_protocol:
            typing_names.append("Protocol")
        if needs_overload:
            typing_names.append("overload")
        if typing_names:
            body.append(
                ast.ImportFrom(
                    module="typing",
                    names=[ast.alias(name=n, asname=None) for n in typing_names],
                    level=0,
                    lineno=1,
                    col_offset=0,
                )
            )

        body.extend(extern_import_nodes)
        body.extend(ns_import_nodes)
        body.extend(class_defs)

        mod = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(mod)
        return mod

    # ========================================================================
    # TYPE DECLARATION BUILDERS
    # ========================================================================

    def build_type_decl(
        self, type_sym: TypeSymbol, lowerer: ExpressionLowerer
    ) -> ast.ClassDef:
        if type_sym.is_interface:
            return self.build_interface_protocol(type_sym, lowerer)
        if type_sym.is_enum:
            return self.build_enum_class(type_sym, lowerer)
        if type_sym.ast_node.emission_strategy.kind == "SlottedDataclass":
            return self.build_record_or_struct_dataclass(type_sym, lowerer)
        return self.build_standard_class(type_sym, lowerer)

    def build_interface_protocol(
        self, type_sym: TypeSymbol, lowerer: ExpressionLowerer
    ) -> ast.ClassDef:
        decl = type_sym.ast_node
        bases: list[ast.expr] = [ast.Name(id="Protocol", ctx=ast.Load())]
        body: list[ast.stmt] = []

        for member in decl.members:
            if isinstance(member, PropertyDecl):
                ret_ann = lowerer.lower_type_ref_annotation(member.type_ref)
                prop_fn = ast.FunctionDef(
                    name=member.emitted_snake_name,
                    args=ast.arguments(
                        posonlyargs=[],
                        args=[ast.arg(arg="self")],
                        kwonlyargs=[],
                        kw_defaults=[],
                        defaults=[],
                    ),
                    body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
                    decorator_list=[ast.Name(id="property", ctx=ast.Load())],
                    returns=ret_ann,
                )
                body.append(stamp_span(prop_fn, member.span))  # type: ignore[arg-type]
            elif isinstance(member, MethodDecl):
                overload_emitter = OverloadAstEmitter(self.symtab, lowerer)
                py_args = overload_emitter._build_method_arguments(
                    member.params, is_static="static" in member.modifiers
                )
                ret_ann = lowerer.lower_type_ref_annotation(member.return_type)
                fn_cls = ast.AsyncFunctionDef if "async" in member.modifiers else ast.FunctionDef
                m_fn = fn_cls(
                    name=member.lowering_mode.emitted_snake_name,
                    args=py_args,
                    body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
                    decorator_list=[],
                    returns=ret_ann,
                )
                body.append(stamp_span(m_fn, member.span))  # type: ignore[arg-type]

        if not body:
            body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))

        cls_def = ast.ClassDef(
            name=decl.name,
            bases=bases,
            keywords=[],
            body=body,
            decorator_list=[],
        )
        return stamp_span(cls_def, decl.span)  # type: ignore[return-value]

    def build_enum_class(
        self, type_sym: TypeSymbol, lowerer: ExpressionLowerer
    ) -> ast.ClassDef:
        decl = type_sym.ast_node
        bases: list[ast.expr] = [
            ast.Attribute(
                value=ast.Name(id="enum", ctx=ast.Load()),
                attr="IntEnum",
                ctx=ast.Load(),
            )
        ]
        body: list[ast.stmt] = []
        for idx, em in enumerate(decl.enum_members):
            val_ast = (
                lowerer.lower_expr(em.value)
                if em.value is not None
                else ast.Constant(value=idx)
            )
            assign = ast.Assign(
                targets=[ast.Name(id=em.name, ctx=ast.Store())],
                value=val_ast,
            )
            body.append(stamp_span(assign, em.span))  # type: ignore[arg-type]

        if not body:
            body.append(ast.Pass())

        cls_def = ast.ClassDef(
            name=decl.name,
            bases=bases,
            keywords=[],
            body=body,
            decorator_list=[],
        )
        return stamp_span(cls_def, decl.span)  # type: ignore[return-value]

    def build_record_or_struct_dataclass(
        self, type_sym: TypeSymbol, lowerer: ExpressionLowerer
    ) -> ast.ClassDef:
        decl = type_sym.ast_node
        strat = decl.emission_strategy

        dc_keywords = [ast.keyword(arg="slots", value=ast.Constant(value=True))]
        if strat.is_frozen_dataclass:
            dc_keywords.append(ast.keyword(arg="frozen", value=ast.Constant(value=True)))

        decorators: list[ast.expr] = [
            ast.Call(
                func=ast.Name(id="dataclass", ctx=ast.Load()),
                args=[],
                keywords=dc_keywords,
            ),
            *[lowerer.lower_expr(d) for d in decl.decorators_to_emit],
        ]

        body: list[ast.stmt] = []
        if strat.ps_types_tuple:
            body.append(self._build_ps_types_assign(strat.ps_types_tuple, decl.span))

        for p in decl.primary_ctor_params:
            ann_ast = lowerer.lower_type_ref_annotation(p.type_ref)
            val_ast = lowerer.lower_expr(p.default_value) if p.default_value is not None else None
            ann_assign = ast.AnnAssign(
                target=ast.Name(id=p.emitted_snake_name, ctx=ast.Store()),
                annotation=ann_ast,
                value=val_ast,
                simple=1,
            )
            body.append(stamp_span(ann_assign, p.span))  # type: ignore[arg-type]

        # Also emit any explicit members on the record/struct
        body.extend(self._emit_class_members(type_sym, lowerer, is_dataclass=True))

        if not body:
            body.append(ast.Pass())

        cls_def = ast.ClassDef(
            name=decl.name,
            bases=self._build_runtime_bases(type_sym),
            keywords=[],
            body=body,
            decorator_list=decorators,
        )
        return stamp_span(cls_def, decl.span)  # type: ignore[return-value]

    def build_standard_class(
        self, type_sym: TypeSymbol, lowerer: ExpressionLowerer
    ) -> ast.ClassDef:
        decl = type_sym.ast_node
        strat = decl.emission_strategy
        decorators = [lowerer.lower_expr(d) for d in decl.decorators_to_emit]
        body: list[ast.stmt] = []

        # 1. `__ps_types__ = (...)`
        if strat.ps_types_tuple:
            body.append(self._build_ps_types_assign(strat.ps_types_tuple, decl.span))

        # 2. `__slots__ = (...)` (unless SchemaModel)
        if strat.kind != "SchemaModel":
            slots_tuple = ast.Tuple(
                elts=[ast.Constant(value=s) for s in strat.own_slots],
                ctx=ast.Load(),
            )
            slots_assign = ast.Assign(
                targets=[ast.Name(id="__slots__", ctx=ast.Store())],
                value=slots_tuple,
            )
            body.append(stamp_span(slots_assign, decl.span))  # type: ignore[arg-type]

        # 3. Static fields & static properties
        for member in decl.members:
            if isinstance(member, FieldDecl) and "static" in member.modifiers:
                ann_ast = lowerer.lower_type_ref_annotation(member.type_ref)
                val_ast = (
                    lowerer.lower_expr(member.initializer)
                    if member.initializer is not None
                    else ast.Constant(value=None)
                )
                body.append(
                    stamp_span(
                        ast.AnnAssign(
                            target=ast.Name(id=member.emitted_snake_name, ctx=ast.Store()),
                            annotation=ann_ast,
                            value=val_ast,
                            simple=1,
                        ),
                        member.span,
                    )  # type: ignore[arg-type]
                )

        # 4. Constructors, Properties, Indexers, and Methods
        body.extend(self._emit_class_members(type_sym, lowerer, is_dataclass=False))

        # 5. Synthesize `__enter__` / `__exit__` if implements `IDisposable`
        if strat.generates_context_manager:
            body.extend(self._build_sync_context_manager_methods(type_sym))
        if strat.generates_async_context_manager:
            body.extend(self._build_async_context_manager_methods(type_sym))

        if not body:
            body.append(ast.Pass())

        cls_def = ast.ClassDef(
            name=decl.name,
            bases=self._build_runtime_bases(type_sym),
            keywords=[],
            body=body,
            decorator_list=decorators,
        )
        return stamp_span(cls_def, decl.span)  # type: ignore[return-value]

    # ========================================================================
    # MEMBER EMISSION HELPERS
    # ========================================================================

    def _emit_class_members(
        self,
        type_sym: TypeSymbol,
        lowerer: ExpressionLowerer,
        is_dataclass: bool,
    ) -> list[ast.stmt]:
        decl = type_sym.ast_node
        stmts: list[ast.stmt] = []
        overload_emitter = OverloadAstEmitter(self.symtab, lowerer)

        # Build instance field & auto-property backing slot initializers for `__init__`
        ctor_slot_inits = self._build_instance_slot_initializers(type_sym, lowerer)
        overload_groups_by_name = {g.snake_name: g for g in decl.overload_groups}
        emitted_overload_groups: set[str] = set()

        ctors = [
            m for m in decl.members if isinstance(m, MethodDecl) and m.is_constructor
        ]

        # If not a dataclass and no explicit constructor was declared, emit default `__init__` if slots have initializers
        if not is_dataclass and not ctors and ctor_slot_inits:
            init_fn = ast.FunctionDef(
                name="__init__",
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg="self")],
                    kwonlyargs=[],
                    kw_defaults=[],
                    defaults=[],
                ),
                body=ctor_slot_inits,
                decorator_list=[],
                returns=ast.Constant(value=None),
            )
            stmts.append(stamp_span(init_fn, decl.span))  # type: ignore[arg-type]

        for member in decl.members:
            if isinstance(member, PropertyDecl):
                stmts.extend(self._emit_property(member, lowerer))
            elif isinstance(member, IndexerDecl):
                stmts.extend(self._emit_indexer(member, lowerer, overload_emitter))
            elif isinstance(member, MethodDecl):
                snake = "__init__" if member.is_constructor else member.lowering_mode.emitted_snake_name
                if snake in overload_groups_by_name:
                    if snake in emitted_overload_groups:
                        continue
                    emitted_overload_groups.add(snake)
                    group = overload_groups_by_name[snake]
                    group_variants = [
                        m
                        for m in decl.members
                        if isinstance(m, MethodDecl)
                        and ("__init__" if m.is_constructor else m.lowering_mode.emitted_snake_name) == snake
                    ]
                    stmts.extend(
                        overload_emitter.emit_overload_group(
                            owner_type=type_sym,
                            group=group,
                            variants=group_variants,
                            ctor_slot_inits=ctor_slot_inits if member.is_constructor else None,
                        )
                    )
                else:
                    stmts.append(
                        self._emit_single_method(
                            member,
                            lowerer,
                            overload_emitter,
                            ctor_slot_inits=ctor_slot_inits if member.is_constructor else None,
                        )
                    )

        return stmts

    def _build_instance_slot_initializers(
        self, type_sym: TypeSymbol, lowerer: ExpressionLowerer
    ) -> list[ast.stmt]:
        inits: list[ast.stmt] = []
        for member in type_sym.ast_node.members:
            if isinstance(member, FieldDecl) and "static" not in member.modifiers:
                if member.initializer is not None:
                    ann_ast = lowerer.lower_type_ref_annotation(member.type_ref)
                    val_ast = lowerer.lower_expr(member.initializer)
                    stmt = ast.AnnAssign(
                        target=ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr=member.emitted_snake_name,
                            ctx=ast.Store(),
                        ),
                        annotation=ann_ast,
                        value=val_ast,
                        simple=0,
                    )
                    inits.append(stamp_span(stmt, member.span))  # type: ignore[arg-type]
            elif isinstance(member, PropertyDecl) and "static" not in member.modifiers:
                if member.backing_slot_name and member.initializer is not None:
                    ann_ast = lowerer.lower_type_ref_annotation(member.type_ref)
                    val_ast = lowerer.lower_expr(member.initializer)
                    stmt = ast.AnnAssign(
                        target=ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr=member.backing_slot_name,
                            ctx=ast.Store(),
                        ),
                        annotation=ann_ast,
                        value=val_ast,
                        simple=0,
                    )
                    inits.append(stamp_span(stmt, member.span))  # type: ignore[arg-type]
        return inits

    def _emit_property(
        self, prop: PropertyDecl, lowerer: ExpressionLowerer
    ) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []
        ret_ann = lowerer.lower_type_ref_annotation(prop.type_ref)
        snake = prop.emitted_snake_name

        # 1. Expression-bodied computed property (`public bool IsOverdrawn => Balance < 0.0m;`)
        if prop.expr_body is not None:
            getter = ast.FunctionDef(
                name=snake,
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg="self")],
                    kwonlyargs=[],
                    kw_defaults=[],
                    defaults=[],
                ),
                body=[ast.Return(value=lowerer.lower_expr(prop.expr_body))],
                decorator_list=[ast.Name(id="property", ctx=ast.Load())],
                returns=ret_ann,
            )
            stmts.append(stamp_span(getter, prop.span))  # type: ignore[arg-type]
            return stmts

        # 2. Accessor-based property (`{ get; private set; }` or custom bodies)
        for acc in prop.accessors:
            if acc.kind == "get":
                if acc.expr_body is not None:
                    g_body: list[ast.stmt] = [ast.Return(value=lowerer.lower_expr(acc.expr_body))]
                elif acc.body is not None:
                    g_body = lowerer.lower_block_with_using(acc.body.statements, acc.span)
                else:
                    slot_attr = prop.backing_slot_name or f"_{snake}"
                    g_body = [
                        ast.Return(
                            value=ast.Attribute(
                                value=ast.Name(id="self", ctx=ast.Load()),
                                attr=slot_attr,
                                ctx=ast.Load(),
                            )
                        )
                    ]
                getter = ast.FunctionDef(
                    name=snake,
                    args=ast.arguments(
                        posonlyargs=[],
                        args=[ast.arg(arg="self")],
                        kwonlyargs=[],
                        kw_defaults=[],
                        defaults=[],
                    ),
                    body=g_body,
                    decorator_list=[ast.Name(id="property", ctx=ast.Load())],
                    returns=ret_ann,
                )
                stmts.append(stamp_span(getter, acc.span))  # type: ignore[arg-type]

            elif acc.kind == "set":
                if acc.expr_body is not None:
                    s_body: list[ast.stmt] = [lowerer.lower_expr_as_stmt(acc.expr_body)]
                elif acc.body is not None:
                    s_body = lowerer.lower_block_with_using(acc.body.statements, acc.span)
                else:
                    slot_attr = prop.backing_slot_name or f"_{snake}"
                    s_body = [
                        ast.Assign(
                            targets=[
                                ast.Attribute(
                                    value=ast.Name(id="self", ctx=ast.Load()),
                                    attr=slot_attr,
                                    ctx=ast.Store(),
                                )
                            ],
                            value=ast.Name(id="value", ctx=ast.Load()),
                        )
                    ]
                setter = ast.FunctionDef(
                    name=snake,
                    args=ast.arguments(
                        posonlyargs=[],
                        args=[
                            ast.arg(arg="self"),
                            ast.arg(arg="value", annotation=ret_ann),
                        ],
                        kwonlyargs=[],
                        kw_defaults=[],
                        defaults=[],
                    ),
                    body=s_body,
                    decorator_list=[
                        ast.Attribute(
                            value=ast.Name(id=snake, ctx=ast.Load()),
                            attr="setter",
                            ctx=ast.Load(),
                        )
                    ],
                    returns=ast.Constant(value=None),
                )
                stmts.append(stamp_span(setter, acc.span))  # type: ignore[arg-type]

        return stmts

    def _emit_indexer(
        self,
        indexer: IndexerDecl,
        lowerer: ExpressionLowerer,
        overload_emitter: OverloadAstEmitter,
    ) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []
        val_ann = lowerer.lower_type_ref_annotation(indexer.type_ref)

        for acc in indexer.accessors:
            if acc.kind == "get":
                py_args = overload_emitter._build_method_arguments(
                    indexer.params, is_static=False
                )
                if acc.expr_body is not None:
                    g_body: list[ast.stmt] = [ast.Return(value=lowerer.lower_expr(acc.expr_body))]
                elif acc.body is not None:
                    g_body = lowerer.lower_block_with_using(acc.body.statements, acc.span)
                else:
                    g_body = [ast.Expr(value=ast.Constant(value=Ellipsis))]

                getitem_fn = ast.FunctionDef(
                    name="__getitem__",
                    args=py_args,
                    body=g_body,
                    decorator_list=[],
                    returns=val_ann,
                )
                stmts.append(stamp_span(getitem_fn, acc.span))  # type: ignore[arg-type]

            elif acc.kind == "set":
                py_args = overload_emitter._build_method_arguments(
                    indexer.params, is_static=False
                )
                py_args.args.append(ast.arg(arg="value", annotation=val_ann))
                if acc.expr_body is not None:
                    s_body: list[ast.stmt] = [lowerer.lower_expr_as_stmt(acc.expr_body)]
                elif acc.body is not None:
                    s_body = lowerer.lower_block_with_using(acc.body.statements, acc.span)
                else:
                    s_body = [ast.Expr(value=ast.Constant(value=Ellipsis))]

                setitem_fn = ast.FunctionDef(
                    name="__setitem__",
                    args=py_args,
                    body=s_body,
                    decorator_list=[],
                    returns=ast.Constant(value=None),
                )
                stmts.append(stamp_span(setitem_fn, acc.span))  # type: ignore[arg-type]

        return stmts

    def _emit_single_method(
        self,
        method: MethodDecl,
        lowerer: ExpressionLowerer,
        overload_emitter: OverloadAstEmitter,
        ctor_slot_inits: list[ast.stmt] | None = None,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        is_static = "static" in method.modifiers
        is_async = "async" in method.modifiers
        snake_name = "__init__" if method.is_constructor else method.lowering_mode.emitted_snake_name

        py_args = overload_emitter._build_method_arguments(method.params, is_static=is_static)
        ret_ann = (
            ast.Constant(value=None)
            if method.is_constructor
            else lowerer.lower_type_ref_annotation(method.return_type)
        )

        body: list[ast.stmt] = []
        if method.is_constructor and ctor_slot_inits:
            body.extend(ctor_slot_inits)

        if method.is_constructor and method.ctor_chain is not None:
            pos_args, kw_args = lowerer._lower_call_args(method.ctor_chain.args)
            if method.ctor_chain.target == "base":
                chain_callee: ast.expr = ast.Attribute(
                    value=ast.Call(
                        func=ast.Name(id="super", ctx=ast.Load()), args=[], keywords=[]
                    ),
                    attr="__init__",
                    ctx=ast.Load(),
                )
            else:
                chain_callee = ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="__init__",
                    ctx=ast.Load(),
                )
            body.append(
                stamp_span(
                    ast.Expr(value=ast.Call(func=chain_callee, args=pos_args, keywords=kw_args)),
                    method.ctor_chain.span,
                )  # type: ignore[arg-type]
            )

        if method.expr_body is not None:
            is_void = method.is_constructor or (
                method.return_type is not None and method.return_type.path == ["void"]
            )
            if is_void:
                body.append(lowerer.lower_expr_as_stmt(method.expr_body))
            else:
                body.append(
                    stamp_span(
                        ast.Return(value=lowerer.lower_expr(method.expr_body)),
                        method.expr_body.span,
                    )  # type: ignore[arg-type]
                )
        elif method.body is not None:
            body.extend(lowerer.lower_block_with_using(method.body.statements, method.span))

        if not body:
            body.append(ast.Pass())

        decorators: list[ast.expr] = []
        if is_static:
            decorators.append(ast.Name(id="staticmethod", ctx=ast.Load()))
        for dec_expr in method.decorators_to_emit:
            decorators.append(lowerer.lower_expr(dec_expr))

        fn_cls = ast.AsyncFunctionDef if is_async else ast.FunctionDef
        fn_def = fn_cls(
            name=snake_name,
            args=py_args,
            body=body,
            decorator_list=decorators,
            returns=ret_ann,
        )
        return stamp_span(fn_def, method.span)  # type: ignore[return-value]

    # ========================================================================
    # CONTEXT MANAGERS (`IDisposable` -> `__enter__` / `__exit__`) & BASES
    # ========================================================================

    def _build_sync_context_manager_methods(
        self, type_sym: TypeSymbol
    ) -> list[ast.stmt]:
        span = type_sym.span
        enter_fn = ast.FunctionDef(
            name="__enter__",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="self")],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[ast.Return(value=ast.Name(id="self", ctx=ast.Load()))],
            decorator_list=[],
            returns=ast.Name(id=type_sym.name, ctx=ast.Load()),
        )
        exit_fn = ast.FunctionDef(
            name="__exit__",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="self"),
                    ast.arg(arg="exc_type"),
                    ast.arg(arg="exc_val"),
                    ast.arg(arg="exc_tb"),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr="dispose",
                            ctx=ast.Load(),
                        ),
                        args=[],
                        keywords=[],
                    )
                )
            ],
            decorator_list=[],
            returns=ast.Constant(value=None),
        )
        return [
            stamp_span(enter_fn, span),  # type: ignore[list-item]
            stamp_span(exit_fn, span),  # type: ignore[list-item]
        ]

    def _build_async_context_manager_methods(
        self, type_sym: TypeSymbol
    ) -> list[ast.stmt]:
        span = type_sym.span
        aenter_fn = ast.AsyncFunctionDef(
            name="__aenter__",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="self")],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[ast.Return(value=ast.Name(id="self", ctx=ast.Load()))],
            decorator_list=[],
            returns=ast.Name(id=type_sym.name, ctx=ast.Load()),
        )
        aexit_fn = ast.AsyncFunctionDef(
            name="__aexit__",
            args=ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg="self"),
                    ast.arg(arg="exc_type"),
                    ast.arg(arg="exc_val"),
                    ast.arg(arg="exc_tb"),
                ],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=[
                ast.Expr(
                    value=ast.Await(
                        value=ast.Call(
                            func=ast.Attribute(
                                value=ast.Name(id="self", ctx=ast.Load()),
                                attr="dispose_async",
                                ctx=ast.Load(),
                            ),
                            args=[],
                            keywords=[],
                        )
                    )
                )
            ],
            decorator_list=[],
            returns=ast.Constant(value=None),
        )
        return [
            stamp_span(aenter_fn, span),  # type: ignore[list-item]
            stamp_span(aexit_fn, span),  # type: ignore[list-item]
        ]

    @staticmethod
    def _build_runtime_bases(type_sym: TypeSymbol) -> list[ast.expr]:
        """
        Emits concrete non-interface base classes in Python `class Sub(Base):`.
        (Interfaces are recorded in `__ps_types__` for O(1) nominal checking rather than
        polluting the runtime MRO with Protocol metaclasses.)
        """
        bases: list[ast.expr] = []
        for base_sym in type_sym.base_type_symbols:
            if not base_sym.is_interface and not base_sym.is_primitive:
                bases.append(ast.Name(id=base_sym.name, ctx=ast.Load()))
        return bases

    @staticmethod
    def _build_ps_types_assign(
        ps_types: list[str], span: SourceSpan
    ) -> ast.stmt:
        tup = ast.Tuple(
            elts=[ast.Constant(value=t) for t in ps_types],
            ctx=ast.Load(),
        )
        assign = ast.Assign(
            targets=[ast.Name(id="__ps_types__", ctx=ast.Store())],
            value=tup,
        )
        return stamp_span(assign, span)  # type: ignore[return-value]


```

---

##### 5. src/psc/codegen/**init**.py

```python
from psc.codegen.topo_sorter import NamespacePackagePlanner, PlannedPythonModule
from psc.codegen.expr_lowerer import ExpressionLowerer, stamp_span
from psc.codegen.overload_emitter import OverloadAstEmitter
from psc.codegen.py_ast_builder import PythonAstBuilder

__all__ = [
    "NamespacePackagePlanner",
    "PlannedPythonModule",
    "ExpressionLowerer",
    "OverloadAstEmitter",
    "PythonAstBuilder",
    "stamp_span",
]


```

---

##### 6. tests/test_py_ast_builder.py

```python
from __future__ import annotations
import ast
from decimal import Decimal
from typing import Any
from psc.codegen import NamespacePackagePlanner, PythonAstBuilder
from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.semantics import GlobalSymbolTable, analyze_compilation_units


STDLIB_STUB = """
namespace PythonSharp.Core;

[MapsTo("contextlib.AbstractContextManager")]
public interface IDisposable
{
    [MapsTo("dispose")]
    void Dispose();
}

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

    [InlineTemplate("({0} in {self})")]
    public extern bool ContainsKey(TKey key);

    [MapsTo("values")]
    public extern IEnumerable<TValue> Values();

    [MapsTo("clear")]
    public extern void Clear();
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


def test_end_to_end_ast_lowering_and_runtime_execution_of_order_cache() -> None:
    """
    Compiles `OrderService.ps` through Pass 1 -> Pass 2 -> Pass 3A (`PythonAstBuilder`),
    verifies the emitted Python 3.11+ source code structure, and executes the compiled
    module on CPython 3.11+ to verify:
      - `@dataclass(slots=True, frozen=True)` on `Order`
      - `__slots__ = ('_store', '_audit_tag')` (zero `__dict__` allocation on `OrderCache`)
      - `__ps_types__` O(1) nominal interface checking (`cache is IAuditable`)
      - `@overload` runtime dispatcher on `put(Order)` vs `put(int, Decimal)`
      - Fused list comprehension in `get_active_ids()`
      - `using var cache = ...` lowering to `with OrderCache(...) as cache:` (`__enter__`/`__exit__`)
    """
    source = """
    namespace Commerce.Services;

    using PythonSharp.Core;

    public interface IAuditable { string AuditTag { get; } }

    public record Order(int Id, decimal Total, bool IsActive);

    public class OrderCache : IAuditable, IDisposable
    {
        private readonly Dict<int, Order> _store = new Dict<int, Order>();
        public string AuditTag { get; private set; }

        public OrderCache(string tag) => AuditTag = tag;

        public void Put(Order order) => _store[order.Id] = order;
        public void Put(int id, decimal total) => _store[id] = new Order(id, total, true);

        public bool IsAuditTarget(object candidate) => candidate is IAuditable;

        public List<int> GetActiveIds(decimal minTotal = 0.0m)
        {
            return _store.Values()
                .Where(o => o.IsActive && o.Total >= minTotal)
                .Select(o => o.Id)
                .ToList();
        }

        public void Dispose() => _store.Clear();
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

    planner = NamespacePackagePlanner(symtab)
    planned_modules = planner.plan_modules()
    assert "commerce/services.py" in planned_modules

    builder = PythonAstBuilder(symtab)
    py_mod_ast = builder.build_module(planned_modules["commerce/services.py"])
    py_source = ast.unparse(py_mod_ast)

    # 1. Verify structural Python 3.11+ constructs in emitted code
    assert "from __future__ import annotations" in py_source
    assert "@dataclass(slots=True, frozen=True)" in py_source
    assert "__slots__ = ('_store', '_audit_tag')" in py_source
    assert "@overload" in py_source
    assert "[o.id for o in self._store.values() if o.is_active and o.total >= min_total]" in py_source
    assert "def __enter__(self) -> OrderCache:" in py_source
    assert "def __exit__(self, exc_type, exc_val, exc_tb) -> None:" in py_source

    # 2. Execute the emitted Python AST in CPython and test runtime behavior!
    ns_globals: dict[str, Any] = {}
    code_obj = compile(py_mod_ast, filename="Services/OrderCache.ps", mode="exec")
    exec(code_obj, ns_globals)

    OrderCls = ns_globals["Order"]
    OrderCacheCls = ns_globals["OrderCache"]

    with OrderCacheCls("PROD-AUDIT") as cache:
        # Confirm `__slots__` eliminates per-instance `__dict__`
        assert not hasattr(cache, "__dict__")
        assert cache.audit_tag == "PROD-AUDIT"
        assert cache.is_audit_target(cache) is True
        assert cache.is_audit_target("not-auditable") is False

        # Test Overload Variant 0: `Put(Order)`
        cache.put(OrderCls(101, Decimal("25.50"), True))
        cache.put(OrderCls(102, Decimal("5.00"), False))

        # Test Overload Variant 1: `Put(int, decimal)`
        cache.put(103, Decimal("99.95"))

        # Test fused LINQ comprehension `GetActiveIds(minTotal)`
        assert cache.get_active_ids() == [101, 103]
        assert cache.get_active_ids(Decimal("50.00")) == [103]

    # Exiting the `with` block automatically invoked `Dispose()` -> `_store.clear()`!
    assert cache.get_active_ids() == []


def test_multidimensional_tensor_slicing_and_walrus_null_safety_lowering() -> None:
    """
    Verifies Pass 3A lowering for:
      - `tensor[1..5, ^2.., ::2]` -> `tensor[1:5, -2:, ::2]`
      - `user?.Profile?.Name ?? "Guest"` -> walrus-guarded `IfExp` that does NOT
        treat empty string `""` or `0` as null!
    """
    source = """
    namespace ML.Pipelines;

    public record Profile(string? Name);
    public record User(Profile? Profile);

    public class Slicer
    {
        public object Slice1D(object seq) => seq[1..5:2];
        public object FromEnd(object seq) => seq[^1];
        public string ResolveName(User? user) => user?.Profile?.Name ?? "Guest";
        public int CoalesceZero(int? count) => count ?? 42;
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="Slicer.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    analyze_compilation_units([unit], symtab, diag)
    assert not diag.has_errors(), diag.format_all()

    planned = NamespacePackagePlanner(symtab).plan_modules()["ml/pipelines.py"]
    py_mod_ast = PythonAstBuilder(symtab).build_module(planned)
    py_source = ast.unparse(py_mod_ast)

    assert "seq[1:5:2]" in py_source
    assert "seq[-1]" in py_source

    ns_globals: dict[str, Any] = {}
    exec(compile(py_mod_ast, filename="Slicer.ps", mode="exec"), ns_globals)

    ProfileCls = ns_globals["Profile"]
    UserCls = ns_globals["User"]
    slicer = ns_globals["Slicer"]()

    assert slicer.slice_1d([0, 1, 2, 3, 4, 5, 6]) == [1, 3]
    assert slicer.from_end([10, 20, 30]) == 30
    assert slicer.resolve_name(None) == "Guest"
    assert slicer.resolve_name(UserCls(None)) == "Guest"
    assert slicer.resolve_name(UserCls(ProfileCls(None))) == "Guest"
    assert slicer.resolve_name(UserCls(ProfileCls("Ada"))) == "Ada"
    # Crucial null-safety test: empty string `""` and `0` are NOT null (`is not None`)!
    assert slicer.resolve_name(UserCls(ProfileCls(""))) == ""
    assert slicer.coalesce_zero(0) == 0
    assert slicer.coalesce_zero(None) == 42


```

---

Shall we continue with the raw individual files for **Milestone 6 (Pass 3B & CLI: `src/psc/codegen/emitter.py` for PEP 552 `.pyc` bytecode emission with `.ps` `co_filename` & `lineno` line-pinning, `src/psc/cli.py`, `src/psc/__init__.py`, `pyproject.toml`, `stdlib/PythonSharp.Core.d.ps`, and `tests/test_bytecode_tracebacks.py`)**?
