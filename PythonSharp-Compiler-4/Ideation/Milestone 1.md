Start creating raw individual files for milestone 1, don't try to wrap it in a file generation script, just give the files individually in plain text





Here are the raw individual source files for **Milestone 1 (Frontend Foundation: Diagnostics, Tokens, Lexer, Multi-Pass AST Nodes, Recursive-Descent/Pratt Parser, and Unit Tests)** of the **PythonSharp Prototype Transpiler (`psc`)**.

---

### 1. `src/psc/diagnostics.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Tracks exact 1-indexed line and column positions in the original .ps/.d.ps file."""
    file_id: int
    ps_filename: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def merge(self, other: SourceSpan) -> SourceSpan:
        return SourceSpan(
            file_id=self.file_id,
            ps_filename=self.ps_filename,
            start_line=self.start_line,
            start_col=self.start_col,
            end_line=other.end_line,
            end_col=other.end_col,
        )

    def format_location(self) -> str:
        return f"{self.ps_filename}:{self.start_line}:{self.start_col}"


@dataclass(slots=True)
class Diagnostic:
    code: str
    severity: Literal["ERROR", "WARNING"]
    message: str
    span: SourceSpan

    def __str__(self) -> str:
        return f"{self.severity} [{self.code}] at {self.span.format_location()}: {self.message}"


@dataclass(slots=True)
class DiagnosticEngine:
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def report_syntax_error(self, span: SourceSpan, message: str) -> None:
        self.diagnostics.append(
            Diagnostic(code="PS000", severity="ERROR", message=message, span=span)
        )

    def report_ps001_access_violation(
        self, span: SourceSpan, member_name: str, access_mod: str, owner_type: str
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                code="PS001",
                severity="ERROR",
                message=(
                    f"Member '{owner_type}.{member_name}' is '{access_mod}' and cannot "
                    f"be accessed from this context."
                ),
                span=span,
            )
        )

    def report_ps002_ambiguous_overload(
        self, span: SourceSpan, method_name: str, sig_a: str, sig_b: str, erased_py_type: str
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                code="PS002",
                severity="ERROR",
                message=(
                    f"Overloads '{sig_a}' and '{sig_b}' on '{method_name}' erase to "
                    f"identical Python runtime type '{erased_py_type}' at the same arity."
                ),
                span=span,
            )
        )

    def report_ps003_circular_static_init(self, span: SourceSpan, cycle_path: str) -> None:
        self.diagnostics.append(
            Diagnostic(
                code="PS003",
                severity="ERROR",
                message=f"Circular static initializer cycle detected: {cycle_path}",
                span=span,
            )
        )

    def report_ps004_native_compile_dynamic(self, span: SourceSpan, type_name: str) -> None:
        self.diagnostics.append(
            Diagnostic(
                code="PS004",
                severity="ERROR",
                message=(
                    f"Type '{type_name}' is marked [NativeCompile] and cannot use 'dynamic'."
                ),
                span=span,
            )
        )

    def has_errors(self) -> bool:
        return any(d.severity == "ERROR" for d in self.diagnostics)

    def format_all(self) -> str:
        return "\n".join(str(d) for d in self.diagnostics)

