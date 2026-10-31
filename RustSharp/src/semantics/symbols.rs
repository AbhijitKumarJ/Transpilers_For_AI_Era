use std::collections::{BTreeMap, HashMap};
use std::path::PathBuf;

use crate::diagnostics::SourceSpan;
use crate::frontend::ast::{
    AccessMod, BorrowMode, EffectSignature, FieldStorageMode, ImportDecl, PolymorphismStrategy,
    PrimitiveLowering, SymbolId, TypeKind, TypeRef,
};

/// Hierarchical virtual namespace tree node (`NamespaceNode` from the repomap).
#[derive(Clone, Debug, Default)]
pub struct NamespaceNode {
    pub segment: String,
    pub full_path: Vec<String>,
    pub type_ids: Vec<SymbolId>,
    pub children: BTreeMap<String, NamespaceNode>,
}

impl NamespaceNode {
    pub fn insert_type(&mut self, ns_segments: &[String], type_id: SymbolId) {
        let mut current = self;
        let mut path_so_far = Vec::new();
        for seg in ns_segments {
            path_so_far.push(seg.clone());
            current = current
                .children
                .entry(seg.clone())
                .or_insert_with(|| NamespaceNode {
                    segment: seg.clone(),
                    full_path: path_so_far.clone(),
                    type_ids: Vec::new(),
                    children: BTreeMap::new(),
                });
        }
        if !current.type_ids.contains(&type_id) {
            current.type_ids.push(type_id);
        }
    }
}

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
    /// Hierarchical virtual namespace tree root (`NamespaceNode`).
    pub namespace_root: NamespaceNode,
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

        let ns_list = self.namespaces.entry(ns.clone()).or_default();
        if !ns_list.contains(&id) {
            ns_list.push(id);
        }
        self.namespace_root.insert_type(&ns, id);

        id
    }

    /// Resolves a type name within the context of `current_ns` and file `imports`.
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
                            !t.is_ambient_stub && !matches!(t.kind, TypeKind::PrimitiveClass { .. })
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
                if prev.is_lowercase()
                    || prev.is_ascii_digit()
                    || (prev.is_uppercase() && next_is_lower)
                {
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
