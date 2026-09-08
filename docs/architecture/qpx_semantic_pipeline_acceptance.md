# QPX Semantic Pipeline Acceptance

## 1. Purpose and authority

This document is the canonical end-to-end acceptance record for the QPX semantic-compilation architecture governed by EPIC #131 and acceptance Issue #135.

It records the verified architecture on the `development` branch after semantic ownership, package migration, ontology projection, declarative specification, policy synthesis, execution compilation, MOOSE lowering, historical replay, and CLI/application consolidation.

The accepted semantic flow is:

```text
experiment.json
  -> Experiment Specification
  -> Semantic Compiler
  -> ExperimentIntent
  + DevelopmentState
  + CapabilityDescriptors
  -> Policy Synthesizer
  -> ScientificPolicy
  -> Execution Compiler
  -> solver-independent ExecutionPlan
  -> MOOSE Target Adapter
  -> MOOSE Target IR / emitted input
  -> Execution
  -> Observation / Evidence
  -> Analysis / Reasoning / Validation
  -> DevelopmentState transition
```

This acceptance does not redefine scientific formulas, thresholds, historical conclusions, or runtime evidence.

---

## 2. Versions and contracts under test

```text
SEMANTIC_CONTRACT: QPX_STATE_SEMANTICS_V1
ONTOLOGY_SCHEMA_VERSION: 1
EXPERIMENT_SPEC_SCHEMA_VERSION: 2
SEMANTIC_COMPILER_ID: qpx_harness.specification.compiler:v2
POLICY_VERSION: governed by QPX_STATE_SEMANTICS_V1; no independent persisted policy-version field
EXECUTION_PLAN_VERSION: repository-revision governed; no independent persisted plan-version field
OWLREADY2_ACCEPTANCE_DEPENDENCY: 0.51
ACCEPTANCE_BRANCH: development
ACCEPTANCE_HEAD: b095434609c34019243122c07e6fea0db0a89a1b
ACCEPTANCE_CI_RUN: QPX CI validation #649
ACCEPTANCE_STATUS: PASS
```

Version statements above reflect the versions actually represented by the implementation. No synthetic policy or ExecutionPlan version is invented merely for this report.

---

## 3. Acceptance manifest

Canonical acceptance surfaces:

```text
Semantic contract
  docs/architecture/qpx_development_state_semantics.md

Semantic ownership
  docs/architecture/qpx_semantic_ownership_matrix.yaml
  docs/architecture/qpx_semantic_ownership_review.md

Ontology
  qpx_harness/ontology/model.py
  qpx_harness/ontology/service.py
  qpx_harness/ontology/owlready.py
  qpx_harness/ontology/replay.py

Specification
  qpx_harness/specification/schema.py
  qpx_harness/specification/compiler.py

Planning
  qpx_harness/planning/*

Execution
  qpx_harness/execution/plan.py
  qpx_harness/execution/*

Target realization
  qpx_harness/adapters/moose/target.py

Golden semantic experiment
  experiments/semantic/electron_energy_diffusion/experiment.json

End-to-end acceptance
  tests/architecture/test_qpx_semantic_pipeline.py
  tests/architecture/test_qpx_semantic_epic_acceptance.py
  tests/architecture/test_qpx_historical_replay.py
  tests/architecture/test_qpx_responsibility_boundaries.py

Ontology dependency
  requirements-ontology.txt

CI executor
  .github/workflows/qpx-cleanup-validation.yml
```

---

## 4. Source and provenance inventory

Historical replay remains provenance-constrained. Historical Issue numbers identify sources; they are not ontology vocabulary or reusable semantic API identities.

Acceptance corpus:

| Fixture group | Sources | Primary distinction exercised |
| --- | --- | --- |
| F18 | #18 | construction failure is not physics rejection |
| F19 | #19 | representation/checker failure is not production-model failure |
| F20 | #20 | environment/JIT failure is not numerical-model invalidity |
| F23 | #23 | harness intervention failure is not solver/physics defect |
| F31 | #31 | degenerate/not-applicable metric is not PASS or threshold relaxation |
| F44 | #44 | observation-contract change may occur without world-state change |
| F45 | #45, #46, #86-#89 | partial evidence, hypothesis evolution, scientific closure, repository-only transition |
| F91 | #91-#94, #98 | fault isolation, owner-class versus atomic-owner distinction, counterfactual versus production acceptance |
| E2A_GOLDEN | accepted electron-energy diffusion semantic fixture | JSON -> Intent -> Policy -> Plan -> MOOSE lineage |

