#!/usr/bin/env python3
"""Issue #222 B1: setup-only Rhie-Chow baseline-memory discriminator.

This diagnostic deliberately performs zero physical timesteps. It compares the
production Rhie-Chow interpolation path with a diagnostic-only average-velocity
branch at R1/R2 to attribute setup->UserObject resident-memory growth without
entering a nonlinear/linear solve.
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
from physics_harness.adapters.moose.performance.collection import parse_problem_identity
from physics_harness.adapters.moose.performance.profile import live_memory_samples
from physics_harness.execution.cases import stage_case, validate_case_references

DT_S = w5.BASELINE_DT_S
END_TIME_S = w5.END_TIME_S
CASE_SPECS = (
    ("r1_rc", 1, "rc"),
    ("r1_average", 1, "average"),
    ("r2_rc", 2, "rc"),
    ("r2_average", 2, "average"),
)


class Issue222Error(RuntimeError):
    pass


def _build(level: int, velocity_interp: str) -> tuple[str, dict[str, Any]]:
    if velocity_interp not in {"rc", "average"}:
        raise Issue222Error(f"unsupported velocity interpolation: {velocity_interp}")
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=level)
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "0")
    text = mp.upsert_parameter(text, "GlobalParams", "velocity_interp_method", velocity_interp)
    return text, {
        **meta,
        "issue": 222,
        "parent_issue": 219,
        "diagnostic": "B1_RHIE_CHOW_SETUP_MEMORY",
        "uniform_refine": level,
        "velocity_interp_method": velocity_interp,
        "num_steps": 0,
        "physical_timestep_executed": False,
        "diagnostic_only_numerical_branch": velocity_interp == "average",
        "production_physics_claim": False,
    }


def _stage(case_dir: Path, *, level: int, velocity_interp: str) -> tuple[str, dict[str, Any]]:
    text, meta = _build(level, velocity_interp)
    stage_case(
        w5.SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    s5r._copy_runtime_assets(case_dir)
    refs = validate_case_references(case_dir)
    meta = {**meta, "references": refs}
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return text, meta


def _sample(samples: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    return next((sample for sample in samples if sample.get("label") == label), None)


def _mb(sample: Mapping[str, Any] | None) -> float | None:
    if not sample:
        return None
    value = sample.get("resident_mb")
    return float(value) if isinstance(value, (int, float)) else None


def _execute(
    exe: Path,
    out: Path,
    *,
    name: str,
    level: int,
    velocity_interp: str,
    timeout: float,
) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    input_text, meta = _stage(case_dir, level=level, velocity_interp=velocity_interp)

    p2_log = logs / f"{name}_p2.log"
    p2 = s5r._p2(exe, case_dir, p2_log, timeout=timeout)
    item: dict[str, Any] = {
        "uniform_refine": level,
        "velocity_interp_method": velocity_interp,
        "meta": meta,
        "p2": p2,
        "hard_pass": False,
    }
    if p2.get("returncode") != 0:
        item["reason"] = "P2_FAIL"
        return item

    runtime_log = logs / f"{name}_runtime.log"
    runtime = s5r._runtime(exe, case_dir, runtime_log, timeout=timeout)
    text = runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""
    samples = live_memory_samples(runtime_log)
    setup = _sample(samples, "Finished Setting Up")
    user_objects = _sample(samples, "Finished Computing User Objects")
    initial_setup = _sample(samples, "Finished Performing Initial Setup")
    peak = max(samples, key=lambda x: float(x["resident_mb"])) if samples else None
    setup_mb = _mb(setup)
    user_mb = _mb(user_objects) or _mb(initial_setup)
    increment = user_mb - setup_mb if setup_mb is not None and user_mb is not None else None
    no_linear_solve = "Linear solve" not in text and "SNES Function norm" not in text
    no_physical_step = "Time Step 1" not in text
    problem = parse_problem_identity(text)

    item.update(
        {
            "runtime": runtime,
            "problem": problem,
            "memory": {
                "setup_mb": setup_mb,
                "post_user_object_mb": user_mb,
                "setup_to_user_object_increment_mb": increment,
                "peak_resident_mb": _mb(peak),
                "samples_observed": len(samples),
            },
            "guards": {
                "no_linear_solve": no_linear_solve,
                "no_physical_timestep": no_physical_step,
                "num_steps_is_zero": mp.get_parameter(input_text, "Executioner", "num_steps") == "0",
            },
        }
    )
    item["hard_pass"] = (
        runtime.get("returncode") == 0
        and setup_mb is not None
        and user_mb is not None
        and no_linear_solve
        and no_physical_step
        and item["guards"]["num_steps_is_zero"]
    )
    if not item["hard_pass"]:
        item["reason"] = "SETUP_ONLY_CONTRACT_FAIL"
    return item


def _removed_fraction(rc: Mapping[str, Any], avg: Mapping[str, Any]) -> float | None:
    rc_inc = rc.get("memory", {}).get("setup_to_user_object_increment_mb")
    avg_inc = avg.get("memory", {}).get("setup_to_user_object_increment_mb")
    if not isinstance(rc_inc, (int, float)) or not isinstance(avg_inc, (int, float)) or rc_inc <= 0:
        return None
    return (float(rc_inc) - float(avg_inc)) / float(rc_inc)


def _classify(frac: float | None) -> str:
    if frac is None:
        return "UNRESOLVED"
    if frac >= 0.75:
        return "RHIE_CHOW_AD_STORAGE_DOMINANT"
    if frac >= 0.25:
        return "RHIE_CHOW_AD_STORAGE_MATERIAL_CONTRIBUTOR"
    return "RHIE_CHOW_NOT_DOMINANT"


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for name, level, interp in CASE_SPECS:
        text, meta = _build(level, interp)
        checks[f"{name}_num_steps_zero"] = mp.get_parameter(text, "Executioner", "num_steps") == "0"
        checks[f"{name}_mesh_level"] = mp.get_parameter(text, "Mesh", "uniform_refine") == str(level)
        checks[f"{name}_velocity_interp"] = (
            mp.get_parameter(text, "GlobalParams", "velocity_interp_method") == interp
        )
        checks[f"{name}_dt_preserved"] = math.isclose(float(meta["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0)
        checks[f"{name}_end_time_preserved"] = math.isclose(float(meta["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0)
    checks["classification_dominant"] = _classify(0.80) == "RHIE_CHOW_AD_STORAGE_DOMINANT"
    checks["classification_material"] = _classify(0.50) == "RHIE_CHOW_AD_STORAGE_MATERIAL_CONTRIBUTOR"
    checks["classification_not_dominant"] = _classify(0.10) == "RHIE_CHOW_NOT_DOMINANT"
    failed = sorted(key for key, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue222Error(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue222Error(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 222,
        "parent_issue": 219,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": w5._sha256(exe),
        "diagnostic": "B1_RHIE_CHOW_SETUP_MEMORY",
        "physical_timesteps_authorized": 0,
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    for name, level, interp in CASE_SPECS:
        case = _execute(
            exe,
            out,
            name=name,
            level=level,
            velocity_interp=interp,
            timeout=args.timeout,
        )
        summary["cases"][name] = case
        _write(out, summary)
        if not case["hard_pass"]:
            summary["status"] = "ISSUE222_B1_HOLD"
            summary["decision"] = {
                "classification": "UNRESOLVED",
                "reason": f"setup-only contract failed for {name}",
                "full_r2_solve_executed": False,
            }
            _write(out, summary)
            return 2

    r1_fraction = _removed_fraction(summary["cases"]["r1_rc"], summary["cases"]["r1_average"])
    r2_fraction = _removed_fraction(summary["cases"]["r2_rc"], summary["cases"]["r2_average"])
    classification = _classify(r2_fraction)
    summary["status"] = "ISSUE222_B1_ATTRIBUTION_READY"
    summary["decision"] = {
        "classification": classification,
        "r1_removed_fraction": r1_fraction,
        "r2_removed_fraction": r2_fraction,
        "full_r2_solve_executed": False,
        "diagnostic_average_is_production_candidate": False,
        "next_action": (
            "Investigate reducing/clearing Rhie-Chow AD coefficient derivative storage while preserving RC mathematics."
            if classification in {"RHIE_CHOW_AD_STORAGE_DOMINANT", "RHIE_CHOW_AD_STORAGE_MATERIAL_CONTRIBUTOR"}
            else "Continue baseline attribution with vectors/Jacobian/AD-material storage."
        ),
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument(
        "--results-root", type=Path, default=Path("issue222-baseline-memory-results")
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None:
        parser.error("--physics-opt required unless --self-test")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
