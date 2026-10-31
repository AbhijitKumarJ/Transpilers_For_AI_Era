#!/usr/bin/env python3
"""
Test runner for Ported 10_micro_bitarray (bitarray in PythonSharp).
Builds the project with `psc` and validates bit packing, bitwise ops, hex, shifts, and searches.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    proj_dir = Path(__file__).resolve().parent
    dist_dir = proj_dir / "dist"

    print("=== Step 1: Building MicroBitArray via `psc build` ===")
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

    print("\n=== Step 2: Testing Ported BitArray Functionality ===")
    sys.path.insert(0, str(dist_dir))

    try:
        from micro_bit_array import BitArray
    except ImportError as e:
        print(f"Failed to import micro_bit_array: {e}", file=sys.stderr)
        return 1

    # 1. Initialization and Bit Access
    ba = BitArray(10, False)
    assert ba.length == 10
    assert ba.byte_count == 2
    assert ba.count(True) == 0
    assert ba.to_01() == "0000000000"

    ba.set(0, True)
    ba.set(9, True)
    assert ba.get(0) is True
    assert ba.get(9) is True
    assert ba.get(1) is False
    assert ba.to_01() == "1000000001"
    assert ba.count(True) == 2
    print("[PASS] Initialization, length, byte packing, and get/set verified")

    # 2. Binary String Creation and Roundtrip
    str_sample = "1011001101"
    ba_str = BitArray.from_string(str_sample)
    assert ba_str.length == len(str_sample)
    assert ba_str.to_01() == str_sample
    print("[PASS] BitArray.from_string and to_01 verified")

    # 3. Hexadecimal Conversions
    ba_hex = BitArray.from_hex("A5")  # 0xA5 = 10100101
    assert ba_hex.length == 8
    assert ba_hex.to_01() == "10100101"
    assert ba_hex.to_hex() == "A5"
    print("[PASS] Hex conversions (A5 -> 10100101 -> A5) verified")

    # 4. Bitwise AND, OR, XOR, NOT
    a = BitArray.from_string("11001010")
    b = BitArray.from_string("10101100")

    and_res = a.and_(b)
    assert and_res.to_01() == "10001000", f"Unexpected AND: {and_res.to_01()}"

    or_res = a.or_(b)
    assert or_res.to_01() == "11101110", f"Unexpected OR: {or_res.to_01()}"

    xor_res = a.xor(b)
    assert xor_res.to_01() == "01100110", f"Unexpected XOR: {xor_res.to_01()}"

    not_res = a.not_()
    assert not_res.to_01() == "00110101", f"Unexpected NOT: {not_res.to_01()}"
    print("[PASS] Bitwise operations (AND, OR, XOR, NOT) verified")

    # 5. Logical Shifts
    c = BitArray.from_string("11010010")
    shl = c.shift_left(2)
    assert shl.to_01() == "01001000", f"Unexpected shift_left: {shl.to_01()}"

    shr = c.shift_right(3)
    assert shr.to_01() == "00011010", f"Unexpected shift_right: {shr.to_01()}"
    print("[PASS] Bitwise shift_left and shift_right verified")

    # 6. Searching & Predicates
    d = BitArray.from_string("00010010")
    assert d.find(True) == 3
    assert d.find(True, start=4) == 6
    assert d.find(True, start=7) == -1
    assert d.any() is True
    assert d.all() is False

    ones = BitArray.from_string("1111")
    assert ones.all() is True
    print("[PASS] Searching (find, any, all, popcount) verified")

    print("\nAll micro-bitarray verification checks succeeded with 0 errors!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

