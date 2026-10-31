### 1. Audit of Current `stdlib/` `.d.ps` Files: Strengths & High-Impact Fixes

Your current `stdlib/` layout establishes the four-tier file convention (`00_*.primitives.d.ps`, `01_*.raw.d.ps`, `02_*.csharp.d.ps`, `03_*.enterprise.d.ps`), integrates `[CanonicalApi]` and `[SurfaceLevel]` in `PythonSharp.Core.d.ps`, and uses static module-property routing (`np.linalg`, `np.LinearAlgebra`, `os.path`, `OS.Path`).

To make these declarations ready for production AI, ML, and Data Science codebases, the existing `.d.ps` files need five specific upgrades:

| File / Area in `stdlib/` | Current Limitation in `consolidated_stdlib_folder.md` | Recommended Fix & Expansion |
| --- | --- | --- |
| **`01_numpy/01_numpy.raw.d.ps`**<br>

<br>*(Shape Tuple Overloads)* | `np.zeros(int rows, int cols)` and `np.ones(int rows, int cols)` only accept two separate `int` arguments. In real Python, `np.zeros((3, 3))` passes a **tuple** or a 1D/3D shape.

 | Add overloads for 1D `(int size)`, 2D tuple `((int, int) shape)`, 3D tuple `((int, int, int) shape)`, and variadic `(params int[] shape)` across all creation methods (`zeros`, `ones`, `full`, `empty`, `randn`).

 |
| **`01_numpy/00_numpy.primitives.d.ps`**<br>

<br>*(Missing AI/ML Tensor Ops)* | `NDArray<T>` only defines `shape`, `ndim`, `T`, `reshape`, `dot`, and an indexer. It lacks reductions, type casting, and shape squeezing needed in ML pipelines.

 | Add `dtype`/`DataType`, `size`/`TotalElementCount`, axis reductions (`sum`, `mean`, `std`, `min`, `max`, `argmax`, `argmin`), `astype<TOut>()`, `flatten()`, `squeeze()`, `expand_dims()`, and `tolist()`.

 |
| **`01_numpy/` Submodules**<br>

<br>*(Missing `np.random` & Math)* | Only `np.linalg` is currently exposed. ML data synthesis and weight initialization depend heavily on `np.random` and element-wise ufuncs (`exp`, `log`, `clip`, `where`, `concatenate`).

 | Add `RandomModule` (`np.random` / `np.Random` / `RandomTensorGenerator`) and element-wise mathematical operations (`Exp`, `Log`, `Sqrt`, `Clip`, `Where`, `Concatenate`, `Stack`).

 |
| **`PythonSharp.Core.d.ps`**<br>

<br>*(Missing `Bytes`, `Complex` & `builtins`)* | `PythonSharp.Core.d.ps` imports `builtins` and `dt`, but does not expose a `Bytes` primitive (`bytes`) for binary weights/images, `Complex` (`complex`) for SciPy/Quantum, or a triple-surface `builtins` wrapper (`range`, `enumerate`, `zip`, `open`).

 | Add `primitive class Bytes` (`[MapsTo("bytes")]`), `primitive struct Complex` (`[MapsTo("complex")]`), and `01_python_stdlib/builtins/` for `open`, `range`, `enumerate`, and `zip`.

 |
| **`02_scientific_and_ai/`**<br>

<br>*(Missing ML/AI Ecosystem)* | Currently contains only `01_numpy/`. Real-world AI/ML requires `pandas`, `scipy`, `sklearn`, `torch`, `matplotlib`/`seaborn`, `sympy`, and `qiskit`.

 | Add dependency-layered 4-file bundles (`02_scipy`, `03_pandas`, `04_matplotlib_seaborn`, `05_sklearn`, `06_torch`, `07_sympy`, `08_qiskit`) where each `00_*.primitives.d.ps` explicitly imports `PythonSharp.Numerics.Tensors` (`NDArray<T>`).

 |

---

### 2. Upgraded `01_numpy` `.d.ps` Files (AI/ML Ready)

Below are the expanded additions for `02_scientific_and_ai/01_numpy/` so `NDArray<T>` and `np` handle real feature engineering, broadcasting, reductions, and random sampling across all three surfaces:

#### `stdlib/02_scientific_and_ai/01_numpy/00_numpy.primitives.d.ps` (Expanded)

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
    [InlineTemplate("{self}.shape")]
    public extern List<int> DimensionShape { get; }

    [InlineTemplate("{self}.shape")]
    public extern List<int> Shape { get; }

    [InlineTemplate("{self}.shape")]
    public extern List<int> shape { get; }

    [InlineTemplate("{self}.ndim")]
    public extern int NumberOfDimensions { get; }

    [InlineTemplate("{self}.ndim")]
    public extern int NDim { get; }

    [InlineTemplate("{self}.ndim")]
    public extern int ndim { get; }

    [InlineTemplate("{self}.size")]
    public extern int TotalElementCount { get; }

    [InlineTemplate("{self}.size")]
    public extern int Size { get; }

    [InlineTemplate("{self}.size")]
    public extern int size { get; }

    [InlineTemplate("str({self}.dtype)")]
    public extern string ElementDataType { get; }

    [InlineTemplate("str({self}.dtype)")]
    public extern string DType { get; }

    [InlineTemplate("str({self}.dtype)")]
    public extern string dtype { get; }

    [InlineTemplate("{self}.T")]
    public extern NDArray<T> TransposedMatrix { get; }

    [InlineTemplate("{self}.T")]
    public extern NDArray<T> T { get; }

    // ========================================================================
    // 2. SHAPE & TYPE TRANSFORMATIONS
    // ========================================================================
    [InlineTemplate("{self}.reshape(({0}, {1}))")]
    public extern NDArray<T> ReshapeToMatrix(int rows, int columns);

    [MapsTo("reshape")]
    public extern NDArray<T> Reshape(params int[] shape);

    [MapsTo("reshape")]
    public extern NDArray<T> reshape(params int[] shape);

    [MapsTo("flatten")]
    public extern NDArray<T> FlattenTo1DVector();

    [MapsTo("flatten")]
    public extern NDArray<T> Flatten();

    [MapsTo("flatten")]
    public extern NDArray<T> flatten();

    [InlineTemplate("{self}.astype({0})")]
    public extern NDArray<TOut> CastElementsTo<TOut>(string targetDtype);

    [InlineTemplate("{self}.astype({0})")]
    public extern NDArray<TOut> AsType<TOut>(string dtype);

    [InlineTemplate("{self}.astype({0})")]
    public extern NDArray<TOut> astype<TOut>(string dtype);

    [MapsTo("tolist")]
    public extern List<T> ToPythonList();

    [MapsTo("tolist")]
    public extern List<T> ToList();

    [MapsTo("tolist")]
    public extern List<T> tolist();

    // ========================================================================
    // 3. STATISTICAL & AXIS REDUCTIONS (Critical for ML Feature Scaling)
    // ========================================================================
    [MapsTo("mean")]
    public extern double ComputeArithmeticMean(int? axis = null);

    [MapsTo("mean")]
    public extern double Mean(int? axis = null);

    [MapsTo("mean")]
    public extern double mean(int? axis = null);

    [MapsTo("std")]
    public extern double ComputeStandardDeviation(int? axis = null);

    [MapsTo("std")]
    public extern double Std(int? axis = null);

    [MapsTo("std")]
    public extern double std(int? axis = null);

    [MapsTo("sum")]
    public extern T ComputeSum(int? axis = null);

    [MapsTo("sum")]
    public extern T Sum(int? axis = null);

    [MapsTo("sum")]
    public extern T sum(int? axis = null);

    [MapsTo("argmax")]
    public extern int FindIndexOfMaximum(int? axis = null);

    [MapsTo("argmax")]
    public extern int ArgMax(int? axis = null);

    [MapsTo("argmax")]
    public extern int argmax(int? axis = null);

    // ========================================================================
    // 4. LINEAR ALGEBRA & MULTI-AXIS SLICING
    // ========================================================================
    [InlineTemplate("({self} @ {0})")]
    public extern NDArray<T> MultiplyMatrix(NDArray<T> other);

    [MapsTo("dot")]
    public extern NDArray<T> Dot(NDArray<T> other);

    [MapsTo("dot")]
    public extern NDArray<T> dot(NDArray<T> other);

    [InlineTemplate("{self}[{0}]")]
    public extern NDArray<T> this[params object[] slices] { get; set; }
}

```

#### `stdlib/02_scientific_and_ai/01_numpy/01_numpy.raw.d.ps` & `02_numpy.csharp.d.ps` (Adding Tuple Overloads & `random` Submodule)

```csharp
// Excerpt adding RandomModule and Tuple/List Creation Overloads in 01_numpy.raw.d.ps
namespace numpy;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
extern using numpy as np;

[SurfaceLevel(2)]
[MapsTo("np.random")]
public static primitive class RandomModule
{
    [CanonicalApi("PythonSharp.Numerics.RandomSampling.RandomTensorGenerator.SetRandomSeed", "PythonSharp.NumPy.np.Random.Seed")]
    [InlineTemplate("np.random.seed({0})")]
    public static extern void seed(int seedValue);

    [CanonicalApi("PythonSharp.Numerics.RandomSampling.RandomTensorGenerator.CreateStandardNormalMatrix", "PythonSharp.NumPy.np.Random.RandN")]
    [InlineTemplate("np.random.randn({0}, {1})")]
    public static extern NDArray<double> randn(int rows, int cols);

    [CanonicalApi("PythonSharp.Numerics.RandomSampling.RandomTensorGenerator.CreateNormalDistributionTensor", "PythonSharp.NumPy.np.Random.Normal")]
    [InlineTemplate("np.random.normal({0}, {1}, {2})")]
    public static extern NDArray<double> normal(double loc = 0.0, double scale = 1.0, (int, int)? size = null);
}

// Inside static primitive class np:
// Overloads supporting both Python tuple `np.zeros((3, 3))` and C# `np.zeros(3, 3)`:
// [InlineTemplate("np.zeros({0})")] public static extern NDArray<double> zeros((int, int) shape);
// [InlineTemplate("np.zeros(({0}, {1}))")] public static extern NDArray<double> zeros(int rows, int cols);
// [InlineTemplate("np.array({0})")] public static extern NDArray<T> array<T>(IEnumerable<T> data);
// [InlineTemplate("np.random")] public static extern RandomModule random { get; }

