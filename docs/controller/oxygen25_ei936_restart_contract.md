# Oxygen25 EI936 effective O(ex): canonical cross-CI restart contract

**Authority:** science and approved 25 reactions remain in issue #419; bounded runtime Controller in issue #427. This is a *numerical restart procedure*, not scientific acceptance. Maintain `SCIENCE_HOLD`.

## Proven starting points

- Native independent 0→1 ns for both 400 W and 1000 W: successful Actions run `41198547541`, original source SHA `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`.
- Genuine distinct-CI 1→2 ns restarts with **full source, input, mesh, rate SHA and native checkpoint**: successful run `41208644597`. Verified 400 W artifact `13045668207`, 1000 W artifact `13045289286`.
- **Current last promoted time: 2 ns per power.** Never replace it with a failed intermediate experiment. Continue only after actual P3 final-time proof and P4 full-state manifest/archive round-trip.

## One stable process, configurable time targets

Workflow: `.github/workflows/issue419-oxygen25-restart-chain.yml` on the isolated Controller branch. The workflow supports a bounded `workflow_dispatch` interface in addition to push-triggered default replay:

| Input | Meaning | Current default |
| --- | --- | --- |
| `start_ns` | Existing separately verified checkpoint *physical* time, integer nanoseconds | `2` |
| `end_ns` | Requested new physical end time, integer nanoseconds (max 100000 = 100 µs) | `100` |
| `interval_ns` | Requested sequence/event target spacing in **nanoseconds**, positive decimal | `1` |
| `upstream_run_id` | Exact prior successful GitHub Actions run ID hosting independently verified per-power artifacts | `41208644597` |

Example (when upstream 100 ns becomes independently verified): `start_ns=100`, `end_ns=1000`, `interval_ns=10`, `upstream_run_id=<that 100 ns success run>`. Before 100ns PASS the above values are **not a runnable accepted handoff**.

**Important:** `interval_ns` controls `Executioner/TimeStepper/time_sequence` requested physical targets. It is **not a guarantee** that the internal MOOSE timestep or Maxwell RF cadence increases to that value. MOOSE may substep; do not expand its fast-scale timestep without verified plasma/RF stability. A bounded max event count (20001) rejects runaway time grids; erroneous nonfinite/zero/negative intervals fail P0.

## Immutable scientific and runtime identities

1. From the *exact* previous successful run + each power-specific artifact, verify the archived `restart_run_...tar.gz`, `restart_inputs_...tar.gz`, complete per-member sizes/SHA256 and native checkpoint data/header/mesh. Check source SHA, reaction inventory (25 EI936 O(ex)), mesh, power, build-image digest and all 19 private lookup SHA256 values. EI936 has explicit attributed analytic Maxwellian fallback until a valid private 936 table is available.
2. Checkout the pinned original physics source; build the actual native `physics-opt` using the pinned image. Never rerun chemistry prepare over the saved runtime.
3. Stage exact parent and child inputs from archives. Apply a **known-inventory advanced-restart-only transformation**: remove 15 parent variable seed `initial_condition` assignments and 3 Maxwell child AuxVariable seeds (except already-cleaned successive stages), retain every variable, kinetics, mesh and chemistry component, require Maxwell `no_restore=false`, and bind the full *absolute* restored checkpoint base. Reject other/unreviewed initial conditions; never force `allow_initial_conditions_with_restart`.
4. Use advanced `Problem/restart_file_base`, **not `--recover`** when the future `TimeSequenceStepper` sequence is being extended. Preserve prior `time_sequence` prefix and append future targets, including exact requested endpoint. Preserve parent and nested MultiApp state.
5. P0 mutation tests and archive round-trip → P1 native build → P2 real `--check-input` (parent and child) → P3 real native PhysicsApp → P4 time/monitor continuity, state files and complete next-stage archive SHA256. Separate CI per stage and per-power artifacts. Capture failure logs, no protected rate tables.
6. `RUN_SUCCESS` is not `SCIENTIFIC_ACCEPTED`; EI936 source and independent charge/mass/power plausibility remain a scientific hold.

