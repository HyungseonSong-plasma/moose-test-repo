# Code3 PR-A — electron source projector retirement qualification

**Scope:** `PhysicsFVElectronReactionSource.C/.h` to standard MOOSE `FVCoupledForce`.
**Authority:** source-bound planning/qualification ONLY. The custom C++ and every
live production input remain unchanged in PR-A. No P3/AD numerical evidence is
claimed; `SAFE_DELETE=HOLD`.

## Three-module graph and the historical-import trap

At PR HEAD, the canonical Repository CI emits a three-report artifact:

- `structural.json` — `fdeg.structural.v0.3`;
- `functional.json` — `fdeg.functional.v0.2`;
- `transition.json` — `fdeg.transition.v0.1`.

All three contain the same exact HEAD and linked graph IDs. Structural may
return code 2 with a partial report; incomplete coverage remains an explicit
HOLD, not an omitted failure. The reports are **not** a physics run.

`experiments/historical_recipe_support/issue192_s5r.py` is a live *migration
candidate* because non-historical experiment entry modules statically import
it (for example `experiments/Issue192_s5r_representative/run.py`). Treating its
pathname as proof of historical-only use would cause Transition to silently
`PRESERVE_HISTORICAL` rather than propose rewiring. P0 now creates a
source-pinned `IMPORTS_HISTORICAL_GENERATOR_CANDIDATE` edge and uses
`HISTORICAL_MODULE_IMPORTED_BY_CURRENT_SOURCE_NOT_PROVEN_ACTIVE` on the
generator's edges. A test-only import does not promote its classification.
Neither this edge nor current-scope naming proves a script was executed.

Transition v0.1 still requires consumer activation/effective Functor proof,
approved numerical oracle, post-change graph coverage and domain approval.
A generator with `NOT_OBSERVED` activation is never a demonstrated caller-zero.

## Replacement candidate and P0 input-diff fence

The source files of the old kernel show:
- `physical: R_e=-S_e`;
- `normalized: R_e=-S_e/n_ref`, with mandatory positive `n_ref`;
- `S_e` is the already-owned signed physical electron-number Functor.

Pinned MOOSE `FVCoupledForce` is a candidate because its residual is
`-coef*v(makeElemArg(_current_elem), determineState())` in
`MOOSE=9f388366ccf38b9c34542ec5561198249fde0ac9`.
Candidate mapping: `number_source→v`, `coef=1` physical or `coef=1/n_ref`
normalized. Remove only the old object's `number_source/state_form/n_ref`
parameters. The *producer* of `S_e_s5r`, reaction progress, Avogadro factor,
species/energy kernels, materials, BCs and all other input bytes must remain
unchanged.

Use `experiments/Code3_electron_source_retirement/run.py` to prepare W5
input pairs from **one** baseline generator call. Its programmatic guard
compares every byte **outside the electron-kernel block**; it refuses a
missing, non-positive or non-finite normalization. `--prepare` stages
identical runtime assets and writes source hashes. An optional
`--physics-opt` performs paired P2 input checks; this is not P3.

```sh
python3 -m unittest discover -s tests -p test_fdeg_structural.py -v
python3 -m unittest discover -s tests -p test_code3_electron_source_retirement.py -v
python3 experiments/Code3_electron_source_retirement/run.py --self-test
python3 experiments/Code3_electron_source_retirement/run.py \
  --prepare /tmp/code3-electron-ab
# If a pinned, exact-build physics-opt binary is supplied:
python3 experiments/Code3_electron_source_retirement/run.py \
  --prepare /tmp/code3-electron-ab-p2 --physics-opt /path/to/physics-opt
```

## Required independent parity to unblock PR-B

The following remain **not evaluated**, and must have separately approved
observable/tolerance/provenance before a production cutover:

1. Distinguishing `S_e>0`, `S_e=0`, `S_e<0`; physical and normalized,
   including `n_ref != 1`, default mode, invalid/missing `n_ref`.
2. Same-mesh, same-build, same-timestep residual and full AD Jacobian,
   including coupled off-diagonal derivatives; unmodified upstream Functor
   provider and `determineState()`. A setup-only run is not parity.
3. Source ownership: EI01 consumes electrons; EI16/EI20/EDETACH/H05 produce;
   `S_e_s5r=N_A*(-rattach+rei20+rdetach+rh05)+sei16`, with exactly
   one `N_A` conversion and one residual projection.
4. EI18/EI19 negative control: **zero electron particle-number source**
   despite using standard `FVCoupledForce` for *energy* elsewhere.
5. Electron inventory, charge/source/flux closure and accepted historical W5
   runtime observables, respecting each oracle's original scope.
6. Dynamic/external input, generator and Checker/Workflow consumers: resolve
   or explicitly record supported-domain exclusions and historical replay vs
   current-binary compatibility separately.

The old C++ is removed **only in a later PR-C**, after the generator/inputs/
checkers and FDEG's own source-pinned registry are migrated in PR-B and
post-cutover coverage plus P1/P2/P3 gates are approved. A new `main` SHA,
changed provider, or failed experiment requires regenerating all three graphs
and holding retirement.
