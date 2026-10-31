use std::collections::HashSet;

use crate::frontend::ast::{
    Block, CompilationUnit, EffectSignature, Expr, ExprKind, LambdaBody, MemberDecl, MethodDecl,
    Stmt, SymbolId, TypeRef,
};
use crate::semantics::symbols::GlobalSymbolTable;

/// Pass 2B Checked Effect (`throws` & `try/catch`) Call-Graph Analyzer.
///
/// Lowers C# exception syntax into zero-cost monadic `Result<T, E>` & `?` propagation:
/// 1. Marks any method with an explicit `throws TError` clause or an unguarded `throw new TError(...)`
///    statement as `EffectSignature::Fallible { error_type }`.
/// 2. Propagates `EffectSignature::Fallible` bottom-up across the call graph whenever a method
///    calls a fallible callee outside a matching `try / catch` block.
/// 3. Annotates every unguarded call to a fallible method with `expr.append_try_question_mark = true`
///    so Pass 3 appends the `?` operator automatically.
pub fn infer_checked_effects(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable) {
    // Step 1: Seed initial fallible/infallible effect signatures on all methods
    for unit in units.iter_mut() {
        for type_decl in &mut unit.types {
            for member in &mut type_decl.members {
                if let MemberDecl::Method(method) = member {
                    seed_method_effect(method, symtab);
                }
            }
        }
    }

    // Step 2: Propagate `Fallible` bottom-up across the call graph to a fixed point
    for _ in 0..16 {
        let mut changed = false;
        for unit in units.iter_mut() {
            if unit.is_ambient_stub {
                continue;
            }
            for type_decl in &mut unit.types {
                for member in &mut type_decl.members {
                    if let MemberDecl::Method(method) = member {
                        if propagate_method_effect(method, symtab) {
                            changed = true;
                        }
                    }
                }
            }
        }
        if !changed {
            break;
        }
    }

    // Step 3: Mark unguarded calls to fallible methods with `append_try_question_mark = true`
    for unit in units.iter_mut() {
        if unit.is_ambient_stub {
            continue;
        }
        for type_decl in &mut unit.types {
            for member in &mut type_decl.members {
                if let MemberDecl::Method(method) = member {
                    if let Some(body) = &mut method.body {
                        let empty_caught = HashSet::new();
                        annotate_block_question_marks(body, &empty_caught, false, symtab);
                    }
                }
            }
        }
    }
}

fn seed_method_effect(method: &mut MethodDecl, symtab: &mut GlobalSymbolTable) {
    if let Some(throws_ty) = &method.explicit_throws {
        method.inferred_effect = EffectSignature::Fallible {
            error_type: throws_ty.clone(),
        };
    } else if let Some(body) = &method.body {
        let empty_caught = HashSet::new();
        if let Some(thrown_ty) = find_uncaught_effect_in_block(body, &empty_caught, symtab) {
            method.inferred_effect = EffectSignature::Fallible {
                error_type: thrown_ty,
            };
        } else {
            method.inferred_effect = EffectSignature::Infallible;
        }
    } else {
        method.inferred_effect = EffectSignature::Infallible;
    }

    if let Some(msym) = symtab.methods.get_mut(&method.id) {
        msym.inferred_effect = method.inferred_effect.clone();
    }
}

fn propagate_method_effect(method: &mut MethodDecl, symtab: &mut GlobalSymbolTable) -> bool {
    if matches!(method.inferred_effect, EffectSignature::Fallible { .. }) {
        return false;
    }

    let Some(body) = &method.body else {
        return false;
    };

    let empty_caught = HashSet::new();
    if let Some(err_ty) = find_uncaught_effect_in_block(body, &empty_caught, symtab) {
        method.inferred_effect = EffectSignature::Fallible { error_type: err_ty };
        if let Some(msym) = symtab.methods.get_mut(&method.id) {
            msym.inferred_effect = method.inferred_effect.clone();
        }
        return true;
    }
    false
}

fn find_uncaught_effect_in_block(
    block: &Block,
    caught_errors: &HashSet<String>,
    symtab: &GlobalSymbolTable,
) -> Option<TypeRef> {
    for stmt in &block.stmts {
        if let Some(err) = find_uncaught_effect_in_stmt(stmt, caught_errors, symtab) {
            return Some(err);
        }
    }
    None
}

