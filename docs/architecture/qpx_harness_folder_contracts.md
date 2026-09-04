# QPX Harness Folder Contracts

Status: canonical package responsibility contract for `development`.

## Canonical root

```text
repo/
├── bin/
├── qpx_harness/
├── experiments/
├── tests/
├── docs/
└── .github/
```

Other long-lived architectural roots are non-canonical and require an explicit bounded exception or retirement plan.

## Internal responsibility hierarchy

```text
qpx_harness/
├── specification/
├── ontology/
├── planning/
├── execution/
├── adapters/
│   └── moose/
├── observation/
│   └── source_code/
├── analysis/
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

Purpose: realize solver-independent ExecutionPlan as structured MOOSE target IR and deterministic `.i` text.

May own: MOOSE block/object names, serialization, MOOSE-specific PETSc realization when assigned by responsibility.

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

Canonical operator model: `qpx <subcommand> ...`. One canonical implementation lives at `bin/qpx.py`; the root `qpx` file is a compatibility launcher only.

## Dependency contract

```text
specification -> ontology                         ALLOW
semantic compiler -> planning                     FORBID
semantic compiler -> adapters.moose               FORBID
ontology -> adapters.moose                        FORBID by default
planning -> adapters.moose                        FORBID
execution compiler -> planning policy contract    ALLOW
execution compiler -> MOOSE internals             FORBID
adapters.moose -> ExecutionPlan contract          ALLOW
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

## Legacy migration dispositions

```text
qpx_harness/spec        -> semantic user spec migrates to specification; low-level mutation IR becomes internal/legacy
qpx_harness/cpp         -> retire after observation/source_code migration (#139)
qpx_harness/diagnose    -> retire after reasoning/backend/domain-rule split (#140)
qpx_harness/inventory   -> split/retire or explicit domain retention after #141
qpx_harness/dmix        -> split/retire after #141
qpx_harness/performance -> split/retire after #141
recipes/                -> decompose then retire (#138)
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
