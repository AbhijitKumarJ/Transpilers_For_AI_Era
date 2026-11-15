from __future__ import annotations

from dataclasses import dataclass, field

from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol, namespace_to_module_path


@dataclass(slots=True)
class PlannedPythonModule:
    """Represents a synthesized Python module aggregated from a logical namespace."""

    namespace: tuple[str, ...]
    module_rel_path: str
    types: list[TypeSymbol] = field(default_factory=list)
    primary_ps_filename: str = ""


class NamespacePackagePlanner:
    """
    Pass 3A (Part 1) — Virtual Namespace Aggregator & Topological Class Sorter:
      1. Groups all non-ambient, non-primitive `TypeSymbol`s by their logical `namespace`
         regardless of which physical `.ps` file or directory declared them.
      2. Topologically orders classes within each synthesized Python module so base
         classes and interfaces always precede subclasses in the emitted `.py` file.
    """

    def __init__(self, symtab: GlobalSymbolTable) -> None:
        self.symtab = symtab

    def plan_modules(self) -> dict[str, PlannedPythonModule]:
        modules_by_path: dict[str, PlannedPythonModule] = {}

        for ns_tuple, ns_types in self.symtab.namespaces.items():
            emittable = [
                t
                for t in ns_types
                if not t.is_ambient_stub
                and not t.is_primitive
                and t.ast_node.emission_strategy.kind != "ErasedPrimitive"
            ]
            if not emittable:
                continue

            sorted_types = self.topological_sort_types(emittable)
            rel_path = namespace_to_module_path(ns_tuple)
            primary_ps = sorted_types[0].span.ps_filename if sorted_types else "module.ps"

            modules_by_path[rel_path] = PlannedPythonModule(
                namespace=ns_tuple,
                module_rel_path=rel_path,
                types=sorted_types,
                primary_ps_filename=primary_ps,
            )

        return modules_by_path

    @staticmethod
    def topological_sort_types(types: list[TypeSymbol]) -> list[TypeSymbol]:
        """
        Orders `types` so that any base class or implemented interface declared
        in the same namespace appears before its derived classes.
        """
        type_map = {t.id.value: t for t in types}
        visited: set[int] = set()
        ordered: list[TypeSymbol] = []

        def visit(sym: TypeSymbol) -> None:
            sid = sym.id.value
            if sid in visited:
                return
            visited.add(sid)
            for base_sym in sym.base_type_symbols:
                if base_sym.id.value in type_map:
                    visit(type_map[base_sym.id.value])
            sym.ast_node.topological_order_rank = len(ordered)
            ordered.append(sym)

        for t in types:
            visit(t)

        return ordered
