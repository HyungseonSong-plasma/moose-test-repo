# Post-2026-09-01 Efficiency Metric Reconstruction — 2026-09-03

- **Snapshot date:** 2026-09-03
- **Scope anchor:** work completed after the existing 2026-09-01 efficiency snapshots, plus carry-in Issue #31 whose substantive R4 execution/closure occurred after that snapshot
- **Canonical metric owner:** `docs/protocols/metrics_closure.md`
- **Comparison reports:**
  - `docs/metrics/efficiency/snapshots/2026-09-01_refactor_efficiency_trend.md`
  - `docs/metrics/efficiency/snapshots/2026-09-01_capability_architecture_batch_closure.md`
- **Canonical monitoring:** `docs/metrics/issue_efficiency_monitoring.md`
- **CLOSED-work ledger:** `docs/metrics/work_closure_efficiency_ledger.md`
- **Status:** retrospective reconstruction; exact, reconstructed/lower-bound, and unavailable fields are deliberately separated

## 1. Purpose

This report was created because the repository has closed a large number of Issues since the 2026-09-01 efficiency snapshots, but the canonical metrics required by `docs/protocols/metrics_closure.md` were not consistently finalized at Issue closure.

The objectives are:

1. reconstruct every defensible post-snapshot metric without inventing missing values;
2. restore exact CLOSED-work records where durable MET-14 evidence exists;
3. quantify the measurement-completeness debt itself;
4. compare the new exact cohort with the previous refactor-efficiency reports;
5. assess whether scientific execution efficiency improved or merely shifted cost between Issues;
6. identify why the metrics process stopped being reliable;
7. define a prospective measurement rule for #27 and subsequent work.

The central conclusion is two-sided:

> **Technical execution became substantially more efficient in the exact post-convergence cleanup cohort, but the metrics system itself regressed after #84.**

The current problem is therefore not simply high execution cost. It is that later science/refactor work often closed with strong technical evidence but without a complete canonical efficiency observation.

---

## 2. Evidence discipline

The canonical evidence labels are used strictly:

```text
exact
  = complete value is directly present in durable issue body/comment or a canonical metric record

reconstructed
  = value is recoverable from explicit durable execution chronology or retained interaction history

lower-bound
  = at least this much cost is proven, but the exact total cannot be recovered

unavailable
  = evidence is insufficient; no estimate is forced
```

Important distinctions from the prior reports remain in force:

```text
scientific P3 executions
  !=
canonical EVR
```

and:

```text
child/sibling execution history
  != automatically inherited parent metrics
```

A user-local validation result may be attributable to more than one sibling only when it directly validates each sibling's acceptance surface. Parent/milestone drivers do not inherit child rounds merely from dependency structure.

### 2.1 Audit window

The previous 2026-09-01 snapshots already cover the earlier refactor campaigns through #76. To avoid double counting, this report uses the following post-snapshot population:

```text
#77-#84                         8 closed technical Issues
#86-#94 + #98                 10 closed technical Issues
#99-#111 + #114               14 closed technical Issues
#31 R4 carry-in                1 closed technical Issue
-----------------------------------------------
reconstruction population      33
```

Excluded:

- #95/#96: `CLOSED / NOT_PLANNED` optional branches, not completed technical work;
- #97 and later still-open/planned technical work;
- #112/#113: discarded connector-verification Issues, no engineering work;
- PR #85: merge vehicle, not an Issue-local technical work unit;
- #43: architecture/governance parent, excluded from issue-local efficiency aggregation even though it closed after #31;
- #17/#26/#27/#40/#41 state synchronization without completed technical closure in this audit window.

---

## 3. Measurement-completeness reconstruction

### 3.1 Full MET-14 coverage

| Cohort | Closed technical Issues | Complete durable MET-14 | Coverage | Evidence quality |
|---|---:|---:|---:|---|
| #77-#84 | 8 | 8 | **100%** | exact |
| #86-#94 + #98 | 10 | 0 | **0%** | partial science/runtime evidence only |
| #99-#111 + #114 | 14 | 0 | **0%** | architecture/CI evidence; canonical round metrics absent |
| #31 carry-in | 1 | 0 | **0%** | lower-bound reconstruction from retained interaction history |
| **Overall** | **33** | **8** | **24.2%** | insufficient for pooled post-snapshot WCC/RWR statistics |

