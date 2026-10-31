use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use crate::codegen::rs_ast_emitter::RustModuleEmitter;
use crate::codegen::sourcemap::RustSourceMap;
use crate::frontend::ast::{CompilationUnit, MemberDecl, TypeDecl};
use crate::project::RsProjConfig;
use crate::semantics::symbols::{pascal_to_snake_case, GlobalSymbolTable, NamespaceModulePlan};

/// Output artifact summary produced by Pass 3 (`CargoWorkspaceSynthesizer`).
#[derive(Clone, Debug)]
pub struct SynthesizedCrateOutput {
    pub cargo_toml_path: PathBuf,
    pub cargo_toml_content: String,
    pub lib_rs_path: PathBuf,
    pub lib_rs_content: String,
    /// Map of relative path (e.g. `"src/commerce/checkout.rs"`) -> emitted Rust code.
    pub emitted_modules: BTreeMap<String, String>,
    /// Map of relative path -> bidirectional `.rsharp` <-> `.rs` source map.
    pub sourcemaps: BTreeMap<String, RustSourceMap>,
    /// Co-located `.rs` files copied and linked into the synthesized crate.
    pub linked_colocated_files: Vec<String>,
}

/// Pass 3 Cargo Workspace & Module Tree Synthesizer.
///
/// Groups all decorated `.rsharp` types by their logical virtual namespace, emits formatted
/// `src/<namespace>.rs` modules, links any co-located raw `.rs` files (`extern partial`)
/// into the module tree, writes `.rsharp.map` bidirectional source maps, and synthesizes
/// `Cargo.toml` and `src/lib.rs`.
pub struct CargoWorkspaceSynthesizer;

impl CargoWorkspaceSynthesizer {
    /// Generates all in-memory Rust modules, `Cargo.toml`, `src/lib.rs`, and `.rsharp.map` tables.
    pub fn synthesize_in_memory(
        config: &RsProjConfig,
        symtab: &GlobalSymbolTable,
        units: &[CompilationUnit],
    ) -> Result<SynthesizedCrateOutput, String> {
        let plans = symtab.build_namespace_module_plans();
        let mut emitted_modules = BTreeMap::new();
        let mut sourcemaps = BTreeMap::new();
        let mut linked_colocated_files = Vec::new();

        // Map co-located `.rs` file stems (e.g. `"PacketHeader"`) to their raw `.rs` paths
        let mut colocated_by_stem: BTreeMap<String, &PathBuf> = BTreeMap::new();
        for rs_path in &config.colocated_rs_files {
            if let Some(stem) = rs_path.file_stem().and_then(|s| s.to_str()) {
                colocated_by_stem.insert(stem.to_string(), rs_path);
            }
        }

        let mut emitter = RustModuleEmitter::new(symtab);

        for plan in &plans {
            // Collect all non-ambient AST `TypeDecl`s belonging to `plan.namespace`
            let mut ns_decls: Vec<&TypeDecl> = Vec::new();
            for unit in units {
                if unit.is_ambient_stub || unit.namespace != plan.namespace {
                    continue;
                }
                for decl in &unit.types {
                    ns_decls.push(decl);
                }
            }

            let (mut rs_code, smap) =
                emitter.emit_namespace_module(&plan.namespace, &ns_decls, &plan.target_rs_file);

            // Check if any type in this namespace has a matching co-located `.rs` file (`extern partial`)
            for decl in &ns_decls {
                if let Some(&colocated_path) = colocated_by_stem.get(&decl.name) {
                    let submod_snake = format!("{}_ext", pascal_to_snake_case(&decl.name));
                    let parent_dir = Path::new(&plan.target_rs_file)
                        .parent()
                        .unwrap_or_else(|| Path::new("src"));
                    let colocated_rel = parent_dir
                        .join(format!("{}.rs", submod_snake))
                        .to_string_lossy()
                        .replace('\\', "/");

                    let raw_rs = fs::read_to_string(colocated_path).map_err(|e| {
                        format!(
                            "Failed to read co-located Rust file '{}': {}",
                            colocated_path.display(),
                            e
                        )
                    })?;

                    rs_code.push_str(&format!(
                        "\n// Linked co-located raw Rust implementation (`{}`)\n#[path = \"{}.rs\"]\npub mod {};\n",
                        colocated_path
                            .file_name()
                            .and_then(|s| s.to_str())
                            .unwrap_or(""),
                        submod_snake,
                        submod_snake
                    ));

                    emitted_modules.insert(colocated_rel.clone(), raw_rs);
                    linked_colocated_files.push(colocated_rel);
                }
            }

            emitted_modules.insert(plan.target_rs_file.clone(), rs_code);
            sourcemaps.insert(plan.target_rs_file.clone(), smap);
        }

        // Detect static Main entrypoint if present
        let mut main_entry: Option<(String, String)> = None;
        for plan in &plans {
            for unit in units {
                if unit.is_ambient_stub || unit.namespace != plan.namespace {
                    continue;
                }
                for ty in &unit.types {
                    for m in &ty.members {
                        if let MemberDecl::Method(meth) = m {
                            if meth.is_static && meth.name == "Main" {
                                let mod_path = plan.rust_mod_segments.join("::");
                                main_entry = Some((mod_path, ty.name.clone()));
                                break;
                            }
                        }
                    }
                    if main_entry.is_some() {
                        break;
                    }
                }
                if main_entry.is_some() {
                    break;
                }
            }
            if main_entry.is_some() {
                break;
            }
        }

        if let Some((mod_path, class_name)) = main_entry {
            let crate_ident = config.name.replace('-', "_");
            let main_code = format!(
                "// Auto-generated by rsharpc entrypoint\nfn main() {{\n    {}::{}::{}::main();\n}}\n",
                crate_ident, mod_path, class_name
            );
            emitted_modules.insert("src/main.rs".to_string(), main_code);
        }

        let cargo_toml_content = Self::emit_cargo_toml(config);
        let lib_rs_content = Self::emit_lib_rs(&plans);

        Ok(SynthesizedCrateOutput {
            cargo_toml_path: config.out_cargo_dir.join("Cargo.toml"),
            cargo_toml_content,
            lib_rs_path: config.out_cargo_dir.join("src").join("lib.rs"),
            lib_rs_content,
            emitted_modules,
            sourcemaps,
            linked_colocated_files,
        })
    }

