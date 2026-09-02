# Issue #93 — R3 electron residual isolation

This experiment workspace owns the diagnostic continuation after Issue #92 closed
with the combined R3 electron residual blocker unresolved.

## Scope

The scientific scope remains pre-Poisson R3:

- real `qvt.msh` geometry/mesh identity;
- accepted Issue #2 electron drift-diffusion semantics;
- prescribed electric field ownership retained;
- Poisson and charge-to-potential feedback OFF.

The first discriminator deliberately removes the heavy nonlinear equations while
freezing the electron lookup state to the same entering R3-E0 values. This is a
diagnostic reduction only and cannot establish Issue #91 PASS.

## J0 — qpx-free dependency audit

`dependency_audit.py` reconstructs the canonical Issue #91 R3-E0 input and checks
the residual ownership contract. The expected structural result is:

```text
R_e <- n_e                         nonlinear self block
R_e <- electron_diffusion(p,T_g)  p nonlinear cross dependency
R_e <- electron_mobility(p,T_g)   inactive in R3-E0 because E=0
R_e <- phi_prescribed             prescribed function, not a Newton variable
R_e <- electron boundary contract no explicit electron FVBC objects inserted
```

`T_g` is an AuxVariable in the combined R3 input, so it is a coefficient/runtime
dependency but not an assembled nonlinear cross block. `p` is nonlinear.

The reciprocal heavy path is through `QPXThermalDiffusionMaterial`, which consumes
`electron_number_density = n_e`; its `D_mix_*` properties feed the six solved
heavy-species mixture-averaged diffusion residuals.

## J1 — real-QVT frozen-heavy electron discriminator

`run.py` creates a temporary case using the exact Issue #91 mesh-generation block
and accepted electron table, then solves only:

```text
FVTimeKernel(n_e)
+ FVDiffusion(n_e, electron_diffusion)
+ QPXFVElectrostaticDrift(n_e, E=0)
```

with:

```text
p = 1.33322 Pa       frozen functor
T_g = 600 K          frozen functor
n_e(t=0) = 1e16 m^-3 uniform
E = 0
Poisson OFF
```

No heavy transport equation participates in the nonlinear solve. Under this
reduction the electron coefficients are frozen and the residual is linear in
`n_e`. The uniform, source-free, zero-field state is also a null-flux invariant.

Decision:

```text
J1 converges + invariant checker PASS
  -> local real-QVT electron equation path supported
  -> combined-R3 cross-coupling/Jacobian branch becomes the next discriminator

J1 reproduces electron stagnation/nonconvergence
  -> electron equation/BC/material/runtime representation branch is favored
```

## Execution

J0 is qpx-free and consumes no scientific EVR:

```bash
python -m experiments.Issue93_r3_electron_isolation.dependency_audit
```

J1 performs one governed local QPX scientific run and is Issue #93 EVR1:

```bash
python -m experiments.Issue93_r3_electron_isolation.run --qpx "$QPX_OPT"
```

The runner performs P2 `--check-input` first. P2 failure does not launch P3.
Generated runtime artifacts are written to a temporary directory unless
`--work-dir` is supplied.
