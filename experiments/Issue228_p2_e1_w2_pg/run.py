#!/usr/bin/env python3
"""Issue #228 next causal discriminator campaign.

Groups
------
P2/PG: coupled FV transport with FE P1 Poisson, with baseline and selected
       first-cell geometry controls.
E1:    one-cell orthogonal FV wall-flux balance sweep isolating A/V = 1/h.
W2:    frozen production charge field, actual MOOSE FV Poisson re-solve with
       controlled suppression of positive wall-adjacent volume charge. Removed
       charge is booked to a diagnostic subgrid/sheath reservoir.

All cases are diagnostic-only. No result from this file changes production
physics by itself.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue211_science_factorial import run as sci
from experiments.Issue228_axis_bc_10step import run as axis
from experiments.Issue228_pgw_parallel import run as pgw
from experiments.Issue228_wall_av_10step import run as wav
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import validate_case_references

EPS0 = 8.8541878128e-12
HOTSPOTS = (2401, 2424, 2387)
FE_MODES = ("fe_baseline", "fe_wafer_matched", "fe_right_matched")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_command(cmd: list[str], cwd: Path, log: Path, timeout: float) -> dict[str, Any]:
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, check=False)
        log.write_text(p.stdout or "", encoding="utf-8")
        return {"returncode": int(p.returncode), "timed_out": False,
                "command": cmd, "log": str(log)}
    except subprocess.TimeoutExpired as exc:
        text = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        log.write_text(text, encoding="utf-8")
        return {"returncode": 124, "timed_out": True, "command": cmd, "log": str(log)}


def _decode_names(a) -> list[str]:
    return [bytes(row).split(b"\0")[0].decode(errors="ignore").strip() for row in a]


def _sidesets_from_exodus(f) -> list[tuple[str, np.ndarray, np.ndarray]]:
    names = _decode_names(f.variables["ss_names"].data.copy())
    return [(name,
             f.variables[f"elem_ss{i}"].data.copy().astype(int),
             f.variables[f"side_ss{i}"].data.copy().astype(int))
            for i, name in enumerate(names, 1)]


def _wall_hills(elem_map: np.ndarray, conn: np.ndarray, sidesets, cell_phi: np.ndarray) -> dict[str, Any]:
    wall, neigh = pgw._wall_cells_and_neighbors(conn, sidesets)
    result: dict[str, Any] = {}
    for eid in HOTSPOTS:
        hits = np.where(elem_map == eid)[0]
        if len(hits) != 1:
            continue
        i = int(hits[0])
        js = sorted(neigh.get(i, set()))
        if not js:
            continue
        inward = float(np.mean(cell_phi[js]))
        result[str(eid)] = {
            "wall_cell_phi_V": float(cell_phi[i]),
            "inward_neighbor_mean_phi_V": inward,
            "H_wall_minus_inward_V": float(cell_phi[i] - inward),
            "inward_neighbor_element_ids": [int(elem_map[j]) for j in js],
            "is_physical_wall_cell": bool(i in wall),
        }
    return result


# P2 / PG -------------------------------------------------------------------
def build_fe_case(mode: str) -> tuple[str, dict[str, Any]]:
    if mode not in FE_MODES:
        raise ValueError(mode)
    text, meta = axis.build_case()
    text = mb.replace_block(
        text,
        "Variables/potential_plasma",
        """  [potential_plasma]
    family = LAGRANGE
    order = FIRST
    initial_condition = 0
    block = plasma
  []""",
    )
    text = mb.remove_block(text, "FVKernels/r31_phi_diffusion")
    text = mb.remove_block(text, "FVKernels/r31_phi_charge_source")
    text = mb.remove_block(text, "FVBCs/r31_phi_ground_all")
    text = mb.append_top_level_block(
        text,
        """[Kernels]
  [r228_fe_phi_diffusion]
    type = Diffusion
    variable = potential_plasma
    block = plasma
  []
  [r228_fe_phi_charge_source]
    type = FunctorKernel
    variable = potential_plasma
    functor = poisson_charge_source
    functor_on_rhs = true
    block = plasma
  []
[]""",
    )
    text = mb.append_top_level_block(
        text,
        f"""[BCs]
  [r228_fe_phi_ground]
    type = DirichletBC
    variable = potential_plasma
    boundary = {axis.GROUND_NONAXIS}
    value = 0
  []
