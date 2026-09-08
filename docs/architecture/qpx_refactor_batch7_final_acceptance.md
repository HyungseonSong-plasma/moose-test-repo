# Batch 7 final umbrella acceptance — #145 semantic architecture cleanup

Status: **PASS — INTEGRATED CLOSEOUT ACCEPTED**

This document is the integrated acceptance manifest for #145 Batch 7. Batch 7 is acceptance-only: it does not introduce numerical, solver, plasma-physics, or historical experiment behavior changes.

## Baseline and independent validation

The closeout review started from the post-Batch-6 `development` state:

```text
development baseline = ea43169fb1d53321bc06ec874d3f2e8894a240ca
```

All seven implementation child issues were closed before this review:

```text
#146 MOOSE boundary consolidation
#147 canonical experiment control plane
#148 plasma semantic generalization
#149 campaign/performance/scale residue cleanup
#150 canonical model terminology
#151 gradient-reconstruction ownership
#152 Jacobian-verification ownership
```

Their closure was treated only as prerequisite evidence. Batch 7 independently reran the integrated architecture/regression gates on one post-Batch-6 tree containing only this closeout manifest as a new file.

First integrated closeout run:

```text
commit = 1232118c8a8202fe81812a74b246a1fb54d131ca
branch = review/development-semantic-architecture
workflow = QPX CI validation
run = 34021744227
conclusion = success
QPX-free pytest = 255 passed
scientific EVR consumed by closeout characterization = 0
```

## Independent closeout sequence

The run executed, in one workflow job:

```text
1. Evidence dependency guard
2. Analysis dependency guard
3. Execution dependency guard
4. Presentation dependency guard
5. canonical package cycle guard
6. declarative experiment-control-plane guard
7. plasma semantic ownership guard
8. campaign/performance/scale ownership guard
9. numerical-method ownership guard
10. model terminology + MOOSE boundary guard
11. strict zero-legacy architecture census
12. QPX-free pytest
13. canonical `python qpx -i all`
14. frozen Issue43/45 historical characterization guard
15. frozen Issue89 historical characterization guard
16. execution-contract characterization guard
```

The canonical CI owner is `.github/workflows/qpx-cleanup-validation.yml`.

## Cross-cutting source census

Two #145 umbrella claims are intentionally broader than a single printed guard counter, so Batch 7 also inspected their current owners directly.

### Generic diagnostic metrics remain backend-neutral

`qpx_harness/analysis/diagnostic_metrics.py` owns deterministic aggregation over normalized frames and imports only generic data/model dependencies (`polars`, Pydantic, standard-library types). It does not import MOOSE/PETSc adapters, campaign policy, or solver log decoders. Dependency, campaign-residue, and MOOSE-boundary guards all pass on the same tree.

### Temporal observation and output mutation remain separate

Read-only temporal trajectory observation and CSV normalization are owned by `qpx_harness/analysis/temporal.py`; `observe_temporal_csv` explicitly never modifies its source. Application-level composition is exposed through `normalize_temporal_run_csv` in `qpx_harness/application/operations.py`.

Concrete MOOSE output mutation is separately owned by `qpx_harness/adapters/moose/output_observation.py`. The canonical experiment gateway in `qpx_harness/application/gateway.py` owns experiment compile/plan/lower flow and does not create a parallel standalone temporal gateway. Therefore the temporal policy is explicit: generic temporal normalization is an application operation; concrete output mutation stays behind the MOOSE adapter boundary.

## Acceptance ownership map

| #145 closeout claim | Independent owner/evidence |
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
| generic diagnostic-metric neutrality | source census + analysis/campaign/MOOSE-boundary guards |
| temporal ownership separation | source census + application/analysis/MOOSE-boundary guards |
| generic runtime/regression integrity | QPX-free `pytest` + `python qpx -i all` |
| historical science characterization unchanged | Issue43/45 + Issue89 + execution-contract guards |

## Integrated acceptance values

