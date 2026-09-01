"""EfficiencyStats mapping from normalized performance facts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .._coerce import as_mapping, optional_float, optional_int
from ...models.stats import EfficiencyStats, MemoryStats, TimingStats


def _perfgraph_timings(perfgraph: Mapping[str, Any]) -> list[TimingStats]:
    rows: list[TimingStats] = []
    nodes = perfgraph.get("nodes")
    if not isinstance(nodes, list):
        return rows
    for node in nodes:
        if not isinstance(node, Mapping) or not isinstance(node.get("name"), str):
            continue
        rows.append(
            TimingStats(
                name=node["name"],
                source="moose_perfgraph",
                self_seconds=optional_float(node.get("self_seconds")),
                call_count=optional_int(
                    node.get("num_calls")
                    if node.get("num_calls") is not None
                    else node.get("call_count")
                ),
                parent=node.get("parent") if isinstance(node.get("parent"), str) else None,
                level=optional_int(node.get("level")),
            )
        )
    return rows


def _petsc_timings(petsc: Mapping[str, Any]) -> list[TimingStats]:
    rows: list[TimingStats] = []
    events = petsc.get("rows")
    if not isinstance(events, list):
        return rows
    for event in events:
        if not isinstance(event, Mapping):
            continue
        name = event.get("Event Name")
        if not isinstance(name, str) or not name or name == "summary":
            continue
        rows.append(
            TimingStats(
                name=name,
                source="petsc_log",
                call_count=optional_int(event.get("Count")),
                rank=optional_int(event.get("Rank")),
                total_seconds=optional_float(event.get("Time")),
            )
        )
    return rows


def _memory_stats(perfgraph: Mapping[str, Any]) -> list[MemoryStats]:
    rows: list[MemoryStats] = []
    this_rank = optional_float(perfgraph.get("max_memory_this_rank_mb"))
    if this_rank is not None:
        rows.append(
            MemoryStats(
                kind="max_memory_this_rank",
                value=this_rank,
                unit="MB",
                source="moose_perfgraph",
            )
        )
    per_rank = perfgraph.get("max_memory_per_rank_mb")
    if isinstance(per_rank, list):
        for rank, value in enumerate(per_rank):
            number = optional_float(value)
            if number is not None:
                rows.append(
                    MemoryStats(
                        kind="max_memory_per_rank",
                        value=number,
                        unit="MB",
                        source="moose_perfgraph",
                        rank=rank,
                    )
                )
    return rows


def build_efficiency_stats(record: Mapping[str, Any]) -> EfficiencyStats | None:
    """Build work/timing/resource facts from a performance-style result record."""

    work = as_mapping(record.get("work"))
    performance = as_mapping(record.get("performance"))
    perfgraph = as_mapping(performance.get("perfgraph"))
    petsc = as_mapping(performance.get("petsc"))
    timings = (*_perfgraph_timings(perfgraph), *_petsc_timings(petsc))
    memories = tuple(_memory_stats(perfgraph))
    peak_rss_bytes = optional_int(performance.get("peak_rss_bytes"))
    residual_evaluations = optional_int(work.get("residual_evaluations"))
    jacobian_evaluations = optional_int(work.get("jacobian_evaluations"))
    if (
        peak_rss_bytes is None
        and residual_evaluations is None
        and jacobian_evaluations is None
        and not timings
        and not memories
    ):
        return None
    return EfficiencyStats(
        peak_rss_bytes=peak_rss_bytes,
        residual_evaluations=residual_evaluations,
        jacobian_evaluations=jacobian_evaluations,
        timings=tuple(timings),
        memories=memories,
    )


def self_test() -> int:
    try:
        stats = build_efficiency_stats(
            {
                "work": {
                    "residual_evaluations": 5,
                    "jacobian_evaluations": 2,
                },
                "performance": {
                    "peak_rss_bytes": 4096,
                    "perfgraph": {
                        "max_memory_this_rank_mb": 128.0,
                        "max_memory_per_rank_mb": [128.0, 96.0],
                        "nodes": [
                            {
                                "name": "app",
                                "parent": None,
                                "level": 0,
                                "self_seconds": 0.25,
                                "num_calls": 1,
                            }
                        ],
                    },
                    "petsc": {
                        "rows": [
                            {
                                "Event Name": "SNESJacobianEval",
                                "Rank": 0,
                                "Count": 2,
                                "Time": 0.4,
                            }
                        ]
                    },
                },
            }
        )
        if stats is None:
            raise AssertionError("representative efficiency facts produced None")
        if (
            stats.peak_rss_bytes != 4096
            or stats.residual_evaluations != 5
            or stats.jacobian_evaluations != 2
            or len(stats.timings) != 2
            or len(stats.memories) != 3
        ):
            raise AssertionError("EfficiencyStats mapping drifted")
        if not any(
            row.source == "petsc_log" and row.total_seconds == 0.4
            for row in stats.timings
        ):
            raise AssertionError("PETSc timing mapping drifted")
        if build_efficiency_stats({}) is not None:
            raise AssertionError("empty facts invented EfficiencyStats")
    except Exception as exc:
        print(f"QPX_EFFICIENCY_STATS_MAPPING_SELFTEST: FAIL ({exc})")
        return 1

    print("QPX_EFFICIENCY_STATS_MAPPING_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
