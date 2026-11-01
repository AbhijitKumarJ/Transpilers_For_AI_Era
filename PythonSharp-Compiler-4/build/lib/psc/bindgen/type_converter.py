from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(slots=True)
class ConvertedType:
    """Represents a converted PythonSharp type signature."""

    main_type: str
    is_nullable: bool = False
    is_union: bool = False
    union_alternatives: list[str] = field(default_factory=list)

    @property
    def rendered(self) -> str:
        """Render the complete PythonSharp type string."""
        if self.is_nullable:
            base = self.main_type.rstrip("?")
            return f"{base}?"
        return self.main_type

    def get_overload_types(self) -> list[str]:
        """Return list of distinct type strings for method overload splitting."""
        if self.is_union and self.union_alternatives:
            return self.union_alternatives
        return [self.rendered]


PRIMITIVE_TYPE_MAP: dict[str, str] = {
    "int": "int",
    "float": "float",
    "str": "string",
    "bool": "bool",
    "bytes": "bytes",
    "bytearray": "bytearray",
    "object": "object",
    "Any": "object",
    "None": "void",
    "NoneType": "void",
    "Ellipsis": "object",
    "Self": "object",
}

COLLECTION_TYPE_MAP: dict[str, str] = {
    "list": "List",
    "List": "List",
    "set": "HashSet",
    "Set": "HashSet",
    "frozenset": "HashSet",
    "FrozenSet": "HashSet",
    "Sequence": "IEnumerable",
    "Iterable": "IEnumerable",
    "Iterator": "IEnumerable",
    "Collection": "IEnumerable",
    "Generator": "IEnumerable",
    "dict": "Dict",
    "Dict": "Dict",
    "Mapping": "Dict",
    "MutableMapping": "Dict",
}