fn find_uncaught_effect_in_stmt(
    stmt: &Stmt,
    caught_errors: &HashSet<String>,
    symtab: &GlobalSymbolTable,
) -> Option<TypeRef> {
    match stmt {
        Stmt::Block(b) => find_uncaught_effect_in_block(b, caught_errors, symtab),
        Stmt::Throw { error_expr, .. } => {
            if let Some(err_ty) = infer_thrown_error_type(error_expr) {
                if !caught_errors.contains(err_ty.short_name()) && !caught_errors.contains("_") {
                    return Some(err_ty);
                }
            }
            None
        }
        Stmt::LocalVar { init, .. } | Stmt::UsingResource { init, .. } => {
            find_uncaught_effect_in_expr(init, caught_errors, symtab)
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            if let Some(e) = find_uncaught_effect_in_expr(cond, caught_errors, symtab) {
                return Some(e);
            }
            if let Some(e) = find_uncaught_effect_in_stmt(then_branch, caught_errors, symtab) {
                return Some(e);
            }
            if let Some(el) = else_branch {
                if let Some(e) = find_uncaught_effect_in_stmt(el, caught_errors, symtab) {
                    return Some(e);
                }
            }
            None
        }
        Stmt::While { cond, body, .. } => find_uncaught_effect_in_expr(cond, caught_errors, symtab)
            .or_else(|| find_uncaught_effect_in_stmt(body, caught_errors, symtab)),
        Stmt::ForEach {
            collection, body, ..
        } => find_uncaught_effect_in_expr(collection, caught_errors, symtab)
            .or_else(|| find_uncaught_effect_in_stmt(body, caught_errors, symtab)),
        Stmt::Return { value: Some(v), .. } => {
            find_uncaught_effect_in_expr(v, caught_errors, symtab)
        }
        Stmt::Return { value: None, .. } => None,
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            let mut try_caught = caught_errors.clone();
            for c in catches {
                try_caught.insert(c.error_type.short_name().to_string());
            }
            if let Some(e) = find_uncaught_effect_in_block(try_block, &try_caught, symtab) {
                return Some(e);
            }
            for c in catches {
                if let Some(e) = find_uncaught_effect_in_block(&c.body, caught_errors, symtab) {
                    return Some(e);
                }
            }
            None
        }
        Stmt::ExprStmt { expr, .. } => find_uncaught_effect_in_expr(expr, caught_errors, symtab),
    }
}

