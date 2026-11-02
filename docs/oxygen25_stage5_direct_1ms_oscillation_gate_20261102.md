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

At 1000 W, RF power oscillations have roughly 70–80 µs spacing. This is a material solver/coupling oscillation, not a minor neutral-density numerical roundoff. Proposed `dtmax=100 µs` would be larger than the observed oscillation period and is therefore not justified without investigating the underlying dynamics and timestep sensitivity.

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
