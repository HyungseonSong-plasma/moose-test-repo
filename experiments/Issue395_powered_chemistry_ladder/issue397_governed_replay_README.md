# Issue 397 — Samuel-governed Graded Coarse L1 power-scan replay

## Scope and provenance

This integration preserves the original 200/250/300 W Graded Coarse L1 / EI17
scientific inputs and successful later Maxwell tolerance resolution. The original
workflow `.github/workflows/issue397-graded-l1-power-scan-200-250-300w-100us.yml`
was **not authorized by the governed workflow-surface guard** and is intentionally
**absent from main**. Its historical Git blob is
`228fffdf8dd265ceffda973e2319c6c30b450a66`.
It must not be restored as a permanent workflow.

- Original [Actions run #39617859962](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39617859962): 200/250 W P3/P4 PASS, original 300 W interrupted under Maxwell `nl_abs_tol=1e-12`.
- Verified follow-up [run #39740088502](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39740088502): 300/400 W 100 µs P3/P4/P5 PASS after the **single exact-source Maxwell `1e-12 → 1e-11` change**.
- Issue #403 is completed for numerical convergence. **This integration does not rerun or reinterpret the historical 100 µs results.**

## Approved preflight — no long-running solver

The persistent, authorized entrypoint is **`.github/workflows/experiment.yml`**.
Its existing `workflow_dispatch` inputs are:

| Input | Value |
|---|---|
| `issue` | `397` |
| `sequence` | `01` |
| `manifest` | `automation/manifests/experiments/Issue_397_experiments01.json` |
| `base_sha` | Exact intended 40-hex commit SHA containing this manifest |

The Samuel governed-work action reads the manifest from the control-plane checkout,
validates the target checkout at exactly `base_sha`, and generates structured
stage evidence and artifacts. The manifest performs:

1. **P0** — Bash static validation, contract identity and pinned Python library installation.
2. **P1** — generate inputs, original 27-face L1 mesh, unchanged ion/electron wall physics,
   full 460-step time grid, six EI17-baseline reaction operators, per-case RF targets,
   SHA-audited Maxwell child `nl_abs_tol=1e-11` for 200, 250 and 300 W.
3. **P2** — compile `physics_app/physics-opt` against the immutable build-base image.
4. **P3** — exact `--check-input` on all three cases.

**P3 of the Samuel preflight manifest is check-input, not the physics time
integration.** Do not report a 100 µs solver PASS from this manifest. The existing
governed workflow has a **120-minute job limit**; its manifest stage limit is
**7200 seconds**, whereas the historical individual 100 µs solves took roughly
3–5 hours.

## Long solver replay — explicit governed one-shot

The same source-faithful replay script has five phases:

```bash
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh prepare 300
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh build 300
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh check 300
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh solve 300
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh audit 300
```

For a new full 100 µs replay, separately authorize deployment of the **inactive**
`experiments/Issue395_powered_chemistry_ladder/issue397_l1_final_replay_once.template.yml.txt`
to `.github/workflows/issue397-l1-final-replay-once.yml` on an **exact approved main SHA**.
That filename is an accepted **self-path push one-shot** in the existing
workflow-surface guard; it runs three independent 6-hour-bounded matrix jobs
and uploads per-case evidence even when a solver fails. After terminal
observation, remove the workflow through Samuel's governed mutation/cleanup
path. **Do not deploy this one-shot as part of PR #400 merging**, and do not
modify the guard, weaken the wall physics, or change the Maxwell tolerance/PID
cap to make the integration appear successful.

## Regression verification

```bash
python3 -m pytest -q tests/characterization/test_issue397_samuel_replay.py
python3 ci/guards/workflow_surface_guard.py --check
```

See `issue397_final_l1_200_250_300w_power_scan_contract.json` for immutable
mesh SHA, 27-face D1 and original-versus-follow-up experimental provenance.
