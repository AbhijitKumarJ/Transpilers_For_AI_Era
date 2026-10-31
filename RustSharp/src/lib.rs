pub mod bindgen;
pub mod codegen;
pub mod diagnostics;
pub mod frontend;
pub mod lsp;
pub mod project;
pub mod semantics;

use std::fs;
use std::path::Path;

use codegen::{CargoWorkspaceSynthesizer, SynthesizedCrateOutput};
use diagnostics::DiagnosticEngine;
use frontend::{CompilationUnit, Lexer, Parser};
use project::{load_rsproj, RsProjConfig};
use semantics::{
    analyze_archetypes, collect_global_symbols, fuse_linq_pipelines, infer_checked_effects,
    resolve_overloads, resolve_polymorphism_strategies, resolve_primitives,
    run_preflight_ownership_checks, GlobalSymbolTable, InterproceduralBorrowInferencer,
};

/// Convenience helper to lex and parse a single `.rsharp` or `.d.rsharp` source string.
pub fn parse_source_str(
    source: &str,
    file_id: usize,
    filename: &str,
    diag: &mut DiagnosticEngine,
) -> CompilationUnit {
    let tokens = {
        let mut lexer = Lexer::new(source, file_id, filename, diag);
        lexer.tokenize()
    };
    let mut parser = Parser::new(tokens, file_id, filename, diag);
    parser.parse_compilation_unit()
}

/// Runs Milestone 1 (Frontend Lexer + Parser) and Milestone 2 (Pass 1 Global Symbol Collector
/// & Virtual Namespace Aggregator) over an in-memory set of `(filename, source_code)` pairs.
pub fn analyze_workspace_pass1(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let mut diag = DiagnosticEngine::new();
    let mut units = Vec::with_capacity(files.len());

    for (idx, (filename, source)) in files.iter().enumerate() {
        let unit = parse_source_str(source, idx, filename, &mut diag);
        units.push(unit);
    }

    let mut symtab = GlobalSymbolTable::new();
    collect_global_symbols(&mut units, &mut symtab, &mut diag);

    (units, symtab, diag)
}

/// Runs Milestone 1, Milestone 2 (Pass 1), and Milestone 3 (Pass 2A: Archetype Lowering,
/// Hierarchy Flattening & Static Overload Resolution) across all workspace files.
pub fn analyze_workspace_pass2a(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (mut units, mut symtab, mut diag) = analyze_workspace_pass1(files);
    if !diag.has_errors() {
        analyze_archetypes(&mut units, &mut symtab, &mut diag);
        resolve_polymorphism_strategies(&mut units, &mut symtab);
        resolve_overloads(&mut units, &mut symtab);
    }
    (units, symtab, diag)
}

/// Runs Milestones 1–4 (Pass 1, Pass 2A, and Pass 2B: `primitive` Type Erasure,
/// Interprocedural Borrow & Mutation Propagation, Checked `throws` Effect Inference,
/// and Zero-Cost LINQ-to-Iterator Pipeline Fusion).
pub fn analyze_workspace_pass2b(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (mut units, mut symtab, diag) = analyze_workspace_pass2a(files);
    if !diag.has_errors() {
        fuse_linq_pipelines(&mut units, &symtab);
        resolve_primitives(&mut units, &mut symtab);
        InterproceduralBorrowInferencer::infer_all(&mut units, &mut symtab);
        infer_checked_effects(&mut units, &mut symtab);
    }
    (units, symtab, diag)
}

/// Runs Milestones 1–5 (Pass 1, Pass 2A, Pass 2B, and Pass 2.5 Pre-Flight Ownership Verifier
/// enforcing rules `RSHARP001`–`RSHARP003` before Rust code emission).
pub fn analyze_workspace_with_preflight(
    files: &[(&str, &str)],
) -> (Vec<CompilationUnit>, GlobalSymbolTable, DiagnosticEngine) {
    let (units, symtab, mut diag) = analyze_workspace_pass2b(files);
    if !diag.has_errors() {
        run_preflight_ownership_checks(&units, &symtab, &mut diag);
    }
    (units, symtab, diag)
}

/// Full 3-pass compiler pipeline (Milestones 1–6) from an on-disk `.rsproj` file:
/// - Discovers all `.d.rsharp`, `.rsharp`, and co-located `.rs` files.
/// - Runs Pass 1 (Global Symbol Table), Pass 2A/2B (Archetype, Hierarchy, Overload, Borrow,
///   Effect & LINQ Analysis), and Pass 2.5 (Pre-Flight Ownership Verifier).
/// - Runs Pass 3 (`CargoWorkspaceSynthesizer`) if `write_to_disk` is true or returns the
///   in-memory synthesized crate output.
pub fn compile_rsproj(
    rsproj_path: &Path,
    stdlib_dir: Option<&Path>,
    write_to_disk: bool,
) -> Result<(RsProjConfig, SynthesizedCrateOutput, DiagnosticEngine), String> {
    let mut config = load_rsproj(rsproj_path, stdlib_dir)?;
    let input_paths = config.all_rsharp_inputs();

    let mut loaded_sources: Vec<(String, String)> = Vec::with_capacity(input_paths.len());
    for path in &input_paths {
        let src = fs::read_to_string(path)
            .map_err(|e| format!("Failed to read '{}': {}", path.display(), e))?;
        let display_name = path
            .strip_prefix(&config.root_dir)
            .unwrap_or(path)
            .to_string_lossy()
            .replace('\\', "/");
        loaded_sources.push((display_name, src));
    }

    let borrowed_pairs: Vec<(&str, &str)> = loaded_sources
        .iter()
        .map(|(f, s)| (f.as_str(), s.as_str()))
        .collect();

    let (units, mut symtab, diag) = analyze_workspace_with_preflight(&borrowed_pairs);
    symtab.colocated_rs_files = config.colocated_rs_files.clone();

    if diag.has_errors() {
        return Err(diag.format_all());
    }

    // Automatically synchronize external crate dependencies detected in stubs/code into Cargo.toml
    let discovered_deps =
        crate::bindgen::CargoDependencySynchronizer::discover_dependencies(&units);
    crate::bindgen::CargoDependencySynchronizer::merge_into_dependencies(
        &mut config.cargo_dependencies,
        discovered_deps,
    );

    let synth = if write_to_disk {
        CargoWorkspaceSynthesizer::synthesize_workspace(&config, &symtab, &units)?
    } else {
        CargoWorkspaceSynthesizer::synthesize_in_memory(&config, &symtab, &units)?
    };

    Ok((config, synth, diag))
}
