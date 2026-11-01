"""
PythonSharp Ecosystem Binding Generator (`ps-bindgen`).
Translates Python `.pyi` type stubs into PythonSharp ambient `.d.ps` declarations.
"""

from __future__ import annotations

import ast
from pathlib import Path

from psc.bindgen.generator import BindgenGenerator
from psc.bindgen.manifest import BindingManifest, compute_content_hash, compute_file_hash

__all__ = [
    "generate_bindings",
    "parse_pyi_file",
    "parse_pyi_source",
    "BindingManifest",
    "BindgenGenerator",
]


def parse_pyi_source(
    source: str,
    module_name: str,
    *,
    root_namespace: str = "Extern",
) -> str:
    """Parse a .pyi string source and generate the corresponding .d.ps text."""
    pyi_ast = ast.parse(source)
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
) -> list[Path]:
    """
    Generate .d.ps stubs from a single .pyi file or directory of .pyi files.
    Writes emitted files and updates the binding manifest.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    mpath = manifest_path or (out_dir / "psc-bindings-manifest.json")
    manifest = BindingManifest.load_from(mpath)

    pyi_files: list[Path] = []
    if target.is_file() and target.suffix == ".pyi":
        pyi_files.append(target)
    elif target.is_dir():
        pyi_files.extend(sorted(target.rglob("*.pyi")))

    generated_files: list[Path] = []
    for pyi in pyi_files:
        module_name = pyi.stem
        # If part of a subfolder structure, determine logical module name
        if target.is_dir():
            try:
                rel = pyi.relative_to(target)
                parts = list(rel.parts)
                parts[-1] = pyi.stem
                if parts[-1] == "__init__":
                    parts.pop()
                if parts:
                    module_name = ".".join(parts)
            except ValueError:
                pass

        d_ps_content = parse_pyi_file(pyi, module_name, root_namespace=root_namespace)
        dest_filename = f"{module_name}.d.ps"
        dest_path = out_dir / dest_filename
        dest_path.write_text(d_ps_content, encoding="utf-8")
        generated_files.append(dest_path)

        manifest.add_entry(
            package_name=module_name,
            pyi_path=pyi.resolve(),
            pyi_hash=compute_file_hash(pyi),
            d_ps_path=dest_path.resolve(),
            d_ps_hash=compute_content_hash(d_ps_content),
        )

    manifest.write_to(mpath)
    return generated_files
