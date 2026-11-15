"""
PythonSharp Ecosystem Binding Generator (`ps-bindgen`).
Translates Python `.pyi` type stubs into PythonSharp ambient `.d.ps` declarations.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import warnings

from psc.bindgen.generator import BindgenGenerator
from psc.bindgen.manifest import BindingManifest, compute_content_hash, compute_file_hash

__all__ = [
    "generate_bindings",
    "parse_pyi_file",
    "parse_pyi_source",
    "BindingManifest",
    "BindgenGenerator",
]

_PYRIGHT_INVALID_ALIAS_PATTERN = re.compile(
    r"^(?![ \t]*type\b)([A-Za-z_][A-Za-z0-9_]*\[[^\]]*\*\*[^\]]*\]\s*=)",
    re.MULTILINE,
)


def _sanitize_pyi_source(source: str) -> str:
    """Fixes Pyright stubgen bug emitting `Name[**P] = ...` instead of `type Name[**P] = ...`."""
    return _PYRIGHT_INVALID_ALIAS_PATTERN.sub(r"type \1", source)


def parse_pyi_source(
    source: str,
    module_name: str,
    *,
    root_namespace: str = "Extern",
) -> str:
    """Parse a .pyi string source and generate the corresponding .d.ps text."""
    clean_source = _sanitize_pyi_source(source)
    pyi_ast = ast.parse(clean_source)
    gen = BindgenGenerator(module_name=module_name, root_namespace=root_namespace)
    return gen.generate_d_ps(pyi_ast)


def parse_pyi_file(
    pyi_path: Path,
    module_name: str | None = None,
    *,
    root_namespace: str = "Extern",
) -> str:
    """Read and parse a .pyi file and generate the corresponding .d.ps text."""
    source = pyi_path.read_text(encoding="utf-8")
    mod_name = module_name or pyi_path.stem
    return parse_pyi_source(source, mod_name, root_namespace=root_namespace)


def generate_bindings(
    target: Path,
    out_dir: Path,
    *,
    manifest_path: Path | None = None,
    root_namespace: str = "Extern",
    module_name: str | None = None,
    package_name: str | None = None,
    triple_surface: bool = False,
    include_tests: bool = False,
) -> list[Path]:
    """
    Generate .d.ps stubs from a single .pyi file or directory of .pyi files.
    Writes emitted files and updates the binding manifest.
    When triple_surface=True, outputs the 4-file bundle per module
    (primitives, raw surface 1, csharp bridge surface 2, enterprise surface 3).
    When include_tests=False (default), internal test directories (tests/, test/, testing/)
    are excluded to avoid generating thousands of unnecessary test stubs and syntax warnings.
    """
    import warnings

    out_dir.mkdir(parents=True, exist_ok=True)
    mpath = manifest_path or (out_dir / "psc-bindings-manifest.json")
    manifest = BindingManifest.load_from(mpath)

    pyi_files: list[Path] = []
    if target.is_file() and target.suffix == ".pyi":
        pyi_files.append(target)
    elif target.is_dir():
        pyi_files.extend(sorted(target.rglob("*.pyi")))

    if not include_tests and target.is_dir():
        test_dir_names = {"tests", "test", "testing"}
        filtered: list[Path] = []
        for p in pyi_files:
            try:
                rel = p.relative_to(target)
                if any(part.lower() in test_dir_names for part in rel.parts):
                    continue
            except ValueError:
                pass
            filtered.append(p)
        pyi_files = filtered

    is_package_root = package_name or (target.is_dir() and ((target / "__init__.pyi").exists() or (target / "__init__.py").exists()))
    pkg_prefix = package_name or (target.name if is_package_root else None)

    pkg_symbol_index: dict[str, tuple[ast.FunctionDef | ast.ClassDef, list[str]]] = {}
    if target.is_dir():
        for p in pyi_files:
            try:
                rel = p.relative_to(target)
                parts = [re.sub(r"[^A-Za-z0-9_]+", "_", seg) for seg in rel.parts]
                parts[-1] = re.sub(r"[^A-Za-z0-9_]+", "_", p.stem)
                if parts[-1] == "__init__":
                    parts.pop()
                if pkg_prefix:
                    mod_parts = [pkg_prefix] + parts
                else:
                    mod_parts = parts
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", SyntaxWarning)
                    tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
                for s in tree.body:
                    if isinstance(s, (ast.FunctionDef, ast.ClassDef)):
                        if s.name not in pkg_symbol_index:
                            pkg_symbol_index[s.name] = (s, mod_parts)
            except Exception:
                pass

    generated_files: list[Path] = []
    for pyi in pyi_files:
        mod_name = module_name or pyi.stem
        # If part of a subfolder structure, determine logical module name
        if target.is_dir() and module_name is None:
            try:
                rel = pyi.relative_to(target)
                parts = [re.sub(r"[^A-Za-z0-9_]+", "_", seg) for seg in rel.parts]
                parts[-1] = re.sub(r"[^A-Za-z0-9_]+", "_", pyi.stem)
                if parts[-1] == "__init__":
                    parts.pop()
                if pkg_prefix:
                    if parts:
                        mod_name = f"{pkg_prefix}.{'.'.join(parts)}"
                    else:
                        mod_name = pkg_prefix
                elif parts:
                    mod_name = ".".join(parts)
                else:
                    mod_name = target.name
            except ValueError:
                pass

        if mod_name.endswith(".__init__"):
            mod_name = mod_name[:-9]

        parts = mod_name.split(".")
        source = _sanitize_pyi_source(pyi.read_text(encoding="utf-8"))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                pyi_ast = ast.parse(source, filename=str(pyi))
        except SyntaxError as ex:
            warnings.warn(f"Skipping malformed pyi stub {pyi}: {ex}")
            continue

        if triple_surface:
            gen = BindgenGenerator(
                module_name=mod_name,
                root_namespace=root_namespace,
                package_symbol_index=pkg_symbol_index,
            )
            bundle = gen.generate_triple_surface_bundle(pyi_ast)

            pkg_dir = out_dir.joinpath(*parts)
            pkg_dir.mkdir(parents=True, exist_ok=True)
            surface_map: dict[str, str] = {}
            for fname, content in bundle.items():
                dest_path = pkg_dir / fname
                dest_path.write_text(content, encoding="utf-8")
                generated_files.append(dest_path)
                if "primitives" in fname:
                    surface_map["primitives"] = str(dest_path.resolve())
                elif "raw" in fname:
                    surface_map["surface_1"] = str(dest_path.resolve())
                elif "csharp" in fname:
                    surface_map["surface_2"] = str(dest_path.resolve())
                elif "enterprise" in fname:
                    surface_map["surface_3"] = str(dest_path.resolve())

            manifest.add_entry(
                package_name=mod_name,
                pyi_path=pyi.resolve(),
                pyi_hash=compute_file_hash(pyi),
                d_ps_path=pkg_dir.resolve(),
                d_ps_hash=compute_content_hash("\n".join(bundle.values())),
                surface_files=surface_map,
            )
        else:
            d_ps_content = parse_pyi_file(pyi, mod_name, root_namespace=root_namespace)
            if len(parts) > 1:
                dest_dir = out_dir.joinpath(*parts[:-1])
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / f"{parts[-1]}.d.ps"
            else:
                dest_path = out_dir / f"{mod_name}.d.ps"
            dest_path.write_text(d_ps_content, encoding="utf-8")
            generated_files.append(dest_path)

            manifest.add_entry(
                package_name=mod_name,
                pyi_path=pyi.resolve(),
                pyi_hash=compute_file_hash(pyi),
                d_ps_path=dest_path.resolve(),
                d_ps_hash=compute_content_hash(d_ps_content),
            )

    manifest.write_to(mpath)
    return generated_files
