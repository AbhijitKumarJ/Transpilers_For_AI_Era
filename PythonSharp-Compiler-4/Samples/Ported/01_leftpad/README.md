# 01_leftpad — PythonSharp Ported Library

Ported implementation of the classic string padding utility `left-pad` / `pad-left` in PythonSharp.

## Features
- `PadUtil.LeftPad(string str, int len, string ch = " ")`
- `PadUtil.RightPad(string str, int len, string ch = " ")`
- `PadUtil.Center(string str, int len, string ch = " ")`
- Zero external runtime dependencies.
- Native integer division and builtin shadowing avoidance.

## Compiling and Running

```bash
# 1. Compile with PythonSharp compiler
psc build .

# 2. Run verification test harness
python3 run_leftpad.py
```

