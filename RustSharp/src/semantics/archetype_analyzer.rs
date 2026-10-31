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
                if !method.is_static
                    && method.inferred_self_borrow == BorrowMode::Unresolved
                    && (is_service || is_shared)
                {
                    method.inferred_self_borrow = BorrowMode::ReadBorrow;
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
            } else if let Some(tid) =
                infer_expr_type_symbol(init, caller_type_id, current_ns, imports, env, symtab)
            {
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
            check_stmt_access(
                then_branch,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
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
            check_expr_access(
                collection,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
            check_stmt_access(body, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        Stmt::Return { value: Some(v), .. } => {
            check_expr_access(v, caller_type_id, current_ns, imports, env, symtab, diag);
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            check_expr_access(
                error_expr,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            check_block_access(
                try_block,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
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
            check_expr_access(
                target,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
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
            check_expr_access(
                target,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
            check_expr_access(
                value,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
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
                check_expr_access(
                    &arg.expr,
                    caller_type_id,
                    current_ns,
                    imports,
                    env,
                    symtab,
                    diag,
                );
            }
        }
        ExprKind::Construct { args, .. } => {
            for arg in args {
                check_expr_access(
                    &arg.expr,
                    caller_type_id,
                    current_ns,
                    imports,
                    env,
                    symtab,
                    diag,
                );
            }
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            check_expr_access(left, caller_type_id, current_ns, imports, env, symtab, diag);
            check_expr_access(
                right,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            check_expr_access(
                operand,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
        }
        ExprKind::IndexAccess { target, indices } => {
            check_expr_access(
                target,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
            for idx in indices {
                check_expr_access(
                    &idx.expr,
                    caller_type_id,
                    current_ns,
                    imports,
                    env,
                    symtab,
                    diag,
                );
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
            check_expr_access(
                scrutinee,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
            for arm in arms {
                if let Some(g) = &arm.guard {
                    check_expr_access(g, caller_type_id, current_ns, imports, env, symtab, diag);
                }
                check_expr_access(
                    &arm.body,
                    caller_type_id,
                    current_ns,
                    imports,
                    env,
                    symtab,
                    diag,
                );
            }
        }
        ExprKind::LinqChain(chain) => {
            check_expr_access(
                &chain.source,
                caller_type_id,
                current_ns,
                imports,
                env,
                symtab,
                diag,
            );
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
                diag.report_access_violation(
                    span.clone(),
                    member_name,
                    "private",
                    &target_type.name,
                );
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
