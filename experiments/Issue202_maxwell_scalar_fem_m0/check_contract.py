#!/usr/bin/env python3
from __future__ import annotations

import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = Path(__file__).resolve().parent
MESH = ROOT / "experiments/Issue18_qvt_plasma_mapping/qvt.msh"
INPUT = CASE / "input.i"

COILS = ("coil1", "coil2", "coil3")
EXPECTED_DR = 0.009
EXPECTED_DZ = 0.018
EXPECTED_AREA = EXPECTED_DR * EXPECTED_DZ
MU0 = 4.0 * math.pi * 1e-7


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def parse_physical_names(lines: list[str]) -> dict[str, tuple[int, int]]:
    try:
        start = lines.index("$PhysicalNames")
        end = lines.index("$EndPhysicalNames")
    except ValueError as exc:
        fail(f"missing PhysicalNames section: {exc}")
    count = int(lines[start + 1])
    entries = lines[start + 2 : end]
    if len(entries) != count:
        fail(f"PhysicalNames count mismatch: expected {count}, got {len(entries)}")
    out: dict[str, tuple[int, int]] = {}
    pat = re.compile(r'^(\d+)\s+(\d+)\s+"([^"]+)"$')
    for line in entries:
        m = pat.match(line.strip())
        if not m:
            fail(f"cannot parse PhysicalNames line: {line}")
        dim, tag, name = int(m.group(1)), int(m.group(2)), m.group(3)
        out[name] = (dim, tag)
    return out


def parse_surface_bboxes(
    lines: list[str], physical: dict[str, tuple[int, int]]
) -> dict[str, tuple[float, float, float, float]]:
    try:
        start = lines.index("$Entities")
    except ValueError:
        fail("missing Entities section")
    npoints, ncurves, nsurfaces, _ = map(int, lines[start + 1].split())
    cursor = start + 2 + npoints + ncurves

    wanted = {physical[name][1]: name for name in COILS}
    found: dict[str, tuple[float, float, float, float]] = {}
    for line in lines[cursor : cursor + nsurfaces]:
        tok = line.split()
        if len(tok) < 9:
            fail(f"cannot parse surface entity: {line}")
        xmin, ymin, _zmin = map(float, tok[1:4])
        xmax, ymax, _zmax = map(float, tok[4:7])
        nphys = int(tok[7])
        phys_tags = [int(v) for v in tok[8 : 8 + nphys]]
        for tag in phys_tags:
            if tag in wanted:
                found[wanted[tag]] = (xmin, xmax, ymin, ymax)
    return found


def numeric_assignment(text: str, name: str) -> float:
    m = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*([0-9.eE+-]+)\s*$", text)
    if not m:
        fail(f"missing simple numeric assignment for {name}")
    return float(m.group(1))


def main() -> None:
    mesh_text = MESH.read_text()
    input_text = INPUT.read_text()
    lines = mesh_text.splitlines()

    physical = parse_physical_names(lines)
    for name in COILS:
        if name not in physical:
            fail(f"{name} physical group missing")
        dim, _ = physical[name]
        if dim != 2:
            fail(f"{name} must be a 2D RZ block, got dim={dim}")

    boxes = parse_surface_bboxes(lines, physical)
    if set(boxes) != set(COILS):
        fail(f"coil surface mapping incomplete: {boxes}")

    areas = {}
    for name in COILS:
        xmin, xmax, ymin, ymax = boxes[name]
        dr = xmax - xmin
        dz = ymax - ymin
        area = dr * dz
        areas[name] = area
        if not math.isclose(dr, EXPECTED_DR, rel_tol=0.0, abs_tol=1e-12):
            fail(f"{name} radial width {dr} != {EXPECTED_DR}")
        if not math.isclose(dz, EXPECTED_DZ, rel_tol=0.0, abs_tol=1e-12):
            fail(f"{name} axial height {dz} != {EXPECTED_DZ}")
        if not math.isclose(area, EXPECTED_AREA, rel_tol=0.0, abs_tol=1e-15):
            fail(f"{name} cross-section {area} != {EXPECTED_AREA}")

    required_tokens = (
        "coord_type = RZ",
        "rz_coord_axis = Y",
        "expression = '-(1/(x*x) - k2)'",
        "type = MatReaction",
        "type = MatCoupledForce",
        "source_imag = ${fparse -omega*mu0*J_coil}",
        "block = coil1",
        "block = coil2",
        "block = coil3",
    )
    for token in required_tokens:
        if token not in input_text:
            fail(f"missing input contract token: {token}")

    for name in COILS:
        block = re.search(
            rf"\[{name}_current\](.*?)\n\s*\[\]",
            input_text,
            flags=re.S,
        )
        if not block:
            fail(f"missing {name}_current kernel")
        body = block.group(1)
        if "type = BodyForce" not in body or f"block = {name}" not in body:
            fail(f"{name}_current is not an independent BodyForce on {name}")
        if "value = ${source_imag}" not in body:
            fail(f"{name}_current does not share the canonical source_imag")

    forbidden = (
        "sigma_copper",
        "copper_conductivity",
        "skin_effect",
        "external_circuit",
    )
    for token in forbidden:
        if token in input_text:
            fail(f"baseline unexpectedly enables deferred coil physics: {token}")

    freq = numeric_assignment(input_text, "frequency")
    i_peak = numeric_assignment(input_text, "I_peak")
    area = next(iter(areas.values()))
    j_coil = i_peak / area
    omega = 2.0 * math.pi * freq
    source_imag = -omega * MU0 * j_coil

    centers = {
        name: 0.5 * (boxes[name][0] + boxes[name][1])
        for name in COILS
    }

    print("PASS: Issue #202 scalar-RZ FEM coil contract")
    print(f"  frequency_Hz={freq:.12g}")
    print(f"  I_peak_A={i_peak:.12g}")
    print(f"  turn_area_m2={area:.12g}")
    print(f"  J_theta_A_m2={j_coil:.12g}")
    print(f"  source_imag_SI={source_imag:.12g}")
    for name in COILS:
        print(f"  {name}: r_center_m={centers[name]:.12g}, area_m2={areas[name]:.12g}")


if __name__ == "__main__":
    main()
