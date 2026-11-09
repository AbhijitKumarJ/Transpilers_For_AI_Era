The complete raw `.d.ps` declaration files for `02_scipy`, `03_pandas`, `04_matplotlib_seaborn`, `05_sklearn`, `06_torch`, `07_sympy`, and `08_qiskit` follow the four-file Triple-Surface architecture (`00_*.primitives.d.ps`, `01_*.raw.d.ps`, `02_*.csharp.d.ps`, `03_*.enterprise.d.ps`). Each file declares a single top-level namespace with explicit upstream primitive dependencies (`PythonSharp.Core` and `PythonSharp.Numerics.Tensors`) so it parses cleanly in `psc` and drops directly into `stdlib/02_scientific_and_ai/`.

---

## 1. `02_scipy` (Optimization, Linear Algebra, Signal Processing & Sparse Matrices)

Each `02_scipy` file depends on `NDArray<T>` from `01_numpy/00_numpy.primitives.d.ps` and maps Surface 2 (`scipy`), Surface 3 (`PythonSharp.SciPy`), and Surface 1 (`PythonSharp.Scientific`) to `scipy.optimize`, `scipy.linalg`, `scipy.fft`, and `scipy.sparse`.

### `stdlib/02_scientific_and_ai/02_scipy/00_scipy.primitives.d.ps`

```csharp
namespace PythonSharp.Scientific;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using scipy.optimize as _scipy_opt;
extern using scipy.sparse as _scipy_sparse;

[MapsTo("scipy.optimize.OptimizeResult")]
[RuntimeType("scipy.optimize.OptimizeResult")]
public primitive class OptimizationResult
{
    // --- Surface 1: Self-Documenting Enterprise Properties ---
    [InlineTemplate("{self}.x")]
    public extern NDArray<double> OptimalSolutionVector { get; }

    [InlineTemplate("bool({self}.success)")]
    public extern bool ConvergedSuccessfully { get; }

    [InlineTemplate("float({self}.fun)")]
    public extern double ObjectiveFunctionValue { get; }

    [InlineTemplate("int({self}.nit)")]
    public extern int IterationCount { get; }

    [InlineTemplate("str({self}.message)")]
    public extern string TerminationMessage { get; }

    // --- Surface 3: C#-Standardized Properties ---
    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.OptimalSolutionVector")]
    [InlineTemplate("{self}.x")]
    public extern NDArray<double> X { get; }

    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.ConvergedSuccessfully")]
    [InlineTemplate("bool({self}.success)")]
    public extern bool Success { get; }

    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.ObjectiveFunctionValue")]
    [InlineTemplate("float({self}.fun)")]
    public extern double Fun { get; }

    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.IterationCount")]
    [InlineTemplate("int({self}.nit)")]
    public extern int Nit { get; }

    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.TerminationMessage")]
    [InlineTemplate("str({self}.message)")]
    public extern string Message { get; }

    // --- Surface 2: Raw Python snake_case Properties ---
    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.OptimalSolutionVector", "X")]
    [InlineTemplate("{self}.x")]
    public extern NDArray<double> x { get; }

    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.ConvergedSuccessfully", "Success")]
    [InlineTemplate("bool({self}.success)")]
    public extern bool success { get; }

    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.ObjectiveFunctionValue", "Fun")]
    [InlineTemplate("float({self}.fun)")]
    public extern double fun { get; }

    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.IterationCount", "Nit")]
    [InlineTemplate("int({self}.nit)")]
    public extern int nit { get; }

    [CanonicalApi("PythonSharp.Scientific.OptimizationResult.TerminationMessage", "Message")]
    [InlineTemplate("str({self}.message)")]
    public extern string message { get; }
}

[MapsTo("scipy.sparse.csr_matrix")]
[RuntimeType("scipy.sparse.csr_matrix")]
public primitive class CompressedSparseRowMatrix<T>
{
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) MatrixDimensions { get; }

    [CanonicalApi("PythonSharp.Scientific.CompressedSparseRowMatrix.MatrixDimensions")]
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) Shape { get; }

    [CanonicalApi("PythonSharp.Scientific.CompressedSparseRowMatrix.MatrixDimensions", "Shape")]
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) shape { get; }

    [InlineTemplate("int({self}.nnz)")]
    public extern int NonZeroElementCount { get; }

    [CanonicalApi("PythonSharp.Scientific.CompressedSparseRowMatrix.NonZeroElementCount")]
    [InlineTemplate("int({self}.nnz)")]
    public extern int Nnz { get; }

    [CanonicalApi("PythonSharp.Scientific.CompressedSparseRowMatrix.NonZeroElementCount", "Nnz")]
    [InlineTemplate("int({self}.nnz)")]
    public extern int nnz { get; }

    // --- Triple-Surface Instance Methods ---
    [MapsTo("toarray")]
    public extern NDArray<T> ConvertToDenseArray();

    [CanonicalApi("PythonSharp.Scientific.CompressedSparseRowMatrix.ConvertToDenseArray")]
    [MapsTo("toarray")]
    public extern NDArray<T> ToArray();

    [CanonicalApi("PythonSharp.Scientific.CompressedSparseRowMatrix.ConvertToDenseArray", "ToArray")]
    [MapsTo("toarray")]
    public extern NDArray<T> toarray();

    [MapsTo("dot")]
    public extern NDArray<T> MultiplyDense(NDArray<T> other);

    [CanonicalApi("PythonSharp.Scientific.CompressedSparseRowMatrix.MultiplyDense")]
    [MapsTo("dot")]
    public extern NDArray<T> Dot(NDArray<T> other);

    [CanonicalApi("PythonSharp.Scientific.CompressedSparseRowMatrix.MultiplyDense", "Dot")]
    [MapsTo("dot")]
    public extern NDArray<T> dot(NDArray<T> other);
}

```

### `stdlib/02_scientific_and_ai/02_scipy/01_scipy.raw.d.ps`

```csharp
namespace scipy;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.Scientific;
extern using scipy.optimize as _scipy_opt;
extern using scipy.linalg as _scipy_linalg;
extern using scipy.fft as _scipy_fft;
extern using scipy.sparse as _scipy_sparse;
extern using scipy.stats as _scipy_stats;

[SurfaceLevel(2)]
[MapsTo("_scipy_opt")]
public static primitive class OptimizeModule
{
    [CanonicalApi("PythonSharp.Scientific.FunctionMinimizer.MinimizeScalarFunction", "PythonSharp.SciPy.sp.Optimize.Minimize")]
    [InlineTemplate("_scipy_opt.minimize({0}, {1})")]
    public static extern OptimizationResult minimize(object fun, NDArray<double> x0);

    [CanonicalApi("PythonSharp.Scientific.FunctionMinimizer.MinimizeScalarFunctionWithMethod", "PythonSharp.SciPy.sp.Optimize.Minimize")]
    [InlineTemplate("_scipy_opt.minimize({0}, {1}, method={2})")]
    public static extern OptimizationResult minimize(object fun, NDArray<double> x0, string method);

    [CanonicalApi("PythonSharp.Scientific.FunctionMinimizer.FindScalarRoot", "PythonSharp.SciPy.sp.Optimize.Root")]
    [InlineTemplate("_scipy_opt.root({0}, {1})")]
    public static extern OptimizationResult root(object fun, NDArray<double> x0);
}

[SurfaceLevel(2)]
[MapsTo("_scipy_linalg")]
public static primitive class LinalgModule
{
    [CanonicalApi("PythonSharp.Scientific.MatrixDecompositions.ComputeLuDecomposition", "PythonSharp.SciPy.sp.LinearAlgebra.Lu")]
    [InlineTemplate("_scipy_linalg.lu({0})")]
    public static extern (NDArray<double> p, NDArray<double> l, NDArray<double> u) lu(NDArray<double> a);

    [CanonicalApi("PythonSharp.Scientific.MatrixDecompositions.ComputeCholeskyDecomposition", "PythonSharp.SciPy.sp.LinearAlgebra.Cholesky")]
    [InlineTemplate("_scipy_linalg.cholesky({0})")]
    public static extern NDArray<double> cholesky(NDArray<double> a);

    [CanonicalApi("PythonSharp.Scientific.MatrixDecompositions.ComputeSingularValueDecomposition", "PythonSharp.SciPy.sp.LinearAlgebra.Svd")]
    [InlineTemplate("_scipy_linalg.svd({0})")]
    public static extern (NDArray<double> u, NDArray<double> s, NDArray<double> vh) svd(NDArray<double> a);

    [CanonicalApi("PythonSharp.Scientific.MatrixDecompositions.SolveLinearSystem", "PythonSharp.SciPy.sp.LinearAlgebra.Solve")]
    [InlineTemplate("_scipy_linalg.solve({0}, {1})")]
    public static extern NDArray<double> solve(NDArray<double> a, NDArray<double> b);
}

[SurfaceLevel(2)]
[MapsTo("_scipy_fft")]
public static primitive class FftModule
{
    [CanonicalApi("PythonSharp.Scientific.FourierTransform.ComputeFastFourierTransform", "PythonSharp.SciPy.sp.Fft.Fft1D")]
    [InlineTemplate("_scipy_fft.fft({0})")]
    public static extern NDArray<double> fft(NDArray<double> x);

    [CanonicalApi("PythonSharp.Scientific.FourierTransform.ComputeInverseFastFourierTransform", "PythonSharp.SciPy.sp.Fft.Ifft1D")]
    [InlineTemplate("_scipy_fft.ifft({0})")]
    public static extern NDArray<double> ifft(NDArray<double> x);

    [CanonicalApi("PythonSharp.Scientific.FourierTransform.ComputeRealFastFourierTransform", "PythonSharp.SciPy.sp.Fft.Rfft1D")]
    [InlineTemplate("_scipy_fft.rfft({0})")]
    public static extern NDArray<double> rfft(NDArray<double> x);
}

[SurfaceLevel(2)]
[MapsTo("_scipy_sparse")]
public static primitive class SparseModule
{
    [CanonicalApi("PythonSharp.Scientific.SparseMatrixFactory.CreateCompressedSparseRowMatrix", "PythonSharp.SciPy.sp.Sparse.CsrMatrix")]
    [InlineTemplate("_scipy_sparse.csr_matrix({0})")]
    public static extern CompressedSparseRowMatrix<double> csr_matrix(NDArray<double> denseMatrix);

    [CanonicalApi("PythonSharp.Scientific.SparseMatrixFactory.CreateSparseIdentityMatrix", "PythonSharp.SciPy.sp.Sparse.Eye")]
    [InlineTemplate("_scipy_sparse.eye({0}, format='csr')")]
    public static extern CompressedSparseRowMatrix<double> eye(int m);
}

[SurfaceLevel(2)]
[MapsTo("_scipy_stats")]
public static primitive class StatsModule
{
    [CanonicalApi("PythonSharp.Scientific.StatisticalAnalysis.ComputePearsonCorrelation", "PythonSharp.SciPy.sp.Stats.PearsonR")]
    [InlineTemplate("_scipy_stats.pearsonr({0}, {1})")]
    public static extern (double statistic, double pvalue) pearsonr(NDArray<double> x, NDArray<double> y);

    [CanonicalApi("PythonSharp.Scientific.StatisticalAnalysis.ComputeZScoreNormalized", "PythonSharp.SciPy.sp.Stats.ZScore")]
    [InlineTemplate("_scipy_stats.zscore({0})")]
    public static extern NDArray<double> zscore(NDArray<double> a);
}

[SurfaceLevel(2)]
public static primitive class scipy
{
    [InlineTemplate("_scipy_opt")]
    public static extern OptimizeModule optimize { get; }

    [InlineTemplate("_scipy_linalg")]
    public static extern LinalgModule linalg { get; }

    [InlineTemplate("_scipy_fft")]
    public static extern FftModule fft { get; }

    [InlineTemplate("_scipy_sparse")]
    public static extern SparseModule sparse { get; }

    [InlineTemplate("_scipy_stats")]
    public static extern StatsModule stats { get; }
}

```

### `stdlib/02_scientific_and_ai/02_scipy/02_scipy.csharp.d.ps`

