#!/usr/bin/env python3
"""Issue #224 C5R: OS-level RSS repair for the C5 observer-family discriminator.

C5 localized a harness weakness: some successful zero-step cases do not emit a
post-INITIAL MOOSE profiler checkpoint, so profiler samples alone cannot certify
process peak RSS. C5R preserves the exact C5 case construction and thresholds,
but measures every runtime in a fresh process through GNU /usr/bin/time -v and
uses its Maximum resident set size as the authoritative cross-case peak metric.

MOOSE profiler samples are retained as phase evidence only. No physical timestep
or linear solve is authorized and no production promotion claim is made.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue224_observability_memory import run as c4_base
from experiments.Issue224_observability_memory import run_c5 as c5
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.performance.collection import parse_problem_identity
from physics_harness.adapters.moose.performance.profile import live_memory_samples
from physics_harness.execution.runtime import run_command

TIME_BIN = Path("/usr/bin/time")
TIME_MAX_RSS_PREFIX = "Maximum resident set size (kbytes):"


class Issue224C5RError(RuntimeError):
    pass


def _parse_time_max_rss_mib(text: str) -> float | None:
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(TIME_MAX_RSS_PREFIX):
            try:
                kib = float(line.split(":", 1)[1].strip())
            except ValueError:
                return None
            if not math.isfinite(kib) or kib < 0.0:
                return None
            return kib / 1024.0
    return None


def _runtime_with_os_rss(
    exe: Path,
    case_dir: Path,
    runtime_log: Path,
    time_log: Path,
    *,
    timeout: float,
) -> dict[str, Any]:
    result = run_command(
        [
            str(TIME_BIN),
            "-v",
            "-o",
            str(time_log.resolve()),
            str(exe),
            "-i",
            "input.i",
            "-snes_monitor",
            "-snes_converged_reason",
            "-ksp_converged_reason",
        ],
        cwd=case_dir,
        log_path=runtime_log,
        timeout_seconds=timeout,
    )
    log_text = runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""
    time_text = time_log.read_text(errors="replace") if time_log.is_file() else ""
    return {
        "returncode": result.returncode,
        "wall_seconds": result.wall_seconds,
        "timed_out": result.timed_out,
        "runtime_facts": s5r._runtime_log_facts(
            log_text, returncode=result.returncode, timed_out=result.timed_out
        ),
        "log": str(runtime_log),
        "time_log": str(time_log),
        "os_max_rss_mib": _parse_time_max_rss_mib(time_text),
    }


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
    input_text, meta = c5._stage(case_dir, branch=branch)

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
    time_log = logs / f"{name}_time_v.log"
    runtime = _runtime_with_os_rss(
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


def _os_peak(case: Mapping[str, Any]) -> float | None:
    value = case.get("memory", {}).get("os_max_rss_mib")
    return float(value) if isinstance(value, (int, float)) else None


def _control_drift(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    a = _os_peak(before)
    b = _os_peak(after)
    if a is None or b is None:
        return {"stable": False, "reason": "missing OS max RSS control metric"}
    absolute_mib = abs(a - b)
    denominator = max(min(a, b), 1.0)
    fraction = absolute_mib / denominator
    stable = not (absolute_mib > c5.CONTROL_ABS_MB and fraction > c5.CONTROL_REL)
    return {
        "stable": stable,
        "metric": "os_max_rss_mib",
        "before_mib": a,
        "after_mib": b,
        "absolute_drift_mib": absolute_mib,
        "relative_drift": fraction,
        "limits": {
            "absolute_mib": c5.CONTROL_ABS_MB,
            "relative": c5.CONTROL_REL,
        },
    }


def _comparison(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, float | None]:
    a = _os_peak(before)
    b = _os_peak(after)
    c = _os_peak(candidate)
    if a is None or b is None or c is None:
        return {
            "production_before_mib": a,
            "production_after_mib": b,
            "conservative_reference_mib": None,
            "candidate_mib": c,
            "reduction_mib": None,
            "reduction_fraction": None,
        }
    reference = min(a, b)
    reduction = reference - c
    return {
        "production_before_mib": a,
        "production_after_mib": b,
        "conservative_reference_mib": reference,
        "candidate_mib": c,
        "reduction_mib": reduction,
        "reduction_fraction": reduction / reference if reference else None,
    }


def _family_classification(comparison: Mapping[str, Any]) -> str:
    reduction = comparison.get("reduction_mib")
    fraction = comparison.get("reduction_fraction")
    if not isinstance(reduction, (int, float)) or not isinstance(fraction, (int, float)):
        return "UNRESOLVED"
    if float(reduction) >= c5.MAJOR_ABS_MB or float(fraction) >= c5.MAJOR_REL:
        return "MAJOR"
    if float(reduction) >= c5.SECONDARY_ABS_MB or float(fraction) >= c5.SECONDARY_REL:
        return "SECONDARY"
    return "NEGLIGIBLE"


def _write(out: Path, summary: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def self_test() -> dict[str, Any]:
    base = c5.self_test()
    checks: dict[str, bool] = {
        "c5_base_self_test": base.get("status") == "PASS",
        "time_binary_exists": TIME_BIN.is_file(),
        "time_parser_2_mib": math.isclose(
            _parse_time_max_rss_mib(
                "Maximum resident set size (kbytes): 2048\n"
            )
            or -1.0,
            2.0,
            rel_tol=0.0,
            abs_tol=0.0,
        ),
        "time_parser_rejects_missing": _parse_time_max_rss_mib("Elapsed: 1.0\n") is None,
    }
    synthetic = {
        "production_before_mib": 1900.0,
        "production_after_mib": 1890.0,
        "conservative_reference_mib": 1890.0,
        "candidate_mib": 800.0,
        "reduction_mib": 1090.0,
        "reduction_fraction": 1090.0 / 1890.0,
    }
    checks["os_peak_only_major_classification"] = _family_classification(synthetic) == "MAJOR"
    failed = sorted(key for key, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "base_c5": base,
    }


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue224C5RError(f"invalid physics-opt: {exe}")

    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue224C5RError(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 224,
        "parent_issue": 222,
        "repository_head": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": c5.w5._sha256(exe),
        "diagnostic": "C5R_OBSERVER_FAMILY_OS_RSS",
        "repair_of": "C5_OBSERVER_FAMILY_INITIAL_MEMORY",
        "physical_timesteps_authorized": 0,
        "authoritative_peak_metric": "GNU_time_v_Maximum_resident_set_size",
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    for name, branch in c5.CASE_SPECS:
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
            summary["status"] = "ISSUE224_C5R_HOLD"
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
    drift = _control_drift(before, after)
    if not drift["stable"]:
        summary["status"] = "ISSUE224_C5R_HOLD"
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
    for family in c5.GROUPS:
        candidate = summary["cases"][f"r2_{family}_deferred"]
        comparison = _comparison(before, after, candidate)
        comparisons[family] = comparison
        family_classes[family] = _family_classification(comparison)

    majors = sorted(name for name, cls in family_classes.items() if cls == "MAJOR")
    secondaries = sorted(name for name, cls in family_classes.items() if cls == "SECONDARY")
    classification = (
        "OBSERVER_FAMILY_MEMORY_ATTRIBUTED"
        if majors
        else "NO_SINGLE_OBSERVER_FAMILY_DOMINANT"
    )

    summary["status"] = "ISSUE224_C5R_RSS_ATTRIBUTION_READY"
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
        "measurement_scope": (
            "R2 zero-step fresh-process OS max RSS; MOOSE profiler phase samples are optional evidence"
        ),
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
        default=Path("issue224-c5r-observer-family-rss-results"),
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
