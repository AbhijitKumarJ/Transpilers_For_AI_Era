Here are the complete, raw individual source files for **Milestone 1 (Frontend Foundation: Diagnostics, Tokens, UTF-8 Lexer, Multi-Pass AST Nodes, Recursive-Descent/Pratt Parser, and M1 Verification Suite)** of the **RustSharp Prototype Transpiler (`rsharpc`)**.

---

### `Cargo.toml`

```toml
[package]
name = "rsharpc"
version = "0.1.0"
edition = "2021"
description = "RustSharp (.rsharp) Multi-Pass Compiler Prototype — C# Ergonomics to Zero-Cost Rust"

[lib]
name = "rsharpc"
path = "src/lib.rs"

[[bin]]
name = "rsharpc"
path = "src/main.rs"

```

---

### `src/diagnostics.rs`

```rust
use std::fmt;

/// Tracks exact 1-indexed line and column positions in the original `.rsharp` or `.d.rsharp` file.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct SourceSpan {
    pub file_id: usize,
    pub filename: String,
    pub start_line: u32,
    pub start_col: u32,
    pub end_line: u32,
    pub end_col: u32,
}

impl SourceSpan {
    pub fn new(
        file_id: usize,
        filename: impl Into<String>,
        start_line: u32,
        start_col: u32,
        end_line: u32,
        end_col: u32,
    ) -> Self {
        Self {
            file_id,
            filename: filename.into(),
            start_line,
            start_col,
            end_line,
            end_col,
        }
    }

    pub fn merge(&self, other: &SourceSpan) -> SourceSpan {
        SourceSpan {
            file_id: self.file_id,
            filename: self.filename.clone(),
            start_line: self.start_line,
            start_col: self.start_col,
            end_line: other.end_line,
            end_col: other.end_col,
        }
    }

    pub fn format_location(&self) -> String {
        format!("{}:{}:{}", self.filename, self.start_line, self.start_col)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DiagnosticSeverity {
    Error,
    Warning,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DiagnosticCode {
    SyntaxError,
    UnresolvedSymbol,
    AccessViolation,
    /// RSHARP001: Attempted field mutation inside a `service class` outside the constructor.
    RSharp001ServiceMutation,
    /// RSHARP002: Mutating a collection while iterating over it in a `foreach` loop.
    RSharp002CollectionAliasing,
    /// RSHARP003: Use-after-move of a non-Clone / linear `IDisposable` resource.
    RSharp003UseAfterMove,
}

impl DiagnosticCode {
    pub fn as_str(&self) -> &'static str {
        match self {
            DiagnosticCode::SyntaxError => "RSHARP000",
            DiagnosticCode::RSharp001ServiceMutation => "RSHARP001",
            DiagnosticCode::RSharp002CollectionAliasing => "RSHARP002",
            DiagnosticCode::RSharp003UseAfterMove => "RSHARP003",
            DiagnosticCode::AccessViolation => "RSHARP004",
            DiagnosticCode::UnresolvedSymbol => "RSHARP005",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Diagnostic {
    pub code: DiagnosticCode,
    pub severity: DiagnosticSeverity,
    pub message: String,
    pub span: SourceSpan,
    pub quick_fix: Option<String>,
}

impl fmt::Display for Diagnostic {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let sev = match self.severity {
            DiagnosticSeverity::Error => "ERROR",
            DiagnosticSeverity::Warning => "WARNING",
        };
        write!(
            f,
            "{} [{}] at {}: {}",
            sev,
            self.code.as_str(),
            self.span.format_location(),
            self.message
        )?;
        if let Some(fix) = &self.quick_fix {
            write!(f, " (Quick-fix: {})", fix)?;
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Default)]
pub struct DiagnosticEngine {
    pub diagnostics: Vec<Diagnostic>,
}

impl DiagnosticEngine {
    pub fn new() -> Self {
        Self {
            diagnostics: Vec::new(),
        }
    }

    pub fn report_syntax_error(&mut self, span: SourceSpan, message: impl Into<String>) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::SyntaxError,
            severity: DiagnosticSeverity::Error,
            message: message.into(),
            span,
            quick_fix: None,
        });
    }

    pub fn report_unresolved_symbol(&mut self, span: SourceSpan, symbol_name: &str) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::UnresolvedSymbol,
            severity: DiagnosticSeverity::Error,
            message: format!("Unresolved symbol or type '{}'.", symbol_name),
            span,
            quick_fix: None,
        });
    }

    pub fn report_access_violation(
        &mut self,
        span: SourceSpan,
        member_name: &str,
        access_mod: &str,
        owner_type: &str,
    ) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::AccessViolation,
            severity: DiagnosticSeverity::Error,
            message: format!(
                "Member '{}.{}' is '{}' and cannot be accessed from this context.",
                owner_type, member_name, access_mod
            ),
            span,
            quick_fix: None,
        });
    }

    pub fn report_rsharp001(
        &mut self,
        span: SourceSpan,
        service_name: &str,
        field_name: &str,
    ) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::RSharp001ServiceMutation,
            severity: DiagnosticSeverity::Error,
            message: format!(
                "Cannot mutate field '{}' inside service class '{}'. Service classes are immutable after construction.",
                field_name, service_name
            ),
            span,
            quick_fix: Some(
                "Wrap mutable state in a 'shared class' or pass state via method parameters."
                    .to_string(),
            ),
        });
    }

    pub fn report_rsharp002(&mut self, span: SourceSpan, collection_name: &str) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::RSharp002CollectionAliasing,
            severity: DiagnosticSeverity::Error,
            message: format!(
                "Cannot mutate collection '{}' while iterating over it in a 'foreach' loop.",
                collection_name
            ),
            span,
            quick_fix: Some(format!(
                "Iterate over a snapshot with '{}.ToList()' or collect mutations separately.",
                collection_name
            )),
        });
    }

    pub fn report_rsharp003(
        &mut self,
        span: SourceSpan,
        var_name: &str,
        moved_at: &SourceSpan,
    ) {
        self.diagnostics.push(Diagnostic {
            code: DiagnosticCode::RSharp003UseAfterMove,
            severity: DiagnosticSeverity::Error,
            message: format!(
                "Linear resource '{}' was already consumed at {}:{} and cannot be used again.",
                var_name, moved_at.start_line, moved_at.start_col
            ),
            span,
            quick_fix: Some(
                "Pass the resource by read/mutable borrow instead of a '[Moves]' parameter, or clone if supported."
                    .to_string(),
            ),
        });
    }

    pub fn has_errors(&self) -> bool {
        self.diagnostics
            .iter()
            .any(|d| d.severity == DiagnosticSeverity::Error)
    }

    pub fn format_all(&self) -> String {
        self.diagnostics
            .iter()
            .map(|d| d.to_string())
            .collect::<Vec<_>>()
            .join("\n")
    }
}

```

---

### `src/frontend/mod.rs`

```rust
pub mod ast;
pub mod lexer;
pub mod parser;
pub mod tokens;

pub use ast::*;
pub use lexer::Lexer;
pub use parser::Parser;
pub use tokens::{InterpPart, Token, TokenKind};

```

---

### `src/frontend/tokens.rs`

```rust
use crate::diagnostics::SourceSpan;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum InterpPart {
    Literal(String),
    ExprSource(String),
}

#[derive(Clone, Debug, PartialEq)]
pub enum TokenKind {
    // End of file
    Eof,

    // Identifiers and Literals
    Ident(String),
    IntLit(i64),
    FloatLit(f64),
    DecimalLit(String),
    StringLit(String),
    CharLit(char),
    BoolLit(bool),
    InterpString(Vec<InterpPart>),

    // Architectural & Declaration Keywords
    Namespace,
    Using,
    Extern,
    As,
    Public,
    Internal,
    Protected,
    Private,
    Abstract,
    Sealed,
    Partial,
    Static,
    Readonly,
    Virtual,
    Override,
    Async,
    Await,
    Service,
    Shared,
    Primitive,
    Extensible,
    Record,
    Class,
    Struct,
    Interface,
    Enum,
    Where,
    Throws,
    Params,

    // Accessor & Expression Keywords
    Get,
    Set,
    This,
    Base,
    New,
    Var,
    If,
    Else,
    While,
    ForEach,
    In,
    Switch,
    When,
    Return,
    Throw,
    Try,
    Catch,
    Is,
    Null,

    // Built-in Type Keywords
    Void,
    Bool,
    Byte,
    SByte,
    Short,
    UShort,
    Int,
    UInt,
    Long,
    ULong,
    Float,
    Double,
    Decimal,
    Char,
    StringKw,

    // Punctuation & Delimiters
    LParen,     // (
    RParen,     // )
    LBrace,     // {
    RBrace,     // }
    LBracket,   // [
    RBracket,   // ]
    Semicolon,  // ;
    Comma,      // ,
    Dot,        // .
    Colon,      // :
    ColonColon, // ::
    Question,   // ?

    // Operators
    DotDot,         // ..
    Caret,          // ^
    NullCoalesce,   // ??
    NullCoalesceEq, // ??=
    NullCond,       // ?.
    FatArrow,       // =>
    Assign,         // =
    PlusAssign,     // +=
    MinusAssign,    // -=
    StarAssign,     // *=
    SlashAssign,    // /=
    Eq,             // ==
    Neq,            // !=
    Lt,             // <
    Gt,             // >
    Lte,            // <=
    Gte,            // >=
    AndAnd,         // &&
    OrOr,           // ||
    Bang,           // !
    Plus,           // +
    Minus,          // -
    Star,           // *
    Slash,          // /
    Percent,        // %
    Underscore,     // _
}

impl TokenKind {
    pub fn from_keyword(ident: &str) -> Option<TokenKind> {
        match ident {
            "namespace" => Some(TokenKind::Namespace),
            "using" => Some(TokenKind::Using),
            "extern" => Some(TokenKind::Extern),
            "as" => Some(TokenKind::As),
            "public" => Some(TokenKind::Public),
            "internal" => Some(TokenKind::Internal),
            "protected" => Some(TokenKind::Protected),
            "private" => Some(TokenKind::Private),
            "abstract" => Some(TokenKind::Abstract),
            "sealed" => Some(TokenKind::Sealed),
            "partial" => Some(TokenKind::Partial),
            "static" => Some(TokenKind::Static),
            "readonly" => Some(TokenKind::Readonly),
            "virtual" => Some(TokenKind::Virtual),
            "override" => Some(TokenKind::Override),
            "async" => Some(TokenKind::Async),
            "await" => Some(TokenKind::Await),
            "service" => Some(TokenKind::Service),
            "shared" => Some(TokenKind::Shared),
            "primitive" => Some(TokenKind::Primitive),
            "extensible" => Some(TokenKind::Extensible),
            "record" => Some(TokenKind::Record),
            "class" => Some(TokenKind::Class),
            "struct" => Some(TokenKind::Struct),
            "interface" => Some(TokenKind::Interface),
            "enum" => Some(TokenKind::Enum),
            "where" => Some(TokenKind::Where),
            "throws" => Some(TokenKind::Throws),
            "params" => Some(TokenKind::Params),
            "get" => Some(TokenKind::Get),
            "set" => Some(TokenKind::Set),
            "this" => Some(TokenKind::This),
            "base" => Some(TokenKind::Base),
            "new" => Some(TokenKind::New),
            "var" => Some(TokenKind::Var),
            "if" => Some(TokenKind::If),
            "else" => Some(TokenKind::Else),
            "while" => Some(TokenKind::While),
            "foreach" => Some(TokenKind::ForEach),
            "in" => Some(TokenKind::In),
            "switch" => Some(TokenKind::Switch),
            "when" => Some(TokenKind::When),
            "return" => Some(TokenKind::Return),
            "throw" => Some(TokenKind::Throw),
            "try" => Some(TokenKind::Try),
            "catch" => Some(TokenKind::Catch),
            "is" => Some(TokenKind::Is),
            "null" => Some(TokenKind::Null),
            "true" => Some(TokenKind::BoolLit(true)),
            "false" => Some(TokenKind::BoolLit(false)),
            "void" => Some(TokenKind::Void),
            "bool" => Some(TokenKind::Bool),
            "byte" => Some(TokenKind::Byte),
            "sbyte" => Some(TokenKind::SByte),
            "short" => Some(TokenKind::Short),
            "ushort" => Some(TokenKind::UShort),
            "int" => Some(TokenKind::Int),
            "uint" => Some(TokenKind::UInt),
            "long" => Some(TokenKind::Long),
            "ulong" => Some(TokenKind::ULong),
            "float" => Some(TokenKind::Float),
            "double" => Some(TokenKind::Double),
            "decimal" => Some(TokenKind::Decimal),
            "char" => Some(TokenKind::Char),
            "string" => Some(TokenKind::StringKw),
            "_" => Some(TokenKind::Underscore),
            _ => None,
        }
    }

    pub fn is_primitive_type_keyword(&self) -> Option<&'static str> {
        match self {
            TokenKind::Void => Some("void"),
            TokenKind::Bool => Some("bool"),
            TokenKind::Byte => Some("byte"),
            TokenKind::SByte => Some("sbyte"),
            TokenKind::Short => Some("short"),
            TokenKind::UShort => Some("ushort"),
            TokenKind::Int => Some("int"),
            TokenKind::UInt => Some("uint"),
            TokenKind::Long => Some("long"),
            TokenKind::ULong => Some("ulong"),
            TokenKind::Float => Some("float"),
            TokenKind::Double => Some("double"),
            TokenKind::Decimal => Some("decimal"),
            TokenKind::Char => Some("char"),
            TokenKind::StringKw => Some("string"),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Token {
    pub kind: TokenKind,
    pub lexeme: String,
    pub span: SourceSpan,
}

impl Token {
    pub fn new(kind: TokenKind, lexeme: impl Into<String>, span: SourceSpan) -> Self {
        Self {
            kind,
            lexeme: lexeme.into(),
            span,
        }
    }
}

```

