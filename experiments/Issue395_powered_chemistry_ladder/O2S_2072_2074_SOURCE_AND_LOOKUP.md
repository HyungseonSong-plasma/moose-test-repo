# Oxygen chemistry #419: O2(a1Delta_g) reactions 2072, 2073, 2074

Date: 2026-10-30. STATUS: source-chain identified, numerical primary data not acquired, derived excited-state sigma not experimentally validated, no Boltzmann rates generated.

## Species identity and primary literature

Here O2* is O2(a1Delta_g), the Physics O2s / w_O2s species, not an arbitrary excited oxygen molecule. Internal state energy = 0.977 eV. Physics authority: docs/development/2026-09-07_issue17_r0_reaction_ledger.json.

Sungjin Kim (2006), UCB/EECS-2006-56, Table 2.1 and Appendix A, https://www2.eecs.berkeley.edu/Pubs/TechRpts/2006/Archive/EECS-2006-56.pdf models electron collisions with O2(a1Delta_g) using a **0.98-eV threshold reduction** relative to matching ground-state channels. This is a model assumption, NOT independently measured metastable-state collision cross sections.

| ID | Reaction | Type | Exact parent cross-section source | Status |
|---|---|---|---|---|
| 2072 | e + O2(a1Delta_g) -> O2+ + 2e | Ionization | Ground-state O2->O2+ (415), Phelps original O2 IONIZATION | Derived-model preparation; measured O2* sigma not acquired |
| 2073 | e + O2(a1Delta_g) -> O(3P)+O(3P)+e | Dissociation | Ground-state **physical dissociation** (412), Phelps compilation referencing Cosby 1993 | Derived-model preparation; product-state parity requires review |
| 2074 | e + O2(a1Delta_g) -> O+ + O(3P) + 2e | Dissociative ionization | Ground-state **O+ fragment partial** ionization (417), Krishnakumar and Srivastava 1992 | Original O+ partial numeric data NOT acquired |

Phelps original source https://us.lxcat.net/notes/index.php?download=phelps5 ; 2072 parent source section: O2 IONIZATION. For 2073 use the **separate** O2 DISSOCIATION - BASED ON TABLE I OF section (P. C. Cosby, J. Chem. Phys. 98, 9560, 1993). The O2 6.0 LOSS section is NOT automatically a dissociation cross section. For 2074 use Krishnakumar & Srivastava (1992), DOI https://doi.org/10.1016/0168-1176(92)87037-F , **partial O+ fragment** channel; never use the ground-state molecular O2+ parent-ion or total ionization curve.

## Proposed model energy accounting — not physical acceptance

Under the chosen approximate 0.977-eV initial state offset:
- 2072: parent 415 modeled loss 12.06 - 0.977 = **11.083 eV**.
- 2073: parent 412 modeled loss 6.0 - 0.977 = **5.023 eV**.
- 2074: parent 417 modeled loss 20.0 - 0.977 = **19.023 eV**.

These numbers are **provisional model conventions**, NOT experimentally measured thresholds or approved energy sinks. The effective collision energy and outgoing energy partition require a separate scientific review. Do not silently add them to Physics energy equations.

## Local, non-redistributing cross-section workflow

Tool: prepare_o2s_eimpact_2072_2074.py . Input ground-state CSV columns: electron_energy_eV,cross_section_m2 . A source-linked parent provenance JSON and exactly matched parent reaction/channel/CSV SHA-256 are mandatory. The tool rejects unknown data, total-vs-partial ionization confusion, the loss-only channel for 2073, non-monotone or negative sigma, and overwriting local outputs.

The model shift uses sigma_model(E) = sigma_parent(E + 0.977 eV), with sigma magnitudes unchanged. This is NOT a state-resolved experimental sigma and is labeled DERIVED_MODEL_ONLY_NOT_EXPERIMENTAL_O2STAR_CROSS_SECTION. Both raw and model-derived datasets remain local; never commit LXCat or author-owned numerical arrays without permission.

For 2072/2073, PR #420 provides a local parent Phelps provenance manifest (channels 415 and 412_dissociation). For 2074, an independently sourced 417 O+ partial CSV needs metadata: reaction_id=417, parent_channel=Oplus_fragment_partial, original_target_state=O2(X3Sigma_g-,v=0), original_source_doi=10.1016/0168-1176(92)87037-F, source SHA-256 and CSV SHA-256. Metadata self-declarations do not independently certify a paper's real numerical data.

Example invocation after obtaining verified original data:

    python3 experiments/Issue395_powered_chemistry_ladder/prepare_o2s_eimpact_2072_2074.py derive --reaction-id 2072 --ground-sigma-csv /path/to/o2_415_sigma.csv --ground-provenance-json /path/to/phelps_o2_channels_provenance.json --output-dir experiments/Issue395_powered_chemistry_ladder/.local_cross_sections/o2s_2072 --retrieved-on YYYY-MM-DD --accept-model-threshold-shift

For 2073 select parent o2_412_dissociation_sigma.csv, for 2074 use the verified partial O+ CSV and source manifest. No direct remote fetch, measured arrays or fabricated cross-section magnitudes are bundled.

## Historical formulas — future Lookup comparison only

Kim (2006), Table 2.1, Maxwellian Te between 1 and 7 eV; all k in m3/s, Te in eV:

- 2072: k_ref = 2.34e-15 Te^1.03 exp(-11.31/Te).
- 2073: k_ref = 6.86e-15 exp(-5.31/Te).
- 2074: Kim specifies threshold reduction, but no independent metastable-state numerical fit. The script optionally compares to **derived, not independently fitted** 1.88e-16 Te^1.699 exp(-(16.81-0.977)/Te), which is only a heuristic, NOT a direct integration of sigma(E).

After an actual EEDF/Boltzmann solve, feed independently computed reaction_id,Te_eV,k_lookup_m3_s rows to:

    python3 experiments/Issue395_powered_chemistry_ladder/prepare_o2s_eimpact_2072_2074.py compare --rates-csv /path/to/real_boltzmann_rates.csv --report-json /path/to/comparison.json

The report gives relative deviation without claiming physics acceptance. Proper electron energy balance, mass/charge closure, and a resolved O2s density in the coupled MOOSE runtime are prerequisites for scientific activation. No production chemistry is changed by this PR.