```

---

### 3. New Triple-Surface `.d.ps` Bundles for AI & ML Packages

Here is how we expand `stdlib/02_scientific_and_ai/` to cover **Pandas (`03_pandas`)**, **Scikit-Learn (`05_sklearn`)**, and **PyTorch (`06_torch`)**, keeping explicit cross-package dependencies in `00_*.primitives.d.ps`.

---

#### Package A: `03_pandas` (Schema-Safe `DataFrame<TRow>` + Triple Surface)

Notice how `00_pandas.primitives.d.ps` explicitly imports `PythonSharp.Numerics.Tensors` so `.ToNumpy()` / `.to_numpy()` returns a strongly typed `NDArray<double>`:

##### 1. `stdlib/02_scientific_and_ai/03_pandas/00_pandas.primitives.d.ps`

```csharp
namespace PythonSharp.DataScience.Tabular;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors; // Explicit dependency on 01_numpy!
extern using pandas as pd;

[MapsTo("pd.Series")]
[RuntimeType("pd.Series")]
public primitive class Series<T> : IEnumerable<T>
{
    [MapsTo("to_numpy")]
    public extern NDArray<T> ConvertToNumPyArray();

    [MapsTo("to_numpy")]
    public extern NDArray<T> ToNumpy();

    [MapsTo("to_numpy")]
    public extern NDArray<T> to_numpy();

    [MapsTo("mean")]
    public extern double ComputeMean();

    [MapsTo("mean")]
    public extern double Mean();

    [MapsTo("mean")]
    public extern double mean();

    [MapsTo("fillna")]
    public extern Series<T> FillMissingValues(T replacementValue);

    [MapsTo("fillna")]
    public extern Series<T> FillNa(T value);

    [MapsTo("fillna")]
    public extern Series<T> fillna(T value);
}

/// <summary>
/// Schema-checked DataFrame<TRow> where TRow erases at runtime to pd.DataFrame.
/// Using DataFrame<object> or non-generic alias allows dynamic untyped migration.
/// </summary>
[MapsTo("pd.DataFrame")]
[RuntimeType("pd.DataFrame")]
public primitive class DataFrame<TRow>
{
    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) TableDimensions { get; }

    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) Shape { get; }

    [InlineTemplate("{self}.shape")]
    public extern (int Rows, int Columns) shape { get; }

    [InlineTemplate("list({self}.columns)")]
    public extern List<string> ColumnNames { get; }

    [InlineTemplate("list({self}.columns)")]
    public extern List<string> Columns { get; }

    [InlineTemplate("list({self}.columns)")]
    public extern List<string> columns { get; }

    // --- Surface 1: Self-Documenting Enterprise Methods ---
    [MapsTo("dropna")]
    public extern DataFrame<TRow> DropRowsWithMissingValues();

    [MapsTo("fillna")]
    public extern DataFrame<TRow> FillMissingValuesWith(object replacementValue);

    [MapsTo("head")]
    public extern DataFrame<TRow> TakeFirstRows(int rowCount = 5);

    [MapsTo("to_numpy")]
    public extern NDArray<double> ConvertToFeatureMatrix();

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

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ConvertToFeatureMatrix")]
    [MapsTo("to_numpy")]
    public extern NDArray<double> ToNumpy();

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

    [CanonicalApi("PythonSharp.DataScience.Tabular.DataFrame.ConvertToFeatureMatrix", "ToNumpy")]
    [MapsTo("to_numpy")]
    public extern NDArray<double> to_numpy();

    // Column indexing: df["age"] or df[["age", "salary"]]
    [InlineTemplate("{self}[{0}]")]
    public extern Series<object> this[string columnName]
    {
        get;
        [InlineTemplate("{self}[{0}] = {value}")] set;
    }

    [InlineTemplate("{self}[{0}]")]
    public extern DataFrame<TRow> this[List<string> columnNames] { get; }
}

```

##### 2. `01_pandas.raw.d.ps`, `02_pandas.csharp.d.ps` & `03_tabular.enterprise.d.ps`

```csharp
// ============================================================================
// FILE: 01_pandas.raw.d.ps (Surface 2 — Raw Python Mirror)
// ============================================================================
namespace pandas;

using PythonSharp.Core;
using PythonSharp.DataScience.Tabular;
extern using pandas as pd;

[SurfaceLevel(2)]
[MapsTo("pd")]
public static primitive class pd
{
    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadCsvFile", "PythonSharp.Pandas.pd.ReadCsv")]
    [InlineTemplate("pd.read_csv({0})")]
    public static extern DataFrame<object> read_csv(string filepathOrBuffer);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadParquetFile", "PythonSharp.Pandas.pd.ReadParquet")]
    [InlineTemplate("pd.read_parquet({0})")]
    public static extern DataFrame<object> read_parquet(string path);
}

// ============================================================================
// FILE: 02_pandas.csharp.d.ps (Surface 3 — C#-Standardized Bridge)
// ============================================================================
namespace PythonSharp.Pandas;

