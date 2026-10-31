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
    kind: str = "NoneRequired"  # NoneRequired | PyIsInstance | PyIsInstanceStrictInt | PsTypesContains
    target_type: str = ""


@dataclass(slots=True)
class OverloadGuard:
    min_arity: int = 0
    max_arity: int = 0
    param_type_checks: list[tuple[int, RuntimeTypeCheck]] = field(default_factory=list)


@dataclass(slots=True)
class MemberLoweringMode:
    """Populated in Pass 2 for every method/property/indexer declaration and call site."""

    kind: str = (
        "Unresolved"  # Unresolved | StandardPython | OverloadedVariant | PrimitiveDirect | PrimitiveInlineTemplate
    )
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
            inner = ", ".join(f"{t.display_name()} {n}" if n else t.display_name() for t, n in self.tuple_elements)
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
    namespace_span: SourceSpan | None = None


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
class BreakStmt:
    span: SourceSpan


@dataclass(slots=True)
class ContinueStmt:
    span: SourceSpan


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
    | BreakStmt
    | ContinueStmt
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
    BITWISE_NOT = "~"


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
    IN = "in"
    AND = "&&"
    OR = "||"
    BITWISE_AND = "&"
    BITWISE_OR = "|"
    BITWISE_XOR = "^"
    LSHIFT = "<<"
    RSHIFT = ">>"
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
    CONDITIONAL = auto()
    LINQ_COMPREHENSION = auto()  # Fused by Pass 2
    RAW_PYTHON_AST = auto()


@dataclass(slots=True)
class Expr:
    span: SourceSpan
    kind: ExprKind
    data: dict[str, Any] = field(default_factory=dict)
    # Pass 2 Semantic Slots
    resolved_type: str | None = None
    resolved_lowering: MemberLoweringMode | None = None
