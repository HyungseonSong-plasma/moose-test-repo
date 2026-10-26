# Ground-state O₂ three-power 100 µs experiment — run 40295762963

**Observation:** 2026-10-26 UTC. **Source:** `main@9732eadbbf67ddb933527fcfce2b62601e018f66`. **Run:** https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40295762963 (attempt 1; `completed/failure`). **Classification:** **FAIL (input/runtime setup)**, **INCOMPLETE (scientific outcomes)**. This is not a completed 100 µs simulation, a 6-hour timeout, or a numerical scientific rejection.

## Exact three-job result

| Power | Job / log | Artifact | P0 | P1 | P2 | P3 | P4 | P5 | Accepted physical time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 200 W | [121481304894](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40295762963/job/121481304894) | [12638850604](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40295762963/artifacts/12638850604) | PASS | PASS | FAIL | SKIPPED | SKIPPED | FAIL/NOT_PASS | null (0 points) |
| 600 W | [121481305124](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40295762963/job/121481305124) | [12638900027](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40295762963/artifacts/12638900027) | PASS | PASS | FAIL | SKIPPED | SKIPPED | FAIL/NOT_PASS | null (0 points) |
| 1000 W | [121481304638](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40295762963/job/121481304638) | [12638122139](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40295762963/artifacts/12638122139) | PASS | PASS | FAIL | SKIPPED | SKIPPED | FAIL/NOT_PASS | null (0 points) |

P0 generated the Graded L1 mesh, per-power overlays and 460-step target time grid; P1 built `physics-opt`. P2 `--check-input` stopped in all three jobs with **`A 'PhysicsFEMLogMolarElectronFieldLimitedFluxBC' is not a registered object.`** and MPI exit code 1. The preceding `Outputs/execute_on` override is a warning, not the terminating error. The class is requested by `enable_electron_adjacent_sheath_wall.py`; no matching registration appears in `physics_app/src/bcs/PhysicsFEMPlasmaWallBCs.C` at the source SHA. Repair/confirm exact binary registration and rerun input checking before a physics solve. P3 solve and P4 native D1 audit never ran; P5 correctly rejected absent runtime evidence.

## Scientific evidence taxonomy (all three powers)

- **Time:** requested `end_time_us=100`, 460 staged steps (preparation PASS), but **last accepted physical time = null**, `observed_time_points=0`. Do not confuse a configured end time with an achieved end time.
- **RF power:** target 200/600/1000 W only. Actual delivered/scaled RF and Maxwell absorbed power **INCOMPLETE/null**; no `P_rf_raw_W_t6`/absorption timeseries was produced.
- **PID:** original `maximum_output_value=3` remains configured; generated Receiver initial defaults are **3.3521333751042257 / 5.8060653194278604 / 7.49559809637885** for 200/600/1000 W, respectively, exceeding that configured cap. **Actual PID saturation is unobserved**, not `PASS` and not demonstrably `FAIL` from runtime. The analyzer's `original_PID_cap_reached=false` without any time points is not proof that the cap was avoided.
- **Maxwell:** preparation's only tolerance change is `nl_abs_tol: 1e-12 → 1e-11`, with `nl_rel_tol=1e-10` and `max_newton_its=20`. No solve: convergence **INCOMPLETE**; `maxwell_DIVERGED_MAX_IT=false` is an absence-of-observation flag, not convergence proof.
- **Dissociation:** static input contains `R=1.41e-15*n_e*c_O2*Te^-0.22*exp(-2.98/Te)`, where `Te=(2/3)*mean_en_solved`; source fit and generated overlay **PASS at preparation only**. Actual `diss_R_integral`, min/max and dissociation progress **INCOMPLETE**.
- **Electron-energy source:** static functor expression `-6*R` **PASS as input definition**; `diss_energy_source_integral` absent, numerical consistency **INCOMPLETE**.
- **O mass source:** static `+0.032*R` for atomic O and implicit `-0.032*R` for O₂ **PASS as input definitions**; `diss_O_mass_source_integral` absent, numerical consistency **INCOMPLETE**.
- **Heavy-mass closure:** static `S_O + S_O2` is constructed to cancel; `diss_heavy_mass_closure_integral` absent, measured closure **INCOMPLETE**.
- **Wafer D1:** preparation mesh identity `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc` and 27 wafer faces **PASS for geometry/input only**. No native output, face-current/charge or 27-face runtime audit: **INCOMPLETE**.

## Preserved evidence and integrity

All three artifact ZIPs were downloaded and inspected: each includes `check_input.log`, `diagnostics/ground_state_three_power.json`, preparation logs, mesh, source input and dissociation overlay. No `runtime.log`, solved time series, or native D1 output exists. The downloaded ZIP SHA-256 matches GitHub's artifact digest:

- 200 W: `bef24b3474f6f6d2145da4bd69ca91270e73b8d9956bc6eb7b9570b93b650f24`
- 600 W: `87423de81cc6edf3abfe4deaad9e62b55243aa38c9a22dbbea6a2ac400cd4336`
- 1000 W: `bb647a7bf244b6e2415a41a4b614c2faaa41b433588fc4c462527824d1441696`

GitHub artifact retention expires **2026-11-25**. This durable report preserves the interpretation and artifact identities, **not** the ZIP contents past expiry. Preserve/mirror ZIPs separately before expiry if long-term reproducibility is required.

## One-shot lifecycle

Run and all three jobs are terminal; all three artifacts are present and hash-verified. Remove `.github/workflows/issue395-ground-state-three-power-once.yml` via a separate exact-head, CI-validated change. Do not automatically rerun this failed scientific case or promote a configuration test to scientific acceptance. A future repaired experiment requires new exact-source identity and new independent scientific evidence.
