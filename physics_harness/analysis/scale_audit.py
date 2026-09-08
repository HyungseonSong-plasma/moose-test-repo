"""Generic multiphysics space-time scale analysis.

This module owns reusable geometry/statistics and scale calculations only.
Experiment-specific anchors, species collision data, thresholds, and treatment
policy are caller-owned inputs rather than production defaults.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

KB = 1.380649e-23
EPS0 = 8.8541878128e-12
E_CHARGE = 1.602176634e-19
MU0 = 1.25663706212e-6
C0 = 299792458.0

ELEMENT_NODES = {
    1: 2, 2: 3, 3: 4, 8: 3, 9: 6, 10: 9, 15: 1, 16: 8,
    20: 9, 21: 10, 22: 12, 23: 15, 24: 15, 25: 21,
}
TRIANGLE_TYPES = {2, 9, 20, 21, 22, 23, 24, 25}


class ScaleAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class Triangle:
    nodes: tuple[int, int, int]


def _section(text: str, name: str) -> str:
    start_token, end_token = f"${name}", f"$End{name}"
    start, end = text.find(start_token), text.find(end_token)
    if start < 0 or end < 0 or end <= start:
        raise ScaleAuditError(f"missing Gmsh section {name}")
    start = text.find("\n", start)
    if start < 0:
        raise ScaleAuditError(f"malformed Gmsh section {name}")
    return text[start + 1 : end]


def _physical_tag(text: str, name: str) -> int:
    lines = [line.strip() for line in _section(text, "PhysicalNames").splitlines() if line.strip()]
    if not lines:
        raise ScaleAuditError("empty PhysicalNames section")
    count = int(lines[0])
    matches = []
    for line in lines[1 : 1 + count]:
        parts = line.split(maxsplit=2)
        if len(parts) == 3 and parts[2].strip().strip('"') == name:
            matches.append(int(parts[1]))
    if len(matches) != 1:
        raise ScaleAuditError(f"expected one physical group {name!r}, found {len(matches)}")
    return matches[0]


def _surface_entities_with_physical(text: str, physical_tag: int) -> set[int]:
    lines = [line.strip() for line in _section(text, "Entities").splitlines() if line.strip()]
    counts = [int(value) for value in lines[0].split()]
    if len(counts) != 4:
        raise ScaleAuditError("invalid Entities header")
    npoints, ncurves, nsurfaces, _ = counts
    found: set[int] = set()
    for line in lines[1 + npoints + ncurves : 1 + npoints + ncurves + nsurfaces]:
        parts = line.split()
        if len(parts) < 8:
            raise ScaleAuditError(f"malformed surface entity: {line}")
        tag, nphys = int(parts[0]), int(parts[7])
        if physical_tag in [int(value) for value in parts[8 : 8 + nphys]]:
            found.add(tag)
    if not found:
        raise ScaleAuditError(f"no surface entity carries physical tag {physical_tag}")
    return found


def _nodes(text: str) -> dict[int, tuple[float, float, float]]:
    tokens = _section(text, "Nodes").split()
    pos = 0
    try:
        nblocks = int(tokens[pos]); pos += 1
        nnodes = int(tokens[pos]); pos += 1
        pos += 2
        result: dict[int, tuple[float, float, float]] = {}
        for _ in range(nblocks):
            entity_dim = int(tokens[pos]); pos += 1
            pos += 1
            parametric = int(tokens[pos]); pos += 1
            count = int(tokens[pos]); pos += 1
            tags = [int(tokens[pos + i]) for i in range(count)]
            pos += count
            for tag in tags:
                xyz = tuple(float(tokens[pos + i]) for i in range(3))
                pos += 3 + (entity_dim if parametric else 0)
                result[tag] = xyz  # type: ignore[assignment]
    except (IndexError, ValueError) as exc:
        raise ScaleAuditError("failed to parse Gmsh Nodes section") from exc
    if len(result) != nnodes:
        raise ScaleAuditError(f"node count mismatch: parsed {len(result)}, header {nnodes}")
    return result


def _plasma_triangles(text: str, surface_entities: set[int]) -> list[Triangle]:
    lines = [line.strip() for line in _section(text, "Elements").splitlines() if line.strip()]
    header = [int(value) for value in lines[0].split()]
    if len(header) != 4:
        raise ScaleAuditError("invalid Elements header")
    idx, triangles = 1, []
    for _ in range(header[0]):
        entity_dim, entity_tag, element_type, count = [int(value) for value in lines[idx].split()]
        idx += 1
        expected_nodes = ELEMENT_NODES.get(element_type)
        for _ in range(count):
            record = [int(value) for value in lines[idx].split()]
            idx += 1
            if expected_nodes is not None and len(record) != expected_nodes + 1:
                raise ScaleAuditError(f"element type {element_type} node-count mismatch")
            if entity_dim == 2 and entity_tag in surface_entities and element_type in TRIANGLE_TYPES:
                triangles.append(Triangle((record[1], record[2], record[3])))
    if not triangles:
        raise ScaleAuditError("no triangles found in requested physical group")
    return triangles


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _triangle_geometry(tri: Triangle, nodes: dict[int, tuple[float, float, float]]) -> tuple[float, tuple[float, float, float]]:
    a, b, c = (nodes[tag] for tag in tri.nodes)
    edges = (_dist(a, b), _dist(b, c), _dist(c, a))
    s = 0.5 * sum(edges)
    area = math.sqrt(max(s * (s - edges[0]) * (s - edges[1]) * (s - edges[2]), 0.0))
    if area <= 0.0:
        raise ScaleAuditError(f"degenerate triangle {tri.nodes}")
    return area, edges


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        raise ScaleAuditError("cannot compute statistics of empty data")
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def mesh_stats(path: Path, physical_name: str = "plasma") -> dict[str, Any]:
    text = path.read_text(errors="strict")
    physical = _physical_tag(text, physical_name)
    surfaces = _surface_entities_with_physical(text, physical)
    nodes = _nodes(text)
    triangles = _plasma_triangles(text, surfaces)
    h_eq: list[float] = []
    edges_all: list[float] = []
    edge_owners: Counter[tuple[int, int]] = Counter()
    geometry = []
    used_nodes: set[int] = set()
    for tri in triangles:
        area, edges = _triangle_geometry(tri, nodes)
        geometry.append((tri, area, edges))
        h_eq.append(math.sqrt(4.0 * area / math.sqrt(3.0)))
        edges_all.extend(edges)
        used_nodes.update(tri.nodes)
        n0, n1, n2 = tri.nodes
        for edge in ((n0, n1), (n1, n2), (n2, n0)):
            edge_owners[tuple(sorted(edge))] += 1
    boundary_altitudes = []
    for tri, area, edges in geometry:
        n0, n1, n2 = tri.nodes
        for edge, length in zip(((n0, n1), (n1, n2), (n2, n0)), edges):
            if edge_owners[tuple(sorted(edge))] == 1:
                boundary_altitudes.append(2.0 * area / length)
    coords = [nodes[tag] for tag in used_nodes]
    spans = {
        axis: max(row[i] for row in coords) - min(row[i] for row in coords)
        for i, axis in enumerate(("x", "y", "z"))
    }
    nonzero = [value for value in spans.values() if value > 0.0]
    return {
        "path": str(path.resolve()),
        "physical_name": physical_name,
        "physical_tag": physical,
        "surface_entities": sorted(surfaces),
        "triangles": len(triangles),
        "nodes": len(used_nodes),
        "bbox_span_m": spans,
        "characteristic_length_m": min(nonzero) if nonzero else max(spans.values()),
        "equivalent_cell_size_m": _stats(h_eq),
        "triangle_edge_length_m": _stats(edges_all),
        "boundary_normal_spacing_m": _stats(boundary_altitudes),
    }


def anchor_scales(
    *, pressure: float, gas_temperature: float, electron_density: float,
    mu_n: float, d_n: float, dt: float, mesh: dict[str, Any] | None,
    rf_frequency: float | None, q11_cross_sections: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Calculate reusable scales from explicit caller-owned physical inputs."""
    if min(pressure, gas_temperature, electron_density, mu_n, d_n, dt) <= 0:
        raise ScaleAuditError("physical inputs and dt must be positive")
    neutral_density = pressure / (KB * gas_temperature)
    mu_e, d_e = mu_n / neutral_density, d_n / neutral_density
    einstein_voltage = d_e / mu_e
    sigma_e = E_CHARGE * electron_density * mu_e
    tau_dr = EPS0 / sigma_e
    lambda_d = math.sqrt(EPS0 * einstein_voltage / (electron_density * E_CHARGE))
    collision_lengths = {}
    for pair, q_si in (q11_cross_sections or {}).items():
        if q_si <= 0:
            raise ScaleAuditError(f"collision cross section must be positive: {pair}")
        collision_lengths[pair] = 1.0 / (math.sqrt(2.0) * neutral_density * q_si)
    numerical: dict[str, Any] = {"dt_s": dt}
    if mesh is not None:
        hstats, wall = mesh["equivalent_cell_size_m"], mesh["boundary_normal_spacing_m"]
        numerical["h_over_lambda_D"] = {k: v / lambda_d for k, v in hstats.items()}
        numerical["wall_spacing_over_lambda_D"] = {k: v / lambda_d for k, v in wall.items()}
        numerical["electron_diffusion_number"] = {k: d_e * dt / (v * v) for k, v in hstats.items()}
        numerical["electron_cell_diffusion_time_s"] = {k: v * v / d_e for k, v in hstats.items()}
    maxwell = {"status": "FREQUENCY_NOT_PROVIDED"}
    if rf_frequency is not None:
        if rf_frequency <= 0:
            raise ScaleAuditError("rf frequency must be positive")
        omega = 2.0 * math.pi * rf_frequency
        maxwell = {
            "status": "ANCHORED", "frequency_hz": rf_frequency,
            "period_s": 1.0 / rf_frequency, "vacuum_wavelength_m": C0 / rf_frequency,
            "conductive_skin_depth_using_sigma_e_m": math.sqrt(2.0 / (omega * MU0 * sigma_e)),
        }
    return {
        "inputs": {"pressure_Pa": pressure, "gas_temperature_K": gas_temperature,
                   "electron_density_m-3": electron_density, "muN": mu_n, "DN": d_n},
        "electron": {"neutral_density_m-3": neutral_density, "mobility_m2_Vs": mu_e,
                     "diffusion_m2_s": d_e, "D_over_mu_V": einstein_voltage,
                     "conductivity_S_m": sigma_e, "dielectric_relaxation_s": tau_dr,
                     "debye_length_m": lambda_d},
        "collision_length_m": collision_lengths,
        "maxwell": maxwell,
        "numerical": numerical,
    }


