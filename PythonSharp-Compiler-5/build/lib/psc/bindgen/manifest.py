from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


def compute_file_hash(path: Path) -> str:
    """Compute deterministic SHA-256 hex digest of a file's content."""
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class BindingEntry:
    package_name: str
    pyi_path: str
    pyi_hash: str
    d_ps_path: str
    d_ps_hash: str
    surface_files: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BindingManifest:
    version: str = "1.0"
    entries: dict[str, BindingEntry] = field(default_factory=dict)

    def add_entry(
        self,
        package_name: str,
        pyi_path: Path,
        pyi_hash: str,
        d_ps_path: Path,
        d_ps_hash: str,
        *,
        surface_files: dict[str, str] | None = None,
        dependencies: list[str] | None = None,
    ) -> None:
        self.entries[package_name] = BindingEntry(
            package_name=package_name,
            pyi_path=str(pyi_path),
            pyi_hash=pyi_hash,
            d_ps_path=str(d_ps_path),
            d_ps_hash=d_ps_hash,
            surface_files=surface_files or {},
            dependencies=dependencies or [],
        )

    def is_drifted(self, package_name: str, pyi_path: Path) -> bool:
        """Return True if the source .pyi file has changed since bindings were generated."""
        if package_name not in self.entries:
            return True
        entry = self.entries[package_name]
        if not pyi_path.exists():
            return True
        current_hash = compute_file_hash(pyi_path)
        return current_hash != entry.pyi_hash

    def to_json(self) -> str:
        data = {
            "version": self.version,
            "entries": {k: asdict(v) for k, v in sorted(self.entries.items())},
        }
        return json.dumps(data, indent=2) + "\n"

    def write_to(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load_from(cls, path: Path) -> BindingManifest:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = {
            k: BindingEntry(**v) for k, v in data.get("entries", {}).items()
        }
        return cls(version=data.get("version", "1.0"), entries=entries)

