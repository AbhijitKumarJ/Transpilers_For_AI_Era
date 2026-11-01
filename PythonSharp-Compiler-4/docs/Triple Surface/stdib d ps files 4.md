The complete six-file modular `stdlib/00_core/` declaration bundle (`00_attributes.d.ps`, `01_contracts.d.ps`, `02_primitives.d.ps`, `03_builtins.raw.d.ps`, `04_builtins.csharp.d.ps`, and `05_core.enterprise.d.ps`) replaces the monolithic `stdlib/PythonSharp.Core.d.ps` and establishes the foundational compiler intrinsics, zero-cost collection primitives, and Triple-Surface Python built-in bindings loaded first by `load_project()`.

---

### `stdlib/00_core/00_attributes.d.ps`

Defines all compiler-intrinsic attributes governing type erasure (`[MapsTo]`, `[InlineTemplate]`, `[RuntimeType]`), Triple-Surface metadata (`[CanonicalApi]`, `[SurfaceLevel]`), LINQ comprehension fusion (`[LinqStage]`), keyword argument unpacking (`[KwArgs]`), decorator lowering (`[PythonDecorator]`), Pydantic schema emission (`[SchemaModel]`), and native C-extension compilation (`[NativeCompile]`).

```csharp
namespace PythonSharp.Core;

public abstract class Attribute { }

/// Erases the PythonSharp identifier and emits the target Python symbol or type annotation.
public sealed class MapsToAttribute : Attribute
{
    public MapsToAttribute(string pythonTarget) { }
}

/// Substitutes {self}, {0}, {1}, and {value} directly into a Python 3.11+ AST expression.
public sealed class InlineTemplateAttribute : Attribute
{
    public InlineTemplateAttribute(string pythonAstTemplate) { }
}

/// Specifies the concrete Python runtime class used inside `isinstance(arg, py_type)` checks
/// when synthesizing method overload dispatch tables.
public sealed class RuntimeTypeAttribute : Attribute
{
    public RuntimeTypeAttribute(string pythonRuntimeType) { }
}

/// Links a Surface 2 (Raw Python) or Surface 3 (C# Bridge) declaration to its
/// Surface 1 Enterprise FQN and Surface 3 Bridge FQN for IDE hover cards and migration hints.
public sealed class CanonicalApiAttribute : Attribute
{
    public CanonicalApiAttribute(string enterpriseFqn, string csharpBridgeFqn = "") { }
}

/// Identifies whether an ambient declaration belongs to Surface 1 (Enterprise),
/// Surface 2 (Raw Python), or Surface 3 (C# Bridge).
public sealed class SurfaceLevelAttribute : Attribute
{
    public SurfaceLevelAttribute(int surfaceNumber) { }
}

/// Lowers a Dict<string, T> or object parameter into Python `**kwargs: T`.
public sealed class KwArgsAttribute : Attribute { }

/// Marks an IEnumerable<T> method as part of a chainable LINQ query to be fused
/// by Pass 2B into a single Python comprehension or generator expression.
public sealed class LinqStageAttribute : Attribute
{
    public LinqStageAttribute(string stageKind) { }
}

/// Marks a C# attribute class so that applying `[MyAttr(...)]` to a class or method
/// emits `@my_attr(...)` in Python.
public class PythonDecoratorAttribute : Attribute
{
    public PythonDecoratorAttribute(string decoratorPath) { }
}

/// Suppresses automatic `__slots__` generation and lowers the type into a
/// `pydantic.BaseModel` subclass for runtime schema validation.
public sealed class SchemaModelAttribute : Attribute { }

/// Instructs Pass 3 to emit strict `mypyc` / Cython compatible output for native compilation.
public sealed class NativeCompileAttribute : Attribute { }

```

---

### `stdlib/00_core/01_contracts.d.ps`

Declares the core interfaces (`IDisposable`, `IAsyncDisposable`, `IEquatable<T>`, `IComparable<T>`, `IEnumerable<T>`, and `IAsyncEnumerable<T>`) and all `[LinqStage]` comprehension pipeline methods fused during Pass 2B.

