# Phelps-based pure O2 Boltzmann base collision set — source preparation

Date: 2026-10-30. Issue: https://github.com/HyungseonSong-plasma/moose-test-repo/issues/419
Solver science issue: https://github.com/HyungseonSong-plasma/moose-test-repo/issues/412
**Classification: SOURCE-READY-TO-EXTRACT; NOT AN EXECUTABLE/ACCEPTED FULL EEDF COLLISION MODEL.**

## Pinned primary source, rights and conversion

- Source: A. V. Phelps, *Compilation of Electron Cross Sections Used by A. V. Phelps*, revised 2008-06-24, O2 section, printed pages 2–8. https://us.lxcat.net/notes/index.php?download=phelps5
- Source terms: https://us.lxcat.net/instructions/redistribution.php . Obtain the PDF after personally satisfying the provider's access/acknowledgment conditions. Do not commit, redistribute or archive the original source PDF or derivative raw numeric tables in a public PR without appropriate rights.
- Original units: 1E-16 cm² per printed numerical sigma; conversion to SI: multiply by 1E-20 m². Published `QSCALE` has already been applied; do not multiply again. Linear interpolation between original knots was used by Phelps/BACKPRO; source artifact quirks must not be silently edited.

## Phelps 1978 source census (18 sections), 14 selected for extraction

**User chemistry allowlist:** only the 25 reactions in Issue #419 may be chemically activated. Phelps's 18-section original list remains a bibliographic inventory, but Three-body attachment is excluded because it is not in Chemistry, and rotation (KIN-R01), O2(b1Sigma) (KIN-E01) and 130-nm effective excitation (KIN-E02) are excluded by the approved reduced-complexity model. Selection is now **14** Phelps sections. Separate momentum/rotational/vibrational input candidates are *physical Boltzmann diagnostics*, not authorization for new chemical reactions.

| Local key | Exact Phelps channel | Samples | Energy loss eV | Main role |
|---|---|---:|---:|---|
| momentum_effective | `O2 MOMENTUM-TRANSFER CROSS SECTION` | 66 | not applicable | **effective Qm**; NOT pure elastic recoil |
| attachment_three_body | `O2 THREE-BODY ATTACHMENT` | 36 | 0 | **EXCLUDED — not in canonical Chemistry Table; no extraction or computation** |
| attachment_two_body | `O2 TWO-BODY ATTACHMENT` | 20 | 0 (bookkeeping) | dissociative electron attachment; physical threshold ≠ bookkeeping loss |
| rotation_300K | `O2 SINGL LEVEL ROT PKQ FOR 300K` | 48 | 0.020 | **EXCLUDED by user simplification; source data not extracted** |
| v1_low | `O2 V=1 LINDER AND SCHMIDT WITH SPLIT PK` | 48 | 0.190 | vibrational excitation |
| v2_low | `O2 V=2 LINDER AND SCHMIDT X2` | 42 | 0.380 | vibrational excitation |
| v3_low | `O2 V=3 LINDER AND SCHMIDT X2 WITH 9EV RES FRM WONG-TRAJMAR` | 48 | 0.570 | vibrational excitation |
| v4_low | `O2 V=4 LINDER AND SCHMIDT X2 WITH 9EV RES FRM WONG-TRAJMAR` | 40 | 0.750 | vibrational excitation |
| v1_9eV | `O2 V=1 9V RES OF WONG ET AL NORM TO TRAJMAR ET AL` | 16 | 0.190 | additional high-energy resonance contribution to same v=1 product |
| v2_9eV | `O2 V=2 9V RES OF WONG ET AL NORM TO TRAJMAR ET AL` | 16 | 0.380 | additional high-energy resonance contribution to same v=2 product |
| a1delta | `O2 SING DELTA FROM LINDER-SCHMIDT AND TRAJMAR ET AL` | 26 | 0.977 | O2(a1Delta_g) excitation (registry 407) |
| b1sigma | `O2 B SINGLET SIGMA FROM LINDER-SCHMIDT AND TRAJMAR ET AL` | 26 | 1.627 | **EXCLUDED by user simplification; source data not extracted** |
| loss_4p5 | `O2 4.5 LOSS` | 16 | 4.5 | energy-loss-only; NOT validated 2O(3P) dissociation (registry 411 HOLD) |
| loss_6 | `O2 6.0 LOSS` | 12 | 6.0 | energy-loss-only; distinguish Cosby dissociation (registry 412) |
| loss_8p4 | `O2 8.4 LOSS HAYASHI ABOVE 20EV - CHANTRY BELOW` | 18 | 8.4 | effective electronic excitation; no resolved O2(a) product |
| loss_10 | `O2 9.97 LOSS TRAJMAR` | 24 | **10.0** | effective electronic excitation; label ≠ actual loss |
| ionization | `O2 IONIZATION` | 24 | 12.06 | O2+ molecular ionization (registry 415) |
| line_130nm | `O2 130 NM LINE MUMMA-ZIPF` | 12 | 14.7 | **EXCLUDED by user simplification; source data not extracted** |

