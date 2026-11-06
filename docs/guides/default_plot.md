# Physics default-plot — native Exodus field visualization

**Canonical CLI:** `python3 bin/physics.py default-plot`

The command is a **read-only observational helper**, not a solver, a MOOSE input generator, or a scientific acceptance test. It renders *native nodal fields* from an existing **2D classic NetCDF Exodus** file, using one colorbar per field and an automatically chosen, centered panel layout. The plot and JSON summary preserve source identity and native time selection.

## Minimal invocation

```bash
python3 bin/physics.py default-plot \
  --exodus results/plasma.e \
  --output figures/default_fields.png
```

Defaults: **last stored native timestep**, `--layout auto`, Exodus nodal variables in file order, **plasma element block** when present (otherwise all element blocks), PNG output named `<exodus stem>_default_plot.png` if no `--output` is supplied.

To show only primary fields declared by a MOOSE input rather than every Exodus nodal output, supply one or more `--input` arguments. This uses the canonical HIT parser to select direct children of `[Variables]`, **not** `[AuxVariables]`; only declarations that actually occur in the Exodus data are plotted. If no `--input` is given, all Exodus nodal fields are candidate variables.

```bash
python3 bin/physics.py default-plot \
  --exodus results/plasma.e \
  --input input/base.i \
  --input input/rf_parent_overlay.i \
  --time-us 100 \
  --output figures/primary_100us.png
```

## User-controlled layout, variable order, and time

```bash
# Default auto layout: five fields -> first row 3, second row 2.
python3 bin/physics.py default-plot --exodus results/plasma.e \
  --variables a b c d e --layout auto --output figures/five.png

# A deliberately ragged layout with five plots.
python3 bin/physics.py default-plot --exodus results/plasma.e \
  --variables a b c d e --layout 3,2 --output figures/three_plus_two.svg

# Explicit two rows and four columns, with unused cells left empty if needed.
python3 bin/physics.py default-plot --exodus results/plasma.e \
  --variables a b c d e f g h --layout 2x4 --output figures/eight.pdf

# Reorder a subset, select a native time, override block/color map.
python3 bin/physics.py default-plot --exodus results/plasma.e \
  --variables log_energy log_ne --time-index 100 \
  --block plasma --cmap plasma --output figures/t100.png
```

Layout forms:

- `auto` — balanced rows, five fields `(3,2)`, eight `(4,4)`, twelve `(4,4,4)`; incomplete last row is centered.
- `ROWSxCOLS`, e.g. `2x4` — regular grid; unfilled slots are intentionally blank.
- Comma-separated **row capacities**, e.g. `3,2`, `4,4,2` — equal-sized centered panels.

**Colormap:** the default is Matplotlib `hsv` (also the Python API default). Override it with `--cmap plasma`, `--cmap viridis`, `--cmap inferno`, or any other Matplotlib-registered colormap name. The requested colormap is recorded in the JSON sidecar.

The layout must have enough slots for the selected fields; there is a 100-panel safety limit. `--variables` can be comma-separated or space-separated, and its order is preserved. `--time-us` requires an actual, unique native Exodus timestep; it never interpolates. `--time-index -1` selects the last native timestep.

Outputs: PNG, PDF or SVG and adjacent `<image-name>.json` recording source paths/SHA-256, selected names, block, node/triangle count, time index, physical time, layout and unused input declarations. Existing output is never silently replaced; `--overwrite` is required to replace it.

## Requirements and limitations

Install Python `numpy`, `scipy`, and `matplotlib` in the environment running the command. Matplotlib is imported only when an actual image is requested; CLI help remains lightweight. The current reader supports linear 2D triangular and quadrilateral elements encoded in classic NetCDF Exodus, including separated `coordx/coordy` or combined `coord` arrays. Higher-order meshes, 3D Exodus, or NetCDF4/HDF5-only files are not silently reinterpreted; extend the owning decoder if these are needed.

Values are plotted **exactly as written to Exodus**. For example, `log_ne` is plotted as `log_ne` rather than incorrectly labeled as physical `n_e`. Plasma node filtering excludes dielectric-only nodes from the plotted color normalization; no spatial interpolation beyond native triangulated visualization is treated as measured physics.

The sidecar reports `EXODUS_VISUALIZATION_ONLY_NOT_SCIENCE_PASS` and `science_acceptance=NOT_EVALUATED`. Successful plotting does **not** change the scientific status of Issue #457 or any other experiment.
