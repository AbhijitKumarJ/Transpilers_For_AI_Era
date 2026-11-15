psc docs consolidated shows currently stage of project, readme and plan are from current samples folder while "PythonSharp next goals final.md" is the next plan, but i want a PythonSharp that wraps libraries like numpy with overloads or classes implemented as both closely similar to original python syntax as well as well named, organized and structured C# syntax so that looking at a fully qualified name is sufficient to understand its purpose while we familiarize with new syntax as well as easy migration of existing code.





To support both rapid migration of existing Python code and self-documenting, enterprise-scale readability, PythonSharp can use its **`primitive` class type-erasure engine** (`[MapsTo]`, `[InlineTemplate]`) and **compile-time overload resolver** (`OverloadResolver`) to provide a **Dual-Surface (Bi-Modal) Ambient Library Architecture**.

Because `primitive` classes and their method overloads exist strictly at compile time and erase 100% during Pass 2B and Pass 3A, PythonSharp can expose **two synchronized syntactic surfaces** for every library (`numpy`, `scipy`, `pandas`, `matplotlib`, `sklearn`, `torch`, etc.) with **zero runtime wrapper overhead**:

1. **The Self-Documenting C# FQN Surface (Human-Understanding & Scaling Layer):** Deeply organized, descriptive namespaces, classes, and overloaded method signatures where reading a fully qualified name (e.g., `PythonSharp.Numerics.LinearAlgebra.MatrixOperations.ComputeInverse(matrix)` or `PythonSharp.Numerics.Creation.ArrayFactory.CreateZeroFilled<double>(rows: 3, columns: 3)`) immediately communicates its exact mathematical or architectural domain without requiring prior knowledge of Python's abbreviated function names.


2. **The Python-Mirrored Surface (Zero-Friction Migration & Familiarity Layer):** Direct 1:1 namespace and method mirrors (`using numpy;`, `np.linalg.inv(matrix)`, `np.zeros((3, 3))`) plus Python-named overloads on the exact same underlying `primitive` types. Developers can copy-paste or minimally adapt existing Python scripts, and gradually transition to—or mix and match with—verbose C# syntax as they familiarize themselves with the codebase.



---

## 1. How the Dual-Surface Architecture Works Under the Hood

In `psc`, physical files and declared namespaces are decoupled (`GlobalSymbolTable` in `src/psc/semantics/symbols.py`), and `primitive` types erase to their `[MapsTo]` Python target. By structuring ambient `.d.ps` packages into two unified layers that resolve to the **same `ResolvedType` (`numpy.ndarray`)**, both styles are 100% type-compatible:

* **Unified Underlying `primitive` Type:** Both `PythonSharp.Numerics.Tensors.NDArray<T>` and `numpy.ndarray<T>` map to `"numpy.ndarray"` via `[MapsTo("numpy.ndarray")]`. Passing an array created via `np.zeros(3, 3)` into a verbose enterprise method expecting `NDArray<double>` requires zero casting or conversion.


* **Dual-Named Overloads on Every Type:** On `NDArray<T>`, shorthand Pythonic methods (`Reshape`, `Transpose`, `Dot`) sit right alongside descriptive C# overloads (`ReshapeToDimensions`, `TransposeAxes`, `MultiplyMatrix`). Both carry the same `[MapsTo]` or `[InlineTemplate]` directive, so Pass 3 lowers both to the exact same Python AST call.


* **Erased Static Facade Hierarchy:** Descriptive C# static classes (`PythonSharp.Numerics.LinearAlgebra.MatrixDecompositions.SingularValueDecomposition(...)`) use `[InlineTemplate("np.linalg.svd({0})")]` or `[MapsTo("numpy.linalg.svd")]` to lower directly to `np.linalg.svd(...)` without emitting any intermediate C# wrapper classes.



---

## 2. Concrete Blueprint: Dual-Surface `NumPy` in PythonSharp

### A. The Dual-Surface Ambient Declaration (`PythonSharp.Numerics.NumPy.d.ps`)

```csharp
// ============================================================================
// SURFACE 1: Self-Documenting, Hierarchical C# Enterprise Syntax
// Fully-qualified names explain their exact domain and mathematical purpose.
// ============================================================================
namespace PythonSharp.Numerics.Tensors;

using PythonSharp.Core;

extern using numpy as np;

[MapsTo("np.ndarray")]
[RuntimeType("np.ndarray")]
public primitive class NDArray<T>
{
    // --- Self-Documenting C# Properties ---
    [InlineTemplate("{self}.shape")]
    public extern List<int> DimensionShape { get; }

    [InlineTemplate("{self}.ndim")]
    public extern int NumberOfDimensions { get; }

    [InlineTemplate("{self}.T")]
    public extern NDArray<T> Transposed { get; }

    // --- Python-Familiar Alias Properties (Same Class!) ---
    [InlineTemplate("{self}.shape")]
    public extern List<int> Shape { get; }

    [InlineTemplate("{self}.ndim")]
    public extern int Ndim { get; }

    [InlineTemplate("{self}.T")]
    public extern NDArray<T> T { get; }

    // --- Overloaded Methods: Verbose C# + Pythonic Shorthand ---
    [InlineTemplate("{self}.reshape(({0}, {1}))")]
    public extern NDArray<T> ReshapeToMatrix(int rows, int columns);

    [MapsTo("reshape")]
    public extern NDArray<T> Reshape(params int[] dimensions);

    [MapsTo("mean")]
    public extern double CalculateArithmeticMean(int? axis = null);

    [MapsTo("mean")]
    public extern double Mean(int? axis = null);

    [InlineTemplate("({self} @ {0})")]
    public extern NDArray<T> MatrixMultiply(NDArray<T> rightMatrix);

    [MapsTo("dot")]
    public extern NDArray<T> Dot(NDArray<T> other);

    // Supports C# multi-dimensional slicing: matrix[1..5, ^2.., ::2] -> matrix[1:5, -2:, ::2]
    [InlineTemplate("{self}[{0}]")]
    public extern NDArray<T> this[params object[] slices] { get; set; }
}

namespace PythonSharp.Numerics.Creation;

using PythonSharp.Numerics.Tensors;
extern using numpy as np;

[MapsTo("np")]
public static primitive class ArrayFactory
{
    // Self-documenting C# overloads
    [InlineTemplate("np.zeros(({0}, {1}))")]
    public static extern NDArray<double> CreateZeroMatrix(int rows, int columns);

    [InlineTemplate("np.ones(({0}, {1}))")]
    public static extern NDArray<double> CreateOnesMatrix(int rows, int columns);

    [InlineTemplate("np.eye({0})")]
    public static extern NDArray<double> CreateIdentityMatrix(int dimensionSize);

    [InlineTemplate("np.linspace({0}, {1}, {2})")]
    public static extern NDArray<double> CreateLinearlySpacedVector(double start, double stop, int sampleCount = 50);
}

namespace PythonSharp.Numerics.LinearAlgebra;

using PythonSharp.Numerics.Tensors;
extern using numpy as np;

[MapsTo("np.linalg")]
public static primitive class MatrixOperations
{
    [InlineTemplate("np.linalg.inv({0})")]
    public static extern NDArray<double> ComputeMultiplicativeInverse(NDArray<double> squareMatrix);

    [InlineTemplate("np.linalg.det({0})")]
    public static extern double ComputeDeterminant(NDArray<double> squareMatrix);

    [InlineTemplate("np.linalg.solve({0}, {1})")]
    public static extern NDArray<double> SolveLinearSystem(NDArray<double> coefficientMatrixA, NDArray<double> dependentVectorB);
}

// ============================================================================
// SURFACE 2: Python-Mirrored Syntax (Easy Migration & Instant Familiarity)
// ============================================================================
namespace numpy;

using PythonSharp.Numerics.Tensors;
extern using numpy as np;

[MapsTo("np")]
public static primitive class np
{
    // Overloads for tuple-style Python calls and C# variadic calls
    [InlineTemplate("np.zeros({0})")]
    public static extern NDArray<double> zeros((int, int) shape);

    [InlineTemplate("np.zeros(({0}, {1}))")]
    public static extern NDArray<double> zeros(int rows, int cols);

    [InlineTemplate("np.eye({0})")]
    public static extern NDArray<double> eye(int n);

    [InlineTemplate("np.linspace({0}, {1}, {2})")]
    public static extern NDArray<double> linspace(double start, double stop, int num = 50);

    [MapsTo("np.linalg")]
    public static primitive class linalg
    {
        [InlineTemplate("np.linalg.inv({0})")]
        public static extern NDArray<double> inv(NDArray<double> a);

        [InlineTemplate("np.linalg.det({0})")]
        public static extern double det(NDArray<double> a);

        [InlineTemplate("np.linalg.solve({0}, {1})")]
        public static extern NDArray<double> solve(NDArray<double> a, NDArray<double> b);
    }
}

```

### B. Side-by-Side Usage: Easy Migration vs. Self-Documenting FQN

Because both surfaces resolve to the same underlying `primitive` symbols, developers can write either style—or mix them in the same file while migrating legacy Python scripts:

