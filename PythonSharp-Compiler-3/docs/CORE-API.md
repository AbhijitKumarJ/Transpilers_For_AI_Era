# PythonSharp Core Library Reference (`PythonSharp.Core`)

**Status:** Phase 2 & Triple-Surface Architecture Complete  
**Last updated:** 2026-10-31  
**Related docs:** [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DIAGNOSTICS.md](DIAGNOSTICS.md)

---

## 1. Overview & Architectural Principles

The `PythonSharp.Core` standard library (`stdlib/PythonSharp.Core.d.ps`) provides the fundamental types, collections, mathematics, resource management, and LINQ query operators for PythonSharp.

Key architectural design tenets:
1. **Zero Runtime Wrapper Tax**: Ambient types in `PythonSharp.Core` carry `[MapsTo("...")]` or `[InlineTemplate("...")]` annotations. At compile time, they provide full C# static typing; at code generation time, they erase completely to native Python builtins or standard library modules (`str`, `list`, `dict`, `set`, `math`, `asyncio`). No wrapper classes or runtime adapters are deployed with transpiled packages.
2. **Compile-time Static Safety, Runtime Python Isomorphism**: Types are verified statically during Pass 1 and Pass 2 (visibility, member access, arity, nullability, LINQ fusion validity). Emitted code uses idiomatic Python constructs.
3. **Automatic Ambient Module Imports**: When transpiled code references types mapped to Python standard library modules (such as `Math` -> `math`, non-fused LINQ -> `itertools`/`statistics`, or `Task.Delay` -> `asyncio`), the code generator automatically emits the corresponding `import` statements.

---

## 2. Primitive & Fundamental Type Mapping

| C# / PythonSharp Type | Python Target | Erased Type | Semantics & Notes |
|---|---|---|---|
| `object` | `object` | `object` | Root of the nominal hierarchy; erases to Python's `object`. |
| `string` / `String` | `str` | `str` | Immutable Unicode strings; supports indexing and slicing. |
| `bool` | `bool` | `bool` | Boolean (`True` / `False`). Overload resolution orders `bool` before `int` to avoid Python subclassing traps. |
| `int` / `long` | `int` | `int` | Arbitrary-precision Python integers. |
| `float` / `double` | `float` | `float` | IEEE 754 double-precision floating-point numbers. |
| `decimal` | `decimal.Decimal` | `Decimal` | Exact decimal arithmetic via Python's standard `decimal` module. |
| `void` | `None` | `None` | Method return type indicating no value returned. |

### 2.1 Primitive Static Classes (`Int32`, `Double`, `Boolean`)

The standard library provides static helper classes for numeric and boolean operations, accessible either by keyword (`int`, `double`, `bool`) or type name (`Int32`, `Double`, `Boolean`):

| Member | Python Lowering | Description |
|---|---|---|
| `Int32.Parse(s)` / `int.Parse(s)` | `int(s)` | Parses an integer from string. Raises `ValueError` if invalid. |
| `Int32.From(val)` / `int.From(val)` | `int(val)` | Explicit conversion to `int`. |
| `Double.Parse(s)` / `double.Parse(s)` | `float(s)` | Parses a floating-point number from string. |
| `Double.From(val)` / `double.From(val)` | `float(val)` | Explicit conversion to `float`. |
| `Boolean.Parse(s)` / `bool.Parse(s)` | `bool(s)` | Parses a boolean. |

---

## 3. String Operations (`String`)

The `String` type exposes standard string manipulation methods mapped directly to Python string methods:

```csharp
string text = "  Hello, PythonSharp!  ";
int len = text.Length;                     // len(text)
string trimmed = text.Trim();              // text.strip()
string ltrimmed = text.TrimStart();        // text.lstrip()
string rtrimmed = text.TrimEnd();          // text.rstrip()
string lower = text.ToLower();             // text.lower()
string upper = text.ToUpper();             // text.upper()
string padded = text.PadLeft(30, " ");     // text.rjust(30, " ")
string rightPad = text.PadRight(30, ".");  // text.ljust(30, ".")
bool hasSub = text.Contains("Hello");      // "Hello" in text
bool starts = text.StartsWith("  ");       // text.startswith("  ")
bool ends = text.EndsWith("!");            // text.endswith("!")
string replaced = text.Replace("!", "?");  // text.replace("!", "?")
List<string> parts = text.Split(",");      // text.split(",")
string joined = String.Join(",", parts);   // ",".join(parts)
string sub = text.Substring(2, 5);         // text[2:2+5]
int idx = text.IndexOf("P");               // text.find("P")
int lastIdx = text.LastIndexOf("P");       // text.rfind("P")
bool empty = String.IsNullOrEmpty(text);   // (text is None or len(text) == 0)
char ch = text[0];                         // text[0]
```

---

## 4. Collections

