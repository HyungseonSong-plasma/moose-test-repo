# Oxygen electron cross sections outside LXCat — source discovery and acquisition

**Date:** 2026-10-30. **Scope fixed:** 33 entries: 25 Chemistry + 7 kinetic supports + 1 atomic-O elastic. User-excluded KIN-R01, KIN-E01, KIN-E02, KIN-EL-O2 and three-body attachment remain OUT. **No actual Boltzmann solver run or rate lookup**.

## Direct numerical sources now found outside LXCat

**Zenodo 8192503 (Schmalzried, 2023), BOLSIG+ `Cross section.txt`**

- Dataset landing page: <https://zenodo.org/records/8192503>
- **Direct numeric original public file:** <https://zenodo.org/records/8192503/files/Cross%20section.txt?download=1>
- Registered DOI: <https://doi.org/10.5281/zenodo.8192503>
- File size about **2.7 MB**, published MD5 **`c0c1073f5ea940568ce4925b8b242e1a`**.
- Data is explicitly an energy (eV) vs cross-section (m²) dataset with source-fitting provenance comments. **It is a compiled/model-fitted derivative dataset; not the private HPEM numerical cross sections and not necessarily independent primary measured tables.**
- **Explicitly matched numeric sections and source metadata:**

| Canonical row | Source exact e + O process | Source threshold | Provenance stated in source | Assessment |
|---|---|---:|---|---|
| `KIN-EL-O` | `E + O -> E + O, Momentum` | 0 eV | Williams & Allen (1989), ELSEPA above 10 eV | Correct atomic-O elastic momentum-transfer target; verify recoil convention |
| `EI-935` | `E + O -> E + O*((2p4)1D), Electronic` | 1.967 eV | Fit to Doering (1992) and Shyn | Correct O(3P) → O(1D) target/product |
| `EI-936` | `E + O -> E + O*((2p4)1S), Electronic` | 4.190 eV | Fit to Gulcicek & Doering (1989) and Shyn | Correct O(3P) → O(1S) target/product |
| `EI-941` | `E + O -> E + O+, Total` | 13.60 eV | RBEQ fit to Brook (1978), Rothe | Correct atomic-O total ionization process; compare HPEM 13.62 eV |

The four **public numerical arrays are individually visible within the file** and have been reviewed at their exact source headers, not guessed from database category search. They remain `PUBLIC_TABULATED_EXACT_PROCESS_CANDIDATE` until the unchanged numeric file is downloaded, pinned by checksum, validated for physical units/energy support and assessed against alternative original sources.

## More independent sources found (do not count as equivalent numeric processes)

- **Zenodo 19250744 (Duling et al., 2026):** <https://zenodo.org/records/19250744/files/cross_sections.txt?download=1>. The file has *measured and extrapolated* energy-vs-cross section data from `10^1`–`10^5` eV, columns for **total electron-impact O₂ ionization**, OI 1356 Å **dissociative excitation** of O₂ and OI 1356 Å excitation of O, in **cm²** (conversion to m² requires `× 10^-4`). The total ionization column contains O₂⁺/O⁺/multiply charged products; **it CANNOT replace `EI-415` O₂⁺ partial ionization or `EI-417` O⁺ fragment ionization independently**. Safe as **independent high-energy/total-ionization benchmark** only.
- **NIST SRD 107:** <https://www.nist.gov/pml/electron-impact-cross-sections-ionization-and-excitation-database>. Molecular O₂ BEB ionization benchmark: <https://pml.nist.gov/cgi-bin/Ionization/graph_new.pl?element=O2.0>. BEB theoretical total ionization curve, not production-specific partial `EI-415` or `EI-417`; not a source replacement.
- **NIST Journal of Physical and Chemical Reference Data 2026:** Song et al. (2026), DOI <https://doi.org/10.1063/5.0287254>, UCL open-access manuscript <https://discovery.ucl.ac.uk/id/eprint/10222954/>. Reviews recommended electron+O and electron+O₂ elastic, excitation and ionization with uncertainty; cite and compare but **no complete independently machine-readable numerical export was verified**.
- **Laher & Gilmore (1990):** open NIST paper DOI <https://doi.org/10.1063/1.555872> with O(1D), O(1S) excitation and ionization review. Published tables/figures are not a verified downloadable `sigma(E)` machine data file here.
- **Burrow (1973), O₂(a1Delta) attachment:** <https://digitalcommons.unl.edu/physicsburrow/17/> reports a measured cross-section maximum **(4.6 ± 1.3) × 10⁻¹⁸ cm²** for `EI-2058`; full numerical energy series not acquired. Belic & Hall (1981) DOI <https://doi.org/10.1088/0022-3700/14/2/019> is another experimental study; cannot derive full `sigma(E)` from the peak alone.
- **Peverall et al. (2001), O₂⁺ dissociative recombination:** <https://ir.amolf.nl/pub/1211/> reports experimental **1 meV–3 eV** cross sections and O(¹D) yield but no verified downloadable machine vector. Its Maxwellian DR rate fit is **NOT** a non-Maxwellian electron-energy cross section.
- **Krishnakumar & Srivastava (1992), O₂ partial/dissociative ionization:** <https://ntrs.nasa.gov/citations/19930054456> (NASA record reports **no downloadable file**); article DOI <https://doi.org/10.1016/0168-1176(92)87037-F>. Preserve O⁺ fragment `EI-417` separately from total O₂ ionization.

