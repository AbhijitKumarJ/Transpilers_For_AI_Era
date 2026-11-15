# PandasFullPrac: End-to-End Data Preprocessing & Analytics in PythonSharp

An enterprise-grade data engineering and preprocessing pipeline built in **PythonSharp (`.ps`)**, compiling natively into zero-overhead Python 3.11+ bytecode and modules. This sample demonstrates how PythonSharp blends C#'s strong type safety, modular namespace architecture, and static checking with Python's rich data science ecosystem (Pandas, NumPy, and Scikit-Learn conventions).

---

## 1. Architectural Overview

The project is structured according to clean separation of concerns and follows the modular preprocessing patterns outlined in `Pandas preprocessing 1.md`. Every pipeline phase is encapsulated in its own submodule within `CalHousing/`, keeping each file around 50 lines for maximum maintainability, readability, and testability.

```
Sample_Practice/PandasFullPrac/
├── PandasDemo.psproj                  # PythonSharp Project Configuration
├── .ps.conf.json                      # Stub Layer & Ambient Package Configuration
├── ProjMain.ps                        # Master project entry point
├── TestUtil.ps                        # Shared logging and utility helpers
├── run_main.py                        # Python execution runner
├── CalHousing/                        # California Housing Preprocessing Pipeline
│   ├── pp1.ps                         # Orchestrator & sequential pipeline runner (~60 lines)
│   ├── Inspection/
│   │   └── DataInspector.ps           # Phase 1: High-level shape, head & stats inspection
│   ├── Cleaning/
│   │   └── DataCleaner.ps             # Phase 2: Missing data audit, median imputation & deduplication
│   ├── Outliers/
│   │   └── OutlierHandler.ps          # Phase 3: Price ceiling clipping & population IQR filtering
│   ├── Engineering/
│   │   └── FeatureTransformer.ps      # Phase 4: Domain ratios, age binning & log transforms
│   ├── Analytics/
│   │   └── InsightAggregator.ps       # Phase 5: Grouped insights, aggregations & correlations
│   ├── Encoding/
│   │   └── CategoricalEncoder.ps      # Phase 6: Ordinal, target & dummy variable trap encoding
│   ├── Splitting/
│   │   └── DatasetSplitter.ps         # Phase 7: Deterministic train/test partition (80/20)
│   ├── Scaling/
│   │   └── FeatureScaler.ps           # Phase 8: Zero-leakage Z-score standardization
│   ├── Export/
│   │   └── DataExporter.ps            # Phase 9: Directory creation & clean CSV artifact exports
│   └── Pipeline/
│       └── CaliforniaHousingPipeline.ps # Phase 10: Object-oriented reusable pipeline engine
├── Titanic/
│   └── pp2.ps                         # Titanic survival exploratory demo
└── data/
    └── processed/                     # Generated artifact directory
        ├── X_train.csv                # Standardized training feature matrix (14,818 rows x 15 cols)
        ├── X_test.csv                 # Standardized testing feature matrix (3,704 rows x 15 cols)
        ├── y_train.csv                # Training target vector (14,818 rows)
        ├── y_test.csv                 # Testing target vector (3,704 rows)
        └── cal_housing_summary_report.csv # Descriptive statistics export
```

---

## 2. Technical Pipeline Breakdown

### Phase 1: High-Level Inspection (`DataInspector.ps`)
- **Dimensions & Footprint:** Inspects total row count ($N = 20,640$) and columns ($D = 9$) via `df.Shape` and cell count ($185,760$) via `df.Size`.
- **Observations Preview:** Generates first 5 sample rows using `df.Head(5)`.
- **Descriptive Statistics:** Generates numerical metrics (`mean`, `std`, `min`, $25\%$, $50\%$, $75\%$, `max`) via `df.Describe()`.
- **Missing Value Audit:** Computes per-column null counts using `df.Isna().Sum()`.

