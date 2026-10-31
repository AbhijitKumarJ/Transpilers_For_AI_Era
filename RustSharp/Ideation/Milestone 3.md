Here are the complete, raw individual source files for **Milestone 3 (Pass 2A: `src/semantics/archetype_analyzer.rs`, `src/semantics/hierarchy_lowerer.rs`, `src/semantics/overload_resolver.rs`, updated `src/semantics/mod.rs` and `src/lib.rs`, and `tests/m3_polymorphism_overload_tests.rs`)** of the **RustSharp Prototype Transpiler (`rsharpc`)**.

---

### `src/semantics/archetype_analyzer.rs`

```rust
use std::collections::HashMap;

use crate::diagnostics::DiagnosticEngine;
use crate::frontend::ast::{
    AccessMod, Block, BorrowMode, CompilationUnit, Expr, ExprKind, FieldStorageMode, ImportDecl,
    LambdaBody, MemberDecl, Stmt, SymbolId, TypeDecl, TypeKind, TypeRef,
};
use crate::semantics::symbols::GlobalSymbolTable;

/// Pass 2A Archetype, Storage Mode & Encapsulation Analyzer.
///
/// Responsibilities:
/// 1. Classifies `service class` fields/properties as `FieldStorageMode::ArcShared` (readonly)
///    and `shared class` fields/properties as `FieldStorageMode::RwLockShared`.
/// 2. Detects `IDisposable` implementation or `Dispose()` methods and sets
///    `has_disposable_drop = true` so Pass 3 emits `impl Drop`.
/// 3. Sets initial receiver borrow modes (`&self` for `service class` and `shared class`).
/// 4. Enforces compile-time `private` and `protected` encapsulation across member accesses.
pub fn analyze_archetypes(
    units: &mut [CompilationUnit],
    symtab: &mut GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    // Step 1: Decorate archetype storage modes, default self borrows, and IDisposable Drop flags
    for unit in units.iter_mut() {
        for type_decl in &mut unit.types {
            configure_type_archetype(type_decl, symtab);
        }
    }

    // Step 2: Verify member access modifiers (`private`, `protected`, `internal`) across method bodies
    for unit in units.iter() {
        if unit.is_ambient_stub {
            continue;
        }
        for type_decl in &unit.types {
            check_type_encapsulation(type_decl, &unit.namespace, &unit.imports, symtab, diag);
        }
    }
}

fn configure_type_archetype(type_decl: &mut TypeDecl, symtab: &mut GlobalSymbolTable) {
    let is_service = matches!(type_decl.kind, TypeKind::ServiceClass);
    let is_shared = matches!(type_decl.kind, TypeKind::SharedClass);
    let is_value_copy = matches!(
        type_decl.kind,
        TypeKind::ValueStruct
            | TypeKind::Record { is_struct: true }
            | TypeKind::Enum
            | TypeKind::PrimitiveClass { is_struct: true }
    );

    let mut implements_disposable = type_decl
        .base_types
        .iter()
        .any(|b| b.short_name() == "IDisposable");

    for member in &mut type_decl.members {
        match member {
            MemberDecl::Field(field) => {
                let mode = if is_service {
                    field.is_readonly = true;
                    FieldStorageMode::ArcShared
                } else if is_shared {
                    FieldStorageMode::RwLockShared
                } else if is_service_type_ref(&field.ty, symtab) {
                    FieldStorageMode::ArcShared
                } else {
                    FieldStorageMode::Plain
                };
                field.resolved_storage = mode;

                if let Some(f_sym) = symtab.fields.get_mut(&field.id) {
                    f_sym.storage_mode = mode;
                    f_sym.is_readonly = field.is_readonly;
                }
            }

            MemberDecl::Property(prop) => {
                let mode = if is_service {
                    FieldStorageMode::ArcShared
                } else if is_shared {
                    FieldStorageMode::RwLockShared
                } else {
                    FieldStorageMode::Plain
                };
                prop.resolved_storage = mode;

                if let Some(p_sym) = symtab.properties.get_mut(&prop.id) {
                    p_sym.storage_mode = mode;
                }
            }

            MemberDecl::Method(method) => {
                if method.name == "Dispose" && method.params.is_empty() {
                    implements_disposable = true;
                    if method.inferred_self_borrow == BorrowMode::Unresolved {
                        method.inferred_self_borrow = BorrowMode::MutBorrow;
                    }
                }

                // Service classes and shared classes always take `&self` (`ReadBorrow`)
                // because service state is immutable and shared state uses interior mutability (`RwLock`).
                if !method.is_static && method.inferred_self_borrow == BorrowMode::Unresolved {
                    if is_service || is_shared {
                        method.inferred_self_borrow = BorrowMode::ReadBorrow;
                    }
                }

                // Mark parameters whose types are `service class` as `SharedArc` (`Arc<T>`)
                // or `Copy` value structs as `CopyValue` if not explicitly constrained.
                for param in &mut method.params {
                    if param.inferred_borrow == BorrowMode::Unresolved {
                        if let Some(explicit) = param.explicit_constraint {
                            param.inferred_borrow = explicit;
                        } else if is_copy_type_ref(&param.ty, symtab) {
                            param.inferred_borrow = BorrowMode::CopyValue;
                        }
                    }
                }

                if let Some(m_sym) = symtab.methods.get_mut(&method.id) {
                    m_sym.inferred_self_borrow = method.inferred_self_borrow;
                    for (idx, p) in method.params.iter().enumerate() {
                        if let Some(ps) = m_sym.params.get_mut(idx) {
                            ps.inferred_borrow = p.inferred_borrow;
                        }
                    }
                }
            }

            MemberDecl::Constructor(ctor) => {
                for param in &mut ctor.params {
                    if param.inferred_borrow == BorrowMode::Unresolved {
                        if let Some(explicit) = param.explicit_constraint {
                            param.inferred_borrow = explicit;
                        } else if is_service && is_service_type_ref(&param.ty, symtab) {
                            param.inferred_borrow = BorrowMode::SharedArc;
                        } else if is_copy_type_ref(&param.ty, symtab) {
                            param.inferred_borrow = BorrowMode::CopyValue;
                        } else {
                            param.inferred_borrow = BorrowMode::OwnedMove;
                        }
                    }
                }

                if let Some(c_sym) = symtab.methods.get_mut(&ctor.id) {
                    for (idx, p) in ctor.params.iter().enumerate() {
                        if let Some(ps) = c_sym.params.get_mut(idx) {
                            ps.inferred_borrow = p.inferred_borrow;
                        }
                    }
                }
            }

            MemberDecl::Indexer(_) => {}
        }
    }

    if implements_disposable && !is_value_copy {
        type_decl.has_disposable_drop = true;
    }

    if let Some(t_sym) = symtab.types.get_mut(&type_decl.id) {
        t_sym.has_disposable_drop = type_decl.has_disposable_drop;
    }
}

fn is_service_type_ref(ty: &TypeRef, symtab: &GlobalSymbolTable) -> bool {
    if let Some(candidates) = symtab.short_name_index.get(ty.short_name()) {
        for &id in candidates {
            if let Some(t_sym) = symtab.types.get(&id) {
                if matches!(t_sym.kind, TypeKind::ServiceClass) {
                    return true;
                }
            }
        }
    }
    false
}

pub fn is_copy_type_ref(ty: &TypeRef, symtab: &GlobalSymbolTable) -> bool {
    if ty.is_primitive_keyword {
        return ty.short_name() != "string";
    }
    if matches!(
        ty.short_name(),
        "bool"
            | "byte"
            | "sbyte"
            | "short"
            | "ushort"
            | "int"
            | "uint"
            | "long"
            | "ulong"
            | "float"
            | "double"
            | "decimal"
            | "char"
    ) {
        return true;
    }
    if let Some(candidates) = symtab.short_name_index.get(ty.short_name()) {
        for &id in candidates {
            if let Some(t_sym) = symtab.types.get(&id) {
                if t_sym.is_value_or_copy_archetype() {
                    return true;
                }
            }
        }
    }
    false
}

fn check_type_encapsulation(
    type_decl: &TypeDecl,
    current_ns: &[String],
    imports: &[ImportDecl],
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    let mut base_env: HashMap<String, SymbolId> = HashMap::new();

    for param in &type_decl.primary_ctor_params {
        if let Some(tid) = symtab.resolve_type_ref(&param.ty, current_ns, imports) {
            base_env.insert(param.name.clone(), tid);
        }
    }

    for member in &type_decl.members {
        match member {
            MemberDecl::Field(f) => {
                if let Some(tid) = symtab.resolve_type_ref(&f.ty, current_ns, imports) {
                    base_env.insert(f.name.clone(), tid);
                }
            }
            MemberDecl::Property(p) => {
                if let Some(tid) = symtab.resolve_type_ref(&p.ty, current_ns, imports) {
                    base_env.insert(p.name.clone(), tid);
                }
            }
            _ => {}
        }
    }

    for member in &type_decl.members {
        match member {
            MemberDecl::Method(m) => {
                let mut local_env = base_env.clone();
                for p in &m.params {
                    if let Some(tid) = symtab.resolve_type_ref(&p.ty, current_ns, imports) {
                        local_env.insert(p.name.clone(), tid);
                    }
                }
                if let Some(body) = &m.body {
                    check_block_access(
                        body,
                        type_decl.id,
                        current_ns,
                        imports,
                        &mut local_env,
                        symtab,
                        diag,
                    );
                }
            }
            MemberDecl::Constructor(c) => {
                let mut local_env = base_env.clone();
                for p in &c.params {
                    if let Some(tid) = symtab.resolve_type_ref(&p.ty, current_ns, imports) {
                        local_env.insert(p.name.clone(), tid);
                    }
                }
                if let Some(body) = &c.body {
                    check_block_access(
                        body,
                        type_decl.id,
                        current_ns,
                        imports,
                        &mut local_env,
                        symtab,
                        diag,
                    );
                }
            }
            MemberDecl::Property(p) => {
                for acc in &p.accessors {
                    if let Some(body) = &acc.body {
                        let mut local_env = base_env.clone();
                        check_block_access(
                            body,
                            type_decl.id,
                            current_ns,
                            imports,
                            &mut local_env,
                            symtab,
                            diag,
                        );
                    }
                }
            }
            _ => {}
        }
    }
}

fn check_block_access(
    block: &Block,
    caller_type_id: SymbolId,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &mut HashMap<String, SymbolId>,
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    for stmt in &block.stmts {
        check_stmt_access(stmt, caller_type_id, current_ns, imports, env, symtab, diag);
    }
}

fn check_stmt_access(
    stmt: &Stmt,
    caller_type_id: SymbolId,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &mut HashMap<String, SymbolId>,
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    match stmt {
        Stmt::Block(b) => {
            let mut inner = env.clone();
            check_block_access(b, caller_type_id, current_ns, imports, &mut inner, symtab, diag);
        }
        Stmt::LocalVar {
            name,
            explicit_type,
            init,
            ..
        }
        | Stmt::UsingResource {
            name,
            explicit_type,
            init,
            ..
        } => {
            check_expr_access(init, caller_type_id, current_ns, imports, env, symtab, diag);
            if let Some(ty_ref) = explicit_type {
                if let Some(tid) = symtab.resolve_type_ref(ty_ref, current_ns, imports) {
                    env.insert(name.clone(), tid);
                }
            } else if let Some(tid) = infer_expr_type_symbol(init, caller_type_id, current_ns, imports, env, symtab) {
                env.insert(name.clone(), tid);
            }
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            check_expr_access(cond, caller_type_id, current_ns, imports, env, symtab, diag);
            check_stmt_access(then_branch, caller_type_id, current_ns, imports, env, symtab, diag);
            if let Some(el) = else_branch {
                check_stmt_access(el, caller_type_id, current_ns, imports, env, symtab, diag);
            }
        }
        Stmt::While { cond, body, .. } => {
            check_expr_access(cond, caller_type_id, current_ns, imports, env, symtab, diag);
            check_stmt_access(body, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        Stmt::ForEach {
            collection, body, ..
        } => {
            check_expr_access(collection, caller_type_id, current_ns, imports, env, symtab, diag);
            check_stmt_access(body, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        Stmt::Return { value: Some(v), .. } => {
            check_expr_access(v, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            check_expr_access(error_expr, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            check_block_access(try_block, caller_type_id, current_ns, imports, env, symtab, diag);
            for c in catches {
                let mut catch_env = env.clone();
                if let Some(vname) = &c.var_name {
                    if let Some(tid) = symtab.resolve_type_ref(&c.error_type, current_ns, imports) {
                        catch_env.insert(vname.clone(), tid);
                    }
                }
                check_block_access(
                    &c.body,
                    caller_type_id,
                    current_ns,
                    imports,
                    &mut catch_env,
                    symtab,
                    diag,
                );
            }
        }
        Stmt::ExprStmt { expr, .. } => {
            check_expr_access(expr, caller_type_id, current_ns, imports, env, symtab, diag);
        }
    }
}

fn check_expr_access(
    expr: &Expr,
    caller_type_id: SymbolId,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &HashMap<String, SymbolId>,
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    match &expr.kind {
        ExprKind::MemberAccess { target, member, .. } => {
            check_expr_access(target, caller_type_id, current_ns, imports, env, symtab, diag);
            if let Some(target_type_id) =
                infer_expr_type_symbol(target, caller_type_id, current_ns, imports, env, symtab)
            {
                verify_member_visibility(
                    &expr.span,
                    caller_type_id,
                    target_type_id,
                    member,
                    false,
                    symtab,
                    diag,
                );
            }
        }
        ExprKind::Assignment { target, value, .. } => {
            check_expr_access(target, caller_type_id, current_ns, imports, env, symtab, diag);
            check_expr_access(value, caller_type_id, current_ns, imports, env, symtab, diag);
            if let ExprKind::MemberAccess {
                target: recv,
                member,
                ..
            } = &target.kind
            {
                if let Some(target_type_id) =
                    infer_expr_type_symbol(recv, caller_type_id, current_ns, imports, env, symtab)
                {
                    verify_member_visibility(
                        &target.span,
                        caller_type_id,
                        target_type_id,
                        member,
                        true,
                        symtab,
                        diag,
                    );
                }
            }
        }
        ExprKind::MethodCall {
            receiver,
            method_name,
            args,
            ..
        } => {
            if let Some(recv) = receiver {
                check_expr_access(recv, caller_type_id, current_ns, imports, env, symtab, diag);
                if let Some(target_type_id) =
                    infer_expr_type_symbol(recv, caller_type_id, current_ns, imports, env, symtab)
                {
                    verify_member_visibility(
                        &expr.span,
                        caller_type_id,
                        target_type_id,
                        method_name,
                        false,
                        symtab,
                        diag,
                    );
                }
            }
            for arg in args {
                check_expr_access(&arg.expr, caller_type_id, current_ns, imports, env, symtab, diag);
            }
        }
        ExprKind::Construct { args, .. } => {
            for arg in args {
                check_expr_access(&arg.expr, caller_type_id, current_ns, imports, env, symtab, diag);
            }
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            check_expr_access(left, caller_type_id, current_ns, imports, env, symtab, diag);
            check_expr_access(right, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            check_expr_access(operand, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        ExprKind::IndexAccess { target, indices } => {
            check_expr_access(target, caller_type_id, current_ns, imports, env, symtab, diag);
            for idx in indices {
                check_expr_access(&idx.expr, caller_type_id, current_ns, imports, env, symtab, diag);
            }
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                check_expr_access(t, caller_type_id, current_ns, imports, env, symtab, diag);
            }
            if let Some(s) = start {
                check_expr_access(s, caller_type_id, current_ns, imports, env, symtab, diag);
            }
            if let Some(e) = end {
                check_expr_access(e, caller_type_id, current_ns, imports, env, symtab, diag);
            }
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => {
                check_expr_access(e, caller_type_id, current_ns, imports, env, symtab, diag);
            }
            LambdaBody::Block(b) => {
                let mut inner = env.clone();
                check_block_access(
                    b,
                    caller_type_id,
                    current_ns,
                    imports,
                    &mut inner,
                    symtab,
                    diag,
                );
            }
        },
        ExprKind::Switch { scrutinee, arms } => {
            check_expr_access(scrutinee, caller_type_id, current_ns, imports, env, symtab, diag);
            for arm in arms {
                if let Some(g) = &arm.guard {
                    check_expr_access(g, caller_type_id, current_ns, imports, env, symtab, diag);
                }
                check_expr_access(&arm.body, caller_type_id, current_ns, imports, env, symtab, diag);
            }
        }
        ExprKind::LinqChain(chain) => {
            check_expr_access(&chain.source, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::Identifier { .. }
        | ExprKind::This
        | ExprKind::Base => {}
    }
}

fn infer_expr_type_symbol(
    expr: &Expr,
    caller_type_id: SymbolId,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &HashMap<String, SymbolId>,
    symtab: &GlobalSymbolTable,
) -> Option<SymbolId> {
    match &expr.kind {
        ExprKind::This => Some(caller_type_id),
        ExprKind::Identifier { name, .. } => env
            .get(name)
            .copied()
            .or_else(|| symtab.resolve_type(name, current_ns, imports)),
        ExprKind::Construct { ty, .. } => symtab.resolve_type_ref(ty, current_ns, imports),
        ExprKind::MemberAccess { target, member, .. } => {
            let owner_id =
                infer_expr_type_symbol(target, caller_type_id, current_ns, imports, env, symtab)?;
            let owner_sym = symtab.types.get(&owner_id)?;
            for &fid in &owner_sym.fields {
                if let Some(f) = symtab.fields.get(&fid) {
                    if f.name == *member {
                        return f.resolved_type_id;
                    }
                }
            }
            for &pid in &owner_sym.properties {
                if let Some(p) = symtab.properties.get(&pid) {
                    if p.name == *member {
                        return p.resolved_type_id;
                    }
                }
            }
            None
        }
        _ => None,
    }
}

fn verify_member_visibility(
    span: &crate::diagnostics::SourceSpan,
    caller_type_id: SymbolId,
    target_type_id: SymbolId,
    member_name: &str,
    is_write: bool,
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    if caller_type_id == target_type_id {
        return;
    }

    let Some(target_type) = symtab.types.get(&target_type_id) else {
        return;
    };

    // Check fields
    for &fid in &target_type.fields {
        if let Some(field) = symtab.fields.get(&fid) {
            if field.name == member_name {
                check_access_rule(
                    span,
                    caller_type_id,
                    target_type,
                    member_name,
                    field.access,
                    symtab,
                    diag,
                );
                return;
            }
        }
    }

    // Check properties (including private setter access on `is_write`)
    for &pid in &target_type.properties {
        if let Some(prop) = symtab.properties.get(&pid) {
            if prop.name == member_name {
                let effective_access = if is_write {
                    prop.setter_access.unwrap_or(prop.access)
                } else {
                    prop.access
                };
                let display_name = if is_write && prop.setter_access.is_some() {
                    format!("{}.set", member_name)
                } else {
                    member_name.to_string()
                };
                check_access_rule(
                    span,
                    caller_type_id,
                    target_type,
                    &display_name,
                    effective_access,
                    symtab,
                    diag,
                );
                return;
            }
        }
    }

    // Check methods
    for &mid in &target_type.methods {
        if let Some(method) = symtab.methods.get(&mid) {
            if method.name == member_name {
                check_access_rule(
                    span,
                    caller_type_id,
                    target_type,
                    member_name,
                    method.access,
                    symtab,
                    diag,
                );
                return;
            }
        }
    }
}

fn check_access_rule(
    span: &crate::diagnostics::SourceSpan,
    caller_type_id: SymbolId,
    target_type: &crate::semantics::symbols::TypeSymbol,
    member_name: &str,
    access: AccessMod,
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    match access {
        AccessMod::Public | AccessMod::Internal => {}
        AccessMod::Private => {
            if caller_type_id != target_type.id {
                diag.report_access_violation(span.clone(), member_name, "private", &target_type.name);
            }
        }
        AccessMod::Protected => {
            if !is_subtype_of(caller_type_id, target_type.id, symtab) {
                diag.report_access_violation(
                    span.clone(),
                    member_name,
                    "protected",
                    &target_type.name,
                );
            }
        }
    }
}

pub fn is_subtype_of(
    child_id: SymbolId,
    ancestor_id: SymbolId,
    symtab: &GlobalSymbolTable,
) -> bool {
    if child_id == ancestor_id {
        return true;
    }
    let Some(child) = symtab.types.get(&child_id) else {
        return false;
    };
    for &base_id in &child.resolved_base_type_ids {
        if is_subtype_of(base_id, ancestor_id, symtab) {
            return true;
        }
    }
    false
}

```

