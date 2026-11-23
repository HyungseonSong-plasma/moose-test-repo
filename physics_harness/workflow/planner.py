"""Execution DAG planning only, separate from GitHub dispatch and physics acceptance."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from physics_harness.workflow.matrix import build_matrix


@dataclass(frozen=True)
class WorkflowPlan:
    workflow: str
    source_sha: str
    oci_ref: str
    profile: str
    jobs: tuple[str, ...]
    matrix: dict
    max_parallel: int
    case_timeout_minutes: int
    shared_build: bool
    case_isolation: bool
    fail_fast: bool
    execution_state: str
    science_state: str


def plan(spec) -> WorkflowPlan:
    return WorkflowPlan(
        workflow=spec.name,
        source_sha=spec.source_sha,
        oci_ref=spec.oci_ref,
        profile=spec.profile,
        jobs=("build", "cases", "aggregate"),
        matrix=build_matrix(spec),
        max_parallel=spec.max_parallel,
        case_timeout_minutes=spec.timeout_minutes,
        shared_build=True,
        case_isolation=True,
        fail_fast=False,
        execution_state="NOT_DISPATCHED",
        science_state="HOLD",
    )


def plan_dict(spec) -> dict:
    return asdict(plan(spec))
