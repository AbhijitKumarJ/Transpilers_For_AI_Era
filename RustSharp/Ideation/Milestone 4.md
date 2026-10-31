Here are the complete, raw individual source files for **Milestone 4 (Pass 2B: `src/semantics/primitive_resolver.rs`, `src/semantics/borrow_inferencer.rs`, `src/semantics/effect_inferencer.rs`, `src/semantics/linq_fuser.rs`, updated `src/semantics/mod.rs` and `src/lib.rs`, and `tests/m4_borrow_and_effect_tests.rs`)** of the **RustSharp Prototype Transpiler (`rsharpc`)**.

---

### `src/semantics/primitive_resolver.rs`

```rust
use std::collections::HashMap;

use crate::frontend::ast::{
    Block, BorrowMode, CompilationUnit, Expr, ExprKind, ImportDecl, LambdaBody, MemberDecl,
    PrimitiveLowering, Stmt, SymbolId, TypeDecl, TypeKind, TypeRef,
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
                    bind_primitives_in_block(body, current_ns, imports, &mut env, intrinsics, symtab);
                }
            }
            MemberDecl::Constructor(c) => {
                let mut env = base_env.clone();
                for p in &c.params {
                    env.insert(p.name.clone(), p.ty.clone());
                }
                if let Some(body) = &mut c.body {
                    bind_primitives_in_block(body, current_ns, imports, &mut env, intrinsics, symtab);
                }
            }
            MemberDecl::Property(p) => {
                for acc in &mut p.accessors {
                    if let Some(body) = &mut acc.body {
                        let mut env = base_env.clone();
                        bind_primitives_in_block(
                            body,
                            current_ns,
                            imports,
                            &mut env,
                            intrinsics,
                            symtab,
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
                bind_primitives_in_expr(&mut arg.expr, current_ns, imports, env, intrinsics, symtab);
            }
            if expr.resolved_type.is_none() {
                expr.resolved_type = Some(ty.clone());
            }

            if *primitive_lowering == PrimitiveLowering::None {
                let short = normalize_primitive_type_key(ty.short_name());
                let ctor_key = if args.is_empty() { ".ctor_0" } else { ".ctor_1" };
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
                bind_primitives_in_expr(&mut arg.expr, current_ns, imports, env, intrinsics, symtab);
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
                bind_primitives_in_expr(&mut idx.expr, current_ns, imports, env, intrinsics, symtab);
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
                bind_primitives_in_expr(&mut arm.body, current_ns, imports, env, intrinsics, symtab);
            }
        }
        ExprKind::LinqChain(chain) => {
            bind_primitives_in_expr(&mut chain.source, current_ns, imports, env, intrinsics, symtab);
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
pub fn build_builtin_primitive_table() -> HashMap<(&'static str, &'static str), IntrinsicMemberSpec> {
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

    m
}

```

---

### `src/semantics/borrow_inferencer.rs`

```rust
use std::collections::{HashMap, HashSet};

use crate::frontend::ast::{
    Block, BorrowMode, CallerArgCoercion, CompilationUnit, Expr, ExprKind, LambdaBody, MemberDecl,
    MethodDecl, Stmt, SymbolId, TypeDecl, TypeKind, TypeRef,
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
            method.inferred_self_borrow = if is_service || is_shared {
                BorrowMode::ReadBorrow
            } else {
                BorrowMode::ReadBorrow
            };
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
            collection, body, ..
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
                let recv_ty = recv.resolved_type.as_ref().or_else(|| {
                    extract_root_ident(recv).and_then(|n| var_types.get(&n))
                });
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
                let recv_ty = recv.resolved_type.as_ref().or_else(|| {
                    extract_root_ident(recv).and_then(|n| var_types.get(&n))
                });
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
                annotate_expr_coercions(&mut arg.expr, param_borrows, var_types, intrinsics, symtab);
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
                let recv_ty = recv.resolved_type.as_ref().or_else(|| {
                    extract_root_ident(recv).and_then(|n| var_types.get(&n))
                });
                if let Some(rty) = recv_ty {
                    let tkey = normalize_primitive_type_key(rty.short_name());
                    if let Some(spec) = lookup_intrinsic(tkey, method_name, intrinsics) {
                        for (i, arg) in args.iter_mut().enumerate() {
                            if let Some(&target_mode) = spec.param_borrows.get(i) {
                                arg.expr.caller_coercion = compute_arg_coercion(
                                    &arg.expr,
                                    target_mode,
                                    param_borrows,
                                );
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
                annotate_expr_coercions(&mut arg.expr, param_borrows, var_types, intrinsics, symtab);
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
                annotate_expr_coercions(&mut idx.expr, param_borrows, var_types, intrinsics, symtab);
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
                annotate_expr_coercions(&mut arm.body, param_borrows, var_types, intrinsics, symtab);
            }
        }
        ExprKind::LinqChain(chain) => {
            annotate_expr_coercions(&mut chain.source, param_borrows, var_types, intrinsics, symtab);
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

```