**Outside original 1978 set:** P. C. Cosby (1993), `O2 DISSOCIATION - BASED ON TABLE I OF`, 15 points, is a *separate source/model choice* already prepared by `collect_phelps_o2_channels.py` in this PR. Do NOT simply append that collision energy sink to all other 1978 channels; Phelps explicitly discusses non-perturbative rate-diagnostic use to avoid double-counting the dissociation energy loss.

## Canonical Chemistry table + 7 selected Boltzmann kinetic-only entries

The canonical Issue #419 **25-row Chemistry Table remains unchanged** (22 electron-impact + 3 heavy-particle reactions). Exactly 14 of the Phelps source's original 18 sections are selected; **7** correspond to already-listed Chemistry IDs `401, 407, 411, 412, 413, 414, 415` and are not duplicated. **7** have explicit `KIN-*` IDs in the supplemental Issue #419 Boltzmann collision table:

| Internal ID | Source channel | Class | Selected-state policy |
|---|---|---|---|
| KIN-M01 | `momentum_effective` | Effective momentum | Required; physics convention HOLD |
| KIN-V01 | `v1_low` | Vibrational | Required for complete Phelps O2 base |
| KIN-V02 | `v2_low` | Vibrational | Required for complete Phelps O2 base |
| KIN-V03 | `v3_low` | Vibrational | Required for complete Phelps O2 base |
| KIN-V04 | `v4_low` | Vibrational | Required for complete Phelps O2 base |
| KIN-V01R | `v1_9eV` | 9-eV vibrational resonance | Requires overlap/branch accounting |
| KIN-V02R | `v2_9eV` | 9-eV vibrational resonance | Requires overlap/branch accounting |

Full 14-row source CSV: [OXYGEN_BOLTZMANN_COLLISION_INVENTORY.csv](OXYGEN_BOLTZMANN_COLLISION_INVENTORY.csv). Provenance: Phelps 2008 compilation, original headings and sample counts. Every entry is `NUMERIC_CROSS_SECTION_NOT_VERIFIED`. Note the diagnostic/support-only status of kinetic processes: selection for potential EEDF input **does not mean chemical production/loss source activation**. No HPEM Special Numbers have been assigned to the invented internal KIN IDs.

**Never import/compute `attachment_three_body`:** It is the permanently excluded unregistered source section, absent from the 25 allowed chemistry reactions. The original publication contains it, but neither local extraction nor the C++ Boltzmann source selection may activate it. Reaction 2058 is a permitted, distinct two-body excited-O2 attachment requiring its own source; it is not part of this original ground-O2 17-section Phelps subset.

## Local extraction — only after obtaining the PDF under source conditions

```bash
CHEM=experiments/Issue395_powered_chemistry_ladder
python3 "$CHEM/collect_phelps_o2_core_set.py" \
  --source /path/to/phelps5.pdf \
  --output-dir "$CHEM/.local_cross_sections/phelps_o2_1978" \
  --retrieved-on 2026-10-30
```

This program performs **all-or-nothing source validation** of headings, source loss, QSCALE, sample count, sequential indices, energy ordering and known threshold anchors before writing any CSV. It writes 14 **local** CSVs and `phelps_o2_core_manifest.json` with per-file SHA-256. **No three-body attachment CSV is generated**, even if that section exists in the source PDF. Outputs are source-extraction artifacts and are never automatically approved solver inputs.

## Final simplified collision selection — 33-row canonical registry (2026-10-30)

The consolidated 33-entry scope in Issue #419 is **25 Chemistry + 7 kinetic-only supports + 1 atomic-O elastic**. Phelps O2 `KIN-M01` effective (Q_m) is the **single selected O2 momentum-transfer input**. The formerly proposed `KIN-EL-O2` has been removed as redundant for this **effective-scattering model choice**. Its Itikawa O2 elastic source can remain a scientific alternate/reference in the literature, but is **not** a second active collision, registry row, or automatically added scattering term. `KIN-EL-O` e + O(3P) → e + O(3P) remains selected when atomic oxygen is present. Three-body attachment stays excluded.

**Necessary solver gate:** effective O2 `Q_m` represents elastic plus inelastic *momentum* transfer. It does **not** authorize substituting effective (Q_m) for the **pure elastic recoil-energy coefficient**. Existing developmental C++ `ElasticTarget.momentum_transfer_m2` expects elastic recoil while `field_momentum_transfer_m2` can represent full first-harmonic field scattering. If a physically valid pure O2 elastic recoil cross-section cannot be reconstructed from the effective and process-resolved inelastic datasets or obtained as internal solver data, stop and do not claim physical EEDF acceptance. Inelastic scattering and effective (Q_m) also must not be counted twice. Source-specific nonnegative reconstruction and energy-closure checks are required before running real-data Oxygen cases.