---

### `src/semantics/hierarchy_lowerer.rs`

```rust
use std::collections::HashMap;

use crate::frontend::ast::{CompilationUnit, PolymorphismStrategy, SymbolId, TypeKind};
use crate::semantics::symbols::GlobalSymbolTable;

/// Pass 2A Polymorphism & Hierarchy Lowerer.
///
/// Inspects the whole-project type hierarchy in `GlobalSymbolTable` and assigns a zero-vtable
/// Rust lowering strategy (`PolymorphismStrategy`) to every type:
/// 1. `OpenTrait`: Interfaces marked `extensible interface` (or `IDisposable` / ambient interfaces)
///    lower to native `pub trait`.
/// 2. `ClosedWorldEnum`: Abstract classes or non-extensible interfaces with concrete subclasses
///    in the crate lower to an exhaustive Rust `enum` with `match` dispatch.
/// 3. `FlattenedSubStruct`: Concrete subclasses inheriting from a class (abstract or concrete)
///    embed `pub base: BaseStruct` and implement `Deref` / `DerefMut` for zero-indirection state reuse.
/// 4. `MonomorphicStruct`: Standard records, services, structs, and classes without subclasses.
pub fn resolve_polymorphism_strategies(
    units: &mut [CompilationUnit],
    symtab: &mut GlobalSymbolTable,
) {
    // 1. Build a map from every base type/interface `SymbolId` to its concrete implementing types
    let mut implementors_by_base: HashMap<SymbolId, Vec<SymbolId>> = HashMap::new();
    let mut direct_base_class: HashMap<SymbolId, SymbolId> = HashMap::new();

    let mut all_type_ids: Vec<SymbolId> = symtab.types.keys().copied().collect();
    all_type_ids.sort_by_key(|id| id.0);

    for &type_id in &all_type_ids {
        let Some(type_sym) = symtab.types.get(&type_id) else {
            continue;
        };
        if type_sym.is_ambient_stub {
            continue;
        }

        let is_concrete_type = !type_sym.is_abstract
            && !matches!(type_sym.kind, TypeKind::Interface { .. } | TypeKind::Enum);

        for &base_id in &type_sym.resolved_base_type_ids {
            let Some(base_sym) = symtab.types.get(&base_id) else {
                continue;
            };

            if is_concrete_type {
                implementors_by_base
                    .entry(base_id)
                    .or_default()
                    .push(type_id);
            }

            // Record single-inheritance base class (as opposed to interfaces) for struct flattening
            if !matches!(
                base_sym.kind,
                TypeKind::Interface { .. } | TypeKind::PrimitiveClass { .. }
            ) {
                direct_base_class.insert(type_id, base_id);
            }
        }
    }

    // 2. Compute `PolymorphismStrategy` for every registered TypeSymbol
    let mut resolved_strategies: HashMap<SymbolId, PolymorphismStrategy> = HashMap::new();

    for &type_id in &all_type_ids {
        let Some(type_sym) = symtab.types.get(&type_id) else {
            continue;
        };

        let strategy = match type_sym.kind {
            TypeKind::Interface { is_extensible } => {
                if is_extensible || type_sym.is_ambient_stub || type_sym.name == "IDisposable" {
                    PolymorphismStrategy::OpenTrait
                } else {
                    let variants = implementors_by_base
                        .get(&type_id)
                        .cloned()
                        .unwrap_or_default();
                    if variants.is_empty() {
                        PolymorphismStrategy::OpenTrait
                    } else {
                        PolymorphismStrategy::ClosedWorldEnum { variants }
                    }
                }
            }

            TypeKind::StandardClass | TypeKind::ServiceClass | TypeKind::SharedClass => {
                if type_sym.is_abstract {
                    let variants = implementors_by_base
                        .get(&type_id)
                        .cloned()
                        .unwrap_or_default();
                    PolymorphismStrategy::ClosedWorldEnum { variants }
                } else if let Some(&base_class_id) = direct_base_class.get(&type_id) {
                    PolymorphismStrategy::FlattenedSubStruct {
                        base_type: base_class_id,
                    }
                } else {
                    PolymorphismStrategy::MonomorphicStruct
                }
            }

            TypeKind::Record { .. }
            | TypeKind::ValueStruct
            | TypeKind::PrimitiveClass { .. }
            | TypeKind::Enum => {
                if let Some(&base_class_id) = direct_base_class.get(&type_id) {
                    PolymorphismStrategy::FlattenedSubStruct {
                        base_type: base_class_id,
                    }
                } else {
                    PolymorphismStrategy::MonomorphicStruct
                }
            }
        };

        resolved_strategies.insert(type_id, strategy);
    }

    // 3. Write the resolved strategies back to `GlobalSymbolTable` and AST `TypeDecl` nodes
    for (type_id, strat) in &resolved_strategies {
        if let Some(type_sym) = symtab.types.get_mut(type_id) {
            type_sym.inferred_polymorphism = strat.clone();
        }
    }

    for unit in units.iter_mut() {
        for type_decl in &mut unit.types {
            if let Some(strat) = resolved_strategies.get(&type_decl.id) {
                type_decl.inferred_polymorphism = strat.clone();
            }
        }
    }
}

```

