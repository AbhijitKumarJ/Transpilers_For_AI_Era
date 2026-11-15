from __future__ import annotations

import json
import re
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


@dataclass
class PsConfigFile:
    """Represents declarative configuration from .ps.conf.json / psconfig.json / pythonsharp.json."""

    stub_layers: dict[str, bool] = field(
        default_factory=lambda: {
            "00_core": True,
            "01_python_stdlib": True,
            "02_scientific_and_ai": True,
            "03_typeshed_replica": True,
            "03_extended": True,
            "external_stubs": True,
        }
    )
    disabled_packages: list[str] = field(default_factory=list)
    preferred_surface: int | None = None
    config_path: Path | None = None


def find_ps_config_file(start_dir: Path) -> Path | None:
    """Discovers .ps.conf.json, psconfig.json, or pythonsharp.json walking up to git root."""
    cur = start_dir.resolve()
    if cur.is_file():
        cur = cur.parent
    while cur != cur.parent:
        for fname in (".ps.conf.json", "psconfig.json", "pythonsharp.json"):
            cand = cur / fname
            if cand.is_file():
                return cand
        if (cur / ".git").is_dir():
            break
        cur = cur.parent
    return None


def load_ps_config(start_dir: Path | None = None) -> PsConfigFile:
    """Loads and parses .ps.conf.json from start_dir or parent hierarchy."""
    cfg = PsConfigFile()
    if start_dir is None:
        return cfg
    cfg_path = find_ps_config_file(start_dir)
    if cfg_path is None or not cfg_path.is_file():
        return cfg

    cfg.config_path = cfg_path
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return cfg

        if "stub_layers" in data and isinstance(data["stub_layers"], dict):
            for k, v in data["stub_layers"].items():
                cfg.stub_layers[k] = bool(v)

        if "disabled_layers" in data and isinstance(data["disabled_layers"], list):
            for layer in data["disabled_layers"]:
                cfg.stub_layers[str(layer)] = False

        if "external_stubs" in data:
            cfg.stub_layers["external_stubs"] = bool(data["external_stubs"])

        if "disabled_packages" in data and isinstance(data["disabled_packages"], list):
            cfg.disabled_packages = [str(p).strip().lower() for p in data["disabled_packages"] if p]

        if "preferred_surface" in data and data["preferred_surface"] is not None:
            try:
                cfg.preferred_surface = int(data["preferred_surface"])
            except (ValueError, TypeError):
                pass
    except Exception:
        pass
    return cfg


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
    config: PsConfigFile = field(default_factory=PsConfigFile)

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


def extract_referenced_namespaces(source_files: list[Path]) -> set[str]:
    """Scans project source files for using/extern using namespaces to enable lazy stub loading."""
    namespaces: set[str] = set()
    ns_regex = re.compile(r"\b(?:using|extern\s+using)\s+([A-Za-z0-9_.]+)\s*;")
    for f in source_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            for m in ns_regex.finditer(content):
                namespaces.add(m.group(1).strip())
        except Exception:
            pass
    return namespaces


def find_stdlib_stubs(
    stdlib_dir: Path | None,
    referenced_namespaces: set[str] | None = None,
    config: PsConfigFile | None = None,
) -> list[Path]:
    """
    Discovers and deterministically orders all standard library `.d.ps` stubs.
    - Layer 0 & Layer 1 (00_core, 01_python_stdlib, 02_scientific_and_ai) are loaded eagerly (<95 files).
    - Layer 2 (03_typeshed_replica / 03_extended) is loaded lazily on demand matching referenced namespaces.
    - Respects .ps.conf.json layer toggles and disabled packages when config is provided.
    """
    if stdlib_dir is None or not stdlib_dir.exists():
        return []
    cfg = config or PsConfigFile()
    has_00_core = (stdlib_dir / "00_core").is_dir()

    def _is_layer_allowed(p: Path) -> bool:
        parts = p.parts
        if "00_core" in parts and not cfg.stub_layers.get("00_core", True):
            return False
        if "01_python_stdlib" in parts and not cfg.stub_layers.get("01_python_stdlib", True):
            return False
        if "02_scientific_and_ai" in parts and not cfg.stub_layers.get("02_scientific_and_ai", True):
            return False
        if ("03_typeshed_replica" in parts or "03_extended" in parts) and (
            not cfg.stub_layers.get("03_typeshed_replica", True)
            or not cfg.stub_layers.get("03_extended", True)
        ):
            return False
        if cfg.disabled_packages:
            stem_lower = p.name.replace(".d.ps", "").lower()
            parts_lower = [part.lower() for part in parts]
            for dp in cfg.disabled_packages:
                if stem_lower == dp or dp in parts_lower or any(part.startswith(f"{dp}.") or part.endswith(f".{dp}") for part in parts_lower):
                    return False
        return True

    stubs = [
        p for p in stdlib_dir.rglob("*")
        if p.is_file() and is_ps_stub_file(p) and not (has_00_core and p.name == "PythonSharp.Core.d.ps")
        and "03_typeshed_replica" not in p.parts and "03_extended" not in p.parts
        and _is_layer_allowed(p)
    ]

    # Layer 2: 03_typeshed_replica / 03_extended (Lazy On-Demand)
    if cfg.stub_layers.get("03_typeshed_replica", True) and cfg.stub_layers.get("03_extended", True):
        typeshed_dir = stdlib_dir / "03_typeshed_replica"
        if not typeshed_dir.exists():
            typeshed_dir = stdlib_dir / "03_extended"

        if typeshed_dir.is_dir() and referenced_namespaces:
            norm_refs = {ns.lower() for ns in referenced_namespaces}
            for child in typeshed_dir.iterdir():
                child_name = child.name.replace(".d.ps", "").lower()
                matched = any(
                    child_name == ref
                    or ref.endswith(f".{child_name}")
                    or ref.startswith(f"{child_name}.")
                    or f".{child_name}." in ref
                    for ref in norm_refs
                )
                if matched:
                    if child.is_dir():
                        stubs.extend(
                            p for p in child.rglob("*")
                            if p.is_file() and is_ps_stub_file(p) and _is_layer_allowed(p)
                        )
                    elif is_ps_stub_file(child) and _is_layer_allowed(child):
                        stubs.append(child)

    stubs.sort(key=stdlib_stub_sort_key)
    return stubs


