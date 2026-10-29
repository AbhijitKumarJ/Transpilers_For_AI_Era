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

    def all_input_files(self) -> list[Path]:
        """Returns ambient .d.ps stubs first, followed by user .ps source files."""
        return [*self.stub_files, *self.source_files]


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

    stub_files: list[Path] = []
    if stdlib_dir is not None and stdlib_dir.exists():
        for p in stdlib_dir.rglob("*"):
            if p.is_file() and is_ps_stub_file(p):
                stub_files.append(p)
        stub_files.sort()

    project_stubs: list[Path] = []
    for p in root_dir.rglob("*"):
        if p.is_file() and is_ps_stub_file(p):
            if p not in stub_files:
                project_stubs.append(p)
    project_stubs.sort()
    stub_files.extend(project_stubs)

    source_files = sorted(
        p for p in root_dir.rglob("*")
        if p.is_file() and is_ps_source_file(p)
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
    )