**Canonical CSV:** [OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv](OXYGEN_FINAL_UNIFIED_COLLISION_REGISTRY_33.csv). The earlier 37- and 36-entry inventories are superseded by this selection decision. `KIN-M01` remains source-numeric **NOT_VERIFIED**.

## Mandatory physical preflight before any C++ EEDF run

1. **Effective momentum:** `Qm,eff` includes nonelastic scattering per Phelps introductory notes. The solver's `ElasticTarget.momentum_transfer_m2` controls elastic recoil; its optional `field_momentum_transfer_m2` controls first-harmonic field heating. Do not feed `Qm,eff` into the recoil parameter or add inelastic momentum twice. A independently verified elastic-recoil cross section or conservative, nonnegative momentum decomposition is required first. The repository's existing collision-coverage preflight rejects unqualified EFFECTIVE+growth combinations.
2. **Rotation:** In printed 300 K data, the 33rd and 34th records both use **1.230 eV** with different sigma. This is **not strictly interpolable**; the extractor preserves source order and marks the knot as BLOCKED. No jitter, averaging, dropping or sorting without an explicit source correction and sensitivity test. At Tg other than 300 K, assess transferability.
3. **Three-body attachment:** **NOT SELECTED, NOT CALCULATED.** It is outside the approved 25-reaction Chemistry Table. No O2- chemistry species, numerical cross-section import, EEDF source/sink or rate lookup is permitted for this channel. Reaction 401 (ground O2 two-body attachment) remains in the selection; reaction 2058 (O2(a1Delta) two-body attachment) is in the approved Chemistry Table but requires a separate state-specific source.
4. **Vibration:** Low-energy and 9-eV resonance channels overlap in product v=1 and v=2. Keep their source identities and energy losses explicit; if collapsing, sum only validated collision contributions once.
5. **Species bookkeeping:** Phelps's 4.5-eV and 6-eV energy-loss channels do not automatically imply `2O(3P)` reaction products. Model effect on EEDF separately from chemical rate reporting. Preserve O2(a), O2(b), O- and O2+ distinctions; superelastic rates require excited-target fractions.
6. **Solver coverage:** Use the real PR #408 C++ developmental solver on its own non-main branch, with source-hash checked inputs, positivity/normalization/energy flux and adaptive-grid checks. Its full EFFECTIVE/growth and production coupling are still subject to Issue #412. The out-of-registry three-body channel is excluded. Avoid claiming science PASS from synthetic fixtures or successful Repository CI.
7. **Execution conditions:** Pure neutral O2 (fraction 1.0) is the first independent preflight case. Tg=300 K matches the rotational approximation; E/N, gas density, electron fraction and energy-domain policy must be set as explicit run inputs, not fabricated from a 400 W/1000 W RF power label. E/N in Td: 1 Td = 1e-21 V m².
8. **Acceptance:** Only after the above gates, actual authorized sigma pairs, complete cross-section coverage, source hashes, and comparison to native BOLSIG+ / published transport/attachment/ionization can the result be called physics-validated. A resulting `Te -> k` table is **not** the original sigma(E) source.

## Deliverable state (2026-10-30)

- [x] Original 18-section Phelps census; **14 selected** (Three-body attachment, R01, E01, E02 excluded).
- [x] Local-only extractor, strict provenance manifest and synthetic regression tests on PR #420.
- [ ] Real original Phelps PDF locally obtained under provider conditions in the execution environment.
- [ ] **Real** 14-selected-section sigma(E) CSV extraction and SHA readback; no excluded-channel CSVs.
- [ ] Effective-momentum/recoil physics resolution; rotation and three-body attachment explicitly OUT OF SCOPE.
- [ ] Full C++ EEDF execution using this oxygen source.
- [ ] 407/412 etc. verified rate table and independent Formula comparison.
- [ ] P2/P3 governed Physics runtime acceptance.

**Runtime safety:** Do not overwrite existing `physics_app/data/electron_impact/` coefficient tables or promote this under unverified source physics.

## Reduced-precision approximation (user decision, 2026-10-30)

KIN-R01, KIN-E01, and KIN-E02 are **out of the active solver inventory** and deliberately not exported. This may alter low-energy EEDF/transport, inelastic energy-loss budget, and high-energy tails (respectively rotational, b-state excitation, and 130-nm emission-related losses). Retain the original scientific source census above for traceability; neither absence nor a successful synthetic CI proves numerical insignificance. Before claiming quantitative accuracy over a specified E/N range, perform a sensitivity study versus a fuller collision model. The 25 approved Chemistry rows and 7 remaining kinetic-support rows are unchanged.
