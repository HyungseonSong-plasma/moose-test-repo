# Adapter Extraction Evaluation Framework

Status: **Draft v0.1 — canonical evaluation artifact, intentionally revisable**  
Scope: solver/backend adapter extraction and repository-boundary decisions  
Primary current application: Issue #157 (`sol-adapter-moose` extraction review)

## 1. Purpose

This document defines the canonical evaluation framework for deciding whether an in-repository solver/backend adapter should be externalized into an independently owned repository.

It deliberately evaluates two different questions:

1. **Extraction Readiness** — can the adapter be separated safely, reproducibly, and without corrupting semantic ownership?
2. **Architectural Simplicity / Elegance** — does the separation actually make the system easier to understand, change, test, and maintain?

These axes are independent.

```text
Readiness 100 != Simplicity 100
```

A technically perfect extraction can still be over-engineered. Conversely, a conceptually elegant design may still be unsafe to migrate.

The purpose of this framework is therefore not to reward repository separation by itself. The desired result is a smaller, clearer ownership graph with fewer accidental dependencies and no semantic duplication.

## 2. Governing principles

1. Canonical scientific meaning remains upstream of solver-specific realization.
2. Solver-native spelling, runtime syntax, backend decoding, and compatibility belong to the solver adapter.
3. Generic harness layers must not parse or generate solver-specific raw representation.
4. Repository extraction must reduce or preserve cognitive complexity; increasing indirection merely to create a repository boundary is a failure mode.
5. Compatibility wrappers and migration facades are temporary unless there is a separately justified permanent API requirement.
6. Protocol conformance is not equivalent to numerical or physical correctness.
7. A successful migration should end in deletion of duplicate/legacy ownership rather than indefinite coexistence.
8. Normal feature work should usually be local to one repository and a small number of architectural layers.

## 3. Hard gates

All hard gates must pass before a full extraction is authorized.

| Gate | Question | PASS condition |
|---|---|---|
| G1 Architecture acceptance | Is the source architecture stable enough to extract from? | Parent cleanup/ownership campaigns have completed their actual integrated acceptance gates. |
| G2 Scientific safety | Did cleanup/extraction planning alter scientific or numerical behavior? | No physics, numerical algorithm, tolerance, accepted scientific-state, or provenance-semantic change is introduced by the architecture migration. Scientific EVR consumption remains explicitly accounted for. |
| G3 Ownership completeness | Is every remaining adapter production responsibility understood? | 100% of relevant production modules/functions are classified into canonical ownership categories; no unexplained adapter residue remains. |
| G4 Semantic boundary | Does the adapter realize semantics rather than redefine them? | Canonical scientific meaning has one upstream owner; solver adapter owns realization only; duplicate canonical-to-solver semantic owners = 0. |
| G5 Generic-layer purity | Do generic layers remain solver-independent? | Generic application/execution/evidence/analysis owns no raw solver syntax generation or raw solver-log decoding. |
| G6 Protocol viability | Can the repository boundary carry the required behavior? | Required describe/validate/execute/result/evidence semantics are representable through a stable adapter contract, or a bounded prerequisite contract-extension plan exists. |
| G7 CI separability | Can ordinary harness development proceed without the live solver? | Ordinary harness PR CI can run without live solver installation; backend-specific CI is owned by the adapter repository. |
| G8 Version reproducibility | Can a working cross-repository combination be reproduced? | Adapter, protocol/public contract, artifact identity, and supported solver/application versions can be pinned and reconstructed. |

If any hard gate fails, the extraction decision is **HOLD** regardless of numeric score.

## 4. Extraction Readiness Score — 100 points

This score measures whether extraction is safe and operationally sound. It does **not** measure elegance.

### R1. Ownership boundary — 20

Evaluate whether adapter-specific production ownership is explicit and complete.

Target indicators:

```text
UNCLASSIFIED_ADAPTER_PRODUCTION_MODULES = 0
GENERIC_RAW_SOLVER_DECODERS = 0
GENERIC_SOLVER_INPUT_GENERATORS = 0
SOLVER_SPECIFIC_SOURCE_OBSERVERS_OUTSIDE_ADAPTER = 0
```

Scoring guidance:

- 20: ownership is explicit and localized;
- 15: only minor helper ambiguity remains;
- 10: realization and solver mechanics still partially mixed;
- 0: broad cross-layer ownership ambiguity remains.

### R2. Canonical realization-contract coverage — 20

Evaluate whether current scientific intent can cross the repository boundary without leaking solver-native concepts upstream.

The contract should carry, where required:

- scientific entities and mathematical models;
- constitutive/closure relationships;
- parameters and quantities;
- spatial scopes;
- observations;
- execution constraints;
- provenance/identity needed for realization.