```csharp
namespace PythonSharp.Core;

extern using builtins;
extern using collections.abc as abc;
extern using contextlib;
extern using itertools;

/// Implementing IDisposable on any PythonSharp class automatically synthesizes `__enter__`
/// and `__exit__` calling `self.dispose()`, and lowers `using var x = ...;` to `with ... as x:`.
[MapsTo("contextlib.AbstractContextManager")]
public interface IDisposable
{
    [MapsTo("dispose")]
    void Dispose();
}

/// Implementing IAsyncDisposable synthesizes `__aenter__` and `__aexit__`
/// and lowers `await using var x = ...;` to `async with ... as x:`.
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

[MapsTo("collections.abc.AsyncIterable")]
[RuntimeType("collections.abc.AsyncIterable")]
public primitive interface IAsyncEnumerable<T> { }

/// Zero-cost LINQ pipeline contract. Chained calls are fused by `LinqComprehensionFuser`
/// in Pass 2B into single-pass native Python list, set, dict, or generator comprehensions.
[MapsTo("collections.abc.Iterable")]
[RuntimeType("collections.abc.Iterable")]
public primitive interface IEnumerable<T>
{
    // --- Lazy Comprehension / Generator Stages (Fused in Pass 2B) ---

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

```

---

### `stdlib/00_core/02_primitives.d.ps`

Declares the zero-cost runtime-erased primitive types (`String`, `Bytes`, `Complex`, `List<T>`, `Dict<TKey, TValue>`, `HashSet<T>`, `KeyValuePair<TKey, TValue>`, `TextFileStream`, `Task`, `Task<TResult>`, `DateTime`, `TimeSpan`, `Console`, and `Math`) with Triple-Surface methods so Python `snake_case`, C# `PascalCase`, and self-documenting enterprise calls all resolve on the same primitive instances.

