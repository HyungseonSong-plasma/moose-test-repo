# Boltzmann P0-2: threshold-aware finite-volume mesh — first implemented slice

**Status: DEVELOPMENT / SCIENCE HOLD** (2026-10-29). Child Draft PR #413
based on #408, tracked by issue #412. No native BOLSIG+ parity asserted.

## Algorithm (deterministic, bounded)

`PhysicsBoltzmannThresholdMesh.h` builds conservative energy-cell **faces**,
not a postprocessed EEPF. It unions three face families:
1. low-energy power-law base faces `E_i = Emax (i/N)^p`, default `p=2`;
2. an **exact face at each explicitly active inelastic threshold**, plus
   four faces on each side. The above-threshold spacing is no larger than
   `(Emax-threshold)/4` and one-quarter of the base-cell width;
3. 12 uniform subdivisions over the top 12% of the energy domain.

Coincident faces are deduplicated with priority
`endpoints > exact thresholds > threshold-neighbor > tail > base`.
Invalid thresholds, non-increasing faces, excessive cell count and
underresolved tail fail closed. The default **256-cell cap** respects the
current dense M6b eigen reference. Existing uniform and power-law paths
are unchanged; `withThresholdAwareMesh` refuses to overwrite custom faces.

**This is not a posteriori error-controlled adaptivity.** The active threshold
inventory is an explicit input; the caller must not use native BOLSIG+ Emax.
P0-1 automatic ceiling and P0-2 mesh are not yet coupled into one convergence
loop, and P0-3 positivity-preserving within-cell EEPF reconstruction is
unimplemented.

## Real C++ CI test (first-party synthetic collision data)

The native `g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic`
test `tests/boltzmann/threshold_mesh_growth_test.C` compiles and
**executes the actual** `PhysicsBoltzmannElasticSolver.C`,
`PhysicsBoltzmannGrowth.C` and `PhysicsBoltzmannTemporalGrowth.C`.
It verifies exact threshold faces, increasing geometry, low-energy
refinement, bounded tail width, invalid-input rejection, dense-cell-budget
HOLD, normalized nonnegative eigen-EEPF, temporal-growth eigen residual,
ionization/attachment gain/loss balance and excitation rate evaluation.

At `Emax=15.8367 eV`, the **geometric** C3 test has threshold
`15.8 eV` exactly on a face and **4 active cells** between 15.8 and
15.8367 eV, versus the old power-law grid's one straddling cell.
The 48-base-cell C3 geometry has **77 total cells**. This is NOT
a self-consistent native C3 rate correction: no original LXCat data
or native BOLSIG+ reference was used in the CI test.

The **independent synthetic** coupled growth/eigen test uses 40 base
cells, `Emax=4 eV`, synthetic ionization threshold 0.5 eV,
synthetic excitation threshold 0.8 eV, synthetic attachment,
and **70 refined cells**. Verified GitHub [Repository CI
40853467142](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40853467142)
native Boltzmann job **SUCCESS**:
- mean energy `0.203467 eV`;
- conservative FV normalization `1` (printed);
- maximum normalized eigen residual `1.56657e-14`;
- growth number balance relative error `3.8038e-16`.

Public immutable Physics runtime smoke **SUCCESS** on the same run.
Full `validate` job was still IN_PROGRESS when this document was
first written; do not infer whole-workflow success from the native job.

## Remaining acceptance work

- Couple adaptive ceiling + mesh in the **same** temporal-growth re-solve
  loop and define independent mesh/rate/moment convergence stopping tests.
- Validate against actual user-local BOLSIG+ 151 Example 1–4 runs with
  correct native failure codes, cross-section semantics and real EEPF.
- Implement P0-3 conservative within-cell reconstruction in the
  collision source **and** eigen operator. A threshold-aligned grid alone
  does not establish C3 rate parity.
- Scale beyond the dense 256-cell reference, quantify stability under
  mesh refinement and demonstrate energy/number conservation.

**No main merge, no production O2 ICP closure changes, no third-party
LXCat/BOLSIG+ arrays committed.**
