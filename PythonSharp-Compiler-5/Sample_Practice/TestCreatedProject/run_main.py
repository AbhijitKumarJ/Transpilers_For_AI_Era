#!/usr/bin/env python3
"""Starter entrypoint runner for TestCreatedProject."""

import sys
from pathlib import Path


def main(args: list[str]) -> int:
    proj_dir = Path(__file__).parent.resolve()
    dist_dir = proj_dir / "dist"
    sys.path.insert(0, str(dist_dir))

    from test_created_project import ProjMain

    ProjMain.main(args)
    return 0


if __name__ == "__main__":
    sys.exit(main(args=sys.argv[1:]))
