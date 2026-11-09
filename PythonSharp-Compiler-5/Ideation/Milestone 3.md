Here are the raw individual files for **Milestone 3 (Pass 2A: `slot_analyzer.py` for deduplicated `__slots__`, `__ps_types__` nominal metadata, `IDisposable` context manager synthesis, and Rules `PS003`/`PS004`; `access_checker.py` for Rule `PS001` `private`/`protected`/`internal` verification; updated `src/psc/semantics/__init__.py`; and `tests/test_access_and_slots.py`)** of the **PythonSharp Prototype Transpiler (`psc`)**.

---

##### 1. src/psc/semantics/slot_analyzer.py

```python
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
    ReturnStmt,
    Stmt,
    SwitchStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    TypeKind,
    TypeRef,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.symbols import GlobalSymbolTable, MemberSymbol, TypeSymbol


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
            ps_types = list(self.compute_ps_types_tuple(type_sym)) if not type_sym.is_enum else [type_sym.qualified_name]
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
                slot_name = member.backing_slot_name
                if slot_name and slot_name not in seen:
                    seen.add(slot_name)
                    own_slots.append(slot_name)

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
        # Also include unresolved/external interface references such as IDisposable if not in base_type_symbols
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
            if (
                base.qualified_name in ASYNC_DISPOSABLE_QNAMES
                or self.check_async_disposable_contract(base)
            ):
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
                    self.diagnostics.report_ps004_native_compile_dynamic(
                        member.return_type.span, type_sym.name
                    )
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


```

---

