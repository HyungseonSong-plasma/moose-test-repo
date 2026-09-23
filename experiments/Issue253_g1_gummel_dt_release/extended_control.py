#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
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
GENERATED = ROOT / "generated_extreme"
RESULTS = ROOT / "results_extreme"
BUILD_BASE_REF = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)

FINAL_TAU = 20000.0
REFERENCE_CHI = 0.1
REFERENCE_STEPS = 200000
TARGET_TOTAL_COUPLING_BUDGET = 140000
REFERENCE_FAMILY_EINF = 0.10

CASES = (
    {
        "name": "ref_chi0p1",
        "chi": 0.1,
        "steps": 200000,
        "fp_min": 1,
        "fp_max": 1,
        "omega": 1.0,
    },
    {
        "name": "relaxed_chi1000",
        "chi": 1000.0,
        "steps": 20,
        "fp_min": 2,
        "fp_max": 7000,
        "omega": 1.0 / 1001.0,
    },
    {
        "name": "relaxed_chi10000",
        "chi": 10000.0,
        "steps": 2,
        "fp_min": 2,
        "fp_max": 70000,
        "omega": 1.0 / 10001.0,
    },
)


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
    log_ce = math.log(prepare.NE0 / prepare.NA)
    w_o2p = prepare.NE0 * prepare.M_O2P / (prepare.RHO * prepare.NA)
    return {
        "name": str(spec["name"]),
        "chi": chi,
        "tau_epsilon_s": tau,
        "dt_s": dt,
        "end_time_s": end_time,
        "steps": steps,
        "fp_min": int(spec["fp_min"]),
        "fp_max": int(spec["fp_max"]),
        "log_ce0": log_ce,
        "w_O2p0": w_o2p,
        "ne0_m3": prepare.NE0,
        "relaxation_factor": float(spec["omega"]),
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


def _make_output_light(text: str, steps: int) -> str:
    vpp_old = """  [electron_profile]
    type = ElementValueSampler
    variable = 'log_e electron_density_out potential_from_poisson'
    sort_by = id
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
    vpp_new = """  [electron_profile]
    type = ElementValueSampler
    variable = 'log_e electron_density_out potential_from_poisson'
    sort_by = id
    execute_on = 'TIMESTEP_END'
  []
"""
    if text.count(vpp_old) != 1:
        raise RuntimeError("electron profile output block changed unexpectedly")
    text = text.replace(vpp_old, vpp_new, 1)

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
    outputs_new = f"""[Outputs]
  console = false
  [final_csv]
    type = CSV
    file_base = input_out
    execute_on = 'TIMESTEP_END'
    time_step_interval = {steps}
  []
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
        electron = _make_output_light(electron, int(params["steps"]))

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
                "sequence": 5,
                "objective": (
                    "fixed-total-time extreme-Gummel comparison: "
                    "chi=0.1 reference vs relaxed chi=1000 and chi=10000"
                ),
                "total_time_tau_epsilon": FINAL_TAU,
                "total_time_definition": "2 * dt(chi=10000)",
                "reference_steps": REFERENCE_STEPS,
                "max_total_coupling_budget_per_candidate": TARGET_TOTAL_COUPLING_BUDGET,
                "profile_output": "TIMESTEP_END sampled only on the final step",
                "exodus_output": False,
                "poisson_subapp_csv_output": False,
                "scientific_scope": (
                    "final-time accuracy and computational efficiency; "
                    "not transient-trajectory accuracy"
                ),
                "cases": built,
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
    by_name = {str(x["name"]): x for x in built}
    ref = by_name["ref_chi0p1"]
    c1000 = by_name["relaxed_chi1000"]
    c10000 = by_name["relaxed_chi10000"]

    assert ref["chi"] == 0.1 and ref["steps"] == 200000 and ref["fp_max"] == 1
    assert c1000["chi"] == 1000.0 and c1000["steps"] == 20 and c1000["fp_max"] == 7000
    assert c10000["chi"] == 10000.0 and c10000["steps"] == 2 and c10000["fp_max"] == 70000
    assert math.isclose(float(c1000["relaxation_factor"]), 1.0 / 1001.0, rel_tol=0.0, abs_tol=1e-16)
    assert math.isclose(float(c10000["relaxation_factor"]), 1.0 / 10001.0, rel_tol=0.0, abs_tol=1e-16)
    assert c1000["steps"] * c1000["fp_max"] == TARGET_TOTAL_COUPLING_BUDGET
    assert c10000["steps"] * c10000["fp_max"] == TARGET_TOTAL_COUPLING_BUDGET

    expected_end = FINAL_TAU * prepare.tau_epsilon()
    for case in (ref, c1000, c10000):
        assert math.isclose(float(case["end_time_s"]), expected_end, rel_tol=1e-14)
        text = (GENERATED / str(case["name"]) / "input.i").read_text(encoding="utf-8")
        assert "execute_on = 'TIMESTEP_END'" in text
        assert f"time_step_interval = {case['steps']}" in text
        assert "cumulative_fixed_point_iterations" in text
        assert "exodus = true" not in text
        assert "PhysicsFVLogMolarElectronEnergy" not in text
        poisson_text = (GENERATED / str(case["name"]) / "poisson_sub.i").read_text(
            encoding="utf-8"
        )
        assert "[Outputs]\n  console = false\n[]" in poisson_text
        assert "csv = true" not in poisson_text
        assert "exodus = true" not in poisson_text

    for case in (c1000, c10000):
        text = (GENERATED / str(case["name"]) / "input.i").read_text(encoding="utf-8")
        assert "transformed_variables = 'potential_plasma'" in text
        assert "keep_solution_during_restore = true" in text
        assert "update_old_solution_when_keeping_solution_during_restore = false" in text

    ref_text = (GENERATED / "ref_chi0p1" / "input.i").read_text(encoding="utf-8")
    assert "transformed_variables = 'potential_plasma'" not in ref_text

    return {
        "status": "PASS",
        "tau_epsilon_s": prepare.tau_epsilon(),
        "total_time_tau_epsilon": FINAL_TAU,
        "total_time_s": expected_end,
        "cases": built,
        "scientific_scope": (
            "final-time state and computational efficiency only; "
            "large-dt transient trajectory is not claimed accurate"
        ),
    }


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _final_profile(case_dir: Path) -> list[tuple[float, float, float]]:
    candidates = sorted(case_dir.glob("input_out_electron_profile*.csv"))
    if not candidates:
        raise RuntimeError(f"{case_dir.name}: missing FINAL electron profile")
    path = candidates[-1]
    points: list[tuple[float, float, float]] = []
    for row in _rows(path):
        points.append(
            (
                float(row["x"]),
                float(row["electron_density_out"]),
                float(row["potential_from_poisson"]),
            )
        )
    points.sort()
    if len(points) < 3:
        raise RuntimeError(f"{case_dir.name}: insufficient final profile points")
    return points


def _fixed_point_stats(case_dir: Path) -> dict[str, object]:
    rows = _rows(case_dir / "input_out.csv")
    if not rows:
        raise RuntimeError(f"{case_dir.name}: missing final scalar CSV row")
    row = rows[-1]
    total = float(row.get("cumulative_fixed_point_iterations", "0") or 0.0)
    last = float(row.get("fixed_point_iterations", "0") or 0.0)
    return {
        "total_fixed_point_iterations": int(round(total)),
        "last_step_fixed_point_iterations": last,
    }


def _read_float(path: Path) -> float:
    return float(path.read_text(encoding="utf-8").strip())


def _read_int(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").strip())


def _runtime_status(name: str) -> dict[str, object]:
    return {
        "returncode": _read_int(RESULTS / f"{name}_returncode.txt"),
        "elapsed_seconds": _read_float(RESULTS / f"{name}_elapsed_seconds.txt"),
    }


def inner_run(case_name: str) -> int:
    case_dir = GENERATED / case_name
    log_path = RESULTS / f"{case_name}_runtime.log"
    rc_path = RESULTS / f"{case_name}_returncode.txt"
    elapsed_path = RESULTS / f"{case_name}_elapsed_seconds.txt"
    RESULTS.mkdir(parents=True, exist_ok=True)
    command = [
        str(REPO / "physics_app" / "physics-opt"),
        "-i",
        "input.i",
    ]
    start = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            command,
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - start
    rc_path.write_text(f"{completed.returncode}\n", encoding="utf-8")
    elapsed_path.write_text(f"{elapsed:.9f}\n", encoding="utf-8")
    print(
        json.dumps(
            {"case": case_name, "returncode": completed.returncode, "elapsed_seconds": elapsed}
        )
    )
    return 0


def _classify_candidate(
    *,
    name: str,
    ref_profile: list[tuple[float, float, float]],
    ref_elapsed: float,
) -> dict[str, object]:
    status = _runtime_status(name)
    out: dict[str, object] = {"runtime": status}
    log = (RESULTS / f"{name}_runtime.log").read_text(errors="replace")
    if int(status["returncode"]) != 0:
        out["classification"] = (
            "RELAXED_GUMMEL_DIVERGED"
            if "DIVERGED_MAX_ITS" in log
            else "UNCLASSIFIED_RUNTIME_FAILURE"
        )
        out["evidence_valid"] = "DIVERGED_MAX_ITS" in log
        return out

    case_dir = GENERATED / name
    profile = _final_profile(case_dir)
    metrics = analyze._profile_metrics(ref_profile, profile)
    fp = _fixed_point_stats(case_dir)
    out["profile_error_vs_reference"] = metrics
    out["fixed_point"] = fp
    out["runtime"]["speedup_vs_reference"] = ref_elapsed / max(float(status["elapsed_seconds"]), 1e-30)
    out["coupling_solve_reduction_vs_reference"] = (
        REFERENCE_STEPS / max(int(fp["total_fixed_point_iterations"]), 1)
    )

    if all(metrics[key] <= REFERENCE_FAMILY_EINF for key in analyze.PRIMARY_ERROR_METRICS):
        out["classification"] = "FINAL_STATE_REFERENCE_RECOVERED"
    else:
        out["classification"] = "FINAL_STATE_OUTSIDE_REFERENCE_FAMILY"
    out["evidence_valid"] = True
    return out


def analyze_result() -> tuple[dict[str, object], int]:
    ref_status = _runtime_status("ref_chi0p1")
    if int(ref_status["returncode"]) != 0:
        return {
            "issue": 253,
            "sequence": 5,
            "classification": "REFERENCE_RUNTIME_FAILURE",
            "evidence_valid": False,
            "reference_runtime": ref_status,
        }, 2

    ref_dir = GENERATED / "ref_chi0p1"
    ref_profile = _final_profile(ref_dir)
    ref_fp = _fixed_point_stats(ref_dir)
    ref_elapsed = float(ref_status["elapsed_seconds"])

    summary: dict[str, object] = {
        "issue": 253,
        "sequence": 5,
        "comparison": "fixed T=20000 tau: chi=0.1 reference vs relaxed chi=1000 and chi=10000",
        "total_time_tau_epsilon": FINAL_TAU,
        "total_time_s": FINAL_TAU * prepare.tau_epsilon(),
        "reference_family_threshold_einf": REFERENCE_FAMILY_EINF,
        "scientific_scope": (
            "final-time state and computational efficiency; "
            "no claim of large-dt transient-trajectory accuracy"
        ),
        "reference": {
            "chi": 0.1,
            "physical_steps": REFERENCE_STEPS,
            "runtime": ref_status,
            "fixed_point": ref_fp,
        },
        "candidates": {},
        "evidence_valid": True,
    }

    for name in ("relaxed_chi1000", "relaxed_chi10000"):
        summary["candidates"][name] = _classify_candidate(
            name=name, ref_profile=ref_profile, ref_elapsed=ref_elapsed
        )

    classes = [
        summary["candidates"][name]["classification"]
        for name in ("relaxed_chi1000", "relaxed_chi10000")
    ]
    if all(c == "FINAL_STATE_REFERENCE_RECOVERED" for c in classes):
        summary["classification"] = "CHI1000_AND_CHI10000_FINAL_STATE_SUPPORTED"
    elif any(c == "FINAL_STATE_REFERENCE_RECOVERED" for c in classes):
        summary["classification"] = "PARTIAL_FINAL_STATE_SUPPORT"
    else:
        summary["classification"] = "NO_FINAL_STATE_SUPPORT_AT_CHI1000_OR_CHI10000"

    invalid = [
        item
        for item in summary["candidates"].values()
        if not bool(item.get("evidence_valid", False))
    ]
    if invalid:
        summary["evidence_valid"] = False
        return summary, 2
    return summary, 0


def p0() -> None:
    summary = static_contract()
    print("ISSUE253_G1_EXTREME_P0: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))


def p1() -> None:
    build()
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; "
        + "; ".join(
            (
                "python3 /workspace/bin/physics.py preflight "
                "/workspace/experiments/Issue253_g1_gummel_dt_release/"
                f"generated_extreme/{name}/input.i"
            )
            for name in ("ref_chi0p1", "relaxed_chi1000", "relaxed_chi10000")
        )
    )
    _docker(script)
    print("ISSUE253_G1_EXTREME_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    checks = "; ".join(
        (
            "cd /workspace/experiments/Issue253_g1_gummel_dt_release/"
            f"generated_extreme/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i input.i "
            "> /workspace/experiments/Issue253_g1_gummel_dt_release/"
            f"results_extreme/{name}_p2.log 2>&1"
        )
        for name in ("ref_chi0p1", "relaxed_chi1000", "relaxed_chi10000")
    )
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "mkdir -p /workspace/experiments/Issue253_g1_gummel_dt_release/results_extreme; "
        "make -C /workspace/physics_app -j2; "
        "test -x /workspace/physics_app/physics-opt; "
        + checks
    )
    _docker(script)
    print("ISSUE253_G1_EXTREME_P2: PASS")


def p3() -> None:
    exe = REPO / "physics_app" / "physics-opt"
    if not exe.exists():
        raise SystemExit("physics-opt missing: P2 must complete before P3")
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "export PYTHONPATH=/workspace; "
        + "; ".join(
            (
                "python3 /workspace/experiments/Issue253_g1_gummel_dt_release/"
                f"extended_control.py --inner-run {name}"
            )
            for name in ("ref_chi0p1", "relaxed_chi1000", "relaxed_chi10000")
        )
    )
    _docker(script)
    summary, rc = analyze_result()
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "extreme_analysis.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE253_G1_EXTREME_CLASSIFICATION:", summary["classification"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    if rc != 0:
        raise SystemExit(rc)
    print("ISSUE253_G1_EXTREME_P3: EVIDENCE_READY")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2", "p3"))
    parser.add_argument("--inner-run", choices=("ref_chi0p1", "relaxed_chi1000", "relaxed_chi10000"))
    args = parser.parse_args()
    if args.inner_run:
        return inner_run(args.inner_run)
    if not args.phase:
        parser.error("one of --phase or --inner-run is required")
    RESULTS.mkdir(parents=True, exist_ok=True)
    {"p0": p0, "p1": p1, "p2": p2, "p3": p3}[args.phase]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
