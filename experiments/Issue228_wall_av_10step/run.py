#!/usr/bin/env python3
"""Issue #228 wall first-cell A/V 10-step discriminator.

Axis grounding stays removed as in Issue228_axis_bc_10step. Production physics,
transport, sheath law, chemistry, timestep, Poisson discretization, boundary
faces, and mesh topology remain unchanged. The only intervention is moving two
interior Gmsh nodes that control the two dominant plasma_right hotspot cells.

Cases:
  baseline : axis-free production mesh
  moderate : prior validated corner edit + moderate second-hotspot depth edit
  matched  : prior validated corner edit + near-neighbor-matched second-hotspot depth edit

This is a diagnostic geometry sensitivity test, not a production mesh prescription.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue211_science_factorial import run as sci
from experiments.Issue228_axis_bc_10step import run as axis
from physics_harness.execution.cases import validate_case_references

MODES = ("baseline", "moderate", "matched")

NODE_A_TAG = 1017
NODE_A_OLD = (0.2363274316974429, 0.2749293432139846)
NODE_A_NEW = (0.2373851955160453, 0.2733895740140211)

NODE_B_TAG = 1530
NODE_B_OLD = (0.2381394868977356, 0.05183333333327342)
NODE_B_MODERATE = (0.2362, NODE_B_OLD[1])
NODE_B_MATCHED = (0.2350, NODE_B_OLD[1])

RIGHT_WALL_X_M = 0.243
B_CENTROID_DEPTH_BASELINE_M = (RIGHT_WALL_X_M - NODE_B_OLD[0]) / 3.0
B_CENTROID_DEPTH_MODERATE_M = (RIGHT_WALL_X_M - NODE_B_MODERATE[0]) / 3.0
B_CENTROID_DEPTH_MATCHED_M = (RIGHT_WALL_X_M - NODE_B_MATCHED[0]) / 3.0


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_case(mode: str) -> tuple[str, dict[str, Any]]:
    if mode not in MODES:
        raise ValueError(mode)
    text, meta = axis.build_case()
    node_b_target = None
    if mode == "moderate":
        node_b_target = NODE_B_MODERATE
    elif mode == "matched":
        node_b_target = NODE_B_MATCHED
    return text, {
        **meta,
        "issue": 228,
        "claim": "wall_first_cell_A_over_V_10step_discriminator",
        "diagnostic_only": True,
        "mode": mode,
        "axis_grounding_removed": True,
        "mesh_topology_changed": False,
        "boundary_geometry_changed": False,
        "physical_coefficients_changed": False,
        "transport_changed": False,
        "sheath_law_changed": False,
        "chemistry_changed": False,
        "poisson_kernel_changed": False,
        "node_a_tag": NODE_A_TAG if mode != "baseline" else None,
        "node_a_old_xy_m": NODE_A_OLD if mode != "baseline" else None,
        "node_a_new_xy_m": NODE_A_NEW if mode != "baseline" else None,
        "node_b_tag": NODE_B_TAG if mode != "baseline" else None,
        "node_b_old_xy_m": NODE_B_OLD if mode != "baseline" else None,
        "node_b_new_xy_m": node_b_target,
        "cell2424_centroid_depth_baseline_m": B_CENTROID_DEPTH_BASELINE_M,
        "cell2424_centroid_depth_target_m": (
            B_CENTROID_DEPTH_MODERATE_M
            if mode == "moderate"
            else B_CENTROID_DEPTH_MATCHED_M
            if mode == "matched"
            else B_CENTROID_DEPTH_BASELINE_M
        ),
    }


def _move_gmsh_node(path: Path, *, tag: int, expected_old_xy: tuple[float, float], new_xy: tuple[float, float]) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        i0 = lines.index("$Nodes")
        i1 = lines.index("$EndNodes", i0 + 1)
    except ValueError as exc:
        raise RuntimeError("Gmsh $Nodes section not found") from exc

    hdr = lines[i0 + 1].split()
    if len(hdr) != 4:
        raise RuntimeError(f"unexpected Gmsh node header: {lines[i0 + 1]!r}")
    nblocks = int(hdr[0])
    pos = i0 + 2
    found = None
    for _ in range(nblocks):
        bh = lines[pos].split()
        if len(bh) != 4:
            raise RuntimeError(f"unexpected node block header: {lines[pos]!r}")
        entity_dim, entity_tag, parametric, n = map(int, bh)
        pos += 1
        tags = [int(lines[pos + j].strip()) for j in range(n)]
        pos += n
        coords_start = pos
        if tag in tags:
            j = tags.index(tag)
            fields = lines[coords_start + j].split()
            if len(fields) < 3:
                raise RuntimeError("node coordinate record has fewer than 3 fields")
            old = (float(fields[0]), float(fields[1]), float(fields[2]))
            if not (
                math.isclose(old[0], expected_old_xy[0], rel_tol=0.0, abs_tol=1e-12)
                and math.isclose(old[1], expected_old_xy[1], rel_tol=0.0, abs_tol=1e-12)
            ):
                raise RuntimeError(f"node {tag} old coordinate mismatch: {old}; expected {expected_old_xy}")
            fields[0] = f"{new_xy[0]:.17g}"
            fields[1] = f"{new_xy[1]:.17g}"
            lines[coords_start + j] = " ".join(fields)
            found = {
                "node_tag": tag,
                "entity_dim": entity_dim,
                "entity_tag": entity_tag,
                "parametric": parametric,
                "old_xyz": old,
                "new_xyz": (new_xy[0], new_xy[1], old[2]),
            }
        pos += n
    if found is None:
        raise RuntimeError(f"node tag {tag} not found")
    if pos != i1:
        raise RuntimeError(f"node parser ended at {pos}, expected {i1}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return found


def _validated_case_references(case_dir: Path) -> list[dict[str, str]]:
    refs = validate_case_references(case_dir)
    if not isinstance(refs, list) or not all(isinstance(item, dict) for item in refs):
        raise TypeError(
            "validate_case_references contract changed: expected list[dict[str, str]], "
            f"got {type(refs).__name__}"
        )
    return refs


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for mode in MODES:
        text, meta = build_case(mode)
        checks[f"{mode}:axis_ground_boundary"] = meta["diagnostic_ground_boundary"] == axis.GROUND_NONAXIS
        checks[f"{mode}:steps"] = int(meta["expected_steps"]) == axis.EXPECTED_STEPS
        checks[f"{mode}:end_time"] = math.isclose(float(meta["end_time_s"]), axis.END_TIME_S, rel_tol=0.0, abs_tol=1e-24)
        checks[f"{mode}:r0"] = int(meta["uniform_refine"]) == 0
    checks["depth:baseline"] = math.isclose(B_CENTROID_DEPTH_BASELINE_M, 0.001620171034088133, rel_tol=0.0, abs_tol=1e-12)
    checks["depth:moderate_increased"] = B_CENTROID_DEPTH_MODERATE_M > B_CENTROID_DEPTH_BASELINE_M
    checks["depth:matched_increased"] = B_CENTROID_DEPTH_MATCHED_M > B_CENTROID_DEPTH_MODERATE_M
    failed = sorted(k for k, v in checks.items() if not v)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _comparison(base: dict[str, Any], other: dict[str, Any]) -> dict[str, float]:
    be = base["endpoint"]
    oe = other["endpoint"]
    bspan = float(base["phi_span_V"])
    ospan = float(other["phi_span_V"])
    return {
        "phi_span_reduction_fraction": 1.0 - ospan / max(abs(bspan), 1e-300),
        "phi_max_change_V": float(oe["phi_max_V"]) - float(be["phi_max_V"]),
        "phi_min_change_V": float(oe["phi_min_V"]) - float(be["phi_min_V"]),
        "volume_charge_relative_change": (float(oe["volume_charge_C"]) - float(be["volume_charge_C"])) / max(abs(float(be["volume_charge_C"])), 1e-300),
        "wall_current_relative_change": (float(oe["net_outward_wall_current_A"]) - float(be["net_outward_wall_current_A"])) / max(abs(float(be["net_outward_wall_current_A"])), 1e-300),
    }


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    out = args.results_root.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    p0 = self_test()
    _write(out / "self_test.json", p0)
    if p0["status"] != "PASS":
        raise RuntimeError(p0)

    summary: dict[str, Any] = {"status": "RUNNING", "cases": {}}
    good = True

    for mode in MODES:
        text, meta = build_case(mode)
        case_dir = out / "cases" / mode
        logs = out / "logs" / mode
        logs.mkdir(parents=True, exist_ok=True)
        cs: dict[str, Any] = {"meta": meta}
        try:
            cs["stage"] = sci._stage(case_dir, text, meta)
            edits = []
            if mode != "baseline":
                edits.append(_move_gmsh_node(case_dir / "qvt.msh", tag=NODE_A_TAG, expected_old_xy=NODE_A_OLD, new_xy=NODE_A_NEW))
                btarget = NODE_B_MODERATE if mode == "moderate" else NODE_B_MATCHED
                edits.append(_move_gmsh_node(case_dir / "qvt.msh", tag=NODE_B_TAG, expected_old_xy=NODE_B_OLD, new_xy=btarget))
                cs["references_after_mesh_edit"] = _validated_case_references(case_dir)
            cs["mesh_edits"] = edits
        except Exception as exc:
            cs["status"] = "HARNESS_FAIL"
            cs["harness_error"] = f"{type(exc).__name__}: {exc}"
            summary["cases"][mode] = cs
            good = False
            _write(out / "summary.partial.json", summary)
            continue

        p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 300.0))
        cs["p2"] = p2
        if p2.get("returncode") != 0:
            cs["status"] = "P2_FAIL"
            summary["cases"][mode] = cs
            good = False
            _write(out / "summary.partial.json", summary)
            continue

        runtime = sci._runtime(exe, case_dir, logs / "runtime.log", logs / "time_v.log", float(args.timeout))
        cs["runtime"] = runtime
        try:
            result = axis._analyse(case_dir, text, meta, runtime)
            cs["result"] = result
            ok = result["runtime_returncode"] == 0 and not result["timed_out"] and result["physical_steps"] == axis.EXPECTED_STEPS and result["all_steps_hard_pass"]
            cs["status"] = "PASS" if ok else "FAIL"
            good = good and ok
        except Exception as exc:
            cs["status"] = "ANALYSIS_FAIL"
            cs["analysis_error"] = f"{type(exc).__name__}: {exc}"
            good = False

        summary["cases"][mode] = cs
        _write(out / "summary.partial.json", summary)

    base = summary["cases"].get("baseline", {}).get("result")
    if base:
        summary["comparisons_to_baseline"] = {}
        for mode in MODES[1:]:
            result = summary["cases"].get(mode, {}).get("result")
            if result:
                summary["comparisons_to_baseline"][mode] = _comparison(base, result)

    summary["status"] = "PASS" if good else "PARTIAL_OR_FAIL"
    _write(out / "summary.json", summary)
    return 0 if good else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue228-wall-av-10step-results"))
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
