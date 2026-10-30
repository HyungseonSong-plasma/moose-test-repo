# Boltzmann P0-1/P0-2: coupled automatic Emax and threshold-aware M6b (2026-10-29)

## Scope and provenance

This is **first-party synthetic C++ development evidence**, not native BOLSIG+
or LXCat process parity. Parent Draft PR #408 remains unchanged. Child Draft
PR #413 targets the #408 development branch, not main; production O2 ICP is
not modified. The real user-owned collision data and native EEPF arrays are
not included in this repository.

This development slice adds:
- `PhysicsBoltzmannAdaptiveGrowth.h`: independently rebuilds the
  threshold-aware nonuniform FV mesh at **each** proposed Emax, reassembles
  the coupled M6b temporal-growth eigenproblem, and recomputes ionization,
  attachment, excitation and superelastic rates on the **new** eigen-EEPF.
- `PhysicsBoltzmannEnergyCeiling.h`: explicit `EnergyCeilingHold` return
  path preserves prior successful convergence history and never converts
  expected dense-resource exhaustion into a false PASS.
- `tests/boltzmann/adaptive_growth_ceiling_test.C`: compiled C++ regression
  covering each trial's exact mesh geometry, independent final eigen re-solve,
  positive normalized FV EEPF, growth source/gain conservation, all process
  rates, stable tail/moment/rate gates, cross-section coverage, dormant
  thresholds, and first/later resource HOLD.
- CI builds with `g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic`.
  Test command and linked source files are in `.github/workflows/ci.yml`.

## Algorithm and safety invariants

The controller starts with user-supplied initial Emax and nominal base-cell
width; it never reads native BOLSIG+ Emax. Each trial at `Emax` uses
`ceil(initial_cells * Emax / initial_Emax)` power-law base cells, adds
exact faces at all initially active ionization/excitation thresholds and
local threshold-side cells, then refines the upper 12% of energy space.
All tables must cover the requested maximum Emax. Inactive thresholds
are explicitly rejected; channels cannot silently turn on during the sweep.
The full M6b collision operator and EEPF are recomputed for each trial.

The same FV integration as P0-1 checks total mass=1, mean-energy consistency,
tail number/energy fractions, maximum per-process rate change, and
consecutive stable trials. Mesh budget is limited to 256 cells because
the current M6b reference eigen solver is dense. If any proposed mesh
exceeds this limit, status is `HOLD_DENSE_REFERENCE_CELL_LIMIT`;
previous successful trial history and distribution are preserved,
`converged=false`. Unexpected numerical/geometry errors still throw.

## Actual GitHub CI-built C++ evidence

[Repository CI 40861917232](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40861917232)
at code SHA `206a4a2f501566f86a84cb2823a4763acbe2a702`
(`Native Boltzmann EEPF development controls` job):

| Test | Observed |
| --- | ---: |
| Synthetic independently selected Emax | 4.5 eV |
| Threshold-aware FV cells at final Emax | 82 |
| Final mean energy | 0.203177 eV |
| Independent final eigen normalized residual | 2.59779e-15 |
| Exact FV EEPF number normalization | 1 |
| Growth operator number balance relative error | 2.98367e-16 |
| Maximum rate relative change at final Emax | 0.00230531 |
| Resource limit during a later trial | HOLD with history, PASS |
| Resource limit before first trial | HOLD, PASS |
| Original P0-1 elastic/growth tests | PASS |
| Original P0-2 nonuniform mesh/growth test | PASS |
| BOLSIG+ native Example 1–4 parity | **NOT TESTED** |

The native C++ job is **SUCCESS** after one earlier test-only failure:
the initial resource-HOLD fixture allowed convergence before exhausting
100 cells. Tightening its **test** budget to 75 cells correctly exercises
the intended fail-closed path. No physical solver parameter was fitted
to BOLSIG+ to make the regression pass. Other CI jobs must be checked
independently before claiming whole-workflow green.

## Scientific HOLD / remaining work

This result proves actual coupling of the two previously separate
development components, **not** P0-1/P0-2 acceptance. Still required:
independent mesh-density refinement at fixed Emax, independent
tail/threshold/cross-section domain convergence, scalable 400–1000+
sparse eigensolver, and native Example 1–4 per-process EEPF/rate parity.
P0-3 positivity-preserving within-cell reconstruction must be coupled
consistently to the FV collision gain/loss operator; this slice still
uses cell-constant EEPF.

Example 4 C3 Ar ionization +13.02% native comparison is **not**
remeasured or claimed improved by this synthetic test. Its narrow
[15.8,15.8367] eV active interval remains the designated high-threshold
acceptance case. Example 1 400 Td mean-energy ~4% discrepancy, Example 2
R5 mobility ~10%, O2 three-body attachment density/unit semantics,
and native-informed prior Emax benchmark limitations remain OPEN.
Science HOLD, PRs Draft, no main merge or production closure switch.
