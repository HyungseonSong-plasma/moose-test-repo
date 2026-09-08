# Domain Normalization Migration Manifest

Authority: #130/#133. Scope: #141 quick migration pass on `development`.

## Rule

`domains/` owns reusable scientific meaning only. Parsing, quantitative derivation, generic reasoning, process execution, persistence, target realization, CLI, and application orchestration remain cross-cutting responsibility owners.

## D_mix

| Surface | Primary responsibility | Canonical owner | Legacy disposition |
|---|---|---|---|
| `dmix/analysis.py` constants/species/trace contract | plasma transport scientific meaning | `domains/plasma/transport` | SPLIT |
| `dmix/analysis.py::read_dmix` | source/result observation | observation | MOVE candidate |
| `dmix/analysis.py::compare` | quantitative derivation | analysis | MOVE candidate |
| `dmix/analysis.py::trace_input` | controlled test/input transformation | execution/adapter compatibility | classify per caller |
| `dmix/characterization.py` | characterization/analysis | analysis | MOVE |
| `dmix/runtime.py` | process/runtime mechanics | execution | MOVE |
| `dmix/source_transform.py` | source transformation mechanic | observation/adapter depending target semantics | SPLIT |

Scientific constants extracted now:

```text
qpx_harness/domains/plasma/transport/
  OXYGEN_HEAVY_SPECIES
  DMIX_EQUIVALENCE_REL_TOL
  DMIX_TRACE_MASS_FRACTIONS
```

The legacy `dmix/` package remains bounded compatibility during caller migration; it is not canonical semantic authority after this manifest.

## Inventory

Current inventory surfaces mix at least four concerns:

```text
closure scientific semantics            -> plasma electrostatics/inventory domain + validation
closure/first-linear quantitative data  -> analysis
runtime/check-input/process mechanics    -> execution / adapters/moose
CLI/orchestration                        -> cli/application
```

Representative dispositions:

| Legacy surface | Classification | Future owner |
|---|---|---|
| `inventory/closure_model.py` | DOMAIN_SCIENTIFIC_KNOWLEDGE + validation contract | domain/validation split |
| `inventory/closure_schema.py` | representation/projection | domain/validation projection |
| `inventory/closure_runtime.py` | EXECUTION | execution |
| `inventory/first_linear_stats.py` | ANALYSIS value record | analysis |
| `inventory/first_linear_characterization.py` | ANALYSIS | analysis |
| `inventory/first_linear_orchestration.py` | APPLICATION_ORCHESTRATION | application |
| `inventory/cli.py` | CLI | cli |

The legacy package remains compatibility-only until current callers are redirected. No new reusable capability may be added there.

## Performance

`performance/` is not automatically a scientific domain. Default classification:

```text
measurement/profiling mechanics -> execution/analysis
quantitative aggregation        -> analysis
scientific interpretation       -> domain/reasoning only when genuinely reusable
CLI                              -> cli
```

The legacy `performance/` package remains compatibility-only during migration and may not acquire new semantic authority.

## Canonical domain packages retained/created in this pass

```text
qpx_harness/domains/plasma/transport
```

Further electrostatics/electron-energy packages should be created only when concrete live scientific symbols are migrated, not as empty taxonomy placeholders.

## Guard condition

New code must not import CLI, direct Z3 backend, generic process runtime, or MOOSE target syntax into `qpx_harness/domains`.

## Evidence

```text
STATUS: PASS_WITH_BOUNDED_COMPATIBILITY
LEGACY_INVENTORY_DISPOSITION: SPLIT / compatibility-only during caller migration
LEGACY_DMIX_DISPOSITION: SPLIT / compatibility-only during caller migration
LEGACY_PERFORMANCE_DISPOSITION: SPLIT / compatibility-only during caller migration
DOMAIN_PACKAGES_CREATED_OR_RETAINED: [domains/plasma/transport]
UNMAPPED_RESPONSIBILITY_CLASSES: 0 at package-level quick census
CROSS_CUTTING_CODE_AUTHORIZED_AS_NEW_DOMAIN_OWNER: 0
SCIENTIFIC_SEMANTICS_CHANGED: false
```
