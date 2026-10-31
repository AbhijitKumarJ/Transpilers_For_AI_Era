use crate::diagnostics::{DiagnosticEngine, SourceSpan};
use crate::frontend::tokens::{InterpPart, Token, TokenKind};

/// Hand-written UTF-8 lexer for RustSharp (`.rsharp` and `.d.rsharp`) source files.
pub struct Lexer<'a> {
    chars: Vec<char>,
    file_id: usize,
    filename: String,
    pos: usize,
    line: u32,
    col: u32,
    diag: &'a mut DiagnosticEngine,
}

impl<'a> Lexer<'a> {
    pub fn new(
        source: &str,
        file_id: usize,
        filename: impl Into<String>,
        diag: &'a mut DiagnosticEngine,
    ) -> Self {
        Self {
            chars: source.chars().collect(),
            file_id,
            filename: filename.into(),
            pos: 0,
            line: 1,
            col: 1,
            diag,
        }
    }

    pub fn tokenize(&mut self) -> Vec<Token> {
        let mut tokens = Vec::new();

        while !self.is_at_end() {
            self.skip_whitespace_and_comments();
            if self.is_at_end() {
                break;
            }

            let start_line = self.line;
            let start_col = self.col;
            let ch = self.peek(0);

            // Interpolated string: $"..."
            if ch == '$' && self.peek(1) == '"' {
                tokens.push(self.lex_interpolated_string(start_line, start_col));
                continue;
            }

            // Standard string literal: "..."
            if ch == '"' {
                tokens.push(self.lex_string(start_line, start_col));
                continue;
            }

            // Character literal: 'a'
            if ch == '\'' {
                tokens.push(self.lex_char(start_line, start_col));
                continue;
            }

            // Identifiers and keywords (including @verbatim identifiers)
            if ch.is_alphabetic()
                || ch == '_'
                || (ch == '@' && (self.peek(1).is_alphabetic() || self.peek(1) == '_'))
            {
                tokens.push(self.lex_ident_or_keyword(start_line, start_col));
                continue;
            }

            // Numeric literals (int, float, decimal `10.0m`)
            if ch.is_ascii_digit() {
                tokens.push(self.lex_number(start_line, start_col));
                continue;
            }

            // Operators and delimiters
            if let Some(tok) = self.lex_operator_or_delimiter(start_line, start_col) {
                tokens.push(tok);
            }
        }

        let eof_span = self.make_span(self.line, self.col);
        tokens.push(Token::new(TokenKind::Eof, "", eof_span));
        tokens
    }

    fn is_at_end(&self) -> bool {
        self.pos >= self.chars.len()
    }

    fn peek(&self, offset: usize) -> char {
        self.chars.get(self.pos + offset).copied().unwrap_or('\0')
    }

    fn advance(&mut self) -> char {
        let ch = self.chars[self.pos];
        self.pos += 1;
        if ch == '\n' {
            self.line += 1;
            self.col = 1;
        } else {
            self.col += 1;
        }
        ch
    }

    fn make_span(&self, start_line: u32, start_col: u32) -> SourceSpan {
        SourceSpan::new(
            self.file_id,
            &self.filename,
            start_line,
            start_col,
            self.line,
            self.col,
        )
    }

    fn skip_whitespace_and_comments(&mut self) {
        while !self.is_at_end() {
            let ch = self.peek(0);
            if ch.is_whitespace() {
                self.advance();
            } else if ch == '/' && self.peek(1) == '/' {
                while !self.is_at_end() && self.peek(0) != '\n' {
                    self.advance();
                }
            } else if ch == '/' && self.peek(1) == '*' {
                let start_line = self.line;
                let start_col = self.col;
                self.advance();
                self.advance();
                let mut closed = false;
                while !self.is_at_end() {
                    if self.peek(0) == '*' && self.peek(1) == '/' {
                        self.advance();
                        self.advance();
                        closed = true;
                        break;
                    }
                    self.advance();
                }
                if !closed {
                    let span = self.make_span(start_line, start_col);
                    self.diag
                        .report_syntax_error(span, "Unterminated multi-line comment.");
                }
            } else {
                break;
            }
        }
    }

    fn lex_string(&mut self, start_line: u32, start_col: u32) -> Token {
        self.advance(); // consume opening '"'
        let mut buf = String::new();

        while !self.is_at_end() && self.peek(0) != '"' {
            let ch = self.advance();
            if ch == '\\' && !self.is_at_end() {
                let esc = self.advance();
                match esc {
                    'n' => buf.push('\n'),
                    'r' => buf.push('\r'),
                    't' => buf.push('\t'),
                    '"' => buf.push('"'),
                    '\\' => buf.push('\\'),
                    '0' => buf.push('\0'),
                    other => buf.push(other),
                }
            } else {
                buf.push(ch);
            }
        }

        if self.is_at_end() {
            let span = self.make_span(start_line, start_col);
            self.diag
                .report_syntax_error(span.clone(), "Unterminated string literal.");
            return Token::new(TokenKind::StringLit(buf.clone()), buf, span);
        }

        self.advance(); // consume closing '"'
        let span = self.make_span(start_line, start_col);
        Token::new(TokenKind::StringLit(buf.clone()), buf, span)
    }

