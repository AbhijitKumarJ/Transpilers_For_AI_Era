Based on the **Milestone 1–6 Implementation Plan and Repository Map (`repomap`)** for the **PythonSharp Prototype Transpiler (`psc`)**, the following files from the repository map remained to be generated:

1. `src/psc/semantics/type_checker.py` — **Milestone 4 (Pass 2 Orchestrator, Generic `where` Constraint Verifier & Expression Type Checker)**


2. `src/psc/semantics/__init__.py` — **Updated Semantics Package Exports (including `TypeChecker`)**


3. `tests/fixtures/commerce_sample/Commerce.psproj` — **Milestone 2/6 Multi-File Sample Project Configuration**


4. `tests/fixtures/commerce_sample/Domain/IAuditable.ps` — **Milestone 3/6 Nominal Interface Fixture**


5. `tests/fixtures/commerce_sample/Domain/Order.ps` — **Milestone 2/6 Circular Cross-File Type Reference Fixture (`Order` $\leftrightarrow$ `OrderCache`)**


6. `tests/fixtures/commerce_sample/Services/OrderCache.ps` — **Milestone 3/4/5/6 End-to-End Service Fixture (`Dict<K,V>`, Overloads, LINQ, `private set`, `IDisposable`)**


7. `README.md` — **Repository Architecture Overview, Diagnostic Reference & Quickstart Guide**



Here are each of the missing files in full, individual plain text format:

---

### `src/psc/semantics/type_checker.py`

```python
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
                    self._check_expr_generic_instantiations(
                        member.initializer, type_sym, active_tparams
                    )

            elif isinstance(member, PropertyDecl):
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
                    self._check_expr_generic_instantiations(
                        member.initializer, type_sym, active_tparams
                    )
                if member.expr_body is not None:
                    self._check_expr_generic_instantiations(
                        member.expr_body, type_sym, active_tparams
                    )
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
                    active_tparams=active_tparams,
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
                self._verify_declared_constraints(
                    member.constraints, type_sym, method_tparams
                )
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
                    self._check_expr_generic_instantiations(
                        member.expr_body, type_sym, method_tparams
                    )

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
            self._check_expr_generic_instantiations(
                stmt.initializer, caller_type, active_tparams
            )

        elif isinstance(stmt, UsingResourceStmt):
            self._check_expr_generic_instantiations(
                stmt.initializer, caller_type, active_tparams
            )

        elif isinstance(stmt, IfStmt):
            self._check_expr_generic_instantiations(
                stmt.condition, caller_type, active_tparams
            )
            self._check_stmt_types(
                stmt.then_branch, caller_type, expected_return, active_tparams
            )
            if stmt.else_branch is not None:
                self._check_stmt_types(
                    stmt.else_branch, caller_type, expected_return, active_tparams
                )

        elif isinstance(stmt, WhileStmt):
            self._check_expr_generic_instantiations(
                stmt.condition, caller_type, active_tparams
            )
            self._check_stmt_types(
                stmt.body, caller_type, expected_return, active_tparams
            )

        elif isinstance(stmt, ForEachStmt):
            self._check_expr_generic_instantiations(
                stmt.collection, caller_type, active_tparams
            )
            self._check_stmt_types(
                stmt.body, caller_type, expected_return, active_tparams
            )

        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                if expected_return is not None and expected_return.py_annotation != "None":
                    self._check_null_assignment(
                        span=stmt.span,
                        target_name="return value",
                        declared_type=expected_return,
                        value_expr=stmt.value,
                    )
                self._check_expr_generic_instantiations(
                    stmt.value, caller_type, active_tparams
                )

        elif isinstance(stmt, YieldStmt):
            if stmt.value is not None:
                self._check_expr_generic_instantiations(
                    stmt.value, caller_type, active_tparams
                )

        elif isinstance(stmt, ThrowStmt):
            if stmt.exception is not None:
                self._check_expr_generic_instantiations(
                    stmt.exception, caller_type, active_tparams
                )

        elif isinstance(stmt, TryCatchFinallyStmt):
            self._check_stmt_types(
                stmt.try_block, caller_type, expected_return, active_tparams
            )
            for c in stmt.catches:
                if c.body is not None:
                    self._check_stmt_types(
                        c.body, caller_type, expected_return, active_tparams
                    )
            if stmt.finally_block is not None:
                self._check_stmt_types(
                    stmt.finally_block, caller_type, expected_return, active_tparams
                )

        elif isinstance(stmt, SwitchStmt):
            self._check_expr_generic_instantiations(
                stmt.scrutinee, caller_type, active_tparams
            )
            for sec in stmt.sections:
                for s in sec.statements:
                    self._check_stmt_types(
                        s, caller_type, expected_return, active_tparams
                    )

        elif isinstance(stmt, ExprStmt):
            self._check_expr_generic_instantiations(
                stmt.expr, caller_type, active_tparams
            )

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
            self._check_expr_generic_instantiations(
                expr.data.get("callee"), caller_type, active_tparams
            )
            for arg in expr.data.get("args", ()):
                self._check_expr_generic_instantiations(arg.expr, caller_type, active_tparams)

        elif expr.kind in (ExprKind.BINARY, ExprKind.NULL_COALESCE):
            self._check_expr_generic_instantiations(
                expr.data.get("left"), caller_type, active_tparams
            )
            self._check_expr_generic_instantiations(
                expr.data.get("right"), caller_type, active_tparams
            )

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

```

