#!/usr/bin/env python3
"""Issue-236 transfer/recovery diagnostic wrapper.

Diagnostic-only extension of run_live_ci_nochem.py.  It does not alter the
physics, timestep policy, nonlinear solver, chemistry-off state, or operational
fast_from_electron payload.

Four observation lanes are produced:

A. accepted child state at INITIAL/TIMESTEP_END;
B. parent state immediately after TIMESTEP_BEGIN child execution/transfers;
C. parent state on every heavy NONLINEAR evaluation;
D. the exact functor supplied to heavy_transport/electron_number_density,
   observed in B and C.

To avoid ambiguous child/parent CSV pairing during timestep cutback/recovery, a
second diagnostic MultiAppCopyTransfer copies the same accepted child variables
into dedicated parent Aux snapshots on TIMESTEP_BEGIN.  The operational parent
mirrors and immutable diagnostic snapshots are therefore compared in the same
parent row/attempt instead of being joined by floating-point time.
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

_SNAPSHOT_TRANSFER = "issue236_diag_fast_snapshot_from_electron"
_SNAPSHOTS = {
    "ne_snap": ("n_e", "issue236_diag_snap_ne", "1.0"),
    "nepsilon_snap": ("n_epsilon", "issue236_diag_snap_nepsilon", "1.0"),
    "phi_snap": ("potential_plasma", "issue236_diag_snap_phi", "0.0"),
}
_BASE_FIELDS = {
    "ne": "n_e",
    "nepsilon": "n_epsilon",
    "phi": "potential_plasma",
    "ne_physical": "n_e_physical",
}
_LANES = {
    "child_accepted": {
        "pp_execute_on": "INITIAL TIMESTEP_END",
        "output_execute_on": "INITIAL TIMESTEP_END",
        "output": "issue236_diag_child_accepted_csv",
        "file_base": "issue236_diag_child_accepted",
    },
    "parent_after_transfer": {
        "pp_execute_on": "INITIAL TIMESTEP_BEGIN",
        "output_execute_on": "INITIAL TIMESTEP_BEGIN",
        "output": "issue236_diag_parent_after_transfer_csv",
        "file_base": "issue236_diag_parent_after_transfer",
    },
    "parent_nonlinear": {
        "pp_execute_on": "NONLINEAR",
        "output_execute_on": "NONLINEAR",
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
    text: str, *, lane: str, field_key: str, functor: str, value_type: str
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


def _insert_context_pp(text: str, *, lane: str, suffix: str, pp_type: str) -> str:
    spec = _LANES[lane]
    name = f"issue236_diag_{lane}_{suffix}"
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


def _instrument_lane(text: str, *, lane: str, fields: dict[str, str]) -> str:
    for field_key, functor in fields.items():
        for value_type in ("min", "max"):
            text = _insert_extreme_pp(
                text,
                lane=lane,
                field_key=field_key,
                functor=functor,
                value_type=value_type,
            )
    for suffix, pp_type in (
        ("step", "NumTimeSteps"),
        ("failed", "NumFailedTimeSteps"),
        ("dt", "TimestepSize"),
    ):
        text = _insert_context_pp(text, lane=lane, suffix=suffix, pp_type=pp_type)
    return _insert_lane_output(text, lane=lane)


def _heavy_input_functor(text: str) -> str:
    path = "FunctorMaterials/heavy_transport"
    if not base.mb.has_block(text, path):
        raise base.Issue236Error("parent lacks FunctorMaterials/heavy_transport")
    value = base.mp.unquote(base.mp.get_parameter(text, path, "electron_number_density"))
    if not value:
        raise base.Issue236Error("heavy_transport lacks electron_number_density functor")
    return value


def _add_snapshot_variables_and_transfer(text: str) -> str:
    text = base._ensure_top_block(text, "AuxVariables")
    for _key, (_source, target, initial) in _SNAPSHOTS.items():
        path = f"AuxVariables/{target}"
        if base.mb.has_block(text, path):
            raise base.Issue236Error(f"duplicate diagnostic snapshot variable: {path}")
        text = base.mb.insert_child_block(
            text,
            "AuxVariables",
            f"""  [{target}]
    type = MooseVariableFVReal
    initial_condition = {initial}
    block = plasma
  []""",
        )

    text = base._ensure_top_block(text, "Transfers")
    transfer_path = f"Transfers/{_SNAPSHOT_TRANSFER}"
    if base.mb.has_block(text, transfer_path):
        raise base.Issue236Error(f"duplicate diagnostic transfer: {transfer_path}")
    sources = " ".join(source for source, _target, _initial in _SNAPSHOTS.values())
    targets = " ".join(target for _source, target, _initial in _SNAPSHOTS.values())
    return base.mb.insert_child_block(
        text,
        "Transfers",
        f"""  [{_SNAPSHOT_TRANSFER}]
    type = MultiAppCopyTransfer
    from_multi_app = electron
    source_variable = '{sources}'
    variable = '{targets}'
    execute_on = TIMESTEP_BEGIN
  []""",
    )


def _parent_fields(text: str) -> dict[str, str]:
    fields = dict(_BASE_FIELDS)
    fields.update({key: target for key, (_source, target, _initial) in _SNAPSHOTS.items()})
    fields["heavy_ne_input"] = _heavy_input_functor(text)
    return fields


def _build_parent_input(production_text: str) -> str:
    text = _nochem_build_parent_input(production_text)
    text = _add_snapshot_variables_and_transfer(text)
    fields = _parent_fields(text)
    text = _instrument_lane(text, lane="parent_after_transfer", fields=fields)
    text = _instrument_lane(text, lane="parent_nonlinear", fields=fields)
    return text


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    text = _nochem_build_child_input(production_text, dt_e=dt_e)
    return _instrument_lane(text, lane="child_accepted", fields=_BASE_FIELDS)


def _lane_audit(text: str, *, lane: str, fields: dict[str, str]) -> dict[str, bool]:
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
        and "FAILED" not in (base.mp.unquote(base.mp.get_parameter(text, output_path, "execute_on")) or "")
    )
    expected = []
    for field_key in fields:
        for value_type in ("min", "max"):
            expected.append(f"issue236_diag_{lane}_{field_key}_{value_type}")
    expected.extend(
        (
            f"issue236_diag_{lane}_step",
            f"issue236_diag_{lane}_failed",
            f"issue236_diag_{lane}_dt",
        )
    )
    for name in expected:
        path = f"Postprocessors/{name}"
        checks[f"diag_pp:{name}"] = (
            base.mb.has_block(text, path)
            and base.mp.unquote(base.mp.get_parameter(text, path, "execute_on"))
            == spec["pp_execute_on"]
            and base.mp.words(base.mp.get_parameter(text, path, "outputs"))
            == [spec["output"]]
        )
    return checks


def _schedule_audit(text: str) -> dict[str, bool]:
    multiapp = "MultiApps/electron"
    operational = "Transfers/fast_from_electron"
    snapshot = f"Transfers/{_SNAPSHOT_TRANSFER}"
    ma_exec = base.mp.unquote(base.mp.get_parameter(text, multiapp, "execute_on"))
    operational_exec = base.mp.unquote(base.mp.get_parameter(text, operational, "execute_on"))
    snapshot_exec = base.mp.unquote(base.mp.get_parameter(text, snapshot, "execute_on"))
    return {
        "diag_multiapp_runs_at_timestep_begin": ma_exec == "TIMESTEP_BEGIN",
        "diag_operational_transfer_same_as_multiapp": operational_exec in (
            None,
            "",
            "SAME_AS_MULTIAPP",
            "TIMESTEP_BEGIN",
        ),
        "diag_snapshot_transfer_at_timestep_begin": snapshot_exec == "TIMESTEP_BEGIN",
    }


def _audit_parent(text: str):
    result = _nochem_audit_parent(text)
    fields = _parent_fields(text)
    result["checks"].update(_lane_audit(text, lane="parent_after_transfer", fields=fields))
    result["checks"].update(_lane_audit(text, lane="parent_nonlinear", fields=fields))
    result["checks"].update(_schedule_audit(text))

    operational = "Transfers/fast_from_electron"
    snapshot = f"Transfers/{_SNAPSHOT_TRANSFER}"
    result["checks"]["diag_operational_payload_unchanged"] = (
        base.mp.words(base.mp.get_parameter(text, operational, "source_variable"))
        == list(base.FAST_SOLVER_VARIABLES)
        and base.mp.words(base.mp.get_parameter(text, operational, "variable"))
        == list(base.FAST_SOLVER_VARIABLES)
    )
    result["checks"]["diag_snapshot_payload_matches_operational_source"] = (
        base.mp.words(base.mp.get_parameter(text, snapshot, "source_variable"))
        == list(base.FAST_SOLVER_VARIABLES)
        and base.mp.words(base.mp.get_parameter(text, snapshot, "variable"))
        == [target for _source, target, _initial in _SNAPSHOTS.values()]
    )
    return _finalize(result)


def _audit_child(text: str, *, dt_e: float):
    result = _nochem_audit_child(text, dt_e=dt_e)
    result["checks"].update(
        _lane_audit(text, lane="child_accepted", fields=_BASE_FIELDS)
    )
    return _finalize(result)


def _self_test():
    result = _nochem_self_test()
    checks = result.setdefault("checks", {})
    parent, child, meta = base.build_split(dt_e=live.ELECTRON_DT_S)
    fields = _parent_fields(parent)
    checks.update(_lane_audit(parent, lane="parent_after_transfer", fields=fields))
    checks.update(_lane_audit(parent, lane="parent_nonlinear", fields=fields))
    checks.update(_lane_audit(child, lane="child_accepted", fields=_BASE_FIELDS))
    checks.update(_schedule_audit(parent))
    checks["diag_schedule_unchanged"] = (
        math.isclose(meta["dt_e_s"], 1.0e-10, rel_tol=0.0, abs_tol=0.0)
        and math.isclose(meta["dt_h_s"], 1.0e-8, rel_tol=0.0, abs_tol=0.0)
        and meta["subcycles_per_heavy"] == 100
    )
    return _finalize(result)


def _find_diag_csv(case_dir: Path, file_base: str) -> Path | None:
    candidates = [
        path
        for path in case_dir.rglob("*.csv")
        if file_base in path.name and path.is_file()
    ]
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


def _attempt_key(row: dict[str, float], lane: str) -> tuple[int, int, float, float] | None:
    names = (
        f"issue236_diag_{lane}_step",
        f"issue236_diag_{lane}_failed",
        f"issue236_diag_{lane}_dt",
        "time",
    )
    if not all(name in row for name in names):
        return None
    return (
        int(round(row[names[0]])),
        int(round(row[names[1]])),
        row[names[2]],
        row[names[3]],
    )


def _same_attempt(a: tuple[int, int, float, float] | None, b: tuple[int, int, float, float] | None) -> bool:
    if a is None or b is None or a[:2] != b[:2]:
        return False
    return math.isclose(a[2], b[2], rel_tol=0.0, abs_tol=1e-20) and math.isclose(
        a[3], b[3], rel_tol=0.0, abs_tol=1e-18
    )


def _compare_values(
    left: dict[str, float] | None,
    right: dict[str, float] | None,
    pairs: dict[str, tuple[str, str]],
+) -> dict[str, Any]:
    result: dict[str, Any] = {"available": bool(left and right), "fields": {}}
    if not left or not right:
        return result
    for label, (left_key, right_key) in pairs.items():
        if left_key not in left or right_key not in right:
            continue
        lv = left[left_key]
        rv = right[right_key]
        scale = max(abs(lv), abs(rv), 1e-300)
        result["fields"][label] = {
            "left": lv,
            "right": rv,
            "absolute_difference": abs(lv - rv),
            "relative_difference": abs(lv - rv) / scale,
        }
    return result


def _within_parent_transfer_compare(row: dict[str, float] | None) -> dict[str, Any]:
    pairs: dict[str, tuple[str, str]] = {}
    for state, snap in (("ne", "ne_snap"), ("nepsilon", "nepsilon_snap"), ("phi", "phi_snap")):
        for extreme in ("min", "max"):
            pairs[f"{state}_{extreme}"] = (
                f"issue236_diag_parent_after_transfer_{state}_{extreme}",
                f"issue236_diag_parent_after_transfer_{snap}_{extreme}",
            )
    return _compare_values(row, row, pairs)


def _between_parent_lanes(
    begin: dict[str, float] | None, nonlinear: dict[str, float] | None
) -> dict[str, Any]:
    pairs: dict[str, tuple[str, str]] = {}
    for field in (*_BASE_FIELDS.keys(), *_SNAPSHOTS.keys(), "heavy_ne_input"):
        for extreme in ("min", "max"):
            pairs[f"{field}_{extreme}"] = (
                f"issue236_diag_parent_after_transfer_{field}_{extreme}",
                f"issue236_diag_parent_nonlinear_{field}_{extreme}",
            )
    return _compare_values(begin, nonlinear, pairs)


def _collect_transfer_diagnostics(case_dir: Path) -> dict[str, Any]:
    paths = {
        lane: _find_diag_csv(case_dir, spec["file_base"])
        for lane, spec in _LANES.items()
    }
    rows = {lane: _numeric_rows(path) for lane, path in paths.items()}
    begin = rows["parent_after_transfer"][-1] if rows["parent_after_transfer"] else None
    begin_key = _attempt_key(begin, "parent_after_transfer") if begin else None
    nonlinear = None
    if begin_key:
        for row in rows["parent_nonlinear"]:
            if _same_attempt(begin_key, _attempt_key(row, "parent_nonlinear")):
                nonlinear = row
                break

    return {
        "files": {lane: str(path) if path else None for lane, path in paths.items()},
        "row_counts": {lane: len(values) for lane, values in rows.items()},
        "latest_parent_attempt_key": begin_key,
        "latest_parent_after_transfer": begin,
        "first_matching_parent_nonlinear": nonlinear,
        "operational_vs_snapshot_same_transfer": _within_parent_transfer_compare(begin),
        "after_transfer_vs_first_nonlinear": _between_parent_lanes(begin, nonlinear),
        "child_accepted_history": rows["child_accepted"][-8:],
        "pairing_policy": "parent lanes matched by (step, failed_count, dt, time); child history is not time-joined to parent",
    }


def _runtime_analysis(case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool):
    result = _nochem_runtime_analysis(
        case_dir,
        dt_e=dt_e,
        returncode=returncode,
        timed_out=timed_out,
    )
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