---

### `src/semantics/effect_inferencer.rs`

```rust
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
        Stmt::While { cond, body, .. } => {
            find_uncaught_effect_in_expr(cond, caught_errors, symtab)
                .or_else(|| find_uncaught_effect_in_stmt(body, caught_errors, symtab))
        }
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

```

---

### `src/semantics/linq_fuser.rs`

```rust
use std::collections::HashSet;

use crate::frontend::ast::{
    Block, CompilationUnit, Expr, ExprKind, LambdaBody, LinqChain, LinqOp, LinqTerminal,
    MemberDecl, Stmt,
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

fn fuse_linq_in_stmt(
    stmt: &mut Stmt,
    used_later: &HashSet<String>,
    param_names: &HashSet<String>,
) {
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

fn fuse_linq_in_expr(
    expr: &mut Expr,
    used_later: &HashSet<String>,
    param_names: &HashSet<String>,
) {
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
        expr.kind = ExprKind::LinqChain(fused_chain);
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
        "FirstOrDefault" if args.len() <= 1 => LinqTerminal::FirstOrDefault {
            predicate: args.first().map(|a| a.expr.clone()),
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
pub mod primitive_resolver;
pub mod symbols;

pub use archetype_analyzer::analyze_archetypes;
pub use borrow_inferencer::InterproceduralBorrowInferencer;
pub use collector::collect_global_symbols;
pub use effect_inferencer::infer_checked_effects;
pub use hierarchy_lowerer::resolve_polymorphism_strategies;
pub use linq_fuser::fuse_linq_pipelines;
pub use overload_resolver::resolve_overloads;
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
    resolve_overloads, resolve_polymorphism_strategies, resolve_primitives, GlobalSymbolTable,
    InterproceduralBorrowInferencer,
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

```

---

### `tests/m4_borrow_and_effect_tests.rs`

