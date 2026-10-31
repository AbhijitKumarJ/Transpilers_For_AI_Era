# Sample Port 18: MicroShutil (Tier 8: Systems & Resources)

A ported, strongly-typed PythonSharp implementation of high-level filesystem tree and directory management inspired by Python's `shutil` and `os.path`.

## Architectural Highlights
- **Zero Runtime Wrapper Tax**: All calls to `ShutilEngine` lower directly to Python 3.11+ AST calls into standard `os.path`, `os`, and `shutil`.
- **Recursive Tree Traversal**: Implements `ScanTree` and `FindFilesWithExtension` with recursion, list aggregation, and strongly-typed data records.
- **Records with Slotted Footprint**: `PathMetadata` and `TreeStats` transpile to Python `@dataclass(slots=True, frozen=True)`.

## Features
- `CombinePaths`, `CombineThreePaths`
- `Exists`, `IsFile`, `IsDirectory`
- `EnsureDirectory`, `CopyFile`, `MoveFile`, `DeleteFile`
- `CopyTree`, `RemoveTree`, `ListContents`
- `GetMetadata`, `ScanTree`, `FindFilesWithExtension`

## Compilation & Verification

```bash
# 1. Compile via PythonSharp compiler
psc build . -o dist

# 2. Run the automated test runner
python3 run_shutil.py
```

