# Physics Harness Folder Contracts

Status: current package responsibility locator for `main`; the semantic execution boundary follows the canonical SOL request/runtime architecture.

This file path is retained for compatibility with historical references. The current canonical product/harness naming is `Physics` / `physics_harness`.

## Primary source and support roots

```text
repo/
├── bin/               # CLI entry
├── physics_app/       # local Physics application source
├── physics_harness/   # reusable harness
├── libs/              # independent libraries, including code_lucidity
├── experiments/      # experiment assets
├── tests/            # regression tests
├── docs/             # contracts, guidance and evidence
└── .github/          # repository automation
```

This is a responsibility locator, not an exhaustive allowlist of root directories. Repository automation, CI, operational support, specifications, studies, reports and retained historical material have separate scopes.

## Internal responsibility hierarchy

```text
physics_harness/
├── specification/
├── ontology/
├── planning/
├── execution/
├── adapters/
│   └── moose/
├── observation/
│   └── source_code/
├── analysis/
├── evaluation/
├── evidence/
├── code/
├── reasoning/
│   └── engines/
├── validation/
├── provenance/
├── domains/
├── application/
└── cli/
```

Legacy packages may exist only during bounded migration and must not remain competing semantic authorities.

## `specification`

Purpose: strict user-facing experiment schema, loading, capability-reference validation, and deterministic semantic compilation.

May own: `ExperimentSpec`, loader, semantic compiler, specification error codes.

Must not own: ScientificPolicy synthesis, ExecutionPlan construction, MOOSE/PETSc target syntax, process execution.

Allowed: `specification -> ontology` semantic constructors/services.

Forbidden: `specification -> adapters.moose`, target mutation syntax in canonical JSON.

## `ontology`

Purpose: DevelopmentState/ExperimentIntent semantic representation, stable identity, state construction, persistence/query projection, semantic versioning.

May own: semantic records and bounded Owlready2 service/projection.

Must not own: numerical algorithms, Z3 diagnosis, process execution, dense numerical payloads, target lowering.

Forbidden by default: `ontology -> adapters`.

## `planning`

Purpose: CapabilityDescriptor, ActionSpec/SearchDecision, policy rules, ScientificPolicy synthesis.

May own: solver-independent planning and reusable semantic derivations.

Must not own: MOOSE syntax, process invocation, validated-claim mutation without evidence.

Forbidden: `planning -> adapters.moose`.

## `execution`

Purpose: solver-independent ExecutionPlan compilation plus generic workspace/process mechanics and immutable execution events/status/outcomes.

May own: execution compiler, execution bounds, generic runner.

Must not own: scientific policy meaning, target-specific object syntax, scientific acceptance.

Allowed: execution compiler consumes ScientificPolicy contract.

Forbidden: execution compiler imports MOOSE implementation details.

## `adapters/moose`

Purpose: local MOOSE input, preflight, runtime observation and regression utilities. Existing target/IR helpers do not authorize the retired canonical local-lowering route.

Canonical semantic execution uses explicit `CanonicalRealizationModel` and Physics-to-SOL capability mapping to prepare a SOL request through `application/gateway.py`. The pinned SOL runtime consumer and external `sol-adapter-moose` own the canonical runtime and native realization boundary. The CLI does not silently fall back to local lowering. See [current tutorial](../guides/physics_harness_tutorials.md) and [pinned runtime consumer](../sol-runtime-consumer-v02.md).

Must not own: ScientificPolicy meaning, generic reasoning, claim acceptance.

## `observation`

Purpose: source-faithful acquisition/extraction/normalization.

May own: source-code inspection and runtime source parsing.

Must not own: causal interpretation or claim acceptance.

`observation/source_code/cpp.py` is generic C++ inspection only. MOOSE-specific source interpretation is separately identifiable.

## `analysis`

Purpose: deterministic quantitative derivation and aggregation.

May own: DerivedFact computation, numerical summaries.

Must not own: source-faithful acquisition, causal diagnosis, target lowering.

## `evaluation`, `evidence`, `code`

