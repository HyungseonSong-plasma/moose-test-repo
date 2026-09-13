#!/usr/bin/env python3
"""Issue #224 C3: isolate Rhie-Chow GatherRCData/AD setup memory.

Both branches use diagnostic-only average velocity interpolation and zero physical
steps.  The control uses the standard INSFVRhieChowInterpolator, whose execute()
intentionally still gathers momentum residual/Jacobian AD data even in average
mode.  The ablation branch changes only the UserObject type to a diagnostic
subclass whose execute() is a no-op.

This is attribution-only. The no-gather object must never be used for physics.
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
STANDARD_RC = "INSFVRhieChowInterpolator"
NO_GATHER_RC = "PhysicsDiagnosticNoGatherRhieChowInterpolator"
CASE_SPECS = (
    ("r1_standard_average", 1, False),
    ("r1_no_gather_average", 1, True),
    ("r2_standard_average", 2, False),
    ("r2_no_gather_average", 2, True),
)


class Issue224C3Error(RuntimeError):
    pass


def _build(level: int, no_gather: bool) -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=level)
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "0")
    text = mp.upsert_parameter(text, "GlobalParams", "velocity_interp_method", "average")
    rc_path = "UserObjects/rc"
    if mp.get_parameter(text, rc_path, "type") != STANDARD_RC:
        raise Issue224C3Error("unexpected production Rhie-Chow UserObject type")
    if no_gather:
        text = mp.upsert_parameter(text, rc_path, "type", NO_GATHER_RC)
    return text, {
        **meta,
        "issue": 224,
        "parent_issue": 222,
        "diagnostic": "C3_RHIE_CHOW_GATHER_AD_MEMORY",
        "uniform_refine": level,
        "velocity_interp_method": "average",
        "rc_object_type": NO_GATHER_RC if no_gather else STANDARD_RC,
        "gather_execute_enabled": not no_gather,
        "num_steps": 0,
        "physical_timestep_executed": False,
        "production_promotion_claim": False,
    }


def _stage(case_dir: Path, *, level: int, no_gather: bool) -> tuple[str, dict[str, Any]]:
    text, meta = _build(level, no_gather)
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
    no_gather: bool,
    timeout: float,
) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    input_text, meta = _stage(case_dir, level=level, no_gather=no_gather)

    p2_log = logs / f"{name}_p2.log"
    p2 = s5r._p2(exe, case_dir, p2_log, timeout=timeout)
    item: dict[str, Any] = {
        "uniform_refine": level,
        "branch": "no_gather_average" if no_gather else "standard_average",
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
                "average_interp": mp.get_parameter(input_text, "GlobalParams", "velocity_interp_method") == "average",
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
        and item["guards"]["average_interp"]
    )
    if not item["hard_pass"]:
        item["reason"] = "SETUP_ONLY_CONTRACT_FAIL"
    return item


def _delta(control: Mapping[str, Any], ablation: Mapping[str, Any], key: str) -> dict[str, float | None]:
    a = control.get("memory", {}).get(key)
    b = ablation.get("memory", {}).get(key)
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return {"control_mb": None, "ablation_mb": None, "reduction_mb": None, "reduction_fraction": None}
    reduction = float(a) - float(b)
    return {
        "control_mb": float(a),
        "ablation_mb": float(b),
        "reduction_mb": reduction,
        "reduction_fraction": reduction / float(a) if float(a) else None,
    }


def _removed_increment_fraction(control: Mapping[str, Any], ablation: Mapping[str, Any]) -> float | None:
    a = control.get("memory", {}).get("setup_to_user_object_increment_mb")
    b = ablation.get("memory", {}).get("setup_to_user_object_increment_mb")
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or float(a) <= 0.0:
        return None
    return (float(a) - float(b)) / float(a)


def _classify(frac: float | None) -> str:
    if frac is None:
        return "UNRESOLVED"
    if frac >= 0.75:
        return "RC_GATHER_AD_STORAGE_DOMINANT"
    if frac >= 0.25:
        return "RC_GATHER_AD_STORAGE_MATERIAL_CONTRIBUTOR"
    return "RC_GATHER_AD_STORAGE_NOT_DOMINANT"


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for name, level, no_gather in CASE_SPECS:
        text, meta = _build(level, no_gather)
        checks[f"{name}_num_steps_zero"] = mp.get_parameter(text, "Executioner", "num_steps") == "0"
        checks[f"{name}_mesh_level"] = mp.get_parameter(text, "Mesh", "uniform_refine") == str(level)
        checks[f"{name}_average_interp"] = mp.get_parameter(text, "GlobalParams", "velocity_interp_method") == "average"
        checks[f"{name}_rc_type"] = mp.get_parameter(text, "UserObjects/rc", "type") == (
            NO_GATHER_RC if no_gather else STANDARD_RC
        )
        checks[f"{name}_dt_preserved"] = math.isclose(float(meta["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0)
        checks[f"{name}_end_time_preserved"] = math.isclose(float(meta["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0)
        for species in SOLVED_HEAVY:
            checks[f"{name}_conservative_time_preserved:{species}"] = (
                mp.get_parameter(text, f"FVKernels/{species}_time", "type")
                == "PhysicsFVConservativeMassFractionTimeDerivative"
            )
    checks["classification_dominant"] = _classify(0.80) == "RC_GATHER_AD_STORAGE_DOMINANT"
    checks["classification_material"] = _classify(0.50) == "RC_GATHER_AD_STORAGE_MATERIAL_CONTRIBUTOR"
    checks["classification_not_dominant"] = _classify(0.10) == "RC_GATHER_AD_STORAGE_NOT_DOMINANT"
    failed = sorted(key for key, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue224C3Error(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue224C3Error(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 224,
        "parent_issue": 222,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": w5._sha256(exe),
        "diagnostic": "C3_RHIE_CHOW_GATHER_AD_MEMORY",
        "physical_timesteps_authorized": 0,
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    for name, level, no_gather in CASE_SPECS:
        case = _execute(
            exe,
            out,
            name=name,
            level=level,
            no_gather=no_gather,
            timeout=args.timeout,
        )
        summary["cases"][name] = case
        _write(out, summary)
        if not case["hard_pass"]:
            summary["status"] = "ISSUE224_C3_HOLD"
            summary["decision"] = {
                "classification": "UNRESOLVED",
                "reason": f"setup-only contract failed for {name}",
                "full_r2_solve_executed": False,
            }
            _write(out, summary)
            return 2

    comparisons: dict[str, Any] = {}
    fractions: dict[str, float | None] = {}
    for level in ("r1", "r2"):
        control = summary["cases"][f"{level}_standard_average"]
        ablation = summary["cases"][f"{level}_no_gather_average"]
        comparisons[level] = {
            key: _delta(control, ablation, key)
            for key in (
                "setup_mb",
                "post_user_object_mb",
                "setup_to_user_object_increment_mb",
                "peak_resident_mb",
            )
        }
        fractions[level] = _removed_increment_fraction(control, ablation)

    classification = _classify(fractions["r2"])
    summary["status"] = "ISSUE224_C3_ATTRIBUTION_READY"
    summary["decision"] = {
        "classification": classification,
        "removed_setup_to_uo_fraction": fractions,
        "comparisons": comparisons,
        "full_r2_solve_executed": False,
        "promotion_authorized": False,
        "interpretation": (
            "This experiment attributes memory to standard MOOSE GatherRCData/AD execution. The no-gather subclass is diagnostic-only and cannot be promoted."
        ),
        "next_action": (
            "If dominant/material, inspect how much retained AD derivative state in the gathered a-coefficients is mathematically required and test a source-backed derivative-thinning/lifetime strategy; also retain autoscaling as a separate ~0.55 GiB later-phase target."
            if classification != "RC_GATHER_AD_STORAGE_NOT_DOMINANT"
            else "Continue initial-setup attribution outside Rhie-Chow GatherRCData."
        ),
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue224-c3-rc-gather-memory-results"))
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
