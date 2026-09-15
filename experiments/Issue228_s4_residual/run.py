#!/usr/bin/env python3
"""Issue #228 S4 residual closure campaign.

S3 current-balance restored the physical bulk potential scale and removed the
wafer / second right-wall hills, but element 2401 retained H ~= +1.35 V.
S4 isolates the remaining cause with one-axis frozen-Poisson interventions:

  s4_0 : exact S3 current_balance reference.
  s4_g : move only the validated interior node controlling 2401 geometry,
         while preserving every plasma element's integrated frozen charge
         Q_i = rho_i V_i.  This isolates Poisson geometry/reconstruction.
  s4_q : keep geometry fixed and transfer only the remaining positive bulk
         source in element 2401 to a diagnostic sheath reservoir.  This
         isolates residual local source ownership.

All cases keep the S3 current-balance sheath-edge wall values fixed.  Thus the
scientific axes are separated from the sheath closure itself.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import netcdf_file

from experiments.Issue228_d1_s3 import run as s3
from experiments.Issue228_wall_av_10step import run as gav

MODES = ("s4_0", "s4_g", "s4_q")
TARGET_EID = 2401
NODE_TAG = gav.NODE_A_TAG
NODE_OLD = gav.NODE_A_OLD
NODE_NEW = gav.NODE_A_NEW
EPS0 = s3.EPS0
HOTSPOTS = s3.HOTSPOTS


def _write(path: Path, payload: Any) -> None:
    s3._write(path, payload)


def _source_arrays(path: Path):
    f = netcdf_file(str(path), "r", mmap=False)
    x = f.variables["coordx"].data.copy().astype(float)
    y = f.variables["coordy"].data.copy().astype(float)
    conn = f.variables["connect1"].data.copy().astype(int)
    emap = f.variables["elem_num_map"].data.copy().astype(int)[: len(conn)]
    names = s3.d1s2._decode_names(f.variables["name_elem_var"].data.copy())
    iv = names.index("potential_plasma") + 1
    source = f.variables[f"vals_elem_var{iv}eb1"].data.copy()[-1].astype(float)
    ss_names = s3.d1s2._decode_names(f.variables["ss_names"].data.copy())
    sidesets = [
        (name,
         f.variables[f"elem_ss{i}"].data.copy().astype(int),
         f.variables[f"side_ss{i}"].data.copy().astype(int))
        for i, name in enumerate(ss_names, 1)
    ]
    f.close()
    return np.column_stack([x, y]), conn, emap, source, sidesets


def _volumes(coords: np.ndarray, conn: np.ndarray) -> np.ndarray:
    _tri, _area, _rcent, vol = s3.d1s2._geom(coords, conn)
    return vol


def _write_source_and_coords(path: Path, coords: np.ndarray, source: np.ndarray) -> None:
    f = netcdf_file(str(path), "a", mmap=False)
    f.variables["coordx"][:] = coords[:, 0]
    f.variables["coordy"][:] = coords[:, 1]
    names = s3.d1s2._decode_names(f.variables["name_elem_var"].data.copy())
    iv = names.index("potential_plasma") + 1
    var = f.variables[f"vals_elem_var{iv}eb1"]
    data = var.data.copy()
    data[:] = source[np.newaxis, :]
    var[:] = data
    f.flush(); f.close()


def _apply_geometry(path: Path) -> dict[str, Any]:
    coords, conn, emap, source, _ss = _source_arrays(path)
    vol0 = _volumes(coords, conn)
    rho0 = source * EPS0
    q0 = rho0 * vol0

    d = np.sqrt((coords[:, 0] - NODE_OLD[0]) ** 2 + (coords[:, 1] - NODE_OLD[1]) ** 2)
    hits = np.where(d <= 1.0e-12)[0]
    if len(hits) != 1:
        raise RuntimeError(f"expected one Exodus node at {NODE_OLD}, found {hits.tolist()}")
    inode = int(hits[0])
    old_xy = (float(coords[inode, 0]), float(coords[inode, 1]))
    coords[inode, 0] = NODE_NEW[0]
    coords[inode, 1] = NODE_NEW[1]

    vol1 = _volumes(coords, conn)
    if np.any(vol1 <= 0.0):
        raise RuntimeError("geometry edit created non-positive plasma element volume")
    rho1 = q0 / vol1
    source1 = rho1 / EPS0
    _write_source_and_coords(path, coords, source1)

    q1 = rho1 * vol1
    scale = max(float(np.max(np.abs(q0))), 1.0e-300)
    q_defect = float(np.max(np.abs(q1 - q0)) / scale)
    affected = np.where(np.any((conn - 1) == inode, axis=1))[0]
    hit2401 = np.where(emap == TARGET_EID)[0]
    if len(hit2401) != 1:
        raise RuntimeError("target element 2401 missing")
    it = int(hit2401[0])
    return {
        "axis": "geometry_only_with_per_element_integrated_charge_preserved",
        "node_tag_from_gmsh_reference": NODE_TAG,
        "exodus_node_index_zero_based": inode,
        "old_xy_m": old_xy,
        "new_xy_m": [float(NODE_NEW[0]), float(NODE_NEW[1])],
        "per_element_charge_max_relative_defect": q_defect,
        "total_charge_before_C": float(np.sum(q0)),
        "total_charge_after_C": float(np.sum(q1)),
        "affected_element_ids": [int(emap[i]) for i in affected],
        "target_2401_volume_before_m3": float(vol0[it]),
        "target_2401_volume_after_m3": float(vol1[it]),
        "target_2401_volume_ratio": float(vol1[it] / vol0[it]),
        "target_2401_rho_before_C_m3": float(rho0[it]),
        "target_2401_rho_after_C_m3": float(rho1[it]),
    }


def _apply_local_source_ownership(path: Path) -> dict[str, Any]:
    coords, conn, emap, source, _ss = _source_arrays(path)
    vol = _volumes(coords, conn)
    rho = source * EPS0
    hits = np.where(emap == TARGET_EID)[0]
    if len(hits) != 1:
        raise RuntimeError("target element 2401 missing")
    i = int(hits[0])
    correction = max(float(rho[i]), 0.0)
    before = float(rho[i])
    q_before = float(np.dot(rho, vol))
    reservoir = correction * float(vol[i])
    rho[i] -= correction
    q_after = float(np.dot(rho, vol))
    _write_source_and_coords(path, coords, rho / EPS0)
    ledger_defect = abs((q_after + reservoir) - q_before)
    return {
        "axis": "target_2401_remaining_positive_bulk_source_to_sheath_reservoir",
        "target_element_id": TARGET_EID,
        "rho_before_C_m3": before,
        "rho_after_C_m3": float(rho[i]),
        "removed_positive_rho_C_m3": correction,
        "removed_charge_to_diagnostic_reservoir_C": reservoir,
        "volume_charge_before_C": q_before,
        "volume_charge_after_C": q_after,
        "ledger_total_C": q_after + reservoir,
        "ledger_defect_C": ledger_defect,
    }


def _case_geometry(path: Path):
    coords, conn, emap, _source, sidesets = _source_arrays(path)
    vol = _volumes(coords, conn)
    return coords, conn, emap, sidesets, vol


def _reference_reproduction(summary: dict[str, Any], ref_root: Path | None) -> dict[str, Any] | None:
    if ref_root is None:
        return None
    p = ref_root / "summary.json"
    if not p.exists():
        return {"status": "MISSING_REFERENCE", "path": str(p)}
    ref = json.loads(p.read_text(encoding="utf-8"))
    diffs: dict[str, float] = {
        "phi_min_abs_diff_V": abs(float(summary["phi_min_V"]) - float(ref["phi_min_V"])),
        "phi_max_abs_diff_V": abs(float(summary["phi_max_V"]) - float(ref["phi_max_V"])),
        "nonwall_mean_abs_diff_V": abs(float(summary["nonwall_volume_mean_phi_V"]) - float(ref["nonwall_volume_mean_phi_V"])),
    }
    for eid in HOTSPOTS:
        key = str(eid)
        diffs[f"H_{eid}_abs_diff_V"] = abs(
            float(summary["hotspots"][key]["H_wall_minus_inward_V"]) -
            float(ref["hotspots"][key]["H_wall_minus_inward_V"])
        )
    maxdiff = max(diffs.values())
    return {"status": "PASS" if maxdiff <= 5.0e-3 else "FAIL", "max_abs_diff_V": maxdiff, "diffs": diffs}


def run(args: argparse.Namespace) -> int:
    mode = args.mode
    if mode not in MODES:
        raise ValueError(mode)
    exe = args.physics_opt.resolve()
    snapshot = args.snapshot_root.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    case = out / "case"; logs = out / "logs"
    case.mkdir(parents=True); logs.mkdir()

    # Common baseline: S3 current-balance sheath closure + W3 excess-corrected source.
    prep = s3._prepare_source(snapshot, case)
    wall_values = s3._wall_values("current_balance", prep)
    intervention: dict[str, Any] = {"axis": "none_reference"}
    if mode == "s4_g":
        intervention = _apply_geometry(case / "source.e")
    elif mode == "s4_q":
        intervention = _apply_local_source_ownership(case / "source.e")

    initial_phi = float(np.mean(list(wall_values.values())))
    text = s3._s3_input("current_balance", wall_values, initial_phi)
    (case / "input.i").write_text(text, encoding="utf-8")

    p2 = s3.d1s2._run([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 180)
    summary: dict[str, Any] = {
        "status": "RUNNING",
        "claim": "target_2401_residual_geometry_vs_local_source_ownership",
        "mode": mode,
        "diagnostic_only": True,
        "common_sheath_model": "S3 current_balance",
        "bulk_sheath_edge_wall_values_V": wall_values,
        "preparation": prep,
        "intervention": intervention,
        "p2": p2,
    }
    if p2["returncode"] != 0:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; _write(out / "summary.json", summary); return 1

    rt = s3.d1s2._run([str(exe), "-i", "input.i"], case, logs / "runtime.log", 600)
    summary["runtime"] = rt
    if rt["returncode"] != 0 or rt["timed_out"]:
        summary["status"] = "SOLVER_CONVERGENCE_FAIL"; _write(out / "summary.json", summary); return 1

    exo = sorted(case.glob("*_out.e"))
    if len(exo) != 1:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"
        summary["error"] = f"expected one output Exodus, got {exo}"
        _write(out / "summary.json", summary); return 1

    conn, emap, phi, sidesets = s3.d1s2._read_phi(exo[0])
    hs = s3.d1s2._hotspots(emap, conn, sidesets, phi)
    _coords, conn_src, emap_src, sidesets_src, vol = _case_geometry(case / "source.e")
    if not np.array_equal(conn, conn_src) or not np.array_equal(emap, emap_src):
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"
        summary["error"] = "output/source plasma element indexing mismatch"
        _write(out / "summary.json", summary); return 1
    wall, _neigh = s3.pgw._wall_cells_and_neighbors(conn_src, sidesets_src)
    nonwall = np.asarray([i for i in range(len(conn_src)) if i not in wall], dtype=int)
    nonwall_mean = float(np.dot(phi[nonwall], vol[nonwall]) / np.sum(vol[nonwall]))
    baseline_mean = float(prep["baseline_nonwall_volume_mean_phi_V"])
    span = float(phi.max() - phi.min())
    max_lookup_resid = max(abs(float(v)) for v in prep["lookup"]["current_balance_relative_residual"].values())

    gates = {
        "target_2401_drop": str(TARGET_EID) in hs and float(hs[str(TARGET_EID)]["H_wall_minus_inward_V"]) <= 0.0,
        "other_hotspots_no_regression": all(
            str(eid) in hs and float(hs[str(eid)]["H_wall_minus_inward_V"]) <= 0.0
            for eid in HOTSPOTS if eid != TARGET_EID
        ),
        "bulk_mean_scale": abs(nonwall_mean - baseline_mean) <= 5.0,
        "finite_moderate_span": span <= 30.0,
        "bounded_potential": float(phi.min()) >= -5.0 and float(phi.max()) <= 40.0,
        "lookup_current_balance": max_lookup_resid <= 1.0e-9,
    }
    if mode == "s4_g":
        gates["integrated_charge_preserved"] = float(intervention["per_element_charge_max_relative_defect"]) <= 1.0e-12
    if mode == "s4_q":
        qscale = max(abs(float(intervention["volume_charge_before_C"])), 1.0e-300)
        gates["source_reservoir_ledger"] = float(intervention["ledger_defect_C"]) / qscale <= 1.0e-12

    summary.update({
        "phi_min_V": float(phi.min()),
        "phi_max_V": float(phi.max()),
        "phi_span_V": span,
        "phi_max_element_id": int(emap[int(np.argmax(phi))]),
        "nonwall_volume_mean_phi_V": nonwall_mean,
        "baseline_nonwall_volume_mean_phi_V": baseline_mean,
        "nonwall_mean_delta_V": nonwall_mean - baseline_mean,
        "hotspots": hs,
        "acceptance_gates": gates,
        "physical_acceptance": all(gates.values()),
    })

    ref_root = args.s3_reference_root.resolve() if args.s3_reference_root is not None else None
    if mode == "s4_0":
        reproduction = _reference_reproduction(summary, ref_root)
        summary["s3_current_balance_reproduction"] = reproduction
        ok = reproduction is None or reproduction.get("status") == "PASS"
        summary["status"] = "PASS" if ok else "VALIDATOR_SELFTEST_FAIL"
        _write(out / "summary.json", summary)
        return 0 if ok else 1

    summary["status"] = "PASS" if summary["physical_acceptance"] else "PHYSICS_MODEL_FAIL"
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--snapshot-root", type=Path, required=True)
    p.add_argument("--s3-reference-root", type=Path)
    p.add_argument("--physics-opt", type=Path, required=True)
    p.add_argument("--results-root", type=Path, required=True)
    return run(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