using PythonSharp.Core;
using PythonSharp.DataScience.Tabular;
extern using pandas as _pd;

[SurfaceLevel(3)]
[MapsTo("_pd")]
public static primitive class pd
{
    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadCsvFile")]
    [InlineTemplate("_pd.read_csv({0})")]
    public static extern DataFrame<TRow> ReadCsv<TRow>(string filePath);

    [CanonicalApi("PythonSharp.DataScience.Tabular.TabularDataReader.ReadParquetFile")]
    [InlineTemplate("_pd.read_parquet({0})")]
    public static extern DataFrame<TRow> ReadParquet<TRow>(string filePath);
}

// ============================================================================
// FILE: 03_tabular.enterprise.d.ps (Surface 1 — Self-Documenting Enterprise FQN)
// ============================================================================
namespace PythonSharp.DataScience.Tabular;

using PythonSharp.Core;
extern using pandas as _pd;

[SurfaceLevel(1)]
public static primitive class TabularDataReader
{
    [InlineTemplate("_pd.read_csv({0})")]
    public static extern DataFrame<TRow> ReadCsvFile<TRow>(string csvFilePath);

    [InlineTemplate("_pd.read_parquet({0})")]
    public static extern DataFrame<TRow> ReadParquetFile<TRow>(string parquetFilePath);
}

```

---

#### Package B: `05_sklearn` (Classical ML Pipelines, Preprocessing & Models)

`05_sklearn` depends on `01_numpy` (`NDArray<T>`) and provides contracts for `StandardScaler`, `RandomForestClassifier`, `train_test_split`, and evaluation metrics:

##### 1. `stdlib/02_scientific_and_ai/05_sklearn/00_sklearn.primitives.d.ps`

```csharp
namespace PythonSharp.MachineLearning.Classical;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors; // Depends on 01_numpy

public primitive interface IFeatureTransformer<T>
{
    // Surface 1 (Enterprise)
    [MapsTo("fit_transform")]
    NDArray<T> FitAndTransformFeatures(NDArray<T> featureMatrix);

    [MapsTo("transform")]
    NDArray<T> TransformFeatures(NDArray<T> featureMatrix);

    // Surface 3 (C# Bridge)
    [MapsTo("fit_transform")]
    NDArray<T> FitTransform(NDArray<T> X);

    [MapsTo("transform")]
    NDArray<T> Transform(NDArray<T> X);

    // Surface 2 (Raw Python)
    [MapsTo("fit_transform")]
    NDArray<T> fit_transform(NDArray<T> X);

    [MapsTo("transform")]
    NDArray<T> transform(NDArray<T> X);
}

public primitive interface ISupervisedEstimator<TFeature, TLabel>
{
    // Surface 1 (Enterprise)
    [MapsTo("fit")]
    void TrainOnLabeledDataset(NDArray<TFeature> featureMatrix, NDArray<TLabel> targetLabels);

    [MapsTo("predict")]
    NDArray<TLabel> PredictLabels(NDArray<TFeature> featureMatrix);

    [MapsTo("predict_proba")]
    NDArray<double> PredictClassProbabilities(NDArray<TFeature> featureMatrix);

    // Surface 3 (C# Bridge)
    [MapsTo("fit")]
    void Fit(NDArray<TFeature> X, NDArray<TLabel> y);

    [MapsTo("predict")]
    NDArray<TLabel> Predict(NDArray<TFeature> X);

    // Surface 2 (Raw Python)
    [MapsTo("fit")]
    void fit(NDArray<TFeature> X, NDArray<TLabel> y);

    [MapsTo("predict")]
    NDArray<TLabel> predict(NDArray<TFeature> X);
}

[MapsTo("sklearn.preprocessing.StandardScaler")]
public primitive class StandardFeatureScaler : IFeatureTransformer<double>
{
    [InlineTemplate("StandardScaler()")]
    public extern StandardFeatureScaler();
}

[MapsTo("sklearn.ensemble.RandomForestClassifier")]
public primitive class RandomForestClassifierModel : ISupervisedEstimator<double, int>
{
    [InlineTemplate("RandomForestClassifier(n_estimators={0}, max_depth={1}, random_state={2})")]
    public extern RandomForestClassifierModel(int numberOfTrees = 100, int? maxTreeDepth = null, int? randomSeed = null);
}

```

##### 2. `01_sklearn.raw.d.ps`, `02_sklearn.csharp.d.ps` & `03_ml.enterprise.d.ps`

```csharp
// ============================================================================
// FILE: 01_sklearn.raw.d.ps (Surface 2 — Raw Python Mirror)
// ============================================================================
namespace sklearn;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.MachineLearning.Classical;
extern using sklearn.model_selection as _ms;
extern using sklearn.preprocessing as _prep;
extern using sklearn.ensemble as _ens;
extern using sklearn.metrics as _met;

[SurfaceLevel(2)]
public static primitive class model_selection
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.Validation.DatasetSplitter.SplitTrainAndTestSets", "PythonSharp.ScikitLearn.sk.ModelSelection.TrainTestSplit")]
    [InlineTemplate("_ms.train_test_split({0}, {1}, test_size={2}, random_state={3})")]
    public static extern (NDArray<double> X_train, NDArray<double> X_test, NDArray<int> y_train, NDArray<int> y_test) train_test_split(
        NDArray<double> X, NDArray<int> y, double test_size = 0.2, int random_state = 42);
}

