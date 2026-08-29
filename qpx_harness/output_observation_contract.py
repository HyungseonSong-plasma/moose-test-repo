"""Reusable micro-time output observation contract for MOOSE/QPX."""

from __future__ import annotations

import math
import re
from typing import Any

from .moose_input import MooseInput, MooseInputError


class OutputObservationContractError(RuntimeError):
    pass


def _fmt(value: float) -> str:
    return f"{value:.17g}"


def _parameter_count(text: str, path: str, name: str) -> int:
    doc = MooseInput(text)
    span = doc.unique(path)
    block = text[span.start : span.end]
    return len(re.findall(rf"(?m)^\s*{re.escape(name)}\s*=", block))


def _set_parameter(text: str, path: str, name: str, value: str) -> str:
    count = _parameter_count(text, path, name)
    if count > 1:
        raise OutputObservationContractError(
            f"ambiguous parameter {path}/{name}: found {count} assignments"
        )
    try:
        if count == 1:
            text, _ = MooseInput(text).replace_parameters(path, {name: value})
        else:
            text, _ = MooseInput(text).insert_before_close(path, f"    {name} = {value}")
    except MooseInputError as exc:
        raise OutputObservationContractError(f"failed to set {path}/{name}: {exc}") from exc
    return text


def _remove_optional_parameter(text: str, path: str, name: str) -> str:
    count = _parameter_count(text, path, name)
    if count > 1:
        raise OutputObservationContractError(
            f"ambiguous parameter {path}/{name}: found {count} assignments"
        )
    if count == 0:
        return text
    try:
        text, _ = MooseInput(text).remove_parameters(path, (name,))
    except MooseInputError as exc:
        raise OutputObservationContractError(f"failed to remove {path}/{name}: {exc}") from exc
    return text


def _block_parameter(text: str, path: str, name: str) -> str | None:
    doc = MooseInput(text)
    span = doc.unique(path)
    block = text[span.start : span.end]
    matches = re.findall(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\r\n]+)", block)
    if len(matches) > 1:
        raise OutputObservationContractError(
            f"ambiguous parameter {path}/{name}: found {len(matches)} assignments"
        )
    return matches[0].strip() if matches else None


def _parse_scalar(raw: str | None) -> Any:
    if raw is None:
        return None
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


