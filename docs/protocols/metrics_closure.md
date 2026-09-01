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

Then route reusable lessons through the canonical rule-reuse gate in `PROTOCOL_INDEX.md`; do not add another overlapping guide.

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
-> classify incident learning status when applicable (MET-20)
-> evaluate prevention-learning KPIs when sufficient data exists (MET-21)
-> apply the enforcement-promotion decision when a known failure recurs (MET-22)
-> extract one candidate process lesson
-> apply the canonical rule-reuse gate in PROTOCOL_INDEX.md
-> change one existing canonical owner only when needed
-> compare future similar work against the baseline
```

The purpose of the metrics is to turn problem-solving efficiency and research quality into measurable engineering variables without growing duplicate rules.

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

## MET-20 — Incident novelty and enforcement classification

Every incident included in prospective incident-learning statistics must carry two independent classifications:

```text
Root-cause class = what failed
Learning status  = why the existing operating system did or did not prevent it
```

Use exactly one primary learning status:

```text
NOVEL
  No existing canonical rule, protocol trigger, reusable knowledge entry, or machine gate materially covered the root cause before the incident.

KNOWN_BUT_NOT_ENFORCED
  The failure class was already covered conceptually, but prevention depended on a human/agent remembering or manually applying the rule; no effective mandatory gate blocked the bad state.

KNOWN_AND_GATE_BYPASSED
  A relevant mandatory gate existed, but the affected path did not invoke it, was grandfathered/exempted incorrectly, or routing/trigger logic failed to select it.

GATE_DEFECT
  The intended gate executed but accepted the invalid state, rejected the valid state, used the wrong semantic equivalence/aggregation/state identity, or otherwise malfunctioned.

ENVIRONMENT_ESCAPE
  The canonical rule/gate was sound for the declared execution environment, but environment/build/path/cache/runtime identity caused the failure to escape or be misclassified.
```

Do not infer a learning status from the symptom alone. Evidence must identify the pre-incident control state: what rule existed, whether its trigger applied, whether a machine-enforced gate existed, whether the gate ran, and whether the gate behaved correctly.

When evidence cannot discriminate the statuses, record:

```text
Learning status = UNRESOLVED
```

`UNRESOLVED` is excluded from recurrence/enforcement-rate denominators until resolved. Do not force historical aggregate data into one of the prospective classes without incident-level evidence.

The learning classification is orthogonal to the technical root-cause taxonomy. For example, two `Solver Tolerance Floor` incidents may be classified differently if one predates the numerical-contract gate (`NOVEL`) and another occurs because a required gate was not routed (`KNOWN_AND_GATE_BYPASSED`).

## MET-21 — Prevention-learning KPIs

Incident-learning analysis must distinguish raw incident volume from recurrence of already-known failure classes. For a reporting window with incident-level classification, report at least:

```text
Incident rate             = incidents / bounded work items
Known recurrence rate     = known-class incidents / classified incidents
Pre-execution catch rate  = known invalid states blocked before P2/P3 / all known invalid states observed
Gate-bypass rate          = KNOWN_AND_GATE_BYPASSED / classified incidents
Gate-defect rate          = GATE_DEFECT / classified incidents
Enforcement coverage      = machine-enforced applicable controls / applicable known controls
Novel-class share         = NOVEL / classified incidents
```

For `Known recurrence rate`, the known-class numerator is:

```text
KNOWN_BUT_NOT_ENFORCED
+ KNOWN_AND_GATE_BYPASSED
+ GATE_DEFECT
+ ENVIRONMENT_ESCAPE
```

Interpretation:

```text
incident count stable + known recurrence falling + novel share rising
  -> evidence that the system is learning while encountering new failure modes

incident count stable/high + known recurrence high
  -> existing knowledge is not being converted into effective prevention

KNOWN_BUT_NOT_ENFORCED high
  -> convert semantic/manual rules into mandatory executable invariants where practical

KNOWN_AND_GATE_BYPASSED high
  -> fix routing, trigger coverage, schema migration, or execution-path integration

GATE_DEFECT high
  -> validator/control system is itself a material defect source; strengthen mutation/self-tests

ENVIRONMENT_ESCAPE high
  -> strengthen runtime identity/preflight and separate environment evidence from physics evidence
```

Do not compare percentages across time unless the denominator and classification coverage are reported. A root-cause percentage snapshot alone is not evidence that total incident frequency increased or decreased.

Prospective incident records and aggregate snapshots live under `docs/metrics/incidents/`. Historical root-cause snapshots remain immutable observations; add learning-status annotations only when incident-level evidence supports them.

## MET-22 — Enforcement promotion policy

The learning loop is incomplete when a known failure is only documented again. A recurrence must produce an explicit prevention decision.

### Promotion triggers

A mandatory **Enforcement Promotion Review (EPR)** is triggered when any of the following is true:

```text
1. the same semantic failure class reaches its second classified known recurrence after canonical coverage already existed;
2. a single known failure has high execution/rework cost and a deterministic low-risk precondition can be checked before the expensive stage;
3. MET-21 shows a material concentration of KNOWN_BUT_NOT_ENFORCED, KNOWN_AND_GATE_BYPASSED, GATE_DEFECT, or ENVIRONMENT_ESCAPE for one control surface.
```

The second-recurrence trigger is based on semantic failure identity, not textual symptom identity. Do not reset the count because the same underlying control failure appears under a different input, solver, object name, or message spelling.

A first known recurrence still requires the MET-20 classification and a targeted remediation decision; it does not automatically require a new gate when the evidence is insufficient or the gate would create a larger validation failure surface.

### Required EPR decision

Record exactly one primary outcome:

```text
PROMOTE_TO_MACHINE_GATE
  Convert a manual/semantic control into a mandatory executable invariant on every applicable path.

