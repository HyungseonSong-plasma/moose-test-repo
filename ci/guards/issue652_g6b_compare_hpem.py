#!/usr/bin/env python3
"""Read the original #652 G6B 417/941 full-100us Exodus artifacts and compare to
the frozen 400W HPEM profiles at r=0cm and z=23cm, diagnostic only.

Requires immutable GitHub artifact receipts and independently checked SHA256
for *both* original plasma.e/plasma.csv. Never publishes protected rates,
full Exodus again, native logs, or checkpoints. HPEM reference time UNKNOWN.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
REF_ROOT = ROOT / "experiments/Issue493_s6_boltzmann"
sys.path.insert(0, str(REF_ROOT))
import compare_native_reference as refmod  # noqa: E402

CASES = ("417", "941")
EXACT_RUN_SOURCE = "26e84a4a33cf93d9e278a4f0b2d78c53cae2d6ce"
EXACT_RUN_ID = 45216929109
PUBLIC_D100_SHA = "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
REFERENCE_SHA = {
    "vertical": "24f72104a12c087c36ec5107fb4c581276ffe110ee01b7d9fea48ab058eb9ad8",
    "horizontal": "8e6856a46273b00058428874d3bcbe89dadddd0038e803565c8dfab1c220eff8",
}
REFERENCE_PATHS = {
    "vertical": REF_ROOT / "reference/reference_vertical.csv",
    "horizontal": REF_ROOT / "reference/reference_horizontal.csv",
}


class ComparisonHold(ValueError):
    pass


def exact_file(folder: Path, filename: str) -> Path:
    files = list(folder.rglob(filename))
    if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
        raise ComparisonHold("ARTIFACT_REQUIRED_EXACTLY_ONCE:" + filename)
    return files[0]


def read_verified_artifact(case: str, status_folder: Path, raw_folder: Path) -> dict:
    receipt_file = exact_file(status_folder, "g6b-full100-" + case + ".json")
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ComparisonHold("CASE_RECEIPT_NOT_JSON") from exc
    required = (
        receipt.get("schema") == "issue652.g6b.native_100us_case.v1"
        and receipt.get("case_id") == case
        and receipt.get("source_sha") == EXACT_RUN_SOURCE
        and receipt.get("original_publicd_lookup_sha256") == PUBLIC_D100_SHA
        and receipt.get("P3_100us") == "PASS_NATIVE_FINITE_461_FRAMES"
        and receipt.get("P4") == "NOT_RUN"
        and receipt.get("science") == "SCIENCE_HOLD"
        and receipt.get("original_s6_input_unchanged") is True
        and receipt.get("public_outputs_ready") is True
        and receipt.get("time_series", {}).get("time_points") == 461
        and receipt.get("original_time_grid", {}).get("intervals") == 460
        and receipt.get("raw_protected_rates_in_artifact") is False
    )
    if not required:
        raise ComparisonHold("FULL100_CASE_PROVENANCE_NOT_PROVEN:" + case)
    result = {"case": case, "receipt": receipt}
    for filename, key in (("plasma.e", "native_exodus"), ("plasma.csv", "native_csv")):
        path = exact_file(raw_folder, filename)
        observed = refmod.sha256(path)
        if (observed != receipt.get(key, {}).get("sha256")
                or path.stat().st_size != receipt.get(key, {}).get("bytes")):
            raise ComparisonHold("EXACT_NATIVE_SHA_OR_SIZE_DRIFT:" + case + ":" + filename)
        result[key] = path
    return result


def names(chars) -> list[str]:
    import numpy as np
    a = np.asarray(chars)
    if a.ndim != 2:
        raise ComparisonHold("EXODUS_NAME_TABLE_UNEXPECTED_DIMENSION")
    result = []
    for row in a:
        if row.dtype.kind == "U":
            word = "".join(row.tolist())
        else:
            word = row.astype("S1").tobytes().decode("ascii", "ignore")
        result.append(word.strip("\x00 "))
    return result


def slice_exodus(path: Path, vertical: list[float], horizontal: list[float]) -> dict:
    import numpy as np
    import matplotlib.tri as mtri

    with path.open("rb") as handle:
        magic = handle.read(8)
    if magic.startswith((b"CDF\x01", b"CDF\x02", b"CDF\x05")):
        from scipy.io import netcdf_file
        dataset = netcdf_file(path, "r", mmap=False)
        engine = "scipy_netcdf3"
    elif magic == b"\x89HDF\r\n\x1a\n":
        from netCDF4 import Dataset
        dataset = Dataset(path, "r")
        engine = "netcdf4_hdf5"
    else:
        raise ComparisonHold("EXODUS_FILE_FORMAT_UNKNOWN")
    with dataset as data:
        times = np.asarray(data.variables["time_whole"][:], dtype=float)
        if not len(times) or not np.isfinite(times).all():
            raise ComparisonHold("EXODUS_TIME_AXIS_INVALID")
        idx = int(np.argmin(abs(times - 1e-4)))
        native_time = float(times[idx])
        if abs(native_time - 1e-4) > 1e-9:
            raise ComparisonHold("EXODUS_100US_FINAL_FRAME_MISSING")
        nodal = names(data.variables["name_nod_var"][:])
        possible = [name for name in ("log_e", "log_ne") if name in nodal]
        if len(possible) != 1 or nodal.count(possible[0]) != 1:
            raise ComparisonHold("EXODUS_ELECTRON_LOG_VARIABLE_MISSING_OR_AMBIGUOUS")
        electron_field = possible[0]
        variable = "vals_nod_var" + str(nodal.index(electron_field) + 1)
        logged = np.asarray(data.variables[variable][idx, :], dtype=float)
        r_cm = np.asarray(data.variables["coordx"][:], dtype=float) * 100.0
        z_cm = np.asarray(data.variables["coordy"][:], dtype=float) * 100.0
        blocks = names(data.variables["eb_names"][:])
        if blocks.count("plasma") != 1:
            raise ComparisonHold("EXODUS_PLASMA_MESH_NOT_UNIQUE")
        connectivity = np.asarray(
            data.variables["connect" + str(blocks.index("plasma") + 1)][:], dtype=int) - 1
        if connectivity.ndim != 2 or connectivity.shape[1] not in (3, 4):
            raise ComparisonHold("EXODUS_PLASMA_TRI_OR_QUAD_REQUIRED")
        if connectivity.shape[1] == 4:
            triangles = np.vstack((
                connectivity[:, [0, 1, 2]], connectivity[:, [0, 2, 3]]))
        else:
            triangles = connectivity
        nodes = np.unique(triangles)
        if min(nodes) < 0 or max(nodes) >= len(r_cm):
            raise ComparisonHold("EXODUS_CONNECTIVITY_OUT_OF_BOUNDS")
        if not (len(r_cm) == len(z_cm) == len(logged)):
            raise ComparisonHold("EXODUS_COORD_FIELD_SIZE_DRIFT")
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            ne = refmod.NA * np.exp(logged)
        if not np.isfinite(ne[nodes]).all() or (ne[nodes] < 0).any():
            raise ComparisonHold("EXODUS_ELECTRON_DENSITY_NONFINITE")
        try:
            interpolator = mtri.LinearTriInterpolator(mtri.Triangulation(
                r_cm, z_cm, triangles), ne)
            vertical_native = np.ma.filled(
                interpolator(np.zeros(len(vertical)), vertical), np.nan).tolist()
            horizontal_native = np.ma.filled(
                interpolator(horizontal, np.full(len(horizontal), 23.0)), np.nan).tolist()
        except (ValueError, RuntimeError) as exc:
            raise ComparisonHold("PLASMA_TRIANGLE_INTERPOLATION_FAILED") from exc
        on_axis = nodes[np.isclose(r_cm[nodes], 0.0, rtol=0.0, atol=1e-10)]
        on_axis = on_axis[np.argsort(z_cm[on_axis])]
        raw_axis_z = z_cm[on_axis].tolist()
        raw_axis_ne = ne[on_axis].tolist()
        peak_idx = nodes[int(np.argmax(ne[nodes]))]
        return {
            "vertical_native": vertical_native, "horizontal_native": horizontal_native,
            "axis_native_raw": {"z_cm": raw_axis_z, "ne_m_minus3": raw_axis_ne},
            "field": electron_field, "time_us": native_time * 1e6,
            "plasma_nodes": len(nodes), "plasma_elements": len(triangles),
            "native_plasma_peak_ne_m_minus3": float(ne[peak_idx]),
            "native_plasma_peak_position_cm": {
                "r": float(r_cm[peak_idx]), "z": float(z_cm[peak_idx]),
            },
            "exodus_engine": engine,
        }


def metrics(x: list[float], reference: list[float], native: list[float]) -> dict:
    import numpy as np
    base = refmod.evaluate(reference, native)
    overlap = [i for i, (h, n) in enumerate(zip(reference, native))
               if h > 1e15 and math.isfinite(n)]
    h = np.asarray([reference[i] for i in overlap])
    n = np.asarray([native[i] for i in overlap])
    x_overlap = [x[i] for i in overlap]
    ih, inode = int(np.argmax(h)), int(np.argmax(n))
    base.update({
        "reference_peak_location_on_overlap_cm": x_overlap[ih],
        "native_peak_location_on_overlap_cm": x_overlap[inode],
        "native_over_reference_peak_on_overlap": float(np.max(n) / np.max(h)),
        "peak_location_shift_cm": x_overlap[inode] - x_overlap[ih],
        "mean_signed_bias_m_minus3": float(np.mean(n - h)),
        "mean_absolute_relative_error": float(np.mean(np.abs(n - h) / h)),
        "reference_support_range_cm": [x_overlap[0], x_overlap[-1]],
    })
    return base


def maybe_float(val: float) -> float | None:
    return float(val) if math.isfinite(val) else None


def plot_overlays(output: Path, key: str, x: list[float], reference: list[float],
                  records: dict, native_key: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    ax.plot(x, np.asarray(reference) / 1e16, linewidth=2.4, marker="o",
            markersize=3, label="HPEM reference (time unknown)")
    for case in CASES:
        record = records[case]["slices"]
        if key == "vertical" and len(record["axis_native_raw"]["z_cm"]) > 1:
            ax.plot(record["axis_native_raw"]["z_cm"],
                    np.asarray(record["axis_native_raw"]["ne_m_minus3"]) / 1e16,
                    lw=1.5, label=f"MOOSE S6-{case} 100us (raw axis)")
        else:
            ax.plot(x, np.asarray(record[native_key]) / 1e16,
                    lw=1.5, label=f"MOOSE S6-{case} 100us (mesh interpolation)")
    ax.set(xlim=(0, 44 if key == "vertical" else 25),
           xlabel=("z (cm) at r=0" if key == "vertical" else "r (cm) at z=23 cm"),
           ylabel="Electron number density (1e16 m^-3)",
           title=("Vertical axis electron density" if key == "vertical"
                  else "Horizontal electron density at z=23 cm"))
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.2)
    ax.legend()
    fig.text(0.5, 0.008,
             "HPEM reference timestamp/coordinate calibration unverified; "
             "Native only inside plasma mesh.",
             ha="center", fontsize=8)
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(output / (key + "_hpem_vs_s6_417_941.png"), dpi=160)
    plt.close(fig)


def compare(*, case417_status: Path, case417_raw: Path,
            case941_status: Path, case941_raw: Path,
            aggregate_root: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ComparisonHold("COMPARISON_OUTPUT_ALREADY_EXISTS")
    expected = {
        "417": read_verified_artifact("417", case417_status, case417_raw),
        "941": read_verified_artifact("941", case941_status, case941_raw),
    }
    summary = json.loads(exact_file(aggregate_root, "g6b_full100_parallel_summary.json")
                         .read_text(encoding="utf-8"))
    if (summary.get("schema") != "issue652.g6b.full100_parallel_summary.v1"
            or summary.get("source_sha") != EXACT_RUN_SOURCE
            or summary.get("P3_100us") != "PASS_NATIVE_461_TIMES_EACH_NO_PARITY"
            or summary.get("science") != "SCIENCE_HOLD"
            or set(summary.get("cases", {})) != set(CASES)):
        raise ComparisonHold("BOTH_CASES_P3_AGGREGATE_NOT_PROVEN")
    for case in CASES:
        s = summary["cases"][case]
        r = expected[case]["receipt"]
        if (s.get("csv_sha256") != r["native_csv"]["sha256"]
                or s.get("exodus_sha256") != r["native_exodus"]["sha256"]):
            raise ComparisonHold("AGGREGATE_VS_CASE_NATIVE_OUTPUT_SHA_DRIFT")
    for key, path in REFERENCE_PATHS.items():
        if refmod.sha256(path) != REFERENCE_SHA[key]:
            raise ComparisonHold("FROZEN_HPEM_REFERENCE_SHA_DRIFT:" + key)
    vx, vy = refmod.load_reference(REFERENCE_PATHS["vertical"], "z_cm")
    rx, ry = refmod.load_reference(REFERENCE_PATHS["horizontal"], "r_cm")
    if (len(vx) != 45 or vx[0] != 0 or vx[-1] != 44 or
            len(rx) != 51 or rx[0] != 0 or rx[-1] != 25 or
            vx[23] != 23 or rx[0] != 0 or vy[23] != ry[0]):
        raise ComparisonHold("HPEM_REFERENCE_GEOMETRY_CHANGED")
    results = {}
    for case in CASES:
        sl = slice_exodus(expected[case]["native_exodus"], vx, rx)
        if abs(sl["time_us"] - 100) > 0.001:
            raise ComparisonHold("NATIVE_EXODUS_TIME_NOT_100US")
        results[case] = {
            "exodus_sha256": expected[case]["receipt"]["native_exodus"]["sha256"],
            "csv_sha256": expected[case]["receipt"]["native_csv"]["sha256"],
            "slices": sl,
            "vertical_metrics": metrics(vx, vy, sl["vertical_native"]),
            "horizontal_metrics": metrics(rx, ry, sl["horizontal_native"]),
        }
    output.mkdir(parents=True)
    for key, x, y, native_key in [
        ("vertical", vx, vy, "vertical_native"),
        ("horizontal", rx, ry, "horizontal_native"),
    ]:
        plot_overlays(output, key, x, y, results, native_key)
        with (output / (key + "_profiles.csv")).open("w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["coordinate_cm", "hpem_m_minus3",
                             "s6_417_m_minus3", "s6_941_m_minus3"])
            for i in range(len(x)):
                writer.writerow([
                    x[i], y[i],
                    maybe_float(results["417"]["slices"][native_key][i]),
                    maybe_float(results["941"]["slices"][native_key][i]),
                ])
    report = {
        "schema": "issue652.g6b.hpem_417_941_100us_slice_diagnostic.v1",
        "source_run": EXACT_RUN_ID, "source_sha": EXACT_RUN_SOURCE,
        "reference_source": "HPEM_400W_E_matrix(2)_public_derived",
        "reference_sha256": REFERENCE_SHA,
        "reference_timestamp": "UNKNOWN",
        "reference_coordinate_calibration": "ASSUMED_R0_TO25_Z0_TO44_CM",
        "electron_conversion": "n_e=N_A*exp(log_e_or_log_ne)",
        "axes": {"vertical": "r=0cm, z=0..44cm",
                 "horizontal": "z=23cm, r=0..25cm"},
        "comparison": "DIAGNOSTIC_ONLY_NO_TIME_MATCHED_SCIENCE_PARITY",
        "P3_100us": "PASS_REPORTED_BOTH",
        "P4": "NOT_RUN", "science": "SCIENCE_HOLD",
        "reference_peak_m_minus3": max(max(vy), max(ry)),
        "cases": {
            case: {
                "exodus_sha256": results[case]["exodus_sha256"],
                "csv_sha256": results[case]["csv_sha256"],
                "time_us": results[case]["slices"]["time_us"],
                "native_field": results[case]["slices"]["field"],
                "plasma_nodes": results[case]["slices"]["plasma_nodes"],
                "plasma_elements": results[case]["slices"]["plasma_elements"],
                "native_plasma_peak_ne_m_minus3": results[case]["slices"]["native_plasma_peak_ne_m_minus3"],
                "native_plasma_peak_position_cm": results[case]["slices"]["native_plasma_peak_position_cm"],
                "vertical": results[case]["vertical_metrics"],
                "horizontal": results[case]["horizontal_metrics"],
            } for case in CASES},
    }
    (output / "metrics.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8")
    compact = {
        case: {"peak": results[case]["slices"]["native_plasma_peak_ne_m_minus3"],
               "vertical_nrmse": results[case]["vertical_metrics"]["rmse_over_reference_peak"],
               "horizontal_nrmse": results[case]["horizontal_metrics"]["rmse_over_reference_peak"],
               "vertical_relative_l2": results[case]["vertical_metrics"]["relative_l2"],
               "horizontal_relative_l2": results[case]["horizontal_metrics"]["relative_l2"]}
        for case in CASES
    }
    print("HPEM_COMPARE_METRICS_JSON=" + json.dumps(compact, sort_keys=True))
    profile = {
        "vertical": {"x": vx, "hpem": vy,
                     **{case: [maybe_float(v) for v in results[case]["slices"]["vertical_native"]]
                        for case in CASES}},
        "horizontal": {"x": rx, "hpem": ry,
                       **{case: [maybe_float(v) for v in results[case]["slices"]["horizontal_native"]]
                          for case in CASES}},
    }
    print("HPEM_COMPARE_PROFILES_JSON=" + json.dumps(profile, separators=(",", ":")))
    print("HPEM_COMPARE_COMPLETE_TWO_CASES_SCIENCE_HOLD")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case417-status", type=Path, required=True)
    parser.add_argument("--case417-raw", type=Path, required=True)
    parser.add_argument("--case941-status", type=Path, required=True)
    parser.add_argument("--case941-raw", type=Path, required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        compare(case417_status=args.case417_status, case417_raw=args.case417_raw,
                case941_status=args.case941_status, case941_raw=args.case941_raw,
                aggregate_root=args.aggregate, output=args.output)
        return 0
    except (OSError, ValueError, KeyError, IndexError, ImportError, RuntimeError) as exc:
        print("HPEM_COMPARE_HOLD", type(exc).__name__, str(exc)[:180], flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
