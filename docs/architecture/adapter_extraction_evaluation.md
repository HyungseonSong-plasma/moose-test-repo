# Adapter Extraction Evaluation Framework

Status: **Draft v0.3 — canonical evaluation artifact, intentionally revisable**  
Scope: solver/backend adapter extraction and repository-boundary decisions  
Primary current application: Issue #157 (`sol-adapter-moose` extraction review)

## 1. Purpose

This document defines the canonical evaluation framework for deciding whether an in-repository solver/backend adapter should be externalized into an independently owned repository.

It evaluates two independent questions:

1. **Extraction Readiness** — can the adapter be separated safely, reproducibly, and without corrupting semantic ownership?
2. **Architectural Simplicity / Elegance** — does the resulting code contain only justified, non-redundant concepts, expressed at the broadest useful level, with names and boundaries that make their roles predictable?

```text
Readiness 100 != Simplicity 100
```

A technically perfect extraction can still be over-engineered. Conversely, a conceptually elegant design may still be unsafe to migrate.

The framework does not reward repository separation by itself. The desired result is a smaller, clearer ownership graph with fewer accidental dependencies, no semantic duplication, no unjustified new abstraction, and names that expose responsibility rather than hide it.

### Working definition of simple

For this framework, **simple does not mean merely short, flat, or low in file count**.

Simple means:

```text
necessary responsibility
        +
non-redundant owner
        +
useful generality
        +
semantically predictive naming
        +
minimal sufficient mechanism
```

Three tests are primary:

1. **Necessity / Irreplaceability** — if a new production abstraction can be replaced by an existing canonical facility without loss of required behavior, ownership, policy, lifecycle, or contract clarity, the new abstraction should not exist.
2. **Generality** — if a responsibility is genuinely reusable, its owner should express the broadest useful stable contract that covers legitimate use cases, rather than encode one caller, campaign, solver spelling, or historical workflow unnecessarily.
3. **Naming clarity** — a developer should be able to infer the primary responsibility of a production concept from its name and namespace without first opening its implementation.

These principles must be applied together. Generality without necessity produces speculative frameworks; necessity without generality produces one-off duplication; correct ownership hidden behind vague naming still produces unnecessary cognitive cost.

The target is **minimal sufficient generality with semantically obvious ownership**.

## 2. Governing principles

1. Canonical scientific meaning remains upstream of solver-specific realization.
2. Solver-native spelling, runtime syntax, backend decoding, and compatibility belong to the solver adapter.
3. Generic harness layers must not parse or generate solver-specific raw representation.
4. Every new production abstraction must justify why an existing canonical owner cannot satisfy the responsibility adequately.
5. Reusable responsibilities should be expressed at the broadest useful stable level, but speculative generalization without demonstrated need is not rewarded.
6. Names should describe current architectural role and responsibility, not migration history or implementation accident.
7. The same canonical concept should not acquire multiple competing names without a deliberate semantic distinction.
8. The same name should not silently denote materially different responsibilities when namespace/context does not disambiguate them.
9. Repository extraction must reduce or preserve cognitive complexity; increasing indirection merely to create a repository boundary is a failure mode.
10. Compatibility wrappers and migration facades are temporary unless there is a separately justified permanent API requirement.
11. Protocol conformance is not equivalent to numerical or physical correctness.
12. A successful migration should end in deletion of duplicate/legacy ownership rather than indefinite coexistence.
13. Normal feature work should usually be local to one repository and a small number of architectural layers.
14. Exact external contract names, solver-native identifiers, and established mathematical/domain terms must not be renamed merely for aesthetic uniqueness.

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

This score measures whether the resulting architecture contains only code and abstractions that have earned their existence and whether their purpose is obvious from the vocabulary used to describe them.

The primary question is not "how little code is there?" but:

> **Is every production concept necessary, non-substitutable by an existing canonical owner, general enough for the responsibility it claims, and named so that its role is predictable?**

### S1. Necessity / Irreplaceability — 25

Every newly introduced production module, class, service, wrapper, protocol helper, or abstraction must answer:

```text
What responsibility would be inadequately served if this code did not exist?
```

