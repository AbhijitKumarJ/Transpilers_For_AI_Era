use std::collections::HashMap;

use crate::frontend::ast::{
    Block, BorrowMode, CompilationUnit, Expr, ExprKind, ImportDecl, LambdaBody, MemberDecl,
    PrimitiveLowering, Stmt, TypeDecl, TypeRef,
};
use crate::semantics::symbols::GlobalSymbolTable;

/// Intrinsic lowering rule for a member on a `primitive` standard library type.
#[derive(Clone, Debug)]
pub struct IntrinsicMemberSpec {
    pub self_borrow: BorrowMode,
    pub param_borrows: Vec<BorrowMode>,
    pub lowering: PrimitiveLowering,
    pub return_type_name: Option<&'static str>,
}

/// Pass 2B `primitive` Type Erasure & Intrinsic Attribute Binder.
///
/// Binds `[MapsTo("...")]`, `[ParamType("...")]`, `[InlineTemplate("...")]`, and
/// `[Borrows]` / `[Mutates]` / `[Moves]` semantics onto AST nodes calling `primitive`
/// types (`List<T>`, `Dictionary<K,V>`, `HashSet<T>`, `String`/`string`, `ReadOnlySpan<T>`,
/// `Span<T>`, `Option<T>`, `SharedState<T>`, `Console`, and `TimeSpan`).
/// Works both when `stdlib/RustSharp.Core.d.rsharp` is loaded and in standalone unit tests.
pub fn resolve_primitives(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable) {
    let intrinsic_table = build_builtin_primitive_table();

    for unit in units.iter_mut() {
        if unit.is_ambient_stub {
            continue;
        }
        let current_ns = unit.namespace.clone();
        let imports = unit.imports.clone();

        for type_decl in &mut unit.types {
            bind_primitives_in_type(type_decl, &current_ns, &imports, &intrinsic_table, symtab);
        }
    }
}

/// Maps a `.rsharp` parameter `TypeRef` and its inferred `BorrowMode` into the idiomatic
/// Rust parameter type string (respecting `[ParamType("&str")]` and `[ParamType("&[{T}]")]`).
pub fn format_rust_param_type(
    ty: &TypeRef,
    mode: BorrowMode,
    symtab: &GlobalSymbolTable,
) -> String {
    let base_rust = format_rust_owned_type(ty, symtab);

    if ty.is_nullable {
        return match mode {
            BorrowMode::MutBorrow => format!("&mut {}", base_rust),
            _ => base_rust,
        };
    }

    match ty.short_name() {
        "string" | "String" => match mode {
            BorrowMode::ReadBorrow | BorrowMode::Unresolved => "&str".to_string(),
            BorrowMode::MutBorrow => "&mut String".to_string(),
            BorrowMode::OwnedMove | BorrowMode::CopyValue => "String".to_string(),
            BorrowMode::SharedArc => "std::sync::Arc<String>".to_string(),
        },
        "List" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            match mode {
                BorrowMode::ReadBorrow => format!("&[{}]", elem),
                BorrowMode::MutBorrow => format!("&mut Vec<{}>", elem),
                BorrowMode::OwnedMove | BorrowMode::Unresolved | BorrowMode::CopyValue => {
                    format!("Vec<{}>", elem)
                }
                BorrowMode::SharedArc => format!("std::sync::Arc<Vec<{}>>", elem),
            }
        }
        "HashSet" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            match mode {
                BorrowMode::ReadBorrow => format!("&std::collections::HashSet<{}>", elem),
                BorrowMode::MutBorrow => format!("&mut std::collections::HashSet<{}>", elem),
                BorrowMode::OwnedMove | BorrowMode::Unresolved | BorrowMode::CopyValue => {
                    format!("std::collections::HashSet<{}>", elem)
                }
                BorrowMode::SharedArc => {
                    format!("std::sync::Arc<std::collections::HashSet<{}>>", elem)
                }
            }
        }
        "Dictionary" => {
            let k = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            let v = ty
                .type_args
                .get(1)
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            match mode {
                BorrowMode::ReadBorrow => format!("&std::collections::HashMap<{}, {}>", k, v),
                BorrowMode::MutBorrow => format!("&mut std::collections::HashMap<{}, {}>", k, v),
                BorrowMode::OwnedMove | BorrowMode::Unresolved | BorrowMode::CopyValue => {
                    format!("std::collections::HashMap<{}, {}>", k, v)
                }
                BorrowMode::SharedArc => {
                    format!("std::sync::Arc<std::collections::HashMap<{}, {}>>", k, v)
                }
            }
        }
        "ReadOnlySpan" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "u8".to_string());
            format!("&[{}]", elem)
        }
        "Span" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "u8".to_string());
            format!("&mut [{}]", elem)
        }
        _ => match mode {
            BorrowMode::CopyValue | BorrowMode::OwnedMove => base_rust,
            BorrowMode::ReadBorrow | BorrowMode::Unresolved => format!("&{}", base_rust),
            BorrowMode::MutBorrow => format!("&mut {}", base_rust),
            BorrowMode::SharedArc => format!("std::sync::Arc<{}>", base_rust),
        },
    }
}

