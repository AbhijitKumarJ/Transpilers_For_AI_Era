Here are the complete, raw individual source files for **Milestone 2 (Pass 1: `.rsproj` Workspace Loader, Virtual Namespace Aggregator, `GlobalSymbolTable`, Multi-File Circular Type Reference Collector, and M2 Verification Suite)** of the **RustSharp Prototype Transpiler (`rsharpc`)**.

---

### `src/project.rs`

```rust
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
    let canonical_path = path
        .canonicalize()
        .unwrap_or_else(|_| path.to_path_buf());
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
        *name = val.to_lowercase().replace('.', "_").replace('-', "_");
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
                    "name" => *name = val.to_lowercase().replace('.', "_").replace('-', "_"),
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

```

---

### `src/semantics/mod.rs`

```rust
pub mod collector;
pub mod symbols;

pub use collector::collect_global_symbols;
pub use symbols::{
    FieldSymbol, GlobalSymbolTable, MethodSymbol, NamespaceModulePlan, ParamSymbol,
    PropertySymbol, TypeSymbol,
};

```

---

### `src/semantics/symbols.rs`

```rust
use std::collections::{BTreeMap, HashMap};
use std::path::PathBuf;

use crate::diagnostics::SourceSpan;
use crate::frontend::ast::{
    AccessMod, BorrowMode, EffectSignature, FieldStorageMode, ImportDecl, PolymorphismStrategy,
    PrimitiveLowering, SymbolId, TypeKind, TypeRef,
};

/// Metadata for a registered field or synthesized record primary-constructor member.
#[derive(Clone, Debug)]
pub struct FieldSymbol {
    pub id: SymbolId,
    pub owner_type: SymbolId,
    pub name: String,
    pub access: AccessMod,
    pub is_readonly: bool,
    pub is_static: bool,
    pub ty: TypeRef,
    pub resolved_type_id: Option<SymbolId>,
    pub storage_mode: FieldStorageMode,
    pub span: SourceSpan,
}

/// Metadata for a registered property declaration.
#[derive(Clone, Debug)]
pub struct PropertySymbol {
    pub id: SymbolId,
    pub owner_type: SymbolId,
    pub name: String,
    pub access: AccessMod,
    pub is_static: bool,
    pub is_extern: bool,
    pub has_getter: bool,
    pub has_setter: bool,
    pub setter_access: Option<AccessMod>,
    pub ty: TypeRef,
    pub resolved_type_id: Option<SymbolId>,
    pub storage_mode: FieldStorageMode,
    pub primitive_lowering: PrimitiveLowering,
    pub span: SourceSpan,
}

/// Metadata for a method or constructor parameter in the global symbol table.
#[derive(Clone, Debug)]
pub struct ParamSymbol {
    pub id: SymbolId,
    pub name: String,
    pub ty: TypeRef,
    pub resolved_type_id: Option<SymbolId>,
    pub has_default: bool,
    pub explicit_constraint: Option<BorrowMode>,
    pub inferred_borrow: BorrowMode,
    pub span: SourceSpan,
}

/// Metadata for a registered method or constructor in the global symbol table.
#[derive(Clone, Debug)]
pub struct MethodSymbol {
    pub id: SymbolId,
    pub owner_type: SymbolId,
    pub name: String,
    pub is_constructor: bool,
    pub access: AccessMod,
    pub is_static: bool,
    pub is_async: bool,
    pub is_extern: bool,
    pub is_virtual: bool,
    pub is_override: bool,
    pub is_abstract: bool,
    pub type_params: Vec<String>,
    pub params: Vec<ParamSymbol>,
    pub return_type: TypeRef,
    pub resolved_return_type_id: Option<SymbolId>,
    pub explicit_throws: Option<TypeRef>,
    pub resolved_throws_type_id: Option<SymbolId>,
    pub inferred_self_borrow: BorrowMode,
    pub inferred_effect: EffectSignature,
    pub disambiguated_rust_name: String,
    pub primitive_lowering: PrimitiveLowering,
    pub linq_stage: Option<String>,
    pub span: SourceSpan,
}

/// Metadata for any registered `.rsharp` or `.d.rsharp` type archetype.
#[derive(Clone, Debug)]
pub struct TypeSymbol {
    pub id: SymbolId,
    pub name: String,
    pub namespace: Vec<String>,
    pub fqn: String,
    pub kind: TypeKind,
    pub access: AccessMod,
    pub is_abstract: bool,
    pub is_sealed: bool,
    pub is_partial: bool,
    pub is_static: bool,
    pub is_ambient_stub: bool,
    pub type_params: Vec<String>,
    pub base_types: Vec<TypeRef>,
    pub resolved_base_type_ids: Vec<SymbolId>,
    pub fields: Vec<SymbolId>,
    pub properties: Vec<SymbolId>,
    pub methods: Vec<SymbolId>,
    pub constructors: Vec<SymbolId>,
    pub inferred_polymorphism: PolymorphismStrategy,
    pub primitive_rust_target: Option<String>,
    pub primitive_param_type: Option<String>,
    pub has_disposable_drop: bool,
    pub source_files: Vec<String>,
    pub span: SourceSpan,
}

impl TypeSymbol {
    /// Returns true if the type is a value/Copy primitive or `record struct` / `struct`.
    pub fn is_value_or_copy_archetype(&self) -> bool {
        matches!(
            self.kind,
            TypeKind::ValueStruct
                | TypeKind::Record { is_struct: true }
                | TypeKind::Enum
                | TypeKind::PrimitiveClass { is_struct: true }
        )
    }
}

/// Synthesized Rust module layout entry for a logical RustSharp namespace.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NamespaceModulePlan {
    /// Logical RustSharp namespace segments (e.g., `["Commerce", "Checkout"]`).
    pub namespace: Vec<String>,
    /// Lowercase snake_case Rust module path segments (e.g., `["commerce", "checkout"]`).
    pub rust_mod_segments: Vec<String>,
    /// Target relative `.rs` file inside the synthesized Cargo crate (e.g., `"src/commerce/checkout.rs"`).
    pub target_rs_file: String,
    /// Non-ambient `TypeSymbol` IDs aggregated into this module across all `.rsharp` files.
    pub type_ids: Vec<SymbolId>,
}

/// Whole-project symbol table populated during Pass 1 (`collector.rs`).
/// Decouples physical directory structure from logical `namespace` declarations and
/// resolves circular cross-file type references.
#[derive(Clone, Debug, Default)]
pub struct GlobalSymbolTable {
    next_id: u32,
    pub types: HashMap<SymbolId, TypeSymbol>,
    pub fields: HashMap<SymbolId, FieldSymbol>,
    pub properties: HashMap<SymbolId, PropertySymbol>,
    pub methods: HashMap<SymbolId, MethodSymbol>,
    /// Virtual namespace (`["Commerce", "Checkout"]`) -> ordered list of `TypeSymbol` IDs.
    pub namespaces: BTreeMap<Vec<String>, Vec<SymbolId>>,
    /// Fully-qualified name (`"Commerce.Checkout.OrderHandler"`) -> `SymbolId`.
    pub fqn_to_symbol: HashMap<String, SymbolId>,
    /// Unqualified short name (`"OrderHandler"`) -> list of candidate `SymbolId`s across namespaces.
    pub short_name_index: HashMap<String, Vec<SymbolId>>,
    /// Maps external Rust crate aliases (`extern using rust_decimal::Decimal as Decimal;`) to their crate path.
    pub extern_crate_aliases: HashMap<String, Vec<String>>,
    /// Co-located `.rs` files discovered in the workspace.
    pub colocated_rs_files: Vec<PathBuf>,
}

impl GlobalSymbolTable {
    pub fn new() -> Self {
        Self {
            next_id: 1,
            ..Self::default()
        }
    }

    pub fn alloc_symbol_id(&mut self) -> SymbolId {
        let id = SymbolId(self.next_id);
        self.next_id += 1;
        id
    }

    /// Registers a `TypeSymbol` or merges into an existing `partial` type in the same namespace.
    pub fn register_or_merge_type(&mut self, sym: TypeSymbol) -> SymbolId {
        if let Some(&existing_id) = self.fqn_to_symbol.get(&sym.fqn) {
            if let Some(existing) = self.types.get_mut(&existing_id) {
                for f in sym.source_files {
                    if !existing.source_files.contains(&f) {
                        existing.source_files.push(f);
                    }
                }
                for bt in sym.base_types {
                    if !existing.base_types.contains(&bt) {
                        existing.base_types.push(bt);
                    }
                }
                if existing.primitive_rust_target.is_none() {
                    existing.primitive_rust_target = sym.primitive_rust_target;
                }
                if existing.primitive_param_type.is_none() {
                    existing.primitive_param_type = sym.primitive_param_type;
                }
                return existing_id;
            }
        }

        let id = sym.id;
        let fqn = sym.fqn.clone();
        let short_name = sym.name.clone();
        let ns = sym.namespace.clone();

        self.types.insert(id, sym);
        self.fqn_to_symbol.insert(fqn, id);
        self.short_name_index
            .entry(short_name)
            .or_default()
            .push(id);

        let ns_list = self.namespaces.entry(ns).or_default();
        if !ns_list.contains(&id) {
            ns_list.push(id);
        }

        id
    }

    /// Resolves a type name within the context of `current_ns` and file `imports`.
    /// Resolution priority:
    /// 1. Exact fully-qualified name match (`"Commerce.Domain.Order"`).
    /// 2. Current namespace (`"{current_ns}.{name}"`) and parent enclosing namespaces.
    /// 3. Imported RustSharp namespaces (`using Commerce.Domain;`).
    /// 4. Ambient standard library namespace (`RustSharp.Core.{name}`).
    /// 5. Unambiguous global short-name match across the workspace.
    pub fn resolve_type(
        &self,
        name: &str,
        current_ns: &[String],
        imports: &[ImportDecl],
    ) -> Option<SymbolId> {
        let mapped_name = match name {
            "string" => "String",
            other => other,
        };

        // 1. Direct FQN match
        if let Some(&id) = self.fqn_to_symbol.get(mapped_name) {
            return Some(id);
        }

        // 2. Current namespace and enclosing parent namespaces
        for prefix_len in (1..=current_ns.len()).rev() {
            let prefix = current_ns[..prefix_len].join(".");
            let candidate_fqn = format!("{}.{}", prefix, mapped_name);
            if let Some(&id) = self.fqn_to_symbol.get(&candidate_fqn) {
                return Some(id);
            }
        }

        // 3. Explicit `using <Namespace>;` imports in the compilation unit
        for imp in imports {
            if !imp.is_extern_crate {
                let imp_ns = imp.path.join(".");
                let candidate_fqn = format!("{}.{}", imp_ns, mapped_name);
                if let Some(&id) = self.fqn_to_symbol.get(&candidate_fqn) {
                    return Some(id);
                }
            }
        }

        // 4. Ambient `RustSharp.Core` standard library lookup
        let std_fqn = format!("RustSharp.Core.{}", mapped_name);
        if let Some(&id) = self.fqn_to_symbol.get(&std_fqn) {
            return Some(id);
        }

        // 5. Unambiguous short-name fallback
        if let Some(candidates) = self.short_name_index.get(mapped_name) {
            if candidates.len() == 1 {
                return Some(candidates[0]);
            }
        }

        None
    }

    /// Resolves a `TypeRef` AST node against the symbol table.
    pub fn resolve_type_ref(
        &self,
        type_ref: &TypeRef,
        current_ns: &[String],
        imports: &[ImportDecl],
    ) -> Option<SymbolId> {
        if type_ref.path.len() > 1 {
            let fqn = type_ref.qualified_name();
            if let Some(id) = self.resolve_type(&fqn, current_ns, imports) {
                return Some(id);
            }
        }
        self.resolve_type(type_ref.short_name(), current_ns, imports)
    }

    /// Checks whether an identifier matches an `extern using` Rust crate import or alias.
    pub fn is_extern_crate_type(&self, type_ref: &TypeRef, imports: &[ImportDecl]) -> bool {
        let first_seg = type_ref.path.first().map(|s| s.as_str()).unwrap_or("");
        let short = type_ref.short_name();

        if self.extern_crate_aliases.contains_key(first_seg)
            || self.extern_crate_aliases.contains_key(short)
        {
            return true;
        }

        for imp in imports {
            if imp.is_extern_crate {
                if let Some(alias) = &imp.alias {
                    if alias == first_seg || alias == short {
                        return true;
                    }
                }
                if let Some(last) = imp.path.last() {
                    if last == first_seg || last == short {
                        return true;
                    }
                }
                if let Some(root) = imp.path.first() {
                    if root == first_seg {
                        return true;
                    }
                }
            }
        }
        false
    }

    /// Returns true if the given `TypeRef` represents a built-in C# value primitive (`int`, `decimal`, `bool`, etc.).
    pub fn is_builtin_primitive(type_ref: &TypeRef) -> bool {
        if type_ref.is_primitive_keyword {
            return true;
        }
        matches!(
            type_ref.short_name(),
            "void"
                | "bool"
                | "byte"
                | "sbyte"
                | "short"
                | "ushort"
                | "int"
                | "uint"
                | "long"
                | "ulong"
                | "float"
                | "double"
                | "decimal"
                | "char"
                | "string"
                | "Func"
                | "Action"
                | "Attribute"
        )
    }

    /// Computes the snake_case Rust module path segments for a logical namespace.
    /// Example: `["Commerce", "Checkout"]` -> `["commerce", "checkout"]`.
    pub fn rust_module_segments(namespace: &[String]) -> Vec<String> {
        if namespace.is_empty() {
            return vec!["root".to_string()];
        }
        namespace
            .iter()
            .map(|seg| pascal_to_snake_case(seg))
            .collect()
    }

    /// Computes the synthesized relative `.rs` file path for a logical namespace.
    /// Example: `["Commerce", "Checkout"]` -> `"src/commerce/checkout.rs"`.
    pub fn synthesized_rust_module_path(namespace: &[String]) -> String {
        let segs = Self::rust_module_segments(namespace);
        format!("src/{}.rs", segs.join("/"))
    }

    /// Builds the deterministic list of synthesized Rust modules for all non-ambient namespaces.
    pub fn build_namespace_module_plans(&self) -> Vec<NamespaceModulePlan> {
        let mut plans = Vec::new();

        for (ns, type_ids) in &self.namespaces {
            let emitted_types: Vec<SymbolId> = type_ids
                .iter()
                .copied()
                .filter(|id| {
                    self.types
                        .get(id)
                        .map(|t| {
                            !t.is_ambient_stub
                                && !matches!(t.kind, TypeKind::PrimitiveClass { .. })
                        })
                        .unwrap_or(false)
                })
                .collect();

            if emitted_types.is_empty() {
                continue;
            }

            plans.push(NamespaceModulePlan {
                namespace: ns.clone(),
                rust_mod_segments: Self::rust_module_segments(ns),
                target_rs_file: Self::synthesized_rust_module_path(ns),
                type_ids: emitted_types,
            });
        }

        plans
    }
}

/// Converts a `PascalCase` or `camelCase` identifier into idiomatic Rust `snake_case`.
pub fn pascal_to_snake_case(ident: &str) -> String {
    let mut out = String::with_capacity(ident.len() + 4);
    let chars: Vec<char> = ident.chars().collect();

    for (i, &ch) in chars.iter().enumerate() {
        if ch.is_uppercase() {
            if i > 0 {
                let prev = chars[i - 1];
                let next_is_lower = chars.get(i + 1).map(|c| c.is_lowercase()).unwrap_or(false);
                if prev.is_lowercase() || prev.is_ascii_digit() || (prev.is_uppercase() && next_is_lower) {
                    out.push('_');
                }
            }
            for lower in ch.to_lowercase() {
                out.push(lower);
            }
        } else {
            out.push(ch);
        }
    }
    out
}

```

