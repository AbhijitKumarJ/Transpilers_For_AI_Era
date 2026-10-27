Here are the complete, raw individual source files for **Milestone 5 (Pass 2.5: Pre-Flight Ownership & Aliasing Verifier `src/semantics/preflight_verifier.rs` enforcing rules `RSHARP001`–`RSHARP003`, updated `src/semantics/mod.rs` and `src/lib.rs`, and `tests/m5_preflight_diagnostics_tests.rs`)** of the **RustSharp Prototype Transpiler (`rsharpc`)**.

---

### `src/semantics/preflight_verifier.rs`

```rust
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
                        diag.report_rsharp001(
                            expr.span.clone(),
                            &ctx.type_decl.name,
                            &field_name,
                        );
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
                    crate::frontend::ast::LinqOp::WithIndex => {}
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

fn extract_collection_key(
    expr: &Expr,
    type_fields: &HashMap<String, TypeRef>,
) -> Option<String> {
    match &expr.kind {
        ExprKind::Identifier { name, .. } => Some(name.clone()),
        ExprKind::MemberAccess { target, member, .. } => {
            if matches!(target.kind, ExprKind::This) && type_fields.contains_key(member) {
                Some(member.clone())
            } else if let Some(prefix) = extract_collection_key(target, type_fields) {
                Some(format!("{}.{}", prefix, member))
            } else {
                None
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
        "Add"
            | "AddRange"
            | "Insert"
            | "Remove"
            | "RemoveAt"
            | "Pop"
            | "Clear"
            | "Sort"
            | "Fill"
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

```

---

### `src/semantics/mod.rs`

```rust
pub mod archetype_analyzer;
pub mod borrow_inferencer;
pub mod collector;
pub mod effect_inferencer;
pub mod hierarchy_lowerer;
pub mod linq_fuser;
pub mod overload_resolver;
pub mod preflight_verifier;
pub mod primitive_resolver;
pub mod symbols;

pub use archetype_analyzer::analyze_archetypes;
pub use borrow_inferencer::InterproceduralBorrowInferencer;
pub use collector::collect_global_symbols;
pub use effect_inferencer::infer_checked_effects;
pub use hierarchy_lowerer::resolve_polymorphism_strategies;
pub use linq_fuser::fuse_linq_pipelines;
pub use overload_resolver::resolve_overloads;
pub use preflight_verifier::run_preflight_ownership_checks;
pub use primitive_resolver::{
    format_rust_owned_type, format_rust_param_type, resolve_primitives,
};
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
    analyze_archetypes, collect_global_symbols, fuse_linq_pipelines, infer_checked_effects,
    resolve_overloads, resolve_polymorphism_strategies, resolve_primitives,
    run_preflight_ownership_checks, GlobalSymbolTable, InterproceduralBorrowInferencer,
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

/// Runs Milestones 1–4 (Pass 1, Pass 2A, and Pass 2B: `primitive` Type Erasure,
/// Interprocedural Borrow & Mutation Propagation, Checked `throws` Effect Inference,
/// and Zero-Cost LINQ-to-Iterator Pipeline Fusion).
pub fn analyze_workspace_pass2b(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (mut units, mut symtab, diag) = analyze_workspace_pass2a(files);
    if !diag.has_errors() {
        resolve_primitives(&mut units, &mut symtab);
        InterproceduralBorrowInferencer::infer_all(&mut units, &mut symtab);
        infer_checked_effects(&mut units, &mut symtab);
        fuse_linq_pipelines(&mut units, &symtab);
    }
    (units, symtab, diag)
}

/// Runs Milestones 1–5 (Pass 1, Pass 2A, Pass 2B, and Pass 2.5 Pre-Flight Ownership Verifier
/// enforcing rules `RSHARP001`–`RSHARP003` before Rust code emission).
pub fn analyze_workspace_with_preflight(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (units, symtab, mut diag) = analyze_workspace_pass2b(files);
    if !diag.has_errors() {
        run_preflight_ownership_checks(&units, &symtab, &mut diag);
    }
    (units, symtab, diag)
}

```

---

### `tests/m5_preflight_diagnostics_tests.rs`

