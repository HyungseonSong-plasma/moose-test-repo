"""Issue #44 output-observation contract layer for the Issue #43 fast-plasma runner."""

from __future__ import annotations

import argparse
import csv
import math
import re
import tempfile
from pathlib import Path
from typing import Any

from recipes import issue43_fast_relaxation as relaxation_recipe

from . import artifacts
from . import cases as case_ops
from . import evidence
from . import execution_contract as ec
from . import issue43_relaxation_runtime as issue43_runtime
from . import output_observation_contract as ooc
from . import preflight
from . import scale_audit
from . import temporal
from .moose import executioner as moose_executioner
from .runtime import resolve_executable, run_qpx, validate_executable


# Absorbed v3 CORE-16 ownership. Generic mechanics remain in their canonical
# reusable owners; this module now composes them directly rather than depending
# on a historical version layer.
FastPlasmaV3Error = moose_executioner.MooseExecutionerError
_RAW_BUILD_ELECTRON_300K = issue43_runtime.build_electron_300k
_BASE_BUILD_ONEWAY = issue43_runtime.build_oneway
_BASE_BUILD_FEEDBACK = issue43_runtime.build_feedback
_RAW_RUN_CASE = issue43_runtime.run_case

_RUNTIME_PURGE_DIRECTORY_NAMES = (".jitcache",)
_RUNTIME_PURGE_PATTERNS = (
    "input_out*",
    "r43_csv*",
    "perfgraph*",
    "petsc_log*",
    "metrics*",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    artifacts.write_json_bundle(
        path.parent,
        {"payload": (path.name, payload)},
    )


def _create_root(results_root: Path) -> Path:
    return evidence.create_collision_safe_directory(
        results_root,
        f"fast_plasma_discriminator_v2_Issue43_{evidence.utc_timestamp()}",
    )


def _stage_case(source: Path, target: Path, input_text: str | None = None) -> None:
    try:
        case_ops.stage_case(
            source,
            target,
            input_text=input_text,
            purge_directory_names=_RUNTIME_PURGE_DIRECTORY_NAMES,
            purge_patterns=_RUNTIME_PURGE_PATTERNS,
        )
    except case_ops.CaseError as exc:
        raise relaxation_recipe.Issue43FastRelaxationError(
            f"case staging failed: {exc}"
        ) from exc


def _validate_assets(case_dir: Path) -> list[str]:
    try:
        refs = case_ops.validate_case_references(case_dir)
    except case_ops.CaseError as exc:
        raise relaxation_recipe.Issue43FastRelaxationError(
            f"asset validation failed: {exc}"
        ) from exc
    return [ref["resolved"] for ref in refs]


def _set_executioner_parameter(text: str, name: str, value: str) -> str:
    return moose_executioner.set_executioner_parameter(text, name, value)


def apply_micro_time_contract(text: str, *, dt: float, steps: int) -> str:
    return moose_executioner.apply_fixed_step_contract(text, dt=dt, steps=steps)


def _build_electron_fixed(base_text: str, *, dt: float, steps: int) -> str:
    return apply_micro_time_contract(
        _RAW_BUILD_ELECTRON_300K(base_text, dt=dt, steps=steps),
        dt=dt,
        steps=steps,
    )


def _build_oneway_fixed(
    base_text: str, *, dt: float, steps: int, radial_span: float
) -> str:
    return apply_micro_time_contract(
        _BASE_BUILD_ONEWAY(
            base_text, dt=dt, steps=steps, radial_span=radial_span
        ),
        dt=dt,
        steps=steps,
    )


def _build_feedback_fixed(
    base_text: str, *, dt: float, steps: int, radial_span: float
) -> str:
    return apply_micro_time_contract(
        _BASE_BUILD_FEEDBACK(
            base_text, dt=dt, steps=steps, radial_span=radial_span
        ),
        dt=dt,
        steps=steps,
    )


def _executioner_controls(text: str) -> dict[str, Any]:
    return moose_executioner.executioner_controls(
        text,
        required=(
            "dt",
            "end_time",
            "num_steps",
            "dtmin",
            "timestep_tolerance",
            "abort_on_solve_fail",
        ),
    )


def _case_semantics(case_id: str) -> tuple[str, list[str], list[str]]:
    if "electron_300K" in case_id:
        return (
            "300 K electron-only transient control with prescribed electric field",
            ["electron transport", "300 K lookup state"],
            ["solved Poisson feedback", "chemistry", "Maxwell"],
        )
    if "oneway" in case_id:
        return (
            "one-way electron-to-bulk-Poisson triangular discriminator",
            ["electron transport", "bulk Poisson response"],
            ["Poisson-to-electron feedback", "chemistry", "Maxwell"],
        )
    return (
        "two-way electron and bulk-Poisson fixed-step feedback discriminator",
        ["electron transport", "bulk Poisson", "two-way electrostatic feedback"],
        ["sheath-resolved physics", "chemistry", "Maxwell"],
    )


def _build_execution_contract(case_id: str, input_text: str) -> dict[str, Any]:
    controls = _executioner_controls(input_text)
    dt = float(controls["dt"])
    steps = int(controls["num_steps"])
    end_time = float(controls["end_time"])
    tolerance = float(controls["timestep_tolerance"])
    representation, retained, reduced = _case_semantics(case_id)

    dt_rel_tol = 1.0e-6
    contract: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": f"{case_id}-core16",
        "claim": {
            "statement": (
                "execute the declared Issue43 discriminator in its intended fixed-step "
                "numerical regime before interpreting electron/Poisson physics"
            ),
            "acceptance": (
                "P1 numerical/framework conformance plus P3 physical timestep trajectory "
                "and requested final-time conformance"
            ),
        },
        "model": {
            "representation": representation,
            "retained": retained,
            "reduced": reduced,
            "assumptions": [
                "current QVT Poisson contract is bulk electrostatic, not sheath resolved",
                "fixed-step semantics are part of this discriminator",
                "model-scale thresholds remain owned by Issue43/PS-23 rather than this validator",
            ],
        },
        "numerical_regime": {
            "intent": "fixed-step discriminator",
            "declared_controls": {
                "dt": dt,
                "num_steps": steps,
                "end_time": end_time,
                "required_end_time": dt * steps,
                "minimum_acceptable_final_time": end_time - tolerance,
                "minimum_acceptable_dt": dt * (1.0 - dt_rel_tol),
                "maximum_acceptable_dt": dt * (1.0 + dt_rel_tol),
            },
            "declared_scales": {},
        },
        "framework_effective": {
            "provenance": (
                "explicit generated Executioner controls in the packaged input; "
                "P2 checks parser acceptance and P3 verifies the actual time trajectory"
            ),
            "controls": controls,
        },
        "runtime_regime": {"observed": {}},
        "evidence": {
            "requirements": [
                "P3 return code",
                "positive physical timestep rows",
                "actual final physical time",
                "actual fixed-step cadence",
            ],
            "observed": {},
        },
        "decision": {"status": "PENDING"},
        "checks": [
            {
                "id": "dt-above-dtmin",
                "phase": "P1",
                "meaning": "requested fixed dt must exceed the explicit effective dtmin",
                "left": {"path": "numerical_regime.declared_controls.dt"},
                "op": "gt",
                "right": {"path": "framework_effective.controls.dtmin"},
                "on_fail": "NUMERICAL_CONTRACT_FAIL",
            },
            {
                "id": "time-tolerance-below-dt",
                "phase": "P1",
                "meaning": "framework timestep tolerance must be smaller than the intended step",
                "left": {"path": "framework_effective.controls.timestep_tolerance"},
                "op": "lt",
                "right": {"path": "numerical_regime.declared_controls.dt"},
                "on_fail": "NUMERICAL_CONTRACT_FAIL",
            },
            {
                "id": "end-time-supports-step-count",
                "phase": "P1",
                "meaning": "end_time must permit the declared fixed-step count",
                "left": {"path": "framework_effective.controls.end_time"},
                "op": "ge",
                "right": {"path": "numerical_regime.declared_controls.required_end_time"},
                "on_fail": "NUMERICAL_CONTRACT_FAIL",
            },
            {
                "id": "step-count-preserved",
                "phase": "P1",
                "meaning": "effective num_steps must match the declared discriminator count",
                "left": {"path": "framework_effective.controls.num_steps"},
                "op": "eq",
                "right": {"path": "numerical_regime.declared_controls.num_steps"},
                "on_fail": "NUMERICAL_CONTRACT_FAIL",
            },
            {
                "id": "silent-cutback-disabled",
                "phase": "P1",
                "meaning": "solver failure must not silently change the fixed-step discriminator",
                "left": {"path": "framework_effective.controls.abort_on_solve_fail"},
                "op": "eq",
                "right": {"value": True},
                "on_fail": "NUMERICAL_CONTRACT_FAIL",
            },
            {
                "id": "p3-process-completed",
                "phase": "P3",
                "meaning": "QPX P3 process must complete before physics acceptance",
                "left": {"path": "evidence.observed.p3_returncode"},
                "op": "eq",
                "right": {"value": 0},
                "on_fail": "RUNTIME_SEMANTIC_FAIL",
            },
            {
                "id": "physical-row-count",
                "phase": "P3",
                "meaning": "runtime must emit at least the declared number of physical rows",
                "left": {"path": "runtime_regime.observed.physical_rows"},
                "op": "ge",
                "right": {"path": "numerical_regime.declared_controls.num_steps"},
                "on_fail": "RUNTIME_SEMANTIC_FAIL",
            },
            {
                "id": "final-time-reached",
                "phase": "P3",
                "meaning": "runtime must reach the requested final physical time",
                "left": {"path": "runtime_regime.observed.final_time"},
                "op": "ge",
                "right": {"path": "numerical_regime.declared_controls.minimum_acceptable_final_time"},
                "on_fail": "RUNTIME_SEMANTIC_FAIL",
            },
            {
                "id": "minimum-dt-preserved",
                "phase": "P3",
                "meaning": "actual timestep must not silently undershoot the fixed-step contract",
                "left": {"path": "runtime_regime.observed.actual_dt_min"},
                "op": "ge",
                "right": {"path": "numerical_regime.declared_controls.minimum_acceptable_dt"},
                "on_fail": "RUNTIME_SEMANTIC_FAIL",
            },
            {
                "id": "maximum-dt-preserved",
                "phase": "P3",
                "meaning": "actual timestep must not silently overshoot the fixed-step contract",
                "left": {"path": "runtime_regime.observed.actual_dt_max"},
                "op": "le",
                "right": {"path": "numerical_regime.declared_controls.maximum_acceptable_dt"},
                "on_fail": "RUNTIME_SEMANTIC_FAIL",
            },
        ],
    }
    ec.validate_contract(contract)
    return contract