---

### `src/semantics/collector.rs`

```rust
use crate::diagnostics::DiagnosticEngine;
use crate::frontend::ast::{
    AccessMod, BorrowMode, CompilationUnit, FieldStorageMode, ImportDecl, MemberDecl,
    PolymorphismStrategy, SymbolId, TypeDecl, TypeKind, TypeRef,
};
use crate::semantics::symbols::{
    pascal_to_snake_case, FieldSymbol, GlobalSymbolTable, MethodSymbol, ParamSymbol,
    PropertySymbol, TypeSymbol,
};

/// Pass 1 Whole-Project Symbol Collector & Virtual Namespace Aggregator.
///
/// Runs three sub-passes across all parsed `CompilationUnit`s (`.d.rsharp` and `.rsharp`):
/// - **Pass 1A:** Registers every type archetype into `GlobalSymbolTable` and aggregates
///   virtual namespaces regardless of physical file path.
/// - **Pass 1B:** Registers all fields, properties, constructors, methods, and record
///   primary constructor parameters with unique `SymbolId`s.
/// - **Pass 1C:** Resolves all cross-file and mutually recursive (circular) type references
///   across base types, fields, properties, parameters, return types, and `throws` clauses.
pub fn collect_global_symbols(
    units: &mut [CompilationUnit],
    symtab: &mut GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    // ------------------------------------------------------------------------
    // PASS 1A: Register `extern using` aliases and all top-level TypeDecls
    // ------------------------------------------------------------------------
    for unit in units.iter_mut() {
        for imp in &unit.imports {
            if imp.is_extern_crate {
                let key = imp
                    .alias
                    .clone()
                    .or_else(|| imp.path.last().cloned())
                    .unwrap_or_default();
                if !key.is_empty() {
                    symtab.extern_crate_aliases.insert(key, imp.path.clone());
                }
            }
        }

        for type_decl in &mut unit.types {
            let fqn = if unit.namespace.is_empty() {
                type_decl.name.clone()
            } else {
                format!("{}.{}", unit.namespace.join("."), type_decl.name)
            };

            let provisional_id = symtab.alloc_symbol_id();
            let sym = TypeSymbol {
                id: provisional_id,
                name: type_decl.name.clone(),
                namespace: unit.namespace.clone(),
                fqn,
                kind: type_decl.kind,
                access: type_decl.access,
                is_abstract: type_decl.is_abstract,
                is_sealed: type_decl.is_sealed,
                is_partial: type_decl.is_partial,
                is_static: type_decl.is_static,
                is_ambient_stub: unit.is_ambient_stub,
                type_params: type_decl.type_params.clone(),
                base_types: type_decl.base_types.clone(),
                resolved_base_type_ids: Vec::new(),
                fields: Vec::new(),
                properties: Vec::new(),
                methods: Vec::new(),
                constructors: Vec::new(),
                inferred_polymorphism: PolymorphismStrategy::Unresolved,
                primitive_rust_target: type_decl.primitive_rust_target.clone(),
                primitive_param_type: type_decl.primitive_param_type.clone(),
                has_disposable_drop: type_decl.has_disposable_drop,
                source_files: vec![unit.filename.clone()],
                span: type_decl.span.clone(),
            };

            let registered_id = symtab.register_or_merge_type(sym);
            type_decl.id = registered_id;
        }
    }

    // ------------------------------------------------------------------------
    // PASS 1B: Register members and resolve cross-file / circular TypeRefs
    // ------------------------------------------------------------------------
    for unit in units.iter_mut() {
        let current_ns = unit.namespace.clone();
        let imports = unit.imports.clone();
        let is_ambient = unit.is_ambient_stub;

        for type_decl in &mut unit.types {
            collect_and_resolve_type_members(
                type_decl,
                &current_ns,
                &imports,
                is_ambient,
                symtab,
                diag,
            );
        }
    }
}

fn collect_and_resolve_type_members(
    type_decl: &mut TypeDecl,
    current_ns: &[String],
    imports: &[ImportDecl],
    is_ambient: bool,
    symtab: &mut GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) {
    let owner_id = type_decl.id;
    let mut type_generics = type_decl.type_params.clone();

    // 1. Resolve base types / interfaces
    let mut resolved_bases = Vec::new();
    let mut implements_disposable = false;

    for base_ref in &type_decl.base_types {
        if base_ref.short_name() == "IDisposable" {
            implements_disposable = true;
        }
        if let Some(base_id) = verify_and_resolve_type_ref(
            base_ref,
            current_ns,
            imports,
            &type_generics,
            is_ambient,
            symtab,
            diag,
        ) {
            if !resolved_bases.contains(&base_id) {
                resolved_bases.push(base_id);
            }
        }
    }

    if implements_disposable {
        type_decl.has_disposable_drop = true;
    }

    // 2. Register primary constructor parameters on `record` declarations as public fields
    let mut registered_fields = Vec::new();
    let mut registered_props = Vec::new();
    let mut registered_methods = Vec::new();
    let mut registered_ctors = Vec::new();

    for param in &mut type_decl.primary_ctor_params {
        let field_id = symtab.alloc_symbol_id();
        param.id = field_id;
        let resolved_ty = verify_and_resolve_type_ref(
            &param.ty,
            current_ns,
            imports,
            &type_generics,
            is_ambient,
            symtab,
            diag,
        );

        let field_sym = FieldSymbol {
            id: field_id,
            owner_type: owner_id,
            name: param.name.clone(),
            access: AccessMod::Public,
            is_readonly: false,
            is_static: false,
            ty: param.ty.clone(),
            resolved_type_id: resolved_ty,
            storage_mode: FieldStorageMode::Plain,
            span: param.span.clone(),
        };
        symtab.fields.insert(field_id, field_sym);
        registered_fields.push(field_id);
    }

    // 3. Register explicit fields, properties, constructors, methods, and indexers
    for member in &mut type_decl.members {
        match member {
            MemberDecl::Field(field) => {
                let field_id = symtab.alloc_symbol_id();
                field.id = field_id;
                let resolved_ty = verify_and_resolve_type_ref(
                    &field.ty,
                    current_ns,
                    imports,
                    &type_generics,
                    is_ambient,
                    symtab,
                    diag,
                );

                let storage_mode = match type_decl.kind {
                    TypeKind::ServiceClass => FieldStorageMode::ArcShared,
                    TypeKind::SharedClass => FieldStorageMode::RwLockShared,
                    _ => FieldStorageMode::Plain,
                };
                field.resolved_storage = storage_mode;

                symtab.fields.insert(
                    field_id,
                    FieldSymbol {
                        id: field_id,
                        owner_type: owner_id,
                        name: field.name.clone(),
                        access: field.access,
                        is_readonly: field.is_readonly
                            || matches!(type_decl.kind, TypeKind::ServiceClass),
                        is_static: field.is_static,
                        ty: field.ty.clone(),
                        resolved_type_id: resolved_ty,
                        storage_mode,
                        span: field.span.clone(),
                    },
                );
                registered_fields.push(field_id);
            }

            MemberDecl::Property(prop) => {
                let prop_id = symtab.alloc_symbol_id();
                prop.id = prop_id;
                let resolved_ty = verify_and_resolve_type_ref(
                    &prop.ty,
                    current_ns,
                    imports,
                    &type_generics,
                    is_ambient,
                    symtab,
                    diag,
                );

                let has_getter = prop.accessors.iter().any(|a| a.is_get);
                let setter = prop.accessors.iter().find(|a| !a.is_get);
                let has_setter = setter.is_some();
                let setter_access = setter.and_then(|s| s.access);

                let storage_mode = match type_decl.kind {
                    TypeKind::ServiceClass => FieldStorageMode::ArcShared,
                    TypeKind::SharedClass => FieldStorageMode::RwLockShared,
                    _ => FieldStorageMode::Plain,
                };
                prop.resolved_storage = storage_mode;

                symtab.properties.insert(
                    prop_id,
                    PropertySymbol {
                        id: prop_id,
                        owner_type: owner_id,
                        name: prop.name.clone(),
                        access: prop.access,
                        is_static: prop.is_static,
                        is_extern: prop.is_extern,
                        has_getter,
                        has_setter,
                        setter_access,
                        ty: prop.ty.clone(),
                        resolved_type_id: resolved_ty,
                        storage_mode,
                        primitive_lowering: prop.primitive_lowering.clone(),
                        span: prop.span.clone(),
                    },
                );
                registered_props.push(prop_id);
            }

            MemberDecl::Constructor(ctor) => {
                let ctor_id = symtab.alloc_symbol_id();
                ctor.id = ctor_id;

                let mut param_syms = Vec::new();
                for param in &mut ctor.params {
                    let pid = symtab.alloc_symbol_id();
                    param.id = pid;
                    let resolved_pty = verify_and_resolve_type_ref(
                        &param.ty,
                        current_ns,
                        imports,
                        &type_generics,
                        is_ambient,
                        symtab,
                        diag,
                    );
                    param_syms.push(ParamSymbol {
                        id: pid,
                        name: param.name.clone(),
                        ty: param.ty.clone(),
                        resolved_type_id: resolved_pty,
                        has_default: param.default_value.is_some(),
                        explicit_constraint: param.explicit_constraint,
                        inferred_borrow: param.inferred_borrow,
                        span: param.span.clone(),
                    });
                }

                if ctor.disambiguated_rust_name.is_empty() {
                    ctor.disambiguated_rust_name = String::from("new");
                }

                let self_ty_ref = TypeRef {
                    span: ctor.span.clone(),
                    path: vec![type_decl.name.clone()],
                    type_args: Vec::new(),
                    is_nullable: false,
                    is_primitive_keyword: false,
                };

                symtab.methods.insert(
                    ctor_id,
                    MethodSymbol {
                        id: ctor_id,
                        owner_type: owner_id,
                        name: ctor.name.clone(),
                        is_constructor: true,
                        access: ctor.access,
                        is_static: true,
                        is_async: false,
                        is_extern: ctor.is_extern,
                        is_virtual: false,
                        is_override: false,
                        is_abstract: false,
                        type_params: Vec::new(),
                        params: param_syms,
                        return_type: self_ty_ref,
                        resolved_return_type_id: Some(owner_id),
                        explicit_throws: None,
                        resolved_throws_type_id: None,
                        inferred_self_borrow: BorrowMode::Unresolved,
                        inferred_effect: crate::frontend::ast::EffectSignature::Infallible,
                        disambiguated_rust_name: ctor.disambiguated_rust_name.clone(),
                        primitive_lowering: ctor.primitive_lowering.clone(),
                        linq_stage: None,
                        span: ctor.span.clone(),
                    },
                );
                registered_ctors.push(ctor_id);
            }

            MemberDecl::Method(method) => {
                let method_id = symtab.alloc_symbol_id();
                method.id = method_id;

                if method.name == "Dispose" && method.params.is_empty() {
                    type_decl.has_disposable_drop = true;
                }

                // Combine enclosing type generic parameters with method-level generic parameters
                let mut combined_generics = type_generics.clone();
                for mp in &method.type_params {
                    if !combined_generics.contains(mp) {
                        combined_generics.push(mp.clone());
                    }
                }

                let mut param_syms = Vec::new();
                for param in &mut method.params {
                    let pid = symtab.alloc_symbol_id();
                    param.id = pid;
                    let resolved_pty = verify_and_resolve_type_ref(
                        &param.ty,
                        current_ns,
                        imports,
                        &combined_generics,
                        is_ambient,
                        symtab,
                        diag,
                    );
                    param_syms.push(ParamSymbol {
                        id: pid,
                        name: param.name.clone(),
                        ty: param.ty.clone(),
                        resolved_type_id: resolved_pty,
                        has_default: param.default_value.is_some(),
                        explicit_constraint: param.explicit_constraint,
                        inferred_borrow: param.inferred_borrow,
                        span: param.span.clone(),
                    });
                }

                let resolved_ret = verify_and_resolve_type_ref(
                    &method.return_type,
                    current_ns,
                    imports,
                    &combined_generics,
                    is_ambient,
                    symtab,
                    diag,
                );

                let resolved_throws = if let Some(throws_ref) = &method.explicit_throws {
                    verify_and_resolve_type_ref(
                        throws_ref,
                        current_ns,
                        imports,
                        &combined_generics,
                        is_ambient,
                        symtab,
                        diag,
                    )
                } else {
                    None
                };

                if method.disambiguated_rust_name.is_empty() {
                    method.disambiguated_rust_name = pascal_to_snake_case(&method.name);
                }

                symtab.methods.insert(
                    method_id,
                    MethodSymbol {
                        id: method_id,
                        owner_type: owner_id,
                        name: method.name.clone(),
                        is_constructor: false,
                        access: method.access,
                        is_static: method.is_static,
                        is_async: method.is_async,
                        is_extern: method.is_extern,
                        is_virtual: method.is_virtual,
                        is_override: method.is_override,
                        is_abstract: method.is_abstract,
                        type_params: method.type_params.clone(),
                        params: param_syms,
                        return_type: method.return_type.clone(),
                        resolved_return_type_id: resolved_ret,
                        explicit_throws: method.explicit_throws.clone(),
                        resolved_throws_type_id: resolved_throws,
                        inferred_self_borrow: method.inferred_self_borrow,
                        inferred_effect: method.inferred_effect.clone(),
                        disambiguated_rust_name: method.disambiguated_rust_name.clone(),
                        primitive_lowering: method.primitive_lowering.clone(),
                        linq_stage: method.linq_stage.clone(),
                        span: method.span.clone(),
                    },
                );
                registered_methods.push(method_id);
            }

            MemberDecl::Indexer(idx) => {
                let idx_id = symtab.alloc_symbol_id();
                idx.id = idx_id;
                let _ = verify_and_resolve_type_ref(
                    &idx.ty,
                    current_ns,
                    imports,
                    &type_generics,
                    is_ambient,
                    symtab,
                    diag,
                );
                for param in &mut idx.params {
                    param.id = symtab.alloc_symbol_id();
                    let _ = verify_and_resolve_type_ref(
                        &param.ty,
                        current_ns,
                        imports,
                        &type_generics,
                        is_ambient,
                        symtab,
                        diag,
                    );
                }
            }
        }
    }

    // 4. Resolve types inside enum variant payloads
    for variant in &mut type_decl.enum_variants {
        for param in &mut variant.payload {
            param.id = symtab.alloc_symbol_id();
            let _ = verify_and_resolve_type_ref(
                &param.ty,
                current_ns,
                imports,
                &type_generics,
                is_ambient,
                symtab,
                diag,
            );
        }
    }

    // 5. Update the owning TypeSymbol in GlobalSymbolTable
    if let Some(type_sym) = symtab.types.get_mut(&owner_id) {
        for base_id in resolved_bases {
            if !type_sym.resolved_base_type_ids.contains(&base_id) {
                type_sym.resolved_base_type_ids.push(base_id);
            }
        }
        type_sym.fields.extend(registered_fields);
        type_sym.properties.extend(registered_props);
        type_sym.methods.extend(registered_methods);
        type_sym.constructors.extend(registered_ctors);
        if type_decl.has_disposable_drop {
            type_sym.has_disposable_drop = true;
        }
    }
}

fn verify_and_resolve_type_ref(
    type_ref: &TypeRef,
    current_ns: &[String],
    imports: &[ImportDecl],
    active_type_params: &[String],
    is_ambient: bool,
    symtab: &GlobalSymbolTable,
    diag: &mut DiagnosticEngine,
) -> Option<SymbolId> {
    // Recursively verify generic type arguments first (e.g., `List<Order>`, `Dictionary<string, User>`)
    for arg in &type_ref.type_args {
        let _ = verify_and_resolve_type_ref(
            arg,
            current_ns,
            imports,
            active_type_params,
            is_ambient,
            symtab,
            diag,
        );
    }

    let short = type_ref.short_name();

    // 1. Check if it's an active generic type parameter (`T`, `TKey`, `TValue`, `TResult`)
    if type_ref.path.len() == 1 && active_type_params.iter().any(|tp| tp == short) {
        return None;
    }

    // 2. Resolve against registered `.rsharp` and `.d.rsharp` symbols
    if let Some(sym_id) = symtab.resolve_type_ref(type_ref, current_ns, imports) {
        return Some(sym_id);
    }

    // 3. Built-in C# primitive keywords (`int`, `decimal`, `bool`, `void`, `string`, etc.)
    if GlobalSymbolTable::is_builtin_primitive(type_ref) {
        return None;
    }

    // 4. External Rust crate types imported via `extern using`
    if symtab.is_extern_crate_type(type_ref, imports) {
        return None;
    }

    // 5. Well-known standard library primitives if running without `RustSharp.Core.d.rsharp` loaded
    if matches!(
        short,
        "List"
            | "Dictionary"
            | "HashSet"
            | "ReadOnlySpan"
            | "Span"
            | "Option"
            | "SharedState"
            | "IEnumerable"
            | "IDisposable"
            | "IEquatable"
            | "IComparable"
            | "KeyValuePair"
            | "TimeSpan"
            | "Console"
    ) {
        return None;
    }

    if !is_ambient {
        diag.report_unresolved_symbol(type_ref.span.clone(), &type_ref.qualified_name());
    }
    None
}

```

