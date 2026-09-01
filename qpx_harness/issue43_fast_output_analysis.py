"""Pure output/runtime evidence interpretation for Issue43/Issue44 fast runs."""
from __future__ import annotations

from . import issue43_fast_output_contract as _contract
for _name in dir(_contract):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_contract, _name)


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


__all__ = [name for name in globals() if not name.startswith("__")]
