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
GENERATED = ROOT / "generated_parallel"
RESULTS = ROOT / "results_parallel"
BUILD_BASE_REF = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)

FINAL_TAU = 20.0
REFERENCE_STEPS = 200
REFERENCE_CHI = 0.1
REFERENCE_FAMILY_EINF = 0.10

CASES = (
    {
        "name": "ref_chi0p1",
        "chi": 0.1,
        "steps": 200,
        "fp_min": 1,
        "fp_max": 1,
        "omega": 1.0,
    },
    {
        "name": "relaxed_chi1",
        "chi": 1.0,
        "steps": 20,
        "fp_min": 2,
        "fp_max": 30,
        "omega": 1.0 / 2.0,
    },
    {
        "name": "relaxed_chi10",
        "chi": 10.0,
        "steps": 2,
        "fp_min": 2,
        "fp_max": 80,
        "omega": 1.0 / 11.0,
    },
)
CASE_NAMES = tuple(str(x["name"]) for x in CASES)


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _docker(script: str) -> None:
    _run(["docker", "pull", BUILD_BASE_REF])
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            "--user",
            "0:0",
            "--workdir",
            "/workspace",
            "-v",
            f"{REPO}:/workspace",
            BUILD_BASE_REF,
            "-lc",
            script,
        ]
    )


def _case_parameters(spec: dict[str, object]) -> dict[str, object]:
    tau = prepare.tau_epsilon()
    chi = float(spec["chi"])
    dt = chi * tau
    end_time = FINAL_TAU * tau
    steps = int(spec["steps"])
    if not math.isclose(dt * steps, end_time, rel_tol=1e-14, abs_tol=1e-30):
        raise RuntimeError(
            f"{spec['name']}: dt*steps={dt * steps:.17g} != end_time={end_time:.17g}"
        )
    return {
        "name": str(spec["name"]),
        "chi": chi,
        "tau_epsilon_s": tau,
        "dt_s": dt,
        "end_time_s": end_time,
        "steps": steps,
        "fp_min": int(spec["fp_min"]),
        "fp_max": int(spec["fp_max"]),
        "relaxation_factor": float(spec["omega"]),
        "log_ce0": math.log(prepare.NE0 / prepare.NA),
        "w_O2p0": prepare.NE0 * prepare.M_O2P / (prepare.RHO * prepare.NA),
        "ne0_m3": prepare.NE0,
    }


def _with_relaxed_poisson_multiapp(text: str, omega: float) -> str:
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
        raise RuntimeError("expected exactly one Poisson MultiApp insertion point")
    return text.replace(needle, replacement, 1)


def _with_stepwise_outputs(text: str) -> str:
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
        raise RuntimeError("fixed-point postprocessor block changed unexpectedly")
    text = text.replace(fp_old, fp_new, 1)

    outputs_old = """[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL TIMESTEP_END'
[]
"""
    outputs_new = """[Outputs]
  csv = true
  exodus = false
  execute_on = 'TIMESTEP_END'
[]
"""
    if text.count(outputs_old) != 1:
        raise RuntimeError("parent Outputs block changed unexpectedly")
    return text.replace(outputs_old, outputs_new, 1)


def _silence_poisson_outputs(text: str) -> str:
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
        raise RuntimeError("Poisson Outputs block changed unexpectedly")
    return text.replace(old, new, 1)


