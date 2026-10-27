In previous chat "The Myth of Code Transpilation" we established the feasibility of RustSharp, now lets get into the details of how to create it, first let us plan for major language syntax, then plan next phase targets for covering more grounds



To turn **RustSharp (`.rsharp`)** from an architectural concept into a working compiler, we need two foundational pillars:

1. **A Concrete Language Syntax & Lowering Specification (Phase 1 Core):** Exact rules for how `.rsharp` syntax is parsed, ownership-checked, and lowered into idiomatic, zero-cost, borrow-checked Rust code.


2. **A Multi-Phase Engineering Roadmap (Next Phase Targets):** A staged plan for expanding from the core transpiler into zero-cost LINQ iterators, automated Cargo crate bindings (`rsharp-bindgen`), procedural macro/async ecosystems (Serde, Tokio, Axum), and IDE/LSP tooling.



---

### Part 1: Major Language Syntax & Lowering Specification

The golden rule of RustSharp’s syntax design is **Compile-Time C# Discipline, Runtime Zero-Cost Rust Isomorphism**. Every syntax construct in `.rsharp` must either erase completely at compile time or lower 1:1 into stack/heap-optimal Rust AST constructs without introducing hidden garbage collection or unnecessary `Arc<Mutex<T>>` wrappers.

##### 1.1 Namespaces, Imports, Access Modifiers, and File Decoupling

In RustSharp, physical file paths do not dictate Rust `mod` trees. Developers organize files freely by feature or domain, and the compiler synthesizes the Cargo module hierarchy automatically.

* **Syntax (`.rsharp`):**
* `namespace <Identifier>;` declares the logical module path for the file.


* `using <Namespace>;` imports other RustSharp namespaces.


* `extern using <crate_path> [as <Alias>];` imports native Rust crates from `Cargo.toml`.





```csharp
// File: src/Features/Checkout/Handlers/OrderHandler.rsharp
namespace Commerce.Checkout;

using Commerce.Domain.Models; // Resolved globally even across circular type references!
extern using tokio::time as time;
extern using rust_decimal::Decimal;

```

* **Lowering Strategy (`.rs`):**
* **Virtual Namespace Aggregation:** The compiler collects all types declared under `namespace Commerce.Checkout` across all `.rsharp` files and emits a unified `src/commerce/checkout.rs` module alongside an auto-generated `src/lib.rs` module tree.


* **Access Modifiers:**
* `public` $\rightarrow$ `pub` (visible outside the crate).


* `internal` $\rightarrow$ `pub(crate)` (visible only within the current `.rsproj` Cargo sub-crate).


* `private` $\rightarrow$ private module/struct item (omits `pub`).


* `protected` $\rightarrow$ `pub(super)` or scoped visibility checked by the RustSharp compiler across flattened struct hierarchies.







---

##### 1.2 The Three Type Archetypes & Whole-Program Borrow Inference

Instead of forcing developers to write `'a` lifetime annotations or `Arc<RwLock<T>>` boilerplate, RustSharp classifies data structures into three explicit architectural archetypes and infers parameter borrows (`&T`, `&mut T`, or owned `T`) via **Interprocedural Escape & Mutation Analysis**.

| RustSharp Archetype | Architectural Role | Emitted Rust Representation |
| --- | --- | --- |
| **`record` / `struct**` | Linear DTOs, value types, and domain messages

 | Plain `pub struct` with `#[derive(Clone, Debug, PartialEq)]`; passed by `&T` or `&mut T` automatically

 |
| **`service class`** | Dependency-injected services & orchestrators

 | Fields enforced as `readonly` after construction; held via lock-free `Arc<T>` or static references

 |
| **`shared class`** | Explicit multi-owner mutable state (caches, graphs)

 | Fields wrapped in `Arc<RwLock<T>>` or `slotmap` arena handles for safe shared mutability

 |

* **Syntax (`.rsharp`):**

```csharp
namespace Commerce.Orders;

public record Order(int Id, decimal Total, List<string> Items);

public service class OrderProcessor
{
    private readonly Database _db; // Implicitly readonly in a service class

    public OrderProcessor(Database db) => _db = db;

    public void ProcessOrder(Order order, string promoCode)
    {
        if (promoCode == "VIP")
        {
            order.Total -= 10.0m;      // Mutation detected on 'order'
        }
        _db.Save(order);               // Read-only borrow detected
    }
}

```

* **Lowering Strategy (`.rs`):**
* **Receiver & Parameter Inference:** By inspecting `ProcessOrder` and its callees, the compiler sees that `this` is only read (`&self`), `order` has its field mutated (`&mut Order`), and `promoCode` is only compared (`&str`).


* **Caller-Site Mutation Injection:** Whenever a caller passes an `Order` variable into `ProcessOrder`, the emitter automatically marks the local variable declaration as `let mut order = ...` and passes `&mut order`.





```rust
// Emitted Idiomatic Rust (src/commerce/orders.rs)
use std::sync::Arc;
use rust_decimal::Decimal;

#[derive(Clone, Debug, PartialEq)]
pub struct Order {
    pub id: i32,
    pub total: Decimal,
    pub items: Vec<String>,
}

pub struct OrderProcessor {
    db: Arc<Database>,
}

impl OrderProcessor {
    pub fn new(db: Arc<Database>) -> Self {
        Self { db }
    }

    pub fn process_order(&self, order: &mut Order, promo_code: &str) {
        if promo_code == "VIP" {
            order.total -= Decimal::new(100, 1);
        }
        self.db.save(&*order);
    }
}

```

---

##### 1.3 Inheritance, Polymorphism, and Interfaces

RustSharp eliminates heap-heavy vtable emulation by distinguishing between **state reuse**, **closed-world hierarchies**, and **open plugin traits**.

1. **State Inheritance $\rightarrow$ Struct Flattening + `Deref`:**
* Declaring `public class PriorityOrder : OrderBase` embeds `pub base: OrderBase` as the first field of `PriorityOrder` and emits `impl Deref<Target OrderBase>` and `impl DerefMut` so base fields are accessed seamlessly without heap indirection.




2. **Closed-World Polymorphism $\rightarrow$ Sealed Enum Dispatch:**
* When an `abstract class` or `interface` is only implemented within the current project (`internal` or `sealed` hierarchy), RustSharp lowers the entire hierarchy into a **Rust Tagged Union (`enum`)** and lowers `virtual`/`override` methods into exhaustive `match` arms.




3. **Open Polymorphism $\rightarrow$ Native Rust `trait`:**
* Marking an interface `public extensible interface IPlugin` emits a native `pub trait IPlugin`, allowing external Cargo crates or co-located `.rs` files to implement it directly.





* **Syntax (`.rsharp`):**

```csharp
namespace Commerce.Payments;

public abstract class Payment
{
    public decimal Amount { get; set; }
    public abstract string Summarize();
}

public class CardPayment : Payment
{
    public string LastFour { get; set; }
    public override string Summarize() => $"Card *{LastFour}: {Amount}";
}

public class CryptoPayment : Payment
{
    public string WalletHash { get; set; }
    public override string Summarize() => $"Wallet {WalletHash}: {Amount}";
}

```

* **Lowering Strategy (`.rs`):**

```rust
// Emitted Rust: Zero-cost Enum Dispatch + Embedded Base Struct
pub struct PaymentBase {
    pub amount: rust_decimal::Decimal,
}

pub struct CardPayment {
    pub base: PaymentBase,
    pub last_four: String,
}

pub struct CryptoPayment {
    pub base: PaymentBase,
    pub wallet_hash: String,
}

pub enum Payment {
    Card(CardPayment),
    Crypto(CryptoPayment),
}

impl Payment {
    pub fn summarize(&self) -> String {
        match self {
            Payment::Card(c) => format!("Card *{}: {}", c.last_four, c.base.amount),
            Payment::Crypto(w) => format!("Wallet {}: {}", w.wallet_hash, w.base.amount),
        }
    }
}

```

---

##### 1.4 Method & Constructor Overloading (Static Monomorphized Dispatch)

Rust does not allow multiple methods or constructors with the same identifier in an `impl` block. Unlike dynamic languages that require runtime `isinstance` checks, RustSharp resolves all overloads **statically at compile time** with zero runtime cost.

* **Syntax (`.rsharp`):**

```csharp
public service class UserRepository
{
    public User Find(int id) => FetchById(id);
    public User Find(string email, bool activeOnly = true) => FetchByEmail(email, activeOnly);
}

```

* **Lowering Strategy (`.rs`):**
* During Pass 2 (Overload Resolution), the compiler matches every call site to its exact signature and emits disambiguated, human-readable Rust method names (`find_by_i32`, `find_by_str`) or defaults when optional arguments are omitted.


* Overloaded constructors (`public User(int id)` vs. `public User(string email)`) lower to idiomatic Rust associated constructors (`User::new(id)` and `User::from_email(email)`).



```rust
// Emitted Rust (Zero Runtime Dispatch Overhead)
impl UserRepository {
    pub fn find_by_id(&self, id: i32) -> User {
        self.fetch_by_id(id)
    }

    pub fn find_by_email(&self, email: &str, active_only: bool) -> User {
        self.fetch_by_email(email, active_only)
    }
}
// Caller `repo.Find("a@b.com")` lowers directly to: `repo.find_by_email("a@b.com", true)`

```

---

##### 1.5 Checked Effect Inference (`throw` / `try-catch` $\rightarrow$ `Result<T, E>` & `?`)

Developers write clean C# exception syntax while the compiler emits monadic `Result<T, E>` error propagation underneath.

* **Syntax (`.rsharp`):**

```csharp
public record ParseError(string Message);

public static class ConfigLoader
{
    public static int ParsePort(string raw) throws ParseError
    {
        if (raw.IsEmpty) throw new ParseError("Port string cannot be empty");
        return 8080;
    }

    public static int LoadDefaultPort(string input)
    {
        try
        {
            return ParsePort(input);
        }
        catch (ParseError err)
        {
            return 80;
        }
    }
}

```

* **Lowering Strategy (`.rs`):**
* Any method marked `throws TError` (or inferred to throw via call-graph analysis) has its return type rewritten from `T` to `Result<T, TError>`.


* Every unguarded call to a throwing method automatically appends the `?` operator.


* `try / catch` blocks lower directly into Rust `match` expressions on the `Result`.





```rust
// Emitted Rust
#[derive(Clone, Debug)]
pub struct ParseError { pub message: String }

pub fn parse_port(raw: &str) -> Result<i32, ParseError> {
    if raw.is_empty() {
        return Err(ParseError { message: "Port string cannot be empty".to_string() });
    }
    Ok(8080)
}

pub fn load_default_port(input: &str) -> i32 {
    match parse_port(input) {
        Ok(_val) => _val,
        Err(err) => 80,
    }
}

```

---

##### 1.6 The `primitive` Keyword & Co-Located `.rs` Files (`extern partial`)

To ensure zero wrapper overhead with Rust's standard library and raw `.rs` systems code, RustSharp uses compile-time `primitive` facades and `extern partial` bindings.

1. **`primitive` Type Erasure:**

```csharp
namespace RustSharp.Core;

[MapsTo("std::vec::Vec")]
public primitive class List<T>
{
    [MapsTo("push")]
    public extern void Add([Moves] T item); // [Moves] tells escape analysis this consumes T!

    [MapsTo("len")]
    public extern int Count { get; }

    [InlineTemplate("{self}.contains(&{0})")]
    public extern bool Contains(T item);
}

```

* `var items = new List<int>();` $\rightarrow$ `let mut items: Vec<i32> = Vec::new();`


* `items.Add(42);` $\rightarrow$ `items.push(42);`


* `if (items.Contains(42))` $\rightarrow$ `if items.contains(&42)`



