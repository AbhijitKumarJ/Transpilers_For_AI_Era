pub mod incremental;
pub mod watcher;

pub use incremental::{compute_sha256, IncrementalBuildCache};
pub use watcher::WorkspaceWatcher;

use std::fs;
use std::path::{Path, PathBuf};

/// Represents a `.rsproj` project configuration and Cargo workspace synthesis plan.
/// Maps 1:1 to a synthesized Cargo crate where C# `internal` lowers to Rust `pub(crate)`.
#[derive(Clone, Debug)]
pub struct RsProjConfig {
    /// Cargo package name (e.g., `"commerce_api"`).
    pub name: String,
    /// Package semantic version (defaults to `"0.1.0"`).
    pub version: String,
    /// Rust edition (defaults to `"2021"`).
    pub edition: String,
    /// Root directory containing the `.rsproj` file.
    pub root_dir: PathBuf,
    /// Output directory where the synthesized Cargo project (`Cargo.toml` + `src/`) is emitted.
    pub out_cargo_dir: PathBuf,
    /// External Cargo crate dependencies `(crate_name, version_req)`.
    pub cargo_dependencies: Vec<(String, String)>,
    /// Ambient `.d.rsharp` declaration files (including `RustSharp.Core.d.rsharp`).
    pub stub_files: Vec<PathBuf>,
    /// User `.rsharp` source files discovered across arbitrary folders.
    pub rsharp_files: Vec<PathBuf>,
    /// Co-located raw `.rs` files (`extern partial` implementations) discovered in the project.
    pub colocated_rs_files: Vec<PathBuf>,
}

impl RsProjConfig {
    /// Returns all `.d.rsharp` stub files followed by all `.rsharp` source files in deterministic order.
    pub fn all_rsharp_inputs(&self) -> Vec<PathBuf> {
        let mut all = Vec::with_capacity(self.stub_files.len() + self.rsharp_files.len());
        all.extend(self.stub_files.iter().cloned());
        all.extend(self.rsharp_files.iter().cloned());
        all
    }
}

/// Loads a `.rsproj` file (supporting both C#-style XML `<Project>` and TOML formats)
/// and recursively discovers all `.d.rsharp`, `.rsharp`, and co-located `.rs` files.
pub fn load_rsproj(path: &Path, stdlib_dir: Option<&Path>) -> Result<RsProjConfig, String> {
    let canonical_path = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    let root_dir = canonical_path
        .parent()
        .ok_or_else(|| format!("Invalid .rsproj path '{}'", path.display()))?
        .to_path_buf();

    let raw_text = fs::read_to_string(&canonical_path)
        .map_err(|e| format!("Failed to read '{}': {}", canonical_path.display(), e))?;

    let default_stem = canonical_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("rsharp_app")
        .to_lowercase()
        .replace('.', "_");

    let mut name = default_stem;
    let mut version = String::from("0.1.0");
    let mut edition = String::from("2021");
    let mut out_cargo_dir = root_dir.join("target").join("rsharp_synth");
    let mut cargo_dependencies = Vec::new();

    let trimmed = raw_text.trim();
    if trimmed.starts_with('<') {
        parse_xml_rsproj(
            trimmed,
            &root_dir,
            &mut name,
            &mut version,
            &mut edition,
            &mut out_cargo_dir,
            &mut cargo_dependencies,
        );
    } else {
        parse_toml_like_rsproj(
            trimmed,
            &root_dir,
            &mut name,
            &mut version,
            &mut edition,
            &mut out_cargo_dir,
            &mut cargo_dependencies,
        );
    }

    let mut stub_files = Vec::new();
    if let Some(stdlib) = stdlib_dir {
        if stdlib.exists() {
            let mut std_stubs = Vec::new();
            let mut unused_rsharp = Vec::new();
            let mut unused_rs = Vec::new();
            discover_workspace_files(
                stdlib,
                &out_cargo_dir,
                &mut std_stubs,
                &mut unused_rsharp,
                &mut unused_rs,
            )?;
            std_stubs.sort();
            stub_files.extend(std_stubs);
        }
    }

    let mut proj_stubs = Vec::new();
    let mut rsharp_files = Vec::new();
    let mut colocated_rs_files = Vec::new();

    discover_workspace_files(
        &root_dir,
        &out_cargo_dir,
        &mut proj_stubs,
        &mut rsharp_files,
        &mut colocated_rs_files,
    )?;

    proj_stubs.sort();
    for st in proj_stubs {
        if !stub_files.contains(&st) {
            stub_files.push(st);
        }
    }
    rsharp_files.sort();
    colocated_rs_files.sort();

    Ok(RsProjConfig {
        name,
        version,
        edition,
        root_dir,
        out_cargo_dir,
        cargo_dependencies,
        stub_files,
        rsharp_files,
        colocated_rs_files,
    })
}

