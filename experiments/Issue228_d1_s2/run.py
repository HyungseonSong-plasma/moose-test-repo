#!/usr/bin/env python3
"""Issue #228 D1/S2 causal-closure campaign.

D1
--
Decompose the governed step-10 wall charge anomaly by species and compare each
physical-wall cell with its immediate inward reference.

S2
--
Frozen-Poisson 2x2 ownership factorial:

  source ownership: raw | wall-excess-corrected
  wall ownership:   physical-wall Dirichlet | sheath-edge flux + gauge constraint

The sheath-edge flux branch is diagnostic-only.  It uses the *shape* of the S1
reduced Bohm-sheath edge field (psi_edge=0.1) but applies one global scale factor
so that the prescribed physical-wall flux exactly satisfies the frozen bulk
Gauss compatibility condition.  The scale factor is evidence, not a production
closure.  The absolute potential nullspace is removed by constraining the
volume-average phi to the governed non-wall baseline mean; this only fixes the
gauge and does not prescribe wall-normal differences.
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
NA = pgw.NA
R_GAS = pgw.R_GAS
TG_K = pgw.TG_K
N_REF = pgw.N_REF
ENERGY_REF_EV = 5.73276
HOTSPOTS = (2401, 2424, 2387)
PHYSICAL_WALLS = (
    "plasma_electrode", "plasma_metal", "plasma_right",
    "plasma_cover", "plasma_wafer", "plasma_focus_ring",
)
S2_MODES = (
    "dirichlet_raw", "dirichlet_excess",
    "neumann_raw", "neumann_excess",
)
PSI_EDGE = 0.1


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run(cmd: list[str], cwd: Path, log: Path, timeout: float) -> dict[str, Any]:
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, check=False)
        log.write_text(p.stdout or "", encoding="utf-8")
        return {"returncode": int(p.returncode), "timed_out": False,
                "command": cmd, "log": str(log)}
    except subprocess.TimeoutExpired as exc:
        text = exc.stdout if isinstance(exc.stdout, str) else ""
        log.write_text(text or "", encoding="utf-8")
        return {"returncode": 124, "timed_out": True, "command": cmd, "log": str(log)}


def _decode_names(a) -> list[str]:
    return [bytes(row).split(b"\0")[0].decode(errors="ignore").strip() for row in a]


def _species_charge(vals: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    p = vals["p"]
    wO = vals["w_O"]; wO2p = vals["w_O2p"]; wO2s = vals["w_O2s"]
    wOm = vals["w_Om"]; wOp = vals["w_Op"]; wOs = vals["w_Os"]
    wO2 = 1.0 - (wO2p + wO2s + wO + wOm + wOp + wOs)
    Mn = 1.0 / (wO2 / 0.032 + wO2s / 0.032 + wO2p / 0.032 +
                wO / 0.016 + wOm / 0.016 + wOp / 0.016 + wOs / 0.016)
    rho = p * Mn / (R_GAS * TG_K)
    out = {
        "O2p": E_CHARGE * rho * wO2p * NA / 0.032,
        "Op": E_CHARGE * rho * wOp * NA / 0.016,
        "Om": -E_CHARGE * rho * wOm * NA / 0.016,
        "electron": -E_CHARGE * N_REF * vals["n_e"],
    }
    out["net"] = out["O2p"] + out["Op"] + out["Om"] + out["electron"]
    return out


def _wall_refs(arr: np.ndarray, conn: np.ndarray, sidesets):
    wall, neigh = pgw._wall_cells_and_neighbors(conn, sidesets)
    ref = np.full(len(arr), np.nan)
    for i in sorted(wall):
        js = sorted(neigh.get(i, set()))
        if js:
            ref[i] = float(np.mean(arr[js]))
    return wall, neigh, ref


def _geom(coords: np.ndarray, conn: np.ndarray):
    tri = coords[conn - 1]
    a = tri[:, 1] - tri[:, 0]; b = tri[:, 2] - tri[:, 0]
    area = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) / 2.0
    rcent = tri[:, :, 0].mean(axis=1)
    vol = 2.0 * math.pi * area * rcent
    return tri, area, rcent, vol


def _physical_faces(coords: np.ndarray, conn: np.ndarray, sidesets):
    side_nodes = {1: (0, 1), 2: (1, 2), 3: (2, 0)}
    faces = []
    for name, elems, sides in sidesets:
        if name not in PHYSICAL_WALLS:
            continue
        for e, s in zip(elems, sides):
            i = int(e - 1)
            if not (0 <= i < len(conn)):
                continue
            tri = coords[conn[i] - 1]
            ia, ib = side_nodes[int(s)]
            p1, p2 = tri[ia], tri[ib]
            length = float(np.linalg.norm(p2 - p1))
            rface = float(0.5 * (p1[0] + p2[0]))
            face_area = 2.0 * math.pi * length * rface
            faces.append((name, i, face_area))
    return faces


def _edge_field_shape(ne_s: float, mean_energy_eV: float) -> float:
    te_eV = (2.0 / 3.0) * mean_energy_eV
    if ne_s <= 0.0 or te_eV <= 0.0:
        return 0.0
    lam = math.sqrt(EPS0 * te_eV / (E_CHARGE * ne_s))
    energy_integral = math.sqrt(1.0 + 2.0 * PSI_EDGE) + math.exp(-PSI_EDGE) - 2.0
    F = math.sqrt(max(2.0 * energy_integral, 0.0))
    return te_eV / lam * F


def run_d1(args: argparse.Namespace) -> int:
    root = args.snapshot_root.resolve(); out = args.results_root.resolve()
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    coords, conn, emap, vals, t, sidesets = pgw._load_snapshot(root, 10)
    species = _species_charge(vals)
    reference = pgw._charge_density(vals)
    reconstruction_abs = float(np.max(np.abs(species["net"] - reference)))
    reconstruction_scale = max(float(np.max(np.abs(reference))), 1e-300)
    reconstruction_rel = reconstruction_abs / reconstruction_scale
    wall, neigh, net_ref = _wall_refs(species["net"], conn, sidesets)
    refs = {}
    for sp in ("O2p", "Op", "Om", "electron"):
        _w, _n, refs[sp] = _wall_refs(species[sp], conn, sidesets)

    rows = []
    hotspot = {}
    electron_delta_all = []
    net_delta_all = []
    for i in sorted(wall):
        if not np.isfinite(net_ref[i]):
            continue
        eid = int(emap[i])
        delta = {sp: float(species[sp][i] - refs[sp][i]) for sp in ("O2p", "Op", "Om", "electron")}
        net_delta = float(species["net"][i] - net_ref[i])
        heavy_delta = delta["O2p"] + delta["Op"] + delta["Om"]
        electron_delta = delta["electron"]
        record = {
            "element_id": eid,
            "rho_net_wall_C_m3": float(species["net"][i]),
            "rho_net_inward_C_m3": float(net_ref[i]),
            "net_excess_delta_C_m3": net_delta,
            "O2p_delta_C_m3": delta["O2p"],
            "Op_delta_C_m3": delta["Op"],
            "Om_delta_C_m3": delta["Om"],
            "electron_delta_C_m3": electron_delta,
            "heavy_species_delta_C_m3": heavy_delta,
            "electron_to_net_ratio": electron_delta / net_delta if abs(net_delta) > 0 else None,
            "heavy_cancellation_fraction_of_electron": -heavy_delta / electron_delta if abs(electron_delta) > 0 else None,
            "net_fraction_of_electron": net_delta / electron_delta if abs(electron_delta) > 0 else None,
            "inward_neighbor_element_ids": [int(emap[j]) for j in sorted(neigh.get(i, set()))],
        }
        rows.append(record)
        if net_delta > 0 and electron_delta > 0:
            electron_delta_all.append(electron_delta); net_delta_all.append(net_delta)
        if eid in HOTSPOTS:
            hotspot[str(eid)] = record

    with (out / "wall_species_decomposition.csv").open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader(); writer.writerows(rows)

    corr = None; slope = None
    if len(electron_delta_all) >= 2:
        x = np.asarray(electron_delta_all); y = np.asarray(net_delta_all)
        corr = float(np.corrcoef(x, y)[0, 1])
        slope = float(np.dot(x, y) / np.dot(x, x))
    summary = {
        "status": "PASS" if reconstruction_rel <= 1e-12 and len(hotspot) == len(HOTSPOTS) else "VALIDATOR_SELFTEST_FAIL",
        "claim": "wall_charge_species_cancellation_decomposition",
        "time_s": t,
        "net_charge_reconstruction_max_abs_C_m3": reconstruction_abs,
        "net_charge_reconstruction_relative": reconstruction_rel,
        "positive_excess_wall_cells_used_for_fit": len(electron_delta_all),
        "corr_electron_delta_vs_net_excess": corr,
        "least_squares_net_over_electron_slope": slope,
        "hotspots": hotspot,
    }
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def _prepare_s2_source(snapshot: Path, work: Path, mode: str) -> dict[str, Any]:
    from scipy.io import netcdf_file
    if mode not in S2_MODES: raise ValueError(mode)
    coords, conn, emap, vals, t, sidesets = pgw._load_snapshot(snapshot, 10)
    species = _species_charge(vals); rho_raw = species["net"]
    tri, area, rcent, vol = _geom(coords, conn)
    wall, neigh, rho_ref = _wall_refs(rho_raw, conn, sidesets)
    rho_use = rho_raw.copy()
    removed_C = 0.0
    if mode.endswith("excess"):
        for i in sorted(wall):
            if not np.isfinite(rho_ref[i]): continue
            excess = max(float(rho_raw[i] - rho_ref[i]), 0.0)
            if excess > 0.0:
                rho_use[i] -= excess
                removed_C += excess * vol[i]

    meanE = ENERGY_REF_EV * vals["n_epsilon"] / vals["n_e"]
    ne = N_REF * vals["n_e"]
    faces = _physical_faces(coords, conn, sidesets)
    edge_raw = np.zeros(len(conn))
    weighted_raw = 0.0
    physical_area = 0.0
    for _name, i, face_area in faces:
        js = sorted(neigh.get(i, set()))
        if js:
            ne_s = float(np.mean(ne[js])); me_s = float(np.mean(meanE[js]))
        else:
            ne_s = float(ne[i]); me_s = float(meanE[i])
        eedge = _edge_field_shape(ne_s, me_s)
        edge_raw[i] = max(edge_raw[i], eedge)
        weighted_raw += face_area * eedge
        physical_area += face_area

    Q_use = float(np.dot(rho_use, vol))
    target_integral_E = Q_use / EPS0
    scale = target_integral_E / weighted_raw if weighted_raw > 0 else 0.0
    edge_scaled = edge_raw * scale
    weighted_scaled = 0.0
    for _name, i, face_area in faces:
        weighted_scaled += face_area * edge_scaled[i]
    compatibility = abs(weighted_scaled - target_integral_E) / max(abs(target_integral_E), 1e-300)

    nonwall = np.asarray([i for i in range(len(conn)) if i not in wall], dtype=int)
    phi0 = float(np.dot(vals["potential_plasma"][nonwall], vol[nonwall]) / np.sum(vol[nonwall]))

    src_e = work / "source.e"
    shutil.copy2(snapshot / "case" / "input_out.e", src_e)
    f = netcdf_file(str(src_e), "a", mmap=False)
    names = _decode_names(f.variables["name_elem_var"].data.copy())
    iv_src = names.index("potential_plasma") + 1
    iv_flux = names.index("u") + 1
    vsrc = f.variables[f"vals_elem_var{iv_src}eb1"]; dsrc = vsrc.data.copy(); dsrc[:] = (rho_use / EPS0)[np.newaxis, :]; vsrc[:] = dsrc
    vflux = f.variables[f"vals_elem_var{iv_flux}eb1"]; dflux = vflux.data.copy(); dflux[:] = edge_scaled[np.newaxis, :]; vflux[:] = dflux
    f.flush(); f.close()

    return {
        "mode": mode, "time_s": t,
        "volume_charge_raw_C": float(np.dot(rho_raw, vol)),
        "volume_charge_used_C": Q_use,
        "removed_wall_excess_C": float(removed_C),
        "physical_wall_area_m2": float(physical_area),
        "s1_edge_shape_integral_A_V": float(weighted_raw),
        "required_gauss_integral_A_V": float(target_integral_E),
        "edge_field_global_scale": float(scale),
        "scaled_edge_integral_A_V": float(weighted_scaled),
        "gauss_compatibility_relative_defect": float(compatibility),
        "gauge_target_nonwall_volume_mean_phi_V": phi0,
        "psi_edge_shape": PSI_EDGE,
        "edge_field_shape_is_diagnostic_only": True,
    }


def _s2_input(mode: str, phi0: float) -> str:
    use_neumann = mode.startswith("neumann")
    gauge = "" if not use_neumann else f"""
  [lambda]
    type = MooseVariableScalar
  []"""
    constraint = "" if not use_neumann else f"""
  [mean_phi_gauge]
    type = FVIntegralValueConstraint
    variable = phi
    lambda = lambda
    phi0 = {phi0:.17g}
    block = plasma
  []"""
    bc = f"""
  [ground]
    type = FVDirichletBC
    variable = phi
    boundary = {axis.GROUND_NONAXIS}
    value = 0
  []""" if not use_neumann else f"""
  [sheath_edge_flux]
    type = FVFunctorNeumannBC
    variable = phi
    boundary = '{' '.join(PHYSICAL_WALLS)}'
    functor = edge_flux
    factor = -1
  []"""
    petsc = "" if not use_neumann else """
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'"""
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
    initial_condition = {phi0:.17g}
    block = plasma
  []{gauge}
