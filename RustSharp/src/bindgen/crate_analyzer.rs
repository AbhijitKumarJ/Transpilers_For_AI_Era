//! Cargo Crate Analyzer for `rsharp-bindgen`.
//!
//! Inspects Cargo crate directory structure, reads `Cargo.toml`, discovers entry points
//! (`src/lib.rs`), recursively parses submodules, and produces an aggregated module hierarchy.

use std::fs;
use std::path::{Path, PathBuf};

use crate::bindgen::rs_ast::*;
use crate::bindgen::rs_parser::{RsLexer, RsParser};

#[derive(Clone, Debug, Default)]
pub struct ParsedCargoManifest {
    pub name: String,
    pub version: String,
    pub dependencies: Vec<(String, String)>,
}

#[derive(Clone, Debug)]
pub struct RustCrateInfo {
    pub name: String,
    pub version: String,
    pub root_dir: PathBuf,
    pub root_module: RustModule,
    pub dependencies: Vec<(String, String)>,
}

pub struct CrateAnalyzer;

impl CrateAnalyzer {
    /// Analyzes a crate from either a crate directory containing `Cargo.toml`
    /// or a single `.rs` source file.
    pub fn analyze(
        path: &Path,
        crate_name_override: Option<&str>,
    ) -> Result<RustCrateInfo, String> {
        if path.is_file() {
            Self::analyze_single_file(path, crate_name_override)
        } else if path.is_dir() {
            Self::analyze_crate_dir(path, crate_name_override)
        } else {
            Err(format!("Path '{}' does not exist.", path.display()))
        }
    }

    fn analyze_single_file(
        file_path: &Path,
        crate_name_override: Option<&str>,
    ) -> Result<RustCrateInfo, String> {
        let text = fs::read_to_string(file_path)
            .map_err(|e| format!("Failed to read file '{}': {}", file_path.display(), e))?;

        let stem = file_path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("crate");
        let name = crate_name_override
            .map(|s| s.to_string())
            .unwrap_or_else(|| stem.to_string());

        let mut lexer = RsLexer::new(&text);
        let tokens = lexer.tokenize();
        let mut parser = RsParser::new(tokens);
        let root_module = parser.parse_module(&name);

        let parent_dir = file_path
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .to_path_buf();

        Ok(RustCrateInfo {
            name,
            version: "0.1.0".to_string(),
            root_dir: parent_dir,
            root_module,
            dependencies: Vec::new(),
        })
    }

    fn analyze_crate_dir(
        dir_path: &Path,
        crate_name_override: Option<&str>,
    ) -> Result<RustCrateInfo, String> {
        let cargo_toml_path = dir_path.join("Cargo.toml");
        let manifest = if cargo_toml_path.exists() {
            Self::parse_cargo_toml(&cargo_toml_path)?
        } else {
            let stem = dir_path
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("crate");
            ParsedCargoManifest {
                name: stem.to_string(),
                version: "0.1.0".to_string(),
                dependencies: Vec::new(),
            }
        };

        let final_name = crate_name_override
            .map(|s| s.to_string())
            .unwrap_or(manifest.name);

        // Find lib.rs or main.rs
        let src_dir = dir_path.join("src");
        let lib_rs = src_dir.join("lib.rs");
        let main_rs = src_dir.join("main.rs");

        let entry_point = if lib_rs.exists() {
            lib_rs
        } else if main_rs.exists() {
            main_rs
        } else {
            return Err(format!(
                "Could not find 'src/lib.rs' or 'src/main.rs' in crate '{}'.",
                dir_path.display()
            ));
        };

        let text = fs::read_to_string(&entry_point)
            .map_err(|e| format!("Failed to read '{}': {}", entry_point.display(), e))?;

        let mut lexer = RsLexer::new(&text);
        let tokens = lexer.tokenize();
        let mut parser = RsParser::new(tokens);
        let mut root_module = parser.parse_module(&final_name);

        // Recursively resolve submodules declared via `mod foo;` on disk
        Self::resolve_submodules_on_disk(&src_dir, &mut root_module);

        Ok(RustCrateInfo {
            name: final_name,
            version: manifest.version,
            root_dir: dir_path.to_path_buf(),
            root_module,
            dependencies: manifest.dependencies,
        })
    }

    fn resolve_submodules_on_disk(parent_dir: &Path, module: &mut RustModule) {
        for sub in &mut module.submodules {
            if sub.structs.is_empty() && sub.enums.is_empty() && sub.functions.is_empty() {
                // Try `src/<sub.name>.rs` or `src/<sub.name>/mod.rs`
                let candidate1 = parent_dir.join(format!("{}.rs", sub.name));
                let candidate2 = parent_dir.join(&sub.name).join("mod.rs");

                let target = if candidate1.exists() {
                    Some((candidate1, parent_dir.to_path_buf()))
                } else if candidate2.exists() {
                    let sub_dir = parent_dir.join(&sub.name);
                    Some((candidate2, sub_dir))
                } else {
                    None
                };

                if let Some((file, sub_parent)) = target {
                    if let Ok(text) = fs::read_to_string(&file) {
                        let mut lexer = RsLexer::new(&text);
                        let tokens = lexer.tokenize();
                        let mut parser = RsParser::new(tokens);
                        let mut loaded = parser.parse_module(&sub.name);
                        Self::resolve_submodules_on_disk(&sub_parent, &mut loaded);
                        *sub = loaded;
                    }
                }
            }
        }
    }

    fn parse_cargo_toml(path: &Path) -> Result<ParsedCargoManifest, String> {
        let content = fs::read_to_string(path)
            .map_err(|e| format!("Failed to read '{}': {}", path.display(), e))?;

        let mut name = String::new();
        let mut version = "0.1.0".to_string();
        let mut dependencies = Vec::new();

        let mut current_section = "";
        for raw_line in content.lines() {
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

                if current_section == "package" {
                    if key == "name" {
                        name = val.to_string();
                    } else if key == "version" {
                        version = val.to_string();
                    }
                } else if current_section == "dependencies" {
                    let dep_ver = if val.starts_with('{') {
                        // Table inline dep: `serde = { version = "1.0", features = [...] }`
                        if let Some(v_start) = val.find("version = \"") {
                            let rest = &val[v_start + 11..];
                            let v_end = rest.find('"').unwrap_or(rest.len());
                            &rest[..v_end]
                        } else {
                            "*"
                        }
                    } else {
                        val
                    };
                    dependencies.push((key.to_string(), dep_ver.to_string()));
                }
            }
        }

        if name.is_empty() {
            let stem = path
                .parent()
                .and_then(|p| p.file_name())
                .and_then(|s| s.to_str())
                .unwrap_or("crate");
            name = stem.to_string();
        }

        Ok(ParsedCargoManifest {
            name,
            version,
            dependencies,
        })
    }
}
