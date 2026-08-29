"""Issue #44 output-observation contract layer for the Issue #43 fast-plasma runner."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path
from typing import Any

from . import evidence
from . import execution_contract as ec
from . import fast_plasma_relaxation_v2 as v2
from . import fast_plasma_relaxation_v3 as v3
from . import fast_plasma_relaxation_v4 as v4
from . import output_observation_contract as ooc
from .runtime import run_qpx


_RAW_BUILD_ELECTRON = v3._build_electron_fixed
_RAW_BUILD_ONEWAY = v3._build_oneway_fixed
_RAW_BUILD_FEEDBACK = v3._build_feedback_fixed
_RAW_BUILD_EXECUTION_CONTRACT = v3._build_execution_contract
_RAW_RUN_CASE_SAFE = v3._run_case_safe


def _with_output_contract(text: str, *, dt: float) -> str:
    return ooc.apply_microtime_output_contract(text, dt=dt)


def _build_electron_v5(base_text: str, *, dt: float, steps: int) -> str:
    return _with_output_contract(
        _RAW_BUILD_ELECTRON(base_text, dt=dt, steps=steps), dt=dt
    )


def _build_oneway_v5(
    base_text: str, *, dt: float, steps: int, radial_span: float
) -> str:
    return _with_output_contract(
        _RAW_BUILD_ONEWAY(base_text, dt=dt, steps=steps, radial_span=radial_span),
        dt=dt,
    )


def _build_feedback_v5(
    base_text: str, *, dt: float, steps: int, radial_span: float
) -> str:
    return _with_output_contract(
        _RAW_BUILD_FEEDBACK(base_text, dt=dt, steps=steps, radial_span=radial_span),
        dt=dt,
    )


def _augment_execution_contract(case_id: str, input_text: str) -> dict[str, Any]:
    contract = _RAW_BUILD_EXECUTION_CONTRACT(case_id, input_text)
    try:
        separation = float(contract["numerical_regime"]["declared_controls"]["dt"])
        report = ooc.observation_report(
            input_text, required_time_separation=separation
        )
    except Exception:
        # Lower-layer v3 unit tests use a synthetic input without [Outputs].
        if "[Outputs]" not in input_text:
            return contract
        raise

    contract["framework_effective"]["controls"]["output_observation"] = report
    contract["evidence"]["requirements"].append(
        "distinct CSV physical-time rows under the declared output observation contract"
    )
    contract["checks"].extend(
        [
            {
                "id": "csv-row-tolerance-below-physical-separation",
                "phase": "P1",
                "meaning": (
                    "CSV duplicate-row tolerance must be smaller than the minimum "
                    "physical time separation required by the claim"
                ),
                "left": {
                    "path": (
                        "framework_effective.controls.output_observation."
                        "csv.new_row_tolerance"
                    )
                },
                "op": "lt",
                "right": {"path": "numerical_regime.declared_controls.dt"},
                "on_fail": "OUTPUT_OBSERVATION_CONTRACT_FAIL",
            },
            {
                "id": "csv-time-tolerance-below-physical-separation",
                "phase": "P1",
                "meaning": (
                    "CSV time tolerance must be smaller than the physical time "
                    "separation required for observation"
                ),
                "left": {
                    "path": (
                        "framework_effective.controls.output_observation."
                        "csv.time_tolerance"
                    )
                },
                "op": "lt",
                "right": {"path": "numerical_regime.declared_controls.dt"},
                "on_fail": "OUTPUT_OBSERVATION_CONTRACT_FAIL",
            },
            {
                "id": "csv-observes-timestep-end",
                "phase": "P1",
                "meaning": "CSV output must observe solved TIMESTEP_END states",
                "left": {
                    "path": (
                        "framework_effective.controls.output_observation."
                        "csv.timestep_end_enabled"
                    )
                },
                "op": "eq",
                "right": {"value": True},
                "on_fail": "OUTPUT_OBSERVATION_CONTRACT_FAIL",
            },
            {
                "id": "csv-every-step",
                "phase": "P1",
                "meaning": "CSV output must be eligible on every discriminator timestep",
                "left": {
                    "path": (
                        "framework_effective.controls.output_observation."
                        "csv.time_step_interval"
                    )
                },
                "op": "eq",
                "right": {"value": 1},
                "on_fail": "OUTPUT_OBSERVATION_CONTRACT_FAIL",
            },
            {
                "id": "console-row-tolerance-supporting-observability",
                "phase": "P1",
                "severity": "warn",
                "meaning": (
                    "Console row tolerance should preserve supporting micro-time "
                    "postprocessor observability"
                ),
                "left": {
                    "path": (
                        "framework_effective.controls.output_observation."
                        "console.new_row_tolerance"
                    )
                },
                "op": "lt",
                "right": {"path": "numerical_regime.declared_controls.dt"},
                "on_fail": "OUTPUT_OBSERVABILITY_WARNING",
            },
        ]
    )
    ec.validate_contract(contract)
    return contract


def _solver_trajectory(log_path: Path) -> dict[str, Any]:
    if not log_path.is_file():
        return {"status": "MISSING_LOG", "time_steps_seen": 0, "converged_steps": 0}
    text = log_path.read_text(errors="replace")
    matches = re.findall(
        r"Time Step\s+(\d+),\s*time\s*=\s*([+\-0-9.eE]+)"
        r"(?:,\s*dt\s*=\s*([+\-0-9.eE]+))?",
        text,
    )
    steps: list[dict[str, Any]] = []
    for step_raw, time_raw, dt_raw in matches:
        try:
            step = int(step_raw)
            time = float(time_raw)
            dt = float(dt_raw) if dt_raw else None
        except ValueError:
            continue
        if step <= 0:
            continue
        steps.append({"step": step, "time": time, "dt": dt})
    converged_steps = len(re.findall(r"Solve Converged!", text))
    result: dict[str, Any] = {
        "status": "PASS",
        "time_steps_seen": len(steps),
        "converged_steps": converged_steps,
    }
    if steps:
        result["final_step_seen"] = steps[-1]["step"]
        result["solver_final_time"] = steps[-1]["time"]
        dts = [item["dt"] for item in steps if item["dt"] is not None]
        if dts:
            result["solver_dt_min"] = min(dts)
            result["solver_dt_max"] = max(dts)
    return result


def _run_case_v5(**kwargs: Any) -> dict[str, Any]:
    result = _RAW_RUN_CASE_SAFE(**kwargs)
    case_id = str(kwargs.get("case_id", "unknown"))
    measurements_root = Path(kwargs["measurements_root"])
    p3_log = measurements_root / case_id / "p3_runtime.log"
    if p3_log.is_file():
        result["p3_log"] = str(p3_log)
        result["solver_trajectory"] = _solver_trajectory(p3_log)
        result = v2._attach_residual(result)
    return result


def _install_v5_repairs() -> None:
    v3._build_electron_fixed = _build_electron_v5
    v3._build_oneway_fixed = _build_oneway_v5
    v3._build_feedback_fixed = _build_feedback_v5
    v3._build_execution_contract = _augment_execution_contract
    v3._run_case_safe = _run_case_v5


def _p2_check_input_args() -> tuple[str, ...]:
    return ("--check-input", "--color", "off")


def _p2_output_introspection_args() -> tuple[str, ...]:
    # --show-outputs is emitted by constructed Console output during INITIAL.
    # num_steps=0 preserves object construction while prohibiting a physical
    # transient timestep. A positive Time Step in the log is a hard phase leak.
    return (
        "--show-outputs",
        "--color",
        "off",
        "Executioner/num_steps=0",
    )


def _positive_timestep_numbers(text: str) -> list[int]:
    return [
        int(raw)
        for raw in re.findall(r"(?m)^\s*Time Step\s+([1-9]\d*)\b", text)
    ]


def _output_execute_flags(text: str, output_name: str) -> list[str] | None:
    match = re.search(
        rf'(?mi)^\s*{re.escape(output_name)}\s+"([^"]*)"\s*$',
        text,
    )
    if not match:
        return None
    return [token.upper() for token in match.group(1).split() if token]


def _framework_output_evidence(
    log_path: Path,
    report: dict[str, Any],
    *,
    check_input_returncode: int,
    introspection_returncode: int | None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(
        check_id: str,
        passed: bool,
        observed: Any,
        required: Any,
        *,
        severity: str = "hard",
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "PASS" if passed else "FAIL",
                "severity": severity,
                "observed": observed,
                "required": required,
            }
        )

    csv = report["csv"]
    separation = float(report["required_time_separation"])
    add(
        "qpx-accepted-explicit-output-contract",
        check_input_returncode == 0,
        check_input_returncode,
        0,
    )
    add(
        "accepted-csv-row-tolerance",
        float(csv.get("new_row_tolerance", float("inf"))) < separation,
        csv.get("new_row_tolerance"),
        f"< {separation}",
    )
    add(
        "accepted-csv-time-tolerance",
        float(csv.get("time_tolerance", float("inf"))) < separation,
        csv.get("time_tolerance"),
        f"< {separation}",
    )
    add(
        "accepted-csv-every-step",
        csv.get("time_step_interval") == 1,
        csv.get("time_step_interval"),
        1,
    )
    add(
        "accepted-csv-row-identity",
        str(csv.get("new_row_detection_columns", "")).lower() == "time",
        csv.get("new_row_detection_columns"),
        "time",
    )

    if not log_path.is_file():
        add("output-introspection-log", False, "missing", "present")
        blockers = [
            item
            for item in checks
            if item["severity"] == "hard" and item["status"] == "FAIL"
        ]
        return {
            "status": "HOLD",
            "checks": checks,
            "blockers": blockers,
            "warnings": [],
            "positive_time_steps": [],
            "provenance": {
                "parameter_values": (
                    "hashed packaged input.i plus user-local qpx-opt --check-input acceptance"
                ),
                "output_schedule": (
                    "user-local qpx-opt --show-outputs under Executioner/num_steps=0 guard"
                ),
            },
        }

    text = log_path.read_text(errors="replace")
    positive_steps = _positive_timestep_numbers(text)
    out_flags = _output_execute_flags(text, "out")
    console_flags = _output_execute_flags(text, "console")

    add(
        "output-introspection-returncode",
        introspection_returncode == 0,
        introspection_returncode,
        0,
    )
    add(
        "output-introspection-no-physical-timestep",
        not positive_steps,
        positive_steps,
        [],
    )
    add(
        "show-outputs-section",
        "Outputs:" in text,
        "present" if "Outputs:" in text else "missing",
        "present",
    )
    add(
        "show-outputs-csv-object",
        out_flags is not None,
        out_flags,
        "out output object present",
    )
    add(
        "show-outputs-csv-timestep-end",
        out_flags is not None and "TIMESTEP_END" in out_flags,
        out_flags,
        "contains TIMESTEP_END",
    )
    add(
        "show-outputs-console-object",
        console_flags is not None,
        console_flags,
        "console output object present",
        severity="warn",
    )

    blockers = [
        item
        for item in checks
        if item["severity"] == "hard" and item["status"] == "FAIL"
    ]
    warnings = [
        item
        for item in checks
        if item["severity"] == "warn" and item["status"] == "FAIL"
    ]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "positive_time_steps": positive_steps,
        "effective_execute_on": {
            "out": out_flags,
            "console": console_flags,
        },
        "provenance": {
            "parameter_values": (
                "hashed packaged input.i plus user-local qpx-opt --check-input acceptance"
            ),
            "output_schedule": (
                "user-local qpx-opt --show-outputs under Executioner/num_steps=0 guard"
            ),
        },
    }


def _classify_p2_failure(log_path: Path, returncode: int) -> dict[str, Any]:
    if returncode == 0:
        return {
            "status": "PASS",
            "class": None,
            "reason": None,
            "detail": None,
        }
    if not log_path.is_file():
        return {
            "status": "HOLD",
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "MISSING_P2_LOG",
            "detail": None,
        }

    text = log_path.read_text(errors="replace")
    unused = re.search(r"unused parameter ['\"]([^'\"]+)['\"]", text)
    if unused:
        return {
            "status": "HOLD",
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "UNUSED_PARAMETER",
            "detail": unused.group(1),
        }
    if "ADFParser::JITCompile() failed" in text:
        return {
            "status": "HOLD",
            "class": "ENVIRONMENT_OR_BUILD_FAIL",
            "reason": "JIT_COMPILE_FAIL",
            "detail": None,
        }

    error_detail: str | None = None
    error_match = re.search(r"\*\*\* ERROR \*\*\*\s*\n([^\n]+)", text)
    if error_match:
        error_detail = error_match.group(1).strip()
    return {
        "status": "HOLD",
        "class": "HARNESS_OR_CONSTRUCTION_FAIL",
        "reason": "QPX_CHECK_INPUT_FAIL",
        "detail": error_detail,
    }


def _run_output_preflight(*, qpx: str | None, results_root: str | None) -> int:
    exe = v2.resolve_executable(qpx)
    v2.validate_executable(exe)

    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / v2.v1.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise SystemExit(f"missing accepted qvt electron control: {base_case}")

    mesh = v2.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    input_text = _build_feedback_v5(
        base_text,
        dt=v2.DT_FEEDBACK_SMALL,
        steps=v2.N_STEPS,
        radial_span=radial_span,
    )
    v2.validate_parser_symbols_text(input_text)

    report = ooc.observation_report(
        input_text, required_time_separation=v2.DT_FEEDBACK_SMALL
    )
    static_decision = ooc.evaluate_observation_report(report)
    if static_decision["status"] != "PASS":
        print("ISSUE44_OUTPUT_PREFLIGHT_P1: HOLD")
        print("ISSUE44_OUTPUT_PREFLIGHT_REASON: static output contract failed")
        return 2

    evidence_root = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    root = evidence.ensure_fresh_directory(
        evidence_root / f"issue44_output_preflight_{evidence.utc_timestamp()}"
    )
    case_dir = root / "case"
    v2.v1._copy_case(base_case, case_dir, input_text)
    v2.v1._validate_assets(case_dir)

    input_path = case_dir / "input.i"
    check_log_path = root / "p2_check_input.log"
    introspection_log_path = root / "p2_output_introspection.log"
    summary_path = root / "summary.json"

    p2 = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_path.name,
        log_path=check_log_path,
        extra_args=_p2_check_input_args(),
        stream=False,
    )
    p2_failure = _classify_p2_failure(check_log_path, p2.returncode)

    introspection = None
    if p2.returncode == 0:
        introspection = run_qpx(
            exe,
            cwd=case_dir,
            input_name=input_path.name,
            log_path=introspection_log_path,
            extra_args=_p2_output_introspection_args(),
            stream=False,
        )

    framework_evidence = _framework_output_evidence(
        introspection_log_path,
        report,
        check_input_returncode=p2.returncode,
        introspection_returncode=(
            introspection.returncode if introspection is not None else None
        ),
    )
    p3_executed = bool(framework_evidence.get("positive_time_steps"))

    status = (
        "PASS"
        if (
            p2.returncode == 0
            and introspection is not None
            and introspection.returncode == 0
            and framework_evidence["status"] == "PASS"
            and not p3_executed
        )
        else "HOLD"
    )
    summary = {
        "issue": 44,
        "mode": "output-preflight",
        "status": status,
        "p3_executed": p3_executed,
        "identity": {
            **evidence.identity_record(executable=exe, input_path=input_path),
            "qpx_sha256": evidence.sha256_file(exe),
        },
        "p1_output_contract": {
            "report": report,
            "decision": static_decision,
        },
        "p2_qpx_introspection": {
            "check_input": {
                "returncode": p2.returncode,
                "wall_seconds": p2.wall_seconds,
                "log": str(check_log_path),
                "failure": p2_failure,
            },
            "output_introspection": {
                "returncode": (
                    introspection.returncode if introspection is not None else None
                ),
                "wall_seconds": (
                    introspection.wall_seconds if introspection is not None else None
                ),
                "log": str(introspection_log_path),
                "args": list(_p2_output_introspection_args()),
            },
            "framework_evidence": framework_evidence,
        },
    }
    v2._write_json(summary_path, summary)

    print(f"ISSUE44_OUTPUT_PREFLIGHT_P1: {static_decision['status']}")
    print(
        "ISSUE44_OUTPUT_PREFLIGHT_P2_CHECK_INPUT: "
        + ("PASS" if p2.returncode == 0 else "FAIL")
    )
    if p2.returncode != 0:
        print(f"ISSUE44_OUTPUT_PREFLIGHT_P2_CLASS: {p2_failure['class']}")
        print(f"ISSUE44_OUTPUT_PREFLIGHT_P2_REASON: {p2_failure['reason']}")
        if p2_failure["detail"]:
            print(f"ISSUE44_OUTPUT_PREFLIGHT_P2_DETAIL: {p2_failure['detail']}")
    print(
        "ISSUE44_OUTPUT_PREFLIGHT_P2_OUTPUT_INTROSPECTION: "
        + (
            "PASS"
            if introspection is not None and introspection.returncode == 0
            else "HOLD"
        )
    )
    print(
        "ISSUE44_OUTPUT_PREFLIGHT_FRAMEWORK_EVIDENCE: "
        f"{framework_evidence['status']}"
    )
    if framework_evidence["status"] != "PASS":
        for blocker in framework_evidence.get("blockers", []):
            print(
                "ISSUE44_OUTPUT_PREFLIGHT_FRAMEWORK_BLOCKER: "
                f"{blocker['id']} observed={blocker.get('observed')!r} "
                f"required={blocker.get('required')!r}"
            )
    print(f"ISSUE44_OUTPUT_PREFLIGHT_PRECLASS: {status}")
    print(f"ISSUE44_OUTPUT_PREFLIGHT_CHECK_LOG: {check_log_path}")
    print(f"ISSUE44_OUTPUT_PREFLIGHT_LOG: {introspection_log_path}")
    print(f"ISSUE44_OUTPUT_PREFLIGHT_SUMMARY: {summary_path}")
    return 0 if status == "PASS" else 2


def self_test() -> int:
    try:
        if v4.self_test() != 0:
            raise AssertionError("v4 self-test failed")
        if ooc.self_test() != 0:
            raise AssertionError("output-observation contract self-test failed")

        base = """[Executioner]
  type = Transient
  dt = 1e-14
  end_time = 5e-14
  num_steps = 5
  dtmin = 1e-15
  timestep_tolerance = 1e-17
  abort_on_solve_fail = true