[]

[AuxVariables]
  [frozen_source]
    family = MONOMIAL
    order = CONSTANT
    block = plasma
  []
  [edge_flux]
    family = MONOMIAL
    order = CONSTANT
    block = plasma
  []
[]

[UserObjects]
  [frozen_solution]
    type = SolutionUserObject
    mesh = source.e
    system_variables = 'potential_plasma u'
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
  [import_edge_flux]
    type = SolutionAux
    variable = edge_flux
    solution = frozen_solution
    from_variable = u
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
  []{constraint}
[]

[FVBCs]{bc}
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
  nl_rel_tol = 1e-11{petsc}
[]

[Outputs]
  csv = true
  exodus = true
[]
"""


def _read_phi(epath: Path):
    from scipy.io import netcdf_file
    f = netcdf_file(str(epath), "r", mmap=False)
    conn = f.variables["connect1"].data.copy().astype(int)
    emap = f.variables["elem_num_map"].data.copy().astype(int)[:len(conn)]
    names = _decode_names(f.variables["name_elem_var"].data.copy())
    iv = names.index("phi") + 1
    phi = f.variables[f"vals_elem_var{iv}eb1"].data.copy()[-1].astype(float)
    ss_names = _decode_names(f.variables["ss_names"].data.copy())
    sidesets = [(name, f.variables[f"elem_ss{i}"].data.copy().astype(int), f.variables[f"side_ss{i}"].data.copy().astype(int))
                for i, name in enumerate(ss_names, 1)]
    f.close()
    return conn, emap, phi, sidesets


def _hotspots(emap: np.ndarray, conn: np.ndarray, sidesets, phi: np.ndarray):
    _wall, neigh = pgw._wall_cells_and_neighbors(conn, sidesets)
    out = {}
    for eid in HOTSPOTS:
        hit = np.where(emap == eid)[0]
        if len(hit) != 1: continue
        i = int(hit[0]); js = sorted(neigh.get(i, set()))
        if not js: continue
        inward = float(np.mean(phi[js]))
        out[str(eid)] = {
            "wall_cell_phi_V": float(phi[i]),
            "inward_neighbor_mean_phi_V": inward,
            "H_wall_minus_inward_V": float(phi[i] - inward),
            "inward_neighbor_element_ids": [int(emap[j]) for j in js],
        }
    return out


def run_s2(args: argparse.Namespace) -> int:
    mode = args.mode; exe = args.physics_opt.resolve(); snapshot = args.snapshot_root.resolve(); out = args.results_root.resolve()
    if mode not in S2_MODES: raise ValueError(mode)
    if out.exists(): shutil.rmtree(out)
    case = out / "case"; logs = out / "logs"; case.mkdir(parents=True); logs.mkdir()
    prep = _prepare_s2_source(snapshot, case, mode)
    text = _s2_input(mode, prep["gauge_target_nonwall_volume_mean_phi_V"])
    (case / "input.i").write_text(text, encoding="utf-8")
    p2 = _run([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 180)
    summary: dict[str, Any] = {"status": "RUNNING", "claim": "bulk_sheath_ownership_factorial", "mode": mode, "preparation": prep, "p2": p2}
    if p2["returncode"] != 0:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; _write(out / "summary.json", summary); return 1
    rt = _run([str(exe), "-i", "input.i"], case, logs / "runtime.log", 600); summary["runtime"] = rt
    if rt["returncode"] != 0 or rt["timed_out"]:
        summary["status"] = "SOLVER_CONVERGENCE_FAIL"; _write(out / "summary.json", summary); return 1
    exo = sorted(case.glob("*_out.e"))
    if len(exo) != 1:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; summary["error"] = f"expected one output Exodus, got {exo}"; _write(out / "summary.json", summary); return 1
    conn, emap, phi, sidesets = _read_phi(exo[0])
    hs = _hotspots(emap, conn, sidesets, phi)
    summary.update({
        "phi_min_V": float(phi.min()), "phi_max_V": float(phi.max()), "phi_span_V": float(phi.max() - phi.min()),
        "phi_max_element_id": int(emap[int(np.argmax(phi))]), "hotspots": hs,
        "all_hotspot_hills_removed": len(hs) == len(HOTSPOTS) and all(v["H_wall_minus_inward_V"] <= 0 for v in hs.values()),
    })
    if mode == "dirichlet_raw":
        _c, _co, em0, vals0, _t, _ss = pgw._load_snapshot(snapshot, 10)
        ref = vals0["potential_plasma"]
        by = {int(e): float(v) for e, v in zip(em0, ref)}
        summary["baseline_reproduction_max_abs_V"] = float(max(abs(float(v) - by[int(e)]) for e, v in zip(emap, phi)))
        if summary["baseline_reproduction_max_abs_V"] > 5e-3:
            summary["status"] = "VALIDATOR_SELFTEST_FAIL"; _write(out / "summary.json", summary); return 1
    if mode.startswith("neumann") and prep["gauss_compatibility_relative_defect"] > 1e-10:
        summary["status"] = "VALIDATOR_SELFTEST_FAIL"; _write(out / "summary.json", summary); return 1
    summary["status"] = "PASS"; _write(out / "summary.json", summary); return 0


def main() -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("d1"); d.add_argument("--snapshot-root", type=Path, required=True); d.add_argument("--results-root", type=Path, required=True)
    s = sub.add_parser("s2"); s.add_argument("--mode", choices=S2_MODES, required=True); s.add_argument("--snapshot-root", type=Path, required=True); s.add_argument("--physics-opt", type=Path, required=True); s.add_argument("--results-root", type=Path, required=True)
    a = p.parse_args()
    return run_d1(a) if a.cmd == "d1" else run_s2(a)


if __name__ == "__main__":
    raise SystemExit(main())
