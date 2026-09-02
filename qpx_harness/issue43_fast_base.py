"""Shared base mechanics for the Issue43 fast-plasma runtime."""

from __future__ import annotations

import argparse
import csv
import math
import re
import tempfile
from pathlib import Path
from typing import Any

from recipes import issue43_fast_relaxation as relaxation_recipe

from .evidence import artifacts
from .execution import cases as case_ops
from .execution import contract as ec
from . import evidence
from . import issue43_relaxation_runtime as issue43_runtime
from .moose import output_observation as ooc
from .moose import preflight
from . import scale_audit
from .analysis import temporal
from .moose import executioner as moose_executioner
from .execution.runtime import resolve_executable, run_qpx, validate_executable


# Absorbed v3 CORE-16 ownership. Generic mechanics remain in their canonical
# reusable owners; this module now composes them directly rather than depending
# on a historical version layer.
FastPlasmaV3Error = moose_executioner.MooseExecutionerError
_RAW_BUILD_ELECTRON_300K = issue43_runtime.build_electron_300k
_BASE_BUILD_ONEWAY = issue43_runtime.build_oneway
_BASE_BUILD_FEEDBACK = issue43_runtime.build_feedback
_RAW_RUN_CASE = issue43_runtime.run_case

_RUNTIME_PURGE_DIRECTORY_NAMES = (".jitcache",)
_RUNTIME_PURGE_PATTERNS = (
    "input_out*",
    "r43_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    artifacts.write_json_bundle(
        path.parent,
        {"payload": (path.name, payload)},
    )


def _create_root(results_root: Path) -> Path:
    return evidence.create_collision_safe_directory(
        results_root,
        f"fast_plasma_discriminator_v2_Issue43_{evidence.utc_timestamp()}",
    )


def _stage_case(source: Path, target: Path, input_text: str | None = None) -> None:
    try:
        case_ops.stage_case(
            source,
            target,
            input_text=input_text,
            purge_directory_names=_RUNTIME_PURGE_DIRECTORY_NAMES,
            purge_patterns=_RUNTIME_PURGE_PATTERNS,
        )
    except case_ops.CaseError as exc:
        raise relaxation_recipe.Issue43FastRelaxationError(
            f"case staging failed: {exc}"
        ) from exc


def _validate_assets(case_dir: Path) -> list[str]:
    try:
        refs = case_ops.validate_case_references(case_dir)
    except case_ops.CaseError as exc:
        raise relaxation_recipe.Issue43FastRelaxationError(
            f"asset validation failed: {exc}"
        ) from exc
    return [ref["resolved"] for ref in refs]


def _set_executioner_parameter(text: str, name: str, value: str) -> str:
    return moose_executioner.set_executioner_parameter(text, name, value)


def apply_micro_time_contract(text: str, *, dt: float, steps: int) -> str:
    return moose_executioner.apply_fixed_step_contract(text, dt=dt, steps=steps)


def _build_electron_fixed(base_text: str, *, dt: float, steps: int) -> str:
    return apply_micro_time_contract(
        _RAW_BUILD_ELECTRON_300K(base_text, dt=dt, steps=steps),
        dt=dt,
        steps=steps,
    )


def _build_oneway_fixed(
    base_text: str, *, dt: float, steps: int, radial_span: float
) -> str:
    return apply_micro_time_contract(
        _BASE_BUILD_ONEWAY(
            base_text, dt=dt, steps=steps, radial_span=radial_span
        ),
        dt=dt,
        steps=steps,
    )


def _build_feedback_fixed(
    base_text: str, *, dt: float, steps: int, radial_span: float
) -> str:
    return apply_micro_time_contract(
        _BASE_BUILD_FEEDBACK(
            base_text, dt=dt, steps=steps, radial_span=radial_span
        ),
        dt=dt,
        steps=steps,
    )


def _executioner_controls(text: str) -> dict[str, Any]:
    return moose_executioner.executioner_controls(
        text,
        required=(
            "dt",
            "end_time",
            "num_steps",
            "dtmin",
            "timestep_tolerance",
            "abort_on_solve_fail",
        ),
    )


def _case_semantics(case_id: str) -> tuple[str, list[str], list[str]]:
    if "electron_300K" in case_id:
        return (
            "300 K electron-only transient control with prescribed electric field",
            ["electron transport", "300 K lookup state"],
            ["solved Poisson feedback", "chemistry", "Maxwell"],
        )
    if "oneway" in case_id:
        return (
            "one-way electron-to-bulk-Poisson triangular discriminator",
            ["electron transport", "bulk Poisson response"],
            ["Poisson-to-electron feedback", "chemistry", "Maxwell"],
        )
    return (
        "two-way electron and bulk-Poisson fixed-step feedback discriminator",
        ["electron transport", "bulk Poisson", "two-way electrostatic feedback"],
        ["sheath-resolved physics", "chemistry", "Maxwell"],
    )


__all__ = [name for name in globals() if not name.startswith("__")]
