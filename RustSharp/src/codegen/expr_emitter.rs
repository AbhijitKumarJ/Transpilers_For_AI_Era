use std::collections::{HashMap, HashSet};

use crate::codegen::sourcemap::RustSourceMap;
use crate::frontend::ast::{
    AssignOp, BinaryOp, Block, BorrowMode, CallerArgCoercion, Expr, ExprKind, FieldStorageMode,
    LambdaBody, LinqChain, LinqOp, LinqTerminal, LiteralValue, Pattern, PrimitiveLowering, Stmt,
    SymbolId, TypeKind, TypeRef, UnaryOp,
};
use crate::frontend::tokens::InterpPart;
use crate::semantics::primitive_resolver::format_rust_owned_type;
use crate::semantics::symbols::{pascal_to_snake_case, GlobalSymbolTable};

/// Pass 3 Idiomatic Rust Statement & Expression Emitter.
///
/// Lowers decorated `.rsharp` statements and expressions into zero-cost Rust syntax:
/// - Applies caller argument coercions (`&`, `&mut`, `&*`, `.clone()`, `Arc::clone(&...)`).
/// - Expands `[InlineTemplate("...")]` and `[MapsTo("...")]` primitive operations.
/// - Emits fused `.iter().filter(...).map(...).collect()` pipelines from `ExprKind::LinqChain`.
/// - Emits `Result<T, E>` propagation (`?`), `Ok(...)` / `Err(...)` wrapping, and `try / catch` `match` blocks.
/// - Lowers `10.0m` decimal literals to `Decimal::new(mantissa, scale)` and `..` slices to `&buf[a..b]`.
pub struct RustExprEmitter<'a> {
    pub symtab: &'a GlobalSymbolTable,
    pub current_type_id: Option<SymbolId>,
    pub type_fields: HashMap<String, FieldStorageMode>,
    pub base_struct_fields: HashSet<String>,
    pub method_param_borrows: HashMap<String, BorrowMode>,
    pub is_fallible_method: bool,
    pub is_void_return: bool,
    pub return_type_name: Option<String>,
    pub block_depth: usize,
}

impl<'a> RustExprEmitter<'a> {
    pub fn new(symtab: &'a GlobalSymbolTable, current_type_id: Option<SymbolId>) -> Self {
        let mut type_fields = HashMap::new();
        let mut base_struct_fields = HashSet::new();

        if let Some(tid) = current_type_id {
            if let Some(tsym) = symtab.types.get(&tid) {
                for &fid in &tsym.fields {
                    if let Some(f) = symtab.fields.get(&fid) {
                        type_fields.insert(f.name.clone(), f.storage_mode);
                    }
                }
                for &pid in &tsym.properties {
                    if let Some(p) = symtab.properties.get(&pid) {
                        type_fields.insert(p.name.clone(), p.storage_mode);
                    }
                }
                for &base_id in &tsym.resolved_base_type_ids {
                    if let Some(bsym) = symtab.types.get(&base_id) {
                        for &bfid in &bsym.fields {
                            if let Some(bf) = symtab.fields.get(&bfid) {
                                base_struct_fields.insert(bf.name.clone());
                            }
                        }
                        for &bpid in &bsym.properties {
                            if let Some(bp) = symtab.properties.get(&bpid) {
                                base_struct_fields.insert(bp.name.clone());
                            }
                        }
                    }
                }
            }
        }

        Self {
            symtab,
            current_type_id,
            type_fields,
            base_struct_fields,
            method_param_borrows: HashMap::new(),
            is_fallible_method: false,
            is_void_return: true,
            return_type_name: None,
            block_depth: 0,
        }
    }

    pub fn emit_block(
        &mut self,
        block: &Block,
        indent: usize,
        sourcemap: &mut RustSourceMap,
        current_rs_line: &mut u32,
    ) -> String {
        self.block_depth += 1;
        let is_top_level = self.block_depth == 1;
        let mut lines = Vec::new();
        let len = block.stmts.len();

        for (idx, stmt) in block.stmts.iter().enumerate() {
            let is_last = is_top_level && (idx + 1 == len);
            let rendered = self.emit_stmt(stmt, indent, is_last, sourcemap, current_rs_line);
            if !rendered.is_empty() {
                lines.push(rendered);
            }
        }

        // If the method is `Fallible` (`throws TError`) and returns `void` (`Result<(), E>`),
        // append the trailing `Ok(())` if the block doesn't already end with an explicit return/throw.
        if is_top_level && self.is_fallible_method && self.is_void_return {
            let ends_with_terminator = block
                .stmts
                .last()
                .map(|s| matches!(s, Stmt::Return { .. } | Stmt::Throw { .. }))
                .unwrap_or(false);
            if !ends_with_terminator {
                let pad = "    ".repeat(indent);
                lines.push(format!("{}Ok(())", pad));
                *current_rs_line += 1;
            }
        }

        self.block_depth -= 1;
        lines.join("\n")
    }

