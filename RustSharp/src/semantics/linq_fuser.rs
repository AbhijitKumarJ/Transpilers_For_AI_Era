use std::collections::HashSet;

use crate::frontend::ast::{
    Block, CompilationUnit, Expr, ExprKind, LambdaBody, LinqChain, LinqOp, LinqTerminal,
    MemberDecl, Stmt, TypeRef,
};
use crate::semantics::symbols::GlobalSymbolTable;

/// Pass 2B Zero-Cost LINQ-to-Iterator Pipeline Fuser.
///
/// Rewrites chained C# LINQ queries (`.Where()`, `.Select()`, `.SelectMany()`, `.Take()`,
/// `.Skip()`, `.WithIndex()`) ending in a terminal operation (`.ToList()`, `.ToHashSet()`,
/// `.Any()`, `.All()`, `.FirstOrDefault()`, `.Count()`, `.Sum()`) into a single fused
/// `ExprKind::LinqChain` AST node that lowers 1:1 into a zero-allocation Rust
/// `.iter().filter(...).map(...).collect()` pipeline.
pub fn fuse_linq_pipelines(units: &mut [CompilationUnit], _symtab: &GlobalSymbolTable) {
    for unit in units.iter_mut() {
        if unit.is_ambient_stub {
            continue;
        }
        for type_decl in &mut unit.types {
            for member in &mut type_decl.members {
                match member {
                    MemberDecl::Method(m) => {
                        let param_names: HashSet<String> =
                            m.params.iter().map(|p| p.name.clone()).collect();
                        if let Some(body) = &mut m.body {
                            fuse_linq_in_block(body, &param_names);
                        }
                    }
                    MemberDecl::Constructor(c) => {
                        let param_names: HashSet<String> =
                            c.params.iter().map(|p| p.name.clone()).collect();
                        if let Some(body) = &mut c.body {
                            fuse_linq_in_block(body, &param_names);
                        }
                    }
                    MemberDecl::Property(p) => {
                        let empty_params = HashSet::new();
                        for acc in &mut p.accessors {
                            if let Some(body) = &mut acc.body {
                                fuse_linq_in_block(body, &empty_params);
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }
}

fn fuse_linq_in_block(block: &mut Block, param_names: &HashSet<String>) {
    let len = block.stmts.len();
    for i in 0..len {
        // Collect identifiers referenced in all *subsequent* statements of the block
        // to apply Rule 1 (`.iter()` vs consuming `.into_iter()`).
        let mut used_later = param_names.clone();
        for later_stmt in &block.stmts[(i + 1)..] {
            collect_referenced_idents_in_stmt(later_stmt, &mut used_later);
        }

        fuse_linq_in_stmt(&mut block.stmts[i], &used_later, param_names);
    }
}

fn fuse_linq_in_stmt(stmt: &mut Stmt, used_later: &HashSet<String>, param_names: &HashSet<String>) {
    match stmt {
        Stmt::Block(b) => fuse_linq_in_block(b, param_names),
        Stmt::LocalVar { init, .. } | Stmt::UsingResource { init, .. } => {
            fuse_linq_in_expr(init, used_later, param_names);
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            fuse_linq_in_expr(cond, used_later, param_names);
            fuse_linq_in_stmt(then_branch, used_later, param_names);
            if let Some(el) = else_branch {
                fuse_linq_in_stmt(el, used_later, param_names);
            }
        }
        Stmt::While { cond, body, .. } => {
            fuse_linq_in_expr(cond, used_later, param_names);
            fuse_linq_in_stmt(body, used_later, param_names);
        }
        Stmt::ForEach {
            collection, body, ..
        } => {
            fuse_linq_in_expr(collection, used_later, param_names);
            fuse_linq_in_stmt(body, used_later, param_names);
        }
        Stmt::Return { value: Some(v), .. } => {
            fuse_linq_in_expr(v, used_later, param_names);
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            fuse_linq_in_expr(error_expr, used_later, param_names);
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            fuse_linq_in_block(try_block, param_names);
            for c in catches {
                fuse_linq_in_block(&mut c.body, param_names);
            }
        }
        Stmt::ExprStmt { expr, .. } => {
            fuse_linq_in_expr(expr, used_later, param_names);
        }
    }
}

fn fuse_linq_in_expr(expr: &mut Expr, used_later: &HashSet<String>, param_names: &HashSet<String>) {
    // First recursively fuse children
    match &mut expr.kind {
        ExprKind::MethodCall { receiver, args, .. } => {
            if let Some(recv) = receiver {
                fuse_linq_in_expr(recv, used_later, param_names);
            }
            for arg in args {
                fuse_linq_in_expr(&mut arg.expr, used_later, param_names);
            }
        }
        ExprKind::Construct { args, .. } => {
            for arg in args {
                fuse_linq_in_expr(&mut arg.expr, used_later, param_names);
            }
        }
        ExprKind::Assignment { target, value, .. } => {
            fuse_linq_in_expr(target, used_later, param_names);
            fuse_linq_in_expr(value, used_later, param_names);
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            fuse_linq_in_expr(left, used_later, param_names);
            fuse_linq_in_expr(right, used_later, param_names);
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            fuse_linq_in_expr(operand, used_later, param_names);
        }
        ExprKind::MemberAccess { target, .. } => {
            fuse_linq_in_expr(target, used_later, param_names);
        }
        ExprKind::IndexAccess { target, indices } => {
            fuse_linq_in_expr(target, used_later, param_names);
            for idx in indices {
                fuse_linq_in_expr(&mut idx.expr, used_later, param_names);
            }
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                fuse_linq_in_expr(t, used_later, param_names);
            }
            if let Some(s) = start {
                fuse_linq_in_expr(s, used_later, param_names);
            }
            if let Some(e) = end {
                fuse_linq_in_expr(e, used_later, param_names);
            }
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => fuse_linq_in_expr(e, used_later, param_names),
            LambdaBody::Block(b) => fuse_linq_in_block(b, param_names),
        },
        ExprKind::Switch { scrutinee, arms } => {
            fuse_linq_in_expr(scrutinee, used_later, param_names);
            for arm in arms {
                if let Some(g) = &mut arm.guard {
                    fuse_linq_in_expr(g, used_later, param_names);
                }
                fuse_linq_in_expr(&mut arm.body, used_later, param_names);
            }
        }
        ExprKind::LinqChain(_)
        | ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::Identifier { .. }
        | ExprKind::This
        | ExprKind::Base => {}
    }

    // Attempt to match and extract a LINQ pipeline rooted at this expression
    if let Some(fused_chain) = try_extract_linq_chain(expr, used_later) {
        let return_type = match &fused_chain.terminal {
            LinqTerminal::ToList => Some(TypeRef {
                span: expr.span.clone(),
                path: vec!["List".to_string()],
                type_args: Vec::new(),
                is_nullable: false,
                is_primitive_keyword: false,
            }),
            LinqTerminal::ToHashSet => Some(TypeRef {
                span: expr.span.clone(),
                path: vec!["HashSet".to_string()],
                type_args: Vec::new(),
                is_nullable: false,
                is_primitive_keyword: false,
            }),
            LinqTerminal::Count | LinqTerminal::Sum => Some(TypeRef {
                span: expr.span.clone(),
                path: vec!["int".to_string()],
                type_args: Vec::new(),
                is_nullable: false,
                is_primitive_keyword: true,
            }),
            LinqTerminal::Any { .. } | LinqTerminal::All { .. } => Some(TypeRef {
                span: expr.span.clone(),
                path: vec!["bool".to_string()],
                type_args: Vec::new(),
                is_nullable: false,
                is_primitive_keyword: true,
            }),
            _ => None,
        };
        if expr.resolved_type.is_none() {
            expr.resolved_type = return_type;
        }
        expr.kind = ExprKind::LinqChain(Box::new(fused_chain));
    }
}

fn try_extract_linq_chain(expr: &Expr, used_later: &HashSet<String>) -> Option<LinqChain> {
    let ExprKind::MethodCall {
        receiver: Some(recv),
        method_name,
        args,
        ..
    } = &expr.kind
    else {
        return None;
    };

    // 1. Check if `method_name` is a LINQ terminal operation
    let terminal = match method_name.as_str() {
        "ToList" if args.is_empty() => LinqTerminal::ToList,
        "ToHashSet" if args.is_empty() => LinqTerminal::ToHashSet,
        "Any" if args.len() <= 1 => LinqTerminal::Any {
            predicate: args.first().map(|a| a.expr.clone()),
        },
        "All" if args.len() == 1 => LinqTerminal::All {
            predicate: args[0].expr.clone(),
        },
        "First" if args.len() <= 1 => LinqTerminal::First {
            predicate: args.first().map(|a| a.expr.clone()),
        },
        "FirstOrDefault" if args.len() <= 1 => LinqTerminal::FirstOrDefault {
            predicate: args.first().map(|a| a.expr.clone()),
        },
        "Last" if args.len() <= 1 => LinqTerminal::Last {
            predicate: args.first().map(|a| a.expr.clone()),
        },
        "LastOrDefault" if args.len() <= 1 => LinqTerminal::LastOrDefault {
            predicate: args.first().map(|a| a.expr.clone()),
        },
        "Aggregate" if args.len() == 2 => LinqTerminal::Aggregate {
            seed: Some(args[0].expr.clone()),
            func: Box::new(args[1].expr.clone()),
        },
        "Aggregate" if args.len() == 1 => LinqTerminal::Aggregate {
            seed: None,
            func: Box::new(args[0].expr.clone()),
        },
        "Count" if args.is_empty() => {
            // Only treat `.Count()` (method call with parens) as LINQ terminal
            LinqTerminal::Count
        }
        "Sum" if args.is_empty() => LinqTerminal::Sum,
        _ => return None,
    };

    // 2. Unwind intermediate lazy adaptor stages (`.Where`, `.Select`, `.SelectMany`, `.Take`, `.Skip`, `.WithIndex`)
    let mut ops_reversed: Vec<LinqOp> = Vec::new();
    let mut current_source: &Expr = recv;

    while let ExprKind::MethodCall {
        receiver: Some(inner_recv),
        method_name: stage_name,
        args: stage_args,
        ..
    } = &current_source.kind
    {
        let stage_op = match stage_name.as_str() {
            "Where" if stage_args.len() == 1 => Some(LinqOp::Where {
                predicate: stage_args[0].expr.clone(),
            }),
            "Select" if stage_args.len() == 1 => Some(LinqOp::Select {
                selector: stage_args[0].expr.clone(),
            }),
            "SelectMany" if stage_args.len() == 1 => Some(LinqOp::SelectMany {
                selector: stage_args[0].expr.clone(),
            }),
            "Take" if stage_args.len() == 1 => Some(LinqOp::Take {
                count: stage_args[0].expr.clone(),
            }),
            "Skip" if stage_args.len() == 1 => Some(LinqOp::Skip {
                count: stage_args[0].expr.clone(),
            }),
            "WithIndex" if stage_args.is_empty() => Some(LinqOp::WithIndex),
            "OrderBy" if stage_args.len() == 1 => Some(LinqOp::OrderBy {
                key_selector: stage_args[0].expr.clone(),
                descending: false,
            }),
            "OrderByDescending" if stage_args.len() == 1 => Some(LinqOp::OrderBy {
                key_selector: stage_args[0].expr.clone(),
                descending: true,
            }),
            "Distinct" if stage_args.is_empty() => Some(LinqOp::Distinct),
            "Reverse" if stage_args.is_empty() => Some(LinqOp::Reverse),
            _ => None,
        };

        if let Some(op) = stage_op {
            ops_reversed.push(op);
            current_source = inner_recv;
        } else {
            break;
        }
    }

    ops_reversed.reverse();

    // Determine whether the pipeline can consume `current_source` via `.into_iter()`
    // or should borrow via `.iter()` (Default Rule 1: borrow if parameter/field or used later).
    let consumes_source = match &current_source.kind {
        ExprKind::Identifier { name, .. } => {
            !used_later.contains(name)
                && matches!(terminal, LinqTerminal::ToList | LinqTerminal::ToHashSet)
                && ops_reversed.is_empty()
        }
        _ => false,
    };

    Some(LinqChain {
        source: Box::new(current_source.clone()),
        ops: ops_reversed,
        terminal,
        consumes_source,
    })
}

fn collect_referenced_idents_in_stmt(stmt: &Stmt, out: &mut HashSet<String>) {
    match stmt {
        Stmt::Block(b) => {
            for s in &b.stmts {
                collect_referenced_idents_in_stmt(s, out);
            }
        }
        Stmt::LocalVar { init, .. } | Stmt::UsingResource { init, .. } => {
            collect_referenced_idents_in_expr(init, out);
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            collect_referenced_idents_in_expr(cond, out);
            collect_referenced_idents_in_stmt(then_branch, out);
            if let Some(el) = else_branch {
                collect_referenced_idents_in_stmt(el, out);
            }
        }
        Stmt::While { cond, body, .. } => {
            collect_referenced_idents_in_expr(cond, out);
            collect_referenced_idents_in_stmt(body, out);
        }
        Stmt::ForEach {
            collection, body, ..
        } => {
            collect_referenced_idents_in_expr(collection, out);
            collect_referenced_idents_in_stmt(body, out);
        }
        Stmt::Return { value: Some(v), .. } => {
            collect_referenced_idents_in_expr(v, out);
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            collect_referenced_idents_in_expr(error_expr, out);
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            for s in &try_block.stmts {
                collect_referenced_idents_in_stmt(s, out);
            }
            for c in catches {
                for s in &c.body.stmts {
                    collect_referenced_idents_in_stmt(s, out);
                }
            }
        }
        Stmt::ExprStmt { expr, .. } => {
            collect_referenced_idents_in_expr(expr, out);
        }
    }
}

fn collect_referenced_idents_in_expr(expr: &Expr, out: &mut HashSet<String>) {
    match &expr.kind {
        ExprKind::Identifier { name, .. } => {
            out.insert(name.clone());
        }
        ExprKind::MethodCall { receiver, args, .. } => {
            if let Some(r) = receiver {
                collect_referenced_idents_in_expr(r, out);
            }
            for a in args {
                collect_referenced_idents_in_expr(&a.expr, out);
            }
        }
        ExprKind::Construct { args, .. } => {
            for a in args {
                collect_referenced_idents_in_expr(&a.expr, out);
            }
        }
        ExprKind::MemberAccess { target, .. } => {
            collect_referenced_idents_in_expr(target, out);
        }
        ExprKind::Assignment { target, value, .. } => {
            collect_referenced_idents_in_expr(target, out);
            collect_referenced_idents_in_expr(value, out);
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            collect_referenced_idents_in_expr(left, out);
            collect_referenced_idents_in_expr(right, out);
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            collect_referenced_idents_in_expr(operand, out);
        }
        ExprKind::IndexAccess { target, indices } => {
            collect_referenced_idents_in_expr(target, out);
            for idx in indices {
                collect_referenced_idents_in_expr(&idx.expr, out);
            }
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                collect_referenced_idents_in_expr(t, out);
            }
            if let Some(s) = start {
                collect_referenced_idents_in_expr(s, out);
            }
            if let Some(e) = end {
                collect_referenced_idents_in_expr(e, out);
            }
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => collect_referenced_idents_in_expr(e, out),
            LambdaBody::Block(b) => {
                for s in &b.stmts {
                    collect_referenced_idents_in_stmt(s, out);
                }
            }
        },
        ExprKind::Switch { scrutinee, arms } => {
            collect_referenced_idents_in_expr(scrutinee, out);
            for arm in arms {
                if let Some(g) = &arm.guard {
                    collect_referenced_idents_in_expr(g, out);
                }
                collect_referenced_idents_in_expr(&arm.body, out);
            }
        }
        ExprKind::LinqChain(chain) => {
            collect_referenced_idents_in_expr(&chain.source, out);
        }
        ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::This
        | ExprKind::Base => {}
    }
}
