#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.Issue253_g1_gummel_dt_release import analyze, prepare

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_extreme08"
RESULTS = ROOT / "results_extreme08"
BUILD_BASE_REF = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"

FINAL_TAU = 1000.0
CASES = (
    {"name": "relaxed_chi10", "chi": 10.0, "steps": 100, "fp_max": 120},
    {"name": "relaxed_chi100", "chi": 100.0, "steps": 10, "fp_max": 1000},
    {"name": "relaxed_chi1000", "chi": 1000.0, "steps": 1, "fp_max": 8000},
)
CASE_NAMES = tuple(str(x["name"]) for x in CASES)


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _docker(script: str) -> None:
    _run(["docker", "pull", BUILD_BASE_REF])
    _run([
        "docker", "run", "--rm", "--entrypoint", "/bin/bash", "--user", "0:0",
        "--workdir", "/workspace", "-v", f"{REPO}:/workspace", BUILD_BASE_REF,
        "-lc", script,
    ])


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def _picard_residuals(text: str) -> list[float]:
    clean = _strip_ansi(text)
    return [
        float(value)
        for value in re.findall(r"\bPicard\s+\|R\|\s*=\s*([0-9.eE+\-]+)", clean)
    ]


def _convergence_reasons(text: str) -> list[str]:
    clean = _strip_ansi(text)
    return re.findall(r"Fixed point convergence reason:\s*([A-Z0-9_]+)", clean)


def _params(spec: dict[str, object]) -> dict[str, object]:
    tau = prepare.tau_epsilon()
    chi = float(spec["chi"])
    dt = chi * tau
    end_time = FINAL_TAU * tau
    steps = int(spec["steps"])
    if not math.isclose(dt * steps, end_time, rel_tol=1e-14, abs_tol=1e-30):
        raise RuntimeError(f"{spec['name']}: dt*steps does not equal common final time")
    return {
        "name": str(spec["name"]),
        "chi": chi,
        "tau_epsilon_s": tau,
        "dt_s": dt,
        "end_time_s": end_time,
        "end_time_tau": FINAL_TAU,
        "steps": steps,
        "fp_min": 2,
        "fp_max": int(spec["fp_max"]),
        "relaxation_factor": 1.0 / (1.0 + chi),
        "log_ce0": math.log(prepare.NE0 / prepare.NA),
        "w_O2p0": prepare.NE0 * prepare.M_O2P / (prepare.RHO * prepare.NA),
        "ne0_m3": prepare.NE0,
    }


def _relax(text: str, omega: float) -> str:
    needle = """    input_files = poisson_sub.i
    execute_on = TIMESTEP_END
"""
    replacement = f"""    input_files = poisson_sub.i
    execute_on = TIMESTEP_END
    relaxation_factor = {omega:.17g}
    transformed_variables = 'potential_plasma'
    keep_solution_during_restore = true
    update_old_solution_when_keeping_solution_during_restore = false
"""
    if text.count(needle) != 1:
        raise RuntimeError("Poisson MultiApp insertion point changed")
    return text.replace(needle, replacement, 1)


