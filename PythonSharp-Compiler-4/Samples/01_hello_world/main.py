"""Sample 01: Interacting with PythonSharp compiled code from standard Python."""

import sys
from pathlib import Path

# Add output directory to python path
out_dir = Path(__file__).parent / "dist"
sys.path.insert(0, str(out_dir))

from hello_app import Program  # noqa: E402

if __name__ == "__main__":
    print("--- Calling PythonSharp from Python ---")
    greeting = Program.create_greeting("Pythonista")
    print("Result:", greeting)

    total = Program.add(10, 25)
    print("10 + 25 =", total)