fn discover_workspace_files(
    dir: &Path,
    out_cargo_dir: &Path,
    stubs: &mut Vec<PathBuf>,
    rsharp_files: &mut Vec<PathBuf>,
    colocated_rs_files: &mut Vec<PathBuf>,
) -> Result<(), String> {
    if !dir.exists() {
        return Ok(());
    }
    let entries = fs::read_dir(dir)
        .map_err(|e| format!("Failed to read directory '{}': {}", dir.display(), e))?;

    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();

        if path == *out_cargo_dir {
            continue;
        }

        if let Some(fname) = path.file_name().and_then(|s| s.to_str()) {
            if fname.starts_with('.') || fname == "target" || fname == "node_modules" {
                continue;
            }
            if path.is_dir() {
                discover_workspace_files(
                    &path,
                    out_cargo_dir,
                    stubs,
                    rsharp_files,
                    colocated_rs_files,
                )?;
            } else if fname.ends_with(".d.rsharp") {
                stubs.push(path);
            } else if fname.ends_with(".rsharp") {
                rsharp_files.push(path);
            } else if fname.ends_with(".rs") {
                colocated_rs_files.push(path);
            }
        }
    }
    Ok(())
}

fn parse_xml_rsproj(
    xml: &str,
    root_dir: &Path,
    name: &mut String,
    version: &mut String,
    edition: &mut String,
    out_cargo_dir: &mut PathBuf,
    cargo_dependencies: &mut Vec<(String, String)>,
) {
    if let Some(val) = extract_xml_tag_value(xml, "AssemblyName")
        .or_else(|| extract_xml_tag_value(xml, "PackageName"))
    {
        *name = val.to_lowercase().replace(['.', '-'], "_");
    }
    if let Some(val) = extract_xml_tag_value(xml, "Version") {
        *version = val;
    }
    if let Some(val) = extract_xml_tag_value(xml, "RustEdition") {
        *edition = val;
    }
    if let Some(val) = extract_xml_tag_value(xml, "OutputPath") {
        *out_cargo_dir = root_dir.join(val);
    }

    // Parse `<CargoCrate Include="rust_decimal" Version="1.36" />` or `<PackageReference ... />`
    for line in xml.lines() {
        let line = line.trim();
        if line.starts_with("<CargoCrate") || line.starts_with("<PackageReference") {
            if let Some(crate_name) = extract_xml_attr(line, "Include") {
                let ver = extract_xml_attr(line, "Version").unwrap_or_else(|| "*".to_string());
                cargo_dependencies.push((crate_name, ver));
            }
        }
    }
}

fn extract_xml_tag_value(xml: &str, tag: &str) -> Option<String> {
    let open = format!("<{}>", tag);
    let close = format!("</{}>", tag);
    let start = xml.find(&open)? + open.len();
    let end = xml[start..].find(&close)? + start;
    let content = xml[start..end].trim();
    if content.is_empty() {
        None
    } else {
        Some(content.to_string())
    }
}

fn extract_xml_attr(line: &str, attr: &str) -> Option<String> {
    let pattern = format!("{}=\"", attr);
    let start = line.find(&pattern)? + pattern.len();
    let end = line[start..].find('"')? + start;
    Some(line[start..end].trim().to_string())
}

fn parse_toml_like_rsproj(
    text: &str,
    root_dir: &Path,
    name: &mut String,
    version: &mut String,
    edition: &mut String,
    out_cargo_dir: &mut PathBuf,
    cargo_dependencies: &mut Vec<(String, String)>,
) {
    let mut current_section = "";
    for raw_line in text.lines() {
        let line = raw_line.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        if line.starts_with('[') && line.ends_with(']') {
            current_section = &line[1..line.len() - 1];
            continue;
        }
        if let Some((k, v)) = line.split_once('=') {
            let key = k.trim();
            let val = v.trim().trim_matches('"').trim_matches('\'');
            match current_section {
                "project" | "package" | "" => match key {
                    "name" => *name = val.to_lowercase().replace(['.', '-'], "_"),
                    "version" => *version = val.to_string(),
                    "edition" => *edition = val.to_string(),
                    "out_dir" | "out_cargo_dir" => *out_cargo_dir = root_dir.join(val),
                    _ => {}
                },
                "dependencies" | "cargo.dependencies" => {
                    cargo_dependencies.push((key.to_string(), val.to_string()));
                }
                _ => {}
            }
        }
    }
}