The historical replay implementation preserves explicit availability/admissibility distinctions including missing, unavailable, and non-evidentiary information. Missing raw evidence is never converted into negative evidence.

---

## 5. Canonical semantic JSON fixtures

The golden semantic fixture is:

```text
experiments/semantic/electron_energy_diffusion/experiment.json
```

It describes scientific intent and bounded execution rather than MOOSE input mutation operations.

The executable acceptance suite rejects canonical semantic specifications that attempt to embed target mutation vocabulary such as MOOSE block manipulation. The specification layer therefore remains target independent.

Golden architectural invariant:

```text
supported semantic capability
  -> new/changed experiment JSON
  -> existing Semantic Compiler
  -> existing Policy Synthesizer
  -> existing Execution Compiler
  -> existing target adapter

NEW_ISSUE_SPECIFIC_PYTHON_MODULES = 0
NEW_PROTOCOL_REGISTRY_ENTRIES = 0
NEW_RECIPES = 0
NEW_CLI_COMMANDS = 0
```

A genuinely unsupported semantic capability remains a `CAPABILITY_GAP`; it is not permission to add an Issue-specific bypass.

---

## 6. JSON -> ExperimentIntent

Production owner:

```text
qpx_harness.specification
```

The Semantic Compiler answers:

```text
What does this validated experiment specification mean?
```

It does not select scientific actions and does not know MOOSE realization details.

Verified lineage includes:

```text
source experiment.json path/hash
schema version
compiler identity
experiment identity
DevelopmentGoal identity
target proposition/question identities
requested semantic capabilities
constraints
requested observations
execution bounds
ExperimentIntent identity
provenance identity
```

Required distinction is preserved:

```text
ExperimentSpec != ExperimentIntent
DevelopmentState != ExperimentIntent
ExperimentIntent != ScientificPolicy
```

---

## 7. DevelopmentState + ExperimentIntent + Capabilities -> ScientificPolicy

Production owner:

```text
qpx_harness.planning
```

The policy layer receives immutable semantic context and produces immutable `ScientificPolicy` data/IR.

For E2A_GOLDEN the policy preserves the semantic equivalents of:

```text
objective: isolate electron-energy diffusion
control: zero diffusion coefficient
treatment: requested positive diffusion coefficient
held-fixed non-diffusion controls
required inventory/profile observations
control-vs-treatment discriminator
acceptance requirements
selection rationale
```

Verified boundaries:

```text
ScientificPolicy != ExperimentIntent
ScientificPolicy != ExecutionPlan
ScientificPolicy != MOOSE input
policy acceptance requirement != validated claim
policy synthesis does not mutate source DevelopmentState
```

Derived semantic values such as quasi-neutral initialization are produced by reusable policy logic rather than a general-purpose programming DSL embedded in JSON.

---

## 8. ScientificPolicy -> solver-independent ExecutionPlan

Production owner:

```text
qpx_harness.execution
```

`ExecutionPlan` preserves:

```text
source ScientificPolicy identity
ordered action/case identity
resolved parameters
derived values and provenance
required observations
execution bounds
artifact/output contracts
target capability requirements
```

The accepted IR contains no canonical MOOSE block paths, MOOSE object class names, raw `.i` text, or raw PETSc option spelling.

Required distinction is preserved:

```text
ScientificPolicy != ExecutionPlan
ExecutionPlan != ActionExecution
ExecutionPlan != target input
```

---

## 9. ExecutionPlan -> MOOSE target realization

Production owner:

```text
qpx_harness.adapters.moose
```

The MOOSE adapter is the first accepted layer allowed to know target syntax and realization details.

Verified lineage:

```text
ScientificPolicy.policy_id
  -> ExecutionPlan.source_policy_id
  -> ExecutionPlan.plan_id
  -> MooseTargetIR.source_plan_id
  -> MooseCaseIR.case_id / action_id
  -> deterministic emitted input
```

The adapter selects target spelling only. It does not select the scientific objective, discriminator, held-fixed semantics, or acceptance policy.

---

## 10. JSON-only supported-capability proof

