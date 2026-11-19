# FDEG Functional Contract Graph v0.1

**Owner:** Issue #693. **Dependency:** Structural Evidence v0.2 (#691 / Draft PR #692). P0 static evidence only.

## Input / contract

The Functional assembler consumes:

1. A Structural `fdeg.structural.v0.2` JSON report created from the **same exact Git HEAD**, with valid `graph_id`, `edge_id`, `instance_id`, `source path/line/blob` and declared `.i` bindings.
2. A reviewed source-pinned contract registry at `ci/baselines/fdeg_functional_contracts.json`. Every source-supported claim is bound to its owning C++ source blob (or an explicitly linked helper source blob) plus one or more exact textual anchors. A changed file blob invalidates the profile; a missing witness anchor fails P0.
3. The source checkout at the report's `repository_head`, with a clean tracked worktree. If evidence references do not match local bytes or source paths, Functional fails closed.

## One-command pipeline

```bash
head="$(git rev-parse HEAD)"
python3 ci/guards/fdeg_structural.py \
  --target PhysicsFVElectronReactionSource --expected-head "$head" \
  --output /tmp/fdeg-structural.json

python3 ci/guards/fdeg_functional.py \
  --target PhysicsFVElectronReactionSource \
  --structural /tmp/fdeg-structural.json \
  --expected-head "$head" \
  --output /tmp/fdeg-functional.json

python3 -m unittest discover -s tests -p test_fdeg_functional.py -v
```

A Structural scan with unrelated unresolved dynamic/generated calls can return exit code 2 and still write a partial JSON report. This is **not a caller-zero proof**. The Functional assembler may source-verify the target in this case but preserves `STRUCTURAL_SCAN_INCOMPLETE`, and **retirement remains HOLD**.

## Output

`fdeg.functional.v0.1` is a typed source-bound Functional Contract Graph:

- `source_identity`: exact head, Structural schema/graph ID, registry schema and rehashed source blobs.
- `edges[]`: `IMPLEMENTS`, `CONTRIBUTES_TO`, `REQUIRES`, `EVALUATES`, `APPLIES_WHEN`, `COUPLED_WITH`, `SATISFIES`, and `ALTERNATIVE_CANDIDATE`. Source-backed claims include `claim_id`, stable `edge_id`, condition, mode, unit, expression, counterexamples, and path/line/blob witnesses.
- `consumer_contracts`: Structural edges joined to declared input instance bindings, without promoting `MENTIONS_SYMBOL`, `ACTION_CREATES`, static Python/JSON declarations or input syntax matching into observed runtime use.
- `required_discriminators`, `historical_guards`, `unresolved_obligations`: independent oracles, historical parity constraints and conditions that must remain unproven until separately evidenced.
- `runtime_observation=NOT_OBSERVED`, `equivalence_verdict=NOT_PROVEN`, `safety=NO_CALLER_ZERO_TRANSITION_OR_RETIREMENT_AUTHORIZATION`: invariant P0 boundaries.

`SOURCE_SUPPORTED` means the **recorded source has the claimed textual implementation under its pinned blob and reviewed interpretation**, not that a numeric observer/physical acceptance has run. `CANDIDATE_UNVERIFIED` never becomes `REPLACED_BY` or a retirement pass. Exact source line references are generated at collection time; no hardcoded stale line indices.

## Initial source-pinned target catalog

- code1: `FVElectronResponseBandedCorrection`, 1D banded Poisson response, row-map assumptions, **historical parity != removal parity**
- code2: `PhysicsFVElectronEnergyJouleHeating`, electric-work sign, two representation modes, **shared helper preservation**
- code3: `PhysicsFVElectronReactionSource`, signed source, normalized `n_ref`, source ownership and AD discriminator, **FVCoupledForce as unverified candidate**
- code4: `PhysicsFVElectrostaticDrift`, normal drift, previous-state limiter, upwind, **heavy mass correction coupling**
- code6: `PhysicsFVMassFractionTimeDerivative`, density-weighted `_u_dot`, time-integration uncertainty, **non-conservative/conservative only conditionally comparable**
- code7: `PhysicsFVThermalDiffusion`, face flux and flag, zero controls, internal/boundary distinction, **unobserved Native contribution**

code5 Functional review was not present on #691 when the scope was fixed. Add that profile after its unique physical/representation contract is reviewed; do not silently infer the four multi-class log-molar operators from one filename.

## P0 acceptance / limits

P0 positive and negative checks cover stable JSON IDs, same-SHA Structural joins, source blob mutation, missing anchors, corrupted Structural graph/edge identities, changing declared inputs after evidence generation, unverified alternatives and unknown consumer scope. The registry is reviewed semantic data, not a general-purpose physics theorem prover. This implementation does **not** run Native P1/P2/P3, resolve external consumers, prove conservation or AD Jacobian parity, prescribe rewire/deletion sequence, authorize GitHub mutation, or accept historical replay.