##### 2. src/psc/semantics/access_checker.py

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend.ast_nodes import (
    AccessMod,
    BinaryOp,
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
    TypeRef,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.semantics.symbols import (
    BUILTIN_PRIMITIVE_MAP,
    GlobalSymbolTable,
    MemberSymbol,
    ResolvedType,
    TypeSymbol,
)


ASSIGN_OPS = frozenset(
    {
        BinaryOp.ASSIGN,
        BinaryOp.ADD_ASSIGN,
        BinaryOp.SUB_ASSIGN,
        BinaryOp.MUL_ASSIGN,
        BinaryOp.DIV_ASSIGN,
        BinaryOp.NULL_COALESCE_ASSIGN,
    }
)


class AccessChecker:
    """
    Pass 2A Encapsulation Verifier (Rule PS001):
      Enforces compile-time `private`, `protected`, and `internal` (.psproj assembly-scoped)
      visibility across all type references, field accesses, property getters/setters
      (including `{ get; private set; }`), constructors, methods, and indexers.
    """

    def __init__(
        self,
        symtab: GlobalSymbolTable,
        diagnostics: DiagnosticEngine,
    ) -> None:
        self.symtab = symtab
        self.diagnostics = diagnostics

    def check_all(self, units: list[CompilationUnit]) -> None:
        """Runs encapsulation verification across all non-ambient compilation units."""
        for unit in units:
            if unit.is_ambient_stub:
                continue
            for decl in unit.types:
                if decl.symbol_id is not None and decl.symbol_id in self.symtab.types_by_id:
                    type_sym = self.symtab.types_by_id[decl.symbol_id]
                    self.check_type_decl(type_sym)

    # ========================================================================
    # CORE VISIBILITY VERIFICATION RULES (PS001)
    # ========================================================================

    def verify_type_access(
        self,
        span: SourceSpan,
        caller_type: TypeSymbol,
        target_type: TypeSymbol,
    ) -> bool:
        """Verifies that `caller_type` is permitted to reference `target_type`."""
        if target_type.is_ambient_stub or target_type.access == AccessMod.PUBLIC:
            return True

        if target_type.access == AccessMod.INTERNAL:
            if caller_type.assembly_name == target_type.assembly_name:
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=target_type.name,
                access_mod="internal",
                owner_type=".".join(target_type.namespace) or target_type.assembly_name,
            )
            return False

        if target_type.access == AccessMod.PRIVATE:
            if caller_type.id == target_type.id:
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=target_type.name,
                access_mod="private",
                owner_type=".".join(target_type.namespace) or target_type.assembly_name,
            )
            return False

        if target_type.access == AccessMod.PROTECTED:
            if caller_type.is_subclass_of(target_type.qualified_name):
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=target_type.name,
                access_mod="protected",
                owner_type=".".join(target_type.namespace) or target_type.assembly_name,
            )
            return False

        return True

    def verify_member_access(
        self,
        span: SourceSpan,
        caller_type: TypeSymbol,
        target_member: MemberSymbol,
        is_write: bool = False,
        in_constructor: bool = False,
    ) -> bool:
        """
        Verifies that `caller_type` can read (or write, if `is_write=True`) `target_member`.
        Handles `private set`, `protected set`, `internal set`, and `readonly` fields.
        """
        owner_sym = self.symtab.types_by_id.get(target_member.owner_type_id)
        if owner_sym is not None and owner_sym.is_ambient_stub:
            return True

        # 1. Check write-specific constraints (`readonly` fields and property setters)
        if is_write:
            if target_member.kind == "field" and target_member.is_readonly:
                if not (in_constructor and caller_type.id == target_member.owner_type_id):
                    self.diagnostics.report_ps001_access_violation(
                        span=span,
                        member_name=target_member.name,
                        access_mod="readonly",
                        owner_type=target_member.owner_qualified_name,
                    )
                    return False

            if target_member.kind in ("property", "indexer"):
                if target_member.setter_access is None:
                    # Read-only property (`{ get; }` or `=> expr`)
                    if not (in_constructor and caller_type.id == target_member.owner_type_id):
                        self.diagnostics.report_ps001_access_violation(
                            span=span,
                            member_name=f"{target_member.name}.set",
                            access_mod="private (read-only)",
                            owner_type=target_member.owner_qualified_name,
                        )
                        return False
                    effective_access = AccessMod.PRIVATE
                else:
                    effective_access = target_member.setter_access
                member_label = f"{target_member.name}.set"
            else:
                effective_access = target_member.access
                member_label = target_member.name
        else:
            effective_access = target_member.access
            member_label = target_member.name

        # 2. Evaluate effective AccessMod against caller context
        if effective_access == AccessMod.PUBLIC:
            return True

        if effective_access == AccessMod.PRIVATE:
            if caller_type.id == target_member.owner_type_id:
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=member_label,
                access_mod="private",
                owner_type=target_member.owner_qualified_name,
            )
            return False

        if effective_access == AccessMod.PROTECTED:
            if caller_type.is_subclass_of(target_member.owner_qualified_name):
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=member_label,
                access_mod="protected",
                owner_type=target_member.owner_qualified_name,
            )
            return False

        if effective_access == AccessMod.INTERNAL:
            if owner_sym is None or caller_type.assembly_name == owner_sym.assembly_name:
                return True
            self.diagnostics.report_ps001_access_violation(
                span=span,
                member_name=member_label,
                access_mod="internal",
                owner_type=target_member.owner_qualified_name,
            )
            return False

        return True

    # ========================================================================
    # AST TRAVERSAL & LOCAL TYPE ENVIRONMENT TRACKING
    # ========================================================================

    def check_type_decl(self, type_sym: TypeSymbol) -> None:
        decl = type_sym.ast_node
        active_tparams = set(type_sym.type_params)

        # Verify base type accessibility
        for base_sym in type_sym.base_type_symbols:
            self.verify_type_access(decl.span, type_sym, base_sym)

        # Verify primary constructor parameter types
        for p in decl.primary_ctor_params:
            self._check_type_ref_access(p.type_ref, type_sym, active_tparams)
            if p.default_value is not None:
                self._check_expr(p.default_value, type_sym, {}, in_constructor=True)

        # Verify all members
        for member in decl.members:
            if isinstance(member, FieldDecl):
                self._check_type_ref_access(member.type_ref, type_sym, active_tparams)
                if member.initializer is not None:
                    self._check_expr(
                        member.initializer,
                        type_sym,
                        {},
                        in_constructor=("static" not in member.modifiers),
                    )

            elif isinstance(member, PropertyDecl):
                self._check_type_ref_access(member.type_ref, type_sym, active_tparams)
                if member.initializer is not None:
                    self._check_expr(member.initializer, type_sym, {}, in_constructor=True)
                if member.expr_body is not None:
                    self._check_expr(member.expr_body, type_sym, {}, in_constructor=False)
                for acc in member.accessors:
                    prop_ty = self.symtab.resolve_type_ref(
                        member.type_ref,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=active_tparams,
                    )
                    env = {"value": prop_ty} if acc.kind == "set" else {}
                    if acc.body is not None:
                        self._check_stmt(acc.body, type_sym, env, in_constructor=False)
                    if acc.expr_body is not None:
                        self._check_expr(acc.expr_body, type_sym, env, in_constructor=False)

            elif isinstance(member, IndexerDecl):
                self._check_type_ref_access(member.type_ref, type_sym, active_tparams)
                base_env: dict[str, ResolvedType] = {}
                for p in member.params:
                    self._check_type_ref_access(p.type_ref, type_sym, active_tparams)
                    base_env[p.name] = self.symtab.resolve_type_ref(
                        p.type_ref,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=active_tparams,
                    )
                idx_ty = self.symtab.resolve_type_ref(
                    member.type_ref,
                    current_ns=type_sym.namespace,
                    imports=type_sym.unit.imports,
                    active_type_params=active_tparams,
                )
                for acc in member.accessors:
                    env = dict(base_env)
                    if acc.kind == "set":
                        env["value"] = idx_ty
                    if acc.body is not None:
                        self._check_stmt(acc.body, type_sym, env, in_constructor=False)
                    if acc.expr_body is not None:
                        self._check_expr(acc.expr_body, type_sym, env, in_constructor=False)

            elif isinstance(member, MethodDecl):
                method_tparams = active_tparams | set(member.type_params)
                if member.return_type is not None:
                    self._check_type_ref_access(member.return_type, type_sym, method_tparams)

                env = {}
                for p in member.params:
                    self._check_type_ref_access(p.type_ref, type_sym, method_tparams)
                    p_ty = self.symtab.resolve_type_ref(
                        p.type_ref,
                        current_ns=type_sym.namespace,
                        imports=type_sym.unit.imports,
                        active_type_params=method_tparams,
                    )
                    env[p.name] = p_ty
                    if p.default_value is not None:
                        self._check_expr(
                            p.default_value,
                            type_sym,
                            env,
                            in_constructor=member.is_constructor,
                        )

                if member.ctor_chain is not None:
                    for arg in member.ctor_chain.args:
                        self._check_expr(arg.expr, type_sym, env, in_constructor=True)

                if member.body is not None:
                    self._check_stmt(
                        member.body, type_sym, env, in_constructor=member.is_constructor
                    )
                if member.expr_body is not None:
                    self._check_expr(
                        member.expr_body, type_sym, env, in_constructor=member.is_constructor
                    )

    def _check_type_ref_access(
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
            target_sym = self.symtab.types_by_id[resolved.symbol_id]
            self.verify_type_access(type_ref.span, caller_type, target_sym)

        for arg in type_ref.type_args:
            self._check_type_ref_access(arg, caller_type, active_tparams)
        for elem_tr, _ in type_ref.tuple_elements:
            self._check_type_ref_access(elem_tr, caller_type, active_tparams)

    def _check_stmt(
        self,
        stmt: Stmt,
        caller_type: TypeSymbol,
        env: dict[str, ResolvedType],
        in_constructor: bool,
    ) -> None:
        if isinstance(stmt, BlockStmt):
            inner_env = dict(env)
            for s in stmt.statements:
                self._check_stmt(s, caller_type, inner_env, in_constructor)

        elif isinstance(stmt, LocalVarStmt):
            if stmt.type_ref is not None:
                self._check_type_ref_access(
                    stmt.type_ref, caller_type, set(caller_type.type_params)
                )
            init_ty = self._check_expr(stmt.initializer, caller_type, env, in_constructor)
            if stmt.type_ref is not None:
                decl_ty = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
                env[stmt.name] = decl_ty
            elif init_ty is not None:
                env[stmt.name] = init_ty

        elif isinstance(stmt, UsingResourceStmt):
            if stmt.type_ref is not None:
                self._check_type_ref_access(
                    stmt.type_ref, caller_type, set(caller_type.type_params)
                )
            init_ty = self._check_expr(stmt.initializer, caller_type, env, in_constructor)
            if stmt.type_ref is not None:
                env[stmt.name] = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
            elif init_ty is not None:
                env[stmt.name] = init_ty

        elif isinstance(stmt, IfStmt):
            self._check_expr(stmt.condition, caller_type, env, in_constructor)
            self._check_stmt(stmt.then_branch, caller_type, dict(env), in_constructor)
            if stmt.else_branch is not None:
                self._check_stmt(stmt.else_branch, caller_type, dict(env), in_constructor)

        elif isinstance(stmt, WhileStmt):
            self._check_expr(stmt.condition, caller_type, env, in_constructor)
            self._check_stmt(stmt.body, caller_type, dict(env), in_constructor)

        elif isinstance(stmt, ForEachStmt):
            coll_ty = self._check_expr(stmt.collection, caller_type, env, in_constructor)
            loop_env = dict(env)
            if stmt.type_ref is not None:
                self._check_type_ref_access(
                    stmt.type_ref, caller_type, set(caller_type.type_params)
                )
                loop_env[stmt.item_name] = self.symtab.resolve_type_ref(
                    stmt.type_ref,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                )
            elif coll_ty is not None and coll_ty.type_args:
                loop_env[stmt.item_name] = coll_ty.type_args[0]
            self._check_stmt(stmt.body, caller_type, loop_env, in_constructor)

        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                self._check_expr(stmt.value, caller_type, env, in_constructor)

        elif isinstance(stmt, YieldStmt):
            if stmt.value is not None:
                self._check_expr(stmt.value, caller_type, env, in_constructor)

        elif isinstance(stmt, ThrowStmt):
            if stmt.exception is not None:
                self._check_expr(stmt.exception, caller_type, env, in_constructor)

        elif isinstance(stmt, TryCatchFinallyStmt):
            self._check_stmt(stmt.try_block, caller_type, dict(env), in_constructor)
            for catch in stmt.catches:
                catch_env = dict(env)
                if catch.exception_type is not None:
                    self._check_type_ref_access(
                        catch.exception_type, caller_type, set(caller_type.type_params)
                    )
                    if catch.bind_name:
                        catch_env[catch.bind_name] = self.symtab.resolve_type_ref(
                            catch.exception_type,
                            current_ns=caller_type.namespace,
                            imports=caller_type.unit.imports,
                            active_type_params=set(caller_type.type_params),
                        )
                if catch.when_guard is not None:
                    self._check_expr(catch.when_guard, caller_type, catch_env, in_constructor)
                if catch.body is not None:
                    self._check_stmt(catch.body, caller_type, catch_env, in_constructor)
            if stmt.finally_block is not None:
                self._check_stmt(stmt.finally_block, caller_type, dict(env), in_constructor)

        elif isinstance(stmt, SwitchStmt):
            self._check_expr(stmt.scrutinee, caller_type, env, in_constructor)
            for sec in stmt.sections:
                sec_env = dict(env)
                for pat, guard in sec.labels:
                    if pat is not None and pat.type_ref is not None:
                        self._check_type_ref_access(
                            pat.type_ref, caller_type, set(caller_type.type_params)
                        )
                        if pat.bind_name:
                            sec_env[pat.bind_name] = self.symtab.resolve_type_ref(
                                pat.type_ref,
                                current_ns=caller_type.namespace,
                                imports=caller_type.unit.imports,
                                active_type_params=set(caller_type.type_params),
                            )
                    if guard is not None:
                        self._check_expr(guard, caller_type, sec_env, in_constructor)
                for s in sec.statements:
                    self._check_stmt(s, caller_type, sec_env, in_constructor)

        elif isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr, caller_type, env, in_constructor)

    def _check_expr(
        self,
        expr: Expr | None,
        caller_type: TypeSymbol,
        env: dict[str, ResolvedType],
        in_constructor: bool,
        is_write_target: bool = False,
    ) -> ResolvedType | None:
        if expr is None:
            return None

        kind = expr.kind

        if kind == ExprKind.LITERAL:
            lit_kind = expr.data.get("literal_kind")
            lit_map = {
                LiteralKind.INT: "int",
                LiteralKind.FLOAT: "double",
                LiteralKind.DECIMAL: "decimal",
                LiteralKind.STRING: "string",
                LiteralKind.BOOL: "bool",
            }
            if lit_kind in lit_map:
                qname, py_ann, rt = BUILTIN_PRIMITIVE_MAP[lit_map[lit_kind]]
                sym = self.symtab.types_by_qname.get(qname)
                return ResolvedType(
                    qualified_name=qname,
                    py_annotation=py_ann,
                    runtime_isinstance_type=rt,
                    symbol_id=sym.id if sym else None,
                    is_primitive=True,
                )
            return None

        if kind == ExprKind.THIS:
            return ResolvedType(
                qualified_name=caller_type.qualified_name,
                py_annotation=caller_type.name,
                runtime_isinstance_type=caller_type.name,
                symbol_id=caller_type.id,
            )

        if kind == ExprKind.BASE:
            if caller_type.base_type_symbols:
                base_sym = caller_type.base_type_symbols[0]
                return ResolvedType(
                    qualified_name=base_sym.qualified_name,
                    py_annotation=base_sym.name,
                    runtime_isinstance_type=base_sym.name,
                    symbol_id=base_sym.id,
                )
            return None

        if kind == ExprKind.IDENT:
            name = str(expr.data.get("name", ""))
            # 1. Local variable or parameter in scope
            if name in env:
                return env[name]
            # 2. Implicit `this.<Member>` access on current class or base classes
            members = caller_type.lookup_member(name, include_bases=True)
            if members:
                target_member = members[0]
                self.verify_member_access(
                    expr.span,
                    caller_type,
                    target_member,
                    is_write=is_write_target,
                    in_constructor=in_constructor,
                )
                return target_member.resolved_type
            # 3. Type identifier for static member access (`OrderCache.StaticMethod()`)
            type_sym = self.symtab.lookup_type_in_context(
                [name], caller_type.namespace, caller_type.unit.imports
            )
            if type_sym is not None:
                self.verify_type_access(expr.span, caller_type, type_sym)
                return ResolvedType(
                    qualified_name=type_sym.qualified_name,
                    py_annotation=type_sym.name,
                    runtime_isinstance_type=type_sym.name,
                    symbol_id=type_sym.id,
                )
            return None

        if kind in (ExprKind.MEMBER_ACCESS, ExprKind.NULL_COND_ACCESS):
            target_expr: Expr | None = expr.data.get("target")
            member_name: str = str(expr.data.get("member", ""))
            target_ty = self._check_expr(
                target_expr, caller_type, env, in_constructor, is_write_target=False
            )
            if target_ty is not None and target_ty.symbol_id is not None:
                owner_sym = self.symtab.types_by_id.get(target_ty.symbol_id)
                if owner_sym is not None:
                    members = owner_sym.lookup_member(member_name, include_bases=True)
                    if members:
                        target_member = members[0]
                        self.verify_member_access(
                            expr.span,
                            caller_type,
                            target_member,
                            is_write=is_write_target,
                            in_constructor=in_constructor,
                        )
                        return target_member.resolved_type
            return None

        if kind == ExprKind.BINARY:
            op: BinaryOp = expr.data["op"]
            left: Expr = expr.data["left"]
            right: Expr = expr.data["right"]
            is_assign = op in ASSIGN_OPS
            left_ty = self._check_expr(
                left, caller_type, env, in_constructor, is_write_target=is_assign
            )
            self._check_expr(right, caller_type, env, in_constructor, is_write_target=False)
            return left_ty

        if kind == ExprKind.NULL_COALESCE:
            left_ty = self._check_expr(expr.data.get("left"), caller_type, env, in_constructor)
            right_ty = self._check_expr(expr.data.get("right"), caller_type, env, in_constructor)
            return right_ty or left_ty

        if kind == ExprKind.UNARY:
            return self._check_expr(expr.data.get("operand"), caller_type, env, in_constructor)

        if kind == ExprKind.CALL:
            callee: Expr = expr.data["callee"]
            args = expr.data.get("args", ())
            for arg in args:
                self._check_expr(arg.expr, caller_type, env, in_constructor)
            return self._check_expr(callee, caller_type, env, in_constructor)

        if kind == ExprKind.NEW_OBJECT:
            type_ref: TypeRef = expr.data["type_ref"]
            self._check_type_ref_access(type_ref, caller_type, set(caller_type.type_params))
            resolved_ty = self.symtab.resolve_type_ref(
                type_ref,
                current_ns=caller_type.namespace,
                imports=caller_type.unit.imports,
                active_type_params=set(caller_type.type_params),
            )
            args = expr.data.get("args", ())
            for arg in args:
                self._check_expr(arg.expr, caller_type, env, in_constructor)

            # Check constructor accessibility if the type has explicit constructors
            if resolved_ty.symbol_id is not None and resolved_ty.symbol_id in self.symtab.types_by_id:
                inst_sym = self.symtab.types_by_id[resolved_ty.symbol_id]
                ctors = [
                    m
                    for m in inst_sym.lookup_member(inst_sym.name, include_bases=False)
                    if m.kind == "constructor"
                ]
                if ctors:
                    # Pick matching arity constructor if overloaded, or first constructor
                    matching = [
                        c for c in ctors if c.min_arity <= len(args) <= c.max_arity
                    ] or ctors
                    if not any(self._can_access_quietly(caller_type, c) for c in matching):
                        self.verify_member_access(
                            expr.span, caller_type, matching[0], is_write=False
                        )

                # Also check object initializer property writes (`new Order { Total = 10m }`)
                for prop_name, init_val_expr in expr.data.get("initializers", ()):
                    self._check_expr(init_val_expr, caller_type, env, in_constructor)
                    props = inst_sym.lookup_member(prop_name, include_bases=True)
                    if props:
                        self.verify_member_access(
                            expr.span, caller_type, props[0], is_write=True
                        )

            return resolved_ty

        if kind == ExprKind.INDEX_OR_SLICE:
            target_ty = self._check_expr(
                expr.data.get("target"), caller_type, env, in_constructor
            )
            for dim in expr.data.get("dimensions", ()):
                if dim.single_expr is not None:
                    self._check_expr(dim.single_expr, caller_type, env, in_constructor)
                if dim.start is not None:
                    self._check_expr(dim.start, caller_type, env, in_constructor)
                if dim.stop is not None:
                    self._check_expr(dim.stop, caller_type, env, in_constructor)
                if dim.step is not None:
                    self._check_expr(dim.step, caller_type, env, in_constructor)
            if target_ty is not None and target_ty.symbol_id is not None:
                owner_sym = self.symtab.types_by_id.get(target_ty.symbol_id)
                if owner_sym is not None:
                    idx_members = owner_sym.lookup_member("this[]", include_bases=True)
                    if idx_members:
                        self.verify_member_access(
                            expr.span,
                            caller_type,
                            idx_members[0],
                            is_write=is_write_target,
                            in_constructor=in_constructor,
                        )
                        return idx_members[0].resolved_type
            return None

        if kind == ExprKind.INTERP_STRING:
            for part in expr.data.get("parts", ()):
                if part.is_expr and part.expr is not None:
                    self._check_expr(part.expr, caller_type, env, in_constructor)
            qname, py_ann, rt = BUILTIN_PRIMITIVE_MAP["string"]
            return ResolvedType(qualified_name=qname, py_annotation=py_ann, runtime_isinstance_type=rt, is_primitive=True)

        if kind in (ExprKind.LIST_LITERAL, ExprKind.TUPLE_LITERAL):
            for el in expr.data.get("elements", ()):
                self._check_expr(el, caller_type, env, in_constructor)
            return None

        if kind == ExprKind.TYPE_CHECK_IS:
            self._check_expr(expr.data.get("target"), caller_type, env, in_constructor)
            pat = expr.data.get("pattern")
            if pat is not None and pat.type_ref is not None:
                self._check_type_ref_access(
                    pat.type_ref, caller_type, set(caller_type.type_params)
                )
            return None

        if kind == ExprKind.TYPE_CAST_AS:
            self._check_expr(expr.data.get("target"), caller_type, env, in_constructor)
            tr: TypeRef | None = expr.data.get("type_ref")
            if tr is not None:
                self._check_type_ref_access(tr, caller_type, set(caller_type.type_params))
                return self.symtab.resolve_type_ref(
                    tr,
                    current_ns=caller_type.namespace,
                    imports=caller_type.unit.imports,
                    active_type_params=set(caller_type.type_params),
                ).with_nullable(True)
            return None

        if kind == ExprKind.LAMBDA:
            lam_env = dict(env)
            for lp in expr.data.get("params", ()):
                if lp.type_ref is not None:
                    lam_env[lp.name] = self.symtab.resolve_type_ref(
                        lp.type_ref,
                        current_ns=caller_type.namespace,
                        imports=caller_type.unit.imports,
                        active_type_params=set(caller_type.type_params),
                    )
            body = expr.data.get("body")
            if isinstance(body, Expr):
                self._check_expr(body, caller_type, lam_env, in_constructor=False)
            elif isinstance(body, BlockStmt):
                self._check_stmt(body, caller_type, lam_env, in_constructor=False)
            return None

        if kind == ExprKind.SWITCH_EXPR:
            self._check_expr(expr.data.get("scrutinee"), caller_type, env, in_constructor)
            for arm in expr.data.get("arms", ()):
                arm_env = dict(env)
                if arm.pattern.type_ref is not None:
                    self._check_type_ref_access(
                        arm.pattern.type_ref, caller_type, set(caller_type.type_params)
                    )
                    if arm.pattern.bind_name:
                        arm_env[arm.pattern.bind_name] = self.symtab.resolve_type_ref(
                            arm.pattern.type_ref,
                            current_ns=caller_type.namespace,
                            imports=caller_type.unit.imports,
                            active_type_params=set(caller_type.type_params),
                        )
                if arm.when_guard is not None:
                    self._check_expr(arm.when_guard, caller_type, arm_env, in_constructor)
                self._check_expr(arm.result_expr, caller_type, arm_env, in_constructor)
            return None

        return None

    def _can_access_quietly(self, caller_type: TypeSymbol, member: MemberSymbol) -> bool:
        if member.access == AccessMod.PUBLIC:
            return True
        if member.access == AccessMod.PRIVATE:
            return caller_type.id == member.owner_type_id
        if member.access == AccessMod.PROTECTED:
            return caller_type.is_subclass_of(member.owner_qualified_name)
        if member.access == AccessMod.INTERNAL:
            owner_sym = self.symtab.types_by_id.get(member.owner_type_id)
            return owner_sym is None or caller_type.assembly_name == owner_sym.assembly_name
        return True


