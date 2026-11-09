from __future__ import annotations

import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

PS_SOURCE_EXTENSIONS: tuple[str, ...] = (".ps", ".pysharp", ".pys")
PS_STUB_EXTENSIONS: tuple[str, ...] = (".d.ps", ".d.pysharp", ".d.pys")
PS_PROJECT_EXTENSIONS: tuple[str, ...] = (".psproj", ".pysharpproj")


def is_ps_stub_file(path: Path | str) -> bool:
    name = Path(path).name.lower()
    return any(name.endswith(ext) for ext in PS_STUB_EXTENSIONS)


def is_ps_source_file(path: Path | str) -> bool:
    name = Path(path).name.lower()
    return any(name.endswith(ext) for ext in PS_SOURCE_EXTENSIONS) and not is_ps_stub_file(path)


def is_ps_project_file(path: Path | str) -> bool:
    name = Path(path).name.lower()
    return any(name.endswith(ext) for ext in PS_PROJECT_EXTENSIONS)


@dataclass(slots=True)
class PsProjectConfig:
    """Represents a .psproj assembly boundary and build configuration."""

    project_name: str
    root_dir: Path
    out_dir: Path = field(default_factory=lambda: Path("dist"))
    target_python: str = "3.11"
    emit_pyc: bool = True
    source_files: list[Path] = field(default_factory=list)
    stub_files: list[Path] = field(default_factory=list)
    pypi_dependencies: dict[str, str] = field(default_factory=dict)
    project_references: list[Path] = field(default_factory=list)
    project_file_path: Path | None = None

    def all_input_files(self) -> list[Path]:
        """Returns ambient .d.ps stubs first, followed by user .ps source files."""
        return [*self.stub_files, *self.source_files]


def stdlib_stub_sort_key(p: Path) -> tuple[int, str]:
    """Ensures 00_core stubs are sorted in strict topological order before others."""
    name = p.name
    pos = str(p)
    if "00_core" in pos:
        if name.startswith("00_"):
            return (0, name)
        if name.startswith("01_"):
            return (1, name)
        if name.startswith("02_"):
            return (2, name)
        if name.startswith("03_"):
            return (3, name)
        if name.startswith("04_"):
            return (4, name)
        if name.startswith("05_"):
            return (5, name)
        return (6, name)
    if "01_python_stdlib" in pos:
        return (10, pos)
    if "02_scientific_and_ai" in pos:
        return (20, pos)
    return (30, pos)


def find_stdlib_stubs(stdlib_dir: Path | None) -> list[Path]:
    """Discovers and deterministically orders all standard library `.d.ps` stubs."""
    if stdlib_dir is None or not stdlib_dir.exists():
        return []
    has_00_core = (stdlib_dir / "00_core").is_dir()
    stubs = [
        p for p in stdlib_dir.rglob("*")
        if p.is_file() and is_ps_stub_file(p) and not (has_00_core and p.name == "PythonSharp.Core.d.ps")
    ]
    stubs.sort(key=stdlib_stub_sort_key)
    return stubs


def load_project(psproj_path: Path, stdlib_dir: Path | None = None) -> PsProjectConfig:
    """
    Loads a PythonSharp project file (.psproj in XML or TOML format) and
    discovers all .ps and .d.ps files recursively inside the project root.
    """
    psproj_path = psproj_path.resolve()
    root_dir = psproj_path.parent
    raw_text = psproj_path.read_text(encoding="utf-8").strip()

    project_name = psproj_path.stem
    out_dir = root_dir / "dist"
    target_python = "3.11"
    emit_pyc = True
    pypi_deps: dict[str, str] = {}

    if raw_text.startswith("<"):
        # Parse C#-style XML .psproj
        root = ET.fromstring(raw_text)
        prop_group = root.find("PropertyGroup")
        if prop_group is not None:
            if (name_el := prop_group.find("AssemblyName")) is not None and name_el.text:
                project_name = name_el.text.strip()
            if (out_el := prop_group.find("OutputPath")) is not None and out_el.text:
                out_dir = root_dir / out_el.text.strip()
            if (py_el := prop_group.find("TargetPython")) is not None and py_el.text:
                target_python = py_el.text.strip()
            if (pyc_el := prop_group.find("EmitPyc")) is not None and pyc_el.text:
                emit_pyc = pyc_el.text.strip().lower() == "true"

        for pkg in root.findall("./ItemGroup/PyPiPackage"):
            inc = pkg.attrib.get("Include")
            ver = pkg.attrib.get("Version", "*")
            if inc:
                pypi_deps[inc] = ver

        project_references: list[Path] = []
        for ref in root.findall("./ItemGroup/ProjectReference"):
            inc = ref.attrib.get("Include")
            if inc:
                target_p = (root_dir / inc).resolve()
                if target_p not in project_references:
                    project_references.append(target_p)
    else:
        # Parse TOML-formatted .psproj
        data = tomllib.loads(raw_text)
        proj_sec = data.get("project", {})
        project_name = proj_sec.get("name", project_name)
        if "out_dir" in proj_sec:
            out_dir = root_dir / proj_sec["out_dir"]
        target_python = proj_sec.get("target_python", target_python)
        emit_pyc = bool(proj_sec.get("emit_pyc", emit_pyc))
        pypi_deps = dict(data.get("dependencies", {}))
        project_references = []
        for ref in data.get("project_references", []):
            target_p = (root_dir / ref).resolve()
            if target_p not in project_references:
                project_references.append(target_p)

    stub_files: list[Path] = find_stdlib_stubs(stdlib_dir)

    ignored_dir_names = {"dist", ".git", ".venv", "venv", "__pycache__", "node_modules"}
    if out_dir.exists():
        ignored_dir_names.add(out_dir.name)

    project_stubs: list[Path] = []
    for p in root_dir.rglob("*"):
        if any(part in ignored_dir_names for part in p.parts):
            continue
        if p.is_file() and is_ps_stub_file(p):
            if p not in stub_files:
                project_stubs.append(p)
    project_stubs.sort()
    stub_files.extend(project_stubs)

    source_files = sorted(
        p for p in root_dir.rglob("*")
        if p.is_file() and is_ps_source_file(p) and not any(part in ignored_dir_names for part in p.parts)
    )

    return PsProjectConfig(
        project_name=project_name,
        root_dir=root_dir,
        out_dir=out_dir,
        target_python=target_python,
        emit_pyc=emit_pyc,
        source_files=source_files,
        stub_files=stub_files,
        pypi_dependencies=pypi_deps,
        project_references=project_references,
        project_file_path=psproj_path,
    )