```csharp
namespace PythonSharp.Core;

extern using builtins;
extern using asyncio;
extern using math as py_math;
extern using datetime as dt;

// ----------------------------------------------------------------------------
// 1. STRINGS, BYTES & COMPLEX NUMBERS
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

    // --- Surface 1 & 3 (C# / Enterprise) ---
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

    [MapsTo("encode")]
    public extern Bytes Encode(string encoding = "utf-8");

    // --- Surface 2 (Raw Python snake_case aliases) ---
    [CanonicalApi("PythonSharp.Core.String.StartsWith")]
    [MapsTo("startswith")]
    public extern bool startswith(string prefix);

    [CanonicalApi("PythonSharp.Core.String.EndsWith")]
    [MapsTo("endswith")]
    public extern bool endswith(string suffix);

    [CanonicalApi("PythonSharp.Core.String.ToLower")]
    [MapsTo("lower")]
    public extern string lower();

    [CanonicalApi("PythonSharp.Core.String.ToUpper")]
    [MapsTo("upper")]
    public extern string upper();

    [CanonicalApi("PythonSharp.Core.String.Trim")]
    [MapsTo("strip")]
    public extern string strip();

    [CanonicalApi("PythonSharp.Core.String.Replace")]
    [MapsTo("replace")]
    public extern string replace(string old, string @new);

    [CanonicalApi("PythonSharp.Core.String.Split")]
    [MapsTo("split")]
    public extern List<string> split(string? sep = null, int maxsplit = -1);

    [CanonicalApi("PythonSharp.Core.String.Encode")]
    [MapsTo("encode")]
    public extern Bytes encode(string encoding = "utf-8");

    [InlineTemplate("{0}.join({1})")]
    public static extern string Join(string separator, IEnumerable<string> values);

    [InlineTemplate("(not {0} or {0}.isspace())")]
    public static extern bool IsNullOrWhiteSpace(string? value);

    [InlineTemplate("(not {0})")]
    public static extern bool IsNullOrEmpty(string? value);

    [InlineTemplate("{self}[{0}]")]
    public extern string this[int index] { get; }
}

[MapsTo("bytes")]
[RuntimeType("bytes")]
public primitive class Bytes : IEnumerable<int>
{
    [InlineTemplate("len({self})")]
    public extern int Length { get; }

    [MapsTo("decode")]
    public extern string DecodeUtf8(string encoding = "utf-8");

    [CanonicalApi("PythonSharp.Core.Bytes.DecodeUtf8")]
    [MapsTo("decode")]
    public extern string Decode(string encoding = "utf-8");

    [CanonicalApi("PythonSharp.Core.Bytes.DecodeUtf8", "Decode")]
    [MapsTo("decode")]
    public extern string decode(string encoding = "utf-8");

    [MapsTo("hex")]
    public extern string ToHexString();

    [CanonicalApi("PythonSharp.Core.Bytes.ToHexString")]
    [MapsTo("hex")]
    public extern string hex();

    [InlineTemplate("{self}[{0}]")]
    public extern int this[int index] { get; }
}

[MapsTo("complex")]
[RuntimeType("complex")]
public primitive struct Complex
{
    [InlineTemplate("complex({0}, {1})")]
    public extern Complex(double real, double imag = 0.0);

    [InlineTemplate("float({self}.real)")]
    public extern double Real { get; }

    [CanonicalApi("PythonSharp.Core.Complex.Real")]
    [InlineTemplate("float({self}.real)")]
    public extern double real { get; }

    [InlineTemplate("float({self}.imag)")]
    public extern double Imaginary { get; }

    [CanonicalApi("PythonSharp.Core.Complex.Imaginary")]
    [InlineTemplate("float({self}.imag)")]
    public extern double imag { get; }

    [MapsTo("conjugate")]
    public extern Complex Conjugate();

    [CanonicalApi("PythonSharp.Core.Complex.Conjugate")]
    [MapsTo("conjugate")]
    public extern Complex conjugate();
}

// ----------------------------------------------------------------------------
// 2. COLLECTIONS: List<T>, Dict<TKey, TValue>, HashSet<T>, KeyValuePair<K, V>
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

    // --- Surface 1 & 3 (C# / Enterprise) ---
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

    // --- Surface 2 (Raw Python snake_case aliases) ---
    [CanonicalApi("PythonSharp.Core.List.Add")]
    [MapsTo("append")]
    public extern void append(T item);

    [CanonicalApi("PythonSharp.Core.List.AddRange")]
    [MapsTo("extend")]
    public extern void extend(IEnumerable<T> iterable);

    [CanonicalApi("PythonSharp.Core.List.Pop")]
    [MapsTo("pop")]
    public extern T pop(int index = -1);

    [CanonicalApi("PythonSharp.Core.List.Clear")]
    [MapsTo("clear")]
    public extern void clear();

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

    [CanonicalApi("PythonSharp.Core.Dict.GetOrDefault")]
    [MapsTo("get")]
    public extern TValue? get(TKey key, TValue? defaultValue = default);

    [InlineTemplate("({0} in {self})")]
    public extern bool ContainsKey(TKey key);

    [InlineTemplate("({self}.pop({0}, None) is not None)")]
    public extern bool Remove(TKey key);

    [MapsTo("pop")]
    public extern TValue Pop(TKey key, TValue defaultValue);

    [MapsTo("update")]
    public extern void Merge(Dict<TKey, TValue> other);

    [CanonicalApi("PythonSharp.Core.Dict.Merge")]
    [MapsTo("update")]
    public extern void update(Dict<TKey, TValue> other);

    [MapsTo("clear")]
    public extern void Clear();

    [CanonicalApi("PythonSharp.Core.Dict.Clear")]
    [MapsTo("clear")]
    public extern void clear();

    [MapsTo("keys")]
    public extern IEnumerable<TKey> Keys();

    [CanonicalApi("PythonSharp.Core.Dict.Keys")]
    [MapsTo("keys")]
    public extern IEnumerable<TKey> keys();

    [MapsTo("values")]
    public extern IEnumerable<TValue> Values();

    [CanonicalApi("PythonSharp.Core.Dict.Values")]
    [MapsTo("values")]
    public extern IEnumerable<TValue> values();

    [MapsTo("items")]
    public extern IEnumerable<KeyValuePair<TKey, TValue>> Items();

    [CanonicalApi("PythonSharp.Core.Dict.Items")]
    [MapsTo("items")]
    public extern IEnumerable<KeyValuePair<TKey, TValue>> items();

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

    [CanonicalApi("PythonSharp.Core.HashSet.Add")]
    [MapsTo("add")]
    public extern void add(T item);

    [MapsTo("discard")]
    public extern void Remove(T item);

    [CanonicalApi("PythonSharp.Core.HashSet.Remove")]
    [MapsTo("discard")]
    public extern void discard(T item);

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
// 3. FILE STREAMS, ASYNC TASKS, CONSOLE, MATH & DATETIME
// ----------------------------------------------------------------------------

[MapsTo("typing.TextIO")]
[RuntimeType("object")]
public primitive class TextFileStream : IDisposable
{
    [MapsTo("read")]
    public extern string ReadAllText();

    [CanonicalApi("PythonSharp.Core.TextFileStream.ReadAllText")]
    [MapsTo("read")]
    public extern string Read();

    [CanonicalApi("PythonSharp.Core.TextFileStream.ReadAllText", "Read")]
    [MapsTo("read")]
    public extern string read();

    [MapsTo("readlines")]
    public extern List<string> ReadAllLines();

    [CanonicalApi("PythonSharp.Core.TextFileStream.ReadAllLines")]
    [MapsTo("readlines")]
    public extern List<string> ReadLines();

    [CanonicalApi("PythonSharp.Core.TextFileStream.ReadAllLines", "ReadLines")]
    [MapsTo("readlines")]
    public extern List<string> readlines();

    [MapsTo("write")]
    public extern int WriteText(string content);

    [CanonicalApi("PythonSharp.Core.TextFileStream.WriteText")]
    [MapsTo("write")]
    public extern int Write(string content);

    [CanonicalApi("PythonSharp.Core.TextFileStream.WriteText", "Write")]
    [MapsTo("write")]
    public extern int write(string s);

    [MapsTo("close")]
    public extern void Dispose();
}

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

    [InlineTemplate("math.e")]
    public static extern double E { get; }

    [InlineTemplate("math.inf")]
    public static extern double Infinity { get; }

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

### `stdlib/00_core/03_builtins.raw.d.ps`

Provides **Surface 2 (Raw Python Mirror)** for Python built-in functions (`len`, `range`, `enumerate`, `zip`, `print`, `open`, `getattr`, `setattr`, `hasattr`, `isinstance`), special module variables (`__name__`, `__file__`), and `math` constants (`math.pi`, `math.e`, `math.inf`).

```csharp
namespace builtins;