def _execute_tokens(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [token.upper() for token in raw.strip().strip("'\"").split() if token]


def _ensure_output_block(text: str, name: str, output_type: str) -> str:
    path = f"Outputs/{name}"
    matches = MooseInput(text).find(path)
    if len(matches) > 1:
        raise OutputObservationContractError(f"duplicate output block {path}")
    if not matches:
        fragment = f"  [{name}]\n    type = {output_type}\n  []"
        try:
            text, _ = MooseInput(text).insert_before_close("Outputs", fragment)
        except MooseInputError as exc:
            raise OutputObservationContractError(f"failed to create {path}: {exc}") from exc
        return text
    actual = _block_parameter(text, path, "type")
    if actual is None or actual.strip("'\"").lower() != output_type.lower():
        raise OutputObservationContractError(
            f"{path} must be type={output_type}, got {actual!r}"
        )
    return text


def apply_microtime_output_contract(
    text: str,
    *,
    dt: float,
    row_tolerance: float | None = None,
) -> str:
    if not math.isfinite(dt) or dt <= 0.0:
        raise OutputObservationContractError("dt must be finite and positive")
    tolerance = dt * 1.0e-3 if row_tolerance is None else float(row_tolerance)
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise OutputObservationContractError("row_tolerance must be finite and positive")
    if tolerance >= dt:
        raise OutputObservationContractError(
            "row_tolerance must be smaller than the required physical timestep separation"
        )
    if len(MooseInput(text).find("Outputs")) != 1:
        raise OutputObservationContractError("expected exactly one [Outputs] block")

    text = _remove_optional_parameter(text, "Outputs", "csv")
    text = _ensure_output_block(text, "out", "CSV")
    text = _ensure_output_block(text, "console", "Console")

    csv_settings = {
        "execute_on": "'INITIAL TIMESTEP_END'",
        "time_step_interval": "1",
        "min_simulation_time_interval": "0",
        "sync_only": "false",
        "new_row_detection_columns": "time",
        "new_row_tolerance": _fmt(tolerance),
        "time_tolerance": _fmt(tolerance),
        "precision": "17",
        "scientific_notation": "true",
    }
    for name, value in csv_settings.items():
        text = _set_parameter(text, "Outputs/out", name, value)

    # Console uses its own time-formatting parameter names. Remove legacy CSV-style
    # names if a previously generated block is being repaired rather than masking
    # them with --allow-unused at P2.
    text = _remove_optional_parameter(text, "Outputs/console", "precision")
    text = _remove_optional_parameter(text, "Outputs/console", "scientific_notation")
    console_settings = {
        "time_step_interval": "1",
        "min_simulation_time_interval": "0",
        "sync_only": "false",
        "new_row_detection_columns": "time",
        "new_row_tolerance": _fmt(tolerance),
        "time_tolerance": _fmt(tolerance),
        "time_precision": "17",
        "scientific_time": "true",
    }
    for name, value in console_settings.items():
        text = _set_parameter(text, "Outputs/console", name, value)
    return text


def observation_report(text: str, *, required_time_separation: float) -> dict[str, Any]:
    if not math.isfinite(required_time_separation) or required_time_separation <= 0.0:
        raise OutputObservationContractError(
            "required_time_separation must be finite and positive"
        )

    def one(path: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in (
            "type",
            "execute_on",
            "time_step_interval",
            "min_simulation_time_interval",
            "sync_only",
            "new_row_detection_columns",
            "new_row_tolerance",
            "time_tolerance",
            "precision",
            "scientific_notation",
            "time_precision",
            "scientific_time",
        ):
            raw = _block_parameter(text, path, name)
            if raw is not None:
                result[name] = _parse_scalar(raw)
        result["timestep_end_enabled"] = (
            "TIMESTEP_END" in _execute_tokens(_block_parameter(text, path, "execute_on"))
        )
        return result

    return {
        "required_time_separation": float(required_time_separation),
        "provenance": (
            "explicit generated MOOSE Output objects; confirm effective objects with "
            "user-local qpx-opt --show-outputs before promotion"
        ),
        "csv": one("Outputs/out"),
        "console": one("Outputs/console"),
        "evidence_role": {
            "csv": "canonical state/time trajectory",
            "console": "supporting solver observability",
        },
    }


def evaluate_observation_report(report: dict[str, Any]) -> dict[str, Any]:
    separation = float(report["required_time_separation"])
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, *, severity: str, meaning: str, observed: Any, required: Any) -> None:
        checks.append({
            "id": check_id,
            "severity": severity,
            "meaning": meaning,
            "status": "PASS" if passed else "FAIL",
            "observed": observed,
            "required": required,
        })

    csv = report["csv"]
    console = report["console"]
    csv_row_tol = float(csv.get("new_row_tolerance", math.inf))
    csv_time_tol = float(csv.get("time_tolerance", math.inf))
    csv_min_interval = float(csv.get("min_simulation_time_interval", math.inf))
    add("csv-row-tolerance", csv_row_tol < separation, severity="hard",
        meaning="CSV duplicate-row tolerance must be below required physical time separation",
        observed=csv_row_tol, required=f"< {separation}")
    add("csv-time-tolerance", csv_time_tol < separation, severity="hard",
        meaning="CSV output time tolerance must be below required physical time separation",
        observed=csv_time_tol, required=f"< {separation}")
    add("csv-step-interval", csv.get("time_step_interval") == 1, severity="hard",
        meaning="CSV output must be eligible on every physical timestep",
        observed=csv.get("time_step_interval"), required=1)
    add("csv-min-simulation-interval", csv_min_interval < separation, severity="hard",
        meaning="CSV minimum simulation-time interval must not suppress required rows",
        observed=csv_min_interval, required=f"< {separation}")
    add("csv-timestep-end", bool(csv.get("timestep_end_enabled")), severity="hard",
        meaning="CSV must observe TIMESTEP_END for the relaxation trajectory",
        observed=csv.get("execute_on"), required="contains TIMESTEP_END")
    add("csv-row-detection-columns",
        str(csv.get("new_row_detection_columns", "")).lower() == "time",
        severity="hard", meaning="CSV row identity must be keyed by physical time for this claim",
        observed=csv.get("new_row_detection_columns"), required="time")

    console_row_tol = float(console.get("new_row_tolerance", math.inf))
    console_time_tol = float(console.get("time_tolerance", math.inf))
    add("console-row-tolerance", console_row_tol < separation, severity="warn",
        meaning="Console row tolerance should preserve supporting micro-time observability",
        observed=console_row_tol, required=f"< {separation}")
    add("console-time-tolerance", console_time_tol < separation, severity="warn",
        meaning="Console time tolerance should preserve supporting micro-time observability",
        observed=console_time_tol, required=f"< {separation}")
    add("console-legacy-precision-absent", "precision" not in console, severity="hard",
        meaning="Console must not carry the CSV-only precision parameter",
        observed=console.get("precision"), required="absent")
    add("console-legacy-scientific-notation-absent",
        "scientific_notation" not in console, severity="hard",
        meaning="Console must not carry the CSV-only scientific_notation parameter",
        observed=console.get("scientific_notation"), required="absent")
    add("console-time-precision", console.get("time_precision") == 17, severity="warn",
        meaning="Console should preserve micro-time display precision",
        observed=console.get("time_precision"), required=17)
    add("console-scientific-time", console.get("scientific_time") is True, severity="warn",
        meaning="Console should display micro-time values in scientific notation",
        observed=console.get("scientific_time"), required=True)

    blockers = [x for x in checks if x["severity"] == "hard" and x["status"] == "FAIL"]
    warnings = [x for x in checks if x["severity"] == "warn" and x["status"] == "FAIL"]
    return {"status": "PASS" if not blockers else "HOLD", "checks": checks,
            "blockers": blockers, "warnings": warnings}


def self_test() -> int:
    try:
        base = """[Executioner]\n  type = Transient\n  dt = 1e-14\n  end_time = 5e-14\n[]\n[Outputs]\n  csv = true\n  execute_on = 'INITIAL TIMESTEP_END'\n[]\n"""
        tuned = apply_microtime_output_contract(base, dt=1.0e-14)
        if "csv = true" in tuned:
            raise AssertionError("shortcut CSV parameter remained")
        doc = MooseInput(tuned)
        if len(doc.find("Outputs/out")) != 1 or len(doc.find("Outputs/console")) != 1:
            raise AssertionError("explicit CSV/Console blocks missing")
        report = observation_report(tuned, required_time_separation=1.0e-14)
        if evaluate_observation_report(report)["status"] != "PASS":
            raise AssertionError("valid output observation contract failed")
        if report["csv"].get("precision") != 17 or report["csv"].get("scientific_notation") is not True:
            raise AssertionError("CSV precision/scientific notation contract missing")
        if report["console"].get("time_precision") != 17 or report["console"].get("scientific_time") is not True:
            raise AssertionError("Console time formatting contract missing")
        if "precision" in report["console"] or "scientific_notation" in report["console"]:
            raise AssertionError("legacy CSV-style Console formatting parameter remained")

        mutated = _set_parameter(tuned, "Outputs/out", "new_row_tolerance", "1e-12")
        bad = evaluate_observation_report(
            observation_report(mutated, required_time_separation=1.0e-14)
        )
        failed_ids = {item["id"] for item in bad["blockers"]}
        if bad["status"] != "HOLD" or "csv-row-tolerance" not in failed_ids:
            raise AssertionError("historical row-tolerance mutation was not rejected")

        console_mutated = _set_parameter(
            tuned, "Outputs/console", "new_row_tolerance", "1e-12"
        )
        console_decision = evaluate_observation_report(
            observation_report(console_mutated, required_time_separation=1.0e-14)
        )
        if console_decision["status"] != "PASS" or not console_decision["warnings"]:
            raise AssertionError("Console supporting tolerance should be warning-only")

        legacy_console = _set_parameter(tuned, "Outputs/console", "precision", "17")
        legacy_decision = evaluate_observation_report(
            observation_report(legacy_console, required_time_separation=1.0e-14)
        )
        legacy_failed_ids = {item["id"] for item in legacy_decision["blockers"]}
        if (
            legacy_decision["status"] != "HOLD"
            or "console-legacy-precision-absent" not in legacy_failed_ids
        ):
            raise AssertionError("legacy Console precision mutation was not rejected")
        repaired_legacy = apply_microtime_output_contract(legacy_console, dt=1.0e-14)
        repaired_report = observation_report(
            repaired_legacy, required_time_separation=1.0e-14
        )
        if evaluate_observation_report(repaired_report)["status"] != "PASS":
            raise AssertionError("legacy Console precision was not repaired")

        try:
            apply_microtime_output_contract(base, dt=1.0e-14, row_tolerance=1.0e-12)
        except OutputObservationContractError:
            pass
        else:
            raise AssertionError("invalid derived row tolerance was not rejected")
    except Exception as exc:
        print(f"OUTPUT_OBSERVATION_CONTRACT_SELFTEST: FAIL ({exc})")
        return 1
    print("OUTPUT_OBSERVATION_CONTRACT_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
