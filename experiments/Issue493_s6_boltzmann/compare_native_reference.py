#!/usr/bin/env python3
"""Read-only per-run electron-density reference overlays from verified Issue493 public Exodus.

The reference is versioned as two public CSVs in this repository.
This diagnostic makes no science-acceptance or B/C parity claim.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

NA = 6.02214076e23

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def load_reference(path: Path, coordinate: str) -> tuple[list[float], list[float]]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 3 or any(coordinate not in row or "n_e_m^-3" not in row for row in rows):
        raise ValueError("REFERENCE_REFERENCE_SCHEMA_MISMATCH")
    x = [float(row[coordinate]) for row in rows]
    y = [float(row["n_e_m^-3"]) for row in rows]
    if (not all(math.isfinite(v) for v in x + y)
            or any(v < 0 for v in y)
            or any(b <= a for a, b in zip(x, x[1:]))):
        raise ValueError("REFERENCE_REFERENCE_NONFINITE_OR_UNORDERED")
    return x, y

def plasma_slice(exodus: Path, vertical: list[float], horizontal: list[float],
                 time_us: float) -> tuple[list[float], list[float], float, float, tuple[list[float], list[float]]]:
    import numpy as np
    import matplotlib.tri as mtri
    from scipy.io import netcdf_file

    with netcdf_file(exodus, "r", mmap=False) as data:
        times = np.asarray(data.variables["time_whole"][:], dtype=float)
        if not len(times) or not np.isfinite(times).all():
            raise ValueError("NATIVE_TIMESTAMPS_INVALID")
        idx = int(np.argmin(np.abs(times * 1e6 - time_us)))
        if abs(times[idx] * 1e6 - time_us) > 0.001:
            raise ValueError("NATIVE_EXACT_TIME_UNAVAILABLE")
        nodal_names = [b"".join(row).decode("ascii", "ignore").strip("\x00 ")
                       for row in data.variables["name_nod_var"][:]]
        # Canonical ContinuityEq outputs log_e. Historical pinned S6 Exodus
        # records log_ne; detect it by actual on-disk field name, never by a
        # runtime legacy naming switch. Ambiguous files are rejected.
        electron_fields = [name for name in ("log_e", "log_ne") if name in nodal_names]
        if len(electron_fields) != 1:
            raise ValueError("NATIVE_ELECTRON_STATE_AMBIGUOUS" if electron_fields
                             else "NATIVE_ELECTRON_STATE_MISSING")
        electron_field = electron_fields[0]
        if nodal_names.count(electron_field) != 1:
            raise ValueError("NATIVE_ELECTRON_STATE_DUPLICATED")
        variable = f"vals_nod_var{nodal_names.index(electron_field) + 1}"
        electron_log = np.asarray(data.variables[variable][idx, :], dtype=float)
        x = np.asarray(data.variables["coordx"][:], dtype=float) * 100.0
        z = np.asarray(data.variables["coordy"][:], dtype=float) * 100.0
        blocks = [b"".join(row).decode("ascii", "ignore").strip("\x00 ")
                  for row in data.variables["eb_names"][:]]
        if "plasma" not in blocks:
            raise ValueError("NATIVE_PLASMA_BLOCK_MISSING")
        connect = f"connect{blocks.index('plasma') + 1}"
        triangles = np.asarray(data.variables[connect][:], dtype=int) - 1
        if triangles.ndim != 2 or triangles.shape[1] != 3:
            raise ValueError("NATIVE_PLASMA_TRIANGLE_MESH_REQUIRED")
        nodes = np.unique(triangles)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            ne = NA * np.exp(electron_log)
        if not np.isfinite(ne[nodes]).all() or np.any(ne[nodes] < 0):
            raise ValueError("NATIVE_LOG_NE_INVALID")
        interpolator = mtri.LinearTriInterpolator(mtri.Triangulation(x, z, triangles), ne)
        vv = np.ma.filled(interpolator(np.zeros(len(vertical)), vertical), np.nan)
        rr = np.ma.filled(interpolator(horizontal, np.full(len(horizontal), 23.0)), np.nan)
        # Preserve the original plasma-mesh axis nodes for the vertical PNG.
        # These samples are not interpolated to the Reference coordinates.
        axis_nodes = nodes[np.isclose(x[nodes], 0.0, atol=1e-10, rtol=0.0)]
        axis_nodes = axis_nodes[np.argsort(z[axis_nodes])]
        if len(axis_nodes) < 2 or np.any(np.diff(z[axis_nodes]) <= 0):
            raise ValueError("NATIVE_AXIS_NODES_INVALID")
        raw_vertical = (z[axis_nodes].tolist(), ne[axis_nodes].tolist())
        return (vv.tolist(), rr.tolist(), float(np.max(ne[nodes])),
                float(times[idx] * 1e6), raw_vertical)

def evaluate(reference: list[float], native: list[float], cutoff: float = 1e15) -> dict:
    pairs = [(h, n) for h, n in zip(reference, native) if h > cutoff and math.isfinite(n)]
    if len(pairs) < 3:
        raise ValueError("INSUFFICIENT_COMMON_PLASMA_SUPPORT")
    h = [pair[0] for pair in pairs]
    n = [pair[1] for pair in pairs]
    rmse = math.sqrt(sum((a - b) ** 2 for a, b in pairs) / len(pairs))
    peak_h, peak_n = max(h), max(n)
    return {
        "common_support_points": len(pairs),
        "absolute_rmse_m_minus3": rmse,
        "rmse_over_reference_peak": rmse / max(reference),
        "relative_l2": math.sqrt(sum((a - b) ** 2 for a, b in pairs) / sum(a * a for a in h)),
        "normalized_shape_rmse": math.sqrt(sum((a / peak_h - b / peak_n) ** 2
                                            for a, b in pairs) / len(pairs)),
    }

def plot_profile(reference_x: list[float], reference: list[float],
                 native_x: list[float], native: list[float], *,
                 axis: str, case: str, time_us: float, output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    if len(reference_x) != len(reference) or len(native_x) != len(native):
        raise ValueError("PLOT_PROFILE_COORDINATE_VALUE_MISMATCH")
    h, n = np.asarray(reference) / 1e16, np.asarray(native) / 1e16
    raw_vertical = axis == "vertical"
    fig, ax = plt.subplots(figsize=(8.5, 5.1))
    ax.plot(reference_x, h, label="Reference (timestamp unknown)", lw=2.0,
            marker="o" if raw_vertical else None, markersize=3.5)
    ax.plot(native_x, n,
            label=(f"Native {case} at {time_us:g} us (raw r=0 nodes)"
                   if raw_vertical else f"Native {case} at {time_us:g} us"),
            lw=1.6, marker="x" if raw_vertical else None, markersize=4.0)
    ax.set(xlabel=("Axial z (cm)" if raw_vertical else "Radius r (cm)"),
           ylabel="n_e (1e16 m^-3)",
           title=f"Reference vs Native | {case} | {axis}")
    ax.set_xlim(0, 44 if raw_vertical else 25)
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.text(
        0.5, 0.01,
        ("Original vertical CSV and plasma axis nodes; lines join samples; "
         "no plot interpolation/extrapolation."
         if raw_vertical else
         "Reference time/coordinate mapping assumed; Native plasma mesh only; no extrapolation."),
        ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(output, dpi=155)
    plt.close(fig)

def analyze(*, exodus: Path, csv_file: Path, manifest_file: Path,
            vertical_reference: Path, horizontal_reference: Path,
            output: Path, label: str, time_us: float = 100.0) -> dict:
    manifest = json.loads(manifest_file.read_text())
    if (manifest.get("schema") != "issue493_public_p3_artifact_v1"
            or manifest.get("P3") != "PASS"
            or manifest.get("science") != "SCIENCE_HOLD"):
        raise ValueError("NATIVE_P3_PROVENANCE_NOT_VERIFIED")
    for path in (exodus, csv_file):
        if sha256(path) != manifest.get("files", {}).get(path.name, {}).get("sha256"):
            raise ValueError("NATIVE_OUTPUT_SHA256_MISMATCH")
    vx, vy = load_reference(vertical_reference, "z_cm")
    rx, ry = load_reference(horizontal_reference, "r_cm")
    if abs(rx[0]) > 1e-8 or 23.0 not in vx:
        raise ValueError("REFERENCE_SLICE_COORDINATES_INVALID")
    if output.exists():
        raise ValueError("REFERENCE_OUTPUT_ALREADY_EXISTS")
    v_native, r_native, native_peak, actual_time, raw_vertical = plasma_slice(exodus, vx, rx, time_us)
    summary = {
        "schema": "issue493_public_reference_native_overlay_v1",
        "case": manifest["case"], "arm": manifest["arm"], "label": label,
        "native_time_us": actual_time,
        "native_peak_ne_m_minus3": native_peak,
        "reference_peak_ne_m_minus3": max(max(vy), max(ry)),
        "native_peak_over_reference_peak": native_peak / max(max(vy), max(ry)),
        "vertical": evaluate(vy, v_native), "horizontal": evaluate(ry, r_native),
        "reference_sha256": {
            "vertical": sha256(vertical_reference), "horizontal": sha256(horizontal_reference)},
        "native_sha256": {"exodus": sha256(exodus), "csv": sha256(csv_file)},
        "reference_timestamp": "UNKNOWN",
        "reference_coordinates": "ASSUMED_R_0_TO_25_Z_0_TO_44_CM",
        "sampling": "PLASMA_TRIANGLE_LINEAR_NO_EXTRAPOLATION",
        "comparison_status": "DIAGNOSTIC_ONLY",
        "science": "SCIENCE_HOLD",
        "native_p3": "PASS",
        "bc_p4_parity": "NOT_EVALUATED",
    }
    output.mkdir(parents=True)
    for axis, x, reference, native in (("vertical", vx, vy, v_native),
                                   ("horizontal", rx, ry, r_native)):
        with (output / f"{axis}_profile.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            # Keep the sampled Native values separate from the versioned public reference.
            writer.writerow(["coordinate_cm", "native_ne_m_minus3"])
            writer.writerows(zip(x, native))
        # Vertical: plot the original r=0 plasma nodes; horizontal keeps the
        # existing z=23 cm triangle-interpolated profile (no exact mesh nodes).
        plot_x, plot_native = raw_vertical if axis == "vertical" else (x, native)
        plot_profile(x, reference, plot_x, plot_native, axis=axis, case=label,
                     time_us=actual_time,
                     output=output / f"{axis}_absolute.png")
    (output / "metrics.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exodus", required=True, type=Path)
    p.add_argument("--csv", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--reference-vertical", required=True, type=Path)
    p.add_argument("--reference-horizontal", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--label", required=True)
    p.add_argument("--time-us", type=float, default=100)
    a = p.parse_args()
    try:
        report = analyze(exodus=a.exodus, csv_file=a.csv, manifest_file=a.manifest,
                         vertical_reference=a.reference_vertical,
                         horizontal_reference=a.horizontal_reference, output=a.output,
                         label=a.label, time_us=a.time_us)
        print(json.dumps({"event": "REFERENCE_NATIVE_OVERLAY_WRITTEN",
                          "label": report["label"], "science": report["science"]}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, ImportError) as exc:
        print("REFERENCE_NATIVE_OVERLAY_HOLD", type(exc).__name__, str(exc)[:120])
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
