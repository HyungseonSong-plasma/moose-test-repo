#!/usr/bin/env python3
"""Wave-O v4 closure gate layered on the validated v3 qualification checker.

V4 retains every v3 fail-closed provenance/trajectory check and adds the two
remaining CodeRabbit closure requirements:
* bind the wrapper return code to the downloaded artifact;
* bind the failing parent attempt to structured nonlinear solver context and
  the actual automatic-scaling/SNESComputeFunction Om-error path.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import check_om_forensic_o as v3

_CASES = ("O0", "O1", "O2")
_OM_ERROR_TEXT = "Species 'Om' has Y="
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PARENT_STEP_RE = re.compile(
    r"^Time Step\s+(\d+),\s*time\s*=\s*([-+0-9.eE]+)(?:,\s*dt\s*=\s*([-+0-9.eE]+))?"
)
_SNES_RE = re.compile(r"^\s*(\d+)\s+SNES Function norm\s+([-+0-9.eE]+)")


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _int(value: Any) -> int | None:
    number = _float(value)
    if number is None or not math.isclose(number, round(number), rel_tol=0.0, abs_tol=1e-12):
        return None
    return int(round(number))


def _close(a: Any, b: Any, *, rel: float = 1e-10, abs_: float = 1e-18) -> bool:
    aa = _float(a)
    bb = _float(b)
    return aa is not None and bb is not None and math.isclose(aa, bb, rel_tol=rel, abs_tol=abs_)


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _csv_rows(root: Path, filename: str) -> list[dict[str, str]]:
    paths = [path for path in root.rglob(filename) if path.is_file()]
    if len(paths) != 1:
        return []
    try:
        with paths[0].open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _context_rows(rows: list[dict[str, Any]], lane: str, *, solver: bool = False) -> list[dict[str, Any]]:
    prefix = f"issue236_diag_{lane}_"
    output: list[dict[str, Any]] = []
    for row in rows:
        time = _float(row.get("time"))
        step = _int(row.get(prefix + "step"))
        failed = _int(row.get(prefix + "failed"))
        dt = _float(row.get(prefix + "dt"))
        if time is None or time <= 0 or step is None or step < 1 or failed is None or failed < 0:
            continue
        if dt is None or dt <= 0:
            continue
        item: dict[str, Any] = {"time": time, "step": step, "failed": failed, "dt": dt}
        if solver:
            nl_its = _int(row.get(prefix + "nl_its"))
            residual = _float(row.get(prefix + "residual"))
            if nl_its is None or nl_its < 0 or residual is None or residual < 0:
                continue
            item.update({"nl_its": nl_its, "residual": residual})
        output.append(item)
    return output


def _parse_parent_attempts(log_text: str) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    after_om_error = False
    for raw in log_text.splitlines():
        line = _ANSI_RE.sub("", raw)
        match = _PARENT_STEP_RE.match(line)
        if match:
            if current is not None:
                attempts.append(current)
            current = {
                "step": int(match.group(1)),
                "time": float(match.group(2)),
                "dt": _float(match.group(3)),
                "snes": [],
                "solver_reasons": [],
                "automatic_scaling": False,
                "om_error": False,
                "stack_snes_compute_function": False,
            }
            after_om_error = False
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped == "Performing automatic scaling calculation":
            current["automatic_scaling"] = True
        snes = _SNES_RE.match(line)
        if snes:
            residual = _float(snes.group(2))
            if residual is not None:
                current["snes"].append({"iteration": int(snes.group(1)), "residual": residual})
        if stripped.startswith("Nonlinear solve did not converge") or "Solve Converged!" in stripped:
            current["solver_reasons"].append(stripped)
        if _OM_ERROR_TEXT in line:
            current["om_error"] = True
            after_om_error = True
        elif after_om_error and "SNESComputeFunction" in line:
            current["stack_snes_compute_function"] = True
    if current is not None:
        attempts.append(current)
    return attempts


def _attempt_digest(attempts: list[dict[str, Any]]) -> str:
    canonical = [
        {
            "step": row.get("step"),
            "time": row.get("time"),
            "dt": row.get("dt"),
            "snes": row.get("snes", []),
            "solver_reasons": row.get("solver_reasons", []),
            "automatic_scaling": row.get("automatic_scaling"),
            "om_error": row.get("om_error"),
            "stack_snes_compute_function": row.get("stack_snes_compute_function"),
        }
        for row in attempts
    ]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _summary_context(summary: dict[str, Any], lane: str, *, solver: bool = False) -> list[dict[str, Any]]:
    trajectory = v3._trajectory(summary)
    payloads = trajectory.get("payloads") if isinstance(trajectory, dict) else None
    if not isinstance(payloads, dict):
        return []
    rows = payloads.get({
        "child_accepted": "accepted_child",
        "parent_after_transfer": "parent_attempts",
        "parent_nonlinear": "parent_nonlinear",
    }[lane])
    return _context_rows(rows if isinstance(rows, list) else [], lane, solver=solver)


def _add_v4_checks(
    result: dict[str, Any], root: Path | None, summaries: dict[str, dict[str, Any]]
) -> None:
    checks: dict[str, bool] = {}
    attempt_digests: dict[str, str] = {}
    if root is None:
        checks["v4:artifact_root_required"] = False
    else:
        for case in _CASES:
            result_root = root / "issue236-om-results" / case
            log_root = root / "issue236-om-logs" / case
            manifest = v3._json_or_empty(log_root / "manifest.json")
            wrapper_file = log_root / "wrapper-returncode.txt"
            wrapper_rc = _read_int(wrapper_file)
            checks[f"v4:{case}:wrapper_returncode_artifact"] = wrapper_rc == 1
            checks[f"v4:{case}:wrapper_returncode_bound"] = (
                manifest.get("wrapper_returncode") == wrapper_rc == 1
                and manifest.get("runtime_evidence_valid") is True
                and manifest.get("state") == "FINAL_VALIDATED"
            )

            child_summary = _summary_context(summaries[case], "child_accepted")
            attempt_summary = _summary_context(summaries[case], "parent_after_transfer")
            nonlinear_summary = _summary_context(summaries[case], "parent_nonlinear", solver=True)
            checks[f"v4:{case}:summary_child_structured"] = len(child_summary) >= 2
            checks[f"v4:{case}:summary_attempt_structured"] = len(attempt_summary) >= 2
            checks[f"v4:{case}:summary_nonlinear_solver_context"] = len(nonlinear_summary) >= 2

            child_raw = _context_rows(
                _csv_rows(result_root, "issue236_diag_child_accepted.csv"), "child_accepted"
            )
            attempt_raw = _context_rows(
                _csv_rows(result_root, "issue236_diag_parent_after_transfer.csv"),
                "parent_after_transfer",
            )
            nonlinear_raw = _context_rows(
                _csv_rows(result_root, "issue236_diag_parent_nonlinear.csv"),
                "parent_nonlinear",
                solver=True,
            )
            checks[f"v4:{case}:raw_child_structured"] = len(child_raw) >= 2
            checks[f"v4:{case}:raw_attempt_structured"] = len(attempt_raw) >= 2
            checks[f"v4:{case}:raw_nonlinear_solver_context"] = len(nonlinear_raw) >= 2
            checks[f"v4:{case}:failed_count_monotone"] = bool(attempt_raw) and all(
                attempt_raw[i]["failed"] <= attempt_raw[i + 1]["failed"]
                for i in range(len(attempt_raw) - 1)
            )

            runtime_log = result_root / "runtime.log"
            try:
                log_text = runtime_log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                log_text = ""
            attempts = _parse_parent_attempts(log_text)
            attempt_digests[case] = _attempt_digest(attempts)
            terminal_log = max(attempts, key=lambda row: row["time"]) if attempts else None
            terminal_csv = max(attempt_raw, key=lambda row: row["time"]) if attempt_raw else None
            if terminal_log and terminal_csv:
                terminal_match = (
                    terminal_log["step"] == terminal_csv["step"]
                    and _close(terminal_log["time"], terminal_csv["time"], rel=1e-8, abs_=1e-15)
                    and _close(terminal_log["dt"], terminal_csv["dt"], rel=1e-8, abs_=1e-18)
                )
                same_attempt_nonlinear = [
                    row
                    for row in nonlinear_raw
                    if row["step"] == terminal_csv["step"]
                    and row["failed"] == terminal_csv["failed"]
                    and _close(row["dt"], terminal_csv["dt"])
                ]
            else:
                terminal_match = False
                same_attempt_nonlinear = []
            checks[f"v4:{case}:terminal_log_csv_attempt_match"] = terminal_match
            checks[f"v4:{case}:terminal_attempt_nonlinear_context"] = bool(same_attempt_nonlinear)
            checks[f"v4:{case}:terminal_automatic_scaling_snes_error"] = bool(terminal_log) and (
                terminal_log.get("automatic_scaling") is True
                and terminal_log.get("om_error") is True
                and terminal_log.get("stack_snes_compute_function") is True
            )
            preterminal = attempts[:-1] if len(attempts) >= 2 else []
            checks[f"v4:{case}:preterminal_snes_history"] = bool(preterminal) and any(
                bool(row.get("snes")) or bool(row.get("solver_reasons")) for row in preterminal
            )

            result.setdefault("cases", {}).setdefault(case, {})["v4_terminal_attempt"] = (
                {**terminal_log, "failed": terminal_csv.get("failed") if terminal_csv else None}
                if terminal_log
                else None
            )

        checks["v4:observer_parent_solver_attempts_equal"] = (
            attempt_digests.get("O0") is not None
            and attempt_digests.get("O0")
            == attempt_digests.get("O1")
            == attempt_digests.get("O2")
        )

    result.setdefault("checks", {}).update(checks)
    failed = sorted(key for key, ok in result["checks"].items() if not ok)
    result["failed_checks"] = failed
    result["schema"] = "ISSUE236_OM_WAVE_O_QUALIFICATION_V4"
    if failed:
        result["status"] = "FAIL"
        result["evidence_validity"] = "EVIDENCE_INVALID"


def self_test() -> int:
    log = """Time Step 7, time = 9.32617e-10, dt = 1.5625e-10
  0 SNES Function norm 1.0
  Nonlinear solve did not converge due to DIVERGED_MAX_IT iterations 80
