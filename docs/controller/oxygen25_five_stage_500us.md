# Oxygen25 EI936 — five independent native runs to 500 µs

**Status:** experimental, not yet scientifically accepted. No chemistry, mesh, gas boundary, parent/Maxwell coupling or native physics source modifications. Source SHA: `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab` with exact pinned 19 lookup rates and 25 effective O(ex) reactions.

## Exact requested schedule

| Stage | Physical start | Physical finish | Nominal Δt | Requested intervals | Cumulative intervals | Independent CI |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 0 | 0.1 µs (100 ns) | 1 ns | 100 | 100 | `oxygen25-500us-stage1-initial.yml` |
| 2 | 0.1 µs | 2 µs | 10 ns | 190 | 290 | `oxygen25-500us-stage2-restart.yml` |
| 3 | 2 µs | 10 µs | 100 ns | 80 | 370 | `oxygen25-500us-stage3-restart.yml` |
| 4 | 10 µs | 100 µs | 1 µs | 90 | 460 | `oxygen25-500us-stage4-restart.yml` |
| 5 | 100 µs | **500 µs** | **10 µs** | **40** | **500** | `oxygen25-500us-stage5-restart.yml` |

There are exactly **500 requested intervals and 501 unique global target times**. Stage boundary 100/2000/10000/100000 ns is counted only once globally (although each local run emits its checkpoint initial row). The previous 100 µs / 460-step schedule is retained for historical comparison; this new 500 µs plan does not silently overwrite `set_timegrid_100us_460steps.py`.

The single source of truth is `.github/scripts/oxygen25_five_stage_plan.py`, which computes the global grid and SHA256 of the full five-stage plan. `--self-test` rejects wrong segment counts, discontinuous start/end, terminal time drift, and altered upstream model/power/step/plan provenance.

## Native execution versus the requested grid

**A target time is not an assurance that the native MOOSE timestep lands exactly on it.** Stage 1 uses the proved fresh `TimeSequenceStepper` input `0,1,...,100ns` and writes the genuine final `plasma_cp/<actual MOOSE step>` at 100ns.

At Stages 2–5, the original 2ns recovered MOOSE `TimeSequenceStepper` history showed a corrupted/stale serialized step vector; the tested 2→100ns advanced restart with `IterationAdaptiveDT` overcame that failure and computed up to 100ns, pending RF boundary acceptance. Consequently, Stages 2–5 use **advanced native restart**, carry the full checkpoint state, switch only the staged TimeStepper to `IterationAdaptiveDT` with `reset_dt=true`, initial 1ps and `dtmax` set to that stage's requested spacing (10ns, 100ns, 1µs, 10µs). MOOSE may cut back, take intermediate substeps, or fail numerical convergence. Stage-specific time grids are *requested cadence/upper bounds*, not a guaranteed 500-step integration.

A maximum 10µs timestep is **not validated as scientifically or numerically stable** for this RF plasma. Do not interpret a green P0/P2 as that validation. Actual iteration counts, source/energy/charge balance and convergence histories must be examined. If a stage fails, decrease its native dt cap, rerun the same stage from the same last-good checkpoint, and leave prior artifacts immutable. Any smaller validated cap must be recorded in the stage's evidence (and if schedule definition changes, require an explicit new plan version/approval).

## Independent workflow run and checkpoint handoff rules

Each stage is a **separate GitHub Actions workflow** with both 400W and 1000W jobs. A successful Stage N emits distinct native `restart_run_<END>ns.tar.gz`, `restart_inputs_<END>ns.tar.gz`, JSON `restart_<END>ns_manifest.json`, and raw CSV/Exodus/native log per power.

Stages 2–5 are triggered only on the prior stage's completed **successful** workflow, via `workflow_run`, and require the triggering workflow's branch to match the repository default branch. Alternatively, each has manual `workflow_dispatch` with an **exact prior successful run ID**. GitHub only activates `workflow_run` workflows after they exist on the default branch; **this draft feature branch does not yet activate unattended chaining**. The Stage 1 branch push is an independent test; it does not authorize Stages 2–5 before review/merge.

At every handoff, P0 must verify:

1. **Exact source and provenance:** previous stage number, 400/1000 W power, source SHA, chemistry identity, plan SHA, actual physical endpoint, actual MOOSE step checkpoint prefix, and the previous stage's native artifact name / run ID.
2. **Byte-for-byte native state:** the entire prior run tar, all native checkpoint data/header/mesh files, prior Exodus and CSV, all 12+ input/mesh/overlay paths, original 19 rate-table SHA256, artifact archives per-member SHA256/size. Never reconstruct plasma/Maxwell state from CSV and never run `prepare` after restoring the archive.
3. **Correct native advanced restart:** full parent field and Maxwell MultiApp state from the exact checkpoint, known previous seed ICs removed only for the staged restart, `no_restore=false`, absolute checkpoint path, past native data untouched.
4. **Physical continuity:** at P4, native solver reaches exact requested ending time, writes final new numbered checkpoint, produces actual Exodus and CSV and preserves 145+ fixed density/energy/Maxwell/chemistry monitors at the boundary. Exactly five known RF diagnostics are compared under their source-backed INITIAL re-evaluation semantics; changed source or scale ratios, nonfinite values, or unknown monitors are rejected.
5. **Acceptance:** only after both per-power P3 and P4 pass may the workflow complete successfully, publish the next stage's full restart artifacts, and activate the downstream workflow. The `five_stage_chain` manifest attestation records requested steps, previous run ID, plan SHA and stage identity; `scientific_acceptance` stays `HOLD` pending independent physical assessment.

## Validation and rollout

- Original 0→1ns success: CI [41198547541](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41198547541).
- Parameterized fresh 0→1ns checkpoint CI [41237570736](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41237570736) passed P0–P4 for both powers, proving the initial-run adapter and real native artifact archiving.
- Separate old advanced restart CI [41226074449](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41226074449) actually reached 100ns for both powers, but failed P4 RF diagnostic epoch check; it is **not** an accepted stage1 checkpoint for this new chain.
- Feature-branch Stage1 native 0→100ns run [41254154699](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41254154699) had passed P0 and started native build on initial observation. Stage2–5 are implementation targets, not claimed production successes.
- Independent lightweight static CI verifies the five YAML files and per-stage SHA/provenance and negative mutation cases. Actual P3/P4 for each stage and both powers remain mandatory.

Failure of any stage leaves the last validated native checkpoint and run ID unchanged; a successful timestep log alone never advances the chain. Post-500µs numerical completion is distinct from a scientifically credible steady-state ICP solution.