This is the strongest process finding in the audit.

The repository moved from a cohort with complete per-Issue MET-14 recording (#77-#84) to two large cohorts where technical/scientific closure continued but canonical efficiency measurement stopped.

Therefore:

```text
technical closure quality       remained strong
metric closure quality          degraded sharply
```

A green CI or accepted scientific result must not be interpreted as a complete efficiency observation when WCC/T-WCC/RVR/EVR/DBR/RWR/CLR/FBR are absent.

### 3.2 Why missing values were not backfilled numerically

WCC, T-WCC, RWR and CLR depend on **user interaction round boundaries**. GitHub Issue chronology alone cannot reconstruct those boundaries reliably after straight-through automated work.

For example, multiple commits, CI failures and fixes can occur in one user round and therefore create zero RWR, while a single avoidable defect that forces the user to return a new result creates RWR. Counting commits, comments or CI runs as proxy rounds would violate the canonical definitions.

Accordingly, this report does not synthesize WCC from timestamps or number of commits.

---

## 4. Exact post-convergence cohort — #77 through #84

The durable closure records for #77-#84 contain complete MET-14 values. #79/#82/#84 stored their exact records in closure comments rather than the final body; those records are now restored into the canonical CLOSED-work ledger.

| Issue | Complexity | WCC | T-WCC | RVR | EVR | DBR | RWR | CLR | FBR | Evidence |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|:---:|---|
| #77 | C2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | yes | exact |
| #78 | C2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | yes | exact |
| #79 | C2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | n/a | exact |
| #80 | C2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | yes | exact |
| #81 | C2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | yes | exact |
| #82 | C3 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | n/a | exact |
| #83 | C2 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | yes | exact |
| #84 | C3 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | n/a | exact |

Exact aggregate:

```text
n                 = 8
mean WCC          = 1.0
median WCC        = 1.0
mean T-WCC        = 1.0
mean EVR          = 0.0
mean RWR          = 0.0
EVR > 3           = 0/8
RWR > 0           = 0/8
reopened          = 0/8
```

These Issues were architecture/cleanup work and intentionally consumed no scientific P3. Their validation was largely assistant-side current-tree/static/CI validation rather than user-local QPX execution.

### 4.1 Comparison with the 2026-09-01 #66-#76 technical-child table

For an issue-local comparison, parent driver #69 is excluded from the prior batch. The comparable #66-#76 table therefore contains ten technical rows.

Previous reconstructed means:

```text
#66-#76 technical children, n=10
mean WCC          = 5.6
mean T-WCC        = 4.2
mean EVR          = 3.2
mean RWR          = 1.0
EVR > 3           = 3/10 = 30%
RWR > 0           = 5/10 = 50%
```

New exact means:

```text
#77-#84, n=8
mean WCC          = 1.0
mean T-WCC        = 1.0
mean EVR          = 0.0
mean RWR          = 0.0
EVR > 3           = 0/8
RWR > 0           = 0/8
```

Directional change:

| Metric | #66-#76 | #77-#84 | Change |
|---|---:|---:|---:|
| mean WCC | 5.6 | **1.0** | **-82.1%** |
| mean T-WCC | 4.2 | **1.0** | **-76.2%** |
| mean EVR | 3.2 | **0.0** | **-100%** |
| mean RWR | 1.0 | **0.0** | **-100%** |
| EVR budget exceedance | 30% | **0%** | improved |
| positive RWR rate | 50% | **0%** | improved |

### 4.2 Interpretation of the improvement

This improvement is credible for the **post-convergence cleanup class** because closure quality remained strong:

- consumer/reference census was performed before retirement;
- canonical ownership was already mature;
- refactors were increasingly implementation-free or bounded ownership moves;
- static/current-tree validation caught defects before user-local execution;
- scientific semantics were frozen;
- fresh CI/checkpoint validation was performed before closure.

However, this cohort is easier than a new scientific integration problem. The result should be interpreted as:

> Once architecture contracts and validation surfaces became stable, cleanup work approached one-round closure with zero user-local execution/rework cost.

It does **not** prove that scientific C2/C3 work should have EVR=0.

---

## 5. Science cohort — partial reconstruction for #86-#94 and #98

Full canonical MET-14 is missing for this entire cohort, but significant scientific-runtime information is durable.

| Issue | Role | Complexity | Canonical round metrics | Durable execution evidence | Reconstruction status |
|---|---|:---:|---|---|---|
| #86 | existing-evidence provenance reconstruction | C1 | WCC/T-WCC/RWR unavailable | no new scientific runtime | scientific EVR 0 supported; full MET-14 unavailable |
| #87 | residual-fidelity / conditioning audit | C2 | WCC/T-WCC/RWR unavailable | no new scientific runtime; one final discriminator recommended | scientific EVR 0 supported; full MET-14 unavailable |
| #88 | final Issue45 discriminator | C2 | WCC/T-WCC/RWR unavailable | exactly one EVR3 executed; H1 conditioning favored | EVR=1 exact for this Issue's scientific run; other canonical fields unavailable |
| #89 | post-science canonicalization | C2 | WCC/T-WCC/RWR unavailable | scientific EVR 0; CI PASS | partial only |
| #90 | experiment/pytest separation | unavailable in MET-14 | WCC/T-WCC/RWR unavailable | scientific EVR 0; qpx-free CI PASS | partial only |
| #91 | governed R3 acceptance parent | C3 | parent/child attribution incomplete | final accepted R3 bundle exists | at least one direct acceptance return; do not inherit #92/#93/#98 rounds |
| #92 | nonlinear-cycle discriminator | C2 | WCC/RWR unavailable | scientific EVR 3/3 exhausted | EVR=3 exact; DBR≈3 reconstructed; FBR=no reconstructed |
| #93 | electron residual isolation | C2 | WCC/RWR unavailable | scientific EVR 3/3 exhausted | EVR=3 exact; DBR≈2 reconstructed; FBR=no reconstructed |
| #94 | scientific localization owner | not finalized in MET-14 | execution attribution shared with #98 | consumes #98 evidence; no independent metric block | issue-local EVR unavailable |
| #98 | execution/remedy verification campaign | not finalized in MET-14 | WCC/RWR unavailable | one-queue completion + scaling/remedy verification | EVR>=2 reconstructed lower bound; DBR≈1; FBR=yes reconstructed |

The DBR/FBR reconstructions above are descriptive and are **not** written into the canonical ledger because the corresponding MET-14 records were never prospectively frozen.

### 5.1 #86 -> #87 -> #88: evidence-first science improved runtime efficiency

This sequence is a strong positive process example.

```text
#86  reconstruct existing evidence        -> no new scientific EVR
#87  eliminate unsupported hypotheses     -> no new scientific EVR
#88  one predeclared final discriminator  -> exactly one scientific EVR
```

The result was a scientific decision:

```text
H1 severe conditioning favored
H2 residual-fidelity hypothesis disfavored
H3 formulation defect disfavored
Outcome B frozen
```

This pattern is functionally consistent with the intended RVR philosophy: research/evidence work narrowed the final runtime question before spending the final EVR.

However, RVR itself was not canonically recorded, so the report cannot quantify `RVR -> EVR` effectiveness. That is a measurement failure, not evidence that the strategy failed.

### 5.2 #92 and #93: bounded Issue size did not guarantee first-batch resolution

Both Issues respected the nominal three-EVR cap but consumed it fully:

```text
#92 EVR = 3/3
#93 EVR = 3/3
```

#92 disfavored globalization-only, scaling-only and characteristic-time-only explanations but ended with the primary electron residual owner unresolved.

#93 then used three more EVRs:

```text
J1  heavy/electron coupling not required
J2  diffusion/FV path selected
J3  boundary ownership disfavored + Jacobian inconsistency confirmed
```

This means the science chain respected per-Issue budgets while still spending six consecutive scientific EVRs before the assembled diffusion path was isolated.

The process lesson is important:

> Decomposition protects each Issue from unbounded runtime, but it can hide **cross-Issue cumulative EVR cost** unless the parent science campaign also tracks a campaign-level budget.

The previous metrics protocol correctly prevents copying child rounds into parent Issue metrics, but a separate campaign-level `unique scientific EVR` total is still needed for planning efficiency. Issue-local correctness and campaign-level user burden are different measurements.

### 5.3 #98: high-information one-queue completion improved diagnostic density

The later #98 completion campaign changed the shape of the experiment. Instead of one narrow hypothesis per user-return cycle, one QPX queue predeclared multiple mutually discriminating controls:

```text
time-only
full FVDiffusion at high/O(1) state
FVOrthogonalDiffusion controls
AD/Real direct Green-Gauss probes
two-term vs one-term reconstruction
offline RZ decomposition
constant-face interpolation audit
bounded Jacobian probes
```

The first completion return isolated:

```text
FV_GREEN_GAUSS_CELL_GRADIENT_CONSTANT_PRESERVATION
```

and the follow-up O(1) scaling counterfactual directly tested the production remedy. This is closer to the intended FBR behavior than #92/#93.

The substantive gain was not “more tests.” It was **more orthogonal discriminators per expensive QPX return**.

---

## 6. Carry-in Issue #31 R4 — lower-bound reconstruction

Issue #31 is the clearest example of why retrospective metric reconstruction cannot recover exact WCC after the fact.

The Issue initially contained zero-valued placeholder metrics, but those counters were not incremented during the substantial R4 campaign. At closure the body was rewritten around the scientific conclusion and no final MET-14 block was preserved.

### 6.1 Defensible lower bounds

Retained interaction history identifies at least these distinct user-local result-return stages:

```text
1. Q0 all-ground solved-Poisson control
2. QN0 quasi-neutral-reference control
3. first closed-feedback QF1
4. QF1 after uniform-O / actual-quasi-neutral IC correction
5. QF1 after QPX/QN Avogadro-constant convention alignment
6. QF2 local-charge relaxation discriminator
```

Therefore:

```text
EVR   >= 6   reconstructed lower bound
WCC   >= 6   reconstructed lower bound
T-WCC >= 6   reconstructed lower bound
```

These are lower bounds only. Earlier construction/runtime correction returns may increase the true values.

### 6.2 Assistant-side rework lower bound

At least two later user result returns were caused by avoidable experiment/instrumentation design corrections:

1. first QF1 C2 accounting substituted nominal `Q(t0)=0` instead of measuring actual discretized initial charge;
2. the spatial neutral-O perturbation made the actual discretized IC inconsistent with the intended quasi-neutral starting state, forcing IC redesign and rerun.

Thus:

```text
RWR >= 2 reconstructed lower bound
```

This excludes two other classes deliberately:

- the QPX `N_A=6.022e23` convention mismatch is not classified as assistant-side RWR merely because it required a rerun;
- the QF2 floating-point exact-equality pytest defect was caught and repaired inside the same assistant-side CI cycle before the user executed QF2, so it did not necessarily create an additional user round.

### 6.3 Why R4 cost remained high despite a good solver

The accepted R4 monolithic solver was not the main source of repeated user interaction. Final QF1/QF2 runs converged in two Newton iterations and charge conservation closed strongly.

The external-round cost came primarily from progressively freezing the experiment contract:

```text
Poisson construction semantics
material/block coverage
actual versus nominal initial charge
initial quasi-neutrality definition
physical constant convention
C1/C2 diagnostic normalization
final non-zero local response discriminator
```

This is a crucial distinction:

> R4's numerical architecture became reliable before the **measurement/initialization contract** became fully stable.

For future coupled-physics work, initial-state algebra, constant conventions, and conservation-observable execution times should be predeclared and checked before the first expensive feedback runtime.

---

## 7. #99-#111 and #114 architecture/refactor cohort

GitHub state shows fourteen completed technical Issues in this cohort after excluding the discarded #112/#113 connector checks.

The technical outputs are substantial: evidence/diagnose ownership separation, application/execution architecture cleanup, declarative experiment routing, dependency guards, regression/architecture CI and other structural changes were accepted.

However, a repository search finds **no complete MET-14 closure record** for this cohort.

### 7.1 What can be said

- the work was predominantly qpx-free architecture/refactor work;
- scientific P3 was generally frozen/not required;
- GitHub CI became a stronger assistant-side preflight surface;
- #114 explicitly reports two integration regressions discovered and fixed by CI before closure;
- final CI/architecture guards passed.

### 7.2 What cannot be said

Without WCC/T-WCC/RWR counters it is not valid to claim statistically that this cohort improved interaction efficiency relative to #77-#84.

A CI failure repaired before the user must return is **not** RWR. A CI failure that forces another user interaction may be RWR. That distinction is unavailable unless user-round events are recorded prospectively.

This cohort therefore demonstrates a process paradox:

```text
technical automation improved
measurement automation did not
```

The repository is now better at proving architecture correctness than at proving how efficiently that architecture work was delivered.

---

## 8. Comparison with the previous efficiency reports

### 8.1 Hypothesis from `2026-09-01_refactor_efficiency_trend.md`

The earlier report hypothesized that final-tree-ready batching could reduce user interaction while preserving rollback boundaries and closure quality.

Observed later evidence:

```text
#77-#84 exact cohort:
  strongly supports low interaction/rework after architecture convergence

science #86-#98:
  mixed; evidence-first stages save runtime, but #92/#93 still consume full budgets

#31 R4:
  not improved on total external-return count; contract refinement caused repeated reruns

#99-#114:
  technical CI automation appears strong, but canonical WCC/RWR measurement is missing
```

So the original batching hypothesis is **partially confirmed**, not universally confirmed.

### 8.2 Hypothesis from `2026-09-01_capability_architecture_batch_closure.md`

That report concluded that the main architecture bottleneck had shifted from raw Issue count to **validation-surface coupling**.

The #77-#84 cohort supports that conclusion: once the cleanup tasks shared stable architecture and validation surfaces, exact WCC/RWR collapsed to 1/0.

The science chain adds a second dimension:

> For scientific work the key variable is not just validation-surface coupling; it is **discriminator information density per expensive runtime return**.

#92/#93 used bounded but sequential hypotheses. #98 packaged orthogonal controls into one queue and isolated the owner more efficiently.

### 8.3 Improvement summary

| Area | Status | Evidence |
|---|---|---|
| post-convergence refactor WCC | **strongly improved** | exact #77-#84 WCC=1 each |
| post-convergence refactor RWR | **strongly improved** | exact RWR=0 for all #77-#84 |
| architecture scientific P3 avoidance | **improved/maintained** | cleanup/refactor work closes without scientific runtime |
| evidence-first scientific narrowing | **improved** | #86/#87 -> one #88 EVR |
| high-information diagnostic batching | **improved later** | #98 one-queue owner isolation |
| science first-batch resolution | **not consistently improved** | #92/#93 each consume 3/3 EVR |
| broad coupled-physics external-return cost | **not improved enough** | #31 `EVR>=6` lower bound |
| MET-14 recording completeness | **materially worsened** | overall 8/33 complete = 24.2% |
| closure quality | **remained strong** | scientific acceptance / CI / architecture guards remain strong |

---

## 9. Why the metrics did not stay reliable

### 9.1 MET-14 is normative, not transactional

`docs/protocols/metrics_closure.md` says a CLOSED technical work item must have a MET-14 record, but Issue closure is not mechanically blocked when the record is missing.

As execution became faster and more automated, the metric write became optional in practice.

### 9.2 `scientific EVR=0` became a substitute for canonical metrics

Many later refactor Issues carefully state:

```text
scientific EVR = 0
scientific P3 = 0
```

This is useful but incomplete. It does not record WCC/T-WCC/RWR/CLR, and it does not prove canonical EVR if a user-local guard return occurred.

The project had already documented this distinction in the previous efficiency reports, but the closure templates did not enforce it.

### 9.3 User-round metrics have no durable event source

WCC/T-WCC/RWR/CLR are inherently conversational metrics. After the conversation ends, GitHub retains outcomes but not enough information to distinguish:

```text
5 CI reruns inside one assistant turn
```

from:

```text
1 defect causing 1 extra user-return round
```

The metric system therefore cannot be fully reconstructed from repository state alone.

### 9.4 Parent/child science campaigns complicate issue-local attribution

#91/#92/#93/#94/#98 demonstrate the problem:

- child Issues own specific experiments;
- parent Issues own scientific acceptance;
- the same returned bundle may directly validate a science owner while being executed by a separate campaign Issue;
- copying all child EVR to a parent is prohibited;
- not recording attribution at result-return time makes later reconstruction ambiguous.

### 9.5 Closure bodies prioritized scientific truth over process accounting

This is understandable but incomplete. #31 is the strongest example: the final body accurately freezes the accepted monolithic R4 architecture and charge-conservation evidence, but the original metric counters were not maintained and the final MET-14 record is absent.

The technical result is strong; the efficiency evidence is weak.

---

## 10. Root causes of areas that did not improve

### 10.1 Science EVR remained high when discriminators were sequential

#92 and #93 show that a nominal `EVR<=3 per Issue` rule can still yield six sequential EVRs across a successor chain.

Cause:

```text
per-Issue budget control
without campaign-level cumulative budget / information-gain accounting
```

Remedy direction:

- keep issue-local EVR limits;
- additionally track unique campaign EVR across successor Issues;
- prefer one queue that measures mutually exclusive owner classes together when safe.

### 10.2 R4 repeated runs were caused by experiment-contract maturation

Cause:

```text
initial-state semantics not fully frozen
+ diagnostic execution timing incomplete
+ constant conventions not aligned before first closed-feedback run
```

The numerical solver itself was not the primary rework owner.

Remedy direction:

- precompute nominal and discretized initial charge separately;
- require INITIAL execution of conservation observables before feedback activation;
- freeze physical constants/conventions in one canonical source;
- remove purposeless IC perturbations before acceptance experiments;
- make control/positive-control pair design explicit before the first expensive run.

### 10.3 Metric completeness degraded because it had no machine owner

Cause:

```text
policy exists
but no closure artifact/schema/guard owns enforcement
```

This is the largest process debt discovered by this reconstruction.

---

## 11. Prospective metric architecture recommendation

This report does not implement a new metrics subsystem, but the next process change should make metric accounting **transactional rather than retrospective**.

### 11.1 Required state per active technical Issue

Maintain a machine-readable active record conceptually equivalent to:

```text
issue
work_id
complexity
state
WCC
T_WCC
RVR
EVR
DBR
RWR
CLR
FBR
reopened
scientific_P3_executions
metric_quality
```

`scientific_P3_executions` must remain separate from canonical EVR.

### 11.2 Event-time attribution

At each user round that advances an active Issue:

```text
increment WCC
classify technical/governance -> T-WCC
classify clarification -> CLR
classify assistant-caused repeat -> RWR
```

At each user-local returned validation/QPX result:

```text
attribute EVR immediately to the Issue(s) whose acceptance surface it directly validates
record run/bundle identity
record whether it is diagnostic or production-validation
```

Do not attempt to reconstruct this only at closure.

### 11.3 Closure gate

A technical Issue should not be considered metric-complete unless:

```text
MET-14 complete
or
explicit metric_quality = unavailable with reason
```

A recommended monitoring KPI is:

```text
complete MET-14 / CLOSED technical Issues
```

Target:

```text
100%
```

This audit found:

```text
24.2%
```

### 11.4 Campaign-level supplement

Issue-local accounting must remain canonical, but successor chains should additionally record:

```text
unique campaign user rounds
unique campaign EVR
unique diagnostic batches
Issues closed / campaign round
root-cause established after campaign EVR N
```

This prevents a chain of individually compliant `3/3 EVR` Issues from hiding high cumulative scientific cost.

### 11.5 RWR interpretation guard

Internal assistant-side CI/test failures are not automatically RWR.

Use:

```text
failure repaired before user must return
  -> internal repair; no RWR by itself

avoidable assistant defect forces another user round/result return
  -> RWR
```

This distinction is essential for interpreting #114-style CI repair versus #31-style user reruns.

---

## 12. Immediate application to the next work — #27 surface reaction

#27 is currently ACTIVE with an initial metric block already present. That is a good restart point for prospective instrumentation.

Do not wait until surface-reaction closure to reconstruct its efficiency.

From the next user round onward, preserve exact issue-local counters while Phase 0/Phase A progresses:

```text
WCC / T-WCC
RVR for source/species/reference parity decisions
EVR only when user-local execution results return
DBR for distinct wall-reaction diagnostic batches
RWR for assistant-caused repeat rounds
CLR
FBR
```

Surface-reaction development is also a good test of whether RVR improves scientific efficiency because source parity, species mapping and wall-flux semantics can be resolved before expensive coupled QPX runs.

---

## 13. Final assessment

### What clearly improved

1. **Post-convergence architecture cleanup efficiency** improved substantially.
   - exact mean WCC `5.6 reconstructed -> 1.0 exact` relative to the prior comparable technical-child cohort;
   - exact mean RWR `1.0 reconstructed -> 0`;
   - no external user-local validation cost was required for #77-#84.

2. **Assistant-side validation maturity** improved.
   - more errors are caught by current-tree census/CI before they become user-return cycles;
   - #114 is evidence that integration defects can be repaired before closure without automatically becoming RWR.

3. **Scientific diagnostic design improved later in the R3 chain.**
   - #86/#87 avoided premature runtime;
   - #98 packed orthogonal controls into one completion queue and achieved narrow owner isolation.

4. **Closure quality remained high.**
   - lower interaction cost did not come from weakening scientific/architecture acceptance.

### What did not improve enough

1. **Scientific external-return cost** remained high in sequential diagnosis.
   - #92/#93 together spent six scientific EVRs before narrow ownership;
   - #31 R4 has a defensible `EVR>=6` lower bound.

2. **First-batch resolution is still inconsistent.**
   - #92/#93 demonstrate that bounded Issues can still require successor Issues;
   - #98 shows a better pattern, but not yet enough exact samples exist for a rate comparison.

3. **Metric recording regressed badly.**
   - only `8/33 = 24.2%` of the post-snapshot reconstruction population has a complete durable MET-14 record.

### Root cause of the metric regression

The project improved technical automation faster than it automated process measurement.

```text
technical work:
  increasingly machine-checked

metrics:
  still manually finalized from conversational state
```

That asymmetry explains why the repository now contains strong scientific/CI closure evidence but insufficient exact WCC/T-WCC/RWR statistics.

### Process decision

The next optimization should not be another retrospective reconstruction. It should be:

> **make MET-14 state update part of the work transaction itself, and make metric completeness a closure gate.**

Until that is done, report exact cohort statistics separately, retain reconstructed/lower-bound science values visibly, and do not pool missing-field Issues into medians/correlations.

---

## Appendix A — issue-level evidence-quality register

| Issue(s) | Work class | Metric evidence status | Notes |
|---|---|---|---|
| #77 | cleanup/refactor | **exact** | full MET-14 in closure body |
| #78 | cleanup/refactor | **exact** | full MET-14 in closure body |
| #79 | cleanup/refactor | **exact** | full MET-14 recovered from closure comment |
| #80 | cleanup/refactor | **exact** | full MET-14 in closure body |
| #81 | cleanup/refactor | **exact** | full MET-14 in closure body |
| #82 | cleanup/refactor | **exact** | full MET-14 recovered from closure comment |
| #83 | cleanup/refactor | **exact** | full MET-14 in closure body |
| #84 | cleanup/refactor | **exact** | full MET-14 recovered from closure comment |
| #86 | science evidence audit | partial | scientific EVR=0; WCC/T-WCC/RWR unavailable |
| #87 | science hypothesis audit | partial | scientific EVR=0; WCC/T-WCC/RWR unavailable |
| #88 | science discriminator | partial | one exact scientific EVR; other MET-14 fields unavailable |
| #89 | post-science refactor | partial | scientific EVR=0; canonical round metrics unavailable |
| #90 | architecture/test separation | partial | scientific EVR=0; canonical round metrics unavailable |
| #91 | R3 acceptance | partial | final acceptance return exists; child metrics not inherited |
| #92 | science discriminator | partial | EVR=3 exact; remaining canonical metrics incomplete |
| #93 | science discriminator | partial | EVR=3 exact; remaining canonical metrics incomplete |
| #94 | science localization owner | partial/ambiguous attribution | #98 owns execution campaign; no final MET-14 |
| #98 | execution/remedy campaign | reconstructed lower-bound | completion + remedy verification; no final MET-14 |
| #99-#111 | architecture/refactor | unavailable full MET-14 | technical/CI evidence exists, canonical round metrics absent |
| #114 | declarative experiment gateway | unavailable full MET-14 | CI PASS after two internally repaired integration regressions |
| #31 | R4 coupled-physics carry-in | **lower-bound** | EVR/WCC >=6, RWR>=2; exact counters unavailable |

## Appendix B — statistical-use rule

For future analysis:

```text
exact cohort
  -> may be used for exact means/medians/rates

reconstructed cohort
  -> directional/process comparison only unless reconstruction basis is frozen

lower-bound cohort
  -> cost floor only; never pool as exact mean

unavailable cohort
  -> metric-completeness denominator, not performance-statistic numerator
```

This rule prevents the current metric debt from creating false precision.