Scoring guidance:

- 20: currently required realizations are expressible through canonical contracts;
- 15: generic extraction is ready but some domain realization remains incomplete;
- 10: substantial domain meaning still depends on local solver-specific implementation types;
- 0: current behavior cannot be represented without direct local adapter implementation ownership.

### R3. Adapter independence — 15

Target behavior:

```text
canonical request
    -> adapter validation
    -> solver realization
    -> execution / check
    -> canonical result/evidence
```

Target indicators:

```text
ADAPTER_TO_HARNESS_INTERNAL_IMPORT_EDGES = 0
APPLICATION_TO_LOCAL_SOLVER_IMPLEMENTATION_EDGES = target 0
```

### R4. CI architecture — 15

Preferred responsibility split:

```text
Harness CI
    -> protocol fixtures / fake adapter
    -> no live solver

Adapter CI
    -> protocol conformance
    -> live solver check/execution
    -> backend compatibility
    -> adapter-specific V&V

Cross-repository CI
    -> pinned harness + pinned adapter + pinned solver
```

A branch-head dependency such as `adapter@main` is not sufficient for full credit.

### R5. Compatibility and versioning — 10

A compatibility envelope should identify at least:

```text
Harness version/commit
Public Contract / realization-contract version
Adapter Protocol version
Adapter version/artifact digest
Supported solver version/application identity
```

### R6. Characterization and equivalence evidence — 10

Migration should preserve observable behavior where behavior is intended to remain unchanged.

Useful evidence includes:

- canonical request fixtures;
- before/after generated input comparison;
- result/evidence schema comparison;
- failure-semantics comparison;
- representative adapter characterization cases;
- explicit exceptions where byte-for-byte equivalence is not required but semantic equivalence is.

### R7. Operational locality — 5

Normal solver-specific changes should usually require changes in the adapter repository only.

Protocol/public-contract changes may legitimately require coordinated repository changes, but this should be exceptional rather than the normal development path.

### R8. Migration and rollback safety — 5

Prefer staged cutover:

```text
existing implementation characterization
        -> external adapter shadow/equivalence path
        -> protocol cutover
        -> local implementation deletion
```

Avoid irreversible big-bang migration where possible.

## 5. Architectural Simplicity / Elegance Score — 100 points

This score measures whether the resulting architecture is actually simpler to reason about and change.

### S1. Conceptual economy — 20

Ask how many distinct architectural concepts a developer must understand to trace a normal adapter feature.

Full credit requires that concepts correspond to real responsibilities rather than wrapper layers created only to route calls.

Penalty signals:

```text
Facade -> Service -> Manager -> Provider -> Gateway -> Bridge -> Translator
```

when those layers do not represent independently meaningful policies or contracts.

### S2. Change locality — 20

A normal solver-specific feature should usually change:

```text
1 repository
<= 2-3 architectural layers
small, cohesive set of production files
```

A feature that routinely requires synchronized edits across harness application, execution, evidence, protocol wrappers, adapter translation, execution, and result layers indicates poor locality.

### S3. Public API minimality — 15

The cross-repository public surface should be small, explicit, and stable.

Preferred conceptual surface:

```text
describe_adapter
validate_plan
execute_plan
```

Additional operations are acceptable only when they represent genuinely distinct contracts, not implementation convenience.

Target indicator:

```text
CROSS_REPO_PUBLIC_PROTOCOL_SURFACES = 1
```

### S4. Dependency and indirection depth — 15

Evaluate the shortest understandable path from canonical intent to backend realization and from backend evidence to canonical interpretation.

Good:

```text
QPX/SOL
   -> adapter runtime
   -> adapter protocol
   -> solver adapter
   -> solver
```

Poor:

```text
QPX
   -> client facade
   -> compatibility wrapper
   -> transport wrapper
   -> adapter service
   -> translation service
   -> backend bridge
   -> solver
```

Every indirection layer must justify itself with a distinct contract, policy, or lifecycle responsibility.

### S5. Duplicate representation absence — 15

Target indicators:

```text
DUPLICATE_SOLVER_REALIZATION_OWNERS = 0
DUPLICATE_CANONICAL_TO_SOLVER_MAPPINGS = 0
DUPLICATE_PROTOCOL_MODEL_TRANSLATIONS = 0
```

Temporary migration duplication must have an explicit deletion condition.

### S6. Legacy/wrapper deletion — 15

A successful extraction should delete obsolete local implementation and compatibility ownership.

Target indicators:

```text
PERMANENT_COMPATIBILITY_FACADES = 0
RETIRED_LOCAL_ADAPTER_IMPLEMENTATION_OWNERS = 0
```

