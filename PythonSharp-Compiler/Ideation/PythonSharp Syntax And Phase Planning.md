In previous chat "The Myth of Code Transpilation" we established the feasibility of PythonSharp, now lets get into the details of how to create it, first let us plan for major language syntax, then plan next phase targets for covering more grounds




To turn **PythonSharp (`.ps`)** from an architectural concept into a working compiler, we need two things:

1. **A Concrete Language Syntax & Lowering Specification (Phase 1 Core):** Exact rules for how `.ps` syntax is parsed, type-checked, and lowered into clean, zero-overhead Python 3.11+ code.


2. **A Multi-Phase Engineering Roadmap (Next Phase Targets):** A staged plan for expanding from the core transpiler into ecosystem bindings (`ps-bindgen`), Pythonic metaprogramming (decorators, comprehensions, context managers), IDE tooling, and native C-extension compilation (`[NativeCompile]`).



---

# Part 1: Major Language Syntax & Lowering Specification

The golden rule of PythonSharp’s syntax design is **Compile-Time C# Discipline, Runtime Python Isomorphism**. Every syntax construct in `.ps` must either erase completely at compile time or lower 1:1 into high-performance Python AST constructs.

### 1.1 Namespaces, Imports, and File Decoupling

In PythonSharp, physical file paths do not dictate module structure, and circular type references across files are resolved globally by the compiler before code emission.

* **Syntax (`.ps`):**
* `namespace <Identifier>;` declares the logical namespace for the file.


* `using <Namespace>;` imports other PythonSharp namespaces.
* `extern using <py_module> [as <Alias>];` imports native Python packages.



```csharp
// File: src/Domain/Models/Order.ps
namespace Commerce.Domain.Models;

using Commerce.Domain.Services; // Even if OrderService also imports Order!
extern using datetime as dt;
extern using torch;

```

* **Lowering Strategy (`.py`):**
* The compiler aggregates all types belonging to `Commerce.Domain.Models` into a synthesized package path (`commerce/domain/models.py`) or topologically sorted sub-modules.


* Every emitted file begins with `from __future__ import annotations` so type annotations never trigger runtime import evaluation order crashes.
* Circular runtime imports are automatically deferred or topologically ordered in the generated module initialization.



---

### 1.2 Classes, Access Modifiers, Properties, and `__slots__`

Standard classes provide C# encapsulation (`public`, `private`, `protected`, `internal`) and automatically emit `__slots__` to cut memory overhead by 40–60% compared to standard Python classes.

* **Syntax (`.ps`):**

```csharp
namespace Commerce.Domain;

public class Account : BaseEntity, IAuditable
{
    private readonly string _id;
    internal decimal Balance { get; private set; } = 0.0m;

    public Account(string id, decimal initialBalance) : base(id)
    {
        _id = id;
        Balance = initialBalance;
    }

    // Expression-bodied computed property
    public bool IsOverdrawn => Balance < 0;
}

```

* **Lowering Strategy (`.py`):**
* **Access Modifiers:** `private`, `protected`, and `internal` (scoped to a `.psproj` assembly) are strictly enforced by the PythonSharp type-checker and erased at runtime. Private backing fields are prefixed with a single underscore (`_id`, `_balance`) rather than Python’s `__` name-mangling so inheritance and debugging remain clean.


* **Automatic `__slots__`:** The compiler collects all declared instance fields and auto-property backing fields on the class (excluding those already declared on `BaseEntity`) and emits `__slots__`.


* **Runtime Type Metadata (`__ps_types__`):** Nominal interfaces and generic hierarchy signatures are baked into a static class tuple for $O(1)$ runtime `is`/`as` checks.





```python
# Emitted Python
from __future__ import annotations
from decimal import Decimal

class Account(BaseEntity):
    __ps_types__ = ("Commerce.Domain.Account", "Commerce.Domain.BaseEntity", "Commerce.Domain.IAuditable")
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

---

### 1.3 Method & Constructor Overloading

Python does not support multiple methods with the same name. PythonSharp provides true C# method and constructor overloading by synthesizing a compile-time `@overload` stub block paired with a single runtime type-dispatch method.

* **Syntax (`.ps`):**

```csharp
public class UserLoader
{
    public User Load(int userId) => FetchById(userId);
    public User Load(string email, bool includeInactive = false) => FetchByEmail(email, includeInactive);
}

```

* **Lowering Strategy (`.py`):**
* If overloads differ strictly by **arity (argument count)**, the compiler dispatches on `len(args)` (fastest check).
* If overloads share the same arity, the compiler dispatches using `isinstance()` for native types or `__ps_types__` membership for PythonSharp interfaces.





```python
# Emitted Python
from typing import overload

class UserLoader:
    __slots__ = ()

    @overload
    def load(self, user_id: int) -> User: ...
    @overload
    def load(self, email: str, include_inactive: bool = False) -> User: ...

    def load(self, *args) -> User:
        _n = len(args)
        if _n == 1 and isinstance(args[0], int):
            return self.fetch_by_id(args[0])
        if (1 <= _n <= 2) and isinstance(args[0], str):
            return self.fetch_by_email(args[0], args[1] if _n == 2 else False)
        raise TypeError(f"No matching overload for UserLoader.load with args {args}")

```

---

### 1.4 Records, Structs, and Enums

For data transfer objects (DTOs) and value types, PythonSharp maps C# `record` and `struct` declarations directly to Python 3.10+ slotted `@dataclass` definitions.

| PythonSharp Construct | Mutability | Emitted Python Construct |
| --- | --- | --- |
| `public record UserDto(int Id, string Name);` | Immutable by default | `@dataclass(slots=True, frozen=True)` |
| `public record struct Point(double X, double Y);` | Mutable value semantics | `@dataclass(slots=True)` + copy-on-pass semantics |
| `public enum Status { Pending = 1, Active = 2 }` | Immutable enum | `class Status(enum.IntEnum): ...` |

---

### 1.5 The `primitive` Keyword & Zero-Cost Native Bindings

To prevent wrapper overhead when working with Python built-ins (`list`, `dict`, `str`, `set`) or C-extensions (`numpy.ndarray`, `torch.Tensor`), the `primitive` modifier tells the compiler that the class exists **only at compile time** and erases to the underlying Python type at runtime.

* **Syntax (`.ps`):**

```csharp
namespace PythonSharp.Core;

[MapsTo("dict")]
public primitive class Dict<TKey, TValue>
{
    [MapsTo("get")]
    public extern TValue? GetOrDefault(TKey key, TValue? defaultValue = default);

    [MapsTo("keys")]
    public extern IEnumerable<TKey> Keys();

    // Operator mapping: dict[key]
    public extern TValue this[TKey key] { get; set; }

    // Emits inline Python 'key in dict'
    [InlineTemplate("{0} in {self}")]
    public extern bool ContainsKey(TKey key);
}

```

* **Lowering Strategy (`.py`):**
* `var cache = new Dict<string, int>();` $\rightarrow$ `cache: dict[str, int] = {}`
* `if (cache.ContainsKey("id"))` $\rightarrow$ `if "id" in cache:`
* `int val = cache.GetOrDefault("id", 0);` $\rightarrow$ `val: int = cache.get("id", 0)`





---

### 1.6 Expressions, Slicing, Null-Safety, and Control Flow

PythonSharp bridges modern C# (C# 8–12) expressions directly to Python 3.11+ constructs:

1. **Range & Index Slicing:**
* C# `^n` (from-end index) lowers to `-n`.


* C# `a..b` lowers to `a:b`.


* We extend C# range syntax with an optional step operator `a..b:step` to cover full NumPy/PyTorch tensor slicing:
* `tensor[1..5, ^2.., ::2]` $\rightarrow$ `tensor[1:5, -2:, ::2]`.






2. **Named Arguments, `*args`, and `**kwargs`:**
* Named arguments lower 1:1 into keyword arguments: `model.Fit(x, y, epochs: 10)` $\rightarrow$ `model.fit(x, y, epochs=10)`.


* `params T[] items` lowers to `*items: T`.
* `[KwArgs] Dict<string, object> options` lowers to `**options: object`.


3. **Null-Safety Operators (`??`, `??=`, `?.`):**
* `x ?? defaultVal` $\rightarrow$ `(_t if (_t := x) is not None else default_val)` (avoiding Python's truthiness pitfall where `0 or default_val` evaluates to `default_val`!).
* `user?.Profile?.Name` $\rightarrow$ `(_t1.name if (_t0 := user) is not None and (_t1 := _t0.profile) is not None else None)`.


4. **Pattern Matching (`switch` $\rightarrow$ `match / case`):**
* C# `switch` statements and expressions lower directly to Python 3.10+ structural pattern matching (`match` / `case`), using `__ps_types__` guards when matching against PythonSharp interfaces.




5. **Resource Management (`using` $\rightarrow$ `with`):**
* Implementing `IDisposable` (`public void Dispose()`) automatically generates `__enter__` and `__exit__` methods on the Python class.
* `using var file = File.Open("data.csv");` lowers directly to `with File.open("data.csv") as file:`.



---

# Part 2: Next-Phase Targets for Covering More Ground

Once the core syntax grammar and AST lowering rules above are locked in, we can build out the ecosystem in **five structured phases**.

```
Phase 1: Bootstrap Compiler & AST Emitter (Core .ps -> .py/.pyc)
   │
   ▼
Phase 2: PythonSharp.Core & LINQ-to-Comprehensions
   │
   ▼
Phase 3: Ecosystem Bridge (ps-bindgen: .pyi -> .d.ps)
   │
   ▼
Phase 4: Pythonic Metaprogramming (Decorators, Async, Pydantic)
   │
   ▼
Phase 5: Build Toolchain (.psproj), LSP, & [NativeCompile]

```

---

### Phase 1: The Bootstrap Compiler & Two-Pass Architecture

Instead of single-file transpilation, the compiler must operate as a **whole-project analyzer** to resolve namespaces and overloads across files.

* **Target 1.1: Parser & Global Symbol Table (Pass 1):**
* Scan all `.ps` and `.d.ps` files in a project.


* Register every `namespace`, `class`, `interface`, `record`, `primitive`, and method signature into a unified Symbol Table before inspecting method bodies. This immediately eliminates forward-reference and circular-type issues.




* **Target 1.2: Type Checker & Overload Resolver (Pass 2):**
* Validate access modifiers (`private`, `protected`, `internal`), generic constraints (`where T : IEntity`), and nullability (`string` vs. `string?`).


* Resolve every method call to its exact target signature (determining whether a call hits a `primitive` inline template, an overloaded method, or a standard method).




* **Target 1.3: Python `ast` Emitter & Bytecode Line-Pinning (Pass 3):**
* Rather than concatenating strings, emit native Python `ast.AST` nodes.
* Attach the original `.ps` line number (`lineno`) and column offset (`col_offset`) to every generated Python AST node, and compile `.pyc` bytecode with `co_filename = "<OriginalFile>.ps"` so CPython stack traces point directly to `.ps` source lines natively.





---

### Phase 2: `PythonSharp.Core` & Zero-Cost LINQ Lowering

C# developers love **LINQ** (`.Where()`, `.Select()`, `.Any()`, `.All()`, `.FirstOrDefault()`), but chaining lambdas in Python (`map`/`filter`) adds function-call overhead.

* **Target 2.1: Standard `primitive` Library (`PythonSharp.Core`):**
* Define zero-cost `.d.ps` mappings for `List<T>`, `Dict<K,V>`, `HashSet<T>`, `String`, `Tuple`, `Math`, and `DateTime`.




* **Target 2.2: LINQ-to-Comprehension Compiler Pass:**
* Detect chained LINQ queries on `IEnumerable<T>` / `List<T>` at the AST level and lower them directly into **native Python list/generator comprehensions**:
* **PythonSharp Input:**
```csharp
var activeEmails = users
    .Where(u => u.IsActive && u.Age >= 18)
    .Select(u => u.Email.ToLower())
    .ToList();

