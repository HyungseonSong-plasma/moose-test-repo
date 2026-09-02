# Issue #93 — R3 electron residual isolation

This workspace owns the diagnostic continuation after Issue #92 closed with the
combined R3 electron residual blocker unresolved.

## Scope

The scientific scope remains pre-Poisson R3:

- real `qvt.msh` geometry/mesh identity;
- accepted Issue #2 electron lookup/drift-diffusion semantics;
- prescribed electric field ownership retained;
- Poisson and charge-to-potential feedback OFF.

Reduced cases are diagnostic-only and cannot establish Issue #91 PASS.

## J0 — qpx-free dependency audit

`dependency_audit.py` reconstructs canonical Issue #91 R3-E0 and checks residual
ownership.

```text
R_e <- n_e                         nonlinear self block
R_e <- electron_diffusion(p,T_g)  p nonlinear cross dependency
R_e <- electron_mobility(p,T_g)   inactive in R3-E0 because E=0
R_e <- phi_prescribed             prescribed function, not Newton variable
```

Current ownership:

```text
p    = nonlinear INSFV pressure variable
T_g  = constant AD functor in state_constants
phi  = prescribed function
```

Therefore `dR_e/dT_g` is not an assembled Newton cross block in current R3.
The reciprocal heavy path remains structurally present through:

```text
n_e -> QPXThermalDiffusionMaterial -> D_mix_* -> heavy diffusion residuals
```

## J1 — real-QVT electron-only zero-field discriminator — EVR1 complete

The corrected J1 does not reconstruct a new framework contract. It derives
straight from the historically accepted Issue #2 `qvt_prepoisson/input.i`, with
identical `qvt.msh` and `electron_moments.txt`, and changes only:

```text
phi_prescribed: -0.01*x -> 0.0*x
```

Heavy nonlinear equations are absent in the accepted Issue #2 reference. J1
therefore tests the real-QVT electron path with frozen lookup state and Poisson
OFF.

Returned EVR1:

```text
P2 PASS
P3 rc = 1
SNES norm = 1.197516979581 repeated without descent
linear solve = CONVERGED_RTOL / 1 iteration
nonlinear solve = DIVERGED_LINE_SEARCH / iteration 0
timestep cut back to dtmin = 1e-12
```

Scientific consequence:

```text
heavy <-> electron cross-coupling is not required to reproduce the blocker
```

This does not by itself prove a C++ defect because zero prescribed field is the
scientific discriminator relative to the historical Issue #2 accepted case.

## J2 — one-shot real-QVT electron operator decomposition — EVR2 next

`operator_decomposition.py` derives every case from the same accepted Issue #2
real-QVT input and uses the accepted Issue #2 `expected.json` observable contract.

```text
C0 accepted #2 current-executable control
   time + diffusion + drift, E=0.01

C1 zero-field time-only

C2 zero-field time + diffusion

C3 zero-field time + drift

C4 zero-field time + diffusion + drift
   repeatability case, only reached if C0-C3 pass
```

Decision tree:

```text
C0 fails -> E4 current-executable/historical-control regression favored
C1 fails -> E3 transient/convergence/runtime representation favored
C2 fails -> E2 diffusion / framework-effective FV boundary path favored
C3 fails -> E1 zero-field electrostatic-drift path favored
C4 fails -> electron-operator interaction favored
all pass -> J1 repeatability/configuration HOLD
```

### EVR protection

All five case inputs are prepared and all five P2 `--check-input` calls are run
**before any P3 launch**. Therefore a J2 construction/framework-contract failure
does not consume EVR2.

Once P3 begins, the adaptive C0→C4 batch is one governed Issue #93 scientific
result return and consumes EVR2. It stops at the first failing scientific owner.

The accepted Issue #2 checker semantics are reused for runtime classification:
positive physical row, transport lookup values, positivity, inventory/mean
closure, and qvt finite-state requirement.

## J3 — final focused confirmation — reserved EVR3

EVR3 is reserved for exactly one owner selected by J2. Because the electron-only
real-QVT system contains only `n_e` as nonlinear variable, a bounded finite-
difference Jacobian check may be admissible for the isolated failing case even
though the full combined-R3 system exceeded the earlier Jacobian cost guard.

No combined-R3 all-DOF Jacobian sweep is authorized here.

## Execution

J0, qpx-free / EVR 0:

```bash
python -m experiments.Issue93_r3_electron_isolation.dependency_audit
```

Historical J1 runner, already consumed EVR1:

```bash
python -m experiments.Issue93_r3_electron_isolation.run --qpx "$QPX_OPT"
```

J2 one-shot operator decomposition, next local scientific run:

```bash
python -m experiments.Issue93_r3_electron_isolation.operator_decomposition \
  --qpx "$QPX_OPT"
```

Generated artifacts are written to a temporary directory unless `--work-dir` is
supplied. `summary.json` records P2/P3 results, accepted-control checker results,
residual trajectories, first failing case, hypothesis status, and EVR accounting.
