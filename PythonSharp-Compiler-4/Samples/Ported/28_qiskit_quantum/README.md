# PythonSharp Tier 11 Port: Qiskit Quantum Circuit Simulation & Measurement

This sample dogfoods PythonSharp on **Qiskit** (`qiskit`, `qiskit.quantum_info`) for quantum register circuits, Bell pair entanglement, GHZ states, quantum teleportation protocols, unitary rotations, and statevector probability sampling with **Zero Runtime Wrapper Tax**.

---

## Architecture & Features

1. **Bell State Entanglement Generator (`BellStateGenerator`)**:
   - 2-qubit register circuit with Hadamard gate ($H$) and Controlled-NOT gate ($CX$).
   - Maximally entangled Bell pair $|\Phi^+\rangle = \frac{|00\rangle + |11\rangle}{\sqrt{2}}$.
   - Simulates statevector and measures bitstring probability distribution ($P(00) = 0.5, P(11) = 0.5$).

2. **GHZ State Engine (`GhzStateEngine`)**:
   - Multi-qubit Greenberger–Horne–Zeilinger (GHZ) state $|\text{GHZ}\rangle = \frac{|000\rangle + |111\rangle}{\sqrt{2}}$.
   - Entanglement propagation via chained CNOT gates.

3. **Quantum Teleportation Protocol (`QuantumTeleportationProtocol`)**:
   - 3-qubit protocol transmitting quantum information using shared entanglement and classical correction gates.

4. **Parameterized Unitary Rotations (`QuantumRotationService`)**:
   - Rotation gates $R_x(\theta)$, $R_y(\theta)$, $R_z(\theta)$ on single-qubit states.

5. **Tri-Modal Surface Verification (`TriModalQuantumVerification`)**:
   - **Surface 1 Enterprise**: `QuantumCircuitFactory.CreateBellPairEntangledCircuit()`, `QuantumSimulator.SimulateStatevectorFromCircuit()`.
   - **Surface 3 C# Bridge**: `PythonSharp.Qiskit.qk.CreateCircuit()`, `circuit.Hadamard()`, `circuit.CNot()`, `qk.QuantumInfo.FromInstruction()`.
   - **Surface 2 Raw Python ABI**: `qiskit.qk.QuantumCircuit()`, `circuit.h()`, `circuit.cx()`, `qk.quantum_info.from_instruction()`.

---

## Compilation & Verification

To build and run the sample:

```bash
# 1. Compile the PythonSharp project
psc build Samples/Ported/28_qiskit_quantum/QiskitQuantum.psproj -o Samples/Ported/28_qiskit_quantum/dist

# 2. Execute verification test harness
python3 Samples/Ported/28_qiskit_quantum/run_qiskit.py
```

