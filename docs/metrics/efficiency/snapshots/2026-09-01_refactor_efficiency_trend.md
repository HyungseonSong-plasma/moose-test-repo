# Refactor Efficiency Trend — 2026-09-01

- **Snapshot date:** 2026-09-01
- **Metric type:** Refactor interaction-efficiency retrospective
- **Scope:** Recent QPX architecture/refactor work, primarily Issues #53-#57 and #59-#64
- **Canonical metric owner:** `docs/protocols/metrics_closure.md`
- **Related monitoring:** `docs/metrics/issue_efficiency_monitoring.md`
- **Related CLOSED-work ledger:** `docs/metrics/work_closure_efficiency_ledger.md`
- **Incident context:** `docs/metrics/incidents/`
- **Status:** Derived retrospective; reconstructed values must not be silently promoted to exact canonical ledger values

## 1. Purpose

This report evaluates whether the recent refactor execution strategy is reducing user interaction and validation cost while preserving closure quality.

The main process change under review is:

```text
small/staged refactor
  -> multi-owner campaign
  -> multi-Issue batch
  -> independent rollback boundaries
  -> one final-tree-ready state
  -> consolidated user-local validation
```

The report also tests whether the remaining interaction cost has shifted away from production-code defects toward validator/control-plane/environment defects.

## 2. Metric discipline

Canonical efficiency metrics are issue-local:

```text
WCC
T-WCC
RVR
EVR
DBR
RWR
CLR
FBR
```

This retrospective additionally uses derived **batch-level** measurements such as `unique user rounds / Issues closed`. Those derived values are not canonical WCC and must not be copied into issue-local ledgers as if they were.

Evidence labels:

```text
exact          = directly supported by durable issue/validation evidence
reconstructed  = recoverable from explicit closure evidence and/or retained interaction history
unavailable    = insufficient evidence; no estimate is forced
```

### Important EVR correction

Recent architecture guards often printed markers such as:

```text
ISSUEXX_REFACTOR_EVRS: 0
```

Those markers established that **no scientific runtime/P3 evidence** was consumed. They did not mean canonical `MET-05 EVR=0` when the user executed a final guard/self-test and returned the result.

For this report:

```text
scientific runtime/P3 consumption
  !=
canonical external validation rounds (EVR)
```

A returned user-local final guard is a canonical external validation round attributable to the work it validates.

## 3. Durable refactor evidence — #53 to #57

| Issue | Scope | Consolidation strategy | Canonical EVR evidence | Repair / defect evidence | Scientific runtime/P3 |
|---|---|---|---|---|---|
| #53 | one 942-LOC Stats owner, D1-D5 extraction | staged decomposition | unavailable from retained closure summary | 2 transcription-drift incidents + 1 stage-blind inventory false FAIL | no scientific change recorded |
| #54 | one Issue45 electron-inventory owner | close-level decomposition | `2 reconstructed` minimum: initial final-guard FAIL + repaired rerun PASS | 1 final-guard import-path `GATE_DEFECT` | 0 consumed by refactor |
| #55 | five large owners | one coordinated campaign, one final validation | `1 exact` consolidated user-local validation | no repair cycle recorded | 0 scientific runtime |
| #56 | five contract/diagnostic owners | one coordinated campaign, one final validation | `1 exact` consolidated user-local validation | no repair cycle recorded | 0 scientific runtime |
| #57 | ten owners, Stage A/B | one queue, one consolidated validation | `2 exact`: consolidated validation + repaired M0 inventory rerun | 1 validator baseline-data defect | 0 scientific runtime |

### #53 interpretation

Issue #53 successfully reduced `stats_builder.py` from 942 LOC to an 81-LOC facade, but its closure record explicitly reports two whole-file transcription-drift incidents and one inventory false FAIL. Exact WCC/T-WCC/EVR were not prospectively instrumented in the retained closure record, so they remain unavailable here rather than estimated.

### #54 interpretation

Issue #54 reached the desired close-level decomposition and preserved scientific state, but the initial final guard failed because file-based execution did not place the repository root on `sys.path`. The guard was repaired and rerun. This is a clear validator-side rework event, not scientific evidence consumption.

### #55-#56 interpretation

Issues #55 and #56 are the strongest early evidence for efficient consolidation. Each campaign processed five owners and closed from one consolidated user-local validation return with no recorded repair cycle. Both retained independent work-unit rollback boundaries while deferring local execution until the final tree was ready.

### #57 interpretation

