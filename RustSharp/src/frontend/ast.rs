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
    pub attributes: Vec<AttributeNode>,
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
    BitAnd,
    BitOr,
    BitXor,
    Shl,
    Shr,
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
    BitNot,  // ~
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
    Where {
        predicate: Expr,
    },
    Select {
        selector: Expr,
    },
    SelectMany {
        selector: Expr,
    },
    Take {
        count: Expr,
    },
    Skip {
        count: Expr,
    },
    WithIndex,
    OrderBy {
        key_selector: Expr,
        descending: bool,
    },
    Distinct,
    Reverse,
}

#[derive(Clone, Debug, PartialEq)]
pub enum LinqTerminal {
    ToList,
    ToHashSet,
    Any { predicate: Option<Expr> },
    All { predicate: Expr },
    First { predicate: Option<Expr> },
    FirstOrDefault { predicate: Option<Expr> },
    Last { predicate: Option<Expr> },
    LastOrDefault { predicate: Option<Expr> },
    Count,
    Sum,
    Aggregate { seed: Option<Expr>, func: Box<Expr> },
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
    LinqChain(Box<LinqChain>),
}
