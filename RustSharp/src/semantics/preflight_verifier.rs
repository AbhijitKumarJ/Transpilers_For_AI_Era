use std::collections::{HashMap, HashSet};

use crate::diagnostics::{DiagnosticEngine, SourceSpan};
use crate::frontend::ast::{
    Block, BorrowMode, CompilationUnit, Expr, ExprKind, ImportDecl, LambdaBody, MemberDecl,
    MethodDecl, Stmt, TypeDecl, TypeKind, TypeRef,
};
use crate::semantics::archetype_analyzer::is_copy_type_ref;
use crate::semantics::primitive_resolver::{
    build_builtin_primitive_table, lookup_intrinsic, normalize_primitive_type_key,
    IntrinsicMemberSpec,
};
use crate::semantics::symbols::GlobalSymbolTable;

/// Pass 2.5 Pre-Flight Ownership & Aliasing Verifier.
///
/// Inspects the decorated `.rsharp` AST *before* Rust code generation to catch
/// ownership and aliasing violations and report C#-ergonomic diagnostics with exact
/// `.rsharp` source file, line, and column locations:
/// - **RSHARP001 (Service State Mutation):** Prevents mutating fields or calling `&mut self`
///   methods on fields of a `service class` outside its constructor (unless the field is a
///   `shared class` or `SharedState<T>`).
/// - **RSHARP002 (Concurrent Collection Aliasing):** Prevents mutating a collection (e.g.,
///   `.Add()`, `.Remove()`, `.Clear()`, index assignment) while iterating over it in a `foreach` loop.
/// - **RSHARP003 (Use-After-Move on Linear Resource):** Prevents using a linear/non-Copy
///   resource (such as an `IDisposable` handle or `[Moves]`-consumed variable) after ownership
///   has been moved.
pub fn run_preflight_ownership_checks(
    units: &[CompilationUnit],
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    let intrinsics = build_builtin_primitive_table();

    for unit in units {
        if unit.is_ambient_stub {
            continue;
        }
        for type_decl in &unit.types {
            verify_type_decl(
                type_decl,
                &unit.namespace,
                &unit.imports,
                &intrinsics,
                symtab,
                diag,
            );
        }
    }
}

struct VerificationContext<'a> {
    type_decl: &'a TypeDecl,
    is_service_class: bool,
    in_constructor: bool,
    current_ns: &'a [String],
    imports: &'a [ImportDecl],
    /// Maps field/property names of the enclosing type to their declared `TypeRef`.
    type_fields: HashMap<String, TypeRef>,
    /// Maps local variable and parameter names to their `TypeRef`.
    local_types: HashMap<String, TypeRef>,
    /// Tracks active collection identifiers currently being iterated in enclosing `foreach` loops.
    active_foreach_collections: Vec<String>,
    /// Tracks variables whose ownership has already been moved (`var_name -> moved_at_span`).
    moved_vars: HashMap<String, SourceSpan>,
    /// Tracks variables already reported for RSHARP003 to avoid duplicate cascading errors.
    reported_use_after_move: HashSet<String>,
    intrinsics: &'a HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &'a GlobalSymbolTable,
}