```csharp
namespace PythonSharp.SciPy;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.Scientific;
extern using scipy.optimize as _scipy_opt;
extern using scipy.linalg as _scipy_linalg;
extern using scipy.fft as _scipy_fft;
extern using scipy.sparse as _scipy_sparse;
extern using scipy.stats as _scipy_stats;

[SurfaceLevel(3)]
[MapsTo("_scipy_opt")]
public static primitive class SciPyOptimizeModule
{
    [CanonicalApi("PythonSharp.Scientific.FunctionMinimizer.MinimizeScalarFunction")]
    [InlineTemplate("_scipy_opt.minimize({0}, {1})")]
    public static extern OptimizationResult Minimize(object objectiveFunction, NDArray<double> initialGuess);

    [CanonicalApi("PythonSharp.Scientific.FunctionMinimizer.MinimizeScalarFunctionWithMethod")]
    [InlineTemplate("_scipy_opt.minimize({0}, {1}, method={2})")]
    public static extern OptimizationResult Minimize(object objectiveFunction, NDArray<double> initialGuess, string solverMethod);

    [CanonicalApi("PythonSharp.Scientific.FunctionMinimizer.FindScalarRoot")]
    [InlineTemplate("_scipy_opt.root({0}, {1})")]
    public static extern OptimizationResult Root(object equationFunction, NDArray<double> initialGuess);
}

[SurfaceLevel(3)]
[MapsTo("_scipy_linalg")]
public static primitive class SciPyLinearAlgebraModule
{
    [CanonicalApi("PythonSharp.Scientific.MatrixDecompositions.ComputeLuDecomposition")]
    [InlineTemplate("_scipy_linalg.lu({0})")]
    public static extern (NDArray<double> Permutation, NDArray<double> Lower, NDArray<double> Upper) Lu(NDArray<double> matrix);

    [CanonicalApi("PythonSharp.Scientific.MatrixDecompositions.ComputeCholeskyDecomposition")]
    [InlineTemplate("_scipy_linalg.cholesky({0})")]
    public static extern NDArray<double> Cholesky(NDArray<double> matrix);

    [CanonicalApi("PythonSharp.Scientific.MatrixDecompositions.ComputeSingularValueDecomposition")]
    [InlineTemplate("_scipy_linalg.svd({0})")]
    public static extern (NDArray<double> U, NDArray<double> SingularValues, NDArray<double> Vh) Svd(NDArray<double> matrix);

    [CanonicalApi("PythonSharp.Scientific.MatrixDecompositions.SolveLinearSystem")]
    [InlineTemplate("_scipy_linalg.solve({0}, {1})")]
    public static extern NDArray<double> Solve(NDArray<double> matrixA, NDArray<double> vectorB);
}

[SurfaceLevel(3)]
[MapsTo("_scipy_fft")]
public static primitive class SciPyFftModule
{
    [CanonicalApi("PythonSharp.Scientific.FourierTransform.ComputeFastFourierTransform")]
    [InlineTemplate("_scipy_fft.fft({0})")]
    public static extern NDArray<double> Fft1D(NDArray<double> signal);

    [CanonicalApi("PythonSharp.Scientific.FourierTransform.ComputeInverseFastFourierTransform")]
    [InlineTemplate("_scipy_fft.ifft({0})")]
    public static extern NDArray<double> Ifft1D(NDArray<double> spectrum);

    [CanonicalApi("PythonSharp.Scientific.FourierTransform.ComputeRealFastFourierTransform")]
    [InlineTemplate("_scipy_fft.rfft({0})")]
    public static extern NDArray<double> Rfft1D(NDArray<double> realSignal);
}

[SurfaceLevel(3)]
[MapsTo("_scipy_sparse")]
public static primitive class SciPySparseModule
{
    [CanonicalApi("PythonSharp.Scientific.SparseMatrixFactory.CreateCompressedSparseRowMatrix")]
    [InlineTemplate("_scipy_sparse.csr_matrix({0})")]
    public static extern CompressedSparseRowMatrix<double> CsrMatrix(NDArray<double> denseMatrix);

    [CanonicalApi("PythonSharp.Scientific.SparseMatrixFactory.CreateSparseIdentityMatrix")]
    [InlineTemplate("_scipy_sparse.eye({0}, format='csr')")]
    public static extern CompressedSparseRowMatrix<double> Eye(int dimensionSize);
}

[SurfaceLevel(3)]
[MapsTo("_scipy_stats")]
public static primitive class SciPyStatsModule
{
    [CanonicalApi("PythonSharp.Scientific.StatisticalAnalysis.ComputePearsonCorrelation")]
    [InlineTemplate("_scipy_stats.pearsonr({0}, {1})")]
    public static extern (double Correlation, double PValue) PearsonR(NDArray<double> x, NDArray<double> y);

    [CanonicalApi("PythonSharp.Scientific.StatisticalAnalysis.ComputeZScoreNormalized")]
    [InlineTemplate("_scipy_stats.zscore({0})")]
    public static extern NDArray<double> ZScore(NDArray<double> values);
}

[SurfaceLevel(3)]
public static primitive class sp
{
    [InlineTemplate("_scipy_opt")]
    public static extern SciPyOptimizeModule Optimize { get; }

    [InlineTemplate("_scipy_linalg")]
    public static extern SciPyLinearAlgebraModule LinearAlgebra { get; }

    [InlineTemplate("_scipy_fft")]
    public static extern SciPyFftModule Fft { get; }

    [InlineTemplate("_scipy_sparse")]
    public static extern SciPySparseModule Sparse { get; }

    [InlineTemplate("_scipy_stats")]
    public static extern SciPyStatsModule Stats { get; }
}

```

### `stdlib/02_scientific_and_ai/02_scipy/03_scientific.enterprise.d.ps`

```csharp
namespace PythonSharp.Scientific;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using scipy.optimize as _scipy_opt;
extern using scipy.linalg as _scipy_linalg;
extern using scipy.fft as _scipy_fft;
extern using scipy.sparse as _scipy_sparse;
extern using scipy.stats as _scipy_stats;

[SurfaceLevel(1)]
[MapsTo("_scipy_opt")]
public static primitive class FunctionMinimizer
{
    [InlineTemplate("_scipy_opt.minimize({0}, {1})")]
    public static extern OptimizationResult MinimizeScalarFunction(object objectiveFunction, NDArray<double> initialGuessVector);

    [InlineTemplate("_scipy_opt.minimize({0}, {1}, method={2})")]
    public static extern OptimizationResult MinimizeScalarFunctionWithMethod(object objectiveFunction, NDArray<double> initialGuessVector, string solverAlgorithm);

    [InlineTemplate("_scipy_opt.root({0}, {1})")]
    public static extern OptimizationResult FindScalarRoot(object systemFunction, NDArray<double> initialGuessVector);
}

[SurfaceLevel(1)]
[MapsTo("_scipy_linalg")]
public static primitive class MatrixDecompositions
{
    [InlineTemplate("_scipy_linalg.lu({0})")]
    public static extern (NDArray<double> PermutationMatrix, NDArray<double> LowerTriangular, NDArray<double> UpperTriangular) ComputeLuDecomposition(NDArray<double> squareMatrix);

    [InlineTemplate("_scipy_linalg.cholesky({0})")]
    public static extern NDArray<double> ComputeCholeskyDecomposition(NDArray<double> symmetricPositiveDefiniteMatrix);

    [InlineTemplate("_scipy_linalg.svd({0})")]
    public static extern (NDArray<double> LeftSingularVectors, NDArray<double> SingularValues, NDArray<double> RightSingularVectorsTransposed) ComputeSingularValueDecomposition(NDArray<double> matrix);

    [InlineTemplate("_scipy_linalg.solve({0}, {1})")]
    public static extern NDArray<double> SolveLinearSystem(NDArray<double> coefficientMatrixA, NDArray<double> dependentVectorB);
}

[SurfaceLevel(1)]
[MapsTo("_scipy_fft")]
public static primitive class FourierTransform
{
    [InlineTemplate("_scipy_fft.fft({0})")]
    public static extern NDArray<double> ComputeFastFourierTransform(NDArray<double> timeDomainSignal);

    [InlineTemplate("_scipy_fft.ifft({0})")]
    public static extern NDArray<double> ComputeInverseFastFourierTransform(NDArray<double> frequencySpectrum);

    [InlineTemplate("_scipy_fft.rfft({0})")]
    public static extern NDArray<double> ComputeRealFastFourierTransform(NDArray<double> realTimeDomainSignal);
}

[SurfaceLevel(1)]
[MapsTo("_scipy_sparse")]
public static primitive class SparseMatrixFactory
{
    [InlineTemplate("_scipy_sparse.csr_matrix({0})")]
    public static extern CompressedSparseRowMatrix<double> CreateCompressedSparseRowMatrix(NDArray<double> denseMatrix);

    [InlineTemplate("_scipy_sparse.eye({0}, format='csr')")]
    public static extern CompressedSparseRowMatrix<double> CreateSparseIdentityMatrix(int dimensionSize);
}

[SurfaceLevel(1)]
[MapsTo("_scipy_stats")]
public static primitive class StatisticalAnalysis
{
    [InlineTemplate("_scipy_stats.pearsonr({0}, {1})")]
    public static extern (double CorrelationCoefficient, double TwoTailedPValue) ComputePearsonCorrelation(NDArray<double> sampleX, NDArray<double> sampleY);

    [InlineTemplate("_scipy_stats.zscore({0})")]
    public static extern NDArray<double> ComputeZScoreNormalized(NDArray<double> sampleValues);
}

```

---

## 2. `03_pandas` (Schema-Checked Tabular DataFrames & Series)

`03_pandas` exposes `Series<T>`, `GroupByClause<TRow>`, and schema-checked `DataFrame<TRow>` alongside `pandas` (Surface 2), `PythonSharp.Pandas` (Surface 3), and `PythonSharp.DataScience.Tabular` (Surface 1).

### `stdlib/02_scientific_and_ai/03_pandas/00_pandas.primitives.d.ps`

```csharp
namespace PythonSharp.DataScience.Tabular;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using pandas as pd;

[MapsTo("pd.Series")]
[RuntimeType("pd.Series")]
public primitive class Series<T> : IEnumerable<T>
{
    // --- Surface 1: Self-Documenting Enterprise Properties & Methods ---
    [InlineTemplate("len({self})")]
    public extern int RowCount { get; }

    [MapsTo("to_numpy")]
    public extern NDArray<T> ConvertToNumPyArray();

    [MapsTo("tolist")]
    public extern List<T> ConvertToList();

    [MapsTo("mean")]
    public extern double ComputeArithmeticMean();

    [MapsTo("std")]
    public extern double ComputeStandardDeviation();

    [MapsTo("sum")]
    public extern T ComputeSum();

    [MapsTo("min")]
    public extern T FindMinimumValue();

    [MapsTo("max")]
    public extern T FindMaximumValue();

    [MapsTo("fillna")]
    public extern Series<T> FillMissingValues(T replacementValue);

    [MapsTo("dropna")]
    public extern Series<T> DropMissingValues();

    // --- Surface 3: C#-Standardized Properties & Methods ---
    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.RowCount")]
    [InlineTemplate("len({self})")]
    public extern int Count { get; }

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ConvertToNumPyArray")]
    [MapsTo("to_numpy")]
    public extern NDArray<T> ToNumpy();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ConvertToList")]
    [MapsTo("tolist")]
    public extern List<T> ToList();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ComputeArithmeticMean")]
    [MapsTo("mean")]
    public extern double Mean();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ComputeStandardDeviation")]
    [MapsTo("std")]
    public extern double Std();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ComputeSum")]
    [MapsTo("sum")]
    public extern T Sum();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.FindMinimumValue")]
    [MapsTo("min")]
    public extern T Min();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.FindMaximumValue")]
    [MapsTo("max")]
    public extern T Max();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.FillMissingValues")]
    [MapsTo("fillna")]
    public extern Series<T> FillNa(T value);

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.DropMissingValues")]
    [MapsTo("dropna")]
    public extern Series<T> DropNa();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ConvertToNumPyArray", "ToNumpy")]
    [MapsTo("to_numpy")]
    public extern NDArray<T> to_numpy();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ConvertToList", "ToList")]
    [MapsTo("tolist")]
    public extern List<T> tolist();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ComputeArithmeticMean", "Mean")]
    [MapsTo("mean")]
    public extern double mean();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ComputeStandardDeviation", "Std")]
    [MapsTo("std")]
    public extern double std();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.ComputeSum", "Sum")]
    [MapsTo("sum")]
    public extern T sum();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.FindMinimumValue", "Min")]
    [MapsTo("min")]
    public extern T min();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.FindMaximumValue", "Max")]
    [MapsTo("max")]
    public extern T max();

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.FillMissingValues", "FillNa")]
    [MapsTo("fillna")]
    public extern Series<T> fillna(T value);

    [CanonicalApi("PythonSharp.DataScience.Tabular.Series.DropMissingValues", "DropNa")]
    [MapsTo("dropna")]
    public extern Series<T> dropna();

    [InlineTemplate("{self}[{0}]")]
    public extern T this[int index] { get; set; }
}

[MapsTo("pd.core.groupby.DataFrameGroupBy")]
[RuntimeType("object")]
public primitive class GroupByClause<TRow>
{
    [MapsTo("mean")]
    public extern DataFrame<TRow> AggregateByMean();

    [CanonicalApi("PythonSharp.DataScience.Tabular.GroupByClause.AggregateByMean")]
    [MapsTo("mean")]
    public extern DataFrame<TRow> Mean();

    [CanonicalApi("PythonSharp.DataScience.Tabular.GroupByClause.AggregateByMean", "Mean")]
    [MapsTo("mean")]
    public extern DataFrame<TRow> mean();

    [MapsTo("sum")]
    public extern DataFrame<TRow> AggregateBySum();

    [CanonicalApi("PythonSharp.DataScience.Tabular.GroupByClause.AggregateBySum")]
    [MapsTo("sum")]
    public extern DataFrame<TRow> Sum();

    [CanonicalApi("PythonSharp.DataScience.Tabular.GroupByClause.AggregateBySum", "Sum")]
    [MapsTo("sum")]
    public extern DataFrame<TRow> sum();

    [MapsTo("count")]
    public extern DataFrame<TRow> AggregateByCount();

    [CanonicalApi("PythonSharp.DataScience.Tabular.GroupByClause.AggregateByCount")]
    [MapsTo("count")]
    public extern DataFrame<TRow> Count();

    [CanonicalApi("PythonSharp.DataScience.Tabular.GroupByClause.AggregateByCount", "Count")]
    [MapsTo("count")]
    public extern DataFrame<TRow> count();
}

[MapsTo("pd.DataFrame")]
[RuntimeType("pd.DataFrame")]
public primitive class DataFrame<TRow>
{
    // --- Triple-Surface Properties ---
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) TableDimensions { get; }

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.TableDimensions")]
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) Shape { get; }

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.TableDimensions", "Shape")]
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) shape { get; }

    [InlineTemplate("list({self}.columns)")]
    public extern List<string> ColumnNames { get; }

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ColumnNames")]
    [InlineTemplate("list({self}.columns)")]
    public extern List<string> Columns { get; }

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ColumnNames", "Columns")]
    [InlineTemplate("list({self}.columns)")]
    public extern List<string> columns { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("dropna")]
    public extern DataFrame<TRow> DropRowsWithMissingValues();

    [MapsTo("fillna")]
    public extern DataFrame<TRow> FillMissingValuesWith(object replacementValue);

    [MapsTo("head")]
    public extern DataFrame<TRow> TakeFirstRows(int rowCount = 5);

    [MapsTo("tail")]
    public extern DataFrame<TRow> TakeLastRows(int rowCount = 5);

    [MapsTo("groupby")]
    public extern GroupByClause<TRow> GroupRowsByColumn(string columnName);

    [MapsTo("sort_values")]
    public extern DataFrame<TRow> SortRowsByColumn(string byColumn, bool ascending = true);

    [MapsTo("to_numpy")]
    public extern NDArray<double> ConvertToFeatureMatrix();

    [MapsTo("to_csv")]
    public extern void ExportToCsvFile(string filePath, bool includeIndex = false);

    [MapsTo("describe")]
    public extern DataFrame<object> ComputeSummaryStatistics();

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.DropRowsWithMissingValues")]
    [MapsTo("dropna")]
    public extern DataFrame<TRow> DropNa();

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.FillMissingValuesWith")]
    [MapsTo("fillna")]
    public extern DataFrame<TRow> FillNa(object value);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.TakeFirstRows")]
    [MapsTo("head")]
    public extern DataFrame<TRow> Head(int n = 5);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.TakeLastRows")]
    [MapsTo("tail")]
    public extern DataFrame<TRow> Tail(int n = 5);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.GroupRowsByColumn")]
    [MapsTo("groupby")]
    public extern GroupByClause<TRow> GroupBy(string by);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.SortRowsByColumn")]
    [MapsTo("sort_values")]
    public extern DataFrame<TRow> SortValues(string by, bool ascending = true);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ConvertToFeatureMatrix")]
    [MapsTo("to_numpy")]
    public extern NDArray<double> ToNumpy();

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ExportToCsvFile")]
    [InlineTemplate("{self}.to_csv({0}, index={1})")]
    public extern void ToCsv(string path, bool index = false);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ComputeSummaryStatistics")]
    [MapsTo("describe")]
    public extern DataFrame<object> Describe();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.DropRowsWithMissingValues", "DropNa")]
    [MapsTo("dropna")]
    public extern DataFrame<TRow> dropna();

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.FillMissingValuesWith", "FillNa")]
    [MapsTo("fillna")]
    public extern DataFrame<TRow> fillna(object value);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.TakeFirstRows", "Head")]
    [MapsTo("head")]
    public extern DataFrame<TRow> head(int n = 5);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.TakeLastRows", "Tail")]
    [MapsTo("tail")]
    public extern DataFrame<TRow> tail(int n = 5);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.GroupRowsByColumn", "GroupBy")]
    [MapsTo("groupby")]
    public extern GroupByClause<TRow> groupby(string by);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.SortRowsByColumn", "SortValues")]
    [MapsTo("sort_values")]
    public extern DataFrame<TRow> sort_values(string by, bool ascending = true);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ConvertToFeatureMatrix", "ToNumpy")]
    [MapsTo("to_numpy")]
    public extern NDArray<double> to_numpy();

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ExportToCsvFile", "ToCsv")]
    [InlineTemplate("{self}.to_csv({0}, index={1})")]
    public extern void to_csv(string path, bool index = false);

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ComputeSummaryStatistics", "Describe")]
    [MapsTo("describe")]
    public extern DataFrame<object> describe();

    // --- Column Indexing ---
    [InlineTemplate("{self}[{0}]")]
    public extern Series<double> this[string columnName]
    {
        get;
        [InlineTemplate("{self}[{0}] = {value}")] set;
    }

    [InlineTemplate("{self}[{0}]")]
    public extern DataFrame<TRow> this[List<string> columnNames] { get; }
}

```

