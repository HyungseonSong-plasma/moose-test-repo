# Issue #419: O2 cross-section-first Lookup and legacy formula benchmarks

**Date:** 2026-10-30. This is a *design/data acquisition* update.
**Authoritative registry:** https://github.com/HyungseonSong-plasma/moose-test-repo/issues/419
**Original source:** A. V. Phelps, *Compilation of Electron Cross Sections Used by A. V. Phelps*, last revision 2008-06-24, https://us.lxcat.net/notes/index.php?download=phelps5 .

## Source sections identified in original PDF

All are **electron collision cross sections** indexed by incident energy in eV; sigma values in
`1e-16 cm2` (convert 1 numerical unit to `1e-20 m2`). The source says to linearly interpolate
between points. Original `QSCALE` is preprocessing provenance, not an instruction to scale the
published sigma values a second time.

| ID | Registry reaction | Exact original section | PDF page | Points | QSCALE | Treatment |
|---|---|---|---:|---:|---:|---|
| 401 | `e+O2 -> O+O-` | `O2 TWO-BODY ATTACHMENT` | 3–4 | 20 | 1.2 | Dissociative attachment; do not use three-body attachment |
| 407 | `e+O2 -> e+O2(a1Delta_g)` | `O2 SING DELTA FROM LINDER-SCHMIDT AND TRAJMAR ET AL` | 6 | 26 | 1.0 | Excitation |
| 411 | `e+O2 -> e+2O(3P)` (requested, unvalidated) | `O2 4.5 LOSS` | 7 | 16 | 1.0 | **Energy-loss only**, O production not supported |
| 412 (loss) | `e+O2 -> e+2O(3P)` | `O2 6.0 LOSS` | 7 | 12 | 1.0 | **6.0-eV loss**, NOT source-confirmed dissociation |
| 412 (physical) | same | `O2 DISSOCIATION - BASED ON TABLE I OF` (Cosby 1993) | 8–9 | 15 | N/A | Explicit dissociation cross section, separate from the 1978 set |
| 413 | `e+O2 -> e+O2*` | `O2 8.4 LOSS HAYASHI ABOVE 20EV - CHANTRY BELOW` | 7–8 | 18 | 1.0 | Effective electronic excitation; branching unresolved |
| 414 | `e+O2 -> e+O2*` | `O2 9.97 LOSS TRAJMAR` | 8 | 24 | 1.0 | **10.0 eV energy loss** in source, not 9.97 eV; branching unresolved |

**Primary dataset warning:** The Cosby dissociation data are an *additional* set outside the
Phelps 1978 swarm-inversion set. Phelps says that using 8.4-eV loss as a dissociation
proxy can greatly overestimate dissociation below 30 eV. Do NOT add 412 loss and
412 physical dissociation as two independent energy sinks without kinetic reconciliation.
411 and 412 share the user's currently assigned stoichiometry; do not activate both
without resolving double-counting, threshold/energetics, and actual product branching.

## Authorized local extraction

LXCat [redistribution policy](https://us.lxcat.net/instructions/redistribution.php) restricts
third-party redistribution. This PR deliberately includes **no original numerical
cross-section arrays**. Obtain the primary PDF under its terms and retain it locally.

```bash
CHEM=experiments/Issue395_powered_chemistry_ladder
python3 "$CHEM/collect_phelps_o2_channels.py" \
  --source /path/to/phelps5.pdf \
  --output-dir "$CHEM/.local_cross_sections/phelps_all" \
  --retrieved-on YYYY-MM-DD
```

The extractor also accepts faithful local `pdftotext -layout` `.txt` exports.
It requires the exact source heading, 401's non-unit QSCALE, original energy loss,
point count, strict energy ordering and threshold anchors for each channel. All
channels must parse successfully before any CSVs are written. The original
unmodified file and individual converted outputs are identified by SHA-256.
The existing `.gitignore` excludes the output directory; do not commit the PDF,
any extracted files or generated cross-section tables without explicit permission.

Outputs are:
```text
o2_401_sigma.csv
o2_407_sigma.csv
o2_411_sigma.csv
o2_412_loss_sigma.csv
o2_412_dissociation_sigma.csv
o2_413_sigma.csv
o2_414_sigma.csv
phelps_o2_channels_provenance.json
```

Each CSV has `electron_energy_eV,cross_section_m2`. **No file here is a
`Te -> k` lookup table.** The 401 existing
`physics_app/data/electron_impact/o2_attachment.txt` contains a rate lookup,
not the raw Phelps cross section; do not conflate them.

## Solver and Formula comparison contract

1. Assemble a physically consistent complete O2 Boltzmann collision set, with
   momentum transfer, rotational/vibrational, metastable excitation, attachment,
   additional electronic excitation, ionization, appropriate electron-electron
   and atomic-oxygen components if the case requires them. The six prepared
   sections alone are **not a complete EEDF closure**.
2. Choose a compatible EEDF model and operating-condition grid (E/N, gas
   temperature, O2/O mixture ratio, pressure / ionization regime as relevant).
   Do not infer a Maxwellian EEDF solely from mean energy.
3. Compute normalized electron-energy distributions and evaluate
   `k_j = integral[ sigma_j(eps) v(eps) f_E(eps) d(eps) ]`.
4. For each meaningful `Te` or mean energy, tabulate
   `reaction_id,Te_eV,k_lookup_m3_s`. The `Te` mapping uses
   `Te=(2/3)*mean_electron_energy` and is a parameterization of the solved
   EEDF; it does not make the EEDF Maxwellian.
5. Only **after** generating genuine Boltzmann rate tables, run
   ```bash
   python3 experiments/Issue395_powered_chemistry_ladder/compare_o2_lookup_formula.py \
     --rates-csv /path/to/boltzmann_rates.csv \
     --report-json /path/to/formula_vs_lookup.json
   ```
   The comparison preserves historical **407** Gudmundsson
   `1.37e-15*exp(-2.14/Te)` (Maxwellian validity 1–7 eV) and
   **412** Zhao `1.41e-15*Te**-0.22*exp(-2.98/Te)` as *benchmark*
   laws, never authoritative rate generators. **411's old
   `1.07e-15*exp(-3.43/Te)` is for O2(ex1), not the user-assigned
   `2O(3P)` dissociation, and is excluded.**
6. Before switching any MOOSE **runtime** source from formula to
   interpolated lookup, require real calculated tables, metadata/provenance,
   collision energy/temperature coverage, error and energy-source regression,
   source-species consistency, and controlled `physics-opt` P2/P3 comparison.
   The present PR does **not** switch any deployed runtime chemistry formula
   to an empty/invented table.

**Original scientific references:** Gudmundsson et al., *J. Phys. D* **33**
1323–1331 (2000), Table 3, DOI https://doi.org/10.1088/0022-3727/33/11/311;
Zhao et al. (2024), *Phys. Plasmas* **31** 083507,
DOI https://doi.org/10.1063/5.0214357;
P. C. Cosby, *J. Chem. Phys.* **98** 9560 (1993), as attributed in Phelps.
