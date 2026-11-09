#!/usr/bin/env python3
"""Verification harness for ported 01_leftpad library."""

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).parent.resolve()
    print("=== Step 1: Building LeftPad via `psc build` ===")
    cmd = ["psc", "build", str(proj_dir)] if shutil.which("psc") else [sys.executable, "-m", "psc.cli", "build", str(proj_dir)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout.strip())
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        return res.returncode

    print("\n=== Step 2: Testing Ported PadUtil Functionality ===")
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    from text_util import PadUtil

    # Test 1: Standard left-pad
    res1 = PadUtil.left_pad("hello", 10)
    assert res1 == "     hello", f"Expected '     hello', got {repr(res1)}"
    print(f"[PASS] PadUtil.left_pad('hello', 10) -> {repr(res1)}")

    # Test 2: Custom pad character
    res2 = PadUtil.left_pad("42", 5, "0")
    assert res2 == "00042", f"Expected '00042', got {repr(res2)}"
    print(f"[PASS] PadUtil.left_pad('42', 5, '0') -> {repr(res2)}")

    # Test 3: String already longer than length
    res3 = PadUtil.left_pad("supercalifragilistic", 10)
    assert res3 == "supercalifragilistic", f"Expected unchanged, got {repr(res3)}"
    print(f"[PASS] PadUtil.left_pad('supercalifragilistic', 10) -> {repr(res3)}")

    # Test 4: Right-pad
    res4 = PadUtil.right_pad("item", 10, ".")
    assert res4 == "item......", f"Expected 'item......', got {repr(res4)}"
    print(f"[PASS] PadUtil.right_pad('item', 10, '.') -> {repr(res4)}")

    # Test 5: Center pad
    res5 = PadUtil.center("Title", 15, "=")
    assert res5 == "=====Title=====", f"Expected '=====Title=====', got {repr(res5)}"
    print(f"[PASS] PadUtil.center('Title', 15, '=') -> {repr(res5)}")

    print("\nAll leftpad verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