fn verify_type_decl(
    type_decl: &TypeDecl,
    current_ns: &[String],
    imports: &[ImportDecl],
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    let is_service_class = matches!(type_decl.kind, TypeKind::ServiceClass);

    let mut type_fields: HashMap<String, TypeRef> = HashMap::new();
    for p in &type_decl.primary_ctor_params {
        type_fields.insert(p.name.clone(), p.ty.clone());
    }
    for member in &type_decl.members {
        match member {
            MemberDecl::Field(f) => {
                type_fields.insert(f.name.clone(), f.ty.clone());
            }
            MemberDecl::Property(p) => {
                type_fields.insert(p.name.clone(), p.ty.clone());
            }
            _ => {}
        }
    }

    for member in &type_decl.members {
        match member {
            MemberDecl::Method(method) => {
                verify_method_body(
                    type_decl,
                    method,
                    is_service_class,
                    current_ns,
                    imports,
                    &type_fields,
                    intrinsics,
                    symtab,
                    diag,
                );
            }
            MemberDecl::Constructor(ctor) => {
                if let Some(body) = &ctor.body {
                    let mut local_types = HashMap::new();
                    for p in &ctor.params {
                        local_types.insert(p.name.clone(), p.ty.clone());
                    }
                    let mut ctx = VerificationContext {
                        type_decl,
                        is_service_class,
                        in_constructor: true,
                        current_ns,
                        imports,
                        type_fields: type_fields.clone(),
                        local_types,
                        active_foreach_collections: Vec::new(),
                        moved_vars: HashMap::new(),
                        reported_use_after_move: HashSet::new(),
                        intrinsics,
                        symtab,
                    };
                    verify_block(body, &mut ctx, diag);
                }
            }
            MemberDecl::Property(prop) => {
                for acc in &prop.accessors {
                    if let Some(body) = &acc.body {
                        let mut ctx = VerificationContext {
                            type_decl,
                            is_service_class,
                            in_constructor: false,
                            current_ns,
                            imports,
                            type_fields: type_fields.clone(),
                            local_types: HashMap::new(),
                            active_foreach_collections: Vec::new(),
                            moved_vars: HashMap::new(),
                            reported_use_after_move: HashSet::new(),
                            intrinsics,
                            symtab,
                        };
                        verify_block(body, &mut ctx, diag);
                    }
                }
            }
            _ => {}
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn verify_method_body(
    type_decl: &TypeDecl,
    method: &MethodDecl,
    is_service_class: bool,
    current_ns: &[String],
    imports: &[ImportDecl],
    type_fields: &HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    let Some(body) = &method.body else {
        return;
    };

    let mut local_types = HashMap::new();
    for p in &method.params {
        local_types.insert(p.name.clone(), p.ty.clone());
    }

    let mut ctx = VerificationContext {
        type_decl,
        is_service_class,
        in_constructor: false,
        current_ns,
        imports,
        type_fields: type_fields.clone(),
        local_types,
        active_foreach_collections: Vec::new(),
        moved_vars: HashMap::new(),
        reported_use_after_move: HashSet::new(),
        intrinsics,
        symtab,
    };

    verify_block(body, &mut ctx, diag);
}

fn verify_block(block: &Block, ctx: &mut VerificationContext<'_>, diag: &mut DiagnosticEngine) {
    for stmt in &block.stmts {
        verify_stmt(stmt, ctx, diag);
    }
}

fn verify_stmt(stmt: &Stmt, ctx: &mut VerificationContext<'_>, diag: &mut DiagnosticEngine) {
    match stmt {
        Stmt::Block(b) => {
            verify_block(b, ctx, diag);
        }

        Stmt::LocalVar {
            name,
            explicit_type,
            init,
            inferred_type,
            ..
        } => {
            verify_expr(init, ctx, diag);

            // Moving a linear local variable into a new binding `var b = a;` consumes `a`
            if let ExprKind::Identifier { name: rhs_name, .. } = &init.kind {
                if let Some(rhs_ty) = ctx.local_types.get(rhs_name) {
                    if is_linear_move_tracked_type(rhs_ty, ctx) {
                        ctx.moved_vars.insert(rhs_name.clone(), init.span.clone());
                    }
                }
            }

            if let Some(ty) = explicit_type
                .clone()
                .or_else(|| inferred_type.clone())
                .or_else(|| init.resolved_type.clone())
            {
                ctx.local_types.insert(name.clone(), ty);
            }
            // Re-binding clears any prior move state for that variable name
            ctx.moved_vars.remove(name);
        }

        Stmt::UsingResource {
            name,
            explicit_type,
            init,
            ..
        } => {
            verify_expr(init, ctx, diag);
            if let Some(ty) = explicit_type.clone().or_else(|| init.resolved_type.clone()) {
                ctx.local_types.insert(name.clone(), ty);
            }
            ctx.moved_vars.remove(name);
        }

        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            verify_expr(cond, ctx, diag);

            let saved_moves = ctx.moved_vars.clone();
            verify_stmt(then_branch, ctx, diag);
            let then_moves = ctx.moved_vars.clone();

            ctx.moved_vars = saved_moves;
            if let Some(el) = else_branch {
                verify_stmt(el, ctx, diag);
            }
            // Merge moves from either branch so subsequent code after `if/else` catches use-after-move
            for (k, span) in then_moves {
                ctx.moved_vars.entry(k).or_insert(span);
            }
        }

        Stmt::While { cond, body, .. } => {
            verify_expr(cond, ctx, diag);
            verify_stmt(body, ctx, diag);
        }

        Stmt::ForEach {
            item_name,
            item_type,
            collection,
            body,
            ..
        } => {
            verify_expr(collection, ctx, diag);

            if let Some(ty) = item_type.clone().or_else(|| {
                collection
                    .resolved_type
                    .as_ref()
                    .and_then(|ct| ct.type_args.first().cloned())
            }) {
                ctx.local_types.insert(item_name.clone(), ty);
            }

            let pushed_coll = extract_collection_key(collection, &ctx.type_fields);
            if let Some(ref coll_key) = pushed_coll {
                ctx.active_foreach_collections.push(coll_key.clone());
            }

            verify_stmt(body, ctx, diag);

            if pushed_coll.is_some() {
                ctx.active_foreach_collections.pop();
            }
        }

        Stmt::Return { value: Some(v), .. } => {
            verify_expr(v, ctx, diag);
            if let ExprKind::Identifier { name, .. } = &v.kind {
                if let Some(ty) = ctx.local_types.get(name) {
                    if is_linear_move_tracked_type(ty, ctx) {
                        ctx.moved_vars.insert(name.clone(), v.span.clone());
                    }
                }
            }
        }

        Stmt::Return { value: None, .. } => {}

        Stmt::Throw { error_expr, .. } => {
            verify_expr(error_expr, ctx, diag);
        }

        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            verify_block(try_block, ctx, diag);
            for c in catches {
                if let Some(vname) = &c.var_name {
                    ctx.local_types.insert(vname.clone(), c.error_type.clone());
                }
                verify_block(&c.body, ctx, diag);
            }
        }

        Stmt::ExprStmt { expr, .. } => {
            verify_expr(expr, ctx, diag);
        }
    }
}

fn verify_expr(expr: &Expr, ctx: &mut VerificationContext<'_>, diag: &mut DiagnosticEngine) {
    match &expr.kind {
        ExprKind::Identifier { name, .. } => {
            check_use_after_move(name, &expr.span, ctx, diag);
        }

        ExprKind::Assignment { target, value, .. } => {
            // Verify RHS first
            verify_expr(value, ctx, diag);
            // Verify target expressions (e.g., index expressions)
            verify_assignment_target_subexprs(target, ctx, diag);

            // 1. Rule RSHARP001: Check if assignment mutates a `service class` field outside constructor
            if ctx.is_service_class && !ctx.in_constructor {
                if let Some(field_name) = extract_service_field_target(target, &ctx.type_fields) {
                    if !is_interior_mutable_field(&field_name, ctx) {
                        diag.report_rsharp001(expr.span.clone(), &ctx.type_decl.name, &field_name);
                    }
                }
            }

            // 2. Rule RSHARP002: Check if assignment mutates an active `foreach` collection (`list[i] = x`)
            if let ExprKind::IndexAccess {
                target: idx_target, ..
            } = &target.kind
            {
                if let Some(coll_key) = extract_collection_key(idx_target, &ctx.type_fields) {
                    if ctx.active_foreach_collections.contains(&coll_key) {
                        diag.report_rsharp002(expr.span.clone(), &coll_key);
                    }
                }
            }

            // Re-assigning a moved variable restores its validity
            if let ExprKind::Identifier { name, .. } = &target.kind {
                ctx.moved_vars.remove(name);
            }
        }

        ExprKind::MethodCall {
            receiver,
            method_name,
            args,
            resolved_overload,
            ..
        } => {
            if let Some(recv) = receiver {
                verify_expr(recv, ctx, diag);
            }

            // Evaluate arguments and check for RSHARP003 use-after-move
            for arg in args {
                verify_expr(&arg.expr, ctx, diag);
            }

            let mutates_receiver = is_receiver_mutating_call(
                receiver.as_deref(),
                method_name,
                *resolved_overload,
                ctx,
            );

            if let Some(recv) = receiver {
                // 1. Rule RSHARP001: Calling a `&mut self` method on a `service class` field
                if mutates_receiver && ctx.is_service_class && !ctx.in_constructor {
                    if let Some(field_name) = extract_service_field_target(recv, &ctx.type_fields) {
                        if !is_interior_mutable_field(&field_name, ctx) {
                            diag.report_rsharp001(
                                expr.span.clone(),
                                &ctx.type_decl.name,
                                &field_name,
                            );
                        }
                    }
                }

                // 2. Rule RSHARP002: Calling a `&mut self` method on a collection currently iterated in `foreach`
                if mutates_receiver {
                    if let Some(coll_key) = extract_collection_key(recv, &ctx.type_fields) {
                        if ctx.active_foreach_collections.contains(&coll_key) {
                            diag.report_rsharp002(expr.span.clone(), &coll_key);
                        }
                    }
                }
            }

            // 3. Rule RSHARP003: Record any arguments consumed by `[Moves]` / `BorrowMode::OwnedMove`
            for (i, arg) in args.iter().enumerate() {
                if let ExprKind::Identifier { name: arg_var, .. } = &arg.expr.kind {
                    if is_argument_consumed_by_callee(
                        receiver.as_deref(),
                        method_name,
                        *resolved_overload,
                        i,
                        arg_var,
                        ctx,
                    ) {
                        ctx.moved_vars
                            .entry(arg_var.clone())
                            .or_insert_with(|| arg.expr.span.clone());
                    }
                }
            }
        }

        ExprKind::Construct {
            args,
            resolved_ctor,
            ..
        } => {
            for (i, arg) in args.iter().enumerate() {
                verify_expr(&arg.expr, ctx, diag);

                if let ExprKind::Identifier { name: arg_var, .. } = &arg.expr.kind {
                    let is_linear = ctx
                        .local_types
                        .get(arg_var)
                        .map(|ty| is_linear_move_tracked_type(ty, ctx))
                        .unwrap_or(false);

                    let ctor_moves = resolved_ctor
                        .and_then(|cid| ctx.symtab.methods.get(&cid))
                        .and_then(|csym| csym.params.get(i))
                        .map(|psym| psym.inferred_borrow == BorrowMode::OwnedMove)
                        .unwrap_or(true);

                    if is_linear && ctor_moves {
                        ctx.moved_vars
                            .entry(arg_var.clone())
                            .or_insert_with(|| arg.expr.span.clone());
                    }
                }
            }
        }

        ExprKind::MemberAccess { target, .. } => {
            verify_expr(target, ctx, diag);
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            verify_expr(left, ctx, diag);
            verify_expr(right, ctx, diag);
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            verify_expr(operand, ctx, diag);
        }
        ExprKind::IndexAccess { target, indices } => {
            verify_expr(target, ctx, diag);
            for idx in indices {
                verify_expr(&idx.expr, ctx, diag);
            }
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                verify_expr(t, ctx, diag);
            }
            if let Some(s) = start {
                verify_expr(s, ctx, diag);
            }
            if let Some(e) = end {
                verify_expr(e, ctx, diag);
            }
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => verify_expr(e, ctx, diag),
            LambdaBody::Block(b) => verify_block(b, ctx, diag),
        },
        ExprKind::Switch { scrutinee, arms } => {
            verify_expr(scrutinee, ctx, diag);
            for arm in arms {
                if let Some(g) = &arm.guard {
                    verify_expr(g, ctx, diag);
                }
                verify_expr(&arm.body, ctx, diag);
            }
        }
        ExprKind::LinqChain(chain) => {
            verify_expr(&chain.source, ctx, diag);
            for op in &chain.ops {
                match op {
                    crate::frontend::ast::LinqOp::Where { predicate } => {
                        verify_expr(predicate, ctx, diag);
                    }
                    crate::frontend::ast::LinqOp::Select { selector }
                    | crate::frontend::ast::LinqOp::SelectMany { selector } => {
                        verify_expr(selector, ctx, diag);
                    }
                    crate::frontend::ast::LinqOp::Take { count }
                    | crate::frontend::ast::LinqOp::Skip { count } => {
                        verify_expr(count, ctx, diag);
                    }
                    crate::frontend::ast::LinqOp::OrderBy { key_selector, .. } => {
                        verify_expr(key_selector, ctx, diag);
                    }
                    crate::frontend::ast::LinqOp::WithIndex
                    | crate::frontend::ast::LinqOp::Distinct
                    | crate::frontend::ast::LinqOp::Reverse => {}
                }
            }
        }
        ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::This
        | ExprKind::Base => {}
    }
}