    pub fn emit_stmt(
        &mut self,
        stmt: &Stmt,
        indent: usize,
        is_last_in_block: bool,
        sourcemap: &mut RustSourceMap,
        current_rs_line: &mut u32,
    ) -> String {
        let pad = "    ".repeat(indent);

        match stmt {
            Stmt::Block(b) => {
                let mut out = format!("{}{{\n", pad);
                *current_rs_line += 1;
                let inner = self.emit_block(b, indent + 1, sourcemap, current_rs_line);
                if !inner.is_empty() {
                    out.push_str(&inner);
                    out.push('\n');
                }
                out.push_str(&format!("{}}}", pad));
                *current_rs_line += 1;
                out
            }

            Stmt::LocalVar {
                span,
                name,
                explicit_type,
                init,
                inferred_mut,
                ..
            } => {
                sourcemap.record(*current_rs_line, span);
                let var_snake = normalize_local_ident(name);
                let mut_kw = if *inferred_mut { "mut " } else { "" };

                let type_annot = if let Some(ty) = explicit_type {
                    format!(": {}", format_rust_owned_type(ty, self.symtab))
                } else {
                    String::new()
                };

                let rhs = self.emit_expr(init);
                *current_rs_line += 1;
                format!("{}let {}{}{}= {};", pad, mut_kw, var_snake, type_annot, rhs)
            }

            Stmt::UsingResource {
                span,
                name,
                explicit_type,
                init,
                inferred_mut,
                ..
            } => {
                sourcemap.record(*current_rs_line, span);
                let var_snake = normalize_local_ident(name);
                let mut_kw = if *inferred_mut { "mut " } else { "" };
                let type_annot = explicit_type
                    .as_ref()
                    .map(|ty| format!(": {}", format_rust_owned_type(ty, self.symtab)))
                    .unwrap_or_default();
                let rhs = self.emit_expr(init);
                *current_rs_line += 1;
                format!(
                    "{}let {}{}{}= {}; // RAII Drop at scope exit",
                    pad, mut_kw, var_snake, type_annot, rhs
                )
            }

            Stmt::If {
                span,
                cond,
                then_branch,
                else_branch,
            } => {
                sourcemap.record(*current_rs_line, span);
                let cond_str = self.emit_expr(cond);
                let mut out = format!("{}if {} {{\n", pad, cond_str);
                *current_rs_line += 1;

                let then_body =
                    self.emit_branch_contents(then_branch, indent + 1, sourcemap, current_rs_line);
                if !then_body.is_empty() {
                    out.push_str(&then_body);
                    out.push('\n');
                }
                out.push_str(&format!("{}}}", pad));

                if let Some(el) = else_branch {
                    out.push_str(" else {\n");
                    *current_rs_line += 1;
                    let else_body =
                        self.emit_branch_contents(el, indent + 1, sourcemap, current_rs_line);
                    if !else_body.is_empty() {
                        out.push_str(&else_body);
                        out.push('\n');
                    }
                    out.push_str(&format!("{}}}", pad));
                }

                *current_rs_line += 1;
                out
            }

            Stmt::While { span, cond, body } => {
                sourcemap.record(*current_rs_line, span);
                let cond_str = self.emit_expr(cond);
                let mut out = format!("{}while {} {{\n", pad, cond_str);
                *current_rs_line += 1;
                let inner = self.emit_branch_contents(body, indent + 1, sourcemap, current_rs_line);
                if !inner.is_empty() {
                    out.push_str(&inner);
                    out.push('\n');
                }
                out.push_str(&format!("{}}}", pad));
                *current_rs_line += 1;
                out
            }

            Stmt::ForEach {
                span,
                item_name,
                collection,
                body,
                iter_borrow_mode,
                ..
            } => {
                sourcemap.record(*current_rs_line, span);
                let item_snake = normalize_local_ident(item_name);
                let coll_str = self.emit_expr(collection);
                let iter_method = match iter_borrow_mode {
                    BorrowMode::MutBorrow => "iter_mut()",
                    BorrowMode::OwnedMove => "into_iter()",
                    _ => "iter()",
                };
                let mut out = format!(
                    "{}for {} in {}.{} {{\n",
                    pad, item_snake, coll_str, iter_method
                );
                *current_rs_line += 1;
                let inner = self.emit_branch_contents(body, indent + 1, sourcemap, current_rs_line);
                if !inner.is_empty() {
                    out.push_str(&inner);
                    out.push('\n');
                }
                out.push_str(&format!("{}}}", pad));
                *current_rs_line += 1;
                out
            }

            Stmt::Return { span, value } => {
                sourcemap.record(*current_rs_line, span);
                *current_rs_line += 1;
                match value {
                    Some(v) => {
                        let mut rendered = self.emit_expr(v);
                        if let Some(ret) = &self.return_type_name {
                            if (ret == "string" || ret == "String")
                                && matches!(v.kind, ExprKind::Literal(LiteralValue::String(_)))
                            {
                                rendered = format!("{}.to_string()", rendered);
                            } else if matches!(&v.kind, ExprKind::MemberAccess { target, .. } if matches!(target.kind, ExprKind::This))
                                && !rendered.ends_with(".clone()")
                            {
                                rendered = format!("{}.clone()", rendered);
                            }
                        }
                        if self.is_fallible_method {
                            if is_last_in_block {
                                format!("{}Ok({})", pad, rendered)
                            } else {
                                format!("{}return Ok({});", pad, rendered)
                            }
                        } else if is_last_in_block {
                            format!("{}{}", pad, rendered)
                        } else {
                            format!("{}return {};", pad, rendered)
                        }
                    }
                    None => {
                        if self.is_fallible_method {
                            format!("{}return Ok(());", pad)
                        } else {
                            format!("{}return;", pad)
                        }
                    }
                }
            }

            Stmt::Throw { span, error_expr } => {
                sourcemap.record(*current_rs_line, span);
                let err_rendered = self.emit_expr(error_expr);
                *current_rs_line += 1;
                format!("{}return Err({});", pad, err_rendered)
            }

            Stmt::TryCatch {
                span,
                try_block,
                catches,
            } => {
                sourcemap.record(*current_rs_line, span);
                self.emit_try_catch_match(try_block, catches, indent, sourcemap, current_rs_line)
            }

            Stmt::ExprStmt { span, expr } => {
                sourcemap.record(*current_rs_line, span);
                let rendered = self.emit_expr(expr);
                *current_rs_line += 1;
                format!("{}{};", pad, rendered)
            }
        }
    }

