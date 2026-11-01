# Level 4 — Post 4: Symbolic Calculus & Closed-Form Physics: Operator Overloading with SymPy

Scientific computation often requires exact analytical mathematics rather than floating-point approximations. In computational physics, robotics kinematics, and control theory, computing symbolic derivatives, integrals, equilibrium roots, and trigonometric simplifications in closed form prevents compounding numerical error.

In **Tier 11** ([`Samples/Ported/26_sympy_math/`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/26_sympy_math/)), PythonSharp demonstrates the transpilation of analytical calculus via **SymPy**, showcasing how C# **Operator Overloading** (`operator +`, `operator -`, `operator *`) compiles into Python's object model (`__add__`, `__sub__`, `__mul__`) without runtime wrappers.

---

## 🧮 C# Operator Overloading in Vector Mechanics

To model 2D trajectory dynamics, [`SymbolicPoint2D`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/26_sympy_math/SymbolicMathEngine.ps) defines mathematical vector operators:

```csharp
public class SymbolicPoint2D
{
    public double X { get; set; }
    public double Y { get; set; }

    public SymbolicPoint2D(double x, double y)
    {
        X = x;
        Y = y;
    }

    public static SymbolicPoint2D operator +(SymbolicPoint2D a, SymbolicPoint2D b)
    {
        return new SymbolicPoint2D(a.X + b.X, a.Y + b.Y);
    }

    public static SymbolicPoint2D operator -(SymbolicPoint2D a, SymbolicPoint2D b)
    {
        return new SymbolicPoint2D(a.X - b.X, a.Y - b.Y);
    }

    public static SymbolicPoint2D operator -(SymbolicPoint2D a)
    {
        return new SymbolicPoint2D(-a.X, -a.Y);
    }

    public static SymbolicPoint2D operator *(SymbolicPoint2D a, double scalar)
    {
        return new SymbolicPoint2D(a.X * scalar, a.Y * scalar);
    }
}
```

### Emitted Python AST
PythonSharp resolves static operators and emits instance dunder methods conforming strictly to Python's data model:

```python
class SymbolicPoint2D:
    __slots__ = ('_x', '_y')

    def __init__(self, x: float, y: float) -> None:
        self._x = x
        self._y = y

    def __add__(self, b: SymbolicPoint2D) -> SymbolicPoint2D:
        return SymbolicPoint2D(self._x + b._x, self._y + b._y)

    def __sub__(self, b: SymbolicPoint2D) -> SymbolicPoint2D:
        return SymbolicPoint2D(self._x - b._x, self._y - b._y)

    def __neg__(self) -> SymbolicPoint2D:
        return SymbolicPoint2D(-self._x, -self._y)

    def __mul__(self, scalar: float) -> SymbolicPoint2D:
        return SymbolicPoint2D(self._x * scalar, self._y * scalar)
```

Notice that binary `operator +(a, b)` maps to `def __add__(self, b)`. C# unary minus `operator -(a)` maps to `def __neg__(self)`. The translation is 100% native and zero-cost.

---

## 🚀 Kinematics Calculus: Analytical Derivatives

```mermaid
flowchart TD
    Pos["Position x(t) = 3t^3 - 4t^2 + 5t + 2"] --> Deriv1["ComputeDerivative(x, t)"]
    Deriv1 --> Vel["Velocity v(t) = 9t^2 - 8t + 5"]
    Vel --> Deriv2["ComputeDerivative(v, t)"]
    Deriv2 --> Acc["Acceleration a(t) = 18t - 8"]
    Acc --> Eval["EvaluateAtTime(t = 2.0s)"]
    Eval --> Res["(x=20.0m, v=25.0m/s, a=28.0m/s^2)"]
```

In [`PhysicsKinematicsService`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/26_sympy_math/SymbolicMathEngine.ps), higher-order derivatives are computed symbolically:

```csharp
public class PhysicsKinematicsService
{
    public SymbolicVariable TimeVariable { get; set; }
    public SymbolicExpression PositionExpression { get; set; }
    public SymbolicExpression VelocityExpression { get; set; }
    public SymbolicExpression AccelerationExpression { get; set; }

    public PhysicsKinematicsService(string positionFormula)
    {
        TimeVariable = SymbolicMathFactory.CreateSymbol("t");
        PositionExpression = SymbolicMathFactory.ParseMathematicalExpression(positionFormula);
        VelocityExpression = PositionExpression.ComputeDerivativeWithRespectTo(TimeVariable);
        AccelerationExpression = VelocityExpression.ComputeDerivativeWithRespectTo(TimeVariable);
    }

    public KinematicsState EvaluateKinematics(double timeInstant)
    {
        double pos = PositionExpression.EvaluateAtSubstitution(TimeVariable, timeInstant);
        double vel = VelocityExpression.EvaluateAtSubstitution(TimeVariable, timeInstant);
        double acc = AccelerationExpression.EvaluateAtSubstitution(TimeVariable, timeInstant);
        return new KinematicsState(timeInstant, pos, vel, acc);
    }
}
```

At $t = 2.0$:
- Position $x(2) = 3(2)^3 - 4(2)^2 + 5(2) + 2 = 24 - 16 + 10 + 2 = 20.0\text{ m}$
- Velocity $v(2) = 9(2)^2 - 8(2) + 5 = 36 - 16 + 5 = 25.0\text{ m/s}$
- Acceleration $a(2) = 18(2) - 8 = 36 - 8 = 28.0\text{ m/s}^2$

Every formula is solved symbolically by SymPy and evaluated with double-precision accuracy.

---

## ⚡ Harmonic Potential Wells & Trigonometric Rewrites

[`SymbolicPotentialWellSolver`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/26_sympy_math/SymbolicMathEngine.ps) solves for equilibrium points where the gradient of the potential energy vanishes $\frac{dV}{dx} = 0$, and calculates the curvature $\frac{d^2V}{dx^2}$:

```csharp
public class SymbolicPotentialWellSolver
{
    public static List<double> FindEquilibriumPoints(SymbolicExpression potential, SymbolicVariable coord)
    {
        var force = potential.ComputeDerivativeWithRespectTo(coord);
        return force.SolveRootsEquatedToZero(coord);
    }

    public static double CalculateCurvature(SymbolicExpression potential, SymbolicVariable coord, double atX)
    {
        var curvature = potential.ComputeDerivativeWithRespectTo(coord).ComputeDerivativeWithRespectTo(coord);
        return curvature.EvaluateAtSubstitution(coord, atX);
    }

    public static string SimplifyTrigonometricIdentity(string unsimplifiedTrig)
    {
        var expr = SymbolicMathFactory.ParseMathematicalExpression(unsimplifiedTrig);
        return expr.SimplifyTrigonometricTerms().RenderToString();
    }
}
```

When given $\sin^2(x) + \cos^2(x)$, `SimplifyTrigonometricTerms()` applies the Pythagorean identity in closed form and returns `"1"`.

---

## 🔬 Test Harness Verification

[`run_sympy.py`](file:///home/abhijit/Videos/transpilers/PythonSharp/Samples/Ported/26_sympy_math/run_sympy.py) verifies:
- Operator overloading arithmetic on `SymbolicPoint2D`.
- Kinematic derivation and substitution values at $t = 2.0\text{s}$.
- Potential well root finding and curvature at equilibrium $x = 0$.
- Trigonometric simplification to canonical identity.
- Full execution in 1.32s with zero runtime overhead.