def load_project(
    psproj_path: Path,
    stdlib_dir: Path | None = None,
    config: PsConfigFile | None = None,
) -> PsProjectConfig:
    """
    Loads a PythonSharp project file (.psproj in XML or TOML format) and
    discovers all .ps and .d.ps files recursively inside the project root.
    """
    psproj_path = psproj_path.resolve()
    root_dir = psproj_path.parent
    ps_config = config or load_ps_config(root_dir)
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

    ignored_dir_names = {"dist", ".git", ".venv", "venv", "__pycache__", "node_modules", ".ps-stubs", "typings"}
    if out_dir.exists():
        ignored_dir_names.add(out_dir.name)

    source_files = sorted(
        p for p in root_dir.rglob("*")
        if p.is_file() and is_ps_source_file(p) and not any(part in ignored_dir_names for part in p.parts)
    )

    ref_namespaces = extract_referenced_namespaces(source_files)
    stub_files: list[Path] = find_stdlib_stubs(
        stdlib_dir, referenced_namespaces=ref_namespaces, config=ps_config
    )

    project_stubs: list[Path] = []
    # Dedicated 3rd-party stub directories: .ps-stubs/, typings/, or virtualenv share
    dedicated_dirs: list[Path] = []
    if ps_config.stub_layers.get("external_stubs", ps_config.stub_layers.get("dedicated_stubs", True)):
        dedicated_dirs.extend([root_dir / ".ps-stubs", root_dir / "typings"])
        venv_stubs = root_dir / ".venv" / "share" / "pythonsharp" / "stubs"
        if venv_stubs.is_dir():
            dedicated_dirs.append(venv_stubs)

        # Walk up parent directories to discover workspace-level stubs
        cur = root_dir.parent
        while cur != cur.parent:
            for cand in [cur / ".ps-stubs", cur / "typings", cur / ".venv" / "share" / "pythonsharp" / "stubs"]:
                if cand.is_dir() and cand not in dedicated_dirs:
                    dedicated_dirs.append(cand)
            if (cur / ".git").is_dir():
                break
            cur = cur.parent

    norm_refs = {ns.lower() for ns in ref_namespaces} if ref_namespaces else set()
    for d in dedicated_dirs:
        if d.is_dir():
            for child in d.iterdir():
                child_name = child.name.replace(".d.ps", "").lower()
                if norm_refs:
                    matched = any(
                        child_name == ref
                        or ref.startswith(f"{child_name}.")
                        or f".{child_name}." in ref
                        or ref.endswith(f".{child_name}")
                        for ref in norm_refs
                    )
                    if not matched:
                        continue
                if child.is_dir():
                    for p in child.rglob("*"):
                        if p.is_file() and is_ps_stub_file(p):
                            if ps_config.preferred_surface is not None:
                                if p.name.startswith("0") and len(p.name) > 2 and p.name[1] in "123":
                                    surf = int(p.name[1])
                                    if surf != ps_config.preferred_surface:
                                        continue
                            if p not in stub_files and p not in project_stubs:
                                project_stubs.append(p)
                elif is_ps_stub_file(child) and child not in stub_files and child not in project_stubs:
                    if ps_config.preferred_surface is not None:
                        if child.name.startswith("0") and len(child.name) > 2 and child.name[1] in "123":
                            surf = int(child.name[1])
                            if surf != ps_config.preferred_surface:
                                continue
                    project_stubs.append(child)

    for p in root_dir.rglob("*"):
        if any(part in ignored_dir_names for part in p.parts):
            continue
        if p.is_file() and is_ps_stub_file(p):
            if p not in stub_files and p not in project_stubs:
                project_stubs.append(p)
    project_stubs.sort()
    stub_files.extend(project_stubs)

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
        config=ps_config,
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
