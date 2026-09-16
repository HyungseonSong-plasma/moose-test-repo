#!/usr/bin/env python3
"""Issue-236 boundary-face discriminator for transferred parent electron density.

This wrapper extends run_live_ci_transfer_diag.py without changing production
physics, timestep policy, chemistry state, MultiApp schedule, or transfer
payload.  It compares two diagnostic modes selected by the environment variable
ISSUE236_NE_BOUNDARY_MODE:

* two_term: parent n_e uses the MOOSE FV default two-term boundary expansion;
* one_term: parent n_e uses one-term boundary evaluation only.

The transferred diagnostic snapshot remains two-term in both modes.  Boundary
SideExtremeValue probes on plasma_electrode therefore distinguish a transfer
problem from a spatial-representation problem: the operational and snapshot
cell states can agree while their reconstructed boundary-face values differ
only when the operational n_e expansion policy is changed.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_transfer_diag as diag

base = diag.base
live = diag.live

_diag_build_parent_input = base.build_parent_input
_diag_audit_parent = base._audit_parent
_diag_self_test = base.self_test
_diag_runtime_analysis = base._runtime_analysis

_MODE_ENV = "ISSUE236_NE_BOUNDARY_MODE"
_MODE = os.environ.get(_MODE_ENV, "two_term").strip().lower()
_ALLOWED_MODES = {"two_term", "one_term"}
if _MODE not in _ALLOWED_MODES:
    raise RuntimeError(f"{_MODE_ENV} must be one of {sorted(_ALLOWED_MODES)}, got {_MODE!r}")

_BOUNDARY = "plasma_electrode"
_PARENT_NE = "AuxVariables/n_e"
_SNAPSHOT_NE = "AuxVariables/issue236_diag_snap_ne"
_FACE_FIELDS = {
    "ne_face": "n_e",
    "ne_snap_face": "issue236_diag_snap_ne",
}
_NEGATIVE_NE_SIGNATURE = "requires electron_number_density >= 0"


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["failed_checks"] = sorted(key for key, ok in result["checks"].items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _insert_side_extreme_pp(
    text: str, *, lane: str, field_key: str, variable: str, value_type: str
) -> str:
    spec = diag._LANES[lane]
    name = f"issue236_diag_{lane}_{field_key}_{value_type}"
    return diag._insert_pp(
        text,
        name,
        f"""  [{name}]
    type = SideExtremeValue
    variable = {variable}
    boundary = {_BOUNDARY}
    value_type = {value_type}
    execute_on = '{spec['pp_execute_on']}'
    outputs = {spec['output']}
  []""",
    )


def _instrument_boundary_faces(text: str) -> str:
    for lane in ("parent_after_transfer", "parent_nonlinear"):
        for field_key, variable in _FACE_FIELDS.items():
            for value_type in ("min", "max"):
                text = _insert_side_extreme_pp(
                    text,
                    lane=lane,
                    field_key=field_key,
                    variable=variable,
                    value_type=value_type,
                )
    return text


def _set_boundary_mode(text: str) -> str:
    if not base.mb.has_block(text, _PARENT_NE):
        raise base.Issue236Error(f"parent lacks transferred electron mirror: {_PARENT_NE}")
    if not base.mb.has_block(text, _SNAPSHOT_NE):
        raise base.Issue236Error(f"parent lacks diagnostic electron snapshot: {_SNAPSHOT_NE}")

    operational_two_term = "true" if _MODE == "two_term" else "false"
    text = base.mp.upsert_parameter(
        text, _PARENT_NE, "two_term_boundary_expansion", operational_two_term
    )
    # Immutable control: same transferred child state, always reconstructed with
    # the baseline two-term policy.
    text = base.mp.upsert_parameter(
        text, _SNAPSHOT_NE, "two_term_boundary_expansion", "true"
    )
    return text


def _build_parent_input(production_text: str) -> str:
    text = _diag_build_parent_input(production_text)
    text = _set_boundary_mode(text)
    return _instrument_boundary_faces(text)


def _boundary_audit(text: str) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    expected_operational = "true" if _MODE == "two_term" else "false"
    checks["diag_parent_ne_boundary_mode"] = (
        base.mp.unquote(base.mp.get_parameter(text, _PARENT_NE, "two_term_boundary_expansion"))
        == expected_operational
    )
    checks["diag_snapshot_ne_remains_two_term"] = (
        base.mp.unquote(base.mp.get_parameter(text, _SNAPSHOT_NE, "two_term_boundary_expansion"))
        == "true"
    )

    for lane in ("parent_after_transfer", "parent_nonlinear"):
        spec = diag._LANES[lane]
        for field_key, variable in _FACE_FIELDS.items():
            for value_type in ("min", "max"):
                name = f"issue236_diag_{lane}_{field_key}_{value_type}"
                path = f"Postprocessors/{name}"
                checks[f"diag_face_pp:{name}"] = (
                    base.mb.has_block(text, path)
                    and base.mp.unquote(base.mp.get_parameter(text, path, "type"))
                    == "SideExtremeValue"
                    and base.mp.unquote(base.mp.get_parameter(text, path, "variable"))
                    == variable
                    and base.mp.words(base.mp.get_parameter(text, path, "boundary"))
                    == [_BOUNDARY]
                    and base.mp.unquote(base.mp.get_parameter(text, path, "value_type"))
                    == value_type
                    and base.mp.unquote(base.mp.get_parameter(text, path, "execute_on"))
                    == spec["pp_execute_on"]
                    and base.mp.words(base.mp.get_parameter(text, path, "outputs"))
                    == [spec["output"]]
                )
    return checks


def _audit_parent(text: str):
    result = _diag_audit_parent(text)
    result["checks"].update(_boundary_audit(text))
    result["boundary_mode"] = _MODE
    return _finalize(result)


def _self_test():
    result = _diag_self_test()
    checks = result.setdefault("checks", {})
    parent, _child, meta = base.build_split(dt_e=live.ELECTRON_DT_S)
    checks.update(_boundary_audit(parent))
    checks["diag_boundary_schedule_unchanged"] = (
        meta["subcycles_per_heavy"] == 100
        and meta["dt_h_s"] == 1.0e-8
        and meta["dt_e_s"] == 1.0e-10
    )
    result["boundary_mode"] = _MODE
    return _finalize(result)


def _float_or_none(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read_runtime_log(case_dir: Path) -> str:
    log_path = case_dir.parent / "runtime.log"
    if not log_path.is_file():
        return ""
    return log_path.read_text(encoding="utf-8", errors="replace")


def _boundary_discriminator(result: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    transfer = result.get("transfer_diagnostics", {})
    row = transfer.get("latest_parent_after_transfer") or {}
    lane = "parent_after_transfer"

    cell_min = _float_or_none(row, f"issue236_diag_{lane}_ne_min")
    face_min = _float_or_none(row, f"issue236_diag_{lane}_ne_face_min")
    snapshot_cell_min = _float_or_none(row, f"issue236_diag_{lane}_ne_snap_min")
    snapshot_face_min = _float_or_none(row, f"issue236_diag_{lane}_ne_snap_face_min")
    log_text = _read_runtime_log(case_dir)

    return {
        "mode": _MODE,
        "boundary": _BOUNDARY,
        "cell_ne_min": cell_min,
        "face_ne_min": face_min,
        "snapshot_cell_ne_min": snapshot_cell_min,
        "snapshot_face_ne_min": snapshot_face_min,
        "cell_positive": cell_min is not None and cell_min > 0.0,
        "face_negative": face_min is not None and face_min < 0.0,
        "face_nonnegative": face_min is not None and face_min >= 0.0,
        "snapshot_cell_positive": snapshot_cell_min is not None and snapshot_cell_min > 0.0,
        "snapshot_face_negative": snapshot_face_min is not None and snapshot_face_min < 0.0,
        "negative_heavy_transport_signature_present": _NEGATIVE_NE_SIGNATURE in log_text,
        "interpretation": (
            "two_term operational reconstruction"
            if _MODE == "two_term"
            else "one_term operational control with two_term snapshot control"
        ),
    }


def _runtime_analysis(case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool):
    result = _diag_runtime_analysis(
        case_dir, dt_e=dt_e, returncode=returncode, timed_out=timed_out
    )
    result["boundary_face_discriminator"] = _boundary_discriminator(result, case_dir)
    return result


base.build_parent_input = _build_parent_input
base._audit_parent = _audit_parent
base.self_test = _self_test
base._runtime_analysis = _runtime_analysis

if __name__ == "__main__":
    raise SystemExit(base.main())
