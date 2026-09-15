#!/usr/bin/env python3
"""Issue #234 M0: deterministic characteristic-time preflight for multirate MultiApp.

This stage does not construct a MultiApp. It derives the parent/subapp timestep
candidates from the governed #228 snapshot and the current electron-transport
implementation, then records the numerical policy that later MultiApp stages
must satisfy.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import netcdf_file

ENERGY_TRANSPORT_FACTOR = 5.0 / 3.0
HEAVY_SAFETY = 0.1
ELECTRON_REFERENCE_SAFETY = 0.5
DT_HEAVY_CANDIDATE_S = 1.0e-8
DT_HEAVY_REFERENCE_S = 5.0e-9
DT_HEAVY_COARSE_S = 2.0e-8
DT_E_CANDIDATE_S = 1.0e-11
DT_E_REFERENCE_S = 5.0e-12
DT_E_COARSE_S = (2.0e-11, 1.0e-10)
HEAVY_SPECIES = ("w_O", "w_O2p", "w_O2s", "w_Om", "w_Op", "w_Os")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _decode_names(a) -> list[str]:
    return [b"".join(row).decode(errors="ignore").strip().strip("\x00") for row in a]


def _read_csv_endpoint(path: Path) -> dict[str, float]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty CSV: {path}")
    return {k: float(v) for k, v in rows[-1].items() if v not in (None, "")}


def _read_snapshot(root: Path):
    epath = root / "case" / "input_out.e"
    cpath = root / "case" / "input_out.csv"
    spath = root / "summary.json"
    if not epath.is_file() or not cpath.is_file() or not spath.is_file():
        raise RuntimeError("governed snapshot must contain case/input_out.e, case/input_out.csv, summary.json")

    f = netcdf_file(str(epath), "r", mmap=False)
    coords = np.c_[f.variables["coordx"].data.copy(), f.variables["coordy"].data.copy()]
    conn = f.variables["connect1"].data.copy().astype(int) - 1
    times = f.variables["time_whole"].data.copy().astype(float)
    names = _decode_names(f.variables["name_elem_var"].data.copy())
    values = {
        name: f.variables[f"vals_elem_var{i + 1}eb1"].data.copy().astype(float)
        for i, name in enumerate(names)
    }
    f.close()
    endpoint = _read_csv_endpoint(cpath)
    summary = json.loads(spath.read_text(encoding="utf-8"))
    return coords, conn, times, values, endpoint, summary


def _internal_pairs(conn: np.ndarray) -> list[tuple[int, int]]:
    edge_map: dict[tuple[int, int], list[int]] = {}
    for i, row in enumerate(conn):
        edges = ((row[0], row[1]), (row[1], row[2]), (row[2], row[0]))
        for a, b in edges:
            edge_map.setdefault(tuple(sorted((int(a), int(b)))), []).append(i)
    return [(cells[0], cells[1]) for cells in edge_map.values() if len(cells) == 2]


def _robust_evolution_time(times: np.ndarray, a: np.ndarray) -> float:
    taus: list[float] = []
    for k in range(1, len(times)):
        dt = float(times[k] - times[k - 1])
        x = np.abs(a[k])
        dxdt = np.abs((a[k] - a[k - 1]) / dt)
        scale = max(float(np.max(x)), 1.0e-300)
        threshold = max(1.0e-12, 1.0e-6 * scale)
        mask = (x > threshold) & (dxdt > 0.0) & np.isfinite(dxdt)
        if np.any(mask):
            taus.extend((x[mask] / dxdt[mask]).tolist())
    if not taus:
        return math.inf
    return float(np.min(np.asarray(taus)))


def _wall_charge_tau(summary: dict[str, Any]) -> float:
    steps = summary["result"]["steps"]
    currents = [abs(float(x["wall_current"]["net_outward_wall_current_A"])) for x in steps[:5]]
    dt = float(summary["meta"]["dt_s"])
    taus = []
    for a, b in zip(currents[:-1], currents[1:]):
        if a > b > 0.0:
            taus.append(-dt / math.log(b / a))
    if not taus:
        raise RuntimeError("unable to infer wall-charge relaxation time")
    return float(np.median(np.asarray(taus)))


def self_test() -> int:
    assert math.isclose(ENERGY_TRANSPORT_FACTOR, 5.0 / 3.0)
    assert DT_E_REFERENCE_S < DT_E_CANDIDATE_S < DT_HEAVY_CANDIDATE_S
    assert math.isclose(DT_HEAVY_CANDIDATE_S / DT_E_CANDIDATE_S, 1000.0)
    assert math.isclose(DT_HEAVY_CANDIDATE_S / DT_E_REFERENCE_S, 2000.0)
    print("Issue234 M0 self-test PASS")
    return 0


def run(args: argparse.Namespace) -> int:
    root = args.snapshot_root.resolve()
    repo = args.repo_root.resolve()
    out = args.results_root.resolve()
    out.mkdir(parents=True, exist_ok=True)

    cpp = repo / "physics_app" / "src" / "materials" / "PhysicsElectronTransportLookupMaterial.C"
    text = cpp.read_text(encoding="utf-8")
    if "constexpr Real energy_transport_factor = 5.0 / 3.0;" not in text:
        payload = {"status": "HARNESS_OR_CONSTRUCTION_FAIL", "evidence_valid": False,
                   "error": "electron energy transport factor is no longer 5/3"}
        _write(out / "summary.json", payload)
        return 1

    coords, conn, times, values, endpoint, summary = _read_snapshot(root)
    centroids = coords[conn].mean(axis=1)
    pairs = _internal_pairs(conn)
    dcc = np.asarray([np.linalg.norm(centroids[j] - centroids[i]) for i, j in pairs], dtype=float)
    if len(dcc) == 0 or not np.all(np.isfinite(dcc)):
        raise RuntimeError("invalid internal FV centroid spacing")
    dcc_min = float(np.min(dcc))

    D_e = float(endpoint["electron_diffusion_avg"])
    mu_e = float(endpoint["electron_mobility_avg"])
    D_eps = ENERGY_TRANSPORT_FACTOR * D_e
    tau_e_particle_diff = dcc_min * dcc_min / (2.0 * D_e)
    tau_e_energy_diff = dcc_min * dcc_min / (2.0 * D_eps)
    tau_charge = _wall_charge_tau(summary)

    phi = values["potential_plasma"][-1]
    approx_e = []
    for i, j in pairs:
        d = float(np.linalg.norm(centroids[j] - centroids[i]))
        approx_e.append(abs(float(phi[j] - phi[i])) / d)
    approx_e = np.asarray(approx_e)
    mask = approx_e > 1.0e-12
    tau_e_drift = float(np.min(dcc[mask] / (mu_e * approx_e[mask]))) if np.any(mask) else math.inf

    ion_transport = {}
    ion_tau_diff = []
    ion_tau_drift = []
    Emax = float(np.max(approx_e))
    for sp in ("O2p", "Om", "Op"):
        D = float(endpoint[f"Dmix_{sp}_avg"])
        mu = float(endpoint[f"mu_{sp}_avg"])
        td = dcc_min * dcc_min / (2.0 * D)
        te = dcc_min / (mu * Emax)
        ion_transport[sp] = {"D_avg_m2_s": D, "mu_avg_m2_V_s": mu,
                             "tau_diff_min_s": td, "tau_drift_supporting_s": te}
        ion_tau_diff.append(td)
        ion_tau_drift.append(te)

    heavy_evolution = {name: _robust_evolution_time(times, values[name]) for name in HEAVY_SPECIES}
    tau_h_observed = min(heavy_evolution.values())
    tau_h_control = min(tau_h_observed, min(ion_tau_diff), min(ion_tau_drift))
    tau_e_control = min(tau_e_energy_diff, tau_charge, tau_e_particle_diff, tau_e_drift)

    gates = {
        "electron_reference_resolves_half_fastest_time": DT_E_REFERENCE_S <= ELECTRON_REFERENCE_SAFETY * tau_e_control,
        "electron_candidate_not_slower_than_fastest_time": DT_E_CANDIDATE_S <= tau_e_control,
        "heavy_candidate_within_10pct_fastest_heavy_time": DT_HEAVY_CANDIDATE_S <= HEAVY_SAFETY * tau_h_control,
        "candidate_subcycle_ratio_integer": math.isclose(DT_HEAVY_CANDIDATE_S / DT_E_CANDIDATE_S, 1000.0),
        "reference_subcycle_ratio_integer": math.isclose(DT_HEAVY_CANDIDATE_S / DT_E_REFERENCE_S, 2000.0),
    }

    payload = {
        "status": "BATCH_PASS" if all(gates.values()) else "SCIENTIFIC_PRECHECK_REJECTED",
        "ci_status": "success",
        "evidence_valid": True,
        "scientific_outcome": "MULTIRATE_TIMESTEP_BRACKET_QUALIFIED" if all(gates.values()) else "MULTIRATE_TIMESTEP_BRACKET_NOT_QUALIFIED",
        "claim": "derive MultiApp parent/subapp timestep bracket from governed characteristic times",
        "model_note": "plasma frequency is excluded because the active electron model is drift-diffusion without electron inertia",
        "geometry": {"internal_face_count": len(pairs), "minimum_centroid_spacing_m": dcc_min},
        "electron": {
            "D_avg_m2_s": D_e,
            "mu_avg_m2_V_s": mu_e,
            "energy_transport_factor": ENERGY_TRANSPORT_FACTOR,
            "D_energy_avg_m2_s": D_eps,
            "tau_particle_diff_min_s": tau_e_particle_diff,
            "tau_energy_diff_min_s": tau_e_energy_diff,
            "tau_wall_charge_median_s": tau_charge,
            "tau_drift_supporting_min_s": tau_e_drift,
            "tau_control_s": tau_e_control,
        },
        "heavy": {
            "robust_observed_species_tau_min_s": tau_h_observed,
            "robust_observed_species_times_s": heavy_evolution,
            "ion_transport": ion_transport,
            "tau_control_s": tau_h_control,
        },
        "timestep_plan": {
            "heavy_candidate_s": DT_HEAVY_CANDIDATE_S,
            "heavy_reference_s": DT_HEAVY_REFERENCE_S,
            "heavy_coarse_control_s": DT_HEAVY_COARSE_S,
            "electron_candidate_s": DT_E_CANDIDATE_S,
            "electron_reference_s": DT_E_REFERENCE_S,
            "electron_coarse_controls_s": list(DT_E_COARSE_S),
            "candidate_subcycles_per_parent": int(round(DT_HEAVY_CANDIDATE_S / DT_E_CANDIDATE_S)),
            "reference_subcycles_per_parent": int(round(DT_HEAVY_CANDIDATE_S / DT_E_REFERENCE_S)),
        },
        "gates": gates,
        "interpretation": {
            "electron_1e-10_s": "coarse convergence control only",
            "electron_1e-11_s": "production candidate pending M1 convergence against 5e-12 s",
            "heavy_1e-8_s": "production candidate pending M2 convergence against 5e-9 s",
        },
    }
    _write(out / "summary.json", payload)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--snapshot-root", type=Path)
    p.add_argument("--repo-root", type=Path, default=Path("."))
    p.add_argument("--results-root", type=Path)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.snapshot_root is None or args.results_root is None:
        p.error("--snapshot-root and --results-root are required unless --self-test")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