STRENGTHEN_TRIGGER_OR_ROUTING
  A gate already exists; make applicability/routing/schema migration/path integration mandatory so it cannot be silently skipped.

REPAIR_GATE_AND_SELFTEST
  The intended gate ran but was semantically wrong or insufficient; repair it and add a discriminating self-test/mutation.

HARDEN_ENVIRONMENT_IDENTITY
  Make executable/build/path/cache/environment identity observable and preflighted before downstream classification.

IMPOSSIBLE_BY_CONSTRUCTION
  Remove the invalid state from the generator/schema/ownership model when this is simpler and safer than adding another validator.

RETAIN_MANUAL_WITH_JUSTIFICATION
  Keep a manual/semantic control only when machine enforcement is not sufficiently observable, would create unacceptable false positives, or would add more failure surface than it removes.

DEFER_PENDING_EVIDENCE
  Evidence is not yet sufficient to select a safe prevention mechanism. Define the missing discriminator; do not create a speculative gate.
```

`RETAIN_MANUAL_WITH_JUSTIFICATION` and `DEFER_PENDING_EVIDENCE` must record the reason. They are decisions, not exemptions from future recurrence accounting.

### Gate-promotion acceptance criteria

Prefer promotion only when the proposed control is:

```text
observable      -> the invalid precondition/runtime state can be measured reliably
specific        -> it rejects the intended failure class without silently redefining the scientific claim
early placed    -> it blocks the defect at the earliest practical stage, preferably P0/P1 before expensive P2/P3 execution
testable        -> positive and negative/mutated controls can prove sensitivity
owned           -> one canonical code/protocol owner and one applicability trigger are identifiable
fail-closed     -> uncertainty cannot silently become physics PASS
lower-risk      -> expected prevention benefit exceeds the new validator/harness failure surface
```

A promoted machine gate is not accepted merely because it detects the historical reproducer. It must include an applicable-path test plus at least one mutation/negative control that demonstrates the material defect is rejected.

### Prevention maturity

Track the strongest achieved prevention level for a reusable known failure:

```text
DOCUMENTED
  semantic rule/knowledge exists, but application depends on human/agent behavior

TRIGGERED
  applicability is explicitly routed and cannot be omitted without a contract violation

MACHINE_CHECKED
  a mandatory executable gate rejects the invalid state

MUTATION_TESTED
  the gate carries positive/negative or mutation evidence proving sensitivity

IMPOSSIBLE_BY_CONSTRUCTION
  the canonical construction path cannot represent the invalid state under its declared contract
```

Do not promote maturity based on documentation wording alone. `MACHINE_CHECKED` and above require executable evidence on the applicable path.

### Learning-status to prevention action

Use the MET-20 status to choose the first remediation surface:

```text
KNOWN_BUT_NOT_ENFORCED
  -> review PROMOTE_TO_MACHINE_GATE or IMPOSSIBLE_BY_CONSTRUCTION

KNOWN_AND_GATE_BYPASSED
  -> STRENGTHEN_TRIGGER_OR_ROUTING

GATE_DEFECT
  -> REPAIR_GATE_AND_SELFTEST

ENVIRONMENT_ESCAPE
  -> HARDEN_ENVIRONMENT_IDENTITY

NOVEL
  -> establish the reusable semantic owner first; do not jump directly to a broad gate without defining the failure contract
```

### Validator-complexity guardrail

The objective is prevention, not maximum gate count. The validation/harness system is itself a failure surface. Therefore:

```text
one recurring failure != one new standalone checker by default
```

Prefer, in order where semantics permit:

```text
invalid state impossible by construction
-> extension of an existing canonical preflight/gate
-> shared reusable invariant
-> new dedicated gate only when no existing owner can safely absorb it
```

Apply the `PROTOCOL_INDEX.md` rule-reuse gate before creating another rule, checker, or protocol owner.

### Recurrence after promotion

After an enforcement decision has been implemented:

```text
same invalid state + gate not invoked
  -> KNOWN_AND_GATE_BYPASSED

same invalid state + gate invoked but wrong result
  -> GATE_DEFECT

same invalid state blocked by the gate before expensive execution
  -> prevention success; count toward pre-execution catch rate, not incident recurrence
```

A known failure is considered prevention-closed only when the chosen enforcement action has applicable-path evidence and its prevention maturity is recorded in the incident-learning ledger or linked evidence.