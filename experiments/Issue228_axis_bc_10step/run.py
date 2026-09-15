#!/usr/bin/env python3
"""Issue #228 axis-grounding discriminator.

This diagnostic keeps production transport, sheath, chemistry, mesh, timestep,
and Poisson discretization unchanged. It only excludes the geometric RZ axis
(x = 0 for coord_type=RZ, rz_coord_axis=Y) from the grounded potential sideset,
then advances exactly ten physical timesteps.
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
from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

DT_S = w5.BASELINE_DT_S
EXPECTED_STEPS = 10
END_TIME_S = EXPECTED_STEPS * DT_S
GROUND_NONAXIS = "r228_phi_ground_nonaxis"
ALL_PLASMA_BOUNDARY = "r31_plasma_all_boundary"
GROUND_BC_PATH = "FVBCs/r31_phi_ground_all"
AXIS_X_TOL_M = 1.0e-12


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_case() -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=0)

    mb.require_absent(text, f"Mesh/{GROUND_NONAXIS}")
    text = mb.insert_child_block(
        text,
        "Mesh",
        f"""  [{GROUND_NONAXIS}]
    type = ParsedGenerateSideset
    input = {ALL_PLASMA_BOUNDARY}
    combinatorial_geometry = 'x > {AXIS_X_TOL_M:.17g}'
    included_boundaries = {ALL_PLASMA_BOUNDARY}
    included_subdomains = plasma
    new_sideset_name = {GROUND_NONAXIS}
  []""",
    )

    text = mp.upsert_parameter(text, GROUND_BC_PATH, "boundary", GROUND_NONAXIS)
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{END_TIME_S:.17g}")
    text = mp.upsert_parameter(text, "Outputs", "exodus", "true")

    return text, {
        **meta,
        "issue": 228,
        "claim": "axis_grounding_removed_10step_discriminator",
        "diagnostic_only": True,
        "expected_steps": EXPECTED_STEPS,
        "dt_s": DT_S,
        "end_time_s": END_TIME_S,
        "uniform_refine": 0,
        "axis_coordinate": "x=0 (RZ axis=Y)",
        "axis_exclusion_tolerance_m": AXIS_X_TOL_M,
        "original_ground_boundary": ALL_PLASMA_BOUNDARY,
        "diagnostic_ground_boundary": GROUND_NONAXIS,
        "gauss_boundary_unchanged": ALL_PLASMA_BOUNDARY,
        "mesh_geometry_changed": False,
        "transport_changed": False,
        "sheath_law_changed": False,
        "chemistry_changed": False,
        "poisson_kernel_changed": False,
    }


def self_test() -> dict[str, Any]:
    text, meta = build_case()
    checks = {
        "dt": math.isclose(
            float(mp.get_parameter(text, "Executioner", "dt") or "nan"),
            DT_S,
            rel_tol=0.0,
            abs_tol=0.0,
        ),
        "end_time": math.isclose(
            float(mp.get_parameter(text, "Executioner", "end_time") or "nan"),
            END_TIME_S,
            rel_tol=0.0,
            abs_tol=1.0e-24,
        ),
        "expected_steps": int(meta["expected_steps"]) == EXPECTED_STEPS,
        "ground_bc_retargeted": mp.get_parameter(text, GROUND_BC_PATH, "boundary") == GROUND_NONAXIS,
        "parsed_sideset_type": mp.get_parameter(text, f"Mesh/{GROUND_NONAXIS}", "type") == "ParsedGenerateSideset",
        "parsed_sideset_input": mp.get_parameter(text, f"Mesh/{GROUND_NONAXIS}", "input") == ALL_PLASMA_BOUNDARY,
        "parsed_sideset_source_boundary": mp.get_parameter(text, f"Mesh/{GROUND_NONAXIS}", "included_boundaries") == ALL_PLASMA_BOUNDARY,
        "parsed_sideset_plasma_only": mp.get_parameter(text, f"Mesh/{GROUND_NONAXIS}", "included_subdomains") == "plasma",
        "gauss_boundary_unchanged": mp.get_parameter(text, "Postprocessors/r31_gauss_flux_reduced", "boundary") == ALL_PLASMA_BOUNDARY,
        "production_drift_unchanged": mp.get_parameter(text, "FVKernels/n_e_drift", "type") == "PhysicsFVElectrostaticDrift",
        "r0_mesh": int(meta["uniform_refine"]) == 0,
    }
    failed = sorted(k for k, value in checks.items() if not value)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _analyse(case_dir: Path, text: str, meta: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    rows = s5r._read_rows(case_dir / "input_out.csv")
    physical = w5._physical_rows(rows)
    if len(physical) != EXPECTED_STEPS:
        raise RuntimeError(f"expected {EXPECTED_STEPS} physical rows, got {len(physical)}")

    steps = []
    for i in range(1, len(rows)):
        if s5r._num(rows[i], "time") <= 1.0e-15:
            continue
        steps.append(w5._step_evidence(rows[i - 1], rows[i], input_text=text, meta=meta))
    if len(steps) != EXPECTED_STEPS:
        raise RuntimeError(f"expected {EXPECTED_STEPS} step evidence rows, got {len(steps)}")

    endpoint = w5._endpoint(rows, meta=meta)
    final_step = steps[-1]
    phi_min = float(endpoint["phi_min_V"])
    phi_max = float(endpoint["phi_max_V"])
    return {
        "runtime_returncode": int(runtime.get("returncode", 1)),
        "timed_out": bool(runtime.get("timed_out", False)),
        "physical_steps": len(physical),
        "all_steps_hard_pass": all(step.get("hard_pass") is True for step in steps),
        "endpoint": endpoint,
        "phi_span_V": phi_max - phi_min,
        "max_current_charge_relative_defect": max(
            float(step["charge"]["relative_defect_over_boundary_current_scale"]) for step in steps
        ),
        "max_gauss_relative_defect": max(float(step["gauss"]["relative_defect"]) for step in steps),
        "final_step": final_step,
        "steps": steps,
        "exodus_files": sorted(path.name for path in case_dir.glob("*.e*")),
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

    text, meta = build_case()
    case_dir = out / "case"
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {"status": "RUNNING", "meta": meta}
    try:
        summary["stage"] = sci._stage(case_dir, text, meta)
    except Exception as exc:
        summary["status"] = "HARNESS_FAIL"
        summary["harness_error"] = f"{type(exc).__name__}: {exc}"
        _write(out / "summary.json", summary)
        return 1

    p2 = s5r._p2(exe, case_dir, logs / "p2.log", timeout=min(float(args.timeout), 300.0))
    summary["p2"] = p2
    if p2.get("returncode") != 0:
        summary["status"] = "P2_FAIL"
        _write(out / "summary.json", summary)
        return 1

    runtime = sci._runtime(exe, case_dir, logs / "runtime.log", logs / "time_v.log", float(args.timeout))
    summary["runtime"] = runtime
    try:
        result = _analyse(case_dir, text, meta, runtime)
        summary["result"] = result
        good = (
            result["runtime_returncode"] == 0
            and not result["timed_out"]
            and result["physical_steps"] == EXPECTED_STEPS
            and result["all_steps_hard_pass"]
        )
        summary["status"] = "PASS" if good else "FAIL"
    except Exception as exc:
        summary["status"] = "ANALYSIS_FAIL"
        summary["analysis_error"] = f"{type(exc).__name__}: {exc}"
        good = False

    _write(out / "summary.json", summary)
    return 0 if good else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("issue228-axis-bc-10step-results"),
    )
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
