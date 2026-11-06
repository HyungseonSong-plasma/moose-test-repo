# P0-1/P0-2: independent joint energy-ceiling and FV-mesh gate (2026-10-29)

**Status: IMPLEMENTED DEVELOPMENT GATE; SCIENCE HOLD.**
This code is not native BOLSIG+ parity, not P0-3, and not a production
MOOSE/Physics closure. All CI cross sections are first-party synthetic.

## Why this gate exists

Earlier P0-1 automatic ceiling selection re-solved the temporal-growth
eigenproblem on one threshold-aware FV mesh per Emax. Independently, P0-2
fixed-Emax refinement measured **EEPF L1 = 0.107967** (10.7967%)
despite a small eigen residual. A stable ceiling on a coarse grid does
not establish grid convergence. An outer Emax selector must not accept
an EEPF whose *inner* fixed-ceiling grid study is unresolved.

## New algorithm

`PhysicsBoltzmannJointConvergence.h` wraps the existing
`selectEnergyCeiling` controller with a real
`solveTemporalGrowthWithMeshRefinement` call at **each** proposed Emax:

1. Validate collision cross-section coverage through the configured
   maximum Emax and require represented thresholds active from the first
   solve. Never silently activate a dormant channel.
2. Scale the initial nominal FV base-cell count with Emax, then build
   fresh threshold-aligned meshes at fixed Emax and repeatedly solve
   the actual C++ M6b temporal-growth eigenproblem. Recompute all
   ionization, attachment, excitation and reverse process rates.
3. Compare normalized conservative cross-mesh EEPF L1, mean energy and
   all monitored process rates, requiring consecutive mesh stability.
4. Only a **mesh-converged** sample enters the outer Emax tail/moment/rate
   controller. A failed inner refinement or dense-cell limit raises an
   expected, explicit `HOLD_JOINT_MESH_*` without fabricating Emax
   convergence. Keep the failed mesh trial history and all earlier
   accepted Emax samples.
5. Only after multiple stable Emax trials on individually mesh-converged
   solutions return `CONVERGED_JOINT_EMAX_MESH_SCIENCE_HOLD`.

The final mesh-refined rate inventory is now retained in
`MeshRefinementResult::rates_m3_per_s`, avoiding any comparison of stale
coarse-grid rates. This is still a *numerical state machine*, not a
physically validated tolerance policy. The dense M6b reference is
limited to 256 FV cells.

## Actual C++ CI evidence

Source code/test SHA: `bf87082cca5bd204d2e6aabd864d4afbaa3272a8`.

[Repository CI run #40877354277](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40877354277):
`Native Boltzmann EEPF development controls` **SUCCESS**;
`Public immutable Physics runtime smoke` **SUCCESS**.
The full `validate` job was still in progress when this document
was drafted; do not claim whole-workflow success without checking it.

New compiled C++ step (g++ C++17, -O2 -Wall -Wextra -Werror -pedantic):
`tests/boltzmann/joint_emax_mesh_convergence_test.C`.
Its actual first-party synthetic M6b output:

| Metric | Result |
| --- | ---: |
| Joint-gate Emax | 4.5 eV |
| Final threshold-aware FV cells | 64 |
| Mean energy | 0.203725 eV |
| Max process-rate relative change between accepted Emax trials | 0.0104447 (1.04447%) |
| Final fixed-Emax mesh EEPF L1 | 0.111225 (11.1225%) |
| Final M6b normalized eigen residual | 4.82255e-15 |
| Strict inner mesh convergence test | HOLD = PASS |
| Dense FV budget exhaustion test | HOLD = PASS |
| Truncated cross-section / dormant threshold / invalid channel controls | Rejected = PASS |

**CRITICAL:** The synthetic "converged" path deliberately uses
permissive mesh tolerances (`distribution_l1_limit=2`,
`mean_relative_limit=1`, `rate_relative_limit=1`) and similarly
permissive outer moment/rate tolerances to exercise state transitions.
The **11.12%** EEPF shape change would FAIL scientifically meaningful
L1 tolerances (e.g., 1%). The test also confirms strict tolerances
return HOLD rather than PASS. Do not interpret this as mesh-converged
physics or improvement over native BOLSIG+.

The earlier fixed-Emax regression remains independently compiled and
passes in the same CI job; no legacy uniform/power-law solver was
modified. Original Draft PR #408, `main`, and production O2 ICP
remain unchanged. The child Draft PR #413 targets the parent
development branch after a temporary main-base CI trigger; no merge.

## Remaining science and implementation blockers

- Real Example 1–4 151-run parity requires the user's genuine BOLSIG+
  output and original LXCat collision semantics. No private
  cross-section tables or native EEPF arrays are committed.
- Current dense solver 256-cell limit prevents strict L1 mesh
  convergence at many conditions. Sparse eigensolver remains P1.
- P0-3 positivity-preserving, particle/energy-consistent *within-cell*
  EEPF reconstruction coupled to collision gain/loss is not implemented.
- C3 Ar ionization +13.02% near 15.8–15.8367 eV, Example1
  400 Td mean-energy ~4%, Example2 R5 DC mobility ~10% and O2
  three-body attachment density semantics are unresolved.
- Required: independently justify scientific tolerance values, add
  P0-3 and scalable sparse eigensolving, then re-run genuine native
  reference comparisons and transport/rate/energy budgets.

**Decision:** P0-1/P0-2 checkboxes remain OPEN; science HOLD.
