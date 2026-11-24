# Graph-only FDEG Migration Planning Acceptance v0.1

> **Historical design record (#881).** The standalone subsystem is being retired. Commands and contracts below describe the original implementation at [pre-retirement revision 7a119106](https://github.com/HyungseonSong-plasma/moose-test-repo/tree/7a119106a22f2de2ca5c761a4119f00509e0efdd); they are not current CI instructions. See [historical provenance](archive/issue881_fdeg/README.md) and [Harness Code](../../physics_harness/code/README.md).

**Issue:** #701. **Design objective:** independent GPT/human planner can propose a *conditional* migration plan for code1–7 using **only the serialized, identity-verified** Structural v0.3, Functional v0.2 and Transition v0.1 JSON reports, with no new source browsing.

## Evaluation separation

- **P0 contract fixtures (automatable):** `tests/test_fdeg_transition.py` verifies hash/target joins, disposition safety, owner group, registered claims, semantic HOLD, dependency DAG, expected unobserved edge removal and rollback exact HEAD. These are unit/contract tests, **not** a blind independent GPT acceptance.
- **Independent graph-only planner evaluation (not automatically executed):** a separate evaluator must give the planner only the three JSONs, not C++ source or the reviewed answer key, and compare its plan to the rubric below. It must record model/tool access, inputs' `graph_id`, output, reviewer decision and false-PASS count. Until executed and reviewed, `GRAPH_ONLY_ACCEPTANCE=NOT_EVALUATED`.
- **Actual scientific retirement:** requires Coverage and executed Native independent oracle; neither test category authorizes `SAFE_DELETE`.

## Graph-only input fixtures

For each target below, generate Structural+Functional+Transition **at a single fresh exact HEAD** and store the three complete JSONs. The evaluator receives only these files (no repository browser, no `git grep`, no direct C++ inspection).

| Case | Expected preservation / blocker | Required negative control |
| --- | --- | --- |
| code1 `FVElectronResponseBandedCorrection` | Poisson banded residual, ghosting, AD, historical pinned replay vs current binary input compatibility, unresolved generated `poisson_sub.i` | Gen34 historical parity with kernel present on both sides does **not** authorize removal |
| code2 `PhysicsFVElectronEnergyJouleHeating` | Electric-work signed residual, normalized/physical_eV and shared `PhysicsElectronFluxModel`; no approved replacement | A lexical/helper reference is not an active consumer; helper must not be cascaded into deletion |
| code3 `PhysicsFVElectronReactionSource` | Signed number source, `n_ref`, `FVCoupledForce` conditional parameter mapping, EI18/EI19 negatives | A candidate/coef mapping is not residual/Jacobian parity; no duplicate Source |
| code4 `PhysicsFVElectrostaticDrift` | face `z μ E·n`, upwind/limiter, BC, FE/FV mode, HeavyMassCorrection cancellation | zero-electric-field smoke cannot prove nonzero charged drift parity |
| code5 four `PhysicsFVLogMolarElectron*` classes | all four owner statuses, Time/Diffusion/Drift/Reaction invariants, independent candidate oracles | 3/4 migrated does **not** permit removal of common `.C/.h`; D6 historical ≠ New-only S6 |
| code6 `PhysicsFVMassFractionTimeDerivative` | `rho*dw/dt`, variable `rho`, time scheme and mass conservation; documented conservative candidate | `d(rho*w)/dt` differs for variable density; source similarity or BE assumption not parity |
| code7 `PhysicsFVThermalDiffusion` | `-D_T/T grad(T)·n`, ON/OFF, internal/boundary, independent `NVTransportMaterial D_T` producer | OFF or zero-gradient Native scope cannot certify global dead code or Material retirement |

## Planner prompt (for independent evaluation)

> You have only these Structural, Functional and Transition JSONs. Do not access C++ sources or repository metadata. Produce for each identified consumer: source and instance/edge IDs; observed vs unobserved activation; disposition option and reason; exact source-attested candidate mapping only if present; preserved equation terms, protected independent owners, required scientific discriminators, unresolved evidence, ordered change DAG and rollback target. Distinguish pinned historical replay from current binary compatibility and note dynamic/untracked paths. No PASS for unexecuted or unverified steps. State explicitly that SAFE_DELETE is HOLD. Return `blocking_obligation` objects for any essential unknown. Do not invent input names, parameter mappings, changed files, tolerances or Native artifacts.

## Evaluation scorecard

1. **Identity:** every referenced `edge_id`, `claim_id`, `instance_id`, `graph_id`, `repository_head` matches supplied JSON. Invented identifiers = failure.
2. **Consumer coverage within known graph:** every declared input/Action/generator candidate included with correct evidence strength; lexical/historical references **not** promoted to runtime.
3. **Preservation:** all explicitly recorded Functional `claim_ids` and independent protected owners are retained/conditioned; missing physical term, duplicated Source or shared-helper deletion = failure.
4. **Candidate semantics:** candidate/source presence never implies parity; ten Functional diff dimensions and discriminators remain unresolved until independent approved proof. A missing candidate implies RETAIN/HOLD.
5. **DAG & rollback:** change sites and step preconditions derived from Transition JSON, correct order and no invented paths; rollback exact baseline SHA and required revalidation included.
6. **Scope & missing evidence:** dynamic/generated output, effective Functor, observed activation, Native residual/AD, independent tolerance, old binary compatibility and Coverage/caller-zero uncertainties explicitly blocked.
7. **Safety invariants:** **zero** false `SAFE_DELETE`, `PARITY_PASS`, `CALLER_ZERO`, `APPLIED`, `NUMERICALLY_VERIFIED`, `NATIVE_PASS` promotions. Any one is failure.

Pass requires 7/7 target-case assessments and 0 false promotions, with independent reviewer recording bounded omissions as explicit blockers. Passing this evaluation means **a conditional plan is representable using the graph**, not that code retirement is executable. An independent evaluator must explicitly attest that no source files were opened.

## Required evaluation record (not yet populated)

```json
{
  "schema": "fdeg.graph_only_acceptance.v0.1",
  "status": "NOT_EVALUATED",
  "repository_head": null,
  "input_graph_ids": [],
  "cases_evaluated": 0,
  "false_pass_promotions": null,
  "reviewer": null,
  "source_access": "UNVERIFIED",
  "decision": "PENDING_INDEPENDENT_EVALUATION"
}
```

This is a **template**, not an evidence result. Do not mark acceptance complete on the basis of P0 fixtures alone.