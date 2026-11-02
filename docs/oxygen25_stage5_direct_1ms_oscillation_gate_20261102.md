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
