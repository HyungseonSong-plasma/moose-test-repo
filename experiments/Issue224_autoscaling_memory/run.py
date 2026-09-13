#!/usr/bin/env python3
"""Issue #224 C2: setup-only automatic-scaling memory discriminator.

This diagnostic performs zero physical timesteps and no linear solve. It keeps
all W5 physics/discretization objects unchanged while comparing only the MOOSE
nonlinear automatic-scaling allocation policy:

  production     : automatic_scaling=true, off-diagonals=true
  diagonal_only  : automatic_scaling=true, off-diagonals=false
  scaling_off    : automatic_scaling=false

The purpose is attribution of the R2 setup/post-UserObject resident-memory
increment. No branch is a production promotion candidate from this experiment
alone.
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
SOLVED_HEAVY = ("O2s", "O2p", "O", "Om", "Op", "Os")
CASE_SPECS = (
    ("r1_production", 1, "production"),
    ("r1_diagonal_only", 1, "diagonal_only"),
    ("r1_scaling_off", 1, "scaling_off"),
    ("r2_production", 2, "production"),
    ("r2_diagonal_only", 2, "diagonal_only"),
    ("r2_scaling_off", 2, "scaling_off"),
)


class Issue224C2Error(RuntimeError):
    pass


def _configure_scaling(text: str, branch: str) -> str:
    if branch == "production":
        # Preserve the inherited production settings exactly.
        expected = {
            "automatic_scaling": "true",
            "off_diagonals_in_auto_scaling": "true",
            "compute_scaling_once": "false",
        }
        for name, value in expected.items():
            actual = (mp.get_parameter(text, "Executioner", name) or "").strip().lower()
            if actual != value:
                raise Issue224C2Error(
                    f"unexpected production Executioner/{name}: {actual!r} != {value!r}"
                )
        return text
    if branch == "diagonal_only":
        return mp.upsert_parameter(text, "Executioner", "off_diagonals_in_auto_scaling", "false")
    if branch == "scaling_off":
        return mp.upsert_parameter(text, "Executioner", "automatic_scaling", "false")
    raise Issue224C2Error(f"unsupported scaling branch: {branch}")


def _build(level: int, branch: str) -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=level)
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "0")
    text = _configure_scaling(text, branch)
    return text, {
        **meta,
        "issue": 224,
        "parent_issue": 222,
        "diagnostic": "C2_AUTOMATIC_SCALING_SETUP_MEMORY",
        "uniform_refine": level,
        "scaling_branch": branch,
        "num_steps": 0,
        "physical_timestep_executed": False,
        "production_promotion_claim": False,
    }


def _stage(case_dir: Path, *, level: int, branch: str) -> tuple[str, dict[str, Any]]:
    text, meta = _build(level, branch)
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
    branch: str,
    timeout: float,
) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    input_text, meta = _stage(case_dir, level=level, branch=branch)

    p2_log = logs / f"{name}_p2.log"
    p2 = s5r._p2(exe, case_dir, p2_log, timeout=timeout)
    item: dict[str, Any] = {
        "uniform_refine": level,
        "branch": branch,
        "meta": meta,
        "p2": p2,
        "hard_pass": False,
    }
    if p2.get("returncode") != 0:
        item["reason"] = "P2_FAIL"
        return item

    runtime_log = logs / f"{name}_runtime.log"
    runtime = s5r._runtime(exe, case_dir, runtime_log, timeout=timeout)
    log_text = runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""
    samples = live_memory_samples(runtime_log)
    setup = _sample(samples, "Finished Setting Up")
    user_objects = _sample(samples, "Finished Computing User Objects")
    initial_setup = _sample(samples, "Finished Performing Initial Setup")
    peak = max(samples, key=lambda x: float(x["resident_mb"])) if samples else None
    setup_mb = _mb(setup)
    user_mb = _mb(user_objects) or _mb(initial_setup)
    no_linear_solve = "Linear solve" not in log_text and "SNES Function norm" not in log_text
    no_physical_step = "Time Step 1" not in log_text

    item.update(
        {
            "runtime": runtime,
            "problem": parse_problem_identity(log_text),
            "memory": {
                "setup_mb": setup_mb,
                "post_user_object_mb": user_mb,
                "setup_to_user_object_increment_mb": (
                    user_mb - setup_mb
                    if setup_mb is not None and user_mb is not None
                    else None
                ),
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


def _delta(reference: Mapping[str, Any], candidate: Mapping[str, Any], key: str) -> dict[str, float | None]:
    a = reference.get("memory", {}).get(key)
    b = candidate.get("memory", {}).get(key)
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return {
            "production_mb": None,
            "candidate_mb": None,
            "reduction_mb": None,
            "reduction_fraction": None,
        }
    reduction = float(a) - float(b)
    return {
        "production_mb": float(a),
        "candidate_mb": float(b),
        "reduction_mb": reduction,
        "reduction_fraction": reduction / float(a) if float(a) else None,
    }


def _removed_fraction(reference: Mapping[str, Any], candidate: Mapping[str, Any]) -> float | None:
    a = reference.get("memory", {}).get("setup_to_user_object_increment_mb")
    b = candidate.get("memory", {}).get("setup_to_user_object_increment_mb")
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or float(a) <= 0.0:
        return None
    return (float(a) - float(b)) / float(a)


def _classify(diagonal_fraction: float | None, off_fraction: float | None) -> str:
    if diagonal_fraction is None or off_fraction is None:
        return "UNRESOLVED"
    if diagonal_fraction >= 0.75:
        return "OFFDIAGONAL_AUTOSCALING_STORAGE_DOMINANT"
    if off_fraction >= 0.75:
        return "AUTOMATIC_SCALING_STORAGE_DOMINANT"
    if diagonal_fraction >= 0.25:
        return "OFFDIAGONAL_AUTOSCALING_MATERIAL_CONTRIBUTOR"
    if off_fraction >= 0.25:
        return "AUTOMATIC_SCALING_MATERIAL_CONTRIBUTOR"
    return "AUTOMATIC_SCALING_NOT_DOMINANT"


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for name, level, branch in CASE_SPECS:
        text, meta = _build(level, branch)
        checks[f"{name}_num_steps_zero"] = mp.get_parameter(text, "Executioner", "num_steps") == "0"
        checks[f"{name}_mesh_level"] = mp.get_parameter(text, "Mesh", "uniform_refine") == str(level)
        checks[f"{name}_dt_preserved"] = math.isclose(float(meta["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0)
        checks[f"{name}_end_time_preserved"] = math.isclose(float(meta["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0)
        auto = (mp.get_parameter(text, "Executioner", "automatic_scaling") or "").strip().lower()
        offdiag = (mp.get_parameter(text, "Executioner", "off_diagonals_in_auto_scaling") or "").strip().lower()
        once = (mp.get_parameter(text, "Executioner", "compute_scaling_once") or "").strip().lower()
        if branch == "production":
            checks[f"{name}_scaling_contract"] = auto == "true" and offdiag == "true" and once == "false"
        elif branch == "diagonal_only":
            checks[f"{name}_scaling_contract"] = auto == "true" and offdiag == "false" and once == "false"
        else:
            checks[f"{name}_scaling_contract"] = auto == "false" and offdiag == "true" and once == "false"
        checks[f"{name}_rhie_chow_preserved"] = (
            (mp.get_parameter(text, "GlobalParams", "velocity_interp_method") or "").strip() == "rc"
        )
        for species in SOLVED_HEAVY:
            checks[f"{name}_conservative_time_preserved:{species}"] = (
                mp.get_parameter(text, f"FVKernels/{species}_time", "type")
                == "PhysicsFVConservativeMassFractionTimeDerivative"
            )
    checks["classification_offdiag"] = _classify(0.80, 0.90) == "OFFDIAGONAL_AUTOSCALING_STORAGE_DOMINANT"
    checks["classification_auto"] = _classify(0.10, 0.80) == "AUTOMATIC_SCALING_STORAGE_DOMINANT"
    checks["classification_not_dominant"] = _classify(0.10, 0.15) == "AUTOMATIC_SCALING_NOT_DOMINANT"
    failed = sorted(key for key, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue224C2Error(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue224C2Error(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 224,
        "parent_issue": 222,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": w5._sha256(exe),
        "diagnostic": "C2_AUTOMATIC_SCALING_SETUP_MEMORY",
        "physical_timesteps_authorized": 0,
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    for name, level, branch in CASE_SPECS:
        case = _execute(
            exe,
            out,
            name=name,
            level=level,
            branch=branch,
            timeout=args.timeout,
        )
        summary["cases"][name] = case
        _write(out, summary)
        if not case["hard_pass"]:
            summary["status"] = "ISSUE224_C2_HOLD"
            summary["decision"] = {
                "classification": "UNRESOLVED",
                "reason": f"setup-only contract failed for {name}",
                "full_r2_solve_executed": False,
            }
            _write(out, summary)
            return 2

    comparisons: dict[str, Any] = {}
    fractions: dict[str, Any] = {}
    for level in ("r1", "r2"):
        prod = summary["cases"][f"{level}_production"]
        diag = summary["cases"][f"{level}_diagonal_only"]
        off = summary["cases"][f"{level}_scaling_off"]
        comparisons[level] = {
            "diagonal_only": {
                key: _delta(prod, diag, key)
                for key in (
                    "setup_mb",
                    "post_user_object_mb",
                    "setup_to_user_object_increment_mb",
                    "peak_resident_mb",
                )
            },
            "scaling_off": {
                key: _delta(prod, off, key)
                for key in (
                    "setup_mb",
                    "post_user_object_mb",
                    "setup_to_user_object_increment_mb",
                    "peak_resident_mb",
                )
            },
        }
        fractions[level] = {
            "diagonal_only_removed_setup_to_uo_fraction": _removed_fraction(prod, diag),
            "scaling_off_removed_setup_to_uo_fraction": _removed_fraction(prod, off),
        }

    r2_diag = fractions["r2"]["diagonal_only_removed_setup_to_uo_fraction"]
    r2_off = fractions["r2"]["scaling_off_removed_setup_to_uo_fraction"]
    classification = _classify(r2_diag, r2_off)
    summary["status"] = "ISSUE224_C2_ATTRIBUTION_READY"
    summary["decision"] = {
        "classification": classification,
        "fractions": fractions,
        "comparisons": comparisons,
        "full_r2_solve_executed": False,
        "promotion_authorized": False,
        "next_action": (
            "If autoscaling storage is material/dominant, validate a bounded R1 production candidate: diagonal-only autoscaling first when sufficient; otherwise explicit/manual scaling with automatic scaling disabled. Preserve all W5 physics and hard gates."
            if classification != "AUTOMATIC_SCALING_NOT_DOMINANT"
            else "Continue baseline attribution with matrix/vector allocation and AD/material dependency storage."
        ),
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue224-c2-autoscaling-memory-results"))
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
