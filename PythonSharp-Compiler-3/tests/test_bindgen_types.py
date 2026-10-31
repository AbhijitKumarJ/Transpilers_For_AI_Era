from __future__ import annotations

import ast

from psc.bindgen.type_converter import TypeConverter


def _parse_type(expr_str: str) -> ast.AST:
    return ast.parse(expr_str, mode="eval").body


def test_primitive_type_conversions() -> None:
    conv = TypeConverter()
    assert conv.convert(_parse_type("int")).rendered == "int"
    assert conv.convert(_parse_type("float")).rendered == "float"
    assert conv.convert(_parse_type("str")).rendered == "string"
    assert conv.convert(_parse_type("bool")).rendered == "bool"
    assert conv.convert(_parse_type("bytes")).rendered == "bytes"
    assert conv.convert(_parse_type("Any")).rendered == "object"
    assert conv.convert(_parse_type("object")).rendered == "object"
    assert conv.convert(_parse_type("None"), is_return=True).rendered == "void"
    assert conv.convert(_parse_type("None"), is_return=False).rendered == "object?"


def test_optional_and_union_conversions() -> None:
    conv = TypeConverter()
    # Optional[int]
    opt_int = conv.convert(_parse_type("Optional[int]"))
    assert opt_int.rendered == "int?"

    # int | None
    bitor_opt = conv.convert(_parse_type("int | None"))
    assert bitor_opt.rendered == "int?"

    # str | None
    str_opt = conv.convert(_parse_type("str | None"))
    assert str_opt.rendered == "string?"

    # Non-None union: Union[int, str]
    union_types = conv.convert(_parse_type("Union[int, str]"))
    assert union_types.is_union is True
    assert union_types.get_overload_types() == ["int", "string"]

    # Python 3.10+ Union syntax: int | str
    bitor_union = conv.convert(_parse_type("int | str"))
    assert bitor_union.is_union is True
    assert bitor_union.get_overload_types() == ["int", "string"]

    # Union with None: int | str | None
    union_with_null = conv.convert(_parse_type("int | str | None"))
    assert union_with_null.is_union is True
    assert union_with_null.is_nullable is True
    assert union_with_null.get_overload_types() == ["int?", "string?"]


def test_collection_conversions() -> None:
    conv = TypeConverter()
    assert conv.convert(_parse_type("List[int]")).rendered == "List<int>"
    assert conv.convert(_parse_type("list[str]")).rendered == "List<string>"
    assert conv.convert(_parse_type("Dict[str, int]")).rendered == "Dict<string, int>"
    assert conv.convert(_parse_type("dict[int, float]")).rendered == "Dict<int, float>"
    assert conv.convert(_parse_type("Set[str]")).rendered == "HashSet<string>"
    assert conv.convert(_parse_type("set[int]")).rendered == "HashSet<int>"
    assert conv.convert(_parse_type("Sequence[float]")).rendered == "IEnumerable<float>"
    assert conv.convert(_parse_type("Iterable[int]")).rendered == "IEnumerable<int>"


def test_callable_and_tuple_conversions() -> None:
    conv = TypeConverter()
    # Callable[[int, str], bool]
    func_type = conv.convert(_parse_type("Callable[[int, str], bool]"))
    assert func_type.rendered == "Func<int, string, bool>"

    # Callable[[int], None]
    action_type = conv.convert(_parse_type("Callable[[int], None]"))
    assert action_type.rendered == "Action<int>"

    # Tuple[int, str]
    tuple_type = conv.convert(_parse_type("Tuple[int, str]"))
    assert tuple_type.rendered == "(int, string)"

    # Tuple[int, ...]
    var_tuple = conv.convert(_parse_type("Tuple[int, ...]"))
    assert var_tuple.rendered == "IEnumerable<int>"


def test_self_and_custom_types() -> None:
    conv = TypeConverter(current_class_name="DataFrame")
    assert conv.convert(_parse_type("Self")).rendered == "DataFrame"
    assert conv.convert(_parse_type("DataFrame")).rendered == "DataFrame"
    assert conv.convert(_parse_type("Optional[DataFrame]")).rendered == "DataFrame?"

