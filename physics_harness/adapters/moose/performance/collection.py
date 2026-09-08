"""MOOSE-specific collection helpers for canonical performance measurement.

Raw HIT/output naming, MOOSE banner parsing, metrics CSV decoding, and
PerfGraphReporter decoding belong here rather than in generic orchestration.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


class MoosePerformanceDecodeError(ValueError):
    pass


def find_output(base: Path | None, suffix: str) -> Path | None:
    if base is None:
        return None
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


def metric_int(metrics: dict[str, str], prefix: str, stem: str) -> int | None:
    value = metrics.get(f"{prefix}_{stem}")
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


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


def check_overlay_collisions(input_path: Path, prefix: str) -> None:
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
        raise MoosePerformanceDecodeError(
            "input already defines reserved performance names: " + ", ".join(collisions)
        )


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MoosePerformanceDecodeError(f"{path} must be an object")
    return value


def _reporter_name(payload: dict[str, Any], preferred: str | None) -> str:
    reporters = _mapping(payload.get("reporters"), "perfgraph.reporters")
    names = [
        name
        for name, meta in reporters.items()
        if isinstance(meta, dict) and meta.get("type") == "PerfGraphReporter"
    ]
    if preferred is not None:
        if preferred not in names:
            raise MoosePerformanceDecodeError(
                f"requested PerfGraphReporter {preferred!r} not found; present={names}"
            )
        return preferred
    if len(names) != 1:
        raise MoosePerformanceDecodeError(
            f"expected one PerfGraphReporter, found {len(names)}"
        )
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
            raise MoosePerformanceDecodeError(f"PerfGraph node {name!r} missing {key}")
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
        children = {key: value for key, value in node.items() if key not in reserved}
    else:
        children = node.get("children", {})
    if not isinstance(children, dict):
        raise MoosePerformanceDecodeError(
            f"PerfGraph node {name!r} children must be an object"
        )
    for child_name, child in children.items():
        if not isinstance(child, dict):
            raise MoosePerformanceDecodeError(
                f"PerfGraph child {child_name!r} must be an object"
            )
        _flatten_node(child_name, child, version=version, parent=name, rows=rows)


def collect_perfgraph_json(
    path: Path | None,
    *,
    reporter_name: str | None = None,
) -> dict[str, Any] | None:
    """Decode measurement PerfGraph JSON preserving the established result shape."""
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text())
    name = _reporter_name(payload, reporter_name)
    steps = payload.get("time_steps")
    if not isinstance(steps, list) or not steps:
        raise MoosePerformanceDecodeError("PerfGraphReporter JSON has no time_steps")
    step = _mapping(steps[-1], "perfgraph.time_steps[-1]")
    reporter = _mapping(step.get(name), f"perfgraph.time_steps[-1].{name}")
    graph = reporter.get("graph")
    if not isinstance(graph, dict) or len(graph) != 1:
        raise MoosePerformanceDecodeError("PerfGraphReporter graph must have exactly one root")
    version = reporter.get("version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise MoosePerformanceDecodeError(
            "PerfGraphReporter version must be non-negative integer"
        )
    root_name, root = next(iter(graph.items()))
    if not isinstance(root, dict):
        raise MoosePerformanceDecodeError("PerfGraph root node must be an object")
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


def max_memory_mb(perfgraph: dict[str, Any] | None) -> float | None:
    if not perfgraph:
        return None
    value = perfgraph.get("max_memory_this_rank_mb")
    if isinstance(value, (int, float)):
        return float(value)
    values = perfgraph.get("max_memory_per_rank_mb")
    if (
        isinstance(values, list)
        and values
        and all(isinstance(item, (int, float)) for item in values)
    ):
        return float(max(values))
    return None


__all__ = [
    "MoosePerformanceDecodeError",
    "check_overlay_collisions",
    "collect_perfgraph_json",
    "find_output",
    "max_memory_mb",
    "metric_int",
    "parse_framework_identity",
    "parse_problem_identity",
    "read_last_metrics_row",
]