fn verify_assignment_target_subexprs(
    target: &Expr,
    ctx: &mut VerificationContext<'_>,
    diag: &mut DiagnosticEngine,
) {
    match &target.kind {
        ExprKind::MemberAccess { target: inner, .. } => {
            verify_expr(inner, ctx, diag);
        }
        ExprKind::IndexAccess {
            target: inner,
            indices,
        } => {
            verify_expr(inner, ctx, diag);
            for idx in indices {
                verify_expr(&idx.expr, ctx, diag);
            }
        }
        _ => {}
    }
}

fn check_use_after_move(
    var_name: &str,
    span: &SourceSpan,
    ctx: &mut VerificationContext<'_>,
    diag: &mut DiagnosticEngine,
) {
    if let Some(moved_at) = ctx.moved_vars.get(var_name) {
        if ctx.reported_use_after_move.insert(var_name.to_string()) {
            diag.report_rsharp003(span.clone(), var_name, moved_at);
        }
    }
}

fn extract_service_field_target(
    expr: &Expr,
    type_fields: &HashMap<String, TypeRef>,
) -> Option<String> {
    match &expr.kind {
        ExprKind::Identifier { name, .. } => {
            if type_fields.contains_key(name) {
                Some(name.clone())
            } else {
                None
            }
        }
        ExprKind::MemberAccess { target, member, .. } => {
            if matches!(target.kind, ExprKind::This) && type_fields.contains_key(member) {
                Some(member.clone())
            } else {
                extract_service_field_target(target, type_fields)
            }
        }
        ExprKind::IndexAccess { target, .. } => extract_service_field_target(target, type_fields),
        _ => None,
    }
}

