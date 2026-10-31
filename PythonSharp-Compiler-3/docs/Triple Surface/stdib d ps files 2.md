Here are the expanded four-file `.d.ps` declarations for **`01_numpy`** (with `RandomModule`, 1D/2D/3D/tuple creation overloads, element-wise ufuncs, and ML axis reductions), followed by five essential AI/ML package bundles (**`09_polars`**, **`10_xgboost_lightgbm`**, **`11_optuna`**, **`12_transformers`**, and **`13_faiss_onnxruntime`**) covering high-speed columnar ETL, gradient-boosted decision trees, hyperparameter optimization, Hugging Face pretrained language models, and FAISS vector search + ONNX Runtime inference without relying on TensorFlow or JAX.

Each file adheres to the single-namespace-per-compilation-unit grammar (`CompilationUnit ::= NamespaceDecl? ImportDecl* TypeDecl* EOF ;`) and the four-file Triple-Surface convention (`00_*.primitives.d.ps`, `01_*.raw.d.ps`, `02_*.csharp.d.ps`, `03_*.enterprise.d.ps`).

---

## 1. `01_numpy` (Expanded AI/ML Tensor Reductions, UFuncs, Tuple Overloads & Random Sampling)

This expanded `01_numpy` bundle upgrades `NDArray<T>` with ML axis reductions (`sum`, `mean`, `std`, `min`, `max`, `argmax`, `argmin`), shape transformations (`flatten`, `squeeze`, `astype<TOut>`, `tolist`), tuple creation overloads (`(int, int)` and `(int, int, int)`), element-wise ufuncs (`exp`, `log`, `sqrt`, `clip`, `where`, `concatenate`, `stack`), and `RandomModule` (`np.random` / `np.Random` / `RandomTensorGenerator`).

### `stdlib/02_scientific_and_ai/01_numpy/00_numpy.primitives.d.ps`

```csharp
namespace PythonSharp.Numerics.Tensors;

using PythonSharp.Core;
extern using numpy as np;

[MapsTo("np.ndarray")]
[RuntimeType("np.ndarray")]
public primitive class NDArray<T> : IEnumerable<T>
{
    // ========================================================================
    // 1. PROPERTIES (Surface 1: Enterprise | Surface 3: C# | Surface 2: Raw)
    // ========================================================================
    [InlineTemplate("list({self}.shape)")]
    public extern List<int> DimensionShape { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.DimensionShape")]
    [InlineTemplate("list({self}.shape)")]
    public extern List<int> Shape { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.DimensionShape", "Shape")]
    [InlineTemplate("list({self}.shape)")]
    public extern List<int> shape { get; }

    [InlineTemplate("int({self}.ndim)")]
    public extern int NumberOfDimensions { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.NumberOfDimensions")]
    [InlineTemplate("int({self}.ndim)")]
    public extern int NDim { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.NumberOfDimensions", "NDim")]
    [InlineTemplate("int({self}.ndim)")]
    public extern int ndim { get; }

    [InlineTemplate("int({self}.size)")]
    public extern int TotalElementCount { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.TotalElementCount")]
    [InlineTemplate("int({self}.size)")]
    public extern int Size { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.TotalElementCount", "Size")]
    [InlineTemplate("int({self}.size)")]
    public extern int size { get; }

    [InlineTemplate("str({self}.dtype)")]
    public extern string ElementDataType { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ElementDataType")]
    [InlineTemplate("str({self}.dtype)")]
    public extern string DType { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ElementDataType", "DType")]
    [InlineTemplate("str({self}.dtype)")]
    public extern string dtype { get; }

    [InlineTemplate("{self}.T")]
    public extern NDArray<T> TransposedMatrix { get; }

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.TransposedMatrix")]
    [InlineTemplate("{self}.T")]
    public extern NDArray<T> T { get; }

    // ========================================================================
    // 2. SHAPE & TYPE TRANSFORMATIONS
    // ========================================================================
    [InlineTemplate("{self}.reshape(({0}, {1}))")]
    public extern NDArray<T> ReshapeToMatrix(int rows, int columns);

    [InlineTemplate("{self}.reshape(({0}, {1}, {2}))")]
    public extern NDArray<T> ReshapeTo3DTensor(int depth, int rows, int columns);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ReshapeToMatrix")]
    [MapsTo("reshape")]
    public extern NDArray<T> Reshape(params int[] shape);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ReshapeToMatrix", "Reshape")]
    [MapsTo("reshape")]
    public extern NDArray<T> reshape(params int[] shape);

    [MapsTo("flatten")]
    public extern NDArray<T> FlattenTo1DVector();

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FlattenTo1DVector")]
    [MapsTo("flatten")]
    public extern NDArray<T> Flatten();

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FlattenTo1DVector", "Flatten")]
    [MapsTo("flatten")]
    public extern NDArray<T> flatten();

    [MapsTo("squeeze")]
    public extern NDArray<T> SqueezeSingletonDimensions(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.SqueezeSingletonDimensions")]
    [MapsTo("squeeze")]
    public extern NDArray<T> Squeeze(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.SqueezeSingletonDimensions", "Squeeze")]
    [MapsTo("squeeze")]
    public extern NDArray<T> squeeze(int? axis = null);

    [InlineTemplate("{self}.astype({0})")]
    public extern NDArray<TOut> CastElementsTo<TOut>(string targetDtype);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.CastElementsTo")]
    [InlineTemplate("{self}.astype({0})")]
    public extern NDArray<TOut> AsType<TOut>(string dtype);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.CastElementsTo", "AsType")]
    [InlineTemplate("{self}.astype({0})")]
    public extern NDArray<TOut> astype<TOut>(string dtype);

    [MapsTo("copy")]
    public extern NDArray<T> CloneDeepCopy();

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.CloneDeepCopy")]
    [MapsTo("copy")]
    public extern NDArray<T> Copy();

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.CloneDeepCopy", "Copy")]
    [MapsTo("copy")]
    public extern NDArray<T> copy();

    [MapsTo("tolist")]
    public extern List<T> ConvertToList();

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ConvertToList")]
    [MapsTo("tolist")]
    public extern List<T> ToList();

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ConvertToList", "ToList")]
    [MapsTo("tolist")]
    public extern List<T> tolist();

    // ========================================================================
    // 3. STATISTICAL & AXIS REDUCTIONS (ML Feature Scaling & Logit ArgMax)
    // ========================================================================
    [MapsTo("mean")]
    public extern double ComputeArithmeticMean(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ComputeArithmeticMean")]
    [MapsTo("mean")]
    public extern double Mean(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ComputeArithmeticMean", "Mean")]
    [MapsTo("mean")]
    public extern double mean(int? axis = null);

    [MapsTo("std")]
    public extern double ComputeStandardDeviation(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ComputeStandardDeviation")]
    [MapsTo("std")]
    public extern double Std(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ComputeStandardDeviation", "Std")]
    [MapsTo("std")]
    public extern double std(int? axis = null);

    [MapsTo("var")]
    public extern double ComputeVariance(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ComputeVariance")]
    [MapsTo("var")]
    public extern double Var(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ComputeVariance", "Var")]
    [MapsTo("var")]
    public extern double @var(int? axis = null);

    [MapsTo("sum")]
    public extern T ComputeSum(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ComputeSum")]
    [MapsTo("sum")]
    public extern T Sum(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ComputeSum", "Sum")]
    [MapsTo("sum")]
    public extern T sum(int? axis = null);

    [MapsTo("min")]
    public extern T FindMinimumValue(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FindMinimumValue")]
    [MapsTo("min")]
    public extern T Min(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FindMinimumValue", "Min")]
    [MapsTo("min")]
    public extern T min(int? axis = null);

    [MapsTo("max")]
    public extern T FindMaximumValue(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FindMaximumValue")]
    [MapsTo("max")]
    public extern T Max(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FindMaximumValue", "Max")]
    [MapsTo("max")]
    public extern T max(int? axis = null);

    [MapsTo("argmax")]
    public extern int FindIndexOfMaximum(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FindIndexOfMaximum")]
    [MapsTo("argmax")]
    public extern int ArgMax(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FindIndexOfMaximum", "ArgMax")]
    [MapsTo("argmax")]
    public extern int argmax(int? axis = null);

    [MapsTo("argmin")]
    public extern int FindIndexOfMinimum(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FindIndexOfMinimum")]
    [MapsTo("argmin")]
    public extern int ArgMin(int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.FindIndexOfMinimum", "ArgMin")]
    [MapsTo("argmin")]
    public extern int argmin(int? axis = null);

    [MapsTo("clip")]
    public extern NDArray<T> ClipValuesToRange(T minLimit, T maxLimit);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ClipValuesToRange")]
    [MapsTo("clip")]
    public extern NDArray<T> Clip(T min, T max);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.ClipValuesToRange", "Clip")]
    [MapsTo("clip")]
    public extern NDArray<T> clip(T min, T max);

    // ========================================================================
    // 4. LINEAR ALGEBRA & MULTI-AXIS SLICING
    // ========================================================================
    [InlineTemplate("({self} @ {0})")]
    public extern NDArray<T> MultiplyMatrix(NDArray<T> other);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.MultiplyMatrix")]
    [MapsTo("dot")]
    public extern NDArray<T> Dot(NDArray<T> other);

    [CanonicalApi("PythonSharp.Numerics.Tensors.NDArray.MultiplyMatrix", "Dot")]
    [MapsTo("dot")]
    public extern NDArray<T> dot(NDArray<T> other);

    [InlineTemplate("{self}[{0}]")]
    public extern NDArray<T> this[params object[] slices] { get; set; }
}

```

