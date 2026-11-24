# FDEG Functional Contract Graph v0.2

**Owner:** Issue #697; dependent on Structural v0.3 / Issue #696. **Evidence level:** P0 static, source-pinned, review-qualified semantic claims. `SAFE_DELETE=HOLD`.

## Purpose

Consume only the Structural v0.3 evidence graph and reviewed Functional registry so GPT can list, per declared consumer, *what functionality would be removed if it were active*, the known/unknown provider and runtime bindings, candidates' necessary parity dimensions and missing evidence without searching implementation source.

The assembler does not claim a complete dependency census or that a supplied source-bound hypothesis was proven by Native execution. [Transition v0.1](fdeg_transition_evidence_v0_1.md) is a separate assembler; global Coverage and Native equivalence are not established here.

## Input identity

`ci/guards/fdeg_functional.py` now emits `fdeg.functional.v0.2` and requires `fdeg.structural.v0.3` plus `fdeg.functional_registry.v0.2`.

- Validate `repository_head`, all Structural `edge_id` and `graph_id`, instance type and per-binding source line.
- Independently reconstruct Structural v0.3 from exact checked-out source and reject forged generator/provider/build metadata even when `graph_id` was recomputed.
- Bind all existing incumbent claims to pinned C++ source Blob/line and function-local anchors. Failing anchors and changed blobs are hard P0 errors.
- For candidate alternatives with source present locally, attest candidate source Blob/function/anchor; this establishes a candidate expression only, **never equivalence**. Missing candidate source stays `NOT_LOCALLY_SOURCE_VERIFIED`.

## Output

| Graph surface | Meaning / limit |
| --- | --- |
| `parameter_declarations` | Source-bound local `validParams()` declarations, required/optional parameters, C++ type and explicit defaults versus description-only; not effective runtime values or a complete inherited-parameter census |
| `discriminator_contracts` | Reviewed positive/negative experiment specifications; no observed result or accepted tolerance |
| `runtime_observation`, `equivalence_verdict` | `NOT_OBSERVED`, `NOT_PROVEN`; source-supported text/claims are not executed scientific evidence |
| `preservation_contract` | Conditional loss of residual/flux/time contribution, representation, coupled invariants, refusal/counterexamples, related incumbent claim IDs |
| `consumer_contracts[]` | Declared source `instance_id`, structural edge ID, variable/block/raw state_form, local source default, possible producer candidates and `UNKNOWN` effective provider/integrator/state; functional effect **if active** |
| `EQUATION_TERM_OWNER_CONDITIONAL` | Declared input instance maps to an equation term. Does not prove that a Native object was instantiated |
| `EFFECTIVE_FUNCTIONAL_BINDING_CANDIDATE` | Functor name is bound by a source declaration; actual producer is `UNKNOWN` even with a unique same-file candidate |
| `semantic_replacement_diffs[]` | Conditional Old ↔ Candidate comparison: representation, residual formula, sign, units, time state, faces/boundary, limiter/interpolation, AD/Jacobian, defaults, source ownership; each dimension `NOT_EVALUATED` |
| `REQUIRED_DISCRIMINATOR` | One edge per reviewed experiment contract; setup, observable, expected and owner-undefined tolerance; no executed result |
| `generator_consumer_routes` | Static template/type-map paths, tracked output candidates, untracked generated output obligations; no execution proof |
| `producer_binding_graph` | Source candidate list per declared consumer parameter; name match is insufficient to claim a resolved runtime Functor |
| `build_and_header_ownership` | Build configuration candidate, source file co-owners and shared header, not proof that a binary was linked |
| `workflow_execution_routes` | Workflow job/trigger static declarations, not CI runtime provenance |
| `target_scoped_unresolved` | Exact unresolved generator/provider references in the target graph. A missing provider candidate may be declared in included/external input, not necessarily absent |

### Original code1–7 target catalog (historical contract context)

These entries describe the original source-pinned functional obligations, not a current inventory of active Factory classes or retirement status. Consult the owning retirement issues and current source tree before choosing a target.

- **code1:** source-backed Poisson banded term; row-sum-zero and historical both-with-kernel parity remain unverified; ON/OFF Native required.
- **code2:** electron-energy electric work; preserve `PhysicsElectronFluxModel` helper, residual `-E·Gamma_e`, normalized scale and AD derivatives; **no approved replacement**.
- **code3:** signed electron-number source and reaction single ownership, `n_ref`, stoichiometric factors, EI18/EI19 exclusion; `FVCoupledForce` alternative source not locally pinned, equivalence unknown.
- **code4:** signed face drift/upwind and conditional heavy-mass-correction cancellation; local log-molar candidate's expression can be anchored, but mode/representation/limiter parity is not asserted.
- **code5:** four distinct Factory classes in one `.C` source; a 3-of-4 transition **cannot retire the file**. Each has its own source/function scope, parameter declarations, and conditional alternative Diff. Unknown `FVLogMolar*` source does not imply equivalence.
- **code6:** incumbent `rho * dw/dt` vs locally pinned conservative `d(rho w)/dt`. Under an independently established common BE integrator, candidate − incumbent is `(rho_n-rho_old)*w_old/dt`; variable density is a *counterexample* to unconditional equivalence.
- **code7:** `-D_T/T grad(T)·n` with internal/boundary and ON/OFF distinctions; `NVTransportMaterial` `D_T_<species>` remains an independent producer and cannot be deleted merely with the consumer.

## P0 test and usage

```bash
python3 -m unittest discover -s tests -p test_fdeg_structural.py -v
python3 -m unittest discover -s tests -p test_fdeg_functional.py -v

head="$(git rev-parse HEAD)"
python3 ci/guards/fdeg_structural.py \
  --target PhysicsFVMassFractionTimeDerivative \
  --expected-head "$head" --output /tmp/structural.json
python3 ci/guards/fdeg_functional.py \
  --target PhysicsFVMassFractionTimeDerivative \
  --structural /tmp/structural.json --expected-head "$head" \
  --output /tmp/functional.json
```

Structural may exit 2 when it emits an evidence graph with unresolved source paths; the produced JSON may still be assembled by Functional, but **the unresolved conditions remain explicit and retirement remains HOLD**. Code shown is a contract example rather than a claim of executed Physics P3/P4.

P0 negative controls cover missing/tracked generator paths, source and header identity, provider ambiguity/missing/mutated metadata, exact SHA and altered graph ID, dynamic refs, candidate source Blob change, replacement-dimension false PASS, historical vs current and absent runtime evidence.

**No C++ deletion, auto-migration or scientific parity claim.** Transition planning and the general-purpose [Harness Code](../../physics_harness/code/README.md) layer are separate; neither is a substitute for executed runtime evidence.
