# 3-EVR Problem-Solving Protocol

**Status:** living guide  
**Scope:** MOOSE/QPX technical issues and bounded child work items  
**Objective:** close each bounded technical issue with at most three user-local external validation rounds whenever practical, without weakening technical acceptance criteria.

## 1. Primary operating target

The protocol targets the external validation burden, not research effort itself.

```text
EVR budget <= 3

EVR #1 = broad discrimination
EVR #2 = targeted confirmation / fix validation
EVR #3 = canonical production regression
```

Supporting targets:

```text
DBR <= 2
RWR = 0
CLR ~= 0
```

`RVR` is not minimized by itself. Research validation is an upstream investment that may be increased when it reduces downstream EVR, DBR, RWR, or reopening risk.

The quality constraint is mandatory:

```text
minimize EVR subject to closure-quality constraints
```

not:

```text
minimize EVR by weakening validation
```

## 2. Work-boundary rule

The three-EVR budget applies to one **bounded issue or child issue**, not necessarily an entire multi-physics program.

If a parent issue contains separable source/model, transport, framework, and coupled-integration uncertainties, split them into bounded work items before spending external runtime rounds.

Example:

```text
Parent C4 issue
  -> source/model child            <= 3 EVR
  -> transport/data child          <= 3 EVR
  -> construction/framework child  <= 3 EVR
  -> coupled integration child     <= 3 EVR
```

If EVR #3 is reached without a defensible root-cause/fix/closure decision, do not default to EVR #4. First reassess the work boundary and Phase-0 preparation.

## 3. Phase 0 — pre-runtime problem framing

Phase 0 consumes no EVR. It may consume RVR.

Before constructing a user-local runtime batch, the Manager must state:

```text
Claim
  What exact statement will close this bounded work item?

Unknown classes
  source/model?
  representation?
  framework contract?
  implementation?
  environment/build?
  harness/analyzer?

Dependencies
  Which hypotheses are prerequisites for others?

Evidence
  What quantity/signature separates the hypotheses?

Known-good control
  What previously accepted case should still pass?

Failure budget
  Which likely failure classes can be discriminated in EVR #1?
```

### Research gate

Route source/model/provenance/representation uncertainty through:

```text
Manager
  -> Researcher: establish source truth / model state dependencies
  -> Validator: decide adequacy / applicability / acceptance
```

Count one `RVR` when this produces a material engineering decision.

A source/model-heavy issue should not reach EVR #1 while a high-impact research question remains unresolved if that question can be answered offline.

## 4. Test-independence audit

Before external execution, the Validator must inspect the proposed tests as a dependency graph.

Required question:

```text
If T1 fails, do T2/T3 still provide independent information?
```

If the answer is no, dependent descendants must not be presented as parallel discriminators.

Bad pattern:

```text
J1
 -> J2
    -> J3
       -> J4
```

If J1 fails, J2-J4 may provide no new information.

Preferred pattern:

```text
candidate
  -> known-good comparison
  -> primitive minimal reproducer
  -> alternate implementation/control
  -> environment/build fingerprint
```

The first batch should maximize **independent information gain**, not raw test count.

## 5. EVR #1 — broad discrimination

EVR #1 is successful when it identifies the root-cause class or reduces the issue to one dominant class that can be fixed/confirmed directly.

Every external bundle should include, when applicable:

```text
P0 validator/checker mutation self-test
P1 static construction checks
P2 qpx-opt --check-input
P3 candidate runtime only after P0-P2

exact known-good control
candidate case
independent oracle/reference
predeclared fail-branch discriminators
environment/build fingerprint
```

### Mandatory known-good control

For any regression/integration problem with a historical accepted case:

```text
candidate FAIL + control PASS -> candidate-specific class
candidate FAIL + control FAIL -> environment/build/global class
```

Environment fingerprint should record at least the executable realpath and enough build/runtime identity to determine whether the historical control is being executed in the same effective environment.

### EVR #1 decision classes

The batch should end in an explicit class such as:

```text
PASS
SOURCE_MODEL_FAIL
REFERENCE_DATA_FAIL
REPRESENTATION_ADEQUACY_FAIL
HARNESS_OR_CONSTRUCTION_FAIL
ENVIRONMENT_OR_BUILD_FAIL
IMPLEMENTATION_PARITY_FAIL
PHYSICS_MODEL_FAIL
```

`UNKNOWN_FAIL` after EVR #1 is treated as a batch-design warning and requires Validator review before another external run.

## 6. EVR #2 — targeted confirmation / fix validation

EVR #2 may change only the diagnosed failure class unless new evidence falsifies the diagnosis.

