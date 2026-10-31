use std::collections::{HashMap, HashSet};

use crate::frontend::ast::{
    Block, BorrowMode, CallerArgCoercion, CompilationUnit, Expr, ExprKind, LambdaBody, MemberDecl,
    MethodDecl, Stmt, TypeDecl, TypeKind, TypeRef,
};
use crate::semantics::archetype_analyzer::is_copy_type_ref;
use crate::semantics::primitive_resolver::{
    build_builtin_primitive_table, lookup_intrinsic, normalize_primitive_type_key,
    IntrinsicMemberSpec,
};
use crate::semantics::symbols::GlobalSymbolTable;

/// Pass 2B Whole-Program Interprocedural Escape & Mutation Propagator.
///
/// Infers `BorrowMode` (`ReadBorrow` `&T`, `MutBorrow` `&mut T`, `OwnedMove` `T`,
/// `SharedArc` `Arc<T>`, `CopyValue` `T`) across the entire project call graph:
/// 1. Initializes baseline parameter & receiver borrow modes from local mutations,
///    returns, field stores, and explicit `[Moves]`/`[Mutates]`/`[Borrows]` attributes.
/// 2. Iterates to a fixed point bottom-up across the call graph: if Method A passes
///    parameter `x` into Method B's `MutBorrow` parameter (or invokes a `MutBorrow`
///    method on `x`), Method A's parameter `x` automatically upgrades to `MutBorrow`!
/// 3. Annotates caller local variables with `inferred_mut = true` (`let mut`) and
///    call-site arguments with `CallerArgCoercion` (`&`, `&mut`, `.clone()`, `Arc::clone`).
pub struct InterproceduralBorrowInferencer;

impl InterproceduralBorrowInferencer {
    pub fn infer_all(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable) {
        let intrinsics = build_builtin_primitive_table();

        // Phase 1: Initial intra-procedural pass over every method in the workspace
        for unit in units.iter_mut() {
            if unit.is_ambient_stub {
                continue;
            }
            for type_decl in &mut unit.types {
                seed_initial_method_borrows(type_decl, &intrinsics, symtab);
            }
        }

        // Phase 2: Interprocedural fixed-point propagation bottom-up across call sites
        let max_iterations = 16;
        for _ in 0..max_iterations {
            let mut changed = false;
            for unit in units.iter_mut() {
                if unit.is_ambient_stub {
                    continue;
                }
                for type_decl in &mut unit.types {
                    if propagate_type_method_borrows(type_decl, &intrinsics, symtab) {
                        changed = true;
                    }
                }
            }
            if !changed {
                break;
            }
        }

        // Phase 3: Annotate local `let mut` declarations, `foreach` iterator modes,
        //          and call-site argument coercions (`&`, `&mut`, `.clone()`, `Arc::clone`).
        for unit in units.iter_mut() {
            if unit.is_ambient_stub {
                continue;
            }
            for type_decl in &mut unit.types {
                annotate_type_call_sites_and_locals(type_decl, &intrinsics, symtab);
            }
        }
    }
}

