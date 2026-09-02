#!/usr/bin/env python3
"""Issue #92 one-shot adaptive diagnostic driver for the real-QVT R3 nonlinear blocker.

This driver is intentionally Issue-scoped. It builds the accepted Issue #91 R3-E0
model in a temporary work directory, executes only the descendants selected by the
predeclared #92 decision tree, and emits machine-readable diagnostic evidence.

Diagnostic subruns are never scientific acceptance runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from recipes.issue91_r3 import build_r3_input

ISSUE = 92
EVR = 2
DOMINANCE_RATIO = 10.0
JACOBIAN_RATIO_PASS = 1.0e-5
JACOBIAN_RATIO_FAIL = 1.0e-3
DEFAULT_MAX_JACOBIAN_DOFS = 4000
DEFAULT_TIMEOUT_SECONDS = 600

GROUPS: dict[str, tuple[str, ...]] = {
    "FLOW": ("u", "v", "p"),
    "HEAVY_NEUTRAL": ("w_O2s", "w_O", "w_Os"),
    "HEAVY_CHARGED": ("w_O2p", "w_Om", "w_Op"),
    "ELECTRON": ("n_e",),
}
ALL_VARIABLES = tuple(var for names in GROUPS.values() for var in names)

_FLOAT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
NONLINEAR_PATTERNS = (
    re.compile(rf"^\s*(\d+)\s+Nonlinear\s+\|R\|\s*=\s*({_FLOAT})\s*$"),
    re.compile(rf"^\s*(\d+)\s+SNES\s+Function\s+norm\s+({_FLOAT})\s*$", re.I),
    re.compile(rf"^\s*(\d+)\s+({_FLOAT})\s*$"),
)
VARIABLE_LINE = re.compile(rf"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*({_FLOAT})\s*$")
JACOBIAN_RATIO = re.compile(rf"Norm of matrix ratio\s+({_FLOAT}),\s*difference\s+({_FLOAT})", re.I)
NONFINITE = re.compile(r"(?i)(?:^|[\s=(:,])(?:nan|[+-]?inf(?:inity)?)(?:$|[\s,;)])")
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class DiagnosticError(RuntimeError):
    pass


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    elapsed_seconds: float
    timed_out: bool
    log: str


@dataclass
class ResidualAnalysis:
    global_residuals: list[float]
    variable_norms: list[dict[str, float]]
    group_norms: list[dict[str, float]]
    group_ratios: list[float]
    dominant_groups: list[str | None]
    two_cycle: bool
    nonfinite: bool
    parse_complete: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _json_write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _resolve_qpx(value: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.parent != Path(".") or "/" in value:
        if not candidate.is_file():
            raise DiagnosticError(f"qpx executable does not exist: {candidate}")
        return str(candidate.resolve())
    found = shutil.which(value)
    if not found:
        raise DiagnosticError(f"qpx executable not found on PATH: {value}")
    return found


def _run(command: list[str], *, cwd: Path, log_path: Path, timeout: int) -> CommandResult:
    start = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = completed.stdout or ""
        rc = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        raw = exc.stdout or ""
        output = raw.decode() if isinstance(raw, bytes) else raw
        output += f"\nISSUE92_TIMEOUT_AFTER_SECONDS={timeout}\n"
        rc = 124
    elapsed = time.monotonic() - start
    log_path.write_text(output)
    return CommandResult(command, rc, elapsed, timed_out, str(log_path))


def _copy_case_dependencies(case_dir: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for source in case_dir.iterdir():
        if not source.is_file():
            continue
        name = source.name
        if name in {"input.i", "prepare_evidence.json", "run.log"}:
            continue
        if name.startswith("input_out") or source.suffix in {".csv", ".e", ".exo"}:
            continue
        shutil.copy2(source, destination / name)


def _set_debug(text: str) -> str:
    if mb.has_block(text, "Debug"):
        text = mp.upsert_parameter(text, "Debug", "show_var_residual_norms", "true")
        text = mp.upsert_parameter(text, "Debug", "show_top_residuals", "20")
        return text
    return mb.append_top_level_block(
        text,
        """[Debug]
  show_var_residual_norms = true
  show_top_residuals = 20
