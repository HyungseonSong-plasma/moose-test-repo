#!/usr/bin/env python3
"""P4: compare verified public B/C CSV and all Exodus numerical field arrays.

Numerical differences are MEASURED, not judged equivalent without user-approved
physics tolerances. Historical A/private rates and full scientific acceptance
are deliberately outside this public-only B/C comparison.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

CASES = ("417", "941")
ARMS = ("B", "C")
SELECTED_TIMES = (0, 115, 230, 345, 460)

def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as data:
        for chunk in iter(lambda: data.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_arm(root: Path, case: str, arm: str) -> tuple[dict, dict]:
    folder = root / f"issue493-public-{case}-{arm}-results"
    manifest = json.loads((folder / "manifest.json").read_text())
    if (manifest.get("schema") != "issue493_public_p3_artifact_v1"
            or manifest.get("case") != case or manifest.get("arm") != arm
            or any(manifest.get(k) != "PASS" for k in ("P0", "P1", "P2", "P3"))
            or manifest.get("science") != "SCIENCE_HOLD"
            or manifest.get("frames") != 461
            or manifest.get("t_end_seconds") != 0.0001):
        raise ValueError("P4_UNTRUSTED_ARM_PROVENANCE")
    for name in ("plasma.e", "plasma.csv"):
        file = folder / name
        rec = manifest.get("files", {}).get(name, {})
        if (not file.is_file() or file.is_symlink()
                or file.stat().st_size != rec.get("bytes")
                or hash_file(file) != rec.get("sha256")):
            raise ValueError("P4_ARTIFACT_HASH_MISMATCH")
    return manifest, {"csv": folder / "plasma.csv", "exodus": folder / "plasma.e"}

def read_csv(file: Path) -> tuple[list[str], list[dict[str, float]]]:
    with file.open(newline="") as stream:
        reader = csv.DictReader(stream)
        names = reader.fieldnames
        if not names or names[0] != "time" or len(set(names)) != len(names):
            raise ValueError("P4_BAD_CSV_HEADERS")
        records = []
        for rec in reader:
            if None in rec or set(rec) != set(names):
                raise ValueError("P4_BAD_CSV_COLUMNS")
            parsed = {key: float(rec[key]) for key in names}
            if not all(math.isfinite(value) for value in parsed.values()):
                raise ValueError("P4_NONFINITE_CSV")
            records.append(parsed)
    if len(records) != 461 or not math.isclose(records[0]["time"], 0, abs_tol=1e-15):
        raise ValueError("P4_INCOMPLETE_CSV")
    if not math.isclose(records[-1]["time"], 0.0001, abs_tol=1e-9):
        raise ValueError("P4_WRONG_END_TIME")
    if any(b["time"] <= a["time"] for a, b in zip(records, records[1:])):
        raise ValueError("P4_NONMONOTONIC_TIME")
    return names, records

def compare_csv(b: Path, c: Path) -> tuple[dict, list, list]:
    names_b, rows_b = read_csv(b)
    names_c, rows_c = read_csv(c)
    if set(names_b) != set(names_c):
        raise ValueError("P4_CSV_FIELD_SCHEMA_MISMATCH")
    times = [r["time"] for r in rows_b]
    if max(abs(a["time"] - z["time"]) for a, z in zip(rows_b, rows_c)) > 1e-12:
        raise ValueError("P4_B_C_TIMEGRID_MISMATCH")
    measurements = {}
    for key in sorted(set(names_b) - {"time"}):
        diffs = [a[key] - z[key] for a, z in zip(rows_b, rows_c)]
        scale = sum(a[key] ** 2 for a in rows_b)
        sse = sum(d * d for d in diffs)
        measurements[key] = {
            "max_abs": max(abs(d) for d in diffs),
            "rmse": math.sqrt(sse / len(diffs)),
            "relative_l2_to_B": math.sqrt(sse / scale) if scale > 0 else None,
            "B_final": rows_b[-1][key], "C_final": rows_c[-1][key],
            "sample_times_us": {
                str(round(times[i] * 1e6, 8)): {
                    "B": rows_b[i][key], "C": rows_c[i][key],
                    "abs_diff": abs(diffs[i]),
                } for i in SELECTED_TIMES
            },
        }
    return {
        "timepoints": 461, "t_end_seconds": 0.0001,
        "fields_compared": len(measurements), "field_metrics": measurements,
        "comparison": "MEASURED_NO_ACCEPTED_NUMERICAL_TOLERANCES",
    }, rows_b, rows_c

def compare_exodus(b: Path, c: Path) -> dict:
    import netCDF4
    import numpy as np
    metrics = {}
    max_abs = 0.0
    with netCDF4.Dataset(b, "r") as aa, netCDF4.Dataset(c, "r") as bb:
        for dim in ("time_step", "num_nodes", "num_elem"):
            if (dim not in aa.dimensions or dim not in bb.dimensions
                    or len(aa.dimensions[dim]) != len(bb.dimensions[dim])):
                raise ValueError("P4_EXODUS_DIMENSION_MISMATCH_" + dim)
        if len(aa.dimensions["time_step"]) != 461:
            raise ValueError("P4_EXODUS_FRAME_COUNT")
        va = set(aa.variables)
        vb = set(bb.variables)
        key_fields = sorted(n for n in (va | vb) if n.startswith("vals_"))
        if not key_fields or any(n not in va or n not in vb for n in key_fields):
            raise ValueError("P4_EXODUS_FIELD_MISMATCH")
        for name in sorted(va | vb):
            if name.startswith(("name_nod_var", "name_elem_var", "name_glo_var")):
                if name not in va or name not in vb:
                    raise ValueError("P4_EXODUS_LABELS_MISMATCH")
                if np.any(aa.variables[name][:] != bb.variables[name][:]):
                    raise ValueError("P4_EXODUS_FIELD_NAMES_MISMATCH")
        geometry = sorted(n for n in (va | vb) if n.startswith(("coord", "connect")))
        if any(n not in va or n not in vb for n in geometry):
            raise ValueError("P4_EXODUS_MESH_SCHEMA_MISMATCH")
        for name in geometry:
            a = np.ma.filled(aa.variables[name][:], np.nan)
            d = np.ma.filled(bb.variables[name][:], np.nan)
            if a.shape != d.shape or not np.array_equal(a, d):
                raise ValueError("P4_EXODUS_MESH_DIFFERENCE_" + name)
        for name in ["time_whole"] + key_fields:
            if name not in aa.variables or name not in bb.variables:
                raise ValueError("P4_EXODUS_FIELD_ABSENT_" + name)
            v1, v2 = aa.variables[name], bb.variables[name]
            if v1.shape != v2.shape:
                raise ValueError("P4_EXODUS_VARIABLE_SHAPE_MISMATCH_" + name)
            n = 0
            sumdiff = 0.0
            sumb = 0.0
            largest = 0.0
            # Work one time slice at a time to bound peak memory for 127MB files.
            total = v1.shape[0] if len(v1.shape) > 0 else 1
            for i in range(total):
                arr_a = np.asarray(np.ma.filled(v1[i] if len(v1.shape) else v1[...], np.nan), dtype=np.float64)
                arr_b = np.asarray(np.ma.filled(v2[i] if len(v2.shape) else v2[...], np.nan), dtype=np.float64)
                if not (np.isfinite(arr_a).all() and np.isfinite(arr_b).all()):
                    raise ValueError("P4_NONFINITE_EXODUS_FIELD_" + name)
                delta = arr_a - arr_b
                largest = max(largest, float(np.max(np.abs(delta))))
                sumdiff += float(np.sum(delta ** 2))
                sumb += float(np.sum(arr_a ** 2))
                n += int(arr_a.size)
            max_abs = max(max_abs, largest)
            metrics[name] = {
                "max_abs": largest,
                "rmse": math.sqrt(sumdiff / n) if n else None,
                "relative_l2_to_B": math.sqrt(sumdiff / sumb) if sumb else None,
                "values_compared": n,
            }
    return {
        "timepoints": 461, "mesh": "IDENTICAL",
        "fields_compared": len(key_fields), "max_abs_across_fields": max_abs,
        "field_metrics": metrics,
        "comparison": "MEASURED_NO_ACCEPTED_NUMERICAL_TOLERANCES",
    }

def make_plot(b: list[dict], c: list[dict], dest: Path, case: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = [n for n in b[0] if n != "time"]
    preferred = [n for n in names if any(k in n.lower() for k in ("ne", "electron", "energy", "o2", "ion"))]
    selected = (preferred or names)[:6]
    if not selected:
        return
    t = [v["time"] * 1e6 for v in b]
    fig, axs = plt.subplots(len(selected), 1, figsize=(10, 2.5 * len(selected)), sharex=True, squeeze=False)
    for i, name in enumerate(selected):
        ax = axs[i, 0]
        ax.plot(t, [v[name] for v in b], label="B", linewidth=1)
        ax.plot(t, [v[name] for v in c], label="C", linewidth=1)
        ax.set_ylabel(name[:65])
        ax.grid(True, alpha=0.2)
        ax.legend()
    axs[-1, 0].set_xlabel("Time (microseconds)")
    fig.suptitle("Issue493 S6-" + case + " public B/C CSV comparison")
    fig.tight_layout()
    fig.savefig(dest / f"s6_{case}_bc_traces.png", dpi=130)
    plt.close(fig)

def analyze(root: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("P4_OUTPUT_ROOT_EXISTS")
    # Prevalidate all four SHA records before writing a success metric.
    by_case = {}
    for case in CASES:
        b, bf = load_arm(root, case, "B")
        c, cf = load_arm(root, case, "C")
        for name in ("source_sha", "candidate_sha", "oci_image", "mesh_sha256", "p1_binary_sha256"):
            if b.get(name) != c.get(name):
                raise ValueError("P4_B_C_IDENTITY_MISMATCH_" + name)
        by_case[case] = (b, c, bf, cf)
    output.mkdir(mode=0o700, parents=True)
    report = {
        "schema": "issue493_p4_public_bc_v1",
        "science": "SCIENCE_HOLD",
        "P3": "PASS_B_C_461_FRAMES",
        "P4_DATA_AND_COMPARISON": "MEASURED",
        "P4_NUMERICAL_EQUIVALENCE": "HOLD_NO_APPROVED_TOLERANCES",
        "A_original_private_rate_reference": "NOT_INCLUDED",
        "cases": {},
    }
    for case, (bm, cm, bf, cf) in by_case.items():
        csv_metric, brow, crow = compare_csv(bf["csv"], cf["csv"])
        exodus_metric = compare_exodus(bf["exodus"], cf["exodus"])
        report["cases"][case] = {
            "binary_sha256": bm["p1_binary_sha256"],
            "source_sha": bm["source_sha"], "candidate_sha": bm["candidate_sha"],
            "B_manifest": bm, "C_manifest": cm,
            "csv": csv_metric, "exodus": exodus_metric,
        }
        make_plot(brow, crow, output, case)
    (output / "p4_metrics.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    try:
        record = analyze(a.artifacts_root, a.output)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        print("ISSUE493_P4_PUBLIC_BC_HOLD", type(exc).__name__, str(exc)[:150], file=sys.stderr)
        return 2
    print(json.dumps({
        "event": "ISSUE493_P4_PUBLIC_BC_MEASURED",
        "cases": list(record["cases"]),
        "data": "PASS", "numerical_equivalence": "HOLD_NO_APPROVED_TOLERANCES",
        "science": "SCIENCE_HOLD",
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