2. **Co-Located Raw `.rs` Escape Hatch (`extern partial`):**
* Declaring `public extern static Packet Parse(ReadOnlySpan<byte> buf);` inside `Packet.rsharp` allows you to implement `impl Packet { pub fn parse(buf: &[u8]) -> Packet { ... } }` inside a sibling `Packet.rs` file in the exact same Cargo crate—sharing structs in memory with zero FFI conversion.





---

##### 1.7 Null-Safety (`T?` $\rightarrow$ `Option<T>`), Slicing, Pattern Matching, and RAII (`IDisposable` $\rightarrow$ `Drop`)

RustSharp maps modern C# (C# 8–12) expressions 1:1 into zero-cost Rust idioms:

1. **Nullable Types (`T?` $\rightarrow$ `Option<T>`):**
* `int? count = null;` $\rightarrow$ `let count: Option<i32> = None;`
* `int finalCount = count ?? 0;` $\rightarrow$ `let final_count: i32 = count.unwrap_or(0);`
* `string? city = user?.Address?.City;` $\rightarrow$ `let city: Option<String> = user.as_ref().and_then(|u| u.address.as_ref()).map(|a| a.city.clone());`


2. **Range & Span Slicing (`..` $\rightarrow$ `&[..]`):**
* `ReadOnlySpan<byte> header = buffer[0..16];` $\rightarrow$ `let header: &[u8] = &buffer[0..16];`




3. **Pattern Matching (`switch` $\rightarrow$ `match`):**
* C# `switch` expressions with type and property patterns lower directly into exhaustive Rust `match` expressions over enums and structs.




4. **Deterministic Resource Cleanup (`IDisposable` $\rightarrow$ `Drop`):**
* Implementing `IDisposable` (`public void Dispose()`) emits `impl Drop for MyResource { fn drop(&mut self) { ... } }`, giving C# developers deterministic RAII cleanup at scope exit without needing a garbage collector.



---

### Part 2: Next-Phase Targets for Covering More Ground

Once the Phase 1 core grammar and lowering rules are locked in, we can build out the complete RustSharp toolchain across **five structured phases**.

```
Phase 1: Bootstrap Compiler, Global Symbol Table & Interprocedural Borrow Pass
   │
   ▼
Phase 2: RustSharp.Core (primitive Facades) & Zero-Cost LINQ-to-Iterator Lowering
   │
   ▼
Phase 3: Cargo Ecosystem Bridge (rsharp-bindgen & Co-Located .rs Interop)
   │
   ▼
Phase 4: Rust Metaprogramming (Attributes -> Macros, Serde, Tokio Async)
   │
   ▼
Phase 5: Build Toolchain (.rsproj -> Cargo), Pre-Flight LSP, & Source Debugging

```

---

##### Phase 1: The Bootstrap Compiler & Whole-Program Ownership Analyzer

Because Rust requires accurate borrow signatures (`&self`, `&mut self`, `&T`, `&mut T`, `T`) across function boundaries, the compiler must operate as a **multi-pass whole-project analyzer**.

* **Target 1.1: Parser & Virtual Namespace Aggregator (Pass 1):**
* Scan all `.rsharp`, `.d.rsharp`, and co-located `.rs` files in a project.


* Register every namespace, `record`, `service class`, `shared class`, `interface`, and method signature into a unified Global Symbol Table, resolving circular type references across files.




* **Target 1.2: Interprocedural Mutation & Escape Analyzer (Pass 2):**
* Build a directed call graph of all methods in the project.


* Propagate mutation flags bottom-up: if Method A passes parameter `x` to Method B, and Method B mutates `x`, then both Method B and Method A have their parameter signatures inferred as `&mut T`.


* Run the **Pre-Flight Ownership Verifier** to catch illegal aliasing (such as mutating a `List<T>` while iterating over it) and emit clear, C#-oriented diagnostics pointing directly to the `.rsharp` file and line number.




* **Target 1.3: Rust AST Emitter & Cargo Module Synthesizer (Pass 3):**
* Emit formatted, idiomatic Rust code grouped by logical namespace into a synthesized Cargo workspace, complete with `Cargo.toml` and `lib.rs`/`main.rs` entry points.





---

##### Phase 2: `RustSharp.Core` & Zero-Cost LINQ-to-Iterator Lowering

C# developers rely heavily on **LINQ** (`.Where()`, `.Select()`, `.Take()`, `.Any()`, `.Sum()`, `.ToList()`). Remarkably, Rust's `std::iter::Iterator` trait is already a zero-cost, lazy pipeline that mirrors LINQ almost 1:1.

* **Target 2.1: Standard `primitive` Library (`RustSharp.Core`):**
* Define zero-cost `.d.rsharp` mappings for `List<T>` (`Vec<T>`), `Dictionary<K,V>` (`HashMap<K,V>`), `HashSet<T>` (`HashSet<T>`), `ReadOnlySpan<T>` (`&[T]`), `String` (`String`/`&str`), `Option<T>`, and `Duration`.




* **Target 2.2: LINQ-to-Iterator Compiler Pass:**
* Lower chained C# LINQ queries directly into **zero-allocation Rust iterator chains** where LLVM inlines the closures into a single tight loop:
* **RustSharp Input:**



```csharp
var highValueIds = orders
    .Where(o => o.IsActive && o.Total >= 100.0m)
    .Select(o => o.Id)
    .ToList();

```

* **Emitted Rust (Zero Intermediate Allocations, LLVM Vectorized):**

```rust
let high_value_ids: Vec<i32> = orders
    .iter()
    .filter(|o| o.is_active && o.total >= Decimal::new(1000, 1))
    .map(|o| o.id)
    .collect();

```

---

##### Phase 3: The Cargo Ecosystem Bridge (`rsharp-bindgen`)

RustSharp must allow developers to add crates like `serde`, `tokio`, `axum`, `sqlx`, or `polars` to their project and consume them with C# autocompletion and PascalCase naming.

* **Target 3.1: Automated Cargo Stub Generator (`rsharp-bindgen`):**
* Use `rustdoc --output-format json` or Rust's `syn` crate to parse the public API surface of any Cargo dependency.


* Automatically emit ambient `.d.rsharp` declaration files inside `.rsharp-stubs/`.




* **Target 3.2: Naming & Borrow Adaptation:**
* Map Rust `snake_case` functions and methods to C# `PascalCase` via `[MapsTo("snake_case")]`.


* Record whether crate parameters expect `T` (`[Moves]`), `&T` (`[Borrows]`), or `&mut T` (`[Mutates]`) in the `.d.rsharp` stub so the RustSharp compiler automatically inserts `&`, `&mut`, or `.clone()` at the boundary without developer friction.





---

##### Phase 4: Rust Metaprogramming, Attributes-to-Macros & Async Ecosystem

Modern Rust relies heavily on **derive/procedural macros** (`#[derive(Serialize, Deserialize)]`, `#[tokio::main]`, `#[tracing::instrument]`) and **async futures**.

* **Target 4.1: C# Attributes $\rightarrow$ Rust Derive & Procedural Macros:**
* Map C# attributes cleanly onto Rust `#[derive(...)]` and attribute macros:


* **RustSharp Input:**



```csharp
[JsonSerializable]
public record CreateUserRequest(
    [JsonPropertyName("user_name")] string UserName,
    int Age
);

```

* **Emitted Rust:**

```rust
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct CreateUserRequest {
    #[serde(rename = "user_name")]
    pub user_name: String,
    pub age: i32,
}

```

* **Target 4.2: Ergonomic Async/Await & Tokio Integration:**
* Lower `public async Task<User> GetUserAsync(int id)` into `pub async fn get_user_async(&self, id: i32) -> User`.
* Because `service class` instances are backed by `Arc<T>`, spawning background tasks (`Task.Run(() => _service.DoWork())`) automatically clones the `Arc` before moving it into `tokio::spawn(async move { ... })`, eliminating the notorious Rust "captured variable does not live long enough (`'static`)" error in async closures!



---

##### Phase 5: Project Tooling (`.rsproj`), Pre-Flight LSP (`rsharp-lsp`), and Native Debugging

The final phase wraps the compiler and Cargo into a cohesive developer experience.

* **Target 5.1: The `.rsproj` Build Orchestrator (`rsharp` CLI):**
* A clean project file (`Commerce.Api.rsproj`) that defines assembly boundaries (`internal` $\rightarrow$ `pub(crate)`), project references, and Cargo dependencies.


* Running `rsharp add axum` updates the underlying `Cargo.toml` and invokes `rsharp-bindgen` to generate `.rsharp-stubs/axum.d.rsharp`.


* Running `rsharp build --release` synthesizes the Cargo workspace and invokes `cargo build --release` to produce a single, static native binary.




* **Target 5.2: Language Server (`rsharp-lsp`):**
* Exposes Pass 1 & Pass 2 of the RustSharp compiler over LSP for VS Code, Cursor, and JetBrains Rider.


* Provides instant feedback on `private`/`internal` access violations, hover hints showing the inferred Rust signature (`&mut Order`), and quick-fixes for ownership conflicts before `rustc` ever runs.




* **Target 5.3: Source-Map Span Tracking & LLDB Debugging:**
* Maintain a bidirectional source map between `.rsharp` AST spans and emitted `.rs` lines so any residual `rustc` diagnostics or LLDB/GDB breakpoints map straight back to the exact `.rsharp` source file and line number.





---

##### Suggested Immediate Next Step

To begin implementing **Phase 1**, we can either:

1. **Design the Formal Grammar & AST Specification** for the core `.rsharp` subset (`namespace`, the three archetypes `record` / `service class` / `shared class`, `throws` error inference, and `primitive` declarations), or


