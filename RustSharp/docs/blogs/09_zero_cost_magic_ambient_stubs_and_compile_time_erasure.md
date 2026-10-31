# Under the Hood of RustSharp: Blog 09
# Zero-Cost Magic — Ambient Stubs and Compile-Time Erasure

> *Part 9 of the 12-part technical series "Under the Hood of RustSharp: From C# Ergonomics to Pure Zero-Cost Rust"*

---

## 1. The Wrapper Tax in Foreign Function Interfaces

When bridging two distinct languages, standard transpilers almost universally introduce **Wrapper Classes**:
- To use Rust's `String`, a transpiler creates a C# class `RustStringWrapper` containing a 64-bit pointer.
- To call `string.Split()`, the program calls into a C/FFI runtime shim that allocates native heap memory and wraps the result in another class.
- Primitives like `DateTime`, `Guid`, or `TimeSpan` become heap objects.

This wrapper tax creates severe memory fragmentation and destroys CPU instruction cache performance.

RustSharp takes inspiration from TypeScript's ambient declaration files (`.d.ts`). Instead of shipping a heavy C runtime library, RustSharp ships **Ambient Declarations** in [`stdlib/RustSharp.Core.d.rsharp`](file:///home/abhijit/Videos/transpilers/RustSharp/stdlib/RustSharp.Core.d.rsharp).

Ambient declarations define C# type prototypes that exist **purely at compile time**. At code emission time (Pass 3), the compiler **completely erases** the stub class and inlines pure, native Rust types and standard library macros directly into the emitted source code.

---

## 2. Anatomy of an Ambient Stub

Inside `stdlib/RustSharp.Core.d.rsharp`, standard types are decorated with compiler metadata attributes:

```csharp
[MapsTo("String")]
[ParamType("&str")]
public primitive class string
{
    [InlineTemplate("{0}.len() as i32")]
    public extern int Length { get; }

    [InlineTemplate("{0}.is_empty()")]
    public extern bool IsEmpty { get; }

    [InlineTemplate("{0}.to_lowercase()")]
    public extern string ToLower();

    [InlineTemplate("{0}.contains({1})")]
    public extern bool Contains([Borrows] string value);

    [InlineTemplate("{0}.replace({1}, {2})")]
    public extern string Replace([Borrows] string oldValue, [Borrows] string newValue);
}
```

```mermaid
flowchart LR
    Source["C# Code:\nif (name.IsEmpty) {\n    Console.WriteLine(name.ToLower());\n}"]
    Stub["Ambient Metadata in stdlib:\n- [MapsTo(\"String\")]\n- [InlineTemplate(\"{0}.is_empty()\")]\n- [InlineTemplate(\"println!(\\\"{{}}\\\", {0})\")]"]
    Emitted["Pure Emitted Rust:\nif name.is_empty() {\n    println!(\"{}\", name.to_lowercase());\n}"]

    Source --> Stub --> Emitted
```

### The Key Attributes:
1. **`[MapsTo("RustType")]`**: Tells Pass 3 what native Rust type represents this type in struct fields, return types, and local variable declarations.
   - `string` &rarr; `String`
   - `List<T>` &rarr; `Vec<T>`
   - `Dictionary<K, V>` &rarr; `std::collections::HashMap<K, V>`
   - `TimeSpan` &rarr; `std::time::Duration`
2. **`[ParamType("RustBorrow")]`**: Specifies how the type should be accepted when passed as an immutable input parameter.
   - `string` parameters &rarr; `&str`
   - `List<T>` parameters &rarr; `&[T]`
   - `byte[]` parameters &rarr; `&[u8]`
3. **`[InlineTemplate("rust_expression")]`**: Replaces the method call with an exact Rust expression template at compile time.
   - `{0}` references the receiver (`this`).
   - `{1}`, `{2}`, etc. reference method arguments.
