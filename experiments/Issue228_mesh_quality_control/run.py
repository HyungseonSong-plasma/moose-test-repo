#!/usr/bin/env python3
"""Issue #228 local mesh-quality discriminator.

Keeps production physics, production electron-drift gradient, Poisson, sheath law,
chemistry, dt, and R0 topology unchanged. The only diagnostic intervention is
moving one *interior* Gmsh node adjacent to the fixed corner hotspot to improve
local triangle angle/non-orthogonality quality. This is a diagnostic control,
not a proposed hard-coded production mesh fix.
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
from experiments.Issue216_w5_multistep_acceptance import run as w5
from experiments.Issue228_drift_gradient_compare import run as cmp
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import validate_case_references

DT_S = w5.BASELINE_DT_S
MODES = ("production", "mesh_quality")
NODE_TAG = 1017
OLD_XY = (0.2363274316974429, 0.2749293432139846)
NEW_XY = (0.2373851955160453, 0.2733895740140211)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_case(mode: str) -> tuple[str, dict[str, Any]]:
    if mode not in MODES:
        raise ValueError(mode)
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=0)
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{DT_S:.17g}")
    text = mp.upsert_parameter(text, "Outputs", "exodus", "true")
    return text, {
        **meta,
        "issue": 228,
        "claim": "local_mesh_quality_discriminator",
        "diagnostic_only": True,
        "mode": mode,
        "expected_steps": 1,
        "dt_s": DT_S,
        "end_time_s": DT_S,
        "uniform_refine": 0,
        "physical_coefficients_changed": False,
        "electron_drift_discretization_changed": False,
        "poisson_discretization_changed": False,
        "sheath_law_changed": False,
        "chemistry_changed": False,
        "mesh_topology_changed": False,
        "boundary_geometry_changed": False,
        "interior_node_tag": NODE_TAG if mode == "mesh_quality" else None,
        "old_xy_m": OLD_XY if mode == "mesh_quality" else None,
        "new_xy_m": NEW_XY if mode == "mesh_quality" else None,
    }


def _move_gmsh_node(path: Path, tag: int, new_xy: tuple[float, float]) -> dict[str, Any]:
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
            if not (math.isclose(old[0], OLD_XY[0], rel_tol=0.0, abs_tol=1e-12) and
                    math.isclose(old[1], OLD_XY[1], rel_tol=0.0, abs_tol=1e-12)):
                raise RuntimeError(f"node {tag} old coordinate mismatch: {old}")
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


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for mode in MODES:
        text, meta = build_case(mode)
        checks[f"{mode}:dt"] = math.isclose(float(mp.get_parameter(text, "Executioner", "dt") or "nan"), DT_S, rel_tol=0.0, abs_tol=0.0)
        checks[f"{mode}:end"] = math.isclose(float(mp.get_parameter(text, "Executioner", "end_time") or "nan"), DT_S, rel_tol=0.0, abs_tol=1e-24)
        checks[f"{mode}:drift_type"] = mp.get_parameter(text, "FVKernels/n_e_drift", "type") == "PhysicsFVElectrostaticDrift"
        checks[f"{mode}:r0"] = int(meta["uniform_refine"]) == 0
    failed = sorted(k for k, v in checks.items() if not v)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


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
        stage = sci._stage(case_dir, text, meta)
        mesh_edit = None
        if mode == "mesh_quality":
            mesh_edit = _move_gmsh_node(case_dir / "qvt.msh", NODE_TAG, NEW_XY)
            refs = validate_case_references(case_dir)
            if not refs.get("ok", False):
                raise RuntimeError(f"references invalid after mesh edit: {refs}")
        p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 300.0))
        cs: dict[str, Any] = {"meta": meta, "stage": stage, "mesh_edit": mesh_edit, "p2": p2}
        if p2.get("returncode") != 0:
            cs["status"] = "P2_FAIL"
            good = False
            summary["cases"][mode] = cs
            continue
        runtime = sci._runtime(exe, case_dir, logs / "runtime.log", logs / "time_v.log", float(args.timeout))
        cs["runtime"] = runtime
        try:
            result = cmp._case_result(case_dir, text, meta, runtime)
            cs["result"] = result
            cs["status"] = "PASS" if result["runtime_returncode"] == 0 and result["step_hard_pass"] else "FAIL"
            good = good and cs["status"] == "PASS"
        except Exception as exc:
            cs["status"] = "ANALYSIS_FAIL"
            cs["analysis_error"] = f"{type(exc).__name__}: {exc}"
            good = False
        summary["cases"][mode] = cs
        _write(out / "summary.partial.json", summary)

    prod = summary["cases"].get("production", {}).get("result")
    mesh = summary["cases"].get("mesh_quality", {}).get("result")
    if prod and mesh:
        summary["comparison"] = {
            "phi_span_reduction_fraction": 1.0 - float(mesh["phi_span_V"]) / max(float(prod["phi_span_V"]), 1e-300),
            "volume_charge_relative_change": (float(mesh["volume_charge_C"]) - float(prod["volume_charge_C"])) / max(abs(float(prod["volume_charge_C"])), 1e-300),
            "wall_current_relative_change": (float(mesh["net_outward_wall_current_A"]) - float(prod["net_outward_wall_current_A"])) / max(abs(float(prod["net_outward_wall_current_A"])), 1e-300),
            "primary_electron_rate_relative_change": (float(mesh["primary_electron_particle_rate_s-1"]) - float(prod["primary_electron_particle_rate_s-1"])) / max(abs(float(prod["primary_electron_particle_rate_s-1"])), 1e-300),
        }
    summary["status"] = "PASS" if good else "PARTIAL_OR_FAIL"
    _write(out / "summary.json", summary)
    return 0 if good else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue228-mesh-quality-control-results"))
    parser.add_argument("--timeout", type=float, default=900.0)
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
