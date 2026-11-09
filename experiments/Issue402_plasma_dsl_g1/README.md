# Issue #402 / G1: Native FEM/FV species-binding pilot

**Status: implementation candidate, NOT yet Native validated.**
G0 design is approved. This first G1 slice is **read-only / external
binding only**; it does **not** implement a new full automatic
plasma-equation builder, change existing S5/S6 runs, or establish
science acceptance. SCIENCE_HOLD remains.

## Implementation authority and limits

- Based on the approved user design with no input \`schema_version\`,
  \`fem_species\` / \`fvm_species\` on species-bearing equation leaves,
  and no global \`Transport/discretization\`.
- Registers one fixed path
  \`Physics/Plasmas/Transport/DriftDiffusion/Continuity\`
  to \`PlasmaSpeciesContinuityPhysics : PhysicsBase\`.
- Accepts ordered \`fem_species\`, \`fvm_species\`, \`variables\` and
  \`owner_mode=external\` only.
- Rejects duplicate/overlap, missing solver variables, wrong FV/FEM
  types, invalid lengths and \`owner_mode=generate\`. It **creates
  zero** kernels, sources, BCs, variables or transfers.
- This is a preparatory action for testing syntax and variable binding
  against pinned native MOOSE, not a claim that new DSL owns electron
  kinetics, Navier–Stokes, Poisson or Maxwell yet.

## Pin / reproduce

Native build image:
\`ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008\`

Pinned MOOSE:
\`9f388366ccf38b9c34542ec5561198249fde0ac9\`.

To run native checks on a machine or runner with Docker and access
to the published OCI build image:

\`\`\`bash
git checkout <exact-PR-head>
bash experiments/Issue402_plasma_dsl_g1/run_native_binding_smoke.sh
\`\`\`

The runner tests:
1. exact pinned-container native C++ build;
2. original minimal FEM+FV diffusion fixture \`--check-input\`;
3. same fixture plus new \`[Physics]/[Plasmas]\` input \`--check-input\`;
4. **four negative checks** for duplicate/overlapping species,
   wrong discretization family, unsupported generation and missing
   solver variable;
5. original vs additive binding-only native diffusion solve;
6. Exodus nodal/element/time results, fail-closed numerical parity
   via \`compare_native_outputs.py\`.

The tests are only marked **PASS** if the native runner actually
produces \`evidence/numerical_parity.json\` with
\`TINY_DIFFUSION_NATIVE_NUMERICAL_PARITY_PASS\`.

## Latest completed S6 input evidence

Complete source artefacts from S6-417 and S6-941 each have 10 input
layers and eight chemistry channels. Local manifest/provenance and
FEM/FV variable families can be checked *offline*:

\`\`\`bash
python experiments/Issue402_plasma_dsl_g1/audit_archived_s6.py \
  --archive /path/to/S6-417-combined_native.zip \
  --archive /path/to/S6-941-combined_native.zip \
  --output /tmp/issue402-s6-input-audit.json
\`\`\`

\`s6_external_bindings.i\` is an **additive, validation-only**
eleventh overlay for both S6 variants. Do not replace or mutate any
original 10-layer input. Reconstruct private rates from the governed
secrets/replay pipeline; never publish private table bytes. A further
Native check-input and 400 W/100 us solve must be run on the actual
pinned S6 replay before **full-run parity** can be assessed.

### Not done by this G1 pilot

- No registered coefficient/Chemistry/energy/NavierStokes/Poisson/Maxwell
  equation-building DSL.
- No automatic old-to-new effective-option mapping or generated-object graph.
- No real-time or cached native build evidence solely from static pytest.
- No 400 W full plasma replay with new C++ plugin/overlay.
- No Jacobian, charge/RF, convergence or scientific equivalence claim.
- No default input cutover or merge without separate acceptance.

## Future implementation gates

1. Native **build and parse** this external-only registration; if
   exact fixed syntax fails, correct it before any DSL expansion.
2. Native **minimal solve** original vs binding-only; require identical
   physical fields and convergence.
3. Add **per-equation owner generation** with explicit FV/FEM kernel,
   state, BC and source mapping. Reject duplicate owners.
4. Fully reconcile S5/S6 effective option layers, then native
   run both S6-417 and S6-941 at the same 400 W and full 100 us.
5. Only after numerical/object/physical parity, propose per-consumer
   opt-in cutover. Keep SCIENCE_HOLD until science gate.
