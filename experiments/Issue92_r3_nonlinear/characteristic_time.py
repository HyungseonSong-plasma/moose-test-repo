#!/usr/bin/env python3
"""QPX-free characteristic-time audit for Issue #92 R3 diagnostics.

This module reads the accepted real-QVT R3 assets only. It does not execute
qpx-opt and therefore consumes no scientific EVR. The audit distinguishes
physical/domain transport scales from local mesh transport scales and fails
closed when an accepted coefficient cannot be reconstructed without QPX.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from statistics import median
from typing import Any

from experiments.historical_recipe_support.issue91_r3 import ELECTRON_DT, MEAN_ELECTRON_ENERGY_EV

KB = 1.380649e-23
R = 8.31446261815324
DIAGNOSTIC_POINTS_PER_ELECTRON_TIME = 10.0
COMFORTABLE_CHI = 0.1


class CharacteristicTimeError(RuntimeError):
    pass


def _scalar(text: str, name: str) -> float:
    matches = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", text)
    if len(matches) != 1:
        raise CharacteristicTimeError(f"cannot resolve unique scalar {name}")
    try:
        value = float(matches[0].strip())
    except ValueError as exc:
        raise CharacteristicTimeError(f"scalar {name} is not a literal float") from exc
    if not math.isfinite(value):
        raise CharacteristicTimeError(f"scalar {name} is non-finite")
    return value


def _species_masses(transport_text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in transport_text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "species":
            out[parts[1]] = float(parts[2])
    if not out:
        raise CharacteristicTimeError("transport_data.txt contains no species masses")
    return out


def _electron_moment(table_text: str, energy_ev: float) -> tuple[float, float]:
    rows: list[tuple[float, float, float]] = []
    for raw in table_text.splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        try:
            rows.append(tuple(float(v) for v in parts[:3]))
        except ValueError:
            continue
    if not rows:
        raise CharacteristicTimeError("electron_moments.txt contains no numeric rows")
    energy, mu_n, d_n = min(rows, key=lambda row: abs(row[0] - energy_ev))
    if abs(energy - energy_ev) > 1.0e-8:
        raise CharacteristicTimeError(
            f"electron moment row for mean energy {energy_ev} eV is not present"
        )
    return mu_n, d_n


def _physical_names(lines: list[str]) -> dict[tuple[int, int], str]:
    try:
        i = lines.index("$PhysicalNames")
        n = int(lines[i + 1])
    except (ValueError, IndexError):
        return {}
    out: dict[tuple[int, int], str] = {}
    for raw in lines[i + 2 : i + 2 + n]:
        m = re.match(r'^\s*(\d+)\s+(\d+)\s+"(.*)"\s*$', raw)
        if m:
            out[(int(m.group(1)), int(m.group(2)))] = m.group(3)
    return out


def _entities(lines: list[str]) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    try:
        i = lines.index("$Entities")
        np, nc, ns, nv = (int(v) for v in lines[i + 1].split())
    except (ValueError, IndexError) as exc:
        raise CharacteristicTimeError("unsupported/missing Gmsh $Entities section") from exc
    cursor = i + 2 + np
    curves: dict[int, dict[str, Any]] = {}
    for raw in lines[cursor : cursor + nc]:
        p = raw.split()
        if len(p) < 8:
            raise CharacteristicTimeError("malformed curve entity")
        tag = int(p[0])
        nphys = int(p[7])
        phys = [int(v) for v in p[8 : 8 + nphys]]
        j = 8 + nphys
        nbound = int(p[j])
        curves[tag] = {
            "bbox": tuple(float(v) for v in p[1:7]),
            "physical_tags": phys,
            "bounds": [int(v) for v in p[j + 1 : j + 1 + nbound]],
        }
    cursor += nc
    surfaces: dict[int, dict[str, Any]] = {}
    for raw in lines[cursor : cursor + ns]:
        p = raw.split()
        if len(p) < 8:
            raise CharacteristicTimeError("malformed surface entity")
        tag = int(p[0])
        nphys = int(p[7])
        phys = [int(v) for v in p[8 : 8 + nphys]]
        j = 8 + nphys
        nbound = int(p[j])
        surfaces[tag] = {
            "bbox": tuple(float(v) for v in p[1:7]),
            "physical_tags": phys,
            "bounds": [int(v) for v in p[j + 1 : j + 1 + nbound]],
        }
    return curves, surfaces


def _nodes(lines: list[str]) -> dict[int, tuple[float, float, float]]:
    try:
        i = lines.index("$Nodes")
        nblocks = int(lines[i + 1].split()[0])
    except (ValueError, IndexError) as exc:
        raise CharacteristicTimeError("unsupported/missing Gmsh $Nodes section") from exc
    cursor = i + 2
    out: dict[int, tuple[float, float, float]] = {}
    for _ in range(nblocks):
        dim, _entity, parametric, n = (int(v) for v in lines[cursor].split())
        cursor += 1
        tags: list[int] = []
        while len(tags) < n:
            tags.extend(int(v) for v in lines[cursor].split())
            cursor += 1
        stride = 3 + (dim if parametric else 0)
        coords: list[float] = []
        while len(coords) < n * stride:
            coords.extend(float(v) for v in lines[cursor].split())
            cursor += 1
        for k, tag in enumerate(tags):
            base = k * stride
            out[tag] = tuple(coords[base : base + 3])
    return out


def _plasma_edge_lengths(lines: list[str], plasma_entity: int, nodes: dict[int, tuple[float, float, float]]) -> list[float]:
    try:
        i = lines.index("$Elements")
        nblocks = int(lines[i + 1].split()[0])
    except (ValueError, IndexError) as exc:
        raise CharacteristicTimeError("unsupported/missing Gmsh $Elements section") from exc
    corner_count = {2: 3, 3: 4, 9: 3, 10: 4, 16: 4}
    cursor = i + 2
    lengths: list[float] = []
    for _ in range(nblocks):
        dim, entity, etype, n = (int(v) for v in lines[cursor].split())
        cursor += 1
        for raw in lines[cursor : cursor + n]:
            p = [int(v) for v in raw.split()]
            if dim == 2 and entity == plasma_entity and etype in corner_count:
                ids = p[1 : 1 + corner_count[etype]]
                for a, b in zip(ids, ids[1:] + ids[:1]):
                    xa, ya, za = nodes[a]
                    xb, yb, zb = nodes[b]
                    lengths.append(math.dist((xa, ya, za), (xb, yb, zb)))
        cursor += n
    if not lengths:
        raise CharacteristicTimeError("no supported 2-D plasma element edges found")
    return lengths


def _rz_curve_area(bbox: tuple[float, ...]) -> float:
    xmin, ymin, _zmin, xmax, ymax, _zmax = bbox
    dx, dy = xmax - xmin, ymax - ymin
    tol = 1.0e-12
    if abs(dx) <= tol:
        return 2.0 * math.pi * 0.5 * (xmin + xmax) * abs(dy)
    if abs(dy) <= tol:
        return math.pi * abs(xmax * xmax - xmin * xmin)
    length = math.hypot(dx, dy)
    return 2.0 * math.pi * 0.5 * (xmin + xmax) * length


def _mesh_metrics(mesh_text: str) -> dict[str, Any]:
    lines = mesh_text.splitlines()
    names = _physical_names(lines)
    curves, surfaces = _entities(lines)
    plasma_phys = next((tag for (dim, tag), name in names.items() if dim == 2 and name == "plasma"), None)
    port_phys = next((tag for (dim, tag), name in names.items() if dim == 2 and name == "port"), None)
    if plasma_phys is None:
        raise CharacteristicTimeError("physical surface 'plasma' not found")
    plasma_entities = [tag for tag, rec in surfaces.items() if plasma_phys in rec["physical_tags"]]
    if len(plasma_entities) != 1:
        raise CharacteristicTimeError(f"expected one plasma surface entity, found {plasma_entities}")
    plasma_entity = plasma_entities[0]
    bbox = surfaces[plasma_entity]["bbox"]
    spans = [abs(bbox[3] - bbox[0]), abs(bbox[4] - bbox[1])]
    spans = [v for v in spans if v > 0]
    nodes = _nodes(lines)
    edges = _plasma_edge_lengths(lines, plasma_entity, nodes)

    inlet_area = None
    shared_curves: list[int] = []
    if port_phys is not None:
        ports = [tag for tag, rec in surfaces.items() if port_phys in rec["physical_tags"]]
        if len(ports) == 1:
            pb = {abs(v) for v in surfaces[plasma_entity]["bounds"]}
            qb = {abs(v) for v in surfaces[ports[0]]["bounds"]}
            shared_curves = sorted(pb & qb)
            if shared_curves:
                inlet_area = sum(_rz_curve_area(curves[tag]["bbox"]) for tag in shared_curves)

    return {
        "plasma_entity": plasma_entity,
        "plasma_bbox": bbox,
        "domain_length_min": min(spans),
        "domain_length_max": max(spans),
        "mesh_edge_min": min(edges),
        "mesh_edge_median": median(edges),
        "mesh_edge_max": max(edges),
        "plasma_edge_sample_count": len(edges),
        "inlet_shared_curve_entities": shared_curves,
        "inlet_rz_area": inlet_area,
    }


def _inlet_molar_mass(base_text: str, masses: dict[str, float]) -> float:
    species = ("O2", "O2s", "O2p", "O", "Om", "Op", "Os")
    inv = 0.0
    for name in species:
        y = _scalar(base_text, f"Yin_{name}")
        if name not in masses:
            raise CharacteristicTimeError(f"missing molar mass for {name}")
        inv += y / masses[name]
    if inv <= 0:
        raise CharacteristicTimeError("invalid inlet composition")
    return 1.0 / inv


def _time(length: float, speed_or_diffusion: float, *, diffusion: bool) -> float:
    if speed_or_diffusion <= 0:
        return math.inf
    return length * length / speed_or_diffusion if diffusion else length / speed_or_diffusion


def audit_case(case_dir: Path, *, current_dt: float = ELECTRON_DT) -> dict[str, Any]:
    case = case_dir.resolve()
    base_text = (case / "heavy_base.i").read_text()
    mesh_text = (case / "qvt.msh").read_text()
    transport_text = (case / "transport_data.txt").read_text()
    moments_text = (case / "electron_moments.txt").read_text()

    mesh = _mesh_metrics(mesh_text)
    p = _scalar(base_text, "outlet_pressure")
    tg = _scalar(base_text, "T_g_value")
    efield = abs(_scalar(base_text, "E0_migration"))
    # Issue91 R3-E0 composition replaces E0_migration by zero. The case asset is
    # an upstream heavy base, so T0 audits E0 explicitly for the active branch.
    efield = 0.0
    mu_n, d_n = _electron_moment(moments_text, MEAN_ELECTRON_ENERGY_EV)
    neutral_density = p / (KB * tg)
    mu_e = mu_n / neutral_density
    d_e = d_n / neutral_density

    lengths = {
        "mesh_min": mesh["mesh_edge_min"],
        "mesh_median": mesh["mesh_edge_median"],
        "domain_min": mesh["domain_length_min"],
        "domain_max": mesh["domain_length_max"],
    }
    electron: dict[str, Any] = {}
    for key, length in lengths.items():
        tau_diff = _time(length, d_e, diffusion=True)
        tau_drift = math.inf if efield == 0 else _time(length, mu_e * efield, diffusion=False)
        electron[key] = {
            "length_m": length,
            "tau_diff_s": tau_diff,
            "chi_diff": current_dt / tau_diff,
            "tau_drift_s": None if math.isinf(tau_drift) else tau_drift,
            "chi_drift": 0.0 if math.isinf(tau_drift) else current_dt / tau_drift,
        }

    masses = _species_masses(transport_text)
    molar_mass = _inlet_molar_mass(base_text, masses)
    q_sccm = _scalar(base_text, "Q_sccm")
    vm_std = _scalar(base_text, "Vm_std")
    q_std = q_sccm * 1.0e-6 / 60.0
    mdot = q_std * molar_mass / vm_std
    rho = p * molar_mass / (R * tg)
    inlet_area = mesh["inlet_rz_area"]
    inlet_velocity = None
    if inlet_area is not None and inlet_area > 0 and rho > 0:
        inlet_velocity = mdot / (rho * inlet_area)

    heavy_adv: dict[str, Any] = {}
    if inlet_velocity is not None and inlet_velocity > 0:
        for key, length in lengths.items():
            tau = _time(length, inlet_velocity, diffusion=False)
            heavy_adv[key] = {"length_m": length, "tau_adv_s": tau, "chi_adv": current_dt / tau}

    local_e = electron["mesh_min"]["chi_diff"]
    local_h = heavy_adv.get("mesh_min", {}).get("chi_adv")
    values_complete = local_h is not None
    if not values_complete:
        t0 = "T0-C"
        reason = "HEAVY_ADVECTIVE_SCALE_NOT_ESTABLISHED_QPX_FREE"
        candidate_dt = None
    elif local_e <= COMFORTABLE_CHI:
        t0 = "T0-A"
        reason = "CURRENT_DT_COMFORTABLY_BELOW_LOCAL_ELECTRON_DIFFUSION_TIME"
        candidate_dt = None
    else:
        t0 = "T0-B"
        reason = "LOCAL_ELECTRON_DIFFUSION_TIME_IS_WITHIN_ONE_DECADE_OF_OR_BELOW_CURRENT_DT"
        candidate_dt = electron["mesh_min"]["tau_diff_s"] / DIAGNOSTIC_POINTS_PER_ELECTRON_TIME

    tau_e_local = electron["mesh_min"]["tau_diff_s"]
    separation = None
    if heavy_adv:
        separation = heavy_adv["domain_min"]["tau_adv_s"] / tau_e_local

    return {
        "issue": 92,
        "audit": "T0_CHARACTERISTIC_TIME",
        "qpx_executed": False,
        "scientific_evr_consumed": 0,
        "current_dt_s": current_dt,
        "decision": t0,
        "decision_reason": reason,
        "candidate_temporal_dt_s": candidate_dt,
        "diagnostic_points_per_electron_time": DIAGNOSTIC_POINTS_PER_ELECTRON_TIME,
        "comfort_band_chi": COMFORTABLE_CHI,
        "mesh": mesh,
        "electron_state": {
            "pressure_Pa": p,
            "gas_temperature_K": tg,
            "mean_energy_eV": MEAN_ELECTRON_ENERGY_EV,
            "neutral_density_m-3": neutral_density,
            "muN": mu_n,
            "DN": d_n,
            "electron_mobility_m2_Vs": mu_e,
            "electron_diffusion_m2_s": d_e,
            "prescribed_E_V_m": efield,
        },
        "electron_times": electron,
        "heavy_advection": {
            "status": "ESTABLISHED" if heavy_adv else "NOT_ESTABLISHED",
            "inlet_molar_mass_kg_mol": molar_mass,
            "mass_flow_kg_s": mdot,
            "initial_density_kg_m3": rho,
            "inlet_rz_area_m2": inlet_area,
            "inlet_velocity_m_s": inlet_velocity,
            "times": heavy_adv,
        },
        "heavy_diffusion": {
            "status": "NOT_ESTABLISHED",
            "reason": "QPXThermalDiffusionMaterial D_mix requires framework material evaluation; no surrogate coefficient used",
        },
        "timescale_separation": {
            "tau_h_adv_domain_min_over_tau_e_diff_mesh_min": separation,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit_case(args.case_dir)
    except (CharacteristicTimeError, OSError, ValueError) as exc:
        print(f"ISSUE92_T0_ERROR: {exc}")
        return 2
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    print(f"ISSUE92_T0_DECISION: {result['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
