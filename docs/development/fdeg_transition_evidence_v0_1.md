# FDEG Transition Evidence v0.1 — conditional migration evidence

> **Historical design record (#881).** The standalone subsystem is being retired. Commands and contracts below describe the original implementation at [pre-retirement revision 7a119106](https://github.com/HyungseonSong-plasma/moose-test-repo/tree/7a119106a22f2de2ca5c761a4119f00509e0efdd); they are not current CI instructions. See [historical provenance](archive/issue881_fdeg/README.md) and [Harness Code](../../physics_harness/code/README.md).

**Status:** P0 design/implementation for Issue #701. **Depends on:** Structural v0.3 (#698) and Functional v0.2 (#700). **Out of scope:** executed migration, Coverage/caller-zero, scientific acceptance, source/Factory deletion.

## Purpose and authority

This module is a **read-only evidence assembler**. It does not choose a replacement, synthesize modified MOOSE inputs, run Native physics or declare SAFE_DELETE. It describes what a GPT/human planner can infer *only from supplied Structural + Functional graphs and reviewed requirements*, with a complete list of known stopping conditions.

Use `ci/guards/fdeg_transition.py` with `ci/baselines/fdeg_transition_contracts.json` and the two source-bound evidence reports. Static candidates, lexical references, generated input templates, workflow commands and Functor names are **not** observed runtime consumers. A graph-only conditional plan is not an executable retirement permission.

## Identity and validation contract

`fdeg.transition.v0.1` requires:
- `fdeg.structural.v0.3` and `fdeg.functional.v0.2` from the same exact HEAD;
- the Functional report's original `functional-graph` SHA-256 identity and each `functional-edge` identity;
- matching Structural `graph_id`, target, HEAD, instance/edge references;
- **independent reassembly** through `fdeg_functional.assemble()`, which itself verifies and reconstructs Structural from source, and checks C++ blob/anchor and candidate source witnesses;
- exact source-blob identity of reviewed Transition policy when CLI is called with `--expected-head`, a clean tracked checkout, and valid policy status. Registry review requirements are **not** execution acceptance.

Reject forged graph IDs, rehashed fake provider/instance records, mutated source/blob/claim, stale HEAD, changed candidate `HOLD` to `PASS`, or claimed runtime `PASS`. Do **not** downgrade these to a warning.

## Output contract

- `source_identity`: exact `repository_head`, Structural/Functional graph IDs and schema versions, policy blob SHA;
- `consumer_dispositions`: one entry per direct/generated/Action/lexical consumer relation in Functional's target-rooted graph; references `structural_edge_id` and `instance_id`, before raw bindings, unknown effective provider, proposed candidate options, `HOLD_UNKNOWN` / `PRESERVE_HISTORICAL` / `REFERENCE_ONLY`, proposed rather than executed work;
- `candidate_rewiring_options`: typed candidates, policy-reviewed proposed parameter mapping, Functional 10-dimension diff and provenance, always `CANDIDATE_UNVERIFIED`;
- `change_sites`: declared input sites, generator sources, **unobserved** output path candidates, workflow/static checker sites and C++ translation units, not automatically authorized edit operations;
- `protected_resources`: independent shared helpers, chemistry owners, historical artifacts, Material/Functor producers, or four-class C++ translation units that must not be silently deleted;
- `blocking_obligations`: machine-readable `{obligation_id, object, consumer, kind, required_evidence, gate, oracle, owner, status=OPEN, origin_ref}` with negative reasons and evidence origin;
- `steps[]`: dependency DAG, with **per-consumer** `REWIRE_CONSUMER_CANDIDATE:<structural_edge_id>` (unverified option), no-edit `RETAIN_CONSUMER_UNTIL_APPROVAL:<structural_edge_id>` (no approved owner), or no-edit `PRESERVE_HISTORICAL_CONSUMER:<structural_edge_id>` tasks between qualification and aggregate rewire/verification. Each task has its own `consumer_id`, `instance_id`, `structural_edge_id`, before/after proposal, paths, exact-HEAD rollback, preconditions, required evidence and only *proposed* graph delta. Independent P0/P1/P2/P3/history/Coverage gates remain unexecuted. All steps are `PLANNED`, `NOT_EXECUTED`, `eligible_to_execute=false`;
- `edges[]`: `HAS_DISPOSITION`, `REWIRES_TO` (unverified candidate), `PRESERVES`, `DEPENDS_ON_STEP`, `BLOCKED_BY`, `REQUIRES_EVIDENCE`, `ROLLBACK_TO`, with canonical `transition-edge` IDs and `transition-graph` ID.

No output in this version may say `CALLER_ZERO`, `NUMERICALLY_VERIFIED`, `SAFE_DELETE` PASS or actually APPLIED. A scanned zero-consumer graph must emit an explicit `NO_IDENTIFIED_CONSUMERS_IS_NOT_CALLER_ZERO` blocker.

### Case-specific constraints

| Review | Distinguishing Transition v0.1 obligation |
| --- | --- |
| code1 | Poisson banded response: #337/#351 both-with-kernel historical parity cannot establish removal parity; historical pinned replay and current-binary input compatibility require **separate** approval |
| code2 | Joule `-E·Gamma_e` and normalized energy scaling, no approved replacement; `PhysicsElectronFluxModel` shared helper retained |
| code3 | Signed Source `FVCoupledForce` only conditional option: `number_source→v`, `coef=1` physical or `1/n_ref` normalized after verified mapping; EI18/EI19 zero-source assertions and single signed progress owner |
| code4 | Electrostatic Drift carrier/state and signed normal/upwind parity; FE/FV potential gradients, wall BC and `PhysicsFVHeavyMassElectromigrationCorrection` coupled owner |
| code5 | Four **independent** Factory owners in `PhysicsFVLogMolarElectronTransport.C`; a 3-of-4 migration remains HOLD for the whole shared C/H; historical Issue3 D6 and New-only S6 are separate gates |
| code6 | `rho * dw/dt` versus `d(rho*w)/dt` are not equivalent for variable rho; integrator, state, residual/AD and mass-inventory discriminators required |
| code7 | Thermal Flux ON/OFF and nonzero gradient/coeff, face/boundary, AD, `NVTransportMaterial` D_T producer retained for independent consumers |

## Command and phases

The upstream reports must exist even when Structural is incomplete (its scanner may write JSON and exit 2). With the **same clean Git checkout and HEAD**, run:

```sh
HEAD_SHA="$(git rev-parse HEAD)"
python3 ci/guards/fdeg_structural.py --target PhysicsFVMassFractionTimeDerivative \
  --expected-head "$HEAD_SHA" --output /tmp/fdeg-struct.json
# If exit=2: inspect partial JSON; it remains incomplete but can be assembled in HOLD.
python3 ci/guards/fdeg_functional.py --target PhysicsFVMassFractionTimeDerivative \
  --structural /tmp/fdeg-struct.json --expected-head "$HEAD_SHA" \
  --output /tmp/fdeg-func.json
python3 ci/guards/fdeg_transition.py --target PhysicsFVMassFractionTimeDerivative \
  --structural /tmp/fdeg-struct.json --functional /tmp/fdeg-func.json \
  --expected-head "$HEAD_SHA" --output /tmp/fdeg-transition.json
python3 -m unittest discover -s tests -p test_fdeg_transition.py -v
```

The Transition module performs P0 verification/assembly only. `FDEG_TRANSITION_P0=PASS` means *the plan evidence and conservative labels were constructed and verified*, **not** physics PASS. `FDEG_TRANSITION_PLAN=CONDITIONAL`, `FDEG_RETIREMENT=HOLD` are mandatory.

## Why we do not auto-infer the exact change

A current `.i` declaration or Python template may not correspond to an observed effective runtime object. A reviewer must decide `REWIRE`, `RETAIN`, `PRESERVE_HISTORICAL` or `HOLD` from additional evidence/approval; Transition only exposes options, obligations and ordering. In particular, declaring a candidate does not authorize changing a parameter, and the source file may have other owners or external consumers.

**Next:** perform the independent [Graph-only acceptance](fdeg_graph_only_acceptance_v0_1.md) before considering Coverage v0.1, then require fresh exact-HEAD Runtime/Coverage/owner approvals for any isolated deletion candidate.