---

### `src/frontend/lexer.rs`

```rust
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
            return Token::new(TokenKind::DecimalLit(num_str.clone()), format!("{}m", num_str), span);
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
            ('&', '&') => Some((TokenKind::AndAnd, "&&")),
            ('|', '|') => Some((TokenKind::OrOr, "||")),
            _ => None,
        };

        if let Some((kind, lexeme)) = two_char {
            self.advance();
            return Some(Token::new(kind, lexeme, self.make_span(start_line, start_col)));
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

```

---

### `src/frontend/ast.rs`

```rust
use crate::diagnostics::SourceSpan;
use crate::frontend::tokens::InterpPart;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub struct SymbolId(pub u32);

// ============================================================================
// PASS 2 INFERRED SEMANTIC SLOTS (POPULATED BY SEMANTICS LAYER)
// ============================================================================

/// Inferred by Pass 2 Interprocedural Escape & Mutation Analysis for parameters & receivers.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum BorrowMode {
    #[default]
    Unresolved,
    /// Emits `&T` or `&self` (`string` -> `&str`, `List<T>` -> `&[T]`).
    ReadBorrow,
    /// Emits `&mut T` or `&mut self` (automatically injects `let mut` at caller).
    MutBorrow,
    /// Emits owned `T` (value is moved into a field, collection, or return).
    OwnedMove,
    /// Emits `Arc<T>` (used for `service class` dependencies).
    SharedArc,
    /// Emits `T` by value for `Copy` primitives (`i32`, `bool`, `f64`, `Decimal`).
    CopyValue,
}

/// Inferred by Pass 2 Hierarchy Lowerer for abstract classes, subclasses, and interfaces.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum PolymorphismStrategy {
    #[default]
    Unresolved,
    /// Standard struct with no subclasses.
    MonomorphicStruct,
    /// Concrete single-inheritance subclass: embeds `pub base: BaseType` + `Deref`/`DerefMut`.
    FlattenedSubStruct { base_type: SymbolId },
    /// Closed-world hierarchy: lowers base class/interface into a tagged union `pub enum`.
    ClosedWorldEnum { variants: Vec<SymbolId> },
    /// Marked `extensible interface` -> lowers to a native `pub trait`.
    OpenTrait,
}

/// Inferred by Pass 2 Checked Effect Analysis (`throws` & `try/catch` call graph).
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum EffectSignature {
    #[default]
    Unresolved,
    /// Returns `T` directly.
    Infallible,
    /// Rewrites return type to `Result<T, E>`.
    Fallible { error_type: TypeRef },
}

/// Parsed from `[MapsTo("...")]` and `[InlineTemplate("...")]` on `primitive` types.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum PrimitiveLowering {
    #[default]
    None,
    /// Direct Rust symbol mapping: e.g., `List<T>.Add` -> `push`.
    DirectSymbol { rust_path: String },
    /// Inline template substitution: e.g., `{self}.contains(&{0})`.
    InlineTemplate { template: String },
    /// Direct indexing: `this[i]` -> `{self}[{0} as usize]`.
    OperatorIndex,
}

/// Storage wrapper mode inferred for class/record fields.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum FieldStorageMode {
    #[default]
    Plain,
    /// `std::sync::Arc<T>` (automatically selected for `service class` dependencies).
    ArcShared,
    /// `std::sync::Arc<std::sync::RwLock<T>>` (automatically selected in `shared class`).
    RwLockShared,
}

/// Coercion injected at call sites by Pass 2 when passing arguments to inferred parameters.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum CallerArgCoercion {
    #[default]
    None,
    /// Prepends `&` (or `&*` if re-borrowing a `&mut T` as `&T`).
    BorrowShared,
    /// Prepends `&mut`.
    BorrowMutable,
    /// Appends `.clone()` when an owned value is needed again later in scope.
    CloneOwned,
    /// Wraps or clones via `Arc::clone(&x)`.
    ArcClone,
}

// ============================================================================
// TOP-LEVEL COMPILATION UNIT, IMPORTS & ATTRIBUTES
// ============================================================================

#[derive(Clone, Debug)]
pub struct CompilationUnit {
    pub file_id: usize,
    pub filename: String,
    pub is_ambient_stub: bool,
    pub namespace: Vec<String>,
    pub imports: Vec<ImportDecl>,
    pub types: Vec<TypeDecl>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ImportDecl {
    pub span: SourceSpan,
    pub is_extern_crate: bool,
    pub path: Vec<String>,
    pub alias: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AttributeArg {
    pub name: Option<String>,
    pub value: Expr,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AttributeNode {
    pub span: SourceSpan,
    pub path: Vec<String>,
    pub args: Vec<AttributeArg>,
}

impl AttributeNode {
    pub fn short_name(&self) -> &str {
        self.path.last().map(|s| s.as_str()).unwrap_or("")
    }

    pub fn first_string_arg(&self) -> Option<&str> {
        self.args.first().and_then(|arg| match &arg.value.kind {
            ExprKind::Literal(LiteralValue::String(s)) => Some(s.as_str()),
            _ => None,
        })
    }
}

// ============================================================================
// TYPE DECLARATIONS & ARCHETYPES
// ============================================================================

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum AccessMod {
    #[default]
    Public,
    Internal,
    Protected,
    Private,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TypeKind {
    Record { is_struct: bool },
    StandardClass,
    ServiceClass,
    SharedClass,
    PrimitiveClass { is_struct: bool },
    ValueStruct,
    Interface { is_extensible: bool },
    Enum,
}

#[derive(Clone, Debug, PartialEq)]
pub struct TypeConstraint {
    pub type_param: String,
    pub bounds: Vec<TypeRef>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct EnumVariantDecl {
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub name: String,
    pub payload: Vec<ParamDecl>,
    pub discriminant: Option<Expr>,
}

#[derive(Clone, Debug)]
pub struct TypeDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub kind: TypeKind,
    pub is_abstract: bool,
    pub is_sealed: bool,
    pub is_partial: bool,
    pub is_static: bool,
    pub name: String,
    pub type_params: Vec<String>,
    pub primary_ctor_params: Vec<ParamDecl>,
    pub base_types: Vec<TypeRef>,
    pub constraints: Vec<TypeConstraint>,
    pub members: Vec<MemberDecl>,
    pub enum_variants: Vec<EnumVariantDecl>,

    // --- Pass 2 Semantic Slots ---
    pub inferred_polymorphism: PolymorphismStrategy,
    pub primitive_rust_target: Option<String>,
    pub primitive_param_type: Option<String>,
    pub has_disposable_drop: bool,
}

// ============================================================================
// TYPE REFERENCES
// ============================================================================

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct TypeRef {
    pub span: SourceSpan,
    pub path: Vec<String>,
    pub type_args: Vec<TypeRef>,
    pub is_nullable: bool,
    pub is_primitive_keyword: bool,
}

impl TypeRef {
    pub fn short_name(&self) -> &str {
        self.path.last().map(|s| s.as_str()).unwrap_or("")
    }

    pub fn qualified_name(&self) -> String {
        self.path.join(".")
    }
}

// ============================================================================
// CLASS / RECORD / INTERFACE MEMBERS
// ============================================================================

#[derive(Clone, Debug, PartialEq)]
pub enum MemberDecl {
    Field(FieldDecl),
    Property(PropertyDecl),
    Constructor(ConstructorDecl),
    Method(MethodDecl),
    Indexer(IndexerDecl),
}

#[derive(Clone, Debug, PartialEq)]
pub struct FieldDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub is_readonly: bool,
    pub is_static: bool,
    pub name: String,
    pub ty: TypeRef,
    pub initializer: Option<Expr>,

    // --- Pass 2 Semantic Slot ---
    pub resolved_storage: FieldStorageMode,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AccessorDecl {
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: Option<AccessMod>,
    pub is_get: bool,
    pub body: Option<Block>,
    pub inline_template: Option<String>,
    pub explicit_borrow: Option<BorrowMode>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PropertyDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub is_static: bool,
    pub is_extern: bool,
    pub name: String,
    pub ty: TypeRef,
    pub accessors: Vec<AccessorDecl>,
    pub initializer: Option<Expr>,

    // --- Pass 2 Semantic Slots ---
    pub resolved_storage: FieldStorageMode,
    pub primitive_lowering: PrimitiveLowering,
}

#[derive(Clone, Debug, PartialEq)]
pub struct IndexerDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub is_extern: bool,
    pub ty: TypeRef,
    pub params: Vec<ParamDecl>,
    pub accessors: Vec<AccessorDecl>,
    pub primitive_lowering: PrimitiveLowering,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ConstructorDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub is_extern: bool,
    pub name: String,
    pub params: Vec<ParamDecl>,
    pub base_args: Option<Vec<ArgNode>>,
    pub body: Option<Block>,

    // --- Pass 2 Semantic Slots ---
    pub disambiguated_rust_name: String,
    pub primitive_lowering: PrimitiveLowering,
}

#[derive(Clone, Debug, PartialEq)]
pub struct MethodDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub is_static: bool,
    pub is_async: bool,
    pub is_extern: bool,
    pub is_virtual: bool,
    pub is_override: bool,
    pub is_abstract: bool,
    pub name: String,
    pub type_params: Vec<String>,
    pub params: Vec<ParamDecl>,
    pub return_type: TypeRef,
    pub explicit_throws: Option<TypeRef>,
    pub constraints: Vec<TypeConstraint>,
    pub body: Option<Block>,

    // --- Pass 2 Semantic Slots ---
    pub inferred_self_borrow: BorrowMode,
    pub inferred_effect: EffectSignature,
    pub disambiguated_rust_name: String,
    pub primitive_lowering: PrimitiveLowering,
    pub linq_stage: Option<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ParamDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub is_params: bool,
    pub ty: TypeRef,
    pub name: String,
    pub default_value: Option<Expr>,

    // --- Pass 2 Semantic Slots ---
    pub explicit_constraint: Option<BorrowMode>,
    pub inferred_borrow: BorrowMode,
}

// ============================================================================
// STATEMENTS & CONTROL FLOW
// ============================================================================

#[derive(Clone, Debug, PartialEq)]
pub struct Block {
    pub span: SourceSpan,
    pub stmts: Vec<Stmt>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct CatchArm {
    pub span: SourceSpan,
    pub error_type: TypeRef,
    pub var_name: Option<String>,
    pub body: Block,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Stmt {
    Block(Block),
    LocalVar {
        span: SourceSpan,
        symbol_id: SymbolId,
        name: String,
        explicit_type: Option<TypeRef>,
        init: Expr,
        inferred_mut: bool,
        inferred_type: Option<TypeRef>,
    },
    UsingResource {
        span: SourceSpan,
        symbol_id: SymbolId,
        name: String,
        explicit_type: Option<TypeRef>,
        init: Expr,
        inferred_mut: bool,
    },
    If {
        span: SourceSpan,
        cond: Expr,
        then_branch: Box<Stmt>,
        else_branch: Option<Box<Stmt>>,
    },
    While {
        span: SourceSpan,
        cond: Expr,
        body: Box<Stmt>,
    },
    ForEach {
        span: SourceSpan,
        item_symbol: SymbolId,
        item_type: Option<TypeRef>,
        item_name: String,
        collection: Expr,
        body: Box<Stmt>,
        iter_borrow_mode: BorrowMode,
    },
    Return {
        span: SourceSpan,
        value: Option<Expr>,
    },
    Throw {
        span: SourceSpan,
        error_expr: Expr,
    },
    TryCatch {
        span: SourceSpan,
        try_block: Block,
        catches: Vec<CatchArm>,
    },
    ExprStmt {
        span: SourceSpan,
        expr: Expr,
    },
}

// ============================================================================
// EXPRESSIONS, SLICING, LINQ CHAINS & PATTERN MATCHING
// ============================================================================

#[derive(Clone, Debug, PartialEq)]
pub enum LiteralValue {
    Int(i64),
    Float(f64),
    Decimal(String),
    String(String),
    Char(char),
    Bool(bool),
    Null,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AssignOp {
    Assign,         // =
    AddAssign,      // +=
    SubAssign,      // -=
    MulAssign,      // *=
    DivAssign,      // /=
    NullCoalesceEq, // ??=
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BinaryOp {
    Add,
    Sub,
    Mul,
    Div,
    Rem,
    Eq,
    Neq,
    Lt,
    Gt,
    Lte,
    Gte,
    And,
    Or,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UnaryOp {
    Not,       // !
    Neg,       // -
    Await,     // await
    FromEnd,   // ^
}

#[derive(Clone, Debug, PartialEq)]
pub struct ArgNode {
    pub span: SourceSpan,
    pub name: Option<String>,
    pub expr: Expr,
}

#[derive(Clone, Debug, PartialEq)]
pub enum LambdaBody {
    Expr(Box<Expr>),
    Block(Block),
}

#[derive(Clone, Debug, PartialEq)]
pub struct PropertyPatternField {
    pub field_name: String,
    pub pattern: Pattern,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Pattern {
    Wildcard(SourceSpan),
    Null(SourceSpan),
    Literal(SourceSpan, LiteralValue),
    TypePattern {
        span: SourceSpan,
        ty: TypeRef,
        bind_name: Option<String>,
        property_patterns: Vec<PropertyPatternField>,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct SwitchArmNode {
    pub span: SourceSpan,
    pub pattern: Pattern,
    pub guard: Option<Expr>,
    pub body: Expr,
}

#[derive(Clone, Debug, PartialEq)]
pub enum LinqOp {
    Where { predicate: Expr },
    Select { selector: Expr },
    SelectMany { selector: Expr },
    Take { count: Expr },
    Skip { count: Expr },
    WithIndex,
}

#[derive(Clone, Debug, PartialEq)]
pub enum LinqTerminal {
    ToList,
    ToHashSet,
    Any { predicate: Option<Expr> },
    All { predicate: Expr },
    FirstOrDefault { predicate: Option<Expr> },
    Count,
    Sum,
}

#[derive(Clone, Debug, PartialEq)]
pub struct LinqChain {
    pub source: Box<Expr>,
    pub ops: Vec<LinqOp>,
    pub terminal: LinqTerminal,
    pub consumes_source: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Expr {
    pub span: SourceSpan,
    pub kind: ExprKind,

    // --- Pass 2 Semantic Slots ---
    pub resolved_type: Option<TypeRef>,
    pub append_try_question_mark: bool,
    pub caller_coercion: CallerArgCoercion,
}

impl Expr {
    pub fn new(span: SourceSpan, kind: ExprKind) -> Self {
        Self {
            span,
            kind,
            resolved_type: None,
            append_try_question_mark: false,
            caller_coercion: CallerArgCoercion::None,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum ExprKind {
    Literal(LiteralValue),
    InterpolatedString(Vec<InterpPart>),
    Identifier {
        name: String,
        resolved_symbol: Option<SymbolId>,
    },
    This,
    Base,
    Unary {
        op: UnaryOp,
        operand: Box<Expr>,
    },
    Binary {
        op: BinaryOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Assignment {
        op: AssignOp,
        target: Box<Expr>,
        value: Box<Expr>,
    },
    NullCoalesce {
        left: Box<Expr>,
        right: Box<Expr>,
    },
    IsPattern {
        expr: Box<Expr>,
        pattern: Pattern,
    },
    MemberAccess {
        target: Box<Expr>,
        member: String,
        is_null_conditional: bool,
        resolved_symbol: Option<SymbolId>,
    },
    MethodCall {
        receiver: Option<Box<Expr>>,
        method_name: String,
        type_args: Vec<TypeRef>,
        args: Vec<ArgNode>,
        is_null_conditional: bool,
        resolved_overload: Option<SymbolId>,
        primitive_lowering: PrimitiveLowering,
    },
    IndexAccess {
        target: Box<Expr>,
        indices: Vec<ArgNode>,
    },
    RangeSlice {
        target: Option<Box<Expr>>,
        start: Option<Box<Expr>>,
        end: Option<Box<Expr>>,
    },
    Construct {
        ty: TypeRef,
        args: Vec<ArgNode>,
        resolved_ctor: Option<SymbolId>,
        primitive_lowering: PrimitiveLowering,
    },
    Lambda {
        params: Vec<String>,
        body: LambdaBody,
    },
    Switch {
        scrutinee: Box<Expr>,
        arms: Vec<SwitchArmNode>,
    },
    LinqChain(LinqChain),
}

```

