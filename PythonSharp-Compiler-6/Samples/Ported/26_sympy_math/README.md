# PythonSharp Tier 11 Port: SymPy Symbolic Math Engine

This sample dogfoods PythonSharp on **SymPy** for symbolic mathematics, calculus, algebraic equation solving, trigonometric identities, physics modeling, and user-defined operator overloading with **Zero Runtime Wrapper Tax**.

---

## Architecture & Features

1. **User-Defined Operator Overloading (`SymbolicPoint2D`)**:
   - Compiles static `operator +`, `operator -`, `operator -` (negation), and `operator *` into Python dunder methods (`__add__`, `__sub__`, `__neg__`, `__mul__`).
   - Direct native Python execution with zero dispatch overhead.

2. **Calculus & Physics Modeling (`PhysicsKinematicsService`)**:
   - First-order differentiation ($\frac{ds}{dt} = v$) and second-order differentiation ($\frac{dv}{dt} = a$).
   - Definite integration ($\int_{t_1}^{t_2} v(t) dt$) for total displacement calculation.
   - Evaluates trajectories numerically into strongly typed `KinematicsState` records.

3. **Algebraic Systems & Curvature Analysis (`PotentialWellOptimizer`)**:
   - Symbolic solving of stationary points ($\frac{dV}{dx} = 0$).
   - Second derivative curvature evaluation ($\frac{d^2V}{dx^2}$) for potential barrier vs potential well stability classification.

4. **Trigonometric Simplification (`HarmonicOscillatorEngine`)**:
   - Automated simplification of trigonometric identities: $\sin^2(\theta) + \cos^2(\theta) = 1$.

5. **Tri-Modal Surface Verification (`TriModalVerificationService`)**:
   - **Surface 1 Enterprise**: `SymbolFactory`, `SymbolicCalculus`, `SymbolicAlgebra`, `SymbolicTrigonometry`.
   - **Surface 3 C# Bridge**: `PythonSharp.SymPy.sp.Symbols`, `sp.Diff`, `sp.Integrate`, `sp.Sin`.
   - **Surface 2 Raw Python ABI**: `sympy.sp.symbols`, `sp.diff`, `sp.integrate`, `sp.sin`.

---

## Compilation & Verification

To build and run the sample:

```bash
# 1. Compile the PythonSharp project
psc build Samples/Ported/26_sympy_math/SympyMath.psproj -o Samples/Ported/26_sympy_math/dist

# 2. Execute verification test harness
python3 Samples/Ported/26_sympy_math/run_sympy.py
```

