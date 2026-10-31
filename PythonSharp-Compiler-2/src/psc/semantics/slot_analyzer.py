from __future__ import annotations

from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend.ast_nodes import (
    BlockStmt,
    ClassEmissionStrategy,
    CompilationUnit,
    Expr,
    ExprKind,
    FieldDecl,
    ForEachStmt,
    IfStmt,
    LocalVarStmt,
    MethodDecl,
    PropertyDecl,
    Stmt,
    SwitchStmt,
    TryCatchFinallyStmt,
    TypeKind,
    TypeRef,
    UsingResourceStmt,
    WhileStmt,
)
from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol

DISPOSABLE_QNAMES = frozenset({"PythonSharp.Core.IDisposable", "IDisposable"})
ASYNC_DISPOSABLE_QNAMES = frozenset({"PythonSharp.Core.IAsyncDisposable", "IAsyncDisposable"})
SCHEMA_BASE_NAMES = frozenset({"BaseModel", "pydantic.BaseModel", "PythonSharp.Core.SchemaModel"})


class SlotAndHierarchyAnalyzer:
    """
    Pass 2A of the PythonSharp Compiler (`psc`):
      1. Computes deduplicated `__slots__` across class inheritance chains (collecting
         instance fields and auto-property `_prop` backing slots while subtracting any
         slots already declared on ancestor base classes).
      2. Computes the static `__ps_types__` nominal hierarchy tuple for O(1) runtime
         `is` and `as` interface/type checks.
      3. Detects `IDisposable` and `IAsyncDisposable` implementations to synthesize
         Python `__enter__`/`__exit__` and `__aenter__`/`__aexit__` context managers.
      4. Populates `TypeDecl.emission_strategy` (`ClassEmissionStrategy`).
      5. Enforces Rule PS003 (circular static field initializers) and Rule PS004
         (`[NativeCompile]` classes cannot use `dynamic`).
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        diagnostics: DiagnosticEngine,
    ) -> None:
        self.symtab = symtab
        self.diagnostics = diagnostics
        self._all_inherited_slots_cache: dict[int, set[str]] = {}

    def analyze_all(self, units: list[CompilationUnit] | None = None) -> None:
        """Analyzes all registered types in the symbol table and populates Pass 2A slots."""
        target_types: list[TypeSymbol] = []
        if units is not None:
            for unit in units:
                for decl in unit.types:
                    if decl.symbol_id is not None and decl.symbol_id in self.symtab.types_by_id:
                        target_types.append(self.symtab.types_by_id[decl.symbol_id])
        else:
            target_types = list(self.symtab.types_by_id.values())

        for type_sym in target_types:
            self.analyze_type(type_sym)

        self._verify_no_circular_static_initializers(target_types)

    def analyze_type(self, type_sym: TypeSymbol) -> ClassEmissionStrategy:
        decl = type_sym.ast_node

        # 1. Ambient or `primitive` types erase completely at runtime
        if type_sym.is_primitive:
            strategy = ClassEmissionStrategy(
                kind="ErasedPrimitive",
                py_runtime_type=type_sym.maps_to_py_type or type_sym.name,
                own_slots=[],
                ps_types_tuple=[],
                generates_context_manager=False,
                generates_async_context_manager=False,
                is_frozen_dataclass=False,
            )
            decl.emission_strategy = strategy
            return strategy

        # 2. Interfaces & Enums do not allocate instance `__slots__`
        if type_sym.is_interface or type_sym.is_enum:
            ps_types = (
                list(self.compute_ps_types_tuple(type_sym)) if not type_sym.is_enum else [type_sym.qualified_name]
            )
            strategy = ClassEmissionStrategy(
                kind="SlottedClass",
                py_runtime_type=type_sym.name,
                own_slots=[],
                ps_types_tuple=ps_types,
                generates_context_manager=False,
                generates_async_context_manager=False,
                is_frozen_dataclass=False,
            )
            decl.emission_strategy = strategy
            return strategy

        own_slots = self.compute_own_slots(type_sym)
        ps_types = list(self.compute_ps_types_tuple(type_sym))
        is_sync_disp = self.check_disposable_contract(type_sym)
        is_async_disp = self.check_async_disposable_contract(type_sym)

        # 3. Check if `[SchemaModel]` or inherits from `BaseModel` (Pydantic model)
        if type_sym.is_schema_model or self._inherits_schema_base(type_sym):
            strategy = ClassEmissionStrategy(
                kind="SchemaModel",
                py_runtime_type=type_sym.name,
                own_slots=[],  # Pydantic BaseModel suppresses __slots__
                ps_types_tuple=ps_types,
                generates_context_manager=is_sync_disp,
                generates_async_context_manager=is_async_disp,
                is_frozen_dataclass=False,
            )
            decl.emission_strategy = strategy
            return strategy

        # 4. Check if `[NativeCompile]` (mypyc / Cython strict class)
        if type_sym.is_native_compile:
            self._verify_native_compile_constraints(type_sym)
            strategy = ClassEmissionStrategy(
                kind="NativeCompiledClass",
                py_runtime_type=type_sym.name,
                own_slots=own_slots,
                ps_types_tuple=ps_types,
                generates_context_manager=is_sync_disp,
                generates_async_context_manager=is_async_disp,
                is_frozen_dataclass=(type_sym.kind == TypeKind.RECORD),
            )
            decl.emission_strategy = strategy
            return strategy

        # 5. Records and Structs lower to `@dataclass(slots=True, frozen=...)`
        if type_sym.kind in (TypeKind.RECORD, TypeKind.RECORD_STRUCT, TypeKind.STRUCT):
            is_frozen = type_sym.kind == TypeKind.RECORD
            strategy = ClassEmissionStrategy(
                kind="SlottedDataclass",
                py_runtime_type=type_sym.name,
                own_slots=own_slots,
                ps_types_tuple=ps_types,
                generates_context_manager=is_sync_disp,
                generates_async_context_manager=is_async_disp,
                is_frozen_dataclass=is_frozen,
            )
            decl.emission_strategy = strategy
            return strategy

        # 6. Standard PythonSharp class with automatic `__slots__` and `__ps_types__`
        strategy = ClassEmissionStrategy(
            kind="SlottedClass",
            py_runtime_type=type_sym.name,
            own_slots=own_slots,
            ps_types_tuple=ps_types,
            generates_context_manager=is_sync_disp,
            generates_async_context_manager=is_async_disp,
            is_frozen_dataclass=False,
        )
        decl.emission_strategy = strategy
        return strategy

    # ========================================================================
    # DEDUPLICATED `__slots__` COMPUTATION
    # ========================================================================

    def compute_own_slots(self, type_sym: TypeSymbol) -> list[str]:
        """
        Collects all instance fields and auto-property backing slots declared directly
        on `type_sym`, excluding any slot names already present on base classes.
        """
        inherited_slots = self._get_inherited_slots(type_sym)
        own_slots: list[str] = []
        seen: set[str] = set(inherited_slots)

        for member in type_sym.ast_node.members:
            if isinstance(member, FieldDecl):
                if "static" in member.modifiers or "extern" in member.modifiers:
                    continue
                slot_name = member.emitted_snake_name
                if slot_name and slot_name not in seen:
                    seen.add(slot_name)
                    own_slots.append(slot_name)

            elif isinstance(member, PropertyDecl):
                if "static" in member.modifiers or "extern" in member.modifiers:
                    continue
                # Computed expression-bodied properties (`public bool IsOverdrawn => Balance < 0;`)
                # have `backing_slot_name = None` and never allocate a slot.
                prop_slot = member.backing_slot_name
                if prop_slot and prop_slot not in seen:
                    seen.add(prop_slot)
                    own_slots.append(prop_slot)

        return own_slots

    def _get_inherited_slots(self, type_sym: TypeSymbol) -> set[str]:
        """Returns the union of all instance slot names declared on ancestor classes."""
        inherited: set[str] = set()
        visited: set[int] = {type_sym.id.value}
        queue = list(type_sym.base_type_symbols)

        while queue:
            base = queue.pop(0)
            if base.id.value in visited:
                continue
            visited.add(base.id.value)

            if not base.is_interface and not base.is_primitive:
                inherited.update(self._get_direct_slots(base))
                # Also include primary constructor fields if inheriting from a record
                for p in base.ast_node.primary_ctor_params:
                    if p.emitted_snake_name:
                        inherited.add(p.emitted_snake_name)

            queue.extend(base.base_type_symbols)

        return inherited

    @staticmethod
    def _get_direct_slots(type_sym: TypeSymbol) -> list[str]:
        slots: list[str] = []
        for member in type_sym.ast_node.members:
            if isinstance(member, FieldDecl) and "static" not in member.modifiers:
                if member.emitted_snake_name:
                    slots.append(member.emitted_snake_name)
            elif isinstance(member, PropertyDecl) and "static" not in member.modifiers:
                if member.backing_slot_name:
                    slots.append(member.backing_slot_name)
        return slots

    # ========================================================================
    # NOMINAL HIERARCHY METADATA (`__ps_types__`) & `IDisposable`
    # ========================================================================

    def compute_ps_types_tuple(self, type_sym: TypeSymbol) -> tuple[str, ...]:
        """
        Computes the ordered transitive closure of nominal class and interface names
        for `__ps_types__`, enabling O(1) runtime `is` / `as` checks.
        """
        result: list[str] = [type_sym.qualified_name]
        seen: set[str] = {type_sym.qualified_name}

        queue: list[TypeSymbol] = list(type_sym.base_type_symbols)

        while queue:
            cur = queue.pop(0)
            qname = cur.qualified_name
            # Skip erased primitive collection/value types unless they are nominal contracts
            if cur.is_primitive and qname not in DISPOSABLE_QNAMES and qname not in ASYNC_DISPOSABLE_QNAMES:
                continue
            if qname not in seen:
                seen.add(qname)
                result.append(qname)
            for parent in cur.base_type_symbols:
                if parent.qualified_name not in seen:
                    queue.append(parent)

        # Include unresolved/external disposable references not represented by a symbol.
        for base_ref in type_sym.base_type_refs:
            if base_ref.qualified_name in DISPOSABLE_QNAMES or base_ref.qualified_name in ASYNC_DISPOSABLE_QNAMES:
                canonical = (
                    "PythonSharp.Core.IDisposable"
                    if base_ref.qualified_name in DISPOSABLE_QNAMES
                    else "PythonSharp.Core.IAsyncDisposable"
                )
                if canonical not in seen:
                    seen.add(canonical)
                    result.append(canonical)

        return tuple(result)

    def check_disposable_contract(self, type_sym: TypeSymbol) -> bool:
        """Returns True if `type_sym` implements `IDisposable` directly or via inheritance."""
        for ref in type_sym.base_type_refs:
            if ref.qualified_name in DISPOSABLE_QNAMES:
                return True
        for base in type_sym.base_type_symbols:
            if base.qualified_name in DISPOSABLE_QNAMES or self.check_disposable_contract(base):
                return True
        return False

    def check_async_disposable_contract(self, type_sym: TypeSymbol) -> bool:
        """Returns True if `type_sym` implements `IAsyncDisposable` directly or via inheritance."""
        for ref in type_sym.base_type_refs:
            if ref.qualified_name in ASYNC_DISPOSABLE_QNAMES:
                return True
        for base in type_sym.base_type_symbols:
            if base.qualified_name in ASYNC_DISPOSABLE_QNAMES or self.check_async_disposable_contract(base):
                return True
        return False

    @staticmethod
    def _inherits_schema_base(type_sym: TypeSymbol) -> bool:
        for ref in type_sym.base_type_refs:
            if ref.qualified_name in SCHEMA_BASE_NAMES or ref.py_annotation in SCHEMA_BASE_NAMES:
                return True
        return False

    # ========================================================================
    # RULE PS004: `[NativeCompile]` DYNAMIC RESTRICTION VERIFIER
    # ========================================================================

    def _verify_native_compile_constraints(self, type_sym: TypeSymbol) -> None:
        """
        Verifies that a class marked `[NativeCompile]` does not use `dynamic`
        in any primary constructor parameter, field, property, method signature, or local variable.
        """
        for p in type_sym.ast_node.primary_ctor_params:
            if self._type_ref_contains_dynamic(p.type_ref):
                self.diagnostics.report_ps004_native_compile_dynamic(p.span, type_sym.name)

        for member in type_sym.ast_node.members:
            if isinstance(member, FieldDecl):
                if self._type_ref_contains_dynamic(member.type_ref):
                    self.diagnostics.report_ps004_native_compile_dynamic(member.span, type_sym.name)
            elif isinstance(member, PropertyDecl):
                if self._type_ref_contains_dynamic(member.type_ref):
                    self.diagnostics.report_ps004_native_compile_dynamic(member.span, type_sym.name)
            elif isinstance(member, MethodDecl):
                if member.return_type and self._type_ref_contains_dynamic(member.return_type):
                    self.diagnostics.report_ps004_native_compile_dynamic(member.return_type.span, type_sym.name)
                for p in member.params:
                    if self._type_ref_contains_dynamic(p.type_ref):
                        self.diagnostics.report_ps004_native_compile_dynamic(p.span, type_sym.name)
                if member.body is not None:
                    self._check_stmt_for_dynamic(member.body, type_sym.name)

    def _type_ref_contains_dynamic(self, tr: TypeRef) -> bool:
        if tr.path == ["dynamic"]:
            return True
        for arg in tr.type_args:
            if self._type_ref_contains_dynamic(arg):
                return True
        for elem_tr, _ in tr.tuple_elements:
            if self._type_ref_contains_dynamic(elem_tr):
                return True
        return False

    def _check_stmt_for_dynamic(self, stmt: Stmt, type_name: str) -> None:
        if isinstance(stmt, BlockStmt):
            for s in stmt.statements:
                self._check_stmt_for_dynamic(s, type_name)
        elif isinstance(stmt, LocalVarStmt):
            if stmt.type_ref and self._type_ref_contains_dynamic(stmt.type_ref):
                self.diagnostics.report_ps004_native_compile_dynamic(stmt.span, type_name)
        elif isinstance(stmt, UsingResourceStmt):
            if stmt.type_ref and self._type_ref_contains_dynamic(stmt.type_ref):
                self.diagnostics.report_ps004_native_compile_dynamic(stmt.span, type_name)
        elif isinstance(stmt, IfStmt):
            self._check_stmt_for_dynamic(stmt.then_branch, type_name)
            if stmt.else_branch:
                self._check_stmt_for_dynamic(stmt.else_branch, type_name)
        elif isinstance(stmt, WhileStmt):
            self._check_stmt_for_dynamic(stmt.body, type_name)
        elif isinstance(stmt, ForEachStmt):
            if stmt.type_ref and self._type_ref_contains_dynamic(stmt.type_ref):
                self.diagnostics.report_ps004_native_compile_dynamic(stmt.span, type_name)
            self._check_stmt_for_dynamic(stmt.body, type_name)
        elif isinstance(stmt, TryCatchFinallyStmt):
            self._check_stmt_for_dynamic(stmt.try_block, type_name)
            for c in stmt.catches:
                if c.body:
                    self._check_stmt_for_dynamic(c.body, type_name)
            if stmt.finally_block:
                self._check_stmt_for_dynamic(stmt.finally_block, type_name)
        elif isinstance(stmt, SwitchStmt):
            for sec in stmt.sections:
                for s in sec.statements:
                    self._check_stmt_for_dynamic(s, type_name)

    # ========================================================================
    # RULE PS003: CIRCULAR STATIC INITIALIZER DETECTOR
    # ========================================================================

    def _verify_no_circular_static_initializers(self, types: list[TypeSymbol]) -> None:
        """
        Detects cycles between static field/property initializers across types
        (e.g., `Config.Default` initializing from `Env.Current` while `Env.Current`
        initializes from `Config.Default`), emitting Rule PS003.
        """
        static_nodes: dict[str, tuple[SourceSpan, set[str]]] = {}

        for type_sym in types:
            if type_sym.is_ambient_stub:
                continue
            for member in type_sym.ast_node.members:
                if isinstance(member, (FieldDecl, PropertyDecl)) and "static" in member.modifiers:
                    init_expr = member.initializer
                    if isinstance(member, PropertyDecl) and init_expr is None:
                        init_expr = member.expr_body
                    if init_expr is not None:
                        key = f"{type_sym.name}.{member.name}"
                        deps = self._extract_static_member_refs(init_expr, type_sym)
                        static_nodes[key] = (member.span, deps)

        visited: set[str] = set()
        in_stack: set[str] = set()

        def dfs(node_key: str, path: list[str]) -> bool:
            if node_key in in_stack:
                cycle_start = path.index(node_key)
                cycle_path = " -> ".join([*path[cycle_start:], node_key])
                span = static_nodes[path[cycle_start]][0]
                self.diagnostics.report_ps003_circular_static_init(span, cycle_path)
                return True
            if node_key in visited or node_key not in static_nodes:
                return False

            visited.add(node_key)
            in_stack.add(node_key)
            _, deps = static_nodes[node_key]
            for dep in deps:
                if dfs(dep, [*path, node_key]):
                    in_stack.remove(node_key)
                    return True
            in_stack.remove(node_key)
            return False

        for key in static_nodes:
            if key not in visited:
                dfs(key, [])

    def _extract_static_member_refs(self, expr: Expr, current_type: TypeSymbol) -> set[str]:
        refs: set[str] = set()

        def walk(e: Expr | None) -> None:
            if e is None:
                return
            if e.kind == ExprKind.MEMBER_ACCESS:
                target = e.data.get("target")
                member_name = e.data.get("member")
                if isinstance(target, Expr) and target.kind == ExprKind.IDENT and isinstance(member_name, str):
                    target_ident = target.data.get("name")
                    if isinstance(target_ident, str):
                        refs.add(f"{target_ident}.{member_name}")
                walk(target)
            elif e.kind == ExprKind.IDENT:
                ident_name = e.data.get("name")
                if isinstance(ident_name, str):
                    # Check if referencing another static member on the same class
                    for m in current_type.lookup_member(ident_name, include_bases=False):
                        if m.is_static:
                            refs.add(f"{current_type.name}.{ident_name}")
            elif e.kind == ExprKind.CALL:
                walk(e.data.get("callee"))
                for arg in e.data.get("args", ()):
                    walk(arg.expr)
            elif e.kind in (ExprKind.BINARY, ExprKind.NULL_COALESCE):
                walk(e.data.get("left"))
                walk(e.data.get("right"))
            elif e.kind == ExprKind.UNARY:
                walk(e.data.get("operand"))
            elif e.kind == ExprKind.NEW_OBJECT:
                for arg in e.data.get("args", ()):
                    walk(arg.expr)

        walk(expr)
        return refs