[]""",
    )
    geometry = "baseline"
    if mode == "fe_wafer_matched":
        geometry = "wafer_matched"
    elif mode == "fe_right_matched":
        geometry = "right_matched"
    return text, {
        **meta,
        "issue": 228,
        "claim": "coupled_FE_Poisson_and_geometry_interaction",
        "diagnostic_only": True,
        "mode": mode,
        "geometry_mode": geometry,
        "poisson_discretization": "P1_FE",
        "transport_discretization": "production_FV",
        "ion_model": "production_mixture",
        "electron_model": "production_FV",
        "sheath_law_changed": False,
        "chemistry_changed": False,
        "dt_s": axis.DT_S,
        "expected_steps": axis.EXPECTED_STEPS,
    }


def fe_self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for mode in FE_MODES:
        text, meta = build_fe_case(mode)
        checks[f"{mode}:fe_family"] = mp.get_parameter(text, "Variables/potential_plasma", "family") == "LAGRANGE"
        checks[f"{mode}:fe_order"] = mp.get_parameter(text, "Variables/potential_plasma", "order") == "FIRST"
        checks[f"{mode}:no_fv_phi_diff"] = not mb.has_block(text, "FVKernels/r31_phi_diffusion")
        checks[f"{mode}:no_fv_phi_source"] = not mb.has_block(text, "FVKernels/r31_phi_charge_source")
        checks[f"{mode}:no_fv_phi_bc"] = not mb.has_block(text, "FVBCs/r31_phi_ground_all")
        checks[f"{mode}:fe_diff"] = mp.get_parameter(text, "Kernels/r228_fe_phi_diffusion", "type") == "Diffusion"
        checks[f"{mode}:fe_source"] = mp.get_parameter(text, "Kernels/r228_fe_phi_charge_source", "functor") == "poisson_charge_source"
        checks[f"{mode}:fe_ground"] = mp.get_parameter(text, "BCs/r228_fe_phi_ground", "boundary") == axis.GROUND_NONAXIS
        checks[f"{mode}:electron_drift_same"] = mp.get_parameter(text, "FVKernels/n_e_drift", "type") == "PhysicsFVElectrostaticDrift"
        checks[f"{mode}:steps"] = int(meta["expected_steps"]) == axis.EXPECTED_STEPS
    failed = sorted(k for k, v in checks.items() if not v)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _apply_geometry(case: Path, mode: str) -> list[dict[str, Any]]:
    edits: list[dict[str, Any]] = []
    mesh = case / "qvt.msh"
    if mode == "fe_wafer_matched":
        edits.append(pgw._move_gmsh_node(mesh, pgw.WAFER_NODE_TAG, pgw.WAFER_NODE_OLD,
                                         pgw.WAFER_NODE_TARGETS["wafer_matched"]))
    elif mode == "fe_right_matched":
        edits.append(wav._move_gmsh_node(mesh, tag=wav.NODE_A_TAG,
                                         expected_old_xy=wav.NODE_A_OLD, new_xy=wav.NODE_A_NEW))
        edits.append(wav._move_gmsh_node(mesh, tag=wav.NODE_B_TAG,
                                         expected_old_xy=wav.NODE_B_OLD, new_xy=wav.NODE_B_MATCHED))
    if edits:
        refs = validate_case_references(case)
        if not isinstance(refs, list):
            raise TypeError("validate_case_references must return list")
    return edits


def _analyse_fe_exodus(epath: Path) -> dict[str, Any]:
    from scipy.io import netcdf_file
    f = netcdf_file(str(epath), "r", mmap=False)
    conn = f.variables["connect1"].data.copy().astype(int)
    elem_map = f.variables["elem_num_map"].data.copy().astype(int)[:len(conn)]
    sidesets = _sidesets_from_exodus(f)
    nod_names = _decode_names(f.variables["name_nod_var"].data.copy()) if "name_nod_var" in f.variables else []
    if "potential_plasma" not in nod_names:
        raise RuntimeError(f"potential_plasma is not nodal in FE output: {nod_names}")
    iv = nod_names.index("potential_plasma") + 1
    phi_nodes = f.variables[f"vals_nod_var{iv}"].data.copy()[-1].astype(float)
    cell_phi = np.mean(phi_nodes[conn - 1], axis=1)
    f.close()
    return {
        "phi_node_min_V": float(phi_nodes.min()),
        "phi_node_max_V": float(phi_nodes.max()),
        "phi_cell_centroid_min_V": float(cell_phi.min()),
        "phi_cell_centroid_max_V": float(cell_phi.max()),
        "hotspots": _wall_hills(elem_map, conn, sidesets, cell_phi),
    }


def run_fe(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve(); out = args.results_root.resolve(); mode = args.mode
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True); (out / "logs").mkdir()
    p0 = fe_self_test(); _write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        raise RuntimeError(p0)
    text, meta = build_fe_case(mode)
    case = out / "case"; summary: dict[str, Any] = {"status": "RUNNING", "meta": meta}
    try:
        summary["stage"] = sci._stage(case, text, meta)
        summary["mesh_edits"] = _apply_geometry(case, mode)
    except Exception as exc:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        _write(out / "summary.json", summary); return 1
    p2 = s5r._p2(exe, case, out / "logs" / "p2.log", timeout=min(300.0, float(args.timeout)))
    summary["p2"] = p2
    if p2.get("returncode") != 0:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; _write(out / "summary.json", summary); return 1
    rt = sci._runtime(exe, case, out / "logs" / "runtime.log", out / "logs" / "time_v.log", float(args.timeout))
    summary["runtime"] = rt
    if int(rt.get("returncode", 1)) != 0 or bool(rt.get("timed_out", False)):
        summary["status"] = "SOLVER_CONVERGENCE_FAIL"; _write(out / "summary.json", summary); return 1
    try:
        governed = axis._analyse(case, text, meta, rt)
        exo = sorted(case.glob("*.e*"))
        if not exo:
            raise RuntimeError("missing FE Exodus output")
        summary["governed"] = governed
        summary["profile"] = _analyse_fe_exodus(exo[0])
        summary["status"] = "PASS" if governed.get("all_steps_hard_pass") is True else "PHYSICS_MODEL_FAIL"
    except Exception as exc:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"
        summary["error"] = f"{type(exc).__name__}: {exc}"
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


# E1 ------------------------------------------------------------------------
E1_DT = 1.0e-4
E1_FLUX = 1.0
E1_INITIAL = 1.0


def build_e1_input(h_m: float) -> str:
    return f"""[Mesh]
  [gen]
    type = GeneratedMeshGenerator
    dim = 1
    xmin = 0
    xmax = {h_m:.17g}
    nx = 1
  []
