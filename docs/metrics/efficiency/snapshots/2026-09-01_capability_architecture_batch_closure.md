# Capability Architecture Batch Closure — 2026-09-01

- **Snapshot date:** 2026-09-01
- **Scope:** Issues #66-#76 capability-oriented QPX architecture convergence
- **Parent driver:** #69
- **Canonical metric owner:** `docs/protocols/metrics_closure.md`
- **Comparison snapshot:** `docs/metrics/efficiency/snapshots/2026-09-01_refactor_efficiency_trend.md`
- **Status:** CLOSED-batch retrospective; issue-local values marked `reconstructed` where prospective counters were not independently persisted per Issue

## 1. Closure result

The final consolidated user-local guard returned:

```text
ISSUE66_BOUNDED_TRANSFORMS: PASS operations=11
ISSUE67_68_SPEC_DIAGNOSTICS: PASS legacy/spec byte-identical
ISSUE70_72_73_OWNERSHIP: PASS
ISSUE74_75_CLI_RETIREMENT: PASS commands=25 scripts_refs=0
ISSUE76_INTEGRATION: PASS
ISSUE66_76_SCIENTIFIC_RUNTIME_P3_EVR: NOT_RUN
ISSUE66_76_FINAL_GUARD: PASS
```

Issues #66-#76 and milestone driver #69 were then closed `completed`. No scientific runtime/P3 was executed solely for the architecture work.

## 2. Interaction reconstruction

The retained operating-session history contains seven unique user interaction rounds from the accepted WORK_START through final technical PASS:

| Round | Type | Batch event |
|---|---|---|
| R1 | WORK_START | user requested #66-#76 as one execution queue |
| R2 | resume | continued the partially completed implementation queue |
| R3 | external validation | final guard import failed because `qpx_harness/evidence.py` and `qpx_harness/evidence/` created a Python module/package namespace collision |
| R4 | external validation | after collision repair, architecture census rejected `recipes/__init__.py` as unclassified and CLI-retirement validation found a stale `scripts/qpx.py` reference in current documentation |
| R5 | resume | continued the file-only repair phase after issue-resource evidence recording |
| R6 | external validation | architecture/ownership/integration checks passed, but CLI retirement saw `docs/protocols/validation.md` from an intermediate/stale workspace state |
| R7 | external validation | current-head ZIP returned the complete PASS shown above |

Derived batch totals:

```text
Issues closed in technical queue:     11  (#66-#76)
Unique user interaction rounds:        7 reconstructed
External validation returns:           4
Scientific runtime/P3 returns:         0
Dedicated diagnostic batches:          0
Final technical result:                PASS
```

The `ISSUE66_76_EXTERNAL_VALIDATION_ROUND: 1` marker printed by the guard was a per-run static marker, not a cumulative MET-05 counter. The canonical batch history contains four returned user-local guard executions.

## 3. Issue-local attribution rule

MET-11 prohibits summing or copying sibling metrics as though they were one parent metric. This batch therefore uses the following reconstruction rule:

A shared user round is attributable to an Issue only when it:

1. starts/resumes that Issue's accepted queue work;
2. returns evidence that directly exercises that Issue's acceptance surface; or
3. authorizes/validates repair of a blocker attributable to that Issue.

A consolidated validation return may count in multiple sibling EVRs when it directly validates those siblings. It is never divided fractionally. Later sibling-only rework is not copied into an Issue merely because all Issues belong to the same batch.

Because these counters were not persisted prospectively per Issue during R1, the values below are recorded as **reconstructed**, not exact prospective observations.

## 4. Reconstructed canonical issue-local metrics