A migration that only adds an external repository while retaining the old implementation indefinitely should score poorly.

## 6. Decision matrix

Numeric thresholds are guidance after hard gates, not a substitute for architecture review.

| Extraction Readiness | Simplicity | Decision |
|---:|---:|---|
| >= 80 | >= 80 | **READY** — implementation migration may be authorized. |
| >= 80 | < 80 | **OVER-ENGINEERED / REDESIGN** — technically separable, but resulting architecture is not simple enough. |
| < 80 | >= 80 | **NOT YET SAFE** — attractive architecture, insufficient migration/contract/CI readiness. |
| < 80 | < 80 | **HOLD** — both safety and design require more work. |
| any | any | **HOLD** if any Hard Gate fails. |

A score of 100 on Extraction Readiness alone must never be reported as proof that the codebase is simple or elegant.

## 7. Core architectural invariants

For the current MOOSE extraction review, evaluate at least the following target invariants:

```text
DIRECT_QPX_TO_MOOSE_IMPLEMENTATION_EDGES = 0
CROSS_REPO_PUBLIC_PROTOCOL_SURFACES = 1
MOOSE_FEATURE_NORMAL_CHANGE_REPOS = 1
MOOSE_FEATURE_NORMAL_CHANGE_LAYERS <= 3
PERMANENT_COMPATIBILITY_FACADES = 0
DUPLICATE_MOOSE_REALIZATION_OWNERS = 0
DUPLICATE_CANONICAL_TO_MOOSE_MAPPINGS = 0
SCIENTIFIC_SEMANTICS_REDEFINED_BY_ADAPTER = false
ORDINARY_HARNESS_CI_REQUIRES_LIVE_MOOSE = false
CROSS_REPO_ADAPTER_DEPENDENCY_IS_PINNED = true
```

Threshold-like invariants such as `MOOSE_FEATURE_NORMAL_CHANGE_LAYERS <= 3` are design heuristics rather than immutable universal laws. If a case justifiably exceeds them, the evaluation must record the reason.

## 8. Human comprehensibility test

A new developer should be able to answer these questions without tracing a large graph of wrappers or cross-repository implementation details:

1. Where is canonical scientific meaning defined?
2. Where is solver-specific realization/mapping defined?
3. Where is solver execution and compatibility owned?
4. Where are canonical result/evidence interpretation and reasoning owned?

For the intended MOOSE end state, the expected conceptual answers are approximately:

```text
scientific meaning       -> SOL/QPX semantic ownership
MOOSE realization        -> sol-adapter-moose
MOOSE execution/compat   -> sol-adapter-moose
canonical interpretation -> qpx_harness generic evidence/analysis/reasoning
```

If these answers require significant qualification because the same responsibility has multiple owners, the simplicity score should be reduced.

## 9. Evaluation evidence requirements

A formal extraction review should record:

```text
HARD GATES
G1 Architecture acceptance                PASS/HOLD
G2 Scientific safety                      PASS/HOLD
G3 Ownership completeness                 PASS/HOLD
G4 Semantic boundary                      PASS/HOLD
G5 Generic-layer purity                   PASS/HOLD
G6 Protocol viability                     PASS/HOLD
G7 CI separability                        PASS/HOLD
G8 Version reproducibility                PASS/HOLD

EXTRACTION READINESS
R1 Ownership boundary                     /20
R2 Realization-contract coverage          /20
R3 Adapter independence                   /15
R4 CI architecture                        /15
R5 Compatibility/versioning               /10
R6 Characterization/equivalence           /10
R7 Operational locality                    /5
R8 Migration/rollback safety               /5
                                          ----
TOTAL                                     /100

SIMPLICITY / ELEGANCE
S1 Conceptual economy                     /20
S2 Change locality                        /20
S3 Public API minimality                  /15
S4 Dependency/indirection depth           /15
S5 Duplicate representation absence       /15
S6 Legacy/wrapper deletion                /15
                                          ----
TOTAL                                     /100

DECISION
READY / OVER-ENGINEERED / NOT YET SAFE / HOLD
```

Scores must cite concrete repository evidence. Do not award points solely because a target architecture is documented.

## 10. Revision policy

This framework is intentionally introduced as **Draft v0.1**.

It should be revised when real extraction reviews reveal that:

- a criterion does not predict maintainability or failure risk;
- weights over-emphasize migration mechanics relative to code simplicity;
- a useful measurable invariant is missing;
- a threshold encourages unnecessary abstraction;
- the SOL Adapter Protocol or repository operating model materially changes.

Changes to this evaluation framework should preserve the distinction between **safe separability** and **architectural simplicity**.

Issue-specific acceptance matrices may extend this framework, but should not silently redefine its canonical scoring meaning.
