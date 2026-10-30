# Reaction 414: Phelps O2 9.97 LOSS, with 10.000 eV model energy loss

**Registry:** [Oxygen Chemistry #419](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/419)

**User-assigned reaction:** e + O2 -> e + O2* (effective electronic excitation; same equation as 413).
**Electron loss per collision:** **10.000 eV**, distinct from Reaction 413's 8.4 eV.

## Primary-source provenance

A. V. Phelps, *Compilation of Electron Cross Sections Used by A. V. Phelps*, revision 2008-06-24, https://us.lxcat.net/notes/index.php?download=phelps5, **PDF page 8 (zero-based page 7)**. The heading is **O2 9.97 LOSS TRAJMAR**, with metadata:
- ENERGY LOSS = 10.000 (eV)
- LOWER LIMIT = 9.778; UPPER LIMIT = 100.001
- QSCALE = 1.000000
- 24 tabulated electron-energy / cross-section pairs
- Original sigma unit: 1e-16 cm² = 1e-20 m² per tabulated value
- Interpolation: linear, as specified by Phelps.

The **9.97** in the source's channel *name* and **10.000** in its actual energy-loss *parameter* have distinct meanings; retain both.

[COMSOL Dry Air Boltzmann Analysis](https://doc.comsol.com/6.4/doc/com.comsol.help.models.plasma.boltzmann_dry_air/boltzmann_dry_air.html) models this nominal 9.97-eV channel as effective excitation, whereas [COMSOL Oxygen Boltzmann Analysis](https://doc.comsol.com/6.4/doc/com.comsol.help.models.plasma.boltzmann_oxygen/boltzmann_oxygen.html) uses e + O2 -> e + O + O(1S) dissociation. Do not infer atom production from the chosen 414 effective-O2* bookkeeping reaction without a separate state-resolved science decision.

## Locally acquire and validate (no redistribution)

[LXCat redistribution policy](https://us.lxcat.net/instructions/redistribution.php) requires attribution and directs users to acquire the data at its source. The numerical cross-section table and original PDF are **not** committed. Obtain the original source for authorized local use and run, from repository root:

    python3 experiments/Issue395_powered_chemistry_ladder/collect_phelps_o2_9p97.py \
      --source /path/to/phelps5.pdf \
      --output-dir experiments/Issue395_powered_chemistry_ladder/.local_cross_sections/phelps_414 \
      --retrieved-on YYYY-MM-DD

Python 3 and pdftotext are needed for PDF input. An independently generated pdftotext -layout .txt file is also accepted. The program does not download data or accept terms on the user's behalf.

Git-ignored outputs:
- o2_9p97_loss_sigma.csv — columns electron_energy_eV,cross_section_m2
- o2_9p97_loss_provenance.json — source and output SHA-256, date, units, source channel, 24-point count, exact loss, and redistribution/scientific warnings.

The extractor fails closed on incorrect channel, section boundary, energy loss/limits, QSCALE, point count, negative/nonfinite sigma, nonincreasing energy and altered tail anchors. Existing outputs are not overwritten without --replace. Synthetic regression tests **do not contain original cross-section numerical values**.

## Future Boltzmann rate table

This is cross-section **input acquisition**, not a computed chemistry lookup. A consistent complete O2 collision set, defined EEDF solver conditions, collision rate integration and separate product/energy conservation validation are required before publishing any k(Te), including checking the difference between effective excitation and dissociative product interpretations. No production chemistry activation or physics-opt scientific PASS is implied.
