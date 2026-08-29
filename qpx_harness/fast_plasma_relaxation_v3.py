"""Issue #43 fast plasma discriminator v3.

Repairs v2's sub-picosecond execution contract. MOOSE Transient defaults use
`timestep_tolerance = 1e-12` and `dtmin = 1e-12`; those defaults can suppress
all physical timesteps when a diagnostic uses dt/end_time below 1e-12.

v3 wraps the validated v2 discriminator and makes the micro-time contract
explicit, while converting missing-positive-time CSV evidence into a structured
harness failure instead of an uncaught Python exception.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from . import fast_plasma_relaxation as v1
from . import fast_plasma_relaxation_v2 as v2
from .moose_input import MooseInput, MooseInputError


class FastPlasmaV3Error(RuntimeError):
    pass


_RAW_BUILD_FEEDBACK = v2._build_feedback
_RAW_RUN_CASE = v2._run_case


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def _executioner_parameter_count(text: str, name: str) -> int:
    doc = MooseInput(text)
    span = doc.unique("Executioner")
    block = text[span.start : span.end]
    pattern = re.compile(rf"(?m)^\s*{re.escape(name)}\s*=")
    return len(pattern.findall(block))


def _set_executioner_parameter(text: str, name: str, value: str) -> str:
    count = _executioner_parameter_count(text, name)
    if count > 1:
        raise FastPlasmaV3Error(
            f"ambiguous Executioner parameter {name!r}: found {count} assignments"
        )
    try:
        if count == 1:
            text, _ = MooseInput(text).replace_parameters(
                "Executioner", {name: value}
            )
        else:
            text, _ = MooseInput(text).insert_before_close(
                "Executioner", f"  {name} = {value}"
            )
    except MooseInputError as exc:
        raise FastPlasmaV3Error(
            f"failed to set Executioner/{name}: {exc}"
        ) from exc
    return text


def apply_micro_time_contract(text: str, *, dt: float, steps: int) -> str:
    """Make a sub-picosecond fixed-step contract explicit for MOOSE Transient."""
    if dt <= 0.0 or steps <= 0:
        raise FastPlasmaV3Error("dt and steps must be positive")

    # Keep final-time/sync tolerance far below one intended step and move dtmin
    # below the requested fixed dt. abort_on_solve_fail prevents an implicit
    # cutback from silently changing the discriminator's dt.
    settings = {
        "dt": _fmt(dt),
        "end_time": _fmt(dt * steps),
        "num_steps": str(steps),
        "dtmin": _fmt(dt * 0.1),
        "timestep_tolerance": _fmt(dt * 1.0e-3),
        "abort_on_solve_fail": "true",
        "compute_scaling_once": "true",
    }
    for name, value in settings.items():
        text = _set_executioner_parameter(text, name, value)
    return text


def _build_feedback_fixed(
    base_text: str, *, dt: float, steps: int, radial_span: float
) -> str:
    text = _RAW_BUILD_FEEDBACK(
        base_text, dt=dt, steps=steps, radial_span=radial_span
    )
    return apply_micro_time_contract(text, dt=dt, steps=steps)


def _run_case_safe(**kwargs: Any) -> dict[str, Any]:
    """Never let temporal CSV semantics erase the rest of an external batch."""
    try:
        return _RAW_RUN_CASE(**kwargs)
    except v1.FastPlasmaRelaxationError as exc:
        case_id = str(kwargs.get("case_id", "unknown"))
        measurements_root = Path(kwargs["measurements_root"])
        result_root = measurements_root / case_id
        p2_log = result_root / "p2_check_input.log"
        p3_log = result_root / "p3_runtime.log"
        result: dict[str, Any] = {
            "case_id": case_id,
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "temporal output did not contain an interpretable positive-time row",
            "harness_error": str(exc),
        }
        if p2_log.is_file():
            result["p2_log"] = str(p2_log)
        if p3_log.is_file():
            result["p3_log"] = str(p3_log)
        return v2._attach_residual(result)


def _install_v2_repairs() -> None:
    v2._build_feedback = _build_feedback_fixed
    v2._run_case = _run_case_safe


def self_test() -> int:
    try:
        if v2.self_test() != 0:
            raise AssertionError("v2 self-test failed")

        base = """[Executioner]
  type = Transient
  scheme = implicit-euler
  dt = 1e-8
  end_time = 2e-8
  compute_scaling_once = true
[]
"""
        tuned = apply_micro_time_contract(base, dt=1.0e-13, steps=5)
        doc = MooseInput(tuned)
        span = doc.unique("Executioner")
        block = tuned[span.start : span.end]
        required = {
            "dt": "1e-13",
            "end_time": "5e-13",
            "num_steps": "5",
            "dtmin": "1e-14",
            "timestep_tolerance": "1e-16",
            "abort_on_solve_fail": "true",
        }
        for name, expected in required.items():
            match = re.search(
                rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", block
            )
            if match is None:
                raise AssertionError(f"missing micro-time parameter {name}")
            actual = match.group(1).strip()
            if name in {"dt", "end_time", "dtmin", "timestep_tolerance"}:
                if float(actual) != float(expected):
                    raise AssertionError(
                        f"wrong {name}: expected {expected}, got {actual}"
                    )
            elif actual != expected:
                raise AssertionError(
                    f"wrong {name}: expected {expected}, got {actual}"
                )

        # Negative control: a duplicate time-control assignment must be rejected.
        duplicate = tuned.replace(
            "  num_steps = 5\n", "  num_steps = 5\n  num_steps = 6\n"
        )
        try:
            apply_micro_time_contract(duplicate, dt=1.0e-13, steps=5)
        except FastPlasmaV3Error:
            pass
        else:
            raise AssertionError("duplicate Executioner parameter was not rejected")
    except Exception as exc:
        print(f"ISSUE43_FAST_V3_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_V3_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    known, _ = parser.parse_known_args(args)
    if known.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    _install_v2_repairs()
    return v2.main(args)


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
