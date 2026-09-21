# R3 FV internal completion

Purpose: finish the remaining finite-volume ownership split for the R3 electron constant-state diffusion blocker without another probe-design cycle or avoidable harness-rerun cycle.

This campaign is self-contained and keeps the real `qvt.msh`, `RZ`, and `plasma` domain fixed. Geometry is `HELD_FIXED_OUT_OF_SCOPE`; it is not declared correct or exonerated.

## One-queue evidence matrix

The runner prebuilds and executes the remaining independent discriminators before seeing their runtime outcomes:

- `C0_TIME_ONLY`: execution/control reference.
- `F0/F1/F2`: nonlinear `FVDiffusion` internal path at `n_e=1e16`, `n_e=1`, and the O(1) diagnostic absolute-tolerance probe.
- `O0/O1`: nonlinear `FVOrthogonalDiffusion`, which bypasses Green-Gauss/non-orthogonal reconstruction and uses only the cell-value difference over `dCN`.
- `P0_GRADIENT_PINNED_STYLE`: operational gate for the direct gradient measurement path. It mirrors the pinned-MOOSE functor-gradient regression pattern: `solve=false`, `Steady`, no solve-time FV kernels, and default Aux scheduling.
- `P1_GRADIENT_INITIAL_VARIANT`: independent `INITIAL`-scheduled counterfactual. Its failure is recorded operationally but does not invalidate the `P0`/G scientific path.
- `G0/G1`: direct AD and Real `n_e` cell-gradient measurements with two-term boundary reconstruction, using the same pinned-style execution contract as `P0`.
- `G2/G3`: the same direct gradient measurements with one-term boundary reconstruction, also using the pinned-style execution contract.
- Offline same-mesh RZ decomposition: reproduces the pinned-MOOSE interior Green-Gauss face sum, RZ coordinate weighting, and `n_e/r` subtraction using the unchanged `qvt.msh`.
- Jacobian probes are predeclared for `F0`, `F1`, and `O0`; they are not selected after the cheap matrix.

## RZ coordinate contract

The accepted input uses:

```text
coord_type = RZ
rz_coord_axis = Y
```

In MOOSE, `rz_coord_axis` identifies the symmetry/axial axis. Therefore this configuration means:

```text
symmetry / axial axis = Y
radial coordinate     = X
radial component      = 0
```

The offline RZ reproducer therefore defaults to `radial_axis = 0`. Magnitude agreement between the offline RZ arithmetic and the direct QPX gradient is treated only as supporting evidence. It is not sufficient by itself to emit the RZ-specific atomic owner; spatial/component agreement would also be required.

When the direct interior Green-Gauss gradient is nonzero in both AD and Real paths while `FVOrthogonalDiffusion` remains exactly zero, the conservative primary owner is:

```text
FV_GREEN_GAUSS_CELL_GRADIENT_CONSTANT_PRESERVATION
```

RZ-specific versus more general Green-Gauss arithmetic remains a lower-level unresolved mechanism until stronger evidence is available.

## Gradient harness hardening

Gradient cases deliberately retain the accepted `qvt.msh`, RZ coordinate system, `[Materials]` coverage, and the FV `n_e` variable while removing objects that are irrelevant to direct gradient sampling:

```text
removed from P0/P1/G0-G3
  [FVKernels]
  FVTimeKernel
  FVDiffusion
  [FunctorMaterials]
  QPXElectronTransportLookupMaterial
  legacy [Postprocessors]
```

The safe scientific gradient path is:

```text
[Problem]
  solve = false
[]

MooseVariableFVReal n_e
  -> ADFunctorElementalGradientAux / FunctorElementalGradientAux
  -> MONOMIAL_VEC AuxVariables
  -> VectorVariableComponentAux
  -> ElementValueSampler

[Executioner]
  type = Steady
[]
```

`P0` and all `G` cases use the pinned-style/default Aux schedule. `P1` alone forces `execute_on = INITIAL` as a counterfactual. The case builder performs a static contract check before staging and rejects any gradient input that accidentally retains a time kernel, nonlinear diffusion kernel, QPX transport material, or legacy postprocessor.

Scientific Green-Gauss ownership is gated by `P0`:

```text
P0 PASS
  -> G0-G3 scientific evidence may be classified

P0 FAIL
  -> primary_owner = null
  -> status = HOLD_GRADIENT_PROBE
  -> G0-G3 excluded from scientific ownership

P1 FAIL with P0 PASS
  -> record INITIAL-schedule operational finding
  -> continue G0-G3 scientific classification
```

This keeps operational construction/runtime failures out of scientific ownership.

## Jacobian one-shot contract

Jacobian diagnostics are evidence probes, not transient integrations. They therefore use:

```text
Executioner/num_steps=1
Executioner/abort_on_solve_fail=true
-snes_test_jacobian
```

`-snes_test_jacobian_view` is deliberately not used. A nonlinear failure after the Jacobian comparison aborts immediately instead of triggering `ConstantDT` timestep halving and repeated Jacobian evaluations. This prevents a failed Jacobian probe from blocking the remaining completion queue or producing multi-megabyte matrix dumps.

The canonical diagnosis contains exactly one `primary_owner` or `null`. Jacobian-only findings are recorded under `secondary_candidates`, and probe-execution findings are recorded under `operational_findings`, so multiple simultaneous primary scientific owners cannot be emitted.

## Execute

From the repository root on the QPX machine:

```bash
python -m experiments.R3_fv_internal_completion.run \
  --qpx "$QPX_OPT" \
  --results-root "$PWD/r3_results"
```

The run prints `R3_FV_COMPLETION_ROOT`. Preserve that entire directory.

## Artifacts

The completion root contains:

- `identity.json`
- `case_matrix.json`
- `gradient_matrix.json`
- `rz_decomposition.json`
- `jacobian_matrix.json`
- `final_diagnosis.json`
- `summary.json`
- `error_events.jsonl` and error-stat summaries
- staged `cases/`, raw `logs/`, and `jacobian/` evidence

The terminal contract remains:

```text
Evidence -> Atomic Owner -> Remedy -> Verification
```

No production remedy is authorized merely because a diagnostic substitution passes.
