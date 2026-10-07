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
SECONDARY = (1317, 1324)
PRIMARY_A = (12, 12)
PRIMARY_B = (1235, 1237)


def ids(values):
    return " ".join(str(v) for v in values)


def coarse_p1_potential() -> str:
    text = wall.wall_layer_hrefine()

    problem = f"""[Problem]
  type = PhysicsCoarseP1ConstraintProblem
  coarse_p1_variable = potential
  coarse_p1_secondary_nodes = '{ids(SECONDARY)}'
  coarse_p1_primary_nodes_a = '{ids(PRIMARY_A)}'
  coarse_p1_primary_nodes_b = '{ids(PRIMARY_B)}'
[]

"""

    marker = "[Mesh]\n"
    if text.count(marker) != 1:
        raise RuntimeError(f"expected exactly one Mesh marker, found {text.count(marker)}")
    return text.replace(marker, problem + marker, 1)


if __name__ == "__main__":
    out = Path(base.HERE) / "hybrid_wall_layer_coarse_p1.i"
    out.write_text(coarse_p1_potential(), encoding="utf-8")
    print(f"wrote {out}")
    print("FV transport mesh: plasma_right + plasma_focus_ring wall layer h-refined one level")
    print("FEM potential: exact libMesh DofMap constraints retain coarse-P1 midpoint interpolation")
    for s, a, b in zip(SECONDARY, PRIMARY_A, PRIMARY_B):
        print(f"  phi[{s}] = 0.5*phi[{a}] + 0.5*phi[{b}]")
    print("constraint mechanism: System::Constraint -> DofMap::add_constraint_row -> process_constraints")
    print("no MOOSE LinearNodalConstraint and no penalty residual")
    print(f"dt={base.DT} s; one step")