using PythonSharp.Core;
extern using builtins as _py_builtins;
extern using math as _py_math;

[SurfaceLevel(2)]
[MapsTo("_py_builtins")]
public static primitive class builtins
{
    // --- Special Module Variables ---
    [CanonicalApi("PythonSharp.Core.ModuleContext.CurrentModuleName", "PythonSharp.Builtins.Builtins.ModuleName")]
    [InlineTemplate("__name__")]
    public static extern string __name__ { get; }

    [CanonicalApi("PythonSharp.Core.ModuleContext.CurrentFilePath", "PythonSharp.Builtins.Builtins.ModuleFilePath")]
    [InlineTemplate("__file__")]
    public static extern string __file__ { get; }

    // --- Built-in Sequence & Iteration Functions ---
    [CanonicalApi("PythonSharp.Core.SequenceOperations.GetElementCount", "PythonSharp.Builtins.Builtins.Len")]
    [InlineTemplate("len({0})")]
    public static extern int len(object sizedCollection);

    [CanonicalApi("PythonSharp.Core.IntegerRange.FromZeroToStop", "PythonSharp.Builtins.Builtins.Range")]
    [InlineTemplate("range({0})")]
    public static extern IEnumerable<int> range(int stop);

    [CanonicalApi("PythonSharp.Core.IntegerRange.FromStartToStop", "PythonSharp.Builtins.Builtins.Range")]
    [InlineTemplate("range({0}, {1})")]
    public static extern IEnumerable<int> range(int start, int stop);

    [CanonicalApi("PythonSharp.Core.IntegerRange.CreateStepped", "PythonSharp.Builtins.Builtins.Range")]
    [InlineTemplate("range({0}, {1}, {2})")]
    public static extern IEnumerable<int> range(int start, int stop, int step);

    [CanonicalApi("PythonSharp.Core.SequenceOperations.EnumerateWithIndex", "PythonSharp.Builtins.Builtins.Enumerate")]
    [InlineTemplate("enumerate({0}, {1})")]
    public static extern IEnumerable<KeyValuePair<int, T>> enumerate<T>(IEnumerable<T> iterable, int start = 0);

    [CanonicalApi("PythonSharp.Core.SequenceOperations.ZipSequences", "PythonSharp.Builtins.Builtins.Zip")]
    [InlineTemplate("zip({0}, {1})")]
    public static extern IEnumerable<KeyValuePair<TFirst, TSecond>> zip<TFirst, TSecond>(
        IEnumerable<TFirst> first,
        IEnumerable<TSecond> second);

    // --- Built-in I/O & Reflection Functions ---
    [CanonicalApi("PythonSharp.Core.StandardConsole.WriteLine", "PythonSharp.Builtins.Builtins.Print")]
    [InlineTemplate("print({0})")]
    public static extern void print(object? value = null);

    [CanonicalApi("PythonSharp.Core.FileStreams.OpenTextStream", "PythonSharp.Builtins.Builtins.Open")]
    [InlineTemplate("open({0}, {1}, encoding={2})")]
    public static extern TextFileStream open(string file, string mode = "r", string encoding = "utf-8");

    [CanonicalApi("PythonSharp.Core.ObjectInspector.GetAttributeOrDefault", "PythonSharp.Builtins.Builtins.GetAttr")]
    [InlineTemplate("getattr({0}, {1}, {2})")]
    public static extern object? getattr(object target, string name, object? defaultValue = null);

    [CanonicalApi("PythonSharp.Core.ObjectInspector.SetAttributeValue", "PythonSharp.Builtins.Builtins.SetAttr")]
    [InlineTemplate("setattr({0}, {1}, {2})")]
    public static extern void setattr(object target, string name, object? value);

    [CanonicalApi("PythonSharp.Core.ObjectInspector.HasAttribute", "PythonSharp.Builtins.Builtins.HasAttr")]
    [InlineTemplate("hasattr({0}, {1})")]
    public static extern bool hasattr(object target, string name);
}

