from __future__ import annotations

from psc.diagnostics import DiagnosticEngine
from psc.frontend.ast_nodes import CompilationUnit
from psc.semantics.access_checker import AccessChecker
from psc.semantics.collector import SymbolCollector
from psc.semantics.linq_fuser import ComprehensionGenerator, LinqComprehensionFuser
from psc.semantics.overload_resolver import OverloadResolver
from psc.semantics.primitive_resolver import PrimitiveResolver
from psc.semantics.slot_analyzer import SlotAndHierarchyAnalyzer
from psc.semantics.symbols import (
    BUILTIN_PRIMITIVE_MAP,
    GlobalSymbolTable,
    MemberSymbol,
    ResolvedType,
    TypeSymbol,
    namespace_to_module_path,
    pascal_to_snake,
)
from psc.semantics.type_checker import TypeChecker


def analyze_compilation_units(
    units: list[CompilationUnit],
    symtab: GlobalSymbolTable,
    diagnostics: DiagnosticEngine,
    assembly_name: str | None = None,
) -> None:
    """
    Runs the complete Pass 1 + Pass 2A + Pass 2B semantic pipeline across all units:
      1. SymbolCollector (Pass 1: global type headers, inheritance, member signatures)
      2. SlotAndHierarchyAnalyzer (Pass 2A: deduplicated __slots__, __ps_types__, PS003/PS004)
      3. AccessChecker (Pass 2A: Rule PS001 private/protected/internal verification)
      4. PrimitiveResolver (Pass 2B: [MapsTo], [InlineTemplate], [KwArgs], generators)
      5. OverloadResolver (Pass 2B: @overload dispatch groups, Rule PS002, call-site binding)
      6. LinqComprehensionFuser (Pass 2B: .Where().Select().ToList() comprehension fusion)
    """
    SymbolCollector(symtab, diagnostics).collect_all(units, assembly_name=assembly_name)
    SlotAndHierarchyAnalyzer(symtab, diagnostics).analyze_all(units)
    AccessChecker(symtab, diagnostics).check_all(units)
    PrimitiveResolver(symtab, diagnostics).resolve_all(units)
    OverloadResolver(symtab, diagnostics).resolve_all(units)
    LinqComprehensionFuser(symtab).fuse_all(units)
    TypeChecker(symtab, diagnostics).verify_all(units)


__all__ = [
    "BUILTIN_PRIMITIVE_MAP",
    "GlobalSymbolTable",
    "MemberSymbol",
    "ResolvedType",
    "TypeSymbol",
    "SymbolCollector",
    "SlotAndHierarchyAnalyzer",
    "AccessChecker",
    "PrimitiveResolver",
    "OverloadResolver",
    "LinqComprehensionFuser",
    "TypeChecker",
    "ComprehensionGenerator",
    "analyze_compilation_units",
    "namespace_to_module_path",
    "pascal_to_snake",
]
