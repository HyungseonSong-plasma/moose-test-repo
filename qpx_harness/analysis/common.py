"""Common run, problem, and environment Stats mappings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._coerce import as_mapping, optional_float, optional_int, string_tuple
from ..models.stats import CommonStats, EnvironmentStats, ProblemStats


def build_problem_stats(facts: Mapping[str, Any] | None) -> ProblemStats | None:
    """Map a normalized problem-identity mapping without adding interpretation."""

    if not facts:
        return None
    return ProblemStats(
        nodes=optional_int(facts.get("nodes")),
        elements=optional_int(facts.get("elements")),
        dofs=optional_int(facts.get("dofs")),
        variables=string_tuple(facts.get("variables")),
        species=string_tuple(facts.get("species")),
    )


def build_environment_stats(
    facts: Mapping[str, Any] | None,
) -> EnvironmentStats | None:
    """Map environment/framework identity facts using existing producer names."""

    if not facts:
        return None
    return EnvironmentStats(
        hostname=facts.get("hostname") if isinstance(facts.get("hostname"), str) else None,
        platform=facts.get("platform") if isinstance(facts.get("platform"), str) else None,
        system=facts.get("system") if isinstance(facts.get("system"), str) else None,
        machine=facts.get("machine") if isinstance(facts.get("machine"), str) else None,
        processor=facts.get("processor") if isinstance(facts.get("processor"), str) else None,
        python_version=facts.get("python")
        if isinstance(facts.get("python"), str)
        else (
            facts.get("python_version")
            if isinstance(facts.get("python_version"), str)
            else None
        ),
        mpi_ranks=optional_int(facts.get("mpi_ranks")),
        threads=optional_int(facts.get("threads")),
        qpx_realpath=facts.get("qpx_realpath")
        if isinstance(facts.get("qpx_realpath"), str)
        else None,
        moose_version=facts.get("moose")
        if isinstance(facts.get("moose"), str)
        else (
            facts.get("moose_version")
            if isinstance(facts.get("moose_version"), str)
            else None
        ),
        libmesh_version=facts.get("libmesh")
        if isinstance(facts.get("libmesh"), str)
        else (
            facts.get("libmesh_version")
            if isinstance(facts.get("libmesh_version"), str)
            else None
        ),
        petsc_version=facts.get("petsc")
        if isinstance(facts.get("petsc"), str)
        else (
            facts.get("petsc_version")
            if isinstance(facts.get("petsc_version"), str)
            else None
        ),
        slepc_version=facts.get("slepc")
        if isinstance(facts.get("slepc"), str)
        else (
            facts.get("slepc_version")
            if isinstance(facts.get("slepc_version"), str)
            else None
        ),
        logical_cpu_count=optional_int(facts.get("logical_cpu_count")),
    )


def _runtime_return_code(record: Mapping[str, Any]) -> int | None:
    direct = optional_int(record.get("return_code"))
    if direct is not None:
        return direct
    validation = as_mapping(record.get("validation"))
    p3 = optional_int(validation.get("p3_returncode"))
    if p3 is not None:
        return p3
    return optional_int(validation.get("p2_returncode"))


def build_common_stats(record: Mapping[str, Any]) -> CommonStats:
    """Build common run facts from an existing result-style producer record."""

    performance = as_mapping(record.get("performance"))
    backend = record.get("backend") if isinstance(record.get("backend"), str) else None
    timestamp = (
        record.get("timestamp_iso")
        if isinstance(record.get("timestamp_iso"), str)
        else None
    )
    case_id = record.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("stats builder requires a non-empty case_id")
    return CommonStats(
        case_id=case_id,
        run_id=record.get("run_id") if isinstance(record.get("run_id"), str) else None,
        experiment_id=record.get("experiment_id")
        if isinstance(record.get("experiment_id"), str)
        else None,
        backend=backend,
        return_code=_runtime_return_code(record),
        wall_time_seconds=optional_float(performance.get("wall_seconds")),
        timestamp_iso=timestamp,
        problem=build_problem_stats(as_mapping(record.get("problem"))),
        environment=build_environment_stats(as_mapping(record.get("environment"))),
    )


def build_runtime_common_stats(
    runtime: Mapping[str, Any],
    *,
    case_id: str | None = None,
) -> CommonStats:
    """Map the shared issue-runtime shape into CommonStats through one boundary."""

    resolved_case_id = case_id if case_id is not None else runtime.get("case_id")
    return build_common_stats(
        {
            "case_id": resolved_case_id,
            "return_code": runtime.get("returncode"),
            "performance": {"wall_seconds": runtime.get("wall_seconds")},
        }
    )


def self_test() -> int:
    try:
        common = build_common_stats(
            {
                "run_id": "run-1",
                "experiment_id": "exp-1",
                "case_id": "case-1",
                "backend": "moose",
                "timestamp_iso": "2026-09-01T12:00:00Z",
                "problem": {
                    "nodes": 10,
                    "elements": 8,
                    "dofs": 12,
                    "variables": ["u", "v"],
                    "species": ["O2", "O"],
                },
                "environment": {
                    "hostname": "host",
                    "platform": "linux",
                    "python": "3.12",
                    "mpi_ranks": 2,
                    "threads": 4,
                    "logical_cpu_count": 16,
                    "qpx_realpath": "/opt/qpx-opt",
                    "moose": "moose-v",
                    "petsc": "petsc-v",
                },
                "performance": {"wall_seconds": 1.25},
                "validation": {"p2_returncode": 2, "p3_returncode": 0},
            }
        )
        if (
            common.case_id != "case-1"
            or common.run_id != "run-1"
            or common.experiment_id != "exp-1"
            or common.backend != "moose"
            or common.return_code != 0
            or common.wall_time_seconds != 1.25
            or common.problem is None
            or common.problem.variables != ("u", "v")
            or common.environment is None
            or common.environment.python_version != "3.12"
            or common.environment.logical_cpu_count != 16
        ):
            raise AssertionError("CommonStats mapping semantics drifted")

        runtime = build_runtime_common_stats(
            {"case_id": "runtime-case", "returncode": 3, "wall_seconds": 0.5}
        )
        if (
            runtime.case_id != "runtime-case"
            or runtime.return_code != 3
            or runtime.wall_time_seconds != 0.5
        ):
            raise AssertionError("runtime CommonStats mapping semantics drifted")

        if build_problem_stats(None) is not None:
            raise AssertionError("empty problem facts invented ProblemStats")
        if build_environment_stats(None) is not None:
            raise AssertionError("empty environment facts invented EnvironmentStats")

        try:
            build_common_stats({"run_id": "missing-case"})
        except ValueError:
            pass
        else:
            raise AssertionError("missing case_id was accepted")
    except Exception as exc:
        print(f"QPX_COMMON_STATS_MAPPING_SELFTEST: FAIL ({exc})")
        return 1

    print("QPX_COMMON_STATS_MAPPING_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
