# QPX Development State Semantics

```text
semantic_contract_id: QPX_STATE_SEMANTICS_V1
status: FROZEN
```

## Authority

This document is the normative semantic contract for the QPX development-state architecture. Python types, JSON schemas, OWL/Owlready2 entities, persisted records, package names, adapters, and CLI surfaces are projections or consumers of this contract and must not redefine it.

## Layer boundaries

```text
DevelopmentState
  immutable decision-sufficient snapshot of the current development situation.

ExperimentIntent
  immutable semantic interpretation of what a validated experiment specification asks to investigate.

DevelopmentGoal
  stable target knowledge, claim, or state objective referenced by an ExperimentIntent.

CapabilityDescriptor
  versioned solver-independent declaration of an available semantic affordance.

ScientificPolicy
  immutable semantic policy synthesized from DevelopmentState + ExperimentIntent + available capabilities.

ExecutionPlan
  immutable solver-independent mechanical IR describing concrete executable cases/actions/observations.

ActionExecution
  immutable event representing an actual realization attempt of an ActionSpec.
```

Required invariants:

```text
JSON != ExperimentIntent
DevelopmentState != ExperimentIntent
ExperimentIntent != ScientificPolicy
ScientificPolicy != ExecutionPlan
ExecutionPlan != target solver input
ExecutionPlan != ActionExecution
CapabilityDescriptor != solver adapter
```

Conceptual relationships:

```text
ExperimentIntent = semantic_compilation(validated_experiment_spec)
ScientificPolicy = f(DevelopmentState, ExperimentIntent, CapabilityDescriptors)
ExecutionPlan = g(ScientificPolicy, execution_capabilities)
```

## Evidence and epistemic chain

```text
Artifact
  persisted source object such as a log, CSV, Parquet dataset, input file, or Exodus result.

Observation
  source-faithful extracted statement/value. No scientific interpretation is added.

Evidence
  provenance-qualified Observation admitted for one reasoning/claim context.

DerivedFact
  deterministic computation over Observation/Evidence.

Constraint
  declared condition that limits search, execution, interpretation, or scope.

ProvenanceRecord
  source/lineage record linking a semantic object to its origin.

EvidenceAvailability
  whether an expected evidence source is AVAILABLE, MISSING, or UNAVAILABLE.

EvidenceAdmissibility
  whether available material is admissible for a particular reasoning context.
```

Hard invariants:

```text
Artifact != Observation != Evidence != DerivedFact
DerivedFact != Hypothesis
MISSING != negative evidence
NOT_OBSERVED != ABSENT_IN_WORLD
SYNTHETIC_FIXTURE != RUNTIME_EVIDENCE
NON_EVIDENTIARY != runtime evidence
```

The same Observation may be admissible Evidence for one claim and non-admissible for another.

## Identity and lifetime

| Term | Identity class | Mutation rule | State scope |
|---|---|---|---|
| DevelopmentState | IMMUTABLE_SNAPSHOT | never mutate after commit | one state |
| ExperimentIntent | IMMUTABLE_SNAPSHOT | never mutate | intent context |
| ScientificPolicy | IMMUTABLE_SNAPSHOT | never mutate | synthesis context |
| ExecutionPlan | IMMUTABLE_SNAPSHOT / downstream IR | never mutate | policy context |
| Proposition | STABLE_IDENTITY | proposition text/identity stable | cross-state |
| Hypothesis | STABLE_IDENTITY | stable | cross-state |
| MechanismClaim | STABLE_IDENTITY | stable | cross-state |
| ValidationClaim | STABLE_IDENTITY | stable | cross-state |
| CapabilityDescriptor | STABLE_IDENTITY, versioned | version instead of mutation | cross-state |
| HypothesisAssessment | STATE_SCOPED_ASSERTION | append new assessment | exactly one state |
| ClaimAssessment | STATE_SCOPED_ASSERTION | append new assessment | exactly one state |
| DiagnosticConclusion | STATE_SCOPED_ASSERTION | append new conclusion | exactly one state |
| ActionSpec | STABLE_IDENTITY | declarative identity stable | cross-state |
| SearchDecision | IMMUTABLE_EVENT | never mutate | one decision context |
| ActionExecution | IMMUTABLE_EVENT | never mutate | one execution |
| ExecutionOutcome | IMMUTABLE_EVENT / result | never mutate | one execution |
| StateTransition | IMMUTABLE_EVENT / relation | never mutate | predecessor/successor |
| StateDelta | VALUE_RECORD | immutable | one transition |

