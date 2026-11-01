from __future__ import annotations

from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend.ast_nodes import (
    AccessMod,
    AccessorDecl,
    ArgNode,
    AttributeArg,
    AttributeNode,
    BinaryOp,
    BlockStmt,
    CatchClause,
    CompilationUnit,
    ConstructorChain,
    EnumMember,
    Expr,
    ExprKind,
    ExprStmt,
    FieldDecl,
    ForEachStmt,
    IfStmt,
    ImportDecl,
    IndexerDecl,
    InterpolatedPart,
    LambdaParam,
    LiteralKind,
    LocalVarStmt,
    MemberDecl,
    MethodDecl,
    ParamDecl,
    PatternNode,
    PropertyDecl,
    ReturnStmt,
    SliceDimension,
    Stmt,
    SwitchArm,
    SwitchSection,
    SwitchStmt,
    ThrowStmt,
    TryCatchFinallyStmt,
    TypeConstraint,
    TypeDecl,
    TypeKind,
    TypeRef,
    UnaryOp,
    UsingResourceStmt,
    WhileStmt,
    YieldStmt,
)
from psc.frontend.lexer import Lexer
from psc.frontend.tokens import PRIMITIVE_TYPE_TOKENS, Token, TokenKind

ACCESS_TOKEN_MAP: dict[TokenKind, AccessMod] = {
    TokenKind.PUBLIC: AccessMod.PUBLIC,
    TokenKind.INTERNAL: AccessMod.INTERNAL,
    TokenKind.PROTECTED: AccessMod.PROTECTED,
    TokenKind.PRIVATE: AccessMod.PRIVATE,
}

MODIFIER_TOKENS: frozenset[TokenKind] = frozenset(
    {
        TokenKind.ABSTRACT,
        TokenKind.SEALED,
        TokenKind.PARTIAL,
        TokenKind.STATIC,
        TokenKind.PRIMITIVE,
        TokenKind.READONLY,
        TokenKind.VIRTUAL,
        TokenKind.OVERRIDE,
        TokenKind.EXTERN,
        TokenKind.ASYNC,
    }
)


class _ParseBacktrack(Exception):
    """Internal signal used for speculative lookahead (generics, lambdas, local vars)."""


