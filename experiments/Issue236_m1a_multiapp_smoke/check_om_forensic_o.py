#!/usr/bin/env python3
"""Aggregate Wave-O recorder qualification evidence.

A green gate means the recorder is observationally qualified for later R/L/W
campaigns.  It is not a physics acceptance and does not establish a production
fix for negative O- mass fraction.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


class QualificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise QualificationError(f"missing summary: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise QualificationError(f"summary is not an object: {path}")
    return data


def _forensic(summary: dict[str, Any]) -> dict[str, Any]:
    value = summary.get("om_forensic")
    return value if isinstance(value, dict) else {}


def _close(a: Any, b: Any, *, rel: float = 1.0e-8, abs_: float = 1.0e-14) -> bool:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)


def _same_optional_number(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    return _close(a, b, rel=0.0, abs_=1.0e-18)


def _first(summary: dict[str, Any]) -> dict[str, Any]:
    value = _forensic(summary).get("first_invalid_material_event")
    return value if isinstance(value, dict) else {}


def qualify(o0: dict[str, Any], o1: dict[str, Any], o2: dict[str, Any]) -> dict[str, Any]:
    cases = {"O0": o0, "O1": o1, "O2": o2}
    f = {case: _forensic(summary) for case, summary in cases.items()}
    first = {case: _first(summary) for case, summary in cases.items()}

    checks: dict[str, bool] = {}
    for case in ("O0", "O1", "O2"):
        checks[f"{case}:case_identity"] = f[case].get("case_id") == case
        checks[f"{case}:om_failure_reproduced"] = bool(f[case].get("om_error_signature_present"))
        checks[f"{case}:old_negative_ne_absent"] = not bool(
            f[case].get("negative_electron_signature_present")
        )
        checks[f"{case}:not_timeout"] = not bool(cases[case].get("timed_out"))

    checks["O0:recorder_disabled"] = f["O0"].get("enabled") is False
    checks["O0:no_forensic_record"] = int(f["O0"].get("record_count", -1)) == 0

    for case in ("O1", "O2"):
        checks[f"{case}:recorder_enabled"] = f[case].get("enabled") is True
        checks[f"{case}:record_present"] = int(f[case].get("record_count", 0)) > 0
        checks[f"{case}:consumed_value_negative"] = isinstance(
            first[case].get("consumed_value"), (int, float)
        ) and first[case]["consumed_value"] < 0.0
        checks[f"{case}:argument_identified"] = first[case].get("arg") in {
            "ElemArg",
            "FaceArg",
            "Other",
        }
        checks[f"{case}:state_identified"] = isinstance(first[case].get("state"), int)
        checks[f"{case}:evidence_contract"] = bool(
            f[case].get("evidence_record_present_when_required")
        )

    # Observer-effect gate: enabling the recorder must not move the baseline
    # accepted trajectory or change the production error seen by the transport
    # material.  The printed material Y is deliberately compared separately
    # from the full-precision forensic value.
    for case in ("O1", "O2"):
        checks[f"observer:{case}:parent_final_time"] = _same_optional_number(
            o0.get("parent_final_time_s"), cases[case].get("parent_final_time_s")
        )
        checks[f"observer:{case}:child_final_time"] = _same_optional_number(
            o0.get("child_final_time_s"), cases[case].get("child_final_time_s")
        )
        checks[f"observer:{case}:material_error_value"] = _close(
            f["O0"].get("om_error_value"),
            f[case].get("om_error_value"),
            rel=0.0,
            abs_=1.0e-12,
        )

    # Independent recorder-on replicate must identify the same consumer context.
    checks["replicate:argument_kind"] = first["O1"].get("arg") == first["O2"].get("arg")
    for key in ("elem_id", "face_id", "neighbor_id", "face_side_id", "state", "iteration_type"):
        checks[f"replicate:{key}"] = first["O1"].get(key) == first["O2"].get(key)
    checks["replicate:consumed_value"] = _close(
        first["O1"].get("consumed_value"),
        first["O2"].get("consumed_value"),
        rel=1.0e-10,
        abs_=1.0e-14,
    )

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {
        "schema": "ISSUE236_OM_WAVE_O_QUALIFICATION_V1",
        "status": "PASS" if not failed else "FAIL",
        "evidence_validity": "EVIDENCE_VALID" if not failed else "EVIDENCE_INVALID",
        "claim": (
            "forensic pass-through recorder is observationally qualified for later "
            "Om mechanism experiments"
        ),
        "checks": checks,
        "failed_checks": failed,
        "cases": {
            case: {
                "om_error_value": f[case].get("om_error_value"),
                "parent_final_time_s": cases[case].get("parent_final_time_s"),
                "child_final_time_s": cases[case].get("child_final_time_s"),
                "record_count": f[case].get("record_count"),
                "interpretation": f[case].get("interpretation"),
                "first_invalid_material_event": first[case] or None,
            }
            for case in ("O0", "O1", "O2")
        },
    }


def _apply_manifest_gate(result: dict[str, Any], root: Path | None) -> None:
    if root is None:
        return
    expected_recorder = {"O0": "off", "O1": "on", "O2": "on"}
    manifest_checks: dict[str, bool] = {}
    for case in ("O0", "O1", "O2"):
        path = root / "issue236-om-logs" / case / "manifest.json"
        summary = root / "issue236-om-results" / case / "summary.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        manifest_checks[f"manifest:{case}:exists_and_final"] = bool(data) and data.get("state") == "FINAL"
        manifest_checks[f"manifest:{case}:identity"] = (
            data.get("case") == case and data.get("recorder") == expected_recorder[case]
        )
        current_sha = os.environ.get("GITHUB_SHA")
        manifest_checks[f"manifest:{case}:git_sha"] = (
            current_sha is None or data.get("git_sha") == current_sha
        )
        if summary.is_file():
            digest = hashlib.sha256(summary.read_bytes()).hexdigest()
        else:
            digest = None
        manifest_checks[f"manifest:{case}:summary_hash"] = (
            digest is not None and data.get("summary_sha256") == digest
        )

    result.setdefault("checks", {}).update(manifest_checks)
    failed = sorted(key for key, ok in result["checks"].items() if not ok)
    result["failed_checks"] = failed
    if failed:
        result["status"] = "FAIL"
        result["evidence_validity"] = "EVIDENCE_INVALID"


def _synthetic(case: str, *, enabled: bool) -> dict[str, Any]:
    event = None
    count = 0
    if enabled:
        event = {
            "event": 1,
            "arg": "FaceArg",
            "face_id": 9,
            "elem_id": 10,
            "neighbor_id": None,
            "face_side_id": 10,
            "state": 0,
            "iteration_type": 0,
            "consumed_value": -0.00402221,
            "elem_ref": 0.005,
            "neighbor_ref": None,
        }
        count = 1
    return {
        "timed_out": False,
        "parent_final_time_s": 9.326171875e-10,
        "child_final_time_s": 1.2451171875e-9,
        "om_forensic": {
            "case_id": case,
            "enabled": enabled,
            "record_count": count,
            "first_invalid_material_event": event,
            "interpretation": (
                "NEGATIVE_FACEARG_WITH_NONNEGATIVE_CELL_REFERENCES"
                if enabled
                else "NO_FORENSIC_RECORD"
            ),
            "om_error_signature_present": True,
            "om_error_value": -0.00402221,
            "negative_electron_signature_present": False,
            "evidence_record_present_when_required": True,
        },
    }


def self_test() -> int:
    o0 = _synthetic("O0", enabled=False)
    o1 = _synthetic("O1", enabled=True)
    o2 = _synthetic("O2", enabled=True)
    positive = qualify(o0, o1, o2)
    if positive["status"] != "PASS":
        print(json.dumps({"CHECK_OM_FORENSIC_O_P0": "FAIL", "positive": positive}, indent=2))
        return 1

    mutated = copy.deepcopy(o1)
    mutated["om_forensic"]["record_count"] = 0
    mutated["om_forensic"]["first_invalid_material_event"] = None
    negative = qualify(o0, mutated, o2)
    if negative["status"] != "FAIL":
        print(json.dumps({"CHECK_OM_FORENSIC_O_P0": "FAIL", "negative": negative}, indent=2))
        return 1

    print(json.dumps({"CHECK_OM_FORENSIC_O_P0": "PASS"}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("o0", nargs="?", type=Path)
    parser.add_argument("o1", nargs="?", type=Path)
    parser.add_argument("o2", nargs="?", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not all((args.o0, args.o1, args.o2)):
        parser.error("o0, o1, and o2 summaries are required unless --self-test is used")

    try:
        result = qualify(_load(args.o0), _load(args.o1), _load(args.o2))
    except (QualificationError, OSError, json.JSONDecodeError, ValueError) as error:
        result = {
            "schema": "ISSUE236_OM_WAVE_O_QUALIFICATION_V1",
            "status": "FAIL",
            "evidence_validity": "EVIDENCE_INVALID",
            "checks": {},
            "failed_checks": ["aggregate_input_invalid"],
            "detail": str(error),
        }

    _apply_manifest_gate(result, args.artifact_root)
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
