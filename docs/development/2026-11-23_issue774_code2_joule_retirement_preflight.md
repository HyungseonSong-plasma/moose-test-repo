# #774 code2 — FV Electron Joule source retirement preflight (New-only)

**STATE:** `WORK_AUTHORIZED / G0_SOURCE_IDENTIFIED / OM02_CONSUMERS_OPEN / OM04_TARGET_NOT_PROVEN / SAFE_DELETE=HOLD / MAIN_MERGE=DEFERRED`.

**Owner:** #774. Related historical evidence: #736 (closed diagnostic, not deletion), #714 (closed T2 evidence, not compatibility acceptance). This is a **branch-only, pre-removal decision record**; it does not change Physics code, delete a Factory, accept science, or authorize main merge.

## Exact identity

- Intended New-only integration base: clean Thermal production Draft #807, commit `51475b5eeb2e40c9f71bac30012daa7954e3b3b7`.
- Source: `physics_app/src/fvkernels/PhysicsFVElectronEnergyJouleHeating.C`, Git blob `07ecd234871c659b04389c87bff6f52fae7f800e`.
- Header: `physics_app/include/fvkernels/PhysicsFVElectronEnergyJouleHeating.h`, Git blob `1d2afa9ba448041c664fdc1822ede5472b93551e`.
- One `registerMooseObject("PhysicsApp", PhysicsFVElectronEnergyJouleHeating)` in this translation unit.
- Current #807 D9 New-only expectation: 12 FVKernel C files / 17 registered Factory types. **Only after verified standalone code2 cut:** expect 11 / 16. Do not reuse that expectation blindly when combining code1 #809 and heavy-mass #811, whose independent candidates also each expect 11 / 16 from different ancestry. Reconcile the combined exact tree and tests, not per-branch constants.

## Source contract and non-equivalence

The FV source computes `electric_field = -gradient(potential)`, obtains electron density and its gradient plus mobility/diffusion, computes `PhysicsElectronFluxModel::electronElectricWork(...)`, optionally divides by `energy_reference_eV` in normalized mode, and contributes `-source` to the residual. Its `state_form` enum accepts `normalized` and `physical_eV`, **not** `molar_eV`.

The current New-only `DDEnergyEq.C` selects `FEMLogMolarElectronJouleHeating` and explicitly states the FEM log-molar eV·mol/(m³·s) convention. This demonstrates an alternate New-only owner **but does not by itself demonstrate equivalence** to FV physical/normalized energy, off-diagonal AD response, different residual assembly, or every historical consumer.

No general FV-to-FEM Joule parity claim is accepted here.

## Known consumer/reference disposition matrix (source-reviewed at #807)

| Reference | Observed evidence | Proposed disposition | Current gate |
| --- | --- | --- | --- |
| `physics_app/ci/electron_energy_joule_smoke.i` | Three active `[FVKernels]` instances `energy_drift_joule`, `energy_plus_joule`, `energy_minus_joule`, all `state_form=physical_eV`. Source blob `6c4901f843a98b74b450cc3a1fab09e8e1873b2c`. | KEEP_ACTIVE until a genuine same-observable replacement test is adopted, or explicitly retire the smoke contract with an approved test-coverage disposition. | BLOCKED_CONSUMER |
| `experiments/fem_fvm_plasma_discriminator/prepare_cases.py` | Emits old FV Factory with `state_form=molar_eV`. Source blob `69ec14c58b502a953c9024c46d332494cad61e6c`. Existing C++ enum cannot parse this option. | Classify the experiment as historical/erroring vs still-supported; never silently change enum/units. Preserve source/run provenance. | BLOCKED_COMPATIBILITY |
| `experiments/Issue351_frozen_heavy_driver_parity/control.py` | Asserts old type is generated and launches the **current branch's** `physics_app/physics-opt`. Source blob `6d7efcb4ea94b2011782aba2c9cab40238756312`. | Decide whether current-binary replay is still supported; if not, freeze historical source/ELF/input/result identities and remove live dispatch from supported CI. Merely retaining file bytes does not make replay supported. | BLOCKED_DECISION |
| `tests/test_issue402_material_class_names.py` | Textual reference to `electron_energy_joule_smoke.i` in repository code search. | Verify the test's live assertion and preserve an equivalent supported check or explicitly amend the retired smoke contract. | AUDIT_PENDING |
| historical FDEG code2, #736/#714 | Prior target-scoped source/transition/compatibility evidence is recorded, but not current global caller-zero. | PRESERVE_HISTORICAL by immutable SHA; never import obsolete code7 CI/FDEG into the New-only production integration. | EVIDENCE_ONLY |
| external callers, generated runtime objects, Workflow and indirect tests | No same-head complete consumer proof. | UNKNOWN until an attributable exact-head scan and active route analysis. | BLOCKED_CENSUS |

## Ordered closure gates

1. **G0 — Exact source and scope:** record current #807 parent and C/H blob identity, active New-only 417/941 W1/P05 identities, full tracked reference classes, dynamic generator uncertainty and external uninspected surfaces. A lexical search is not caller-zero.
2. **G1 — Consumer disposition:** decide supported `electron_energy_joule_smoke.i` coverage, `prepare_cases.py` broken `molar_eV` generated input, and Issue351 current-binary replay. Explicitly separate `KEEP_ACTIVE`, `REWIRE_VERIFIED`, `ARCHIVE_HISTORICAL`, `REMOVE_OBSOLETE`, `UNKNOWN`.
3. **G2 — Characterization/target readiness:** if semantics migrate, characterize FV Joule sign, units, density-gradient term, `E=-grad(phi)`, normalization, boundary/field signs and AD derivatives. Prove the actual accepted target contract in the affected regime; a FEM owner declaration alone is insufficient. If no current FV capability is supported, document the explicit scope-retirement decision and preserved historical evidence instead of inventing parity.
4. **G3 — Bounded source cut:** only after G1/G2 acceptance, delete exactly the C/H pair on an isolated descendant; update existing D9 source guard/usage census, source-anchored tests and allowed historical reference classification. No new broad CI, no blind string replacement, no change to `PhysicsElectronFluxModel`, `DDEnergyEq`, Poisson #652 or protected EI sources.
5. **G4 — Exact-head executable validation:** P0 source/Factory absence and negative reintroduction controls; `.github/workflows/ci.yml` == `ci/workflow_templates/general-ci.yml`; P1 clean PhysicsApp build; S6-417 and S6-941 real Native P2/P05 with exact source/ELF/input SHA and sanitized receipts; independent Joule residual/AD/P3 comparison when the retained behavior requires it. Syntax or CI PASS alone is not science parity.
6. **G5 — Integration / hygiene:** reconcile competing code1 #809, code8 #811 and Thermal #807 guard counts on **one final exact candidate head**; remove branch-only one-shot workflow definitions after verification, preserve historical Actions runs/artifacts, review exact-head CI/review/rollback, defer `main` until Poisson #652 isolation and separate merge authorization, then reconcile PRs/issues and exact-SHA unused branches.

## First real gate

`G1_CONSUMER_AND_LEGACY_REPLAY_DISPOSITION=HOLD`.

No C/H deletion, CI removal, experimental input conversion, or replacement-parity claim should be made on this preflight branch. The current reproducible old typed inputs and the current-binary Issue351 replay must either be validly migrated or explicitly declared unsupported for the accepted New-only scope. Any statement of universal external caller-zero is unsupported.

**Required next action:** classify and disposition the four identified tracked consumer surfaces and inspect indirect runtime/test/Workflow routes at the exact selected candidate SHA before proposing a source-cut PR.
