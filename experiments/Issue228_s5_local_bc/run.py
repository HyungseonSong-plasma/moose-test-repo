#!/usr/bin/env python3
"""Issue #228 S5 local sheath-edge BC discriminator with evidence-aware CI semantics.

Scientific goal
---------------
S3 restored the bulk potential scale with a wall-wide current-balance sheath-edge
Dirichlet value, but element 2401 retained H ~= +1.35 V.  S4 showed that neither
its tiny remaining positive volume charge nor a charge-preserving geometry edit
removes that residual.  S5 tests whether the residual is caused by lumping all
`plasma_right` faces into one scalar sheath-edge potential.

Cases
-----
  s5_ref       : exact S3 current-balance reference.
  s5_shoulder  : use one inward-reference sheath-edge value on the horizontal
                 shoulder segment of plasma_right; elsewhere keep the S3
                 wall-wide current-balance value.
  s5_face2401  : use the 2401 face-local inward-reference sheath-edge value only
                 on the 2401 shoulder face; elsewhere keep the S3 wall-wide
                 current-balance value.

CI semantics
------------
A scientifically negative but numerically valid discriminator is evidence, not a
broken CI run.  Therefore process exit != 0 is reserved for evidence-generation
failure (construction, validator, solver/runtime, or analysis failure).  A valid
run always exits 0 and records `scientific_outcome` separately.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from experiments.Issue228_d1_s3 import run as s3

MODES = ("s5_ref", "s5_shoulder", "s5_face2401")
TARGET_EID = 2401
RIGHT_WALL = "plasma_right"
SHOULDER_Y_MIN_M = 0.278
TARGET_X_MAX_M = 0.239
HOTSPOTS = s3.HOTSPOTS
PHYSICAL_WALLS = s3.PHYSICAL_WALLS


def _write(path: Path, payload: Any) -> None:
    s3._write(path, payload)


def _hard_fail(out: Path, summary: dict[str, Any], status: str, error: str | None = None) -> int:
    summary["status"] = status
    summary["evidence_valid"] = False
    summary["ci_status"] = "FAIL"
    if error is not None:
        summary["error"] = error
    _write(out / "summary.json", summary)
    return 1


def _valid_evidence(summary: dict[str, Any], outcome: str) -> int:
    summary["status"] = "PASS"
    summary["evidence_valid"] = True
    summary["ci_status"] = "PASS"
    summary["scientific_outcome"] = outcome
    return 0


def _ci_exit_code(evidence_valid: bool, scientific_outcome: str) -> int:
    """Scientific rejection must not make evidence-producing diagnostics red."""
    _ = scientific_outcome
    return 0 if evidence_valid else 1


def ci_self_test(out: Path) -> int:
    cases = {
        "supported_valid": (True, "HYPOTHESIS_SUPPORTED_STRONG", 0),
        "rejected_valid": (True, "HYPOTHESIS_NOT_SUPPORTED", 0),
        "negative_control_valid": (True, "REFERENCE_RESIDUAL_CONFIRMED", 0),
        "construction_invalid": (False, "HARNESS_OR_CONSTRUCTION_FAIL", 1),
        "solver_invalid": (False, "SOLVER_CONVERGENCE_FAIL", 1),
    }
    observed = {k: _ci_exit_code(v[0], v[1]) for k, v in cases.items()}
    expected = {k: v[2] for k, v in cases.items()}
    ok = observed == expected
    payload = {
        "status": "PASS" if ok else "VALIDATOR_SELFTEST_FAIL",
        "rule": "CI failure means invalid evidence; scientific rejection remains green",
        "observed": observed,
        "expected": expected,
    }
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "ci_semantics_self_test.json", payload)
    return 0 if ok else 1


def _right_face_records(snapshot: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    coords, conn, emap, vals, _t, sidesets = s3.pgw._load_snapshot(snapshot, 10)
    rho_raw = s3.d1s2._species_charge(vals)["net"]
    wall, neigh, _rho_ref = s3.d1s2._wall_refs(rho_raw, conn, sidesets)
    side_nodes = {1: (0, 1), 2: (1, 2), 3: (2, 0)}

    records: list[dict[str, Any]] = []
    for name, elems, sides in sidesets:
        if name != RIGHT_WALL:
            continue
        for e, side in zip(elems, sides):
            i = int(e - 1)
            tri = coords[conn[i] - 1]
            ia, ib = side_nodes[int(side)]
            p1 = tri[ia]; p2 = tri[ib]
            mid = 0.5 * (p1 + p2)
            length = float(np.linalg.norm(p2 - p1))
            area = 2.0 * math.pi * length * float(mid[0])
            js = s3._inward_indices(i, wall, neigh)
            if not js:
                raise RuntimeError(f"no inward reference for right-wall element {int(emap[i])}")
            phi_ref = float(np.mean(vals["potential_plasma"][js]))
            records.append({
                "element_id": int(emap[i]),
                "cell_index": i,
                "side": int(side),
                "midpoint_r_m": float(mid[0]),
                "midpoint_z_m": float(mid[1]),
                "face_area_m2": area,
                "inward_reference_phi_V": phi_ref,
                "inward_neighbor_element_ids": [int(emap[j]) for j in js],
            })

    shoulder = [r for r in records if r["midpoint_z_m"] > SHOULDER_Y_MIN_M]
    target = [r for r in shoulder if r["midpoint_r_m"] < TARGET_X_MAX_M]
    checks = {
        "right_faces_present": len(records) > 0,
        "shoulder_elements_exact": sorted(r["element_id"] for r in shoulder) == [2401, 2511],
        "target_face_exact": [r["element_id"] for r in target] == [TARGET_EID],
    }
    if not all(checks.values()):
        raise RuntimeError(f"S5 geometric predicate self-test failed: {checks}")

    shoulder_area = sum(float(r["face_area_m2"]) for r in shoulder)
    shoulder_phi = sum(float(r["face_area_m2"]) * float(r["inward_reference_phi_V"]) for r in shoulder) / shoulder_area
    target_phi = float(target[0]["inward_reference_phi_V"])
    meta = {
        "predicate_checks": checks,
        "shoulder_y_min_m": SHOULDER_Y_MIN_M,
        "target_x_max_m": TARGET_X_MAX_M,
        "shoulder_element_ids": [r["element_id"] for r in shoulder],
        "shoulder_area_weighted_inward_phi_V": float(shoulder_phi),
        "target_2401_inward_phi_V": target_phi,
        "right_face_records": records,
    }
    return records, meta


def _s5_input(mode: str, wall_values: dict[str, float], initial_phi: float, local: dict[str, Any]) -> str:
    function_block = ""
    right_bc = ""
    base = float(wall_values[RIGHT_WALL])
    if mode == "s5_ref":
        right_bc = f"""  [sheath_edge_{RIGHT_WALL}]
    type = FVDirichletBC
    variable = phi
    boundary = {RIGHT_WALL}
    value = {base:.17g}
  []"""
    else:
        if mode == "s5_shoulder":
            shoulder = float(local["shoulder_area_weighted_inward_phi_V"])
            expr = f"if(y>{SHOULDER_Y_MIN_M:.17g},{shoulder:.17g},{base:.17g})"
        elif mode == "s5_face2401":
            target = float(local["target_2401_inward_phi_V"])
            expr = (
                f"if(y>{SHOULDER_Y_MIN_M:.17g},"
                f"if(x<{TARGET_X_MAX_M:.17g},{target:.17g},{base:.17g}),"
                f"{base:.17g})"
            )
        else:
            raise ValueError(mode)
        function_block = f"""
