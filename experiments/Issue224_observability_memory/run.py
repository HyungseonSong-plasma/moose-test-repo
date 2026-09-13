#!/usr/bin/env python3
"""Issue #224 C3: setup-only INITIAL observability memory discriminator.

The diagnostic compares the exact W5 production construction against a branch
that suppresses INITIAL execution of passive Postprocessor observers only. It
executes zero physical timesteps and no linear solve. Governing equations,
materials, kernels, BCs, variables, mesh, timestep, solver settings, and
conservative heavy-species accumulation remain unchanged.
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
from physics_harness.adapters.moose.input import MooseInput
from physics_harness.adapters.moose.performance.collection import parse_problem_identity
from physics_harness.adapters.moose.performance.profile import live_memory_samples
from physics_harness.execution.cases import stage_case, validate_case_references

DT_S = w5.BASELINE_DT_S
END_TIME_S = w5.END_TIME_S
SOLVED_HEAVY = ("O2s", "O2p", "O", "Om", "Op", "Os")
PASSIVE_TYPES = {
    "AreaPostprocessor",
    "VolumetricFlowRate",
    "SideAverageFunctorPostprocessor",
    "ElementAverageFunctorPostprocessor",
    "ADElementExtremeFunctorValue",
    "ADElementIntegralFunctorPostprocessor",
    "SideFVFluxBCIntegral",
    "ScalePostprocessor",
    "ElementExtremeValue",
    "SideDiffusiveFluxIntegral",
}
EXPECTED_PASSIVE_COUNT = 146
CASE_SPECS = (
    ("r1_production", 1, "production"),
    ("r1_observers_deferred", 1, "observers_deferred"),
    ("r2_production", 2, "production"),
    ("r2_observers_deferred", 2, "observers_deferred"),
)


class Issue224C3Error(RuntimeError):
    pass


def _postprocessor_paths(text: str) -> list[str]:
    doc = MooseInput(text)
    return sorted(
        block.path
        for block in doc.blocks
        if block.path.startswith("Postprocessors/") and block.path.count("/") == 1
    )


def _defer_passive_observers(text: str) -> tuple[str, dict[str, Any]]:
    paths = _postprocessor_paths(text)
    passive: list[dict[str, str]] = []
    receivers: list[str] = []
    unknown: list[dict[str, str | None]] = []

    for path in paths:
        typ = mp.get_parameter(text, path, "type")
        if typ == "Receiver":
            receivers.append(path)
            continue
        if typ not in PASSIVE_TYPES:
            unknown.append({"path": path, "type": typ})
            continue
        old = mp.get_parameter(text, path, "execute_on")
        text = mp.upsert_parameter(text, path, "execute_on", "'TIMESTEP_END'")
        passive.append({"path": path, "type": str(typ), "old_execute_on": old or "<default>"})

    if unknown:
        raise Issue224C3Error(f"unclassified Postprocessor types: {unknown}")
    if len(passive) != EXPECTED_PASSIVE_COUNT:
        raise Issue224C3Error(
            f"expected {EXPECTED_PASSIVE_COUNT} passive observers, found {len(passive)}; "
            f"receivers={len(receivers)}, total={len(paths)}"
        )

    return text, {
        "postprocessor_count": len(paths),
        "passive_deferred_count": len(passive),
        "receiver_preserved_count": len(receivers),
        "receivers": receivers,
        "passive": passive,
    }


def _build(level: int, branch: str) -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=level)
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "0")
    observer_meta: dict[str, Any] = {
        "postprocessor_count": len(_postprocessor_paths(text)),
        "passive_deferred_count": 0,
        "receiver_preserved_count": 0,
    }
    if branch == "observers_deferred":
        text, observer_meta = _defer_passive_observers(text)
    elif branch != "production":
        raise Issue224C3Error(f"unsupported branch {branch}")

    return text, {
        **meta,
        "issue": 224,
        "parent_issue": 222,
        "diagnostic": "C3_INITIAL_OBSERVABILITY_SETUP_MEMORY",
        "uniform_refine": level,
        "observer_branch": branch,
        "num_steps": 0,
        "physical_timestep_executed": False,
        "observer_mutation": observer_meta,
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
        return {"production_mb": None, "candidate_mb": None, "reduction_mb": None, "reduction_fraction": None}
    reduction = float(a) - float(b)
    return {
        "production_mb": float(a),
        "candidate_mb": float(b),
        "reduction_mb": reduction,
        "reduction_fraction": reduction / float(a) if float(a) else None,
    }


def _classify(prod: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    p_inc = prod.get("memory", {}).get("setup_to_user_object_increment_mb")
    c_inc = candidate.get("memory", {}).get("setup_to_user_object_increment_mb")
    p_peak = prod.get("memory", {}).get("peak_resident_mb")
    c_peak = candidate.get("memory", {}).get("peak_resident_mb")
    if not all(isinstance(v, (int, float)) for v in (p_inc, c_inc, p_peak, c_peak)):
        return "UNRESOLVED"
    inc_reduction = float(p_inc) - float(c_inc)
    peak_reduction = float(p_peak) - float(c_peak)
    inc_fraction = inc_reduction / float(p_inc) if float(p_inc) else 0.0
    if inc_reduction >= 256.0 or inc_fraction >= 0.20 or peak_reduction >= 256.0:
        return "INITIAL_OBSERVABILITY_MATERIAL_MEMORY_CONTRIBUTOR"
    return "INITIAL_OBSERVABILITY_NOT_DOMINANT"


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for name, level, branch in CASE_SPECS:
        text, meta = _build(level, branch)
        checks[f"{name}_num_steps_zero"] = mp.get_parameter(text, "Executioner", "num_steps") == "0"
        checks[f"{name}_mesh_level"] = mp.get_parameter(text, "Mesh", "uniform_refine") == str(level)
        checks[f"{name}_dt_preserved"] = math.isclose(float(meta["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0)
        checks[f"{name}_end_time_preserved"] = math.isclose(float(meta["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0)
        checks[f"{name}_rhie_chow_preserved"] = (mp.get_parameter(text, "GlobalParams", "velocity_interp_method") or "").strip() == "rc"
        for species in SOLVED_HEAVY:
            checks[f"{name}_conservative_time_preserved:{species}"] = (
                mp.get_parameter(text, f"FVKernels/{species}_time", "type")
                == "PhysicsFVConservativeMassFractionTimeDerivative"
            )
        if branch == "production":
            checks[f"{name}_observer_count"] = len(_postprocessor_paths(text)) == 153
        else:
            checks[f"{name}_observer_count"] = meta["observer_mutation"]["postprocessor_count"] == 153
            checks[f"{name}_passive_count"] = meta["observer_mutation"]["passive_deferred_count"] == EXPECTED_PASSIVE_COUNT
            checks[f"{name}_receivers_preserved"] = meta["observer_mutation"]["receiver_preserved_count"] == 7
            for row in meta["observer_mutation"]["passive"]:
                checks[f"{name}_deferred:{row['path']}"] = (
                    (mp.get_parameter(text, row["path"], "execute_on") or "").strip("'\"") == "TIMESTEP_END"
                )
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
        "diagnostic": "C3_INITIAL_OBSERVABILITY_SETUP_MEMORY",
        "physical_timesteps_authorized": 0,
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    for name, level, branch in CASE_SPECS:
        case = _execute(exe, out, name=name, level=level, branch=branch, timeout=args.timeout)
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
    for level in ("r1", "r2"):
        prod = summary["cases"][f"{level}_production"]
        candidate = summary["cases"][f"{level}_observers_deferred"]
        comparisons[level] = {
            key: _delta(prod, candidate, key)
            for key in ("setup_mb", "post_user_object_mb", "setup_to_user_object_increment_mb", "peak_resident_mb")
        }
    classification = _classify(
        summary["cases"]["r2_production"],
        summary["cases"]["r2_observers_deferred"],
    )
    summary["status"] = "ISSUE224_C3_ATTRIBUTION_READY"
    summary["decision"] = {
        "classification": classification,
        "comparisons": comparisons,
        "full_r2_solve_executed": False,
        "promotion_authorized": False,
        "next_action": (
            "Split passive observers by class/ownership and identify production-removable diagnostics."
            if classification == "INITIAL_OBSERVABILITY_MATERIAL_MEMORY_CONTRIBUTOR"
            else "Continue attribution with matrix/vector allocation and AD dependency width."
        ),
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("issue224-c3-observability-memory-results"))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 2
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