def build_scale_map(args: argparse.Namespace) -> dict[str, Any]:
    mesh = mesh_stats(args.mesh, args.physical_name) if args.mesh else None
    q11 = None
    if args.q11_json:
        payload = json.loads(args.q11_json.read_text())
        if not isinstance(payload, dict):
            raise ScaleAuditError("--q11-json must contain an object of pair -> cross-section_m2")
        q11 = {str(k): float(v) for k, v in payload.items()}
    return {"schema": 2, "mesh": mesh, "scales": anchor_scales(
        pressure=args.pressure, gas_temperature=args.gas_temperature,
        electron_density=args.electron_density, mu_n=args.mu_n, d_n=args.d_n,
        dt=args.dt, mesh=mesh, rf_frequency=args.rf_frequency,
        q11_cross_sections=q11,
    )}


def print_summary(payload: dict[str, Any]) -> None:
    e = payload["scales"]["electron"]
    print("SCALE_ANALYSIS: PASS")
    print(f"SCALE_NEUTRAL_DENSITY_M3={e['neutral_density_m-3']:.6e}")
    print(f"SCALE_DEBYE_LENGTH_M={e['debye_length_m']:.6e}")
    print(f"SCALE_DIELECTRIC_RELAXATION_S={e['dielectric_relaxation_s']:.6e}")