def resolve_project_dependencies(
    config: PsProjectConfig,
    stdlib_dir: Path | None = None,
) -> list[PsProjectConfig]:
    """
    Recursively resolves and topologically orders all .psproj dependencies.
    Detects circular references and ensures dependencies are returned before dependents.
    """
    ordered_deps: list[PsProjectConfig] = []
    visiting: set[Path] = set()
    visited: set[Path] = set()

    def visit(proj_path: Path, chain: list[str]) -> None:
        proj_path = proj_path.resolve()
        if proj_path.is_dir():
            psprojs = [p for p in proj_path.glob("*") if is_ps_project_file(p)]
            if not psprojs:
                raise FileNotFoundError(f"No .psproj file found in referenced directory '{proj_path}'.")
            proj_path = psprojs[0].resolve()

        if proj_path in visiting:
            cycle = " -> ".join([*chain, proj_path.stem])
            raise ValueError(f"Circular project reference detected: {cycle}")

        if proj_path in visited:
            return

        visiting.add(proj_path)
        dep_cfg = load_project(proj_path, stdlib_dir=stdlib_dir)

        for ref in dep_cfg.project_references:
            visit(ref, [*chain, dep_cfg.project_name])

        visiting.remove(proj_path)
        visited.add(proj_path)
        ordered_deps.append(dep_cfg)

    for ref in config.project_references:
        visit(ref, [config.project_name])

    return ordered_deps


def add_project_reference(target_proj: Path, ref_proj: Path) -> Path:
    """
    Adds a <ProjectReference Include="..." /> to target_proj pointing to ref_proj.
    Returns the resolved target .psproj path.
    """
    import os

    target_proj = target_proj.resolve()
    if target_proj.is_dir():
        projs = [p for p in target_proj.glob("*") if is_ps_project_file(p)]
        if not projs:
            raise FileNotFoundError(f"No .psproj file found in target directory '{target_proj}'.")
        target_proj = projs[0]

    ref_proj = ref_proj.resolve()
    if ref_proj.is_dir():
        projs = [p for p in ref_proj.glob("*") if is_ps_project_file(p)]
        if not projs:
            raise FileNotFoundError(f"No .psproj file found in reference directory '{ref_proj}'.")
        ref_proj = projs[0]

    rel_path = os.path.relpath(ref_proj, target_proj.parent).replace("\\", "/")

    raw_text = target_proj.read_text(encoding="utf-8").strip()
    if raw_text.startswith("<"):
        root = ET.fromstring(raw_text)
        for existing in root.findall("./ItemGroup/ProjectReference"):
            if existing.attrib.get("Include") == rel_path:
                return target_proj

        item_group = root.find("ItemGroup")
        if item_group is None:
            item_group = ET.SubElement(root, "ItemGroup")

        ET.SubElement(item_group, "ProjectReference", Include=rel_path)
        ET.indent(root, space="  ")
        updated_xml = ET.tostring(root, encoding="utf-8").decode("utf-8")
        target_proj.write_text(updated_xml + "\n", encoding="utf-8")
    else:
        if rel_path in raw_text:
            return target_proj
        lines = target_proj.read_text(encoding="utf-8").splitlines()
        ref_line = f'    "{rel_path}",'
        if any("project_references" in line_text for line_text in lines):
            idx = next(i for i, line_text in enumerate(lines) if "project_references" in line_text)
            lines.insert(idx + 1, ref_line)
        else:
            lines.append("\nproject_references = [")
            lines.append(ref_line)
            lines.append("]")
        target_proj.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return target_proj
