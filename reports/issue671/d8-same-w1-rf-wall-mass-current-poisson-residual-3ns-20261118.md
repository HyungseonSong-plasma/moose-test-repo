# Issue #671 — actual original S6 RF + Wall Mass/Number + Current + Poisson Charge + assembled residual, 3 ns

**Evidence status:** `D8_RF_ON_3NS_MASS_CURRENT_CHARGE_ASSEMBLED_RESIDUAL=PASS_417_941`. This is a bounded two-case production-physics diagnostic, **not** 100 µs scientific parity or exact latest PR #665 acceptance.

## Immutable execution evidence

- One-shot diagnostic commit `0f36b6e24c0a592d9430b0eea3e08c2e2d84348f` on isolated `issue-671-d8-rf-closure-3ns-20261118`, based on PR #665 **production source** `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`; original production source/11 layer inputs unchanged.
- [Successful run #44346835225](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44346835225), [Artifact #14445594805](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44346835225/artifacts/14445594805).
- Downloaded Artifact ZIP SHA-256 `a1f37b29ffb6095b329631cead8f8ae5b30f97c95d1697345f9dc58ec2728c73`; ZIP CRC PASS.
- Actual downloaded executable `physics-opt` SHA-256 `1bdc85c65f5847ae58d51c76f89f8e67c67291dc9b5ee842bcbab98c4a71befa` matches the actual byte payload in immutable W1 [build Artifact #14435245012](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44319316180/artifacts/14435245012). Independently rechecked original W1 TAR, `libphysics-opt.so.0` SHA `b107698dfc7539237cd194331e306efd28f3fba7bc7e0b958f4f8dd2165f67bd` and `libphysics_test-opt.so.0` SHA `bd1e0626a5e6682ffdda66fa6e1589f3f0d975a66aa9f79b964efeb1d84924a6`.
- S6-417/941 **both** native `--check-input` exit 0 / 3 × 1 ns RF solver exit 0, original Maxwell child & seven Transfers preserved, original 11-layer SHA unchanged, protected five original EI rate files/case in private tmpfs and removed, no raw private rates uploaded.
- 34 runtime postprocessors per case; all finite. Observed exact arithmetic closure: **9/9 number→mass comparisons, 3/3 signed surface current comparisons, 2/2 Poisson charge/source coefficient identities and 4/4 assembled variable residual norms** per case. Independent receipt-level ZIP/numeric audit returned PASS for both cases.

## Direct Mass Flux boundary integrals

These values are **direct Native `ADSideIntegralFunctorPostprocessor` results**, not the independently calculated values. Number-to-mass prediction uses species molar mass / Avogadro number, with O2p `0.032 kg/mol`, Om and Op `0.016 kg/mol`.

| Boundary | Species | 417 mass integral | 941 mass integral |
|---|---|---:|---:|
| cover | O2p | 6.2409765329319e-08 | 6.2409830961647e-08 |
| cover | Om | 7.2789153794929e-13 | 7.2789153141553e-13 |
| cover | Op | 3.1415628334661e-11 | 3.1410485427475e-11 |
| wafer | O2p | 2.3122259971624e-08 | 2.3122261051180e-08 |
| wafer | Om | 2.4179876779782e-13 | 2.4179876782556e-13 |
| wafer | Op | 1.1629264563648e-11 | 1.1629234326977e-11 |
| focus ring | O2p | 2.2404845542800e-10 | 2.2404848938567e-10 |
| focus ring | Om | 8.5593671641708e-15 | 8.5593671686688e-15 |
| focus ring | Op | 1.1444854302067e-13 | 1.1444799715262e-13 |

For all 18 case/species/boundary values, `direct mass integral ≈ directly observed number integral × M/N_A`. Largest observed absolute mass discrepancy is `2.45e-21` in integral output units.

## Signed conventional current, independent 4-species reconstruction

`I = e*(Gamma_O2p + Gamma_Op - Gamma_Om - Gamma_e)` with every species number flux measured directly at its own physical boundary.

| Boundary | 417 current (A) | 941 current (A) | 417 abs error (A) | 941 abs error (A) |
|---|---:|---:|---:|---:|
| Cover | -3.6011286276022 | -3.6011294112670 | 9.86e-14 | 3.20e-14 |
| Wafer | -0.85181504110183 | -0.85181503581399 | 5.55e-15 | 4.33e-15 |
| Focus ring | -0.057864287198826 | -0.057864285539620 | 2.57e-16 | 9.71e-17 |

All 6 surface-current identities PASS at relative tolerance `1e-8` / absolute `1e-12 A`.

## Poisson signed charge integration / RHS identity

| Direct volume integral | 417 | 941 |
|---|---:|---:|
| `charge_number_density` | +377145460092.23 | +377145475072.74 |
| `charge_density_C_m3` | +6.0425364377895e-08 | +6.0425366778037e-08 |
| `poisson_source` | +6824.4954427714 | +6824.4957138455 |

Numerically checked `rho = 1.602176634e-19 * n_charge`; `poisson_source = 1.8095128179727827e-08 * n_charge`. Both identities PASS for 417 and 941. These values are volume integrals in the effective MOOSE/RZ integration measure; do not equate them with a pointwise value or assume a separate Gauss-law boundary flux identity.

## Assembled equation residual L2 norms — same original RF solve

The built-in MOOSE `DiscreteVariableResidualNorm` was evaluated for each lower-D sigma variable and Poisson `potential` at TIMESTEP_END in **the same RF-ON 3 ns job**:

| Variable / block | 417 residual L2 | 941 residual L2 |
|---|---:|---:|
| `sigma_s` / `cover_surface` | 9.1846843204073e-16 | 8.7363940423421e-16 |
| `sigma_wafer` / `wafer_surface` | 3.5271378638386e-16 | 4.0706863356423e-16 |
| `sigma_focus_ring` / `focus_ring_surface` | 2.6969266635746e-16 | 9.2090178756206e-17 |
| `potential` / `plasma` | 5.4486428053723e-11 | 5.3612688903395e-11 |

All 8 finite/nonnegative checks PASS. **These are assembled variable equation residual norms**, not direct function-entry tracing or separately isolated `PhysicsLowerDSurfaceCurrent::computeQpResidual()` and `FunctorKernel::computeQpResidual()` contributions. No stronger kernel-specific evidence is claimed.

## Scope and remaining HOLD

- **New 3 ns full RF run:** 417/941 PASS, Maxwell power transfer & seven real Transfers preserved. The safe overlay adds only observers and Debug residual norms.
- **Raw-data limit:** Public sanitized Artifact contains compiled ELF, numeric receipt files, log excerpts and SHA records; it deliberately excludes full raw solver CSV, full logs and private EI rates. Independent ZIP, ELF and **reported-value** arithmetic verified; no claim of independent off-job raw-CSV re-extraction.
- **Physics interpretation:** residual norms near zero establish bounded algebraic convergence, not independent physical Gauss-law balance or long-time scientific equivalence.
- **Exact-current HEAD:** PR #665 current `52067302d16074592503d0ef6b903cc344f55a08` is not the W1's `74a2b0f…` build HEAD. `P5_X_FINAL_NATIVE=HOLD_EXACT_CURRENT_HEAD`; source-blob compatibility does not promote to exact-HEAD PASS.
- **Scientific:** `S6_100US=NOT_RUN`, `SCIENCE_HOLD`, no original input/main/PR #665 source changes, no merge or long-running workflows.
