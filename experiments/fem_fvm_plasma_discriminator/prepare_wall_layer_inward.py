#!/usr/bin/env python3
import argparse
from pathlib import Path

import prepare_cases as base
import prepare_hybrid_1ns as hybrid

REFINED_BOUNDARIES = "plasma_right plasma_focus_ring"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def inward_layer_case(layers: int) -> str:
    if layers < 1:
        raise ValueError("layers must be >= 1")

    text = hybrid.hybrid_1ns()

    old_mesh_tail = r'''  [plasma_only]
    type = BlockDeletionGenerator
    input = plasma_focus_ring
    operation = keep
    block = plasma
  []
[]
'''

    new_mesh_tail = f'''  [plasma_only]\n    type = BlockDeletionGenerator\n    input = plasma_focus_ring\n    operation = keep\n    block = plasma\n  []\n  [refine_wall_layers]\n    type = PhysicsBoundaryLayerRefineGenerator\n    input = plasma_only\n    boundaries = '{REFINED_BOUNDARIES}'\n    layers = {layers}\n    enable_neighbor_refinement = true\n    show_info = true\n  []\n[]\n'''

    text = replace_once(text, old_mesh_tail, new_mesh_tail, "plasma-only mesh tail")

    problem = """[Problem]
  type = PhysicsCoarseP1ConstraintProblem
  coarse_p1_variable = potential
  coarse_p1_auto_detect_refinement_midpoints = true
[]

"""
    marker = "[Mesh]\n"
    if text.count(marker) != 1:
        raise RuntimeError(f"expected exactly one Mesh marker, found {text.count(marker)}")
    return text.replace(marker, problem + marker, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a one-step hybrid case with N inward refined FV wall layers and coarse-P1 potential."
    )
    parser.add_argument("--layers", type=int, required=True)
    args = parser.parse_args()

    out = Path(base.HERE) / f"hybrid_wall_layer_L{args.layers}_coarse_p1.i"
    out.write_text(inward_layer_case(args.layers), encoding="utf-8")
    print(f"wrote {out}")
    print(f"refined boundaries={REFINED_BOUNDARIES}")
    print(f"inward topological layers={args.layers}")
    print("FV transport: selected cumulative wall layers h-refined exactly one level")
    print("FEM potential: original coarse-P1 space retained by automatic DofMap midpoint constraints")
    print("native libMesh hanging-node constraints retained at refined/unrefined interface")
    print(f"dt={base.DT} s; one step")


if __name__ == "__main__":
    main()