- `evaluation/` owns statistics data contracts.
- `evidence/` owns evidence schema, identity, artifact records, storage and normalization.
- [`code/`](../../physics_harness/code/README.md) owns source-bound graph diagnostics, code analysis, refactor planning and verification. Source evidence does not establish scientific acceptance or automatic safe deletion.

## `reasoning`

Purpose: propositions/assessments, backend-neutral rules, DiagnosticConclusion representation/synthesis.

May own: generic reasoning IR and diagnosis semantics.

Must not own: scientific/domain thresholds as generic truth, Z3-specific mechanics in semantic modules, target adapters.

### `reasoning/engines`
Backend mechanics only. `z3.py` may translate neutral predicates, invoke Z3, and return mechanical decisions. It may not define scientific meaning.

Domain scientific rule -> direct Z3 import is forbidden.

## `validation`

Purpose: claim/applicability/acceptance evaluation.

May own: ClaimAssessment computation and acceptance criteria execution.

Must not own: observation acquisition, process execution, ontology vocabulary redefinition.

## `provenance`

Purpose: stable source identity, lineage, hashes, artifact references.

May own: provenance envelope/records and lineage services.

Must not own: dense payload storage semantics beyond references.

## `domains`

Purpose: reusable scientific/domain meaning only.

May own: domain capability definitions, scientific parameters/constraints, domain reasoning/policy rules expressed through generic IR.

Must not own: generic parsers, generic aggregation frameworks, process runners, Z3 invocation, MOOSE lowering, CLI.

## `application`

Purpose: thin use-case coordination across canonical capabilities.

May own: orchestration of specification -> ontology -> planning -> execution -> observation/validation workflows.

Must not own: duplicate scientific policy, duplicate process runner, target lowering, domain rules.

## `cli`

Purpose: argument parsing, bounded routing, presentation, exit-code mapping.

Must not own: scientific thresholds/policy, target lowering, ontology vocabulary, reasoning backend, process execution implementation.

Canonical operator model: `physics <subcommand> ...`. One canonical implementation lives at `bin/physics.py`; the root `physics` file is a compatibility launcher only.

## Dependency contract

```text
specification -> ontology                         ALLOW
semantic compiler -> planning                     FORBID
semantic compiler -> adapters.moose               FORBID
ontology -> adapters.moose                        FORBID by default
planning -> adapters.moose                        FORBID
execution compiler -> planning policy contract    ALLOW
execution compiler -> MOOSE internals             FORBID
local MOOSE utility -> explicit local contract    ALLOW
canonical semantic gateway -> local MOOSE lowering FORBID
adapter -> redefine semantic meaning              FORBID
observation -> domain interpretation              FORBID by default
domain rule -> backend-neutral reasoning IR       ALLOW
domain rule -> z3                                 FORBID
reasoning semantic owner -> target adapter        FORBID
query -> mutate committed semantic state          FORBID
execution mechanic -> scientific acceptance       FORBID
cli -> domain reasoning backend                   FORBID
application -> duplicate process execution        FORBID
```

## Historical migration dispositions

The following `qpx_harness` paths are historical migration identifiers. They are retained here only so old issue/refactor evidence remains interpretable; they are not current canonical package names.

```text
qpx_harness/spec        -> semantic user spec migrated to specification; low-level mutation IR became internal/legacy
qpx_harness/cpp         -> retired after observation/source_code migration (#139)
qpx_harness/diagnose    -> retired after reasoning/backend/domain-rule split (#140)
qpx_harness/inventory   -> split/retired or explicit domain retention after #141
qpx_harness/dmix        -> split/retired after #141
qpx_harness/performance -> split/retired after #141
recipes/                -> decomposed then retired (#138)
```

## Migration protocol

```text
M0 CENSUS
M1 CLASSIFY
M2 ADD canonical destination
M3 MIGRATE callers
M4 VERIFY equivalence + zero legacy authority
M5 RETIRE
M6 GUARD
```

Hard rule: understand -> add owner -> redirect -> prove -> retire.