```rust
use rsharpc::analyze_workspace_pass2b;
use rsharpc::frontend::ast::{
    BorrowMode, CallerArgCoercion, EffectSignature, ExprKind, LinqOp, LinqTerminal, MemberDecl,
    PrimitiveLowering, Stmt,
};
use rsharpc::semantics::format_rust_param_type;

#[test]
fn test_bottom_up_interprocedural_mut_borrow_propagation_and_caller_coercion() {
    let checkout_src = r#"
namespace Commerce.Checkout;

public record Order(int Id, decimal Total);
public record ValidationError(string Reason);

public service class TaxCalculator
{
    public void RecordAudit(Order order)
    {
    }
}

public service class OrderHandler
{
    private readonly TaxCalculator _tax;

    public OrderHandler(TaxCalculator tax) => _tax = tax;

    public void Checkout(Order order, string coupon) throws ValidationError
    {
        if (order.Total <= 0.0m)
            throw new ValidationError("Order total must be positive");

        ApplyCoupon(order, coupon);
        _tax.RecordAudit(order);
    }

    private void ApplyCoupon(Order order, string code)
    {
        if (code == "SAVE10")
            order.Total -= 10.0m;
    }

    public void RunDemo()
    {
        var localOrder = new Order(101, 250.0m);
        ApplyCoupon(localOrder, "SAVE10");
    }
}
"#;

    let (units, symtab, diag) =
        analyze_workspace_pass2b(&[("Features/Checkout/OrderHandler.rsharp", checkout_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let handler_id = symtab.fqn_to_symbol["Commerce.Checkout.OrderHandler"];
    let handler_sym = &symtab.types[&handler_id];

    let checkout_id = handler_sym.methods[0];
    let apply_coupon_id = handler_sym.methods[1];

    // 1. `ApplyCoupon` directly mutates `order.Total -= 10.0m` -> `MutBorrow` (&mut Order),
    //    while `code` is only read -> `ReadBorrow` (&str)
    let apply_sym = &symtab.methods[&apply_coupon_id];
    assert_eq!(apply_sym.inferred_self_borrow, BorrowMode::ReadBorrow);
    assert_eq!(apply_sym.params[0].inferred_borrow, BorrowMode::MutBorrow);
    assert_eq!(apply_sym.params[1].inferred_borrow, BorrowMode::ReadBorrow);
    assert_eq!(
        format_rust_param_type(
            &apply_sym.params[1].ty,
            apply_sym.params[1].inferred_borrow,
            &symtab
        ),
        "&str"
    );

    // 2. `Checkout` does NOT mutate `order` directly, but passes `order` to `ApplyCoupon`.
    //    Bottom-up interprocedural propagation upgrades `Checkout`'s `order` parameter to `MutBorrow`!
    let checkout_sym = &symtab.methods[&checkout_id];
    assert_eq!(
        checkout_sym.params[0].inferred_borrow,
        BorrowMode::MutBorrow,
        "Expected bottom-up interprocedural propagation to upgrade Checkout's 'order' to MutBorrow"
    );
    assert_eq!(
        checkout_sym.params[1].inferred_borrow,
        BorrowMode::ReadBorrow
    );

    // 3. Inspect `Checkout` body call-site coercions (`ApplyCoupon` gets `BorrowMutable`,
    //    and subsequent `_tax.RecordAudit(order)` gets `BorrowShared`)
    let handler_decl = &units[0].types[3];
    let checkout_decl = match &handler_decl.members[2] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected Checkout method"),
    };
    let checkout_stmts = &checkout_decl.body.as_ref().unwrap().stmts;

    match &checkout_stmts[1] {
        Stmt::ExprStmt { expr, .. } => match &expr.kind {
            ExprKind::MethodCall { args, .. } => {
                assert_eq!(args[0].expr.caller_coercion, CallerArgCoercion::BorrowMutable);
                assert_eq!(args[1].expr.caller_coercion, CallerArgCoercion::BorrowShared);
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected ExprStmt, got {:?}", other),
    }

    match &checkout_stmts[2] {
        Stmt::ExprStmt { expr, .. } => match &expr.kind {
            ExprKind::MethodCall { args, .. } => {
                assert_eq!(args[0].expr.caller_coercion, CallerArgCoercion::BorrowShared);
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected ExprStmt, got {:?}", other),
    }

    // 4. Inspect `RunDemo`: `var localOrder = new Order(...)` is passed to `ApplyCoupon`
    //    so `inferred_mut` is automatically set to `true` (`let mut local_order`)!
    let run_demo_decl = match &handler_decl.members[4] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected RunDemo method"),
    };
    match &run_demo_decl.body.as_ref().unwrap().stmts[0] {
        Stmt::LocalVar {
            name, inferred_mut, ..
        } => {
            assert_eq!(name, "localOrder");
            assert!(
                *inferred_mut,
                "Expected local variable passed to &mut parameter to be marked `inferred_mut = true`"
            );
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }
}

#[test]
fn test_checked_effect_throws_propagation_and_question_mark_injection() {
    let config_src = r#"
namespace Commerce.Config;

public record ParseError(string Message);

public static class ConfigLoader
{
    public static int ParsePort(string raw) throws ParseError
    {
        if (raw.IsEmpty)
            throw new ParseError("Port string cannot be empty");
        return 8080;
    }

    public static int ValidateAndDoublePort(string raw) throws ParseError
    {
        var port = ParsePort(raw);
        return port * 2;
    }

    public static int LoadDefaultPort(string input)
    {
        try
        {
            return ParsePort(input);
        }
        catch (ParseError err)
        {
            return 80;
        }
    }
}
"#;

    let (units, symtab, diag) =
        analyze_workspace_pass2b(&[("Config/ConfigLoader.rsharp", config_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let loader_id = symtab.fqn_to_symbol["Commerce.Config.ConfigLoader"];
    let loader_sym = &symtab.types[&loader_id];

    let parse_port_id = loader_sym.methods[0];
    let validate_double_id = loader_sym.methods[1];
    let load_default_id = loader_sym.methods[2];

    // 1. `ParsePort` and `ValidateAndDoublePort` are `Fallible { error_type: ParseError }`
    assert!(matches!(
        symtab.methods[&parse_port_id].inferred_effect,
        EffectSignature::Fallible { .. }
    ));
    assert!(matches!(
        symtab.methods[&validate_double_id].inferred_effect,
        EffectSignature::Fallible { .. }
    ));

    // 2. `LoadDefaultPort` catches `ParseError` in `try / catch`, so its effect is `Infallible`!
    assert_eq!(
        symtab.methods[&load_default_id].inferred_effect,
        EffectSignature::Infallible
    );

    // 3. Inside `ValidateAndDoublePort`, the unguarded call `ParsePort(raw)` has
    //    `append_try_question_mark = true` (`parse_port(raw)?`)
    let loader_decl = &units[0].types[1];
    let validate_decl = match &loader_decl.members[1] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected ValidateAndDoublePort method"),
    };
    match &validate_decl.body.as_ref().unwrap().stmts[0] {
        Stmt::LocalVar { init, .. } => {
            assert!(
                init.append_try_question_mark,
                "Expected unguarded call to fallible ParsePort(raw) to have append_try_question_mark = true"
            );
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }
}

#[test]
fn test_linq_to_iterator_pipeline_fusion_and_primitive_lowering() {
    let linq_src = r#"
namespace Commerce.Analytics;

public record Order(int Id, decimal Total, bool IsActive);

public service class OrderAnalytics
{
    public List<int> GetHighValueIds(List<Order> orders)
    {
        var ids = orders
            .Where(o => o.IsActive && o.Total >= 100.0m)
            .Select(o => o.Id)
            .ToList();
        ids.Add(999);
        return ids;
    }

    public bool HasAnyActive(List<Order> orders)
    {
        return orders.Any(o => o.IsActive);
    }
}
"#;

    let (units, symtab, diag) =
        analyze_workspace_pass2b(&[("Analytics/OrderAnalytics.rsharp", linq_src)]);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let analytics_id = symtab.fqn_to_symbol["Commerce.Analytics.OrderAnalytics"];
    let get_ids_id = symtab.types[&analytics_id].methods[0];
    let get_ids_sym = &symtab.methods[&get_ids_id];

    // `orders` parameter is only read by `.Where().Select().ToList()` -> `ReadBorrow` (`&[Order]`)
    assert_eq!(get_ids_sym.params[0].inferred_borrow, BorrowMode::ReadBorrow);
    assert_eq!(
        format_rust_param_type(
            &get_ids_sym.params[0].ty,
            get_ids_sym.params[0].inferred_borrow,
            &symtab
        ),
        "&[Order]"
    );

    let analytics_decl = &units[0].types[1];
    let get_ids_decl = match &analytics_decl.members[0] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected GetHighValueIds method"),
    };
    let stmts = &get_ids_decl.body.as_ref().unwrap().stmts;

    // Statement 0: `var ids = orders.Where(...).Select(...).ToList();`
    // Verifies both `inferred_mut = true` (because `ids.Add(999)` mutates `ids` on the next line)
    // and `ExprKind::LinqChain` fusion!
    match &stmts[0] {
        Stmt::LocalVar {
            name,
            init,
            inferred_mut,
            ..
        } => {
            assert_eq!(name, "ids");
            assert!(
                *inferred_mut,
                "Expected `ids` to be marked `inferred_mut = true` due to `ids.Add(999)`"
            );
            match &init.kind {
                ExprKind::LinqChain(chain) => {
                    assert!(!chain.consumes_source);
                    assert_eq!(chain.ops.len(), 2);
                    assert!(matches!(chain.ops[0], LinqOp::Where { .. }));
                    assert!(matches!(chain.ops[1], LinqOp::Select { .. }));
                    assert_eq!(chain.terminal, LinqTerminal::ToList);
                }
                other => panic!("Expected fused ExprKind::LinqChain, got {:?}", other),
            }
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 1: `ids.Add(999);` -> resolved to `PrimitiveLowering::DirectSymbol { rust_path: "push" }`
    match &stmts[1] {
        Stmt::ExprStmt { expr, .. } => match &expr.kind {
            ExprKind::MethodCall {
                primitive_lowering, ..
            } => {
                assert_eq!(
                    *primitive_lowering,
                    PrimitiveLowering::DirectSymbol {
                        rust_path: "push".to_string()
                    }
                );
            }
            other => panic!("Expected MethodCall, got {:?}", other),
        },
        other => panic!("Expected ExprStmt, got {:?}", other),
    }
}

```

---

Would you like me to continue with the raw individual files for **Milestone 5 (Pass 2.5: Pre-Flight Ownership Verifier `src/semantics/preflight_verifier.rs` enforcing rules `RSHARP001`–`RSHARP003`, updated `src/semantics/mod.rs` and `src/lib.rs`, and `tests/m5_preflight_diagnostics_tests.rs`)** next?