/// Maps a `.rsharp` `TypeRef` into its owned Rust type representation (`Vec<T>`, `HashMap<K,V>`, `i32`, etc.).
pub fn format_rust_owned_type(ty: &TypeRef, symtab: &GlobalSymbolTable) -> String {
    let core = match ty.short_name() {
        "void" => "()".to_string(),
        "bool" | "Boolean" => "bool".to_string(),
        "byte" | "Byte" => "u8".to_string(),
        "sbyte" | "SByte" => "i8".to_string(),
        "short" | "Int16" => "i16".to_string(),
        "ushort" | "UInt16" => "u16".to_string(),
        "int" | "Int32" => "i32".to_string(),
        "uint" | "UInt32" => "u32".to_string(),
        "long" | "Int64" => "i64".to_string(),
        "ulong" | "UInt64" => "u64".to_string(),
        "float" | "Single" => "f32".to_string(),
        "double" | "Double" => "f64".to_string(),
        "decimal" | "Decimal" => "Decimal".to_string(),
        "char" | "Char" => "char".to_string(),
        "string" | "String" => "String".to_string(),
        "List" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            format!("Vec<{}>", elem)
        }
        "Dictionary" => {
            let k = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            let v = ty
                .type_args
                .get(1)
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            format!("std::collections::HashMap<{}, {}>", k, v)
        }
        "HashSet" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            format!("std::collections::HashSet<{}>", elem)
        }
        "ReadOnlySpan" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "u8".to_string());
            format!("&[{}]", elem)
        }
        "Span" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "u8".to_string());
            format!("&mut [{}]", elem)
        }
        "Option" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            return format!("Option<{}>", elem);
        }
        "SharedState" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            format!("std::sync::Arc<std::sync::RwLock<{}>>", elem)
        }
        "TimeSpan" => "std::time::Duration".to_string(),
        "Task" | "ValueTask" => {
            if let Some(inner) = ty.type_args.first() {
                format_rust_owned_type(inner, symtab)
            } else {
                "()".to_string()
            }
        }
        "IAsyncEnumerable" => {
            let elem = ty
                .type_args
                .first()
                .map(|a| format_rust_owned_type(a, symtab))
                .unwrap_or_else(|| "_".to_string());
            format!("impl futures_core::Stream<Item = {}>", elem)
        }
        other => {
            // Check if registered as a `primitive` type in `GlobalSymbolTable`
            if let Some(candidates) = symtab.short_name_index.get(other) {
                for &cid in candidates {
                    if let Some(tsym) = symtab.types.get(&cid) {
                        if let Some(target) = &tsym.primitive_rust_target {
                            if ty.type_args.is_empty() {
                                return target.clone();
                            }
                            let rendered_args: Vec<String> = ty
                                .type_args
                                .iter()
                                .map(|a| format_rust_owned_type(a, symtab))
                                .collect();
                            if target.contains("{T}") {
                                return target.replace("{T}", &rendered_args[0]);
                            }
                            return format!("{}<{}>", target, rendered_args.join(", "));
                        }
                    }
                }
            }

            if ty.type_args.is_empty() {
                other.to_string()
            } else {
                let rendered_args: Vec<String> = ty
                    .type_args
                    .iter()
                    .map(|a| format_rust_owned_type(a, symtab))
                    .collect();
                format!("{}<{}>", other, rendered_args.join(", "))
            }
        }
    };

    if ty.is_nullable && !core.starts_with("Option<") {
        format!("Option<{}>", core)
    } else {
        core
    }
}

