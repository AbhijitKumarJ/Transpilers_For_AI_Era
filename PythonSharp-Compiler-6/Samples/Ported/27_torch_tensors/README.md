# PythonSharp Tier 11 Port: PyTorch Tensors & Neural Autograd Engine

This sample dogfoods PythonSharp on **PyTorch** (`torch`, `torch.nn`, `torch.optim`) for deep learning tensors, multi-layer perceptron (MLP) architectures, automatic differentiation (`backward()`), Adam gradient optimization, and triple-surface deep learning APIs with **Zero Runtime Wrapper Tax**.

---

## Architecture & Features

1. **Neural Network Architecture (`TwoLayerPerceptron`)**:
   - `FullyConnectedLinearLayer` input $\rightarrow$ hidden $\rightarrow$ output layers.
   - Non-linear activation functions (`ActivationFunctions.ApplyRectifiedLinearUnit`).
   - Loss functions (`MeanSquaredErrorLoss`) and gradient optimizers (`GradientOptimizer` / Adam).
   - Training loop with gradient zeroing, autograd backpropagation, and parameter updating.

2. **Tensor Shape Inspection & Device Analytics (`TensorAnalyticsService`)**:
   - Strongly typed `TorchTensor<double>` shape querying (`TensorShape`).
   - Reductions: `ComputeMean()` and `ComputeSum()`.
   - Dynamic device selection (`AcceleratorRuntime.SelectOptimalDeviceName`).

3. **Tri-Modal Surface Verification (`TriModalDeepLearningVerification`)**:
   - **Surface 1 Enterprise**: `TensorFactory`, `NeuralLayerFactory`, `LossCriterionFactory`, `OptimizerFactory`, `ActivationFunctions`, `AcceleratorRuntime`.
   - **Surface 3 C# Bridge**: `PythonSharp.PyTorch.torch.ManualSeed`, `torch.NN.Linear`, `torch.Optim.Adam`, `torch.ReLU`.
   - **Surface 2 Raw Python ABI**: `torch.torch.manual_seed`, `torch.torch.nn.Linear`, `torch.torch.optim.Adam`, `torch.torch.relu`.

---

## Compilation & Verification

To build and run the sample:

```bash
# 1. Compile the PythonSharp project
psc build Samples/Ported/27_torch_tensors/TorchTensors.psproj -o Samples/Ported/27_torch_tensors/dist

# 2. Execute verification test harness
python3 Samples/Ported/27_torch_tensors/run_torch.py
```