[]

[Variables]
  [q]
    type = MooseVariableFVReal
    initial_condition = {E1_INITIAL:.17g}
  []
[]

[FVKernels]
  [time]
    type = FVTimeKernel
    variable = q
  []
[]

[FVBCs]
  [right_loss]
    type = FVFunctorNeumannBC
    variable = q
    boundary = right
    functor = {E1_FLUX:.17g}
    factor = 1
  []
[]

[Postprocessors]
  [q_avg]
    type = ElementAverageFunctorPostprocessor
    functor = q
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {E1_DT:.17g}
  end_time = {E1_DT:.17g}
  nl_abs_tol = 1e-13
  nl_rel_tol = 1e-12
[]

[Outputs]
  csv = true
[]
"""


def run_e1(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve(); out = args.results_root.resolve(); h = float(args.h_m)
    if out.exists(): shutil.rmtree(out)
    case = out / "case"; logs = out / "logs"; case.mkdir(parents=True); logs.mkdir()
    (case / "input.i").write_text(build_e1_input(h), encoding="utf-8")
    p2 = _run_command([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 120)
    summary: dict[str, Any] = {"status": "RUNNING", "h_m": h, "A_over_V_1_per_m": 1.0/h,
                               "dt_s": E1_DT, "outward_flux": E1_FLUX, "p2": p2}
    if p2["returncode"] != 0:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; _write(out / "summary.json", summary); return 1
    rt = _run_command([str(exe), "-i", "input.i"], case, logs / "runtime.log", 120)
    summary["runtime"] = rt
    if rt["returncode"] != 0:
        summary["status"] = "SOLVER_CONVERGENCE_FAIL"; _write(out / "summary.json", summary); return 1
    csvs = sorted(case.glob("*.csv"))
    if len(csvs) != 1:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; summary["error"] = f"expected one csv, got {csvs}"; _write(out / "summary.json", summary); return 1
    with csvs[0].open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; summary["error"] = f"too few CSV rows: {rows}"; _write(out / "summary.json", summary); return 1
    q0 = float(rows[0]["q_avg"]); q1 = float(rows[-1]["q_avg"])
    expected = E1_INITIAL - E1_FLUX * E1_DT / h
    ratio = (E1_INITIAL - q1) / (E1_FLUX * E1_DT / h)
    summary.update({"q_initial": q0, "q_final": q1, "q_expected": expected,
                    "absolute_error": abs(q1-expected), "normalized_loss_ratio": ratio})
    summary["status"] = "PASS" if abs(q1-expected) <= 1e-9 and abs(ratio-1.0) <= 1e-9 else "PHYSICS_MODEL_FAIL"
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


# W2 ------------------------------------------------------------------------
def _prepare_w2_source(snapshot: Path, work: Path, fraction: float) -> dict[str, Any]:
    from scipy.io import netcdf_file
    _coords, conn, _emap, vals, t, sidesets = pgw._load_snapshot(snapshot, 10)
    rhoq = pgw._charge_density(vals)
    _tri, _area, _rcent, vol = pgw._geom(_coords, conn)
    wall, _neigh = pgw._wall_cells_and_neighbors(conn, sidesets)
    rho_used = rhoq.copy(); removed = 0.0; count = 0
    for i in sorted(wall):
        if rhoq[i] <= 0:
            continue
        dq = fraction * rhoq[i] * vol[i]
        rho_used[i] -= dq / vol[i]
        removed += dq; count += 1
    source = rho_used / EPS0
    src_e = work / "source.e"
    shutil.copy2(snapshot / "case" / "input_out.e", src_e)
    f = netcdf_file(str(src_e), "a", mmap=False)
    names = _decode_names(f.variables["name_elem_var"].data.copy())
    iv = names.index("potential_plasma") + 1
    v = f.variables[f"vals_elem_var{iv}eb1"]
    data = v.data.copy(); data[:] = source[np.newaxis, :]; v[:] = data
    f.flush(); f.close()
    return {
        "time_s": t,
        "suppression_fraction": fraction,
        "positive_wall_cells": count,
        "removed_volume_charge_C": float(removed),
        "volume_charge_before_C": float(np.dot(rhoq, vol)),
        "volume_charge_after_C": float(np.dot(rho_used, vol)),
        "diagnostic_sheath_reservoir_C": float(removed),
        "ledger_total_C": float(np.dot(rho_used, vol) + removed),
        "ledger_defect_C": float(abs(np.dot(rho_used, vol) + removed - np.dot(rhoq, vol))),
    }


def build_w2_input() -> str:
    return f"""[Mesh]
  type = FileMesh
  file = source.e
  parallel_type = replicated
  coord_type = RZ
  rz_coord_axis = Y
