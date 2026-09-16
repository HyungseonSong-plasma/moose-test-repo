#!/usr/bin/env python3
"""Wave-O v4 wrapper adding structured parent nonlinear solver context.

This layer preserves the v3 pass-through forensic physics, adds only two
parent NONLINEAR postprocessors needed to bind the pre-failure Newton trajectory,
and classifies the forensic diagnostic JSONL path as runtime output rather than
a staged input asset.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_om_forensic_ci as v3
from physics_harness.execution.cases import CaseError

base = v3.base

_PARENT_NL_OUTPUT = "issue236_diag_parent_nonlinear_csv"
_PARENT_NL_EXEC = "NONLINEAR"
_NL_ITS_NAME = "issue236_diag_parent_nonlinear_nl_its"
_NL_RESIDUAL_NAME = "issue236_diag_parent_nonlinear_residual"

# The generic staging validator intentionally treats *_file parameters as input
# assets. This exact parameter is different: PhysicsPassThroughForensicMaterial
# creates it at runtime. Strip only the two governed forensic output names from
# staging validation; every other file-like parameter remains fail-closed.
_FORENSIC_OUTPUT_RE = re.compile(
    r"""(?mx)
    ^[ \t]*diagnostic_file[ \t]*=[ \t]*
    (?P<quote>['"])
    issue236_om_forensic_(?:parent|child)\.jsonl
    (?P=quote)
    [ \t]*(?:\#.*)?$
    """
)

_v3_build_parent_input = base.build_parent_input
_v3_audit_parent = base._audit_parent
_v3_self_test = base.self_test
_v3_validate_referenced_files = base.validate_referenced_files


def _validate_referenced_files(
    input_text: str, case_dir: Path, *, skip_dynamic: bool = False
):
    """Validate true input assets while excluding only governed forensic outputs."""
    sanitized = _FORENSIC_OUTPUT_RE.sub("", str(input_text))
    return _v3_validate_referenced_files(
        sanitized, case_dir, skip_dynamic=skip_dynamic
    )


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


def _self_test() -> dict[str, Any]:
    result = _v3_self_test()
    checks = result.setdefault("checks", {})

    with tempfile.TemporaryDirectory(prefix="issue236-wave-o-v4-") as tmp:
        root = Path(tmp)
        try:
            _validate_referenced_files(
                "diagnostic_file = 'issue236_om_forensic_parent.jsonl'\n",
                root,
                skip_dynamic=True,
            )
            output_ignored = True
        except CaseError:
            output_ignored = False

        try:
            _validate_referenced_files(
                "required_file = 'must_exist.tbl'\n",
                root,
                skip_dynamic=True,
            )
            missing_input_rejected = False
        except CaseError:
            missing_input_rejected = True

    checks["om_forensic:staging_runtime_output_not_input_asset"] = output_ignored
    checks["om_forensic:staging_true_input_still_fail_closed"] = missing_input_rejected
    result["failed_checks"] = sorted(key for key, ok in checks.items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


base.validate_referenced_files = _validate_referenced_files
base.build_parent_input = _build_parent_input
base._audit_parent = _audit_parent
base.self_test = _self_test

if __name__ == "__main__":
    raise SystemExit(base.main())