fn find_uncaught_effect_in_expr(
    expr: &Expr,
    caught_errors: &HashSet<String>,
    symtab: &GlobalSymbolTable,
) -> Option<TypeRef> {
    match &expr.kind {
        ExprKind::MethodCall {
            receiver,
            args,
            resolved_overload,
            ..
        } => {
            if let Some(recv) = receiver {
                if let Some(e) = find_uncaught_effect_in_expr(recv, caught_errors, symtab) {
                    return Some(e);
                }
            }
            for arg in args {
                if let Some(e) = find_uncaught_effect_in_expr(&arg.expr, caught_errors, symtab) {
                    return Some(e);
                }
            }
            if let Some(err_ty) = lookup_callee_fallible_error(*resolved_overload, symtab) {
                if !caught_errors.contains(err_ty.short_name()) && !caught_errors.contains("_") {
                    return Some(err_ty);
                }
            }
            None
        }
        ExprKind::Construct { args, .. } => {
            for arg in args {
                if let Some(e) = find_uncaught_effect_in_expr(&arg.expr, caught_errors, symtab) {
                    return Some(e);
                }
            }
            None
        }
        ExprKind::Assignment { target, value, .. } => {
            find_uncaught_effect_in_expr(target, caught_errors, symtab)
                .or_else(|| find_uncaught_effect_in_expr(value, caught_errors, symtab))
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            find_uncaught_effect_in_expr(left, caught_errors, symtab)
                .or_else(|| find_uncaught_effect_in_expr(right, caught_errors, symtab))
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            find_uncaught_effect_in_expr(operand, caught_errors, symtab)
        }
        ExprKind::MemberAccess { target, .. } => {
            find_uncaught_effect_in_expr(target, caught_errors, symtab)
        }
        ExprKind::IndexAccess { target, indices } => {
            if let Some(e) = find_uncaught_effect_in_expr(target, caught_errors, symtab) {
                return Some(e);
            }
            for idx in indices {
                if let Some(e) = find_uncaught_effect_in_expr(&idx.expr, caught_errors, symtab) {
                    return Some(e);
                }
            }
            None
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                if let Some(e) = find_uncaught_effect_in_expr(t, caught_errors, symtab) {
                    return Some(e);
                }
            }
            if let Some(s) = start {
                if let Some(e) = find_uncaught_effect_in_expr(s, caught_errors, symtab) {
                    return Some(e);
                }
            }
            if let Some(en) = end {
                if let Some(e) = find_uncaught_effect_in_expr(en, caught_errors, symtab) {
                    return Some(e);
                }
            }
            None
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => find_uncaught_effect_in_expr(e, caught_errors, symtab),
            LambdaBody::Block(b) => find_uncaught_effect_in_block(b, caught_errors, symtab),
        },
        ExprKind::Switch { scrutinee, arms } => {
            if let Some(e) = find_uncaught_effect_in_expr(scrutinee, caught_errors, symtab) {
                return Some(e);
            }
            for arm in arms {
                if let Some(g) = &arm.guard {
                    if let Some(e) = find_uncaught_effect_in_expr(g, caught_errors, symtab) {
                        return Some(e);
                    }
                }
                if let Some(e) = find_uncaught_effect_in_expr(&arm.body, caught_errors, symtab) {
                    return Some(e);
                }
            }
            None
        }
        ExprKind::LinqChain(chain) => {
            find_uncaught_effect_in_expr(&chain.source, caught_errors, symtab)
        }
        ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::Identifier { .. }
        | ExprKind::This
        | ExprKind::Base => None,
    }
}

fn annotate_block_question_marks(
    block: &mut Block,
    caught_errors: &HashSet<String>,
    inside_direct_try_single_stmt: bool,
    symtab: &GlobalSymbolTable,
) {
    let is_single_stmt = block.stmts.len() == 1;
    for stmt in &mut block.stmts {
        annotate_stmt_question_marks(
            stmt,
            caught_errors,
            inside_direct_try_single_stmt && is_single_stmt,
            symtab,
        );
    }
}

fn annotate_stmt_question_marks(
    stmt: &mut Stmt,
    caught_errors: &HashSet<String>,
    is_direct_try_target: bool,
    symtab: &GlobalSymbolTable,
) {
    match stmt {
        Stmt::Block(b) => {
            annotate_block_question_marks(b, caught_errors, is_direct_try_target, symtab);
        }
        Stmt::LocalVar { init, .. } | Stmt::UsingResource { init, .. } => {
            annotate_expr_question_marks(init, caught_errors, false, symtab);
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            annotate_expr_question_marks(cond, caught_errors, false, symtab);
            annotate_stmt_question_marks(then_branch, caught_errors, false, symtab);
            if let Some(el) = else_branch {
                annotate_stmt_question_marks(el, caught_errors, false, symtab);
            }
        }
        Stmt::While { cond, body, .. } => {
            annotate_expr_question_marks(cond, caught_errors, false, symtab);
            annotate_stmt_question_marks(body, caught_errors, false, symtab);
        }
        Stmt::ForEach {
            collection, body, ..
        } => {
            annotate_expr_question_marks(collection, caught_errors, false, symtab);
            annotate_stmt_question_marks(body, caught_errors, false, symtab);
        }
        Stmt::Return { value: Some(v), .. } => {
            annotate_expr_question_marks(v, caught_errors, is_direct_try_target, symtab);
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            annotate_expr_question_marks(error_expr, caught_errors, false, symtab);
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            let mut try_caught = caught_errors.clone();
            for c in catches.iter() {
                try_caught.insert(c.error_type.short_name().to_string());
            }
            // If the `try` block is a single `return FallibleCall();` or `FallibleCall();`,
            // Pass 3 lowers the call directly as the `match FallibleCall() { Ok(..) => .., Err(..) => .. }`
            // scrutinee; otherwise inner calls inside a multi-statement `try` closure use `?`.
            let single_try = try_block.stmts.len() == 1;
            annotate_block_question_marks(try_block, &try_caught, single_try, symtab);
            for c in catches.iter_mut() {
                annotate_block_question_marks(&mut c.body, caught_errors, false, symtab);
            }
        }
        Stmt::ExprStmt { expr, .. } => {
            annotate_expr_question_marks(expr, caught_errors, is_direct_try_target, symtab);
        }
    }
}

