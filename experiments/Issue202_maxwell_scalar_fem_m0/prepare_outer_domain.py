#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

CASE = Path(__file__).resolve().parent
SOURCE_MESH = CASE.parent / "Issue18_qvt_plasma_mapping" / "qvt.msh"
SOURCE_INPUT = CASE / "input.i"
OUT = CASE / "results_outer"

# The original qvt mesh already contains explicit top/right/bottom outer-buffer
# blocks.  These coordinates are the *inner* interfaces of those buffers and
# are frozen during this study.
R_INNER = 0.243
R_OUTER_0 = 0.2565
Z_BOTTOM_INNER = 0.018
Z_BOTTOM_0 = 0.0
Z_TOP_INNER = 0.432
Z_TOP_0 = 0.45
FACTORS = (1, 2, 4, 8)
TOL = 1.0e-12


def map_xyz(x: float, y: float, z: float, factor: float) -> tuple[float, float, float]:
    # Preserve all physical geometry at and inside the buffer interfaces.
    # Only nodes in the existing outer buffer are stretched away from the
    # device.  The corner naturally receives both radial and axial mappings.
    if x > R_INNER + TOL:
        x = R_INNER + factor * (x - R_INNER)
    if y < Z_BOTTOM_INNER - TOL:
        y = Z_BOTTOM_INNER - factor * (Z_BOTTOM_INNER - y)
    elif y > Z_TOP_INNER + TOL:
        y = Z_TOP_INNER + factor * (y - Z_TOP_INNER)
    return x, y, z


def transform_nodes(text: str, factor: float) -> tuple[str, dict[str, float | int]]:
    lines = text.splitlines()
    try:
        start = lines.index("$Nodes")
        end = lines.index("$EndNodes", start + 1)
    except ValueError as exc:
        raise SystemExit(f"invalid Gmsh file: missing Nodes section: {exc}")

    header = lines[start + 1].split()
    if len(header) != 4:
        raise SystemExit(f"unexpected Gmsh 4.1 node header: {lines[start + 1]!r}")
    nblocks, nnodes = int(header[0]), int(header[1])

    i = start + 2
    moved = 0
    seen = 0
    min_x = float("inf")
    max_x = float("-inf")
    min_y = float("inf")
    max_y = float("-inf")

    for _ in range(nblocks):
        block = lines[i].split()
        if len(block) != 4:
            raise SystemExit(f"unexpected node-block header: {lines[i]!r}")
        _entity_dim, _entity_tag, parametric, nblock = map(int, block)
        i += 1

        # Node tags precede coordinates in Gmsh 4.1 ASCII.
        i += nblock
        for _ in range(nblock):
            vals = lines[i].split()
            if len(vals) < 3:
                raise SystemExit(f"unexpected node coordinate record: {lines[i]!r}")
            x0, y0, z0 = map(float, vals[:3])
            x1, y1, z1 = map_xyz(x0, y0, z0, factor)
            if abs(x1 - x0) > TOL or abs(y1 - y0) > TOL or abs(z1 - z0) > TOL:
                moved += 1
            rest = vals[3:]
            lines[i] = " ".join([f"{x1:.17g}", f"{y1:.17g}", f"{z1:.17g}", *rest])
            min_x, max_x = min(min_x, x1), max(max_x, x1)
            min_y, max_y = min(min_y, y1), max(max_y, y1)
            seen += 1
            i += 1

            # Parametric coordinates, when present, are on the same record in
            # this mesh family and are deliberately preserved in `rest`.
            _ = parametric

    if i != end:
        raise SystemExit(f"node parser ended at line {i}, expected $EndNodes at {end}")
    if seen != nnodes:
        raise SystemExit(f"node count mismatch: parsed {seen}, header says {nnodes}")

    stats: dict[str, float | int] = {
        "nodes": nnodes,
        "moved_nodes": moved,
        "r_min": min_x,
        "r_max": max_x,
        "z_min": min_y,
        "z_max": max_y,
    }
    return "\n".join(lines) + "\n", stats


