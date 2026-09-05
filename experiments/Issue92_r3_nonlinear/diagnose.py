#!/usr/bin/env python3
"""Issue #92 one-shot adaptive diagnostic driver for the real-QVT R3 blocker.

Issue-scoped only: this is diagnostic orchestration, not a reusable qpx_harness
capability and never a scientific-acceptance run.
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
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp
from experiments.historical_recipe_support.issue91_r3 import build_r3_input

ISSUE = 92
EVR = 2
DOMINANCE_RATIO = 10.0
JAC_PASS = 1.0e-5
JAC_FAIL = 1.0e-3
DEFAULT_MAX_JAC_DOF = 4000
DEFAULT_TIMEOUT = 600

GROUPS: dict[str, tuple[str, ...]] = {
    "FLOW": ("u", "v", "p"),
    "HEAVY_NEUTRAL": ("w_O2s", "w_O", "w_Os"),
    "HEAVY_CHARGED": ("w_O2p", "w_Om", "w_Op"),
    "ELECTRON": ("n_e",),
}
ALL_VARS = tuple(v for names in GROUPS.values() for v in names)
FLOAT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
NL_PATTERNS = (
    re.compile(rf"^\s*(\d+)\s+Nonlinear\s+\|R\|\s*=\s*({FLOAT})\s*$"),
    re.compile(rf"^\s*(\d+)\s+SNES\s+Function\s+norm\s+({FLOAT})\s*$", re.I),
    re.compile(rf"^\s*(\d+)\s+({FLOAT})\s*$"),
)
VAR_LINE = re.compile(rf"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*({FLOAT})\s*$")
JAC_LINE = re.compile(rf"Norm of matrix ratio\s+({FLOAT}),\s*difference\s+({FLOAT})", re.I)
NONFINITE = re.compile(r"(?i)(?:^|[\s=(:,])(?:nan|[+-]?inf(?:inity)?)(?:$|[\s,;)])")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
VAR_HEADERS = {
    "|residual|_2 of individual variables:",  # current MOOSE VariableResidualNormsDebugOutput
    "Variable Residual Norms:",               # retained for older persisted evidence
}


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _resolve_qpx(value: str) -> str:
    p = Path(value).expanduser()
    if "/" in value:
        if not p.is_file():
            raise DiagnosticError(f"qpx executable does not exist: {p}")
        return str(p.resolve())
    found = shutil.which(value)
    if not found:
        raise DiagnosticError(f"qpx executable not found on PATH: {value}")
    return found


def _run(cmd: list[str], cwd: Path, log: Path, timeout: int) -> CommandResult:
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        output, rc = result.stdout or "", result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out, rc = True, 124
        raw = exc.stdout or ""
        output = raw.decode() if isinstance(raw, bytes) else raw
        output += f"\nISSUE92_TIMEOUT_AFTER_SECONDS={timeout}\n"
    elapsed = time.monotonic() - started
    log.write_text(output)
    return CommandResult(cmd, rc, elapsed, timed_out, str(log))


def _copy_assets(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for p in source.iterdir():
        if not p.is_file():
            continue
        if p.name in {"input.i", "prepare_evidence.json", "run.log"}:
            continue
        if p.name.startswith("input_out") or p.suffix in {".csv", ".e", ".exo"}:
            continue
        shutil.copy2(p, dest / p.name)


def _debug_overlay(text: str) -> str:
    if not mb.has_block(text, "Debug"):
        text = mb.append_top_level_block(text, "[Debug]\n[]")
    text = mp.upsert_parameter(text, "Debug", "show_var_residual_norms", "true")
    return mp.upsert_parameter(text, "Debug", "show_top_residuals", "20")


def build_overlay(
    canonical: str, *, residual_scaling: bool = False, dt: float | None = None, nl_max_its: int = 3
) -> str:
    text = mp.upsert_parameter(canonical, "Executioner", "line_search", "none")
    text = mp.upsert_parameter(text, "Executioner", "nl_max_its", str(nl_max_its))
    text = mp.upsert_parameter(text, "Executioner", "abort_on_solve_fail", "true")
    if residual_scaling:
        text = mp.upsert_parameter(text, "Executioner", "resid_vs_jac_scaling_param", "1")
    if dt is not None:
        if not math.isfinite(dt) or dt <= 0:
            raise DiagnosticError("diagnostic dt must be finite and positive")
        value = f"{dt:.17g}"
        text = mp.upsert_parameter(text, "Executioner", "dt", value)
        text = mp.upsert_parameter(text, "Executioner", "end_time", value)
    return _debug_overlay(text)


def parse_global_residuals(log: str) -> list[float]:
    values: list[float] = []
    for raw in log.splitlines():
        line = ANSI.sub("", raw)
        for pattern in NL_PATTERNS:
            m = pattern.match(line)
            if m:
                value = float(m.group(2))
                if math.isfinite(value):
                    values.append(value)
                break
    return values


def parse_variable_residuals(log: str) -> list[dict[str, float]]:
    tables: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for raw in log.splitlines():
        line = ANSI.sub("", raw).strip()
        if line in VAR_HEADERS:
            if current:
                tables.append(current)
            current = {}
            continue
        if current is None:
            continue
        m = VAR_LINE.match(line)
        if m:
            name, raw_value = m.groups()
            if name in ALL_VARS:
                value = float(raw_value)
                if math.isfinite(value):
                    current[name] = value
            continue
        if current and (line or not line):
            tables.append(current)
        current = None
    if current:
        tables.append(current)
    return tables


def _group_norms(table: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for group, names in GROUPS.items():
        vals = [table[n] for n in names if n in table]
        if vals:
            out[group] = math.sqrt(sum(v * v for v in vals))
    return out


def _dominance(table: dict[str, float]) -> tuple[str | None, float]:
    ranked = sorted((v, k) for k, v in table.items() if math.isfinite(v) and v >= 0)
    if not ranked:
        return None, math.nan
    top, name = ranked[-1]
    if len(ranked) == 1:
        return name, math.inf if top > 0 else 1.0
    second = ranked[-2][0]
    return name, (math.inf if second == 0 and top > 0 else (1.0 if second == 0 else top / second))


def detect_two_cycle(values: list[float], rel_tol: float = 0.05) -> bool:
    if len(values) < 4:
        return False
    vals = values[-6:]
    lag2 = [abs(vals[i] - vals[i - 2]) / max(abs(vals[i]), abs(vals[i - 2]), 1e-30) for i in range(2, len(vals))]
    adjacent = [abs(vals[i] - vals[i - 1]) / max(abs(vals[i]), abs(vals[i - 1]), 1e-30) for i in range(1, len(vals))]
    return max(lag2) <= rel_tol and max(adjacent) >= 0.03


def analyze_residual_log(log: str) -> ResidualAnalysis:
    global_residuals = parse_global_residuals(log)
    variable_norms = parse_variable_residuals(log)
    group_norms = [_group_norms(t) for t in variable_norms]
    dom = [_dominance(t) for t in group_norms]
    return ResidualAnalysis(
        global_residuals, variable_norms, group_norms,
        [d[1] for d in dom], [d[0] for d in dom], detect_two_cycle(global_residuals),
        bool(NONFINITE.search(ANSI.sub("", log))), bool(global_residuals and variable_norms),
    )


def classify_d1(a: ResidualAnalysis) -> tuple[str, str]:
    if a.nonfinite:
        return "B1", "NONFINITE_OR_INVALID_STATE"
    if not a.parse_complete:
        return "B7", "DIAGNOSTIC_OUTPUT_INCOMPLETE_OR_CONFIGURATION_MISMATCH"
    if not a.two_cycle:
        return "B7", "CANONICAL_TWO_CYCLE_NOT_REPRODUCED"
    material = [(g, r) for g, r in zip(a.dominant_groups, a.group_ratios) if g and r >= DOMINANCE_RATIO]
    groups = [g for g, _ in material]
    if len(set(groups)) >= 2:
        return "B5", "DOMINANT_GROUP_ALTERNATES_WITH_TWO_CYCLE"
    if not groups:
        return "B6", "VARIABLE_GROUP_RESIDUALS_COMPARABLE_WITH_TWO_CYCLE"
    group = groups[-1]
    return {
        "ELECTRON": ("B2", "ELECTRON_RESIDUAL_DOMINANCE"),
        "HEAVY_CHARGED": ("B3", "CHARGED_HEAVY_RESIDUAL_DOMINANCE"),
        "FLOW": ("B4", "FLOW_RESIDUAL_DOMINANCE"),
    }.get(group, ("B3", "HEAVY_RESIDUAL_DOMINANCE"))


def _median_ratio(values: Iterable[float]) -> float:
    vals = sorted(1e300 if math.isinf(v) else v for v in values if not math.isnan(v))
    if not vals:
        return math.nan
    n = len(vals)
    return vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])


def trajectory_improved(ref: ResidualAnalysis, candidate: ResidualAnalysis) -> bool:
    if not candidate.global_residuals:
        return False
    first, last = candidate.global_residuals[0], candidate.global_residuals[-1]
    return first > 0 and (last / first <= 0.8 or (ref.two_cycle and not candidate.two_cycle and last < 0.9 * first))


def scaling_discriminator(ref: ResidualAnalysis, candidate: ResidualAnalysis) -> bool:
    r0, r1 = _median_ratio(ref.group_ratios), _median_ratio(candidate.group_ratios)
    collapse = math.isfinite(r1) and (r1 < DOMINANCE_RATIO or (math.isfinite(r0) and r1 <= 0.5 * r0))
    return collapse and trajectory_improved(ref, candidate)


def classify_jacobian(log: str) -> tuple[str, list[dict[str, float]]]:
    rows = [{"ratio": float(m.group(1)), "difference": float(m.group(2))} for m in JAC_LINE.finditer(log)]
    if not rows:
        return "UNAVAILABLE", rows
    worst = max(r["ratio"] for r in rows)
    if worst <= JAC_PASS:
        return "ACCEPTABLE", rows
    if worst >= JAC_FAIL:
        return "MATERIAL_MISMATCH", rows
    return "AMBIGUOUS", rows


def estimate_gmsh_2d_cells(path: Path) -> int | None:
    try:
        lines = path.read_text().splitlines()
        start = lines.index("$Elements")
        count = int(lines[start + 1])
    except (OSError, UnicodeDecodeError, ValueError, IndexError):
        return None
    cell_types = {2, 3, 9, 10, 16}
    cells = 0
    for line in lines[start + 2:start + 2 + count]:
        parts = line.split()
        try:
            cells += int(len(parts) >= 2 and int(parts[1]) in cell_types)
        except ValueError:
            return None
    return cells


def _check_run(qpx: str, case: Path, overlay: Path, logs: Path, name: str, timeout: int, extra: list[str] | None = None) -> tuple[CommandResult, CommandResult | None]:
    check = _run([qpx, "-i", overlay.name, "--check-input"], case, logs / f"{name}_check.log", timeout)
    if check.returncode != 0:
        return check, None
    cmd = [qpx, "-i", overlay.name, "-snes_converged_reason", "-ksp_converged_reason"]
    if extra:
        cmd += extra
    return check, _run(cmd, case, logs / f"{name}.log", timeout)


def _subrun(manifest: dict[str, Any], name: str, overlay: Path, axis: list[str], check: CommandResult, run: CommandResult | None) -> None:
    manifest["subruns"].append({
        "name": name, "overlay": str(overlay), "overlay_sha256": _sha(overlay.read_text()),
        "changed_axis": axis, "check": asdict(check), "run": asdict(run) if run else None,
        "scientific_acceptance_eligible": False,
    })


def _overlay(case: Path, name: str, text: str) -> Path:
    p = case / f"{name}.i"
    p.write_text(text)
    return p


def _finish(root: Path, manifest: dict[str, Any], summary: dict[str, Any], rc: int) -> int:
    manifest.update(finished_at=_now(), terminal_branch=summary["selected_branch"], scientific_acceptance_eligible=False)
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "summary.json", summary)
    hyp = " ".join(f"{k}={v}" for k, v in summary["hypotheses"].items())
    decision = (
        f"ISSUE92_DIAGNOSTIC_BRANCH: {summary['selected_branch']}\n"
        f"TERMINAL_REASON: {summary['terminal_reason']}\n"
        f"HYPOTHESES: {hyp}\nEVR: {EVR}\nSCIENTIFIC_ACCEPTANCE_ELIGIBLE: false\n"
    )
    (root / "decision.txt").write_text(decision)
    print(decision, end="")
    print(f"ARTIFACT_ROOT: {root}")
    return rc


def run_batch(args: argparse.Namespace) -> int:
    source = args.case_dir.resolve()
    for name in ("heavy_base.i", "qvt.msh", "transport_data.txt", "electron_moments.txt"):
        if not (source / name).is_file():
            raise DiagnosticError(f"missing required Issue91 asset: {source / name}")
    qpx = _resolve_qpx(args.qpx)
    root = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix="issue92_r3_nonlinear_"))
    case, logs = root / "case", root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    _copy_assets(source, case)

    canonical, build_meta = build_r3_input((source / "heavy_base.i").read_text(), field_strength=0.0)
    auto = (mp.get_parameter(canonical, "Executioner", "automatic_scaling") or "").strip().lower()
    if auto not in {"true", "1"}:
        raise DiagnosticError("canonical R3-E0 must have automatic_scaling enabled")
    (case / "canonical_r3_e0.i").write_text(canonical)
    _write_json(root / "prepare_evidence.json", build_meta)

    manifest: dict[str, Any] = {
        "issue": ISSUE, "evr": EVR, "started_at": _now(), "case_dir": str(source),
        "work_root": str(root), "qpx": qpx, "canonical_input_sha256": _sha(canonical), "subruns": [],
    }
    hyp = {"H1": "DISFAVORED", "H2": "OPEN", "H3": "OPEN", "H4": "OPEN", "H5": "OPEN", "H6": "OPEN"}
    summary: dict[str, Any] = {
        "issue": ISSUE, "evr": EVR, "selected_branch": "B0", "terminal_reason": "NOT_STARTED",
        "hypotheses": hyp, "scientific_acceptance_eligible": False,
        "d1": None, "d2a": None, "d2b": None, "d2c": None,
    }

    d1 = _overlay(case, "d1_residual_anatomy", build_overlay(canonical))
    check, run = _check_run(qpx, case, d1, logs, "d1_residual_anatomy", args.timeout)
    _subrun(manifest, "D1", d1, ["line_search=none", "nl_max_its=3", "Debug residual anatomy"], check, run)
    if run is None:
        summary.update(selected_branch="B0", terminal_reason="D1_CHECK_INPUT_FAIL")
        hyp["H6"] = "FAVORED"
        return _finish(root, manifest, summary, 2)
    a1 = analyze_residual_log(Path(run.log).read_text())
    summary["d1"] = asdict(a1)
    branch, reason = classify_d1(a1)
    summary.update(selected_branch=branch, terminal_reason=reason)
    if branch == "B1":
        hyp["H5"] = "FAVORED"
        return _finish(root, manifest, summary, 1)
    if branch == "B7":
        hyp["H6"] = "HOLD"
        return _finish(root, manifest, summary, 1)

    if branch in {"B2", "B3", "B4"}:
        p = _overlay(case, "d2a_residual_scaling", build_overlay(canonical, residual_scaling=True))
        check, run = _check_run(qpx, case, p, logs, "d2a_residual_scaling", args.timeout)
        _subrun(manifest, "D2A", p, ["resid_vs_jac_scaling_param=1"], check, run)
        if run is None:
            summary["terminal_reason"] += "; D2A_CHECK_INPUT_FAIL"
            hyp["H6"] = "FAVORED"
            return _finish(root, manifest, summary, 2)
        a2 = analyze_residual_log(Path(run.log).read_text())
        favored = scaling_discriminator(a1, a2)
        summary["d2a"] = {**asdict(a2), "h2_scaling_favored": favored}
        if favored:
            hyp["H2"] = "FAVORED"
            summary["terminal_reason"] += "; RESIDUAL_SCALING_COLLAPSED_DOMINANCE_AND_IMPROVED_TRAJECTORY"
            return _finish(root, manifest, summary, 0)
        hyp.update(H2="DISFAVORED", H3="FAVORED")
    else:
        hyp.update(H2="DISFAVORED", H3="FAVORED")

    cells = estimate_gmsh_2d_cells(case / "qvt.msh")
    dofs = cells * len(ALL_VARS) if cells is not None else None
    guard = dofs is None or dofs > args.max_jacobian_dofs
    summary["d2b"] = {"mesh_2d_cells": cells, "estimated_solution_dofs": dofs, "max_jacobian_dofs": args.max_jacobian_dofs, "cost_guard": guard}
    if guard:
        summary["d2b"]["jacobian_status"] = "JACOBIAN_CHECK_SKIPPED_COST_GUARD"
        summary["terminal_reason"] += "; JACOBIAN_CHECK_SKIPPED_COST_GUARD"
        if branch == "B6":
            hyp["H3"] = "HOLD"
        return _finish(root, manifest, summary, 1)

    p = _overlay(case, "d2b_jacobian", build_overlay(canonical, nl_max_its=1))
    check, run = _check_run(qpx, case, p, logs, "d2b_jacobian", args.timeout, ["-snes_test_jacobian"])
    _subrun(manifest, "D2B", p, ["-snes_test_jacobian", "nl_max_its=1"], check, run)
    if run is None:
        summary["d2b"]["jacobian_status"] = "CHECK_INPUT_FAIL"
        hyp["H6"] = "FAVORED"
        summary["terminal_reason"] += "; D2B_CHECK_INPUT_FAIL"
        return _finish(root, manifest, summary, 2)
    status, rows = classify_jacobian(Path(run.log).read_text())
    summary["d2b"].update(jacobian_status=status, rows=rows)
    if status == "MATERIAL_MISMATCH":
        hyp["H3"] = "FAVORED"
        summary["terminal_reason"] += "; MATERIAL_JACOBIAN_MISMATCH"
        return _finish(root, manifest, summary, 0)
    if status != "ACCEPTABLE":
        hyp["H3"] = "HOLD"
        summary["terminal_reason"] += f"; JACOBIAN_{status}"
        return _finish(root, manifest, summary, 1)

    hyp["H3"] = "DISFAVORED"
    p = _overlay(case, "d2c_dt_1e9", build_overlay(canonical, dt=1e-9))
    check, run = _check_run(qpx, case, p, logs, "d2c_dt_1e9", args.timeout)
    _subrun(manifest, "D2C", p, ["dt=1e-9", "end_time=1e-9"], check, run)
    if run is None:
        summary["d2c"] = {"status": "CHECK_INPUT_FAIL"}
        hyp["H6"] = "FAVORED"
        summary["terminal_reason"] += "; D2C_CHECK_INPUT_FAIL"
        return _finish(root, manifest, summary, 2)
    a3 = analyze_residual_log(Path(run.log).read_text())
    favored = trajectory_improved(a1, a3)
    summary["d2c"] = {**asdict(a3), "h4_temporal_favored": favored}
    hyp["H4"] = "FAVORED" if favored else "DISFAVORED"
    summary["terminal_reason"] += "; " + ("DT_1E9_BREAKS_CYCLE_OR_GIVES_CLEAR_DESCENT" if favored else "SAME_BLOCKER_AT_DT_1E9")
    return _finish(root, manifest, summary, 0 if favored else 1)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case-dir", type=Path, required=True)
    p.add_argument("--qpx", required=True)
    p.add_argument("--work-dir", type=Path)
    p.add_argument("--max-jacobian-dofs", type=int, default=DEFAULT_MAX_JAC_DOF)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = p.parse_args()
    if args.max_jacobian_dofs < 1 or args.timeout < 1:
        p.error("--max-jacobian-dofs and --timeout must be positive")
    try:
        return run_batch(args)
    except DiagnosticError as exc:
        print(f"ISSUE92_DIAGNOSTIC_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
