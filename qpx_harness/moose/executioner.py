"""Experiment-agnostic MOOSE Executioner fixed-step operations."""
from __future__ import annotations

import math
from typing import Any, Iterable

from .parameters import MooseParameterError, get_parameter, upsert_parameter


class MooseExecutionerError(RuntimeError):
    """Raised when an Executioner operation is invalid or structurally ambiguous."""


DEFAULT_CONTROL_NAMES = (
    "dt",
    "end_time",
    "num_steps",
    "dtmin",
    "dtmax",
    "timestep_tolerance",
    "abort_on_solve_fail",
    "compute_scaling_once",
)


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def parse_scalar(raw: str) -> Any:
    """Parse a MOOSE scalar literal into a Python bool/int/float/string value."""
    value = raw.strip().strip("'\"")
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        number = float(value)
    except ValueError:
        return value
    if math.isfinite(number) and number.is_integer() and not any(
        token in value.lower() for token in (".", "e")
    ):
        return int(number)
    return number


def set_executioner_parameter(text: str, name: str, value: str) -> str:
    """Upsert exactly one parameter in the top-level ``[Executioner]`` block."""
    try:
        return upsert_parameter(text, "Executioner", name, value)
    except MooseParameterError as exc:
        raise MooseExecutionerError(
            f"failed to set Executioner/{name}: {exc}"
        ) from exc


def executioner_controls(
    text: str,
    *,
    names: Iterable[str] = DEFAULT_CONTROL_NAMES,
    required: Iterable[str] = (),
) -> dict[str, Any]:
    """Return typed effective Executioner controls and fail closed on ambiguity."""
    controls: dict[str, Any] = {}
    for name in names:
        try:
            raw = get_parameter(text, "Executioner", str(name))
        except MooseParameterError as exc:
            raise MooseExecutionerError(
                f"cannot read Executioner/{name}: {exc}"
            ) from exc
        if raw is not None:
            controls[str(name)] = parse_scalar(raw)

    missing = [str(name) for name in required if str(name) not in controls]
    if missing:
        raise MooseExecutionerError(
            "Executioner controls missing explicit parameters: " + ", ".join(missing)
        )
    return controls


def apply_fixed_step_contract(
    text: str,
    *,
    dt: float,
    steps: int,
    dtmin_factor: float = 0.1,
    timestep_tolerance_factor: float = 1.0e-3,
    abort_on_solve_fail: bool = True,
    compute_scaling_once: bool = True,
) -> str:
    """Apply explicit fixed-step controls without embedding experiment semantics."""
    if not math.isfinite(dt) or dt <= 0.0:
        raise MooseExecutionerError("dt must be finite and positive")
    if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
        raise MooseExecutionerError("steps must be a positive integer")
    if not math.isfinite(dtmin_factor) or not 0.0 < dtmin_factor < 1.0:
        raise MooseExecutionerError("dtmin_factor must be finite and in (0, 1)")
    if (
        not math.isfinite(timestep_tolerance_factor)
        or not 0.0 < timestep_tolerance_factor < 1.0
    ):
        raise MooseExecutionerError(
            "timestep_tolerance_factor must be finite and in (0, 1)"
        )

    settings = {
        "dt": _fmt(dt),
        "end_time": _fmt(dt * steps),
        "num_steps": str(steps),
        "dtmin": _fmt(dt * dtmin_factor),
        "timestep_tolerance": _fmt(dt * timestep_tolerance_factor),
        "abort_on_solve_fail": "true" if abort_on_solve_fail else "false",
        "compute_scaling_once": "true" if compute_scaling_once else "false",
    }
    for name, value in settings.items():
        text = set_executioner_parameter(text, name, value)
    return text


def self_test() -> int:
    try:
        base = """[Executioner]
  type = Transient
  scheme = implicit-euler
  dt = 1e-8
  end_time = 2e-8
  compute_scaling_once = true
[]
"""
        tuned = apply_fixed_step_contract(base, dt=1.0e-13, steps=5)
        controls = executioner_controls(
            tuned,
            required=(
                "dt",
                "end_time",
                "num_steps",
                "dtmin",
                "timestep_tolerance",
                "abort_on_solve_fail",
            ),
        )
        expected = {
            "dt": 1.0e-13,
            "end_time": 5.0e-13,
            "num_steps": 5,
            "dtmin": 1.0e-14,
            "timestep_tolerance": 1.0e-16,
            "abort_on_solve_fail": True,
            "compute_scaling_once": True,
        }
        for name, value in expected.items():
            actual = controls.get(name)
            if isinstance(value, float):
                if not math.isclose(
                    float(actual), value, rel_tol=1.0e-15, abs_tol=0.0
                ):
                    raise AssertionError(
                        f"wrong {name}: expected {value}, got {actual}"
                    )
            elif actual != value:
                raise AssertionError(
                    f"wrong {name}: expected {value}, got {actual}"
                )

        duplicate = tuned.replace(
            "  num_steps = 5\n", "  num_steps = 5\n  num_steps = 6\n"
        )
        try:
            apply_fixed_step_contract(duplicate, dt=1.0e-13, steps=5)
        except MooseExecutionerError:
            pass
        else:
            raise AssertionError("duplicate Executioner parameter was accepted")

        for kwargs in (
            {"dt": 0.0, "steps": 5},
            {"dt": 1.0e-13, "steps": 0},
            {"dt": 1.0e-13, "steps": 5, "dtmin_factor": 1.0},
            {
                "dt": 1.0e-13,
                "steps": 5,
                "timestep_tolerance_factor": 0.0,
            },
        ):
            try:
                apply_fixed_step_contract(base, **kwargs)
            except MooseExecutionerError:
                pass
            else:
                raise AssertionError(f"invalid fixed-step contract was accepted: {kwargs}")
    except Exception as exc:
        print(f"MOOSE_EXECUTIONER_SELFTEST: FAIL ({exc})")
        return 1
    print("MOOSE_EXECUTIONER_SELFTEST: PASS")
    return 0
