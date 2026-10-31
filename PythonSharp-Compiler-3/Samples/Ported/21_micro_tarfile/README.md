# Sample Port 21: MicroTarFile (Tier 8: Systems & Resources)

A ported, strongly-typed PythonSharp implementation of the **POSIX USTAR** binary TAR archive format, exercising the `Bytes` primitive, binary structs, fixed-offset byte slices, checksum validation, and bi-directional compatibility with Python's standard `tarfile` module.

## Architectural Highlights
- **Zero Runtime Wrapper Tax**: Binary byte operations compile directly to Python 3.11+ byte slicing, byte concatenation, and ASCII conversions.
- **512-Byte Block Alignment**: Fully implements POSIX USTAR 512-byte header encoding, octal numerical serialization, and block padding.
- **Bi-Directional Parity**:
  - Archives written by `MicroTarArchive` are fully readable by Python's standard `tarfile.open()`.
  - Archives created by standard `tarfile` can be parsed and extracted by `MicroTarArchive.ReadArchive()`.

## Features
- `TarEntry`: Immutable record representing an archived file member.
- `TarHeader`:
  - `CreateHeader(string name, long size, int mode = 420)`
  - `CalculateChecksum(Bytes headerBlock)`
  - `DecodeAsciiString(Bytes data, int offset, int length)`
  - `ParseOctal(string octalStr)`
- `MicroTarArchive`:
  - `CreateArchive(List<TarEntry> entries) -> Bytes`
  - `ReadArchive(Bytes archiveData) -> List<TarEntry>`
  - `FindEntry(List<TarEntry> entries, string name) -> TarEntry?`

## Compilation & Verification

```bash
# 1. Compile via PythonSharp compiler
psc build . -o dist

# 2. Run the automated test runner
python3 run_tarfile.py
```

