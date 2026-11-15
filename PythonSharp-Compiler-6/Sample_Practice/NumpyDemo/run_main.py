import sys
from pathlib import Path

# Add dist to sys.path so emitted Python modules can be imported
dist_dir = Path(__file__).parent / "dist"
if str(dist_dir) not in sys.path:
    sys.path.insert(0, str(dist_dir))

from numpy_demo import ProjMain

def main(args=None):
    if args is None:
        args = sys.argv[1:]
    ProjMain.main(args)
    return 0

if __name__ == "__main__":
    sys.exit(main(args=sys.argv[1:]))