The semantic-pipeline architecture tests construct and compile supported electron-energy and derived-state semantic requests through the production pipeline without adding Issue-specific routing.

Acceptance:

```text
ISSUE_SPECIFIC_SEMANTIC_CLASS_REQUIRED: false
ISSUE_SPECIFIC_RECIPE_REQUIRED: false
ISSUE_SPECIFIC_PROTOCOL_RUNNER_REQUIRED: false
PROTOCOL_REGISTRY_ENTRY_REQUIRED: false
NEW_CLI_COMMAND_REQUIRED: false
```

Unsupported target lowering raises an explicit lowering/capability error rather than emitting a placeholder target.

---

## 11. Historical replay acceptance

Historical replay is implemented in:

```text
qpx_harness/ontology/replay.py
tests/architecture/test_qpx_historical_replay.py
```

The historical query registry covers Q1-Q9 and preserves source-supported facts only.

Accepted distinctions include:

```text
MISSING != FALSE / negative evidence
UNAVAILABLE != REJECTED
NON_EVIDENTIARY != runtime evidence
NOT_TESTED != DISFAVORED
SKIPPED != PASS/FAIL
COST_GUARDED != evidence
OUT_OF_SCOPE != REJECTED
NOT_REQUIRED != DISFAVORED
NOT_APPLICABLE != PASS
DEGENERATE_METRIC != THRESHOLD_RELAXED
DERIVED_FACT != CAUSAL_HYPOTHESIS
OBSERVED_CHRONOLOGY != CAUSAL_MECHANISM
OWNER_CLASS_ISOLATED != ATOMIC_OWNER_ISOLATED
COUNTERFACTUAL_PASS != PRODUCTION_ACCEPTED
SCIENTIFIC_CLOSED != PRODUCTION_READY
EXECUTION_SUCCEEDED != SCIENTIFICALLY_VALIDATED
```

Repository-only state transitions can carry `repository_delta` while world and epistemic deltas remain empty.

---

## 12. Repository migration acceptance

The actual production dependency architecture is guarded by deterministic tests.

### #139 — C++ source inspection

Top-level C++ language identity is not a canonical semantic responsibility. Canonical responsibility packages do not depend on the retired `qpx_harness.cpp` authority.

### #140 — reasoning / Z3

Generic reasoning semantics and backend mechanics are separated. Domain packages are forbidden from directly importing Z3 or treating Z3 as scientific semantic authority.

### #141 — domain normalization

`domains/` is guarded against direct Z3, CLI, and MOOSE-adapter coupling. Cross-cutting responsibility remains outside the scientific domain owner.

### #142 — CLI/application

One canonical QPX operator entrypoint is retained. No second canonical `qpx-run` executable is permitted, and the semantic application gateway does not depend on retired root recipes or Issue-specific protocol dispatch for the supported semantic path.

### Root `recipes/` compatibility status

The physical root `recipes/` namespace still exists for bounded historical v1 reproduction/protocol compatibility.

Its canonical contract states:

```text
COMPATIBILITY_ONLY = true
SEMANTIC_AUTHORITY_RETIRED = true
NEW_CALLERS_FORBIDDEN = true
```

Therefore:

```text
ROOT_RECIPES_SEMANTIC_AUTHORITY_RETIRED: true
ROOT_RECIPES_PHYSICAL_NAMESPACE_REMOVED: false
```

The remaining physical namespace is not accepted as a competing semantic owner. Its explicit removal condition is retirement or migration of all legacy v1/historical reproduction callers. This compatibility debt is not part of the canonical supported-capability semantic path.

---

## 13. Semantic and architecture coverage matrix

