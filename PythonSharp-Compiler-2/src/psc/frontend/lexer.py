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

        eof_span = SourceSpan(self.file_id, self.ps_filename, self.line, self.col, self.line, self.col)
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

        # Hexadecimal literal 0x...
        if self._peek() == "0" and self._peek_next() in ("x", "X"):
            chars.append(self._advance())  # '0'
            chars.append(self._advance())  # 'x'
            while not self._is_at_end() and (self._peek().isalnum() or self._peek() == "_"):
                ch = self._advance()
                if ch != "_":
                    chars.append(ch)
            return Token(TokenKind.INT_LIT, "".join(chars), self._make_span(start_line, start_col))

        # Binary literal 0b...
        if self._peek() == "0" and self._peek_next() in ("b", "B"):
            chars.append(self._advance())  # '0'
            chars.append(self._advance())  # 'b'
            while not self._is_at_end() and (self._peek() in ("0", "1", "_")):
                ch = self._advance()
                if ch != "_":
                    chars.append(ch)
            return Token(TokenKind.INT_LIT, "".join(chars), self._make_span(start_line, start_col))

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
            "<<": TokenKind.LSHIFT,
            ">>": TokenKind.RSHIFT,
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
            "&": TokenKind.AMP,
            "|": TokenKind.PIPE,
            "~": TokenKind.TILDE,
        }
        if ch in one_char_map:
            return Token(one_char_map[ch], ch, self._make_span(start_line, start_col))

        span = self._make_span(start_line, start_col)
        self.diagnostics.report_syntax_error(span, f"Unexpected character {ch!r}.")
        return None