fn is_interior_mutable_field(field_name: &str, ctx: &VerificationContext<'_>) -> bool {
    let Some(field_ty) = ctx.type_fields.get(field_name) else {
        return false;
    };
    if field_ty.short_name() == "SharedState" {
        return true;
    }
    if let Some(tid) = ctx
        .symtab
        .resolve_type_ref(field_ty, ctx.current_ns, ctx.imports)
    {
        if let Some(tsym) = ctx.symtab.types.get(&tid) {
            return matches!(tsym.kind, TypeKind::SharedClass);
        }
    }
    false
}

fn extract_collection_key(expr: &Expr, type_fields: &HashMap<String, TypeRef>) -> Option<String> {
    match &expr.kind {
        ExprKind::Identifier { name, .. } => Some(name.clone()),
        ExprKind::MemberAccess { target, member, .. } => {
            if matches!(target.kind, ExprKind::This) && type_fields.contains_key(member) {
                Some(member.clone())
            } else {
                extract_collection_key(target, type_fields)
                    .map(|prefix| format!("{}.{}", prefix, member))
            }
        }
        _ => None,
    }
}

fn is_receiver_mutating_call(
    receiver: Option<&Expr>,
    method_name: &str,
    resolved_overload: Option<crate::frontend::ast::SymbolId>,
    ctx: &VerificationContext<'_>,
) -> bool {
    if let Some(mid) = resolved_overload {
        if let Some(msym) = ctx.symtab.methods.get(&mid) {
            if msym.inferred_self_borrow == BorrowMode::MutBorrow {
                return true;
            }
        }
    }

    if let Some(recv) = receiver {
        let recv_ty = recv.resolved_type.as_ref().or_else(|| {
            if let Some(key) = extract_collection_key(recv, &ctx.type_fields) {
                ctx.local_types
                    .get(&key)
                    .or_else(|| ctx.type_fields.get(&key))
            } else {
                None
            }
        });

        if let Some(rty) = recv_ty {
            let tkey = normalize_primitive_type_key(rty.short_name());
            if let Some(spec) = lookup_intrinsic(tkey, method_name, ctx.intrinsics) {
                return spec.self_borrow == BorrowMode::MutBorrow;
            }
        }
    }

    matches!(
        method_name,
        "Add" | "AddRange" | "Insert" | "Remove" | "RemoveAt" | "Pop" | "Clear" | "Sort" | "Fill"
    )
}

