# Root Recipes Decomposition / Retirement Manifest

Scope: #138 quick migration pass on `development`.

## Decision

Root `recipes/` is no longer a canonical semantic owner. Existing files are bounded legacy compatibility until caller migration proves deletion safe. New reusable semantics MUST NOT be added under `recipes/`.

Canonical destinations:

```text
DECLARATIVE_EXPERIMENT_INTENT     -> experiments/.../experiment.json
REUSABLE_SEMANTIC_COMPILATION    -> qpx_harness/specification
REUSABLE_POLICY_RULE             -> qpx_harness/planning or approved domain owner
SCIENTIFIC_DERIVED_VALUE_RULE    -> planning/domain + analysis as appropriate
EXECUTION_COMPILATION_RULE       -> qpx_harness/execution
MOOSE_TARGET_LOWERING_MECHANIC   -> qpx_harness/adapters/moose
OBSERVATION                      -> qpx_harness/observation
ANALYSIS                         -> qpx_harness/analysis
VALIDATION                       -> qpx_harness/validation
LEGACY_COMPATIBILITY_ONLY        -> root recipes during bounded migration only
DEAD_OR_ONE_OFF                  -> RETIRE
```

## Current recipe families

| Recipe family | Embedded responsibility | Canonical destination / action |
|---|---|---|
| `issue26_e1.py` | Issue-specific experiment intent + MOOSE mutation | intent -> experiment JSON; lowering -> adapter; compatibility bounded |
| `issue26_e2a.py` | controlled diffusion intent/policy/lowering | intent -> semantic JSON; control/treatment synthesis -> planning; target spelling -> adapter |
| `issue26_energy_chain.py` | multi-stage experiment/policy orchestration | semantic case declarations -> JSON; reusable action selection -> planning; execution ordering -> execution |
| `issue31_coupling.py` | electrostatic/coupling intent + target construction | intent -> JSON/domain semantics; lowering -> adapter |
| `issue31_r4*.py` | derived charge/electrostatic scientific rules + execution construction | domain/planning/analysis split; lowering -> adapter |
| `issue43_coupling_diagnostic.py` | diagnostic intent/observation/analysis | JSON + observation/analysis |
| `issue43_execution_contract.py` | execution/acceptance contract | execution + validation |
| `issue43_fast_relaxation.py` | experiment/policy + target execution | JSON/planning/execution/adapter split |
| other `issue*.py` recipes | historical protocol ownership | classify by same responsibility slices; no Issue-number canonical API |

## Representative migration implemented

A canonical semantic E2a-style experiment is added under:

```text
experiments/semantic/electron_energy_diffusion/experiment.json
```

It expresses controlled electron-energy diffusion without MOOSE block paths, object class names, or PETSc mutation syntax. Policy synthesis generates control/treatment `ActionSpec`s; execution compilation produces solver-independent `ExecutionPlan`; MOOSE spelling is downstream of the adapter boundary.

## Low-level operation language

The old `qpx_harness/spec` low-level operations remain compatibility/internal IR only. They are not canonical user-facing Experiment Specification semantics.

Canonical schema under `qpx_harness/specification` explicitly rejects target mutation vocabulary such as:

```text
ensure_block
set_parameter
replace_block
insert_child_block
add/remove PETSc flags/options
FVKernels/FunctorMaterials/Executioner paths
```

## Retirement condition

Root `recipes/` may be physically deleted when all current production callers satisfy both:

```text
1. supported capability route exists through specification -> planning -> execution -> adapter
2. remaining recipe import count == 0 (historical docs excluded)
```

Until that gate, it is a compatibility-only surface and is forbidden from owning new semantics.

## Evidence

```text
STATUS: PASS_WITH_BOUNDED_COMPATIBILITY
EXECUTION_PLAN_OWNER: qpx_harness.execution.plan.ExecutionPlan
EXECUTION_COMPILER_OWNER: qpx_harness.execution.compiler.compile_execution_plan
MOOSE_ADAPTER_OWNER: qpx_harness.adapters.moose
ROOT_RECIPES_CANONICAL_AUTHORITY: false
ROOT_RECIPES_PHYSICALLY_RETIRED: false
CANONICAL_JSON_LOW_LEVEL_MOOSE_OPS: 0
PETSC_AUTOMATIC_ADAPTER_OWNER_CREATED: false
SCIENTIFIC_SEMANTICS_CHANGED: false
```
