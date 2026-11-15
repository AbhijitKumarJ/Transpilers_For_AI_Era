from __future__ import annotations

import ast
import itertools
import re
import sys
from dataclasses import dataclass, field
from typing import Any

from psc.bindgen.type_converter import ConvertedType, TypeConverter

RESERVED_KEYWORDS: set[str] = {
    "abstract", "as", "base", "bool", "break", "byte", "case", "catch", "char",
    "checked", "class", "const", "continue", "decimal", "default", "delegate",
    "do", "double", "else", "enum", "event", "explicit", "extern", "false",
    "finally", "fixed", "float", "for", "foreach", "goto", "if", "implicit",
    "in", "int", "interface", "internal", "is", "lock", "long", "namespace",
    "new", "null", "object", "operator", "out", "override", "params", "private",
    "protected", "public", "readonly", "ref", "return", "sbyte", "sealed",
    "short", "sizeof", "stackalloc", "static", "string", "struct", "switch",
    "this", "throw", "true", "try", "typeof", "uint", "ulong", "unchecked",
    "unsafe", "ushort", "using", "virtual", "void", "volatile", "while", "when",
    "dynamic", "yield", "record",
}


def escape_identifier(name: str) -> str:
    """Escape C# reserved keywords using the `@` prefix and sanitize invalid identifier characters."""
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    if clean in RESERVED_KEYWORDS:
        return f"@{clean}"
    return clean


def snake_to_pascal(name: str) -> str:
    """Convert snake_case identifiers into PascalCase, preserving existing PascalCase."""
    if not name:
        return ""
    if name.startswith("__") and name.endswith("__"):
        return name
    leading = ""
    while name.startswith("_"):
        leading += "_"
        name = name[1:]
    if not name:
        return leading
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    parts = name.split("_")
    pascal = "".join(
        part.capitalize() if part.isupper() and len(part) > 1 else (part[0].upper() + part[1:] if part else "")
        for part in parts
    )
    return leading + pascal


_KNOWN_UPSTREAM_ATTRIBUTIONS: dict[str, str] = {
    "numpy": "(c) 2005-2026, NumPy Developers (BSD-3-Clause)",
    "scipy": "(c) 2001-2026, Enthought, Inc. & SciPy Developers (BSD-3-Clause)",
    "pandas": "(c) 2008-2026, AQR Capital Management, LLC, Lambda Foundry, Inc. & PyData Development Team (BSD-3-Clause)",
    "matplotlib": "(c) 2012-2026 Matplotlib Development Team; All Rights Reserved (PSF-based Matplotlib License)",
    "seaborn": "(c) 2012-2026, Michael L. Waskom (BSD-3-Clause)",
    "sklearn": "(c) 2007-2026, The scikit-learn developers (BSD-3-Clause)",
    "scikit_learn": "(c) 2007-2026, The scikit-learn developers (BSD-3-Clause)",
    "torch": "(c) 2016-2026, Facebook, Inc. / PyTorch Contributors (BSD-3-Clause)",
    "pytorch": "(c) 2016-2026, Facebook, Inc. / PyTorch Contributors (BSD-3-Clause)",
    "sympy": "(c) 2006-2026 SymPy Development Team (BSD-3-Clause)",
    "qiskit": "(c) 2017-2026, Qiskit Development Team (Apache-2.0)",
    "polars": "(c) 2020-2026 Ritchie Vink (MIT)",
    "xgboost": "(c) 2014-2026, XGBoost Contributors (Apache-2.0)",
    "lightgbm": "(c) 2016-2026, Microsoft Corporation (MIT)",
    "optuna": "(c) 2018-2026, Preferred Networks, Inc. (MIT)",
    "transformers": "(c) 2018-2026, The Hugging Face team (Apache-2.0)",
    "faiss": "(c) Meta Platforms, Inc. and affiliates (MIT)",
    "onnxruntime": "(c) Microsoft Corporation (MIT)",
    "requests": "(c) Kenneth Reitz & Requests Authors (Apache-2.0)",
    "urllib3": "(c) Andrey Petrov and contributors (MIT)",
    "pydantic": "(c) Samuel Colvin and contributors (MIT)",
    "pytest": "(c) Holger Krekel and pytest-dev team (MIT)",
    "flask": "(c) Pallets (BSD-3-Clause)",
    "django": "(c) Django Software Foundation and contributors (BSD-3-Clause)",
    "fastapi": "(c) Sebastián Ramírez (MIT)",
    "click": "(c) Pallets (BSD-3-Clause)",
}

_PYTHON_STDLIB_MODULES: set[str] = {
    "abc", "argparse", "array", "ast", "asyncio", "base64", "bisect", "builtins",
    "bz2", "calendar", "cmath", "collections", "colorsys", "compileall", "concurrent",
    "contextlib", "contextvars", "copy", "csv", "ctypes", "curses", "dataclasses",
    "datetime", "dbm", "decimal", "difflib", "dis", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools", "gc", "getopt", "getpass", "gettext", "glob",
    "graphlib", "gzip", "hashlib", "heapq", "hmac", "html", "http", "idlelib",
    "imaplib", "imghdr", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "linecache", "locale", "logging", "lzma", "mailbox",
    "mailcap", "marshal", "math", "mimetypes", "mmap", "modulefinder", "msilib",
    "msvcrt", "multiprocessing", "netrc", "nntplib", "numbers", "operator", "optparse",
    "os", "ossaudiodev", "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
    "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc", "queue", "quopri",
    "random", "re", "readline", "reprlib", "resource", "rlcompleter", "runpy",
    "sched", "secrets", "select", "selectors", "shelve", "shlex", "shutil", "signal",
    "site", "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd", "sqlite3",
    "ssl", "stat", "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny", "tarfile",
    "telnetlib", "tempfile", "termios", "test", "textwrap", "threading", "time",
    "timeit", "tkinter", "token", "tokenize", "tomllib", "trace", "traceback",
    "tracemalloc", "tty", "turtle", "turtledemo", "types", "typing", "unicodedata",
    "unittest", "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
    "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
}


