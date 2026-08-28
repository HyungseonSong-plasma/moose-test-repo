"""Managed PF-1 BENCHMARK/PROFILE smoke execution.

This module owns user-local performance evidence layout for the PF-1 runtime
smoke gate: it creates manifests, timestamped result directories, executes both
measurement modes, and writes a parity summary. Users should not need shell
scripts to manage run directories or JSON manifests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .performance_core import (
    PerformanceContractError,
    run_measurement,
    validate_experiment_manifest,
)
from .runtime import resolve_executable, validate_executable


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "case"


def build_smoke_manifest(
    *,
    mode: str,
    case_dir: Path,
    input_name: str,
    experiment_id: str,
    case_id: str,
    num_steps: int = 1,
    species: list[str] | None = None,
) -> dict[str, Any]:
    if mode not in {"BENCHMARK", "PROFILE"}:
        raise PerformanceContractError(f"unsupported smoke mode: {mode}")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "case_id": case_id,
        "mode": mode,
        "case": {
            "directory": str(Path(case_dir).expanduser().resolve()),
            "input": input_name,
        },
        "runtime": {"num_steps": num_steps},
        "collectors": {
            "work_counters": True,
            "perfgraph": mode == "PROFILE",
            "petsc_log": mode == "PROFILE",
        },
        "stream_output": True,
    }
    if species:
        manifest["physics"] = {"species": list(species)}
    validate_experiment_manifest(manifest)
    return manifest


def default_results_root(executable: Path) -> Path:
    """Use the QPX-local temp/results directory unless explicitly overridden."""

    return executable.resolve().parent / "temp" / "results"


def create_run_root(results_root: Path, case_id: str) -> Path:
    results_root = Path(results_root).expanduser().resolve()
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"pf1_smoke_{_safe_token(case_id)}_{stamp}"
    candidate = results_root / stem
    index = 1
    while candidate.exists():
        candidate = results_root / f"{stem}_{index:02d}"
        index += 1
    candidate.mkdir()
    return candidate


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _load_result(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text())
    return payload if isinstance(payload, dict) else None


def compare_smoke_results(
    benchmark: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "benchmark_result_present": benchmark is not None,
        "profile_result_present": profile is not None,
    }
    if benchmark is None or profile is None:
        return {"pass": False, "checks": checks, "parity": {}, "timing": {}}

    checks["benchmark_runtime_pass"] = (
        benchmark.get("validation", {}).get("status") == "P2_PASS_P3_PASS"
    )
    checks["profile_runtime_pass"] = (
        profile.get("validation", {}).get("status") == "P2_PASS_P3_PASS"
    )
    checks["benchmark_has_no_perfgraph"] = (
        benchmark.get("performance", {}).get("perfgraph") is None
    )
    checks["benchmark_has_no_petsc"] = (
        benchmark.get("performance", {}).get("petsc") is None
    )
    checks["profile_has_perfgraph"] = bool(
        profile.get("performance", {}).get("perfgraph")
    )
    checks["profile_has_petsc"] = bool(
        profile.get("performance", {}).get("petsc")
    )

    fields = {
        "input_sha256": (
            benchmark.get("identity", {}).get("input_sha256"),
            profile.get("identity", {}).get("input_sha256"),
        ),
        "dofs": (
            benchmark.get("problem", {}).get("dofs"),
            profile.get("problem", {}).get("dofs"),
        ),
        "nonlinear_iterations": (
            benchmark.get("work", {}).get("nonlinear_iterations"),
            profile.get("work", {}).get("nonlinear_iterations"),
        ),
        "linear_iterations": (
            benchmark.get("work", {}).get("linear_iterations"),
            profile.get("work", {}).get("linear_iterations"),
        ),
        "residual_evaluations": (
            benchmark.get("work", {}).get("residual_evaluations"),
            profile.get("work", {}).get("residual_evaluations"),
        ),
    }
    parity: dict[str, Any] = {}
    for name, (left, right) in fields.items():
        match = left == right
        checks[f"parity_{name}"] = match
        parity[name] = {"benchmark": left, "profile": right, "match": match}

    benchmark_wall = benchmark.get("performance", {}).get("wall_seconds")
    profile_wall = profile.get("performance", {}).get("wall_seconds")
    ratio = None
    if isinstance(benchmark_wall, (int, float)) and benchmark_wall > 0:
        if isinstance(profile_wall, (int, float)):
            ratio = float(profile_wall) / float(benchmark_wall)

    return {
        "pass": all(checks.values()),
        "checks": checks,
        "parity": parity,
        "timing": {
            "benchmark_wall_seconds": benchmark_wall,
            "profile_wall_seconds": profile_wall,
            "profile_to_benchmark_ratio": ratio,
            "timing_parity_required": False,
        },
    }


def run_smoke_pair(
    *,
    case_dir: Path,
    input_name: str = "input.i",
    executable: str | Path | None = None,
    results_root: Path | None = None,
    case_id: str | None = None,
    experiment_id: str = "pf1-runtime-smoke",
    num_steps: int = 1,
    species: list[str] | None = None,
) -> int:
    exe = resolve_executable(executable)
    validate_executable(exe)

    case_dir = Path(case_dir).expanduser().resolve()
    if not case_dir.is_dir():
        raise PerformanceContractError(f"case directory does not exist: {case_dir}")
    input_path = (case_dir / input_name).resolve()
    if case_dir not in input_path.parents and input_path.parent != case_dir:
        raise PerformanceContractError("case input must resolve inside case directory")
    if not input_path.is_file():
        raise PerformanceContractError(f"case input does not exist: {input_path}")

    resolved_case_id = case_id or case_dir.name
    root = create_run_root(
        results_root if results_root is not None else default_results_root(exe),
        resolved_case_id,
    )

    benchmark_manifest = build_smoke_manifest(
        mode="BENCHMARK",
        case_dir=case_dir,
        input_name=input_name,
        experiment_id=experiment_id,
        case_id=resolved_case_id,
        num_steps=num_steps,
        species=species,
    )
    profile_manifest = build_smoke_manifest(
        mode="PROFILE",
        case_dir=case_dir,
        input_name=input_name,
        experiment_id=experiment_id,
        case_id=resolved_case_id,
        num_steps=num_steps,
        species=species,
    )

    benchmark_manifest_path = root / "benchmark_manifest.json"
    profile_manifest_path = root / "profile_manifest.json"
    _write_json(benchmark_manifest_path, benchmark_manifest)
    _write_json(profile_manifest_path, profile_manifest)

    print(f"PF1_SMOKE_ROOT: {root}")
    print("PF1_SMOKE_PHASE: BENCHMARK")
    benchmark_rc = run_measurement(
        benchmark_manifest_path,
        executable=exe,
        out_dir=root / "benchmark",
    )

    print("PF1_SMOKE_PHASE: PROFILE")
    profile_rc = run_measurement(
        profile_manifest_path,
        executable=exe,
        out_dir=root / "profile",
    )

    benchmark_result = _load_result(root / "benchmark" / "result.json")
    profile_result = _load_result(root / "profile" / "result.json")
    summary = compare_smoke_results(benchmark_result, profile_result)
    summary.update(
        {
            "schema_version": 1,
            "experiment_id": experiment_id,
            "case_id": resolved_case_id,
            "case_dir": str(case_dir),
            "input": input_name,
            "qpx_realpath": str(exe),
            "results_root": str(root.parent),
            "run_root": str(root),
            "benchmark_returncode": benchmark_rc,
            "profile_returncode": profile_rc,
            "benchmark_result": str(root / "benchmark" / "result.json"),
            "profile_result": str(root / "profile" / "result.json"),
        }
    )
    _write_json(root / "smoke_summary.json", summary)

    print("PF1_SMOKE_RESULT:", "PASS" if summary["pass"] else "FAIL")
    print(f"PF1_SMOKE_SUMMARY: {root / 'smoke_summary.json'}")
    print(f"PF1_SMOKE_ROOT: {root}")
    return 0 if summary["pass"] else 2


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        case_dir = Path(tmp) / "case"
        case_dir.mkdir()
        (case_dir / "input.i").write_text("[Mesh]\n[]\n")

        benchmark_manifest = build_smoke_manifest(
            mode="BENCHMARK",
            case_dir=case_dir,
            input_name="input.i",
            experiment_id="selftest",
            case_id="case",
        )
        profile_manifest = build_smoke_manifest(
            mode="PROFILE",
            case_dir=case_dir,
            input_name="input.i",
            experiment_id="selftest",
            case_id="case",
        )
        if benchmark_manifest["collectors"]["perfgraph"]:
            print("PF1_SMOKE_SELFTEST: BENCHMARK_COLLECTOR_FAIL")
            return 1
        if not profile_manifest["collectors"]["perfgraph"]:
            print("PF1_SMOKE_SELFTEST: PROFILE_COLLECTOR_FAIL")
            return 1

        base = {
            "validation": {"status": "P2_PASS_P3_PASS"},
            "identity": {"input_sha256": "abc"},
            "problem": {"dofs": 100},
            "work": {
                "nonlinear_iterations": 3,
                "linear_iterations": 3,
                "residual_evaluations": 4,
            },
            "performance": {
                "wall_seconds": 10.0,
                "perfgraph": None,
                "petsc": None,
            },
        }
        profile = json.loads(json.dumps(base))
        profile["performance"]["wall_seconds"] = 12.0
        profile["performance"]["perfgraph"] = {"nodes": [{"name": "app"}]}
        profile["performance"]["petsc"] = {"rows": [{"Event Name": "SNESSolve"}]}

        summary = compare_smoke_results(base, profile)
        if not summary["pass"]:
            print("PF1_SMOKE_SELFTEST: POSITIVE_PAIR_FAIL")
            return 1

        mutated = json.loads(json.dumps(profile))
        mutated["problem"]["dofs"] = 101
        summary = compare_smoke_results(base, mutated)
        if summary["pass"] or summary["checks"].get("parity_dofs") is not False:
            print("PF1_SMOKE_SELFTEST: DOF_MUTATION_MISSED")
            return 1

    print("QPX_PERFORMANCE_SMOKE_SELFTEST: PASS")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx measure-smoke")
    parser.add_argument("case_dir", nargs="?")
    parser.add_argument("--input", default="input.i")
    parser.add_argument("--qpx")
    parser.add_argument("--results-root")
    parser.add_argument("--case-id")
    parser.add_argument("--experiment-id", default="pf1-runtime-smoke")
    parser.add_argument("--num-steps", type=int, default=1)
    parser.add_argument("--species", nargs="*")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return self_test()
    if not args.case_dir:
        parser.error("case_dir is required unless --self-test is used")
    try:
        return run_smoke_pair(
            case_dir=Path(args.case_dir),
            input_name=args.input,
            executable=args.qpx,
            results_root=Path(args.results_root) if args.results_root else None,
            case_id=args.case_id,
            experiment_id=args.experiment_id,
            num_steps=args.num_steps,
            species=args.species or None,
        )
    except PerformanceContractError as exc:
        print(f"PERFORMANCE_CONTRACT_FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
