# Sample 04: Native Python Interoperability with `ps-bindgen`

Demonstrates:
- Creating ambient `.d.ps` declarations from Python `.pyi` type stubs via `psc bindgen`.
- Using `extern using native_text as NativeText;` in PythonSharp to import native Python modules.
- Writing strongly typed C# code that calls native Python methods at full native speed.
- Zero runtime wrapper tax: no synthetic bridge or wrapper objects.

## Compilation & Execution

### 1. Generate ambient stubs from `.pyi` (already generated in `stubs/`)
```bash
psc bindgen native_text.pyi -o stubs --root-namespace Extern
```

### 2. Compile PythonSharp project
```bash
psc build . -o dist
```

### 3. Run the integrated Python script
```bash
python3 run_interop.py
```