Issue #57 doubled campaign scope to ten owners. The first consolidated validation established the production/facade/self-test acceptance surface. One additional result return was needed because the M0 validator baseline encoded A3 as 698 LOC while the frozen blob actually contained 729 LOC. Production code was unchanged.

The resulting descriptive throughput is:

| Campaign | Owners reviewed | User-local validation returns | Owners / validation return | Assistant/gate repair cycle |
|---|---:|---:|---:|---:|
| #55 | 5 | 1 | 5.0 | 0 |
| #56 | 5 | 1 | 5.0 | 0 |
| #57 | 10 | 2 | 5.0 | 1 |

The owner-level throughput remained approximately five owners per external validation return even when campaign scope doubled. This is descriptive only; owner complexity is not uniform.

## 4. Declarative architecture batches — #59 to #64

The current interaction history permits a more direct reconstruction of the recent batching pattern.

### Batch A — #59

```text
Issues closed:                    1
Unique user interaction rounds:   4 reconstructed
Unique validation returns:        1 reconstructed
Assistant-caused repair rounds:   0 reconstructed
Scientific runtime/P3:            0
Final guard:                      PASS on first returned run
```

Issue #59 froze seven production recipes, 130 symbols, and their consumer baseline without production recipe mutation.

### Batch B — #60 + #61

```text
Issues closed:                    2
Unique user interaction rounds:   4 reconstructed
Unique validation returns:        1 reconstructed
Assistant-caused repair rounds:   2 reconstructed at batch level
Scientific runtime/P3:            0
Final consolidated guard:         PASS on first returned run
```

The two additional interaction rounds were not caused by ExperimentSpec/transform implementation failures. They were control-plane/process failures:

1. accidental placeholder Issue #65 mutation during a file phase;
2. an over-strict RM-12 interpretation that blocked business mutation merely because unrelated mutator schemas were provider-bundled.

The actual #60/#61 user-local consolidated implementation guard passed on its first returned execution.

Because these rework rounds occurred while both sibling Issues were being executed as one batch, exact issue-local allocation of `RWR` is ambiguous. This report therefore keeps `2 reconstructed` as a batch-level rework observation rather than duplicating it into both canonical issue ledgers.

### Batch C — #62 + #63 + #64

```text
Issues closed:                    3
Unique user interaction rounds:   3 reconstructed
Unique validation returns:        2 reconstructed
Assistant-caused repair rounds:   0 reconstructed
Scientific runtime/P3:            0
Implementation repair between runs: none
Final consolidated guard:         PASS
```

The first validation return failed only because the executed workspace did not contain:

```text
docs/development/2026-09-01_issue63_recipe_readiness.json
```

The later current-tree run passed without a code repair. Therefore the extra round is classified here as a workspace/artifact-freshness rerun, not `RWR` caused by an implementation or analyzer repair.

## 5. Derived batching trend

The following table is deliberately **not** canonical issue-local WCC. It measures the interaction density of each executed batch using unique user rounds observed for the batch.

| Batch | Issues closed | Unique user rounds | Derived rounds / Issue | Derived Issues / round | Unique validation returns | Returns / Issue |
|---|---:|---:|---:|---:|---:|---:|
| #59 | 1 | 4 | 4.00 | 0.25 | 1 | 1.00 |
| #60-#61 | 2 | 4 | 2.00 | 0.50 | 1 | 0.50 |
| #62-#64 | 3 | 3 | **1.00** | **1.00** | 2 | 0.67 |

From #59 to #62-#64, the derived interaction density changed from:

```text
4.0 unique user rounds / Issue
  ->
1.0 unique user round / Issue
```

This is a **75% reduction in the derived batch interaction density**.

The reciprocal throughput changed from:

```text
0.25 Issues / unique user round
  ->
1.00 Issue / unique user round
```

which is a **4x increase in derived Issue throughput per interaction round**.

These are small-sample descriptive observations, not causal or inferential statistics. Issue complexity and work type are not identical across batches.

## 6. Closure-quality guardrail

The apparent efficiency gain did not come from weakening the acceptance surface.

Across the recent batches:

- #55 and #56 full relevant QPX harness/self-test surfaces passed;
- #57 full relevant harness/self-test surfaces passed after a validator-data repair;
- #59 census/consumer guard passed;
- #60/#61 strict schema, deterministic plan, transform, negative-control, and issue-leakage guards passed;
- #62 default/Jacobian legacy-vs-spec rendering was byte-identical;
- #63 classified all six remaining recipes and transferred follow-up debt explicitly;
- #64 relevant full QPX harness self-test and architecture integration guard passed;
- no new scientific P3/runtime discriminator was executed solely for these refactors.

