from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend import Lexer, TokenKind


def _lex(source: str, filename: str = "LexerTest.ps") -> tuple[list[TokenKind], DiagnosticEngine]:
    diagnostics = DiagnosticEngine()
    tokens = Lexer(source, file_id=3, ps_filename=filename, diagnostics=diagnostics).tokenize()
    return [token.kind for token in tokens], diagnostics


def test_lexer_recognizes_all_punctuation_and_operators() -> None:
    source = "( ) { } [ ] ; , . : ? .. ^ ?? ??= ?. => ** = += -= *= /= == != < > <= >= && || ! + - * / %"

    kinds, diagnostics = _lex(source)

    assert not diagnostics.has_errors()
    assert kinds == [
        TokenKind.LPAREN,
        TokenKind.RPAREN,
        TokenKind.LBRACE,
        TokenKind.RBRACE,
        TokenKind.LBRACKET,
        TokenKind.RBRACKET,
        TokenKind.SEMICOLON,
        TokenKind.COMMA,
        TokenKind.DOT,
        TokenKind.COLON,
        TokenKind.QUESTION,
        TokenKind.DOT_DOT,
        TokenKind.CARET,
        TokenKind.NULL_COALESCE,
        TokenKind.NULL_COALESCE_EQ,
        TokenKind.NULL_COND,
        TokenKind.FAT_ARROW,
        TokenKind.DOUBLE_STAR,
        TokenKind.ASSIGN,
        TokenKind.PLUS_ASSIGN,
        TokenKind.MINUS_ASSIGN,
        TokenKind.STAR_ASSIGN,
        TokenKind.SLASH_ASSIGN,
        TokenKind.EQ,
        TokenKind.NEQ,
        TokenKind.LT,
        TokenKind.GT,
        TokenKind.LTE,
        TokenKind.GTE,
        TokenKind.AND_AND,
        TokenKind.OR_OR,
        TokenKind.BANG,
        TokenKind.PLUS,
        TokenKind.MINUS,
        TokenKind.STAR,
        TokenKind.SLASH,
        TokenKind.PERCENT,
        TokenKind.EOF,
    ]


def test_lexer_recognizes_keywords_and_verbatim_identifiers() -> None:
    source = "namespace class record @class @namespace normal_ident"

    tokens = Lexer(source, ps_filename="LexerTest.ps").tokenize()

    assert [token.kind for token in tokens] == [
        TokenKind.NAMESPACE,
        TokenKind.CLASS,
        TokenKind.RECORD,
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.IDENT,
        TokenKind.EOF,
    ]
    assert [token.lexeme for token in tokens[:-1]] == [
        "namespace",
        "class",
        "record",
        "class",
        "namespace",
        "normal_ident",
    ]


def test_lexer_handles_numeric_literals_and_distinguishes_ranges() -> None:
    source = "1_000 3.14 10.5m 2f 3.5D 1..5"

    tokens = Lexer(source, ps_filename="LexerTest.ps").tokenize()

    assert [token.kind for token in tokens] == [
        TokenKind.INT_LIT,
        TokenKind.FLOAT_LIT,
        TokenKind.DECIMAL_LIT,
        TokenKind.FLOAT_LIT,
        TokenKind.FLOAT_LIT,
        TokenKind.INT_LIT,
        TokenKind.DOT_DOT,
        TokenKind.INT_LIT,
        TokenKind.EOF,
    ]
    assert [token.lexeme for token in tokens[:-1]] == ["1000", "3.14", "10.5", "2", "3.5", "1", "..", "5"]


def test_lexer_decodes_string_escapes() -> None:
    source = r'"line\nnext\t\"quoted\"\\\0\q"'

    tokens = Lexer(source, ps_filename="LexerTest.ps").tokenize()

    assert tokens[0].kind == TokenKind.STRING_LIT
    assert tokens[0].lexeme == 'line\nnext\t"quoted"\\\0q'


def test_lexer_reports_unterminated_string() -> None:
    kinds, diagnostics = _lex('"unterminated')

    assert kinds == [TokenKind.STRING_LIT, TokenKind.EOF]
    assert diagnostics.has_errors()
    assert "Unterminated string literal." in diagnostics.format_all()


def test_lexer_handles_interpolated_strings_with_braces_and_escapes() -> None:
    source = r'$"Hello {{name}} {user.Name} {{ and }} \n"'

    tokens = Lexer(source, ps_filename="LexerTest.ps").tokenize()

    assert tokens[0].kind == TokenKind.INTERP_STRING
    assert tokens[0].lexeme == r"Hello {{name}} {user.Name} {{ and }} \n"


def test_lexer_reports_unterminated_interpolated_string() -> None:
    kinds, diagnostics = _lex('$"Hello {name}')

    assert kinds == [TokenKind.INTERP_STRING, TokenKind.EOF]
    assert diagnostics.has_errors()
    assert "Unterminated interpolated string literal." in diagnostics.format_all()


def test_lexer_skips_line_and_block_comments() -> None:
    source = """
    // line comment
    int /* block
    comment */ value; /* trailing */
    """

    tokens = Lexer(source, ps_filename="LexerTest.ps").tokenize()

    assert [token.kind for token in tokens] == [
        TokenKind.INT,
        TokenKind.IDENT,
        TokenKind.SEMICOLON,
        TokenKind.EOF,
    ]


def test_lexer_reports_unterminated_block_comment() -> None:
    kinds, diagnostics = _lex("int /* never closed")

    assert kinds == [TokenKind.INT, TokenKind.EOF]
    assert diagnostics.has_errors()
    assert "Unterminated multi-line comment." in diagnostics.format_all()


def test_lexer_reports_unexpected_character_and_continues() -> None:
    kinds, diagnostics = _lex("int # value;")

    assert kinds == [TokenKind.INT, TokenKind.IDENT, TokenKind.SEMICOLON, TokenKind.EOF]
    assert diagnostics.has_errors()
    assert "Unexpected character '#'." in diagnostics.format_all()


def test_lexer_tracks_exact_line_and_column_spans_including_eof() -> None:
    tokens = Lexer("foo\n  bar", file_id=9, ps_filename="Span.ps").tokenize()

    assert tokens[0].span.start_line == 1
    assert tokens[0].span.start_col == 1
    assert tokens[0].span.end_col == 4
    assert tokens[1].span.start_line == 2
    assert tokens[1].span.start_col == 3
    assert tokens[1].span.end_col == 6
    assert tokens[-1].kind == TokenKind.EOF
    assert tokens[-1].span.start_line == 2
    assert tokens[-1].span.start_col == 6
    assert tokens[-1].span.file_id == 9
    assert tokens[-1].span.ps_filename == "Span.ps"