---

### `src/semantics/overload_resolver.rs`

```rust
use std::collections::{HashMap, HashSet};

use crate::frontend::ast::{
    ArgNode, Block, CompilationUnit, ConstructorDecl, Expr, ExprKind, ImportDecl, LambdaBody,
    LiteralValue, MemberDecl, MethodDecl, ParamDecl, Stmt, SymbolId, TypeDecl, TypeRef,
};
use crate::semantics::symbols::{pascal_to_snake_case, GlobalSymbolTable, ParamSymbol};

/// Pass 2A Static Compile-Time Method & Constructor Overload Disambiguator.
///
/// Because Rust does not support overloaded method identifiers in an `impl` block,
/// RustSharp resolves all method and constructor overloads statically at compile time:
/// 1. Assigns human-readable disambiguated snake_case Rust names to overloaded methods
///    (e.g., `Find(int id)` -> `find_by_id`, `Find(string email, bool activeOnly = true)` -> `find_by_email`)
///    and overloaded constructors (`new`, `from_email`).
/// 2. Walks all expressions across all compilation units, infers `expr.resolved_type`,
///    binds `ExprKind::MethodCall.resolved_overload` and `ExprKind::Construct.resolved_ctor`
///    to the exact matching `SymbolId`, and injects omitted default argument expressions at call sites.
pub fn resolve_overloads(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable) {
    // Step 1: Disambiguate method and constructor names on every type declaration
    for unit in units.iter_mut() {
        for type_decl in &mut unit.types {
            disambiguate_type_overloads(type_decl, symtab);
        }
    }

    // Step 2: Walk all method, constructor, and property bodies to resolve overloaded call sites
    //         and inject default arguments where omitted by the caller.
    for unit in units.iter_mut() {
        if unit.is_ambient_stub {
            continue;
        }
        let current_ns = unit.namespace.clone();
        let imports = unit.imports.clone();

        for type_decl in &mut unit.types {
            resolve_calls_in_type(type_decl, &current_ns, &imports, symtab);
        }
    }
}

fn disambiguate_type_overloads(type_decl: &mut TypeDecl, symtab: &mut GlobalSymbolTable) {
    // 1. Group methods by C# identifier
    let mut method_indices_by_name: HashMap<String, Vec<usize>> = HashMap::new();
    let mut ctor_indices: Vec<usize> = Vec::new();

    for (idx, member) in type_decl.members.iter().enumerate() {
        match member {
            MemberDecl::Method(m) => {
                method_indices_by_name
                    .entry(m.name.clone())
                    .or_default()
                    .push(idx);
            }
            MemberDecl::Constructor(_) => {
                ctor_indices.push(idx);
            }
            _ => {}
        }
    }

    // 2. Disambiguate method groups
    for (base_name, indices) in method_indices_by_name {
        let base_snake = pascal_to_snake_case(&base_name);

        if indices.len() == 1 {
            let idx = indices[0];
            if let MemberDecl::Method(m) = &mut type_decl.members[idx] {
                m.disambiguated_rust_name = base_snake.clone();
                if let Some(msym) = symtab.methods.get_mut(&m.id) {
                    msym.disambiguated_rust_name = base_snake;
                }
            }
            continue;
        }

        // Multiple overloads share `base_name`: first try ` {base_snake}_by_{first_param_name} `
        let mut candidate_names: Vec<String> = Vec::with_capacity(indices.len());
        for &idx in &indices {
            if let MemberDecl::Method(m) = &type_decl.members[idx] {
                let name = build_param_name_disambiguation(&base_snake, &m.params);
                candidate_names.push(name);
            }
        }

        // If any two overloads still collide (e.g., both have first parameter named `value`),
        // fall back to appending parameter type suffixes (`{base_snake}_by_{type}` or `{base_snake}_{types}`).
        if has_duplicates(&candidate_names) {
            candidate_names.clear();
            for &idx in &indices {
                if let MemberDecl::Method(m) = &type_decl.members[idx] {
                    let name = build_param_type_disambiguation(&base_snake, &m.params);
                    candidate_names.push(name);
                }
            }
        }

        // Apply final unique names
        for (pos, &idx) in indices.iter().enumerate() {
            let final_name = candidate_names[pos].clone();
            if let MemberDecl::Method(m) = &mut type_decl.members[idx] {
                m.disambiguated_rust_name = final_name.clone();
                if let Some(msym) = symtab.methods.get_mut(&m.id) {
                    msym.disambiguated_rust_name = final_name;
                }
            }
        }
    }

    // 3. Disambiguate constructor groups (`new`, `from_<param>`, etc.)
    if ctor_indices.len() == 1 {
        let idx = ctor_indices[0];
        if let MemberDecl::Constructor(c) = &mut type_decl.members[idx] {
            c.disambiguated_rust_name = String::from("new");
            if let Some(csym) = symtab.methods.get_mut(&c.id) {
                csym.disambiguated_rust_name = String::from("new");
            }
        }
    } else if ctor_indices.len() > 1 {
        let mut used_names = HashSet::new();
        for (pos, &idx) in ctor_indices.iter().enumerate() {
            if let MemberDecl::Constructor(c) = &mut type_decl.members[idx] {
                let candidate = if pos == 0 {
                    String::from("new")
                } else {
                    build_ctor_disambiguation(c, pos)
                };
                let final_name = if used_names.contains(&candidate) {
                    format!("{}_{}", candidate, pos)
                } else {
                    candidate
                };
                used_names.insert(final_name.clone());
                c.disambiguated_rust_name = final_name.clone();
                if let Some(csym) = symtab.methods.get_mut(&c.id) {
                    csym.disambiguated_rust_name = final_name;
                }
            }
        }
    }
}

fn build_param_name_disambiguation(base_snake: &str, params: &[ParamDecl]) -> String {
    if params.is_empty() {
        return base_snake.to_string();
    }
    let first_param = pascal_to_snake_case(&params[0].name);
    format!("{}_by_{}", base_snake, first_param)
}

fn build_param_type_disambiguation(base_snake: &str, params: &[ParamDecl]) -> String {
    if params.is_empty() {
        return base_snake.to_string();
    }
    let suffixes: Vec<String> = params
        .iter()
        .map(|p| sanitize_type_suffix(&p.ty))
        .collect();
    format!("{}_{}", base_snake, suffixes.join("_"))
}

fn build_ctor_disambiguation(ctor: &ConstructorDecl, index: usize) -> String {
    if ctor.params.is_empty() {
        return String::from("default_new");
    }
    if ctor.params.len() == 1 {
        let param_snake = pascal_to_snake_case(&ctor.params[0].name);
        return format!("from_{}", param_snake);
    }
    let first_snake = pascal_to_snake_case(&ctor.params[0].name);
    let second_snake = pascal_to_snake_case(&ctor.params[1].name);
    let name = format!("with_{}_and_{}", first_snake, second_snake);
    if name.is_empty() {
        format!("new_{}", index)
    } else {
        name
    }
}

fn sanitize_type_suffix(ty: &TypeRef) -> String {
    match ty.short_name() {
        "int" => "i32".to_string(),
        "long" => "i64".to_string(),
        "short" => "i16".to_string(),
        "byte" => "u8".to_string(),
        "uint" => "u32".to_string(),
        "ulong" => "u64".to_string(),
        "float" => "f32".to_string(),
        "double" => "f64".to_string(),
        "decimal" => "decimal".to_string(),
        "string" | "String" => "str".to_string(),
        "bool" => "bool".to_string(),
        other => pascal_to_snake_case(other),
    }
}

fn has_duplicates(items: &[String]) -> bool {
    let mut seen = HashSet::with_capacity(items.len());
    for item in items {
        if !seen.insert(item) {
            return true;
        }
    }
    false
}

fn resolve_calls_in_type(
    type_decl: &mut TypeDecl,
    current_ns: &[String],
    imports: &[ImportDecl],
    symtab: &GlobalSymbolTable,
) {
    // Build base variable type environment from primary constructor params, fields, and properties
    let mut base_env: HashMap<String, TypeRef> = HashMap::new();
    for p in &type_decl.primary_ctor_params {
        base_env.insert(p.name.clone(), p.ty.clone());
    }
    for member in &type_decl.members {
        match member {
            MemberDecl::Field(f) => {
                base_env.insert(f.name.clone(), f.ty.clone());
            }
            MemberDecl::Property(p) => {
                base_env.insert(p.name.clone(), p.ty.clone());
            }
            _ => {}
        }
    }

    // Collect default parameter expressions by `(method_symbol_id, param_index)` so call sites
    // omitting optional arguments can have the default expression injected statically!
    let default_arg_table = build_default_arg_table(type_decl);

    let owner_id = type_decl.id;
    let owner_type_ref = TypeRef {
        span: type_decl.span.clone(),
        path: vec![type_decl.name.clone()],
        type_args: Vec::new(),
        is_nullable: false,
        is_primitive_keyword: false,
    };

    for member in &mut type_decl.members {
        match member {
            MemberDecl::Method(m) => {
                let mut env = base_env.clone();
                env.insert("this".to_string(), owner_type_ref.clone());
                for p in &m.params {
                    env.insert(p.name.clone(), p.ty.clone());
                }
                if let Some(body) = &mut m.body {
                    resolve_calls_in_block(
                        body,
                        owner_id,
                        current_ns,
                        imports,
                        &mut env,
                        &default_arg_table,
                        symtab,
                    );
                }
            }
            MemberDecl::Constructor(c) => {
                let mut env = base_env.clone();
                env.insert("this".to_string(), owner_type_ref.clone());
                for p in &c.params {
                    env.insert(p.name.clone(), p.ty.clone());
                }
                if let Some(body) = &mut c.body {
                    resolve_calls_in_block(
                        body,
                        owner_id,
                        current_ns,
                        imports,
                        &mut env,
                        &default_arg_table,
                        symtab,
                    );
                }
            }
            MemberDecl::Property(p) => {
                for acc in &mut p.accessors {
                    if let Some(body) = &mut acc.body {
                        let mut env = base_env.clone();
                        env.insert("this".to_string(), owner_type_ref.clone());
                        resolve_calls_in_block(
                            body,
                            owner_id,
                            current_ns,
                            imports,
                            &mut env,
                            &default_arg_table,
                            symtab,
                        );
                    }
                }
            }
            _ => {}
        }
    }
}

fn build_default_arg_table(type_decl: &TypeDecl) -> HashMap<(SymbolId, usize), Expr> {
    let mut table = HashMap::new();
    for member in &type_decl.members {
        match member {
            MemberDecl::Method(m) => {
                for (i, p) in m.params.iter().enumerate() {
                    if let Some(def_expr) = &p.default_value {
                        table.insert((m.id, i), def_expr.clone());
                    }
                }
            }
            MemberDecl::Constructor(c) => {
                for (i, p) in c.params.iter().enumerate() {
                    if let Some(def_expr) = &p.default_value {
                        table.insert((c.id, i), def_expr.clone());
                    }
                }
            }
            _ => {}
        }
    }
    table
}

fn resolve_calls_in_block(
    block: &mut Block,
    owner_id: SymbolId,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &mut HashMap<String, TypeRef>,
    default_args: &HashMap<(SymbolId, usize), Expr>,
    symtab: &GlobalSymbolTable,
) {
    for stmt in &mut block.stmts {
        resolve_calls_in_stmt(
            stmt,
            owner_id,
            current_ns,
            imports,
            env,
            default_args,
            symtab,
        );
    }
}

fn resolve_calls_in_stmt(
    stmt: &mut Stmt,
    owner_id: SymbolId,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &mut HashMap<String, TypeRef>,
    default_args: &HashMap<(SymbolId, usize), Expr>,
    symtab: &GlobalSymbolTable,
) {
    match stmt {
        Stmt::Block(b) => {
            let mut inner = env.clone();
            resolve_calls_in_block(
                b,
                owner_id,
                current_ns,
                imports,
                &mut inner,
                default_args,
                symtab,
            );
        }
        Stmt::LocalVar {
            name,
            explicit_type,
            init,
            inferred_type,
            ..
        } => {
            resolve_calls_in_expr(
                init,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            let var_ty = explicit_type
                .clone()
                .or_else(|| init.resolved_type.clone());
            if let Some(ty) = var_ty {
                *inferred_type = Some(ty.clone());
                env.insert(name.clone(), ty);
            }
        }
        Stmt::UsingResource {
            name,
            explicit_type,
            init,
            ..
        } => {
            resolve_calls_in_expr(
                init,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            let var_ty = explicit_type
                .clone()
                .or_else(|| init.resolved_type.clone());
            if let Some(ty) = var_ty {
                env.insert(name.clone(), ty);
            }
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            resolve_calls_in_expr(
                cond,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            resolve_calls_in_stmt(
                then_branch,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            if let Some(el) = else_branch {
                resolve_calls_in_stmt(
                    el,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }
        }
        Stmt::While { cond, body, .. } => {
            resolve_calls_in_expr(
                cond,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            resolve_calls_in_stmt(
                body,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
        }
        Stmt::ForEach {
            item_name,
            item_type,
            collection,
            body,
            ..
        } => {
            resolve_calls_in_expr(
                collection,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            let mut loop_env = env.clone();
            if let Some(explicit_ty) = item_type {
                loop_env.insert(item_name.clone(), explicit_ty.clone());
            } else if let Some(coll_ty) = &collection.resolved_type {
                if let Some(first_arg) = coll_ty.type_args.first() {
                    loop_env.insert(item_name.clone(), first_arg.clone());
                }
            }
            resolve_calls_in_stmt(
                body,
                owner_id,
                current_ns,
                imports,
                &mut loop_env,
                default_args,
                symtab,
            );
        }
        Stmt::Return { value: Some(v), .. } => {
            resolve_calls_in_expr(v, owner_id, current_ns, imports, env, default_args, symtab);
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            resolve_calls_in_expr(
                error_expr,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            resolve_calls_in_block(
                try_block,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            for c in catches {
                let mut catch_env = env.clone();
                if let Some(vname) = &c.var_name {
                    catch_env.insert(vname.clone(), c.error_type.clone());
                }
                resolve_calls_in_block(
                    &mut c.body,
                    owner_id,
                    current_ns,
                    imports,
                    &mut catch_env,
                    default_args,
                    symtab,
                );
            }
        }
        Stmt::ExprStmt { expr, .. } => {
            resolve_calls_in_expr(
                expr,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
        }
    }
}

fn resolve_calls_in_expr(
    expr: &mut Expr,
    owner_id: SymbolId,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &HashMap<String, TypeRef>,
    default_args: &HashMap<(SymbolId, usize), Expr>,
    symtab: &GlobalSymbolTable,
) {
    let span = expr.span.clone();

    match &mut expr.kind {
        ExprKind::Literal(lit) => {
            let prim_name = match lit {
                LiteralValue::Int(_) => Some("int"),
                LiteralValue::Float(_) => Some("double"),
                LiteralValue::Decimal(_) => Some("decimal"),
                LiteralValue::String(_) => Some("string"),
                LiteralValue::Char(_) => Some("char"),
                LiteralValue::Bool(_) => Some("bool"),
                LiteralValue::Null => None,
            };
            if let Some(p) = prim_name {
                expr.resolved_type = Some(TypeRef {
                    span,
                    path: vec![p.to_string()],
                    type_args: Vec::new(),
                    is_nullable: false,
                    is_primitive_keyword: true,
                });
            }
        }

        ExprKind::InterpolatedString(_) => {
            expr.resolved_type = Some(TypeRef {
                span,
                path: vec!["string".to_string()],
                type_args: Vec::new(),
                is_nullable: false,
                is_primitive_keyword: true,
            });
        }

        ExprKind::Identifier { name, .. } => {
            if let Some(ty) = env.get(name) {
                expr.resolved_type = Some(ty.clone());
            }
        }

        ExprKind::This => {
            if let Some(ty) = env.get("this") {
                expr.resolved_type = Some(ty.clone());
            }
        }

        ExprKind::MemberAccess {
            target,
            member,
            resolved_symbol,
            ..
        } => {
            resolve_calls_in_expr(
                target,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            if let Some(recv_ty) = &target.resolved_type {
                if let Some(recv_sym_id) = symtab.resolve_type_ref(recv_ty, current_ns, imports) {
                    if let Some((mem_id, mem_ty)) = lookup_field_or_prop(recv_sym_id, member, symtab)
                    {
                        *resolved_symbol = Some(mem_id);
                        expr.resolved_type = Some(mem_ty);
                    }
                }
            }
        }

        ExprKind::MethodCall {
            receiver,
            method_name,
            args,
            resolved_overload,
            primitive_lowering,
            ..
        } => {
            if let Some(recv) = receiver {
                resolve_calls_in_expr(
                    recv,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }
            for arg in args.iter_mut() {
                resolve_calls_in_expr(
                    &mut arg.expr,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }

            // Determine target type SymbolId (either explicit receiver type or enclosing `owner_id`)
            let target_type_id = if let Some(recv) = receiver {
                if let Some(recv_ty) = &recv.resolved_type {
                    symtab.resolve_type_ref(recv_ty, current_ns, imports)
                } else if let ExprKind::Identifier { name, .. } = &recv.kind {
                    symtab.resolve_type(name, current_ns, imports)
                } else {
                    None
                }
            } else {
                Some(owner_id)
            };

            if let Some(tid) = target_type_id {
                if let Some(matched_method_id) =
                    select_best_overload(tid, method_name, args, false, symtab)
                {
                    *resolved_overload = Some(matched_method_id);
                    if let Some(msym) = symtab.methods.get(&matched_method_id) {
                        expr.resolved_type = Some(msym.return_type.clone());
                        *primitive_lowering = msym.primitive_lowering.clone();

                        // Inject default parameter values if caller omitted optional trailing parameters
                        inject_missing_default_args(args, &msym.params, matched_method_id, default_args);
                    }
                }
            }
        }

        ExprKind::Construct {
            ty,
            args,
            resolved_ctor,
            primitive_lowering,
        } => {
            for arg in args.iter_mut() {
                resolve_calls_in_expr(
                    &mut arg.expr,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }
            expr.resolved_type = Some(ty.clone());

            if let Some(tid) = symtab.resolve_type_ref(ty, current_ns, imports) {
                if let Some(matched_ctor_id) =
                    select_best_overload(tid, ty.short_name(), args, true, symtab)
                {
                    *resolved_ctor = Some(matched_ctor_id);
                    if let Some(csym) = symtab.methods.get(&matched_ctor_id) {
                        *primitive_lowering = csym.primitive_lowering.clone();
                        inject_missing_default_args(args, &csym.params, matched_ctor_id, default_args);
                    }
                }
            }
        }

        ExprKind::Assignment { target, value, .. } => {
            resolve_calls_in_expr(
                target,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            resolve_calls_in_expr(
                value,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            expr.resolved_type = target.resolved_type.clone();
        }

        ExprKind::Binary { left, right, .. } => {
            resolve_calls_in_expr(
                left,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            resolve_calls_in_expr(
                right,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            expr.resolved_type = left.resolved_type.clone();
        }

        ExprKind::NullCoalesce { left, right } => {
            resolve_calls_in_expr(
                left,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            resolve_calls_in_expr(
                right,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            expr.resolved_type = right.resolved_type.clone().or_else(|| left.resolved_type.clone());
        }

        ExprKind::Unary { operand, .. } => {
            resolve_calls_in_expr(
                operand,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            expr.resolved_type = operand.resolved_type.clone();
        }

        ExprKind::IndexAccess { target, indices } => {
            resolve_calls_in_expr(
                target,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            for idx in indices {
                resolve_calls_in_expr(
                    &mut idx.expr,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }
            if let Some(t_ty) = &target.resolved_type {
                if let Some(elem_ty) = t_ty.type_args.last() {
                    expr.resolved_type = Some(elem_ty.clone());
                }
            }
        }

        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                resolve_calls_in_expr(
                    t,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
                expr.resolved_type = t.resolved_type.clone();
            }
            if let Some(s) = start {
                resolve_calls_in_expr(
                    s,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }
            if let Some(e) = end {
                resolve_calls_in_expr(
                    e,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }
        }

        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => {
                resolve_calls_in_expr(
                    e,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }
            LambdaBody::Block(b) => {
                let mut inner = env.clone();
                resolve_calls_in_block(
                    b,
                    owner_id,
                    current_ns,
                    imports,
                    &mut inner,
                    default_args,
                    symtab,
                );
            }
        },

        ExprKind::Switch { scrutinee, arms } => {
            resolve_calls_in_expr(
                scrutinee,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            for arm in arms {
                if let Some(g) = &mut arm.guard {
                    resolve_calls_in_expr(
                        g,
                        owner_id,
                        current_ns,
                        imports,
                        env,
                        default_args,
                        symtab,
                    );
                }
                resolve_calls_in_expr(
                    &mut arm.body,
                    owner_id,
                    current_ns,
                    imports,
                    env,
                    default_args,
                    symtab,
                );
            }
            if let Some(first_arm) = arms.first() {
                expr.resolved_type = first_arm.body.resolved_type.clone();
            }
        }

        ExprKind::IsPattern { expr: inner, .. } => {
            resolve_calls_in_expr(
                inner,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
            expr.resolved_type = Some(TypeRef {
                span,
                path: vec!["bool".to_string()],
                type_args: Vec::new(),
                is_nullable: false,
                is_primitive_keyword: true,
            });
        }

        ExprKind::LinqChain(chain) => {
            resolve_calls_in_expr(
                &mut chain.source,
                owner_id,
                current_ns,
                imports,
                env,
                default_args,
                symtab,
            );
        }

        ExprKind::Base => {}
    }
}

fn lookup_field_or_prop(
    type_id: SymbolId,
    member_name: &str,
    symtab: &GlobalSymbolTable,
) -> Option<(SymbolId, TypeRef)> {
    let type_sym = symtab.types.get(&type_id)?;
    for &fid in &type_sym.fields {
        if let Some(f) = symtab.fields.get(&fid) {
            if f.name == member_name {
                return Some((fid, f.ty.clone()));
            }
        }
    }
    for &pid in &type_sym.properties {
        if let Some(p) = symtab.properties.get(&pid) {
            if p.name == member_name {
                return Some((pid, p.ty.clone()));
            }
        }
    }
    for &base_id in &type_sym.resolved_base_type_ids {
        if let Some(found) = lookup_field_or_prop(base_id, member_name, symtab) {
            return Some(found);
        }
    }
    None
}

fn select_best_overload(
    type_id: SymbolId,
    member_name: &str,
    args: &[ArgNode],
    is_ctor: bool,
    symtab: &GlobalSymbolTable,
) -> Option<SymbolId> {
    let type_sym = symtab.types.get(&type_id)?;
    let candidate_ids: Vec<SymbolId> = if is_ctor {
        type_sym.constructors.clone()
    } else {
        let mut ids = Vec::new();
        collect_methods_in_hierarchy(type_id, member_name, symtab, &mut ids);
        ids
    };

    if candidate_ids.is_empty() {
        return None;
    }
    if candidate_ids.len() == 1 {
        return Some(candidate_ids[0]);
    }

    let mut best_id = None;
    let mut best_score = -1i32;

    for cid in candidate_ids {
        let Some(msym) = symtab.methods.get(&cid) else {
            continue;
        };

        let min_arity = msym.params.iter().filter(|p| !p.has_default).count();
        let max_arity = msym.params.len();
        if args.len() < min_arity || args.len() > max_arity {
            continue;
        }

        let mut score = 10i32;
        let mut compatible = true;

        for (i, arg) in args.iter().enumerate() {
            let param = &msym.params[i];

            // Named argument check (`email: "a@b.com"`)
            if let Some(arg_name) = &arg.name {
                if arg_name != &param.name {
                    compatible = false;
                    break;
                }
                score += 20;
            }

            if let Some(arg_ty) = &arg.expr.resolved_type {
                if types_match(arg_ty, &param.ty) {
                    score += 50;
                } else {
                    compatible = false;
                    break;
                }
            }
        }

        if compatible && score > best_score {
            best_score = score;
            best_id = Some(cid);
        }
    }

    best_id
}

fn collect_methods_in_hierarchy(
    type_id: SymbolId,
    method_name: &str,
    symtab: &GlobalSymbolTable,
    out: &mut Vec<SymbolId>,
) {
    let Some(type_sym) = symtab.types.get(&type_id) else {
        return;
    };
    for &mid in &type_sym.methods {
        if let Some(m) = symtab.methods.get(&mid) {
            if m.name == method_name && !out.contains(&mid) {
                out.push(mid);
            }
        }
    }
    for &base_id in &type_sym.resolved_base_type_ids {
        collect_methods_in_hierarchy(base_id, method_name, symtab, out);
    }
}

fn types_match(arg_ty: &TypeRef, param_ty: &TypeRef) -> bool {
    let a = normalize_type_name(arg_ty.short_name());
    let b = normalize_type_name(param_ty.short_name());
    a == b
}

fn normalize_type_name(name: &str) -> &str {
    match name {
        "String" | "string" => "string",
        "Int32" | "int" => "int",
        "Int64" | "long" => "long",
        "Boolean" | "bool" => "bool",
        "Decimal" | "decimal" => "decimal",
        "Double" | "double" => "double",
        other => other,
    }
}

fn inject_missing_default_args(
    args: &mut Vec<ArgNode>,
    params: &[ParamSymbol],
    method_id: SymbolId,
    default_args: &HashMap<(SymbolId, usize), Expr>,
) {
    while args.len() < params.len() {
        let missing_idx = args.len();
        if let Some(def_expr) = default_args.get(&(method_id, missing_idx)) {
            args.push(ArgNode {
                span: def_expr.span.clone(),
                name: None,
                expr: def_expr.clone(),
            });
        } else {
            break;
        }
    }
}

```

