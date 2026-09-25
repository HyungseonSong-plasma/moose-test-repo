# Issue #310 Gen34 — relax_2x reference input preparation

This generation prepares the final controlled performance-reference inputs. It does not launch a benchmark.

## Why the historical Sequence01 input is not copied verbatim

The historical `relax_2x` case (run `35837437816`) used the superseded Issue306 wall09/Bohm-positive-ion lane and the old residual-only fixed-point stopping rule. Its measured runtime remains useful as an engineering-history reference, but it is not an accuracy-matched scientific comparator for the current #310 endpoint.

## Controlled reference

`relax2x_reference_20ns` uses the current canonical transient/time-aware thermal plasma model and current measurement policy:

- 88 heavy cycles / 352 electron steps (~19.941 ns; nominal 20 ns target)
- TransientMultiApp + Transient Poisson
- `no_restore=true`
- ordinary Poisson equation; no banded electron-response correction
- Picard fixed-point iteration
- `relaxation_factor = 2/(1+100) = 0.019801980198019802`
- delta-phi convergence `1e-6 V`
- `compute_scaling_once=true`
- `fp_anchor_csv enable=false`
- compact step/final scientific outputs retained

The previous-potential anchor transfer is retained only so the same delta-phi convergence criterion can be evaluated. No `gummel_band_beta`, `n_epsilon_frozen`, or `FVGummelBandedCorrection` is present in the reference Poisson solve.

## Optimized endpoint

`optimized_endpoint_20ns` uses the same physics, horizon, convergence, output, and scaling policy, with:

- band5 electron-response correction
- outer alpha = 0.45
- Steffensen on `potential_from_poisson`

## Acceptance contract before timing

The parent/heavy-plasma input must be byte-identical across reference and optimized cases. Both must use the same 1e-6 V delta-phi accuracy gate, minimal FP output, and scaling-once policy. Timing is interpreted only after trajectory/profile parity is shown at the converged root.

Generator: `control_seq34_relax2x_reference_input.py`
