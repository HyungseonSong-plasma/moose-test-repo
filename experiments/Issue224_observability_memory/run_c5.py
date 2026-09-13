#!/usr/bin/env python3
"""Issue #224 C5: R2 observer-family INITIAL-memory discriminator.

C4 showed that deferring all 146 passive INITIAL Postprocessors removes the
~1.08 GiB R2 setup-to-observer high-water. C5 attributes that execution-path
memory across four pre-registered observer families without executing a
physical timestep or linear solve.
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
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.performance.collection import parse_problem_identity
from physics_harness.adapters.moose.performance.profile import live_memory_samples
from physics_harness.execution.cases import stage_case, validate_case_references

DT_S = w5.BASELINE_DT_S
END_TIME_S = w5.END_TIME_S
SOLVED_HEAVY = ("O2s", "O2p", "O", "Om", "Op", "Os")

TYPE_COUNTS = {
    "SideFVFluxBCIntegral": 44,
    "VolumetricFlowRate": 8,
    "AreaPostprocessor": 2,
    "SideAverageFunctorPostprocessor": 1,
    "SideDiffusiveFluxIntegral": 1,
    "ElementAverageFunctorPostprocessor": 45,
    "ADElementIntegralFunctorPostprocessor": 12,
    "ADElementExtremeFunctorValue": 27,
    "ScalePostprocessor": 4,
    "ElementExtremeValue": 2,
}
GROUPS = {
    "side_flux": {
        "SideFVFluxBCIntegral",
        "VolumetricFlowRate",
        "AreaPostprocessor",
        "SideAverageFunctorPostprocessor",
        "SideDiffusiveFluxIntegral",
    },
    "element_aggregate": {
        "ElementAverageFunctorPostprocessor",
        "ADElementIntegralFunctorPostprocessor",
    },
    "ad_extreme": {"ADElementExtremeFunctorValue"},
    "light_derived": {"ScalePostprocessor", "ElementExtremeValue"},
}
EXPECTED_GROUP_COUNTS = {
    name: sum(TYPE_COUNTS[typ] for typ in types)
    for name, types in GROUPS.items()
}
EXPECTED_TOTAL_POSTPROCESSORS = 153
EXPECTED_RECEIVERS = 7
EXPECTED_PASSIVE = 146

CASE_SPECS = (
    ("r2_production_before", "production"),
    ("r2_side_flux_deferred", "side_flux"),
    ("r2_element_aggregate_deferred", "element_aggregate"),
    ("r2_ad_extreme_deferred", "ad_extreme"),
    ("r2_light_derived_deferred", "light_derived"),
    ("r2_production_after", "production"),
)

CONTROL_ABS_MB = 32.0
CONTROL_REL = 0.03
MAJOR_ABS_MB = 256.0
MAJOR_REL = 0.20
SECONDARY_ABS_MB = 64.0
SECONDARY_REL = 0.05


class Issue224C5Error(RuntimeError):
    pass


def _observer_snapshot(text: str) -> dict[str, dict[str, str]]:
    snapshot: dict[str, dict[str, str]] = {}
    for path in c4_base._postprocessor_paths(text):
        typ = mp.get_parameter(text, path, "type")
        snapshot[path] = {
            "type": str(typ),
            "execute_on": mp.get_parameter(text, path, "execute_on") or "<default>",
        }
    return snapshot


def _defer_family(text: str, family: str) -> tuple[str, dict[str, Any]]:
    if family not in GROUPS:
        raise Issue224C5Error(f"unsupported observer family: {family}")

    before = _observer_snapshot(text)
    if len(before) != EXPECTED_TOTAL_POSTPROCESSORS:
        raise Issue224C5Error(
            f"expected {EXPECTED_TOTAL_POSTPROCESSORS} Postprocessors, found {len(before)}"
        )

    allowed = set(TYPE_COUNTS) | {"Receiver"}
    unknown = sorted(
        (path, row["type"])
        for path, row in before.items()
        if row["type"] not in allowed
    )
    if unknown:
        raise Issue224C5Error(f"unclassified Postprocessor types: {unknown}")

    observed_type_counts: dict[str, int] = {}
    receiver_count = 0
    for row in before.values():
        typ = row["type"]
        if typ == "Receiver":
            receiver_count += 1
        else:
            observed_type_counts[typ] = observed_type_counts.get(typ, 0) + 1

    if receiver_count != EXPECTED_RECEIVERS:
        raise Issue224C5Error(
            f"expected {EXPECTED_RECEIVERS} Receiver observers, found {receiver_count}"
        )
    if observed_type_counts != TYPE_COUNTS:
        raise Issue224C5Error(
            f"Postprocessor type-count drift: expected={TYPE_COUNTS}, observed={observed_type_counts}"
        )

    target_types = GROUPS[family]
    target_paths = sorted(
        path for path, row in before.items() if row["type"] in target_types
    )
    expected_count = EXPECTED_GROUP_COUNTS[family]
    if len(target_paths) != expected_count:
        raise Issue224C5Error(
            f"{family}: expected {expected_count} target observers, found {len(target_paths)}"
        )

    for path in target_paths:
        text = mp.upsert_parameter(text, path, "execute_on", "'TIMESTEP_END'")

    after = _observer_snapshot(text)
    changed_non_target: list[str] = []
    bad_target: list[str] = []
    for path, before_row in before.items():
        after_row = after[path]
        if path in target_paths:
            if after_row["execute_on"].strip("'\"") != "TIMESTEP_END":
                bad_target.append(path)
        elif after_row != before_row:
            changed_non_target.append(path)

    if changed_non_target:
        raise Issue224C5Error(
            f"{family}: non-target observer schedules changed: {changed_non_target}"
        )
    if bad_target:
        raise Issue224C5Error(
            f"{family}: target observer deferral failed: {bad_target}"
        )

    by_type = {
        typ: sum(1 for path in target_paths if before[path]["type"] == typ)
        for typ in sorted(target_types)
    }
    return text, {
        "family": family,
        "postprocessor_count": len(before),
        "receiver_preserved_count": receiver_count,
        "target_deferred_count": len(target_paths),
        "target_type_counts": by_type,
        "non_target_changed_count": 0,
        "target_paths": target_paths,
    }


def _build(branch: str) -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=DT_S, uniform_refine=2)
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "0")
    observer_meta: dict[str, Any] = {
        "family": "production",
        "postprocessor_count": len(c4_base._postprocessor_paths(text)),
        "receiver_preserved_count": EXPECTED_RECEIVERS,
        "target_deferred_count": 0,
        "target_type_counts": {},
        "non_target_changed_count": 0,
    }
    if branch != "production":
        text, observer_meta = _defer_family(text, branch)

    return text, {
        **meta,
        "issue": 224,
        "parent_issue": 222,
        "diagnostic": "C5_OBSERVER_FAMILY_INITIAL_MEMORY",
        "uniform_refine": 2,
        "observer_branch": branch,
        "num_steps": 0,
        "physical_timestep_executed": False,
        "observer_mutation": observer_meta,
        "production_promotion_claim": False,
    }


def _stage(case_dir: Path, *, branch: str) -> tuple[str, dict[str, Any]]:
    text, meta = _build(branch)
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
    branch: str,
    timeout: float,
) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    input_text, meta = _stage(case_dir, branch=branch)

    p2_log = logs / f"{name}_p2.log"
    p2 = s5r._p2(exe, case_dir, p2_log, timeout=timeout)
    item: dict[str, Any] = {
        "uniform_refine": 2,
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
    setup = c4_base._sample(samples, "Finished Setting Up")
    user_objects = c4_base._sample(samples, "Finished Computing User Objects")
    initial_setup = c4_base._sample(samples, "Finished Performing Initial Setup")
    peak = max(samples, key=lambda x: float(x["resident_mb"])) if samples else None
    setup_mb = c4_base._mb(setup)
    user_mb = c4_base._mb(user_objects) or c4_base._mb(initial_setup)
    peak_mb = c4_base._mb(peak)
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
                "peak_resident_mb": peak_mb,
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
        and peak_mb is not None
        and no_linear_solve
        and no_physical_step
        and item["guards"]["num_steps_is_zero"]
    )
    if not item["hard_pass"]:
        item["reason"] = "SETUP_ONLY_CONTRACT_FAIL"
    return item


def _metric(case: Mapping[str, Any], key: str) -> float | None:
    value = case.get("memory", {}).get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _control_drift(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    stable = True
    for key in ("setup_to_user_object_increment_mb", "peak_resident_mb"):
        a = _metric(before, key)
        b = _metric(after, key)
        if a is None or b is None:
            metrics[key] = {"stable": False, "reason": "missing metric"}
            stable = False
            continue
        absolute_mb = abs(a - b)
        denominator = max(min(a, b), 1.0)
        fraction = absolute_mb / denominator
        metric_stable = not (absolute_mb > CONTROL_ABS_MB and fraction > CONTROL_REL)
        metrics[key] = {
            "before_mb": a,
            "after_mb": b,
            "absolute_drift_mb": absolute_mb,
            "relative_drift": fraction,
            "stable": metric_stable,
        }
        stable = stable and metric_stable
    return {"stable": stable, "metrics": metrics}


def _conservative_delta(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    candidate: Mapping[str, Any],
    key: str,
) -> dict[str, float | None]:
    a = _metric(before, key)
    b = _metric(after, key)
    c = _metric(candidate, key)
    if a is None or b is None or c is None:
        return {
            "production_before_mb": a,
            "production_after_mb": b,
            "conservative_reference_mb": None,
            "candidate_mb": c,
            "reduction_mb": None,
            "reduction_fraction": None,
        }
    reference = min(a, b)
    reduction = reference - c
    return {
        "production_before_mb": a,
        "production_after_mb": b,
        "conservative_reference_mb": reference,
        "candidate_mb": c,
        "reduction_mb": reduction,
        "reduction_fraction": reduction / reference if reference else None,
    }


def _family_classification(comparison: Mapping[str, Any]) -> str:
    inc = comparison["setup_to_user_object_increment_mb"]
    peak = comparison["peak_resident_mb"]
    inc_reduction = inc.get("reduction_mb")
    inc_fraction = inc.get("reduction_fraction")
    peak_reduction = peak.get("reduction_mb")
    if not all(isinstance(v, (int, float)) for v in (inc_reduction, inc_fraction, peak_reduction)):
        return "UNRESOLVED"
    if (
        float(inc_reduction) >= MAJOR_ABS_MB
        or float(inc_fraction) >= MAJOR_REL
        or float(peak_reduction) >= MAJOR_ABS_MB
    ):
        return "MAJOR"
    if (
        float(inc_reduction) >= SECONDARY_ABS_MB
        or float(inc_fraction) >= SECONDARY_REL
        or float(peak_reduction) >= SECONDARY_ABS_MB
    ):
        return "SECONDARY"
    return "NEGLIGIBLE"


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def self_test() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    checks["family_partition_passive_count"] = sum(EXPECTED_GROUP_COUNTS.values()) == EXPECTED_PASSIVE
    checks["family_type_partition_unique"] = (
        set().union(*GROUPS.values()) == set(TYPE_COUNTS)
        and sum(len(types) for types in GROUPS.values()) == len(TYPE_COUNTS)
    )

    for name, branch in CASE_SPECS:
        text, meta = _build(branch)
        checks[f"{name}_num_steps_zero"] = mp.get_parameter(text, "Executioner", "num_steps") == "0"
        checks[f"{name}_mesh_level"] = mp.get_parameter(text, "Mesh", "uniform_refine") == "2"
        checks[f"{name}_dt_preserved"] = math.isclose(
            float(meta["timestep_s"]), DT_S, rel_tol=0.0, abs_tol=0.0
        )
        checks[f"{name}_end_time_preserved"] = math.isclose(
            float(meta["end_time_s"]), END_TIME_S, rel_tol=0.0, abs_tol=0.0
        )
        checks[f"{name}_rhie_chow_preserved"] = (
            mp.get_parameter(text, "GlobalParams", "velocity_interp_method") or ""
        ).strip() == "rc"
        checks[f"{name}_observer_count"] = (
            len(c4_base._postprocessor_paths(text)) == EXPECTED_TOTAL_POSTPROCESSORS
        )
        for species in SOLVED_HEAVY:
            checks[f"{name}_conservative_time_preserved:{species}"] = (
                mp.get_parameter(text, f"FVKernels/{species}_time", "type")
                == "PhysicsFVConservativeMassFractionTimeDerivative"
            )

        if branch == "production":
            checks[f"{name}_no_observer_deferred"] = (
                meta["observer_mutation"]["target_deferred_count"] == 0
            )
        else:
            mutation = meta["observer_mutation"]
            checks[f"{name}_family_count"] = (
                mutation["target_deferred_count"] == EXPECTED_GROUP_COUNTS[branch]
            )
            checks[f"{name}_receivers_preserved"] = (
                mutation["receiver_preserved_count"] == EXPECTED_RECEIVERS
            )
            checks[f"{name}_non_target_unchanged"] = (
                mutation["non_target_changed_count"] == 0
            )
            checks[f"{name}_type_counts"] = mutation["target_type_counts"] == {
                typ: TYPE_COUNTS[typ] for typ in sorted(GROUPS[branch])
            }

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue224C5Error(f"invalid physics-opt: {exe}")

    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue224C5Error(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 224,
        "parent_issue": 222,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": w5._sha256(exe),
        "diagnostic": "C5_OBSERVER_FAMILY_INITIAL_MEMORY",
        "physical_timesteps_authorized": 0,
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    for name, branch in CASE_SPECS:
        case = _execute(
            exe,
            out,
            name=name,
            branch=branch,
            timeout=args.timeout,
        )
        summary["cases"][name] = case
        _write(out, summary)
        if not case["hard_pass"]:
            summary["status"] = "ISSUE224_C5_HOLD"
            summary["decision"] = {
                "classification": "UNRESOLVED",
                "reason": f"setup-only contract failed for {name}",
                "full_r2_solve_executed": False,
                "promotion_authorized": False,
            }
            _write(out, summary)
            return 2

    before = summary["cases"]["r2_production_before"]
    after = summary["cases"]["r2_production_after"]
    drift = _control_drift(before, after)
    if not drift["stable"]:
        summary["status"] = "ISSUE224_C5_HOLD"
        summary["decision"] = {
            "classification": "UNRESOLVED_CONTROL_DRIFT",
            "production_control_drift": drift,
            "full_r2_solve_executed": False,
            "promotion_authorized": False,
        }
        _write(out, summary)
        return 2

    comparisons: dict[str, Any] = {}
    family_classes: dict[str, str] = {}
    for family in GROUPS:
        candidate = summary["cases"][f"r2_{family}_deferred"]
        comparison = {
            key: _conservative_delta(before, after, candidate, key)
            for key in (
                "setup_mb",
                "post_user_object_mb",
                "setup_to_user_object_increment_mb",
                "peak_resident_mb",
            )
        }
        comparisons[family] = comparison
        family_classes[family] = _family_classification(comparison)

    majors = sorted(name for name, cls in family_classes.items() if cls == "MAJOR")
    secondaries = sorted(name for name, cls in family_classes.items() if cls == "SECONDARY")
    classification = (
        "OBSERVER_FAMILY_MEMORY_ATTRIBUTED"
        if majors
        else "NO_SINGLE_OBSERVER_FAMILY_DOMINANT"
    )

    summary["status"] = "ISSUE224_C5_ATTRIBUTION_READY"
    summary["decision"] = {
        "classification": classification,
        "production_control_drift": drift,
        "family_classification": family_classes,
        "major_families": majors,
        "secondary_families": secondaries,
        "comparisons": comparisons,
        "family_reductions_are_additive": False,
        "full_r2_solve_executed": False,
        "promotion_authorized": False,
        "next_action": (
            "Split the MAJOR observer family or families by exact Postprocessor type/ownership."
            if majors
            else "Investigate cross-family shared functor/AD evaluation and allocator high-water."
        ),
    }
    _write(out, summary)
    print((out / "summary.json").read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("issue224-c5-observer-family-memory-results"),
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