def _runtime_csv(case_dir: Path) -> Path | None:
    return temporal.find_temporal_csv(case_dir)


def _runtime_observation(case_dir: Path) -> dict[str, Any]:
    return temporal.observe_case_trajectory(case_dir)


def _write_contract_artifacts(
    *,
    measurements_root: Path,
    case_id: str,
    contract: dict[str, Any],
    p1: dict[str, Any],
    p3: dict[str, Any] | None,
) -> dict[str, str]:
    payloads: dict[str, tuple[str, object]] = {
        "contract": ("execution_contract.json", contract),
        "p1": ("execution_contract_p1.json", p1),
    }
    if p3 is not None:
        payloads["p3"] = ("execution_contract_p3.json", p3)
    return artifacts.write_json_bundle(measurements_root / case_id, payloads)


_CONTRACT_ARTIFACT_WRITER = _write_contract_artifacts


def _run_case_safe(**kwargs: Any) -> dict[str, Any]:
    case_id = str(kwargs.get("case_id", "unknown"))
    case_dir = Path(kwargs["case_dir"])
    measurements_root = Path(kwargs["measurements_root"])
    input_text = str(kwargs["input_text"])

    contract = _build_execution_contract(case_id, input_text)
    p1 = ec.evaluate_contract(contract, phase="P1")
    artifact_paths = _CONTRACT_ARTIFACT_WRITER(
        measurements_root=measurements_root,
        case_id=case_id,
        contract=contract,
        p1=p1,
        p3=None,
    )
    if p1["status"] != "PASS":
        return {
            "case_id": case_id,
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "CORE-16 P1 numerical execution contract did not pass",
            "execution_contract": contract,
            "execution_contract_p1": p1,
            "execution_contract_artifacts": artifact_paths,
        }

    caught_error: str | None = None
    try:
        result = _RAW_RUN_CASE(**kwargs)
    except relaxation_recipe.Issue43FastRelaxationError as exc:
        caught_error = str(exc)
        result = {
            "case_id": case_id,
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "legacy analyzer could not interpret runtime temporal evidence",
            "harness_error": caught_error,
            "p3_returncode": 0,
        }
        result = issue43_runtime.attach_nonlinear_residual(result)

    runtime_observed = _runtime_observation(case_dir)
    contract["runtime_regime"]["observed"].update(runtime_observed)
    if result.get("p3_returncode") is not None:
        contract["evidence"]["observed"]["p3_returncode"] = result.get(
            "p3_returncode"
        )
    if result.get("analysis") is not None:
        contract["evidence"]["observed"]["physics_analysis"] = result.get(
            "analysis"
        )
    if caught_error is not None:
        contract["evidence"]["observed"]["legacy_analyzer_error"] = caught_error

    p3 = ec.evaluate_contract(contract, phase="P3")
    artifact_paths = _CONTRACT_ARTIFACT_WRITER(
        measurements_root=measurements_root,
        case_id=case_id,
        contract=contract,
        p1=p1,
        p3=p3,
    )
    result["execution_contract"] = contract
    result["execution_contract_p1"] = p1
    result["execution_contract_p3"] = p3
    result["execution_contract_artifacts"] = artifact_paths

    if result.get("class") == "P3_PASS" and p3["status"] != "PASS":
        result["pre_contract_class"] = "P3_PASS"
        result["class"] = "HARNESS_OR_CONSTRUCTION_FAIL"
        result["reason"] = (
            "QPX process completed but CORE-16 runtime-semantic contract did not pass"
        )
    elif caught_error is not None:
        result["reason"] = (
            "runtime evidence failed the ontology path before physics interpretation"
        )
    return result


