Based on the **Milestone 1–6 Implementation Plan and Repository Map (`repomap`)** for the **RustSharp Prototype Transpiler (`rsharpc`)**, the following files are needed to make this conversation a 100% self-contained, complete repository across all 6 milestones (M1–M6):

1. `Cargo.toml` — **Milestone 1 Host Workspace Configuration (`rsharpc` binary + library)**


2. `src/diagnostics.rs` — **Milestone 1/5 `SourceSpan`, `DiagnosticEngine`, and `RSHARP000`–`RSHARP005` Formatters**


3. `src/frontend/mod.rs` — **Milestone 1 Frontend Package Exports**


4. `src/frontend/tokens.rs` — **Milestone 1 `TokenKind` (`service`, `shared`, `primitive`, `extensible`, `throws`, `..`, `??`, `?.`) & `Token**`


5. `src/frontend/lexer.rs` — **Milestone 1 Hand-Written UTF-8 Lexer (`$"..."` interpolation, `10.0m` Decimal, `::`, comments)**


6. `src/frontend/ast.rs` — **Milestone 1 Multi-Pass `.rsharp` AST Nodes + Pass 2 Semantic Slots**


7. `src/frontend/parser.rs` — **Milestone 1 Recursive-Descent Declaration Parser + Pratt Expression Parser**


8. `src/semantics/symbols.rs` — **Updated Pass 1 Symbol Table (including `NamespaceNode` tree representation from the repomap)**


9. `src/semantics/mod.rs` — **Updated Semantics Module Exports (exporting `NamespaceNode`)**


10. `tests/m1_parser_tests.rs` — **Milestone 1 Verification Suite (Archetypes, `throws`, `primitive` attributes, slicing, `switch`)**


11. `tests/fixtures/commerce_workspace/Domain/Models.rsharp` — **Milestone 2/6 Cross-Namespace Domain Models Fixture (`Commerce.Domain`)**