### `stdlib/02_scientific_and_ai/03_pandas/01_pandas.raw.d.ps`

```csharp
namespace pandas;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DataScience.Tabular;
extern using pandas as pd;

[SurfaceLevel(2)]
[MapsTo("pd")]
public static primitive class pd
{
    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadCsvFile", "PythonSharp.Pandas.pd.ReadCsv")]
    [InlineTemplate("pd.read_csv({0})")]
    public static extern DataFrame<object> read_csv(string filepath_or_buffer);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadParquetFile", "PythonSharp.Pandas.pd.ReadParquet")]
    [InlineTemplate("pd.read_parquet({0})")]
    public static extern DataFrame<object> read_parquet(string path);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadJsonFile", "PythonSharp.Pandas.pd.ReadJson")]
    [InlineTemplate("pd.read_json({0})")]
    public static extern DataFrame<object> read_json(string path_or_buf);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataFactory.CreateDataFrameFromDictionary", "PythonSharp.Pandas.pd.FromDict")]
    [InlineTemplate("pd.DataFrame({0})")]
    public static extern DataFrame<object> DataFrame(object data);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataFactory.CreateSeriesFromSequence", "PythonSharp.Pandas.pd.CreateSeries")]
    [InlineTemplate("pd.Series({0})")]
    public static extern Series<T> Series<T>(IEnumerable<T> data);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularOperations.ConcatenateDataFrames", "PythonSharp.Pandas.pd.Concat")]
    [InlineTemplate("pd.concat({0}, axis={1})")]
    public static extern DataFrame<TRow> concat<TRow>(IEnumerable<DataFrame<TRow>> objs, int axis = 0);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularOperations.MergeDataFramesOnKey", "PythonSharp.Pandas.pd.Merge")]
    [InlineTemplate("pd.merge({0}, {1}, on={2}, how={3})")]
    public static extern DataFrame<object> merge<TLeft, TRight>(DataFrame<TLeft> left, DataFrame<TRight> right, string on, string how = "inner");
}

```

### `stdlib/02_scientific_and_ai/03_pandas/02_pandas.csharp.d.ps`

```csharp
namespace PythonSharp.Pandas;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DataScience.Tabular;
extern using pandas as _pd;

[SurfaceLevel(3)]
[MapsTo("_pd")]
public static primitive class pd
{
    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadCsvFile")]
    [InlineTemplate("_pd.read_csv({0})")]
    public static extern DataFrame<TRow> ReadCsv<TRow>(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadCsvFile")]
    [InlineTemplate("_pd.read_csv({0})")]
    public static extern DataFrame<object> ReadCsv(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadParquetFile")]
    [InlineTemplate("_pd.read_parquet({0})")]
    public static extern DataFrame<TRow> ReadParquet<TRow>(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadJsonFile")]
    [InlineTemplate("_pd.read_json({0})")]
    public static extern DataFrame<TRow> ReadJson<TRow>(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataFactory.CreateDataFrameFromDictionary")]
    [InlineTemplate("_pd.DataFrame({0})")]
    public static extern DataFrame<TRow> FromDict<TRow>(object columnDictionary);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataFactory.CreateSeriesFromSequence")]
    [InlineTemplate("_pd.Series({0})")]
    public static extern Series<T> CreateSeries<T>(IEnumerable<T> values);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularOperations.ConcatenateDataFrames")]
    [InlineTemplate("_pd.concat({0}, axis={1})")]
    public static extern DataFrame<TRow> Concat<TRow>(IEnumerable<DataFrame<TRow>> frames, int axis = 0);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularOperations.MergeDataFramesOnKey")]
    [InlineTemplate("_pd.merge({0}, {1}, on={2}, how={3})")]
    public static extern DataFrame<object> Merge<TLeft, TRight>(DataFrame<TLeft> left, DataFrame<TRight> right, string onColumn, string joinHow = "inner");
}

```

### `stdlib/02_scientific_and_ai/03_pandas/03_tabular.enterprise.d.ps`

```csharp
namespace PythonSharp.DataScience.Tabular;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using pandas as _pd;

[SurfaceLevel(1)]
[MapsTo("_pd")]
public static primitive class TabularDataReader
{
    [InlineTemplate("_pd.read_csv({0})")]
    public static extern DataFrame<TRow> ReadCsvFile<TRow>(string csvFilePath);

    [InlineTemplate("_pd.read_csv({0})")]
    public static extern DataFrame<object> ReadUntypedCsvFile(string csvFilePath);

    [InlineTemplate("_pd.read_parquet({0})")]
    public static extern DataFrame<TRow> ReadParquetFile<TRow>(string parquetFilePath);

    [InlineTemplate("_pd.read_json({0})")]
    public static extern DataFrame<TRow> ReadJsonFile<TRow>(string jsonFilePath);
}

[SurfaceLevel(1)]
[MapsTo("_pd")]
public static primitive class TabularDataFactory
{
    [InlineTemplate("_pd.DataFrame({0})")]
    public static extern DataFrame<TRow> CreateDataFrameFromDictionary<TRow>(object columnDictionary);

    [InlineTemplate("_pd.DataFrame({0}, columns={1})")]
    public static extern DataFrame<TRow> CreateDataFrameFromMatrix<TRow>(NDArray<double> featureMatrix, List<string> columnNames);

    [InlineTemplate("_pd.Series({0})")]
    public static extern Series<T> CreateSeriesFromSequence<T>(IEnumerable<T> items);
}

[SurfaceLevel(1)]
[MapsTo("_pd")]
public static primitive class TabularOperations
{
    [InlineTemplate("_pd.concat({0}, axis={1})")]
    public static extern DataFrame<TRow> ConcatenateDataFrames<TRow>(IEnumerable<DataFrame<TRow>> tables, int concatenationAxis = 0);

    [InlineTemplate("_pd.merge({0}, {1}, on={2}, how={3})")]
    public static extern DataFrame<object> MergeDataFramesOnKey<TLeft, TRight>(DataFrame<TLeft> leftTable, DataFrame<TRight> rightTable, string keyColumnName, string joinStrategy = "inner");
}

```

---

## 3. `04_matplotlib_seaborn` (Scientific Plotting & Statistical Visualization)

`04_matplotlib_seaborn` depends on both `PythonSharp.Numerics.Tensors` (`01_numpy`) and `PythonSharp.DataScience.Tabular` (`03_pandas`), mapping `matplotlib.pyplot` and `seaborn` across all three surfaces.

### `stdlib/02_scientific_and_ai/04_matplotlib_seaborn/00_viz.primitives.d.ps`

```csharp
namespace PythonSharp.Visualization;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using matplotlib.pyplot as _plt;

[MapsTo("matplotlib.figure.Figure")]
[RuntimeType("object")]
public primitive class PlotFigure
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("savefig")]
    public extern void SaveFigureToFile(string outputFilePath, int dotsPerInch = 150);

    [MapsTo("tight_layout")]
    public extern void ApplyTightLayout();

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.Visualization.PlotFigure.SaveFigureToFile")]
    [InlineTemplate("{self}.savefig({0}, dpi={1})")]
    public extern void SaveFig(string path, int dpi = 150);

    [CanonicalApi("PythonSharp.Visualization.PlotFigure.ApplyTightLayout")]
    [MapsTo("tight_layout")]
    public extern void TightLayout();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.Visualization.PlotFigure.SaveFigureToFile", "SaveFig")]
    [InlineTemplate("{self}.savefig({0}, dpi={1})")]
    public extern void savefig(string fname, int dpi = 150);

    [CanonicalApi("PythonSharp.Visualization.PlotFigure.ApplyTightLayout", "TightLayout")]
    [MapsTo("tight_layout")]
    public extern void tight_layout();
}

[MapsTo("matplotlib.axes.Axes")]
[RuntimeType("object")]
public primitive class PlotAxes
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("plot")]
    public extern void PlotLineSeries(NDArray<double> xCoordinates, NDArray<double> yCoordinates, string? seriesLabel = null);

    [MapsTo("scatter")]
    public extern void PlotScatterPoints(NDArray<double> xCoordinates, NDArray<double> yCoordinates, string? seriesLabel = null);

    [MapsTo("set_title")]
    public extern void SetAxesTitle(string titleText);

    [MapsTo("set_xlabel")]
    public extern void SetHorizontalAxisLabel(string labelText);

    [MapsTo("set_ylabel")]
    public extern void SetVerticalAxisLabel(string labelText);

    [MapsTo("legend")]
    public extern void EnableLegend();

    [InlineTemplate("{self}.grid({0})")]
    public extern void SetGridVisibility(bool visible = true);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.Visualization.PlotAxes.PlotLineSeries")]
    [InlineTemplate("{self}.plot({0}, {1}, label={2})")]
    public extern void Plot(NDArray<double> x, NDArray<double> y, string? label = null);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.PlotScatterPoints")]
    [InlineTemplate("{self}.scatter({0}, {1}, label={2})")]
    public extern void Scatter(NDArray<double> x, NDArray<double> y, string? label = null);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.SetAxesTitle")]
    [MapsTo("set_title")]
    public extern void SetTitle(string title);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.SetHorizontalAxisLabel")]
    [MapsTo("set_xlabel")]
    public extern void SetXLabel(string label);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.SetVerticalAxisLabel")]
    [MapsTo("set_ylabel")]
    public extern void SetYLabel(string label);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.EnableLegend")]
    [MapsTo("legend")]
    public extern void Legend();

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.SetGridVisibility")]
    [InlineTemplate("{self}.grid({0})")]
    public extern void Grid(bool visible = true);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.Visualization.PlotAxes.PlotLineSeries", "Plot")]
    [InlineTemplate("{self}.plot({0}, {1}, label={2})")]
    public extern void plot(NDArray<double> x, NDArray<double> y, string? label = null);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.PlotScatterPoints", "Scatter")]
    [InlineTemplate("{self}.scatter({0}, {1}, label={2})")]
    public extern void scatter(NDArray<double> x, NDArray<double> y, string? label = null);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.SetAxesTitle", "SetTitle")]
    [MapsTo("set_title")]
    public extern void set_title(string label);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.SetHorizontalAxisLabel", "SetXLabel")]
    [MapsTo("set_xlabel")]
    public extern void set_xlabel(string xlabel);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.SetVerticalAxisLabel", "SetYLabel")]
    [MapsTo("set_ylabel")]
    public extern void set_ylabel(string ylabel);

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.EnableLegend", "Legend")]
    [MapsTo("legend")]
    public extern void legend();

    [CanonicalApi("PythonSharp.Visualization.PlotAxes.SetGridVisibility", "Grid")]
    [InlineTemplate("{self}.grid({0})")]
    public extern void grid(bool visible = true);
}

```

### `stdlib/02_scientific_and_ai/04_matplotlib_seaborn/01_viz.raw.d.ps`