def _v3_compat_self_test() -> int:
    try:
        if issue43_runtime.self_test() != 0:
            raise AssertionError("Issue43 runtime self-test failed")
        if ec.self_test() != 0:
            raise AssertionError("execution-contract self-test failed")
        if moose_executioner.self_test() != 0:
            raise AssertionError("generic Executioner self-test failed")
        if temporal.self_test() != 0:
            raise AssertionError("generic temporal observation self-test failed")

        if _BASE_BUILD_ONEWAY is not issue43_runtime.build_oneway:
            raise AssertionError("one-way base builder alias drifted")
        if _BASE_BUILD_FEEDBACK is not issue43_runtime.build_feedback:
            raise AssertionError("feedback base builder alias drifted")
        if _RAW_BUILD_ONEWAY is not _build_oneway_fixed:
            raise AssertionError("one-way fixed-layer alias drifted")
        if _RAW_BUILD_FEEDBACK is not _build_feedback_fixed:
            raise AssertionError("feedback fixed-layer alias drifted")
        if "_RAW_BUILD_ONEWAY" in _build_oneway_fixed.__code__.co_names:
            raise AssertionError("one-way fixed builder can recurse through downstream alias")
        if "_RAW_BUILD_FEEDBACK" in _build_feedback_fixed.__code__.co_names:
            raise AssertionError("feedback fixed builder can recurse through downstream alias")

        fixture = issue43_runtime._fixture()
        for label, constructed in (
            (
                "oneway",
                _build_oneway_fixed(
                    fixture,
                    dt=issue43_runtime.DT_FEEDBACK_BASE,
                    steps=issue43_runtime.N_STEPS,
                    radial_span=0.243,
                ),
            ),
            (
                "feedback",
                _build_feedback_fixed(
                    fixture,
                    dt=issue43_runtime.DT_FEEDBACK_BASE,
                    steps=issue43_runtime.N_STEPS,
                    radial_span=0.243,
                ),
            ),
        ):
            builder_controls = _executioner_controls(constructed)
            if builder_controls.get("num_steps") != issue43_runtime.N_STEPS:
                raise AssertionError(f"{label} fixed builder lost num_steps contract")
            if not math.isclose(
                float(builder_controls.get("dt")),
                issue43_runtime.DT_FEEDBACK_BASE,
                rel_tol=1.0e-15,
                abs_tol=0.0,
            ):
                raise AssertionError(f"{label} fixed builder lost dt contract")

        base = """[Executioner]
  type = Transient
  scheme = implicit-euler
  dt = 1e-8
  end_time = 2e-8
  compute_scaling_once = true
[]
"""
        tuned = apply_micro_time_contract(base, dt=1.0e-13, steps=5)
        controls = _executioner_controls(tuned)
        required = {
            "dt": 1.0e-13,
            "end_time": 5.0e-13,
            "num_steps": 5,
            "dtmin": 1.0e-14,
            "timestep_tolerance": 1.0e-16,
            "abort_on_solve_fail": True,
        }
        for name, expected in required.items():
            actual = controls.get(name)
            if isinstance(expected, float):
                if not math.isclose(
                    float(actual), expected, rel_tol=1.0e-15, abs_tol=0.0
                ):
                    raise AssertionError(
                        f"wrong {name}: expected {expected}, got {actual}"
                    )
            elif actual != expected:
                raise AssertionError(
                    f"wrong {name}: expected {expected}, got {actual}"
                )

        contract = _build_execution_contract(
            "Issue43_FAST2_feedback_dt1e13", tuned
        )
        if ec.evaluate_contract(contract, phase="P1")["status"] != "PASS":
            raise AssertionError("valid fixed-step ontology contract failed P1")

        invalid = _set_executioner_parameter(tuned, "dtmin", "1e-12")
        invalid_contract = _build_execution_contract(
            "Issue43_FAST2_feedback_dt1e13_bad", invalid
        )
        if ec.evaluate_contract(invalid_contract, phase="P1")["status"] != "HOLD":
            raise AssertionError("dt<dtmin mutation was not rejected by ontology P1")

        duplicate = tuned.replace(
            "  num_steps = 5\n", "  num_steps = 5\n  num_steps = 6\n"
        )
        try:
            apply_micro_time_contract(duplicate, dt=1.0e-13, steps=5)
        except FastPlasmaV3Error:
            pass
        else:
            raise AssertionError("duplicate Executioner parameter was not rejected")

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            csv_path = case_dir / "input_out.csv"
            csv_path.write_text(
                "time,value\n"
                "0,0\n"
                "1e-13,1\n"
                "2e-13,1\n"
                "3e-13,1\n"
                "4e-13,1\n"
                "5e-13,1\n"
            )
            observed = _runtime_observation(case_dir)
            runtime_contract = _build_execution_contract(
                "Issue43_FAST2_feedback_dt1e13", tuned
            )
            runtime_contract["runtime_regime"]["observed"].update(observed)
            runtime_contract["evidence"]["observed"]["p3_returncode"] = 0
            if ec.evaluate_contract(runtime_contract, phase="P3")["status"] != "PASS":
                raise AssertionError("valid runtime trajectory failed ontology P3")

            csv_path.write_text("time,value\n0,0\n")
            zero_observed = _runtime_observation(case_dir)
            zero_contract = _build_execution_contract(
                "Issue43_FAST2_feedback_dt1e13_zero", tuned
            )
            zero_contract["runtime_regime"]["observed"].update(zero_observed)
            zero_contract["evidence"]["observed"]["p3_returncode"] = 0
            if ec.evaluate_contract(zero_contract, phase="P3")["status"] != "HOLD":
                raise AssertionError("initial-only runtime was not held by ontology P3")
    except Exception as exc:
        print(f"ISSUE43_FAST_V3_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_V3_SELFTEST: PASS")
    return 0


