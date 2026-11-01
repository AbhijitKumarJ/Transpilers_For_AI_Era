# Ported 05: SemVer (Semantic Versioning 2.0.0)

A ported version of the `semver` Python library implemented cleanly in PythonSharp (`.ps`). Demonstrates C# 9+ records with primary constructors, string manipulation, numeric parsing (`Int32.Parse`), and SemVer 2.0.0 precedence comparison rules.

## Project Structure

- `SemVer.psproj`: PythonSharp project file specifying assembly `SemVerUtil` and target `py3.11`.
- `SemanticVersion.ps`: Core implementation of `SemVer` record with parsing and comparison methods.
- `run_semver.py`: Verification script that compiles the project via `psc build` and runs canonical SemVer 2.0.0 precedence tests.

## Features

- **SemVer Record**: `SemVer(int Major, int Minor, int Patch, string Prerelease = "", string Build = "")`
- **Parsing**: `SemVer.Parse("1.2.3-alpha.1+build.42")` supporting core, pre-release, and build metadata.
- **Precedence**: Full SemVer 2.0.0 precedence ordering (numeric comparison for numeric identifiers, lexical comparison for alphanumeric identifiers, pre-release precedence over normal versions, build metadata ignored).
- **Caret Compatibility**: `SemVer.IsCompatibleWith(...)` checking compatibility according to SemVer rules.

## How to Build and Run

```bash
# Build the PythonSharp project
psc build Samples/Ported/05_semver

# Run the test suite
python3 Samples/Ported/05_semver/run_semver.py
```

