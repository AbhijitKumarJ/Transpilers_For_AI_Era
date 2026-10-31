# RustSharp Examples & Running Guide

This directory contains real-world example projects and dogfooding test suites demonstrating RustSharp language features, zero-runtime GC elimination, borrow inference, and native Rust interop.

---

## Prerequisites

Build the `rsharpc` release compiler binary from the repository root:

```bash
cargo build --release
```

The binary will be located at `./target/release/rsharpc`.

---

## 1. Running Executable Examples

The `rsharpc run` command transpiles `.rsharp` and co-located `.rs` files into a standard Cargo workspace, compiles the native Rust code, and executes the binary immediately.

### Example 09: Native Interop Crypto (MurmurHash3 & Constant-Time Verification)
Combines high-level C# services with raw Rust low-level hashing and constant-time equality routines.

```bash
./target/release/rsharpc run examples/09_native_interop_crypto/CryptoProject.rsproj
```
**Expected Output:**
```text
[CryptoProject] MurmurHash3 digest: 3382513890
[CryptoProject] Verification passed: true
```

### Example 10: 2D Game Physics Engine
Demonstrates linear resource ownership, zero-cost value structs (`Vector2`), and co-located raw Rust SIMD-style distance and AABB overlap detection.

```bash
./target/release/rsharpc run examples/10_game_physics_engine/PhysicsEngine.rsproj
```
**Expected Output:**
```text
[PhysicsEngine] Testing collision before adding bodies...
[PhysicsEngine] Initial collision: false
[PhysicsEngine] Simulation step complete!
```

### Example 11: Concurrent Database Layer
Demonstrates a document database combining C# domain records with a thread-safe raw Rust `RwLock<Option<BTreeMap<String, u64>>>` index.

```bash
./target/release/rsharpc run examples/11_mixed_database_layer/DatabaseLayer.rsproj
```
**Expected Output:**
```text
[DatabaseLayer] Stored document 'user_42' with native BTree indexing.
[DatabaseLayer] BTree index contains 'user_42': true
[DatabaseLayer] BTree index contains 'user_99': false
```

---

## 2. Running Ported Ecosystem Libraries (01 – 08)

For library crates without a `static void Main()` entry point, `rsharpc run` automatically runs `cargo test` against the synthesized crate:

```bash
# Text Slugification & String Processing
./target/release/rsharpc run examples/01_slugify/Slugify.rsproj

# Levenshtein Edit-Distance Dynamic Programming
./target/release/rsharpc run examples/02_levenshtein/Levenshtein.rsproj

# Pure-Rust SHA-256 Bitwise Cryptography
./target/release/rsharpc run examples/03_crypto_sha256/CryptoSha256.rsproj

# Arbitrary-Precision BigInteger Math
./target/release/rsharpc run examples/04_big_integer/BigInteger.rsproj

# Recursive-Descent JSON Lexer and Parser
./target/release/rsharpc run examples/05_json_parser/JsonParser.rsproj

# Reflection-Free Zero-Allocation JSON Serializer
./target/release/rsharpc run examples/06_json_serializer/JsonSerializer.rsproj

# HTTP Client Model (Reqwest Interop)
./target/release/rsharpc run examples/07_http_client/HttpClient.rsproj

# Axum REST Microservice with Routing Attributes
./target/release/rsharpc run examples/08_rest_service/RestService.rsproj
```

---

## 3. CLI Command Reference

| Command | Purpose | Example |
| :--- | :--- | :--- |
| **`rsharpc run`** | Transpile, build, and run the binary or tests | `./target/release/rsharpc run examples/09_native_interop_crypto/CryptoProject.rsproj` |
| **`rsharpc check`** | Fast in-memory Pass 1–2.5 type & borrow check | `./target/release/rsharpc check examples/01_slugify/Slugify.rsproj` |
| **`rsharpc build`** | Synthesize Cargo crate and run `cargo check` | `./target/release/rsharpc build examples/10_game_physics_engine/PhysicsEngine.rsproj` |
| **`rsharpc emit-rs`** | Emit Rust crate & `.rsharp.map` files to disk | `./target/release/rsharpc emit-rs examples/11_mixed_database_layer/DatabaseLayer.rsproj` |
| **`rsharpc watch`** | Recompile automatically on file changes | `./target/release/rsharpc watch examples/09_native_interop_crypto/CryptoProject.rsproj` |
| **`rsharpc lsp`** | Launch Language Server (used by VS Code) | `./target/release/rsharpc lsp` |

---

## 4. Running Native Cargo Directly

Every time `rsharpc build` or `rsharpc run` is invoked, it synthesizes a 100% native Rust workspace in `<project_dir>/target/rsharp_synth/`:

```bash
# Navigate to the synthesized Rust crate
cd examples/09_native_interop_crypto/target/rsharp_synth

# Inspect the emitted Rust source code
cat src/lib.rs
cat src/security/crypto.rs
cat src/main.rs

# Execute directly using native Cargo
cargo run
cargo test
cargo clippy
```

---

## 5. How to Write an Executable RustSharp Project

To make any `.rsharp` project executable, declare a class containing a `static void Main()` method:

```csharp
namespace Security.Crypto;

public class Program {
    public static void Main() {
        var svc = new CryptoService(1337);
        var result = svc.HashKey(42);
        Console.WriteLine($"[CryptoProject] MurmurHash3 digest: {result.Digest}");
        var isValid = svc.VerifyKey(42, result.Digest);
        Console.WriteLine($"[CryptoProject] Verification passed: {isValid}");
    }
}
```

The `rsharpc` compiler automatically:
1. Lowers `Console.WriteLine` to Rust's native `println!("{}", ...)` with zero runtime overhead.
2. Expands interpolated strings `$"{expr}"` into Rust `format!("...", expr)`.
3. Synthesizes `src/main.rs` that calls `Program::main()`.
4. Runs `cargo run` when executing `rsharpc run`.