```

---

### 2. `src/psc/frontend/__init__.py`

```python
from psc.frontend.tokens import Token, TokenKind, KEYWORDS
from psc.frontend.lexer import Lexer
from psc.frontend.ast_nodes import (
    AccessMod,
    AccessorDecl,
    ArgNode,
    AttributeArg,
    AttributeNode,
    BinaryOp,
    BlockStmt,
    CatchClause,
    ClassEmissionStrategy,
    CompilationUnit,
    ComprehensionKind,
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
    MemberLoweringMode,
    MethodDecl,
    OverloadDispatchGroup,
    OverloadGuard,
    ParamDecl,
    PatternNode,
    PropertyDecl,
    ReturnStmt,
    RuntimeTypeCheck,
    SliceDimension,
    Stmt,
    SwitchArm,
    SwitchSection,
    SwitchStmt,
    SymbolId,
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
from psc.frontend.parser import Parser

__all__ = [
    "Token",
    "TokenKind",
    "KEYWORDS",
    "Lexer",
    "Parser",
    "AccessMod",
    "AccessorDecl",
    "ArgNode",
    "AttributeArg",
    "AttributeNode",
    "BinaryOp",
    "BlockStmt",
    "CatchClause",
    "ClassEmissionStrategy",
    "CompilationUnit",
    "ComprehensionKind",
    "ConstructorChain",
    "EnumMember",
    "Expr",
    "ExprKind",
    "ExprStmt",
    "FieldDecl",
    "ForEachStmt",
    "IfStmt",
    "ImportDecl",
    "IndexerDecl",
    "InterpolatedPart",
    "LambdaParam",
    "LiteralKind",
    "LocalVarStmt",
    "MemberDecl",
    "MemberLoweringMode",
    "MethodDecl",
    "OverloadDispatchGroup",
    "OverloadGuard",
    "ParamDecl",
    "PatternNode",
    "PropertyDecl",
    "ReturnStmt",
    "RuntimeTypeCheck",
    "SliceDimension",
    "Stmt",
    "SwitchArm",
    "SwitchSection",
    "SwitchStmt",
    "SymbolId",
    "ThrowStmt",
    "TryCatchFinallyStmt",
    "TypeConstraint",
    "TypeDecl",
    "TypeKind",
    "TypeRef",
    "UnaryOp",
    "UsingResourceStmt",
    "WhileStmt",
    "YieldStmt",
]

```

---

### 3. `src/psc/frontend/tokens.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from psc.diagnostics import SourceSpan


class TokenKind(Enum):
    # End of file
    EOF = auto()

    # Identifiers & Literals
    IDENT = auto()
    INT_LIT = auto()
    FLOAT_LIT = auto()
    DECIMAL_LIT = auto()      # e.g., 10.0m
    STRING_LIT = auto()       # e.g., "hello"
    INTERP_STRING = auto()    # e.g., $"Order {id}: {total}"

    # Keywords — Module & Imports
    NAMESPACE = auto()
    USING = auto()
    EXTERN = auto()
    AS = auto()

    # Keywords — Access Modifiers
    PUBLIC = auto()
    INTERNAL = auto()
    PROTECTED = auto()
    PRIVATE = auto()

    # Keywords — Type & Member Modifiers
    CLASS = auto()
    RECORD = auto()
    STRUCT = auto()
    INTERFACE = auto()
    ENUM = auto()
    PRIMITIVE = auto()
    ABSTRACT = auto()
    SEALED = auto()
    PARTIAL = auto()
    STATIC = auto()
    READONLY = auto()
    VIRTUAL = auto()
    OVERRIDE = auto()
    ASYNC = auto()
    AWAIT = auto()
    WHERE = auto()
    PARAMS = auto()

    # Keywords — Contextual & OOP
    GET = auto()
    SET = auto()
    THIS = auto()
    BASE = auto()
    NEW = auto()
    VAR = auto()
    DEFAULT = auto()

    # Keywords — Built-in Primitive Types
    VOID = auto()
    BOOL = auto()
    INT = auto()
    LONG = auto()
    FLOAT = auto()
    DOUBLE = auto()
    DECIMAL = auto()
    STRING = auto()
    OBJECT = auto()
    DYNAMIC = auto()

    # Keywords — Literals & Constants
    TRUE = auto()
    FALSE = auto()
    NULL = auto()

    # Keywords — Control Flow
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOREACH = auto()
    IN = auto()
    SWITCH = auto()
    CASE = auto()
    WHEN = auto()
    RETURN = auto()
    YIELD = auto()
    BREAK = auto()
    THROW = auto()
    TRY = auto()
    CATCH = auto()
    FINALLY = auto()
    IS = auto()

    # Delimiters
    LPAREN = auto()           # (
    RPAREN = auto()           # )
    LBRACE = auto()           # {
    RBRACE = auto()           # }
    LBRACKET = auto()         # [
    RBRACKET = auto()         # ]
    SEMICOLON = auto()        # ;
    COMMA = auto()            # ,
    DOT = auto()              # .
    COLON = auto()            # :
    QUESTION = auto()         # ?

    # Multi-character & Special Operators
    DOT_DOT = auto()          # ..
    CARET = auto()            # ^
    NULL_COALESCE = auto()    # ??
    NULL_COALESCE_EQ = auto() # ??=
    NULL_COND = auto()        # ?.
    FAT_ARROW = auto()        # =>
    DOUBLE_STAR = auto()      # **

    # Standard Operators
    ASSIGN = auto()           # =
    PLUS_ASSIGN = auto()      # +=
    MINUS_ASSIGN = auto()     # -=
    STAR_ASSIGN = auto()      # *=
    SLASH_ASSIGN = auto()     # /=
    EQ = auto()               # ==
    NEQ = auto()              # !=
    LT = auto()               # <
    GT = auto()               # >
    LTE = auto()              # <=
    GTE = auto()              # >=
    AND_AND = auto()          # &&
    OR_OR = auto()            # ||
    BANG = auto()             # !
    PLUS = auto()             # +
    MINUS = auto()            # -
    STAR = auto()             # *
    SLASH = auto()            # /
    PERCENT = auto()          # %


KEYWORDS: dict[str, TokenKind] = {
    "namespace": TokenKind.NAMESPACE,
    "using": TokenKind.USING,
    "extern": TokenKind.EXTERN,
    "as": TokenKind.AS,
    "public": TokenKind.PUBLIC,
    "internal": TokenKind.INTERNAL,
    "protected": TokenKind.PROTECTED,
    "private": TokenKind.PRIVATE,
    "class": TokenKind.CLASS,
    "record": TokenKind.RECORD,
    "struct": TokenKind.STRUCT,
    "interface": TokenKind.INTERFACE,
    "enum": TokenKind.ENUM,
    "primitive": TokenKind.PRIMITIVE,
    "abstract": TokenKind.ABSTRACT,
    "sealed": TokenKind.SEALED,
    "partial": TokenKind.PARTIAL,
    "static": TokenKind.STATIC,
    "readonly": TokenKind.READONLY,
    "virtual": TokenKind.VIRTUAL,
    "override": TokenKind.OVERRIDE,
    "async": TokenKind.ASYNC,
    "await": TokenKind.AWAIT,
    "where": TokenKind.WHERE,
    "params": TokenKind.PARAMS,
    "get": TokenKind.GET,
    "set": TokenKind.SET,
    "this": TokenKind.THIS,
    "base": TokenKind.BASE,
    "new": TokenKind.NEW,
    "var": TokenKind.VAR,
    "default": TokenKind.DEFAULT,
    "void": TokenKind.VOID,
    "bool": TokenKind.BOOL,
    "int": TokenKind.INT,
    "long": TokenKind.LONG,
    "float": TokenKind.FLOAT,
    "double": TokenKind.DOUBLE,
    "decimal": TokenKind.DECIMAL,
    "string": TokenKind.STRING,
    "object": TokenKind.OBJECT,
    "dynamic": TokenKind.DYNAMIC,
    "true": TokenKind.TRUE,
    "false": TokenKind.FALSE,
    "null": TokenKind.NULL,
    "if": TokenKind.IF,
    "else": TokenKind.ELSE,
    "while": TokenKind.WHILE,
    "foreach": TokenKind.FOREACH,
    "in": TokenKind.IN,
    "switch": TokenKind.SWITCH,
    "case": TokenKind.CASE,
    "when": TokenKind.WHEN,
    "return": TokenKind.RETURN,
    "yield": TokenKind.YIELD,
    "break": TokenKind.BREAK,
    "throw": TokenKind.THROW,
    "try": TokenKind.TRY,
    "catch": TokenKind.CATCH,
    "finally": TokenKind.FINALLY,
    "is": TokenKind.IS,
}

PRIMITIVE_TYPE_TOKENS: frozenset[TokenKind] = frozenset({
    TokenKind.VOID,
    TokenKind.BOOL,
    TokenKind.INT,
    TokenKind.LONG,
    TokenKind.FLOAT,
    TokenKind.DOUBLE,
    TokenKind.DECIMAL,
    TokenKind.STRING,
    TokenKind.OBJECT,
    TokenKind.DYNAMIC,
})


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    lexeme: str
    span: SourceSpan

    def __repr__(self) -> str:
        return f"Token({self.kind.name}, {self.lexeme!r}, {self.span.format_location()})"

```

---

### 4. `src/psc/frontend/lexer.py`

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine, SourceSpan
from psc.frontend.tokens import KEYWORDS, Token, TokenKind


class Lexer:
    """Hand-written UTF-8 lexer for PythonSharp (.ps and .d.ps) source files."""

    def __init__(
        self,
        source: str,
        file_id: int = 0,
        ps_filename: str = "<input>.ps",
        diagnostics: DiagnosticEngine | None = None,
    ) -> None:
        self.source = source
        self.file_id = file_id
        self.ps_filename = ps_filename
        self.diagnostics = diagnostics if diagnostics is not None else DiagnosticEngine()
        self.pos = 0
        self.line = 1
        self.col = 1
        self.length = len(source)

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while not self._is_at_end():
            self._skip_whitespace_and_comments()
            if self._is_at_end():
                break

            start_line = self.line
            start_col = self.col
            ch = self._peek()

            # Interpolated string literal: $"..."
            if ch == "$" and self._peek_next() == '"':
                tokens.append(self._lex_interpolated_string(start_line, start_col))
                continue

            # Standard string literal: "..."
            if ch == '"':
                tokens.append(self._lex_string(start_line, start_col))
                continue

            # Identifiers and keywords (supporting @verbatim identifiers)
            if ch.isalpha() or ch == "_" or (ch == "@" and (self._peek_next().isalpha() or self._peek_next() == "_")):
                tokens.append(self._lex_identifier_or_keyword(start_line, start_col))
                continue

            # Numeric literals (int, float, and decimal with 'm'/'M')
            if ch.isdigit():
                tokens.append(self._lex_number(start_line, start_col))
                continue

            # Punctuation and operators
            tok = self._lex_operator_or_delimiter(start_line, start_col)
            if tok is not None:
                tokens.append(tok)

        eof_span = SourceSpan(
            self.file_id, self.ps_filename, self.line, self.col, self.line, self.col
        )
        tokens.append(Token(TokenKind.EOF, "", eof_span))
        return tokens

    def _is_at_end(self) -> bool:
        return self.pos >= self.length

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= self.length:
            return "\0"
        return self.source[idx]

    def _peek_next(self) -> str:
        return self._peek(1)

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _make_span(self, start_line: int, start_col: int) -> SourceSpan:
        return SourceSpan(
            file_id=self.file_id,
            ps_filename=self.ps_filename,
            start_line=start_line,
            start_col=start_col,
            end_line=self.line,
            end_col=self.col,
        )

    def _skip_whitespace_and_comments(self) -> None:
        while not self._is_at_end():
            ch = self._peek()
            if ch in (" ", "\t", "\r", "\n"):
                self._advance()
            elif ch == "/" and self._peek_next() == "/":
                # Single-line comment
                while not self._is_at_end() and self._peek() != "\n":
                    self._advance()
            elif ch == "/" and self._peek_next() == "*":
                # Multi-line comment
                start_line, start_col = self.line, self.col
                self._advance()
                self._advance()
                while not self._is_at_end():
                    if self._peek() == "*" and self._peek_next() == "/":
                        self._advance()
                        self._advance()
                        break
                    self._advance()
                else:
                    self.diagnostics.report_syntax_error(
                        self._make_span(start_line, start_col),
                        "Unterminated multi-line comment.",
                    )
            else:
                break

    def _lex_string(self, start_line: int, start_col: int) -> Token:
        self._advance()  # Consume opening '"'
        chars: list[str] = []
        while not self._is_at_end() and self._peek() != '"':
            ch = self._advance()
            if ch == "\\":
                if self._is_at_end():
                    break
                esc = self._advance()
                escape_map = {
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                    '"': '"',
                    "\\": "\\",
                    "0": "\0",
                }
                chars.append(escape_map.get(esc, esc))
            else:
                chars.append(ch)

        if self._is_at_end():
            span = self._make_span(start_line, start_col)
            self.diagnostics.report_syntax_error(span, "Unterminated string literal.")
            return Token(TokenKind.STRING_LIT, "".join(chars), span)

        self._advance()  # Consume closing '"'
        return Token(TokenKind.STRING_LIT, "".join(chars), self._make_span(start_line, start_col))

    def _lex_interpolated_string(self, start_line: int, start_col: int) -> Token:
        self._advance()  # Consume '$'
        self._advance()  # Consume opening '"'
        chars: list[str] = []
        brace_depth = 0

        while not self._is_at_end():
            ch = self._peek()
            if ch == '"' and brace_depth == 0:
                self._advance()  # Consume closing '"'
                return Token(
                    TokenKind.INTERP_STRING,
                    "".join(chars),
                    self._make_span(start_line, start_col),
                )
            if ch == "\\":
                self._advance()
                if not self._is_at_end():
                    esc = self._advance()
                    chars.append("\\" + esc)
                continue
            if ch == "{":
                if self._peek_next() == "{":
                    self._advance()
                    self._advance()
                    chars.append("{{")
                    continue
                brace_depth += 1
            elif ch == "}":
                if self._peek_next() == "}" and brace_depth == 0:
                    self._advance()
                    self._advance()
                    chars.append("}}")
                    continue
                if brace_depth > 0:
                    brace_depth -= 1
            chars.append(self._advance())

        span = self._make_span(start_line, start_col)
        self.diagnostics.report_syntax_error(span, "Unterminated interpolated string literal.")
        return Token(TokenKind.INTERP_STRING, "".join(chars), span)

    def _lex_identifier_or_keyword(self, start_line: int, start_col: int) -> Token:
        is_verbatim = False
        if self._peek() == "@":
            is_verbatim = True
            self._advance()

        chars: list[str] = []
        while not self._is_at_end() and (self._peek().isalnum() or self._peek() == "_"):
            chars.append(self._advance())

        ident = "".join(chars)
        span = self._make_span(start_line, start_col)
        if not is_verbatim and ident in KEYWORDS:
            return Token(KEYWORDS[ident], ident, span)
        return Token(TokenKind.IDENT, ident, span)

    def _lex_number(self, start_line: int, start_col: int) -> Token:
        chars: list[str] = []
        is_float = False

        while not self._is_at_end() and (self._peek().isdigit() or self._peek() == "_"):
            ch = self._advance()
            if ch != "_":
                chars.append(ch)

        # Check fractional part, ensuring we do not consume '..' range slice operator!
        if self._peek() == "." and self._peek_next().isdigit():
            is_float = True
            chars.append(self._advance())  # '.'
            while not self._is_at_end() and (self._peek().isdigit() or self._peek() == "_"):
                ch = self._advance()
                if ch != "_":
                    chars.append(ch)

        # Check for decimal suffix 'm' or 'M'
        if self._peek() in ("m", "M"):
            self._advance()
            return Token(
                TokenKind.DECIMAL_LIT,
                "".join(chars),
                self._make_span(start_line, start_col),
            )

        # Check for optional float suffix 'f', 'F', 'd', 'D'
        if self._peek() in ("f", "F", "d", "D"):
            self._advance()
            is_float = True

        kind = TokenKind.FLOAT_LIT if is_float else TokenKind.INT_LIT
        return Token(kind, "".join(chars), self._make_span(start_line, start_col))

    def _lex_operator_or_delimiter(self, start_line: int, start_col: int) -> Token | None:
        ch = self._advance()
        nxt = self._peek()

        # 3-character operators
        if ch == "?" and nxt == "?" and self._peek(1) == "=":
            self._advance()
            self._advance()
            return Token(TokenKind.NULL_COALESCE_EQ, "??=", self._make_span(start_line, start_col))

        # 2-character operators
        two_char_map: dict[str, TokenKind] = {
            "..": TokenKind.DOT_DOT,
            "??": TokenKind.NULL_COALESCE,
            "?.": TokenKind.NULL_COND,
            "=>": TokenKind.FAT_ARROW,
            "**": TokenKind.DOUBLE_STAR,
            "+=": TokenKind.PLUS_ASSIGN,
            "-=": TokenKind.MINUS_ASSIGN,
            "*=": TokenKind.STAR_ASSIGN,
            "/=": TokenKind.SLASH_ASSIGN,
            "==": TokenKind.EQ,
            "!=": TokenKind.NEQ,
            "<=": TokenKind.LTE,
            ">=": TokenKind.GTE,
            "&&": TokenKind.AND_AND,
            "||": TokenKind.OR_OR,
        }
        pair = ch + nxt
        if pair in two_char_map:
            self._advance()
            return Token(two_char_map[pair], pair, self._make_span(start_line, start_col))

        # 1-character operators & delimiters
        one_char_map: dict[str, TokenKind] = {
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            "{": TokenKind.LBRACE,
            "}": TokenKind.RBRACE,
            "[": TokenKind.LBRACKET,
            "]": TokenKind.RBRACKET,
            ";": TokenKind.SEMICOLON,
            ",": TokenKind.COMMA,
            ".": TokenKind.DOT,
            ":": TokenKind.COLON,
            "?": TokenKind.QUESTION,
            "^": TokenKind.CARET,
            "=": TokenKind.ASSIGN,
            "<": TokenKind.LT,
            ">": TokenKind.GT,
            "!": TokenKind.BANG,
            "+": TokenKind.PLUS,
            "-": TokenKind.MINUS,
            "*": TokenKind.STAR,
            "/": TokenKind.SLASH,
            "%": TokenKind.PERCENT,
        }
        if ch in one_char_map:
            return Token(one_char_map[ch], ch, self._make_span(start_line, start_col))

        span = self._make_span(start_line, start_col)
        self.diagnostics.report_syntax_error(span, f"Unexpected character {ch!r}.")
        return None

```

---

### 5. `src/psc/frontend/ast_nodes.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from psc.diagnostics import SourceSpan


# ============================================================================
# 1. SYMBOL ID & PASS 2 SEMANTIC SLOTS
# ============================================================================

@dataclass(frozen=True, slots=True)
class SymbolId:
    value: int


class AccessMod(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PROTECTED = "protected"
    PRIVATE = "private"


class TypeKind(Enum):
    CLASS = auto()
    PRIMITIVE_CLASS = auto()
    RECORD = auto()
    RECORD_STRUCT = auto()
    STRUCT = auto()
    PRIMITIVE_STRUCT = auto()
    INTERFACE = auto()
    PRIMITIVE_INTERFACE = auto()
    ENUM = auto()


@dataclass(slots=True)
class ClassEmissionStrategy:
    """Populated in Pass 2 to instruct Pass 3 how to emit a TypeDecl."""
    kind: str = "Unresolved"  # Unresolved | ErasedPrimitive | SlottedClass | SlottedDataclass | SchemaModel | NativeCompiledClass
    py_runtime_type: str | None = None
    own_slots: list[str] = field(default_factory=list)
    ps_types_tuple: list[str] = field(default_factory=list)
    generates_context_manager: bool = False
    generates_async_context_manager: bool = False
    is_frozen_dataclass: bool = False


@dataclass(slots=True)
class RuntimeTypeCheck:
    kind: str = "NoneRequired"  # NoneRequired | PyIsInstance | PsTypesContains
    target_type: str = ""


@dataclass(slots=True)
class OverloadGuard:
    min_arity: int = 0
    max_arity: int = 0
    param_type_checks: list[tuple[int, RuntimeTypeCheck]] = field(default_factory=list)


@dataclass(slots=True)
class MemberLoweringMode:
    """Populated in Pass 2 for every method/property/indexer declaration and call site."""
    kind: str = "Unresolved"  # Unresolved | StandardPython | OverloadedVariant | PrimitiveDirect | PrimitiveInlineTemplate
    emitted_snake_name: str = ""
    overload_index: int = 0
    runtime_guard: OverloadGuard | None = None
    py_target_name: str = ""
    inline_template: str = ""


@dataclass(slots=True)
class OverloadDispatchGroup:
    snake_name: str
    variants: list[SymbolId] = field(default_factory=list)
    is_strictly_arity_disjoint: bool = True


class ComprehensionKind(Enum):
    LIST = auto()
    SET = auto()
    DICT = auto()
    GENERATOR = auto()
    ANY = auto()
    ALL = auto()
    FIRST_OR_DEFAULT = auto()
    SUM = auto()
    COUNT = auto()
    MIN = auto()
    MAX = auto()


# ============================================================================
# 2. COMPILATION UNIT, IMPORTS, ATTRIBUTES & TYPE REFERENCES
# ============================================================================

@dataclass(slots=True)
class ImportDecl:
    span: SourceSpan
    is_extern: bool
    path: list[str]
    alias: str | None = None


@dataclass(slots=True)
class AttributeArg:
    span: SourceSpan
    name: str | None
    expr: Expr


@dataclass(slots=True)
class AttributeNode:
    span: SourceSpan
    path: list[str]
    args: list[AttributeArg] = field(default_factory=list)


@dataclass(slots=True)
class TypeRef:
    span: SourceSpan
    is_nullable: bool = False
    is_primitive_keyword: bool = False
    path: list[str] = field(default_factory=list)
    type_args: list[TypeRef] = field(default_factory=list)
    tuple_elements: list[tuple[TypeRef, str | None]] = field(default_factory=list)

    def display_name(self) -> str:
        if self.tuple_elements:
            inner = ", ".join(
                f"{t.display_name()} {n}" if n else t.display_name()
                for t, n in self.tuple_elements
            )
            base = f"({inner})"
        else:
            base = ".".join(self.path)
            if self.type_args:
                args_str = ", ".join(arg.display_name() for arg in self.type_args)
                base = f"{base}<{args_str}>"
        return f"{base}?" if self.is_nullable else base


@dataclass(slots=True)
class TypeConstraint:
    span: SourceSpan
    type_param: str
    bounds: list[TypeRef] = field(default_factory=list)


# ============================================================================
# 3. TOP-LEVEL TYPE DECLARATIONS & MEMBERS
# ============================================================================

@dataclass(slots=True)
class CompilationUnit:
    file_id: int
    ps_filename: str
    is_ambient_stub: bool
    namespace: list[str]
    imports: list[ImportDecl]
    types: list[TypeDecl]
    # Pass 2 slot
    emitted_py_module_path: str = ""


@dataclass(slots=True)
class TypeDecl:
    span: SourceSpan
    attributes: list[AttributeNode]
    access: AccessMod
    modifiers: list[str]
    kind: TypeKind
    name: str
    type_params: list[str] = field(default_factory=list)
    primary_ctor_params: list[ParamDecl] = field(default_factory=list)
    base_types: list[TypeRef] = field(default_factory=list)
    constraints: list[TypeConstraint] = field(default_factory=list)
    members: list[MemberDecl] = field(default_factory=list)
    enum_members: list[EnumMember] = field(default_factory=list)

    # Pass 2 Semantic Slots
    symbol_id: SymbolId | None = None
    emission_strategy: ClassEmissionStrategy = field(default_factory=ClassEmissionStrategy)
    overload_groups: list[OverloadDispatchGroup] = field(default_factory=list)
    topological_order_rank: int = 0
    decorators_to_emit: list[Expr] = field(default_factory=list)


@dataclass(slots=True)
class EnumMember:
    span: SourceSpan
    attributes: list[AttributeNode]
    name: str
    value: Expr | None = None


@dataclass(slots=True)
class ParamDecl:
    span: SourceSpan
    attributes: list[AttributeNode]
    type_ref: TypeRef
    name: str
    default_value: Expr | None = None
    is_params: bool = False
    # Pass 2 Slots
    symbol_id: SymbolId | None = None
    emitted_snake_name: str = ""
    is_kwargs_dict: bool = False


@dataclass(slots=True)
class AccessorDecl:
    span: SourceSpan
    access: AccessMod | None
    kind: str  # "get" | "set"
    attributes: list[AttributeNode] = field(default_factory=list)
    body: BlockStmt | None = None
    expr_body: Expr | None = None


@dataclass(slots=True)
class FieldDecl:
    span: SourceSpan
    attributes: list[AttributeNode]
    access: AccessMod
    modifiers: list[str]
    type_ref: TypeRef
    name: str
    initializer: Expr | None = None
    # Pass 2 Slots
    symbol_id: SymbolId | None = None
    emitted_snake_name: str = ""


@dataclass(slots=True)
class PropertyDecl:
    span: SourceSpan
    attributes: list[AttributeNode]
    access: AccessMod
    modifiers: list[str]
    type_ref: TypeRef
    name: str
    accessors: list[AccessorDecl] = field(default_factory=list)
    expr_body: Expr | None = None
    initializer: Expr | None = None
    # Pass 2 Slots
    symbol_id: SymbolId | None = None
    backing_slot_name: str | None = None
    emitted_snake_name: str = ""
    lowering_mode: MemberLoweringMode = field(default_factory=MemberLoweringMode)


@dataclass(slots=True)
class IndexerDecl:
    span: SourceSpan
    attributes: list[AttributeNode]
    access: AccessMod
    modifiers: list[str]
    type_ref: TypeRef
    params: list[ParamDecl]
    accessors: list[AccessorDecl]
    # Pass 2 Slots
    symbol_id: SymbolId | None = None
    lowering_mode: MemberLoweringMode = field(default_factory=MemberLoweringMode)


@dataclass(slots=True)
class ConstructorChain:
    span: SourceSpan
    target: str  # "base" | "this"
    args: list[ArgNode] = field(default_factory=list)


@dataclass(slots=True)
class MethodDecl:
    span: SourceSpan
    attributes: list[AttributeNode]
    access: AccessMod
    modifiers: list[str]
    is_constructor: bool
    name: str
    return_type: TypeRef | None
    type_params: list[str] = field(default_factory=list)
    params: list[ParamDecl] = field(default_factory=list)
    constraints: list[TypeConstraint] = field(default_factory=list)
    ctor_chain: ConstructorChain | None = None
    body: BlockStmt | None = None
    expr_body: Expr | None = None
    # Pass 2 Slots
    symbol_id: SymbolId | None = None
    lowering_mode: MemberLoweringMode = field(default_factory=MemberLoweringMode)
    is_generator: bool = False
    decorators_to_emit: list[Expr] = field(default_factory=list)


MemberDecl = FieldDecl | PropertyDecl | IndexerDecl | MethodDecl


# ============================================================================
# 4. STATEMENTS & PATTERNS
# ============================================================================

@dataclass(slots=True)
class PatternNode:
    span: SourceSpan
    kind: str  # "Discard" | "Null" | "Literal" | "TypePattern"
    literal_expr: Expr | None = None
    type_ref: TypeRef | None = None
    bind_name: str | None = None
    property_subpatterns: list[tuple[str, PatternNode]] = field(default_factory=list)


@dataclass(slots=True)
class BlockStmt:
    span: SourceSpan
    statements: list[Stmt] = field(default_factory=list)


@dataclass(slots=True)
class LocalVarStmt:
    span: SourceSpan
    type_ref: TypeRef | None  # None when declared with `var`
    name: str
    initializer: Expr


@dataclass(slots=True)
class UsingResourceStmt:
    span: SourceSpan
    is_await: bool
    type_ref: TypeRef | None
    name: str
    initializer: Expr


@dataclass(slots=True)
class IfStmt:
    span: SourceSpan
    condition: Expr
    then_branch: Stmt
    else_branch: Stmt | None = None


@dataclass(slots=True)
class WhileStmt:
    span: SourceSpan
    condition: Expr
    body: Stmt


@dataclass(slots=True)
class ForEachStmt:
    span: SourceSpan
    is_await: bool
    type_ref: TypeRef | None
    item_name: str
    collection: Expr
    body: Stmt


@dataclass(slots=True)
class ReturnStmt:
    span: SourceSpan
    value: Expr | None = None


@dataclass(slots=True)
class YieldStmt:
    span: SourceSpan
    is_break: bool
    value: Expr | None = None


@dataclass(slots=True)
class ThrowStmt:
    span: SourceSpan
    exception: Expr | None = None


@dataclass(slots=True)
class CatchClause:
    span: SourceSpan
    exception_type: TypeRef | None = None
    bind_name: str | None = None
    when_guard: Expr | None = None
    body: BlockStmt | None = None


@dataclass(slots=True)
class TryCatchFinallyStmt:
    span: SourceSpan
    try_block: BlockStmt
    catches: list[CatchClause] = field(default_factory=list)
    finally_block: BlockStmt | None = None


@dataclass(slots=True)
class SwitchSection:
    span: SourceSpan
    labels: list[tuple[PatternNode | None, Expr | None]]  # None pattern == `default:`
    statements: list[Stmt] = field(default_factory=list)


@dataclass(slots=True)
class SwitchStmt:
    span: SourceSpan
    scrutinee: Expr
    sections: list[SwitchSection] = field(default_factory=list)


@dataclass(slots=True)
class ExprStmt:
    span: SourceSpan
    expr: Expr


Stmt = (
    BlockStmt
    | LocalVarStmt
    | UsingResourceStmt
    | IfStmt
    | WhileStmt
    | ForEachStmt
    | ReturnStmt
    | YieldStmt
    | ThrowStmt
    | TryCatchFinallyStmt
    | SwitchStmt
    | ExprStmt
)


# ============================================================================
# 5. EXPRESSIONS, SLICING, LAMBDAS & LINQ COMPREHENSIONS
# ============================================================================

class LiteralKind(Enum):
    INT = auto()
    FLOAT = auto()
    DECIMAL = auto()
    STRING = auto()
    BOOL = auto()
    NULL = auto()
    DEFAULT = auto()


class UnaryOp(Enum):
    NOT = "!"
    NEG = "-"
    AWAIT = "await"
    FROM_END = "^"


class BinaryOp(Enum):
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    MOD = "%"
    POW = "**"
    EQ = "=="
    NEQ = "!="
    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="
    AND = "&&"
    OR = "||"
    ASSIGN = "="
    ADD_ASSIGN = "+="
    SUB_ASSIGN = "-="
    MUL_ASSIGN = "*="
    DIV_ASSIGN = "/="
    NULL_COALESCE_ASSIGN = "??="


@dataclass(slots=True)
class ArgNode:
    span: SourceSpan
    name: str | None
    expr: Expr


@dataclass(slots=True)
class SliceDimension:
    span: SourceSpan
    is_range_or_slice: bool
    single_expr: Expr | None = None
    start: Expr | None = None
    stop: Expr | None = None
    step: Expr | None = None


@dataclass(slots=True)
class InterpolatedPart:
    is_expr: bool
    text: str = ""
    expr: Expr | None = None


@dataclass(slots=True)
class LambdaParam:
    span: SourceSpan
    name: str
    type_ref: TypeRef | None = None


@dataclass(slots=True)
class SwitchArm:
    span: SourceSpan
    pattern: PatternNode
    when_guard: Expr | None
    result_expr: Expr


class ExprKind(Enum):
    LITERAL = auto()
    INTERP_STRING = auto()
    IDENT = auto()
    THIS = auto()
    BASE = auto()
    UNARY = auto()
    BINARY = auto()
    NULL_COALESCE = auto()
    MEMBER_ACCESS = auto()
    NULL_COND_ACCESS = auto()
    CALL = auto()
    INDEX_OR_SLICE = auto()
    NEW_OBJECT = auto()
    LIST_LITERAL = auto()
    TUPLE_LITERAL = auto()
    TYPE_CHECK_IS = auto()
    TYPE_CAST_AS = auto()
    LAMBDA = auto()
    SWITCH_EXPR = auto()
    LINQ_COMPREHENSION = auto()  # Fused by Pass 2


@dataclass(slots=True)
class Expr:
    span: SourceSpan
    kind: ExprKind
    data: dict[str, Any] = field(default_factory=dict)
    # Pass 2 Semantic Slots
    resolved_type: str | None = None
    resolved_lowering: MemberLoweringMode | None = None

```

---

### 6. `src/psc/frontend/parser.py`

```python
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

MODIFIER_TOKENS: frozenset[TokenKind] = frozenset({
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
})


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

    def _parse_access_and_modifiers(
        self, default_access: AccessMod
    ) -> tuple[AccessMod, list[str]]:
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

    def parse_member_decl(
        self, enclosing_type_name: str, in_interface: bool = False
    ) -> MemberDecl:
        attrs = self.parse_attribute_sections()
        start_span = attrs[0].span if attrs else self._current().span
        default_acc = AccessMod.PUBLIC if in_interface else AccessMod.PRIVATE
        access, modifiers = self._parse_access_and_modifiers(default_access=default_acc)

        # Constructor check: `<EnclosingTypeName>(...)`
        if (
            self._current().lexeme == enclosing_type_name
            and self._peek(1).kind == TokenKind.LPAREN
        ):
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
            end_tok = self._expect(TokenKind.RPAREN, "Expected ')' after tuple type")
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
            self._current().kind in PRIMITIVE_TYPE_TOKENS
            or self._check_ident_like()
            or self._check(TokenKind.LPAREN)
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

        end_span = (
            finally_block.span
            if finally_block
            else (catches[-1].span if catches else try_block.span)
        )
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
            while not self._is_at_end() and not self._check(
                TokenKind.CASE, TokenKind.DEFAULT, TokenKind.RBRACE
            ):
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
                data={"expr": left, "pattern": pat},
            )
        if self._match(TokenKind.AS):
            ty = self.parse_type_ref()
            return Expr(
                span=left.span.merge(ty.span),
                kind=ExprKind.TYPE_CAST_AS,
                data={"expr": left, "type_ref": ty},
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
            end_span = (
                step_expr.span
                if step_expr
                else (stop_expr.span if stop_expr else self._previous().span)
            )
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

        self.diagnostics.report_syntax_error(
            tok.span, f"Unexpected token {tok.lexeme!r} in expression"
        )
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

```

---

### 7. `tests/test_lexer_parser.py`

```python
from __future__ import annotations
from psc.diagnostics import DiagnosticEngine
from psc.frontend import (
    AccessMod,
    ExprKind,
    LiteralKind,
    LocalVarStmt,
    MethodDecl,
    Parser,
    PropertyDecl,
    TypeKind,
    UsingResourceStmt,
)


def test_parse_core_stdlib_primitive_declarations() -> None:
    source = """
    namespace PythonSharp.Core;

    extern using collections.abc as abc;

    [MapsTo("dict")]
    [RuntimeType("dict")]
    public primitive class Dict<TKey, TValue> : IEnumerable<KeyValuePair<TKey, TValue>>
    {
        [InlineTemplate("{}")]
        public extern Dict();

        [InlineTemplate("len({self})")]
        public extern int Count { get; }

        [MapsTo("get")]
        public extern TValue? GetOrDefault(TKey key, TValue? defaultValue = default);

        [InlineTemplate("({0} in {self})")]
        public extern bool ContainsKey(TKey key);

        [InlineTemplate("{self}[{0}]")]
        public extern TValue this[TKey key]
        {
            get;
            [InlineTemplate("{self}[{0}] = {value}")] set;
        }
    }
    """
    diag = DiagnosticEngine()
    parser = Parser.from_source(source, ps_filename="PythonSharp.Core.d.ps", diagnostics=diag)
    unit = parser.parse_compilation_unit()

    assert not diag.has_errors(), diag.format_all()
    assert unit.is_ambient_stub is True
    assert unit.namespace == ["PythonSharp", "Core"]
    assert len(unit.imports) == 1
    assert unit.imports[0].is_extern is True
    assert unit.imports[0].path == ["collections", "abc"]
    assert unit.imports[0].alias == "abc"

    assert len(unit.types) == 1
    dict_decl = unit.types[0]
    assert dict_decl.kind == TypeKind.PRIMITIVE_CLASS
    assert dict_decl.name == "Dict"
    assert dict_decl.type_params == ["TKey", "TValue"]
    assert len(dict_decl.attributes) == 2
    assert dict_decl.attributes[0].path == ["MapsTo"]
    assert len(dict_decl.members) == 5


def test_parse_order_cache_with_overloads_linq_and_disposable() -> None:
    source = """
    namespace Commerce.Services;

    using PythonSharp.Core;

    public interface IAuditable { string AuditTag { get; } }

    public record Order(int Id, decimal Total, bool IsActive);

    public class OrderCache : IAuditable, IDisposable
    {
        private readonly Dict<int, Order> _store = new Dict<int, Order>();
        public string AuditTag { get; private set; }

        public OrderCache(string tag) => AuditTag = tag;

        public void Put(Order order) => _store[order.Id] = order;
        public void Put(int id, decimal total) => _store[id] = new Order(id, total, true);

        public List<int> GetActiveIds(decimal minTotal = 0.0m)
        {
            return _store.Values()
                .Where(o => o.IsActive && o.Total >= minTotal)
                .Select(o => o.Id)
                .ToList();
        }

        public void Dispose() => _store.Clear();
    }
    """
    diag = DiagnosticEngine()
    parser = Parser.from_source(source, ps_filename="Services/OrderCache.ps", diagnostics=diag)
    unit = parser.parse_compilation_unit()

    assert not diag.has_errors(), diag.format_all()
    assert unit.namespace == ["Commerce", "Services"]
    assert len(unit.types) == 3

    iface, rec, cache = unit.types
    assert iface.kind == TypeKind.INTERFACE
    assert rec.kind == TypeKind.RECORD
    assert [p.name for p in rec.primary_ctor_params] == ["Id", "Total", "IsActive"]

    assert cache.kind == TypeKind.CLASS
    assert [b.display_name() for b in cache.base_types] == ["IAuditable", "IDisposable"]

    prop = next(m for m in cache.members if isinstance(m, PropertyDecl))
    assert prop.name == "AuditTag"
    assert prop.access == AccessMod.PUBLIC
    assert prop.accessors[1].kind == "set"
    assert prop.accessors[1].access == AccessMod.PRIVATE

    puts = [m for m in cache.members if isinstance(m, MethodDecl) and m.name == "Put"]
    assert len(puts) == 2
    assert len(puts[0].params) == 1
    assert len(puts[1].params) == 2

    # Verify exact source line tracking on GetActiveIds
    get_active = next(
        m for m in cache.members if isinstance(m, MethodDecl) and m.name == "GetActiveIds"
    )
    assert get_active.span.ps_filename == "Services/OrderCache.ps"
    assert get_active.params[0].default_value is not None
    assert get_active.params[0].default_value.data["literal_kind"] == LiteralKind.DECIMAL


def test_parse_multidimensional_slices_null_safety_and_switch_expr() -> None:
    source = """
    namespace ML.Pipelines;

    public class TensorOps
    {
        public void Run(Tensor tensor, User? user)
        {
            using var scope = new GradScope();
            var slice = tensor[1..5, ^2.., ::2];
            var name = user?.Profile?.Name ?? "Anonymous";
            var label = name switch
            {
                "Anonymous" => $"Guest-{1 + 1}",
                string s when s.Length > 5 => s,
                _ => "Short"
            };
        }
    }
    """
    diag = DiagnosticEngine()
    parser = Parser.from_source(source, ps_filename="TensorOps.ps", diagnostics=diag)
    unit = parser.parse_compilation_unit()

    assert not diag.has_errors(), diag.format_all()
    run_method = unit.types[0].members[0]
    assert isinstance(run_method, MethodDecl)
    assert run_method.body is not None

    stmts = run_method.body.statements
    assert len(stmts) == 4
    assert isinstance(stmts[0], UsingResourceStmt)

    # Check multi-axis tensor slice `tensor[1..5, ^2.., ::2]`
    slice_stmt = stmts[1]
    assert isinstance(slice_stmt, LocalVarStmt)
    assert slice_stmt.initializer.kind == ExprKind.INDEX_OR_SLICE
    dims = slice_stmt.initializer.data["dimensions"]
    assert len(dims) == 3
    assert dims[0].is_range_or_slice is True
    assert dims[1].is_range_or_slice is True
    assert dims[2].is_range_or_slice is True
    assert dims[2].step is not None

    # Check `??` and `?.`
    null_stmt = stmts[2]
    assert isinstance(null_stmt, LocalVarStmt)
    assert null_stmt.initializer.kind == ExprKind.NULL_COALESCE

    # Check `switch` expression and interpolated string `$"Guest-{1 + 1}"`
    switch_stmt = stmts[3]
    assert isinstance(switch_stmt, LocalVarStmt)
    assert switch_stmt.initializer.kind == ExprKind.SWITCH_EXPR
    arms = switch_stmt.initializer.data["arms"]
    assert len(arms) == 3
    assert arms[0].result_expr.kind == ExprKind.INTERP_STRING

```

---

Want me to proceed with the raw files for **Milestone 2 (Pass 1: `GlobalSymbolTable`, `SymbolCollector`, Virtual Namespace Aggregator, and Circular Type Reference Resolver)** next?








