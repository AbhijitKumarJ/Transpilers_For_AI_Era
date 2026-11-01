# 02_slugify — PythonSharp Ported Library

Ported implementation of the standard URL slug generator library `python-slugify` in PythonSharp.

## Features
- `Slugifier.Slugify(string text, string separator = "-", bool lowercase = true)`
- Strips special characters, collapses consecutive separators, and trims edges.
- Supports custom separators and case retention.
- Exercises ternary conditional expressions (`? :`) and zero-overhead string methods.

## Compiling and Running

```bash
# 1. Compile with PythonSharp compiler
psc build .

# 2. Run verification test harness
python3 run_slugify.py
```

