"""Fixed-step CORE-16 execution contract owner for Issue43 fast-plasma runs."""
from __future__ import annotations

from . import issue43_fast_base as _base
for _name in dir(_base):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_base, _name)


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


__all__ = [name for name in globals() if not name.startswith("__")]
