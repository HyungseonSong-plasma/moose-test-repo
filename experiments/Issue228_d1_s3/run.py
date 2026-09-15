#!/usr/bin/env python3
"""Issue #228 D1 validator correction + S3 frozen sheath-edge closure campaign.

D1r
----
Re-run the D1 species decomposition with a roundoff-aware reconstruction
validator.  No scientific axis changes relative to D1.

S3
--
Frozen-Poisson discriminator for bulk/sheath ownership after S2 rejected a
prescribed Neumann edge-field closure.

All S3 modes use the W3-style excess-corrected bulk charge.  The scientific
axis is the physical-wall electrostatic boundary value seen by the bulk:

  control_zero      : physical wall 0 V (reproduces W3 / S2 dirichlet_excess)
  inward_reference  : one constant sheath-edge value per physical wall equal
                      to the governed baseline inward-reference potential
  current_balance   : one constant sheath-edge value per physical wall found
                      from a nonlinear Maxwellian electron-current closure
                      calibrated to the governed production wall-current ledger

In current_balance the physical wall remains V_w=0 only inside the sheath
closure.  Bulk FV Poisson sees phi_s, not V_w.  Frozen n_e, T_e and ion wall
rates make this a nonlinear scalar root per wall rather than a coupled PDE
fixed point.  A true Poisson/sheath fixed point is only meaningful once those
states evolve in a coupled run.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import brentq

from experiments.Issue228_d1_s2 import run as d1s2
from experiments.Issue228_pgw_parallel import run as pgw

EPS0 = pgw.EPS0
E_CHARGE = pgw.E_CHARGE
NA = pgw.NA
N_REF = pgw.N_REF
ENERGY_REF_EV = 5.73276
M_E = 9.1093837139e-31
FARADAY = E_CHARGE * NA
HOTSPOTS = d1s2.HOTSPOTS
PHYSICAL_WALLS = d1s2.PHYSICAL_WALLS
S3_MODES = ("control_zero", "inward_reference", "current_balance")


def _write(path: Path, payload: Any) -> None:
    d1s2._write(path, payload)


def run_d1r(args: argparse.Namespace) -> int:
    """D1 with roundoff-aware charge reconstruction acceptance."""
    root = args.snapshot_root.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    # Re-use the governed D1 calculation, then correct only the validator.
    _ = d1s2.run_d1(args)
    summary_path = out / "summary.json"
    if not summary_path.exists():
        raise RuntimeError("D1 did not emit summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    _coords, _conn, _emap, vals, _t, _sidesets = pgw._load_snapshot(root, 10)
    species = d1s2._species_charge(vals)
    component_scale = float(np.max(
        np.abs(species["O2p"]) + np.abs(species["Op"]) +
        np.abs(species["Om"]) + np.abs(species["electron"])
    ))
    eps = float(np.finfo(float).eps)
    roundoff_abs_tol = max(1.0e-15, 128.0 * eps * component_scale)
    reconstruction_abs = float(summary["net_charge_reconstruction_max_abs_C_m3"])
    hotspot_count = len(summary.get("hotspots", {}))
    checks = {
        "roundoff_aware_reconstruction": reconstruction_abs <= roundoff_abs_tol,
        "all_hotspots_present": hotspot_count == len(HOTSPOTS),
    }
    summary.update({
        "validator_revision": "D1r roundoff-aware absolute reconstruction tolerance",
        "charge_component_max_sum_abs_C_m3": component_scale,
        "machine_epsilon": eps,
        "roundoff_abs_tolerance_C_m3": roundoff_abs_tol,
        "validator_checks": checks,
        "status": "PASS" if all(checks.values()) else "VALIDATOR_SELFTEST_FAIL",
    })
    _write(summary_path, summary)
    return 0 if summary["status"] == "PASS" else 1


def _load_snapshot_summary(snapshot: Path) -> dict[str, Any]:
    path = snapshot / "summary.json"
    if not path.exists():
        raise RuntimeError(f"missing governed snapshot summary: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _inward_indices(i: int, wall: set[int], neigh: dict[int, set[int]]) -> list[int]:
    js = sorted(set(neigh.get(i, set())) - wall)
    if not js:
        js = sorted(neigh.get(i, set()))
    return js


def _face_states(snapshot: Path):
    coords, conn, emap, vals, t, sidesets = pgw._load_snapshot(snapshot, 10)
    species = d1s2._species_charge(vals)
    rho_raw = species["net"]
    _tri, _area, _rcent, vol = d1s2._geom(coords, conn)
    wall, neigh, rho_ref = d1s2._wall_refs(rho_raw, conn, sidesets)
    faces = d1s2._physical_faces(coords, conn, sidesets)
    ne = N_REF * vals["n_e"]
    meanE = ENERGY_REF_EV * vals["n_epsilon"] / vals["n_e"]

    records: list[dict[str, Any]] = []
    for name, i, face_area in faces:
        js = _inward_indices(i, wall, neigh)
        if not js:
            continue
        ne_s = float(np.mean(ne[js]))
        me_s = float(np.mean(meanE[js]))
        te = (2.0 / 3.0) * me_s
        phi_ref = float(np.mean(vals["potential_plasma"][js]))
        gamma0 = ne_s * math.sqrt(E_CHARGE * te / (2.0 * math.pi * M_E))
        records.append({
            "wall": name,
            "cell_index": int(i),
            "element_id": int(emap[i]),
            "face_area_m2": float(face_area),
            "n_e_s_m3": ne_s,
            "mean_energy_s_eV": me_s,
            "T_e_s_eV": te,
            "phi_inward_reference_V": phi_ref,
            "electron_unsuppressed_flux_m2_s": gamma0,
            "inward_neighbor_element_ids": [int(emap[j]) for j in js],
        })
    return coords, conn, emap, vals, t, sidesets, species, rho_raw, vol, wall, neigh, rho_ref, records


def _electron_current_A(records: list[dict[str, Any]], wall_name: str, phi_s: float, kappa: float) -> float:
    total = 0.0
    for rec in records:
        if rec["wall"] != wall_name:
            continue
        te = float(rec["T_e_s_eV"])
        suppression = math.exp(-max(phi_s, 0.0) / te)
        total += (E_CHARGE * float(rec["face_area_m2"]) *
                  float(rec["electron_unsuppressed_flux_m2_s"]) * suppression)
    return float(kappa * total)


def _build_sheath_lookup(snapshot: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    snap_summary = _load_snapshot_summary(snapshot)
    final = snap_summary["result"]["final_step"]["wall_current"]
    comps = final["components"]
    charged = final["wall"]["charged"]
    baseline_primary_A = abs(float(comps["primary_electron_A"]))
    see_A = float(comps["see_electron_A"])
    positive_A = float(comps["O2p_A"]) + float(comps["Op_A"])
    gamma_see = see_A / positive_A if positive_A > 0.0 else 0.0

    # Calibrate only one global prefactor to the governed production primary
    # electron current at the governed baseline inward-reference potentials.
    raw_baseline = 0.0
    for rec in records:
        te = float(rec["T_e_s_eV"])
        phi_ref = float(rec["phi_inward_reference_V"])
        raw_baseline += (
            E_CHARGE * float(rec["face_area_m2"]) *
            float(rec["electron_unsuppressed_flux_m2_s"]) *
            math.exp(-max(phi_ref, 0.0) / te)
        )
    if raw_baseline <= 0.0:
        raise RuntimeError("non-positive baseline electron-current proxy")
    kappa = baseline_primary_A / raw_baseline

    molar_mass = {"O2p": 0.032, "Om": 0.016, "Op": 0.016}
    z = {"O2p": 1.0, "Om": -1.0, "Op": 1.0}
    local_zero_targets: dict[str, float] = {}
    component_by_wall: dict[str, dict[str, float]] = {}
    for wall_name in PHYSICAL_WALLS:
        c: dict[str, float] = {}
        for sp in ("O2p", "Om", "Op"):
            item = charged[sp]["by_wall"][wall_name]
            mdot = float(item["migration_mass_rate_kg_s"]) + float(item["surface_mass_rate_kg_s"])
            current = z[sp] * FARADAY * mdot / molar_mass[sp]
            c[f"{sp}_A"] = float(current)
        c["SEE_A"] = float(gamma_see * (c["O2p_A"] + c["Op_A"]))
        target = c["O2p_A"] + c["Om_A"] + c["Op_A"] + c["SEE_A"]
        c["local_zero_current_primary_target_A"] = float(target)
        local_zero_targets[wall_name] = float(target)
        component_by_wall[wall_name] = c

    target_sum = float(sum(local_zero_targets.values()))
    target_scale = baseline_primary_A / target_sum if target_sum > 0.0 else 1.0

    roots: dict[str, float] = {}
    residuals: dict[str, float] = {}
    inward_wall_mean: dict[str, float] = {}
    lookup_rows: list[dict[str, Any]] = []
    for wall_name in PHYSICAL_WALLS:
        area_sum = sum(float(r["face_area_m2"]) for r in records if r["wall"] == wall_name)
        if area_sum <= 0.0:
            raise RuntimeError(f"no physical faces for {wall_name}")
        inward_wall_mean[wall_name] = (
            sum(float(r["face_area_m2"]) * float(r["phi_inward_reference_V"])
                for r in records if r["wall"] == wall_name) / area_sum
        )
        target = local_zero_targets[wall_name] * target_scale
        f0 = _electron_current_A(records, wall_name, 0.0, kappa) - target
        f60 = _electron_current_A(records, wall_name, 60.0, kappa) - target
        if not (f0 > 0.0 and f60 < 0.0):
            raise RuntimeError(f"current-balance root not bracketed for {wall_name}: f0={f0}, f60={f60}")
        root = float(brentq(lambda v: _electron_current_A(records, wall_name, v, kappa) - target,
                            0.0, 60.0, xtol=1e-12, rtol=1e-12))
        roots[wall_name] = root
        current = _electron_current_A(records, wall_name, root, kappa)
        residuals[wall_name] = float((current - target) / max(abs(target), 1e-300))
        for v in np.linspace(0.0, 30.0, 61):
            lookup_rows.append({
                "wall": wall_name,
                "phi_s_V": float(v),
                "primary_electron_current_A": _electron_current_A(records, wall_name, float(v), kappa),
                "target_primary_electron_current_A": float(target),
            })

    return {
        "model": "Maxwellian one-way electron flux with exp[-(phi_s-Vw)/Te]; Vw=0",
        "frozen_state": True,
        "global_electron_current_prefactor_calibration": float(kappa),
        "baseline_primary_electron_current_A": baseline_primary_A,
        "baseline_net_outward_wall_current_A": float(final["net_outward_wall_current_A"]),
        "inferred_SEE_yield_from_governed_ledger": float(gamma_see),
        "local_zero_current_target_sum_A": target_sum,
        "target_rescale_to_preserve_governed_primary_current": float(target_scale),
        "wall_current_components_A": component_by_wall,
        "inward_reference_wall_potential_V": inward_wall_mean,
        "current_balance_phi_s_V": roots,
        "current_balance_relative_residual": residuals,
        "lookup_rows": lookup_rows,
    }


def _prepare_source(snapshot: Path, work: Path) -> dict[str, Any]:
    from scipy.io import netcdf_file
    (coords, conn, emap, vals, t, sidesets, species, rho_raw, vol,
     wall, neigh, rho_ref, records) = _face_states(snapshot)
    rho_use = rho_raw.copy()
    removed_C = 0.0
    corrected = 0
    for i in sorted(wall):
        if not np.isfinite(rho_ref[i]):
            continue
        excess = max(float(rho_raw[i] - rho_ref[i]), 0.0)
        if excess <= 0.0:
            continue
        rho_use[i] -= excess
        removed_C += excess * vol[i]
        corrected += 1

    src_e = work / "source.e"
    shutil.copy2(snapshot / "case" / "input_out.e", src_e)
    f = netcdf_file(str(src_e), "a", mmap=False)
    names = d1s2._decode_names(f.variables["name_elem_var"].data.copy())
    iv = names.index("potential_plasma") + 1
    var = f.variables[f"vals_elem_var{iv}eb1"]
    data = var.data.copy()
    data[:] = (rho_use / EPS0)[np.newaxis, :]
    var[:] = data
    f.flush(); f.close()

    nonwall = np.asarray([i for i in range(len(conn)) if i not in wall], dtype=int)
    baseline_nonwall_mean = float(np.dot(vals["potential_plasma"][nonwall], vol[nonwall]) / np.sum(vol[nonwall]))
    lookup = _build_sheath_lookup(snapshot, records)
    return {
        "time_s": t,
        "volume_charge_raw_C": float(np.dot(rho_raw, vol)),
        "volume_charge_used_C": float(np.dot(rho_use, vol)),
        "removed_wall_excess_C": float(removed_C),
        "corrected_wall_cells": corrected,
        "baseline_nonwall_volume_mean_phi_V": baseline_nonwall_mean,
        "lookup": lookup,
    }


def _wall_values(mode: str, prep: dict[str, Any]) -> dict[str, float]:
    if mode == "control_zero":
        return {w: 0.0 for w in PHYSICAL_WALLS}
    if mode == "inward_reference":
        return {w: float(prep["lookup"]["inward_reference_wall_potential_V"][w]) for w in PHYSICAL_WALLS}
    if mode == "current_balance":
        return {w: float(prep["lookup"]["current_balance_phi_s_V"][w]) for w in PHYSICAL_WALLS}
    raise ValueError(mode)


def _s3_input(mode: str, wall_values: dict[str, float], initial_phi: float) -> str:
    wall_bcs = []
    for w in PHYSICAL_WALLS:
        wall_bcs.append(f"""  [sheath_edge_{w}]
    type = FVDirichletBC
    variable = phi
    boundary = {w}
    value = {wall_values[w]:.17g}
  []""")
    wall_bc_text = "\n".join(wall_bcs)
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
    initial_condition = {initial_phi:.17g}
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
  [openings_ground]
    type = FVDirichletBC
    variable = phi
    boundary = 'inlet outlet'
    value = 0
  []
{wall_bc_text}
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


def _write_lookup_csv(out: Path, lookup: dict[str, Any]) -> None:
    rows = lookup["lookup_rows"]
    with (out / "sheath_current_lookup.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)


def run_s3(args: argparse.Namespace) -> int:
    mode = args.mode
    if mode not in S3_MODES:
        raise ValueError(mode)
    exe = args.physics_opt.resolve()
    snapshot = args.snapshot_root.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    case = out / "case"; logs = out / "logs"
    case.mkdir(parents=True); logs.mkdir()

    prep = _prepare_source(snapshot, case)
    _write_lookup_csv(out, prep["lookup"])
    wall_values = _wall_values(mode, prep)
    initial_phi = float(np.mean(list(wall_values.values()))) if wall_values else prep["baseline_nonwall_volume_mean_phi_V"]
    text = _s3_input(mode, wall_values, initial_phi)
    (case / "input.i").write_text(text, encoding="utf-8")

    p2 = d1s2._run([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 180)
    summary: dict[str, Any] = {
        "status": "RUNNING",
        "claim": "subgrid_sheath_edge_boundary_current_balance_frozen_prototype",
        "mode": mode,
        "diagnostic_only": True,
        "physical_wall_voltage_V": 0.0,
        "bulk_sheath_edge_wall_values_V": wall_values,
        "preparation": prep,
        "p2": p2,
    }
    if p2["returncode"] != 0:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"; _write(out / "summary.json", summary); return 1
    rt = d1s2._run([str(exe), "-i", "input.i"], case, logs / "runtime.log", 600)
    summary["runtime"] = rt
    if rt["returncode"] != 0 or rt["timed_out"]:
        summary["status"] = "SOLVER_CONVERGENCE_FAIL"; _write(out / "summary.json", summary); return 1

    exo = sorted(case.glob("*_out.e"))
    if len(exo) != 1:
        summary["status"] = "HARNESS_OR_CONSTRUCTION_FAIL"
        summary["error"] = f"expected one output Exodus, got {exo}"
        _write(out / "summary.json", summary); return 1
    conn, emap, phi, sidesets = d1s2._read_phi(exo[0])
    hs = d1s2._hotspots(emap, conn, sidesets, phi)

    coords, conn0, _emap0, _vals0, _t0, sidesets0 = pgw._load_snapshot(snapshot, 10)[:6]
    _tri, _area, _rcent, vol = d1s2._geom(coords, conn0)
    wall, _neigh = pgw._wall_cells_and_neighbors(conn0, sidesets0)
    nonwall = np.asarray([i for i in range(len(conn0)) if i not in wall], dtype=int)
    nonwall_mean = float(np.dot(phi[nonwall], vol[nonwall]) / np.sum(vol[nonwall]))
    baseline_mean = float(prep["baseline_nonwall_volume_mean_phi_V"])
    max_lookup_resid = max(abs(float(v)) for v in prep["lookup"]["current_balance_relative_residual"].values())

    gates = {
        "all_hotspots_drop": len(hs) == len(HOTSPOTS) and all(v["H_wall_minus_inward_V"] <= 0.0 for v in hs.values()),
        "bulk_mean_scale": abs(nonwall_mean - baseline_mean) <= 5.0,
        "finite_moderate_span": float(phi.max() - phi.min()) <= 30.0,
        "bounded_potential": float(phi.min()) >= -5.0 and float(phi.max()) <= 40.0,
        "lookup_current_balance": max_lookup_resid <= 1.0e-9,
    }
    physical_acceptance = all(gates.values())
    summary.update({
        "phi_min_V": float(phi.min()),
        "phi_max_V": float(phi.max()),
        "phi_span_V": float(phi.max() - phi.min()),
        "phi_max_element_id": int(emap[int(np.argmax(phi))]),
        "nonwall_volume_mean_phi_V": nonwall_mean,
        "baseline_nonwall_volume_mean_phi_V": baseline_mean,
        "nonwall_mean_delta_V": nonwall_mean - baseline_mean,
        "hotspots": hs,
        "acceptance_gates": gates,
        "physical_acceptance": physical_acceptance,
    })

    # Controls are evidence-generating even when intentionally nonphysical.
    if mode == "control_zero":
        summary["status"] = "PASS"
        summary["control_expected_to_fail_physical_acceptance"] = True
        _write(out / "summary.json", summary); return 0
    summary["status"] = "PASS" if physical_acceptance else "PHYSICS_MODEL_FAIL"
    _write(out / "summary.json", summary)
    return 0 if summary["status"] == "PASS" else 1


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("d1r")
    d.add_argument("--snapshot-root", type=Path, required=True)
    d.add_argument("--results-root", type=Path, required=True)
    s = sub.add_parser("s3")
    s.add_argument("--mode", choices=S3_MODES, required=True)
    s.add_argument("--snapshot-root", type=Path, required=True)
    s.add_argument("--physics-opt", type=Path, required=True)
    s.add_argument("--results-root", type=Path, required=True)
    args = p.parse_args()
    return run_d1r(args) if args.cmd == "d1r" else run_s3(args)


if __name__ == "__main__":
    raise SystemExit(main())
