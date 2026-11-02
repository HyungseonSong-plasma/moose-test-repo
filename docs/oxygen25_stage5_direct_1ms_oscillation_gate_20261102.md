# Oxygen25 Stage5 DIRECT 1 ms: scientific oscillation gate (2026-11-02)

**Decision: HOLD — do not launch 1–10 ms Stage6 with dtmax=100 µs.**

## Verified provenance

- Direct Stage5 GitHub Actions run [41358545575](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41358545575): `completed/success`, workflow SHA `3d9fb0746f67422ed6d69ff9bd1676fd75f3e770`.
- Both 400 W and 1000 W: native P0/P1/P2/P3/P4, private-rate SHA verification, and final artifact upload all `success`.
- Native 1 ms artifact IDs: 400 W `13107661302`, 1000 W `13109110076`.
- Each ZIP contains `run/plasma.csv`, `restart_run_1000000ns.tar.gz`, `restart_inputs_1000000ns.tar.gz`, and `restart_1000000ns_manifest.json`.
- Both ZIPs' two restart archives have been SHA256-hashed locally and match their manifest byte counts and digests. Each manifest reports `final_time_s=0.001`, `recovered_time_ns=1000000`, source SHA `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`, EI936 25-effective-O(ex), native advanced restart.
- Native CSVs: 619 rows each, strictly increasing finite time 0–1 ms, no negative/nonfinite values in the four selected neutral densities.

## Quantitative neutral oscillation screen (direct Stage5)

Window: 100–1000 µs and late 500–1000 µs. 400 W: all four neutrals monotone (O2(X) decreases, other three increase), zero sign reversals.

1000 W: O2(X) decreases monotonically; O(3P) and O(1D) increase monotonically. **O2(a1Delta) exhibits two separate late-time local maxima and declines:**

| Peak (µs) | Trough (µs) | Relative drop |
| ---: | ---: | ---: |
| 866.777215 | 876.777215 | 0.060406% |
| 946.777215 | 966.777215 | **0.117077%** |

The late O2(a1Delta) trace has 47 positive steps, 3 negative steps, and 4 derivative sign reversals. The two peaks are separated by 80 µs. This exceeds the exploratory 0.1% local-drop gate threshold. It is small compared with the growing neutral baseline, but is not floating-point roundoff.

## Stronger RF power oscillation evidence

At 500–1000 µs:

| Condition | P_rf_raw min (W) | max (W) | mean (W) | peak-to-peak / nominal |
| --- | ---: | ---: | ---: | ---: |
| 400 W | 400.188881 | 400.557179 | 400.301713 | 0.0921% |
| **1000 W** | **281.382434** | **2034.639374** | 986.852335 | **175.326%** |

At 1000 W, RF power oscillations have roughly 70–80 µs spacing. In the direct 500–1000 µs window, the RF drive scale reaches its apparent upper bound of 3.0 at 10 of 51 CSV samples (versus zero samples for 400 W), and ranges from 2.007683 to 3.0. The prior 1000 W restart chain also hits 3.0 at 5 of 73 late samples. The native checkpoint input `rf_elastic_multiapp_parent_1000w_100us_dt1000ns_overlay.i` contains `PIDTransientControl` with `postprocessor=P_rf_raw_W_t6`, `target=1000`, `K_proportional=-0.0005`, `K_integral=0`, `K_derivative=0`, `minimum_output_value=0.1`, `maximum_output_value=3`, and `execute_on=TIMESTEP_END`. The 400 W input uses the same proportional gain and bounds with target 400 W. **Proportional feedback saturation and lag in the Maxwell/plasma coupled response are a concrete, testable limit-cycle hypothesis, not yet an established root cause.** This is a material solver/coupling oscillation, not a minor neutral-density numerical roundoff. Proposed `dtmax=100 µs` would be larger than the observed oscillation period and is therefore not justified without investigating the underlying dynamics and timestep sensitivity.

## Comparison with prior 500 µs restart chain

Reference Stage6 run [41347038089](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41347038089), 400 W diagnostic artifact `13101525492`, 1000 W diagnostic artifact `13102228620`.

At 1 ms, direct minus reference relative differences (percent):

| Neutral | 400 W | 1000 W |
| --- | ---: | ---: |
| O2(X) | -0.000032 | +0.0233 |
| O2(a1Delta) | +0.000732 | -0.5534 |
| O(3P) | +0.000549 | -0.7537 |
| O(1D) | +0.0080 | -0.5531 |