fn is_argument_consumed_by_callee(
    receiver: Option<&Expr>,
    method_name: &str,
    resolved_overload: Option<crate::frontend::ast::SymbolId>,
    arg_index: usize,
    arg_var_name: &str,
    ctx: &VerificationContext<'_>,
) -> bool {
    let Some(var_ty) = ctx.local_types.get(arg_var_name) else {
        return false;
    };

    // Copy primitives (`int`, `decimal`, `bool`, `struct`) are copied by value, never moved
    if is_copy_type_ref(var_ty, ctx.symtab) {
        return false;
    }

    // 1. Check resolved project/stdlib method in `GlobalSymbolTable`
    if let Some(mid) = resolved_overload {
        if let Some(msym) = ctx.symtab.methods.get(&mid) {
            if let Some(psym) = msym.params.get(arg_index) {
                if psym.explicit_constraint == Some(BorrowMode::OwnedMove) {
                    return true;
                }
                if psym.inferred_borrow == BorrowMode::OwnedMove
                    && is_linear_move_tracked_type(var_ty, ctx)
                {
                    return true;
                }
            }
        }
    }

    // 2. Check built-in `primitive` intrinsic table (e.g., `List<T>.Add([Moves] T item)`)
    if let Some(recv) = receiver {
        let recv_ty = recv.resolved_type.as_ref().or_else(|| {
            if let Some(key) = extract_collection_key(recv, &ctx.type_fields) {
                ctx.local_types
                    .get(&key)
                    .or_else(|| ctx.type_fields.get(&key))
            } else {
                None
            }
        });
        if let Some(rty) = recv_ty {
            let tkey = normalize_primitive_type_key(rty.short_name());
            if let Some(spec) = lookup_intrinsic(tkey, method_name, ctx.intrinsics) {
                if let Some(&pmode) = spec.param_borrows.get(arg_index) {
                    if pmode == BorrowMode::OwnedMove && is_linear_move_tracked_type(var_ty, ctx) {
                        return true;
                    }
                }
            }
        }
    }

    false
}

fn is_linear_move_tracked_type(ty: &TypeRef, ctx: &VerificationContext<'_>) -> bool {
    if is_copy_type_ref(ty, ctx.symtab) {
        return false;
    }
    if let Some(tid) = ctx.symtab.resolve_type_ref(ty, ctx.current_ns, ctx.imports) {
        if let Some(tsym) = ctx.symtab.types.get(&tid) {
            if tsym.has_disposable_drop {
                return true;
            }
            if matches!(tsym.kind, TypeKind::StandardClass) {
                return true;
            }
        }
    }
    false
}
