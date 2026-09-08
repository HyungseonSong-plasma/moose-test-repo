# QPX Semantic Ownership Review

Semantic input: `QPX_STATE_SEMANTICS_V1`.

## Result

The repository is being normalized around one primary classification axis: **semantic responsibility**. Technology, language, backend, Issue identity, and domain are subordinate qualifiers.

## Canonical responsibility owners

| Responsibility | Canonical owner |
|---|---|
| experiment specification + semantic compilation | `qpx_harness.specification` |
| state/intent semantic projection + persistence/query | `qpx_harness.ontology` |
| planning / capability / ScientificPolicy | `qpx_harness.planning` |
| solver-independent execution compilation + process runtime | `qpx_harness.execution` |
| MOOSE target realization | `qpx_harness.adapters.moose` |
| source-faithful acquisition | `qpx_harness.observation` |
| deterministic quantitative derivation | `qpx_harness.analysis` |
| generic propositions, rules, diagnosis synthesis | `qpx_harness.reasoning` |
| Z3 execution mechanics | `qpx_harness.reasoning.engines` |
| claim/applicability/acceptance evaluation | `qpx_harness.validation` |
| lineage/source identity | `qpx_harness.provenance` |
| reusable scientific meaning | `qpx_harness.domains` |
| workflow coordination | `qpx_harness.application` |
| operator routing/presentation | `qpx_harness.cli` |

## ExperimentSpec collision

Two existing APIs use `ExperimentSpec` for different meanings:

- `application/experiment_spec.py` describes protocol/execution configuration.
- `spec/models.py` describes low-level target mutation operations.

This is `SAME_TERM_DIFFERENT_MEANING`. The canonical future `ExperimentSpec` is the user-facing semantic specification under `qpx_harness.specification`. Low-level operations are internal lowering/compatibility IR and are not canonical user semantics.

## Technology/backend classification

- MOOSE: target-system realization -> `adapters/moose` when code emits/interprets target realization.
- C++: source language, not a package responsibility -> source inspection moves under `observation/source_code`.
- PETSc: classify by responsibility; no blanket `adapters/petsc` owner.
- Z3: reasoning backend mechanics only -> `reasoning/engines/z3.py`.

## Legacy-package dispositions

| Legacy owner | Disposition | Reason |
|---|---|---|
| `qpx_harness/cpp` | RETIRE | language-as-owner axis collision |
| `qpx_harness/diagnose` | RETIRE | mixes semantic rules, diagnosis, evaluator and backend |
| `qpx_harness/inventory` | SPLIT | scientific meaning mixed with analysis/runtime mechanics |
| `qpx_harness/dmix` | SPLIT | parsing/analysis mixed with transport semantics |
| `qpx_harness/performance` | SPLIT | measurement mechanics mixed with interpretation |
| root `recipes/` | RETIRE | Issue/protocol identity cannot own reusable semantics |
| root `qpx` | compatibility wrapper only | canonical operator implementation is `bin/qpx.py` |

## Recipe decomposition

Every recipe responsibility maps to exactly one class:

```text
DECLARATIVE_EXPERIMENT_INTENT -> experiments/.../experiment.json
REUSABLE_POLICY_RULE -> planning or approved domain owner
SCIENTIFIC_DERIVED_VALUE_RULE -> planning/domain + analysis as appropriate
EXECUTION_COMPILATION_RULE -> execution
MOOSE_TARGET_LOWERING_MECHANIC -> adapters/moose
OBSERVATION -> observation
ANALYSIS -> analysis
VALIDATION -> validation
LEGACY_COMPATIBILITY_ONLY -> bounded facade
DEAD_OR_ONE_OFF -> retire
```

A file may split across several owners. A cosmetic `recipes -> scientific_policy` root rename is forbidden.

## Domain normalization

`domains/` contains reusable scientific meaning only. Generic parsing, aggregation, process execution, backend invocation, persistence, target lowering, and CLI routing are extracted first.

Recommended initial scientific subdomains are plasma transport, electrostatics/inventory semantics, and electron-energy semantics when justified by live reusable content. `performance` is not presumed to be a scientific domain; measurement mechanics belong to analysis/execution.

## CLI/application map

Target:

```text
qpx <subcommand>
```

One operator gateway routes through thin application coordination. New experiments using supported semantics require neither a new CLI command nor an Issue-specific protocol-registry entry.

## Migration protocol

All legacy migration uses:

```text
CENSUS -> CLASSIFY -> ADD -> MIGRATE -> VERIFY -> RETIRE -> GUARD
```

No delete-first migration.

## Downstream handoffs

- #130: freeze package paths/contracts and dependency directions from this mapping.
- #134: ontology service lives under `qpx_harness.ontology` and preserves semantic authority.
- #136: one canonical semantic `ExperimentSpec` under `qpx_harness.specification`.
- #137: policy/capability ownership under `qpx_harness.planning`.
- #138: solver-independent plan under execution; MOOSE syntax only in adapter; recipes retire.
- #139: C++ inspection -> observation/source_code.
- #140: diagnose -> reasoning; Z3 isolated; domain rules outside backend.
- #141: split cross-cutting mechanics from domain scientific meaning.
- #142: one canonical qpx gateway and thin application routing.

## Evidence

```text
SEMANTIC_INPUT: QPX_STATE_SEMANTICS_V1
STATUS: PASS
CANONICAL_OWNER_CONFLICTS: 0 in target architecture
UNOWNED_PIPELINE_RESPONSIBILITIES: 0
EXPERIMENTSPEC_CANONICAL_OWNER_COUNT: 1 in target architecture
#130_HANDOFF: READY
#134_HANDOFF: READY
#136_HANDOFF: READY
#137_HANDOFF: READY
#138_HANDOFF: READY
#139_HANDOFF: READY
#140_HANDOFF: READY
#141_HANDOFF: READY
#142_HANDOFF: READY
```