    fn lex_interpolated_string(&mut self, start_line: u32, start_col: u32) -> Token {
        self.advance(); // consume '$'
        self.advance(); // consume '"'

        let mut parts = Vec::new();
        let mut literal_buf = String::new();
        let mut raw_lexeme = String::from("$\"");

        while !self.is_at_end() && self.peek(0) != '"' {
            let ch = self.advance();
            raw_lexeme.push(ch);

            if ch == '\\' && !self.is_at_end() {
                let esc = self.advance();
                raw_lexeme.push(esc);
                match esc {
                    'n' => literal_buf.push('\n'),
                    'r' => literal_buf.push('\r'),
                    't' => literal_buf.push('\t'),
                    '"' => literal_buf.push('"'),
                    '\\' => literal_buf.push('\\'),
                    other => literal_buf.push(other),
                }
                continue;
            }

            if ch == '{' {
                if self.peek(0) == '{' {
                    self.advance();
                    raw_lexeme.push('{');
                    literal_buf.push('{');
                    continue;
                }
                if !literal_buf.is_empty() {
                    parts.push(InterpPart::Literal(std::mem::take(&mut literal_buf)));
                }
                let mut expr_buf = String::new();
                let mut depth = 1;
                while !self.is_at_end() && depth > 0 {
                    let c = self.advance();
                    raw_lexeme.push(c);
                    if c == '{' {
                        depth += 1;
                        expr_buf.push(c);
                    } else if c == '}' {
                        depth -= 1;
                        if depth > 0 {
                            expr_buf.push(c);
                        }
                    } else {
                        expr_buf.push(c);
                    }
                }
                parts.push(InterpPart::ExprSource(expr_buf.trim().to_string()));
            } else if ch == '}' && self.peek(0) == '}' {
                self.advance();
                raw_lexeme.push('}');
                literal_buf.push('}');
            } else {
                literal_buf.push(ch);
            }
        }

        if !literal_buf.is_empty() {
            parts.push(InterpPart::Literal(literal_buf));
        }

        if self.is_at_end() {
            let span = self.make_span(start_line, start_col);
            self.diag
                .report_syntax_error(span.clone(), "Unterminated interpolated string literal.");
            return Token::new(TokenKind::InterpString(parts), raw_lexeme, span);
        }

        self.advance(); // consume closing '"'
        raw_lexeme.push('"');
        let span = self.make_span(start_line, start_col);
        Token::new(TokenKind::InterpString(parts), raw_lexeme, span)
    }

    fn lex_char(&mut self, start_line: u32, start_col: u32) -> Token {
        self.advance(); // consume '\''
        let ch = if self.peek(0) == '\\' {
            self.advance();
            match self.advance() {
                'n' => '\n',
                'r' => '\r',
                't' => '\t',
                '\'' => '\'',
                '\\' => '\\',
                '0' => '\0',
                other => other,
            }
        } else if !self.is_at_end() {
            self.advance()
        } else {
            '\0'
        };

        if self.peek(0) == '\'' {
            self.advance();
        } else {
            let span = self.make_span(start_line, start_col);
            self.diag
                .report_syntax_error(span, "Unterminated character literal.");
        }
        let span = self.make_span(start_line, start_col);
        Token::new(TokenKind::CharLit(ch), ch.to_string(), span)
    }

    fn lex_ident_or_keyword(&mut self, start_line: u32, start_col: u32) -> Token {
        let mut is_verbatim = false;
        if self.peek(0) == '@' {
            is_verbatim = true;
            self.advance();
        }

        let mut ident = String::new();
        while !self.is_at_end() && (self.peek(0).is_alphanumeric() || self.peek(0) == '_') {
            ident.push(self.advance());
        }

        let span = self.make_span(start_line, start_col);
        if !is_verbatim {
            if let Some(kw) = TokenKind::from_keyword(&ident) {
                return Token::new(kw, ident, span);
            }
        }
        Token::new(TokenKind::Ident(ident.clone()), ident, span)
    }