Here are each of the files in full, individual plain-text format:

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
    Not,     // !
    Neg,     // -
    Await,   // await
    FromEnd, // ^
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
        let mut namespace = Vec::new();
        let mut imports = Vec::new();
        let mut types = Vec::new();

        // Optional `namespace Foo.Bar;`
        if self.check(&TokenKind::Namespace) {
            self.advance();
            namespace = self.parse_qualified_ident();
            self.expect(&TokenKind::Semicolon, "Expected ';' after namespace declaration.");
        }

        // `using ...;` and `extern using ...;`
        while self.check(&TokenKind::Using)
            || (self.check(&TokenKind::Extern) && self.peek_kind(1) == &TokenKind::Using)
        {
            imports.push(self.parse_import_decl());
        }

        // Top-level type declarations
        while !self.is_at_end() {
            if self.check(&TokenKind::Semicolon) {
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

        let end_span =
            self.expect(&TokenKind::Semicolon, "Expected ';' after using directive.");
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
                let path = self.parse_qualified_ident();
                let mut args = Vec::new();

                if self.match_kind(&TokenKind::LParen) {
                    while !self.check(&TokenKind::RParen) && !self.is_at_end() {
                        let name = if self. is_ident_at(0) && self.peek_kind(1) == &TokenKind::Assign
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
                    self.expect(&TokenKind::RParen, "Expected ')' after attribute arguments.");
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
            self.expect(&TokenKind::RBracket, "Expected ']' after attribute section.");
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
                format!("Expected type declaration keyword, found '{}'.", self.peek(0).lexeme),
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
                    if self.pos == member_pos && !self.check(&TokenKind::RBrace) && !self.is_at_end()
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
        if self.peek_ident(0) == Some(enclosing_type_name) && self.peek_kind(1) == &TokenKind::LParen
        {
            let ctor_name = self.expect_ident("Expected constructor name.");
            let params = self.parse_param_list();

            let base_args = if self.match_kind(&TokenKind::Colon) {
                self.expect(&TokenKind::Base, "Expected 'base' in constructor initializer.");
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
            self.expect(&TokenKind::RBracket, "Expected ']' after indexer parameters.");
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
                let end_span =
                    self.expect(&TokenKind::Semicolon, "Expected ';' after expression property.");
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
        self.expect(&TokenKind::Semicolon, "Expected ';' after field declaration.");

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
            while !self.check(&TokenKind::Gt) && !self.is_at_end() {
                params.push(self.expect_ident("Expected generic type parameter name."));
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect(&TokenKind::Gt, "Expected '>' after generic type parameters.");
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
            while !self.check(&TokenKind::Gt) && !self.is_at_end() {
                type_args.push(self.parse_type_ref());
                if !self.match_kind(&TokenKind::Comma) {
                    break;
                }
            }
            self.expect(&TokenKind::Gt, "Expected '>' after generic type arguments.");
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
            self.expect(&TokenKind::Assign, "Expected '=' in 'using' resource statement.");
            let init = self.parse_expr();
            let end = self.expect(&TokenKind::Semicolon, "Expected ';' after 'using' statement.");
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
            self.expect(&TokenKind::Assign, "Expected '=' in local variable declaration.");
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
        let end = self.expect(&TokenKind::Semicolon, "Expected ';' after expression statement.");
        Stmt::ExprStmt {
            span: start_span.merge(&end),
            expr,
        }
    }

    fn looks_like_typed_local_var(&self) -> bool {
        let saved = self.pos;
        let mut cursor = saved;

        if self.peek_kind_at(cursor).is_primitive_type_keyword().is_some() {
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
            let mut depth = 1;
            cursor += 1;
            while cursor < self.tokens.len() && depth > 0 {
                match self.peek_kind_at(cursor) {
                    TokenKind::Lt => depth += 1,
                    TokenKind::Gt => depth -= 1,
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
        let mut expr = self.parse_equality_expr();
        while self.match_kind(&TokenKind::AndAnd) {
            let right = self.parse_equality_expr();
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

        let left = self.parse_additive_expr();
        if self.match_kind(&TokenKind::DotDot) {
            let end = if self.can_start_expr() {
                Some(Box::new(self.parse_additive_expr()))
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
                    while !self.check(&TokenKind::Gt) && !self.is_at_end() {
                        args.push(self.parse_type_ref());
                        if !self.match_kind(&TokenKind::Comma) {
                            break;
                        }
                    }
                    self.expect(&TokenKind::Gt, "Expected '>' after method type arguments.");
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
                let start = self.advance().span;
                let ty = self.parse_type_ref();
                self.expect(&TokenKind::LParen, "Expected '(' after type in 'new' expression.");
                let args = self.parse_arg_list();
                let end = self.expect(&TokenKind::RParen, "Expected ')' after constructor arguments.");
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
                let start = self.advance().span;
                let inner = self.parse_expr();
                let end = self.expect(&TokenKind::RParen, "Expected ')' after parenthesized expression.");
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
                let start = self.advance().span;
                if let TokenKind::IntLit(v) = self.advance().kind {
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
        let mut depth = 1;
        cursor += 1;
        while cursor < self.tokens.len() && depth > 0 {
            match self.peek_kind_at(cursor) {
                TokenKind::Lt => depth += 1,
                TokenKind::Gt => depth -= 1,
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
            TokenKind::ValueStruct => {
                self.advance();
                "value".to_string()
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

```

---

### `src/semantics/symbols.rs`

```rust
use std::collections::{BTreeMap, HashMap};
use std::path::PathBuf;

use crate::diagnostics::SourceSpan;
use crate::frontend::ast::{
    AccessMod, BorrowMode, EffectSignature, FieldStorageMode, ImportDecl, PolymorphismStrategy,
    PrimitiveLowering, SymbolId, TypeKind, TypeRef,
};

/// Hierarchical virtual namespace tree node (`NamespaceNode` from the repomap).
#[derive(Clone, Debug, Default)]
pub struct NamespaceNode {
    pub segment: String,
    pub full_path: Vec<String>,
    pub type_ids: Vec<SymbolId>,
    pub children: BTreeMap<String, NamespaceNode>,
}

impl NamespaceNode {
    pub fn insert_type(&mut self, ns_segments: &[String], type_id: SymbolId) {
        let mut current = self;
        let mut path_so_far = Vec::new();
        for seg in ns_segments {
            path_so_far.push(seg.clone());
            current = current
                .children
                .entry(seg.clone())
                .or_insert_with(|| NamespaceNode {
                    segment: seg.clone(),
                    full_path: path_so_far.clone(),
                    type_ids: Vec::new(),
                    children: BTreeMap::new(),
                });
        }
        if !current.type_ids.contains(&type_id) {
            current.type_ids.push(type_id);
        }
    }
}

/// Metadata for a registered field or synthesized record primary-constructor member.
#[derive(Clone, Debug)]
pub struct FieldSymbol {
    pub id: SymbolId,
    pub owner_type: SymbolId,
    pub name: String,
    pub access: AccessMod,
    pub is_readonly: bool,
    pub is_static: bool,
    pub ty: TypeRef,
    pub resolved_type_id: Option<SymbolId>,
    pub storage_mode: FieldStorageMode,
    pub span: SourceSpan,
}

/// Metadata for a registered property declaration.
#[derive(Clone, Debug)]
pub struct PropertySymbol {
    pub id: SymbolId,
    pub owner_type: SymbolId,
    pub name: String,
    pub access: AccessMod,
    pub is_static: bool,
    pub is_extern: bool,
    pub has_getter: bool,
    pub has_setter: bool,
    pub setter_access: Option<AccessMod>,
    pub ty: TypeRef,
    pub resolved_type_id: Option<SymbolId>,
    pub storage_mode: FieldStorageMode,
    pub primitive_lowering: PrimitiveLowering,
    pub span: SourceSpan,
}

/// Metadata for a method or constructor parameter in the global symbol table.
#[derive(Clone, Debug)]
pub struct ParamSymbol {
    pub id: SymbolId,
    pub name: String,
    pub ty: TypeRef,
    pub resolved_type_id: Option<SymbolId>,
    pub has_default: bool,
    pub explicit_constraint: Option<BorrowMode>,
    pub inferred_borrow: BorrowMode,
    pub span: SourceSpan,
}

/// Metadata for a registered method or constructor in the global symbol table.
#[derive(Clone, Debug)]
pub struct MethodSymbol {
    pub id: SymbolId,
    pub owner_type: SymbolId,
    pub name: String,
    pub is_constructor: bool,
    pub access: AccessMod,
    pub is_static: bool,
    pub is_async: bool,
    pub is_extern: bool,
    pub is_virtual: bool,
    pub is_override: bool,
    pub is_abstract: bool,
    pub type_params: Vec<String>,
    pub params: Vec<ParamSymbol>,
    pub return_type: TypeRef,
    pub resolved_return_type_id: Option<SymbolId>,
    pub explicit_throws: Option<TypeRef>,
    pub resolved_throws_type_id: Option<SymbolId>,
    pub inferred_self_borrow: BorrowMode,
    pub inferred_effect: EffectSignature,
    pub disambiguated_rust_name: String,
    pub primitive_lowering: PrimitiveLowering,
    pub linq_stage: Option<String>,
    pub span: SourceSpan,
}

/// Metadata for any registered `.rsharp` or `.d.rsharp` type archetype.
#[derive(Clone, Debug)]
pub struct TypeSymbol {
    pub id: SymbolId,
    pub name: String,
    pub namespace: Vec<String>,
    pub fqn: String,
    pub kind: TypeKind,
    pub access: AccessMod,
    pub is_abstract: bool,
    pub is_sealed: bool,
    pub is_partial: bool,
    pub is_static: bool,
    pub is_ambient_stub: bool,
    pub type_params: Vec<String>,
    pub base_types: Vec<TypeRef>,
    pub resolved_base_type_ids: Vec<SymbolId>,
    pub fields: Vec<SymbolId>,
    pub properties: Vec<SymbolId>,
    pub methods: Vec<SymbolId>,
    pub constructors: Vec<SymbolId>,
    pub inferred_polymorphism: PolymorphismStrategy,
    pub primitive_rust_target: Option<String>,
    pub primitive_param_type: Option<String>,
    pub has_disposable_drop: bool,
    pub source_files: Vec<String>,
    pub span: SourceSpan,
}

impl TypeSymbol {
    /// Returns true if the type is a value/Copy primitive or `record struct` / `struct`.
    pub fn is_value_or_copy_archetype(&self) -> bool {
        matches!(
            self.kind,
            TypeKind::ValueStruct
                | TypeKind::Record { is_struct: true }
                | TypeKind::Enum
                | TypeKind::PrimitiveClass { is_struct: true }
        )
    }
}

/// Synthesized Rust module layout entry for a logical RustSharp namespace.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NamespaceModulePlan {
    /// Logical RustSharp namespace segments (e.g., `["Commerce", "Checkout"]`).
    pub namespace: Vec<String>,
    /// Lowercase snake_case Rust module path segments (e.g., `["commerce", "checkout"]`).
    pub rust_mod_segments: Vec<String>,
    /// Target relative `.rs` file inside the synthesized Cargo crate (e.g., `"src/commerce/checkout.rs"`).
    pub target_rs_file: String,
    /// Non-ambient `TypeSymbol` IDs aggregated into this module across all `.rsharp` files.
    pub type_ids: Vec<SymbolId>,
}

/// Whole-project symbol table populated during Pass 1 (`collector.rs`).
/// Decouples physical directory structure from logical `namespace` declarations and
/// resolves circular cross-file type references.
#[derive(Clone, Debug, Default)]
pub struct GlobalSymbolTable {
    next_id: u32,
    pub types: HashMap<SymbolId, TypeSymbol>,
    pub fields: HashMap<SymbolId, FieldSymbol>,
    pub properties: HashMap<SymbolId, PropertySymbol>,
    pub methods: HashMap<SymbolId, MethodSymbol>,
    /// Virtual namespace (`["Commerce", "Checkout"]`) -> ordered list of `TypeSymbol` IDs.
    pub namespaces: BTreeMap<Vec<String>, Vec<SymbolId>>,
    /// Hierarchical virtual namespace tree root (`NamespaceNode`).
    pub namespace_root: NamespaceNode,
    /// Fully-qualified name (`"Commerce.Checkout.OrderHandler"`) -> `SymbolId`.
    pub fqn_to_symbol: HashMap<String, SymbolId>,
    /// Unqualified short name (`"OrderHandler"`) -> list of candidate `SymbolId`s across namespaces.
    pub short_name_index: HashMap<String, Vec<SymbolId>>,
    /// Maps external Rust crate aliases (`extern using rust_decimal::Decimal as Decimal;`) to their crate path.
    pub extern_crate_aliases: HashMap<String, Vec<String>>,
    /// Co-located `.rs` files discovered in the workspace.
    pub colocated_rs_files: Vec<PathBuf>,
}

impl GlobalSymbolTable {
    pub fn new() -> Self {
        Self {
            next_id: 1,
            ..Self::default()
        }
    }

    pub fn alloc_symbol_id(&mut self) -> SymbolId {
        let id = SymbolId(self.next_id);
        self.next_id += 1;
        id
    }

    /// Registers a `TypeSymbol` or merges into an existing `partial` type in the same namespace.
    pub fn register_or_merge_type(&mut self, sym: TypeSymbol) -> SymbolId {
        if let Some(&existing_id) = self.fqn_to_symbol.get(&sym.fqn) {
            if let Some(existing) = self.types.get_mut(&existing_id) {
                for f in sym.source_files {
                    if !existing.source_files.contains(&f) {
                        existing.source_files.push(f);
                    }
                }
                for bt in sym.base_types {
                    if !existing.base_types.contains(&bt) {
                        existing.base_types.push(bt);
                    }
                }
                if existing.primitive_rust_target.is_none() {
                    existing.primitive_rust_target = sym.primitive_rust_target;
                }
                if existing.primitive_param_type.is_none() {
                    existing.primitive_param_type = sym.primitive_param_type;
                }
                return existing_id;
            }
        }

        let id = sym.id;
        let fqn = sym.fqn.clone();
        let short_name = sym.name.clone();
        let ns = sym.namespace.clone();

        self.types.insert(id, sym);
        self.fqn_to_symbol.insert(fqn, id);
        self.short_name_index
            .entry(short_name)
            .or_default()
            .push(id);

        let ns_list = self.namespaces.entry(ns.clone()).or_default();
        if !ns_list.contains(&id) {
            ns_list.push(id);
        }
        self.namespace_root.insert_type(&ns, id);

        id
    }

    /// Resolves a type name within the context of `current_ns` and file `imports`.
    pub fn resolve_type(
        &self,
        name: &str,
        current_ns: &[String],
        imports: &[ImportDecl],
    ) -> Option<SymbolId> {
        let mapped_name = match name {
            "string" => "String",
            other => other,
        };

        // 1. Direct FQN match
        if let Some(&id) = self.fqn_to_symbol.get(mapped_name) {
            return Some(id);
        }

        // 2. Current namespace and enclosing parent namespaces
        for prefix_len in (1..=current_ns.len()).rev() {
            let prefix = current_ns[..prefix_len].join(".");
            let candidate_fqn = format!("{}.{}", prefix, mapped_name);
            if let Some(&id) = self.fqn_to_symbol.get(&candidate_fqn) {
                return Some(id);
            }
        }

        // 3. Explicit `using <Namespace>;` imports in the compilation unit
        for imp in imports {
            if !imp.is_extern_crate {
                let imp_ns = imp.path.join(".");
                let candidate_fqn = format!("{}.{}", imp_ns, mapped_name);
                if let Some(&id) = self.fqn_to_symbol.get(&candidate_fqn) {
                    return Some(id);
                }
            }
        }

        // 4. Ambient `RustSharp.Core` standard library lookup
        let std_fqn = format!("RustSharp.Core.{}", mapped_name);
        if let Some(&id) = self.fqn_to_symbol.get(&std_fqn) {
            return Some(id);
        }

        // 5. Unambiguous short-name fallback
        if let Some(candidates) = self.short_name_index.get(mapped_name) {
            if candidates.len() == 1 {
                return Some(candidates[0]);
            }
        }

        None
    }

    /// Resolves a `TypeRef` AST node against the symbol table.
    pub fn resolve_type_ref(
        &self,
        type_ref: &TypeRef,
        current_ns: &[String],
        imports: &[ImportDecl],
    ) -> Option<SymbolId> {
        if type_ref.path.len() > 1 {
            let fqn = type_ref.qualified_name();
            if let Some(id) = self.resolve_type(&fqn, current_ns, imports) {
                return Some(id);
            }
        }
        self.resolve_type(type_ref.short_name(), current_ns, imports)
    }

    /// Checks whether an identifier matches an `extern using` Rust crate import or alias.
    pub fn is_extern_crate_type(&self, type_ref: &TypeRef, imports: &[ImportDecl]) -> bool {
        let first_seg = type_ref.path.first().map(|s| s.as_str()).unwrap_or("");
        let short = type_ref.short_name();

        if self.extern_crate_aliases.contains_key(first_seg)
            || self.extern_crate_aliases.contains_key(short)
        {
            return true;
        }

        for imp in imports {
            if imp.is_extern_crate {
                if let Some(alias) = &imp.alias {
                    if alias == first_seg || alias == short {
                        return true;
                    }
                }
                if let Some(last) = imp.path.last() {
                    if last == first_seg || last == short {
                        return true;
                    }
                }
                if let Some(root) = imp.path.first() {
                    if root == first_seg {
                        return true;
                    }
                }
            }
        }
        false
    }

    /// Returns true if the given `TypeRef` represents a built-in C# value primitive (`int`, `decimal`, `bool`, etc.).
    pub fn is_builtin_primitive(type_ref: &TypeRef) -> bool {
        if type_ref.is_primitive_keyword {
            return true;
        }
        matches!(
            type_ref.short_name(),
            "void"
                | "bool"
                | "byte"
                | "sbyte"
                | "short"
                | "ushort"
                | "int"
                | "uint"
                | "long"
                | "ulong"
                | "float"
                | "double"
                | "decimal"
                | "char"
                | "string"
                | "Func"
                | "Action"
                | "Attribute"
        )
    }

    /// Computes the snake_case Rust module path segments for a logical namespace.
    pub fn rust_module_segments(namespace: &[String]) -> Vec<String> {
        if namespace.is_empty() {
            return vec!["root".to_string()];
        }
        namespace
            .iter()
            .map(|seg| pascal_to_snake_case(seg))
            .collect()
    }

    /// Computes the synthesized relative `.rs` file path for a logical namespace.
    pub fn synthesized_rust_module_path(namespace: &[String]) -> String {
        let segs = Self::rust_module_segments(namespace);
        format!("src/{}.rs", segs.join("/"))
    }

    /// Builds the deterministic list of synthesized Rust modules for all non-ambient namespaces.
    pub fn build_namespace_module_plans(&self) -> Vec<NamespaceModulePlan> {
        let mut plans = Vec::new();

        for (ns, type_ids) in &self.namespaces {
            let emitted_types: Vec<SymbolId> = type_ids
                .iter()
                .copied()
                .filter(|id| {
                    self.types
                        .get(id)
                        .map(|t| {
                            !t.is_ambient_stub
                                && !matches!(t.kind, TypeKind::PrimitiveClass { .. })
                        })
                        .unwrap_or(false)
                })
                .collect();

            if emitted_types.is_empty() {
                continue;
            }

            plans.push(NamespaceModulePlan {
                namespace: ns.clone(),
                rust_mod_segments: Self::rust_module_segments(ns),
                target_rs_file: Self::synthesized_rust_module_path(ns),
                type_ids: emitted_types,
            });
        }

        plans
    }
}

/// Converts a `PascalCase` or `camelCase` identifier into idiomatic Rust `snake_case`.
pub fn pascal_to_snake_case(ident: &str) -> String {
    let mut out = String::with_capacity(ident.len() + 4);
    let chars: Vec<char> = ident.chars().collect();

    for (i, &ch) in chars.iter().enumerate() {
        if ch.is_uppercase() {
            if i > 0 {
                let prev = chars[i - 1];
                let next_is_lower = chars.get(i + 1).map(|c| c.is_lowercase()).unwrap_or(false);
                if prev.is_lowercase()
                    || prev.is_ascii_digit()
                    || (prev.is_uppercase() && next_is_lower)
                {
                    out.push('_');
                }
            }
            for lower in ch.to_lowercase() {
                out.push(lower);
            }
        } else {
            out.push(ch);
        }
    }
    out
}

```

---

### `src/semantics/mod.rs`

```rust
pub mod archetype_analyzer;
pub mod borrow_inferencer;
pub mod collector;
pub mod effect_inferencer;
pub mod hierarchy_lowerer;
pub mod linq_fuser;
pub mod overload_resolver;
pub mod preflight_verifier;
pub mod primitive_resolver;
pub mod symbols;

pub use archetype_analyzer::analyze_archetypes;
pub use borrow_inferencer::InterproceduralBorrowInferencer;
pub use collector::collect_global_symbols;
pub use effect_inferencer::infer_checked_effects;
pub use hierarchy_lowerer::resolve_polymorphism_strategies;
pub use linq_fuser::fuse_linq_pipelines;
pub use overload_resolver::resolve_overloads;
pub use preflight_verifier::run_preflight_ownership_checks;
pub use primitive_resolver::{
    format_rust_owned_type, format_rust_param_type, resolve_primitives,
};
pub use symbols::{
    FieldSymbol, GlobalSymbolTable, MethodSymbol, NamespaceModulePlan, NamespaceNode, ParamSymbol,
    PropertySymbol, TypeSymbol,
};

```

---

### `tests/m1_parser_tests.rs`

```rust
use rsharpc::diagnostics::DiagnosticEngine;
use rsharpc::frontend::{
    AccessMod, BorrowMode, EffectSignature, ExprKind, Lexer, MemberDecl, Parser,
    PrimitiveLowering, Stmt, TypeKind,
};

fn parse_source(
    filename: &str,
    src: &str,
) -> (rsharpc::frontend::CompilationUnit, DiagnosticEngine) {
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
    assert!(
        !diag.has_errors(),
        "Unexpected syntax errors: {}",
        diag.format_all()
    );
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
    assert!(
        !diag.has_errors(),
        "Unexpected syntax errors: {}",
        diag.format_all()
    );
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
    assert!(
        !diag.has_errors(),
        "Unexpected syntax errors: {}",
        diag.format_all()
    );

    let method = match &unit.types[0].members[0] {
        MemberDecl::Method(m) => m,
        _ => panic!("Expected method"),
    };
    let body = method.body.as_ref().unwrap();
    assert_eq!(body.stmts.len(), 3);

    match &body.stmts[0] {
        Stmt::LocalVar { name, init, .. } => {
            assert_eq!(name, "header");
            assert!(matches!(init.kind, ExprKind::RangeSlice { .. }));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    match &body.stmts[1] {
        Stmt::LocalVar { name, init, .. } => {
            assert_eq!(name, "effective");
            assert!(matches!(init.kind, ExprKind::NullCoalesce { .. }));
        }
        other => panic!("Expected LocalVar, got {:?}", other),
    }

    match &body.stmts[2] {
        Stmt::Return {
            value: Some(expr), ..
        } => {
            assert!(matches!(expr.kind, ExprKind::Switch { .. }));
        }
        other => panic!("Expected Return with Switch expr, got {:?}", other),
    }
}

```

---

### `tests/fixtures/commerce_workspace/Domain/Models.rsharp`

```csharp
namespace Commerce.Domain;

using Commerce.Checkout;

public record CustomerProfile(int CustomerId, string Email, List<Order> Orders);

```

---

With these files added, every single file in the `rustsharp-compiler/` (`rsharpc`) **Milestone 1–6 Implementation Plan and Repository Map (`repomap`)** is now present in this chat. Would you like me to run the complete `rsharpc` pipeline or move on to **Phase 3 (`rsharp-bindgen` Cargo Stub Generator)** next?
