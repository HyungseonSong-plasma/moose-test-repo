"""Reusable QPX/MOOSE performance measurement core.

PF-1 owns measurement construction and normalization only. Regression policy,
statistical thresholds, matrix generation, and bottleneck classification belong
in successor work packages.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .evidence import ensure_fresh_directory, sha256_file
from .runtime import resolve_executable, run_qpx, validate_executable

SCHEMA_VERSION = 1
VALID_MODES = {"BENCHMARK", "PROFILE"}
RESULT_STATUSES = {
    "P2_PASS_P3_PASS",
    "HARNESS_OR_CONSTRUCTION_FAIL",
    "RUNTIME_FAIL_OR_NONCONVERGENCE",
}


class PerformanceContractError(ValueError):
    """Raised when a PF-1 manifest/result violates the measurement contract."""


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
        raise PerformanceContractError(
            "BENCHMARK mode cannot enable PerfGraph/PETSc deep collectors"
        )
    if mode == "PROFILE" and not (perfgraph or petsc_log):
        raise PerformanceContractError(
            "PROFILE mode must enable at least one deep collector"
        )
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
    for key in ("input_sha256", "qpx_realpath", "executable_sha256"):
        _string(identity, key, "result.identity")

    environment = _mapping(root.get("environment"), "result.environment")
    for key in ("hostname", "platform", "python"):
        _string(environment, key, "result.environment")

    problem = _mapping(root.get("problem"), "result.problem")
    for key in ("nodes", "elements", "dofs"):
        _nonnegative_int(problem, key, "result.problem")
    for key in ("variables", "species"):
        value = problem.get(key)
        if value is not None and (
            not isinstance(value, list) or not all(isinstance(v, str) for v in value)
        ):
            raise PerformanceContractError(f"result.problem.{key} must be string array or null")

    work = _mapping(root.get("work"), "result.work")
    for key in (
        "nonlinear_iterations",
        "linear_iterations",
        "residual_evaluations",
        "jacobian_evaluations",
    ):
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
        raise PerformanceContractError(
            f"result.validation.status must be one of {sorted(RESULT_STATUSES)}"
        )
    for key in ("p2_returncode", "p3_returncode"):
        value = validation.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise PerformanceContractError(f"result.validation.{key} must be integer or null")
    _mapping(root.get("evidence"), "result.evidence")
    return root


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "case"


def _quote(path: Path) -> str:
    text = str(path)
    if "'" in text:
        raise PerformanceContractError(f"output path contains unsupported single quote: {path}")
    return f"'{text}'"


def write_measurement_overlay(
    path: Path,
    *,
    metrics_base: Path,
    perfgraph_base: Path | None,
    prefix: str = "qpxperf",
) -> None:
    """Write diagnostics-only MOOSE objects for BENCHMARK/PROFILE measurement."""

    if perfgraph_base is not None:
        outputs = f"""
[Reporters]
  [{prefix}_perf_graph]
    type = PerfGraphReporter
    execute_on = FINAL
  []
[]

[Outputs]
  [{prefix}_perf_json]
    type = JSON
    execute_on = FINAL
    file_base = {_quote(perfgraph_base)}
  []
  [{prefix}_metrics]
    type = CSV
    file_base = {_quote(metrics_base)}
    show = '{prefix}_num_dofs {prefix}_nonlinear_iterations {prefix}_linear_iterations {prefix}_residual_evaluations'
    execute_on = 'initial timestep_end'
  []
[]
"""
    else:
        outputs = f"""
[Outputs]
  [{prefix}_metrics]
    type = CSV
    file_base = {_quote(metrics_base)}
    show = '{prefix}_num_dofs {prefix}_nonlinear_iterations {prefix}_linear_iterations {prefix}_residual_evaluations'
    execute_on = 'initial timestep_end'
  []
[]
"""

    path.write_text(
        f"""# Generated QPX performance measurement overlay.
# Diagnostics only: no physics coefficient, dt, tolerance, BC, or solver change.

[Postprocessors]
  [{prefix}_num_dofs]
    type = NumDOFs
    system = NL
    execute_on = 'initial timestep_end'
  []
  [{prefix}_nonlinear_iterations]
    type = NumNonlinearIterations
    execute_on = timestep_end
  []
  [{prefix}_linear_iterations]
    type = NumLinearIterations
    execute_on = timestep_end
  []
  [{prefix}_residual_evaluations]
    type = NumResidualEvaluations
    execute_on = timestep_end
  []
