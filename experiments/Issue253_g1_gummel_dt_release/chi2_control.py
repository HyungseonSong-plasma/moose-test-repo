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

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.Issue253_g1_gummel_dt_release import prepare

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_chi2"
RESULTS = ROOT / "results_chi2"
BUILD_BASE_REF = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)
SPEC = {"name": "gummel_chi2", "chi": 2.0, "steps": 10, "fp_min": 2, "fp_max": 30}


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


def build_case(clean: bool = True) -> dict[str, object]:
    params = prepare.case_parameters(SPEC)
    electron_template = (ROOT / "electron_template.i").read_text(encoding="utf-8")
    poisson_template = (ROOT / "poisson_template.i").read_text(encoding="utf-8")
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
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
    poisson = prepare._render(
        poisson_template,
        {"LOG_CE": common["LOG_CE"], "W_O2P": common["W_O2P"]},
    )
    (case_dir / "input.i").write_text(electron, encoding="utf-8")
    (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
    (case_dir / "case.json").write_text(
        json.dumps(params, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return params


def static_contract() -> dict[str, object]:
    params = build_case()
    assert params["chi"] == 2.0
    assert params["steps"] == 10
    assert params["fp_min"] == 2
    assert params["fp_max"] == 30
    assert math.isclose(
        float(params["dt_s"]) / float(params["tau_epsilon_s"]),
        2.0,
        rel_tol=1.0e-14,
    )
    assert math.isclose(
        float(params["end_time_s"]) / float(params["tau_epsilon_s"]),
        prepare.FINAL_TAU,
        rel_tol=1.0e-14,
    )

    text = (GENERATED / "gummel_chi2" / "input.i").read_text(encoding="utf-8")
    assert "PhysicsFVLogMolarElectronTimeDerivative" in text
    assert "PhysicsFVLogMolarElectrostaticDrift" in text
    assert "potential = potential_from_poisson" in text
    assert "FullSolveMultiApp" in text
    assert "auto_advance = true" in text
    assert "fixed_point_min_its = 2" in text
    assert "fixed_point_max_its = 30" in text
    assert "fixed_point_relaxation" not in text.lower()
    assert "under_relax" not in text.lower()
    assert "PhysicsFVLogMolarElectronEnergy" not in text

    return {
        "status": "PASS",
        "case": params,
        "claim": "chi=2 plain Gummel control; no under-relaxation or physics change",
    }


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def classify_runtime(
    *,
    returncode: int,
    log_text: str,
    final_time: float | None,
    expected_end_time: float,
    fixed_point_iterations: float | None,
) -> tuple[str, bool]:
    if "FullSolveMultiApp is not compatible with auto_advance=false" in log_text:
        return "CONSTRUCTION_FAILURE", False
    if returncode != 0 and "DIVERGED_MAX_ITS" in log_text:
        return "GUMMEL_DIVERGED", True
    if returncode == 0:
        if final_time is None or not math.isclose(
            final_time, expected_end_time, rel_tol=1.0e-8, abs_tol=1.0e-24
        ):
            return "INCOMPLETE_PHYSICAL_HORIZON", False
        if fixed_point_iterations is None or fixed_point_iterations <= 1.0:
            return "GUMMEL_NOT_EXERCISED", False
        return "GUMMEL_CONVERGED", True
    return "UNCLASSIFIED_RUNTIME_FAILURE", False


def analyze() -> int:
    params = json.loads(
        (GENERATED / "gummel_chi2" / "case.json").read_text(encoding="utf-8")
    )
    log_path = RESULTS / "gummel_chi2_runtime.log"
    rc_path = RESULTS / "gummel_chi2_returncode.txt"
    if not log_path.is_file() or not rc_path.is_file():
        raise SystemExit("missing chi=2 runtime evidence")

    log_text = log_path.read_text(errors="replace")
    returncode = int(rc_path.read_text(encoding="utf-8").strip())

    rows = _rows(GENERATED / "gummel_chi2" / "input_out.csv")
    final_time: float | None = None
    fixed_point_iterations: float | None = None
    n_e_min: float | None = None
    electron_inventory: float | None = None
    if rows:
        row = rows[-1]
        if row.get("time") not in (None, ""):
            final_time = float(row["time"])
        if row.get("fixed_point_iterations") not in (None, ""):
            fixed_point_iterations = float(row["fixed_point_iterations"])
        if row.get("n_e_min") not in (None, ""):
            n_e_min = float(row["n_e_min"])
        if row.get("electron_inventory") not in (None, ""):
            electron_inventory = float(row["electron_inventory"])

    classification, valid = classify_runtime(
        returncode=returncode,
        log_text=log_text,
        final_time=final_time,
        expected_end_time=float(params["end_time_s"]),
        fixed_point_iterations=fixed_point_iterations,
    )
    diverged_reason = None
    if "DIVERGED_MAX_ITS" in log_text:
        diverged_reason = "DIVERGED_MAX_ITS"

    residuals = [
        float(value)
        for value in re.findall(
            r"Picard\s+\|R\|\s*=?\s*([0-9.eE+\-]+)", log_text
        )
    ]

    summary = {
        "issue": 253,
        "sequence": 2,
        "objective": "test plain transient Gummel convergence at chi=2",
        "chi": 2.0,
        "plain_gummel": True,
        "under_relaxation": False,
        "returncode": returncode,
        "classification": classification,
        "evidence_valid": valid,
        "divergence_reason": diverged_reason,
        "final_time_s": final_time,
        "expected_end_time_s": float(params["end_time_s"]),
        "fixed_point_iterations_final": fixed_point_iterations,
        "n_e_min_final_m3": n_e_min,
        "electron_inventory_final": electron_inventory,
        "picard_residual_count": len(residuals),
        "picard_residual_first": residuals[0] if residuals else None,
        "picard_residual_last": residuals[-1] if residuals else None,
        "scientific_scope": (
            "convergence-control evidence only; no dt-release acceptance claim"
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "chi2_control_analysis.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE253_G1_CHI2_CLASSIFICATION:", classification)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if valid else 2


def p0() -> None:
    summary = static_contract()
    print("ISSUE253_G1_CHI2_P0: PASS")
    print(json.dumps(summary, sort_keys=True))


def p1() -> None:
    build_case()
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; "
        "python3 /workspace/bin/physics.py preflight "
        "/workspace/experiments/Issue253_g1_gummel_dt_release/generated_chi2/gummel_chi2/input.i"
    )
    _docker(script)
    print("ISSUE253_G1_CHI2_P1: PASS")


def p2() -> None:
    if not (GENERATED / "gummel_chi2" / "input.i").is_file():
        build_case()
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "mkdir -p /workspace/experiments/Issue253_g1_gummel_dt_release/results_chi2; "
        "make -C /workspace/physics_app -j2; "
        "test -x /workspace/physics_app/physics-opt; "
        "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated_chi2/gummel_chi2; "
        "/workspace/physics_app/physics-opt --check-input -i input.i "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_chi2/gummel_chi2_p2.log 2>&1"
    )
    _docker(script)
    print("ISSUE253_G1_CHI2_P2: PASS")


def p3() -> None:
    if not (REPO / "physics_app" / "physics-opt").is_file():
        raise SystemExit("physics-opt missing: P2 must complete before P3")
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "mkdir -p /workspace/experiments/Issue253_g1_gummel_dt_release/results_chi2; "
        "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated_chi2/gummel_chi2; "
        "set +e; "
        "/workspace/physics_app/physics-opt -i input.i "
        "-snes_monitor -snes_converged_reason -ksp_converged_reason "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_chi2/gummel_chi2_runtime.log 2>&1; "
        "rc=$?; "
        "set -e; "
        "printf '%s\\n' \"$rc\" "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_chi2/gummel_chi2_returncode.txt; "
        "exit 0"
    )
    _docker(script)
    rc = analyze()
    if rc != 0:
        raise SystemExit(rc)
    print("ISSUE253_G1_CHI2_P3: EVIDENCE_READY")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("p0", "p1", "p2", "p3"))
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    {"p0": p0, "p1": p1, "p2": p2, "p3": p3}[args.phase]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