[]""",
    )


def build_overlay(
    canonical: str,
    *,
    residual_scaling: bool = False,
    dt: float | None = None,
    nl_max_its: int = 3,
) -> str:
    text = canonical
    text = mp.upsert_parameter(text, "Executioner", "line_search", "none")
    text = mp.upsert_parameter(text, "Executioner", "nl_max_its", str(nl_max_its))
    text = mp.upsert_parameter(text, "Executioner", "abort_on_solve_fail", "true")
    if residual_scaling:
        text = mp.upsert_parameter(text, "Executioner", "resid_vs_jac_scaling_param", "1")
    if dt is not None:
        if not math.isfinite(dt) or dt <= 0.0:
            raise DiagnosticError("diagnostic dt must be finite and positive")
        text = mp.upsert_parameter(text, "Executioner", "dt", f"{dt:.17g}")
        text = mp.upsert_parameter(text, "Executioner", "end_time", f"{dt:.17g}")
    return _set_debug(text)


def parse_global_residuals(log: str) -> list[float]:
    values: list[float] = []
    for raw in log.splitlines():
        line = ANSI_ESCAPE.sub("", raw)
        for pattern in NONLINEAR_PATTERNS:
            match = pattern.match(line)
            if match:
                value = float(match.group(2))
                if math.isfinite(value):
                    values.append(value)
                break
    return values


def parse_variable_residuals(log: str) -> list[dict[str, float]]:
    tables: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for raw in log.splitlines():
        line = ANSI_ESCAPE.sub("", raw).strip()
        if line in {"Variable Residual Norms:", "Outlier Variable Residual Norms:"}:
            if current:
                tables.append(current)
            current = {}
            continue
        if current is None:
            continue
        match = VARIABLE_LINE.match(line)
        if match:
            name, raw_value = match.groups()
            if name in ALL_VARIABLES:
                value = float(raw_value)
                if math.isfinite(value):
                    current[name] = value
            continue
        if line and current:
            tables.append(current)
            current = None
        elif not line and current:
            tables.append(current)
            current = None
    if current:
        tables.append(current)
    return tables


def _group_table(table: dict[str, float]) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for group, names in GROUPS.items():
        vals = [table[name] for name in names if name in table]
        if vals:
            grouped[group] = math.sqrt(sum(value * value for value in vals))
    return grouped


def _dominance(grouped: dict[str, float]) -> tuple[str | None, float]:
    positive = sorted(
        ((value, name) for name, value in grouped.items() if math.isfinite(value) and value >= 0.0),
        reverse=True,
    )
    if not positive:
        return None, math.nan
    top_value, top_name = positive[0]
    if len(positive) == 1:
        return top_name, math.inf if top_value > 0.0 else 1.0
    second = positive[1][0]
    if second == 0.0:
        ratio = math.inf if top_value > 0.0 else 1.0
    else:
        ratio = top_value / second
    return top_name, ratio


def detect_two_cycle(values: list[float], *, rel_tol: float = 0.05) -> bool:
    if len(values) < 4:
        return False
    tail = values[-6:]
    lag_two: list[float] = []
    for idx in range(2, len(tail)):
        scale = max(abs(tail[idx]), abs(tail[idx - 2]), 1.0e-30)
        lag_two.append(abs(tail[idx] - tail[idx - 2]) / scale)
    adjacent: list[float] = []
    for idx in range(1, len(tail)):
        scale = max(abs(tail[idx]), abs(tail[idx - 1]), 1.0e-30)
        adjacent.append(abs(tail[idx] - tail[idx - 1]) / scale)
    return bool(lag_two) and max(lag_two) <= rel_tol and max(adjacent, default=0.0) >= 0.03


def analyze_residual_log(log: str) -> ResidualAnalysis:
    global_residuals = parse_global_residuals(log)
    variable_norms = parse_variable_residuals(log)
    group_norms = [_group_table(table) for table in variable_norms]
    dominance = [_dominance(table) for table in group_norms]
    dominant_groups = [item[0] for item in dominance]
    group_ratios = [item[1] for item in dominance]
    return ResidualAnalysis(
        global_residuals=global_residuals,
        variable_norms=variable_norms,
        group_norms=group_norms,
        group_ratios=group_ratios,
        dominant_groups=dominant_groups,
        two_cycle=detect_two_cycle(global_residuals),
        nonfinite=bool(NONFINITE.search(log)),
        parse_complete=bool(global_residuals and variable_norms),
    )


def classify_d1(analysis: ResidualAnalysis) -> tuple[str, str]:
    if analysis.nonfinite:
        return "B1", "NONFINITE_OR_INVALID_STATE"
    if not analysis.parse_complete:
        return "B7", "DIAGNOSTIC_OUTPUT_INCOMPLETE_OR_CONFIGURATION_MISMATCH"
    if not analysis.two_cycle:
        return "B7", "CANONICAL_TWO_CYCLE_NOT_REPRODUCED"

    material = [
        (group, ratio)
        for group, ratio in zip(analysis.dominant_groups, analysis.group_ratios)
        if group is not None and ratio >= DOMINANCE_RATIO
    ]
    groups = [group for group, _ in material]
    if len(set(groups)) >= 2:
        return "B5", "DOMINANT_GROUP_ALTERNATES_WITH_TWO_CYCLE"
    if groups:
        group = groups[-1]
        if group == "ELECTRON":
            return "B2", "ELECTRON_RESIDUAL_DOMINANCE"
        if group == "HEAVY_CHARGED":
            return "B3", "CHARGED_HEAVY_RESIDUAL_DOMINANCE"
        if group == "FLOW":
            return "B4", "FLOW_RESIDUAL_DOMINANCE"
        return "B3", "HEAVY_RESIDUAL_DOMINANCE"
    return "B6", "VARIABLE_GROUP_RESIDUALS_COMPARABLE_WITH_TWO_CYCLE"


def _median_finite(values: Iterable[float]) -> float:
    filtered = sorted(v for v in values if math.isfinite(v))
    if not filtered:
        return math.nan
    n = len(filtered)
    mid = n // 2
    return filtered[mid] if n % 2 else 0.5 * (filtered[mid - 1] + filtered[mid])


def trajectory_improved(reference: ResidualAnalysis, candidate: ResidualAnalysis) -> bool:
    if not candidate.global_residuals:
        return False
    first = candidate.global_residuals[0]
    last = candidate.global_residuals[-1]
    descent = first > 0.0 and last / first <= 0.8
    cycle_broken = reference.two_cycle and not candidate.two_cycle and first > 0.0 and last < 0.9 * first
    return descent or cycle_broken


def scaling_discriminator(reference: ResidualAnalysis, candidate: ResidualAnalysis) -> bool:
    ref_ratio = _median_finite(reference.group_ratios)
    cand_ratio = _median_finite(candidate.group_ratios)
    dominance_collapsed = (
        math.isfinite(cand_ratio)
        and (cand_ratio < DOMINANCE_RATIO or (math.isfinite(ref_ratio) and cand_ratio <= 0.5 * ref_ratio))
    )
    return dominance_collapsed and trajectory_improved(reference, candidate)


def parse_jacobian_ratios(log: str) -> list[dict[str, float]]:
    return [
        {"ratio": float(match.group(1)), "difference": float(match.group(2))}
        for match in JACOBIAN_RATIO.finditer(log)
    ]


def classify_jacobian(log: str) -> tuple[str, list[dict[str, float]]]:
    rows = parse_jacobian_ratios(log)
    if not rows:
        return "UNAVAILABLE", rows
    worst = max(row["ratio"] for row in rows)
    if worst <= JACOBIAN_RATIO_PASS:
        return "ACCEPTABLE", rows
    if worst >= JACOBIAN_RATIO_FAIL:
        return "MATERIAL_MISMATCH", rows
    return "AMBIGUOUS", rows


def estimate_gmsh_2d_cells(mesh_path: Path) -> int | None:
    try:
        lines = mesh_path.read_text(errors="strict").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    try:
        start = lines.index("$Elements")
        count = int(lines[start + 1].strip())
    except (ValueError, IndexError):
        return None
    two_d_types = {2, 3, 9, 10, 16}
    cells = 0
    for line in lines[start + 2 : start + 2 + count]:
        parts = line.split()
        if len(parts) >= 2:
            try:
                if int(parts[1]) in two_d_types:
                    cells += 1
            except ValueError:
                return None
    return cells


def _write_overlay(work_case: Path, name: str, text: str) -> Path:
    path = work_case / f"{name}.i"
    path.write_text(text)
    return path


def _record_subrun(
    manifest: dict[str, Any],
    *,
    name: str,
    overlay: Path,
    changed_axis: list[str],
    check: CommandResult,
    run: CommandResult | None,
) -> None:
    manifest["subruns"].append(
        {
            "name": name,
            "overlay": str(overlay),
            "overlay_sha256": _sha256_text(overlay.read_text()),
            "changed_axis": changed_axis,
            "check": asdict(check),
            "run": asdict(run) if run else None,
            "scientific_acceptance_eligible": False,
        }
    )


def _check_and_run(
    *,
    qpx: str,
    work_case: Path,
    overlay: Path,
    name: str,
    logs: Path,
    timeout: int,
    extra_run_args: list[str] | None = None,
) -> tuple[CommandResult, CommandResult | None]:
    check = _run(
        [qpx, "-i", overlay.name, "--check-input"],
        cwd=work_case,
        log_path=logs / f"{name}_check.log",
        timeout=timeout,
    )
    if check.returncode != 0:
        return check, None
    run_args = [qpx, "-i", overlay.name, "-snes_monitor", "-snes_converged_reason", "-ksp_converged_reason"]
    if extra_run_args:
        run_args.extend(extra_run_args)
    run = _run(run_args, cwd=work_case, log_path=logs / f"{name}.log", timeout=timeout)
    return check, run


def _hypotheses() -> dict[str, str]:
    return {
        "H1": "DISFAVORED",
        "H2": "OPEN",
        "H3": "OPEN",
        "H4": "OPEN",
        "H5": "OPEN",
        "H6": "OPEN",
    }


def _decision_text(summary: dict[str, Any]) -> str:
    hypotheses = " ".join(f"{k}={v}" for k, v in summary["hypotheses"].items())
    return (
        f"ISSUE92_DIAGNOSTIC_BRANCH: {summary['selected_branch']}\n"
        f"TERMINAL_REASON: {summary['terminal_reason']}\n"
        f"HYPOTHESES: {hypotheses}\n"
        f"EVR: {summary['evr']}\n"
        "SCIENTIFIC_ACCEPTANCE_ELIGIBLE: false\n"
    )


def run_batch(args: argparse.Namespace) -> int:
    case_dir = args.case_dir.resolve()
    for required in ("heavy_base.i", "qvt.msh", "transport_data.txt", "electron_moments.txt"):
        if not (case_dir / required).is_file():
            raise DiagnosticError(f"missing required Issue91 asset: {case_dir / required}")
    qpx = _resolve_qpx(args.qpx)

    if args.work_dir:
        work_root = args.work_dir.resolve()
        work_root.mkdir(parents=True, exist_ok=True)
    else:
        work_root = Path(tempfile.mkdtemp(prefix="issue92_r3_nonlinear_"))
    work_case = work_root / "case"
    logs = work_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    _copy_case_dependencies(case_dir, work_case)

    canonical, build_meta = build_r3_input((case_dir / "heavy_base.i").read_text(), field_strength=0.0)
    automatic_scaling = (mp.get_parameter(canonical, "Executioner", "automatic_scaling") or "").strip().lower()
    if automatic_scaling not in {"true", "1"}:
        raise DiagnosticError("canonical R3-E0 must have Executioner/automatic_scaling enabled")
    (work_case / "canonical_r3_e0.i").write_text(canonical)
    _json_write(work_root / "prepare_evidence.json", build_meta)

    manifest: dict[str, Any] = {
        "issue": ISSUE,
        "evr": EVR,
        "started_at": _utc_now(),
        "case_dir": str(case_dir),
        "work_root": str(work_root),
        "qpx": qpx,
        "canonical_input_sha256": _sha256_text(canonical),
        "subruns": [],
    }
    hypotheses = _hypotheses()
    summary: dict[str, Any] = {
        "issue": ISSUE,
        "evr": EVR,
        "selected_branch": "B0",
        "terminal_reason": "NOT_STARTED",
        "hypotheses": hypotheses,
        "scientific_acceptance_eligible": False,
        "d1": None,
        "d2a": None,
        "d2b": None,
        "d2c": None,
    }

    d1_text = build_overlay(canonical)
    d1 = _write_overlay(work_case, "d1_residual_anatomy", d1_text)
    d1_check, d1_run = _check_and_run(
        qpx=qpx, work_case=work_case, overlay=d1, name="d1_residual_anatomy", logs=logs, timeout=args.timeout
    )
    _record_subrun(
        manifest,
        name="D1",
        overlay=d1,
        changed_axis=["line_search=none", "nl_max_its=3", "Debug residual anatomy"],
        check=d1_check,
        run=d1_run,
    )
    if d1_run is None:
        summary["selected_branch"] = "B0"
        summary["terminal_reason"] = "D1_CHECK_INPUT_FAIL"
        hypotheses["H6"] = "FAVORED"
        return _finish(work_root, manifest, summary, 2)

    d1_analysis = analyze_residual_log(Path(d1_run.log).read_text())
    summary["d1"] = asdict(d1_analysis)
    branch, reason = classify_d1(d1_analysis)
    summary["selected_branch"] = branch
    summary["terminal_reason"] = reason

    if branch == "B1":
        hypotheses["H5"] = "FAVORED"
        return _finish(work_root, manifest, summary, 1)
    if branch == "B7":
        hypotheses["H6"] = "HOLD"
        return _finish(work_root, manifest, summary, 1)

    if branch in {"B2", "B3", "B4"}:
        d2a_text = build_overlay(canonical, residual_scaling=True)
        d2a = _write_overlay(work_case, "d2a_residual_scaling", d2a_text)
        check, run = _check_and_run(
            qpx=qpx, work_case=work_case, overlay=d2a, name="d2a_residual_scaling", logs=logs, timeout=args.timeout
        )
        _record_subrun(
            manifest,
            name="D2A",
            overlay=d2a,
            changed_axis=["resid_vs_jac_scaling_param=1"],
            check=check,
            run=run,
        )
        if run is None:
            summary["terminal_reason"] = "D2A_CHECK_INPUT_FAIL"
            hypotheses["H6"] = "FAVORED"
            return _finish(work_root, manifest, summary, 2)
        d2a_analysis = analyze_residual_log(Path(run.log).read_text())
        favored = scaling_discriminator(d1_analysis, d2a_analysis)
        summary["d2a"] = {**asdict(d2a_analysis), "h2_scaling_favored": favored}
        if favored:
            hypotheses["H2"] = "FAVORED"
            hypotheses["H3"] = "OPEN"
            summary["terminal_reason"] = f"{reason}; RESIDUAL_SCALING_COLLAPSED_DOMINANCE_AND_IMPROVED_TRAJECTORY"
            return _finish(work_root, manifest, summary, 0)
        hypotheses["H2"] = "DISFAVORED"
        hypotheses["H3"] = "FAVORED"
    elif branch == "B5":
        hypotheses["H2"] = "DISFAVORED"
        hypotheses["H3"] = "FAVORED"
    elif branch == "B6":
        hypotheses["H2"] = "DISFAVORED"
        hypotheses["H3"] = "FAVORED"

    cells = estimate_gmsh_2d_cells(work_case / "qvt.msh")
    estimated_dofs = cells * len(ALL_VARIABLES) if cells is not None else None
    cost_guard = estimated_dofs is None or estimated_dofs > args.max_jacobian_dofs
    summary["d2b"] = {
        "mesh_2d_cells": cells,
        "estimated_solution_dofs": estimated_dofs,
        "max_jacobian_dofs": args.max_jacobian_dofs,
        "cost_guard": cost_guard,
    }
    if cost_guard:
        summary["d2b"]["jacobian_status"] = "JACOBIAN_CHECK_SKIPPED_COST_GUARD"
        summary["terminal_reason"] += "; JACOBIAN_CHECK_SKIPPED_COST_GUARD"
        hypotheses["H3"] = "HOLD" if branch == "B6" else hypotheses["H3"]
        return _finish(work_root, manifest, summary, 1)

    d2b_text = build_overlay(canonical, nl_max_its=1)
    d2b = _write_overlay(work_case, "d2b_jacobian", d2b_text)
    check, run = _check_and_run(
        qpx=qpx,
        work_case=work_case,
        overlay=d2b,
        name="d2b_jacobian",
        logs=logs,
        timeout=args.timeout,
        extra_run_args=["-snes_test_jacobian"],
    )
    _record_subrun(
        manifest,
        name="D2B",
        overlay=d2b,
        changed_axis=["-snes_test_jacobian", "nl_max_its=1"],
        check=check,
        run=run,
    )
    if run is None:
        summary["d2b"]["jacobian_status"] = "CHECK_INPUT_FAIL"
        summary["terminal_reason"] += "; D2B_CHECK_INPUT_FAIL"
        hypotheses["H6"] = "FAVORED"
        return _finish(work_root, manifest, summary, 2)
    jac_status, jac_rows = classify_jacobian(Path(run.log).read_text())
    summary["d2b"].update({"jacobian_status": jac_status, "rows": jac_rows})
    if jac_status == "MATERIAL_MISMATCH":
        hypotheses["H3"] = "FAVORED"
        summary["terminal_reason"] += "; MATERIAL_JACOBIAN_MISMATCH"
        return _finish(work_root, manifest, summary, 0)
    if jac_status != "ACCEPTABLE":
        hypotheses["H3"] = "HOLD"
        summary["terminal_reason"] += f"; JACOBIAN_{jac_status}"
        return _finish(work_root, manifest, summary, 1)

    hypotheses["H3"] = "DISFAVORED"
    d2c_text = build_overlay(canonical, dt=1.0e-9)
    d2c = _write_overlay(work_case, "d2c_dt_1e9", d2c_text)
    check, run = _check_and_run(
        qpx=qpx, work_case=work_case, overlay=d2c, name="d2c_dt_1e9", logs=logs, timeout=args.timeout
    )
    _record_subrun(
        manifest,
        name="D2C",
        overlay=d2c,
        changed_axis=["dt=1e-9", "end_time=1e-9"],
        check=check,
        run=run,
    )
    if run is None:
        summary["d2c"] = {"status": "CHECK_INPUT_FAIL"}
        summary["terminal_reason"] += "; D2C_CHECK_INPUT_FAIL"
        hypotheses["H6"] = "FAVORED"
        return _finish(work_root, manifest, summary, 2)
    d2c_analysis = analyze_residual_log(Path(run.log).read_text())
    favored = trajectory_improved(d1_analysis, d2c_analysis)
    summary["d2c"] = {**asdict(d2c_analysis), "h4_temporal_favored": favored}
    if favored:
        hypotheses["H4"] = "FAVORED"
        summary["terminal_reason"] += "; DT_1E9_BREAKS_CYCLE_OR_GIVES_CLEAR_DESCENT"
        return _finish(work_root, manifest, summary, 0)
    hypotheses["H4"] = "DISFAVORED"
    summary["terminal_reason"] += "; SAME_BLOCKER_AT_DT_1E9"
    return _finish(work_root, manifest, summary, 1)


def _finish(work_root: Path, manifest: dict[str, Any], summary: dict[str, Any], rc: int) -> int:
    manifest["finished_at"] = _utc_now()
    manifest["terminal_branch"] = summary["selected_branch"]
    manifest["scientific_acceptance_eligible"] = False
    _json_write(work_root / "manifest.json", manifest)
    _json_write(work_root / "summary.json", summary)
    (work_root / "decision.txt").write_text(_decision_text(summary))
    print(_decision_text(summary), end="")
    print(f"ARTIFACT_ROOT: {work_root}")
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True, help="Issue91 r3_e0 case directory")
    parser.add_argument("--qpx", required=True, help="qpx-opt path or executable name")
    parser.add_argument("--work-dir", type=Path, help="persistent output directory; default is a temp directory")
    parser.add_argument("--max-jacobian-dofs", type=int, default=DEFAULT_MAX_JACOBIAN_DOFS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="per-command timeout in seconds")
    args = parser.parse_args()
    if args.max_jacobian_dofs < 1:
        parser.error("--max-jacobian-dofs must be positive")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    try:
        return run_batch(args)
    except DiagnosticError as exc:
        print(f"ISSUE92_DIAGNOSTIC_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