### 4.1 `List<T>` (Target: `list`)

Indexed, mutable linear collections mapping directly to Python's built-in `list`:

| Method / Property | Python Lowering | Notes & Differences vs .NET |
|---|---|---|
| `Count` | `len(self)` | Read-only integer count. |
| `Add(item)` | `self.append(item)` | Appends to the end of the list. |
| `AddRange(items)` | `self.extend(items)` | Appends all elements from an iterable. |
| `Insert(index, item)` | `self.insert(index, item)` | Inserts at the specified index. |
| `Remove(item)` | `self.remove(item)` | **Behavior difference**: Raises `ValueError` if item is missing (unlike .NET which returns `bool`). Guard with `Contains` if needed. |
| `RemoveAt(index)` | `self.pop(index)` | Removes and discards element at `index`. |
| `Pop()` | `self.pop()` | Removes and returns the last element. |
| `Clear()` | `self.clear()` | Removes all items. |
| `IndexOf(item)` | `self.index(item)` | Returns 0-based index or raises `ValueError`. |
| `Contains(item)` | `item in self` | Returns boolean presence. |
| `Sort()` | `self.sort()` | In-place stable sort. |
| `Reverse()` | `self.reverse()` | In-place list reversal. |
| `this[index]` | `self[index]` | Element read/write via indexing. |

### 4.2 `Dict<K, V>` (Target: `dict`)

Key-value hash map mapping directly to Python's built-in `dict`:

| Method / Property | Python Lowering | Notes & Differences vs .NET |
|---|---|---|
| `Count` | `len(self)` | Read-only integer count of keys. |
| `Add(key, value)` | `self[key] = value` | **Behavior difference**: Overwrites existing key rather than throwing `ArgumentException`. |
| `Remove(key)` | `self.pop(key)` | **Behavior difference**: Raises `KeyError` if key is missing. Guard with `ContainsKey` if needed. |
| `ContainsKey(key)` | `key in self` | Check key presence in $O(1)$. |
| `ContainsValue(val)` | `val in self.values()` | Check value presence in $O(N)$. |
| `GetOrDefault(key, default)`| `self.get(key, default)`| Returns value or supplied fallback if missing. |
| `Clear()` | `self.clear()` | Removes all mappings. |
| `Keys()` | `list(self.keys())` | Returns key collection. |
| `Values()` | `list(self.values())` | Returns value collection. |
| `Items()` | `list(self.items())` | Returns collection of `KeyValuePair<K, V>`. |
| `this[key]` | `self[key]` | Indexer read/write (`self[key] = val` or `self[key]`). |

### 4.3 `HashSet<T>` (Target: `set`)

Unique unordered set mapping directly to Python's built-in `set`:

| Method / Property | Python Lowering | Notes |
|---|---|---|
| `Count` | `len(self)` | Number of unique elements. |
| `Add(item)` | `self.add(item)` | Adds item to set. |
| `Remove(item)` | `self.discard(item)` | **Behavior difference**: Idempotent; does not throw if missing (Python `set.discard`). |
| `Contains(item)` | `item in self` | Fast membership test. |
| `Clear()` | `self.clear()` | Empties set. |
| `UnionWith(other)` | `self.update(other)` | In-place set union ($\cup$). |
| `IntersectWith(other)` | `self.intersection_update(other)` | In-place set intersection ($\cap$). |
| `ExceptWith(other)` | `self.difference_update(other)` | In-place set difference ($\setminus$). |
| `SymmetricExceptWith(other)`| `self.symmetric_difference_update(other)` | In-place symmetric difference ($\Delta$). |
| `IsSubsetOf(other)` | `self.issubset(other)` | Subset check ($\subseteq$). |
| `IsSupersetOf(other)` | `self.issuperset(other)` | Superset check ($\supseteq$). |
| `Overlaps(other)` | `not self.isdisjoint(other)` | Non-empty intersection check. |
| `SetEquals(other)` | `self == set(other)` | Set equality test. |

---

## 5. Mathematical Operations (`Math`)

The `Math` static class maps directly to Python's standard `math` module (with `import math` emitted automatically):

