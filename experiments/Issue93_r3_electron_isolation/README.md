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

The corrected J1 derives straight from the historically accepted Issue #2
`qvt_prepoisson/input.i`, with identical `qvt.msh` and `electron_moments.txt`,
and changes only:

```text
phi_prescribed: -0.01*x -> 0.0*x
```

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

## J2 — real-QVT electron operator decomposition — EVR2 complete

`operator_decomposition.py` derives every case from the same accepted Issue #2
real-QVT input and uses the accepted Issue #2 observable contract.

Returned governed batch:

```text
C0 accepted #2 control
   time + diffusion + drift, E=0.01
   PASS

C1 zero-field time-only
   PASS
   residuals = [0.0, 0.0]

C2 zero-field time + diffusion
   FAIL
   residual = 1.197516979581 repeated without descent
```

The adaptive batch stopped at C2. C3/C4 were not launched.

Decision:

```text
E2_DIFFUSION_OR_FV_BOUNDARY_PATH_FAVORED
Issue #93 EVR = 2/3
```

The ordering matters:

```text
C0 PASS -> accepted #2 current-executable control reproduced
C1 PASS -> time/init/runtime representation disfavored
C2 FAIL -> diffusion / framework-effective FV boundary path favored
```

C2 does not by itself prove an `FVDiffusion` implementation defect.

## J3 — diffusion boundary-flux ownership confirmation — reserved EVR3

`boundary_flux_ownership.py` is a bounded confirmation for the C2 owner selected
by J2. It does not add wall or surface-reaction physics.

The real-QVT plasma interfaces are:

```text
inlet
outlet
plasma_electrode
plasma_metal
plasma_right
plasma_cover
plasma_wafer
plasma_focus_ring
```

MOOSE `FVDiffusion` is an FV flux kernel and executes on internal boundaries by
default. J3 first derives D0 from exact J2 C2 and changes only the diffusion
execution contract:

```text
FVDiffusion(n_e)
+ boundaries_to_avoid = '<all plasma interface sidesets above>'
```

No coefficient, initial condition, timestep, solver tolerance, drift term, wall
loss, or surface reaction is added.

### J3 decision order

All predeclared J3 inputs are P2 checked before any P3 launch.

```text
D0: C2 + plasma-interface FVDiffusion execution excluded

D0 converges, accepted checker PASS, electron residual trace -> 0
  -> FRAMEWORK_EFFECTIVE_DIFFUSION_BOUNDARY_FLUX_OWNERSHIP_CONFIRMED
  -> stop J3; do not launch Jacobian fallback

otherwise
  -> run exact original C2 once with PETSc -snes_test_jacobian
  -> return bounded AD-vs-FD Jacobian evidence
```

The D0 discriminator is intentionally diagnostic. If ownership is confirmed,
the subsequent implementation work is to give plasma-wall physics an explicit
owner, using a surface-reaction/wall-flux model rather than relying on implicit
bulk-diffusion interface execution.

The Jacobian fallback remains restricted to the electron-only C2 system. No
combined-R3 all-DOF Jacobian sweep is authorized.

### EVR protection

D0 and JAC are both constructed and P2 checked before P3. A P2 construction or
framework-contract failure therefore consumes no EVR3.

Once D0 P3 launches, the bounded J3 batch consumes EVR3 exactly once, whether it
stops after D0 or continues to the predeclared C2 Jacobian fallback.

## Execution

J0, qpx-free / EVR 0:

```bash
python -m experiments.Issue93_r3_electron_isolation.dependency_audit
```

Historical J1 runner, already consumed EVR1:

```bash
python -m experiments.Issue93_r3_electron_isolation.run --qpx "$QPX_OPT"
```

Historical J2 operator decomposition, already consumed EVR2:

```bash
python -m experiments.Issue93_r3_electron_isolation.operator_decomposition \
  --qpx "$QPX_OPT"
```

J3 focused boundary-flux ownership confirmation, next scientific run:

```bash
python -m experiments.Issue93_r3_electron_isolation.boundary_flux_ownership \
  --qpx "$QPX_OPT"
```

Generated artifacts are written to a temporary directory unless `--work-dir` is
supplied. `summary.json` records P2/P3 results, residual trajectories, checker
results, the J3 decision, EVR accounting, and Jacobian evidence if the fallback
was required.