def inject_probe_block(text: str) -> str:
    marker = """  [E_imag_probe_r20]\n    type = PointValue\n    variable = E_imag\n    point = '0.20 0.225 0'\n  []\n[]\n\n[Preconditioning]"""
    replacement = """  [E_imag_probe_r20]\n    type = PointValue\n    variable = E_imag\n    point = '0.20 0.225 0'\n  []\n\n  # Additional fixed internal probes for outer-domain sensitivity.\n  [E_imag_probe_upper_r05]\n    type = PointValue\n    variable = E_imag\n    point = '0.05 0.390 0'\n  []\n  [E_imag_probe_upper_r12]\n    type = PointValue\n    variable = E_imag\n    point = '0.12 0.390 0'\n  []\n  [E_imag_probe_upper_r18]\n    type = PointValue\n    variable = E_imag\n    point = '0.18 0.390 0'\n  []\n[]\n\n[Preconditioning]"""
    if marker not in text:
        raise SystemExit("cannot inject outer-domain probes: baseline marker not found")
    return text.replace(marker, replacement, 1)


def make_input(base: str, factor: int, rmax: float, zmin: float, zmax: float) -> str:
    out = base
    old_file = "file = '../Issue18_qvt_plasma_mapping/qvt.msh'"
    new_file = f"file = 'outer_{factor}.msh'"
    if old_file not in out:
        raise SystemExit("baseline mesh-file marker not found")
    out = out.replace(old_file, new_file, 1)

    old_right = "combinatorial_geometry = 'abs(x - 0.2565) < 1e-10'"
    old_bottom = "combinatorial_geometry = 'abs(y) < 1e-12'"
    old_top = "combinatorial_geometry = 'abs(y - 0.45) < 1e-10'"
    replacements = {
        old_right: f"combinatorial_geometry = 'abs(x - {rmax:.17g}) < 1e-10'",
        old_bottom: f"combinatorial_geometry = 'abs(y - {zmin:.17g}) < 1e-10'",
        old_top: f"combinatorial_geometry = 'abs(y - {zmax:.17g}) < 1e-10'",
    }
    for old, new in replacements.items():
        if old not in out:
            raise SystemExit(f"baseline boundary marker not found: {old}")
        out = out.replace(old, new, 1)
    return inject_probe_block(out)


def main() -> None:
    source_mesh = SOURCE_MESH.read_text(encoding="utf-8")
    source_input = SOURCE_INPUT.read_text(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, object] = {
        "frozen_inner_interfaces_m": {
            "r": R_INNER,
            "z_bottom": Z_BOTTOM_INNER,
            "z_top": Z_TOP_INNER,
        },
        "cases": {},
    }

    for factor in FACTORS:
        mesh_text, stats = transform_nodes(source_mesh, factor)
        rmax = R_INNER + factor * (R_OUTER_0 - R_INNER)
        zmin = Z_BOTTOM_INNER - factor * (Z_BOTTOM_INNER - Z_BOTTOM_0)
        zmax = Z_TOP_INNER + factor * (Z_TOP_0 - Z_TOP_INNER)

        # These are strong guards against accidentally moving the device or
        # interpreting the scale factor as a whole-domain scale.
        if abs(float(stats["r_max"]) - rmax) > 1e-10:
            raise SystemExit(f"factor {factor}: unexpected r_max {stats['r_max']} != {rmax}")
        if abs(float(stats["z_min"]) - zmin) > 1e-10:
            raise SystemExit(f"factor {factor}: unexpected z_min {stats['z_min']} != {zmin}")
        if abs(float(stats["z_max"]) - zmax) > 1e-10:
            raise SystemExit(f"factor {factor}: unexpected z_max {stats['z_max']} != {zmax}")

        mesh_path = OUT / f"outer_{factor}.msh"
        input_path = OUT / f"outer_{factor}.i"
        mesh_path.write_text(mesh_text, encoding="utf-8")
        input_path.write_text(make_input(source_input, factor, rmax, zmin, zmax), encoding="utf-8")

        manifest["cases"][str(factor)] = {
            "factor": factor,
            "mesh": mesh_path.name,
            "input": input_path.name,
            "outer_r_m": rmax,
            "outer_zmin_m": zmin,
            "outer_zmax_m": zmax,
            **stats,
        }

    (OUT / "outer_domain_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("PASS: prepared Issue #202 outer-domain variants")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
