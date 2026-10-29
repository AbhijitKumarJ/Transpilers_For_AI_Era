from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from psc.build_cache import compute_file_sha256
from psc.codegen import ArtifactEmitter
from psc.project import PsProjectConfig


@dataclass(slots=True)
class WatchResult:
    iterations: int
    builds_triggered: int
    last_error: str | None = None


class ProjectWatcher:
    """Monitors PythonSharp project files for changes and triggers incremental rebuilds."""

    def __init__(
        self,
        config: PsProjectConfig,
        on_build: Callable[[PsProjectConfig], tuple[bool, str]] | None = None,
        poll_interval_sec: float = 0.5,
    ) -> None:
        self.config = config
        self.on_build = on_build or self._default_build
        self.poll_interval_sec = poll_interval_sec
        self._file_hashes: dict[Path, str] = {}

    def _snapshot_hashes(self) -> dict[Path, str]:
        hashes: dict[Path, str] = {}
        for f in self.config.all_input_files():
            if f.is_file():
                try:
                    hashes[f] = compute_file_sha256(f)
                except Exception:
                    pass
        return hashes

    def _default_build(self, config: PsProjectConfig) -> tuple[bool, str]:
        from psc.cli import parse_and_analyze_config

        units, symtab, diag = parse_and_analyze_config(config)
        if diag.has_errors():
            return False, diag.format_all()
        emitter = ArtifactEmitter(symtab)
        artifacts = emitter.emit_all(config.out_dir, emit_pyc=config.emit_pyc)
        return True, f"Emitted {len(artifacts)} module(s)"

    def watch(
        self,
        max_iterations: int | None = None,
        stop_condition: Callable[[], bool] | None = None,
    ) -> WatchResult:
        """
        Runs the watch loop. If `max_iterations` is set, terminates after that many
        polling iterations (useful for testing). If `stop_condition` returns True, stops.
        """
        self._file_hashes = self._snapshot_hashes()
        builds_triggered = 0
        iterations = 0
        last_error: str | None = None

        # Initial build
        success, msg = self.on_build(self.config)
        builds_triggered += 1
        if not success:
            last_error = msg

        while True:
            if max_iterations is not None and iterations >= max_iterations:
                break
            if stop_condition is not None and stop_condition():
                break

            time.sleep(self.poll_interval_sec)
            iterations += 1

            current_hashes = self._snapshot_hashes()
            changed = current_hashes != self._file_hashes

            if changed:
                self._file_hashes = current_hashes
                builds_triggered += 1
                success, msg = self.on_build(self.config)
                if not success:
                    last_error = msg
                else:
                    last_error = None

        return WatchResult(
            iterations=iterations,
            builds_triggered=builds_triggered,
            last_error=last_error,
        )