```csharp
namespace matplotlib;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DataScience.Tabular;
using PythonSharp.Visualization;
extern using matplotlib.pyplot as _plt;
extern using seaborn as _sns;

[SurfaceLevel(2)]
[MapsTo("_plt")]
public static primitive class plt
{
    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.CreateFigureAndAxes", "PythonSharp.Matplotlib.plt.Subplots")]
    [InlineTemplate("_plt.subplots(figsize={0})")]
    public static extern (PlotFigure fig, PlotAxes ax) subplots((int, int)? figsize = null);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.PlotLineSeries", "PythonSharp.Matplotlib.plt.Plot")]
    [InlineTemplate("_plt.plot({0}, {1}, label={2})")]
    public static extern void plot(NDArray<double> x, NDArray<double> y, string? label = null);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.PlotScatterSeries", "PythonSharp.Matplotlib.plt.Scatter")]
    [InlineTemplate("_plt.scatter({0}, {1}, label={2})")]
    public static extern void scatter(NDArray<double> x, NDArray<double> y, string? label = null);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.PlotHistogram", "PythonSharp.Matplotlib.plt.Hist")]
    [InlineTemplate("_plt.hist({0}, bins={1})")]
    public static extern void hist(NDArray<double> x, int bins = 20);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.SetChartTitle", "PythonSharp.Matplotlib.plt.Title")]
    [InlineTemplate("_plt.title({0})")]
    public static extern void title(string label);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.SetHorizontalAxisLabel", "PythonSharp.Matplotlib.plt.XLabel")]
    [InlineTemplate("_plt.xlabel({0})")]
    public static extern void xlabel(string xlabel);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.SetVerticalAxisLabel", "PythonSharp.Matplotlib.plt.YLabel")]
    [InlineTemplate("_plt.ylabel({0})")]
    public static extern void ylabel(string ylabel);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.ShowLegend", "PythonSharp.Matplotlib.plt.Legend")]
    [InlineTemplate("_plt.legend()")]
    public static extern void legend();

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.SaveChartToFile", "PythonSharp.Matplotlib.plt.SaveFig")]
    [InlineTemplate("_plt.savefig({0}, dpi={1})")]
    public static extern void savefig(string fname, int dpi = 150);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.DisplayInteractiveChart", "PythonSharp.Matplotlib.plt.Show")]
    [InlineTemplate("_plt.show()")]
    public static extern void show();

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.CloseCurrentFigure", "PythonSharp.Matplotlib.plt.Close")]
    [InlineTemplate("_plt.close()")]
    public static extern void close();
}

[SurfaceLevel(2)]
[MapsTo("_sns")]
public static primitive class sns
{
    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.SetVisualTheme", "PythonSharp.Matplotlib.sns.SetTheme")]
    [InlineTemplate("_sns.set_theme(style={0})")]
    public static extern void set_theme(string style = "whitegrid");

    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.RenderCorrelationHeatmap", "PythonSharp.Matplotlib.sns.Heatmap")]
    [InlineTemplate("_sns.heatmap({0}, annot={1}, cmap={2})")]
    public static extern PlotAxes heatmap(NDArray<double> data, bool annot = true, string cmap = "viridis");

    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.RenderDataFrameHeatmap", "PythonSharp.Matplotlib.sns.Heatmap")]
    [InlineTemplate("_sns.heatmap({0}, annot={1}, cmap={2})")]
    public static extern PlotAxes heatmap<TRow>(DataFrame<TRow> data, bool annot = true, string cmap = "viridis");

    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.RenderDistributionHistogram", "PythonSharp.Matplotlib.sns.HistPlot")]
    [InlineTemplate("_sns.histplot({0}, kde={1})")]
    public static extern PlotAxes histplot(NDArray<double> data, bool kde = true);

    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.RenderBoxPlot", "PythonSharp.Matplotlib.sns.BoxPlot")]
    [InlineTemplate("_sns.boxplot(data={0}, x={1}, y={2})")]
    public static extern PlotAxes boxplot<TRow>(DataFrame<TRow> data, string x, string y);
}

```

### `stdlib/02_scientific_and_ai/04_matplotlib_seaborn/02_viz.csharp.d.ps`

```csharp
namespace PythonSharp.Matplotlib;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DataScience.Tabular;
using PythonSharp.Visualization;
extern using matplotlib.pyplot as _plt;
extern using seaborn as _sns;

[SurfaceLevel(3)]
[MapsTo("_plt")]
public static primitive class plt
{
    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.CreateFigureAndAxes")]
    [InlineTemplate("_plt.subplots(figsize=({0}, {1}))")]
    public static extern (PlotFigure Figure, PlotAxes Axes) Subplots(int widthInches = 8, int heightInches = 6);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.PlotLineSeries")]
    [InlineTemplate("_plt.plot({0}, {1}, label={2})")]
    public static extern void Plot(NDArray<double> x, NDArray<double> y, string? label = null);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.PlotScatterSeries")]
    [InlineTemplate("_plt.scatter({0}, {1}, label={2})")]
    public static extern void Scatter(NDArray<double> x, NDArray<double> y, string? label = null);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.PlotHistogram")]
    [InlineTemplate("_plt.hist({0}, bins={1})")]
    public static extern void Hist(NDArray<double> values, int bins = 20);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.SetChartTitle")]
    [InlineTemplate("_plt.title({0})")]
    public static extern void Title(string text);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.SetHorizontalAxisLabel")]
    [InlineTemplate("_plt.xlabel({0})")]
    public static extern void XLabel(string text);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.SetVerticalAxisLabel")]
    [InlineTemplate("_plt.ylabel({0})")]
    public static extern void YLabel(string text);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.ShowLegend")]
    [InlineTemplate("_plt.legend()")]
    public static extern void Legend();

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.SaveChartToFile")]
    [InlineTemplate("_plt.savefig({0}, dpi={1})")]
    public static extern void SaveFig(string filePath, int dpi = 150);

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.DisplayInteractiveChart")]
    [InlineTemplate("_plt.show()")]
    public static extern void Show();

    [CanonicalApi("PythonSharp.Visualization.FigureCanvas.CloseCurrentFigure")]
    [InlineTemplate("_plt.close()")]
    public static extern void Close();
}

[SurfaceLevel(3)]
[MapsTo("_sns")]
public static primitive class sns
{
    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.SetVisualTheme")]
    [InlineTemplate("_sns.set_theme(style={0})")]
    public static extern void SetTheme(string style = "whitegrid");

    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.RenderCorrelationHeatmap")]
    [InlineTemplate("_sns.heatmap({0}, annot={1}, cmap={2})")]
    public static extern PlotAxes Heatmap(NDArray<double> matrix, bool annotate = true, string colorMap = "viridis");

    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.RenderDataFrameHeatmap")]
    [InlineTemplate("_sns.heatmap({0}, annot={1}, cmap={2})")]
    public static extern PlotAxes Heatmap<TRow>(DataFrame<TRow> frame, bool annotate = true, string colorMap = "viridis");

    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.RenderDistributionHistogram")]
    [InlineTemplate("_sns.histplot({0}, kde={1})")]
    public static extern PlotAxes HistPlot(NDArray<double> values, bool showKernelDensity = true);

    [CanonicalApi("PythonSharp.Visualization.StatisticalPlotter.RenderBoxPlot")]
    [InlineTemplate("_sns.boxplot(data={0}, x={1}, y={2})")]
    public static extern PlotAxes BoxPlot<TRow>(DataFrame<TRow> data, string xColumn, string yColumn);
}

```

### `stdlib/02_scientific_and_ai/04_matplotlib_seaborn/03_visualization.enterprise.d.ps`

```csharp
namespace PythonSharp.Visualization;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DataScience.Tabular;
extern using matplotlib.pyplot as _plt;
extern using seaborn as _sns;

[SurfaceLevel(1)]
[MapsTo("_plt")]
public static primitive class FigureCanvas
{
    [InlineTemplate("_plt.subplots(figsize=({0}, {1}))")]
    public static extern (PlotFigure Figure, PlotAxes Axes) CreateFigureAndAxes(int widthInches = 8, int heightInches = 6);

    [InlineTemplate("_plt.plot({0}, {1}, label={2})")]
    public static extern void PlotLineSeries(NDArray<double> xCoordinates, NDArray<double> yCoordinates, string? seriesLabel = null);

    [InlineTemplate("_plt.scatter({0}, {1}, label={2})")]
    public static extern void PlotScatterSeries(NDArray<double> xCoordinates, NDArray<double> yCoordinates, string? seriesLabel = null);

    [InlineTemplate("_plt.hist({0}, bins={1})")]
    public static extern void PlotHistogram(NDArray<double> sampleValues, int binCount = 20);

    [InlineTemplate("_plt.title({0})")]
    public static extern void SetChartTitle(string titleText);

    [InlineTemplate("_plt.xlabel({0})")]
    public static extern void SetHorizontalAxisLabel(string axisLabelText);

    [InlineTemplate("_plt.ylabel({0})")]
    public static extern void SetVerticalAxisLabel(string axisLabelText);

    [InlineTemplate("_plt.legend()")]
    public static extern void ShowLegend();

    [InlineTemplate("_plt.savefig({0}, dpi={1})")]
    public static extern void SaveChartToFile(string outputFilePath, int dotsPerInch = 150);

    [InlineTemplate("_plt.show()")]
    public static extern void DisplayInteractiveChart();

    [InlineTemplate("_plt.close()")]
    public static extern void CloseCurrentFigure();
}

[SurfaceLevel(1)]
[MapsTo("_sns")]
public static primitive class StatisticalPlotter
{
    [InlineTemplate("_sns.set_theme(style={0})")]
    public static extern void SetVisualTheme(string themeStyle = "whitegrid");

    [InlineTemplate("_sns.heatmap({0}, annot={1}, cmap={2})")]
    public static extern PlotAxes RenderCorrelationHeatmap(NDArray<double> correlationMatrix, bool annotateCells = true, string colorPalette = "viridis");

    [InlineTemplate("_sns.heatmap({0}, annot={1}, cmap={2})")]
    public static extern PlotAxes RenderDataFrameHeatmap<TRow>(DataFrame<TRow> table, bool annotateCells = true, string colorPalette = "viridis");

    [InlineTemplate("_sns.histplot({0}, kde={1})")]
    public static extern PlotAxes RenderDistributionHistogram(NDArray<double> sampleValues, bool overlayKernelDensityEstimate = true);

    [InlineTemplate("_sns.boxplot(data={0}, x={1}, y={2})")]
    public static extern PlotAxes RenderBoxPlot<TRow>(DataFrame<TRow> table, string categoryColumnName, string valueColumnName);
}

```

---

## 4. `05_sklearn` (Classical Machine Learning, Preprocessing, Models & Metrics)

`05_sklearn` provides `IFeatureTransformer<T>`, `ISupervisedEstimator<TFeature, TLabel>`, `StandardFeatureScaler`, `RandomForestClassifierModel`, `LogisticRegressionModel`, and `RidgeRegressionModel` across `sklearn` (Surface 2), `PythonSharp.ScikitLearn` (Surface 3), and `PythonSharp.MachineLearning.Classical` (Surface 1).

### `stdlib/02_scientific_and_ai/05_sklearn/00_sklearn.primitives.d.ps`