The prior 1000 W chain also exhibits large RF oscillations and late O2(a1Delta) negative steps, but their phase differs from the direct run. Thus, the phenomenon is not uniquely attributable to a Stage5 DIRECT restart error. Root cause (power-control feedback, plasma coupling, timestep, or other) is **not established**.

## Gate and follow-up

**HOLD** the proposed Stage6 1–10 ms with `IterationAdaptiveDT dtmax=100 µs`. The Stage5 native checkpoint and scientific source remain intact. Next: diagnose the 1000 W RF power-control / Maxwell coupling oscillation, verify whether 10 µs dtmax resolves it, compare shorter dtmax and convergence behavior, and only then reconsider a safe 10 ms continuation. Do not claim steady state or timestep convergence.

This report documents numerical evidence; threshold values are conservative screening heuristics, not proven physical acceptance criteria. No chemistry, EEDF, source, or power-target changes were made.

## Controlled timestep-sensitivity experiment — 2026-11-02 02:42 UTC

- New **isolated** branch: [experiment/oxygen25-1000w-dt5us-sensitivity-20261102](https://github.com/HyungseonSong-plasma/moose-test-repo/tree/experiment/oxygen25-1000w-dt5us-sensitivity-20261102).
- New native GitHub Actions diagnostic: [Run 41379107857](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41379107857), commit `29967a94d857260c950d7bf628c3fad737640bb0` (submitted, completion pending).
- Control: 1000 W direct Stage5 Run `41358545575`, `IterationAdaptiveDT dtmax=10 µs`, from Stage4 native checkpoint Run `41310708653` at 100 µs.
- Trial: same 1000 W, same native Stage4 checkpoint, same immutable physics source `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`, same private-rate SHA256 and EI936 network, same PID `Kp=-0.0005`, target 1000 W, output bounds 0.1–3.0; **only `dtmax` changes from 10 µs to 5 µs**. The requested audit spacing becomes 5 µs × 180 intervals for 100–1000 µs, not an enforced fixed-step schedule.
- Provenance gates: original Stage4 P0–P4 job identity and artifacts, original native archive SHA256, parent and child checkpoint restart, unchanged science SHA and rate hashes, P1–P4 native continuation, separate artifact namespace. A second immutable control artifact is downloaded for paired RF/neutral comparison.
- After successful P4, script `.github/scripts/oxygen25_stage5_dt5us_compare.py` writes `stage5_dt5us_vs_dt10us_1000w.json` and aligned CSV. It compares late (500–1000 µs) RF peak-to-peak and RMS target error, PID upper-clamp hit rate, four-neutral extrema and derivative sign reversals, plus endpoint relative differences. Negative/nonfinite density and invalid time order cause fail-closed diagnostics.
- **Scientific gate remains HOLD** independently of whether this sensitivity run succeeds. A 5 µs refinement is a diagnostic, not proof of timestep convergence or validation of the proposed Stage6 `dtmax=100 µs`. If RF oscillation persists, prioritize controller saturation/lag, source/response phase and physical attainability of the 1000 W target. Any PID-gain changes require a separately justified scientific design experiment.

## 2026-11-02 03:38 UTC: dtmax=5µs native progress and RF diagnostics

- Live native diagnostic run [41379107857](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41379107857) is **in progress**. Stage4 gate, P0 native restore, P1 rebuild, P2 input checks passed; P3 remains running, P4 and result upload pending.
- Native P3 job `125065801658` log at 03:23:34 UTC reports `Time Step 46, time = 0.000223389, dt = 5e-06` (223.389µs, 5µs step). This is only **early-time progress**, not evidence about late 500–1000µs behavior. No error/NaN text was found in the fetched partial log.
- The latest RF diagnostic table in that log covers 153.389–218.389µs and shows raw power near 1kW (e.g., 999.231W at 153.389µs, 1007.810W at 213.389µs). This early-time observation does **not** resolve the 1000W late-time oscillation.
- Added standalone evidence script [`.github/scripts/oxygen25_pid_limitcycle_diagnostic.py`](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/analysis/oxygen25-stage5-1ms-oscillation-gate-20261102/.github/scripts/oxygen25_pid_limitcycle_diagnostic.py), commit `9b5381d7d9957750b9a929552e2053be27f4b489`. The script is designed for the **verified native plasma.csv**, checks monotone finite time and 1ms endpoint, computes 500–1000µs RF peak-to-peak and RMS error, time- and sample-weighted upper-clamp occupancy, prominence-filtered peak periods, and unsaturated error-to-drive-increment correlations at several sample lags. It has a synthetic self-test. Its outputs are diagnostics, **not causal identification** of PID/Maxwell instability.
- After the 5µs run completes and native artifacts are verified, apply the same script to both 10µs and 5µs 1000W CSV histories. Correlation lag is in **sample indices**, so compare it with the measured adaptive time steps rather than treating it as a fixed physical lag. Use the already-integrated `oxygen25_stage5_dt5us_compare.py` for the main paired metrics.

**Decision unchanged: HOLD Stage6 1–10ms, dtmax=100µs.** Do not change PID gain, chemistry, or the accepted Stage5 checkpoints.

## 2026-11-02 04:40 UTC: matched early-window RF timestep evidence

- Live native 1000W dtmax=5µs sensitivity [Run 41379107857](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41379107857) remains **in progress** in P3; Stage4 gate, P0, P1 and P2 passed. Last available decoded P3 log at 04:21:55 UTC shows Time Step 106, time=0.000523389 s, dt=5µs. P4 and final artifacts are still pending.
- Extracted deduplicated native P_rf_raw_W_t6 postprocessor rows directly from the running 5µs job log and the original successful 10µs Stage5 1000W job log. The *same 400–500µs physical-time window* yields:

| 1000W 400–500µs metric | Original 10µs dtmax | Trial 5µs dtmax |
| --- | ---: | ---: |
| Native monitor rows | 10 | 20 |
| RF minimum (W) | 864.4407 | 955.8005 |
| RF maximum (W) | 1098.1640 | 1055.0660 |
| RF peak-to-peak (W) | 233.7233 | 99.2655 |
| Sample RMS error from 1000W (W) | 73.8335 | 28.6957 |

- This window shows a smaller sampled RF excursion at 5µs (about 57.5% smaller peak-to-peak and 61.1% smaller RMS), **but it is not a converged timestep study**: samples have different time grids and phase, and the 5µs run has not reached the decisive 500–1000µs interval. The 5µs trace still shows a real oscillatory RF response, so the PID/Maxwell hypothesis remains open.
- Added [oxygen25_pid_physical_lag.py](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/analysis/oxygen25-stage5-1ms-oscillation-gate-20261102/.github/scripts/oxygen25_pid_physical_lag.py), commit `9a4ff303dc520a7bc853bc62cc37ed8e40e06b68`, to evaluate **physical-time** RF-error vs PID-drive-rate correlations using linear interpolation, interval-duration weights, and unsaturated-only intervals. This avoids comparing sample-index lags as if 5µs and 10µs samples had identical physical delays. Synthetic 5µs/10µs test recovers a known 10µs injected delay and passes locally. Correlation is diagnostic only; no controller causality or Stage6 safety follows.
- After P4 and native artifact verification, compare the full 500–1000µs window with both existing `oxygen25_stage5_dt5us_compare.py` and this physical-time-lag diagnostic. Do not adjust PID gains or chemistry without an independently justified scientific experiment.

**Decision: Stage6 1–10ms dtmax=100µs remains HOLD.**

## 2026-11-02 05:39 UTC: live 500–800 µs matched-window test reveals timestep-scaled RF cycle

- Rechecked original Stage5 DIRECT Run [41358545575](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41358545575): `completed/success`, both 400 W and 1000 W native P0–P4 passed; 1 ms restart artifact IDs `13107661302` and `13109110076` remain available.
- Rechecked the isolated 1000 W dtmax=5 µs [Run 41379107857](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41379107857): `in_progress`, Stage4 gate/P0/P1/P2 passed, **P3 still running**; P4 and native artifacts pending. Latest decoded P3 monitor/step reached **823.389 µs**, with `dt=5 µs`, as of log timestamp 05:30 UTC.
- Parsed the actual MOOSE postprocessor tables from job logs (`125065801658` at 5 µs, `125003788529` at 10 µs), deduplicating repeated rolling-history rows by physical time. Compared **the same 500–800 µs physical-time window**, not equal sample indices:

| 1000 W metric, 500–800 µs | dtmax=10 µs (original) | dtmax=5 µs (trial) |
| --- | ---: | ---: |
| Unique RF monitor samples | 30 (506.777–796.777 µs) | 60 (503.389–798.389 µs) |
| Raw RF power minimum | 313.681 W | 619.696 W |
| Raw RF power maximum | 1938.829 W | 1436.778 W |
| RF peak-to-peak | **1625.148 W** | **817.082 W** |
| RMS RF target error | **403.652 W** | **174.254 W** |
| PID output at upper clamp 3.0 | **4/30 (13.3%)** | **2/60 (3.3%)** |
| RF local-maximum spacings | **80, 70, 80 µs** | **40, 40, 40, 40, 45, 40 µs** |
| O2(a1Delta) negative sample-to-sample steps | 0 | 0 |

- At 5 µs, the sampled peak-to-peak RF excursion is **49.7% smaller** and sampled RMS error **56.8% smaller** than the 10 µs case in this window, but remains **817 W peak-to-peak** at a nominal 1000 W target: a significant oscillation.
- **New root-cause clue:** observed cycle periods approximately halve as dtmax halves: ~70–80 µs at 10 µs dtmax versus ~40 µs at 5 µs dtmax, i.e. roughly **8 time steps per cycle** in both trials. This is consistent with a discrete-time feedback / solver-coupling limit-cycle mechanism, rather than a timestep-independent physical oscillation. **It is not causal proof**: phase, sample grids, adaptive stepping, and nonlinear plasma response may confound the comparison. PID saturation still occurs in both runs.
- Both O2(a1Delta) sampled traces are monotone over 500–800 µs, but the original 10 µs neutral dips appeared **after 866 µs**. Do not extrapolate the neutral result to 1 ms. Only final verified native CSVs can establish the full 500–1000 µs comparison.
- Next: finish the 5 µs P3/P4 and verify its native restart artifact, compare full 500–1000 µs with `oxygen25_stage5_dt5us_compare.py`, `oxygen25_pid_limitcycle_diagnostic.py` and `oxygen25_pid_physical_lag.py`; assess whether a further 2.5 µs refinement is scientifically justified. No PID gain or chemistry modifications are authorized by this observation.

**Stage6 1–10 ms with dtmax=100 µs remains HOLD.** A dtmax larger than the observed 40–80 µs RF cycle has no demonstrated stability or convergence basis.


## 2026-11-02 06:35 UTC: completed 5 µs 1000 W native result; postprocessor defect isolated

- Live Stage5 DIRECT [Run 41358545575](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41358545575) remains `completed/success`, both powers P0–P4 PASS, native 1 ms artifact IDs 13107661302 (400 W) and 13109110076 (1000 W).
- Isolated 1000 W `dtmax=5 µs` [Run 41379107857](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41379107857) finished at **06:16:03 UTC** with workflow `completed/failure`. This is **not a physics/P3 failure**: P0, rates, P1, P2, P3, **P4 native advanced-restart archive proof**, and neutral-trend diagnostics **passed**. The later Python comparison step failed before producing paired JSON/CSV; final `restart-complete` artifact was therefore not uploaded. The available 5 µs diagnostics artifact ID **13120970548** contains the actual `run/plasma.csv`, 1 ms native checkpoint directory, and `restart_1000000ns_manifest.json`. Its manifest reports `final_time_s=0.001`, `actual_moose_step=202`, `source_sha=8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`, `power_w=1000`, `scientific_acceptance=HOLD`, and both restart archive identities. P4 log reports native continuity and SHA256 attestation PASS; **do not represent the missing final restart-complete upload as successful**.
- Root cause of postprocessor failure: the genuine native `plasma.csv` has **exactly one** RF power zero, at `t=0` (before the RF postprocessor initializes); the same initial row has pre-clamp `rf_drive_scale_t6=7.4955980963788`. All subsequent native RF values are positive and the drive is in the permitted clamp range. The comparator incorrectly rejected `RF<=0` at *all* timestamps with `ValueError: negative/zero native RF or negative neutral`. Fixed comparison and RF/PID lag diagnostic readers to allow this **initial row only**, while retaining strict nonfinite, negative-density, positive post-start RF and post-start drive-bound checks. Added regression testing of t=0 acceptance and post-start zero rejection. This is a diagnostic software defect, not evidence of an unstable MOOSE solver.

### Full native 500–1000 µs matched physical-window comparison (1000 W)

The following values were independently calculated from the two downloaded original **native CSVs**, not extrapolated from partial P3 logs. Original control diagnostics artifact ID **13108926022**; trial artifact ID **13120970548**. Both time series reach 1 ms, have strictly increasing finite timestamps, nonnegative four-neutral densities, and positive RF power after the initial sample.

| Metric | dtmax=10 µs, control | dtmax=5 µs, trial |
| --- | ---: | ---: |
| Late-window native rows | 51 | 101 |
| RF minimum (W) | 281.382 | 566.813 |
| RF maximum (W) | 2034.639 | 1493.363 |
| RF peak-to-peak (W) | **1753.257** | **926.550** |
| RF RMS target error (W) | **500.714** | **247.649** |
| PID upper clamp at 3.0 | 10/51 (19.61%) | 10/101 (9.90%) |
| Sampled RF local-peak spacing | 70–80 µs | 40–45 µs |
| O2(a1Delta) negative density increments | 3 | **0** |
| O2(a1Delta) slope sign reversals | 4 | **0** |
| Largest O2(a1Delta) local drop | 0.117077% | **0%** |

- The 5 µs trial reduces the **sampled late-window RF peak-to-peak by 47.15%** and RMS target error by **50.54%**, yet still has a **926.55 W** peak-to-peak oscillation and PID saturation. This is consistent with a timestep-dependent discrete feedback/Maxwell-plasma limit-cycle hypothesis; it is **not** proof of cause or numerical convergence.
- At 1 ms, trial minus control neutral densities: **O2(X) −0.05626%, O2(a1Delta) +1.44488%, O(3P) +1.36020%, O(1D) +0.31196%**. The 5 µs trace has no significant late-window O2(a1Delta) downward step, whereas the 10 µs control does. O2(X) decreases monotonically in both runs, which is physically admissible and is **not** an oscillation.
- Native 5 µs P3/P4 reached 1 ms, but **the full workflow failed in a diagnostic post-step**, so distinguish native solver completion from overall CI acceptance. The comparison can be rerun **artifact-only** without recomputing 3.5 h of physics.

**Decision remains HOLD for Stage6 1–10 ms at dtmax=100 µs.** A 5 µs refinement did not eliminate RF oscillation or demonstrate convergence. Next: execute an artifact-only CI postprocessing workflow with corrected t=0 reader, verify paired JSON and PID lag metrics, then design a further 2.5 µs refinement or a separately justified RF feedback diagnostic. Do not modify chemistry/PID gain or overwrite successful Stage5/Stage6 runs.


### 2026-11-02 06:37 UTC: independent artifact-only CI comparison PASSED

- Implemented an **artifact-only** GitHub Actions workflow [oxygen25-dt5us-artifact-only-analysis.yml](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/analysis/oxygen25-stage5-1ms-oscillation-gate-20261102/.github/workflows/oxygen25-dt5us-artifact-only-analysis.yml). It verifies exact original/trial run IDs and SHAs, both P0–P4 step outcomes, Stage5 native manifests and source identity, checkpoint directory presence, t=0 regression tests, the paired full-window native comparison, RF limit-cycle metrics and physical-time PID lag. It does **not** rerun MOOSE, modify the solver, or launch Stage6.
- [Postrun CI Run 41400946021](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41400946021) **completed SUCCESS** at analysis workflow SHA `38cacc47f47a6c1a23b7ae4105730cb7b673191e`. Uploaded artifact **13120544265**, `oxygen25-stage5-dt5us-vs-dt10us-1000w-postrun-evidence`, containing paired JSON/CSV and 10 µs/5 µs RF saturation, period and physical-time lag JSONs.
- CI output independently confirms 10 µs late RF period **80 µs**, 5 µs late RF period **40 µs** (prominence-filtered), with RF peak-to-peak reduction **47.15264%**. Time-weighted observational PID lag correlation finds strongest negative correlation at 5 µs for 10 µs control (r≈−1.0) and 0 µs for 5 µs trial (r≈−0.945). These are **sampled feedback correlations**, not evidence of causal delay or a controller gain prescription.
- Full-window neutral results match independent local CSV analysis: O2(a1Delta) late local drop **0.117077% → 0%**; 1 ms endpoint trial-minus-control **O2(X) −0.05626%, O2(a1Delta) +1.44488%, O(3P) +1.36020%, O(1D) +0.31196%**.
- **Next bounded experiment proposal:** a further 1000 W dtmax=2.5 µs refinement, initially **100–500 µs only** (160 requested 2.5 µs intervals), keeping the exact native Stage4 100 µs checkpoint, PID, chemistry, source SHA and RF target. The 5 µs 100–1000 µs job took ~3.5 h, so attempting 2.5 µs all the way to 1 ms in one standard 6 h GitHub-hosted job risks timeout. Evaluate 400–500 µs matched RF amplitude/period first; extend by verified native checkpoint continuation only if scientifically justified.

**Stage6 at dtmax=100 µs remains HOLD.** The native 5 µs run finished, but the original 5 µs workflow remains failed in its postprocessor; independent analysis CI passed without rewriting the historical run.
