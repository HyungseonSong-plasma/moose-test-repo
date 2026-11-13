# Issue #402 — FEM electron sheath BC class cutover and historical retirement

**Status:** Draft, source refactor only. P0 static/source contracts required; pinned native P1/P2 and P3 science parity not yet accepted. **SCIENCE_HOLD**.

## Active canonical C++ owners

- `FEMElectronSheathBC` — particle flux; source `physics_app/src/bcs/FEMElectronSheathBC.C`.
- `FEMElectronEnergySheathBC` — energy flux; source `physics_app/src/bcs/FEMElectronEnergySheathBC.C`.
- Both are registered under their exact C++ class names. No registration aliases or retained old filename.
- C++ equations are a source-preserving rename/split of the prior FieldLimitedFlux BCs, retaining plasma-side `FaceArg`, `wall_number_flux`, `N_A`, `mean_energy`, and `(5/2)T_e` energy factor; no wall model or science result is thereby accepted.

## Fully retired GroundedSheath owners

- `PhysicsFEMLogMolarElectronGroundedSheathBC` — **RETIRED / UNREGISTERED / SOURCE DELETED**.
- `PhysicsFEMLogMolarElectronGroundedSheathEnergyBC` — **RETIRED / UNREGISTERED / SOURCE DELETED**.
- Both were historically implemented in `PhysicsFEMPlasmaWallBCs.h/.C`; that pair now contains only `PhysicsFEMLogMolarIonWallBC`.
- Active `experiments/fem_fvm_plasma_discriminator/prepare_cases.py::fem()` and `prepare_full_fem_contour_mesh.py::build_case()` explicitly raise `RETIRED_GROUNDED_SHEATH_BCS`. Their old scientific configuration is not silently mapped to the adjacent-field sheath law.
- Historical archived inputs, one-shot workflow records, and provenance documents are immutable **historical evidence**, not live supported runtime classes. Do not amend frozen SHA-bound past Actions or run inputs to masquerade as the original evidence.

## Dielectric energy BC classification

`PhysicsFEMLogMolarElectronEnergyDielectricBC` is **not retired globally**. Its direct uses in Issue #3 cover/wafer/focus-ring dielectric pilots remain. Latest S6 uses the canonical `FEMElectronEnergySheathBC` instead; the Issue #395 scratch preparer replaces its old dielectric energy BC only in those S6 wall inputs. Source and registrations for independent Issue #3 are preserved.

## Validation and migration limits

- P0: assert exactly one registration for each canonical class and no GroundedSheath source registration; assert equations and the plasma-side Functor evaluation are source-preserving; assert retired FEM generators fail closed; assert explicit S6 generated input class names; keep dielectric energy implementation.
- P1: compile pinned native PhysicsApp with both split source files.
- P2: `physics-opt --check-input` for actual staged 417/941 S6 and representative independent dielectric case; prior historical frozen input is not a valid new-source P2 claim.
- P3: no re-execution or scientific acceptance under this naming-only change. Existing published S6/Issue #3 evidence retains its exact original source/runtime identity.

**Parent:** Draft PR #528 (Issue #402); no merge into parent or main until matching source-bound checks and review.
