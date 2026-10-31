use crate::diagnostics::{DiagnosticEngine, SourceSpan};
use crate::frontend::ast::*;
use crate::frontend::tokens::{Token, TokenKind};

/// Recursive-Descent Declaration Parser & Pratt Expression Parser for `.rsharp` and `.d.rsharp`.
pub struct Parser<'a> {
    tokens: Vec<Token>,
    pos: usize,
    file_id: usize,
    filename: String,
    diag: &'a mut DiagnosticEngine,
}

impl<'a> Parser<'a> {
    pub fn new(
        tokens: Vec<Token>,
        file_id: usize,
        filename: impl Into<String>,
        diag: &'a mut DiagnosticEngine,
    ) -> Self {
        Self {
            tokens,
            pos: 0,
            file_id,
            filename: filename.into(),
            diag,
        }
    }

    pub fn parse_compilation_unit(&mut self) -> CompilationUnit {
        let is_ambient_stub = self.filename.ends_with(".d.rsharp");
        let mut attributes = Vec::new();
        let mut namespace = Vec::new();
        let mut imports = Vec::new();
        let mut types = Vec::new();

        // Top-level assembly/module attributes: `[assembly: ...]`
        while self.check(&TokenKind::LBracket) {
            let attrs = self.parse_attributes();
            attributes.extend(attrs);
        }

        // Optional `namespace Foo.Bar;` or `namespace Foo.Bar { ... }`
        if self.check(&TokenKind::Namespace) {
            self.advance();
            namespace = self.parse_qualified_ident();
            if self.match_kind(&TokenKind::LBrace) {
                // Block-scoped namespace
            } else {
                self.expect(
                    &TokenKind::Semicolon,
                    "Expected ';' after namespace declaration.",
                );
            }
        }

        // `using ...;` and `extern using ...;`
        while self.check(&TokenKind::Using)
            || (self.check(&TokenKind::Extern) && self.peek_kind(1) == &TokenKind::Using)
        {
            imports.push(self.parse_import_decl());
        }

        // Top-level type declarations
        while !self.is_at_end() {
            if self.check(&TokenKind::Semicolon) || self.check(&TokenKind::RBrace) {
                self.advance();
                continue;
            }
            let start_pos = self.pos;
            if let Some(ty_decl) = self.parse_type_decl() {
                types.push(ty_decl);
            }
            if self.pos == start_pos && !self.is_at_end() {
                self.advance();
            }
        }

        CompilationUnit {
            file_id: self.file_id,
            filename: self.filename.clone(),
            is_ambient_stub,
            attributes,
            namespace,
            imports,
            types,
        }
    }

    fn parse_import_decl(&mut self) -> ImportDecl {
        let start_span = self.current_span();
        let is_extern_crate = if self.match_kind(&TokenKind::Extern) {
            self.expect(&TokenKind::Using, "Expected 'using' after 'extern'.");
            true
        } else {
            self.expect(&TokenKind::Using, "Expected 'using'.");
            false
        };

        let mut path = Vec::new();
        path.push(self.expect_ident("Expected identifier in import path."));
        while self.match_kind(&TokenKind::Dot) || self.match_kind(&TokenKind::ColonColon) {
            path.push(self.expect_ident("Expected identifier segment in import path."));
        }

        let alias = if self.match_kind(&TokenKind::As) {
            Some(self.expect_ident("Expected alias identifier after 'as'."))
        } else {
            None
        };

        let end_span = self.expect(&TokenKind::Semicolon, "Expected ';' after using directive.");
        ImportDecl {
            span: start_span.merge(&end_span),
            is_extern_crate,
            path,
            alias,
        }
    }

