# Ported: `10_micro_bitarray`

A dynamic bitset backed by packed byte arrays and native bitwise operators, ported to **PythonSharp** (`.ps`), compiling to clean Python 3.11+.

Ported from concepts in the Python `bitarray` library.

---

## Features

- **Buffer Packing**: Efficiently stores 8 bits per byte array slot with automatic trailing bit masking.
- **Index Access**: `Get(index)` and `Set(index, bool)` with bounds checking.
- **Dynamic Growth**: `Append(bool)` for building bit vectors on the fly.
- **Native Bitwise Operations**:
  - `And(other)`: Bitwise AND (`&`)
  - `Or(other)`: Bitwise OR (`|`)
  - `Xor(other)`: Bitwise XOR (`^`)
  - `Not()` / `Invert()`: Bitwise NOT (`~`)
  - `ShiftLeft(count)` / `ShiftRight(count)`: Logical bit shifts (`<<`, `>>`)
- **Conversions & Formatting**:
  - `FromString(string)` / `To01()`: Binary string representation (`"1011001"`)
  - `FromHex(string)` / `ToHex()`: Hexadecimal string representation (`"A5"`)
  - `ToBytes()`: Raw byte list export
- **Metrics & Search**:
  - `Count(bool)`: Population count (popcount)
  - `Find(bool, start)`: Linear search for first bit match
  - `Any()`, `All()`: Boolean aggregate predicates

---

## Build & Run

```bash
# 1. Compile the project
psc build Samples/Ported/10_micro_bitarray -o Samples/Ported/10_micro_bitarray/dist

# 2. Run the test harness
python3 Samples/Ported/10_micro_bitarray/run_bitarray.py
```