### `stdlib/02_scientific_and_ai/01_numpy/01_numpy.raw.d.ps`

```csharp
namespace numpy;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using numpy as _np;

[SurfaceLevel(2)]
[MapsTo("_np.linalg")]
public static primitive class LinalgModule
{
    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeMultiplicativeInverse", "PythonSharp.NumPy.np.LinearAlgebra.Inverse")]
    [InlineTemplate("_np.linalg.inv({0})")]
    public static extern NDArray<double> inv(NDArray<double> a);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeDeterminant", "PythonSharp.NumPy.np.LinearAlgebra.Determinant")]
    [InlineTemplate("_np.linalg.det({0})")]
    public static extern double det(NDArray<double> a);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.SolveLinearEquations", "PythonSharp.NumPy.np.LinearAlgebra.Solve")]
    [InlineTemplate("_np.linalg.solve({0}, {1})")]
    public static extern NDArray<double> solve(NDArray<double> a, NDArray<double> b);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeEuclideanNorm", "PythonSharp.NumPy.np.LinearAlgebra.Norm")]
    [InlineTemplate("_np.linalg.norm({0}, axis={1})")]
    public static extern double norm(NDArray<double> x, int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeEigenDecomposition", "PythonSharp.NumPy.np.LinearAlgebra.Eig")]
    [InlineTemplate("_np.linalg.eig({0})")]
    public static extern (NDArray<double> eigenvalues, NDArray<double> eigenvectors) eig(NDArray<double> a);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeSingularValueDecomposition", "PythonSharp.NumPy.np.LinearAlgebra.Svd")]
    [InlineTemplate("_np.linalg.svd({0})")]
    public static extern (NDArray<double> u, NDArray<double> s, NDArray<double> vh) svd(NDArray<double> a);
}

[SurfaceLevel(2)]
[MapsTo("_np.random")]
public static primitive class RandomModule
{
    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SetRandomSeed", "PythonSharp.NumPy.np.Random.Seed")]
    [InlineTemplate("_np.random.seed({0})")]
    public static extern void seed(int seedValue);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleUniformMatrix", "PythonSharp.NumPy.np.Random.Rand")]
    [InlineTemplate("_np.random.rand({0}, {1})")]
    public static extern NDArray<double> rand(int d0, int d1);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleStandardNormalMatrix", "PythonSharp.NumPy.np.Random.RandN")]
    [InlineTemplate("_np.random.randn({0}, {1})")]
    public static extern NDArray<double> randn(int d0, int d1);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleGaussianDistribution", "PythonSharp.NumPy.np.Random.Normal")]
    [InlineTemplate("_np.random.normal({0}, {1}, {2})")]
    public static extern NDArray<double> normal(double loc = 0.0, double scale = 1.0, (int, int)? size = null);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleUniformDistribution", "PythonSharp.NumPy.np.Random.Uniform")]
    [InlineTemplate("_np.random.uniform({0}, {1}, {2})")]
    public static extern NDArray<double> uniform(double low = 0.0, double high = 1.0, (int, int)? size = null);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleRandomIntegers", "PythonSharp.NumPy.np.Random.RandInt")]
    [InlineTemplate("_np.random.randint({0}, {1}, size={2})")]
    public static extern NDArray<int> randint(int low, int high, (int, int) size);
}

[SurfaceLevel(2)]
[MapsTo("_np")]
public static primitive class np
{
    [InlineTemplate("_np.linalg")]
    public static extern LinalgModule linalg { get; }

    [InlineTemplate("_np.random")]
    public static extern RandomModule random { get; }

    // --- Creation Overloads: 1D, 2D (int, int), 2D Tuple, 3D Tuple ---
    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateFromSequence", "PythonSharp.NumPy.np.Array")]
    [InlineTemplate("_np.array({0})")]
    public static extern NDArray<T> array<T>(IEnumerable<T> data);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateZeroVector", "PythonSharp.NumPy.np.Zeros")]
    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> zeros(int length);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateZeroMatrix", "PythonSharp.NumPy.np.Zeros")]
    [InlineTemplate("_np.zeros(({0}, {1}))")]
    public static extern NDArray<double> zeros(int rows, int cols);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateZeroMatrix", "PythonSharp.NumPy.np.Zeros")]
    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> zeros((int, int) shape);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateZero3DTensor", "PythonSharp.NumPy.np.Zeros")]
    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> zeros((int, int, int) shape);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateOnesVector", "PythonSharp.NumPy.np.Ones")]
    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> ones(int length);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateOnesMatrix", "PythonSharp.NumPy.np.Ones")]
    [InlineTemplate("_np.ones(({0}, {1}))")]
    public static extern NDArray<double> ones(int rows, int cols);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateOnesMatrix", "PythonSharp.NumPy.np.Ones")]
    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> ones((int, int) shape);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateOnes3DTensor", "PythonSharp.NumPy.np.Ones")]
    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> ones((int, int, int) shape);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateConstantFilledMatrix", "PythonSharp.NumPy.np.Full")]
    [InlineTemplate("_np.full({0}, {1})")]
    public static extern NDArray<T> full<T>((int, int) shape, T fill_value);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateIdentityMatrix", "PythonSharp.NumPy.np.Eye")]
    [InlineTemplate("_np.eye({0})")]
    public static extern NDArray<double> eye(int n);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateSteppedRangeVector", "PythonSharp.NumPy.np.Arange")]
    [InlineTemplate("_np.arange({0}, {1}, {2})")]
    public static extern NDArray<double> arange(double start, double stop, double step = 1.0);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateLinearlySpacedVector", "PythonSharp.NumPy.np.LinSpace")]
    [InlineTemplate("_np.linspace({0}, {1}, {2})")]
    public static extern NDArray<double> linspace(double start, double stop, int num = 50);

    // --- Element-Wise Mathematical UFuncs & Joins ---
    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.ComputeExponential", "PythonSharp.NumPy.np.Exp")]
    [InlineTemplate("_np.exp({0})")]
    public static extern NDArray<double> exp(NDArray<double> x);

    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.ComputeNaturalLogarithm", "PythonSharp.NumPy.np.Log")]
    [InlineTemplate("_np.log({0})")]
    public static extern NDArray<double> log(NDArray<double> x);

    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.ComputeSquareRoot", "PythonSharp.NumPy.np.Sqrt")]
    [InlineTemplate("_np.sqrt({0})")]
    public static extern NDArray<double> sqrt(NDArray<double> x);

    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.ClipTensorValues", "PythonSharp.NumPy.np.Clip")]
    [InlineTemplate("_np.clip({0}, {1}, {2})")]
    public static extern NDArray<T> clip<T>(NDArray<T> a, T a_min, T a_max);

    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.SelectConditionally", "PythonSharp.NumPy.np.Where")]
    [InlineTemplate("_np.where({0}, {1}, {2})")]
    public static extern NDArray<T> where<T>(NDArray<bool> condition, NDArray<T> x, NDArray<T> y);

    [CanonicalApi("PythonSharp.Numerics.TensorManipulation.ConcatenateAlongAxis", "PythonSharp.NumPy.np.Concatenate")]
    [InlineTemplate("_np.concatenate({0}, axis={1})")]
    public static extern NDArray<T> concatenate<T>(IEnumerable<NDArray<T>> arrays, int axis = 0);

    [CanonicalApi("PythonSharp.Numerics.TensorManipulation.StackAlongNewAxis", "PythonSharp.NumPy.np.Stack")]
    [InlineTemplate("_np.stack({0}, axis={1})")]
    public static extern NDArray<T> stack<T>(IEnumerable<NDArray<T>> arrays, int axis = 0);

    [CanonicalApi("PythonSharp.Numerics.TensorManipulation.ExpandDimensions", "PythonSharp.NumPy.np.ExpandDims")]
    [InlineTemplate("_np.expand_dims({0}, axis={1})")]
    public static extern NDArray<T> expand_dims<T>(NDArray<T> a, int axis);
}

```

### `stdlib/02_scientific_and_ai/01_numpy/02_numpy.csharp.d.ps`

