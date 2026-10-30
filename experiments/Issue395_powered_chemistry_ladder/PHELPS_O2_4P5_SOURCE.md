# Reaction 411: source-backed Phelps O2 4.5 eV LOSS cross section

**Chemistry registry:** [Issue #419](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/419)

## Primary source and provenance

- A. V. Phelps, *Compilation of Electron Cross Sections Used by A. V. Phelps*, file last revised **2008-06-24** as printed in the document.
- Original source PDF: https://us.lxcat.net/notes/index.php?download=phelps5
- Original oxygen swarm cross-section provenance: Lawton and Phelps, *J. Chem. Phys.* **69**, 1055 (1978), as acknowledged in the Phelps compilation.
- Exact source heading: **`O2 4.5 LOSS`**, PDF **page 7** (zero-indexed page 6).
- Metadata: `ENERGY LOSS = 4.500`, `LOWER LIMIT = 4.386`, `UPPER LIMIT = 14.990`, `QSCALE = 1.000000`.
- **16 points** with incident electron energy in eV; original cross section is in `1e-16 cm^2` (= `1e-20 m^2`). Interpolate **linearly**, following Phelps's introductory instructions. Do not treat the 50/10,000-eV zero-tail tabulation anchors as separately validated high-energy physics.
- This original source distinguishes `O2 4.5 LOSS`, `O2 6.0 LOSS` and an explicit, separate `O2 DISSOCIATION` dataset based on P. C. Cosby, *J. Chem. Phys.* **98**, 9560 (1993).

## Copyright-safe collection procedure

LXCat preserves contributor ownership and restricts redistribution: https://us.lxcat.net/instructions/redistribution.php. Do **not** commit either the original PDF or its extracted numerical table into the repository. Download the original for authorized local research use from the source site; preserve retrieval date, attribution and the unmodified file.

With Python 3 and `pdftotext` installed (for PDF sources), from the repository root run:

```bash
python3 experiments/Issue395_powered_chemistry_ladder/collect_phelps_o2_4p5.py \
  --source /path/to/phelps5.pdf \
  --output-dir experiments/Issue395_powered_chemistry_ladder/.local_cross_sections/phelps_411 \
  --retrieved-on YYYY-MM-DD
```

The converter also accepts an independently produced `pdftotext -layout` `.txt` input. It **does not download data** or accept website terms on the user's behalf.

Two **Git-ignored** local outputs are created:
- `o2_4p5_loss_sigma.csv`: `electron_energy_eV,cross_section_m2` for the future Boltzmann input, not a rate coefficient.
- `o2_4p5_loss_provenance.json`: source URL, revision, retrieval date, input SHA-256, output SHA-256, channel ID, units, count and science-acceptance warning.

Extraction fails closed if the exact channel, source units, loss, section boundary, 16 samples, ordered energy axis or endpoint anchors disagree. Existing files require explicit `--replace` to overwrite. Synthetic regression tests live in `tests/characterization/test_collect_phelps_o2_4p5.py` and contain no original numeric table.

## Future Boltzmann solver boundary

**Source identification is established; the user-proposed Reaction 411 `e+O2 -> e+2O(3P)` is *not* validated as the product channel of Phelps's 4.5-eV LOSS data.** No reaction rate table, O atom creation, production coupling, or physical runtime acceptance is implied. The conflicting [PR #418](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/418) remains in need of scientific correction.

A complete, internally consistent O2 cross-section set (elastic/momentum transfer, attachment, vibrational and electronic excitation, ionization, etc.) and a specified gas/EEDF model are needed to **solve** the Boltzmann equation. For a normalized electron-energy distribution `f_E(ε)`, the eventual coefficient for the selected 4.5-eV *energy-loss* process is:

```text
k_4p5 = integral[ sigma_4p5(eps) * sqrt(2*e*eps/m_e) * f_E(eps) d(eps) ]
```

Here `eps` is in eV, `sigma` in `m^2` and `k` in `m^3/s`. This collision rate alone does **not** establish an O atom source. Do not conflate this cross-section process with 6-eV loss / Reaction 412.