```csharp
namespace AI.Calibration;

using PythonSharp.Numerics.Tensors;
using PythonSharp.Numerics.Creation;
using PythonSharp.Numerics.LinearAlgebra;
using numpy;

public class SensorCalibrator
{
    // STYLE 1: Quick Migration from Existing Python Code
    public static NDArray<double> MigratePythonFast(NDArray<double> readings)
    {
        var weights = np.eye(3);
        var cropped = readings[1..10, ::2];
        var reshaped = cropped.Reshape(3, 3);
        return np.linalg.inv(reshaped).Dot(weights);
    }

    // STYLE 2: Self-Documenting C# FQN (Readable at a Glance)
    public static NDArray<double> CalibrateEnterprise(NDArray<double> sensorReadings)
    {
        NDArray<double> identityWeights = PythonSharp.Numerics.Creation.ArrayFactory.CreateIdentityMatrix(dimensionSize: 3);
        NDArray<double> croppedSlice = sensorReadings[1..10, ::2];
        NDArray<double> squareMatrix = croppedSlice.ReshapeToMatrix(rows: 3, columns: 3);
        NDArray<double> invertedMatrix = PythonSharp.Numerics.LinearAlgebra.MatrixOperations.ComputeMultiplicativeInverse(squareMatrix);
        return invertedMatrix.MatrixMultiply(identityWeights);
    }
}

```

### C. Emitted Python 3.11+ Output (`ai/calibration.py`)

Both methods compile down to clean, zero-wrapper Python 3.11+:

```python
from __future__ import annotations
import numpy as np

class SensorCalibrator:
    __slots__ = ()

    @staticmethod
    def migrate_python_fast(readings: np.ndarray) -> np.ndarray:
        weights: np.ndarray = np.eye(3)
        cropped: np.ndarray = readings[1:10, ::2]
        reshaped: np.ndarray = cropped.reshape(3, 3)
        return np.linalg.inv(reshaped).dot(weights)

    @staticmethod
    def calibrate_enterprise(sensor_readings: np.ndarray) -> np.ndarray:
        identity_weights: np.ndarray = np.eye(3)
        cropped_slice: np.ndarray = sensor_readings[1:10, ::2]
        square_matrix: np.ndarray = cropped_slice.reshape((3, 3))
        inverted_matrix: np.ndarray = np.linalg.inv(square_matrix)
        return inverted_matrix @ identity_weights

```

---

## 3. Dual-Surface FQN Taxonomy Across the Target Ecosystem

To make every scientific, data, and AI library self-explanatory from its fully qualified name while preserving 1:1 Python migration aliases, here is the standardized dual-surface namespace taxonomy across the roadmap libraries:

| Library | Python-Familiar Surface (Migration) | Self-Documenting C# FQN Surface (Enterprise Clarity) | Emitted Python 3.11+ Target |
| --- | --- | --- | --- |
| **OS / Shutil** | `os.path.join(a, b)`<br>

<br>`shutil.copytree(src, dst)` | `PythonSharp.System.IO.FilePath.Combine(a, b)`<br>

<br>`PythonSharp.System.IO.DirectoryOperations.CopyDirectoryTreeRecursively(src, dst)` | `os.path.join(a, b)`<br>

<br>`shutil.copytree(src, dst)`

 |
| **NumPy** | `np.zeros((3, 3))`<br>

<br>`np.linalg.eig(mat)` | `PythonSharp.Numerics.Creation.ArrayFactory.CreateZeroMatrix(3, 3)`<br>

<br>`PythonSharp.Numerics.LinearAlgebra.EigenDecomposition.ComputeEigenvalues(mat)` | `np.zeros((3, 3))`<br>

<br>`np.linalg.eig(mat)`

 |
| **SciPy** | `scipy.optimize.minimize(fn, x0)`<br>

<br>`scipy.fft.fft(sig)` | `PythonSharp.Scientific.Optimization.FunctionMinimizer.MinimizeScalarFunction(fn, x0)`<br>

<br>`PythonSharp.Scientific.SignalProcessing.FourierTransform.ComputeFastFourierTransform(sig)` | `scipy.optimize.minimize(fn, x0)`<br>

<br>`scipy.fft.fft(sig)`

 |
| **Pandas** | `pd.read_csv(path)`<br>

<br>`df.dropna()` | `PythonSharp.DataScience.Tabular.DataFrameReader.ReadCsvFile<TRow>(path)`<br>

<br>`df.DropRowsWithMissingValues()` | `pd.read_csv(path)`<br>

<br>`df.dropna()`

 |
| **Matplotlib & Seaborn** | `plt.plot(x, y)`<br>

<br>`sns.heatmap(data)` | `PythonSharp.Visualization.Plotting.FigureCanvas.PlotLineSeries(x, y)`<br>

<br>`PythonSharp.Visualization.Statistical.HeatmapPlotter.RenderCorrelationHeatmap(data)` | `plt.plot(x, y)`<br>

<br>`sns.heatmap(data)`

 |
| **Scikit-Learn** | `sklearn.ensemble.RandomForestClassifier()`<br>

<br>`model.fit(X, y)` | `PythonSharp.MachineLearning.Classical.Ensemble.RandomForestClassifier()`<br>

<br>`model.TrainOnLabeledDataset(features: X, labels: y)` | `RandomForestClassifier()`<br>

<br>`model.fit(X, y)`

 |
| **SymPy** | `sp.symbols("x")`<br>

<br>`sp.diff(expr, x)` | `PythonSharp.SymbolicMath.Algebra.SymbolFactory.DeclareSymbol("x")`<br>

<br>`PythonSharp.SymbolicMath.Calculus.Differentiator.DifferentiateWithRespectTo(expr, x)` | `sp.symbols('x')`<br>

<br>`sp.diff(expr, x)`

 |
| **PyTorch / JAX** | `torch.no_grad()`<br>

<br>`nn.Linear(in_f, out_f)` | `[PythonSharp.DeepLearning.Autograd.DisableGradientTracking]`<br>

<br>`PythonSharp.DeepLearning.NeuralNetworks.Layers.FullyConnectedLinearLayer(in_f, out_f)` | `@torch.no_grad()`<br>

<br>`nn.Linear(in_f, out_f)`

 |
| **Qiskit** | `QuantumCircuit(2, 2)`<br>

<br>`qc.h(0); qc.cx(0, 1)` | `PythonSharp.QuantumComputing.Circuits.QuantumRegisterCircuit(qubits: 2, classicalBits: 2)`<br>

<br>`qc.ApplyHadamardGate(0); qc.ApplyControlledNotGate(0, 1)` | `QuantumCircuit(2, 2)`<br>

<br>`qc.h(0); qc.cx(0, 1)`

 |

---

## 4. Replanned Incremental Roadmap (Targets 18–28)