```csharp
namespace PythonSharp.MachineLearning.Classical;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using sklearn.preprocessing as _prep;
extern using sklearn.ensemble as _ens;
extern using sklearn.linear_model as _lin;

public primitive interface IFeatureTransformer<T>
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("fit")]
    void FitToFeatures(NDArray<T> featureMatrix);

    [MapsTo("transform")]
    NDArray<T> TransformFeatures(NDArray<T> featureMatrix);

    [MapsTo("fit_transform")]
    NDArray<T> FitAndTransformFeatures(NDArray<T> featureMatrix);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.MachineLearning.Classical.IFeatureTransformer.FitToFeatures")]
    [MapsTo("fit")]
    void Fit(NDArray<T> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.IFeatureTransformer.TransformFeatures")]
    [MapsTo("transform")]
    NDArray<T> Transform(NDArray<T> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.IFeatureTransformer.FitAndTransformFeatures")]
    [MapsTo("fit_transform")]
    NDArray<T> FitTransform(NDArray<T> X);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.MachineLearning.Classical.IFeatureTransformer.FitToFeatures", "Fit")]
    [MapsTo("fit")]
    void fit(NDArray<T> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.IFeatureTransformer.TransformFeatures", "Transform")]
    [MapsTo("transform")]
    NDArray<T> transform(NDArray<T> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.IFeatureTransformer.FitAndTransformFeatures", "FitTransform")]
    [MapsTo("fit_transform")]
    NDArray<T> fit_transform(NDArray<T> X);
}

public primitive interface ISupervisedEstimator<TFeature, TLabel>
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("fit")]
    void TrainOnLabeledDataset(NDArray<TFeature> featureMatrix, NDArray<TLabel> targetLabels);

    [MapsTo("predict")]
    NDArray<TLabel> PredictLabels(NDArray<TFeature> featureMatrix);

    [MapsTo("score")]
    double EvaluateModelScore(NDArray<TFeature> featureMatrix, NDArray<TLabel> groundTruthLabels);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.MachineLearning.Classical.ISupervisedEstimator.TrainOnLabeledDataset")]
    [MapsTo("fit")]
    void Fit(NDArray<TFeature> X, NDArray<TLabel> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.ISupervisedEstimator.PredictLabels")]
    [MapsTo("predict")]
    NDArray<TLabel> Predict(NDArray<TFeature> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.ISupervisedEstimator.EvaluateModelScore")]
    [MapsTo("score")]
    double Score(NDArray<TFeature> X, NDArray<TLabel> y);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.MachineLearning.Classical.ISupervisedEstimator.TrainOnLabeledDataset", "Fit")]
    [MapsTo("fit")]
    void fit(NDArray<TFeature> X, NDArray<TLabel> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.ISupervisedEstimator.PredictLabels", "Predict")]
    [MapsTo("predict")]
    NDArray<TLabel> predict(NDArray<TFeature> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.ISupervisedEstimator.EvaluateModelScore", "Score")]
    [MapsTo("score")]
    double score(NDArray<TFeature> X, NDArray<TLabel> y);
}

[MapsTo("_prep.StandardScaler")]
[RuntimeType("object")]
public primitive class StandardFeatureScaler : IFeatureTransformer<double>
{
    [InlineTemplate("{self}.mean_")]
    public extern NDArray<double> FeatureMeans { get; }

    [InlineTemplate("{self}.scale_")]
    public extern NDArray<double> FeatureStandardDeviations { get; }

    [MapsTo("fit")]
    public extern void FitToFeatures(NDArray<double> featureMatrix);

    [MapsTo("transform")]
    public extern NDArray<double> TransformFeatures(NDArray<double> featureMatrix);

    [MapsTo("fit_transform")]
    public extern NDArray<double> FitAndTransformFeatures(NDArray<double> featureMatrix);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.StandardFeatureScaler.FitToFeatures")]
    [MapsTo("fit")]
    public extern void Fit(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.StandardFeatureScaler.TransformFeatures")]
    [MapsTo("transform")]
    public extern NDArray<double> Transform(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.StandardFeatureScaler.FitAndTransformFeatures")]
    [MapsTo("fit_transform")]
    public extern NDArray<double> FitTransform(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.StandardFeatureScaler.FitToFeatures", "Fit")]
    [MapsTo("fit")]
    public extern void fit(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.StandardFeatureScaler.TransformFeatures", "Transform")]
    [MapsTo("transform")]
    public extern NDArray<double> transform(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.StandardFeatureScaler.FitAndTransformFeatures", "FitTransform")]
    [MapsTo("fit_transform")]
    public extern NDArray<double> fit_transform(NDArray<double> X);
}

[MapsTo("_ens.RandomForestClassifier")]
[RuntimeType("object")]
public primitive class RandomForestClassifierModel : ISupervisedEstimator<double, int>
{
    [InlineTemplate("{self}.feature_importances_")]
    public extern NDArray<double> FeatureImportanceScores { get; }

    [MapsTo("fit")]
    public extern void TrainOnLabeledDataset(NDArray<double> featureMatrix, NDArray<int> targetLabels);

    [MapsTo("predict")]
    public extern NDArray<int> PredictLabels(NDArray<double> featureMatrix);

    [MapsTo("predict_proba")]
    public extern NDArray<double> PredictClassProbabilities(NDArray<double> featureMatrix);

    [MapsTo("score")]
    public extern double EvaluateModelScore(NDArray<double> featureMatrix, NDArray<int> groundTruthLabels);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RandomForestClassifierModel.TrainOnLabeledDataset")]
    [MapsTo("fit")]
    public extern void Fit(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RandomForestClassifierModel.PredictLabels")]
    [MapsTo("predict")]
    public extern NDArray<int> Predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RandomForestClassifierModel.PredictClassProbabilities")]
    [MapsTo("predict_proba")]
    public extern NDArray<double> PredictProba(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RandomForestClassifierModel.EvaluateModelScore")]
    [MapsTo("score")]
    public extern double Score(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RandomForestClassifierModel.TrainOnLabeledDataset", "Fit")]
    [MapsTo("fit")]
    public extern void fit(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RandomForestClassifierModel.PredictLabels", "Predict")]
    [MapsTo("predict")]
    public extern NDArray<int> predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RandomForestClassifierModel.PredictClassProbabilities", "PredictProba")]
    [MapsTo("predict_proba")]
    public extern NDArray<double> predict_proba(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RandomForestClassifierModel.EvaluateModelScore", "Score")]
    [MapsTo("score")]
    public extern double score(NDArray<double> X, NDArray<int> y);
}

[MapsTo("_lin.LogisticRegression")]
[RuntimeType("object")]
public primitive class LogisticRegressionModel : ISupervisedEstimator<double, int>
{
    [MapsTo("fit")]
    public extern void TrainOnLabeledDataset(NDArray<double> featureMatrix, NDArray<int> targetLabels);

    [MapsTo("predict")]
    public extern NDArray<int> PredictLabels(NDArray<double> featureMatrix);

    [MapsTo("predict_proba")]
    public extern NDArray<double> PredictClassProbabilities(NDArray<double> featureMatrix);

    [MapsTo("score")]
    public extern double EvaluateModelScore(NDArray<double> featureMatrix, NDArray<int> groundTruthLabels);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.LogisticRegressionModel.TrainOnLabeledDataset")]
    [MapsTo("fit")]
    public extern void Fit(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.LogisticRegressionModel.PredictLabels")]
    [MapsTo("predict")]
    public extern NDArray<int> Predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.LogisticRegressionModel.PredictClassProbabilities")]
    [MapsTo("predict_proba")]
    public extern NDArray<double> PredictProba(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.LogisticRegressionModel.EvaluateModelScore")]
    [MapsTo("score")]
    public extern double Score(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.LogisticRegressionModel.TrainOnLabeledDataset", "Fit")]
    [MapsTo("fit")]
    public extern void fit(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.LogisticRegressionModel.PredictLabels", "Predict")]
    [MapsTo("predict")]
    public extern NDArray<int> predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.LogisticRegressionModel.PredictClassProbabilities", "PredictProba")]
    [MapsTo("predict_proba")]
    public extern NDArray<double> predict_proba(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.LogisticRegressionModel.EvaluateModelScore", "Score")]
    [MapsTo("score")]
    public extern double score(NDArray<double> X, NDArray<int> y);
}

[MapsTo("_lin.Ridge")]
[RuntimeType("object")]
public primitive class RidgeRegressionModel : ISupervisedEstimator<double, double>
{
    [MapsTo("fit")]
    public extern void TrainOnLabeledDataset(NDArray<double> featureMatrix, NDArray<double> targetValues);

    [MapsTo("predict")]
    public extern NDArray<double> PredictLabels(NDArray<double> featureMatrix);

    [MapsTo("score")]
    public extern double EvaluateModelScore(NDArray<double> featureMatrix, NDArray<double> groundTruthValues);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RidgeRegressionModel.TrainOnLabeledDataset")]
    [MapsTo("fit")]
    public extern void Fit(NDArray<double> X, NDArray<double> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RidgeRegressionModel.PredictLabels")]
    [MapsTo("predict")]
    public extern NDArray<double> Predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RidgeRegressionModel.EvaluateModelScore")]
    [MapsTo("score")]
    public extern double Score(NDArray<double> X, NDArray<double> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RidgeRegressionModel.TrainOnLabeledDataset", "Fit")]
    [MapsTo("fit")]
    public extern void fit(NDArray<double> X, NDArray<double> y);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RidgeRegressionModel.PredictLabels", "Predict")]
    [MapsTo("predict")]
    public extern NDArray<double> predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.RidgeRegressionModel.EvaluateModelScore", "Score")]
    [MapsTo("score")]
    public extern double score(NDArray<double> X, NDArray<double> y);
}

```

### `stdlib/02_scientific_and_ai/05_sklearn/01_sklearn.raw.d.ps`

```csharp
namespace sklearn;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.MachineLearning.Classical;
extern using sklearn.model_selection as _ms;
extern using sklearn.preprocessing as _prep;
extern using sklearn.ensemble as _ens;
extern using sklearn.linear_model as _lin;
extern using sklearn.metrics as _met;

[SurfaceLevel(2)]
[MapsTo("_ms")]
public static primitive class ModelSelectionModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.DatasetSplitter.SplitTrainAndTestSets", "PythonSharp.ScikitLearn.sk.ModelSelection.TrainTestSplit")]
    [InlineTemplate("_ms.train_test_split({0}, {1}, test_size={2}, random_state={3})")]
    public static extern (NDArray<double> X_train, NDArray<double> X_test, NDArray<TLabel> y_train, NDArray<TLabel> y_test) train_test_split<TLabel>(
        NDArray<double> X, NDArray<TLabel> y, double test_size = 0.2, int random_state = 42);
}

[SurfaceLevel(2)]
[MapsTo("_prep")]
public static primitive class PreprocessingModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.FeaturePreprocessingFactory.CreateStandardZScoreScaler", "PythonSharp.ScikitLearn.sk.Preprocessing.StandardScaler")]
    [InlineTemplate("_prep.StandardScaler()")]
    public static extern StandardFeatureScaler StandardScaler();
}

[SurfaceLevel(2)]
[MapsTo("_ens")]
public static primitive class EnsembleModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.ModelEstimatorFactory.CreateRandomForestClassifier", "PythonSharp.ScikitLearn.sk.Ensemble.RandomForestClassifier")]
    [InlineTemplate("_ens.RandomForestClassifier(n_estimators={0}, random_state={1})")]
    public static extern RandomForestClassifierModel RandomForestClassifier(int n_estimators = 100, int random_state = 42);
}

[SurfaceLevel(2)]
[MapsTo("_lin")]
public static primitive class LinearModelModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.ModelEstimatorFactory.CreateLogisticRegressionClassifier", "PythonSharp.ScikitLearn.sk.LinearModel.LogisticRegression")]
    [InlineTemplate("_lin.LogisticRegression(max_iter={0}, random_state={1})")]
    public static extern LogisticRegressionModel LogisticRegression(int max_iter = 200, int random_state = 42);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.ModelEstimatorFactory.CreateRidgeRegressor", "PythonSharp.ScikitLearn.sk.LinearModel.Ridge")]
    [InlineTemplate("_lin.Ridge(alpha={0})")]
    public static extern RidgeRegressionModel Ridge(double alpha = 1.0);
}

[SurfaceLevel(2)]
[MapsTo("_met")]
public static primitive class MetricsModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.EvaluationMetrics.ComputeAccuracyScore", "PythonSharp.ScikitLearn.sk.Metrics.AccuracyScore")]
    [InlineTemplate("_met.accuracy_score({0}, {1})")]
    public static extern double accuracy_score(NDArray<int> y_true, NDArray<int> y_pred);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.EvaluationMetrics.ComputeF1Score", "PythonSharp.ScikitLearn.sk.Metrics.F1Score")]
    [InlineTemplate("_met.f1_score({0}, {1}, average={2})")]
    public static extern double f1_score(NDArray<int> y_true, NDArray<int> y_pred, string average = "weighted");

    [CanonicalApi("PythonSharp.MachineLearning.Classical.EvaluationMetrics.ComputeMeanSquaredError", "PythonSharp.ScikitLearn.sk.Metrics.MeanSquaredError")]
    [InlineTemplate("_met.mean_squared_error({0}, {1})")]
    public static extern double mean_squared_error(NDArray<double> y_true, NDArray<double> y_pred);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.EvaluationMetrics.ComputeR2Score", "PythonSharp.ScikitLearn.sk.Metrics.R2Score")]
    [InlineTemplate("_met.r2_score({0}, {1})")]
    public static extern double r2_score(NDArray<double> y_true, NDArray<double> y_pred);
}

[SurfaceLevel(2)]
public static primitive class sklearn
{
    [InlineTemplate("_ms")]
    public static extern ModelSelectionModule model_selection { get; }

    [InlineTemplate("_prep")]
    public static extern PreprocessingModule preprocessing { get; }

    [InlineTemplate("_ens")]
    public static extern EnsembleModule ensemble { get; }

    [InlineTemplate("_lin")]
    public static extern LinearModelModule linear_model { get; }

    [InlineTemplate("_met")]
    public static extern MetricsModule metrics { get; }
}

```

### `stdlib/02_scientific_and_ai/05_sklearn/02_sklearn.csharp.d.ps`

```csharp
namespace PythonSharp.ScikitLearn;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.MachineLearning.Classical;
extern using sklearn.model_selection as _ms;
extern using sklearn.preprocessing as _prep;
extern using sklearn.ensemble as _ens;
extern using sklearn.linear_model as _lin;
extern using sklearn.metrics as _met;

[SurfaceLevel(3)]
[MapsTo("_ms")]
public static primitive class SklearnModelSelectionModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.DatasetSplitter.SplitTrainAndTestSets")]
    [InlineTemplate("_ms.train_test_split({0}, {1}, test_size={2}, random_state={3})")]
    public static extern (NDArray<double> XTrain, NDArray<double> XTest, NDArray<TLabel> YTrain, NDArray<TLabel> YTest) TrainTestSplit<TLabel>(
        NDArray<double> features, NDArray<TLabel> labels, double testSize = 0.2, int randomState = 42);
}

[SurfaceLevel(3)]
[MapsTo("_prep")]
public static primitive class SklearnPreprocessingModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.FeaturePreprocessingFactory.CreateStandardZScoreScaler")]
    [InlineTemplate("_prep.StandardScaler()")]
    public static extern StandardFeatureScaler StandardScaler();
}

[SurfaceLevel(3)]
[MapsTo("_ens")]
public static primitive class SklearnEnsembleModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.ModelEstimatorFactory.CreateRandomForestClassifier")]
    [InlineTemplate("_ens.RandomForestClassifier(n_estimators={0}, random_state={1})")]
    public static extern RandomForestClassifierModel RandomForestClassifier(int nEstimators = 100, int randomState = 42);
}

[SurfaceLevel(3)]
[MapsTo("_lin")]
public static primitive class SklearnLinearModelModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.ModelEstimatorFactory.CreateLogisticRegressionClassifier")]
    [InlineTemplate("_lin.LogisticRegression(max_iter={0}, random_state={1})")]
    public static extern LogisticRegressionModel LogisticRegression(int maxIter = 200, int randomState = 42);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.ModelEstimatorFactory.CreateRidgeRegressor")]
    [InlineTemplate("_lin.Ridge(alpha={0})")]
    public static extern RidgeRegressionModel Ridge(double alpha = 1.0);
}

[SurfaceLevel(3)]
[MapsTo("_met")]
public static primitive class SklearnMetricsModule
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.EvaluationMetrics.ComputeAccuracyScore")]
    [InlineTemplate("_met.accuracy_score({0}, {1})")]
    public static extern double AccuracyScore(NDArray<int> trueLabels, NDArray<int> predictedLabels);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.EvaluationMetrics.ComputeF1Score")]
    [InlineTemplate("_met.f1_score({0}, {1}, average={2})")]
    public static extern double F1Score(NDArray<int> trueLabels, NDArray<int> predictedLabels, string average = "weighted");

    [CanonicalApi("PythonSharp.MachineLearning.Classical.EvaluationMetrics.ComputeMeanSquaredError")]
    [InlineTemplate("_met.mean_squared_error({0}, {1})")]
    public static extern double MeanSquaredError(NDArray<double> trueValues, NDArray<double> predictedValues);

    [CanonicalApi("PythonSharp.MachineLearning.Classical.EvaluationMetrics.ComputeR2Score")]
    [InlineTemplate("_met.r2_score({0}, {1})")]
    public static extern double R2Score(NDArray<double> trueValues, NDArray<double> predictedValues);
}

[SurfaceLevel(3)]
public static primitive class sk
{
    [InlineTemplate("_ms")]
    public static extern SklearnModelSelectionModule ModelSelection { get; }

    [InlineTemplate("_prep")]
    public static extern SklearnPreprocessingModule Preprocessing { get; }

    [InlineTemplate("_ens")]
    public static extern SklearnEnsembleModule Ensemble { get; }

    [InlineTemplate("_lin")]
    public static extern SklearnLinearModelModule LinearModel { get; }

    [InlineTemplate("_met")]
    public static extern SklearnMetricsModule Metrics { get; }
}

```

### `stdlib/02_scientific_and_ai/05_sklearn/03_ml.enterprise.d.ps`