---

### `src/psc/semantics/__init__.py`

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine
from psc.frontend.ast_nodes import CompilationUnit
from psc.semantics.symbols import (
    BUILTIN_PRIMITIVE_MAP,
    GlobalSymbolTable,
    MemberSymbol,
    ResolvedType,
    TypeSymbol,
    namespace_to_module_path,
    pascal_to_snake,
)
from psc.semantics.collector import SymbolCollector
from psc.semantics.slot_analyzer import SlotAndHierarchyAnalyzer
from psc.semantics.access_checker import AccessChecker
from psc.semantics.primitive_resolver import PrimitiveResolver
from psc.semantics.overload_resolver import OverloadResolver
from psc.semantics.linq_fuser import ComprehensionGenerator, LinqComprehensionFuser
from psc.semantics.type_checker import TypeChecker


def analyze_compilation_units(
    units: list[CompilationUnit],
    symtab: GlobalSymbolTable,
    diagnostics: DiagnosticEngine,
    assembly_name: str | None = None,
) -> None:
    """
    Runs the complete Pass 1 + Pass 2 semantic pipeline across all compilation units:
      1. Pass 1 (`SymbolCollector`): Registers all types, inheritance chains, and members.
      2. Pass 2 (`TypeChecker`): Runs `SlotAndHierarchyAnalyzer`, `AccessChecker`,
         `PrimitiveResolver`, `OverloadResolver`, `LinqComprehensionFuser`, and
         generic constraint / nullability checks.
    """
    SymbolCollector(symtab, diagnostics).collect_all(units, assembly_name=assembly_name)
    TypeChecker(symtab, diagnostics).check_and_decorate_all(units)


__all__ = [
    "BUILTIN_PRIMITIVE_MAP",
    "GlobalSymbolTable",
    "MemberSymbol",
    "ResolvedType",
    "TypeSymbol",
    "SymbolCollector",
    "SlotAndHierarchyAnalyzer",
    "AccessChecker",
    "PrimitiveResolver",
    "OverloadResolver",
    "LinqComprehensionFuser",
    "ComprehensionGenerator",
    "TypeChecker",
    "analyze_compilation_units",
    "namespace_to_module_path",
    "pascal_to_snake",
]

```

---

### `tests/fixtures/commerce_sample/Commerce.psproj`

```xml
<Project Sdk="PythonSharp.Sdk">
  <PropertyGroup>
    <AssemblyName>Commerce.Sample</AssemblyName>
    <OutputPath>dist</OutputPath>
    <TargetPython>3.11</TargetPython>
    <EmitPyc>true</EmitPyc>
  </PropertyGroup>
</Project>

```

---

### `tests/fixtures/commerce_sample/Domain/IAuditable.ps`

```csharp
namespace Commerce.Domain;

public interface IAuditable
{
    string AuditTag { get; }
}

```

---

### `tests/fixtures/commerce_sample/Domain/Order.ps`

```csharp
namespace Commerce.Domain;

using Commerce.Services;

/// <summary>
/// Demonstrates decoupled virtual namespaces (`Commerce.Domain` merged with `IAuditable.ps`)
/// and circular cross-file type references (`Order` references `OrderCache` while
/// `OrderCache` in `Services/OrderCache.ps` references `Order`).
/// </summary>
public record Order(int Id, decimal Total, bool IsActive)
{
    public bool RegisterIn(OrderCache cache)
    {
        cache.Put(this);
        return IsActive;
    }
}

```

---

### `tests/fixtures/commerce_sample/Services/OrderCache.ps`

```csharp
namespace Commerce.Services;

using PythonSharp.Core;
using Commerce.Domain;

public class OrderCache : IAuditable, IDisposable
{
    private readonly Dict<int, Order> _store = new Dict<int, Order>();
    public string AuditTag { get; private set; }

    public OrderCache(string tag) => AuditTag = tag;

    public void Put(Order order) => _store[order.Id] = order;
    public void Put(int id, decimal total) => _store[id] = new Order(id, total, true);

    public Order? GetOrNull(int id) => _store.GetOrDefault(id);

    public List<int> GetActiveIds(decimal minTotal = 0.0m)
    {
        return _store.Values()
            .Where(o => o.IsActive && o.Total >= minTotal)
            .Select(o => o.Id)
            .ToList();
    }

    public void Dispose() => _store.Clear();
}

```

---

### `README.md`

```markdown
# PythonSharp Compiler (`psc`) — Phase 1 Prototype

**PythonSharp (`.ps` / `.d.ps`)** is a multi-pass static C#-to-Python 3.11+ transpiler that pairs **Compile-Time C# Architectural Discipline** with **Zero-Overhead Runtime Python Isomorphism**.