| Boundary | Executable evidence | Status |
| --- | --- | --- |
| semantic ExperimentSpec | strict semantic schema/tests | PASS |
| ExperimentIntent | semantic compiler tests | PASS |
| DevelopmentState != ExperimentIntent | semantic pipeline tests | PASS |
| CapabilityDescriptor | semantic compiler/planning tests | PASS |
| ScientificPolicy synthesis | policy determinism and E2A tests | PASS |
| ActionSpec/SearchDecision/discriminator | policy tests | PASS |
| acceptance requirement != validated claim | semantic/policy invariants | PASS |
| ExecutionPlan solver independence | execution tests | PASS |
| MOOSE adapter-only target syntax | lowering/dependency tests | PASS |
| Artifact -> Observation -> Evidence -> DerivedFact | historical replay tests | PASS |
| stable propositions + state-scoped assessments | ontology/historical tests | PASS |
| DiagnosticConclusion distinctions | historical replay tests | PASS |
| ExecutionStatus != ExecutionOutcome | semantic model/historical tests | PASS |
| metric applicability / degeneracy | F31 replay | PASS |
| StateTransition / StateDelta facets | ontology/replay tests | PASS |
| repository-only transition | semantic pipeline/historical tests | PASS |
| counterfactual vs production acceptance | F91 replay | PASS |
| JSON-only supported experiment path | semantic pipeline tests | PASS |
| root recipes semantic authority retirement | responsibility-boundary test | PASS |
| C++ source responsibility | responsibility-boundary test | PASS |
| reasoning semantics vs Z3 backend | responsibility-boundary test | PASS |
| domain cross-cutting dependency boundaries | responsibility-boundary test | PASS |
| single QPX CLI/application gateway | responsibility-boundary test | PASS |
| Owlready2 explicit World isolation | semantic EPIC acceptance test | PASS |
| Owlready2 persistence/reload | semantic EPIC acceptance test | PASS |

---

## 14. Q1-Q12 deterministic query and lineage acceptance

Q1-Q9 are deterministic historical-replay queries:

```text
Q1  current-state
Q2  epistemic-partition
Q3  hypothesis-trajectory
Q4  evidence-lineage
Q5  search-history
Q6  state-delta
Q7  claim-readiness
Q8  absence-scope
Q9  repository-only-change
```

Q10-Q12 are cross-layer semantic-pipeline lineage contracts rather than historical-only replay queries:

```text
Q10 intent-lineage
  ExperimentSpec/source
    -> ExperimentIntent
    -> DevelopmentGoal / targets / provenance

Q11 policy-lineage
  DevelopmentState + ExperimentIntent + CapabilityDescriptors
    -> ScientificPolicy
    -> selected ActionSpecs / SearchDecisions / rationale

Q12 execution-lineage
  ScientificPolicy
    -> ExecutionPlan
    -> MOOSE Target IR
    -> deterministic emitted target input
```

Executable acceptance:

```text
test_q10_intent_lineage_is_deterministic_and_read_only
test_q11_policy_lineage_preserves_state_intent_capabilities_and_rationale
test_q12_execution_lineage_preserves_policy_plan_and_target_identity
```

All were executed successfully in CI run #649.

```text
Q1_Q9_HISTORICAL_REPLAY: PASS
Q10_INTENT_LINEAGE: PASS
Q11_POLICY_LINEAGE: PASS
Q12_EXECUTION_LINEAGE: PASS
Q1_Q12: PASS
```

---

## 15. Owlready2 and persistence acceptance

Owlready2 is now a required acceptance dependency rather than an optional skipped test dependency:

```text
requirements-ontology.txt
  owlready2==0.51
```

CI imports Owlready2 directly through the EPIC acceptance test. A missing dependency now fails collection rather than silently skipping World acceptance.

Verified Owlready2 contract:

```text
explicit World instance: PASS
world != owlready2.default_world: PASS
two Worlds isolated: PASS
semantic individual materialization: PASS
semantic contract metadata persisted: PASS
ontology schema version persisted: PASS
RDF/XML save: PASS
fresh World reload: PASS
stable semantic identity after reload: PASS
```

The closed-world `OntologyService` independently verifies immutable state commit, stable typed JSON round-trip, and semantic/schema version rejection for incompatible persisted data.

No external JVM reasoner is required for this acceptance path.

---

## 16. Ownership, dependency, CLI, and legacy-owner acceptance

The CI acceptance run executes:

```text
Evidence dependency guard
Analysis dependency guard
Execution dependency guard
presentation dependency guard
canonical package cycle guard
declarative experiment gateway guard
capability architecture census
full pytest
canonical `qpx -i all`
legacy science-refactor guards
execution-contract refactor guard
```

All completed successfully in QPX CI validation #649.

Required architecture results:

