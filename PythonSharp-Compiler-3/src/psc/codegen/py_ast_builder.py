from __future__ import annotations

import ast

from psc.codegen.expr_lowerer import ExpressionLowerer, stamp_span
from psc.codegen.overload_emitter import OverloadAstEmitter
from psc.codegen.topo_sorter import PlannedPythonModule
from psc.diagnostics import SourceSpan
from psc.frontend.ast_nodes import (
    FieldDecl,
    IndexerDecl,
    MethodDecl,
    PropertyDecl,
)
from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol, namespace_to_module_path


def _loaded_names(node: ast.AST) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)}


class _RuntimeNameCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.names.add(node.id)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        if node.value is not None:
            self.visit(node.value)

    def visit_arg(self, node: ast.arg) -> None:
        return

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        for statement in node.body:
            self.visit(statement)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.visit(node.args)
        self.visit(node.body)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)
        for statement in node.body:
            self.visit(statement)


def _runtime_names(node: ast.AST) -> set[str]:
    collector = _RuntimeNameCollector()
    collector.visit(node)
    return collector.names


def _annotation_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        annotation: ast.expr | None = None
        if isinstance(child, ast.arg):
            annotation = child.annotation
        elif isinstance(child, ast.AnnAssign):
            annotation = child.annotation
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotation = child.returns
        if annotation is not None:
            names.update(_loaded_names(annotation))
    return names


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

        # Collect all imports declared across units contributing to this namespace
        seen_extern_imports: set[tuple[tuple[str, ...], str | None]] = set()
        seen_ns_imports: set[tuple[str, ...]] = set()
        extern_import_nodes: list[ast.stmt] = []
        ns_import_nodes: list[ast.stmt] = []
        type_checking_import_nodes: list[ast.stmt] = []
        module_for_names = ast.Module(body=class_defs, type_ignores=[])
        runtime_names = _runtime_names(module_for_names)
        annotation_names = _annotation_names(module_for_names)
        needs_math = "math" in runtime_names
        needs_itertools = "itertools" in runtime_names
        needs_statistics = "statistics" in runtime_names
        needs_classvar = "ClassVar" in annotation_names

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
                        runtime_imports = [
                            ast.alias(name=t.name, asname=None)
                            for t in self.symtab.namespaces[target_ns]
                            if not t.is_primitive and not t.is_ambient_stub and t.name in runtime_names
                        ]
                        type_only_imports = [
                            ast.alias(name=t.name, asname=None)
                            for t in self.symtab.namespaces[target_ns]
                            if (
                                not t.is_primitive
                                and not t.is_ambient_stub
                                and t.name not in runtime_names
                                and t.name in annotation_names
                            )
                        ]
                        if runtime_imports:
                            ns_import_nodes.append(
                                stamp_span(
                                    ast.ImportFrom(module=mod_path, names=runtime_imports, level=0),
                                    imp.span,
                                )  # type: ignore[arg-type]
                            )
                        if type_only_imports:
                            type_checking_import_nodes.append(
                                stamp_span(
                                    ast.ImportFrom(module=mod_path, names=type_only_imports, level=0),
                                    imp.span,
                                )  # type: ignore[arg-type]
                            )

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
        stdlib_imports: list[ast.Import] = []
        existing_extern_aliases = {
            alias.asname or alias.name
            for imp in extern_import_nodes
            for alias in imp.names
        }

        if needs_enum and "enum" not in existing_extern_aliases:
            stdlib_imports.append(
                ast.Import(
                    names=[ast.alias(name="enum", asname=None)],
                    lineno=1,
                    col_offset=0,
                )
            )
        if needs_itertools and "itertools" not in existing_extern_aliases:
            stdlib_imports.append(
                ast.Import(
                    names=[ast.alias(name="itertools", asname=None)],
                    lineno=1,
                    col_offset=0,
                )
            )
        if needs_math and "math" not in existing_extern_aliases:
            stdlib_imports.append(
                ast.Import(
                    names=[ast.alias(name="math", asname=None)],
                    lineno=1,
                    col_offset=0,
                )
            )
        if needs_statistics and "statistics" not in existing_extern_aliases:
            stdlib_imports.append(
                ast.Import(
                    names=[ast.alias(name="statistics", asname=None)],
                    lineno=1,
                    col_offset=0,
                )
            )

        known_stdlib_auto = (
            "os",
            "sys",
            "json",
            "re",
            "time",
            "datetime",
            "logging",
            "contextlib",
            "subprocess",
            "shutil",
            "math",
            "pathlib",
            "hashlib",
            "uuid",
            "urllib",
            "scipy",
            "sklearn",
            "torch",
            "pandas",
            "polars",
            "numpy",
            "xgboost",
            "lightgbm",
            "optuna",
            "transformers",
            "faiss",
            "onnxruntime",
            "sympy",
            "qiskit",
        )
        for mod_name in known_stdlib_auto:
            if mod_name in runtime_names and mod_name not in existing_extern_aliases:
                stdlib_imports.append(
                    ast.Import(
                        names=[ast.alias(name=mod_name, asname=None)],
                        lineno=1,
                        col_offset=0,
                    )
                )

        known_aliased_stdlib = {
            "_py_os": "os",
            "_py_time": "time",
            "_py_json": "json",
            "_py_re": "re",
            "_py_sys": "sys",
            "_py_shutil": "shutil",
            "_py_logging": "logging",
            "_py_log": "logging",
            "_py_ctx": "contextlib",
            "_py_sub": "subprocess",
            "_py_proc": "subprocess",
            "_py_pathlib": "pathlib",
            "_py_path": "pathlib",
            "_py_hashlib": "hashlib",
            "_py_hash": "hashlib",
            "_py_uuid": "uuid",
            "_py_req": "urllib.request",
            "_py_urllib_req": "urllib.request",
            "_py_parse": "urllib.parse",
            "_py_dt": "datetime",
            "dt": "datetime",
            "_py_math": "math",
            "py_math": "math",
            "_py_builtins": "builtins",
            "_py_tb": "traceback",
            "np": "numpy",
            "_np": "numpy",
            "pd": "pandas",
            "_pd": "pandas",
            "pl": "polars",
            "_pl": "polars",
            "xgb": "xgboost",
            "_xgb": "xgboost",
            "lgb": "lightgbm",
            "_lgb": "lightgbm",
            "optuna": "optuna",
            "_optuna": "optuna",
            "_hf": "transformers",
            "transformers": "transformers",
            "_faiss": "faiss",
            "ort": "onnxruntime",
            "_ort": "onnxruntime",
            "_scipy_fft": "scipy.fft",
            "_scipy_linalg": "scipy.linalg",
            "_scipy_opt": "scipy.optimize",
            "_scipy_sparse": "scipy.sparse",
            "_scipy_stats": "scipy.stats",
            "plt": "matplotlib.pyplot",
            "_plt": "matplotlib.pyplot",
            "sns": "seaborn",
            "_sns": "seaborn",
            "_ens": "sklearn.ensemble",
            "_lin": "sklearn.linear_model",
            "_met": "sklearn.metrics",
            "_ms": "sklearn.model_selection",
            "_prep": "sklearn.preprocessing",
            "sp": "sympy",
            "_sp": "sympy",
            "torch": "torch",
            "_torch": "torch",
            "_nn": "torch.nn",
            "_optim": "torch.optim",
            "_qk": "qiskit",
            "_qi": "qiskit.quantum_info",
        }
        for alias, mod_name in known_aliased_stdlib.items():
            if alias in runtime_names and alias not in existing_extern_aliases:
                stdlib_imports.append(
                    ast.Import(
                        names=[ast.alias(name=mod_name, asname=alias)],
                        lineno=1,
                        col_offset=0,
                    )
                )

        stdlib_imports.sort(key=lambda node: node.names[0].name)
        body.extend(stdlib_imports)

        from_imports: list[ast.ImportFrom] = []
        if needs_dataclass:
            from_imports.append(
                ast.ImportFrom(
                    module="dataclasses",
                    names=[ast.alias(name="dataclass", asname=None)],
                    level=0,
                    lineno=1,
                    col_offset=0,
                )
            )
        if needs_decimal:
            from_imports.append(
                ast.ImportFrom(
                    module="decimal",
                    names=[ast.alias(name="Decimal", asname=None)],
                    level=0,
                    lineno=1,
                    col_offset=0,
                )
            )
        needs_pydantic = any(
            t.ast_node.emission_strategy.kind == "SchemaModel"
            for t in planned.types
            if not t.is_interface and not t.is_enum and not t.is_primitive
        )
        if needs_pydantic:
            from_imports.append(
                ast.ImportFrom(
                    module="pydantic",
                    names=[ast.alias(name="BaseModel", asname=None)],
                    level=0,
                    lineno=1,
                    col_offset=0,
                )
            )

        typing_names: list[str] = []
        if needs_any or needs_overload:
            typing_names.append("Any")
        if needs_protocol:
            typing_names.append("Protocol")
        if needs_overload:
            typing_names.append("overload")
        if needs_classvar:
            typing_names.append("ClassVar")
        if type_checking_import_nodes:
            typing_names.append("TYPE_CHECKING")
        if typing_names:
            from_imports.append(
                ast.ImportFrom(
                    module="typing",
                    names=[ast.alias(name=n, asname=None) for n in sorted(typing_names)],
                    level=0,
                    lineno=1,
                    col_offset=0,
                )
            )
        from_imports.sort(key=lambda node: node.module or "")
        body.extend(from_imports)

        body.extend(extern_import_nodes)
        body.extend(ns_import_nodes)
        if type_checking_import_nodes:
            body.append(
                ast.If(
                    test=ast.Name(id="TYPE_CHECKING", ctx=ast.Load()),
                    body=type_checking_import_nodes,
                    orelse=[],
                )
            )
        body.extend(class_defs)

        mod = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(mod)
        return mod

    # ========================================================================
    # TYPE DECLARATION BUILDERS
    # ========================================================================

    def build_type_decl(self, type_sym: TypeSymbol, lowerer: ExpressionLowerer) -> ast.ClassDef:
        if type_sym.is_interface:
            return self.build_interface_protocol(type_sym, lowerer)
        if type_sym.is_enum:
            return self.build_enum_class(type_sym, lowerer)
        if type_sym.ast_node.emission_strategy.kind == "SchemaModel":
            return self.build_schema_model_class(type_sym, lowerer)
        if type_sym.ast_node.emission_strategy.kind == "SlottedDataclass":
            return self.build_record_or_struct_dataclass(type_sym, lowerer)
        return self.build_standard_class(type_sym, lowerer)

    def build_schema_model_class(self, type_sym: TypeSymbol, lowerer: ExpressionLowerer) -> ast.ClassDef:
        decl = type_sym.ast_node
        strat = decl.emission_strategy
        decorators = [lowerer.lower_expr(d) for d in decl.decorators_to_emit]
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

        for member in decl.members:
            if isinstance(member, FieldDecl):
                ann_ast = lowerer.lower_type_ref_annotation(member.type_ref)
                val_ast = lowerer.lower_expr(member.initializer) if member.initializer is not None else None
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
            elif (
                isinstance(member, PropertyDecl)
                and not member.expr_body
                and all(a.body is None for a in member.accessors)
                and "static" not in member.modifiers
            ):
                ann_ast = lowerer.lower_type_ref_annotation(member.type_ref)
                val_ast = lowerer.lower_expr(member.initializer) if member.initializer is not None else None
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
            elif isinstance(member, PropertyDecl) and "static" in member.modifiers:
                body.extend(self._emit_static_property(member, lowerer, use_classvar=True))
            elif isinstance(member, PropertyDecl):
                body.extend(self._emit_property(member, lowerer))
            elif isinstance(member, MethodDecl) and not member.is_constructor:
                body.append(self._emit_single_method(member, lowerer, OverloadAstEmitter(self.symtab, lowerer)))

        if not body:
            body.append(ast.Pass())

        runtime_bases = self._build_runtime_bases(type_sym)
        has_base_model = any(isinstance(b, ast.Name) and b.id == "BaseModel" for b in runtime_bases)
        if not has_base_model:
            runtime_bases.insert(0, ast.Name(id="BaseModel", ctx=ast.Load()))

        cls_def = ast.ClassDef(
            name=decl.name,
            bases=runtime_bases,
            keywords=[],
            body=body,
            decorator_list=decorators,
        )
        return stamp_span(cls_def, decl.span)  # type: ignore[return-value]

    def build_interface_protocol(self, type_sym: TypeSymbol, lowerer: ExpressionLowerer) -> ast.ClassDef:
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

    def build_enum_class(self, type_sym: TypeSymbol, lowerer: ExpressionLowerer) -> ast.ClassDef:
        decl = type_sym.ast_node
        bases: list[ast.expr] = [
            ast.Attribute(
                value=ast.Name(id="enum", ctx=ast.Load()),
                attr="IntEnum",
                ctx=ast.Load(),
            )
        ]
        body: list[ast.stmt] = []
        next_value: int | None = 0
        for idx, em in enumerate(decl.enum_members):
            if em.value is not None:
                val_ast = lowerer.lower_expr(em.value)
                try:
                    literal_value = ast.literal_eval(val_ast)
                except (ValueError, TypeError, SyntaxError):
                    next_value = None
                else:
                    next_value = (
                        literal_value + 1
                        if isinstance(literal_value, int) and not isinstance(literal_value, bool)
                        else None
                    )
            elif next_value is not None:
                val_ast = ast.Constant(value=next_value)
                next_value += 1
            else:
                val_ast = ast.Constant(value=idx)
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

    def build_record_or_struct_dataclass(self, type_sym: TypeSymbol, lowerer: ExpressionLowerer) -> ast.ClassDef:
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

        for member in decl.members:
            if isinstance(member, PropertyDecl) and "static" in member.modifiers:
                body.extend(self._emit_static_property(member, lowerer, use_classvar=True))

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

    def build_standard_class(self, type_sym: TypeSymbol, lowerer: ExpressionLowerer) -> ast.ClassDef:
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
            elif isinstance(member, PropertyDecl) and "static" in member.modifiers:
                body.extend(self._emit_static_property(member, lowerer, use_classvar=False))

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

        ctors = [m for m in decl.members if isinstance(m, MethodDecl) and m.is_constructor]

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
                if "static" not in member.modifiers:
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

    def _build_instance_slot_initializers(self, type_sym: TypeSymbol, lowerer: ExpressionLowerer) -> list[ast.stmt]:
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

    def _emit_static_property(
        self,
        prop: PropertyDecl,
        lowerer: ExpressionLowerer,
        *,
        use_classvar: bool,
    ) -> list[ast.stmt]:
        snake = prop.emitted_snake_name
        ret_ann = lowerer.lower_type_ref_annotation(prop.type_ref)
        all_auto = prop.expr_body is None and all(
            accessor.body is None and accessor.expr_body is None for accessor in prop.accessors
        )

        if all_auto:
            annotation = ret_ann
            if use_classvar:
                annotation = ast.Subscript(
                    value=ast.Name(id="ClassVar", ctx=ast.Load()),
                    slice=ret_ann,
                    ctx=ast.Load(),
                )
            value = lowerer.lower_expr(prop.initializer) if prop.initializer is not None else ast.Constant(value=None)
            stmt = ast.AnnAssign(
                target=ast.Name(id=snake, ctx=ast.Store()),
                annotation=annotation,
                value=value,
                simple=1,
            )
            return [stamp_span(stmt, prop.span)]  # type: ignore[list-item]

        getter = next((accessor for accessor in prop.accessors if accessor.kind == "get"), None)
        if prop.expr_body is not None:
            body: list[ast.stmt] = [ast.Return(value=lowerer.lower_expr(prop.expr_body))]
            span = prop.span
        elif getter is not None and getter.expr_body is not None:
            body = [ast.Return(value=lowerer.lower_expr(getter.expr_body))]
            span = getter.span
        elif getter is not None and getter.body is not None:
            body = lowerer.lower_block_with_using(getter.body.statements, getter.span)
            span = getter.span
        else:
            body = [ast.Return(value=ast.Constant(value=None))]
            span = prop.span

        getter_fn = ast.FunctionDef(
            name=snake,
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg="cls")],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=body,
            decorator_list=[
                ast.Name(id="classmethod", ctx=ast.Load()),
            ],
            returns=ret_ann,
        )
        return [stamp_span(getter_fn, span)]  # type: ignore[list-item]

    def _emit_property(self, prop: PropertyDecl, lowerer: ExpressionLowerer) -> list[ast.stmt]:
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
                py_args = overload_emitter._build_method_arguments(indexer.params, is_static=False)
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
                py_args = overload_emitter._build_method_arguments(indexer.params, is_static=False)
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
            ast.Constant(value=None) if method.is_constructor else lowerer.lower_type_ref_annotation(method.return_type)
        )

        body: list[ast.stmt] = []
        if method.is_constructor and ctor_slot_inits:
            body.extend(ctor_slot_inits)

        if method.is_constructor and method.ctor_chain is not None:
            pos_args, kw_args = lowerer._lower_call_args(method.ctor_chain.args)
            if method.ctor_chain.target == "base":
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
            body.append(
                stamp_span(
                    ast.Expr(value=ast.Call(func=chain_callee, args=pos_args, keywords=kw_args)),
                    method.ctor_chain.span,
                )  # type: ignore[arg-type]
            )

        if method.expr_body is not None:
            is_void = method.is_constructor or (method.return_type is not None and method.return_type.path == ["void"])
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

    def _build_sync_context_manager_methods(self, type_sym: TypeSymbol) -> list[ast.stmt]:
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
                    ast.arg(
                        arg="exc_type",
                        annotation=ast.BinOp(
                            left=ast.Name(id="object", ctx=ast.Load()),
                            op=ast.BitOr(),
                            right=ast.Constant(value=None),
                        ),
                    ),
                    ast.arg(
                        arg="exc_val",
                        annotation=ast.BinOp(
                            left=ast.Name(id="object", ctx=ast.Load()),
                            op=ast.BitOr(),
                            right=ast.Constant(value=None),
                        ),
                    ),
                    ast.arg(
                        arg="exc_tb",
                        annotation=ast.BinOp(
                            left=ast.Name(id="object", ctx=ast.Load()),
                            op=ast.BitOr(),
                            right=ast.Constant(value=None),
                        ),
                    ),
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

    def _build_async_context_manager_methods(self, type_sym: TypeSymbol) -> list[ast.stmt]:
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
                    ast.arg(
                        arg="exc_type",
                        annotation=ast.BinOp(
                            left=ast.Name(id="object", ctx=ast.Load()),
                            op=ast.BitOr(),
                            right=ast.Constant(value=None),
                        ),
                    ),
                    ast.arg(
                        arg="exc_val",
                        annotation=ast.BinOp(
                            left=ast.Name(id="object", ctx=ast.Load()),
                            op=ast.BitOr(),
                            right=ast.Constant(value=None),
                        ),
                    ),
                    ast.arg(
                        arg="exc_tb",
                        annotation=ast.BinOp(
                            left=ast.Name(id="object", ctx=ast.Load()),
                            op=ast.BitOr(),
                            right=ast.Constant(value=None),
                        ),
                    ),
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
            if base_sym.is_interface or base_sym.is_primitive:
                continue
            py_base = base_sym.maps_to_py_type or base_sym.name
            bases.append(ast.parse(py_base, mode="eval").body)
        return bases

    @staticmethod
    def _build_ps_types_assign(ps_types: list[str], span: SourceSpan) -> ast.stmt:
        tup = ast.Tuple(
            elts=[ast.Constant(value=t) for t in ps_types],
            ctx=ast.Load(),
        )
        assign = ast.Assign(
            targets=[ast.Name(id="__ps_types__", ctx=ast.Store())],
            value=tup,
        )
        return stamp_span(assign, span)  # type: ignore[return-value]