    fn emit_branch_contents(
        &mut self,
        branch: &Stmt,
        indent: usize,
        sourcemap: &mut RustSourceMap,
        current_rs_line: &mut u32,
    ) -> String {
        match branch {
            Stmt::Block(b) => {
                let saved_fallible = self.is_fallible_method;
                let saved_void = self.is_void_return;
                self.is_void_return = false; // prevent implicit `Ok(())` inside nested `if/while/for` blocks
                let out = self.emit_block(b, indent, sourcemap, current_rs_line);
                self.is_fallible_method = saved_fallible;
                self.is_void_return = saved_void;
                out
            }
            single => self.emit_stmt(single, indent, false, sourcemap, current_rs_line),
        }
    }

    fn emit_try_catch_match(
        &mut self,
        try_block: &Block,
        catches: &[crate::frontend::ast::CatchArm],
        indent: usize,
        sourcemap: &mut RustSourceMap,
        current_rs_line: &mut u32,
    ) -> String {
        let pad = "    ".repeat(indent);
        let arm_pad = "    ".repeat(indent + 1);

        // Single-statement `try { return FallibleCall(...); } catch (E err) { ... }`
        let scrutinee_str = if try_block.stmts.len() == 1 {
            match &try_block.stmts[0] {
                Stmt::Return {
                    value: Some(expr), ..
                }
                | Stmt::ExprStmt { expr, .. } => self.emit_expr(expr),
                _ => "(() -> Result<_, _> { Ok(()) })()".to_string(),
            }
        } else {
            "(() -> Result<_, _> { Ok(()) })()".to_string()
        };

        let mut out = format!("{}match {} {{\n", pad, scrutinee_str);
        *current_rs_line += 1;
        out.push_str(&format!("{}Ok(_val) => _val,\n", arm_pad));
        *current_rs_line += 1;

        if let Some(first_catch) = catches.first() {
            let err_var = first_catch
                .var_name
                .as_deref()
                .map(normalize_local_ident)
                .unwrap_or_else(|| "_err".to_string());

            if first_catch.body.stmts.len() == 1 {
                if let Stmt::Return { value: Some(v), .. } = &first_catch.body.stmts[0] {
                    let catch_expr = self.emit_expr(v);
                    out.push_str(&format!("{}Err({}) => {},\n", arm_pad, err_var, catch_expr));
                    *current_rs_line += 1;
                } else {
                    out.push_str(&format!("{}Err({}) => {{\n", arm_pad, err_var));
                    *current_rs_line += 1;
                    let inner =
                        self.emit_block(&first_catch.body, indent + 2, sourcemap, current_rs_line);
                    out.push_str(&inner);
                    out.push_str(&format!("\n{}}}\n", arm_pad));
                    *current_rs_line += 1;
                }
            } else {
                out.push_str(&format!("{}Err({}) => {{\n", arm_pad, err_var));
                *current_rs_line += 1;
                let inner =
                    self.emit_block(&first_catch.body, indent + 2, sourcemap, current_rs_line);
                out.push_str(&inner);
                out.push_str(&format!("\n{}}}\n", arm_pad));
                *current_rs_line += 1;
            }
        } else {
            out.push_str(&format!("{}Err(_err) => Default::default(),\n", arm_pad));
            *current_rs_line += 1;
        }

        out.push_str(&format!("{}}}", pad));
        *current_rs_line += 1;
        out
    }