Building on the 17 completed packages in `Samples/Ported/`, the next roadmap tiers are structured so that each target upgrades `psc` and `psc bindgen` to support Dual-Surface (Python-Mirrored + Verbose C# FQN) bindings:

### Tier 8: Native Resource Core & Dual-Surface Bindgen Engine

* **18. `18_core_disposable_contextlib` (`contextlib` $\leftrightarrow$ `PythonSharp.Core.ResourceManagement`):**
* **Dual Surface:** Supports both `using var scope = ...;` (`IDisposable`) and `contextlib.ExitStack`.


* **Compiler Upgrade:** Hardens `using` block unwinding and exception suppression in `__exit__`.




* **19. `19_system_io_shutil` (`os` / `shutil` $\leftrightarrow$ `PythonSharp.System.IO.FileSystem`):**
* **Dual Surface:** Exposes `os.path` / `shutil` directly alongside `PythonSharp.System.IO.DirectoryOperations` and `FilePath`.


* **Compiler & Bindgen Upgrade:** Enhances `psc bindgen` (`src/psc/bindgen/generator.py`) with a `--dual-surface` mode that emits both the 1:1 Python module namespace and the hierarchical C# FQN facade from `.pyi` stubs.





### Tier 9: High-Performance Math, Operators & Multi-Axis Slicing (`NumPy` / `SciPy`)

* **20. `20_numpy_numerics` (`numpy` $\leftrightarrow$ `PythonSharp.Numerics.Tensors` & `LinearAlgebra`):**
* **Dual Surface:** `using numpy;` (`np.zeros`, `np.linalg.inv`, `ndarray<T>`) + `PythonSharp.Numerics.Creation.ArrayFactory` and `PythonSharp.Numerics.LinearAlgebra.MatrixOperations`.


* **Compiler Upgrade:** Implements operator overloading lowering (resolving open decision `OQ-08` / `D-020` in `PROGRESS.md` so `+`, `-`, `*`, and `[OperatorSymbol("@")]` lower to native Python/NumPy operators) and variadic multi-axis range/step slicing (`tensor[1..5, ^2.., ::2]`).




* **21. `21_scipy_scientific` (`scipy` $\leftrightarrow$ `PythonSharp.Scientific.Optimization` & `SignalProcessing`):**
* **Dual Surface:** `scipy.optimize` / `scipy.fft` / `scipy.sparse` + descriptive C# FQN classes (`FunctionMinimizer`, `FourierTransform`, `SparseMatrix`).


* **Compiler Upgrade:** Tuple unpacking return types (`var (eigenvalues, eigenvectors) = ...`) and keyword-argument forwarding (`[KwArgs]`) on overloaded scientific routines.





### Tier 10: Schema-Checked Tabular Data & Fluent Visualization (`Pandas` / `Matplotlib` / `Seaborn`)

* **22. `22_pandas_dataframes` (`pandas` $\leftrightarrow$ `PythonSharp.DataScience.Tabular`):**
* **Dual Surface:** Standard `pd.DataFrame` string-indexed operations for quick migration (`df["age"]`, `df.dropna()`) + schema-bound `DataFrame<TContract>` with descriptive C# methods (`df.SelectColumn(r => r.Age)`, `df.DropRowsWithMissingValues()`) that erase to vanilla Pandas at runtime.


* **Compiler Upgrade:** Compile-time property-to-column name verification on generic `DataFrame<TRecord>` types.




* **23. `23_matplotlib_seaborn_viz` (`matplotlib.pyplot` / `seaborn` $\leftrightarrow$ `PythonSharp.Visualization`):**
* **Dual Surface:** Imperative `plt.plot()` / `sns.heatmap()` calls + fluent C# builder chains (`ChartBuilder.CreateFigure().SetTitle("...").SetXAxisLabel("...").Show()`) that flatten into sequential `plt.*` statements.





### Tier 11: Classical ML, Symbolic Math, Async Harnesses & Deep Learning (`Scikit-Learn` / `SymPy` / `PyTorch` / `Qiskit`)

* **24. `24_sklearn_pipelines` (`sklearn` $\leftrightarrow$ `PythonSharp.MachineLearning.Classical`):**
* **Dual Surface:** `sklearn.pipeline.make_pipeline` + strongly typed `MachineLearningPipeline<TFeatures, TPrediction>` enforcing `IFeatureTransformer` and `IModelEstimator` contracts at compile time.




* **25. `25_sympy_symbolic` (`sympy` $\leftrightarrow$ `PythonSharp.SymbolicMath.Calculus` & `Algebra`):**
* **Dual Surface:** `sp.symbols` / `sp.diff` / `sp.integrate` + C# expression-lambda to symbolic math lowering.




* **26. `26_asyncio_agent_harness` (`asyncio` $\leftrightarrow$ `PythonSharp.Concurrency.Orchestration`):**
* **Dual Surface:** `asyncio.gather` / `asyncio.sleep` + `Task.WhenAll` / `CancellationToken` lowering for multi-agent and data ingestion harnesses.




* **27. `27_torch_deeplearning` (`torch` / `torch.nn` $\leftrightarrow$ `PythonSharp.DeepLearning.NeuralNetworks`):**
* **Dual Surface:** `nn.Module` / `@torch.no_grad()` + `NeuralNetworkModule` base class and `[DisableGradientTracking]` decorator attributes.




* **28. `28_qiskit_quantum` (`qiskit` $\leftrightarrow$ `PythonSharp.QuantumComputing.Circuits`):**
* **Dual Surface:** `qc.h(0)` / `qc.cx(0, 1)` + self-documenting quantum gate methods (`qc.ApplyHadamardGate(qubitIndex: 0)`, `qc.ApplyControlledNotGate(controlQubit: 0, targetQubit: 1)`).





Would you like to start by implementing **operator overloading (`+`, `-`, `*`, `@`) and multi-axis slicing** in `psc` so we can build `20_numpy_numerics` with both the `numpy` and `PythonSharp.Numerics` dual-surface `.d.ps` stubs, or would you prefer starting at Target 18/19 (`System.IO` + `--dual-surface` support in `psc bindgen`)?










Why not have Triple surface, where first is like "PythonSharp.Numerics.LinearAlgebra.MatrixOperations.ComputeInverse(matrix)" while second is like "using numpy;, np.linalg.inv(matrix), np.zeros((3, 3))" and the third is somewhat in between where we define Similarly named namespace but with C# coding standards like PascalCasing somewhat similar naming easily identifiable as replacement of original but following c# conventions and a bit verbose Like " using PythonSharp.Numpy as np; np.LinearAlgebra.Inverse(matrix)" or something more suitable. Also, separate definition of .d,ps for such libraries and what they depend on in separate .d.ps files. This helps identify functions, maintain changes in third party lib  and ultimately navigate to first approach in future






A **Triple-Surface Architecture** paired with **modular, dependency-layered `.d.ps` declaration files** solves both sides of the enterprise adoption curve: it gives Python engineers zero-friction entry, gives C# engineers idiomatic package familiarity, and creates a structured, tool-assisted migration path toward self-documenting domain architecture—all while compiling down to the exact same zero-overhead Python 3.11+ AST.

---

## 1. The Triple-Surface Architecture & Graduation Path

Because `primitive` classes and their static/instance methods exist purely in `GlobalSymbolTable` during Passes 1 and 2 and erase completely via `[MapsTo]` and `[InlineTemplate]` in Pass 3, PythonSharp can expose three distinct syntactic layers that all operate on the **exact same underlying `ResolvedType` (`numpy.ndarray`)**:

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ SURFACE 2: Raw Python Mirror (Stage 1 — Instant Copy-Paste Migration)      │
│ using numpy;                                                               │
│ var inv = np.linalg.inv(matrix);                                           │
│ var z   = np.zeros((3, 3));                                                │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │  Familiarize with C# PascalCase &
                                      ▼  clean up cryptic Python abbreviations
┌────────────────────────────────────────────────────────────────────────────┐
│ SURFACE 3: C#-Standardized Library Mirror (Stage 2 — Idiomatic Bridge)     │
│ using PythonSharp.NumPy as np; // or using PythonSharp.NumPy;              │
│ var inv = np.LinearAlgebra.Inverse(matrix);                                │
│ var z   = np.Zeros(rows: 3, cols: 3);                                      │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │  Refactor to domain-driven,
                                      ▼  self-documenting enterprise FQNs
┌────────────────────────────────────────────────────────────────────────────┐
│ SURFACE 1: Enterprise Domain FQN (Stage 3 — Self-Documenting Scale)        │
│ using PythonSharp.Numerics.LinearAlgebra;                                  │
│ using PythonSharp.Numerics.Creation;                                       │
│ var inv = MatrixOperations.ComputeMultiplicativeInverse(matrix);           │
│ var z   = ArrayFactory.CreateZeroMatrix(rows: 3, columns: 3);              │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │
                                      ▼  Pass 2B Erasure & Pass 3 Lowering
┌────────────────────────────────────────────────────────────────────────────┐
│ EMITTED PYTHON 3.11+ (Identical across all 3 surfaces!)                    │
│ import numpy as np                                                         │
│ inv: np.ndarray = np.linalg.inv(matrix)                                    │
│ z: np.ndarray = np.zeros((3, 3))                                           │
└────────────────────────────────────────────────────────────────────────────┘

```

* **Zero Casting Between Surfaces:** Because every surface returns the shared `NDArray<T>` primitive type (`[MapsTo("np.ndarray")]`), a developer can create a tensor using Surface 2 (`np.zeros((3, 3))`), pass it to a Surface 3 helper (`np.LinearAlgebra.Inverse(m)`), and return it into a Surface 1 pipeline (`MatrixOperations.ComputeDeterminant(m)`) with zero type mismatch or wrapper conversion.


* **Progressive Team Onboarding:** Data scientists porting a Jupyter notebook can start in **Surface 2**, immediately switch to **Surface 3** (`using PythonSharp.NumPy as np; np.LinearAlgebra.Inverse(matrix)`) to get clean C# PascalCasing and descriptive submodule names (`linalg` $\rightarrow$ `LinearAlgebra`, `inv` $\rightarrow$ `Inverse`, `svd` $\rightarrow$ `SingularValueDecomposition`), and eventually promote core production modules to **Surface 1**.



---

## 2. Modular `.d.ps` File Separation & Dependency Topology

Because `ProjectLoader` (`src/psc/project.py`) and `SymbolCollector` (`src/psc/semantics/collector.py`) aggregate logical namespaces across any number of `.d.ps` files before resolving member bodies, we should **never** put an entire library into one monolithic `.d.ps` file.

Instead, separating `.d.ps` files by **1) Shared Data Primitives**, **2) Upstream Dependencies**, and **3) The Three Surfaces** provides massive maintenance advantages:

```text
stdlib/
├── PythonSharp.Core.d.ps                           # Core built-ins (String, List<T>, Dict<K,V>, IEnumerable<T>)
└── packages/
    ├── numpy/
    │   ├── 00_numpy.primitives.d.ps                # Shared foundation: NDArray<T>, DType, Shape (Depended on by SciPy/Pandas/Sklearn)
    │   ├── 01_numpy.raw.d.ps                       # [Surface 2] `namespace numpy;` (1:1 Python mirror: np.zeros, np.linalg.inv)
    │   ├── 02_numpy.csharp.d.ps                    # [Surface 3] `namespace PythonSharp.NumPy;` (C# mirror: np.LinearAlgebra.Inverse)
    │   └── 03_numerics.enterprise.d.ps             # [Surface 1] `namespace PythonSharp.Numerics.*;` (Domain FQN: MatrixOperations.*)
    │
    ├── scipy/
    │   ├── 00_scipy.dependencies.d.ps              # Explicit `using PythonSharp.Numerics.Tensors;` (Requires numpy/00_numpy.primitives.d.ps)
    │   ├── 01_scipy.raw.d.ps                       # [Surface 2] `namespace scipy;` (scipy.linalg, scipy.optimize, scipy.fft)
    │   ├── 02_scipy.csharp.d.ps                    # [Surface 3] `namespace PythonSharp.SciPy;` (SciPy.LinearAlgebra, SciPy.Optimize)
    │   └── 03_scientific.enterprise.d.ps           # [Surface 1] `namespace PythonSharp.Scientific.*;` (FunctionMinimizer, FourierTransform)
    │
    ├── pandas/
    │   ├── 00_pandas.primitives.d.ps               # Shared foundation: DataFrame<TRow>, Series<T>, Index<T> (Depends on NumPy NDArray<T>)
    │   ├── 01_pandas.raw.d.ps                      # [Surface 2] `namespace pandas;` (pd.read_csv, df.dropna, df.groupby)
    │   ├── 02_pandas.csharp.d.ps                   # [Surface 3] `namespace PythonSharp.Pandas;` (pd.ReadCsv, df.DropNa, df.GroupBy)
    │   └── 03_datascience.enterprise.d.ps          # [Surface 1] `namespace PythonSharp.DataScience.Tabular;` (DataFrameReader.ReadCsvFile)
    │
    └── sklearn/
        ├── 00_sklearn.contracts.d.ps               # Shared interfaces: IEstimator<TIn, TOut>, ITransformer<T> (Depends on NumPy & Pandas)
        ├── 01_sklearn.raw.d.ps                     # [Surface 2] `namespace sklearn;` (sklearn.ensemble, model.fit, model.predict)
        ├── 02_sklearn.csharp.d.ps                  # [Surface 3] `namespace PythonSharp.ScikitLearn;` (sk.Ensemble, model.Fit, model.Predict)
        └── 03_machinelearning.enterprise.d.ps      # [Surface 1] `namespace PythonSharp.MachineLearning.Classical;` (model.TrainOnDataset)

```

### Why Separate `.d.ps` Files This Way?

1. **Explicit Inter-Library Dependency Graph:** `pandas` (`Series.ToNumpy()`) and `scipy` (`scipy.linalg.svd()`) depend directly on `NDArray<T>` from `numpy/00_numpy.primitives.d.ps`. Separating `00_<pkg>.primitives.d.ps` makes it immediately obvious which types a library exports to downstream libraries versus which functions belong to its API surface.
2. **Isolating Upstream Breaking Changes:** When a third-party Python package (e.g., NumPy or Pandas) releases a breaking change in a minor/major version, `psc bindgen` only regenerates or diffs `01_<pkg>.raw.d.ps` via `psc-bindings-manifest.json`. If an upstream function is renamed in Python, you only update the `[InlineTemplate]` or `[MapsTo]` string inside `02_<pkg>.csharp.d.ps` and `03_<domain>.enterprise.d.ps`—protecting 100% of your C# application files from breaking!


3. **LSP Navigation & Deprecation Path to Surface 1:** In `psc lsp` (`src/psc/lsp/server.py`), hovering over a Surface 2 call (`np.linalg.inv`) or a Surface 3 call (`np.LinearAlgebra.Inverse`) displays the docstring from `01_numpy.raw.d.ps` or `02_numpy.csharp.d.ps`. By adding `<seealso cref="PythonSharp.Numerics.LinearAlgebra.MatrixOperations.ComputeMultiplicativeInverse"/>` in the stub's XML doc comment, the IDE hover card explicitly teaches the developer the Surface 1 Enterprise FQN as they code.



---

## 3. Concrete Multi-File Implementation Showcase: Triple-Surface `NumPy` + `SciPy` Dependency

Here is how the four modular `.d.ps` files for NumPy and a dependent SciPy `.d.ps` file look in practice.

### File 1: `stdlib/packages/numpy/00_numpy.primitives.d.ps` (Foundation & Instance Overloads)

Defines the core `NDArray<T>` primitive type depended on by all three NumPy surfaces as well as `SciPy`, `Pandas`, `Scikit-Learn`, and `PyTorch`:

```csharp
namespace PythonSharp.Numerics.Tensors;

using PythonSharp.Core;
extern using numpy as np;

/// <summary>
/// Core zero-cost N-dimensional array primitive mapping to numpy.ndarray.
/// Shared across Surface 1 (Enterprise), Surface 2 (Raw Python), and Surface 3 (C# NumPy).
/// </summary>
[MapsTo("np.ndarray")]
[RuntimeType("np.ndarray")]
public primitive class NDArray<T>
{
    // --- Surface 1: Self-Documenting Enterprise Properties ---
    [InlineTemplate("{self}.shape")]
    public extern List<int> DimensionShape { get; }

    [InlineTemplate("{self}.ndim")]
    public extern int NumberOfDimensions { get; }

    [InlineTemplate("{self}.T")]
    public extern NDArray<T> TransposedMatrix { get; }

    // --- Surface 3: C#-Standardized Properties ---
    [InlineTemplate("{self}.shape")]
    public extern List<int> Shape { get; }

    [InlineTemplate("{self}.ndim")]
    public extern int NDim { get; }

    [InlineTemplate("{self}.T")]
    public extern NDArray<T> T { get; }

    // --- Surface 2: Raw Python snake_case Properties ---
    [InlineTemplate("{self}.shape")]
    public extern List<int> shape { get; }

    [InlineTemplate("{self}.ndim")]
    public extern int ndim { get; }

    // --- Triple-Surface Instance Methods ---
    [InlineTemplate("{self}.reshape(({0}, {1}))")]
    public extern NDArray<T> ReshapeToMatrix(int rows, int columns); // Surface 1

    [MapsTo("reshape")]
    public extern NDArray<T> Reshape(params int[] shape);            // Surface 3

    [MapsTo("reshape")]
    public extern NDArray<T> reshape(params int[] shape);            // Surface 2

    [InlineTemplate("({self} @ {0})")]
    public extern NDArray<T> MultiplyMatrix(NDArray<T> other);       // Surface 1

    [MapsTo("dot")]
    public extern NDArray<T> Dot(NDArray<T> other);                  // Surface 3

    [MapsTo("dot")]
    public extern NDArray<T> dot(NDArray<T> other);                  // Surface 2

    // Multi-axis C# range & step slicing: tensor[1..5, ^2.., ::2] -> tensor[1:5, -2:, ::2]
    [InlineTemplate("{self}[{0}]")]
    public extern NDArray<T> this[params object[] slices] { get; set; }
}

```

---

### File 2: `stdlib/packages/numpy/01_numpy.raw.d.ps` (Surface 2 — Raw Python Mirror)

Provides 1:1 Python naming for immediate copy-paste migration (`using numpy; np.linalg.inv(matrix)`):

```csharp
namespace numpy;

using PythonSharp.Numerics.Tensors;
extern using numpy as np;

[MapsTo("np")]
public static primitive class np
{
    /// <summary>
    /// Raw Python mirror for numpy.zeros.
    /// Bridge equivalent: PythonSharp.NumPy.Zeros(rows, cols)
    /// Enterprise equivalent: PythonSharp.Numerics.Creation.ArrayFactory.CreateZeroMatrix(rows, columns)
    /// </summary>
    [InlineTemplate("np.zeros({0})")]
    public static extern NDArray<double> zeros((int, int) shape);

    [InlineTemplate("np.zeros(({0}, {1}))")]
    public static extern NDArray<double> zeros(int rows, int cols);

    [InlineTemplate("np.ones({0})")]
    public static extern NDArray<double> ones((int, int) shape);

    [InlineTemplate("np.eye({0})")]
    public static extern NDArray<double> eye(int n);

    [MapsTo("np.linalg")]
    public static primitive class linalg
    {
        /// <summary>
        /// Raw Python mirror for numpy.linalg.inv.
        /// Bridge equivalent: PythonSharp.NumPy.LinearAlgebra.Inverse(matrix)
        /// Enterprise equivalent: PythonSharp.Numerics.LinearAlgebra.MatrixOperations.ComputeInverse(matrix)
        /// </summary>
        [InlineTemplate("np.linalg.inv({0})")]
        public static extern NDArray<double> inv(NDArray<double> a);

        [InlineTemplate("np.linalg.det({0})")]
        public static extern double det(NDArray<double> a);

        [InlineTemplate("np.linalg.solve({0}, {1})")]
        public static extern NDArray<double> solve(NDArray<double> a, NDArray<double> b);
    }
}

```

---

### File 3: `stdlib/packages/numpy/02_numpy.csharp.d.ps` (Surface 3 — C#-Standardized Library Mirror)

Provides the clean middle ground you described: keeps the recognizable `NumPy` package identity (`using PythonSharp.NumPy as np;`), expands cryptic module abbreviations (`linalg` $\rightarrow$ `LinearAlgebra`, `fft` $\rightarrow$ `FastFourierTransform`, `random` $\rightarrow$ `Random`), and uses standard C# `PascalCase` (`inv` $\rightarrow$ `Inverse`, `det` $\rightarrow$ `Determinant`):

```csharp
namespace PythonSharp.NumPy;

using PythonSharp.Numerics.Tensors;
extern using numpy as _np;

[MapsTo("_np")]
public static primitive class np
{
    // Top-level array creation in clean C# PascalCase
    [InlineTemplate("_np.zeros(({0}, {1}))")]
    public static extern NDArray<double> Zeros(int rows, int cols);

    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> Zeros((int, int) shape);

    [InlineTemplate("_np.ones(({0}, {1}))")]
    public static extern NDArray<double> Ones(int rows, int cols);

    [InlineTemplate("_np.eye({0})")]
    public static extern NDArray<double> Identity(int size);

    [InlineTemplate("_np.linspace({0}, {1}, {2})")]
    public static extern NDArray<double> LinSpace(double start, double stop, int count = 50);

    /// <summary>
    /// C#-standardized mirror of numpy.linalg.
    /// Enterprise FQN: PythonSharp.Numerics.LinearAlgebra.MatrixOperations
    /// </summary>
    [MapsTo("_np.linalg")]
    public static primitive class LinearAlgebra
    {
        [InlineTemplate("_np.linalg.inv({0})")]
        public static extern NDArray<double> Inverse(NDArray<double> matrix);

        [InlineTemplate("_np.linalg.det({0})")]
        public static extern double Determinant(NDArray<double> matrix);

        [InlineTemplate("_np.linalg.solve({0}, {1})")]
        public static extern NDArray<double> Solve(NDArray<double> matrixA, NDArray<double> vectorB);

        [InlineTemplate("_np.linalg.norm({0})")]
        public static extern double Norm(NDArray<double> matrixOrVector);
    }

    /// <summary>
    /// C#-standardized mirror of numpy.fft.
    /// </summary>
    [MapsTo("_np.fft")]
    public static primitive class FastFourier
    {
        [InlineTemplate("_np.fft.fft({0})")]
        public static extern NDArray<double> Fft1D(NDArray<double> signal);

        [InlineTemplate("_np.fft.ifft({0})")]
        public static extern NDArray<double> InverseFft1D(NDArray<double> spectrum);
    }
}

```

---

### File 4: `stdlib/packages/numpy/03_numerics.enterprise.d.ps` (Surface 1 — Enterprise Domain FQN)

Provides the self-documenting architectural hierarchy where the fully qualified name explains the exact domain operation without needing to know whether `numpy` or `scipy` is underneath:

```csharp
namespace PythonSharp.Numerics.Creation;

using PythonSharp.Numerics.Tensors;
extern using numpy as _np;

[MapsTo("_np")]
public static primitive class ArrayFactory
{
    [InlineTemplate("_np.zeros(({0}, {1}))")]
    public static extern NDArray<double> CreateZeroMatrix(int rows, int columns);

    [InlineTemplate("_np.ones(({0}, {1}))")]
    public static extern NDArray<double> CreateOnesMatrix(int rows, int columns);

    [InlineTemplate("_np.eye({0})")]
    public static extern NDArray<double> CreateIdentityMatrix(int dimensionSize);

    [InlineTemplate("_np.linspace({0}, {1}, {2})")]
    public static extern NDArray<double> CreateLinearlySpacedVector(double startValue, double stopValue, int sampleCount = 50);
}

namespace PythonSharp.Numerics.LinearAlgebra;

using PythonSharp.Numerics.Tensors;
extern using numpy as _np;

[MapsTo("_np.linalg")]
public static primitive class MatrixOperations
{
    [InlineTemplate("_np.linalg.inv({0})")]
    public static extern NDArray<double> ComputeInverse(NDArray<double> squareMatrix);

    [InlineTemplate("_np.linalg.det({0})")]
    public static extern double ComputeDeterminant(NDArray<double> squareMatrix);

    [InlineTemplate("_np.linalg.solve({0}, {1})")]
    public static extern NDArray<double> SolveLinearEquations(NDArray<double> coefficientMatrixA, NDArray<double> dependentVectorB);

    [InlineTemplate("_np.linalg.norm({0})")]
    public static extern double ComputeEuclideanNorm(NDArray<double> tensor);
}

```

---

### File 5: `stdlib/packages/scipy/02_scipy.csharp.d.ps` (Explicit Cross-Library `.d.ps` Dependency)

Notice how `SciPy`'s `.d.ps` file explicitly imports `PythonSharp.Numerics.Tensors` from `numpy/00_numpy.primitives.d.ps`. If a developer inspects `scipy/02_scipy.csharp.d.ps`, they immediately see that `SciPy` depends on `NumPy`'s `NDArray<T>` primitive:

```csharp
namespace PythonSharp.SciPy;

// Explicit dependency on NumPy's core tensor primitive (.d.ps)
using PythonSharp.Numerics.Tensors;
extern using scipy.linalg as _scipy_linalg;
extern using scipy.optimize as _scipy_opt;

public static primitive class sp
{
    [MapsTo("_scipy_linalg")]
    public static primitive class LinearAlgebra
    {
        [InlineTemplate("_scipy_linalg.lu({0})")]
        public static extern (NDArray<double> Permutation, NDArray<double> Lower, NDArray<double> Upper) LuDecomposition(NDArray<double> matrix);

        [InlineTemplate("_scipy_linalg.cholesky({0})")]
        public static extern NDArray<double> CholeskyDecomposition(NDArray<double> symmetricPositiveDefiniteMatrix);
    }
}

```

---

## 4. Triple-Surface Comparison Matrix Across Target Libraries

Here is how all three surfaces align across the scientific, data engineering, and AI ecosystem:

| Library & Operation | Surface 2: Raw Python Mirror<br>

<br>*(Instant Migration)* | Surface 3: C#-Standardized Library Mirror<br>

<br>*(Familiar + C# Conventions)* | Surface 1: Enterprise Domain FQN<br>

<br>*(Self-Documenting Architecture)* | Emitted Python 3.11+ |
| --- | --- | --- | --- | --- |
| **NumPy**<br>

<br>*(Matrix Inverse)* | `using numpy;`<br>

<br>`np.linalg.inv(m)` | `using PythonSharp.NumPy;`<br>

<br>`np.LinearAlgebra.Inverse(m)` | `PythonSharp.Numerics.LinearAlgebra`<br>

<br>`.MatrixOperations.ComputeInverse(m)` | `np.linalg.inv(m)`

 |
| **NumPy**<br>

<br>*(Zero Matrix)* | `using numpy;`<br>

<br>`np.zeros((3, 3))` | `using PythonSharp.NumPy;`<br>

<br>`np.Zeros(rows: 3, cols: 3)` | `PythonSharp.Numerics.Creation`<br>

<br>`.ArrayFactory.CreateZeroMatrix(3, 3)` | `np.zeros((3, 3))`

 |
| **SciPy**<br>

<br>*(Minimize Func)* | `using scipy;`<br>

<br>`scipy.optimize.minimize(f, x0)` | `using PythonSharp.SciPy;`<br>

<br>`sp.Optimize.Minimize(f, x0)` | `PythonSharp.Scientific.Optimization`<br>

<br>`.FunctionMinimizer.MinimizeScalar(f, x0)` | `scipy.optimize.minimize(f, x0)`

 |
| **Pandas**<br>

<br>*(Read CSV & Clean)* | `using pandas;`<br>

<br>`var df = pd.read_csv(path);`<br>

<br>`df.dropna()` | `using PythonSharp.Pandas;`<br>

<br>`var df = pd.ReadCsv<UserRow>(path);`<br>

<br>`df.DropMissing()` | `PythonSharp.DataScience.Tabular`<br>

<br>`.DataFrameReader.ReadCsvFile<UserRow>(path)`<br>

<br>`.DropRowsWithMissingValues()` | `df = pd.read_csv(path)`<br>

<br>`df.dropna()`

 |
| **Matplotlib & Seaborn**<br>

<br>*(Plotting)* | `using matplotlib.pyplot;`<br>

<br>`plt.plot(x, y);`<br>

<br>`plt.xlabel("Time");` | `using PythonSharp.Matplotlib;`<br>

<br>`plt.Plot(x, y);`<br>

<br>`plt.XLabel("Time");` | `PythonSharp.Visualization.Plotting`<br>

<br>`.FigureCanvas.PlotLineSeries(x, y)`<br>

<br>`.SetHorizontalAxisLabel("Time")` | `plt.plot(x, y)`<br>

<br>`plt.xlabel('Time')`

 |
| **Scikit-Learn**<br>

<br>*(Model Fit/Predict)* | `using sklearn.ensemble;`<br>

<br>`var clf = RandomForestClassifier();`<br>

<br>`clf.fit(X, y);` | `using PythonSharp.ScikitLearn;`<br>

<br>`var clf = sk.Ensemble.RandomForestClassifier();`<br>

<br>`clf.Fit(X, y);` | `PythonSharp.MachineLearning.Classical.Ensemble`<br>

<br>`.RandomForestClassifier()`<br>

<br>`.TrainOnLabeledDataset(features: X, labels: y)` | `clf = RandomForestClassifier()`<br>

<br>`clf.fit(X, y)`

 |
| **SymPy**<br>

<br>*(Differentiation)* | `using sympy;`<br>

<br>`sp.diff(expr, x)` | `using PythonSharp.SymPy;`<br>

<br>`sp.Calculus.Differentiate(expr, x)` | `PythonSharp.SymbolicMath.Calculus`<br>

<br>`.SymbolicDifferentiator.Differentiate(expr, x)` | `sp.diff(expr, x)`

 |
| **PyTorch**<br>

<br>*(Layers & Grad)* | `using torch;`<br>

<br>`[torch.no_grad]`<br>

<br>`nn.Linear(64, 10)` | `using PythonSharp.PyTorch;`<br>

<br>`[torch.NoGrad]`<br>

<br>`torch.NN.Linear(64, 10)` | `[PythonSharp.DeepLearning.Autograd.DisableGradientTracking]`<br>

<br>`PythonSharp.DeepLearning.Layers.FullyConnectedLinearLayer(64, 10)` | `@torch.no_grad()`<br>

<br>`nn.Linear(64, 10)`

 |
| **Qiskit**<br>

<br>*(Quantum Gates)* | `using qiskit;`<br>

<br>`qc.h(0); qc.cx(0, 1);` | `using PythonSharp.Qiskit;`<br>

<br>`qc.Hadamard(0); qc.CNot(0, 1);` | `PythonSharp.QuantumComputing.Circuits`<br>

<br>`qc.ApplyHadamardGate(0);`<br>

<br>`qc.ApplyControlledNotGate(0, 1);` | `qc.h(0)`<br>

<br>`qc.cx(0, 1)`

 |

---

## 5. How `psc` & `psc lsp` Help Developers Navigate from Surface 2 $\rightarrow$ Surface 3 $\rightarrow$ Surface 1

To make this triple-surface architecture actively guide developers toward Surface 1 over time, we can add one lightweight compile-time attribute to `PythonSharp.Core.d.ps`: **`[CanonicalApi("Fully.Qualified.Surface1.Method")]`**.

1. **Zero-Friction Authoring:** A developer migrating Python code writes `np.linalg.inv(matrix)` (Surface 2) or `np.LinearAlgebra.Inverse(matrix)` (Surface 3). It compiles cleanly with zero errors.
2. **LSP Hover Guidance (`psc lsp`):** Because `01_numpy.raw.d.ps` and `02_numpy.csharp.d.ps` annotate `inv` / `Inverse` with `[CanonicalApi("PythonSharp.Numerics.LinearAlgebra.MatrixOperations.ComputeInverse")]`, hovering over `np.linalg.inv` in VS Code displays:
> **`(primitive method) NDArray<double> np.linalg.inv(NDArray<double> a)`**
> *Emits:* `np.linalg.inv(a)`
> *C# Library Alias (Surface 3):* `PythonSharp.NumPy.np.LinearAlgebra.Inverse(a)`
> *Canonical Enterprise API (Surface 1):* `PythonSharp.Numerics.LinearAlgebra.MatrixOperations.ComputeInverse(a)`


3. **Optional CLI Upgrade Hint (`psc check --suggest-canonical`):** Teams that want to standardize a migrated module onto Surface 3 or Surface 1 can run `psc check --suggest-canonical`, which emits `WARNING [PS004]` hints pointing out every Surface 2 call and its exact Surface 3 and Surface 1 replacements.

Would you like to start by creating the **modular `.d.ps` directory structure and the first triple-surface package (`numpy` across its 4 `.d.ps` files)**, or should we first update `psc bindgen` so it can automatically scaffold `01_<pkg>.raw.d.ps` and `02_<pkg>.csharp.d.ps` from any Python `.pyi` stub?









we need to apply this to standard python packages and function, variables as well and plan on upgrading our app to this new standard





Extending the **Triple-Surface Architecture** to Python’s built-in functions, special variables, and standard library modules turns PythonSharp (`psc`) into a self-contained, progressive ecosystem. Because `load_project()` in `src/psc/project.py` already discovers `.d.ps` files recursively via `sorted(stdlib_dir.rglob("*.d.ps"))` before parsing user `.ps` files, we can modularize `stdlib/` into dependency-ordered, four-file `.d.ps` bundles without breaking existing project loading.

---

## 1. Triple-Surface Taxonomy: Python Built-ins, Variables & Standard Library

Every Python built-in function, global/module variable, and standard library module is exposed across three synchronized surfaces that erase to the exact same Python 3.11+ AST in Pass 3:

* **Surface 2 (Raw Python Mirror):** 1:1 Python module, function, and variable names (`os.environ`, `sys.argv`, `json.loads`, `builtins.len`) for zero-friction copy-pasting and rapid migration.


* **Surface 3 (C#-Standardized Module Mirror):** Retains the recognizable Python module identity (`PythonSharp.OS`, `PythonSharp.Sys`, `PythonSharp.Json`, `PythonSharp.Builtins`) while applying C# `PascalCase` and clean C# overloads (`OS.Environ`, `Sys.Argv`, `Json.Loads`, `Builtins.Len`).


* **Surface 1 (Enterprise Self-Documenting Domain FQN):** Organized by architectural domain so that reading a fully qualified name (`PythonSharp.System.Environment.EnvironmentVariables.GetOrDefault(...)` or `PythonSharp.Serialization.Json.JsonSerializer.DeserializeFromString(...)`) makes its exact purpose unmistakable during code review.



| Category & Item | Surface 2: Raw Python Mirror<br>

<br>*(1:1 Migration)* | Surface 3: C#-Standardized Mirror<br>

<br>*(Familiar + C# Conventions)* | Surface 1: Enterprise Domain FQN<br>

<br>*(Self-Documenting Architecture)* | Emitted Python 3.11+ |
| --- | --- | --- | --- | --- |
| **Built-in Functions**<br>

<br>*(Length / Range / Enum)* | `using builtins;`<br>

<br>`builtins.len(items)`<br>

<br>`builtins.range(0, 10, 2)`<br>

<br>`builtins.enumerate(items)` | `using PythonSharp.Builtins;`<br>

<br>`Builtins.Len(items)`<br>

<br>`Builtins.Range(0, 10, 2)`<br>

<br>`Builtins.Enumerate(items)` | `PythonSharp.Core.Collections`<br>

<br>`.SequenceOperations.GetCount(items)`<br>

<br>`.IntegerRange.CreateStepped(0, 10, 2)`<br>

<br>`.SequenceOperations.WithIndex(items)` | `len(items)`<br>

<br>`range(0, 10, 2)`<br>

<br>`enumerate(items)`

 |
| **Built-in I/O & Reflection**<br>

<br>*(Print / Open / Getattr)* | `using builtins;`<br>

<br>`builtins.print(msg)`<br>

<br>`builtins.open(p, "r")`<br>

<br>`builtins.getattr(obj, k)` | `using PythonSharp.Builtins;`<br>

<br>`Builtins.Print(msg)`<br>

<br>`Builtins.Open(p, "r")`<br>

<br>`Builtins.GetAttr(obj, k)` | `PythonSharp.System.Terminal.StandardOutput.WriteLine(msg)`<br>

<br>`PythonSharp.System.IO.FileStreams.OpenTextReader(p)`<br>

<br>`PythonSharp.Core.Reflection.ObjectInspector.GetAttributeValue(obj, k)` | `print(msg)`<br>

<br>`open(p, 'r')`<br>

<br>`getattr(obj, k)`

 |
| **Special & Module Variables**<br>

<br>*(Name / File / Math Constants)* | `builtins.__name__`<br>

<br>`builtins.__file__`<br>

<br>`math.pi` / `math.inf` | `Builtins.ModuleName`<br>

<br>`Builtins.ModuleFilePath`<br>

<br>`Math.Pi` / `Math.Infinity` | `PythonSharp.System.Runtime.ModuleContext.CurrentModuleName`<br>

<br>`PythonSharp.System.Runtime.ModuleContext.CurrentFilePath`<br>

<br>`PythonSharp.Numerics.Constants.MathematicalConstants.Pi` | `__name__`<br>

<br>`__file__`<br>

<br>`math.pi` / `math.inf`

 |
| **System & Environment Vars**<br>

<br>*(Env / CLI Args / Exit)* | `using os; using sys;`<br>

<br>`os.environ["API_KEY"]`<br>

<br>`sys.argv`<br>

<br>`sys.stdout.write(s)` | `using PythonSharp.OS;`<br>

<br>`OS.Environ["API_KEY"]`<br>

<br>`Sys.Argv`<br>

<br>`Sys.Stdout.Write(s)` | `PythonSharp.System.Environment.EnvironmentVariables.GetRequired("API_KEY")`<br>

<br>`PythonSharp.System.Runtime.ProcessContext.CommandLineArguments`<br>

<br>`PythonSharp.System.Terminal.StandardOutput.WriteRaw(s)` | `os.environ['API_KEY']`<br>

<br>`sys.argv`<br>

<br>`sys.stdout.write(s)`

 |
| **File System & Paths**<br>

<br>*(OS Path / Shutil)* | `using os; using shutil;`<br>

<br>`os.path.join(a, b)`<br>

<br>`os.path.exists(p)`<br>

<br>`shutil.copytree(s, d)` | `using PythonSharp.OS;`<br>

<br>`OS.Path.Join(a, b)`<br>

<br>`OS.Path.Exists(p)`<br>

<br>`Shutil.CopyTree(s, d)` | `PythonSharp.System.IO.FilePath.Combine(a, b)`<br>

<br>`PythonSharp.System.IO.FileSystemEntry.ExistsAtPath(p)`<br>

<br>`PythonSharp.System.IO.DirectoryOperations.CopyDirectoryRecursively(s, d)` | `os.path.join(a, b)`<br>

<br>`os.path.exists(p)`<br>

<br>`shutil.copytree(s, d)`

 |
| **JSON Serialization**<br>

<br>*(Loads / Dumps)* | `using json;`<br>

<br>`json.loads(raw)`<br>

<br>`json.dumps(obj, indent: 2)` | `using PythonSharp.Json;`<br>

<br>`Json.Loads(raw)`<br>

<br>`Json.Dumps(obj, indent: 2)` | `PythonSharp.Serialization.Json.JsonSerializer.DeserializeObject(raw)`<br>

<br>`PythonSharp.Serialization.Json.JsonSerializer.SerializeFormatted(obj, indentSpaces: 2)` | `json.loads(raw)`<br>

<br>`json.dumps(obj, indent=2)`

 |
| **Regular Expressions**<br>

<br>*(Sub / Match / Compile)* | `using re;`<br>

<br>`re.sub(pat, rep, txt)`<br>

<br>`re.findall(pat, txt)` | `using PythonSharp.Re;`<br>

<br>`Re.Sub(pat, rep, txt)`<br>

<br>`Re.FindAll(pat, txt)` | `PythonSharp.Text.RegularExpressions.RegexEngine.ReplaceAllMatches(txt, pat, rep)`<br>

<br>`PythonSharp.Text.RegularExpressions.RegexEngine.FindAllMatches(txt, pat)` | `re.sub(pat, rep, txt)`<br>

<br>`re.findall(pat, txt)`

 |
| **Time, Dates & Logging**<br>

<br>*(Time / Datetime / Logging)* | `using time; using logging;`<br>

<br>`time.time()`<br>

<br>`time.sleep(0.5)`<br>

<br>`logging.getLogger(name)` | `using PythonSharp.Time;`<br>

<br>`Time.NowEpoch()`<br>

<br>`Time.Sleep(0.5)`<br>

<br>`Logging.GetLogger(name)` | `PythonSharp.System.Diagnostics.SystemClock.GetUnixTimestampSeconds()`<br>

<br>`PythonSharp.System.Threading.ThreadOperations.SleepSeconds(0.5)`<br>

<br>`PythonSharp.Diagnostics.Logging.LoggerFactory.GetNamedLogger(name)` | `time.time()`<br>

<br>`time.sleep(0.5)`<br>

<br>`logging.getLogger(name)`

 |

---

## 2. Modular `.d.ps` Directory & Dependency Layout (`stdlib/`)

Because `load_project()` in `src/psc/project.py` sorts discovered `.d.ps` paths lexicographically (`sorted(stdlib_dir.rglob("*.d.ps"))`), prefixing directories and files numerically guarantees that **upstream primitives and dependencies are always registered in `GlobalSymbolTable` before downstream libraries**:

```text
stdlib/
├── 00_core/                                        # Loaded 1st: Compiler Intrinsics & Core Primitives
│   ├── 00_attributes.d.ps                          # [MapsTo], [InlineTemplate], [RuntimeType], [CanonicalApi], [SurfaceLevel]
│   ├── 01_contracts.d.ps                           # IDisposable, IAsyncDisposable, IEquatable<T>, IComparable<T>, IEnumerable<T>
│   ├── 02_primitives.d.ps                          # String, Bytes, Int32, Double, Boolean, Decimal, List<T>, Dict<K,V>, HashSet<T>
│   ├── 03_builtins.raw.d.ps                        # [Surface 2] `namespace builtins;` (len, range, print, open, getattr, __name__)
│   ├── 04_builtins.csharp.d.ps                     # [Surface 3] `namespace PythonSharp.Builtins;` (Builtins.Len, Builtins.Range)
│   └── 05_core.enterprise.d.ps                     # [Surface 1] `namespace PythonSharp.Core.*;` (SequenceOperations, ObjectInspector)
│
├── 01_python_stdlib/                               # Loaded 2nd: Python Standard Library Packages (Depends on 00_core)
│   ├── os_shutil/
│   │   ├── 00_os.primitives.d.ps                   # Shared types: FileStat, DirEntry, EnvironMap (Depends on Dict<string, string>)
│   │   ├── 01_os.raw.d.ps                          # [Surface 2] `namespace os;` & `namespace shutil;` (os.environ, os.path.join)
│   │   ├── 02_os.csharp.d.ps                       # [Surface 3] `namespace PythonSharp.OS;` & `PythonSharp.Shutil;`
│   │   └── 03_io.enterprise.d.ps                   # [Surface 1] `namespace PythonSharp.System.IO;` & `PythonSharp.System.Environment;`
│   ├── sys/
│   │   ├── 00_sys.primitives.d.ps                  # Shared types: TextIOStream, VersionInfo (Depends on 00_core)
│   │   ├── 01_sys.raw.d.ps                         # [Surface 2] `namespace sys;` (sys.argv, sys.path, sys.stdout, sys.exit)
│   │   ├── 02_sys.csharp.d.ps                      # [Surface 3] `namespace PythonSharp.Sys;` (Sys.Argv, Sys.Stdout)
│   │   └── 03_runtime.enterprise.d.ps              # [Surface 1] `namespace PythonSharp.System.Runtime;` & `System.Terminal;`
│   ├── json/
│   │   ├── 00_json.primitives.d.ps                 # Shared types: JsonValue, JsonDecodeError (Depends on 00_core)
│   │   ├── 01_json.raw.d.ps                        # [Surface 2] `namespace json;` (json.loads, json.dumps)
│   │   ├── 02_json.csharp.d.ps                     # [Surface 3] `namespace PythonSharp.Json;` (Json.Loads, Json.Dumps)
│   │   └── 03_serialization.enterprise.d.ps        # [Surface 1] `namespace PythonSharp.Serialization.Json;` (JsonSerializer)
│   ├── re/
│   │   ├── 00_re.primitives.d.ps                   # Shared types: RegexMatch, CompiledPattern (Depends on 00_core)
│   │   ├── 01_re.raw.d.ps                          # [Surface 2] `namespace re;` (re.sub, re.match, re.compile)
│   │   ├── 02_re.csharp.d.ps                       # [Surface 3] `namespace PythonSharp.Re;` (Re.Sub, Re.Match, Re.Compile)
│   │   └── 03_regex.enterprise.d.ps                # [Surface 1] `namespace PythonSharp.Text.RegularExpressions;` (RegexEngine)
│   └── time_datetime_logging_urllib/               # Same 00_primitives -> 01_raw -> 02_csharp -> 03_enterprise split
│
└── 02_scientific_and_ai/                           # Loaded 3rd: Data Science, ML & Quantum (Depends on 00_core & 01_python_stdlib)
    ├── 01_numpy/                                   # 00_numpy.primitives.d.ps (NDArray<T>) -> 01_raw -> 02_csharp -> 03_enterprise
    ├── 02_scipy/                                   # Depends on 01_numpy/00_numpy.primitives.d.ps
    ├── 03_pandas/                                  # Depends on 01_numpy/00_numpy.primitives.d.ps
    ├── 04_matplotlib_seaborn/                      # Depends on 01_numpy & 03_pandas
    ├── 05_sklearn/                                 # Depends on 01_numpy & 03_pandas
    ├── 06_sympy/                                   # Symbolic math & expression trees
    ├── 07_torch_jax/                               # Deep learning tensors & neural modules
    └── 08_qiskit/                                  # Quantum circuits (Depends on 01_numpy)

```

---

## 3. Concrete `.d.ps` Blueprint: Built-in Functions, Variables & `os`/`sys`

Here is how variables (`os.environ`, `sys.argv`, `__name__`) and functions (`len`, `open`, `os.path.join`) are declared across the separated `.d.ps` files using static properties with `[InlineTemplate]` so that variable reads emit raw Python attribute/variable lookups rather than function calls:

### A. `stdlib/00_core/00_attributes.d.ps` (Upgraded with Triple-Surface Metadata)

```csharp
namespace PythonSharp.Core;

public abstract class Attribute { }

public sealed class MapsToAttribute : Attribute { public MapsToAttribute(string pythonTarget) { } }
public sealed class InlineTemplateAttribute : Attribute { public InlineTemplateAttribute(string pythonAstTemplate) { } }
public sealed class RuntimeTypeAttribute : Attribute { public RuntimeTypeAttribute(string pythonRuntimeType) { } }

/// Links a Surface 2 (Raw) or Surface 3 (C# Mirror) declaration to its Surface 1 Enterprise FQN
/// and Surface 3 Bridge FQN for IDE hover cards and `psc check --suggest-canonical` migration hints.
public sealed class CanonicalApiAttribute : Attribute
{
    public CanonicalApiAttribute(string enterpriseFqn, string csharpBridgeFqn = "") { }
}

/// Identifies whether an ambient declaration belongs to Surface 1 (Enterprise), 2 (Raw Python), or 3 (C# Bridge).
public sealed class SurfaceLevelAttribute : Attribute
{
    public SurfaceLevelAttribute(int surfaceNumber) { }
}

```

### B. `stdlib/01_python_stdlib/os_shutil/00_os.primitives.d.ps` (Dependencies & Shared Types)

```csharp
namespace PythonSharp.System.Environment;

// Explicit dependency on 00_core primitives (Dict<K,V>, String, IEnumerable<T>)
using PythonSharp.Core;
extern using os;

/// Shared zero-cost primitive representing os._Environ (depended on by all 3 OS surfaces)
[MapsTo("os._Environ")]
[RuntimeType("dict")]
public primitive class EnvironmentVariableMap : IEnumerable<KeyValuePair<string, string>>
{
    [InlineTemplate("{self}[{0}]")]
    public extern string this[string variableName]
    {
        get;
        [InlineTemplate("{self}[{0}] = {value}")] set;
    }

    // Surface 1 (Enterprise) method
    [MapsTo("get")]
    public extern string? GetVariableOrDefault(string variableName, string? defaultValue = null);

    // Surface 3 (C# Mirror) method
    [CanonicalApi("PythonSharp.System.Environment.EnvironmentVariableMap.GetVariableOrDefault")]
    [MapsTo("get")]
    public extern string? Get(string key, string? defaultValue = null);

    // Surface 2 (Raw Python) method
    [CanonicalApi("PythonSharp.System.Environment.EnvironmentVariableMap.GetVariableOrDefault", "Get")]
    [MapsTo("get")]
    public extern string? get(string key, string? defaultValue = null);

    [InlineTemplate("({0} in {self})")]
    public extern bool ContainsVariable(string variableName);
}

```

### C. `stdlib/01_python_stdlib/os_shutil/01_os.raw.d.ps` (Surface 2 — Raw Python Variables & Functions)

```csharp
namespace os;

using PythonSharp.Core;
using PythonSharp.System.Environment;
extern using os as _py_os;

[SurfaceLevel(2)]
[MapsTo("_py_os")]
public static primitive class os
{
    /// Module-level variable: `os.environ` lowers directly to `os.environ`!
    [CanonicalApi("PythonSharp.System.Environment.EnvironmentVariables.Variables", "PythonSharp.OS.OS.Environ")]
    [InlineTemplate("_py_os.environ")]
    public static extern EnvironmentVariableMap environ { get; }

    /// Module-level variable: `os.sep` lowers directly to `os.sep`
    [CanonicalApi("PythonSharp.System.IO.FilePath.DirectorySeparator", "PythonSharp.OS.OS.Sep")]
    [InlineTemplate("_py_os.sep")]
    public static extern string sep { get; }

    [CanonicalApi("PythonSharp.System.Environment.EnvironmentVariables.GetVariableOrDefault", "PythonSharp.OS.OS.GetEnv")]
    [InlineTemplate("_py_os.getenv({0}, {1})")]
    public static extern string? getenv(string key, string? defaultValue = null);

    [MapsTo("_py_os.path")]
    public static primitive class path
    {
        [CanonicalApi("PythonSharp.System.IO.FilePath.Combine", "PythonSharp.OS.OS.Path.Join")]
        [InlineTemplate("_py_os.path.join({0}, {1})")]
        public static extern string join(string a, string b);

        [CanonicalApi("PythonSharp.System.IO.FileSystemEntry.ExistsAtPath", "PythonSharp.OS.OS.Path.Exists")]
        [InlineTemplate("_py_os.path.exists({0})")]
        public static extern bool exists(string path);
    }
}

```

### D. `stdlib/01_python_stdlib/os_shutil/02_os.csharp.d.ps` (Surface 3 — C#-Standardized Mirror)

```csharp
namespace PythonSharp.OS;

using PythonSharp.Core;
using PythonSharp.System.Environment;
extern using os as _py_os;

[SurfaceLevel(3)]
[MapsTo("_py_os")]
public static primitive class OS
{
    [CanonicalApi("PythonSharp.System.Environment.EnvironmentVariables.Variables")]
    [InlineTemplate("_py_os.environ")]
    public static extern EnvironmentVariableMap Environ { get; }

    [CanonicalApi("PythonSharp.System.IO.FilePath.DirectorySeparator")]
    [InlineTemplate("_py_os.sep")]
    public static extern string Sep { get; }

    [CanonicalApi("PythonSharp.System.Environment.EnvironmentVariables.GetVariableOrDefault")]
    [InlineTemplate("_py_os.getenv({0}, {1})")]
    public static extern string? GetEnv(string key, string? defaultValue = null);

    [MapsTo("_py_os.path")]
    public static primitive class Path
    {
        [CanonicalApi("PythonSharp.System.IO.FilePath.Combine")]
        [InlineTemplate("_py_os.path.join({0}, {1})")]
        public static extern string Join(string path1, string path2);

        [CanonicalApi("PythonSharp.System.IO.FileSystemEntry.ExistsAtPath")]
        [InlineTemplate("_py_os.path.exists({0})")]
        public static extern bool Exists(string path);
    }
}

```

### E. `stdlib/01_python_stdlib/os_shutil/03_io.enterprise.d.ps` (Surface 1 — Enterprise Domain FQN)

```csharp
namespace PythonSharp.System.Environment;

using PythonSharp.Core;
extern using os as _py_os;

[SurfaceLevel(1)]
public static primitive class EnvironmentVariables
{
    [InlineTemplate("_py_os.environ")]
    public static extern EnvironmentVariableMap Variables { get; }

    [InlineTemplate("_py_os.getenv({0}, {1})")]
    public static extern string? GetVariableOrDefault(string variableName, string? defaultValue = null);

    [InlineTemplate("_py_os.environ[{0}]")]
    public static extern string GetRequiredVariable(string variableName);
}

namespace PythonSharp.System.IO;

using PythonSharp.Core;
extern using os as _py_os;

[SurfaceLevel(1)]
public static primitive class FilePath
{
    [InlineTemplate("_py_os.sep")]
    public static extern string DirectorySeparator { get; }

    [InlineTemplate("_py_os.path.join({0}, {1})")]
    public static extern string Combine(string basePath, string relativePath);
}

[SurfaceLevel(1)]
public static primitive class FileSystemEntry
{
    [InlineTemplate("_py_os.path.exists({0})")]
    public static extern bool ExistsAtPath(string targetPath);
}

```

---

## 4. Engineering Plan: Upgrading `psc`, `stdlib/`, Tooling & Samples to the Triple-Surface Standard

To upgrade the current PythonSharp v2.0 codebase (`src/psc/`, `stdlib/`, and `Samples/`) cleanly without breaking the 131 existing tests, we can execute the upgrade in **five incremental milestones**:

### Milestone U1: Compiler Pass Enhancements (`src/psc/`)

1. **Static Primitive Property Template Lowering (`src/psc/semantics/primitive_resolver.py` & `src/psc/codegen/expr_lowerer.py`):**
* Currently, static getter-only computed properties on regular classes lower to `@classmethod` calls (`D-019` in `PROGRESS.md`).


* Verify and harden `ExpressionLowerer` so that reading a static property on a `primitive class` carrying `[InlineTemplate("...")]` or `[MapsTo("...")]` (such as `os.environ`, `sys.argv`, `math.pi`, or `Builtins.ModuleName`) always expands its inline template directly as a variable/attribute read (`os.environ`, `sys.argv`, `math.pi`, `__name__`) rather than appending `()`.




2. **Automatic `extern using` Alias Tracking (`src/psc/codegen/py_ast_builder.py`):**
* When an `[InlineTemplate("_py_os.path.join({0}, {1})")]` from a `.d.ps` file is expanded in a user `.ps` file, `PythonAstBuilder` automatically injects the canonical Python import (`import os` or `import numpy as np`) at the top of the emitted `.py` module (expanding the existing auto-import mechanism already used for `math`, `itertools`, and `statistics`).




3. **Register `[CanonicalApi]` & `[SurfaceLevel]` Metadata (`src/psc/semantics/symbols.py`):**
* Add `canonical_api: str | None = None`, `bridge_api: str | None = None`, and `surface_level: int = 1` fields to `TypeSymbol` and `MemberSymbol` so the type checker and LSP server can inspect them.





### Milestone U2: Modularizing `stdlib/` into `00_core/` and `01_python_stdlib/`

1. **Split `stdlib/PythonSharp.Core.d.ps` into `stdlib/00_core/`:**
* Extract attributes (`00_attributes.d.ps`), contracts (`01_contracts.d.ps`), core primitives (`02_primitives.d.ps`), and the three surfaces for Python `builtins` (`03_builtins.raw.d.ps`, `04_builtins.csharp.d.ps`, `05_core.enterprise.d.ps`).




2. **Create `stdlib/01_python_stdlib/` Triple-Surface Bundles:**
* Create the 4-file bundles (`00_primitives`, `01_raw`, `02_csharp`, `03_enterprise`) for the standard library modules already used across the 17 ported samples and Tier 8 targets:


* `os_shutil/` (`os`, `os.path`, `shutil`)


* `sys/` (`sys.argv`, `sys.stdout`, `sys.stderr`, `sys.exit`)


* `re/` (`re.sub`, `re.match`, `re.findall`, `re.compile`)


* `json/` (`json.loads`, `json.dumps`)


* `time_datetime/` (`time.time`, `time.sleep`, `datetime`)


* `urllib_http/` (`urllib.request`)


* `logging_traceback/` (`logging`, `traceback`)


* `contextlib_subprocess/` (`contextlib`, `subprocess`)







### Milestone U3: Upgrading `psc bindgen` to a Triple-Surface Generator (`src/psc/bindgen/`)

1. **Multi-File Bundle Output in `BindgenGenerator` (`src/psc/bindgen/generator.py`):**
* Upgrade `psc bindgen <pyi_path> -o <out_dir>` to emit the structured directory bundle:


* `00_<pkg>.primitives.d.ps`: Classes, records, protocols, and shared types converted by `TypeConverter`.


* `01_<pkg>.raw.d.ps`: Surface 2 (`[SurfaceLevel(2)]`) preserving exact Python `snake_case` function/variable names.
* `02_<pkg>.csharp.d.ps`: Surface 3 (`[SurfaceLevel(3)]`) converting module and function names to `PascalCase` with `[CanonicalApi]` links.


* `03_<pkg>.enterprise.d.ps`: Surface 1 (`[SurfaceLevel(1)]`) scaffold with descriptive domain namespaces ready for team curation.




2. **Manifest Dependency Tracking (`src/psc/bindgen/manifest.py`):**
* Record cross-stub dependencies (`depends_on: ["00_core", "01_numpy"]`) in `psc-bindings-manifest.json` alongside the SHA-256 drift hashes.





### Milestone U4: Upgrading `psc lsp` & CLI Migration Diagnostics (`src/psc/lsp/` & `src/psc/cli.py`)

1. **Triple-Surface Hover & Completion in `LanguageServer` (`src/psc/lsp/server.py`):**
* When a user hovers over any Surface 2 (`os.path.join`) or Surface 3 (`OS.Path.Join`) call in VS Code, `handle_hover` reads `member_sym.canonical_api` and displays the complete 3-tier ladder right in the tooltip:


* **Surface 2 (Raw Python):** `os.path.join(a, b)`
* **Surface 3 (C# Bridge):** `PythonSharp.OS.OS.Path.Join(a, b)`
* **Surface 1 (Enterprise FQN):** `PythonSharp.System.IO.FilePath.Combine(a, b)`
* **Emits:** `os.path.join(a, b)`




2. **CLI Surface Audit Flag (`psc check --target-surface <1|3>`):**
* Add an optional `--target-surface` flag to `psc check` and `psc build`. When enabled, any usage of a lower surface (e.g., Surface 2 raw calls in a production module) emits a `WARNING [PS004]` diagnostic with a fix hint showing the exact Surface 3 or Surface 1 replacement.





### Milestone U5: Dogfooding Upgrade Across Existing Samples (`Samples/` & `Samples/Ported/`)

1. **Eliminate Local Ad-Hoc `extern` Shims in Ported Samples:**
* In `Samples/Ported/02_slugify`, `06_micro_tqdm`, `07_micro_dotenv`, `08_micro_requests`, `12_json_logger`, and `17_micro_eventloop`, replace local ad-hoc `[InlineTemplate("json.loads({0})")]` helpers with imports from the new modular `stdlib/01_python_stdlib/`.




2. **Add a Dedicated Showcase Sample (`Samples/06_triple_surface_migration/`):**
* Demonstrate a single data-ingestion and matrix-processing workflow written side-by-side in Surface 2 (Raw Python), Surface 3 (C# Bridge), and Surface 1 (Enterprise Domain FQN), proving that all three produce byte-identical Python 3.11+ ASTs.



---

Would you like to begin with **Milestone U1 & U2** (updating `src/psc/` and generating the modular `stdlib/00_core/` and `stdlib/01_python_stdlib/` `.d.ps` files), or would you like to inspect the exact file changes for `src/psc/semantics/symbols.py` and `src/psc/codegen/expr_lowerer.py` first?










