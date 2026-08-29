"""Issue #43 fast plasma discriminator with CORE-16 execution contracts.

This layer wraps the v2 electron/Poisson discriminator with two reusable guards:

1. an explicit fixed-step numerical contract for every diagnostic case; and
2. the machine-readable CORE-16 ontology contract from execution_contract.py.

A case must pass the P1 ontology gate before QPX is launched.  After runtime, the
actual positive-time trajectory is reconstructed independently from CSV output and
must pass the P3 runtime-semantic gate before a successful run is eligible for
physics interpretation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

from . import execution_contract as ec
from . import fast_plasma_relaxation as v1
from . import fast_plasma_relaxation_v2 as v2
from .moose_input import MooseInput, MooseInputError


class FastPlasmaV3Error(RuntimeError):
    pass


_RAW_BUILD_ELECTRON_300K = v2._build_electron_300k
_RAW_BUILD_ONEWAY = v2._build_oneway
_RAW_BUILD_FEEDBACK = v2._build_feedback
_RAW_RUN_CASE = v2._run_case


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def _executioner_parameter_count(text: str, name: str) -> int:
    doc = MooseInput(text)
    span = doc.unique("Executioner")
    block = text[span.start : span.end]
    pattern = re.compile(rf"(?m)^\s*{re.escape(name)}\s*=")
    return len(pattern.findall(block))


def _set_executioner_parameter(text: str, name: str, value: str) -> str:
    count = _executioner_parameter_count(text, name)
    if count > 1:
        raise FastPlasmaV3Error(
            f"ambiguous Executioner parameter {name!r}: found {count} assignments"
        )
    try:
        if count == 1:
            text, _ = MooseInput(text).replace_parameters(
                "Executioner", {name: value}
            )
        else:
            text, _ = MooseInput(text).insert_before_close(
                "Executioner", f"  {name} = {value}"
            )
    except MooseInputError as exc:
        raise FastPlasmaV3Error(
            f"failed to set Executioner/{name}: {exc}"
        ) from exc
    return text


def apply_micro_time_contract(text: str, *, dt: float, steps: int) -> str:
    """Make the fixed-step discriminator semantics explicit in the input."""
    if dt <= 0.0 or steps <= 0:
        raise FastPlasmaV3Error("dt and steps must be positive")

    settings = {
        "dt": _fmt(dt),
        "end_time": _fmt(dt * steps),
        "num_steps": str(steps),
        "dtmin": _fmt(dt * 0.1),
        "timestep_tolerance": _fmt(dt * 1.0e-3),
        "abort_on_solve_fail": "true",
        "compute_scaling_once": "true",
    }
    for name, value in settings.items():
        text = _set_executioner_parameter(text, name, value)
    return text


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
        _RAW_BUILD_ONEWAY(
            base_text, dt=dt, steps=steps, radial_span=radial_span
        ),
        dt=dt,
        steps=steps,
    )


def _build_feedback_fixed(
    base_text: str, *, dt: float, steps: int, radial_span: float
) -> str:
    return apply_micro_time_contract(
        _RAW_BUILD_FEEDBACK(
            base_text, dt=dt, steps=steps, radial_span=radial_span
        ),
        dt=dt,
        steps=steps,
    )


def _executioner_block(text: str) -> str:
    doc = MooseInput(text)
    span = doc.unique("Executioner")
    return text[span.start : span.end]


def _parse_scalar(raw: str) -> Any:
    value = raw.strip().strip("'\"")
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        number = float(value)
    except ValueError:
        return value
    if math.isfinite(number) and number.is_integer() and not any(
        token in value.lower() for token in (".", "e")
    ):
        return int(number)
    return number


def _executioner_controls(text: str) -> dict[str, Any]:
    block = _executioner_block(text)
    controls: dict[str, Any] = {}
    for name in (
        "dt",
        "end_time",
        "num_steps",
        "dtmin",
        "dtmax",
        "timestep_tolerance",
        "abort_on_solve_fail",
        "compute_scaling_once",
    ):
        matches = re.findall(
            rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", block
        )
        if len(matches) > 1:
            raise FastPlasmaV3Error(
                f"ambiguous effective Executioner control {name}: {len(matches)} assignments"
            )
        if matches:
            controls[name] = _parse_scalar(matches[0])
    required = (
        "dt",
        "end_time",
        "num_steps",
        "dtmin",
        "timestep_tolerance",
        "abort_on_solve_fail",
    )
    missing = [name for name in required if name not in controls]
    if missing:
        raise FastPlasmaV3Error(
            "fixed-step execution contract missing explicit controls: "
            + ", ".join(missing)
        )
    return controls


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
    preferred = case_dir / "input_out.csv"
    candidates = [preferred] if preferred.is_file() else []
    candidates.extend(
        path for path in sorted(case_dir.glob("*.csv")) if path != preferred
    )
    for path in candidates:
        try:
            with path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                if "time" in (reader.fieldnames or []):
                    return path
        except (OSError, csv.Error):
            continue
    return None


def _runtime_observation(case_dir: Path) -> dict[str, Any]:
    path = _runtime_csv(case_dir)
    if path is None:
        return {"physical_rows": 0, "csv_status": "MISSING_TIME_CSV"}

    times: list[float] = []
    try:
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    value = float(row["time"])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(value) and value > 0.0:
                    times.append(value)
    except (OSError, csv.Error):
        return {"physical_rows": 0, "csv_status": "UNREADABLE_TIME_CSV"}

    observation: dict[str, Any] = {
        "physical_rows": len(times),
        "csv": str(path),
        "csv_status": "PASS",
    }
    if not times:
        return observation

    times.sort()
    dts = [times[0]] + [b - a for a, b in zip(times, times[1:])]
    finite_positive_dts = [value for value in dts if math.isfinite(value) and value > 0.0]
    observation["first_time"] = times[0]
    observation["final_time"] = times[-1]
    if finite_positive_dts:
        observation["actual_dt_min"] = min(finite_positive_dts)
        observation["actual_dt_max"] = max(finite_positive_dts)
    return observation


def _write_contract_artifacts(
    *,
    measurements_root: Path,
    case_id: str,
    contract: dict[str, Any],
    p1: dict[str, Any],
    p3: dict[str, Any] | None,
) -> dict[str, str]:
    root = measurements_root / case_id
    root.mkdir(parents=True, exist_ok=True)
    contract_path = root / "execution_contract.json"
    p1_path = root / "execution_contract_p1.json"
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    p1_path.write_text(json.dumps(p1, indent=2, sort_keys=True) + "\n")
    paths = {
        "contract": str(contract_path),
        "p1": str(p1_path),
    }
    if p3 is not None:
        p3_path = root / "execution_contract_p3.json"
        p3_path.write_text(json.dumps(p3, indent=2, sort_keys=True) + "\n")
        paths["p3"] = str(p3_path)
    return paths


def _run_case_safe(**kwargs: Any) -> dict[str, Any]:
    """Enforce CORE-16 P1/P3 conformance around the legacy case runner."""
    case_id = str(kwargs.get("case_id", "unknown"))
    case_dir = Path(kwargs["case_dir"])
    measurements_root = Path(kwargs["measurements_root"])
    input_text = str(kwargs["input_text"])

    contract = _build_execution_contract(case_id, input_text)
    p1 = ec.evaluate_contract(contract, phase="P1")
    artifact_paths = _write_contract_artifacts(
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
    except v1.FastPlasmaRelaxationError as exc:
        caught_error = str(exc)
        result = {
            "case_id": case_id,
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "legacy analyzer could not interpret runtime temporal evidence",
            "harness_error": caught_error,
            # v1 raises these analyzer errors only after P3 itself returned success.
            "p3_returncode": 0,
        }
        result = v2._attach_residual(result)

    runtime_observed = _runtime_observation(case_dir)
    contract["runtime_regime"]["observed"].update(runtime_observed)
    if result.get("p3_returncode") is not None:
        contract["evidence"]["observed"]["p3_returncode"] = result.get("p3_returncode")
    if result.get("analysis") is not None:
        contract["evidence"]["observed"]["physics_analysis"] = result.get("analysis")
    if caught_error is not None:
        contract["evidence"]["observed"]["legacy_analyzer_error"] = caught_error

    p3 = ec.evaluate_contract(contract, phase="P3")
    artifact_paths = _write_contract_artifacts(
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


def _install_v2_repairs() -> None:
    v2._build_electron_300k = _build_electron_fixed
    v2._build_oneway = _build_oneway_fixed
    v2._build_feedback = _build_feedback_fixed
    v2._run_case = _run_case_safe


def self_test() -> int:
    try:
        if v2.self_test() != 0:
            raise AssertionError("v2 self-test failed")
        if ec.self_test() != 0:
            raise AssertionError("execution-contract self-test failed")

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


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    known, _ = parser.parse_known_args(args)
    if known.self_test:
        return self_test()
    if self_test() != 0:
        return 1
    _install_v2_repairs()
    return v2.main(args)


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
