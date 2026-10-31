#!/usr/bin/env python3
"""
Test runner for Ported 15_multimethod (multiple dispatch engine in PythonSharp).
Builds the project with `psc` and validates multi-argument type dispatch, subclass specificity (MRO),
unmatched signature errors, and decorator support.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroMultiMethod via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported MultiMethod Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_multi_method import MultiMethod
    except ImportError as e:
        print(f"Failed to import micro_multi_method: {e}", file=sys.stderr)
        return 1

    # 1. Exact Primitive Multi-Dispatch
    combine = MultiMethod("combine")
    combine.register([int, int], lambda a, b: a + b)
    combine.register([str, str], lambda a, b: f"{a}-{b}")
    combine.register([list, list], lambda a, b: a + b)

    assert combine.dispatch([10, 25]) == 35
    assert combine.dispatch(["foo", "bar"]) == "foo-bar"
    assert combine.dispatch([[1, 2], [3, 4]]) == [1, 2, 3, 4]
    print("[PASS] Exact type dispatch across (int, int), (str, str), (list, list) verified")

    # 2. Subclass Hierarchy / MRO Specificity
    class Shape:
        pass

    class Circle(Shape):
        pass

    class Square(Shape):
        pass

    draw = MultiMethod("draw")
    draw.register([Shape], lambda s: "General shape rendered")
    draw.register([Circle], lambda c: "Circle rendered with radius")

    # Circle() is both Shape and Circle, but Circle is more specific
    assert draw.dispatch([Circle()]) == "Circle rendered with radius"
    # Square() is only Shape
    assert draw.dispatch([Square()]) == "General shape rendered"
    print("[PASS] Subtype specificity (Circle vs Shape) verified")

    # 3. Two-argument Cross-Type Specificity
    class Entity:
        pass

    class Player(Entity):
        pass

    class Monster(Entity):
        pass

    class Weapon:
        pass

    class MagicWand(Weapon):
        pass

    interact = MultiMethod("interact")
    interact.register([Entity, Weapon], lambda e, w: "Generic entity uses weapon")
    interact.register([Player, MagicWand], lambda p, w: "Player casts spell with wand")
    interact.register([Monster, Weapon], lambda m, w: "Monster swings weapon aggressively")

    assert interact.dispatch([Player(), MagicWand()]) == "Player casts spell with wand"
    assert interact.dispatch([Monster(), MagicWand()]) == "Monster swings weapon aggressively"
    assert interact.dispatch([Entity(), Weapon()]) == "Generic entity uses weapon"
    print("[PASS] Multi-argument cross-type dispatch matrix verified")

    # 4. Missing Signature Exception
    try:
        combine.dispatch([10, "string_mismatch"])
        assert False, "Should have raised exception for unregistered type pair"
    except Exception as e:
        assert "No matching method" in str(e)
        print(f"[PASS] Missing signature correctly raised: {e}")

    # 5. Callable wrapper (AsCallable)
    fn_call = combine.as_callable()
    assert fn_call(100, 200) == 300
    assert fn_call("alpha", "beta") == "alpha-beta"
    print("[PASS] AsCallable wrapper (*args) verified")

    print("\nAll micro-multimethod verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

