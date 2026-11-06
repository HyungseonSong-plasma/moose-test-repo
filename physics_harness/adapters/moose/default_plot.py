"""Read-only, source-faithful default plotting of MOOSE Exodus nodal fields.

CLI owns argument parsing; this module owns Exodus decoding and plotting. It
never modifies the input, executes a solver, or claims scientific acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Sequence


class DefaultPlotError(ValueError):
    """Invalid plot request or unsupported/incomplete Exodus evidence."""


def layout_rows(n: int, layout: str = "auto") -> tuple[int, ...]:
    """Return row capacities; auto gives 5->(3,2) and 8->(4,4)."""
    if not isinstance(n, int) or n < 1:
        raise DefaultPlotError("at least one field is required")
    if n > 100:
        raise DefaultPlotError("at most 100 fields may be plotted at once")
    value = layout.strip().lower()
    if value == "auto":
        if n <= 3:
            return (n,)
        if n == 4:
            return (2, 2)
        # Prefer balanced, near-rectangular grids with few empty slots.
        candidate = min(
            range(1, n + 1),
            key=lambda cols: (
                abs(cols / math.ceil(n / cols) - 1.6)
                + 0.15 * (cols * math.ceil(n / cols) - n),
                cols * math.ceil(n / cols) - n,
                cols,
            ),
        )
        return tuple(min(candidate, n - start) for start in range(0, n, candidate))
    grid = re.fullmatch(r"(\d+)x(\d+)", value)
    if grid:
        rows, cols = map(int, grid.groups())
        widths = (cols,) * rows if rows and cols else ()
    elif re.fullmatch(r"\d+(?:\s*,\s*\d+)*", value):
        widths = tuple(int(part.strip()) for part in value.split(","))
    else:
        raise DefaultPlotError("layout must be auto, ROWSxCOLS (2x4), or row widths (3,2)")
    if not widths or min(widths) < 1 or sum(widths) < n or sum(widths) > 100:
        raise DefaultPlotError("layout capacity must cover all fields and be between 1 and 100")
    return widths


def _names(char_rows) -> list[str]:
    """Decode Exodus fixed-width char tables without leaking NUL padding."""
    return [b"".join(bytes(ch) for ch in row).decode("utf-8", "replace").strip("\x00 ")
            for row in char_rows]


def input_fields(paths: Sequence[Path]) -> list[str]:
    """Ordered direct children of [Variables], excluding [AuxVariables]."""
    # Use the canonical HIT parser; never invent fields from source strings.
    from physics_harness.adapters.moose.input import MooseInput, MooseInputError

    ordered: dict[str, None] = {}
    for path in paths:
        try:
            doc = MooseInput(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, MooseInputError) as exc:
            raise DefaultPlotError(f"cannot inspect MOOSE input {path}: {exc}") from exc
        for block in sorted(doc.blocks, key=lambda item: item.start):
            parts = block.path.split("/")
            if len(parts) == 2 and parts[0] == "Variables":
                ordered.setdefault(parts[1], None)
    if not ordered:
        raise DefaultPlotError("no primary [Variables] blocks found in supplied --input file(s)")
    return list(ordered)


def _triangles(f, requested_block: str, node_count: int):
    import numpy as np

    if "eb_names" not in f.variables:
        raise DefaultPlotError("missing Exodus element-block names (eb_names)")
    blocks = _names(np.asarray(f.variables["eb_names"][:]).copy())
    if len(blocks) != len(set(blocks)):
        raise DefaultPlotError("duplicate Exodus element-block names")
    block_name = ("plasma" if "plasma" in blocks else "all") if requested_block == "auto" else requested_block
    if block_name != "all" and block_name not in blocks:
        raise DefaultPlotError(f"Exodus block {block_name!r} is absent; available: {blocks}")
    indices = range(len(blocks)) if block_name == "all" else (blocks.index(block_name),)
    tri: list[tuple[int, int, int]] = []
    for index in indices:
        key = f"connect{index+1}"
        if key not in f.variables:
            raise DefaultPlotError(f"missing connectivity for block {blocks[index]!r}: {key}")
        con = np.asarray(f.variables[key][:], dtype=np.int64).copy()
        if con.ndim != 2 or con.shape[0] == 0 or con.shape[1] not in (3, 4):
            raise DefaultPlotError(f"only linear 2D triangular/quadrilateral elements supported: {key}")
        if np.any(con < 1) or np.any(con > node_count):
            raise DefaultPlotError(f"invalid 1-based connectivity in {key}")
        for row in con - 1:
            tri.append(tuple(map(int, row[:3])))
            if len(row) == 4:
                tri.append((int(row[0]), int(row[2]), int(row[3])))
    if not tri:
        raise DefaultPlotError("no 2D elements in selected Exodus block")
    return np.asarray(tri, dtype=np.int64), block_name


def _read_exodus(exodus: Path, requested_block: str, time_index: int | None,
                 time_us: float | None):
    """Read one real time slice only; primary field names come from Exodus."""
    import numpy as np
    from scipy.io import netcdf_file

    try:
        f = netcdf_file(str(exodus), mode="r", mmap=False)
    except (OSError, ValueError, TypeError) as exc:
        raise DefaultPlotError(f"cannot open classic NetCDF Exodus {exodus}: {exc}") from exc
    with f:
        nd = f.dimensions.get("num_dim")
        if nd is not None and int(nd) != 2:
            raise DefaultPlotError(f"default-plot currently supports 2D Exodus; num_dim={nd}")
        if "time_whole" not in f.variables:
            raise DefaultPlotError("missing Exodus time_whole")
        times = np.asarray(f.variables["time_whole"][:], dtype=float).copy()
        if times.ndim != 1 or not len(times) or not np.all(np.isfinite(times)):
            raise DefaultPlotError("invalid or empty Exodus timestep vector")
        if time_us is not None:
            if not math.isfinite(time_us):
                raise DefaultPlotError("requested time must be finite")
            target = time_us * 1e-6
            toler = max(1e-13, abs(target) * 1e-8)
            matches = np.flatnonzero(abs(times - target) <= toler)
            if len(matches) != 1:
                raise DefaultPlotError(f"requested time {time_us} us is not a unique native timestep")
            step = int(matches[0])
        else:
            step = -1 if time_index is None else time_index
            if step < 0:
                step += len(times)
            if not 0 <= step < len(times):
                raise DefaultPlotError(f"time index out of range (0..{len(times)-1})")
        if "coordx" in f.variables and "coordy" in f.variables:
            x = np.asarray(f.variables["coordx"][:], dtype=float).copy()
            y = np.asarray(f.variables["coordy"][:], dtype=float).copy()
        elif "coord" in f.variables:
            c = np.asarray(f.variables["coord"][:], dtype=float).copy()
            if c.ndim != 2 or c.shape[0] != 2:
                raise DefaultPlotError("expected two Exodus spatial coordinate arrays")
            x, y = c[0], c[1]
        else:
            raise DefaultPlotError("missing Exodus coordinates")
        if x.ndim != 1 or y.shape != x.shape or not len(x) or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise DefaultPlotError("invalid 2D coordinates")
        triangles, block = _triangles(f, requested_block, len(x))
        if "name_nod_var" not in f.variables:
            raise DefaultPlotError("missing Exodus nodal variable names")
        available = _names(np.asarray(f.variables["name_nod_var"][:]).copy())
        if len(available) != len(set(available)) or not available or any(not name for name in available):
            raise DefaultPlotError("duplicate or empty native nodal variable names")
        # Read only the selected timestep and the node count required by the mesh.
        values = {}
        for slot, name in enumerate(available, 1):
            key = f"vals_nod_var{slot}"
            if key not in f.variables:
                raise DefaultPlotError(f"Exodus field {name!r} has no {key}")
            var = f.variables[key]
            if len(var.shape) != 2 or var.shape != (len(times), len(x)):
                raise DefaultPlotError(f"Exodus variable {name!r} has invalid nodal dimensions")
            values[name] = np.asarray(var[step, :], dtype=float).copy()
    return x, y, triangles, available, values, float(times[step]), step, len(times), block


def generate_fields(exodus: Path, output: Path, *, inputs: Sequence[Path] = (),
             variables: Sequence[str] = (), layout: str = "auto", block: str = "auto",
             time_index: int | None = None, time_us: float | None = None,
             cmap: str = "hsv", dpi: int = 140, overwrite: bool = False) -> dict:
    """Create a PNG/PDF and JSON provenance manifest; never run MOOSE."""
    import numpy as np

    exodus = Path(exodus).expanduser().resolve(strict=True)
    inputs = tuple(Path(path).expanduser().resolve(strict=True) for path in inputs)
    output = Path(output).expanduser().resolve()
    report = output.with_name(output.name + ".json")
    if output.suffix.lower() not in {".png", ".pdf", ".svg"}:
        raise DefaultPlotError("--output must be .png, .pdf, or .svg")
    if not overwrite and (output.exists() or report.exists()):
        raise DefaultPlotError("output or JSON manifest already exists; use --overwrite explicitly")
    if dpi < 40 or dpi > 600:
        raise DefaultPlotError("--dpi must be between 40 and 600")
    if time_index is not None and time_us is not None:
        raise DefaultPlotError("choose either --time-index or --time-us")

    x, y, triangles, available, values, time_s, step, count, chosen_block = _read_exodus(
        exodus, block, time_index, time_us
    )
    allowed = input_fields(inputs) if inputs else available
    allowed_set = set(allowed)
    present = [name for name in allowed if name in values]
    if variables:
        wanted = [name for entry in variables for name in entry.split(",") if name]
        if len(wanted) != len(set(wanted)):
            raise DefaultPlotError("duplicate --variables entry")
        forbidden = [name for name in wanted if name not in allowed_set]
        if forbidden:
            raise DefaultPlotError(f"requested variables not declared in selected input/Exodus: {forbidden}")
        missing = [name for name in wanted if name not in values]
        if missing:
            raise DefaultPlotError(f"requested variables are absent from Exodus nodal fields: {missing}")
        selected = wanted
    else:
        selected = present
    if not selected:
        raise DefaultPlotError("no primary [Variables] fields found in Exodus; use --variables or verify inputs")
    widths = layout_rows(len(selected), layout)
    selected_nodes = np.unique(triangles.ravel())
    for name in selected:
        if not np.all(np.isfinite(values[name][selected_nodes])):
            raise DefaultPlotError(f"non-finite native values in selected block: {name}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    # Limit colors/norms to nodes actually present in the selected block.
    local_triangles = np.searchsorted(selected_nodes, triangles)
    triangulation = mtri.Triangulation(x[selected_nodes], y[selected_nodes], local_triangles)
    ncols = max(widths)
    nrows = len(widths)
    fig = plt.figure(figsize=(max(5.0, 4.5 * ncols), max(3.7, 3.8 * nrows)), facecolor="white")
    try:
        # Use equal-size centered panels, including ragged rows like [3,2].
        x_margin, y_margin = 0.055, 0.09
        row_pitch = (1 - y_margin - 0.09) / nrows
        panel_pitch = (1 - 2 * x_margin) / ncols
        for index, name in enumerate(selected):
            prior = 0
            row = 0
            for row, width in enumerate(widths):
                if index < prior + width:
                    break
                prior += width
            column = index - prior
            offset = (ncols - widths[row]) / 2.0
            left = x_margin + (offset + column) * panel_pitch
            bottom = 1 - 0.065 - (row + 1) * row_pitch + 0.07 * row_pitch
            ax = fig.add_axes([left + 0.01, bottom, panel_pitch * 0.76, row_pitch * 0.72])
            image = ax.tripcolor(triangulation, values[name][selected_nodes], shading="gouraud", cmap=cmap)
            ax.set_title(name, fontsize=11)
            if chosen_block == "plasma":
                ax.set_xlabel("r [m]")
                ax.set_ylabel("z [m]")
            else:
                ax.set_xlabel("x [m]")
                ax.set_ylabel("y [m]")
            ax.set_aspect("equal", adjustable="box")
            ax.tick_params(labelsize=8)
            fig.colorbar(image, ax=ax, fraction=0.052, pad=0.03)
        fig.suptitle(f"Exodus fields | t={time_s * 1e6:.8g} us | block={chosen_block}", y=0.993, fontsize=12)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=dpi, facecolor="white")
    finally:
        plt.close(fig)

    summary = {
        "status": "EXODUS_VISUALIZATION_ONLY_NOT_SCIENCE_PASS",
        "exodus": str(exodus),
        "exodus_sha256": hashlib.sha256(exodus.read_bytes()).hexdigest(),
        "inputs": [str(p) for p in inputs],
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        "output": str(output), "layout": layout, "row_capacities": list(widths),
        "colormap": cmap,
        "fields": selected, "available_nodal_fields": available,
        "declared_but_unavailable": [name for name in allowed if name not in values],
        "time_index": step, "time_s": time_s, "timepoint_count": count,
        "block": chosen_block, "triangle_count": int(len(triangles)),
        "rendered_mesh_node_count": int(len(selected_nodes)),
        "science_acceptance": "NOT_EVALUATED",
    }
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary




def generate(exodus: Path, output: Path, *, inputs: Sequence[Path] = (),
             variables: Sequence[str] = (), layout: str = "auto", block: str = "auto",
             time_index: int | None = None, time_us: float | None = None,
             cmap: str = "hsv", dpi: int = 140, overwrite: bool = False,
             mode: str = "2d-map", gas_temperature_k: float | None = None,
             compare: Path | None = None, compare_inputs: Sequence[Path] = (),
             compare_gas_temperature_k: float | None = None,
             power_field: str = "P_rf_scaled_W_t6") -> dict:
    """One reusable CLI surface; compare is a time-trace modifier, not a mode."""
    if mode == "2d-map":
        if compare is not None:
            raise DefaultPlotError("--compare requires --mode time-trace")
        from .species_plot import generate_species
        return generate_species(
            exodus, output, inputs=inputs, variables=variables, layout=layout,
            block=block, time_index=time_index, time_us=time_us, cmap=cmap,
            dpi=dpi, overwrite=overwrite, gas_temperature_k=gas_temperature_k,
        )
    if mode == "time-trace":
        if block not in ("auto", "plasma"):
            raise DefaultPlotError("time-trace requires plasma block")
        if time_index is not None or time_us is not None:
            raise DefaultPlotError("--time-index/--time-us apply to 2d-map only")
        from .time_trace import generate_time_trace
        return generate_time_trace(
            exodus, output, inputs=inputs, compare=compare,
            compare_inputs=compare_inputs, variables=variables, layout=layout,
            cmap=cmap, dpi=dpi, overwrite=overwrite,
            gas_temperature_k=gas_temperature_k,
            compare_gas_temperature_k=compare_gas_temperature_k,
            power_field=power_field,
        )
    raise DefaultPlotError("mode must be '2d-map' or 'time-trace'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="physics default-plot",
        description="2d-map species density/potential/electron temperature or weighted time-trace; --compare overlays another run",
    )
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--exodus", type=Path, help="existing native Exodus .e file")
    sources.add_argument("--run", type=Path, help="run directory containing plasma.e, or an Exodus .e path")
    parser.add_argument("--mode", choices=("2d-map", "time-trace"), default="2d-map")
    parser.add_argument("--compare", type=Path, help="second run directory/.e; only with time-trace")
    parser.add_argument("--input", action="append", default=[], type=Path,
                        help="primary MOOSE input .i; repeat for overlay inputs")
    parser.add_argument("--compare-input", action="append", default=[], type=Path,
                        help="second run input .i; repeat for overlays")
    parser.add_argument("--gas-temperature-k", type=float, default=None,
                        help="explicit primary run neutral-gas temperature, if input cannot source it")
    parser.add_argument("--compare-gas-temperature-k", type=float, default=None,
                        help="explicit second run neutral-gas temperature")
    parser.add_argument("--power-field", default="P_rf_scaled_W_t6",
                        help="exact native Exodus global field in W (default: P_rf_scaled_W_t6)")
    parser.add_argument("--output", type=Path, help="PNG/PDF/SVG plot file")
    parser.add_argument("--variables", nargs="+", default=[],
                        help="subset of e-, O2+, O-, O+, O2, O2*, O, O*, potential, T_e, power")
    parser.add_argument("--layout", default="auto", help="auto | 2x4 | 3,2 row capacities")
    parser.add_argument("--block", default="auto", help="auto/plasma for 2D maps and traces")
    when = parser.add_mutually_exclusive_group()
    when.add_argument("--time-index", type=int, default=None, help="2d-map: zero-based timestep (default last)")
    when.add_argument("--time-us", type=float, default=None, help="2d-map: exact native time in microseconds")
    parser.add_argument("--cmap", default="hsv", help="2d-map Matplotlib colormap (default: hsv)")
    parser.add_argument("--dpi", type=int, default=140)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        from .time_trace import _resolve_run
        source = _resolve_run(args.exodus if args.exodus is not None else args.run)
        if args.compare is not None and args.mode != "time-trace":
            raise DefaultPlotError("--compare requires --mode time-trace")
        if args.mode == "2d-map" and (args.compare_input or args.compare_gas_temperature_k is not None):
            raise DefaultPlotError("--compare-input/--compare-gas-temperature-k require time-trace --compare")
        if args.mode == "time-trace" and args.compare is None and (
            args.compare_input or args.compare_gas_temperature_k is not None
        ):
            raise DefaultPlotError("--compare-input/--compare-gas-temperature-k require --compare")
        suffix = "_2d_map" if args.mode == "2d-map" else "_time_trace_compare" \
                 if args.compare is not None else "_time_trace"
        output = args.output or source.with_name(source.stem + suffix + ".png")
        result = generate(
            source, output, inputs=args.input, compare=args.compare,
            compare_inputs=args.compare_input, variables=args.variables,
            layout=args.layout, block=args.block,
            time_index=args.time_index, time_us=args.time_us,
            cmap=args.cmap, dpi=args.dpi, overwrite=args.overwrite,
            mode=args.mode, gas_temperature_k=args.gas_temperature_k,
            compare_gas_temperature_k=args.compare_gas_temperature_k,
            power_field=args.power_field,
        )
    except (DefaultPlotError, OSError, ValueError, ImportError, KeyError) as exc:
        print(f"DEFAULT_PLOT: HOLD ({exc})")
        return 2
    print(f"DEFAULT_PLOT: PASS mode={args.mode} compared={bool(args.compare)} fields={len(result['fields'])} layout={result['row_capacities']}")
    print(f"IMAGE={result['output']}")
    print(f"MANIFEST={result['output']}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
