# Issue #419 — Screenshot-specified oxygen chemistry census (25 rows)

**Date:** 2026-10-30. **Owner:** https://github.com/HyungseonSong-plasma/moose-test-repo/issues/419 .
**Input:** user screenshot with 25 reaction rows, A,n,E, exothermicity, Special Number and Comment.
**Status:** DATA / MODEL PROVENANCE CENSUS ONLY — not a Boltzmann-computed rate table, cross-section file redistribution, science acceptance, or production chemistry switch.

## Source and identity rules

- The screenshot carries `A=0,n=0,E=0,exothermicity=0` for its **22 electron-collision rows** because `Uses Cross-Section` is checked. These zeros are not measured cross sections, reaction thresholds, or a zero rate. Apply HPEM special number and source-verified threshold **separately**.
- It carries **three heavy-particle formulas** with the same generic Special Number `1`; uniquely key by screenshot row `H23/H24/H25`, not by Special Number.
- `O2^` means `O2+`; `O^` means `O+`; `O2*` in 2058-2074 maps provisionally to `O2(a1Delta_g)`. In 413/414 the effective excited channel **must not automatically map** to that metastable state. Screenshot `O*` in rows 935 and 936 conflates **O(1D)** and **O(1S)** and requires distinct species.
- E/N-dependent Boltzmann rate lookup `k = integral sigma(ε) v(ε) f_E(ε) dε` is the **electron channel target**; published Maxwellian `k(Te)` fits are **comparators**, never placeholders for missing σ(E). `Te` in eV unless otherwise specified; formulas below are m³/s, except rows H23-H25 (cm³/s source coefficients).
- HPEM **threshold** differs from a chosen energy-loss convention (notably 401, 417, 2259). Ground-state dissociation and excited-target molecular branching require specific checks.
- Numeric σ(E) are **not bundled**. Original Phelps values are copyright/redistribution controlled. The existing PR #420 local-only parser stages the Phelps eight-channel conversion. HPEM `RFXSECS_NEW.F` special numbers identify sections, but the public reaction listing is **not** an energy–sigma dataset.

## Source inventory, reaction-level lookup and formula comparison