def resolve_upstream_attribution_headers(module_name: str) -> list[str]:
    """Resolve upstream copyright, licensing, and attribution lines for a generated .d.ps header."""
    root_pkg = module_name.split(".")[0].lower()

    if root_pkg in _KNOWN_UPSTREAM_ATTRIBUTIONS:
        notice = _KNOWN_UPSTREAM_ATTRIBUTIONS[root_pkg]
        lines = [f"// Upstream stub copyright {notice}"]
        if root_pkg == "matplotlib":
            lines.append("// Modifications: Automated AST translation from .pyi stubs into PythonSharp .d.ps via ps-bindgen")
        return lines

    if root_pkg in _PYTHON_STDLIB_MODULES:
        return ["// Upstream stub copyright (c) Python Software Foundation & Typeshed contributors (Apache-2.0 / MIT)"]

    try:
        import importlib.metadata
        pkg_query = root_pkg.replace("_", "-")
        try:
            meta = importlib.metadata.metadata(pkg_query)
        except Exception:
            meta = importlib.metadata.metadata(root_pkg)

        author = meta.get("Author") or meta.get("Maintainer") or meta.get("Author-email")
        if author:
            author = author.split("\n")[0].strip()
            if "<" in author:
                author = author.split("<")[0].strip()
            if "," in author and len(author) > 40:
                author = author.split(",")[0].strip() + " et al."

        lic = meta.get("License") or meta.get("License-Expression")
        if lic:
            lic = lic.split("\n")[0].strip()
            if len(lic) > 40 or "License agreement" in lic or "Copyright" in lic:
                lic = "permissive open-source"
        else:
            lic = "permissive open-source"

        holder = author if author else f"{root_pkg} contributors"
        return [f"// Upstream stub copyright (c) {holder} ({lic})"]
    except Exception:
        return [f"// Upstream stub copyright (c) {root_pkg} contributors"]


@dataclass(slots=True)
class GeneratedParameter:
    name: str
    type_name: str
    default_value: str | None = None
    is_params: bool = False
    is_kwargs: bool = False


@dataclass(slots=True)
class GeneratedMethod:
    csharp_name: str
    python_name: str
    return_type: str
    parameters: list[GeneratedParameter] = field(default_factory=list)
    is_static: bool = False
    is_constructor: bool = False
    is_indexer: bool = False
    indexer_key_type: str | None = None
    has_setter: bool = False
    is_property: bool = False
    surface_level: int = 0
    canonical_api: str | None = None


def _evaluate_pyi_condition(
    node: ast.AST,
    target_version: tuple[int, ...] = (3, 11),
    target_platform: str = "linux",
) -> bool:
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, ast.Name):
        if node.id in ("TYPE_CHECKING", "True"):
            return True
        if node.id == "False":
            return False
        return False
    if isinstance(node, ast.Attribute):
        if node.attr == "TYPE_CHECKING":
            return True
        return False
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _evaluate_pyi_condition(node.operand, target_version, target_platform)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_evaluate_pyi_condition(v, target_version, target_platform) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_evaluate_pyi_condition(v, target_version, target_platform) for v in node.values)
    if isinstance(node, ast.Compare):
        left_val = _extract_compare_operand(node.left, target_version, target_platform)
        if left_val is None:
            return True
        for op, right_node in zip(node.ops, node.comparators):
            right_val = _extract_compare_operand(right_node, target_version, target_platform)
            if right_val is None:
                return True
            if not _apply_comparison(left_val, op, right_val):
                return False
            left_val = right_val
        return True
    return True


def _extract_compare_operand(node: ast.AST, target_version: tuple[int, ...], target_platform: str) -> Any:
    if isinstance(node, ast.Attribute) and node.attr == "version_info":
        return target_version
    if isinstance(node, ast.Name) and node.id == "version_info":
        return target_version
    if isinstance(node, ast.Subscript):
        val = _extract_compare_operand(node.value, target_version, target_platform)
        if isinstance(val, tuple):
            if isinstance(node.slice, ast.Slice):
                upper = node.slice.upper.value if isinstance(node.slice.upper, ast.Constant) else None
                lower = node.slice.lower.value if isinstance(node.slice.lower, ast.Constant) else None
                return val[lower:upper]
            elif isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
                return val[node.slice.value]
    if isinstance(node, ast.Attribute) and node.attr == "platform":
        return target_platform
    if isinstance(node, ast.Name) and node.id == "platform":
        return target_platform
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(_extract_compare_operand(elt, target_version, target_platform) for elt in node.elts)
    return None


