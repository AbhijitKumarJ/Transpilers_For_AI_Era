# Ported: `13_micro_fn`

A functional programming toolkit bringing first-class function combinators, partial application, currying, function composition, and stream operations to **PythonSharp** (`.ps`), compiling to clean Python 3.11+.

Ported from concepts in the `fn.py` library.

---

## Features

- **Higher-Order Combinators**:
  - `Curry2(fn)` / `Curry3(fn)`: Converts multi-parameter functions into single-argument chains (`f(a)(b)`)
  - `Partial(fn, arg)` / `Partial2(fn, a, b)`: Pre-binds leading arguments with varargs support
  - `Compose(f, g)`: Mathematical function composition $(f \circ g)(x) = f(g(x))$
  - `Pipe(value, [f, g, h])`: Forward pipeline feeding initial values sequentially through transformations
- **Sequence Processing**:
  - `TakeWhile(predicate, items)`: Evaluates elements while a condition remains true
  - `DropWhile(predicate, items)`: Discards leading elements matching a predicate, returning the tail
  - `Partition(predicate, items)`: Splits a list into matched and rejected items packaged as a `PartitionResult` record
  - `Flatten(nestedList)`: Recursively unrolls arbitrarily nested lists
- **Functional Core**:
  - `Map(transform, items)`
  - `Filter(predicate, items)`
  - `Reduce(reducer, items, initial)`

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/13_micro_fn -o Samples/Ported/13_micro_fn/dist

# 2. Run the test harness
python3 Samples/Ported/13_micro_fn/run_fn.py
```

