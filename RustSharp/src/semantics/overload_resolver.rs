use std::collections::{HashMap, HashSet};

use crate::frontend::ast::{
    ArgNode, Block, CompilationUnit, ConstructorDecl, Expr, ExprKind, ImportDecl, LambdaBody,
    LiteralValue, MemberDecl, ParamDecl, Stmt, SymbolId, TypeDecl, TypeRef,
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
    let suffixes: Vec<String> = params.iter().map(|p| sanitize_type_suffix(&p.ty)).collect();
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
            let var_ty = explicit_type.clone().or_else(|| init.resolved_type.clone());
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
            let var_ty = explicit_type.clone().or_else(|| init.resolved_type.clone());
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
                resolve_calls_in_stmt(el, owner_id, current_ns, imports, env, default_args, symtab);
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
                    if let Some((mem_id, mem_ty)) =
                        lookup_field_or_prop(recv_sym_id, member, symtab)
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
                        inject_missing_default_args(
                            args,
                            &msym.params,
                            matched_method_id,
                            default_args,
                        );
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
                        inject_missing_default_args(
                            args,
                            &csym.params,
                            matched_ctor_id,
                            default_args,
                        );
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
            expr.resolved_type = right
                .resolved_type
                .clone()
                .or_else(|| left.resolved_type.clone());
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
                resolve_calls_in_expr(t, owner_id, current_ns, imports, env, default_args, symtab);
                expr.resolved_type = t.resolved_type.clone();
            }
            if let Some(s) = start {
                resolve_calls_in_expr(s, owner_id, current_ns, imports, env, default_args, symtab);
            }
            if let Some(e) = end {
                resolve_calls_in_expr(e, owner_id, current_ns, imports, env, default_args, symtab);
            }
        }

        ExprKind::Lambda { body, .. } => match body {
            LambdaBody::Expr(e) => {
                resolve_calls_in_expr(e, owner_id, current_ns, imports, env, default_args, symtab);
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
            for arm in arms.iter_mut() {
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
