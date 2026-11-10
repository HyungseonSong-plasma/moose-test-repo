# Issue #493 — S6 new Boltzmann table native comparison runner

**Status:** isolated experimental tooling; not a completed Native simulation or
scientific validation. Existing 400 W / 0–100 µs S6 archived A runs are the
references. B and C must run fresh (460 steps / 461 timestamps).

This runner reuses the accepted pinned `physics-build-base` OCI image, compiles
only the exact reviewed PR #491 `physics_app` checkout with MOOSE Unity
**enabled** and only `physics_app/src/utils` excluded through MOOSE's
`app_non_unity_dirs` make variable; the container selects up to four concurrent
compile jobs, constrained by available memory. The resulting identical
`physics-opt` binary is applied to B and C. It does
**not** rebuild MOOSE, Crane, Squirrel or Zapdos, pull a different image, or
change production workflows. It **never** downloads or processes original
protected rate tables.

## Requirements on a trusted execution host

1. `docker`, `git`, Python >=3.10, enough volume for two independent case
   workspaces and the 100 µs solves; `numpy`, `matplotlib` are required by the
   package's post-run CSV/plot helper.
2. A clean, checked-out PR #491 candidate source at
   `bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947` with no compiled
   `physics-opt` yet. Keep candidate source fixed throughout B/C.
3. A separate checked-out historical source at
   `29d1acc6ef7969908b86719e4b95c73a1565136d`, **prepared with
   the original S6 public mesh and support files**. The mesh required by the
   package staging helper is
   `experiments/Issue395_powered_chemistry_ladder/baseline_plasma_plus_unstructured_cover_plus_wafer.msh`.
   Use the historical S6 `issue477-s6-combined-407-2069-h25-once.yml`
   preparation sequence as the reference. Do not blindly use the current-main
   `issue397_l1_power_scan_replay.sh prepare 400` because its top-level power
   guard excludes 400 W; check the *historical pinned* revision and prepare
   separately when necessary. Historical rate secrets are **not** needed for
   the staged B/C source overlays.
4. User-owned `S6_new_rates_partial_input_template_experiment_package.zip`,
   SHA-256 `bde3ab04b2cc80762e1ad25931a25f42b0f295c8695917f2e52041e0755adba6`,
   transferred to the host through a secure offline/private route. Do not
   commit/upload it to this public GitHub repository or to public Actions
   artifacts. Local data and logs are created with restrictive permissions.

## Run

```bash
python3 run_issue493.py \
  --mode preflight \
  --package-zip /secure/S6_new_rates_partial_input_template_experiment_package.zip \
  --output /restricted/issue493-preflight

python3 run_issue493.py \
  --mode run \
  --package-zip /secure/S6_new_rates_partial_input_template_experiment_package.zip \
  --candidate /trusted/pr491-exact \
  --historical /trusted/historical-s6-prepared \
  --output /restricted/issue493-attempt001 \
  --attempt attempt001
```

The second command builds one executable against the immutable base image,
then starts up to two concurrent case lanes. Within each lane, B (original
input template + new lookup) runs first, C (partial migrated input + same
lookup) second. Each arm runs actual `--check-input`, fresh full solve, checks
Exodus existence and CSV completeness (461 monotonically increasing finite
timestamps spanning 0–100 µs), then compares A/B/C diagnostic traces if both
B/C complete. Every attempt uses a new output root and unique attempt ID; no
previous workspace is overwritten. Logs, input overlays and candidate rate
rows remain local/restricted.

To run regression tests on a trusted host with the private package present:

```bash
ISSUE493_PACKAGE_ZIP=/secure/S6_new_rates_partial_input_template_experiment_package.zip \
  python3 test_run_issue493.py
```

Without that file, public CI runs only the safe source-only tests; package
integrity/staging tests are intentionally skipped. No success claim is based
on skipped package tests.

## Interpretation and remaining required analysis

- A vs B: **descriptive**, historically built binary vs new candidate binary
  may confound lookup effects.
- A' vs B: rate-only causal comparison, *only* with a separately approved
  trusted original-private-rate execution on the **same** candidate binary.
- B vs C: direct single `ne_transport` owner-migration numerical parity test.
  This is not the entire Issue #402 Plasma DSL implementation.
- Built-in P4 checks CSV diagnostic traces and produces the source package's
  six-panel CSV comparison. **It does not, by itself, quantify full Exodus
  field parity, RZ volume-weighted electron shape or complete conservation.**
  Perform those analyses on the restricted raw results with the accepted
  `default-plot`/native Exodus analysis contract; preserve 0/25/50/75/100 µs
  electron/ion/energy maps, wall fluxes, RF, charge, oxygen and energy
  closure before calling the experiment completed.
- New candidate rates occupy mean energy 0.47634–19.24235 eV. The archived
  trajectories are within the interval; new trajectories are **not guaranteed**
  to remain in it. Never silently clamp, extrapolate or expand the table.
- Source, table, binary, OCI digest, solver exit codes, 461-frame diagnostics,
  error attempts and artifact SHA-256 are required before calling P2/P3/P4 PASS.
- **`SCIENCE_HOLD` remains regardless of CI or numerical completion.**