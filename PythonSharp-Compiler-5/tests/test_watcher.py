from __future__ import annotations

from pathlib import Path

from psc.project import PsProjectConfig
from psc.watcher import ProjectWatcher


def test_watcher_detects_changes(tmp_path: Path) -> None:
    src_file = tmp_path / "App.ps"
    src_file.write_text("namespace Demo; public class Greeter { public string Hello() => \"v1\"; }", encoding="utf-8")
    out_dir = tmp_path / "dist"

    config = PsProjectConfig(
        project_name="Demo",
        root_dir=tmp_path,
        out_dir=out_dir,
        source_files=[src_file],
        emit_pyc=False,
    )

    build_log: list[str] = []

    def mock_build(cfg: PsProjectConfig) -> tuple[bool, str]:
        code = src_file.read_text(encoding="utf-8")
        build_log.append(code)
        return True, "OK"

    watcher = ProjectWatcher(config, on_build=mock_build, poll_interval_sec=0.05)

    # Trigger a change after iteration 1
    call_count = 0

    def should_stop() -> bool:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            src_file.write_text("namespace Demo; public class Greeter { public string Hello() => \"v2\"; }", encoding="utf-8")
        return call_count > 4

    result = watcher.watch(max_iterations=10, stop_condition=should_stop)

    assert result.builds_triggered >= 2
    assert len(build_log) >= 2
    assert "v1" in build_log[0]
    assert "v2" in build_log[1]