## Combined coverage and what "acquired" means

| Coverage class | Count | Source state |
|---|---:|---|
| Original previous **Phelps/Cantera** numeric candidates | **14** | Remote readable arrays, not original LXCat/solver verified |
| Newly found **Zenodo atomic-O** process-matched numeric candidates | **4** | Remote readable arrays, exact source process, local checksum unverified |
| Remaining **without process-matched numeric tables** | **15** | Includes 12 electron-impact Chemistry + 3 heavy-particle QDB formulas |
| Total frozen collision list | **33** | No chemistry additions |

This **18/33 numeric candidate** count does not mean 18 validated Physics reactions, nor 18 distinct independently measured datasets. No original numerical files have been downloaded into the GitHub branch. **Availability on a public external web page is not the same as repository ingestion.**

### How to acquire the 4 new numerical datasets privately

Use the new restricted extractor: [`acquire_zenodo_atomic_o_cross_sections.py`](acquire_zenodo_atomic_o_cross_sections.py).

```bash
python3 experiments/Issue395_powered_chemistry_ladder/acquire_zenodo_atomic_o_cross_sections.py \
  --download --output-dir /private/oxygen_atomic_zenodo
```

The CLI downloads the source directly, verifies the complete published MD5, refuses changed labels or threshold, parses strictly monotonic/positive four process-specific energy arrays, and records source SHA-256, per-channel CSV SHA-256 and source parameters in a manifest. Output is **private** and `solver_ready=false`. For controlled offline access, use `--source /private/path/Cross_section.txt` instead of `--download`.

**Current execution environment limitation:** The runtime filesystem's DNS/network connection to Zenodo failed; therefore **the original source file has not been saved locally here**. However, the external numeric resource exists and was directly inspected by the web retrieval tool. Do not assert original data acquired, checksummed, or EEDF-ready until the command is successfully run. Check Zenodo file/reuse license before redistributing numeric tables.

## Immediate verification gates

1. Download the Zenodo source and compute MD5/SHA-256 of its original bytes in private working directory; save dataset DOI and retrieval date.
2. Validate `KIN-EL-O, EI-935, EI-936, EI-941` source-specific sigma(E) units, thresholds, first/last energy knots, and whether other source channels must be excluded.
3. Compare O(1D)/O(1S) excitation source curves to Song et al. (2026) uncertainty assessment; atomic O ionization 13.60 vs HPEM 13.62 eV.
4. Reuse the Duling et al. dataset **only for composite O₂ total-ionization benchmarking** and only within measured/meaningful energy range, not as partial `EI-415/417` lookup.
5. Obtain actual Phelps/Cantera 14 candidate arrays locally under source terms. Seek state-specific O₂(a¹Δg), O(¹D), O⁻, O₂⁺ original numerical sources for remaining electron reactions. **No new chemical reactions**.
