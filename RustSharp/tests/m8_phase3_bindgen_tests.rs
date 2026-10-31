//! Phase 3: Cargo Ecosystem Bridge (`rsharp-bindgen`) Verification Suite.
//!
//! Tests for:
//! 1. Rust tokenizer and recursive-descent item parser (`RsLexer`, `RsParser`).
//! 2. Cargo crate directory analyzer & submodule discovery (`CrateAnalyzer`).
//! 3. Ambient `.d.rsharp` header synthesis (`StubGenerator`).
//! 4. Automatic `Cargo.toml` dependency synchronization (`CargoDependencySynchronizer`).

use std::path::Path;

use rsharpc::bindgen::{
    generate_crate_header, CargoDependencySynchronizer, CrateAnalyzer, RsLexer, RsParser,
    RustSelfReceiver, RustType, StubGenerator,
};
use rsharpc::codegen::CargoWorkspaceSynthesizer;
use rsharpc::diagnostics::DiagnosticEngine;
use rsharpc::parse_source_str;
use rsharpc::project::RsProjConfig;

#[test]
fn test_bindgen_single_source_file_parsing() {
    let rs_src = r#"
/// Geographic coordinate in decimal degrees.
pub struct GeoPoint {
    pub latitude: f64,
    pub longitude: f64,
    elevation: f64,
}

/// Directional compass orientation.
pub enum Direction {
    North,
    South,
    East,
    West,
}

impl GeoPoint {
    /// Creates a new geographic point.
    pub fn new(lat: f64, lon: f64) -> Self {
        Self { latitude: lat, longitude: lon, elevation: 0.0 }
    }

    /// Moves point by delta offsets.
    pub fn shift(&mut self, d_lat: f64, d_lon: f64) {
        self.latitude += d_lat;
        self.longitude += d_lon;
    }

    /// Computes distance to another point.
    pub fn distance_to(&self, other: &GeoPoint) -> Result<f64, String> {
        Ok(42.0)
    }
}

/// Computes midpoint between two coordinates.
pub fn calculate_midpoint(a: &GeoPoint, b: &GeoPoint) -> GeoPoint {
    GeoPoint::new((a.latitude + b.latitude) / 2.0, (a.longitude + b.longitude) / 2.0)
}
"#;

    let mut lexer = RsLexer::new(rs_src);
    let tokens = lexer.tokenize();
    let mut parser = RsParser::new(tokens);
    let module = parser.parse_module("geo");

    // Assert struct
    assert_eq!(module.structs.len(), 1);
    let st = &module.structs[0];
    assert_eq!(st.name, "GeoPoint");
    assert!(st.is_pub);
    assert_eq!(st.fields.len(), 3);
    assert_eq!(st.fields[0].name, "latitude");
    assert!(st.fields[0].is_pub);
    assert!(!st.fields[2].is_pub); // elevation is private

    // Assert enum
    assert_eq!(module.enums.len(), 1);
    let en = &module.enums[0];
    assert_eq!(en.name, "Direction");
    assert_eq!(en.variants.len(), 4);
    assert_eq!(en.variants[0].name, "North");

    // Assert impl methods
    assert_eq!(module.impls.len(), 1);
    let im = &module.impls[0];
    assert_eq!(im.target_type, "GeoPoint");
    assert_eq!(im.methods.len(), 3);

    let m_new = &im.methods[0];
    assert_eq!(m_new.name, "new");
    assert_eq!(m_new.self_receiver, None);
    assert_eq!(m_new.return_type, RustType::SelfType);

    let m_shift = &im.methods[1];
    assert_eq!(m_shift.name, "shift");
    assert_eq!(m_shift.self_receiver, Some(RustSelfReceiver::MutRef));

    let m_dist = &im.methods[2];
    assert_eq!(m_dist.name, "distance_to");
    assert_eq!(m_dist.self_receiver, Some(RustSelfReceiver::Ref));
    assert!(m_dist.return_type.is_result());

    // Assert free function
    assert_eq!(module.functions.len(), 1);
    assert_eq!(module.functions[0].name, "calculate_midpoint");
}