```csharp
namespace PythonSharp.MachineLearning.Classical;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using sklearn.model_selection as _ms;
extern using sklearn.preprocessing as _prep;
extern using sklearn.ensemble as _ens;
extern using sklearn.linear_model as _lin;
extern using sklearn.metrics as _met;

[SurfaceLevel(1)]
[MapsTo("_ms")]
public static primitive class DatasetSplitter
{
    [InlineTemplate("_ms.train_test_split({0}, {1}, test_size={2}, random_state={3})")]
    public static extern (NDArray<double> TrainingFeatures, NDArray<double> TestingFeatures, NDArray<TLabel> TrainingLabels, NDArray<TLabel> TestingLabels) SplitTrainAndTestSets<TLabel>(
        NDArray<double> featureMatrix, NDArray<TLabel> labelVector, double testFraction = 0.2, int randomSeed = 42);
}

[SurfaceLevel(1)]
[MapsTo("_prep")]
public static primitive class FeaturePreprocessingFactory
{
    [InlineTemplate("_prep.StandardScaler()")]
    public static extern StandardFeatureScaler CreateStandardZScoreScaler();
}

[SurfaceLevel(1)]
public static primitive class ModelEstimatorFactory
{
    [InlineTemplate("_ens.RandomForestClassifier(n_estimators={0}, random_state={1})")]
    public static extern RandomForestClassifierModel CreateRandomForestClassifier(int numberOfTrees = 100, int randomSeed = 42);

    [InlineTemplate("_lin.LogisticRegression(max_iter={0}, random_state={1})")]
    public static extern LogisticRegressionModel CreateLogisticRegressionClassifier(int maxOptimizationIterations = 200, int randomSeed = 42);

    [InlineTemplate("_lin.Ridge(alpha={0})")]
    public static extern RidgeRegressionModel CreateRidgeRegressor(double l2RegularizationStrength = 1.0);
}

[SurfaceLevel(1)]
[MapsTo("_met")]
public static primitive class EvaluationMetrics
{
    [InlineTemplate("_met.accuracy_score({0}, {1})")]
    public static extern double ComputeAccuracyScore(NDArray<int> groundTruthLabels, NDArray<int> predictedLabels);

    [InlineTemplate("_met.f1_score({0}, {1}, average={2})")]
    public static extern double ComputeF1Score(NDArray<int> groundTruthLabels, NDArray<int> predictedLabels, string averagingMode = "weighted");

    [InlineTemplate("_met.mean_squared_error({0}, {1})")]
    public static extern double ComputeMeanSquaredError(NDArray<double> groundTruthValues, NDArray<double> predictedValues);

    [InlineTemplate("_met.r2_score({0}, {1})")]
    public static extern double ComputeR2Score(NDArray<double> groundTruthValues, NDArray<double> predictedValues);
}

```

---

## 5. `06_torch` (Deep Learning Tensors, Autograd, Neural Layers & Optimizers)

`06_torch` defines `TorchTensor<T>`, `[DisableGradientTracking]` / `[NoGrad]` decorator attributes, `FullyConnectedLinearLayer`, `MeanSquaredErrorLoss`, and `GradientOptimizer` across `torch` (Surface 2), `PythonSharp.PyTorch` (Surface 3), and `PythonSharp.DeepLearning` (Surface 1).

### `stdlib/02_scientific_and_ai/06_torch/00_torch.primitives.d.ps`

```csharp
namespace PythonSharp.DeepLearning;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using torch as _torch;
extern using torch.nn as _nn;
extern using torch.optim as _optim;

public sealed class DisableGradientTrackingAttribute : PythonDecoratorAttribute
{
    public DisableGradientTrackingAttribute() : base("torch.no_grad()") { }
}

public sealed class NoGradAttribute : PythonDecoratorAttribute
{
    public NoGradAttribute() : base("torch.no_grad()") { }
}

[MapsTo("torch.Tensor")]
[RuntimeType("torch.Tensor")]
public primitive class TorchTensor<T>
{
    // --- Triple-Surface Properties ---
    [InlineTemplate("list({self}.shape)")]
    public extern List<int> TensorShape { get; }

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.TensorShape")]
    [InlineTemplate("list({self}.shape)")]
    public extern List<int> Shape { get; }

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.TensorShape", "Shape")]
    [InlineTemplate("list({self}.shape)")]
    public extern List<int> shape { get; }

    [InlineTemplate("str({self}.device)")]
    public extern string ExecutionDevice { get; }

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ExecutionDevice")]
    [InlineTemplate("str({self}.device)")]
    public extern string Device { get; }

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ExecutionDevice", "Device")]
    [InlineTemplate("str({self}.device)")]
    public extern string device { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("to")]
    public extern TorchTensor<T> MoveToDevice(string targetDeviceName);

    [MapsTo("backward")]
    public extern void ComputeBackpropagationGradients();

    [MapsTo("detach")]
    public extern TorchTensor<T> DetachFromComputationGraph();

    [InlineTemplate("{self}.detach().cpu().numpy()")]
    public extern NDArray<T> ConvertToCpuNumPyArray();

    [MapsTo("item")]
    public extern T ExtractScalarValue();

    [MapsTo("reshape")]
    public extern TorchTensor<T> ReshapeTensor(params int[] dimensions);

    [InlineTemplate("({self} @ {0})")]
    public extern TorchTensor<T> MatrixMultiply(TorchTensor<T> rightTensor);

    [MapsTo("mean")]
    public extern TorchTensor<double> ComputeMean();

    [MapsTo("sum")]
    public extern TorchTensor<T> ComputeSum();

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.MoveToDevice")]
    [MapsTo("to")]
    public extern TorchTensor<T> To(string device);

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ComputeBackpropagationGradients")]
    [MapsTo("backward")]
    public extern void Backward();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.DetachFromComputationGraph")]
    [MapsTo("detach")]
    public extern TorchTensor<T> Detach();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ConvertToCpuNumPyArray")]
    [InlineTemplate("{self}.detach().cpu().numpy()")]
    public extern NDArray<T> ToNumpy();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ExtractScalarValue")]
    [MapsTo("item")]
    public extern T Item();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ReshapeTensor")]
    [MapsTo("reshape")]
    public extern TorchTensor<T> Reshape(params int[] shape);

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.MatrixMultiply")]
    [MapsTo("matmul")]
    public extern TorchTensor<T> MatMul(TorchTensor<T> other);

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ComputeMean")]
    [MapsTo("mean")]
    public extern TorchTensor<double> Mean();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ComputeSum")]
    [MapsTo("sum")]
    public extern TorchTensor<T> Sum();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.MoveToDevice", "To")]
    [MapsTo("to")]
    public extern TorchTensor<T> to(string device);

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ComputeBackpropagationGradients", "Backward")]
    [MapsTo("backward")]
    public extern void backward();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.DetachFromComputationGraph", "Detach")]
    [MapsTo("detach")]
    public extern TorchTensor<T> detach();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ConvertToCpuNumPyArray", "ToNumpy")]
    [InlineTemplate("{self}.detach().cpu().numpy()")]
    public extern NDArray<T> numpy();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ExtractScalarValue", "Item")]
    [MapsTo("item")]
    public extern T item();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ReshapeTensor", "Reshape")]
    [MapsTo("reshape")]
    public extern TorchTensor<T> reshape(params int[] shape);

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.MatrixMultiply", "MatMul")]
    [MapsTo("matmul")]
    public extern TorchTensor<T> matmul(TorchTensor<T> other);

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ComputeMean", "Mean")]
    [MapsTo("mean")]
    public extern TorchTensor<double> mean();

    [CanonicalApi("PythonSharp.DeepLearning.TorchTensor.ComputeSum", "Sum")]
    [MapsTo("sum")]
    public extern TorchTensor<T> sum();
}

[MapsTo("_nn.Linear")]
[RuntimeType("object")]
public primitive class FullyConnectedLinearLayer
{
    [InlineTemplate("{self}({0})")]
    public extern TorchTensor<double> ExecuteForwardPass(TorchTensor<double> inputTensor);

    [CanonicalApi("PythonSharp.DeepLearning.FullyConnectedLinearLayer.ExecuteForwardPass")]
    [InlineTemplate("{self}({0})")]
    public extern TorchTensor<double> Forward(TorchTensor<double> x);

    [CanonicalApi("PythonSharp.DeepLearning.FullyConnectedLinearLayer.ExecuteForwardPass", "Forward")]
    [InlineTemplate("{self}({0})")]
    public extern TorchTensor<double> forward(TorchTensor<double> x);

    [MapsTo("parameters")]
    public extern object GetTrainableParameters();

    [CanonicalApi("PythonSharp.DeepLearning.FullyConnectedLinearLayer.GetTrainableParameters")]
    [MapsTo("parameters")]
    public extern object Parameters();

    [CanonicalApi("PythonSharp.DeepLearning.FullyConnectedLinearLayer.GetTrainableParameters", "Parameters")]
    [MapsTo("parameters")]
    public extern object parameters();
}

[MapsTo("_nn.MSELoss")]
[RuntimeType("object")]
public primitive class MeanSquaredErrorLoss
{
    [InlineTemplate("{self}({0}, {1})")]
    public extern TorchTensor<double> ComputeLoss(TorchTensor<double> predictions, TorchTensor<double> targets);

    [CanonicalApi("PythonSharp.DeepLearning.MeanSquaredErrorLoss.ComputeLoss")]
    [InlineTemplate("{self}({0}, {1})")]
    public extern TorchTensor<double> Forward(TorchTensor<double> input, TorchTensor<double> target);

    [CanonicalApi("PythonSharp.DeepLearning.MeanSquaredErrorLoss.ComputeLoss", "Forward")]
    [InlineTemplate("{self}({0}, {1})")]
    public extern TorchTensor<double> forward(TorchTensor<double> input, TorchTensor<double> target);
}

[MapsTo("torch.optim.Optimizer")]
[RuntimeType("object")]
public primitive class GradientOptimizer
{
    [MapsTo("zero_grad")]
    public extern void ResetAllGradientsToZero();

    [CanonicalApi("PythonSharp.DeepLearning.GradientOptimizer.ResetAllGradientsToZero")]
    [MapsTo("zero_grad")]
    public extern void ZeroGrad();

    [CanonicalApi("PythonSharp.DeepLearning.GradientOptimizer.ResetAllGradientsToZero", "ZeroGrad")]
    [MapsTo("zero_grad")]
    public extern void zero_grad();

    [MapsTo("step")]
    public extern void UpdateModelParameters();

    [CanonicalApi("PythonSharp.DeepLearning.GradientOptimizer.UpdateModelParameters")]
    [MapsTo("step")]
    public extern void Step();

    [CanonicalApi("PythonSharp.DeepLearning.GradientOptimizer.UpdateModelParameters", "Step")]
    [MapsTo("step")]
    public extern void step();
}

```

### `stdlib/02_scientific_and_ai/06_torch/01_torch.raw.d.ps`

```csharp
namespace torch;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DeepLearning;
extern using torch as _torch;
extern using torch.nn as _nn;
extern using torch.optim as _optim;

[SurfaceLevel(2)]
[MapsTo("_torch.cuda")]
public static primitive class CudaModule
{
    [CanonicalApi("PythonSharp.DeepLearning.AcceleratorRuntime.IsCudaGpuAvailable", "PythonSharp.PyTorch.torch.Cuda.IsAvailable")]
    [InlineTemplate("_torch.cuda.is_available()")]
    public static extern bool is_available();

    [CanonicalApi("PythonSharp.DeepLearning.AcceleratorRuntime.GetAvailableGpuCount", "PythonSharp.PyTorch.torch.Cuda.DeviceCount")]
    [InlineTemplate("_torch.cuda.device_count()")]
    public static extern int device_count();
}

[SurfaceLevel(2)]
[MapsTo("_nn")]
public static primitive class NnModule
{
    [CanonicalApi("PythonSharp.DeepLearning.NeuralLayerFactory.CreateFullyConnectedLinearLayer", "PythonSharp.PyTorch.torch.NN.Linear")]
    [InlineTemplate("_nn.Linear({0}, {1})")]
    public static extern FullyConnectedLinearLayer Linear(int in_features, int out_features);

    [CanonicalApi("PythonSharp.DeepLearning.LossCriterionFactory.CreateMeanSquaredErrorLoss", "PythonSharp.PyTorch.torch.NN.MSELoss")]
    [InlineTemplate("_nn.MSELoss()")]
    public static extern MeanSquaredErrorLoss MSELoss();
}

[SurfaceLevel(2)]
[MapsTo("_optim")]
public static primitive class OptimModule
{
    [CanonicalApi("PythonSharp.DeepLearning.OptimizerFactory.CreateAdamOptimizer", "PythonSharp.PyTorch.torch.Optim.Adam")]
    [InlineTemplate("_optim.Adam({0}, lr={1})")]
    public static extern GradientOptimizer Adam(object @params, double lr = 0.001);

    [CanonicalApi("PythonSharp.DeepLearning.OptimizerFactory.CreateStochasticGradientDescentOptimizer", "PythonSharp.PyTorch.torch.Optim.SGD")]
    [InlineTemplate("_optim.SGD({0}, lr={1})")]
    public static extern GradientOptimizer SGD(object @params, double lr = 0.01);
}

[SurfaceLevel(2)]
[MapsTo("_torch")]
public static primitive class torch
{
    [InlineTemplate("_torch.cuda")]
    public static extern CudaModule cuda { get; }

    [InlineTemplate("_nn")]
    public static extern NnModule nn { get; }

    [InlineTemplate("_optim")]
    public static extern OptimModule optim { get; }

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.SetRandomSeed", "PythonSharp.PyTorch.torch.ManualSeed")]
    [InlineTemplate("_torch.manual_seed({0})")]
    public static extern void manual_seed(int seed);

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.FromNumPyArray", "PythonSharp.PyTorch.torch.FromNumpy")]
    [InlineTemplate("_torch.from_numpy({0})")]
    public static extern TorchTensor<T> from_numpy<T>(NDArray<T> ndarray);

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.CreateZeroTensor", "PythonSharp.PyTorch.torch.Zeros")]
    [InlineTemplate("_torch.zeros(({0}, {1}))")]
    public static extern TorchTensor<double> zeros(int rows, int cols);

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.CreateOnesTensor", "PythonSharp.PyTorch.torch.Ones")]
    [InlineTemplate("_torch.ones(({0}, {1}))")]
    public static extern TorchTensor<double> ones(int rows, int cols);

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.CreateRandomNormalTensor", "PythonSharp.PyTorch.torch.RandN")]
    [InlineTemplate("_torch.randn({0}, {1})")]
    public static extern TorchTensor<double> randn(int rows, int cols);

    [CanonicalApi("PythonSharp.DeepLearning.ActivationFunctions.ApplyRectifiedLinearUnit", "PythonSharp.PyTorch.torch.ReLU")]
    [InlineTemplate("_torch.relu({0})")]
    public static extern TorchTensor<T> relu<T>(TorchTensor<T> input);

    [CanonicalApi("PythonSharp.DeepLearning.ActivationFunctions.ApplySigmoid", "PythonSharp.PyTorch.torch.Sigmoid")]
    [InlineTemplate("_torch.sigmoid({0})")]
    public static extern TorchTensor<T> sigmoid<T>(TorchTensor<T> input);
}

```

