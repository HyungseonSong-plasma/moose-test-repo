#!/usr/bin/env python3
"""Issue #376 T1B conservative RF-power injection acceptance analyzer."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

FARADAY = 96485.33212331001
EXPECTED_PABS_W = 175.81487393245
EXPECTED_PLASMA_TRIANGLES = 1826
EXPECTED_BOUNDS = (0.0, 0.243, 0.018, 0.3195)
RAW_MAPPING_REL_GATE = 2.0e-2
SOURCE_REPRO_REL_GATE = 1.0e-10
CONSERVATIVE_REL_GATE = 1.0e-9
ENERGY_BE_REL_GATE = 2.0e-8
ZERO_ABS_GATE = 1.0e-13
DT = 1.0e-8


def rows(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as f:
        raw = list(csv.DictReader(f))
    if not raw:
        raise RuntimeError(f"empty CSV: {path}")
    return [
        {k: float(v) for k, v in row.items() if k and v not in (None, "")}
        for row in raw
    ]


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1.0e-300)


def gmsh_plasma_summary(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    ni = lines.index("$Nodes")
    n_nodes = int(lines[ni + 1])
    coords = []
    for line in lines[ni + 2 : ni + 2 + n_nodes]:
        f = line.split()
        coords.append((float(f[1]), float(f[2])))
    ei = lines.index("$Elements")
    n_elem = int(lines[ei + 1])
    tri_nodes: set[int] = set()
    tri_count = 0
    for line in lines[ei + 2 : ei + 2 + n_elem]:
        f = line.split()
        etype = int(f[1])
        ntags = int(f[2])
        tags = [int(x) for x in f[3 : 3 + ntags]]
        conn = [int(x) for x in f[3 + ntags :]]
        if etype == 2 and tags and tags[0] == 10:
            tri_count += 1
            tri_nodes.update(conn)
    xs = [coords[i - 1][0] for i in tri_nodes]
    ys = [coords[i - 1][1] for i in tri_nodes]
    return {
        "plasma_triangles": tri_count,
        "plasma_nodes": len(tri_nodes),
        "bounds": [min(xs), max(xs), min(ys), max(ys)],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maxwell", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--scaled", type=Path, required=True)
    ap.add_argument("--mesh", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--scale", type=float, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    m = rows(args.maxwell)
    r = rows(args.raw)
    s = rows(args.scaled)
    failures: list[str] = []

    p_src = m[-1]["P_abs"]
    p_raw = r[-1]["P_rf_raw_W"]
    p_scaled = s[-1]["P_rf_scaled_W"]
    s_evmol = s[-1]["S_rf_eV_mol_s"]
    raw_e0 = r[0]["electron_energy_inventory_eV_mol"]
    raw_e1 = r[-1]["electron_energy_inventory_eV_mol"]
    e0 = s[0]["electron_energy_inventory_eV_mol"]
    e1 = s[-1]["electron_energy_inventory_eV_mol"]
    emin = s[-1]["electron_energy_min_eV_mol_m3"]
    emax = s[-1]["electron_energy_max_eV_mol_m3"]

    source_repro = rel(p_src, EXPECTED_PABS_W)
    raw_mapping = rel(p_raw, p_src)
    scaled_closure = rel(p_scaled, p_src)
    scale_identity = rel(args.scale * p_raw, p_src)
    source_unit_closure = rel(s_evmol * FARADAY, p_scaled)
    raw_energy_drift = raw_e1 - raw_e0
    observed_power = (e1 - e0) * FARADAY / DT
    energy_be_closure = rel(observed_power, p_scaled)

    mesh = gmsh_plasma_summary(args.mesh)
    input_text = args.input.read_text(encoding="utf-8")

    if source_repro > SOURCE_REPRO_REL_GATE:
        failures.append(f"frozen Maxwell P_abs reproduction {source_repro:.6e} > {SOURCE_REPRO_REL_GATE:.6e}")
    if not (p_raw > 0.0 and raw_mapping <= RAW_MAPPING_REL_GATE):
        failures.append(f"raw mapped power relative error {raw_mapping:.6e} exceeds {RAW_MAPPING_REL_GATE:.6e}")
    if scaled_closure > CONSERVATIVE_REL_GATE:
        failures.append(f"scaled transfer closure {scaled_closure:.6e} > {CONSERVATIVE_REL_GATE:.6e}")
    if scale_identity > CONSERVATIVE_REL_GATE:
        failures.append(f"scale identity closure {scale_identity:.6e} > {CONSERVATIVE_REL_GATE:.6e}")
    if source_unit_closure > CONSERVATIVE_REL_GATE:
        failures.append(f"W -> eV mol/s conversion closure {source_unit_closure:.6e} > {CONSERVATIVE_REL_GATE:.6e}")
    if abs(raw_energy_drift) > ZERO_ABS_GATE:
        failures.append(f"source-off electron-energy drift {raw_energy_drift:.6e} eV mol > {ZERO_ABS_GATE:.6e}")
    if energy_be_closure > ENERGY_BE_REL_GATE:
        failures.append(f"electron-energy BE power closure {energy_be_closure:.6e} > {ENERGY_BE_REL_GATE:.6e}")
    if not (emin > 0.0 and emax >= emin and e1 > e0 > 0.0):
        failures.append("electron-energy positivity/direction failure")

    if mesh["plasma_triangles"] != EXPECTED_PLASMA_TRIANGLES:
        failures.append(f"current baseline plasma triangle count changed: {mesh['plasma_triangles']}")
    for got, expected in zip(mesh["bounds"], EXPECTED_BOUNDS):
        if not math.isclose(got, expected, rel_tol=0.0, abs_tol=1.0e-12):
            failures.append(f"plasma mesh bounds changed: {mesh['bounds']}")
            break

    required = [
        "type = SolutionUserObject",
        "type = SolutionAux",
        "type = MatBodyForce",
        "material_property = q_rf_eV_mol",
        "PhysicsFEMLogMolarTimeDerivative",
        "faraday_J_per_eV_mol = 96485.33212331001",
    ]
    for token in required:
        if token not in input_text:
            failures.append(f"missing T1B contract token: {token}")
    if "type = PhysicsFEMLogMolarElectronJouleHeating" in input_text:
        failures.append("T1B isolated RF source unexpectedly instantiates electrostatic Joule heating")

    report = {
        "issue": 376,
        "gate": "T1B production-standard RF source injection discriminator",
        "status": "FAIL" if failures else "PASS",
        "scientific_acceptance": {"T1_transfer_conservation": not failures, "issue_376_complete": False},
        "source_maxwell": {
            "P_abs_W": p_src,
            "frozen_expected_W": EXPECTED_PABS_W,
            "relative_reproduction_error": source_repro,
        },
        "target_mesh": mesh,
        "raw_mapping": {
            "P_raw_W": p_raw,
            "relative_error_vs_source": raw_mapping,
            "predeclared_gate": RAW_MAPPING_REL_GATE,
            "note": "Spatial-profile fidelity is owned by T2; T1 only requires bounded raw mapping before conservative renormalization.",
        },
        "conservative_transfer": {
            "scale": args.scale,
            "P_scaled_W": p_scaled,
            "relative_power_closure": scaled_closure,
            "scale_identity_relative_closure": scale_identity,
        },
        "energy_source_units": {
            "Faraday_J_per_eV_mol": FARADAY,
            "integrated_source_eV_mol_s": s_evmol,
            "reconstructed_power_W": s_evmol * FARADAY,
            "relative_closure": source_unit_closure,
        },
        "electron_energy_injection": {
            "dt_s": DT,
            "source_off_inventory_delta_eV_mol": raw_energy_drift,
            "initial_inventory_eV_mol": e0,
            "final_inventory_eV_mol": e1,
            "observed_power_from_inventory_W": observed_power,
            "relative_BE_power_closure": energy_be_closure,
            "final_min_eV_mol_m3": emin,
            "final_max_eV_mol_m3": emax,
        },
        "implementation": {
            "field_import": "standard MOOSE SolutionUserObject + SolutionAux",
            "source_injection": "standard MOOSE MatBodyForce",
            "destination": "FEM LAGRANGE log_energy / PhysicsFEMLogMolarTimeDerivative",
            "custom_cpp_added": False,
            "electrostatic_joule_double_counted": False,
        },
        "tolerances": {
            "source_reproduction_relative": SOURCE_REPRO_REL_GATE,
            "raw_mapping_relative": RAW_MAPPING_REL_GATE,
            "conservative_relative": CONSERVATIVE_REL_GATE,
            "energy_BE_relative": ENERGY_BE_REL_GATE,
            "source_off_energy_abs_eV_mol": ZERO_ABS_GATE,
        },
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
