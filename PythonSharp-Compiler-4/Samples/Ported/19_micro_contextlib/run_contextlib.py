#!/usr/bin/env python3
"""
Test runner for Ported 19_micro_contextlib (Python-contextlib resource lifecycle & ExitStack in PythonSharp).
Builds the project with `psc` and validates LIFO stack unwinding, exception handling, and context manager interop.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroContextLib via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported MicroContextLib Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_context_lib import ContextPipeline, ManagedResource, MicroExitStack
    except ImportError as e:
        print(f"Failed to import micro_context_lib: {e}", file=sys.stderr)
        return 1

    # 1. Successful Workflow LIFO Unwinding
    trace = ContextPipeline.run_successful_workflow()
    print("Trace events:", trace)

    assert trace[0] == "acquire:DatabaseConnection"
    assert trace[1] == "acquire:TransactionScope"
    assert trace[2] == "acquire:AuditLogFile"
    assert trace[3] == "execute:business_logic"
    # Guaranteed LIFO reverse disposal order:
    assert trace[4] == "release:AuditLogFile"
    assert trace[5] == "release:TransactionScope"
    assert trace[6] == "release:DatabaseConnection"
    print("[PASS] Successful workflow executed with exact LIFO reverse cleanup order")

    # 2. Failing Workflow Exception Handling & Guaranteed Unwind
    fail_trace = ContextPipeline.run_failing_workflow()
    print("Failing trace events:", fail_trace)

    assert "acquire:DatabaseConnection" in fail_trace
    assert "acquire:TransactionScope" in fail_trace
    assert "acquire:AuditLogFile" in fail_trace
    assert "execute:failing_operation" in fail_trace
    assert "caught:Simulation failure during processing" in fail_trace
    # All 3 resources released in LIFO reverse order despite the exception:
    assert fail_trace[5] == "release:AuditLogFile"
    assert fail_trace[6] == "release:TransactionScope"
    assert fail_trace[7] == "release:DatabaseConnection"
    assert fail_trace[8] == "cleanup:guaranteed_complete"
    print("[PASS] Failing workflow cleanly caught exception and unwound all resources in LIFO order")

    # 3. Python Native Context Manager (`with` statement) Interop
    log: list[str] = []
    with ManagedResource("ScopedLock", log) as lock:
        assert not lock.is_disposed
        assert lock.name == "ScopedLock"
        assert log == ["acquire:ScopedLock"]

    assert lock.is_disposed
    assert log == ["acquire:ScopedLock", "release:ScopedLock"]
    print("[PASS] Python `with` statement integration verified via synthesized __enter__/__exit__")

    # 4. Standalone MicroExitStack Manual Push & Unwind
    manual_log: list[str] = []
    stack = MicroExitStack()
    r1 = ManagedResource("Res1", manual_log)
    r2 = ManagedResource("Res2", manual_log)
    stack.push(r1)
    stack.push(r2)
    assert stack.count == 2
    assert not stack.is_closed

    stack.close()
    assert stack.count == 0
    assert stack.is_closed
    assert r1.is_disposed
    assert r2.is_disposed
    assert manual_log == [
        "acquire:Res1",
        "acquire:Res2",
        "release:Res2",
        "release:Res1",
    ]
    assert stack.cleanup_order == ["ok", "ok"]
    print("[PASS] Manual MicroExitStack push and close verified")

    print("\nAll 19_micro_contextlib verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

