# Level 2 — Blog 21: Ported 13 — Micro-Fn (`13_micro_fn`): Functional Programming, Currying & Composition

Welcome to **Tier 6: Core Language Features & Metaprogramming**!

In this tier, we transition from data structures and algorithms to **language-level programming paradigms**. We begin with **`13_micro_fn`**, ported from canonical functional programming concepts popularized by `fn.py`.

In this post, we explore:
1. **The Functional Paradigm**: First-class functions, currying, partial application, and function composition ($f \circ g$).
2. **Project Layout**: The `.psproj` structure.
3. **The C# Implementation (`Fn.ps`)**: Currying wrappers, partial application closures, pipeline forwarding, and list partitioning.
4. **The Transpiled Output (`micro_fn.py`)**: Emitting high-performance Python lambdas without extra function frame overhead.
5. **The Verification Test Harness (`run_fn.py`)**: Testing `curry_2`, `curry_3`, partials, composition, `take_while`, `drop_while`, and recursive flattening.

---

## 1. What is Functional Programming in Python?

Functional programming treats computation as the evaluation of mathematical functions, avoiding mutable state and side effects:

- **Currying**: Transforming a function that takes $N$ arguments into a chain of $N$ functions that each take 1 argument:
  $$\text{add}(a, b) \implies \text{curried\_add}(a)(b)$$
- **Partial Application**: Fixing a subset of arguments to produce a new function of smaller arity:
  $$\text{multiply}(2, x) \implies \text{double}(x)$$
- **Function Composition ($f \circ g$)**: Chaining functions so the output of $g$ becomes the input to $f$:
  $$(f \circ g)(x) = f(g(x))$$
- **Pipelines**: Passing data forward through a sequence of transformations:
  $$\text{Pipe}(x, f_1, f_2, f_3) \implies f_3(f_2(f_1(x)))$$

---

## 2. Project Layout

The project lives under [`Samples/Ported/13_micro_fn/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/13_micro_fn/):

```
Samples/Ported/13_micro_fn/
├── MicroFn.psproj       # Project configuration manifest
├── Fn.ps                # C# functional programming utility library
├── README.md            # Documentation and build instructions
├── run_fn.py            # Automated verification test suite
└── dist/
    └── micro_fn.py      # Transpiled pure Python 3.11 module
```

---

## 3. The C# Source Implementation: `Fn.ps`

In [`Fn.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/13_micro_fn/Fn.ps), notice how delegates and inline templates generate concise closures:

```csharp
namespace MicroFn;

using PythonSharp.Core;

public record PartitionResult(List<object> Matches, List<object> Rest);

public class Fn
{
    // Inline templates synthesizing direct Python closures
    [InlineTemplate("(lambda a: (lambda b: {0}(a, b)))")]
    private static extern object MakeCurry2(object fn);

    [InlineTemplate("(lambda a: (lambda b: (lambda c: {0}(a, b, c))))")]
    private static extern object MakeCurry3(object fn);

    [InlineTemplate("(lambda *rest: {0}({1}, *rest))")]
    private static extern object MakePartial(object fn, object arg1);

    [InlineTemplate("(lambda x: {0}({1}(x)))")]
    private static extern object MakeCompose(object f, object g);

    public static object Curry2(object fn)
    {
        return MakeCurry2(fn);
    }

    public static object Curry3(object fn)
    {
        return MakeCurry3(fn);
    }

    public static object Partial(object fn, object arg1)
    {
        return MakePartial(fn, arg1);
    }

    public static object Compose(object f, object g)
    {
        return MakeCompose(f, g);
    }

    public static object Pipe(object initialValue, object f1, object f2, object f3)
    {
        object v1 = Invoke1(f1, initialValue);
        object v2 = Invoke1(f2, v1);
        return Invoke1(f3, v2);
    }
```

### Stream Transducers: `TakeWhile` & `DropWhile`
```csharp
    public static List<object> TakeWhile(object predicate, List<object> items)
    {
        List<object> result = new List<object>();
        int i = 0;
        while (i < items.Count)
        {
            if (!TestPredicate(predicate, items[i]))
            {
                break;
            }
            result.Add(items[i]);
            i = i + 1;
        }
        return result;
    }

    public static PartitionResult Partition(object predicate, List<object> items)
    {
        List<object> matches = new List<object>();
        List<object> rest = new List<object>();
        int i = 0;
        while (i < items.Count)
        {
            if (TestPredicate(predicate, items[i]))
            {
                matches.Add(items[i]);
            }
            else
            {
                rest.Add(items[i]);
            }
            i = i + 1;
        }
        return new PartitionResult(matches, rest);
    }
```