| Member | Python Lowering | Description |
|---|---|---|
| `Math.PI` | `math.pi` | Ratio of circumference to diameter ($\approx 3.14159$). |
| `Math.E` | `math.e` | Base of natural logarithms ($\approx 2.71828$). |
| `Math.Sqrt(d)` | `math.sqrt(d)` | Square root $\sqrt{d}$. |
| `Math.Pow(x, y)` | `math.pow(x, y)` | Power function $x^y$. |
| `Math.Exp(d)` | `math.exp(d)` | Exponential $e^d$. |
| `Math.Log(d)` | `math.log(d)` | Natural logarithm $\ln(d)$. |
| `Math.Sin(a)` / `Cos` / `Tan` | `math.sin(a)` / `cos` / `tan` | Trigonometric functions (radians). |
| `Math.Abs(v)` | `abs(v)` | Absolute value $\|v\|$. |
| `Math.Max(val1, val2)` | `max(val1, val2)` | Maximum of two values. Not fused as LINQ terminal (D-017). |
| `Math.Min(val1, val2)` | `min(val1, val2)` | Minimum of two values. Not fused as LINQ terminal (D-017). |
| `Math.Clamp(val, min, max)` | `min(max(val, min), max)` | Clamps value within `[min, max]`. |
| `Math.Ceiling(d)` | `math.ceil(d)` | Smallest integral value $\ge d$. |
| `Math.Floor(d)` | `math.floor(d)` | Largest integral value $\le d$. |
| `Math.Round(d)` | `round(d)` | Rounds to nearest integral value. |
| `Math.Truncate(d)` | `math.trunc(d)` | Discards fractional digits. |
| `Math.Sign(d)` | `(1 if d > 0 else (-1 if d < 0 else 0))` | Sign indicator ($-1, 0, 1$). |

---

## 5.1 Console Output (`Console`)

The `Console` static primitive class provides standard terminal I/O mapping directly to Python's built-in `print`:

| Member | Python Lowering | Description |
|---|---|---|
| `Console.WriteLine()` | `print()` | Emits a newline to standard output. |
| `Console.WriteLine(value)` | `print(value)` | Prints value followed by a newline. |
| `Console.Write(value)` | `print(value, end="", flush=True)` | Prints value without newline, flushing the stream immediately (ideal for progress bars). |

---

## 6. LINQ Operators & Lowering Rules

PythonSharp supports standard LINQ extension methods over `IEnumerable<T>`.

### 6.1 Fused Comprehensions vs Lazy Fallback

1. **Comprehension Fusion**: When a LINQ chain consists of recognized fusable stages (such as `Where(...)`, `Select(...)`) ending in a terminal materializer (`ToList()`, `ToHashSet()`, `ToDict(...)`, `Sum()`, `Count()`, `Any(...)`, `All(...)`, `FirstOrDefault(...)`), the compiler fuses the entire pipeline into a single Python list/set/dict comprehension or generator expression without allocating intermediate iterators.
2. **Explicit Stage Guard (D-017)**: Only methods carrying the `[LinqStage]` metadata attribute are recognized as fusion candidates. Ordinary methods sharing names (e.g., `Math.Max`) are never mistakenly fused.
3. **Lazy Fallback Pipeline (D-018)**: When chains include non-fusable operators (e.g. `OrderBy`, `Distinct`, `Skip`, `Take`, `Concat`), the compiler lowers the operations into a chain of Python iterators using `filter()`, `map()`, `itertools.islice()`, and `itertools.chain()`.
4. **Stable Ordering Composition**: Multi-key ordering (`OrderBy(k1).ThenBy(k2).ThenByDescending(k3)`) lowers by applying stable Python `sorted()` passes in reverse key order, guaranteeing exact multi-key ordering semantics.
5. **Deferred Operators**: `SingleOrDefault()` remains intentionally deferred until a faithful single-element check can be emitted without introducing a runtime helper.

### 6.2 Supported LINQ Methods

```csharp
var items = list.Where(x => x > 0)
                .Select(x => x * 2)
                .OrderBy(x => x)
                .Distinct()
                .Take(5)
                .ToList();
```

- **Filtering & Projection**: `Where`, `Select`, `SelectMany`.
- **Ordering**: `OrderBy`, `OrderByDescending`, `ThenBy`, `ThenByDescending`.
- **Set & Partitioning**: `Distinct`, `Take` (clamped $\ge 0$), `Skip` (clamped $\ge 0$), `Concat`.
- **Quantifiers & Search**: `Contains`, `Any`, `All`, `FirstOrDefault`, `LastOrDefault`.
- **Aggregators**: `Count`, `Sum`, `Min`, `Max`, `Average`.
- **Materializers**: `ToList`, `ToHashSet`, `ToDict`.

---

## 7. Exception Model & Mapping

PythonSharp uses direct Python exception isomorphism (D-016). No custom wrapper exceptions or runtime adapters are used.