### `stdlib/02_scientific_and_ai/06_torch/02_torch.csharp.d.ps`

```csharp
namespace PythonSharp.PyTorch;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DeepLearning;
extern using torch as _torch;
extern using torch.nn as _nn;
extern using torch.optim as _optim;

[SurfaceLevel(3)]
[MapsTo("_torch.cuda")]
public static primitive class PyTorchCudaModule
{
    [CanonicalApi("PythonSharp.DeepLearning.AcceleratorRuntime.IsCudaGpuAvailable")]
    [InlineTemplate("_torch.cuda.is_available()")]
    public static extern bool IsAvailable();

    [CanonicalApi("PythonSharp.DeepLearning.AcceleratorRuntime.GetAvailableGpuCount")]
    [InlineTemplate("_torch.cuda.device_count()")]
    public static extern int DeviceCount();
}

[SurfaceLevel(3)]
[MapsTo("_nn")]
public static primitive class PyTorchNnModule
{
    [CanonicalApi("PythonSharp.DeepLearning.NeuralLayerFactory.CreateFullyConnectedLinearLayer")]
    [InlineTemplate("_nn.Linear({0}, {1})")]
    public static extern FullyConnectedLinearLayer Linear(int inFeatures, int outFeatures);

    [CanonicalApi("PythonSharp.DeepLearning.LossCriterionFactory.CreateMeanSquaredErrorLoss")]
    [InlineTemplate("_nn.MSELoss()")]
    public static extern MeanSquaredErrorLoss MSELoss();
}

[SurfaceLevel(3)]
[MapsTo("_optim")]
public static primitive class PyTorchOptimModule
{
    [CanonicalApi("PythonSharp.DeepLearning.OptimizerFactory.CreateAdamOptimizer")]
    [InlineTemplate("_optim.Adam({0}, lr={1})")]
    public static extern GradientOptimizer Adam(object parameters, double learningRate = 0.001);

    [CanonicalApi("PythonSharp.DeepLearning.OptimizerFactory.CreateStochasticGradientDescentOptimizer")]
    [InlineTemplate("_optim.SGD({0}, lr={1})")]
    public static extern GradientOptimizer SGD(object parameters, double learningRate = 0.01);
}

[SurfaceLevel(3)]
[MapsTo("_torch")]
public static primitive class torch
{
    [InlineTemplate("_torch.cuda")]
    public static extern PyTorchCudaModule Cuda { get; }

    [InlineTemplate("_nn")]
    public static extern PyTorchNnModule NN { get; }

    [InlineTemplate("_optim")]
    public static extern PyTorchOptimModule Optim { get; }

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.SetRandomSeed")]
    [InlineTemplate("_torch.manual_seed({0})")]
    public static extern void ManualSeed(int seed);

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.FromNumPyArray")]
    [InlineTemplate("_torch.from_numpy({0})")]
    public static extern TorchTensor<T> FromNumpy<T>(NDArray<T> array);

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.CreateZeroTensor")]
    [InlineTemplate("_torch.zeros(({0}, {1}))")]
    public static extern TorchTensor<double> Zeros(int rows, int cols);

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.CreateOnesTensor")]
    [InlineTemplate("_torch.ones(({0}, {1}))")]
    public static extern TorchTensor<double> Ones(int rows, int cols);

    [CanonicalApi("PythonSharp.DeepLearning.TensorFactory.CreateRandomNormalTensor")]
    [InlineTemplate("_torch.randn({0}, {1})")]
    public static extern TorchTensor<double> RandN(int rows, int cols);

    [CanonicalApi("PythonSharp.DeepLearning.ActivationFunctions.ApplyRectifiedLinearUnit")]
    [InlineTemplate("_torch.relu({0})")]
    public static extern TorchTensor<T> ReLU<T>(TorchTensor<T> input);

    [CanonicalApi("PythonSharp.DeepLearning.ActivationFunctions.ApplySigmoid")]
    [InlineTemplate("_torch.sigmoid({0})")]
    public static extern TorchTensor<T> Sigmoid<T>(TorchTensor<T> input);
}

```

### `stdlib/02_scientific_and_ai/06_torch/03_deeplearning.enterprise.d.ps`

```csharp
namespace PythonSharp.DeepLearning;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using torch as _torch;
extern using torch.nn as _nn;
extern using torch.optim as _optim;

[SurfaceLevel(1)]
public static primitive class AcceleratorRuntime
{
    [InlineTemplate("_torch.cuda.is_available()")]
    public static extern bool IsCudaGpuAvailable();

    [InlineTemplate("_torch.cuda.device_count()")]
    public static extern int GetAvailableGpuCount();

    [InlineTemplate("('cuda' if _torch.cuda.is_available() else 'cpu')")]
    public static extern string SelectOptimalDeviceName();
}

[SurfaceLevel(1)]
[MapsTo("_torch")]
public static primitive class TensorFactory
{
    [InlineTemplate("_torch.manual_seed({0})")]
    public static extern void SetRandomSeed(int seedValue);

    [InlineTemplate("_torch.from_numpy({0})")]
    public static extern TorchTensor<T> FromNumPyArray<T>(NDArray<T> sourceArray);

    [InlineTemplate("_torch.zeros(({0}, {1}))")]
    public static extern TorchTensor<double> CreateZeroTensor(int rows, int columns);

    [InlineTemplate("_torch.ones(({0}, {1}))")]
    public static extern TorchTensor<double> CreateOnesTensor(int rows, int columns);

    [InlineTemplate("_torch.randn({0}, {1})")]
    public static extern TorchTensor<double> CreateRandomNormalTensor(int rows, int columns);
}

[SurfaceLevel(1)]
[MapsTo("_nn")]
public static primitive class NeuralLayerFactory
{
    [InlineTemplate("_nn.Linear({0}, {1})")]
    public static extern FullyConnectedLinearLayer CreateFullyConnectedLinearLayer(int inputFeatureCount, int outputFeatureCount);
}

[SurfaceLevel(1)]
[MapsTo("_nn")]
public static primitive class LossCriterionFactory
{
    [InlineTemplate("_nn.MSELoss()")]
    public static extern MeanSquaredErrorLoss CreateMeanSquaredErrorLoss();
}

[SurfaceLevel(1)]
[MapsTo("_optim")]
public static primitive class OptimizerFactory
{
    [InlineTemplate("_optim.Adam({0}, lr={1})")]
    public static extern GradientOptimizer CreateAdamOptimizer(object trainableParameters, double learningRate = 0.001);

    [InlineTemplate("_optim.SGD({0}, lr={1})")]
    public static extern GradientOptimizer CreateStochasticGradientDescentOptimizer(object trainableParameters, double learningRate = 0.01);
}

[SurfaceLevel(1)]
[MapsTo("_torch")]
public static primitive class ActivationFunctions
{
    [InlineTemplate("_torch.relu({0})")]
    public static extern TorchTensor<T> ApplyRectifiedLinearUnit<T>(TorchTensor<T> inputTensor);

    [InlineTemplate("_torch.sigmoid({0})")]
    public static extern TorchTensor<T> ApplySigmoid<T>(TorchTensor<T> inputTensor);
}

```

---

## 6. `07_sympy` (Symbolic Mathematics, Algebra & Calculus)

`07_sympy` defines `SymbolicExpression` (`sp.Expr`) and `SymbolicVariable` (`sp.Symbol`) across `sympy` (Surface 2), `PythonSharp.SymPy` (Surface 3), and `PythonSharp.SymbolicMath` (Surface 1).

### `stdlib/02_scientific_and_ai/07_sympy/00_sympy.primitives.d.ps`

```csharp
namespace PythonSharp.SymbolicMath;

using PythonSharp.Core;
extern using sympy as _sp;

[MapsTo("sympy.Expr")]
[RuntimeType("sympy.Expr")]
public primitive class SymbolicExpression
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("subs")]
    public extern SymbolicExpression SubstituteVariable(SymbolicExpression targetVariable, object replacementValue);

    [InlineTemplate("float({self}.evalf())")]
    public extern double EvaluateNumerically();

    [MapsTo("simplify")]
    public extern SymbolicExpression SimplifyAlgebraically();

    [MapsTo("expand")]
    public extern SymbolicExpression ExpandPolynomial();

    [MapsTo("factor")]
    public extern SymbolicExpression FactorizePolynomial();

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.SubstituteVariable")]
    [MapsTo("subs")]
    public extern SymbolicExpression Subs(SymbolicExpression variable, object value);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.EvaluateNumerically")]
    [InlineTemplate("float({self}.evalf())")]
    public extern double EvalF();

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.SimplifyAlgebraically")]
    [MapsTo("simplify")]
    public extern SymbolicExpression Simplify();

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.ExpandPolynomial")]
    [MapsTo("expand")]
    public extern SymbolicExpression Expand();

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.FactorizePolynomial")]
    [MapsTo("factor")]
    public extern SymbolicExpression Factor();

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.SubstituteVariable", "Subs")]
    [MapsTo("subs")]
    public extern SymbolicExpression subs(SymbolicExpression variable, object value);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.EvaluateNumerically", "EvalF")]
    [InlineTemplate("float({self}.evalf())")]
    public extern double evalf();

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.SimplifyAlgebraically", "Simplify")]
    [MapsTo("simplify")]
    public extern SymbolicExpression simplify();

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.ExpandPolynomial", "Expand")]
    [MapsTo("expand")]
    public extern SymbolicExpression expand();

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicExpression.FactorizePolynomial", "Factor")]
    [MapsTo("factor")]
    public extern SymbolicExpression factor();
}

[MapsTo("sympy.Symbol")]
[RuntimeType("sympy.Symbol")]
public primitive class SymbolicVariable : SymbolicExpression
{
    [InlineTemplate("str({self}.name)")]
    public extern string SymbolName { get; }

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicVariable.SymbolName")]
    [InlineTemplate("str({self}.name)")]
    public extern string Name { get; }

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicVariable.SymbolName", "Name")]
    [InlineTemplate("str({self}.name)")]
    public extern string name { get; }
}

```

### `stdlib/02_scientific_and_ai/07_sympy/01_sympy.raw.d.ps`

```csharp
namespace sympy;

using PythonSharp.Core;
using PythonSharp.SymbolicMath;
extern using sympy as _sp;

[SurfaceLevel(2)]
[MapsTo("_sp")]
public static primitive class sp
{
    [CanonicalApi("PythonSharp.SymbolicMath.SymbolFactory.DeclareSymbol", "PythonSharp.SymPy.sp.Symbols")]
    [InlineTemplate("_sp.symbols({0})")]
    public static extern SymbolicVariable symbols(string names);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolFactory.ParseSymbolicExpression", "PythonSharp.SymPy.sp.Sympify")]
    [InlineTemplate("_sp.sympify({0})")]
    public static extern SymbolicExpression sympify(string expressionText);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicCalculus.DifferentiateWithRespectTo", "PythonSharp.SymPy.sp.Diff")]
    [InlineTemplate("_sp.diff({0}, {1}, {2})")]
    public static extern SymbolicExpression diff(SymbolicExpression expr, SymbolicVariable symbol, int order = 1);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicCalculus.IntegrateIndefinite", "PythonSharp.SymPy.sp.Integrate")]
    [InlineTemplate("_sp.integrate({0}, {1})")]
    public static extern SymbolicExpression integrate(SymbolicExpression expr, SymbolicVariable symbol);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicCalculus.IntegrateDefinite", "PythonSharp.SymPy.sp.IntegrateDefinite")]
    [InlineTemplate("_sp.integrate({0}, ({1}, {2}, {3}))")]
    public static extern SymbolicExpression integrate(SymbolicExpression expr, SymbolicVariable symbol, double lowerBound, double upperBound);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicAlgebra.SimplifyExpression", "PythonSharp.SymPy.sp.Simplify")]
    [InlineTemplate("_sp.simplify({0})")]
    public static extern SymbolicExpression simplify(SymbolicExpression expr);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicAlgebra.SolveAlgebraicEquation", "PythonSharp.SymPy.sp.Solve")]
    [InlineTemplate("_sp.solve({0}, {1})")]
    public static extern List<SymbolicExpression> solve(SymbolicExpression equation, SymbolicVariable symbol);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicTrigonometry.Sine", "PythonSharp.SymPy.sp.Sin")]
    [InlineTemplate("_sp.sin({0})")]
    public static extern SymbolicExpression sin(SymbolicExpression expr);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicTrigonometry.Cosine", "PythonSharp.SymPy.sp.Cos")]
    [InlineTemplate("_sp.cos({0})")]
    public static extern SymbolicExpression cos(SymbolicExpression expr);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicTrigonometry.Exponential", "PythonSharp.SymPy.sp.Exp")]
    [InlineTemplate("_sp.exp({0})")]
    public static extern SymbolicExpression exp(SymbolicExpression expr);
}

```

### `stdlib/02_scientific_and_ai/07_sympy/02_sympy.csharp.d.ps`

```csharp
namespace PythonSharp.SymPy;

using PythonSharp.Core;
using PythonSharp.SymbolicMath;
extern using sympy as _sp;

[SurfaceLevel(3)]
[MapsTo("_sp")]
public static primitive class sp
{
    [CanonicalApi("PythonSharp.SymbolicMath.SymbolFactory.DeclareSymbol")]
    [InlineTemplate("_sp.symbols({0})")]
    public static extern SymbolicVariable Symbols(string name);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolFactory.ParseSymbolicExpression")]
    [InlineTemplate("_sp.sympify({0})")]
    public static extern SymbolicExpression Sympify(string expressionText);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicCalculus.DifferentiateWithRespectTo")]
    [InlineTemplate("_sp.diff({0}, {1}, {2})")]
    public static extern SymbolicExpression Diff(SymbolicExpression expr, SymbolicVariable variable, int order = 1);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicCalculus.IntegrateIndefinite")]
    [InlineTemplate("_sp.integrate({0}, {1})")]
    public static extern SymbolicExpression Integrate(SymbolicExpression expr, SymbolicVariable variable);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicCalculus.IntegrateDefinite")]
    [InlineTemplate("_sp.integrate({0}, ({1}, {2}, {3}))")]
    public static extern SymbolicExpression IntegrateDefinite(SymbolicExpression expr, SymbolicVariable variable, double lowerBound, double upperBound);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicAlgebra.SimplifyExpression")]
    [InlineTemplate("_sp.simplify({0})")]
    public static extern SymbolicExpression Simplify(SymbolicExpression expr);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicAlgebra.SolveAlgebraicEquation")]
    [InlineTemplate("_sp.solve({0}, {1})")]
    public static extern List<SymbolicExpression> Solve(SymbolicExpression equation, SymbolicVariable variable);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicTrigonometry.Sine")]
    [InlineTemplate("_sp.sin({0})")]
    public static extern SymbolicExpression Sin(SymbolicExpression expr);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicTrigonometry.Cosine")]
    [InlineTemplate("_sp.cos({0})")]
    public static extern SymbolicExpression Cos(SymbolicExpression expr);

    [CanonicalApi("PythonSharp.SymbolicMath.SymbolicTrigonometry.Exponential")]
    [InlineTemplate("_sp.exp({0})")]
    public static extern SymbolicExpression Exp(SymbolicExpression expr);
}

```

