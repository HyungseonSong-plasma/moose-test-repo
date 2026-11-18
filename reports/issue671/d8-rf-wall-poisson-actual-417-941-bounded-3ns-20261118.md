# Actual S6-417/941 RF × D8 combined evidence — bounded 3 ns

**Result:** `D8_COUPLED_RF_WALL_CURRENT_POISSON_3NS=PASS_BOTH_CASES`; `S6_100US_SCIENCE=NOT_RUN / SCIENCE_HOLD`; `P5-X_RELEASE=HOLD_LATEST_HEAD_AND_TYPED_WAREHOUSE`.

This is **new actual physical execution**, not a static functor graph or an aggregate of disjoint RF-only and D8-only tests. The same unmodified W1 executable physically ran *both cases* with the original S6 plasma eleven-layer inputs, protected EI rate files, original real Maxwell child, original seven forward/reverse Transfer definitions, TimeSequenceStepper and bounded 3 × 1 ns RF.

## Physical execution and exact source

- Exact runtime production source **Draft #665 `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`**, Git tree `10ab018235f047bf1abc250d3b18005b9156752a`. The task-isolated workflow branch does not modify the compiled PhysicsApp or production original input layers.
- Real [CI Run #44337988067](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44337988067), job `134919807070`: terminal **SUCCESS** for 417 and 941, actual `--check-input` and bounded transient exit 0 for each.
- [Artifact #14442342839](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44337988067/artifacts/14442342839), **32,500 bytes**, downloaded, independently ZIP SHA-256 `3a38a8598c8a9b4f9f17b46d0772d20190bba7f795cebb14cc059f6ac75ada73`, CRC PASS.
- Same W1 actual `physics-opt` ELF SHA-256 `1bdc85c65f5847ae58d51c76f89f8e67c67291dc9b5ee842bcbab98c4a71befa`; original one-build [#44319316180 / Artifact #14435245012](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44319316180/artifacts/14435245012), ZIP SHA `b1f2dea2ab3d03b3c640260ce4fbdab72b2497a3d1faa24c54106e5f5847d4cd`. The W1 TAR + ELF + both original app libraries were independently downloaded/rehashed and tied to this run. Pinned OCI `sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`.
- Per-case protected **five original EI rate files** staged with SHA checks in private `/dev/shm`, deleted on exit. Public Artifact contains no rate raw bytes. Final post-P4-X eleven input hashes intact, real parent plasma mesh `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc`, original Maxwell child `655fa43c4c1083e55ea4e845e0e2947c627aec39bc9dd0d384f52468db512698`; old ion FV 26, electron 10 and duplicate materials 6 retired.

## Numeric values observed together in the actual RF run

These are **boundary integrals** via `ADSideIntegralFunctorPostprocessor`, **not local flux densities per face**. The last row is a plasma-block **volume integral** via `ADElementIntegralFunctorPostprocessor`.

| Measured observable | 417 | 941 |
|---|---:|---:|
| Maxwell child absorbed power `P_abs` (W) | 209.31596771096 | 209.31597896021 |
| Parent received `P_abs_maxwell_t6` (W) | 209.31596771096 | 209.31597896021 |
| `O2p_wall_number_flux` cover integral | 1.1745012237866e18 | 1.1745024589339e18 |
| `Om_wall_number_flux` cover integral | 2.7396658122147e13 | 2.7396657876227e13 |
| `Op_wall_number_flux` cover integral | 1.1824333493448e15 | 1.1822397786512e15 |
| `e_wall_number_flux` cover integral | 2.3652133267958e19 | 2.3652139200785e19 |
| `cover_net_surface_current_density` cover integral | −3.6011286276022 | −3.601129411267 |
| `wafer_net_surface_current_density` wafer integral | −0.85181504110183 | −0.85181503581399 |
| `focus_ring_net_surface_current_density` focus integral | −0.057864287198826 | −0.05786428553962 |
| `poisson_source` plasma volume integral | 6824.4954427714 | 6824.4957138455 |

For both, 7/7 RF Transfers actual numeric PASS, Maxwell child `Solve Converged!`, two-way child-to-parent field/power exchange, `P_abs` exact matched, actual parent+child physical states observed at final `time=3e-9 s`. **All eight D8 Postprocessor results finite for both cases**, and 417/941 case-specific outputs are not identical copies. Original [prior full-RF-only run #44330414176](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44330414176) produced identical Maxwell absorbed powers per case, ruling out a changed RF numerical result from the diagnostic Postprocessors in this bounded sample.

**Producer-calculated numerical full-log SHA in Artifact:** 417 `13d6e2e4e5050d8bd126d62f9130c7aeab9b2488317eb9b1c9f9a9afeba9e7b4`; 941 `53aaf926babbd0c0f01545bfc5c13bd8bab75d3d3dbbeced31d4c457ddb4ca82`.

## Independent verification and limits

- **78/78 independently checked assertions PASS**, covering physical ZIP CRC, old RF reference ZIP, current W1 ZIP/TAR, actual ELF and two app `.so` original bytes, both actual S6 case-specific numeric receipts, seven-Transfer gates, eight D8 numeric outputs, original source/case SHA manifests, rates count and cleanup, actual solver excerpts, and per-case identity.
- Local independent verifier SHA-256 `f52a55489eb9056fe682672c12e0ed2c0639fe37cb2a483cb0fbeb36116febc0`; independent report SHA-256 `e54390853e170166eb857c955a15d4b81fe5e7826695292e14f5660d283d0ed3`. Raw producer full CSV, full log and original eleven input `.i` bytes were intentionally **not** included in this sanitized public Artifact. Numeric CSV values and full-log digests are job-generated and hence cannot be **independently recomputed off-job** from public bytes; all exposed values, file identities, CRC and cross-run RF values were independently cross-checked.
- The earlier [RF-OFF D8 direct `computeQpResidual()` diagnostic #44303391987](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44303391987) reported local lower-D residual samples. The **current same-W1 RF-ON coupled run** directly evaluated boundary/current/Poisson **functors via Postprocessors**, but **did not write an instrumented `computeQpResidual()` function-entry trace or an independent raw 12 ion FVKernel +12 FVBC +8 electron FEM BC Warehouse object list**. These distinct evidence levels must not be conflated.
- The actual pinned W1 source was `74a2b0f…`, while PR #665 advanced to `52067302d16074592503d0ef6b903cc344f55a08` (exact Git comparison: only `.github/workflows/ion-fvm-hybrid-staged-dt.yml` and `tests/test_issue633_newonly_run_species_schema.py`). No Physics runtime source changed in that comparison; however **strict latest Git HEAD exactness is still HOLD**. Do not automatically claim the same ELF was built from `52067302…`.
- **3 ns is a bounded initial coupled physics verification** and does not authorize or prove 100 µs P3/P4, reference equivalence, time-step stability or scientific approval. `SCIENCE_HOLD`.

**P5-X handoff:** Accept `D8_RF_WALL_CURRENT_POISSON_NUMERIC=PASS_BOTH_CASES_BOUNDED_3NS_SAME_W1`. Keep `D8_DIRECT_LOWERD_RESIDUAL_SAME_RF_JOB=NOT_OBSERVED`, `WAREHOUSE_TYPED_12K_12BC_8EBC=HOLD`, `P5_X_LATEST_HEAD_W1=HOLD`, `P5_X_FINAL=HOLD`, `SCIENCE_HOLD`. No P05 suppression, source/workflow production merge, Private EI exposure or long-run dispatch was performed.
