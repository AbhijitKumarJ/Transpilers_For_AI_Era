from __future__ import annotations

import ast

from psc.codegen.expr_lowerer import ExpressionLowerer, stamp_span
from psc.frontend.ast_nodes import (
    MethodDecl,
    OverloadDispatchGroup,
    OverloadGuard,
    ParamDecl,
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
            vararg=ast.arg(arg="args", annotation=ast.Name(id="Any", ctx=ast.Load())),
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
                ast.Constant(value=f"No matching overload for {owner_type.name}.{snake_name} with args "),
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

        ret_ann = ast.Constant(value=None) if first_var.is_constructor else None

        fn_cls = ast.AsyncFunctionDef if is_async else ast.FunctionDef
        dispatcher = fn_cls(
            name=snake_name,
            args=dispatcher_args,
            body=body,
            decorator_list=decorators,
            returns=ret_ann,
            type_comment="ignore",
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

    def _build_single_param_check(self, arg_expr: ast.expr, rt_check: RuntimeTypeCheck) -> ast.expr:
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
                    value=ast.Call(func=ast.Name(id="super", ctx=ast.Load()), args=[], keywords=[]),
                    attr="__init__",
                    ctx=ast.Load(),
                )
            else:
                chain_callee = ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="__init__",
                    ctx=ast.Load(),
                )
            stmts.append(ast.Expr(value=ast.Call(func=chain_callee, args=pos_args, keywords=kw_args)))

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
            lowered_stmts = self.lowerer.lower_block_with_using(variant.body.statements, variant.span)
            stmts.extend(lowered_stmts)
            if not stmts or not isinstance(stmts[-1], (ast.Return, ast.Raise)):
                stmts.append(ast.Return(value=None))
        else:
            stmts.append(ast.Return(value=None))

        for s in stmts:
            stamp_span(s, variant.span)

        return stmts

    def _build_method_arguments(self, params: list[ParamDecl], is_static: bool) -> ast.arguments:
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