```


* **Emitted Python (Zero Lambda Overhead):**
```python
active_emails = [u.email.lower() for u in users if u.is_active and u.age >= 18]

```


* Similarly, `.Any(x => ...)` lowers to `any(... for x in ...)` and `.All(x => ...)` lowers to `all(... for x in ...)`.



---

### Phase 3: The Ecosystem Bridge (`ps-bindgen`)

PythonSharp is only useful if a developer can install `fastapi`, `pandas`, `polars`, or `torch` and immediately use them with full static typing and C#-style naming.

* **Target 3.1: Automated `.pyi` Stub Parser (`ps-bindgen`):**
* Use Python’s native `ast` module to parse `.pyi` stub files from `typeshed` or installed site-packages.


* Automatically emit ambient `.d.ps` declaration files wrapped in `namespace Extern.<PackageName>;`.




* **Target 3.2: Automatic C# Naming Convention Aliasing:**
* Convert Python `snake_case` functions/methods into C# `PascalCase` signatures decorated with `[MapsTo("snake_case")]`.


* Convert Python `Union[A, B]` (when not `Optional`) into overloaded method signatures in `.d.ps` so C# callers don't have to deal with awkward union types!
* Convert `*args` and `**kwargs` into typed `params` or optional named parameter lists based on `@overload` stubs in the `.pyi` file.





---

### Phase 4: Pythonic Metaprogramming, Decorators & Async Ecosystem

Modern Python frameworks (FastAPI, Pytest, Celery, LangChain, PyTorch Lightning) rely heavily on **decorators** (`@app.get`, `@pytest.fixture`, `@torch.no_grad()`), **Pydantic models**, and **async generators**.

* **Target 4.1: C# Attributes $\rightarrow$ Python Decorators:**
* Any attribute inheriting from `PythonDecoratorAttribute` (or imported from an external Python module) lowers directly into a `@decorator` above the emitted Python class or function:
* **PythonSharp Input:**
```csharp
[app.Get("/users/{id}")]
public async Task<UserDto> GetUser(int id) { ... }

```


* **Emitted Python:**
```python
@app.get("/users/{id}")
async def get_user(id: int) -> UserDto: ...

```




* **Target 4.2: First-Class Pydantic / Schema Integration:**
* Adding `[SchemaModel]` (or inheriting from `BaseModel`) on a PythonSharp `record` or `class` suppresses `__slots__` and emits a `pydantic.BaseModel` subclass with full field validation attributes (`[Field(MinLength = 3)]` $\rightarrow$ `Field(min_length=3)`).


* **Target 4.3: Async Streams (`IAsyncEnumerable<T>`):**
* Lower `async IAsyncEnumerable<T>` with `yield return` directly into Python async generators (`async def` with `yield`), and `await foreach (var item in stream)` into `async for item in stream:`.



---

### Phase 5: Project Tooling (`.psproj`), IDE Support (LSP), and `[NativeCompile]`

The final phase turns the compiler into a cohesive developer experience and unlocks C-level speed where needed.

* **Target 5.1: The `.psproj` Build Orchestrator (`ps` CLI):**
* A single XML or TOML project file (`App.psproj`) that defines assembly boundaries (`internal` visibility), target Python version, and PyPI dependencies.


* Running `ps add polars` invokes `uv` under the hood to install the package into `.venv` and immediately triggers `ps-bindgen` to generate `.ps-stubs/polars.d.ps`.


* Running `ps build --wheel` outputs a standard, zero-dependency Python `.whl` ready for Docker, AWS Lambda, or Databricks.




* **Target 5.2: Language Server (`ps-lsp`):**
* Exposes Pass 1 & Pass 2 of the PythonSharp compiler over the Language Server Protocol (LSP) for VS Code / Cursor.
* Delivers instant red squiggles on `private`/`internal` violations, auto-imports across namespaces, and hover documentation pulled from `.d.ps` stubs.




* **Target 5.3: Selective Native Compilation (`[NativeCompile]`):**
* When a class or module is marked `[NativeCompile]`, the emitter switches from standard dynamic perks to strict **`mypyc`-compatible** or **Cython (`cdef class`)** output.


* Because PythonSharp already forbids dynamic attribute injection and enforces strict method types, `[NativeCompile]` classes compile cleanly via `mypyc` into native `.so` / `.pyd` C-extensions for 10x–50x speedups on CPU-bound loops.





---

### Suggested Immediate Next Step

To start building **Phase 1**, we can either:

1. **Design the formal EBNF Grammar & AST Node Definitions** for the core `.ps` subset (Namespaces, Classes, `primitive` declarations, Properties, and Method Overloads), or
2. **Prototype the Bootstrap Transpiler Core in Python/Rust** that takes a sample multi-file `.ps` input (with `primitive` types, overloads, and circular class references) and emits the exact `.py` and `.pyc` output.

Which of these two would you like to tackle first?







Design the formal EBNF Grammar & AST Node Definitions for the core .ps subset 




Here is the **Formal EBNF Grammar & Multi-Pass AST Specification** for the core **PythonSharp (`.ps` / `.d.ps`)** language subset.

It is designed so that **Pass 1** parses strict, file-independent C# syntax, **Pass 2 (Global Symbol, Overload & Slot Analyzer)** populates semantic lowering slots across the whole project (resolving circular imports, `__slots__` hierarchies, `primitive` type erasure, and overload dispatch tables), and **Pass 3** lowers the decorated AST directly into Python 3.11+ `ast.AST` nodes with `.ps` bytecode line-pinning (`co_filename` and `lineno`).

---

# Part 1: Lexical Specification & Architectural Keywords

PythonSharp shares C#’s core lexical structure (UTF-8 identifiers, `//` and `/* */` comments, `$"..."` interpolated strings, and numeric literals including `m` for `decimal.Decimal`), paired with **six architectural keywords and contextual tokens** that bridge C# discipline to the Python runtime:

| Keyword / Token | Architectural Purpose |
| --- | --- |
| **`namespace` / `using**` | Decouples logical module structure from physical file paths; compiler resolves circular type references globally and emits topologically sorted Python packages.

 |
| **`extern using`** | Imports a native Python module or package from the environment (e.g., `extern using torch.nn as nn;`).

 |
| **`primitive` (`primitive class`)** | Declares a zero-cost compile-time facade over a native Python or C-extension type (`dict`, `list`, `torch.Tensor`) that erases completely at runtime.

 |
| **`internal` / `private` / `protected**` | Enforces assembly-level (`.psproj`) and class-level encapsulation strictly at compile time before erasing at runtime.

 |
| **`..` / `^` / `:` (Multi-Dim Slicing)** | Extends C# 8+ `Index` (`^1`) and `Range` (`1..5`) syntax with step slices (`1..10:2`, `::2`) and multi-axis indexing (`tensor[1..5, ^2..]`) that lower 1:1 to Python `slice` objects.

 |
| **`params` & `[KwArgs]**` | Maps C# variadic parameters and dictionary options directly to Python `*args` and `**kwargs`.

 |

---

# Part 2: Formal EBNF Grammar (`.ps` & `.d.ps` Core Subset)