### Phase 2: Data Cleaning & Integrity Checks (`DataCleaner.ps`)
- **Median Imputation:** Checks numerical attributes (`AveBedrms`, `AveRooms`) and fills missing values using column median metrics calculated via `.Median()` and `.Fillna()`.
- **Deduplication:** Audits row duplication count using `df.Duplicated().Sum()`, followed by exact duplicate row removal via `df.DropDuplicates()`.
- **Verification:** Verifies that total residual missing cells equal 0 before proceeding to downstream processing.

### Phase 3: Outlier Handling & Filtering (`OutlierHandler.ps`)
- **Artificial Ceiling Clipping:** Filters out the artificial price ceiling at $\$500,000$ (`MedHouseVal < 5.0`), isolating natural market dynamics and retaining 19,648 rows.
- **Interquartile Range (IQR) Filtering:**
  - $Q_1 = \text{Quantile}(0.25) = 796.0$
  - $Q_3 = \text{Quantile}(0.75) = 1746.25$
  - $\text{IQR} = Q_3 - Q_1 = 950.25$
  - $\text{Lower Bound} = Q_1 - 1.5 \times \text{IQR} = -629.375$
  - $\text{Upper Bound} = Q_3 + 1.5 \times \text{IQR} = 3171.625$
- Filters out extreme population density outliers, yielding 18,522 clean records.

### Phase 4: Feature Transformation & Discretization (`FeatureTransformer.ps`)
- **Domain Ratios:**
  - `BedroomRatio = AveBedrms / AveRooms` (bedroom density proportion).
  - `RoomsPerOccupant = AveRooms / AveOccup` (room crowding metric).
- **Discretization / Binning:** Bins continuous `HouseAge` into three distinct tiers using `Pandas.Cut`:
  - `New`: $[0, 15]$ years.
  - `Moderate`: $(15, 35]$ years.
  - `Historical`: $(35, 100]$ years.
- **Skew Normalization:** Applies right-skew log transformation to `Population` using `Math.Log` (`log1p` behavior).

### Phase 5: Grouping, Aggregation & Correlations (`InsightAggregator.ps`)
- **Grouped Mean Pricing:** Evaluates target home pricing across `AgeGroup` categories.
- **Multi-Column Aggregations:** Aggregates multiple statistical metrics (`mean` of income, `median` of pricing, `sum` of population) grouped by age tier via `.Agg()`.
- **Correlation Matrix:** Computes Pearson correlation matrix with `df.Corr(numeric_only: true)` and ranks feature correlations against target pricing `MedHouseVal`.

### Phase 6: Feature Encoding Strategies (`CategoricalEncoder.ps`)
- **Strategy 1: Ordinal Scale Mapping:** Maps natural hierarchical scales (`New=0`, `Moderate=1`, `Historical=2`) via `.Map(ordinalMap)`.
- **Strategy 2: Target Encoding:** Replaces categories with mean target valuations via `.Groupby().Mean()` mapping.
- **Strategy 3: One-Hot Encoding:** Creates binary indicators with `Pandas.GetDummies(..., drop_first=true)` to avoid the dummy variable trap (multicollinearity).
- All encoded features are cast to numerical types (`float`/`int`) to ensure linear algebra and matrix compatibility.

### Phase 7: Pure-Pandas Train/Test Partitioning (`DatasetSplitter.ps`)
- **Target & Feature Separation:** Isolates target vector $y = \text{MedHouseVal}$ and drops target from $X$.
- **Deterministic 80/20 Partition:** Slices indices into:
  - Training features: $X_{\text{train}} \in \mathbb{R}^{14818 \times 15}$
  - Testing features: $X_{\text{test}} \in \mathbb{R}^{3704 \times 15}$
  - Training labels: $y_{\text{train}} \in \mathbb{R}^{14818}$
  - Testing labels: $y_{\text{test}} \in \mathbb{R}^{3704}$