| PythonSharp / C# Exception | Transpiled Python Exception | Description |
|---|---|---|
| `Exception` / `SystemException` | `Exception` | Base application exception. |
| `ArgumentException` | `ValueError` | Argument value invalid. |
| `ArgumentNullException` | `ValueError` | Null argument supplied. |
| `InvalidOperationException` | `RuntimeError` | State invalid for method invocation. |
| `NotSupportedException` | `NotImplementedError` | Feature or method unsupported. |
| `NotImplementedException` | `NotImplementedError` | Method body not implemented. |
| `IndexOutOfRangeException` | `IndexError` | Array or list subscript out of range. |
| `KeyNotFoundException` | `KeyError` | Specified key absent from dictionary. |
| `NullReferenceException` | `AttributeError` | Access on null reference. |
| `FormatException` | `ValueError` | String format incompatible. |
| `TimeoutException` | `TimeoutError` | Operation exceeded time allotment. |
| `UnauthorizedAccessException`| `PermissionError` | Permission check failure. |
| `DivideByZeroException` | `ZeroDivisionError` | Division by zero. |
| `OverflowException` | `OverflowError` | Arithmetic overflow. |
| `IOException` | `OSError` | File or network I/O error. |
| `FileNotFoundException` | `FileNotFoundError` | Target file does not exist. |
| `DirectoryNotFoundException` | `FileNotFoundError` | Target directory does not exist. |

### Catch & Dispatch Semantics
- **Guarded Catches (`when`)**: When multiple catch clauses or `when` condition guards are used, the compiler generates a single ordered dispatcher over `BaseException`. If a `when` guard evaluates to `False`, execution falls through cleanly to subsequent catch blocks, mirroring C# behavior.
- **Bare `throw;`**: Re-raises the active exception. Valid only within a catch handler.

---

## 8. Resource Management

- `IDisposable`: Transpiles classes to Python context managers by synthesizing `__enter__` (returning `self`) and `__exit__` (calling `Dispose()`).
- `IAsyncDisposable`: Transpiles classes to Python asynchronous context managers by synthesizing `__aenter__` and `__aexit__` (calling `await DisposeAsync()`).
- `using (var r = ...)` blocks lower to Python `with ...:` or `async with ...:`.

---

## 9. Triple-Surface Modular Standard Library Bundles (`stdlib/`)

In addition to `PythonSharp.Core.d.ps`, PythonSharp organizes its standard library and ecosystem bindings into a modular, multi-surface package hierarchy under `stdlib/`:

### 9.1 Package Hierarchy

```text
stdlib/
├── PythonSharp.Core.d.ps                  # Fundamental Core types, primitives, and LINQ
├── 01_python_stdlib/                      # Modular Python standard library bindings
│   ├── os_shutil/                         # Raw, Bridge, and Enterprise IO/Environment stubs
│   ├── sys/                               # Runtime, platform, and terminal arguments
│   ├── json/                              # JSON serializer and dictionary parser
│   ├── re/                                # Regular expression matchers and patterns
│   └── time_datetime/                     # SystemClock, Stopwatch, and ThreadOperations
└── 02_scientific_and_ai/                  # High-performance scientific packages
    └── 01_numpy/                          # Tensor primitives, creation, and linear algebra
```

### 9.2 The Tri-Modal Surface Ladder

Each package is structured into 4 cohesive declaration files:
1. `00_{pkg}.primitives.d.ps`: Ambient primitives (`primitive class`) declaring fundamental data structures and operators (`[MapsTo]`, `[RuntimeType]`).
2. `01_{pkg}.raw.d.ps`: **Surface 1 (Raw ABI)** snake_case stubs (`[SurfaceLevel(1)]`) for direct Python API alignment.
3. `02_{pkg}.csharp.d.ps`: **Surface 2 (Idiomatic C# Bridge)** PascalCase stubs (`[SurfaceLevel(2)]`) connecting Python APIs to idiomatic C#.
4. `03_{pkg}.enterprise.d.ps`: **Surface 3 (Enterprise Architecture)** strongly typed domain facade classes (`[SurfaceLevel(3)]`).

### 9.3 Intrinsic Surface Metadata Attributes

| Attribute | Parameters | Description |
|---|---|---|
| `[SurfaceLevel(level)]` | `int level` (1, 2, or 3) | Designates the tier of the annotated class or member. Stripped at compile time. |
| `[CanonicalApi("Target", "Bridge")]` | `string target, string? bridge = null` | Records the recommended enterprise alternative and bridge path for tooling, LSP hovers, and compiler warnings (`PS005`). |

### 9.4 Scientific Tensor Primitives: `NDArray<T>`

The `NDArray<T>` generic primitive (`stdlib/02_scientific_and_ai/01_numpy/00_numpy.primitives.d.ps`) maps directly to `numpy.ndarray` with zero runtime wrapper tax:
- **Matrix Multiplication Operator (`@`) Lowering**: `matrixA.MultiplyMatrix(matrixB)` compiles directly to Python's native `(matrixA @ matrixB)`.
- **Properties Across Surfaces**: `.DimensionShape` (Surface 3), `.Shape` (Surface 2), `.shape` (Surface 1) all erase directly to `.shape`.
- **Transpose**: `.TransposedMatrix` / `.T` erases directly to `.T`.
- **Multi-Axis Slicing**: Multidimensional indexing syntax `matrix[0..2, 0..2]` lowers into Python `matrix[0:2, 0:2]`.

