from __future__ import annotations

from dataclasses import dataclass, field

from psc.frontend.ast_nodes import CompilationUnit
from psc.semantics.symbols import GlobalSymbolTable, TypeSymbol


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

    def __init__(self, symtab: GlobalSymbolTable, target_units: list[CompilationUnit] | None = None) -> None:
        self.symtab = symtab
        self.target_unit_ids: set[int] | None = (
            {id(u) for u in target_units} if target_units is not None else None
        )

    def plan_modules(self) -> dict[str, PlannedPythonModule]:
        modules_by_path: dict[str, PlannedPythonModule] = {}

        # 1. Filter emittable types per namespace
        emittable_by_ns: dict[tuple[str, ...], list[TypeSymbol]] = {}
        for ns_tuple, ns_types in self.symtab.namespaces.items():
            emittable = [
                t
                for t in ns_types
                if not t.is_ambient_stub
                and not t.is_primitive
                and t.ast_node.emission_strategy.kind != "ErasedPrimitive"
                and (self.target_unit_ids is None or id(t.unit) in self.target_unit_ids)
            ]
            if emittable:
                emittable_by_ns[ns_tuple] = emittable

        # 2. Determine which namespaces are parent packages (have child sub-namespaces with emittable types)
        package_namespaces: set[tuple[str, ...]] = set()
        for ns_a in emittable_by_ns:
            for ns_b in emittable_by_ns:
                if len(ns_b) > len(ns_a) and ns_b[:len(ns_a)] == ns_a:
                    package_namespaces.add(ns_a)
                    break

        for ns_tuple, emittable in emittable_by_ns.items():
            sorted_types = self.topological_sort_types(emittable)
            is_package = ns_tuple in package_namespaces
            rel_path = self.namespace_to_disk_path(ns_tuple, is_package=is_package)
            primary_ps = sorted_types[0].span.ps_filename if sorted_types else "module.ps"

            modules_by_path[rel_path] = PlannedPythonModule(
                namespace=ns_tuple,
                module_rel_path=rel_path,
                types=sorted_types,
                primary_ps_filename=primary_ps,
            )

        return modules_by_path

    @staticmethod
    def namespace_to_disk_path(namespace: tuple[str, ...], is_package: bool = False) -> str:
        if not namespace:
            return "__init__.py" if is_package else "__root__.py"
        from psc.semantics.symbols import pascal_to_snake

        parts = [pascal_to_snake(segment) for segment in namespace]
        if is_package:
            return "/".join(parts) + "/__init__.py"
        return "/".join(parts) + ".py"

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