def self_test() -> int:
    try:
        # Numerical sample only; these are not production defaults or acceptance policy.
        scales = anchor_scales(
            pressure=1.33322, gas_temperature=300.0, electron_density=1.0e16,
            mu_n=1.57e24, d_n=6.64e24, dt=1.0e-4, mesh=None,
            rf_frequency=None,
        )
        e = scales["electron"]
        if not math.isclose(e["neutral_density_m-3"], 3.2188243837982474e20, rel_tol=1e-12):
            raise AssertionError("neutral density calculation drift")
        if not math.isclose(e["debye_length_m"], 1.5288095309770667e-4, rel_tol=1e-12):
            raise AssertionError("Debye length calculation drift")
    except Exception as exc:
        print(f"SCALE_ANALYSIS_SELFTEST: FAIL ({exc})")
        return 1
    print("SCALE_ANALYSIS_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", type=Path)
    parser.add_argument("--physical-name", default="plasma")
    parser.add_argument("--pressure", type=float, required=False)
    parser.add_argument("--gas-temperature", type=float, required=False)
    parser.add_argument("--electron-density", type=float, required=False)
    parser.add_argument("--mu-n", type=float, required=False)
    parser.add_argument("--d-n", type=float, required=False)
    parser.add_argument("--dt", type=float, required=False)
    parser.add_argument("--rf-frequency", type=float)
    parser.add_argument("--q11-json", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    required = ("pressure", "gas_temperature", "electron_density", "mu_n", "d_n", "dt")
    missing = [name.replace("_", "-") for name in required if getattr(args, name) is None]
    if missing:
        parser.error("explicit physical inputs required: " + ", ".join("--" + name for name in missing))
    try:
        payload = build_scale_map(args)
        print_summary(payload)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except (OSError, ScaleAuditError, ValueError, json.JSONDecodeError) as exc:
        print(f"SCALE_ANALYSIS_FATAL: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
