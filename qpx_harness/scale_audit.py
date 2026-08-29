"""Quantitative QVT multiphysics space-time scale audit for Issue #43.

The audit deliberately separates:
  * physical characteristic scales,
  * numerical resolution/stiffness indicators, and
  * inter-physics coupling cadence.

It parses the local ASCII Gmsh 4.1 qvt mesh directly so mesh conclusions are
based on the actual plasma discretization rather than reactor-size estimates.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

KB = 1.380649e-23
EPS0 = 8.8541878128e-12
E_CHARGE = 1.602176634e-19
MU0 = 1.25663706212e-6
C0 = 299792458.0

# Accepted oxygen electron-transport anchor used by the real-qvt electron test.
DEFAULT_PRESSURE = 1.33322
DEFAULT_GAS_TEMPERATURE = 300.0
DEFAULT_ELECTRON_DENSITY = 1.0e16
DEFAULT_MU_N = 1.57e24
DEFAULT_D_N = 6.64e24
DEFAULT_DT = 1.0e-4

# QPX canonical 300 K Q^(1,1) values in the Mutation++ multpi=yes convention.
# QPX converts numeric values to SI as q * pi * 1e-20 m^2.
HEAVY_Q11_300K = {
    "O-O": 8.53,
    "O-O2": 9.10,
    "O2-O2": 11.12,
}

# Common Gmsh element types. Only triangle corner nodes are used for geometric
# statistics, but the node count is needed to validate each element record.
ELEMENT_NODES = {
    1: 2,    # line 2
    2: 3,    # triangle 3
    3: 4,    # quadrangle 4
    8: 3,    # second-order line
    9: 6,    # second-order triangle
    10: 9,   # second-order quadrangle
    15: 1,   # point
    16: 8,   # second-order quadrangle (serendipity)
    20: 9,   # incomplete third-order triangle
    21: 10,  # third-order triangle
    22: 12,
    23: 15,
    24: 15,
    25: 21,
}
TRIANGLE_TYPES = {2, 9, 20, 21, 22, 23, 24, 25}


class ScaleAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class Triangle:
    nodes: tuple[int, int, int]


def _section(text: str, name: str) -> str:
    start_token = f"${name}"
    end_token = f"$End{name}"
    start = text.find(start_token)
    end = text.find(end_token)
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
    try:
        count = int(lines[0])
    except ValueError as exc:
        raise ScaleAuditError("invalid PhysicalNames header") from exc
    matches: list[int] = []
    for line in lines[1 : 1 + count]:
        parts = line.split(maxsplit=2)
        if len(parts) != 3:
            continue
        quoted = parts[2].strip().strip('"')
        if quoted == name:
            matches.append(int(parts[1]))
    if len(matches) != 1:
        raise ScaleAuditError(f"expected one physical group {name!r}, found {len(matches)}")
    return matches[0]


def _surface_entities_with_physical(text: str, physical_tag: int) -> set[int]:
    lines = [line.strip() for line in _section(text, "Entities").splitlines() if line.strip()]
    if not lines:
        raise ScaleAuditError("empty Entities section")
    counts = [int(value) for value in lines[0].split()]
    if len(counts) != 4:
        raise ScaleAuditError("invalid Entities header")
    npoints, ncurves, nsurfaces, _ = counts
    offset = 1 + npoints + ncurves
    surfaces = lines[offset : offset + nsurfaces]
    found: set[int] = set()
    for line in surfaces:
        parts = line.split()
        if len(parts) < 8:
            raise ScaleAuditError(f"malformed surface entity: {line}")
        tag = int(parts[0])
        nphys = int(parts[7])
        phys = [int(value) for value in parts[8 : 8 + nphys]]
        if physical_tag in phys:
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
        pos += 2  # min/max tag
        result: dict[int, tuple[float, float, float]] = {}
        for _ in range(nblocks):
            entity_dim = int(tokens[pos]); pos += 1
            pos += 1  # entity tag
            parametric = int(tokens[pos]); pos += 1
            count = int(tokens[pos]); pos += 1
            tags = [int(tokens[pos + i]) for i in range(count)]
            pos += count
            for tag in tags:
                x = float(tokens[pos]); y = float(tokens[pos + 1]); z = float(tokens[pos + 2])
                pos += 3
                if parametric:
                    pos += entity_dim
                result[tag] = (x, y, z)
    except (IndexError, ValueError) as exc:
        raise ScaleAuditError("failed to parse Gmsh Nodes section") from exc
    if len(result) != nnodes:
        raise ScaleAuditError(f"node count mismatch: parsed {len(result)}, header {nnodes}")
    return result


def _plasma_triangles(text: str, surface_entities: set[int]) -> list[Triangle]:
    lines = [line.strip() for line in _section(text, "Elements").splitlines() if line.strip()]
    if not lines:
        raise ScaleAuditError("empty Elements section")
    header = [int(value) for value in lines[0].split()]
    if len(header) != 4:
        raise ScaleAuditError("invalid Elements header")
    nblocks = header[0]
    idx = 1
    triangles: list[Triangle] = []
    for _ in range(nblocks):
        if idx >= len(lines):
            raise ScaleAuditError("truncated Elements section")
        block = [int(value) for value in lines[idx].split()]
        idx += 1
        if len(block) != 4:
            raise ScaleAuditError(f"invalid element block header: {block}")
        entity_dim, entity_tag, element_type, count = block
        expected_nodes = ELEMENT_NODES.get(element_type)
        for _ in range(count):
            if idx >= len(lines):
                raise ScaleAuditError("truncated element records")
            record = [int(value) for value in lines[idx].split()]
            idx += 1
            if expected_nodes is not None and len(record) != expected_nodes + 1:
                raise ScaleAuditError(
                    f"element type {element_type} expected {expected_nodes} nodes, got {len(record)-1}"
                )
            if entity_dim == 2 and entity_tag in surface_entities and element_type in TRIANGLE_TYPES:
                if len(record) < 4:
                    raise ScaleAuditError("triangle record lacks three corner nodes")
                triangles.append(Triangle((record[1], record[2], record[3])))
    if not triangles:
        raise ScaleAuditError("no plasma triangles found")
    return triangles


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _triangle_geometry(tri: Triangle, nodes: dict[int, tuple[float, float, float]]) -> tuple[float, tuple[float, float, float]]:
    a, b, c = (nodes[tag] for tag in tri.nodes)
    ab = _dist(a, b)
    bc = _dist(b, c)
    ca = _dist(c, a)
    s = 0.5 * (ab + bc + ca)
    area_sq = max(s * (s - ab) * (s - bc) * (s - ca), 0.0)
    area = math.sqrt(area_sq)
    if area <= 0.0:
        raise ScaleAuditError(f"degenerate plasma triangle {tri.nodes}")
    return area, (ab, bc, ca)


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        raise ScaleAuditError("cannot compute statistics of empty data")
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def mesh_stats(path: Path, physical_name: str = "plasma") -> dict[str, Any]:
    text = path.read_text(errors="strict")
    physical = _physical_tag(text, physical_name)
    surfaces = _surface_entities_with_physical(text, physical)
    nodes = _nodes(text)
    triangles = _plasma_triangles(text, surfaces)

    h_eq: list[float] = []
    edges_all: list[float] = []
    edge_owners: Counter[tuple[int, int]] = Counter()
    tri_geom: list[tuple[Triangle, float, tuple[float, float, float]]] = []
    used_nodes: set[int] = set()

    for tri in triangles:
        area, edges = _triangle_geometry(tri, nodes)
        tri_geom.append((tri, area, edges))
        h_eq.append(math.sqrt(4.0 * area / math.sqrt(3.0)))
        edges_all.extend(edges)
        used_nodes.update(tri.nodes)
        n0, n1, n2 = tri.nodes
        for edge in ((n0, n1), (n1, n2), (n2, n0)):
            edge_owners[tuple(sorted(edge))] += 1

    boundary_altitudes: list[float] = []
    for tri, area, edges in tri_geom:
        n0, n1, n2 = tri.nodes
        for edge, length in zip(((n0, n1), (n1, n2), (n2, n0)), edges):
            if edge_owners[tuple(sorted(edge))] == 1:
                boundary_altitudes.append(2.0 * area / length)

    coords = [nodes[tag] for tag in used_nodes]
    x = [value[0] for value in coords]
    y = [value[1] for value in coords]
    z = [value[2] for value in coords]
    spans = {"x": max(x) - min(x), "y": max(y) - min(y), "z": max(z) - min(z)}
    nonzero = [value for value in spans.values() if value > 0.0]
    l_reactor = min(nonzero) if nonzero else max(spans.values())

    return {
        "path": str(path.resolve()),
        "physical_name": physical_name,
        "physical_tag": physical,
        "surface_entities": sorted(surfaces),
        "plasma_triangles": len(triangles),
        "plasma_nodes": len(used_nodes),
        "bbox_span_m": spans,
        "reactor_characteristic_length_m": l_reactor,
        "equivalent_cell_size_m": _stats(h_eq),
        "triangle_edge_length_m": _stats(edges_all),
        "boundary_normal_spacing_m": _stats(boundary_altitudes),
    }


def anchor_scales(
    *,
    pressure: float,
    gas_temperature: float,
    electron_density: float,
    mu_n: float,
    d_n: float,
    dt: float,
    mesh: dict[str, Any] | None,
    rf_frequency: float | None,
) -> dict[str, Any]:
    if pressure <= 0 or gas_temperature <= 0 or electron_density <= 0:
        raise ScaleAuditError("pressure, gas temperature, and electron density must be positive")

    neutral_density = pressure / (KB * gas_temperature)
    mu_e = mu_n / neutral_density
    d_e = d_n / neutral_density
    einstein_voltage = d_e / mu_e
    sigma_e = E_CHARGE * electron_density * mu_e
    tau_dr = EPS0 / sigma_e
    lambda_d = math.sqrt(EPS0 * einstein_voltage / (electron_density * E_CHARGE))

    heavy_collision_lengths: dict[str, dict[str, float]] = {}
    if abs(gas_temperature - 300.0) <= 1e-12:
        for pair, q_numeric in HEAVY_Q11_300K.items():
            q_si = q_numeric * math.pi * 1.0e-20
            length = 1.0 / (math.sqrt(2.0) * neutral_density * q_si)
            heavy_collision_lengths[pair] = {
                "Q11_m2": q_si,
                "diagnostic_collision_length_m": length,
            }

    numerical: dict[str, Any] = {"dt_s": dt}
    if mesh is not None:
        hstats = mesh["equivalent_cell_size_m"]
        wall = mesh["boundary_normal_spacing_m"]
        numerical["h_over_lambda_D"] = {
            key: value / lambda_d for key, value in hstats.items()
        }
        numerical["wall_spacing_over_lambda_D"] = {
            key: value / lambda_d for key, value in wall.items()
        }
        numerical["electron_diffusion_number"] = {
            key: d_e * dt / (value * value) for key, value in hstats.items()
        }
        numerical["electron_cell_diffusion_time_s"] = {
            key: value * value / d_e for key, value in hstats.items()
        }

    maxwell: dict[str, Any] = {
        "status": "PENDING_RF_FREQUENCY",
        "treatment_candidate": "FREQUENCY_DOMAIN_PERIOD_AVERAGED",
    }
    if rf_frequency is not None:
        if rf_frequency <= 0:
            raise ScaleAuditError("rf frequency must be positive")
        omega = 2.0 * math.pi * rf_frequency
        maxwell = {
            "status": "ANCHORED",
            "frequency_hz": rf_frequency,
            "period_s": 1.0 / rf_frequency,
            "vacuum_wavelength_m": C0 / rf_frequency,
            "conductive_skin_depth_using_sigma_e_m": math.sqrt(2.0 / (omega * MU0 * sigma_e)),
            "treatment_candidate": "FREQUENCY_DOMAIN_PERIOD_AVERAGED",
        }

    reactor_kn: dict[str, float] = {}
    if mesh is not None and heavy_collision_lengths:
        lreactor = mesh["reactor_characteristic_length_m"]
        reactor_kn = {
            pair: data["diagnostic_collision_length_m"] / lreactor
            for pair, data in heavy_collision_lengths.items()
        }

    return {
        "anchor": {
            "pressure_Pa": pressure,
            "gas_temperature_K": gas_temperature,
            "electron_density_m-3": electron_density,
            "muN": mu_n,
            "DN": d_n,
        },
        "electron": {
            "neutral_density_m-3": neutral_density,
            "mobility_m2_Vs": mu_e,
            "diffusion_m2_s": d_e,
            "D_over_mu_V": einstein_voltage,
            "conductivity_S_m": sigma_e,
            "dielectric_relaxation_s": tau_dr,
            "debye_length_m": lambda_d,
            "classification": {
                "dielectric_relaxation": "QUASI_STEADY_OR_IMPLICIT_CONSTRAINT_CANDIDATE",
                "electron_transport": "RESOLUTION_AUDIT_REQUIRED",
            },
        },
        "heavy": {
            "Q11_300K_collision_diagnostics": heavy_collision_lengths,
            "reactor_Kn_Q11_diagnostic": reactor_kn,
            "classification": "CONTINUUM_VALIDITY_REQUIRES_LOCAL_GRADIENT_KNUDSEN_AUDIT",
        },
        "poisson": {
            "intrinsic_timestep": None,
            "debye_length_m": lambda_d,
            "classification": "BULK_VS_SHEATH_RESOLVED_MODEL_CONTRACT_REQUIRED",
            "coupling_cadence_owner": "CHARGE_STATE_EVOLUTION",
        },
        "chemistry": {
            "status": "PENDING_REACTION_NETWORK",
            "required_scale": "eigenmodes of J_chem=dR/dn and species lifetime diagnostics",
        },
        "maxwell": maxwell,
        "numerical": numerical,
    }


def decision_map(scales: dict[str, Any], mesh: dict[str, Any] | None) -> list[dict[str, str]]:
    rows = [
        {
            "physics": "electron transport",
            "space": "gradient scale and electron collisional validity",
            "time": "cell/gradient diffusion + drift times",
            "current_treatment": "RESOLVED PDE; timestep/coupling audit required",
            "coupling": "electron-Poisson fast block candidate",
        },
        {
            "physics": "Poisson",
            "space": "Debye/sheath only if explicitly retained",
            "time": "elliptic constraint; no standalone physical dt",
            "current_treatment": "BULK/UNRESOLVED-SHEATH until mesh proves otherwise",
            "coupling": "update/iterate with charge evolution",
        },
        {
            "physics": "heavy transport",
            "space": "reactor/gradient scale after Kn validity gate",
            "time": "advection/diffusion/drift/chemistry",
            "current_treatment": "SLOW RESOLVED LAYER candidate",
            "coupling": "macrostep; field/source cadence by sensitivity",
        },
        {
            "physics": "chemistry",
            "space": "reaction-zone scale",
            "time": "J_chem eigenmodes",
            "current_treatment": "UNCLASSIFIED until network exists",
            "coupling": "partition fast/slow only after Jacobian evidence",
        },
        {
            "physics": "Maxwell",
            "space": "EM wavelength/skin/plasma-power gradients",
            "time": "RF period if transient representation retained",
            "current_treatment": scales["maxwell"]["treatment_candidate"],
            "coupling": "refresh when conductivity/power changes materially",
        },
    ]
    if mesh is None:
        rows[1]["current_treatment"] = "MODEL CONTRACT PENDING ACTUAL MESH AUDIT"
    return rows


def build_scale_map(args: argparse.Namespace) -> dict[str, Any]:
    mesh = mesh_stats(args.mesh, args.physical_name) if args.mesh else None
    scales = anchor_scales(
        pressure=args.pressure,
        gas_temperature=args.gas_temperature,
        electron_density=args.electron_density,
        mu_n=args.mu_n,
        d_n=args.d_n,
        dt=args.dt,
        mesh=mesh,
        rf_frequency=args.rf_frequency,
    )
    return {
        "schema": 1,
        "work": "Issue43 QVT multiphysics scale map",
        "mesh": mesh,
        "scales": scales,
        "map": decision_map(scales, mesh),
        "architecture_hypothesis": {
            "fast_periodic": "frequency-domain Maxwell",
            "fast_plasma": "electron transport + Poisson + fast electron chemistry",
            "slow_reactor": "heavy transport + flow + slow heavy chemistry",
            "promotion_status": "HYPOTHESIS_ONLY_PENDING_RUNTIME_AND_MODEL_VALIDITY_AUDIT",
        },
    }


def _fmt(value: float) -> str:
    return f"{value:.6e}"


def print_summary(payload: dict[str, Any]) -> None:
    scales = payload["scales"]
    e = scales["electron"]
    print("QVT_SCALE_MAP: PASS")
    print(f"QVT_SCALE_TG_K: {scales['anchor']['gas_temperature_K']:.6g}")
    print(f"QVT_SCALE_N_M3: {_fmt(e['neutral_density_m-3'])}")
    print(f"QVT_SCALE_MUE_M2_VS: {_fmt(e['mobility_m2_Vs'])}")
    print(f"QVT_SCALE_DE_M2_S: {_fmt(e['diffusion_m2_s'])}")
    print(f"QVT_SCALE_TAU_DR_S: {_fmt(e['dielectric_relaxation_s'])}")
    print(f"QVT_SCALE_LAMBDA_D_M: {_fmt(e['debye_length_m'])}")
    mesh = payload.get("mesh")
    if mesh:
        h = mesh["equivalent_cell_size_m"]
        wall = mesh["boundary_normal_spacing_m"]
        print(
            "QVT_SCALE_H_EQ_M: "
            f"min={_fmt(h['min'])} median={_fmt(h['median'])} max={_fmt(h['max'])}"
        )
        print(
            "QVT_SCALE_WALL_NORMAL_M: "
            f"min={_fmt(wall['min'])} median={_fmt(wall['median'])} max={_fmt(wall['max'])}"
        )
        rx = scales["numerical"]["h_over_lambda_D"]
        print(
            "QVT_SCALE_H_OVER_LAMBDA_D: "
            f"min={rx['min']:.3f} median={rx['median']:.3f} max={rx['max']:.3f}"
        )
        theta = scales["numerical"]["electron_diffusion_number"]
        print(
            "QVT_SCALE_THETA_DIFF_DT: "
            f"min_h={theta['min']:.6e} median_h={theta['median']:.6e} max_h={theta['max']:.6e}"
        )
    for pair, data in scales["heavy"]["Q11_300K_collision_diagnostics"].items():
        print(f"QVT_SCALE_HEAVY_COLLISION_LENGTH_{pair}: {_fmt(data['diagnostic_collision_length_m'])}")
    print(f"QVT_SCALE_POISSON_CLASS: {scales['poisson']['classification']}")
    print(f"QVT_SCALE_MAXWELL_STATUS: {scales['maxwell']['status']}")


def self_test() -> int:
    try:
        scales = anchor_scales(
            pressure=DEFAULT_PRESSURE,
            gas_temperature=300.0,
            electron_density=DEFAULT_ELECTRON_DENSITY,
            mu_n=DEFAULT_MU_N,
            d_n=DEFAULT_D_N,
            dt=DEFAULT_DT,
            mesh=None,
            rf_frequency=None,
        )
        e = scales["electron"]
        if not math.isclose(e["neutral_density_m-3"], 3.2188243837982474e20, rel_tol=1e-12):
            raise AssertionError("neutral density anchor mismatch")
        if not math.isclose(e["mobility_m2_Vs"], 4877.557184860713, rel_tol=1e-12):
            raise AssertionError("electron mobility anchor mismatch")
        if not math.isclose(e["diffusion_m2_s"], 20628.649495207093, rel_tol=1e-12):
            raise AssertionError("electron diffusion anchor mismatch")
        if not math.isclose(e["dielectric_relaxation_s"], 1.1330158004523579e-12, rel_tol=1e-12):
            raise AssertionError("dielectric relaxation anchor mismatch")
        if not math.isclose(e["debye_length_m"], 1.5288095309770667e-4, rel_tol=1e-12):
            raise AssertionError("Debye length anchor mismatch")
        q = scales["heavy"]["Q11_300K_collision_diagnostics"]
        if not (q["O2-O2"]["diagnostic_collision_length_m"] < q["O-O"]["diagnostic_collision_length_m"]):
            raise AssertionError("heavy collision-length ordering mismatch")
    except Exception as exc:
        print(f"QVT_SCALE_SELFTEST: FAIL ({exc})")
        return 1
    print("QVT_SCALE_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", type=Path, help="local ASCII Gmsh 4.1 qvt.msh")
    parser.add_argument("--physical-name", default="plasma")
    parser.add_argument("--pressure", type=float, default=DEFAULT_PRESSURE)
    parser.add_argument("--gas-temperature", type=float, default=DEFAULT_GAS_TEMPERATURE)
    parser.add_argument("--electron-density", type=float, default=DEFAULT_ELECTRON_DENSITY)
    parser.add_argument("--mu-n", type=float, default=DEFAULT_MU_N)
    parser.add_argument("--d-n", type=float, default=DEFAULT_D_N)
    parser.add_argument("--dt", type=float, default=DEFAULT_DT)
    parser.add_argument("--rf-frequency", type=float)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    try:
        payload = build_scale_map(args)
        print_summary(payload)
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            print(f"QVT_SCALE_JSON: {args.json_out.resolve()}")
    except (OSError, ScaleAuditError, ValueError) as exc:
        print(f"QVT_SCALE_FATAL: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