```text
Semantic Compiler -> MOOSE adapter: forbidden / satisfied
Policy Synthesizer -> MOOSE adapter: forbidden / satisfied
ExecutionPlan -> MOOSE syntax: forbidden / satisfied
MOOSE adapter redefines scientific policy: forbidden / satisfied
domain scientific rule -> Z3 direct import: forbidden / satisfied
second canonical qpx-run executable: absent
canonical semantic path -> root recipes dependency: absent
canonical semantic path -> Issue-specific protocol dispatch: absent
```

---

## 17. Remaining explicit limitations

The following limitation is explicit and does not weaken semantic ownership:

```text
root recipes/ physical namespace remains for bounded historical v1 compatibility
```

This is not a hidden canonical owner. New callers are forbidden, canonical capability packages do not import it, and the removal condition is explicit.

No scientific-runtime P3 result is claimed by this architecture acceptance. CI success establishes deterministic architecture, compilation, ontology projection, persistence, and internal validation only.

---

## 18. Gap summary

```text
SEMANTIC_GAPS: NONE
OWNERSHIP_OR_TAXONOMY_GAPS: NONE for canonical supported-capability path
ONTOLOGY_PROJECTION_OR_SERVICE_GAPS: NONE
SPEC_OR_SEMANTIC_COMPILATION_GAPS: NONE
POLICY_SYNTHESIS_GAPS: NONE
EXECUTION_COMPILATION_OR_LOWERING_GAPS: NONE
SOURCE_OBSERVATION_MIGRATION_GAPS: NONE for accepted architecture
REASONING_BACKEND_MIGRATION_GAPS: NONE for accepted architecture
DOMAIN_NORMALIZATION_GAPS: NONE for accepted architecture
CLI_APPLICATION_MIGRATION_GAPS: NONE for accepted architecture
FIXTURE_OR_ACCEPTANCE_EXPECTATION_GAPS: NONE
HISTORICAL_PROVENANCE_GAPS: remain explicit where source evidence is unavailable; never fabricated
BOUNDED_COMPATIBILITY_DEBT: physical root recipes/ namespace pending legacy-v1 caller retirement
```

The bounded compatibility debt is not competing semantic authority and does not block #131 semantic-architecture closure.

---

## 19. CI acceptance evidence

Repository-native execution was used as the acceptance executor.

```text
WORKFLOW: QPX CI validation
RUN: #649
BRANCH: development
HEAD: b095434609c34019243122c07e6fea0db0a89a1b
RESULT: SUCCESS
```

Successful stages include dependency installation with Owlready2, all architecture guards, full QPX-free pytest, canonical `qpx -i all`, and retained legacy refactor guards.

Because `development` is now an explicit workflow trigger, future changes to this branch will continue to execute this acceptance surface automatically.

---

## 20. EPIC closure verdict

The semantic architecture is accepted.

```text
SEMANTIC_VERSION: QPX_STATE_SEMANTICS_V1
ONTOLOGY_SCHEMA_VERSION: 1
EXPERIMENT_SPEC_VERSION: 2
POLICY_VERSION: QPX_STATE_SEMANTICS_V1-governed
EXECUTION_PLAN_VERSION: repository-revision-governed
STATUS: PASS

E2A_JSON_TO_INTENT: PASS
E2A_POLICY_SYNTHESIS: PASS
E2A_EXECUTION_PLAN: PASS
E2A_MOOSE_LOWERING: PASS
JSON_ONLY_NEW_EXPERIMENT: PASS
HISTORICAL_REPLAY: PASS
REPOSITORY_MIGRATIONS_139_142: PASS
Q1_Q12: PASS
ROUND_TRIP: PASS
OWLREADY_WORLD_ISOLATION: PASS
OWLREADY_PERSISTENCE_RELOAD: PASS
OWNERSHIP_ARCHITECTURE: PASS

ROOT_RECIPES_SEMANTIC_AUTHORITY_RETIRED: true
ROOT_RECIPES_PHYSICAL_NAMESPACE_REMOVED: false
DOMAIN_DIRECT_Z3_IMPORTS_IN_ACCEPTED_DOMAIN_PATH: 0
QPX_RUN_SEPARATE_CANONICAL_EXECUTABLE: false
SCIENTIFIC_SEMANTICS_CHANGED: false
UNRESOLVED_GAPS: NONE for #131 semantic architecture closure

UNBLOCKS: #134 closure -> #135 closure -> #131 closure
```