def _apply_comparison(left: Any, op: ast.cmpop, right: Any) -> bool:
    try:
        if isinstance(left, tuple) and isinstance(right, tuple):
            min_len = min(len(left), len(right))
            left_cmp = left[:min_len]
            right_cmp = right[:min_len]
        else:
            left_cmp = left
            right_cmp = right

        if isinstance(op, ast.GtE):
            return left_cmp >= right_cmp
        if isinstance(op, ast.Gt):
            return left_cmp > right_cmp
        if isinstance(op, ast.LtE):
            return left_cmp <= right_cmp
        if isinstance(op, ast.Lt):
            return left_cmp < right_cmp
        if isinstance(op, ast.Eq):
            return left_cmp == right_cmp
        if isinstance(op, ast.NotEq):
            return left_cmp != right_cmp
    except Exception:
        pass
    return True


class _PyiConditionalFlattener:
    """
    Evaluates static sys.version_info, sys.platform, and TYPE_CHECKING conditionals
    and unwraps matching branch definitions directly into the active AST body.
    """

    def __init__(self, target_version: tuple[int, ...] = (3, 11), target_platform: str = "linux") -> None:
        self.target_version = target_version
        self.target_platform = target_platform

    def flatten(self, module: ast.Module) -> ast.Module:
        module.body = self._flatten_stmts(module.body)
        for stmt in module.body:
            if isinstance(stmt, ast.ClassDef):
                stmt.body = self._flatten_stmts(stmt.body)
        return module

    def _flatten_stmts(self, stmts: list[ast.stmt]) -> list[ast.stmt]:
        result: list[ast.stmt] = []
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                cond = _evaluate_pyi_condition(stmt.test, self.target_version, self.target_platform)
                branch = stmt.body if cond else stmt.orelse
                result.extend(self._flatten_stmts(branch))
            else:
                result.append(stmt)
        return result


def _erased_type_token(type_name: str) -> str:
    """Returns the runtime-observable Python type token for PS002 overload collision check."""
    t = type_name.strip()
    if t.endswith("?"):
        t = t[:-1].strip()
    if t in ("int", "long", "short", "byte", "sbyte", "uint", "ulong", "ushort"):
        return "int"
    if t in ("float", "double", "decimal"):
        return "float"
    if t == "bool":
        return "bool"
    if t in ("string", "char"):
        return "str"
    if t == "bytes":
        return "bytes"
    if t.endswith("[]") or t.startswith("List<") or t.startswith("IList<") or t.startswith("IEnumerable<"):
        return "list"
    if t.startswith("Dict<") or t.startswith("IDictionary<"):
        return "dict"
    if t.startswith("Set<") or t.startswith("ISet<"):
        return "set"
    if t.startswith("Tuple<"):
        return "tuple"
    if t.startswith("Action") or t.startswith("Func<"):
        return "callable"
    if t in ("object", "dynamic", "void", ""):
        return "object"
    return t


