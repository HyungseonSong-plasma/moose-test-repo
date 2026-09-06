# Batch 7 final umbrella acceptance — #145 semantic architecture cleanup

Status: **PENDING INDEPENDENT CLOSEOUT VALIDATION**

This document is the integrated acceptance manifest for #145 Batch 7. Batch 7 is acceptance-only: it does not introduce numerical, solver, plasma-physics, or historical experiment behavior changes.

## Baseline under review

The closeout review starts from the post-Batch-6 `development` state:

```text
development baseline = ea43169fb1d53321bc06ec874d3f2e8894a240ca
```

All seven implementation child issues are closed before this review:

```text
#146 MOOSE boundary consolidation
#147 canonical experiment control plane
#148 plasma semantic generalization
#149 campaign/performance/scale residue cleanup
#150 canonical model terminology
#151 gradient-reconstruction ownership
#152 Jacobian-verification ownership
```

Their closure is prerequisite evidence, not a substitute for Batch 7 validation. The integrated tree must pass the independent cross-cutting gates below on one exact commit.

## Independent closeout sequence

```text
1. semantic/terminology/numerical-method/solver-boundary guards
2. dependency-direction and cycle guards
3. strict zero-legacy architecture census
4. QPX-free pytest
5. canonical `python qpx -i all`
6. frozen Issue43/45 historical characterization guard
7. frozen Issue89 historical characterization guard
8. execution-contract characterization guard
9. record exact commit + CI run + integrated acceptance values
```

The canonical CI owner for this sequence is `.github/workflows/qpx-cleanup-validation.yml`.

## Acceptance ownership map

| #145 closeout claim | Independent owner |
|---|---|
| canonical experiment schema/control plane | `tools/qpx_experiment_gateway_guard.py` + strict architecture census |
| plasma species/composition/charge semantics | `tools/qpx_plasma_semantic_residue_guard.py` |
| campaign/performance/scale residue | `tools/qpx_campaign_residue_guard.py` |
| gradient-reconstruction ownership | `tools/qpx_numerical_method_ownership_guard.py` |
| Jacobian-verification ownership / generic-vs-PETSc boundary | `tools/qpx_numerical_method_ownership_guard.py` + dependency guards |
| selected-model terminology | `tools/qpx_boundary_terminology_guard.py` |
| single MOOSE integration boundary | `tools/qpx_boundary_terminology_guard.py` + dependency guards |
| dependency direction and cycles | `tools/qpx_dependency_guard.py` |
| zero legacy / canonical root surface | `tools/qpx_architecture_census.py --require-no-legacy` |
| generic runtime/regression integrity | QPX-free `pytest` + `python qpx -i all` |
| historical science characterization unchanged | Issue43/45 + Issue89 + execution-contract guards |

## Integrated acceptance values

These values remain `PENDING` until the independent Batch 7 CI run completes on the exact closeout commit.

```text
ISSUE_150_STATUS = PENDING_REVERIFY
ISSUE_151_STATUS = PENDING_REVERIFY
ISSUE_152_STATUS = PENDING_REVERIFY
ISSUE_147_STATUS = PENDING_REVERIFY
ISSUE_148_STATUS = PENDING_REVERIFY
ISSUE_149_STATUS = PENDING_REVERIFY
ISSUE_146_STATUS = PENDING_REVERIFY
CANONICAL_SELECTED_MODEL_TERM_COUNT = PENDING
AMBIGUOUS_MODEL_FIELDS_IN_CONTROL_PLANE = PENDING
TOP_LEVEL_GENERIC_MODELS_PACKAGE = PENDING
CANONICAL_GRADIENT_RECONSTRUCTION_CAPABILITY_OWNER_COUNT = PENDING
GENERIC_DEFAULT_FACE_CONTRACT_IS_METHOD_SPECIFIC = PENDING
GENERIC_APPLICATION_OPERATIONS_NAMED_GREEN_GAUSS = PENDING
CANONICAL_JACOBIAN_VERIFICATION_OWNER_COUNT = PENDING
GENERIC_EVIDENCE_TO_PETSC_CONCRETE_DEPENDENCY_EDGES = PENDING
VERIFIED_JACOBIAN_MISMATCH_DISTINCT_FROM_RUNTIME_SUSPECT = PENDING
GENERIC_EVIDENCE_TO_CONCRETE_SOLVER_LOG_DECODING_EDGES = PENDING
PF_CAMPAIGN_KEYS_IN_GENERIC_EVIDENCE = PENDING
GENERIC_DIAGNOSTIC_METRICS_REMAIN_BACKEND_NEUTRAL = PENDING
TEMPORAL_OBSERVATION_AND_OUTPUT_MUTATION_OWNERS_ARE_SEPARATE = PENDING
TEMPORAL_STANDALONE_GATEWAY_POLICY = PENDING
CANONICAL_EXPERIMENT_SCHEMA_COUNT = PENDING
PARALLEL_EXPERIMENT_CONTROL_PLANES = PENDING
PUBLIC_MOOSE_INTEGRATION_BOUNDARY_COUNT = PENDING
PRODUCTION_CAMPAIGN_PROTOCOL_MODULES = PENDING
PRODUCTION_DMIX_CAMPAIGN_MODULES = PENDING
PRODUCTION_ELECTRON_INVENTORY_PACKAGES = PENDING
PRODUCTION_ISSUE_COUPLED_DEFAULT_CASES = PENDING
GENERIC_TO_MOOSE_CONCRETE_DEPENDENCY_EDGES = PENDING
CROSS_STREAM_SEMANTIC_RESIDUE_GUARD = PENDING
DEPENDENCY_DIRECTION_GUARDS = PENDING
STRICT_ZERO_LEGACY_CENSUS = PENDING
QPX_FREE_PYTEST = PENDING
QPX_SELF_VALIDATION = PENDING
HISTORICAL_CHARACTERIZATION = PENDING
```

## Scientific scope statement

A PASS for this manifest means the semantic architecture refactor is internally consistent and regression-safe under the repository's architecture/characterization gates. It does **not** create new scientific validation for historical plasma experiments, does not upgrade pending runtime-scientific evidence in #26/#27, and does not alter accepted numerical/physics contracts.