Therefore the observed batching improvement is compatible with the `MET-13` requirement to minimize interaction/validation cost **subject to closure-quality constraints**.

## 7. Bottleneck shift

The dominant source of extra rounds appears to have shifted.

Earlier refactor work shows implementation/delivery defects:

```text
#53
  transcription drift
  stage-blind validator false FAIL

#54
  final-guard import-path defect
```

Later work increasingly shows control-plane, validator-data, or environment identity defects:

```text
#57
  frozen baseline LOC mismatch in validator data

#60-#61
  repository mutation / protocol-routing defects

#62-#64
  stale/current workspace artifact identity mismatch
```

This is directionally consistent with the broader incident snapshot in `docs/metrics/incidents/snapshots/2026-09-01_root_cause_breakdown.md`, where **Validation Harness & Classifier** is the largest single reported category at 27%.

That historical incident snapshot does not provide enough MET-20 coverage to classify all prior incidents as novel/known/bypass/gate-defect cases. The comparison here is therefore qualitative: validation/control-plane reliability remains a material residual cost surface.

## 8. Comparison with historical efficiency monitoring

`docs/metrics/issue_efficiency_monitoring.md` reports an older four-Issue scientific baseline with:

```text
mean WCC = 9.75
mean EVR = 6.75
mean RWR = 3.25
```

and a later bounded #20 result with:

```text
WCC = 4
EVR = 2
RWR = 0
```

The recent refactor campaigns should **not** be directly pooled with those scientific incidents because work type and complexity differ materially. Structural architecture work can often close using P0/P1/static characterization without scientific runtime.

The valid comparison is process-directional:

- broad historical work incurred high external execution/rework cost;
- bounded post-review work reduced that cost;
- recent refactor campaigns preserve zero architecture-only scientific runtime while increasingly amortizing one local validation across multiple independent rollback units.

## 9. Current conclusion

The available evidence supports the following working hypothesis:

> Consolidating multiple independently recoverable refactor units into one final-tree-ready validation batch is reducing interaction burden without reducing closure quality.

The strongest evidence is:

1. #55 and #56 each validated five owners in one external return with no recorded repair cycle;
2. #57 doubled owner scope while preserving roughly five owners per external return, with only one validator-data repair;
3. the #59 -> #60/#61 -> #62/#63/#64 sequence shows derived interaction density falling from 4.0 -> 2.0 -> 1.0 rounds per Issue;
4. all recent architecture batches preserved scientific runtime/P3 freeze and relevant regression/self-test acceptance.

However, the evidence does **not** yet prove that larger batches are always better. Causal recoverability, rollback locality, and failure attribution remain hard constraints.

## 10. Next prospective test — #66 to #68

The next comparable 3-Issue architecture batch should be instrumented prospectively from WORK_START rather than reconstructed afterward.

Desired execution outcome:

```text
Issues:                         #66, #67, #68
independent rollback units:      yes
consolidated validation:         1 user-local return if final tree is clean
architecture-only scientific P3: 0
RWR target:                      0
CLR target:                      0 where current context/retrieval suffices
closure quality:                 full declared compatibility/regression PASS
```

Canonical metrics must be recorded **per Issue** from start:

```text
Complexity
WCC
T-WCC
RVR
EVR
DBR
RWR
CLR
FBR
Reopened
Root-cause class
Primary process lesson
Closure-quality note
```

If one consolidated user-local result directly validates all three Issues, that return is attributable to each Issue's local EVR; do not divide it fractionally.

The primary process hypothesis to test is:

```text
3-Issue batch
+ one consolidated current-tree validation return
+ RWR = 0
+ no scientific P3
+ preserved rollback locality
=> repeatable interaction-efficiency improvement
```

## 11. Metric debt and recording policy

### #53-#57

Exact WCC/T-WCC cannot be defensibly reconstructed from the retained GitHub closure evidence alone. Keep them unavailable unless explicit historical interaction evidence is reconciled later. Do not create synthetic values merely to fill the ledger.

### #59-#64

Batch interaction counts in this report are `reconstructed` from the current retained operating-session history. They are useful retrospective observations, but future work should use prospective counters so exact issue-local WCC/T-WCC/RWR can be appended to the canonical CLOSED-work ledger.

### Future snapshots

Create a new date-stamped file rather than overwriting this report when #66-#68 or later comparable work closes. The next report should compare predicted vs observed values and explicitly state whether the `RWR=0 / one-consolidated-validation` hypothesis was reproduced.