```ebnf
(* ========================================================================= *)
(* 1. COMPILATION UNIT, NAMESPACES & IMPORTS                                 *)
(* ========================================================================= *)

CompilationUnit     ::= NamespaceDecl? ImportDecl* TypeDecl* EOF ;

NamespaceDecl       ::= "namespace" QualifiedIdent ";" ;

ImportDecl          ::= StandardUsing | ExternUsing ;
StandardUsing       ::= "using" ( Ident "=" )? QualifiedIdent ";" ;
ExternUsing         ::= "extern" "using" PyModulePath ( "as" Ident )? ";" ;

QualifiedIdent      ::= Ident ( "." Ident )* ;
PyModulePath        ::= Ident ( "." Ident )* ;


(* ========================================================================= *)
(* 2. ATTRIBUTES (Compiler Directives, [NativeCompile] & Python @decorators) *)
(* ========================================================================= *)

AttributeSection    ::= "[" Attribute ( "," Attribute )* "]" ;
Attribute           ::= QualifiedIdent ( "(" AttributeArgs? ")" )? ;
AttributeArgs       ::= AttributeArg ( "," AttributeArg )* ;
AttributeArg        ::= ( Ident "=" )? Expr ;


(* ========================================================================= *)
(* 3. TOP-LEVEL TYPE DECLARATIONS                                            *)
(* ========================================================================= *)

TypeDecl            ::= AttributeSection* AccessMod? TypeModifier*
                        ( ClassDecl
                        | RecordDecl
                        | StructDecl
                        | InterfaceDecl
                        | EnumDecl ) ;

AccessMod           ::= "public" | "internal" | "protected" | "private" ;
TypeModifier        ::= "abstract" | "sealed" | "partial" | "static" | "primitive" ;

(* 3.1 Classes: Standard (__slots__ by default) or Primitive (Type-Erased)   *)
ClassDecl           ::= "class" Ident TypeParams? BaseList? TypeConstraint*
                        "{" MemberDecl* "}" ;

(* 3.2 Records: Slotted Frozen/Mutable Dataclasses (@dataclass(slots=True))  *)
RecordDecl          ::= "record" "struct"? Ident TypeParams?
                        PrimaryCtorParams? BaseList?
                        ( ";" | "{" MemberDecl* "}" ) ;

PrimaryCtorParams   ::= "(" ( Param ( "," Param )* )? ")" ;

(* 3.3 Structs: Value-Semantic Slotted Dataclasses                           *)
StructDecl          ::= "struct" Ident TypeParams? BaseList?
                        "{" MemberDecl* "}" ;

(* 3.4 Interfaces: Compile-Time Contracts + __ps_types__ Nominal Metadata    *)
InterfaceDecl       ::= "interface" Ident TypeParams? BaseList?
                        "{" InterfaceMember* "}" ;

(* 3.5 Enums: Lowered to enum.IntEnum or enum.Enum                           *)
EnumDecl            ::= "enum" Ident "{" EnumMember ( "," EnumMember )* ","? "}" ;
EnumMember          ::= AttributeSection* Ident ( "=" Literal )? ;

BaseList            ::= ":" TypeRef ( "," TypeRef )* ;
TypeParams          ::= "<" Ident ( "," Ident )* ">" ;
TypeConstraint      ::= "where" Ident ":" TypeRef ( "," TypeRef )* ;


(* ========================================================================= *)
(* 4. CLASS, RECORD & PRIMITIVE MEMBERS                                      *)
(* ========================================================================= *)

MemberDecl          ::= AttributeSection* AccessMod? MemberModifier*
                        ( FieldDecl
                        | PropertyDecl
                        | ConstructorDecl
                        | MethodDecl
                        | IndexerDecl ) ;

MemberModifier      ::= "readonly" | "static" | "virtual" | "override"
                      | "abstract" | "extern" | "async" ;

FieldDecl           ::= TypeRef Ident ( "=" Expr )? ";" ;

PropertyDecl        ::= TypeRef Ident
                        ( "{" AccessorDecl+ "}" ( "=" Expr ";" )?
                        | "=>" Expr ";" ) ;

AccessorDecl        ::= AccessMod? ( "get" | "set" ) ( ";" | Block | "=>" Expr ";" ) ;

(* Supports multi-dimensional indexing & slicing: tensor[1..5, ^2..]         *)
IndexerDecl         ::= TypeRef "this" "[" Param ( "," Param )* "]"
                        "{" AccessorDecl+ "}" ;

(* Multiple constructors in a class are merged into overloaded __init__      *)
ConstructorDecl     ::= Ident "(" ParamList? ")" CtorChain?
                        ( Block | "=>" Expr ";" ) ;
CtorChain           ::= ":" ( "base" | "this" ) "(" ArgList? ")" ;

(* Multiple methods sharing Ident are merged into @overload + dispatch table *)
MethodDecl          ::= TypeRef Ident TypeParams? "(" ParamList? ")"
                        TypeConstraint*
                        ( Block | "=>" Expr ";" | ";" ) ;

InterfaceMember     ::= AttributeSection*
                        ( TypeRef Ident TypeParams? "(" ParamList? ")" ";"
                        | TypeRef Ident "{" AccessorDecl+ "}" ) ;

ParamList           ::= Param ( "," Param )* ;
Param               ::= AttributeSection* ParamMod? TypeRef Ident ( "=" Expr )? ;
ParamMod            ::= "params" ;


(* ========================================================================= *)
(* 5. TYPE REFERENCES (Nullables, Tuples, Callables & Generics)              *)
(* ========================================================================= *)

TypeRef             ::= NonNullType "?"? ;         (* T? -> T | None *)
NonNullType         ::= PrimitiveType
                      | TupleType
                      | QualifiedIdent TypeArgs? ;

PrimitiveType       ::= "void" | "bool" | "int" | "long" | "float"
                      | "double" | "decimal" | "string" | "object" | "dynamic" ;

TupleType           ::= "(" TypeRef Ident? ( "," TypeRef Ident? )+ ")" ;
TypeArgs            ::= "<" TypeRef ( "," TypeRef )* ">" ;


(* ========================================================================= *)
(* 6. STATEMENTS & RESOURCE / ASYNC CONTROL FLOW                             *)
(* ========================================================================= *)

Block               ::= "{" Stmt* "}" ;

Stmt                ::= Block
                      | LocalVarStmt
                      | UsingResourceStmt
                      | IfStmt
                      | WhileStmt
                      | ForEachStmt
                      | ReturnStmt
                      | YieldStmt
                      | ThrowStmt
                      | TryCatchFinallyStmt
                      | SwitchStmt
                      | ExprStmt ;

LocalVarStmt        ::= ( "var" | TypeRef ) Ident "=" Expr ";" ;

(* Lowers to Python `with expr as ident:` or `async with expr as ident:`     *)
UsingResourceStmt   ::= "await"? "using" ( "var" | TypeRef ) Ident "=" Expr ";" ;

IfStmt              ::= "if" "(" Expr ")" Stmt ( "else" Stmt )? ;
WhileStmt           ::= "while" "(" Expr ")" Stmt ;

(* Lowers to `for x in seq:` or `async for x in seq:`                        *)
ForEachStmt         ::= "await"? "foreach" "(" ( "var" | TypeRef ) Ident "in" Expr ")" Stmt ;

ReturnStmt          ::= "return" Expr? ";" ;
YieldStmt           ::= "yield" ( "return" Expr | "break" ) ";" ;
ThrowStmt           ::= "throw" Expr? ";" ;

TryCatchFinallyStmt ::= "try" Block CatchClause* FinallyClause? ;
CatchClause         ::= "catch" ( "(" TypeRef Ident? ")" )? ( "when" "(" Expr ")" )? Block ;
FinallyClause       ::= "finally" Block ;

SwitchStmt          ::= "switch" "(" Expr ")" "{" SwitchSection* "}" ;
SwitchSection       ::= ( "case" Pattern ( "when" Expr )? ":" | "default" ":" )+ Stmt+ ;

ExprStmt            ::= Expr ";" ;


(* ========================================================================= *)
(* 7. EXPRESSIONS, SLICING, NULL-SAFETY, LINQ & PATTERN MATCHING             *)
(* ========================================================================= *)

Expr                ::= AssignmentExpr
                      | LambdaExpr
                      | SwitchExpr ;

AssignmentExpr      ::= NullCoalesceExpr ( AssignOp Expr )? ;
AssignOp            ::= "=" | "+=" | "-=" | "*=" | "/=" | "??=" ;

NullCoalesceExpr    ::= LogicalOrExpr ( "??" NullCoalesceExpr )? ;
LogicalOrExpr       ::= LogicalAndExpr ( "||" LogicalAndExpr )* ;
LogicalAndExpr      ::= EqualityExpr ( "&&" EqualityExpr )* ;
EqualityExpr        ::= RelationalExpr ( ( "==" | "!=" ) RelationalExpr )* ;

(* `is` checks __ps_types__ for interfaces or isinstance() for classes       *)
RelationalExpr      ::= AdditiveExpr ( ( "<" | ">" | "<=" | ">=" ) AdditiveExpr
                                     | "is" Pattern
                                     | "as" TypeRef )? ;

AdditiveExpr        ::= MultiplicativeExpr ( ( "+" | "-" ) MultiplicativeExpr )* ;
MultiplicativeExpr  ::= UnaryExpr ( ( "*" | "/" | "%" | "**" ) UnaryExpr )* ;

(* `^expr` lowers to `-expr` for from-end indexing                           *)
UnaryExpr           ::= ( "!" | "-" | "await" | "^" ) UnaryExpr
                      | PostfixExpr ;

PostfixExpr         ::= PrimaryExpr PostfixOp* ;
PostfixOp           ::= "." Ident TypeArgs? ( "(" ArgList? ")" )?
                      | "?." Ident ( "(" ArgList? ")" )?
                      | "[" IndexOrSliceList "]" ;

(* Extended Slicing: supports `1..5`, `^2..`, `1..10:2`, and `::2`           *)
IndexOrSliceList    ::= IndexOrSlice ( "," IndexOrSlice )* ;
IndexOrSlice        ::= Expr
                      | Expr? ".." Expr? ( ":" Expr? )?
                      | Expr? ":" Expr? ( ":" Expr? )? ;

PrimaryExpr         ::= Literal
                      | InterpolatedString
                      | Ident
                      | "this"
                      | "base"
                      | "new" TypeRef "(" ArgList? ")" ObjectInitializer?
                      | "[" ( Expr ( "," Expr )* )? "]"
                      | "(" Expr ( "," Expr )* ")" ;

ObjectInitializer   ::= "{" ( Ident "=" Expr ( "," Ident "=" Expr )* )? "}" ;

(* Named arguments `name: val` lower 1:1 to Python keyword args `name=val`   *)
ArgList             ::= Arg ( "," Arg )* ;
Arg                 ::= ( Ident ":" )? Expr ;

LambdaExpr          ::= "async"? ( Ident | "(" ( Param ( "," Param )* )? ")" )
                        "=>" ( Expr | Block ) ;

SwitchExpr          ::= PostfixExpr "switch" "{" SwitchArm ( "," SwitchArm )* ","? "}" ;
SwitchArm           ::= Pattern ( "when" Expr )? "=>" Expr ;

Pattern             ::= "_"
                      | "null"
                      | Literal
                      | TypeRef Ident? ( "{" PropertyPattern ( "," PropertyPattern )* "}" )? ;
PropertyPattern     ::= Ident ":" Pattern ;

```

---

# Part 3: Multi-Pass AST & Semantic Slot Specification

In PythonSharp, the compiler runs three distinct phases over the AST:

1. **Pass 1 (Syntactic Parse & Global Symbol Registration):** Parses all `.ps` and `.d.ps` files into AST nodes with exact `SourceSpan` metadata (used in Pass 3 to inject `.ps` filenames and line numbers directly into `.pyc` bytecode).


2. **Pass 2 (Semantic, Overload & Slot Resolution):** Resolves circular type references across namespaces, computes deduplicated `__slots__` tuples across inheritance chains, builds `__ps_types__` nominal interface tuples, groups overloaded methods into dispatch tables, and detects LINQ chains eligible for comprehension lowering.


3. **Pass 3 (Python `ast` Lowering & Bytecode Emitter):** Emits clean Python 3.11+ code and `.pyc` files.



