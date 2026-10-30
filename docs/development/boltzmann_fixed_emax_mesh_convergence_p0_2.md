# P0-2: independent fixed-Emax mesh refinement (Controller cycle 5, 2026-10-29)

## What changed

The previous P0-1/P0-2 controller selected an independent energy ceiling
while increasing its nominal cell density with Emax. That is **not** an
independent mesh-convergence study: ceiling and discretization errors are
confounded. This slice holds **Emax exactly fixed**, builds a fresh
threshold-aware nonuniform FV grid at each nominal density, solves the
actual C++ M6b temporal-growth eigenproblem, and recomputes ionization,
attachment, excitation and reverse superelastic rate moments from the
new eigen-EEPF.

- Implementation: `physics_app/include/utils/PhysicsBoltzmannMeshRefinement.h`.
- Compiled regression: `tests/boltzmann/fixed_emax_mesh_convergence_test.C`.
- CI: `.github/workflows/ci.yml`, strict C++17 compile and run.
- The distribution comparison uses an exact overlap integral for
  piecewise-constant normalized FV EEPFs on different meshes:
  `L1 = integral_0^Emax sqrt(epsilon) abs(f_old - f_new) d(epsilon)`.
  This is symmetric, is zero for the same normalized distribution
  represented on different meshes, and is bounded by 2.
- Acceptance requires **two consecutive** refinements satisfying all
  three monitored limits (mean energy, maximum process rate, EEPF L1).
  A dense >256-cell budget, base-cell cap, or refinement-count cap
  returns an explicit HOLD with all prior successful trial history.
  Each trial checks eigen residual and collision-number balance.
- This is a separate development API, **not** wired into production
  O2 ICP or the P0-1 automatic Emax selector. No source LXCat data
  or BOLSIG+ native EEPF arrays were committed.

## Actual GitHub C++ test evidence (synthetic, NOT BOLSIG+ parity)

[Repository CI run 40868737571](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40868737571),
job `Native Boltzmann EEPF development controls` **SUCCESS** at
code SHA `1246a8abaf23a4344797ba2c80adb9a073f9da8f`.
`Public immutable Physics runtime smoke` **SUCCESS**.
At initial recording the full `validate` job was still IN_PROGRESS;
do not claim whole-workflow success until independently confirmed.

Actual compiled test output at **fixed Emax = 4 eV** with first-party
synthetic 0.5 eV ionization, 0.8 eV excitation and attachment:

| Metric at third grid | Value |
| --- | ---: |
| Nominal base cells | 36 |
| Actual threshold-aware FV cells | 66 |
| Mean electron energy | 0.203599 eV |
| Relative mean-energy change from preceding mesh | **0.00454725 (0.454725%)** |
| Maximum process-rate relative change | **0.0136862 (1.36862%)** |
| Exact FV EEPF L1 change | **0.107967 (10.7967%)** |
| Normalized M6b eigen residual | 1.76178e-14 |
| Particle-number operator balance relative error | 3.24046e-16 |
| Deliberately strict 1e-14 tolerances | HOLD_MAX_REFINEMENTS PASS |
| Dense cell budget exhaustion | HOLD_DENSE_REFERENCE_CELL_LIMIT PASS |
| Manufactured identical EEPF across different grids | L1=0, PASS |
| Manufactured positive normalized shape change | Nonzero symmetric L1, PASS |

The test also deliberately sets **permissive** tolerances
(mean <= 1, rate <= 1, L1 <= 2) to exercise the successful
two-consecutive-refinement state transition. That state transition
**is not a science-accepted convergence result**. In particular the
observed 10.8% EEPF shape change is far above the default 1% L1
science-development target; the third grid must not be treated as
mesh-independent.

## Remaining scientific blockers

- Native BOLSIG+ Example 1–4 inputs and user-owned LXCat raw tables are
  not available in public CI. No native parity result was produced.
- The 15.8–15.8367 eV C3 Ar ionization window is **not** covered by
  this 4 eV synthetic fixture; original C3 +13.02% is unaltered.
- Current M6b eigensolver is dense and limited to 256 cells.
  A useful high-energy/threshold grid convergence study may need
  400–1000+ cells and sparse iterative eigen methods.
- P0-3 within-cell positivity-preserving EEPF reconstruction,
  consistently coupled to ionization/excitation source/gain,
  remains unimplemented. A low L1 does not by itself guarantee
  rate parity for a tiny near-threshold active interval.
- Example 1 400 Td ~4% mean-energy, Example 2 R5 ~10% DC mobility,
  Example 4 O2 three-body attachment units, and 151-run native
  comparison remain HOLD.

## Next

Use this independent fixed-Emax convergence gate in the adaptive
ceiling acceptance loop; require both ceiling and mesh convergence,
not just a stable ceiling. Then develop P0-3 conservative subcell
reconstruction and validate against threshold-straddling synthetic
fixtures before any real private-data C3 parity comparison.

**Science HOLD; PR #413 Draft targeting parent Draft #408 development
branch; no main merge or production O2 ICP changes.**