[SurfaceLevel(2)]
public static primitive class preprocessing
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.Preprocessing.FeatureScalingFactory.CreateStandardZScoreScaler", "PythonSharp.ScikitLearn.sk.Preprocessing.StandardScaler")]
    [InlineTemplate("_prep.StandardScaler()")]
    public static extern StandardFeatureScaler StandardScaler();
}

[SurfaceLevel(2)]
public static primitive class ensemble
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.Ensemble.EnsembleClassifierFactory.CreateRandomForestClassifier", "PythonSharp.ScikitLearn.sk.Ensemble.RandomForestClassifier")]
    [InlineTemplate("_ens.RandomForestClassifier(n_estimators={0}, random_state={1})")]
    public static extern RandomForestClassifierModel RandomForestClassifier(int n_estimators = 100, int random_state = 42);
}

[SurfaceLevel(2)]
public static primitive class metrics
{
    [CanonicalApi("PythonSharp.MachineLearning.Classical.Evaluation.ClassificationMetrics.ComputeAccuracyScore", "PythonSharp.ScikitLearn.sk.Metrics.AccuracyScore")]
    [InlineTemplate("_met.accuracy_score({0}, {1})")]
    public static extern double accuracy_score(NDArray<int> y_true, NDArray<int> y_pred);
}

// ============================================================================
// FILE: 02_sklearn.csharp.d.ps (Surface 3 — C#-Standardized Bridge)
// ============================================================================
namespace PythonSharp.ScikitLearn;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.MachineLearning.Classical;
extern using sklearn.model_selection as _ms;
extern using sklearn.preprocessing as _prep;
extern using sklearn.ensemble as _ens;
extern using sklearn.metrics as _met;

[SurfaceLevel(3)]
public static primitive class sk
{
    public static primitive class ModelSelection
    {
        [CanonicalApi("PythonSharp.MachineLearning.Classical.Validation.DatasetSplitter.SplitTrainAndTestSets")]
        [InlineTemplate("_ms.train_test_split({0}, {1}, test_size={2}, random_state={3})")]
        public static extern (NDArray<double> XTrain, NDArray<double> XTest, NDArray<int> YTrain, NDArray<int> YTest) TrainTestSplit(
            NDArray<double> features, NDArray<int> labels, double testSize = 0.2, int randomState = 42);
    }

    public static primitive class Preprocessing
    {
        [CanonicalApi("PythonSharp.MachineLearning.Classical.Preprocessing.FeatureScalingFactory.CreateStandardZScoreScaler")]
        [InlineTemplate("_prep.StandardScaler()")]
        public static extern StandardFeatureScaler StandardScaler();
    }

    public static primitive class Ensemble
    {
        [CanonicalApi("PythonSharp.MachineLearning.Classical.Ensemble.EnsembleClassifierFactory.CreateRandomForestClassifier")]
        [InlineTemplate("_ens.RandomForestClassifier(n_estimators={0}, random_state={1})")]
        public static extern RandomForestClassifierModel RandomForestClassifier(int nEstimators = 100, int randomState = 42);
    }

    public static primitive class Metrics
    {
        [CanonicalApi("PythonSharp.MachineLearning.Classical.Evaluation.ClassificationMetrics.ComputeAccuracyScore")]
        [InlineTemplate("_met.accuracy_score({0}, {1})")]
        public static extern double AccuracyScore(NDArray<int> trueLabels, NDArray<int> predictedLabels);
    }
}

// ============================================================================
// FILE: 03_ml.enterprise.d.ps (Surface 1 — Self-Documenting Enterprise FQN)
// ============================================================================
namespace PythonSharp.MachineLearning.Classical.Validation;

using PythonSharp.Numerics.Tensors;
extern using sklearn.model_selection as _ms;

[SurfaceLevel(1)]
public static primitive class DatasetSplitter
{
    [InlineTemplate("_ms.train_test_split({0}, {1}, test_size={2}, random_state={3})")]
    public static extern (NDArray<double> TrainingFeatures, NDArray<double> TestingFeatures, NDArray<int> TrainingLabels, NDArray<int> TestingLabels) SplitTrainAndTestSets(
        NDArray<double> featureMatrix, NDArray<int> labelVector, double testFraction = 0.2, int randomSeed = 42);
}

namespace PythonSharp.MachineLearning.Classical.Evaluation;

using PythonSharp.Numerics.Tensors;
extern using sklearn.metrics as _met;

[SurfaceLevel(1)]
public static primitive class ClassificationMetrics
{
    [InlineTemplate("_met.accuracy_score({0}, {1})")]
    public static extern double ComputeAccuracyScore(NDArray<int> groundTruthLabels, NDArray<int> predictedLabels);
}

```

---

#### Package C: `06_torch` (Deep Learning Tensors, Autograd, `nn.Module` & Optimizers)

PyTorch leverages PythonSharp's `[PythonDecorator]` attribute (for `@torch.no_grad()` and `@torch.compile`) alongside zero-cost `Tensor<T>` primitives:

##### 1. `stdlib/02_scientific_and_ai/06_torch/00_torch.primitives.d.ps`

```csharp
namespace PythonSharp.DeepLearning.Tensors;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors; // Interop with NumPy NDArray<T>
extern using torch;