[]

[Variables]
  [phi]
    type = MooseVariableFVReal
    initial_condition = 0
    block = plasma
  []
[]

[AuxVariables]
  [frozen_source]
    family = MONOMIAL
    order = CONSTANT
    block = plasma
  []
[]

[UserObjects]
  [frozen_solution]
    type = SolutionUserObject
    mesh = source.e
    system_variables = potential_plasma
    timestep = LATEST
    force_replicated_source_mesh = true
    execute_on = INITIAL
  []
[]

[AuxKernels]
  [import_source]
    type = SolutionAux
    variable = frozen_source
    solution = frozen_solution
    from_variable = potential_plasma
    direct = true
    execute_on = INITIAL
  []
[]

[FVKernels]
  [diffusion]
    type = FVDiffusion
    variable = phi
    coeff = 1
    block = plasma
  []
  [source]
    type = FVCoupledForce
    variable = phi
    v = frozen_source
    coef = 1
    block = plasma
  []
[]

[FVBCs]
  [ground]
    type = FVDirichletBC
    variable = phi
    boundary = {axis.GROUND_NONAXIS}
    value = 0
  []
[]

[Postprocessors]
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = phi
    value_type = min
    block = plasma
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = phi
    value_type = max
    block = plasma
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_abs_tol = 1e-12
  nl_rel_tol = 1e-11
