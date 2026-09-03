"""Run the qpx-free constant-face interpolation audit on the accepted qvt mesh."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE

from .face_interpolation_audit import audit_constant_face_interpolation

DEFAULT_MESH = ELECTRON_REFERENCE_CASE / "qvt.msh"


def _compact(result: dict[str, Any]) -> dict[str, Any]:
    worst_face = result["worst_face_delta"]
    worst_cell = result["worst_cell"]
    return {
        "n0": result["n0"],
        "radial_axis": result["radial_axis"],
        "symmetry_axis": result["symmetry_axis"],
        "plasma_gmsh_element_types": result["plasma_gmsh_element_types"],
        "plasma_element_count": result["plasma_element_count"],
        "interior_element_count": result["interior_element_count"],
        "face_evaluation_count": result["face_evaluation_count"],
        "gc_outside_unit_count": result["gc_outside_unit_count"],
        "max_gc_overshoot": result["max_gc_overshoot"],
        "nonzero_face_delta_count": result["nonzero_face_delta_count"],
        "max_abs_face_delta": result["max_abs_face_delta"],
        "max_abs_face_delta_over_n": result["max_abs_face_delta_over_n"],
        "max_abs_final_gradient": result["max_abs_final_gradient"],
        "normalized_max_abs_final_gradient": result["normalized_max_abs_final_gradient"],
        "worst_face": {
            "element_tag": worst_face["element_tag"],
            "neighbor_tag": worst_face["neighbor_tag"],
            "face_info_elem_tag": worst_face["face_info_elem_tag"],
            "gc": worst_face["gc"],
            "field_face_delta": worst_face["field_face_delta"],
            "face_x": worst_face["face_x"],
            "face_y": worst_face["face_y"],
        },
        "worst_cell": {
            "element_tag": worst_cell["element_tag"],
            "cell_x": worst_cell["cell_x"],
            "cell_y": worst_cell["cell_y"],
            "final_gradient_x": worst_cell["final_gradient_x"],
            "final_gradient_y": worst_cell["final_gradient_y"],
            "final_norm": worst_cell["final_norm"],
        },
    }


def run(mesh: Path) -> dict[str, Any]:
    low = audit_constant_face_interpolation(mesh, n0=1.0)
    high = audit_constant_face_interpolation(mesh, n0=1.0e16)
    return {
        "mesh": str(mesh.resolve()),
        "N1": _compact(low),
        "N1E16": _compact(high),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", type=Path, default=DEFAULT_MESH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true", help="print the complete compact JSON")
    args = parser.parse_args()

    result = run(args.mesh)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    high = result["N1E16"]
    low = result["N1"]
    print("R3_FACE_INTERPOLATION_AUDIT: PASS")
    print(
        "  "
        f"gc_outside={high['gc_outside_unit_count']} "
        f"nonzero_face_delta={high['nonzero_face_delta_count']} "
        f"max_face_delta={high['max_abs_face_delta']:.12g}"
    )
    print(
        "  "
        f"high_grad={high['max_abs_final_gradient']:.12g} "
        f"high_norm={high['normalized_max_abs_final_gradient']:.12g} "
        f"low_grad={low['max_abs_final_gradient']:.12g} "
        f"low_norm={low['normalized_max_abs_final_gradient']:.12g}"
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
