//! `rsharp-bindgen`: The Cargo Ecosystem Bridge for RustSharp.
//!
//! Inspects native Rust crates and source files, extracts public type signatures,
//! and synthesizes typed `.d.rsharp` ambient declarations with compile-time mapping attributes.

pub mod cargo_sync;
pub mod crate_analyzer;
pub mod rs_ast;
pub mod rs_parser;
pub mod stub_generator;

pub use cargo_sync::CargoDependencySynchronizer;
pub use crate_analyzer::{CrateAnalyzer, RustCrateInfo};
pub use rs_ast::*;
pub use rs_parser::{RsLexer, RsParser};
pub use stub_generator::StubGenerator;

use std::fs;
use std::path::Path;

/// High-level function generating `.d.rsharp` ambient header file from a crate path.
pub fn generate_crate_header(
    crate_path: &Path,
    namespace_override: Option<&str>,
    crate_name_override: Option<&str>,
    out_file: Option<&Path>,
) -> Result<String, String> {
    let crate_info = CrateAnalyzer::analyze(crate_path, crate_name_override)?;
    let header_code = StubGenerator::generate(&crate_info, namespace_override);

    if let Some(out_p) = out_file {
        if let Some(parent) = out_p.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create directory '{}': {}", parent.display(), e))?;
        }
        fs::write(out_p, &header_code)
            .map_err(|e| format!("Failed to write '{}': {}", out_p.display(), e))?;
    }

    Ok(header_code)
}