| Issue | Complexity | WCC | T-WCC | RVR | EVR | DBR | RWR | CLR | FBR | Prospective EVR budget |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| #66 bounded transform vocabulary | C2 | 5 | 4 | 0 | 3 | 0 | 0 | 0 | yes | 3/3 |
| #67 hybrid spec + diagnostics extraction | C2 | 5 | 4 | 0 | 3 | 0 | 0 | 0 | yes | 3/3 |
| #68 Issue46 localization spec migration | C2 | 5 | 4 | 0 | 3 | 0 | 0 | 0 | yes | 3/3 |
| #70 architecture census | C2 | 6 | 4 | 0 | 3 | 0 | 2 | 0 | yes | 3/3 |
| #71 diagnostics consolidation | C2 | 5 | 4 | 0 | 3 | 0 | 0 | 0 | yes | 3/3 |
| #72 execution/evidence consolidation | C3 | 6 | 5 | 0 | 4 | 0 | 1 | 0 | yes | 4/3 exceeded |
| #73 remaining recipe convergence | C3 | 4 | 3 | 0 | 2 | 0 | 0 | 0 | yes | 2/3 |
| #74 CLI capability boundary | C2 | 7 | 5 | 0 | 4 | 0 | 2 | 0 | yes | 4/3 exceeded |
| #75 facade + scripts retirement | C3 | 6 | 4 | 0 | 3 | 0 | 2 | 0 | yes | 3/3 |
| #76 architecture integration | C4 | 7 | 5 | 0 | 4 | 0 | 3 | 0 | no | 4/3 exceeded |

### RWR reconstruction notes

`RWR` counts additional user rounds caused primarily by avoidable assistant-side artifact/configuration/analyzer defects.

- #70: one guard-taxonomy defect required a separate resume/repair phase and a repair-validation return -> `RWR=2 reconstructed`.
- #72: the module/package collision required one additional repair-validation return -> `RWR=1 reconstructed`.
- #74/#75: the stale current documentation reference required a separate repair continuation and repair-validation return -> `RWR=2 reconstructed` each.
- #76 inherits no child metric by dependency alone; its `RWR=3 reconstructed` reflects integration rounds directly attributable to two successive assistant-side integration defects before the later workspace-identity rerun.
- R6 -> R7 is not counted as assistant-side RWR because the canonical branch already contained the corrected `validation.md`; the observed failure was an intermediate/stale workspace identity escape with no repository repair between R6 and R7.

The values above must not be arithmetically summed across siblings to estimate user burden. Use the batch-level unique-round counts in this snapshot for that purpose.

## 5. Batch-level trend

Derived interaction density now extends the earlier refactor trend:

| Batch | Issues closed | Unique user rounds | Derived rounds / Issue | Derived Issues / round | External validation returns | Returns / Issue |
|---|---:|---:|---:|---:|---:|---:|
| #59 | 1 | 4 | 4.00 | 0.25 | 1 | 1.00 |
| #60-#61 | 2 | 4 | 2.00 | 0.50 | 1 | 0.50 |
| #62-#64 | 3 | 3 | 1.00 | 1.00 | 2 | 0.67 |
| #66-#76 | 11 | 7 | **0.64** | **1.57** | 4 | **0.36** |

Compared with #62-#64, the derived interaction density improved by about **36%** (`1.00 -> 0.64 rounds/Issue`). Compared with #59, it improved by about **84%** (`4.00 -> 0.64`). Derived Issue throughput per user round increased from `0.25` in #59 to about `1.57` in #66-#76, approximately **6.3x**.

This is a batching/amortization result only. It does not mean the larger batch had better validation reliability.

## 6. Validation-cost counter-signal

The number of external validation returns per batch changed as follows:

```text
#59        1 return
#60-#61   1 return
#62-#64   2 returns
#66-#76   4 returns
```

The 11-Issue queue therefore improved interaction amortization while **failing the planned one-consolidated-validation / RWR=0 hypothesis** and exceeding the nominal three-EVR budget at the integration level.

The main reason is not scientific complexity. It is the number of heterogeneous architecture/control surfaces placed behind one external closure boundary:

```text
bounded transform schema
spec rendering equivalence
reusable diagnostics
execution/evidence ownership
architecture census
recipe ownership
CLI migration
consumer/documentation retirement
cross-layer integration
workspace/head identity
```

