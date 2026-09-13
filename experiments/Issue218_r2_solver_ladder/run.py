#!/usr/bin/env python3
"""Issue #218 bounded solver ladder for a resource-feasible W5 R2 endpoint.

Production physics, mesh levels, dt, end time, W5 hard gates, and the already
registered 1e-4 R1 endpoint-equivalence tolerance remain fixed. GMRES+ILU(1)
and then GMRES+ILU(2) are tested at R1. The first candidate that passes both
W5 hard gates (including solver convergence) and the endpoint-equivalence gate
is admitted unchanged to uniform_refine=2. No post-hoc solver-gate relaxation
is permitted.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue216_w5_multistep_acceptance import run as w5
from experiments.Issue216_w5_multistep_acceptance import evr2_mesh as evr2
from experiments.Issue218_r2_resource import run as bridge0
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case, validate_case_references

DT_S = w5.BASELINE_DT_S
END_TIME_S = w5.END_TIME_S
EQUIV_REL_TOL = bridge0.EQUIV_REL_TOL
EQUIV_KEYS = bridge0.EQUIV_KEYS
CANDIDATE_LEVELS = (1, 2)
ITER_INAME = "-ksp_type -pc_type -pc_factor_levels -ksp_rtol -ksp_max_it"


class Issue218LadderError(RuntimeError):
    pass


def _iter_values(level: int) -> str:
    return f"gmres ilu {level} 1e-10 500"


def _build(level: int, *, ilu_level: int | None) -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=level)
    solver_name = "accepted_direct_lu"
    if ilu_level is not None:
        text = mp.upsert_parameter(text, "Executioner", "petsc_options_iname", f"'{ITER_INAME}'")
        text = mp.upsert_parameter(text, "Executioner", "petsc_options_value", f"'{_iter_values(ilu_level)}'")
        solver_name = f"gmres_ilu{ilu_level}"
    return text, {
        **meta,
        "issue": 218,
        "parent_issue": 216,
        "numerical_solver": solver_name,
        "physics_semantics_changed": False,
        "solver_ladder_pre_registered": True,
    }


def _stage(case_dir: Path, *, level: int, ilu_level: int | None) -> tuple[str, dict[str, Any], dict[str, Any]]:
    text, meta = _build(level, ilu_level=ilu_level)
    staged = stage_case(
        w5.SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    s5r._copy_runtime_assets(case_dir)
    refs = validate_case_references(case_dir)
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return text, meta, {"staging": staged, "references": refs}


def _execute(exe: Path, out: Path, name: str, level: int, ilu_level: int | None, timeout: float) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    text, meta, staging = _stage(case_dir, level=level, ilu_level=ilu_level)
    p2 = s5r._p2(exe, case_dir, logs / f"{name}_p2.log", timeout=timeout)
    item: dict[str, Any] = {
        "uniform_refine": level,
        "ilu_level": ilu_level,
        "meta": meta,
        "staging": staging,
        "p2": p2,
    }
    if p2["returncode"] != 0:
        item["hard_pass"] = False
        item["reason"] = "P2_FAIL"
        return item
    runtime_log = logs / f"{name}_runtime.log"
    runtime = s5r._runtime(exe, case_dir, runtime_log, timeout=timeout)
    item["runtime"] = runtime
    try:
        evidence = w5._analyze_case(
            case_dir,
            input_text=text,
            meta=meta,
            runtime_log=runtime_log,
            runtime_returncode=int(runtime.get("returncode", 1)),
        )
    except (w5.Issue216Error, KeyError, ValueError, AssertionError) as exc:
        evidence = {"hard_pass": False, "analysis_error": str(exc)}
    item["evidence"] = evidence
    item["hard_pass"] = evidence.get("hard_pass") is True
    return item


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_test() -> dict[str, Any]:
    direct, meta0 = _build(1, ilu_level=None)
    checks: dict[str, bool] = {
        "dt_preserved": math.isclose(float(meta0["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0),
        "end_time_preserved": math.isclose(float(meta0["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0),
    }
    for ilu_level in CANDIDATE_LEVELS:
        candidate, _ = _build(1, ilu_level=ilu_level)
        r2, _ = _build(2, ilu_level=ilu_level)
        checks[f"ilu{ilu_level}_physics_normalized_equal"] = bridge0._normalized(direct) == bridge0._normalized(candidate)
        checks[f"ilu{ilu_level}_declared"] = _iter_values(ilu_level) in (mp.get_parameter(candidate, "Executioner", "petsc_options_value") or "")
        checks[f"ilu{ilu_level}_r2_preserved"] = mp.get_parameter(r2, "Mesh", "uniform_refine") == "2"
    good = bridge0._equivalence({k: 1.0 for k in EQUIV_KEYS}, {k: 1.0 + 5e-5 for k in EQUIV_KEYS})
    bad = bridge0._equivalence({k: 1.0 for k in EQUIV_KEYS}, {k: 1.0 + 2e-4 for k in EQUIV_KEYS})
    checks["equivalence_positive_control"] = good["passed"] is True
    checks["equivalence_negative_control"] = bad["passed"] is False
    failed = sorted(k for k, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue218LadderError(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue218LadderError(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 218,
        "parent_issue": 216,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": w5._sha256(exe),
        "dt_s": DT_S,
        "end_time_s": END_TIME_S,
        "equivalence_tolerance": EQUIV_REL_TOL,
        "candidate_order": [f"gmres_ilu{x}" for x in CANDIDATE_LEVELS],
        "p0": p0,
        "cases": {},
        "candidate_assessment": {},
        "selected_candidate": None,
        "mesh_convergence": {},
        "decision": {},
    }

    summary["cases"]["coarse_lu"] = _execute(exe, out, "coarse_lu", 0, None, args.timeout)
    summary["cases"]["r1_lu"] = _execute(exe, out, "r1_lu", 1, None, args.timeout)
    if not (summary["cases"]["coarse_lu"]["hard_pass"] and summary["cases"]["r1_lu"]["hard_pass"]):
        summary["status"] = "ISSUE218_LADDER_REFERENCE_FAIL"
        summary["decision"] = {"resource_remediation_ready": False, "reason": "same-build accepted direct-LU reference failed"}
        _write(out, summary)
        return 2

    r1_ref = summary["cases"]["r1_lu"]["evidence"]["endpoint"]
    selected: int | None = None
    for ilu_level in CANDIDATE_LEVELS:
        name = f"r1_ilu{ilu_level}"
        case = _execute(exe, out, name, 1, ilu_level, args.timeout)
        summary["cases"][name] = case
        assessment: dict[str, Any] = {"hard_pass": case["hard_pass"], "equivalence": None, "admitted": False}
        if case["hard_pass"]:
            eq = bridge0._equivalence(r1_ref, case["evidence"]["endpoint"])
            assessment["equivalence"] = eq
            assessment["admitted"] = eq["passed"] is True
            if assessment["admitted"]:
                selected = ilu_level
                summary["candidate_assessment"][f"gmres_ilu{ilu_level}"] = assessment
                break
        summary["candidate_assessment"][f"gmres_ilu{ilu_level}"] = assessment

    if selected is None:
        summary["status"] = "ISSUE218_SOLVER_LADDER_EXHAUSTED"
        summary["decision"] = {
            "resource_remediation_ready": False,
            "reason": "No pre-registered ILU(1/2) candidate passed both W5 hard gates and the fixed R1 endpoint-equivalence gate",
            "solver_gate_relaxed": False,
        }
        _write(out, summary)
        return 3

    summary["selected_candidate"] = f"gmres_ilu{selected}"
    r2_name = f"r2_ilu{selected}"
    summary["cases"][r2_name] = _execute(exe, out, r2_name, 2, selected, args.timeout)
    if not summary["cases"][r2_name]["hard_pass"]:
        summary["status"] = "ISSUE218_R2_STILL_BLOCKED"
        summary["decision"] = {
            "resource_remediation_ready": False,
            "selected_candidate": summary["selected_candidate"],
            "reason": "Validated R1 solver candidate did not complete R2 W5 hard gates",
            "solver_gate_relaxed": False,
        }
        _write(out, summary)
        return 4

    endpoints = {
        "coarse": summary["cases"]["coarse_lu"]["evidence"]["endpoint"],
        "refine_1": summary["cases"]["r1_lu"]["evidence"]["endpoint"],
        "refine_2": summary["cases"][r2_name]["evidence"]["endpoint"],
    }
    summary["mesh_convergence"] = evr2._mesh_trends(endpoints)
    summary["status"] = "ISSUE218_R2_ENDPOINT_AND_MESH_TREND_READY"
    summary["decision"] = {
        "resource_remediation_ready": True,
        "r2_endpoint_complete": True,
        "selected_candidate": summary["selected_candidate"],
        "bridge_equivalent": True,
        "validator_review_required": True,
        "post_hoc_threshold_used": False,
        "solver_gate_relaxed": False,
        "reason": "Pre-registered R1 solver candidate passed W5 hard gates and fixed equivalence before unchanged R2 use; R2 endpoint and mesh trend are ready for #216 review",
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--physics-opt", type=Path)
    p.add_argument("--results-root", type=Path, default=Path("issue218-r2-solver-ladder-results"))
    p.add_argument("--timeout", type=float, default=3600.0)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        p.error("--physics-opt required unless --self-test")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