#[test]
fn test_bindgen_ambient_stub_generation() {
    let rs_src = r#"
pub struct TokenBucket {
    pub capacity: u32,
    tokens: u32,
}

impl TokenBucket {
    pub fn new(capacity: u32) -> Self {
        Self { capacity, tokens: capacity }
    }

    pub fn try_acquire(&mut self, amount: u32) -> Result<bool, String> {
        Ok(true)
    }

    pub fn current_tokens(&self) -> u32 {
        self.tokens
    }
}

pub fn reset_all() -> Result<(), String> {
    Ok(())
}
"#;

    let mut lexer = RsLexer::new(rs_src);
    let tokens = lexer.tokenize();
    let mut parser = RsParser::new(tokens);
    let module = parser.parse_module("limiter");

    let crate_info = rsharpc::bindgen::RustCrateInfo {
        name: "rate_limiter".to_string(),
        version: "1.4.0".to_string(),
        root_dir: std::path::PathBuf::from("."),
        root_module: module,
        dependencies: Vec::new(),
    };

    let stub = StubGenerator::generate(&crate_info, Some("RateLimiter"));

    assert!(stub.contains("[assembly: CrateDependency(\"rate_limiter\", \"1.4.0\")]"));
    assert!(stub.contains("namespace RateLimiter"));
    assert!(stub.contains("[MapsTo(\"rate_limiter::TokenBucket\")]"));
    assert!(stub.contains("public class TokenBucket")); // has mutating method -> service class archetype
    assert!(stub.contains("public uint Capacity;"));
    assert!(stub.contains("[MapsTo(\"new\")]"));
    assert!(stub.contains("public TokenBucket(uint capacity);"));
    assert!(stub.contains("[Borrow(BorrowKind.MutBorrow)]"));
    assert!(stub.contains("[MapsTo(\"try_acquire\")]"));
    assert!(stub.contains("public bool TryAcquire(uint amount) throws string;"));
    assert!(stub.contains("[MapsTo(\"current_tokens\")]"));
    assert!(stub.contains("public uint CurrentTokens();"));
    assert!(stub.contains("public static class RateLimiterModule"));
    assert!(stub.contains("[MapsTo(\"rate_limiter::reset_all\")]"));
    assert!(stub.contains("public static void ResetAll() throws string;"));
}

#[test]
fn test_bindgen_crate_directory_multi_file_analysis() {
    let fixture_dir = Path::new("tests/fixtures/sample_cargo_crate");
    assert!(fixture_dir.exists(), "Sample cargo crate fixture missing!");

    let crate_info = CrateAnalyzer::analyze(fixture_dir, None)
        .expect("Failed to analyze sample_cargo_crate directory");

    assert_eq!(crate_info.name, "sample_crypto");
    assert_eq!(crate_info.version, "0.2.1");

    // Root module has submodule `crypto`
    assert_eq!(crate_info.root_module.submodules.len(), 1);
    let crypto_sub = &crate_info.root_module.submodules[0];
    assert_eq!(crypto_sub.name, "crypto");

    // Crypto submodule contains Hasher struct and Algorithm enum
    assert!(crypto_sub.structs.iter().any(|s| s.name == "Hasher"));
    assert!(crypto_sub.enums.iter().any(|e| e.name == "Algorithm"));
    assert!(crypto_sub.traits.iter().any(|t| t.name == "DigestProducer"));

    // Generate complete .d.rsharp header code
    let header = generate_crate_header(fixture_dir, None, None, None)
        .expect("Failed to generate crate header");

    assert!(header.contains("[assembly: CrateDependency(\"sample_crypto\", \"0.2.1\")]"));
    assert!(header.contains("namespace SampleCrypto"));
    assert!(header.contains("public const nuint MaxKeySize = 256;"));
    assert!(header.contains("public static string QuickHash(string input) throws CryptoError;"));
    assert!(header.contains("public static class Crypto"));
    assert!(header.contains("public string Finalize() throws CryptoError;"));
}

#[test]
fn test_bindgen_cargo_sync_and_e2e_transpilation() {
    let stub_src = r#"
namespace SampleCrypto
{
    [CrateDependency("sample_crypto", "0.2.1")]
    [MapsTo("sample_crypto::Hasher")]
    public class Hasher
    {
        [MapsTo("finalize")]
        public string Finalize();
    }
}
"#;
    let mut diag = DiagnosticEngine::new();
    let unit = parse_source_str(stub_src, 1, "SampleCrypto.d.rsharp", &mut diag);
    assert!(!diag.has_errors());

    let discovered = CargoDependencySynchronizer::discover_dependencies(&[unit]);
    assert_eq!(discovered.get("sample_crypto"), Some(&"0.2.1".to_string()));

    let mut existing_deps = vec![("serde".to_string(), "1.0".to_string())];
    CargoDependencySynchronizer::merge_into_dependencies(&mut existing_deps, discovered);

    assert_eq!(existing_deps.len(), 2);
    assert_eq!(existing_deps[0], ("serde".to_string(), "1.0".to_string()));
    assert_eq!(
        existing_deps[1],
        ("sample_crypto".to_string(), "0.2.1".to_string())
    );

    // 2. Synthesize Cargo.toml with the synchronized dependency
    let config = RsProjConfig {
        name: "crypto_client".to_string(),
        version: "0.1.0".to_string(),
        edition: "2021".to_string(),
        root_dir: std::path::PathBuf::from("."),
        out_cargo_dir: std::path::PathBuf::from("target/test_sync_out"),
        cargo_dependencies: existing_deps,
        stub_files: Vec::new(),
        rsharp_files: Vec::new(),
        colocated_rs_files: Vec::new(),
    };

    let cargo_toml = CargoWorkspaceSynthesizer::emit_cargo_toml(&config);
    assert!(cargo_toml.contains("name = \"crypto_client\""));
    assert!(cargo_toml.contains("serde = \"1.0\""));
    assert!(cargo_toml.contains("sample_crypto = \"0.2.1\""));
}
