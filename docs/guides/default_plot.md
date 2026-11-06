# Physics default-plot — source-attributable Exodus densities

**CLI:** python3 bin/physics.py default-plot

The default mode is **Oxygen14 species physical number density (m^-3)**. The command reads an existing native Exodus solution; it never executes a solver or claims scientific acceptance.

## Default: 8 species and auto 2×4 layout

~~~bash
python3 bin/physics.py default-plot \
  --exodus results/plasma.e \
  --input chemistry_off.i \
  --time-us 100 \
  --output figures/species_100us.png
~~~

With the source model identity provided, the default panels are **e-, O2+, O-, O+, O2, O2*, O, O***. Every panel displays density in **m^-3** with an independent logarithmic color scale. The default colormap is **hsv**.

- e-: reconstruct N_A * exp(log_ne) from **plasma nodal** log_ne.
- O2+, O-, O+: reconstruct N_A * exp(log_ni), N_A * exp(log_nm), N_A * exp(log_nop) from **plasma elemental** field values respectively.
- O2, O2*, O, O*: use elemental p, w_O2s, w_O, w_Os and w_O2 = 1 - w_O2s - w_O - w_Os. Apply the source Oxygen14 ideal-gas mixing EOS: Mmix = 1/sum(w_i/M_i), rho = p*Mmix/(8.31446*T_g), n_i = rho*w_i*N_A/M_i. Validated source molar masses: M(O2) = M(O2*) = 0.032 kg/mol, M(O) = M(O*) = 0.016 kg/mol.
- **T_g is not a spatial Exodus field.** Supply the actual MOOSE --input to read literal T_g_fixed and verify the declared EOS/mixture. Alternatively specify --gas-temperature-k (e.g. 300) explicitly when no input file is available. No temperature is silently assumed.

If temperature or elemental neutral state data are unavailable, only the recoverable charged species are plotted; omissions are recorded in the JSON. Selecting an unavailable species explicitly fails. No interpolation of time, no invented field values, and no implicit generic chemistry interpretation.

## Layout, species selection, colormap

~~~bash
# Five species with first row three, second row two:
python3 bin/physics.py default-plot --exodus plasma.e --input chemistry_off.i \
  --variables 'e-' 'O2+' 'O-' 'O2' 'O' --layout 3,2

# Eight species in two rows and four columns:
python3 bin/physics.py default-plot --exodus plasma.e --input chemistry_off.i \
  --layout 2x4 --time-us 50 --cmap viridis --output species_50us.png
~~~

--layout auto chooses 5 → [3,2], 8 → [4,4]; --layout 2x4 is a fixed regular grid. --variables picks the displayed subset/order. --time-us selects a unique native Exodus frame (no interpolation); --time-index selects a zero-based frame (default last). PNG, PDF, SVG outputs supported; --overwrite required to replace existing results.

## Legacy raw nodal field view

~~~bash
# Keep original Exodus nodal-field plotting functionality:
python3 bin/physics.py default-plot --exodus plasma.e --mode fields

# Filter to MOOSE primary [Variables] also present in Exodus:
python3 bin/physics.py default-plot --exodus plasma.e --mode fields \
  --input chemistry_off.i --variables log_ne log_energy potential --cmap plasma
~~~

Raw --mode fields does **not** convert log states; it plots their actual Exodus values. A MOOSE input filters only primary [Variables] in this mode, excluding [AuxVariables].

Exodus also supports **global time-history scalar variables** and other metadata, but those are not 2D spatial fields and are not misleadingly plotted as spatial maps. Separate time-history plotting would be a different mode.

## Provenance

Each plot has an adjacent JSON manifest identifying input/Exodus SHA-256, native frame, block/geometry, nodal-vs-elemental ownership, field conversions, chosen gas temperature and provenance, layout, colormap, density ranges and unavailable-species reasons. Science status remains **NOT_EVALUATED**; this is never a Chemistry-OFF scientific PASS.
