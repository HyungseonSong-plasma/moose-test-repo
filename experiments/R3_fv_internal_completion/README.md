# R3 FV internal completion

Purpose: finish the remaining finite-volume ownership split for the R3 electron constant-state diffusion blocker without another probe-design cycle.

This campaign is self-contained and keeps the real `qvt.msh`, `RZ`, and `plasma` domain fixed. Geometry is `HELD_FIXED_OUT_OF_SCOPE`; it is not declared correct or exonerated.

## One-queue evidence matrix

The runner prebuilds and executes the remaining independent discriminators before seeing their runtime outcomes:

- `C0_TIME_ONLY`: execution/control reference.
- `F0/F1/F2`: nonlinear `FVDiffusion` internal path at `n_e=1e16`, `n_e=1`, and the O(1) diagnostic absolute-tolerance probe.
- `O0/O1`: nonlinear `FVOrthogonalDiffusion`, which bypasses Green-Gauss/non-orthogonal reconstruction and uses only the cell-value difference over `dCN`.
- `G0/G1`: direct AD and Real `n_e` cell-gradient measurements with two-term boundary reconstruction.
- `G2/G3`: the same direct gradient measurements with one-term boundary reconstruction.
- Offline same-mesh RZ decomposition: reproduces the pinned-MOOSE interior Green-Gauss face sum, RZ coordinate weighting, and `n_e/r` subtraction using the unchanged `qvt.msh`.
- Jacobian probes are predeclared for `F0`, `F1`, and `O0`; they are not selected after the cheap matrix.

The canonical diagnosis contains exactly one `primary_owner` or `null`. Jacobian-only findings are recorded under `secondary_candidates` so multiple simultaneous primary owners cannot be emitted.

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