/// <summary>
/// Surface 1 & Surface 3 Decorator attribute lowering to @torch.no_grad()
/// </summary>
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
    [InlineTemplate("list({self}.shape)")]
    public extern List<int> TensorShape { get; }

    [InlineTemplate("list({self}.shape)")]
    public extern List<int> Shape { get; }

    [InlineTemplate("list({self}.shape)")]
    public extern List<int> shape { get; }

    [InlineTemplate("str({self}.device)")]
    public extern string ExecutionDevice { get; }

    [InlineTemplate("str({self}.device)")]
    public extern string Device { get; }

    [InlineTemplate("str({self}.device)")]
    public extern string device { get; }

    // --- Device Transfer & Autograd Operations ---
    [MapsTo("to")]
    public extern TorchTensor<T> MoveToDevice(string deviceName);

    [MapsTo("to")]
    public extern TorchTensor<T> To(string device);

    [MapsTo("to")]
    public extern TorchTensor<T> to(string device);

    [MapsTo("backward")]
    public extern void ComputeBackpropagationGradients();

    [MapsTo("backward")]
    public extern void Backward();

    [MapsTo("backward")]
    public extern void backward();

    [InlineTemplate("{self}.detach().cpu().numpy()")]
    public extern NDArray<T> DetachToCpuNumPyArray();

    [MapsTo("detach")]
    public extern TorchTensor<T> Detach();

    [MapsTo("detach")]
    public extern TorchTensor<T> detach();

    [MapsTo("item")]
    public extern T ExtractScalarValue();

    [MapsTo("item")]
    public extern T Item();

    [MapsTo("item")]
    public extern T item();
}

namespace PythonSharp.DeepLearning.NeuralNetworks;

using PythonSharp.Core;
using PythonSharp.DeepLearning.Tensors;
extern using torch.nn as _nn;

[MapsTo("_nn.Linear")]
public primitive class FullyConnectedLinearLayer
{
    [MapsTo("__call__")]
    [InlineTemplate("{self}({0})")]
    public extern TorchTensor<double> ForwardPass(TorchTensor<double> inputTensor);

    [InlineTemplate("{self}({0})")]
    public extern TorchTensor<double> Call(TorchTensor<double> x);
}

[MapsTo("torch.optim.Optimizer")]
public primitive class GradientOptimizer
{
    [MapsTo("zero_grad")]
    public extern void ResetAllGradientsToZero();

    [MapsTo("zero_grad")]
    public extern void ZeroGrad();

    [MapsTo("zero_grad")]
    public extern void zero_grad();

    [MapsTo("step")]
    public extern void UpdateModelParameters();

    [MapsTo("step")]
    public extern void Step();

    [MapsTo("step")]
    public extern void step();
}

```

##### 2. `01_torch.raw.d.ps`, `02_torch.csharp.d.ps` & `03_deeplearning.enterprise.d.ps`

```csharp
// ============================================================================
// FILE: 01_torch.raw.d.ps (Surface 2 — Raw Python Mirror)
// ============================================================================
namespace torch;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DeepLearning.Tensors;
using PythonSharp.DeepLearning.NeuralNetworks;
extern using torch as _torch;
extern using torch.nn as _nn;
extern using torch.optim as _optim;

[SurfaceLevel(2)]
public static primitive class cuda
{
    [CanonicalApi("PythonSharp.DeepLearning.Hardware.AcceleratorRuntime.IsCudaGpuAvailable", "PythonSharp.PyTorch.torch.Cuda.IsAvailable")]
    [InlineTemplate("_torch.cuda.is_available()")]
    public static extern bool is_available();
}

[SurfaceLevel(2)]
public static primitive class nn
{
    [CanonicalApi("PythonSharp.DeepLearning.NeuralNetworks.LayerFactory.CreateFullyConnectedLinearLayer", "PythonSharp.PyTorch.torch.NN.Linear")]
    [InlineTemplate("_nn.Linear({0}, {1})")]
    public static extern FullyConnectedLinearLayer Linear(int in_features, int out_features);
}

[SurfaceLevel(2)]
public static primitive class optim
{
    [CanonicalApi("PythonSharp.DeepLearning.Optimization.OptimizerFactory.CreateAdamOptimizer", "PythonSharp.PyTorch.torch.Optim.Adam")]
    [InlineTemplate("_optim.Adam({0}, lr={1})")]
    public static extern GradientOptimizer Adam(object parameters, double lr = 0.001);
}

[SurfaceLevel(2)]
[MapsTo("_torch")]
public static primitive class torch
{
    [CanonicalApi("PythonSharp.DeepLearning.Tensors.TensorFactory.FromNumPyArray", "PythonSharp.PyTorch.torch.FromNumpy")]
    [InlineTemplate("_torch.from_numpy({0})")]
    public static extern TorchTensor<T> from_numpy<T>(NDArray<T> ndarray);

    [CanonicalApi("PythonSharp.DeepLearning.Tensors.TensorFactory.CreateRandomNormalTensor", "PythonSharp.PyTorch.torch.RandN")]
    [InlineTemplate("_torch.randn({0}, {1})")]
    public static extern TorchTensor<double> randn(int rows, int cols);
}