### Phase 8: Zero-Leakage Feature Scaling (`FeatureScaler.ps`)
- **Leakage Prevention:** Mean ($\mu$) and standard deviation ($\sigma$) are computed **strictly from $X_{\text{train}}$**.
- **Vectorized Standardization:**
  $$X_{\text{scaled}} = \frac{X - \mu_{\text{train}}}{\sigma_{\text{train}}}$$
- **Verification:** Confirms $X_{\text{train}}$ has mean $\approx 0.0$ and std $= 1.0$, while $X_{\text{test}}$ reflects natural distribution shift without leakage.

### Phase 9: Automated Structural Artifact Export (`DataExporter.ps`)
- Recursively ensures the destination folder `data/processed/` exists via `OS.MakeDirs()`.
- Exports `X_train.csv`, `X_test.csv`, `y_train.csv`, and `y_test.csv` using `index=false` to eliminate unnecessary row index counter bloat.
- Writes descriptive analytical summary to `cal_housing_summary_report.csv`.

### Phase 10: Reusable Pipeline Engine (`CaliforniaHousingPipeline.ps`)
- Encapsulates state (`TrainMean`, `TrainStd`) inside an object-oriented class mimicking modern Scikit-Learn transformers.
- Implements `FitTransform()` for training sets and `Transform()` for unseen inference batches.

---

## 3. Configuration & PythonSharp Compilation

### Project File (`PandasDemo.psproj`)
```xml
<Project Sdk="PythonSharp.Sdk/0.1.0">
  <PropertyGroup>
    <AssemblyName>PandasDemo</AssemblyName>
    <TargetFramework>py3.11</TargetFramework>
  </PropertyGroup>
</Project>
```

### Stub & Layer Configuration (`.ps.conf.json`)
```json
{
  "stub_layers": {
    "00_core": true,
    "01_python_stdlib": true,
    "02_scientific_and_ai": false,
    "03_typeshed_replica": false,
    "dedicated_stubs": true
  },
  "disabled_packages": ["pandas"],
  "preferred_surface": 2
}
```
- `"dedicated_stubs": true`: Instructs the compiler to automatically discover and resolve triple-surface stubs under `.ps-stubs/pandas`.
- `"disabled_packages": ["pandas"]`: Suppresses the default ambient `02_scientific_and_ai` stubs to prevent symbol collision with the dedicated Surface 2 bridge stubs.
- `"preferred_surface": 2`: Prioritizes Surface 2 (idiomatic C# bridge with PascalCase methods and canonical Python name mappings).

---

## 4. Build and Execution Instructions

### Prerequisites
- Python 3.11+
- PythonSharp Compiler CLI (`psc`)
- Virtual environment with `pandas` installed

### Build
From the `Sample_Practice/PandasFullPrac` directory, execute:
```bash
psc rebuild
```
This cleans the `dist/` folder and emits 13 compiled Python modules:
- `dist/pandas_demo/__init__.py`
- `dist/pandas_demo/cal_housing/__init__.py`
- `dist/pandas_demo/cal_housing/inspection.py`
- `dist/pandas_demo/cal_housing/cleaning.py`
- `dist/pandas_demo/cal_housing/outliers.py`
- `dist/pandas_demo/cal_housing/engineering.py`
- `dist/pandas_demo/cal_housing/encoding.py`
- `dist/pandas_demo/cal_housing/analytics.py`
- `dist/pandas_demo/cal_housing/splitting.py`
- `dist/pandas_demo/cal_housing/scaling.py`
- `dist/pandas_demo/cal_housing/export.py`
- `dist/pandas_demo/cal_housing/pipeline.py`
- `dist/pandas_demo/titanic.py`

### Run
Execute the application runner:
```bash
python run_main.py
```
Or via `uv`:
```bash
uv run python run_main.py
```

### Verification
Check generated dataset outputs in `data/processed/`:
```bash
ls -lh data/processed/
```
Output:
- `X_train.csv` (~4.2 MB)
- `X_test.csv` (~1.1 MB)
- `y_train.csv` (~85 KB)
- `y_test.csv` (~22 KB)
- `cal_housing_summary_report.csv` (~1.1 KB)
