use std::collections::HashMap;

use crate::frontend::ast::{CompilationUnit, PolymorphismStrategy, SymbolId, TypeKind};
use crate::semantics::symbols::GlobalSymbolTable;

/// Pass 2A Polymorphism & Hierarchy Lowerer.
///
/// Inspects the whole-project type hierarchy in `GlobalSymbolTable` and assigns a zero-vtable
/// Rust lowering strategy (`PolymorphismStrategy`) to every type:
/// 1. `OpenTrait`: Interfaces marked `extensible interface` (or `IDisposable` / ambient interfaces)
///    lower to native `pub trait`.
/// 2. `ClosedWorldEnum`: Abstract classes or non-extensible interfaces with concrete subclasses
///    in the crate lower to an exhaustive Rust `enum` with `match` dispatch.
/// 3. `FlattenedSubStruct`: Concrete subclasses inheriting from a class (abstract or concrete)
///    embed `pub base: BaseStruct` and implement `Deref` / `DerefMut` for zero-indirection state reuse.
/// 4. `MonomorphicStruct`: Standard records, services, structs, and classes without subclasses.
pub fn resolve_polymorphism_strategies(
    units: &mut [CompilationUnit],
    symtab: &mut GlobalSymbolTable,
) {
    // 1. Build a map from every base type/interface `SymbolId` to its concrete implementing types
    let mut implementors_by_base: HashMap<SymbolId, Vec<SymbolId>> = HashMap::new();
    let mut direct_base_class: HashMap<SymbolId, SymbolId> = HashMap::new();

    let mut all_type_ids: Vec<SymbolId> = symtab.types.keys().copied().collect();
    all_type_ids.sort_by_key(|id| id.0);

    for &type_id in &all_type_ids {
        let Some(type_sym) = symtab.types.get(&type_id) else {
            continue;
        };
        if type_sym.is_ambient_stub {
            continue;
        }

        let is_concrete_type = !type_sym.is_abstract
            && !matches!(type_sym.kind, TypeKind::Interface { .. } | TypeKind::Enum);

        for &base_id in &type_sym.resolved_base_type_ids {
            let Some(base_sym) = symtab.types.get(&base_id) else {
                continue;
            };

            if is_concrete_type {
                implementors_by_base
                    .entry(base_id)
                    .or_default()
                    .push(type_id);
            }

            // Record single-inheritance base class (as opposed to interfaces) for struct flattening
            if !matches!(
                base_sym.kind,
                TypeKind::Interface { .. } | TypeKind::PrimitiveClass { .. }
            ) {
                direct_base_class.insert(type_id, base_id);
            }
        }
    }

    // 2. Compute `PolymorphismStrategy` for every registered TypeSymbol
    let mut resolved_strategies: HashMap<SymbolId, PolymorphismStrategy> = HashMap::new();

    for &type_id in &all_type_ids {
        let Some(type_sym) = symtab.types.get(&type_id) else {
            continue;
        };

        let strategy = match type_sym.kind {
            TypeKind::Interface { is_extensible } => {
                if is_extensible || type_sym.is_ambient_stub || type_sym.name == "IDisposable" {
                    PolymorphismStrategy::OpenTrait
                } else {
                    let variants = implementors_by_base
                        .get(&type_id)
                        .cloned()
                        .unwrap_or_default();
                    if variants.is_empty() {
                        PolymorphismStrategy::OpenTrait
                    } else {
                        PolymorphismStrategy::ClosedWorldEnum { variants }
                    }
                }
            }

            TypeKind::StandardClass | TypeKind::ServiceClass | TypeKind::SharedClass => {
                if type_sym.is_abstract {
                    let variants = implementors_by_base
                        .get(&type_id)
                        .cloned()
                        .unwrap_or_default();
                    PolymorphismStrategy::ClosedWorldEnum { variants }
                } else if let Some(&base_class_id) = direct_base_class.get(&type_id) {
                    PolymorphismStrategy::FlattenedSubStruct {
                        base_type: base_class_id,
                    }
                } else {
                    PolymorphismStrategy::MonomorphicStruct
                }
            }

            TypeKind::Record { .. }
            | TypeKind::ValueStruct
            | TypeKind::PrimitiveClass { .. }
            | TypeKind::Enum => {
                if let Some(&base_class_id) = direct_base_class.get(&type_id) {
                    PolymorphismStrategy::FlattenedSubStruct {
                        base_type: base_class_id,
                    }
                } else {
                    PolymorphismStrategy::MonomorphicStruct
                }
            }
        };

        resolved_strategies.insert(type_id, strategy);
    }

    // 3. Write the resolved strategies back to `GlobalSymbolTable` and AST `TypeDecl` nodes
    for (type_id, strat) in &resolved_strategies {
        if let Some(type_sym) = symtab.types.get_mut(type_id) {
            type_sym.inferred_polymorphism = strat.clone();
        }
    }

    for unit in units.iter_mut() {
        for type_decl in &mut unit.types {
            if let Some(strat) = resolved_strategies.get(&type_decl.id) {
                type_decl.inferred_polymorphism = strat.clone();
            }
        }
    }
}
