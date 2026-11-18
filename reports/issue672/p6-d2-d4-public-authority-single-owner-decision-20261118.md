# P6-D2 / D4 — Public D Lookup Authority & Single-Owner Execution Contract

**Decision:** `D2_SOURCE_AUTHORITY=FROZEN` · `D4_EXECUTION_CONTRACT=FROZEN` · `D4_IMPLEMENTATION=NATIVE_HOLD` · `PR684_MERGE=HOLD` · `SCIENCE_HOLD`.

## Immutable versions and meaning of PASS

Parent Draft PR #665 exact HEAD `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`; unmerged candidate Draft PR #684 `3e48a0651ac53ec32e34b4b31e44098ffad80e1c`; historical input `29d1acc6ef7969908b86719e4b95c73a1565136d`. P5 latest exact-head W1 binary `1bdc85c65f5847ae58d51c76f89f8e67c67291dc9b5ee842bcbab98c4a71befa` exists for New-only P2, **not** Public D PR684. Current #684 code still has zero reactions and no Chemistry action in Public D overlay and fails prior to P05; source-only guard success must never promote it to native or scientific PASS.

## D2 — Three explicitly separated authorities

| Mode ID | Input SHA256 | Actual verified Native evidence | What it authorizes |
|---|---|---|---|
| `HISTORICAL_ORIGINAL_100ROW_COMPATIBILITY` | `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387`, original Issue91 electron_moments.txt 100 rows | [CI #44324197618](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44324197618): **417/941 B/D 4/4 Native P2 PASS** using historical PR #578 source `1efdd922...` and same historical ELF `617b8316...`; original table unchanged | History-preserving *pinned compat* P2 only. NOT modern generated New-only, NOT P3/P4 |
| `EXISTING_PUBLIC_RESEARCH_PREPARED_42ROW` | `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`, original separately named `.github/oxygen25_eedf/initial_mixture_23xsec_transport.txt`, 42 rows | The 42-row model's prior research operation is acknowledged; however [PR #684 Public D CI #44323024938](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44323024938) 417/941 P2 both **exit 1** because Chemistry source generator is absent | Independent *prepared research* input version. No 100-row numerical/byte equivalence claim, no modern Public D Native PASS |
| `DEDICATED_GENERATED_NEWONLY_42ROW` | Same exact 42-row SHA, different **code and owner mode** | [#44322557957](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44322557957) 417/941 both Native P2 +16/16 intentional negative, same latest-head ELF `1bdc85c65f58...`; P5-X still needs same-ELF Warehouse inventory/full D8 | New-only P2-only route; neither historical compat nor a Public D science approval |

**Scientific authority distinction:** The 42-row pathway has been used successfully for research, but it is not identical to the immutable 100-row original. The actual C++ reduced lookup interpolation differs (source audit at 5, 10 and 20 eV). Different physical data versions must carry different source-path+SHA+mode IDs. Do not overwrite the historical 100-row path and then assert it was original. Existing workflows which copy the prepared 42-row file to the old relative pathname must expose this as an explicit prepared-mode stage, not hidden provenance.

## D4 — Deterministic e/O2p/Om/Op single-owner contract

**Public D 11-layer disposable case only**; archive inputs, Public B 10-layer, protected EI Rate originals, main and PR #665 remain immutable.

1. Preserve e/O2p/Om/Op signed charges **−1/+1/−1/+1**. All three ion mobilities originate from original C0 functors `ion_mobility`, `negative_ion_mobility`, `atomic_positive_ion_mobility`, with corresponding diffusion functors; original constants μ=10 m²/(V·s), D=0.25851999786435537 m²/s. No arbitrary synthetic coefficients. 100-row vs 42-row electron lookup keeps its own exact source/path, reduced/clamp, actual p/T functor values.
2. Retire **exactly 4** existing manual Transport Material owners, and generate them once from JSON: `electron_transport`, `O2p_species_transport_alias`, `Om_species_transport_alias`, `Op_species_transport_alias`. Keep electron particle and energy aliases, **5/3 energy mobility and diffusion** and all original charge/Poisson/wall/surface-current consumers. Preserve **8 FEM electron sheath BC** source meanings.
3. `fem_species='e'` and `fvm_species='O2p Om Op'` only. **Mandatory** active `[Physics]/[Plasmas]/[Transport]/[Chemistry]`. Use **real** 7-species/8-reaction 417/941 source: common `EI-02,EI-17,EI-415,EI-401,EI-407,EI-2069,H25` plus exactly one of `EI-417` or `EI-941`. Each selected ion must have nonzero stoichiometric participation in a real progress channel; actual (S_{O2p,molar}), (S_{Om,molar}), (S_{Op,molar}) originate from Chemistry's validated signed rate combination, not dummy/zero progress. Protected Rate source SHA and cleanup remain separate secure gate.
4. **No legacy old-ion 26 + generated 24 overlap.** For *approved* generated-only New-only staging, remove exactly **14 old Native ion FV Kernels +12 Native ion FV BCs** from copied inputs (26→0), and require real Warehouse **12 generated ion FV Kernels +12 FV BCs**, plus **8 original electron FEM BCs**, uniquely named and bound to actual equations. Keep original QVT main mesh, Maxwell child and seven Transfers for later D8 runtime review. Historical Hybrid keeps its separate old owner model, not partial cleanup.
5. Fail closed for missing Chemistry, missing or duplicate 8 reactions, changed signed source, table SHA mismatch, absent/multiple transport providers, unresolved energy/BC consumers, wrong P05 count, 26→0 incompleteness or a changed 100/42 file provenance. **Never** use `dont_create_kernels`, skip jobs, fake reactions, partial FVM selection or suppressed P05 to produce a green result.
6. **D5 acceptance after implementation:** exact authorized source HEAD and one actual ELF/2 app libs/OCI, real 417 and 941 `--check-input` exit 0; same-ELF Warehouse type/name/variable inventory 12+12+8, signed rates and consumer graph; N1–N8 ×2 deliberate expected P05 negative/restore cases; original 100 vs prepared 42 distinction recorded; protected EI tmpfs cleanup. **Then** P6-X→P7 approval. Native P3/P4 science remains separate approval.

## Current first-blocker / signed verdict

The existing PR #684 D option overlay selects three FV ions but **does not enable Chemistry**, and `plasma_species_only.json` has `reactions=[]` and `equations={}`. In the exact candidate C++ `DDContinuityEq.C`, `chemistryEnabled()` and `hasSpeciesSource(id)` are hard preconditions. The actual 42-row [CI #44323024938](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44323024938) 417/941 both exit 1 at `FV species kernels require [Physics]/[Plasmas]/[Transport]/[Chemistry] to generate species source functors`; **P05 NOT_REACHED**. The 100-row PR684 D attempts are **pre-Native rejects** at the explicit 42-row SHA guard; do not misreport them as Native tests. The historical source+original 100-row compatibility path separately passes 4/4 and must remain untouched.

**Implementation is NOT complete**, even when D2/D4 contract guard passes. #684 must **remain Draft / NOT MERGE** until the generated-mode Physics Chemistry and consumer ownership are implemented and Native verified. Newly approved scope: source contract and P2-only next implementation preparation, not a new physics scientific equivalence assertion.

## Evidence and executable checks

- Immutable machine-readable source/input mode contract: `reports/issue672/p6-d2-d4-public-authority-and-single-owner-contract-20261118.json`.
- Standard-library exact source+binary-stage guard: `ci/guards/p6_d2_d4_public_authority_contract_guard.py`, with pinned Git HEADs and **16 synthetic contract counterexamples**, not a real solver.
- [D5 actual Public D 100/42 split](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/672#issuecomment-6981577934).
- [Historical source100 417/941 B/D P2 4/4](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/672#issuecomment-6981820692).
- [PR684 P05 merge HOLD](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/684#issuecomment-6980545736).
- [P5-X newer source W1 P2+16 negatives](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/672#issuecomment-6981681850).

**Gate:** `P6_D2_CONTRACT=PASS_FROZEN`, `P6_D4_CONTRACT=PASS_FROZEN`, `P6_D4_ACTUAL_GENERATED_OWNER_IMPLEMENTATION=HOLD`, `P6_D5_PUBLIC_D_NATIVE_ACCEPTANCE=HOLD`, `PR684_MERGE=HOLD`, `SCIENCE_HOLD`. No production source/workflow, PR665/main, historical original or private data mutation.