[SurfaceLevel(2)]
[MapsTo("_py_math")]
public static primitive class math
{
    [CanonicalApi("PythonSharp.Core.MathematicalConstants.Pi", "PythonSharp.Builtins.PyMath.Pi")]
    [InlineTemplate("_py_math.pi")]
    public static extern double pi { get; }

    [CanonicalApi("PythonSharp.Core.MathematicalConstants.EulerNumber", "PythonSharp.Builtins.PyMath.E")]
    [InlineTemplate("_py_math.e")]
    public static extern double e { get; }

    [CanonicalApi("PythonSharp.Core.MathematicalConstants.PositiveInfinity", "PythonSharp.Builtins.PyMath.Infinity")]
    [InlineTemplate("_py_math.inf")]
    public static extern double inf { get; }
}

```

---

### `stdlib/00_core/04_builtins.csharp.d.ps`

Provides **Surface 3 (C#-Standardized Module Mirror)** for Python built-in functions and special variables (`PythonSharp.Builtins.Builtins` and `PythonSharp.Builtins.PyMath`).

```csharp
namespace PythonSharp.Builtins;

using PythonSharp.Core;
extern using builtins as _py_builtins;
extern using math as _py_math;

[SurfaceLevel(3)]
[MapsTo("_py_builtins")]
public static primitive class Builtins
{
    // --- Special Module Properties ---
    [CanonicalApi("PythonSharp.Core.ModuleContext.CurrentModuleName")]
    [InlineTemplate("__name__")]
    public static extern string ModuleName { get; }

    [CanonicalApi("PythonSharp.Core.ModuleContext.CurrentFilePath")]
    [InlineTemplate("__file__")]
    public static extern string ModuleFilePath { get; }

    // --- C#-Standardized Built-in Functions ---
    [CanonicalApi("PythonSharp.Core.SequenceOperations.GetElementCount")]
    [InlineTemplate("len({0})")]
    public static extern int Len(object collection);

    [CanonicalApi("PythonSharp.Core.IntegerRange.FromZeroToStop")]
    [InlineTemplate("range({0})")]
    public static extern IEnumerable<int> Range(int stop);

    [CanonicalApi("PythonSharp.Core.IntegerRange.FromStartToStop")]
    [InlineTemplate("range({0}, {1})")]
    public static extern IEnumerable<int> Range(int start, int stop);

    [CanonicalApi("PythonSharp.Core.IntegerRange.CreateStepped")]
    [InlineTemplate("range({0}, {1}, {2})")]
    public static extern IEnumerable<int> Range(int start, int stop, int step);

    [CanonicalApi("PythonSharp.Core.SequenceOperations.EnumerateWithIndex")]
    [InlineTemplate("enumerate({0}, {1})")]
    public static extern IEnumerable<KeyValuePair<int, T>> Enumerate<T>(IEnumerable<T> sequence, int startIndex = 0);

    [CanonicalApi("PythonSharp.Core.SequenceOperations.ZipSequences")]
    [InlineTemplate("zip({0}, {1})")]
    public static extern IEnumerable<KeyValuePair<TFirst, TSecond>> Zip<TFirst, TSecond>(
        IEnumerable<TFirst> first,
        IEnumerable<TSecond> second);

    [CanonicalApi("PythonSharp.Core.StandardConsole.WriteLine")]
    [InlineTemplate("print({0})")]
    public static extern void Print(object? message = null);

    [CanonicalApi("PythonSharp.Core.FileStreams.OpenTextStream")]
    [InlineTemplate("open({0}, {1}, encoding={2})")]
    public static extern TextFileStream Open(string filePath, string mode = "r", string encoding = "utf-8");

    [CanonicalApi("PythonSharp.Core.ObjectInspector.GetAttributeOrDefault")]
    [InlineTemplate("getattr({0}, {1}, {2})")]
    public static extern object? GetAttr(object target, string attributeName, object? defaultValue = null);

    [CanonicalApi("PythonSharp.Core.ObjectInspector.SetAttributeValue")]
    [InlineTemplate("setattr({0}, {1}, {2})")]
    public static extern void SetAttr(object target, string attributeName, object? value);

    [CanonicalApi("PythonSharp.Core.ObjectInspector.HasAttribute")]
    [InlineTemplate("hasattr({0}, {1})")]
    public static extern bool HasAttr(object target, string attributeName);
}

