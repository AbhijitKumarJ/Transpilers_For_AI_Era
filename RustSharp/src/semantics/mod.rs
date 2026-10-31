pub mod archetype_analyzer;
pub mod borrow_inferencer;
pub mod collector;
pub mod effect_inferencer;
pub mod hierarchy_lowerer;
pub mod linq_fuser;
pub mod overload_resolver;
pub mod preflight_verifier;
pub mod primitive_resolver;
pub mod symbols;

pub use archetype_analyzer::analyze_archetypes;
pub use borrow_inferencer::InterproceduralBorrowInferencer;
pub use collector::collect_global_symbols;
pub use effect_inferencer::infer_checked_effects;
pub use hierarchy_lowerer::resolve_polymorphism_strategies;
pub use linq_fuser::fuse_linq_pipelines;
pub use overload_resolver::resolve_overloads;
pub use preflight_verifier::run_preflight_ownership_checks;
pub use primitive_resolver::{format_rust_owned_type, format_rust_param_type, resolve_primitives};
pub use symbols::{
    FieldSymbol, GlobalSymbolTable, MethodSymbol, NamespaceModulePlan, NamespaceNode, ParamSymbol,
    PropertySymbol, TypeSymbol,
};
