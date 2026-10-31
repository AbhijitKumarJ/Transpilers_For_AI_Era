# 04_levenshtein — PythonSharp Ported Library

Ported implementation of the standard Levenshtein edit distance and similarity ratio algorithm in PythonSharp.

## Features
- `Levenshtein.Distance(string s1, string s2)`: Dynamic programming matrix calculation of minimum insertion, deletion, and substitution cost.
- `Levenshtein.Ratio(string s1, string s2)`: Normalized similarity ratio score between $0.0$ and $1.0$.
- Two-row rolling matrix optimization for memory efficiency.

## Compiling and Running

```bash
# 1. Compile with PythonSharp compiler
psc build .

# 2. Run verification test harness
python3 run_levenshtein.py
```