### `stdlib/02_scientific_and_ai/07_sympy/03_symbolicmath.enterprise.d.ps`

```csharp
namespace PythonSharp.SymbolicMath;

using PythonSharp.Core;
extern using sympy as _sp;

[SurfaceLevel(1)]
[MapsTo("_sp")]
public static primitive class SymbolFactory
{
    [InlineTemplate("_sp.symbols({0})")]
    public static extern SymbolicVariable DeclareSymbol(string symbolIdentifier);

    [InlineTemplate("_sp.sympify({0})")]
    public static extern SymbolicExpression ParseSymbolicExpression(string mathematicalExpression);
}

[SurfaceLevel(1)]
[MapsTo("_sp")]
public static primitive class SymbolicCalculus
{
    [InlineTemplate("_sp.diff({0}, {1}, {2})")]
    public static extern SymbolicExpression DifferentiateWithRespectTo(SymbolicExpression expression, SymbolicVariable variable, int derivativeOrder = 1);

    [InlineTemplate("_sp.integrate({0}, {1})")]
    public static extern SymbolicExpression IntegrateIndefinite(SymbolicExpression integrand, SymbolicVariable integrationVariable);

    [InlineTemplate("_sp.integrate({0}, ({1}, {2}, {3}))")]
    public static extern SymbolicExpression IntegrateDefinite(SymbolicExpression integrand, SymbolicVariable integrationVariable, double lowerLimit, double upperLimit);
}

[SurfaceLevel(1)]
[MapsTo("_sp")]
public static primitive class SymbolicAlgebra
{
    [InlineTemplate("_sp.simplify({0})")]
    public static extern SymbolicExpression SimplifyExpression(SymbolicExpression expression);

    [InlineTemplate("_sp.solve({0}, {1})")]
    public static extern List<SymbolicExpression> SolveAlgebraicEquation(SymbolicExpression equationEqualsZero, SymbolicVariable targetVariable);
}

[SurfaceLevel(1)]
[MapsTo("_sp")]
public static primitive class SymbolicTrigonometry
{
    [InlineTemplate("_sp.sin({0})")]
    public static extern SymbolicExpression Sine(SymbolicExpression angleExpression);

    [InlineTemplate("_sp.cos({0})")]
    public static extern SymbolicExpression Cosine(SymbolicExpression angleExpression);

    [InlineTemplate("_sp.exp({0})")]
    public static extern SymbolicExpression Exponential(SymbolicExpression exponentExpression);
}

```

---

## 7. `08_qiskit` (Quantum Computing Circuits, Gates & Statevector Simulation)

`08_qiskit` defines `QuantumRegisterCircuit` (`qiskit.QuantumCircuit`) and `QuantumStatevector` (`qiskit.quantum_info.Statevector`), depending on `PythonSharp.Numerics.Tensors` (`NDArray<double>`) for probability vectors and exposing all three surfaces (`qiskit`, `PythonSharp.Qiskit`, and `PythonSharp.QuantumComputing`).

### `stdlib/02_scientific_and_ai/08_qiskit/00_qiskit.primitives.d.ps`

```csharp
namespace PythonSharp.QuantumComputing;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using qiskit as _qk;
extern using qiskit.quantum_info as _qi;

[MapsTo("qiskit.QuantumCircuit")]
[RuntimeType("qiskit.QuantumCircuit")]
public primitive class QuantumRegisterCircuit
{
    // --- Triple-Surface Properties ---
    [InlineTemplate("int({self}.num_qubits)")]
    public extern int QubitCount { get; }

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.QubitCount")]
    [InlineTemplate("int({self}.num_qubits)")]
    public extern int NumQubits { get; }

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.QubitCount", "NumQubits")]
    [InlineTemplate("int({self}.num_qubits)")]
    public extern int num_qubits { get; }

    [InlineTemplate("int({self}.depth())")]
    public extern int CircuitDepth { get; }

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.CircuitDepth")]
    [MapsTo("depth")]
    public extern int Depth();

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.CircuitDepth", "Depth")]
    [MapsTo("depth")]
    public extern int depth();

    // --- Surface 1: Self-Documenting Enterprise Gate Methods ---
    [MapsTo("h")]
    public extern void ApplyHadamardGate(int targetQubit);

    [MapsTo("x")]
    public extern void ApplyPauliXGate(int targetQubit);

    [MapsTo("y")]
    public extern void ApplyPauliYGate(int targetQubit);

    [MapsTo("z")]
    public extern void ApplyPauliZGate(int targetQubit);

    [MapsTo("rx")]
    public extern void ApplyRotationXGate(double angleRadians, int targetQubit);

    [MapsTo("ry")]
    public extern void ApplyRotationYGate(double angleRadians, int targetQubit);

    [MapsTo("rz")]
    public extern void ApplyRotationZGate(double angleRadians, int targetQubit);

    [MapsTo("cx")]
    public extern void ApplyControlledNotGate(int controlQubit, int targetQubit);

    [MapsTo("cz")]
    public extern void ApplyControlledZGate(int controlQubit, int targetQubit);

    [MapsTo("swap")]
    public extern void ApplySwapGate(int firstQubit, int secondQubit);

    [MapsTo("measure_all")]
    public extern void MeasureAllQubits();

    [InlineTemplate("str({self}.draw('text'))")]
    public extern string RenderAsciiCircuitDiagram();

    // --- Surface 3: C#-Standardized Gate Methods ---
    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyHadamardGate")]
    [MapsTo("h")]
    public extern void Hadamard(int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyPauliXGate")]
    [MapsTo("x")]
    public extern void PauliX(int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyPauliYGate")]
    [MapsTo("y")]
    public extern void PauliY(int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyPauliZGate")]
    [MapsTo("z")]
    public extern void PauliZ(int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyRotationXGate")]
    [MapsTo("rx")]
    public extern void RotateX(double theta, int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyRotationYGate")]
    [MapsTo("ry")]
    public extern void RotateY(double theta, int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyRotationZGate")]
    [MapsTo("rz")]
    public extern void RotateZ(double theta, int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyControlledNotGate")]
    [MapsTo("cx")]
    public extern void CNot(int controlQubit, int targetQubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyControlledZGate")]
    [MapsTo("cz")]
    public extern void CZ(int controlQubit, int targetQubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplySwapGate")]
    [MapsTo("swap")]
    public extern void Swap(int qubitA, int qubitB);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.MeasureAllQubits")]
    [MapsTo("measure_all")]
    public extern void MeasureAll();

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.RenderAsciiCircuitDiagram")]
    [InlineTemplate("str({self}.draw('text'))")]
    public extern string DrawText();

    // --- Surface 2: Raw Python snake_case Gate Methods ---
    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyHadamardGate", "Hadamard")]
    [MapsTo("h")]
    public extern void h(int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyPauliXGate", "PauliX")]
    [MapsTo("x")]
    public extern void x(int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyPauliYGate", "PauliY")]
    [MapsTo("y")]
    public extern void y(int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyPauliZGate", "PauliZ")]
    [MapsTo("z")]
    public extern void z(int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyRotationXGate", "RotateX")]
    [MapsTo("rx")]
    public extern void rx(double theta, int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyRotationYGate", "RotateY")]
    [MapsTo("ry")]
    public extern void ry(double theta, int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyRotationZGate", "RotateZ")]
    [MapsTo("rz")]
    public extern void rz(double theta, int qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyControlledNotGate", "CNot")]
    [MapsTo("cx")]
    public extern void cx(int control_qubit, int target_qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplyControlledZGate", "CZ")]
    [MapsTo("cz")]
    public extern void cz(int control_qubit, int target_qubit);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.ApplySwapGate", "Swap")]
    [MapsTo("swap")]
    public extern void swap(int qubit1, int qubit2);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.MeasureAllQubits", "MeasureAll")]
    [MapsTo("measure_all")]
    public extern void measure_all();

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumRegisterCircuit.RenderAsciiCircuitDiagram", "DrawText")]
    [InlineTemplate("str({self}.draw('text'))")]
    public extern string draw();
}

[MapsTo("qiskit.quantum_info.Statevector")]
[RuntimeType("qiskit.quantum_info.Statevector")]
public primitive class QuantumStatevector
{
    [MapsTo("probabilities")]
    public extern NDArray<double> ComputeMeasurementProbabilities();

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumStatevector.ComputeMeasurementProbabilities")]
    [MapsTo("probabilities")]
    public extern NDArray<double> Probabilities();

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumStatevector.ComputeMeasurementProbabilities", "Probabilities")]
    [MapsTo("probabilities")]
    public extern NDArray<double> probabilities();

    [MapsTo("probabilities_dict")]
    public extern Dict<string, double> ComputeBitstringProbabilityMap();

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumStatevector.ComputeBitstringProbabilityMap")]
    [MapsTo("probabilities_dict")]
    public extern Dict<string, double> ProbabilitiesDict();

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumStatevector.ComputeBitstringProbabilityMap", "ProbabilitiesDict")]
    [MapsTo("probabilities_dict")]
    public extern Dict<string, double> probabilities_dict();
}

```

### `stdlib/02_scientific_and_ai/08_qiskit/01_qiskit.raw.d.ps`

```csharp
namespace qiskit;

using PythonSharp.Core;
using PythonSharp.QuantumComputing;
extern using qiskit as _qk;
extern using qiskit.quantum_info as _qi;

[SurfaceLevel(2)]
[MapsTo("_qi")]
public static primitive class QuantumInfoModule
{
    [CanonicalApi("PythonSharp.QuantumComputing.QuantumSimulator.SimulateStatevectorFromCircuit", "PythonSharp.Qiskit.qk.QuantumInfo.FromInstruction")]
    [InlineTemplate("_qi.Statevector.from_instruction({0})")]
    public static extern QuantumStatevector from_instruction(QuantumRegisterCircuit circuit);
}

[SurfaceLevel(2)]
[MapsTo("_qk")]
public static primitive class qk
{
    [InlineTemplate("_qi")]
    public static extern QuantumInfoModule quantum_info { get; }

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumCircuitFactory.CreateQuantumCircuit", "PythonSharp.Qiskit.qk.CreateCircuit")]
    [InlineTemplate("_qk.QuantumCircuit({0})")]
    public static extern QuantumRegisterCircuit QuantumCircuit(int num_qubits);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumCircuitFactory.CreateQuantumAndClassicalCircuit", "PythonSharp.Qiskit.qk.CreateCircuit")]
    [InlineTemplate("_qk.QuantumCircuit({0}, {1})")]
    public static extern QuantumRegisterCircuit QuantumCircuit(int num_qubits, int num_clbits);
}

```

### `stdlib/02_scientific_and_ai/08_qiskit/02_qiskit.csharp.d.ps`

```csharp
namespace PythonSharp.Qiskit;

using PythonSharp.Core;
using PythonSharp.QuantumComputing;
extern using qiskit as _qk;
extern using qiskit.quantum_info as _qi;

[SurfaceLevel(3)]
[MapsTo("_qi")]
public static primitive class QiskitQuantumInfoModule
{
    [CanonicalApi("PythonSharp.QuantumComputing.QuantumSimulator.SimulateStatevectorFromCircuit")]
    [InlineTemplate("_qi.Statevector.from_instruction({0})")]
    public static extern QuantumStatevector FromInstruction(QuantumRegisterCircuit circuit);
}

[SurfaceLevel(3)]
[MapsTo("_qk")]
public static primitive class qk
{
    [InlineTemplate("_qi")]
    public static extern QiskitQuantumInfoModule QuantumInfo { get; }

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumCircuitFactory.CreateQuantumCircuit")]
    [InlineTemplate("_qk.QuantumCircuit({0})")]
    public static extern QuantumRegisterCircuit CreateCircuit(int qubits);

    [CanonicalApi("PythonSharp.QuantumComputing.QuantumCircuitFactory.CreateQuantumAndClassicalCircuit")]
    [InlineTemplate("_qk.QuantumCircuit({0}, {1})")]
    public static extern QuantumRegisterCircuit CreateCircuit(int qubits, int classicalBits);
}

```

### `stdlib/02_scientific_and_ai/08_qiskit/03_quantum.enterprise.d.ps`

```csharp
namespace PythonSharp.QuantumComputing;

using PythonSharp.Core;
extern using qiskit as _qk;
extern using qiskit.quantum_info as _qi;

[SurfaceLevel(1)]
[MapsTo("_qk")]
public static primitive class QuantumCircuitFactory
{
    [InlineTemplate("_qk.QuantumCircuit({0})")]
    public static extern QuantumRegisterCircuit CreateQuantumCircuit(int qubitCount);

    [InlineTemplate("_qk.QuantumCircuit({0}, {1})")]
    public static extern QuantumRegisterCircuit CreateQuantumAndClassicalCircuit(int qubitCount, int classicalBitCount);

    [InlineTemplate("(lambda _c: (_c.h(0), _c.cx(0, 1), _c)[2])(_qk.QuantumCircuit(2))")]
    public static extern QuantumRegisterCircuit CreateBellPairEntangledCircuit();
}

[SurfaceLevel(1)]
[MapsTo("_qi")]
public static primitive class QuantumSimulator
{
    [InlineTemplate("_qi.Statevector.from_instruction({0})")]
    public static extern QuantumStatevector SimulateStatevectorFromCircuit(QuantumRegisterCircuit quantumCircuit);
}

```

---

Would you like me to also generate the expanded `stdlib/02_scientific_and_ai/01_numpy/` four-file bundle (with the `RandomModule`, tuple creation overloads, and ML reduction methods) or a multi-package showcase `.ps` sample testing all 7 scientific/AI bundles across Surfaces 1, 2, and 3?
