#!/usr/bin/env python3
"""Issue #92 EVR3 continuation from preserved B2 electron-dominance evidence.

Order:
  T0 qpx-free characteristic-time audit
  -> D2A residual-scaling discriminator
  -> D2C T0-informed temporal discriminator first when T0-B is established
  -> D2B bounded Jacobian consistency only after the temporal branch, if needed

D1 is not rerun. This file is Issue-specific diagnostic orchestration, not a
qpx_harness production capability and not a scientific-acceptance runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.Issue92_r3_nonlinear.characteristic_time import audit_case
from experiments.Issue92_r3_nonlinear.diagnose import (
    ALL_VARS,
    CommandResult,
    DiagnosticError,
    ResidualAnalysis,
    _dominance,
    _group_norms,
    analyze_residual_log,
    build_overlay,
    classify_jacobian,
    scaling_discriminator,
    trajectory_improved,
)
from experiments.historical_recipe_support.issue91_r3 import build_r3_input
from physics_harness.adapters.moose import parameters as mp

ISSUE = 92
EVR = 3
DEFAULT_MAX_JAC_DOF = 4000
DEFAULT_TIMEOUT = 600
REFERENCE = Path(__file__).with_name("evr2_d1_reference.json")


class Evr3Error(RuntimeError):
    pass


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
            raise Evr3Error(f"qpx executable does not exist: {p}")
        return str(p.resolve())
    found = shutil.which(value)
    if not found:
        raise Evr3Error(f"qpx executable not found on PATH: {value}")
    return found


def _run(cmd: list[str], cwd: Path, log: Path, timeout: int) -> CommandResult:
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output, rc = result.stdout or "", result.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out, rc = True, 124
        raw = exc.stdout or ""
        output = raw.decode() if isinstance(raw, bytes) else raw
        output += f"\nISSUE92_EVR3_TIMEOUT_AFTER_SECONDS={timeout}\n"
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


def _overlay(case: Path, name: str, text: str) -> Path:
    p = case / f"{name}.i"
    p.write_text(text)
    return p


def _check_run(
    qpx: str,
    case: Path,
    overlay: Path,
    logs: Path,
    name: str,
    timeout: int,
    extra: list[str] | None = None,
) -> tuple[CommandResult, CommandResult | None]:
    check = _run([qpx, "-i", overlay.name, "--check-input"], case, logs / f"{name}_check.log", timeout)
    if check.returncode != 0:
        return check, None
    cmd = [qpx, "-i", overlay.name, "-snes_converged_reason", "-ksp_converged_reason"]
    if extra:
        cmd += extra
    return check, _run(cmd, case, logs / f"{name}.log", timeout)


def _subrun(
    manifest: dict[str, Any],
    name: str,
    overlay: Path,
    axis: list[str],
    check: CommandResult,
    run: CommandResult | None,
) -> None:
    manifest["subruns"].append(
        {
            "name": name,
            "overlay": str(overlay),
            "overlay_sha256": _sha(overlay.read_text()),
            "changed_axis": axis,
            "check": asdict(check),
            "run": asdict(run) if run else None,
            "scientific_acceptance_eligible": False,
        }
    )


def _with_electron_fallback(log: str) -> ResidualAnalysis:
    a = analyze_residual_log(log)
    if a.global_residuals or not a.variable_norms:
        return a
    electron = [t["n_e"] for t in a.variable_norms if "n_e" in t]
    if not electron:
        return a
    from experiments.Issue92_r3_nonlinear.diagnose import detect_two_cycle

    return ResidualAnalysis(
        global_residuals=electron,
        variable_norms=a.variable_norms,
        group_norms=a.group_norms,
        group_ratios=a.group_ratios,
        dominant_groups=a.dominant_groups,
        two_cycle=detect_two_cycle(electron),
        nonfinite=a.nonfinite,
        parse_complete=bool(a.variable_norms),
    )


def _load_reference(path: Path = REFERENCE) -> ResidualAnalysis:
    data = json.loads(path.read_text())
    tables = data["variable_norms"]
    group_norms = [_group_norms(t) for t in tables]
    dom = [_dominance(t) for t in group_norms]
    return ResidualAnalysis(
        global_residuals=[float(v) for v in data["electron_residuals"]],
        variable_norms=tables,
        group_norms=group_norms,
        group_ratios=[d[1] for d in dom],
        dominant_groups=[d[0] for d in dom],
        two_cycle=bool(data["two_cycle_supported_by_electron_residual"]),
        nonfinite=False,
        parse_complete=True,
    )


def _plasma_cell_count_v41(mesh_text: str) -> int | None:
    lines = mesh_text.splitlines()
    try:
        p = lines.index("$PhysicalNames")
        nphys = int(lines[p + 1])
        plasma_phys = None
        for raw in lines[p + 2 : p + 2 + nphys]:
            parts = raw.split(maxsplit=2)
            if len(parts) == 3 and parts[0] == "2" and parts[2].strip('"') == "plasma":
                plasma_phys = int(parts[1])
                break
        if plasma_phys is None:
            return None

        e = lines.index("$Entities")
        np, nc, ns, _nv = (int(v) for v in lines[e + 1].split())
        cursor = e + 2 + np + nc
        plasma_entity = None
        for raw in lines[cursor : cursor + ns]:
            parts = raw.split()
            npt = int(parts[7])
            tags = [int(v) for v in parts[8 : 8 + npt]]
            if plasma_phys in tags:
                plasma_entity = int(parts[0])
                break
        if plasma_entity is None:
            return None

        k = lines.index("$Elements")
        nblocks = int(lines[k + 1].split()[0])
        cursor = k + 2
        count = 0
        for _ in range(nblocks):
            dim, entity, _etype, n = (int(v) for v in lines[cursor].split())
            cursor += 1
            if dim == 2 and entity == plasma_entity:
                count += n
            cursor += n
        return count
    except (ValueError, IndexError):
        return None


def _diagnostic_order(t0_decision: str) -> tuple[str, ...]:
    if t0_decision == "T0-B":
        return ("D2A", "D2C", "D2B_OPTIONAL")
    return ("D2A", "D2B")


def _finish(root: Path, manifest: dict[str, Any], summary: dict[str, Any], rc: int) -> int:
    manifest.update(
        finished_at=_now(),
        terminal_branch=summary["selected_branch"],
        scientific_acceptance_eligible=False,
    )
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "summary.json", summary)
    hyp = " ".join(f"{k}={v}" for k, v in summary["hypotheses"].items())
    decision = (
        f"ISSUE92_EVR3_BRANCH: {summary['selected_branch']}\n"
        f"TERMINAL_REASON: {summary['terminal_reason']}\n"
        f"T0_DECISION: {summary['t0']['decision']}\n"
        f"HYPOTHESES: {hyp}\n"
        f"EVR: {EVR}\n"
        "SCIENTIFIC_ACCEPTANCE_ELIGIBLE: false\n"
    )
    (root / "decision.txt").write_text(decision)
    print(decision, end="")
    print(f"ARTIFACT_ROOT: {root}")
    return rc


def _run_jacobian_branch(
    *,
    qpx: str,
    case: Path,
    canonical: str,
    logs: Path,
    manifest: dict[str, Any],
    summary: dict[str, Any],
    hyp: dict[str, str],
    max_jacobian_dofs: int,
    timeout: int,
) -> tuple[bool, int | None]:
    mesh_text = (case / "qvt.msh").read_text()
    cells = _plasma_cell_count_v41(mesh_text)
    dofs = cells * len(ALL_VARS) if cells is not None else None
    guard = dofs is None or dofs > max_jacobian_dofs
    summary["d2b"] = {
        "mesh_2d_cells": cells,
        "estimated_solution_dofs": dofs,
        "max_jacobian_dofs": max_jacobian_dofs,
        "cost_guard": guard,
    }
    if guard:
        summary["d2b"]["jacobian_status"] = "JACOBIAN_CHECK_SKIPPED_COST_GUARD"
        hyp["H3"] = "HOLD"
        return False, None

    p = _overlay(case, "d2b_jacobian", build_overlay(canonical, nl_max_its=1))
    check, runtime = _check_run(
        qpx,
        case,
        p,
        logs,
        "d2b_jacobian",
        timeout,
        ["-snes_test_jacobian"],
    )
    _subrun(manifest, "D2B", p, ["-snes_test_jacobian", "nl_max_its=1"], check, runtime)
    if runtime is None:
        summary["d2b"]["jacobian_status"] = "CHECK_INPUT_FAIL"
        hyp["H6"] = "FAVORED"
        summary["terminal_reason"] = "D2B_CHECK_INPUT_FAIL"
        return True, 2
    status, rows = classify_jacobian(Path(runtime.log).read_text())
    summary["d2b"].update(jacobian_status=status, rows=rows)
    if status == "MATERIAL_MISMATCH":
        hyp["H3"] = "FAVORED"
        summary["terminal_reason"] = "MATERIAL_JACOBIAN_MISMATCH"
        return True, 0
    if status != "ACCEPTABLE":
        hyp["H3"] = "HOLD"
        summary["terminal_reason"] = f"JACOBIAN_{status}"
        return True, 1
    hyp["H3"] = "DISFAVORED"
    return False, None


def run(args: argparse.Namespace) -> int:
    source = args.case_dir.resolve()
    required = ("heavy_base.i", "qvt.msh", "transport_data.txt", "electron_moments.txt")
    for name in required:
        if not (source / name).is_file():
            raise Evr3Error(f"missing required Issue91 asset: {source / name}")

    # T0 is deliberately completed before qpx resolution/execution.
    t0 = audit_case(source)
    reference = _load_reference()

    qpx = _resolve_qpx(args.qpx)
    root = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix="issue92_evr3_"))
    case, logs = root / "case", root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    _copy_assets(source, case)

    canonical, build_meta = build_r3_input((source / "heavy_base.i").read_text(), field_strength=0.0)
    auto = (mp.get_parameter(canonical, "Executioner", "automatic_scaling") or "").strip().lower()
    if auto not in {"true", "1"}:
        raise Evr3Error("canonical R3-E0 must have automatic_scaling enabled")
    (case / "canonical_r3_e0.i").write_text(canonical)
    _write_json(root / "prepare_evidence.json", build_meta)
    _write_json(root / "t0_summary.json", t0)

    manifest: dict[str, Any] = {
        "issue": ISSUE,
        "evr": EVR,
        "started_at": _now(),
        "case_dir": str(source),
        "work_root": str(root),
        "qpx": qpx,
        "canonical_input_sha256": _sha(canonical),
        "evr2_reference_sha256": _sha(REFERENCE.read_text()),
        "t0": t0,
        "diagnostic_order": _diagnostic_order(t0["decision"]),
        "subruns": [],
    }
    hyp = {
        "H1": "DISFAVORED",
        "H2": "OPEN",
        "H3": "OPEN",
        "H4": "FAVORED_AS_INVESTIGATION_BRANCH" if t0["decision"] == "T0-B" else "OPEN",
        "H5": "DISFAVORED",
        "H6": "DISFAVORED",
    }
    summary: dict[str, Any] = {
        "issue": ISSUE,
        "evr": EVR,
        "selected_branch": "B2",
        "terminal_reason": "EVR3_STARTED_FROM_PRESERVED_B2",
        "hypotheses": hyp,
        "scientific_acceptance_eligible": False,
        "t0": t0,
        "diagnostic_order": _diagnostic_order(t0["decision"]),
        "d1_reference": asdict(reference),
        "d2a": None,
        "d2b": None,
        "d2c": None,
    }

    # D2A: only residual-vs-Jacobian autoscaling policy changes.
    p = _overlay(case, "d2a_residual_scaling", build_overlay(canonical, residual_scaling=True))
    check, runtime = _check_run(qpx, case, p, logs, "d2a_residual_scaling", args.timeout)
    _subrun(manifest, "D2A", p, ["resid_vs_jac_scaling_param=1"], check, runtime)
    if runtime is None:
        hyp["H6"] = "FAVORED"
        summary["terminal_reason"] = "D2A_CHECK_INPUT_FAIL"
        return _finish(root, manifest, summary, 2)
    a2 = _with_electron_fallback(Path(runtime.log).read_text())
    favored = scaling_discriminator(reference, a2)
    summary["d2a"] = {**asdict(a2), "h2_scaling_favored": favored}
    if favored:
        hyp["H2"] = "FAVORED"
        summary["terminal_reason"] = "RESIDUAL_SCALING_COLLAPSED_ELECTRON_DOMINANCE_AND_IMPROVED_TRAJECTORY"
        return _finish(root, manifest, summary, 0)
    hyp["H2"] = "DISFAVORED"

    # T0-B has priority over the expensive Jacobian branch. This preserves the
    # final EVR for the strongest qpx-free discriminator instead of allowing a
    # Jacobian cost guard to terminate the package first.
    candidate_dt = t0.get("candidate_temporal_dt_s")
    if t0["decision"] == "T0-B" and candidate_dt is not None:
        candidate_dt = float(candidate_dt)
        p = _overlay(case, "d2c_t0_informed_dt", build_overlay(canonical, dt=candidate_dt))
        axis = [
            f"dt={candidate_dt:.17g}",
            f"end_time={candidate_dt:.17g}",
            "source=T0_local_electron_diffusion_time/10",
        ]
        check, runtime = _check_run(qpx, case, p, logs, "d2c_t0_informed_dt", args.timeout)
        _subrun(manifest, "D2C", p, axis, check, runtime)
        if runtime is None:
            summary["d2c"] = {"status": "CHECK_INPUT_FAIL", "candidate_dt_s": candidate_dt}
            hyp["H6"] = "FAVORED"
            summary["terminal_reason"] = "D2C_CHECK_INPUT_FAIL"
            return _finish(root, manifest, summary, 2)
        a3 = _with_electron_fallback(Path(runtime.log).read_text())
        temporal_favored = trajectory_improved(reference, a3)
        summary["d2c"] = {
            **asdict(a3),
            "candidate_dt_s": candidate_dt,
            "candidate_source": "T0_local_electron_diffusion_time/10",
            "h4_temporal_favored": temporal_favored,
        }
        if temporal_favored:
            hyp["H4"] = "FAVORED"
            summary["terminal_reason"] = "T0_INFORMED_DT_BREAKS_CYCLE_OR_GIVES_CLEAR_DESCENT"
            return _finish(root, manifest, summary, 0)

        hyp["H4"] = "DISFAVORED"
        completed, rc = _run_jacobian_branch(
            qpx=qpx,
            case=case,
            canonical=canonical,
            logs=logs,
            manifest=manifest,
            summary=summary,
            hyp=hyp,
            max_jacobian_dofs=args.max_jacobian_dofs,
            timeout=args.timeout,
        )
        if completed:
            return _finish(root, manifest, summary, rc if rc is not None else 1)
        if summary["d2b"] and summary["d2b"].get("cost_guard"):
            summary["terminal_reason"] = "SAME_ELECTRON_BLOCKER_AT_T0_INFORMED_DT; JACOBIAN_CHECK_SKIPPED_COST_GUARD"
        else:
            summary["terminal_reason"] = "SAME_ELECTRON_BLOCKER_AT_T0_INFORMED_DT; JACOBIAN_ACCEPTABLE"
        return _finish(root, manifest, summary, 1)

    # T0-A/C do not justify a temporal discriminator. Preserve the previous
    # bounded Jacobian-first route for those cases.
    completed, rc = _run_jacobian_branch(
        qpx=qpx,
        case=case,
        canonical=canonical,
        logs=logs,
        manifest=manifest,
        summary=summary,
        hyp=hyp,
        max_jacobian_dofs=args.max_jacobian_dofs,
        timeout=args.timeout,
    )
    if completed:
        return _finish(root, manifest, summary, rc if rc is not None else 1)
    if summary["d2b"] and summary["d2b"].get("cost_guard"):
        hyp["H4"] = "DISFAVORED" if t0["decision"] == "T0-A" else "HOLD"
        summary["terminal_reason"] = "SCALING_NOT_CAUSAL; JACOBIAN_CHECK_SKIPPED_COST_GUARD"
        return _finish(root, manifest, summary, 1)

    hyp["H4"] = "DISFAVORED" if t0["decision"] == "T0-A" else "HOLD"
    summary["terminal_reason"] = (
        "JACOBIAN_ACCEPTABLE; T0_TEMPORAL_DISPARITY_WEAKENED"
        if t0["decision"] == "T0-A"
        else "JACOBIAN_ACCEPTABLE; T0_TEMPORAL_CONCLUSION_HOLD"
    )
    return _finish(root, manifest, summary, 1)


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
        return run(args)
    except (Evr3Error, DiagnosticError, OSError, ValueError, KeyError) as exc:
        print(f"ISSUE92_EVR3_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())