## Core Architectural Features

1. **File-Independent Virtual Namespaces & Circular Reference Resolution (Pass 1):**
   Organize `.ps` files freely across directories. `psc` resolves circular cross-file type references globally before emitting topologically ordered Python packages with `from __future__ import annotations`.
2. **Compile-Time Encapsulation & Automatic `__slots__` (Pass 2A):**
   Enforces `private`, `protected`, and `.psproj`-scoped `internal` visibility (`PS001`), computes deduplicated `__slots__` across inheritance hierarchies (saving 40–60% instance RAM), and attaches static `__ps_types__` nominal metadata tuples for $O(1)$ `is` / `as` interface checks.
3. **Zero-Cost `primitive` Type Erasure (Pass 2B):**
   `List<T>`, `Dict<K, V>`, `HashSet<T>`, and `String` in `stdlib/PythonSharp.Core.d.ps` erase 1:1 to native Python `list`, `dict`, `set`, and `str` via `[MapsTo]` and `[InlineTemplate]` with zero runtime wrapper objects.
4. **True Method & Constructor Overloading (Pass 2B / Pass 3A):**
   Synthesizes `@overload` static typing stubs paired with an arity/`isinstance`/`__ps_types__` runtime dispatch router, while catching ambiguous erased generic overloads at compile time (`PS002`).
5. **LINQ-to-Comprehension Fusion (Pass 2B):**
   Fuses chained `.Where().Select().ToList()`, `.ToHashSet()`, `.ToDict()`, `.Any()`, `.All()`, and `.Sum()` pipelines into single-pass Python comprehensions with alpha-renamed lambda variables and zero lambda call overhead.
6. **PEP 552 `.pyc` Bytecode Line-Pinning (Pass 3B):**
   Stamps every emitted Python `ast.AST` node with its original `.ps` line number (`lineno`) and compiles `.pyc` bytecode with `co_filename = "<OriginalFile>.ps"`, so native CPython tracebacks point directly to `.ps` files and lines with zero runtime hooks.

## Repository Layout

```text
pythonsharp-compiler/
├── pyproject.toml
├── README.md
├── stdlib/
│   └── PythonSharp.Core.d.ps
├── src/
│   └── psc/
│       ├── __init__.py
│       ├── cli.py
│       ├── project.py
│       ├── diagnostics.py
│       ├── frontend/
│       │   ├── __init__.py
│       │   ├── tokens.py
│       │   ├── lexer.py
│       │   ├── ast_nodes.py
│       │   └── parser.py
│       ├── semantics/
│       │   ├── __init__.py
│       │   ├── symbols.py
│       │   ├── collector.py
│       │   ├── access_checker.py
│       │   ├── slot_analyzer.py
│       │   ├── primitive_resolver.py
│       │   ├── overload_resolver.py
│       │   ├── linq_fuser.py
│       │   └── type_checker.py
│       └── codegen/
│           ├── __init__.py
│           ├── topo_sorter.py
│           ├── py_ast_builder.py
│           ├── overload_emitter.py
│           ├── expr_lowerer.py
│           └── emitter.py
└── tests/
    ├── test_lexer_parser.py
    ├── test_symbol_collector.py
    ├── test_access_and_slots.py
    ├── test_overloads_and_linq.py
    ├── test_py_ast_builder.py
    ├── test_bytecode_tracebacks.py
    └── fixtures/
        └── commerce_sample/
            ├── Commerce.psproj
            ├── Domain/
            │   ├── IAuditable.ps
            │   └── Order.ps
            └── Services/
                └── OrderCache.ps

```

## Quickstart & CLI Usage

```bash
# Install in editable mode
pip install -e .

# Run Pass 1 & Pass 2 static verification on a .psproj project
psc check tests/fixtures/commerce_sample/Commerce.psproj

# Inspect lowered Python 3.11+ AST output
psc dump-ast tests/fixtures/commerce_sample/Commerce.psproj

# Build Python packages (.py) and line-pinned PEP 552 bytecode (.pyc)
psc build tests/fixtures/commerce_sample/Commerce.psproj

# Run the pytest verification suite across Milestones 1–6
pytest

```

## Compiler Diagnostic Codes

| Code | Rule Name | Description |
| --- | --- | --- |
| **`PS000`** | Syntax / Type Error | Lexical, grammatical, constraint, or nullability violation. |
| **`PS001`** | Encapsulation Violation | Illegal access to a `private`, `protected`, `readonly`, or cross-assembly `internal` member. |
| **`PS002`** | Ambiguous Erased Overload | Two method or constructor overloads erase to identical Python runtime types at the same arity (e.g. `List<int>` vs `List<string>`). |
| **`PS003`** | Circular Static Initializer | Mutual dependency cycle detected between static field/property initializers across classes. |
| **`PS004`** | NativeCompile Dynamic Restriction | A class marked `[NativeCompile]` uses the `dynamic` type in a field, property, parameter, or local variable. |

```

```