Time Step 8, time = 1.2451171875e-09, dt = 3.125e-10
Performing automatic scaling calculation
PhysicsThermalDiffusionMaterial requires non-negative mass fractions. Species 'Om' has Y=-0.00402221
12: SNESComputeFunction
"""
    parsed = _parse_parent_attempts(log)
    ok = (
        len(parsed) == 2
        and parsed[0]["snes"] == [{"iteration": 0, "residual": 1.0}]
        and parsed[-1]["automatic_scaling"] is True
        and parsed[-1]["om_error"] is True
        and parsed[-1]["stack_snes_compute_function"] is True
    )
    print(json.dumps({"CHECK_OM_FORENSIC_O_V4_P0": "PASS" if ok else "FAIL"}))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("o0", nargs="?", type=Path)
    parser.add_argument("o1", nargs="?", type=Path)
    parser.add_argument("o2", nargs="?", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not all((args.o0, args.o1, args.o2)):
        parser.error("o0, o1, and o2 summaries are required unless --self-test is used")

    try:
        summaries = {"O0": v3._load(args.o0), "O1": v3._load(args.o1), "O2": v3._load(args.o2)}
        result = v3.qualify(summaries["O0"], summaries["O1"], summaries["O2"])
        v3._apply_manifest_gate(result, args.artifact_root, summaries)
        _add_v4_checks(result, args.artifact_root, summaries)
    except (v3.QualificationError, OSError, json.JSONDecodeError, ValueError) as error:
        result = {
            "schema": "ISSUE236_OM_WAVE_O_QUALIFICATION_V4",
            "status": "FAIL",
            "evidence_validity": "EVIDENCE_INVALID",
            "checks": {},
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