---

### `src/semantics/mod.rs`

```rust
pub mod archetype_analyzer;
pub mod collector;
pub mod hierarchy_lowerer;
pub mod overload_resolver;
pub mod symbols;

pub use archetype_analyzer::analyze_archetypes;
pub use collector::collect_global_symbols;
pub use hierarchy_lowerer::resolve_polymorphism_strategies;
pub use overload_resolver::resolve_overloads;
pub use symbols::{
    FieldSymbol, GlobalSymbolTable, MethodSymbol, NamespaceModulePlan, ParamSymbol,
    PropertySymbol, TypeSymbol,
};

```

---

### `src/lib.rs`

```rust
pub mod diagnostics;
pub mod frontend;
pub mod project;
pub mod semantics;

use diagnostics::DiagnosticEngine;
use frontend::{CompilationUnit, Lexer, Parser};
use semantics::{
    analyze_archetypes, collect_global_symbols, resolve_overloads,
    resolve_polymorphism_strategies, GlobalSymbolTable,
};

/// Convenience helper to lex and parse a single `.rsharp` or `.d.rsharp` source string.
pub fn parse_source_str(
    source: &str,
    file_id: usize,
    filename: &str,
    diag: &mut DiagnosticEngine,
) -> CompilationUnit {
    let tokens = {
        let mut lexer = Lexer::new(source, file_id, filename, diag);
        lexer.tokenize()
    };
    let mut parser = Parser::new(tokens, file_id, filename, diag);
    parser.parse_compilation_unit()
}

/// Runs Milestone 1 (Frontend Lexer + Parser) and Milestone 2 (Pass 1 Global Symbol Collector
/// & Virtual Namespace Aggregator) over an in-memory set of `(filename, source_code)` pairs.
pub fn analyze_workspace_pass1(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let mut diag = DiagnosticEngine::new();
    let mut units = Vec::with_capacity(files.len());

    for (idx, (filename, source)) in files.iter().enumerate() {
        let unit = parse_source_str(source, idx, filename, &mut diag);
        units.push(unit);
    }

    let mut symtab = GlobalSymbolTable::new();
    collect_global_symbols(&mut units, &mut symtab, &mut diag);

    (units, symtab, diag)
}

/// Runs Milestone 1, Milestone 2 (Pass 1), and Milestone 3 (Pass 2A: Archetype Lowering,
/// Hierarchy Flattening & Static Overload Resolution) across all workspace files.
pub fn analyze_workspace_pass2a(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (mut units, mut symtab, mut diag) = analyze_workspace_pass1(files);
    if !diag.has_errors() {
        analyze_archetypes(&mut units, &mut symtab, &mut diag);
        resolve_polymorphism_strategies(&mut units, &mut symtab);
        resolve_overloads(&mut units, &mut symtab);
    }
    (units, symtab, diag)
}

```