    fn parse_attributes(&mut self) -> Vec<AttributeNode> {
        let mut attrs = Vec::new();
        while self.match_kind(&TokenKind::LBracket) {
            loop {
                if self.check(&TokenKind::RBracket) || self.is_at_end() {
                    break;
                }
                let attr_start = self.current_span();

                // Skip attribute target specifiers: `assembly:`, `module:`, etc.
                if self.is_ident_at(0)
                    && self.peek_kind(1) == &TokenKind::Colon
                    && self.peek_kind(2) != &TokenKind::Colon
                {
                    self.advance(); // target identifier (e.g. 'assembly')
                    self.advance(); // ':'
                }

                let path = self.parse_qualified_ident();
                let mut args = Vec::new();

                if self.match_kind(&TokenKind::LParen) {
                    while !self.check(&TokenKind::RParen) && !self.is_at_end() {
                        let name = if self.is_ident_at(0) && self.peek_kind(1) == &TokenKind::Assign
                        {
                            let n = self.expect_ident("Expected attribute argument name.");
                            self.advance(); // '='
                            Some(n)
                        } else {
                            None
                        };
                        let value = self.parse_expr();
                        args.push(AttributeArg { name, value });
                        if !self.match_kind(&TokenKind::Comma) {
                            break;
                        }
                    }
                    self.expect(
                        &TokenKind::RParen,
                        "Expected ')' after attribute arguments.",
                    );
                }

                attrs.push(AttributeNode {
                    span: attr_start.merge(&self.previous_span()),
                    path,
                    args,
                });

                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect(
                &TokenKind::RBracket,
                "Expected ']' after attribute section.",
            );
        }
        attrs
    }

    fn parse_type_decl(&mut self) -> Option<TypeDecl> {
        let attributes = self.parse_attributes();
        let start_span = self.current_span();

        let mut access = AccessMod::Internal;
        let mut is_abstract = false;
        let mut is_sealed = false;
        let mut is_partial = false;
        let mut is_static = false;
        let mut is_service = false;
        let mut is_shared = false;
        let mut is_primitive = false;
        let mut is_extensible = false;

        loop {
            match self.peek_kind(0) {
                TokenKind::Public => {
                    self.advance();
                    access = AccessMod::Public;
                }
                TokenKind::Internal => {
                    self.advance();
                    access = AccessMod::Internal;
                }
                TokenKind::Protected => {
                    self.advance();
                    access = AccessMod::Protected;
                }
                TokenKind::Private => {
                    self.advance();
                    access = AccessMod::Private;
                }
                TokenKind::Abstract => {
                    self.advance();
                    is_abstract = true;
                }
                TokenKind::Sealed => {
                    self.advance();
                    is_sealed = true;
                }
                TokenKind::Partial => {
                    self.advance();
                    is_partial = true;
                }
                TokenKind::Static => {
                    self.advance();
                    is_static = true;
                }
                TokenKind::Service => {
                    self.advance();
                    is_service = true;
                }
                TokenKind::Shared => {
                    self.advance();
                    is_shared = true;
                }
                TokenKind::Primitive => {
                    self.advance();
                    is_primitive = true;
                }
                TokenKind::Extensible => {
                    self.advance();
                    is_extensible = true;
                }
                TokenKind::Extern => {
                    self.advance();
                }
                _ => break,
            }
        }

        let kind = if self.match_kind(&TokenKind::Record) {
            let is_struct = self.match_kind(&TokenKind::Struct);
            let _ = self.match_kind(&TokenKind::Class);
            TypeKind::Record { is_struct }
        } else if self.match_kind(&TokenKind::Class) {
            if is_service {
                TypeKind::ServiceClass
            } else if is_shared {
                TypeKind::SharedClass
            } else if is_primitive {
                TypeKind::PrimitiveClass { is_struct: false }
            } else {
                TypeKind::StandardClass
            }
        } else if self.match_kind(&TokenKind::Struct) {
            if is_primitive {
                TypeKind::PrimitiveClass { is_struct: true }
            } else {
                TypeKind::ValueStruct
            }
        } else if self.match_kind(&TokenKind::Interface) {
            TypeKind::Interface {
                is_extensible: is_extensible || is_primitive,
            }
        } else if self.match_kind(&TokenKind::Enum) {
            TypeKind::Enum
        } else {
            let span = self.current_span();
            self.diag.report_syntax_error(
                span,
                format!(
                    "Expected type declaration keyword, found '{}'.",
                    self.peek(0).lexeme
                ),
            );
            return None;
        };

        let name = self.expect_ident("Expected type name.");
        let type_params = self.parse_optional_type_params();

        // Primary constructor parameters on `record Name(int Id, decimal Total)`
        let primary_ctor_params =
            if matches!(kind, TypeKind::Record { .. }) && self.check(&TokenKind::LParen) {
                self.parse_param_list()
            } else {
                Vec::new()
            };

        // Base types / interfaces (`: BaseType, IInterface`)
        let mut base_types = Vec::new();
        if self.match_kind(&TokenKind::Colon) {
            loop {
                base_types.push(self.parse_type_ref());
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
        }

        let constraints = self.parse_where_constraints();

        let mut members = Vec::new();
        let mut enum_variants = Vec::new();

        if self.match_kind(&TokenKind::Semicolon) {
            // Semicolon-terminated record declaration (`public record Order(int Id, decimal Total);`)
        } else if self.match_kind(&TokenKind::LBrace) {
            if kind == TypeKind::Enum {
                while !self.check(&TokenKind::RBrace) && !self.is_at_end() {
                    let v_attrs = self.parse_attributes();
                    let v_start = self.current_span();
                    let v_name = self.expect_ident("Expected enum variant name.");
                    let payload = if self.check(&TokenKind::LParen) {
                        self.parse_param_list()
                    } else {
                        Vec::new()
                    };
                    let discriminant = if self.match_kind(&TokenKind::Assign) {
                        Some(self.parse_expr())
                    } else {
                        None
                    };
                    enum_variants.push(EnumVariantDecl {
                        span: v_start.merge(&self.previous_span()),
                        attributes: v_attrs,
                        name: v_name,
                        payload,
                        discriminant,
                    });
                    if !self.match_kind(&TokenKind::Comma) {
                        break;
                    }
                }
            } else {
                let is_interface = matches!(kind, TypeKind::Interface { .. });
                while !self.check(&TokenKind::RBrace) && !self.is_at_end() {
                    if self.match_kind(&TokenKind::Semicolon) {
                        continue;
                    }
                    let member_pos = self.pos;
                    if let Some(member) = self.parse_member_decl(&name, is_interface) {
                        members.push(member);
                    }
                    if self.pos == member_pos
                        && !self.check(&TokenKind::RBrace)
                        && !self.is_at_end()
                    {
                        self.advance();
                    }
                }
            }
            self.expect(&TokenKind::RBrace, "Expected '}' after type body.");
        }

        let primitive_rust_target = extract_attr_string(&attributes, "MapsTo");
        let primitive_param_type = extract_attr_string(&attributes, "ParamType");
        let has_disposable_drop = base_types.iter().any(|b| b.short_name() == "IDisposable");

        Some(TypeDecl {
            id: SymbolId(0),
            span: start_span.merge(&self.previous_span()),
            attributes,
            access,
            kind,
            is_abstract,
            is_sealed,
            is_partial,
            is_static,
            name,
            type_params,
            primary_ctor_params,
            base_types,
            constraints,
            members,
            enum_variants,
            inferred_polymorphism: PolymorphismStrategy::Unresolved,
            primitive_rust_target,
            primitive_param_type,
            has_disposable_drop,
        })
    }

    fn parse_member_decl(
        &mut self,
        enclosing_type_name: &str,
        is_interface: bool,
    ) -> Option<MemberDecl> {
        let attributes = self.parse_attributes();
        let start_span = self.current_span();

        let mut access = if is_interface {
            AccessMod::Public
        } else {
            AccessMod::Private
        };
        let mut is_readonly = false;
        let mut is_static = false;
        let mut is_virtual = false;
        let mut is_override = false;
        let mut is_abstract = is_interface;
        let mut is_extern = false;
        let mut is_async = false;

        loop {
            match self.peek_kind(0) {
                TokenKind::Public => {
                    self.advance();
                    access = AccessMod::Public;
                }
                TokenKind::Internal => {
                    self.advance();
                    access = AccessMod::Internal;
                }
                TokenKind::Protected => {
                    self.advance();
                    access = AccessMod::Protected;
                }
                TokenKind::Private => {
                    self.advance();
                    access = AccessMod::Private;
                }
                TokenKind::Readonly => {
                    self.advance();
                    is_readonly = true;
                }
                TokenKind::Static => {
                    self.advance();
                    is_static = true;
                }
                TokenKind::Virtual => {
                    self.advance();
                    is_virtual = true;
                }
                TokenKind::Override => {
                    self.advance();
                    is_override = true;
                }
                TokenKind::Abstract => {
                    self.advance();
                    is_abstract = true;
                }
                TokenKind::Extern => {
                    self.advance();
                    is_extern = true;
                }
                TokenKind::Async => {
                    self.advance();
                    is_async = true;
                }
                _ => break,
            }
        }

        // Constructor: `EnclosingTypeName(...)`
        if self.peek_ident(0) == Some(enclosing_type_name)
            && self.peek_kind(1) == &TokenKind::LParen
        {
            let ctor_name = self.expect_ident("Expected constructor name.");
            let params = self.parse_param_list();

            let base_args = if self.match_kind(&TokenKind::Colon) {
                self.expect(
                    &TokenKind::Base,
                    "Expected 'base' in constructor initializer.",
                );
                self.expect(&TokenKind::LParen, "Expected '(' after 'base'.");
                let args = self.parse_arg_list();
                self.expect(&TokenKind::RParen, "Expected ')' after base arguments.");
                Some(args)
            } else {
                None
            };

            let body = self.parse_method_or_ctor_body(None);
            let primitive_lowering = extract_primitive_lowering(&attributes);

            return Some(MemberDecl::Constructor(ConstructorDecl {
                id: SymbolId(0),
                span: start_span.merge(&self.previous_span()),
                attributes,
                access,
                is_extern,
                name: ctor_name,
                params,
                base_args,
                body,
                disambiguated_rust_name: String::new(),
                primitive_lowering,
            }));
        }

        // Member starts with `TypeRef`
        let member_type = self.parse_type_ref();

        // Indexer: `T this[...]`
        if self.match_kind(&TokenKind::This) {
            self.expect(&TokenKind::LBracket, "Expected '[' in indexer declaration.");
            let mut params = Vec::new();
            while !self.check(&TokenKind::RBracket) && !self.is_at_end() {
                params.push(self.parse_param());
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect(
                &TokenKind::RBracket,
                "Expected ']' after indexer parameters.",
            );
            let accessors = self.parse_property_accessors();
            let primitive_lowering = extract_primitive_lowering(&attributes);

            return Some(MemberDecl::Indexer(IndexerDecl {
                id: SymbolId(0),
                span: start_span.merge(&self.previous_span()),
                attributes,
                access,
                is_extern,
                ty: member_type,
                params,
                accessors,
                primitive_lowering,
            }));
        }

        let member_name = self.expect_ident("Expected member name.");

        // Method: `T Name<...>(...)`
        if self.check(&TokenKind::LParen) || self.check(&TokenKind::Lt) {
            let type_params = self.parse_optional_type_params();
            let params = self.parse_param_list();

            let explicit_throws = if self.match_kind(&TokenKind::Throws) {
                Some(self.parse_type_ref())
            } else {
                None
            };

            let constraints = self.parse_where_constraints();
            let body = self.parse_method_or_ctor_body(Some(&member_type));

            let inferred_self_borrow =
                extract_explicit_borrow(&attributes).unwrap_or(BorrowMode::Unresolved);
            let inferred_effect = match &explicit_throws {
                Some(err_ty) => EffectSignature::Fallible {
                    error_type: err_ty.clone(),
                },
                None => EffectSignature::Infallible,
            };
            let primitive_lowering = extract_primitive_lowering(&attributes);
            let linq_stage = extract_attr_string(&attributes, "LinqStage");

            return Some(MemberDecl::Method(MethodDecl {
                id: SymbolId(0),
                span: start_span.merge(&self.previous_span()),
                attributes,
                access,
                is_static,
                is_async,
                is_extern,
                is_virtual,
                is_override,
                is_abstract,
                name: member_name,
                type_params,
                params,
                return_type: member_type,
                explicit_throws,
                constraints,
                body,
                inferred_self_borrow,
                inferred_effect,
                disambiguated_rust_name: String::new(),
                primitive_lowering,
                linq_stage,
            }));
        }

        // Property: `T Name { get; set; }` or `T Name => expr;`
        if self.check(&TokenKind::LBrace) || self.check(&TokenKind::FatArrow) {
            let mut accessors = Vec::new();
            let mut initializer = None;

            if self.match_kind(&TokenKind::FatArrow) {
                let expr = self.parse_expr();
                let end_span = self.expect(
                    &TokenKind::Semicolon,
                    "Expected ';' after expression property.",
                );
                let block_span = expr.span.merge(&end_span);
                accessors.push(AccessorDecl {
                    span: block_span.clone(),
                    attributes: Vec::new(),
                    access: None,
                    is_get: true,
                    body: Some(Block {
                        span: block_span.clone(),
                        stmts: vec![Stmt::Return {
                            span: block_span,
                            value: Some(expr),
                        }],
                    }),
                    inline_template: None,
                    explicit_borrow: Some(BorrowMode::ReadBorrow),
                });
            } else {
                accessors = self.parse_property_accessors();
                if self.match_kind(&TokenKind::Assign) {
                    initializer = Some(self.parse_expr());
                    self.expect(
                        &TokenKind::Semicolon,
                        "Expected ';' after property initializer.",
                    );
                }
            }

            let primitive_lowering = extract_primitive_lowering(&attributes);
            return Some(MemberDecl::Property(PropertyDecl {
                id: SymbolId(0),
                span: start_span.merge(&self.previous_span()),
                attributes,
                access,
                is_static,
                is_extern,
                name: member_name,
                ty: member_type,
                accessors,
                initializer,
                resolved_storage: FieldStorageMode::Plain,
                primitive_lowering,
            }));
        }

        // Field: `T Name (= Expr)?;`
        let initializer = if self.match_kind(&TokenKind::Assign) {
            Some(self.parse_expr())
        } else {
            None
        };
        self.expect(
            &TokenKind::Semicolon,
            "Expected ';' after field declaration.",
        );

        Some(MemberDecl::Field(FieldDecl {
            id: SymbolId(0),
            span: start_span.merge(&self.previous_span()),
            attributes,
            access,
            is_readonly,
            is_static,
            name: member_name,
            ty: member_type,
            initializer,
            resolved_storage: FieldStorageMode::Plain,
        }))
    }

    fn parse_property_accessors(&mut self) -> Vec<AccessorDecl> {
        let mut accessors = Vec::new();
        self.expect(&TokenKind::LBrace, "Expected '{' for property accessors.");

        while !self.check(&TokenKind::RBrace) && !self.is_at_end() {
            let acc_attrs = self.parse_attributes();
            let acc_start = self.current_span();

            let acc_access = match self.peek_kind(0) {
                TokenKind::Public => {
                    self.advance();
                    Some(AccessMod::Public)
                }
                TokenKind::Internal => {
                    self.advance();
                    Some(AccessMod::Internal)
                }
                TokenKind::Protected => {
                    self.advance();
                    Some(AccessMod::Protected)
                }
                TokenKind::Private => {
                    self.advance();
                    Some(AccessMod::Private)
                }
                _ => None,
            };

            let is_get = if self.match_kind(&TokenKind::Get) {
                true
            } else if self.match_kind(&TokenKind::Set) {
                false
            } else {
                let _ = self.expect_ident("Expected 'get' or 'set' in property accessor.");
                true
            };

            let body = if self.match_kind(&TokenKind::Semicolon) {
                None
            } else if self.match_kind(&TokenKind::FatArrow) {
                let expr = self.parse_expr();
                let end = self.expect(&TokenKind::Semicolon, "Expected ';' after accessor '=>'.");
                let sp = expr.span.merge(&end);
                Some(Block {
                    span: sp.clone(),
                    stmts: vec![if is_get {
                        Stmt::Return {
                            span: sp,
                            value: Some(expr),
                        }
                    } else {
                        Stmt::ExprStmt { span: sp, expr }
                    }],
                })
            } else if self.check(&TokenKind::LBrace) {
                Some(self.parse_block())
            } else {
                None
            };

            let inline_template = extract_attr_string(&acc_attrs, "InlineTemplate");
            let explicit_borrow = extract_explicit_borrow(&acc_attrs);

            accessors.push(AccessorDecl {
                span: acc_start.merge(&self.previous_span()),
                attributes: acc_attrs,
                access: acc_access,
                is_get,
                body,
                inline_template,
                explicit_borrow,
            });
        }

        self.expect(&TokenKind::RBrace, "Expected '}' after property accessors.");
        accessors
    }

    fn parse_method_or_ctor_body(&mut self, return_type: Option<&TypeRef>) -> Option<Block> {
        if self.match_kind(&TokenKind::Semicolon) {
            return None;
        }
        if self.match_kind(&TokenKind::FatArrow) {
            let expr = self.parse_expr();
            let end_span = self.expect(
                &TokenKind::Semicolon,
                "Expected ';' after expression-bodied member.",
            );
            let block_span = expr.span.merge(&end_span);
            let is_void_or_ctor = return_type
                .map(|rt| rt.short_name() == "void")
                .unwrap_or(true);
            let is_assign = matches!(expr.kind, ExprKind::Assignment { .. });

            let stmt = if is_void_or_ctor || is_assign {
                Stmt::ExprStmt {
                    span: block_span.clone(),
                    expr,
                }
            } else {
                Stmt::Return {
                    span: block_span.clone(),
                    value: Some(expr),
                }
            };

            return Some(Block {
                span: block_span,
                stmts: vec![stmt],
            });
        }
        if self.check(&TokenKind::LBrace) {
            return Some(self.parse_block());
        }
        None
    }

    fn parse_optional_type_params(&mut self) -> Vec<String> {
        let mut params = Vec::new();
        if self.match_kind(&TokenKind::Lt) {
            while !self.check_gt_or_shr() && !self.is_at_end() {
                params.push(self.expect_ident("Expected generic type parameter name."));
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect_gt_or_split_shr("Expected '>' after generic type parameters.");
        }
        params
    }

    fn parse_where_constraints(&mut self) -> Vec<TypeConstraint> {
        let mut constraints = Vec::new();
        while self.match_kind(&TokenKind::Where) {
            let type_param = self.expect_ident("Expected type parameter after 'where'.");
            self.expect(&TokenKind::Colon, "Expected ':' in 'where' constraint.");
            let mut bounds = Vec::new();
            loop {
                bounds.push(self.parse_type_ref());
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            constraints.push(TypeConstraint { type_param, bounds });
        }
        constraints
    }

    fn parse_param_list(&mut self) -> Vec<ParamDecl> {
        let mut params = Vec::new();
        self.expect(&TokenKind::LParen, "Expected '(' for parameter list.");
        while !self.check(&TokenKind::RParen) && !self.is_at_end() {
            params.push(self.parse_param());
            if !self.match_kind(&TokenKind::Comma) {
                break;
            }
        }
        self.expect(&TokenKind::RParen, "Expected ')' after parameter list.");
        params
    }

    fn parse_param(&mut self) -> ParamDecl {
        let attributes = self.parse_attributes();
        let start_span = self.current_span();
        let is_params = self.match_kind(&TokenKind::Params);
        let ty = self.parse_type_ref();
        let name = self.expect_ident("Expected parameter name.");
        let default_value = if self.match_kind(&TokenKind::Assign) {
            Some(self.parse_expr())
        } else {
            None
        };

        let explicit_constraint = extract_explicit_borrow(&attributes);
        let inferred_borrow = explicit_constraint.unwrap_or(BorrowMode::Unresolved);

        ParamDecl {
            id: SymbolId(0),
            span: start_span.merge(&self.previous_span()),
            attributes,
            is_params,
            ty,
            name,
            default_value,
            explicit_constraint,
            inferred_borrow,
        }
    }

    pub fn parse_type_ref(&mut self) -> TypeRef {
        let start_span = self.current_span();
        let mut path = Vec::new();
        let mut is_primitive_keyword = false;

        if let Some(prim) = self.peek_kind(0).is_primitive_type_keyword() {
            self.advance();
            path.push(prim.to_string());
            is_primitive_keyword = true;
        } else {
            path.push(self.expect_ident("Expected type name."));
            while self.match_kind(&TokenKind::Dot) || self.match_kind(&TokenKind::ColonColon) {
                path.push(self.expect_ident("Expected qualified type segment."));
            }
        }

        let mut type_args = Vec::new();
        if self.match_kind(&TokenKind::Lt) {
            while !self.check_gt_or_shr() && !self.is_at_end() {
                type_args.push(self.parse_type_ref());
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect_gt_or_split_shr("Expected '>' after generic type arguments.");
        }

        let is_nullable = self.match_kind(&TokenKind::Question);

        TypeRef {
            span: start_span.merge(&self.previous_span()),
            path,
            type_args,
            is_nullable,
            is_primitive_keyword,
        }
    }

    // ========================================================================
    // STATEMENT PARSER
    // ========================================================================

    pub fn parse_block(&mut self) -> Block {
        let start_span = self.expect(&TokenKind::LBrace, "Expected '{' to begin block.");
        let mut stmts = Vec::new();
        while !self.check(&TokenKind::RBrace) && !self.is_at_end() {
            if self.match_kind(&TokenKind::Semicolon) {
                continue;
            }
            stmts.push(self.parse_stmt());
        }
        let end_span = self.expect(&TokenKind::RBrace, "Expected '}' to close block.");
        Block {
            span: start_span.merge(&end_span),
            stmts,
        }
    }

    pub fn parse_stmt(&mut self) -> Stmt {
        let start_span = self.current_span();

        if self.check(&TokenKind::LBrace) {
            return Stmt::Block(self.parse_block());
        }

        if self.match_kind(&TokenKind::Using) {
            let explicit_type = if self.match_kind(&TokenKind::Var) {
                None
            } else {
                Some(self.parse_type_ref())
            };
            let name = self.expect_ident("Expected variable name in 'using' statement.");
            self.expect(
                &TokenKind::Assign,
                "Expected '=' in 'using' resource statement.",
            );
            let init = self.parse_expr();
            let end = self.expect(
                &TokenKind::Semicolon,
                "Expected ';' after 'using' statement.",
            );
            return Stmt::UsingResource {
                span: start_span.merge(&end),
                symbol_id: SymbolId(0),
                name,
                explicit_type,
                init,
                inferred_mut: false,
            };
        }

        if self.match_kind(&TokenKind::Var) {
            let name = self.expect_ident("Expected local variable name after 'var'.");
            self.expect(&TokenKind::Assign, "Expected '=' after variable name.");
            let init = self.parse_expr();
            let end = self.expect(
                &TokenKind::Semicolon,
                "Expected ';' after local variable declaration.",
            );
            return Stmt::LocalVar {
                span: start_span.merge(&end),
                symbol_id: SymbolId(0),
                name,
                explicit_type: None,
                init,
                inferred_mut: false,
                inferred_type: None,
            };
        }

        if self.match_kind(&TokenKind::If) {
            self.expect(&TokenKind::LParen, "Expected '(' after 'if'.");
            let cond = self.parse_expr();
            self.expect(&TokenKind::RParen, "Expected ')' after 'if' condition.");
            let then_branch = Box::new(self.parse_stmt());
            let else_branch = if self.match_kind(&TokenKind::Else) {
                Some(Box::new(self.parse_stmt()))
            } else {
                None
            };
            return Stmt::If {
                span: start_span.merge(&self.previous_span()),
                cond,
                then_branch,
                else_branch,
            };
        }

        if self.match_kind(&TokenKind::While) {
            self.expect(&TokenKind::LParen, "Expected '(' after 'while'.");
            let cond = self.parse_expr();
            self.expect(&TokenKind::RParen, "Expected ')' after 'while' condition.");
            let body = Box::new(self.parse_stmt());
            return Stmt::While {
                span: start_span.merge(&self.previous_span()),
                cond,
                body,
            };
        }

        if self.match_kind(&TokenKind::ForEach) {
            self.expect(&TokenKind::LParen, "Expected '(' after 'foreach'.");
            let item_type = if self.match_kind(&TokenKind::Var) {
                None
            } else {
                Some(self.parse_type_ref())
            };
            let item_name = self.expect_ident("Expected loop variable name in 'foreach'.");
            self.expect(&TokenKind::In, "Expected 'in' inside 'foreach'.");
            let collection = self.parse_expr();
            self.expect(&TokenKind::RParen, "Expected ')' after 'foreach' header.");
            let body = Box::new(self.parse_stmt());
            return Stmt::ForEach {
                span: start_span.merge(&self.previous_span()),
                item_symbol: SymbolId(0),
                item_type,
                item_name,
                collection,
                body,
                iter_borrow_mode: BorrowMode::Unresolved,
            };
        }

        if self.match_kind(&TokenKind::Return) {
            let value = if self.check(&TokenKind::Semicolon) {
                None
            } else {
                Some(self.parse_expr())
            };
            let end = self.expect(&TokenKind::Semicolon, "Expected ';' after 'return'.");
            return Stmt::Return {
                span: start_span.merge(&end),
                value,
            };
        }

        if self.match_kind(&TokenKind::Throw) {
            let error_expr = self.parse_expr();
            let end = self.expect(&TokenKind::Semicolon, "Expected ';' after 'throw'.");
            return Stmt::Throw {
                span: start_span.merge(&end),
                error_expr,
            };
        }

        if self.match_kind(&TokenKind::Try) {
            let try_block = self.parse_block();
            let mut catches = Vec::new();
            while self.match_kind(&TokenKind::Catch) {
                let c_start = self.previous_span();
                self.expect(&TokenKind::LParen, "Expected '(' after 'catch'.");
                let error_type = self.parse_type_ref();
                let var_name = if !self.check(&TokenKind::RParen) {
                    Some(self.expect_ident("Expected exception variable name in 'catch'."))
                } else {
                    None
                };
                self.expect(&TokenKind::RParen, "Expected ')' after 'catch' clause.");
                let body = self.parse_block();
                catches.push(CatchArm {
                    span: c_start.merge(&body.span),
                    error_type,
                    var_name,
                    body,
                });
            }
            return Stmt::TryCatch {
                span: start_span.merge(&self.previous_span()),
                try_block,
                catches,
            };
        }

        // Speculative check for explicit typed local variable: `TypeRef ident = expr;`
        if self.looks_like_typed_local_var() {
            let ty = self.parse_type_ref();
            let name = self.expect_ident("Expected local variable name.");
            self.expect(
                &TokenKind::Assign,
                "Expected '=' in local variable declaration.",
            );
            let init = self.parse_expr();
            let end = self.expect(&TokenKind::Semicolon, "Expected ';' after local variable.");
            return Stmt::LocalVar {
                span: start_span.merge(&end),
                symbol_id: SymbolId(0),
                name,
                explicit_type: Some(ty),
                init,
                inferred_mut: false,
                inferred_type: None,
            };
        }

        let expr = self.parse_expr();
        let end = self.expect(
            &TokenKind::Semicolon,
            "Expected ';' after expression statement.",
        );
        Stmt::ExprStmt {
            span: start_span.merge(&end),
            expr,
        }
    }

    fn looks_like_typed_local_var(&self) -> bool {
        let saved = self.pos;
        let mut cursor = saved;

        if self
            .peek_kind_at(cursor)
            .is_primitive_type_keyword()
            .is_some()
        {
            cursor += 1;
        } else if matches!(self.peek_kind_at(cursor), TokenKind::Ident(_)) {
            cursor += 1;
            while matches!(
                self.peek_kind_at(cursor),
                TokenKind::Dot | TokenKind::ColonColon
            ) {
                cursor += 1;
                if matches!(self.peek_kind_at(cursor), TokenKind::Ident(_)) {
                    cursor += 1;
                } else {
                    return false;
                }
            }
        } else {
            return false;
        }

        // Skip generic `<...>`
        if self.peek_kind_at(cursor) == &TokenKind::Lt {
            let mut depth: i32 = 1;
            cursor += 1;
            while cursor < self.tokens.len() && depth > 0 {
                match self.peek_kind_at(cursor) {
                    TokenKind::Lt => depth += 1,
                    TokenKind::Gt => depth -= 1,
                    TokenKind::Shr => depth = depth.saturating_sub(2),
                    TokenKind::Semicolon | TokenKind::LBrace | TokenKind::Eof => return false,
                    _ => {}
                }
                cursor += 1;
            }
        }

        // Optional nullable `?`
        if self.peek_kind_at(cursor) == &TokenKind::Question {
            cursor += 1;
        }

        // Must be followed by `Ident =`
        matches!(self.peek_kind_at(cursor), TokenKind::Ident(_))
            && self.peek_kind_at(cursor + 1) == &TokenKind::Assign
    }

    // ========================================================================
    // PRATT / PRECEDENCE-CLIMBING EXPRESSION PARSER
    // ========================================================================

    pub fn parse_expr(&mut self) -> Expr {
        // Check for lambda expression: `x => ...` or `(x, y) => ...`
        if let Some(lambda) = self.try_parse_lambda() {
            return lambda;
        }
        self.parse_assignment_expr()
    }

    fn try_parse_lambda(&mut self) -> Option<Expr> {
        let start_span = self.current_span();

        // Single-param lambda: `ident => ...`
        if self.is_ident_at(0) && self.peek_kind(1) == &TokenKind::FatArrow {
            let param = self.expect_ident("Expected lambda parameter.");
            self.advance(); // consume `=>`
            let body = if self.check(&TokenKind::LBrace) {
                LambdaBody::Block(self.parse_block())
            } else {
                LambdaBody::Expr(Box::new(self.parse_expr()))
            };
            return Some(Expr::new(
                start_span.merge(&self.previous_span()),
                ExprKind::Lambda {
                    params: vec![param],
                    body,
                },
            ));
        }

        // Parenthesized lambda: `(a, b) => ...` or `() => ...`
        if self.check(&TokenKind::LParen) {
            let mut cursor = self.pos + 1;
            let mut valid = true;
            while cursor < self.tokens.len() && self.peek_kind_at(cursor) != &TokenKind::RParen {
                if !matches!(self.peek_kind_at(cursor), TokenKind::Ident(_)) {
                    valid = false;
                    break;
                }
                cursor += 1;
                if self.peek_kind_at(cursor) == &TokenKind::Comma {
                    cursor += 1;
                } else if self.peek_kind_at(cursor) != &TokenKind::RParen {
                    valid = false;
                    break;
                }
            }

            if valid
                && self.peek_kind_at(cursor) == &TokenKind::RParen
                && self.peek_kind_at(cursor + 1) == &TokenKind::FatArrow
            {
                self.advance(); // '('
                let mut params = Vec::new();
                while !self.check(&TokenKind::RParen) && !self.is_at_end() {
                    params.push(self.expect_ident("Expected lambda parameter."));
                    if !self.match_kind(&TokenKind::Comma) {
                        break;
                    }
                }
                self.expect(&TokenKind::RParen, "Expected ')' in lambda.");
                self.expect(&TokenKind::FatArrow, "Expected '=>' in lambda.");
                let body = if self.check(&TokenKind::LBrace) {
                    LambdaBody::Block(self.parse_block())
                } else {
                    LambdaBody::Expr(Box::new(self.parse_expr()))
                };
                return Some(Expr::new(
                    start_span.merge(&self.previous_span()),
                    ExprKind::Lambda { params, body },
                ));
            }
        }

        None
    }

    fn parse_assignment_expr(&mut self) -> Expr {
        let left = self.parse_null_coalesce_expr();

        let assign_op = match self.peek_kind(0) {
            TokenKind::Assign => Some(AssignOp::Assign),
            TokenKind::PlusAssign => Some(AssignOp::AddAssign),
            TokenKind::MinusAssign => Some(AssignOp::SubAssign),
            TokenKind::StarAssign => Some(AssignOp::MulAssign),
            TokenKind::SlashAssign => Some(AssignOp::DivAssign),
            TokenKind::NullCoalesceEq => Some(AssignOp::NullCoalesceEq),
            _ => None,
        };

        if let Some(op) = assign_op {
            self.advance();
            let right = self.parse_expr();
            let span = left.span.merge(&right.span);
            return Expr::new(
                span,
                ExprKind::Assignment {
                    op,
                    target: Box::new(left),
                    value: Box::new(right),
                },
            );
        }

        left
    }

    fn parse_null_coalesce_expr(&mut self) -> Expr {
        let left = self.parse_logical_or_expr();
        if self.match_kind(&TokenKind::NullCoalesce) {
            let right = self.parse_null_coalesce_expr();
            let span = left.span.merge(&right.span);
            return Expr::new(
                span,
                ExprKind::NullCoalesce {
                    left: Box::new(left),
                    right: Box::new(right),
                },
            );
        }
        left
    }

    fn parse_logical_or_expr(&mut self) -> Expr {
        let mut expr = self.parse_logical_and_expr();
        while self.match_kind(&TokenKind::OrOr) {
            let right = self.parse_logical_and_expr();
            let span = expr.span.merge(&right.span);
            expr = Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Or,
                    left: Box::new(expr),
                    right: Box::new(right),
                },
            );
        }
        expr
    }

    fn parse_logical_and_expr(&mut self) -> Expr {
        let mut expr = self.parse_bitwise_or_expr();
        while self.match_kind(&TokenKind::AndAnd) {
            let right = self.parse_bitwise_or_expr();
            let span = expr.span.merge(&right.span);
            expr = Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::And,
                    left: Box::new(expr),
                    right: Box::new(right),
                },
            );
        }
        expr
    }

    fn parse_bitwise_or_expr(&mut self) -> Expr {
        let mut expr = self.parse_bitwise_xor_expr();
        while self.match_kind(&TokenKind::Pipe) {
            let right = self.parse_bitwise_xor_expr();
            let span = expr.span.merge(&right.span);
            expr = Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::BitOr,
                    left: Box::new(expr),
                    right: Box::new(right),
                },
            );
        }
        expr
    }

