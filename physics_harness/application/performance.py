"""Canonical application orchestration for performance measurement and analysis.

The application layer coordinates solver-neutral execution primitives with
explicit adapter boundaries. Raw MOOSE/PETSc syntax and decoding are owned by
adapter packages; backend-neutral interpretation remains in analysis.
"""
from __future__ import annotations

import json
import os
import platform
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from physics_harness.adapters.moose.performance.collection import (
    MoosePerformanceDecodeError,
    check_overlay_collisions,
    collect_perfgraph_json,
    find_output,
    max_memory_mb,
    metric_int,
    parse_framework_identity,
    parse_problem_identity,
    read_last_metrics_row,
)
from physics_harness.adapters.moose.performance.measurement import write_measurement_overlay
from physics_harness.adapters.moose.performance.profile import jacobian_self_time
from physics_harness.adapters.petsc.performance import (
    collect_log_view_csv,
    decode_timing_facts,
    jacobian_evaluation_count,
    log_view_args,
)
from physics_harness.analysis.performance.profile import analyze_facts
from physics_harness.evidence import ensure_fresh_directory, sha256_file
from physics_harness.execution.runtime import resolve_executable, run_physics, validate_executable

SCHEMA_VERSION = 1
VALID_MODES = {"BENCHMARK", "PROFILE"}
RESULT_STATUSES = {
    "P2_PASS_P3_PASS",
    "HARNESS_OR_CONSTRUCTION_FAIL",
    "RUNTIME_FAIL_OR_NONCONVERGENCE",
}


class PerformanceContractError(ValueError):
    """Raised when a performance manifest/result violates the application contract."""


def result_status(result: dict[str, Any] | None) -> str | None:
    if not isinstance(result, dict):
        return None
    validation = result.get("validation")
    if not isinstance(validation, dict):
        return None
    status = validation.get("status")
    return status if isinstance(status, str) else None


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PerformanceContractError(f"{path} must be an object")
    return value


