#!/usr/bin/env python3
"""Wave-O qualification runner for exact O- invalid-evaluation forensics.

This wrapper keeps the Run-35 C electron-mirror configuration fixed
(``mirrors_one_term``) and changes only whether heavy transport reads ``w_Om``
directly or through ``PhysicsPassThroughForensicMaterial``. The pass-through
property returns exactly ``w_Om(r, state)`` and records an already-negative value
before the existing ``PhysicsThermalDiffusionMaterial`` guard terminates the run.

Qualification cases are selected by environment:

* O0: recorder off; original heavy-transport mass-fraction binding.
* O1: recorder on.
* O2: recorder on, independent replicate.

The recorder is evidence only. It does not clamp, floor, change wall physics,
or change the live/frozen electron representation selected by Run-35 C.
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run_live_ci_boundary_diag as boundary

base = boundary.base
live = boundary.live

if boundary._MODE != "mirrors_one_term":
    raise RuntimeError(
        "Wave-O requires ISSUE236_NE_BOUNDARY_MODE=mirrors_one_term so the "
        "previous negative-electron blocker remains disabled."
    )

_RECORDER_ENV = "ISSUE236_OM_FORENSIC"
_CASE_ENV = "ISSUE236_OM_CASE_ID"
_RECORDER_RAW = os.environ.get(_RECORDER_ENV, "off").strip().lower()
if _RECORDER_RAW not in {"off", "on"}:
    raise RuntimeError(f"{_RECORDER_ENV} must be 'off' or 'on', got {_RECORDER_RAW!r}")
_RECORDER_ENABLED = _RECORDER_RAW == "on"
_CASE_ID = os.environ.get(_CASE_ENV, "O0" if not _RECORDER_ENABLED else "O1").strip()
if not re.fullmatch(r"O[0-9]+", _CASE_ID):
    raise RuntimeError(f"{_CASE_ENV} must look like O0/O1/O2, got {_CASE_ID!r}")

_HEAVY = "FunctorMaterials/heavy_transport"
_FORENSIC_NAME = "issue236_om_forensic"
_FORENSIC_PATH = f"FunctorMaterials/{_FORENSIC_NAME}"
_FORENSIC_PROPERTY = "issue236_forensic_w_Om"
_ORIGINAL_OM = "w_Om"
_OM_ERROR = re.compile(r"Species 'Om' has Y=([-+0-9.eE]+)")
_MARKER = "ISSUE236_OM_FORENSIC_V1"

_prior_build_parent = base.build_parent_input
_prior_build_child = base.build_child_input
_prior_audit_parent = base._audit_parent
_prior_audit_child = base._audit_child
_prior_self_test = base.self_test
_prior_runtime_analysis = base._runtime_analysis


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["failed_checks"] = sorted(key for key, ok in result["checks"].items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


def _forensic_filename(role: str) -> str:
    return f"issue236_om_forensic_{role}.jsonl"


def _wire_forensic_om(text: str, *, role: str) -> str:
    if not base.mb.has_block(text, _HEAVY):
        raise base.Issue236Error(f"{role} input lacks {_HEAVY}")

    mass_fractions = base.mp.words(base.mp.get_parameter(text, _HEAVY, "mass_fractions"))
    if mass_fractions.count(_ORIGINAL_OM) != 1:
        raise base.Issue236Error(
            f"{role} heavy_transport must contain exactly one {_ORIGINAL_OM}; got {mass_fractions}"
        )

    if not _RECORDER_ENABLED:
        base.mb.require_absent(text, _FORENSIC_PATH)
        return text

    base.mb.require_absent(text, _FORENSIC_PATH)
    text = base.mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [{_FORENSIC_NAME}]
    type = PhysicsPassThroughForensicMaterial
    source = {_ORIGINAL_OM}
    property_name = {_FORENSIC_PROPERTY}
    diagnostic_file = '{_forensic_filename(role)}'
    diagnostic_tag = '{_CASE_ID}-{role}'
    block = plasma
  []""",
    )

    rewritten = [
        _FORENSIC_PROPERTY if item == _ORIGINAL_OM else item for item in mass_fractions
    ]
    return base.mp.upsert_parameter(
        text,
        _HEAVY,
        "mass_fractions",
        "'" + " ".join(rewritten) + "'",
    )


def _build_parent_input(production_text: str) -> str:
    return _wire_forensic_om(_prior_build_parent(production_text), role="parent")


def _build_child_input(production_text: str, *, dt_e: float) -> str:
    return _wire_forensic_om(_prior_build_child(production_text, dt_e=dt_e), role="child")


def _forensic_audit(text: str, *, role: str) -> dict[str, bool]:
    mass_fractions = base.mp.words(base.mp.get_parameter(text, _HEAVY, "mass_fractions"))
    checks: dict[str, bool] = {
        f"om_forensic:{role}:mirrors_one_term_base": boundary._MODE == "mirrors_one_term",
    }

    if not _RECORDER_ENABLED:
        checks[f"om_forensic:{role}:material_absent_when_off"] = not base.mb.has_block(
            text, _FORENSIC_PATH
        )
        checks[f"om_forensic:{role}:direct_om_binding_when_off"] = (
            mass_fractions.count(_ORIGINAL_OM) == 1
            and _FORENSIC_PROPERTY not in mass_fractions
        )
        return checks

    checks[f"om_forensic:{role}:material_present"] = base.mb.has_block(text, _FORENSIC_PATH)
    checks[f"om_forensic:{role}:transparent_binding"] = (
        base.mp.unquote(base.mp.get_parameter(text, _FORENSIC_PATH, "type"))
        == "PhysicsPassThroughForensicMaterial"
        and base.mp.unquote(base.mp.get_parameter(text, _FORENSIC_PATH, "source"))
        == _ORIGINAL_OM
        and base.mp.unquote(base.mp.get_parameter(text, _FORENSIC_PATH, "property_name"))
        == _FORENSIC_PROPERTY
        and base.mp.unquote(base.mp.get_parameter(text, _FORENSIC_PATH, "diagnostic_file"))
        == _forensic_filename(role)
        and base.mp.unquote(base.mp.get_parameter(text, _FORENSIC_PATH, "diagnostic_tag"))
        == f"{_CASE_ID}-{role}"
        and base.mp.words(base.mp.get_parameter(text, _FORENSIC_PATH, "block")) == ["plasma"]
    )
    checks[f"om_forensic:{role}:heavy_transport_rewired_once"] = (
        mass_fractions.count(_FORENSIC_PROPERTY) == 1 and _ORIGINAL_OM not in mass_fractions
    )
    return checks


