#!/usr/bin/env python3
"""Issue #216 W5 EVR-2 mesh-convergence discriminator.

This runner does not change production physics. It reuses the accepted W5
construction and analysis surface and evaluates the same bounded physical-time
case on coarse, uniform-refine-1, and uniform-refine-2 meshes. Numerical
adequacy is characterized by the contraction (or lack of contraction) of
successive endpoint differences; no post-hoc scientific pass threshold is
introduced here.
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
from physics_harness.adapters.moose import parameters as mp

EVR = 2
DT_S = w5.BASELINE_DT_S
END_TIME_S = w5.END_TIME_S
CASE_SPECS = (
    ("coarse", 0),
    ("refine_1", 1),
    ("refine_2", 2),
)
MATERIAL_KEYS = (
    "n_e_inventory",
    "n_e_min_m3",
    "n_epsilon_inventory",
    "n_epsilon_min",
    "mean_energy_avg_eV",
    "primary_electron_particle_rate_s-1",
    "primary_energy_power_W",
    "see_electron_particle_rate_s-1",
    "volume_charge_C",
    "phi_min_V",
    "phi_max_V",
    "rho_q_min_C_m3",
    "rho_q_max_C_m3",
    "net_outward_wall_current_A",
)


class Issue216EVR2Error(RuntimeError):
    pass


def _trend_triplet(v0: float, v1: float, v2: float) -> dict[str, Any]:
    values = (float(v0), float(v1), float(v2))
    if not all(math.isfinite(v) for v in values):
        return {"classification": "NONFINITE", "values": list(values)}
    d01 = abs(values[1] - values[0])
    d12 = abs(values[2] - values[1])
    if d01 == 0.0 and d12 == 0.0:
        classification = "IDENTICAL"
        ratio = 0.0
        order = None
    elif d01 == 0.0:
        classification = "NEW_DIFFERENCE_AFTER_ZERO"
        ratio = math.inf
        order = None
    else:
        ratio = d12 / d01
        if d12 < d01:
            classification = "CONTRACTING"
        elif d12 > d01:
            classification = "EXPANDING"
        else:
            classification = "STALLED"
        order = math.log(d01 / d12, 2.0) if d12 > 0.0 else math.inf
    signed01 = values[1] - values[0]
    signed12 = values[2] - values[1]
    return {
        "values": {"coarse": values[0], "refine_1": values[1], "refine_2": values[2]},
        "absolute_difference": {"coarse_to_r1": d01, "r1_to_r2": d12},
        "contraction_ratio_d12_over_d01": ratio,
        "observed_order_from_successive_differences": order,
        "monotone_direction": signed01 == 0.0 or signed12 == 0.0 or signed01 * signed12 > 0.0,
        "sign_change_present": (values[0] < 0.0 < values[1])
        or (values[1] < 0.0 < values[0])
        or (values[1] < 0.0 < values[2])
        or (values[2] < 0.0 < values[1]),
        "classification": classification,
    }


def _mesh_trends(endpoints: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    missing = [
        key
        for key in MATERIAL_KEYS
        if any(key not in endpoints[name] for name, _ in CASE_SPECS)
    ]
    if missing:
        raise Issue216EVR2Error(f"missing endpoint keys: {sorted(set(missing))}")
    trends = {
        key: _trend_triplet(
            endpoints["coarse"][key],
            endpoints["refine_1"][key],
            endpoints["refine_2"][key],
        )
        for key in MATERIAL_KEYS
    }
    counts: dict[str, int] = {}
    for item in trends.values():
        cls = str(item["classification"])
        counts[cls] = counts.get(cls, 0) + 1
    non_contracting = sorted(
        key
        for key, item in trends.items()
        if item["classification"] not in ("CONTRACTING", "IDENTICAL")
    )
    return {
        "status": "MEASURED_UNTHRESHOLDED",
        "method": (
            "uniform h-refinement levels 0,1,2 at equal physical time; compare absolute "
            "successive endpoint differences d01=|R1-R0| and d12=|R2-R1|. "
            "CONTRACTING means d12<d01. No post-hoc magnitude threshold is used."
        ),
        "classification_counts": counts,
        "non_contracting_observables": non_contracting,
        "all_material_observables_contracting_or_identical": not non_contracting,
        "observables": trends,
    }


def self_test() -> dict[str, Any]:
    predecessor = w5.self_test()
    text0, meta0 = w5._build_case(dt_s=DT_S, uniform_refine=0)
    text1, meta1 = w5._build_case(dt_s=DT_S, uniform_refine=1)
    text2, meta2 = w5._build_case(dt_s=DT_S, uniform_refine=2)
    contracting = _trend_triplet(1.0, 1.5, 1.6)
    expanding = _trend_triplet(1.0, 1.1, 1.3)
    sign_crossing = _trend_triplet(-0.1, 0.02, 0.01)
    checks = {
        "w5_predecessor_p0": predecessor["status"] == "PASS",
        "coarse_mesh_unmodified": mp.get_parameter(text0, "Mesh", "uniform_refine") in (None, "0"),
        "refine_1_level": mp.get_parameter(text1, "Mesh", "uniform_refine") == "1",
        "refine_2_level": mp.get_parameter(text2, "Mesh", "uniform_refine") == "2",
        "equal_physical_end_time": all(
            math.isclose(float(meta["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0)
            for meta in (meta0, meta1, meta2)
        ),
        "equal_timestep": all(
            math.isclose(float(meta["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0)
            for meta in (meta0, meta1, meta2)
        ),
        "five_steps_each": all(int(meta["expected_steps"]) == 5 for meta in (meta0, meta1, meta2)),
        "contracting_positive_control": contracting["classification"] == "CONTRACTING"
        and math.isclose(contracting["contraction_ratio_d12_over_d01"], 0.2),
        "expanding_negative_control": expanding["classification"] == "EXPANDING",
        "sign_crossing_recorded": sign_crossing["sign_change_present"] is True,
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def _write_summary(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue216EVR2Error(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue216EVR2Error(f"EVR-2 P0 failed: {p0}")

    out = args.results_root.resolve()
    cases_root = out / "cases"
    logs = out / "logs"
    cases_root.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 216,
        "evr": EVR,
        "parent_controller": 211,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "runtime_authority": "governed_ci_provenance_controlled",
        "physics_opt_realpath": str(exe),
        "physics_opt_sha256": w5._sha256(exe),
        "bounded_horizon_s": END_TIME_S,
        "timestep_s": DT_S,
        "p0": p0,
        "cases": {},
        "mesh_convergence": {},
        "decision": {},
        "claim_boundary": {
            "on_green": "W5 EVR-2 mesh-convergence evidence ready for terminal Validator review",
            "does_not_establish": [
                "a post-hoc numerical tolerance",
                "long-time powered ICP correctness",
                "A7 local user acceptance",
                "RF/Maxwell powered ICP closure",
            ],
        },
    }

    case_inputs: dict[str, str] = {}
    case_meta: dict[str, dict[str, Any]] = {}
    for name, level in CASE_SPECS:
        case_dir = cases_root / name
        text, meta, staging = w5._stage(case_dir, dt_s=DT_S, uniform_refine=level)
        case_inputs[name] = text
        case_meta[name] = meta
        summary["cases"][name] = {
            "dt_s": DT_S,
            "end_time_s": END_TIME_S,
            "uniform_refine": level,
            "staging": staging,
            "p2": {},
            "runtime": {},
            "evidence": {},
        }

    for name, _ in CASE_SPECS:
        case_dir = cases_root / name
        p2 = s5r._p2(exe, case_dir, logs / f"{name}_p2.log", timeout=args.timeout)
        summary["cases"][name]["p2"] = p2
        if p2["returncode"] != 0:
            summary["decision"] = {"core_hard_pass": False, "closure_ready": False, "reason": f"P2_FAIL_{name}"}
            summary["status"] = "W5_EVR2_P2_FAIL"
            _write_summary(out, summary)
            return 2

    core_pass = True
    for name, _ in CASE_SPECS:
        case_dir = cases_root / name
        runtime_log = logs / f"{name}_runtime.log"
        runtime = s5r._runtime(exe, case_dir, runtime_log, timeout=args.timeout)
        summary["cases"][name]["runtime"] = runtime
        try:
            evidence = w5._analyze_case(
                case_dir,
                input_text=case_inputs[name],
                meta=case_meta[name],
                runtime_log=runtime_log,
                runtime_returncode=int(runtime.get("returncode", 1)),
            )
        except (w5.Issue216Error, KeyError, ValueError, AssertionError) as exc:
            evidence = {"hard_pass": False, "analysis_error": str(exc)}
        summary["cases"][name]["evidence"] = evidence
        core_pass = core_pass and evidence.get("hard_pass") is True

    if core_pass:
        endpoints = {
            name: summary["cases"][name]["evidence"]["endpoint"] for name, _ in CASE_SPECS
        }
        summary["mesh_convergence"] = _mesh_trends(endpoints)
    else:
        summary["mesh_convergence"] = {"status": "NOT_EVALUATED_CASE_FAILURE"}

    summary["decision"] = {
        "core_hard_pass": core_pass,
        "closure_ready": False,
        "validator_review_required": True,
        "post_hoc_threshold_used": False,
        "reason": (
            "EVR-2 core invariants pass; coarse/R1/R2 contraction evidence is ready for terminal Validator review."
            if core_pass
            else "one or more EVR-2 runtime/invariant cases failed"
        ),
    }
    summary["status"] = (
        "W5_EVR2_MESH_EVIDENCE_READY_FOR_VALIDATOR_REVIEW"
        if core_pass
        else "W5_EVR2_RUNTIME_OR_INVARIANT_FAIL"
    )
    _write_summary(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0 if core_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue216-w5-evr2-results"))
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    if args.timeout <= 0.0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