```rust
use rsharpc::analyze_workspace_with_preflight;
use rsharpc::diagnostics::DiagnosticCode;

#[test]
fn test_rsharp001_catches_service_class_field_mutation_outside_constructor() {
    let bad_service_src = r#"
namespace Commerce.Services;

public service class UserService
{
    private int _requestCounter;
    private readonly List<string> _auditLog;

    public UserService(List<string> auditLog)
    {
        _requestCounter = 0;
        _auditLog = auditLog;
    }

    public void RecordLogin(string user)
    {
        _requestCounter += 1;
        _auditLog.Add(user);
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_with_preflight(&[("Services/UserService.rsharp", bad_service_src)]);
    assert!(diag.has_errors());
    assert_eq!(
        diag.diagnostics.len(),
        2,
        "Expected RSHARP001 on both `_requestCounter += 1` and `_auditLog.Add(user)`, got: {}",
        diag.format_all()
    );

    assert_eq!(diag.diagnostics[0].code, DiagnosticCode::RSharp001ServiceMutation);
    assert!(diag.diagnostics[0].message.contains("_requestCounter"));
    assert!(diag.diagnostics[0].message.contains("UserService"));
    assert_eq!(diag.diagnostics[0].span.start_line, 17);

    assert_eq!(diag.diagnostics[1].code, DiagnosticCode::RSharp001ServiceMutation);
    assert!(diag.diagnostics[1].message.contains("_auditLog"));
    assert_eq!(diag.diagnostics[1].span.start_line, 18);
}

#[test]
fn test_rsharp002_catches_collection_mutation_during_foreach_iteration() {
    let aliasing_src = r#"
namespace Commerce.Orders;

public record Order(int Id, decimal Total);

public service class OrderBatchCleaner
{
    public void PruneEmptyOrders(List<Order> orders)
    {
        foreach (var order in orders)
        {
            if (order.Total <= 0.0m)
            {
                orders.Clear();
            }
        }
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_with_preflight(&[("Orders/OrderBatchCleaner.rsharp", aliasing_src)]);
    assert!(diag.has_errors());
    assert_eq!(diag.diagnostics.len(), 1);

    let err = &diag.diagnostics[0];
    assert_eq!(err.code, DiagnosticCode::RSharp002CollectionAliasing);
    assert!(err.message.contains("orders"));
    assert_eq!(err.span.filename, "Orders/OrderBatchCleaner.rsharp");
    assert_eq!(err.span.start_line, 14);
    assert!(err.quick_fix.as_deref().unwrap().contains("orders.ToList()"));
}

#[test]
fn test_rsharp003_catches_use_after_move_on_linear_disposable_resource() {
    let use_after_move_src = r#"
namespace Telemetry.Transport;

public class SocketHandle : IDisposable
{
    public intFd Fd;

    public void Dispose()
    {
    }
}

public record intFd(int Value);

public static class ChannelDispatcher
{
    public static void TakeOwnership([Moves] SocketHandle handle)
    {
    }

    public static void InspectSocket(SocketHandle handle)
    {
    }

    public static void DispatchTwice(SocketHandle socket)
    {
        TakeOwnership(socket);
        InspectSocket(socket);
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_with_preflight(&[("Transport/ChannelDispatcher.rsharp", use_after_move_src)]);
    assert!(diag.has_errors());
    assert_eq!(diag.diagnostics.len(), 1);

    let err = &diag.diagnostics[0];
    assert_eq!(err.code, DiagnosticCode::RSharp003UseAfterMove);
    assert!(err.message.contains("socket"));
    assert!(
        err.message.contains("27:"),
        "Expected diagnostic to point to original move line 27, got: {}",
        err.message
    );
    assert_eq!(err.span.start_line, 28);
}

#[test]
fn test_clean_code_passes_preflight_verifier_with_zero_diagnostics() {
    let valid_src = r#"
namespace Commerce.Valid;

public record Item(int Id);

public shared class SharedSessionStore
{
    public void TouchSession(string sessionId)
    {
    }
}

public service class ValidCheckoutService
{
    private readonly SharedSessionStore _sessions;

    public ValidCheckoutService(SharedSessionStore sessions)
    {
        _sessions = sessions;
    }

    public int CountItems(List<Item> items)
    {
        var total = 0;
        foreach (var item in items)
        {
            total += item.Id;
        }
        return total;
    }
}
"#;

    let (_units, _symtab, diag) =
        analyze_workspace_with_preflight(&[("Valid/ValidCheckoutService.rsharp", valid_src)]);
    assert!(
        !diag.has_errors(),
        "Expected valid service and foreach read loop to pass preflight checks, got: {}",
        diag.format_all()
    );
}

```

---

Would you like me to continue with the raw individual files for **Milestone 6 (Pass 3: `src/codegen/sourcemap.rs`, `src/codegen/expr_emitter.rs`, `src/codegen/rs_ast_emitter.rs`, `src/codegen/cargo_synthesizer.rs`, `src/codegen/mod.rs`, `src/main.rs`, `stdlib/RustSharp.Core.d.rsharp`, the `tests/fixtures/commerce_workspace/` multi-file fixture, and end-to-end codegen tests)** next?