[Functions]
  [right_sheath_edge]
    type = ParsedFunction
    expression = '{expr}'
  []
[]
"""
        right_bc = f"""  [sheath_edge_{RIGHT_WALL}]
    type = FVFunctionDirichletBC
    variable = phi
    boundary = {RIGHT_WALL}
    function = right_sheath_edge
  []"""

    other = []
    for w in PHYSICAL_WALLS:
        if w == RIGHT_WALL:
            continue
        other.append(f"""  [sheath_edge_{w}]
    type = FVDirichletBC
    variable = phi
    boundary = {w}
    value = {float(wall_values[w]):.17g}
  []""")
    wall_bcs = "\n".join(other + [right_bc])

    return f"""[Problem]
  kernel_coverage_check = ONLY_LIST
  kernel_coverage_block_list = plasma
[]

[Mesh]
  type = FileMesh
  file = source.e
  parallel_type = replicated
  coord_type = RZ
  rz_coord_axis = Y
[]

[Variables]
  [phi]
    type = MooseVariableFVReal
    initial_condition = {initial_phi:.17g}
    block = plasma
  []
[]

[AuxVariables]
  [frozen_source]
    family = MONOMIAL
    order = CONSTANT
    block = plasma
  []
[]

[UserObjects]
  [frozen_solution]
    type = SolutionUserObject
    mesh = source.e
    system_variables = potential_plasma
    timestep = LATEST
    force_replicated_source_mesh = true
    execute_on = INITIAL
  []
