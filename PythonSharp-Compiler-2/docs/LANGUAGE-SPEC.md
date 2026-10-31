# PythonSharp Language Specification

**Status:** Phase 1 subset
**Last updated:** 2026-10-28
**Related docs:** [ARCHITECTURE.md](ARCHITECTURE.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [PRD.md](PRD.md)

## 1. Design rules

1. **Compile-time C# discipline, runtime Python isomorphism.** Every construct
   either erases at compile time or lowers to readable Python.
2. **No runtime wrapper tax.** Primitive facades and visibility metadata disappear
   from emitted code.
3. **Static names are resolved globally.** Physical file layout does not define
   module structure; namespaces do.
4. **Unsupported C# constructs are rejected explicitly.** There is no silent
   approximation of semantics the backend cannot preserve.
5. **Python remains the boundary.** `extern using` exposes native modules directly;
   Python exceptions, descriptors, and duck typing apply at that boundary.

## 2. Source files and compilation units

| Extension | Purpose |
| --- | --- |
| `.ps`, `.pysharp`, `.pys` | PythonSharp source files |
| `.d.ps`, `.d.pysharp`, `.d.pys` | Declaration-only ambient or binding stubs |
| `.psproj`, `.pysharpproj` | Project/assembly file in XML or TOML |

- Encoding is UTF-8.
- Statements and declarations are semicolon-terminated unless they are block
  declarations.
- A compilation unit contains one optional namespace declaration, imports, and
  any number of type declarations.
- Files may contribute types to a shared logical namespace regardless of their
  physical directory.
- The project file determines the assembly boundary used by `internal` access.

## 3. Lexical structure

### 3.1 Comments and whitespace

```csharp
// line comment
/* block comment */
```

Whitespace is insignificant except as a token separator and for line tracking.

### 3.2 Identifiers and keywords

Identifiers are Unicode letters, digits, and underscores, and may be prefixed with
`@` to use a reserved word as an identifier. Names are case-sensitive.

| Category | Keywords |
| --- | --- |
| Declarations | `namespace`, `using`, `extern`, `class`, `interface`, `enum`, `record`, `struct`, `primitive` |
| Modifiers | `public`, `private`, `protected`, `internal`, `static`, `readonly`, `abstract`, `sealed`, `partial`, `virtual`, `override`, `async` |
| Statements | `if`, `else`, `while`, `foreach`, `in`, `switch`, `case`, `default`, `break`, `continue`, `return`, `yield`, `throw`, `try`, `catch`, `finally`, `when`, `using` |
| Expressions | `new`, `this`, `base`, `var`, `is`, `as`, `null`, `true`, `false`, `await`, `default`, `params` |
| Types | `void`, `bool`, `int`, `long`, `float`, `double`, `decimal`, `string`, `object`, `dynamic` |

### 3.3 Literals

| Literal | Example | Notes |
| --- | --- | --- |
| Integer | `42`, `0xFF`, `1_000` | Maps to Python `int` |
| Long | `42L` | Parsed distinctly, erased to `int` |
| Float | `3.14`, `1e9` | Maps to Python `float` |
| Decimal | `19.99m` | Maps to `decimal.Decimal` |
| Boolean | `true`, `false` | Maps to `True`, `False` |
| String | `"text"` | Escape sequences supported |
| Interpolated string | `$"Hello {name}"` | Lowers to an f-string |
| Null | `null` | Maps to `None` |
| List initializer | `[1, 2, 3]` | Maps to a Python list |

Only double-quoted strings, with escape sequences, and `$"..."` interpolated
strings are part of the Phase 1 lexer. Raw and triple-quoted strings are not
Phase 1 syntax.

### 3.4 Operators

| Precedence (high to low) | Operators |
| --- | --- |
| Postfix | `.`, `?.`, `()`, `[]` |
| Unary | `!`, `-`, `await`, `^` |
| Multiplicative | `*`, `/`, `%`, `**` |
| Additive | `+`, `-` |
| Relational | `<`, `>`, `<=`, `>=`, `is`, `as` |
| Equality | `==`, `!=` |
| Logical AND | `&&` |
| Logical OR | `\|\|` |
| Null-coalescing | `??` |
| Conditional (ternary) | `? :` |
| Assignment | `=`, `+=`, `-=`, `*=`, `/=`, `??=` |

`&&` and `||` lower to Python `and` and `or` with their short-circuit behavior.
Boolean expressions are not implicitly converted to non-boolean values in
PythonSharp source; the compiler enforces boolean conditions.
Binary `/` between integer types (`int`, `long`, `short`, etc.) lowers to Python's
integer floor division `//` (`ast.FloorDiv`), matching C# semantics; if either operand
is `float` or `double`, standard floating-point division `/` (`ast.Div`) is emitted.
Conditional expressions (`cond ? a : b`) lower to Python's conditional expression `a if cond else b`.

## 4. Grammar (Phase 1 core)

This is a condensed form of the EBNF used by the parser. It is normative for the
supported subset; newer constructs are added only with a documented lowering.

```ebnf
CompilationUnit   ::= NamespaceDecl? ImportDecl* TypeDecl* EOF ;
NamespaceDecl     ::= "namespace" QualifiedIdent ";" ;
ImportDecl        ::= StandardUsing | ExternUsing ;
StandardUsing     ::= "using" QualifiedIdent ";" ;
ExternUsing       ::= "extern" "using" PyModulePath ( "as" Ident )? ";" ;

TypeDecl          ::= AttributeSection* AccessMod? TypeModifier*
                      ( ClassDecl | RecordDecl | StructDecl
                      | InterfaceDecl | EnumDecl ) ;
AccessMod         ::= "public" | "internal" | "protected" | "private" ;
TypeModifier      ::= "abstract" | "sealed" | "partial" | "static" | "primitive" ;

ClassDecl         ::= "class" Ident TypeParams? BaseList?
                      "{" MemberDecl* "}" ;
RecordDecl        ::= "record" "struct"? Ident TypeParams?
                      PrimaryCtorParams? BaseList?
                      ( ";" | "{" MemberDecl* "}" ) ;
StructDecl        ::= "struct" Ident TypeParams? BaseList?
                      "{" MemberDecl* "}" ;
InterfaceDecl     ::= "interface" Ident TypeParams? BaseList?
                      "{" InterfaceMember* "}" ;
EnumDecl          ::= "enum" Ident
                      "{" EnumMember ( "," EnumMember )* ","? "}" ;

MemberDecl        ::= AttributeSection* AccessMod? MemberModifier*
                      ( FieldDecl | PropertyDecl | ConstructorDecl
                      | MethodDecl | IndexerDecl ) ;
MemberModifier    ::= "readonly" | "static" | "virtual" | "override"
                    | "abstract" | "extern" | "async" ;

FieldDecl         ::= TypeRef Ident ( "=" Expr )? ";" ;
PropertyDecl      ::= TypeRef Ident
                      ( "{" AccessorDecl+ "}" ( "=" Expr ";" )?
                      | "=>" Expr ";" ) ;
AccessorDecl      ::= AccessMod? ( "get" | "set" )
                      ( ";" | Block | "=>" Expr ";" ) ;
ConstructorDecl   ::= Ident "(" ParamList? ")" CtorChain?
                      ( Block | "=>" Expr ";" ) ;
MethodDecl        ::= TypeRef Ident TypeParams? "(" ParamList? ")"
                      TypeConstraint*
                      ( Block | "=>" Expr ";" | ";" ) ;
ParamList         ::= Param ( "," Param )* ;
Param             ::= AttributeSection* ParamMod? TypeRef Ident ( "=" Expr )? ;
ParamMod          ::= "params" ;

TypeRef           ::= NonNullType "?"? ;
NonNullType       ::= PrimitiveType | TupleType
                    | QualifiedIdent TypeArgs? ;
PrimitiveType     ::= "void" | "bool" | "int" | "long" | "float"
                    | "double" | "decimal" | "string" | "object" | "dynamic" ;
TupleType         ::= "(" TypeRef Ident? ( "," TypeRef Ident? )+ ")" ;
TypeArgs          ::= "<" TypeRef ( "," TypeRef )* ">" ;

Stmt              ::= Block | LocalVarStmt | UsingResourceStmt
                    | IfStmt | WhileStmt | ForEachStmt | ReturnStmt
                    | YieldStmt | ThrowStmt | TryCatchFinallyStmt
                    | SwitchStmt | ExprStmt ;
LocalVarStmt      ::= ( "var" | TypeRef ) Ident "=" Expr ";" ;
UsingResourceStmt ::= "await"? "using" ( "var" | TypeRef ) Ident "=" Expr ";" ;
IfStmt            ::= "if" "(" Expr ")" Stmt ( "else" Stmt )? ;
WhileStmt         ::= "while" "(" Expr ")" Stmt ;
ForEachStmt       ::= "await"? "foreach" "(" ( "var" | TypeRef ) Ident
                      "in" Expr ")" Stmt ;
TryCatchFinallyStmt ::= "try" Block CatchClause* FinallyClause? ;
CatchClause       ::= "catch" ( "(" TypeRef Ident? ")" )?
                      ( "when" "(" Expr ")" )? Block ;
SwitchStmt        ::= "switch" "(" Expr ")" "{" SwitchSection* "}" ;

Expr              ::= AssignmentExpr | LambdaExpr | SwitchExpr ;
AssignmentExpr    ::= NullCoalesceExpr ( AssignOp Expr )? ;
NullCoalesceExpr  ::= LogicalOrExpr ( "??" NullCoalesceExpr )? ;
LogicalOrExpr     ::= LogicalAndExpr ( "||" LogicalAndExpr )* ;
LogicalAndExpr    ::= EqualityExpr ( "&&" EqualityExpr )* ;
EqualityExpr      ::= RelationalExpr ( ( "==" | "!=" ) RelationalExpr )* ;
RelationalExpr    ::= AdditiveExpr ( ( "<" | ">" | "<=" | ">=" ) AdditiveExpr
                                  | "is" Pattern | "as" TypeRef )? ;
AdditiveExpr      ::= MultiplicativeExpr ( ( "+" | "-" ) MultiplicativeExpr )* ;
MultiplicativeExpr::= UnaryExpr ( ( "*" | "/" | "%" | "**" ) UnaryExpr )* ;
UnaryExpr         ::= ( "!" | "-" | "await" | "^" ) UnaryExpr | PostfixExpr ;
PostfixExpr       ::= PrimaryExpr PostfixOp* ;
PostfixOp         ::= "." Ident TypeArgs? ( "(" ArgList? ")" )?
                    | "?." Ident ( "(" ArgList? ")" )?
                    | "[" IndexOrSliceList "]" ;
PrimaryExpr       ::= Literal | InterpolatedString | Ident | "this" | "base"
                    | "new" TypeRef "(" ArgList? ")" ObjectInitializer?
                    | "[" ( Expr ( "," Expr )* )? "]"
                    | "(" Expr ( "," Expr )* ")" ;
ArgList           ::= Arg ( "," Arg )* ;
Arg               ::= ( Ident ":" )? Expr ;
LambdaExpr        ::= "async"? ( Ident | "(" ( Param ( "," Param )* )? ")" )
                      "=>" ( Expr | Block ) ;
```

## 5. Namespaces and imports

### 5.1 Namespace declaration

```csharp
namespace Commerce.Domain.Models;
```

- One namespace per compilation unit.
- Types declared in the same namespace across files are aggregated.
- The namespace maps to a Python module path by converting each PascalCase segment
  to snake_case:

| PythonSharp namespace | Emitted module |
| --- | --- |
| `Commerce.Domain.Models` | `commerce/domain/models.py` |
| `Commerce.Services` | `commerce/services.py` |
| `ML.Pipelines` | `ml/pipelines.py` |

Intermediate directories receive generated `__init__.py` package markers.

### 5.2 Imports

```csharp
using Commerce.Domain.Services;
extern using datetime as dt;
extern using torch;
```

| Form | Meaning | Emitted behavior |
| --- | --- | --- |
| `using X;` | Compile-time visibility of PythonSharp namespace `X` | Cross-module `from ... import ...` as needed |
| `extern using m;` | Native Python module `m` | `import m` |
| `extern using m as A;` | Native module under alias `A` | `import m as A` |

- `using` is compile-time only; it does not imply a runtime import unless a type
  or member from that namespace is referenced.
- Circular type references across namespaces are resolved at compile time. Runtime
  import cycles are ordered topologically; a genuine initialization cycle is
  reported instead of producing a partially initialized module.
- `extern using` targets are never imported during compilation.

## 6. Type declarations

### 6.1 Classes

```csharp
public class Account : BaseEntity, IAuditable
{
    private readonly string _id;
    internal decimal Balance { get; private set; } = 0.0m;

    public Account(string id, decimal initialBalance) : base(id)
    {
        _id = id;
        Balance = initialBalance;
    }

    public bool IsOverdrawn => Balance < 0m;
}
```

Emission outline:

```python
class Account(BaseEntity):
    __ps_types__ = (
        "Commerce.Domain.Account",
        "Commerce.Domain.BaseEntity",
        "Commerce.Domain.IAuditable",
    )
    __slots__ = ("_id", "_balance")

    def __init__(self, id: str, initial_balance: Decimal) -> None:
        super().__init__(id)
        self._id: str = id
        self._balance: Decimal = initial_balance

    @property
    def balance(self) -> Decimal:
        return self._balance

    @property
    def is_overdrawn(self) -> bool:
        return self._balance < Decimal("0")
```

Rules:

- Only concrete base classes enter the Python MRO; interfaces are recorded in
  `__ps_types__`.
- `__slots__` contains only slots introduced by the class, not inherited slots.
- Private fields use a single underscore prefix, not Python name mangling.
- Auto-properties become `@property` accessors over `_snake_case` backing slots.
- Expression-bodied computed properties become read-only `@property` methods.
- Static auto-properties emit as class attributes; inside records/structs they use
  `ClassVar` so they do not become dataclass constructor fields.
- Static getter-only computed properties emit as `@classmethod` methods. Reads
  such as `Config.Default` lower to `Config.default()` so the value stays lazy and
  works on CPython 3.11-3.13.
- Static fields, properties, and method calls used unqualified inside a type body
  are emitted with the declaring type qualifier.
- Static properties with custom setters are rejected. Static auto-properties with
  get/set accessors remain assignable as class attributes; access checks still
  enforce `private`/`protected` setters at compile time.

### 6.2 Records and structs

| Construct | Emitted Python | Semantics |
| --- | --- | --- |
| `record UserDto(int Id, string Name);` | `@dataclass(slots=True, frozen=True)` | Immutable data carrier |
| `record struct Point(double X, double Y);` | `@dataclass(slots=True)` | Mutable data carrier |
| `struct Point { ... }` | `@dataclass(slots=True)` | Mutable data carrier |

Struct copy-on-assignment and value-type identity are **not** reproduced. A struct
is a slotted dataclass with Python reference semantics. Do not rely on value
copying; use `record` for immutable carriers.

The stable subset supports primary-constructor parameters, static fields and
properties, methods, and getter-only computed properties over primary-constructor
state. Explicit instance fields and instance auto-properties are rejected with a
diagnostic because they would require dataclass fields outside the primary
constructor. Instance properties with setters are rejected on `record` because
records emit as frozen dataclasses; `record struct` and `struct` remain mutable.

### 6.3 Interfaces

```csharp
public interface IAuditable
{
    string AuditTag { get; }
}
```

- Emitted as a `typing.Protocol` declaration with method/property stubs.
- Interfaces do not enter the runtime MRO.
- Conformance is recorded in `__ps_types__`.
- Runtime type tests against an interface use nominal membership:

```python
"Commerce.Domain.IAuditable" in getattr(obj, "__ps_types__", ())
```

- Interface checks are nominal, not structural, even though the emitted Python
  shape is a Protocol.

### 6.4 Enums

```csharp
public enum Status { Pending = 1, Active = 2 }
```

- Emitted as `enum.IntEnum` for integer-valued enums.
- Explicit integer values are preserved; unspecified values follow C# auto-increment
  from the previous member, starting at 0 for the first member.
- Enum member names preserve their declared casing.
- Non-integer enum payloads are a later-phase feature.

### 6.5 Primitive classes

```csharp
[MapsTo("dict")]
public primitive class Dict<TKey, TValue>
{
    [MapsTo("get")]
    public extern TValue? GetOrDefault(TKey key, TValue? defaultValue = default);

    [InlineTemplate("{0} in {self}")]
    public extern bool ContainsKey(TKey key);
}
```

- `primitive` types exist only at compile time.
- They must declare an erasure target with `[MapsTo]` or `[InlineTemplate]`.
- No primitive wrapper object is emitted.
- Member calls lower directly to the mapped Python operation.

## 7. Type system

### 7.1 Type mapping

| PythonSharp type | Annotation | Runtime check | Notes |
| --- | --- | --- | --- |
| `bool` | `bool` | `bool` | Checked before `int` |
| `int` | `int` | `int` and not `bool` | `long` also erases to `int` |
| `long` | `int` | `int` and not `bool` | Range not enforced |
| `float` | `float` | `(float, int)` | `double` also erases to `float` |
| `double` | `float` | `(float, int)` | Same as `float` |
| `decimal` | `Decimal` | `Decimal` | `decimal.Decimal` |
| `string` | `str` | `str` | `PythonSharp.Core.String` |
| `object` | `object` | `object` | Any Python object |
| `dynamic` | `Any` | none | Unchecked; forbidden in `[NativeCompile]` |
| `void` | `None` | none | Return type only |
| `T?` | `T \| None` | `None` or `T` check | Nullable |
| `List<T>` | `list[T]` | `list` | Generic args erased at runtime |
| `Dict<K,V>` | `dict[K,V]` | `dict` | Generic args erased at runtime |
| `HashSet<T>` | `set[T]` | `set` | Generic args erased at runtime |
| Class | `ClassName` | `isinstance` | Nominal class |
| Interface | `IAuditable` | `__ps_types__` membership | Nominal interface |
| Tuple | `tuple[...]` | `tuple` | Positional and named elements |

### 7.2 Nullability

- Reference types are nullable only when annotated with `?`.
- `T?` accepts `T` or `None`.
- Null-safety operators are checked by the compiler; assigning a nullable value to
  a non-nullable target is an error unless narrowed.
- `!` is the null-forgiving operator and erases at runtime.
- `default` lowers to the type's default value or `None`.

### 7.3 Generics

- Generic type parameters are parsed and resolved at compile time, then erased.
- `List<int>` and `List<string>` share the runtime type `list`.
- Overloads that collide after erasure are rejected with `PS002`.
- Generic constraints are validated statically; no runtime generic metadata is
  emitted.

### 7.4 Type inference

- `var` infers the declared type from the initializer.
- `var` requires an initializer with a statically known type.
- Inferred types participate in overload resolution and null checking normally.

## 8. Access modifiers and member modifiers

| Modifier | Compile-time meaning |
| --- | --- |
| `public` | Accessible anywhere |
| `private` | Accessible only in the declaring type |
| `protected` | Accessible in the declaring type and derived types |
| `internal` | Accessible within the same `.psproj` assembly |
| `readonly` | Field assignable only in a constructor or field initializer |
| `static` | Belongs to the type, not an instance |
| `virtual` / `override` | Reserved for later polymorphic dispatch work |
| `abstract` | Declaration without implementation |
| `sealed` | Prevents further derivation |
| `async` | Marks an async method; Phase 4 semantics |
| `partial` | Grammar reserved; not a Phase 1 guarantee |

Access modifiers are erased at runtime. They are enforced before emission and
produce `PS001` on violation. Property accessors may have narrower visibility than
the property itself, for example `public string AuditTag { get; private set; }`.

## 9. Statements

| Statement | Lowering |
| --- | --- |
| Block | Python block |
| Local variable | Annotated assignment |
| `if` / `else` | `if` / `else` |
| `while` | `while` |
| `foreach (var x in seq)` | `for x in seq` |
| `break;` | `break` |
| `continue;` | `continue` |
| `return` | `return` |
| `yield return` / `yield break` | Generator yield; Phase 4 semantics |
| `throw new T(...)` | `raise T(...)`; bare `throw;` only inside a catch |
| `try` / `catch` / `finally` | `try` / `except` / `finally`; untyped `catch` uses `BaseException` |
| `catch (T e) when (cond)` | Ordered dispatcher; failed guards fall through to later catches |
| `switch` | `match` / `case` or `if` / `elif` |
| `using var x = expr;` | `with expr as x:` |
| `await using var x = expr;` | `async with expr as x:` |
| Expression statement | Python expression statement |

There is no C-style `for (;;)` loop in the Phase 1 grammar; use `while` or
`foreach`.

## 10. Expressions

### 10.1 Assignment and initialization

- `=` and compound assignments lower directly.
- `new T(args)` lowers to `T(args)`.
- Object initializers (`new T() { X = 1 }`) are parsed but may be lowered through
  a generated constructor or rejected in Phase 1; the behavior must be explicit
  per type.
- Named arguments use `name: value` in PythonSharp and `name=value` in Python.

### 10.2 Null-safe access

```csharp
string? name = user?.Profile?.Name;
string display = name ?? "unknown";
cache.Tag ??= "default";
```

Lowering uses single-evaluation temporaries to avoid repeated property access:

```python
name: str | None = (
    (_t1.name if (_t1 := _t0.profile) is not None else None)
    if (_t0 := user) is not None
    else None
)
display: str = name if name is not None else "unknown"
if cache.tag is None:
    cache.tag = "default"
```

`??` must test `is not None`, never truthiness, so `0`, `""`, and empty
collections remain valid values.

### 10.3 Casts and type tests

| PythonSharp | Python |
| --- | --- |
| `(T)expr` | `expr` with a compile-time check, or `cast(T, expr)` |
| `expr is T` | `isinstance(expr, T)` for classes |
| `expr is I` | `"Namespace.I" in getattr(expr, "__ps_types__", ())` |
| `expr as T` | conditional assignment or `None` |
| `expr is null` | `expr is None` |

### 10.4 String interpolation

```csharp
$"Order {order.Id} total {order.Total}"
```

lowers to an f-string. Interpolated expressions are evaluated once, left to
right. Unqualified instance members inside the expression are qualified with
`self`, just like other method-body expressions.

### 10.5 Slicing and indexing

PythonSharp extends C# index/range syntax with steps and multi-axis slicing:

| PythonSharp | Python |
| --- | --- |
| `items[^1]` | `items[-1]` |
| `items[1..5]` | `items[1:5]` |
| `items[1..]` | `items[1:]` |
| `items[..5]` | `items[:5]` |
| `items[1..10:2]` | `items[1:10:2]` |
| `items[::2]` | `items[::2]` |
| `tensor[1..5, ^2.., ::2]` | `tensor[1:5, -2:, ::2]` |

- Indices and bounds are expressions.
- Out-of-range indices follow Python semantics.
- Slicing syntax is only valid inside index expressions.

### 10.6 Lambdas

```csharp
users.Where(u => u.IsActive)
```

- Expression lambdas lower to Python expressions inside comprehensions or to
  `lambda` only when fusion cannot preserve semantics.
- Block lambdas lower to nested functions.
- Lambda parameter names are alpha-renamed during LINQ fusion.

## 11. LINQ lowering

LINQ method chains are recognized structurally. Fusion occurs only when it
preserves evaluation order, side effects, and short-circuit behavior.

| PythonSharp | Lowered Python |
| --- | --- |
| `.Where(u => cond).Select(u => expr).ToList()` | `[expr for u in seq if cond]` |
| `.Select(u => expr).ToHashSet()` | `{expr for u in seq}` |
| `.Where(...).ToDict(u => k, u => v)` | `{k: v for u in seq if ...}` |
| `.SelectMany(o => o.Items).Where(...).ToList()` | `[i for o in seq for i in o.items if ...]` |
| `.Any(u => cond)` | `any(cond for u in seq)` |
| `.All(u => cond)` | `all(cond for u in seq)` |
| `.FirstOrDefault(u => cond)` | `next((u for u in seq if cond), None)` |
| `.Where(...).Sum()` | `sum(x for x in seq if ...)` |
| `.OrderBy(u => key)` | `sorted(seq, key=lambda u: key)` |
| `.OrderBy(u => k1).ThenBy(u => k2)` | stable sorts applied from the last key to the first |
| `.Distinct().ToList()` | `list(dict.fromkeys(seq))` |
| `.Skip(n).Take(n).ToList()` | `list(itertools.islice(itertools.islice(seq, max(0, n), None), max(0, n)))` |
| `.Concat(other).ToList()` | `list(itertools.chain(seq, other))` |
| `.Contains(value)` | `value in seq` |
| `.LastOrDefault()` | `next(iter(reversed(list(seq))), None)` |
| `.Average()` | `statistics.fmean(seq)` |
| `.Min()` / `.Max()` | `min(seq)` / `max(seq)` |

Fusion rules:

1. A terminal materializer chooses the comprehension kind.
2. Chained `Where` predicates are conjoined into one guard.
3. Lambda parameters are alpha-renamed to the single iteration variable.
4. Chains with an unfusable stage lower to ordinary Python iterator calls such as
   `filter`, `map`, `itertools.chain`, `itertools.islice`, `dict.fromkeys`,
   `sorted`, and `statistics.fmean`; `itertools` and `statistics` are imported
   automatically when used.
5. Ordering stages compose stable sorts from the last key to the first, so
   `OrderBy`/`OrderByDescending` and `ThenBy`/`ThenByDescending` preserve earlier
   ordering when later keys tie.
6. `Take` and `Skip` clamp negative counts to zero. Ordering and materialisation
   operators are eager; sequence filters, projections, concatenation, and slicing
   remain lazy where the corresponding Python operation is lazy.
7. `SingleOrDefault` is deferred and is not part of the stable surface.

## 12. Attributes

Attributes are compile-time directives unless explicitly mapped to a Python
decorator.

| Attribute | Phase | Purpose |
| --- | --- | --- |
| `[MapsTo("target")]` | 1 | Map a type or member to a Python name |
| `[InlineTemplate("...")]` | 1 | Inline a Python expression template |
| `[RuntimeType("...")]` | 1 | Override the runtime `isinstance` type |
| `[KwArgs]` | 1/4 | Lower a dictionary parameter to `**kwargs` |
| `[LinqStage("Kind")]` | 1 | Mark a sequence method as fusable |
| `[PythonDecorator("path")]` | 4 | Apply a Python decorator |
| `[SchemaModel]` | 4 | Lower to a Pydantic model |
| `[NativeCompile]` | 5 | Compile the type with mypyc/Cython |

Attribute arguments are compile-time values. The compiler never executes
attribute code.

## 13. Resource management

`IDisposable` and `IAsyncDisposable` are compiler-recognized contracts:

```csharp
public interface IDisposable
{
    void Dispose();
}

public interface IAsyncDisposable
{
    Task DisposeAsync();
}
```

Implementing types receive:

```python
def __enter__(self):
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    self.dispose()
```

and async equivalents. `using` lowers to `with`; `await using` lowers to
`async with`. Cleanup runs on both normal and exceptional exit.

## 14. Naming and emission conventions

| Source element | Emitted name |
| --- | --- |
| Namespace segment `Commerce` | `commerce` |
| Class `OrderCache` | `OrderCache` |
| Method `GetOrCreate` | `get_or_create` |
| Property `AuditTag` | `audit_tag` |
| Private field `_id` | `_id` |
| Auto-property backing slot | `_audit_tag` |
| Constructor | `__init__` |
| Enum member `Pending` | `Pending` |
| Parameter `initialBalance` | `initial_balance` |
| Local `isActive` | `is_active` |

Every emitted module begins with `from __future__ import annotations` so annotations
never force runtime imports.

## 15. Semantic rules and diagnostics

| Rule | Meaning |
| --- | --- |
| `PS000` | Syntax or structural error |
| `PS001` | Encapsulation or readonly-access violation |
| `PS002` | Overloads erasing to the same runtime signature at the same arity |
| `PS003` | Circular static value initialization |
| `PS004` | `dynamic` used inside a `[NativeCompile]` type |

Exact messages, severities, and exit behavior are in
[DIAGNOSTICS.md](DIAGNOSTICS.md).

## 16. Compatibility and deviations from C#

| Area | PythonSharp behavior |
| --- | --- |
| Memory | Garbage-collected; no deterministic destruction |
| Value types | Records/structs are dataclasses with reference identity; no copy-on-assign |
| Overloading | Limited to runtime-distinguishable erased signatures |
| Generics | Compile-time only; erased at runtime |
| Access control | Compile-time only; no runtime enforcement |
| Multiple inheritance | Limited; interfaces do not enter the MRO |
| `dynamic` | Maps to `Any`; no static checking |
| Exceptions | Direct Python exception hierarchy; C# names map through Core `[MapsTo]` declarations (D-016) |
| Threads | Python threading/GIL semantics; no CLR threading model |
| Properties | Lowered to Python descriptors/class attributes; no C# property metadata at runtime; static computed reads become classmethod calls (D-019) |
| `switch` | Only patterns with a faithful Python lowering |
| Operator overloading | Not in Phase 2; deferred to Phase 4 (D-020) |
| Events/delegates | Not in Phase 1 |

### 16.1 Exception mapping

Exceptions use Python's hierarchy directly; there is no wrapper exception runtime.
`throw new X(...)` lowers to `raise X(...)`. A bare `throw;` lowers to bare
`raise` and is rejected outside a catch handler. Untyped `catch` lowers to
`BaseException`; typed catches use the mapped Python type.

| PythonSharp exception | Python exception |
| --- | --- |
| `Exception` | `Exception` |
| `SystemException` | `Exception` |
| `ArgumentException` | `ValueError` |
| `ArgumentNullException` | `ValueError` |
| `InvalidOperationException` | `RuntimeError` |
| `NotSupportedException` | `NotImplementedError` |
| `NotImplementedException` | `NotImplementedError` |
| `IndexOutOfRangeException` | `IndexError` |
| `KeyNotFoundException` | `KeyError` |
| `DivideByZeroException` | `ZeroDivisionError` |
| `OverflowException` | `OverflowError` |
| `IOException` | `OSError` |
| `FileNotFoundException` | `FileNotFoundError` |
| `EndOfStreamException` | `EOFError` |
| `InvalidDataException` | `ValueError` |
| `FormatException` | `ValueError` |
| `NullReferenceException` | `AttributeError` |
| `UnauthorizedAccessException` | `PermissionError` |
| `ArithmeticException` | `ArithmeticError` |
| `ObjectDisposedException` | `ValueError` |
| `InvalidCastException` | `TypeError` |
| `TimeoutException` | `TimeoutError` |

Multiple catches, or any catch with a `when` guard, lower through one ordered
`BaseException` dispatcher. If a guard fails, evaluation continues with the next
catch; if no catch matches, the original exception is re-raised. User-defined
exception classes inherit the mapped Python base, so `class MyError : Exception`
emits `class MyError(Exception)`.

### 16.2 Core API subset

The Phase 2 Core surface is intentionally small and maps directly to Python
builtins or standard-library objects. It introduces no runtime wrapper classes.

| PythonSharp type | Python target | Supported surface |
| --- | --- | --- |
| `String` | `str` | Length, IsEmpty, Contains, StartsWith, EndsWith, ToLower, ToUpper, Trim, Replace, Split, Substring, IndexOf, LastIndexOf, ToString, IsNullOrEmpty, indexer |
| `List<T>` | `list` | Constructors, Count, Add, AddRange, Remove, Pop, Clear, Insert, RemoveAt, IndexOf, Sort, Reverse, Contains, indexer |
| `Dict<K,V>` | `dict` | Constructor, Count, Add, GetOrDefault, ContainsKey, Clear, Keys, Values, Items, ContainsValue, Remove, indexer |
| `HashSet<T>` | `set` | Constructor, Count, Add, Remove, Contains, Clear, UnionWith, IntersectWith, ExceptWith, SymmetricExceptWith, IsSubsetOf, IsSupersetOf, Overlaps, SetEquals |
| `KeyValuePair<K,V>` | `tuple` | Key, Value |
| `Math` | `math` | PI, E, Sqrt, Pow, Exp, Log, Sin, Cos, Tan, Abs, Max, Min, Clamp, Ceiling, Floor, Round, Truncate, Sign |
| `IEnumerable<T>` / `IOrderedEnumerable<T>` | `collections.abc.Iterable` | Where, Select, SelectMany, OrderBy, OrderByDescending, ThenBy, ThenByDescending, Distinct, Take, Skip, Concat, Contains, ToList, ToHashSet, ToDict, Any, All, FirstOrDefault, LastOrDefault, Count, Sum, Min, Max, Average |
| `Console` | builtins | WriteLine |
| `Task` | `collections.abc.Awaitable` | Delay (lowers to `asyncio.sleep`) |

`Math` calls emit a normal `import math`; no ambient import is required in user
source. Empty `List`/`Dict`/`HashSet` locals receive Python annotations such as
`values: set[int] = set()` so Pyright strict can infer their element types. LINQ
fusion requires an explicit `[LinqStage]` on the resolved member (D-017), which
keeps ordinary methods such as `Math.Max` on the normal call path.

Non-fusable LINQ chains lower to ordinary Python iterator calls rather than a
runtime wrapper. The builder imports `itertools` and `statistics` when those
names appear. Ordering and materialisation operators are eager; `Distinct`
preserves first occurrence through `dict.fromkeys`; `Take`/`Skip` clamp negative
counts to zero; `LastOrDefault` returns `None` for an empty sequence, consistent
with the existing `FirstOrDefault` lowering.

Not yet covered by the stable subset: `SingleOrDefault`, `String.Join`/`Format`,
`Dict.TryGetValue`, `List.RemoveAll`/`Find`, and filesystem wrappers. These remain
candidates for later Core additions or Phase 3 bindings rather than hidden
runtime behavior.

Known collection differences are explicit: `List.Remove` follows Python
`list.remove` and raises `ValueError` when absent; `Dict.Remove` follows
`dict.pop` and raises `KeyError` when absent; `HashSet.Remove` follows
`set.discard` and is a no-op when absent. `Dict.Add` lowers to key assignment and
overwrites an existing key rather than throwing; `ToDict` follows Python dict
assignment, so a duplicate key keeps the last value. Guard removal, insertion, or
key uniqueness with `Contains`, `ContainsKey`, or an explicit check when C#-style
absence/throw behavior is required.

## 17. Deferred features

- `async`/`await`, async streams, and generators (Phase 4 semantics).
- `[PythonDecorator]`, `[SchemaModel]`, and Pydantic integration (Phase 4).
- `[NativeCompile]` output (Phase 5).
- Full LINQ query syntax (`from x in ... select ...`).
- Events, delegates, and operator overloading.
- `partial` types and advanced generic constraints.
- Structural interface matching.
- Non-integer enums.
- Pattern matching beyond type/value/property patterns.
- `lock`, `unsafe`, and pointer syntax.

Features in this list may parse in limited forms, but they are not part of the
Phase 1 semantic contract unless a milestone gate explicitly includes them.
