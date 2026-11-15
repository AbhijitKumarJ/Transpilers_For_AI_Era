# 20_numpy_numerics (Tier 9: High-Performance Math, Operators & Multi-Axis Slicing)

This ported sample demonstrates **Tier 9 Scientific Computing** in PythonSharp, covering N-dimensional array manipulation, matrix multiplication lowering via the Python `@` operator, matrix transposition, and multi-axis range slicing.

---

## Technical Features Tested

1. **Generic Tensor Erasure (`NDArray<T>`)**:
   - `NDArray<double>` erases statically to `numpy.ndarray` with zero runtime wrapper tax.
2. **Matrix Multiplication `@` Operator Lowering**:
   - Compiles `.MultiplyMatrix(other)` directly into Python's native `@` matrix multiplication operator.
3. **Multi-Axis Slicing**:
   - C# multidimensional slice syntax `matrix[0..2, 0..2]` lowers cleanly into Python `matrix[0:2, 0:2]`.
4. **Triple-Surface Binding Ingress**:
   - Demonstrates calling `ArrayFactory` methods from `stdlib/02_scientific_and_ai/01_numpy/`.

---

## How to Build and Run

```bash
# 1. Build using psc
psc build Samples/Ported/20_numpy_numerics/NumpyNumerics.psproj -o Samples/Ported/20_numpy_numerics/dist

# 2. Run verification suite
python3 Samples/Ported/20_numpy_numerics/run_numpy.py
```

