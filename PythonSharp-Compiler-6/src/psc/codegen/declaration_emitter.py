from __future__ import annotations

from pathlib import Path

from psc.codegen.topo_sorter import PlannedPythonModule
from psc.frontend.ast_nodes import (
    EnumMember,
    FieldDecl,
    IndexerDecl,
    MethodDecl,
    ParamDecl,
    PropertyDecl,
    TypeDecl,
    TypeKind,
)
from psc.semantics.symbols import TypeSymbol


class DeclarationEmitter:
    """
    Pass 3C — Ambient C# Declaration Header (.d.ps) Emitter:
    Emits clean, strongly-typed ambient declaration files for compiled
    PythonSharp packages and project references (equivalent to TypeScript's `.d.ts`).
    """

    @classmethod
    def emit_module_declaration(cls, planned: PlannedPythonModule, out_dir: Path) -> Path:
        source = cls.generate_declaration_source(planned)
        rel_d_ps = Path(planned.module_rel_path).with_suffix(".d.ps")
        d_ps_path = out_dir / rel_d_ps
        d_ps_path.parent.mkdir(parents=True, exist_ok=True)
        d_ps_path.write_text(source, encoding="utf-8")
        return d_ps_path

    @classmethod
    def generate_declaration_source(cls, planned: PlannedPythonModule) -> str:
        lines: list[str] = [
            "// Auto-generated ambient declarations by PythonSharp (psc)",
        ]

        if planned.namespace:
            lines.append(f"namespace {'.'.join(planned.namespace)};")
            lines.append("")

        lines.append("using PythonSharp.Core;")
        lines.append("")

        for type_sym in planned.types:
            decl = type_sym.ast_node
            lines.extend(cls._emit_type_decl(type_sym, decl))
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def _emit_type_decl(cls, type_sym: TypeSymbol, decl: TypeDecl) -> list[str]:
        lines: list[str] = []

        # Emit attributes if any
        for attr in getattr(decl, "attributes", []):
            attr_name = ".".join(attr.path) if hasattr(attr, "path") and attr.path else getattr(attr, "name", "Attribute")
            args_str = ""
            if attr.args:
                formatted_args = []
                for a in attr.args:
                    expr = getattr(a, "expr", None)
                    val = expr.data.get("value") if expr and hasattr(expr, "data") else None
                    if isinstance(val, str):
                        formatted_args.append(f'"{val}"')
                    elif val is not None:
                        formatted_args.append(str(val))
                    elif hasattr(a, "name") and a.name:
                        formatted_args.append(str(a.name))
                if formatted_args:
                    args_str = f"({', '.join(formatted_args)})"
            lines.append(f"[{attr_name}{args_str}]")

        # Kind & Modifiers
        is_interface = type_sym.is_interface
        is_enum = type_sym.is_enum
        is_struct = type_sym.is_struct
        is_record = decl.kind == TypeKind.RECORD

        mod_parts: list[str] = ["public"]
        if "static" in getattr(decl, "modifiers", []) and not is_interface and not is_enum:
            mod_parts.append("static")
        elif "abstract" in getattr(decl, "modifiers", []) and not is_interface and not is_enum:
            mod_parts.append("abstract")

        if type_sym.is_primitive:
            mod_parts.append("primitive")

        if is_interface:
            kind_str = "interface"
        elif is_enum:
            kind_str = "enum"
        elif is_struct:
            kind_str = "struct"
        elif is_record:
            kind_str = "record"
        else:
            kind_str = "class"

        type_header = f"{' '.join(mod_parts)} {kind_str} {type_sym.name}"
        if type_sym.type_params:
            type_header += f"<{', '.join(type_sym.type_params)}>"

        # Base types
        if getattr(decl, "base_types", None):
            bases = [b.display_name() for b in decl.base_types]
            if bases:
                type_header += f" : {', '.join(bases)}"

        # Generic constraints
        if getattr(decl, "constraints", None):
            for c in decl.constraints:
                type_header += f" where {c.type_param} : {', '.join(b.display_name() for b in c.bounds)}"

        # Enum body
        if is_enum:
            lines.append(f"{type_header}")
            lines.append("{")
            for m in getattr(decl, "enum_members", []):
                if m.value is not None:
                    v_val = m.value.data.get("value") if hasattr(m.value, "data") else None
                    if v_val is not None:
                        lines.append(f"    {m.name} = {v_val},")
                    else:
                        lines.append(f"    {m.name},")
                else:
                    lines.append(f"    {m.name},")
            lines.append("}")
            return lines

        # Record with primary constructor parameters
        record_params = getattr(decl, "primary_ctor_params", None)
        if is_record and record_params:
            params_str = cls._format_params(record_params)
            lines.append(f"{type_header}({params_str});")
            return lines

        lines.append(f"{type_header}")
        lines.append("{")

        for member in getattr(decl, "members", []):
            if isinstance(member, MethodDecl):
                if member.is_constructor:
                    params_str = cls._format_params(member.params)
                    lines.append(f"    public extern {type_sym.name}({params_str});")
                else:
                    lines.append(cls._emit_method_decl(member, is_interface=is_interface))
            elif isinstance(member, PropertyDecl):
                lines.append(cls._emit_property_decl(member, is_interface=is_interface))
            elif isinstance(member, FieldDecl):
                f_type = member.type_ref.display_name() if member.type_ref else "object"
                static_kw = "static " if "static" in member.modifiers else ""
                const_kw = "const " if "const" in member.modifiers else ""
                lines.append(f"    public {static_kw}{const_kw}{f_type} {member.name};")

        lines.append("}")
        return lines

    @classmethod
    def _emit_method_decl(cls, method: MethodDecl, is_interface: bool = False) -> str:
        ret_type = method.return_type.display_name() if method.return_type else "void"
        tparams = f"<{', '.join(method.type_params)}>" if method.type_params else ""
        params_str = cls._format_params(method.params)

        if is_interface:
            return f"    {ret_type} {method.name}{tparams}({params_str});"

        mods: list[str] = ["public"]
        if "static" in method.modifiers:
            mods.append("static")
        elif "override" in method.modifiers:
            mods.append("override")
        elif "virtual" in method.modifiers:
            mods.append("virtual")
        elif "abstract" in method.modifiers:
            mods.append("abstract")

        mods.append("extern")
        return f"    {' '.join(mods)} {ret_type} {method.name}{tparams}({params_str});"

    @classmethod
    def _emit_property_decl(cls, prop: PropertyDecl, is_interface: bool = False) -> str:
        p_type = prop.type_ref.display_name() if prop.type_ref else "object"
        accessors = []
        if any(a.kind == "get" for a in prop.accessors) or not prop.accessors:
            accessors.append("get;")
        if any(a.kind == "set" for a in prop.accessors):
            accessors.append("set;")
        acc_str = f" {{ {' '.join(accessors)} }}"

        if is_interface:
            return f"    {p_type} {prop.name}{acc_str}"

        mods: list[str] = ["public"]
        if "static" in prop.modifiers:
            mods.append("static")
        mods.append("extern")
        return f"    {' '.join(mods)} {p_type} {prop.name}{acc_str}"

    @classmethod
    def _format_params(cls, params: list[ParamDecl]) -> str:
        out: list[str] = []
        for p in params:
            p_type = p.type_ref.display_name() if p.type_ref else "object"
            params_kw = "params " if p.is_params else ""
            default_kw = ""
            if p.default_value is not None:
                val = p.default_value.data.get("value")
                if val is None:
                    default_kw = " = null"
                elif isinstance(val, str):
                    default_kw = f' = "{val}"'
                elif isinstance(val, bool):
                    default_kw = f" = {str(val).lower()}"
                else:
                    default_kw = f" = {val}"
            out.append(f"{params_kw}{p_type} {p.name}{default_kw}")
        return ", ".join(out)
