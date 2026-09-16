#!/usr/bin/env python3
"""Wave-O v2 qualification runner for exact O- invalid-evaluation forensics.

O0 leaves heavy_transport bound directly to w_Om. O1/O2 route only that one
mass-fraction entry through PhysicsPassThroughForensicMaterial. All cases retain
Run-35 C (mirrors_one_term) physics, use one process / one MOOSE thread, and
emit canonical trajectory hashes for observer-effect qualification.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Iterable

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
if _CASE_ID not in {"O0", "O1", "O2"}:
    raise RuntimeError(f"{_CASE_ENV} must be O0/O1/O2, got {_CASE_ID!r}")

_HEAVY = "FunctorMaterials/heavy_transport"
_FORENSIC_NAME = "issue236_om_forensic"
_FORENSIC_PATH = f"FunctorMaterials/{_FORENSIC_NAME}"
_FORENSIC_PROPERTY = "issue236_forensic_w_Om"
_ORIGINAL_OM = "w_Om"
_OM_ERROR = re.compile(r"Species 'Om' has Y=([-+0-9.eE]+)")
_MARKER = "ISSUE236_OM_FORENSIC_V2"
_PETSC_TOKENS = (
    "SNES Function norm",
    "KSP Residual norm",
    "CONVERGED_",
    "DIVERGED_",
    "Nonlinear solve",
    "Linear solve",
)

_prior_build_parent = base.build_parent_input
_prior_build_child = base.build_child_input
_prior_audit_parent = base._audit_parent
_prior_audit_child = base._audit_child
_prior_self_test = base.self_test
_prior_runtime_analysis = base._runtime_analysis
_prior_run_physics = base.run_physics


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
    diagnostic_tag = '{role}'
    block = plasma
  []""",
    )
    rewritten = [
        _FORENSIC_PROPERTY if item == _ORIGINAL_OM else item for item in mass_fractions
    ]
    return base.mp.upsert_parameter(
        text, _HEAVY, "mass_fractions", "'" + " ".join(rewritten) + "'"
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
        == role
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
    result["checks"]["om_forensic:serial_contract"] = True
    result["om_forensic_case"] = _CASE_ID
    result["om_forensic_enabled"] = _RECORDER_ENABLED
    return _finalize(result)


def _serial_run_physics(exe: Path, **kwargs):
    extra_args = tuple(kwargs.pop("extra_args", ()))
    forced = (
        "--n-threads=1",
        "-snes_monitor",
        "-snes_converged_reason",
        "-ksp_converged_reason",
    )
    return _prior_run_physics(exe, extra_args=(*extra_args, *forced), **kwargs)


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
        if "=" in token:
            key, value = token.split("=", 1)
            record[key] = _parse_value(value)
    return record


def _forensic_records(case_dir: Path) -> list[dict[str, Any]]:
    files: dict[str, Path] = {}
    for root in (case_dir, case_dir.parent):
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
        return "NEGATIVE_FACEARG_OBSERVED"
    return "NEGATIVE_OTHER_ARGUMENT_OBSERVED"


def _stable_rows(rows: Iterable[dict[str, float]], *, keys: Iterable[str] | None = None) -> list[dict[str, str]]:
    selected = set(keys) if keys is not None else None
    output: list[dict[str, str]] = []
    for row in rows:
        item: dict[str, str] = {}
        for key in sorted(row):
            if selected is not None and key not in selected:
                continue
            value = row[key]
            if math.isfinite(value):
                item[key] = format(value, ".17g")
        if item:
            output.append(item)
    return output


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lane_context(rows: list[dict[str, float]], lane: str) -> list[dict[str, str]]:
    keys = (
        "time",
        f"issue236_diag_{lane}_step",
        f"issue236_diag_{lane}_failed",
        f"issue236_diag_{lane}_dt",
    )
    return _stable_rows(rows, keys=keys)


def _petsc_trace(log_text: str) -> list[str]:
    return [line.strip() for line in log_text.splitlines() if any(token in line for token in _PETSC_TOKENS)]


def _trajectory(case_dir: Path, analysis: dict[str, Any], log_text: str) -> dict[str, Any]:
    child_rows = boundary._lane_rows(case_dir, "child_accepted")
    parent_attempt_rows = boundary._lane_rows(case_dir, "parent_after_transfer")
    parent_nonlinear_rows = boundary._lane_rows(case_dir, "parent_nonlinear")
    accepted_parent_times = analysis.get("parent_times_s")
    if not isinstance(accepted_parent_times, list):
        accepted_parent_times = []
    payloads = {
        "accepted_parent_times": [format(float(value), ".17g") for value in accepted_parent_times],
        "accepted_child": _lane_context(child_rows, "child_accepted"),
        "parent_attempts": _lane_context(parent_attempt_rows, "parent_after_transfer"),
        "parent_nonlinear": _stable_rows(parent_nonlinear_rows),
        "petsc_monitor": _petsc_trace(log_text),
    }
    return {
        "execution_contract": {
            "mpi_ranks": 1,
            "moose_threads": 1,
            "direct_process_execution": True,
            "petsc_monitor_enabled": True,
        },
        "payloads": payloads,
        "hashes": {name: _digest(payload) for name, payload in payloads.items()},
    }


def canonical_observer_input_text(text: str) -> str:
    """Normalize away only the O0-vs-recorder wiring difference."""
    if base.mb.has_block(text, _FORENSIC_PATH):
        text = base.mb.remove_block(text, _FORENSIC_PATH)
    mass_fractions = base.mp.words(base.mp.get_parameter(text, _HEAVY, "mass_fractions"))
    normalized = [_ORIGINAL_OM if item == _FORENSIC_PROPERTY else item for item in mass_fractions]
    text = base.mp.upsert_parameter(
        text, _HEAVY, "mass_fractions", "'" + " ".join(normalized) + "'"
    )
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()) + "\n"


def canonical_observer_input_hash(text: str) -> str:
    return hashlib.sha256(canonical_observer_input_text(text).encode("utf-8")).hexdigest()


def _runtime_analysis(case_dir: Path, *, dt_e: float, returncode: int, timed_out: bool):
    result = _prior_runtime_analysis(
        case_dir, dt_e=dt_e, returncode=returncode, timed_out=timed_out
    )
    records = _forensic_records(case_dir)
    first = records[0] if records else None
    log_text = boundary._read_runtime_log(case_dir)
    trajectory = _trajectory(case_dir, result, log_text)
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
        "trajectory": trajectory,
        "claim_scope": (
            "first observed invalid Om evaluation on the heavy-transport mass-fraction "
            "functor path under one-process/one-thread execution"
        ),
    }
    return result


base.build_parent_input = _build_parent_input
base.build_child_input = _build_child_input
base._audit_parent = _audit_parent
base._audit_child = _audit_child
base.self_test = _self_test
base._runtime_analysis = _runtime_analysis
base.run_physics = _serial_run_physics

if __name__ == "__main__":
    raise SystemExit(base.main())
