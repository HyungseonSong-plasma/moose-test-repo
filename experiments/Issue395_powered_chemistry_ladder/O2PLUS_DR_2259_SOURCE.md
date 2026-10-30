# Oxygen chemistry #419: Reaction 2259 — O2+ dissociative recombination

**Status (2026-10-30):** Original **literature source verified**; measured
energy range and independently published thermal-rate fit identified.
Original numerical cross-section pairs **not retrieved / not digitized**.
An authorized-local-import, source-hash, SI-conversion and later-rate
comparison workflow is implemented in `collect_o2plus_dr_2259.py`.
No rate lookup table, full Boltzmann EEDF, or MOOSE kinetic source has been
constructed, activated, or scientifically accepted.

## Reaction identity

```text
ID 2259: e + O2+(X 2Pi_g, v=0) -> O + O
type: dissociative recombination (DR); NOT electron-impact dissociation,
      NOT dissociative ionization, NOT O2+ dissociative excitation.
stoichiometry per event: electron -1, O2+ -1, neutral O nuclei +2.
net charge change: -1 electron and -1 positive ion simultaneously, 0 net charge.
collision partner: O2+ ion, NOT neutral O2.
```

The proposed total reaction is state-unresolved. Measurements show production
of atomic O(3P), O(1D) and O(1S) in multiple branches; setting all products
to 2O(3P) requires a separately justified *effective ground-state closure*.
Peverall (2001) reports the O(1D) **atomic quantum yield 1.17 ± 0.05**
per DR event, so assuming **two O(3P)** is not source-consistent.

DR is **exothermic** and produces atom internal/kinetic energy. **No fixed
positive electron-energy loss** should be applied by copying a neutral-O2
electron-impact loss. Literature reports ~6.95 eV released for
O(3P)+O(3P) at near-zero collision energy, with lower energy release
for excited product states; this is **channel-specific release**, not
a 6.95-eV electron energy sink.

## Primary cross-section source

R. Peverall et al. (2001), *Dissociative recombination and excitation of
O2+: Cross sections, product yields and implications for studies of
the ionospheric airglows*, *Journal of Chemical Physics* **114**,
6679–6689, DOI https://doi.org/10.1063/1.1349079 .

- [AMOLF institutional repository](https://ir.amolf.nl/pub/1211)
- **Measured DR cross section:** O2+ electronic/vibrational ground-state
  `X 2Pi_g,v=0` with electrons from **1 meV to 3 eV** collision energy.
- **Avoid confusing:** the *dissociative excitation* (DE) cross section,
  whose threshold is ~6.7 eV and maximum ~3e-16 cm2 at ~15 eV.
- **Data availability:** journal repository metadata/abstract are verified,
  but an exact digital machine-readable sigma(E) table has **not** been
  identified or downloaded. A graph or an analytic thermal fit does not
  constitute the measured raw table. Permission/attribution apply to any
  externally obtained numerical digitization.
- **Cross-validation:** P. M. Mul and J. W. McGowan (1979),
  *J. Phys. B* **12**, 1591, DOI
  https://doi.org/10.1088/0022-3700/12/9/011,
  measured electron-ion DR cross sections over 0.007–1 eV.
- **Ion vibrational dependence:** Petrignani et al. (2005),
  *J. Chem. Phys.* DOI https://doi.org/10.1063/1.1825991
  reports resolved DR rates and branching. A ground-vibrational
  dataset must not silently be applied to excited ion populations.

### Local source acquisition / immutable provenance

Obtain the actual numeric **total DR** cross-section data directly from
the original authors, publisher, or an authorized verified digitization.
Record source DOI, experimental/ion-state identity, and any instrument or
data-reduction caveats. Do **not** fabricate values from the thermal
rate-law. Do not redistribute copyrighted data without permission.

Prepare local **source CSV** (not committed):

```text
collision_energy_eV,cross_section_cm2
[source measurements only, strictly increasing energies]
```

Then from the repository root:

```bash
CHEM=experiments/Issue395_powered_chemistry_ladder
python3 "$CHEM/collect_o2plus_dr_2259.py" extract \
  --source-csv /path/to/verified_Peverall2001_O2plus_DR.csv \
  --output-dir "$CHEM/.local_cross_sections/o2plus_dr_2259" \
  --retrieved-on YYYY-MM-DD
```

The utility validates strict numeric/positive energies and sigma, a minimum
sample count, representative lower/upper collision-energy coverage,
no zero-energy anchor, expected original units, source SHA-256,
and a duplicate-write guard. It converts **cm² → m²** by factor **1e-4**,
producing `o2plus_dr_2259_sigma.csv` and
`o2plus_dr_2259_provenance.json`.
Both are Git-ignored; the converter **cannot independently establish**
that user-provided points actually originate from the cited experiment.
Only an authorized primary source/provenance audit can do that.

## Boltzmann Lookup — separate from electron-neutral Phelps channels

The general relation is

```text
k_2259 = integral[ sigma_DR(eps)*sqrt(2*e*eps/m_e)*f_E(eps) d(eps) ] [m3/s]
```

where `eps` is electron-ion **relative collision energy [eV]**,
`f_E(eps)` is the normalized *energy probability density* in [1/eV],
and sigma_DR is in [m2]. Heavy-ion relative speed is usually negligible
but the adopted reduced mass/relative-energy treatment must be documented.

Use the separately solved electron EEDF and the **electron-ion DR cross
section**, **not** the Phelps neutral-O2 excitation/ionization set.
The source range is 0.001–3 eV. No artificial extrapolation beyond it.
In particular, electron temperatures of several eV can give appreciable
EEDF weight outside the measured DR cross-section range; a defensible
extension or separate sensitivity treatment is required.

For physical number densities the event rate is

```text
r_2259 [events/(m3 s)] = k_2259 [m3/s] * ne [1/m3] * nO2plus [1/m3]
R_2259 [mol/(m3 s)]   = r_2259 / N_A
```

The eventual Physics kernels must use **a single canonical progress**:
electron sink `-R_2259`, O2+ sink `-R_2259` and oxygen-atom source
`+2 R_2259` distributed across measured state branches. If only O(3P)
is solved, the effective closure and downstream excited-state quenching
must be explicit. Never treat the ion concentration as `neutral O2`.

## Historical Formula (benchmark only)

Peverall (2001) derived the **thermal** rate law

```text
k_ref(Te_K) = 2.4e-13 * (300/Te_K)^0.70 [m3/s]
Te_K > 200 K
k_ref(300 K) = 2.4e-13 m3/s
```

The exponent's quoted experimental uncertainty is ±0.01.
`Te_eV = (8.617333262145e-5 eV/K)*Te_K`.
This is an empirical thermal Maxwellian benchmark, **not** a
digitized sigma(E), a source collision operator, or Boltzmann output.

When *real* computed Lookup rates are available, compare them with
the benchmark (same electron temperature/ion internal state) using:

```bash
python3 "$CHEM/collect_o2plus_dr_2259.py" compare \
  --boltzmann-rates-csv /path/to/2259_boltzmann_rates.csv \
  --report-json /path/to/2259_formula_vs_lookup.json
```

Input comparison format: `Te_K,k_lookup_m3_s`.
Do not claim Physics scientific validation from a formula comparison
alone. Source-data acceptance, product-state branching, energy balance,
and real `physics-opt` P2/P3 validation remain mandatory.
