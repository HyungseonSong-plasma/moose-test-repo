# Qualified PhysicsApp migration

This branch ports the previously qualified Gummel/closure composition surface onto the current `main`
without replacing the newer sheath and boundary-condition implementations already present on `main`.

## Imported architecture

- `[GummelIteration]` orchestration Action
- `DeltaPhiMultiAppConvergence`
- optional Poisson-side `FVElectronResponseBandedCorrection`
- `[PlasmaClosures]` composition Action
- unified electron closure material
- vectorized electron-impact kinetics material
- heavy-particle transport wrapper material

The underlying physics materials remain separate C++ owners. `[PlasmaClosures]` is the single
user-facing composition layer; it does not collapse unrelated physical models into one monolithic
implementation.

## Qualification provenance

The closure migration was qualified on 2026-09-25 from the historical migration line rooted at
`5ee447a88b65cd6aa784863b38b3510f470120db`.

Full migration evidence from workflow run `36163219902` reported:

- classification: `PLASMA_CLOSURES_FULL_QUALIFIED`
- evidence valid: true
- exact fixed-point history in AB and BA execution order
- cumulative fixed-point iterations: 9102 legacy / 9102 migrated
- maximum final-profile metric: 0
- maximum potential-trajectory absolute delta: 0
- geometric-mean migrated/legacy runtime ratio: 1.0093824517789294

This integration intentionally does not overwrite the current-main electron-wall/sheath source files.

## Local validation

From `physics_app/`, with the normal PhysicsApp dependencies configured:

```bash
export MOOSE_DIR=/path/to/moose
export CRANE_DIR=/path/to/crane
export SQUIRREL_DIR=/path/to/squirrel
export ZAPDOS_DIR=/path/to/zapdos
export METHOD=opt

python3 ci/check_gummel_iteration_action_contract.py
python3 ci/check_plasma_closures_contract.py
make -j2
./physics-opt --check-input -i ci/gummel_action_smoke.i
./physics-opt --check-input -i ci/plasma_closures_smoke.i
./physics-opt -i ci/plasma_closures_smoke.i
```
