# Batch 6 canonical ownership manifest

- Selected simulation-model reference term: `model_ref` end-to-end.
- Canonical MOOSE integration boundary: `qpx_harness/adapters/moose/`.
- Semantic lowering: `adapters/moose/target.py`.
- HIT syntax/parser/render primitives: `adapters/moose/input.py`, `blocks.py`, `parameters.py`.
- Declarative mutation schema/application: `adapters/moose/mutation_spec/` and `adapters/moose/transforms.py`.
- Runtime/preflight/regression: `adapters/moose/preflight.py`, `regression.py`, `executioner.py`, `dofmap.py`.
- MOOSE log/output decoding: `adapters/moose/log.py`, `nonlinear_solver.py`, `output_observation.py`.
- MOOSE-specific PETSc option mutation: `adapters/moose/petsc_options.py`. Pure PETSc diagnostic parsers remain under `qpx_harness/petsc/`.
- Normalized run/evaluation contracts: `qpx_harness/evaluation/statistics.py`.
- Semantic ontology records: `qpx_harness/ontology/records.py`.
- MOOSE mutation-spec records: `qpx_harness/adapters/moose/mutation_spec/schema.py`.

Allowed direction: semantic specification/planning/execution IR -> public MOOSE adapter -> concrete solver syntax/runtime -> decoded observations/evidence. Generic evidence/analysis/reasoning must not import concrete MOOSE mechanics. Exact MOOSE/QPX/PETSc identifiers remain valid only where they represent external contracts.