4. **`[Borrows]` and `[Moves]`**: Informs Pass 2.5 borrow inference whether an argument is borrowed immutably or moved linearly.

---

## 3. Zero-Allocation Primitive Inlining

Let's look at how everyday C# operations are erased at compile time:

### Case 1: String Checking and Manipulation
```csharp
var clean = input.Trim().ToLower();
```
* **Template for `Trim()`:** `{0}.trim()`
* **Template for `ToLower()`:** `{0}.to_lowercase()`
* **Emitted Rust:**
  ```rust
  let clean = input.trim().to_lowercase();
  ```
Zero runtime wrapper. Zero intermediate class allocations. Standard native Rust methods.

### Case 2: Standard Output Printing (`Console.WriteLine`)
In C#:
```csharp
Console.WriteLine($"Order {order.Id} verified.");
```
In `RustSharp.Core.d.rsharp`:
```csharp
public static primitive class Console {
    [InlineTemplate("println!(\"{}\", {0})")]
    public static extern void WriteLine([Borrows] string message);
}
```
* **Emitted Rust:**
  ```rust
  println!("{}", format!("Order {} verified.", order.id));
  ```
The C# call compiles directly to Rust's built-in `println!` macro.

### Case 3: Threading and Duration
In C#:
```csharp
Thread.Sleep(TimeSpan.FromMilliseconds(500));
```
In `RustSharp.Core.d.rsharp`:
```csharp
[MapsTo("std::thread")]
public static primitive class Thread {
    [InlineTemplate("std::thread::sleep({0})")]
    public static extern void Sleep(TimeSpan timeout);
}

[MapsTo("std::time::Duration")]
public primitive struct TimeSpan {
    [InlineTemplate("std::time::Duration::from_millis({0} as u64)")]
    public static extern TimeSpan FromMilliseconds(long ms);
}
```
* **Emitted Rust:**
  ```rust
  std::thread::sleep(std::time::Duration::from_millis(500 as u64));
  ```
`TimeSpan` does not exist in the generated binary. It was completely erased and replaced by Rust's standard `std::time::Duration`.

---

## 4. Collections: `List<T>` and `Dictionary<K, V>`

In .NET, `List<T>` and `Dictionary<TKey, TValue>` have complex runtime layouts with internal sync roots and version fields. In RustSharp:

### `List<T>` Stubs:
```csharp
[MapsTo("Vec<{0}>")]
[ParamType("&[{0}]")]
public primitive class List<T>
{
    [InlineTemplate("Vec::new()")]
    public extern List();

    [InlineTemplate("Vec::with_capacity({0} as usize)")]
    public extern List(int capacity);

    [InlineTemplate("{0}.push({1})")]
    public extern void Add([Moves] T item);

    [InlineTemplate("{0}.len() as i32")]
    public extern int Count { get; }

    [InlineTemplate("{0}.clear()")]
    public extern void Clear();
}
```

When client code writes:
```csharp
var buffer = new List<byte>(1024);
buffer.Add(0xFF);
```

The emitted Rust is:
```rust
let mut buffer = Vec::with_capacity(1024 as usize);
buffer.push(255);
```

The generated code is identical to what an expert systems engineer would hand-write in native Rust.

---

## 5. Summary & What's Next

Ambient stubs and compile-time template erasure provide:
- **Zero Runtime Tax:** No heavy runtime libraries or foreign function shims.
- **Pure Native Rust Types:** Direct mapping to `String`, `&str`, `Vec<T>`, and `std::time::Duration`.
- **Zero Overhead Inlining:** Standard methods are replaced with zero-cost Rust macros and native functions.

In **[Blog 10: Two-Way Interop — Linking Native Rust with extern partial](10_two_way_interop_linking_native_rust_with_extern_partial.md)**, we examine how RustSharp enables seamless two-way interoperability: allowing C# code to invoke raw Rust SIMD kernels and letting existing Rust crates generate ambient C# headers via `rsharp-bindgen`.

