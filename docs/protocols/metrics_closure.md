# Metrics and Closure Protocol

**Status:** canonical procedure  
**Scope:** issue-local efficiency measurement, closure quality, and retrospectives  
**Purpose:** measure interaction cost without hiding research investment or weakening validation.

## MET-01 — Work boundary

A bounded work item starts when a concrete objective and closure claim are accepted for execution. It closes only when the technical acceptance criteria, required canonical validation, production decision/fix, and blocking hold points for that bounded item are resolved.

Do not close a work item merely because a solver returns success.

## MET-02 — WCC

`WCC` (Work Closure Chat Count) counts user interaction rounds attributable to the bounded work item from start through closure.

```text
WCC = count(user interaction rounds from WORK_START through WORK_CLOSE)
```

Approval/resume messages count when they are part of the interaction burden.

## MET-03 — T-WCC

`T-WCC` counts rounds containing technical evidence, tests, decisions, failures, fixes, or validation results. Governance-only rounds are excluded.

```text
T-WCC <= WCC
```

## MET-04 — RVR

`RVR` (Research Validation Rounds) counts attributable Researcher->Validator evidence rounds where a material source/model/provenance/representation question can change implementation or acceptance and receives an explicit recorded validation decision.

Examples that count:
- source/provenance research followed by acceptance;
- literature/model research followed by benchmark acceptance;
- source-state dependency research followed by representation-adequacy decision.

Examples that do not count:
- unvalidated lookup;
- routine constant lookup with no decision impact;
- pure runtime debugging;
- governance-only discussion.

Historical RVR may be backfilled only from explicit evidence and must be marked `reconstructed` or `estimated` where exact prospective counting was not in place.

## MET-05 — EVR

`EVR` (External Validation Rounds) counts user-local QPX execution result returns attributable to the work item.

The prospective bounded-work target is normally `EVR <= 3` under `problem_solving.md`.

## MET-06 — DBR

`DBR` (Diagnostic Batch Rounds) counts distinct external diagnostic batches required before root-cause class establishment.

Target:

```text
DBR <= 2
```

Round 1 should be broad high-information discrimination; Round 2 targeted confirmation only if needed.

## MET-07 — RWR

`RWR` (Rework Rounds) counts additional user rounds caused primarily by avoidable assistant-side artifact/configuration/analyzer defects.

Examples:
- wrong executable path handling;
- missing required file;
- incorrect runner logic;
- duplicate generated block;
- unsupported parameter inserted by the harness;
- checker/analyzer defect or false classification.

Target:

```text
RWR = 0
```

## MET-08 — CLR

`CLR` (Clarification Rounds) counts rounds spent obtaining information that could not be safely inferred or retrieved from current context/resources.

Repeated clarification patterns should be converted into stronger issue-start contracts or retrieval rules.

## MET-09 — FBR

`FBR` (First-Batch Resolution) is true when the first diagnostic batch provides enough evidence to establish the root-cause class and proceed directly to production-fix validation.

It does not require final closure in the first batch.

## MET-10 — Prospective EVR budget

For each bounded work package using the 3-EVR protocol, record separately from lifetime issue metrics:

```text
Prospective EVR budget: N/3 used
```

Historical EVRs remain in lifetime metrics. A pause/resume may begin a fresh prospective budget only when the bounded work package is explicitly re-framed; do not erase historical cost.

## MET-11 — Issue-local accounting

Metrics are issue-local/bounded-work-local. Do not copy child issue technical/research rounds into the parent metrics merely because the parent depends on the child.

Governance/status synchronization does not consume a physics work cycle unless it contains attributable technical work for that item.

## MET-12 — Complexity class

Use a coarse comparison class:

```text
C1 = local/single-object change
C2 = one subsystem or bounded regression
C3 = coupled multi-subsystem incident
C4 = cross-layer architecture/integration incident
```

Report raw metrics first; complexity is only a comparison dimension.

C4 work should normally be decomposed before runtime under `PS-15`; use C4 primarily for planning/tracking when several serial closure claims are present.

## MET-13 — Closure quality guardrail

Efficiency comparisons are valid only when closure quality is preserved:

```text
canonical regressions pass
physical invariants pass
construction failures not mislabeled as physics
root-cause claims independently supported when required
actual production path validated where applicable
negative controls/checker sensitivity demonstrated
```

Optimization objective:

```text
minimize WCC/EVR subject to closure-quality constraints
```

## MET-14 — Work-close record

Every CLOSED technical bounded work item should append a record containing:

```text
Work ID
Work title
Complexity
WCC
T-WCC
RVR
EVR
Prospective EVR budget used / 3 when applicable
DBR
RWR
CLR
FBR
Reopened? yes/no
Root-cause class
Primary process lesson
Closure-quality note
```

## MET-15 — Retrospective for work exceeding three EVRs

Classify every excess round into at least one reusable cause:

```text
missing research gate
missing known-good control
sequential diagnostics
non-independent tests
harness construction defect
analyzer/checker defect
missing mutation/self-test
scope too broad
new independent incident
unavoidable external dependency
```

Then convert reusable causes into `problem_solving.md`, `validation.md`, or `docs/knowledge/` rather than adding another overlapping guide.

## MET-16 — RVR effectiveness analysis

RVR is an upstream investment, not a target to minimize. Across comparable complexity/work types, analyze:

```text
(RVR, EVR)
(RVR, DBR)
(RVR, RWR)
```

A repeated pattern of higher well-targeted RVR with lower EVR/DBR/RWR may support the hypothesis that early research validation reduces downstream iteration. Do not infer causality from one work item.

## MET-17 — Reporting order

Active issue metric blocks use this canonical order:

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

Add prospective `EVR budget N/3` immediately after the lifetime metric block for a currently active bounded work package.

## MET-18 — Learning loop

At closure:

```text
close work
-> record metrics
-> identify largest interaction-cost component
-> compare RVR against EVR/DBR/RWR for similar work
-> extract one material process improvement
-> update one canonical owner only
-> compare future similar work against the baseline
```

The purpose of the metrics is to turn problem-solving efficiency and research quality into measurable engineering variables.

## MET-19 — Decomposed-parent closure

When a large parent is intentionally replaced by smaller bounded successor issues, close the parent with closure type `DECOMPOSED_PARENT` rather than pretending its unfinished downstream physics is complete.

Accounting rules:

```text
preserve the parent's lifetime WCC/T-WCC/RVR/EVR/DBR/RWR/CLR/FBR
record validated work already completed under the parent
record every successor issue and dependency edge
do not copy parent metrics into successors
successors begin at WCC=0/EVR=0 while PLANNED
governance-only decomposition does not increment parent technical metrics
```

GitHub `state_reason=not_planned` is appropriate when the original remaining scope will no longer be executed inside that issue. The issue body/final comment must state explicitly that closure is due to decomposition, not technical completion of the successor physics.

This closure type is excluded from comparisons of technically completed bounded issues unless the analysis is specifically about scope-sizing/decomposition efficiency.