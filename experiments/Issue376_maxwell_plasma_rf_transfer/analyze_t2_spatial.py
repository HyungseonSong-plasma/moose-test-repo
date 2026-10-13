#!/usr/bin/env python3
"""Issue #376 T2 independent spatial transfer analyzer."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

SIGMA_R = 5.0
NODE_COMPLEX_L2_GATE = 1.0e-10
NODE_Q_L2_GATE = 1.0e-10
NODE_MAX_NORM_GATE = 1.0e-9
RZ_FIELD_L2_GATE = 2.0e-2
RZ_Q_L2_GATE = 2.0e-2
RZ_Q_SHAPE_L2_GATE = 2.0e-2
PROBE_GLOBAL_MAX_GATE = 5.0e-3
RAW_POWER_REL_GATE = 2.0e-2

PROBES = np.array(
    [
        [0.05, 0.15],
        [0.12, 0.15],
        [0.20, 0.15],
        [0.05, 0.28],
        [0.12, 0.28],
        [0.20, 0.28],
    ],
    dtype=float,
)


def decode_names(var) -> list[str]:
    a = np.asarray(var.data).copy()
    out: list[str] = []
    for row in a:
        if row.dtype.kind == "S":
            text = b"".join(row.tolist()).decode(errors="ignore")
        else:
            text = "".join(chr(int(v)) for v in row if int(v) != 0)
        out.append(text.split("\0")[0].strip())
    return out


def read_exodus(path: Path) -> dict:
    with netcdf_file(path, "r", mmap=False) as f:
        x = np.asarray(f.variables["coordx"].data, dtype=float).copy()
        y = np.asarray(f.variables["coordy"].data, dtype=float).copy()
        times = np.asarray(f.variables["time_whole"].data, dtype=float).copy()
        eb_names = decode_names(f.variables["eb_names"])
        blocks: dict[str, np.ndarray] = {}
        for i, name in enumerate(eb_names, start=1):
            key = f"connect{i}"
            if key not in f.variables:
                continue
            conn = np.asarray(f.variables[key].data, dtype=int).copy() - 1
            if conn.ndim == 2 and conn.shape[1] == 3:
                blocks[name] = conn
        names = decode_names(f.variables["name_nod_var"])
        nodal: dict[str, np.ndarray] = {}
        for i, name in enumerate(names, start=1):
            nodal[name] = np.asarray(f.variables[f"vals_nod_var{i}"].data, dtype=float).copy()
    return {"x": x, "y": y, "times": times, "blocks": blocks, "nodal": nodal}


def p1_eval(points: np.ndarray, triangles: np.ndarray, values: np.ndarray, queries: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tri_xy = points[triangles]
    mins = tri_xy.min(axis=1) - 1.0e-12
    maxs = tri_xy.max(axis=1) + 1.0e-12
    out = np.full(len(queries), np.nan, dtype=float)
    owners = np.full(len(queries), -1, dtype=int)
    for k, p in enumerate(queries):
        cand = np.where(
            (mins[:, 0] <= p[0])
            & (p[0] <= maxs[:, 0])
            & (mins[:, 1] <= p[1])
            & (p[1] <= maxs[:, 1])
        )[0]
        for idx in cand:
            a, b, c = tri_xy[idx]
            matrix = np.array(
                [[a[0], b[0], c[0]], [a[1], b[1], c[1]], [1.0, 1.0, 1.0]],
                dtype=float,
            )
            lam = np.linalg.solve(matrix, np.array([p[0], p[1], 1.0]))
            if lam.min() >= -2.0e-10 and lam.max() <= 1.0 + 2.0e-10:
                out[k] = float(np.dot(lam, values[triangles[idx]]))
                owners[k] = int(idx)
                break
    return out, owners


def rel_l2(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1.0e-300))


def weighted_rel_l2(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> float:
    num = float(np.sum(w * (a - b) ** 2))
    den = float(np.sum(w * b**2))
    return math.sqrt(num / max(den, 1.0e-300))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--maxwell-csv", type=Path, required=True)
    ap.add_argument("--raw-csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    src = read_exodus(args.source)
    tgt = read_exodus(args.target)
    failures: list[str] = []

    def last_csv(path: Path) -> dict[str, float]:
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            raise RuntimeError(f"empty CSV: {path}")
        return {k: float(v) for k, v in rows[-1].items() if k and v not in (None, "")}

    source_power = last_csv(args.maxwell_csv)["P_abs"]
    raw_power = last_csv(args.raw_csv)["P_rf_raw_W"]

    sxy = np.column_stack((src["x"], src["y"]))
    txy = np.column_stack((tgt["x"], tgt["y"]))
    stri = src["blocks"]["plasma"]
    ttri = tgt["blocks"]["plasma"]
    sr = src["nodal"]["E_real"][-1]
    si = src["nodal"]["E_imag"][-1]
    mr = tgt["nodal"]["E_real_rf"][-1]
    mi = tgt["nodal"]["E_imag_rf"][-1]

    ref_r, own_r = p1_eval(sxy, stri, sr, txy)
    ref_i, own_i = p1_eval(sxy, stri, si, txy)
    located = (own_r >= 0) & (own_i >= 0)
    if not np.all(located):
        failures.append(f"independent source interpolation missed {int((~located).sum())} target nodes")

    node_complex_l2 = math.sqrt(
        float(np.sum((mr - ref_r) ** 2 + (mi - ref_i) ** 2))
        / max(float(np.sum(ref_r**2 + ref_i**2)), 1.0e-300)
    )
    node_max_norm = max(
        float(np.max(np.abs(mr - ref_r))) / max(float(np.max(np.abs(ref_r))), 1.0e-300),
        float(np.max(np.abs(mi - ref_i))) / max(float(np.max(np.abs(ref_i))), 1.0e-300),
    )
    q_m = 0.5 * SIGMA_R * (mr**2 + mi**2)
    q_ref = 0.5 * SIGMA_R * (ref_r**2 + ref_i**2)
    node_q_l2 = rel_l2(q_m, q_ref)

    if node_complex_l2 > NODE_COMPLEX_L2_GATE:
        failures.append(f"MOOSE/reference nodal complex-field L2 {node_complex_l2:.6e} > {NODE_COMPLEX_L2_GATE:.6e}")
    if node_q_l2 > NODE_Q_L2_GATE:
        failures.append(f"MOOSE/reference nodal q_RF L2 {node_q_l2:.6e} > {NODE_Q_L2_GATE:.6e}")
    if node_max_norm > NODE_MAX_NORM_GATE:
        failures.append(f"MOOSE/reference nodal max normalized error {node_max_norm:.6e} > {NODE_MAX_NORM_GATE:.6e}")

    bary = np.array(
        [[1.0 / 6.0, 1.0 / 6.0, 2.0 / 3.0],
         [1.0 / 6.0, 2.0 / 3.0, 1.0 / 6.0],
         [2.0 / 3.0, 1.0 / 6.0, 1.0 / 6.0]],
        dtype=float,
    )
    tri_xy = txy[ttri]
    qpts = (tri_xy[:, None, :, :] * bary[None, :, :, None]).sum(axis=2).reshape(-1, 2)
    target_r_q = (mr[ttri][:, None, :] * bary[None, :, :]).sum(axis=2).reshape(-1)
    target_i_q = (mi[ttri][:, None, :] * bary[None, :, :]).sum(axis=2).reshape(-1)
    source_r_q, own_qr = p1_eval(sxy, stri, sr, qpts)
    source_i_q, own_qi = p1_eval(sxy, stri, si, qpts)
    if not (np.all(own_qr >= 0) and np.all(own_qi >= 0)):
        failures.append("independent source interpolation missed target quadrature points")

    v1 = tri_xy[:, 1] - tri_xy[:, 0]
    v2 = tri_xy[:, 2] - tri_xy[:, 0]
    area = 0.5 * np.abs(v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0])
    weights = np.repeat(area / 3.0, 3) * 2.0 * math.pi * qpts[:, 0]

    field_rz_l2 = math.sqrt(
        float(np.sum(weights * ((target_r_q - source_r_q) ** 2 + (target_i_q - source_i_q) ** 2)))
        / max(float(np.sum(weights * (source_r_q**2 + source_i_q**2))), 1.0e-300)
    )
    source_q = 0.5 * SIGMA_R * (source_r_q**2 + source_i_q**2)
    target_q = 0.5 * SIGMA_R * (target_r_q**2 + target_i_q**2)
    q_rz_l2 = weighted_rel_l2(target_q, source_q, weights)
    source_q_power = float(np.sum(weights * source_q))
    target_q_power = float(np.sum(weights * target_q))
    source_shape = source_q / source_q_power
    target_shape = target_q / target_q_power
    q_shape_l2 = weighted_rel_l2(target_shape, source_shape, weights)

    if field_rz_l2 > RZ_FIELD_L2_GATE:
        failures.append(f"RZ-weighted remesh field L2 {field_rz_l2:.6e} > {RZ_FIELD_L2_GATE:.6e}")
    if q_rz_l2 > RZ_Q_L2_GATE:
        failures.append(f"RZ-weighted remesh q_RF L2 {q_rz_l2:.6e} > {RZ_Q_L2_GATE:.6e}")
    if q_shape_l2 > RZ_Q_SHAPE_L2_GATE:
        failures.append(f"RZ-weighted normalized q_RF shape L2 {q_shape_l2:.6e} > {RZ_Q_SHAPE_L2_GATE:.6e}")

    src_pr, own_pr = p1_eval(sxy, stri, sr, PROBES)
    src_pi, own_pi = p1_eval(sxy, stri, si, PROBES)
    tgt_pr, own_tr = p1_eval(txy, ttri, mr, PROBES)
    tgt_pi, own_ti = p1_eval(txy, ttri, mi, PROBES)
    if not (np.all(own_pr >= 0) and np.all(own_pi >= 0) and np.all(own_tr >= 0) and np.all(own_ti >= 0)):
        failures.append("representative probe location failure")
    global_source_max = float(np.max(np.hypot(sr, si)))
    probe_abs = np.hypot(tgt_pr - src_pr, tgt_pi - src_pi)
    probe_global_norm = probe_abs / max(global_source_max, 1.0e-300)
    max_probe_global_norm = float(np.max(probe_global_norm))
    if max_probe_global_norm > PROBE_GLOBAL_MAX_GATE:
        failures.append(
            f"representative probe max absolute/global-field error {max_probe_global_norm:.6e} > {PROBE_GLOBAL_MAX_GATE:.6e}"
        )

    raw_power_rel = abs(raw_power - source_power) / max(abs(source_power), 1.0e-300)
    if raw_power_rel > RAW_POWER_REL_GATE:
        failures.append(f"raw mapped power defect {raw_power_rel:.6e} > {RAW_POWER_REL_GATE:.6e}")

    probes = []
    for p, srr, sii, trr, tii, ng in zip(PROBES, src_pr, src_pi, tgt_pr, tgt_pi, probe_global_norm):
        probes.append(
            {
                "r_m": float(p[0]),
                "z_m": float(p[1]),
                "source_E_real": float(srr),
                "source_E_imag": float(sii),
                "target_E_real": float(trr),
                "target_E_imag": float(tii),
                "abs_error_over_global_source_max": float(ng),
            }
        )

    report = {
        "issue": 376,
        "gate": "T2 spatial transfer against independent TRI3 interpolation/integration reference",
        "status": "FAIL" if failures else "PASS",
        "scientific_acceptance": {"T2_spatial_transfer": not failures, "issue_376_complete": False},
        "target_nodes": int(len(txy)),
        "target_triangles": int(len(ttri)),
        "independent_node_coverage": float(np.mean(located)),
        "moose_vs_independent_nodal_projection": {
            "complex_field_relative_l2": node_complex_l2,
            "q_rf_relative_l2": node_q_l2,
            "max_component_error_over_component_max": node_max_norm,
        },
        "source_to_target_remesh_fidelity": {
            "rz_weighted_complex_field_relative_l2": field_rz_l2,
            "rz_weighted_q_rf_relative_l2": q_rz_l2,
            "rz_weighted_normalized_q_rf_shape_relative_l2": q_shape_l2,
            "three_point_reference_power_W": source_q_power,
            "three_point_target_power_W": target_q_power,
            "raw_moose_target_power_W": raw_power,
            "source_moose_power_W": source_power,
            "raw_power_relative_defect": raw_power_rel,
        },
        "representative_probes": probes,
        "max_probe_abs_error_over_global_source_max": max_probe_global_norm,
        "tolerances": {
            "nodal_complex_relative_l2": NODE_COMPLEX_L2_GATE,
            "nodal_q_relative_l2": NODE_Q_L2_GATE,
            "nodal_max_normalized": NODE_MAX_NORM_GATE,
            "rz_field_relative_l2": RZ_FIELD_L2_GATE,
            "rz_q_relative_l2": RZ_Q_L2_GATE,
            "rz_q_shape_relative_l2": RZ_Q_SHAPE_L2_GATE,
            "probe_abs_over_global_source_max": PROBE_GLOBAL_MAX_GATE,
            "raw_power_relative": RAW_POWER_REL_GATE,
        },
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
