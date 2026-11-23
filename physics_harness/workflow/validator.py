"""Fail-closed validation of case plans, rendered workflows and trusted scripts."""
from __future__ import annotations

import math
from pathlib import Path, PurePosixPath
import re

SHA = re.compile(r"[a-f0-9]{40}\Z")
OCI = re.compile(r"[a-zA-Z0-9._/-]+@sha256:[a-f0-9]{64}\Z")
IDENT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}\Z")
NAME = re.compile(r"[a-zA-Z][a-zA-Z0-9 -]{0,79}\Z")
PREFIX = re.compile(r"[a-z][a-z0-9-]{0,59}\Z")
SCRIPT_ROOTS = {"ci", "experiments", "physics_harness"}


class WorkflowValidationError(ValueError):
    pass


def safe_repo_path(raw: str, *, roots: set[str]) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\n" in raw:
        raise WorkflowValidationError("UNSAFE_REPOSITORY_PATH")
    p = PurePosixPath(raw)
    if p.is_absolute() or len(p.parts) < 2 or p.parts[0] not in roots or any(
        x in {".", "..", ""} for x in raw.split("/")
    ) or p.as_posix() != raw:
        raise WorkflowValidationError("UNSAFE_REPOSITORY_PATH")
    return raw


def validate_spec(spec) -> None:
    if type(spec.schema_version) is not int or spec.schema_version != 1:
        raise WorkflowValidationError("SCHEMA_VERSION")
    if not isinstance(spec.name, str) or not NAME.fullmatch(spec.name):
        raise WorkflowValidationError("WORKFLOW_NAME")
    if spec.profile not in {"single_case", "parallel_cases"}:
        raise WorkflowValidationError("EXECUTION_PROFILE")
    if not isinstance(spec.source_sha, str) or not SHA.fullmatch(spec.source_sha):
        raise WorkflowValidationError("SOURCE_SHA")
    if not isinstance(spec.oci_ref, str) or not OCI.fullmatch(spec.oci_ref):
        raise WorkflowValidationError("UNPINNED_OCI")
    if not isinstance(spec.cases, tuple) or not 1 <= len(spec.cases) <= 128:
        raise WorkflowValidationError("CASE_COUNT")
    if any(not isinstance(c.id, str) or not IDENT.fullmatch(c.id) for c in spec.cases):
        raise WorkflowValidationError("CASE_ID")
    if len({c.id for c in spec.cases}) != len(spec.cases):
        raise WorkflowValidationError("DUPLICATE_CASE")
    if spec.profile == "single_case" and len(spec.cases) != 1:
        raise WorkflowValidationError("SINGLE_CASE_CARDINALITY")
    if spec.profile == "parallel_cases" and len(spec.cases) < 2:
        raise WorkflowValidationError("PARALLEL_CASE_CARDINALITY")
    if (type(spec.max_parallel) is not int or not 1 <= spec.max_parallel <= 20
            or spec.max_parallel > len(spec.cases)
            or (spec.profile == "single_case" and spec.max_parallel != 1)):
        raise WorkflowValidationError("PARALLEL_BUDGET")
    if type(spec.timeout_minutes) is not int or not 1 <= spec.timeout_minutes <= 360:
        raise WorkflowValidationError("TIMEOUT_BUDGET")
    if not isinstance(spec.artifact_prefix, str) or not PREFIX.fullmatch(spec.artifact_prefix):
        raise WorkflowValidationError("ARTIFACT_PREFIX")
    if (spec.build_script is None) != (spec.case_script is None):
        raise WorkflowValidationError("INCOMPLETE_EXECUTOR")
    for script in (spec.build_script, spec.case_script):
        if script is not None:
            safe_repo_path(script, roots=SCRIPT_ROOTS)
            if not script.endswith(".py"):
                raise WorkflowValidationError("EXECUTOR_MUST_BE_PYTHON")
    if (spec.end_time_s is None) != (spec.intervals is None):
        raise WorkflowValidationError("TIME_GRID_INCOMPLETE")
    if spec.end_time_s is not None:
        if (type(spec.end_time_s) not in (int, float)
                or not math.isfinite(spec.end_time_s) or not spec.end_time_s > 0
                or type(spec.intervals) is not int or not 1 <= spec.intervals <= 1000000):
            raise WorkflowValidationError("INVALID_TIME_GRID")


def validate_executor_files(spec, root: Path) -> None:
    if not spec.build_script or not spec.case_script:
        raise WorkflowValidationError("EXECUTOR_NOT_CONFIGURED")
    root = root.resolve()
    for script in (spec.build_script, spec.case_script):
        path = (root / script).resolve()
        if not path.is_file() or not path.is_relative_to(root):
            raise WorkflowValidationError("EXECUTOR_NOT_IN_SOURCE")
