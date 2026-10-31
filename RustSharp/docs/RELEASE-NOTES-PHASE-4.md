# RustSharp Phase 4 Release Notes: Rust Metaprogramming, Attributes & Async Ecosystem

**Release Date:** 2026-10-30  
**Status:** Complete & Verified (`cargo test` 37/37 passed across 10 suites; `cargo clippy` 0 warnings; `cargo fmt` clean)

---

## 1. Overview

Phase 4 bridges C#'s expressive metaprogramming and asynchronous programming patterns directly into the modern Rust ecosystem. It introduces first-class lowering for:
1. **Serde Serialization:** Translating C# JSON attributes (`[JsonPropertyName]`, `[JsonIgnore]`, `[JsonRequired]`) into native `#[serde(...)]` field annotations and injecting `#[derive(serde::Serialize, serde::Deserialize)]`.
2. **Async/Await & Futures:** Unwrapping `async Task<T>` and `async ValueTask<T>` into native Rust `pub async fn ... -> T` (and `-> Result<T, E>` when fallible with `throws E`), while lowering `await expr` cleanly into `.await?`.
3. **Async Streams:** Lowering `IAsyncEnumerable<T>` into native Rust asynchronous streams (`impl futures_core::Stream<Item = T>`).
4. **Web Routing (ASP.NET $\rightarrow$ Axum):** Mapping controller attributes (`[HttpGet]`, `[HttpPost]`, `[HttpPut]`, `[HttpDelete]`, `[Route]`) to native `#[axum::routing::*]` macros and binding `[FromBody]`, `[FromRoute]`, and `[FromQuery]` parameter extractors to `axum::extract::*`.
5. **Zero-Config Cargo Dependency Discovery:** Automatically discovering when `.rsharp` code utilizes Serde, Axum, or Tokio, and synchronizing these dependencies directly into the synthesized `Cargo.toml`.

---

## 2. Key Deliverables & Enhancements

### 2.1 Serde Attribute Lowering (`src/codegen/rs_ast_emitter.rs`)
- **Derive Synthesis:** Records, structs, and enums decorated with serialization attributes automatically receive `#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]`.
- **Field & Property Annotations:**
  - `[JsonPropertyName("id")]` $\rightarrow$ `#[serde(rename = "id")]`
  - `[JsonIgnore]` $\rightarrow$ `#[serde(skip)]`
  - `[JsonRequired]` $\rightarrow$ `#[serde(default)]`
- Supported across both primary constructor parameters (e.g. `record User([JsonPropertyName("uid")] int Id)`) and explicit struct fields/properties.

### 2.2 Async/Await Lowering & Task Unwrapping
- In `format_method_return_type`, methods marked `is_async` automatically unwrap:
  - `Task<T>` / `ValueTask<T>` $\rightarrow$ `T` (or `Result<T, E>` if marked `throws E`).
  - `Task` / `ValueTask` $\rightarrow$ `()` (or `Result<(), E>`).
- In `src/codegen/expr_emitter.rs`, `await expr` expressions lower to `{inner}.await?` when calling fallible async functions, ensuring the Future is awaited first before the `Result` is unwrapped with `?`.

### 2.3 Async Streams (`IAsyncEnumerable<T>`)
- Added ambient contract `IAsyncEnumerable<T>` in `stdlib/RustSharp.Core.d.rsharp`.
- Lowered in `format_rust_owned_type` to `impl futures_core::Stream<Item = T>`.

### 2.4 Web Framework Interop (Axum Lowering)
- Supported attributes: `[HttpGet("path")]`, `[HttpPost("path")]`, `[HttpPut("path")]`, `[HttpDelete("path")]`, `[Route("path")]`.
- Implemented `csharp_route_to_axum`: Converts ASP.NET route template syntax `{param}` to Axum syntax `:param` (e.g. `"/api/orders/{customerId}/{orderId}"` $\rightarrow$ `"/api/orders/:customerId/:orderId"`).
- Parameter extractors:
  - `[FromBody]` $\rightarrow$ `axum::extract::Json<T>`
  - `[FromRoute]` $\rightarrow$ `axum::extract::Path<T>`
  - `[FromQuery]` $\rightarrow$ `axum::extract::Query<T>`
  - Correctly selects owned type representations (`T`) for extractors.

### 2.5 Automated Dependency Discovery
- In `src/bindgen/cargo_sync.rs`, added automated detection for:
  - Serde attributes $\rightarrow$ `serde = "1.0"`
  - Axum attributes $\rightarrow$ `axum = "0.7"`
  - Async methods $\rightarrow$ `tokio = "1.0"`

---

## 3. Verification Metrics

- **`cargo fmt --check`:** Clean (0 differences).
- **`cargo clippy --all-targets -- -D warnings`:** Clean (0 warnings).
- **`cargo test`:** 37/37 passed across 10 test suites (100% success rate in 3.11s).
- **Zero External Dependencies:** Maintained 100% pure standard library Rust (`std`) for the compiler host.