---

### `tests/m3_polymorphism_overload_tests.rs`

```rust
use rsharpc::analyze_workspace_pass2a;
use rsharpc::diagnostics::DiagnosticCode;
use rsharpc::frontend::ast::{
    BorrowMode, ExprKind, FieldStorageMode, LiteralValue, MemberDecl, PolymorphismStrategy, Stmt,
};

#[test]
fn test_closed_world_enum_dispatch_and_flattened_base_struct_lowering() {
    let payment_src = r#"
namespace Commerce.Payments;

public extensible interface IPaymentPlugin
{
    string PluginId();
}

public abstract class Payment
{
    public decimal Amount { get; set; }
    public abstract string Summarize();
}

public class CardPayment : Payment
{
    public string LastFour { get; set; }
    public override string Summarize() => $"Card *{LastFour}: {Amount}";
}

public class CryptoPayment : Payment
{
    public string WalletHash { get; set; }
    public override string Summarize() => $"Wallet {WalletHash}: {Amount}";
}
"#;

    let (_units, symtab, diag) =
        analyze_workspace_pass2a(&[("Features/Payments/PaymentHierarchy.rsharp", payment_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let plugin_id = symtab.fqn_to_symbol["Commerce.Payments.IPaymentPlugin"];
    let payment_id = symtab.fqn_to_symbol["Commerce.Payments.Payment"];
    let card_id = symtab.fqn_to_symbol["Commerce.Payments.CardPayment"];
    let crypto_id = symtab.fqn_to_symbol["Commerce.Payments.CryptoPayment"];

    // 1. `extensible interface IPaymentPlugin` -> `PolymorphismStrategy::OpenTrait`
    assert_eq!(
        symtab.types[&plugin_id].inferred_polymorphism,
        PolymorphismStrategy::OpenTrait
    );

    // 2. Closed-world `abstract class Payment` -> `PolymorphismStrategy::ClosedWorldEnum`
    //    containing `CardPayment` and `CryptoPayment` variants (zero dynamic vtable heap boxing!)
    assert_eq!(
        symtab.types[&payment_id].inferred_polymorphism,
        PolymorphismStrategy::ClosedWorldEnum {
            variants: vec![card_id, crypto_id]
        }
    );

    // 3. `CardPayment` and `CryptoPayment` -> `PolymorphismStrategy::FlattenedSubStruct`
    //    embedding `Payment` for `Deref`/`DerefMut` state reuse
    assert_eq!(
        symtab.types[&card_id].inferred_polymorphism,
        PolymorphismStrategy::FlattenedSubStruct {
            base_type: payment_id
        }
    );
    assert_eq!(
        symtab.types[&crypto_id].inferred_polymorphism,
        PolymorphismStrategy::FlattenedSubStruct {
            base_type: payment_id
        }
    );
}

#[test]
fn test_static_compile_time_overload_disambiguation_and_default_arg_injection() {
    let repo_src = r#"
namespace Commerce.Users;

public record User(int Id, string Email);

public service class UserRepository
{
    public User Find(int id) => new User(id, "id@example.com");

    public User Find(string email, bool activeOnly = true) => new User(1, email);

    public User RunLookup()
    {
        var byId = Find(42);
        var byEmail = Find("alice@example.com");
        return byEmail;
    }
}
"#;

    let (units, symtab, diag) =
        analyze_workspace_pass2a(&[("Users/UserRepository.rsharp", repo_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let repo_id = symtab.fqn_to_symbol["Commerce.Users.UserRepository"];
    let repo_sym = &symtab.types[&repo_id];

    let find_int_id = repo_sym.methods[0];
    let find_email_id = repo_sym.methods[1];

    // Verify static compile-time disambiguated Rust method names
    assert_eq!(
        symtab.methods[&find_int_id].disambiguated_rust_name,
        "find_by_id"
    );
    assert_eq!(
        symtab.methods[&find_email_id].disambiguated_rust_name,
        "find_by_email"
    );

    // Verify call sites inside `RunLookup()` resolved statically to their exact overload SymbolIds
    // and that `Find("alice@example.com")` had the default `true` argument injected automatically!
    let repo_decl = &units[0].types[1];
    let run_lookup = match &repo_decl.members[2] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected RunLookup method"),
    };
    let stmts = &run_lookup.body.as_ref().unwrap().stmts;

    // `var byId = Find(42);`
    match &stmts[0] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::MethodCall {
                resolved_overload,
                args,
                ..
            } => {
                assert_eq!(*resolved_overload, Some(find_int_id));
                assert_eq!(args.len(), 1);
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // `var byEmail = Find("alice@example.com");` -> resolves to `find_email_id` + injects `true`
    match &stmts[1] {
        Stmt::LocalVar { init, .. } => match &init.kind {
            ExprKind::MethodCall {
                resolved_overload,
                args,
                ..
            } => {
                assert_eq!(*resolved_overload, Some(find_email_id));
                assert_eq!(
                    args.len(),
                    2,
                    "Expected omitted default parameter `activeOnly = true` to be injected"
                );
                assert_eq!(
                    args[1].expr.kind,
                    ExprKind::Literal(LiteralValue::Bool(true))
                );
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected LocalVar, got {:?}", other),
    }
}

#[test]
fn test_service_arc_shared_rwlock_and_disposable_drop_archetypes() {
    let archetype_src = r#"
namespace Commerce.Infrastructure;

public shared class MetricsRegistry
{
    private int _requestCount;
}

public service class AuditLogger
{
    private readonly MetricsRegistry _metrics;

    public AuditLogger(MetricsRegistry metrics) => _metrics = metrics;
}

public class DbTransaction : IDisposable
{
    public void Dispose()
    {
    }
}
"#;

    let (_units, symtab, diag) =
        analyze_workspace_pass2a(&[("Infra/Archetypes.rsharp", archetype_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let metrics_id = symtab.fqn_to_symbol["Commerce.Infrastructure.MetricsRegistry"];
    let logger_id = symtab.fqn_to_symbol["Commerce.Infrastructure.AuditLogger"];
    let tx_id = symtab.fqn_to_symbol["Commerce.Infrastructure.DbTransaction"];

    // `shared class MetricsRegistry` field uses `RwLockShared`
    let req_field_id = symtab.types[&metrics_id].fields[0];
    assert_eq!(
        symtab.fields[&req_field_id].storage_mode,
        FieldStorageMode::RwLockShared
    );

    // `service class AuditLogger` field uses `ArcShared`
    let metrics_field_id = symtab.types[&logger_id].fields[0];
    assert_eq!(
        symtab.fields[&metrics_field_id].storage_mode,
        FieldStorageMode::ArcShared
    );

    // `DbTransaction : IDisposable` sets `has_disposable_drop = true` and `Dispose(&mut self)`
    let tx_sym = &symtab.types[&tx_id];
    assert!(tx_sym.has_disposable_drop);
    let dispose_id = tx_sym.methods[0];
    assert_eq!(
        symtab.methods[&dispose_id].inferred_self_borrow,
        BorrowMode::MutBorrow
    );
}

#[test]
fn test_enforces_private_access_modifier_across_classes() {
    let bad_access_src = r#"
namespace Commerce.Security;

public class Vault
{
    private string _secretKey;
    public string PublicLabel { get; private set; }
}

public service class VaultInspector
{
    public void Tamper(Vault v)
    {
        v.PublicLabel = "Hacked";
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_pass2a(&[("Security/Vault.rsharp", bad_access_src)]);
    assert!(diag.has_errors());
    assert_eq!(diag.diagnostics.len(), 1);
    assert_eq!(diag.diagnostics[0].code, DiagnosticCode::AccessViolation);
    assert!(diag.diagnostics[0].message.contains("PublicLabel.set"));
}

```

---

Would you like me to continue with the raw individual files for **Milestone 4 (Pass 2B: `src/semantics/primitive_resolver.rs`, `src/semantics/borrow_inferencer.rs`, `src/semantics/effect_inferencer.rs`, `src/semantics/linq_fuser.rs`, and `tests/m4_borrow_and_effect_tests.rs`)** next?