```csharp
namespace PythonSharp.NumPy;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using numpy as _np;

[SurfaceLevel(3)]
[MapsTo("_np.linalg")]
public static primitive class NumPyLinearAlgebraModule
{
    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeMultiplicativeInverse")]
    [InlineTemplate("_np.linalg.inv({0})")]
    public static extern NDArray<double> Inverse(NDArray<double> matrix);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeDeterminant")]
    [InlineTemplate("_np.linalg.det({0})")]
    public static extern double Determinant(NDArray<double> matrix);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.SolveLinearEquations")]
    [InlineTemplate("_np.linalg.solve({0}, {1})")]
    public static extern NDArray<double> Solve(NDArray<double> matrixA, NDArray<double> vectorB);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeEuclideanNorm")]
    [InlineTemplate("_np.linalg.norm({0}, axis={1})")]
    public static extern double Norm(NDArray<double> tensor, int? axis = null);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeEigenDecomposition")]
    [InlineTemplate("_np.linalg.eig({0})")]
    public static extern (NDArray<double> Eigenvalues, NDArray<double> Eigenvectors) Eig(NDArray<double> matrix);

    [CanonicalApi("PythonSharp.Numerics.MatrixOperations.ComputeSingularValueDecomposition")]
    [InlineTemplate("_np.linalg.svd({0})")]
    public static extern (NDArray<double> U, NDArray<double> SingularValues, NDArray<double> Vh) Svd(NDArray<double> matrix);
}

[SurfaceLevel(3)]
[MapsTo("_np.random")]
public static primitive class NumPyRandomModule
{
    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SetRandomSeed")]
    [InlineTemplate("_np.random.seed({0})")]
    public static extern void Seed(int seedValue);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleUniformMatrix")]
    [InlineTemplate("_np.random.rand({0}, {1})")]
    public static extern NDArray<double> Rand(int rows, int cols);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleStandardNormalMatrix")]
    [InlineTemplate("_np.random.randn({0}, {1})")]
    public static extern NDArray<double> RandN(int rows, int cols);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleGaussianDistribution")]
    [InlineTemplate("_np.random.normal({0}, {1}, {2})")]
    public static extern NDArray<double> Normal(double mean = 0.0, double stdDev = 1.0, (int, int)? shape = null);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleUniformDistribution")]
    [InlineTemplate("_np.random.uniform({0}, {1}, {2})")]
    public static extern NDArray<double> Uniform(double low = 0.0, double high = 1.0, (int, int)? shape = null);

    [CanonicalApi("PythonSharp.Numerics.RandomTensorGenerator.SampleRandomIntegers")]
    [InlineTemplate("_np.random.randint({0}, {1}, size={2})")]
    public static extern NDArray<int> RandInt(int lowInclusive, int highExclusive, (int, int) shape);
}

[SurfaceLevel(3)]
[MapsTo("_np")]
public static primitive class np
{
    [InlineTemplate("_np.linalg")]
    public static extern NumPyLinearAlgebraModule LinearAlgebra { get; }

    [InlineTemplate("_np.random")]
    public static extern NumPyRandomModule Random { get; }

    // --- Creation Overloads ---
    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateFromSequence")]
    [InlineTemplate("_np.array({0})")]
    public static extern NDArray<T> Array<T>(IEnumerable<T> items);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateZeroVector")]
    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> Zeros(int length);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateZeroMatrix")]
    [InlineTemplate("_np.zeros(({0}, {1}))")]
    public static extern NDArray<double> Zeros(int rows, int cols);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateZeroMatrix")]
    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> Zeros((int, int) shape);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateZero3DTensor")]
    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> Zeros((int, int, int) shape);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateOnesVector")]
    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> Ones(int length);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateOnesMatrix")]
    [InlineTemplate("_np.ones(({0}, {1}))")]
    public static extern NDArray<double> Ones(int rows, int cols);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateOnesMatrix")]
    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> Ones((int, int) shape);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateOnes3DTensor")]
    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> Ones((int, int, int) shape);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateConstantFilledMatrix")]
    [InlineTemplate("_np.full({0}, {1})")]
    public static extern NDArray<T> Full<T>((int, int) shape, T fillValue);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateIdentityMatrix")]
    [InlineTemplate("_np.eye({0})")]
    public static extern NDArray<double> Eye(int dimensionSize);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateSteppedRangeVector")]
    [InlineTemplate("_np.arange({0}, {1}, {2})")]
    public static extern NDArray<double> Arange(double start, double stop, double step = 1.0);

    [CanonicalApi("PythonSharp.Numerics.ArrayFactory.CreateLinearlySpacedVector")]
    [InlineTemplate("_np.linspace({0}, {1}, {2})")]
    public static extern NDArray<double> LinSpace(double start, double stop, int count = 50);

    // --- Element-Wise UFuncs & Joins ---
    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.ComputeExponential")]
    [InlineTemplate("_np.exp({0})")]
    public static extern NDArray<double> Exp(NDArray<double> tensor);

    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.ComputeNaturalLogarithm")]
    [InlineTemplate("_np.log({0})")]
    public static extern NDArray<double> Log(NDArray<double> tensor);

    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.ComputeSquareRoot")]
    [InlineTemplate("_np.sqrt({0})")]
    public static extern NDArray<double> Sqrt(NDArray<double> tensor);

    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.ClipTensorValues")]
    [InlineTemplate("_np.clip({0}, {1}, {2})")]
    public static extern NDArray<T> Clip<T>(NDArray<T> tensor, T minVal, T maxVal);

    [CanonicalApi("PythonSharp.Numerics.ElementWiseMath.SelectConditionally")]
    [InlineTemplate("_np.where({0}, {1}, {2})")]
    public static extern NDArray<T> Where<T>(NDArray<bool> conditionMask, NDArray<T> whenTrue, NDArray<T> whenFalse);

    [CanonicalApi("PythonSharp.Numerics.TensorManipulation.ConcatenateAlongAxis")]
    [InlineTemplate("_np.concatenate({0}, axis={1})")]
    public static extern NDArray<T> Concatenate<T>(IEnumerable<NDArray<T>> tensors, int axis = 0);

    [CanonicalApi("PythonSharp.Numerics.TensorManipulation.StackAlongNewAxis")]
    [InlineTemplate("_np.stack({0}, axis={1})")]
    public static extern NDArray<T> Stack<T>(IEnumerable<NDArray<T>> tensors, int axis = 0);

    [CanonicalApi("PythonSharp.Numerics.TensorManipulation.ExpandDimensions")]
    [InlineTemplate("_np.expand_dims({0}, axis={1})")]
    public static extern NDArray<T> ExpandDims<T>(NDArray<T> tensor, int axis);
}

```

### `stdlib/02_scientific_and_ai/01_numpy/03_numerics.enterprise.d.ps`

```csharp
namespace PythonSharp.Numerics;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using numpy as _np;

[SurfaceLevel(1)]
[MapsTo("_np")]
public static primitive class ArrayFactory
{
    [InlineTemplate("_np.array({0})")]
    public static extern NDArray<T> CreateFromSequence<T>(IEnumerable<T> items);

    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> CreateZeroVector(int elementCount);

    [InlineTemplate("_np.zeros(({0}, {1}))")]
    public static extern NDArray<double> CreateZeroMatrix(int rows, int columns);

    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> CreateZeroMatrix((int Rows, int Columns) shape);

    [InlineTemplate("_np.zeros({0})")]
    public static extern NDArray<double> CreateZero3DTensor((int Depth, int Rows, int Columns) shape);

    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> CreateOnesVector(int elementCount);

    [InlineTemplate("_np.ones(({0}, {1}))")]
    public static extern NDArray<double> CreateOnesMatrix(int rows, int columns);

    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> CreateOnesMatrix((int Rows, int Columns) shape);

    [InlineTemplate("_np.ones({0})")]
    public static extern NDArray<double> CreateOnes3DTensor((int Depth, int Rows, int Columns) shape);

    [InlineTemplate("_np.full({0}, {1})")]
    public static extern NDArray<T> CreateConstantFilledMatrix<T>((int Rows, int Columns) shape, T constantValue);

    [InlineTemplate("_np.eye({0})")]
    public static extern NDArray<double> CreateIdentityMatrix(int dimensionSize);

    [InlineTemplate("_np.arange({0}, {1}, {2})")]
    public static extern NDArray<double> CreateSteppedRangeVector(double startInclusive, double stopExclusive, double stepIncrement = 1.0);

    [InlineTemplate("_np.linspace({0}, {1}, {2})")]
    public static extern NDArray<double> CreateLinearlySpacedVector(double startValue, double stopValue, int sampleCount = 50);
}

[SurfaceLevel(1)]
[MapsTo("_np.linalg")]
public static primitive class MatrixOperations
{
    [InlineTemplate("_np.linalg.inv({0})")]
    public static extern NDArray<double> ComputeMultiplicativeInverse(NDArray<double> squareMatrix);

    [InlineTemplate("_np.linalg.det({0})")]
    public static extern double ComputeDeterminant(NDArray<double> squareMatrix);

    [InlineTemplate("_np.linalg.solve({0}, {1})")]
    public static extern NDArray<double> SolveLinearEquations(NDArray<double> coefficientMatrixA, NDArray<double> dependentVectorB);

    [InlineTemplate("_np.linalg.norm({0}, axis={1})")]
    public static extern double ComputeEuclideanNorm(NDArray<double> tensor, int? axis = null);

    [InlineTemplate("_np.linalg.eig({0})")]
    public static extern (NDArray<double> Eigenvalues, NDArray<double> Eigenvectors) ComputeEigenDecomposition(NDArray<double> squareMatrix);

    [InlineTemplate("_np.linalg.svd({0})")]
    public static extern (NDArray<double> LeftSingularVectors, NDArray<double> SingularValues, NDArray<double> RightSingularVectorsTransposed) ComputeSingularValueDecomposition(NDArray<double> matrix);
}

[SurfaceLevel(1)]
[MapsTo("_np.random")]
public static primitive class RandomTensorGenerator
{
    [InlineTemplate("_np.random.seed({0})")]
    public static extern void SetRandomSeed(int seedValue);

    [InlineTemplate("_np.random.rand({0}, {1})")]
    public static extern NDArray<double> SampleUniformMatrix(int rows, int columns);

    [InlineTemplate("_np.random.randn({0}, {1})")]
    public static extern NDArray<double> SampleStandardNormalMatrix(int rows, int columns);

    [InlineTemplate("_np.random.normal({0}, {1}, {2})")]
    public static extern NDArray<double> SampleGaussianDistribution(double mean = 0.0, double standardDeviation = 1.0, (int Rows, int Columns)? matrixShape = null);

    [InlineTemplate("_np.random.uniform({0}, {1}, {2})")]
    public static extern NDArray<double> SampleUniformDistribution(double lowerBound = 0.0, double upperBound = 1.0, (int Rows, int Columns)? matrixShape = null);

    [InlineTemplate("_np.random.randint({0}, {1}, size={2})")]
    public static extern NDArray<int> SampleRandomIntegers(int lowInclusive, int highExclusive, (int Rows, int Columns) matrixShape);
}

[SurfaceLevel(1)]
[MapsTo("_np")]
public static primitive class ElementWiseMath
{
    [InlineTemplate("_np.exp({0})")]
    public static extern NDArray<double> ComputeExponential(NDArray<double> inputTensor);

    [InlineTemplate("_np.log({0})")]
    public static extern NDArray<double> ComputeNaturalLogarithm(NDArray<double> inputTensor);

    [InlineTemplate("_np.sqrt({0})")]
    public static extern NDArray<double> ComputeSquareRoot(NDArray<double> inputTensor);

    [InlineTemplate("_np.clip({0}, {1}, {2})")]
    public static extern NDArray<T> ClipTensorValues<T>(NDArray<T> inputTensor, T minimumBound, T maximumBound);

    [InlineTemplate("_np.where({0}, {1}, {2})")]
    public static extern NDArray<T> SelectConditionally<T>(NDArray<bool> conditionMask, NDArray<T> valueWhenTrue, NDArray<T> valueWhenFalse);
}

[SurfaceLevel(1)]
[MapsTo("_np")]
public static primitive class TensorManipulation
{
    [InlineTemplate("_np.concatenate({0}, axis={1})")]
    public static extern NDArray<T> ConcatenateAlongAxis<T>(IEnumerable<NDArray<T>> tensors, int concatenationAxis = 0);

    [InlineTemplate("_np.stack({0}, axis={1})")]
    public static extern NDArray<T> StackAlongNewAxis<T>(IEnumerable<NDArray<T>> tensors, int newAxisIndex = 0);

    [InlineTemplate("_np.expand_dims({0}, axis={1})")]
    public static extern NDArray<T> ExpandDimensions<T>(NDArray<T> tensor, int insertedAxisIndex);
}

```

