#!/usr/bin/env python3
"""Issue #224 C6: split the C5R MAJOR element-aggregate family by exact type.

C5R established that deferring INITIAL execution of the 57-object
``element_aggregate`` family removes about 1 GiB of R2 zero-step OS max RSS,
while the other observer families are negligible. C6 separates that family
into its two exact Postprocessor types and retains an all-element-aggregate
positive control. Every case is R2, num_steps=0, fresh-process, and measured
with GNU /usr/bin/time -v. No physical timestep, linear solve, or production
promotion is authorized.
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
from experiments.Issue224_observability_memory import run as c4_base
from experiments.Issue224_observability_memory import run_c5 as c5
from experiments.Issue224_observability_memory import run_c5r as c5r
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.performance.collection import parse_problem_identity
from physics_harness.adapters.moose.performance.profile import live_memory_samples
from physics_harness.execution.cases import stage_case, validate_case_references

VARIANTS = {
    "element_average": {"ElementAverageFunctorPostprocessor": 45},
    "ad_element_integral": {"ADElementIntegralFunctorPostprocessor": 12},
    "element_aggregate_all": {
        "ElementAverageFunctorPostprocessor": 45,
        "ADElementIntegralFunctorPostprocessor": 12,
    },
}
CASE_SPECS = (
    ("r2_production_before", "production"),
    ("r2_element_average_deferred", "element_average"),
    ("r2_ad_element_integral_deferred", "ad_element_integral"),
    ("r2_element_aggregate_all_deferred", "element_aggregate_all"),
    ("r2_production_after", "production"),
)


class Issue224C6Error(RuntimeError):
    pass


def _validate_inventory(text: str) -> tuple[dict[str, dict[str, str]], int, dict[str, int]]:
    snapshot = c5._observer_snapshot(text)
    if len(snapshot) != c5.EXPECTED_TOTAL_POSTPROCESSORS:
        raise Issue224C6Error(
            f"expected {c5.EXPECTED_TOTAL_POSTPROCESSORS} Postprocessors, found {len(snapshot)}"
        )

    allowed = set(c5.TYPE_COUNTS) | {"Receiver"}
    unknown = sorted(
        (path, row["type"])
        for path, row in snapshot.items()
        if row["type"] not in allowed
    )
    if unknown:
        raise Issue224C6Error(f"unclassified Postprocessor types: {unknown}")

    receiver_count = sum(1 for row in snapshot.values() if row["type"] == "Receiver")
    observed: dict[str, int] = {}
    for row in snapshot.values():
        typ = row["type"]
        if typ != "Receiver":
            observed[typ] = observed.get(typ, 0) + 1

    if receiver_count != c5.EXPECTED_RECEIVERS:
        raise Issue224C6Error(
            f"expected {c5.EXPECTED_RECEIVERS} Receivers, found {receiver_count}"
        )
    if observed != c5.TYPE_COUNTS:
        raise Issue224C6Error(
            f"Postprocessor type-count drift: expected={c5.TYPE_COUNTS}, observed={observed}"
        )
    return snapshot, receiver_count, observed


def _defer_variant(text: str, variant: str) -> tuple[str, dict[str, Any]]:
    if variant not in VARIANTS:
        raise Issue224C6Error(f"unsupported C6 variant: {variant}")

    before, receiver_count, _ = _validate_inventory(text)
    target_counts = VARIANTS[variant]
    target_types = set(target_counts)
    target_paths = sorted(
        path for path, row in before.items() if row["type"] in target_types
    )
    expected_total = sum(target_counts.values())
    if len(target_paths) != expected_total:
        raise Issue224C6Error(
            f"{variant}: expected {expected_total} targets, found {len(target_paths)}"
        )
    observed_targets = {
        typ: sum(1 for path in target_paths if before[path]["type"] == typ)
        for typ in sorted(target_types)
    }
    if observed_targets != target_counts:
        raise Issue224C6Error(
            f"{variant}: target count drift: expected={target_counts}, observed={observed_targets}"
        )

    for path in target_paths:
        text = mp.upsert_parameter(text, path, "execute_on", "'TIMESTEP_END'")

    after = c5._observer_snapshot(text)
    changed_non_target: list[str] = []
    bad_target: list[str] = []
    target_set = set(target_paths)
    for path, before_row in before.items():
        after_row = after[path]
        if path in target_set:
            if after_row["execute_on"].strip("'\"") != "TIMESTEP_END":
                bad_target.append(path)
        elif after_row != before_row:
            changed_non_target.append(path)

    if changed_non_target:
        raise Issue224C6Error(
            f"{variant}: non-target observer schedules changed: {changed_non_target}"
        )
    if bad_target:
        raise Issue224C6Error(f"{variant}: target deferral failed: {bad_target}")

    return text, {
        "variant": variant,
        "postprocessor_count": len(before),
        "receiver_preserved_count": receiver_count,
        "target_deferred_count": len(target_paths),
        "target_type_counts": observed_targets,
        "non_target_changed_count": 0,
        "target_paths": target_paths,
    }


def _build(variant: str) -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=w5.BASELINE_DT_S, uniform_refine=2)
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "0")
    _validate_inventory(text)
    observer_meta: dict[str, Any] = {
        "variant": "production",
        "postprocessor_count": c5.EXPECTED_TOTAL_POSTPROCESSORS,
        "receiver_preserved_count": c5.EXPECTED_RECEIVERS,
        "target_deferred_count": 0,
        "target_type_counts": {},
        "non_target_changed_count": 0,
    }
    if variant != "production":
        text, observer_meta = _defer_variant(text, variant)

    return text, {
        **meta,
        "issue": 224,
        "parent_issue": 222,
        "diagnostic": "C6_ELEMENT_AGGREGATE_TYPE_OS_RSS",
        "uniform_refine": 2,
        "observer_variant": variant,
        "num_steps": 0,
        "physical_timestep_executed": False,
        "observer_mutation": observer_meta,
        "production_promotion_claim": False,
    }


def _stage(case_dir: Path, *, variant: str) -> tuple[str, dict[str, Any]]:
    text, meta = _build(variant)
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


def _execute(
    exe: Path,
    out: Path,
    *,
    name: str,
    variant: str,
    timeout: float,
) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    input_text, meta = _stage(case_dir, variant=variant)

    p2_log = logs / f"{name}_p2.log"
    p2 = s5r._p2(exe, case_dir, p2_log, timeout=timeout)
    item: dict[str, Any] = {
        "uniform_refine": 2,
        "variant": variant,
        "meta": meta,
        "p2": p2,
        "hard_pass": False,
    }
    if p2.get("returncode") != 0:
        item["reason"] = "P2_FAIL"
        return item

    runtime_log = logs / f"{name}_runtime.log"
    time_log = logs / f"{name}_time_v.log"
    runtime = c5r._runtime_with_os_rss(
        exe, case_dir, runtime_log, time_log, timeout=timeout
    )
    log_text = runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""
    samples = live_memory_samples(runtime_log)
    setup = c4_base._sample(samples, "Finished Setting Up")
    user_objects = c4_base._sample(samples, "Finished Computing User Objects")
    initial_setup = c4_base._sample(samples, "Finished Performing Initial Setup")
    profiler_peak = max(samples, key=lambda x: float(x["resident_mb"])) if samples else None
    setup_mb = c4_base._mb(setup)
    post_initial_mb = c4_base._mb(user_objects) or c4_base._mb(initial_setup)
    profiler_peak_mb = c4_base._mb(profiler_peak)
    os_peak_mib = runtime.get("os_max_rss_mib")
    no_linear_solve = "Linear solve" not in log_text and "SNES Function norm" not in log_text
    no_physical_step = "Time Step 1" not in log_text

    item.update(
        {
            "runtime": runtime,
            "problem": parse_problem_identity(log_text),
            "memory": {
                "setup_mb": setup_mb,
                "post_user_object_mb": post_initial_mb,
                "setup_to_user_object_increment_mb": (
                    post_initial_mb - setup_mb
                    if setup_mb is not None and post_initial_mb is not None
                    else None
                ),
                "profiler_peak_resident_mb": profiler_peak_mb,
                "os_max_rss_mib": os_peak_mib,
                "samples_observed": len(samples),
                "authoritative_peak_metric": "os_max_rss_mib",
                "profiler_phase_metric_optional": True,
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
        and isinstance(os_peak_mib, (int, float))
        and math.isfinite(float(os_peak_mib))
        and float(os_peak_mib) > 0.0
        and no_linear_solve
        and no_physical_step
        and item["guards"]["num_steps_is_zero"]
    )
    if not item["hard_pass"]:
        item["reason"] = "SETUP_ONLY_OS_RSS_CONTRACT_FAIL"
    return item


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _type_decision(classes: Mapping[str, str], positive_control: str) -> str:
    if positive_control != "MAJOR":
        return "C6_POSITIVE_CONTROL_NOT_REPRODUCED"
    majors = sorted(name for name, cls in classes.items() if cls == "MAJOR")
    if majors == ["element_average"]:
        return "ELEMENT_AVERAGE_FUNCTOR_DOMINANT"
    if majors == ["ad_element_integral"]:
        return "AD_ELEMENT_INTEGRAL_DOMINANT"
    if len(majors) == 2:
        return "BOTH_ELEMENT_AGGREGATE_TYPES_MAJOR"
    return "JOINT_OR_CROSS_TYPE_INTERACTION"


def self_test() -> dict[str, Any]:
    base = c5r.self_test()
    checks: dict[str, bool] = {"c5r_base_self_test": base.get("status") == "PASS"}
    production, _ = _build("production")
    snapshot, receivers, observed = _validate_inventory(production)
    checks["production_inventory_exact"] = (
        len(snapshot) == c5.EXPECTED_TOTAL_POSTPROCESSORS
        and receivers == c5.EXPECTED_RECEIVERS
        and observed == c5.TYPE_COUNTS
    )
    expected_totals = {
        "element_average": 45,
        "ad_element_integral": 12,
        "element_aggregate_all": 57,
    }
    for variant, expected in expected_totals.items():
        _, meta = _defer_variant(production, variant)
        checks[f"{variant}_target_count"] = meta["target_deferred_count"] == expected
        checks[f"{variant}_non_target_unchanged"] = meta["non_target_changed_count"] == 0
    checks["synthetic_element_average_dominant"] = (
        _type_decision(
            {"element_average": "MAJOR", "ad_element_integral": "NEGLIGIBLE"},
            "MAJOR",
        )
        == "ELEMENT_AVERAGE_FUNCTOR_DOMINANT"
    )
    checks["synthetic_interaction_path"] = (
        _type_decision(
            {"element_average": "NEGLIGIBLE", "ad_element_integral": "NEGLIGIBLE"},
            "MAJOR",
        )
        == "JOINT_OR_CROSS_TYPE_INTERACTION"
    )
    failed = sorted(key for key, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "base_c5r": base,
    }


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue224C6Error(f"invalid physics-opt: {exe}")

    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue224C6Error(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 224,
        "parent_issue": 222,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": w5._sha256(exe),
        "diagnostic": "C6_ELEMENT_AGGREGATE_TYPE_OS_RSS",
        "physical_timesteps_authorized": 0,
        "authoritative_peak_metric": "GNU_time_v_Maximum_resident_set_size",
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    for name, variant in CASE_SPECS:
        case = _execute(
            exe,
            out,
            name=name,
            variant=variant,
            timeout=args.timeout,
        )
        summary["cases"][name] = case
        _write(out, summary)
        if not case["hard_pass"]:
            summary["status"] = "ISSUE224_C6_HOLD"
            summary["decision"] = {
                "classification": "UNRESOLVED",
                "reason": f"setup-only OS RSS contract failed for {name}",
                "full_r2_solve_executed": False,
                "promotion_authorized": False,
            }
            _write(out, summary)
            return 2

    before = summary["cases"]["r2_production_before"]
    after = summary["cases"]["r2_production_after"]
    drift = c5r._control_drift(before, after)
    if not drift["stable"]:
        summary["status"] = "ISSUE224_C6_HOLD"
        summary["decision"] = {
            "classification": "UNRESOLVED_CONTROL_DRIFT",
            "production_control_drift": drift,
            "full_r2_solve_executed": False,
            "promotion_authorized": False,
        }
        _write(out, summary)
        return 2

    candidate_names = {
        "element_average": "r2_element_average_deferred",
        "ad_element_integral": "r2_ad_element_integral_deferred",
        "element_aggregate_all": "r2_element_aggregate_all_deferred",
    }
    comparisons: dict[str, Any] = {}
    classes: dict[str, str] = {}
    for key, case_name in candidate_names.items():
        comparison = c5r._comparison(before, after, summary["cases"][case_name])
        comparisons[key] = comparison
        classes[key] = c5r._family_classification(comparison)

    positive_control = classes["element_aggregate_all"]
    type_classes = {
        "element_average": classes["element_average"],
        "ad_element_integral": classes["ad_element_integral"],
    }
    classification = _type_decision(type_classes, positive_control)

    individual_reductions = [
        comparisons[name].get("reduction_mib")
        for name in ("element_average", "ad_element_integral")
    ]
    all_reduction = comparisons["element_aggregate_all"].get("reduction_mib")
    interaction_residual = None
    if all(isinstance(x, (int, float)) for x in individual_reductions) and isinstance(
        all_reduction, (int, float)
    ):
        interaction_residual = float(all_reduction) - sum(float(x) for x in individual_reductions)

    summary["status"] = "ISSUE224_C6_TYPE_ATTRIBUTION_READY"
    summary["decision"] = {
        "classification": classification,
        "production_control_drift": drift,
        "type_classification": type_classes,
        "positive_control_classification": positive_control,
        "major_types": sorted(name for name, cls in type_classes.items() if cls == "MAJOR"),
        "secondary_types": sorted(name for name, cls in type_classes.items() if cls == "SECONDARY"),
        "comparisons": comparisons,
        "interaction_residual_mib": interaction_residual,
        "individual_reductions_are_additive": False,
        "full_r2_solve_executed": False,
        "promotion_authorized": False,
        "measurement_scope": "R2 zero-step fresh-process OS max RSS",
        "next_action": (
            "Inspect exact ElementAverageFunctorPostprocessor ownership/evaluated functors."
            if classification == "ELEMENT_AVERAGE_FUNCTOR_DOMINANT"
            else "Inspect exact ADElementIntegralFunctorPostprocessor ownership/evaluated functors."
            if classification == "AD_ELEMENT_INTEGRAL_DOMINANT"
            else "Resolve per-type overlap/interaction before any production scheduling change."
        ),
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0 if positive_control == "MAJOR" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("issue224-c6-element-aggregate-type-rss-results"),
    )
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
