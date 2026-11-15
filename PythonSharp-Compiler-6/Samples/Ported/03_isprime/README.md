# 03_isprime — PythonSharp Ported Library

Ported implementation of the standard primality and mathematical factorization utilities in PythonSharp.

## Features
- `PrimeMath.IsPrime(long n)`: Fast $6k \pm 1$ primality test.
- `PrimeMath.NextPrime(long n)`: Next prime number discovery.
- `PrimeMath.PrimesUpTo(int limit)`: Sieve of Eratosthenes generating `List<int>`.
- `PrimeMath.PrimeFactors(long n)`: Prime factor decomposition into `List<long>`.

## Compiling and Running

```bash
# 1. Compile with PythonSharp compiler
psc build .

# 2. Run verification test harness
python3 run_isprime.py
```