---

## 4. The Transpiled Output: `micro_fn.py`

Compiling with:
```bash
psc build Samples/Ported/13_micro_fn -o Samples/Ported/13_micro_fn/dist
```
produces [`Samples/Ported/13_micro_fn/dist/micro_fn.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/13_micro_fn/dist/micro_fn.py).

### Emitted Python Snippet:
```python
# Auto-generated by PythonSharp (psc) — Bytecode line-pinned to Fn.ps
from __future__ import annotations
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class PartitionResult:
    __ps_types__ = ('MicroFn.PartitionResult',)
    matches: list[object]
    rest: list[object]

class Fn:
    __ps_types__ = ('MicroFn.Fn',)
    __slots__ = ()

    @staticmethod
    def curry_2(fn: object) -> object:
        return lambda a: lambda b: fn(a, b)

    @staticmethod
    def curry_3(fn: object) -> object:
        return lambda a: lambda b: lambda c: fn(a, b, c)

    @staticmethod
    def partial(fn: object, arg_1: object) -> object:
        return lambda *rest: fn(arg_1, *rest)

    @staticmethod
    def compose(f: object, g: object) -> object:
        return lambda x: f(g(x))

    @staticmethod
    def pipe(initial_value: object, f_1: object, f_2: object, f_3: object) -> object:
        v_1: object = f_1(initial_value)
        v_2: object = f_2(v_1)
        return f_3(v_2)
```

Look at how clean the output is:
- `curry_2` returns `lambda a: lambda b: fn(a, b)`
- `compose` returns `lambda x: f(g(x))`
- `pipe` directly invokes the functions in linear order with zero intermediate list allocations!

---

## 5. Verification Test Suite

[`run_fn.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/13_micro_fn/run_fn.py) verifies all functional combinators:

```python
# 1. Currying
def multiply(a, b): return a * b
curried_mult = Fn.curry_2(multiply)
assert curried_mult(6)(7) == 42

def add3(a, b, c): return a + b + c
curried_add = Fn.curry_3(add3)
assert curried_add(10)(20)(12) == 42

# 2. Partial application
double = Fn.partial(multiply, 2)
assert double(21) == 42

# 3. Composition: f ∘ g
def square(x): return x * x
def increment(x): return x + 1
inc_then_square = Fn.compose(square, increment) # square(increment(4)) = 25
assert inc_then_square(4) == 25

# 4. Pipeline
assert Fn.pipe(5, lambda x: x * 2, lambda x: x + 3, lambda x: f"Result: {x}") == "Result: 13"

# 5. TakeWhile & Partition
nums = [1, 2, 3, 4, 10, 2, 3]
assert Fn.take_while(lambda x: x < 5, nums) == [1, 2, 3, 4]

part = Fn.partition(lambda x: x % 2 == 0, [1, 2, 3, 4, 5, 6])
assert part.matches == [2, 4, 6]
assert part.rest == [1, 3, 5]
```

Running the runner:
```bash
python3 Samples/Ported/13_micro_fn/run_fn.py
```
Outputs:
```
=== Step 1: Building MicroFn via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported Fn Functionality ===
[PASS] Currying (curry_2 and curry_3) verified
[PASS] Partial application verified
[PASS] Function composition (f ∘ g) verified
[PASS] Pipeline forwarding verified
[PASS] TakeWhile and DropWhile verified
[PASS] Partition record (matches, rest) verified
[PASS] Recursive Flatten verified
[PASS] Functional primitives (Map, Filter, Reduce) verified

All micro-fn verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Closures Without Wrapper Overhead**: Emitting direct Python lambdas creates native closures with zero runtime libraries.
2. **First-Class Functions**: Passing functions as arguments and returning functions from functions works seamlessly across languages.
3. **Declarative Data Pipelines**: Combining `Pipe`, `TakeWhile`, and `Partition` enables functional programming in PythonSharp.

---

## Next Steps

Now let's explore extensible plugin architectures and hook specifications!

In **[Blog 22: Ported 14 — Micro-Pluggy (`14_micro_pluggy`): Hook Specifications, Plugins & Discovery](./22_ported_14_micro_pluggy_hook_specs_and_discovery.md)**, we examine how the hook system powering `pytest` was ported to PythonSharp!