Pattern:

```text
one diagnosed class
  -> one targeted fix
  -> direct regression
  -> negative control / mutation proving detector sensitivity
  -> representative original case
```

Do not simultaneously change unrelated physics coefficients, timestep, solver tolerance, parser syntax, environment, and acceptance thresholds.

If EVR #2 falsifies the EVR #1 diagnosis, route through the predeclared fail branch or return to Phase 0. Do not stack speculative fixes.

## 7. EVR #3 — canonical production regression

EVR #3 is not a debugging batch. It is the canonical closure regression.

Include:

```text
actual production path
representative regime matrix
boundary/off-grid or edge case when relevant
physical/analytic invariant
negative control / mutation self-test
known-good non-regression case
```

A PASS must satisfy the original closure claim, not merely return `rc=0`.

If EVR #3 fails:

```text
A. return to Researcher -> Validator if a source/model assumption is now doubtful;
B. split the work into a narrower child issue if the failure is a new independent class;
C. open a reusable incident if the failure is framework/harness/environmental;
D. do not automatically consume EVR #4 under the same unchanged issue boundary.
```

## 8. Mandatory pre-runtime harness defenses

The default static/preflight layer should catch failure modes observed in prior MOOSE/QPX work before the user executes the solver.

Minimum applicable checks:

- duplicate MOOSE blocks/objects;
- reserved ParsedFunctor symbols such as `x,y,z,t`;
- missing functor providers;
- generated dot-functor naming mismatches;
- missing files and outputs;
- stale-output contamination;
- invalid alias/pair keys;
- impossible charge collapse;
- analyzer treatment of initialization rows;
- unsupported input parameters;
- runner executable path resolution using `realpath`.

A harness or analyzer defect discovered in user-local runtime increments RWR and should result in a new P0/P1 regression before the next external round.

## 9. Analyzer contract

The analyzer is part of the test harness and must be validated like production code.

Before external delivery, require:

```text
positive control -> accepted
negative/mutated control -> rejected
construction fail -> not mislabeled physics fail
runtime success + metric fail -> exact metric failure reported
initialization-only rows -> excluded or explicitly classified when non-physical
```

Direct target evidence takes precedence over supporting environment smoke tests. A supporting diagnostic must not override a direct PASS unless the acceptance contract explicitly says it can.

## 10. Research-validation placement

RVR should be spent before implementation/runtime when uncertainty is upstream of the solver.

High-value RVR classes include:

- source/provenance acceptance;
- experimental benchmark acceptance;
- model-selection decisions;
- representation-adequacy gates;
- framework/source-contract research that changes the test or implementation architecture.

The working empirical hypothesis is:

```text
higher well-targeted RVR
  -> lower EVR / DBR / RWR
```

Do not assume this relationship. Measure it across comparable complexity classes and work types.

## 11. Issue-start template

Every new bounded technical issue should contain:

```text
Work ID
Complexity
Closure claim
Known-good control
Primary unknown classes
Research questions / expected RVR
EVR budget: 0/3 used
EVR #1 decision objective
EVR #2 reserved purpose
EVR #3 reserved purpose
P0-P3 preflight contract
```

After each external result, update:

```text
EVR budget used: N/3
current root-cause class
remaining uncovered failure classes
next round purpose
```

## 12. Manager stop rules

The Manager should block external execution when any of the following is true:

- material source/model uncertainty is unresolved and cheaply researchable;
- the proposed tests are prerequisite-dependent and non-discriminating;
- there is no known-good control despite one being available;
- P0 checker sensitivity has not been demonstrated;
- P1 static construction checks have known gaps matching previous incidents;
- PASS criteria are post-hoc or unspecified;
- EVR #2/#3 has no unique decision purpose.

## 13. Retrospective rule

When a work item exceeds three EVRs, the closure review must classify every excess round into at least one category:

```text
missing research gate
missing known-good control
sequential diagnostics
non-independent tests
harness construction defect
analyzer defect
missing mutation/self-test
scope too broad
new independent incident
unavoidable external dependency
```

The review must then convert reusable causes into protocol/preflight changes.

## 14. Success metrics

For comparable work items, track:

```text
WCC
T-WCC
RVR
EVR
EVR budget used / 3
DBR
RWR
CLR
FBR
Reopened?
closure quality
```

Primary operational success:

```text
EVR <= 3
DBR <= 2
RWR = 0
closure quality unchanged
```

The long-term objective is not merely to debug faster. It is to turn repeated technical problem solving into a measured algorithm whose early research, preflight, and batch design steadily reduce user-local runtime repetition.