2. **Build the Prototype Bootstrap Transpiler (in Rust or C#)** that runs the 3-pass pipeline (Global Symbol Table $\rightarrow$ Interprocedural Borrow/Mutation Inference $\rightarrow$ Idiomatic `.rs` Codegen) on a multi-file `.rsharp` sample.



Which of these two would you like to tackle first?







Design the Formal Grammar & AST Specification for the core .rsharp subset



Here is the **Formal EBNF Grammar & Multi-Pass AST Specification** for the core **RustSharp (`.rsharp` / `.d.rsharp`)** language subset.

It is specifically engineered so that **Pass 1** parses purely C#-ergonomic syntax (zero `'a` lifetimes or `&mut` clutter in user code) while providing **Pass 2 (Interprocedural Escape, Mutation & Effect Analysis)** with the exact semantic slots needed to infer Rust ownership and emit **Pass 3 (Idiomatic, Zero-Cost Rust AST)**.

---

### Part 1: Lexical Specification & Architectural Keywords

RustSharp uses standard C# lexical tokens (UTF-8 identifiers, C#-style comments `//` and `/* */`, string interpolation `$"..."`, and numeric literals with `m` for `rust_decimal::Decimal`), augmented with **seven architectural keywords** that drive the ownership, polymorphism, and interop passes:

| Keyword / Contextual Token | Architectural Purpose |
| --- | --- |
| **`service` (`service class`)** | Declares an immutable-after-construction dependency-injected service (lowers fields to `readonly` and references to `Arc<T>` or `&T`).

 |
| **`shared` (`shared class`)** | Declares an explicit multi-owner mutable graph/cache archetype (lowers fields to `Arc<RwLock<T>>` or `slotmap` keys).

 |
| **`primitive` (`primitive class`)** | Compile-time facade over a native Rust type (`Vec<T>`, `HashMap<K,V>`, `&[T]`) that erases completely during codegen.

 |
| **`extensible` (`extensible interface`)** | Marks an interface/base as open to external crates, lowering to a native `pub trait` instead of a closed-world `enum`.

 |
| **`throws` (`throws TError`)** | Checked effect clause on method signatures; triggers automatic `Result<T, TError>` return rewriting and `?` propagation.

 |
| **`extern using`** | Imports a native Cargo crate path (e.g., `extern using tokio::time as time;`).

 |
| **`extern partial`** | Binds a `.rsharp` type or method signature directly to a co-located raw `.rs` implementation file in the same crate.

 |

---

### Part 2: Formal EBNF Grammar (`.rsharp` & `.d.rsharp` Core Subset)

```ebnf
(* ========================================================================= *)
(* 1. COMPILATION UNIT, NAMESPACES & IMPORTS                                 *)
(* ========================================================================= *)

CompilationUnit     ::= NamespaceDecl? ImportDecl* TypeDecl* EOF ;

NamespaceDecl       ::= "namespace" QualifiedIdent ";" ;

ImportDecl          ::= StandardUsing | ExternUsing ;
StandardUsing       ::= "using" QualifiedIdent ";" ;
ExternUsing         ::= "extern" "using" RustCratePath ( "as" Ident )? ";" ;

QualifiedIdent      ::= Ident ( "." Ident )* ;
RustCratePath       ::= Ident ( "::" Ident )* ;


(* ========================================================================= *)
(* 2. ATTRIBUTES (C# Attributes -> Compiler Directives & Rust Macros)        *)
(* ========================================================================= *)

AttributeSection    ::= "[" Attribute ( "," Attribute )* "]" ;
Attribute           ::= QualifiedIdent ( "(" AttributeArgs? ")" )? ;
AttributeArgs       ::= AttributeArg ( "," AttributeArg )* ;
AttributeArg        ::= ( Ident "=" )? Expr ;


(* ========================================================================= *)
(* 3. TYPE ARCHETYPE DECLARATIONS                                            *)
(* ========================================================================= *)

TypeDecl            ::= AttributeSection* AccessMod? TypeModifier*
                        ( RecordDecl
                        | ClassDecl
                        | StructDecl
                        | InterfaceDecl
                        | EnumDecl ) ;

AccessMod           ::= "public" | "internal" | "protected" | "private" ;
TypeModifier        ::= "abstract" | "sealed" | "partial" | "static" ;

(* 3.1 Records: Linear Value/DTO Types -> #[derive(Clone, Debug, PartialEq)] *)
RecordDecl          ::= "record" "struct"? Ident TypeParams?
                        PrimaryCtorParams? BaseList?
                        ( ";" | "{" MemberDecl* "}" ) ;

PrimaryCtorParams   ::= "(" ( Param ( "," Param )* )? ")" ;

(* 3.2 Classes: Standard, Service (DI), Shared (Mutable Graph), or Primitive *)
ClassDecl           ::= ClassArchetype? "class" Ident TypeParams?
                        BaseList? TypeConstraint*
                        "{" MemberDecl* "}" ;

ClassArchetype      ::= "service" | "shared" | "primitive" ;

(* 3.3 Structs: Stack-Allocated Value Types *)
StructDecl          ::= "struct" Ident TypeParams? BaseList?
                        "{" MemberDecl* "}" ;

(* 3.4 Interfaces: Closed-World Enum Dispatch vs. Open 'extensible' Trait    *)
InterfaceDecl       ::= "extensible"? "interface" Ident TypeParams?
                        BaseList? "{" InterfaceMember* "}" ;

(* 3.5 Enums: C-like & Algebraic Discriminated Unions                        *)
EnumDecl            ::= "enum" Ident "{" EnumVariant ( "," EnumVariant )* ","? "}" ;
EnumVariant         ::= AttributeSection* Ident
                        ( "(" Param ( "," Param )* ")" | "=" Literal )? ;

BaseList            ::= ":" TypeRef ( "," TypeRef )* ;
TypeParams          ::= "<" Ident ( "," Ident )* ">" ;
TypeConstraint      ::= "where" Ident ":" TypeRef ( "," TypeRef )* ;


(* ========================================================================= *)
(* 4. CLASS / RECORD / PRIMITIVE MEMBERS                                     *)
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

IndexerDecl         ::= TypeRef "this" "[" Param ( "," Param )* "]"
                        "{" AccessorDecl+ "}" ;

ConstructorDecl     ::= Ident "(" ParamList? ")" CtorChain?
                        ( Block | "=>" Expr ";" ) ;
CtorChain           ::= ":" "base" "(" ArgList? ")" ;

MethodDecl          ::= TypeRef Ident TypeParams? "(" ParamList? ")"
                        ThrowsClause? TypeConstraint*
                        ( Block | "=>" Expr ";" | ";" ) ;

ThrowsClause        ::= "throws" TypeRef ;

InterfaceMember     ::= AttributeSection* TypeRef Ident TypeParams?
                        "(" ParamList? ")" ThrowsClause? ";" ;

ParamList           ::= Param ( "," Param )* ;
Param               ::= AttributeSection* ParamMod? TypeRef Ident ( "=" Expr )? ;
ParamMod            ::= "params" ;


(* ========================================================================= *)
(* 5. TYPE REFERENCES (Built-ins, Nullables, Spans, Generics)                *)
(* ========================================================================= *)

TypeRef             ::= NonNullType "?"? ;         (* T? -> Option<T> *)
NonNullType         ::= PrimitiveType
                      | "ReadOnlySpan" "<" TypeRef ">"  (* -> &[T] *)
                      | "Span" "<" TypeRef ">"          (* -> &mut [T] *)
                      | QualifiedIdent TypeArgs? ;

PrimitiveType       ::= "void" | "bool" | "byte" | "sbyte"
                      | "short" | "ushort" | "int" | "uint"
                      | "long" | "ulong" | "float" | "double"
                      | "decimal" | "char" | "string" ;

TypeArgs            ::= "<" TypeRef ( "," TypeRef )* ">" ;


(* ========================================================================= *)
(* 6. STATEMENTS & CONTROL FLOW                                              *)
(* ========================================================================= *)

Block               ::= "{" Stmt* "}" ;

Stmt                ::= Block
                      | LocalVarStmt
                      | UsingResourceStmt
                      | IfStmt
                      | WhileStmt
                      | ForEachStmt
                      | ReturnStmt
                      | ThrowStmt
                      | TryCatchStmt
                      | ExprStmt ;

LocalVarStmt        ::= ( "var" | TypeRef ) Ident "=" Expr ";" ;
UsingResourceStmt   ::= "using" ( "var" | TypeRef ) Ident "=" Expr ";" ;
IfStmt              ::= "if" "(" Expr ")" Stmt ( "else" Stmt )? ;
WhileStmt           ::= "while" "(" Expr ")" Stmt ;
ForEachStmt         ::= "foreach" "(" ( "var" | TypeRef ) Ident "in" Expr ")" Stmt ;
ReturnStmt          ::= "return" Expr? ";" ;
ThrowStmt           ::= "throw" Expr ";" ;

TryCatchStmt        ::= "try" Block CatchClause+ ;
CatchClause         ::= "catch" "(" TypeRef Ident? ")" Block ;

ExprStmt            ::= Expr ";" ;


(* ========================================================================= *)
(* 7. EXPRESSIONS, SLICING, NULL-COALESCING, LINQ LAMBDAS & SWITCH           *)
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
RelationalExpr      ::= RangeExpr ( ( "<" | ">" | "<=" | ">=" ) RangeExpr
                                  | "is" Pattern )? ;

RangeExpr           ::= AdditiveExpr ( ".." AdditiveExpr? )? ;
AdditiveExpr        ::= MultiplicativeExpr ( ( "+" | "-" ) MultiplicativeExpr )* ;
MultiplicativeExpr  ::= UnaryExpr ( ( "*" | "/" | "%" ) UnaryExpr )* ;

UnaryExpr           ::= ( "!" | "-" | "await" | "^" ) UnaryExpr
                      | PostfixExpr ;

PostfixExpr         ::= PrimaryExpr PostfixOp* ;
PostfixOp           ::= "." Ident TypeArgs? ( "(" ArgList? ")" )?
                      | "?." Ident ( "(" ArgList? ")" )?
                      | "[" ArgList "]" ;

PrimaryExpr         ::= Literal
                      | InterpolatedString
                      | Ident
                      | "this"
                      | "base"
                      | "new" TypeRef "(" ArgList? ")"
                      | "(" Expr ")" ;

ArgList             ::= Arg ( "," Arg )* ;
Arg                 ::= ( Ident ":" )? Expr ;

LambdaExpr          ::= ( Ident | "(" ( Ident ( "," Ident )* )? ")" )
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

### Part 3: The Multi-Pass AST & Semantic Slot Specification

Because RustSharp infers borrowing (`&T`, `&mut T`, `T`), local mutability (`let` vs. `let mut`), polymorphic representation (`enum` vs. `trait`), and error propagation (`Result<T, E>` + `?`) across the whole codebase, **every AST node carries two layers of data**:

1. **Syntactic Fields (Populated in Pass 1):** What the developer wrote in `.rsharp` plus exact `SourceSpan` locations for `.rsharp` LSP diagnostics and source mapping.


2. **Semantic Inference Slots (`resolved_*` / `inferred_*`, Populated in Pass 2):** Computed by the Interprocedural Escape, Mutation, and Effect Analyzer before Pass 3 emits Rust.



Below is the concrete AST data schema (written in Rust, the natural host language for the `rsharpc` compiler):

```rust
// ============================================================================
// 1. SOURCE TRACKING & COMPILER METADATA
// ============================================================================

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceSpan {
    pub file_id: usize,
    pub start_line: u32,
    pub start_col: u32,
    pub end_line: u32,
    pub end_col: u32,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct SymbolId(pub u32);

// ============================================================================
// 2. PASS 2 INFERRED SEMANTIC SLOTS (THE "SECRET SAUCE" OF RUSTSHARP)
// ============================================================================

/// Inferred by Pass 2 Escape & Mutation Analysis for every parameter & receiver
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BorrowMode {
    Unresolved,         // Initial state during Pass 1
    ReadBorrow,         // Emits `&T` or `&self` ( string -> `&str`, List<T> -> `&[T]` )
    MutBorrow,          // Emits `&mut T` or `&mut self` (injects `mut` at caller!)
    OwnedMove,          // Emits `T` (consumed into field, collection, or return)
    SharedArc,          // Emits `Arc<T>` (used for `service class` dependencies)
    CopyValue,          // Emits `T` by value (for i32, bool, f64, Decimal, Copy structs)
}

/// Inferred by Pass 2 Hierarchy Analysis for abstract classes & interfaces
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PolymorphismStrategy {
    Unresolved,
    MonomorphicStruct,                           // Standard struct, no subclasses
    FlattenedSubStruct { base_type: SymbolId },  // Embeds `pub base: BaseStruct` + Deref
    ClosedWorldEnum { variants: Vec<SymbolId> }, // Lowers hierarchy to `pub enum Base`
    OpenTrait,                                   // Marked `extensible` -> `pub trait`
}

/// Inferred by Pass 2 Checked Effect Analysis (`throws` & `try/catch` call graph)
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum EffectSignature {
    Unresolved,
    Infallible,                         // Returns `T` directly
    Fallible { error_type: ResolvedType }, // Rewrites return to `Result<T, E>`
}

/// Parsed from `[MapsTo("...")]` and `[InlineTemplate("...")]` on `primitive` types
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PrimitiveLowering {
    None,
    DirectSymbol { rust_path: String },      // e.g., List<T>.Add -> `push`
    InlineTemplate { template: String },     // e.g., `{self}.contains(&{0})`
    OperatorIndex,                           // e.g., `this[i]` -> `{self}[{0}]`
}

// ============================================================================
// 3. TOP-LEVEL DECLARATIONS & TYPE ARCHETYPES
// ============================================================================

#[derive(Clone, Debug)]
pub struct CompilationUnit {
    pub file_id: usize,
    pub is_ambient_stub: bool, // true if `.d.rsharp`
    pub namespace: Option<Vec<String>>,
    pub imports: Vec<ImportDecl>,
    pub types: Vec<TypeDecl>,
}

#[derive(Clone, Debug)]
pub enum TypeKind {
    Record { is_struct: bool }, // Linear value/DTO -> #[derive(Clone, Debug, PartialEq)]
    StandardClass,              // Scoped entity/state
    ServiceClass,               // DI Singleton -> fields enforced readonly, wrapped in Arc<T>
    SharedClass,                // Multi-owner mutable -> fields wrapped in Arc<RwLock<T>>
    PrimitiveClass,             // Compile-time facade -> erased at Pass 3 codegen
    ValueStruct,                // Stack struct -> #[derive(Clone, Copy, Debug)]
    Interface { is_extensible: bool },
    Enum,
}

#[derive(Clone, Debug)]
pub struct TypeDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub kind: TypeKind,
    pub is_partial: bool,
    pub name: String,
    pub type_params: Vec<String>,
    pub base_types: Vec<TypeRef>,
    pub members: Vec<MemberDecl>,

    // --- Pass 2 Semantic Slots ---
    pub inferred_polymorphism: PolymorphismStrategy,
    pub primitive_rust_target: Option<String>, // e.g., Some("std::vec::Vec")
    pub has_disposable_drop: bool,             // True if implements IDisposable -> emits `impl Drop`
}

// ============================================================================
// 4. MEMBERS: FIELDS, PROPERTIES, AND METHODS WITH BORROW SLOTS
// ============================================================================

#[derive(Clone, Debug)]
pub enum MemberDecl {
    Field(FieldDecl),
    Property(PropertyDecl),
    Method(MethodDecl),
    Constructor(ConstructorDecl),
}

#[derive(Clone, Debug)]
pub struct FieldDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub access: AccessMod,
    pub is_readonly: bool,
    pub name: String,
    pub ty: TypeRef,
    pub initializer: Option<Expr>,

    // --- Pass 2 Semantic Slots ---
    pub resolved_storage: FieldStorageMode, // Plain, ArcService, or RwLockShared
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FieldStorageMode {
    Plain,          // `field: T`
    ArcShared,      // `field: std::sync::Arc<T>` (auto-selected for `service class` fields)
    RwLockShared,   // `field: std::sync::Arc<std::sync::RwLock<T>>` (in `shared class`)
}

#[derive(Clone, Debug)]
pub struct MethodDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub attributes: Vec<AttributeNode>,
    pub access: AccessMod,
    pub is_static: bool,
    pub is_async: bool,
    pub is_extern: bool, // True for `primitive` methods or co-located `.rs` methods
    pub is_virtual_or_override: bool,
    pub name: String,
    pub type_params: Vec<String>,
    pub params: Vec<ParamDecl>,
    pub return_type: TypeRef,
    pub explicit_throws: Option<TypeRef>,
    pub body: Option<Block>,

    // --- Pass 2 Semantic Slots ---
    pub inferred_self_borrow: BorrowMode,        // &self, &mut self, or static
    pub inferred_effect: EffectSignature,        // Infallible vs. Fallible(Result<T, E>)
    pub disambiguated_rust_name: String,         // Handles static overload resolution!
    pub primitive_lowering: PrimitiveLowering,   // Non-none if declared on a `primitive class`
}

