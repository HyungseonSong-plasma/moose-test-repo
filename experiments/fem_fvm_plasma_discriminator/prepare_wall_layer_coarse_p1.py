#!/usr/bin/env python3
from pathlib import Path

import prepare_cases as base
import prepare_wall_layer_hrefine as wall

# MOOSE/libMesh node ids are zero-based. These are the only two independent
# interior edge-midpoint potential nodes introduced by the deterministic
# plasma_right + plasma_focus_ring one-level TRI3 refinement. All other new
# potential nodes are either hanging-node constrained by libMesh or grounded
# wall nodes.
#
# Exodus node map (1-based) -> libMesh id (0-based):
#   midpoint 1318 of coarse edge (13,1236) -> 1317 of (12,1235)
#   midpoint 1325 of coarse edge (13,1238) -> 1324 of (12,1237)
COARSE_P1_CONSTRAINTS = (
    (1317, (12, 1235)),
    (1324, (12, 1237)),
)


def coarse_p1_potential() -> str:
    text = wall.wall_layer_hrefine()

    blocks = ["[Constraints]"]
    for secondary, primary in COARSE_P1_CONSTRAINTS:
        blocks.append(
            f"""  [coarse_p1_phi_{secondary}]
    type = LinearNodalConstraint
    variable = potential
    primary = '{primary[0]} {primary[1]}'
    secondary_node_ids = '{secondary}'
    weights = '0.5 0.5'
    formulation = kinematic
    penalty = 1.0
  []"""
        )
    blocks.append("[]")
    constraints = "\n".join(blocks) + "\n\n"

    marker = "[Postprocessors]\n"
    if text.count(marker) != 1:
        raise RuntimeError(f"expected exactly one Postprocessors marker, found {text.count(marker)}")
    return text.replace(marker, constraints + marker, 1)


if __name__ == "__main__":
    out = Path(base.HERE) / "hybrid_wall_layer_coarse_p1.i"
    out.write_text(coarse_p1_potential(), encoding="utf-8")
    print(f"wrote {out}")
    print("FV transport mesh: plasma_right + plasma_focus_ring wall layer h-refined one level")
    print("FEM potential: independent refinement midpoint DOFs constrained to coarse-P1 interpolation")
    for secondary, primary in COARSE_P1_CONSTRAINTS:
        print(f"  phi[{secondary}] = 0.5*phi[{primary[0]}] + 0.5*phi[{primary[1]}]")
    print(f"dt={base.DT} s; one step")