---

## 2. `09_polars` (High-Performance Rust-Backed Lazy & Eager Columnar DataFrames)

Polars is a key modern companion to Pandas for high-throughput ML feature engineering and lazy query optimization.

### `stdlib/02_scientific_and_ai/09_polars/00_polars.primitives.d.ps`

```csharp
namespace PythonSharp.DataScience.Columnar;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using polars as _pl;

[MapsTo("polars.Expr")]
[RuntimeType("polars.Expr")]
public primitive class PolarsColumnExpression
{
    // --- Surface 1: Enterprise Self-Documenting Methods ---
    [MapsTo("alias")]
    public extern PolarsColumnExpression WithColumnAlias(string newColumnName);

    [MapsTo("mean")]
    public extern PolarsColumnExpression AggregateMean();

    [MapsTo("sum")]
    public extern PolarsColumnExpression AggregateSum();

    [MapsTo("fill_null")]
    public extern PolarsColumnExpression FillNullValuesWith(object replacementValue);

    [InlineTemplate("({self} > {0})")]
    public extern PolarsColumnExpression IsGreaterThan(double thresholdValue);

    [InlineTemplate("({self} == {0})")]
    public extern PolarsColumnExpression IsEqualTo(object targetValue);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsColumnExpression.WithColumnAlias")]
    [MapsTo("alias")]
    public extern PolarsColumnExpression Alias(string name);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsColumnExpression.AggregateMean")]
    [MapsTo("mean")]
    public extern PolarsColumnExpression Mean();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsColumnExpression.AggregateSum")]
    [MapsTo("sum")]
    public extern PolarsColumnExpression Sum();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsColumnExpression.FillNullValuesWith")]
    [MapsTo("fill_null")]
    public extern PolarsColumnExpression FillNull(object value);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsColumnExpression.WithColumnAlias", "Alias")]
    [MapsTo("alias")]
    public extern PolarsColumnExpression alias(string name);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsColumnExpression.AggregateMean", "Mean")]
    [MapsTo("mean")]
    public extern PolarsColumnExpression mean();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsColumnExpression.AggregateSum", "Sum")]
    [MapsTo("sum")]
    public extern PolarsColumnExpression sum();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsColumnExpression.FillNullValuesWith", "FillNull")]
    [MapsTo("fill_null")]
    public extern PolarsColumnExpression fill_null(object value);
}

[MapsTo("polars.DataFrame")]
[RuntimeType("polars.DataFrame")]
public primitive class PolarsDataFrame<TRow>
{
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) TableDimensions { get; }

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.TableDimensions")]
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) Shape { get; }

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.TableDimensions", "Shape")]
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) shape { get; }

    // --- Surface 1: Enterprise Self-Documenting Methods ---
    [MapsTo("select")]
    public extern PolarsDataFrame<TRow> SelectColumns(params PolarsColumnExpression[] expressions);

    [MapsTo("filter")]
    public extern PolarsDataFrame<TRow> FilterRows(PolarsColumnExpression predicateExpression);

    [MapsTo("with_columns")]
    public extern PolarsDataFrame<TRow> WithComputedColumns(params PolarsColumnExpression[] expressions);

    [MapsTo("drop_nulls")]
    public extern PolarsDataFrame<TRow> DropRowsWithNullValues();

    [MapsTo("to_numpy")]
    public extern NDArray<double> ConvertToNumPyMatrix();

    [MapsTo("write_parquet")]
    public extern void WriteToParquetFile(string outputFilePath);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.SelectColumns")]
    [MapsTo("select")]
    public extern PolarsDataFrame<TRow> Select(params PolarsColumnExpression[] exprs);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.FilterRows")]
    [MapsTo("filter")]
    public extern PolarsDataFrame<TRow> Filter(PolarsColumnExpression predicate);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.WithComputedColumns")]
    [MapsTo("with_columns")]
    public extern PolarsDataFrame<TRow> WithColumns(params PolarsColumnExpression[] exprs);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.DropRowsWithNullValues")]
    [MapsTo("drop_nulls")]
    public extern PolarsDataFrame<TRow> DropNulls();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.ConvertToNumPyMatrix")]
    [MapsTo("to_numpy")]
    public extern NDArray<double> ToNumpy();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.WriteToParquetFile")]
    [MapsTo("write_parquet")]
    public extern void WriteParquet(string path);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.SelectColumns", "Select")]
    [MapsTo("select")]
    public extern PolarsDataFrame<TRow> select(params PolarsColumnExpression[] exprs);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.FilterRows", "Filter")]
    [MapsTo("filter")]
    public extern PolarsDataFrame<TRow> filter(PolarsColumnExpression predicate);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.WithComputedColumns", "WithColumns")]
    [MapsTo("with_columns")]
    public extern PolarsDataFrame<TRow> with_columns(params PolarsColumnExpression[] exprs);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.DropRowsWithNullValues", "DropNulls")]
    [MapsTo("drop_nulls")]
    public extern PolarsDataFrame<TRow> drop_nulls();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.ConvertToNumPyMatrix", "ToNumpy")]
    [MapsTo("to_numpy")]
    public extern NDArray<double> to_numpy();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsDataFrame.WriteToParquetFile", "WriteParquet")]
    [MapsTo("write_parquet")]
    public extern void write_parquet(string file);
}

[MapsTo("polars.LazyFrame")]
[RuntimeType("polars.LazyFrame")]
public primitive class PolarsLazyFrame<TRow>
{
    [MapsTo("select")]
    public extern PolarsLazyFrame<TRow> SelectColumnsLazy(params PolarsColumnExpression[] expressions);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsLazyFrame.SelectColumnsLazy")]
    [MapsTo("select")]
    public extern PolarsLazyFrame<TRow> Select(params PolarsColumnExpression[] exprs);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsLazyFrame.SelectColumnsLazy", "Select")]
    [MapsTo("select")]
    public extern PolarsLazyFrame<TRow> select(params PolarsColumnExpression[] exprs);

    [MapsTo("filter")]
    public extern PolarsLazyFrame<TRow> FilterRowsLazy(PolarsColumnExpression predicateExpression);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsLazyFrame.FilterRowsLazy")]
    [MapsTo("filter")]
    public extern PolarsLazyFrame<TRow> Filter(PolarsColumnExpression predicate);

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsLazyFrame.FilterRowsLazy", "Filter")]
    [MapsTo("filter")]
    public extern PolarsLazyFrame<TRow> filter(PolarsColumnExpression predicate);

    [MapsTo("collect")]
    public extern PolarsDataFrame<TRow> ExecuteAndMaterialize();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsLazyFrame.ExecuteAndMaterialize")]
    [MapsTo("collect")]
    public extern PolarsDataFrame<TRow> Collect();

    [CanonicalApi("PythonSharp.DataScience.Columnar.PolarsLazyFrame.ExecuteAndMaterialize", "Collect")]
    [MapsTo("collect")]
    public extern PolarsDataFrame<TRow> collect();
}

```

