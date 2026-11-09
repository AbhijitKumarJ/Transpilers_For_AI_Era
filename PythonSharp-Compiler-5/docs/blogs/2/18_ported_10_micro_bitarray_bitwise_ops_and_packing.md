# Level 2 — Blog 18: Ported 10 — Micro-BitArray (`10_micro_bitarray`): Bitwise Operations & Byte Packing

In [Blog 17](./17_ported_09_micro_toml_scanner_and_state_machines.md), we explored state machines and structured TOML parsing.

Now, we examine **`10_micro_bitarray`**, ported from concepts in the `bitarray` library.

This port is historically significant in PythonSharp: **it directly drove the evolution of the compiler itself**. To port `bitarray`, the compiler had to be enhanced with:
1. **Bitwise Operator Lexing & Precedence**: `&` (`BitAnd`), `|` (`BitOr`), `^` (`BitXor`), `~` (`Invert`), `<<` (`LShift`), and `>>` (`RShift`).
2. **Hexadecimal & Binary Integer Literals**: `0xFF`, `0x80`, `0b1010`.
3. **Byte Packing & Masking**: Dynamic indexing into byte buffers (`index / 8`, `7 - (index % 8)`).

In this post, we explore:
1. **The Target**: Compact bit arrays storing boolean flags at 1 bit per value (instead of Python's 8 bytes per bool).
2. **Compiler Evolution**: How the compiler was enhanced to support bitwise expressions.
3. **The C# Implementation (`BitArray.ps`)**: Byte masking, bit setting/getting, boolean logic gates (`&`, `|`, `^`, `~`), and hex encoding.
4. **The Transpiled Output (`micro_bit_array.py`)**: Direct lowering to Python bitwise bytecode.
5. **The Verification Test Harness (`run_bitarray.py`)**: Testing logic operations, bit counts, and hex serialization.

---

## 1. The Target: Why `bitarray`?

In Python, a standard `bool` is an object allocating **28 bytes** in memory (`sys.getsizeof(True) == 28`). Even a `list[bool]` of $1,000,000$ booleans consumes over 8 megabytes of RAM.

A **BitArray** packs 8 boolean flags into a single unsigned 8-bit byte. One million flags consume only **125 kilobytes**!

Key operations:
- **Indexing**: Read and write the $k$-th bit.
- **Bitwise Logic**: In-place and binary operations (`A & B`, `A | B`, `A ^ B`, `~A`).
- **Population Count**: Count the number of set bits (1s) efficiently.
- **Serialization**: Format bits as hexadecimal strings (`0xFA12...`).

---

## 2. Compiler Evolution: Adding Bitwise Operators to `psc`

When we first attempted to compile `BitArray.ps`, the compiler halted with:
```
ERROR [PS000]: Unexpected character '&'
```
Because PythonSharp was originally designed for high-level enterprise code, bitwise operators had not yet been wired through the frontend.

Porting `10_micro_bitarray` drove the following enhancements:
1. **Lexer Tokens** ([`src/psc/frontend/tokens.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/frontend/tokens.py)):
   - Added `AMP` (`&`), `PIPE` (`|`), `TILDE` (`~`), `LSHIFT` (`<<`), `RSHIFT` (`>>`).
2. **Numeric Literals** ([`src/psc/frontend/lexer.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/frontend/lexer.py)):
   - Added `0x...` (hexadecimal) and `0b...` (binary) scanning support.
3. **Parser Precedence** ([`src/psc/frontend/parser.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/frontend/parser.py)):
   - Wired operator precedence: `BitwiseOr` $\to$ `BitwiseXor` $\to$ `BitwiseAnd` $\to$ `Relational` $\to$ `Shift`.
4. **AST Codegen** ([`src/psc/codegen/expr_lowerer.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/src/psc/codegen/expr_lowerer.py)):
   - Mapped operators to Python's `ast.BitAnd()`, `ast.BitOr()`, `ast.BitXor()`, `ast.Invert()`, `ast.LShift()`, and `ast.RShift()`.

---

## 3. The C# Source Implementation: `BitArray.ps`

In [`BitArray.ps`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/10_micro_bitarray/BitArray.ps), notice the bitwise masking algorithms:

```csharp
namespace MicroBitArray;

using PythonSharp.Core;

public class BitArray
{
    private int _length;
    private List<int> _bytes;

    public BitArray(int length = 0, bool initial = false)
    {
        this._length = length;
        this._bytes = new List<int>();

        if (length > 0)
        {
            int numBytes = (length + 7) / 8;
            int fill = initial ? 0xFF : 0x00;
            int i = 0;
            while (i < numBytes)
            {
                this._bytes.Add(fill);
                i = i + 1;
            }
            if (initial && (length % 8 != 0))
            {
                this.MaskUnusedBits();
            }
        }
    }

    public bool Get(int index)
    {
        if (index < 0 || index >= this._length)
        {
            throw new IndexOutOfRangeException("Bit index out of range");
        }
        int byteIdx = index / 8;
        int bitOffset = 7 - (index % 8);
        return (this._bytes[byteIdx] & (1 << bitOffset)) != 0;
    }

    public void Set(int index, bool value)
    {
        if (index < 0 || index >= this._length)
        {
            throw new IndexOutOfRangeException("Bit index out of range");
        }
        int byteIdx = index / 8;
        int bitOffset = 7 - (index % 8);
        if (value)
        {
            this._bytes[byteIdx] = this._bytes[byteIdx] | (1 << bitOffset);
        }
        else
        {
            this._bytes[byteIdx] = this._bytes[byteIdx] & ~(1 << bitOffset);
        }
    }

    public BitArray BitwiseAnd(BitArray other)
    {
        int minLen = this._length < other.Length ? this._length : other.Length;
        BitArray result = new BitArray(minLen);
        int i = 0;
        while (i < result.ByteCount)
        {
            result._bytes[i] = this._bytes[i] & other._bytes[i];
            i = i + 1;
        }
        result.MaskUnusedBits();
        return result;
    }
}
```

---

## 4. The Transpiled Output: `micro_bit_array.py`

Compiling with:
```bash
psc build Samples/Ported/10_micro_bitarray -o Samples/Ported/10_micro_bitarray/dist
```
produces clean, direct Python bitwise bytecode:

```python
# Auto-generated by PythonSharp (psc) — Bytecode line-pinned to BitArray.ps
from __future__ import annotations

class BitArray:
    __ps_types__ = ('MicroBitArray.BitArray',)
    __slots__ = ('_length', '_bytes')

    def get(self, index: int) -> bool:
        if index < 0 or index >= self._length:
            raise IndexError('Bit index out of range')
        byte_idx: int = index // 8
        bit_offset: int = 7 - index % 8
        return (self._bytes[byte_idx] & 1 << bit_offset) != 0

    def set(self, index: int, value: bool) -> None:
        if index < 0 or index >= self._length:
            raise IndexError('Bit index out of range')
        byte_idx: int = index // 8
        bit_offset: int = 7 - index % 8
        if value:
            self._bytes[byte_idx] = self._bytes[byte_idx] | 1 << bit_offset
        else:
            self._bytes[byte_idx] = self._bytes[byte_idx] & ~(1 << bit_offset)
```

Notice how `~(1 << bit_offset)` and `1 << bit_offset` compile directly into native Python `ast.BinOp` and `ast.UnaryOp` operations. At runtime, CPython executes them via `BINARY_OR`, `BINARY_AND`, and `UNARY_INVERT` opcodes at raw C-speed!

---

## 5. Verification Test Suite

[`run_bitarray.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/10_micro_bitarray/run_bitarray.py) verifies all bitwise logic:

```python
# 1. Initialization and indexing
ba = BitArray(16, initial=False)
ba.set(0, True)
ba.set(7, True)
ba.set(15, True)
assert ba.get(0) is True
assert ba.get(1) is False
assert ba.get(7) is True
assert ba.get(15) is True

# 2. Logic gates: AND, OR, XOR
b1 = BitArray.from_hex("F0")  # 11110000
b2 = BitArray.from_hex("AA")  # 10101010

and_res = b1.bitwise_and(b2)
assert and_res.to_hex() == "a0"  # 10100000

or_res = b1.bitwise_or(b2)
assert or_res.to_hex() == "fa"   # 11111010

xor_res = b1.bitwise_xor(b2)
assert xor_res.to_hex() == "5a"  # 01011010

# 3. Population count
assert ba.count_bits() == 3
```

Running the runner:
```bash
python3 Samples/Ported/10_micro_bitarray/run_bitarray.py
```
Outputs:
```
=== Step 1: Building MicroBitArray via `psc build` ===
Build is up to date: outputs in '.../dist' are fresh.

=== Step 2: Testing Ported BitArray Functionality ===
[PASS] BitArray initialization, get, and set verified
[PASS] Bitwise AND, OR, XOR operations verified
[PASS] BitArray Invert (NOT) and unused bit masking verified
[PASS] CountBits (population count) verified
[PASS] Hex string serialization (to_hex and from_hex) verified
[PASS] Dynamic resizing (append and extend) verified

All micro-bitarray verification checks succeeded with 0 errors!
```

---

## Key Takeaways

1. **Dogfooding Drives Language Growth**: Porting real-world libraries exposed the need for bitwise operators and hexadecimal literals, directly improving the compiler for all future users.
2. **Raw Bitwise Speed**: Emitted Python bitwise expressions run with zero function overhead.
3. **Memory Density**: Achieves 8 bits per byte storage density natively in Python.

---

## Next Steps

Now let's examine complex calendar date-time mathematics and modular arithmetic!

In **[Blog 19: Ported 11 — Micro-Croniter (`11_micro_croniter`): 5-Field Cron Scheduling & Calendar Math](./19_ported_11_micro_croniter_cron_and_calendar_math.md)**, we examine how cron expressions advance timestamps across leap years!

