#!/usr/bin/env python3
from pathlib import Path

import prepare_cases as base
import prepare_hybrid_1ns as hybrid

TARGET_ELEMENT_ID = 2237
TEMP_BLOCK_ID = 999


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def local_hrefine_2237() -> str:
    text = hybrid.hybrid_1ns()

    old_mesh_tail = r'''  [plasma_only]
    type = BlockDeletionGenerator
    input = plasma_focus_ring
    operation = keep
    block = plasma
  []
[]
'''

    new_mesh_tail = f'''  [plasma_only]\n    type = BlockDeletionGenerator\n    input = plasma_focus_ring\n    operation = keep\n    block = plasma\n  []\n  [mark_target_element]\n    type = SubdomainPerElementGenerator\n    input = plasma_only\n    element_ids = '{TARGET_ELEMENT_ID}'\n    subdomain_ids = '{TEMP_BLOCK_ID}'\n  []\n  [refine_target_element]\n    type = RefineBlockGenerator\n    input = mark_target_element\n    block = '{TEMP_BLOCK_ID}'\n    refinement = '1'\n    enable_neighbor_refinement = true\n  []\n  [restore_plasma_block]\n    type = RenameBlockGenerator\n    input = refine_target_element\n    old_block = '{TEMP_BLOCK_ID}'\n    new_block = 'plasma'\n  []\n[]\n'''

    return replace_once(text, old_mesh_tail, new_mesh_tail, "plasma-only mesh tail")


if __name__ == "__main__":
    out = Path(base.HERE) / "hybrid_local_hrefine_2237.i"
    out.write_text(local_hrefine_2237(), encoding="utf-8")
    print(f"wrote {out}")
    print(f"target element id={TARGET_ELEMENT_ID}")
    print("refinement=1 level using standard MOOSE/libMesh h-refinement")
    print("neighbor refinement enabled for supported local conformity")
    print("physics identical to reconstructed-rho 1 ns hybrid baseline")
