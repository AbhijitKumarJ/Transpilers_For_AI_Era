# PythonSharp Diagnostics

**Status:** Phases 1–5 & Triple-Surface Catalog
**Last updated:** 2026-10-31
**Related docs:** [LANGUAGE-SPEC.md](LANGUAGE-SPEC.md), [ARCHITECTURE.md](ARCHITECTURE.md), [TESTING.md](TESTING.md)

## 1. Overview

`psc` reports diagnostics with a stable code, a severity, a source span, and an
actionable message. Compilation accumulates diagnostics across files, sorts them,
and stops before code generation when any error is present.

The current diagnostic catalog:

| Code | Name | Severity |
| --- | --- | --- |
| `PS000` | Syntax or structural error | ERROR |
| `PS001` | Encapsulation or readonly-access violation | ERROR |
| `PS002` | Ambiguous runtime overload | ERROR |
| `PS003` | Circular static initialization | ERROR |
| `PS004` | Invalid `[NativeCompile]` dynamic construct | ERROR |
| `PS005` | Target surface migration recommendation | WARNING |

Warning-severity diagnostics use the same format and do not halt compilation. `PS005` emits actionable migration recommendations when code references APIs below the targeted enterprise tier.

## 2. Diagnostic model

```python
@dataclass(frozen=True, slots=True)
class SourceSpan:
    file_id: int
    ps_filename: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int

@dataclass(slots=True)
class Diagnostic:
    code: str
    severity: Literal["ERROR", "WARNING"]
    message: str
    span: SourceSpan
    hint: str | None = None
```

- `ps_filename` is the path shown to the user, relative to the project root where
  possible.
- `file_id` identifies the compilation unit within a single build.
- Line and column are 1-indexed.
- `end_line`/`end_col` allow editors to underline the full construct. The CLI
  currently prints the start position.
- `hint` provides an actionable suggestion or fix guidance when available.
- A diagnostic is immutable with respect to its code, severity, message, and span.

## 3. Human-readable format

Canonical form:

```text
{SEVERITY} [{CODE}] at {file}:{line}:{column}: {message} [(Hint: {hint})]
```

Examples:

```text
ERROR [PS001] at Domain/Order.ps:19:9: Member 'OrderCache.AuditTag.set' is 'private' and cannot be accessed from this context. (Hint: Expose 'AuditTag.set' with 'public' or 'internal' visibility, or access it from within 'OrderCache'.)
ERROR [PS002] at Services/Batch.ps:17:9: Overloads 'Process(List<int>)' and 'Process(List<string>)' on 'Process' erase to identical Python runtime type 'list' at the same arity. (Hint: Rename one overload, change parameter arity, or wrap the 'list' argument in a distinct record.)
ERROR [PS003] at Config/App.ps:12:9: Circular static initializer cycle detected: Config.Default -> Env.Current -> Config.Default (Hint: Break the initialization cycle using a lazy property, method call, or local factory.)
ERROR [PS004] at Math/FastMatrix.ps:34:9: Type 'FastMatrix' is marked [NativeCompile] and cannot use 'dynamic'. (Hint: Replace 'dynamic' with a concrete static type, interface, generic parameter, or 'object'.)
ERROR [PS000] at Domain/Order.ps:8:5: Expected ';' after field declaration.
```

The CLI writes errors to stderr and normal build summaries to stdout.

## 4. Severity behavior

| Severity | Effect |
| --- | --- |
| `ERROR` | Compilation fails; no artifacts are emitted |
| `WARNING` | Compilation may continue; artifacts may be emitted |

`check` reports errors without emitting. `build` and `run` require a clean
analysis phase.

## 5. Ordering and deduplication

- Diagnostics are sorted by `ps_filename`, `start_line`, `start_col`, then `code`.
- Identical `(code, span, message)` tuples are emitted once.
- Multiple independent errors in one file are retained, not collapsed.
- The order is deterministic across runs.

## 6. Code catalog

### PS000 - Syntax or structural error

**Triggered by**

- Unexpected token or missing delimiter.
- Unterminated string or block comment.
- Invalid declaration shape, malformed attribute, or unsupported construct.
- Duplicate declarations or namespace path collisions detected during structural
  validation.
- A bare `throw;` used outside a catch handler.
- Project configuration errors that are not usage errors.

**Example**

```text
ERROR [PS000] at Domain/Order.ps:8:5: Expected ';' after field declaration.
```

**Recovery**

The parser skips to the next statement boundary (`;`, `}`, or declaration
keyword) and continues. Pass 1-2 errors are reported after parsing completes.

**Fix**

Correct the syntax or declaration shape at the reported span. When a construct is
outside the supported subset, the message names the unsupported construct rather
than reporting a generic parse failure.

### PS001 - Encapsulation or readonly-access violation

**Triggered by**

- Reading a `private` member outside its declaring type.
- Writing a `private` property setter outside its declaring type.
- Accessing a `protected` member from a non-derived type.
- Accessing an `internal` member from another `.psproj` assembly.
- Assigning a `readonly` field outside its constructor or declaration.
- Illegal cross-assembly access to a member whose accessor has narrower visibility
  than its containing property.

**Example**

```text
ERROR [PS001] at Checkout.ps:19:9: Member 'OrderCache.AuditTag.set' is 'private' and cannot be accessed from this context.
```

**Notes**

- Access control is compile-time only. Emitted Python does not raise at runtime
  for a violation that the compiler missed.
- Property getter and setter visibility are checked independently.
- The diagnostic points at the access site, not the declaration.

**Fix**