fn seed_initial_method_borrows(
    type_decl: &mut TypeDecl,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &mut GlobalSymbolTable,
) {
    let is_service = matches!(type_decl.kind, TypeKind::ServiceClass);
    let is_shared = matches!(type_decl.kind, TypeKind::SharedClass);

    let type_field_names: HashSet<String> = type_decl
        .primary_ctor_params
        .iter()
        .map(|p| p.name.clone())
        .chain(type_decl.members.iter().filter_map(|m| match m {
            MemberDecl::Field(f) => Some(f.name.clone()),
            MemberDecl::Property(p) => Some(p.name.clone()),
            _ => None,
        }))
        .collect();

    for member in &mut type_decl.members {
        let MemberDecl::Method(method) = member else {
            continue;
        };

        // 1. Seed `self` borrow
        if !method.is_static && method.inferred_self_borrow == BorrowMode::Unresolved {
            method.inferred_self_borrow = BorrowMode::ReadBorrow;
        }

        // 2. Seed parameter borrows
        for param in &mut method.params {
            if let Some(explicit) = param.explicit_constraint {
                param.inferred_borrow = explicit;
            } else if param.ty.short_name() == "ReadOnlySpan" {
                param.inferred_borrow = BorrowMode::ReadBorrow;
            } else if param.ty.short_name() == "Span" {
                param.inferred_borrow = BorrowMode::MutBorrow;
            } else if is_copy_type_ref(&param.ty, symtab) {
                param.inferred_borrow = BorrowMode::CopyValue;
            } else if is_service_type(&param.ty, symtab) {
                param.inferred_borrow = BorrowMode::SharedArc;
            } else if param.inferred_borrow == BorrowMode::Unresolved {
                param.inferred_borrow = BorrowMode::ReadBorrow;
            }
        }

        // 3. Inspect body for direct field/parameter mutations or moves
        let _ = inspect_method_body_for_borrows(
            method,
            is_service,
            is_shared,
            &type_field_names,
            intrinsics,
            symtab,
        );

        sync_method_to_symtab(method, symtab);
    }
}

fn propagate_type_method_borrows(
    type_decl: &mut TypeDecl,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &mut GlobalSymbolTable,
) -> bool {
    let is_service = matches!(type_decl.kind, TypeKind::ServiceClass);
    let is_shared = matches!(type_decl.kind, TypeKind::SharedClass);

    let type_field_names: HashSet<String> = type_decl
        .primary_ctor_params
        .iter()
        .map(|p| p.name.clone())
        .chain(type_decl.members.iter().filter_map(|m| match m {
            MemberDecl::Field(f) => Some(f.name.clone()),
            MemberDecl::Property(p) => Some(p.name.clone()),
            _ => None,
        }))
        .collect();

    let mut any_changed = false;
    for member in &mut type_decl.members {
        if let MemberDecl::Method(method) = member {
            if inspect_method_body_for_borrows(
                method,
                is_service,
                is_shared,
                &type_field_names,
                intrinsics,
                symtab,
            ) {
                sync_method_to_symtab(method, symtab);
                any_changed = true;
            }
        }
    }
    any_changed
}

fn inspect_method_body_for_borrows(
    method: &mut MethodDecl,
    is_service: bool,
    is_shared: bool,
    type_field_names: &HashSet<String>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) -> bool {
    let Some(body) = &method.body else {
        return false;
    };

    let mut mutated_vars: HashSet<String> = HashSet::new();
    let mut moved_vars: HashSet<String> = HashSet::new();
    let mut self_mutated = false;

    let param_types: HashMap<String, TypeRef> = method
        .params
        .iter()
        .map(|p| (p.name.clone(), p.ty.clone()))
        .collect();

    scan_block_mutations_and_moves(
        body,
        type_field_names,
        &param_types,
        intrinsics,
        symtab,
        &mut mutated_vars,
        &mut moved_vars,
        &mut self_mutated,
    );

    let mut changed = false;

    // Upgrade `self` to `MutBorrow` if mutated on a regular class/struct/record
    if !method.is_static
        && !is_service
        && !is_shared
        && self_mutated
        && method.inferred_self_borrow != BorrowMode::MutBorrow
    {
        method.inferred_self_borrow = BorrowMode::MutBorrow;
        changed = true;
    }

    // Upgrade parameter borrows based on `mutated_vars` and `moved_vars`
    for param in &mut method.params {
        if param.explicit_constraint.is_some()
            || param.inferred_borrow == BorrowMode::CopyValue
            || param.inferred_borrow == BorrowMode::SharedArc
        {
            continue;
        }

        if moved_vars.contains(&param.name) && param.inferred_borrow != BorrowMode::OwnedMove {
            param.inferred_borrow = BorrowMode::OwnedMove;
            changed = true;
        } else if mutated_vars.contains(&param.name)
            && param.inferred_borrow != BorrowMode::MutBorrow
            && param.inferred_borrow != BorrowMode::OwnedMove
        {
            param.inferred_borrow = BorrowMode::MutBorrow;
            changed = true;
        }
    }

    changed
}