class BindgenGenerator:
    """
    Translates a Python `.pyi` AST into a clean, strongly typed ambient `.d.ps` file.
    Supports C# PascalCase aliasing via [MapsTo], Union overload splitting,
    @overload decorators, class properties, and module-level functions.
    """

    def __init__(
        self,
        module_name: str,
        *,
        root_namespace: str = "Extern",
        package_symbol_index: dict[str, tuple[ast.FunctionDef | ast.ClassDef, list[str]]] | None = None,
    ) -> None:
        self.module_name = module_name
        self.root_namespace = root_namespace
        self.package_symbol_index = package_symbol_index or {}
        parts = [snake_to_pascal(p) for p in module_name.split(".") if p]
        self.pascal_parts = parts
        self.namespace_name = f"{root_namespace}.{'.'.join(parts)}" if parts else root_namespace

    def generate_d_ps(self, pyi_ast: ast.Module) -> str:
        """Generate PythonSharp .d.ps text from a parsed .pyi AST."""
        pyi_ast = _PyiConditionalFlattener().flatten(pyi_ast)
        attribution = resolve_upstream_attribution_headers(self.module_name)
        lines: list[str] = [
            "// ============================================================================",
            f"// Ambient stubs for Python module: {self.module_name}",
            "// Auto-generated by ps-bindgen — Zero Runtime Wrapper Tax",
            *attribution,
            "// ============================================================================",
            "",
            f"namespace {self.namespace_name};",
            "",
            "using PythonSharp.Core;",
            f"extern using {self.module_name};",
            "",
        ]

        top_level_functions: list[ast.FunctionDef] = []
        top_level_classes: list[ast.ClassDef] = []
        top_level_vars: list[ast.AnnAssign] = []

        for stmt in pyi_ast.body:
            if isinstance(stmt, ast.FunctionDef):
                top_level_functions.append(stmt)
            elif isinstance(stmt, ast.ClassDef):
                top_level_classes.append(stmt)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                top_level_vars.append(stmt)

        # 1. Classes
        for cls_node in top_level_classes:
            lines.extend(self._generate_class(cls_node))
            lines.append("")

        # Collect re-exported symbols from import statements and __all__
        reexported_symbols: dict[str, str | None] = {}
        for stmt in pyi_ast.body:
            if isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    sym_name = alias.asname or alias.name
                    reexported_symbols[sym_name] = stmt.module
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.asname:
                        reexported_symbols[alias.asname] = alias.name
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(stmt.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in stmt.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    if elt.value not in reexported_symbols:
                                        reexported_symbols[elt.value] = None

        existing_class_names = {c.name for c in top_level_classes}
        existing_fn_names = {f.name for f in top_level_functions}
        existing_var_names = {v.target.id for v in top_level_vars if isinstance(v.target, ast.Name)}
        filtered_reexports: dict[str, str | None] = {
            name: mod
            for name, mod in reexported_symbols.items()
            if name.isidentifier()
            and not (name.startswith("_") and not name.startswith("__"))
            and name not in existing_class_names
            and name not in existing_fn_names
            and name not in existing_var_names
        }

        # 2. Top-level functions, constants, and re-exports wrapped in a static module class
        if top_level_functions or top_level_vars or filtered_reexports:
            mod_lines, extra_ns = self._generate_module_class(
                top_level_functions,
                top_level_vars,
                existing_class_names,
                reexported_symbols=filtered_reexports,
            )
            for ens in sorted(extra_ns):
                if ens != self.namespace_name:
                    lines.insert(6, f"using {ens};")
            lines.extend(mod_lines)
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    def generate_triple_surface_bundle(self, pyi_ast: ast.Module) -> dict[str, str]:
        """
        Generate a 4-file Triple Surface bundle from a parsed .pyi AST:
        1. 00_{mod}.primitives.d.ps: Ambient primitives under PythonSharp.Primitives.{mod}
        2. 01_{mod}.raw.d.ps: Surface 1 (Raw ABI snake_case) stubs under PythonSharp.Raw.{mod}
        3. 02_{mod}.csharp.d.ps: Surface 2 (Idiomatic C#) stubs under PythonSharp.Bridge.{mod}
        4. 03_{mod}.enterprise.d.ps: Surface 3 (Enterprise C# Architecture) stubs under PythonSharp.{mod}
        """
        pyi_ast = _PyiConditionalFlattener().flatten(pyi_ast)
        top_level_functions: list[ast.FunctionDef] = []
        top_level_classes: list[ast.ClassDef] = []
        top_level_vars: list[ast.AnnAssign] = []

        for stmt in pyi_ast.body:
            if isinstance(stmt, ast.FunctionDef):
                top_level_functions.append(stmt)
            elif isinstance(stmt, ast.ClassDef):
                top_level_classes.append(stmt)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                top_level_vars.append(stmt)

        mod_short = self.module_name.split(".")[-1]
        existing_class_names = {c.name for c in top_level_classes}
        pascal_mod = ".".join(self.pascal_parts) if self.pascal_parts else snake_to_pascal(mod_short)

        enterprise_ns = f"PythonSharp.{pascal_mod}"
        raw_ns = f"PythonSharp.Raw.{pascal_mod}"
        bridge_ns = f"PythonSharp.Bridge.{pascal_mod}"
        primitives_ns = f"PythonSharp.Primitives.{pascal_mod}"

        # Collect re-exported symbols from import statements and __all__
        reexported_symbols: dict[str, str | None] = {}
        for stmt in pyi_ast.body:
            if isinstance(stmt, ast.ImportFrom):
                for alias in stmt.names:
                    sym_name = alias.asname or alias.name
                    reexported_symbols[sym_name] = stmt.module
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.asname:
                        reexported_symbols[alias.asname] = alias.name
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(stmt.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in stmt.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    if elt.value not in reexported_symbols:
                                        reexported_symbols[elt.value] = None

        existing_fn_names = {f.name for f in top_level_functions}
        existing_var_names = {v.target.id for v in top_level_vars if isinstance(v.target, ast.Name)}
        filtered_reexports: dict[str, str | None] = {
            name: mod
            for name, mod in reexported_symbols.items()
            if name.isidentifier()
            and not (name.startswith("_") and not name.startswith("__"))
            and name not in existing_class_names
            and name not in existing_fn_names
            and name not in existing_var_names
        }

        attribution = resolve_upstream_attribution_headers(self.module_name)

        # ---------------------------------------------------------
        # File 0: Primitives
        # ---------------------------------------------------------
        prim_lines: list[str] = [
            "// ============================================================================",
            f"// Ambient primitives for Python module: {self.module_name}",
            "// Auto-generated by ps-bindgen — Zero Runtime Wrapper Tax",
            *attribution,
            "// ============================================================================",
            "",
            f"namespace {primitives_ns};",
            "",
            "using PythonSharp.Core;",
            f"extern using {self.module_name};",
            "",
        ]
        if top_level_classes:
            for cls_node in top_level_classes:
                prim_lines.extend(self._generate_class(cls_node, is_primitive=True))
                prim_lines.append("")
        else:
            mod_prim_class = f"{snake_to_pascal(mod_short)}Primitive"
            prim_lines.extend([
                f'[MapsTo("{self.module_name}")]',
                f'[RuntimeType("{self.module_name}")]',
                f"public primitive class {escape_identifier(mod_prim_class)}",
                "{",
                "}",
                "",
            ])

        # ---------------------------------------------------------
        # File 1: Surface 1 (Raw ABI snake_case)
        # ---------------------------------------------------------
        raw_lines: list[str] = [
            "// ============================================================================",
            f"// Surface 1 (Raw ABI) stubs for Python module: {self.module_name}",
            *attribution,
            "// ============================================================================",
            "",
            f"namespace {raw_ns};",
            "",
            "using PythonSharp.Core;",
            f"using {primitives_ns};",
            f"extern using {self.module_name};",
            "",
        ]
        for cls_node in top_level_classes:
            raw_lines.extend(self._generate_class(
                cls_node,
                surface_level=1,
                canonical_target_prefix=enterprise_ns,
                raw_names=True,
            ))
            raw_lines.append("")
        if top_level_functions or top_level_vars or filtered_reexports:
            raw_mod, raw_extra = self._generate_module_class(
                top_level_functions,
                top_level_vars,
                existing_class_names,
                surface_level=1,
                canonical_target_prefix=enterprise_ns,
                raw_names=True,
                reexported_symbols=filtered_reexports,
            )
            for ens in sorted(raw_extra):
                if ens != raw_ns:
                    raw_lines.insert(6, f"using {ens};")
            raw_lines.extend(raw_mod)
            raw_lines.append("")

        # ---------------------------------------------------------
        # File 2: Surface 2 (Idiomatic C# Bridge)
        # ---------------------------------------------------------
        bridge_lines: list[str] = [
            "// ============================================================================",
            f"// Surface 2 (C# Idiomatic Bridge) stubs for Python module: {self.module_name}",
            *attribution,
            "// ============================================================================",
            "",
            f"namespace {bridge_ns};",
            "",
            "using PythonSharp.Core;",
            f"using {primitives_ns};",
            f"extern using {self.module_name};",
            "",
        ]
        for cls_node in top_level_classes:
            bridge_lines.extend(self._generate_class(
                cls_node,
                surface_level=2,
                canonical_target_prefix=enterprise_ns,
                raw_names=False,
            ))
            bridge_lines.append("")
        if top_level_functions or top_level_vars or filtered_reexports:
            bridge_mod, bridge_extra = self._generate_module_class(
                top_level_functions,
                top_level_vars,
                existing_class_names,
                surface_level=2,
                canonical_target_prefix=enterprise_ns,
                raw_names=False,
                reexported_symbols=filtered_reexports,
            )
            for ens in sorted(bridge_extra):
                if ens != bridge_ns:
                    bridge_lines.insert(6, f"using {ens};")
            bridge_lines.extend(bridge_mod)
            bridge_lines.append("")

        # ---------------------------------------------------------
        # File 3: Surface 3 (Enterprise C# Architecture)
        # ---------------------------------------------------------
        ent_lines: list[str] = [
            "// ============================================================================",
            f"// Surface 3 (Enterprise C# Architecture) stubs for Python module: {self.module_name}",
            *attribution,
            "// ============================================================================",
            "",
            f"namespace {enterprise_ns};",
            "",
            "using PythonSharp.Core;",
            f"using {primitives_ns};",
            f"extern using {self.module_name};",
            "",
        ]
        for cls_node in top_level_classes:
            ent_lines.extend(self._generate_class(
                cls_node,
                surface_level=3,
                raw_names=False,
            ))
            ent_lines.append("")
        if top_level_functions or top_level_vars or filtered_reexports:
            ent_mod, ent_extra = self._generate_module_class(
                top_level_functions,
                top_level_vars,
                existing_class_names,
                surface_level=3,
                raw_names=False,
                reexported_symbols=filtered_reexports,
            )
            for ens in sorted(ent_extra):
                if ens != enterprise_ns:
                    ent_lines.insert(6, f"using {ens};")
            ent_lines.extend(ent_mod)
            ent_lines.append("")

        return {
            f"00_{mod_short}.primitives.d.ps": "\n".join(prim_lines).strip() + "\n",
            f"01_{mod_short}.raw.d.ps": "\n".join(raw_lines).strip() + "\n",
            f"02_{mod_short}.csharp.d.ps": "\n".join(bridge_lines).strip() + "\n",
            f"03_{mod_short}.enterprise.d.ps": "\n".join(ent_lines).strip() + "\n",
        }

    def _generate_module_class(
        self,
        top_level_functions: list[ast.FunctionDef],
        top_level_vars: list[ast.AnnAssign],
        existing_class_names: set[str],
        *,
        surface_level: int = 0,
        canonical_target_prefix: str | None = None,
        raw_names: bool = False,
        reexported_symbols: dict[str, str | None] | None = None,
    ) -> tuple[list[str], set[str]]:
        lines: list[str] = []
        extra_namespaces: set[str] = set()
        module_class_name = snake_to_pascal(self.module_name.split(".")[-1])
        if module_class_name in existing_class_names:
            module_class_name = f"{module_class_name}Module"

        if surface_level > 0:
            lines.append(f"[SurfaceLevel({surface_level})]")
        if canonical_target_prefix:
            lines.append(f'[CanonicalApi("{canonical_target_prefix}.{module_class_name}")]')

        lines.append(f"public static class {escape_identifier(module_class_name)}")
        lines.append("{")
        conv = TypeConverter()

        for var in top_level_vars:
            if isinstance(var.target, ast.Name):
                var_type = conv.convert(var.annotation).rendered
                ps_var_name = var.target.id if raw_names else snake_to_pascal(var.target.id)
                if surface_level > 0:
                    lines.append(f"    [SurfaceLevel({surface_level})]")
                if canonical_target_prefix:
                    lines.append(
                        f'    [CanonicalApi("{canonical_target_prefix}.{module_class_name}.{snake_to_pascal(var.target.id)}")]'
                    )
                lines.append(f'    [MapsTo("{var.target.id}")]')
                lines.append(f"    public static extern {var_type} {escape_identifier(ps_var_name)} {{ get; }}")

        target_prefix = f"{canonical_target_prefix}.{module_class_name}" if canonical_target_prefix else None
        all_module_methods: list[GeneratedMethod] = []
        for fn in top_level_functions:
            methods = self._convert_function_to_methods(
                fn,
                is_static=True,
                conv=conv,
                raw_names=raw_names,
                surface_level=surface_level,
                canonical_target_prefix=target_prefix,
            )
            all_module_methods.extend(methods)

        if reexported_symbols:
            for sym_name in sorted(reexported_symbols.keys()):
                if not sym_name.isidentifier():
                    continue
                source_mod = reexported_symbols[sym_name]
                if sym_name in self.package_symbol_index:
                    sym_node, mod_parts = self.package_symbol_index[sym_name]
                    if mod_parts:
                        target_pascal = [snake_to_pascal(p) for p in mod_parts]
                        if surface_level == 2:
                            extra_namespaces.add(f"PythonSharp.Bridge.{'.'.join(target_pascal)}")
                        elif surface_level == 1:
                            extra_namespaces.add(f"PythonSharp.Raw.{'.'.join(target_pascal)}")
                        elif surface_level == 3:
                            extra_namespaces.add(f"PythonSharp.{'.'.join(target_pascal)}")

                    if isinstance(sym_node, ast.FunctionDef):
                        methods = self._convert_function_to_methods(
                            sym_node,
                            is_static=True,
                            conv=conv,
                            raw_names=raw_names,
                            surface_level=surface_level,
                            canonical_target_prefix=target_prefix,
                        )
                        for m in methods:
                            m.python_name = sym_name
                            m.csharp_name = sym_name if raw_names else snake_to_pascal(sym_name)
                        all_module_methods.extend(methods)
                    elif isinstance(sym_node, ast.ClassDef):
                        cls_ret = sym_node.name if raw_names else snake_to_pascal(sym_node.name)
                        fn_name = sym_node.name if raw_names else snake_to_pascal(sym_node.name)
                        m = GeneratedMethod(
                            python_name=sym_name,
                            csharp_name=fn_name,
                            return_type=cls_ret,
                            parameters=[
                                GeneratedParameter("args", "object[]", is_params=True),
                                GeneratedParameter("kwargs", "object", is_kwargs=True, default_value="null"),
                            ],
                            is_static=True,
                            surface_level=surface_level,
                            canonical_api=f"{target_prefix}.{fn_name}" if target_prefix else None,
                        )
                        all_module_methods.append(m)
                else:
                    fn_name = sym_name if raw_names else snake_to_pascal(sym_name)
                    m = GeneratedMethod(
                        python_name=sym_name,
                        csharp_name=fn_name,
                        return_type="object",
                        parameters=[
                            GeneratedParameter("args", "object[]", is_params=True),
                            GeneratedParameter("kwargs", "object", is_kwargs=True, default_value="null"),
                        ],
                        is_static=True,
                        surface_level=surface_level,
                        canonical_api=f"{target_prefix}.{fn_name}" if target_prefix else None,
                    )
                    all_module_methods.append(m)

        all_module_methods = self._deduplicate_methods(all_module_methods)
        for m in all_module_methods:
            lines.extend(self._render_method(m, indent="    "))

        lines.append("}")
        return lines, extra_namespaces

    def _generate_class(
        self,
        cls_node: ast.ClassDef,
        *,
        surface_level: int = 0,
        canonical_target_prefix: str | None = None,
        raw_names: bool = False,
        is_primitive: bool = False,
    ) -> list[str]:
        lines: list[str] = []
        class_name = cls_node.name
        conv = TypeConverter(current_class_name=class_name)

        csharp_cls_name = class_name if raw_names else snake_to_pascal(class_name)
        bases: list[str] = []
        for b in cls_node.bases:
            base_type = conv.convert(b).rendered
            base_clean = base_type.split("<")[0].lstrip("@")
            if (
                base_clean not in ("object", "Generic", "Protocol", "")
                and base_clean != csharp_cls_name
                and base_clean != snake_to_pascal(class_name)
            ):
                if base_type in RESERVED_KEYWORDS:
                    base_type = f"@{base_type}"
                bases.append(base_type)

        base_clause = f" : {', '.join(bases)}" if bases else ""

        if is_primitive:
            lines.append(f'[MapsTo("{class_name}")]')
            lines.append(f'[RuntimeType("{self.module_name}.{class_name}")]')
            lines.append(f'public primitive class {escape_identifier(snake_to_pascal(class_name))}{base_clause}')
        else:
            if class_name != csharp_cls_name:
                lines.append(f'[MapsTo("{class_name}")]')
            if surface_level > 0:
                lines.append(f"[SurfaceLevel({surface_level})]")
            if canonical_target_prefix:
                lines.append(f'[CanonicalApi("{canonical_target_prefix}.{snake_to_pascal(class_name)}")]')
            lines.append(f'public class {escape_identifier(csharp_cls_name)}{base_clause}')

        lines.append("{")

        properties_seen: dict[str, GeneratedMethod] = {}
        normal_methods: list[GeneratedMethod] = []

        for item in cls_node.body:
            # Field annotations: `x: int`
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_type = conv.convert(item.annotation).rendered
                field_name = item.target.id if raw_names else snake_to_pascal(item.target.id)
                if not is_primitive:
                    if surface_level > 0:
                        lines.append(f"    [SurfaceLevel({surface_level})]")
                    if canonical_target_prefix:
                        lines.append(
                            f'    [CanonicalApi("{canonical_target_prefix}.{snake_to_pascal(class_name)}.{snake_to_pascal(item.target.id)}")]'
                        )
                lines.append(f'    [MapsTo("{item.target.id}")]')
                lines.append(f"    public extern {field_type} {escape_identifier(field_name)};")
                continue

            if isinstance(item, ast.FunctionDef):
                # Detect property getter
                if any(self._is_decorator(d, "property") for d in item.decorator_list):
                    ret_type = conv.convert(item.returns, is_return=False).rendered
                    prop_name = item.name if raw_names else snake_to_pascal(item.name)
                    prop_canonical = (
                        f"{canonical_target_prefix}.{snake_to_pascal(class_name)}.{snake_to_pascal(item.name)}"
                        if canonical_target_prefix
                        else None
                    )
                    gm = GeneratedMethod(
                        csharp_name=prop_name,
                        python_name=item.name,
                        return_type=ret_type,
                        is_property=True,
                        has_setter=False,
                        surface_level=0 if is_primitive else surface_level,
                        canonical_api=None if is_primitive else prop_canonical,
                    )
                    properties_seen[item.name] = gm
                    continue

                # Detect property setter: `@prop.setter`
                if any(isinstance(d, ast.Attribute) and d.attr == "setter" for d in item.decorator_list):
                    if item.name in properties_seen:
                        properties_seen[item.name].has_setter = True
                    continue

                is_static = any(self._is_decorator(d, "staticmethod", "classmethod") for d in item.decorator_list)
                method_target_prefix = (
                    f"{canonical_target_prefix}.{snake_to_pascal(class_name)}" if canonical_target_prefix else None
                )
                converted = self._convert_function_to_methods(
                    item,
                    is_static=is_static,
                    conv=conv,
                    class_name=class_name if raw_names else snake_to_pascal(class_name),
                    raw_names=raw_names,
                    surface_level=0 if is_primitive else surface_level,
                    canonical_target_prefix=None if is_primitive else method_target_prefix,
                )
                normal_methods.extend(converted)

        # Render properties
        for gm in properties_seen.values():
            accessor = "{ get; set; }" if gm.has_setter else "{ get; }"
            if gm.surface_level > 0:
                lines.append(f"    [SurfaceLevel({gm.surface_level})]")
            if gm.canonical_api:
                lines.append(f'    [CanonicalApi("{gm.canonical_api}")]')
            lines.append(f'    [MapsTo("{gm.python_name}")]')
            lines.append(f"    public extern {gm.return_type} {escape_identifier(gm.csharp_name)} {accessor}")

        # Render merged indexers and methods
        merged_indexers: dict[str, GeneratedMethod] = {}
        final_methods: list[GeneratedMethod] = []
        for m in normal_methods:
            if m.is_indexer and m.indexer_key_type:
                if m.indexer_key_type in merged_indexers:
                    if m.has_setter:
                        merged_indexers[m.indexer_key_type].has_setter = True
                else:
                    merged_indexers[m.indexer_key_type] = m
            else:
                final_methods.append(m)

        for idxer in merged_indexers.values():
            lines.extend(self._render_method(idxer, indent="    "))

        final_methods = self._deduplicate_methods(final_methods)
        for m in final_methods:
            lines.extend(self._render_method(m, indent="    "))

        lines.append("}")
        return lines

    @staticmethod
    def _deduplicate_methods(methods: list[GeneratedMethod]) -> list[GeneratedMethod]:
        """
        Deduplicates overloaded methods to prevent Rule PS002 runtime collisions
        and identical C# signature errors.
        """
        unique_methods: list[GeneratedMethod] = []
        seen_exact: set[tuple[str, bool, tuple[str, ...]]] = set()
        seen_erased_arities: dict[tuple[str, bool], dict[int, set[tuple[str, ...]]]] = {}

        for m in methods:
            if m.is_indexer:
                unique_methods.append(m)
                continue

            csharp_param_types = tuple(p.type_name for p in m.parameters)
            exact_key = (m.csharp_name, m.is_static, csharp_param_types)
            if exact_key in seen_exact:
                continue

            core_params = [p for p in m.parameters if not p.is_params and not p.is_kwargs]
            min_arity = sum(1 for p in core_params if p.default_value is None)
            max_arity = len(core_params)

            fn_group_key = (m.csharp_name, m.is_static)
            group_erased = seen_erased_arities.setdefault(fn_group_key, {})

            collided = False
            for k in range(min_arity, max_arity + 1):
                erased_k = tuple(_erased_type_token(p.type_name) for p in core_params[:k])
                if erased_k in group_erased.get(k, set()):
                    collided = True
                    break

            if collided:
                continue

            for k in range(min_arity, max_arity + 1):
                erased_k = tuple(_erased_type_token(p.type_name) for p in core_params[:k])
                group_erased.setdefault(k, set()).add(erased_k)

            seen_exact.add(exact_key)
            unique_methods.append(m)

        return unique_methods

    def _convert_function_to_methods(
        self,
        fn: ast.FunctionDef,
        *,
        is_static: bool,
        conv: TypeConverter,
        class_name: str | None = None,
        raw_names: bool = False,
        surface_level: int = 0,
        canonical_target_prefix: str | None = None,
    ) -> list[GeneratedMethod]:
        is_constructor = fn.name == "__init__" and class_name is not None
        is_indexer = fn.name in ("__getitem__", "__setitem__") and class_name is not None

        if is_constructor and class_name is not None:
            csharp_name = class_name
            canonical_target = None
        elif raw_names:
            csharp_name = fn.name
            canonical_target = (
                f"{canonical_target_prefix}.{snake_to_pascal(fn.name)}" if canonical_target_prefix else None
            )
        else:
            csharp_name = snake_to_pascal(fn.name)
            canonical_target = (
                f"{canonical_target_prefix}.{csharp_name}" if canonical_target_prefix else None
            )
        ret_type_info = conv.convert(fn.returns, is_return=True)
        ret_type = "void" if is_constructor else ret_type_info.rendered
        if fn.name == "__getitem__" and (ret_type == "void" or fn.returns is None):
            ret_type = "object"

        # Skip `self` or `cls` parameter
        args = fn.args
        pos_args = args.posonlyargs + args.args
        if class_name and not is_static and pos_args:
            pos_args = pos_args[1:]

        # Extract defaults
        defaults_count = len(args.defaults)
        first_default_idx = len(pos_args) - defaults_count

        raw_param_infos: list[tuple[str, ConvertedType, str | None]] = []
        for i, a in enumerate(pos_args):
            p_type_info = conv.convert(a.annotation, is_return=False)
            default_val: str | None = None
            if i >= first_default_idx:
                def_node = args.defaults[i - first_default_idx]
                default_val = self._extract_default_value(def_node)
            raw_param_infos.append((a.arg, p_type_info, default_val))

        # Handle *args (vararg)
        vararg_param: GeneratedParameter | None = None
        if args.vararg:
            v_conv = conv.convert(args.vararg.annotation, is_return=False)
            if v_conv.is_union or v_conv.rendered in ("object", ""):
                v_type = "object[]"
            else:
                v_type = v_conv.rendered
                if not v_type.endswith("[]"):
                    v_type = f"{v_type}[]"
            vararg_param = GeneratedParameter(
                name=escape_identifier(args.vararg.arg),
                type_name=v_type,
                is_params=True,
            )

        # Handle **kwargs (kwarg)
        kwarg_param: GeneratedParameter | None = None
        if args.kwarg:
            kwarg_param = GeneratedParameter(
                name=escape_identifier(args.kwarg.arg),
                type_name="object",
                default_value="null",
                is_kwargs=True,
            )

        # Overload expansion for Union parameters:
        # For each parameter with a Union, compute Cartesian product of alternatives
        param_alternatives: list[list[GeneratedParameter]] = []
        for p_name, p_type_info, p_def in raw_param_infos:
            overload_types = p_type_info.get_overload_types()
            alts = [
                GeneratedParameter(
                    name=escape_identifier(p_name),
                    type_name=t,
                    default_value=p_def,
                )
                for t in overload_types
            ]
            param_alternatives.append(alts)

        expanded_param_lists = list(itertools.product(*param_alternatives)) if param_alternatives else [()]

        results: list[GeneratedMethod] = []
        for p_tuple in expanded_param_lists:
            p_list = list(p_tuple)
            if vararg_param:
                p_list.append(vararg_param)
            if kwarg_param:
                p_list.append(kwarg_param)

            # Special case for __getitem__ / __setitem__
            if is_indexer:
                key_type = p_list[0].type_name if p_list else "object"
                val_type = ret_type if fn.name == "__getitem__" else (p_list[1].type_name if len(p_list) > 1 else "object")
                results.append(
                    GeneratedMethod(
                        csharp_name="this",
                        python_name=fn.name,
                        return_type=val_type,
                        is_indexer=True,
                        indexer_key_type=key_type,
                        has_setter=(fn.name == "__setitem__"),
                        surface_level=surface_level,
                    )
                )
            else:
                results.append(
                    GeneratedMethod(
                        csharp_name=csharp_name,
                        python_name=fn.name,
                        return_type=ret_type,
                        parameters=p_list,
                        is_static=is_static,
                        is_constructor=is_constructor,
                        surface_level=surface_level,
                        canonical_api=canonical_target,
                    )
                )

        return results

    def _render_method(self, m: GeneratedMethod, indent: str = "    ") -> list[str]:
        lines: list[str] = []

        if m.is_indexer:
            ret = "object" if m.return_type in ("void", "None", "") else m.return_type
            accessor = "{ get; set; }" if m.has_setter else "{ get; }"
            lines.append(f"{indent}public extern {ret} this[{m.indexer_key_type} index] {accessor}")
            return lines

        if m.surface_level > 0:
            lines.append(f"{indent}[SurfaceLevel({m.surface_level})]")
        if m.canonical_api:
            lines.append(f'{indent}[CanonicalApi("{m.canonical_api}")]')
        if not m.is_constructor:
            lines.append(f'{indent}[MapsTo("{m.python_name}")]')

        modifiers = ["public"]
        if m.is_static:
            modifiers.append("static")
        modifiers.append("extern")

        mod_str = " ".join(modifiers)
        ret_prefix = "" if m.is_constructor else f"{m.return_type} "

        param_strs: list[str] = []
        for p in m.parameters:
            prefix = "[KwArgs] " if p.is_kwargs else ("params " if p.is_params else "")
            default_suffix = f" = {p.default_value}" if p.default_value is not None else ""
            param_strs.append(f"{prefix}{p.type_name} {p.name}{default_suffix}")

        params_joined = ", ".join(param_strs)
        lines.append(f"{indent}{mod_str} {ret_prefix}{escape_identifier(m.csharp_name)}({params_joined});")
        return lines

    @staticmethod
    def _is_decorator(node: ast.AST, *names: str) -> bool:
        if isinstance(node, ast.Name):
            return node.id in names
        if isinstance(node, ast.Attribute):
            return node.attr in names
        return False

    @staticmethod
    def _extract_default_value(node: ast.AST) -> str:
        if isinstance(node, ast.Constant):
            if node.value is None:
                return "null"
            if isinstance(node.value, bool):
                return "true" if node.value else "false"
            if isinstance(node.value, (int, float)):
                return str(node.value)
            if isinstance(node.value, str):
                import json
                return json.dumps(node.value)
            if node.value is Ellipsis:
                return "null"
        return "null"
