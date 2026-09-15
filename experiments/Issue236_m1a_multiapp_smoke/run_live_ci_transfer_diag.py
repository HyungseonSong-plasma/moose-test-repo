#!/usr/bin/env python3
"""Issue-236 transfer/recovery diagnostic wrapper.

Observational extension of run_live_ci_nochem.py.  It adds three independent
lanes without changing physics or transfer payloads:

A. child accepted state at INITIAL/TIMESTEP_END;
B. parent state at INITIAL/TIMESTEP_BEGIN, after FROM_MULTIAPP transfer and
   before the heavy nonlinear solve;
C. parent state on every NONLINEAR evaluation during the heavy solve.

Each lane records extrema for n_e, n_epsilon, potential_plasma and
n_e_physical, plus timestep index and dt, into a dedicated CSV file.  The
existing acceptance CSV files and pass/fail gates are left untouched.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_nochem as nochem

base = nochem.base
live = nochem.live

_nochem_build_parent_input = base.build_parent_input
_nochem_build_child_input = base.build_child_input
_nochem_audit_parent = base._audit_parent
_nochem_audit_child = base._audit_child
_nochem_self_test = base.self_test
_nochem_runtime_analysis = base._runtime_analysis

_FIELDS = {
    "ne": "n_e",
    "nepsilon": "n_epsilon",
    "phi": "potential_plasma",
    "ne_physical": "n_e_physical",
}

_LANES = {
    "child_accepted": {
        "pp_execute_on": "INITIAL TIMESTEP_END",
        "output_execute_on": "INITIAL TIMESTEP_END FAILED",
        "output": "issue236_diag_child_accepted_csv",
        "file_base": "issue236_diag_child_accepted",
    },
    "parent_begin": {
        "pp_execute_on": "INITIAL TIMESTEP_BEGIN",
        "output_execute_on": "INITIAL TIMESTEP_BEGIN FAILED",
        "output": "issue236_diag_parent_begin_csv",
        "file_base": "issue236_diag_parent_begin",
    },
    "parent_nonlinear": {
        "pp_execute_on": "NONLINEAR",
        "output_execute_on": "NONLINEAR FAILED",
        "output": "issue236_diag_parent_nonlinear_csv",
        "file_base": "issue236_diag_parent_nonlinear",
    },
}


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["failed_checks"] = sorted(
        key for key, ok in result["checks"].items() if not ok
    )
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _insert_pp(text: str, name: str, payload: str) -> str:
    text = base._ensure_top_block(text, "Postprocessors")
    path = f"Postprocessors/{name}"
    if base.mb.has_block(text, path):
        raise base.Issue236Error(f"duplicate transfer diagnostic postprocessor: {path}")
    return base.mb.insert_child_block(text, "Postprocessors", payload)


def _insert_extreme_pp(
    text: str,
    *,
    lane: str,
    field_key: str,
    functor: str,
    value_type: str,
) -> str:
    spec = _LANES[lane]
    name = f"issue236_diag_{lane}_{field_key}_{value_type}"
    return _insert_pp(
        text,
        name,
        f"""  [{name}]
    type = ElementExtremeFunctorValue
    functor = {functor}
    value_type = {value_type}
    block = plasma
    execute_on = '{spec['pp_execute_on']}'
    outputs = {spec['output']}
  []""",
    )


def _insert_context_pp(text: str, *, lane: str, name_suffix: str, pp_type: str) -> str:
    spec = _LANES[lane]
    name = f"issue236_diag_{lane}_{name_suffix}"
    return _insert_pp(
        text,
        name,
        f"""  [{name}]
    type = {pp_type}
    execute_on = '{spec['pp_execute_on']}'
    outputs = {spec['output']}
  []""",
    )


def _insert_lane_output(text: str, *, lane: str) -> str:
    spec = _LANES[lane]
    text = base._ensure_top_block(text, "Outputs")
    path = f"Outputs/{spec['output']}"
    if base.mb.has_block(text, path):
        raise base.Issue236Error(f"duplicate transfer diagnostic output: {path}")
    return base.mb.insert_child_block(
        text,
        "Outputs",
        f"""  [{spec['output']}]
    type = CSV
    file_base = {spec['file_base']}
    execute_on = '{spec['output_execute_on']}'
    new_row_detection_columns = all
    precision = 17
  []""",
    )


def _instrument_lane(text: str, *, lane: str) -> str:
    for field_key, functor in _FIELDS.items():
        for value_type in ("min", "max"):
            text = _insert_extreme_pp(
                text,
                lane=lane,
                field_key=field_key,
                functor=functor,
                value_type=value_type,
            )
    text = _insert_context_pp(text, lane=lane, name_suffix="step", pp_type="NumTimeSteps")
    text = _insert_context_pp(text, lane=lane, name_suffix="dt", pp_type="TimestepSize")
    return _insert_lane_output(text, lane=lane)


def _build_parent_input(production_text: str) -> str:
    text = _nochem_build_parent_input(production_text)
    text = _instrument_lane(text, lane="parent_begin")
    text = _instrument_lane(text, lane="parent_nonlinear")
    return text


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _nochem_build_child_input(production_text, dt_e=dt_e)
    return _instrument_lane(text, lane="child_accepted")


def _lane_audit(text: str, *, lane: str) -> dict[str, bool]:
    spec = _LANES[lane]
    checks: dict[str, bool] = {}
    output_path = f"Outputs/{spec['output']}"
    checks[f"diag_output:{lane}"] = (
        base.mb.has_block(text, output_path)
        and base.mp.unquote(base.mp.get_parameter(text, output_path, "type")) == "CSV"
        and base.mp.unquote(base.mp.get_parameter(text, output_path, "file_base"))
        == spec["file_base"]
        and base.mp.unquote(base.mp.get_parameter(text, output_path, "execute_on"))
        == spec["output_execute_on"]
        and base.mp.unquote(
            base.mp.get_parameter(text, output_path, "new_row_detection_columns")
        )
        == "all"
    )

    expected_names: list[str] = []
    for field_key in _FIELDS:
        for value_type in ("min", "max"):
            expected_names.append(f"issue236_diag_{lane}_{field_key}_{value_type}")
    expected_names.extend(
        (f"issue236_diag_{lane}_step", f"issue236_diag_{lane}_dt")
    )
    for name in expected_names:
        path = f"Postprocessors/{name}"
        checks[f"diag_pp:{name}"] = (
            base.mb.has_block(text, path)
            and base.mp.unquote(base.mp.get_parameter(text, path, "execute_on"))
            == spec["pp_execute_on"]
            and base.mp.words(base.mp.get_parameter(text, path, "outputs"))
            == [spec["output"]]
        )
    return checks


def _audit_parent(text: str):
    result = _nochem_audit_parent(text)
    result["checks"].update(_lane_audit(text, lane="parent_begin"))
    result["checks"].update(_lane_audit(text, lane="parent_nonlinear"))
    fast_transfer = "Transfers/fast_from_electron"
    result["checks"]["diag_preserves_fast_transfer"] = (
        base.mb.has_block(text, fast_transfer)
        and base.mp.unquote(base.mp.get_parameter(text, fast_transfer, "type"))
        == "MultiAppCopyTransfer"
        and base.mp.words(base.mp.get_parameter(text, fast_transfer, "source_variable"))
        == list(base.FAST_SOLVER_VARIABLES)
        and base.mp.words(base.mp.get_parameter(text, fast_transfer, "variable"))
        == list(base.FAST_SOLVER_VARIABLES)
    )
    return _finalize(result)


def _audit_child(text: str, *, dt_e: float):
    result = _nochem_audit_child(text, dt_e=dt_e)
    result["checks"].update(_lane_audit(text, lane="child_accepted"))
    return _finalize(result)


def _self_test():
    result = _nochem_self_test()
    checks = result.setdefault("checks", {})
    parent, child, _meta = base.build_split(dt_e=live.ELECTRON_DT_S)
    checks.update(_lane_audit(parent, lane="parent_begin"))
    checks.update(_lane_audit(parent, lane="parent_nonlinear"))
    checks.update(_lane_audit(child, lane="child_accepted"))

    # The diagnostics are observational: all original transfer and solver
    # ownership contracts must remain intact.
    checks["diag_fast_transfer_payload_unchanged"] = (
        base.mp.words(
            base.mp.get_parameter(parent, "Transfers/fast_from_electron", "source_variable")
        )
        == list(base.FAST_SOLVER_VARIABLES)
        and base.mp.words(
            base.mp.get_parameter(parent, "Transfers/fast_from_electron", "variable")
        )
        == list(base.FAST_SOLVER_VARIABLES)
    )
    checks["diag_schedule_unchanged"] = (
        math.isclose(_meta["dt_e_s"], 1.0e-10, rel_tol=0.0, abs_tol=0.0)
        and math.isclose(_meta["dt_h_s"], 1.0e-8, rel_tol=0.0, abs_tol=0.0)
        and _meta["subcycles_per_heavy"] == 100
    )
    return _finalize(result)


def _find_diag_csv(case_dir: Path, file_base: str) -> Path | None:
    candidates = sorted(
        path
        for path in case_dir.rglob("*.csv")
        if file_base in path.name and path.is_file()
    )
    return max(candidates, key=lambda path: path.stat().st_size) if candidates else None


def _numeric_rows(path: Path | None) -> list[dict[str, float]]:
    if path is None:
        return []
    rows: list[dict[str, float]] = []
    for row in base._read_csv(path):
        try:
            rows.append({key: float(value) for key, value in row.items() if value != ""})
        except (TypeError, ValueError):
            continue
    return rows


def _row_at_time(
    rows: list[dict[str, float]], target: float, *, first: bool
) -> dict[str, float] | None:
    ordered = rows if first else reversed(rows)
    for row in ordered:
        if "time" in row and math.isclose(
            row["time"], target, rel_tol=0.0, abs_tol=1.0e-18
        ):
            return row
    return None


def _compare_lane_rows(
    left: dict[str, float] | None,
    right: dict[str, float] | None,
    *,
    left_lane: str,
    right_lane: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {"available": bool(left and right), "fields": {}}
    if not left or not right:
        return result
    for field_key in _FIELDS:
        for value_type in ("min", "max"):
            left_key = f"issue236_diag_{left_lane}_{field_key}_{value_type}"
            right_key = f"issue236_diag_{right_lane}_{field_key}_{value_type}"
            if left_key not in left or right_key not in right:
                continue
            lv = left[left_key]
            rv = right[right_key]
            scale = max(abs(lv), abs(rv), 1.0e-300)
            result["fields"][f"{field_key}_{value_type}"] = {
                "left": lv,
                "right": rv,
                "absolute_difference": abs(lv - rv),
                "relative_difference": abs(lv - rv) / scale,
            }
    return result


def _collect_transfer_diagnostics(case_dir: Path) -> dict[str, Any]:
    paths = {
        lane: _find_diag_csv(case_dir, spec["file_base"])
        for lane, spec in _LANES.items()
    }
    rows = {lane: _numeric_rows(path) for lane, path in paths.items()}
    parent_begin = rows["parent_begin"][-1] if rows["parent_begin"] else None
    child_at_begin = None
    nonlinear_at_begin = None
    if parent_begin and "time" in parent_begin:
        target = parent_begin["time"]
        child_at_begin = _row_at_time(rows["child_accepted"], target, first=False)
        nonlinear_at_begin = _row_at_time(rows["parent_nonlinear"], target, first=True)

    return {
        "files": {lane: str(path) if path else None for lane, path in paths.items()},
        "row_counts": {lane: len(values) for lane, values in rows.items()},
        "latest_parent_begin": parent_begin,
        "child_at_latest_parent_begin": child_at_begin,
        "first_parent_nonlinear_at_latest_begin": nonlinear_at_begin,
        "child_to_parent_begin": _compare_lane_rows(
            child_at_begin,
            parent_begin,
            left_lane="child_accepted",
            right_lane="parent_begin",
        ),
        "parent_begin_to_first_nonlinear": _compare_lane_rows(
            parent_begin,
            nonlinear_at_begin,
            left_lane="parent_begin",
            right_lane="parent_nonlinear",
        ),
    }


def _runtime_analysis(case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool):
    result = _nochem_runtime_analysis(
        case_dir,
        dt_e=dt_e,
        returncode=returncode,
        timed_out=timed_out,
    )
    # Observational only: do not change hard_pass or any existing acceptance gate.
    result["transfer_diagnostics"] = _collect_transfer_diagnostics(case_dir)
    return result


base.build_parent_input = _build_parent_input
base.build_child_input = _build_child_input
base._audit_parent = _audit_parent
base._audit_child = _audit_child
base.self_test = _self_test
base._runtime_analysis = _runtime_analysis

if __name__ == "__main__":
    raise SystemExit(base.main())
