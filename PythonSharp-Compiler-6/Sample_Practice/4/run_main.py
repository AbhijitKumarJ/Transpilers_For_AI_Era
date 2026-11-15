#!/usr/bin/env python3
"""Verification harness for ported 01_leftpad library."""

import sys
from pathlib import Path

def main(args) -> int:

    proj_dir = Path(__file__).parent.resolve()
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))
    
    from ps_2 import ProjMain

    ProjMain.main(args)
    return 0


if __name__ == "__main__":
    sys.exit(main(args=sys.argv[1:]))
