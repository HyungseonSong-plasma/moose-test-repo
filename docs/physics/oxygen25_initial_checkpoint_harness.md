# Oxygen25: parameterized first-run native checkpoint harness

## Scope and authority

This feature packages the **first native MOOSE run starting from time zero** for the pinned, already demonstrated 25-reaction Oxygen ICP with EI936 effective O(ex). It does **not** attempt to repair or continue an existing MOOSE checkpoint. The source commit is pinned to `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`; the GHCR build image is pinned by SHA256. It does not add or remove reactions, reassign O(1S)/O(1D), change gas conditions, or alter full parent and Maxwell MultiApp coupling.

Original successful evidence: [first-run 0→1ns Actions #41198547541](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41198547541). The helper preserves the same `issue397_l1_power_scan_replay.sh` `prepare → build → check → solve` recipe and the original 12 input, mesh and overlay files. Chemistry is prepared **once, before** the clock/checkpoint overlay; no upstream first-run `--recover`, no `Problem/restart_file_base`, no resumed-stage parent or child seed suppression.

## Parameter contract

| Parameter | Meaning | Default |
| --- | --- | --- |
| `power_w` | `400`, `1000`, or workflow choice `both` | both |
| `end_ns` | Positive *integer* ns for first-run final physical time, maximum `100000` | `1` |
| `interval_ns` | Requested TimeSequenceStepper interval, positive decimal ns, minimum `0.001` ns | `1` |
| `source_sha` | Immutable proven 25-reaction source and scientific model | fixed; cannot override |

A maximum 20,001 time-grid events prevents unbounded input generation. The harness **does not guarantee** a numerical solve at other `end_ns` or `interval_ns` combinations: MOOSE must complete P1/P2/P3/P4, and plasma/RF stability must be reviewed for each combination. Changing target spacing is not a substitute for resolving physical timestep limits. The 30-minute native solve wall cap and 90-minute job bound also remain explicit.

The standalone adapter is `physics_harness/adapters/moose/initial_checkpoint.py` and accepts:

```bash
python3 physics_harness/adapters/moose/initial_checkpoint.py --self-test
python3 physics_harness/adapters/moose/initial_checkpoint.py --stage-input --root "$PWD" --power-w 400 --end-ns 1 --interval-ns 1
python3 physics_harness/adapters/moose/initial_checkpoint.py --verify-and-archive --root "$PWD" --power-w 400 --end-ns 1 --interval-ns 1
```

The stage command must execute only after the proven source `prepare` command has regenerated the original 2ns smoke input. The archive command must execute **only after the genuine solver P3**. These direct commands do not run a solver by themselves. CI wraps them with the fixed solver commands and explicit rate rehydration.

GitHub Actions workflow: `.github/workflows/oxygen25-initial-checkpoint-harness.yml`. Once merged onto the repository default branch, launch it with **Run workflow**, choose `power_w`, `end_ns`, and `interval_ns`; it checks out the pinned science source and loads the harness from the exact workflow commit. The isolated development branch's push trigger tests the successful default 1ns case only. Do not confuse workflow availability on an unmerged feature branch with enabled default-branch manual dispatch.

## Acceptance evidence and output contract

An accepted first-run job requires: original 19 private collision-rate tables rehydrated from a CI secret, 25-reaction EI936 scientific identity, existing source/regression P0 tests, native PhysicsApp build P1, native input check P2, genuine solver timestep and requested final time P3, and complete MOOSE state plus archive SHA256 validation P4. A workflow event without native jobs and a green P2 without actual P3/P4 are **not** success.

Each successful power produces an independent `oxygen25-ei936-<end>ns-initial-checkpoint-complete-<power>W` artifact with:

- `restart_run_<end>ns.tar.gz`: **all** run directory files, including native `plasma_cp` parent/Maxwell restart state, Exodus, CSV, etc.
- `restart_inputs_<end>ns.tar.gz`: exactly the verified 12 input, overlay, mesh and public collision files.
- `restart_<end>ns_manifest.json`: physics source/image, model/rates identity, actual native MOOSE step, exact physical end, full file SHA256/size inventories, and restart dependencies.
- `restart_archives_<end>ns.sha256` and original solver/verification evidence.

Native checkpoint numbering is derived from the *actual final MOOSE step*, **not from elapsed nanoseconds**. Required restartable `.rd/data`, header and mesh checkpoint header must be nonempty. Archive round-trip verifies every byte/size, and any private numerical rate table or secret path is prohibited from artifact creation. On failure, diagnostics are retained separately with no false green success artifact.

## Distinct follow-on restart

This contract produces a **first-run checkpoint only**. A separate restart harness must validate the manifest version, the previous run artifact, time algorithm state and parent+Maxwell continuity before restarting to another target. Producing this artifact does not automatically certify compatibility with the existing `issue419-oxygen25-restart-chain.yml`, whose legacy bootstrap expects different manifest schema and timing modes. Do not promote a fresh first-run artifact into a restart chain until that independent contract is tested.

All accepted native numerical runs retain `scientific_acceptance=HOLD` until independent plasma, rate and RF power-closure assessment.
