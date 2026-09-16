#!/usr/bin/env python3
"""Wave-O v4 wrapper adding structured parent nonlinear solver context.

This layer preserves the v3 pass-through forensic physics and adds only two
parent NONLINEAR postprocessors needed to bind the pre-failure Newton trajectory:
current nonlinear-iteration count and current SNES residual norm.
"""
from __future__ import annotations

from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_om_forensic_ci as v3

base = v3.base

_PARENT_NL_OUTPUT = "issue236_diag_parent_nonlinear_csv"
_PARENT_NL_EXEC = "NONLINEAR"
_NL_ITS_NAME = "issue236_diag_parent_nonlinear_nl_its"
_NL_RESIDUAL_NAME = "issue236_diag_parent_nonlinear_residual"

_v3_build_parent_input = base.build_parent_input
_v3_audit_parent = base._audit_parent


def _insert_parent_nonlinear_solver_context(text: str) -> str:
    """Add observer-only solver context to the existing parent NONLINEAR CSV lane."""
    text = base._ensure_top_block(text, "Postprocessors")
    payloads = {
        _NL_ITS_NAME: f"""  [{_NL_ITS_NAME}]
    type = NumNonlinearIterations
    execute_on = '{_PARENT_NL_EXEC}'
    outputs = {_PARENT_NL_OUTPUT}
  []""",
        _NL_RESIDUAL_NAME: f"""  [{_NL_RESIDUAL_NAME}]
    type = Residual
    residual_type = CURRENT
    execute_on = '{_PARENT_NL_EXEC}'
    outputs = {_PARENT_NL_OUTPUT}
  []""",
    }
    for name, payload in payloads.items():
        path = f"Postprocessors/{name}"
        if base.mb.has_block(text, path):
            raise base.Issue236Error(f"duplicate Wave-O nonlinear diagnostic: {path}")
        text = base.mb.insert_child_block(text, "Postprocessors", payload)
    return text


def _build_parent_input(production_text: str) -> str:
    return _insert_parent_nonlinear_solver_context(_v3_build_parent_input(production_text))


def _solver_context_audit(text: str) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    its_path = f"Postprocessors/{_NL_ITS_NAME}"
    residual_path = f"Postprocessors/{_NL_RESIDUAL_NAME}"
    checks["om_forensic:parent:nonlinear_iteration_context"] = (
        base.mb.has_block(text, its_path)
        and base.mp.unquote(base.mp.get_parameter(text, its_path, "type"))
        == "NumNonlinearIterations"
        and base.mp.unquote(base.mp.get_parameter(text, its_path, "execute_on"))
        == _PARENT_NL_EXEC
        and base.mp.words(base.mp.get_parameter(text, its_path, "outputs"))
        == [_PARENT_NL_OUTPUT]
    )
    checks["om_forensic:parent:nonlinear_residual_context"] = (
        base.mb.has_block(text, residual_path)
        and base.mp.unquote(base.mp.get_parameter(text, residual_path, "type")) == "Residual"
        and base.mp.unquote(base.mp.get_parameter(text, residual_path, "residual_type"))
        == "CURRENT"
        and base.mp.unquote(base.mp.get_parameter(text, residual_path, "execute_on"))
        == _PARENT_NL_EXEC
        and base.mp.words(base.mp.get_parameter(text, residual_path, "outputs"))
        == [_PARENT_NL_OUTPUT]
    )
    return checks


def _audit_parent(text: str) -> dict[str, Any]:
    result = _v3_audit_parent(text)
    result.setdefault("checks", {}).update(_solver_context_audit(text))
    result["failed_checks"] = sorted(key for key, ok in result["checks"].items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


base.build_parent_input = _build_parent_input
base._audit_parent = _audit_parent

if __name__ == "__main__":
    raise SystemExit(base.main())