[]
[Outputs]
  csv = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""
        tuned = ooc.apply_microtime_output_contract(base, dt=1.0e-14)
        report = ooc.observation_report(tuned, required_time_separation=1.0e-14)
        if ooc.evaluate_observation_report(report)["status"] != "PASS":
            raise AssertionError("valid observation report did not pass")
        augmented = _augment_execution_contract("Issue44_output_contract_probe", tuned)
        if ec.evaluate_contract(augmented, phase="P1")["status"] != "PASS":
            raise AssertionError("valid output-aware execution contract failed P1")

        mutated = ooc._set_parameter(
            tuned, "Outputs/out", "new_row_tolerance", "1e-12"
        )
        bad_report = ooc.observation_report(
            mutated, required_time_separation=1.0e-14
        )
        if ooc.evaluate_observation_report(bad_report)["status"] != "HOLD":
            raise AssertionError("historical output-row suppression mutation was not rejected")
        bad_contract = _augment_execution_contract("Issue44_output_contract_bad", mutated)
        if ec.evaluate_contract(bad_contract, phase="P1")["status"] != "HOLD":
            raise AssertionError("execution contract did not reject output-row suppression")

        check_args = _p2_check_input_args()
        if "--check-input" not in check_args or "--show-outputs" in check_args:
            raise AssertionError("P2 check-input arguments are not phase isolated")
        if "--no-color" in check_args or check_args[-2:] != ("--color", "off"):
            raise AssertionError("P2 check-input did not use current color CLI contract")

        introspection_args = _p2_output_introspection_args()
        if "--show-outputs" not in introspection_args:
            raise AssertionError("output introspection did not request --show-outputs")
        if "--check-input" in introspection_args:
            raise AssertionError("output introspection leaked check-input early exit")
        if "Executioner/num_steps=0" not in introspection_args:
            raise AssertionError("output introspection lacks zero-step phase guard")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log = tmp_path / "p3_runtime.log"
            log.write_text(
                "Time Step 1, time = 1e-14, dt = 1e-14\n"
                " Solve Converged!\n"
                "Time Step 2, time = 2e-14, dt = 1e-14\n"
                " Solve Converged!\n"
            )
            trajectory = _solver_trajectory(log)
            if trajectory.get("converged_steps") != 2:
                raise AssertionError("solver trajectory parser lost converged steps")
            if trajectory.get("solver_final_time") != 2.0e-14:
                raise AssertionError("solver trajectory parser lost final time")

            introspection_log = tmp_path / "introspection.log"
            introspection_log.write_text(
                "Outputs:\n"
                " out                      \"INITIAL TIMESTEP_END\"\n"
                " console                  \"INITIAL TIMESTEP_BEGIN LINEAR NONLINEAR FAILED TIMESTEP_END\"\n"
                "Time Step 0, time = 0\n"
            )
            good_framework = _framework_output_evidence(
                introspection_log,
                report,
                check_input_returncode=0,
                introspection_returncode=0,
            )
            if good_framework["status"] != "PASS":
                raise AssertionError("valid zero-step framework introspection failed")
            if good_framework.get("positive_time_steps"):
                raise AssertionError("zero-step introspection fabricated a physical timestep")

            introspection_log.write_text(
                "Outputs:\n"
                " out                      \"INITIAL\"\n"
                " console                  \"INITIAL TIMESTEP_END\"\n"
                "Time Step 0, time = 0\n"
            )
            missing_schedule = _framework_output_evidence(
                introspection_log,
                report,
                check_input_returncode=0,
                introspection_returncode=0,
            )
            failed_ids = {item["id"] for item in missing_schedule["blockers"]}
            if (
                missing_schedule["status"] != "HOLD"
                or "show-outputs-csv-timestep-end" not in failed_ids
            ):
                raise AssertionError("missing CSV TIMESTEP_END schedule was accepted")

            introspection_log.write_text(
                "Outputs:\n"
                " out                      \"INITIAL TIMESTEP_END\"\n"
                " console                  \"INITIAL TIMESTEP_END\"\n"
                "Time Step 1, time = 1e-14, dt = 1e-14\n"
            )
            phase_leak = _framework_output_evidence(
                introspection_log,
                report,
                check_input_returncode=0,
                introspection_returncode=0,
            )
            failed_ids = {item["id"] for item in phase_leak["blockers"]}
            if (
                phase_leak["status"] != "HOLD"
                or "output-introspection-no-physical-timestep" not in failed_ids
                or phase_leak.get("positive_time_steps") != [1]
            ):
                raise AssertionError("physical-timestep introspection leak was not rejected")

            p2_error = tmp_path / "p2_error.log"
            p2_error.write_text(
                "*** ERROR ***\n"
                "input.i:480.5: unused parameter 'Outputs/console/precision'\n"
            )
            p2_class = _classify_p2_failure(p2_error, 1)
            if (
                p2_class["class"] != "HARNESS_OR_CONSTRUCTION_FAIL"
                or p2_class["reason"] != "UNUSED_PARAMETER"
                or p2_class["detail"] != "Outputs/console/precision"
            ):
                raise AssertionError("P2 unused-parameter failure was not classified")
    except Exception as exc:
        print(f"ISSUE44_OUTPUT_CONTRACT_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE44_OUTPUT_CONTRACT_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output-preflight", action="store_true")
    parser.add_argument("--qpx")
    parser.add_argument("--results-root")
    known, _ = parser.parse_known_args(args)
    if known.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    if known.output_preflight:
        return _run_output_preflight(
            qpx=known.qpx,
            results_root=known.results_root,
        )
    _install_v5_repairs()
    return v4.main(args)


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
