# FVKernel source retirement — New-only S6-417/941 baseline v0.1

> **EVIDENCE ONLY / PROVISIONAL** — no source or test deletion authorized.

Workboard: https://github.com/HyungseonSong-plasma/moose-test-repo/issues/774

## Verified reference identities
- Production-inventory baseline: main @ \`156a5117ebe6816e67b352a9470572c2e74da367\`, 12 source \`.C\` / 15 factory types.
- New-only 417/941 exact source: Draft, unmerged PR #665 @ \`9457191f4c0693ae886586edd961965867ccd5c0\`.
- Native P2: run https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757 / artifact \`14458752206\` — both cases passed limited P2 checks.
- D8 bounded RF 3 ns: https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44409942970 / artifact \`14475669657\` — reused exact W1 binary.
- Original pinned 11-layer input artifact: \`14372278070\`.
- P05 receipt's \`observed_FVKernel\` list is **only O2p/Om/Op**, 12 per variant, not the entire FVKernel registry. The unfiltered trace contains 77 events per variant but is **not distributed** in the receipt ZIP. Final poststage full rendered \`.i\` bytes are also not attached.
- P3/P4 100 microseconds and general science parity are **NOT accepted**.

## Source-level inventory (not Factory-class status)

| Source (.C) | New-only screening | Concrete other consumers / impact |
|---|---|---|
| PhysicsFVConservativeMassFractionTimeDerivative.C | USED | O2s/O/Os conservative heavy-species accumulation; preserve |
| PhysicsFVMassFractionAdvection.C | USED | O2s/O/Os transport; preserve |
| PhysicsFVMixtureAveragedDiffusion.C | USED | O2s/O/Os diffusion; preserve |
| PhysicsFVSpeciesReactionSource.C | USED | neutral/heavy source; preserve |
| FVElectronResponseBandedCorrection.C | **PROVISIONAL CANDIDATE** | Issue351 \`control.py\` generated historical correction assertion; FDEG code1. Archive historical byte/physics references; decide whether qualified old input remains supported |
| PhysicsFVElectronEnergyJouleHeating.C | **PROVISIONAL CANDIDATE** | \`physics_app/ci/electron_energy_joule_smoke.i\`, \`experiments/fem_fvm_plasma_discriminator/prepare_cases.py\`, Issue351; never assume replacement by \`DDEnergyEq\` is equivalent without signed residual and units checks |
| PhysicsFVElectronReactionSource.C | **PROVISIONAL CANDIDATE** | \`physics_app/ci/check_stage5_*.py\` generators, \`issue192_s5r.py\`, \`ei01_attachment_runtime_smoke.i\`; separate required runtime checkers from historical-only tests and preserve source sign/scaling |
| PhysicsFVElectrostaticDrift.C | **PROVISIONAL CANDIDATE** | \`electron_energy_transport_smoke.i\`, \`electron_energy_lookup_response_smoke.i\`, Issue192/Issue282; verify charge/mobility/upwind semantics when migrating supported callers |
| PhysicsFVHeavyMassElectromigrationCorrection.C | **PROVISIONAL CANDIDATE** | \`experiments/historical_recipe_support/issue192_s5r.py\` Type mapping and \`tests/test_issue402_species_transport_rule.py\`; common mass-flux correction is not equivalent to direct drift |
| PhysicsFVLogMolarElectronTransport.C | **PROVISIONAL CANDIDATE** | Four Factory classes in one source/header; Issue3, historical Issue402, \`check_electron_molar_representation_contract.py\`; New-only FVLogMolar time/diffusion/drift replacement covers three roles, **not automatically the fourth reaction-source role** |
| PhysicsFVMassFractionTimeDerivative.C | **PROVISIONAL CANDIDATE** | \`check_stage5_*.py\` generated test inputs. \`rho dw/dt\` differs from \`d(rho w)/dt\` when density varies; conservative replacement is not automatic |
| PhysicsFVThermalDiffusion.C | **PROVISIONAL CANDIDATE** | \`physics-code-ci.yml\` live code7 FDEG source capture, \`test_fdeg_harness_abcd.py\`, curated contracts; migrate historical exact-SHA FDEG receipt before code/header deletion |

All eight are **run-scoped provisional deletion candidates**, NOT verified global unused files. On the current \`main\`, other consumers, FDEG and historical runs remain significant and **no file deletion is approved**.

## Required impact disposition for each candidate
Assign every observed consumer one of \`KEEP_ACTIVE\`, \`MIGRATE\`, \`ARCHIVE_HISTORICAL\`, \`REMOVE_OBSOLETE\`, \`UNKNOWN\`, with an exact path, reason and verification obligation. \`UNKNOWN\` means hold, never silent deletion. Historical inputs/artifacts are immutable and can remain readable without requiring live compilation if explicitly accepted.

## Ordered implementation
1. Obtain or regenerate an **unfiltered complete poststage source-type and Physics-generated Factory inventory** from New-only 417/941, linked to exact source and binary SHA. Until then, the candidate list is provisional.
2. Start with \`PhysicsFVThermalDiffusion.C\` as a **feasibility/impact-only package**: preserve code7 FDEG archive identity, rework the live CI capture obligation, and prove the old thermal flux has no supported current consumer. Do not delete before closure.
3. Tackle individual Factory-source classes in separate small change sets. For \`PhysicsFVLogMolarElectronTransport.C\`, resolve all **four** registered types before removing the shared source and header.
4. Perform retirement edits **after** PR #665 New-only integration is accepted into the base being tested; never drop old source while the new owner exists only on a draft branch and older native checks still require it.
5. At exact deletion PR head run affected Harness/Physics CI, C++ build, \`--check-input\`, Native New-only P2 and relevant negative controls, D8 3ns if affected; add scientific parity tests **only when a supported physical function is actually migrated**.

Deletion gate: \`safe_to_delete=false\`, \`global_consumer_closed=false\`, \`SCIENCE_HOLD\` unchanged.