```text
ISSUE_150_STATUS = PASS
ISSUE_151_STATUS = PASS
ISSUE_152_STATUS = PASS
ISSUE_147_STATUS = PASS
ISSUE_148_STATUS = PASS
ISSUE_149_STATUS = PASS
ISSUE_146_STATUS = PASS

CANONICAL_SELECTED_MODEL_TERM = model_ref
CANONICAL_SELECTED_MODEL_TERM_COUNT = 1
AMBIGUOUS_MODEL_FIELDS_IN_CONTROL_PLANE = 0
TOP_LEVEL_GENERIC_MODELS_PACKAGE = 0

CANONICAL_GRADIENT_RECONSTRUCTION_CAPABILITY_OWNER_COUNT = 1
GENERIC_DEFAULT_FACE_CONTRACT_IS_METHOD_SPECIFIC = 0
GENERIC_APPLICATION_OPERATIONS_NAMED_GREEN_GAUSS = 0
CANONICAL_JACOBIAN_VERIFICATION_OWNER_COUNT = 1
GENERIC_EVIDENCE_TO_PETSC_CONCRETE_DEPENDENCY_EDGES = 0
VERIFIED_JACOBIAN_MISMATCH_DISTINCT_FROM_RUNTIME_SUSPECT = PASS

GENERIC_EVIDENCE_TO_CONCRETE_SOLVER_LOG_DECODING_EDGES = 0
PF_CAMPAIGN_KEYS_IN_GENERIC_EVIDENCE = 0
GENERIC_DIAGNOSTIC_METRICS_REMAIN_BACKEND_NEUTRAL = PASS

TEMPORAL_OBSERVATION_AND_OUTPUT_MUTATION_OWNERS_ARE_SEPARATE = PASS
TEMPORAL_STANDALONE_GATEWAY_POLICY = EXPLICIT_APPLICATION_OPERATION_NOT_PARALLEL_GATEWAY

CANONICAL_EXPERIMENT_SCHEMA_COUNT = 1
PARALLEL_EXPERIMENT_CONTROL_PLANES = 0
PRODUCTION_CAMPAIGN_PROTOCOL_MODULES = 0

PUBLIC_MOOSE_INTEGRATION_BOUNDARY_COUNT = 1
PRODUCTION_DMIX_CAMPAIGN_MODULES = 0
PRODUCTION_ELECTRON_INVENTORY_PACKAGES = 0
PRODUCTION_ISSUE_COUPLED_DEFAULT_CASES = 0
GENERIC_TO_MOOSE_CONCRETE_DEPENDENCY_EDGES = 0

CROSS_STREAM_SEMANTIC_RESIDUE_GUARD = PASS
DEPENDENCY_DIRECTION_GUARDS = PASS
STRICT_ZERO_LEGACY_CENSUS = PASS
QPX_FREE_PYTEST = PASS (255 passed)
QPX_SELF_VALIDATION = PASS
HISTORICAL_CHARACTERIZATION = PASS
```

Additional machine-observed closeout facts:

```text
EXPERIMENT_CONTROL_PLANE_GUARD = PASS
schema_version = 2
canonical_specs = 1
protocol_dispatch = 0

PRODUCTION_DMIX_CAMPAIGN_SYMBOLS = 0
SINGLE_SPECIES_HARDCODED_INVENTORY_APIS = 0
SPECIES_CONSTRAINT_CAPABILITIES_ARE_PARAMETERIZED = true
PRODUCTION_ISSUE_SPEC_DEPENDENCIES = 0
CAMPAIGN_FIXTURES_IN_DOMAIN_OWNERS = 0

PRODUCTION_PF_CAMPAIGN_API_IDENTITIES = 0
PRODUCTION_QVT_POLICY_ANCHORS_IN_GENERIC_ANALYSIS = 0
GENERIC_PERFORMANCE_TO_CONCRETE_SOLVER_INTROSPECTION_EDGES = 0
CAMPAIGN_BRANDING_IN_GENERIC_MODULE_IDENTITY = 0

PETSC_JACOBIAN_DIAGNOSTIC_PARSER_OWNER_COUNT = 1
JACOBIAN_COMPARISON_EVIDENCE_CONTRACT_COUNT = 1
JACOBIAN_CORRECTNESS_POLICY_OWNER_COUNT = 1
COUPLED_SOLVER_JACOBIAN_CORRECTNESS_DUPLICATION = 0

PARALLEL_MOOSE_ROOTS = 0
MOOSE_INPUT_REALIZATION_OWNER_COUNT = 1
MOOSE_SYNTAX_MUTATION_OWNER_COUNT = 1
MOOSE_OUTPUT_DECODER_OWNER_COUNT = 1

ISSUE70_UNCLASSIFIED = 0
ISSUE70_GENERIC_TO_ISSUE_EDGES = 0
ISSUE128_FORBIDDEN_PRODUCTION_NAMESPACES = 0
ISSUE70_MODULE_PACKAGE_COLLISIONS = 0
ISSUE129_ROOT_MODULES = 0
ISSUE143_LEGACY_NAMESPACES_PRESENT = 0
ISSUE143_EXTERNAL_LEGACY_IMPORTS = 0
ISSUE143_ZERO_LEGACY = PASS
ISSUE144_ROOT_RECIPES_PHYSICALLY_REMOVED = PASS
ISSUE144_CANONICAL_EXPERIMENTSPEC_OWNER_COUNT = 1
ISSUE70_ARCHITECTURE_CENSUS = PASS

ISSUE43_45_SCIENCE_REFACTOR_GUARD = PASS
ISSUE89_POST_SCIENCE_CANONICALIZATION_GUARD = PASS
EXECUTION_CONTRACT_REFACTOR_GUARD = PASS
SCIENTIFIC_EVR_CONSUMED = 0
```

## Closure interpretation

The #145 semantic-architecture campaign is accepted when this final manifest is present and the final manifest commit itself passes the same integrated CI route. No additional architecture child issue is required by this census.

## Scientific scope statement

This PASS means the semantic architecture refactor is internally consistent and regression-safe under the repository's architecture/characterization gates. It does **not** create new scientific validation for historical plasma experiments, does not upgrade pending runtime-scientific evidence in #26/#27, and does not alter accepted numerical/physics contracts.
