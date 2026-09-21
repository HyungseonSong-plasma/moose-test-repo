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

from experiments.Issue253_g1_gummel_dt_release import analyze, prepare

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_relaxed"
RESULTS = ROOT / "results_relaxed"
BUILD_BASE_REF = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)
OMEGA = 1.0 / 6.0
CASES = (
    {"name": "ref_chi0p1", "chi": 0.1, "steps": 200, "fp_min": 1, "fp_max": 1},
    {"name": "onepass_chi5", "chi": 5.0, "steps": 4, "fp_min": 1, "fp_max": 1},
    {"name": "relaxed_gummel_chi5", "chi": 5.0, "steps": 4, "fp_min": 2, "fp_max": 30},
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


def _with_relaxed_poisson_multiapp(text: str) -> str:
    needle = """    input_files = poisson_sub.i
    execute_on = TIMESTEP_END
"""
    replacement = """    input_files = poisson_sub.i
    execute_on = TIMESTEP_END
    # Relax the steady Poisson subapp solution between outer electron-Poisson iterations.
    # chi=5 gives the a-priori linear estimate omega = 1/(1+chi) = 1/6.
    relaxation_factor = 0.16666666666666666
    transformed_variables = 'potential_plasma'
    keep_solution_during_restore = true
    update_old_solution_when_keeping_solution_during_restore = false
"""
    if text.count(needle) != 1:
        raise RuntimeError("expected exactly one Poisson MultiApp insertion point")
    return text.replace(needle, replacement, 1)


def build(clean: bool = True) -> list[dict[str, object]]:
    electron_template = (ROOT / "electron_template.i").read_text(encoding="utf-8")
    poisson_template = (ROOT / "poisson_template.i").read_text(encoding="utf-8")
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    built: list[dict[str, object]] = []
    for spec in CASES:
        params = prepare.case_parameters(spec)
        params["relaxation_factor"] = (
            OMEGA if params["name"] == "relaxed_gummel_chi5" else 1.0
        )
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
        if params["name"] == "relaxed_gummel_chi5":
            electron = _with_relaxed_poisson_multiapp(electron)

        poisson = prepare._render(
            poisson_template,
            {"LOG_CE": common["LOG_CE"], "W_O2P": common["W_O2P"]},
        )
        (case_dir / "input.i").write_text(electron, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        (case_dir / "case.json").write_text(
            json.dumps(params, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        built.append(params)

    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 253,
                "sequence": 3,
                "objective": (
                    "chi=5 physically scaled relaxed Gummel versus chi=5 one-pass "
                    "against chi=0.1 reference"
                ),
                "relaxation_target": "Poisson subapp potential_plasma",
                "relaxation_factor": OMEGA,
                "relaxation_formula": "omega=1/(1+chi)",
                "first_poisson_solve_unrelaxed_by_moose_semantics": True,
                "electron_energy_equation": False,
                "mean_electron_energy_eV": 5.73276,
                "chemistry": False,
                "rf_heating": False,
                "heavy_evolution": False,
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
    one = by_name["onepass_chi5"]
    rel = by_name["relaxed_gummel_chi5"]

    assert ref["chi"] == 0.1 and ref["steps"] == 200 and ref["fp_max"] == 1
    assert one["chi"] == 5.0 and one["steps"] == 4 and one["fp_max"] == 1
    assert rel["chi"] == 5.0 and rel["steps"] == 4 and rel["fp_min"] == 2
    assert rel["fp_max"] == 30
    assert math.isclose(float(rel["relaxation_factor"]), 1.0 / 6.0, rel_tol=0.0, abs_tol=1e-16)
    assert math.isclose(float(one["dt_s"]), float(rel["dt_s"]), rel_tol=0.0, abs_tol=0.0)

    for name in by_name:
        text = (GENERATED / name / "input.i").read_text(encoding="utf-8")
        assert "PhysicsFVLogMolarElectronTimeDerivative" in text
        assert "PhysicsFVLogMolarElectrostaticDrift" in text
        assert "potential = potential_from_poisson" in text
        assert "FullSolveMultiApp" in text
        assert "auto_advance = true" in text
        assert "PhysicsFVLogMolarElectronEnergy" not in text
        if name == "relaxed_gummel_chi5":
            assert "relaxation_factor = 0.16666666666666666" in text
            assert "transformed_variables = 'potential_plasma'" in text
            assert "keep_solution_during_restore = true" in text
            assert "update_old_solution_when_keeping_solution_during_restore = false" in text
        else:
            assert "relaxation_factor = 0.16666666666666666" not in text
            assert "transformed_variables = 'potential_plasma'" not in text

    return {
        "status": "PASS",
        "tau_epsilon_s": prepare.tau_epsilon(),
        "omega": OMEGA,
        "cases": built,
        "claim": (
            "same particle-Poisson model; chi=5 relaxed case changes only "
            "the Poisson-to-electron fixed-point update"
        ),
    }


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _fixed_point_stats(case_dir: Path) -> dict[str, float | int | list[float] | None]:
    rows = _rows(case_dir / "input_out.csv")
    vals: list[float] = []
    for row in rows:
        if float(row.get("time", "0") or 0.0) <= 0.0:
            continue
        value = row.get("fixed_point_iterations", "")
        if value != "":
            vals.append(float(value))
    return {
        "per_timestep": vals,
        "count": len(vals),
        "sum": float(sum(vals)) if vals else 0.0,
        "mean": float(sum(vals) / len(vals)) if vals else None,
        "max": float(max(vals)) if vals else None,
    }


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def _picard_residuals(text: str) -> list[float]:
    clean = _strip_ansi(text)
    return [
        float(v)
        for v in re.findall(r"\bPicard\s+\|R\|\s*=\s*([0-9.eE+\-]+)", clean)
    ]


def analyze_result() -> tuple[dict[str, object], int]:
    ref_dir = GENERATED / "ref_chi0p1"
    one_dir = GENERATED / "onepass_chi5"
    rel_dir = GENERATED / "relaxed_gummel_chi5"
    log_path = RESULTS / "relaxed_gummel_chi5_runtime.log"
    rc_path = RESULTS / "relaxed_gummel_chi5_returncode.txt"
    if not log_path.is_file() or not rc_path.is_file():
        raise RuntimeError("missing relaxed chi=5 runtime evidence")

    runtime_log = log_path.read_text(errors="replace")
    relaxed_rc = int(rc_path.read_text(encoding="utf-8").strip())
    residuals = _picard_residuals(runtime_log)

    ref_profile = analyze._final_profile(ref_dir)
    one_profile = analyze._final_profile(one_dir)
    one_metrics = analyze._profile_metrics(ref_profile, one_profile)
    ref_scalar = analyze._final_scalar(ref_dir)
    one_scalar = analyze._final_scalar(one_dir)

    summary: dict[str, object] = {
        "issue": 253,
        "sequence": 3,
        "comparison": (
            "chi=5 omega=1/6 relaxed Gummel vs chi=5 one-pass against chi=0.1 reference"
        ),
        "omega": OMEGA,
        "omega_formula": "1/(1+chi)",
        "relaxation_target": "Poisson subapp potential_plasma",
        "first_poisson_solve_unrelaxed_by_moose_semantics": True,
        "onepass_chi5": one_metrics,
        "scalars": {
            "ref_chi0p1": ref_scalar,
            "onepass_chi5": one_scalar,
        },
        "relaxed_runtime_returncode": relaxed_rc,
        "picard_residual_count": len(residuals),
        "picard_residual_first": residuals[0] if residuals else None,
        "picard_residual_last": residuals[-1] if residuals else None,
        "fixed_point_stats": _fixed_point_stats(rel_dir),
        "gauss_is_hard_gate": False,
    }

    if one_metrics["phi_einf"] < 1.0:
        summary["classification"] = "BASELINE_NOT_REPRODUCED"
        summary["evidence_valid"] = False
        return summary, 2

    if relaxed_rc != 0:
        if "DIVERGED_MAX_ITS" in runtime_log:
            summary["classification"] = "RELAXED_GUMMEL_DIVERGED"
            summary["evidence_valid"] = True
            summary["divergence_reason"] = "DIVERGED_MAX_ITS"
            return summary, 0
        summary["classification"] = "UNCLASSIFIED_RELAXED_RUNTIME_FAILURE"
        summary["evidence_valid"] = False
        return summary, 2

    rel_profile = analyze._final_profile(rel_dir)
    rel_metrics = analyze._profile_metrics(ref_profile, rel_profile)
    rel_scalar = analyze._final_scalar(rel_dir)
    summary["relaxed_gummel_chi5"] = rel_metrics
    summary["scalars"]["relaxed_gummel_chi5"] = rel_scalar

    classification, valid, ratios = analyze.classify_result(
        one_metrics,
        rel_metrics,
        fixed_point_iterations=rel_scalar.get("fixed_point_iterations", 0.0),
    )
    summary["classification"] = classification
    summary["evidence_valid"] = valid
    summary["improvement_ratios_relaxed_over_onepass"] = ratios
    return summary, (0 if valid else 2)


def p0() -> None:
    summary = static_contract()
    print("ISSUE253_G1_RELAXED_P0: PASS")
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
                f"generated_relaxed/{name}/input.i"
            )
            for name in ("ref_chi0p1", "onepass_chi5", "relaxed_gummel_chi5")
        )
    )
    _docker(script)
    print("ISSUE253_G1_RELAXED_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    checks = "; ".join(
        (
            "cd /workspace/experiments/Issue253_g1_gummel_dt_release/"
            f"generated_relaxed/{name} && "
            "/workspace/physics_app/physics-opt --check-input -i input.i "
            "> /workspace/experiments/Issue253_g1_gummel_dt_release/"
            f"results_relaxed/{name}_p2.log 2>&1"
        )
        for name in ("ref_chi0p1", "onepass_chi5", "relaxed_gummel_chi5")
    )
    script = (
        "set -euo pipefail; "
        "source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; "
        "export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; "
        "export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        "mkdir -p /workspace/experiments/Issue253_g1_gummel_dt_release/results_relaxed; "
        "make -C /workspace/physics_app -j2; "
        "test -x /workspace/physics_app/physics-opt; "
        + checks
    )
    _docker(script)
    print("ISSUE253_G1_RELAXED_P2: PASS")


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
        "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated_relaxed/ref_chi0p1; "
        "/workspace/physics_app/physics-opt -i input.i "
        "-snes_monitor -snes_converged_reason -ksp_converged_reason "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_relaxed/ref_chi0p1_runtime.log 2>&1; "
        "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated_relaxed/onepass_chi5; "
        "/workspace/physics_app/physics-opt -i input.i "
        "-snes_monitor -snes_converged_reason -ksp_converged_reason "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_relaxed/onepass_chi5_runtime.log 2>&1; "
        "cd /workspace/experiments/Issue253_g1_gummel_dt_release/generated_relaxed/relaxed_gummel_chi5; "
        "set +e; "
        "/workspace/physics_app/physics-opt -i input.i "
        "-snes_monitor -snes_converged_reason -ksp_converged_reason "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_relaxed/relaxed_gummel_chi5_runtime.log 2>&1; "
        "rc=$?; set -e; "
        "printf '%s\\n' \"$rc\" "
        "> /workspace/experiments/Issue253_g1_gummel_dt_release/results_relaxed/relaxed_gummel_chi5_returncode.txt; "
        "exit 0"
    )
    _docker(script)
    summary, rc = analyze_result()
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "relaxed_analysis.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE253_G1_RELAXED_CLASSIFICATION:", summary["classification"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    if rc != 0:
        raise SystemExit(rc)
    print("ISSUE253_G1_RELAXED_P3: EVIDENCE_READY")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=("p0", "p1", "p2", "p3"))
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    {"p0": p0, "p1": p1, "p2": p2, "p3": p3}[args.phase]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
