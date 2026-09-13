#!/usr/bin/env python3
"""Issue #224 C1: setup-only memory A/B for standard-MOOSE source projectors.

Compare the accepted W5 production construction against a diagnostic branch that
replaces only thin heavy/electron reaction-source projector kernels with standard
MOOSE FVCoupledForce. Conservative species accumulation and all transport,
kinetics, sheath, coefficients, mesh, and Rhie-Chow semantics remain unchanged.
No physical timestep or linear solve is authorized.
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
    ("r1_custom", 1, False),
    ("r1_standard", 1, True),
    ("r2_custom", 2, False),
    ("r2_standard", 2, True),
)


class Issue224Error(RuntimeError):
    pass


def _replace_source_projectors(text: str) -> tuple[str, dict[str, Any]]:
    replacements: list[dict[str, Any]] = []

    for species in SOLVED_HEAVY:
        path = f"FVKernels/s5r_source_{species}"
        typ = mp.get_parameter(text, path, "type")
        source = mp.get_parameter(text, path, "source")
        if typ != "PhysicsFVSpeciesReactionSource" or not source:
            raise Issue224Error(f"unexpected heavy projector contract at {path}: type={typ}, source={source}")
        text = mp.upsert_parameter(text, path, "type", "FVCoupledForce")
        text = mp.remove_parameter(text, path, "source")
        text = mp.upsert_parameter(text, path, "v", source)
        text = mp.upsert_parameter(text, path, "coef", "1.0")
        replacements.append({"path": path, "from": typ, "to": "FVCoupledForce", "v": source, "coef": 1.0})

    path = "FVKernels/s5r_electron_source"
    typ = mp.get_parameter(text, path, "type")
    source = mp.get_parameter(text, path, "number_source")
    n_ref_raw = mp.get_parameter(text, path, "n_ref")
    if typ != "PhysicsFVElectronReactionSource" or not source or not n_ref_raw:
        raise Issue224Error(
            f"unexpected electron projector contract at {path}: type={typ}, source={source}, n_ref={n_ref_raw}"
        )
    n_ref = float(n_ref_raw)
    if not math.isfinite(n_ref) or n_ref <= 0.0:
        raise Issue224Error(f"invalid n_ref={n_ref_raw}")
    coef = 1.0 / n_ref
    text = mp.upsert_parameter(text, path, "type", "FVCoupledForce")
    text = mp.remove_parameter(text, path, "number_source")
    text = mp.remove_parameter(text, path, "n_ref")
    text = mp.upsert_parameter(text, path, "v", source)
    text = mp.upsert_parameter(text, path, "coef", f"{coef:.17g}")
    replacements.append({"path": path, "from": typ, "to": "FVCoupledForce", "v": source, "coef": coef})

    return text, {"replacement_count": len(replacements), "replacements": replacements}


def _build(level: int, standard: bool) -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=level)
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "0")
    replacement_meta: dict[str, Any] = {"replacement_count": 0, "replacements": []}
    if standard:
        text, replacement_meta = _replace_source_projectors(text)
    return text, {
        **meta,
        "issue": 224,
        "parent_issue": 222,
        "diagnostic": "C1_STANDARD_SOURCE_PROJECTOR_MEMORY",
        "uniform_refine": level,
        "source_projector_branch": "standard_fv_coupled_force" if standard else "custom_production",
        "num_steps": 0,
        "physical_timestep_executed": False,
        "replacement": replacement_meta,
        "production_promotion_claim": False,
    }


def _stage(case_dir: Path, *, level: int, standard: bool) -> tuple[str, dict[str, Any]]:
    text, meta = _build(level, standard)
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


def _execute(exe: Path, out: Path, *, name: str, level: int, standard: bool, timeout: float) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    input_text, meta = _stage(case_dir, level=level, standard=standard)

    p2_log = logs / f"{name}_p2.log"
    p2 = s5r._p2(exe, case_dir, p2_log, timeout=timeout)
    item: dict[str, Any] = {
        "uniform_refine": level,
        "branch": "standard" if standard else "custom",
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

    item.update({
        "runtime": runtime,
        "problem": parse_problem_identity(log_text),
        "memory": {
            "setup_mb": setup_mb,
            "post_user_object_mb": user_mb,
            "setup_to_user_object_increment_mb": (
                user_mb - setup_mb if setup_mb is not None and user_mb is not None else None
            ),
            "peak_resident_mb": _mb(peak),
            "samples_observed": len(samples),
        },
        "guards": {
            "no_linear_solve": no_linear_solve,
            "no_physical_timestep": no_physical_step,
            "num_steps_is_zero": mp.get_parameter(input_text, "Executioner", "num_steps") == "0",
        },
    })
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


def _delta(custom: Mapping[str, Any], standard: Mapping[str, Any], key: str) -> dict[str, float | None]:
    a = custom.get("memory", {}).get(key)
    b = standard.get("memory", {}).get(key)
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return {"custom_mb": None, "standard_mb": None, "reduction_mb": None, "reduction_fraction": None}
    reduction = float(a) - float(b)
    return {
        "custom_mb": float(a),
        "standard_mb": float(b),
        "reduction_mb": reduction,
        "reduction_fraction": reduction / float(a) if float(a) else None,
    }


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    custom, _ = _build(1, False)
    standard, meta = _build(1, True)
    checks["replacement_count_7"] = meta["replacement"]["replacement_count"] == len(SOLVED_HEAVY) + 1
    for species in SOLVED_HEAVY:
        source_path = f"FVKernels/s5r_source_{species}"
        time_path = f"FVKernels/{species}_time"
        checks[f"custom_heavy_projector:{species}"] = mp.get_parameter(custom, source_path, "type") == "PhysicsFVSpeciesReactionSource"
        checks[f"standard_heavy_projector:{species}"] = (
            mp.get_parameter(standard, source_path, "type") == "FVCoupledForce"
            and mp.get_parameter(standard, source_path, "v") == f"S_{species}_s5r"
            and float(mp.get_parameter(standard, source_path, "coef") or "nan") == 1.0
        )
        checks[f"conservative_time_preserved_custom:{species}"] = mp.get_parameter(custom, time_path, "type") == "PhysicsFVConservativeMassFractionTimeDerivative"
        checks[f"conservative_time_preserved_standard:{species}"] = mp.get_parameter(standard, time_path, "type") == "PhysicsFVConservativeMassFractionTimeDerivative"
    ep = "FVKernels/s5r_electron_source"
    checks["custom_electron_projector"] = mp.get_parameter(custom, ep, "type") == "PhysicsFVElectronReactionSource"
    checks["standard_electron_projector"] = (
        mp.get_parameter(standard, ep, "type") == "FVCoupledForce"
        and mp.get_parameter(standard, ep, "v") == "S_e_s5r"
        and mp.get_parameter(standard, ep, "number_source") is None
        and mp.get_parameter(standard, ep, "n_ref") is None
    )
    for name, level, standard_branch in CASE_SPECS:
        text, case_meta = _build(level, standard_branch)
        checks[f"{name}_num_steps_zero"] = mp.get_parameter(text, "Executioner", "num_steps") == "0"
        checks[f"{name}_mesh_level"] = mp.get_parameter(text, "Mesh", "uniform_refine") == str(level)
        checks[f"{name}_dt_preserved"] = math.isclose(float(case_meta["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0)
        checks[f"{name}_end_time_preserved"] = math.isclose(float(case_meta["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0)
    failed = sorted(key for key, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue224Error(f"invalid physics-opt: {exe}")
    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue224Error(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 224,
        "parent_issue": 222,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": w5._sha256(exe),
        "diagnostic": "C1_STANDARD_SOURCE_PROJECTOR_MEMORY",
        "physical_timesteps_authorized": 0,
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    for name, level, standard in CASE_SPECS:
        case = _execute(exe, out, name=name, level=level, standard=standard, timeout=args.timeout)
        summary["cases"][name] = case
        _write(out, summary)
        if not case["hard_pass"]:
            summary["status"] = "ISSUE224_C1_HOLD"
            summary["decision"] = {"reason": f"setup-only contract failed for {name}", "full_r2_solve_executed": False}
            _write(out, summary)
            return 2

    comparisons: dict[str, Any] = {}
    for level in ("r1", "r2"):
        custom = summary["cases"][f"{level}_custom"]
        standard = summary["cases"][f"{level}_standard"]
        comparisons[level] = {
            key: _delta(custom, standard, key)
            for key in ("setup_mb", "post_user_object_mb", "setup_to_user_object_increment_mb", "peak_resident_mb")
        }

    r2_peak = comparisons["r2"]["peak_resident_mb"]
    reduction_mb = r2_peak.get("reduction_mb")
    reduction_fraction = r2_peak.get("reduction_fraction")
    if isinstance(reduction_mb, (int, float)) and isinstance(reduction_fraction, (int, float)) and reduction_mb >= 64.0 and reduction_fraction >= 0.02:
        classification = "MATERIAL_SETUP_MEMORY_REDUCTION"
    elif isinstance(reduction_mb, (int, float)) and reduction_mb > 0.0:
        classification = "SMALL_OR_NOISY_SETUP_MEMORY_REDUCTION"
    else:
        classification = "NO_MEASURABLE_SETUP_MEMORY_REDUCTION"

    summary["status"] = "ISSUE224_C1_MEASUREMENT_READY"
    summary["decision"] = {
        "classification": classification,
        "comparisons": comparisons,
        "full_r2_solve_executed": False,
        "promotion_authorized": False,
        "note": "Zero-step A/B ranks memory impact only. Any production promotion still requires physical R1 parity/non-regression.",
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue224-c1-memory-results"))
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
