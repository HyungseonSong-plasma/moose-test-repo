"""Issue44 output-observation augmentation for the Issue43 fast runtime."""
from __future__ import annotations

from . import issue43_fast_contract as _contract
from . import issue43_fast_v3_characterization as _v3
for _module in (_contract, _v3):
    for _name in dir(_module):
        if not _name.startswith("__"):
            globals()[_name] = getattr(_module, _name)

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


__all__ = [name for name in globals() if not name.startswith("__")]
