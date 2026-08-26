# Work Closure Validator

**Status:** living guide  
**Scope:** MOOSE-team work-item execution efficiency and validation sufficiency  
**Objective:** reach a validated CLOSED state with fewer user↔MOOSE interaction rounds without weakening technical acceptance criteria.

## 1. Primary metric — WCC

### WCC: Work Closure Chat Count

`WCC` is the number of user interaction rounds required from the start of one defined work item until that work item reaches `CLOSED`.

```text
WCC = count(user interaction rounds from WORK_START through WORK_CLOSE)
```

An interaction round is counted when the user must send a message for the same work item before progress can continue. Assistant tool calls, internal analysis, and progress updates do not add to WCC.

WCC intentionally includes approval/resume messages and user-executed validation replies because they are part of the actual interaction burden experienced by the user.

### Work boundaries

A work item starts when:

- a concrete objective is accepted for execution; and
- the expected closure condition can be stated.

A work item closes only when:

- the technical acceptance criteria pass;
- required canonical validation is complete;
- the production decision/fix is recorded when relevant; and
- no known blocking hold point remains for that work item.

Do not close a work item merely because a solver process returns success.

## 2. Diagnostic metrics

WCC is the headline KPI. The following metrics explain why WCC is high or low.

### T-WCC: Technical Work Closure Chat Count

Number of rounds containing technical evidence, decisions, tests, failures, fixes, or validation results.

Governance-only messages such as `approve`/`resume` are excluded from T-WCC but remain included in total WCC.

```text
T-WCC <= WCC
```

### EVR: External Validation Rounds

Number of times the user must execute a test/bundle in the external QPX runtime and return results.

```text
EVR = count(user-run validation result returns)
```

EVR is especially important because every avoidable sequential diagnostic batch creates another chat round.

Target: maximize useful discrimination per EVR.

### RWR: Rework Rounds

Number of additional rounds caused by an avoidable assistant-side artifact/configuration error, such as:

- wrong relative executable path;
- missing required test file;
- incorrect runner logic;
- confounded diagnostic setting;
- checker that reports only process PASS/FAIL when numeric invariants were required.

```text
RWR = count(rounds whose primary purpose is correcting avoidable prior delivery)
```

Target: `RWR = 0`.

### CLR: Clarification Rounds

Number of rounds spent obtaining information that could not be inferred, retrieved, or safely resolved from the current work context.

A clarification is not automatically waste. Track it so repeated clarification patterns can be engineered out through better work-start contracts and context retrieval.

### DBR: Diagnostic Batch Rounds

Number of distinct diagnostic batches that required external execution before root cause was established.

The preferred MOOSE-team pattern is:

```text
DBR <= 2

Round 1: broad parallel hypothesis triage
Round 2: targeted confirmation, only if needed
```

### FBR: First-Batch Resolution

Boolean metric:

```text
FBR = true
```

when the first diagnostic batch provides enough evidence to identify the root-cause class and proceed directly to production-fix validation.

This does not require the final production setting to be selected in the first batch.

## 3. Quality guardrails

The team must never reduce WCC by weakening verification.

A work is eligible for efficiency comparison only if its closure satisfies the applicable quality gates:

- canonical regressions pass;
- physical invariants pass;
- infrastructure failures are not mislabeled as physics results;
- root-cause claims have independent evidence when required;
- production fixes are validated across a representative regime matrix when applicable.

Therefore:

```text
minimize WCC subject to closure-quality constraints
```

not:

```text
minimize WCC at any cost
```

## 4. Validator sufficiency audit before execution

The Validator is responsible not only for scoring work after execution, but for deciding whether the proposed test set is capable of supporting the intended conclusion.

Before a batch is accepted for external execution, the Validator should answer:

```text
What claim will PASS establish?
Which failure classes are covered?
Which plausible failure classes remain uncovered?
Can implementation and checker share the same bug and false-PASS?
Does the production code path itself get exercised?
Are negative controls/mutations present to prove checker sensitivity?
Are harness/construction failures separated from physics failures?
```