Full credit requires that the new owner provides at least one genuinely distinct value:

- a unique contract boundary;
- a unique policy decision;
- a unique lifecycle/resource responsibility;
- a necessary representation translation;
- an unavoidable external-system boundary;
- or a reusable capability not already owned canonically.

Penalty or rejection signals:

```text
NEW_OWNER_EQUIVALENT_TO_EXISTING_CANONICAL_OWNER > 0
PASS_THROUGH_WRAPPERS_WITHOUT_POLICY > 0
DUPLICATE_HELPERS_WITH_EXISTING_EQUIVALENT = true
```

If deleting a new abstraction and calling an existing canonical facility directly preserves required semantics, ownership, testability, and contract clarity, deletion is preferred.

### S2. Useful generality — 20

A necessary abstraction should be as general as its stable responsibility permits, but no more general than demonstrated use warrants.

Good generality:

```text
backend-neutral execution lifecycle
solver-specific realization boundary
canonical evidence normalization
```

Poor under-generalization:

```text
one module per historical campaign
one helper per caller when behavior is identical
QPX-specific names inside a genuinely generic transport/runtime primitive
```

Poor over-generalization:

```text
framework/plugin/provider layer created for hypothetical future backends
configurable extension machinery with no current second use case
abstract base classes whose only implementation is structurally permanent
```

The target is:

```text
GENERALITY = broadest useful stable responsibility
NOT broadest imaginable responsibility
```

### S3. Naming clarity and semantic predictability — 15

A production name should let a developer predict what the concept owns or does before reading the implementation.

Evaluate names jointly with their namespace. A leaf name does not need to be globally unique when its containing namespace makes the role precise.

Good examples of the principle:

```text
specification/compiler.py
    -> compiles specification-level intent

adapters/moose/mutation_spec/compiler.py
    -> compiles MOOSE mutation specifications

analysis/gradient_reconstruction/green_gauss.py
    -> exact Green–Gauss reconstruction analysis method
```

The same leaf name such as `compiler.py` is acceptable when the namespace provides strong semantic disambiguation.

Full credit requires:

1. **Functional expressiveness** — the name reflects the responsibility rather than a vague implementation category.
2. **Semantic predictability** — name + namespace makes likely inputs/outputs or role reasonably inferable.
3. **Vocabulary consistency** — one canonical concept normally has one canonical term.
4. **Low ambiguity** — the same term is not reused for unrelated responsibilities without clear namespace qualification.
5. **Current-role naming** — canonical production names describe what the code is now, not where it migrated from or which campaign created it.
6. **Appropriate specificity** — generic code uses generic vocabulary; solver/domain-specific code uses specific vocabulary where the specificity is intrinsic.

Penalty signals include vague bucket names when a more precise role exists:

```text
utils.py
helpers.py
misc.py
manager.py
processor.py
handler.py
service.py
common.py
```

These names are not automatically forbidden, but they require stronger namespace/context justification because they convey little responsibility by themselves.

Also penalize competing synonyms for the same architectural concept, for example when `adapter_runtime`, `backend_gateway`, and `solver_bridge` all denote the same responsibility without a real semantic distinction.

Do **not** force uniqueness by renaming exact external identifiers, established mathematical terms, or legitimate same-role leaf names that are already disambiguated by namespace.

Target indicators:

```text
UNJUSTIFIED_AMBIGUOUS_PRODUCTION_NAMES = 0
COMPETING_CANONICAL_SYNONYM_SETS = 0
UNJUSTIFIED_SAME_NAME_DIFFERENT_ROLE_COLLISIONS = 0
MIGRATION_HISTORY_NAMES_IN_CANONICAL_PRODUCTION = 0
EXACT_EXTERNAL_CONTRACT_NAMES_RENAMED_FOR_AESTHETICS = 0
```

A useful review test is:

> **Given only the path and public symbol name, can a developer make a mostly correct prediction about the responsibility without opening the implementation?**

### S4. Conceptual economy — 10

Ask how many distinct architectural concepts a developer must understand to trace a normal adapter feature.

