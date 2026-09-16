#!/usr/bin/env python3
"""Aggregate Issue-236 L nonlinear-globalization discriminator evidence.

Evidence validity is separated from the scientific outcome. A valid run may
show suppression, delay, no material effect, or another later failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from physics_harness.adapters.moose import parameters as mp

_CASES = ("L0_fullstep", "L1_damp_0p5", "L2_backtracking")
_EXPECTED = {
    "L0_fullstep": {"line_search": "none", "damping": None},
    "L1_damp_0p5": {"line_search": "basic", "damping": 0.5},
    "L2_backtracking": {"line_search": "bt", "damping": None},
}
_DAMPING_OPT = "-snes_linesearch_damping"
_EXPECTED_OM = -0.00402221
_EXPECTED_BASELINE_ATTEMPT = 1.2451171875e-9
_EXPECTED_BUILD_BASE = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)
_EXPECTED_DEPS = {
    "MOOSE_SHA": "9f388366ccf38b9c34542ec5561198249fde0ac9",
    "CRANE_SHA": "ba26970cf419dcac563a20ed7079d445bc6341c3",
    "SQUIRREL_SHA": "16a26d504f3ee11161a86d4e3ebf3c0e5f2afbb1",
    "ZAPDOS_SHA": "9eceffbc46048c3760bbfa9a7f1ca681ae35af1d",
}


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"not a JSON object: {path}")
    return data


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _analysis(summary: dict[str, Any]) -> dict[str, Any]:
    value = summary.get("analysis")
    return value if isinstance(value, dict) else {}


def _runtime(summary: dict[str, Any]) -> dict[str, Any]:
    value = summary.get("runtime")
    return value if isinstance(value, dict) else {}


def _forensic(summary: dict[str, Any]) -> dict[str, Any]:
    value = _analysis(summary).get("om_forensic")
    return value if isinstance(value, dict) else {}


def _control(summary: dict[str, Any]) -> dict[str, Any]:
    value = _analysis(summary).get("om_nonlinear_control")
    return value if isinstance(value, dict) else {}


def _first(summary: dict[str, Any]) -> dict[str, Any]:
    value = _forensic(summary).get("first_invalid_material_event")
    return value if isinstance(value, dict) else {}


def _solver_pairs(text: str) -> list[tuple[str, str]]:
    names = mp.words(mp.get_parameter(text, "Executioner", "petsc_options_iname"))
    values = mp.words(mp.get_parameter(text, "Executioner", "petsc_options_value"))
    if len(names) != len(values):
        raise ValueError(f"PETSc option/value length mismatch: {len(names)} != {len(values)}")
    return list(zip(names, values))


def _canonical_parent(text: str) -> str:
    pairs = [(name, value) for name, value in _solver_pairs(text) if name != _DAMPING_OPT]
    text = mp.upsert_parameter(text, "Executioner", "line_search", "OM_L_NORMALIZED")
    text = mp.upsert_parameter(
        text,
        "Executioner",
        "petsc_options_iname",
        "'" + " ".join(name for name, _ in pairs) + "'",
    )
    text = mp.upsert_parameter(
        text,
        "Executioner",
        "petsc_options_value",
        "'" + " ".join(value for _, value in pairs) + "'",
    )
    return "\n".join(line.rstrip() for line in text.splitlines()).strip() + "\n"


def _control_exact(text: str, case: str) -> bool:
    expected = _EXPECTED[case]
    line_search = mp.unquote(mp.get_parameter(text, "Executioner", "line_search"))
    pairs = dict(_solver_pairs(text))
    if line_search != expected["line_search"]:
        return False
    damping = expected["damping"]
    if damping is None:
        return _DAMPING_OPT not in pairs
    value = _float(pairs.get(_DAMPING_OPT))
    return value is not None and math.isclose(value, float(damping), rel_tol=0.0, abs_tol=0.0)


def _max_parent_attempt(summary: dict[str, Any]) -> float | None:
    trajectory = _forensic(summary).get("trajectory")
    if not isinstance(trajectory, dict):
        return None
    payloads = trajectory.get("payloads")
    if not isinstance(payloads, dict):
        return None
    rows = payloads.get("parent_attempts")
    if not isinstance(rows, list):
        return None
    times = [
        value
        for row in rows
        if isinstance(row, dict) and (value := _float(row.get("time"))) is not None
    ]
    return max(times) if times else None


def _progress(summary: dict[str, Any]) -> float | None:
    candidates = [_float(_analysis(summary).get("parent_final_time_s")), _max_parent_attempt(summary)]
    finite = [value for value in candidates if value is not None]
    return max(finite) if finite else None


def _case_signal(case: str, summary: dict[str, Any], baseline_progress: float) -> str:
    forensic = _forensic(summary)
    runtime = _runtime(summary)
    progress = _progress(summary)
    om_error = forensic.get("om_error_signature_present") is True
    value = _float(forensic.get("om_error_value"))
    first = _first(summary)
    if case == "L0_fullstep":
        return "BASELINE_ELEMARG_OM_FAILURE" if om_error else "BASELINE_NOT_REPRODUCED"
    if not om_error:
        if runtime.get("returncode") == 0 and progress is not None and progress > baseline_progress:
            return "OM_NEGATIVITY_SUPPRESSED_THROUGH_RUN_HORIZON"
        if progress is not None and progress > baseline_progress:
            return "OM_NEGATIVITY_NOT_OBSERVED_BEFORE_LATER_STOP"
        return "OM_NEGATIVITY_NOT_OBSERVED_WITHOUT_PROGRESS_GAIN"
    if progress is not None and progress > baseline_progress * (1.0 + 1e-6):
        return "OM_NEGATIVITY_DELAYED"
    if value is not None and abs(value) < abs(_EXPECTED_OM) * 0.99 and first.get("arg") == "ElemArg":
        return "OM_NEGATIVITY_WEAKENED"
    return "OM_NEGATIVITY_MATERIALLY_UNCHANGED"


def _overall_signal(signals: dict[str, str]) -> str:
    altered = {
        "OM_NEGATIVITY_SUPPRESSED_THROUGH_RUN_HORIZON",
        "OM_NEGATIVITY_NOT_OBSERVED_BEFORE_LATER_STOP",
        "OM_NEGATIVITY_DELAYED",
        "OM_NEGATIVITY_WEAKENED",
    }
    if any(signals[case] in altered for case in _CASES[1:]):
        return "GLOBALIZATION_SENSITIVE_ELEMARG_NEGATIVITY"
    if all(signals[case] == "OM_NEGATIVITY_MATERIALLY_UNCHANGED" for case in _CASES[1:]):
        return "NO_MATERIAL_GLOBALIZATION_EFFECT"
    return "MIXED_OR_INCONCLUSIVE"


def self_test() -> int:
    baseline = """[Executioner]
  type = Transient
  line_search = none
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]
"""
    damped = mp.upsert_parameter(baseline, "Executioner", "line_search", "basic")
    damped = mp.upsert_parameter(
        damped,
        "Executioner",
        "petsc_options_iname",
        "'-pc_type -pc_factor_shift_type -snes_linesearch_damping'",
    )
    damped = mp.upsert_parameter(
        damped, "Executioner", "petsc_options_value", "'lu NONZERO 0.5'"
    )
    backtracking = mp.upsert_parameter(baseline, "Executioner", "line_search", "bt")
    changed = damped.replace("type = Transient", "type = Steady")
    ok = (
        _canonical_parent(baseline) == _canonical_parent(damped) == _canonical_parent(backtracking)
        and _canonical_parent(baseline) != _canonical_parent(changed)
        and _control_exact(baseline, "L0_fullstep")
        and _control_exact(damped, "L1_damp_0p5")
        and _control_exact(backtracking, "L2_backtracking")
    )
    print(json.dumps({"CHECK_OM_NONLINEAR_L_P0": "PASS" if ok else "FAIL"}))
    return 0 if ok else 1


def qualify(root: Path) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    cases: dict[str, dict[str, Any]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    parent_canonical: dict[str, str] = {}
    child_sha: dict[str, str | None] = {}
    physics_sha: dict[str, str] = {}

    provenance = _load(root / "issue236-om-l-logs" / "provenance.json")
    checks["provenance:git_sha"] = isinstance(provenance.get("git_sha"), str) and len(provenance["git_sha"]) == 40
    checks["provenance:run_id"] = str(provenance.get("run_id", "")).isdigit()
    checks["provenance:run_attempt"] = str(provenance.get("run_attempt", "")).isdigit()
    checks["provenance:build_base"] = provenance.get("build_base") == _EXPECTED_BUILD_BASE
    for key, expected in _EXPECTED_DEPS.items():
        checks[f"provenance:{key}"] = provenance.get(key) == expected
    checks["provenance:physics_opt_sha256"] = (
        isinstance(provenance.get("physics_opt_sha256"), str)
        and len(provenance["physics_opt_sha256"]) == 64
    )

    for case in _CASES:
        result_root = root / "issue236-om-l-results" / case
        log_root = root / "issue236-om-l-logs" / case
        summary = _load(result_root / "summary.json")
        summaries[case] = summary
        runtime = _runtime(summary)
        forensic = _forensic(summary)
        control = _control(summary)
        first = _first(summary)
        parent_path = result_root / "case" / "input.i"
        child_path = result_root / "case" / "electron_sub.i"
        parent_text = parent_path.read_text(encoding="utf-8")
        parent_canonical[case] = _canonical_parent(parent_text)
        child_sha[case] = _sha(child_path)

        checks[f"{case}:runtime_returncode_present"] = isinstance(runtime.get("returncode"), int)
        checks[f"{case}:runtime_not_timeout"] = runtime.get("timed_out") is False
        checks[f"{case}:recorder_enabled"] = forensic.get("enabled") is True
        checks[f"{case}:old_negative_ne_absent"] = forensic.get("negative_electron_signature_present") is False
        checks[f"{case}:control_mode"] = control.get("mode") == case
        checks[f"{case}:control_scope"] = control.get("scope") == "parent Executioner only"
        checks[f"{case}:control_input_exact"] = _control_exact(parent_text, case)
        checks[f"{case}:child_input_present"] = child_sha[case] is not None
        checks[f"{case}:self_test_pass"] = _load(result_root / "self_test.json").get("status") == "PASS"

        sha_text = (log_root / "physics-opt.sha256").read_text(encoding="utf-8").strip().split()
        sha_value = sha_text[0] if sha_text else ""
        physics_sha[case] = sha_value
        checks[f"{case}:physics_opt_sha256"] = (
            len(sha_value) == 64 and sha_value == provenance.get("physics_opt_sha256")
        )
        cases[case] = {
            "runtime_returncode": runtime.get("returncode"),
            "wall_seconds": runtime.get("wall_seconds"),
            "progress_s": _progress(summary),
            "om_error_present": forensic.get("om_error_signature_present"),
            "om_error_value": forensic.get("om_error_value"),
            "first_invalid_material_event": first or None,
            "line_search": control.get("line_search"),
            "damping": control.get("damping"),
        }

    baseline = summaries["L0_fullstep"]
    baseline_forensic = _forensic(baseline)
    baseline_first = _first(baseline)
    baseline_progress = _progress(baseline)
    checks["baseline:om_failure_reproduced"] = baseline_forensic.get("om_error_signature_present") is True
    baseline_value = _float(baseline_forensic.get("om_error_value"))
    checks["baseline:om_value_reproduced"] = (
        baseline_value is not None
        and math.isclose(baseline_value, _EXPECTED_OM, rel_tol=1e-6, abs_tol=1e-10)
    )
    checks["baseline:first_invalid_parent_elemarg"] = (
        baseline_first.get("tag") == "parent"
        and baseline_first.get("arg") == "ElemArg"
        and _float(baseline_first.get("consumed_value")) is not None
        and float(baseline_first["consumed_value"]) < 0.0
    )
    checks["baseline:element_2400"] = baseline_first.get("elem_id") == 2400
    checks["baseline:terminal_attempt_reproduced"] = (
        baseline_progress is not None
        and math.isclose(
            baseline_progress, _EXPECTED_BASELINE_ATTEMPT, rel_tol=1e-6, abs_tol=1e-15
        )
    )

    baseline_parent = parent_canonical["L0_fullstep"]
    for case in _CASES[1:]:
        checks[f"semantic:{case}:parent_only_declared_controls"] = parent_canonical[case] == baseline_parent
        checks[f"semantic:{case}:child_byte_identical"] = child_sha[case] == child_sha["L0_fullstep"]
    checks["same_binary_all_cases"] = len(set(physics_sha.values())) == 1

    if baseline_progress is None:
        signals = {case: "INVALID_BASELINE_PROGRESS" for case in _CASES}
    else:
        signals = {case: _case_signal(case, summaries[case], baseline_progress) for case in _CASES}
    for case in _CASES:
        cases[case]["scientific_signal"] = signals[case]

    failed = sorted(key for key, ok in checks.items() if not ok)
    return {
        "schema": "ISSUE236_OM_NONLINEAR_L_V1",
        "status": "PASS" if not failed else "FAIL",
        "evidence_validity": "EVIDENCE_VALID" if not failed else "EVIDENCE_INVALID",
        "failed_checks": failed,
        "checks": checks,
        "cases": cases,
        "scientific_conclusion": _overall_signal(signals) if not failed else "NOT_INTERPRETABLE",
        "claim_scope": (
            "sensitivity of the parent ElemArg Om negativity to parent nonlinear globalization; "
            "wall physics, FV representation, chemistry, and timestep schedule are unchanged"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    try:
        result = qualify(args.artifact_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        result = {
            "schema": "ISSUE236_OM_NONLINEAR_L_V1",
            "status": "FAIL",
            "evidence_validity": "EVIDENCE_INVALID",
            "failed_checks": ["aggregate_input_invalid"],
            "detail": str(error),
        }
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
