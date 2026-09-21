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

from experiments.Issue253_g1_gummel_dt_release import prepare

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
GENERATED = ROOT / "generated_energy09"
RESULTS = ROOT / "results_energy09"
BUILD_BASE_REF = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"

ENERGY_REFERENCE_EV = 5.73276
CHI = 10.0
FINAL_TAU = 1000.0
DT = CHI * prepare.tau_epsilon()
STEPS = int(round(FINAL_TAU / CHI))
END_TIME = FINAL_TAU * prepare.tau_epsilon()

TRANSPORT_SOURCE = REPO / "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
ELASTIC_SOURCE = REPO / "physics_app/data/electron_impact/o2_elastic.txt"

CASES = (
    {"name": "wall_j0_e0", "joule": 0.0, "elastic": 0.0},
    {"name": "wall_j1_e0", "joule": 1.0, "elastic": 0.0},
    {"name": "wall_j0_e1", "joule": 0.0, "elastic": 1.0},
    {"name": "wall_j1_e1", "joule": 1.0, "elastic": 1.0},
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


def _params(spec: dict[str, object]) -> dict[str, object]:
    return {
        "name": str(spec["name"]),
        "joule_heating": bool(spec["joule"]),
        "elastic_collision": bool(spec["elastic"]),
        "energy_wall_flux": True,
        "wall_closure": "COMSOL_HALF_MAXWELLIAN_5_OVER_6",
        "chi": CHI,
        "tau_epsilon_initial_s": prepare.tau_epsilon(),
        "dt_s": DT,
        "end_time_s": END_TIME,
        "end_time_tau_epsilon_initial": FINAL_TAU,
        "steps": STEPS,
        "initial_mean_energy_eV": ENERGY_REFERENCE_EV,
        "transport_pressure_Pa": 0.66661,
        "gas_temperature_K": 300.0,
        "neutral_O2_molar_concentration_mol_m3": 0.0002672491819834387,
    }


def build(clean: bool = True) -> list[dict[str, object]]:
    template = (ROOT / "energy09_template.i").read_text(encoding="utf-8")
    poisson_template = (ROOT / "poisson_template.i").read_text(encoding="utf-8")
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    log_ce0 = math.log(prepare.NE0 / prepare.NA)
    w_o2p0 = prepare.NE0 * prepare.M_O2P / (prepare.RHO * prepare.NA)
    built: list[dict[str, object]] = []

    for spec in CASES:
        p = _params(spec)
        case_dir = GENERATED / str(p["name"])
        case_dir.mkdir(parents=True, exist_ok=True)
        electron = prepare._render(
            template,
            {
                "LOG_CE": f"{log_ce0:.17g}",
                "W_O2P": f"{w_o2p0:.17g}",
                "NE0": f"{prepare.NE0:.17g}",
                "JOULE_FACTOR": "1.0" if p["joule_heating"] else "0.0",
                "ELASTIC_FACTOR": "1.0" if p["elastic_collision"] else "0.0",
                "DT": f"{DT:.17g}",
                "END_TIME": f"{END_TIME:.17g}",
                "STEPS": str(STEPS),
                "TIMESTEP_TOL": f"{max(DT * 1.0e-8, 1.0e-30):.17g}",
            },
        )
        poisson = prepare._render(
            poisson_template,
            {"LOG_CE": f"{log_ce0:.17g}", "W_O2P": f"{w_o2p0:.17g}"},
        )
        poisson = _silence_poisson(poisson)

        (case_dir / "input.i").write_text(electron, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(TRANSPORT_SOURCE, case_dir / "electron_moments.txt")
        shutil.copy2(ELASTIC_SOURCE, case_dir / "o2_elastic.txt")
        (case_dir / "case.json").write_text(
            json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        built.append(p)

    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 253,
                "sequence": 9,
                "objective": (
                    "Solved electron-energy feedback with energy wall flux always on; "
                    "2x2 Joule-heating and O2-elastic toggles"
                ),
                "energy_wall_flux": "ALWAYS_ON",
                "wall_closure": "COMSOL_HALF_MAXWELLIAN_5_OVER_6",
                "wall_particle_flux": "Gamma=(1/2)*n_e*v_th",
                "wall_energy_flux": "q=(5/6)*n_epsilon*v_th",
                "joule_heating_matrix": [False, True],
                "elastic_collision_matrix": [False, True],
                "energy_dependent_mobility_diffusion": True,
                "heavy_evolution": False,
                "chi": CHI,
                "total_time_tau_epsilon_initial": FINAL_TAU,
                "cases": built,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    built = build()
    by = {str(x["name"]): x for x in built}
    assert set(by) == {"wall_j0_e0", "wall_j1_e0", "wall_j0_e1", "wall_j1_e1"}
    assert STEPS == 100
    assert math.isclose(DT / prepare.tau_epsilon(), 10.0, rel_tol=1e-14)
    assert math.isclose(END_TIME / prepare.tau_epsilon(), 1000.0, rel_tol=1e-14)

    expected = {
        "wall_j0_e0": (False, False),
        "wall_j1_e0": (True, False),
        "wall_j0_e1": (False, True),
        "wall_j1_e1": (True, True),
    }
    for name, (joule, elastic) in expected.items():
        p = by[name]
        assert p["energy_wall_flux"] is True
        assert p["joule_heating"] is joule
        assert p["elastic_collision"] is elastic
        text = (GENERATED / name / "input.i").read_text(encoding="utf-8")
        assert "PhysicsFVElectronEnergyWallFluxBC" in text
        assert "expression = '0.5*exp(loge)*sqrt(16.0*" in text
        assert "PhysicsFVElectronEnergyJouleHeating" in text
        assert "PhysicsElectronMeanEnergyMaterial" in text
        assert "PhysicsElectronTransportLookupMaterial" in text
        assert "PhysicsElectronImpactRateMaterial" in text
        assert "bounds_policy = error" in text
        assert "nl_abs_tol = 1.0e-7" in text
        assert "[final_exodus]" in text
        assert "execute_on = 'FINAL'" in text
        assert "@@" not in text

        factor = "1.0" if joule else "0.0"
        assert f"expression = '{factor}*mu'" in text
        assert f"expression = '{factor}*diff'" in text
        efactor = "1.0" if elastic else "0.0"
        assert f"expression = '{efactor}*source'" in text

    return {
        "status": "PASS",
        "tau_epsilon_initial_s": prepare.tau_epsilon(),
        "chi": CHI,
        "total_time_tau_epsilon_initial": FINAL_TAU,
        "energy_wall_flux": "ALWAYS_ON",
        "wall_closure": "COMSOL_HALF_MAXWELLIAN_5_OVER_6",
        "wall_particle_flux": "Gamma=(1/2)*n_e*v_th",
        "wall_energy_flux": "q=(5/6)*n_epsilon*v_th",
        "wall_energy_per_lost_electron": "(5/3)*mean_en=(5/2)*T_e",
        "cases": built,
    }


def p0() -> None:
    print("ISSUE253_G2_ENERGY09_P0: PASS")
    print(json.dumps(static_contract(), indent=2, sort_keys=True))


def p1() -> None:
    build()
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{ROOT.relative_to(REPO)}/generated_energy09/{name}/input.i"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    _docker(script)
    print("ISSUE253_G2_ENERGY09_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    checks = "; ".join(
        f"cd /workspace/{ROOT.relative_to(REPO)}/generated_energy09/{name} && "
        "/workspace/physics_app/physics-opt --check-input -i input.i "
        f"> /workspace/{ROOT.relative_to(REPO)}/results_energy09/{name}_p2.log 2>&1"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        f"mkdir -p /workspace/{ROOT.relative_to(REPO)}/results_energy09; "
        "make -C /workspace/physics_app -j2; test -x /workspace/physics_app/physics-opt; "
        + checks
    )
    _docker(script)
    print("ISSUE253_G2_ENERGY09_P2: PASS")


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _profile(case_dir: Path) -> list[dict[str, float]]:
    candidates: list[tuple[int, Path]] = []
    for path in case_dir.glob("input_final_csv_energy_profile_*.csv"):
        match = re.search(r"_([0-9]+)\.csv$", path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        raise RuntimeError(f"{case_dir.name}: no final energy profile")
    _, path = max(candidates)
    out: list[dict[str, float]] = []
    for row in _rows(path):
        out.append(
            {
                "x": float(row["x"]),
                "electron_density": float(row["electron_density_out"]),
                "potential": float(row["potential_from_poisson"]),
                "n_epsilon": float(row["n_epsilon"]),
                "mean_energy_eV": float(row["mean_energy_out"]),
                "mobility_m2_V_s": float(row["mobility_out"]),
                "diffusion_m2_s": float(row["diffusion_out"]),
                "elastic_loss_candidate_W_m3": float(row["elastic_loss_candidate_out"]),
            }
        )
    out.sort(key=lambda item: item["x"])
    return out


def inner_run(case_name: str) -> int:
    if case_name not in CASE_NAMES:
        raise SystemExit(f"unknown case {case_name}")
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
    (RESULTS / f"{case_name}_returncode.txt").write_text(
        f"{completed.returncode}\n", encoding="utf-8"
    )
    (RESULTS / f"{case_name}_elapsed_seconds.txt").write_text(
        f"{elapsed:.9f}\n", encoding="utf-8"
    )
    return 0


def _f(row: dict[str, str], name: str) -> float:
    return float(row[name])


def analyze_case(case_name: str) -> tuple[dict[str, object], int]:
    p = json.loads((GENERATED / case_name / "case.json").read_text(encoding="utf-8"))
    rc = int((RESULTS / f"{case_name}_returncode.txt").read_text().strip())
    elapsed = float((RESULTS / f"{case_name}_elapsed_seconds.txt").read_text().strip())
    log_text = (RESULTS / f"{case_name}_runtime.log").read_text(
        encoding="utf-8", errors="replace"
    )
    rows = _rows(GENERATED / case_name / "input_step_csv.csv")

    result: dict[str, object] = {
        "case": case_name,
        "joule_heating": p["joule_heating"],
        "elastic_collision": p["elastic_collision"],
        "energy_wall_flux": True,
        "chi": p["chi"],
        "dt_s": p["dt_s"],
        "physical_steps_requested": p["steps"],
        "elapsed_seconds": elapsed,
        "returncode": rc,
    }

    if rc != 0:
        if "DIVERGED_LINE_SEARCH" in log_text:
            result["classification"] = "NONLINEAR_LINE_SEARCH_FAILURE"
        elif "outside" in log_text and "mean" in log_text.lower():
            result["classification"] = "STRICT_LOOKUP_BOUNDS_FAILURE"
        else:
            result["classification"] = "RUNTIME_FAILURE"
        result["evidence_valid"] = False
        return result, 2

    if len(rows) < 2:
        result["classification"] = "MISSING_STEP_HISTORY"
        result["evidence_valid"] = False
        return result, 2

    completed_steps = len(rows) - 1
    final = rows[-1]
    final_time = _f(final, "time")
    full_horizon = (
        completed_steps == int(p["steps"])
        and math.isclose(final_time, float(p["end_time_s"]), rel_tol=1e-10, abs_tol=1e-24)
    )
    if not full_horizon:
        result["classification"] = "INCOMPLETE_HORIZON"
        result["evidence_valid"] = False
        result["physical_steps_completed"] = completed_steps
        result["final_time_s"] = final_time
        return result, 2

    cumulative_wall = 0.0
    cumulative_elastic = 0.0
    for row in rows[1:]:
        cumulative_wall += abs(_f(row, "wall_energy_power_W_m2")) * float(p["dt_s"])
        cumulative_elastic += max(_f(row, "elastic_loss_applied_W_m2"), 0.0) * float(p["dt_s"])

    initial_energy = _f(rows[0], "energy_inventory_J_m2")
    final_energy = _f(final, "energy_inventory_J_m2")
    inferred_joule = final_energy - initial_energy + cumulative_wall + cumulative_elastic

    final_profile = _profile(GENERATED / case_name)
    wall_mean_energy_eV = final_profile[-1]["mean_energy_eV"]
    particle_rate_mol = abs(_f(final, "wall_particle_rate_mol_m2_s"))
    wall_energy_per_lost_electron_eV = (
        abs(_f(final, "wall_energy_power_W_m2"))
        / (particle_rate_mol * prepare.NA * prepare.E_CHARGE)
        if particle_rate_mol > 0.0
        else None
    )

    result.update(
        {
            "classification": "CASE_CONVERGED",
            "evidence_valid": True,
            "physical_steps_completed": completed_steps,
            "final_time_s": final_time,
            "total_fixed_point_iterations": int(round(_f(final, "cumulative_fixed_point_iterations"))),
            "final_energy_inventory_J_m2": final_energy,
            "energy_inventory_change_J_m2": final_energy - initial_energy,
            "cumulative_wall_energy_loss_J_m2": cumulative_wall,
            "cumulative_elastic_energy_loss_J_m2": cumulative_elastic,
            "cumulative_inferred_joule_input_J_m2": inferred_joule,
            "final_wall_energy_power_W_m2": abs(_f(final, "wall_energy_power_W_m2")),
            "final_wall_particle_rate_mol_m2_s": particle_rate_mol,
            "final_wall_mean_energy_eV": wall_mean_energy_eV,
            "final_wall_energy_per_lost_electron_eV": wall_energy_per_lost_electron_eV,
            "expected_wall_energy_per_lost_electron_eV": (5.0 / 3.0) * wall_mean_energy_eV,
            "final_elastic_loss_candidate_W_m2": max(
                _f(final, "elastic_loss_candidate_W_m2"), 0.0
            ),
            "final_elastic_loss_applied_W_m2": max(
                _f(final, "elastic_loss_applied_W_m2"), 0.0
            ),
            "final_mean_energy_avg_eV": _f(final, "mean_energy_avg_eV"),
            "final_mean_energy_min_eV": _f(final, "mean_energy_min_eV"),
            "final_mean_energy_max_eV": _f(final, "mean_energy_max_eV"),
            "final_electron_mobility_avg": _f(final, "electron_mobility_avg"),
            "final_electron_diffusion_avg": _f(final, "electron_diffusion_avg"),
            "final_phi_min_V": _f(final, "phi_min"),
            "final_phi_max_V": _f(final, "phi_max"),
            "final_n_e_min_m3": _f(final, "n_e_min"),
            "final_n_e_max_m3": _f(final, "n_e_max"),
            "final_profile": final_profile,
        }
    )
    return result, 0


def run_case(case_name: str) -> None:
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        f"python3 /workspace/{ROOT.relative_to(REPO)}/energy09_control.py --inner-run {case_name}"
    )
    _docker(script)
    result, code = analyze_case(case_name)
    out = RESULTS / f"{case_name}_result.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE253_G2_ENERGY09_CASE:", case_name, result["classification"])
    print(json.dumps(result, indent=2, sort_keys=True))
    if code:
        raise SystemExit(code)


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [name for name in CASE_NAMES if name not in found]
    if missing:
        raise RuntimeError(f"missing energy09 result(s): {missing}")

    if not all(bool(found[name].get("evidence_valid")) for name in CASE_NAMES):
        return {
            "issue": 253,
            "sequence": 9,
            "classification": "ENERGY09_INVALID_EVIDENCE",
            "evidence_valid": False,
            "cases": found,
        }

    def delta(a: str, b: str, key: str) -> float:
        return float(found[a][key]) - float(found[b][key])

    comparisons = {
        "joule_effect_elastic_off": {
            "mean_energy_delta_eV": delta("wall_j1_e0", "wall_j0_e0", "final_mean_energy_avg_eV"),
            "wall_loss_power_delta_W_m2": delta("wall_j1_e0", "wall_j0_e0", "final_wall_energy_power_W_m2"),
            "elastic_candidate_loss_delta_W_m2": delta("wall_j1_e0", "wall_j0_e0", "final_elastic_loss_candidate_W_m2"),
        },
        "joule_effect_elastic_on": {
            "mean_energy_delta_eV": delta("wall_j1_e1", "wall_j0_e1", "final_mean_energy_avg_eV"),
            "wall_loss_power_delta_W_m2": delta("wall_j1_e1", "wall_j0_e1", "final_wall_energy_power_W_m2"),
            "elastic_candidate_loss_delta_W_m2": delta("wall_j1_e1", "wall_j0_e1", "final_elastic_loss_candidate_W_m2"),
        },
        "elastic_effect_joule_off": {
            "mean_energy_delta_eV": delta("wall_j0_e1", "wall_j0_e0", "final_mean_energy_avg_eV"),
            "wall_loss_power_delta_W_m2": delta("wall_j0_e1", "wall_j0_e0", "final_wall_energy_power_W_m2"),
            "elastic_candidate_loss_delta_W_m2": delta("wall_j0_e1", "wall_j0_e0", "final_elastic_loss_candidate_W_m2"),
        },
        "elastic_effect_joule_on": {
            "mean_energy_delta_eV": delta("wall_j1_e1", "wall_j1_e0", "final_mean_energy_avg_eV"),
            "wall_loss_power_delta_W_m2": delta("wall_j1_e1", "wall_j1_e0", "final_wall_energy_power_W_m2"),
            "elastic_candidate_loss_delta_W_m2": delta("wall_j1_e1", "wall_j1_e0", "final_elastic_loss_candidate_W_m2"),
        },
    }
    return {
        "issue": 253,
        "sequence": 9,
        "classification": "ENERGY09_MATRIX_COMPLETE",
        "evidence_valid": True,
        "energy_wall_flux": "ALWAYS_ON",
        "cases": found,
        "comparisons": comparisons,
    }


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
        root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
        if not root:
            raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
        summary = aggregate(Path(root))
        out = RESULTS / "energy09_summary.json"
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("ISSUE253_G2_ENERGY09_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
