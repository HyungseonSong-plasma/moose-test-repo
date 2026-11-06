# Physics default-plot: 2d-map, time-trace, compare

**Canonical CLI:** python3 bin/physics.py default-plot

This is read-only postprocessing of solved native Exodus. No MOOSE solve or scientific PASS is claimed. Current species identities and neutral EOS are Oxygen14-specific; output field count is determined from actual native Exodus sources (and input files where available).

## Modes

- **2d-map** (default): available species number densities (m^-3), potential (V), electron temperature (eV), one native timestep. Auto layout; rainbow default colormap. Species use independent log colorbars; potential and electron temperature use independent linear colorbars. Missing fields are omitted with reasons, not invented.
- **time-trace**: plasma-weighted species number densities, volume-weighted potential, electron-number-weighted electron temperature, and native integrated RF power as functions of native time. Each quantity has its own subplot and proper units.
- **--compare RUN_2** is an option only for time-trace, not a separate mode. Each run retains its own native time grid; same physical quantity is overlaid on the same axis without interpolation, time resampling or changes to the source mesh. Explicit requests unavailable in either run fail. Default selection uses the intersection of available quantities.

The retired public modes --mode species and --mode fields are intentionally absent. Raw nodal plotting is not part of the public default-plot contract.

## Examples

~~~bash
# 2D plasma maps at the last native time
python3 bin/physics.py default-plot --exodus run_1/plasma.e \
  --input run_1/chemistry_off.i --output maps.png

# Explicit native map time, custom layout and color map
python3 bin/physics.py default-plot --mode 2d-map --run run_1 \
  --input run_1/chemistry_off.i --time-us 100 \
  --layout 4,4,2 --cmap viridis --output map_100us.png

# One run: complete weighted time histories
python3 bin/physics.py default-plot --mode time-trace --run run_1 \
  --input run_1/chemistry_off.i --output traces.png

# Two runs: overlaid weighted histories
python3 bin/physics.py default-plot --mode time-trace --run run_1 \
  --input run_1/chemistry_off.i \
  --compare run_2 --compare-input run_2/chemistry_on.i \
  --output compare.png

# Subset and explicit two-row layout
python3 bin/physics.py default-plot --mode time-trace --run run_1 \
  --compare run_2 --variables 'e-' 'O2+' 'T_e' power \
  --layout 2x2
~~~

--run accepts a directory containing plasma.e (or exactly one .e file) or a direct .e path; --exodus accepts a direct .e path. --input and --compare-input may be repeated for multiple MOOSE overlays. The available labels are e-, O2+, O-, O+, O2, O2*, O, O*, potential, T_e, and power (time-trace only). --variables selects and orders panels. --layout accepts auto, ROWSxCOLS (2x4), or row capacities (3,2), with centering for incomplete rows. --time-us and --time-index are 2d-map-only, because time-trace uses the entire native timeline. Output .png, .pdf or .svg, plus .json; overwrites require --overwrite.

## Source-backed physical quantities

- e-: native nodal log_ne -> N_A exp(log_ne), m^-3.
- O2+, O-, O+: plasma elemental log_ni, log_nm, log_nop -> N_A exp(log_state), m^-3.
- O2, O2*, O, O*: plasma elemental p, w_O2s, w_O, w_Os -> Oxygen14 mass-fraction mixture EOS. Mean molar mass M = 1/sum(w_i/M_i); rho=p*M/(R*T_g); n_i=rho*w_i*N_A/M_i. Source Oxygen14 molar masses: molecular 0.032 kg/mol and atomic 0.016 kg/mol. The unique literal T_g_fixed is read from --input when supplied; --gas-temperature-k or --compare-gas-temperature-k can state explicit assumptions. Without temperature and neutral source fields, neutrals are omitted with reasons. Source EOS/mass fractions are checked when input files are present.
- Potential: native nodal potential, V, including its sign.
- T_e: nodal log_energy and log_ne -> (2/3) exp(log_energy-log_ne), eV.
- Power: native Exodus global P_rf_scaled_W_t6, W, by default. This is the run's globally stored RF scaled-power integral, not the requested 400 W target. The only currently audited alternative --power-field is P_rf_raw_W_t6; other names are not automatically trusted as W-valued power fields. Do not substitute other globals if the requested field is absent.

## RZ weighting and comparison rules

Axisymmetric plasma volume integration uses dV = 2*pi*r*dA and only the native Exodus plasma block. Elemental values are cell constants and weighted by element volume. Linear nodal values use the exact triangular RZ interpolation integral based on vertices and cell geometry, not an arithmetic mean across nodes.

- Density and potential: weighted plasma volume means, integral(f dV)/integral(dV).
- Electron temperature: electron-number weighted mean, integral(n_e*T_e dV)/integral(n_e dV), reconstructed at native nodes before integration. This is a declared nodal reconstruction convention.
- Power: native global scalar time history (W), not a spatial average.

Run_1 and run_2 are weighted **independently** on their own native geometry and time grid. Comparison uses the same semantic quantity/unit and the same explicitly named global power source; it does not imply that two different plasma regions are geometrically equivalent. Time-alignment or error differences would require a separately declared alignment and geometric-compatibility contract.

## Evidence

Each plot has an adjacent JSON provenance summary with Exodus and input SHA-256, selected source fields and transformations, independent run time grids, geometry and plasma volume, weights, temperature source, global power field, units, layout, omitted quantities, and native value ranges. Status remains NOT_EVALUATED (SCIENCE_HOLD) irrespective of CI or successful rendering.
