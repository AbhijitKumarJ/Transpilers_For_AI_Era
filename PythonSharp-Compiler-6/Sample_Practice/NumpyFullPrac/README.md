# NumpyFullPrac: From-Scratch Deep Learning & Neural Network Framework in PythonSharp

An enterprise-grade, from-scratch deep learning and neural network library implemented in **PythonSharp (`.ps`)**, compiling into zero-overhead Python 3.11+ code with native **NumPy** runtime execution. 

This project implements the comprehensive mathematical calculus and architectural blueprints from [`Building a NN.md`](./Building%20a%20NN.md), structured into a highly modular, decoupled namespace hierarchy where files average ~50 lines and `dynamic` is restricted strictly to low-level array operations.

---

## 1. Architectural Overview & Folder Segregation

Following the architectural standards established in `Sample_Practice/PandasFullPrac`, all components are segregated into dedicated domain subdirectories under `NeuralNet/`:

```
Sample_Practice/NumpyFullPrac/
├── NumpyFullPrac.psproj                 # PythonSharp Project Configuration
├── .ps.conf.json                        # Stub layer configuration (scientific_and_ai: true)
├── ProjMain.ps                          # Master CLI entry point
├── TestUtil.ps                          # Diagnostic logging utilities
├── run_main.py                          # Python execution bootstrap runner
├── Building a NN.md                     # Deep learning blueprint reference document
├── README.md                            # Comprehensive technical documentation
└── NeuralNet/                           # Neural Network Domain Architecture
    ├── NeuralNetRunner.ps               # Master orchestrator executing Phases 1 through 4 (~30 lines)
    ├── Activations/                     # Non-linear activation functions & mathematical derivatives
    │   ├── SigmoidActivation.ps         # Numerically clipped sigmoid & analytical derivative (~25 lines)
    │   ├── ReluActivation.ps            # Rectified Linear Unit & gradient step function (~25 lines)
    │   ├── LeakyReluActivation.ps       # Leaky ReLU with parametric alpha slope (~30 lines)
    │   ├── TanhActivation.ps            # Hyperbolic tangent & 1 - a^2 derivative (~25 lines)
    │   └── SoftmaxActivation.ps         # Exp-shifted stable softmax across axis 1 (~20 lines)
    ├── Layers/                          # Modular neural network structural layers
    │   ├── DenseLayer.ps                # Linear transformation, He/Xavier init & L2 backprop (~100 lines)
    │   ├── DropoutLayer.ps              # Inverted dropout with train/eval mode switching (~55 lines)
    │   ├── BatchNormalizationLayer.ps   # Running statistics, scale/shift (γ, β) & backprop (~100 lines)
    │   ├── LayerNormLayer.ps            # Feature-dimension normalization for transformer blocks (~35 lines)
    │   └── SoftmaxOutputLayer.ps        # Combined Softmax + Categorical Cross-Entropy (dZ = P - Y) (~45 lines)
    ├── Losses/                          # Objective functions & analytical loss gradients
    │   ├── MSELoss.ps                   # Mean Squared Error forward loss & 2/N(P - Y) gradient (~30 lines)
    │   └── CrossEntropyLoss.ps          # Epsilon-clipped categorical cross-entropy & gradient (~30 lines)
    ├── Optimizers/                      # Parameter optimization algorithms & schedulers
    │   ├── SGDOptimizer.ps              # Stochastic gradient descent with momentum velocity (~50 lines)
    │   ├── AdamOptimizer.ps             # First/second moments (m, v) with bias correction (~85 lines)
    │   ├── CosineScheduler.ps           # Cosine annealing learning rate schedule (~40 lines)
    │   └── GradientClipper.ps           # Value clipping and global L2 norm clipping (~30 lines)
    ├── Regularization/                  # Overfitting mitigation & training controls
    │   └── EarlyStoppingHandler.ps      # Loss patience tracking and convergence termination (~40 lines)
    ├── Data/                            # Tensor batching and synthetic dataset synthesis
    │   ├── BatchPair.ps                 # Strongly typed record container (Features, Targets) (~6 lines)
    │   ├── DatasetGenerator.ps          # Non-linear XOR & 3-class Gaussian cluster generators (~45 lines)
    │   └── MiniBatchIterator.ps         # Multi-slice batch iterator with random permutation (~45 lines)
    ├── Metrics/                         # Telemetry and model evaluation utilities
    │   └── ModelEvaluator.ps            # Argmax classification accuracy & telemetry logging (~40 lines)
    ├── Models/                          # Composable model containers
    │   └── SequentialMLP.ps             # Multi-layer container with training mode & L2 penalty (~65 lines)
    ├── Attention/                       # Transformer & self-attention architectures
    │   ├── ScaledDotProductAttention.ps # Scaled dot-product attention with causal mask (~45 lines)
    │   └── MultiHeadAttention.ps        # Multi-head projection, slice splitting & concatenation (~65 lines)
    └── Pipelines/                       # End-to-end executable learning benchmarks
        ├── XORBenchmarkPipeline.ps      # Phase 1: 2-layer MLP solving non-linear XOR (~75 lines)
        ├── MultiClassClassificationPipeline.ps # Phase 2: 3-class cluster classification with Adam (~70 lines)
        ├── MiniBatchRegularizationPipeline.ps  # Phase 3: Mini-batch SGD + L2 + Dropout + BatchNorm (~110 lines)
        └── AttentionDemonstrationPipeline.ps   # Phase 4: Self-Attention & Multi-Head Transformer (~65 lines)
```

