#!/usr/bin/env python3
"""
Test runner for Ported 11_micro_croniter (croniter in PythonSharp).
Builds the project with `psc` and validates cron parsing, validity, schedules, day-of-week, and leap year rollover.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroCroniter via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported Croniter Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_croniter import CronCalendar, CronDateTime, CronIterator
    except ImportError as e:
        print(f"Failed to import micro_croniter: {e}", file=sys.stderr)
        return 1

    # 1. Validation Checks
    assert CronIterator.is_valid("* * * * *") is True
    assert CronIterator.is_valid("*/15 0-23 1,15 * 1-5") is True
    assert CronIterator.is_valid("0 8 * * *") is True
    assert CronIterator.is_valid("0 0 1 1 *") is True
    assert CronIterator.is_valid("* * * *") is False
    assert CronIterator.is_valid("invalid cron string") is False
    print("[PASS] CronIterator.is_valid verified across valid and malformed expressions")

    # 2. Every minute rule (* * * * *)
    start = CronDateTime(2026, 5, 10, 14, 30)
    it = CronIterator("* * * * *", start)
    nxt = it.get_next()
    assert nxt.to_iso_string() == "2026-05-10 14:31"
    print(f"[PASS] Every minute schedule: {start.to_iso_string()} -> {nxt.to_iso_string()}")

    # 3. Step intervals (*/15 * * * *)
    start = CronDateTime(2026, 5, 10, 14, 31)
    it = CronIterator("*/15 * * * *", start)
    nxt = it.get_next()
    assert nxt.to_iso_string() == "2026-05-10 14:45"
    nxt2 = it.get_next()
    assert nxt2.to_iso_string() == "2026-05-10 15:00"
    print(f"[PASS] Step interval schedule: {start.to_iso_string()} -> {nxt.to_iso_string()} -> {nxt2.to_iso_string()}")

    # 4. Daily Schedule with hour rollover (30 8 * * *)
    # Start on 2026-05-10 at 09:00, next should be 2026-05-11 at 08:30
    start = CronDateTime(2026, 5, 10, 9, 0)
    it = CronIterator("30 8 * * *", start)
    nxt = it.get_next()
    assert nxt.to_iso_string() == "2026-05-11 08:30"
    print(f"[PASS] Daily 08:30 schedule: {start.to_iso_string()} -> {nxt.to_iso_string()}")

    # 5. Weekday Schedule (0 9 * * 1-5: Mon-Fri 09:00)
    # 2026-05-15 is a Friday. Start at 10:00 (after 9 AM).
    # Next should skip Saturday (16th) and Sunday (17th) to land on Monday 2026-05-18 09:00!
    assert CronCalendar.get_day_of_week(2026, 5, 15) == 5  # Friday
    assert CronCalendar.get_day_of_week(2026, 5, 18) == 1  # Monday
    start_fri = CronDateTime(2026, 5, 15, 10, 0)
    it = CronIterator("0 9 * * 1-5", start_fri)
    nxt_mon = it.get_next()
    assert nxt_mon.to_iso_string() == "2026-05-18 09:00", f"Unexpected weekday next: {nxt_mon.to_iso_string()}"
    print(f"[PASS] Weekday schedule weekend skip: {start_fri.to_iso_string()} (Fri) -> {nxt_mon.to_iso_string()} (Mon)")

    # 6. Leap Day Rollover (0 0 29 2 *)
    # Start on 2026-01-01. 2026 and 2027 are not leap years; 2028 is a leap year!
    # Next should land directly on 2028-02-29 00:00
    start = CronDateTime(2026, 1, 1, 0, 0)
    it = CronIterator("0 0 29 2 *", start)
    nxt_leap = it.get_next()
    assert nxt_leap.to_iso_string() == "2028-02-29 00:00", f"Unexpected leap year next: {nxt_leap.to_iso_string()}"
    assert CronCalendar.is_leap_year(2028) is True
    assert CronCalendar.is_leap_year(2026) is False
    print(f"[PASS] Leap year rollover: {start.to_iso_string()} -> {nxt_leap.to_iso_string()}")

    print("\nAll micro-croniter verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

