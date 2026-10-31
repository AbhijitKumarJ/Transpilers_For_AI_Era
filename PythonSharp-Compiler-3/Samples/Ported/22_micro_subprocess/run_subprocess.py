#!/usr/bin/env python3
"""
Test runner for Ported 22_micro_subprocess (OS process spawning and IPC in PythonSharp).
Builds the project with `psc` and validates process execution, exit codes, stdin piping, and output parsing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroSubprocess via `psc build` ===")
    psc_bin = shutil.which("psc")
    if psc_bin:
        cmd = [psc_bin, "build", str(proj_dir)]
    else:
        cmd = [sys.executable, "-m", "psc.cli", "build", str(proj_dir)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Build failed:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
        return 1
    print(res.stdout.strip())

    print("\n=== Step 2: Testing Ported MicroSubprocess Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_subprocess import ProcessEngine, ProcessOutput
    except ImportError as e:
        print(f"Failed to import micro_subprocess: {e}", file=sys.stderr)
        return 1

    # 1. Basic command execution & record verification
    py_exec = sys.executable
    out1 = ProcessEngine.execute([py_exec, "-c", "print('Hello from Subprocess Engine!')"])
    assert isinstance(out1, ProcessOutput)
    assert out1.exit_code == 0
    assert out1.succeeded
    assert out1.standard_output == "Hello from Subprocess Engine!\n"
    print(f"[PASS] Execute command: exit_code={out1.exit_code}, succeeded={out1.succeeded}")

    # 2. Command with failure exit code
    out2 = ProcessEngine.execute([py_exec, "-c", "import sys; sys.stderr.write('Fatal boom\\n'); sys.exit(7)"])
    assert out2.exit_code == 7
    assert not out2.succeeded
    assert "Fatal boom" in out2.standard_error
    print(f"[PASS] Execute with non-zero exit code: code={out2.exit_code}, error_captured=True")

    # 3. Piping standard input (stdin)
    pipe_script = "import sys; print(f'PIPED:{sys.stdin.read().strip().upper()}')"
    out3 = ProcessEngine.execute_with_stdin([py_exec, "-c", pipe_script], "pythonsharp stream payload")
    assert out3.succeeded
    assert "PIPED:PYTHONSHARP STREAM PAYLOAD" in out3.standard_output
    print(f"[PASS] Execute with stdin piping verified: output={out3.standard_output.strip()}")

    # 4. Captured trimmed stdout
    stdout_text = ProcessEngine.execute_and_capture_stdout([py_exec, "-c", "print('  1337  ')"])
    assert stdout_text == "1337"
    print(f"[PASS] ExecuteAndCaptureStdout: '{stdout_text}'")

    # 5. CheckSuccess boolean guard
    ok = ProcessEngine.check_success([py_exec, "-c", "import sys; sys.exit(0)"])
    bad = ProcessEngine.check_success([py_exec, "-c", "import sys; sys.exit(2)"])
    assert ok is True
    assert bad is False
    print("[PASS] CheckSuccess boolean guard verified")

    # 6. ParseLines multiline utility
    multiline = "alpha\n\nbeta\n   \ngamma\n"
    lines = ProcessEngine.parse_lines(multiline)
    assert lines == ["alpha", "beta", "gamma"]
    print(f"[PASS] ParseLines parsed {len(lines)} non-empty lines: {lines}")

    print("\nAll 22_micro_subprocess verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

