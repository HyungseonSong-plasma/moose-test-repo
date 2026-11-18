# D8 — same-RF-run direct lower-D `computeQpResidual()` evidence

**Verdict:** `D8_RF_ON_DIRECT_LOWERD_QP_RESIDUAL_3NS=PASS_DIAGNOSTIC_417_941`. `P5_X_STRICT_CURRENT_HEAD=HOLD`. `SCIENCE_HOLD`; 100 µs P3/P4 **NOT_RUN**.

## Actual native execution

- Actual [GitHub Actions run #44345638246](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44345638246), attempt **1**, terminal **SUCCESS**; workflow commit **`33dd83c5f22f590904a4a4c6c69bbfb19f9f29cf`**, job **`134947148309`**.
- [Artifact #14445519251](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44345638246/artifacts/14445519251), ZIP SHA-256 **`69433119bfc9f7f67a556b7920d2092b41c7aaed67b3db1b638f941feeef0cb2`**; raw ZIP CRC PASS.
- Immutable **original Physics source** for both cases: Draft PR #665 `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`. Original eleven-layer S6-417/941 input SHA and protected five original EI rates per case preserved; private /dev/shm cleanup PASS. Original 400 W parent mesh, original Maxwell child, actual seven Transfers and TimeSequenceStepper retained. Three original 1 ns steps, total **3 ns**.
- One isolated **diagnostic compile** injected the known numerical-entry trace into `PhysicsLowerDSurfaceCurrent::computeQpResidual()` without modifying the repository's original C++ or input layers. Diagnostic Physics ELF SHA-256 **`ccd50c0eb7a34ac35b4e303b337a9145d0bfda39ed597b54f2f546e9c91290d2`**, independently recalculated from actual ZIP bytes; instrumented source SHA-256 **`db093e9dd1c53848bf5b2404ad27419a329a54989f205ffff30763c7c2c42004`**; OCI **`sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`**.
- **This is not the unmodified W1 executable.** Old W1 ELF was `1bdc85c65f5847ae58d51c76f89f8e67c67291dc9b5ee842bcbab98c4a71befa`, so it must not be called a same-W1 binary proof. The test instead establishes actual direct method execution in an RF-on, source-pinned diagnostic executable.

## Both cases, same individual RF-on execution

| Observable | 417 | 941 |
|---|---:|---:|
| Real `--check-input` exit / Syntax OK | 0 / yes | 0 / yes |
| Real RF-on 3 ns transient exit | 0 | 0 |
| Child `P_abs` (W) | 209.31596771096 | 209.31597896021 |
| Parent received `P_abs` (W) | 209.31596771096 | 209.31597896021 |
| Seven bidirectional Transfer numeric check | PASS | PASS |
| D8 Wall/Current/Poisson numerical PP | 8/8 finite | 8/8 finite |
| Direct lower-D residual method entry | **3/3** | **3/3** |
| Direct trace in parser-only P2 | absent | absent |

Both **separate physical transient runs** emitted their own three `D8_LOWERD_RESIDUAL_VALUE` lines directly from the compiled C++ `computeQpResidual()` method. These were parsed from the **same execution stdout** as that case's RF child/Transfer evidence, not from an RF-disabled or Postprocessor-only run.

| Actual owner | Face ID | Element ID | qp | First local current (A/m²) | First Qp residual |
|---|---:|---:|---:|---:|---:|
| `sigma_surface_current` | 350 | 3155 | 0 | -43.7561 | +43.7561 |
| `sigma_wafer_surface_current` | 104 | 3208 | 0 | -43.7561 | +43.7561 |
| `sigma_focus_ring_surface_current` | 2153 | 3235 | 0 | -43.7561 | +43.7561 |

The first sampled values and owner identities above were identical for 417/941; this does **not** mean their entire RF fields or trajectories were identical. Separate case trace files both SHA-256 `30cab076841cc9de92632c3a6f18a268202ba500811821ba2eb736aaac64b00e`; raw trace bytes were included in Artifact and independently rehashed. Full sanitized Qp lines were also found in each actual Native excerpt. Producer-reported full Native log SHA-256: 417 `841f9533aa15c8eeec11e9c8e819bf508060978ed4e2b3e2f9e31806274b62f6`, 941 `fe814090daf8d90f4c86646f6d6dc64be7217576f45a6604cbde3e9bf15ea46c` (full logs were **not** uploaded for independent off-job rehash).

**Independent audit:** 42/42 checks PASS on actual downloaded ZIP (SHA-256, CRC, raw diagnostic ELF, provenance and bounded gates, actual three owner event lines per case, numeric finiteness/sign, per-case raw trace hashes, no trace in P2, same 3 ns RF transfer/child-parent power, protected cleanup).

## Exact limits and remaining gates

- `computeQpResidual()` function entry and its **first sampled QP current/residual** are proven during the RF-active **same case execution**. The trace does not carry an event timestamp. Thus **RF-induced temporal modulation of the local QP residual**, convergence across 100 µs, long-run physical validity, and scientific parity are not established.
- PR #665 advanced to **`52067302d16074592503d0ef6b903cc344f55a08`** as checked after this execution. The diagnostic source is pinned to `74a2b0f`; strict current-HEAD/binary acceptance remains separately HOLD. Source/ELF equivalence cannot be promoted by implication.
- This evidence does not merge PR #665, change main, weaken P05, or approve P3/P4. Original private EI bytes, raw chemistry/RF full solver outputs and original eleven input raw files are intentionally absent from the public ZIP; numeric trace text is public/sanitized.
- The parent Issue #671 canonical STATE should incorporate this bounded diagnostic result only at its authorized integration gate; do not independently convert this result to `P5_X_FINAL=PASS`.

**Evidence workflow:** [Isolated RF-on direct-Qp one-shot](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/33dd83c5f22f590904a4a4c6c69bbfb19f9f29cf/.github/workflows/issue671-d8-rf-on-qp-residual-3ns-once.yml).
