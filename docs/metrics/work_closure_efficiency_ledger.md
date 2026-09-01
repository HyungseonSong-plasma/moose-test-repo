# Work Closure Efficiency Ledger

This ledger records user↔MOOSE interaction efficiency for formally CLOSED technical work items.

Canonical metric definitions are owned by `docs/protocols/metrics_closure.md`.

| Work ID | Title | Complexity | WCC | T-WCC | RVR | EVR | Prospective EVR budget | DBR | RWR | CLR | FBR | Reopened | Root-cause class | Primary process lesson | Closure-quality note |
|---|---|:---:|---:|---:|---:|---:|---|---:|---:|---:|:---:|:---:|---|---|---|
| M5-ion-wall | Solved-potential O2+ wall migration incident | C3 | `>=20*` | `>=15*` | n/a | 8 | n/a | 5 | 2 | 0 known | no | no | nonlinear convergence / scaling interaction | parallelize hypothesis triage; include convergence sensitivity + numeric invariants in first batch | historical reconstructed closure; use directionally, not for exact medians |
| reactor-o2plus-integration | Reactor-scale O2+ charged-heavy integration | C3 | 9 | 7 | n/a | 5 | n/a | 1 | 3 | 0 | yes | no | charged-heavy integration / conservation closure | first valid broad batch resolved hypotheses; remaining cost came from preventable test-harness defects | production closure accepted; harness rework preserved in metrics |
| qpx-transform-vocabulary-v2-complex-construction | #66 Extend bounded ExperimentSpec transforms for complex MOOSE/PETSc construction | C2 | `5*` | `4*` | `0*` | `3*` | `3/3*` | `0*` | `0*` | `0*` | `yes*` | no | planned architecture debt / bounded transform capability gap | bounded vocabulary can expand without JSON control-flow creep when each op is justified by concrete recipe needs | final #66-#76 guard PASS; operations=11; no scientific P3 |
| qpx-hybrid-spec-plus-diagnostics-extraction | #67 Extract hybrid spec policy and reusable diagnostic capability owners | C2 | `5*` | `4*` | `0*` | `3*` | `3/3*` | `0*` | `0*` | `0*` | `yes*` | no | planned architecture debt / mixed declarative-algorithm ownership | keep declarative policy in specs and reusable interpretation mechanics in capability owners | legacy/spec byte-identical guard PASS; no scientific P3 |
| qpx-spec-ready-issue46-jacobian-localization-migration | #68 Migrate spec-ready Issue46 Jacobian localization recipe to ExperimentSpec v1 | C2 | `5*` | `4*` | `0*` | `3*` | `3/3*` | `0*` | `0*` | `0*` | `yes*` | no | planned architecture debt / spec-ready recipe duplication | migrate spec-ready policy without expanding vocabulary and prove byte equivalence | legacy/spec byte-identical guard PASS; no scientific P3 |
| qpx-post-migration-architecture-census | #70 Freeze post-migration QPX architecture census and dependency baseline | C2 | `6*` | `4*` | `0*` | `3*` | `3/3*` | `0*` | `2*` | `0*` | `yes*` | no | architecture census / guard taxonomy defect during validation | census must distinguish namespace markers from production recipes and machine-check namespace collisions | final census PASS; generic→issue edges=0; collisions=0; no scientific P3 |
| qpx-diagnostics-capability-consolidation | #71 Consolidate reusable diagnostics under qpx_harness/diagnostics | C2 | `5*` | `4*` | `0*` | `3*` | `3/3*` | `0*` | `0*` | `0*` | `yes*` | no | planned architecture debt / reusable diagnostic ownership | reusable Jacobian/nonlinear/runtime facts should depend downward from issue policy, never import issue owners | diagnostics/spec guard PASS; no scientific P3 |
| qpx-execution-evidence-capability-consolidation | #72 Consolidate execution and evidence orchestration into capability packages | C3 | `6*` | `5*` | `0*` | `4*` | `4/3 exceeded*` | `0*` | `1*` | `0*` | `yes*` | no | execution/evidence ownership + Python module/package namespace collision | never introduce `foo.py` + `foo/` ownership collisions; make the invariant machine-checked before external validation | compatibility identity + final integration PASS; no scientific P3 |
| qpx-remaining-recipe-convergence | #73 Converge remaining recipe policy onto ExperimentSpec and capability owners | C3 | `4*` | `3*` | `0*` | `2*` | `2/3*` | `0*` | `0*` | `0*` | `yes*` | no | planned architecture debt / recipe ownership convergence | terminal recipe ownership models prevent both policy duplication and JSON DSL creep | ownership guard PASS; all production recipes terminally classified; no scientific P3 |
| qpx-capability-oriented-cli-boundary | #74 Introduce capability-oriented CLI package and bin/qpx.py entrypoint | C2 | `7*` | `5*` | `0*` | `4*` | `4/3 exceeded*` | `0*` | `2*` | `0*` | `yes*` | no | CLI ownership migration / stale documentation consumer | entrypoint retirement needs exhaustive current-surface consumer/reference proof before external validation | 25 commands preserved; bin launcher PASS; no scientific P3 |
| qpx-compatibility-facade-retirement | #75 Retire redundant issue-numbered facades and normalize public package surfaces | C3 | `6*` | `4*` | `0*` | `3*` | `3/3*` | `0*` | `2*` | `0*` | `yes*` | no | compatibility-surface retirement / stale documentation consumer | retirement is safe only after code, docs, tests and tooling references are all migrated or explicitly justified | scripts refs=0 and final retirement guard PASS; no scientific P3 |
| qpx-capability-oriented-architecture-integration | #76 Integrate and accept capability-oriented QPX harness target architecture | C4 | `7*` | `5*` | `0*` | `4*` | `4/3 exceeded*` | `0*` | `3*` | `0*` | `no*` | no | cross-layer architecture integration / compounded validation-delivery defects | large batches amortize user interaction but need validation-surface preflight to prevent sequential failure exposure | full architecture integration + QPX harness self-test PASS; no scientific P3 |

