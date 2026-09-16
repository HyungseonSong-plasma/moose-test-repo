#!/usr/bin/env python3
"""Aggregate Wave-O v3 recorder qualification evidence.

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

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp


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
    "terminal_om_error",
)
_OM_ERROR_TEXT = "Species 'Om' has Y="
_HEAVY = "FunctorMaterials/heavy_transport"
_FORENSIC_PATH = "FunctorMaterials/issue236_om_forensic"
_FORENSIC_PROPERTY = "issue236_forensic_w_Om"
_ORIGINAL_OM = "w_Om"
_EXPECTED_MANIFEST_SCHEMA = "ISSUE236_OM_WAVE_O_ARTIFACT_V3"
_EXPECTED_SUMMARY_SCHEMA = "ISSUE236_OM_WAVE_O_QUALIFICATION_V3"


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


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _float_value(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _times(rows: Any) -> list[float]:
    if not isinstance(rows, list):
        return []
    output: list[float] = []
    for row in rows:
        if isinstance(row, dict):
            value = _float_value(row.get("time"))
        else:
            value = _float_value(row)
        if value is not None:
            output.append(value)
    return output


def _trajectory_checks(case: str, summary: dict[str, Any]) -> dict[str, bool]:
    trajectory = _trajectory(summary)
    payloads = trajectory.get("payloads")
    hashes = trajectory.get("hashes")
    contract = trajectory.get("execution_contract")
    checks: dict[str, bool] = {}

    checks[f"{case}:trajectory_payloads_mapping"] = isinstance(payloads, dict)
    checks[f"{case}:trajectory_hashes_mapping"] = isinstance(hashes, dict)
    if not isinstance(payloads, dict) or not isinstance(hashes, dict):
        for key in _TRACE_KEYS:
            checks[f"{case}:trajectory:{key}:substantive"] = False
            checks[f"{case}:trajectory:{key}:hash_recomputed"] = False
    else:
        for key in _TRACE_KEYS:
            payload = payloads.get(key)
            checks[f"{case}:trajectory:{key}:substantive"] = (
                isinstance(payload, list) and len(payload) > 0
            )
            checks[f"{case}:trajectory:{key}:hash_recomputed"] = (
                key in payloads
                and isinstance(hashes.get(key), str)
                and hashes.get(key) == _digest(payload)
            )

        accepted_parent = _times(payloads.get("accepted_parent_times"))
        accepted_child = _times(payloads.get("accepted_child"))
        parent_attempts = _times(payloads.get("parent_attempts"))
        parent_nonlinear = _times(payloads.get("parent_nonlinear"))
        checks[f"{case}:trajectory:accepted_parent_positive"] = bool(accepted_parent) and max(
            accepted_parent
        ) > 0.0
        checks[f"{case}:trajectory:accepted_child_present"] = bool(accepted_child)
        checks[f"{case}:trajectory:failing_attempt_after_accept"] = (
            bool(accepted_parent)
            and bool(parent_attempts)
            and max(parent_attempts) > max(accepted_parent)
        )
        checks[f"{case}:trajectory:nonlinear_reaches_failing_attempt"] = (
            bool(parent_attempts)
            and bool(parent_nonlinear)
            and math.isclose(
                max(parent_nonlinear), max(parent_attempts), rel_tol=0.0, abs_tol=1.0e-15
            )
        )
        terminal = payloads.get("terminal_om_error")
        checks[f"{case}:trajectory:terminal_om_error_exact"] = (
            isinstance(terminal, list)
            and len(terminal) > 0
            and all(isinstance(line, str) for line in terminal)
            and any(_OM_ERROR_TEXT in line for line in terminal)
        )

    processors = contract.get("observed_num_processors") if isinstance(contract, dict) else None
    threads = contract.get("observed_num_threads") if isinstance(contract, dict) else None
    checks[f"{case}:serial:direct_request"] = isinstance(contract, dict) and (
        contract.get("requested_direct_process_execution") is True
        and contract.get("requested_moose_threads") == 1
    )
    checks[f"{case}:serial:runtime_banner"] = (
        isinstance(processors, list)
        and len(processors) > 0
        and isinstance(threads, list)
        and len(threads) > 0
    )
    checks[f"{case}:serial:runtime_observed"] = (
        isinstance(contract, dict)
        and contract.get("serial_observed") is True
        and isinstance(processors, list)
        and all(value == 1 for value in processors)
        and isinstance(threads, list)
        and all(value == 1 for value in threads)
    )
    return checks


def qualify(o0: dict[str, Any], o1: dict[str, Any], o2: dict[str, Any]) -> dict[str, Any]:
    cases = {"O0": o0, "O1": o1, "O2": o2}
    f = {case: _forensic(summary) for case, summary in cases.items()}
    first = {case: _first(summary) for case, summary in cases.items()}
    runtimes = {case: _runtime(summary) for case, summary in cases.items()}
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
        checks.update(_trajectory_checks(case, cases[case]))

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
        "schema": _EXPECTED_SUMMARY_SCHEMA,
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


def _canonical_observer_input_text(text: str) -> str:
    if mb.has_block(text, _FORENSIC_PATH):
        text = mb.remove_block(text, _FORENSIC_PATH)
    mass_fractions = mp.words(mp.get_parameter(text, _HEAVY, "mass_fractions"))
    normalized = [_ORIGINAL_OM if item == _FORENSIC_PROPERTY else item for item in mass_fractions]
    text = mp.upsert_parameter(
        text, _HEAVY, "mass_fractions", "'" + " ".join(normalized) + "'"
    )
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()) + "\n"


def _canonical_observer_input_hash(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
        normalized = _canonical_observer_input_text(text)
    except (OSError, ValueError):
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _actual_input_maps(result_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    paths = sorted(path for path in result_root.rglob("*.i") if path.is_file())
    raw: dict[str, str] = {}
    normalized: dict[str, str] = {}
    for path in paths:
        key = str(path.relative_to(result_root))
        raw[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        value = _canonical_observer_input_hash(path)
        if value is not None:
            normalized[key] = value
    return raw, normalized


def _sha256_file_value(path: Path) -> str | None:
    try:
        tokens = path.read_text(encoding="utf-8", errors="replace").split()
    except OSError:
        return None
    if not tokens:
        return None
    value = tokens[0].lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        return None
    return value


def _apply_manifest_gate(
    result: dict[str, Any], root: Path | None, summaries: dict[str, dict[str, Any]]
) -> None:
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
        log_root = root / "issue236-om-logs" / case
        result_root = root / "issue236-om-results" / case
        manifest_path = log_root / "manifest.json"
        summary_path = result_root / "summary.json"
        runtime_log = result_root / "runtime.log"
        physics_sha_path = log_root / "physics-opt.sha256"
        data = _json_or_empty(manifest_path)
        manifests[case] = data
        summary = summaries[case]
        runtime = _runtime(summary)
        forensic = _forensic(summary)

        checks[f"manifest:{case}:schema"] = data.get("schema") == _EXPECTED_MANIFEST_SCHEMA
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

        stored_exe_hash = data.get("physics_opt_sha256")
        checks[f"manifest:{case}:physics_opt_sha256"] = (
            isinstance(stored_exe_hash, str) and len(stored_exe_hash) == 64
        )
        checks[f"manifest:{case}:physics_opt_hash_file"] = (
            _sha256_file_value(physics_sha_path) == stored_exe_hash
        )

        actual_raw_inputs, actual_observer_inputs = _actual_input_maps(result_root)
        checks[f"manifest:{case}:input_sha256"] = (
            bool(actual_raw_inputs) and data.get("input_sha256") == actual_raw_inputs
        )
        checks[f"manifest:{case}:observer_input_sha256"] = (
            bool(actual_observer_inputs)
            and set(actual_observer_inputs) == set(actual_raw_inputs)
            and data.get("observer_input_sha256") == actual_observer_inputs
        )

        summary_digest = _sha256(summary_path)
        checks[f"manifest:{case}:summary_hash"] = (
            summary_digest is not None and data.get("summary_sha256") == summary_digest
        )
        runtime_digest = _sha256(runtime_log)
        checks[f"manifest:{case}:runtime_log_hash"] = (
            runtime_digest is not None and data.get("runtime_log_sha256") == runtime_digest
        )
        try:
            log_text = runtime_log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log_text = ""
        checks[f"manifest:{case}:physics_opt_started"] = (
            data.get("physics_opt_started") is True
            and isinstance(runtime.get("returncode"), int)
            and bool(log_text)
        )
        checks[f"manifest:{case}:not_timeout"] = (
            data.get("timed_out") is False and runtime.get("timed_out") is False
        )
        checks[f"manifest:{case}:solver_returncode"] = (
            isinstance(data.get("solver_returncode"), int)
            and data.get("solver_returncode") == runtime.get("returncode")
            and data["solver_returncode"] != 0
        )
        checks[f"manifest:{case}:expected_om_error"] = (
            data.get("expected_om_error") is True
            and forensic.get("om_error_signature_present") is True
            and _OM_ERROR_TEXT in log_text
        )
        checks[f"manifest:{case}:trajectory_hashes_match_summary"] = (
            data.get("trajectory_hashes") == _trace_hashes(summary)
        )
        checks[f"manifest:{case}:runtime_evidence_valid"] = data.get(
            "runtime_evidence_valid"
        ) is True

    for field in ("git_sha", "run_id", "run_attempt", "build_base", "dependencies"):
        values = [manifests[case].get(field) for case in _CASES]
        checks[f"manifest:cross_case:{field}"] = (
            values[0] is not None and values[0] == values[1] == values[2]
        )

    executable_hashes = [manifests[case].get("physics_opt_sha256") for case in _CASES]
    checks["manifest:cross_case:physics_opt_sha256"] = (
        isinstance(executable_hashes[0], str)
        and executable_hashes[0] == executable_hashes[1] == executable_hashes[2]
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
        "accepted_parent_times": ["9.3261718750000003e-10"],
        "accepted_child": [{"time": "1.1451171875000001e-09"}],
        "parent_attempts": [
            {
                "time": "1.2451171875000001e-09",
                "issue236_diag_parent_after_transfer_step": "8",
                "issue236_diag_parent_after_transfer_failed": "0",
                "issue236_diag_parent_after_transfer_dt": "3.125e-10",
            }
        ],
        "parent_nonlinear": [{"time": "1.2451171875000001e-09", "residual": "1"}],
        "petsc_monitor": ["0 SNES Function norm 1.0"],
        "terminal_om_error": [
            "PhysicsThermalDiffusionMaterial requires non-negative mass fractions. Species 'Om' has Y=-0.00402221"
        ],
    }
    hashes = {key: _digest(value) for key, value in payloads.items()}
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
                        "requested_direct_process_execution": True,
                        "requested_moose_threads": 1,
                        "observed_num_processors": [1],
                        "observed_num_threads": [1],
                        "parallelism_banner_present": True,
                        "serial_observed": True,
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
    mutated["analysis"]["om_forensic"]["trajectory"]["payloads"]["parent_nonlinear"] = []
    mutated["analysis"]["om_forensic"]["trajectory"]["hashes"]["parent_nonlinear"] = _digest([])
    negative = qualify(o0, mutated, o2)
    if negative["status"] != "FAIL":
        print(json.dumps({"CHECK_OM_FORENSIC_O_P0": "FAIL", "empty_trace": negative}, indent=2))
        return 1

    forged = copy.deepcopy(o1)
    forged["analysis"]["om_forensic"]["trajectory"]["hashes"]["parent_nonlinear"] = "0" * 64
    negative_hash = qualify(o0, forged, o2)
    if negative_hash["status"] != "FAIL":
        print(json.dumps({"CHECK_OM_FORENSIC_O_P0": "FAIL", "forged_hash": negative_hash}, indent=2))
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

    summaries: dict[str, dict[str, Any]] = {}
    try:
        summaries = {
            "O0": _load(args.o0),
            "O1": _load(args.o1),
            "O2": _load(args.o2),
        }
        result = qualify(summaries["O0"], summaries["O1"], summaries["O2"])
    except (QualificationError, OSError, json.JSONDecodeError, ValueError) as error:
        result = {
            "schema": _EXPECTED_SUMMARY_SCHEMA,
            "status": "FAIL",
            "evidence_validity": "EVIDENCE_INVALID",
            "checks": {},
            "failed_checks": ["aggregate_input_invalid"],
            "detail": str(error),
        }

    if summaries:
        _apply_manifest_gate(result, args.artifact_root, summaries)
    else:
        result.setdefault("checks", {})["manifest:summaries_available"] = False
        result["failed_checks"] = sorted(
            key for key, ok in result["checks"].items() if not ok
        )
        result["status"] = "FAIL"
        result["evidence_validity"] = "EVIDENCE_INVALID"

    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