def _audit_parent(text: str):
    result = _prior_audit_parent(text)
    result["checks"].update(_forensic_audit(text, role="parent"))
    result["om_forensic_case"] = _CASE_ID
    result["om_forensic_enabled"] = _RECORDER_ENABLED
    return _finalize(result)


def _audit_child(text: str, *, dt_e: float):
    result = _prior_audit_child(text, dt_e=dt_e)
    result["checks"].update(_forensic_audit(text, role="child"))
    result["om_forensic_case"] = _CASE_ID
    result["om_forensic_enabled"] = _RECORDER_ENABLED
    return _finalize(result)


def _self_test():
    try:
        result = _prior_self_test()
        parent, child, meta = base.build_split(dt_e=live.ELECTRON_DT_S)
    except base.Issue236Error as error:
        return {
            "status": "FAIL",
            "checks": {"om_forensic_builds": False},
            "failed_checks": ["om_forensic_builds"],
            "detail": {"split_error": str(error)},
            "om_forensic_case": _CASE_ID,
            "om_forensic_enabled": _RECORDER_ENABLED,
        }

    result.setdefault("checks", {}).update(_forensic_audit(parent, role="parent"))
    result["checks"].update(_forensic_audit(child, role="child"))
    result["checks"]["om_forensic:schedule_unchanged"] = (
        meta["subcycles_per_heavy"] == 100
        and math.isclose(meta["dt_h_s"], 1.0e-8, rel_tol=0.0, abs_tol=0.0)
        and math.isclose(meta["dt_e_s"], 1.0e-10, rel_tol=0.0, abs_tol=0.0)
    )
    result["om_forensic_case"] = _CASE_ID
    result["om_forensic_enabled"] = _RECORDER_ENABLED
    return _finalize(result)


def _parse_value(raw: str) -> Any:
    if raw == "NA":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_record(line: str, *, path: Path) -> dict[str, Any] | None:
    text = line.strip()
    if not text.startswith(_MARKER + " "):
        return None
    record: dict[str, Any] = {"schema": _MARKER, "path": str(path)}
    for token in text.split()[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        record[key] = _parse_value(value)
    return record


def _forensic_records(case_dir: Path) -> list[dict[str, Any]]:
    roots = (case_dir, case_dir.parent)
    files: dict[str, Path] = {}
    for root in roots:
        if root.exists():
            for path in root.rglob("issue236_om_forensic_*.jsonl"):
                files[str(path.resolve())] = path

    records: list[dict[str, Any]] = []
    for path in files.values():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            parsed = _parse_record(line, path=path)
            if parsed is not None:
                records.append(parsed)
    return sorted(records, key=lambda item: (int(item.get("event", 10**18)), item["path"]))


def _om_error_value(log_text: str) -> float | None:
    match = _OM_ERROR.search(log_text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _record_interpretation(record: dict[str, Any] | None) -> str:
    if not record:
        return "NO_FORENSIC_RECORD"
    consumed = record.get("consumed_value")
    if not isinstance(consumed, (int, float)) or consumed >= 0.0:
        return "INVALID_FORENSIC_RECORD"
    if record.get("arg") == "ElemArg":
        return "NEGATIVE_ELEMARG_OBSERVED"
    if record.get("arg") == "FaceArg":
        cell_ref = record.get("cell_ref")
        if isinstance(cell_ref, (int, float)) and cell_ref >= 0.0:
            return "NEGATIVE_FACEARG_WITH_NONNEGATIVE_SAME_STATE_CELL_REFERENCE"
        return "NEGATIVE_FACEARG_OBSERVED"
    return "NEGATIVE_OTHER_ARGUMENT_OBSERVED"


def _runtime_analysis(case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool):
    result = _prior_runtime_analysis(
        case_dir, dt_e=dt_e, returncode=returncode, timed_out=timed_out
    )
    records = _forensic_records(case_dir)
    first = records[0] if records else None
    log_text = boundary._read_runtime_log(case_dir)
    result["om_forensic"] = {
        "case_id": _CASE_ID,
        "enabled": _RECORDER_ENABLED,
        "schema": _MARKER,
        "record_count": len(records),
        "first_invalid_material_event": first,
        "interpretation": _record_interpretation(first),
        "om_error_signature_present": "Species 'Om' has Y=" in log_text,
        "om_error_value": _om_error_value(log_text),
        "negative_electron_signature_present": boundary._NEGATIVE_NE_SIGNATURE in log_text,
        "evidence_record_present_when_required": (not _RECORDER_ENABLED) or bool(records),
        "claim_scope": "first observed invalid Om evaluation on the heavy-transport mass-fraction functor path",
    }
    return result


base.build_parent_input = _build_parent_input
base.build_child_input = _build_child_input
base._audit_parent = _audit_parent
base._audit_child = _audit_child
base.self_test = _self_test
base._runtime_analysis = _runtime_analysis

if __name__ == "__main__":
    raise SystemExit(base.main())