def _string(mapping: dict[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PerformanceContractError(f"{path}.{key} must be a non-empty string")
    return value


def _nonnegative_int(mapping: dict[str, Any], key: str, path: str) -> int | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PerformanceContractError(f"{path}.{key} must be a non-negative integer or null")
    return value


def _nonnegative_number(mapping: dict[str, Any], key: str, path: str) -> float | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise PerformanceContractError(f"{path}.{key} must be a non-negative number or null")
    return float(value)


def validate_experiment_manifest(data: dict[str, Any]) -> dict[str, Any]:
    root = _mapping(data, "manifest")
    if root.get("schema_version") != SCHEMA_VERSION:
        raise PerformanceContractError(f"manifest.schema_version must be {SCHEMA_VERSION}")
    _string(root, "experiment_id", "manifest")
    _string(root, "case_id", "manifest")
    mode = _string(root, "mode", "manifest")
    if mode not in VALID_MODES:
        raise PerformanceContractError(f"manifest.mode must be one of {sorted(VALID_MODES)}")
    case = _mapping(root.get("case"), "manifest.case")
    _string(case, "directory", "manifest.case")
    _string(case, "input", "manifest.case")
    runtime = _mapping(root.get("runtime", {}), "manifest.runtime")
    num_steps = runtime.get("num_steps", 1)
    if isinstance(num_steps, bool) or not isinstance(num_steps, int) or num_steps <= 0:
        raise PerformanceContractError("manifest.runtime.num_steps must be a positive integer")
    collectors = _mapping(root.get("collectors", {}), "manifest.collectors")
    for key in ("work_counters", "perfgraph", "petsc_log"):
        if key in collectors and not isinstance(collectors[key], bool):
            raise PerformanceContractError(f"manifest.collectors.{key} must be boolean")
    perfgraph = collectors.get("perfgraph", mode == "PROFILE")
    petsc_log = collectors.get("petsc_log", mode == "PROFILE")
    if mode == "BENCHMARK" and (perfgraph or petsc_log):
        raise PerformanceContractError("BENCHMARK mode cannot enable PerfGraph/PETSc deep collectors")
    if mode == "PROFILE" and not (perfgraph or petsc_log):
        raise PerformanceContractError("PROFILE mode must enable at least one deep collector")
    return root


def validate_result_record(data: dict[str, Any]) -> dict[str, Any]:
    root = _mapping(data, "result")
    if root.get("schema_version") != SCHEMA_VERSION:
        raise PerformanceContractError(f"result.schema_version must be {SCHEMA_VERSION}")
    for key in ("run_id", "experiment_id", "case_id", "mode"):
        _string(root, key, "result")
    if root["mode"] not in VALID_MODES:
        raise PerformanceContractError(f"result.mode must be one of {sorted(VALID_MODES)}")
    identity = _mapping(root.get("identity"), "result.identity")
    for key in ("input_sha256", "physics_realpath", "executable_sha256"):
        _string(identity, key, "result.identity")
    environment = _mapping(root.get("environment"), "result.environment")
    for key in ("hostname", "platform", "python"):
        _string(environment, key, "result.environment")
    problem = _mapping(root.get("problem"), "result.problem")
    for key in ("nodes", "elements", "dofs"):
        _nonnegative_int(problem, key, "result.problem")
    for key in ("variables", "species"):
        value = problem.get(key)
        if value is not None and (not isinstance(value, list) or not all(isinstance(item, str) for item in value)):
            raise PerformanceContractError(f"result.problem.{key} must be string array or null")
    work = _mapping(root.get("work"), "result.work")
    for key in ("nonlinear_iterations", "linear_iterations", "residual_evaluations", "jacobian_evaluations"):
        _nonnegative_int(work, key, "result.work")
    performance = _mapping(root.get("performance"), "result.performance")
    _nonnegative_number(performance, "wall_seconds", "result.performance")
    _nonnegative_number(performance, "max_memory_mb", "result.performance")
    for key in ("perfgraph", "petsc"):
        if performance.get(key) is not None:
            _mapping(performance[key], f"result.performance.{key}")
    validation = _mapping(root.get("validation"), "result.validation")
    status = _string(validation, "status", "result.validation")
    if status not in RESULT_STATUSES:
        raise PerformanceContractError(f"result.validation.status must be one of {sorted(RESULT_STATUSES)}")
    for key in ("p2_returncode", "p3_returncode"):
        value = validation.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise PerformanceContractError(f"result.validation.{key} must be integer or null")
    _mapping(root.get("evidence"), "result.evidence")
    return root


def build_measurement_stats(result: dict[str, Any]) -> Any:
    from physics_harness.analysis.statistics_builder import build_convergence_stats, build_simulation_stats

    convergence = build_convergence_stats(work=_mapping(result.get("work"), "result.work"))
    return build_simulation_stats(result, convergence=convergence)


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "case"


def _env_int(*names: str, default: int = 1) -> int:
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    return default


def _cpu_model() -> str | None:
    processor = platform.processor().strip()
    if processor:
        return processor
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        match = re.search(r"^model name\s*:\s*(.+)$", cpuinfo.read_text(errors="replace"), re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _collect_environment(exe: Path) -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(), "platform": platform.platform(),
        "system": platform.system(), "machine": platform.machine(),
        "processor": _cpu_model(), "logical_cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "mpi_ranks": _env_int("OMPI_COMM_WORLD_SIZE", "PMI_SIZE"),
        "threads": _env_int("OMP_NUM_THREADS"), "physics_realpath": str(exe),
    }


def run_measurement(manifest_path: Path, *, executable: str | Path | None = None, out_dir: Path | None = None) -> int:
    manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = validate_experiment_manifest(json.loads(manifest_path.read_text()))
    case = manifest["case"]
    case_dir = Path(case["directory"]).expanduser()
    case_dir = ((manifest_path.parent / case_dir).resolve() if not case_dir.is_absolute() else case_dir.resolve())
    if not case_dir.is_dir():
        raise PerformanceContractError(f"case directory does not exist: {case_dir}")
    input_path = (case_dir / case["input"]).resolve()
    if case_dir not in input_path.parents and input_path.parent != case_dir:
        raise PerformanceContractError("case input must resolve inside case directory")
    if not input_path.is_file():
        raise PerformanceContractError(f"case input does not exist: {input_path}")
    exe = resolve_executable(executable); validate_executable(exe)
    mode = manifest["mode"]
    num_steps = int(manifest.get("runtime", {}).get("num_steps", 1))
    collectors = manifest.get("collectors", {})
    prefix = _safe_token(manifest.get("overlay_prefix", "physicsperf"))
    try:
        check_overlay_collisions(input_path, prefix)
    except MoosePerformanceDecodeError as exc:
        raise PerformanceContractError(str(exc)) from exc
    if out_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = case_dir / "performance_evidence" / f"{_safe_token(manifest['case_id'])}_{mode.lower()}_{stamp}"
    out_dir = Path(out_dir).expanduser().resolve(); ensure_fresh_directory(out_dir)
    metrics_base = out_dir / "metrics"
    perfgraph_base = out_dir / "perfgraph" if mode == "PROFILE" and collectors.get("perfgraph", True) else None
    petsc_path = out_dir / "petsc_log.csv" if mode == "PROFILE" and collectors.get("petsc_log", True) else None
    overlay = out_dir / "measurement_overlay.i"; p2_log = out_dir / "p2_check_input.log"; p3_log = out_dir / "p3_run.log"
    write_measurement_overlay(overlay, metrics_base=metrics_base, perfgraph_base=perfgraph_base, prefix=prefix)
    common = [str(overlay), f"Executioner/num_steps={num_steps}"]
    p2 = run_physics(exe, cwd=case_dir, input_name=case["input"], log_path=p2_log, extra_args=[*common, "--check-input"])
    p3 = None
    if p2.returncode == 0:
        p3_args = [*common]
        if petsc_path is not None:
            p3_args.extend(log_view_args(petsc_path))
        p3 = run_physics(exe, cwd=case_dir, input_name=case["input"], log_path=p3_log, extra_args=p3_args, stream=bool(manifest.get("stream_output", True)))
    metrics_csv = find_output(metrics_base, ".csv")
    perfgraph_json = find_output(perfgraph_base, ".json")
    metrics = read_last_metrics_row(metrics_csv)
    try:
        perfgraph = collect_perfgraph_json(perfgraph_json, reporter_name=f"{prefix}_perf_graph" if perfgraph_json else None)
    except MoosePerformanceDecodeError as exc:
        raise PerformanceContractError(str(exc)) from exc
    petsc = collect_log_view_csv(petsc_path)
    log_path = p3_log if p3_log.is_file() else p2_log
    log_text = log_path.read_text(errors="replace")
    framework = parse_framework_identity(log_text); problem_log = parse_problem_identity(log_text)
    status = "HARNESS_OR_CONSTRUCTION_FAIL" if p2.returncode != 0 else ("RUNTIME_FAIL_OR_NONCONVERGENCE" if p3 is None or p3.returncode != 0 else "P2_PASS_P3_PASS")
    environment = _collect_environment(exe); environment.update(framework)
    dofs = metric_int(metrics, prefix, "num_dofs")
    result = {
        "schema_version": SCHEMA_VERSION, "run_id": out_dir.name,
        "experiment_id": manifest["experiment_id"], "case_id": manifest["case_id"], "mode": mode,
        "identity": {"input_sha256": sha256_file(input_path), "physics_realpath": str(exe), "executable_sha256": sha256_file(exe), "manifest_sha256": sha256_file(manifest_path), "overlay_sha256": sha256_file(overlay)},
        "environment": environment,
        "problem": {"nodes": problem_log.get("nodes"), "elements": problem_log.get("elements"), "dofs": dofs if dofs is not None else problem_log.get("dofs"), "variables": problem_log.get("variables"), "species": manifest.get("physics", {}).get("species")},
        "work": {"nonlinear_iterations": metric_int(metrics, prefix, "nonlinear_iterations"), "linear_iterations": metric_int(metrics, prefix, "linear_iterations"), "residual_evaluations": metric_int(metrics, prefix, "residual_evaluations"), "jacobian_evaluations": jacobian_evaluation_count(petsc)},
        "performance": {"wall_seconds": p3.wall_seconds if p3 is not None else None, "max_memory_mb": max_memory_mb(perfgraph), "perfgraph": perfgraph, "petsc": petsc},
        "validation": {"status": status, "p2_returncode": p2.returncode, "p3_returncode": p3.returncode if p3 is not None else None, "physics_parameters_changed": False, "solver_tolerances_changed": False, "bounded_num_steps_override": num_steps},
        "evidence": {"manifest": str(manifest_path), "overlay": str(overlay), "p2_log": str(p2_log), "p3_log": str(p3_log) if p3_log.exists() else None, "metrics_csv": str(metrics_csv) if metrics_csv else None, "perfgraph_json": str(perfgraph_json) if perfgraph_json else None, "petsc_csv": str(petsc_path) if petsc_path and petsc_path.is_file() else None},
    }
    validate_result_record(result)
    result_path = out_dir / "result.json"; result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"PERFORMANCE_RESULT: {status}"); print(f"RESULT_JSON: {result_path}")
    return 0 if status == "P2_PASS_P3_PASS" else (p2.returncode or (p3.returncode if p3 else 2) or 2)


def analyze_profile(summary_path: Path, petsc_log_path: Path, perf_log_path: Path | None = None, *, metric_prefix: str | None = None) -> dict[str, Any]:
    return analyze_facts(
        json.loads(Path(summary_path).read_text()),
        decode_timing_facts(Path(petsc_log_path)),
        jacobian_self_time(Path(perf_log_path)) if perf_log_path else None,
        metric_prefix=metric_prefix,
    )


def self_test() -> int:
    profile = {"schema_version": 1, "experiment_id": "pf1-selftest", "case_id": "synthetic", "mode": "PROFILE", "case": {"directory": ".", "input": "input.i"}, "runtime": {"num_steps": 1}, "collectors": {"work_counters": True, "perfgraph": True, "petsc_log": True}}
    validate_experiment_manifest(profile)
    mutation = json.loads(json.dumps(profile)); mutation["mode"] = "UNKNOWN"
    try:
        validate_experiment_manifest(mutation)
    except PerformanceContractError:
        pass
    else:
        print("PF1_MUTATION_invalid_mode: MISSED"); return 1
    result = {"schema_version": 1, "run_id": "run", "experiment_id": "exp", "case_id": "case", "mode": "PROFILE", "identity": {"input_sha256": "a", "physics_realpath": "/tmp/physics-opt", "executable_sha256": "b"}, "environment": {"hostname": "host", "platform": "linux", "python": "3.12"}, "problem": {"nodes": 1, "elements": 1, "dofs": 2, "variables": ["u"], "species": None}, "work": {"nonlinear_iterations": 1, "linear_iterations": 1, "residual_evaluations": 2, "jacobian_evaluations": 1}, "performance": {"wall_seconds": 1.0, "max_memory_mb": 10.0, "perfgraph": {}, "petsc": {}}, "validation": {"status": "P2_PASS_P3_PASS", "p2_returncode": 0, "p3_returncode": 0}, "evidence": {}}
    validate_result_record(result)
    stats = build_measurement_stats(result)
    if stats.common.case_id != "case" or stats.efficiency is None or stats.efficiency.jacobian_evaluations != 1:
        print("PF1_STATS_MAPPING_SELFTEST: FAIL"); return 1
    print("PHYSICS_PERFORMANCE_APPLICATION_SELFTEST: PASS"); return 0


__all__ = ["PerformanceContractError", "analyze_profile", "build_measurement_stats", "result_status", "run_measurement", "self_test", "validate_experiment_manifest", "validate_result_record"]
