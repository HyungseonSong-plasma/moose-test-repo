#!/usr/bin/env python3
"""Issue #228 E2/W3/W4/S1 causal closure campaign.

E2: formal one-cell orthogonal FV wall-loss A/V balance.
W3: remove only wall charge above immediate inward charge reference.
W4: electron-only minimum correction sufficient to remove that excess.
S1: reduced collisionless planar Bohm-sheath reference from governed step-10 fields.
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

from experiments.Issue228_axis_bc_10step import run as axis
from experiments.Issue228_pgw_parallel import run as pgw

EPS0 = pgw.EPS0
E_CHARGE = pgw.E_CHARGE
N_REF = pgw.N_REF
ENERGY_REF_EV = 5.73276
HOTSPOTS = (2401, 2424, 2387)
PHYSICAL_WALLS = {
    "plasma_electrode", "plasma_metal", "plasma_right",
    "plasma_cover", "plasma_wafer", "plasma_focus_ring",
}


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


# E2 -------------------------------------------------------------------------
E2_DT = 1.0e-4
E2_FLUX_MAG = 1.0
E2_INITIAL = 1.0


def build_e2_input(h_m: float) -> str:
    # E1 established that positive FVNeumannBC value acts as an inward source
    # for this scalar balance. Use -Gamma for an outward loss.
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
    initial_condition = {E2_INITIAL:.17g}
  []
[]

[FVKernels]
  [time]
    type = FVTimeKernel
    variable = q
  []
  [diffusion_flux_carrier]
    type = FVDiffusion
    variable = q
    coeff = 1
  []
[]

[FVBCs]
  [right_loss]
    type = FVNeumannBC
    variable = q
    boundary = right
    value = {-E2_FLUX_MAG:.17g}
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
  dt = {E2_DT:.17g}
  end_time = {E2_DT:.17g}
  nl_abs_tol = 1e-13
  nl_rel_tol = 1e-12
[]

[Outputs]
  csv = true
[]
"""


