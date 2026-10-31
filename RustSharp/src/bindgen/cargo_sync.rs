//! Cargo.toml Dependency Synchronizer for `rsharp-bindgen` and `rsharpc`.
//!
//! Automatically detects external Cargo crate references across `.rsharp` and `.d.rsharp`
//! compilation units and synchronizes them into the synthesized `Cargo.toml`.

use std::collections::BTreeMap;

use crate::frontend::ast::{CompilationUnit, ExprKind, LiteralValue};

pub struct CargoDependencySynchronizer;

impl CargoDependencySynchronizer {
    /// Discovers all external crate requirements referenced across compilation units.
    pub fn discover_dependencies(units: &[CompilationUnit]) -> BTreeMap<String, String> {
        let mut deps = BTreeMap::new();

        for unit in units {
            // Ambient standard library (RustSharp.Core.d.rsharp) does not impose external dependencies
            if unit.filename.ends_with("RustSharp.Core.d.rsharp") {
                continue;
            }

            // 1. Check unit-level / assembly-level attributes: `[assembly: CrateDependency("...", "...")]`
            for attr in &unit.attributes {
                let short = attr.short_name();
                if short == "CrateDependency" && attr.args.len() >= 2 {
                    let name_opt = match &attr.args[0].value.kind {
                        ExprKind::Literal(LiteralValue::String(s)) => Some(s.clone()),
                        _ => None,
                    };
                    let ver_opt = match &attr.args[1].value.kind {
                        ExprKind::Literal(LiteralValue::String(s)) => Some(s.clone()),
                        _ => None,
                    };
                    if let (Some(name), Some(ver)) = (name_opt, ver_opt) {
                        deps.insert(name, ver);
                    }
                }
            }

            // 2. Check `extern using foo;`
            for imp in &unit.imports {
                if imp.is_extern_crate {
                    if let Some(crate_name) = imp.path.first() {
                        if !Self::is_builtin_crate(crate_name) {
                            deps.entry(crate_name.clone())
                                .or_insert_with(|| "*".to_string());
                        }
                    }
                }
            }

            // 3. Check type-level and member-level attributes
            for ty in &unit.types {
                for attr in &ty.attributes {
                    let short = attr.short_name();
                    if short == "CrateDependency" && attr.args.len() >= 2 {
                        let name_opt = match &attr.args[0].value.kind {
                            ExprKind::Literal(LiteralValue::String(s)) => Some(s.clone()),
                            _ => None,
                        };
                        let ver_opt = match &attr.args[1].value.kind {
                            ExprKind::Literal(LiteralValue::String(s)) => Some(s.clone()),
                            _ => None,
                        };
                        if let (Some(name), Some(ver)) = (name_opt, ver_opt) {
                            deps.insert(name, ver);
                        }
                    } else if short == "MapsTo" && !unit.is_ambient_stub {
                        if let Some(rust_path) = attr.first_string_arg() {
                            if let Some((crate_prefix, _)) = rust_path.split_once("::") {
                                let clean_prefix = crate_prefix
                                    .split_whitespace()
                                    .last()
                                    .unwrap_or(crate_prefix);
                                if !Self::is_builtin_crate(clean_prefix) {
                                    deps.entry(clean_prefix.to_string())
                                        .or_insert_with(|| "*".to_string());
                                }
                            }
                        }
                    } else if matches!(
                        short,
                        "JsonPropertyName"
                            | "JsonIgnore"
                            | "JsonRequired"
                            | "Serialize"
                            | "Deserialize"
                    ) {
                        deps.entry("serde".to_string())
                            .or_insert_with(|| "1.0".to_string());
                    } else if matches!(
                        short,
                        "HttpGet" | "HttpPost" | "HttpPut" | "HttpDelete" | "Route"
                    ) {
                        deps.entry("axum".to_string())
                            .or_insert_with(|| "0.7".to_string());
                    }
                }

                // Check primary constructor parameters
                for param in &ty.primary_ctor_params {
                    for attr in &param.attributes {
                        let short = attr.short_name();
                        if matches!(short, "JsonPropertyName" | "JsonIgnore" | "JsonRequired") {
                            deps.entry("serde".to_string())
                                .or_insert_with(|| "1.0".to_string());
                        }
                    }
                }

                // Check methods and fields
                for member in &ty.members {
                    if let crate::frontend::ast::MemberDecl::Method(m) = member {
                        if m.is_async {
                            deps.entry("tokio".to_string())
                                .or_insert_with(|| "1.0".to_string());
                        }
                    }

                    let member_attrs = match member {
                        crate::frontend::ast::MemberDecl::Method(m) => &m.attributes,
                        crate::frontend::ast::MemberDecl::Field(f) => &f.attributes,
                        crate::frontend::ast::MemberDecl::Constructor(c) => &c.attributes,
                        crate::frontend::ast::MemberDecl::Property(p) => &p.attributes,
                        crate::frontend::ast::MemberDecl::Indexer(i) => &i.attributes,
                    };
                    for attr in member_attrs {
                        let short = attr.short_name();
                        if short == "MapsTo" && !unit.is_ambient_stub {
                            if let Some(rust_path) = attr.first_string_arg() {
                                if let Some((crate_prefix, _)) = rust_path.split_once("::") {
                                    let clean_prefix = crate_prefix
                                        .split_whitespace()
                                        .last()
                                        .unwrap_or(crate_prefix);
                                    if !Self::is_builtin_crate(clean_prefix) {
                                        deps.entry(clean_prefix.to_string())
                                            .or_insert_with(|| "*".to_string());
                                    }
                                }
                            }
                        } else if matches!(
                            short,
                            "JsonPropertyName" | "JsonIgnore" | "JsonRequired"
                        ) {
                            deps.entry("serde".to_string())
                                .or_insert_with(|| "1.0".to_string());
                        } else if matches!(
                            short,
                            "HttpGet" | "HttpPost" | "HttpPut" | "HttpDelete" | "Route"
                        ) {
                            deps.entry("axum".to_string())
                                .or_insert_with(|| "0.7".to_string());
                        }
                    }
                }
            }
        }

        deps
    }

    /// Merges discovered dependencies into an existing `cargo_dependencies` vector,
    /// preserving explicit versions already defined in `.rsproj`.
    pub fn merge_into_dependencies(
        existing: &mut Vec<(String, String)>,
        discovered: BTreeMap<String, String>,
    ) {
        for (crate_name, ver) in discovered {
            if !existing.iter().any(|(name, _)| name == &crate_name) {
                existing.push((crate_name, ver));
            }
        }
    }

    fn is_builtin_crate(name: &str) -> bool {
        matches!(name, "std" | "core" | "alloc" | "crate" | "self" | "super")
    }
}