```

---

##### 3. src/psc/semantics/**init**.py

```python
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

__all__ = [
    "BUILTIN_PRIMITIVE_MAP",
    "GlobalSymbolTable",
    "MemberSymbol",
    "ResolvedType",
    "TypeSymbol",
    "SymbolCollector",
    "SlotAndHierarchyAnalyzer",
    "AccessChecker",
    "namespace_to_module_path",
    "pascal_to_snake",
]


```

---

##### 4. tests/test_access_and_slots.py

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine
from psc.frontend import Parser
from psc.semantics import (
    AccessChecker,
    GlobalSymbolTable,
    SlotAndHierarchyAnalyzer,
    SymbolCollector,
)


STDLIB_STUB = """
namespace PythonSharp.Core;

[MapsTo("contextlib.AbstractContextManager")]
public interface IDisposable
{
    [MapsTo("dispose")]
    void Dispose();
}

[MapsTo("contextlib.AbstractAsyncContextManager")]
public interface IAsyncDisposable
{
    [MapsTo("dispose_async")]
    void DisposeAsync();
}

[MapsTo("dict")]
[RuntimeType("dict")]
public primitive class Dict<TKey, TValue>
{
    [InlineTemplate("{}")]
    public extern Dict();
}
"""


def test_deduplicated_slots_nominal_ps_types_and_disposable_context_manager() -> None:
    """
    Verifies Pass 2A `SlotAndHierarchyAnalyzer`:
      1. Base class `BaseEntity` gets `own_slots = ["_id", "_created_by"]`.
      2. Subclass `Account` inherits from `BaseEntity` and implements `IAuditable` + `IDisposable`:
         - `own_slots` excludes `_id` and `_created_by` (preventing CPython slot collision!),
           contains `_balance` and `_audit_tag`, and excludes computed property `IsOverdrawn`.
         - `ps_types_tuple` includes `Account`, `BaseEntity`, `IAuditable`, and `IDisposable`.
         - `generates_context_manager` is set to `True`.
      3. Record `OrderDto` lowers to `SlottedDataclass(is_frozen_dataclass=True)`.
      4. Primitive `Dict` lowers to `ErasedPrimitive`.
    """
    source = """
    namespace Commerce.Domain;

    using PythonSharp.Core;

    public interface IAuditable
    {
        string AuditTag { get; }
    }

    public record OrderDto(int Id, decimal Amount);

    public class BaseEntity
    {
        private readonly string _id;
        public string CreatedBy { get; protected set; }

        public BaseEntity(string id, string createdBy)
        {
            _id = id;
            CreatedBy = createdBy;
        }
    }

    public class Account : BaseEntity, IAuditable, IDisposable
    {
        private readonly string _id; // Redeclared shadow field must be deduplicated!
        public decimal Balance { get; private set; } = 0.0m;
        public string AuditTag { get; private set; }

        // Expression-bodied computed property: must NOT allocate a slot!
        public bool IsOverdrawn => Balance < 0.0m;

        public Account(string id, string createdBy, string tag) : base(id, createdBy)
        {
            AuditTag = tag;
        }

        public void Dispose() { }
    }
    """
    diag = DiagnosticEngine()
    unit_std = Parser.from_source(
        STDLIB_STUB, file_id=0, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_dom = Parser.from_source(
        source, file_id=1, ps_filename="Domain/Account.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable(default_assembly_name="CommerceApp")
    SymbolCollector(symtab, diag).collect_all([unit_std, unit_dom])
    SlotAndHierarchyAnalyzer(symtab, diag).analyze_all([unit_std, unit_dom])

    assert not diag.has_errors(), diag.format_all()

    # 1. Primitive Dict is erased
    dict_sym = symtab.types_by_qname["PythonSharp.Core.Dict"]
    assert dict_sym.ast_node.emission_strategy.kind == "ErasedPrimitive"
    assert dict_sym.ast_node.emission_strategy.py_runtime_type == "dict"

    # 2. Record OrderDto is a frozen slotted dataclass
    order_sym = symtab.types_by_qname["Commerce.Domain.OrderDto"]
    assert order_sym.ast_node.emission_strategy.kind == "SlottedDataclass"
    assert order_sym.ast_node.emission_strategy.is_frozen_dataclass is True

    # 3. BaseEntity slots
    base_sym = symtab.types_by_qname["Commerce.Domain.BaseEntity"]
    base_strat = base_sym.ast_node.emission_strategy
    assert base_strat.kind == "SlottedClass"
    assert base_strat.own_slots == ["_id", "_created_by"]
    assert base_strat.generates_context_manager is False

    # 4. Subclass Account deduplicated slots, __ps_types__, and IDisposable context manager
    acc_sym = symtab.types_by_qname["Commerce.Domain.Account"]
    acc_strat = acc_sym.ast_node.emission_strategy
    assert acc_strat.kind == "SlottedClass"
    assert acc_strat.own_slots == ["_balance", "_audit_tag"]
    assert "_id" not in acc_strat.own_slots
    assert "_is_overdrawn" not in acc_strat.own_slots
    assert acc_strat.ps_types_tuple == [
        "Commerce.Domain.Account",
        "Commerce.Domain.BaseEntity",
        "Commerce.Domain.IAuditable",
        "PythonSharp.Core.IDisposable",
    ]
    assert acc_strat.generates_context_manager is True


def test_ps001_private_and_protected_member_enforcement() -> None:
    """
    Verifies Rule PS001:
      - `SavingsAccount` (subclass of `Account`) CAN write `CreatedBy` (`protected set`),
        CANNOT read `_secretPin` (`private`), and CANNOT write `Balance` (`private set`).
      - `ExternalCheckout` (unrelated class) CANNOT write `Balance` (`private set`)
        and CANNOT write `CreatedBy` (`protected set`), but CAN read `Balance` (`public`).
    """
    source = """
    namespace Commerce.Domain;

    public class Account
    {
        private string _secretPin = "1234";
        public decimal Balance { get; private set; } = 0.0m;
        public string CreatedBy { get; protected set; } = "System";

        public void Deposit(decimal amount)
        {
            // Legal inside declaring class:
            Balance = Balance + amount;
            _secretPin = "9999";
        }
    }

    public class SavingsAccount : Account
    {
        public void Upgrade(string officer)
        {
            // Legal in subclass (`protected set`):
            CreatedBy = officer;

            // ILLEGAL in subclass (`private set` on Balance):
            Balance = 100.0m;

            // ILLEGAL in subclass (`private` field `_secretPin`):
            var pin = _secretPin;
        }
    }

    public class ExternalCheckout
    {
        public void Process(Account acc)
        {
            // Legal public read:
            var current = acc.Balance;

            // ILLEGAL outside declaring class (`private set`):
            acc.Balance = 500.0m;

            // ILLEGAL outside hierarchy (`protected set`):
            acc.CreatedBy = "Hacker";
        }
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="AccessTest.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable(default_assembly_name="CommerceApp")
    SymbolCollector(symtab, diag).collect_all([unit])
    AccessChecker(symtab, diag).check_all([unit])

    assert diag.has_errors()
    errors = [d for d in diag.diagnostics if d.code == "PS001"]
    assert len(errors) == 4

    messages = "\n".join(str(e) for e in errors)
    assert "Commerce.Domain.Account.Balance.set' is 'private'" in messages
    assert "Commerce.Domain.Account._secretPin' is 'private'" in messages
    assert "Commerce.Domain.Account.CreatedBy.set' is 'protected'" in messages


def test_ps001_internal_assembly_boundary_enforcement() -> None:
    """
    Verifies that `internal` members are accessible within the same `.psproj` assembly
    (`Commerce.Core`), but emit Rule PS001 when accessed from a different assembly
    (`Commerce.ExternalPlugin`).
    """
    core_source = """
    namespace Commerce.Core;

    public class Ledger
    {
        internal void ReconcileInternal() { }
    }

    public class InternalService
    {
        public void Run(Ledger ledger)
        {
            // Legal within same assembly 'Commerce.Core':
            ledger.ReconcileInternal();
        }
    }
    """

    plugin_source = """
    namespace Commerce.Plugin;

    using Commerce.Core;

    public class PluginRunner
    {
        public void Execute(Ledger ledger)
        {
            // ILLEGAL across assembly boundary ('Commerce.Plugin' != 'Commerce.Core'):
            ledger.ReconcileInternal();
        }
    }
    """
    diag = DiagnosticEngine()
    unit_core = Parser.from_source(
        core_source, file_id=1, ps_filename="Core/Ledger.ps", diagnostics=diag
    ).parse_compilation_unit()
    unit_plugin = Parser.from_source(
        plugin_source, file_id=2, ps_filename="Plugin/PluginRunner.ps", diagnostics=diag
    ).parse_compilation_unit()

    symtab = GlobalSymbolTable()
    collector = SymbolCollector(symtab, diag)
    collector.collect_all([unit_core], assembly_name="Commerce.Core")
    collector.collect_all([unit_plugin], assembly_name="Commerce.Plugin")

    AccessChecker(symtab, diag).check_all([unit_core, unit_plugin])

    assert diag.has_errors()
    errors = [d for d in diag.diagnostics if d.code == "PS001"]
    assert len(errors) == 1
    assert "Ledger.ReconcileInternal' is 'internal'" in errors[0].message
    assert errors[0].span.ps_filename == "Plugin/PluginRunner.ps"


def test_ps003_circular_static_initializer_and_ps004_native_compile_dynamic() -> None:
    """
    Verifies Rules PS003 (circular static initializer cycle across classes)
    and PS004 (`[NativeCompile]` class using `dynamic`).
    """
    source = """
    namespace PerfAndCycles;

    public class Config
    {
        public static string Default = Env.Current;
    }

    public class Env
    {
        public static string Current = Config.Default;
    }

    [NativeCompile]
    public class FastMatrix
    {
        public dynamic Compute(int x) => x;
    }
    """
    diag = DiagnosticEngine()
    unit = Parser.from_source(source, ps_filename="DiagnosticsTest.ps", diagnostics=diag).parse_compilation_unit()
    symtab = GlobalSymbolTable()
    SymbolCollector(symtab, diag).collect_all([unit])
    SlotAndHierarchyAnalyzer(symtab, diag).analyze_all([unit])

    codes = {d.code for d in diag.diagnostics}
    assert "PS003" in codes
    assert "PS004" in codes


```

---

Shall we continue with the raw individual files for **Milestone 4 (Pass 2B: `primitive_resolver.py` for `[MapsTo]` and `[InlineTemplate]` type erasure, `overload_resolver.py` for `@overload` dispatch table synthesis and Rule `PS002` runtime collision detection, `linq_fuser.py` for `.Where().Select().ToList()` comprehension fusion, `type_checker.py`, and `tests/test_overloads_and_linq.py`)**?