## Failure-ledger regression constraints

| Prior CI | First proven failure | Mandatory regression guard |
| --- | --- | --- |
| `41204362088` | P4 incorrectly equated nanoseconds with MOOSE native step ID | Check final step parsed from solver log, not `end_ns` |
| `41212837874` | `--recover` preserved old completed TimeSequenceStepper sequence; negative next dt | Advanced restart and full restored time/step continuity |
| `41218079940` | Parent `ConstantIC` collided with native restored plasma variables | Exact 15 parent seed inventory removed only for advanced restart |
| `41222090939` | Relative restart path duplicated input folder; parent Maxwell `no_restore=true` | Absolute /workspace checkpoint path; `no_restore=false` |
| `41222709336` | Invalid workflow YAML created an empty job run | Confirm actual matrix jobs, not just a workflow event |
| `41222771191` | Maxwell child `electron_density_state_t6_moose` `ConstantIC` collided with checkpoint | Exact 3 child AuxVariable seeds suppressed and P0 mutated inventory checks |
| `41223958574` | Time-grid refactor accidentally omitted explicit `checkpoint=true` gate, caught by self-test | Checkpoint-enabled P0 negative mutation restored |


### Legacy 2 ns checkpoint TimeStepper prefix reconciliation (2026-10-31)

The independently verified 1→2 ns native recovery completed at actual step **4** in both 400 W and 1000 W, with accepted CSV history `[0, 1, 1.001, 1.002, 2]` ns. MOOSE 9f388366 serializes a restarted `TimeSequenceStepper::_time_sequence` and `_current_step`; `setupSequence` checks all indices `j <= _current_step` on advanced restart. Previous failed native CI **41224078027** reported at entry 3: staged value **2 ns**, restored value **1 ns** (required prefix length **5**). This is *not* a P2 syntax/IC issue; both powers passed P2.

For this **specific** original SHA `8e2fe042...`, stage schema 2, native step 4, and exact source 2 ns CSV, the helper constructs a checkpoint-compatible **staged input time-sequence overlay**:
`[0, 1, 1.00000001, 1.001, 1.002, 2, 3, ..., 100]` ns.

The small extra `1.00000001` ns entry is a **strictly increasing proxy** for the historically serialized duplicate **1 ns** index; its difference is `1e-17` seconds, within the `MooseUtils::absoluteFuzzyEqual` default tolerance. This is **not** an extra physical solver timestep and does not alter any checkpoint binary or chemistry. The saved vector is the native authority, the accepted CSV only attests the case-specific history; **P3 is still the required test** that this proxy aligns all `_current_step` entries. Unknown step/CSV/SHA histories fail closed rather than synthesizing a prefix. Future stages preserve the full already-staged prefix and append user-selected interval and endpoint; new cutback insertions require independent re-characterization.

The helper writes `restart_time_sequence_overlay.json` with the exact upstream checkpoint and staged time-sequence, which P4 SHA-includes in the next restart inputs archive. It does not replace a genuine native MOOSE field restart. Current active exact-head CI run: [41225167309](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41225167309), commit `2b2cb59c1dd9a844f82f8f26aca56e79c1ae04f8`. Both P0 / 19 private SHA **PASS**, P1 build **in progress** at 17:34 UTC. P2/P3/P4 are not yet accepted; both valid endpoints remain **2 ns**.

## Acceptance and continuation

A green workflow does not substitute for numerical final-time proof, CSV and Exodus continuity, parent plus child restored fields, RF power/convergence checks, and immutable manifest SHA evidence. Each power advances independently. If a stage fails, keep its previous valid upstream checkpoint and diagnose the first failed gate before retrying. Only after a real both-power 100 ns PASS should 100ns→1µs→10µs→100µs be launched with new specified interval and provenance-bound artifact ID/run ID. Do not stop the hourly Controller until the two-observation terminal protocol completes.
