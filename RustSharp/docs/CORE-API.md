# RustSharp Core Library Reference (`RustSharp.Core`)

| Field | Value |
| :--- | :--- |
| **Namespace** | `RustSharp.Core` |
| **Stub File** | `stdlib/RustSharp.Core.d.rsharp` |
| **Status** | Active |
| **Owner** | RustSharp Core Team |
| **Related Documents** | [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md), [PRD.md](PRD.md) |

---

## 1. Overview & Architectural Principles

The RustSharp Core standard library provides the familiar C# primitive types, collections, and utility methods, but executes with **zero runtime overhead**. 

Every type in `RustSharp.Core.d.rsharp` is an ambient compile-time declaration. At compilation time, the compiler erases these wrappers and emits direct, native Rust types and zero-cost iterator pipelines. No external C# runtime, bridge DLL, or reflection assembly is required.

---

## 2. Compiler Intrinsic Attributes

These attributes are defined in `stdlib/RustSharp.Core.d.rsharp` and instruct the code generator how to lower methods, parameters, and expressions:

| Attribute | Description | Example |
| :--- | :--- | :--- |
| `[MapsTo("symbol")]` | Rewrites the member or type name to a native Rust identifier. | `[MapsTo("len")] int Count { get; }` $\rightarrow$ `.len()` |
| `[ParamType("&str")]` | Overrides the emitted Rust parameter type to use an idiomatic borrow. | `void Find([ParamType("&str")] string name)` $\rightarrow$ `&str` |
| `[InlineTemplate("...")]` | Inlines a custom Rust expression formatting template. | `[InlineTemplate("{self}.contains(&{0})")]` |
| `[Moves]` | Notifies the ownership analyzer that this argument consumes the value. | `void Add([Moves] T item)` $\rightarrow$ `vec.push(item)` |

---

## 3. Primitive Type Mappings

| C# Primitive Type | Emitted Rust Type | Borrowed Rust Form | Default Derives / Notes |
| :--- | :--- | :--- | :--- |
| `int` | `i32` | `i32` (Copy) | 32-bit signed integer |
| `long` | `i64` | `i64` (Copy) | 64-bit signed integer |
| `short` | `i16` | `i16` (Copy) | 16-bit signed integer |
| `byte` | `u8` | `u8` (Copy) | 8-bit unsigned integer |
| `float` | `f32` | `f32` (Copy) | 32-bit IEEE float |
| `double` | `f64` | `f64` (Copy) | 64-bit IEEE float |
| `bool` | `bool` | `bool` (Copy) | Boolean |
| `decimal` | `rust_decimal::Decimal` | `rust_decimal::Decimal` | Emits `rust_decimal` crate dependency |
| `string` | `String` | `&str` | Inferred automatically or via `[ParamType]` |

---

## 4. String Operations (`string` / `String`)

In RustSharp, `string` represents a UTF-8 string. The compiler lowers member invocations to native Rust `str` and `String` methods:

| C# Expression | Emitted Rust Lowering | Notes |
| :--- | :--- | :--- |
| `s.Length` | `s.len() as i32` | Byte count (ASCII/UTF-8 length) |
| `s.IsEmpty` | `s.is_empty()` | Fast slice check |
| `s.Contains(sub)` | `s.contains(&sub)` | Native sub-slice search |
| `s.StartsWith(prefix)` | `s.starts_with(&prefix)` | Prefix match |
| `s.EndsWith(suffix)` | `s.ends_with(&suffix)` | Suffix match |
| `s.ToLower()` | `s.to_lowercase()` | Allocates lowercased `String` |
| `s.ToUpper()` | `s.to_uppercase()` | Allocates uppercased `String` |
| `$"ID: {id}"` | `format!("ID: {}", id)` | Interpolated string lowering |

---

## 5. Collections

### 5.1 `List<T>` (Target: `std::vec::Vec<T>`)
Linear dynamically sized heap vector.

```csharp
[MapsTo("std::vec::Vec")]
public class List<T>
{
    [MapsTo("push")]
    public void Add([Moves] T item);

    [MapsTo("len")]
    public int Count { get; }

    [InlineTemplate("{self}[{0} as usize]")]
    public T this[int index] { get; set; }

    [MapsTo("clear")]
    public void Clear();
}
```

- `list.Add(x)` $\rightarrow$ `list.push(x)`
- `list.Count` $\rightarrow$ `list.len() as i32`
- `list[i]` $\rightarrow$ `list[i as usize]`

### 5.2 `Dictionary<K, V>` (Target: `std::collections::HashMap<K, V>`)
Key-value hash map.

- `dict.Add(k, v)` $\rightarrow$ `dict.insert(k, v)`
- `dict.ContainsKey(k)` $\rightarrow$ `dict.contains_key(&k)`
- `dict.Count` $\rightarrow$ `dict.len() as i32`
- `dict[k]` $\rightarrow$ `dict[&k]`

### 5.3 `HashSet<T>` (Target: `std::collections::HashSet<T>`)
Unique value set.

- `set.Add(v)` $\rightarrow$ `set.insert(v)`
- `set.Contains(v)` $\rightarrow$ `set.contains(&v)`
- `set.Count` $\rightarrow$ `set.len() as i32`

---

## 6. Zero-Cost LINQ-to-Iterator Fusion

RustSharp transforms LINQ method chains directly into fused, lazy Rust iterators without heap allocations or temporary collections.

### 6.1 Transformation Table

| LINQ Method | Rust Iterator Adaptor | Notes |
| :--- | :--- | :--- |
| `.Where(x => cond)` | `.filter(\|x\| cond)` | Lazy filtering |
| `.Select(x => expr)` | `.map(\|x\| expr)` | Lazy projection |
| `.ToList()` | `.collect::<Vec<_>>()` | Materialization |
| `.ToHashSet()` | `.collect::<std::collections::HashSet<_>>()` | Set materialization |
| `.Count()` | `.count() as i32` | Iterator count |
| `.Any(x => cond)` | `.any(\|x\| cond)` | Short-circuit boolean |
| `.All(x => cond)` | `.all(\|x\| cond)` | Universal check |
| `.First()` | `.next().unwrap()` | First item (panics if empty) |
| `.FirstOrDefault()` | `.next()` | Lowers to `Option<T>` |

### 6.2 Example: LINQ Pipeline Fusion

```csharp
var activeOrders = orders
    .Where(o => o.Total > 100.0m)
    .Select(o => o.Id)
    .ToList();
```
Emitted Rust Code:
```rust
let active_orders: Vec<_> = orders
    .iter()
    .filter(|o| o.total > rust_decimal::Decimal::new(1000, 1))
    .map(|o| o.id)
    .collect();
```

---

## 7. System Utilities

### 7.1 `Console`
- `Console.WriteLine(msg)` $\rightarrow$ `println!("{}", msg)`
- `Console.WriteLine()` $\rightarrow$ `println!()`
- `Console.Write(msg)` $\rightarrow$ `print!("{}", msg)`

### 7.2 `Math`
All methods lower directly to Rust primitive float/integer intrinsics:
- `Math.Min(a, b)` $\rightarrow$ `a.min(b)` / `std::cmp::min(a, b)`
- `Math.Max(a, b)` $\rightarrow$ `a.max(b)` / `std::cmp::max(a, b)`
- `Math.Abs(x)` $\rightarrow$ `x.abs()`
- `Math.Sqrt(x)` $\rightarrow$ `x.sqrt()`
- `Math.Floor(x)` $\rightarrow$ `x.floor()`
- `Math.Ceiling(x)` $\rightarrow$ `x.ceil()`