def _stepwise_outputs(text: str) -> str:
    fp_old = """  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
"""
    fp_new = """  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
  [cumulative_fixed_point_iterations]
    type = CumulativeValuePostprocessor
    postprocessor = fixed_point_iterations
    execute_on = 'TIMESTEP_END'
  []
"""
    if text.count(fp_old) != 1:
        raise RuntimeError("fixed-point postprocessor block changed")
    text = text.replace(fp_old, fp_new, 1)
    old = """[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""
    new = """[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'TIMESTEP_END'
    new_row_tolerance = 1.0e-30
  []
[]
"""
    if text.count(old) != 1:
        raise RuntimeError("parent Outputs block changed")
    return text.replace(old, new, 1)


def _silence_poisson(text: str) -> str:
    old = """[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL FINAL'
[]
"""
    new = """[Outputs]
  console = false
[]
"""
    if text.count(old) != 1:
        raise RuntimeError("Poisson Outputs block changed")
    return text.replace(old, new, 1)


def build(clean: bool = True) -> list[dict[str, object]]:
    electron_template = (ROOT / "electron_template.i").read_text(encoding="utf-8")
    poisson_template = (ROOT / "poisson_template.i").read_text(encoding="utf-8")
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    built: list[dict[str, object]] = []
    for spec in CASES:
        p = _params(spec)
        case_dir = GENERATED / str(p["name"])
        case_dir.mkdir(parents=True, exist_ok=True)
        common = {
            "LOG_CE": f"{p['log_ce0']:.17g}",
            "W_O2P": f"{p['w_O2p0']:.17g}",
            "NE0": f"{p['ne0_m3']:.17g}",
        }
        electron = prepare._render(
            electron_template,
            {
                **common,
                "CASE_NAME": str(p["name"]),
                "DT": f"{p['dt_s']:.17g}",
                "END_TIME": f"{p['end_time_s']:.17g}",
                "STEPS": str(p["steps"]),
                "TIMESTEP_TOL": f"{max(float(p['dt_s']) * 1.0e-8, 1.0e-30):.17g}",
                "FP_MIN": "2",
                "FP_MAX": str(p["fp_max"]),
            },
        )
        electron = _stepwise_outputs(_relax(electron, float(p["relaxation_factor"])))
        poisson = prepare._render(
            poisson_template,
            {"LOG_CE": common["LOG_CE"], "W_O2P": common["W_O2P"]},
        )
        poisson = _silence_poisson(poisson)
        (case_dir / "input.i").write_text(electron, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        (case_dir / "case.json").write_text(
            json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        built.append(p)

    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 253,
                "sequence": 8,
                "objective": "equal-time chi=10/100/1000 relaxed Gummel comparison",
                "total_time_tau_epsilon": FINAL_TAU,
                "equal_final_time": True,
                "relaxation_formula": "omega=1/(1+chi)",
                "cases": built,
                "scientific_scope": (
                    "compare stable convergence, coupling cost, and final-state agreement "
                    "at T=1000 tau_epsilon; chi=10 is the anchor, not an independent truth reference"
                ),
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    cases = build()
    expected = {
        "relaxed_chi10": (10.0, 100, 120),
        "relaxed_chi100": (100.0, 10, 1000),
        "relaxed_chi1000": (1000.0, 1, 8000),
    }
    by = {str(c["name"]): c for c in cases}
    for name, (chi, steps, fp_max) in expected.items():
        p = by[name]
        assert p["chi"] == chi and p["steps"] == steps and p["fp_max"] == fp_max
        assert math.isclose(float(p["dt_s"]) / float(p["tau_epsilon_s"]), chi, rel_tol=1e-14)
        assert math.isclose(float(p["end_time_s"]) / float(p["tau_epsilon_s"]), FINAL_TAU, rel_tol=1e-14)
        assert math.isclose(float(p["relaxation_factor"]), 1.0 / (1.0 + chi), rel_tol=1e-14)
        text = (GENERATED / name / "input.i").read_text(encoding="utf-8")
        assert "PhysicsFVLogMolarElectronEnergy" not in text
        assert "new_row_tolerance = 1.0e-30" in text
        assert "cumulative_fixed_point_iterations" in text
    return {
        "status": "PASS",
        "tau_epsilon_s": prepare.tau_epsilon(),
        "total_time_tau_epsilon": FINAL_TAU,
        "cases": cases,
    }


def p0() -> None:
    print("ISSUE253_G1_EXTREME08_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{ROOT.relative_to(REPO)}/generated_extreme08/{name}/input.i"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    _docker(script)
    print("ISSUE253_G1_EXTREME08_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    checks = "; ".join(
        f"cd /workspace/{ROOT.relative_to(REPO)}/generated_extreme08/{name} && "
        "/workspace/physics_app/physics-opt --check-input -i input.i "
        f"> /workspace/{ROOT.relative_to(REPO)}/results_extreme08/{name}_p2.log 2>&1"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; export METHOD=opt; "
        f"mkdir -p /workspace/{ROOT.relative_to(REPO)}/results_extreme08; "
        "make -C /workspace/physics_app -j2; test -x /workspace/physics_app/physics-opt; "
        + checks
    )
    _docker(script)
    print("ISSUE253_G1_EXTREME08_P2: PASS")


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _final_profile(case_dir: Path) -> list[tuple[float, float, float]]:
    candidates: list[tuple[int, Path]] = []
    for path in case_dir.glob("input_out_electron_profile_*.csv"):
        match = re.search(r"_([0-9]+)\.csv$", path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        raise RuntimeError(f"{case_dir.name}: no final profile")
    _, path = max(candidates)
    points = [
        (
            float(row["x"]),
            float(row["electron_density_out"]),
            float(row["potential_from_poisson"]),
        )
        for row in _rows(path)
    ]
    points.sort()
    return points


def inner_run(case_name: str) -> int:
    if case_name not in CASE_NAMES:
        raise SystemExit(f"unknown case: {case_name}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED / case_name
    log_path = RESULTS / f"{case_name}_runtime.log"
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-i", "input.i"],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    (RESULTS / f"{case_name}_returncode.txt").write_text(f"{completed.returncode}\n", encoding="utf-8")
    (RESULTS / f"{case_name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n", encoding="utf-8")
    return 0


def analyze_case(case_name: str) -> tuple[dict[str, object], int]:
    p = json.loads((GENERATED / case_name / "case.json").read_text(encoding="utf-8"))
    log_text = (RESULTS / f"{case_name}_runtime.log").read_text(encoding="utf-8", errors="replace")
    rc = int((RESULTS / f"{case_name}_returncode.txt").read_text().strip())
    elapsed = float((RESULTS / f"{case_name}_elapsed_seconds.txt").read_text().strip())
    residuals = _picard_residuals(log_text)
    reasons = _convergence_reasons(log_text)
    rows = _rows(GENERATED / case_name / "input_out.csv")
    final_time = float(rows[-1]["time"]) if rows else None
    total_fp = int(round(float(rows[-1]["cumulative_fixed_point_iterations"]))) if rows else 0
    per_step = [int(round(float(row["fixed_point_iterations"]))) for row in rows]
    full_horizon = (
        rc == 0
        and len(rows) == int(p["steps"])
        and final_time is not None
        and math.isclose(final_time, float(p["end_time_s"]), rel_tol=1e-10, abs_tol=1e-24)
    )
    result: dict[str, object] = {
        "case": case_name,
        "chi": p["chi"],
        "dt_s": p["dt_s"],
        "dt_ns": float(p["dt_s"]) * 1.0e9,
        "physical_steps_requested": p["steps"],
        "physical_steps_completed": len(rows),
        "relaxation_factor": p["relaxation_factor"],
        "fixed_point_max": p["fp_max"],
        "total_fixed_point_iterations": total_fp,
        "mean_fixed_point_iterations_per_step": (
            sum(per_step) / len(per_step) if per_step else None
        ),
        "max_fixed_point_iterations_per_step": max(per_step) if per_step else None,
        "returncode": rc,
        "elapsed_seconds": elapsed,
        "convergence_reasons": reasons,
        "picard_residual_count": len(residuals),
        "picard_residual_first": residuals[0] if residuals else None,
        "picard_residual_last": residuals[-1] if residuals else None,
    }
    if rc != 0:
        if "DIVERGED_MAX_ITS" in log_text:
            result["classification"] = "GUMMEL_DIVERGED_MAX_ITS"
            result["evidence_valid"] = True
            return result, 0
        result["classification"] = "RUNTIME_FAILURE"
        result["evidence_valid"] = False
        return result, 2
    if not full_horizon:
        result["classification"] = "INCOMPLETE_HORIZON"
        result["evidence_valid"] = False
        return result, 2
    result["classification"] = "CASE_CONVERGED"
    result["evidence_valid"] = True
    result["final_profile"] = [
        {"x": x, "electron_density": ne, "potential": phi}
        for x, ne, phi in _final_profile(GENERATED / case_name)
    ]
    return result, 0


def run_case(case_name: str) -> None:
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        f"python3 /workspace/{ROOT.relative_to(REPO)}/extreme08_control.py --inner-run {case_name}"
    )
    _docker(script)
    result, rc = analyze_case(case_name)
    out = RESULTS / f"{case_name}_result.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE253_G1_EXTREME08_CASE:", case_name, result["classification"])
    print(json.dumps(result, indent=2, sort_keys=True))
    if rc:
        raise SystemExit(rc)


def _profile_from_result(item: dict[str, object]) -> list[tuple[float, float, float]]:
    return [
        (float(row["x"]), float(row["electron_density"]), float(row["potential"]))
        for row in item["final_profile"]
    ]


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [name for name in CASE_NAMES if name not in found]
    if missing:
        raise RuntimeError(f"missing extreme08 result(s): {missing}")

    anchor = found["relaxed_chi10"]
    summary: dict[str, object] = {
        "issue": 253,
        "sequence": 8,
        "total_time_tau_epsilon": FINAL_TAU,
        "equal_final_time": True,
        "anchor": anchor,
        "cases": {},
        "scientific_scope": (
            "equal-time agreement against chi=10 anchor; this does not make chi=10 "
            "an independent fine-step truth reference at T=1000 tau_epsilon"
        ),
    }
    if not bool(anchor.get("evidence_valid")) or anchor.get("classification") != "CASE_CONVERGED":
        summary["classification"] = "ANCHOR_NOT_CONVERGED"
        summary["evidence_valid"] = False
        return summary

    anchor_profile = _profile_from_result(anchor)
    all_converged = True
    for name in ("relaxed_chi100", "relaxed_chi1000"):
        item = dict(found[name])
        if item.get("classification") == "CASE_CONVERGED":
            item["profile_error_vs_chi10"] = analyze._profile_metrics(
                anchor_profile, _profile_from_result(item)
            )
            item["fp_solve_ratio_vs_chi10"] = (
                float(item["total_fixed_point_iterations"])
                / max(float(anchor["total_fixed_point_iterations"]), 1.0)
            )
            item["wall_clock_ratio_vs_chi10"] = (
                float(item["elapsed_seconds"])
                / max(float(anchor["elapsed_seconds"]), 1e-30)
            )
        else:
            all_converged = False
        summary["cases"][name] = item

    summary["classification"] = (
        "CHI10_100_1000_ALL_CONVERGED" if all_converged
        else "CHI10_100_1000_CONVERGENCE_LIMIT"
    )
    summary["evidence_valid"] = True
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2"))
    parser.add_argument("--case", choices=CASE_NAMES)
    parser.add_argument("--inner-run", choices=CASE_NAMES)
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.inner_run:
        return inner_run(args.inner_run)
    if args.case:
        run_case(args.case)
        return 0
    if args.aggregate:
        evidence_root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
        if not evidence_root:
            raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
        summary = aggregate(Path(evidence_root))
        out = RESULTS / "extreme08_summary.json"
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("ISSUE253_G1_EXTREME08_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