[SurfaceLevel(3)]
[MapsTo("_py_math")]
public static primitive class PyMath
{
    [CanonicalApi("PythonSharp.Core.MathematicalConstants.Pi")]
    [InlineTemplate("_py_math.pi")]
    public static extern double Pi { get; }

    [CanonicalApi("PythonSharp.Core.MathematicalConstants.EulerNumber")]
    [InlineTemplate("_py_math.e")]
    public static extern double E { get; }

    [CanonicalApi("PythonSharp.Core.MathematicalConstants.PositiveInfinity")]
    [InlineTemplate("_py_math.inf")]
    public static extern double Infinity { get; }
}

```

---

### `stdlib/00_core/05_core.enterprise.d.ps`

Provides **Surface 1 (Enterprise Self-Documenting Domain FQN)** for sequence operations, integer ranges, runtime reflection, module context inspection, file stream opening, and mathematical constants.

```csharp
namespace PythonSharp.Core;

extern using builtins as _py_builtins;
extern using math as _py_math;

[SurfaceLevel(1)]
public static primitive class ModuleContext
{
    [InlineTemplate("__name__")]
    public static extern string CurrentModuleName { get; }

    [InlineTemplate("__file__")]
    public static extern string CurrentFilePath { get; }

    [InlineTemplate("(__name__ == '__main__')")]
    public static extern bool IsMainEntryPoint { get; }
}

