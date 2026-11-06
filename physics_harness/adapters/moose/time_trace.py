"""RZ-volume-weighted native Exodus time traces and like-for-like run overlays.

Source-faithful postprocessing only: it never runs the solver, interpolates a
time grid, assumes a fixed set of present species, or declares science PASS.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

from .default_plot import DefaultPlotError, _names, layout_rows
from .species_plot import (
    LOG_NAMES, SPECIES, NEUTRAL_MASS_FRACTIONS,
    _find_temperature, _number_density_from_log,
    _neutral_number_densities, _validate_oxygen14_neutral_contract,
)

DEFAULT_POWER_FIELD = "P_rf_scaled_W_t6"
OBSERVABLES = (*SPECIES, "potential", "T_e", "power")


def rz_triangle_weights(x, y, connectivity):
    """Exact axisymmetric RZ volume and linear-nodal integral coefficients.

    ∫_triangle 2πr f(r,z) dA = Σ_i f_i [2π A (Σ_j r_j + r_i) / 12]
    when f is linearly interpolated; elemental constants use 2π A mean(r).
    Quadrilaterals are triangulated consistently with the native map decoder.
    """
    import numpy as np

    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    conn = np.asarray(connectivity, dtype=np.int64)
    if x.ndim != 1 or y.shape != x.shape or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise DefaultPlotError("invalid RZ coordinates")
    if np.any(x < -1e-12):
        raise DefaultPlotError("RZ volume weighting requires nonnegative radius")
    if conn.ndim != 2 or conn.shape[0] == 0 or conn.shape[1] not in (3, 4):
        raise DefaultPlotError("RZ weighting requires linear triangular or quadrilateral cells")
    if np.any(conn < 1) or np.any(conn > len(x)):
        raise DefaultPlotError("invalid 1-based Exodus cell connectivity")
    tri = conn[:, :3] - 1
    owners = np.arange(len(conn), dtype=np.int64)
    if conn.shape[1] == 4:
        tri = np.stack([tri, conn[:, [0, 2, 3]] - 1], axis=1).reshape(-1, 3)
        owners = np.repeat(owners, 2)
    rr, zz = x[tri], y[tri]
    area = 0.5 * np.abs(
        (rr[:, 1] - rr[:, 0]) * (zz[:, 2] - zz[:, 0])
        - (rr[:, 2] - rr[:, 0]) * (zz[:, 1] - zz[:, 0])
    )
    if np.any(area <= 0) or not np.all(np.isfinite(area)):
        raise DefaultPlotError("zero-area or invalid plasma cells")
    volume = 2 * math.pi * area * rr.mean(axis=1)
    if np.any(volume <= 0) or not np.all(np.isfinite(volume)):
        raise DefaultPlotError("zero-volume or invalid RZ plasma cells")
    nodal_coeff = 2 * math.pi * area[:, None] * (rr.sum(axis=1, keepdims=True) + rr) / 12.0
    if not np.allclose(nodal_coeff.sum(axis=1), volume, rtol=1e-13, atol=0):
        raise DefaultPlotError("RZ nodal quadrature inconsistent with cell volume")
    return tri, owners, volume, nodal_coeff


def _native_traces(exodus: Path, inputs: Sequence[Path], gas_temperature_k: float | None,
                   power_field: str = DEFAULT_POWER_FIELD) -> dict:
    import numpy as np
    from scipy.io import netcdf_file

    exodus = Path(exodus).expanduser().resolve(strict=True)
    inputs = tuple(Path(path).expanduser().resolve(strict=True) for path in inputs)
    with netcdf_file(str(exodus), mode="r", mmap=False) as f:
        if f.dimensions.get("num_dim") not in (2, None):
            raise DefaultPlotError("time-trace requires a 2D RZ Exodus file")
        if "time_whole" not in f.variables:
            raise DefaultPlotError("missing native Exodus time_whole")
        times = np.asarray(f.variables["time_whole"][:], dtype=float).copy()
        if times.ndim != 1 or not len(times) or not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
            raise DefaultPlotError("native Exodus times must be finite, unique and increasing")
        if "eb_names" not in f.variables:
            raise DefaultPlotError("missing native Exodus element blocks")
        blocks = _names(np.asarray(f.variables["eb_names"][:]).copy())
        if blocks.count("plasma") != 1:
            raise DefaultPlotError("time-trace requires exactly one plasma element block")
        block_id = blocks.index("plasma") + 1
        key = f"connect{block_id}"
        if key not in f.variables:
            raise DefaultPlotError("missing plasma element connectivity")
        if "coordx" in f.variables and "coordy" in f.variables:
            x = np.asarray(f.variables["coordx"][:], dtype=float).copy()
            y = np.asarray(f.variables["coordy"][:], dtype=float).copy()
        elif "coord" in f.variables:
            coord = np.asarray(f.variables["coord"][:], dtype=float).copy()
            if coord.ndim != 2 or coord.shape[0] != 2:
                raise DefaultPlotError("invalid 2D coordinate layout")
            x, y = coord[0], coord[1]
        else:
            raise DefaultPlotError("missing 2D RZ coordinates")
        connectivity = np.asarray(f.variables[key][:], dtype=int).copy()
        triangles, owners, volumes, nodal_coeff = rz_triangle_weights(x, y, connectivity)
        nodes = np.unique(triangles.ravel())
        local_tri = np.searchsorted(nodes, triangles)
        volume = float(volumes.sum())

        def read_nodal(field):
            if "name_nod_var" not in f.variables:
                return None
            names = _names(np.asarray(f.variables["name_nod_var"][:]).copy())
            if names.count(field) > 1:
                raise DefaultPlotError(f"duplicate native nodal name: {field}")
            if field not in names:
                return None
            name = f"vals_nod_var{names.index(field)+1}"
            if name not in f.variables:
                raise DefaultPlotError(f"native nodal {field} has no data")
            var = f.variables[name]
            if var.shape != (len(times), len(x)):
                raise DefaultPlotError(f"native nodal shape mismatch: {field}")
            val = np.asarray(var[:, nodes], dtype=float).copy()
            if not np.all(np.isfinite(val)):
                raise DefaultPlotError(f"nonfinite native plasma nodal values: {field}")
            return val

        elem_names = _names(np.asarray(f.variables["name_elem_var"][:]).copy()) if "name_elem_var" in f.variables else []
        if len(elem_names) != len(set(elem_names)):
            raise DefaultPlotError("duplicate native elemental names")

        def read_elemental(field):
            if field not in elem_names:
                return None
            name = f"vals_elem_var{elem_names.index(field)+1}eb{block_id}"
            if name not in f.variables:
                return None  # exists elsewhere but not on plasma
            var = f.variables[name]
            if var.shape != (len(times), len(connectivity)):
                raise DefaultPlotError(f"native elemental shape mismatch: {field}")
            val = np.asarray(var[:], dtype=float).copy()
            if not np.all(np.isfinite(val)):
                raise DefaultPlotError(f"nonfinite native plasma elemental values: {field}")
            return val

        def nodal_integral(val):
            return np.einsum("tij,ij->t", val[:, local_tri], nodal_coeff, optimize=True)

        def elemental_integral(val):
            return np.einsum("ti,i->t", val[:, owners], volumes, optimize=True)

        series, sources, unavailable = {}, {}, {}
        ne_log = read_nodal("log_ne")
        if ne_log is not None:
            ne = _number_density_from_log(ne_log, "log_ne")
            series["e-"] = nodal_integral(ne) / volume
            sources["e-"] = "nodal log_ne: RZ-volume-weighted N_A exp(log_ne)"
        else:
            unavailable["e-"] = "nodal log_ne absent"
            ne = None

        for label in ("O2+", "O-", "O+"):
            name = LOG_NAMES[label]
            raw = read_elemental(name)
            if raw is not None:
                density = _number_density_from_log(raw, name)
                series[label] = elemental_integral(density) / volume
                sources[label] = f"plasma elemental {name}: RZ-volume-weighted N_A exp({name})"
            else:
                unavailable[label] = f"plasma elemental {name} absent"

        derived_temp, temp_source = _find_temperature(inputs)
        if gas_temperature_k is not None:
            if not math.isfinite(gas_temperature_k) or gas_temperature_k <= 0:
                raise DefaultPlotError("gas-temperature-k must be finite and positive")
            if derived_temp is not None and not math.isclose(derived_temp, gas_temperature_k, rel_tol=1e-12):
                raise DefaultPlotError("explicit gas-temperature-k contradicts MOOSE T_g_fixed")
            temperature, temp_source = gas_temperature_k, "explicit --gas-temperature-k"
        else:
            temperature = derived_temp

        raw = {name: read_elemental(name) for name in ("p", *NEUTRAL_MASS_FRACTIONS.values())}
        if temperature is not None and all(val is not None for val in raw.values()):
            if inputs:
                _validate_oxygen14_neutral_contract(inputs)
            for label, density in _neutral_number_densities(raw, temperature).items():
                series[label] = elemental_integral(density) / volume
                sources[label] = f"plasma elemental p,w: RZ-volume weighted Oxygen14 EOS; {temp_source}"
        else:
            reason = "gas temperature not sourced from MOOSE --input or explicit option" \
                     if temperature is None else "plasma elemental p and mass fractions incomplete"
            for label in ("O2", "O2*", "O", "O*"):
                unavailable[label] = reason

        potential = read_nodal("potential")
        if potential is not None:
            series["potential"] = nodal_integral(potential) / volume
            sources["potential"] = "nodal potential: axisymmetric RZ volume mean"
        else:
            unavailable["potential"] = "nodal potential absent"
        energy_log = read_nodal("log_energy")
        if ne is not None and energy_log is not None:
            with np.errstate(over="ignore", under="ignore", invalid="ignore"):
                te = (2 / 3) * np.exp(energy_log - ne_log)
            if not np.all(np.isfinite(te)) or np.any(te < 0):
                raise DefaultPlotError("invalid derived electron temperature")
            ne_int = nodal_integral(ne)
            if np.any(ne_int <= 0):
                raise DefaultPlotError("nonpositive total electron inventory")
            series["T_e"] = nodal_integral(ne * te) / ne_int
            sources["T_e"] = "nodal T_e=(2/3)exp(log_energy-log_ne), electron-number-weighted RZ mean"
        else:
            unavailable["T_e"] = "nodal log_ne/log_energy absent"

        global_names = _names(np.asarray(f.variables["name_glo_var"][:]).copy()) if "name_glo_var" in f.variables else []
        if len(global_names) != len(set(global_names)):
            raise DefaultPlotError("duplicate native Exodus global variable names")
        if power_field in global_names:
            if "vals_glo_var" not in f.variables:
                raise DefaultPlotError(f"native global power {power_field} missing vals_glo_var")
            var = f.variables["vals_glo_var"]
            if var.shape != (len(times), len(global_names)):
                raise DefaultPlotError("native global power data shape mismatch")
            power = np.asarray(var[:, global_names.index(power_field)], dtype=float).copy()
            if not np.all(np.isfinite(power)):
                raise DefaultPlotError(f"nonfinite native global power {power_field}")
            series["power"] = power
            sources["power"] = f"actual native global {power_field} [W], not target power"
        else:
            unavailable["power"] = f"native global {power_field} absent; no substitute power claim"
    # No Exodus handle remains; all physical traces are explicit numerical arrays.
    if any(len(v) != len(times) or not np.all(np.isfinite(v)) for v in series.values()):
        raise DefaultPlotError("invalid weighted/derived time trace")
    return {
        "exodus": str(exodus), "input_paths": [str(path) for path in inputs],
        "time_us": times * 1e6, "series": series, "sources": sources,
        "unavailable": unavailable, "power_field": power_field,
        "temperature_k": temperature, "temperature_source": temp_source,
        "plasma_volume_m3": volume, "plasma_element_count": len(connectivity),
        "plasma_triangle_count": len(triangles), "plasma_node_count": len(nodes),
        "weighting": {
            "density": "2pi*r dA plasma volume mean; nodal linear interpolation/elemental FV constants",
            "potential": "2pi*r dA plasma nodal volume mean",
            "T_e": "2pi*r dA plasma electron-number-weighted mean from vertex reconstructed n_e*T_e",
            "power": "native Exodus global W time-history, not spatially averaged",
        },
    }


def _resolve_run(source: Path) -> Path:
    path = Path(source).expanduser().resolve(strict=True)
    if path.is_file():
        if path.suffix != ".e":
            raise DefaultPlotError(f"run file is not Exodus .e: {path}")
        return path
    if not path.is_dir():
        raise DefaultPlotError(f"--run must name a directory or native Exodus .e: {path}")
    candidate = path / "plasma.e"
    if candidate.is_file():
        return candidate
    candidates = sorted(path.glob("*.e"))
    if len(candidates) != 1:
        raise DefaultPlotError(f"run directory needs plasma.e or exactly one .e file; found {len(candidates)}: {path}")
    return candidates[0]


def generate_time_trace(run: Path, output: Path, *, inputs: Sequence[Path] = (),
                        compare: Path | None = None, compare_inputs: Sequence[Path] = (),
                        variables: Sequence[str] = (), layout: str = "auto", cmap: str = "hsv",
                        dpi: int = 140, overwrite: bool = False,
                        gas_temperature_k: float | None = None,
                        compare_gas_temperature_k: float | None = None,
                        power_field: str = DEFAULT_POWER_FIELD) -> dict:
    """Plot one or two run-native time grids with comparable scalar observables."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(output).expanduser().resolve()
    report = output.with_name(output.name + ".json")
    if output.suffix.lower() not in {".png", ".pdf", ".svg"}:
        raise DefaultPlotError("--output must end in .png, .pdf or .svg")
    if not overwrite and (output.exists() or report.exists()):
        raise DefaultPlotError("output or manifest exists; use --overwrite")
    if dpi < 40 or dpi > 600:
        raise DefaultPlotError("--dpi must be between 40 and 600")
    first_exodus = _resolve_run(run)
    first = _native_traces(first_exodus, inputs, gas_temperature_k, power_field=power_field)
    runs = [first]
    if compare is not None:
        second_exodus = _resolve_run(compare)
        if second_exodus == first_exodus:
            raise DefaultPlotError("cannot compare a run to itself")
        runs.append(_native_traces(second_exodus, compare_inputs, compare_gas_temperature_k, power_field=power_field))

    requested = [x.strip() for group in variables for x in group.split(",") if x.strip()]
    if len(requested) != len(set(requested)):
        raise DefaultPlotError("duplicate requested time-trace observables")
    if any(x not in OBSERVABLES for x in requested):
        raise DefaultPlotError(f"unsupported time-trace observable: {requested}")
    common = set.intersection(*(set(r["series"]) for r in runs))
    selected = requested if requested else [name for name in OBSERVABLES if name in common]
    absent = {name: [r["unavailable"].get(name, "not recovered") for r in runs]
              for name in selected if name not in common}
    if absent:
        raise DefaultPlotError(f"requested quantities not available in every run: {absent}")
    if not selected:
        raise DefaultPlotError("no comparable native time-trace quantities")
    widths = layout_rows(len(selected), layout)
    nrows, ncols = len(widths), max(widths)
    fig = plt.figure(figsize=(max(5, 4.6*ncols), max(4, 3.7*nrows)), facecolor="white")
    ranges = {}
    try:
        margin = .055
        row_pitch = .84 / nrows
        panel_pitch = .89 / ncols
        for k, name in enumerate(selected):
            past = 0
            for row, cap in enumerate(widths):
                if k < past + cap:
                    break
                past += cap
            col_offset = (ncols - widths[row]) / 2
            left = margin + (col_offset + k - past) * panel_pitch
            bottom = .92 - (row + 1) * row_pitch + .14 * row_pitch
            ax = fig.add_axes([left + .012, bottom, panel_pitch*.78, row_pitch*.70])
            yunit = "m$^{-3}$" if name in SPECIES else "V" if name == "potential" \
                    else "eV" if name == "T_e" else "W"
            minima, maxima = [], []
            for idx, one in enumerate(runs):
                y = np.asarray(one["series"][name], dtype=float)
                t = np.asarray(one["time_us"], dtype=float)
                if name in SPECIES:
                    # Nonpositive samples cannot be displayed on logarithmic axes.
                    yplot = np.where(y > 0, y, np.nan)
                    if not np.any(np.isfinite(yplot)):
                        raise DefaultPlotError(f"all nonpositive species trace: {name} in run {idx+1}")
                    ax.semilogy(t, yplot, label=f"run_{idx+1}", linewidth=1.65)
                else:
                    ax.plot(t, y, label=f"run_{idx+1}", linewidth=1.65)
                minima.append(float(np.min(y)))
                maxima.append(float(np.max(y)))
            ax.set_title(f"{name} [{yunit}]", fontsize=10)
            ax.set_xlabel("Time [µs]", fontsize=9)
            ax.grid(True, alpha=.25, which="both")
            ax.tick_params(labelsize=7)
            if len(runs) > 1:
                ax.legend(fontsize=8)
            ranges[name] = {"minimum": min(minima), "maximum": max(maxima),
                            "units": "m^-3" if name in SPECIES else "V" if name == "potential"
                                     else "eV" if name == "T_e" else "W"}
        fig.suptitle("RZ-weighted time traces" + (" | run_1 vs run_2" if len(runs) > 1 else ""),
                     y=.995, fontsize=12)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=dpi, facecolor="white")
    finally:
        plt.close(fig)

    summary = {
        "status": "NATIVE_EXODUS_WEIGHTED_TRACES_NOT_SCIENCE_PASS",
        "mode": "time-trace", "compare": len(runs) > 1,
        "fields": selected, "units": {s: ranges[s]["units"] for s in selected},
        "field_ranges": ranges, "layout": layout, "row_capacities": list(widths),
        "colormap": cmap, "output": str(output), "power_field": power_field,
        "axis": "run-native time_us; no interpolation or automatic alignment",
        "runs": [
            {
                "id": f"run_{i+1}", "exodus": one["exodus"],
                "exodus_sha256": hashlib.sha256(Path(one["exodus"]).read_bytes()).hexdigest(),
                "inputs": one["input_paths"],
                "input_sha256": {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                 for p in one["input_paths"]},
                "native_time_us": [float(t) for t in one["time_us"]],
                "timepoint_count": len(one["time_us"]),
                "available": sorted(one["series"]),
                "unavailable": one["unavailable"], "sources": one["sources"],
                "weighting": one["weighting"], "plasma_volume_m3": one["plasma_volume_m3"],
                "plasma_node_count": one["plasma_node_count"],
                "plasma_element_count": one["plasma_element_count"],
                "temperature_k": one["temperature_k"],
                "temperature_source": one["temperature_source"],
            }
            for i, one in enumerate(runs)
        ],
        "science_acceptance": "NOT_EVALUATED",
    }
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
