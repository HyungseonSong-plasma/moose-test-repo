#!/usr/bin/env python3
"""Issue-236 L nonlinear-globalization discriminator for negative O- trials.

The Wave-O recorder established that the first invalid O- value is consumed as
an ElemArg in the parent heavy solve. This wrapper changes only the parent
nonlinear globalization control while preserving the qualified recorder,
physics model, timestep schedule, wall closure, FV representation, and child
solver.
"""
from __future__ import annotations

import math
import os
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_om_forensic_ci_v4 as wave

base = wave.base
v3 = wave.v3

_MODE_ENV = "ISSUE236_OM_L_MODE"
_MODES = {
    "L0_fullstep": {"line_search": "none", "damping": None},
    "L1_damp_0p5": {"line_search": "basic", "damping": 0.5},
    "L2_backtracking": {"line_search": "bt", "damping": None},
}
_MODE = os.environ.get(_MODE_ENV, "L0_fullstep").strip()
if _MODE not in _MODES:
    raise RuntimeError(f"{_MODE_ENV} must be one of {sorted(_MODES)}, got {_MODE!r}")
if not v3._RECORDER_ENABLED:
    raise RuntimeError("Issue-236 L requires ISSUE236_OM_FORENSIC=on")

# Wave-O validates O0/O1/O2 during import. L is a downstream campaign, so
# relabel only the evidence metadata after the recorder has been qualified.
v3._CASE_ID = _MODE
_CONTROL = _MODES[_MODE]
_DAMPING_OPT = "-snes_linesearch_damping"

_prior_build_parent = base.build_parent_input
_prior_audit_parent = base._audit_parent
_prior_self_test = base.self_test
_prior_runtime_analysis = base._runtime_analysis
_prior_run_physics = base.run_physics


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["failed_checks"] = sorted(key for key, ok in result["checks"].items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _solver_pairs(text: str) -> list[tuple[str, str]]:
    names = base.mp.words(base.mp.get_parameter(text, "Executioner", "petsc_options_iname"))
    values = base.mp.words(base.mp.get_parameter(text, "Executioner", "petsc_options_value"))
    if len(names) != len(values):
        raise base.Issue236Error(
            f"Executioner PETSc option/value length mismatch: {len(names)} != {len(values)}"
        )
    return list(zip(names, values))


def _apply_control(text: str, mode: str) -> str:
    control = _MODES[mode]
    text = base.mp.upsert_parameter(text, "Executioner", "line_search", control["line_search"])
    pairs = [(name, value) for name, value in _solver_pairs(text) if name != _DAMPING_OPT]
    if control["damping"] is not None:
        pairs.append((_DAMPING_OPT, format(float(control["damping"]), ".17g")))
    text = base.mp.upsert_parameter(
        text,
        "Executioner",
        "petsc_options_iname",
        "'" + " ".join(name for name, _ in pairs) + "'",
    )
    text = base.mp.upsert_parameter(
        text,
        "Executioner",
        "petsc_options_value",
        "'" + " ".join(value for _, value in pairs) + "'",
    )
    return text


def _build_parent_input(production_text: str) -> str:
    return _apply_control(_prior_build_parent(production_text), _MODE)


def _control_audit(text: str) -> dict[str, bool]:
    pairs = dict(_solver_pairs(text))
    damping = _CONTROL["damping"]
    return {
        "om_l:parent_line_search_exact": (
            base.mp.unquote(base.mp.get_parameter(text, "Executioner", "line_search"))
            == _CONTROL["line_search"]
        ),
        "om_l:parent_damping_exact": (
            (_DAMPING_OPT not in pairs)
            if damping is None
            else (
                _DAMPING_OPT in pairs
                and math.isclose(
                    float(pairs[_DAMPING_OPT]), float(damping), rel_tol=0.0, abs_tol=0.0
                )
            )
        ),
    }


def _audit_parent(text: str) -> dict[str, Any]:
    result = _prior_audit_parent(text)
    result.setdefault("checks", {}).update(_control_audit(text))
    result["om_nonlinear_mode"] = _MODE
    result["om_nonlinear_control"] = dict(_CONTROL)
    return _finalize(result)


def _normalize_declared_controls(text: str) -> str:
    """Remove only the declared L globalization differences."""
    pairs = [(name, value) for name, value in _solver_pairs(text) if name != _DAMPING_OPT]
    text = base.mp.upsert_parameter(text, "Executioner", "line_search", "OM_L_NORMALIZED")
    text = base.mp.upsert_parameter(
        text,
        "Executioner",
        "petsc_options_iname",
        "'" + " ".join(name for name, _ in pairs) + "'",
    )
    text = base.mp.upsert_parameter(
        text,
        "Executioner",
        "petsc_options_value",
        "'" + " ".join(value for _, value in pairs) + "'",
    )
    return "\n".join(line.rstrip() for line in text.splitlines()).strip() + "\n"


def _synthetic_executioner() -> str:
    return """[Executioner]
  type = Transient
  line_search = none
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]
"""


def _self_test() -> dict[str, Any]:
    result = _prior_self_test()
    checks = result.setdefault("checks", {})
    rendered = {mode: _apply_control(_synthetic_executioner(), mode) for mode in _MODES}
    baseline = _normalize_declared_controls(rendered["L0_fullstep"])
    checks["om_l:variants_only_declared_controls"] = all(
        _normalize_declared_controls(rendered[mode]) == baseline for mode in _MODES
    )
    checks["om_l:negative_physics_mutation_detected"] = (
        _normalize_declared_controls(
            rendered["L0_fullstep"].replace("type = Transient", "type = Steady")
        )
        != baseline
    )
    checks["om_l:L0_contract"] = (
        "line_search = none" in rendered["L0_fullstep"]
        and _DAMPING_OPT not in rendered["L0_fullstep"]
    )
    checks["om_l:L1_contract"] = (
        "line_search = basic" in rendered["L1_damp_0p5"]
        and _DAMPING_OPT in rendered["L1_damp_0p5"]
        and "0.5" in rendered["L1_damp_0p5"]
    )
    checks["om_l:L2_contract"] = (
        "line_search = bt" in rendered["L2_backtracking"]
        and _DAMPING_OPT not in rendered["L2_backtracking"]
    )
    checks["om_l:recorder_required"] = v3._RECORDER_ENABLED is True
    result["om_nonlinear_mode"] = _MODE
    result["om_nonlinear_control"] = dict(_CONTROL)
    return _finalize(result)


def _runtime_analysis(case_dir, *, dt_e: float, returncode: int, timed_out: bool):
    result = _prior_runtime_analysis(
        case_dir, dt_e=dt_e, returncode=returncode, timed_out=timed_out
    )
    result["om_nonlinear_control"] = {
        "mode": _MODE,
        "line_search": _CONTROL["line_search"],
        "damping": _CONTROL["damping"],
        "scope": "parent Executioner only",
        "recorder_enabled": True,
    }
    return result


def _run_physics(exe, **kwargs):
    extra_args = tuple(kwargs.pop("extra_args", ()))
    return _prior_run_physics(
        exe,
        extra_args=(*extra_args, "-snes_linesearch_monitor"),
        **kwargs,
    )


base.build_parent_input = _build_parent_input
base._audit_parent = _audit_parent
base.self_test = _self_test
base._runtime_analysis = _runtime_analysis
base.run_physics = _run_physics

if __name__ == "__main__":
    raise SystemExit(base.main())
