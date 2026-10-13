#!/usr/bin/env python3
"""Finalize the full-geometry Issue #3 dielectric pilot.

The QVT mesh remains geometrically identical, but its linear elements are
converted to second-order elements so the narrow focus-ring plasma face gains
an interior edge DOF between grounded conductor corners. The electrostatic
potential is then solved with quadratic Lagrange shape functions. Passive QVT
blocks intentionally carrying no nonlinear variables are excluded from global
kernel/material coverage checks.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected one match, found {n}")
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    text = args.input.read_text()

    focus_mesh_tail = """  [focus_surface_block]\n    type = LowerDBlockFromSidesetGenerator\n    input = wafer_surface_block\n    sidesets = plasma_focus_ring\n    new_block_id = 132\n    new_block_name = focus_surface\n  []\n[]"""
    second_order_tail = """  [focus_surface_block]\n    type = LowerDBlockFromSidesetGenerator\n    input = wafer_surface_block\n    sidesets = plasma_focus_ring\n    new_block_id = 132\n    new_block_name = focus_surface\n  []\n  [second_order_mesh]\n    type = ElementOrderConversionGenerator\n    input = focus_surface_block\n    conversion_type = SECOND_ORDER_NONFULL\n  []\n[]"""
    text = replace_once(text, focus_mesh_tail, second_order_tail, "second-order mesh conversion")

    potential_first = """  [potential]\n    family = LAGRANGE\n    order = FIRST\n    initial_condition = 0.0\n    block = 'plasma cover wafer focus_ring'\n  []"""
    potential_second = potential_first.replace("order = FIRST", "order = SECOND")
    text = replace_once(text, potential_first, potential_second, "potential order")

    marker = "[GlobalParams]\n"
    problem = """[Problem]\n  kernel_coverage_check = false\n  material_coverage_check = false\n[]\n\n"""
    if "[Problem]" in text:
        raise RuntimeError("full dielectric pilot already contains a Problem block")
    text = replace_once(text, marker, problem + marker, "Problem insertion")

    required = (
        "boundary = 'inlet outlet plasma_electrode plasma_metal plasma_right wafer_electrode_ground focus_electrode_ground'",
        "boundary = plasma_cover\n    surface_charge = sigma_s",
        "boundary = plasma_wafer\n    surface_charge = sigma_wafer",
        "boundary = plasma_focus_ring\n    surface_charge = sigma_focus",
        "block = cover_surface",
        "block = wafer_surface",
        "block = focus_surface",
        "conversion_type = SECOND_ORDER_NONFULL",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"missing full dielectric contract token: {token}")

    grounded_block = text[text.index("  [grounded_potential]\n"):]
    grounded_block = grounded_block[: grounded_block.index("\n  []")]
    for dielectric_face in ("plasma_cover", "plasma_wafer", "plasma_focus_ring"):
        if dielectric_face in grounded_block:
            raise RuntimeError(f"dielectric plasma face must not be grounded: {dielectric_face}")

    args.input.write_text(text)
    print(
        "FULL_DIELECTRIC_FINALIZE_PASS "
        f"sha256={digest(text)} potential_order=SECOND mesh_order=SECOND_ORDER_NONFULL"
    )


if __name__ == "__main__":
    main()