| Image row | HPEM ID / unique key | Reaction | HPEM threshold eV | Source of sigma or model | Actual sigma acquisition status | Rate formula reference, not primary | Validation caution |
|---:|---|---|---:|---|---|---|---|
| 1 | 401 | `e+O2(X) -> O-+O` | ~3.5 | Phelps O2 TWO-BODY ATTACHMENT | local extraction pending | `—` | loss 0 convention ≠ threshold |
| 2 | 407 | `e+O2(X) -> O2(a1Delta)+e` | 0.98 | Phelps O2 SING DELTA (26 points) | local extraction pending | `1.37e-15 exp(-2.14/Te)` | 0.977 eV model |
| 3 | 411 | `e+O2(X) -> 2O+e` | 4.50 | Phelps O2 4.5 LOSS (16 points) | species mapping HOLD | `none valid` | 4.5 eV below 2O(3P) physical onset |
| 4 | 412 | `e+O2(X) -> 2O+e` | 6.00 | Phelps 6.0 LOSS vs Cosby O2 DISSOCIATION | parent source distinction | `1.41e-15 Te^-0.22 exp(-2.98/Te)` | exclusive alternatives with 411 |
| 5 | 413 | `e+O2(X) -> O2*(eff)+e` | 8.40 | Phelps O2 8.4 LOSS (18 points) | local extraction pending | `none matched` | O2*(eff) not necessarily a1Delta |
| 6 | 414 | `e+O2(X) -> O2*(eff)+e` | 10.00 | Phelps O2 9.97 LOSS TRAJMAR (24 points) | local extraction pending | `none matched` | printed energy loss 10 eV |
| 7 | 415 | `e+O2(X) -> O2+ + 2e` | 12.06 | Phelps O2 IONIZATION (24 points) | local extraction pending | `Kim: 2.34e-15 Te^1.03 exp(-12.29/Te)` | molecular parent ionization only |
| 8 | 417 | `e+O2(X) -> O+ + O + 2e` | 17.00 | Krishnakumar/Srivastava O+ partial sigma | numeric partial sigma pending | `Kim: 1.88e-16 Te^1.699 exp(-16.81/Te)` | HPEM 17 vs prior model 20 eV loss |
| 9 | 2259 | `e+O2+ -> 2O` | 0.00 | Peverall 2001 O2+ DR sigma | measured source, grid pending | `2.4e-13 (300/Te_K)^0.70` | thermal formula T>200 K; product branches |
| 10 | 2058 | `e+O2(a1Delta) -> O- + O` | 3.50 | Jaffke 1992 / HPEM RFXSECS | partial peak facts only | `4.19e-15 Te^-1.376 exp(-5.19/Te)` | full excited-target sigma requested |
| 11 | 2067 | `e+O2(a1Delta) -> O2(X)+e` | -0.98 | 407 inverse detailed balance, gX/ga=3/2 | inverse σ transform prepared | `2.06e-15 exp(-1.163/Te)` | electron gains ~0.977 eV |
| 12 | 2068 | `e+O2(a1Delta) -> 2O+e` | 3.52 | HPEM O2*-ELECTRONIC 4.5eV | species & energetics HOLD | `none valid` | 3.52 below 2O(3P) limit ~4.14 |
| 13 | 2069 | `e+O2(a1Delta) -> 2O+e` | 5.02 | HPEM O2*-ELECTRONIC 6eV | excited-state σ unverified | `no independent matched formula` | threshold shift assumption |
| 14 | 2072 | `e+O2(a1Delta) -> O2+ + 2e` | 11.08 | Kim 2006 threshold-shift; HPEM | model derived σ only | `2.34e-15 Te^1.03 exp(-11.31/Te)` | state-specific measurement not verified |
| 15 | 2073 | `e+O2(a1Delta) -> 2O+e` | 13.72 | HPEM O2*-130nm LINE EXCITE | mapping/σ HOLD | `none matched` | CRITICAL: 5.023 previously assigned to 2073 is wrong |
| 16 | 2074 | `e+O2(a1Delta) -> O+ + O + 2e` | 16.02 | HPEM excited-state O+ partial channel | partial sigma pending | `no independently matched excited-state fit` | CRITICAL: 19.023 legacy assignment wrong |
| 17 | 943 | `e+O(1D) -> O(3P)+e` | -1.97 | inverse of 935 (Laher–Gilmore) | inverse σ pending forward source | `(9/5)exp(1.97/Te) k935_ref` | Maxwellian detailed balance, not independent |
| 18 | 944 | `e+O(1D) -> O+ + 2e` | 11.65 | Tayal/Zatsarinny atomic O(1D) ionization | review curves, numeric pending | `none verified` | not same as 941 ground O ionization |
| 19 | 2738 | `e+O- -> O + 2e` | 2.70 | HPEM O- detachment | complete numeric source pending | `none verified` | electron source +1 |
| 20 | 935 | `e+O(3P) -> O(1D)+e` | 1.97 | Laher–Gilmore atomic excitation | published curves, grid pending | `4.47e-15 exp(-2.286/Te)` | Gudmundsson 1-7eV |
| 21 | 936 | `e+O(3P) -> O(1S)+e` | 4.19 | Laher–Gilmore atomic excitation | published curves, grid pending | `4.54e-15 exp(-4.49/Te)` | screenshot O* conflates 1D and 1S |
| 22 | 941 | `e+O(3P) -> O+ + 2e` | 13.62 | NIST SRD107 / Laher–Gilmore | available model, grid pending | `none matched` | source-specific σ(E) required |
| 23 | 1 (H23) | `O+ + O- -> 2O` | n/a | QDB-API 1377 screenshot | heavy-particle formula | `A=1e-7 cm3/s, n=0, E=0` | SI prefactor 1e-13 m3/s |
| 24 | 1 (H24) | `O- + O2+ -> O2+O` | n/a | QDB-API 1378 screenshot | heavy-particle formula | `A=1e-7 cm3/s, n=0, E=0` | SI prefactor 1e-13 m3/s |
| 25 | 1 (H25) | `O+ + O2 -> O+O2+` | n/a | QDB-API 1115 screenshot | heavy-particle formula | `A=2e-11 cm3/s, n=-0.4, E=0` | SI A 2e-17, temperature convention TBD |