fn annotate_expr_question_marks(
    expr: &mut Expr,
    caught_errors: &HashSet<String>,
    suppress_top_level_qmark: bool,
    symtab: &GlobalSymbolTable,
) {
    match &mut expr.kind {
        ExprKind::MethodCall {
            receiver,
            args,
            resolved_overload,
            ..
        } => {
            if let Some(recv) = receiver {
                annotate_expr_question_marks(recv, caught_errors, false, symtab);
            }
            for arg in args.iter_mut() {
                annotate_expr_question_marks(&mut arg.expr, caught_errors, false, symtab);
            }

            if lookup_callee_fallible_error(*resolved_overload, symtab).is_some()
                && !suppress_top_level_qmark
            {
                expr.append_try_question_mark = true;
            }
        }
        ExprKind::Construct { args, .. } => {
            for arg in args.iter_mut() {
                annotate_expr_question_marks(&mut arg.expr, caught_errors, false, symtab);
            }
        }
        ExprKind::Assignment { target, value, .. } => {
            annotate_expr_question_marks(target, caught_errors, false, symtab);
            annotate_expr_question_marks(value, caught_errors, false, symtab);
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            annotate_expr_question_marks(left, caught_errors, false, symtab);
            annotate_expr_question_marks(right, caught_errors, false, symtab);
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            annotate_expr_question_marks(operand, caught_errors, false, symtab);
        }
        ExprKind::MemberAccess { target, .. } => {
            annotate_expr_question_marks(target, caught_errors, false, symtab);
        }
        ExprKind::IndexAccess { target, indices } => {
            annotate_expr_question_marks(target, caught_errors, false, symtab);
            for idx in indices {
                annotate_expr_question_marks(&mut idx.expr, caught_errors, false, symtab);
            }
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                annotate_expr_question_marks(t, caught_errors, false, symtab);
            }
            if let Some(s) = start {
                annotate_expr_question_marks(s, caught_errors, false, symtab);
            }
            if let Some(e) = end {
                annotate_expr_question_marks(e, caught_errors, false, symtab);
            }
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => {
                annotate_expr_question_marks(e, caught_errors, false, symtab);
            }
            LambdaBody::Block(b) => {
                annotate_block_question_marks(b, caught_errors, false, symtab);
            }
        },
        ExprKind::Switch { scrutinee, arms } => {
            annotate_expr_question_marks(scrutinee, caught_errors, false, symtab);
            for arm in arms {
                if let Some(g) = &mut arm.guard {
                    annotate_expr_question_marks(g, caught_errors, false, symtab);
                }
                annotate_expr_question_marks(&mut arm.body, caught_errors, false, symtab);
            }
        }
        ExprKind::LinqChain(chain) => {
            annotate_expr_question_marks(&mut chain.source, caught_errors, false, symtab);
        }
        ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::Identifier { .. }
        | ExprKind::This
        | ExprKind::Base => {}
    }
}

fn infer_thrown_error_type(error_expr: &Expr) -> Option<TypeRef> {
    if let ExprKind::Construct { ty, .. } = &error_expr.kind {
        return Some(ty.clone());
    }
    error_expr.resolved_type.clone()
}

fn lookup_callee_fallible_error(
    resolved_overload: Option<SymbolId>,
    symtab: &GlobalSymbolTable,
) -> Option<TypeRef> {
    let mid = resolved_overload?;
    let msym = symtab.methods.get(&mid)?;
    match &msym.inferred_effect {
        EffectSignature::Fallible { error_type } => Some(error_type.clone()),
        _ => msym.explicit_throws.clone(),
    }
}
