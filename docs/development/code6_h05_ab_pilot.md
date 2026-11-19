# code6 PR B — H05 conditional old/conservative A/B pilot

**Tracking:** #704. **Harness defect:** #696 code6 audit. **State:** Independent exact-HEAD P0 input preparation; Native requires a separately supplied executable and is not CI-triggered automatically.

## Model under test

The existing H05 runtime fixture `physics_app/ci/check_stage5_h05_runtime.py` declares exactly two mass-fraction time kernels: `w_O_time` and `w_Om_time`, both with `rho = rho_const`. This pilot imports the pinned H05 fixture and generates two byte-comparable inputs; the only changes are the **two type lines**:

- **Incumbent:** `PhysicsFVMassFractionTimeDerivative`, `R=rho*_u_dot`.
- **Conditional candidate:** `PhysicsFVConservativeMassFractionTimeDerivative`, `R=(rho_n*w_n-rho_old*w_old)/dt`.

**Important:** these formulas are not generally equivalent. Under an independently pinned common Backward Euler discretization, candidate minus incumbent is `(rho_n-rho_old)*w_old/dt`. Thus a changing density with nonzero old mass fraction is a known non-equivalence counterexample. An observed numeric `rho_const` in the Python template does **not** itself prove a constant effective Functor at Native runtime.

## P0 — exact-HEAD preparation (automated CI)

```bash
set -euo pipefail
head="$(git rev-parse HEAD)"
python3 physics_app/ci/code6_ab_pilot.py --self-test
python3 physics_app/ci/code6_ab_pilot.py \
  --mode prepare --expected-head "$head" \
  --output-dir code6-h05-pilot
```

Outputs:

- `incumbent/stage5_h05_runtime.i`
- `candidate/stage5_h05_runtime.i`
- `code6-h05-ab-receipt.json`

The receipt preserves exact checkout SHA, pinned H05 source/blob, input SHA256 values, target type and block identity, source-declared constant density, and explicitly `native_status=NOT_RUN`, `time_integrator=NOT_SOURCE_PINNED`, `safe_delete=HOLD`.

The P0 self-test checks zero-vs-variable density algebra, zero timestep negative, both H05 block names and the invariant that **no input line other than the two class types changes**. CI uploads the prepared input pair and P0 receipt; this is *not* Native parity.

## Controlled Native exploration (manual gated execution only)

After the pinned immutable Physics executable and its build-base identity are available:

```bash
head="$(git rev-parse HEAD)"
python3 physics_app/ci/code6_ab_pilot.py \
  --mode native --expected-head "$head" \
  --output-dir /tmp/code6-h05-native \
  --executable /absolute/path/to/physics-opt \
  --build-base-ref 'ghcr.io/...@sha256:...'
```

Each case executes `--check-input`, then `-i`, against the **same** executable, writes separate logs and captures the full `stage5_h05_runtime_out.csv`. The existing H05 bounded reaction checker runs for both cases; the pilot records raw CSV hashes and differences in `w_O_avg`, `w_Om_avg`, `w_O2_avg` and time. Nontrivial species evolution is mandatory. Numerical observations are exploratory; no unspecified tolerance is accepted as scientific parity.

## Release/retirement gates still missing

1. **Effective MOOSE time semantics:** source-anchored `FVTimeKernel::_u_dot` / `determineState`, actual Executioner scheme and old/current state, solver/binary/physics SHA. Original H05 input does not explicitly set an integrator.
2. **Real input and Functor binding:** effective `rho_const` and generated `.i` source provenance, not merely name match.
3. **Independent AD Jacobian parity:** scalar CSV equality is insufficient. Execute residual and Jacobian comparison under both constant density and a **Native variable-density negative** with a reviewer-approved oracle/tolerance.
4. **Mass conservation/chemistry:** reaction, flux and species/mixture mass balance. Historical H05 validation is one limited oracle, not whole-program equivalence.
5. **Harness completeness:** #696 confirms Structural `instances=0` versus 15 declarations and 0 provider bindings; the code6 Transition consumer DAG currently undercounts editable Kernel blocks. Keep that failure separate from this two-kernel experimental fixture.
6. **Approval:** dynamic/external consumer coverage, historical replay and source-retirement review (PR C/D).

**No C++ or H05 source modifications; no automatic Native workflow launch; no merge or deletion. `SAFE_DELETE=HOLD` regardless of P0 result.**