## Priority correction to canonical issue #419

- **2073:** HPEM 2026-02-16 official reference is `O2*-130nm LINE EXCITE`, energy **13.72 eV**, NOT 5.023 eV. Previous Kim-derived `6.86e-15 exp(-5.31/Te)` corresponds to a different lower-energy 6.0-eV-related metastable dissociation model and must **not** be attached to 2073 until process identity is reconciled.
- **2074:** HPEM official reference is **16.02 eV**, NOT 19.023 eV. Legacy `16.81-0.977` shifted formula is not a reaction-matched independent benchmark and must not be used as if calibrated to HPEM 2074.
- **417:** HPEM lists a 17.00-eV threshold whereas an earlier research model used 20.0-eV assigned loss. Keep these independent; no silent change of runtime energy bookkeeping.
- **2068:** HPEM 3.52 eV < ~4.14 eV physical threshold for `O2(a1Delta) -> 2O(3P)`; no scientifically valid 2O-source activation without reclassification.
- **935/936:** Separate excited oxygen state species O(1D) and O(1S) before any executable model acceptance.
- Existing issue #419 rows and prior source statements remain historical evidence where superseded by exact HPEM list. Update the issue body before claiming all 25 reactions are in the canonical registry.

## External references and acquisition route

1. HPEM electron impact list (v174a, 2026-02-16), pp. 137–138: https://cpseg.eecs.umich.edu/pub/data/e_reactions.pdf . This provides identifiers, comments, thresholds and ICOLION but **not** numerical σ(E).
2. Phelps O2 cross-section compilation, original local acquisition under its terms: https://us.lxcat.net/notes/index.php?download=phelps5 . See PR #420 local Phelps channels extractor.
3. LXCat third-party redistribution rule: https://us.lxcat.net/instructions/redistribution.php .
4. Gudmundsson et al. (2000) atomic/molecular Maxwellian 1–7 eV fits: https://cden.ucsd.edu/internal/Publications/Archive/SFR/Plasma/PlanarIndOxyDisch.pdf .
5. Sungjin Kim (2006), Table 2.1 / Appendix A metastable formulas and threshold-shift approximations: https://www2.eecs.berkeley.edu/Pubs/TechRpts/2006/EECS-2006-56.pdf .
6. Laher and Gilmore (1990), atomic-O excitation and ionization cross sections: https://doi.org/10.1063/1.555872 .
7. Song et al. (2026) reviewed molecular/atomic oxygen sources, accepted CC-BY manuscript: https://discovery.ucl.ac.uk/id/eprint/10222954/ .
8. NIST SRD 107 ionization data/model: https://www.nist.gov/pml/electron-impact-cross-sections-ionization-and-excitation-database .
9. Peverall et al. (2001), experimental O2+ DR source and thermal rate: https://ir.amolf.nl/pub/1211/ .
10. QDB-API references 1377/1378/1115 are **screenshot-only labels** until independent live QDB retrieval is verified.

## Acquisition/acceptance next steps

1. Obtain compatible complete O2 and O electron collision source sets, not only the selected reaction channels. Preserve source version, license, SHA-256, state identity, energy units, cross-section units and original energy grid.
2. Where measurement exists but only a plot/source description is public, mark `REFERENCE_IDENTIFIED_NUMERIC_NOT_ACQUIRED`; never fit a made-up sigma curve or treat threshold-shift outputs as independent measurement.
3. Generate non-Maxwellian EEDF and lookup `k(Te)` with explicit E/N, composition, pressure/temperature, density/state fractions, solver version and interpolation range. Compare to Maxwellian formulas only on stated domain.
4. Validate electron/ion/oxygen nuclei bookkeeping; avoid double-counting 411/412, 2068/2069, 413/414 and 2073 source channels; keep source-species states consistent.
5. Require proven Physics `physics-opt` governed execution before any production `PASS`. Until then, all newly added chemistry is `SCIENTIFIC HOLD`.
