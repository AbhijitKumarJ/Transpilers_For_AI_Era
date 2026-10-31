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
    Tilde,          // ~
    Amp,            // &
    Pipe,           // |
    Shl,            // <<
    Shr,            // >>
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