Use a public operation, add a public accessor, or move the call into the declaring
type or assembly as appropriate.

### PS002 - Ambiguous runtime overload

**Triggered by**

- Two methods or constructors share a name and arity.
- Their parameter types erase to the same runtime `isinstance` signature.
- Example: `Process(List<int>)` and `Process(List<string>)` both erase to `list`.
- Example: `Load(int)` and `Load(bool)` must remain distinguishable because `bool`
  is a subclass of `int`; the dispatcher orders `bool` first.

**Example**

```text
ERROR [PS002] at Services/Batch.ps:17:9: Overloads 'Process(List<int>)' and 'Process(List<string>)' on 'Process' erase to identical Python runtime type 'list' at the same arity.
```

**Notes**

- Overloads that differ only by generic arguments are not runtime-distinguishable.
- `float`/`double` accept `int` at runtime when no exact match exists; this
  widening is deterministic and must not create an ambiguous pair.
- Optional parameters and `params` expansions participate in arity analysis.

**Fix**

Rename one overload, change arity, or use distinct nominal wrapper records for
types that erase to the same Python type.

### PS003 - Circular static initialization

**Triggered by**

- Two or more static field or property initializers depend on each other at module
  load time.
- The dependency graph contains a cycle reachable from module initialization.

**Example**

```text
ERROR [PS003] at Config/App.ps:12:9: Circular static initializer cycle detected: Config.Default -> Env.Current -> Config.Default
```

**Notes**

- Circular **type** references across files are legal and resolved by Pass 1.
- Only runtime value initialization cycles are errors.
- Lazy initialization or explicit factory methods can break a cycle.

**Fix**

Remove the cycle, initialize one side lazily, or move the value into a function
that is called after module import.

### PS004 - Invalid `[NativeCompile]` dynamic construct

**Triggered by**

- A class marked `[NativeCompile]` declares or uses `dynamic` in:
  - a field or property type,
  - a method or constructor parameter,
  - a local variable.

**Example**

```text
ERROR [PS004] at Math/FastMatrix.ps:34:9: Type 'FastMatrix' is marked [NativeCompile] and cannot use 'dynamic'.
```

**Notes**

- The check runs in Pass 2A before type erasure.
- `[NativeCompile]` code generation is a Phase 5 feature, but the restriction is
  enforced as soon as the attribute is recognized.
- Use a concrete type or `object` with an explicit conversion at the boundary.

**Fix**

Replace `dynamic` with a statically known type inside the native-compiled type.

### PS005 - Target surface migration recommendation

**Triggered by**

- Code compiled with `--target-surface <level>` (or project configuration) references a symbol or namespace whose `surface_level` is lower than the target (e.g. referencing Surface 1 `PythonSharp.Raw.*` or Surface 2 `PythonSharp.Bridge.*` when compiling with `--target-surface 3`).

**Example**

```text
WARNING [PS005] at Checkout.ps:14:22: Symbol 'Time.Time' is a Surface 2 API; project targets Surface 3. (Hint: Migrate to 'PythonSharp.Diagnostics.Stopwatch.GetTimestamp' to comply with targeted enterprise Surface 3.)
```

**Notes**

- Emitted as a `WARNING` severity diagnostic; it informs the developer and LSP editor tooling without failing the build.
- Suggests the canonical alternative registered via `[CanonicalApi]`.

**Fix**

Upgrade the import or invocation to the recommended canonical Surface 3 enterprise API.

## 7. Reserved codes

Codes `PS006` and above are unassigned. Reserved ranges:

| Range | Intended use |
| --- | --- |
| `PS006`-`PS049` | Language and semantic errors |
| `PS050`-`PS099` | Project, configuration, and build errors |
| `PS100`-`PS199` | Bindgen and interop errors (Phase 3) |
| `PS200`-`PS299` | Tooling, LSP, and native compilation (Phase 5) |

New codes require:

1. A definition in this document.
2. A positive and negative test.
3. A documented remediation.
4. A decision-log entry if the code changes an existing contract.

## 8. CLI behavior and exit codes

| Exit code | Meaning |
| --- | --- |
| `0` | Success; no error diagnostics |
| `1` | Compilation, project discovery, or input error |
| `2` | CLI usage error reported by `argparse` |

- `check`: prints `Check succeeded: N .ps file(s) verified with 0 errors.` on success.
- `build`: prints the output directory and module count on success.
- `run`: reports the entrypoint result or propagates the program's exit status.
- `dump-ast`: prints lowered Python source and does not write artifacts.

## 9. JSON diagnostics (planned)

A future `--json` mode will emit one object per diagnostic with stable fields:

```json
{
  "code": "PS001",
  "severity": "ERROR",
  "message": "Member 'OrderCache.AuditTag.set' is 'private' and cannot be accessed from this context.",
  "file": "Checkout.ps",
  "start_line": 19,
  "start_column": 9,
  "end_line": 19,
  "end_column": 32
}
```

The schema must remain backward compatible within a major version. JSON mode is
not a Phase 1 release requirement.

## 10. Testing requirements

Every diagnostic code must have:

- a minimal positive trigger with an asserted code;
- a negative case that compiles cleanly;
- an asserted span (file, line, column);
- an asserted message shape or snapshot;
- a CLI integration test asserting exit code `1`;
- deterministic ordering when multiple diagnostics are present.

Tests live in the milestone suites (`test_lexer_parser.py`,
`test_access_and_slots.py`, `test_overloads_and_linq.py`) and in end-to-end CLI
tests. See [TESTING.md](TESTING.md).