fn bind_primitives_in_type(
    type_decl: &mut TypeDecl,
    current_ns: &[String],
    imports: &[ImportDecl],
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) {
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

    for member in &mut type_decl.members {
        match member {
            MemberDecl::Method(m) => {
                let mut env = base_env.clone();
                for p in &m.params {
                    env.insert(p.name.clone(), p.ty.clone());
                }
                if let Some(body) = &mut m.body {
                    bind_primitives_in_block(
                        body, current_ns, imports, &mut env, intrinsics, symtab,
                    );
                }
            }
            MemberDecl::Constructor(c) => {
                let mut env = base_env.clone();
                for p in &c.params {
                    env.insert(p.name.clone(), p.ty.clone());
                }
                if let Some(body) = &mut c.body {
                    bind_primitives_in_block(
                        body, current_ns, imports, &mut env, intrinsics, symtab,
                    );
                }
            }
            MemberDecl::Property(p) => {
                for acc in &mut p.accessors {
                    if let Some(body) = &mut acc.body {
                        let mut env = base_env.clone();
                        bind_primitives_in_block(
                            body, current_ns, imports, &mut env, intrinsics, symtab,
                        );
                    }
                }
            }
            _ => {}
        }
    }
}

fn bind_primitives_in_block(
    block: &mut Block,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &mut HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) {
    for stmt in &mut block.stmts {
        bind_primitives_in_stmt(stmt, current_ns, imports, env, intrinsics, symtab);
    }
}

