"""PF-3 performance investigation analyzer.

Consumes PF-1 managed BENCHMARK/PROFILE smoke evidence and produces a bounded,
Issue-agnostic bottleneck diagnosis. This first PF-3 slice deliberately avoids
physics changes and solver retuning: it only decomposes already-captured timing,
work, memory, and profiler-overhead evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from ...performance.runner import PerformanceContractError
from ...performance.smoke import default_results_root
from ...execution.runtime import resolve_executable, validate_executable

CANONICAL_CLASSES = {
    "APPLICATION_EVALUATION",
    "JACOBIAN_AD",
    "NONLINEAR_WORK",
    "MATRIX_ASSEMBLY",
    "PC_FACTORIZATION",
    "LINEAR_SOLVE",
    "MEMORY",
    "PARALLEL",
    "INIT_IO",
    "MIXED_PERFORMANCE_COST",
}


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise PerformanceContractError(f"missing {label}: {path}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise PerformanceContractError(f"{label} must contain a JSON object: {path}")
    return payload


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _rank_zero(row: dict[str, Any]) -> bool:
    rank = row.get("Rank")
    return rank in (None, "", 0, "0", 0.0)


def petsc_events(profile: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Aggregate rank-0 PETSc event Count/Time by exact event name."""

    petsc = profile.get("performance", {}).get("petsc")
    if not isinstance(petsc, dict):
        return {}
    rows = petsc.get("rows")
    if not isinstance(rows, list):
        return {}

    events: dict[str, dict[str, float]] = {}
    for row in rows:
        if not isinstance(row, dict) or not _rank_zero(row):
            continue
        name = row.get("Event Name")
        if not isinstance(name, str) or not name or name == "summary":
            continue
        time_value = _finite_number(row.get("Time"))
        count_value = _finite_number(row.get("Count"))
        bucket = events.setdefault(name, {"time_seconds": 0.0, "count": 0.0})
        if time_value is not None:
            bucket["time_seconds"] += time_value
        if count_value is not None:
            bucket["count"] += count_value
    return events


def perfgraph_nodes(profile: dict[str, Any]) -> list[dict[str, Any]]:
    perfgraph = profile.get("performance", {}).get("perfgraph")
    if not isinstance(perfgraph, dict):
        return []
    nodes = perfgraph.get("nodes")
    if not isinstance(nodes, list):
        return []
    clean: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("name"), str):
            continue
        seconds = _finite_number(node.get("self_seconds"))
        calls = _finite_number(node.get("num_calls"))
        if seconds is None:
            continue
        clean.append(
            {
                "name": node["name"],
                "parent": node.get("parent"),
                "self_seconds": seconds,
                "num_calls": int(calls) if calls is not None else None,
            }
        )
    return clean


def _event_time(events: dict[str, dict[str, float]], *names: str) -> float:
    return sum(events.get(name, {}).get("time_seconds", 0.0) for name in names)


def _event_count(events: dict[str, dict[str, float]], name: str) -> int | None:
    value = events.get(name, {}).get("count")
    return int(value) if isinstance(value, (int, float)) else None


def _pg_sum(nodes: list[dict[str, Any]], needles: tuple[str, ...]) -> float:
    lowered = tuple(n.lower() for n in needles)
    return sum(
        float(node["self_seconds"])
        for node in nodes
        if any(needle in node["name"].lower() for needle in lowered)
    )


