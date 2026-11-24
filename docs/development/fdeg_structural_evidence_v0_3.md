# FDEG Structural Evidence v0.3

**Owner:** Issue #696 (updated code1–7 requirements on #691). **Scope:** source-only graph evidence, not runtime/retirement.

## Versioned JSON contract

`ci/guards/fdeg_structural.py` emits `fdeg.structural.v0.3`, the Structural schema consumed by Functional v0.2. The base contract includes:

- Directed nodes and `edges[]` with `from`, `to`, `relation`, `strength`, `detail` and path/line/blob/excerpt `evidence`.
- Exact `repository_head`, content-addressed `graph_id` and `edge_id` (not persistent IDs across changed evidence).
- `instances[]` records identify declared input instances by `instance_id`, input/block path, Factory type, type line, structural edge, raw parameter bindings and source blob. `DECLARES_INSTANCE` and `INPUT_INSTANTIATES` are source declarations, not Native activation.
- Declared bindings and includes are not effective defaults, resolved Functors or evaluated include expansions. Dynamic, generated, overridden and external consumers retain unresolved coverage obligations.

Additional source surfaces:

- Each edge now has `source_head`, `revision_scope`, `reference_role`, and `activation_status=NOT_OBSERVED`.
- `enrichment.build_ownership[]`: `physics_app/Makefile`/app.mk declaration `BUILD_OWNS_SOURCE`, not proof of successful compilation/linking.
- `enrichment.shared_translation_units[]`: one C++ source and **all registered Factory classes** (code5 has four). Keep whole file until each owner is independently discharged.
- `INCLUDES_OWNER_HEADER`, `HEADER_DECLARES_TARGET`: link multi-class shared headers by C++ includes and declarations even when header basename != class name.
- `enrichment.generator_routes[]`: source-bound Python literal map, DictComp/f-string key pattern and input template candidate. `GENERATOR_EMITS_OBJECT_CANDIDATE` does **not** assert generated artifacts or runtime. Static tracked writers connect through `PYTHON_WRITES_INPUT`; unknown/untracked paths create explicit unresolved records.
- `enrichment.provider_bindings[]`: consumer `instance_id` + parameter + declared value, `BINDS_PARAMETER` through functor name, `PRODUCES_FUNCTOR_CANDIDATE` from same-file material declaration. `effective_provider=UNKNOWN` even when a single candidate matches. Missing/ambiguous property names fail closed. `NVTransportMaterial` `D_T_names` default naming is a **candidate**, not an observed runtime binding.
- `enrichment.workflow_execution_paths[]`: declared job and trigger from workflow, script command, and source witness. `WORKFLOW_RUNS_SCRIPT` / `SHELL_RUNS_SCRIPT` denote static reachability only.
- `enrichment.external_imports[]`: named external generator/import dependencies with source evidence and an unresolved source path; never infer their implementation.
- `target_scoped_unresolved[]`: unresolved input/provider/generator facts on paths participating in the selected target graph, in addition to full `unresolved[]` for global parser observability.

### Scope / evidence strength

`CURRENT_SOURCE_NOT_PROVEN_ACTIVE`, `TEST_OR_CHECKER_ONLY`, `HISTORICAL_SOURCE_NOT_PROVEN_ACTIVE`, and `WORKFLOW_DECLARATION` are **source-location classifications**, not an ACTIVE runtime verdict. `SOURCE_INCLUDE_ONLY`, `BUILD_CONFIG_CANDIDATE`, `STATIC_TEMPLATE_NOT_EXECUTED`, `DECLARED_BINDING_ONLY`, and `DECLARED_PROVIDER_ONLY` cannot be promoted to `RUNTIME_REACHABLE`.

`FUNCTOR_PROVIDER_NOT_PROVEN`, `GENERATED_INPUT_NOT_TRACKED_OR_OBSERVED`, dynamic and nontracked paths remain `UNKNOWN` / HOLD. A provider may be defined in an included input or in an external artifact not examined by the local same-file candidate scanner; a missing candidate is **not** proof that a provider does not exist.

## P0 invocation

```bash
python3 -m unittest discover -s tests -p test_fdeg_structural.py -v
python3 ci/guards/fdeg_structural.py \
  --target PhysicsFVMassFractionTimeDerivative \
  --expected-head "$(git rev-parse HEAD)" \
  --output /tmp/fdeg-structural.json
```

`STRUCTURAL_RECORDED` establishes source extraction only. `INCOMPLETE` with unresolved contracts is expected for many historical generator paths. The CLI returns 2 on incomplete reports but still writes JSON; Functional may consume that report while preserving unresolved gating. Neither code path can issue a deletion/transition/physics-PASS decision. Transition v0.1 is a separate conditional planning assembler; global Coverage/caller-zero and runtime proof remain outside this source contract.

## Current cross-module contract

[Functional v0.2](fdeg_functional_contract_v0_2.md) consumes Structural v0.3 at the same exact HEAD, validates graph/edge/instance identities and reconstructs source evidence. [Transition v0.1](fdeg_transition_evidence_v0_1.md) consumes those matching reports for conditional migration planning. Regenerate obsolete-schema reports at the relevant exact revision; do not relabel them. See [A–D remediation](fdeg_harness_abcd_remediation.md) for later scope and lifecycle refinements. The current general-purpose Code Diagnostics/Analysis framework is documented separately in [Harness Code](../../physics_harness/code/README.md); it does not automatically replace FDEG validation.