[]

[Outputs]
  csv = true
  exodus = true
[]
"""


def _read_w2_phi(epath: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    from scipy.io import netcdf_file
    f = netcdf_file(str(epath), "r", mmap=False)
    conn = f.variables["connect1"].data.copy().astype(int)
    emap = f.variables["elem_num_map"].data.copy().astype(int)[:len(conn)]
    names = _decode_names(f.variables["name_elem_var"].data.copy())
    iv = names.index("phi") + 1
    phi = f.variables[f"vals_elem_var{iv}eb1"].data.copy()[-1].astype(float)
    sidesets = _sidesets_from_exodus(f)
    f.close(); return conn, emap, phi, sidesets


def run_w2(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve(); snapshot = args.snapshot_root.resolve(); out = args.results_root.resolve(); frac = float(args.suppression_fraction)
    if out.exists(): shutil.rmtree(out)
    case = out / "case"; logs = out / "logs"; case.mkdir(parents=True); logs.mkdir()
    ledger = _prepare_w2_source(snapshot, case, frac)
    (case / "input.i").write_text(build_w2_input(), encoding="utf-8")
    p2 = _run_command([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 180)
    summary: dict[str, Any] = {"status": "RUNNING", "ledger": ledger, "p2": p2}
    if p2["returncode"] != 0:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; _write(out / "summary.json", summary); return 1
    rt = _run_command([str(exe), "-i", "input.i"], case, logs / "runtime.log", 300)
    summary["runtime"] = rt
    if rt["returncode"] != 0:
        summary["status"] = "SOLVER_CONVERGENCE_FAIL"; _write(out / "summary.json", summary); return 1
    exo = sorted(case.glob("*_out.e"))
    if len(exo) != 1:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; summary["error"] = f"expected one output e, got {exo}"; _write(out / "summary.json", summary); return 1
    conn, emap, phi, sidesets = _read_w2_phi(exo[0])
    summary["phi_min_V"] = float(phi.min()); summary["phi_max_V"] = float(phi.max()); summary["phi_span_V"] = float(phi.max()-phi.min())
    summary["hotspots"] = _wall_hills(emap, conn, sidesets, phi)
    _c0, _conn0, emap0, vals0, _t0, _ss0 = pgw._load_snapshot(snapshot, 10)
    fv_ref = vals0["potential_plasma"]
    if np.array_equal(emap, emap0):
        err = float(np.max(np.abs(phi - fv_ref)))
    else:
        ref_by_id = {int(e): float(v) for e, v in zip(emap0, fv_ref)}
        err = float(max(abs(float(v)-ref_by_id[int(e)]) for e, v in zip(emap, phi)))
    summary["baseline_reproduction_max_abs_V"] = err
    summary["f0_reference_valid"] = bool(frac != 0.0 or err <= 5.0e-3)
    summary["status"] = "PASS" if summary["f0_reference_valid"] else "VALIDATOR_SELFTEST_FAIL"
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fe"); f.add_argument("--mode", choices=FE_MODES, required=True); f.add_argument("--physics-opt", type=Path, required=True); f.add_argument("--results-root", type=Path, required=True); f.add_argument("--timeout", type=float, default=1800); f.add_argument("--self-test", action="store_true")
    e = sub.add_parser("e1"); e.add_argument("--h-m", type=float, required=True); e.add_argument("--physics-opt", type=Path, required=True); e.add_argument("--results-root", type=Path, required=True)
    w = sub.add_parser("w2"); w.add_argument("--suppression-fraction", type=float, required=True); w.add_argument("--snapshot-root", type=Path, required=True); w.add_argument("--physics-opt", type=Path, required=True); w.add_argument("--results-root", type=Path, required=True)
    a = p.parse_args()
    if a.cmd == "fe" and a.self_test:
        x = fe_self_test(); print(json.dumps(x, indent=2, sort_keys=True)); return 0 if x["status"] == "PASS" else 1
    if a.cmd == "fe": return run_fe(a)
    if a.cmd == "e1": return run_e1(a)
    return run_w2(a)


if __name__ == "__main__":
    raise SystemExit(main())