### `stdlib/02_scientific_and_ai/09_polars/01_polars.raw.d.ps`

```csharp
namespace polars;

using PythonSharp.Core;
using PythonSharp.DataScience.Columnar;
extern using polars as _pl;

[SurfaceLevel(2)]
[MapsTo("_pl")]
public static primitive class pl
{
    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarDataReader.ReadCsvFileEager", "PythonSharp.Polars.pl.ReadCsv")]
    [InlineTemplate("_pl.read_csv({0})")]
    public static extern PolarsDataFrame<object> read_csv(string source);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarDataReader.ReadParquetFileEager", "PythonSharp.Polars.pl.ReadParquet")]
    [InlineTemplate("_pl.read_parquet({0})")]
    public static extern PolarsDataFrame<object> read_parquet(string source);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarDataReader.ScanCsvFileLazy", "PythonSharp.Polars.pl.ScanCsv")]
    [InlineTemplate("_pl.scan_csv({0})")]
    public static extern PolarsLazyFrame<object> scan_csv(string source);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarDataReader.ScanParquetFileLazy", "PythonSharp.Polars.pl.ScanParquet")]
    [InlineTemplate("_pl.scan_parquet({0})")]
    public static extern PolarsLazyFrame<object> scan_parquet(string source);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarExpressionBuilder.ReferenceColumn", "PythonSharp.Polars.pl.Col")]
    [InlineTemplate("_pl.col({0})")]
    public static extern PolarsColumnExpression col(string name);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarExpressionBuilder.ConstantLiteral", "PythonSharp.Polars.pl.Lit")]
    [InlineTemplate("_pl.lit({0})")]
    public static extern PolarsColumnExpression lit(object value);
}

```

### `stdlib/02_scientific_and_ai/09_polars/02_polars.csharp.d.ps`

```csharp
namespace PythonSharp.Polars;

using PythonSharp.Core;
using PythonSharp.DataScience.Columnar;
extern using polars as _pl;

[SurfaceLevel(3)]
[MapsTo("_pl")]
public static primitive class pl
{
    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarDataReader.ReadCsvFileEager")]
    [InlineTemplate("_pl.read_csv({0})")]
    public static extern PolarsDataFrame<TRow> ReadCsv<TRow>(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarDataReader.ReadParquetFileEager")]
    [InlineTemplate("_pl.read_parquet({0})")]
    public static extern PolarsDataFrame<TRow> ReadParquet<TRow>(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarDataReader.ScanCsvFileLazy")]
    [InlineTemplate("_pl.scan_csv({0})")]
    public static extern PolarsLazyFrame<TRow> ScanCsv<TRow>(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarDataReader.ScanParquetFileLazy")]
    [InlineTemplate("_pl.scan_parquet({0})")]
    public static extern PolarsLazyFrame<TRow> ScanParquet<TRow>(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarExpressionBuilder.ReferenceColumn")]
    [InlineTemplate("_pl.col({0})")]
    public static extern PolarsColumnExpression Col(string columnName);

    [CanonicalApi("PythonSharp.DataScience.Columnar.ColumnarExpressionBuilder.ConstantLiteral")]
    [InlineTemplate("_pl.lit({0})")]
    public static extern PolarsColumnExpression Lit(object literalValue);
}

```

### `stdlib/02_scientific_and_ai/09_polars/03_columnar.enterprise.d.ps`

```csharp
namespace PythonSharp.DataScience.Columnar;

using PythonSharp.Core;
extern using polars as _pl;

[SurfaceLevel(1)]
[MapsTo("_pl")]
public static primitive class ColumnarDataReader
{
    [InlineTemplate("_pl.read_csv({0})")]
    public static extern PolarsDataFrame<TRow> ReadCsvFileEager<TRow>(string csvFilePath);

    [InlineTemplate("_pl.read_parquet({0})")]
    public static extern PolarsDataFrame<TRow> ReadParquetFileEager<TRow>(string parquetFilePath);

    [InlineTemplate("_pl.scan_csv({0})")]
    public static extern PolarsLazyFrame<TRow> ScanCsvFileLazy<TRow>(string csvFilePath);

    [InlineTemplate("_pl.scan_parquet({0})")]
    public static extern PolarsLazyFrame<TRow> ScanParquetFileLazy<TRow>(string parquetFilePath);
}

[SurfaceLevel(1)]
[MapsTo("_pl")]
public static primitive class ColumnarExpressionBuilder
{
    [InlineTemplate("_pl.col({0})")]
    public static extern PolarsColumnExpression ReferenceColumn(string columnName);

    [InlineTemplate("_pl.lit({0})")]
    public static extern PolarsColumnExpression ConstantLiteral(object literalValue);
}

```

---

## 3. `10_xgboost_lightgbm` (Gradient Boosted Decision Trees for Tabular ML)

XGBoost and LightGBM dominate structured/tabular machine learning competitions and enterprise risk/churn modeling, integrating directly with `ISupervisedEstimator<TFeature, TLabel>` from `05_sklearn` and `NDArray<T>` from `01_numpy`.

### `stdlib/02_scientific_and_ai/10_xgboost_lightgbm/00_gbdt.primitives.d.ps`

```csharp
namespace PythonSharp.MachineLearning.GradientBoosting;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.MachineLearning.Classical;
extern using xgboost as _xgb;
extern using lightgbm as _lgb;

[MapsTo("xgboost.XGBClassifier")]
[RuntimeType("object")]
public primitive class XgBoostClassifierModel : ISupervisedEstimator<double, int>
{
    [InlineTemplate("{self}.feature_importances_")]
    public extern NDArray<double> FeatureImportanceScores { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("fit")]
    public extern void TrainOnLabeledDataset(NDArray<double> featureMatrix, NDArray<int> targetLabels);

    [MapsTo("predict")]
    public extern NDArray<int> PredictLabels(NDArray<double> featureMatrix);

    [MapsTo("predict_proba")]
    public extern NDArray<double> PredictClassProbabilities(NDArray<double> featureMatrix);

    [MapsTo("score")]
    public extern double EvaluateModelScore(NDArray<double> featureMatrix, NDArray<int> groundTruthLabels);

    [MapsTo("save_model")]
    public extern void SaveModelToFile(string modelFilePath);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.TrainOnLabeledDataset")]
    [MapsTo("fit")]
    public extern void Fit(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.PredictLabels")]
    [MapsTo("predict")]
    public extern NDArray<int> Predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.PredictClassProbabilities")]
    [MapsTo("predict_proba")]
    public extern NDArray<double> PredictProba(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.EvaluateModelScore")]
    [MapsTo("score")]
    public extern double Score(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.SaveModelToFile")]
    [MapsTo("save_model")]
    public extern void SaveModel(string fname);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.TrainOnLabeledDataset", "Fit")]
    [MapsTo("fit")]
    public extern void fit(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.PredictLabels", "Predict")]
    [MapsTo("predict")]
    public extern NDArray<int> predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.PredictClassProbabilities", "PredictProba")]
    [MapsTo("predict_proba")]
    public extern NDArray<double> predict_proba(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.EvaluateModelScore", "Score")]
    [MapsTo("score")]
    public extern double score(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostClassifierModel.SaveModelToFile", "SaveModel")]
    [MapsTo("save_model")]
    public extern void save_model(string fname);
}

[MapsTo("xgboost.XGBRegressor")]
[RuntimeType("object")]
public primitive class XgBoostRegressorModel : ISupervisedEstimator<double, double>
{
    [MapsTo("fit")]
    public extern void TrainOnLabeledDataset(NDArray<double> featureMatrix, NDArray<double> targetValues);

    [MapsTo("predict")]
    public extern NDArray<double> PredictLabels(NDArray<double> featureMatrix);

    [MapsTo("score")]
    public extern double EvaluateModelScore(NDArray<double> featureMatrix, NDArray<double> groundTruthValues);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostRegressorModel.TrainOnLabeledDataset")]
    [MapsTo("fit")]
    public extern void Fit(NDArray<double> X, NDArray<double> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostRegressorModel.PredictLabels")]
    [MapsTo("predict")]
    public extern NDArray<double> Predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostRegressorModel.EvaluateModelScore")]
    [MapsTo("score")]
    public extern double Score(NDArray<double> X, NDArray<double> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostRegressorModel.TrainOnLabeledDataset", "Fit")]
    [MapsTo("fit")]
    public extern void fit(NDArray<double> X, NDArray<double> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostRegressorModel.PredictLabels", "Predict")]
    [MapsTo("predict")]
    public extern NDArray<double> predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.XgBoostRegressorModel.EvaluateModelScore", "Score")]
    [MapsTo("score")]
    public extern double score(NDArray<double> X, NDArray<double> y);
}

[MapsTo("lightgbm.LGBMClassifier")]
[RuntimeType("object")]
public primitive class LightGbmClassifierModel : ISupervisedEstimator<double, int>
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

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.LightGbmClassifierModel.TrainOnLabeledDataset")]
    [MapsTo("fit")]
    public extern void Fit(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.LightGbmClassifierModel.PredictLabels")]
    [MapsTo("predict")]
    public extern NDArray<int> Predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.LightGbmClassifierModel.PredictClassProbabilities")]
    [MapsTo("predict_proba")]
    public extern NDArray<double> PredictProba(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.LightGbmClassifierModel.EvaluateModelScore")]
    [MapsTo("score")]
    public extern double Score(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.LightGbmClassifierModel.TrainOnLabeledDataset", "Fit")]
    [MapsTo("fit")]
    public extern void fit(NDArray<double> X, NDArray<int> y);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.LightGbmClassifierModel.PredictLabels", "Predict")]
    [MapsTo("predict")]
    public extern NDArray<int> predict(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.LightGbmClassifierModel.PredictClassProbabilities", "PredictProba")]
    [MapsTo("predict_proba")]
    public extern NDArray<double> predict_proba(NDArray<double> X);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.LightGbmClassifierModel.EvaluateModelScore", "Score")]
    [MapsTo("score")]
    public extern double score(NDArray<double> X, NDArray<int> y);
}

```