class Parser:
    """Recursive-descent declaration/statement parser + Pratt expression parser for PythonSharp."""

    def __init__(
        self,
        tokens: list[Token],
        diagnostics: DiagnosticEngine | None = None,
        is_ambient_stub: bool = False,
    ) -> None:
        self.tokens = tokens
        self.diagnostics = diagnostics if diagnostics is not None else DiagnosticEngine()
        self.is_ambient_stub = is_ambient_stub
        self.pos = 0
        self._speculative_depth = 0

    @classmethod
    def from_source(
        cls,
        source: str,
        file_id: int = 0,
        ps_filename: str = "<input>.ps",
        diagnostics: DiagnosticEngine | None = None,
    ) -> Parser:
        diag = diagnostics if diagnostics is not None else DiagnosticEngine()
        lexer = Lexer(source, file_id=file_id, ps_filename=ps_filename, diagnostics=diag)
        tokens = lexer.tokenize()
        return cls(
            tokens=tokens,
            diagnostics=diag,
            is_ambient_stub=ps_filename.endswith(".d.ps"),
        )

    # ========================================================================
    # 1. CURSOR & TOKEN NAVIGATION HELPERS
    # ========================================================================

    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _previous(self) -> Token:
        return self.tokens[self.pos - 1]

    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _is_at_end(self) -> bool:
        return self._current().kind == TokenKind.EOF

    def _check(self, *kinds: TokenKind) -> bool:
        return self._current().kind in kinds

    def _check_ident_like(self) -> bool:
        """Allows contextual keywords like `get`, `set`, `value`, or `from` as identifiers."""
        k = self._current().kind
        return k in (TokenKind.IDENT, TokenKind.GET, TokenKind.SET)

    def _advance(self) -> Token:
        if not self._is_at_end():
            self.pos += 1
        return self.tokens[self.pos - 1]

    def _match(self, *kinds: TokenKind) -> bool:
        if self._check(*kinds):
            self._advance()
            return True
        return False

    def _expect(self, kind: TokenKind, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        if self._speculative_depth > 0:
            raise _ParseBacktrack()
        cur = self._current()
        self.diagnostics.report_syntax_error(cur.span, f"{message} (found {cur.lexeme!r})")
        return self._advance()

    def _expect_ident(self, message: str = "Expected identifier") -> Token:
        if self._check_ident_like():
            return self._advance()
        return self._expect(TokenKind.IDENT, message)

    # ========================================================================
    # 2. COMPILATION UNIT, NAMESPACE & IMPORTS
    # ========================================================================

    def parse_compilation_unit(self) -> CompilationUnit:
        first_tok = self._current()
        namespace: list[str] = []
        imports: list[ImportDecl] = []
        types: list[TypeDecl] = []

        if self._match(TokenKind.NAMESPACE):
            namespace = self._parse_qualified_ident()
            self._expect(TokenKind.SEMICOLON, "Expected ';' after namespace declaration")

        while self._check(TokenKind.USING, TokenKind.EXTERN):
            if self._check(TokenKind.EXTERN) and self._peek(1).kind != TokenKind.USING:
                break
            imports.append(self.parse_import_decl())

        while not self._is_at_end():
            types.append(self.parse_type_decl())

        return CompilationUnit(
            file_id=first_tok.span.file_id,
            ps_filename=first_tok.span.ps_filename,
            is_ambient_stub=self.is_ambient_stub,
            namespace=namespace,
            imports=imports,
            types=types,
        )

    def _parse_qualified_ident(self) -> list[str]:
        parts = [self._expect_ident("Expected identifier in qualified name").lexeme]
        while self._match(TokenKind.DOT):
            parts.append(self._expect_ident("Expected identifier after '.'").lexeme)
        return parts

    def parse_import_decl(self) -> ImportDecl:
        start_span = self._current().span
        is_extern = self._match(TokenKind.EXTERN)
        self._expect(TokenKind.USING, "Expected 'using'")

        alias: str | None = None
        if not is_extern and self._check_ident_like() and self._peek(1).kind == TokenKind.ASSIGN:
            alias = self._advance().lexeme
            self._advance()  # Consume '='

        path = self._parse_qualified_ident()
        if is_extern and self._match(TokenKind.AS):
            alias = self._expect_ident("Expected alias identifier after 'as'").lexeme

        end_tok = self._expect(TokenKind.SEMICOLON, "Expected ';' after using directive")
        return ImportDecl(
            span=start_span.merge(end_tok.span),
            is_extern=is_extern,
            path=path,
            alias=alias,
        )

    # ========================================================================
    # 3. ATTRIBUTES
    # ========================================================================

    def parse_attribute_sections(self) -> list[AttributeNode]:
        attrs: list[AttributeNode] = []
        while self._match(TokenKind.LBRACKET):
            while not self._is_at_end() and not self._check(TokenKind.RBRACKET):
                attr_start = self._current().span
                path = self._parse_qualified_ident()
                args: list[AttributeArg] = []
                if self._match(TokenKind.LPAREN):
                    if not self._check(TokenKind.RPAREN):
                        args.append(self._parse_attribute_arg())
                        while self._match(TokenKind.COMMA):
                            if self._check(TokenKind.RPAREN):
                                break
                            args.append(self._parse_attribute_arg())
                    self._expect(TokenKind.RPAREN, "Expected ')' after attribute arguments")
                attrs.append(
                    AttributeNode(
                        span=attr_start.merge(self._previous().span),
                        path=path,
                        args=args,
                    )
                )
                if not self._match(TokenKind.COMMA):
                    break
            self._expect(TokenKind.RBRACKET, "Expected ']' after attribute section")
        return attrs

    def _parse_attribute_arg(self) -> AttributeArg:
        start_span = self._current().span
        arg_name: str | None = None
        if self._check_ident_like() and self._peek(1).kind in (TokenKind.ASSIGN, TokenKind.COLON):
            arg_name = self._advance().lexeme
            self._advance()  # Consume '=' or ':'
        expr = self.parse_expr()
        return AttributeArg(
            span=start_span.merge(expr.span),
            name=arg_name,
            expr=expr,
        )

    # ========================================================================
    # 4. TYPE DECLARATIONS (Class, Primitive Class, Record, Struct, Interface, Enum)
    # ========================================================================

    def parse_type_decl(self) -> TypeDecl:
        attrs = self.parse_attribute_sections()
        start_span = attrs[0].span if attrs else self._current().span

        access, modifiers = self._parse_access_and_modifiers(default_access=AccessMod.INTERNAL)
        is_primitive = "primitive" in modifiers

        if self._match(TokenKind.CLASS):
            kind = TypeKind.PRIMITIVE_CLASS if is_primitive else TypeKind.CLASS
        elif self._match(TokenKind.RECORD):
            if self._match(TokenKind.STRUCT):
                kind = TypeKind.RECORD_STRUCT
            else:
                self._match(TokenKind.CLASS)
                kind = TypeKind.RECORD
        elif self._match(TokenKind.STRUCT):
            kind = TypeKind.PRIMITIVE_STRUCT if is_primitive else TypeKind.STRUCT
        elif self._match(TokenKind.INTERFACE):
            kind = TypeKind.PRIMITIVE_INTERFACE if is_primitive else TypeKind.INTERFACE
        elif self._match(TokenKind.ENUM):
            kind = TypeKind.ENUM
        else:
            tok = self._current()
            self.diagnostics.report_syntax_error(
                tok.span,
                f"Expected type declaration ('class', 'record', 'struct', 'interface', or 'enum'), found {tok.lexeme!r}",
            )
            self._advance()
            kind = TypeKind.CLASS

        name_tok = self._expect_ident("Expected type name")
        type_params = self._parse_optional_type_params()

        if kind == TypeKind.ENUM:
            return self._parse_enum_body(start_span, attrs, access, modifiers, name_tok.lexeme)

        # Primary constructor parameters for records
        primary_ctor_params: list[ParamDecl] = []
        if kind in (TypeKind.RECORD, TypeKind.RECORD_STRUCT) and self._match(TokenKind.LPAREN):
            primary_ctor_params = self._parse_param_list_until_rparen()

        # Base types / interfaces (`: Base, IFoo<T>`)
        base_types: list[TypeRef] = []
        if self._match(TokenKind.COLON):
            base_types.append(self.parse_type_ref())
            while self._match(TokenKind.COMMA):
                base_types.append(self.parse_type_ref())

        constraints = self._parse_type_constraints()

        # Records can terminate directly with ';'
        members: list[MemberDecl] = []
        if self._match(TokenKind.SEMICOLON):
            end_span = self._previous().span
        else:
            self._expect(TokenKind.LBRACE, f"Expected '{{' to open body of '{name_tok.lexeme}'")
            is_iface = kind in (TypeKind.INTERFACE, TypeKind.PRIMITIVE_INTERFACE)
            while not self._is_at_end() and not self._check(TokenKind.RBRACE):
                members.append(
                    self.parse_member_decl(
                        enclosing_type_name=name_tok.lexeme,
                        in_interface=is_iface,
                    )
                )
            end_tok = self._expect(TokenKind.RBRACE, f"Expected '}}' to close '{name_tok.lexeme}'")
            end_span = end_tok.span

        return TypeDecl(
            span=start_span.merge(end_span),
            attributes=attrs,
            access=access,
            modifiers=modifiers,
            kind=kind,
            name=name_tok.lexeme,
            type_params=type_params,
            primary_ctor_params=primary_ctor_params,
            base_types=base_types,
            constraints=constraints,
            members=members,
        )

    def _parse_enum_body(
        self,
        start_span: SourceSpan,
        attrs: list[AttributeNode],
        access: AccessMod,
        modifiers: list[str],
        name: str,
    ) -> TypeDecl:
        self._expect(TokenKind.LBRACE, f"Expected '{{' in enum '{name}'")
        enum_members: list[EnumMember] = []
        while not self._is_at_end() and not self._check(TokenKind.RBRACE):
            m_attrs = self.parse_attribute_sections()
            m_start = m_attrs[0].span if m_attrs else self._current().span
            m_name = self._expect_ident("Expected enum member name")
            val_expr: Expr | None = None
            if self._match(TokenKind.ASSIGN):
                val_expr = self.parse_expr()
            enum_members.append(
                EnumMember(
                    span=m_start.merge(val_expr.span if val_expr else m_name.span),
                    attributes=m_attrs,
                    name=m_name.lexeme,
                    value=val_expr,
                )
            )
            if not self._match(TokenKind.COMMA):
                break
        end_tok = self._expect(TokenKind.RBRACE, f"Expected '}}' after enum '{name}'")
        return TypeDecl(
            span=start_span.merge(end_tok.span),
            attributes=attrs,
            access=access,
            modifiers=modifiers,
            kind=TypeKind.ENUM,
            name=name,
            enum_members=enum_members,
        )

    def _parse_access_and_modifiers(self, default_access: AccessMod) -> tuple[AccessMod, list[str]]:
        access: AccessMod | None = None
        modifiers: list[str] = []
        while True:
            cur_kind = self._current().kind
            if cur_kind in ACCESS_TOKEN_MAP:
                access = ACCESS_TOKEN_MAP[self._advance().kind]
            elif cur_kind in MODIFIER_TOKENS:
                modifiers.append(self._advance().lexeme)
            else:
                break
        return (access if access is not None else default_access), modifiers

    def _parse_optional_type_params(self) -> list[str]:
        params: list[str] = []
        if self._match(TokenKind.LT):
            params.append(self._expect_ident("Expected generic type parameter name").lexeme)
            while self._match(TokenKind.COMMA):
                params.append(self._expect_ident("Expected generic type parameter name").lexeme)
            self._expect(TokenKind.GT, "Expected '>' after generic type parameters")
        return params

    def _parse_type_constraints(self) -> list[TypeConstraint]:
        constraints: list[TypeConstraint] = []
        while self._match(TokenKind.WHERE):
            start_span = self._previous().span
            tp_name = self._expect_ident("Expected type parameter name after 'where'").lexeme
            self._expect(TokenKind.COLON, "Expected ':' in type constraint")
            bounds = [self.parse_type_ref()]
            while self._match(TokenKind.COMMA):
                bounds.append(self.parse_type_ref())
            constraints.append(
                TypeConstraint(
                    span=start_span.merge(bounds[-1].span),
                    type_param=tp_name,
                    bounds=bounds,
                )
            )
        return constraints

    # ========================================================================
    # 5. CLASS, INTERFACE & PRIMITIVE MEMBERS
    # ========================================================================

    def parse_member_decl(self, enclosing_type_name: str, in_interface: bool = False) -> MemberDecl:
        attrs = self.parse_attribute_sections()
        start_span = attrs[0].span if attrs else self._current().span
        default_acc = AccessMod.PUBLIC if in_interface else AccessMod.PRIVATE
        access, modifiers = self._parse_access_and_modifiers(default_access=default_acc)

        # Constructor check: `<EnclosingTypeName>(...)`
        if self._current().lexeme == enclosing_type_name and self._peek(1).kind == TokenKind.LPAREN:
            name_tok = self._advance()
            self._expect(TokenKind.LPAREN, "Expected '(' in constructor")
            params = self._parse_param_list_until_rparen()
            ctor_chain: ConstructorChain | None = None
            if self._match(TokenKind.COLON):
                chain_start = self._previous().span
                if self._match(TokenKind.BASE):
                    target = "base"
                elif self._match(TokenKind.THIS):
                    target = "this"
                else:
                    target = "base"
                    self.diagnostics.report_syntax_error(
                        self._current().span, "Expected 'base' or 'this' in constructor initializer"
                    )
                self._expect(TokenKind.LPAREN, "Expected '(' after constructor chain")
                chain_args = self._parse_arg_list_until(TokenKind.RPAREN)
                end_chain = self._expect(TokenKind.RPAREN, "Expected ')' after constructor chain")
                ctor_chain = ConstructorChain(
                    span=chain_start.merge(end_chain.span),
                    target=target,
                    args=chain_args,
                )
            body, expr_body, end_span = self._parse_callable_body()
            return MethodDecl(
                span=start_span.merge(end_span),
                attributes=attrs,
                access=access,
                modifiers=modifiers,
                is_constructor=True,
                name=name_tok.lexeme,
                return_type=None,
                params=params,
                ctor_chain=ctor_chain,
                body=body,
                expr_body=expr_body,
            )

        # Otherwise, parse member return/field type first
        member_type = self.parse_type_ref()

        # Indexer check: `T this[...]`
        if self._match(TokenKind.THIS):
            self._expect(TokenKind.LBRACKET, "Expected '[' in indexer declaration")
            params = self._parse_param_list_until(TokenKind.RBRACKET)
            self._expect(TokenKind.LBRACE, "Expected '{' in indexer declaration")
            accessors = self._parse_accessor_list()
            end_tok = self._expect(TokenKind.RBRACE, "Expected '}' after indexer accessors")
            return IndexerDecl(
                span=start_span.merge(end_tok.span),
                attributes=attrs,
                access=access,
                modifiers=modifiers,
                type_ref=member_type,
                params=params,
                accessors=accessors,
            )

        name_tok = self._expect_ident("Expected member name")

        # Method declaration: `<TypeParams>? (...)`
        if self._check(TokenKind.LT, TokenKind.LPAREN):
            type_params = self._parse_optional_type_params()
            self._expect(TokenKind.LPAREN, f"Expected '(' in method '{name_tok.lexeme}'")
            params = self._parse_param_list_until_rparen()
            constraints = self._parse_type_constraints()
            body, expr_body, end_span = self._parse_callable_body()
            return MethodDecl(
                span=start_span.merge(end_span),
                attributes=attrs,
                access=access,
                modifiers=modifiers,
                is_constructor=False,
                name=name_tok.lexeme,
                return_type=member_type,
                type_params=type_params,
                params=params,
                constraints=constraints,
                body=body,
                expr_body=expr_body,
            )

        # Property declaration: `{ get; set; } (= expr;)?` or `=> expr;`
        if self._match(TokenKind.LBRACE):
            accessors = self._parse_accessor_list()
            end_tok = self._expect(TokenKind.RBRACE, "Expected '}' after property accessors")
            end_span = end_tok.span
            init_expr: Expr | None = None
            if self._match(TokenKind.ASSIGN):
                init_expr = self.parse_expr()
                semi_tok = self._expect(TokenKind.SEMICOLON, "Expected ';' after property initializer")
                end_span = semi_tok.span
            return PropertyDecl(
                span=start_span.merge(end_span),
                attributes=attrs,
                access=access,
                modifiers=modifiers,
                type_ref=member_type,
                name=name_tok.lexeme,
                accessors=accessors,
                initializer=init_expr,
            )

        if self._match(TokenKind.FAT_ARROW):
            expr_body = self.parse_expr()
            semi_tok = self._expect(TokenKind.SEMICOLON, "Expected ';' after expression-bodied property")
            return PropertyDecl(
                span=start_span.merge(semi_tok.span),
                attributes=attrs,
                access=access,
                modifiers=modifiers,
                type_ref=member_type,
                name=name_tok.lexeme,
                expr_body=expr_body,
            )

        # Field declaration: `(= expr)? ;`
        init_expr = None
        if self._match(TokenKind.ASSIGN):
            init_expr = self.parse_expr()
        semi_tok = self._expect(TokenKind.SEMICOLON, f"Expected ';' after field '{name_tok.lexeme}'")
        return FieldDecl(
            span=start_span.merge(semi_tok.span),
            attributes=attrs,
            access=access,
            modifiers=modifiers,
            type_ref=member_type,
            name=name_tok.lexeme,
            initializer=init_expr,
        )

    def _parse_accessor_list(self) -> list[AccessorDecl]:
        accessors: list[AccessorDecl] = []
        while not self._is_at_end() and not self._check(TokenKind.RBRACE):
            acc_attrs = self.parse_attribute_sections()
            acc_start = acc_attrs[0].span if acc_attrs else self._current().span
            acc_mod: AccessMod | None = None
            if self._current().kind in ACCESS_TOKEN_MAP:
                acc_mod = ACCESS_TOKEN_MAP[self._advance().kind]

            if self._match(TokenKind.GET):
                kind = "get"
            elif self._match(TokenKind.SET):
                kind = "set"
            else:
                tok = self._current()
                self.diagnostics.report_syntax_error(
                    tok.span, f"Expected 'get' or 'set' in property/indexer, found {tok.lexeme!r}"
                )
                self._advance()
                break

            body, expr_body, end_span = self._parse_callable_body()
            accessors.append(
                AccessorDecl(
                    span=acc_start.merge(end_span),
                    access=acc_mod,
                    kind=kind,
                    attributes=acc_attrs,
                    body=body,
                    expr_body=expr_body,
                )
            )
        return accessors

    def _parse_callable_body(self) -> tuple[BlockStmt | None, Expr | None, SourceSpan]:
        if self._match(TokenKind.SEMICOLON):
            return None, None, self._previous().span
        if self._match(TokenKind.FAT_ARROW):
            expr = self.parse_expr()
            semi = self._expect(TokenKind.SEMICOLON, "Expected ';' after expression body")
            return None, expr, semi.span
        block = self.parse_block_stmt()
        return block, None, block.span

    def _parse_param_list_until_rparen(self) -> list[ParamDecl]:
        return self._parse_param_list_until(TokenKind.RPAREN)

    def _parse_param_list_until(self, closing_kind: TokenKind) -> list[ParamDecl]:
        params: list[ParamDecl] = []
        if not self._check(closing_kind):
            params.append(self._parse_param())
            while self._match(TokenKind.COMMA):
                if self._check(closing_kind):
                    break
                params.append(self._parse_param())
        self._expect(closing_kind, f"Expected '{closing_kind.name}' after parameter list")
        return params

    def _parse_param(self) -> ParamDecl:
        attrs = self.parse_attribute_sections()
        start_span = attrs[0].span if attrs else self._current().span
        is_params = self._match(TokenKind.PARAMS)
        ty = self.parse_type_ref()
        name_tok = self._expect_ident("Expected parameter name")
        default_val: Expr | None = None
        if self._match(TokenKind.ASSIGN):
            default_val = self.parse_expr()
        end_span = default_val.span if default_val else name_tok.span
        is_kwargs = any(a.path[-1] in ("KwArgs", "KwArgsAttribute") for a in attrs)
        return ParamDecl(
            span=start_span.merge(end_span),
            attributes=attrs,
            type_ref=ty,
            name=name_tok.lexeme,
            default_value=default_val,
            is_params=is_params,
            is_kwargs_dict=is_kwargs,
        )

    # ========================================================================
    # 6. TYPE REFERENCES (Primitives, Generics, Tuples, Arrays, Nullables)
    # ========================================================================

    def parse_type_ref(self) -> TypeRef:
        start_span = self._current().span

        # Tuple type: `(int Id, string Name)`
        if self._match(TokenKind.LPAREN):
            elements: list[tuple[TypeRef, str | None]] = []
            first_ty = self.parse_type_ref()
            first_name = self._advance().lexeme if self._check_ident_like() else None
            elements.append((first_ty, first_name))
            self._expect(TokenKind.COMMA, "Tuple type requires at least two elements")
            while not self._is_at_end() and not self._check(TokenKind.RPAREN):
                elem_ty = self.parse_type_ref()
                elem_name = self._advance().lexeme if self._check_ident_like() else None
                elements.append((elem_ty, elem_name))
                if not self._match(TokenKind.COMMA):
                    break
            self._expect(TokenKind.RPAREN, "Expected ')' after tuple type")
            is_null = self._match(TokenKind.QUESTION)
            return TypeRef(
                span=start_span.merge(self._previous().span),
                is_nullable=is_null,
                tuple_elements=elements,
            )

        # Primitive keyword type (`int`, `string`, `decimal`, `void`, ...)
        if self._current().kind in PRIMITIVE_TYPE_TOKENS:
            prim_tok = self._advance()
            base_ref = TypeRef(
                span=prim_tok.span,
                is_primitive_keyword=True,
                path=[prim_tok.lexeme],
            )
        else:
            path = [self._expect_ident("Expected type name").lexeme]
            while self._match(TokenKind.DOT):
                path.append(self._expect_ident("Expected identifier in qualified type").lexeme)
            type_args: list[TypeRef] = []
            if self._match(TokenKind.LT):
                type_args.append(self.parse_type_ref())
                while self._match(TokenKind.COMMA):
                    type_args.append(self.parse_type_ref())
                self._expect(TokenKind.GT, "Expected '>' after generic type arguments")
            base_ref = TypeRef(
                span=start_span.merge(self._previous().span),
                is_primitive_keyword=False,
                path=path,
                type_args=type_args,
            )

        # Optional array suffix `T[]` -> normalized to `List<T>`
        while self._check(TokenKind.LBRACKET) and self._peek(1).kind == TokenKind.RBRACKET:
            self._advance()
            rbr = self._advance()
            base_ref = TypeRef(
                span=start_span.merge(rbr.span),
                is_primitive_keyword=False,
                path=["List"],
                type_args=[base_ref],
            )

        # Optional nullable `?`
        if self._match(TokenKind.QUESTION):
            base_ref.is_nullable = True
            base_ref.span = start_span.merge(self._previous().span)

        return base_ref

    # ========================================================================
    # 7. STATEMENTS & CONTROL FLOW
    # ========================================================================

    def parse_block_stmt(self) -> BlockStmt:
        start_tok = self._expect(TokenKind.LBRACE, "Expected '{'")
        stmts: list[Stmt] = []
        while not self._is_at_end() and not self._check(TokenKind.RBRACE):
            stmts.append(self.parse_stmt())
        end_tok = self._expect(TokenKind.RBRACE, "Expected '}'")
        return BlockStmt(span=start_tok.span.merge(end_tok.span), statements=stmts)

    def parse_stmt(self) -> Stmt:
        if self._check(TokenKind.LBRACE):
            return self.parse_block_stmt()

        # `await using ...` or `await foreach ...`
        if self._check(TokenKind.AWAIT) and self._peek(1).kind in (TokenKind.USING, TokenKind.FOREACH):
            await_tok = self._advance()
            if self._match(TokenKind.USING):
                return self._parse_using_resource_stmt(await_tok.span, is_await=True)
            self._expect(TokenKind.FOREACH, "Expected 'foreach'")
            return self._parse_foreach_stmt(await_tok.span, is_await=True)

        if self._match(TokenKind.USING):
            return self._parse_using_resource_stmt(self._previous().span, is_await=False)
        if self._match(TokenKind.IF):
            return self._parse_if_stmt(self._previous().span)
        if self._match(TokenKind.WHILE):
            return self._parse_while_stmt(self._previous().span)
        if self._match(TokenKind.FOREACH):
            return self._parse_foreach_stmt(self._previous().span, is_await=False)
        if self._match(TokenKind.RETURN):
            return self._parse_return_stmt(self._previous().span)
        if self._match(TokenKind.YIELD):
            return self._parse_yield_stmt(self._previous().span)
        if self._match(TokenKind.THROW):
            return self._parse_throw_stmt(self._previous().span)
        if self._match(TokenKind.TRY):
            return self._parse_try_stmt(self._previous().span)
        if self._match(TokenKind.SWITCH):
            return self._parse_switch_stmt(self._previous().span)

        # `var x = expr;`
        if self._match(TokenKind.VAR):
            start_span = self._previous().span
            name_tok = self._expect_ident("Expected variable name after 'var'")
            self._expect(TokenKind.ASSIGN, "Expected '=' in local variable declaration")
            init_expr = self.parse_expr()
            semi_tok = self._expect(TokenKind.SEMICOLON, "Expected ';' after local variable declaration")
            return LocalVarStmt(
                span=start_span.merge(semi_tok.span),
                type_ref=None,
                name=name_tok.lexeme,
                initializer=init_expr,
            )

        # Speculatively check for typed local variable declaration: `TypeRef ident = expr;`
        local_var = self._try_parse_typed_local_var_stmt()
        if local_var is not None:
            return local_var

        # Fallback: Expression statement `expr;`
        expr = self.parse_expr()
        semi_tok = self._expect(TokenKind.SEMICOLON, "Expected ';' after expression")
        return ExprStmt(span=expr.span.merge(semi_tok.span), expr=expr)

    def _try_parse_typed_local_var_stmt(self) -> LocalVarStmt | None:
        if not (
            self._current().kind in PRIMITIVE_TYPE_TOKENS or self._check_ident_like() or self._check(TokenKind.LPAREN)
        ):
            return None

        saved_pos = self.pos
        self._speculative_depth += 1
        try:
            start_span = self._current().span
            ty = self.parse_type_ref()
            if not self._check_ident_like():
                raise _ParseBacktrack()
            name_tok = self._advance()
            if not self._match(TokenKind.ASSIGN):
                raise _ParseBacktrack()
        except _ParseBacktrack:
            self.pos = saved_pos
            return None
        finally:
            self._speculative_depth -= 1

        init_expr = self.parse_expr()
        semi_tok = self._expect(TokenKind.SEMICOLON, "Expected ';' after variable declaration")
        return LocalVarStmt(
            span=start_span.merge(semi_tok.span),
            type_ref=ty,
            name=name_tok.lexeme,
            initializer=init_expr,
        )

    def _parse_using_resource_stmt(self, start_span: SourceSpan, is_await: bool) -> UsingResourceStmt:
        ty: TypeRef | None = None
        if not self._match(TokenKind.VAR):
            ty = self.parse_type_ref()
        name_tok = self._expect_ident("Expected resource variable name in 'using' statement")
        self._expect(TokenKind.ASSIGN, "Expected '=' in 'using' statement")
        init_expr = self.parse_expr()
        semi_tok = self._expect(TokenKind.SEMICOLON, "Expected ';' after 'using' statement")
        return UsingResourceStmt(
            span=start_span.merge(semi_tok.span),
            is_await=is_await,
            type_ref=ty,
            name=name_tok.lexeme,
            initializer=init_expr,
        )

    def _parse_if_stmt(self, start_span: SourceSpan) -> IfStmt:
        self._expect(TokenKind.LPAREN, "Expected '(' after 'if'")
        cond = self.parse_expr()
        self._expect(TokenKind.RPAREN, "Expected ')' after 'if' condition")
        then_branch = self.parse_stmt()
        else_branch: Stmt | None = None
        if self._match(TokenKind.ELSE):
            else_branch = self.parse_stmt()
        end_span = else_branch.span if else_branch else then_branch.span
        return IfStmt(
            span=start_span.merge(end_span),
            condition=cond,
            then_branch=then_branch,
            else_branch=else_branch,
        )

    def _parse_while_stmt(self, start_span: SourceSpan) -> WhileStmt:
        self._expect(TokenKind.LPAREN, "Expected '(' after 'while'")
        cond = self.parse_expr()
        self._expect(TokenKind.RPAREN, "Expected ')' after 'while' condition")
        body = self.parse_stmt()
        return WhileStmt(span=start_span.merge(body.span), condition=cond, body=body)

    def _parse_foreach_stmt(self, start_span: SourceSpan, is_await: bool) -> ForEachStmt:
        self._expect(TokenKind.LPAREN, "Expected '(' after 'foreach'")
        ty: TypeRef | None = None
        if not self._match(TokenKind.VAR):
            ty = self.parse_type_ref()
        item_tok = self._expect_ident("Expected loop variable name in 'foreach'")
        self._expect(TokenKind.IN, "Expected 'in' inside 'foreach'")
        collection = self.parse_expr()
        self._expect(TokenKind.RPAREN, "Expected ')' after 'foreach' header")
        body = self.parse_stmt()
        return ForEachStmt(
            span=start_span.merge(body.span),
            is_await=is_await,
            type_ref=ty,
            item_name=item_tok.lexeme,
            collection=collection,
            body=body,
        )

    def _parse_return_stmt(self, start_span: SourceSpan) -> ReturnStmt:
        val: Expr | None = None
        if not self._check(TokenKind.SEMICOLON):
            val = self.parse_expr()
        semi = self._expect(TokenKind.SEMICOLON, "Expected ';' after return statement")
        return ReturnStmt(span=start_span.merge(semi.span), value=val)

    def _parse_yield_stmt(self, start_span: SourceSpan) -> YieldStmt:
        if self._match(TokenKind.BREAK):
            semi = self._expect(TokenKind.SEMICOLON, "Expected ';' after 'yield break'")
            return YieldStmt(span=start_span.merge(semi.span), is_break=True, value=None)
        self._expect(TokenKind.RETURN, "Expected 'return' or 'break' after 'yield'")
        val = self.parse_expr()
        semi = self._expect(TokenKind.SEMICOLON, "Expected ';' after 'yield return'")
        return YieldStmt(span=start_span.merge(semi.span), is_break=False, value=val)

    def _parse_throw_stmt(self, start_span: SourceSpan) -> ThrowStmt:
        exc: Expr | None = None
        if not self._check(TokenKind.SEMICOLON):
            exc = self.parse_expr()
        semi = self._expect(TokenKind.SEMICOLON, "Expected ';' after throw statement")
        return ThrowStmt(span=start_span.merge(semi.span), exception=exc)

    def _parse_try_stmt(self, start_span: SourceSpan) -> TryCatchFinallyStmt:
        try_block = self.parse_block_stmt()
        catches: list[CatchClause] = []
        while self._match(TokenKind.CATCH):
            c_start = self._previous().span
            exc_type: TypeRef | None = None
            bind_name: str | None = None
            if self._match(TokenKind.LPAREN):
                exc_type = self.parse_type_ref()
                if self._check_ident_like():
                    bind_name = self._advance().lexeme
                self._expect(TokenKind.RPAREN, "Expected ')' after catch declaration")
            when_guard: Expr | None = None
            if self._match(TokenKind.WHEN):
                self._expect(TokenKind.LPAREN, "Expected '(' after 'when'")
                when_guard = self.parse_expr()
                self._expect(TokenKind.RPAREN, "Expected ')' after 'when' guard")
            c_body = self.parse_block_stmt()
            catches.append(
                CatchClause(
                    span=c_start.merge(c_body.span),
                    exception_type=exc_type,
                    bind_name=bind_name,
                    when_guard=when_guard,
                    body=c_body,
                )
            )
        finally_block: BlockStmt | None = None
        if self._match(TokenKind.FINALLY):
            finally_block = self.parse_block_stmt()

        end_span = finally_block.span if finally_block else (catches[-1].span if catches else try_block.span)
        return TryCatchFinallyStmt(
            span=start_span.merge(end_span),
            try_block=try_block,
            catches=catches,
            finally_block=finally_block,
        )

    def _parse_switch_stmt(self, start_span: SourceSpan) -> SwitchStmt:
        self._expect(TokenKind.LPAREN, "Expected '(' after 'switch'")
        scrutinee = self.parse_expr()
        self._expect(TokenKind.RPAREN, "Expected ')' after switch expression")
        self._expect(TokenKind.LBRACE, "Expected '{' to open switch body")

        sections: list[SwitchSection] = []
        while not self._is_at_end() and not self._check(TokenKind.RBRACE):
            sec_start = self._current().span
            labels: list[tuple[PatternNode | None, Expr | None]] = []
            while self._check(TokenKind.CASE, TokenKind.DEFAULT):
                if self._match(TokenKind.CASE):
                    pat = self.parse_pattern()
                    guard: Expr | None = None
                    if self._match(TokenKind.WHEN):
                        guard = self.parse_expr()
                    self._expect(TokenKind.COLON, "Expected ':' after case label")
                    labels.append((pat, guard))
                elif self._match(TokenKind.DEFAULT):
                    self._expect(TokenKind.COLON, "Expected ':' after 'default'")
                    labels.append((None, None))

            stmts: list[Stmt] = []
            while not self._is_at_end() and not self._check(TokenKind.CASE, TokenKind.DEFAULT, TokenKind.RBRACE):
                if self._match(TokenKind.BREAK):
                    self._expect(TokenKind.SEMICOLON, "Expected ';' after 'break'")
                    break
                stmts.append(self.parse_stmt())

            end_span = stmts[-1].span if stmts else self._previous().span
            sections.append(
                SwitchSection(
                    span=sec_start.merge(end_span),
                    labels=labels,
                    statements=stmts,
                )
            )

        end_tok = self._expect(TokenKind.RBRACE, "Expected '}' after switch statement")
        return SwitchStmt(
            span=start_span.merge(end_tok.span),
            scrutinee=scrutinee,
            sections=sections,
        )

    # ========================================================================
    # 8. PATTERNS
    # ========================================================================

    def parse_pattern(self) -> PatternNode:
        start_span = self._current().span

        # Discard pattern `_`
        if self._check(TokenKind.IDENT) and self._current().lexeme == "_":
            tok = self._advance()
            return PatternNode(span=tok.span, kind="Discard")

        # `null` pattern
        if self._match(TokenKind.NULL):
            return PatternNode(span=self._previous().span, kind="Null")

        # Literal pattern (`123`, `"abc"`, `true`, `false`, `-1`)
        if self._check(
            TokenKind.INT_LIT,
            TokenKind.FLOAT_LIT,
            TokenKind.DECIMAL_LIT,
            TokenKind.STRING_LIT,
            TokenKind.TRUE,
            TokenKind.FALSE,
            TokenKind.MINUS,
        ):
            lit_expr = self._parse_unary()
            return PatternNode(span=lit_expr.span, kind="Literal", literal_expr=lit_expr)

        # Type and/or Property pattern: `TypeRef bindIdent? ({ Prop: SubPat, ... })?`
        ty = self.parse_type_ref()
        bind_name: str | None = None
        if self._check_ident_like():
            bind_name = self._advance().lexeme

        prop_pats: list[tuple[str, PatternNode]] = []
        if self._match(TokenKind.LBRACE):
            while not self._is_at_end() and not self._check(TokenKind.RBRACE):
                prop_name = self._expect_ident("Expected property name in pattern").lexeme
                self._expect(TokenKind.COLON, "Expected ':' in property pattern")
                sub_pat = self.parse_pattern()
                prop_pats.append((prop_name, sub_pat))
                if not self._match(TokenKind.COMMA):
                    break
            self._expect(TokenKind.RBRACE, "Expected '}' after property pattern")

        return PatternNode(
            span=start_span.merge(self._previous().span),
            kind="TypePattern",
            type_ref=ty,
            bind_name=bind_name,
            property_subpatterns=prop_pats,
        )

    # ========================================================================
    # 9. EXPRESSIONS (Pratt / Precedence-Climbing + Lambdas, Slices & Switch)
    # ========================================================================

    def parse_expr(self) -> Expr:
        # Check for lambda expression first
        lam = self._try_parse_lambda_expr()
        if lam is not None:
            return lam
        return self._parse_assignment()

    def _try_parse_lambda_expr(self) -> Expr | None:
        saved_pos = self.pos
        self._speculative_depth += 1
        try:
            start_span = self._current().span
            is_async = self._match(TokenKind.ASYNC)

            params: list[LambdaParam] = []
            if self._check_ident_like() and self._peek(1).kind == TokenKind.FAT_ARROW:
                p_tok = self._advance()
                params.append(LambdaParam(span=p_tok.span, name=p_tok.lexeme))
            elif self._match(TokenKind.LPAREN):
                if not self._check(TokenKind.RPAREN):
                    params.append(self._parse_lambda_param())
                    while self._match(TokenKind.COMMA):
                        params.append(self._parse_lambda_param())
                self._expect(TokenKind.RPAREN, "Expected ')' in lambda parameters")
            else:
                raise _ParseBacktrack()

            if not self._match(TokenKind.FAT_ARROW):
                raise _ParseBacktrack()
        except _ParseBacktrack:
            self.pos = saved_pos
            return None
        finally:
            self._speculative_depth -= 1

        if self._check(TokenKind.LBRACE):
            body: BlockStmt | Expr = self.parse_block_stmt()
            end_span = body.span
        else:
            body = self.parse_expr()
            end_span = body.span

        return Expr(
            span=start_span.merge(end_span),
            kind=ExprKind.LAMBDA,
            data={"is_async": is_async, "params": params, "body": body},
        )

    def _parse_lambda_param(self) -> LambdaParam:
        start_span = self._current().span
        if self._check_ident_like() and self._peek(1).kind in (TokenKind.COMMA, TokenKind.RPAREN):
            tok = self._advance()
            return LambdaParam(span=tok.span, name=tok.lexeme)
        ty = self.parse_type_ref()
        name_tok = self._expect_ident("Expected lambda parameter name")
        return LambdaParam(
            span=start_span.merge(name_tok.span),
            name=name_tok.lexeme,
            type_ref=ty,
        )

    def _parse_assignment(self) -> Expr:
        left = self._parse_null_coalesce()
        assign_map: dict[TokenKind, BinaryOp] = {
            TokenKind.ASSIGN: BinaryOp.ASSIGN,
            TokenKind.PLUS_ASSIGN: BinaryOp.ADD_ASSIGN,
            TokenKind.MINUS_ASSIGN: BinaryOp.SUB_ASSIGN,
            TokenKind.STAR_ASSIGN: BinaryOp.MUL_ASSIGN,
            TokenKind.SLASH_ASSIGN: BinaryOp.DIV_ASSIGN,
            TokenKind.NULL_COALESCE_EQ: BinaryOp.NULL_COALESCE_ASSIGN,
        }
        if self._current().kind in assign_map:
            op = assign_map[self._advance().kind]
            right = self.parse_expr()
            return Expr(
                span=left.span.merge(right.span),
                kind=ExprKind.BINARY,
                data={"op": op, "left": left, "right": right},
            )
        return left

    def _parse_null_coalesce(self) -> Expr:
        left = self._parse_logical_or()
        if self._match(TokenKind.NULL_COALESCE):
            right = self._parse_null_coalesce()
            return Expr(
                span=left.span.merge(right.span),
                kind=ExprKind.NULL_COALESCE,
                data={"left": left, "right": right},
            )
        return left

    def _parse_logical_or(self) -> Expr:
        left = self._parse_logical_and()
        while self._match(TokenKind.OR_OR):
            right = self._parse_logical_and()
            left = Expr(
                span=left.span.merge(right.span),
                kind=ExprKind.BINARY,
                data={"op": BinaryOp.OR, "left": left, "right": right},
            )
        return left

    def _parse_logical_and(self) -> Expr:
        left = self._parse_equality()
        while self._match(TokenKind.AND_AND):
            right = self._parse_equality()
            left = Expr(
                span=left.span.merge(right.span),
                kind=ExprKind.BINARY,
                data={"op": BinaryOp.AND, "left": left, "right": right},
            )
        return left

    def _parse_equality(self) -> Expr:
        left = self._parse_relational()
        while self._check(TokenKind.EQ, TokenKind.NEQ):
            tok = self._advance()
            op = BinaryOp.EQ if tok.kind == TokenKind.EQ else BinaryOp.NEQ
            right = self._parse_relational()
            left = Expr(
                span=left.span.merge(right.span),
                kind=ExprKind.BINARY,
                data={"op": op, "left": left, "right": right},
            )
        return left

    def _parse_relational(self) -> Expr:
        left = self._parse_additive()
        rel_map: dict[TokenKind, BinaryOp] = {
            TokenKind.LT: BinaryOp.LT,
            TokenKind.GT: BinaryOp.GT,
            TokenKind.LTE: BinaryOp.LTE,
            TokenKind.GTE: BinaryOp.GTE,
        }
        if self._current().kind in rel_map:
            op = rel_map[self._advance().kind]
            right = self._parse_additive()
            return Expr(
                span=left.span.merge(right.span),
                kind=ExprKind.BINARY,
                data={"op": op, "left": left, "right": right},
            )
        if self._match(TokenKind.IS):
            pat = self.parse_pattern()
            return Expr(
                span=left.span.merge(pat.span),
                kind=ExprKind.TYPE_CHECK_IS,
                data={"target": left, "pattern": pat},
            )
        if self._match(TokenKind.AS):
            ty = self.parse_type_ref()
            return Expr(
                span=left.span.merge(ty.span),
                kind=ExprKind.TYPE_CAST_AS,
                data={"target": left, "type_ref": ty},
            )
        return left

    def _parse_additive(self) -> Expr:
        left = self._parse_multiplicative()
        while self._check(TokenKind.PLUS, TokenKind.MINUS):
            tok = self._advance()
            op = BinaryOp.ADD if tok.kind == TokenKind.PLUS else BinaryOp.SUB
            right = self._parse_multiplicative()
            left = Expr(
                span=left.span.merge(right.span),
                kind=ExprKind.BINARY,
                data={"op": op, "left": left, "right": right},
            )
        return left

    def _parse_multiplicative(self) -> Expr:
        left = self._parse_unary()
        mul_map: dict[TokenKind, BinaryOp] = {
            TokenKind.STAR: BinaryOp.MUL,
            TokenKind.SLASH: BinaryOp.DIV,
            TokenKind.PERCENT: BinaryOp.MOD,
            TokenKind.DOUBLE_STAR: BinaryOp.POW,
        }
        while self._current().kind in mul_map:
            op = mul_map[self._advance().kind]
            right = self._parse_unary()
            left = Expr(
                span=left.span.merge(right.span),
                kind=ExprKind.BINARY,
                data={"op": op, "left": left, "right": right},
            )
        return left

    def _parse_unary(self) -> Expr:
        unary_map: dict[TokenKind, UnaryOp] = {
            TokenKind.BANG: UnaryOp.NOT,
            TokenKind.MINUS: UnaryOp.NEG,
            TokenKind.AWAIT: UnaryOp.AWAIT,
            TokenKind.CARET: UnaryOp.FROM_END,
        }
        if self._current().kind in unary_map:
            op_tok = self._advance()
            operand = self._parse_unary()
            return Expr(
                span=op_tok.span.merge(operand.span),
                kind=ExprKind.UNARY,
                data={"op": unary_map[op_tok.kind], "operand": operand},
            )
        return self._parse_postfix()

    def _parse_postfix(self) -> Expr:
        expr = self._parse_primary()

        while True:
            # Direct call on identifier/primary: `FetchById(userId)`
            if self._match(TokenKind.LPAREN):
                args = self._parse_arg_list_until(TokenKind.RPAREN)
                end_tok = self._expect(TokenKind.RPAREN, "Expected ')' after arguments")
                expr = Expr(
                    span=expr.span.merge(end_tok.span),
                    kind=ExprKind.CALL,
                    data={"callee": expr, "type_args": [], "args": args},
                )
                continue

            # Standard member access or method call: `.Ident<T>?(args)?`
            if self._match(TokenKind.DOT):
                member_tok = self._expect_ident("Expected member name after '.'")
                type_args = self._try_parse_call_type_args()
                if self._match(TokenKind.LPAREN):
                    args = self._parse_arg_list_until(TokenKind.RPAREN)
                    end_tok = self._expect(TokenKind.RPAREN, "Expected ')' after arguments")
                    member_expr = Expr(
                        span=expr.span.merge(member_tok.span),
                        kind=ExprKind.MEMBER_ACCESS,
                        data={"target": expr, "member": member_tok.lexeme},
                    )
                    expr = Expr(
                        span=expr.span.merge(end_tok.span),
                        kind=ExprKind.CALL,
                        data={"callee": member_expr, "type_args": type_args, "args": args},
                    )
                else:
                    expr = Expr(
                        span=expr.span.merge(member_tok.span),
                        kind=ExprKind.MEMBER_ACCESS,
                        data={"target": expr, "member": member_tok.lexeme},
                    )
                continue

            # Null-conditional access: `?.Ident(args)?`
            if self._match(TokenKind.NULL_COND):
                member_tok = self._expect_ident("Expected member name after '?.'")
                type_args = self._try_parse_call_type_args()
                if self._match(TokenKind.LPAREN):
                    args = self._parse_arg_list_until(TokenKind.RPAREN)
                    end_tok = self._expect(TokenKind.RPAREN, "Expected ')' after arguments")
                    expr = Expr(
                        span=expr.span.merge(end_tok.span),
                        kind=ExprKind.NULL_COND_ACCESS,
                        data={
                            "target": expr,
                            "member": member_tok.lexeme,
                            "is_call": True,
                            "type_args": type_args,
                            "args": args,
                        },
                    )
                else:
                    expr = Expr(
                        span=expr.span.merge(member_tok.span),
                        kind=ExprKind.NULL_COND_ACCESS,
                        data={
                            "target": expr,
                            "member": member_tok.lexeme,
                            "is_call": False,
                            "type_args": [],
                            "args": [],
                        },
                    )
                continue

            # Multi-dimensional indexing & slicing: `tensor[1..5, ^2.., ::2]`
            if self._match(TokenKind.LBRACKET):
                dims: list[SliceDimension] = []
                if not self._check(TokenKind.RBRACKET):
                    dims.append(self._parse_slice_dimension())
                    while self._match(TokenKind.COMMA):
                        if self._check(TokenKind.RBRACKET):
                            break
                        dims.append(self._parse_slice_dimension())
                end_tok = self._expect(TokenKind.RBRACKET, "Expected ']' after index/slice")
                expr = Expr(
                    span=expr.span.merge(end_tok.span),
                    kind=ExprKind.INDEX_OR_SLICE,
                    data={"target": expr, "dimensions": dims},
                )
                continue

            # Postfix `switch` expression: `val switch { Pattern => Expr, ... }`
            if self._match(TokenKind.SWITCH):
                self._expect(TokenKind.LBRACE, "Expected '{' in switch expression")
                arms: list[SwitchArm] = []
                while not self._is_at_end() and not self._check(TokenKind.RBRACE):
                    arm_start = self._current().span
                    pat = self.parse_pattern()
                    guard: Expr | None = None
                    if self._match(TokenKind.WHEN):
                        guard = self.parse_expr()
                    self._expect(TokenKind.FAT_ARROW, "Expected '=>' in switch expression arm")
                    res = self.parse_expr()
                    arms.append(
                        SwitchArm(
                            span=arm_start.merge(res.span),
                            pattern=pat,
                            when_guard=guard,
                            result_expr=res,
                        )
                    )
                    if not self._match(TokenKind.COMMA):
                        break
                end_tok = self._expect(TokenKind.RBRACE, "Expected '}' after switch expression")
                expr = Expr(
                    span=expr.span.merge(end_tok.span),
                    kind=ExprKind.SWITCH_EXPR,
                    data={"scrutinee": expr, "arms": arms},
                )
                continue

            break

        return expr

    def _try_parse_call_type_args(self) -> list[TypeRef]:
        if not self._check(TokenKind.LT):
            return []
        saved_pos = self.pos
        self._speculative_depth += 1
        try:
            self._advance()  # '<'
            args = [self.parse_type_ref()]
            while self._match(TokenKind.COMMA):
                args.append(self.parse_type_ref())
            self._expect(TokenKind.GT, "Expected '>'")
            if not self._check(TokenKind.LPAREN):
                raise _ParseBacktrack()
            return args
        except _ParseBacktrack:
            self.pos = saved_pos
            return []
        finally:
            self._speculative_depth -= 1

    def _parse_slice_dimension(self) -> SliceDimension:
        """Parses `expr`, `start?..stop?(:step?)`, or `start?:stop?(:step?)`."""
        start_span = self._current().span
        start_expr: Expr | None = None
        stop_expr: Expr | None = None
        step_expr: Expr | None = None

        if not self._check(TokenKind.DOT_DOT, TokenKind.COLON):
            start_expr = self.parse_expr()

        if self._match(TokenKind.DOT_DOT) or self._match(TokenKind.COLON):
            if not self._check(TokenKind.COLON, TokenKind.COMMA, TokenKind.RBRACKET):
                stop_expr = self.parse_expr()
            if self._match(TokenKind.COLON):
                if not self._check(TokenKind.COMMA, TokenKind.RBRACKET):
                    step_expr = self.parse_expr()
            end_span = step_expr.span if step_expr else (stop_expr.span if stop_expr else self._previous().span)
            return SliceDimension(
                span=start_span.merge(end_span),
                is_range_or_slice=True,
                start=start_expr,
                stop=stop_expr,
                step=step_expr,
            )

        assert start_expr is not None
        return SliceDimension(
            span=start_expr.span,
            is_range_or_slice=False,
            single_expr=start_expr,
        )

    def _parse_arg_list_until(self, closing_kind: TokenKind) -> list[ArgNode]:
        args: list[ArgNode] = []
        if not self._check(closing_kind):
            args.append(self._parse_arg())
            while self._match(TokenKind.COMMA):
                if self._check(closing_kind):
                    break
                args.append(self._parse_arg())
        return args

    def _parse_arg(self) -> ArgNode:
        start_span = self._current().span
        kw_name: str | None = None
        if self._check_ident_like() and self._peek(1).kind == TokenKind.COLON:
            kw_name = self._advance().lexeme
            self._advance()  # Consume ':'
        val = self.parse_expr()
        return ArgNode(span=start_span.merge(val.span), name=kw_name, expr=val)

    def _parse_primary(self) -> Expr:
        tok = self._current()

        if self._match(TokenKind.INT_LIT):
            return Expr(
                span=tok.span,
                kind=ExprKind.LITERAL,
                data={"literal_kind": LiteralKind.INT, "value": int(tok.lexeme)},
            )
        if self._match(TokenKind.FLOAT_LIT):
            return Expr(
                span=tok.span,
                kind=ExprKind.LITERAL,
                data={"literal_kind": LiteralKind.FLOAT, "value": float(tok.lexeme)},
            )
        if self._match(TokenKind.DECIMAL_LIT):
            return Expr(
                span=tok.span,
                kind=ExprKind.LITERAL,
                data={"literal_kind": LiteralKind.DECIMAL, "value": tok.lexeme},
            )
        if self._match(TokenKind.STRING_LIT):
            return Expr(
                span=tok.span,
                kind=ExprKind.LITERAL,
                data={"literal_kind": LiteralKind.STRING, "value": tok.lexeme},
            )
        if self._match(TokenKind.INTERP_STRING):
            parts = self._parse_interpolated_parts(tok)
            return Expr(
                span=tok.span,
                kind=ExprKind.INTERP_STRING,
                data={"parts": parts},
            )
        if self._match(TokenKind.TRUE):
            return Expr(
                span=tok.span,
                kind=ExprKind.LITERAL,
                data={"literal_kind": LiteralKind.BOOL, "value": True},
            )
        if self._match(TokenKind.FALSE):
            return Expr(
                span=tok.span,
                kind=ExprKind.LITERAL,
                data={"literal_kind": LiteralKind.BOOL, "value": False},
            )
        if self._match(TokenKind.NULL):
            return Expr(
                span=tok.span,
                kind=ExprKind.LITERAL,
                data={"literal_kind": LiteralKind.NULL, "value": None},
            )
        if self._match(TokenKind.DEFAULT):
            return Expr(
                span=tok.span,
                kind=ExprKind.LITERAL,
                data={"literal_kind": LiteralKind.DEFAULT, "value": None},
            )
        if self._match(TokenKind.THIS):
            return Expr(span=tok.span, kind=ExprKind.THIS)
        if self._match(TokenKind.BASE):
            return Expr(span=tok.span, kind=ExprKind.BASE)

        # `new TypeRef(args) { Prop = val }`
        if self._match(TokenKind.NEW):
            ty = self.parse_type_ref()
            args: list[ArgNode] = []
            if self._match(TokenKind.LPAREN):
                args = self._parse_arg_list_until(TokenKind.RPAREN)
                self._expect(TokenKind.RPAREN, "Expected ')' after constructor arguments")
            init_props: list[tuple[str, Expr]] = []
            if self._match(TokenKind.LBRACE):
                while not self._is_at_end() and not self._check(TokenKind.RBRACE):
                    prop_name = self._expect_ident("Expected property name in object initializer").lexeme
                    self._expect(TokenKind.ASSIGN, "Expected '=' in object initializer")
                    prop_val = self.parse_expr()
                    init_props.append((prop_name, prop_val))
                    if not self._match(TokenKind.COMMA):
                        break
                self._expect(TokenKind.RBRACE, "Expected '}' after object initializer")
            return Expr(
                span=tok.span.merge(self._previous().span),
                kind=ExprKind.NEW_OBJECT,
                data={"type_ref": ty, "args": args, "initializers": init_props},
            )

        # List literal: `[expr1, expr2]`
        if self._match(TokenKind.LBRACKET):
            items: list[Expr] = []
            if not self._check(TokenKind.RBRACKET):
                items.append(self.parse_expr())
                while self._match(TokenKind.COMMA):
                    if self._check(TokenKind.RBRACKET):
                        break
                    items.append(self.parse_expr())
            end_tok = self._expect(TokenKind.RBRACKET, "Expected ']' after list literal")
            return Expr(
                span=tok.span.merge(end_tok.span),
                kind=ExprKind.LIST_LITERAL,
                data={"elements": items},
            )

        # Parenthesized expression `(expr)` or Tuple literal `(a, b)`
        if self._match(TokenKind.LPAREN):
            first = self.parse_expr()
            if self._match(TokenKind.COMMA):
                items = [first]
                if not self._check(TokenKind.RPAREN):
                    items.append(self.parse_expr())
                    while self._match(TokenKind.COMMA):
                        if self._check(TokenKind.RPAREN):
                            break
                        items.append(self.parse_expr())
                end_tok = self._expect(TokenKind.RPAREN, "Expected ')' after tuple literal")
                return Expr(
                    span=tok.span.merge(end_tok.span),
                    kind=ExprKind.TUPLE_LITERAL,
                    data={"elements": items},
                )
            end_tok = self._expect(TokenKind.RPAREN, "Expected ')' after expression")
            first.span = tok.span.merge(end_tok.span)
            return first

        # Identifier or built-in type name used for static member access (`string.Join(...)`)
        if self._check_ident_like() or self._current().kind in PRIMITIVE_TYPE_TOKENS:
            id_tok = self._advance()
            return Expr(
                span=id_tok.span,
                kind=ExprKind.IDENT,
                data={"name": id_tok.lexeme},
            )

        if self._speculative_depth > 0:
            raise _ParseBacktrack()

        self.diagnostics.report_syntax_error(tok.span, f"Unexpected token {tok.lexeme!r} in expression")
        self._advance()
        return Expr(span=tok.span, kind=ExprKind.LITERAL, data={"literal_kind": LiteralKind.NULL, "value": None})

    def _parse_interpolated_parts(self, interp_tok: Token) -> list[InterpolatedPart]:
        raw = interp_tok.lexeme
        parts: list[InterpolatedPart] = []
        buf: list[str] = []
        i = 0
        n = len(raw)

        while i < n:
            if raw[i] == "{" and i + 1 < n and raw[i + 1] == "{":
                buf.append("{")
                i += 2
                continue
            if raw[i] == "}" and i + 1 < n and raw[i + 1] == "}":
                buf.append("}")
                i += 2
                continue
            if raw[i] == "{":
                if buf:
                    parts.append(InterpolatedPart(is_expr=False, text="".join(buf)))
                    buf.clear()
                i += 1
                depth = 1
                expr_chars: list[str] = []
                while i < n and depth > 0:
                    if raw[i] == "{":
                        depth += 1
                    elif raw[i] == "}":
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                    expr_chars.append(raw[i])
                    i += 1
                sub_source = "".join(expr_chars).strip()
                sub_parser = Parser.from_source(
                    sub_source,
                    file_id=interp_tok.span.file_id,
                    ps_filename=interp_tok.span.ps_filename,
                    diagnostics=self.diagnostics,
                )
                sub_expr = sub_parser.parse_expr()
                parts.append(InterpolatedPart(is_expr=True, expr=sub_expr))
                continue
            buf.append(raw[i])
            i += 1

        if buf:
            parts.append(InterpolatedPart(is_expr=False, text="".join(buf)))
        return parts
