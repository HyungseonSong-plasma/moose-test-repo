#!/usr/bin/env python3
"""Aggregate Wave-O v2 recorder qualification evidence.

PASS means the pass-through recorder is observationally qualified for later
mechanism experiments. It is not a physics acceptance and is not a production
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


_CASES = ("O0", "O1", "O2")
_EXPECTED_RECORDER = {"O0": "off", "O1": "on", "O2": "on"}
_TRACE_KEYS = (
    "accepted_parent_times",
    "accepted_child",
    "parent_attempts",
    "parent_nonlinear",
    "petsc_monitor",
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise QualificationError(f"missing summary: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise QualificationError(f"summary is not an object: {path}")
    return data


def _analysis(summary: dict[str, Any]) -> dict[str, Any]:
    value = summary.get("analysis")
    return value if isinstance(value, dict) else {}


def _runtime(summary: dict[str, Any]) -> dict[str, Any]:
    value = summary.get("runtime")
    return value if isinstance(value, dict) else {}


def _forensic(summary: dict[str, Any]) -> dict[str, Any]:
    value = _analysis(summary).get("om_forensic")
    return value if isinstance(value, dict) else {}


def _trajectory(summary: dict[str, Any]) -> dict[str, Any]:
    value = _forensic(summary).get("trajectory")
    return value if isinstance(value, dict) else {}


def _first(summary: dict[str, Any]) -> dict[str, Any]:
    value = _forensic(summary).get("first_invalid_material_event")
    return value if isinstance(value, dict) else {}


def _close(a: Any, b: Any, *, rel: float = 1.0e-10, abs_: float = 1.0e-14) -> bool:
    return (
        isinstance(a, (int, float))
        and isinstance(b, (int, float))
        and math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)
    )


def _trace_hashes(summary: dict[str, Any]) -> dict[str, str]:
    value = _trajectory(summary).get("hashes")
    return value if isinstance(value, dict) else {}


def qualify(o0: dict[str, Any], o1: dict[str, Any], o2: dict[str, Any]) -> dict[str, Any]:
    cases = {"O0": o0, "O1": o1, "O2": o2}
    f = {case: _forensic(summary) for case, summary in cases.items()}
    first = {case: _first(summary) for case, summary in cases.items()}
    runtimes = {case: _runtime(summary) for case, summary in cases.items()}
    traces = {case: _trajectory(summary) for case, summary in cases.items()}
    hashes = {case: _trace_hashes(summary) for case, summary in cases.items()}

    checks: dict[str, bool] = {}
    for case in _CASES:
        checks[f"{case}:summary_expected_failure"] = cases[case].get("status") == "FAIL"
        checks[f"{case}:runtime_returncode_present"] = isinstance(
            runtimes[case].get("returncode"), int
        )
        checks[f"{case}:runtime_returncode_nonzero"] = isinstance(
            runtimes[case].get("returncode"), int
        ) and runtimes[case]["returncode"] != 0
        checks[f"{case}:runtime_not_timeout"] = runtimes[case].get("timed_out") is False
        checks[f"{case}:analysis_present"] = bool(_analysis(cases[case]))
        checks[f"{case}:case_identity"] = f[case].get("case_id") == case
        checks[f"{case}:om_failure_reproduced"] = f[case].get(
            "om_error_signature_present"
        ) is True
        checks[f"{case}:old_negative_ne_absent"] = f[case].get(
            "negative_electron_signature_present"
        ) is False

        contract = traces[case].get("execution_contract")
        checks[f"{case}:serial_execution_contract"] = isinstance(contract, dict) and (
            contract.get("mpi_ranks") == 1
            and contract.get("moose_threads") == 1
            and contract.get("direct_process_execution") is True
            and contract.get("petsc_monitor_enabled") is True
        )
        payloads = traces[case].get("payloads")
        checks[f"{case}:trajectory_payloads_present"] = isinstance(payloads, dict) and all(
            key in payloads for key in _TRACE_KEYS
        )
        checks[f"{case}:trajectory_hashes_present"] = all(
            isinstance(hashes[case].get(key), str) and len(hashes[case][key]) == 64
            for key in _TRACE_KEYS
        )

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
        checks[f"{case}:evidence_contract"] = f[case].get(
            "evidence_record_present_when_required"
        ) is True

    for case in ("O1", "O2"):
        for key in _TRACE_KEYS:
            checks[f"observer:{case}:{key}"] = (
                hashes["O0"].get(key) == hashes[case].get(key)
                and isinstance(hashes["O0"].get(key), str)
            )
        checks[f"observer:{case}:material_error_value"] = _close(
            f["O0"].get("om_error_value"),
            f[case].get("om_error_value"),
            rel=0.0,
            abs_=1.0e-12,
        )

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
        "schema": "ISSUE236_OM_WAVE_O_QUALIFICATION_V2",
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
                "solver_returncode": runtimes[case].get("returncode"),
                "om_error_value": f[case].get("om_error_value"),
                "record_count": f[case].get("record_count"),
                "interpretation": f[case].get("interpretation"),
                "trajectory_hashes": hashes[case],
                "first_invalid_material_event": first[case] or None,
            }
            for case in _CASES
        },
    }


def _json_or_empty(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _apply_manifest_gate(result: dict[str, Any], root: Path | None) -> None:
    if root is None:
        result.setdefault("checks", {})["manifest:artifact_root_required"] = False
        result["failed_checks"] = sorted(
            key for key, ok in result["checks"].items() if not ok
        )
        result["status"] = "FAIL"
        result["evidence_validity"] = "EVIDENCE_INVALID"
        return

    checks: dict[str, bool] = {}
    manifests: dict[str, dict[str, Any]] = {}
    current_sha = os.environ.get("GITHUB_SHA")
    expected_build = os.environ.get("BUILD_BASE_REF")
    expected_dependencies = {
        "MOOSE": os.environ.get("MOOSE_SHA"),
        "CRANE": os.environ.get("CRANE_SHA"),
        "SQUIRREL": os.environ.get("SQUIRREL_SHA"),
        "ZAPDOS": os.environ.get("ZAPDOS_SHA"),
    }

    for case in _CASES:
        manifest_path = root / "issue236-om-logs" / case / "manifest.json"
        summary_path = root / "issue236-om-results" / case / "summary.json"
        data = _json_or_empty(manifest_path)
        manifests[case] = data

        checks[f"manifest:{case}:final_validated"] = (
            bool(data) and data.get("state") == "FINAL_VALIDATED"
        )
        checks[f"manifest:{case}:identity"] = (
            data.get("case") == case
            and data.get("recorder") == _EXPECTED_RECORDER[case]
        )
        checks[f"manifest:{case}:git_sha"] = isinstance(data.get("git_sha"), str) and (
            current_sha is None or data.get("git_sha") == current_sha
        )
        checks[f"manifest:{case}:build_base"] = isinstance(data.get("build_base"), str) and (
            expected_build is None or data.get("build_base") == expected_build
        )
        deps = data.get("dependencies")
        checks[f"manifest:{case}:dependencies"] = isinstance(deps, dict) and all(
            isinstance(deps.get(name), str)
            and (expected is None or deps.get(name) == expected)
            for name, expected in expected_dependencies.items()
        )
        checks[f"manifest:{case}:physics_opt_sha256"] = (
            isinstance(data.get("physics_opt_sha256"), str)
            and len(data["physics_opt_sha256"]) == 64
        )
        checks[f"manifest:{case}:input_sha256"] = (
            isinstance(data.get("input_sha256"), dict) and bool(data["input_sha256"])
        )
        checks[f"manifest:{case}:observer_input_sha256"] = (
            isinstance(data.get("observer_input_sha256"), dict)
            and bool(data["observer_input_sha256"])
        )
        summary_digest = _sha256(summary_path)
        checks[f"manifest:{case}:summary_hash"] = (
            summary_digest is not None and data.get("summary_sha256") == summary_digest
        )
        checks[f"manifest:{case}:runtime_log_sha256"] = (
            isinstance(data.get("runtime_log_sha256"), str)
            and len(data["runtime_log_sha256"]) == 64
        )
        checks[f"manifest:{case}:physics_opt_started"] = data.get("physics_opt_started") is True
        checks[f"manifest:{case}:not_timeout"] = data.get("timed_out") is False
        checks[f"manifest:{case}:solver_returncode"] = isinstance(
            data.get("solver_returncode"), int
        ) and data["solver_returncode"] != 0
        checks[f"manifest:{case}:expected_om_error"] = data.get(
            "expected_om_error"
        ) is True
        checks[f"manifest:{case}:runtime_evidence_valid"] = data.get(
            "runtime_evidence_valid"
        ) is True

    for field in ("git_sha", "run_id", "run_attempt", "build_base", "dependencies"):
        values = [manifests[case].get(field) for case in _CASES]
        checks[f"manifest:cross_case:{field}"] = (
            values[0] is not None and values[0] == values[1] == values[2]
        )

    o1_inputs = manifests["O1"].get("input_sha256")
    o2_inputs = manifests["O2"].get("input_sha256")
    checks["manifest:recorder_replicate:exact_inputs"] = (
        isinstance(o1_inputs, dict) and bool(o1_inputs) and o1_inputs == o2_inputs
    )

    observer_maps = [manifests[case].get("observer_input_sha256") for case in _CASES]
    checks["manifest:observer:canonical_inputs_equal"] = (
        all(isinstance(value, dict) and bool(value) for value in observer_maps)
        and observer_maps[0] == observer_maps[1] == observer_maps[2]
    )

    result.setdefault("checks", {}).update(checks)
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
        }
        count = 1
    payloads = {
        "accepted_parent_times": ["9.326171875e-10"],
        "accepted_child": [{"time": "1.2451171875e-09"}],
        "parent_attempts": [{"time": "9.326171875e-10"}],
        "parent_nonlinear": [{"time": "9.326171875e-10", "x": "1"}],
        "petsc_monitor": ["0 SNES Function norm 1.0"],
    }
    hashes = {
        key: hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for key, value in payloads.items()
    }
    return {
        "status": "FAIL",
        "runtime": {"returncode": 1, "timed_out": False},
        "analysis": {
            "om_forensic": {
                "case_id": case,
                "enabled": enabled,
                "record_count": count,
                "first_invalid_material_event": event,
                "interpretation": "NEGATIVE_FACEARG_OBSERVED" if enabled else "NO_FORENSIC_RECORD",
                "om_error_signature_present": True,
                "om_error_value": -0.00402221,
                "negative_electron_signature_present": False,
                "evidence_record_present_when_required": True,
                "trajectory": {
                    "execution_contract": {
                        "mpi_ranks": 1,
                        "moose_threads": 1,
                        "direct_process_execution": True,
                        "petsc_monitor_enabled": True,
                    },
                    "payloads": payloads,
                    "hashes": hashes,
                },
            }
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
    mutated["analysis"]["om_forensic"]["trajectory"]["hashes"]["parent_nonlinear"] = "0" * 64
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
            "schema": "ISSUE236_OM_WAVE_O_QUALIFICATION_V2",
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
