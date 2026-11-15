# Level 2 — Blog 23: Ported 15 — MultiMethod (`15_multimethod`): Multiple Dispatch & Subtype Specificity

In standard object-oriented languages like Python and C++, method dispatch is **single dispatch**: the method executed depends solely on the runtime type of the receiver object (`self`).

What happens when the behavior of an operation depends on the runtime types of **multiple** arguments?
- `collide(Asteroid, Spaceship)` vs `collide(Asteroid, Bullet)` vs `collide(Spaceship, Planet)`
- `draw(Shape, OpenGLCanvas)` vs `draw(Shape, SVGCanvas)`

This is the domain of **Multiple Dispatch (Multimethods)**.

In this post, we examine **`15_multimethod`**, ported from canonical concepts in the `multimethod` library:
1. **The Multiple Dispatch Challenge**: Single dispatch vs. multiple dispatch matrices.
2. **Project Layout**: The `.psproj` structure.
3. **The C# Implementation (`MultiMethod.ps`)**: Argument type tuples, compatibility checking (`isinstance`), MRO specificity scoring (`issubclass`), and callable wrappers (`*args`).
4. **The Transpiled Output (`micro_multi_method.py`)**: Lambda dispatchers and dynamic type matrices.
5. **The Verification Test Harness (`run_multimethod.py`)**: Exact type matches, subtype specificity (derived vs base classes), cross-type matrices, and missing signature error handling.

---

## 1. Single Dispatch vs. Multiple Dispatch

In traditional OOP:
```python
class Spaceship:
    def collide(self, other):
        # We know self is Spaceship, but what is `other`?
        if isinstance(other, Asteroid):
            ...
        elif isinstance(other, Bullet):
            ...
```
This forces developers to write sprawling `if isinstance(...)` chains, violating the Open/Closed Principle.

With **Multiple Dispatch**:
```python
@multimethod
def collide(s: Spaceship, a: Asteroid): ...

@multimethod
def collide(s: Spaceship, b: Bullet): ...

@multimethod
def collide(a: Asteroid, p: Planet): ...
```
The dispatch engine inspects the runtime types of **all** arguments and routes to the most specific matching function signature.

---

## 2. Project Layout