def run_e2(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve(); out = args.results_root.resolve(); h = float(args.h_m)
    if out.exists(): shutil.rmtree(out)
    case = out / "case"; logs = out / "logs"; case.mkdir(parents=True); logs.mkdir()
    (case / "input.i").write_text(build_e2_input(h), encoding="utf-8")
    p2 = _run_command([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 120)
    summary: dict[str, Any] = {
        "status": "RUNNING", "claim": "orthogonal_surface_loss_scales_exactly_with_A_over_V",
        "h_m": h, "A_over_V_1_per_m": 1.0 / h, "dt_s": E2_DT,
        "outward_flux_magnitude": E2_FLUX_MAG, "moose_neumann_value": -E2_FLUX_MAG, "p2": p2,
    }
    if p2["returncode"] != 0:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; _write(out / "summary.json", summary); return 1
    rt = _run_command([str(exe), "-i", "input.i"], case, logs / "runtime.log", 120)
    summary["runtime"] = rt
    if rt["returncode"] != 0 or rt["timed_out"]:
        summary["status"] = "SOLVER_CONVERGENCE_FAIL"; _write(out / "summary.json", summary); return 1
    csvs = sorted(case.glob("*.csv"))
    if len(csvs) != 1:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; summary["error"] = f"expected one csv, got {csvs}"; _write(out / "summary.json", summary); return 1
    with csvs[0].open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; summary["error"] = f"too few rows: {rows}"; _write(out / "summary.json", summary); return 1
    q0 = float(rows[0]["q_avg"]); q1 = float(rows[-1]["q_avg"])
    expected_loss = E2_FLUX_MAG * E2_DT / h
    expected = E2_INITIAL - expected_loss
    ratio = (E2_INITIAL - q1) / expected_loss
    summary.update({"q_initial": q0, "q_final": q1, "q_expected": expected,
                    "expected_loss": expected_loss, "absolute_error": abs(q1 - expected),
                    "normalized_loss_ratio": ratio})
    summary["status"] = "PASS" if abs(q1 - expected) <= 1e-9 and abs(ratio - 1.0) <= 1e-9 else "VALIDATOR_SELFTEST_FAIL"
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


# W3 / W4 --------------------------------------------------------------------
def _frozen_fv_input() -> str:
    return f"""[Problem]
  kernel_coverage_check = ONLY_LIST
  kernel_coverage_block_list = plasma
[]

[Mesh]
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


def _wall_reference_arrays(rhoq: np.ndarray, ne: np.ndarray, conn: np.ndarray, sidesets):
    wall, neigh = pgw._wall_cells_and_neighbors(conn, sidesets)
    rho_ref = np.full(len(rhoq), np.nan); ne_ref = np.full(len(ne), np.nan)
    for i in sorted(wall):
        js = sorted(neigh.get(i, set()))
        if not js: continue
        rho_ref[i] = float(np.mean(rhoq[js])); ne_ref[i] = float(np.mean(ne[js]))
    return wall, neigh, rho_ref, ne_ref


def _prepare_source(snapshot: Path, work: Path, mode: str) -> dict[str, Any]:
    from scipy.io import netcdf_file
    coords, conn, emap, vals, t, sidesets = pgw._load_snapshot(snapshot, 10)
    rhoq = pgw._charge_density(vals); _tri, _area, _rcent, vol = pgw._geom(coords, conn)
    ne = N_REF * vals["n_e"]
    wall, neigh, rho_ref, ne_ref = _wall_reference_arrays(rhoq, ne, conn, sidesets)
    rho_used = rhoq.copy(); removed = 0.0; used = 0; hotspot_diag: dict[str, Any] = {}
    for i in sorted(wall):
        if not np.isfinite(rho_ref[i]): continue
        excess = max(float(rhoq[i] - rho_ref[i]), 0.0)
        if excess <= 0.0: continue
        electron_deficit = max(float(ne_ref[i] - ne[i]), 0.0) if np.isfinite(ne_ref[i]) else 0.0
        electron_capacity = E_CHARGE * electron_deficit
        if mode == "w3_excess": correction = excess
        elif mode == "w4_electron": correction = min(excess, electron_capacity)
        else: raise ValueError(mode)
        if correction <= 0.0: continue
        rho_used[i] -= correction; dq = correction * vol[i]; removed += dq; used += 1
        eid = int(emap[i])
        if eid in HOTSPOTS:
            hotspot_diag[str(eid)] = {
                "rho_q_wall_C_m3": float(rhoq[i]), "rho_q_inward_reference_C_m3": float(rho_ref[i]),
                "positive_excess_C_m3": excess, "n_e_wall_m3": float(ne[i]),
                "n_e_inward_reference_m3": float(ne_ref[i]), "electron_deficit_m3": electron_deficit,
                "electron_deficit_charge_capacity_C_m3": electron_capacity,
                "applied_correction_C_m3": correction,
                "fraction_of_electron_deficit_restored": correction / electron_capacity if electron_capacity > 0 else None,
                "inward_neighbor_element_ids": [int(emap[j]) for j in sorted(neigh[i])],
            }
    source = rho_used / EPS0
    src_e = work / "source.e"; shutil.copy2(snapshot / "case" / "input_out.e", src_e)
    f = netcdf_file(str(src_e), "a", mmap=False)
    names = _decode_names(f.variables["name_elem_var"].data.copy()); iv = names.index("potential_plasma") + 1
    v = f.variables[f"vals_elem_var{iv}eb1"]; data = v.data.copy(); data[:] = source[np.newaxis, :]; v[:] = data
    f.flush(); f.close()
    before = float(np.dot(rhoq, vol)); after = float(np.dot(rho_used, vol))
    return {"mode": mode, "time_s": t, "wall_cells": len(wall), "corrected_wall_cells": used,
            "removed_volume_charge_C": float(removed), "volume_charge_before_C": before,
            "volume_charge_after_C": after, "diagnostic_sheath_reservoir_C": float(removed),
            "ledger_total_C": float(after + removed), "ledger_defect_C": float(abs(after + removed - before)),
            "hotspots": hotspot_diag}


def _read_fv_phi(epath: Path):
    from scipy.io import netcdf_file
    f = netcdf_file(str(epath), "r", mmap=False)
    conn = f.variables["connect1"].data.copy().astype(int)
    emap = f.variables["elem_num_map"].data.copy().astype(int)[:len(conn)]
    names = _decode_names(f.variables["name_elem_var"].data.copy()); iv = names.index("phi") + 1
    phi = f.variables[f"vals_elem_var{iv}eb1"].data.copy()[-1].astype(float)
    ss_names = _decode_names(f.variables["ss_names"].data.copy())
    sidesets = [(name, f.variables[f"elem_ss{i}"].data.copy().astype(int), f.variables[f"side_ss{i}"].data.copy().astype(int))
                for i, name in enumerate(ss_names, 1)]
    f.close(); return conn, emap, phi, sidesets


def _wall_hills(emap: np.ndarray, conn: np.ndarray, sidesets, phi: np.ndarray) -> dict[str, Any]:
    _wall, neigh = pgw._wall_cells_and_neighbors(conn, sidesets); out: dict[str, Any] = {}
    for eid in HOTSPOTS:
        hit = np.where(emap == eid)[0]
        if len(hit) != 1: continue
        i = int(hit[0]); js = sorted(neigh.get(i, set()))
        if not js: continue
        inward = float(np.mean(phi[js]))
        out[str(eid)] = {"wall_cell_phi_V": float(phi[i]), "inward_neighbor_mean_phi_V": inward,
                         "H_wall_minus_inward_V": float(phi[i] - inward),
                         "inward_neighbor_element_ids": [int(emap[j]) for j in js]}
    return out


def run_w(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve(); snapshot = args.snapshot_root.resolve(); out = args.results_root.resolve(); mode = args.mode
    if out.exists(): shutil.rmtree(out)
    case = out / "case"; logs = out / "logs"; case.mkdir(parents=True); logs.mkdir()
    ledger = _prepare_source(snapshot, case, mode); (case / "input.i").write_text(_frozen_fv_input(), encoding="utf-8")
    p2 = _run_command([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 180)
    summary: dict[str, Any] = {"status": "RUNNING", "claim": "physics_derived_wall_charge_ownership", "ledger": ledger, "p2": p2}
    if p2["returncode"] != 0:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; _write(out / "summary.json", summary); return 1
    rt = _run_command([str(exe), "-i", "input.i"], case, logs / "runtime.log", 300); summary["runtime"] = rt
    if rt["returncode"] != 0 or rt["timed_out"]:
        summary["status"] = "SOLVER_CONVERGENCE_FAIL"; _write(out / "summary.json", summary); return 1
    exo = sorted(case.glob("*_out.e"))
    if len(exo) != 1:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; summary["error"] = f"expected one output e, got {exo}"; _write(out / "summary.json", summary); return 1
    conn, emap, phi, sidesets = _read_fv_phi(exo[0])
    summary.update({"phi_min_V": float(phi.min()), "phi_max_V": float(phi.max()), "phi_span_V": float(phi.max() - phi.min()),
                    "phi_max_element_id": int(emap[int(np.argmax(phi))]), "hotspots": _wall_hills(emap, conn, sidesets, phi)})
    summary["all_hotspot_hills_removed"] = all(v["H_wall_minus_inward_V"] <= 0.0 for v in summary["hotspots"].values())
    summary["status"] = "PASS"; _write(out / "summary.json", summary); return 0


# S1 -------------------------------------------------------------------------
def _physical_side_av(coords: np.ndarray, conn: np.ndarray, emap: np.ndarray, sidesets, eid: int):
    side_nodes = {1: (0, 1), 2: (1, 2), 3: (2, 0)}; hits = np.where(emap == eid)[0]
    if len(hits) != 1: return None
    i = int(hits[0]); tri = coords[conn[i] - 1]; a = tri[1] - tri[0]; b = tri[2] - tri[0]
    area = abs(a[0] * b[1] - a[1] * b[0]) / 2.0; rcent = float(np.mean(tri[:, 0]))
    for name, elems, sides in sidesets:
        if name not in PHYSICAL_WALLS: continue
        for eidx, side in zip(elems, sides):
            if int(eidx - 1) != i: continue
            ia, ib = side_nodes[int(side)]; p1, p2 = tri[ia], tri[ib]
            length = float(np.linalg.norm(p2 - p1)); rface = float(0.5 * (p1[0] + p2[0]))
            return length * rface / (area * rcent)
    return None


def _s1_profile(ne_s: float, mean_energy_eV: float, phi_s: float, psi_edge: float = 0.1, npts: int = 2001):
    from scipy.integrate import cumulative_trapezoid, trapezoid
    te_eV = (2.0 / 3.0) * mean_energy_eV
    if ne_s <= 0 or te_eV <= 0 or phi_s <= 0: raise ValueError((ne_s, mean_energy_eV, phi_s))
    lambda_D = math.sqrt(EPS0 * te_eV / (E_CHARGE * ne_s)); psi_wall = phi_s / te_eV
    if psi_wall <= psi_edge: raise ValueError(f"wall normalized drop {psi_wall} <= edge criterion {psi_edge}")
    psi = np.linspace(psi_edge, psi_wall, npts)
    energy_integral = np.sqrt(1.0 + 2.0 * psi) + np.exp(-psi) - 2.0
    F = np.sqrt(np.maximum(2.0 * energy_integral, 1e-300)); dx_dpsi = lambda_D / F
    x = cumulative_trapezoid(dx_dpsi, psi, initial=0.0)
    ne = ne_s * np.exp(-psi); ni = ne_s / np.sqrt(1.0 + 2.0 * psi); rhoq = E_CHARGE * (ni - ne)
    phi = phi_s - te_eV * psi; Ewallward = te_eV / lambda_D * F
    qnum = float(trapezoid(rhoq, x)); qgauss = float(EPS0 * (Ewallward[-1] - Ewallward[0]))
    rel = abs(qnum - qgauss) / max(abs(qgauss), 1e-300)
    return {"te_eV_maxwellian_equivalent": te_eV, "lambda_D_m": lambda_D, "psi_edge": psi_edge,
            "psi_wall": psi_wall, "strong_sheath_thickness_m": float(x[-1]),
            "strong_sheath_thickness_over_lambda_D": float(x[-1] / lambda_D),
            "wall_field_V_m": float(Ewallward[-1]), "edge_field_at_criterion_V_m": float(Ewallward[0]),
            "surface_charge_numeric_C_m2": qnum, "surface_charge_gauss_C_m2": qgauss,
            "surface_charge_rel_defect": rel, "monotonic_phi": bool(np.all(np.diff(phi) < 0.0)),
            "_profile": {"x_m": x, "psi": psi, "phi_V": phi, "n_e_m3": ne, "n_i_m3": ni,
                         "rho_q_C_m3": rhoq, "E_wallward_V_m": Ewallward}}


def run_s1(args: argparse.Namespace) -> int:
    snapshot = args.snapshot_root.resolve(); out = args.results_root.resolve()
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    coords, conn, emap, vals, t, sidesets = pgw._load_snapshot(snapshot, 10)
    rhoq = pgw._charge_density(vals); ne = N_REF * vals["n_e"]; meanE = ENERGY_REF_EV * vals["n_epsilon"] / vals["n_e"]
    _wall, neigh = pgw._wall_cells_and_neighbors(conn, sidesets)
    summary: dict[str, Any] = {"status": "RUNNING", "claim": "debye_resolved_reduced_bohm_sheath_reference", "time_s": t,
        "model": {"electron": "Boltzmann", "ion": "cold collisionless Bohm ion, n_i/n_s=(1+2 psi)^-1/2",
                  "mean_energy_to_temperature": "T_e[eV]=(2/3)*mean_energy[eV]",
                  "strong_sheath_edge_definition": "psi=e*(phi_s-phi)/(kT_e)=0.1",
                  "note": "reduced planar reference; not a production closure"}, "hotspots": {}}
    all_pass = True
    for eid in HOTSPOTS:
        hit = np.where(emap == eid)[0]
        if len(hit) != 1: all_pass = False; continue
        i = int(hit[0]); js = sorted(neigh.get(i, set()))
        if not js: all_pass = False; continue
        ne_s = float(np.mean(ne[js])); mean_energy = float(np.mean(meanE[js])); phi_s = float(np.mean(vals["potential_plasma"][js]))
        rho_ref = float(np.mean(rhoq[js])); excess = max(float(rhoq[i] - rho_ref), 0.0); av = _physical_side_av(coords, conn, emap, sidesets, eid)
        profile = _s1_profile(ne_s, mean_energy, phi_s); pdata = profile.pop("_profile")
        with (out / f"sheath_profile_{eid}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle); writer.writerow(["x_m", "psi", "phi_V", "n_e_m3", "n_i_m3", "rho_q_C_m3", "E_wallward_V_m"])
            for row in zip(pdata["x_m"], pdata["psi"], pdata["phi_V"], pdata["n_e_m3"], pdata["n_i_m3"], pdata["rho_q_C_m3"], pdata["E_wallward_V_m"]):
                writer.writerow([f"{float(x):.17g}" for x in row])
        coarse_sigma = float(excess / av) if av and av > 0 else None; cell_depth = float(1.0 / av) if av and av > 0 else None
        entry = {"inward_neighbor_element_ids": [int(emap[j]) for j in js], "n_e_s_m3": ne_s, "mean_energy_s_eV": mean_energy,
                 "phi_s_V": phi_s, "rho_q_wall_C_m3": float(rhoq[i]), "rho_q_inward_reference_C_m3": rho_ref,
                 "wall_positive_excess_C_m3": excess, "wall_A_over_V_1_per_m": av,
                 "effective_first_cell_depth_m": cell_depth, "coarse_excess_surface_equivalent_C_m2": coarse_sigma, **profile}
        if cell_depth:
            entry["cell_depth_over_lambda_D"] = cell_depth / profile["lambda_D_m"]
            entry["cell_depth_over_strong_sheath_thickness"] = cell_depth / profile["strong_sheath_thickness_m"]
        if coarse_sigma:
            entry["reference_surface_charge_over_coarse_excess"] = profile["surface_charge_gauss_C_m2"] / coarse_sigma
        summary["hotspots"][str(eid)] = entry
        all_pass = all_pass and profile["monotonic_phi"] and profile["surface_charge_rel_defect"] <= 1e-3
    summary["status"] = "PASS" if all_pass and len(summary["hotspots"]) == len(HOTSPOTS) else "PHYSICS_MODEL_FAIL"
    _write(out / "summary.json", summary); return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("e2"); e.add_argument("--h-m", type=float, required=True); e.add_argument("--physics-opt", type=Path, required=True); e.add_argument("--results-root", type=Path, required=True)
    w = sub.add_parser("w"); w.add_argument("--mode", choices=("w3_excess", "w4_electron"), required=True); w.add_argument("--snapshot-root", type=Path, required=True); w.add_argument("--physics-opt", type=Path, required=True); w.add_argument("--results-root", type=Path, required=True)
    s = sub.add_parser("s1"); s.add_argument("--snapshot-root", type=Path, required=True); s.add_argument("--results-root", type=Path, required=True)
    a = p.parse_args()
    if a.cmd == "e2": return run_e2(a)
    if a.cmd == "w": return run_w(a)
    return run_s1(a)


if __name__ == "__main__":
    raise SystemExit(main())