Full credit requires that concepts correspond to real responsibilities rather than wrapper layers created only to route calls.

Penalty signal:

```text
Facade -> Service -> Manager -> Provider -> Gateway -> Bridge -> Translator
```

when those layers do not represent independently meaningful policies or contracts.

### S5. Change locality — 10

A normal solver-specific feature should usually change:

```text
1 repository
<= 2-3 architectural layers
small, cohesive set of production files
```

A feature that routinely requires synchronized edits across harness application, execution, evidence, protocol wrappers, adapter translation, execution, and result layers indicates poor locality.

### S6. Public API minimality — 5

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

### S7. Justified indirection — 5

Evaluate the path from canonical intent to backend realization and from backend evidence to canonical interpretation.

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

Every indirection layer must justify itself with a distinct contract, policy, representation, or lifecycle responsibility. Pure pass-through layers receive no simplicity credit.

### S8. Duplicate representation absence — 5

Target indicators:

```text
DUPLICATE_SOLVER_REALIZATION_OWNERS = 0
DUPLICATE_CANONICAL_TO_SOLVER_MAPPINGS = 0
DUPLICATE_PROTOCOL_MODEL_TRANSLATIONS = 0
```

Temporary migration duplication must have an explicit deletion condition.

### S9. Net simplification / legacy deletion — 5

A successful extraction should delete obsolete local implementation and compatibility ownership.

Target indicators:

```text
PERMANENT_COMPATIBILITY_FACADES = 0
RETIRED_LOCAL_ADAPTER_IMPLEMENTATION_OWNERS = 0
```

A migration that adds a new repository, protocol layer, and wrappers while retaining equivalent old ownership has not simplified the system.

## 6. Simplicity vetoes

Even when the numeric Simplicity score is high, a review should not report **READY** while any of the following remains unexplained:

```text
UNJUSTIFIED_REPLACEABLE_NEW_PRODUCTION_ABSTRACTIONS > 0
UNEXPLAINED_ONE_OFF_GENERIC_CANDIDATES > 0
COMPETING_CANONICAL_SYNONYM_SETS > 0
```

A replaceable abstraction may remain only when the review records the concrete non-code value that makes it necessary, such as process isolation, version independence, security boundary, lifecycle control, or stable external contract ownership.

A one-off implementation may remain when its specificity is intrinsic to the domain or external solver rather than an artifact of historical workflow.

A vocabulary synonym may remain only when the terms encode a real semantic distinction that can be explained in one sentence and is reflected consistently in ownership and contract boundaries.

## 7. Decision matrix

Numeric thresholds are guidance after hard gates and simplicity vetoes, not a substitute for architecture review.

| Extraction Readiness | Simplicity | Decision |
|---:|---:|---|
| >= 80 | >= 80 | **READY** — implementation migration may be authorized, provided no simplicity veto is active. |
| >= 80 | < 80 | **OVER-ENGINEERED / REDESIGN** — technically separable, but resulting architecture is not simple enough. |
| < 80 | >= 80 | **NOT YET SAFE** — attractive architecture, insufficient migration/contract/CI readiness. |
| < 80 | < 80 | **HOLD** — both safety and design require more work. |
| any | any | **HOLD** if any Hard Gate fails. |

A score of 100 on Extraction Readiness alone must never be reported as proof that the codebase is simple or elegant.

## 8. Core architectural invariants

For the current MOOSE extraction review, evaluate at least the following target invariants:

