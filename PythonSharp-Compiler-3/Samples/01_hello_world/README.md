# Sample 01: Hello World & Direct Invocation

A minimal standalone PythonSharp program showing:
- Static methods and entrypoint (`Main`).
- String interpolation (`$"..."`).
- Direct execution with `psc run`.
- Import and interop from a standard Python script (`main.py`).

## Compilation & Execution

### 1. Execute directly with `psc run`
```bash
psc run Program.ps
```

### 2. Compile to Python and import from Python
```bash
# Compile to dist/
psc build Program.ps -o dist

# Run Python script
python3 main.py
```