def build(clean: bool = True) -> list[dict[str, object]]:
    electron_template = (ROOT / "electron_template.i").read_text(encoding="utf-8")
    poisson_template = (ROOT / "poisson_template.i").read_text(encoding="utf-8")
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    built: list[dict[str, object]] = []
    for spec in CASES:
        params = _case_parameters(spec)
        case_dir = GENERATED / str(params["name"])
        case_dir.mkdir(parents=True, exist_ok=True)
        common = {
            "LOG_CE": f"{params['log_ce0']:.17g}",
            "W_O2P": f"{params['w_O2p0']:.17g}",
            "NE0": f"{params['ne0_m3']:.17g}",
        }
        electron = prepare._render(
            electron_template,
            {
                **common,
                "CASE_NAME": str(params["name"]),
                "DT": f"{params['dt_s']:.17g}",
                "END_TIME": f"{params['end_time_s']:.17g}",
                "STEPS": str(params["steps"]),
                "TIMESTEP_TOL": f"{max(float(params['dt_s']) * 1.0e-6, 1.0e-30):.17g}",
                "FP_MIN": str(params["fp_min"]),
                "FP_MAX": str(params["fp_max"]),
            },
        )
        if float(params["chi"]) > REFERENCE_CHI:
            electron = _with_relaxed_poisson_multiapp(
                electron, float(params["relaxation_factor"])
            )
        electron = _with_stepwise_outputs(electron)

        poisson = prepare._render(
            poisson_template,
            {"LOG_CE": common["LOG_CE"], "W_O2P": common["W_O2P"]},
        )
        poisson = _silence_poisson_outputs(poisson)

        (case_dir / "input.i").write_text(electron, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        (case_dir / "case.json").write_text(
            json.dumps(params, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        built.append(params)

    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 253,
                "sequence": 7,
                "objective": (
                    "fixed T=20 tau_epsilon step-count convergence: "
                    "chi=0.1/1/10 with 200/20/2 physical steps"
                ),
                "total_time_tau_epsilon": FINAL_TAU,
                "parallel_cases": list(CASE_NAMES),
                "cases": built,
                "scientific_scope": (
                    "final-state convergence versus the 200-step reference plus "
                    "per-physical-step fixed-point convergence for relaxed candidates"
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    built = build()
    by = {str(x["name"]): x for x in built}
    assert by["ref_chi0p1"]["steps"] == 200
    assert by["relaxed_chi1"]["steps"] == 20
    assert by["relaxed_chi10"]["steps"] == 2
    assert math.isclose(by["relaxed_chi1"]["relaxation_factor"], 0.5)
    assert math.isclose(by["relaxed_chi10"]["relaxation_factor"], 1.0 / 11.0)

    expected_end = FINAL_TAU * prepare.tau_epsilon()
    for case in built:
        assert math.isclose(float(case["end_time_s"]), expected_end, rel_tol=1e-14)
        text = (GENERATED / str(case["name"]) / "input.i").read_text(encoding="utf-8")
        assert "cumulative_fixed_point_iterations" in text
        assert "execute_on = 'TIMESTEP_END'" in text
        assert "exodus = false" in text
        assert "PhysicsFVLogMolarElectronEnergy" not in text

    for name in ("relaxed_chi1", "relaxed_chi10"):
        text = (GENERATED / name / "input.i").read_text(encoding="utf-8")
        assert "transformed_variables = 'potential_plasma'" in text
        assert "keep_solution_during_restore = true" in text

    return {
        "status": "PASS",
        "total_time_tau_epsilon": FINAL_TAU,
        "total_time_s": expected_end,
        "cases": built,
    }


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _convergence_reasons(log_text: str) -> list[str]:
    clean = _strip_ansi(log_text)
    return re.findall(r"Fixed point convergence reason:\s*([A-Z0-9_]+)", clean)


def _final_profile(case_dir: Path) -> list[tuple[float, float, float]]:
    candidates = sorted(case_dir.glob("input_out_electron_profile*.csv"))
    if not candidates:
        raise RuntimeError(f"{case_dir.name}: missing electron profile")
    rows = _rows(candidates[-1])
    points = [
        (
            float(row["x"]),
            float(row["electron_density_out"]),
            float(row["potential_from_poisson"]),
        )
        for row in rows
    ]
    points.sort()
    if len(points) < 3:
        raise RuntimeError(f"{case_dir.name}: insufficient final profile points")
    return points


def _step_history(case_dir: Path) -> list[dict[str, object]]:
    rows = _rows(case_dir / "input_out.csv")
    history: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        history.append(
            {
                "step_index": index,
                "time_s": float(row["time"]),
                "fixed_point_iterations": int(round(float(row.get("fixed_point_iterations", "0") or 0))),
                "cumulative_fixed_point_iterations": int(
                    round(float(row.get("cumulative_fixed_point_iterations", "0") or 0))
                ),
                "electron_inventory": float(row["electron_inventory"]),
                "n_e_min": float(row["n_e_min"]),
                "n_e_max": float(row["n_e_max"]),
                "phi_min": float(row["phi_min"]),
                "phi_max": float(row["phi_max"]),
            }
        )
    return history


def inner_run(case_name: str) -> int:
    if case_name not in CASE_NAMES:
        raise SystemExit(f"unknown case: {case_name}")
    case_dir = GENERATED / case_name
    RESULTS.mkdir(parents=True, exist_ok=True)
    log_path = RESULTS / f"{case_name}_runtime.log"
    rc_path = RESULTS / f"{case_name}_returncode.txt"
    elapsed_path = RESULTS / f"{case_name}_elapsed_seconds.txt"
    start = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-i", "input.i"],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - start
    rc_path.write_text(f"{completed.returncode}\n", encoding="utf-8")
    elapsed_path.write_text(f"{elapsed:.9f}\n", encoding="utf-8")
    return 0


def _case_result(case_name: str) -> tuple[dict[str, object], int]:
    params = json.loads((GENERATED / case_name / "case.json").read_text(encoding="utf-8"))
    rc = int((RESULTS / f"{case_name}_returncode.txt").read_text(encoding="utf-8").strip())
    elapsed = float(
        (RESULTS / f"{case_name}_elapsed_seconds.txt").read_text(encoding="utf-8").strip()
    )
    log_text = (RESULTS / f"{case_name}_runtime.log").read_text(
        encoding="utf-8", errors="replace"
    )
    out: dict[str, object] = {
        "case": case_name,
        "chi": params["chi"],
        "physical_steps_requested": params["steps"],
        "dt_s": params["dt_s"],
        "end_time_s": params["end_time_s"],
        "relaxation_factor": params["relaxation_factor"],
        "returncode": rc,
        "elapsed_seconds": elapsed,
    }
    if rc != 0:
        out["classification"] = (
            "GUMMEL_DIVERGED"
            if "DIVERGED_MAX_ITS" in log_text
            else "RUNTIME_FAILURE"
        )
        out["evidence_valid"] = "DIVERGED_MAX_ITS" in log_text
        return out, 0 if out["evidence_valid"] else 2

    history = _step_history(GENERATED / case_name)
    profile = _final_profile(GENERATED / case_name)
    reasons = _convergence_reasons(log_text)
    out["step_history"] = history
    out["convergence_reasons"] = reasons
    out["final_profile"] = [
        {"x": x, "electron_density": ne, "potential": phi}
        for x, ne, phi in profile
    ]
    out["physical_steps_completed"] = len(history)
    out["total_fixed_point_iterations"] = (
        history[-1]["cumulative_fixed_point_iterations"] if history else 0
    )
    out["max_fixed_point_iterations_per_step"] = max(
        (int(x["fixed_point_iterations"]) for x in history), default=0
    )
    out["mean_fixed_point_iterations_per_step"] = (
        sum(int(x["fixed_point_iterations"]) for x in history) / len(history)
        if history
        else 0.0
    )
    full_horizon = len(history) == int(params["steps"]) and math.isclose(
        float(history[-1]["time_s"]) if history else 0.0,
        float(params["end_time_s"]),
        rel_tol=1e-10,
        abs_tol=1e-30,
    )
    out["classification"] = "CASE_CONVERGED" if full_horizon else "INCOMPLETE_HORIZON"
    out["evidence_valid"] = full_horizon
    return out, 0 if full_horizon else 2


def run_case(case_name: str) -> None:
    exe = REPO / "physics_app" / "physics-opt"
    if not exe.exists():
        raise SystemExit("physics-opt missing: parallel prepare/build job must complete first")
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "export PYTHONPATH=/workspace; "
        f"python3 /workspace/experiments/Issue253_g1_gummel_dt_release/"
        f"parallel_control.py --inner-run {case_name}"
    )
    _docker(script)
    result, rc = _case_result(case_name)
    out = RESULTS / f"{case_name}_result.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE253_G1_PARALLEL_CASE:", case_name, result["classification"])
    print(json.dumps(result, indent=2, sort_keys=True))
    if rc:
        raise SystemExit(rc)


def _profile_from_result(result: dict[str, object]) -> list[tuple[float, float, float]]:
    return [
        (float(row["x"]), float(row["electron_density"]), float(row["potential"]))
        for row in result["final_profile"]
    ]


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        name = str(data.get("case", ""))
        if name in CASE_NAMES:
            found[name] = data
    missing = [name for name in CASE_NAMES if name not in found]
    if missing:
        raise RuntimeError(f"missing case result(s): {missing}")

    ref = found["ref_chi0p1"]
    if not bool(ref.get("evidence_valid")):
        raise RuntimeError("reference is not valid")
    ref_profile = _profile_from_result(ref)
    summary: dict[str, object] = {
        "issue": 253,
        "sequence": 7,
        "total_time_tau_epsilon": FINAL_TAU,
        "reference": ref,
        "candidates": {},
        "comparison": "200/20/2 physical-step convergence at fixed T=20 tau_epsilon",
    }

    for name in ("relaxed_chi1", "relaxed_chi10"):
        item = dict(found[name])
        if bool(item.get("evidence_valid")):
            metrics = analyze._profile_metrics(ref_profile, _profile_from_result(item))
            item["profile_error_vs_200_step_reference"] = metrics
            item["coupling_solve_reduction_vs_reference"] = (
                REFERENCE_STEPS / max(int(item["total_fixed_point_iterations"]), 1)
            )
            item["wall_clock_speedup_vs_reference"] = (
                float(ref["elapsed_seconds"]) / max(float(item["elapsed_seconds"]), 1e-30)
            )
            item["within_reference_family"] = all(
                metrics[key] <= REFERENCE_FAMILY_EINF
                for key in analyze.PRIMARY_ERROR_METRICS
            )
        summary["candidates"][name] = item

    valid_candidates = [
        x for x in summary["candidates"].values() if bool(x.get("evidence_valid"))
    ]
    if len(valid_candidates) != 2:
        summary["classification"] = "PARTIAL_OR_INVALID_STEP_CONVERGENCE_EVIDENCE"
        summary["evidence_valid"] = False
    elif all(bool(x.get("within_reference_family")) for x in valid_candidates):
        summary["classification"] = "STEP_COUNT_CONVERGENCE_SUPPORTED"
        summary["evidence_valid"] = True
    else:
        summary["classification"] = "STEP_COUNT_CONVERGENCE_NOT_YET_SUPPORTED"
        summary["evidence_valid"] = True
    return summary


def p0() -> None:
    print("ISSUE253_G1_PARALLEL_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/experiments/Issue253_g1_gummel_dt_release/generated_parallel/{name}/input.i"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; "
        + commands
    )
    _docker(script)
    print("ISSUE253_G1_PARALLEL_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    checks = "; ".join(
        "cd /workspace/experiments/Issue253_g1_gummel_dt_release/"
        f"generated_parallel/{name} && "
        "/workspace/physics_app/physics-opt --check-input -i input.i "
        f"> /workspace/experiments/Issue253_g1_gummel_dt_release/results_parallel/{name}_p2.log 2>&1"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "mkdir -p /workspace/experiments/Issue253_g1_gummel_dt_release/results_parallel; "
        "make -C /workspace/physics_app -j2; "
        "test -x /workspace/physics_app/physics-opt; "
        + checks
    )
    _docker(script)
    print("ISSUE253_G1_PARALLEL_P2: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2"))
    parser.add_argument("--case", choices=CASE_NAMES)
    parser.add_argument("--inner-run", choices=CASE_NAMES)
    parser.add_argument("--aggregate-root")
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)

    if args.inner_run:
        return inner_run(args.inner_run)
    if args.case:
        run_case(args.case)
        return 0
    if args.aggregate or args.aggregate_root:
        root_value = args.aggregate_root or os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
        if not root_value:
            raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required for --aggregate")
        summary = aggregate(Path(root_value))
        out = RESULTS / "parallel_summary.json"
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("ISSUE253_G1_PARALLEL_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one of --phase, --case, --inner-run, --aggregate, --aggregate-root is required")


if __name__ == "__main__":
    raise SystemExit(main())