A batch is insufficient if it validates only a test-side model while leaving the production parser/resolver/solver path unchecked.

### Validator acceptance classes

Use explicit decisions such as:

```text
TEST_SET_INSUFFICIENT
STATIC_PIPELINE_PASS_ONLY
PRODUCTION_PATH_UNVALIDATED
VALIDATOR_SELFTEST_UNVALIDATED
BATCH_ACCEPTED_FOR_EXECUTION
```

## 5. Mandatory construction-preflight expectation

For MOOSE/QPX executable bundles, the Validator should require preflight coverage before full runtime:

```text
P0 checker self-test / mutation controls
P1 static construction checks
P2 qpx-opt --check-input
P3 full physics runtime
```

Static construction checks should include, when applicable:

- duplicate objects/blocks;
- reserved parser symbols;
- missing functor providers;
- generated dot-functor naming;
- missing files or required outputs;
- alias/identifier integrity.

Example: if `w_O_state` is provided with `define_dot_functors = true`, the generated time derivative is `dw_O_state_dt`; a request for `dO_state_dt` should be detected before a full solve.

Construction failures are harness/configuration evidence, never physics FAIL.

## 6. Engineering interpretation

At closure, classify excess interaction cost.

| Pattern | Likely process defect | Engineering response |
|---|---|---|
| high EVR, low RWR | diagnostics too sequential | increase parallel hypothesis coverage and batch information gain |
| high RWR | artifact/test delivery quality problem | strengthen pre-delivery static checks and path/runtime handling |
| high CLR | weak work-start contract/context retrieval | define acceptance criteria and retrieve context earlier |
| DBR > 2 | incomplete initial hypothesis set or weak discriminators | improve symptom→hypothesis→test mapping |
| low WCC but failed/reopened work | premature closure | strengthen closure gates; do not count as successful efficiency |
| repeated same symptom across incidents | knowledge not being reused | promote symptom→batch mapping into the problem-solving protocol |

## 7. Work-close record

Every CLOSED technical work item should append one record to the efficiency ledger.

Required fields:

```text
Work ID
Work title
Complexity class
WCC
T-WCC
EVR
DBR
RWR
CLR
FBR
Reopened? yes/no
Root-cause class
Primary process lesson
```

### Complexity class

Use a coarse class only to avoid comparing trivial edits directly with multi-physics incidents:

```text
C1 = local/single-object change
C2 = one subsystem or bounded regression
C3 = coupled multi-subsystem incident
C4 = cross-layer architecture/integration incident
```

Do not use complexity to hide poor efficiency. Report raw WCC first; complexity is only a comparison dimension.

## 8. Optimization targets

Initial targets for MOOSE technical incidents:

```text
RWR = 0
DBR <= 2
EVR <= 2 for a normal C2/C3 incident when the runtime must be executed by the user
FBR should increase over time
median WCC should decrease within each complexity class
```

Do not set a hard WCC target until enough closed work items exist to establish a baseline distribution.

## 9. Learning loop

At every work closure:

```text
close work
  -> record WCC metrics
  -> identify largest interaction-cost component
  -> extract one process improvement if material
  -> update diagnostic protocol / validator when reusable
  -> compare future similar work against the historical baseline
```

The validator is therefore not only a scorekeeper. Its purpose is to make interaction efficiency and test sufficiency engineering variables.

## 10. M5 baseline policy

The current M5 solved-potential ion-wall incident is the first designated baseline work item.

Do not assign its final WCC until the canonical promotion validation passes and M5 is formally CLOSED.

At closure, reconstruct and record the interaction metrics from the incident history/conversation evidence as accurately as possible. If an exact historical count cannot be established, record the count as `estimated` rather than inventing precision.

The main known M5 process lessons already identified are:

- initial diagnostics were too sequential;
- convergence sensitivity should have been in the first broad batch;
- early forced-iteration evidence lacked the numeric invariant outputs required for correct interpretation;
- at least one bundle required a relative-path correction;
- later parallel hypothesis batches substantially reduced additional rounds.