`*` marks a reconstructed value rather than an exact prospective per-Issue counter. For #66-#76, the reconstruction basis and shared-round attribution rule are frozen in `docs/metrics/efficiency/snapshots/2026-09-01_capability_architecture_batch_closure.md`. Do not sum sibling WCC/EVR/RWR values to estimate total user burden; the batch had 7 unique user rounds and 4 unique external validation returns.

The `ISSUE66_76_EXTERNAL_VALIDATION_ROUND: 1` guard marker was a per-run static marker and is not used as the cumulative MET-05 value.

## Recording rules

- Add a row only when the work reaches formal `CLOSED` status.
- Use the canonical MET-14 field set and preserve raw WCC even when complexity-normalized comparisons are later added.
- If historical counting is reconstructed rather than directly observed, mark the value and explain the basis below the table.
- If a CLOSED work is later reopened, set `Reopened=yes`; its low WCC must not be treated as a clean efficiency success.
- Lower-bound or reconstructed records should be used for process lessons and directional comparison, not silently pooled with exact prospective counters.
- Parent/milestone drivers do not inherit child rounds. #69 is therefore not a technical efficiency row merely because it depends on #66-#76.

## C3 historical comparison

The first instrumented C3 work showed a large diagnostic-efficiency improvement over the historical M5 baseline:

```text
                         M5 baseline     reactor-o2plus
DBR                      5               1
FBR                      no              yes
EVR                      8               5
RWR                      2               3
```

Interpretation:

- parallel hypothesis triage achieved its intended effect: the first valid reactor-scale batch resolved the initial integration hypothesis set;
- total external execution cost improved but remained above target because three avoidable harness defects created rework;
- later architecture/refactor work should be compared separately by work type and complexity because it intentionally avoids scientific P3.

## Architecture/refactor comparison — 2026-09-01

The #66-#76 batch demonstrates two simultaneous effects:

```text
interaction amortization improved
  7 unique rounds / 11 Issues = 0.64 derived rounds per Issue

validation reliability worsened relative to the intended one-return hypothesis
  4 unique external validation returns
  integration-level EVR budget exceeded
```

The next optimization target is therefore not raw batch size. It is the number and coupling of heterogeneous validation surfaces placed behind one external closure command.

## M5 baseline interpretation

M5 is useful primarily as a process-debt baseline:

- `EVR = 8` is far above the future target because diagnostics were initially sequential;
- `DBR = 5` shows the first hypothesis/test matrix did not include enough high-information convergence discriminators;
- `RWR = 2` identifies delivery/checker defects that should be engineered to zero;
- `FBR = no` establishes the baseline from which first-batch resolution should improve.

Future comparable scientific C3 incidents should aim for:

```text
RWR = 0
DBR <= 2
EVR <= 2 before root-cause/production-validation transition
FBR rate increasing over time
```

Future architecture/refactor batches should additionally aim to reduce external sequential failure exposure while retaining independent rollback boundaries.

## Trend review

Once at least five CLOSED items exist in the same complexity/work-type class with exact instrumentation, review:

- median WCC;
- median EVR;
- RWR rate;
- FBR rate;
- reopened-work rate.

The desired trend is lower median WCC/EVR and RWR, with stable or improving closure quality and FBR. Reconstructed refactor rows should remain visibly separate from future prospectively exact observations.