    fn parse_bitwise_xor_expr(&mut self) -> Expr {
        let mut expr = self.parse_bitwise_and_expr();
        while self.match_kind(&TokenKind::Caret) {
            let right = self.parse_bitwise_and_expr();
            let span = expr.span.merge(&right.span);
            expr = Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::BitXor,
                    left: Box::new(expr),
                    right: Box::new(right),
                },
            );
        }
        expr
    }

    fn parse_bitwise_and_expr(&mut self) -> Expr {
        let mut expr = self.parse_equality_expr();
        while self.match_kind(&TokenKind::Amp) {
            let right = self.parse_equality_expr();
            let span = expr.span.merge(&right.span);
            expr = Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::BitAnd,
                    left: Box::new(expr),
                    right: Box::new(right),
                },
            );
        }
        expr
    }

    fn parse_equality_expr(&mut self) -> Expr {
        let mut expr = self.parse_relational_expr();
        loop {
            let op = match self.peek_kind(0) {
                TokenKind::Eq => Some(BinaryOp::Eq),
                TokenKind::Neq => Some(BinaryOp::Neq),
                _ => None,
            };
            if let Some(op) = op {
                self.advance();
                let right = self.parse_relational_expr();
                let span = expr.span.merge(&right.span);
                expr = Expr::new(
                    span,
                    ExprKind::Binary {
                        op,
                        left: Box::new(expr),
                        right: Box::new(right),
                    },
                );
            } else {
                break;
            }
        }
        expr
    }

    fn parse_relational_expr(&mut self) -> Expr {
        let mut expr = self.parse_range_expr();

        if self.match_kind(&TokenKind::Is) {
            let pattern = self.parse_pattern();
            let span = expr.span.merge(&self.previous_span());
            return Expr::new(
                span,
                ExprKind::IsPattern {
                    expr: Box::new(expr),
                    pattern,
                },
            );
        }

        loop {
            let op = match self.peek_kind(0) {
                TokenKind::Lt => Some(BinaryOp::Lt),
                TokenKind::Gt => Some(BinaryOp::Gt),
                TokenKind::Lte => Some(BinaryOp::Lte),
                TokenKind::Gte => Some(BinaryOp::Gte),
                _ => None,
            };
            if let Some(op) = op {
                self.advance();
                let right = self.parse_range_expr();
                let span = expr.span.merge(&right.span);
                expr = Expr::new(
                    span,
                    ExprKind::Binary {
                        op,
                        left: Box::new(expr),
                        right: Box::new(right),
                    },
                );
            } else {
                break;
            }
        }
        expr
    }

    fn parse_range_expr(&mut self) -> Expr {
        if self.match_kind(&TokenKind::DotDot) {
            let start_span = self.previous_span();
            let end = if self.can_start_expr() {
                Some(Box::new(self.parse_additive_expr()))
            } else {
                None
            };
            let span = start_span.merge(&self.previous_span());
            return Expr::new(
                span,
                ExprKind::RangeSlice {
                    target: None,
                    start: None,
                    end,
                },
            );
        }

        let left = self.parse_shift_expr();
        if self.match_kind(&TokenKind::DotDot) {
            let end = if self.can_start_expr() {
                Some(Box::new(self.parse_shift_expr()))
            } else {
                None
            };
            let span = left.span.merge(&self.previous_span());
            return Expr::new(
                span,
                ExprKind::RangeSlice {
                    target: None,
                    start: Some(Box::new(left)),
                    end,
                },
            );
        }
        left
    }

    fn parse_shift_expr(&mut self) -> Expr {
        let mut expr = self.parse_additive_expr();
        loop {
            let op = match self.peek_kind(0) {
                TokenKind::Shl => Some(BinaryOp::Shl),
                TokenKind::Shr => Some(BinaryOp::Shr),
                _ => None,
            };
            if let Some(op) = op {
                self.advance();
                let right = self.parse_additive_expr();
                let span = expr.span.merge(&right.span);
                expr = Expr::new(
                    span,
                    ExprKind::Binary {
                        op,
                        left: Box::new(expr),
                        right: Box::new(right),
                    },
                );
            } else {
                break;
            }
        }
        expr
    }

    fn parse_additive_expr(&mut self) -> Expr {
        let mut expr = self.parse_multiplicative_expr();
        loop {
            let op = match self.peek_kind(0) {
                TokenKind::Plus => Some(BinaryOp::Add),
                TokenKind::Minus => Some(BinaryOp::Sub),
                _ => None,
            };
            if let Some(op) = op {
                self.advance();
                let right = self.parse_multiplicative_expr();
                let span = expr.span.merge(&right.span);
                expr = Expr::new(
                    span,
                    ExprKind::Binary {
                        op,
                        left: Box::new(expr),
                        right: Box::new(right),
                    },
                );
            } else {
                break;
            }
        }
        expr
    }

    fn parse_multiplicative_expr(&mut self) -> Expr {
        let mut expr = self.parse_unary_expr();
        loop {
            let op = match self.peek_kind(0) {
                TokenKind::Star => Some(BinaryOp::Mul),
                TokenKind::Slash => Some(BinaryOp::Div),
                TokenKind::Percent => Some(BinaryOp::Rem),
                _ => None,
            };
            if let Some(op) = op {
                self.advance();
                let right = self.parse_unary_expr();
                let span = expr.span.merge(&right.span);
                expr = Expr::new(
                    span,
                    ExprKind::Binary {
                        op,
                        left: Box::new(expr),
                        right: Box::new(right),
                    },
                );
            } else {
                break;
            }
        }
        expr
    }

    fn parse_unary_expr(&mut self) -> Expr {
        let start_span = self.current_span();
        let op = match self.peek_kind(0) {
            TokenKind::Bang => Some(UnaryOp::Not),
            TokenKind::Tilde => Some(UnaryOp::BitNot),
            TokenKind::Minus => Some(UnaryOp::Neg),
            TokenKind::Await => Some(UnaryOp::Await),
            TokenKind::Caret => Some(UnaryOp::FromEnd),
            _ => None,
        };

        if let Some(op) = op {
            self.advance();
            let operand = self.parse_unary_expr();
            let span = start_span.merge(&operand.span);
            return Expr::new(
                span,
                ExprKind::Unary {
                    op,
                    operand: Box::new(operand),
                },
            );
        }

        self.parse_postfix_expr()
    }

    fn parse_postfix_expr(&mut self) -> Expr {
        let mut expr = self.parse_primary_expr();

        loop {
            if self.match_kind(&TokenKind::Dot) || self.match_kind(&TokenKind::NullCond) {
                let is_null_conditional = self.previous().kind == TokenKind::NullCond;
                let member = self.expect_ident("Expected member name after '.' or '?.'.");

                let type_args = if self.check(&TokenKind::Lt) && self.looks_like_generic_call_args()
                {
                    let mut args = Vec::new();
                    self.advance(); // '<'
                    while !self.check_gt_or_shr() && !self.is_at_end() {
                        args.push(self.parse_type_ref());
                        if !self.match_kind(&TokenKind::Comma) {
                            break;
                        }
                    }
                    self.expect_gt_or_split_shr("Expected '>' after method type arguments.");
                    args
                } else {
                    Vec::new()
                };

                if self.match_kind(&TokenKind::LParen) {
                    let args = self.parse_arg_list();
                    let end = self.expect(&TokenKind::RParen, "Expected ')' after call arguments.");
                    let span = expr.span.merge(&end);
                    expr = Expr::new(
                        span,
                        ExprKind::MethodCall {
                            receiver: Some(Box::new(expr)),
                            method_name: member,
                            type_args,
                            args,
                            is_null_conditional,
                            resolved_overload: None,
                            primitive_lowering: PrimitiveLowering::None,
                        },
                    );
                } else {
                    let span = expr.span.merge(&self.previous_span());
                    expr = Expr::new(
                        span,
                        ExprKind::MemberAccess {
                            target: Box::new(expr),
                            member,
                            is_null_conditional,
                            resolved_symbol: None,
                        },
                    );
                }
            } else if self.match_kind(&TokenKind::LParen) {
                // Direct unqualified call `ApplyCoupon(order, coupon)`
                let args = self.parse_arg_list();
                let end = self.expect(&TokenKind::RParen, "Expected ')' after arguments.");
                let span = expr.span.merge(&end);

                if let ExprKind::Identifier { name, .. } = expr.kind {
                    expr = Expr::new(
                        span,
                        ExprKind::MethodCall {
                            receiver: None,
                            method_name: name,
                            type_args: Vec::new(),
                            args,
                            is_null_conditional: false,
                            resolved_overload: None,
                            primitive_lowering: PrimitiveLowering::None,
                        },
                    );
                }
            } else if self.match_kind(&TokenKind::LBracket) {
                let mut indices = Vec::new();
                while !self.check(&TokenKind::RBracket) && !self.is_at_end() {
                    let arg_start = self.current_span();
                    let idx_expr = self.parse_expr();
                    indices.push(ArgNode {
                        span: arg_start.merge(&idx_expr.span),
                        name: None,
                        expr: idx_expr,
                    });
                    if !self.match_kind(&TokenKind::Comma) {
                        break;
                    }
                }
                let end = self.expect(&TokenKind::RBracket, "Expected ']' after index/slice.");
                let span = expr.span.merge(&end);

                // If the single index argument is a `..` range (`buffer[0..16]`), produce `ExprKind::RangeSlice`
                if indices.len() == 1 {
                    if let ExprKind::RangeSlice { start, end, .. } = indices[0].expr.kind.clone() {
                        expr = Expr::new(
                            span,
                            ExprKind::RangeSlice {
                                target: Some(Box::new(expr)),
                                start,
                                end,
                            },
                        );
                        continue;
                    }
                }

                expr = Expr::new(
                    span,
                    ExprKind::IndexAccess {
                        target: Box::new(expr),
                        indices,
                    },
                );
            } else if self.match_kind(&TokenKind::Switch) {
                self.expect(&TokenKind::LBrace, "Expected '{' after 'switch'.");
                let mut arms = Vec::new();
                while !self.check(&TokenKind::RBrace) && !self.is_at_end() {
                    let arm_start = self.current_span();
                    let pattern = self.parse_pattern();
                    let guard = if self.match_kind(&TokenKind::When) {
                        Some(self.parse_expr())
                    } else {
                        None
                    };
                    self.expect(&TokenKind::FatArrow, "Expected '=>' in switch arm.");
                    let body = self.parse_expr();
                    arms.push(SwitchArmNode {
                        span: arm_start.merge(&body.span),
                        pattern,
                        guard,
                        body,
                    });
                    if !self.match_kind(&TokenKind::Comma) {
                        break;
                    }
                }
                let end = self.expect(&TokenKind::RBrace, "Expected '}' after switch arms.");
                let span = expr.span.merge(&end);
                expr = Expr::new(
                    span,
                    ExprKind::Switch {
                        scrutinee: Box::new(expr),
                        arms,
                    },
                );
            } else {
                break;
            }
        }

        expr
    }

    fn parse_primary_expr(&mut self) -> Expr {
        let tok = self.peek(0).clone();

        match tok.kind {
            TokenKind::IntLit(v) => {
                self.advance();
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Int(v)))
            }
            TokenKind::FloatLit(v) => {
                self.advance();
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Float(v)))
            }
            TokenKind::DecimalLit(s) => {
                self.advance();
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Decimal(s)))
            }
            TokenKind::StringLit(s) => {
                self.advance();
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::String(s)))
            }
            TokenKind::CharLit(c) => {
                self.advance();
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Char(c)))
            }
            TokenKind::BoolLit(b) => {
                self.advance();
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Bool(b)))
            }
            TokenKind::Null => {
                self.advance();
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Null))
            }
            TokenKind::InterpString(parts) => {
                self.advance();
                Expr::new(tok.span, ExprKind::InterpolatedString(parts))
            }
            TokenKind::This => {
                self.advance();
                Expr::new(tok.span, ExprKind::This)
            }
            TokenKind::Base => {
                self.advance();
                Expr::new(tok.span, ExprKind::Base)
            }
            TokenKind::New => {
                let start = self.advance().span.clone();
                let ty = self.parse_type_ref();
                self.expect(
                    &TokenKind::LParen,
                    "Expected '(' after type in 'new' expression.",
                );
                let args = self.parse_arg_list();
                let end = self.expect(
                    &TokenKind::RParen,
                    "Expected ')' after constructor arguments.",
                );
                Expr::new(
                    start.merge(&end),
                    ExprKind::Construct {
                        ty,
                        args,
                        resolved_ctor: None,
                        primitive_lowering: PrimitiveLowering::None,
                    },
                )
            }
            TokenKind::LParen => {
                let start = self.advance().span.clone();
                let inner = self.parse_expr();
                let end = self.expect(
                    &TokenKind::RParen,
                    "Expected ')' after parenthesized expression.",
                );
                Expr {
                    span: start.merge(&end),
                    ..inner
                }
            }
            TokenKind::Ident(name) => {
                self.advance();
                Expr::new(
                    tok.span,
                    ExprKind::Identifier {
                        name,
                        resolved_symbol: None,
                    },
                )
            }
            _ => {
                if let Some(prim) = tok.kind.is_primitive_type_keyword() {
                    self.advance();
                    return Expr::new(
                        tok.span,
                        ExprKind::Identifier {
                            name: prim.to_string(),
                            resolved_symbol: None,
                        },
                    );
                }
                self.advance();
                self.diag.report_syntax_error(
                    tok.span.clone(),
                    format!("Unexpected token '{}' in expression.", tok.lexeme),
                );
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Null))
            }
        }
    }

    fn parse_arg_list(&mut self) -> Vec<ArgNode> {
        let mut args = Vec::new();
        while !self.check(&TokenKind::RParen) && !self.is_at_end() {
            let arg_start = self.current_span();
            let name = if self.is_ident_at(0) && self.peek_kind(1) == &TokenKind::Colon {
                let n = self.expect_ident("Expected argument name.");
                self.advance(); // ':'
                Some(n)
            } else {
                None
            };
            let expr = self.parse_expr();
            args.push(ArgNode {
                span: arg_start.merge(&expr.span),
                name,
                expr,
            });
            if !self.match_kind(&TokenKind::Comma) {
                break;
            }
        }
        args
    }

    fn parse_pattern(&mut self) -> Pattern {
        let tok = self.peek(0).clone();
        match tok.kind {
            TokenKind::Underscore => {
                self.advance();
                Pattern::Wildcard(tok.span)
            }
            TokenKind::Null => {
                self.advance();
                Pattern::Null(tok.span)
            }
            TokenKind::IntLit(v) => {
                self.advance();
                Pattern::Literal(tok.span, LiteralValue::Int(v))
            }
            TokenKind::Minus if matches!(self.peek_kind(1), TokenKind::IntLit(_)) => {
                let start = self.advance().span.clone();
                if let TokenKind::IntLit(v) = self.advance().kind.clone() {
                    Pattern::Literal(start.merge(&self.previous_span()), LiteralValue::Int(-v))
                } else {
                    Pattern::Wildcard(start)
                }
            }
            TokenKind::StringLit(s) => {
                self.advance();
                Pattern::Literal(tok.span, LiteralValue::String(s))
            }
            TokenKind::BoolLit(b) => {
                self.advance();
                Pattern::Literal(tok.span, LiteralValue::Bool(b))
            }
            _ => {
                let start = self.current_span();
                let ty = self.parse_type_ref();
                let bind_name = if self.is_ident_at(0) && !self.check(&TokenKind::When) {
                    Some(self.expect_ident("Expected pattern variable name."))
                } else {
                    None
                };

                let mut property_patterns = Vec::new();
                if self.match_kind(&TokenKind::LBrace) {
                    while !self.check(&TokenKind::RBrace) && !self.is_at_end() {
                        let field_name = self.expect_ident("Expected property name in pattern.");
                        self.expect(&TokenKind::Colon, "Expected ':' in property pattern.");
                        let sub_pat = self.parse_pattern();
                        property_patterns.push(PropertyPatternField {
                            field_name,
                            pattern: sub_pat,
                        });
                        if !self.match_kind(&TokenKind::Comma) {
                            break;
                        }
                    }
                    self.expect(&TokenKind::RBrace, "Expected '}' after property pattern.");
                }

                Pattern::TypePattern {
                    span: start.merge(&self.previous_span()),
                    ty,
                    bind_name,
                    property_patterns,
                }
            }
        }
    }

    // ========================================================================
    // PARSER NAVIGATION HELPERS
    // ========================================================================

    fn parse_qualified_ident(&mut self) -> Vec<String> {
        let mut parts = Vec::new();
        parts.push(self.expect_ident("Expected identifier."));
        while self.match_kind(&TokenKind::Dot) || self.match_kind(&TokenKind::ColonColon) {
            parts.push(self.expect_ident("Expected identifier after '.' or '::'."));
        }
        parts
    }

    fn looks_like_generic_call_args(&self) -> bool {
        let mut cursor = self.pos;
        if self.peek_kind_at(cursor) != &TokenKind::Lt {
            return false;
        }
        let mut depth: i32 = 1;
        cursor += 1;
        while cursor < self.tokens.len() && depth > 0 {
            match self.peek_kind_at(cursor) {
                TokenKind::Lt => depth += 1,
                TokenKind::Gt => depth -= 1,
                TokenKind::Shr => depth = depth.saturating_sub(2),
                TokenKind::Semicolon | TokenKind::LBrace | TokenKind::RBrace | TokenKind::Eof => {
                    return false
                }
                _ => {}
            }
            cursor += 1;
        }
        self.peek_kind_at(cursor) == &TokenKind::LParen
    }

    fn can_start_expr(&self) -> bool {
        !matches!(
            self.peek_kind(0),
            TokenKind::RBracket
                | TokenKind::RParen
                | TokenKind::RBrace
                | TokenKind::Semicolon
                | TokenKind::Comma
                | TokenKind::Eof
        )
    }

    fn is_at_end(&self) -> bool {
        matches!(self.peek_kind(0), TokenKind::Eof)
    }

    fn peek(&self, offset: usize) -> &Token {
        let idx = (self.pos + offset).min(self.tokens.len().saturating_sub(1));
        &self.tokens[idx]
    }

    fn peek_kind(&self, offset: usize) -> &TokenKind {
        &self.peek(offset).kind
    }

    fn peek_kind_at(&self, index: usize) -> &TokenKind {
        let idx = index.min(self.tokens.len().saturating_sub(1));
        &self.tokens[idx].kind
    }

    fn peek_ident(&self, offset: usize) -> Option<&str> {
        match self.peek_kind(offset) {
            TokenKind::Ident(s) => Some(s.as_str()),
            _ => None,
        }
    }

    fn is_ident_at(&self, offset: usize) -> bool {
        matches!(
            self.peek_kind(offset),
            TokenKind::Ident(_) | TokenKind::Get | TokenKind::Set
        )
    }

    fn check(&self, expected: &TokenKind) -> bool {
        std::mem::discriminant(self.peek_kind(0)) == std::mem::discriminant(expected)
    }

    fn match_kind(&mut self, expected: &TokenKind) -> bool {
        if self.check(expected) {
            self.advance();
            true
        } else {
            false
        }
    }

    fn advance(&mut self) -> &Token {
        if !self.is_at_end() {
            self.pos += 1;
        }
        self.previous()
    }

    fn previous(&self) -> &Token {
        &self.tokens[self.pos.saturating_sub(1)]
    }

    fn current_span(&self) -> SourceSpan {
        self.peek(0).span.clone()
    }

    fn previous_span(&self) -> SourceSpan {
        self.previous().span.clone()
    }

    fn expect(&mut self, expected: &TokenKind, message: &str) -> SourceSpan {
        if self.check(expected) {
            self.advance().span.clone()
        } else {
            let span = self.current_span();
            self.diag.report_syntax_error(span.clone(), message);
            span
        }
    }

    fn check_gt_or_shr(&self) -> bool {
        self.check(&TokenKind::Gt) || self.check(&TokenKind::Shr)
    }

    fn match_gt_or_split_shr(&mut self) -> bool {
        if self.match_kind(&TokenKind::Gt) {
            return true;
        }
        if self.check(&TokenKind::Shr) {
            self.tokens[self.pos].kind = TokenKind::Gt;
            self.tokens[self.pos].lexeme = ">".to_string();
            return true;
        }
        false
    }

    fn expect_gt_or_split_shr(&mut self, message: &str) -> SourceSpan {
        if self.match_gt_or_split_shr() {
            self.previous_span()
        } else {
            let span = self.current_span();
            self.diag.report_syntax_error(span.clone(), message);
            span
        }
    }

    fn expect_ident(&mut self, message: &str) -> String {
        match self.peek_kind(0).clone() {
            TokenKind::Ident(s) => {
                self.advance();
                s
            }
            TokenKind::Get => {
                self.advance();
                "get".to_string()
            }
            TokenKind::Set => {
                self.advance();
                "set".to_string()
            }
            _ => {
                let span = self.current_span();
                self.diag.report_syntax_error(span, message);
                String::from("_error")
            }
        }
    }
}

fn extract_attr_string(attrs: &[AttributeNode], target_name: &str) -> Option<String> {
    for attr in attrs {
        let short = attr.short_name().trim_end_matches("Attribute");
        if short == target_name {
            if let Some(val) = attr.first_string_arg() {
                return Some(val.to_string());
            }
        }
    }
    None
}

fn extract_explicit_borrow(attrs: &[AttributeNode]) -> Option<BorrowMode> {
    for attr in attrs {
        match attr.short_name().trim_end_matches("Attribute") {
            "Borrows" => return Some(BorrowMode::ReadBorrow),
            "Mutates" => return Some(BorrowMode::MutBorrow),
            "Moves" => return Some(BorrowMode::OwnedMove),
            _ => {}
        }
    }
    None
}

fn extract_primitive_lowering(attrs: &[AttributeNode]) -> PrimitiveLowering {
    if let Some(tpl) = extract_attr_string(attrs, "InlineTemplate") {
        return PrimitiveLowering::InlineTemplate { template: tpl };
    }
    if let Some(target) = extract_attr_string(attrs, "MapsTo") {
        return PrimitiveLowering::DirectSymbol { rust_path: target };
    }
    PrimitiveLowering::None
}
