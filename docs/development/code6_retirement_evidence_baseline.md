# code6 retirement — PR A exact-HEAD evidence baseline

**Tracking:** #704; FDEG Structural #696 / Functional #697 / Transition #701. **Target:** `physics_app/src/fvkernels/PhysicsFVMassFractionTimeDerivative.C/.h`.

## Purpose and boundary

Record *source-declared* affected consumers and the verified Structural v0.3, Functional v0.2 and Transition v0.1 evidence graphs at the same immutable repository checkout. This is a **retirement preparation** artifact, **not a Physics replacement, Native acceptance, caller-zero certification or deletion approval**.

The reviewed manifest `ci/baselines/code6_retirement_consumers.json` contains **10 Python CI scripts and 15 declared mass-fraction time Kernel instances**. All currently declare `rho = rho_const`; the reviewed source templates declare an `ADGenericFunctorMaterial` numerical value, but the *effective* Functor at Native runtime has **not** been observed. The manifest is deliberately a **bounded census**, not a complete statement about generated, historical, dynamic or external inputs.

## Reproduce

```bash
set -euo pipefail
head="$(git rev-parse HEAD)"
python3 ci/guards/code6_retirement_baseline.py --self-test
python3 ci/guards/code6_retirement_baseline.py \
  --expected-head "$head" --output-dir /tmp/code6-evidence
```

Four JSON files are written: `code6-structural.json`, `code6-functional.json`, `code6-transition.json`, `code6-baseline-receipt.json`. The receipt pins source HEAD, manifest blob SHA, each source file blob SHA and instance declaration line, all three graph IDs, target-scoped unresolved paths, every Transition blocker and `safe_delete=HOLD`. The repository CI `validate` job runs this command from the **exact PR HEAD** and uploads all four JSONs as a retained workflow artifact. A missing/changed declared consumer fails closed. Any unknown/dynamic consumer stays unresolved instead of being silently removed.

The built-in P0 self-test checks canonical and compact `type=` syntax, lexical-only false positives and missing-`rho` negative controls. The CI step also executes a real read-only three-graph source join, not just unit fixtures.

## Already established source facts (reviewed; still require exact-run receipt)

- Incumbent: `R=rho * _u_dot` in an `FVTimeKernel`, not a generally conservative `d(rho*w)/dt`.
- The candidate `PhysicsFVConservativeMassFractionTimeDerivative` explicitly computes `(rho_now*w_now-rho_old*w_old)/dt`. Under an **independently established common Backward Euler time scheme**, candidate minus incumbent is `(rho_now-rho_old)*w_old/dt`: a variable-density counterexample.
- Current ten-script manifest contains 15 declared instances including H05 (2), S5D (4), EDetach (1), EI18 (1), EI20 (1), E8 EI10 (1), E8 EI16 (1), Standard Energy (2), R2 (1), R3 (1). These are embedded `.i` templates, **not evidence of Native execution**.

## Gated plan

| Gate | Required work | Disposition |
| --- | --- | --- |
| **A / P0** | Produce/inspect three source-bound graphs + independent 10/15 census and full blockers | This PR; no physics edits |
| **B / P1** | Pin real FVTimeKernel `_u_dot`/Executioner scheme, generated final inputs, effective `rho_const`, state/AD coupling | Incomplete → HOLD |
| **B / P2–P3** | Small nonzero transient `w_k` A/B + H05 two-term pilot. Compare residual, AD Jacobian and mass inventory with approved oracle/tolerance; variable-density negative control must reject unconditional substitution | No parity result yet |
| **C** | Groupwise rewire EDetach/EI18/EI20, E8/R2/R3/standard; S5D four-species reaction mass balance last. Preserve test assertions and historical inputs | Only after pilot gate |
| **D** | Prove relevant dynamic/external/legacy scope, no old consumer references; clean build/P2/P3/CI before and after C/H Factory removal, rollback exact SHA | Separate explicit approval; HOLD |

## P0 acceptance criteria

1. Exact source HEAD, `graph_id`, `edge_id`, source blob and 10/15 consumer census match; no unreviewed drift.
2. Three graphs can be regenerated read-only and receipt is uploaded in exact-HEAD CI.
3. Current observed runtime status remains `NOT_OBSERVED`, parity `NOT_PROVEN`, and deletion `HOLD`; no promotion from template mention/CI P0.
4. Blocking obligations are recorded verbatim rather than manually waived. A green P0 cannot authorize kernel rewiring or removal.

**Changes in PR A:** only evidence collector, curated inventory, documentation, and CI validation/artifact upload. No `physics_app/src/fvkernels/*.C` or `*.h` mutation; no Native physics run.