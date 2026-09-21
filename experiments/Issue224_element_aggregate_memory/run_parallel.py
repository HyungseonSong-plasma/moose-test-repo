#!/usr/bin/env python3
"""Issue #224 parallel zero-step hypothesis runner.

Each invocation evaluates exactly one restricted diagnostic specification from
one immutable repository SHA. Candidate mutations are constructed only in the
runner workspace; no repository state is modified. Every hypothesis carries
same-runner production-before/after controls and the accepted all-57-deferred
low-memory control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Mapping

from experiments.Issue192_s5r_representative import run as s5r
from experiments.Issue216_w5_multistep_acceptance import run as w5
from experiments.Issue224_observability_memory import run as c4_base
from experiments.Issue224_observability_memory import run_c5 as c5
from experiments.Issue224_observability_memory import run_c5r as c5r
from experiments.Issue224_element_aggregate_memory import run_c6 as c6
from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.performance.collection import parse_problem_identity
from physics_harness.adapters.moose.performance.profile import live_memory_samples
from physics_harness.execution.cases import stage_case, validate_case_references

ALLOWED_MODES = {"keep_initial", "cell_average", "dependency_substitution"}
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,48}$")
FUNCTOR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")
ELEMENT_TYPES = {
    "ElementAverageFunctorPostprocessor",
    "ADElementIntegralFunctorPostprocessor",
}


class Issue224ParallelError(RuntimeError):
    pass


def _production() -> tuple[str, dict[str, Any]]:
    text, meta = w5._build_case(dt_s=w5.BASELINE_DT_S, uniform_refine=2)
    text = mp.upsert_parameter(text, "Executioner", "num_steps", "0")
    c6._validate_inventory(text)
    return text, meta


def _element_paths(text: str) -> list[str]:
    snapshot, _, _ = c6._validate_inventory(text)
    paths = sorted(path for path, row in snapshot.items() if row["type"] in ELEMENT_TYPES)
    if len(paths) != 57:
        raise Issue224ParallelError(f"expected 57 element-aggregate paths, found {len(paths)}")
    return paths


def _validate_path_list(
    spec: Mapping[str, Any], key: str, allowed: set[str], *, mode: str
) -> list[str]:
    value = spec.get(key)
    if not isinstance(value, list) or not value:
        raise Issue224ParallelError(f"{mode} requires non-empty {key}")
    if not all(isinstance(x, str) for x in value):
        raise Issue224ParallelError(f"{key} must contain strings")
    if len(set(value)) != len(value):
        raise Issue224ParallelError(f"{key} contains duplicates")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise Issue224ParallelError(f"{key} outside accepted 57-object family: {unknown}")
    return sorted(value)


def _validate_substitutions(
    spec: Mapping[str, Any], text: str, keep: set[str]
) -> list[dict[str, str]]:
    raw = spec.get("substitutions")
    if not isinstance(raw, list) or not raw:
        raise Issue224ParallelError(
            "dependency_substitution requires non-empty substitutions"
        )

    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    required = {"path", "expected_functor", "replacement_functor"}
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise Issue224ParallelError(f"substitution[{index}] must be an object")
        keys = set(item)
        if keys != required:
            raise Issue224ParallelError(
                f"substitution[{index}] keys must be exactly {sorted(required)}, got {sorted(keys)}"
            )
        path = item.get("path")
        expected = item.get("expected_functor")
        replacement = item.get("replacement_functor")
        if not isinstance(path, str) or path not in keep:
            raise Issue224ParallelError(
                f"substitution[{index}] path must be one of keep_paths: {path!r}"
            )
        if path in seen:
            raise Issue224ParallelError(f"duplicate substitution path: {path}")
        seen.add(path)
        for label, value in (("expected_functor", expected), ("replacement_functor", replacement)):
            if not isinstance(value, str) or not FUNCTOR_RE.fullmatch(value):
                raise Issue224ParallelError(
                    f"substitution[{index}] invalid {label}: {value!r}"
                )
        if expected == replacement:
            raise Issue224ParallelError(
                f"substitution[{index}] replacement must differ from expected functor"
            )
        current = mp.get_parameter(text, path, "functor")
        if current != expected:
            raise Issue224ParallelError(
                f"substitution[{index}] expected functor mismatch for {path}: "
                f"expected={expected!r}, production={current!r}"
            )
        normalized.append(
            {
                "path": path,
                "expected_functor": expected,
                "replacement_functor": replacement,
            }
        )
    return sorted(normalized, key=lambda row: row["path"])


def _validate_spec(spec: Mapping[str, Any], text: str) -> dict[str, Any]:
    sid = spec.get("id")
    mode = spec.get("mode")
    if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
        raise Issue224ParallelError(f"invalid experiment id: {sid!r}")
    if mode not in ALLOWED_MODES:
        raise Issue224ParallelError(f"unsupported mode: {mode!r}")

    allowed = set(_element_paths(text))
    out: dict[str, Any] = {"id": sid, "mode": mode}
    if mode == "keep_initial":
        extra = sorted(set(spec) - {"id", "mode", "keep_paths"})
        if extra:
            raise Issue224ParallelError(f"unsupported keys for keep_initial: {extra}")
        out["keep_paths"] = _validate_path_list(
            spec, "keep_paths", allowed, mode="keep_initial"
        )
    elif mode == "cell_average":
        extra = sorted(set(spec) - {"id", "mode", "target_paths"})
        if extra:
            raise Issue224ParallelError(f"unsupported keys for cell_average: {extra}")
        targets = spec.get("target_paths")
        if targets is None:
            targets = sorted(allowed)
            spec = {**spec, "target_paths": targets}
        out["target_paths"] = _validate_path_list(
            spec, "target_paths", allowed, mode="cell_average"
        )
    else:
        extra = sorted(set(spec) - {"id", "mode", "keep_paths", "substitutions"})
        if extra:
            raise Issue224ParallelError(
                f"unsupported keys for dependency_substitution: {extra}"
            )
        keep = _validate_path_list(
            spec, "keep_paths", allowed, mode="dependency_substitution"
        )
        out["keep_paths"] = keep
        out["substitutions"] = _validate_substitutions(spec, text, set(keep))
    return out


def _all_deferred(text: str) -> tuple[str, dict[str, Any]]:
    return c6._defer_variant(text, "element_aggregate_all")


def _defer_except(
    text: str,
    *,
    keep: set[str],
    before: Mapping[str, Mapping[str, str]],
    element_set: set[str],
) -> tuple[str, list[str]]:
    deferred = sorted(element_set - keep)
    for path in deferred:
        text = mp.upsert_parameter(text, path, "execute_on", "'TIMESTEP_END'")
    after = c5._observer_snapshot(text)
    changed_non_target = [
        path for path in before if path not in element_set and after[path] != before[path]
    ]
    bad_deferred = [
        path
        for path in deferred
        if after[path]["execute_on"].strip("'\"") != "TIMESTEP_END"
    ]
    bad_keep = [path for path in keep if after[path] != before[path]]
    if changed_non_target or bad_deferred or bad_keep:
        raise Issue224ParallelError(
            f"keep schedule mutation contract failed: non_target={changed_non_target}, "
            f"bad_deferred={bad_deferred}, bad_keep={bad_keep}"
        )
    return text, deferred


def _candidate(text: str, spec: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    spec = _validate_spec(spec, text)
    before = c5._observer_snapshot(text)
    element_paths = _element_paths(text)
    element_set = set(element_paths)

    if spec["mode"] in {"keep_initial", "dependency_substitution"}:
        keep = set(spec["keep_paths"])
        original_functors = {
            path: mp.get_parameter(text, path, "functor") for path in element_paths
        }
        text, deferred = _defer_except(
            text, keep=keep, before=before, element_set=element_set
        )

        if spec["mode"] == "keep_initial":
            return text, {
                "spec": spec,
                "target_family_count": 57,
                "kept_initial_count": len(keep),
                "deferred_count": len(deferred),
                "non_target_changed_count": 0,
            }

        applied: list[dict[str, str]] = []
        for row in spec["substitutions"]:
            path = row["path"]
            current = mp.get_parameter(text, path, "functor")
            if current != row["expected_functor"]:
                raise Issue224ParallelError(
                    f"pre-substitution functor drift for {path}: "
                    f"expected={row['expected_functor']!r}, current={current!r}"
                )
            text = mp.upsert_parameter(
                text, path, "functor", row["replacement_functor"]
            )
            actual = mp.get_parameter(text, path, "functor")
            if actual != row["replacement_functor"]:
                raise Issue224ParallelError(
                    f"failed functor substitution for {path}: {actual!r}"
                )
            applied.append(dict(row))

        schedule_after = c5._observer_snapshot(text)
        expected_schedule = c5._observer_snapshot(
            _defer_except(
                _production()[0],
                keep=keep,
                before=c5._observer_snapshot(_production()[0]),
                element_set=set(_element_paths(_production()[0])),
            )[0]
        )
        if schedule_after != expected_schedule:
            raise Issue224ParallelError(
                "dependency_substitution changed observer schedule/type outside the keep/defer contract"
            )

        final_functors = {
            path: mp.get_parameter(text, path, "functor") for path in element_paths
        }
        changed_functors = sorted(
            path for path in element_paths if final_functors[path] != original_functors[path]
        )
        expected_changed = sorted(row["path"] for row in applied)
        if changed_functors != expected_changed:
            raise Issue224ParallelError(
                f"unexpected functor mutation surface: expected={expected_changed}, "
                f"observed={changed_functors}"
            )
        return text, {
            "spec": spec,
            "target_family_count": 57,
            "kept_initial_count": len(keep),
            "deferred_count": len(deferred),
            "substitution_count": len(applied),
            "substitutions": applied,
            "changed_functor_paths": changed_functors,
            "non_target_changed_count": 0,
        }

    targets = set(spec["target_paths"])
    for path in sorted(targets):
        text = mp.upsert_parameter(text, path, "evaluation_type", "CELL_AVERAGE")
    after = c5._observer_snapshot(text)
    changed_schedule = [path for path in before if after[path] != before[path]]
    if changed_schedule:
        raise Issue224ParallelError(
            f"cell_average changed observer schedule/type snapshot: {changed_schedule}"
        )
    for path in sorted(targets):
        value = mp.get_parameter(text, path, "evaluation_type")
        if value != "CELL_AVERAGE":
            raise Issue224ParallelError(f"failed to set CELL_AVERAGE on {path}: {value!r}")
    return text, {
        "spec": spec,
        "target_family_count": 57,
        "cell_average_count": len(targets),
        "non_target_changed_count": 0,
    }


def _build(kind: str, spec: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    text, meta = _production()
    mutation: dict[str, Any] = {"kind": kind, "changed_count": 0}
    if kind == "candidate":
        text, mutation = _candidate(text, spec)
    elif kind == "all_57_deferred":
        text, mutation = _all_deferred(text)
    elif kind != "production":
        raise Issue224ParallelError(f"unknown case kind: {kind}")
    return text, {
        **meta,
        "issue": 224,
        "parent_issue": 222,
        "diagnostic": "PARALLEL_HYPOTHESIS_ZERO_STEP_OS_RSS",
        "hypothesis_id": spec["id"],
        "case_kind": kind,
        "uniform_refine": 2,
        "num_steps": 0,
        "physical_timestep_executed": False,
        "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "mutation": mutation,
        "production_promotion_claim": False,
    }


def _stage(case_dir: Path, *, kind: str, spec: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    text, meta = _build(kind, spec)
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
    kind: str,
    spec: Mapping[str, Any],
    timeout: float,
) -> dict[str, Any]:
    case_dir = out / "cases" / name
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    input_text, meta = _stage(case_dir, kind=kind, spec=spec)

    p2_log = logs / f"{name}_p2.log"
    p2 = s5r._p2(exe, case_dir, p2_log, timeout=timeout)
    item: dict[str, Any] = {"kind": kind, "meta": meta, "p2": p2, "hard_pass": False}
    if p2.get("returncode") != 0:
        item["reason"] = "P2_FAIL"
        return item

    runtime_log = logs / f"{name}_runtime.log"
    time_log = logs / f"{name}_time_v.log"
    runtime = c5r._runtime_with_os_rss(exe, case_dir, runtime_log, time_log, timeout=timeout)
    log_text = runtime_log.read_text(errors="replace") if runtime_log.is_file() else ""
    samples = live_memory_samples(runtime_log)
    setup = c4_base._sample(samples, "Finished Setting Up")
    user_objects = c4_base._sample(samples, "Finished Computing User Objects")
    initial_setup = c4_base._sample(samples, "Finished Performing Initial Setup")
    profiler_peak = max(samples, key=lambda x: float(x["resident_mb"])) if samples else None
    setup_mb = c4_base._mb(setup)
    post_initial_mb = c4_base._mb(user_objects) or c4_base._mb(initial_setup)
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
                "profiler_peak_resident_mb": c4_base._mb(profiler_peak),
                "os_max_rss_mib": os_peak_mib,
                "authoritative_peak_metric": "os_max_rss_mib",
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


def self_test() -> dict[str, Any]:
    text, _ = _production()
    paths = _element_paths(text)
    checks: dict[str, bool] = {
        "c6_self_test": c6.self_test().get("status") == "PASS",
        "element_aggregate_count_57": len(paths) == 57,
    }
    specs = (
        {"id": "H-test-one", "mode": "keep_initial", "keep_paths": ["Postprocessors/domain_volume"]},
        {"id": "H-test-cell", "mode": "cell_average", "target_paths": paths},
        {
            "id": "H-test-dependency-substitution",
            "mode": "dependency_substitution",
            "keep_paths": ["Postprocessors/n_e_inventory"],
            "substitutions": [
                {
                    "path": "Postprocessors/n_e_inventory",
                    "expected_functor": "n_e_physical",
                    "replacement_functor": "carrier_one",
                }
            ],
        },
    )
    for spec in specs:
        mutated, meta = _candidate(text, spec)
        checks[f"candidate_{spec['id']}_built"] = (
            mutated != text and meta["non_target_changed_count"] == 0
        )
    dep_mutated, dep_meta = _candidate(text, specs[2])
    checks["dependency_substitution_exact_functor"] = (
        mp.get_parameter(dep_mutated, "Postprocessors/n_e_inventory", "functor")
        == "carrier_one"
        and dep_meta.get("changed_functor_paths") == ["Postprocessors/n_e_inventory"]
    )

    try:
        _candidate(
            text,
            {
                "id": "H-test-dependency-mismatch",
                "mode": "dependency_substitution",
                "keep_paths": ["Postprocessors/n_e_inventory"],
                "substitutions": [
                    {
                        "path": "Postprocessors/n_e_inventory",
                        "expected_functor": "wrong_functor",
                        "replacement_functor": "carrier_one",
                    }
                ],
            },
        )
    except Issue224ParallelError:
        checks["dependency_substitution_rejects_expected_mismatch"] = True
    else:
        checks["dependency_substitution_rejects_expected_mismatch"] = False

    try:
        _candidate(
            text,
            {
                "id": "H-test-dependency-outside-keep",
                "mode": "dependency_substitution",
                "keep_paths": ["Postprocessors/domain_volume"],
                "substitutions": [
                    {
                        "path": "Postprocessors/n_e_inventory",
                        "expected_functor": "n_e_physical",
                        "replacement_functor": "carrier_one",
                    }
                ],
            },
        )
    except Issue224ParallelError:
        checks["dependency_substitution_rejects_path_outside_keep"] = True
    else:
        checks["dependency_substitution_rejects_path_outside_keep"] = False

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed_checks": failed}


def run(args: argparse.Namespace) -> int:
    try:
        raw = json.loads(args.spec_json)
    except json.JSONDecodeError as exc:
        raise Issue224ParallelError(f"invalid spec JSON: {exc}") from exc

    production_text, _ = _production()
    spec = _validate_spec(raw, production_text)
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Issue224ParallelError(f"invalid physics-opt: {exe}")

    p0 = self_test()
    if p0["status"] != "PASS":
        raise Issue224ParallelError(f"P0 failed: {p0}")

    out = args.results_root.resolve()
    summary: dict[str, Any] = {
        "schema_version": 2,
        "issue": 224,
        "hypothesis_id": spec["id"],
        "spec": spec,
        "base_sha": os.environ.get("EXPERIMENT_BASE_SHA"),
        "workflow_event_sha": os.environ.get("GITHUB_SHA"),
        "physics_opt_sha256": w5._sha256(exe),
        "production_input_sha256": hashlib.sha256(
            production_text.encode("utf-8")
        ).hexdigest(),
        "diagnostic": "PARALLEL_HYPOTHESIS_ZERO_STEP_OS_RSS",
        "physical_timesteps_authorized": 0,
        "authoritative_peak_metric": "GNU_time_v_Maximum_resident_set_size",
        "p0": p0,
        "cases": {},
        "decision": {},
    }

    sequence = (
        ("production_before", "production"),
        ("candidate", "candidate"),
        ("all_57_deferred", "all_57_deferred"),
        ("production_after", "production"),
    )
    for name, kind in sequence:
        case = _execute(exe, out, name=name, kind=kind, spec=spec, timeout=args.timeout)
        summary["cases"][name] = case
        _write(out, summary)
        if not case["hard_pass"]:
            summary["status"] = "ISSUE224_PARALLEL_HOLD"
            summary["decision"] = {
                "classification": "UNRESOLVED",
                "reason": f"setup-only contract failed for {name}",
                "promotion_authorized": False,
                "full_r2_solve_executed": False,
            }
            _write(out, summary)
            return 2

    before = summary["cases"]["production_before"]
    after = summary["cases"]["production_after"]
    candidate = summary["cases"]["candidate"]
    low = summary["cases"]["all_57_deferred"]
    drift = c5r._control_drift(before, after)
    cand_cmp = c5r._comparison(before, after, candidate)
    low_cmp = c5r._comparison(before, after, low)
    cand_class = c5r._family_classification(cand_cmp)
    low_class = c5r._family_classification(low_cmp)

    ready = drift.get("stable") is True and low_class == "MAJOR"
    summary["status"] = "ISSUE224_PARALLEL_EVIDENCE_READY" if ready else "ISSUE224_PARALLEL_HOLD"
    summary["decision"] = {
        "production_control_drift": drift,
        "candidate_comparison": cand_cmp,
        "low_control_comparison": low_cmp,
        "candidate_reduction_classification": cand_class,
        "low_control_reduction_classification": low_class,
        "interpretation_scope": "MEASUREMENT_ONLY",
        "promotion_authorized": False,
        "full_r2_solve_executed": False,
    }
    _write(out, summary)
    return 0 if ready else 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--spec-json")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.physics_opt is None or args.results_root is None or args.spec_json is None:
        parser.error("--physics-opt, --results-root, and --spec-json are required unless --self-test")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())