### `stdlib/02_scientific_and_ai/10_xgboost_lightgbm/01_gbdt.raw.d.ps`

```csharp
namespace xgboost;

using PythonSharp.Core;
using PythonSharp.MachineLearning.GradientBoosting;
extern using xgboost as _xgb;
extern using lightgbm as _lgb;

[SurfaceLevel(2)]
[MapsTo("_xgb")]
public static primitive class xgb
{
    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.GradientBoostingFactory.CreateXgBoostClassifier", "PythonSharp.GradientBoosting.xgb.XGBClassifier")]
    [InlineTemplate("_xgb.XGBClassifier(n_estimators={0}, max_depth={1}, learning_rate={2}, random_state={3})")]
    public static extern XgBoostClassifierModel XGBClassifier(int n_estimators = 100, int max_depth = 6, double learning_rate = 0.1, int random_state = 42);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.GradientBoostingFactory.CreateXgBoostRegressor", "PythonSharp.GradientBoosting.xgb.XGBRegressor")]
    [InlineTemplate("_xgb.XGBRegressor(n_estimators={0}, max_depth={1}, learning_rate={2}, random_state={3})")]
    public static extern XgBoostRegressorModel XGBRegressor(int n_estimators = 100, int max_depth = 6, double learning_rate = 0.1, int random_state = 42);
}

[SurfaceLevel(2)]
[MapsTo("_lgb")]
public static primitive class lgb
{
    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.GradientBoostingFactory.CreateLightGbmClassifier", "PythonSharp.GradientBoosting.lgb.LGBMClassifier")]
    [InlineTemplate("_lgb.LGBMClassifier(n_estimators={0}, num_leaves={1}, learning_rate={2}, random_state={3})")]
    public static extern LightGbmClassifierModel LGBMClassifier(int n_estimators = 100, int num_leaves = 31, double learning_rate = 0.1, int random_state = 42);
}

```

### `stdlib/02_scientific_and_ai/10_xgboost_lightgbm/02_gbdt.csharp.d.ps`

```csharp
namespace PythonSharp.GradientBoosting;

using PythonSharp.Core;
using PythonSharp.MachineLearning.GradientBoosting;
extern using xgboost as _xgb;
extern using lightgbm as _lgb;

[SurfaceLevel(3)]
[MapsTo("_xgb")]
public static primitive class xgb
{
    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.GradientBoostingFactory.CreateXgBoostClassifier")]
    [InlineTemplate("_xgb.XGBClassifier(n_estimators={0}, max_depth={1}, learning_rate={2}, random_state={3})")]
    public static extern XgBoostClassifierModel XGBClassifier(int nEstimators = 100, int maxDepth = 6, double learningRate = 0.1, int randomState = 42);

    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.GradientBoostingFactory.CreateXgBoostRegressor")]
    [InlineTemplate("_xgb.XGBRegressor(n_estimators={0}, max_depth={1}, learning_rate={2}, random_state={3})")]
    public static extern XgBoostRegressorModel XGBRegressor(int nEstimators = 100, int maxDepth = 6, double learningRate = 0.1, int randomState = 42);
}

[SurfaceLevel(3)]
[MapsTo("_lgb")]
public static primitive class lgb
{
    [CanonicalApi("PythonSharp.MachineLearning.GradientBoosting.GradientBoostingFactory.CreateLightGbmClassifier")]
    [InlineTemplate("_lgb.LGBMClassifier(n_estimators={0}, num_leaves={1}, learning_rate={2}, random_state={3})")]
    public static extern LightGbmClassifierModel LGBMClassifier(int nEstimators = 100, int numLeaves = 31, double learningRate = 0.1, int randomState = 42);
}

```

### `stdlib/02_scientific_and_ai/10_xgboost_lightgbm/03_gbdt.enterprise.d.ps`

```csharp
namespace PythonSharp.MachineLearning.GradientBoosting;

using PythonSharp.Core;
extern using xgboost as _xgb;
extern using lightgbm as _lgb;

[SurfaceLevel(1)]
public static primitive class GradientBoostingFactory
{
    [InlineTemplate("_xgb.XGBClassifier(n_estimators={0}, max_depth={1}, learning_rate={2}, random_state={3})")]
    public static extern XgBoostClassifierModel CreateXgBoostClassifier(
        int numberOfBoostedTrees = 100,
        int maximumTreeDepth = 6,
        double shrinkageLearningRate = 0.1,
        int randomSeed = 42);

    [InlineTemplate("_xgb.XGBRegressor(n_estimators={0}, max_depth={1}, learning_rate={2}, random_state={3})")]
    public static extern XgBoostRegressorModel CreateXgBoostRegressor(
        int numberOfBoostedTrees = 100,
        int maximumTreeDepth = 6,
        double shrinkageLearningRate = 0.1,
        int randomSeed = 42);

    [InlineTemplate("_lgb.LGBMClassifier(n_estimators={0}, num_leaves={1}, learning_rate={2}, random_state={3})")]
    public static extern LightGbmClassifierModel CreateLightGbmClassifier(
        int numberOfBoostedTrees = 100,
        int maximumTreeLeaves = 31,
        double shrinkageLearningRate = 0.1,
        int randomSeed = 42);
}

```

---

## 4. `11_optuna` (Automated Bayesian Hyperparameter Optimization)

Optuna pairs with Scikit-Learn, XGBoost, LightGBM, and PyTorch to automate hyperparameter search via Tree-structured Parzen Estimators (TPE).

### `stdlib/02_scientific_and_ai/11_optuna/00_optuna.primitives.d.ps`

```csharp
namespace PythonSharp.MachineLearning.HyperparameterTuning;

using PythonSharp.Core;
extern using optuna as _optuna;

[MapsTo("optuna.trial.Trial")]
[RuntimeType("object")]
public primitive class HyperparameterTrial
{
    [InlineTemplate("int({self}.number)")]
    public extern int TrialNumber { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [InlineTemplate("{self}.suggest_float({0}, {1}, {2}, log={3})")]
    public extern double SampleFloatHyperparameter(string parameterName, double lowerBound, double upperBound, bool logScale = false);

    [InlineTemplate("{self}.suggest_int({0}, {1}, {2})")]
    public extern int SampleIntegerHyperparameter(string parameterName, int lowerBound, int upperBound);

    [InlineTemplate("{self}.suggest_categorical({0}, {1})")]
    public extern T SampleCategoricalHyperparameter<T>(string parameterName, List<T> candidateChoices);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.HyperparameterTrial.SampleFloatHyperparameter")]
    [InlineTemplate("{self}.suggest_float({0}, {1}, {2}, log={3})")]
    public extern double SuggestFloat(string name, double low, double high, bool log = false);

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.HyperparameterTrial.SampleIntegerHyperparameter")]
    [InlineTemplate("{self}.suggest_int({0}, {1}, {2})")]
    public extern int SuggestInt(string name, int low, int high);

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.HyperparameterTrial.SampleCategoricalHyperparameter")]
    [InlineTemplate("{self}.suggest_categorical({0}, {1})")]
    public extern T SuggestCategorical<T>(string name, List<T> choices);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.HyperparameterTrial.SampleFloatHyperparameter", "SuggestFloat")]
    [InlineTemplate("{self}.suggest_float({0}, {1}, {2}, log={3})")]
    public extern double suggest_float(string name, double low, double high, bool log = false);

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.HyperparameterTrial.SampleIntegerHyperparameter", "SuggestInt")]
    [InlineTemplate("{self}.suggest_int({0}, {1}, {2})")]
    public extern int suggest_int(string name, int low, int high);

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.HyperparameterTrial.SampleCategoricalHyperparameter", "SuggestCategorical")]
    [InlineTemplate("{self}.suggest_categorical({0}, {1})")]
    public extern T suggest_categorical<T>(string name, List<T> choices);
}

[MapsTo("optuna.study.Study")]
[RuntimeType("object")]
public primitive class OptimizationStudy
{
    [InlineTemplate("float({self}.best_value)")]
    public extern double BestObjectiveValue { get; }

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.OptimizationStudy.BestObjectiveValue")]
    [InlineTemplate("float({self}.best_value)")]
    public extern double BestValue { get; }

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.OptimizationStudy.BestObjectiveValue", "BestValue")]
    [InlineTemplate("float({self}.best_value)")]
    public extern double best_value { get; }

    [InlineTemplate("dict({self}.best_params)")]
    public extern Dict<string, object> BestHyperparameterMap { get; }

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.OptimizationStudy.BestHyperparameterMap")]
    [InlineTemplate("dict({self}.best_params)")]
    public extern Dict<string, object> BestParams { get; }

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.OptimizationStudy.BestHyperparameterMap", "BestParams")]
    [InlineTemplate("dict({self}.best_params)")]
    public extern Dict<string, object> best_params { get; }

    // --- Triple-Surface Study Execution ---
    [InlineTemplate("{self}.optimize({0}, n_trials={1})")]
    public extern void RunHyperparameterOptimization(Func<HyperparameterTrial, double> objectiveFunction, int trialCount = 50);

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.OptimizationStudy.RunHyperparameterOptimization")]
    [InlineTemplate("{self}.optimize({0}, n_trials={1})")]
    public extern void Optimize(Func<HyperparameterTrial, double> objective, int nTrials = 50);

    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.OptimizationStudy.RunHyperparameterOptimization", "Optimize")]
    [InlineTemplate("{self}.optimize({0}, n_trials={1})")]
    public extern void optimize(Func<HyperparameterTrial, double> func, int n_trials = 50);
}

```