```text
DIRECT_QPX_TO_MOOSE_IMPLEMENTATION_EDGES = 0
CROSS_REPO_PUBLIC_PROTOCOL_SURFACES = 1
MOOSE_FEATURE_NORMAL_CHANGE_REPOS = 1
MOOSE_FEATURE_NORMAL_CHANGE_LAYERS <= 3
PERMANENT_COMPATIBILITY_FACADES = 0
DUPLICATE_MOOSE_REALIZATION_OWNERS = 0
DUPLICATE_CANONICAL_TO_MOOSE_MAPPINGS = 0
UNJUSTIFIED_REPLACEABLE_NEW_PRODUCTION_ABSTRACTIONS = 0
UNEXPLAINED_ONE_OFF_GENERIC_CANDIDATES = 0
UNJUSTIFIED_AMBIGUOUS_PRODUCTION_NAMES = 0
COMPETING_CANONICAL_SYNONYM_SETS = 0
UNJUSTIFIED_SAME_NAME_DIFFERENT_ROLE_COLLISIONS = 0
MIGRATION_HISTORY_NAMES_IN_CANONICAL_PRODUCTION = 0
SCIENTIFIC_SEMANTICS_REDEFINED_BY_ADAPTER = false
ORDINARY_HARNESS_CI_REQUIRES_LIVE_MOOSE = false
CROSS_REPO_ADAPTER_DEPENDENCY_IS_PINNED = true
```

Threshold-like invariants such as `MOOSE_FEATURE_NORMAL_CHANGE_LAYERS <= 3` are design heuristics rather than immutable universal laws. If a case justifiably exceeds them, the evaluation must record the reason.

## 9. Human comprehensibility and naming test

A new developer should be able to answer these questions without tracing a large graph of wrappers or cross-repository implementation details:

1. Where is canonical scientific meaning defined?
2. Where is solver-specific realization/mapping defined?
3. Where is solver execution and compatibility owned?
4. Where are canonical result/evidence interpretation and reasoning owned?
5. Why does each major abstraction between these owners need to exist?
6. Which parts are intentionally generic, and what concrete second use or stable responsibility justifies that generality?
7. From each major module/package name alone, what responsibility would the developer expect it to own?
8. Are there two or more names for what is effectively the same architectural concept?
9. Is any important name so broad that opening the implementation is required just to learn its basic responsibility?

For the intended MOOSE end state, the expected conceptual answers are approximately:

```text
scientific meaning       -> SOL/QPX semantic ownership
MOOSE realization        -> sol-adapter-moose
MOOSE execution/compat   -> sol-adapter-moose
canonical interpretation -> qpx_harness generic evidence/analysis/reasoning
```

If these answers require significant qualification because the same responsibility has multiple owners, intermediate abstractions cannot justify their existence, or names do not reveal role, the simplicity score should be reduced.

## 10. Evaluation evidence requirements

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
S1 Necessity / Irreplaceability           /25
S2 Useful generality                      /20
S3 Naming clarity / predictability        /15
S4 Conceptual economy                     /10
S5 Change locality                        /10
S6 Public API minimality                   /5
S7 Justified indirection                   /5
S8 Duplicate representation absence        /5
S9 Net simplification / legacy deletion    /5
                                          ----
TOTAL                                     /100

SIMPLICITY VETOES
UNJUSTIFIED_REPLACEABLE_NEW_PRODUCTION_ABSTRACTIONS = 0 / nonzero
UNEXPLAINED_ONE_OFF_GENERIC_CANDIDATES = 0 / nonzero
COMPETING_CANONICAL_SYNONYM_SETS = 0 / nonzero

DECISION
READY / OVER-ENGINEERED / NOT YET SAFE / HOLD
```

Scores must cite concrete repository evidence. Do not award points solely because a target architecture is documented.

## 11. Revision policy

This framework is intentionally maintained as a revisable draft. v0.3 adds **naming clarity and semantic predictability** as a first-class simplicity criterion, alongside necessity/irreplaceability and useful generality.

It should be revised when real extraction reviews reveal that:

- a criterion does not predict maintainability or failure risk;
- weights over-emphasize migration mechanics relative to code simplicity;
- a useful measurable invariant is missing;
- a threshold encourages unnecessary abstraction;
- a supposedly generic abstraction has no demonstrated reusable responsibility;
- new code duplicates an existing canonical capability under a different name;
- naming permits multiple competing terms for one canonical responsibility;
- vague package/module names repeatedly require implementation inspection to understand basic role;
- the SOL Adapter Protocol or repository operating model materially changes.

Changes to this evaluation framework should preserve the distinction between **safe separability** and **architectural simplicity**.

Issue-specific acceptance matrices may extend this framework, but should not silently redefine its canonical scoring meaning.
