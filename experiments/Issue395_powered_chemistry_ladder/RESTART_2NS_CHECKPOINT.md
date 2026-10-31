# Oxygen24 2 ns checkpoint / 2→4 ns actual restart experiment

**Status:** experimental; only mark restart as passed when both per-power GitHub Actions jobs show `OXYGEN24_2NS_TO_4NS_ACTUAL_RECOVERY_PASS` and `success`. No production/100 µs validation is implied.

## Origin and intent

The successful 2026-10-31 2 ns reference (`0fe03c1e5f6bf14385f51130a43dc4732f2608dc`, run [#41188685410](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41188685410)) archived CSV, input and logs but **did not archive MOOSE restartable checkpoint files**. Therefore **the original specific run cannot itself be recovered**. The present experiment reproduces the same physical 2 ns conditions on a separate branch, explicitly enables a MOOSE checkpoint at every step, stores the checkpoint, extends the time sequence to 4 ns and uses native `--recover` to solve the next two steps.

Both powers use full24 chemistry with 19 externally mounted private rate tables, original 200 sccm neutral inlet, `x_{O2a}=x_{O3P}=x_{O1D}=1e-5`, exact mesh source and power-specific Maxwell/MultiApp overlays. Child state is contained in the **parent** MOOSE checkpoint. No scientific claim beyond the two-step runtime/restart test.

## Execution contract

- [One-shot Actions workflow](../../.github/workflows/issue419-oxygen24-restart-once.yml) (actual path at repository root: `.github/workflows/issue419-oxygen24-restart-once.yml`).
- `oxygen24_checkpoint_restart.py`: enable checkpoint, verify 2 ns source identity/CSV, checkpoint file inventory and SHA-256; extend `TimeSequenceStepper` to `0 1 2 3 4 ns`; reject a reset/reinit masquerading as a continuation.
- `oxygen24_resume_native.sh`: execute the same native `physics-opt` and original parent+chemistry+elastic overlays **with `--recover`**. The original `Outputs/file_base` must remain unchanged, so MOOSE can find the parent checkpoint.
- **0→2 ns**: execute exactly two 1 ns steps with `[Outputs] checkpoint = true`; save initial CSV and full `run/plasma_cp` directory as `checkpoint_2ns.tar.gz` plus SHA-256.
- **2→4 ns**: extend input `end_time` / `time_sequence`, do native input check, then `--recover`. Verify actual solver recovery evidence, endpoint 4 ns, original first-stage CSV and preserved reaction physics. Enforce a separate **285-second wall clock cap** on each solve.
- The one-shot workflow archives the tarball, verification JSON, raw solver logs, two inputs, input check, CSV, elapsed wall times. The private numeric rate tables are **never uploaded**.

## How to resume from the archived 2 ns state later

In an identical source checkout with the same native `physics-opt`, mesh, rate tables and identical parent+Maxwell overlays, recreate the same generated input and output directory. Then:

1. Extract the `checkpoint_2ns.tar.gz` into the exact `$RESULT/run/` directory such that `$RESULT/run/plasma_cp` exists. This tarball preserves directory hierarchy and symlinks.
2. Use the archived `input_2ns_checkpoint.i` as the starting main input; extend its time sequence to the desired end time (or use `oxygen24_checkpoint_restart.py --extend` for 4 ns). **Do not call `prepare` after restoring a checkpoint**, because the replay script recreates and clears `$RESULT`.
3. Call the native `oxygen24_resume_native.sh 400` or `1000` with `OXYGEN_RESEARCH_FULL24=1`, `OXYGEN_RESEARCH_QUICK_5MIN=1` and the exact execution-source SHA in `CHATGPT_WORK_BASE_SHA` (the source SHA must match checkout). Run from the repository root.
4. Validate solver stdout for real `--recover`, require time advancement beyond checkpoint timestamp, and compare fields and moment statistics to the pinned initial 2 ns state.

**Limitations:** Changing mesh, MPI processor count, parent/child model structure, or generated overlay paths may invalidate checkpoint recovery. Different time grids can also affect stepper compatibility. This procedure does not bootstrap missing private rate tables or validate the physical correctness of unverified chemistry channels.

Original MOOSE reference: https://mooseframework.inl.gov/docs/site/application_usage/restart_recover.html
