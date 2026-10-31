# Oxygen ICP 400/1000 W: effective 25-reaction O(ex) chemistry

**Current user decision: 2026-10-31.** Restore EI-936 to the powered ICP
chemistry. Keep the physical HPEM identity `e + O(3P) -> e + O(1S)` in
the original 25-reaction registry, but map its product to the single effective
atomic excitation species **O(ex)**, represented by the existing `Os` /
`w_Os` variable. EI-935 independently also produces that effective state.
No separate O(1S) PDE, transport, wall species or O(1S) level is introduced.

## Current effective-state reaction owners

- EI-935: `e + O(3P) -> e + O(ex)`, independent lookup `R_935`,
  electron energy loss **1.97 eV**.
- EI-936: `e + O(3P) -> e + O(ex)`, separate `R_936`,
  electron energy loss **4.19 eV**. Never reuse `R_935` as `R_936`.
- Both reactions contribute `-R` to O(3P), `+R` to O(ex), and no net
  electron particle source. Their individual 1.97/4.19-eV losses are
  separately included in the electron-energy source.
- EI-943/944 continue to act on the combined `Os` pool using the
  pre-existing O(1D)-derived rates. This is a **model approximation**, not
  state-resolved O(1S) kinetics. The 4.19 vs 1.97 eV excitation energies
  imply a 2.22 eV unresolved internal-energy distinction per EI-936 event.
- `n_O_ex_avg` is the preferred diagnostic; legacy `n_O_1D_avg`
  is an alias for the **same effective Os density**, not a genuine
  state-resolved O(1D) density in this revised model.

## EI-936 rate selection

The input generator first looks for a genuine, validated
`EI-936_O_3P.txt` private 100-point rate lookup. If it exists, its own
`PhysicsElectronImpactRateMaterial` owns `R_936`, independent of 935.
Its grid and nonnegative finite rate values must pass the same checks as
the 19 mandatory original rate tables. No missing table is synthesized.

If absent, the generator uses an **analytic rate expression**:

```text
Te_eV = (2/3) * mean_en_solved_eV
k936 = 4.54e-15 * exp(-4.49 / Te_eV)      [m3/s]
R936 = k936 * n_e_physical * c_chem24_O   [mol/(m3 s)]
```

Reference: J. T. Gudmundsson et al., *On the plasma parameters of a planar
inductive oxygen discharge*, J. Phys. D: Appl. Phys. 33 (2000) 1323–1331,
**Table 3**, https://cden.ucsd.edu/internal/Publications/Archive/SFR/Plasma/PlanarIndOxyDisch.pdf.

**Validity:** literature fit uses a Maxwellian electron distribution over
approximately **1–7 eV**; using `(2/3) mean_en_solved` to represent Te
does not reproduce the actual non-Maxwellian EEDF-integrated rate. Retain
scientific HOLD for the numeric source and effective-state approximation.

## Chemistry census and restart lineage

The original provenance registry remains **25 physical reactions**.
The selected active approximation is **25 effective reactions**:
19 mandatory lookup channels, optional 20th lookup for 936; two other
electron formulas (2259, 2738), plus 936 analytic when its table is absent;
three heavy-particle formulas (H23, H24, H25).

**Do not inject this changed network into the pre-existing 2 ns or 4 ns
MOOSE checkpoint.** Checkpoint recovery requires physics/network identity.
The 2026-10-31 cross-run 2→4 ns workflow uses its original 24-reaction
input and separate immutable SHA. A future EI-936 simulation must create a
new 0→2 ns checkpoint and progress from it before any 4→100 ns continuation.

## Historical 2026-10-30 notes (superseded where conflicting)

The subsequent original 24-channel discussion is retained as background
for the earlier decision. All statements below excluding EI-936,
disallowing O(1S) mapping, or counting 24 active reactions have been
**superseded by the user decision above**.

## User-selected EI-407/413/414 effective O2(a) lump

For the 400/1000 W ICP research case ONLY:
- EI-407, EI-413 and EI-414 retain distinct 100-point lookup rate owners.
- All three reactions convert O2(X) -> O2(a1Delta_g), solver species **O2s**.
- Combined molar production rate: R_EI407 + R_EI413 + R_EI414.
- O2s mass source: +0.032 * (R407+R413+R414) kg/(m3 s).
- Constrained O2(X) mass sink: -0.032 * (R407+R413+R414) kg/(m3 s).
- Electron particle source: zero for all three.
- Electron energy source: -(0.977 R407 + 8.4 R413 + 10.0 R414).
- The earlier O2star active-product placeholder is retired for these 2
  channels; it remains in the immutable source inventory for provenance.
- This **does not validate the microscopic branching** of Phelps 8.4/9.97-eV
  loss channels into actual O2(a1Delta_g). This is a user-selected surrogate.

The executable overlay generator is
`build_lumped_o2a_ei407_413_414.py`. The private 100-point lookup files
are NOT in the public repo; provide them through `--rate-dir` at build time.