---

## 2. Typing Discipline & Controlled Dynamic Isolation

In strict accordance with enterprise PythonSharp conventions:
- **Strong Typing on Public Boundaries**: All public API signatures, method parameters, return types, and class fields use strong types (`NDArray<double>`, `NDArray<int>`, `BatchPair`, `double`, `int`, `bool`, `string`).
- **Controlled Dynamic Isolation**: `dynamic` is localized strictly to intra-method mathematical expressions requiring NumPy runtime array methods (e.g., `_np.dot`, `_np.clip`, `_np.exp`, multi-axis slicing `[.., start..end]`, or dynamic broadcasting).
- **Zero Prefix Cast Hazards**: Avoids invalid prefix casts like `(double)x` by leveraging PythonSharp's native promotion rules or `as` expressions.
- **Null Safety**: Avoids comparing NumPy arrays directly with `== null` (which triggers NumPy ambiguity errors) by maintaining explicit boolean state flags (`Initialized`).

---

## 3. Four Integrated Deep Learning Pipelines

### Phase 1: XOR Non-Linear Benchmark (`XORBenchmarkPipeline.ps`)
- **Objective**: Solve the linearly inseparable XOR logic problem using a 2-layer Multilayer Perceptron (`2 -> 4 -> 1`).
- **Components**: `SigmoidActivation`, `MSELoss`, `SGDOptimizer` (learning rate: 0.8, momentum: 0.9).
- **Result**: Initial Loss $0.3343 \rightarrow 0.0018$ over 350 epochs.
  - `[0, 0] => 0.036 (Expected 0.0)`
  - `[0, 1] => 0.965 (Expected 1.0)`
  - `[1, 0] => 0.947 (Expected 1.0)`
  - `[1, 1] => 0.045 (Expected 0.0)`

### Phase 2: 3-Class Cluster Classification & Adam Optimizer (`MultiClassClassificationPipeline.ps`)
- **Objective**: Classify a 3-class synthetic 2D Gaussian cluster dataset (120 samples) into one-hot target vectors.
- **Components**: `DenseLayer` (2 -> 16 with ReLU, 16 -> 3 linear), `SoftmaxOutputLayer` (combined Softmax + Categorical Cross-Entropy with analytical $dZ = (P - Y) / N$), `AdamOptimizer` ($\text{lr} = 0.04, \beta_1 = 0.9, \beta_2 = 0.999$).
- **Result**: Loss dropped from $3.3898 \rightarrow 0.0011$, reaching **100.0% accuracy** within 40 epochs.

### Phase 3: Mini-Batch Regularization & Schedulers (`MiniBatchRegularizationPipeline.ps`)
- **Objective**: Full modern regularization suite on mini-batches with training vs evaluation modes.
- **Components**:
  - `MiniBatchIterator` with random shuffling (batch size 25).
  - `DenseLayer` with $L_2$ weight decay regularization ($\lambda = 0.001$).
  - `BatchNormalizationLayer` with running mean/variance and scale/shift ($\gamma, \beta$) backpropagation.
  - `DropoutLayer` with inverted dropout (rate 0.2) active during training and bypassed during evaluation.
  - `CosineScheduler` decaying learning rate smoothly from 0.05 to 0.005.
  - `GradientClipper` applying global $L_2$ norm capping.
  - `EarlyStoppingHandler` tracking validation loss with patience counter.
- **Result**: Convergence reached in 32 epochs before early stopping; test-mode evaluation with dropout disabled achieved **100.0% accuracy**.

### Phase 4: Scaled Dot-Product & Multi-Head Attention (`AttentionDemonstrationPipeline.ps`)
- **Objective**: Matrix-level multi-head self-attention and transformer normalization blocks.
- **Components**:
  - `ScaledDotProductAttention`: Computes $\text{Attention}(Q, K, V) = \text{Softmax}\left(\frac{Q K^T}{\sqrt{d_k}} + M\right) V$.
  - Causal Masking: Applies upper-triangular masking ($-\infty$) to enforce autoregressive attention.
  - `MultiHeadAttention`: Multi-head projection ($W_q, W_k, W_v, W_o$) with 2 parallel attention heads.
  - `LayerNormLayer`: Residual connection followed by feature normalization yielding zero mean ($\sim 10^{-16}$) and unit variance ($0.9999$).

---

## 4. How to Build and Run

### Prerequisites
- Python 3.11+ virtual environment with `numpy` installed.
- PythonSharp CLI (`psc`).

### Compilation
From the project directory:
```bash
.venv/bin/psc rebuild Sample_Practice/NumpyFullPrac/NumpyFullPrac.psproj
```

### Execution
Run the compiled pipeline via Python:
```bash
cd Sample_Practice/NumpyFullPrac
../../.venv/bin/python run_main.py
```