def _score_seconds(profile: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    events = petsc_events(profile)
    nodes = perfgraph_nodes(profile)

    pg_jacobian = _pg_sum(nodes, ("jacobian",))
    petsc_jacobian = _event_time(events, "SNESJacobianEval")

    pg_application = _pg_sum(
        nodes,
        (
            "kernel",
            "material",
            "functor",
            "userobject",
            "user object",
        ),
    )

    factor_numeric = _event_time(events, "MatLUFactorNum", "MatCholFctrNum")
    factor_symbolic = _event_time(events, "MatLUFactorSym", "MatCholFctrSym")
    pc_setup = _event_time(events, "PCSetUp")
    factorization = max(pc_setup, factor_numeric + factor_symbolic)

    linear = max(
        _event_time(events, "KSPSolve"),
        _event_time(events, "MatSolve", "MatSolves"),
    )
    assembly = _event_time(events, "MatAssemblyBegin", "MatAssemblyEnd")
    init_io = _pg_sum(nodes, ("initialsetup", "initial setup", "output", "meshgenerator"))

    work = profile.get("work", {}) if isinstance(profile.get("work"), dict) else {}
    nl = work.get("nonlinear_iterations")
    residuals = work.get("residual_evaluations")
    nonlinear_proxy = 0.0
    # Work amplification cannot be established from one sample alone. Only a
    # clearly excessive count earns a small diagnostic score; it cannot outrank
    # measured timing unless the timing evidence is otherwise weak.
    if isinstance(nl, int) and nl >= 8:
        wall = _finite_number(profile.get("performance", {}).get("wall_seconds")) or 0.0
        nonlinear_proxy = min(0.20 * wall, 0.02 * wall * nl)
    if isinstance(residuals, int) and isinstance(nl, int) and nl > 0 and residuals / nl >= 4:
        wall = _finite_number(profile.get("performance", {}).get("wall_seconds")) or 0.0
        nonlinear_proxy = max(nonlinear_proxy, 0.15 * wall)

    scores = {
        "APPLICATION_EVALUATION": pg_application,
        "JACOBIAN_AD": max(pg_jacobian, petsc_jacobian),
        "NONLINEAR_WORK": nonlinear_proxy,
        "MATRIX_ASSEMBLY": assembly,
        "PC_FACTORIZATION": factorization,
        "LINEAR_SOLVE": linear,
        "INIT_IO": init_io,
    }

    evidence = {
        "petsc_events": {
            name: events.get(name)
            for name in (
                "SNESSolve",
                "SNESFunctionEval",
                "SNESJacobianEval",
                "KSPSolve",
                "PCSetUp",
                "MatAssemblyBegin",
                "MatAssemblyEnd",
                "MatLUFactorSym",
                "MatLUFactorNum",
                "MatSolve",
            )
            if name in events
        },
        "perfgraph_jacobian_self_seconds": pg_jacobian,
        "perfgraph_application_self_seconds": pg_application,
        "perfgraph_init_io_self_seconds": init_io,
        "factorization_seconds": factorization,
        "matrix_assembly_seconds": assembly,
        "linear_solve_seconds": linear,
    }
    return scores, evidence


def classify_bottleneck(profile: dict[str, Any]) -> dict[str, Any]:
    wall = _finite_number(profile.get("performance", {}).get("wall_seconds"))
    if wall is None or wall <= 0:
        return {
            "outcome": "INSUFFICIENT_EVIDENCE",
            "bottleneck_class": None,
            "confidence": "none",
            "reason": "profile wall time is missing or non-positive",
            "scores": {},
        }

    raw_scores, evidence = _score_seconds(profile)
    scores = {
        name: {
            "seconds": seconds,
            "wall_fraction": seconds / wall if wall else None,
        }
        for name, seconds in raw_scores.items()
        if seconds > 0
    }
    ordered = sorted(scores.items(), key=lambda item: item[1]["seconds"], reverse=True)
    if not ordered:
        return {
            "outcome": "INSUFFICIENT_EVIDENCE",
            "bottleneck_class": None,
            "confidence": "none",
            "reason": "no classifiable timing evidence was captured",
            "scores": scores,
            "evidence": evidence,
        }

    top_name, top = ordered[0]
    second_name, second = ordered[1] if len(ordered) > 1 else (None, {"seconds": 0.0, "wall_fraction": 0.0})
    top_fraction = float(top["wall_fraction"])
    second_seconds = float(second["seconds"])
    ratio = float(top["seconds"]) / second_seconds if second_seconds > 0 else math.inf

    if top_fraction >= 0.35 and ratio >= 1.50:
        outcome = "DOMINANT"
        bottleneck = top_name
        confidence = "high"
        reason = f"{top_name} accounts for {top_fraction:.1%} of wall and is {ratio:.2f}x the next timing class"
    elif top_fraction >= 0.25 and ratio >= 1.25:
        outcome = "DOMINANT"
        bottleneck = top_name
        confidence = "medium"
        reason = f"{top_name} accounts for {top_fraction:.1%} of wall and is {ratio:.2f}x the next timing class"
    elif top_fraction >= 0.15 and second.get("wall_fraction", 0.0) >= 0.15 and ratio < 1.25:
        outcome = "MIXED"
        bottleneck = "MIXED_PERFORMANCE_COST"
        confidence = "medium"
        reason = f"top classes {top_name} and {second_name} are both material and differ by only {ratio:.2f}x"
    else:
        outcome = "INSUFFICIENT_EVIDENCE"
        bottleneck = None
        confidence = "low"
        reason = f"largest measured class {top_name} is {top_fraction:.1%} of wall without sufficient separation"

    return {
        "outcome": outcome,
        "bottleneck_class": bottleneck,
        "confidence": confidence,
        "reason": reason,
        "top_class": top_name,
        "second_class": second_name,
        "top_to_second_ratio": None if math.isinf(ratio) else ratio,
        "scores": scores,
        "evidence": evidence,
    }


def _per_call(seconds: float | None, count: Any) -> float | None:
    if seconds is None or not isinstance(count, int) or count <= 0:
        return None
    return float(seconds) / count


def build_investigation_summary(
    benchmark: dict[str, Any],
    profile: dict[str, Any],
    smoke: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if benchmark.get("validation", {}).get("status") != "P2_PASS_P3_PASS":
        raise PerformanceContractError("benchmark result is not P2_PASS_P3_PASS")
    if profile.get("validation", {}).get("status") != "P2_PASS_P3_PASS":
        raise PerformanceContractError("profile result is not P2_PASS_P3_PASS")

    b_wall = _finite_number(benchmark.get("performance", {}).get("wall_seconds"))
    p_wall = _finite_number(profile.get("performance", {}).get("wall_seconds"))
    ratio = p_wall / b_wall if b_wall and p_wall is not None else None
    overhead = ratio - 1.0 if ratio is not None else None

    classification = classify_bottleneck(profile)
    events = petsc_events(profile)
    work = profile.get("work", {}) if isinstance(profile.get("work"), dict) else {}
    problem = profile.get("problem", {}) if isinstance(profile.get("problem"), dict) else {}

    jac_sec = _event_time(events, "SNESJacobianEval") or classification.get("evidence", {}).get(
        "perfgraph_jacobian_self_seconds", 0.0
    )
    residual_sec = _event_time(events, "SNESFunctionEval")
    linear_sec = _event_time(events, "KSPSolve")

    dofs = problem.get("dofs")
    normalized = {
        "wall_seconds_per_dof": p_wall / dofs if p_wall is not None and isinstance(dofs, int) and dofs > 0 else None,
        "jacobian_seconds_per_evaluation": _per_call(jac_sec, work.get("jacobian_evaluations")),
        "residual_seconds_per_evaluation": _per_call(residual_sec, work.get("residual_evaluations")),
        "linear_seconds_per_iteration": _per_call(linear_sec, work.get("linear_iterations")),
    }

    nodes = sorted(
        perfgraph_nodes(profile), key=lambda node: node["self_seconds"], reverse=True
    )
    top_sections = nodes[:15]

    checks = {
        "smoke_pass": smoke.get("pass") is True if isinstance(smoke, dict) else None,
        "same_input_sha": benchmark.get("identity", {}).get("input_sha256")
        == profile.get("identity", {}).get("input_sha256"),
        "same_dofs": benchmark.get("problem", {}).get("dofs") == profile.get("problem", {}).get("dofs"),
        "same_nonlinear_iterations": benchmark.get("work", {}).get("nonlinear_iterations")
        == profile.get("work", {}).get("nonlinear_iterations"),
        "same_linear_iterations": benchmark.get("work", {}).get("linear_iterations")
        == profile.get("work", {}).get("linear_iterations"),
        "same_residual_evaluations": benchmark.get("work", {}).get("residual_evaluations")
        == profile.get("work", {}).get("residual_evaluations"),
        "profile_has_perfgraph": bool(profile.get("performance", {}).get("perfgraph")),
        "profile_has_petsc": bool(profile.get("performance", {}).get("petsc")),
    }
    mandatory = {k: v for k, v in checks.items() if v is not None}

    return {
        "schema_version": 1,
        "analysis_status": "PASS" if all(mandatory.values()) else "EVIDENCE_PARITY_FAIL",
        "case_id": profile.get("case_id"),
        "experiment_id": profile.get("experiment_id"),
        "benchmark_wall_seconds": b_wall,
        "profile_wall_seconds": p_wall,
        "profile_to_benchmark_ratio": ratio,
        "profiler_overhead_fraction": overhead,
        "profiler_overhead_warning": overhead is not None and overhead > 0.25,
        "problem": problem,
        "work": work,
        "normalized_metrics": normalized,
        "classification": classification,
        "top_perfgraph_sections": top_sections,
        "parity_checks": checks,
        "environment": profile.get("environment"),
        "identity": profile.get("identity"),
    }


def discover_latest_smoke(results_root: Path) -> Path:
    root = Path(results_root).expanduser().resolve()
    if not root.is_dir():
        raise PerformanceContractError(f"results root does not exist: {root}")
    candidates: list[Path] = []
    for path in root.glob("pf1_smoke_*"):
        summary = path / "smoke_summary.json"
        if not summary.is_file():
            continue
        try:
            payload = json.loads(summary.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("pass") is True:
            candidates.append(path)
    if not candidates:
        raise PerformanceContractError(f"no passing PF-1 smoke run found under {root}")
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def run_investigation(
    *,
    run_root: Path | None = None,
    executable: str | Path | None = None,
    results_root: Path | None = None,
) -> int:
    if run_root is None:
        exe = resolve_executable(executable)
        validate_executable(exe)
        root = discover_latest_smoke(
            results_root if results_root is not None else default_results_root(exe)
        )
    else:
        root = Path(run_root).expanduser().resolve()
        if not root.is_dir():
            raise PerformanceContractError(f"run root does not exist: {root}")

    smoke_path = root / "smoke_summary.json"
    smoke = _load_json(smoke_path, "smoke summary")
    if smoke.get("pass") is not True:
        raise PerformanceContractError("PF-1 smoke summary is not PASS")
    benchmark = _load_json(root / "benchmark" / "result.json", "benchmark result")
    profile = _load_json(root / "profile" / "result.json", "profile result")

    summary = build_investigation_summary(benchmark, profile, smoke)
    summary["run_root"] = str(root)
    output = root / "investigation_summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    classification = summary["classification"]
    print(f"PF3_INVESTIGATION_ROOT: {root}")
    print(f"PF3_ANALYSIS_STATUS: {summary['analysis_status']}")
    print(f"PF3_OUTCOME: {classification['outcome']}")
    print(f"PF3_BOTTLENECK: {classification.get('bottleneck_class') or 'UNRESOLVED'}")
    print(f"PF3_CONFIDENCE: {classification['confidence']}")
    print(f"PF3_REASON: {classification['reason']}")
    if summary.get("profile_to_benchmark_ratio") is not None:
        print(f"PF3_PROFILE_OVERHEAD_RATIO: {summary['profile_to_benchmark_ratio']:.4f}")
    print("PF3_TOP_SECTIONS:")
    for node in summary["top_perfgraph_sections"][:8]:
        print(
            f"  {node['self_seconds']:.6g}s  calls={node.get('num_calls')}  "
            f"{node['name']}"
        )
    print(f"PF3_INVESTIGATION_SUMMARY: {output}")
    return 0 if summary["analysis_status"] == "PASS" else 2


def _synthetic_profile(
    *,
    wall: float,
    jacobian: float = 0.0,
    factor: float = 0.0,
    application: float = 0.0,
    linear: float = 0.0,
) -> dict[str, Any]:
    nodes = [
        {"name": "app", "parent": None, "self_seconds": 0.01, "num_calls": 1},
    ]
    if jacobian:
        nodes.append(
            {
                "name": "NonlinearSystemBase::computeJacobianInternal",
                "parent": "solve",
                "self_seconds": jacobian,
                "num_calls": 3,
            }
        )
    if application:
        nodes.append(
            {
                "name": "NonlinearSystemBase::Kernels",
                "parent": "computeJacobianInternal",
                "self_seconds": application,
                "num_calls": 3,
            }
        )
    rows = [
        {"Event Name": "SNESJacobianEval", "Rank": 0, "Count": 3, "Time": jacobian * 0.8},
        {"Event Name": "PCSetUp", "Rank": 0, "Count": 3, "Time": factor},
        {"Event Name": "MatLUFactorNum", "Rank": 0, "Count": 3, "Time": factor},
        {"Event Name": "KSPSolve", "Rank": 0, "Count": 3, "Time": linear},
        {"Event Name": "SNESFunctionEval", "Rank": 0, "Count": 4, "Time": 1.0},
    ]
    return {
        "validation": {"status": "P2_PASS_P3_PASS"},
        "case_id": "synthetic",
        "experiment_id": "pf3-selftest",
        "identity": {"input_sha256": "abc"},
        "environment": {"hostname": "host"},
        "problem": {"dofs": 1000},
        "work": {
            "nonlinear_iterations": 3,
            "linear_iterations": 3,
            "residual_evaluations": 4,
            "jacobian_evaluations": 3,
        },
        "performance": {
            "wall_seconds": wall,
            "perfgraph": {"nodes": nodes},
            "petsc": {"rows": rows},
        },
    }


def self_test() -> int:
    cases = [
        ("jacobian", _synthetic_profile(wall=30, jacobian=15, factor=5, application=3), "JACOBIAN_AD"),
        ("factor", _synthetic_profile(wall=30, jacobian=4, factor=15, application=2), "PC_FACTORIZATION"),
        ("mixed", _synthetic_profile(wall=30, jacobian=7, factor=6.5, application=1), "MIXED_PERFORMANCE_COST"),
    ]
    for name, profile, expected in cases:
        result = classify_bottleneck(profile)
        if result.get("bottleneck_class") != expected:
            print(f"PF3_SELFTEST_{name}: FAIL {result}")
            return 1

    insufficient = _synthetic_profile(wall=30, jacobian=3, factor=2, application=1)
    result = classify_bottleneck(insufficient)
    if result.get("outcome") != "INSUFFICIENT_EVIDENCE" or result.get("bottleneck_class") is not None:
        print(f"PF3_SELFTEST_insufficient: FAIL {result}")
        return 1

    benchmark = _synthetic_profile(wall=10)
    benchmark["performance"]["perfgraph"] = None
    benchmark["performance"]["petsc"] = None
    profile = _synthetic_profile(wall=12, jacobian=6, factor=2, application=1)
    summary = build_investigation_summary(benchmark, profile, {"pass": True})
    if summary["analysis_status"] != "PASS" or summary["profile_to_benchmark_ratio"] != 1.2:
        print("PF3_SELFTEST_summary: FAIL")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old = root / "pf1_smoke_old"
        new = root / "pf1_smoke_new"
        old.mkdir(); new.mkdir()
        (old / "smoke_summary.json").write_text(json.dumps({"pass": True}))
        (new / "smoke_summary.json").write_text(json.dumps({"pass": True}))
        old.touch()
        found = discover_latest_smoke(root)
        if found.name not in {"pf1_smoke_old", "pf1_smoke_new"}:
            print("PF3_SELFTEST_discovery: FAIL")
            return 1

    print("QPX_PERFORMANCE_INVESTIGATION_SELFTEST: PASS")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx investigate")
    parser.add_argument("--run-root")
    parser.add_argument("--qpx")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return self_test()
    if not args.run_root and not args.qpx:
        parser.error("provide --qpx for automatic discovery or --run-root for an explicit smoke run")
    try:
        return run_investigation(
            run_root=Path(args.run_root) if args.run_root else None,
            executable=args.qpx,
            results_root=Path(args.results_root) if args.results_root else None,
        )
    except (PerformanceContractError, json.JSONDecodeError) as exc:
        print(f"PF3_INVESTIGATION_FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
