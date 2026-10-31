#!/usr/bin/env python3
"""
Test runner for Ported 17_micro_eventloop (tiny cooperative async event loop in PythonSharp).
Builds the project with `psc` and validates coroutine execution, cooperative multitasking,
sleep deadline queues, concurrent interleaved tasks, and exception propagation.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroEventLoop via `psc build` ===")
    psc_bin = shutil.which("psc")
    if psc_bin:
        cmd = [psc_bin, "build", str(proj_dir), "-o", str(dist_dir)]
    else:
        cmd = [sys.executable, "-m", "psc.cli", "build", str(proj_dir), "-o", str(dist_dir)]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Build failed:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
        return 1
    print(res.stdout.strip())

    print("\n=== Step 2: Testing Ported EventLoop Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_async import EventLoop
    except ImportError as e:
        print(f"Failed to import micro_event_loop: {e}", file=sys.stderr)
        return 1

    loop = EventLoop()

    # 1. Simple generator coroutine returning value
    def simple_coro():
        yield None
        yield None
        return "Async computation finished"

    t1 = loop.create_task(simple_coro())
    res1 = loop.run_until_complete(t1)
    assert res1 == "Async computation finished"
    assert t1.status == "COMPLETED"
    print(f"[PASS] Simple coroutine execution verified: {res1}")

    # 2. Concurrent Cooperative Tasks with Sleep Schedule
    # Task A sleeps for 0.04s. Task B sleeps for 0.01s.
    # Task B MUST wake up and finish BEFORE Task A finishes!
    execution_timeline: list[str] = []

    def task_a():
        execution_timeline.append("A_start")
        yield 0.04  # Cooperative sleep for 40ms
        execution_timeline.append("A_end")
        return "A_finished"

    def task_b():
        execution_timeline.append("B_start")
        yield 0.01  # Cooperative sleep for 10ms
        execution_timeline.append("B_end")
        return "B_finished"

    loop2 = EventLoop()

    def main_orchestrator():
        # Spawn child task B into the active loop
        loop2.create_task(task_b())
        # Run task A directly to completion
        val_a = yield from task_a()
        return val_a

    main_task = loop2.create_task(main_orchestrator())
    start_t = time.time()
    res_a = loop2.run_until_complete(main_task)
    elapsed = time.time() - start_t

    assert res_a == "A_finished"
    # Task B should have started, finished, and logged B_end before A_end!
    assert execution_timeline == ["A_start", "B_start", "B_end", "A_end"], f"Unexpected timeline: {execution_timeline}"
    assert elapsed >= 0.035, f"Elapsed time too fast: {elapsed}"
    print(f"[PASS] Cooperative interleaved multitasking verified: {execution_timeline} in {elapsed:.3f}s")

    # 3. Exception Propagation
    def failing_coroutine():
        yield 0.005
        raise ZeroDivisionError("Cooperative task division error")

    loop3 = EventLoop()
    fail_task = loop3.create_task(failing_coroutine())

    try:
        loop3.run_until_complete(fail_task)
        assert False, "Should have propagated ZeroDivisionError from coroutine"
    except ZeroDivisionError as exc:
        assert "Cooperative task division error" in str(exc)
        assert fail_task.status == "FAILED"
        print(f"[PASS] Exception correctly propagated from async task: {exc}")

    print("\nAll micro-eventloop verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
