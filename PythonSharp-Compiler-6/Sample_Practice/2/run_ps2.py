#!/usr/bin/env python3
"""Verification harness for ported 01_leftpad library."""

import sys
from pathlib import Path

def main(args) -> int:

    proj_dir = Path(__file__).parent.resolve()
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))
    
    from ps_2 import PadUtil, TestUtil

    # Test 1: Standard left-pad
    res1 = PadUtil.left_pad("hello", 10)
    assert res1 == "     hello", f"Expected '     hello', got {repr(res1)}"
    print(f"[PASS] PadUtil.left_pad('hello', 10) -> {repr(res1)}")


    PadUtil.repeat("xyz", 8)  # Example usage of repeat function

    TestUtil.pat("")
    return 0


if __name__ == "__main__":
    sys.exit(main(args=sys.argv[1:]))