A failure near the front of one grouped check can prevent later acceptance surfaces from being exercised, causing sequential exposure across external rounds even when the Issues themselves have independent rollback boundaries.

## 7. Incident-learning interpretation

### 7.1 Python module/package namespace collision

```text
Root-cause class:
  Python import ownership collision (`evidence.py` + `evidence/`)

Learning status:
  NOVEL

Reason:
  the target architecture defined capability ownership, but no explicit pre-existing module/package collision invariant or machine gate prevented the invalid Python namespace state.

Remediation implemented:
  remove the conflicting flat module;
  move the API to `qpx_harness/evidence/identity.py`;
  export the compatibility API from the package;
  add module/package collision detection to the architecture census.

Prevention maturity after repair:
  MACHINE_CHECKED
```

### 7.2 `recipes/__init__.py` census false FAIL

```text
Root-cause class:
  architecture census taxonomy defect

Learning status:
  GATE_DEFECT

Reason:
  the machine census ran, but its taxonomy rejected a valid namespace marker that the recipe ownership model intentionally excludes from the seven production recipes.

Remediation implemented:
  classify `recipes/__init__.py` as ISSUE_SPECIFIC_POLICY;
  retain the seven-recipe ownership-set check separately.

Prevention maturity after repair:
  MACHINE_CHECKED
```

These two incidents have enough durable evidence in the #70 validation history to enter the incident-learning ledger.

### 7.3 Stale `scripts/qpx.py` documentation reference

The #74/#75 retirement guard correctly detected an invalid current-state reference in `docs/protocols/validation.md`. This is a delivery defect **caught by the intended gate**, not a gate defect. It should be treated as prevention evidence rather than a new MET-20 recurrence row.

### 7.4 Intermediate/stale validation workspace

R6 reported a stale `validation.md` path even though the canonical branch already contained the corrected file and no repository repair was needed before R7 PASS. This is directionally consistent with `ENVIRONMENT_ESCAPE`, but the retained repository evidence does not independently prove the exact local ZIP/cache timing. Keep the learning status out of classified-incident KPI denominators unless stronger incident-level evidence is persisted.

## 8. Hypothesis evaluation

The prior prospective hypothesis was:

```text
3-Issue or larger recoverable batch
+ one consolidated current-tree validation return
+ RWR = 0
+ no scientific P3
+ preserved rollback locality
=> repeatable interaction-efficiency improvement
```

Observed result:

```text
interaction density improvement:  YES
one validation return:             NO (4)
RWR = 0:                           NO on #70/#72/#74/#75/#76
scientific P3 = 0:                 YES
rollback/ownership locality:       YES
closure quality:                   PASS
```

Therefore the data supports **batch amortization**, but does not support “larger Issue count is always more efficient.”

## 9. Process conclusion

The next batching decision should be based primarily on **validation-surface coupling**, not raw Issue count.

Recommended working hypothesis for future architecture/refactor queues:

```text
maximize independently recoverable Issues per user round
subject to:
  bounded number of heterogeneous validation surfaces
  assistant-side static/preflight coverage of those surfaces
  no early-failure check that hides unrelated downstream acceptance checks
  explicit current-head/workspace identity before external validation
```

In practical terms, an 11-Issue queue can be efficient when many Issues share a small number of stable acceptance surfaces. When the queue spans schema, package ownership, CLI, retirement, documentation, and integration contracts simultaneously, the validation surface should be internally partitioned even if the user still receives one consolidated command.

The next improvement target is therefore not “smaller batches” by default. It is:

> **reduce external sequential failure exposure per consolidated batch.**

Useful prospective measurements for the next comparable queue:

```text
Issues / batch
independent validation surfaces / batch
external validation returns
first external return coverage: accepted surfaces / total surfaces
assistant-caused RWR
workspace-identity reruns
unique user rounds / Issue
```

These are supplemental process measurements; canonical WCC/T-WCC/RVR/EVR/DBR/RWR/CLR/FBR remain unchanged.
