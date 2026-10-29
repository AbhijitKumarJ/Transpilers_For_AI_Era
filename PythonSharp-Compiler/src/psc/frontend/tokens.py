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
    DECIMAL_LIT = auto()  # e.g., 10.0m
    STRING_LIT = auto()  # e.g., "hello"
    INTERP_STRING = auto()  # e.g., $"Order {id}: {total}"

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
    CONTINUE = auto()
    THROW = auto()
    TRY = auto()
    CATCH = auto()
    FINALLY = auto()
    IS = auto()

    # Delimiters
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    LBRACE = auto()  # {
    RBRACE = auto()  # }
    LBRACKET = auto()  # [
    RBRACKET = auto()  # ]
    SEMICOLON = auto()  # ;
    COMMA = auto()  # ,
    DOT = auto()  # .
    COLON = auto()  # :
    QUESTION = auto()  # ?

    # Multi-character & Special Operators
    DOT_DOT = auto()  # ..
    CARET = auto()  # ^
    NULL_COALESCE = auto()  # ??
    NULL_COALESCE_EQ = auto()  # ??=
    NULL_COND = auto()  # ?.
    FAT_ARROW = auto()  # =>
    DOUBLE_STAR = auto()  # **

    # Standard Operators
    ASSIGN = auto()  # =
    PLUS_ASSIGN = auto()  # +=
    MINUS_ASSIGN = auto()  # -=
    STAR_ASSIGN = auto()  # *=
    SLASH_ASSIGN = auto()  # /=
    EQ = auto()  # ==
    NEQ = auto()  # !=
    LT = auto()  # <
    GT = auto()  # >
    LTE = auto()  # <=
    GTE = auto()  # >=
    AND_AND = auto()  # &&
    OR_OR = auto()  # ||
    BANG = auto()  # !
    PLUS = auto()  # +
    MINUS = auto()  # -
    STAR = auto()  # *
    SLASH = auto()  # /
    PERCENT = auto()  # %


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
    "continue": TokenKind.CONTINUE,
    "throw": TokenKind.THROW,
    "try": TokenKind.TRY,
    "catch": TokenKind.CATCH,
    "finally": TokenKind.FINALLY,
    "is": TokenKind.IS,
}

PRIMITIVE_TYPE_TOKENS: frozenset[TokenKind] = frozenset(
    {
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
    }
)


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    lexeme: str
    span: SourceSpan

    def __repr__(self) -> str:
        return f"Token({self.kind.name}, {self.lexeme!r}, {self.span.format_location()})"