Selection, stoichiometry, and standalone overlay tests do not make a complete
24-source ICP case. Coupling other chemistry channels and real 400/1000 W
`physics-opt` --check-input/transient runs remain pending. Do not claim
density trends from this gate.

## User-selected approximate dissociation (2026-10-30)

The purpose is a consistent reduced chemistry, not state-resolved scientific
validation. Keep the 24-channel active count.

- EI-411: e + O2(X) -> e + 2 O(3P) = source +0.032 R411 to `w_O`
- EI-2068: e + O2(a) -> e + 2 O(3P) = source +0.032 R2068 to `w_O`
- EI-2073: e + O2(a) -> e + 2 O(3P) = source +0.032 R2073 to `w_O`

O(3P)=`O`, O(1D)=`Os`, O2(a)=`O2s`; no new species.
These are explicit *effective reaction assumptions*, not exact threshold/
branching assignments. EI-411's 4.5 eV and EI-2068's 3.52 eV loss models
are not thermochemically consistent with producing two ground-state O atoms.
Retain channel-specific losses as explicitly chosen modeling parameters.

**EI-412 is not intrinsically duplicate of EI-411.** Existing Zhao DISS-G
empirical fit is a potential second owner of the *same total dissociation
source*. In the new research run, activate individual R411+R412 lookup
progress and DISABLE the legacy Zhao fit instead of summing all three.

**EI-2259:** select provisional thermal formula k=2.4e-13
(300/Te[K])^0.70 m3/s (Te>200 K), not an EEDF lookup.
**EI-2738:** allow a provisional rate model, but its concrete numeric
coefficient/table is still required before running; never fabricate it.
**EI-2074:** provisional partial ionization rate can be used if an explicit
source table/model is present; a shifted EI-417 curve is not a verified
state-specific EI-2074 measurement.

**H23, H24, H25** are selected for the exploratory model. Retain the
existing research coefficients and H25's assumed k=2e-17*(Tg/300K)^(-0.4)
m3/s; science source verification is not a prerequisite for this preliminary
run. This marks *selection only*; it does not imply the heavy source kernels
are connected or that the 400/1000 W transient has run.

## Electron-rate policy resolution (2026-10-30)

- **EI-412**: `Lookup` from the original 100-point mean-electron-energy table.
  Disable the parallel legacy Zhao fitted DISS-G source in the selected 24-channel run.
- **EI-2074**: independent measured `e+O2(a) -> O+ + O + 2e` partial
  cross-section NOT verified in available evidence. Kim (Berkeley, 2006),
  Appendix A, explicitly used a **0.98 eV shifted threshold** from the
  ground-state O2 partial channel, i.e. a model, NOT an independent
  state-specific measurement. No automatic method switch in this step.
- **EI-2259**: adopt thermal `Formula`,
  `k=2.4e-13*(300/Te_K)^0.70 [m3/s]` for `Te_K > 200`, from Peverall
  2001. Actual DR cross sections **were measured** at 0.001-3 eV;
  the local numeric table/EEDF integral is simply unavailable.
- **EI-2738**: adopt `Formula`,
  `k=2.0e-13*exp(-5.5/Te_eV) [m3/s]`, where
  `Te_eV=(2/3)*mean_en_solved_eV`. This is the `e+O- -> 2e+O`
  model in Chinese Physics B 24 (2015) 095203 and Plasma Science
  Technology 26 (2024) 125401, with `2.0e-7 cm3/s` converted
  to `2.0e-13 m3/s`. The **5.5 eV** Arrhenius-like fit parameter
  is distinct from the old **2.70 eV** model electron energy loss.
  Standalone source-coupled overlay: `build_ei2738_detachment_formula_overlay.py`.
  Not yet proven in a 24-channel powered transient.

Do not confuse `physics-opt` smoke CI with an executed 400/1000 W ICP transient.

## EI-2074 original HPEM numeric evidence recovered (2026-10-30)

**Correction to prior 'no independent cross section' claim.**
The user-supplied private HPEM `O2ex.dat` includes
`Process: 18; CROSS SECTION=O2* > O^ + O + E + E;`
`SPECIAL NUMBER=2074; THRESHOLD=16.023eV; NUMBER POINTS=1001`,
with energy in eV and sigma in cm2.
This is **a separate numeric HPEM reaction channel**, not a
threshold-shifted EI-417 rate. The locally prepared
`private_rates/EI-2074_O2_a1Delta.txt` has **100 mean-energy/rate rows**,
in eV and m3/(mol s). Use EI-2074 **Lookup** in this experimental case.

HPEM numeric *existence* does NOT establish an independent
state-resolved laboratory measurement or full scientific validation.
Private raw numeric sources remain outside public GitHub. The
model-specific 100-point lookup is not yet connected to the powered ICP
source kernels.

Source sha256:
`90a44f145e92f435bfc3d895bb92d2f901e71d6d93719e79e2d0bd508aaff09d`.
Rate table sha256:
`156239a4b3771d9bb5f9e41287671e8f3b40e8f7651682ad7ccdf75f595124e6`.