fn bind_primitives_in_stmt(
    stmt: &mut Stmt,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &mut HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) {
    match stmt {
        Stmt::Block(b) => {
            let mut inner = env.clone();
            bind_primitives_in_block(b, current_ns, imports, &mut inner, intrinsics, symtab);
        }
        Stmt::LocalVar {
            name,
            explicit_type,
            init,
            inferred_type,
            ..
        } => {
            bind_primitives_in_expr(init, current_ns, imports, env, intrinsics, symtab);
            let resolved = explicit_type
                .clone()
                .or_else(|| inferred_type.clone())
                .or_else(|| init.resolved_type.clone());
            if let Some(ty) = resolved {
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
            bind_primitives_in_expr(init, current_ns, imports, env, intrinsics, symtab);
            if let Some(ty) = explicit_type.clone().or_else(|| init.resolved_type.clone()) {
                env.insert(name.clone(), ty);
            }
        }
        Stmt::If {
            cond,
            then_branch,
            else_branch,
            ..
        } => {
            bind_primitives_in_expr(cond, current_ns, imports, env, intrinsics, symtab);
            bind_primitives_in_stmt(then_branch, current_ns, imports, env, intrinsics, symtab);
            if let Some(el) = else_branch {
                bind_primitives_in_stmt(el, current_ns, imports, env, intrinsics, symtab);
            }
        }
        Stmt::While { cond, body, .. } => {
            bind_primitives_in_expr(cond, current_ns, imports, env, intrinsics, symtab);
            bind_primitives_in_stmt(body, current_ns, imports, env, intrinsics, symtab);
        }
        Stmt::ForEach {
            item_name,
            item_type,
            collection,
            body,
            ..
        } => {
            bind_primitives_in_expr(collection, current_ns, imports, env, intrinsics, symtab);
            let mut inner = env.clone();
            if let Some(t) = item_type {
                inner.insert(item_name.clone(), t.clone());
            } else if let Some(ct) = &collection.resolved_type {
                if let Some(elem) = ct.type_args.first() {
                    inner.insert(item_name.clone(), elem.clone());
                }
            }
            bind_primitives_in_stmt(body, current_ns, imports, &mut inner, intrinsics, symtab);
        }
        Stmt::Return { value: Some(v), .. } => {
            bind_primitives_in_expr(v, current_ns, imports, env, intrinsics, symtab);
        }
        Stmt::Return { value: None, .. } => {}
        Stmt::Throw { error_expr, .. } => {
            bind_primitives_in_expr(error_expr, current_ns, imports, env, intrinsics, symtab);
        }
        Stmt::TryCatch {
            try_block, catches, ..
        } => {
            bind_primitives_in_block(try_block, current_ns, imports, env, intrinsics, symtab);
            for c in catches {
                let mut catch_env = env.clone();
                if let Some(v) = &c.var_name {
                    catch_env.insert(v.clone(), c.error_type.clone());
                }
                bind_primitives_in_block(
                    &mut c.body,
                    current_ns,
                    imports,
                    &mut catch_env,
                    intrinsics,
                    symtab,
                );
            }
        }
        Stmt::ExprStmt { expr, .. } => {
            bind_primitives_in_expr(expr, current_ns, imports, env, intrinsics, symtab);
        }
    }
}

fn bind_primitives_in_expr(
    expr: &mut Expr,
    current_ns: &[String],
    imports: &[ImportDecl],
    env: &HashMap<String, TypeRef>,
    intrinsics: &HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
    symtab: &GlobalSymbolTable,
) {
    let span = expr.span.clone();

    match &mut expr.kind {
        ExprKind::Identifier { name, .. } => {
            if expr.resolved_type.is_none() {
                if let Some(ty) = env.get(name) {
                    expr.resolved_type = Some(ty.clone());
                }
            }
        }

        ExprKind::Construct {
            ty,
            args,
            primitive_lowering,
            ..
        } => {
            for arg in args.iter_mut() {
                bind_primitives_in_expr(
                    &mut arg.expr,
                    current_ns,
                    imports,
                    env,
                    intrinsics,
                    symtab,
                );
            }
            if expr.resolved_type.is_none() {
                expr.resolved_type = Some(ty.clone());
            }

            if *primitive_lowering == PrimitiveLowering::None {
                let short = normalize_primitive_type_key(ty.short_name());
                let ctor_key = if args.is_empty() {
                    ".ctor_0"
                } else {
                    ".ctor_1"
                };
                if let Some(spec) = intrinsics.get(&(short, ctor_key)) {
                    *primitive_lowering = spec.lowering.clone();
                }
            }
        }

        ExprKind::MethodCall {
            receiver,
            method_name,
            args,
            primitive_lowering,
            ..
        } => {
            if let Some(recv) = receiver {
                bind_primitives_in_expr(recv, current_ns, imports, env, intrinsics, symtab);
            }
            for arg in args.iter_mut() {
                bind_primitives_in_expr(
                    &mut arg.expr,
                    current_ns,
                    imports,
                    env,
                    intrinsics,
                    symtab,
                );
            }

            if *primitive_lowering == PrimitiveLowering::None {
                let recv_key = if let Some(recv) = receiver {
                    if let Some(rty) = &recv.resolved_type {
                        Some(normalize_primitive_type_key(rty.short_name()))
                    } else if let ExprKind::Identifier { name, .. } = &recv.kind {
                        Some(normalize_primitive_type_key(name))
                    } else {
                        None
                    }
                } else {
                    None
                };

                if let Some(type_key) = recv_key {
                    if let Some(spec) = lookup_intrinsic(type_key, method_name, intrinsics) {
                        *primitive_lowering = spec.lowering.clone();
                        if expr.resolved_type.is_none() {
                            if let Some(ret_name) = spec.return_type_name {
                                expr.resolved_type = Some(TypeRef {
                                    span,
                                    path: vec![ret_name.to_string()],
                                    type_args: Vec::new(),
                                    is_nullable: false,
                                    is_primitive_keyword: matches!(
                                        ret_name,
                                        "void" | "bool" | "int" | "long" | "string" | "decimal"
                                    ),
                                });
                            }
                        }
                    }
                }
            }
        }

        ExprKind::MemberAccess { target, member, .. } => {
            bind_primitives_in_expr(target, current_ns, imports, env, intrinsics, symtab);
            if expr.resolved_type.is_none() {
                if let Some(rty) = &target.resolved_type {
                    let type_key = normalize_primitive_type_key(rty.short_name());
                    if let Some(spec) = lookup_intrinsic(type_key, member, intrinsics) {
                        if let Some(ret_name) = spec.return_type_name {
                            expr.resolved_type = Some(TypeRef {
                                span,
                                path: vec![ret_name.to_string()],
                                type_args: Vec::new(),
                                is_nullable: false,
                                is_primitive_keyword: matches!(
                                    ret_name,
                                    "void" | "bool" | "int" | "long" | "string" | "decimal"
                                ),
                            });
                        }
                    }
                }
            }
        }

        ExprKind::Assignment { target, value, .. } => {
            bind_primitives_in_expr(target, current_ns, imports, env, intrinsics, symtab);
            bind_primitives_in_expr(value, current_ns, imports, env, intrinsics, symtab);
        }
        ExprKind::Binary { left, right, .. } | ExprKind::NullCoalesce { left, right } => {
            bind_primitives_in_expr(left, current_ns, imports, env, intrinsics, symtab);
            bind_primitives_in_expr(right, current_ns, imports, env, intrinsics, symtab);
        }
        ExprKind::Unary { operand, .. } | ExprKind::IsPattern { expr: operand, .. } => {
            bind_primitives_in_expr(operand, current_ns, imports, env, intrinsics, symtab);
        }
        ExprKind::IndexAccess { target, indices } => {
            bind_primitives_in_expr(target, current_ns, imports, env, intrinsics, symtab);
            for idx in indices {
                bind_primitives_in_expr(
                    &mut idx.expr,
                    current_ns,
                    imports,
                    env,
                    intrinsics,
                    symtab,
                );
            }
        }
        ExprKind::RangeSlice { target, start, end } => {
            if let Some(t) = target {
                bind_primitives_in_expr(t, current_ns, imports, env, intrinsics, symtab);
            }
            if let Some(s) = start {
                bind_primitives_in_expr(s, current_ns, imports, env, intrinsics, symtab);
            }
            if let Some(e) = end {
                bind_primitives_in_expr(e, current_ns, imports, env, intrinsics, symtab);
            }
        }
        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => {
                bind_primitives_in_expr(e, current_ns, imports, env, intrinsics, symtab);
            }
            LambdaBody::Block(b) => {
                let mut inner = env.clone();
                bind_primitives_in_block(b, current_ns, imports, &mut inner, intrinsics, symtab);
            }
        },
        ExprKind::Switch { scrutinee, arms } => {
            bind_primitives_in_expr(scrutinee, current_ns, imports, env, intrinsics, symtab);
            for arm in arms {
                if let Some(g) = &mut arm.guard {
                    bind_primitives_in_expr(g, current_ns, imports, env, intrinsics, symtab);
                }
                bind_primitives_in_expr(
                    &mut arm.body,
                    current_ns,
                    imports,
                    env,
                    intrinsics,
                    symtab,
                );
            }
        }
        ExprKind::LinqChain(chain) => {
            bind_primitives_in_expr(
                &mut chain.source,
                current_ns,
                imports,
                env,
                intrinsics,
                symtab,
            );
        }
        ExprKind::Literal(_)
        | ExprKind::InterpolatedString(_)
        | ExprKind::This
        | ExprKind::Base => {}
    }
}

