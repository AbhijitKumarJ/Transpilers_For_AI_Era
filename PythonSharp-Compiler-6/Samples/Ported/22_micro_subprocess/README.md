# Sample Port 22: MicroSubprocess (Tier 8: Systems & Resources)

A ported, strongly-typed PythonSharp implementation of native operating system process execution, standard stream capturing, and stdin piping inspired by Python's `subprocess` module.

## Architectural Highlights
- **Zero Runtime Wrapper Tax**: Compiles directly to Python 3.11+ `subprocess.run` calls without intermediate wrapper scripts or synthetic bridge layers.
- **Process Boundaries & IPC**: Full support for argument vectors, exit status tracking, stdout/stderr isolation, and standard input piping.
- **Slotted Data Records**: `ProcessOutput` transpiles to `@dataclass(slots=True, frozen=True)` for minimal memory footprint.

## Features
- `Execute(List<string> args) -> ProcessOutput`: Runs command capturing stdout/stderr without throwing on failure.
- `ExecuteWithStdin(List<string> args, string inputData) -> ProcessOutput`: Pipes text payload into subprocess stdin.
- `ExecuteAndCaptureStdout(List<string> args) -> string`: Runs command and returns trimmed stdout.
- `CheckSuccess(List<string> args) -> bool`: Convenience guard returning whether process exited with code 0.
- `ParseLines(string outputText) -> List<string>`: Splits stdout into trimmed non-empty line collections.

## Compilation & Verification

```bash
# 1. Compile via PythonSharp compiler
psc build . -o dist

# 2. Run the automated test runner
python3 run_subprocess.py
```