[SurfaceLevel(1)]
public static primitive class SequenceOperations
{
    [InlineTemplate("len({0})")]
    public static extern int GetElementCount(object sizedCollection);

    [InlineTemplate("enumerate({0}, {1})")]
    public static extern IEnumerable<KeyValuePair<int, T>> EnumerateWithIndex<T>(IEnumerable<T> sequence, int startIndex = 0);

    [InlineTemplate("zip({0}, {1})")]
    public static extern IEnumerable<KeyValuePair<TFirst, TSecond>> ZipSequences<TFirst, TSecond>(
        IEnumerable<TFirst> firstSequence,
        IEnumerable<TSecond> secondSequence);
}

[SurfaceLevel(1)]
public static primitive class IntegerRange
{
    [InlineTemplate("range({0})")]
    public static extern IEnumerable<int> FromZeroToStop(int stopExclusive);

    [InlineTemplate("range({0}, {1})")]
    public static extern IEnumerable<int> FromStartToStop(int startInclusive, int stopExclusive);

    [InlineTemplate("range({0}, {1}, {2})")]
    public static extern IEnumerable<int> CreateStepped(int startInclusive, int stopExclusive, int stepIncrement);
}

[SurfaceLevel(1)]
public static primitive class ObjectInspector
{
    [InlineTemplate("getattr({0}, {1}, {2})")]
    public static extern object? GetAttributeOrDefault(object targetInstance, string attributeName, object? fallbackValue = null);

    [InlineTemplate("setattr({0}, {1}, {2})")]
    public static extern void SetAttributeValue(object targetInstance, string attributeName, object? newValue);

    [InlineTemplate("hasattr({0}, {1})")]
    public static extern bool HasAttribute(object targetInstance, string attributeName);
}

[SurfaceLevel(1)]
public static primitive class FileStreams
{
    [InlineTemplate("open({0}, {1}, encoding={2})")]
    public static extern TextFileStream OpenTextStream(string filePath, string accessMode = "r", string textEncoding = "utf-8");

    [InlineTemplate("open({0}, 'r', encoding='utf-8')")]
    public static extern TextFileStream OpenTextReaderUtf8(string filePath);

    [InlineTemplate("open({0}, 'w', encoding='utf-8')")]
    public static extern TextFileStream OpenTextWriterUtf8(string filePath);
}

[SurfaceLevel(1)]
public static primitive class StandardConsole
{
    [InlineTemplate("print({0})")]
    public static extern void WriteLine(object? message = null);

    [InlineTemplate("print({0}, end='')")]
    public static extern void Write(object? message);

    [InlineTemplate("input({0})")]
    public static extern string ReadLineFromStdin(string promptText = "");
}

[SurfaceLevel(1)]
[MapsTo("_py_math")]
public static primitive class MathematicalConstants
{
    [InlineTemplate("_py_math.pi")]
    public static extern double Pi { get; }

    [InlineTemplate("_py_math.e")]
    public static extern double EulerNumber { get; }

    [InlineTemplate("_py_math.inf")]
    public static extern double PositiveInfinity { get; }
}

```

---

With `stdlib/00_core/`, `stdlib/01_python_stdlib/`, and `stdlib/02_scientific_and_ai/` complete, would you like me to generate the compiler upgrade files for **Milestone U1** (`src/psc/semantics/symbols.py`, `src/psc/semantics/primitive_resolver.py`, `src/psc/codegen/expr_lowerer.py`, and `src/psc/codegen/py_ast_builder.py`) or a multi-surface `.ps` test suite verifying that all three `stdlib/` tiers compile and interop seamlessly?
