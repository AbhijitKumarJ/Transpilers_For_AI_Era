# Sample 24: Declarative Plotting Builders (Tier 10)

A ported visualization module demonstrating fluent, declarative plotting builders in **PythonSharp** using `matplotlib` and `seaborn`.

---

## 1. Features Demonstrated

- **Fluent C# Chart Builder (`ChartBuilder`)**:
  - Declarative chaining: `.WithTitle(...)`, `.WithXAxis(...)`, `.WithYAxis(...)`, `.WithDpi(...)`, `.EnableLegend()`
  - Multi-series composability: `.AddLineSeries(...)`, `.AddScatterPoints(...)`, `.AddHistogram(...)`
  - Encapsulated output emission: `.Save(path)`
- **Triple-Surface Architecture**:
  - **Surface 1 (Enterprise Architecture)**: Self-documenting static facades (`FigureCanvas.PlotLineSeries`, `StatisticalPlotter.RenderCorrelationHeatmap`)
  - **Surface 3 (C# Standardized Bridge)**: Familiar PascalCase plotting methods (`plt.Plot`, `plt.Scatter`, `plt.SaveFig`)
  - **Surface 2 (Raw Python snake_case ABI)**: Native `matplotlib.pyplot` function calls (`plt.hist`, `plt.title`, `plt.savefig`, `plt.close`)
- **Zero Runtime Wrapper Tax**: Compiled Python calls `matplotlib.pyplot` and `seaborn` directly with zero adapter proxies.

---

## 2. Compilation & Verification

### Build with PythonSharp Compiler (`psc`):
```bash
python3 -m psc.cli build PlottingBuilders.psproj -o dist
```

### Run Verification Harness:
```bash
python3 run_plotting.py
```

