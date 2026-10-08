#!/usr/bin/env python3
"""Independent complex scalar-RZ FEM reference for Issue #202 M2-G.

This script intentionally does not use MOOSE.  It reads the same Gmsh 4.1 mesh,
assembles the complex weak form directly with scipy.sparse, solves the prescribed-
material chamber case, and reports interpolated complex E_theta values at the
same fixed probes used by chamber_materials.i.

The purpose is cross-solver verification of the standard-object MOOSE
composition, not production plasma physics and not a substitute for COMSOL.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

MU0 = 1.2566370614359173e-6
EPS0 = 8.8541878128e-12
FREQUENCY = 13.56e6
OMEGA = 2.0 * math.pi * FREQUENCY
OMEGA_MU0 = OMEGA * MU0
WAVE_K2 = OMEGA * OMEGA * MU0 * EPS0
I_PEAK = 10.0
COIL_AREA = 0.009 * 0.018
J_COIL = I_PEAK / COIL_AREA
SOURCE = -1j * OMEGA_MU0 * J_COIL

# eps_r, sigma_real, sigma_imag [S/m].  This is the frozen M2-G validation
# fixture, not a claim about the final oxygen-plasma constitutive model.
MATERIALS: dict[str, tuple[float, float, float]] = {
    "plasma": (1.0, 5.0, -10.0),
    "cover": (3.6, 0.0, 0.0),
    "wafer": (12.5, 0.0, 0.0),
    "focus_ring": (8.0, 0.0, 0.0),
    "vacuum": (1.0, 0.0, 0.0),
    "metal": (1.0, 0.0, 0.0),
    "electrode": (1.0, 0.0, 0.0),
    "top": (1.0, 0.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "bottom": (1.0, 0.0, 0.0),
    "port": (1.0, 0.0, 0.0),
    "coil1": (1.0, 0.0, 0.0),
    "coil2": (1.0, 0.0, 0.0),
    "coil3": (1.0, 0.0, 0.0),
}

PROBES: dict[str, tuple[float, float, str]] = {
    "p1": (0.05, 0.15, "plasma"),
    "p2": (0.12, 0.15, "plasma"),
    "p3": (0.20, 0.15, "plasma"),
    "p4": (0.05, 0.28, "plasma"),
    "p5": (0.12, 0.28, "plasma"),
    "p6": (0.20, 0.28, "plasma"),
    "q1": (0.03, 0.33, "cover"),
    "q2": (0.09, 0.33, "cover"),
    "q3": (0.15, 0.33, "cover"),
    "q4": (0.21, 0.33, "cover"),
    "v1": (0.03, 0.39, "vacuum"),
    "v2": (0.09, 0.39, "vacuum"),
    "v3": (0.15, 0.39, "vacuum"),
    "v4": (0.21, 0.39, "vacuum"),
}


class ReferenceError(RuntimeError):
    pass


def _physical_names(lines: list[str]) -> dict[tuple[int, int], str]:
    try:
        i = lines.index("$PhysicalNames")
        n = int(lines[i + 1])
    except (ValueError, IndexError) as exc:
        raise ReferenceError("missing $PhysicalNames") from exc
    out: dict[tuple[int, int], str] = {}
    for raw in lines[i + 2 : i + 2 + n]:
        m = re.match(r'^\s*(\d+)\s+(\d+)\s+"(.*)"\s*$', raw)
        if not m:
            raise ReferenceError(f"malformed physical-name line: {raw}")
        out[(int(m.group(1)), int(m.group(2)))] = m.group(3)
    return out


def _surface_physical_tags(lines: list[str]) -> dict[int, list[int]]:
    try:
        i = lines.index("$Entities")
        npnt, ncurve, nsurf, _nvol = (int(v) for v in lines[i + 1].split())
    except (ValueError, IndexError) as exc:
        raise ReferenceError("missing/unsupported $Entities") from exc
    cursor = i + 2 + npnt + ncurve
    out: dict[int, list[int]] = {}
    for raw in lines[cursor : cursor + nsurf]:
        p = raw.split()
        if len(p) < 8:
            raise ReferenceError("malformed surface entity")
        tag = int(p[0])
        nphys = int(p[7])
        out[tag] = [int(v) for v in p[8 : 8 + nphys]]
    return out


def _nodes(lines: list[str]) -> dict[int, tuple[float, float]]:
    try:
        i = lines.index("$Nodes")
        nblocks = int(lines[i + 1].split()[0])
    except (ValueError, IndexError) as exc:
        raise ReferenceError("missing/unsupported $Nodes") from exc
    cursor = i + 2
    out: dict[int, tuple[float, float]] = {}
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
            out[tag] = (coords[base], coords[base + 1])
    return out


def _triangles(
    lines: list[str], physical_names: dict[tuple[int, int], str], surface_phys: dict[int, list[int]]
) -> list[tuple[tuple[int, int, int], str]]:
    try:
        i = lines.index("$Elements")
        nblocks = int(lines[i + 1].split()[0])
    except (ValueError, IndexError) as exc:
        raise ReferenceError("missing/unsupported $Elements") from exc
    cursor = i + 2
    out: list[tuple[tuple[int, int, int], str]] = []
    tri_corner_count = {2: 3, 9: 3, 21: 3, 23: 3, 25: 3}
    quad_corner_count = {3: 4, 10: 4, 16: 4}
    for _ in range(nblocks):
        dim, entity, etype, n = (int(v) for v in lines[cursor].split())
        cursor += 1
        block_name: str | None = None
        if dim == 2:
            tags = surface_phys.get(entity, [])
            if len(tags) != 1:
                raise ReferenceError(f"surface entity {entity} does not have exactly one physical tag")
            try:
                block_name = physical_names[(2, tags[0])]
            except KeyError as exc:
                raise ReferenceError(f"surface entity {entity} physical tag {tags[0]} is unnamed") from exc
            if block_name not in MATERIALS:
                raise ReferenceError(f"no frozen M2-G material for block {block_name}")
        for raw in lines[cursor : cursor + n]:
            if dim != 2:
                continue
            vals = [int(v) for v in raw.split()]
            if etype in tri_corner_count:
                ids = tuple(vals[1 : 1 + tri_corner_count[etype]])
                out.append((ids, block_name or ""))
            elif etype in quad_corner_count:
                ids = vals[1 : 1 + quad_corner_count[etype]]
                out.append(((ids[0], ids[1], ids[2]), block_name or ""))
                out.append(((ids[0], ids[2], ids[3]), block_name or ""))
            else:
                raise ReferenceError(f"unsupported 2-D Gmsh element type {etype}")
        cursor += n
    if not out:
        raise ReferenceError("no 2-D elements found")
    return out


def load_mesh(path: Path):
    lines = [line.strip() for line in path.read_text().splitlines()]
    physical_names = _physical_names(lines)
    surface_phys = _surface_physical_tags(lines)
    node_by_tag = _nodes(lines)
    triangles = _triangles(lines, physical_names, surface_phys)
    tags = sorted(node_by_tag)
    index = {tag: k for k, tag in enumerate(tags)}
    coords = np.array([node_by_tag[tag] for tag in tags], dtype=float)
    tri_idx = [(tuple(index[tag] for tag in ids), block) for ids, block in triangles]
    return coords, tri_idx


def _element_geometry(xy: np.ndarray):
    x0, y0 = xy[0]
    x1, y1 = xy[1]
    x2, y2 = xy[2]
    det2 = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    area = 0.5 * abs(det2)
    if area <= 0.0:
        raise ReferenceError("degenerate triangle")
    grads = np.array(
        [
            [(y1 - y2) / det2, (x2 - x1) / det2],
            [(y2 - y0) / det2, (x0 - x2) / det2],
            [(y0 - y1) / det2, (x1 - x0) / det2],
        ],
        dtype=float,
    )
    return area, grads


def assemble(coords: np.ndarray, triangles):
    n = len(coords)
    rows: list[int] = []
    cols: list[int] = []
    vals: list[complex] = []
    rhs = np.zeros(n, dtype=complex)
    qps = np.array(
        [
            [2.0 / 3.0, 1.0 / 6.0, 1.0 / 6.0],
            [1.0 / 6.0, 2.0 / 3.0, 1.0 / 6.0],
            [1.0 / 6.0, 1.0 / 6.0, 2.0 / 3.0],
        ],
        dtype=float,
    )
    for ids, block in triangles:
        loc = np.array(ids, dtype=int)
        xy = coords[loc]
        area, grads = _element_geometry(xy)
        rbar = float(np.mean(xy[:, 0]))
        ke = area * rbar * (grads @ grads.T)
        fe = np.zeros(3, dtype=complex)
        eps_r, sigma_r, sigma_i = MATERIALS[block]
        for lam in qps:
            r = float(lam @ xy[:, 0])
            if r <= 0.0:
                raise ReferenceError("quadrature point reached nonpositive radius")
            a = 1.0 / (r * r) - WAVE_K2 * eps_r - OMEGA_MU0 * sigma_i
            b = OMEGA_MU0 * sigma_r
            coef = complex(a, b)
            w = area / 3.0
            ke = ke + (w * r * coef) * np.outer(lam, lam)
            if block in {"coil1", "coil2", "coil3"}:
                fe = fe + w * r * SOURCE * lam
        for a_local, a_global in enumerate(loc):
            rhs[a_global] += fe[a_local]
            for b_local, b_global in enumerate(loc):
                rows.append(int(a_global))
                cols.append(int(b_global))
                vals.append(complex(ke[a_local, b_local]))
    mat = coo_matrix((np.asarray(vals, dtype=complex), (rows, cols)), shape=(n, n)).tocsr()
    return mat, rhs


def solve(coords: np.ndarray, mat, rhs: np.ndarray):
    x = coords[:, 0]
    y = coords[:, 1]
    boundary = (
        np.isclose(x, 0.0, atol=1e-12)
        | np.isclose(x, 0.2565, atol=1e-10)
        | np.isclose(y, 0.0, atol=1e-12)
        | np.isclose(y, 0.45, atol=1e-10)
    )
    free = np.flatnonzero(~boundary)
    if len(free) == 0:
        raise ReferenceError("no free degrees of freedom")
    sol = np.zeros(len(coords), dtype=complex)
    sub = mat[free][:, free]
    sol[free] = spsolve(sub, rhs[free])
    residual = mat @ sol - rhs
    rel_res = float(np.linalg.norm(residual[free]) / max(np.linalg.norm(rhs[free]), 1e-30))
    return sol, boundary, rel_res


def _barycentric(point: tuple[float, float], xy: np.ndarray) -> np.ndarray | None:
    x, y = point
    x0, y0 = xy[0]
    x1, y1 = xy[1]
    x2, y2 = xy[2]
    det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(det) < 1e-30:
        return None
    l0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / det
    l1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / det
    l2 = 1.0 - l0 - l1
    lam = np.array([l0, l1, l2], dtype=float)
    if float(np.min(lam)) >= -1e-10 and float(np.max(lam)) <= 1.0 + 1e-10:
        return lam
    return None


def interpolate_probe(point: tuple[float, float], expected_block: str, coords, triangles, sol):
    candidates: list[tuple[complex, str]] = []
    for ids, block in triangles:
        loc = np.array(ids, dtype=int)
        lam = _barycentric(point, coords[loc])
        if lam is not None:
            candidates.append((complex(lam @ sol[loc]), block))
    if not candidates:
        raise ReferenceError(f"probe {point} is outside the mesh")
    same = [item for item in candidates if item[1] == expected_block]
    if not same:
        blocks = sorted({block for _, block in candidates})
        raise ReferenceError(f"probe {point} expected block {expected_block}, found {blocks}")
    values = [value for value, _ in same]
    value = sum(values) / len(values)
    spread = max(abs(v - value) for v in values)
    if spread > 1e-8 * max(abs(value), 1.0):
        raise ReferenceError(f"probe {point} interpolation is nonunique within {expected_block}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    coords, triangles = load_mesh(args.mesh)
    mat, rhs = assemble(coords, triangles)
    sol, boundary, rel_res = solve(coords, mat, rhs)
    if not math.isfinite(rel_res) or rel_res > 1e-10:
        raise ReferenceError(f"independent sparse solve residual too large: {rel_res:.3e}")

    probes: dict[str, dict[str, float | str]] = {}
    for name, (r, z, expected_block) in PROBES.items():
        value = interpolate_probe((r, z), expected_block, coords, triangles, sol)
        probes[name] = {
            "r_m": r,
            "z_m": z,
            "block": expected_block,
            "real": float(value.real),
            "imag": float(value.imag),
            "magnitude": float(abs(value)),
            "phase_deg": float(math.degrees(math.atan2(value.imag, value.real))),
        }

    report = {
        "issue": 202,
        "scope": "M2-G independent complex scalar-RZ FEM prescribed-material chamber reference",
        "status": "REFERENCE_GENERATED",
        "scientific_acceptance": False,
        "solver": "independent scipy.sparse complex H1 FEM assembly",
        "phasor": "exp(+i omega t), peak",
        "frequency_Hz": FREQUENCY,
        "I_peak_A": I_PEAK,
        "nodes": int(len(coords)),
        "triangles_after_linearization": int(len(triangles)),
        "dirichlet_nodes": int(np.count_nonzero(boundary)),
        "relative_linear_residual": rel_res,
        "materials": {
            key: {"epsilon_r": v[0], "sigma_real_S_per_m": v[1], "sigma_imag_S_per_m": v[2]}
            for key, v in MATERIALS.items()
        },
        "probes": probes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("PASS: independent M2-G chamber reference generated")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