### `stdlib/02_scientific_and_ai/11_optuna/01_optuna.raw.d.ps`

```csharp
namespace optuna;

using PythonSharp.Core;
using PythonSharp.MachineLearning.HyperparameterTuning;
extern using optuna as _optuna;

[SurfaceLevel(2)]
[MapsTo("_optuna")]
public static primitive class optuna
{
    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.HyperparameterStudyFactory.CreateOptimizationStudy", "PythonSharp.Optuna.optuna.CreateStudy")]
    [InlineTemplate("_optuna.create_study(direction={0})")]
    public static extern OptimizationStudy create_study(string direction = "maximize");
}

```

### `stdlib/02_scientific_and_ai/11_optuna/02_optuna.csharp.d.ps`

```csharp
namespace PythonSharp.Optuna;

using PythonSharp.Core;
using PythonSharp.MachineLearning.HyperparameterTuning;
extern using optuna as _optuna;

[SurfaceLevel(3)]
[MapsTo("_optuna")]
public static primitive class optuna
{
    [CanonicalApi("PythonSharp.MachineLearning.HyperparameterTuning.HyperparameterStudyFactory.CreateOptimizationStudy")]
    [InlineTemplate("_optuna.create_study(direction={0})")]
    public static extern OptimizationStudy CreateStudy(string direction = "maximize");
}

```

### `stdlib/02_scientific_and_ai/11_optuna/03_tuning.enterprise.d.ps`

```csharp
namespace PythonSharp.MachineLearning.HyperparameterTuning;

using PythonSharp.Core;
extern using optuna as _optuna;

[SurfaceLevel(1)]
[MapsTo("_optuna")]
public static primitive class HyperparameterStudyFactory
{
    [InlineTemplate("_optuna.create_study(direction={0})")]
    public static extern OptimizationStudy CreateOptimizationStudy(string optimizationDirection = "maximize");

    [InlineTemplate("_optuna.create_study(direction='minimize')")]
    public static extern OptimizationStudy CreateMinimizationStudy();

    [InlineTemplate("_optuna.create_study(direction='maximize')")]
    public static extern OptimizationStudy CreateMaximizationStudy();
}

```

---

## 5. `12_transformers` (Hugging Face Pretrained Language Models, Tokenizers & Pipelines)

`12_transformers` connects Hugging Face's `AutoTokenizer`, `AutoModel`, and `pipeline` to PyTorch `TorchTensor<T>` (`06_torch`) across all three syntactic surfaces.

### `stdlib/02_scientific_and_ai/12_transformers/00_transformers.primitives.d.ps`

```csharp
namespace PythonSharp.ArtificialIntelligence.LanguageModels;

using PythonSharp.Core;
using PythonSharp.DeepLearning;
extern using transformers as _hf;

[MapsTo("transformers.PreTrainedTokenizerBase")]
[RuntimeType("object")]
public primitive class PretrainedTextTokenizer
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [InlineTemplate("{self}({0}, return_tensors='pt', padding={1}, truncation={2})")]
    public extern Dict<string, TorchTensor<int>> EncodeTextToPyTorchTensors(string inputText, bool padToMaxLength = true, bool truncateToMaxLength = true);

    [InlineTemplate("{self}.decode({0}, skip_special_tokens={1})")]
    public extern string DecodeTokenIdsToString(TorchTensor<int> tokenIds, bool skipSpecialTokens = true);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.PretrainedTextTokenizer.EncodeTextToPyTorchTensors")]
    [InlineTemplate("{self}({0}, return_tensors='pt', padding={1}, truncation={2})")]
    public extern Dict<string, TorchTensor<int>> TokenizeToPt(string text, bool padding = true, bool truncation = true);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.PretrainedTextTokenizer.DecodeTokenIdsToString")]
    [InlineTemplate("{self}.decode({0}, skip_special_tokens={1})")]
    public extern string Decode(TorchTensor<int> tokenIds, bool skipSpecialTokens = true);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.PretrainedTextTokenizer.EncodeTextToPyTorchTensors", "TokenizeToPt")]
    [InlineTemplate("{self}({0}, return_tensors={1}, padding={2}, truncation={3})")]
    public extern Dict<string, TorchTensor<int>> encode_batch(string text, string return_tensors = "pt", bool padding = true, bool truncation = true);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.PretrainedTextTokenizer.DecodeTokenIdsToString", "Decode")]
    [InlineTemplate("{self}.decode({0}, skip_special_tokens={1})")]
    public extern string decode(TorchTensor<int> token_ids, bool skip_special_tokens = true);
}

[MapsTo("transformers.PreTrainedModel")]
[RuntimeType("object")]
public primitive class PretrainedTransformerModel
{
    [MapsTo("to")]
    public extern PretrainedTransformerModel MoveModelToDevice(string targetDeviceName);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.PretrainedTransformerModel.MoveModelToDevice")]
    [MapsTo("to")]
    public extern PretrainedTransformerModel To(string device);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.PretrainedTransformerModel.MoveModelToDevice", "To")]
    [MapsTo("to")]
    public extern PretrainedTransformerModel to(string device);

    [MapsTo("eval")]
    public extern PretrainedTransformerModel SetEvaluationInferenceMode();

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.PretrainedTransformerModel.SetEvaluationInferenceMode")]
    [MapsTo("eval")]
    public extern PretrainedTransformerModel Eval();

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.PretrainedTransformerModel.SetEvaluationInferenceMode", "Eval")]
    [MapsTo("eval")]
    public extern PretrainedTransformerModel eval();
}

[MapsTo("transformers.Pipeline")]
[RuntimeType("object")]
public primitive class InferenceTaskPipeline
{
    [InlineTemplate("{self}({0})")]
    public extern List<Dict<string, object>> RunInferenceOnText(string promptOrDocument);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.InferenceTaskPipeline.RunInferenceOnText")]
    [InlineTemplate("{self}({0})")]
    public extern List<Dict<string, object>> Invoke(string text);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.InferenceTaskPipeline.RunInferenceOnText", "Invoke")]
    [InlineTemplate("{self}({0})")]
    public extern List<Dict<string, object>> run(string text);
}

```

### `stdlib/02_scientific_and_ai/12_transformers/01_transformers.raw.d.ps`

```csharp
namespace transformers;

using PythonSharp.Core;
using PythonSharp.ArtificialIntelligence.LanguageModels;
extern using transformers as _hf;

[SurfaceLevel(2)]
[MapsTo("_hf.AutoTokenizer")]
public static primitive class AutoTokenizer
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.HuggingFaceHubLoader.LoadPretrainedTokenizer", "PythonSharp.Transformers.hf.AutoTokenizer.FromPretrained")]
    [InlineTemplate("_hf.AutoTokenizer.from_pretrained({0})")]
    public static extern PretrainedTextTokenizer from_pretrained(string pretrained_model_name_or_path);
}

[SurfaceLevel(2)]
[MapsTo("_hf.AutoModel")]
public static primitive class AutoModel
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.HuggingFaceHubLoader.LoadPretrainedTransformerModel", "PythonSharp.Transformers.hf.AutoModel.FromPretrained")]
    [InlineTemplate("_hf.AutoModel.from_pretrained({0})")]
    public static extern PretrainedTransformerModel from_pretrained(string pretrained_model_name_or_path);
}

[SurfaceLevel(2)]
[MapsTo("_hf")]
public static primitive class transformers
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.HuggingFaceHubLoader.CreateInferenceTaskPipeline", "PythonSharp.Transformers.hf.Pipeline")]
    [InlineTemplate("_hf.pipeline({0}, model={1})")]
    public static extern InferenceTaskPipeline pipeline(string task, string? model = null);
}

```

### `stdlib/02_scientific_and_ai/12_transformers/02_transformers.csharp.d.ps`

```csharp
namespace PythonSharp.Transformers;

using PythonSharp.Core;
using PythonSharp.ArtificialIntelligence.LanguageModels;
extern using transformers as _hf;

[SurfaceLevel(3)]
[MapsTo("_hf.AutoTokenizer")]
public static primitive class HfAutoTokenizerModule
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.HuggingFaceHubLoader.LoadPretrainedTokenizer")]
    [InlineTemplate("_hf.AutoTokenizer.from_pretrained({0})")]
    public static extern PretrainedTextTokenizer FromPretrained(string modelIdOrPath);
}

[SurfaceLevel(3)]
[MapsTo("_hf.AutoModel")]
public static primitive class HfAutoModelModule
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.HuggingFaceHubLoader.LoadPretrainedTransformerModel")]
    [InlineTemplate("_hf.AutoModel.from_pretrained({0})")]
    public static extern PretrainedTransformerModel FromPretrained(string modelIdOrPath);
}

[SurfaceLevel(3)]
[MapsTo("_hf")]
public static primitive class hf
{
    [InlineTemplate("_hf.AutoTokenizer")]
    public static extern HfAutoTokenizerModule AutoTokenizer { get; }

    [InlineTemplate("_hf.AutoModel")]
    public static extern HfAutoModelModule AutoModel { get; }

    [CanonicalApi("PythonSharp.ArtificialIntelligence.LanguageModels.HuggingFaceHubLoader.CreateInferenceTaskPipeline")]
    [InlineTemplate("_hf.pipeline({0}, model={1})")]
    public static extern InferenceTaskPipeline Pipeline(string taskName, string? modelId = null);
}

```

