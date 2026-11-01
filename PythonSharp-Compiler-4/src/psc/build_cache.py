from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from psc.codegen import EmittedArtifact
from psc.project import PsProjectConfig
from psc.version import __version__


def compute_file_sha256(path: Path) -> str:
    """Computes hexadecimal SHA-256 hash of a file's binary contents."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@dataclass(slots=True)
class FileCacheEntry:
    sha256: str
    mtime: float
    size: int


@dataclass(slots=True)
class BuildCache:
    version: str = __version__
    emit_pyc: bool = True
    target_python: str = "3.11"
    inputs: dict[str, FileCacheEntry] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "emit_pyc": self.emit_pyc,
            "target_python": self.target_python,
            "inputs": {
                p: {"sha256": e.sha256, "mtime": e.mtime, "size": e.size}
                for p, e in sorted(self.inputs.items())
            },
            "outputs": sorted(self.outputs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BuildCache:
        inputs_raw = data.get("inputs", {})
        inputs: dict[str, FileCacheEntry] = {}
        if isinstance(inputs_raw, dict):
            for p, entry in inputs_raw.items():
                if isinstance(entry, dict):
                    inputs[str(p)] = FileCacheEntry(
                        sha256=str(entry.get("sha256", "")),
                        mtime=float(entry.get("mtime", 0.0)),
                        size=int(entry.get("size", 0)),
                    )
        outputs_raw = data.get("outputs", [])
        outputs = [str(x) for x in outputs_raw] if isinstance(outputs_raw, list) else []
        return cls(
            version=str(data.get("version", __version__)),
            emit_pyc=bool(data.get("emit_pyc", True)),
            target_python=str(data.get("target_python", "3.11")),
            inputs=inputs,
            outputs=outputs,
        )


class BuildCacheManager:
    """Manages content-hash compilation caching for incremental PythonSharp builds."""

    CACHE_FILENAME = ".psc-cache.json"

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir

    def _cache_path(self, config: PsProjectConfig) -> Path:
        base = self.cache_dir or config.out_dir
        return base / self.CACHE_FILENAME

    def load_cache(self, config: PsProjectConfig) -> BuildCache | None:
        cache_path = self._cache_path(config)
        if not cache_path.is_file():
            return None
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return BuildCache.from_dict(data)
        except Exception:
            return None

    def is_up_to_date(
        self,
        config: PsProjectConfig,
        emit_pyc: bool | None = None,
    ) -> bool:
        cache = self.load_cache(config)
        if cache is None:
            return False

        if cache.version != __version__:
            return False

        target_emit_pyc = config.emit_pyc if emit_pyc is None else emit_pyc
        if cache.emit_pyc != target_emit_pyc or cache.target_python != config.target_python:
            return False

        current_files = config.all_input_files()
        cached_keys = set(cache.inputs.keys())
        current_keys: set[str] = set()

        for f in current_files:
            try:
                rel = str(f.relative_to(config.root_dir))
            except ValueError:
                rel = str(f)
            current_keys.add(rel)

            if rel not in cache.inputs:
                return False

            cached_entry = cache.inputs[rel]
            stat = f.stat()
            # Fast check: size mismatch
            if stat.st_size != cached_entry.size:
                return False
            # Check sha256 if mtime changed
            if stat.st_mtime != cached_entry.mtime:
                current_sha = compute_file_sha256(f)
                if current_sha != cached_entry.sha256:
                    return False

        if current_keys != cached_keys:
            return False

        # Verify all output files still exist
        for out_name in cache.outputs:
            out_file = config.out_dir / out_name
            if not out_file.is_file():
                return False

        return True

    def save_cache(
        self,
        config: PsProjectConfig,
        artifacts: list[EmittedArtifact],
        emit_pyc: bool | None = None,
    ) -> None:
        target_emit_pyc = config.emit_pyc if emit_pyc is None else emit_pyc
        inputs: dict[str, FileCacheEntry] = {}

        for f in config.all_input_files():
            try:
                rel = str(f.relative_to(config.root_dir))
            except ValueError:
                rel = str(f)
            stat = f.stat()
            sha = compute_file_sha256(f)
            inputs[rel] = FileCacheEntry(sha256=sha, mtime=stat.st_mtime, size=stat.st_size)

        outputs: list[str] = []
        for art in artifacts:
            try:
                rel_py = str(art.py_path.relative_to(config.out_dir))
                outputs.append(rel_py)
            except ValueError:
                outputs.append(art.py_path.name)
            if art.pyc_path is not None:
                try:
                    rel_pyc = str(art.pyc_path.relative_to(config.out_dir))
                    outputs.append(rel_pyc)
                except ValueError:
                    outputs.append(art.pyc_path.name)

        cache = BuildCache(
            version=__version__,
            emit_pyc=target_emit_pyc,
            target_python=config.target_python,
            inputs=inputs,
            outputs=outputs,
        )

        cache_path = self._cache_path(config)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache.to_dict(), indent=2), encoding="utf-8")

    def clear_cache(self, config: PsProjectConfig) -> None:
        cache_path = self._cache_path(config)
        if cache_path.is_file():
            cache_path.unlink()
