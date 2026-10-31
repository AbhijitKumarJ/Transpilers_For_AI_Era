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
    let type_generics = type_decl.type_params.clone();

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
            | "Task"
            | "ValueTask"
            | "IAsyncEnumerable"
    ) {
        return None;
    }

    if !is_ambient {
        diag.report_unresolved_symbol(type_ref.span.clone(), &type_ref.qualified_name());
    }
    None
}
