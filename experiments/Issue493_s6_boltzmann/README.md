# Issue #493 — S6 new Boltzmann table native comparison runner

**Status:** isolated experimental tooling; not a completed Native simulation or
scientific validation. Existing 400 W / 0–100 µs S6 archived A runs are the
references. B and C must run fresh (460 steps / 461 timestamps).

This runner reuses the accepted pinned `physics-build-base` OCI image and
**delegates P1 compilation to the reusable**
`physics_harness/execution/native_build.py` harness. Its default auto profile
keeps MOOSE Unity enabled, excludes only `physics_app/src/utils` initially,
and permits bounded application-only Unity-collision repair when a new source
directory conflicts. It never enables global non-Unity or rebuilds the
MOOSE/Crane/Squirrel/Zapdos vendor cache; parallelism respects CPU, memory
and cgroup limits. The exact reviewed PR #491 `physics-opt` executable is
shared by B and C. The runner does not pull a different base image, change
production workflows, download original protected tables or grant scientific
acceptance. See `docs/guides/native_p1_build_harness.md` for build profiles,
failure classifications and provenance.

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

## GitHub Actions P2/P3/P4 example (inactive — workflow surface guard)

The repository's `ci/guards/workflow_surface_guard.py` deliberately restricts
which workflow entrypoints may be installed under `.github/workflows/`. The
Issue #493 research-only secret-intake workflow is therefore retained as a
**non-executing example** at
`experiments/Issue493_s6_boltzmann/issue493-s6-native-private-compare.example.yml`.
It is **not** an installed GitHub Actions workflow, so no P2/P3/P4 work
automatically starts after integration into `main`.

The independently generated **19 public Boltzmann rates** now live under
`physics_app/data/electron_impact/boltz/` as 100-row MOOSE molar lookup tables.
The original private/archived rates and original MCS source are not published.
The offline comparison runner still needs isolated prepared S6 B/C input layers
and local trusted execution; merely publishing the rates does not cause a
native solve or prove parity. Converting this private-input example into a
public-data workflow must be reviewed as a separate change through existing
canonical `experiment.yml` governance, without weakening the workflow
surface guard.

The original guarded example checks for a dedicated
`ISSUE493_S6_NATIVE_INPUT_B64` secret, but **that secret has not been
installed** in this chat; earlier jobs displayed success because their
experimental computation steps were skipped. Continue `SCIENCE_HOLD` until
P2 native input checks, P3 460-step fresh B/C solutions, and P4 diagnostic/
Exodus closure comparisons are actually complete.


## Public electron-density reference comparison (research diagnostics)

Reference profiles are now **public, versioned data**, not GitHub Secrets.
The two canonical 400 W CSVs are:

- `reference/reference_vertical.csv`: `z_cm,n_e_m^-3` at r = 0 cm;
  45 points, z = 0–44 cm.
- `reference/reference_horizontal.csv`: `r_cm,n_e_m^-3` at z = 23 cm;
  51 points, r = 0–25 cm.

The reference source and unverified coordinate/time assumptions are disclosed
in `reference/README.md`. Max reference density is 8.885e16 m^-3.
Do not describe the reference timestamp as Native t=100 us; its timestamp
is unknown. These CSV files are the frozen version-controlled input for the
comparison, so updates are reviewed in Git rather than silently swapping a
secret. Neither original private rates nor production acceptance data are used.

After a P3 PASS and verified Exodus/CSV archival, the Issue493 B/C one-shot
workflow runs `compare_native_reference.py` using the CSVs checked out
from the **same workflow commit**. Each case/arm artifact contains:

- `reference_comparison/vertical_absolute.png` (r = 0 cm);
- `reference_comparison/horizontal_absolute.png` (z = 23 cm);
- `reference_comparison/vertical_profile.csv`,
  `horizontal_profile.csv` and `metrics.json`.

There are exactly **two absolute-density plots**; normalized plots are
deliberately omitted. The metrics record full reference CSV SHA-256 digests,
Native Exodus/CSV SHA-256 digests, common-support counts, and RMSE.
Node density is `N_A * exp(log_ne)`; interpolation uses only plasma
triangles, with no external extrapolation, at Native 100 us.
The reference curves are publicly reproducible from the committed CSVs.

If comparison fails, `reference_comparison_status.json` records HOLD and
preserves the previously verified Native Exodus, CSV and manifest.
A successful diagnostic does **not** clear `SCIENCE_HOLD` or prove B/C parity.
No GitHub Secret is required or read.

Synthetic tests run before the expensive solve:

```bash
python3 experiments/Issue493_s6_boltzmann/test_compare_native_reference.py
```

Offline regression against preserved Issue493 417/B and 941/B artifacts
exercises the same 100 us comparator without re-running the solver.
The one-shot workflow is self-path-triggered on main. Merging the PR
that changes it will launch full 460-step B/C jobs; preserve its existing
authorization, provenance and P2/P3 gates.

## C/P2 launcher failure analysis (2026-11-11)

Both historical C lanes ended P2 with exit 127, a sanitized
`P2_LAUNCHER_FAIL` classification and P3 NOT_RUN, despite a verified exact
B-built executable SHA and OCI image. The B executable's ELF dynamic section
lists `libphysics_test-opt.so.0` and has an RPATH/RUNPATH containing
`/app/physics_app/test/lib`. The published B-to-C handoff tarball previously
included only `physics_app/lib`; it excluded `physics_app/test/lib`.
This missing shared-library directory is the strongest evidenced explanation
for exit 127. The raw C P2 stderr was not retained, so loader text is not
independently confirmed.

The corrected handoff archives **both** `lib` and `test/lib` with
SHA-verification, checks for `libphysics_test-opt.so.0` after restoration,
and performs pinned-OCI `ldd` library closure check **before** C P2.
If the closure check fails, C must remain blocked rather than starting P3.
The original two B results are already complete; their old 14-day executable
archives lack `test/lib`, and a new P1 closure bundle must be built or
otherwise independently verified before any C-only retry. No new Native solve
is authorized by this analysis.