// ============================================================================
// FILE: 02_torch.csharp.d.ps (Surface 3 — C#-Standardized Bridge)
// ============================================================================
namespace PythonSharp.PyTorch;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DeepLearning.Tensors;
using PythonSharp.DeepLearning.NeuralNetworks;
extern using torch as _torch;
extern using torch.nn as _nn;
extern using torch.optim as _optim;

[SurfaceLevel(3)]
[MapsTo("_torch")]
public static primitive class torch
{
    [CanonicalApi("PythonSharp.DeepLearning.Tensors.TensorFactory.FromNumPyArray")]
    [InlineTemplate("_torch.from_numpy({0})")]
    public static extern TorchTensor<T> FromNumpy<T>(NDArray<T> array);

    [CanonicalApi("PythonSharp.DeepLearning.Tensors.TensorFactory.CreateRandomNormalTensor")]
    [InlineTemplate("_torch.randn({0}, {1})")]
    public static extern TorchTensor<double> RandN(int rows, int cols);

    public static primitive class Cuda
    {
        [CanonicalApi("PythonSharp.DeepLearning.Hardware.AcceleratorRuntime.IsCudaGpuAvailable")]
        [InlineTemplate("_torch.cuda.is_available()")]
        public static extern bool IsAvailable();
    }

    public static primitive class NN
    {
        [CanonicalApi("PythonSharp.DeepLearning.NeuralNetworks.LayerFactory.CreateFullyConnectedLinearLayer")]
        [InlineTemplate("_nn.Linear({0}, {1})")]
        public static extern FullyConnectedLinearLayer Linear(int inFeatures, int outFeatures);
    }

    public static primitive class Optim
    {
        [CanonicalApi("PythonSharp.DeepLearning.Optimization.OptimizerFactory.CreateAdamOptimizer")]
        [InlineTemplate("_optim.Adam({0}, lr={1})")]
        public static extern GradientOptimizer Adam(object parameters, double learningRate = 0.001);
    }
}

// ============================================================================
// FILE: 03_deeplearning.enterprise.d.ps (Surface 1 — Enterprise Domain FQN)
// ============================================================================
namespace PythonSharp.DeepLearning.Hardware;

extern using torch as _torch;

[SurfaceLevel(1)]
public static primitive class AcceleratorRuntime
{
    [InlineTemplate("_torch.cuda.is_available()")]
    public static extern bool IsCudaGpuAvailable();

    [InlineTemplate("('cuda' if _torch.cuda.is_available() else 'cpu')")]
    public static extern string SelectOptimalDeviceName();
}

namespace PythonSharp.DeepLearning.Tensors;

using PythonSharp.Numerics.Tensors;
extern using torch as _torch;

[SurfaceLevel(1)]
public static primitive class TensorFactory
{
    [InlineTemplate("_torch.from_numpy({0})")]
    public static extern TorchTensor<T> FromNumPyArray<T>(NDArray<T> sourceArray);

    [InlineTemplate("_torch.randn({0}, {1})")]
    public static extern TorchTensor<double> CreateRandomNormalTensor(int rows, int columns);
}

```

---

### 4. End-to-End Sample: All Three Surfaces in an AI/ML Pipeline

Because all three surfaces share the exact same underlying primitive types (`DataFrame<TRow>`, `NDArray<T>`, `StandardFeatureScaler`, `TorchTensor<T>`), a team can migrate a raw Python ML script (Surface 2), clean it up with C# conventions (Surface 3), and architect core domain services with self-documenting FQNs (Surface 1):

#### Input: `Samples/07_ai_ml_triple_surface/CustomerChurnPipeline.ps`

```csharp
namespace EnterpriseAI.ChurnPrediction;

using PythonSharp.Core;
using PythonSharp.Numerics.Tensors;
using PythonSharp.DataScience.Tabular;
using PythonSharp.MachineLearning.Classical;
using PythonSharp.DeepLearning.Tensors;

// Surface 2 (Raw Python imports for quick migration)
using pandas;
using sklearn;
using torch;

// Surface 3 (C#-Standardized bridge imports)
using PythonSharp.ScikitLearn;

// Surface 1 (Self-Documenting Enterprise FQN imports)
using PythonSharp.MachineLearning.Classical.Validation;
using PythonSharp.MachineLearning.Classical.Evaluation;
using PythonSharp.DeepLearning.Hardware;

public record CustomerChurnRow(int CustomerId, double MonthlySpend, double TenureMonths, int Churned);

public class ChurnTrainingService
{
    // ------------------------------------------------------------------------
    // 1. SURFACE 2 (Raw Python Syntax): Easy copy-paste from Jupyter Notebook
    // ------------------------------------------------------------------------
    public static double RunMigratedNotebookStyle(string csvPath)
    {
        var df = pd.read_csv(csvPath).dropna();
        var X = df.to_numpy();
        var y = df["Churned"].to_numpy().astype<int>("int64");

        var scaler = preprocessing.StandardScaler();
        var X_scaled = scaler.fit_transform(X);

        var (X_train, X_test, y_train, y_test) = model_selection.train_test_split(X_scaled, y, 0.2, 42);
        var clf = ensemble.RandomForestClassifier(100, 42);
        clf.fit(X_train, y_train);

        var preds = clf.predict(X_test);
        return metrics.accuracy_score(y_test, preds);
    }