_RAW_BUILD_ELECTRON = _build_electron_fixed
_RAW_BUILD_ONEWAY = _build_oneway_fixed
_RAW_BUILD_FEEDBACK = _build_feedback_fixed
_RAW_BUILD_EXECUTION_CONTRACT = _build_execution_contract
_RAW_RUN_CASE_SAFE = _run_case_safe


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
        result = issue43_runtime.attach_nonlinear_residual(result)
    return result


def _p2_check_input_args() -> tuple[str, ...]:
    return ("--check-input", "--color", "off")


def _p2_output_introspection_args() -> tuple[str, ...]:
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

    csv_report = report["csv"]
    separation = float(report["required_time_separation"])
    add(
        "qpx-accepted-explicit-output-contract",
        check_input_returncode == 0,
        check_input_returncode,
        0,
    )
    add(
        "accepted-csv-row-tolerance",
        float(csv_report.get("new_row_tolerance", float("inf"))) < separation,
        csv_report.get("new_row_tolerance"),
        f"< {separation}",
    )
    add(
        "accepted-csv-time-tolerance",
        float(csv_report.get("time_tolerance", float("inf"))) < separation,
        csv_report.get("time_tolerance"),
        f"< {separation}",
    )
    add(
        "accepted-csv-every-step",
        csv_report.get("time_step_interval") == 1,
        csv_report.get("time_step_interval"),
        1,
    )
    add(
        "accepted-csv-row-identity",
        str(csv_report.get("new_row_detection_columns", "")).lower() == "time",
        csv_report.get("new_row_detection_columns"),
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


def _runtime_csv_times(case_dir: Path) -> tuple[Path | None, list[float], str | None]:
    try:
        csv_path = relaxation_recipe.find_relaxation_csv(case_dir)
    except relaxation_recipe.Issue43FastRelaxationError as exc:
        return None, [], str(exc)

    times: list[float] = []
    try:
        with csv_path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                times.append(float(row["time"]))
    except (OSError, csv.Error, KeyError, ValueError) as exc:
        return csv_path, [], f"invalid runtime CSV time column: {exc}"
    return csv_path, times, None


def _evaluate_output_runtime_confirmation(
    *,
    returncode: int,
    trajectory: dict[str, Any],
    csv_times: list[float],
    dt: float,
    steps: int,
    row_tolerance: float,
) -> dict[str, Any]:
    expected_times = [dt * index for index in range(1, steps + 1)]
    physical_times = [value for value in csv_times if value > row_tolerance]
    compare_tol = max(abs(dt) * 1.0e-9, 1.0e-300)
    final_expected = expected_times[-1]

    solver_checks = [
        {
            "id": "runtime-returncode",
            "status": "PASS" if returncode == 0 else "FAIL",
            "observed": returncode,
            "required": 0,
        },
        {
            "id": "solver-time-step-count",
            "status": "PASS" if trajectory.get("time_steps_seen") == steps else "FAIL",
            "observed": trajectory.get("time_steps_seen"),
            "required": steps,
        },
        {
            "id": "solver-converged-step-count",
            "status": "PASS" if trajectory.get("converged_steps") >= steps else "FAIL",
            "observed": trajectory.get("converged_steps"),
            "required": f">= {steps}",
        },
        {
            "id": "solver-final-time",
            "status": (
                "PASS"
                if trajectory.get("solver_final_time") is not None
                and abs(float(trajectory["solver_final_time"]) - final_expected)
                <= compare_tol
                else "FAIL"
            ),
            "observed": trajectory.get("solver_final_time"),
            "required": final_expected,
        },
    ]
    solver_complete = all(item["status"] == "PASS" for item in solver_checks)

    observation_checks = [
        {
            "id": "csv-physical-row-count",
            "status": "PASS" if len(physical_times) == steps else "FAIL",
            "observed": len(physical_times),
            "required": steps,
        },
        {
            "id": "csv-physical-times-match",
            "status": (
                "PASS"
                if len(physical_times) == steps
                and all(
                    abs(observed - expected) <= compare_tol
                    for observed, expected in zip(physical_times, expected_times)
                )
                else "FAIL"
            ),
            "observed": physical_times,
            "required": expected_times,
        },
        {
            "id": "csv-adjacent-times-distinct",
            "status": (
                "PASS"
                if len(physical_times) == steps
                and all(
                    later - earlier > row_tolerance
                    for earlier, later in zip(physical_times, physical_times[1:])
                )
                else "FAIL"
            ),
            "observed": [
                later - earlier
                for earlier, later in zip(physical_times, physical_times[1:])
            ],
            "required": f"> {row_tolerance}",
        },
        {
            "id": "csv-final-time",
            "status": (
                "PASS"
                if physical_times
                and abs(physical_times[-1] - final_expected) <= compare_tol
                else "FAIL"
            ),
            "observed": physical_times[-1] if physical_times else None,
            "required": final_expected,
        },
    ]

    if not solver_complete:
        return {
            "status": "HOLD",
            "class": "RUNTIME_CONFIRMATION_INCONCLUSIVE",
            "reason": (
                "solver did not complete the five-step observation discriminator; "
                "do not classify output-row behavior from this run"
            ),
            "solver_complete": False,
            "solver_checks": solver_checks,
            "observation_checks": observation_checks,
            "physical_times": physical_times,
            "expected_times": expected_times,
        }

    observation_pass = all(item["status"] == "PASS" for item in observation_checks)
    return {
        "status": "PASS" if observation_pass else "HOLD",
        "class": (
            "OUTPUT_OBSERVATION_CONTRACT_PASS"
            if observation_pass
            else "OUTPUT_OBSERVATION_CONTRACT_FAIL"
        ),
        "reason": (
            "solver completed five physical steps and CSV preserved all required time identities"
            if observation_pass
            else "solver completed five physical steps but CSV did not preserve the required time identities"
        ),
        "solver_complete": True,
        "solver_checks": solver_checks,
        "observation_checks": observation_checks,
        "physical_times": physical_times,
        "expected_times": expected_times,
    }


def _run_output_preflight(*, qpx: str | None, results_root: str | None) -> int:
    exe = resolve_executable(qpx)
    validate_executable(exe)

    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / issue43_runtime.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise SystemExit(f"missing accepted qvt electron control: {base_case}")

    mesh = scale_audit.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    input_text = _build_feedback_v5(
        base_text,
        dt=issue43_runtime.DT_FEEDBACK_SMALL,
        steps=issue43_runtime.N_STEPS,
        radial_span=radial_span,
    )
    preflight.validate_parser_symbols_text(input_text)

    report = ooc.observation_report(
        input_text, required_time_separation=issue43_runtime.DT_FEEDBACK_SMALL
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
    _stage_case(base_case, case_dir, input_text)
    _validate_assets(case_dir)

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
        if p2.returncode == 0
        and introspection is not None
        and introspection.returncode == 0
        and framework_evidence["status"] == "PASS"
        and not p3_executed
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
        "p1_output_contract": {"report": report, "decision": static_decision},
        "p2_qpx_introspection": {
            "check_input": {
                "returncode": p2.returncode,
                "wall_seconds": p2.wall_seconds,
                "log": str(check_log_path),
                "failure": p2_failure,
            },
            "output_introspection": {
                "returncode": introspection.returncode if introspection is not None else None,
                "wall_seconds": introspection.wall_seconds if introspection is not None else None,
                "log": str(introspection_log_path),
                "args": list(_p2_output_introspection_args()),
            },
            "framework_evidence": framework_evidence,
        },
    }
    _write_json(summary_path, summary)

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


def _run_output_runtime_confirmation(
    *, qpx: str | None, results_root: str | None
) -> int:
    preflight_rc = _run_output_preflight(qpx=qpx, results_root=results_root)
    if preflight_rc != 0:
        print("ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_PRECHECK: HOLD")
        print("ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_CLASS: PREFLIGHT_NOT_PASS")
        return 2
    print("ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_PRECHECK: PASS")

    exe = resolve_executable(qpx)
    validate_executable(exe)
    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / issue43_runtime.BASE_CASE_RELATIVE
    mesh = scale_audit.mesh_stats(base_case / "qvt.msh")
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()
    input_text = _build_feedback_v5(
        base_text,
        dt=issue43_runtime.DT_FEEDBACK_SMALL,
        steps=issue43_runtime.N_STEPS,
        radial_span=radial_span,
    )
    preflight.validate_parser_symbols_text(input_text)
    report = ooc.observation_report(
        input_text, required_time_separation=issue43_runtime.DT_FEEDBACK_SMALL
    )

    evidence_root = (
        Path(results_root).expanduser().resolve()
        if results_root
        else exe.parent / "temp" / "results"
    )
    root = evidence.ensure_fresh_directory(
        evidence_root / f"issue44_output_runtime_{evidence.utc_timestamp()}"
    )
    case_dir = root / "case"
    _stage_case(base_case, case_dir, input_text)
    _validate_assets(case_dir)
    input_path = case_dir / "input.i"
    log_path = root / "p3_runtime.log"
    summary_path = root / "summary.json"

    runtime = run_qpx(
        exe,
        cwd=case_dir,
        input_name=input_path.name,
        log_path=log_path,
        extra_args=("--color", "off"),
        stream=False,
    )
    trajectory = _solver_trajectory(log_path)
    csv_path, csv_times, csv_error = _runtime_csv_times(case_dir)
    decision = _evaluate_output_runtime_confirmation(
        returncode=runtime.returncode,
        trajectory=trajectory,
        csv_times=csv_times,
        dt=issue43_runtime.DT_FEEDBACK_SMALL,
        steps=issue43_runtime.N_STEPS,
        row_tolerance=float(report["csv"]["new_row_tolerance"]),
    )

    summary = {
        "issue": 44,
        "mode": "output-runtime-confirmation",
        "status": decision["status"],
        "class": decision["class"],
        "scope": (
            "observation-contract confirmation only; no Issue43 relaxation, "
            "quasi-steady, or production-timestep classification"
        ),
        "p3_executed": True,
        "preflight_passed": True,
        "identity": {
            **evidence.identity_record(executable=exe, input_path=input_path),
            "qpx_sha256": evidence.sha256_file(exe),
        },
        "output_contract": report,
        "runtime": {
            "returncode": runtime.returncode,
            "wall_seconds": runtime.wall_seconds,
            "log": str(log_path),
            "solver_trajectory": trajectory,
        },
        "csv": {
            "path": str(csv_path) if csv_path is not None else None,
            "times": csv_times,
            "error": csv_error,
        },
        "decision": decision,
    }
    _write_json(summary_path, summary)

    print(
        "ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_SOLVER: "
        + ("PASS" if decision["solver_complete"] else "HOLD")
    )
    observation_pass = all(
        item["status"] == "PASS" for item in decision["observation_checks"]
    )
    print(
        "ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_CSV_ROWS: "
        + ("PASS" if observation_pass else "HOLD")
    )
    if decision["status"] != "PASS":
        for check in decision["solver_checks"] + decision["observation_checks"]:
            if check["status"] != "PASS":
                print(
                    "ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_BLOCKER: "
                    f"{check['id']} observed={check.get('observed')!r} "
                    f"required={check.get('required')!r}"
                )
        if csv_error:
            print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_CSV_ERROR: {csv_error}")
    print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_PRECLASS: {decision['status']}")
    print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_CLASS: {decision['class']}")
    print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_LOG: {log_path}")
    print(f"ISSUE44_OUTPUT_RUNTIME_CONFIRMATION_SUMMARY: {summary_path}")
    return 0 if decision["status"] == "PASS" else 2


_RAW_CLASSIFY = relaxation_recipe.classify
_RAW_WRITE_CONTRACT_ARTIFACTS = _write_contract_artifacts


def _write_contract_artifacts_isolated(**kwargs: Any) -> dict[str, str]:
    forwarded = dict(kwargs)
    measurements_root = Path(forwarded["measurements_root"])
    forwarded["measurements_root"] = measurements_root / "execution_contracts"
    return _RAW_WRITE_CONTRACT_ARTIFACTS(**forwarded)


def _install_artifact_namespace() -> None:
    global _CONTRACT_ARTIFACT_WRITER
    _CONTRACT_ARTIFACT_WRITER = _write_contract_artifacts_isolated


def _harness_decision(label: str, case: dict[str, Any] | None) -> dict[str, Any] | None:
    if case is None or case.get("class") != "HARNESS_OR_CONSTRUCTION_FAIL":
        return None
    contract = case.get("execution_contract_p3") or case.get("execution_contract_p1")
    decision: dict[str, Any] = {
        "class": "HARNESS_OR_CONSTRUCTION_FAIL",
        "reason": f"{label} failed execution/ontology conformance before physics classification",
        "failed_case": label,
    }
    if isinstance(contract, dict):
        decision["contract_status"] = contract.get("status")
        decision["contract_blockers"] = contract.get("blockers")
    return decision


def _guarded_classify(
    known_good: dict[str, Any],
    electron_300k: dict[str, Any] | None,
    oneway: dict[str, Any] | None,
    feedback_base: dict[str, Any] | None,
    feedback_small: dict[str, Any] | None,
    feedback_large: dict[str, Any] | None,
    tau_dr: float,
) -> dict[str, Any]:
    for label, case in (
        ("electron_300K", electron_300k),
        ("oneway_e_to_phi", oneway),
        ("feedback_base", feedback_base),
        ("feedback_small", feedback_small),
        ("feedback_large", feedback_large),
    ):
        guarded = _harness_decision(label, case)
        if guarded is not None:
            return guarded

    return _RAW_CLASSIFY(
        known_good,
        electron_300k,
        oneway,
        feedback_base,
        feedback_small,
        feedback_large,
        tau_dr,
    )


def _ontology_blocked(case: dict[str, Any] | None) -> bool:
    return case is not None and case.get("class") == "HARNESS_OR_CONSTRUCTION_FAIL"


def _contract_signature(case: dict[str, Any] | None) -> str:
    if case is None:
        return "not-run"
    p1 = case.get("execution_contract_p1")
    p3 = case.get("execution_contract_p3")
    p1_status = p1.get("status") if isinstance(p1, dict) else "n/a"
    p3_status = p3.get("status") if isinstance(p3, dict) else "n/a"
    return f"P1={p1_status} P3={p3_status}"


def _v4_compat_self_test() -> int:
    try:
        if _v3_compat_self_test() != 0:
            raise AssertionError("v3 compatibility self-test failed")

        with tempfile.TemporaryDirectory() as tmp:
            measurements_root = Path(tmp) / "measurements"
            case_id = "ownership_probe"
            paths = _write_contract_artifacts_isolated(
                measurements_root=measurements_root,
                case_id=case_id,
                contract={"schema_version": 1},
                p1={"status": "PASS"},
                p3=None,
            )
            legacy_owned = measurements_root / case_id
            isolated = measurements_root / "execution_contracts" / case_id
            if legacy_owned.exists():
                raise AssertionError(
                    "contract writer created legacy runner-owned measurement path"
                )
            if not isolated.is_dir():
                raise AssertionError("isolated contract artifact directory was not created")
            if Path(paths["contract"]).parent != isolated:
                raise AssertionError("contract artifact path escaped isolated namespace")

        kge = {"class": "P3_PASS", "canonical_checker": {"status": "PASS"}}
        harness = {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "execution_contract_p1": {
                "status": "HOLD",
                "blockers": [{"id": "dt-above-dtmin"}],
            },
        }
        decision = _guarded_classify(kge, harness, None, None, None, None, 1.0e-12)
        if decision.get("class") != "HARNESS_OR_CONSTRUCTION_FAIL":
            raise AssertionError("construction failure was relabeled as physics failure")
        if not _ontology_blocked(harness):
            raise AssertionError("ontology failure did not prune dependent branches")
        good = {"class": "P3_PASS", "analysis": {"status": "PASS"}}
        decision = _guarded_classify(kge, good, good, good, None, good, 1.0e-12)
        if decision.get("class") != "FEEDBACK_IMPLICIT_COUPLING_RECOVERS_NEAR_TAU_DR":
            raise AssertionError("positive scientific classification path changed")
    except Exception as exc:
        print(f"ISSUE43_FAST_V4_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_V4_SELFTEST: PASS")
    return 0


def _run_issue43_guarded(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Issue43 CORE-16-aware electron/Poisson coupling discriminator"
    )
    parser.add_argument("--qpx", help="path to user-local qpx-opt")
    parser.add_argument("--results-root")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _v4_compat_self_test()
    if _v4_compat_self_test() != 0:
        return 1

    _install_artifact_namespace()

    repo_root = Path(__file__).resolve().parents[1]
    base_case = repo_root / issue43_runtime.BASE_CASE_RELATIVE
    if not base_case.is_dir():
        raise SystemExit(f"missing accepted qvt electron control: {base_case}")

    exe = resolve_executable(args.qpx)
    validate_executable(exe)
    results_root = (
        Path(args.results_root).expanduser().resolve()
        if args.results_root
        else exe.parent / "temp" / "results"
    )
    root = _create_root(results_root)
    root = root.with_name(
        root.name.replace("fast_plasma_relaxation_", "fast_plasma_discriminator_v4_")
    )
    original = next(
        (
            p
            for p in root.parent.glob(
                root.name.replace(
                    "fast_plasma_discriminator_v4_", "fast_plasma_relaxation_"
                )
                + "*"
            )
        ),
        None,
    )
    if not root.exists() and original is not None and original.is_dir():
        original.rename(root)
    root.mkdir(parents=True, exist_ok=True)
    cases_root = root / "cases"
    measurements_root = root / "measurements"
    cases_root.mkdir(exist_ok=True)
    measurements_root.mkdir(exist_ok=True)

    mesh = scale_audit.mesh_stats(base_case / "qvt.msh")
    scales = scale_audit.anchor_scales(
        pressure=scale_audit.DEFAULT_PRESSURE,
        gas_temperature=issue43_runtime.GAS_TEMPERATURE,
        electron_density=scale_audit.DEFAULT_ELECTRON_DENSITY,
        mu_n=scale_audit.DEFAULT_MU_N,
        d_n=scale_audit.DEFAULT_D_N,
        dt=issue43_runtime.HEAVY_MACRO_DT,
        mesh=mesh,
        rf_frequency=None,
    )
    tau_dr = float(scales["electron"]["dielectric_relaxation_s"])
    radial_span = float(mesh["bbox_span_m"]["x"])
    base_text = (base_case / "input.i").read_text()

    known_good = issue43_runtime.run_known_good(
        repo_root=repo_root,
        exe=exe,
        cases_root=cases_root,
        measurements_root=measurements_root,
    )
    if (
        known_good.get("class") != "P3_PASS"
        or known_good.get("canonical_checker", {}).get("status") != "PASS"
    ):
        decision = _guarded_classify(known_good, None, None, None, None, None, tau_dr)
        summary_path = root / "summary.json"
        _write_json(
            summary_path,
            {"scale_map": scales, "known_good": known_good, "decision": decision},
        )
        print(f"ISSUE43_FAST2_PRECLASS: {decision['class']}")
        print(f"ISSUE43_FAST2_REASON: {decision['reason']}")
        print(f"ISSUE43_FAST2_SUMMARY: {summary_path}")
        return 2

    e300_text = _build_electron_v5(
        base_text,
        dt=issue43_runtime.DT_ELECTRON_CONTROL,
        steps=issue43_runtime.N_STEPS,
    )
    electron_300k = _run_case_v5(
        base_case=base_case,
        case_dir=cases_root / "electron_300K",
        input_text=e300_text,
        case_id="Issue43_FAST2_electron_300K",
        exe=exe,
        measurements_root=measurements_root,
        analyze=False,
    )

    oneway = None
    feedback_base = None
    feedback_small = None
    feedback_large = None

    if not _ontology_blocked(electron_300k) and issue43_runtime.physics_pass(electron_300k):
        oneway_text = _build_oneway_v5(
            base_text,
            dt=issue43_runtime.DT_ELECTRON_CONTROL,
            steps=issue43_runtime.N_STEPS,
            radial_span=radial_span,
        )
        oneway = _run_case_v5(
            base_case=base_case,
            case_dir=cases_root / "oneway_e_to_phi",
            input_text=oneway_text,
            case_id="Issue43_FAST2_oneway_e_to_phi",
            exe=exe,
            measurements_root=measurements_root,
            analyze=True,
        )

    if (
        oneway is not None
        and not _ontology_blocked(oneway)
        and issue43_runtime.physics_pass(oneway)
    ):
        feedback_text = _build_feedback_v5(
            base_text,
            dt=issue43_runtime.DT_FEEDBACK_BASE,
            steps=issue43_runtime.N_STEPS,
            radial_span=radial_span,
        )
        feedback_base = _run_case_v5(
            base_case=base_case,
            case_dir=cases_root / "feedback_dt1e13",
            input_text=feedback_text,
            case_id="Issue43_FAST2_feedback_dt1e13",
            exe=exe,
            measurements_root=measurements_root,
            analyze=True,
        )

        if not _ontology_blocked(feedback_base):
            if issue43_runtime.physics_pass(feedback_base):
                large_text = _build_feedback_v5(
                    base_text,
                    dt=issue43_runtime.DT_FEEDBACK_LARGE,
                    steps=issue43_runtime.N_STEPS,
                    radial_span=radial_span,
                )
                feedback_large = _run_case_v5(
                    base_case=base_case,
                    case_dir=cases_root / "feedback_dt1e12",
                    input_text=large_text,
                    case_id="Issue43_FAST2_feedback_dt1e12",
                    exe=exe,
                    measurements_root=measurements_root,
                    analyze=True,
                )
            else:
                small_text = _build_feedback_v5(
                    base_text,
                    dt=issue43_runtime.DT_FEEDBACK_SMALL,
                    steps=issue43_runtime.N_STEPS,
                    radial_span=radial_span,
                )
                feedback_small = _run_case_v5(
                    base_case=base_case,
                    case_dir=cases_root / "feedback_dt1e14",
                    input_text=small_text,
                    case_id="Issue43_FAST2_feedback_dt1e14",
                    exe=exe,
                    measurements_root=measurements_root,
                    analyze=True,
                )

    decision = _guarded_classify(
        known_good,
        electron_300k,
        oneway,
        feedback_base,
        feedback_small,
        feedback_large,
        tau_dr,
    )
    summary = {
        "scale_map": scales,
        "dt_over_tau_dr": {
            "electron_control": issue43_runtime.DT_ELECTRON_CONTROL / tau_dr,
            "feedback_base": issue43_runtime.DT_FEEDBACK_BASE / tau_dr,
            "feedback_small": issue43_runtime.DT_FEEDBACK_SMALL / tau_dr,
            "feedback_large": issue43_runtime.DT_FEEDBACK_LARGE / tau_dr,
        },
        "known_good": known_good,
        "electron_300k": electron_300k,
        "oneway": oneway,
        "feedback_base": feedback_base,
        "feedback_small": feedback_small,
        "feedback_large": feedback_large,
        "decision": decision,
    }
    summary_path = root / "summary.json"
    _write_json(summary_path, summary)

    print(f"ISSUE43_FAST2_KGE: {known_good.get('class')}")
    print(
        f"ISSUE43_FAST2_E300: {electron_300k.get('class')} "
        f"contract={_contract_signature(electron_300k)}"
    )
    if oneway is not None:
        print(
            f"ISSUE43_FAST2_ONEWAY: {oneway.get('class')} "
            f"contract={_contract_signature(oneway)}"
        )
    if feedback_base is not None:
        print(
            f"ISSUE43_FAST2_FEEDBACK_1E13: {feedback_base.get('class')} "
            f"contract={_contract_signature(feedback_base)}"
        )
        print(
            "ISSUE43_FAST2_FEEDBACK_1E13_RESIDUAL: "
            f"{feedback_base.get('nonlinear_residual_summary')}"
        )
    if feedback_small is not None:
        print(
            f"ISSUE43_FAST2_FEEDBACK_1E14: {feedback_small.get('class')} "
            f"contract={_contract_signature(feedback_small)}"
        )
        print(
            "ISSUE43_FAST2_FEEDBACK_1E14_RESIDUAL: "
            f"{feedback_small.get('nonlinear_residual_summary')}"
        )
    if feedback_large is not None:
        print(
            f"ISSUE43_FAST2_FEEDBACK_1E12: {feedback_large.get('class')} "
            f"contract={_contract_signature(feedback_large)}"
        )
        print(
            "ISSUE43_FAST2_FEEDBACK_1E12_RESIDUAL: "
            f"{feedback_large.get('nonlinear_residual_summary')}"
        )
    print(f"ISSUE43_FAST2_PRECLASS: {decision['class']}")
    print(f"ISSUE43_FAST2_REASON: {decision['reason']}")
    print(f"ISSUE43_FAST2_SUMMARY: {summary_path}")

    failure_classes = {
        "KNOWN_GOOD_ELECTRON_CONTROL_FAIL",
        "ELECTRON_300K_CONTROL_FAIL",
        "POISSON_OR_BLOCK_SCALING_FAIL",
        "FEEDBACK_JACOBIAN_SCALING_OR_INITIALIZATION_FAIL",
        "HARNESS_OR_CONSTRUCTION_FAIL",
        "FEEDBACK_CASE_MISSING",
    }
    return 2 if decision["class"] in failure_classes else 0


def self_test() -> int:
    try:
        if _v4_compat_self_test() != 0:
            raise AssertionError("absorbed v4 self-test failed")
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

        complete_trajectory = {
            "status": "PASS",
            "time_steps_seen": 5,
            "converged_steps": 5,
            "solver_final_time": 5.0e-14,
        }
        good_runtime = _evaluate_output_runtime_confirmation(
            returncode=0,
            trajectory=complete_trajectory,
            csv_times=[0.0, 1e-14, 2e-14, 3e-14, 4e-14, 5e-14],
            dt=1.0e-14,
            steps=5,
            row_tolerance=1.0e-17,
        )
        if (
            good_runtime["status"] != "PASS"
            or good_runtime["class"] != "OUTPUT_OBSERVATION_CONTRACT_PASS"
        ):
            raise AssertionError("valid runtime row-identity evidence failed")

        suppressed_runtime = _evaluate_output_runtime_confirmation(
            returncode=0,
            trajectory=complete_trajectory,
            csv_times=[0.0],
            dt=1.0e-14,
            steps=5,
            row_tolerance=1.0e-17,
        )
        if (
            suppressed_runtime["status"] != "HOLD"
            or suppressed_runtime["class"] != "OUTPUT_OBSERVATION_CONTRACT_FAIL"
        ):
            raise AssertionError("suppressed runtime rows were accepted")

        shifted_runtime = _evaluate_output_runtime_confirmation(
            returncode=0,
            trajectory=complete_trajectory,
            csv_times=[0.0, 2e-14, 3e-14, 4e-14, 5e-14, 6e-14],
            dt=1.0e-14,
            steps=5,
            row_tolerance=1.0e-17,
        )
        if shifted_runtime["status"] != "HOLD":
            raise AssertionError("shifted runtime row identities were accepted")

        incomplete_runtime = _evaluate_output_runtime_confirmation(
            returncode=1,
            trajectory={
                "status": "PASS",
                "time_steps_seen": 1,
                "converged_steps": 0,
                "solver_final_time": 1.0e-14,
            },
            csv_times=[0.0],
            dt=1.0e-14,
            steps=5,
            row_tolerance=1.0e-17,
        )
        if (
            incomplete_runtime["class"] != "RUNTIME_CONFIRMATION_INCONCLUSIVE"
            or incomplete_runtime["status"] != "HOLD"
        ):
            raise AssertionError("incomplete solver run was mislabeled as output failure")

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
    parser.add_argument("--output-runtime-confirmation", action="store_true")
    parser.add_argument("--qpx")
    parser.add_argument("--results-root")
    known, _ = parser.parse_known_args(args)
    if known.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    if known.output_preflight:
        return _run_output_preflight(qpx=known.qpx, results_root=known.results_root)
    if known.output_runtime_confirmation:
        return _run_output_runtime_confirmation(
            qpx=known.qpx,
            results_root=known.results_root,
        )
    return _run_issue43_guarded(args)


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
