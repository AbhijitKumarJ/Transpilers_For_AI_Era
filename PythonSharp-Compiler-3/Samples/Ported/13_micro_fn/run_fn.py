#!/usr/bin/env python3
"""
Test runner for Ported 13_micro_fn (fn.py functional toolkit in PythonSharp).
Builds the project with `psc` and validates currying, partial application, composition,
pipelines, take_while, drop_while, partition, and flatten.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroFn via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported Fn Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_fn import Fn, PartitionResult
    except ImportError as e:
        print(f"Failed to import micro_fn: {e}", file=sys.stderr)
        return 1

    # 1. Currying (Curry2 and Curry3)
    def add(a: int, b: int) -> int:
        return a + b

    curried_add = Fn.curry_2(add)
    assert curried_add(10)(25) == 35

    def volume(length: int, width: int, height: int) -> int:
        return length * width * height

    curried_vol = Fn.curry_3(volume)
    assert curried_vol(2)(3)(4) == 24
    print("[PASS] Currying (curry_2 and curry_3) verified")

    # 2. Partial application
    def multiply(a: int, b: int) -> int:
        return a * b

    double = Fn.partial(multiply, 2)
    assert double(7) == 14
    assert double(21) == 42
    print("[PASS] Partial application verified")

    # 3. Function composition (Compose)
    # f(g(x)) where g doubles and f adds 1
    def f(x: int) -> int:
        return x + 1

    def g(x: int) -> int:
        return x * 2

    f_after_g = Fn.compose(f, g)
    assert f_after_g(5) == 11  # (5 * 2) + 1
    assert f_after_g(10) == 21
    print("[PASS] Function composition (f ∘ g) verified")

    # 4. Pipeline forwarding (Pipe)
    pipeline = [
        lambda x: x * 2,         # 5 * 2 = 10
        lambda x: x + 15,        # 10 + 15 = 25
        lambda x: f"Value: {x}"  # "Value: 25"
    ]
    piped_result = Fn.pipe(5, pipeline)
    assert piped_result == "Value: 25"
    print("[PASS] Pipeline forwarding verified")

    # 5. TakeWhile & DropWhile
    seq = [1, 2, 3, 4, 10, 20, 1]
    taken = Fn.take_while(lambda x: x < 5, seq)
    assert taken == [1, 2, 3, 4]

    dropped = Fn.drop_while(lambda x: x < 5, seq)
    assert dropped == [10, 20, 1]
    print("[PASS] TakeWhile and DropWhile verified")

    # 6. Partition
    numbers = [1, 2, 3, 4, 5, 6, 7, 8]
    part_res = Fn.partition(lambda x: x % 2 == 0, numbers)
    assert isinstance(part_res, PartitionResult)
    assert part_res.matches == [2, 4, 6, 8]
    assert part_res.rest == [1, 3, 5, 7]
    print("[PASS] Partition record (matches, rest) verified")

    # 7. Arbitrary nested Flatten
    nested = [1, [2, [3, 4]], 5, [6, 7], 8]
    flat = Fn.flatten(nested)
    assert flat == [1, 2, 3, 4, 5, 6, 7, 8]
    print("[PASS] Recursive Flatten verified")

    # 8. Map, Filter, Reduce
    mapped = Fn.map(lambda x: x * 3, [1, 2, 3])
    assert mapped == [3, 6, 9]

    filtered = Fn.filter(lambda x: x > 5, [2, 4, 6, 8, 10])
    assert filtered == [6, 8, 10]

    summed = Fn.reduce(lambda acc, x: acc + x, [1, 2, 3, 4, 5], 0)
    assert summed == 15
    print("[PASS] Functional primitives (Map, Filter, Reduce) verified")

    print("\nAll micro-fn verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