[]

[AuxKernels]
  [import_source]
    type = SolutionAux
    variable = frozen_source
    solution = frozen_solution
    from_variable = potential_plasma
    direct = true
    execute_on = INITIAL
  []
[]

[FVKernels]
  [diffusion]
    type = FVDiffusion
    variable = phi
    coeff = 1
    block = plasma
  []
  [source]
    type = FVCoupledForce
    variable = phi
    v = frozen_source
    coef = 1
    block = plasma
  []
[]
{function_block}
[FVBCs]
  [openings_ground]
    type = FVDirichletBC
    variable = phi
    boundary = 'inlet outlet'
    value = 0
  []
{wall_bcs}
[]

[Postprocessors]
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = phi
    value_type = min
    block = plasma
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = phi
    value_type = max
    block = plasma
  []
[]

[Executioner]
  type = Steady
  solve_type = NEWTON
  nl_abs_tol = 1e-12
  nl_rel_tol = 1e-11
[]

[Outputs]
  csv = true
  exodus = true
[]
"""


def _reference_summary(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    p = path / "summary.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def run(args: argparse.Namespace) -> int:
    mode = args.mode
    if mode not in MODES:
        raise ValueError(mode)
    exe = args.physics_opt.resolve()
    snapshot = args.snapshot_root.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    case = out / "case"; logs = out / "logs"
    case.mkdir(parents=True); logs.mkdir()

    summary: dict[str, Any] = {
        "status": "RUNNING",
        "evidence_valid": False,
        "ci_status": "RUNNING",
        "claim": "plasma_right_wall_wide_sheath_edge_lumping_causes_2401_residual_hill",
        "mode": mode,
        "diagnostic_only": True,
        "ci_semantics_version": 2,
    }

    try:
        prep = s3._prepare_source(snapshot, case)
        wall_values = s3._wall_values("current_balance", prep)
        _records, local = _right_face_records(snapshot)
    except Exception as exc:
        return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL", f"{type(exc).__name__}: {exc}")

    summary["preparation"] = prep
    summary["bulk_sheath_edge_wall_values_V"] = wall_values
    summary["local_bc_definition"] = local
    initial_phi = float(np.mean(list(wall_values.values())))
    text = _s5_input(mode, wall_values, initial_phi, local)
    (case / "input.i").write_text(text, encoding="utf-8")

    p2 = s3.d1s2._run([str(exe), "-i", "input.i", "--check-input"], case, logs / "p2.log", 180)
    summary["p2"] = p2
    if p2["returncode"] != 0:
        return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL")

    rt = s3.d1s2._run([str(exe), "-i", "input.i"], case, logs / "runtime.log", 600)
    summary["runtime"] = rt
    if rt["returncode"] != 0 or rt["timed_out"]:
        return _hard_fail(out, summary, "SOLVER_CONVERGENCE_FAIL")

    exo = sorted(case.glob("*_out.e"))
    if len(exo) != 1:
        return _hard_fail(out, summary, "HARNESS_OR_CONSTRUCTION_FAIL", f"expected one output Exodus, got {exo}")

    try:
        conn, emap, phi, sidesets = s3.d1s2._read_phi(exo[0])
        hs = s3.d1s2._hotspots(emap, conn, sidesets, phi)
        coords, conn0, _emap0, _vals0, _t0, sidesets0 = s3.pgw._load_snapshot(snapshot, 10)[:6]
        _tri, _area, _rcent, vol = s3.d1s2._geom(coords, conn0)
        wall, _neigh = s3.pgw._wall_cells_and_neighbors(conn0, sidesets0)
        nonwall = np.asarray([i for i in range(len(conn0)) if i not in wall], dtype=int)
        nonwall_mean = float(np.dot(phi[nonwall], vol[nonwall]) / np.sum(vol[nonwall]))
    except Exception as exc:
        return _hard_fail(out, summary, "ANALYSIS_FAIL", f"{type(exc).__name__}: {exc}")

    baseline_mean = float(prep["baseline_nonwall_volume_mean_phi_V"])
    span = float(phi.max() - phi.min())
    max_lookup_resid = max(abs(float(v)) for v in prep["lookup"]["current_balance_relative_residual"].values())
    common_gates = {
        "other_hotspots_no_regression": all(
            str(eid) in hs and float(hs[str(eid)]["H_wall_minus_inward_V"]) <= 0.05
            for eid in HOTSPOTS if eid != TARGET_EID
        ),
        "bulk_mean_scale": abs(nonwall_mean - baseline_mean) <= 5.0,
        "finite_moderate_span": span <= 30.0,
        "bounded_potential": float(phi.min()) >= -5.0 and float(phi.max()) <= 40.0,
        "lookup_current_balance": max_lookup_resid <= 1.0e-9,
    }
    target_h = float(hs[str(TARGET_EID)]["H_wall_minus_inward_V"])
    target_drop = target_h <= 0.0

    ref = _reference_summary(args.s3_reference_root.resolve() if args.s3_reference_root else None)
    ref_h = None
    reproduction = None
    if ref is not None and str(TARGET_EID) in ref.get("hotspots", {}):
        ref_h = float(ref["hotspots"][str(TARGET_EID)]["H_wall_minus_inward_V"])
        if mode == "s5_ref":
            diffs = {
                "phi_min_abs_diff_V": abs(float(phi.min()) - float(ref["phi_min_V"])),
                "phi_max_abs_diff_V": abs(float(phi.max()) - float(ref["phi_max_V"])),
                "H_2401_abs_diff_V": abs(target_h - ref_h),
            }
            reproduction = {"max_abs_diff_V": max(diffs.values()), "diffs": diffs}
            if reproduction["max_abs_diff_V"] > 5.0e-3:
                summary["reference_reproduction"] = reproduction
                return _hard_fail(out, summary, "VALIDATOR_SELFTEST_FAIL")

    if mode == "s5_ref":
        outcome = "REFERENCE_RESIDUAL_CONFIRMED" if target_h > 0.0 else "REFERENCE_RESIDUAL_NOT_REPRODUCED"
    else:
        common_ok = all(common_gates.values())
        if common_ok and target_drop:
            outcome = "HYPOTHESIS_SUPPORTED_STRONG"
        elif common_ok and ref_h is not None and ref_h > 0.0 and target_h <= 0.5 * ref_h:
            outcome = "HYPOTHESIS_SUPPORTED_PARTIAL"
        else:
            outcome = "HYPOTHESIS_NOT_SUPPORTED"

    summary.update({
        "phi_min_V": float(phi.min()),
        "phi_max_V": float(phi.max()),
        "phi_span_V": span,
        "phi_max_element_id": int(emap[int(np.argmax(phi))]),
        "nonwall_volume_mean_phi_V": nonwall_mean,
        "baseline_nonwall_volume_mean_phi_V": baseline_mean,
        "nonwall_mean_delta_V": nonwall_mean - baseline_mean,
        "hotspots": hs,
        "target_2401_H_V": target_h,
        "target_2401_drop": target_drop,
        "reference_2401_H_V": ref_h,
        "reference_reproduction": reproduction,
        "scientific_gates": {**common_gates, "target_2401_drop": target_drop},
    })
    rc = _valid_evidence(summary, outcome)
    _write(out / "summary.json", summary)
    return rc


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("s5")
    s.add_argument("--mode", choices=MODES, required=True)
    s.add_argument("--snapshot-root", type=Path, required=True)
    s.add_argument("--s3-reference-root", type=Path)
    s.add_argument("--physics-opt", type=Path, required=True)
    s.add_argument("--results-root", type=Path, required=True)
    c = sub.add_parser("ci-self-test")
    c.add_argument("--results-root", type=Path, required=True)
    a = p.parse_args()
    if a.cmd == "ci-self-test":
        return ci_self_test(a.results_root.resolve())
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
