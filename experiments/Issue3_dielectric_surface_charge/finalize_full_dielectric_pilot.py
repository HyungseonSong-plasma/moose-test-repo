#!/usr/bin/env python3
"""Finalize the full-geometry Issue #3 dielectric pilot.

This step keeps the plasma/FV mesh unchanged while making the electrostatic
potential quadratic so the narrow focus-ring plasma face has an interior edge
DOF between grounded conductor corners. It also opts out of whole-mesh kernel
and material coverage checks for passive QVT blocks that intentionally carry no
nonlinear variables.
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
    print(f"FULL_DIELECTRIC_FINALIZE_PASS sha256={digest(text)} potential_order=SECOND")


if __name__ == "__main__":
    main()
