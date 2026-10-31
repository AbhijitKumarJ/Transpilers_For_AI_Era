from __future__ import annotations

from dataclasses import dataclass, field

from psc.diagnostics import SourceSpan
from psc.frontend.ast_nodes import (
    ArgNode,
    BinaryOp,
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
    LambdaParam,
    LiteralKind,
    LocalVarStmt,
    MethodDecl,
    PropertyDecl,
    ReturnStmt,
    SliceDimension,
    Stmt,
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

        lazy = self.try_lower_lazy_chain(expr)
        if lazy is not None:
            return lazy

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
            stage = curr.data.get("linq_stage")
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
                    lam_body = self._alpha_rename_ident(lam_body, old_name=lam_param, new_name=current_gen.item_var)

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
                    lam_body = self._alpha_rename_ident(lam_body, old_name=lam_param, new_name=current_gen.item_var)

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
                    lam_body = self._alpha_rename_ident(lam_body, old_name=lam_param, new_name=current_gen.item_var)
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
                        k_body = self._alpha_rename_ident(k_body, old_name=k_param, new_name=current_gen.item_var)
                    if v_param != current_gen.item_var:
                        v_body = self._alpha_rename_ident(v_body, old_name=v_param, new_name=current_gen.item_var)
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
            resolved_type=self._terminal_result_type(
                terminal_kind,
                projection,
                key_projection,
                value_projection,
                expr.resolved_type,
            ),
        )

    # ========================================================================
    # LAZY FALLBACK LOWERING FOR NON-FUSABLE LINQ CHAINS
    # ========================================================================

    def try_lower_lazy_chain(self, expr: Expr) -> Expr | None:
        """
        Lower a LINQ chain that cannot be represented as a single comprehension
        into ordinary Python iterator calls. This keeps unsupported or mixed
        pipelines lazy where Python permits, and preserves eager semantics for
        ordering/materialisation operators.
        """
        chain: list[tuple[str, list[ArgNode], Expr]] = []
        curr = expr
        while curr.kind == ExprKind.CALL:
            callee: Expr = curr.data["callee"]
            if callee.kind != ExprKind.MEMBER_ACCESS:
                break
            stage = curr.data.get("linq_stage")
            if stage is None:
                break
            chain.append((stage, list(curr.data.get("args", ())), curr))
            curr = callee.data["target"]

        if not chain:
            return None

        chain.reverse()
        current = self.rewrite_expr(curr)
        span = expr.span
        projection_ty: str | None = None
        key_ty: str | None = None
        value_ty: str | None = None
        result_type: str | None = None

        i = 0
        while i < len(chain):
            stage, args, _call_node = chain[i]

            if stage in ("OrderBy", "OrderByDescending", "ThenBy", "ThenByDescending"):
                if not args:
                    return None
                ordering: list[tuple[str, list[ArgNode], Expr]] = [(stage, args, _call_node)]
                i += 1
                while i < len(chain) and chain[i][0] in ("ThenBy", "ThenByDescending"):
                    if not chain[i][1]:
                        return None
                    ordering.append(chain[i])
                    i += 1
                for order_stage, order_args, _ in reversed(ordering):
                    key = self.rewrite_expr(order_args[0].expr)
                    call_args = [self._arg(current, span), self._arg(key, span, name="key")]
                    if order_stage in ("OrderByDescending", "ThenByDescending"):
                        call_args.append(self._arg(self._bool(True, span), span, name="reverse"))
                    current = self._call("sorted", call_args, span)
                continue

            if stage == "Filter":
                if not args:
                    return None
                pred = self.rewrite_expr(args[0].expr)
                current = self._call("filter", [self._arg(pred, span), self._arg(current, span)], span)
            elif stage == "Map":
                if not args:
                    return None
                selector = self.rewrite_expr(args[0].expr)
                body = args[0].expr.data.get("body")
                if args[0].expr.kind == ExprKind.LAMBDA and isinstance(body, Expr):
                    projection_ty = body.resolved_type
                current = self._call("map", [self._arg(selector, span), self._arg(current, span)], span)
            elif stage == "FlatMap":
                if not args:
                    return None
                selector = self.rewrite_expr(args[0].expr)
                projection_ty = None
                mapped = self._call("map", [self._arg(selector, span), self._arg(current, span)], span)
                chain_fn = self._member(
                    self._member(self._ident("itertools", span), "chain", span), "from_iterable", span
                )
                current = self._make_call(chain_fn, [self._arg(mapped, span)], span)
            elif stage == "Distinct":
                current = self._call("fromkeys", [self._arg(current, span)], span, member_on="dict")
            elif stage == "Take":
                if not args:
                    return None
                count = self._rewrite_count(args[0].expr, span)
                current = self._call(
                    "islice", [self._arg(current, span), self._arg(count, span)], span, module="itertools"
                )
            elif stage == "Skip":
                if not args:
                    return None
                count = self._rewrite_count(args[0].expr, span)
                current = self._call(
                    "islice",
                    [self._arg(current, span), self._arg(count, span), self._arg(self._none(span), span)],
                    span,
                    module="itertools",
                )
            elif stage == "Concat":
                if not args:
                    return None
                other = self.rewrite_expr(args[0].expr)
                current = self._call(
                    "chain", [self._arg(current, span), self._arg(other, span)], span, module="itertools"
                )
            elif stage in ("TerminalList", "ToList"):
                current = self._call("list", [self._arg(current, span)], span)
                result_type = f"list[{projection_ty}]" if projection_ty is not None else expr.resolved_type
            elif stage in ("TerminalSet", "ToHashSet"):
                current = self._call("set", [self._arg(current, span)], span)
                result_type = f"set[{projection_ty}]" if projection_ty is not None else expr.resolved_type
            elif stage == "TerminalDict":
                if len(args) != 2:
                    return None
                key_sel = self.rewrite_expr(args[0].expr)
                val_sel = self.rewrite_expr(args[1].expr)
                key_body = args[0].expr.data.get("body")
                value_body = args[1].expr.data.get("body")
                if args[0].expr.kind == ExprKind.LAMBDA and isinstance(key_body, Expr):
                    key_ty = key_body.resolved_type
                if args[1].expr.kind == ExprKind.LAMBDA and isinstance(value_body, Expr):
                    value_ty = value_body.resolved_type
                item_name = "_ps_item"
                item = self._ident(item_name, span)
                key_call = self._make_call(key_sel, [self._arg(item, span)], span)
                val_call = self._make_call(val_sel, [self._arg(item, span)], span)
                pair = Expr(
                    span=span,
                    kind=ExprKind.TUPLE_LITERAL,
                    data={"elements": [key_call, val_call]},
                )
                pair_lam = Expr(
                    span=span,
                    kind=ExprKind.LAMBDA,
                    data={
                        "params": [LambdaParam(span=span, name=item_name)],
                        "body": pair,
                    },
                )
                mapped = self._call("map", [self._arg(pair_lam, span), self._arg(current, span)], span)
                current = self._call("dict", [self._arg(mapped, span)], span)
                result_type = (
                    f"dict[{key_ty}, {value_ty}]" if key_ty is not None and value_ty is not None else expr.resolved_type
                )
            elif stage in ("TerminalAny", "TerminalAnyPred"):
                if args:
                    pred = self.rewrite_expr(args[0].expr)
                    current = self._call(
                        "any",
                        [self._arg(self._call("map", [self._arg(pred, span), self._arg(current, span)], span), span)],
                        span,
                    )
                else:
                    current = self._call("any", [self._arg(current, span)], span)
                result_type = "bool"
            elif stage == "TerminalAll":
                if not args:
                    return None
                pred = self.rewrite_expr(args[0].expr)
                current = self._call(
                    "all",
                    [self._arg(self._call("map", [self._arg(pred, span), self._arg(current, span)], span), span)],
                    span,
                )
                result_type = "bool"
            elif stage in ("TerminalFirstOrDefault", "TerminalFirstOrDefaultPred"):
                if args:
                    pred = self.rewrite_expr(args[0].expr)
                    seq = self._call("filter", [self._arg(pred, span), self._arg(current, span)], span)
                else:
                    seq = current
                iterator = self._call("iter", [self._arg(seq, span)], span)
                current = self._call("next", [self._arg(iterator, span), self._arg(self._none(span), span)], span)
                result_type = projection_ty or expr.resolved_type
            elif stage == "TerminalCount":
                current = self._call(
                    "len", [self._arg(self._call("list", [self._arg(current, span)], span), span)], span
                )
                result_type = "int"
            elif stage == "TerminalSum":
                current = self._call("sum", [self._arg(current, span)], span)
                result_type = projection_ty or expr.resolved_type
            elif stage == "TerminalMin":
                current = self._call("min", [self._arg(current, span)], span)
                result_type = projection_ty or expr.resolved_type
            elif stage == "TerminalMax":
                current = self._call("max", [self._arg(current, span)], span)
                result_type = projection_ty or expr.resolved_type
            elif stage in ("LastOrDefault", "LastOrDefaultPred", "TerminalLastOrDefault", "TerminalLastOrDefaultPred"):
                if args:
                    pred = self.rewrite_expr(args[0].expr)
                    seq = self._call("filter", [self._arg(pred, span), self._arg(current, span)], span)
                else:
                    seq = current
                materialised = self._call("list", [self._arg(seq, span)], span)
                reversed_seq = self._call("reversed", [self._arg(materialised, span)], span)
                iterator = self._call("iter", [self._arg(reversed_seq, span)], span)
                current = self._call("next", [self._arg(iterator, span), self._arg(self._none(span), span)], span)
                result_type = projection_ty or expr.resolved_type
            elif stage == "Contains":
                if not args:
                    return None
                value = self.rewrite_expr(args[0].expr)
                current = Expr(
                    span=span,
                    kind=ExprKind.BINARY,
                    data={"op": BinaryOp.IN, "left": value, "right": current},
                    resolved_type="bool",
                )
                result_type = "bool"
            elif stage == "Average":
                current = self._call("fmean", [self._arg(current, span)], span, module="statistics")
                result_type = "float"
            else:
                return None

            i += 1

        current.resolved_type = result_type or expr.resolved_type
        return current

    def _terminal_result_type(
        self,
        terminal_kind: ComprehensionKind,
        projection: Expr | None,
        key_projection: Expr | None,
        value_projection: Expr | None,
        fallback: str | None,
    ) -> str | None:
        projection_ty = projection.resolved_type if projection is not None else None
        if terminal_kind == ComprehensionKind.LIST and projection_ty is not None:
            return f"list[{projection_ty}]"
        if terminal_kind == ComprehensionKind.SET and projection_ty is not None:
            return f"set[{projection_ty}]"
        if terminal_kind == ComprehensionKind.DICT:
            key_ty = key_projection.resolved_type if key_projection is not None else None
            value_ty = value_projection.resolved_type if value_projection is not None else None
            if key_ty is not None and value_ty is not None:
                return f"dict[{key_ty}, {value_ty}]"
        if terminal_kind in (ComprehensionKind.ANY, ComprehensionKind.ALL):
            return "bool"
        if terminal_kind == ComprehensionKind.COUNT:
            return "int"
        if (
            terminal_kind
            in (
                ComprehensionKind.SUM,
                ComprehensionKind.MIN,
                ComprehensionKind.MAX,
            )
            and projection_ty is not None
        ):
            return projection_ty
        return fallback

    def _rewrite_count(self, expr: Expr, span: SourceSpan) -> Expr:
        count = self.rewrite_expr(expr)
        return self._call(
            "max",
            [self._arg(self._int(0, span), span), self._arg(count, span)],
            span,
        )

    @staticmethod
    def _ident(name: str, span: SourceSpan) -> Expr:
        return Expr(span=span, kind=ExprKind.IDENT, data={"name": name})

    @staticmethod
    def _member(target: Expr, name: str, span: SourceSpan) -> Expr:
        return Expr(
            span=span,
            kind=ExprKind.MEMBER_ACCESS,
            data={"target": target, "member": name, "type_args": []},
        )

    @staticmethod
    def _arg(expr: Expr, span: SourceSpan, name: str | None = None) -> ArgNode:
        return ArgNode(span=span, name=name, expr=expr)

    @classmethod
    def _make_call(cls, callee: Expr, args: list[ArgNode], span: SourceSpan) -> Expr:
        return Expr(
            span=span,
            kind=ExprKind.CALL,
            data={"callee": callee, "args": args, "type_args": []},
        )

    @classmethod
    def _call(
        cls,
        name: str,
        args: list[ArgNode],
        span: SourceSpan,
        *,
        module: str | None = None,
        member_on: str | None = None,
    ) -> Expr:
        if module is not None:
            callee = cls._member(cls._ident(module, span), name, span)
        elif member_on is not None:
            callee = cls._member(cls._ident(member_on, span), name, span)
        else:
            callee = cls._ident(name, span)
        return cls._make_call(callee, args, span)

    @staticmethod
    def _none(span: SourceSpan) -> Expr:
        return Expr(span=span, kind=ExprKind.LITERAL, data={"literal_kind": LiteralKind.NULL, "value": None})

    @staticmethod
    def _bool(value: bool, span: SourceSpan) -> Expr:
        return Expr(span=span, kind=ExprKind.LITERAL, data={"literal_kind": LiteralKind.BOOL, "value": value})

    @staticmethod
    def _int(value: int, span: SourceSpan) -> Expr:
        return Expr(span=span, kind=ExprKind.LITERAL, data={"literal_kind": LiteralKind.INT, "value": value})

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

    def _substitute_ident_with_expr(self, expr: Expr, target_name: str, replacement: Expr) -> Expr:
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
                new_data["target"] = self._substitute_ident_with_expr(new_data["target"], target_name, replacement)
            return Expr(
                span=expr.span,
                kind=kind,
                data=new_data,
                resolved_type=expr.resolved_type,
                resolved_lowering=expr.resolved_lowering,
            )

        if kind in (ExprKind.BINARY, ExprKind.NULL_COALESCE):
            new_data = dict(expr.data)
            new_data["left"] = self._substitute_ident_with_expr(new_data["left"], target_name, replacement)
            new_data["right"] = self._substitute_ident_with_expr(new_data["right"], target_name, replacement)
            return Expr(
                span=expr.span,
                kind=kind,
                data=new_data,
                resolved_type=expr.resolved_type,
                resolved_lowering=expr.resolved_lowering,
            )

        if kind == ExprKind.UNARY:
            new_data = dict(expr.data)
            new_data["operand"] = self._substitute_ident_with_expr(new_data["operand"], target_name, replacement)
            return Expr(
                span=expr.span,
                kind=kind,
                data=new_data,
                resolved_type=expr.resolved_type,
                resolved_lowering=expr.resolved_lowering,
            )

        if kind == ExprKind.CALL:
            new_data = dict(expr.data)
            new_data["callee"] = self._substitute_ident_with_expr(new_data["callee"], target_name, replacement)
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
            new_data["target"] = self._substitute_ident_with_expr(new_data["target"], target_name, replacement)
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
                            self._substitute_ident_with_expr(d.start, target_name, replacement) if d.start else None
                        ),
                        stop=(self._substitute_ident_with_expr(d.stop, target_name, replacement) if d.stop else None),
                        step=(self._substitute_ident_with_expr(d.step, target_name, replacement) if d.step else None),
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