The project lives under [`Samples/Ported/15_multimethod/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/15_multimethod/):

```
Samples/Ported/15_multimethod/
├── MultiMethod.psproj      # Project configuration manifest
├── MultiMethod.ps          # C# multiple dispatch engine
├── README.md               # Documentation and build instructions
├── run_multimethod.py      # Automated verification test suite
└── dist/
    └── micro_multi_method.py # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `MultiMethod.ps`

In [`MultiMethod.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/15_multimethod/MultiMethod.ps), notice how subtype specificity is evaluated:

```csharp
namespace MicroMultiMethod;

using PythonSharp.Core;

public class MultiMethodEntry
{
    private List<object> _types;
    private object _fn;

    public MultiMethodEntry(List<object> types, object fn)
    {
        this._types = types;
        this._fn = fn;
    }

    public List<object> Types => this._types;
    public object Function => this._fn;
}

public class MultiMethod
{
    private string _name;
    private List<MultiMethodEntry> _entries;

    public MultiMethod(string name = "multimethod")
    {
        this._name = name;
        this._entries = new List<MultiMethodEntry>();
    }

    // Dynamic type predicates
    [InlineTemplate("[type(a) for a in {0}]")]
    public static extern List<object> GetArgTypes(List<object> args);

    [InlineTemplate("all(isinstance(a, t) for a, t in zip({0}, {1}))")]
    public static extern bool IsCompatible(List<object> args, List<object> types);

    [InlineTemplate("all(issubclass(t1, t2) for t1, t2 in zip({0}, {1}))")]
    public static extern bool IsMoreSpecific(List<object> types1, List<object> types2);

    [InlineTemplate("(lambda *args: {self}.dispatch(list(args)))")]
    private extern object MakeCallable();

    public object AsCallable()
    {
        return this.MakeCallable();
    }
```

### The Specificity Selection Algorithm
When `Dispatch(args)` runs:
1. Filter all entries whose types match the runtime arguments via `IsCompatible(args, entry.Types)`.
2. If no candidate matches, raise `SystemException("No matching method for 'name' with argument types (...)")`.
3. If multiple candidates match, compare their specificity using `IsMoreSpecific(entryA.Types, entryB.Types)`:
   - A signature taking `(Circle, Shape)` is more specific than `(Shape, Shape)` because `Circle` is a subclass of `Shape`.
4. Discard candidates that are strictly less specific than another candidate.
5. If exactly one candidate remains, invoke it! If multiple remain with equal score, raise an ambiguous signature error.

```csharp
    public object Dispatch(List<object> args)
    {
        List<MultiMethodEntry> candidates = new List<MultiMethodEntry>();
        int i = 0;
        while (i < this._entries.Count)
        {
            MultiMethodEntry entry = this._entries[i];
            if (entry.Types.Count == args.Count && IsCompatible(args, entry.Types))
            {
                candidates.Add(entry);
            }
            i = i + 1;
        }

        if (candidates.Count == 0)
        {
            List<object> argTypes = GetArgTypes(args);
            throw new SystemException($"No matching method for '{this._name}' with argument types {TypeTupleToString(argTypes)}");
        }

        // Filter to the most specific signature
        MultiMethodEntry best = candidates[0];
        int c = 1;
        while (c < candidates.Count)
        {
            MultiMethodEntry current = candidates[c];
            if (IsMoreSpecific(current.Types, best.Types))
            {
                best = current;
            }
            c = c + 1;
        }

        return InvokeWithList(best.Function, args);
    }
```

---

## 4. The Transpiled Output: `micro_multi_method.py`

Compiling with:
```bash
psc build Samples/Ported/15_multimethod -o Samples/Ported/15_multimethod/dist
```
produces [`Samples/Ported/15_multimethod/dist/micro_multi_method.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/15_multimethod/dist/micro_multi_method.py).

### Using `MultiMethod` from Python:
```python
from micro_multi_method import MultiMethod

# 1. Create MultiMethod instance
combine = MultiMethod("combine")

# 2. Register Overloads across Different Types
combine.register([int, int], lambda a, b: a + b)
combine.register([str, str], lambda a, b: f"{a}_{b}")
combine.register([list, list], lambda a, b: a + b)

# 3. Create Callable Wrapper
fn = combine.as_callable()

assert fn(10, 20) == 30
assert fn("foo", "bar") == "foo_bar"
assert fn([1, 2], [3, 4]) == [1, 2, 3, 4]
```

---

## 5. Verification Test Suite

[`run_multimethod.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/15_multimethod/run_multimethod.py) verifies exact type dispatch, subtype hierarchy specificity, and error handling:

```python
# 1. Exact Type Matches
assert fn(10, 20) == 30
assert fn("alpha", "beta") == "alpha_beta"

# 2. Subtype Specificity (Circle inherits from Shape)
class Shape: pass
class Circle(Shape): pass

draw = MultiMethod("draw")
draw.register([Shape, Shape], lambda a, b: "Generic shapes collision")
draw.register([Circle, Shape], lambda a, b: "Specific circle collides with shape")

draw_fn = draw.as_callable()
# Calling with (Circle(), Shape()) must pick the Circle overload, not the Shape overload!
res = draw_fn(Circle(), Shape())
assert res == "Specific circle collides with shape"

# 3. Missing Signature Handling
try:
    fn(10, "string") # (int, str) was never registered!
    assert False, "Should have raised exception"
except Exception as e:
    assert "No matching method for 'combine' with argument types ('int', 'str')" in str(e)
```

Running the runner:
```bash
python3 Samples/Ported/15_multimethod/run_multimethod.py
```
Outputs:
```
=== Step 1: Building MicroMultiMethod via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported MultiMethod Functionality ===
[PASS] Exact type dispatch across (int, int), (str, str), (list, list) verified
[PASS] Subtype specificity (Circle vs Shape) verified
[PASS] Multi-argument cross-type dispatch matrix verified
[PASS] Missing signature correctly raised: No matching method for 'combine' with argument types ('int', 'str')
[PASS] AsCallable wrapper (*args) verified

All micro-multimethod verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Multiple Dispatch in Pure PythonSharp**: Solving the $N$-argument dispatch problem with compile-time type safety and runtime MRO scoring.
2. **Subtype Specificity Algorithm**: Automatically selecting the most derived class overload when multiple signatures match.
3. **Idiomatic Python Wrappers**: `AsCallable()` returns a standard `*args` lambda closure that can be called like any native Python function.

---

## Next Steps

Now let's examine fault tolerance, exponential backoff, and decorator syntax!

In **[Blog 24: Ported 16 — Micro-Retry (`16_micro_retry`): Exponential Backoff & Resilience Decorators](./24_ported_16_micro_retry_exponential_backoff_and_decorators.md)**, we examine how to implement resilient retry loops and decorator wrappers!