---

### `src/lib.rs`

```rust
pub mod diagnostics;
pub mod frontend;
pub mod project;
pub mod semantics;

use diagnostics::DiagnosticEngine;
use frontend::{CompilationUnit, Lexer, Parser};
use semantics::{collect_global_symbols, GlobalSymbolTable};

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

```

---

### `tests/m2_namespace_resolution_tests.rs`

```rust
use std::fs;
use std::time::{SystemTime, UNIX_EPOCH};

use rsharpc::analyze_workspace_pass1;
use rsharpc::diagnostics::DiagnosticCode;
use rsharpc::frontend::ast::{FieldStorageMode, TypeKind};
use rsharpc::project::load_rsproj;

#[test]
fn test_decoupled_folders_and_circular_cross_file_type_resolution() {
    // Two `.rsharp` files in completely different physical folders (`Domain/Customer.rsharp`
    // and `Features/Sales/Order.rsharp`) that reference each other's types circularly.
    let customer_src = r#"
namespace Commerce.Domain;

using Commerce.Sales;

public record Customer(int Id, string Name, List<Order> RecentOrders);

public service class CustomerDirectory
{
    public Order? FindLatestOrder(Customer customer)
    {
        return null;
    }
}
"#;

    let order_src = r#"
namespace Commerce.Sales;

using Commerce.Domain;

public record Order(int OrderId, Customer Buyer, decimal Amount);

public service class OrderProcessor
{
    private readonly CustomerDirectory _directory;

    public OrderProcessor(CustomerDirectory directory) => _directory = directory;

    public Customer GetOrderBuyer(Order order) => order.Buyer;
}
"#;

    let files = [
        ("src/Domain/Entities/Customer.rsharp", customer_src),
        ("src/Features/Sales/Handlers/Order.rsharp", order_src),
    ];

    let (_units, symtab, diag) = analyze_workspace_pass1(&files);
    assert!(
        !diag.has_errors(),
        "Expected circular cross-file references to resolve cleanly, got: {}",
        diag.format_all()
    );

    // Verify both namespaces were registered
    let domain_ns = vec!["Commerce".to_string(), "Domain".to_string()];
    let sales_ns = vec!["Commerce".to_string(), "Sales".to_string()];
    assert!(symtab.namespaces.contains_key(&domain_ns));
    assert!(symtab.namespaces.contains_key(&sales_ns));

    // Verify Customer and Order symbol IDs
    let customer_id = symtab
        .fqn_to_symbol
        .get("Commerce.Domain.Customer")
        .copied()
        .expect("Customer symbol missing");
    let order_id = symtab
        .fqn_to_symbol
        .get("Commerce.Sales.Order")
        .copied()
        .expect("Order symbol missing");
    let directory_id = symtab
        .fqn_to_symbol
        .get("Commerce.Domain.CustomerDirectory")
        .copied()
        .expect("CustomerDirectory symbol missing");
    let processor_id = symtab
        .fqn_to_symbol
        .get("Commerce.Sales.OrderProcessor")
        .copied()
        .expect("OrderProcessor symbol missing");

    // Verify Order's `Buyer` primary constructor field resolved directly to `Customer`
    let order_sym = &symtab.types[&order_id];
    assert_eq!(order_sym.fields.len(), 3);
    let buyer_field = &symtab.fields[&order_sym.fields[1]];
    assert_eq!(buyer_field.name, "Buyer");
    assert_eq!(buyer_field.resolved_type_id, Some(customer_id));

    // Verify OrderProcessor's `_directory` field resolved to `CustomerDirectory` and has `ArcShared` storage
    let processor_sym = &symtab.types[&processor_id];
    assert_eq!(processor_sym.kind, TypeKind::ServiceClass);
    let dir_field = &symtab.fields[&processor_sym.fields[0]];
    assert_eq!(dir_field.name, "_directory");
    assert_eq!(dir_field.resolved_type_id, Some(directory_id));
    assert_eq!(dir_field.storage_mode, FieldStorageMode::ArcShared);
    assert!(dir_field.is_readonly);

    // Verify CustomerDirectory.FindLatestOrder return type resolved to `Order`
    let dir_sym = &symtab.types[&directory_id];
    let find_method = &symtab.methods[&dir_sym.methods[0]];
    assert_eq!(find_method.name, "FindLatestOrder");
    assert_eq!(find_method.resolved_return_type_id, Some(order_id));
    assert_eq!(find_method.params[0].resolved_type_id, Some(customer_id));
}

#[test]
fn test_virtual_namespace_aggregation_across_multiple_files() {
    // Three files in different subdirectories all declaring `namespace Commerce.Checkout;`
    let file_a = r#"
namespace Commerce.Checkout;

public record CartItem(int Sku, int Quantity);
"#;

    let file_b = r#"
namespace Commerce.Checkout;

public record CheckoutReceipt(int ReceiptId, List<CartItem> Items);
"#;

    let file_c = r#"
namespace Commerce.Checkout;

public partial service class CheckoutCoordinator
{
    public CheckoutReceipt BuildReceipt(List<CartItem> items) => new CheckoutReceipt(1, items);
}
"#;

    let file_d = r#"
namespace Commerce.Checkout;

public partial service class CheckoutCoordinator
{
    public int CountItems(CheckoutReceipt receipt) => 0;
}
"#;

    let files = [
        ("Features/Cart/CartItem.rsharp", file_a),
        ("Features/Receipts/CheckoutReceipt.rsharp", file_b),
        ("Services/CheckoutCoordinator.Part1.rsharp", file_c),
        ("Services/CheckoutCoordinator.Part2.rsharp", file_d),
    ];

    let (_units, symtab, diag) = analyze_workspace_pass1(&files);
    assert!(!diag.has_errors(), "Diagnostics: {}", diag.format_all());

    let plans = symtab.build_namespace_module_plans();
    assert_eq!(plans.len(), 1);

    let plan = &plans[0];
    assert_eq!(plan.namespace, vec!["Commerce", "Checkout"]);
    assert_eq!(plan.rust_mod_segments, vec!["commerce", "checkout"]);
    assert_eq!(plan.target_rs_file, "src/commerce/checkout.rs");

    // Partial class `CheckoutCoordinator` should be merged into a single TypeSymbol (3 unique types total)
    assert_eq!(plan.type_ids.len(), 3);

    let coord_id = symtab.fqn_to_symbol["Commerce.Checkout.CheckoutCoordinator"];
    let coord_sym = &symtab.types[&coord_id];
    assert_eq!(coord_sym.methods.len(), 2);
    assert_eq!(coord_sym.source_files.len(), 2);
}

#[test]
fn test_reports_unresolved_symbol_diagnostic_with_exact_span() {
    let bad_src = r#"
namespace Commerce.Orders;

public service class BrokenService
{
    public NonExistentDto LoadItem(int id)
    {
        return null;
    }
}
"#;

    let (_units, _symtab, diag) = analyze_workspace_pass1(&[("BrokenService.rsharp", bad_src)]);
    assert!(diag.has_errors());
    assert_eq!(diag.diagnostics.len(), 1);

    let err = &diag.diagnostics[0];
    assert_eq!(err.code, DiagnosticCode::UnresolvedSymbol);
    assert!(err.message.contains("NonExistentDto"));
    assert_eq!(err.span.filename, "BrokenService.rsharp");
    assert_eq!(err.span.start_line, 6);
}

#[test]
fn test_rsproj_loader_discovers_rsharp_stubs_and_colocated_rs_files() {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let temp_root = std::env::temp_dir().join(format!("rsharp_m2_test_{}", unique));
    let ingest_dir = temp_root.join("Ingest");
    let features_dir = temp_root.join("Features").join("Checkout");
    fs::create_dir_all(&ingest_dir).unwrap();
    fs::create_dir_all(&features_dir).unwrap();

    let rsproj_xml = r#"
<Project Sdk="RustSharp.Sdk">
  <PropertyGroup>
    <AssemblyName>Commerce.Core</AssemblyName>
    <Version>0.2.0</Version>
    <RustEdition>2021</RustEdition>
    <OutputPath>build/cargo_out</OutputPath>
  </PropertyGroup>
  <ItemGroup>
    <CargoCrate Include="rust_decimal" Version="1.36" />
    <CargoCrate Include="tokio" Version="1.40" />
  </ItemGroup>
</Project>
"#;

    let rsproj_path = temp_root.join("Commerce.Core.rsproj");
    fs::write(&rsproj_path, rsproj_xml).unwrap();
    fs::write(
        temp_root.join("RustSharp.Core.d.rsharp"),
        "namespace RustSharp.Core;\n[MapsTo(\"std::vec::Vec\")]\npublic primitive class List<T> { }\n",
    )
    .unwrap();
    fs::write(
        features_dir.join("OrderHandler.rsharp"),
        "namespace Commerce.Checkout;\npublic record Order(int Id);\n",
    )
    .unwrap();
    fs::write(
        ingest_dir.join("PacketHeader.rsharp"),
        "namespace Commerce.Ingest;\npublic partial struct PacketHeader { public uint Magic; }\n",
    )
    .unwrap();
    fs::write(
        ingest_dir.join("PacketHeader.rs"),
        "// Co-located raw Rust implementation\n",
    )
    .unwrap();

    let cfg = load_rsproj(&rsproj_path, None).expect("Failed to load .rsproj");
    assert_eq!(cfg.name, "commerce_core");
    assert_eq!(cfg.version, "0.2.0");
    assert_eq!(cfg.edition, "2021");
    assert_eq!(cfg.cargo_dependencies.len(), 2);
    assert_eq!(
        cfg.cargo_dependencies[0],
        ("rust_decimal".to_string(), "1.36".to_string())
    );
    assert_eq!(cfg.stub_files.len(), 1);
    assert_eq!(cfg.rsharp_files.len(), 2);
    assert_eq!(cfg.colocated_rs_files.len(), 1);

    let _ = fs::remove_dir_all(&temp_root);
}

```

---

Would you like me to continue with the raw individual files for **Milestone 3 (Pass 2A: `src/semantics/archetype_analyzer.rs`, `src/semantics/hierarchy_lowerer.rs`, `src/semantics/overload_resolver.rs`, and `tests/m3_polymorphism_overload_tests.rs`)** next?
