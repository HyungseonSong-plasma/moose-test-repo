# D1–D4: PhysicsFVThermalDiffusion source deletion rehearsal

> **SIMULATION ONLY — unapproved source removal. Do not merge into `main`.** Parent archive branch is PR #776. The current deletion is intentionally *not* a proof of safe retirement.

## D1 — Run-scoped usage evidence

| Evidence | Observation | Decision |
|---|---|---|
| New-only S6-417/941 native P2, [run #44366325757](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44366325757) | source `9457191f4c0693ae886586edd961965867ccd5c0`; success for defined P2 checks | Proven run, **not** complete source/Factory census |
| Native P2 artifact #14458752206 | `p05_negative_receipt.json` lists the 12 **O2p/Om/Op ion** FVKernel registrations per case; no unfiltered trace or entire poststage 11-layer input | Absence of Thermal in **ion-only list cannot prove whole-run absence** |
| D8 3ns artifact #14475669657, [run #44409942970](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44409942970) | Receipts for 417/941 and abbreviated logs, no complete final generated `.i` or all Factory events | Independent full-source usage closure still missing |
| Git-tracked direct `.i` declarations | No `type = PhysicsFVThermalDiffusion` found in earlier 153-file census | Supporting static **non-use candidate** evidence only |
| Historical Issue20 `thermal_gradient_activation/input.i` | Uses **`QPXFVThermalDiffusion`**, not PhysicsApp `PhysicsFVThermalDiffusion` | Different app/Factory; never treat as direct PhysicsApp consumption |

**New-only source verdict:** `PROVISIONAL_DELETE_CANDIDATE`, never `ABSENCE_PROVEN`. No Native deletion-before/after equivalence claim here.

## D2 — Exact source/consumer mutation map

| Path | Category | D4 action | Later required gate |
|---|---|---|---|
| `physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C` | Factory and residual implementation | **Delete in simulation branch only** | Native binary rebuild + factory ownership check |
| `physics_app/include/fvkernels/PhysicsFVThermalDiffusion.h` | Class declaration | **Delete in simulation branch only** | C++ include audit; no live references |
| `ci/baselines/fdeg_functional_contracts.json` | Active functional contract; includes source anchors | Preserve at first cut; migration/archiving required | Historical functional profile integrity and runtime compatibility |
| `ci/baselines/fdeg_transition_contracts.json` | Active retirement policy | Preserve at first cut; migration/archiving required | Owner authorization and separated historical policy |
| `tests/test_fdeg_functional.py` | Extracts live Thermal parameters; expects 10 active profiles | Preserve at first cut; expected failure until archive-aware migration | Negative tests and all surviving profiles remain checked |
| `tests/test_fdeg_transition.py` | 10 active profiles | Preserve at first cut; expected failure until profile migration | Full remaining set coverage |
| `tests/test_fdeg_harness_abcd.py` | Calls live code7 `capture` | Preserve at first cut; expected failure until archive-aware migration | Historical graph tampering detection maintained |
| `tests/test_fdeg_thermal_archive.py` | Validates current live .C/.h and historical ZIP | Preserve at first cut; expected failure until after-cut adaptation | Full preserved ZIP and graph joins independently verified |
| `.github/workflows/physics-code-ci.yml` | Live code7 capture and archive artifact upload | Preserve at first cut; expected failure until historical cutover | No silent CI step removal; keep workflow ownership contract |
| `ci/guards/fdeg_retirement_evidence.py` | Existing `verify_retired` fail-closed static guard | **Keep unchanged** | Independent Native/Coverage/owner receipts and historical-exemption policy |
| `reports/issue774/archive/*.zip` | Immutable pre-cut evidence | **Keep byte-for-byte** | SHA/manifest/3-Graph identity must pass |

## D3 — Explicit consumer disposition

- **C++ source and declaration:** `SIMULATE_REMOVE`, not approved.
- **Current New-only owner:** `NO_CONFIRMED_REFERENCE`, **coverage not closed**; reconfirm actual poststage complete input and generated Factory events.
- **FDEG live capture, test, active registries:** `MIGRATION_REQUIRED`; replacement is historical-archive verification, *not deletion of tests*, with preserved negative mutation checks.
- **Issue20 QPX implementation, transport Material `D_T` producer, and pre-existing historical experiments/documents:** `KEEP_UNCHANGED`; do not delete in the same package.
- **External/dynamic Python consumers and old-input support policy:** `UNKNOWN`; requires independent coverage and explicit owner disposition.

## D4 — Rehearsal and gates

First cut removes only the `.C` and `.h` and runs existing CI **without disguising expected failures**. CI errors will identify concrete migration locations. The corrective simulation cut may then migrate only historical evidence checks, while keeping `safe_delete=false`.

**This branch must remain Draft/unmerged** until unrelated approval conditions are satisfied: New-only PR #665 integration strategy, independent full generated-consumer scope, current binary compatibility decision, independent Native before/after comparison and explicit owner review.

## Temporary CI targeting

Repository CI and Physics Code CI trigger only for pull requests targeting `main`. This Draft source-deletion rehearsal is temporarily retargeted to `main` **to expose the original failures**. It must be retargeted back to archive PR #776's branch before review, and cannot be merged under either base. Until the FDEG evidence migration cut, red CI is expected.

## D4 follow-up simulation (pre-approval only)

Prepared a separated technical *archive-aware* version of this rehearsal: remove the now-unavailable Thermal profile from the **active** Functional/Transition registries (old baseline blobs still pinned by Git ancestry and archived FDEG graph), preserve all nine surviving live profile checks, verify the historical `include_thermal_diffusion` default from the immutable functional graph, and replace live source-bound code7 capture with pinned ZIP validation. The FDEG code7 negative graph-tampering test remains. Repository CI's exact Workflow step ownership contract is updated to match the renamed historical verification/upload steps.

**No owner approval is implied** by these simulated profile lifecycle edits. The independent post-cut `verify_retired` gate and all Native/coverage/compatibility receipts remain blocking. This cut is not mergeable to main; it does not produce a proven safe-to-delete verdict.