---

### `src/frontend/parser.rs`

```rust
use crate::diagnostics::{DiagnosticEngine, SourceSpan};
use crate::frontend::ast::*;
use crate::frontend::tokens::{Token, TokenKind};

/// Recursive-descent declaration parser + Pratt expression parser for `.rsharp` and `.d.rsharp`.
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

    // ========================================================================
    // 1. COMPILATION UNIT, NAMESPACE & IMPORTS
    // ========================================================================

    pub fn parse_compilation_unit(&mut self) -> CompilationUnit {
        let is_ambient_stub = self.filename.ends_with(".d.rsharp");
        let mut namespace = Vec::new();
        let mut imports = Vec::new();
        let mut types = Vec::new();

        if self.match_kind(&TokenKind::Namespace) {
            namespace = self.parse_qualified_ident();
            self.consume_semicolon("Expected ';' after namespace declaration.");
        }

        while self.check(&TokenKind::Using) || self.check(&TokenKind::Extern) {
            if self.check(&TokenKind::Extern) && self.peek(1).kind != TokenKind::Using {
                break;
            }
            imports.push(self.parse_import_decl());
        }

        while !self.is_at_end() {
            let start_pos = self.pos;
            types.push(self.parse_type_decl());
            if self.pos == start_pos {
                self.advance();
            }
        }

        CompilationUnit {
            file_id: self.file_id,
            filename: self.filename.clone(),
            is_ambient_stub,
            namespace,
            imports,
            types,
        }
    }

    fn parse_import_decl(&mut self) -> ImportDecl {
        let start_span = self.current_span();
        let is_extern_crate = self.match_kind(&TokenKind::Extern);
        self.expect(&TokenKind::Using, "Expected 'using' keyword.");

        let mut path = Vec::new();
        path.push(self.expect_ident("Expected identifier in import path."));
        while self.match_kind(&TokenKind::Dot) || self.match_kind(&TokenKind::ColonColon) {
            path.push(self.expect_ident("Expected identifier after '.' or '::'."));
        }

        let alias = if self.match_kind(&TokenKind::As) {
            Some(self.expect_ident("Expected alias identifier after 'as'."))
        } else {
            None
        };

        let end_span = self.consume_semicolon("Expected ';' after import declaration.");
        ImportDecl {
            span: start_span.merge(&end_span),
            is_extern_crate,
            path,
            alias,
        }
    }

    // ========================================================================
    // 2. ATTRIBUTES
    // ========================================================================

    fn parse_attribute_sections(&mut self) -> Vec<AttributeNode> {
        let mut attrs = Vec::new();
        while self.match_kind(&TokenKind::LBracket) {
            while !self.is_at_end() && !self.check(&TokenKind::RBracket) {
                let attr_start = self.current_span();
                let path = self.parse_qualified_ident();
                let mut args = Vec::new();

                if self.match_kind(&TokenKind::LParen) {
                    if !self.check(&TokenKind::RParen) {
                        loop {
                            let name = if self.is_ident_at(0)
                                && matches!(self.peek(1).kind, TokenKind::Assign | TokenKind::Colon)
                            {
                                let n = self.expect_ident("Expected attribute argument name.");
                                self.advance(); // consume '=' or ':'
                                Some(n)
                            } else {
                                None
                            };
                            let value = self.parse_expr(0);
                            args.push(AttributeArg { name, value });
                            if !self.match_kind(&TokenKind::Comma) {
                                break;
                            }
                        }
                    }
                    self.expect(&TokenKind::RParen, "Expected ')' after attribute arguments.");
                }

                let attr_end = self.previous_span();
                attrs.push(AttributeNode {
                    span: attr_start.merge(&attr_end),
                    path,
                    args,
                });

                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect(&TokenKind::RBracket, "Expected ']' closing attribute section.");
        }
        attrs
    }

    // ========================================================================
    // 3. TOP-LEVEL TYPE ARCHETYPE DECLARATIONS
    // ========================================================================

    fn parse_type_decl(&mut self) -> TypeDecl {
        let attributes = self.parse_attribute_sections();
        let start_span = self.current_span();
        let access = self.parse_access_modifier(AccessMod::Internal);

        let mut is_abstract = false;
        let mut is_sealed = false;
        let mut is_partial = false;
        let mut is_static = false;
        let mut is_service = false;
        let mut is_shared = false;
        let mut is_primitive = false;
        let mut is_extensible = false;

        loop {
            if self.match_kind(&TokenKind::Abstract) {
                is_abstract = true;
            } else if self.match_kind(&TokenKind::Sealed) {
                is_sealed = true;
            } else if self.match_kind(&TokenKind::Partial) {
                is_partial = true;
            } else if self.match_kind(&TokenKind::Static) {
                is_static = true;
            } else if self.match_kind(&TokenKind::Service) {
                is_service = true;
            } else if self.match_kind(&TokenKind::Shared) {
                is_shared = true;
            } else if self.match_kind(&TokenKind::Primitive) {
                is_primitive = true;
            } else if self.match_kind(&TokenKind::Extensible) {
                is_extensible = true;
            } else {
                break;
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
                    "Expected type declaration ('class', 'record', 'struct', 'interface', or 'enum'), found '{}'.",
                    self.peek(0).lexeme
                ),
            );
            TypeKind::StandardClass
        };

        let name = self.expect_ident("Expected type name.");
        let type_params = self.parse_type_params();

        let primary_ctor_params =
            if matches!(kind, TypeKind::Record { .. }) && self.check(&TokenKind::LParen) {
                self.parse_param_list()
            } else {
                Vec::new()
            };

        let mut base_types = Vec::new();
        if self.match_kind(&TokenKind::Colon) {
            loop {
                base_types.push(self.parse_type_ref());
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
        }

        let constraints = self.parse_type_constraints();

        let mut members = Vec::new();
        let mut enum_variants = Vec::new();

        if self.match_kind(&TokenKind::Semicolon) {
            // Primary-constructor record terminated with ';'
        } else if self.match_kind(&TokenKind::LBrace) {
            if kind == TypeKind::Enum {
                enum_variants = self.parse_enum_variants();
            } else {
                while !self.is_at_end() && !self.check(&TokenKind::RBrace) {
                    let prev_pos = self.pos;
                    members.push(self.parse_member_decl(&name, matches!(kind, TypeKind::Interface { .. })));
                    if self.pos == prev_pos {
                        self.advance();
                    }
                }
            }
            self.expect(&TokenKind::RBrace, "Expected '}' after type body.");
        }

        let primitive_rust_target = attributes
            .iter()
            .find(|a| a.short_name() == "MapsTo")
            .and_then(|a| a.first_string_arg().map(|s| s.to_string()));

        let primitive_param_type = attributes
            .iter()
            .find(|a| a.short_name() == "ParamType")
            .and_then(|a| a.first_string_arg().map(|s| s.to_string()));

        let end_span = self.previous_span();
        TypeDecl {
            id: SymbolId(0),
            span: start_span.merge(&end_span),
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
            has_disposable_drop: false,
        }
    }

    fn parse_enum_variants(&mut self) -> Vec<EnumVariantDecl> {
        let mut variants = Vec::new();
        while !self.is_at_end() && !self.check(&TokenKind::RBrace) {
            let attributes = self.parse_attribute_sections();
            let start_span = self.current_span();
            let name = self.expect_ident("Expected enum variant name.");
            let payload = if self.check(&TokenKind::LParen) {
                self.parse_param_list()
            } else {
                Vec::new()
            };
            let discriminant = if self.match_kind(&TokenKind::Assign) {
                Some(self.parse_expr(0))
            } else {
                None
            };
            let end_span = self.previous_span();
            variants.push(EnumVariantDecl {
                span: start_span.merge(&end_span),
                attributes,
                name,
                payload,
                discriminant,
            });
            if !self.match_kind(&TokenKind::Comma) {
                break;
            }
        }
        variants
    }

    // ========================================================================
    // 4. CLASS / RECORD / PRIMITIVE MEMBERS
    // ========================================================================

    fn parse_member_decl(&mut self, enclosing_type_name: &str, is_interface: bool) -> MemberDecl {
        let attributes = self.parse_attribute_sections();
        let start_span = self.current_span();
        let default_access = if is_interface {
            AccessMod::Public
        } else {
            AccessMod::Private
        };
        let access = self.parse_access_modifier(default_access);

        let mut is_readonly = false;
        let mut is_static = false;
        let mut is_virtual = false;
        let mut is_override = false;
        let mut is_abstract = is_interface;
        let mut is_extern = false;
        let mut is_async = false;

        loop {
            if self.match_kind(&TokenKind::Readonly) {
                is_readonly = true;
            } else if self.match_kind(&TokenKind::Static) {
                is_static = true;
            } else if self.match_kind(&TokenKind::Virtual) {
                is_virtual = true;
            } else if self.match_kind(&TokenKind::Override) {
                is_override = true;
            } else if self.match_kind(&TokenKind::Abstract) {
                is_abstract = true;
            } else if self.match_kind(&TokenKind::Extern) {
                is_extern = true;
            } else if self.match_kind(&TokenKind::Async) {
                is_async = true;
            } else {
                break;
            }
        }

        let primitive_lowering = Self::extract_primitive_lowering(&attributes);

        // Constructor declaration: `TypeName(...)`
        if self.peek(0).lexeme == enclosing_type_name && self.peek(1).kind == TokenKind::LParen {
            let ctor_name = self.expect_ident("Expected constructor name.");
            let params = self.parse_param_list();
            let base_args = if self.match_kind(&TokenKind::Colon) {
                self.expect(&TokenKind::Base, "Expected 'base' in constructor chain.");
                Some(self.parse_arg_list())
            } else {
                None
            };
            let body = self.parse_method_or_ctor_body(start_span.clone());
            let end_span = self.previous_span();
            return MemberDecl::Constructor(ConstructorDecl {
                id: SymbolId(0),
                span: start_span.merge(&end_span),
                attributes,
                access,
                is_extern,
                name: ctor_name,
                params,
                base_args,
                body,
                disambiguated_rust_name: "new".to_string(),
                primitive_lowering,
            });
        }

        let member_type = self.parse_type_ref();

        // Indexer declaration: `TypeRef this[ParamList] { get; set; }`
        if self.match_kind(&TokenKind::This) {
            self.expect(&TokenKind::LBracket, "Expected '[' in indexer declaration.");
            let mut params = Vec::new();
            if !self.check(&TokenKind::RBracket) {
                loop {
                    params.push(self.parse_param());
                    if !self.match_kind(&TokenKind::Comma) {
                        break;
                    }
                }
            }
            self.expect(&TokenKind::RBracket, "Expected ']' after indexer parameters.");
            let accessors = self.parse_accessor_list();
            let end_span = self.previous_span();
            return MemberDecl::Indexer(IndexerDecl {
                id: SymbolId(0),
                span: start_span.merge(&end_span),
                attributes,
                access,
                is_extern,
                ty: member_type,
                params,
                accessors,
                primitive_lowering,
            });
        }

        let member_name = self.expect_ident("Expected member name.");

        // Method declaration: `TypeRef Ident<T>(...) throws E { ... }`
        if self.check(&TokenKind::LParen) || self.check(&TokenKind::Lt) {
            let type_params = self.parse_type_params();
            let params = self.parse_param_list();
            let explicit_throws = if self.match_kind(&TokenKind::Throws) {
                Some(self.parse_type_ref())
            } else {
                None
            };
            let constraints = self.parse_type_constraints();
            let body = self.parse_method_or_ctor_body(start_span.clone());
            let end_span = self.previous_span();

            let inferred_self_borrow = Self::extract_explicit_borrow(&attributes)
                .unwrap_or(BorrowMode::Unresolved);
            let linq_stage = attributes
                .iter()
                .find(|a| a.short_name() == "LinqStage")
                .and_then(|a| a.first_string_arg().map(|s| s.to_string()));

            let inferred_effect = match &explicit_throws {
                Some(err_ty) => EffectSignature::Fallible {
                    error_type: err_ty.clone(),
                },
                None => EffectSignature::Unresolved,
            };

            return MemberDecl::Method(MethodDecl {
                id: SymbolId(0),
                span: start_span.merge(&end_span),
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
            });
        }

        // Property declaration: `TypeRef Ident { get; set; }` or `TypeRef Ident => expr;`
        if self.check(&TokenKind::LBrace) {
            let accessors = self.parse_accessor_list();
            let initializer = if self.match_kind(&TokenKind::Assign) {
                let expr = self.parse_expr(0);
                self.consume_semicolon("Expected ';' after property initializer.");
                Some(expr)
            } else {
                None
            };
            let end_span = self.previous_span();
            return MemberDecl::Property(PropertyDecl {
                id: SymbolId(0),
                span: start_span.merge(&end_span),
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
            });
        }

        if self.match_kind(&TokenKind::FatArrow) {
            let expr = self.parse_expr(0);
            let end_span = self.consume_semicolon("Expected ';' after expression-bodied property.");
            let getter_block = Block {
                span: expr.span.clone(),
                stmts: vec![Stmt::Return {
                    span: expr.span.clone(),
                    value: Some(expr),
                }],
            };
            return MemberDecl::Property(PropertyDecl {
                id: SymbolId(0),
                span: start_span.merge(&end_span),
                attributes,
                access,
                is_static,
                is_extern,
                name: member_name,
                ty: member_type,
                accessors: vec![AccessorDecl {
                    span: start_span.merge(&end_span),
                    attributes: Vec::new(),
                    access: None,
                    is_get: true,
                    body: Some(getter_block),
                    inline_template: None,
                    explicit_borrow: Some(BorrowMode::ReadBorrow),
                }],
                initializer: None,
                resolved_storage: FieldStorageMode::Plain,
                primitive_lowering,
            });
        }

        // Field declaration: `TypeRef Ident (= Expr)?;`
        let initializer = if self.match_kind(&TokenKind::Assign) {
            Some(self.parse_expr(0))
        } else {
            None
        };
        let end_span = self.consume_semicolon("Expected ';' after field declaration.");

        MemberDecl::Field(FieldDecl {
            id: SymbolId(0),
            span: start_span.merge(&end_span),
            attributes,
            access,
            is_readonly,
            is_static,
            name: member_name,
            ty: member_type,
            initializer,
            resolved_storage: FieldStorageMode::Plain,
        })
    }

    fn parse_accessor_list(&mut self) -> Vec<AccessorDecl> {
        let mut accessors = Vec::new();
        self.expect(&TokenKind::LBrace, "Expected '{' starting accessor list.");
        while !self.is_at_end() && !self.check(&TokenKind::RBrace) {
            let attrs = self.parse_attribute_sections();
            let acc_start = self.current_span();
            let acc_mod = self.parse_optional_access_modifier();

            let is_get = if self.match_kind(&TokenKind::Get) {
                true
            } else if self.match_kind(&TokenKind::Set) {
                false
            } else {
                let span = self.current_span();
                self.diag
                    .report_syntax_error(span, "Expected 'get' or 'set' in property accessor.");
                self.advance();
                continue;
            };

            let body = if self.match_kind(&TokenKind::Semicolon) {
                None
            } else if self.match_kind(&TokenKind::FatArrow) {
                let expr = self.parse_expr(0);
                self.consume_semicolon("Expected ';' after accessor expression.");
                Some(Block {
                    span: expr.span.clone(),
                    stmts: vec![Stmt::Return {
                        span: expr.span.clone(),
                        value: Some(expr),
                    }],
                })
            } else if self.check(&TokenKind::LBrace) {
                Some(self.parse_block())
            } else {
                None
            };

            let inline_template = attrs
                .iter()
                .find(|a| a.short_name() == "InlineTemplate")
                .and_then(|a| a.first_string_arg().map(|s| s.to_string()));
            let explicit_borrow = Self::extract_explicit_borrow(&attrs);

            accessors.push(AccessorDecl {
                span: acc_start.merge(&self.previous_span()),
                attributes: attrs,
                access: acc_mod,
                is_get,
                body,
                inline_template,
                explicit_borrow,
            });
        }
        self.expect(&TokenKind::RBrace, "Expected '}' closing accessor list.");
        accessors
    }

    fn parse_method_or_ctor_body(&mut self, start_span: SourceSpan) -> Option<Block> {
        if self.match_kind(&TokenKind::Semicolon) {
            None
        } else if self.match_kind(&TokenKind::FatArrow) {
            let expr = self.parse_expr(0);
            let end_span = self.consume_semicolon("Expected ';' after expression body.");
            let stmt = match &expr.kind {
                ExprKind::Assignment { .. } => Stmt::ExprStmt {
                    span: expr.span.clone(),
                    expr,
                },
                _ => Stmt::Return {
                    span: expr.span.clone(),
                    value: Some(expr),
                },
            };
            Some(Block {
                span: start_span.merge(&end_span),
                stmts: vec![stmt],
            })
        } else if self.check(&TokenKind::LBrace) {
            Some(self.parse_block())
        } else {
            None
        }
    }

    fn parse_param_list(&mut self) -> Vec<ParamDecl> {
        let mut params = Vec::new();
        self.expect(&TokenKind::LParen, "Expected '(' starting parameter list.");
        if !self.check(&TokenKind::RParen) {
            loop {
                params.push(self.parse_param());
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
        }
        self.expect(&TokenKind::RParen, "Expected ')' closing parameter list.");
        params
    }

    fn parse_param(&mut self) -> ParamDecl {
        let attributes = self.parse_attribute_sections();
        let start_span = self.current_span();
        let is_params = self.match_kind(&TokenKind::Params);
        let ty = self.parse_type_ref();
        let name = self.expect_ident("Expected parameter name.");
        let default_value = if self.match_kind(&TokenKind::Assign) {
            Some(self.parse_expr(0))
        } else {
            None
        };
        let end_span = self.previous_span();
        let explicit_constraint = Self::extract_explicit_borrow(&attributes);

        ParamDecl {
            id: SymbolId(0),
            span: start_span.merge(&end_span),
            attributes,
            is_params,
            ty,
            name,
            default_value,
            explicit_constraint,
            inferred_borrow: explicit_constraint.unwrap_or(BorrowMode::Unresolved),
        }
    }

    // ========================================================================
    // 5. TYPE REFERENCES & GENERIC CONSTRAINTS
    // ========================================================================

    pub fn parse_type_ref(&mut self) -> TypeRef {
        let start_span = self.current_span();
        let mut path = Vec::new();
        let mut is_primitive_keyword = false;

        if let Some(kw_str) = self.peek(0).kind.is_primitive_type_keyword() {
            self.advance();
            path.push(kw_str.to_string());
            is_primitive_keyword = true;
        } else {
            path.push(self.expect_ident("Expected type name."));
            while self.match_kind(&TokenKind::Dot) || self.match_kind(&TokenKind::ColonColon) {
                path.push(self.expect_ident("Expected type segment after '.' or '::'."));
            }
        }

        let mut type_args = Vec::new();
        if self.match_kind(&TokenKind::Lt) {
            while !self.is_at_end() && !self.check(&TokenKind::Gt) {
                type_args.push(self.parse_type_ref());
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect(&TokenKind::Gt, "Expected '>' closing generic type arguments.");
        }

        let is_nullable = self.match_kind(&TokenKind::Question);
        let end_span = self.previous_span();

        TypeRef {
            span: start_span.merge(&end_span),
            path,
            type_args,
            is_nullable,
            is_primitive_keyword,
        }
    }

    fn parse_type_params(&mut self) -> Vec<String> {
        let mut params = Vec::new();
        if self.match_kind(&TokenKind::Lt) {
            while !self.is_at_end() && !self.check(&TokenKind::Gt) {
                params.push(self.expect_ident("Expected generic type parameter name."));
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect(&TokenKind::Gt, "Expected '>' after generic type parameters.");
        }
        params
    }

    fn parse_type_constraints(&mut self) -> Vec<TypeConstraint> {
        let mut constraints = Vec::new();
        while self.match_kind(&TokenKind::Where) {
            let type_param = self.expect_ident("Expected type parameter name after 'where'.");
            self.expect(&TokenKind::Colon, "Expected ':' in generic type constraint.");
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

    // ========================================================================
    // 6. STATEMENTS & CONTROL FLOW
    // ========================================================================

    fn parse_block(&mut self) -> Block {
        let start_span = self.current_span();
        self.expect(&TokenKind::LBrace, "Expected '{' starting block.");
        let mut stmts = Vec::new();
        while !self.is_at_end() && !self.check(&TokenKind::RBrace) {
            let prev = self.pos;
            stmts.push(self.parse_stmt());
            if self.pos == prev {
                self.advance();
            }
        }
        let end_span = self.expect(&TokenKind::RBrace, "Expected '}' closing block.");
        Block {
            span: start_span.merge(&end_span),
            stmts,
        }
    }

    fn parse_stmt(&mut self) -> Stmt {
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
            let name = self.expect_ident("Expected variable name in 'using' resource declaration.");
            self.expect(&TokenKind::Assign, "Expected '=' in 'using' resource declaration.");
            let init = self.parse_expr(0);
            let end_span = self.consume_semicolon("Expected ';' after 'using' resource declaration.");
            return Stmt::UsingResource {
                span: start_span.merge(&end_span),
                symbol_id: SymbolId(0),
                name,
                explicit_type,
                init,
                inferred_mut: false,
            };
        }

        if self.match_kind(&TokenKind::Var) {
            let name = self.expect_ident("Expected variable name after 'var'.");
            self.expect(&TokenKind::Assign, "Expected '=' in local variable declaration.");
            let init = self.parse_expr(0);
            let end_span = self.consume_semicolon("Expected ';' after local variable declaration.");
            return Stmt::LocalVar {
                span: start_span.merge(&end_span),
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
            let cond = self.parse_expr(0);
            self.expect(&TokenKind::RParen, "Expected ')' after 'if' condition.");
            let then_branch = Box::new(self.parse_stmt());
            let else_branch = if self.match_kind(&TokenKind::Else) {
                Some(Box::new(self.parse_stmt()))
            } else {
                None
            };
            let end_span = self.previous_span();
            return Stmt::If {
                span: start_span.merge(&end_span),
                cond,
                then_branch,
                else_branch,
            };
        }

        if self.match_kind(&TokenKind::While) {
            self.expect(&TokenKind::LParen, "Expected '(' after 'while'.");
            let cond = self.parse_expr(0);
            self.expect(&TokenKind::RParen, "Expected ')' after 'while' condition.");
            let body = Box::new(self.parse_stmt());
            let end_span = self.previous_span();
            return Stmt::While {
                span: start_span.merge(&end_span),
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
            self.expect(&TokenKind::In, "Expected 'in' inside 'foreach' header.");
            let collection = self.parse_expr(0);
            self.expect(&TokenKind::RParen, "Expected ')' closing 'foreach' header.");
            let body = Box::new(self.parse_stmt());
            let end_span = self.previous_span();
            return Stmt::ForEach {
                span: start_span.merge(&end_span),
                item_symbol: SymbolId(0),
                item_type,
                item_name,
                collection,
                body,
                iter_borrow_mode: BorrowMode::ReadBorrow,
            };
        }

        if self.match_kind(&TokenKind::Return) {
            let value = if !self.check(&TokenKind::Semicolon) {
                Some(self.parse_expr(0))
            } else {
                None
            };
            let end_span = self.consume_semicolon("Expected ';' after return statement.");
            return Stmt::Return {
                span: start_span.merge(&end_span),
                value,
            };
        }

        if self.match_kind(&TokenKind::Throw) {
            let error_expr = self.parse_expr(0);
            let end_span = self.consume_semicolon("Expected ';' after throw statement.");
            return Stmt::Throw {
                span: start_span.merge(&end_span),
                error_expr,
            };
        }

        if self.match_kind(&TokenKind::Try) {
            let try_block = self.parse_block();
            let mut catches = Vec::new();
            while self.match_kind(&TokenKind::Catch) {
                let catch_start = self.previous_span();
                self.expect(&TokenKind::LParen, "Expected '(' after 'catch'.");
                let error_type = self.parse_type_ref();
                let var_name = if self.is_ident_at(0) {
                    Some(self.expect_ident("Expected catch variable identifier."))
                } else {
                    None
                };
                self.expect(&TokenKind::RParen, "Expected ')' after catch declaration.");
                let body = self.parse_block();
                let catch_end = self.previous_span();
                catches.push(CatchArm {
                    span: catch_start.merge(&catch_end),
                    error_type,
                    var_name,
                    body,
                });
            }
            let end_span = self.previous_span();
            return Stmt::TryCatch {
                span: start_span.merge(&end_span),
                try_block,
                catches,
            };
        }

        // Check for explicitly typed local variable declaration: `TypeRef ident = expr;`
        if self.looks_like_typed_local_var() {
            let explicit_type = Some(self.parse_type_ref());
            let name = self.expect_ident("Expected local variable name.");
            self.expect(&TokenKind::Assign, "Expected '=' in local variable declaration.");
            let init = self.parse_expr(0);
            let end_span = self.consume_semicolon("Expected ';' after local variable declaration.");
            return Stmt::LocalVar {
                span: start_span.merge(&end_span),
                symbol_id: SymbolId(0),
                name,
                explicit_type,
                init,
                inferred_mut: false,
                inferred_type: None,
            };
        }

        let expr = self.parse_expr(0);
        let end_span = self.consume_semicolon("Expected ';' after expression statement.");
        Stmt::ExprStmt {
            span: start_span.merge(&end_span),
            expr,
        }
    }

    fn looks_like_typed_local_var(&self) -> bool {
        if self.peek(0).kind.is_primitive_type_keyword().is_some() {
            let offset = if self.peek(1).kind == TokenKind::Question {
                2
            } else {
                1
            };
            return self.is_ident_at(offset) && self.peek(offset + 1).kind == TokenKind::Assign;
        }

        if !self.is_ident_at(0) {
            return false;
        }

        // Scan ahead past `Ident(.Ident)*(<...>)?(\?)?` and check if followed by `Ident =`
        let mut idx = 1;
        while matches!(self.peek(idx).kind, TokenKind::Dot | TokenKind::ColonColon) {
            idx += 1;
            if !self.is_ident_at(idx) {
                return false;
            }
            idx += 1;
        }

        if self.peek(idx).kind == TokenKind::Lt {
            let mut depth = 1;
            idx += 1;
            while idx < self.tokens.len() && depth > 0 {
                match self.peek(idx).kind {
                    TokenKind::Lt => depth += 1,
                    TokenKind::Gt => depth -= 1,
                    TokenKind::Semicolon | TokenKind::LBrace | TokenKind::RBrace => return false,
                    _ => {}
                }
                idx += 1;
            }
        }

        if self.peek(idx).kind == TokenKind::Question {
            idx += 1;
        }

        self.is_ident_at(idx) && self.peek(idx + 1).kind == TokenKind::Assign
    }

    // ========================================================================
    // 7. PRATT EXPRESSION PARSER (PRECEDENCE CLIMBING)
    // ========================================================================

    pub fn parse_expr(&mut self, min_bp: u8) -> Expr {
        let mut lhs = self.parse_prefix_expr();

        loop {
            // Postfix `switch` expression: `scrutinee switch { Pattern => Expr, ... }`
            if self.check(&TokenKind::Switch) && min_bp <= 2 {
                self.advance();
                lhs = self.parse_switch_expr(lhs);
                continue;
            }

            // Postfix operators: `.`, `?.`, `[...]`, `..`
            if let Some(post_bp) = self.postfix_binding_power(&self.peek(0).kind) {
                if post_bp < min_bp {
                    break;
                }
                lhs = self.parse_postfix_op(lhs);
                continue;
            }

            // Infix `is` pattern test: `expr is Pattern`
            if self.check(&TokenKind::Is) && 14 >= min_bp {
                self.advance();
                let pattern = self.parse_pattern();
                let span = lhs.span.merge(&self.previous_span());
                lhs = Expr::new(
                    span,
                    ExprKind::IsPattern {
                        expr: Box::new(lhs),
                        pattern,
                    },
                );
                continue;
            }

            // Binary & Assignment operators
            if let Some((l_bp, r_bp)) = self.infix_binding_power(&self.peek(0).kind) {
                if l_bp < min_bp {
                    break;
                }
                let op_tok = self.advance();
                let rhs = self.parse_expr(r_bp);
                let span = lhs.span.merge(&rhs.span);
                lhs = self.build_infix_expr(span, op_tok.kind, lhs, rhs);
                continue;
            }

            break;
        }

        lhs
    }

    fn parse_prefix_expr(&mut self) -> Expr {
        let start_span = self.current_span();

        // Single-parameter lambda: `x => ...`
        if self.is_ident_at(0) && self.peek(1).kind == TokenKind::FatArrow {
            let param = self.expect_ident("Expected lambda parameter.");
            self.advance(); // consume '=>'
            let body = if self.check(&TokenKind::LBrace) {
                LambdaBody::Block(self.parse_block())
            } else {
                LambdaBody::Expr(Box::new(self.parse_expr(0)))
            };
            let span = start_span.merge(&self.previous_span());
            return Expr::new(
                span,
                ExprKind::Lambda {
                    params: vec![param],
                    body,
                },
            );
        }

        // Parenthesized lambda `() => ...` or `(a, b) => ...`
        if self.looks_like_paren_lambda() {
            self.expect(&TokenKind::LParen, "Expected '(' in lambda.");
            let mut params = Vec::new();
            if !self.check(&TokenKind::RParen) {
                loop {
                    params.push(self.expect_ident("Expected lambda parameter name."));
                    if !self.match_kind(&TokenKind::Comma) {
                        break;
                    }
                }
            }
            self.expect(&TokenKind::RParen, "Expected ')' after lambda parameters.");
            self.expect(&TokenKind::FatArrow, "Expected '=>' after lambda parameters.");
            let body = if self.check(&TokenKind::LBrace) {
                LambdaBody::Block(self.parse_block())
            } else {
                LambdaBody::Expr(Box::new(self.parse_expr(0)))
            };
            let span = start_span.merge(&self.previous_span());
            return Expr::new(span, ExprKind::Lambda { params, body });
        }

        // Prefix unary operators: `!`, `-`, `await`, `^`
        if let Some(unary_op) = match self.peek(0).kind {
            TokenKind::Bang => Some(UnaryOp::Not),
            TokenKind::Minus => Some(UnaryOp::Neg),
            TokenKind::Await => Some(UnaryOp::Await),
            TokenKind::Caret => Some(UnaryOp::FromEnd),
            _ => None,
        } {
            self.advance();
            let operand = self.parse_expr(22);
            let span = start_span.merge(&operand.span);
            return Expr::new(
                span,
                ExprKind::Unary {
                    op: unary_op,
                    operand: Box::new(operand),
                },
            );
        }

        // Prefix range `..end`
        if self.match_kind(&TokenKind::DotDot) {
            let end_expr = if self.can_start_expr(&self.peek(0).kind) {
                Some(Box::new(self.parse_expr(16)))
            } else {
                None
            };
            let span = start_span.merge(&self.previous_span());
            return Expr::new(
                span,
                ExprKind::RangeSlice {
                    target: None,
                    start: None,
                    end: end_expr,
                },
            );
        }

        // `new TypeRef(args)`
        if self.match_kind(&TokenKind::New) {
            let ty = self.parse_type_ref();
            let args = self.parse_arg_list();
            let span = start_span.merge(&self.previous_span());
            return Expr::new(
                span,
                ExprKind::Construct {
                    ty,
                    args,
                    resolved_ctor: None,
                    primitive_lowering: PrimitiveLowering::None,
                },
            );
        }

        // Parenthesized expression `(expr)`
        if self.match_kind(&TokenKind::LParen) {
            let inner = self.parse_expr(0);
            let end_span = self.expect(&TokenKind::RParen, "Expected ')' after expression.");
            return Expr {
                span: start_span.merge(&end_span),
                ..inner
            };
        }

        // Primary literals & identifiers
        let tok = self.advance();
        match tok.kind {
            TokenKind::IntLit(v) => Expr::new(tok.span, ExprKind::Literal(LiteralValue::Int(v))),
            TokenKind::FloatLit(v) => {
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Float(v)))
            }
            TokenKind::DecimalLit(s) => {
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Decimal(s)))
            }
            TokenKind::StringLit(s) => {
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::String(s)))
            }
            TokenKind::CharLit(c) => Expr::new(tok.span, ExprKind::Literal(LiteralValue::Char(c))),
            TokenKind::BoolLit(b) => Expr::new(tok.span, ExprKind::Literal(LiteralValue::Bool(b))),
            TokenKind::Null => Expr::new(tok.span, ExprKind::Literal(LiteralValue::Null)),
            TokenKind::InterpString(parts) => {
                Expr::new(tok.span, ExprKind::InterpolatedString(parts))
            }
            TokenKind::This => Expr::new(tok.span, ExprKind::This),
            TokenKind::Base => Expr::new(tok.span, ExprKind::Base),
            TokenKind::Ident(name) => {
                if self.check(&TokenKind::LParen) {
                    let args = self.parse_arg_list();
                    let span = tok.span.merge(&self.previous_span());
                    Expr::new(
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
                    )
                } else {
                    Expr::new(
                        tok.span,
                        ExprKind::Identifier {
                            name,
                            resolved_symbol: None,
                        },
                    )
                }
            }
            _ => {
                self.diag.report_syntax_error(
                    tok.span.clone(),
                    format!("Unexpected token '{}' in expression.", tok.lexeme),
                );
                Expr::new(tok.span, ExprKind::Literal(LiteralValue::Null))
            }
        }
    }

    fn parse_postfix_op(&mut self, lhs: Expr) -> Expr {
        let tok_kind = self.peek(0).kind.clone();
        match tok_kind {
            TokenKind::Dot | TokenKind::NullCond => {
                let is_null_cond = tok_kind == TokenKind::NullCond;
                self.advance();
                let member_name = self.expect_ident("Expected member name after '.' or '?.'.");

                let type_args = if self.check(&TokenKind::Lt) && self.looks_like_generic_call_args() {
                    self.parse_type_args()
                } else {
                    Vec::new()
                };

                if self.check(&TokenKind::LParen) {
                    let args = self.parse_arg_list();
                    let span = lhs.span.merge(&self.previous_span());
                    Expr::new(
                        span,
                        ExprKind::MethodCall {
                            receiver: Some(Box::new(lhs)),
                            method_name: member_name,
                            type_args,
                            args,
                            is_null_conditional: is_null_cond,
                            resolved_overload: None,
                            primitive_lowering: PrimitiveLowering::None,
                        },
                    )
                } else {
                    let span = lhs.span.merge(&self.previous_span());
                    Expr::new(
                        span,
                        ExprKind::MemberAccess {
                            target: Box::new(lhs),
                            member: member_name,
                            is_null_conditional: is_null_cond,
                            resolved_symbol: None,
                        },
                    )
                }
            }
            TokenKind::LBracket => {
                self.advance(); // consume '['
                let mut indices = Vec::new();
                if !self.check(&TokenKind::RBracket) {
                    loop {
                        let arg_start = self.current_span();
                        let expr = self.parse_expr(0);
                        indices.push(ArgNode {
                            span: arg_start.merge(&expr.span),
                            name: None,
                            expr,
                        });
                        if !self.match_kind(&TokenKind::Comma) {
                            break;
                        }
                    }
                }
                let end_span = self.expect(&TokenKind::RBracket, "Expected ']' after index/slice.");
                let full_span = lhs.span.merge(&end_span);

                // If indexing with a single `a..b` range expression, fold into `ExprKind::RangeSlice`
                if indices.len() == 1 {
                    if let ExprKind::RangeSlice { start, end, .. } = &indices[0].expr.kind {
                        return Expr::new(
                            full_span,
                            ExprKind::RangeSlice {
                                target: Some(Box::new(lhs)),
                                start: start.clone(),
                                end: end.clone(),
                            },
                        );
                    }
                }

                Expr::new(
                    full_span,
                    ExprKind::IndexAccess {
                        target: Box::new(lhs),
                        indices,
                    },
                )
            }
            TokenKind::DotDot => {
                self.advance(); // consume '..'
                let end_expr = if self.can_start_expr(&self.peek(0).kind)
                    && !matches!(self.peek(0).kind, TokenKind::RBracket | TokenKind::Comma | TokenKind::RParen | TokenKind::Semicolon)
                {
                    Some(Box::new(self.parse_expr(17)))
                } else {
                    None
                };
                let span = lhs.span.merge(&self.previous_span());
                Expr::new(
                    span,
                    ExprKind::RangeSlice {
                        target: None,
                        start: Some(Box::new(lhs)),
                        end: end_expr,
                    },
                )
            }
            _ => lhs,
        }
    }

    fn parse_switch_expr(&mut self, scrutinee: Expr) -> Expr {
        self.expect(&TokenKind::LBrace, "Expected '{' in switch expression.");
        let mut arms = Vec::new();
        while !self.is_at_end() && !self.check(&TokenKind::RBrace) {
            let arm_start = self.current_span();
            let pattern = self.parse_pattern();
            let guard = if self.match_kind(&TokenKind::When) {
                Some(self.parse_expr(0))
            } else {
                None
            };
            self.expect(&TokenKind::FatArrow, "Expected '=>' in switch arm.");
            let body = self.parse_expr(0);
            let arm_end = body.span.clone();
            arms.push(SwitchArmNode {
                span: arm_start.merge(&arm_end),
                pattern,
                guard,
                body,
            });
            if !self.match_kind(&TokenKind::Comma) {
                break;
            }
        }
        let end_span = self.expect(&TokenKind::RBrace, "Expected '}' closing switch expression.");
        let full_span = scrutinee.span.merge(&end_span);
        Expr::new(
            full_span,
            ExprKind::Switch {
                scrutinee: Box::new(scrutinee),
                arms,
            },
        )
    }

    fn parse_pattern(&mut self) -> Pattern {
        let start_span = self.current_span();

        if self.match_kind(&TokenKind::Underscore) {
            return Pattern::Wildcard(start_span);
        }
        if self.match_kind(&TokenKind::Null) {
            return Pattern::Null(start_span);
        }

        match self.peek(0).kind.clone() {
            TokenKind::IntLit(v) => {
                self.advance();
                return Pattern::Literal(start_span, LiteralValue::Int(v));
            }
            TokenKind::StringLit(s) => {
                self.advance();
                return Pattern::Literal(start_span, LiteralValue::String(s));
            }
            TokenKind::BoolLit(b) => {
                self.advance();
                return Pattern::Literal(start_span, LiteralValue::Bool(b));
            }
            _ => {}
        }

        let ty = self.parse_type_ref();
        let bind_name = if self.is_ident_at(0) {
            Some(self.expect_ident("Expected pattern variable name."))
        } else {
            None
        };

        let mut property_patterns = Vec::new();
        if self.match_kind(&TokenKind::LBrace) {
            while !self.is_at_end() && !self.check(&TokenKind::RBrace) {
                let field_name = self.expect_ident("Expected property name in pattern.");
                self.expect(&TokenKind::Colon, "Expected ':' after property name in pattern.");
                let sub_pat = self.parse_pattern();
                property_patterns.push(PropertyPatternField {
                    field_name,
                    pattern: sub_pat,
                });
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect(&TokenKind::RBrace, "Expected '}' closing property pattern.");
        }

        let end_span = self.previous_span();
        Pattern::TypePattern {
            span: start_span.merge(&end_span),
            ty,
            bind_name,
            property_patterns,
        }
    }

    fn build_infix_expr(&self, span: SourceSpan, op: TokenKind, lhs: Expr, rhs: Expr) -> Expr {
        match op {
            TokenKind::Assign => Expr::new(
                span,
                ExprKind::Assignment {
                    op: AssignOp::Assign,
                    target: Box::new(lhs),
                    value: Box::new(rhs),
                },
            ),
            TokenKind::PlusAssign => Expr::new(
                span,
                ExprKind::Assignment {
                    op: AssignOp::AddAssign,
                    target: Box::new(lhs),
                    value: Box::new(rhs),
                },
            ),
            TokenKind::MinusAssign => Expr::new(
                span,
                ExprKind::Assignment {
                    op: AssignOp::SubAssign,
                    target: Box::new(lhs),
                    value: Box::new(rhs),
                },
            ),
            TokenKind::StarAssign => Expr::new(
                span,
                ExprKind::Assignment {
                    op: AssignOp::MulAssign,
                    target: Box::new(lhs),
                    value: Box::new(rhs),
                },
            ),
            TokenKind::SlashAssign => Expr::new(
                span,
                ExprKind::Assignment {
                    op: AssignOp::DivAssign,
                    target: Box::new(lhs),
                    value: Box::new(rhs),
                },
            ),
            TokenKind::NullCoalesceEq => Expr::new(
                span,
                ExprKind::Assignment {
                    op: AssignOp::NullCoalesceEq,
                    target: Box::new(lhs),
                    value: Box::new(rhs),
                },
            ),
            TokenKind::NullCoalesce => Expr::new(
                span,
                ExprKind::NullCoalesce {
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::OrOr => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Or,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::AndAnd => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::And,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Eq => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Eq,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Neq => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Neq,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Lt => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Lt,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Gt => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Gt,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Lte => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Lte,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Gte => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Gte,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Plus => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Add,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Minus => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Sub,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Star => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Mul,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Slash => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Div,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            TokenKind::Percent => Expr::new(
                span,
                ExprKind::Binary {
                    op: BinaryOp::Rem,
                    left: Box::new(lhs),
                    right: Box::new(rhs),
                },
            ),
            _ => lhs,
        }
    }

    fn infix_binding_power(&self, kind: &TokenKind) -> Option<(u8, u8)> {
        match kind {
            TokenKind::Assign
            | TokenKind::PlusAssign
            | TokenKind::MinusAssign
            | TokenKind::StarAssign
            | TokenKind::SlashAssign
            | TokenKind::NullCoalesceEq => Some((2, 1)),
            TokenKind::NullCoalesce => Some((4, 3)),
            TokenKind::OrOr => Some((6, 7)),
            TokenKind::AndAnd => Some((8, 9)),
            TokenKind::Eq | TokenKind::Neq => Some((10, 11)),
            TokenKind::Lt | TokenKind::Gt | TokenKind::Lte | TokenKind::Gte => Some((14, 15)),
            TokenKind::Plus | TokenKind::Minus => Some((18, 19)),
            TokenKind::Star | TokenKind::Slash | TokenKind::Percent => Some((20, 21)),
            _ => None,
        }
    }

    fn postfix_binding_power(&self, kind: &TokenKind) -> Option<u8> {
        match kind {
            TokenKind::DotDot => Some(16),
            TokenKind::Dot | TokenKind::NullCond | TokenKind::LBracket => Some(24),
            _ => None,
        }
    }

    // ========================================================================
    // 8. HELPER UTILITIES
    // ========================================================================

    fn parse_arg_list(&mut self) -> Vec<ArgNode> {
        let mut args = Vec::new();
        self.expect(&TokenKind::LParen, "Expected '(' starting argument list.");
        if !self.check(&TokenKind::RParen) {
            loop {
                let arg_start = self.current_span();
                let name = if self.is_ident_at(0) && self.peek(1).kind == TokenKind::Colon {
                    let n = self.expect_ident("Expected argument name.");
                    self.advance(); // consume ':'
                    Some(n)
                } else {
                    None
                };
                let expr = self.parse_expr(0);
                let arg_end = expr.span.clone();
                args.push(ArgNode {
                    span: arg_start.merge(&arg_end),
                    name,
                    expr,
                });
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
        }
        self.expect(&TokenKind::RParen, "Expected ')' closing argument list.");
        args
    }

    fn parse_type_args(&mut self) -> Vec<TypeRef> {
        let mut args = Vec::new();
        self.expect(&TokenKind::Lt, "Expected '<' starting type arguments.");
        while !self.is_at_end() && !self.check(&TokenKind::Gt) {
            args.push(self.parse_type_ref());
            if !self.match_kind(&TokenKind::Comma) {
                break;
            }
        }
        self.expect(&TokenKind::Gt, "Expected '>' closing type arguments.");
        args
    }

    fn looks_like_generic_call_args(&self) -> bool {
        if self.peek(0).kind != TokenKind::Lt {
            return false;
        }
        let mut idx = 1;
        let mut depth = 1;
        while idx < self.tokens.len() && depth > 0 {
            match self.peek(idx).kind {
                TokenKind::Lt => depth += 1,
                TokenKind::Gt => depth -= 1,
                TokenKind::Semicolon | TokenKind::LBrace | TokenKind::RBrace => return false,
                _ => {}
            }
            idx += 1;
        }
        depth == 0 && self.peek(idx).kind == TokenKind::LParen
    }

    fn looks_like_paren_lambda(&self) -> bool {
        if self.peek(0).kind != TokenKind::LParen {
            return false;
        }
        let mut idx = 1;
        if self.peek(idx).kind == TokenKind::RParen {
            return self.peek(idx + 1).kind == TokenKind::FatArrow;
        }
        while idx < self.tokens.len() {
            if !self.is_ident_at(idx) {
                return false;
            }
            idx += 1;
            if self.peek(idx).kind == TokenKind::Comma {
                idx += 1;
            } else if self.peek(idx).kind == TokenKind::RParen {
                return self.peek(idx + 1).kind == TokenKind::FatArrow;
            } else {
                return false;
            }
        }
        false
    }

    fn can_start_expr(&self, kind: &TokenKind) -> bool {
        matches!(
            kind,
            TokenKind::Ident(_)
                | TokenKind::IntLit(_)
                | TokenKind::FloatLit(_)
                | TokenKind::DecimalLit(_)
                | TokenKind::StringLit(_)
                | TokenKind::CharLit(_)
                | TokenKind::BoolLit(_)
                | TokenKind::InterpString(_)
                | TokenKind::Null
                | TokenKind::This
                | TokenKind::Base
                | TokenKind::New
                | TokenKind::LParen
                | TokenKind::Bang
                | TokenKind::Minus
                | TokenKind::Caret
                | TokenKind::Await
        )
    }

    fn parse_qualified_ident(&mut self) -> Vec<String> {
        let mut parts = Vec::new();
        parts.push(self.expect_ident("Expected identifier."));
        while self.match_kind(&TokenKind::Dot) || self.match_kind(&TokenKind::ColonColon) {
            parts.push(self.expect_ident("Expected identifier after '.' or '::'."));
        }
        parts
    }

    fn parse_access_modifier(&mut self, default: AccessMod) -> AccessMod {
        self.parse_optional_access_modifier().unwrap_or(default)
    }

    fn parse_optional_access_modifier(&mut self) -> Option<AccessMod> {
        if self.match_kind(&TokenKind::Public) {
            Some(AccessMod::Public)
        } else if self.match_kind(&TokenKind::Internal) {
            Some(AccessMod::Internal)
        } else if self.match_kind(&TokenKind::Protected) {
            Some(AccessMod::Protected)
        } else if self.match_kind(&TokenKind::Private) {
            Some(AccessMod::Private)
        } else {
            None
        }
    }

    fn extract_primitive_lowering(attrs: &[AttributeNode]) -> PrimitiveLowering {
        for attr in attrs {
            match attr.short_name() {
                "InlineTemplate" => {
                    if let Some(tpl) = attr.first_string_arg() {
                        return PrimitiveLowering::InlineTemplate {
                            template: tpl.to_string(),
                        };
                    }
                }
                "MapsTo" => {
                    if let Some(target) = attr.first_string_arg() {
                        return PrimitiveLowering::DirectSymbol {
                            rust_path: target.to_string(),
                        };
                    }
                }
                _ => {}
            }
        }
        PrimitiveLowering::None
    }

    fn extract_explicit_borrow(attrs: &[AttributeNode]) -> Option<BorrowMode> {
        for attr in attrs {
            match attr.short_name() {
                "Borrows" => return Some(BorrowMode::ReadBorrow),
                "Mutates" => return Some(BorrowMode::MutBorrow),
                "Moves" => return Some(BorrowMode::OwnedMove),
                _ => {}
            }
        }
        None
    }

    fn is_at_end(&self) -> bool {
        matches!(self.peek(0).kind, TokenKind::Eof)
    }

    fn peek(&self, offset: usize) -> &Token {
        self.tokens
            .get(self.pos + offset)
            .unwrap_or_else(|| self.tokens.last().unwrap())
    }

    fn current_span(&self) -> SourceSpan {
        self.peek(0).span.clone()
    }

    fn previous_span(&self) -> SourceSpan {
        if self.pos > 0 {
            self.tokens[self.pos - 1].span.clone()
        } else {
            self.current_span()
        }
    }

    fn check(&self, expected: &TokenKind) -> bool {
        std::mem::discriminant(&self.peek(0).kind) == std::mem::discriminant(expected)
    }

    fn is_ident_at(&self, offset: usize) -> bool {
        matches!(
            self.peek(offset).kind,
            TokenKind::Ident(_)
                | TokenKind::Get
                | TokenKind::Set
                | TokenKind::Service
                | TokenKind::Shared
                | TokenKind::Primitive
                | TokenKind::Extensible
        )
    }

    fn match_kind(&mut self, expected: &TokenKind) -> bool {
        if self.check(expected) {
            self.advance();
            true
        } else {
            false
        }
    }

    fn advance(&mut self) -> Token {
        let tok = self.peek(0).clone();
        if !self.is_at_end() {
            self.pos += 1;
        }
        tok
    }

    fn expect(&mut self, expected: &TokenKind, message: &str) -> SourceSpan {
        if self.check(expected) {
            self.advance().span
        } else {
            let span = self.current_span();
            self.diag.report_syntax_error(
                span.clone(),
                format!("{} Found '{}'.", message, self.peek(0).lexeme),
            );
            span
        }
    }

    fn expect_ident(&mut self, message: &str) -> String {
        match &self.peek(0).kind {
            TokenKind::Ident(_)
            | TokenKind::Get
            | TokenKind::Set
            | TokenKind::Service
            | TokenKind::Shared
            | TokenKind::Primitive
            | TokenKind::Extensible => self.advance().lexeme,
            _ => {
                let span = self.current_span();
                self.diag.report_syntax_error(
                    span,
                    format!("{} Found '{}'.", message, self.peek(0).lexeme),
                );
                self.advance().lexeme
            }
        }
    }

    fn consume_semicolon(&mut self, message: &str) -> SourceSpan {
        self.expect(&TokenKind::Semicolon, message)
    }
}

```

