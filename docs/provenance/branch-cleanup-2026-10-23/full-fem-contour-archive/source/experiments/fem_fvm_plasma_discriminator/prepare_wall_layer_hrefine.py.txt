#!/usr/bin/env python3
from pathlib import Path

import prepare_cases as base
import prepare_hybrid_1ns as hybrid

REFINED_BOUNDARIES = "plasma_right plasma_focus_ring"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def wall_layer_hrefine() -> str:
    text = hybrid.hybrid_1ns()

    old_mesh_tail = r'''  [plasma_only]
    type = BlockDeletionGenerator
    input = plasma_focus_ring
    operation = keep
    block = plasma
  []
[]
'''

    new_mesh_tail = f'''  [plasma_only]\n    type = BlockDeletionGenerator\n    input = plasma_focus_ring\n    operation = keep\n    block = plasma\n  []\n  [refine_wall_layer]\n    type = RefineSidesetGenerator\n    input = plasma_only\n    boundaries = '{REFINED_BOUNDARIES}'\n    refinement = '1 1'\n    boundary_side = 'primary primary'\n    enable_neighbor_refinement = true\n    show_info = true\n  []\n[]\n'''

    return replace_once(text, old_mesh_tail, new_mesh_tail, "plasma-only mesh tail")


if __name__ == "__main__":
    out = Path(base.HERE) / "hybrid_wall_layer_hrefine.i"
    out.write_text(wall_layer_hrefine(), encoding="utf-8")
    print(f"wrote {out}")
    print(f"refined boundaries={REFINED_BOUNDARIES}")
    print("refinement=1 level using MOOSE RefineSidesetGenerator")
    print("boundary_side=primary: refine plasma-side wall-adjacent cells")
    print("neighbor refinement enabled for supported conformity")
    print("physics identical to reconstructed-rho 1 ns hybrid baseline")
