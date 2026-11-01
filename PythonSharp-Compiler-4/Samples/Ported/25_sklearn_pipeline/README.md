# Sample 25: Scikit-Learn Machine Learning Pipeline (Tier 11)

A ported machine learning pipeline module demonstrating strongly-typed classical ML estimators, preprocessing transformers, and evaluation metrics in **PythonSharp** using `scikit-learn`.

---

## 1. Features Demonstrated

- **Composite ML Pipeline (`CompositeMlPipeline`)**:
  - Encapsulates feature scaling (`StandardFeatureScaler`) and supervised classification (`RandomForestClassifierModel`).
  - Implements `.Fit()`, `.Predict()`, and `.Evaluate()` returning strongly-typed `ClassificationMetrics`.
- **Triple-Surface Architecture**:
  - **Surface 1 (Enterprise Architecture)**: Self-documenting static facades (`DatasetSplitter.SplitTrainAndTestSets`, `FeaturePreprocessingFactory.CreateStandardZScoreScaler`, `ModelEstimatorFactory.CreateRandomForestClassifier`, `EvaluationMetrics.ComputeAccuracyScore`).
  - **Surface 3 (C# Standardized Bridge)**: Familiar PascalCase namespaces and methods (`sk.ModelSelection.TrainTestSplit`, `sk.Preprocessing.StandardScaler`, `sk.LinearModel.LogisticRegression`, `sk.LinearModel.Ridge`, `sk.Metrics.AccuracyScore`).
  - **Surface 2 (Raw Python snake_case ABI)**: Native `sklearn` module calls (`sklearn.model_selection.train_test_split`, `sklearn.preprocessing.StandardScaler`, `sklearn.ensemble.RandomForestClassifier`, `sklearn.metrics.accuracy_score`).
- **Regression and Classification**:
  - Binary/multiclass classification with Random Forest and Logistic Regression.
  - Linear continuous estimation with Ridge Regression.
- **Zero Runtime Wrapper Tax**: Compiled Python directly invokes native `scikit-learn` C-extensions with zero adapter overhead.

---

## 2. Compilation & Verification

### Build with PythonSharp Compiler (`psc`):
```bash
python3 -m psc.cli build SklearnPipeline.psproj -o dist
```

### Run Verification Harness:
```bash
python3 run_pipeline.py
```