class TypeConverter:
    """
    Translates Python AST type annotations into PythonSharp types.
    Handles primitives, generic collections, Optionals, Unions, and Callables.
    """

    def __init__(self, current_class_name: str | None = None) -> None:
        self.current_class_name = current_class_name

    def convert(self, node: ast.AST | None, *, is_return: bool = False) -> ConvertedType:
        """Convert a Python AST type annotation into a ConvertedType."""
        if node is None:
            return ConvertedType(main_type="void" if is_return else "object")

        if isinstance(node, ast.Constant):
            if node.value is None:
                return ConvertedType(main_type="void" if is_return else "object?", is_nullable=not is_return)
            if isinstance(node.value, str):
                # Forward reference string literal: "int" -> ast.parse("int", mode="eval")
                try:
                    parsed = ast.parse(node.value, mode="eval")
                    return self.convert(parsed.body, is_return=is_return)
                except Exception:
                    return ConvertedType(main_type=node.value)
            return ConvertedType(main_type="object")

        if isinstance(node, ast.Name):
            return self._convert_name(node.id, is_return=is_return)

        if isinstance(node, ast.Attribute):
            # E.g. typing.Optional, typing.List, collections.abc.Sequence
            return self._convert_name(node.attr, is_return=is_return)

        if isinstance(node, ast.Subscript):
            return self._convert_subscript(node, is_return=is_return)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # Python 3.10+ Union syntax: A | B | None
            return self._convert_bitor_union(node, is_return=is_return)

        if isinstance(node, ast.Tuple):
            # Tuple of types e.g. (int, str)
            elements = [self.convert(elt).rendered for elt in node.elts]
            return ConvertedType(main_type=f"({', '.join(elements)})" if elements else "object")

        return ConvertedType(main_type="void" if is_return else "object")

    def _convert_name(self, name: str, *, is_return: bool) -> ConvertedType:
        if name == "Self":
            return ConvertedType(main_type=self.current_class_name or "object")

        if name in PRIMITIVE_TYPE_MAP:
            mapped = PRIMITIVE_TYPE_MAP[name]
            if mapped == "void" and not is_return:
                return ConvertedType(main_type="object?", is_nullable=True)
            return ConvertedType(main_type=mapped)

        if name in COLLECTION_TYPE_MAP:
            container = COLLECTION_TYPE_MAP[name]
            if container == "Dict":
                return ConvertedType(main_type="Dict<object, object>")
            if container in ("List", "HashSet", "IEnumerable"):
                return ConvertedType(main_type=f"{container}<object>")

        return ConvertedType(main_type=name)

    def _convert_subscript(self, node: ast.Subscript, *, is_return: bool) -> ConvertedType:
        base_name = ""
        if isinstance(node.value, ast.Name):
            base_name = node.value.id
        elif isinstance(node.value, ast.Attribute):
            base_name = node.value.attr

        # Optional[T]
        if base_name == "Optional":
            inner = self.convert(node.slice, is_return=is_return)
            return ConvertedType(main_type=inner.main_type, is_nullable=True)

        # Union[T1, T2, ...]
        if base_name == "Union":
            return self._convert_union_slice(node.slice, is_return=is_return)

        # Generic collection types: List[T], Set[T], Dict[K, V], etc.
        if base_name in COLLECTION_TYPE_MAP:
            container = COLLECTION_TYPE_MAP[base_name]
            if container == "Dict":
                args = self._extract_slice_elements(node.slice)
                if len(args) >= 2:
                    k = self.convert(args[0]).rendered
                    v = self.convert(args[1]).rendered
                    return ConvertedType(main_type=f"Dict<{k}, {v}>")
                return ConvertedType(main_type="Dict<object, object>")

            # Single type-argument collections: List[T], HashSet[T], IEnumerable[T]
            args = self._extract_slice_elements(node.slice)
            t = self.convert(args[0]).rendered if args else "object"
            return ConvertedType(main_type=f"{container}<{t}>")

        # Callable[[Arg1, Arg2], Ret]
        if base_name == "Callable":
            return self._convert_callable(node.slice)

        # Tuple[T1, T2, ...]
        if base_name in ("tuple", "Tuple"):
            args = self._extract_slice_elements(node.slice)
            if not args:
                return ConvertedType(main_type="object")
            # Tuple[T, ...] -> IEnumerable<T>
            if len(args) == 2 and isinstance(args[1], ast.Constant) and args[1].value is Ellipsis:
                elem_type = self.convert(args[0]).rendered
                return ConvertedType(main_type=f"IEnumerable<{elem_type}>")
            rendered_elts = [self.convert(a).rendered for a in args]
            return ConvertedType(main_type=f"({', '.join(rendered_elts)})")

        # Literal[...]
        if base_name == "Literal":
            args = self._extract_slice_elements(node.slice)
            if args:
                first = args[0]
                if isinstance(first, ast.Constant):
                    if isinstance(first.value, str):
                        return ConvertedType(main_type="string")
                    if isinstance(first.value, bool):
                        return ConvertedType(main_type="bool")
                    if isinstance(first.value, int):
                        return ConvertedType(main_type="int")
                    if isinstance(first.value, float):
                        return ConvertedType(main_type="float")
            return ConvertedType(main_type="object")

        # Fallback for generic class: e.g. Custom[T1, T2]
        args = self._extract_slice_elements(node.slice)
        arg_strs = [self.convert(a).rendered for a in args]
        type_str = f"{base_name}<{', '.join(arg_strs)}>" if arg_strs else base_name
        return ConvertedType(main_type=type_str)

    def _convert_callable(self, slice_node: ast.AST) -> ConvertedType:
        args = self._extract_slice_elements(slice_node)
        if len(args) < 2:
            return ConvertedType(main_type="object")

        param_nodes: list[ast.AST] = []
        if isinstance(args[0], (ast.List, ast.Tuple)):
            param_nodes = list(args[0].elts)

        return_node = args[1]
        ret_type = self.convert(return_node, is_return=True)

        param_types = [self.convert(p).rendered for p in param_nodes]
        if ret_type.main_type == "void":
            if param_types:
                return ConvertedType(main_type=f"Action<{', '.join(param_types)}>")
            return ConvertedType(main_type="Action")
        else:
            all_types = [*param_types, ret_type.rendered]
            return ConvertedType(main_type=f"Func<{', '.join(all_types)}>")

    def _convert_union_slice(self, slice_node: ast.AST, *, is_return: bool) -> ConvertedType:
        elements = self._extract_slice_elements(slice_node)
        return self._build_union_result(elements, is_return=is_return)

    def _convert_bitor_union(self, node: ast.BinOp, *, is_return: bool) -> ConvertedType:
        # Collect all operands in a chained `A | B | C`
        nodes: list[ast.AST] = []

        def collect(n: ast.AST) -> None:
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
                collect(n.left)
                collect(n.right)
            else:
                nodes.append(n)

        collect(node)
        return self._build_union_result(nodes, is_return=is_return)

    def _build_union_result(self, nodes: Sequence[ast.AST], *, is_return: bool) -> ConvertedType:
        converted_items: list[ConvertedType] = []
        is_nullable = False

        for n in nodes:
            # Check for None / NoneType
            if isinstance(n, ast.Constant) and n.value is None:
                is_nullable = True
                continue
            if isinstance(n, ast.Name) and n.id in ("None", "NoneType"):
                is_nullable = True
                continue
            c = self.convert(n, is_return=is_return)
            if c.is_nullable:
                is_nullable = True
            converted_items.append(c)

        if not converted_items:
            return ConvertedType(main_type="void" if is_return else "object?", is_nullable=True)

        if len(converted_items) == 1:
            res = converted_items[0]
            return ConvertedType(main_type=res.main_type, is_nullable=is_nullable or res.is_nullable)

        # Multiple non-None types: Union[A, B]
        # Collect distinct type alternatives for overload splitting
        alts = list(dict.fromkeys(item.rendered for item in converted_items))
        if is_nullable:
            alts = [f"{alt}?" if not alt.endswith("?") else alt for alt in alts]

        # For return types, pick object since C# doesn't support return-type-only overloads
        primary = "object" if is_return else alts[0]
        return ConvertedType(
            main_type=primary,
            is_nullable=is_nullable,
            is_union=True,
            union_alternatives=alts,
        )

    @staticmethod
    def _extract_slice_elements(slice_node: ast.AST) -> list[ast.AST]:
        if isinstance(slice_node, ast.Tuple):
            return list(slice_node.elts)
        return [slice_node]