    fn lex_number(&mut self, start_line: u32, start_col: u32) -> Token {
        if self.peek(0) == '0' && matches!(self.peek(1), 'x' | 'X') {
            self.advance(); // '0'
            self.advance(); // 'x'
            let mut hex_str = String::new();
            while !self.is_at_end() && (self.peek(0).is_ascii_hexdigit() || self.peek(0) == '_') {
                let c = self.advance();
                if c != '_' {
                    hex_str.push(c);
                }
            }
            while matches!(self.peek(0), 'u' | 'U' | 'l' | 'L') {
                self.advance();
            }
            let val = u64::from_str_radix(&hex_str, 16).unwrap_or(0) as i64;
            let span = self.make_span(start_line, start_col);
            return Token::new(TokenKind::IntLit(val), format!("0x{}", hex_str), span);
        }

        let mut num_str = String::new();
        let mut is_float = false;

        while !self.is_at_end() && (self.peek(0).is_ascii_digit() || self.peek(0) == '_') {
            let c = self.advance();
            if c != '_' {
                num_str.push(c);
            }
        }

        // Check fractional part without consuming the `..` range operator!
        if self.peek(0) == '.' && self.peek(1).is_ascii_digit() {
            is_float = true;
            num_str.push(self.advance()); // '.'
            while !self.is_at_end() && (self.peek(0).is_ascii_digit() || self.peek(0) == '_') {
                let c = self.advance();
                if c != '_' {
                    num_str.push(c);
                }
            }
        }

        // Check for `m` or `M` decimal suffix (`rust_decimal::Decimal`)
        if matches!(self.peek(0), 'm' | 'M') {
            self.advance();
            let span = self.make_span(start_line, start_col);
            return Token::new(
                TokenKind::DecimalLit(num_str.clone()),
                format!("{}m", num_str),
                span,
            );
        }

        // Check for float/double suffix (`f`, `F`, `d`, `D`)
        if matches!(self.peek(0), 'f' | 'F' | 'd' | 'D') {
            self.advance();
            is_float = true;
        }

        // Skip integer suffixes like `u`, `U`, `l`, `L`
        while matches!(self.peek(0), 'u' | 'U' | 'l' | 'L') {
            self.advance();
        }

        let span = self.make_span(start_line, start_col);
        if is_float {
            let val = num_str.parse::<f64>().unwrap_or(0.0);
            Token::new(TokenKind::FloatLit(val), num_str, span)
        } else {
            let val = num_str.parse::<i64>().unwrap_or(0);
            Token::new(TokenKind::IntLit(val), num_str, span)
        }
    }

    fn lex_operator_or_delimiter(&mut self, start_line: u32, start_col: u32) -> Option<Token> {
        let ch = self.advance();
        let nxt = self.peek(0);

        // 3-character operator: `??=`
        if ch == '?' && nxt == '?' && self.peek(1) == '=' {
            self.advance();
            self.advance();
            return Some(Token::new(
                TokenKind::NullCoalesceEq,
                "??=",
                self.make_span(start_line, start_col),
            ));
        }

        // 2-character operators
        let two_char = match (ch, nxt) {
            ('.', '.') => Some((TokenKind::DotDot, "..")),
            (':', ':') => Some((TokenKind::ColonColon, "::")),
            ('?', '?') => Some((TokenKind::NullCoalesce, "??")),
            ('?', '.') => Some((TokenKind::NullCond, "?.")),
            ('=', '>') => Some((TokenKind::FatArrow, "=>")),
            ('+', '=') => Some((TokenKind::PlusAssign, "+=")),
            ('-', '=') => Some((TokenKind::MinusAssign, "-=")),
            ('*', '=') => Some((TokenKind::StarAssign, "*=")),
            ('/', '=') => Some((TokenKind::SlashAssign, "/=")),
            ('=', '=') => Some((TokenKind::Eq, "==")),
            ('!', '=') => Some((TokenKind::Neq, "!=")),
            ('<', '=') => Some((TokenKind::Lte, "<=")),
            ('>', '=') => Some((TokenKind::Gte, ">=")),
            ('<', '<') => Some((TokenKind::Shl, "<<")),
            ('>', '>') => Some((TokenKind::Shr, ">>")),
            ('&', '&') => Some((TokenKind::AndAnd, "&&")),
            ('|', '|') => Some((TokenKind::OrOr, "||")),
            _ => None,
        };

        if let Some((kind, lexeme)) = two_char {
            self.advance();
            return Some(Token::new(
                kind,
                lexeme,
                self.make_span(start_line, start_col),
            ));
        }

        // 1-character operators and delimiters
        let one_char = match ch {
            '(' => Some(TokenKind::LParen),
            ')' => Some(TokenKind::RParen),
            '{' => Some(TokenKind::LBrace),
            '}' => Some(TokenKind::RBrace),
            '[' => Some(TokenKind::LBracket),
            ']' => Some(TokenKind::RBracket),
            ';' => Some(TokenKind::Semicolon),
            ',' => Some(TokenKind::Comma),
            '.' => Some(TokenKind::Dot),
            ':' => Some(TokenKind::Colon),
            '?' => Some(TokenKind::Question),
            '^' => Some(TokenKind::Caret),
            '~' => Some(TokenKind::Tilde),
            '&' => Some(TokenKind::Amp),
            '|' => Some(TokenKind::Pipe),
            '=' => Some(TokenKind::Assign),
            '<' => Some(TokenKind::Lt),
            '>' => Some(TokenKind::Gt),
            '!' => Some(TokenKind::Bang),
            '+' => Some(TokenKind::Plus),
            '-' => Some(TokenKind::Minus),
            '*' => Some(TokenKind::Star),
            '/' => Some(TokenKind::Slash),
            '%' => Some(TokenKind::Percent),
            _ => None,
        };

        if let Some(kind) = one_char {
            return Some(Token::new(
                kind,
                ch.to_string(),
                self.make_span(start_line, start_col),
            ));
        }

        let span = self.make_span(start_line, start_col);
        self.diag
            .report_syntax_error(span, format!("Unexpected character '{}'.", ch));
        None
    }
}