    pub fn emit_expr(&mut self, expr: &Expr) -> String {
        let core = self.emit_expr_core(expr);
        if expr.append_try_question_mark {
            format!("{}?", core)
        } else {
            core
        }
    }

    fn emit_expr_core(&mut self, expr: &Expr) -> String {
        match &expr.kind {
            ExprKind::Literal(lit) => match lit {
                LiteralValue::Int(v) => v.to_string(),
                LiteralValue::Float(v) => {
                    let s = v.to_string();
                    if s.contains('.') {
                        s
                    } else {
                        format!("{}.0", s)
                    }
                }
                LiteralValue::Decimal(raw) => format_decimal_literal(raw),
                LiteralValue::String(s) => format!("\"{}\"", escape_rust_string(s)),
                LiteralValue::Char(c) => format!("'{}'", c),
                LiteralValue::Bool(b) => b.to_string(),
                LiteralValue::Null => "None".to_string(),
            },

            ExprKind::InterpolatedString(parts) => {
                let mut fmt_str = String::new();
                let mut fmt_args = Vec::new();
                for part in parts {
                    match part {
                        InterpPart::Literal(lit) => {
                            fmt_str.push_str(&escape_rust_string(lit));
                        }
                        InterpPart::ExprSource(src) => {
                            fmt_str.push_str("{}");
                            fmt_args.push(self.translate_interp_expr(src));
                        }
                    }
                }
                if fmt_args.is_empty() {
                    format!("\"{}\".to_string()", fmt_str)
                } else {
                    format!("format!(\"{}\", {})", fmt_str, fmt_args.join(", "))
                }
            }

            ExprKind::Identifier { name, .. } => {
                if self.type_fields.contains_key(name) {
                    format!("self.{}", normalize_field_ident(name))
                } else if self.base_struct_fields.contains(name) {
                    format!("self.base.{}", normalize_field_ident(name))
                } else {
                    normalize_local_ident(name)
                }
            }

            ExprKind::This => "self".to_string(),
            ExprKind::Base => "self.base".to_string(),

            ExprKind::Unary { op, operand } => {
                let inner = self.emit_expr(operand);
                match op {
                    UnaryOp::Not => format!("!{}", inner),
                    UnaryOp::BitNot => format!("!{}", inner),
                    UnaryOp::Neg => format!("-{}", inner),
                    UnaryOp::Await => {
                        if let Some(stripped) = inner.strip_suffix('?') {
                            format!("{}.await?", stripped)
                        } else {
                            format!("{}.await", inner)
                        }
                    }
                    UnaryOp::FromEnd => inner,
                }
            }

            ExprKind::Binary { op, left, right } => {
                let l = self.emit_expr(left);
                let r = self.emit_expr(right);
                let op_str = match op {
                    BinaryOp::Add => "+",
                    BinaryOp::Sub => "-",
                    BinaryOp::Mul => "*",
                    BinaryOp::Div => "/",
                    BinaryOp::Rem => "%",
                    BinaryOp::BitAnd => "&",
                    BinaryOp::BitOr => "|",
                    BinaryOp::BitXor => "^",
                    BinaryOp::Shl => "<<",
                    BinaryOp::Shr => ">>",
                    BinaryOp::Eq => "==",
                    BinaryOp::Neq => "!=",
                    BinaryOp::Lt => "<",
                    BinaryOp::Gt => ">",
                    BinaryOp::Lte => "<=",
                    BinaryOp::Gte => ">=",
                    BinaryOp::And => "&&",
                    BinaryOp::Or => "||",
                };
                format!("{} {} {}", l, op_str, r)
            }

            ExprKind::Assignment { op, target, value } => {
                let lhs = self.emit_expr(target);
                let rhs = self.emit_expr(value);
                match op {
                    AssignOp::Assign => format!("{} = {}", lhs, rhs),
                    AssignOp::AddAssign => format!("{} += {}", lhs, rhs),
                    AssignOp::SubAssign => format!("{} -= {}", lhs, rhs),
                    AssignOp::MulAssign => format!("{} *= {}", lhs, rhs),
                    AssignOp::DivAssign => format!("{} /= {}", lhs, rhs),
                    AssignOp::NullCoalesceEq => format!("{}.get_or_insert({})", lhs, rhs),
                }
            }

            ExprKind::NullCoalesce { left, right } => {
                let l = self.emit_expr(left);
                let r = self.emit_expr(right);
                format!("{}.unwrap_or({})", l, r)
            }

            ExprKind::IsPattern {
                expr: inner,
                pattern,
            } => {
                let scrutinee = self.emit_expr(inner);
                let pat_str = self.emit_pattern(pattern);
                format!("matches!({}, {})", scrutinee, pat_str)
            }

            ExprKind::MemberAccess {
                target,
                member,
                is_null_conditional,
                ..
            } => {
                if let ExprKind::Identifier { name, .. } = &target.kind {
                    if self
                        .symtab
                        .types
                        .values()
                        .any(|t| t.name == *name && t.kind == TypeKind::Enum)
                    {
                        return format!("{}::{}", name, member);
                    }
                }

                if matches!(target.kind, ExprKind::This) {
                    if self.base_struct_fields.contains(member) {
                        return format!("self.base.{}", normalize_field_ident(member));
                    }
                    return format!("self.{}", normalize_field_ident(member));
                }

                let recv_str = self.emit_expr(target);
                if *is_null_conditional {
                    return format!(
                        "{}.as_ref().map(|_x| &_x.{})",
                        recv_str,
                        normalize_field_ident(member)
                    );
                }

                // Built-in property templates on `String`, `List`, `ReadOnlySpan`, `Span`
                match member.as_str() {
                    "Length" | "Count" => format!("{}.len() as i32", recv_str),
                    "IsEmpty" => format!("{}.is_empty()", recv_str),
                    _ => format!("{}.{}", recv_str, normalize_field_ident(member)),
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
                let recv_str = receiver
                    .as_ref()
                    .map(|r| self.emit_expr(r))
                    .unwrap_or_else(|| "self".to_string());

                let rendered_args: Vec<String> = args
                    .iter()
                    .map(|a| {
                        let raw_arg = self.emit_expr(&a.expr);
                        self.apply_caller_coercion(&a.expr, raw_arg, a.expr.caller_coercion)
                    })
                    .collect();

                // 1. Check `primitive_lowering` (`[InlineTemplate]` or `[MapsTo]`)
                match primitive_lowering {
                    PrimitiveLowering::InlineTemplate { template } => {
                        return expand_primitive_inline_template(
                            template,
                            &recv_str,
                            &rendered_args,
                        );
                    }
                    PrimitiveLowering::DirectSymbol { rust_path } => {
                        return format!("{}.{}({})", recv_str, rust_path, rendered_args.join(", "));
                    }
                    PrimitiveLowering::OperatorIndex => {
                        if let Some(first) = rendered_args.first() {
                            return format!("{}[({}) as usize]", recv_str, first);
                        }
                    }
                    PrimitiveLowering::None => {}
                }

                // 2. Resolve disambiguated Rust method name from `GlobalSymbolTable`
                let rust_fn_name = resolved_overload
                    .and_then(|mid| self.symtab.methods.get(&mid))
                    .map(|m| m.disambiguated_rust_name.clone())
                    .filter(|s| !s.is_empty())
                    .unwrap_or_else(|| pascal_to_snake_case(method_name));

                let is_static_call = resolved_overload
                    .and_then(|mid| self.symtab.methods.get(&mid))
                    .map(|m| m.is_static)
                    .unwrap_or(false);

                if let Some(recv) = receiver {
                    if let ExprKind::Identifier { name, .. } = &recv.kind {
                        if is_static_call || self.symtab.short_name_index.contains_key(name) {
                            return format!(
                                "{}::{}({})",
                                name,
                                rust_fn_name,
                                rendered_args.join(", ")
                            );
                        }
                    }
                    format!(
                        "{}.{}({})",
                        recv_str,
                        rust_fn_name,
                        rendered_args.join(", ")
                    )
                } else if is_static_call {
                    format!("Self::{}({})", rust_fn_name, rendered_args.join(", "))
                } else {
                    format!("self.{}({})", rust_fn_name, rendered_args.join(", "))
                }
            }

            ExprKind::IndexAccess { target, indices } => {
                let t = self.emit_expr(target);
                let idx_strs: Vec<String> = indices
                    .iter()
                    .map(|i| format!("({}) as usize", self.emit_expr(&i.expr)))
                    .collect();
                format!("{}[{}]", t, idx_strs.join(", "))
            }

            ExprKind::RangeSlice { target, start, end } => {
                let s = start
                    .as_ref()
                    .map(|e| self.emit_expr(e))
                    .unwrap_or_default();
                let e = end.as_ref().map(|e| self.emit_expr(e)).unwrap_or_default();
                if let Some(t) = target {
                    let t_str = self.emit_expr(t);
                    format!("&{}[{}..{}]", t_str, s, e)
                } else {
                    format!("{}..{}", s, e)
                }
            }

            ExprKind::Construct {
                ty,
                args,
                resolved_ctor,
                primitive_lowering,
            } => self.emit_construct_expr(ty, args, *resolved_ctor, primitive_lowering),

            ExprKind::Lambda { params, body } => {
                let param_list: Vec<String> =
                    params.iter().map(|p| normalize_local_ident(p)).collect();
                let body_str = match body {
                    LambdaBody::Expr(e) => self.emit_expr(e),
                    LambdaBody::Block(b) => {
                        let mut dummy_map = RustSourceMap::default();
                        let mut dummy_line = 1;
                        format!(
                            "{{\n{}\n}}",
                            self.emit_block(b, 1, &mut dummy_map, &mut dummy_line)
                        )
                    }
                };
                format!("|{}| {}", param_list.join(", "), body_str)
            }

            ExprKind::Switch { scrutinee, arms } => {
                let scrut_str = self.emit_expr(scrutinee);
                let mut rendered_arms = Vec::new();
                for arm in arms {
                    let pat = self.emit_pattern(&arm.pattern);
                    let guard = arm
                        .guard
                        .as_ref()
                        .map(|g| format!(" if {}", self.emit_expr(g)))
                        .unwrap_or_default();
                    let body = self.emit_expr(&arm.body);
                    rendered_arms.push(format!("{}{} => {}", pat, guard, body));
                }
                format!("match {} {{ {} }}", scrut_str, rendered_arms.join(", "))
            }

            ExprKind::LinqChain(chain) => self.emit_fused_linq_chain(chain),
        }
    }

    fn emit_construct_expr(
        &mut self,
        ty: &TypeRef,
        args: &[crate::frontend::ast::ArgNode],
        resolved_ctor: Option<SymbolId>,
        primitive_lowering: &PrimitiveLowering,
    ) -> String {
        let rendered_args: Vec<String> = args
            .iter()
            .map(|a| {
                let raw = self.emit_expr(&a.expr);
                if matches!(a.expr.kind, ExprKind::Literal(LiteralValue::String(_))) {
                    format!("{}.to_string()", raw)
                } else {
                    self.apply_caller_coercion(&a.expr, raw, a.expr.caller_coercion)
                }
            })
            .collect();

        if let PrimitiveLowering::InlineTemplate { template } = primitive_lowering {
            return expand_primitive_inline_template(template, "", &rendered_args);
        }

        match ty.short_name() {
            "List" => {
                if rendered_args.is_empty() {
                    return "Vec::new()".to_string();
                }
                return format!("Vec::with_capacity(({}) as usize)", rendered_args[0]);
            }
            "Dictionary" => {
                return "std::collections::HashMap::new()".to_string();
            }
            "HashSet" => {
                return "std::collections::HashSet::new()".to_string();
            }
            _ => {}
        }

        // Check if `ty` is a `Record` with primary constructor parameters -> emit struct literal `Order { id: ..., total: ... }`
        if let Some(candidates) = self.symtab.short_name_index.get(ty.short_name()) {
            for &cid in candidates {
                if let Some(tsym) = self.symtab.types.get(&cid) {
                    if matches!(tsym.kind, crate::frontend::ast::TypeKind::Record { .. })
                        && tsym.constructors.is_empty()
                        && tsym.fields.len() == rendered_args.len()
                    {
                        let mut field_inits = Vec::new();
                        for (i, &fid) in tsym.fields.iter().enumerate() {
                            if let Some(fsym) = self.symtab.fields.get(&fid) {
                                field_inits.push(format!(
                                    "{}: {}",
                                    normalize_field_ident(&fsym.name),
                                    rendered_args[i]
                                ));
                            }
                        }
                        return format!("{} {{ {} }}", ty.short_name(), field_inits.join(", "));
                    }
                }
            }
        }

        let ctor_name = resolved_ctor
            .and_then(|cid| self.symtab.methods.get(&cid))
            .map(|c| c.disambiguated_rust_name.clone())
            .filter(|n| !n.is_empty())
            .unwrap_or_else(|| "new".to_string());

        format!(
            "{}::{}({})",
            ty.short_name(),
            ctor_name,
            rendered_args.join(", ")
        )
    }

    pub fn apply_caller_coercion(
        &self,
        arg_expr: &Expr,
        rendered_expr: String,
        coercion: CallerArgCoercion,
    ) -> String {
        match coercion {
            CallerArgCoercion::None => rendered_expr,
            CallerArgCoercion::BorrowShared => {
                if matches!(
                    arg_expr.kind,
                    ExprKind::Literal(LiteralValue::String(_)) | ExprKind::RangeSlice { .. }
                ) {
                    return rendered_expr;
                }
                if let ExprKind::Identifier { name, .. } = &arg_expr.kind {
                    if let Some(&param_mode) = self.method_param_borrows.get(name) {
                        return match param_mode {
                            BorrowMode::ReadBorrow => rendered_expr,
                            BorrowMode::MutBorrow => format!("&*{}", rendered_expr),
                            _ => format!("&{}", rendered_expr),
                        };
                    }
                }
                format!("&{}", rendered_expr)
            }
            CallerArgCoercion::BorrowMutable => {
                if let ExprKind::Identifier { name, .. } = &arg_expr.kind {
                    if let Some(&param_mode) = self.method_param_borrows.get(name) {
                        if param_mode == BorrowMode::MutBorrow {
                            return rendered_expr;
                        }
                    }
                }
                format!("&mut {}", rendered_expr)
            }
            CallerArgCoercion::CloneOwned => format!("{}.clone()", rendered_expr),
            CallerArgCoercion::ArcClone => format!("Arc::clone(&{})", rendered_expr),
        }
    }

    fn emit_fused_linq_chain(&mut self, chain: &LinqChain) -> String {
        let src_str = self.emit_expr(&chain.source);
        let iter_init = if chain.consumes_source {
            format!("{}.into_iter()", src_str)
        } else {
            format!("{}.iter()", src_str)
        };

        let mut stages = vec![iter_init];
        let mut sort_spec: Option<(String, bool)> = None;

        for op in &chain.ops {
            match op {
                LinqOp::Where { predicate } => {
                    stages.push(format!("filter({})", self.emit_expr(predicate)));
                }
                LinqOp::Select { selector } => {
                    stages.push(format!("map({})", self.emit_expr(selector)));
                }
                LinqOp::SelectMany { selector } => {
                    stages.push(format!("flat_map({})", self.emit_expr(selector)));
                }
                LinqOp::Take { count } => {
                    stages.push(format!("take({} as usize)", self.emit_expr(count)));
                }
                LinqOp::Skip { count } => {
                    stages.push(format!("skip({} as usize)", self.emit_expr(count)));
                }
                LinqOp::WithIndex => {
                    stages.push("enumerate()".to_string());
                }
                LinqOp::Reverse => {
                    stages.push("rev()".to_string());
                }
                LinqOp::Distinct => {
                    stages.push("dedup()".to_string());
                }
                LinqOp::OrderBy {
                    key_selector,
                    descending,
                } => {
                    sort_spec = Some((self.emit_expr(key_selector), *descending));
                }
            }
        }

        let term_str = match &chain.terminal {
            LinqTerminal::ToList => "collect::<Vec<_>>()".to_string(),
            LinqTerminal::ToHashSet => "collect::<std::collections::HashSet<_>>()".to_string(),
            LinqTerminal::Any {
                predicate: Some(pred),
            } => format!("any({})", self.emit_expr(pred)),
            LinqTerminal::Any { predicate: None } => "next().is_some()".to_string(),
            LinqTerminal::All { predicate } => format!("all({})", self.emit_expr(predicate)),
            LinqTerminal::First {
                predicate: Some(pred),
            } => format!("find({}).cloned().unwrap()", self.emit_expr(pred)),
            LinqTerminal::First { predicate: None } => "next().cloned().unwrap()".to_string(),
            LinqTerminal::FirstOrDefault {
                predicate: Some(pred),
            } => format!("find({}).cloned()", self.emit_expr(pred)),
            LinqTerminal::FirstOrDefault { predicate: None } => "next().cloned()".to_string(),
            LinqTerminal::Last {
                predicate: Some(pred),
            } => format!("filter({}).last().cloned().unwrap()", self.emit_expr(pred)),
            LinqTerminal::Last { predicate: None } => "last().cloned().unwrap()".to_string(),
            LinqTerminal::LastOrDefault {
                predicate: Some(pred),
            } => format!("filter({}).last().cloned()", self.emit_expr(pred)),
            LinqTerminal::LastOrDefault { predicate: None } => "last().cloned()".to_string(),
            LinqTerminal::Count => "count() as i32".to_string(),
            LinqTerminal::Sum => "sum()".to_string(),
            LinqTerminal::Aggregate {
                seed: Some(seed),
                func,
            } => format!("fold({}, {})", self.emit_expr(seed), self.emit_expr(func)),
            LinqTerminal::Aggregate { seed: None, func } => {
                format!("reduce({}).unwrap()", self.emit_expr(func))
            }
        };

        if let Some((key_sel, desc)) = sort_spec {
            if matches!(chain.terminal, LinqTerminal::ToList) {
                if desc {
                    format!(
                        "{{ let mut _v = {}.collect::<Vec<_>>(); _v.sort_by_key({}); _v.reverse(); _v }}",
                        stages.join("."),
                        key_sel
                    )
                } else {
                    format!(
                        "{{ let mut _v = {}.collect::<Vec<_>>(); _v.sort_by_key({}); _v }}",
                        stages.join("."),
                        key_sel
                    )
                }
            } else {
                let sorted_iter = if desc {
                    format!(
                        "{{ let mut _v = {}.collect::<Vec<_>>(); _v.sort_by_key({}); _v.reverse(); _v }}.into_iter()",
                        stages.join("."),
                        key_sel
                    )
                } else {
                    format!(
                        "{{ let mut _v = {}.collect::<Vec<_>>(); _v.sort_by_key({}); _v }}.into_iter()",
                        stages.join("."),
                        key_sel
                    )
                };
                format!("{}.{}", sorted_iter, term_str)
            }
        } else {
            stages.push(term_str);
            stages.join(".")
        }
    }

    fn emit_pattern(&mut self, pattern: &Pattern) -> String {
        match pattern {
            Pattern::Wildcard(_) => "_".to_string(),
            Pattern::Null(_) => "None".to_string(),
            Pattern::Literal(_, lit) => match lit {
                LiteralValue::Int(v) => v.to_string(),
                LiteralValue::String(s) => format!("\"{}\"", escape_rust_string(s)),
                LiteralValue::Bool(b) => b.to_string(),
                _ => "_".to_string(),
            },
            Pattern::TypePattern {
                ty,
                bind_name,
                property_patterns,
                ..
            } => {
                let type_name = ty.short_name();
                if !property_patterns.is_empty() {
                    let fields: Vec<String> = property_patterns
                        .iter()
                        .map(|pp| {
                            format!(
                                "{}: {}",
                                normalize_field_ident(&pp.field_name),
                                self.emit_pattern(&pp.pattern)
                            )
                        })
                        .collect();
                    format!("{} {{ {}, .. }}", type_name, fields.join(", "))
                } else if let Some(b) = bind_name {
                    format!("{}({})", type_name, normalize_local_ident(b))
                } else {
                    type_name.to_string()
                }
            }
        }
    }

    fn translate_interp_expr(&self, raw: &str) -> String {
        let trimmed = raw.trim();
        if self.type_fields.contains_key(trimmed) {
            format!("self.{}", normalize_field_ident(trimmed))
        } else if self.base_struct_fields.contains(trimmed) {
            format!("self.base.{}", normalize_field_ident(trimmed))
        } else if let Some((obj, prop)) = trimmed.split_once('.') {
            format!(
                "{}.{}",
                normalize_local_ident(obj.trim()),
                normalize_field_ident(prop.trim())
            )
        } else {
            normalize_local_ident(trimmed)
        }
    }
}

pub fn expand_primitive_inline_template(tpl: &str, receiver: &str, args: &[String]) -> String {
    let mut out = tpl.replace("{self}", receiver);
    for (i, arg) in args.iter().enumerate() {
        let placeholder = format!("{{{}}}", i);
        let addr_placeholder = format!("&{{{}}}", i);
        if out.contains(&addr_placeholder) && arg.starts_with('&') {
            out = out.replace(&addr_placeholder, arg);
        } else {
            out = out.replace(&placeholder, arg);
        }
    }
    out
}

/// Converts a C# decimal literal string (e.g. `"10.0"`, `"100.25"`) into `Decimal::new(mantissa, scale)`.
pub fn format_decimal_literal(raw: &str) -> String {
    if let Some((int_part, frac_part)) = raw.split_once('.') {
        let scale = frac_part.len() as u32;
        let combined = format!("{}{}", int_part, frac_part);
        let mantissa = combined.parse::<i64>().unwrap_or(0);
        format!("Decimal::new({}, {})", mantissa, scale)
    } else {
        let mantissa = raw.parse::<i64>().unwrap_or(0);
        format!("Decimal::new({}, 0)", mantissa)
    }
}

pub fn normalize_field_ident(name: &str) -> String {
    let stripped = name.trim_start_matches('_');
    if stripped.is_empty() {
        "_field".to_string()
    } else {
        pascal_to_snake_case(stripped)
    }
}

pub fn normalize_local_ident(name: &str) -> String {
    if name.starts_with('_') {
        let stripped = name.trim_start_matches('_');
        format!("_{}", pascal_to_snake_case(stripped))
    } else {
        pascal_to_snake_case(name)
    }
}

fn escape_rust_string(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}
