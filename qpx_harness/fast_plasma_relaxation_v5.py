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


def _numeric_assignment_values(text: str, name: str) -> list[float]:
    number = r"[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?"
    matches = re.findall(
        rf"(?m)^\s*{re.escape(name)}\s*=\s*['\"]?({number})",
        text,
    )
    values: list[float] = []
    for raw in matches:
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return values


def _representation_numeric_match(
    text: str, name: str, required: float
) -> tuple[bool, list[float]]:
    values = _numeric_assignment_values(text, name)
    tolerance = max(abs(required) * 1.0e-12, 1.0e-300)
    return (
        any(abs(value - required) <= tolerance for value in values),
        values,
    )


def _output_preflight_log_evidence(
    log_path: Path, report: dict[str, Any]
) -> dict[str, Any]:
    if not log_path.is_file():
        return {
            "status": "HOLD",
            "checks": [{"id": "qpx-introspection-log", "status": "FAIL"}],
        }

    text = log_path.read_text(errors="replace")
    csv = report["csv"]
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "PASS" if passed else "FAIL",
                "observed": observed,
                "required": required,
            }
        )

    # --show-input is the executable-derived representation. These checks are
    # capability/value checks. Decimal serialization is compared numerically,
    # not by exact token spelling, per VAL-16.
    required_names = (
        "new_row_tolerance",
        "time_tolerance",
        "time_step_interval",
        "min_simulation_time_interval",
        "new_row_detection_columns",
    )
    for name in required_names:
        add(
            f"show-input-{name}",
            name in text,
            "present" if name in text else "missing",
            "present",
        )

    row_required = float(csv["new_row_tolerance"])
    row_match, row_values = _representation_numeric_match(
        text, "new_row_tolerance", row_required
    )
    add(
        "show-input-row-tolerance-value",
        row_match,
        row_values,
        row_required,
    )

    time_required = float(csv["time_tolerance"])
    time_match, time_values = _representation_numeric_match(
        text, "time_tolerance", time_required
    )
    add(
        "show-input-time-tolerance-value",
        time_match,
        time_values,
        time_required,
    )
    add(
        "show-output-timestep-end",
        "TIMESTEP_END" in text,
        "TIMESTEP_END" if "TIMESTEP_END" in text else "missing",
        "TIMESTEP_END",
    )

    blockers = [item for item in checks if item["status"] == "FAIL"]
    return {
        "status": "PASS" if not blockers else "HOLD",
        "checks": checks,
        "blockers": blockers,
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
    log_path = root / "p2_qpx_introspection.log"
    summary_path = root / "summary.json"

    p2 = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_path.name,
        log_path=log_path,
        extra_args=(
            "--check-input",
            "--show-input",
            "--show-outputs",
            "--no-color",
        ),
        stream=False,
    )
    framework_evidence = _output_preflight_log_evidence(log_path, report)

    status = (
        "PASS"
        if p2.returncode == 0 and framework_evidence["status"] == "PASS"
        else "HOLD"
    )
    summary = {
        "issue": 44,
        "mode": "output-preflight",
        "status": status,
        "p3_executed": False,
        "identity": {
            **evidence.identity_record(executable=exe, input_path=input_path),
            "qpx_sha256": evidence.sha256_file(exe),
        },
        "p1_output_contract": {
            "report": report,
            "decision": static_decision,
        },
        "p2_qpx_introspection": {
            "returncode": p2.returncode,
            "wall_seconds": p2.wall_seconds,
            "log": str(log_path),
            "framework_evidence": framework_evidence,
        },
    }
    v2._write_json(summary_path, summary)

    print(f"ISSUE44_OUTPUT_PREFLIGHT_P1: {static_decision['status']}")
    print(
        "ISSUE44_OUTPUT_PREFLIGHT_P2_CHECK_INPUT: "
        + ("PASS" if p2.returncode == 0 else "FAIL")
    )
    print(
        "ISSUE44_OUTPUT_PREFLIGHT_FRAMEWORK_EVIDENCE: "
        f"{framework_evidence['status']}"
    )
    print(f"ISSUE44_OUTPUT_PREFLIGHT_PRECLASS: {status}")
    print(f"ISSUE44_OUTPUT_PREFLIGHT_LOG: {log_path}")
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

            introspection = tmp_path / "introspection.log"
            introspection.write_text(
                "new_row_tolerance = 1e-17\n"
                "time_tolerance = 1.0000000000000001e-17\n"
                "time_step_interval = 1\n"
                "min_simulation_time_interval = 0\n"
                "new_row_detection_columns = time\n"
                "execute_on = 'INITIAL TIMESTEP_END'\n"
            )
            if _output_preflight_log_evidence(introspection, report)["status"] != "PASS":
                raise AssertionError(
                    "representation-equivalent executable-introspection evidence failed"
                )

            introspection.write_text(
                "new_row_tolerance = 1e-12\n"
                "time_tolerance = 1e-17\n"
                "time_step_interval = 1\n"
                "min_simulation_time_interval = 0\n"
                "new_row_detection_columns = time\n"
                "execute_on = 'INITIAL TIMESTEP_END'\n"
            )
            bad_introspection = _output_preflight_log_evidence(introspection, report)
            failed_ids = {item["id"] for item in bad_introspection["blockers"]}
            if (
                bad_introspection["status"] != "HOLD"
                or "show-input-row-tolerance-value" not in failed_ids
            ):
                raise AssertionError(
                    "materially different row-tolerance introspection was accepted"
                )
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