#[derive(Clone, Debug)]
pub struct ParamDecl {
    pub id: SymbolId,
    pub span: SourceSpan,
    pub name: String,
    pub ty: TypeRef,
    pub default_value: Option<Expr>,
    pub explicit_constraint: Option<BorrowMode>, // From `[Moves]`, `[Borrows]`, `[Mutates]` in .d.rsharp

    // --- Pass 2 Semantic Slots ---
    pub inferred_borrow: BorrowMode,             // Computed by Pass 2 if explicit_constraint is None
}

// ============================================================================
// 5. STATEMENTS & EXPRESSIONS WITH CALL-SITE COERCION SLOTS
// ============================================================================

#[derive(Clone, Debug)]
pub enum Stmt {
    LocalVar {
        span: SourceSpan,
        symbol_id: SymbolId,
        name: String,
        explicit_type: Option<TypeRef>,
        init: Expr,
        // --- Pass 2 Slot ---
        inferred_mut: bool,       // Emits `let mut` if mutated locally OR passed to a `&mut` param!
        inferred_type: Option<ResolvedType>,
    },
    UsingResource {
        span: SourceSpan,
        symbol_id: SymbolId,
        name: String,
        init: Expr,               // Lowers to standard variable whose type implements `Drop`
    },
    ExprStmt(Expr),
    Return(SourceSpan, Option<Expr>), // Automatically wrapped in `Ok(...)` if method is Fallible
    Throw(SourceSpan, Expr),          // Lowers to `return Err(...)`
    If {
        span: SourceSpan,
        cond: Expr,
        then_branch: Box<Stmt>,
        else_branch: Option<Box<Stmt>>,
    },
    ForEach {
        span: SourceSpan,
        item_symbol: SymbolId,
        item_name: String,
        collection: Expr,
        body: Box<Stmt>,
        // --- Pass 2 Slot ---
        iter_borrow_mode: BorrowMode, // `.iter()`, `.iter_mut()`, or `.into_iter()`
    },
    TryCatch {
        span: SourceSpan,
        try_block: Block,
        catches: Vec<CatchArm>,       // Lowers to `match (() -> Result<_, E> { ... })()`
    },
}

#[derive(Clone, Debug)]
pub struct Expr {
    pub span: SourceSpan,
    pub kind: ExprKind,

    // --- Pass 2 Semantic Slots ---
    pub resolved_type: Option<ResolvedType>,
    pub append_try_question_mark: bool, // True if calling a `Fallible` method outside `try`
    pub caller_coercion: CallerArgCoercion, // Injects `&`, `&mut`, `.as_str()`, or `.clone()`
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CallerArgCoercion {
    None,
    BorrowShared,       // Prepends `&` (or `.as_ref()`)
    BorrowMutable,      // Prepends `&mut`
    CloneOwned,         // Appends `.clone()` when value is used again later in scope
    ArcClone,           // Emits `Arc::clone(&x)` for service dependencies
}

#[derive(Clone, Debug)]
pub enum ExprKind {
    Literal(LiteralValue),
    Identifier { name: String, resolved_symbol: Option<SymbolId> },
    Binary { op: BinaryOp, left: Box<Expr>, right: Box<Expr> },
    NullCoalesce { left: Box<Expr>, right: Box<Expr> }, // `a ?? b` -> `a.unwrap_or_else(|| b)`
    NullConditionalField { target: Box<Expr>, field: String }, // `a?.B` -> `a.as_ref().map(|x| &x.b)`
    RangeSlice { target: Box<Expr>, start: Option<Box<Expr>>, end: Option<Box<Expr>> }, // `buf[0..16]` -> `&buf[0..16]`
    MethodCall {
        receiver: Option<Box<Expr>>,
        method_name: String,
        type_args: Vec<TypeRef>,
        args: Vec<Expr>,
        // --- Pass 2 Slot ---
        resolved_overload: Option<SymbolId>, // Points to exact MethodDecl after overload resolution
    },
    LinqChain {
        source: Box<Expr>,
        ops: Vec<LinqOp>,          // `.Where(...)`, `.Select(...)` -> fused `.iter().filter().map()`
        terminal: LinqTerminal,    // `.ToList()` -> `.collect::<Vec<_>>()`, `.Any()` -> `.any()`
    },
    Construct {
        ty: TypeRef,
        args: Vec<Expr>,
        resolved_ctor: Option<SymbolId>,
    },
    Switch {
        scrutinee: Box<Expr>,
        arms: Vec<SwitchArmNode>,
    },
}

```

---

### Part 4: Concrete End-to-End AST Lowering Trace

To see how the EBNF grammar and Pass 2 AST semantic slots work together, let’s trace a single `.rsharp` snippet through **Pass 1 (Parse)** $\rightarrow$ **Pass 2 (Inference)** $\rightarrow$ **Pass 3 (Emit)**.

#### 1. Input Source (`OrderHandler.rsharp`)

```csharp
namespace Commerce.Checkout;

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

```

#### 2. How Pass 2 Populates the AST Semantic Slots

1. **Archetype & Field Storage Resolution:**
* `OrderHandler` has `TypeKind::ServiceClass`.


* Its field `_tax: TaxCalculator` has `resolved_storage = FieldStorageMode::ArcShared` (`Arc<TaxCalculator>`) and is enforced as immutable after construction.




2. **Bottom-Up Mutation & Borrow Propagation:**
* Inspecting `ApplyCoupon`:
* `this` is unused $\rightarrow$ `inferred_self_borrow = BorrowMode::ReadBorrow` (`&self`).


* `order.Total -= 10.0m` mutates a field of `order` $\rightarrow$ `param[0].inferred_borrow = BorrowMode::MutBorrow` (`&mut Order`).


* `code == "SAVE10"` only reads `code` $\rightarrow$ `param[1].inferred_borrow = BorrowMode::ReadBorrow` (`&str`).




* Propagating up to `Checkout`:
* Because `Checkout` passes `order` to `ApplyCoupon` (which requires `MutBorrow`), `Checkout`'s `order` parameter is **automatically upgraded** to `BorrowMode::MutBorrow` (`&mut Order`)!


* At the call site `ApplyCoupon(order, coupon)` inside `Checkout`, Pass 2 sets `caller_coercion = CallerArgCoercion::BorrowMutable` on `order` (`&mut *order`) and `BorrowShared` on `coupon` (`coupon`).


* At the subsequent call `_tax.RecordAudit(order)`, Pass 2 sees `RecordAudit` only reads `order`, so it re-borrows `&*order` safely after the mutable borrow in `ApplyCoupon` ends (leveraging Rust's Non-Lexical Lifetimes).






3. **Checked Effect Inference (`throws`):**
* `Checkout` declares `throws ValidationError` $\rightarrow$ `inferred_effect = EffectSignature::Fallible { error_type: ValidationError }`.


* Its return type `void` is rewritten to `Result<(), ValidationError>`, the `throw new ValidationError(...)` statement lowers to `return Err(ValidationError { ... })`, and an implicit `Ok(())` is appended to the end of the block.





#### 3. Pass 3 Emitted Rust AST (`src/commerce/checkout.rs`)

```rust
// Auto-generated by rsharpc — DO NOT EDIT
use std::sync::Arc;
use rust_decimal::Decimal;

#[derive(Clone, Debug, PartialEq)]
pub struct Order {
    pub id: i32,
    pub total: Decimal,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ValidationError {
    pub reason: String,
}

pub struct OrderHandler {
    tax: Arc<TaxCalculator>,
}

impl OrderHandler {
    pub fn new(tax: Arc<TaxCalculator>) -> Self {
        Self { tax }
    }

    pub fn checkout(&self, order: &mut Order, coupon: &str) -> Result<(), ValidationError> {
        if order.total <= Decimal::new(0, 1) {
            return Err(ValidationError {
                reason: "Order total must be positive".to_string(),
            });
        }
        self.apply_coupon(order, coupon);
        self.tax.record_audit(&*order);
        Ok(())
    }

