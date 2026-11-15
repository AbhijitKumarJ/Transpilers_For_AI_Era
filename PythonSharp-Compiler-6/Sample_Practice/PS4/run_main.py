#!/usr/bin/env python3
"""Starter entrypoint runner for PS4."""

import sys
from pathlib import Path


def main(args: list[str]) -> int:
    proj_dir = Path(__file__).parent.resolve()
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    from ps_4 import ProjMain

    ProjMain.main(args)
    return 0


if __name__ == "__main__":
    sys.exit(main(args=sys.argv[1:]))