#[allow(clippy::too_many_arguments)]
fn scan_block_mutations_and_moves(
    block: &Block,
    type_field_names: &HashSet<String>,
    var_types: &HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
    mutated_vars: &mut HashSet<String>,
    moved_vars: &mut HashSet<String>,
    self_mutated: &mut bool,
) {
    for stmt in &block.stmts {
        scan_stmt_mutations_and_moves(
            stmt,
            type_field_names,
            var_types,
            intrinsics,
            symtab,
            mutated_vars,
            moved_vars,
            self_mutated,
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn scan_stmt_mutations_and_moves(
    stmt: &Stmt,
    type_field_names: &HashSet<String>,
    var_types: &HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
    mutated_vars: &mut HashSet<String>,
    moved_vars: &mut HashSet<String>,
    self_mutated: &mut bool,
) {
    match stmt {
        Stmt::Block(b) => {
            scan_block_mutations_and_moves(
                b,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        Stmt::LocalVar { init, .. } | Stmt::UsingResource { init, .. } => {
            scan_expr_mutations_and_moves(
                init,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            scan_expr_mutations_and_moves(
                cond,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            scan_stmt_mutations_and_moves(
                then_branch,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            if let Some(el) = else_branch {
                scan_stmt_mutations_and_moves(
                    el,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
        }
        Stmt::While { cond, body, .. } => {
            scan_expr_mutations_and_moves(
                cond,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            scan_stmt_mutations_and_moves(
                body,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        Stmt::ForEach {
            item_name,
            collection,
            body,
            ..
        } => {
            scan_expr_mutations_and_moves(
                collection,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            scan_stmt_mutations_and_moves(
                body,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            if mutated_vars.contains(item_name) {
                if let Some(col_root) = extract_root_ident(collection) {
                    if col_root == "this" || type_field_names.contains(&col_root) {
                        *self_mutated = true;
                    } else {
                        mutated_vars.insert(col_root);
                    }
                }
            }
        }
        Stmt::Return { value: Some(v), .. } => {
            // Returning a non-Copy parameter directly moves ownership out of the function
            if let Some(root) = extract_root_ident(v) {
                if matches!(v.kind, ExprKind::Identifier { .. }) {
                    moved_vars.insert(root);
                }
            }
            scan_expr_mutations_and_moves(
                v,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            scan_expr_mutations_and_moves(
                error_expr,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            scan_block_mutations_and_moves(
                try_block,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            for c in catches {
                scan_block_mutations_and_moves(
                    &c.body,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
        }
        Stmt::ExprStmt { expr, .. } => {
            scan_expr_mutations_and_moves(
                expr,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn scan_expr_mutations_and_moves(
    expr: &Expr,
    type_field_names: &HashSet<String>,
    var_types: &HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
    mutated_vars: &mut HashSet<String>,
    moved_vars: &mut HashSet<String>,
    self_mutated: &mut bool,
) {
    match &expr.kind {
        ExprKind::Assignment { target, value, .. } => {
            // Check if target mutates `this` or a parameter/local variable
            if let Some(root) = extract_root_ident(target) {
                if root == "this" || type_field_names.contains(&root) {
                    *self_mutated = true;
                    // Storing a parameter into a field of `this` consumes ownership
                    if let ExprKind::Identifier { name: rhs_name, .. } = &value.kind {
                        moved_vars.insert(rhs_name.clone());
                    }
                } else {
                    mutated_vars.insert(root);
                }
            }

            scan_expr_mutations_and_moves(
                target,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            scan_expr_mutations_and_moves(
                value,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }

        ExprKind::MethodCall {
            receiver,
            method_name,
            args,
            resolved_overload,
            ..
        } => {
            if let Some(recv) = receiver {
                scan_expr_mutations_and_moves(
                    recv,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
            for arg in args {
                scan_expr_mutations_and_moves(
                    &arg.expr,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }

            // 1. Check if receiver is mutated by callee
            let callee_mutates_self = if let Some(mid) = resolved_overload {
                symtab
                    .methods
                    .get(mid)
                    .map(|m| m.inferred_self_borrow == BorrowMode::MutBorrow)
                    .unwrap_or(false)
            } else if let Some(recv) = receiver {
                let recv_ty = recv
                    .resolved_type
                    .as_ref()
                    .or_else(|| extract_root_ident(recv).and_then(|n| var_types.get(&n)));
                if let Some(rty) = recv_ty {
                    let tkey = normalize_primitive_type_key(rty.short_name());
                    lookup_intrinsic(tkey, method_name, intrinsics)
                        .map(|spec| spec.self_borrow == BorrowMode::MutBorrow)
                        .unwrap_or(false)
                } else {
                    matches!(
                        method_name.as_str(),
                        "Add" | "Remove" | "RemoveAt" | "Clear" | "Insert" | "Pop" | "Sort"
                    )
                }
            } else {
                false
            };

            if callee_mutates_self {
                if let Some(recv) = receiver {
                    if let Some(root) = extract_root_ident(recv) {
                        if root == "this" || type_field_names.contains(&root) {
                            *self_mutated = true;
                        } else {
                            mutated_vars.insert(root);
                        }
                    }
                } else {
                    *self_mutated = true;
                }
            }

            // 2. Check parameter borrow modes on callee (either project method or primitive intrinsic)
            if let Some(mid) = resolved_overload {
                if let Some(msym) = symtab.methods.get(mid) {
                    for (i, arg) in args.iter().enumerate() {
                        if let Some(psym) = msym.params.get(i) {
                            if let ExprKind::Identifier { name, .. } = &arg.expr.kind {
                                match psym.inferred_borrow {
                                    BorrowMode::MutBorrow => {
                                        mutated_vars.insert(name.clone());
                                    }
                                    BorrowMode::OwnedMove => {
                                        moved_vars.insert(name.clone());
                                    }
                                    _ => {}
                                }
                            }
                        }
                    }
                }
            } else if let Some(recv) = receiver {
                let recv_ty = recv
                    .resolved_type
                    .as_ref()
                    .or_else(|| extract_root_ident(recv).and_then(|n| var_types.get(&n)));
                if let Some(rty) = recv_ty {
                    let tkey = normalize_primitive_type_key(rty.short_name());
                    if let Some(spec) = lookup_intrinsic(tkey, method_name, intrinsics) {
                        for (i, arg) in args.iter().enumerate() {
                            if let Some(&pmode) = spec.param_borrows.get(i) {
                                if let ExprKind::Identifier { name, .. } = &arg.expr.kind {
                                    match pmode {
                                        BorrowMode::MutBorrow => {
                                            mutated_vars.insert(name.clone());
                                        }
                                        BorrowMode::OwnedMove => {
                                            moved_vars.insert(name.clone());
                                        }
                                        _ => {}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        ExprKind::Construct { args, .. } => {
            for arg in args {
                // Passing an identifier into a record/struct constructor consumes ownership
                if let ExprKind::Identifier { name, .. } = &arg.expr.kind {
                    moved_vars.insert(name.clone());
                }
                scan_expr_mutations_and_moves(
                    &arg.expr,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
        }

        ExprKind::MemberAccess { target, .. } => {
            scan_expr_mutations_and_moves(
                target,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            scan_expr_mutations_and_moves(
                left,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            scan_expr_mutations_and_moves(
                right,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            scan_expr_mutations_and_moves(
                operand,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        ExprKind::IndexAccess { target, indices } => {
            scan_expr_mutations_and_moves(
                target,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            for idx in indices {
                scan_expr_mutations_and_moves(
                    &idx.expr,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                scan_expr_mutations_and_moves(
                    t,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
            if let Some(s) = start {
                scan_expr_mutations_and_moves(
                    s,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
            if let Some(e) = end {
                scan_expr_mutations_and_moves(
                    e,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => {
                scan_expr_mutations_and_moves(
                    e,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
            LambdaBody::Block(b) => {
                scan_block_mutations_and_moves(
                    b,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
        },
        ExprKind::Switch { scrutinee, arms } => {
            scan_expr_mutations_and_moves(
                scrutinee,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
            for arm in arms {
                if let Some(g) = &arm.guard {
                    scan_expr_mutations_and_moves(
                        g,
                        type_field_names,
                        var_types,
                        intrinsics,
                        symtab,
                        mutated_vars,
                        moved_vars,
                        self_mutated,
                    );
                }
                scan_expr_mutations_and_moves(
                    &arm.body,
                    type_field_names,
                    var_types,
                    intrinsics,
                    symtab,
                    mutated_vars,
                    moved_vars,
                    self_mutated,
                );
            }
        }
        ExprKind::LinqChain(chain) => {
            scan_expr_mutations_and_moves(
                &chain.source,
                type_field_names,
                var_types,
                intrinsics,
                symtab,
                mutated_vars,
                moved_vars,
                self_mutated,
            );
        }
        ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::Identifier { .. }
        | ExprKind::This
        | ExprKind::Base => {}
    }
}

fn annotate_type_call_sites_and_locals(
    type_decl: &mut TypeDecl,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) {
    let type_field_names: HashSet<String> = type_decl
        .primary_ctor_params
        .iter()
        .map(|p| p.name.clone())
        .chain(type_decl.members.iter().filter_map(|m| match m {
            MemberDecl::Field(f) => Some(f.name.clone()),
            MemberDecl::Property(p) => Some(p.name.clone()),
            _ => None,
        }))
        .collect();

    for member in &mut type_decl.members {
        match member {
            MemberDecl::Method(method) => {
                let param_borrows: HashMap<String, BorrowMode> = method
                    .params
                    .iter()
                    .map(|p| (p.name.clone(), p.inferred_borrow))
                    .collect();
                let mut var_types: HashMap<String, TypeRef> = method
                    .params
                    .iter()
                    .map(|p| (p.name.clone(), p.ty.clone()))
                    .collect();

                if let Some(body) = &mut method.body {
                    let mut mutated_vars = HashSet::new();
                    let mut moved_vars = HashSet::new();
                    let mut self_mutated = false;

                    scan_block_mutations_and_moves(
                        body,
                        &type_field_names,
                        &var_types,
                        intrinsics,
                        symtab,
                        &mut mutated_vars,
                        &mut moved_vars,
                        &mut self_mutated,
                    );

                    annotate_block_coercions_and_mut(
                        body,
                        &mutated_vars,
                        &param_borrows,
                        &mut var_types,
                        intrinsics,
                        symtab,
                    );
                }
            }
            MemberDecl::Constructor(ctor) => {
                let param_borrows: HashMap<String, BorrowMode> = ctor
                    .params
                    .iter()
                    .map(|p| (p.name.clone(), p.inferred_borrow))
                    .collect();
                let mut var_types: HashMap<String, TypeRef> = ctor
                    .params
                    .iter()
                    .map(|p| (p.name.clone(), p.ty.clone()))
                    .collect();

                if let Some(body) = &mut ctor.body {
                    let mut mutated_vars = HashSet::new();
                    let mut moved_vars = HashSet::new();
                    let mut self_mutated = false;

                    scan_block_mutations_and_moves(
                        body,
                        &type_field_names,
                        &var_types,
                        intrinsics,
                        symtab,
                        &mut mutated_vars,
                        &mut moved_vars,
                        &mut self_mutated,
                    );

                    annotate_block_coercions_and_mut(
                        body,
                        &mutated_vars,
                        &param_borrows,
                        &mut var_types,
                        intrinsics,
                        symtab,
                    );
                }
            }
            _ => {}
        }
    }
}

fn annotate_block_coercions_and_mut(
    block: &mut Block,
    mutated_vars: &HashSet<String>,
    param_borrows: &HashMap<String, BorrowMode>,
    var_types: &mut HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) {
    for stmt in &mut block.stmts {
        annotate_stmt_coercions_and_mut(
            stmt,
            mutated_vars,
            param_borrows,
            var_types,
            intrinsics,
            symtab,
        );
    }
}

fn annotate_stmt_coercions_and_mut(
    stmt: &mut Stmt,
    mutated_vars: &HashSet<String>,
    param_borrows: &HashMap<String, BorrowMode>,
    var_types: &mut HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) {
    match stmt {
        Stmt::Block(b) => {
            let mut inner_types = var_types.clone();
            annotate_block_coercions_and_mut(
                b,
                mutated_vars,
                param_borrows,
                &mut inner_types,
                intrinsics,
                symtab,
            );
        }
        Stmt::LocalVar {
            name,
            explicit_type,
            init,
            inferred_mut,
            inferred_type,
            ..
        } => {
            annotate_expr_coercions(init, param_borrows, var_types, intrinsics, symtab);
            if mutated_vars.contains(name) {
                *inferred_mut = true;
            }
            if let Some(ty) = explicit_type
                .clone()
                .or_else(|| inferred_type.clone())
                .or_else(|| init.resolved_type.clone())
            {
                var_types.insert(name.clone(), ty);
            }
        }
        Stmt::UsingResource {
            name,
            explicit_type,
            init,
            inferred_mut,
            ..
        } => {
            annotate_expr_coercions(init, param_borrows, var_types, intrinsics, symtab);
            if mutated_vars.contains(name) {
                *inferred_mut = true;
            }
            if let Some(ty) = explicit_type.clone().or_else(|| init.resolved_type.clone()) {
                var_types.insert(name.clone(), ty);
            }
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            annotate_expr_coercions(cond, param_borrows, var_types, intrinsics, symtab);
            annotate_stmt_coercions_and_mut(
                then_branch,
                mutated_vars,
                param_borrows,
                var_types,
                intrinsics,
                symtab,
            );
            if let Some(el) = else_branch {
                annotate_stmt_coercions_and_mut(
                    el,
                    mutated_vars,
                    param_borrows,
                    var_types,
                    intrinsics,
                    symtab,
                );
            }
        }
        Stmt::While { cond, body, .. } => {
            annotate_expr_coercions(cond, param_borrows, var_types, intrinsics, symtab);
            annotate_stmt_coercions_and_mut(
                body,
                mutated_vars,
                param_borrows,
                var_types,
                intrinsics,
                symtab,
            );
        }
        Stmt::ForEach {
            item_name,
            collection,
            body,
            iter_borrow_mode,
            ..
        } => {
            annotate_expr_coercions(collection, param_borrows, var_types, intrinsics, symtab);
            if *iter_borrow_mode == BorrowMode::Unresolved {
                *iter_borrow_mode = if mutated_vars.contains(item_name) {
                    BorrowMode::MutBorrow
                } else {
                    BorrowMode::ReadBorrow
                };
            }
            annotate_stmt_coercions_and_mut(
                body,
                mutated_vars,
                param_borrows,
                var_types,
                intrinsics,
                symtab,
            );
        }
        Stmt::Return { value: Some(v), .. } => {
            annotate_expr_coercions(v, param_borrows, var_types, intrinsics, symtab);
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            annotate_expr_coercions(error_expr, param_borrows, var_types, intrinsics, symtab);
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            annotate_block_coercions_and_mut(
                try_block,
                mutated_vars,
                param_borrows,
                var_types,
                intrinsics,
                symtab,
            );
            for c in catches {
                let mut catch_types = var_types.clone();
                if let Some(vname) = &c.var_name {
                    catch_types.insert(vname.clone(), c.error_type.clone());
                }
                annotate_block_coercions_and_mut(
                    &mut c.body,
                    mutated_vars,
                    param_borrows,
                    &mut catch_types,
                    intrinsics,
                    symtab,
                );
            }
        }
        Stmt::ExprStmt { expr, .. } => {
            annotate_expr_coercions(expr, param_borrows, var_types, intrinsics, symtab);
        }
    }
}

fn annotate_expr_coercions(
    expr: &mut Expr,
    param_borrows: &HashMap<String, BorrowMode>,
    var_types: &HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) {
    match &mut expr.kind {
        ExprKind::MethodCall {
            receiver,
            method_name,
            args,
            resolved_overload,
            ..
        } => {
            if let Some(recv) = receiver {
                annotate_expr_coercions(recv, param_borrows, var_types, intrinsics, symtab);
            }
            for arg in args.iter_mut() {
                annotate_expr_coercions(
                    &mut arg.expr,
                    param_borrows,
                    var_types,
                    intrinsics,
                    symtab,
                );
            }

            if let Some(mid) = resolved_overload {
                if let Some(msym) = symtab.methods.get(mid) {
                    for (i, arg) in args.iter_mut().enumerate() {
                        if let Some(psym) = msym.params.get(i) {
                            arg.expr.caller_coercion = compute_arg_coercion(
                                &arg.expr,
                                psym.inferred_borrow,
                                param_borrows,
                            );
                        }
                    }
                }
            } else if let Some(recv) = receiver {
                let recv_ty = recv
                    .resolved_type
                    .as_ref()
                    .or_else(|| extract_root_ident(recv).and_then(|n| var_types.get(&n)));
                if let Some(rty) = recv_ty {
                    let tkey = normalize_primitive_type_key(rty.short_name());
                    if let Some(spec) = lookup_intrinsic(tkey, method_name, intrinsics) {
                        for (i, arg) in args.iter_mut().enumerate() {
                            if let Some(&target_mode) = spec.param_borrows.get(i) {
                                arg.expr.caller_coercion =
                                    compute_arg_coercion(&arg.expr, target_mode, param_borrows);
                            }
                        }
                    }
                }
            }
        }

        ExprKind::Construct {
            args,
            resolved_ctor,
            ..
        } => {
            for arg in args.iter_mut() {
                annotate_expr_coercions(
                    &mut arg.expr,
                    param_borrows,
                    var_types,
                    intrinsics,
                    symtab,
                );
            }
            if let Some(cid) = resolved_ctor {
                if let Some(csym) = symtab.methods.get(cid) {
                    for (i, arg) in args.iter_mut().enumerate() {
                        if let Some(psym) = csym.params.get(i) {
                            arg.expr.caller_coercion = compute_arg_coercion(
                                &arg.expr,
                                psym.inferred_borrow,
                                param_borrows,
                            );
                        }
                    }
                }
            }
        }

        ExprKind::Assignment { target, value, .. } => {
            annotate_expr_coercions(target, param_borrows, var_types, intrinsics, symtab);
            annotate_expr_coercions(value, param_borrows, var_types, intrinsics, symtab);
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            annotate_expr_coercions(left, param_borrows, var_types, intrinsics, symtab);
            annotate_expr_coercions(right, param_borrows, var_types, intrinsics, symtab);
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            annotate_expr_coercions(operand, param_borrows, var_types, intrinsics, symtab);
        }
        ExprKind::MemberAccess { target, .. } => {
            annotate_expr_coercions(target, param_borrows, var_types, intrinsics, symtab);
        }
        ExprKind::IndexAccess { target, indices } => {
            annotate_expr_coercions(target, param_borrows, var_types, intrinsics, symtab);
            for idx in indices {
                annotate_expr_coercions(
                    &mut idx.expr,
                    param_borrows,
                    var_types,
                    intrinsics,
                    symtab,
                );
            }
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                annotate_expr_coercions(t, param_borrows, var_types, intrinsics, symtab);
            }
            if let Some(s) = start {
                annotate_expr_coercions(s, param_borrows, var_types, intrinsics, symtab);
            }
            if let Some(e) = end {
                annotate_expr_coercions(e, param_borrows, var_types, intrinsics, symtab);
            }
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => {
                annotate_expr_coercions(e, param_borrows, var_types, intrinsics, symtab);
            }
            LambdaBody::Block(b) => {
                let mut inner_types = var_types.clone();
                let empty_muts = HashSet::new();
                annotate_block_coercions_and_mut(
                    b,
                    &empty_muts,
                    param_borrows,
                    &mut inner_types,
                    intrinsics,
                    symtab,
                );
            }
        },
        ExprKind::Switch { scrutinee, arms } => {
            annotate_expr_coercions(scrutinee, param_borrows, var_types, intrinsics, symtab);
            for arm in arms {
                if let Some(g) = &mut arm.guard {
                    annotate_expr_coercions(g, param_borrows, var_types, intrinsics, symtab);
                }
                annotate_expr_coercions(
                    &mut arm.body,
                    param_borrows,
                    var_types,
                    intrinsics,
                    symtab,
                );
            }
        }
        ExprKind::LinqChain(chain) => {
            annotate_expr_coercions(
                &mut chain.source,
                param_borrows,
                var_types,
                intrinsics,
                symtab,
            );
        }
        ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::Identifier { .. }
        | ExprKind::This
        | ExprKind::Base => {}
    }
}

fn compute_arg_coercion(
    arg_expr: &Expr,
    target_mode: BorrowMode,
    caller_param_borrows: &HashMap<String, BorrowMode>,
) -> CallerArgCoercion {
    match target_mode {
        BorrowMode::MutBorrow => CallerArgCoercion::BorrowMutable,
        BorrowMode::ReadBorrow => {
            // If passing a caller parameter that is already `ReadBorrow` (`&T` or `&str`),
            // or a string literal (`"SAVE10"`), or a range slice (`buf[0..16]`),
            // we still mark `BorrowShared` so Pass 3 can emit `&*param` (when re-borrowing `&mut T`)
            // or `&local` cleanly.
            if let ExprKind::Identifier { name, .. } = &arg_expr.kind {
                if let Some(&caller_mode) = caller_param_borrows.get(name) {
                    if caller_mode == BorrowMode::ReadBorrow {
                        return CallerArgCoercion::BorrowShared;
                    }
                }
            }
            CallerArgCoercion::BorrowShared
        }
        BorrowMode::SharedArc => CallerArgCoercion::ArcClone,
        BorrowMode::OwnedMove | BorrowMode::CopyValue | BorrowMode::Unresolved => {
            CallerArgCoercion::None
        }
    }
}

fn sync_method_to_symtab(method: &MethodDecl, symtab: &mut GlobalSymbolTable) {
    if let Some(msym) = symtab.methods.get_mut(&method.id) {
        msym.inferred_self_borrow = method.inferred_self_borrow;
        for (i, p) in method.params.iter().enumerate() {
            if let Some(psym) = msym.params.get_mut(i) {
                psym.inferred_borrow = p.inferred_borrow;
            }
        }
    }
}

fn is_service_type(ty: &TypeRef, symtab: &GlobalSymbolTable) -> bool {
    if let Some(candidates) = symtab.short_name_index.get(ty.short_name()) {
        for &cid in candidates {
            if let Some(tsym) = symtab.types.get(&cid) {
                if matches!(tsym.kind, TypeKind::ServiceClass) {
                    return true;
                }
            }
        }
    }
    false
}

pub fn extract_root_ident(expr: &Expr) -> Option<String> {
    match &expr.kind {
        ExprKind::Identifier { name, .. } => Some(name.clone()),
        ExprKind::This => Some("this".to_string()),
        ExprKind::MemberAccess { target, member, .. } => {
            if matches!(target.kind, ExprKind::This) {
                Some(member.clone())
            } else {
                extract_root_ident(target)
            }
        }
        ExprKind::IndexAccess { target, .. } => extract_root_ident(target),
        _ => None,
    }
}