    fn apply_coupon(&self, order: &mut Order, code: &str) {
        if code == "SAVE10" {
            order.total -= Decimal::new(100, 1);
        }
    }
}

```

---

### Part 5: Pre-Flight Ownership Diagnostic Rules (Pass 2.5 Verifier)

To uphold **Bottleneck 3's circumvention guarantee** (*`rustc` borrow errors never leak to the user*), Pass 2.5 runs three deterministic checks over the decorated AST before emitting `.rs` code:

| Rule ID | Condition Detected in `.rsharp` AST | Diagnostic Emitted on `.rsharp` Source Span |
| --- | --- | --- |
| **`RSHARP001`** *(Service State Mutation)* | A method inside a `service class` attempts to assign to `this.Field` or call a `MutBorrow` method on a field outside the constructor.

 | `Error [RSHARP001]: Cannot mutate field '_cache' inside service class 'UserService'. Wrap mutable state in a 'shared class' or pass state via method parameters.`

 |
| **`RSHARP002`** *(Concurrent Collection Aliasing)* | Inside a `foreach (var x in list)` loop, the loop body invokes a method on `list` with `inferred_self_borrow == MutBorrow` (e.g., `list.Add(...)` or `list.Remove(...)`).

 | `Error [RSHARP002]: Cannot mutate collection 'list' while iterating over it at OrderService.rsharp:42. Quick-fix: iterate over a snapshot with 'list.ToList()' or collect removals separately.`

 |
| **`RSHARP003`** *(Use-After-Move on Linear Resource)* | A variable whose type does not implement `Clone` (such as an `IDisposable` file/socket handle) is passed to two `[Moves]` parameters sequentially.

 | `Error [RSHARP003]: Resource 'socket' was consumed by 'Channel.TakeOwnership(socket)' at line 19 and cannot be used again at line 21.`

 |

---

### Suggested Next Step

With the **Formal EBNF Grammar and Multi-Pass AST Schema** defined, we are ready to write the **Phase 1 Bootstrap Transpiler Prototype** (`rsharpc`).

Would you like to:

1. **Build the executable prototype of the 3-Pass Compiler** (in Rust or Python) that parses `.rsharp` files, runs the bottom-up **Interprocedural Borrow & Effect Inference Pass**, and outputs a ready-to-compile Cargo project (`Cargo.toml` + `src/lib.rs` + module files), or


2. **Write the formal `RustSharp.Core.d.rsharp` Standard Library Specification** (`List<T>`, `Dictionary<K,V>`, `ReadOnlySpan<T>`, `Option<T>`, and the LINQ-to-Iterator rewrite rules)?









Write the formal RustSharp.Core.d.rsharp Standard Library Specification




Here is the **Formal `RustSharp.Core.d.rsharp` Standard Library Specification**.

In the RustSharp architecture, `RustSharp.Core.d.rsharp` is the **ambient compile-time standard library**. None of the `primitive` classes declared in this file exist at runtime—instead, they give developers familiar, self-documenting C# APIs (`List<T>`, `Dictionary<K,V>`, `ReadOnlySpan<T>`, `String`, `IDisposable`, and LINQ) while instructing **Pass 2 (Borrow & Effect Inference)** and **Pass 3 (Rust AST Emitter)** how to lower every call into zero-cost, idiomatic Rust (`Vec<T>`, `HashMap<K,V>`, `&[T]`, `String`/`&str`, `Drop`, and fused `std::iter::Iterator` pipelines).

---

### Part 1: Compiler Directive Attributes (`RustSharp.Runtime.CompilerServices`)

Before declaring the core types, `RustSharp.Core.d.rsharp` defines the intrinsic attributes that control **type erasure**, **Pass 2 borrow inference**, and **inline AST templates**.

| Attribute | Target | Pass 2 / Pass 3 Compiler Behavior |
| --- | --- | --- |
| **`[MapsTo("rust::path")]`** | `primitive class`, `struct`, `method`, `property` | Erases the RustSharp identifier and emits the exact target Rust type or method call.

 |
| **`[ParamType("rust::slice")]`** | `primitive class` | Specifies a distinct Rust borrow representation when used as a `ReadBorrow` parameter (e.g., owned `String` $\rightarrow$ borrowed `&str`, or `Vec<T>` $\rightarrow$ `&[T]`).

 |
| **`[InlineTemplate("...")]`** | `method`, `property`, `indexer` | Substitutes `{self}`, `{0}`, `{1}`, and `{T}` directly into a Rust AST expression (zero function wrapper overhead).

 |
| **`[Borrows]`** | `method`, `parameter` | Forces Pass 2 to infer `BorrowMode::ReadBorrow` (`&self` or `&T`).

 |
| **`[Mutates]`** | `method`, `parameter` | Forces Pass 2 to infer `BorrowMode::MutBorrow` (`&mut self` or `&mut T`) and injects `let mut` at the caller site.

 |
| **`[Moves]`** | `method`, `parameter` | Forces Pass 2 to infer `BorrowMode::OwnedMove` (consumes `self` or `T` by value, triggering `RSHARP003` if used again without cloning).

 |
| **`[LinqStage("...")]`** | `method` | Marks a method on `IEnumerable<T>` as part of a lazy LINQ pipeline to be fused into a native Rust `.iter()` chain.

 |

---

### Part 2: Complete `RustSharp.Core.d.rsharp` Ambient Specification

```csharp
// ============================================================================
// FILE: RustSharp.Core.d.rsharp
// Ambient Standard Library — Zero Runtime Overhead, 100% Compile-Time Erasure
// ============================================================================

namespace RustSharp.Core;

extern using std::vec::Vec;
extern using std::collections::HashMap;
extern using std::collections::HashSet as RustHashSet;
extern using std::time::Duration as RustDuration;
extern using rust_decimal::Decimal as RustDecimal;

// ----------------------------------------------------------------------------
// 1. COMPILER INTRINSIC ATTRIBUTES
// ----------------------------------------------------------------------------

public sealed class MapsToAttribute : Attribute
{
    public MapsToAttribute(string rustTarget) { }
}

public sealed class ParamTypeAttribute : Attribute
{
    public ParamTypeAttribute(string borrowedRustType) { }
}

public sealed class InlineTemplateAttribute : Attribute
{
    public InlineTemplateAttribute(string rustTemplate) { }
}

public sealed class BorrowsAttribute : Attribute { }
public sealed class MutatesAttribute : Attribute { }
public sealed class MovesAttribute : Attribute { }
public sealed class LinqStageAttribute : Attribute
{
    public LinqStageAttribute(string stageKind) { }
}

// ----------------------------------------------------------------------------
// 2. CORE TRAIT CONTRACTS & DETERMINISTIC RAII (IDisposable -> Drop)
// ----------------------------------------------------------------------------

/// Implementing IDisposable on any RustSharp type emits `impl std::ops::Drop`
/// and maps `Dispose()` to `fn drop(&mut self)`.
[MapsTo("std::ops::Drop")]
public extensible interface IDisposable
{
    [Mutates]
    [MapsTo("drop")]
    void Dispose();
}

[MapsTo("std::cmp::PartialEq")]
public extensible interface IEquatable<T>
{
    [Borrows]
    [MapsTo("eq")]
    bool Equals([Borrows] T other);
}

[MapsTo("std::cmp::Ord")]
public extensible interface IComparable<T>
{
    [Borrows]
    [InlineTemplate("{self}.cmp(&{0})")]
    int CompareTo([Borrows] T other);
}

// ----------------------------------------------------------------------------
// 3. STRINGS & SLICES (string -> String / &str, ReadOnlySpan<T> -> &[T])
// ----------------------------------------------------------------------------

[MapsTo("std::string::String")]
[ParamType("&str")]
public primitive class String
{
    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Length { get; }

    [Borrows]
    [MapsTo("is_empty")]
    public extern bool IsEmpty { get; }

    [Borrows]
    [InlineTemplate("{self}.contains({0})")]
    public extern bool Contains([Borrows] string value);

    [Borrows]
    [InlineTemplate("{self}.starts_with({0})")]
    public extern bool StartsWith([Borrows] string prefix);

    [Borrows]
    [InlineTemplate("{self}.ends_with({0})")]
    public extern bool EndsWith([Borrows] string suffix);

    [Borrows]
    [MapsTo("to_lowercase")]
    public extern string ToLower();

    [Borrows]
    [MapsTo("to_uppercase")]
    public extern string ToUpper();

    [Borrows]
    [InlineTemplate("{self}.trim().to_string()")]
    public extern string Trim();

    [Borrows]
    [InlineTemplate("{self}.as_bytes()")]
    public extern ReadOnlySpan<byte> AsBytes();

    [Borrows]
    [InlineTemplate("{self}.split({0}).map(|s| s.to_string()).collect::<Vec<String>>()")]
    public extern List<string> Split([Borrows] string delimiter);
}

/// Zero-copy read-only view over contiguous memory. Erases to `&[T]`.
[MapsTo("&[{T}]")]
public primitive struct ReadOnlySpan<T>
{
    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Length { get; }

    [Borrows]
    [MapsTo("is_empty")]
    public extern bool IsEmpty { get; }

    [Borrows]
    [InlineTemplate("{self}[{0} as usize]")]
    public extern T this[int index] { get; }

    [Borrows]
    [InlineTemplate("&{self}[({0} as usize)..({1} as usize)]")]
    public extern ReadOnlySpan<T> Slice(int start, int length);
}

/// Zero-copy mutable view over contiguous memory. Erases to `&mut [T]`.
[MapsTo("&mut [{T}]")]
public primitive struct Span<T>
{
    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Length { get; }

    [Mutates]
    [InlineTemplate("{self}[{0} as usize]")]
    public extern T this[int index] { get; set; }

    [Mutates]
    [MapsTo("fill")]
    public extern void Fill(T value);
}

// ----------------------------------------------------------------------------
// 4. COLLECTIONS: List<T> (-> Vec<T>), Dictionary<K,V>, HashSet<T>
// ----------------------------------------------------------------------------

[MapsTo("std::vec::Vec")]
[ParamType("&[{T}]")]
public primitive class List<T> : IEnumerable<T>
{
    [InlineTemplate("Vec::new()")]
    public extern List();

    [InlineTemplate("Vec::with_capacity({0} as usize)")]
    public extern List(int capacity);

    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Count { get; }

    [Borrows]
    [MapsTo("is_empty")]
    public extern bool IsEmpty { get; }

    [Mutates]
    [MapsTo("push")]
    public extern void Add([Moves] T item);

    [Mutates]
    [InlineTemplate("{self}.extend({0})")]
    public extern void AddRange([Moves] IEnumerable<T> items);

    [Mutates]
    [InlineTemplate("{self}.insert({0} as usize, {1})")]
    public extern void Insert(int index, [Moves] T item);

    [Mutates]
    [InlineTemplate("{self}.remove({0} as usize)")]
    public extern T RemoveAt(int index);

    [Mutates]
    [MapsTo("pop")]
    public extern T? Pop();

    [Mutates]
    [MapsTo("clear")]
    public extern void Clear();

    [Borrows]
    [InlineTemplate("{self}.contains(&{0})")]
    public extern bool Contains([Borrows] T item);

    [Borrows]
    [InlineTemplate("{self}.as_slice()")]
    public extern ReadOnlySpan<T> AsSpan();

    [Mutates]
    [InlineTemplate("{self}.as_mut_slice()")]
    public extern Span<T> AsMutSpan();

    [Mutates]
    [MapsTo("sort")]
    public extern void Sort();

    [Borrows]
    [InlineTemplate("{self}[{0} as usize]")]
    public extern T this[int index] { [Borrows] get; [Mutates] set; }
}

[MapsTo("std::collections::HashMap")]
public primitive class Dictionary<TKey, TValue> : IEnumerable<KeyValuePair<TKey, TValue>>
{
    [InlineTemplate("std::collections::HashMap::new()")]
    public extern Dictionary();

    [InlineTemplate("std::collections::HashMap::with_capacity({0} as usize)")]
    public extern Dictionary(int capacity);

    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Count { get; }

    [Borrows]
    [MapsTo("is_empty")]
    public extern bool IsEmpty { get; }

    [Mutates]
    [InlineTemplate("{self}.insert({0}, {1})")]
    public extern void Add([Moves] TKey key, [Moves] TValue value);

    [Borrows]
    [InlineTemplate("{self}.get(&{0}).cloned()")]
    public extern TValue? GetOrDefault([Borrows] TKey key);

    [Borrows]
    [InlineTemplate("{self}.contains_key(&{0})")]
    public extern bool ContainsKey([Borrows] TKey key);

    [Mutates]
    [InlineTemplate("{self}.remove(&{0}).is_some()")]
    public extern bool Remove([Borrows] TKey key);

    [Mutates]
    [MapsTo("clear")]
    public extern void Clear();

    [InlineTemplate("{self}[&{0}]")]
    public extern TValue this[[Borrows] TKey key]
    {
        [Borrows] get;
        [Mutates] [InlineTemplate("{self}.insert({0}, {value})")] set;
    }
}

[MapsTo("std::collections::HashSet")]
public primitive class HashSet<T> : IEnumerable<T>
{
    [InlineTemplate("std::collections::HashSet::new()")]
    public extern HashSet();

    [Borrows]
    [InlineTemplate("{self}.len() as i32")]
    public extern int Count { get; }

    [Mutates]
    [MapsTo("insert")]
    public extern bool Add([Moves] T item);

    [Borrows]
    [InlineTemplate("{self}.contains(&{0})")]
    public extern bool Contains([Borrows] T item);

    [Mutates]
    [InlineTemplate("{self}.remove(&{0})")]
    public extern bool Remove([Borrows] T item);
}

[MapsTo("({TKey}, {TValue})")]
public primitive struct KeyValuePair<TKey, TValue>
{
    [InlineTemplate("{self}.0")]
    public extern TKey Key { get; }

    [InlineTemplate("{self}.1")]
    public extern TValue Value { get; }
}

// ----------------------------------------------------------------------------
// 5. OPTION, RESULT, AND CONCURRENCY PRIMITIVES
// ----------------------------------------------------------------------------

/// Underlying representation of `T?` nullable types in RustSharp.
[MapsTo("std::option::Option")]
public primitive struct Option<T>
{
    [Borrows]
    [MapsTo("is_some")]
    public extern bool HasValue { get; }

    [Borrows]
    [MapsTo("is_none")]
    public extern bool IsNull { get; }

    [Moves]
    [MapsTo("unwrap")]
    public extern T Value();

    [Moves]
    [MapsTo("unwrap_or")]
    public extern T GetValueOrDefault([Moves] T defaultValue);
}

/// Explicit thread-safe interior mutability primitive for `shared class` fields.
[MapsTo("std::sync::Arc<std::sync::RwLock<{T}>>")]
public primitive class SharedState<T>
{
    [InlineTemplate("std::sync::Arc::new(std::sync::RwLock::new({0}))")]
    public extern SharedState([Moves] T initialValue);

    [Borrows]
    [InlineTemplate("{self}.read().unwrap()")]
    public extern T Read();

    [Borrows]
    [InlineTemplate("{self}.write().unwrap()")]
    public extern T Write();
}

// ----------------------------------------------------------------------------
// 6. ZERO-COST LINQ PIPELINE DECLARATIONS (IEnumerable<T> -> Iterator)
// ----------------------------------------------------------------------------

/// Compile-time sequence contract. Lowers to fused `std::iter::Iterator` chains.
[MapsTo("impl std::iter::Iterator<Item = {T}>")]
public primitive interface IEnumerable<T>
{
    // --- Intermediate Lazy Adaptors (Zero Allocation) ---

    [LinqStage("Filter")]
    [InlineTemplate("{self}.filter({0})")]
    IEnumerable<T> Where(Func<T, bool> predicate);

    [LinqStage("Map")]
    [InlineTemplate("{self}.map({0})")]
    IEnumerable<TResult> Select<TResult>(Func<T, TResult> selector);

    [LinqStage("FlatMap")]
    [InlineTemplate("{self}.flat_map({0})")]
    IEnumerable<TResult> SelectMany<TResult>(Func<T, IEnumerable<TResult>> selector);

    [LinqStage("Take")]
    [InlineTemplate("{self}.take({0} as usize)")]
    IEnumerable<T> Take(int count);

    [LinqStage("Skip")]
    [InlineTemplate("{self}.skip({0} as usize)")]
    IEnumerable<T> Skip(int count);

    [LinqStage("Enumerate")]
    [InlineTemplate("{self}.enumerate()")]
    IEnumerable<KeyValuePair<int, T>> WithIndex();

    // --- Terminal Consumers (Single-Pass Evaluation) ---

    [LinqStage("TerminalCollectVec")]
    [InlineTemplate("{self}.collect::<Vec<_>>()")]
    List<T> ToList();

    [LinqStage("TerminalCollectSet")]
    [InlineTemplate("{self}.collect::<std::collections::HashSet<_>>()")]
    HashSet<T> ToHashSet();

    [LinqStage("TerminalAny")]
    [InlineTemplate("{self}.any({0})")]
    bool Any(Func<T, bool> predicate);

    [LinqStage("TerminalAll")]
    [InlineTemplate("{self}.all({0})")]
    bool All(Func<T, bool> predicate);

    [LinqStage("TerminalFirstOrDefault")]
    [InlineTemplate("{self}.next()")]
    T? FirstOrDefault();

    [LinqStage("TerminalFind")]
    [InlineTemplate("{self}.find({0})")]
    T? FirstOrDefault(Func<T, bool> predicate);

    [LinqStage("TerminalCount")]
    [InlineTemplate("{self}.count() as i32")]
    int Count();

    [LinqStage("TerminalSum")]
    [InlineTemplate("{self}.sum()")]
    T Sum();
}

// ----------------------------------------------------------------------------
// 7. SYSTEM CONSOLE, MATH & TIME FACADES
// ----------------------------------------------------------------------------

public static primitive class Console
{
    [InlineTemplate("println!(\"{}\", {0})")]
    public static extern void WriteLine([Borrows] string message);

    [InlineTemplate("print!(\"{}\", {0})")]
    public static extern void Write([Borrows] string message);

    [InlineTemplate("eprintln!(\"{}\", {0})")]
    public static extern void WriteErrorLine([Borrows] string message);
}

[MapsTo("std::time::Duration")]
public primitive struct TimeSpan
{
    [InlineTemplate("std::time::Duration::from_millis({0} as u64)")]
    public static extern TimeSpan FromMilliseconds(long ms);

    [InlineTemplate("std::time::Duration::from_secs({0} as u64)")]
    public static extern TimeSpan FromSeconds(long seconds);

    [Borrows]
    [InlineTemplate("{self}.as_millis() as i64")]
    public extern long TotalMilliseconds { get; }
}

```

---

### Part 3: Formal LINQ-to-Iterator Lowering & Borrow-Coercion Rules

Because Rust iterators distinguish between iterating by shared reference (`.iter()` yielding `&T`), mutable reference (`.iter_mut()` yielding `&mut T`), and consuming ownership (`.into_iter()` yielding owned `T`), **Pass 2** applies a deterministic **3-Rule Iterator Selection Algorithm** whenever it encounters a `LinqChain` AST node:

#### Rule 1: Source Iterator Entry Selection (`.iter()` vs. `.into_iter()`)

Given a LINQ chain rooted at collection `source`:

1. **Non-Consuming Query (Default):** If `source` is referenced again later in the method OR is a borrowed parameter (`&[T]`), Pass 2 emits `source.iter()`.
2. **Consuming Pipeline (Zero-Clone Optimization):** If `source` is a local `List<T>` variable whose last live use in the method is this LINQ pipeline and the terminal is `.ToList()` or `.ToHashSet()` over non-`Copy` elements, Pass 2 emits `source.into_iter()`, moving elements directly without cloning!

#### Rule 2: Closure Reference Depth Normalization

When `.iter()` is followed by `.filter(|x| ...)` in Rust, `.iter()` yields `&T` and `.filter()` passes `&&T` to its closure—a notorious Rust ergonomic annoyance.

* **RustSharp Compiler Normalization:** Inside any `.Where(x => ...)` or `.FirstOrDefault(x => ...)` lambda body, the RustSharp AST emitter binds `x` cleanly and automatically dereferences or borrows fields (`x.is_active` instead of forcing the user to write `(**x).is_active`), and automatically appends `.cloned()` before `.collect::<Vec<_>>()` if the pipeline projects `&T` from a borrowed `.iter()`.

#### Rule 3: Concrete Lowering Examples

| RustSharp (`.rsharp`) Expression | Pass 2 Analysis | Emitted Zero-Cost Rust (`.rs`) |
| --- | --- | --- |
| `orders.Where(o => o.Total > 50m).Select(o => o.Id).ToList()` | `orders` is borrowed (`ReadBorrow`); `o.Id` is `i32` (`CopyValue`). | `orders.iter().filter(|o| o.total > Decimal::new(500, 1)).map(|o| o.id).collect::<Vec<_>>()` |
| `users.FirstOrDefault(u => u.Email == target)` | `users` is borrowed; returns `Option<User>` (`User?`). | `users.iter().find(|u| u.email == target).cloned()` |
| `items.Any(x => x.IsExpired)` | Short-circuit boolean check; zero allocation. | `items.iter().any(|x| x.is_expired)` |
| `scores.Where(s => s > 0).Sum()` | Numeric reduction over `i32` (`CopyValue`). | `scores.iter().copied().filter(|&s| s > 0).sum::<i32>()` |

---

### Part 4: Parameter Borrow Coercion Matrix for `primitive` Types

Because `String` and `List<T>` declare `[ParamType("&str")]` and `[ParamType("&[{T}]")]` in `RustSharp.Core.d.rsharp`, Pass 2 automatically selects the idiomatic Rust slice/reference type for every method signature:

| `.rsharp` Parameter Type | Inferred `ReadBorrow` Signature | Inferred `MutBorrow` Signature | Inferred `OwnedMove` Signature | Caller Coercion Applied by Pass 3 |
| --- | --- | --- | --- | --- |
| **`string`** | `&str` | `&mut String` | `String` | Passes `&s` (or `s.as_str()`) for `ReadBorrow`; `"literal".to_string()` if `OwnedMove`.

 |
| **`List<T>`** | `&[T]` (or `&Vec<T>` if `.capacity()` read) | `&mut Vec<T>` | `Vec<T>` | Passes `&list` (coerces via `Deref` to `&[T]`) for `ReadBorrow`; `&mut list` for `MutBorrow`.

 |
| **`ReadOnlySpan<T>`** | `&[T]` | *(Illegal: Compile Error)* | `&[T]` | Zero-cost slice `&buf[a..b]` or `vec.as_slice()`.

 |
| **`T?` (`Option<T>`)** | `Option<&T>` (or `Option<T>` if `T: Copy`) | `&mut Option<T>` | `Option<T>` | Passes `opt.as_ref()` automatically when callee expects `Option<&T>`. |

---

### Suggested Next Step

We now have:

1. The **Language Syntax & Lowering Specification**,


2. The **Formal EBNF Grammar & Multi-Pass AST Schema**, and
3. The **`RustSharp.Core.d.rsharp` Standard Library & LINQ-to-Iterator Specification**.

Would you like to **build the working Phase 1 Prototype Transpiler (`rsharpc`)** next—executing Pass 1 (Parser/Symbol Table), Pass 2 (Interprocedural Borrow, Mutation & `throws` Effect Inference + Pre-Flight Diagnostics), and Pass 3 (Idiomatic Rust & `Cargo.toml` Emitter) on a multi-file `.rsharp` project?








just create multi phase plan and then create repomap for codebase of  the working Phase 1 Prototype Transpiler (rsharpc)






### Part 1: Multi-Phase Implementation Plan for `rsharpc` (Phase 1 Prototype)

Building a working, self-contained Phase 1 prototype of the **RustSharp Compiler (`rsharpc`)** is divided into **six sequential milestones (M1–M6)** following our three-pass whole-program architecture. Implementing the Phase 1 prototype in **Rust** (or Python for rapid AST prototyping) gives direct access to structured AST manipulation, deterministic call-graph traversal, and `cargo check` / `rustc` verification.

| Milestone | Phase Name | Core Deliverables | Verification Gate |
| --- | --- | --- | --- |
| **M1** | **Frontend Foundation (Lexer, Parser & Span Tracker)** | • Tokenize `.rsharp` and `.d.rsharp` files with exact `SourceSpan` (`file_id`, `line`, `col`) tracking.

<br>

<br>• Recursive-descent + Pratt expression parser producing the raw Phase 1 `.rsharp` AST (`CompilationUnit`, `TypeDecl`, `MemberDecl`, `Stmt`, `Expr`) with empty Pass 2 semantic slots.

 | Parses `RustSharp.Core.d.rsharp` and multi-file `.rsharp` fixtures (including `service class`, `shared class`, `primitive class`, `throws`, and `..` slicing) with 100% span accuracy.

 |
| **M2** | **Pass 1: Virtual Namespace Aggregator & Global Symbol Table** | • Scan all `.rsharp`, `.d.rsharp`, and co-located `.rs` files in a `.rsproj` workspace simultaneously.

<br>

<br>• Decouple physical folder paths from logical `namespace` declarations.

<br>

<br>• Register all archetypes (`record`, `struct`, `service class`, `shared class`, `primitive class`, `interface`, `enum`) into a unified `GlobalSymbolTable`, resolving circular cross-file type references.

 | Two `.rsharp` files in separate directories with mutually recursive type references resolve cleanly into a unified namespace module plan.

 |
| **M3** | **Pass 2A: Archetype Lowering, Hierarchy Flattening & Overload Resolution** | • Enforce `private`, `protected`, and `internal` (`pub(crate)`) access rules.

<br>

<br>• Classify `service class` fields as `Arc<T>` (`readonly`) and `shared class` fields as `Arc<RwLock<T>>`.

<br>

<br>• Resolve inheritance into **Flattened Structs (`Deref`)**, **Closed-World Enums (`match`)**, or **Open Traits (`pub trait`)**.

<br>

<br>• Statically disambiguate overloaded methods and constructors (`find_by_id`, `find_by_email`).

 | Zero dynamic vtable wrappers emitted; closed-world subclasses lower to exhaustive Rust `enum` variants; overloaded calls resolve statically at compile time.

 |
| **M4** | **Pass 2B: Interprocedural Borrow, Effect (`throws`) & LINQ Analyzer** | • Build the whole-program call graph and propagate `BorrowMode` (`&T`, `&mut T`, `T`, `Arc<T>`) bottom-up from callees to callers.

<br>

<br>• Propagate `throws TError` across call graphs into `Result<T, TError>`, marking unguarded calls for `?` injection and `try/catch` for `match` lowering.

<br>

<br>• Fuse `.Where().Select().ToList()` chains into zero-allocation Rust `.iter().filter().map().collect()` pipelines and erase `primitive` types via `[MapsTo]` / `[InlineTemplate]`.

 | Mutating a parameter inside a helper automatically upgrades the caller's parameter or local variable to `let mut` / `&mut T`; `throws` methods emit `Result<T, E>` and `?` automatically.

 |
| **M5** | **Pass 2.5: Pre-Flight Ownership Verifier (`RSHARP001`–`RSHARP003`)** | • Run deterministic ownership and aliasing checks on the decorated `.rsharp` AST *before* invoking `rustc`.

<br>

<br>• Detect `service class` field mutation outside constructors (`RSHARP001`), collection mutation during `foreach` iteration (`RSHARP002`), and double-moves of non-`Clone` `IDisposable` resources (`RSHARP003`).

 | Intentional ownership violations produce C#-friendly diagnostics pointing to exact `.rsharp` lines and columns without leaking raw `rustc` borrow errors.

 |
| **M6** | **Pass 3: Idiomatic Rust Emitter, Co-Located `.rs` Linker & Cargo Synthesizer** | • Emit formatted, idiomatic `.rs` modules grouped by logical namespace (`src/<namespace>.rs`) alongside `src/lib.rs` (or `main.rs`) and `Cargo.toml`.

<br>

<br>• Link `extern partial` declarations with co-located raw `.rs` files in the same crate.

<br>

<br>• Emit `.rsharp.map` bidirectional line mappings and run `cargo check` / `cargo build`.

 | Synthesized Cargo workspace compiles cleanly under `cargo test --release` with zero warnings and zero `Arc<Mutex<T>>` bloat on linear data.

 |

---

### Part 2: Complete Repository Map (`repomap`) for `rsharpc`

Below is the directory hierarchy and module layout for the working Phase 1 prototype repository (`rustsharp-compiler/`):

```text
rustsharp-compiler/
├── Cargo.toml                            # Host workspace config (`rsharpc` binary + `rsharpc_core` lib)
├── README.md                             # Architecture overview, CLI usage & lowering reference
│
├── stdlib/                               # Ambient Compile-Time Standard Library
│   └── RustSharp.Core.d.rsharp           # Zero-cost `primitive` facades (List->Vec, Dict->HashMap, Span->&[T], LINQ, IDisposable->Drop)
│
├── src/
│   ├── main.rs                           # CLI entry point (`rsharpc build`, `rsharpc check`, `rsharpc emit-rs`)
│   ├── lib.rs                            # Compiler pipeline orchestrator (Pass 1 -> Pass 2 -> Pass 2.5 -> Pass 3)
│   ├── project.rs                        # `.rsproj` parser, source/stub discovery, and Cargo workspace planner
│   ├── diagnostics.rs                    # `SourceSpan`, `DiagnosticEngine`, & RSHARP001–RSHARP003 error formatters
│   │
│   ├── frontend/                         # [MILESTONE 1] Lexer, Parser & Multi-Pass .rsharp AST
│   │   ├── mod.rs
│   │   ├── tokens.rs                     # `TokenKind` enum (`service`, `shared`, `primitive`, `extensible`, `throws`, `..`, `??`, `?.`)
│   │   ├── lexer.rs                      # Hand-written UTF-8 lexer (handles `$"..."`, `10.0m` Decimal, `::`, attributes)
│   │   ├── ast.rs                        # Multi-pass AST nodes + Pass 2 semantic slots (`BorrowMode`, `EffectSignature`, etc.)
│   │   └── parser.rs                     # Recursive-descent declaration parser + Pratt expression parser
│   │
│   ├── semantics/                        # [MILESTONES 2, 3, 4, 5] Whole-Project Static Analyzer
│   │   ├── mod.rs
│   │   ├── symbols.rs                    # Pass 1: `GlobalSymbolTable`, `SymbolId`, `TypeSymbol`, `NamespaceNode`
│   │   ├── collector.rs                  # Pass 1: Multi-file type/signature collector & virtual namespace aggregator
│   │   ├── archetype_analyzer.rs         # Pass 2A: `record`, `service class` (`Arc`), `shared class` (`Arc<RwLock>`) & `IDisposable` (`Drop`)
│   │   ├── hierarchy_lowerer.rs          # Pass 2A: Struct flattening (`Deref`), closed-world `enum` dispatch, or open `pub trait`
│   │   ├── overload_resolver.rs          # Pass 2A: Static compile-time method & constructor overload disambiguator
│   │   ├── primitive_resolver.rs         # Pass 2B: `[MapsTo]`, `[ParamType]`, `[InlineTemplate]`, & `[Moves]`/`[Mutates]` binder
│   │   ├── borrow_inferencer.rs          # Pass 2B: Interprocedural call-graph escape & mutation propagator (`&T`, `&mut T`, `T`)
│   │   ├── effect_inferencer.rs          # Pass 2B: `throws` / `try-catch` call-graph analyzer -> `Result<T, E>` & `?` injection
│   │   ├── linq_fuser.rs                 # Pass 2B: Chained LINQ -> fused Rust `.iter().filter().map().collect()` lowers
│   │   └── preflight_verifier.rs         # Pass 2.5: Pre-flight ownership & aliasing verifier (Rules RSHARP001–RSHARP003)
│   │
│   └── codegen/                          # [MILESTONE 6] Pass 3 Idiomatic Rust & Cargo Workspace Emitter
│       ├── mod.rs
│       ├── cargo_synthesizer.rs          # Generates `Cargo.toml`, `src/lib.rs` module tree, & links co-located `.rs` files
│       ├── rs_ast_emitter.rs             # Emits structs, enums, traits, `impl` blocks, and `impl Drop`
│       ├── expr_emitter.rs               # Emits expressions, caller coercions (`&`, `&mut`, `.clone()`), `?`, & inline templates
│       └── sourcemap.rs                  # Bidirectional `.rsharp` <-> `.rs` line map & `rustc` fallback span translator
│
└── tests/                                # End-to-End & Milestone Verification Suite
    ├── m1_parser_tests.rs                # Verifies EBNF coverage: archetypes, `throws`, slicing, patterns
    ├── m2_namespace_resolution_tests.rs  # Verifies decoupled folders & circular type references across files
    ├── m3_polymorphism_overload_tests.rs # Verifies closed-world enum dispatch, `Deref` base embedding, static overloads
    ├── m4_borrow_and_effect_tests.rs     # Verifies bottom-up `&mut` inference, `Result<T, E>` + `?`, & LINQ iterator fusion
    ├── m5_preflight_diagnostics_tests.rs # Verifies RSHARP001, RSHARP002, and RSHARP003 catch borrow errors pre-rustc
    └── fixtures/
        └── commerce_workspace/           # Multi-file sample project (`Commerce.rsproj`)
            ├── Commerce.rsproj
            ├── Features/
            │   ├── Checkout/
            │   │   └── OrderHandler.rsharp   # `service class`, `throws ValidationError`, bottom-up `&mut Order`
            │   └── Payments/
            │       └── PaymentHierarchy.rsharp # Closed-world `abstract class Payment` -> lowered to Rust `enum`
            └── Ingest/
                ├── PacketHeader.rsharp       # `extern partial struct` using `ReadOnlySpan<byte>`
                └── PacketHeader.rs           # Co-located raw `.rs` zero-copy slice parser in the same crate!

```

---

### Part 3: Module-by-Module Symbol Map & Pipeline Signatures

This section defines the exact structs, enums, and method signatures inside each module of `src/` so the Phase 1 prototype can be built cleanly file by file.

##### 1. Core Infrastructure (`src/diagnostics.rs` & `src/project.rs`)

```text
src/diagnostics.rs
├── pub struct SourceSpan { file_id: usize, start_line: u32, start_col: u32, end_line: u32, end_col: u32 }
├── pub enum DiagnosticCode { RSharp001ServiceMutation, RSharp002CollectionAliasing, RSharp003UseAfterMove, AccessViolation, UnresolvedSymbol }
├── pub struct Diagnostic { code: DiagnosticCode, message: String, span: SourceSpan, quick_fix: Option<String> }
└── pub struct DiagnosticEngine
    ├── pub fn report_rsharp001(&mut self, span: SourceSpan, service_name: &str, field_name: &str)
    ├── pub fn report_rsharp002(&mut self, span: SourceSpan, collection_name: &str)
    ├── pub fn report_rsharp003(&mut self, span: SourceSpan, var_name: &str, moved_at: SourceSpan)
    └── pub fn has_errors(&self) -> bool

src/project.rs
├── pub struct RsProjConfig
│   ├── pub name: String                  # Cargo crate name (scopes `internal` -> `pub(crate)`)
│   ├── pub root_dir: PathBuf
│   ├── pub out_cargo_dir: PathBuf        # e.g., `target/rsharp_synth/`
│   ├── pub cargo_dependencies: Vec<(String, String)>
│   ├── pub rsharp_files: Vec<PathBuf>    # Discovered `.rsharp` and `.d.rsharp` files
│   └── pub colocated_rs_files: Vec<PathBuf> # Discovered raw `.rs` files (`extern partial`)
└── pub fn load_rsproj(path: &Path) -> Result<RsProjConfig, String>

```

---

##### 2. Frontend Layer (`src/frontend/`)

```text
src/frontend/tokens.rs
├── pub enum TokenKind
│   ├── Archetypes & Modifiers: Service, Shared, Primitive, Extensible, Record, Class, Struct, Interface, Enum,
│   │                           Public, Internal, Protected, Private, Readonly, Partial, Extern, Throws
│   ├── Operators: DotDot (".."), Caret ("^"), NullCoalesce ("??"), NullCond ("?."), FatArrow ("=>"), ColonColon ("::")
│   └── Literals: Ident(String), IntLit(i64), FloatLit(f64), DecimalLit(String), StringLit(String), InterpString(Vec<InterpPart>)
└── pub struct Token { pub kind: TokenKind, pub span: SourceSpan }

src/frontend/ast.rs
├── pub enum BorrowMode { Unresolved, ReadBorrow, MutBorrow, OwnedMove, SharedArc, CopyValue }
├── pub enum PolymorphismStrategy { Unresolved, MonomorphicStruct, FlattenedSubStruct(SymbolId), ClosedWorldEnum(Vec<SymbolId>), OpenTrait }
├── pub enum EffectSignature { Unresolved, Infallible, Fallible { error_type: ResolvedType } }
├── pub enum CallerArgCoercion { None, BorrowShared, BorrowMutable, DerefReborrow, CloneOwned, ArcClone }
├── pub struct CompilationUnit { pub file_id: usize, pub is_ambient_stub: bool, pub namespace: Vec<String>, pub imports: Vec<ImportDecl>, pub types: Vec<TypeDecl> }
├── pub struct TypeDecl { pub id: SymbolId, pub kind: TypeKind, pub name: String, pub members: Vec<MemberDecl>, pub inferred_polymorphism: PolymorphismStrategy, ... }
├── pub struct MethodDecl { pub id: SymbolId, pub name: String, pub params: Vec<ParamDecl>, pub explicit_throws: Option<TypeRef>, pub inferred_self_borrow: BorrowMode, pub inferred_effect: EffectSignature, pub disambiguated_rust_name: String, ... }
└── pub struct Expr { pub span: SourceSpan, pub kind: ExprKind, pub resolved_type: Option<ResolvedType>, pub append_try_question_mark: bool, pub caller_coercion: CallerArgCoercion }

src/frontend/parser.rs
└── pub struct Parser
    ├── pub fn new(tokens: Vec<Token>, file_id: usize) -> Self
    ├── pub fn parse_compilation_unit(&mut self, diag: &mut DiagnosticEngine) -> CompilationUnit
    ├── fn parse_type_decl(&mut self) -> TypeDecl
    ├── fn parse_member_decl(&mut self) -> MemberDecl
    ├── fn parse_stmt(&mut self) -> Stmt
    └── fn parse_expr(&mut self, min_bp: u8) -> Expr

```

---

##### 3. Semantic Analysis & Ownership Inference Layer (`src/semantics/`)

```text
src/semantics/symbols.rs & collector.rs
├── pub struct GlobalSymbolTable
│   ├── pub types: HashMap<SymbolId, TypeSymbol>
│   ├── pub methods: HashMap<SymbolId, MethodSymbol>
│   ├── pub namespaces: BTreeMap<Vec<String>, Vec<SymbolId>> # Virtual namespace -> aggregated TypeIds
│   └── pub fn resolve_type(&self, name: &str, current_ns: &[String], imports: &[ImportDecl]) -> Option<SymbolId>
└── pub fn collect_global_symbols(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable, diag: &mut DiagnosticEngine)

src/semantics/archetype_analyzer.rs
└── pub fn analyze_archetypes(units: &mut [CompilationUnit], symtab: &GlobalSymbolTable)
    # 1. Marks `service class` fields as `FieldStorageMode::ArcShared` and enforces readonly semantics
    # 2. Marks `shared class` fields as `FieldStorageMode::RwLockShared`
    # 3. Detects `IDisposable` implementation -> sets `has_disposable_drop = true`

src/semantics/hierarchy_lowerer.rs
└── pub fn resolve_polymorphism_strategies(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable)
    # Inspects whole-crate subclass graphs:
    # - Sealed/internal abstract hierarchies -> `PolymorphismStrategy::ClosedWorldEnum`
    # - Concrete single inheritance -> `PolymorphismStrategy::FlattenedSubStruct` (+ `Deref`/`DerefMut`)
    # - `extensible interface` -> `PolymorphismStrategy::OpenTrait`

src/semantics/overload_resolver.rs
└── pub fn resolve_overloads(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable)
    # Assigns disambiguated snake_case Rust names (`find_by_id`, `find_by_email`, `new`, `from_email`)
    # and binds every `ExprKind::MethodCall` to its target `resolved_overload: SymbolId`

src/semantics/borrow_inferencer.rs
└── pub struct InterproceduralBorrowInferencer
    ├── pub fn infer_all(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable)
    ├── fn build_call_graph(&self, units: &[CompilationUnit]) -> CallGraph
    ├── fn propagate_parameter_borrows_bottom_up(&mut self, scc_order: &[SymbolId])
    │   # Infers `ReadBorrow` (&T / &str / &[T]), `MutBorrow` (&mut T), or `OwnedMove` (T)
    └── fn annotate_caller_coercions_and_local_mut(&mut self, method: &mut MethodDecl)
        # Sets `inferred_mut = true` on `Stmt::LocalVar` and `CallerArgCoercion::BorrowMutable` at call sites!

src/semantics/effect_inferencer.rs
└── pub fn infer_checked_effects(units: &mut [CompilationUnit], symtab: &mut GlobalSymbolTable)
    # 1. Rewrites methods with `throws TError` to `EffectSignature::Fallible { error_type }`
    # 2. Sets `append_try_question_mark = true` on unguarded calls to fallible methods
    # 3. Marks `try / catch` blocks for `match` lowering

src/semantics/linq_fuser.rs
└── pub fn fuse_linq_pipelines(units: &mut [CompilationUnit], symtab: &GlobalSymbolTable)
    # Rewrites chained `.Where().Select().ToList()` / `.Any()` / `.Sum()` calls into `ExprKind::LinqChain`
    # Selects `.iter()` vs `.into_iter()` and normalizes closure reference depth

src/semantics/preflight_verifier.rs
└── pub fn run_preflight_ownership_checks(units: &[CompilationUnit], symtab: &GlobalSymbolTable, diag: &mut DiagnosticEngine)
    # Enforces RSHARP001 (service mutation), RSHARP002 (collection aliasing in foreach), RSHARP003 (use-after-move)

```

---

##### 4. Rust Code Generation & Cargo Synthesis Layer (`src/codegen/`)

```text
src/codegen/cargo_synthesizer.rs
└── pub struct CargoWorkspaceSynthesizer
    ├── pub fn synthesize_workspace(config: &RsProjConfig, symtab: &GlobalSymbolTable, units: &[CompilationUnit]) -> Result<(), String>
    ├── fn emit_cargo_toml(&self, config: &RsProjConfig) -> String
    ├── fn emit_lib_or_main_rs(&self, namespaces: &BTreeMap<Vec<String>, Vec<SymbolId>>) -> String
    └── fn link_colocated_rs_files(&self, colocated_files: &[PathBuf]) -> Result<(), String>

src/codegen/rs_ast_emitter.rs
└── pub struct RustModuleEmitter
    ├── pub fn emit_namespace_module(&mut self, ns: &[String], types: &[&TypeDecl], symtab: &GlobalSymbolTable) -> String
    ├── fn emit_record_or_struct(&mut self, decl: &TypeDecl) -> String
    ├── fn emit_service_or_shared_class(&mut self, decl: &TypeDecl) -> String
    ├── fn emit_closed_world_enum_hierarchy(&mut self, base: &TypeDecl, variants: &[&TypeDecl]) -> String
    ├── fn emit_flattened_deref_impl(&mut self, sub: &TypeDecl, base_name: &str) -> String
    ├── fn emit_drop_impl(&mut self, decl: &TypeDecl, dispose_method: &MethodDecl) -> String
    └── fn emit_method(&mut self, method: &MethodDecl) -> String

src/codegen/expr_emitter.rs
└── pub struct RustExprEmitter
    ├── pub fn emit_stmt(&mut self, stmt: &Stmt) -> String
    ├── pub fn emit_expr(&mut self, expr: &Expr) -> String
    ├── fn apply_caller_coercion(&self, rendered_expr: String, coercion: CallerArgCoercion) -> String
    ├── fn expand_primitive_inline_template(&self, tpl: &str, receiver: &str, args: &[String]) -> String
    └── fn emit_fused_linq_chain(&mut self, chain: &LinqChain) -> String

```

---

### Part 4: Data Flow Diagram Across the `rsharpc` Codebase

```text
[ stdlib/RustSharp.Core.d.rsharp ]   [ User .rsharp Files ]   [ Co-Located .rs Files ]
                │                              │                         │
                └──────────────┬───────────────┘                         │
                               ▼                                         │
              ┌──────────────────────────────────┐                       │
              │  M1: frontend/lexer & parser     │                       │
              │  Produces CompilationUnit ASTs   │                       │
              │  with exact .rsharp SourceSpans  │                       │
              └────────────────┬─────────────────┘                       │
                               ▼                                         │
              ┌──────────────────────────────────┐                       │
              │  M2: semantics/collector         │                       │
              │  Populates GlobalSymbolTable     │                       │
              │  Aggregates virtual namespaces & │                       │
              │  resolves circular type refs     │                       │
              └────────────────┬─────────────────┘                       │
                               ▼                                         │
    ┌──────────────────────────┴───────────────────────────┐             │
    ▼                                                      ▼             │
┌────────────────────────────────────┐  ┌──────────────────────────────────────┐
│ M3: semantics/archetype_analyzer,  │  │ M4: semantics/borrow_inferencer,     │
│     hierarchy_lowerer &            │  │     effect_inferencer & linq_fuser   │
│     overload_resolver              │  │ • Bottom-up `&T` / `&mut T` / `T`    │
│ • `service class` -> `Arc<T>`      │  │ • Injects caller `let mut` & `&mut`  │
│ • Closed hierarchy -> Rust `enum`  │  │ • `throws` -> `Result<T, E>` + `?`   │
│ • Static overload disambiguation   │  │ • LINQ -> `.iter().filter().map()`   │
└─────────────────┬──────────────────┘  └──────────────────┬───────────────────┘
                  └────────────────────┬───────────────────┘             │
                                       ▼                                 │
                      ┌──────────────────────────────────┐               │
                      │  M5: semantics/preflight_verifier│               │
                      │  Enforces RSHARP001–RSHARP003    │               │
                      │  (Halts with .rsharp diagnostics │               │
                      │   if ownership rules violated)   │               │
                      └────────────────┬─────────────────┘               │
                                       ▼                                 │
                      ┌──────────────────────────────────┐               │
                      │  M6: codegen/cargo_synthesizer & │◄──────────────┘
                      │      rs_ast_emitter              │ (Links `extern partial`
                      │  • Emits `src/<namespace>.rs`    │  raw `.rs` modules)
                      │  • Synthesizes `Cargo.toml` &    │
                      │    `src/lib.rs` + `.rsharp.map`  │
                      └──────────────────────────────────┘

```

---

### Suggested Next Step

With the **Multi-Phase Plan** and **Repository Map (`repomap`)** for `rsharpc` locked in, would you like me to execute a working vertical slice of **`rsharpc`** in the Python interpreter—running all 6 milestones end-to-end on the `commerce_workspace` fixture (`OrderHandler.rsharp`, `PaymentHierarchy.rsharp`, and `PacketHeader.rsharp`) and outputting the complete synthesized Cargo crate files?