## Assessment dimensions

### HypothesisAssessment

```text
support:
  UNKNOWN | CONTRADICTED | DISFAVORED | PLAUSIBLE | SUPPORTED | STRONGLY_SUPPORTED

resolution:
  OPEN | HOLD | RESOLVED

scope:
  IN_SCOPE | OUT_OF_SCOPE | NOT_REQUIRED

confidence:
  optional quantitative value whose interpretation is declared by the producer
```

### ClaimAssessment

```text
validation:
  UNASSESSED | VALIDATED | REJECTED

applicability:
  APPLICABLE | NOT_APPLICABLE | DEGENERATE | INSUFFICIENT_EVIDENCE

acceptance:
  BLOCKED | ACCEPTED

production_readiness:
  NOT_ASSESSED | BLOCKED | READY
```

Required legal distinctions:

```text
PLAUSIBLE + OUT_OF_SCOPE is legal
NOT_REQUIRED != DISFAVORED
NOT_APPLICABLE != PASS
DEGENERATE != threshold relaxation
SCIENTIFIC_CLOSED != PRODUCTION_READY
EXECUTION_SUCCEEDED != SCIENTIFICALLY_VALIDATED
```

## ExperimentIntent, DevelopmentGoal, and capabilities

ExperimentIntent carries semantically:

```text
intent_id
source specification identity/provenance
objective
DevelopmentGoal(s)
target propositions/open questions
requested capabilities
parameters / declared values
Constraints / held-fixed declarations
requested observations
execution bounds / declared budget
```

ExperimentIntent states what is requested. It does not select concrete ActionSpecs, contain MOOSE block paths, carry PETSc option-array syntax, mutate DevelopmentState, or declare validation success.

CapabilityDescriptor carries:

```text
capability_id
responsibility
semantic inputs
semantic outputs
constraints
version
availability identity/projection when applicable
```

Target spelling is not canonical capability meaning.

## Propositions and diagnosis

```text
Proposition
├── Hypothesis
├── MechanismClaim
└── ValidationClaim

DiagnosticConclusion
  state-scoped synthesis over Evidence/DerivedFact and assessed propositions.
```

DiagnosticConclusion may localize an owner class, atomic owner, or mechanism only to the strength justified by evidence.

Hard invariants:

```text
Hypothesis != DiagnosticConclusion
MechanismClaim != DiagnosticConclusion
DERIVED_FACT != CAUSAL_HYPOTHESIS
OBSERVED_CHRONOLOGY != CAUSAL_MECHANISM
OWNER_CLASS_ISOLATED != ATOMIC_OWNER_ISOLATED
```

## Action, search, and ScientificPolicy

ActionSpec declares:

```text
action_id
intent / intended_effect
target
intervention_type
discriminated propositions/questions
expected_information_gain
expected_cost
expected_risk
preserved/held-fixed invariants
required budget/authorization
```

SearchDecision is an immutable record selecting, deferring, pruning, or skipping an ActionSpec with rationale.

ScientificPolicy carries:

```text
policy_id
source DevelopmentState
source ExperimentIntent
objective / target claims
selected ActionSpecs
considered/deferred/pruned ActionSpecs where relevant
held-fixed Constraints
required observations
Discriminators
acceptance/validation requirements
execution bounds
policy rationale
required capabilities
unresolved requirements
provenance
semantic contract version
```

Hard invariants:

```text
ScientificPolicy is semantic data/IR, not an Issue-specific script
policy acceptance requirement != validated claim
PLANNED != SELECTED != EXECUTED
SKIPPED != PASS/FAIL
COST_GUARDED != scientific evidence
```

Reusable derived-policy rules may compute semantic values such as quasi-neutral initialization. General-purpose programming constructs are not embedded in experiment JSON.

## ExecutionPlan and execution boundary

ExecutionPlan answers what concrete executable cases/actions/observation requests must run. It remains solver independent and may contain:

```text
plan_id
source policy id
ordered case/action identities
resolved parameter values
derived values + provenance
required observations
execution bounds
artifact/output contracts
target capability requirements
provenance
```

Canonical ExecutionPlan must not contain MOOSE block paths, MOOSE class names, raw `.i` text, or raw PETSc option-array spelling.

Execution semantics are orthogonal:

```text
ExecutionStatus:
  RUNNING | WAITING | STALL_SUSPECTED | ...

ExecutionOutcome:
  SUCCEEDED | FAILED | CANCELLED | NOT_EXECUTED | ...
```