[]
{outputs}"""
    )


def _find_output(base: Path, suffix: str) -> Path | None:
    direct = Path(str(base) + suffix)
    if direct.is_file():
        return direct
    matches = sorted(base.parent.glob(base.name + "*" + suffix))
    return matches[0] if matches else None


def read_last_metrics_row(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[-1] if rows else {}


def _number(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    text = value.strip()
    try:
        if re.fullmatch(r"[+-]?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return value


def collect_petsc_csv(path: Path | None) -> dict[str, Any] | None:
    """Capture PETSc log_view CSV rows without assigning bottleneck semantics."""

    if path is None or not path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if any(value not in (None, "") for value in row.values()):
                rows.append({k: _number(v) for k, v in row.items() if k is not None})
    return {"format": "petsc_log_view_ascii_csv", "rows": rows}


def _reporter_name(payload: dict[str, Any], preferred: str | None) -> str:
    reporters = _mapping(payload.get("reporters"), "perfgraph.reporters")
    names = [
        name
        for name, meta in reporters.items()
        if isinstance(meta, dict) and meta.get("type") == "PerfGraphReporter"
    ]
    if preferred is not None:
        if preferred not in names:
            raise PerformanceContractError(
                f"requested PerfGraphReporter {preferred!r} not found; present={names}"
            )
        return preferred
    if len(names) != 1:
        raise PerformanceContractError(f"expected one PerfGraphReporter, found {len(names)}")
    return names[0]


def _flatten_node(
    name: str,
    node: dict[str, Any],
    *,
    version: int,
    parent: str | None,
    rows: list[dict[str, Any]],
) -> None:
    for key in ("level", "time", "num_calls"):
        if key not in node:
            raise PerformanceContractError(f"PerfGraph node {name!r} missing {key}")
    rows.append(
        {
            "name": name,
            "parent": parent,
            "level": int(node["level"]),
            "self_seconds": float(node["time"]),
            "num_calls": int(node["num_calls"]),
        }
    )
    if version == 0:
        reserved = {"level", "time", "num_calls", "memory"}
        children = {k: v for k, v in node.items() if k not in reserved}
    else:
        children = node.get("children", {})
    if not isinstance(children, dict):
        raise PerformanceContractError(f"PerfGraph node {name!r} children must be an object")
    for child_name, child in children.items():
        if not isinstance(child, dict):
            raise PerformanceContractError(f"PerfGraph child {child_name!r} must be an object")
        _flatten_node(child_name, child, version=version, parent=name, rows=rows)


def collect_perfgraph_json(
    path: Path | None, *, reporter_name: str | None = None
) -> dict[str, Any] | None:
    """Normalize MOOSE PerfGraphReporter JSON while retaining raw hierarchy semantics."""

    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text())
    name = _reporter_name(payload, reporter_name)
    steps = payload.get("time_steps")
    if not isinstance(steps, list) or not steps:
        raise PerformanceContractError("PerfGraphReporter JSON has no time_steps")
    step = _mapping(steps[-1], "perfgraph.time_steps[-1]")
    reporter = _mapping(step.get(name), f"perfgraph.time_steps[-1].{name}")
    graph = reporter.get("graph")
    if not isinstance(graph, dict) or len(graph) != 1:
        raise PerformanceContractError("PerfGraphReporter graph must have exactly one root")
    version = reporter.get("version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise PerformanceContractError("PerfGraphReporter version must be non-negative integer")
    root_name, root = next(iter(graph.items()))
    if not isinstance(root, dict):
        raise PerformanceContractError("PerfGraph root node must be an object")
    nodes: list[dict[str, Any]] = []
    _flatten_node(root_name, root, version=version, parent=None, rows=nodes)
    return {
        "format": "moose_perfgraph_reporter_json",
        "version": version,
        "time": step.get("time"),
        "time_step": step.get("time_step"),
        "max_memory_this_rank_mb": reporter.get("max_memory_this_rank"),
        "max_memory_per_rank_mb": reporter.get("max_memory_per_rank"),
        "nodes": nodes,
    }


def parse_framework_identity(text: str) -> dict[str, str | None]:
    patterns = {
        "moose": r"^MOOSE Version:\s*(.+?)\s*$",
        "libmesh": r"^LibMesh Version:\s*(.*?)\s*$",
        "petsc": r"^PETSc Version:\s*(.+?)\s*$",
        "slepc": r"^SLEPc Version:\s*(.+?)\s*$",
    }
    result: dict[str, str | None] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.MULTILINE)
        result[key] = match.group(1).strip() if match and match.group(1).strip() else None
    return result


def parse_problem_identity(text: str) -> dict[str, Any]:
    def integer(pattern: str) -> int | None:
        match = re.search(pattern, text, re.MULTILINE)
        return int(match.group(1)) if match else None

    variables = None
    match = re.search(r'^\s*Variables:\s*\{\s*(.*?)\s*\}\s*$', text, re.MULTILINE)
    if match:
        variables = re.findall(r'"([^"]+)"', match.group(1))
    return {
        "nodes": integer(r"^\s*Nodes:\s*(\d+)\s*$"),
        "elements": integer(r"^\s*Elems:\s*(\d+)\s*$"),
        "dofs": integer(r"^\s*Num DOFs:\s*(\d+)\s*$"),
        "variables": variables,
    }


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
        match = re.search(
            r"^model name\s*:\s*(.+)$", cpuinfo.read_text(errors="replace"), re.MULTILINE
        )
        if match:
            return match.group(1).strip()
    return None


def collect_environment(exe: Path) -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": _cpu_model(),
        "logical_cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "mpi_ranks": _env_int("OMPI_COMM_WORLD_SIZE", "PMI_SIZE"),
        "threads": _env_int("OMP_NUM_THREADS"),
        "qpx_realpath": str(exe),
    }


def _metric_int(metrics: dict[str, str], prefix: str, stem: str) -> int | None:
    value = metrics.get(f"{prefix}_{stem}")
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _jacobian_count(petsc: dict[str, Any] | None) -> int | None:
    if not petsc:
        return None
    for row in petsc.get("rows", []):
        if row.get("Event Name") == "SNESJacobianEval" and row.get("Rank") in (None, "", 0, "0"):
            count = row.get("Count")
            if isinstance(count, (int, float)):
                return int(count)
    return None


def _max_memory(perfgraph: dict[str, Any] | None) -> float | None:
    if not perfgraph:
        return None
    value = perfgraph.get("max_memory_this_rank_mb")
    if isinstance(value, (int, float)):
        return float(value)
    values = perfgraph.get("max_memory_per_rank_mb")
    if isinstance(values, list) and values and all(isinstance(v, (int, float)) for v in values):
        return float(max(values))
    return None


def _check_overlay_collisions(input_path: Path, prefix: str) -> None:
    text = input_path.read_text(errors="replace")
    names = [
        f"{prefix}_num_dofs",
        f"{prefix}_nonlinear_iterations",
        f"{prefix}_linear_iterations",
        f"{prefix}_residual_evaluations",
        f"{prefix}_perf_graph",
        f"{prefix}_perf_json",
        f"{prefix}_metrics",
    ]
    collisions = [
        name for name in names if re.search(rf"\[(?:\./)?{re.escape(name)}\]", text)
    ]
    if collisions:
        raise PerformanceContractError(
            "input already defines reserved performance names: " + ", ".join(collisions)
        )


def run_measurement(
    manifest_path: Path,
    *,
    executable: str | Path | None = None,
    out_dir: Path | None = None,
) -> int:
    manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = validate_experiment_manifest(json.loads(manifest_path.read_text()))
    case = manifest["case"]
    case_dir = Path(case["directory"]).expanduser()
    case_dir = (
        (manifest_path.parent / case_dir).resolve()
        if not case_dir.is_absolute()
        else case_dir.resolve()
    )
    if not case_dir.is_dir():
        raise PerformanceContractError(f"case directory does not exist: {case_dir}")
    input_path = (case_dir / case["input"]).resolve()
    if case_dir not in input_path.parents and input_path.parent != case_dir:
        raise PerformanceContractError("case input must resolve inside case directory")
    if not input_path.is_file():
        raise PerformanceContractError(f"case input does not exist: {input_path}")

    exe = resolve_executable(executable)
    validate_executable(exe)
    mode = manifest["mode"]
    num_steps = int(manifest.get("runtime", {}).get("num_steps", 1))
    collectors = manifest.get("collectors", {})
    prefix = _safe_token(manifest.get("overlay_prefix", "qpxperf"))
    _check_overlay_collisions(input_path, prefix)

    if out_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = case_dir / "performance_evidence" / (
            f"{_safe_token(manifest['case_id'])}_{mode.lower()}_{stamp}"
        )
    out_dir = Path(out_dir).expanduser().resolve()
    ensure_fresh_directory(out_dir)

    metrics_base = out_dir / "metrics"
    perfgraph_base = (
        out_dir / "perfgraph"
        if mode == "PROFILE" and collectors.get("perfgraph", True)
        else None
    )
    petsc_path = (
        out_dir / "petsc_log.csv"
        if mode == "PROFILE" and collectors.get("petsc_log", True)
        else None
    )
    overlay = out_dir / "measurement_overlay.i"
    p2_log = out_dir / "p2_check_input.log"
    p3_log = out_dir / "p3_run.log"
    write_measurement_overlay(
        overlay, metrics_base=metrics_base, perfgraph_base=perfgraph_base, prefix=prefix
    )

    common = [str(overlay), f"Executioner/num_steps={num_steps}"]
    p2 = run_qpx(
        exe,
        cwd=case_dir,
        input_name=case["input"],
        log_path=p2_log,
        extra_args=[*common, "--check-input"],
    )
    p3 = None
    if p2.returncode == 0:
        p3_args = [*common]
        if petsc_path is not None:
            p3_args += ["-log_view", f":{petsc_path}:ascii_csv"]
        p3 = run_qpx(
            exe,
            cwd=case_dir,
            input_name=case["input"],
            log_path=p3_log,
            extra_args=p3_args,
            stream=bool(manifest.get("stream_output", True)),
        )

    metrics_csv = _find_output(metrics_base, ".csv")
    perfgraph_json = _find_output(perfgraph_base, ".json") if perfgraph_base else None
    metrics = read_last_metrics_row(metrics_csv)
    perfgraph = collect_perfgraph_json(
        perfgraph_json,
        reporter_name=f"{prefix}_perf_graph" if perfgraph_json else None,
    )
    petsc = collect_petsc_csv(petsc_path)
    log_path = p3_log if p3_log.is_file() else p2_log
    log_text = log_path.read_text(errors="replace")
    framework = parse_framework_identity(log_text)
    problem_log = parse_problem_identity(log_text)

    if p2.returncode != 0:
        status = "HARNESS_OR_CONSTRUCTION_FAIL"
    elif p3 is None or p3.returncode != 0:
        status = "RUNTIME_FAIL_OR_NONCONVERGENCE"
    else:
        status = "P2_PASS_P3_PASS"

    environment = collect_environment(exe)
    environment.update(framework)
    dofs = _metric_int(metrics, prefix, "num_dofs")
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": out_dir.name,
        "experiment_id": manifest["experiment_id"],
        "case_id": manifest["case_id"],
        "mode": mode,
        "identity": {
            "input_sha256": sha256_file(input_path),
            "qpx_realpath": str(exe),
            "executable_sha256": sha256_file(exe),
            "manifest_sha256": sha256_file(manifest_path),
            "overlay_sha256": sha256_file(overlay),
        },
        "environment": environment,
        "problem": {
            "nodes": problem_log.get("nodes"),
            "elements": problem_log.get("elements"),
            "dofs": dofs if dofs is not None else problem_log.get("dofs"),
            "variables": problem_log.get("variables"),
            "species": manifest.get("physics", {}).get("species"),
        },
        "work": {
            "nonlinear_iterations": _metric_int(metrics, prefix, "nonlinear_iterations"),
            "linear_iterations": _metric_int(metrics, prefix, "linear_iterations"),
            "residual_evaluations": _metric_int(metrics, prefix, "residual_evaluations"),
            "jacobian_evaluations": _jacobian_count(petsc),
        },
        "performance": {
            "wall_seconds": p3.wall_seconds if p3 is not None else None,
            "max_memory_mb": _max_memory(perfgraph),
            "perfgraph": perfgraph,
            "petsc": petsc,
        },
        "validation": {
            "status": status,
            "p2_returncode": p2.returncode,
            "p3_returncode": p3.returncode if p3 is not None else None,
            "physics_parameters_changed": False,
            "solver_tolerances_changed": False,
            "bounded_num_steps_override": num_steps,
        },
        "evidence": {
            "manifest": str(manifest_path),
            "overlay": str(overlay),
            "p2_log": str(p2_log),
            "p3_log": str(p3_log) if p3_log.exists() else None,
            "metrics_csv": str(metrics_csv) if metrics_csv else None,
            "perfgraph_json": str(perfgraph_json) if perfgraph_json else None,
            "petsc_csv": str(petsc_path) if petsc_path and petsc_path.is_file() else None,
        },
    }
    validate_result_record(result)
    result_path = out_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"PERFORMANCE_RESULT: {status}")
    print(f"RESULT_JSON: {result_path}")
    return 0 if status == "P2_PASS_P3_PASS" else (p2.returncode or (p3.returncode if p3 else 2) or 2)


def self_test() -> int:
    profile = {
        "schema_version": 1,
        "experiment_id": "pf1-selftest",
        "case_id": "synthetic",
        "mode": "PROFILE",
        "case": {"directory": ".", "input": "input.i"},
        "runtime": {"num_steps": 1},
        "collectors": {"work_counters": True, "perfgraph": True, "petsc_log": True},
    }
    validate_experiment_manifest(profile)
    mutations = []
    mutation = json.loads(json.dumps(profile)); mutation["mode"] = "UNKNOWN"
    mutations.append(("invalid_mode", mutation))
    mutation = json.loads(json.dumps(profile)); mutation["mode"] = "BENCHMARK"
    mutations.append(("benchmark_deep_collector", mutation))
    mutation = json.loads(json.dumps(profile)); del mutation["case"]["input"]
    mutations.append(("missing_input", mutation))
    mutation = json.loads(json.dumps(profile)); mutation["collectors"] = {"perfgraph": False, "petsc_log": False}
    mutations.append(("profile_without_deep_collector", mutation))
    for name, mutation in mutations:
        try:
            validate_experiment_manifest(mutation)
        except PerformanceContractError:
            pass
        else:
            print(f"PF1_MUTATION_{name}: MISSED")
            return 1

    schema_root = Path(__file__).resolve().parents[1] / "performance" / "schema"
    for schema_name in ("experiment.schema.json", "result.schema.json"):
        schema_path = schema_root / schema_name
        if not schema_path.is_file():
            print(f"PF1_SCHEMA_MISSING: {schema_path}")
            return 1
        schema = json.loads(schema_path.read_text())
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            print(f"PF1_SCHEMA_DRAFT_FAIL: {schema_name}")
            return 1

    synthetic_perf = {
        "reporters": {"perf_graph": {"type": "PerfGraphReporter", "values": {}}},
        "time_steps": [{
            "perf_graph": {
                "graph": {"app": {"level": 0, "time": 0.25, "num_calls": 1,
                    "children": {"solve": {"level": 1, "time": 0.10, "num_calls": 2}}}},
                "version": 1,
                "max_memory_this_rank": 128,
                "max_memory_per_rank": [128]
            },
            "time": 1.0,
            "time_step": 1
        }]
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        perf_path = root / "perf.json"
        perf_path.write_text(json.dumps(synthetic_perf))
        perf = collect_perfgraph_json(perf_path)
        if perf is None or len(perf["nodes"]) != 2 or perf["max_memory_this_rank_mb"] != 128:
            print("PF1_PERFGRAPH_SELFTEST: FAIL")
            return 1
        petsc_path = root / "petsc.csv"
        petsc_path.write_text("Event Name,Rank,Count,Time\nSNESJacobianEval,0,3,1.25\n")
        petsc = collect_petsc_csv(petsc_path)
        if petsc is None or _jacobian_count(petsc) != 3:
            print("PF1_PETSC_SELFTEST: FAIL")
            return 1

    result = {
        "schema_version": 1,
        "run_id": "run",
        "experiment_id": "exp",
        "case_id": "case",
        "mode": "PROFILE",
        "identity": {"input_sha256": "a", "qpx_realpath": "/tmp/qpx-opt", "executable_sha256": "b"},
        "environment": {"hostname": "host", "platform": "linux", "python": "3.12"},
        "problem": {"nodes": 1, "elements": 1, "dofs": 2, "variables": ["u"], "species": None},
        "work": {"nonlinear_iterations": 1, "linear_iterations": 1, "residual_evaluations": 2, "jacobian_evaluations": 1},
        "performance": {"wall_seconds": 1.0, "max_memory_mb": 10.0, "perfgraph": {}, "petsc": {}},
        "validation": {"status": "P2_PASS_P3_PASS", "p2_returncode": 0, "p3_returncode": 0},
        "evidence": {},
    }
    validate_result_record(result)
    del result["identity"]
    try:
        validate_result_record(result)
    except PerformanceContractError:
        pass
    else:
        print("PF1_MUTATION_missing_identity: MISSED")
        return 1
    print("QPX_PERFORMANCE_CORE_SELFTEST: PASS")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx measure")
    parser.add_argument("manifest", nargs="?")
    parser.add_argument("--qpx")
    parser.add_argument("--out-dir")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.self_test:
        return self_test()
    if not args.manifest:
        parser.error("manifest is required unless --self-test is used")
    try:
        return run_measurement(
            Path(args.manifest),
            executable=args.qpx,
            out_dir=Path(args.out_dir) if args.out_dir else None,
        )
    except PerformanceContractError as exc:
        print(f"PERFORMANCE_CONTRACT_FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
