# Ported: `15_multimethod`

A multiple dispatch (multimethod) engine supporting multi-argument runtime type routing, subtype specificity (MRO), and ambiguous dispatch detection, ported to **PythonSharp** (`.ps`), compiling to clean Python 3.11+.

Ported from concepts in the `multimethod` library.

---

## Features

- **Multi-Argument Dynamic Dispatch**: Routes function invocations based on the full tuple of argument types `(typeof(A), typeof(B))`.
- **Subtype Specificity (MRO)**: Derived classes correctly match registered derived signatures over base classes; falls back to general base class signatures when specialized ones are absent.
- **Strict Error Detection**:
  - Missing signature errors reporting the exact unmatched type signature `('int', 'str')`.
  - Ambiguity errors when multiple candidate signatures are equally specific.
- **Callable Adaptor (`AsCallable`)**: Exposes the multimethod instance as a transparent Python callable function accepting `*args`.

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/15_multimethod -o Samples/Ported/15_multimethod/dist

# 2. Run the test harness
python3 Samples/Ported/15_multimethod/run_multimethod.py
```

