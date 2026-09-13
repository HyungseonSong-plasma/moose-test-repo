#!/usr/bin/env python3
"""Issue #218: resource-feasible R2 discriminator for W5 EVR-2.

Keep production physics, dt, end_time, and mesh levels fixed. Bridge the accepted
R1 direct-LU path to a lower-memory GMRES+ILU(0) numerical execution path using
an a-priori 1e-4 endpoint-equivalence tolerance. Only if that bridge passes do
we execute uniform_refine=2 with the lower-memory solver and reconstruct the
coarse/R1/R2 mesh trend.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue216_w5_multistep_acceptance import run as w5
from experiments.Issue216_w5_multistep_acceptance import evr2_mesh as evr2
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case, validate_case_references

DT_S = w5.BASELINE_DT_S
END_TIME_S = w5.END_TIME_S
EQUIV_REL_TOL = 1.0e-4
ITER_INAME = "-ksp_type -pc_type -pc_factor_levels -ksp_rtol -ksp_max_it"
ITER_VALUES = "gmres ilu 0 1e-10 500"
EQUIV_KEYS = tuple(k for k in evr2.MATERIAL_KEYS if k != "net_outward_wall_current_A")


class Issue218Error(RuntimeError):
    pass


def _iterative(text: str) -> str:
    text = mp.upsert_parameter(text, "Executioner", "petsc_options_iname", f"'{ITER_INAME}'")
    text = mp.upsert_parameter(text, "Executioner", "petsc_options_value", f"'{ITER_VALUES}'")
    return text


def _normalized(text: str) -> str:
    allowed = {"petsc_options_iname", "petsc_options_value"}
    out = []
    in_exec = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[Executioner]":
            in_exec = True
        elif in_exec and stripped == "[]":
            in_exec = False
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*=.*$", line)
        if in_exec and m and m.group(1) in allowed:
            out.append(f"  {m.group(1)} = <NUMERICAL_CONTROL>")
        else:
            out.append(line)
    return "\n".join(out)


def _build(level: int, iterative: bool) -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=level)
    if iterative:
        text = _iterative(text)
    return text, {
        **meta,
        "issue": 218,
        "parent_issue": 216,
        "numerical_solver": "gmres_ilu0" if iterative else "accepted_direct_lu",
        "physics_semantics_changed": False,
    }


def _stage(case_dir: Path, *, level: int, iterative: bool) -> tuple[str, dict[str, Any], dict[str, Any]]:
    text, meta = _build(level, iterative)
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


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def _equivalence(a: Mapping[str, float], b: Mapping[str, float]) -> dict[str, Any]:
    values = {}
    for key in EQUIV_KEYS:
        av, bv = float(a[key]), float(b[key])
        values[key] = {
            "direct_lu": av,
            "gmres_ilu0": bv,
            "relative_difference": _rel(av, bv),
        }
    max_rel = max(v["relative_difference"] for v in values.values())
    return {
        "a_priori_relative_tolerance": EQUIV_REL_TOL,
        "values": values,
        "max_relative_difference": max_rel,
        "passed": max_rel <= EQUIV_REL_TOL,
        "note": "net wall current excluded from relative equivalence because it may cross zero; both cases still retain W5 current/charge hard gates",
    }


def self_test() -> dict[str, Any]:
    base, _ = _build(1, False)
    test, _ = _build(1, True)
    r2, meta2 = _build(2, True)
    good = _equivalence({k: 1.0 for k in EQUIV_KEYS}, {k: 1.0 + 5e-5 for k in EQUIV_KEYS})
    bad = _equivalence({k: 1.0 for k in EQUIV_KEYS}, {k: 1.0 + 2e-4 for k in EQUIV_KEYS})
    checks = {
        "physics_semantics_normalized_equal": _normalized(base) == _normalized(test),
        "r2_preserved": mp.get_parameter(r2, "Mesh", "uniform_refine") == "2",
        "dt_preserved": math.isclose(float(meta2["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0),
        "end_time_preserved": math.isclose(float(meta2["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0),
        "iterative_pc": "-pc_type" in (mp.get_parameter(test, "Executioner", "petsc_options_iname") or "") and "ilu" in (mp.get_parameter(test, "Executioner", "petsc_options_value") or ""),
        "equivalence_positive_control": good["passed"] is True,
        "equivalence_negative_control": bad["passed"] is False,
    }
    failed = sorted(k for k, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _execute(exe: Path, out: Path, name: str, level: int, iterative: bool, timeout: float) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    text, meta, staging = _stage(case_dir, level=level, iterative=iterative)
    p2 = s5r._p2(exe, case_dir, logs / f"{name}_p2.log", timeout=timeout)
    item: dict[str, Any] = {"uniform_refine": level, "iterative": iterative, "meta": meta, "staging": staging, "p2": p2}
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


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue218Error(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue218Error(f"P0 failed: {p0}")
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
        "p0": p0,
        "cases": {},
        "bridge_equivalence": {},
        "mesh_convergence": {},
        "decision": {},
    }

    # Same-build accepted numerical references.
    summary["cases"]["coarse_lu"] = _execute(exe, out, "coarse_lu", 0, False, args.timeout)
    summary["cases"]["r1_lu"] = _execute(exe, out, "r1_lu", 1, False, args.timeout)
    if not (summary["cases"]["coarse_lu"]["hard_pass"] and summary["cases"]["r1_lu"]["hard_pass"]):
        summary["status"] = "ISSUE218_REFERENCE_PATH_FAIL"
        summary["decision"] = {"resource_remediation_ready": False, "reason": "same-build accepted LU reference failed"}
        _write(out, summary)
        return 2

    summary["cases"]["r1_ilu"] = _execute(exe, out, "r1_ilu", 1, True, args.timeout)
    if not summary["cases"]["r1_ilu"]["hard_pass"]:
        summary["status"] = "ISSUE218_ITERATIVE_R1_FAIL"
        summary["decision"] = {"resource_remediation_ready": False, "reason": "GMRES+ILU0 failed W5 hard gates at R1"}
        _write(out, summary)
        return 3

    bridge = _equivalence(
        summary["cases"]["r1_lu"]["evidence"]["endpoint"],
        summary["cases"]["r1_ilu"]["evidence"]["endpoint"],
    )
    summary["bridge_equivalence"] = bridge
    if not bridge["passed"]:
        summary["status"] = "ISSUE218_ITERATIVE_NOT_EQUIVALENT"
        summary["decision"] = {"resource_remediation_ready": False, "reason": "predeclared R1 endpoint equivalence failed"}
        _write(out, summary)
        return 4

    summary["cases"]["r2_ilu"] = _execute(exe, out, "r2_ilu", 2, True, args.timeout)
    if not summary["cases"]["r2_ilu"]["hard_pass"]:
        summary["status"] = "ISSUE218_R2_STILL_BLOCKED"
        summary["decision"] = {"resource_remediation_ready": False, "reason": "R2 did not complete W5 hard gates on validated lower-memory solver"}
        _write(out, summary)
        return 5

    endpoints = {
        "coarse": summary["cases"]["coarse_lu"]["evidence"]["endpoint"],
        "refine_1": summary["cases"]["r1_lu"]["evidence"]["endpoint"],
        "refine_2": summary["cases"]["r2_ilu"]["evidence"]["endpoint"],
    }
    summary["mesh_convergence"] = evr2._mesh_trends(endpoints)
    summary["status"] = "ISSUE218_R2_ENDPOINT_AND_MESH_TREND_READY"
    summary["decision"] = {
        "resource_remediation_ready": True,
        "r2_endpoint_complete": True,
        "bridge_equivalent": True,
        "validator_review_required": True,
        "post_hoc_threshold_used": False,
        "reason": "R1 solver equivalence passed before R2 use; R2 hard gates completed and coarse/R1/R2 trend is ready for #216 Validator review",
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--physics-opt", type=Path)
    p.add_argument("--results-root", type=Path, default=Path("issue218-r2-resource-results"))
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