    /// Synthesizes the complete Cargo workspace on disk inside `config.out_cargo_dir`.
    pub fn synthesize_workspace(
        config: &RsProjConfig,
        symtab: &GlobalSymbolTable,
        units: &[CompilationUnit],
    ) -> Result<SynthesizedCrateOutput, String> {
        let output = Self::synthesize_in_memory(config, symtab, units)?;

        fs::create_dir_all(config.out_cargo_dir.join("src"))
            .map_err(|e| format!("Failed to create output src directory: {}", e))?;

        fs::write(&output.cargo_toml_path, &output.cargo_toml_content)
            .map_err(|e| format!("Failed to write Cargo.toml: {}", e))?;

        fs::write(&output.lib_rs_path, &output.lib_rs_content)
            .map_err(|e| format!("Failed to write src/lib.rs: {}", e))?;

        for (rel_path, code) in &output.emitted_modules {
            let full_path = config.out_cargo_dir.join(rel_path);
            if let Some(parent) = full_path.parent() {
                fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            fs::write(&full_path, code)
                .map_err(|e| format!("Failed to write '{}': {}", full_path.display(), e))?;
        }

        for (rel_path, smap) in &output.sourcemaps {
            let map_path = config
                .out_cargo_dir
                .join(format!("{}.rsharp.map", rel_path));
            if let Some(parent) = map_path.parent() {
                fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            fs::write(&map_path, smap.to_map_file_string())
                .map_err(|e| format!("Failed to write '{}': {}", map_path.display(), e))?;
        }

        Ok(output)
    }

    pub fn emit_cargo_toml(config: &RsProjConfig) -> String {
        let mut out = String::from("# Auto-generated by rsharpc — DO NOT EDIT\n");
        out.push_str("[package]\n");
        out.push_str(&format!("name = \"{}\"\n", config.name));
        out.push_str(&format!("version = \"{}\"\n", config.version));
        out.push_str(&format!("edition = \"{}\"\n\n", config.edition));
        out.push_str("[dependencies]\n");
        for (crate_name, ver) in &config.cargo_dependencies {
            out.push_str(&format!("{} = \"{}\"\n", crate_name, ver));
        }
        out
    }

    pub fn emit_lib_rs(plans: &[NamespaceModulePlan]) -> String {
        let mut out = String::from("// Auto-generated by rsharpc — DO NOT EDIT\n");

        // Group namespaces by top-level and nested module segments
        let mut top_level_children: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
        let mut single_segment_mods: BTreeSet<String> = BTreeSet::new();

        for plan in plans {
            if plan.rust_mod_segments.len() == 1 {
                single_segment_mods.insert(plan.rust_mod_segments[0].clone());
            } else if plan.rust_mod_segments.len() >= 2 {
                let root = plan.rust_mod_segments[0].clone();
                let child = plan.rust_mod_segments[1..].join("::");
                top_level_children.entry(root).or_default().insert(child);
            }
        }

        for m in &single_segment_mods {
            if !top_level_children.contains_key(m) {
                out.push_str(&format!("pub mod {};\n", m));
            }
        }

        for (root, children) in &top_level_children {
            out.push_str(&format!("pub mod {} {{\n", root));
            for child in children {
                let leaf = child.split("::").last().unwrap_or(child);
                out.push_str(&format!("    pub mod {};\n", leaf));
            }
            out.push_str("}\n");
        }

        out
    }
}
