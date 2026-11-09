#!/usr/bin/env python3
"""
Test runner for Ported 06_micro_tqdm (Micro TQDM CLI Progress Bar in PythonSharp).
Builds the project with `psc` and validates ProgressBar rendering, time formatting, and updates.
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

    print("=== Step 1: Building MicroTqdm via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported ProgressBar Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_tqdm_util import ProgressBar
    except ImportError as e:
        print(f"Failed to import micro_tqdm_util: {e}", file=sys.stderr)
        return 1

    # 1. FormatTime test
    assert ProgressBar.format_time(0.0) == "00:00"
    assert ProgressBar.format_time(59.0) == "00:59"
    assert ProgressBar.format_time(65.0) == "01:05"
    assert ProgressBar.format_time(3605.0) == "60:05"
    print("[PASS] ProgressBar.format_time correctly formats MM:SS")

    # 2. FormatRate test
    assert ProgressBar.format_rate(0.0) == "0.00 it/s"
    assert ProgressBar.format_rate(12.34) == "12.34 it/s"
    assert ProgressBar.format_rate(100.0) == "100.00 it/s"
    print("[PASS] ProgressBar.format_rate correctly formats iteration speed")

    # 3. Structural bar rendering at 0%, 50%, 100%
    bar = ProgressBar(100, desc="Testing", bar_width=20)
    assert bar.current == 0
    assert bar.total == 100
    assert bar.description == "Testing"

    str_0 = bar.render_string()
    assert "Testing: [" in str_0
    assert "0%" in str_0
    assert "(0/100)" in str_0
    print(f"[PASS] 0% Render: {str_0}")

    bar.update(50)
    assert bar.current == 50
    str_50 = bar.render_string()
    assert "50%" in str_50
    assert "(50/100)" in str_50
    assert "=" in str_50
    print(f"[PASS] 50% Render: {str_50}")

    bar.update(50)
    assert bar.current == 100
    str_100 = bar.render_string()
    assert "100%" in str_100
    assert "(100/100)" in str_100
    print(f"[PASS] 100% Render: {str_100}")

    # 4. Interactive Simulation (live terminal updates)
    print("\nSimulating live progress bar:")
    sim_bar = ProgressBar(20, desc="Processing Items", bar_width=25)
    for _ in range(20):
        time.sleep(0.02)
        sim_bar.update(1)

    print("All micro_tqdm verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