---

### `tests/m1_parser_tests.rs`

```rust
use rsharpc::diagnostics::DiagnosticEngine;
use rsharpc::frontend::{
    AccessMod, BorrowMode, EffectSignature, ExprKind, Lexer, MemberDecl, Parser,
    PrimitiveLowering, Stmt, TypeKind,
};

fn parse_source(filename: &str, src: &str) -> (rsharpc::frontend::CompilationUnit, DiagnosticEngine) {
    let mut diag = DiagnosticEngine::new();
    let tokens = {
        let mut lexer = Lexer::new(src, 0, filename, &mut diag);
        lexer.tokenize()
    };
    let unit = {
        let mut parser = Parser::new(tokens, 0, filename, &mut diag);
        parser.parse_compilation_unit()
    };
    (unit, diag)
}

#[test]
fn test_parses_archetypes_throws_and_decimal_literals() {
    let source = r#"
namespace Commerce.Checkout;

using Commerce.Domain;
extern using rust_decimal::Decimal as Decimal;

public record Order(int Id, decimal Total);
public record ValidationError(string Reason);

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
}
"#;

    let (unit, diag) = parse_source("OrderHandler.rsharp", source);
    assert!(!diag.has_errors(), "Unexpected syntax errors: {}", diag.format_all());
    assert_eq!(unit.namespace, vec!["Commerce", "Checkout"]);
    assert_eq!(unit.imports.len(), 2);
    assert!(unit.imports[1].is_extern_crate);
    assert_eq!(unit.imports[1].path, vec!["rust_decimal", "Decimal"]);
    assert_eq!(unit.imports[1].alias.as_deref(), Some("Decimal"));

    assert_eq!(unit.types.len(), 3);
    assert_eq!(unit.types[0].name, "Order");
    assert_eq!(unit.types[0].kind, TypeKind::Record { is_struct: false });
    assert_eq!(unit.types[0].primary_ctor_params.len(), 2);

    let service = &unit.types[2];
    assert_eq!(service.name, "OrderHandler");
    assert_eq!(service.kind, TypeKind::ServiceClass);
    assert_eq!(service.access, AccessMod::Public);

    // Check `Checkout` method has `throws ValidationError` parsed into Fallible EffectSignature
    let checkout_method = service
        .members
        .iter()
        .find_map(|m| match m {
            MemberDecl::Method(md) if md.name == "Checkout" => Some(md),
            _ => None,
        })
        .expect("Expected Checkout method");

    assert_eq!(
        checkout_method.explicit_throws.as_ref().unwrap().short_name(),
        "ValidationError"
    );
    assert!(matches!(
        checkout_method.inferred_effect,
        EffectSignature::Fallible { .. }
    ));
}

#[test]
fn test_parses_primitive_stdlib_declarations_and_borrow_attributes() {
    let stub_src = r#"
namespace RustSharp.Core;

[MapsTo("std::vec::Vec")]
[ParamType("&[{T}]")]
public primitive class List<T> : IEnumerable<T>
{
    [InlineTemplate("Vec::new()")]
    public extern List();

    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Count { get; }

    [Mutates]
    [MapsTo("push")]
    public extern void Add([Moves] T item);
}
"#;

    let (unit, diag) = parse_source("RustSharp.Core.d.rsharp", stub_src);
    assert!(!diag.has_errors(), "Unexpected syntax errors: {}", diag.format_all());
    assert!(unit.is_ambient_stub);

    let list_decl = &unit.types[0];
    assert_eq!(list_decl.name, "List");
    assert_eq!(
        list_decl.kind,
        TypeKind::PrimitiveClass { is_struct: false }
    );
    assert_eq!(
        list_decl.primitive_rust_target.as_deref(),
        Some("std::vec::Vec")
    );
    assert_eq!(list_decl.primitive_param_type.as_deref(), Some("&[{T}]"));

    let add_method = list_decl
        .members
        .iter()
        .find_map(|m| match m {
            MemberDecl::Method(md) if md.name == "Add" => Some(md),
            _ => None,
        })
        .expect("Expected Add method");

    assert_eq!(add_method.inferred_self_borrow, BorrowMode::MutBorrow);
    assert_eq!(
        add_method.primitive_lowering,
        PrimitiveLowering::DirectSymbol {
            rust_path: "push".to_string()
        }
    );
    assert_eq!(add_method.params[0].inferred_borrow, BorrowMode::OwnedMove);
}

#[test]
fn test_parses_range_slicing_null_coalescing_and_switch_expressions() {
    let src = r#"
namespace Telemetry.Ingest;

public static class PacketParser
{
    public static int Inspect(ReadOnlySpan<byte> buffer, int? overrideLen)
    {
        ReadOnlySpan<byte> header = buffer[0..16];
        int effective = overrideLen ?? header.Length;
        return effective switch
        {
            0 => -1,
            16 => 1,
            _ => 0,
        };
    }
}
"#;

    let (unit, diag) = parse_source("PacketParser.rsharp", src);
    assert!(!diag.has_errors(), "Unexpected syntax errors: {}", diag.format_all());

    let method = match &unit.types[0].members[0] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected method"),
    };
    let body = method.body.as_ref().unwrap();
    assert_eq!(body.stmts.len(), 3);

    // Statement 1: `ReadOnlySpan<byte> header = buffer[0..16];`
    match &body.stmts[0] {
        Stmt::LocalVar { name, init, .. } => {
            assert_eq!(name, "header");
            assert!(matches!(init.kind, ExprKind::RangeSlice { .. }));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 2: `int effective = overrideLen ?? header.Length;`
    match &body.stmts[1] {
        Stmt::LocalVar { name, init, .. } => {
            assert_eq!(name, "effective");
            assert!(matches!(init.kind, ExprKind::NullCoalesce { .. }));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    // Statement 3: `return effective switch { ... };`
    match &body.stmts[2] {
        Stmt::Return { value: Some(expr), .. } => {
            assert!(matches!(expr.kind, ExprKind::Switch { .. }));
        }
        other => panic!("Expected Return with Switch expr, got {:?}", other),
    }
}

```

---

Would you like me to proceed with generating the raw individual files for **Milestone 2 (`src/project.rs`, `src/semantics/symbols.rs`, `src/semantics/collector.rs`, and `tests/m2_namespace_resolution_tests.rs`)** next?
