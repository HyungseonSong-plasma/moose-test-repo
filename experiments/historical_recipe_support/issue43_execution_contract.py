"""Scientific execution and observation contract policy for Issue43.

The declared model meaning, numerical acceptance, and output-observation checks
are experiment policy. Generic contract evaluation and MOOSE parsing remain
canonical qpx_harness capabilities.
"""
from __future__ import annotations

from typing import Any

from qpx_harness.execution import contract as ec
from qpx_harness.adapters.moose import executioner as moose_executioner
from qpx_harness.adapters.moose import output_observation as ooc


def case_semantics(case_id: str) -> tuple[str, list[str], list[str]]:
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


def build_execution_contract(case_id: str, input_text: str) -> dict[str, Any]:
    controls = moose_executioner.executioner_controls(
        input_text,
        required=(
            "dt",
            "end_time",
            "num_steps",
            "dtmin",
            "timestep_tolerance",
            "abort_on_solve_fail",
        ),
    )
    dt = float(controls["dt"])
    steps = int(controls["num_steps"])
    end_time = float(controls["end_time"])
    tolerance = float(controls["timestep_tolerance"])
    representation, retained, reduced = case_semantics(case_id)
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


def augment_output_observation_contract(case_id: str, input_text: str) -> dict[str, Any]:
    contract = build_execution_contract(case_id, input_text)
    try:
        separation = float(contract["numerical_regime"]["declared_controls"]["dt"])
        report = ooc.observation_report(input_text, required_time_separation=separation)
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
                "meaning": "CSV duplicate-row tolerance must be smaller than the minimum physical time separation required by the claim",
                "left": {"path": "framework_effective.controls.output_observation.csv.new_row_tolerance"},
                "op": "lt",
                "right": {"path": "numerical_regime.declared_controls.dt"},
                "on_fail": "OUTPUT_OBSERVATION_CONTRACT_FAIL",
            },
            {
                "id": "csv-time-tolerance-below-physical-separation",
                "phase": "P1",
                "meaning": "CSV time tolerance must be smaller than the physical time separation required for observation",
                "left": {"path": "framework_effective.controls.output_observation.csv.time_tolerance"},
                "op": "lt",
                "right": {"path": "numerical_regime.declared_controls.dt"},
                "on_fail": "OUTPUT_OBSERVATION_CONTRACT_FAIL",
            },
            {
                "id": "csv-observes-timestep-end",
                "phase": "P1",
                "meaning": "CSV output must observe solved TIMESTEP_END states",
                "left": {"path": "framework_effective.controls.output_observation.csv.timestep_end_enabled"},
                "op": "eq",
                "right": {"value": True},
                "on_fail": "OUTPUT_OBSERVATION_CONTRACT_FAIL",
            },
            {
                "id": "csv-every-step",
                "phase": "P1",
                "meaning": "CSV output must be eligible on every discriminator timestep",
                "left": {"path": "framework_effective.controls.output_observation.csv.time_step_interval"},
                "op": "eq",
                "right": {"value": 1},
                "on_fail": "OUTPUT_OBSERVATION_CONTRACT_FAIL",
            },
            {
                "id": "console-row-tolerance-supporting-observability",
                "phase": "P1",
                "severity": "warn",
                "meaning": "Console row tolerance should preserve supporting micro-time postprocessor observability",
                "left": {"path": "framework_effective.controls.output_observation.console.new_row_tolerance"},
                "op": "lt",
                "right": {"path": "numerical_regime.declared_controls.dt"},
                "on_fail": "OUTPUT_OBSERVABILITY_WARNING",
            },
        ]
    )
    ec.validate_contract(contract)
    return contract