pub fn normalize_primitive_type_key(name: &str) -> &'static str {
    match name {
        "string" | "String" => "String",
        "List" => "List",
        "Dictionary" => "Dictionary",
        "HashSet" => "HashSet",
        "ReadOnlySpan" => "ReadOnlySpan",
        "Span" => "Span",
        "Option" => "Option",
        "SharedState" => "SharedState",
        "Console" => "Console",
        "TimeSpan" => "TimeSpan",
        "Math" => "Math",
        "int" | "Int32" => "Int32",
        "long" | "Int64" => "Int64",
        "double" | "Double" => "Double",
        "bool" | "Boolean" => "Boolean",
        "Environment" => "Environment",
        _ => "",
    }
}

pub fn lookup_intrinsic<'a>(
    type_key: &str,
    member_name: &str,
    table: &'a HashMap<(&'static str, &'static str), IntrinsicMemberSpec>,
) -> Option<&'a IntrinsicMemberSpec> {
    table
        .iter()
        .find(|((tk, mk), _)| *tk == type_key && *mk == member_name)
        .map(|(_, v)| v)
}

/// Returns the built-in specification table mirroring `stdlib/RustSharp.Core.d.rsharp`
/// so Pass 2B can resolve `primitive` borrow constraints and inline templates even in
/// single-file unit tests.
pub fn build_builtin_primitive_table() -> HashMap<(&'static str, &'static str), IntrinsicMemberSpec>
{
    let mut m = HashMap::new();

    // --- String (`std::string::String` / `&str`) ---
    m.insert(
        ("String", "Length"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.len() as i32".to_string(),
            },
            return_type_name: Some("int"),
        },
    );
    m.insert(
        ("String", "IsEmpty"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::DirectSymbol {
                rust_path: "is_empty".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );
    m.insert(
        ("String", "Contains"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.contains({0})".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );
    m.insert(
        ("String", "StartsWith"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.starts_with({0})".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );
    m.insert(
        ("String", "EndsWith"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.ends_with({0})".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );
    m.insert(
        ("String", "ToLower"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::DirectSymbol {
                rust_path: "to_lowercase".to_string(),
            },
            return_type_name: Some("string"),
        },
    );
    m.insert(
        ("String", "ToUpper"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::DirectSymbol {
                rust_path: "to_uppercase".to_string(),
            },
            return_type_name: Some("string"),
        },
    );
    m.insert(
        ("String", "Trim"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.trim().to_string()".to_string(),
            },
            return_type_name: Some("string"),
        },
    );

    // --- List<T> (`std::vec::Vec<T>`) ---
    m.insert(
        ("List", ".ctor_0"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::OwnedMove,
            param_borrows: vec![],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "Vec::new()".to_string(),
            },
            return_type_name: None,
        },
    );
    m.insert(
        ("List", ".ctor_1"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::OwnedMove,
            param_borrows: vec![BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "Vec::with_capacity({0} as usize)".to_string(),
            },
            return_type_name: None,
        },
    );
    m.insert(
        ("List", "Count"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.len() as i32".to_string(),
            },
            return_type_name: Some("int"),
        },
    );
    m.insert(
        ("List", "IsEmpty"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::DirectSymbol {
                rust_path: "is_empty".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );
    m.insert(
        ("List", "Add"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::MutBorrow,
            param_borrows: vec![BorrowMode::OwnedMove],
            lowering: PrimitiveLowering::DirectSymbol {
                rust_path: "push".to_string(),
            },
            return_type_name: Some("void"),
        },
    );
    m.insert(
        ("List", "RemoveAt"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::MutBorrow,
            param_borrows: vec![BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.remove({0} as usize)".to_string(),
            },
            return_type_name: None,
        },
    );
    m.insert(
        ("List", "Clear"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::MutBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::DirectSymbol {
                rust_path: "clear".to_string(),
            },
            return_type_name: Some("void"),
        },
    );
    m.insert(
        ("List", "Contains"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.contains(&{0})".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );

    // --- Dictionary<TKey, TValue> (`std::collections::HashMap<K, V>`) ---
    m.insert(
        ("Dictionary", ".ctor_0"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::OwnedMove,
            param_borrows: vec![],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "std::collections::HashMap::new()".to_string(),
            },
            return_type_name: None,
        },
    );
    m.insert(
        ("Dictionary", "Add"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::MutBorrow,
            param_borrows: vec![BorrowMode::OwnedMove, BorrowMode::OwnedMove],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.insert({0}, {1})".to_string(),
            },
            return_type_name: Some("void"),
        },
    );
    m.insert(
        ("Dictionary", "ContainsKey"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.contains_key(&{0})".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );
    m.insert(
        ("Dictionary", "Remove"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::MutBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.remove(&{0}).is_some()".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );
    m.insert(
        ("Dictionary", "Clear"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::MutBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::DirectSymbol {
                rust_path: "clear".to_string(),
            },
            return_type_name: Some("void"),
        },
    );

    // --- ReadOnlySpan<T> (`&[T]`) & Span<T> (`&mut [T]`) ---
    m.insert(
        ("ReadOnlySpan", "Length"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.len() as i32".to_string(),
            },
            return_type_name: Some("int"),
        },
    );
    m.insert(
        ("Span", "Length"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{self}.len() as i32".to_string(),
            },
            return_type_name: Some("int"),
        },
    );

    // --- Console ---
    m.insert(
        ("Console", "WriteLine"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "println!(\"{}\", {0})".to_string(),
            },
            return_type_name: Some("void"),
        },
    );
    m.insert(
        ("Console", "Write"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "print!(\"{}\", {0})".to_string(),
            },
            return_type_name: Some("void"),
        },
    );
    m.insert(
        ("Console", "WriteErrorLine"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "eprintln!(\"{}\", {0})".to_string(),
            },
            return_type_name: Some("void"),
        },
    );

    // --- Math ---
    m.insert(
        ("Math", "Min"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue, BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0}).min({1})".to_string(),
            },
            return_type_name: None,
        },
    );
    m.insert(
        ("Math", "Max"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue, BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0}).max({1})".to_string(),
            },
            return_type_name: None,
        },
    );
    m.insert(
        ("Math", "Abs"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0}).abs()".to_string(),
            },
            return_type_name: None,
        },
    );
    m.insert(
        ("Math", "Sqrt"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0} as f64).sqrt()".to_string(),
            },
            return_type_name: Some("double"),
        },
    );
    m.insert(
        ("Math", "Floor"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0} as f64).floor()".to_string(),
            },
            return_type_name: Some("double"),
        },
    );
    m.insert(
        ("Math", "Ceiling"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0} as f64).ceil()".to_string(),
            },
            return_type_name: Some("double"),
        },
    );
    m.insert(
        ("Math", "Round"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0} as f64).round()".to_string(),
            },
            return_type_name: Some("double"),
        },
    );
    m.insert(
        ("Math", "Pow"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue, BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0} as f64).powf({1} as f64)".to_string(),
            },
            return_type_name: Some("double"),
        },
    );
    m.insert(
        ("Math", "Clamp"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![
                BorrowMode::CopyValue,
                BorrowMode::CopyValue,
                BorrowMode::CopyValue,
            ],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "({0}).clamp({1}, {2})".to_string(),
            },
            return_type_name: None,
        },
    );

    // --- Int32 / Int64 / Double / Boolean ---
    m.insert(
        ("Int32", "Parse"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{0}.parse::<i32>().unwrap()".to_string(),
            },
            return_type_name: Some("int"),
        },
    );
    m.insert(
        ("Int32", "TryParse"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{0}.parse::<i32>().ok()".to_string(),
            },
            return_type_name: Some("int"),
        },
    );
    m.insert(
        ("Int64", "Parse"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{0}.parse::<i64>().unwrap()".to_string(),
            },
            return_type_name: Some("long"),
        },
    );
    m.insert(
        ("Double", "Parse"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{0}.parse::<f64>().unwrap()".to_string(),
            },
            return_type_name: Some("double"),
        },
    );
    m.insert(
        ("Boolean", "Parse"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{0}.parse::<bool>().unwrap()".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );

    // --- String static methods ---
    m.insert(
        ("String", "Join"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow, BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{1}.join({0})".to_string(),
            },
            return_type_name: Some("string"),
        },
    );
    m.insert(
        ("String", "IsNullOrEmpty"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{0}.is_empty()".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );
    m.insert(
        ("String", "IsNullOrWhiteSpace"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::ReadBorrow],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "{0}.trim().is_empty()".to_string(),
            },
            return_type_name: Some("bool"),
        },
    );

    // --- Environment ---
    m.insert(
        ("Environment", "Exit"),
        IntrinsicMemberSpec {
            self_borrow: BorrowMode::ReadBorrow,
            param_borrows: vec![BorrowMode::CopyValue],
            lowering: PrimitiveLowering::InlineTemplate {
                template: "std::process::exit({0})".to_string(),
            },
            return_type_name: Some("void"),
        },
    );

    m
}
