"""Oxygen14 source-attributable physical species-density plots from native Exodus.

This is an observational reconstruction of *already-solved* fields: nodal
log-ne, elemental log-ion densities, pressure and neutral mass fractions.
No chemistry, state solving, or scientific-acceptance judgment occurs here.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Sequence

from .default_plot import DefaultPlotError, _names, _read_exodus, layout_rows

N_A = 6.02214076e23
GAS_R = 8.31446
SPECIES = ("e-", "O2+", "O-", "O+", "O2", "O2*", "O", "O*")
LOG_NAMES = {"e-": "log_ne", "O2+": "log_ni", "O-": "log_nm", "O+": "log_nop"}
NEUTRAL_MASSES_KG_PER_MOL = {"O2": 0.032, "O2*": 0.032, "O": 0.016, "O*": 0.016}
NEUTRAL_MASS_FRACTIONS = {"O2*": "w_O2s", "O": "w_O", "O*": "w_Os"}


def _find_temperature(inputs: Sequence[Path]) -> tuple[float | None, str | None]:
    """Read T_g_fixed only from an explicit, uniquely owned MOOSE constant block."""
    if not inputs:
        return None, None
    from .input import MooseInput, MooseInputError

    found = []
    for path in inputs:
        try:
            doc = MooseInput(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, MooseInputError) as exc:
            raise DefaultPlotError(f"cannot inspect MOOSE input {path}: {exc}") from exc
        for span in doc.blocks:
            if not span.path.startswith("FunctorMaterials/") or span.path.count("/") != 1:
                continue
            text = doc.text[span.start:span.end]
            mnames = re.search(r"(?m)^\s*prop_names\s*=\s*'([^']+)'\s*(?:#.*)?$", text)
            mvalues = re.search(r"(?m)^\s*prop_values\s*=\s*'([^']+)'\s*(?:#.*)?$", text)
            if not mnames or not mvalues:
                continue
            names, values = mnames.group(1).split(), mvalues.group(1).split()
            if "T_g_fixed" not in names:
                continue
            if len(names) != len(values) or names.count("T_g_fixed") != 1:
                raise DefaultPlotError("ambiguous T_g_fixed constant declaration")
            try:
                temperature = float(values[names.index("T_g_fixed")])
            except ValueError as exc:
                raise DefaultPlotError("non-literal T_g_fixed must be passed via --gas-temperature-k") from exc
            found.append((temperature, f"{path}: {span.path}"))
    if not found:
        return None, None
    if len(found) != 1:
        raise DefaultPlotError("multiple T_g_fixed constants across MOOSE inputs")
    return found[0]


def _validate_oxygen14_neutral_contract(inputs: Sequence[Path]) -> None:
    """Prevent generic/altered chemistry models from inheriting wrong molar masses."""
    from .input import MooseInput

    expected_molar = "1.0/(m0/0.032+m1/0.032+m2/0.016+m3/0.016)"
    expected_names = "w_O2_constraint w_O2s w_O w_Os"
    expected_eos = "prs*mol/(8.31446*tmp)"
    found_molar, found_eos = [], []
    for path in inputs:
        doc = MooseInput(path.read_text(encoding="utf-8"))
        for block in doc.blocks:
            if block.path not in {"FunctorMaterials/neutral_mean_molar_mass", "FunctorMaterials/neutral_density"}:
                continue
            lines = doc.text[block.start:block.end].splitlines()
            params = {}
            for line in lines:
                m = re.match(r"\s*([A-Za-z_]+)\s*=\s*(.*?)\s*(?:#.*)?$", line)
                if m:
                    params[m.group(1)] = m.group(2).strip().strip("'\"")
            if block.path.endswith("neutral_mean_molar_mass"):
                found_molar.append((params.get("expression", "").replace(" ", ""),
                                    params.get("functor_names", "")))
            else:
                found_eos.append(params.get("expression", "").replace(" ", ""))
    if found_molar != [(expected_molar, expected_names)] or found_eos != [expected_eos]:
        raise DefaultPlotError(
            "neutral physical-density reconstruction requires the explicit Oxygen14 "
            "molar-mass and ideal-gas EOS source contract"
        )


def _native_species(exodus: Path, block: str, time_index: int | None,
                    time_us: float | None, inputs: Sequence[Path],
                    gas_temperature_k: float | None):
    import numpy as np
    from scipy.io import netcdf_file

    x, y, triangles, nodal_names, nodal_values, time_s, step, count, chosen_block = _read_exodus(
        exodus, block, time_index, time_us
    )
    if chosen_block != "plasma":
        raise DefaultPlotError("Oxygen14 species density requires the 'plasma' Exodus element block")
    with netcdf_file(str(exodus), mode="r", mmap=False) as f:
        block_names = _names(np.asarray(f.variables["eb_names"][:]).copy())
        block_index = block_names.index("plasma") + 1
        connectivity = np.asarray(f.variables[f"connect{block_index}"][:], dtype=int).copy()
        if connectivity.ndim != 2 or connectivity.shape[1] not in (3, 4):
            raise DefaultPlotError("plasma block must be linear 2D triangles or quadrilaterals")
        if "name_elem_var" not in f.variables:
            element_names = []
        else:
            element_names = _names(np.asarray(f.variables["name_elem_var"][:]).copy())
        if len(element_names) != len(set(element_names)):
            raise DefaultPlotError("duplicate Exodus elemental variable names")

        def cell_field(name):
            if name not in element_names:
                return None
            slot = element_names.index(name) + 1
            key = f"vals_elem_var{slot}eb{block_index}"
            if key not in f.variables:
                return None
            arr = np.asarray(f.variables[key][step, :], dtype=float).copy()
            if arr.shape != (len(connectivity),):
                raise DefaultPlotError(f"wrong plasma elemental field shape for {name}")
            if not np.all(np.isfinite(arr)):
                raise DefaultPlotError(f"nonfinite source field: {name}")
            return arr

        raw = {name: cell_field(name) for name in (*LOG_NAMES.values(), "p", *NEUTRAL_MASS_FRACTIONS.values())
               if name != "log_ne"}

    owners = np.repeat(np.arange(len(connectivity)), 1 if connectivity.shape[1] == 3 else 2)
    if len(owners) != len(triangles):
        raise DefaultPlotError("plasma triangle-to-element mapping mismatch")
    positive_density = {}
    failures = {}
    sources = {}
    if "log_ne" in nodal_values:
        nodes = np.unique(triangles.ravel())
        ln = np.asarray(nodal_values["log_ne"], dtype=float)
        if not np.all(np.isfinite(ln[nodes])):
            raise DefaultPlotError("nonfinite plasma log_ne values")
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            density = N_A * np.exp(ln)
        positive_density["e-"] = ("nodal", density)
        sources["e-"] = "native nodal log_ne: N_A*exp(log_ne)"
    else:
        failures["e-"] = "nodal log_ne absent"
    for species in ("O2+", "O-", "O+"):
        field = LOG_NAMES[species]
        if raw.get(field) is None:
            failures[species] = f"elemental {field} absent in plasma block"
            continue
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            density = N_A * np.exp(raw[field])
        positive_density[species] = ("elemental", density)
        sources[species] = f"native elemental {field}: N_A*exp({field})"

    derived_temp, temp_source = _find_temperature(inputs)
    if gas_temperature_k is not None:
        if not math.isfinite(gas_temperature_k) or gas_temperature_k <= 0:
            raise DefaultPlotError("--gas-temperature-k must be finite and positive")
        if derived_temp is not None and not math.isclose(derived_temp, gas_temperature_k, rel_tol=1e-12):
            raise DefaultPlotError("--gas-temperature-k contradicts MOOSE T_g_fixed")
        temperature, temp_source = gas_temperature_k, "explicit --gas-temperature-k"
    else:
        temperature = derived_temp
    neutrals_ready = (
        temperature is not None
        and all(raw.get(field) is not None for field in ("p", *NEUTRAL_MASS_FRACTIONS.values()))
    )
    if neutrals_ready:
        if inputs:
            _validate_oxygen14_neutral_contract(inputs)
        elif gas_temperature_k is None:
            raise DefaultPlotError("neutral reconstruction requires MOOSE --input or explicit temperature")
        pressure = raw["p"]
        if np.any(pressure <= 0):
            raise DefaultPlotError("pressure must be strictly positive for neutral number density")
        w = {"O2*": raw["w_O2s"], "O": raw["w_O"], "O*": raw["w_Os"]}
        w["O2"] = 1.0 - w["O2*"] - w["O"] - w["O*"]
        if any(np.any(frac < -1e-12) or np.any(frac > 1 + 1e-12) for frac in w.values()):
            raise DefaultPlotError("invalid neutral mass fraction; cannot derive densities")
        w = {s: np.clip(a, 0.0, 1.0) for s, a in w.items()}
        mix_inverse_mass = sum(w[s] / NEUTRAL_MASSES_KG_PER_MOL[s] for s in w)
        if np.any(mix_inverse_mass <= 0):
            raise DefaultPlotError("invalid neutral mean molar mass")
        total_neutral_density = pressure * N_A / (GAS_R * temperature)
        for species in ("O2", "O2*", "O", "O*"):
            density = total_neutral_density * (w[species] / NEUTRAL_MASSES_KG_PER_MOL[species]) / mix_inverse_mass
            positive_density[species] = ("elemental", density)
            sources[species] = "elemental p,w + Oxygen14 ideal-gas mixture EOS; " + str(temp_source)
    else:
        why = "missing T_g_fixed; pass --input INPUT.i or --gas-temperature-k 300" if temperature is None \
              else "missing elemental pressure or neutral mass fractions"
        for s in ("O2", "O2*", "O", "O*"):
            failures[s] = why
    for species, (kind, data) in positive_density.items():
        valid = data[np.unique(triangles.ravel())] if kind == "nodal" else data
        if not np.all(np.isfinite(valid)) or np.any(valid < 0):
            raise DefaultPlotError(f"nonfinite or negative reconstructed density: {species}")
    return {
        "x": x, "y": y, "triangles": triangles, "owners": owners,
        "species": positive_density, "sources": sources, "unavailable": failures,
        "time_s": time_s, "time_index": step, "time_count": count,
        "temperature_k": temperature, "temperature_source": temp_source,
        "elemental_field_names": element_names, "nodal_field_names": nodal_names,
    }


def generate_species(exodus: Path, output: Path, *, inputs: Sequence[Path] = (),
                     variables: Sequence[str] = (), layout: str = "auto", block: str = "auto",
                     time_index: int | None = None, time_us: float | None = None,
                     gas_temperature_k: float | None = None, cmap: str = "hsv",
                     dpi: int = 140, overwrite: bool = False) -> dict:
    """Render available species densities in m^-3; exact source/provenance recorded."""
    import numpy as np
    from matplotlib.colors import LogNorm
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    exodus = Path(exodus).expanduser().resolve(strict=True)
    inputs = tuple(Path(p).expanduser().resolve(strict=True) for p in inputs)
    output = Path(output).expanduser().resolve()
    report = output.with_name(output.name + ".json")
    if output.suffix.lower() not in {".png", ".pdf", ".svg"}:
        raise DefaultPlotError("--output must be .png, .pdf, or .svg")
    if not overwrite and (output.exists() or report.exists()):
        raise DefaultPlotError("output or JSON manifest already exists; use --overwrite")
    if dpi < 40 or dpi > 600:
        raise DefaultPlotError("--dpi must be between 40 and 600")
    if time_index is not None and time_us is not None:
        raise DefaultPlotError("choose either --time-index or --time-us")
    if block not in {"auto", "plasma"}:
        raise DefaultPlotError("species-density plotting requires plasma block; use --mode fields for other blocks")

    data = _native_species(exodus, block, time_index, time_us, inputs, gas_temperature_k)
    requested = [name.strip() for entry in variables for name in entry.split(",") if name.strip()]
    if len(requested) != len(set(requested)):
        raise DefaultPlotError("duplicate species in --variables")
    if any(s not in SPECIES for s in requested):
        raise DefaultPlotError(f"unknown Oxygen14 species {requested}; choose from {SPECIES}")
    if requested and any(s not in data["species"] for s in requested):
        missing = {s: data["unavailable"].get(s, "not reconstructed") for s in requested if s not in data["species"]}
        raise DefaultPlotError(f"requested species unavailable: {missing}")
    selected = requested or [s for s in SPECIES if s in data["species"]]
    if not selected:
        raise DefaultPlotError("no recoverable species density from native Exodus")
    widths = layout_rows(len(selected), layout)
    tri = data["triangles"]
    nodes = np.unique(tri.ravel())
    triangulation = mtri.Triangulation(data["x"][nodes], data["y"][nodes], np.searchsorted(nodes, tri))
    ncols, nrows = max(widths), len(widths)
    fig = plt.figure(figsize=(max(5, 4.6 * ncols), max(4, 4.0 * nrows)), facecolor="white")
    ranges = {}
    try:
        x_margin, y_margin = 0.055, 0.09
        row_pitch = (1 - y_margin - 0.09) / nrows
        panel_pitch = (1 - 2 * x_margin) / ncols
        for i, s in enumerate(selected):
            row, past = 0, 0
            for row, width in enumerate(widths):
                if i < past + width:
                    break
                past += width
            left = x_margin + ((ncols-widths[row])/2 + i-past)*panel_pitch
            bottom = 1 - 0.065 - (row+1)*row_pitch + 0.07*row_pitch
            ax = fig.add_axes([left + 0.01, bottom, panel_pitch*0.76, row_pitch*0.72])
            kind, val = data["species"][s]
            v = val[nodes] if kind == "nodal" else val
            valid = v[np.isfinite(v)]
            positive = valid[valid > 0]
            if not len(positive):
                raise DefaultPlotError(f"cannot log-plot all-zero species: {s}; use explicit zero-aware renderer")
            lo, hi = float(positive.min()), float(positive.max())
            # Nearly constant densities should not exaggerate roundoff as spatial structure.
            norm_lo, norm_hi = (lo/10, hi*10) if hi/lo < 1 + 1e-10 else (lo, hi)
            norm = LogNorm(vmin=norm_lo, vmax=norm_hi, clip=True)
            draw = np.maximum(v, norm_lo)
            if kind == "nodal":
                img = ax.tripcolor(triangulation, draw, cmap=cmap, norm=norm, shading="gouraud")
            else:
                # Element variables: native cell values (no fabricated nodal interpolation).
                img = ax.tripcolor(triangulation, facecolors=draw[data["owners"]],
                                   shading="flat", cmap=cmap, norm=norm)
            ax.set_title(f"{s} | n [m$^{{-3}}$]", fontsize=10)
            ax.set_xlabel("r [m]", fontsize=9)
            ax.set_ylabel("z [m]", fontsize=9)
            ax.set_aspect("equal", adjustable="box")
            ax.tick_params(labelsize=7)
            fig.colorbar(img, ax=ax, fraction=0.046, pad=0.03)
            ranges[s] = {"min_m3": float(valid.min()), "max_m3": float(valid.max()),
                         "value_location": kind, "log10_color_scale": True,
                         "log_color_floor_m3": norm_lo, "zero_values_clipped_for_display": int(np.count_nonzero(v == 0))}
        fig.suptitle(f"Oxygen14 species densities | t={data['time_s']*1e6:.8g} us | plasma | cmap={cmap}",
                     fontsize=12, y=0.993)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=dpi, facecolor="white")
    finally:
        plt.close(fig)
    summary = {
        "status": "EXODUS_DERIVED_SPECIES_DENSITIES_NOT_SCIENCE_PASS",
        "mode": "species", "species_profile": "Oxygen14_charge_and_neutral",
        "exodus": str(exodus), "exodus_sha256": hashlib.sha256(exodus.read_bytes()).hexdigest(),
        "inputs": [str(p) for p in inputs],
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        "output": str(output), "colormap": cmap, "layout": layout, "row_capacities": list(widths),
        "fields": selected, "available_species": [s for s in SPECIES if s in data["species"]],
        "unavailable_species": data["unavailable"], "field_sources": data["sources"],
        "time_index": data["time_index"], "time_s": data["time_s"],
        "timepoint_count": data["time_count"], "block": "plasma",
        "triangle_count": int(len(tri)), "plasma_node_count": int(len(nodes)),
        "temperature_k": data["temperature_k"],
        "temperature_source": data["temperature_source"],
        "units": "m^-3", "species_density_ranges": ranges,
        "science_acceptance": "NOT_EVALUATED",
    }
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
