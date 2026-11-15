# Blog 07: Polymorphism & Speed — Method Overloads, Dataclasses & Slots

In C#, you can define two or three methods with the exact same name, as long as their parameter types differ:
```csharp
public class Logger
{
    public void Log(string message) { ... }
    public void Log(string message, int code) { ... }
    public void Log(Exception ex) { ... }
}
```

Now try doing that in Python:
```python
class Logger:
    def log(self, message: str): ...
    def log(self, message: str, code: int): ... # Overwrites the first one!
    def log(self, ex: Exception): ...           # Overwrites both!
```
In Python, **the last method definition silently replaces everything that came before it**. Python has no native compiler support for method overloading.

In this post, we explore how PythonSharp solves this problem, and how it maximizes Python runtime performance using:
1. **Method Overloading**: Combining `@typing.overload` with an automatic runtime type dispatcher.
2. **C# Records**: Compiling directly to `@dataclass(frozen=True, slots=True)`.
3. **`__slots__`**: Shrinking memory usage and accelerating property lookups.

---

## 1. How PythonSharp Emits Method Overloads

To make overloads work in Python, two things are needed:
1. **Static Type Signatures**: So IDEs (VS Code, PyCharm) and type checkers (MyPy, Pyright) know all available ways to call the function.
2. **A Runtime Dispatcher**: A single real implementation that inspects the incoming arguments and routes the call to the right logic.

In [`src/psc/codegen/overload_emitter.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/codegen/overload_emitter.py), PythonSharp generates both automatically!

### The C# Source:
```csharp
public class DataProcessor
{
    public string Process(int id) => $"ID: {id}";
    public string Process(string text) => $"Text: {text}";
    public string Process(string key, object value) => $"{key}={value}";
}
```

### The Emitted Python 3.11+:
```python
from typing import overload

class DataProcessor:
    __slots__ = ()

    # 1. Type annotations for IDE autocompletion
    @overload
    def process(self, id: int) -> str: ...

    @overload
    def process(self, text: str) -> str: ...

    @overload
    def process(self, key: str, value: object) -> str: ...

    # 2. Synthesized runtime dispatcher
    def process(self, *args, **kwargs) -> str:
        _n = len(args)
        if _n == 1:
            _a0 = args[0]
            if isinstance(_a0, int):
                return f'ID: {_a0}'
            if isinstance(_a0, str):
                return f'Text: {_a0}'
        elif _n == 2:
            return f'{args[0]}={args[1]}'
        raise TypeError(f"No overload of 'process' matches arguments {args!r}")
```

Look at how smart the dispatcher is:
- It checks argument counts first (`len(args)`).
- For single-argument calls, it checks `isinstance(_a0, int)` vs `isinstance(_a0, str)`.
- If someone calls `process(3.14)` (an invalid type), it raises a helpful `TypeError` explaining that no overload matched.

---

## 2. C# Records -> Frozen Slotted Dataclasses

In modern C#, **Records** are the preferred way to model immutable data structures:
```csharp
public record User(int Id, string Email, bool IsActive = true);
```

In Python 3.7+, Python introduced `@dataclass`. But in Python 3.10+, dataclasses gained a superpower: `slots=True`.

When PythonSharp encounters a `record`, it emits:
```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class User:
    __ps_types__ = ('Commerce.User',)
    id: int
    email: str
    is_active: bool = True
```

Notice the properties:
- **`frozen=True`**: Enforces C# record immutability. Trying to do `user.email = "new"` raises `FrozenInstanceError` at runtime.
- **`slots=True`**: Strips the internal `__dict__` dictionary, drastically reducing memory consumption.
- **Value Equality**: Automatically generates `__eq__` that compares by value, matching C# record equality semantics.

---

## 3. Why `__slots__` Matters So Much

In standard Python, every object instance contains a dynamic dictionary called `__dict__` to store its attributes. While flexible, this dictionary adds heavy memory overhead (~150+ bytes per instance) and requires hash-table lookups for every attribute access.

In C#, class layouts are fixed at compile time.

PythonSharp's [`SlotAnalyzer`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/semantics/slot_analyzer.py) bridges this difference:
1. It analyzes every class, collecting all private fields and backing properties.
2. It emits a fixed `__slots__` tuple on the Python class definition.

```python
class OrderProcessor:
    __slots__ = ('_db', '_logger', '_cache')

    def __init__(self, db: Database, logger: Logger) -> None:
        self._db = db
        self._logger = logger
        self._cache = {}
```

### The Performance Benefits of `__slots__`:
- **~40% to 50% Memory Reduction**: In applications creating millions of objects (such as data pipelines or web scrapers), using `__slots__` prevents memory bloat.
- **Faster Attribute Access**: Python accesses slotted attributes using fixed C-struct offsets rather than hash table lookups.
- **Strict Attribute Prevention**: Prevents typos like `self.totall = 10` (which would silently create a new attribute in normal Python).

---

## 4. Nominal Type Tracking: `__ps_types__`

In C#, types are nominal: if class `Order` implements `IEntity`, `order is IEntity` is true based on inheritance.

In Python, classes might come from different modules or namespaces. To preserve nominal type checking without requiring heavyweight runtime inheritance trees, PythonSharp attaches a lightweight `__ps_types__` tuple:

```python
class Customer:
    __ps_types__ = ('Commerce.Domain.Customer', 'Commerce.Domain.IEntity')
```

When PythonSharp lowers `candidate is IEntity`, it simply emits:
```python
isinstance(candidate, Customer) # or checks __ps_types__
```

---

## Key Takeaways
1. **Overloads** are solved cleanly by emitting `@overload` type stubs alongside an automatic, high-performance runtime type dispatcher.
2. **C# Records** translate seamlessly into Python `@dataclass(slots=True, frozen=True)` with zero manual boilerplate.
3. **`__slots__`** ensures emitted Python classes are as fast and memory-efficient as possible.

Now, prepare for what many consider PythonSharp's most impressive capability:

In **[Blog 08: The Secret Sauce — Fusing LINQ into Native Python Comprehensions](./08_the_secret_sauce_fusing_linq_into_comprehensions.md)**, we'll see how complex C# LINQ queries transform at compile-time into native Python list comprehensions!