ExecutionOutcome never implies claim validation.

## State transition

```text
StateTransition
├── predecessor
├── successor
├── caused_by ActionExecution when applicable
└── delta

StateDelta
├── world_delta
├── observation_delta
├── epistemic_delta
├── search_delta
├── claim_delta
└── repository_delta
```

All facets are independent. Valid transitions include world-changing, observability-only, analysis-only, epistemic-only, claim-only, and repository-only transitions.

Historical #89 requirement:

```text
repository_delta != NONE
world_delta == NONE
epistemic_delta == NONE
```

## Absence, scope, and acceptance invariants

```text
MISSING != FALSE
MISSING != DISFAVORED
NOT_OBSERVED != ABSENT_IN_WORLD
NOT_TESTED != DISFAVORED
SKIPPED != PASS
SKIPPED != FAIL
COST_GUARDED != EVIDENCE_FOR_OR_AGAINST
OUT_OF_SCOPE != REJECTED
OUT_OF_SCOPE != EXONERATED
NOT_REQUIRED != DISFAVORED
NOT_APPLICABLE != PASS
DEGENERATE_METRIC != THRESHOLD_RELAXED
SYNTHETIC_FIXTURE != RUNTIME_EVIDENCE
DERIVED_FACT != CAUSAL_HYPOTHESIS
OBSERVED_CHRONOLOGY != CAUSAL_MECHANISM
OWNER_CLASS_ISOLATED != ATOMIC_OWNER_ISOLATED
COUNTERFACTUAL_PASS != PRODUCTION_ACCEPTED
SCIENTIFIC_CLOSED != PRODUCTION_READY
VALID_PHYSICS != NUMERICALLY_PROMOTABLE
```

## Counterexample matrix

| Counterexample | Required representation | Forbidden representation | Result |
|---|---|---|---|
| raw runtime evidence missing, summary available | availability separated by artifact/evidence identity | missing treated as contradiction | PASS |
| fact survives causal hypothesis rejection | DerivedFact stable; hypothesis assessment changes | delete fact when hypothesis disfavored | PASS |
| owner class isolated | DiagnosticConclusion localizes owner class | atomic C++ defect asserted | PASS |
| normalization counterfactual passes | counterfactual claim supported | production accepted automatically | PASS |
| net-charge metric degenerate | applicability=DEGENERATE; alternate metric may apply | threshold relaxed | PASS |
| observability-only instrumentation | observation_delta changes, world_delta unchanged | physics change inferred | PASS |
| repository-only transition | repository_delta only | epistemic change invented | PASS |
| scientific closure with production blocker | claim validated + readiness blocked | one PASS/FAIL status | PASS |
| synthetic parser fixture | available but non-evidentiary for runtime | runtime Observation | PASS |
| executable completes | ExecutionOutcome=SUCCEEDED | claim marked VALIDATED | PASS |
| JSON intent | ExperimentIntent contains semantic request | MOOSE operation syntax required | PASS |
| state vs intent | separate immutable snapshots | user request inserted into state facts | PASS |
| policy generation | ScientificPolicy semantic IR | ExecutionPlan generated at same semantic layer | PASS |
| MOOSE lowering | target adapter realizes ExecutionPlan | changes ScientificPolicy meaning | PASS |
| unsupported capability | explicit CAPABILITY_GAP | fallback to Issue-specific runner | PASS |

## Change control

`QPX_STATE_SEMANTICS_V1` is frozen for #133/#134/#136/#137/#138/#135 work. Downstream implementation inconvenience is not grounds to redefine it. A genuine semantic defect requires an explicit semantic amendment and revalidation of affected ownership/schema/compiler/policy/replay artifacts.

Issue numbers remain provenance/source identities only and must not become reusable semantic vocabulary.

## Non-goals

This contract does not choose package paths, implement Owlready2, define JSON syntax, synthesize policy, lower solver input, implement MCTS/Bayesian policy learning, or change accepted scientific formulas/thresholds/conclusions.

## Handoff

```text
SEMANTIC_CONTRACT: QPX_STATE_SEMANTICS_V1
STATUS: PASS
UNRESOLVED_TERMS: NONE
UNRESOLVED_SEMANTIC_GAPS: NONE for the accepted corpus
UNBLOCKS: #133
DOES_NOT_AUTHORIZE: package placement, Owlready2 implementation, JSON implementation, policy implementation, solver lowering
```