    // ------------------------------------------------------------------------
    // 2. SURFACE 3 (C# Bridge Syntax): Clean PascalCase & Familiar Names
    // ------------------------------------------------------------------------
    public static double RunCSharpStandardizedStyle(string csvPath)
    {
        var df = PythonSharp.Pandas.pd.ReadCsv<CustomerChurnRow>(csvPath).DropNa();
        var features = df.ToNumpy();
        var labels = df["Churned"].ToNumpy().AsType<int>("int64");

        var scaler = sk.Preprocessing.StandardScaler();
        var scaledFeatures = scaler.FitTransform(features);

        var (xTrain, xTest, yTrain, yTest) = sk.ModelSelection.TrainTestSplit(scaledFeatures, labels, 0.2, 42);
        var model = sk.Ensemble.RandomForestClassifier(100, 42);
        model.Fit(xTrain, yTrain);

        var predictions = model.Predict(xTest);
        return sk.Metrics.AccuracyScore(yTest, predictions);
    }

    // ------------------------------------------------------------------------
    // 3. SURFACE 1 (Enterprise Domain FQN): 100% Self-Documenting Architecture
    // ------------------------------------------------------------------------
    [DisableGradientTracking]
    public static TorchTensor<double> ConvertCleanFeaturesToGpuTensor(string csvFilePath)
    {
        DataFrame<CustomerChurnRow> cleanTable = TabularDataReader
            .ReadCsvFile<CustomerChurnRow>(csvFilePath)
            .DropRowsWithMissingValues();

        NDArray<double> rawFeatureMatrix = cleanTable.ConvertToFeatureMatrix();
        string targetDevice = AcceleratorRuntime.SelectOptimalDeviceName();

        return TensorFactory
            .FromNumPyArray(rawFeatureMatrix)
            .MoveToDevice(targetDevice);
    }
}

```

#### Emitted Python 3.11+ Output (`dist/enterprise_ai/churn_prediction.py`)

Look at how all three surfaces compile down to clean, idiomatic, zero-wrapper Python 3.11+:

```python
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
import sklearn.ensemble as _ens
import sklearn.metrics as _met
import sklearn.model_selection as _ms
import sklearn.preprocessing as _prep
import torch as _torch

@dataclass(slots=True, frozen=True)
class CustomerChurnRow:
    __ps_types__ = ("EnterpriseAI.ChurnPrediction.CustomerChurnRow",)
    customer_id: int
    monthly_spend: float
    tenure_months: float
    churned: int

class ChurnTrainingService:
    __slots__ = ()

    @staticmethod
    def run_migrated_notebook_style(csv_path: str) -> float:
        df: pd.DataFrame = pd.read_csv(csv_path).dropna()
        x: np.ndarray = df.to_numpy()
        y: np.ndarray = df["Churned"].to_numpy().astype("int64")
        scaler = _prep.StandardScaler()
        x_scaled: np.ndarray = scaler.fit_transform(x)
        x_train, x_test, y_train, y_test = _ms.train_test_split(x_scaled, y, test_size=0.2, random_state=42)
        clf = _ens.RandomForestClassifier(n_estimators=100, random_state=42)
        clf.fit(x_train, y_train)
        preds: np.ndarray = clf.predict(x_test)
        return _met.accuracy_score(y_test, preds)

    @staticmethod
    def run_csharp_standardized_style(csv_path: str) -> float:
        df: pd.DataFrame = pd.read_csv(csv_path).dropna()
        features: np.ndarray = df.to_numpy()
        labels: np.ndarray = df["Churned"].to_numpy().astype("int64")
        scaler = _prep.StandardScaler()
        scaled_features: np.ndarray = scaler.fit_transform(features)
        x_train, x_test, y_train, y_test = _ms.train_test_split(scaled_features, labels, test_size=0.2, random_state=42)
        model = _ens.RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(x_train, y_train)
        predictions: np.ndarray = model.predict(x_test)
        return _met.accuracy_score(y_test, predictions)

    @staticmethod
    @_torch.no_grad()
    def convert_clean_features_to_gpu_tensor(csv_file_path: str) -> _torch.Tensor:
        clean_table: pd.DataFrame = pd.read_csv(csv_file_path).dropna()
        raw_feature_matrix: np.ndarray = clean_table.to_numpy()
        target_device: str = "cuda" if _torch.cuda.is_available() else "cpu"
        return _torch.from_numpy(raw_feature_matrix).to(target_device)

```

Would you like me to generate the complete raw `.d.ps` files for **`02_scipy`**, **`03_pandas`**, **`04_matplotlib_seaborn`**, **`05_sklearn`**, **`06_torch`**, **`07_sympy`**, and **`08_qiskit`** so you can drop them directly into `stdlib/02_scientific_and_ai/`?
