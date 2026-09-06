"""Canonical MOOSE PerfGraph hierarchy traversal and aggregation primitives.

This module parses raw PerfGraphReporter JSON into path-aware timing rows.
It owns hierarchy mechanics only; bottleneck policy and experiment-specific
classification remain with callers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class PerfGraphError(RuntimeError):
    pass


def rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    reporters = payload.get("reporters", {})
    if not isinstance(reporters, dict):
        raise PerfGraphError("PerfGraph reporters must be an object")
    names = [
        name
        for name, meta in reporters.items()
        if isinstance(meta, dict) and meta.get("type") == "PerfGraphReporter"
    ]
    if len(names) != 1:
        raise PerfGraphError(f"expected one PerfGraphReporter, found {len(names)}")

    steps = payload.get("time_steps")
    if not isinstance(steps, list) or not steps:
        raise PerfGraphError("PerfGraph JSON has no time_steps")
    step = steps[-1]
    if not isinstance(step, dict):
        raise PerfGraphError("last PerfGraph time step must be an object")
    reporter = step.get(names[0], {})
    if not isinstance(reporter, dict):
        raise PerfGraphError("PerfGraph reporter payload must be an object")
    graph = reporter.get("graph")
    if not isinstance(graph, dict) or len(graph) != 1:
        raise PerfGraphError("PerfGraph graph must have one root")

    version = reporter.get("version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise PerfGraphError("PerfGraph version must be a non-negative integer")

    rows: list[dict[str, Any]] = []

    def walk(name: str, node: dict[str, Any], ancestors: tuple[str, ...]) -> float:
        try:
            self_seconds = float(node.get("time", 0.0))
            num_calls = int(node.get("num_calls", 0))
        except (TypeError, ValueError) as exc:
            raise PerfGraphError(f"invalid timing node values for {name!r}") from exc

        if version == 0:
            reserved = {"level", "time", "num_calls", "memory"}
            children = {
                key: value
                for key, value in node.items()
                if key not in reserved and isinstance(value, dict)
            }
        else:
            children = node.get("children", {})
            if not isinstance(children, dict):
                children = {}

        child_total = 0.0
        for child_name, child in children.items():
            if isinstance(child, dict):
                child_total += walk(child_name, child, ancestors + (name,))
        inclusive = self_seconds + child_total
        rows.append(
            {
                "name": name,
                "path": list(ancestors + (name,)),
                "self_seconds": self_seconds,
                "inclusive_seconds": inclusive,
                "num_calls": num_calls,
            }
        )
        return inclusive

    root_name, root = next(iter(graph.items()))
    if not isinstance(root, dict):
        raise PerfGraphError("PerfGraph root node must be an object")
    walk(root_name, root, tuple())
    return rows


def read_rows(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise PerfGraphError(f"cannot read PerfGraph JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise PerfGraphError("PerfGraph JSON root must be an object")
    return rows_from_payload(payload)


def sum_timer(
    rows: Iterable[dict[str, Any]],
    timer: str,
    *,
    ancestor_contains: str | None = None,
) -> dict[str, float | int]:
    selected: list[dict[str, Any]] = []
    ancestor_token = ancestor_contains.lower() if ancestor_contains is not None else None
    for row in rows:
        if timer not in str(row.get("name", "")):
            continue
        path = row.get("path", [])
        if not isinstance(path, list):
            raise PerfGraphError("PerfGraph row path must be a list")
        if ancestor_token is not None and not any(
            ancestor_token in str(part).lower() for part in path[:-1]
        ):
            continue
        selected.append(row)
    try:
        return {
            "self_seconds": sum(float(row["self_seconds"]) for row in selected),
            "inclusive_seconds": sum(float(row["inclusive_seconds"]) for row in selected),
            "num_calls": sum(int(row["num_calls"]) for row in selected),
            "node_count": len(selected),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise PerfGraphError("invalid PerfGraph timing row") from exc


def self_test() -> int:
    try:
        payload = {
            "reporters": {"pg": {"type": "PerfGraphReporter"}},
            "time_steps": [
                {
                    "pg": {
                        "version": 1,
                        "graph": {
                            "app": {
                                "time": 1.0,
                                "num_calls": 1,
                                "children": {
                                    "ComputeJacobian": {
                                        "time": 2.0,
                                        "num_calls": 2,
                                        "children": {
                                            "target_timer": {
                                                "time": 3.0,
                                                "num_calls": 4,
                                                "children": {},
                                            }
                                        },
                                    }
                                },
                            }
                        },
                    }
                }
            ],
        }
        rows = rows_from_payload(payload)
        target = sum_timer(rows, "target_timer")
        if target != {
            "self_seconds": 3.0,
            "inclusive_seconds": 3.0,
            "num_calls": 4,
            "node_count": 1,
        }:
            raise AssertionError(target)
        jac = sum_timer(rows, "target_timer", ancestor_contains="jacobian")
        if jac != target:
            raise AssertionError("ancestor filter drift")
        root = next(row for row in rows if row["name"] == "app")
        if root["inclusive_seconds"] != 6.0:
            raise AssertionError("inclusive hierarchy sum drift")

        version0 = {
            "reporters": {"pg": {"type": "PerfGraphReporter"}},
            "time_steps": [{"pg": {"version": 0, "graph": {"app": {
                "level": 0, "time": 1.0, "num_calls": 1,
                "child": {"level": 1, "time": 2.0, "num_calls": 3},
            }}}}],
        }
        rows0 = rows_from_payload(version0)
        if next(row for row in rows0 if row["name"] == "app")["inclusive_seconds"] != 3.0:
            raise AssertionError("version-0 hierarchy drift")

        bad = {"reporters": {}, "time_steps": []}
        try:
            rows_from_payload(bad)
        except PerfGraphError:
            pass
        else:
            raise AssertionError("missing-reporter negative control passed")
    except Exception as exc:
        print(f"PERFGRAPH_SELFTEST: FAIL ({exc})")
        return 1
    print("PERFGRAPH_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