Below is the concrete AST data schema (written in Rust for a high-speed `psc` compiler, though equally implementable in Python or C#):

```rust
// ============================================================================
// 1. SOURCE LINE-PINNING METADATA (POWERS NATIVE .PS TRACEBACKS IN CPYTHON)
// ============================================================================

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceSpan {
    pub file_id: usize,
    pub original_ps_filename: String, // Injected into Python code object `co_filename`
    pub start_line: u32,              // Injected into Python ast.AST `lineno`
    pub start_col: u32,               // Injected into Python ast.AST `col_offset`
    pub end_line: u32,
    pub end_col: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct SymbolId(pub u32);

// ============================================================================
// 2. PASS 2 SEMANTIC SLOTS (PYTHONSHARP LOWERING DECISIONS)
// ============================================================================

/// Determines how a TypeDecl is emitted at runtime in Python
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ClassEmissionStrategy {
    Unresolved,
    /// Erased completely at runtime; calls use `[MapsTo]` or `[InlineTemplate]`
    ErasedPrimitive { py_runtime_type: String },
    /// Standard PythonSharp class with auto-computed `__slots__` and `__ps_types__`
    SlottedClass {
        own_slots: Vec<String>,          // Excludes base class slots to avoid Python ValueError!
        ps_types_tuple: Vec<String>,     // e.g., ("Commerce.Account", "Commerce.IAuditable")
        generates_context_manager: bool, // True if implements IDisposable -> emits __enter__/__exit__
    },
    /// Emits `@dataclass(slots=True, frozen=...)`
    SlottedDataclass { is_frozen: bool },
    /// Emits `pydantic.BaseModel` subclass (suppresses `__slots__`)
    SchemaModel,
    /// Emits `mypyc` / Cython-strict class when decorated with `[NativeCompile]`
    NativeCompiledClass,
}

/// Controls how a method call or property access lowers into Python AST
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MemberLoweringMode {
    Unresolved,
    /// Standard snake_case Python method or `@property`
    StandardPython { emitted_snake_name: String },
    /// Part of an overloaded method group; dispatches via synthesized runtime router
    OverloadedVariant {
        group_snake_name: String,
        overload_index: usize,
        runtime_guard: OverloadGuard,
    },
    /// Direct mapping on a `primitive` type: e.g., `[MapsTo("get")]` -> `obj.get(...)`
    PrimitiveDirect { py_target_name: String },
    /// Inline template substitution: e.g., `[InlineTemplate("{0} in {self}")]`
    PrimitiveInlineTemplate { template: String },
}

/// Generated by Pass 2 to dispatch overloaded methods/constructors at runtime
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OverloadDispatchGroup {
    pub snake_name: String,
    pub variants: Vec<SymbolId>,
    /// True if all variants have distinct argument counts (allows fast `len(args)` dispatch!)
    pub is_strictly_arity_disjoint: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OverloadGuard {
    pub min_arity: usize,
    pub max_arity: usize,
    pub param_type_checks: Vec<(usize, RuntimeTypeCheck)>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RuntimeTypeCheck {
    NoneRequired,
    PyIsInstance(String),      // e.g., `isinstance(args[0], (int, str))`
    PsTypesContains(String),   // e.g., `"Commerce.IRetryable" in getattr(args[0], "__ps_types__", ())`
}

// ============================================================================
// 3. COMPILATION UNIT & TOPOLOGICALLY SORTED NAMESPACES
// ============================================================================

#[derive(Clone, Debug)]
pub struct CompilationUnit {
    pub file_id: usize,
    pub is_ambient_stub: bool,          // True for `.d.ps` files generated by `ps-bindgen`
    pub namespace: Vec<String>,         // e.g., ["Commerce", "Domain", "Models"]
    pub imports: Vec<ImportDecl>,
    pub types: Vec<TypeDecl>,

    // --- Pass 2 Slot ---
    pub emitted_py_module_path: String, // e.g., "commerce/domain/models.py"
}

#[derive(Clone, Debug)]
pub struct TypeDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,              // Enforced in Pass 2; erased in Pass 3
    pub is_primitive: bool,
    pub is_record: bool,
    pub is_struct: bool,
    pub is_interface: bool,
    pub name: String,
    pub type_params: Vec<String>,
    pub base_types: Vec<TypeRef>,
    pub members: Vec<MemberDecl>,

    // --- Pass 2 Semantic Slots ---
    pub emission_strategy: ClassEmissionStrategy,
    pub overload_groups: Vec<OverloadDispatchGroup>, // Grouped methods & constructors
    pub topological_order_rank: usize,               // Prevents circular import crashes
    pub decorators_to_emit: Vec<Expr>,               // Lowered from PythonDecorator attributes
}

// ============================================================================
// 4. CLASS & PRIMITIVE MEMBERS
// ============================================================================

#[derive(Clone, Debug)]
pub enum MemberDecl {
    Field(FieldDecl),
    Property(PropertyDecl),
    Constructor(MethodDecl),
    Method(MethodDecl),
    Indexer(IndexerDecl),
}

#[derive(Clone, Debug)]
pub struct PropertyDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub access: AccessMod,
    pub name: String,
    pub ty: TypeRef,
    pub getter: Option<AccessorBody>,
    pub setter: Option<(AccessMod, AccessorBody)>,
    pub initializer: Option<Expr>,

    // --- Pass 2 Semantic Slots ---
    pub backing_slot_name: Option<String>, // e.g., `Some("_balance")` -> added to `__slots__`
    pub emitted_snake_name: String,        // e.g., `"balance"` -> `@property def balance(self)`
}

#[derive(Clone, Debug)]
pub struct MethodDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub is_static: bool,
    pub is_async: bool,
    pub is_extern: bool,
    pub name: String,
    pub type_params: Vec<String>,
    pub params: Vec<ParamDecl>,
    pub return_type: TypeRef,
    pub body: Option<Block>,

    // --- Pass 2 Semantic Slots ---
    pub lowering_mode: MemberLoweringMode,
    pub is_generator: bool,          // True if body contains `yield return`
    pub decorators_to_emit: Vec<Expr>,
}

#[derive(Clone, Debug)]
pub struct ParamDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub name: String,
    pub emitted_snake_name: String,
    pub ty: TypeRef,
    pub default_value: Option<Expr>,
    pub is_params_varargs: bool,     // Lowers to `*args: T`
    pub is_kwargs_dict: bool,        // Marked with `[KwArgs]` -> lowers to `**kwargs: T`
}

// ============================================================================
// 5. EXPRESSIONS & PYTHONIC LOWERING NODES
// ============================================================================

#[derive(Clone, Debug)]
pub struct Expr {
    pub span: SourceSpan,            // Preserved on every emitted Python `ast.expr` node!
    pub kind: ExprKind,
    pub resolved_type: Option<ResolvedType>,
}

#[derive(Clone, Debug)]
pub enum ExprKind {
    Literal(LiteralValue),
    Identifier { name: String, resolved_symbol: Option<SymbolId> },
    Binary { op: BinaryOp, left: Box<Expr>, right: Box<Expr> },

    /// `a ?? b` -> lowered to walrus `(_t if (_t := a) is not None else b)`
    NullCoalesce { left: Box<Expr>, right: Box<Expr>, temp_var_name: String },

    /// `a?.B` -> lowered to `(_t.b if (_t := a) is not None else None)`
    NullConditionalAccess { target: Box<Expr>, member_snake_name: String, temp_var_name: String },

    /// `x is IAuditable a` -> checks `"Commerce.IAuditable" in getattr(x, "__ps_types__", ())`
    TypeCheckIs { expr: Box<Expr>, check: RuntimeTypeCheck, bind_var: Option<String> },

    /// Multi-axis tensor/collection indexing: `tensor[1..5, ^2.., ::2]`
    IndexOrSlice { target: Box<Expr>, dimensions: Vec<SliceDimension> },

    MethodCall {
        receiver: Option<Box<Expr>>,
        method_name: String,
        args: Vec<CallArg>,
        // --- Pass 2 Slot ---
        resolved_lowering: MemberLoweringMode,
    },

    /// Fused by Pass 2 when `.Where()` / `.Select()` / `.ToList()` / `.Any()` are chained!
    LinqComprehension {
        source: Box<Expr>,
        item_var: String,
        filter_predicates: Vec<Expr>,
        projection: Option<Box<Expr>>,
        terminal_kind: ComprehensionKind, // List `[...]`, Set `{...}`, Generator `(...)`, Any, All
    },
}

#[derive(Clone, Debug)]
pub enum SliceDimension {
    SingleIndex { expr: Box<Expr>, is_from_end_caret: bool }, // `^2` -> `-2`
    RangeSlice {
        start: Option<(Box<Expr>, bool)>, // (expr, is_from_end_caret)
        stop: Option<(Box<Expr>, bool)>,
        step: Option<Box<Expr>>,
    },
}

#[derive(Clone, Debug)]
pub struct CallArg {
    pub span: SourceSpan,
    pub keyword_name: Option<String>, // `epochs: 10` -> `ast.keyword(arg="epochs", value=10)`
    pub value: Expr,
}

```

---

# Part 4: Concrete End-to-End AST Lowering Trace

Let’s trace how a single `.ps` file containing **access modifiers**, **auto-properties**, **method overloading**, **`primitive` dictionary calls**, **LINQ**, and **`IDisposable`** flows through **Pass 1 $\rightarrow$ Pass 2 $\rightarrow$ Pass 3**.

### 1. Input Source (`OrderService.ps` — Lines 1 to 38)

```csharp
/* Line 01 */ namespace Commerce.Services;
/* Line 02 */ 
/* Line 03 */ using PythonSharp.Core;
/* Line 04 */ 
/* Line 05 */ public interface IAuditable { string AuditTag { get; } }
/* Line 06 */ 
/* Line 07 */ public record Order(int Id, decimal Total, bool IsActive);
/* Line 08 */ 
/* Line 09 */ public class OrderCache : IAuditable, IDisposable
/* Line 10 */ {
/* Line 11 */     private readonly Dict<int, Order> _store = new Dict<int, Order>();
/* Line 12 */     public string AuditTag { get; private set; }
/* Line 13 */ 
/* Line 14 */     public OrderCache(string tag) => AuditTag = tag;
/* Line 15 */ 
/* Line 16 */     public void Put(Order order) => _store[order.Id] = order;
/* Line 17 */     public void Put(int id, decimal total) => _store[id] = new Order(id, total, true);
/* Line 18 */ 
/* Line 19 */     public List<int> GetActiveIds(decimal minTotal = 0.0m)
/* Line 20 */     {
/* Line 21 */         return _store.Values()
/* Line 22 */             .Where(o => o.IsActive && o.Total >= minTotal)
/* Line 23 */             .Select(o => o.Id)
/* Line 24 */             .ToList();
/* Line 25 */     }
/* Line 26 */ 
/* Line 27 */     public void Dispose() => _store.Clear();
/* Line 28 */ }

```

### 2. How Pass 2 Populates the AST Semantic Slots

1. **`Order` Record Resolution (Line 7):**
* `TypeDecl.emission_strategy` is set to `ClassEmissionStrategy::SlottedDataclass { is_frozen: true }`.


2. **`OrderCache` Slot & Nominal Metadata Resolution (Lines 9–12):**
* `OrderCache` implements `IAuditable` and `IDisposable`.
* Pass 2 populates `emission_strategy = ClassEmissionStrategy::SlottedClass` with:
* `own_slots = ["_store", "_audit_tag"]` (from private field `_store` and auto-property `AuditTag`).


* `ps_types_tuple = ["Commerce.Services.OrderCache", "Commerce.Services.IAuditable", "PythonSharp.Core.IDisposable"]`.


* `generates_context_manager = true` (because `IDisposable` is implemented, Pass 3 synthesizes `__enter__` and `__exit__` calling `self.dispose()`).




3. **`primitive` Type Erasure on `Dict<int, Order>` (Lines 11, 16, 17, 21, 27):**
* `Dict<K,V>` is marked `primitive` with `[MapsTo("dict")]` in `PythonSharp.Core.d.ps`.


* `new Dict<int, Order>()` lowers to `{}`.
* `_store.Values()` lowers via `MemberLoweringMode::PrimitiveDirect { py_target_name: "values" }` to `self._store.values()`.




4. **Overload Dispatch Synthesis on `Put` (Lines 16–17):**
* Pass 2 groups the two `Put` declarations into an `OverloadDispatchGroup` with `is_strictly_arity_disjoint = true` (Variant 0 takes 1 arg; Variant 1 takes 2 args).




5. **LINQ-to-Comprehension Fusion (Lines 21–24):**
* Pass 2 fuses `.Values().Where(...).Select(...).ToList()` into a single `ExprKind::LinqComprehension` node with `terminal_kind = ComprehensionKind::List`.



### 3. Pass 3 Emitted Python 3.11+ AST (`commerce/services.py`)

Every emitted Python statement carries the `.ps` line number (`lineno`) and `co_filename = "OrderService.ps"` in its compiled `.pyc` code object:

```python
# Auto-generated by PythonSharp (psc) — Bytecode pinned to OrderService.ps
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, overload

class IAuditable(Protocol):
    @property
    def audit_tag(self) -> str: ...

@dataclass(slots=True, frozen=True)
class Order:
    __ps_types__ = ("Commerce.Services.Order",)
    id: int
    total: Decimal
    is_active: bool

class OrderCache:
    __ps_types__ = (
        "Commerce.Services.OrderCache",
        "Commerce.Services.IAuditable",
        "PythonSharp.Core.IDisposable",
    )
    __slots__ = ("_store", "_audit_tag")

    def __init__(self, tag: str) -> None:
        self._store: dict[int, Order] = {}
        self._audit_tag: str = tag

    @property
    def audit_tag(self) -> str:
        return self._audit_tag

    @overload
    def put(self, order: Order) -> None: ...
    @overload
    def put(self, id: int, total: Decimal) -> None: ...

    def put(self, *args) -> None:
        _n = len(args)
        if _n == 1 and isinstance(args[0], Order):
            self._store[args[0].id] = args[0]
            return
        if _n == 2 and isinstance(args[0], int):
            self._store[args[0]] = Order(args[0], args[1], True)
            return
        raise TypeError(f"No matching overload for OrderCache.put with args {args!r}")

    def get_active_ids(self, min_total: Decimal = Decimal("0.0")) -> list[int]:
        return [
            o.id
            for o in self._store.values()
            if o.is_active and o.total >= min_total
        ]

    def dispose(self) -> None:
        self._store.clear()

    def __enter__(self) -> OrderCache:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.dispose()

```

---

# Part 5: Compile-Time Verification & Diagnostic Rules (Pass 2.5 Enforcer)

Before Pass 3 emits Python, **Pass 2.5** validates strict C# guarantees that Mypy and Pyright cannot enforce on standard Python:

| Rule ID | Condition Detected in `.ps` AST | Diagnostic Emitted on `.ps` Source Span |
| --- | --- | --- |
| **`PS001`** *(Encapsulation Violation)* | Code accesses a `private` member outside its declaring class, or an `internal` member outside its `.psproj` assembly.

 | `Error [PS001]: Property 'OrderCache.AuditTag.set' is private and cannot be assigned outside 'OrderCache' at Checkout.ps:19.` |
| **`PS002`** *(Ambiguous Runtime Overload)* | Two overloaded methods have the same parameter count and types that erase to the same runtime representation (e.g., `List<int>` vs. `List<string>` on a `primitive` `list`).

 | `Error [PS002]: Overloads 'Process(List<int>)' and 'Process(List<string>)' erase to identical Python runtime type 'list' at Arity 1. Rename one method or use distinct wrapper records.` |
| **`PS003`** *(Circular Value Initialization)* | Two static fields across different files depend on each other's runtime evaluation at module load time (as opposed to circular *type* references, which are always legal).

 | `Error [PS003]: Circular static initializer cycle detected between 'Config.Default' (Config.ps:12) and 'Env.Current' (Env.ps:8).` |
| **`PS004`** *(Invalid `[NativeCompile]` Dynamic Construct)* | A class marked `[NativeCompile]` (targeting `mypyc` C-extension compilation) uses `dynamic` typing.

 | `Error [PS004]: Type 'FastMatrix' is marked [NativeCompile] and cannot use 'dynamic' on line 34.` |

---

### Suggested Next Step

With the **Formal EBNF Grammar & Multi-Pass AST Schema** for PythonSharp complete, we can mirror the next step from our RustSharp design:

1. **Write the formal `PythonSharp.Core.d.ps` Standard Library Specification** (defining `List<T>`, `Dict<K,V>`, `HashSet<T>`, `String`, `Tensor` slicing primitives, `IDisposable`, and the exact LINQ-to-Comprehension rewrite rules), or


2. **Build the executable Phase 1 Bootstrap Transpiler Prototype (`psc`)** in Python using the `ds_python_interpreter` tool to parse `.ps` code, resolve overloads and `__slots__`, and emit both `.py` and line-pinned `.pyc` bytecode!

Which of these would you like to do next?











Write the formal PythonSharp.Core.d.ps Standard Library Specification



Here is the **Formal `PythonSharp.Core.d.ps` Standard Library Specification**.

In the PythonSharp architecture, `PythonSharp.Core.d.ps` is the **ambient compile-time standard library**. None of the `primitive` classes declared in this file exist as wrapper objects at runtime—instead, they provide strict, self-documenting C# APIs (`List<T>`, `Dict<K,V>`, `HashSet<T>`, `String`, `IDisposable`, `Task<T>`, and LINQ) at compile time while instructing **Pass 2 (Semantic, Overload & Comprehension Analyzer)** and **Pass 3 (Python 3.11+ AST Emitter)** how to lower every call 1:1 into zero-overhead native Python constructs (`list`, `dict`, `set`, `str`, `with` context managers, `asyncio` coroutines, and fused list/dict/set/generator comprehensions).

---

# Part 1: Compiler Directive Attributes (`PythonSharp.Runtime.CompilerServices`)

Before declaring the core types, `PythonSharp.Core.d.ps` defines the intrinsic compiler attributes that govern **type erasure**, **inline Python AST templates**, **LINQ comprehension fusion**, **decorator lowering**, and **selective C-extension compilation**.

| Attribute | Target | Pass 2 / Pass 3 Compiler Behavior |
| --- | --- | --- |
| **`[MapsTo("py_symbol")]`** | `primitive class`, `struct`, `interface`, `method`, `property` | Erases the PythonSharp identifier and emits the exact target Python builtin, type annotation, or method call.

 |
| **`[InlineTemplate("...")]`** | `method`, `property`, `indexer`, `constructor` | Substitutes `{self}`, `{0}`, `{1}`, and `{value}` directly into a Python 3.11+ AST expression with zero wrapper function overhead.

 |
| **`[RuntimeType("py_type")]`** | `primitive class` | Specifies the concrete Python runtime class used inside `isinstance(arg, py_type)` checks when synthesizing method overload dispatch tables.

 |
| **`[KwArgs]`** | `parameter` | Lowers a `Dict<string, T>` or `object` parameter into Python `**kwargs: T` at declaration and call sites.

 |
| **`[LinqStage("...")]`** | `method` | Marks an `IEnumerable<T>` method as part of a chainable LINQ query to be fused by Pass 2 into a single Python comprehension or generator expression.

 |
| **`[PythonDecorator]`** | `class` (Attribute) | Marks a C# attribute so that applying `[MyAttr(...)]` to a class or method emits `@my_attr(...)` in Python. |
| **`[SchemaModel]`** | `class`, `record` | Suppresses automatic `__slots__` generation and lowers the type into a `pydantic.BaseModel` subclass for runtime schema validation. |
| **`[NativeCompile]`** | `class`, `struct` | Instructs Pass 3 to emit strict `mypyc` / Cython (`cdef class`) compatible output for native C-extension compilation.

 |

---

# Part 2: Complete `PythonSharp.Core.d.ps` Ambient Specification

```csharp
// ============================================================================
// FILE: PythonSharp.Core.d.ps
// Ambient Standard Library — Zero Runtime Wrapper Tax, 100% Type Erasure
// ============================================================================

namespace PythonSharp.Core;

extern using builtins;
extern using collections.abc as abc;
extern using asyncio;
extern using math as py_math;
extern using datetime as dt;
extern using decimal as dec;

// ----------------------------------------------------------------------------
// 1. COMPILER INTRINSIC ATTRIBUTES
// ----------------------------------------------------------------------------

public abstract class Attribute { }

public sealed class MapsToAttribute : Attribute
{
    public MapsToAttribute(string pythonTarget) { }
}

public sealed class InlineTemplateAttribute : Attribute
{
    public InlineTemplateAttribute(string pythonAstTemplate) { }
}

public sealed class RuntimeTypeAttribute : Attribute
{
    public RuntimeTypeAttribute(string pythonRuntimeType) { }
}

public sealed class KwArgsAttribute : Attribute { }

public sealed class LinqStageAttribute : Attribute
{
    public LinqStageAttribute(string stageKind) { }
}

public class PythonDecoratorAttribute : Attribute
{
    public PythonDecoratorAttribute(string decoratorPath) { }
}

public sealed class SchemaModelAttribute : Attribute { }

public sealed class NativeCompileAttribute : Attribute { }

// ----------------------------------------------------------------------------
// 2. CORE CONTRACTS & CONTEXT MANAGERS (IDisposable -> `with` statement)
// ----------------------------------------------------------------------------

/// Implementing IDisposable on any PythonSharp class automatically synthesizes:
///   def __enter__(self) -> Self: return self
///   def __exit__(self, exc_type, exc_val, exc_tb) -> None: self.dispose()
/// and allows `using var res = ...;` to lower to `with ... as res:`.
[MapsTo("contextlib.AbstractContextManager")]
public interface IDisposable
{
    [MapsTo("dispose")]
    void Dispose();
}

/// Implementing IAsyncDisposable synthesizes `__aenter__` and `__aexit__`
/// and allows `await using var res = ...;` to lower to `async with ... as res:`.
[MapsTo("contextlib.AbstractAsyncContextManager")]
public interface IAsyncDisposable
{
    [MapsTo("dispose_async")]
    Task DisposeAsync();
}

public interface IEquatable<T>
{
    [MapsTo("__eq__")]
    bool Equals(T other);
}

public interface IComparable<T>
{
    [InlineTemplate("(0 if {self} == {0} else (-1 if {self} < {0} else 1))")]
    int CompareTo(T other);
}

// ----------------------------------------------------------------------------
// 3. STRINGS & BYTES (string -> str, Bytes -> bytes)
// ----------------------------------------------------------------------------

[MapsTo("str")]
[RuntimeType("str")]
public primitive class String : IEnumerable<string>
{
    [InlineTemplate("len({self})")]
    public extern int Length { get; }

    [InlineTemplate("(len({self}) == 0)")]
    public extern bool IsEmpty { get; }

    [InlineTemplate("({0} in {self})")]
    public extern bool Contains(string value);

    [MapsTo("startswith")]
    public extern bool StartsWith(string prefix);

    [MapsTo("endswith")]
    public extern bool EndsWith(string suffix);

    [MapsTo("lower")]
    public extern string ToLower();

    [MapsTo("upper")]
    public extern string ToUpper();

    [MapsTo("strip")]
    public extern string Trim();

    [MapsTo("lstrip")]
    public extern string TrimStart();

    [MapsTo("rstrip")]
    public extern string TrimEnd();

    [MapsTo("replace")]
    public extern string Replace(string oldValue, string newValue);

    [MapsTo("split")]
    public extern List<string> Split(string? separator = null, int maxSplit = -1);

    [InlineTemplate("{0}.join({1})")]
    public static extern string Join(string separator, IEnumerable<string> values);

    [InlineTemplate("(not {self} or {self}.isspace())")]
    public static extern bool IsNullOrWhiteSpace(string? value);

    [InlineTemplate("(not {self})")]
    public static extern bool IsNullOrEmpty(string? value);

    [MapsTo("encode")]
    public extern Bytes Encode(string encoding = "utf-8");

    /// Supports single index `s[0]`, from-end `s[^1]`, and range slice `s[1..5]`
    [InlineTemplate("{self}[{0}]")]
    public extern string this[int index] { get; }
}

[MapsTo("bytes")]
[RuntimeType("bytes")]
public primitive class Bytes
{
    [InlineTemplate("len({self})")]
    public extern int Length { get; }

    [MapsTo("decode")]
    public extern string Decode(string encoding = "utf-8");

    [InlineTemplate("{self}[{0}]")]
    public extern int this[int index] { get; }
}

// ----------------------------------------------------------------------------
// 4. COLLECTIONS: List<T> (-> list[T]), Dict<K,V> (-> dict[K,V]), HashSet<T>
// ----------------------------------------------------------------------------

[MapsTo("list")]
[RuntimeType("list")]
public primitive class List<T> : IEnumerable<T>
{
    [InlineTemplate("[]")]
    public extern List();

    [InlineTemplate("list({0})")]
    public extern List(IEnumerable<T> collection);

    [InlineTemplate("len({self})")]
    public extern int Count { get; }

    [InlineTemplate("(len({self}) == 0)")]
    public extern bool IsEmpty { get; }

    [MapsTo("append")]
    public extern void Add(T item);

    [MapsTo("extend")]
    public extern void AddRange(IEnumerable<T> collection);

    [MapsTo("insert")]
    public extern void Insert(int index, T item);

    [MapsTo("remove")]
    public extern void Remove(T item);

    [InlineTemplate("{self}.pop({0})")]
    public extern T RemoveAt(int index);

    [MapsTo("pop")]
    public extern T Pop();

    [MapsTo("clear")]
    public extern void Clear();

    [InlineTemplate("({0} in {self})")]
    public extern bool Contains(T item);

    [MapsTo("index")]
    public extern int IndexOf(T item);

    [MapsTo("sort")]
    public extern void Sort();

    [MapsTo("reverse")]
    public extern void Reverse();

    [MapsTo("copy")]
    public extern List<T> Clone();

    /// Supports `list[i]`, `list[^1]`, and slice `list[1..5:2]`
    [InlineTemplate("{self}[{0}]")]
    public extern T this[int index]
    {
        get;
        [InlineTemplate("{self}[{0}] = {value}")] set;
    }
}

[MapsTo("dict")]
[RuntimeType("dict")]
public primitive class Dict<TKey, TValue> : IEnumerable<KeyValuePair<TKey, TValue>>
{
    [InlineTemplate("{}")]
    public extern Dict();

    [InlineTemplate("len({self})")]
    public extern int Count { get; }

    [InlineTemplate("(len({self}) == 0)")]
    public extern bool IsEmpty { get; }

    [InlineTemplate("{self}[{0}] = {1}")]
    public extern void Add(TKey key, TValue value);

    [MapsTo("get")]
    public extern TValue? GetOrDefault(TKey key, TValue? defaultValue = default);

    [InlineTemplate("({0} in {self})")]
    public extern bool ContainsKey(TKey key);

    [InlineTemplate("({self}.pop({0}, None) is not None)")]
    public extern bool Remove(TKey key);

    [MapsTo("pop")]
    public extern TValue Pop(TKey key, TValue defaultValue);

    [MapsTo("update")]
    public extern void Merge(Dict<TKey, TValue> other);

    [MapsTo("clear")]
    public extern void Clear();

    [MapsTo("keys")]
    public extern IEnumerable<TKey> Keys();

    [MapsTo("values")]
    public extern IEnumerable<TValue> Values();

    [MapsTo("items")]
    public extern IEnumerable<KeyValuePair<TKey, TValue>> Items();

    [InlineTemplate("{self}[{0}]")]
    public extern TValue this[TKey key]
    {
        get;
        [InlineTemplate("{self}[{0}] = {value}")] set;
    }
}

[MapsTo("set")]
[RuntimeType("set")]
public primitive class HashSet<T> : IEnumerable<T>
{
    [InlineTemplate("set()")]
    public extern HashSet();

    [InlineTemplate("set({0})")]
    public extern HashSet(IEnumerable<T> collection);

    [InlineTemplate("len({self})")]
    public extern int Count { get; }

    [MapsTo("add")]
    public extern void Add(T item);

    [MapsTo("discard")]
    public extern void Remove(T item);

    [InlineTemplate("({0} in {self})")]
    public extern bool Contains(T item);

    [MapsTo("clear")]
    public extern void Clear();

    [MapsTo("union")]
    public extern HashSet<T> Union(IEnumerable<T> other);

    [MapsTo("intersection")]
    public extern HashSet<T> Intersect(IEnumerable<T> other);

    [MapsTo("difference")]
    public extern HashSet<T> Except(IEnumerable<T> other);

    [MapsTo("issubset")]
    public extern bool IsSubsetOf(IEnumerable<T> other);
}

[MapsTo("tuple")]
[RuntimeType("tuple")]
public primitive struct KeyValuePair<TKey, TValue>
{
    [InlineTemplate("({0}, {1})")]
    public extern KeyValuePair(TKey key, TValue value);

    [InlineTemplate("{self}[0]")]
    public extern TKey Key { get; }

    [InlineTemplate("{self}[1]")]
    public extern TValue Value { get; }
}

// ----------------------------------------------------------------------------
// 5. ZERO-COST LINQ PIPELINE (IEnumerable<T> -> Fused Comprehensions)
// ----------------------------------------------------------------------------

[MapsTo("collections.abc.Iterable")]
[RuntimeType("collections.abc.Iterable")]
public primitive interface IEnumerable<T>
{
    // --- Lazy Comprehension / Generator Stages (Fused in Pass 2) ---

    [LinqStage("Filter")]
    [InlineTemplate("({x} for {x} in {self} if {0}({x}))")]
    IEnumerable<T> Where(Func<T, bool> predicate);

    [LinqStage("Map")]
    [InlineTemplate("({0}({x}) for {x} in {self})")]
    IEnumerable<TResult> Select<TResult>(Func<T, TResult> selector);

    [LinqStage("FlatMap")]
    [InlineTemplate("({y} for {x} in {self} for {y} in {0}({x}))")]
    IEnumerable<TResult> SelectMany<TResult>(Func<T, IEnumerable<TResult>> selector);

    [LinqStage("Take")]
    [InlineTemplate("itertools.islice({self}, {0})")]
    IEnumerable<T> Take(int count);

    [LinqStage("Skip")]
    [InlineTemplate("itertools.islice({self}, {0}, None)")]
    IEnumerable<T> Skip(int count);

    [LinqStage("OrderBy")]
    [InlineTemplate("sorted({self}, key={0})")]
    IEnumerable<T> OrderBy<TKey>(Func<T, TKey> keySelector);

    [LinqStage("OrderByDescending")]
    [InlineTemplate("sorted({self}, key={0}, reverse=True)")]
    IEnumerable<T> OrderByDescending<TKey>(Func<T, TKey> keySelector);

    [LinqStage("Enumerate")]
    [InlineTemplate("enumerate({self})")]
    IEnumerable<KeyValuePair<int, T>> WithIndex();

    // --- Terminal Comprehension Consumers ---

    [LinqStage("TerminalList")]
    [InlineTemplate("list({self})")]
    List<T> ToList();

    [LinqStage("TerminalSet")]
    [InlineTemplate("set({self})")]
    HashSet<T> ToHashSet();

    [LinqStage("TerminalDict")]
    [InlineTemplate("{ {0}({x}): {1}({x}) for {x} in {self} }")]
    Dict<TKey, TValue> ToDict<TKey, TValue>(
        Func<T, TKey> keySelector,
        Func<T, TValue> valueSelector
    );

    [LinqStage("TerminalAny")]
    [InlineTemplate("any({self})")]
    bool Any();

    [LinqStage("TerminalAnyPred")]
    [InlineTemplate("any({0}({x}) for {x} in {self})")]
    bool Any(Func<T, bool> predicate);

    [LinqStage("TerminalAll")]
    [InlineTemplate("all({0}({x}) for {x} in {self})")]
    bool All(Func<T, bool> predicate);

    [LinqStage("TerminalFirstOrDefault")]
    [InlineTemplate("next(iter({self}), None)")]
    T? FirstOrDefault();

    [LinqStage("TerminalFirstOrDefaultPred")]
    [InlineTemplate("next(({x} for {x} in {self} if {0}({x})), None)")]
    T? FirstOrDefault(Func<T, bool> predicate);

    [LinqStage("TerminalCount")]
    [InlineTemplate("sum(1 for _ in {self})")]
    int Count();

    [LinqStage("TerminalSum")]
    [InlineTemplate("sum({self})")]
    T Sum();

    [LinqStage("TerminalMin")]
    [InlineTemplate("min({self})")]
    T Min();

    [LinqStage("TerminalMax")]
    [InlineTemplate("max({self})")]
    T Max();
}

// ----------------------------------------------------------------------------
// 6. ASYNC & CONCURRENCY PRIMITIVES (Task<T> -> Coroutine / asyncio)
// ----------------------------------------------------------------------------

[MapsTo("collections.abc.Awaitable")]
public primitive class Task
{
    [InlineTemplate("asyncio.sleep({0} / 1000.0)")]
    public static extern Task Delay(int milliseconds);

    [InlineTemplate("asyncio.gather(*{0})")]
    public static extern Task WhenAll(params Task[] tasks);
}

[MapsTo("collections.abc.Awaitable")]
public primitive class Task<TResult> : Task
{
    [InlineTemplate("asyncio.gather(*{0})")]
    public static extern Task<List<TResult>> WhenAll(params Task<TResult>[] tasks);

    [InlineTemplate("asyncio.create_task({0})")]
    public static extern Task<TResult> Run(Task<TResult> coroutine);
}

[MapsTo("collections.abc.AsyncIterable")]
public primitive interface IAsyncEnumerable<T> { }

// ----------------------------------------------------------------------------
// 7. SYSTEM CONSOLE, MATH, DECIMAL & DATETIME FACADES
// ----------------------------------------------------------------------------

public static primitive class Console
{
    [InlineTemplate("print({0})")]
    public static extern void WriteLine(object? value = null);

    [InlineTemplate("print({0}, end=\"\")")]
    public static extern void Write(object? value);

    [InlineTemplate("input({0})")]
    public static extern string ReadLine(string prompt = "");
}

[MapsTo("math")]
public static primitive class Math
{
    [InlineTemplate("math.pi")]
    public static extern double PI { get; }

    [InlineTemplate("abs({0})")]
    public static extern T Abs<T>(T value);

    [InlineTemplate("min({0}, {1})")]
    public static extern T Min<T>(T a, T b);

    [InlineTemplate("max({0}, {1})")]
    public static extern T Max<T>(T a, T b);

    [MapsTo("math.sqrt")]
    public static extern double Sqrt(double d);

    [MapsTo("math.floor")]
    public static extern int Floor(double d);

    [MapsTo("math.ceil")]
    public static extern int Ceiling(double d);

    [InlineTemplate("round({0}, {1})")]
    public static extern double Round(double value, int digits = 0);
}

[MapsTo("datetime.datetime")]
[RuntimeType("datetime.datetime")]
public primitive struct DateTime
{
    [InlineTemplate("datetime.datetime.now(datetime.timezone.utc)")]
    public static extern DateTime UtcNow { get; }

    [InlineTemplate("datetime.datetime.now()")]
    public static extern DateTime Now { get; }

    [MapsTo("isoformat")]
    public extern string ToIsoString();

    [MapsTo("datetime.datetime.fromisoformat")]
    public static extern DateTime ParseIso(string isoString);
}

[MapsTo("datetime.timedelta")]
[RuntimeType("datetime.timedelta")]
public primitive struct TimeSpan
{
    [InlineTemplate("datetime.timedelta(milliseconds={0})")]
    public static extern TimeSpan FromMilliseconds(double ms);

    [InlineTemplate("datetime.timedelta(seconds={0})")]
    public static extern TimeSpan FromSeconds(double seconds);

    [InlineTemplate("datetime.timedelta(minutes={0})")]
    public static extern TimeSpan FromMinutes(double minutes);

    [InlineTemplate("datetime.timedelta(days={0})")]
    public static extern TimeSpan FromDays(double days);

    [MapsTo("total_seconds")]
    public extern double TotalSeconds();
}

```

---

# Part 3: Formal LINQ-to-Comprehension Lowering & Fusion Rules

Unlike naive transpilers that lower `.Where(x => ...)` and `.Select(x => ...)` into nested `map(lambda x: ..., filter(lambda x: ..., seq))` calls—which incur high CPython frame-allocation overhead on every element—**Pass 2** runs a deterministic **Comprehension Fusion Pass** over any chain of `[LinqStage]` calls.

### Rule 1: Lambda Inlining & Alpha-Renaming

When a `.Where(u => cond)` is followed by `.Select(v => expr)`:

1. Pass 2 alpha-renames the parameter `v` in `.Select()` to match the iteration variable `u` bound by `.Where()`.
2. Multiple chained `.Where(u => c1).Where(u => c2)` predicates are conjoined into a single `if c1 and c2` guard inside the comprehension.
3. No `lambda` function object is ever allocated at runtime.

### Rule 2: Terminal Comprehension Bracket Selection

Pass 2 inspects the terminal method of the LINQ chain to choose the exact Python comprehension AST node (`ast.ListComp`, `ast.SetComp`, `ast.DictComp`, or `ast.GeneratorExp`):

| PythonSharp (`.ps`) LINQ Pipeline | Pass 2 Fused AST Node | Emitted Zero-Overhead Python 3.11+ (`.py`) |
| --- | --- | --- |
| `users.Where(u => u.IsActive).Select(u => u.Id).ToList()` | `ast.ListComp` | `[u.id for u in users if u.is_active]` |
| `users.Select(u => u.Role).ToHashSet()` | `ast.SetComp` | `{u.role for u in users}` |
| `users.Where(u => u.IsActive).ToDict(u => u.Id, u => u.Name)` | `ast.DictComp` | `{u.id: u.name for u in users if u.is_active}` |
| `orders.SelectMany(o => o.Items).Where(i => i.Price > 10m).ToList()` | Multi-generator `ast.ListComp` | `[i for o in orders for i in o.items if i.price > Decimal("10")]` |
| `users.Any(u => u.IsAdmin)` | `ast.Call(any, [ast.GeneratorExp])` | `any(u.is_admin for u in users)` |
| `users.All(u => u.IsVerified)` | `ast.Call(all, [ast.GeneratorExp])` | `all(u.is_verified for u in users)` |
| `users.FirstOrDefault(u => u.Id == targetId)` | `next((...), None)` | `next((u for u in users if u.id == target_id), None)` |
| `scores.Where(s => s > 0).Sum()` | `sum(ast.GeneratorExp)` | `sum(s for s in scores if s > 0)` |

---

# Part 4: Type Erasure & Runtime Overload Dispatch Matrix

Because `primitive` classes erase to native Python types at runtime, Pass 2 and Pass 3 treat **compile-time generic annotations** and **runtime `isinstance` overload checks** distinctly:

| PythonSharp Type | Emitted PEP 585 / 604 Type Annotation | Emitted Runtime `isinstance()` Check in `@overload` Dispatcher |
| --- | --- | --- |
| **`int` / `long**` | `int` | `isinstance(arg, int) and not isinstance(arg, bool)` *(guards against Python's `bool` subclassing `int`!)* |
| **`float` / `double**` | `float` | `isinstance(arg, (float, int))` |
| **`decimal`** | `Decimal` | `isinstance(arg, Decimal)` |
| **`string`** | `str` | `isinstance(arg, str)` |
| **`List<T>`** | `list[T]` | `isinstance(arg, list)` *(triggers compile-time error `PS002` if overloaded against `List<U>` at identical arity)* |
| **`Dict<K, V>`** | `dict[K, V]` | `isinstance(arg, dict)` |
| **`HashSet<T>`** | `set[T]` | `isinstance(arg, set)` |
| **`T?` (Nullable)** | `T | None` | `(arg is None or isinstance(arg, T))` |
| **Standard `.ps` `class` / `record**` | `ClassName` | `isinstance(arg, ClassName)` |
| **`.ps` `interface` (`IAuditable`)** | `IAuditable` (`Protocol`) | `"Namespace.IAuditable" in getattr(arg, "__ps_types__", ())` ($O(1)$ tuple check)

 |

---

### Suggested Next Step

We now have the complete architectural foundation for **PythonSharp**:

1. The **Language Syntax & Lowering Specification**,


2. The **Formal EBNF Grammar & Multi-Pass AST Schema**, and


3. The **`PythonSharp.Core.d.ps` Standard Library & Comprehension Fusion Specification**.



Would you like to **build and execute the working Phase 1 Prototype Transpiler (`psc`)** next—running Pass 1 (Parser & Symbol Table), Pass 2 (Encapsulation Verifier, `__slots__` Analyzer, Overload Dispatcher & LINQ-to-Comprehension Fuser), and Pass 3 (Python 3.11+ AST & Line-Pinned `.pyc` Bytecode Emitter) on a multi-file `.ps` project?







just create multi phase plan and then create repomap for codebase of  the working Phase 1 Prototype Transpiler (psc)



Here is the **Multi-Phase Engineering Plan** and the **Complete Repository Map (`repomap`)** for building the working **Phase 1 PythonSharp Prototype Transpiler (`psc`)**.

---

# Part 1: Multi-Phase Implementation Plan for `psc` (Phase 1 Prototype)

To build a working, self-contained Phase 1 prototype of `psc` without getting bogged down in edge cases, the implementation is divided into **six sequential milestones (M1–M6)** following our three-pass compiler architecture. Using **Python 3.11+** as the host implementation language for the Phase 1 bootstrap compiler gives us direct access to Python’s native `ast` and `compile()` machinery for bytecode line-pinning (`co_filename` and `lineno` rewriting).

| Milestone | Phase Name | Core Deliverables | Verification Gate |
| --- | --- | --- | --- |
| **M1** | **Frontend Foundation (Lexer, Parser & Span Tracker)** | • Tokenize `.ps` and `.d.ps` files with exact `SourceSpan` (`file`, `line`, `col`) tracking.

<br>

<br>• Recursive-descent / Pratt parser producing the raw Phase 1 `.ps` AST (`CompilationUnit`, `TypeDecl`, `MemberDecl`, `Stmt`, `Expr`).

 | Parses `PythonSharp.Core.d.ps` and multi-file `.ps` fixtures with 100% span accuracy. |
| **M2** | **Pass 1: Virtual Namespace Aggregator & Global Symbol Table** | • Scan all `.ps` and `.d.ps` files in a project simultaneously.

<br>

<br>• Decouple physical file paths from logical `namespace` declarations.

<br>

<br>• Register all classes, records, interfaces, enums, and `primitive` facades into a unified `GlobalSymbolTable`, resolving circular type references across files.

 | Two `.ps` files in different folders with mutually recursive type references resolve without circular import errors.

 |
| **M3** | **Pass 2A: Encapsulation, `__slots__` & Nominal Metadata (`__ps_types__`)** | • Enforce `private`, `protected`, and `internal` (`.psproj`-scoped) access modifiers (`PS001`).

<br>

<br>• Compute deduplicated `__slots__` tuples across class inheritance chains (auto-generating `_prop` backing slots for auto-properties).

<br>

<br>• Compute static `__ps_types__` nominal hierarchy tuples for $O(1)$ runtime `is` / `as` interface checks.

 | Emits `PS001` on illegal `private` setter access; generates conflict-free `__slots__` and `__ps_types__` on subclasses.

 |
| **M4** | **Pass 2B: `primitive` Type Erasure, Overload Dispatcher & LINQ Fusion** | • Resolve `[MapsTo("...")]` and `[InlineTemplate("...")]` on `primitive` types (`List<T>`, `Dict<K,V>`, `String`).

<br>

<br>• Group overloaded methods and constructors into `OverloadDispatchGroup` tables and verify runtime disambiguability (`PS002`).

<br>

<br>• Fuse chained `.Where().Select().ToList()` / `.Any()` calls into `LinqComprehension` AST nodes.

 | Zero runtime wrapper classes emitted for `Dict`/`List`; overloaded methods dispatch via `@overload` + arity/`isinstance` guards; LINQ chains emit single-pass comprehensions.

 |
| **M5** | **Pass 3: Python 3.11+ `ast.AST` Lowerer & Topological Package Emitter** | • Lower decorated `.ps` AST nodes into native Python `ast.Module` trees.<br>

<br>• Desugar `^n` and `a..b:step` into Python `ast.Slice`, `??` / `?.` into walrus-guarded expressions, and `IDisposable` / `using` into `__enter__`/`__exit__` and `with` blocks.

<br>

<br>• Emit topologically sorted `.py` packages via `ast.unparse()`.

 | Generated `.py` files pass `mypy --strict` / `pyright` and execute cleanly on CPython 3.11+.

 |
| **M6** | **Bytecode Line-Pinning (`.pyc`) & `psc` CLI Orchestrator** | • Stamp every emitted Python `ast.AST` node with the original `.ps` `lineno` and `col_offset`.

<br>

<br>• Compile AST via `compile(tree, filename="OriginalFile.ps", mode="exec")` and write PEP 552 `.pyc` files so CPython tracebacks display `.ps` filenames and line numbers natively.

 | Raising an exception at runtime prints `File "OrderService.ps", line 24` in the standard Python traceback with zero runtime hooks.

 |

---

# Part 2: Complete Repository Map (`repomap`) for `psc`

Below is the directory structure and architectural layout for the Phase 1 prototype repository (`pythonsharp-compiler/`):

```text
pythonsharp-compiler/
├── pyproject.toml                        # Package config, CLI entry point (`psc = psc.cli:main`)
├── README.md                             # Architecture overview & quickstart
│
├── stdlib/                               # Ambient Standard Library Declarations
│   └── PythonSharp.Core.d.ps             # Zero-cost `primitive` mappings (List, Dict, String, LINQ, IDisposable)
│
├── src/
│   └── psc/                              # Core Compiler Package
│       ├── __init__.py
│       ├── cli.py                        # CLI entry point: `psc build`, `psc check`, `psc run`, `psc dump-ast`
│       ├── project.py                    # `.psproj` loader, source discovery, and build configuration
│       ├── diagnostics.py                # SourceSpan, DiagnosticEngine, & PS001–PS004 error formatters
│       │
│       ├── frontend/                     # [MILESTONE 1] Lexer, Parser & Untyped .ps AST
│       │   ├── __init__.py
│       │   ├── tokens.py                 # TokenKind enum & Token dataclass with SourceSpan
│       │   ├── lexer.py                  # Hand-written lexer (supports `$"..."`, `..`, `^`, `??`, `?.`, `10.0m`)
│       │   ├── ast_nodes.py              # Multi-pass .ps AST dataclasses + Pass 2 semantic slots
│       │   └── parser.py                 # Recursive-descent + Pratt expression parser (.ps & .d.ps)
│       │
│       ├── semantics/                    # [MILESTONES 2, 3, 4] Pass 1 & Pass 2 Whole-Project Analyzer
│       │   ├── __init__.py
│       │   ├── symbols.py                # Pass 1: GlobalSymbolTable, SymbolId, NamespaceTree, TypeSymbol
│       │   ├── collector.py              # Pass 1: Multi-file declaration scanner & circular type resolver
│       │   ├── access_checker.py         # Pass 2A: `private`, `protected`, `internal` verifier (Rule PS001)
│       │   ├── slot_analyzer.py          # Pass 2A: `__slots__` deduplicator, `__ps_types__` & IDisposable analyzer
│       │   ├── primitive_resolver.py     # Pass 2B: `[MapsTo]`, `[InlineTemplate]`, & type-erasure resolver
│       │   ├── overload_resolver.py      # Pass 2B: Method/Ctor overload grouper & collision verifier (Rule PS002)
│       │   ├── linq_fuser.py             # Pass 2B: Chained `.Where().Select().ToList()` comprehension fuser
│       │   └── type_checker.py           # Pass 2 orchestrator: expression type inference & call resolution
│       │
│       └── codegen/                      # [MILESTONES 5, 6] Pass 3 Python AST & Bytecode Emitter
│           ├── __init__.py
│           ├── topo_sorter.py            # Topological class & module ordering across virtual namespaces
│           ├── py_ast_builder.py         # Lowers decorated .ps AST -> native Python `ast.AST` with .ps spans
│           ├── overload_emitter.py       # Emits `@overload` stubs + runtime arity/`isinstance`/`__ps_types__` router
│           ├── expr_lowerer.py           # Lowers slices (`^`, `..`), walrus `??`/`?.`, and fused comprehensions
│           └── emitter.py                # Writes formatted `.py` files and line-pinned PEP 552 `.pyc` bytecode
│
└── tests/                                # End-to-End & Unit Test Suite
    ├── test_lexer_parser.py              # M1 unit tests: slicing, records, primitives, attributes
    ├── test_symbol_collector.py          # M2 unit tests: circular cross-file references & namespace merging
    ├── test_access_and_slots.py          # M3 unit tests: PS001 diagnostics, `__slots__` inheritance, `__ps_types__`
    ├── test_overloads_and_linq.py        # M4 unit tests: PS002 collision detection, overload dispatch, LINQ fusion
    ├── test_bytecode_tracebacks.py       # M6 unit tests: verifies CPython tracebacks report `.ps` file & line!
    └── fixtures/
        └── commerce_sample/              # Multi-file sample project (`Commerce.psproj`)
            ├── Commerce.psproj
            ├── Domain/
            │   ├── IAuditable.ps
            │   └── Order.ps              # References OrderCache (circular type dependency test)
            └── Services/
                └── OrderCache.ps         # Uses `Dict<K,V>`, overloads, LINQ, `private set`, and `IDisposable`

```

---

# Part 3: Module-by-Module Symbol Map & Pipeline Signatures

This section maps the exact classes, data structures, and function signatures in each file of `src/psc/` so the codebase can be implemented cleanly module by module.

### 1. Core Infrastructure (`psc/diagnostics.py` & `psc/project.py`)

```text
src/psc/diagnostics.py
├── class SourceSpan( dataclass(frozen=True) )
│   ├── file_id: int
│   ├── ps_filename: str              # e.g., "Services/OrderCache.ps" (injected into .pyc co_filename)
│   ├── start_line: int               # 1-indexed line in .ps file (injected into Python ast.AST.lineno)
│   ├── start_col: int
│   ├── end_line: int
│   └── end_col: int
│
├── class Diagnostic( dataclass )
│   ├── code: str                     # "PS001" | "PS002" | "PS003" | "PS004"
│   ├── severity: Literal["ERROR", "WARNING"]
│   ├── message: str
│   └── span: SourceSpan
│
└── class DiagnosticEngine
    ├── errors: list[Diagnostic]
    ├── report_ps001_access_violation(span, member_name, access_mod, owner_type) -> None
    ├── report_ps002_ambiguous_overload(span, method_name, sig_a, sig_b, erased_py_type) -> None
    ├── report_ps003_circular_static_init(span, cycle_path) -> None
    ├── report_ps004_native_compile_dynamic(span, type_name) -> None
    └── has_errors() -> bool

src/psc/project.py
├── class PsProjectConfig( dataclass )
│   ├── project_name: str             # Assembly boundary for `internal` visibility
│   ├── root_dir: Path
│   ├── out_dir: Path                 # e.g., Path("dist/")
│   ├── emit_pyc: bool                # Default: True (compiles line-pinned .pyc files)
│   └── source_files: list[Path]      # Discovered .ps and .d.ps files
│
└── def load_project(psproj_path: Path) -> PsProjectConfig

```

---

### 2. Frontend Layer (`psc/frontend/`)

```text
src/psc/frontend/tokens.py
├── enum TokenKind
│   ├── Keywords: NAMESPACE, USING, EXTERN, PUBLIC, INTERNAL, PROTECTED, PRIVATE,
│   │             CLASS, RECORD, STRUCT, INTERFACE, ENUM, PRIMITIVE, STATIC, READONLY,
│   │             VIRTUAL, OVERRIDE, ABSTRACT, ASYNC, AWAIT, VAR, NEW, THIS, BASE,
│   │             IF, ELSE, WHILE, FOREACH, IN, SWITCH, CASE, DEFAULT, WHEN,
│   │             RETURN, YIELD, THROW, TRY, CATCH, FINALLY, IS, AS, NULL, PARAMS
│   ├── Operators: DOT_DOT (".."), CARET ("^"), NULL_COALESCE ("??"), NULL_COALESCE_EQ ("??="),
│   │              NULL_COND ("?."), FAT_ARROW ("=>"), COLON (":"), DOUBLE_STAR ("**")
│   └── Literals: IDENT, INT_LIT, FLOAT_LIT, DECIMAL_LIT ("10.0m"), STRING_LIT, INTERP_STRING
│
└── class Token( dataclass )
    ├── kind: TokenKind
    ├── lexeme: str
    └── span: SourceSpan

src/psc/frontend/lexer.py
└── class Lexer
    ├── __init__(self, source: str, file_id: int, ps_filename: str)
    └── tokenize(self) -> list[Token]

src/psc/frontend/ast_nodes.py
├── class CompilationUnit( dataclass )
│   ├── file_id: int
│   ├── ps_filename: str
│   ├── is_ambient_stub: bool         # True if file ends with `.d.ps`
│   ├── namespace: list[str]
│   ├── imports: list[ImportDecl]
│   └── types: list[TypeDecl]
│
├── class TypeDecl( dataclass )
│   ├── symbol_id: SymbolId | None
│   ├── span: SourceSpan
│   ├── attributes: list[AttributeNode]
│   ├── access: AccessMod
│   ├── is_primitive: bool
│   ├── is_record: bool
│   ├── is_struct: bool
│   ├── is_interface: bool
│   ├── name: str
│   ├── type_params: list[str]
│   ├── base_types: list[TypeRef]
│   ├── members: list[MemberDecl]
│   └── # --- Pass 2 Semantic Slots ---
│       ├── emission_strategy: ClassEmissionStrategy
│       ├── overload_groups: list[OverloadDispatchGroup]
│       └── topo_rank: int
│
└── class Expr( dataclass )
    ├── span: SourceSpan
    ├── kind: ExprKind                # Literal | Identifier | Binary | NullCoalesce |
    │                                 # NullConditionalAccess | TypeCheckIs | IndexOrSlice |
    │                                 # MethodCall | LinqComprehension | Lambda | SwitchExpr
    └── resolved_type: ResolvedType | None

src/psc/frontend/parser.py
└── class Parser
    ├── __init__(self, tokens: list[Token], diagnostics: DiagnosticEngine)
    ├── parse_compilation_unit(self) -> CompilationUnit
    ├── parse_type_decl(self) -> TypeDecl
    ├── parse_member_decl(self) -> MemberDecl
    ├── parse_stmt(self) -> Stmt
    └── parse_expr(self, min_prec: int = 0) -> Expr

```

---

### 3. Semantic Analysis Layer (`psc/semantics/`)

```text
src/psc/semantics/symbols.py
├── class TypeSymbol( dataclass )
│   ├── id: SymbolId
│   ├── qualified_name: str           # e.g., "Commerce.Services.OrderCache"
│   ├── namespace: tuple[str, ...]
│   ├── ast_node: TypeDecl
│   ├── is_primitive: bool
│   ├── maps_to_py_type: str | None   # e.g., "dict", "list", "str"
│   ├── runtime_isinstance_type: str | None
│   └── members_by_name: dict[str, list[MemberSymbol]]
│
└── class GlobalSymbolTable
    ├── types_by_qname: dict[str, TypeSymbol]
    ├── namespaces: dict[tuple[str, ...], list[TypeSymbol]]
    ├── register_type(self, unit: CompilationUnit, decl: TypeDecl) -> TypeSymbol
    └── resolve_type_ref(self, ref: TypeRef, current_ns: tuple[str, ...], imports: list[ImportDecl]) -> TypeSymbol

src/psc/semantics/collector.py
└── class SymbolCollector
    └── collect_all(self, units: list[CompilationUnit], symtab: GlobalSymbolTable, diag: DiagnosticEngine) -> None
        # Pass 1: Registers all types & member headers across all files before inspecting bodies

src/psc/semantics/slot_analyzer.py
└── class SlotAndHierarchyAnalyzer
    ├── analyze_type(self, type_sym: TypeSymbol, symtab: GlobalSymbolTable) -> None
    ├── compute_own_slots(self, type_sym: TypeSymbol) -> list[str]
    │   # Collects instance fields + auto-property `_prop` slots; subtracts base class slots!
    ├── compute_ps_types_tuple(self, type_sym: TypeSymbol) -> tuple[str, ...]
    │   # Transitive closure of nominal base classes and interfaces for `__ps_types__`
    └── check_disposable_contract(self, type_sym: TypeSymbol) -> bool
        # Returns True if implements IDisposable -> marks `generates_context_manager = True`

src/psc/semantics/primitive_resolver.py
└── class PrimitiveResolver
    ├── resolve_primitive_type(self, type_sym: TypeSymbol) -> None
    │   # Extracts `[MapsTo("...")]` and `[RuntimeType("...")]` from `.d.ps` declarations
    └── resolve_primitive_member(self, member: MethodDecl | PropertyDecl | IndexerDecl) -> MemberLoweringMode
        # Extracts `[MapsTo("get")]` or `[InlineTemplate("{0} in {self}")]`

src/psc/semantics/overload_resolver.py
└── class OverloadResolver
    ├── build_overload_groups(self, type_sym: TypeSymbol, diag: DiagnosticEngine) -> list[OverloadDispatchGroup]
    │   # Groups methods/ctors sharing a name; verifies erased runtime types do not collide at same arity (PS002)
    └── resolve_call_target(self, call: MethodCall, caller_type: TypeSymbol) -> MemberLoweringMode

src/psc/semantics/linq_fuser.py
└── class LinqComprehensionFuser
    └── try_fuse_method_chain(self, expr: Expr, symtab: GlobalSymbolTable) -> Expr
        # Rewrites chained `[LinqStage]` calls (`.Where().Select().ToList()` / `.Any()` / `.Sum()`)
        # into a single `ExprKind.LinqComprehension` node with alpha-renamed lambda variables

src/psc/semantics/access_checker.py
└── class AccessChecker
    └── verify_member_access(self, span: SourceSpan, caller_type: TypeSymbol, target_member: MemberSymbol, is_write: bool) -> None
        # Enforces `private` (same class), `protected` (subclass), and `internal` (same .psproj) -> emits PS001

```

---

### 4. Code Generation & Bytecode Line-Pinning Layer (`psc/codegen/`)

```text
src/psc/codegen/topo_sorter.py
└── class NamespacePackagePlanner
    └── plan_modules(self, symtab: GlobalSymbolTable) -> dict[str, list[TypeSymbol]]
        # Maps logical namespaces (e.g. `Commerce.Services`) to `commerce/services.py`
        # Topologically sorts classes within each module by inheritance dependencies

src/psc/codegen/py_ast_builder.py
└── class PythonAstBuilder
    ├── build_module(self, ns_types: list[TypeSymbol]) -> ast.Module
    ├── build_class_def(self, type_sym: TypeSymbol) -> ast.ClassDef
    │   # Emits `__ps_types__ = (...)`, `__slots__ = (...)`, properties, methods, and `__enter__`/`__exit__`
    ├── build_record_dataclass(self, type_sym: TypeSymbol) -> ast.ClassDef
    │   # Emits `@dataclass(slots=True, frozen=True)`
    └── stamp_ps_span(self, py_node: ast.AST, ps_span: SourceSpan) -> ast.AST
        # Sets `py_node.lineno = ps_span.start_line`, `py_node.col_offset = ps_span.start_col`

src/psc/codegen/overload_emitter.py
└── class OverloadAstEmitter
    └── emit_overload_group(self, group: OverloadDispatchGroup) -> list[ast.stmt]
        # 1. Emits `@overload def name(...) -> Ret: ...` stubs for static type-checkers
        # 2. Emits unified `def name(self, *args)` dispatcher using `_n = len(args)`,
        #    `isinstance(args[i], ...)` for classes/primitives, and `"Interface" in getattr(args[i], "__ps_types__", ())`

src/psc/codegen/expr_lowerer.py
└── class ExpressionLowerer
    ├── lower_expr(self, expr: Expr) -> ast.expr
    ├── lower_inline_template(self, template: str, receiver: ast.expr | None, args: list[ast.expr]) -> ast.expr
    │   # Parses template into Python `ast.expr` and substitutes `{self}`, `{0}`, `{1}`, `{value}`
    ├── lower_slice_dimension(self, dim: SliceDimension) -> ast.expr | ast.Slice
    │   # Converts `^n` -> `ast.UnaryOp(USub, n)` and `a..b:s` -> `ast.Slice(lower=a, upper=b, step=s)`
    ├── lower_null_coalesce(self, node: NullCoalesce) -> ast.IfExp
    │   # Emits `(_t if (_t := left) is not None else right)`
    └── lower_linq_comprehension(self, node: LinqComprehension) -> ast.ListComp | ast.SetComp | ast.DictComp | ast.Call

src/psc/codegen/emitter.py
└── class ArtifactEmitter
    ├── emit_py_source(self, module_ast: ast.Module, out_py_path: Path) -> str
    │   # Writes clean Python 3.11+ source code via `ast.unparse(module_ast)`
    └── emit_line_pinned_pyc(self, module_ast: ast.Module, original_ps_filename: str, out_pyc_path: Path) -> None
        # Compiles `code_obj = compile(module_ast, filename=original_ps_filename, mode="exec")`
        # Writes valid `.pyc` header + `marshal.dumps(code_obj)` so CPython stack traces point to `.ps`!

```

---

# Part 4: Data Flow Diagram Across the `psc` Codebase

```text
  [ stdlib/PythonSharp.Core.d.ps ]        [ User .ps Files (Arbitrary Folders) ]
                 │                                          │
                 └────────────────────┬─────────────────────┘
                                      ▼
                     ┌─────────────────────────────────┐
                     │  M1: frontend/lexer & parser    │
                     │  Produces CompilationUnit ASTs  │
                     │  with exact .ps SourceSpans     │
                     └────────────────┬────────────────┘
                                      ▼
                     ┌─────────────────────────────────┐
                     │  M2: semantics/collector        │
                     │  Populates GlobalSymbolTable    │
                     │  Resolves circular cross-file   │
                     │  types & virtual namespaces     │
                     └────────────────┬────────────────┘
                                      ▼
       ┌──────────────────────────────┴──────────────────────────────┐
       ▼                                                             ▼
┌────────────────────────────────────┐      ┌────────────────────────────────────┐
│ M3: semantics/slot_analyzer &      │      │ M4: semantics/primitive_resolver,  │
│     access_checker                 │      │     overload_resolver & linq_fuser │
│ • Verifies private/internal (PS001)│      │ • Erases `primitive` types         │
│ • Computes deduplicated __slots__  │      │ • Builds @overload dispatch groups │
│ • Computes __ps_types__ tuple      │      │ • Fuses LINQ -> Comprehensions     │
└──────────────────┬─────────────────┘      └──────────────────┬─────────────────┘
                   └──────────────────┬────────────────────────┘
                                      ▼
                     ┌─────────────────────────────────┐
                     │  M5: codegen/py_ast_builder &   │
                     │      expr_lowerer               │
                     │  Emits Python 3.11+ ast.Module  │
                     │  stamped with .ps line numbers  │
                     └────────────────┬────────────────┘
                                      ▼
                     ┌─────────────────────────────────┐
                     │  M6: codegen/emitter            │
                     │  1. Writes clean `.py` packages │
                     │  2. Compiles `.pyc` with        │
                     │     co_filename = "<File>.ps"   │
                     └─────────────────────────────────┘

```

---

### Ready for Implementation

With this multi-phase plan and `repomap` in place, we can immediately start coding **Milestone 1 & Milestone 2** (or build a single-script executable vertical slice of `psc` that runs all 6 milestones end-to-end on the `commerce_sample` fixture in the Python interpreter). Let me know when you'd like to run or generate the code for the first milestone!