### `stdlib/02_scientific_and_ai/12_transformers/03_languagemodels.enterprise.d.ps`

```csharp
namespace PythonSharp.ArtificialIntelligence.LanguageModels;

using PythonSharp.Core;
extern using transformers as _hf;

[SurfaceLevel(1)]
[MapsTo("_hf")]
public static primitive class HuggingFaceHubLoader
{
    [InlineTemplate("_hf.AutoTokenizer.from_pretrained({0})")]
    public static extern PretrainedTextTokenizer LoadPretrainedTokenizer(string repositoryModelIdentifier);

    [InlineTemplate("_hf.AutoModel.from_pretrained({0})")]
    public static extern PretrainedTransformerModel LoadPretrainedTransformerModel(string repositoryModelIdentifier);

    [InlineTemplate("_hf.pipeline({0}, model={1})")]
    public static extern InferenceTaskPipeline CreateInferenceTaskPipeline(string taskCategory, string? repositoryModelIdentifier = null);
}

```

---

## 6. `13_faiss_onnxruntime` (Vector Similarity Search & High-Speed ONNX Model Inference)

FAISS (`IndexFlatL2`, `IndexFlatIP`) powers high-speed dense embedding similarity search for RAG pipelines, while ONNX Runtime (`InferenceSession`) executes exported models across CPU/CUDA/TensorRT providers using `NDArray<T>` (`01_numpy`).

### `stdlib/02_scientific_and_ai/13_faiss_onnxruntime/00_inference.primitives.d.ps`

```csharp
namespace PythonSharp.ArtificialIntelligence.Inference;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using faiss as _faiss;
extern using onnxruntime as _ort;

[MapsTo("faiss.IndexFlat")]
[RuntimeType("object")]
public primitive class VectorSimilarityIndex
{
    [InlineTemplate("int({self}.ntotal)")]
    public extern int IndexedVectorCount { get; }

    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorSimilarityIndex.IndexedVectorCount")]
    [InlineTemplate("int({self}.ntotal)")]
    public extern int NTotal { get; }

    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorSimilarityIndex.IndexedVectorCount", "NTotal")]
    [InlineTemplate("int({self}.ntotal)")]
    public extern int ntotal { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("add")]
    public extern void AddEmbeddingVectors(NDArray<double> embeddingMatrix);

    [MapsTo("search")]
    public extern (NDArray<double> Distances, NDArray<int> NeighborIndices) SearchNearestNeighbors(NDArray<double> queryEmbeddingMatrix, int topKCount);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorSimilarityIndex.AddEmbeddingVectors")]
    [MapsTo("add")]
    public extern void Add(NDArray<double> vectors);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorSimilarityIndex.SearchNearestNeighbors")]
    [MapsTo("search")]
    public extern (NDArray<double> Distances, NDArray<int> Indices) Search(NDArray<double> queries, int k);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorSimilarityIndex.AddEmbeddingVectors", "Add")]
    [MapsTo("add")]
    public extern void add(NDArray<double> x);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorSimilarityIndex.SearchNearestNeighbors", "Search")]
    [MapsTo("search")]
    public extern (NDArray<double> D, NDArray<int> I) search(NDArray<double> x, int k);
}

[MapsTo("onnxruntime.InferenceSession")]
[RuntimeType("object")]
public primitive class OnnxRuntimeInferenceSession
{
    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [InlineTemplate("{self}.run(None, {0})")]
    public extern List<NDArray<double>> ExecuteModelInference(Dict<string, NDArray<double>> namedInputFeeds);

    // --- Surface 3: C#-Standardized Methods ---
    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.OnnxRuntimeInferenceSession.ExecuteModelInference")]
    [InlineTemplate("{self}.run({0}, {1})")]
    public extern List<NDArray<double>> Run(List<string>? outputNames, Dict<string, NDArray<double>> inputFeed);

    // --- Surface 2: Raw Python snake_case Methods ---
    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.OnnxRuntimeInferenceSession.ExecuteModelInference", "Run")]
    [InlineTemplate("{self}.run({0}, {1})")]
    public extern List<NDArray<double>> run(List<string>? output_names, Dict<string, NDArray<double>> input_feed);
}

```

### `stdlib/02_scientific_and_ai/13_faiss_onnxruntime/01_inference.raw.d.ps`

```csharp
namespace faiss;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.ArtificialIntelligence.Inference;
extern using faiss as _faiss;
extern using onnxruntime as _ort;

[SurfaceLevel(2)]
[MapsTo("_faiss")]
public static primitive class faiss
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorIndexFactory.CreateEuclideanL2VectorIndex", "PythonSharp.VectorSearch.faiss.IndexFlatL2")]
    [InlineTemplate("_faiss.IndexFlatL2({0})")]
    public static extern VectorSimilarityIndex IndexFlatL2(int d);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorIndexFactory.CreateInnerProductVectorIndex", "PythonSharp.VectorSearch.faiss.IndexFlatIP")]
    [InlineTemplate("_faiss.IndexFlatIP({0})")]
    public static extern VectorSimilarityIndex IndexFlatIP(int d);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorIndexFactory.NormalizeRowsL2InPlace", "PythonSharp.VectorSearch.faiss.NormalizeL2")]
    [InlineTemplate("_faiss.normalize_L2({0})")]
    public static extern void normalize_L2(NDArray<double> x);
}

[SurfaceLevel(2)]
[MapsTo("_ort")]
public static primitive class ort
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.OnnxSessionFactory.CreateInferenceSessionFromFile", "PythonSharp.VectorSearch.ort.InferenceSession")]
    [InlineTemplate("_ort.InferenceSession({0})")]
    public static extern OnnxRuntimeInferenceSession InferenceSession(string path_or_bytes);
}

```

### `stdlib/02_scientific_and_ai/13_faiss_onnxruntime/02_inference.csharp.d.ps`

```csharp
namespace PythonSharp.VectorSearch;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.ArtificialIntelligence.Inference;
extern using faiss as _faiss;
extern using onnxruntime as _ort;

[SurfaceLevel(3)]
[MapsTo("_faiss")]
public static primitive class faiss
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorIndexFactory.CreateEuclideanL2VectorIndex")]
    [InlineTemplate("_faiss.IndexFlatL2({0})")]
    public static extern VectorSimilarityIndex IndexFlatL2(int embeddingDimension);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorIndexFactory.CreateInnerProductVectorIndex")]
    [InlineTemplate("_faiss.IndexFlatIP({0})")]
    public static extern VectorSimilarityIndex IndexFlatIP(int embeddingDimension);

    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.VectorIndexFactory.NormalizeRowsL2InPlace")]
    [InlineTemplate("_faiss.normalize_L2({0})")]
    public static extern void NormalizeL2(NDArray<double> embeddingMatrix);
}

[SurfaceLevel(3)]
[MapsTo("_ort")]
public static primitive class ort
{
    [CanonicalApi("PythonSharp.ArtificialIntelligence.Inference.OnnxSessionFactory.CreateInferenceSessionFromFile")]
    [InlineTemplate("_ort.InferenceSession({0})")]
    public static extern OnnxRuntimeInferenceSession InferenceSession(string onnxModelFilePath);
}

```

### `stdlib/02_scientific_and_ai/13_faiss_onnxruntime/03_inference.enterprise.d.ps`

```csharp
namespace PythonSharp.ArtificialIntelligence.Inference;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using faiss as _faiss;
extern using onnxruntime as _ort;

[SurfaceLevel(1)]
[MapsTo("_faiss")]
public static primitive class VectorIndexFactory
{
    [InlineTemplate("_faiss.IndexFlatL2({0})")]
    public static extern VectorSimilarityIndex CreateEuclideanL2VectorIndex(int embeddingDimensionSize);

    [InlineTemplate("_faiss.IndexFlatIP({0})")]
    public static extern VectorSimilarityIndex CreateInnerProductVectorIndex(int embeddingDimensionSize);

    [InlineTemplate("_faiss.normalize_L2({0})")]
    public static extern void NormalizeRowsL2InPlace(NDArray<double> embeddingMatrix);
}

[SurfaceLevel(1)]
[MapsTo("_ort")]
public static primitive class OnnxSessionFactory
{
    [InlineTemplate("_ort.InferenceSession({0})")]
    public static extern OnnxRuntimeInferenceSession CreateInferenceSessionFromFile(string onnxModelFilePath);
}

```

---

Would you like me to also generate the modular `stdlib/01_python_stdlib/` four-file bundles (`os_shutil`, `sys`, `json`, `re`, `time_datetime`, `logging`) or a comprehensive `.ps` test suite that validates all 13 `02_scientific_and_ai/` packages?
